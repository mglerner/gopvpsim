#!/usr/bin/env python
"""Extract per-IV meta performance for one joint-IV pair's FOCAL from its
shipped dive replay blob.

Config-driven generalization of scripts/thievul_licki_meta.py (S1 of
docs/joint_iv_reuse_plan.md): focal species, league, shadow flag, the
moveset arms, the blob path and the output path all come from a
pairs/*.toml file (see scripts/joint_iv_config.py for the schema). The
Thievul-vs-Lickitung config reproduces the shipped
userdata/thievul_licki/meta_wins.npz array-exactly.

The focal's dive blob (``[pair].replay_blob``) already holds a full
4096-IV x pool x scenario score cube per moveset and per (opponent-IV
mode, bait mode); this script counts wins out of that cube so the IV
robustness page can plot "beats the pair opponent" against "still
performs vs the rest of the meta". Note the payload depends only on
(focal, league, blob) -- NOT on the pair's opponent -- which is why the
page builder keeps a fallback meta_wins.npz directory.

Blob score layout (deep_dive_lib.sweep.iv_sweep -> canonical_scores):
    flat[iv_idx * nS * nO + si * nO + oi] = round(pvpoke_score(focal))
with ``iv_idx`` in compute_iv_metadata CANONICAL a=0..15, d=0..15,
s=0..15 order (NOT iv_rank order). Everything written here is converted
to ``gopvpsim.pokemon.iv_rank(focal, league=league)`` order (row i =
stat-product rank i+1), matching the joint-grid bake's axis convention.

Win convention: score > 500 strict (500 = tie, counted as a loss for the
win count). ``[meta.oracle]`` pins that against the pair's shipped dive
claim; see --verify.

Usage:
    python scripts/joint_iv_meta.py pairs/<pair>.toml
    python scripts/joint_iv_meta.py pairs/<pair>.toml --verify
    python scripts/joint_iv_meta.py pairs/<pair>.toml --out /tmp/x.npz
"""
import argparse
import functools
import json
import os
import pathlib
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deep_dive  # noqa: E402
from deep_dive_lib.opponents import (  # noqa: E402
    parse_opponent_spec, resolve_opp_ivs, variant_ivs,
)
from deep_dive_lib.shields import EVEN_SHIELDS  # noqa: E402
from deep_dive_lib.sweep import BattleSide, build_battle_pair  # noqa: E402
from deep_dive_rendering import parse_mode  # noqa: E402
from joint_iv_config import load_pair  # noqa: E402

