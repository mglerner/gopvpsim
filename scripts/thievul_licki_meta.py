#!/usr/bin/env python
"""A1: extract per-IV meta performance for Thievul from the shipped dive blob.

One-off local analysis for the 2026-08-16 Thievul CD "IV tech" question
(see userdata/thievul_licki/DESIGN.md). The shipped GL dive
(userdata/replay/20260815_183454_Thievul_great.replay.pkl.gz) already
holds a full 4096-IV x 88-opponent x 9-scenario score cube per moveset
and per (opponent-IV mode, bait mode); this script counts wins out of
that cube so the IV-robustness page can plot "beats Lickitung" against
"still performs vs the rest of the meta".

Blob score layout (deep_dive_lib.sweep.iv_sweep -> canonical_scores):
    flat[iv_idx * nS * nO + si * nO + oi] = round(pvpoke_score(focal))
with ``iv_idx`` in compute_iv_metadata CANONICAL a=0..15, d=0..15,
s=0..15 order (NOT iv_rank order). Everything written here is converted
to ``gopvpsim.pokemon.iv_rank('Thievul', league='great')`` order (row i =
stat-product rank i+1), matching the joint-grid bake's axis convention.

Win convention: score > 500 strict (500 = tie, counted as a loss for the
win count). This reproduces the shipped landing-page claim exactly; see
--verify.

Usage:
    python scripts/thievul_licki_meta.py            # extract + write npz
    python scripts/thievul_licki_meta.py --verify   # + fresh re-sim checks
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

from gopvpsim.battle import pvpoke_dp, simulate  # noqa: E402
from gopvpsim.moves import get_moves, parse_types  # noqa: E402
from gopvpsim.pokemon import (  # noqa: E402
    LEAGUE_CAPS, Pokemon, get_pokemon_entry, iv_rank,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
BLOB = REPO / 'userdata' / 'replay' / '20260815_183454_Thievul_great.replay.pkl.gz'
OUT = REPO / 'userdata' / 'thievul_licki' / 'meta_wins.npz'

SPECIES = 'Thievul'
LEAGUE = 'great'

# Moveset short labels -> the exact blob label they must match. The blob's
# charged-move ORDER differs from scripts/thievul_licki_bake.py's nsiw grid
# ('ICY_WIND, NIGHT_SLASH' vs ['NIGHT_SLASH', 'ICY_WIND']); --verify proves
# the order is sim-irrelevant.
WANT_MOVESETS = [
    ('iwpr', 'SUCKER_PUNCH / ICY_WIND, PLAY_ROUGH'),
    ('nsiw', 'SUCKER_PUNCH / ICY_WIND, NIGHT_SLASH'),
]


def load_state():
    return deep_dive.load_replay_state(str(BLOB))


def canonical_ivs(state):
    """[(a,d,s)] in the blob's canonical iv_meta order (from the blob itself)."""
    return [(t[0], t[1], t[2]) for t in state['moveset_data'][0]['meta']]


def rank_perm(state):
    """perm[r] = canonical index of iv_rank row r (rank r+1)."""
    canon = canonical_ivs(state)
    pos = {iv: i for i, iv in enumerate(canon)}
    ranked = iv_rank(SPECIES, league=LEAGUE)
    perm = np.array([pos[(r['atk_iv'], r['def_iv'], r['sta_iv'])] for r in ranked],
                    dtype=np.int32)
    assert len(perm) == len(canon) == 4096
    assert len(set(perm.tolist())) == 4096, 'perm is not a permutation'
    return perm, ranked


def key_name(prefix, ms, oppiv, bait, sc):
    return f'{prefix}__{ms}__{oppiv}__{bait}__{sc[0]}-{sc[1]}'


