#!/usr/bin/env python
"""Worlds 2026 Tier-2 RESULT-PRODUCING worker (hashed producer code).

Split out of worlds_tier2.py (2026-08-10) so the producer stamp
(``worlds_tier2.tier2_code_hash``) covers exactly the code that
determines grid CONTENTS -- this module plus the sim/dedup libs -- and
NOT the driver's orchestration loop. Lesson learned in-session: a
driver bugfix (head-of-line-blocking admission) must not invalidate
already-baked grids; over-broad stamping is the same mistake the sweep
cache's v7 gamemaster narrowing fixed. Storage-format changes are
covered separately by ``worlds_tier2.TIER2_SCHEMA`` (bump it manually
when the npz layout or its interpretation changes).

``tier2_task_worker`` moved here VERBATIM; module-level so spawn-mode
pools resolve it by qualified name.
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

from gopvpsim.pokemon import Pokemon, iv_rank, find_pokemon_entry, LEAGUE_CAPS
from gopvpsim.moves import get_moves, parse_types
from gopvpsim.battle import simulate, pvpoke_dp

import worlds_planes as wp
from deep_dive_lib.sweep import make_battle_pokemon
from deep_dive_lib.robustness import _species_has_form_change


def tier2_task_worker(task):
    """One (direction, bait) full grid. Module-level for spawn pickling;
    never prints (worker stdout convention).

    Structure: for each opponent cohort row (a FIXED opponent instance),
    signature-dedup the full 4096-spread focal side against it and sim
    one representative per group x 9 scenarios, fanning out to members.
    Mirrors robustness.opp_plane with the varying/fixed roles swapped.
    Form-change FOCAL species get no dedup (their alt-form stats are
    non-linear in raw IVs; same rule as _opp_robustness_groups) -- the
    plan's "expensive pair-family".
    """
    import functools
    import deep_dive_signature as _sig

    league = task['league']
    league_cp = LEAGUE_CAPS[league]
    fast_db, charged_db = get_moves()
    focal_ranked = iv_rank(task['focal_species'], league=league,
                           shadow=task['focal_shadow'])
    opp_ranked_full = iv_rank(task['opponent'], league=league,
                              shadow=task['opp_shadow'])
    opp_rows = [opp_ranked_full[i] for i in task['cohort']]
    scen = list(task['scenarios'])
    nf, no, ns = len(focal_ranked), len(opp_rows), len(scen)

    focal_mon = find_pokemon_entry(task['focal_species'])
    focal_types = parse_types(focal_mon)
    fm = dict(fast_db[task['focal_fast']])
    cms = [dict(charged_db[c]) for c in task['focal_charged']]
    dedup = not _species_has_form_change(task['focal_species'])
    if dedup:
        profile_list = [(None, r['atk'], r['def_'], r['hp'],
                         r['atk_iv'], r['def_iv'], r['sta_iv'], r['level'])
                        for r in focal_ranked]
        swept = _sig.build_focal_side(focal_mon, focal_types, fm, cms,
                                      profile_list, league_cp,
                                      task['focal_shadow'])
    opp_mon = find_pokemon_entry(task['opponent'])
    opp_fm = dict(fast_db[task['opp_fast']])
    opp_cms = [dict(charged_db[c]) for c in task['opp_charged']]

    if task['bait']:
        focal_policy = pvpoke_dp
    else:
        focal_policy = functools.partial(pvpoke_dp, bait_shields=False)

    won = np.zeros((nf, no, ns), dtype=bool)
    score = np.zeros((nf, no, ns), dtype=np.uint16)
    n_sims = 0
    # Focal BattlePokemon are rebuilt per (group rep, row); the opponent
    # instance is fixed per row.
    for oi, orow in enumerate(opp_rows):
        opp_bp = make_battle_pokemon(
            task['opponent'], task['opp_fast'], task['opp_charged'], league,
            2, orow['atk_iv'], orow['def_iv'], orow['sta_iv'],
            shadow=task['opp_shadow'])
        if dedup:
            opp_pk = Pokemon.at_best_level(
                task['opponent'], orow['atk_iv'], orow['def_iv'],
                orow['sta_iv'], league=league, shadow=task['opp_shadow'])
            fixed = _sig.build_opp_side({
                'types': parse_types(opp_mon), 'fm': opp_fm, 'cms': opp_cms,
                'atk': opp_bp.atk, 'def_': opp_bp.def_, 'mon': opp_mon,
                'ivs': (orow['atk_iv'], orow['def_iv'], orow['sta_iv']),
                'level': opp_pk.level, 'shadow': task['opp_shadow'],
            }, league_cp)
            groups = [m for _r, m in _sig.signature_groups(swept, fixed)]
        else:
            groups = [[i] for i in range(nf)]
        fill = np.zeros(nf, dtype=np.int64)
        for members in groups:
            rep = focal_ranked[members[0]]
            focal_bp = make_battle_pokemon(
                task['focal_species'], task['focal_fast'],
                task['focal_charged'], league, 2,
                rep['atk_iv'], rep['def_iv'], rep['sta_iv'],
                shadow=task['focal_shadow'])
            for si, (sf, so) in enumerate(scen):
                focal_bp.reset_for_battle(sf, opponent=opp_bp)
                opp_bp.reset_for_battle(so, opponent=focal_bp)
                res = simulate(focal_bp, opp_bp,
                               charged_policy_0=focal_policy,
                               charged_policy_1=pvpoke_dp,
                               mechanics=task.get('mechanics', 'legacy'))
                sc = res.pvpoke_score(0)
                n_sims += 1
                idx = np.asarray(members)
                won[idx, oi, si] = sc > 500
                score[idx, oi, si] = sc
            fill[members] += 1
        if not (fill == 1).all():
            bad = np.flatnonzero(fill != 1)
            raise RuntimeError(
                f'tier2 dedup not a partition at opp row {oi}: '
                f'{len(bad)} positions, first {bad[0]}')

    packed, shape = wp.pack_won(won)
    arrs = {
        'won_packed': packed,
        'won_shape': np.asarray(shape, dtype=np.int64),
        'score': score,
        'focal_ivs': np.asarray(
            [(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in focal_ranked],
            dtype=np.int64),
        'focal_levels': np.asarray([r['level'] for r in focal_ranked]),
        'opp_ivs': np.asarray(
            [(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in opp_rows],
            dtype=np.int64),
        'opp_levels': np.asarray([r['level'] for r in opp_rows]),
        'scenarios': np.asarray(scen, dtype=np.int64),
        'top512_mask': np.asarray(task['top512_mask'], dtype=bool),
        'atkband_mask': np.asarray(task['atkband_mask'], dtype=bool),
    }
    if int(arrs['score'].max(initial=0)) > 1000:
        raise RuntimeError('score out of pvpoke range')
    return arrs, n_sims
