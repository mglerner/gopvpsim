"""Opponent-IV robustness planes (Worlds 2026 session-2 split).

Extracted from ``scripts/deep_dive.py`` so the Worlds robustness driver
(``scripts/worlds_bake.py``) can pool-parallelize the bool-plane core
without importing the 5k-line dive orchestrator. ``deep_dive.py`` keeps
alias shims for every moved name, so existing importers and tests keep
working unchanged.

Layering (matches the deep_dive_lib DAG -- ``opponents -> sweep ->
render``; this module sits beside ``sweep`` and imports only it):
``robustness -> sweep``, plus the top-level ``deep_dive_signature``
module. Never import ``deep_dive`` here -- a spawn-mode pool child must
be able to import this module on its own (the same invariant
``deep_dive_lib/__init__.py`` documents for ``sweep``).

The plane core (``opp_plane``) returns per-(opponent IV, scenario)
outcome planes; ``opp_iv_robustness`` is the historical (wins, total)
wrapper whose semantics are pinned by tests/test_deep_dive_card.py.
``plane_task_worker`` is the module-level pool entry point the Worlds
bake driver maps tasks over (module-level so spawn-mode pickling
resolves it by qualified name).
"""
import functools
import os
import sys

import numpy as np

from gopvpsim.pokemon import (
    Pokemon, find_pokemon_entry, iv_rank, LEAGUE_CAPS,
)
from gopvpsim.data import load_gamemaster, parse_types
from gopvpsim.moves import get_moves
from gopvpsim.battle import simulate, pvpoke_dp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_dive_lib.sweep import make_battle_pokemon, group_ivs_by_stat_profile

_FORM_CHANGE_SPECIES_CACHE: dict = {}


def _species_has_form_change(species_name):
    """True if the species participates in a formChange (either directly or
    as a sibling form), so its effective stats are NOT a safe dedup key (the
    alt form's stats are non-linear in raw IVs + level). Cached; defaults
    False on lookup miss.

    A form-changing species is detected two ways: its own gamemaster entry
    declares a formChange, OR its speciesId is the alternativeFormId of some
    other form's formChange. The second case covers sibling forms whose pool
    name lacks the formChange key (e.g. 'Morpeko (Hangry)', reachable only via
    'Morpeko (Full Belly)'.formChange.alternativeFormId) -- they are now
    detected rather than silently misgrouped. For Morpeko specifically the two
    forms share identical baseStats so dedup was already exact, but resolving
    through the sibling link makes this robust to a FUTURE stat-divergent
    toggle/set species pool-named by a key-lacking form."""
    if species_name in _FORM_CHANGE_SPECIES_CACHE:
        return _FORM_CHANGE_SPECIES_CACHE[species_name]
    mon = find_pokemon_entry(species_name)
    has = bool(mon and mon.get('formChange'))
    if mon and not has:
        sid = mon['speciesId']
        # The REVERSE direction (which entry points AT sid) is not a
        # speciesName lookup, so it stays a scan over gm['pokemon'].
        has = any((m.get('formChange') or {}).get('alternativeFormId') == sid
                  for m in load_gamemaster()['pokemon'])
    _FORM_CHANGE_SPECIES_CACHE[species_name] = has
    return has


def _opp_robustness_groups(focal_bp, focal_species, focal_fast, focal_charged,
                           focal_shadow, focal_ivs, opponent, opp_fast,
                           opp_charged, opp_shadow, league, ranked,
                           dedup='signature', focal_max_level=None):
    """Group the opponent's top-k IVs (``ranked``) into sets that fight
    bit-identical battles vs the fixed focal, so one representative sim
    covers each set. Returns a list of member-position lists (indexing
    ``ranked``).

    ``dedup``:
      'signature' - exact damage-signature dedup (deep_dive_signature) for
        fixed-form opponents; collapses the top-512 cohort hard. Form-change
        opponents always fall back to per-IV (their alt-form stats are
        non-linear in raw IVs+level).
      'profile'   - effective-stat dedup (the conservative original).
      'none'      - one group per IV (the no-dedup reference for tests).
    """
    n = len(ranked)
    if dedup == 'none' or _species_has_form_change(opponent):
        return [[i] for i in range(n)]
    if dedup == 'profile':
        groups, _ = group_ivs_by_stat_profile(ranked, per_iv=False)
        return list(groups.values())
    # signature dedup
    import deep_dive_signature as _sig
    league_cp = LEAGUE_CAPS[league]
    fast_db, charged_db = get_moves()
    # None-on-miss on purpose: a species absent from the gamemaster falls
    # back to the no-dedup grouping below instead of raising.
    opp_mon = find_pokemon_entry(opponent)
    focal_mon = find_pokemon_entry(focal_species)
    if opp_mon is None or focal_mon is None:
        return [[i] for i in range(n)]
    profile_list = [(None, r['atk'], r['def_'], r['hp'],
                     r['atk_iv'], r['def_iv'], r['sta_iv'], r['level'])
                    for r in ranked]
    swept = _sig.build_focal_side(
        opp_mon, parse_types(opp_mon), dict(fast_db[opp_fast]),
        [dict(charged_db[c]) for c in opp_charged],
        profile_list, league_cp, opp_shadow)
    focal_pk = Pokemon.at_best_level(focal_species, *focal_ivs,
                                     league=league, shadow=focal_shadow,
                                     max_level=focal_max_level)
    fixed = _sig.build_opp_side({
        'types': parse_types(focal_mon),
        'fm': dict(fast_db[focal_fast]),
        'cms': [dict(charged_db[c]) for c in focal_charged],
        'atk': focal_bp.atk, 'def_': focal_bp.def_,
        'mon': focal_mon, 'ivs': tuple(focal_ivs), 'level': focal_pk.level,
        'shadow': focal_shadow,
    }, league_cp)
    return [members for _rep, members in _sig.signature_groups(swept, fixed)]


