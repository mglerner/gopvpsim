#!/usr/bin/env python
"""Cramorant policy lab -- A/B candidate "PoGoDives strat" rules.

Plan of record: docs/cramorant_policy_plan.md. Runs the knob grid over
the standard GL/UL opponent pools (PvPoke default IVs both sides, all 9
shield cells x both focal bait modes per pair) and reports per-variant
win counts + cell flips vs the PvPoke-default baseline.

Everything goes through direct simulate() calls; the sweep cache is
NEVER touched (the knobs are battle.py module globals the cache does
not key on -- see the warning at their definitions). The baseline
variant is the all-defaults engine by construction; a post-run tripwire
re-runs a baseline sample to catch knob leakage between variants.

Usage:
  direnv exec . python scripts/cramorant_policy_lab.py --league both \\
      --out userdata/cramorant_lab/round1.json
  # Robustness round (plan H4/H5): opponents withhold charged moves vs a
  # prey-holder, and/or shield lethal Dives (the fixed upstream rule):
  ... --opponent-counter withhold --lethal-dive-fix
"""
import argparse
import functools
import itertools
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

import gopvpsim.battle as B  # noqa: E402
from gopvpsim.battle import BattlePokemon, pvpoke_dp, simulate  # noqa: E402
from gopvpsim.data import get_default_moveset  # noqa: E402
from gopvpsim.moves import get_moves  # noqa: E402
from gopvpsim.pokemon import Pokemon, pvpoke_default_ivs  # noqa: E402

from deep_dive_lib.opponents import _parse_opponent_pool_line  # noqa: E402

POOLS = {
    'great': REPO / 'opponent_pools' / 'gl_top50_plus_cs.txt',
    'ultra': REPO / 'opponent_pools' / 'ul_top60.txt',
}
KNOB_NAMES = ('_CRAM_DIVE_GATE_DPE', '_CRAM_DIVE_GATE_HP', '_CRAM_TANK_MULT',
              '_CRAM_DELAY_GORGING', '_CRAM_LETHAL_DIVE_SHIELD_FIX')
PVPOKE_DEFAULTS = {'_CRAM_DIVE_GATE_DPE': 1.5, '_CRAM_DIVE_GATE_HP': 1.3,
                   '_CRAM_TANK_MULT': 2.2, '_CRAM_DELAY_GORGING': False,
                   '_CRAM_LETHAL_DIVE_SHIELD_FIX': False}
SCENARIOS = [(a, b) for a in (0, 1, 2) for b in (0, 1, 2)]


def build_grid():
    """The round-1 knob grid (docs/cramorant_policy_plan.md)."""
    variants = {'baseline': dict(PVPOKE_DEFAULTS)}
    for dpe, hp, tank, delay in itertools.product(
            (0.0, 1.5, 3.0, 1e9), (1.0, 1.3),
            (1.4, 1.8, 2.2, 2.6, 1e9), (False, True)):
        knobs = {'_CRAM_DIVE_GATE_DPE': dpe, '_CRAM_DIVE_GATE_HP': hp,
                 '_CRAM_TANK_MULT': tank, '_CRAM_DELAY_GORGING': delay,
                 '_CRAM_LETHAL_DIVE_SHIELD_FIX': False}
        if knobs == variants['baseline']:
            continue   # identical to baseline; skip the duplicate
        name = (f"dpe{dpe:g}_hp{hp:g}_tank{tank:g}"
                f"{'_delayG' if delay else ''}")
        variants[name] = knobs
    return variants


def load_pool(league):
    """[(display, species, shadow, fast_id, charged_ids)] from the pool file,
    resolving default movesets; entries that fail to resolve are skipped
    with a note (e.g. cup-only species missing from league rankings)."""
    out, skipped = [], []
    for raw in POOLS[league].read_text().splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        display, base, shadow, fast_o, charged_o = \
            _parse_opponent_pool_line(line)
        try:
            fast, charged = get_default_moveset(base, league, shadow=shadow)
        except KeyError:
            skipped.append(display)
            continue
        out.append((display, base, shadow,
                    fast_o or fast,
                    [c.strip() for c in charged_o.split(',')] if charged_o
                    else charged))
    return out, skipped


