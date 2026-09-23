#!/usr/bin/env python
"""Stat-effect strat lab -- when to throw a move whose stat change outlasts it.

Plan of record: docs/statfx_strat_plan.md. The engine is a PvPoke-AI port:
it picks a charged move by immediate damage-per-energy and turns-to-KO, and
gives no value to a GUARANTEED stat change that persists for the rest of the
fight (Drain Punch +1 Def, Icy Wind -1 opp Atk, Superpower -1/-1 self). This
lab A/Bs generic rules that re-choose WHICH affordable charged move to throw
at the moments the engine has already decided to throw -- timing is left to
the engine, so every variant differs from plain PvPoke only in move identity.

Modes (both read a rendered dive page for the focal, moveset, opponent pool
and opponent IVs, so the pool is exactly the published one):

  oracle  Per-cell hindsight ceiling at one focal spread: brute-force every
          identity sequence over the engine's fire points.
  rules   Every registered variant over a stride of focal spreads x all
          opponents x 9 scenarios x {pvpoke, rank1} opp IVs x {bait, nobait},
          written incrementally to --out-dir, one .npz per task. The 'engine'
          variant is re-simmed too and must equal the page tensor exactly
          (proves the lab is on the production path); `summarize` aborts if
          it does not.
  summarize  Strict-bar metrics (Cramorant contract: per start scenario x
          opp-IV mode x bait, net win flips >= 0 AND mean rating delta >= 0
          vs plain PvPoke) for every variant, from --out-dir.

Direct simulate() calls only; the sweep cache is never touched.

    direnv exec . python scripts/statfx_lab.py rules \\
        --page userdata/website/shadow-sableye-great-league/index.html \\
        --stride 13 --out-dir userdata/statfx_lab/shadow_sableye_s13
    direnv exec . python scripts/statfx_lab.py summarize \\
        --out-dir userdata/statfx_lab/shadow_sableye_s13
"""
from __future__ import annotations

import argparse
import functools
import json
import math
import multiprocessing
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

from gopvpsim.battle import (BattlePokemon, _calc_turns_to_live,  # noqa: E402
                             pvpoke_dp, pvpoke_simulate_shield, simulate)
from gopvpsim.moves import get_moves  # noqa: E402
from gopvpsim.pokemon import Pokemon  # noqa: E402

SCENARIOS = [(a, b) for a in (0, 1, 2) for b in (0, 1, 2)]
SLICES = [('pvpoke', 'bait'), ('pvpoke', 'nobait'),
          ('rank1', 'bait'), ('rank1', 'nobait')]
N_IV = 4096
STAGE_CAP = 4


# ---------------------------------------------------------------------------
# Class membership: guaranteed, persistent stat effects
# ---------------------------------------------------------------------------

def stat_effect(move):
    """(kind, stat_index) for a GUARANTEED stat-stage move, else None.

    kind: 'self_buff' | 'opp_debuff' (help us) | 'self_debuff' (costs us).
    stat_index: 0 = attack, 1 = defense (PvPoke's buffs=[atk, def]).
    Chance effects (Moonblast 10%, Air Cutter 12.5%) are excluded on
    purpose: a strategy cannot choose to land them.
    """
    buffs = move.get('buffs')
    if not buffs or not any(buffs):
        return None
    if float(move.get('buffApplyChance') or 0) < 1:
        return None
    target = move.get('buffTarget')
    stat = 0 if buffs[0] else 1
    if target == 'self':
        return ('self_buff' if sum(buffs) > 0 else 'self_debuff', stat)
    if target == 'opponent' and sum(buffs) < 0:
        return ('opp_debuff', stat)
    return None


