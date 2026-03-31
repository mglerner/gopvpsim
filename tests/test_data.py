"""
Tests for gopvpsim.data — fetch and cache layer.

All tests here require network access (or a warm cache) and are marked
'integration'. Run with: pytest -m integration
"""
import pytest
from gopvpsim.data import load_gamemaster, load_rankings, NoDataError


@pytest.mark.integration
def test_load_gamemaster_has_pokemon():
    gm = load_gamemaster()
    assert 'pokemon' in gm
    assert len(gm['pokemon']) > 0

@pytest.mark.integration
def test_load_gamemaster_has_moves():
    gm = load_gamemaster()
    assert 'moves' in gm
    assert len(gm['moves']) > 0

@pytest.mark.integration
def test_load_gamemaster_pokemon_has_expected_fields():
    gm = load_gamemaster()
    mon = gm['pokemon'][0]
    assert 'speciesName' in mon
    assert 'baseStats' in mon
    assert {'atk', 'def', 'hp'} <= set(mon['baseStats'].keys())

@pytest.mark.integration
def test_load_gamemaster_moves_have_energy_fields():
    gm = load_gamemaster()
    move = gm['moves'][0]
    assert 'energyGain' in move or 'energy' in move

@pytest.mark.integration
@pytest.mark.parametrize("league", ["great", "ultra", "master"])
def test_load_rankings_returns_list(league):
    rankings = load_rankings(league)
    assert isinstance(rankings, list)
    assert len(rankings) > 0

@pytest.mark.integration
def test_load_rankings_has_rating():
    rankings = load_rankings("great")
    assert 'rating' in rankings[0]

def test_load_rankings_invalid_league_raises():
    with pytest.raises(ValueError):
        load_rankings("kiddie")