def make_bp(species, league, shadow, fast_id, charged_ids, ivs=None):
    fm, cm = get_moves()
    if ivs is None:
        _lv, a, d, s = pvpoke_default_ivs(species, league=league,
                                          shadow=shadow)
        ivs = (a, d, s)
    p = Pokemon.at_best_level(species, *ivs, league=league, shadow=shadow)
    cp_cap = {'great': 1500, 'ultra': 2500}[league]
    return BattlePokemon.from_pokemon(
        p, dict(fm[fast_id]), [dict(cm[c]) for c in charged_ids],
        league_cp=cp_cap)


def make_withhold_policy():
    """Plan H5 counter-policy: the opponent withholds non-lethal charged
    moves while Cramorant holds prey (denying the missile a trigger)."""
    def withhold(attacker, defender, mechanics='legacy'):
        idx = pvpoke_dp(attacker, defender, mechanics=mechanics)
        if idx is not None and B._holding_prey(defender):
            move = attacker.charged_moves[idx]
            if attacker.charged_move_damage(move, defender) < defender.hp:
                return None
        return idx
    return withhold


def run_variant(name, knobs, league, pool, opponent_counter=None,
                progress=None, focal_ivs=None):
    """All cells for one variant. Returns list of cell dicts."""
    for k, v in knobs.items():
        setattr(B, k, v)
    cells = []
    opp_policy = (make_withhold_policy() if opponent_counter == 'withhold'
                  else pvpoke_dp)
    nobait = functools.partial(pvpoke_dp, bait_shields=False)
    for display, species, shadow, fast_id, charged_ids in pool:
        try:
            cram = make_bp('Cramorant', league, False, 'PECK',
                           ['DIVE', 'FLY'], ivs=focal_ivs)
            opp = make_bp(species, league, shadow, fast_id, charged_ids)
        except KeyError as e:
            cells.append({'opp': display, 'error': str(e)})
            continue
        for bait_label, focal_policy in (('bait', pvpoke_dp),
                                         ('nobait', nobait)):
            for s1, s2 in SCENARIOS:
                cram.reset_for_battle(s1, opp)
                opp.reset_for_battle(s2, cram)
                r = simulate(cram, opp,
                             charged_policy_0=focal_policy,
                             charged_policy_1=opp_policy)
                cells.append({'variant': name, 'league': league,
                              'opp': display, 's1': s1, 's2': s2,
                              'bait': bait_label,
                              'score': round(r.pvpoke_score(0), 1),
                              'winner': r.winner})
        if progress:
            progress()
    # Restore defaults so variants can't leak into each other.
    for k, v in PVPOKE_DEFAULTS.items():
        setattr(B, k, v)
    return cells


