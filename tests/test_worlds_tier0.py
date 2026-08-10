"""Tier-0 closed-form cutoffs (scripts/worlds_tier0.py).

The exactness contract: every cutoff is the exact float boundary of the
ENGINE's damage predicate (moves.damage, staged as battle.py stages it).
Pinned four ways: an exhaustive predicate-equivalence sweep over a real
pair's attainable atk grid, an algebraic-seed drift tripwire, a
third-party oracle pin (DragapultSim's published Tinkaton-vs-Mantine
110.21), and a source scan proving the module never retypes a damage
constant (with a positive control on the scanner).
"""
import ast
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT / 'src', REPO_ROOT / 'scripts'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gopvpsim.data import parse_types  # noqa: E402
from gopvpsim.moves import get_moves, damage as engine_damage  # noqa: E402
from gopvpsim.pokemon import find_pokemon_entry, iv_rank  # noqa: E402
import worlds_tier0 as t0  # noqa: E402

FAST_DB, CHARGED_DB = get_moves()

TINKATON_TYPES = parse_types(find_pokemon_entry('Tinkaton'))
MANTINE_TYPES = parse_types(find_pokemon_entry('Mantine'))
GIGATON = CHARGED_DB['GIGATON_HAMMER']
FAIRY_WIND = FAST_DB['FAIRY_WIND']
BULLDOZE = CHARGED_DB['BULLDOZE']


def _mantine(a, d, s):
    entry = next(e for e in iv_rank('Mantine', league='great', shadow=False)
                 if (e['atk_iv'], e['def_iv'], e['sta_iv']) == (a, d, s))
    return entry


def test_atk_cutoff_is_the_exact_engine_boundary():
    """Exhaustive over Tinkaton's full attainable GL atk grid x a
    32-spread Mantine def cohort x every tier in range: damage >= tier
    iff atk >= cutoff, with both sides of every cutoff non-empty."""
    atks = sorted({e['atk'] for e in iv_rank('Tinkaton', league='great',
                                             shadow=False)})
    cohort = iv_rank('Mantine', league='great', shadow=False)[:32]
    checked_cutoffs = 0
    for entry in cohort:
        d = entry['def_']
        lo_t = t0.staged_damage(GIGATON, atks[0], d,
                                TINKATON_TYPES, MANTINE_TYPES)
        hi_t = t0.staged_damage(GIGATON, atks[-1], d,
                                TINKATON_TYPES, MANTINE_TYPES)
        assert hi_t > lo_t          # the range spans >1 tier (non-trivial)
        for tier in range(lo_t + 1, hi_t + 1):
            cut = t0.atk_cutoff(GIGATON, TINKATON_TYPES, MANTINE_TYPES,
                                tier, d)
            below = [a for a in atks if a < cut]
            above = [a for a in atks if a >= cut]
            assert below and above   # both sides populated
            for a in (below[-1], above[0]):   # the straddling neighbors
                got = t0.staged_damage(GIGATON, a, d,
                                       TINKATON_TYPES, MANTINE_TYPES)
                assert (got >= tier) == (a >= cut)
            checked_cutoffs += 1
    assert checked_cutoffs >= 30     # floor well below today's count


def test_full_grid_predicate_equivalence_one_def():
    """Every attainable atk (not just the straddlers) agrees with the
    cutoff predicate for one def, all tiers."""
    atks = sorted({e['atk'] for e in iv_rank('Tinkaton', league='great',
                                             shadow=False)})
    d = _mantine(0, 15, 7)['def_']
    lo_t = t0.staged_damage(GIGATON, atks[0], d, TINKATON_TYPES,
                            MANTINE_TYPES)
    hi_t = t0.staged_damage(GIGATON, atks[-1], d, TINKATON_TYPES,
                            MANTINE_TYPES)
    cuts = {tier: t0.atk_cutoff(GIGATON, TINKATON_TYPES, MANTINE_TYPES,
                                tier, d)
            for tier in range(lo_t + 1, hi_t + 1)}
    for a in atks:
        got = t0.staged_damage(GIGATON, a, d, TINKATON_TYPES, MANTINE_TYPES)
        for tier, cut in cuts.items():
            assert (got >= tier) == (a >= cut), (a, tier, cut, got)


def test_def_cutoff_take_and_deny_asymmetry():
    tinka = iv_rank('Tinkaton', league='great', shadow=False)[0]
    a = tinka['atk']
    tier = t0.staged_damage(GIGATON, a,
                            _mantine(0, 15, 7)['def_'],
                            TINKATON_TYPES, MANTINE_TYPES) + 1
    cut = t0.def_cutoff(GIGATON, TINKATON_TYPES, MANTINE_TYPES, tier, a)
    take = t0.staged_damage(GIGATON, a, cut, TINKATON_TYPES, MANTINE_TYPES)
    deny = t0.staged_damage(GIGATON, a, math.nextafter(cut, math.inf),
                            TINKATON_TYPES, MANTINE_TYPES)
    assert take >= tier and deny < tier


