"""Tests for the package-level ``gopvpsim.invalidate_caches()``.

DRY review 2026-08-05 entry 11: the nine gamemaster/rankings-derived
module caches had no single invalidator, so a mid-run gamemaster refresh
left modules disagreeing with no error. These tests pin (a) that every
name the invalidator reaches for still exists, (b) that each one is
actually reset, and (c) that state really is re-derived afterwards.
"""
import importlib

import pytest

import gopvpsim
import gopvpsim.data as data_module
import gopvpsim.evolution_lines as evo_module
import gopvpsim.moves as moves_module
import gopvpsim.pokemon as pokemon_module


def test_cache_table_names_all_exist():
    """A typo/rename in the table must not silently no-op."""
    for mod_name, attr, _factory in gopvpsim._CACHE_GLOBALS:
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, attr), f"{mod_name}.{attr} is gone"
    for mod_name, attr in gopvpsim._CACHE_CLEARS:
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, attr), f"{mod_name}.{attr} is gone"
        assert hasattr(getattr(mod, attr), 'cache_clear'), \
            f"{mod_name}.{attr} is not a functools-cached callable"


def test_cache_table_covers_the_documented_nine():
    """The entry-11 inventory, spelled out so a dropped line is visible."""
    expected = {
        ('gopvpsim.pokemon',         '_pokemon_index'),
        ('gopvpsim.pokemon',         '_gm_entry_index'),
        ('gopvpsim.pokemon',         '_gm_id_index'),
        ('gopvpsim.moves',           '_fast_moves'),
        ('gopvpsim.moves',           '_charged_moves'),
        ('gopvpsim.data',            '_species_id_index'),
        ('gopvpsim.data',            '_rankings_index'),
        ('gopvpsim.evolution_lines', '_evolution_lines_cache'),
        ('gopvpsim.evolution_lines', '_pre_to_finals_cache'),
    }
    assert {(m, a) for m, a, _f in gopvpsim._CACHE_GLOBALS} == expected


def test_every_named_global_is_reset():
    """Poison each cache with a sentinel, then assert it is cleared."""
    for mod_name, attr, factory in gopvpsim._CACHE_GLOBALS:
        importlib.import_module(mod_name).__dict__[attr] = 'POISON'

    gopvpsim.invalidate_caches()

    for mod_name, attr, factory in gopvpsim._CACHE_GLOBALS:
        value = getattr(importlib.import_module(mod_name), attr)
        assert value == factory(), f"{mod_name}.{attr} was not reset"


def test_missing_global_raises(monkeypatch):
    """A cache that no longer exists must raise, not pass silently."""
    monkeypatch.setattr(
        gopvpsim, '_CACHE_GLOBALS',
        (('gopvpsim.pokemon', '_not_a_real_cache', gopvpsim._none),))
    with pytest.raises(AttributeError, match='_not_a_real_cache'):
        gopvpsim.invalidate_caches()


def test_missing_cache_clear_target_raises(monkeypatch):
    monkeypatch.setattr(gopvpsim, '_CACHE_GLOBALS', ())
    monkeypatch.setattr(
        gopvpsim, '_CACHE_CLEARS',
        (('gopvpsim.display', '_not_a_real_lru_cache'),))
    with pytest.raises(AttributeError, match='_not_a_real_lru_cache'):
        gopvpsim.invalidate_caches()


def test_state_is_rederived_after_invalidation():
    """Identity changes: the post-invalidation index is a fresh object."""
    first_index = pokemon_module.get_pokemon_index()
    first_entry = pokemon_module.get_pokemon_entry('Azumarill')
    first_fast, first_charged = moves_module.get_moves()
    first_lines = evo_module.load_evolution_lines()
    data_module.species_id('Azumarill')
    first_species_ids = data_module._species_id_index

    gopvpsim.invalidate_caches()

    assert pokemon_module._pokemon_index is None
    assert moves_module._fast_moves is None
    assert data_module._species_id_index is None

    second_index = pokemon_module.get_pokemon_index()
    second_entry = pokemon_module.get_pokemon_entry('Azumarill')
    second_fast, second_charged = moves_module.get_moves()
    second_lines = evo_module.load_evolution_lines()
    data_module.species_id('Azumarill')

    assert second_index is not first_index
    assert second_entry is not first_entry
    assert second_fast is not first_fast
    assert second_charged is not first_charged
    assert second_lines is not first_lines
    assert data_module._species_id_index is not first_species_ids

    # Re-derivation must produce the same content, not just a new object.
    assert second_index == first_index
    assert second_entry == first_entry
    assert second_lines == first_lines


def test_swapped_gamemaster_is_picked_up_by_every_module(monkeypatch):
    """The bug this closes: a mid-run gamemaster swap used to leave the
    modules disagreeing. After invalidate_caches() they all see the new
    data."""
    fake_gm = {
        'pokemon': [{
            'speciesName': 'Fakemon',
            'speciesId': 'fakemon',
            'baseStats': {'atk': 100, 'def': 100, 'hp': 100},
            'types': ['normal', 'none'],
            'fastMoves': ['FAKE_FAST'],
            'chargedMoves': ['FAKE_CHARGED'],
        }],
        'moves': [
            {'moveId': 'FAKE_FAST', 'name': 'Fake Fast', 'type': 'normal',
             'power': 3, 'energyGain': 4, 'cooldown': 1000},
            {'moveId': 'FAKE_CHARGED', 'name': 'Fake Charged',
             'type': 'normal', 'power': 90, 'energy': 50, 'energyGain': 0},
        ],
    }
    for mod in ('gopvpsim.data', 'gopvpsim.pokemon', 'gopvpsim.moves',
                'gopvpsim.evolution_lines'):
        monkeypatch.setattr(f'{mod}.load_gamemaster', lambda: fake_gm,
                            raising=False)

    gopvpsim.invalidate_caches()
    try:
        assert 'Fakemon' in pokemon_module.get_pokemon_index()
        assert 'Azumarill' not in pokemon_module.get_pokemon_index()
        assert pokemon_module.get_pokemon_entry_by_id('fakemon')['speciesName'] \
            == 'Fakemon'
        fast, charged = moves_module.get_moves()
        assert set(fast) == {'FAKE_FAST'}
        assert set(charged) == {'FAKE_CHARGED'}
        assert data_module.species_id('Fakemon') == 'fakemon'
    finally:
        # Undo the swap for everything that follows in this session.
        monkeypatch.undo()
        gopvpsim.invalidate_caches()

    assert 'Azumarill' in pokemon_module.get_pokemon_index()