def summarize(cells_by_variant):
    """Per-variant W/D/L + flips vs baseline."""
    def key(c):
        return (c['league'], c['opp'], c['s1'], c['s2'], c['bait'])
    base = {key(c): c for c in cells_by_variant['baseline']
            if 'error' not in c}
    out = {}
    for name, cells in cells_by_variant.items():
        wins = sum(1 for c in cells if c.get('winner') == 0)
        draws = sum(1 for c in cells
                    if 'error' not in c and c.get('winner') is None)
        losses = sum(1 for c in cells if c.get('winner') == 1)
        gained, lost = [], []
        for c in cells:
            if 'error' in c:
                continue
            b = base.get(key(c))
            if b is None:
                continue
            bw, cw = b['winner'], c['winner']
            if (cw == 0 and bw != 0) or (cw is None and bw == 1):
                gained.append(key(c))
            elif (bw == 0 and cw != 0) or (bw is None and cw == 1):
                lost.append(key(c))
        out[name] = {'wins': wins, 'draws': draws, 'losses': losses,
                     'net_vs_baseline': len(gained) - len(lost),
                     'gained': gained, 'lost': lost}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--league', default='both',
                    choices=['great', 'ultra', 'both'])
    ap.add_argument('--out', default=None,
                    help='JSON output path (default: userdata/cramorant_lab/'
                         'lab_<timestamp>.json)')
    ap.add_argument('--variants', default=None,
                    help='comma-separated variant-name filter over the grid')
    ap.add_argument('--opponent-counter', default=None,
                    choices=['withhold'],
                    help='robustness round: opponent counter-policy')
    ap.add_argument('--focal-ivs', default=None, metavar='A/D/S',
                    help='override the Cramorant focal IVs (default: PvPoke '
                         'default IVs), e.g. 0/15/14 -- for the IV-spread '
                         'robustness round')
    ap.add_argument('--lethal-dive-fix', action='store_true',
                    help='robustness round: opponents shield lethal Dives '
                         '(the fixed upstream rule) in EVERY variant')
    args = ap.parse_args()

    for k, v in PVPOKE_DEFAULTS.items():
        assert getattr(B, k) == v, f'knob {k} not at PvPoke default at start'

    variants = build_grid()
    if args.variants:
        keep = set(args.variants.split(',')) | {'baseline'}
        variants = {k: v for k, v in variants.items() if k in keep}
    if args.lethal_dive_fix:
        for v in variants.values():
            v['_CRAM_LETHAL_DIVE_SHIELD_FIX'] = True

    focal_ivs = (tuple(int(x) for x in args.focal_ivs.split('/'))
                 if args.focal_ivs else None)
    leagues = ['great', 'ultra'] if args.league == 'both' else [args.league]
    out_path = Path(args.out) if args.out else (
        REPO / 'userdata' / 'cramorant_lab' /
        f'lab_{time.strftime("%Y%m%d_%H%M%S")}.json')
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cells_by_variant = {}
    t0 = time.time()
    for league in leagues:
        pool, skipped = load_pool(league)
        print(f'[{league}] pool: {len(pool)} opponents'
              + (f' (skipped: {skipped})' if skipped else ''), flush=True)
        for i, (name, knobs) in enumerate(variants.items()):
            cells = run_variant(name, knobs, league, pool,
                                opponent_counter=args.opponent_counter,
                                focal_ivs=focal_ivs)
            cells_by_variant.setdefault(name, []).extend(cells)
            print(f'[{league}] {i + 1}/{len(variants)} {name} '
                  f'({time.time() - t0:.0f}s)', flush=True)

    # Knob-leak tripwire: a baseline re-run sample must be bit-identical.
    league = leagues[0]
    pool, _ = load_pool(league)
    sample = run_variant('baseline_recheck', dict(PVPOKE_DEFAULTS),
                         league, pool[:3],
                         opponent_counter=args.opponent_counter,
                         focal_ivs=focal_ivs)
    orig = [c for c in cells_by_variant['baseline']
            if c.get('league') == league
            and c.get('opp') in {p[0] for p in pool[:3]}]
    recheck = [{**c, 'variant': 'baseline'} for c in sample]
    assert orig == recheck, 'KNOB LEAK: baseline no longer reproduces'
    print('baseline recheck: bit-identical (no knob leakage)', flush=True)

    summary = summarize(cells_by_variant)
    result = {
        'meta': {'leagues': leagues, 'n_variants': len(variants),
                 'opponent_counter': args.opponent_counter,
                 'lethal_dive_fix': args.lethal_dive_fix,
                 'focal': 'Cramorant PECK/DIVE+FLY, '
                          + (f'IVs {args.focal_ivs}' if args.focal_ivs
                             else 'PvPoke default IVs'),
                 'elapsed_s': round(time.time() - t0, 1)},
        'summary': summary,
        'cells': [c for cells in cells_by_variant.values() for c in cells],
    }
    out_path.write_text(json.dumps(result, indent=1))
    print(f'\nwrote {out_path}')
    ranked = sorted(summary.items(),
                    key=lambda kv: -kv[1]['net_vs_baseline'])
    print(f"{'variant':34s} {'W':>4s} {'D':>3s} {'L':>4s} {'net':>5s}")
    for name, s in ranked[:15]:
        print(f"{name:34s} {s['wins']:4d} {s['draws']:3d} {s['losses']:4d} "
              f"{s['net_vs_baseline']:+5d}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
