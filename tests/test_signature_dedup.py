"""Damage-signature dedup tests (arc S3, 2026-06-10).

Pins the two claims deep_dive_signature.py rests on:

1. damage_vec is a bit-exact vectorized mirror of gopvpsim.moves.damage
   across real swept stats and every stat-stage multiplier.
2. Profiles grouped by signature_groups fight bit-identical battles:
   simming EVERY member of a group individually (not just the
   representative) produces identical score lists vs that opponent.
   Covered for a plain species (Tinkaton) and a form-change focal
   species (Aegislash (Shield), where the Blade-side stats depend on
   raw IVs + whole-level rounding).

The full-sweep equality check (signature-dedup vs per-profile across a
real opponent pool) lives in scripts/verify_signature_dedup.py.
"""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)

import deep_dive_signature as sig  # noqa: E402

from gopvpsim.battle import _stat_stage_mult  # noqa: E402
from gopvpsim.data import load_gamemaster, parse_types  # noqa: E402
from gopvpsim.moves import damage as scalar_damage, get_moves  # noqa: E402
from gopvpsim.pokemon import LEAGUE_CAPS, Pokemon  # noqa: E402

LEAGUE = 'great'
SCENARIOS = [(0, 0), (1, 1), (2, 2)]


def test_damage_vec_matches_scalar_damage_bitwise():
    """damage_vec == moves.damage element-for-element across real
    Tinkaton sweep stats x all 9 stage multipliers x a damage-relevant
    move sample (STAB / non-STAB / SE / resisted / 0-power)."""
    iv_meta = deep_dive.compute_iv_metadata('Tinkaton', LEAGUE)
    atks = np.array([m['atk'] for m in iv_meta], dtype=np.float64)
    fast_db, charged_db = get_moves()
    atk_types = ('fairy', 'steel')
    cases = [
        (charged_db['GIGATON_HAMMER'], ('fairy', 'flying')),   # STAB
        (charged_db['BULLDOZE'], ('steel', 'ground')),         # non-STAB, NVE
        (charged_db['PLAY_ROUGH'], ('dark', 'fighting')),      # STAB, SE
        (fast_db['FAIRY_WIND'], ('water', 'fairy')),           # fast move
        (fast_db['AEGISLASH_CHARGE_PSYCHO_CUT'], ('water', 'fairy')),  # 0 power
    ]
    opp_def = 127.71868924364571   # arbitrary realistic defense stat
    for move, def_types in cases:
        for stage in range(-4, 5):
            atk_eff = atks * _stat_stage_mult(stage)
            got = sig.damage_vec(move['power'], atk_eff, opp_def,
                                 move['type'], atk_types, def_types)
            for i in (0, 1, len(atks) // 2, len(atks) - 1):
                expected = scalar_damage(
                    move['power'], float(atks[i]) * _stat_stage_mult(stage),
                    opp_def, move['type'], atk_types, def_types)
                assert got[i] == expected
        # defender-side vectorization (opp -> focal direction)
        defs = np.array([m['def_'] for m in iv_meta], dtype=np.float64)
        for stage in (-4, 0, 3):
            def_eff = defs * _stat_stage_mult(stage)
            got = sig.damage_vec(move['power'], 95.3, def_eff,
                                 move['type'], atk_types, def_types)
            for i in (0, len(defs) - 1):
                expected = scalar_damage(
                    move['power'], 95.3, float(defs[i]) * _stat_stage_mult(stage),
                    move['type'], atk_types, def_types)
                assert got[i] == expected


def _profile(species, ivs, league=LEAGUE):
    a, d, s = ivs
    pkm = Pokemon.at_best_level(species, a, d, s, league=league)
    pk = (round(pkm.atk, 4), round(pkm.def_, 4), int(pkm.hp), a, d, s,
          pkm.level)
    return (pk, pkm.atk, pkm.def_, pkm.hp, a, d, s, pkm.level)


def _opp_entry(species, fast_id, charged_ids, ivs, league=LEAGUE):
    fast_db, charged_db = get_moves()
    gm = load_gamemaster()
    mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    a, d, s = ivs
    pkm = Pokemon.at_best_level(species, a, d, s, league=league)
    return {
        'species': species, 'types': parse_types(mon),
        'atk': pkm.atk, 'def_': pkm.def_, 'hp': pkm.hp,
        'fm': dict(fast_db[fast_id]),
        'cms': [dict(charged_db[c]) for c in charged_ids],
        'shadow': False,
        'mon': mon, 'ivs': ivs, 'level': pkm.level,
    }


def _groups_and_member_scores(species, fast_id, charged_ids, profiles,
                              opp_cache):
    """Run signature grouping, then sim EVERY profile (not just reps)
    via the sweep worker and return (groups_by_opp, all_scores) where
    all_scores[(pos, oi)] = [score per scenario]."""
    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon']
                     if m['speciesName'] == species)
    focal_types = parse_types(focal_mon)
    fast_db, charged_db = get_moves()
    fm = dict(fast_db[fast_id])
    cms = [dict(charged_db[c]) for c in charged_ids]

    focal_side = sig.build_focal_side(
        focal_mon, focal_types, fm, cms, profiles,
        LEAGUE_CAPS[LEAGUE], False)
    groups_by_opp = [
        sig.signature_groups(focal_side,
                             sig.build_opp_side(opp, LEAGUE_CAPS[LEAGUE]))
        for opp in opp_cache
    ]

    deep_dive._sweep_worker_init(
        species, focal_types, fm, cms, opp_cache, SCENARIOS,
        focal_mon=focal_mon, league_cp=LEAGUE_CAPS[LEAGUE],
        focal_shadow=False)
    chunk = [(prof, oi) for prof in profiles
             for oi in range(len(opp_cache))]
    results, _energy, _ = deep_dive._sweep_worker(chunk)
    all_scores = {
        (pos, oi): results[(profiles[pos][0], oi)]
        for pos in range(len(profiles)) for oi in range(len(opp_cache))
    }
    return groups_by_opp, all_scores


