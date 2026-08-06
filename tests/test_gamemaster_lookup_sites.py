"""Call sites that were moved off linear gamemaster scans keep their
failure modes (DRY review 2026-08-05 entry 12 / L11).

Every site converted here used to run its own
``next((m for m in gm['pokemon'] if m['speciesName'] == x), None)`` and
now calls ``gopvpsim.pokemon.find_pokemon_entry`` -- the ``.get()``-style
accessor over the cached speciesName index.

The hazard the review flagged is a *silent failure-mode change*: the
sibling accessor ``get_pokemon_entry`` raises ``KeyError``, so swapping a
site onto it turns a None/[]-returning lookup into a raising one, and the
site's own miss handling (a ``return None``, a ``return []``, a
``sys.exit``, a purpose-written ``KeyError`` message) becomes dead code
nobody notices until a species goes missing from the gamemaster.

So each converted site is pinned twice: the hit path produces what it
always did, and the MISS path still lands in the site's own handler. Most
miss branches are unreachable with real data -- the callers resolve stats
first, which raises earlier -- so the miss tests patch the module-level
``find_pokemon_entry`` name to a misser. That is exactly the seam the
conversion introduced, and it is the thing that would break.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

from gopvpsim import anchors, breakpoints
from gopvpsim.data import get_default_moveset
from gopvpsim.moves import get_moves
from gopvpsim.pokemon import find_pokemon_entry

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'

KNOWN_SPECIES = 'Azumarill'
MISSING_SPECIES = 'NotARealMon'


def _misser(_name):
    """Stand-in for find_pokemon_entry that finds nothing."""
    return None


def _load_script(name, filename):
    """Load a scripts/*.py file under an alias, once per session."""
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    for p in (REPO_ROOT / 'src', SCRIPTS_DIR):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


# ---------------------------------------------------------------------------
# Class 1: []-on-miss
# ---------------------------------------------------------------------------

def test_threat_moves_hit_returns_the_species_move_pool():
    moves = anchors._opponent_threat_moves(KNOWN_SPECIES)
    assert moves
    assert all('moveId' in m for m in moves)


def test_threat_moves_miss_returns_empty_list():
    """The one converted site a genuinely absent species still reaches:
    it looks the entry up directly, with no stat resolution in front."""
    assert anchors._opponent_threat_moves(MISSING_SPECIES) == []


# ---------------------------------------------------------------------------
# Class 2: None-on-miss
# ---------------------------------------------------------------------------

def test_opponent_ref_hit_returns_defense_and_types():
    ref = anchors._opponent_ref(KNOWN_SPECIES, league='great')
    assert ref is not None
    def_stat, types = ref
    assert def_stat > 0
    assert types == ['water', 'fairy']


def test_opponent_atk_ref_hit_returns_attack_and_types():
    ref = anchors._opponent_atk_ref(KNOWN_SPECIES, league='great')
    assert ref is not None
    atk_stat, types = ref
    assert atk_stat > 0
    assert types == ['water', 'fairy']


@pytest.mark.parametrize('fn_name', ['_opponent_ref', '_opponent_atk_ref'])
def test_opponent_refs_return_none_when_the_entry_is_missing(monkeypatch, fn_name):
    monkeypatch.setattr(anchors, 'find_pokemon_entry', _misser)
    assert getattr(anchors, fn_name)(KNOWN_SPECIES, league='great') is None


# ---------------------------------------------------------------------------
# Class 3: raise, with the site's OWN message
# ---------------------------------------------------------------------------

def test_get_types_hit_returns_the_type_list():
    assert breakpoints._get_types(KNOWN_SPECIES) == ['water', 'fairy']


def test_get_types_miss_keeps_its_own_keyerror_message(monkeypatch):
    """``get_pokemon_entry``'s KeyError carries the bare name; this site's
    carries 'Species not found: ...' and callers surface it to users."""
    monkeypatch.setattr(breakpoints, 'find_pokemon_entry', _misser)
    with pytest.raises(KeyError, match='Species not found'):
        breakpoints._get_types(KNOWN_SPECIES)


# ---------------------------------------------------------------------------
# Class 4: sys.exit-on-miss (CLI)
# ---------------------------------------------------------------------------

def test_cli_battle_builds_a_battle_pokemon():
    cli = _load_script('cli_battle_script', 'battle.py')
    fast, charged = get_default_moveset(KNOWN_SPECIES, 'great', shadow=False)
    bp = cli.make_battle_pokemon(KNOWN_SPECIES, fast, list(charged),
                                 'great', 1, 0, 15, 15)
    assert bp.species == KNOWN_SPECIES
    assert bp.types == ['water', 'fairy']


def test_cli_battle_exits_when_the_entry_is_missing(monkeypatch):
    """A raising accessor here would skip the argument-error exit and
    dump a traceback at the user instead."""
    cli = _load_script('cli_battle_script', 'battle.py')
    fast, charged = get_default_moveset(KNOWN_SPECIES, 'great', shadow=False)
    monkeypatch.setattr(cli, 'find_pokemon_entry', _misser)
    with pytest.raises(SystemExit) as exc:
        cli.make_battle_pokemon(KNOWN_SPECIES, fast, list(charged),
                                'great', 1, 0, 15, 15)
    assert 'Unknown species' in str(exc.value)


# ---------------------------------------------------------------------------
# Class 5: raise-on-miss with the accessor's own KeyError
# ---------------------------------------------------------------------------

def test_harness_grid_make_bp_builds_from_the_accessor():
    """make_bp lost its ``gm`` parameter with the conversion -- the whole
    (fast_moves, charged_moves) ctx tuple is one shorter now."""
    harness = _load_script('harness_grid_script', 'harness_grid.py')
    fast, charged = get_default_moveset(KNOWN_SPECIES, 'great', shadow=False)
    fast_moves, charged_moves = get_moves()
    spec = harness.Spec(
        species_id='azumarill', species_name=KNOWN_SPECIES,
        fast=fast, charged=list(charged), atk_iv=0, def_iv=15, sta_iv=15,
    )
    bp = harness.make_bp(spec, 'great', 1, fast_moves, charged_moves)
    assert bp.species == KNOWN_SPECIES
    assert bp.types == ['water', 'fairy']


def test_harness_grid_make_bp_raises_on_a_missing_entry(monkeypatch):
    harness = _load_script('harness_grid_script', 'harness_grid.py')
    fast, charged = get_default_moveset(KNOWN_SPECIES, 'great', shadow=False)
    fast_moves, charged_moves = get_moves()
    spec = harness.Spec(
        species_id='azumarill', species_name=KNOWN_SPECIES,
        fast=fast, charged=list(charged), atk_iv=0, def_iv=15, sta_iv=15,
    )
    monkeypatch.setattr(harness, 'find_pokemon_entry', _misser)
    with pytest.raises(KeyError, match='species not found in gamemaster'):
        harness.make_bp(spec, 'great', 1, fast_moves, charged_moves)


# ---------------------------------------------------------------------------
# The empty-string lookup the dive renderer can actually pass
# ---------------------------------------------------------------------------

def test_missing_species_key_is_a_miss_not_an_error():
    """deep_dive_lib/render.py looks the focal entry up as
    ``data_obj.get('species', '')`` and falls back to ``[]`` types. With
    the raising accessor that default would blow up the whole render."""
    assert find_pokemon_entry('') is None
    assert find_pokemon_entry(MISSING_SPECIES) is None


# ---------------------------------------------------------------------------
# Regression guard: the converted files stay converted
# ---------------------------------------------------------------------------

# Files whose per-species gamemaster lookups have all been routed through
# the accessor. Not the whole repo: index-building comprehensions
# (build_opponent_pool, migrate_cache, evolution_lines) legitimately walk
# gm['pokemon'], and the case-insensitive / speciesId-keyed lookups in
# generate_article.py and compare_loadouts.py are a different query the
# accessor does not answer.
_CONVERTED = (
    'scripts/battle.py',
    'scripts/harness_grid.py',
    'scripts/deep_dive_lib/render.py',
    'src/gopvpsim/anchors.py',
    'src/gopvpsim/breakpoints.py',
)


def test_converted_files_have_no_linear_species_scans():
    import re
    scan = re.compile(r"for\s+\w+\s+in\s+\w+\[['\"]pokemon['\"]\]")
    offenders = []
    for rel in _CONVERTED:
        for n, line in enumerate(
                (REPO_ROOT / rel).read_text().splitlines(), start=1):
            if line.lstrip().startswith('#'):
                continue
            if scan.search(line):
                offenders.append(f'{rel}:{n}: {line.strip()}')
    assert not offenders, (
        'linear gamemaster scan reintroduced; use '
        'gopvpsim.pokemon.find_pokemon_entry (None on miss) or '
        'get_pokemon_entry (KeyError on miss):\n' + '\n'.join(offenders))