def extract(state):
    """Return (arrays dict, provenance dict)."""
    scenarios = state['shield_scenarios']
    names = state['opponent_names']
    nS, nO = len(scenarios), len(names)
    perm, ranked = rank_perm(state)
    mirror_idx = names.index(SPECIES)

    labels = [m['label'] for m in state['moveset_data']]
    ms_idx = {}
    for short, want in WANT_MOVESETS:
        assert want in labels, (want, labels)
        ms_idx[short] = labels.index(want)

    out = {}
    modes = []
    for mode in state['opp_iv_modes']:
        oppiv, bait = parse_mode(mode)
        modes.append((mode, oppiv, bait))

    for short, mi in ms_idx.items():
        md = state['moveset_data'][mi]
        # best-buddy is a no-op for GL Thievul (blob's best_buddy.noop);
        # assert the L51 cube is identical rather than silently picking one.
        for mode, _, _ in modes:
            assert md['scores'][mode] == md['scores_l51'][mode], (short, mode)
        for mode, oppiv, bait in modes:
            flat = np.asarray(md['scores'][mode], dtype=np.int32)
            assert flat.size == 4096 * nS * nO, flat.size
            cube = flat.reshape(4096, nS, nO)          # canonical IV order
            cube = cube[perm]                          # -> iv_rank order
            wins = (cube > 500).sum(axis=2)            # (4096, nS)
            ties = (cube == 500).sum(axis=2)
            mirror_win = (cube[:, :, mirror_idx] > 500)
            for si, sc in enumerate(scenarios):
                out[key_name('wins', short, oppiv, bait, sc)] = \
                    wins[:, si].astype(np.int16)
                out[key_name('ties', short, oppiv, bait, sc)] = \
                    ties[:, si].astype(np.int16)
            out[f'mirror_win__{short}__{oppiv}__{bait}'] = \
                mirror_win.astype(np.int8)             # (4096, nS)

    out['pool_n'] = np.array(nO, dtype=np.int32)
    out['scenarios'] = np.array(scenarios, dtype=np.int8)
    out['scenario_labels'] = np.array([f'{a}-{b}' for a, b in scenarios])
    out['opponent_names'] = np.array(names)
    out['iv_rank_ivs'] = np.array(
        [(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in ranked], dtype=np.int8)
    out['iv_rank_levels'] = np.array([r['level'] for r in ranked], dtype=np.float64)
    out['perm_rank_to_canonical'] = perm.astype(np.int32)

    prov = {
        'blob': str(BLOB.relative_to(REPO)),
        'species': SPECIES, 'league': LEAGUE,
        'cli_args_str': state['cli_args_str'],
        'opponent_label': state['opponent_label'],
        'pool_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'pool_n': nO,
        'mirror_opponent_index': mirror_idx,
        'movesets': {short: {'blob_index': ms_idx[short],
                             'blob_label': state['moveset_data'][ms_idx[short]]['label']}
                     for short, _ in WANT_MOVESETS},
        'opp_iv_modes': [{'blob_key': m, 'oppiv': o, 'bait': b} for m, o, b in modes],
        'scenario_labels': [f'{a}-{b}' for a, b in scenarios],
        'win_convention': (
            'win = round(pvpoke_score(focal)) > 500 strict; score == 500 is a '
            'tie and is NOT counted as a win (ties__* arrays carry the tie '
            'counts so the page can report W/L/T honestly). The shipped dive '
            'claim "62W-25L" at rank-1 IVs / 1-1 / iwpr / pvpoke opp IVs / '
            'bait reports W and L separately and drops the single tie '
            '(62+25+1 = 88); under the worlds "ties are losses" convention '
            'the same spread is 62W-26L. The WIN COUNT is identical either '
            'way, so wins__* is convention-free.'),
        'iv_order': (
            'Blob cube is in deep_dive_lib.sweep.compute_iv_metadata canonical '
            'a=0..15,d=0..15,s=0..15 order (verified empirically against the '
            "blob's own moveset_data[0]['meta']). Every array here is "
            "PERMUTED to gopvpsim.pokemon.iv_rank('Thievul', league='great') "
            'order: row i = stat-product rank i+1. perm_rank_to_canonical[i] '
            'is the canonical index that produced row i.'),
        'level_note': (
            'Blob ran --best-buddy auto; best_buddy.noop is True for GL '
            'Thievul (every IV is CP-capped below L51), and scores_l51 is '
            'asserted byte-identical to scores. Arrays come from scores.'),
        'opponent_note': (
            'Opponents are the 88-entry dive pool (79 mons + counter-slayer '
            'variants) at the dive\'s own opponent IVs and movesets; the '
            'opponent always baits. oppiv=pvpoke is the landing page default '
            "(PvPoke's default IVs); oppiv=rank1 is the stat-product rank-1 "
            'opponent axis. bait/nobait is the FOCAL bait policy. The pool '
            f'INCLUDES the Thievul mirror at index {mirror_idx}; mirror_win__* '
            '(4096 x 9) lets a consumer subtract it.'),
    }
    out['provenance'] = np.array(json.dumps(prov, indent=1))
    return out, prov


# ---------------------------------------------------------------------------
# Verification: fresh re-sims straight from gopvpsim (no blob involvement)
# ---------------------------------------------------------------------------

def build_opp_cache(state, oppiv_mode):
    """Rebuild the dive's opponent list exactly as iv_sweep did."""
    fast_db, charged_db = get_moves()
    cache = []
    for name, (ofast, ocharged) in zip(state['opponent_names'],
                                       state['opp_movesets']):
        clean, variant, shadow = parse_opponent_spec(name)
        viv = variant_ivs(clean, variant, LEAGUE, state['threshold_registry'])
        if viv is not None:
            oa, od, os_ = viv
        else:
            oa, od, os_ = resolve_opp_ivs(clean, LEAGUE, shadow, oppiv_mode)
        p = Pokemon.at_best_level(clean, oa, od, os_, league=LEAGUE,
                                  shadow=shadow, max_level=None)
        mon = get_pokemon_entry(clean)
        cache.append(BattleSide(
            clean, parse_types(mon), p.atk, p.def_, p.hp, shadow,
            dict(fast_db[ofast]), [dict(charged_db[c]) for c in ocharged],
            mon, (oa, od, os_), p.level, 0))
    return cache


def resim_row(state, fast_id, charged_ids, ivs, oppiv_mode, bait, sc):
    """Fresh-sim one focal spread vs the whole pool at one shield scenario.

    Returns the list of rounded focal scores (one per opponent).
    """
    fast_db, charged_db = get_moves()
    mon = get_pokemon_entry(SPECIES)
    p = Pokemon.at_best_level(SPECIES, *ivs, league=LEAGUE, shadow=False)
    focal = BattleSide(SPECIES, parse_types(mon), p.atk, p.def_, p.hp, False,
                       dict(fast_db[fast_id]),
                       [dict(charged_db[c]) for c in charged_ids],
                       mon, tuple(ivs), p.level, 0)
    policy = pvpoke_dp if bait else functools.partial(pvpoke_dp, bait_shields=False)
    out = []
    for opp in build_opp_cache(state, oppiv_mode):
        bp0, bp1 = build_battle_pair(focal, opp, LEAGUE_CAPS[LEAGUE])
        bp0.reset_for_battle(sc[0], opponent=bp1)
        bp1.reset_for_battle(sc[1], opponent=bp0)
        r = simulate(bp0, bp1, charged_policy_0=policy,
                     charged_policy_1=pvpoke_dp, mechanics='legacy')
        out.append(round(r.pvpoke_score(0)))
    return out


def verify(state, arrays):
    ok = True
    scenarios = state['shield_scenarios']
    perm, ranked = rank_perm(state)
    rank_of = {(r['atk_iv'], r['def_iv'], r['sta_iv']): i for i, r in enumerate(ranked)}
    nO = len(state['opponent_names'])

    # (a) ORACLE -----------------------------------------------------------
    r1 = 0
    w = int(arrays['wins__iwpr__pvpoke__bait__1-1'][r1])
    t = int(arrays['ties__iwpr__pvpoke__bait__1-1'][r1])
    print(f'[a] ORACLE rank-1 {tuple(int(x) for x in arrays["iv_rank_ivs"][0])} '
          f'iwpr/pvpoke/bait/1-1: {w}W {nO - w - t}L {t}T  (want 62W 25L 1T)')
    if not (w == 62 and nO - w - t == 25 and t == 1):
        ok = False
        print('[a] FAIL')

    # (b) fresh re-sim spot checks ----------------------------------------
    checks = [
        ('iwpr', 'SUCKER_PUNCH', ['ICY_WIND', 'PLAY_ROUGH'], (6, 15, 5),
         'pvpoke', True, (1, 1)),
        ('iwpr', 'SUCKER_PUNCH', ['ICY_WIND', 'PLAY_ROUGH'], (6, 15, 5),
         'pvpoke', False, (0, 0)),
        ('nsiw', 'SUCKER_PUNCH', ['ICY_WIND', 'NIGHT_SLASH'], (15, 15, 15),
         'rank1', True, (1, 1)),
        ('nsiw', 'SUCKER_PUNCH', ['ICY_WIND', 'NIGHT_SLASH'], (15, 15, 15),
         'rank1', True, (2, 2)),
    ]
    for ms, fast, charged, ivs, oppiv, bait, sc in checks:
        scores = resim_row(state, fast, charged, ivs, oppiv, bait, sc)
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

    # (b2) charged-move ORDER independence (blob 'ICY_WIND, NIGHT_SLASH' vs
    #      the bake's ['NIGHT_SLASH', 'ICY_WIND'])
    a = resim_row(state, 'SUCKER_PUNCH', ['ICY_WIND', 'NIGHT_SLASH'],
                  (0, 15, 11), 'pvpoke', True, (1, 1))
    b = resim_row(state, 'SUCKER_PUNCH', ['NIGHT_SLASH', 'ICY_WIND'],
                  (0, 15, 11), 'pvpoke', True, (1, 1))
    same = (a == b)
    ok &= same
    print(f'[b2] charged-move order independence (nsiw, rank-1, 1-1): '
          f'{"identical" if same else "DIFFERS"} '
          f'({sum(1 for x, y in zip(a, b) if x != y)} of {len(a)} differ)')

    # (c) distribution -----------------------------------------------------
    print('[c] win-count distribution over 4096 spreads (of '
          f'{nO} pool matchups):')
    for ms, _ in WANT_MOVESETS:
        for oppiv in ('pvpoke', 'rank1'):
            for bait in ('bait', 'nobait'):
                for sc in EVEN_SHIELDS:
                    v = arrays[key_name('wins', ms, oppiv, bait, sc)]
                    print(f'    {ms:5s} {oppiv:6s} {bait:6s} {sc[0]}-{sc[1]}: '
                          f'min={v.min():3d} p25={np.percentile(v, 25):6.1f} '
                          f'med={np.median(v):6.1f} p75={np.percentile(v, 75):6.1f} '
                          f'max={v.max():3d} mean={v.mean():6.2f} '
                          f'rank1={int(v[0]):3d}')
    _ = scenarios
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--no-write', action='store_true')
    args = ap.parse_args()

    state = load_state()
    arrays, prov = extract(state)
    print(f'extracted {len(arrays)} arrays; '
          f'{sum(1 for k in arrays if k.startswith("wins__"))} wins__ keys')

    ok = True
    if args.verify:
        ok = verify(state, arrays)
        print(f'VERIFY: {"PASS" if ok else "FAIL"}')

    if args.no_write:
        return 0 if ok else 1
    if not ok:
        print('refusing to write meta_wins.npz: verification failed')
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.npz.tmp.npz')
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, OUT)
    print(f'wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