def split_moves(charged):
    """(effect_move, other_move) for a 2-charged-move set whose effect
    helps us, else (None, None). Self-debuffers are the mirror-image
    question and get their own rules later (plan, phase 3)."""
    if len(charged) != 2:
        return None, None
    eff = [stat_effect(m) for m in charged]
    helps = [e is not None and e[0] in ('self_buff', 'opp_debuff') for e in eff]
    if helps.count(True) != 1:
        return None, None
    i = helps.index(True)
    return charged[i], charged[1 - i]


# ---------------------------------------------------------------------------
# Rule features (generic -- no species names anywhere)
# ---------------------------------------------------------------------------

def effect_stage(att, dfn, move):
    """Current stage on the stat `move` pushes (ours for a self-buff, the
    opponent's for a debuff), signed so HIGHER = more of the effect."""
    kind, stat = stat_effect(move)
    if kind == 'self_buff':
        return att.atk_stage if stat == 0 else att.def_stage
    return -(dfn.atk_stage if stat == 0 else dfn.def_stage)


def throws_after(att, dfn, move):
    """Rough count of further charged throws we get after this one:
    energy left + fast-move energy over PvPoke's turns-to-live estimate,
    divided by the cheapest charged cost. An approximation (ignores
    shields and the opponent's charged moves beyond what turns-to-live
    already models) -- it gates rules, it is not reported as a fact."""
    fm = att.fast_move
    turns = fm.get('_turns') or max(1, fm.get('cooldown', 500) // 500)
    gain_per_turn = fm.get('energyGain', 0) / turns
    ttl = _calc_turns_to_live(att, dfn)
    if not math.isfinite(ttl):
        return 99                      # the opponent cannot finish us
    energy = att.energy - move['energy'] + gain_per_turn * max(ttl, 0)
    return int(energy // min(m['energy'] for m in att.charged_moves))


def kos(att, dfn, move):
    return att.charged_move_damage(move, dfn) >= dfn.hp


# ---------------------------------------------------------------------------
# Variants: each maps a fire point to 'E', 'O' or None (keep the engine's)
# ---------------------------------------------------------------------------

def _into_shields(att, dfn, fired, E, O):
    if fired is O and dfn.shields > 0 and not kos(att, dfn, O):
        return 'E'
    return None


def _into_predicted_shield(att, dfn, fired, E, O):
    """Throw the effect move only when the opponent would SHIELD it: the
    shield still burns and the effect lands for free. Asks the opponent's
    actual shield policy (PvPoke's), so it assumes a PvPoke-like shielder;
    'shields' (any shield up) is the policy-free version. Motivated by
    Aegislash (Shield), which declines shields on hits under half its HP."""
    if (fired is O and dfn.shields > 0 and not kos(att, dfn, O)
            and pvpoke_simulate_shield(att, dfn, E)):
        return 'E'
    return None


def _early(att, dfn, fired, E, O):
    if (fired is O and effect_stage(att, dfn, E) <= 0
            and not kos(att, dfn, O) and throws_after(att, dfn, E) >= 1):
        return 'E'
    return None


def _early2(att, dfn, fired, E, O):
    if (fired is O and effect_stage(att, dfn, E) < 2
            and not kos(att, dfn, O) and throws_after(att, dfn, E) >= 1):
        return 'E'
    return None


def _cash_out(att, dfn, fired, E, O):
    """Last throw with no shield in the way: take the damage."""
    if (fired is E and dfn.shields == 0
            and throws_after(att, dfn, O) == 0):
        return 'O'
    return None


def _first(*rules):
    def rule(*a):
        for r in rules:
            got = r(*a)
            if got is not None:
                return got
        return None
    return rule


VARIANTS = {
    'engine': None,
    'shields': _into_shields,
    'shields_pred': _into_predicted_shield,
    'shields_pred+early': _first(_into_predicted_shield, _early),
    'early': _early,
    'early2': _early2,
    'shields+early': _first(_into_shields, _early),
    'shields+early+cash': _first(_cash_out, _into_shields, _early),
    'early+cash': _first(_cash_out, _early),
}


def make_policy(rule, bait, script=None, trace=None):
    """pvpoke_dp, with the thrown move re-chosen by `rule` (or by the
    oracle `script`, a sequence of 'E'/'O' over the decision points).
    The swap target must be affordable, so timing is untouched."""
    base = pvpoke_dp if bait == 'bait' else functools.partial(
        pvpoke_dp, bait_shields=False)
    k = [0]

    def policy(att, dfn, mechanics='new', **kw):
        i = base(att, dfn, mechanics=mechanics, **kw)
        if i is None or (rule is None and script is None):
            return i
        E, O = split_moves(att.charged_moves)
        if E is None:
            return i
        fired = att.charged_moves[i]
        alt = O if fired is E else E
        if att.energy < alt['energy']:
            return i                      # no real choice at this moment
        if script is not None:
            if trace is not None:
                trace[0] += 1
            want = script[k[0]] if k[0] < len(script) else None
            k[0] += 1
        else:
            want = rule(att, dfn, fired, E, O)
        if want is None:
            return i
        return att.charged_moves.index(E if want == 'E' else O)
    return policy


# ---------------------------------------------------------------------------
# Page plumbing (same construction as cramorant_mini_sweep: page opponents,
# per-mode opponent IVs, focal at the level-50 cap)
# ---------------------------------------------------------------------------

def load_page(path):
    from cramorant_certify import load_page as _lp
    return _lp(path)


def focal_spec(data):
    fid = data['focalLink']['id']
    return data['species'], fid.endswith('_shadow'), data['movesets'][0]


def make_bp(species, league, shadow, fast_id, charged_ids, ivs, max_level=50.0):
    fm, cm = get_moves()
    p = Pokemon.at_best_level(species, *ivs, league=league, shadow=shadow,
                              max_level=max_level)
    cp_cap = {'great': 1500, 'ultra': 2500}[league]
    return BattlePokemon.from_pokemon(
        p, dict(fm[fast_id]), [dict(cm[c]) for c in charged_ids],
        league_cp=cp_cap)


def make_opp(data, oi, mode):
    from cramorant_certify import species_from_link
    link = data['oppLinks'][oi]
    mv = link['moves'].split('-')
    clean, shadow = species_from_link(link)
    return make_bp(clean, data['league'], shadow, mv[0], mv[1:],
                   tuple(link['byMode'][mode]['ivs']))


def battle(data, focal_ivs, opp, scen, policy):
    species, shadow, ms = focal_spec(data)
    me = make_bp(species, data['league'], shadow, ms['fast'], ms['charged'],
                 focal_ivs)
    me.reset_for_battle(scen[0], opp)
    opp.reset_for_battle(scen[1], me)
    r = simulate(me, opp, charged_policy_0=policy, charged_policy_1=pvpoke_dp)
    return round(r.pvpoke_score(0))


def iv_triplet(data, iv):
    return (data['ivA'][iv], data['ivD'][iv], data['ivS'][iv])


# ---------------------------------------------------------------------------
# rules mode
# ---------------------------------------------------------------------------

def _rules_task(args):
    page, out_dir, mode, bait, oi, ivs, variants = args
    out = Path(out_dir) / f'{mode}_{bait}_{oi:03d}.npz'
    if out.exists():
        return str(out)
    data, _ = load_page(page)
    names = variants
    scores = np.zeros((len(ivs), 9, len(names)), dtype=np.int16)
    opp = make_opp(data, oi, mode)
    for a, iv in enumerate(ivs):
        trip = iv_triplet(data, iv)
        for si, scen in enumerate(SCENARIOS):
            for vi, name in enumerate(names):
                scores[a, si, vi] = battle(
                    data, trip, opp, scen, make_policy(VARIANTS[name], bait))
    tmp = out.with_suffix('.tmp.npz')
    np.savez(tmp, scores=scores, ivs=np.asarray(ivs), variants=np.asarray(names))
    os.replace(tmp, out)
    return str(out)


def cmd_rules(args):
    data, _ = load_page(args.page)
    E, O = split_moves([get_moves()[1][c] for c in data['movesets'][0]['charged']])
    if E is None:
        raise SystemExit('page moveset has no helpful guaranteed stat effect')
    variants = ['engine'] + [v for v in (args.variants.split(',') if args.variants
                                         else VARIANTS) if v != 'engine']
    unknown = set(variants) - set(VARIANTS)
    if unknown:
        raise SystemExit(f'unknown variant(s): {sorted(unknown)}')
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'run.json').write_text(json.dumps({
        'page': args.page, 'stride': args.stride, 'offset': args.offset,
        'variants': variants, 'effect_move': E['moveId'],
        'other_move': O['moveId'], 'started': time.strftime('%Y-%m-%d %H:%M'),
    }, indent=1))
    ivs = list(range(args.offset, N_IV, args.stride))
    n_opp = len(data['opponents'])
    tasks = [(args.page, str(out_dir), m, b, oi, ivs, variants)
             for m, b in SLICES for oi in range(n_opp)]
    ctx = multiprocessing.get_context('spawn')
    done = 0
    with ctx.Pool(args.procs) as pool:
        for _ in pool.imap_unordered(_rules_task, tasks):
            done += 1
            print(f'{done}/{len(tasks)} tasks', flush=True)


def cmd_summarize(args):
    out_dir = Path(args.out_dir)
    run = json.loads((out_dir / 'run.json').read_text())
    data, tensors = load_page(run['page'])
    n_opp = len(data['opponents'])
    names = run['variants']
    res = {}
    for mode, bait in SLICES:
        key = f"0_{mode}{'' if bait == 'bait' else ':nobait'}"
        tens = tensors[key].reshape(N_IV, 9, n_opp).astype(np.int32)
        per_opp = []
        for oi in range(n_opp):
            f = out_dir / f'{mode}_{bait}_{oi:03d}.npz'
            if not f.exists():
                raise SystemExit(f'missing {f} (run incomplete)')
            z = np.load(f)
            per_opp.append(z['scores'].astype(np.int32))
            ivs = z['ivs']
        S = np.stack(per_opp, axis=2)          # [n_iv, 9, n_opp, n_var]
        base = tens[ivs]                        # [n_iv, 9, n_opp]
        eng = S[..., names.index('engine')]
        bad = int((eng != base).sum())
        if bad:
            raise SystemExit(f'{mode}/{bait}: {bad} engine cells differ from the '
                             'page tensor -- the lab is NOT on the production path')
        for vi, name in enumerate(names):
            v = S[..., vi]
            for si, (a, b) in enumerate(SCENARIOS):
                x, y = base[:, si, :], v[:, si, :]
                gained = int(((x < 500) & (y >= 500)).sum())
                lost = int(((x >= 500) & (y < 500)).sum())
                res.setdefault(name, {}).setdefault(f'{a}v{b}', {})[f'{mode}/{bait}'] = {
                    'net': gained - lost, 'gained': gained, 'lost': lost,
                    'mean': round(float((y - x).mean()), 2),
                    'changed': int((x != y).sum()), 'cells': int(x.size)}
    (out_dir / 'summary.json').write_text(json.dumps(res, indent=1))
    print(f"{run['page']}  stride {run['stride']}  "
          f"{run['effect_move']} vs {run['other_move']}")
    print('engine == page tensor on every cell (production path verified)')
    print('cell = worst-slice mean / worst-slice net flips; * = strict bar met '
          'in all 4 slices')
    print(f"{'variant':<20}" + ''.join(f'{s:>13}' for s in res['engine']))
    for name in names:
        if name == 'engine':
            continue
        row = f'{name:<20}'
        for scen, sl in res[name].items():
            m = min(c['mean'] for c in sl.values())
            n = min(c['net'] for c in sl.values())
            ok = '*' if (m >= 0 and n >= 0) else ' '
            row += f'{m:>+7.1f}/{n:>+4d}{ok}'
        print(row)


# ---------------------------------------------------------------------------
# oracle mode
# ---------------------------------------------------------------------------

def _oracle_cell(args):
    page, mode, bait, oi, iv, max_depth = args
    data, _ = load_page(page)
    opp = make_opp(data, oi, mode)
    trip = iv_triplet(data, iv)
    out = []
    for scen in SCENARIOS:
        best = {'score': None}

        def dfs(prefix):
            trace = [0]
            s = battle(data, trip, opp, scen,
                       make_policy(None, bait, script=prefix, trace=trace))
            if best['score'] is None or s > best['score']:
                best.update(score=s, script=''.join(prefix))
            if trace[0] > len(prefix) and len(prefix) < max_depth:
                for c in 'EO':
                    dfs(prefix + [c])
        base = battle(data, trip, opp, scen, make_policy(None, bait))
        dfs([])
        out.append((base, best['score'], best['script']))
    return oi, out


def cmd_oracle(args):
    data, _ = load_page(args.page)
    iv = data['pvpokeRefIvIdx'] if args.iv is None else args.iv
    n_opp = len(data['opponents'])
    tasks = [(args.page, args.mode, args.bait, oi, iv, args.max_depth)
             for oi in range(n_opp)]
    ctx = multiprocessing.get_context('spawn')
    rows = []
    with ctx.Pool(args.procs) as pool:
        for oi, cells in pool.imap_unordered(_oracle_cell, tasks):
            rows.append((oi, cells))
    rows.sort()
    per = {f'{a}v{b}': [0, 0, 0] for a, b in SCENARIOS}
    for oi, cells in rows:
        for (a, b), (base, best, script) in zip(SCENARIOS, cells):
            p = per[f'{a}v{b}']
            p[0] += best - base
            p[1] += (best >= 500) - (base >= 500)
            p[2] += best > base
    print(f'oracle ceiling, iv {iv} {iv_triplet(data, iv)}, {args.mode}/{args.bait}, '
          f'{n_opp} opponents (mean gain / net flips / cells improved)')
    for scen, (g, f, n) in per.items():
        print(f'  {scen}: {g / n_opp:+6.1f} / {f:+3d} / {n}')
    if args.out:
        Path(args.out).write_text(json.dumps(
            {data['opponents'][oi]: cells for oi, cells in rows}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    procs = max(1, (os.cpu_count() or 2) - 2)
    r = sub.add_parser('rules')
    r.add_argument('--page', required=True)
    r.add_argument('--stride', type=int, default=13,
                   help='IV index stride; coprime with 16 (7, 13, 17, ...) '
                        'or the stamina axis aliases; 1 = all 4096')
    r.add_argument('--offset', type=int, default=0)
    r.add_argument('--out-dir', required=True)
    r.add_argument('--procs', type=int, default=procs)
    r.add_argument('--variants', default=None,
                   help="comma list (default: all); 'engine' is always added")
    s = sub.add_parser('summarize')
    s.add_argument('--out-dir', required=True)
    o = sub.add_parser('oracle')
    o.add_argument('--page', required=True)
    o.add_argument('--mode', default='pvpoke', choices=['pvpoke', 'rank1'])
    o.add_argument('--bait', default='bait', choices=['bait', 'nobait'])
    o.add_argument('--iv', type=int, default=None,
                   help="focal IV index (default: the page's PvPoke reference)")
    o.add_argument('--max-depth', type=int, default=8)
    o.add_argument('--procs', type=int, default=procs)
    o.add_argument('--out')
    args = ap.parse_args()
    {'rules': cmd_rules, 'summarize': cmd_summarize, 'oracle': cmd_oracle}[args.cmd](args)


if __name__ == '__main__':
    main()
