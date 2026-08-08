"""Tests for the package-level ``gopvpsim.invalidate_caches()``.

DRY review 2026-08-05 entry 11: the nine gamemaster/rankings-derived
module caches had no single invalidator, so a mid-run gamemaster refresh
left modules disagreeing with no error. These tests pin (a) that every
name the invalidator reaches for still exists, (b) that each one is
actually reset, and (c) that state really is re-derived afterwards.

They also pin (d) the ``register_cache_invalidator()`` seam, which is how a
gamemaster-derived cache that lives OUTSIDE the package joins in -- the
library must not import scripts/, so the out-of-package module registers
itself instead of appearing as a table row.
"""
import ast
import importlib
import sys
from pathlib import Path

import pytest

import gopvpsim
import gopvpsim.data as data_module
import gopvpsim.evolution_lines as evo_module
import gopvpsim.moves as moves_module
import gopvpsim.pokemon as pokemon_module

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


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


# ---------------------------------------------------------------------------
# The out-of-package seam.
#
# scripts/auto_gen_narrative.py caches a gamemaster-derived move-display-name
# index (`_DEFAULT_MOVE_NAMES`), and only its own unit test ever reset it -- so
# a mid-process gamemaster swap left every library index fresh and that one
# index stale, printing old move labels on a freshly re-derived page. It cannot
# be a table row: those are resolved with importlib and the library must not
# import scripts/. Hence register_cache_invalidator().
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_registry(monkeypatch):
    """Run with a private extras registry so a test hook can't leak."""
    monkeypatch.setattr(gopvpsim, '_EXTRA_INVALIDATORS', [])
    return gopvpsim._EXTRA_INVALIDATORS


def test_registered_hook_is_called(clean_registry):
    calls = []
    gopvpsim.register_cache_invalidator(lambda: calls.append(1))
    gopvpsim.invalidate_caches()
    assert calls == [1]


def test_register_is_idempotent_and_returns_the_callable(clean_registry):
    """The lazy registration site runs on every rebuild, so re-registering
    the same callable must not stack up duplicate calls."""
    calls = []

    def hook():
        calls.append(1)

    assert gopvpsim.register_cache_invalidator(hook) is hook
    gopvpsim.register_cache_invalidator(hook)
    gopvpsim.register_cache_invalidator(hook)
    assert clean_registry == [hook]
    gopvpsim.invalidate_caches()
    assert calls == [1]


def test_extras_run_after_the_library_tables(clean_registry):
    """A hook that re-derives from library state must see the FRESH state."""
    seen = {}

    def hook():
        seen['pokemon_index'] = pokemon_module._pokemon_index

    gopvpsim.register_cache_invalidator(hook)
    pokemon_module.get_pokemon_index()
    assert pokemon_module._pokemon_index is not None
    gopvpsim.invalidate_caches()
    assert seen['pokemon_index'] is None


def test_library_does_not_import_scripts():
    """The seam exists because the arrow only points one way."""
    src = (REPO_ROOT / 'src' / 'gopvpsim' / '__init__.py').read_text()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in imported:
        root = name.split('.')[0]
        assert root in ('importlib', 'gopvpsim'), (
            f'gopvpsim/__init__.py imports {name!r}; the extras registry '
            f'exists so it never has to reach outside the package')
    # And the tables, which are the tempting place to put it, name only
    # installed gopvpsim modules.
    for mod_name, _attr, _factory in gopvpsim._CACHE_GLOBALS:
        assert mod_name.startswith('gopvpsim.'), mod_name
    for mod_name, _attr in gopvpsim._CACHE_CLEARS:
        assert mod_name.startswith('gopvpsim.'), mod_name


def test_auto_gen_narrative_move_cache_joins_invalidate_caches():
    """End-to-end: build the out-of-package cache, swap nothing, invalidate,
    and assert it was actually dropped (not just that a hook exists)."""
    import auto_gen_narrative as agn

    agn._reset_move_display_caches()
    assert agn._DEFAULT_MOVE_NAMES is None

    # Building it is ALSO what registers the reset hook.
    names = agn._default_move_names()
    assert names, 'move-name index came back empty'
    assert agn._DEFAULT_MOVE_NAMES is not None
    assert agn._reset_move_display_caches in gopvpsim._EXTRA_INVALIDATORS

    # The per-gm cache is only touched on the explicit-gm path.
    agn.move_display('POWER_WHIP', gm=data_module.load_gamemaster())
    assert agn._MOVE_NAME_INDEX_CACHE

    gopvpsim.invalidate_caches()

    assert agn._DEFAULT_MOVE_NAMES is None, \
        'auto_gen_narrative kept a stale gamemaster-derived move index'
    assert agn._MOVE_NAME_INDEX_CACHE == {}