def opp_plane(focal_species, focal_fast, focal_charged, focal_shadow,
              focal_ivs, opponent, opp_fast, opp_charged, opp_shadow,
              league, shield_scenarios, k=512, dedup='signature',
              mechanics='legacy', focal_max_level=None, focal_bait=True,
              cohort=None):
    """Bool-plane core: ONE fixed focal IV vs an opponent IV cohort.

    Sims one representative per dedup group (see _opp_robustness_groups)
    over every scenario in ``shield_scenarios`` and fans the outcome out
    to every group member. Returns ``(won, score, ranked, n_sims)``:

      won:    bool  (n_cohort, n_scenarios) -- focal pvpoke_score(0) > 500
              (500 = tie counts as a loss, matching the wrapper);
      score:  uint16 (n_cohort, n_scenarios) -- the raw focal
              pvpoke_score(0) in [0, 1000]. ``won`` is the AUTHORITY for
              win/loss; never re-derive it downstream (the > 500 strict
              inequality must not survive a lossy round-trip);
      ranked: the cohort's iv_rank entries, plane-row order;
      n_sims: actual simulate() calls (n_groups * n_scenarios -- fewer
              than won.size whenever dedup collapsed the cohort).

    or ``None`` if the opponent has no valid IVs.

    ``cohort``: optional list of indices into the FULL iv_rank list
    (Worlds cohorts include best-SP-per-atk-IV spreads that sit far
    beyond top-k). When given, ``k`` is ignored and plane rows follow
    ``cohort`` order. Default: top-``k`` by stat product.

    ``focal_bait``: focal-side shield-bait mode (the Worlds planes carry
    both). The opponent always baits (``pvpoke_dp`` default), matching
    the dive convention and the session-1 probe.

    ``shield_scenarios`` is materialized and indexed positionally, so
    duplicate scenarios stay distinct columns (and a generator argument
    can't be silently exhausted after the first group).
    """
    ranked_full = iv_rank(opponent, league=league, shadow=opp_shadow)
    if not ranked_full:
        return None
    if cohort is None:
        ranked = ranked_full[:k]
    else:
        ranked = [ranked_full[i] for i in cohort]
    scen = list(shield_scenarios)
    n = len(ranked)
    a0, d0, s0 = focal_ivs
    focal_bp = make_battle_pokemon(focal_species, focal_fast, focal_charged,
                                   league, 2, a0, d0, s0, shadow=focal_shadow,
                                   max_level=focal_max_level)
    groups = _opp_robustness_groups(
        focal_bp, focal_species, focal_fast, focal_charged, focal_shadow,
        focal_ivs, opponent, opp_fast, opp_charged, opp_shadow, league, ranked,
        dedup=dedup, focal_max_level=focal_max_level)
    if focal_bait:
        focal_policy = pvpoke_dp
    else:
        focal_policy = functools.partial(pvpoke_dp, bait_shields=False)
    won = np.zeros((n, len(scen)), dtype=bool)
    score = np.zeros((n, len(scen)), dtype=np.uint16)
    fill_count = np.zeros(n, dtype=np.int64)
    n_sims = 0
    for members in groups:
        rep = ranked[members[0]]
        opp_bp = make_battle_pokemon(
            opponent, opp_fast, opp_charged, league, 2,
            rep['atk_iv'], rep['def_iv'], rep['sta_iv'], shadow=opp_shadow)
        for si, (sf, so) in enumerate(scen):
            # Reset order is load-bearing: a form-changed mon's reset also
            # clears its opponent's damage cache (battle.py reset_for_battle).
            focal_bp.reset_for_battle(sf, opponent=opp_bp)
            opp_bp.reset_for_battle(so, opponent=focal_bp)
            res = simulate(focal_bp, opp_bp,
                           charged_policy_0=focal_policy,
                           charged_policy_1=pvpoke_dp,
                           mechanics=mechanics)
            sc = res.pvpoke_score(0)
            n_sims += 1
            for m in members:
                won[m, si] = sc > 500
                score[m, si] = sc
        fill_count[members] += 1
    # Partition guard: a dropped/duplicated position would leave garbage
    # False rows in the plane while the shape still LOOKS right -- fail loud
    # instead of shipping silent wrong data (the "does it survive" lens).
    if not (fill_count == 1).all():
        bad = np.flatnonzero(fill_count != 1)
        raise RuntimeError(
            f'opp_plane: dedup grouping is not a partition of the cohort '
            f'({len(bad)} positions covered {fill_count[bad].tolist()} '
            f'times, first at index {bad[0]})')
    return won, score, ranked, n_sims


