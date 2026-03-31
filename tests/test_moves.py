"""
Tests for gopvpsim.moves — type effectiveness, damage formula, move lookup.

Unit tests need no network. Integration tests (marked 'integration') use the
real gamemaster. Run integration tests with: pytest -m integration
"""
import pytest

from gopvpsim.moves import (
    EFFECTIVENESS, STAB_MULTIPLIER,
    type_effectiveness, stab, damage, get_moves,
)


# ===========================================================================
# EFFECTIVENESS table structure
# ===========================================================================

ALL_TYPES = [
    'normal', 'fire', 'water', 'electric', 'grass', 'ice', 'fighting',
    'poison', 'ground', 'flying', 'psychic', 'bug', 'rock', 'ghost',
    'dragon', 'dark', 'steel', 'fairy',
]

def test_effectiveness_has_all_attacker_types():
    assert set(EFFECTIVENESS.keys()) == set(ALL_TYPES)

def test_effectiveness_has_all_defender_types():
    for atk_type, row in EFFECTIVENESS.items():
        assert set(row.keys()) == set(ALL_TYPES), f"Missing defender types for {atk_type}"

def test_effectiveness_values_are_valid():
    valid = {0.390625, 0.625, 1.0, 1.6}
    for atk_type, row in EFFECTIVENESS.items():
        for def_type, val in row.items():
            assert val in valid, (
                f"Unexpected effectiveness {val} for {atk_type} vs {def_type}"
            )


# ===========================================================================
# type_effectiveness()
# ===========================================================================

def test_neutral_single_type():
    assert type_effectiveness('water', ['normal']) == pytest.approx(1.0)

def test_super_effective_single_type():
    assert type_effectiveness('water', ['fire']) == pytest.approx(1.6)

def test_not_very_effective_single_type():
    assert type_effectiveness('water', ['water']) == pytest.approx(0.625)

def test_immune_treated_as_not_effective():
    # Ghost vs Normal — PoGo uses 0.390625 instead of 0
    assert type_effectiveness('ghost', ['normal']) == pytest.approx(0.390625)

def test_double_super_effective():
    # Ice vs Grass/Flying — 1.6 * 1.6 = 2.56
    assert type_effectiveness('ice', ['grass', 'flying']) == pytest.approx(2.56)

def test_double_resist():
    # Ground vs Bug/Flying — 0.625 * 0.390625 (flying immune to ground)
    assert type_effectiveness('ground', ['bug', 'flying']) == pytest.approx(0.625 * 0.390625)

def test_se_and_nve_cancel():
    # Water vs Water/Fire — 0.625 * 1.6 = 1.0
    assert type_effectiveness('water', ['water', 'fire']) == pytest.approx(1.0)

def test_single_type_list():
    # Single-element list same as bare type
    assert type_effectiveness('fire', ['grass']) == pytest.approx(1.6)


# ===========================================================================
# stab()
# ===========================================================================

def test_stab_match():
    assert stab('water', ['water']) == pytest.approx(STAB_MULTIPLIER)

def test_stab_match_dual_type():
    assert stab('fire', ['fire', 'flying']) == pytest.approx(STAB_MULTIPLIER)

def test_stab_no_match():
    assert stab('water', ['fire']) == pytest.approx(1.0)

def test_stab_multiplier_is_1_2():
    assert STAB_MULTIPLIER == pytest.approx(1.2)


# ===========================================================================
# damage()
# ===========================================================================

def test_damage_minimum_is_1():
    # Tiny power, atk much less than def → floor(...) = 0, +1 = 1
    assert damage(1, 1.0, 1000.0, 'normal', ['normal'], ['normal']) == 1

def test_damage_neutral_no_stab():
    """
    floor(0.5 * 1.3 * 10 * 100.0/100.0 * 1.0 * 1.0) + 1
    = floor(6.5) + 1 = 7
    """
    assert damage(10, 100.0, 100.0, 'water', ['fire'], ['normal']) == 7

def test_damage_with_stab():
    """
    floor(0.5 * 1.3 * 10 * 100.0/100.0 * 1.0 * 1.2) + 1
    = floor(7.8) + 1 = 8
    """
    assert damage(10, 100.0, 100.0, 'water', ['water'], ['normal']) == 8

def test_damage_super_effective():
    """
    floor(0.5 * 1.3 * 10 * 100.0/100.0 * 1.6 * 1.0) + 1
    = floor(10.4) + 1 = 11
    """
    assert damage(10, 100.0, 100.0, 'water', ['fire'], ['fire']) == 11

def test_damage_stab_and_super_effective():
    """
    floor(0.5 * 1.3 * 10 * 100.0/100.0 * 1.6 * 1.2) + 1
    = floor(12.48) + 1 = 13
    """
    assert damage(10, 100.0, 100.0, 'water', ['water'], ['fire']) == 13

def test_damage_not_very_effective():
    """
    floor(0.5 * 1.3 * 10 * 100.0/100.0 * 0.625 * 1.0) + 1
    = floor(4.0625) + 1 = 5
    """
    assert damage(10, 100.0, 100.0, 'water', ['fire'], ['water']) == 5

def test_damage_floor_behavior():
    """Verify floor (not round) is applied: 0.65 * 3 = 1.95 → floor=1, +1=2 (round would give 3)."""
    assert damage(3, 100.0, 100.0, 'normal', ['psychic'], ['normal']) == 2

def test_damage_is_int():
    result = damage(10, 100.0, 100.0, 'water', ['water'], ['fire'])
    assert isinstance(result, int)


# ===========================================================================
# Integration tests — require real gamemaster
# ===========================================================================

@pytest.mark.integration
def test_get_moves_returns_two_dicts():
    fast, charged = get_moves()
    assert isinstance(fast, dict)
    assert isinstance(charged, dict)

@pytest.mark.integration
def test_fast_moves_have_energy_gain():
    fast, _ = get_moves()
    assert len(fast) > 0
    for move_id, move in fast.items():
        assert move['energyGain'] != 0, f"Fast move {move_id} has energyGain=0"

@pytest.mark.integration
def test_charged_moves_have_no_energy_gain():
    _, charged = get_moves()
    assert len(charged) > 0
    for move_id, move in charged.items():
        assert move['energyGain'] == 0, f"Charged move {move_id} has energyGain!=0"

@pytest.mark.integration
def test_known_fast_move_exists():
    fast, _ = get_moves()
    assert 'COUNTER' in fast

@pytest.mark.integration
def test_known_charged_move_exists():
    _, charged = get_moves()
    assert 'CLOSE_COMBAT' in charged

@pytest.mark.integration
def test_moves_have_power_field():
    fast, charged = get_moves()
    sample_fast = next(iter(fast.values()))
    sample_charged = next(iter(charged.values()))
    assert 'power' in sample_fast
    assert 'power' in sample_charged