def test_ko_cutoff_reproduces_dragapultsim_gigaton_two_shot():
    """Third-party oracle pin (docs/worlds_prep_plan.md, the designated
    validation pair): Tinkaton guarantees the Gigaton-2-shot vs Mantine
    0/15/7 (12 Fairy Wind + 2 Gigaton Hammer >= 120 HP) at 110.21 atk --
    DragapultSim's published number, reproduced to its 2dp rounding.
    Their best spread 12/6/11 clears the cutoff; the deep-bulk anchor
    itself is the binding constraint of the reach claim."""
    m = _mantine(0, 15, 7)
    assert m['hp'] == 120
    assert f"{m['def_']:.2f}" == '170.36'
    cut = t0.ko_cutoff(FAIRY_WIND, GIGATON, 12, 2, m['hp'],
                       TINKATON_TYPES, MANTINE_TYPES, m['def_'])
    assert f'{cut:.2f}' == '110.21'
    best = next(e for e in iv_rank('Tinkaton', league='great', shadow=False)
                if (e['atk_iv'], e['def_iv'], e['sta_iv']) == (12, 6, 11))
    assert best['atk'] >= cut
    # And the cutoff is exact: one float below fails the plan.
    below = math.nextafter(cut, -math.inf)
    total = (12 * t0.staged_damage(FAIRY_WIND, below, m['def_'],
                                   TINKATON_TYPES, MANTINE_TYPES)
             + 2 * t0.staged_damage(GIGATON, below, m['def_'],
                                    TINKATON_TYPES, MANTINE_TYPES))
    assert total < m['hp']


def test_guarantee_cutoff_maxes_over_the_cohort():
    cohort = iv_rank('Mantine', league='great', shadow=False)[:16]
    cut, binding = t0.guarantee_cutoff(FAIRY_WIND, GIGATON, 12, 2,
                                       TINKATON_TYPES, MANTINE_TYPES, cohort)
    per = [t0.ko_cutoff(FAIRY_WIND, GIGATON, 12, 2, e['hp'],
                        TINKATON_TYPES, MANTINE_TYPES, e['def_'])
           for e in cohort]
    assert cut == max(per)
    assert binding in cohort
    assert min(per) < max(per)       # the max is a real selection


def test_stage_axis_changes_the_cutoff():
    """A -1 opponent-def stage lowers the atk needed (the deny-side
    honesty flag in the module docstring)."""
    d = _mantine(0, 15, 7)['def_']
    base = t0.ko_cutoff(FAIRY_WIND, GIGATON, 12, 2, 120,
                        TINKATON_TYPES, MANTINE_TYPES, d)
    debuffed = t0.ko_cutoff(FAIRY_WIND, GIGATON, 12, 2, 120,
                            TINKATON_TYPES, MANTINE_TYPES, d, stage_def=-1)
    assert debuffed < base


def test_seed_stays_within_ulp_tripwire():
    """The naive algebraic seed (computed HERE, not in the module) must
    stay within SEED_ULP_TRIPWIRE ULP of the exact cutoff -- it blows up
    if anyone reorders the moves.py expression."""
    from gopvpsim.moves import BONUS, stab, type_effectiveness
    cohort = iv_rank('Mantine', league='great', shadow=False)[:8]
    checked = 0
    for move in (GIGATON, BULLDOZE):
        eff = type_effectiveness(move['type'], MANTINE_TYPES)
        stab_ = stab(move['type'], TINKATON_TYPES)
        c = 0.5 * BONUS * move['power'] * eff * stab_
        for entry in cohort:
            d = entry['def_']
            for tier in (5, 9, 14):
                seed = (tier - 1) * d / c
                cut = t0.atk_cutoff(move, TINKATON_TYPES, MANTINE_TYPES,
                                    tier, d)
                steps = 0
                x = seed
                while x < cut and steps <= t0.SEED_ULP_TRIPWIRE:
                    x = math.nextafter(x, math.inf)
                    steps += 1
                while x > cut and steps <= t0.SEED_ULP_TRIPWIRE:
                    x = math.nextafter(x, -math.inf)
                    steps += 1
                assert steps <= t0.SEED_ULP_TRIPWIRE, (move['moveId'], d,
                                                       tier, seed, cut)
                checked += 1
    assert checked == 2 * 8 * 3


def test_zero_power_form_move_raises():
    aegis_fast = FAST_DB['AEGISLASH_CHARGE_PSYCHO_CUT']
    with pytest.raises(t0.ClosedFormError, match='power'):
        t0.staged_damage(aegis_fast, 100.0, 100.0,
                         ('steel', 'ghost'), MANTINE_TYPES)


def test_closed_form_excluded_gates_form_changers():
    assert t0.closed_form_excluded('Aegislash (Shield)') is True
    assert t0.closed_form_excluded('Tinkaton') is False