def opp_iv_robustness(focal_species, focal_fast, focal_charged, focal_shadow,
                      focal_ivs, opponent, opp_fast, opp_charged, opp_shadow,
                      league, shield_scenarios, k=512, dedup='signature',
                      mechanics='legacy', focal_max_level=None):
    """Opponent-IV robustness for ONE fixed focal IV vs ONE opponent.

    Historical (wins, total) wrapper over ``opp_plane`` -- the "top-512
    ranks" robustness notion: do we beat this opponent regardless of
    which good IV it rolled? Returns ``(weighted_wins, weighted_total)``
    floats (caller sums across opponents and divides), or ``None`` if
    the opponent has no valid IVs. A win is focal ``pvpoke_score(0) >
    500`` (>500 = focal won; 500 = tie). ``total`` equals
    ``len(iv_rank(...)[:k]) * len(shield_scenarios)`` regardless of how
    ``dedup`` collapses the cohort (each group's outcome fans out to all
    members).

    Signature dedup is verified bit-identical to no-dedup on
    representative shadow + non-shadow cases
    (test_opp_iv_robustness_signature_dedup_is_exact): deep_dive_signature
    strips the shadow x1.2 from each side's CMP column, so its grouping
    matches the engine's unboosted cmp_atk (2026-06-13 fix) even for
    shadow-mismatched focal/opponent pairs.
    """
    res = opp_plane(focal_species, focal_fast, focal_charged, focal_shadow,
                    focal_ivs, opponent, opp_fast, opp_charged, opp_shadow,
                    league, shield_scenarios, k=k, dedup=dedup,
                    mechanics=mechanics, focal_max_level=focal_max_level,
                    focal_bait=True)
    if res is None:
        return None
    won = res[0]
    # Plain Python floats, matching the historical accumulator exactly
    # (type included -- the fraction feeds a shipped render surface).
    return float(won.sum()), float(won.size)


def plane_task_worker(task):
    """Pool entry point for the Worlds bake driver: one (pair, direction,
    bait) task -> stacked outcome planes over the task's focal spreads.

    ``task`` is a plain dict (picklable for spawn-mode pools):
      focal_species, focal_fast, focal_charged, focal_shadow,
      focal_spreads: [(atk_iv, def_iv, sta_iv), ...],
      opponent, opp_fast, opp_charged, opp_shadow,
      league, scenarios: [(sf, so), ...], cohort: [int, ...],
      bait: bool, and optionally dedup / mechanics.

    Returns ``(won, score, n_sims)`` with won bool and score uint16 of
    shape (n_spreads, n_cohort, n_scenarios). Never prints (worker
    processes must not emit bare stdout -- see CLAUDE.md debugging
    conventions); the driver logs from the parent.
    """
    wons, scores = [], []
    n_sims = 0
    for ivs in task['focal_spreads']:
        res = opp_plane(
            task['focal_species'], task['focal_fast'], task['focal_charged'],
            task['focal_shadow'], tuple(ivs),
            task['opponent'], task['opp_fast'], task['opp_charged'],
            task['opp_shadow'], task['league'], task['scenarios'],
            dedup=task.get('dedup', 'signature'),
            mechanics=task.get('mechanics', 'legacy'),
            focal_bait=task['bait'], cohort=task['cohort'])
        if res is None:
            raise RuntimeError(
                f"plane_task_worker: no valid IVs for {task['opponent']}")
        won, score, _ranked, sims = res
        wons.append(won)
        scores.append(score)
        n_sims += sims
    return np.stack(wons), np.stack(scores), n_sims
