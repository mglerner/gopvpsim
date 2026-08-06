"""``pokemon.effective_stats`` is the one place shadow multipliers get applied.

DRY review 2026-08-05 entry 13 / L15. The multipliers used to be re-applied
six-plus separate ways (pokemon, user_collection, breakpoints, formchange,
battle, scripts) -- the shape that let SHADOW_DEF_MULT sit at the wrong 5/6
for months. These tests pin the primitive itself AND that each routed site
still produces the exact same float, since the batch must not move any score:
the arithmetic has to stay ``raw * MULT`` in that order (float multiplication
is not associative, so a reassociated form is a different number).
"""
import pytest

from gopvpsim.battle import BattlePokemon
from gopvpsim.pokemon import (
    CPM, SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
    Pokemon, battle_stats, effective_stats, iv_rank,
)
from gopvpsim.user_collection import ivs_to_stats_at_cap
from tests.conftest import FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA

RAW = [0.0, 1e-8, 0.1, 1.0, 123.456789, 158.87209701538086, 1e8]


# ---------------------------------------------------------------------------
# The primitive
# ---------------------------------------------------------------------------

def test_non_shadow_returns_the_inputs_unchanged():
    for raw in RAW:
        assert effective_stats(raw, raw * 3, False) == (raw, raw * 3)


def test_shadow_multiplies_each_side_by_its_own_constant():
    for raw in RAW:
        atk, def_ = effective_stats(raw, raw, True)
        assert atk == raw * SHADOW_ATK_BONUS
        assert def_ == raw * SHADOW_DEF_MULT


def test_multiplication_order_is_raw_times_constant():
    """Guard against a 'harmless' refactor folding the constant into the CPM
    (or any other reassociation): the products differ in the last ULP for
    roughly a third of the real (base+IV, CPM) pairs."""
    differing = 0
    for cpm in list(CPM.values()):
        raw = (FAKE_BASE_ATK + 15) * cpm
        assert effective_stats(raw, raw, True)[0] == raw * SHADOW_ATK_BONUS
        if raw * SHADOW_ATK_BONUS != (FAKE_BASE_ATK + 15) * (cpm * SHADOW_ATK_BONUS):
            differing += 1
    assert differing > 0, "reassociation is undetectable here; test is toothless"


def test_hp_and_cp_are_not_shadow_adjusted(mock_gm):
    normal = Pokemon.at_best_level('Testmon', 15, 15, 15, league='great')
    shadow = Pokemon.at_best_level('Testmon', 15, 15, 15, league='great',
                                   shadow=True)
    assert shadow.hp == normal.hp
    assert shadow.cp == normal.cp


# ---------------------------------------------------------------------------
# Every routed site agrees with the primitive, bit for bit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('shadow', [False, True])
def test_pokemon_properties_route_through_the_primitive(mock_gm, shadow):
    p = Pokemon.at_best_level('Testmon', 3, 14, 9, league='great',
                              shadow=shadow)
    raw = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                       3, 14, 9, p.level)
    assert (p.atk, p.def_) == effective_stats(raw['atk'], raw['def'], shadow)


@pytest.mark.parametrize('shadow', [False, True])
def test_iv_rank_rows_route_through_the_primitive(mock_gm, shadow):
    for e in iv_rank('Testmon', league='great', shadow=shadow):
        raw = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                           e['atk_iv'], e['def_iv'], e['sta_iv'], e['level'])
        assert (e['atk'], e['def_']) == effective_stats(raw['atk'], raw['def'],
                                                        shadow)
        assert e['stat_product'] == e['atk'] * e['def_'] * e['hp']


@pytest.mark.parametrize('shadow', [False, True])
def test_ivs_to_stats_at_cap_routes_through_the_primitive(shadow):
    r = ivs_to_stats_at_cap(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                            2, 14, 13, max_cp=1500, shadow=shadow)
    raw = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                       2, 14, 13, r['level'])
    assert (r['attack'], r['defense']) == effective_stats(raw['atk'],
                                                          raw['def'], shadow)


def test_cmp_atk_strips_exactly_the_attack_bonus():
    """CMP compares shadow-free attack, so cmp_atk divides by the same
    constant effective_stats multiplied in (it used to re-type 1.2)."""
    raw_atk = 158.87209701538086
    bp = BattlePokemon(
        species='Testmon', types=['normal'],
        atk=effective_stats(raw_atk, 100.0, True)[0], def_=100.0, max_hp=100,
        fast_move={'moveId': 'F', 'name': 'F', 'type': 'normal', 'power': 5,
                   'energyGain': 5, 'cooldown': 1000},
        charged_moves=[], shadow=True,
    )
    assert bp.cmp_atk == raw_atk * SHADOW_ATK_BONUS / SHADOW_ATK_BONUS
    assert bp.atk / bp.cmp_atk == SHADOW_ATK_BONUS


@pytest.mark.integration
def test_form_change_stats_route_through_the_primitive():
    """formchange.py builds BOTH forms' stats -- the sixth application site.

    Compared shadow-vs-plain rather than rebuilt from base stats, because the
    Blade form re-derives its own level: same IVs and level either way, so the
    shadow pair must be exactly the plain pair through the primitive.
    """
    from gopvpsim.moves import get_moves

    fast_moves, charged_moves = get_moves()
    forms = {}
    for shadow in (False, True):
        p = Pokemon.at_best_level('Aegislash (Shield)', 0, 15, 15,
                                  league='great', shadow=shadow)
        bp = BattlePokemon.from_pokemon(
            p, dict(fast_moves['AEGISLASH_CHARGE_PSYCHO_CUT']),
            [dict(charged_moves['GYRO_BALL'])], league_cp=1500)
        assert bp._form_change is not None
        forms[shadow] = bp._form_change.forms

    for plain, shad in zip(forms[False], forms[True]):
        assert plain.species == shad.species
        assert (shad.atk, shad.def_) == effective_stats(plain.atk, plain.def_,
                                                        True)