from gopvpsim.battle import pvpoke_dp, simulate  # noqa: E402
from gopvpsim.moves import get_moves, parse_types  # noqa: E402
from gopvpsim.pokemon import (  # noqa: E402
    LEAGUE_CAPS, Pokemon, get_pokemon_entry, iv_rank,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Config -> moveset arms
# ---------------------------------------------------------------------------

def moveset_arms(cfg):
    """[(arm, fast, charged_tuple)] -- the config's unique moveset arms in
    grid order.

    An "arm" is a grid label minus its trailing ``_bait``/``_nobait``; that
    string is the npz key infix the page builder recovers by splitting the
    manifest grid label ('nsiw_bait' -> 'nsiw' + 'bait'), so it must be
    derived here exactly the way the bake names its grids.
    """
    arms, seen = [], {}
    for g in cfg.grids:
        arm = g.label
        for suf in ('_nobait', '_bait'):
            if arm.endswith(suf):
                arm = arm[:-len(suf)]
                break
        ms = (g.focal_fast, tuple(g.focal_charged))
        if arm in seen:
            assert seen[arm] == ms, (arm, seen[arm], ms)
            continue
        seen[arm] = ms
        arms.append((arm, g.focal_fast, tuple(g.focal_charged)))
    return arms


def parse_blob_label(label):
    """'SUCKER_PUNCH / ICY_WIND, PLAY_ROUGH' -> ('SUCKER_PUNCH',
    ('ICY_WIND', 'PLAY_ROUGH'))."""
    fast, _, charged = label.partition(' / ')
    return fast.strip(), tuple(c.strip() for c in charged.split(','))


def match_blob_moveset(labels, fast, charged):
    """Index of the one blob moveset matching (fast, SET of charged ids).

    Matching is order-INDEPENDENT on the charged moves because the blob's
    order is the dive's, not the config's (Thievul nsiw: blob
    'ICY_WIND, NIGHT_SLASH' vs the config's ['NIGHT_SLASH', 'ICY_WIND']).
    verify()'s [b2] check proves the order really is sim-irrelevant.
    """
    hits = []
    for i, lab in enumerate(labels):
        bfast, bcharged = parse_blob_label(lab)
        if bfast == fast and frozenset(bcharged) == frozenset(charged):
            hits.append(i)
    if not hits:
        # The dive simmed different movesets than this pair config (the
        # Quagsire (Shadow) dive has no Aqua Tail + Stone Edge cube,
        # 2026-08-19). A DISTINCT exit code so joint_iv_run can skip the
        # meta step honestly (the page renders those panels absent)
        # instead of treating it as a pipeline failure.
        print(f'NO-MATCHING-BLOB-MOVESET: the replay blob has no '
              f'{fast} / {sorted(charged)} cube (blob movesets: {labels}); '
              'meta-wins cannot be extracted for this pair from this dive.')
        sys.exit(3)
    assert len(hits) == 1, (fast, charged, hits, labels)
    return hits[0]


def find_mirror(cfg, names):
    """Index of the focal's own base entry in the dive pool, or None.

    Matched through parse_opponent_spec so a pool that carries the focal
    only as a shadow/atk-weighted/moveset variant does not masquerade as
    the mirror (and so a pool without the focal at all is handled instead
    of raising).
    """
    hits = []
    for i, name in enumerate(names):
        clean, variant, shadow = parse_opponent_spec(name)
        if variant is None and clean == cfg.focal and shadow == cfg.focal_shadow:
            hits.append(i)
    assert len(hits) <= 1, (cfg.focal, hits)
    return hits[0] if hits else None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def load_state(blob):
    return deep_dive.load_replay_state(str(blob))


def canonical_ivs(state):
    """[(a,d,s)] in the blob's canonical iv_meta order (from the blob itself)."""
    return [(t[0], t[1], t[2]) for t in state['moveset_data'][0]['meta']]


def rank_perm(cfg, state):
    """perm[r] = canonical index of iv_rank row r (rank r+1)."""
    canon = canonical_ivs(state)
    pos = {iv: i for i, iv in enumerate(canon)}
    ranked = iv_rank(cfg.focal, league=cfg.league, shadow=cfg.focal_shadow)
    perm = np.array([pos[(r['atk_iv'], r['def_iv'], r['sta_iv'])] for r in ranked],
                    dtype=np.int32)
    assert len(perm) == len(canon) == 4096
    assert len(set(perm.tolist())) == 4096, 'perm is not a permutation'
    return perm, ranked


def key_name(prefix, ms, oppiv, bait, sc):
    return f'{prefix}__{ms}__{oppiv}__{bait}__{sc[0]}-{sc[1]}'


def pool_file_from_state(state):
    """The dive's --opponents-file, recovered from the blob's own command
    line (the [meta] pool_file key overrides this)."""
    toks = state['cli_args_str'].split()
    if '--opponents-file' in toks:
        i = toks.index('--opponents-file')
        if i + 1 < len(toks):
            return toks[i + 1]
    return 'unknown'


def extract(cfg, state):
    """Return (arrays dict, provenance dict)."""
    meta_cfg = cfg.section('meta')
    scenarios = state['shield_scenarios']
    names = state['opponent_names']
    nS, nO = len(scenarios), len(names)
    perm, ranked = rank_perm(cfg, state)
    mirror_idx = find_mirror(cfg, names)

    labels = [m['label'] for m in state['moveset_data']]
    arms = moveset_arms(cfg)
    ms_idx = {arm: match_blob_moveset(labels, fast, charged)
              for arm, fast, charged in arms}

    out = {}
    modes = []
    for mode in state['opp_iv_modes']:
        oppiv, bait = parse_mode(mode)
        modes.append((mode, oppiv, bait))

    for short, mi in ms_idx.items():
        md = state['moveset_data'][mi]
        # best-buddy is a no-op for this focal/league (blob's best_buddy.noop);
        # assert the L51 cube is identical rather than silently picking one.
        # A focal where this fires is a real finding, not a kit bug.
        for mode, _, _ in modes:
            assert md['scores'][mode] == md['scores_l51'][mode], (short, mode)
        for mode, oppiv, bait in modes:
            flat = np.asarray(md['scores'][mode], dtype=np.int32)
            assert flat.size == 4096 * nS * nO, flat.size
            cube = flat.reshape(4096, nS, nO)          # canonical IV order
            cube = cube[perm]                          # -> iv_rank order
            wins = (cube > 500).sum(axis=2)            # (4096, nS)
            ties = (cube == 500).sum(axis=2)
            for si, sc in enumerate(scenarios):
                out[key_name('wins', short, oppiv, bait, sc)] = \
                    wins[:, si].astype(np.int16)
                out[key_name('ties', short, oppiv, bait, sc)] = \
                    ties[:, si].astype(np.int16)
            if mirror_idx is not None:
                out[f'mirror_win__{short}__{oppiv}__{bait}'] = \
                    (cube[:, :, mirror_idx] > 500).astype(np.int8)  # (4096, nS)

    out['pool_n'] = np.array(nO, dtype=np.int32)
    out['scenarios'] = np.array(scenarios, dtype=np.int8)
    out['scenario_labels'] = np.array([f'{a}-{b}' for a, b in scenarios])
    out['opponent_names'] = np.array(names)
    out['iv_rank_ivs'] = np.array(
        [(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in ranked], dtype=np.int8)
    out['iv_rank_levels'] = np.array([r['level'] for r in ranked], dtype=np.float64)
    out['perm_rank_to_canonical'] = perm.astype(np.int32)

    n_base = sum(1 for n in names if parse_opponent_spec(n)[1] is None)
    if mirror_idx is None:
        mirror_note = (
            f'The pool does NOT contain the {cfg.focal} mirror, so no '
            'mirror_win__* arrays are written.')
    else:
        mirror_note = (
            f'The pool INCLUDES the {cfg.focal} mirror at index {mirror_idx}; '
            f'mirror_win__* (4096 x {nS}) lets a consumer subtract it.')
    bb = state.get('best_buddy') or {}

    prov = {
        'blob': str(cfg.replay_blob.relative_to(REPO)),
        'species': cfg.focal, 'league': cfg.league,
        'cli_args_str': state['cli_args_str'],
        'opponent_label': state['opponent_label'],
        'pool_file': meta_cfg.get('pool_file') or pool_file_from_state(state),
        'pool_n': nO,
        'mirror_opponent_index': mirror_idx,
        'movesets': {short: {'blob_index': ms_idx[short],
                             'blob_label': state['moveset_data'][ms_idx[short]]['label']}
                     for short, _, _ in arms},
        'opp_iv_modes': [{'blob_key': m, 'oppiv': o, 'bait': b} for m, o, b in modes],
        'scenario_labels': [f'{a}-{b}' for a, b in scenarios],
        'win_convention': (
            'win = round(pvpoke_score(focal)) > 500 strict; score == 500 is a '
            'tie and is NOT counted as a win (ties__* arrays carry the tie '
            'counts so the page can report W/L/T honestly). '
            + oracle_sentence(cfg, out, nO)),
        'iv_order': (
            'Blob cube is in deep_dive_lib.sweep.compute_iv_metadata canonical '
            'a=0..15,d=0..15,s=0..15 order (verified empirically against the '
            "blob's own moveset_data[0]['meta']). Every array here is "
            f"PERMUTED to gopvpsim.pokemon.iv_rank('{cfg.focal}', "
            f"league='{cfg.league}') order: row i = stat-product rank i+1. "
            'perm_rank_to_canonical[i] is the canonical index that produced '
            'row i.'),
        'level_note': (
            f'Blob ran --best-buddy auto; best_buddy.noop is {bool(bb.get("noop"))} '
            f'for {cfg.league.upper()[0]}L {cfg.focal}, and scores_l51 is '
            'asserted byte-identical to scores. Arrays come from scores.'),
        'opponent_note': (
            f'Opponents are the {nO}-entry dive pool ({n_base} mons + '
            f'{nO - n_base} counter-slayer variants) at the dive\'s own '
            'opponent IVs and movesets; the opponent always baits. '
            'oppiv=pvpoke is the landing page default (PvPoke\'s default '
            'IVs); oppiv=rank1 is the stat-product rank-1 opponent axis. '
            f'bait/nobait is the FOCAL bait policy. {mirror_note}'),
    }
    out['provenance'] = np.array(json.dumps(prov, indent=1))
    return out, prov


def oracle_sentence(cfg, arrays, nO):
    """The W/L/T convention sentence for the pair's shipped dive claim.

    Numbers come from the arrays we just built at the [meta.oracle] slot, so
    the prose and verify()'s [a] check read the same source. Empty when the
    pair has no oracle configured.
    """
    o = cfg.section('meta').get('oracle')
    if not o:
        return ('This pair has no [meta.oracle] slot, so no shipped W-L claim '
                'is restated here.')
    sc = tuple(o['scenario'])
    r = int(o.get('rank', 1)) - 1
    bait = 'bait' if o['bait'] else 'nobait'
    w = int(arrays[key_name('wins', o['arm'], o['oppiv'], bait, sc)][r])
    t = int(arrays[key_name('ties', o['arm'], o['oppiv'], bait, sc)][r])
    lo = nO - w - t
    return (f'The shipped dive claim "{w}W-{lo}L" at rank-{r + 1} IVs / '
            f'{sc[0]}-{sc[1]} / {o["arm"]} / {o["oppiv"]} opp IVs / {bait} '
            f'reports W and L separately and drops the {t} tie '
            f'({w}+{lo}+{t} = {nO}); under the worlds "ties are losses" '
            f'convention the same spread is {w}W-{lo + t}L. The WIN COUNT is '
            'identical either way, so wins__* is convention-free.')


# ---------------------------------------------------------------------------
# Verification: fresh re-sims straight from gopvpsim (no blob involvement)
# ---------------------------------------------------------------------------

def build_opp_cache(cfg, state, oppiv_mode):
    """Rebuild the dive's opponent list exactly as iv_sweep did."""
    fast_db, charged_db = get_moves()
    cache = []
    for name, (ofast, ocharged) in zip(state['opponent_names'],
                                       state['opp_movesets']):
        clean, variant, shadow = parse_opponent_spec(name)
        viv = variant_ivs(clean, variant, cfg.league, state['threshold_registry'])
        if viv is not None:
            oa, od, os_ = viv
        else:
            oa, od, os_ = resolve_opp_ivs(clean, cfg.league, shadow, oppiv_mode)
        p = Pokemon.at_best_level(clean, oa, od, os_, league=cfg.league,
                                  shadow=shadow, max_level=None)
        mon = get_pokemon_entry(clean)
        cache.append(BattleSide(
            clean, parse_types(mon), p.atk, p.def_, p.hp, shadow,
            dict(fast_db[ofast]), [dict(charged_db[c]) for c in ocharged],
            mon, (oa, od, os_), p.level, 0))
    return cache


def resim_row(cfg, state, fast_id, charged_ids, ivs, oppiv_mode, bait, sc):
    """Fresh-sim one focal spread vs the whole pool at one shield scenario.

    Returns the list of rounded focal scores (one per opponent).
    """
    fast_db, charged_db = get_moves()
    mon = get_pokemon_entry(cfg.focal)
    p = Pokemon.at_best_level(cfg.focal, *ivs, league=cfg.league,
                              shadow=cfg.focal_shadow)
    focal = BattleSide(cfg.focal, parse_types(mon), p.atk, p.def_, p.hp,
                       cfg.focal_shadow, dict(fast_db[fast_id]),
                       [dict(charged_db[c]) for c in charged_ids],
                       mon, tuple(ivs), p.level, 0)
    policy = pvpoke_dp if bait else functools.partial(pvpoke_dp, bait_shields=False)
    out = []
    for opp in build_opp_cache(cfg, state, oppiv_mode):
        bp0, bp1 = build_battle_pair(focal, opp, LEAGUE_CAPS[cfg.league])
        bp0.reset_for_battle(sc[0], opponent=bp1)
        bp1.reset_for_battle(sc[1], opponent=bp0)
        r = simulate(bp0, bp1, charged_policy_0=policy,
                     charged_policy_1=pvpoke_dp, mechanics='legacy')
        out.append(round(r.pvpoke_score(0)))
    return out


def spot_checks(cfg, arms, ranked):
    """[(arm, fast, charged, ivs, oppiv, bait, sc)] to fresh-re-sim.

    From the optional [[meta.verify_spreads]] list; with none configured
    every arm still gets its rank-1 spread probed at pvpoke/bait/1-1, so
    the blob-vs-engine cross-check never disappears silently.
    """
    ms = {arm: (fast, charged) for arm, fast, charged in arms}
    spreads = cfg.section('meta').get('verify_spreads')
    if not spreads:
        r1 = ranked[0]
        ivs = (r1['atk_iv'], r1['def_iv'], r1['sta_iv'])
        return [(arm, fast, list(charged), ivs, 'pvpoke', True, (1, 1))
                for arm, fast, charged in arms]
    checks = []
    for s in spreads:
        fast, charged = ms[s['arm']]
        checks.append((s['arm'], fast, list(charged), tuple(s['ivs']),
                       s['oppiv'], bool(s['bait']), tuple(s['scenario'])))
    return checks


def verify(cfg, state, arrays):
    ok = True
    _, ranked = rank_perm(cfg, state)
    rank_of = {(r['atk_iv'], r['def_iv'], r['sta_iv']): i for i, r in enumerate(ranked)}
    nO = len(state['opponent_names'])
    arms = moveset_arms(cfg)
    labels = [m['label'] for m in state['moveset_data']]

    # (a) ORACLE -----------------------------------------------------------
    oracle = cfg.section('meta').get('oracle')
    if not oracle:
        print(f'[a] ORACLE: SKIPPED -- {cfg.path.name} has no [meta.oracle] '
              'table, so the npz is NOT tied to any shipped claim for this '
              'pair. Add one at the pair\'s first publish.')
    else:
        sc = tuple(oracle['scenario'])
        r1 = int(oracle.get('rank', 1)) - 1
        bait = 'bait' if oracle['bait'] else 'nobait'
        w = int(arrays[key_name('wins', oracle['arm'], oracle['oppiv'], bait, sc)][r1])
        t = int(arrays[key_name('ties', oracle['arm'], oracle['oppiv'], bait, sc)][r1])
        print(f'[a] ORACLE rank-{r1 + 1} '
              f'{tuple(int(x) for x in arrays["iv_rank_ivs"][r1])} '
              f'{oracle["arm"]}/{oracle["oppiv"]}/{bait}/{sc[0]}-{sc[1]}: '
              f'{w}W {nO - w - t}L {t}T  (want {oracle["want_w"]}W '
              f'{oracle["want_l"]}L {oracle["want_t"]}T)')
        if not (w == oracle['want_w'] and nO - w - t == oracle['want_l']
                and t == oracle['want_t']):
            ok = False
            print('[a] FAIL')

    # (b) fresh re-sim spot checks ----------------------------------------
    for ms, fast, charged, ivs, oppiv, bait, sc in spot_checks(cfg, arms, ranked):
        scores = resim_row(cfg, state, fast, charged, ivs, oppiv, bait, sc)
        w_sim = sum(1 for s in scores if s > 500)
        t_sim = sum(1 for s in scores if s == 500)
        bait_lbl = 'bait' if bait else 'nobait'
        k = key_name('wins', ms, oppiv, bait_lbl, sc)
        kt = key_name('ties', ms, oppiv, bait_lbl, sc)
        r = rank_of[ivs]
        w_ext = int(arrays[k][r]); t_ext = int(arrays[kt][r])
        good = (w_sim == w_ext and t_sim == t_ext)
        ok &= good
        print(f'[b] {ms} {ivs} rank{r+1} {oppiv}/{bait_lbl} {sc[0]}-{sc[1]}: '
              f'resim {w_sim}W/{t_sim}T vs extracted {w_ext}W/{t_ext}T '
              f'-> {"OK" if good else "MISMATCH"}')

    # (b2) charged-move ORDER independence: the blob's order for an arm vs
    #      the config/bake's order for the same arm. This is what licenses
    #      match_blob_moveset()'s set-based matching.
    r1_ivs = (ranked[0]['atk_iv'], ranked[0]['def_iv'], ranked[0]['sta_iv'])
    flipped = [(arm, fast, charged) for arm, fast, charged in arms
               if parse_blob_label(labels[match_blob_moveset(labels, fast, charged)])[1]
               != charged]
    if not flipped:
        print('[b2] charged-move order independence: SKIPPED -- the blob lists '
              'every arm in the config\'s own charged order, so there is no '
              'order delta to test.')
    else:
        arm, fast, charged = flipped[0]
        blob_charged = parse_blob_label(
            labels[match_blob_moveset(labels, fast, charged)])[1]
        a = resim_row(cfg, state, fast, list(blob_charged), r1_ivs,
                      'pvpoke', True, (1, 1))
        b = resim_row(cfg, state, fast, list(charged), r1_ivs,
                      'pvpoke', True, (1, 1))
        same = (a == b)
        ok &= same
        print(f'[b2] charged-move order independence ({arm}, rank-1, 1-1): '
              f'{"identical" if same else "DIFFERS"} '
              f'({sum(1 for x, y in zip(a, b) if x != y)} of {len(a)} differ)')

    # (c) distribution -----------------------------------------------------
    print('[c] win-count distribution over 4096 spreads (of '
          f'{nO} pool matchups):')
    modes = [parse_mode(m) for m in state['opp_iv_modes']]
    for arm, _, _ in arms:
        for oppiv, bait in modes:
            for sc in EVEN_SHIELDS:
                v = arrays[key_name('wins', arm, oppiv, bait, sc)]
                print(f'    {arm:5s} {oppiv:6s} {bait:6s} {sc[0]}-{sc[1]}: '
                      f'min={v.min():3d} p25={np.percentile(v, 25):6.1f} '
                      f'med={np.median(v):6.1f} p75={np.percentile(v, 75):6.1f} '
                      f'max={v.max():3d} mean={v.mean():6.2f} '
                      f'rank1={int(v[0]):3d}')
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config', help='pairs/<pair>.toml')
    ap.add_argument('--out', help='override the output npz path '
                                  '(default: <data_dir>/meta_wins.npz)')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--no-write', action='store_true')
    args = ap.parse_args()

    cfg = load_pair(args.config)
    if cfg.replay_blob is None:
        raise SystemExit(f'ABORT: {cfg.path} has no [pair].replay_blob, so '
                         f'there is no dive cube to extract {cfg.focal} meta '
                         'wins from. Dive the focal first (or drop the meta '
                         'step for this pair -- the page renders the meta '
                         'panels in their honest-absent state).')
    if not cfg.replay_blob.exists():
        raise SystemExit(f'ABORT: replay blob {cfg.replay_blob} does not exist')
    out_path = pathlib.Path(args.out).resolve() if args.out \
        else cfg.data_dir / 'meta_wins.npz'

    state = load_state(cfg.replay_blob)
    arrays, prov = extract(cfg, state)
    print(f'extracted {len(arrays)} arrays; '
          f'{sum(1 for k in arrays if k.startswith("wins__"))} wins__ keys')

    ok = True
    if args.verify:
        ok = verify(cfg, state, arrays)
        print(f'VERIFY: {"PASS" if ok else "FAIL"}')

    if args.no_write:
        return 0 if ok else 1
    if not ok:
        print(f'refusing to write {out_path.name}: verification failed')
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.parent / (out_path.name + '.tmp.npz')
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, out_path)
    print(f'wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