def test_tier1_is_rejected():
    with pytest.raises(t0.ClosedFormError, match='tier 1'):
        t0.atk_cutoff(GIGATON, TINKATON_TYPES, MANTINE_TYPES, 1, 150.0)


def test_cmp_threshold_nonshadow_and_shadow():
    """Non-shadow: identity comparison, tie band is the single float.
    Shadow: the tie band is the fl(a/1.2)==opp interval, verified by
    predicate on its edges; win_above is its upper neighbor."""
    opp = 147.32158
    r = t0.cmp_threshold(opp, focal_shadow=False)
    assert r['tie_min'] == r['tie_max'] == opp
    assert r['win_above'] == math.nextafter(opp, math.inf)

    rs = t0.cmp_threshold(opp, focal_shadow=True)
    from gopvpsim.pokemon import SHADOW_ATK_BONUS
    assert rs['tie_min'] is not None
    assert rs['tie_min'] / SHADOW_ATK_BONUS == opp
    assert rs['tie_max'] / SHADOW_ATK_BONUS == opp
    assert math.nextafter(rs['tie_min'], -math.inf) / SHADOW_ATK_BONUS < opp
    assert rs['win_above'] / SHADOW_ATK_BONUS > opp
    assert rs['win_above'] == math.nextafter(rs['tie_max'], math.inf)


def test_cmp_shadow_roundtrip_artifact_is_real():
    """Pins the 2026-08-10 audit finding the cmp_threshold docstring
    cites: reconstructing raw atk by division breaks some exact shadow
    ties -- fl(fl(x * 6/5) / (6/5)) != x for Quagsire 0/15/14 (1 ULP
    low). If an engine-side fix ever lands (pending decision, TODO.md),
    this flips and the tier0 docs must be updated with it."""
    from gopvpsim.pokemon import SHADOW_ATK_BONUS
    entry = next(e for e in iv_rank('Quagsire', league='great', shadow=False)
                 if (e['atk_iv'], e['def_iv'], e['sta_iv']) == (0, 15, 14))
    x = entry['atk']
    assert (x * SHADOW_ATK_BONUS) / SHADOW_ATK_BONUS != x
    assert (x * SHADOW_ATK_BONUS) / SHADOW_ATK_BONUS == \
        math.nextafter(x, -math.inf)


def test_movable_stage_axes_matches_meta_movesets():
    """Tinkaton's Bulldoze moves the OPPONENT def axis; Corviknight's
    Air Cutter moves its OWN atk axis (incl. the would_shield
    projection rule); a buff-free pair moves nothing."""
    tinka = (FAIRY_WIND, [GIGATON, BULLDOZE])
    mantine = (FAST_DB['WING_ATTACK'],
               [CHARGED_DB['TWISTER'], CHARGED_DB['WATER_PULSE']])
    (f_atk, f_def), (o_atk, o_def) = t0.movable_stage_axes(tinka, mantine)
    assert (f_atk, f_def) == (False, False)
    assert (o_atk, o_def) == (False, True)      # Bulldoze debuffs opp def

    corv = (FAST_DB['SAND_ATTACK'],
            [CHARGED_DB['AIR_CUTTER'], CHARGED_DB['PAYBACK']])
    (f_atk, f_def), (o_atk, o_def) = t0.movable_stage_axes(corv, mantine)
    assert f_atk is True                        # Air Cutter self atk buff
    # Post-June-2026-rebalance gamemaster: SAND_ATTACK carries NO buffs
    # (the debuff was removed), so Corviknight moves nothing on the
    # opponent -- pinned so a future re-buff surfaces here.
    assert (o_atk, o_def) == (False, False)


def test_module_never_retypes_a_damage_constant():
    """Source scan: no 0.5 / 1.3 / 1.2-family float literal anywhere in
    worlds_tier0.py -- the predicate must go through moves.damage.
    Positive control: the scanner finds a planted literal, and the
    module DOES import the engine damage function (so the absence pin
    cannot rot into vacuity)."""
    src = (REPO_ROOT / 'scripts' / 'worlds_tier0.py').read_text()
    tree = ast.parse(src)
    banned = {0.5, 1.3, 1.2, 1.2999999523162841796875,
              1.2000000476837158203125, 1.60000002384185791015625}
    hits = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, float)
            and n.value in banned]
    assert not hits, f'retyped damage constants in worlds_tier0.py: {hits}'
    # Positive control 1: the scanner catches a planted literal.
    planted = ast.parse('x = 0.5 * 1.3')
    control = [n.value for n in ast.walk(planted)
               if isinstance(n, ast.Constant) and isinstance(n.value, float)
               and n.value in banned]
    assert len(control) == 2
    # Positive control 2: the canonical replacement is present.
    assert 'from gopvpsim.moves import damage as _engine_damage' in src
    assert t0._engine_damage is engine_damage