def test_grouped_profiles_fight_identical_battles_tinkaton():
    """Every member of every signature group produces the same scores
    as its representative — Tinkaton (buffing move on board: Bulldoze
    debuffs, opponent Azumarill has no buffs; Registeel's Zap Cannon
    debuffs atk) — and the grouping is non-trivial (some group has
    more than one member)."""
    ivs = [(a, d, s) for a in (0, 2, 5) for d in (0, 8, 15)
           for s in (5, 10, 15)]
    profiles = [_profile('Tinkaton', t) for t in ivs]
    opp_cache = [
        _opp_entry('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
                   (4, 15, 13)),
        _opp_entry('Registeel', 'LOCK_ON', ['FOCUS_BLAST', 'ZAP_CANNON'],
                   (4, 4, 14)),
    ]
    groups_by_opp, all_scores = _groups_and_member_scores(
        'Tinkaton', 'FAIRY_WIND', ['GIGATON_HAMMER', 'BULLDOZE'],
        profiles, opp_cache)

    saw_multi_member_group = False
    for oi, groups in enumerate(groups_by_opp):
        covered = []
        for rep_pos, members in groups:
            assert rep_pos == members[0]
            covered.extend(members)
            if len(members) > 1:
                saw_multi_member_group = True
            rep_scores = all_scores[(rep_pos, oi)]
            for pos in members:
                assert all_scores[(pos, oi)] == rep_scores, (
                    f"profile {profiles[pos][0]} grouped with "
                    f"{profiles[rep_pos][0]} vs opp {oi} but scores differ")
        assert sorted(covered) == list(range(len(profiles)))
    assert saw_multi_member_group, "dedup never grouped anything — vacuous test"


def test_grouped_profiles_fight_identical_battles_aegislash():
    """Form-change focal: Aegislash (Shield) signature includes the
    Blade-form damage tables, so IVs with identical Shield stats but
    different Blade stats must NOT merge (the S1 plan note's hazard).
    Verified the strong way: sim every member, compare to its rep."""
    ivs = [(a, d, s) for a in (0, 1, 4, 15) for d in (0, 14, 15)
           for s in (13, 15)]
    profiles = [_profile('Aegislash (Shield)', t) for t in ivs]
    opp_cache = [
        _opp_entry('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
                   (4, 15, 13)),
    ]
    groups_by_opp, all_scores = _groups_and_member_scores(
        'Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
        ['SHADOW_BALL', 'GYRO_BALL'], profiles, opp_cache)

    for oi, groups in enumerate(groups_by_opp):
        for rep_pos, members in groups:
            rep_scores = all_scores[(rep_pos, oi)]
            for pos in members:
                assert all_scores[(pos, oi)] == rep_scores, (
                    f"Aegislash profile {profiles[pos][0]} grouped with "
                    f"{profiles[rep_pos][0]} but scores differ")


def test_movable_axes_no_buffs_vs_buffs():
    """Axis movability: a buff-free matchup pins all stages at 0; a
    Bulldoze (opponent def debuff) focal makes the opponent's def axis
    movable but not the focal def axis."""
    fast_db, charged_db = get_moves()

    def side(fast_id, charged_ids, types=('fairy', 'steel')):
        return {
            'forms': [{'types': types,
                       'fast': dict(fast_db[fast_id]),
                       'charged': [dict(charged_db[c]) for c in charged_ids],
                       'atk': 100.0, 'def_': 100.0}],
            'native_atk': False, 'native_def': False,
        }

    no_buff = side('FAIRY_WIND', ['GIGATON_HAMMER', 'PLAY_ROUGH'])
    azu = side('BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], types=('water', 'fairy'))
    assert sig.movable_axes(no_buff, azu) == (False, False)
    assert sig.movable_axes(azu, no_buff) == (False, False)

    bulldoze = side('FAIRY_WIND', ['GIGATON_HAMMER', 'BULLDOZE'])
    # Bulldoze: guaranteed opponent def debuff -> Azumarill's def axis
    # moves; nobody touches atk stages or Tinkaton's def stage.
    assert sig.movable_axes(azu, bulldoze) == (False, True)
    assert sig.movable_axes(bulldoze, azu) == (False, False)


def test_signature_grouping_is_scenario_independent():
    """signature_groups never sees shield counts — assert the same
    grouping object serves all scenarios by construction (the API has
    no scenario parameter; this is a documentation-by-test guard that
    a future change doesn't quietly add one)."""
    import inspect
    params = inspect.signature(sig.signature_groups).parameters
    assert list(params) == ['focal_side', 'opp_side']
