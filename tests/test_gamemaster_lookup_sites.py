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


def _ensure_scripts_on_path():
    for p in (REPO_ROOT / 'src', SCRIPTS_DIR):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _load_script(name, filename):
    """Load a scripts/*.py file under an alias, once per session."""
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    _ensure_scripts_on_path()
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
# The one behavior difference the conversion really has: FIRST vs LAST
# ---------------------------------------------------------------------------

# The gamemaster carries a handful of duplicate speciesName rows (PvPoke's
# 'duplicate'/'duplicate1500' ranking artifacts -- 'lanturn' + 'lanturnw',
# 'cradily' + 'cradily_b', 'golisopod' + 'golisopodsh'). A linear
# ``next(m for m in gm['pokemon'] ...)`` returns the FIRST such row; the
# speciesName index is a dict comprehension, so it keeps the LAST. Every
# converted site therefore picks a different row for those species.
#
# That is score-neutral only while the duplicate rows agree on everything
# the battle reads. Today they differ solely in bookkeeping fields
# (speciesId, aliasId, tags, nicknames, searchPriority, released). If
# PvPoke ever ships duplicates that disagree on stats/types/moves/
# formChange, the conversion stops being a no-op -- and this fails.

_BATTLE_RELEVANT_KEYS = ('baseStats', 'types', 'fastMoves', 'chargedMoves',
                         'eliteMoves', 'legacyMoves', 'formChange', 'level25CP')


def test_duplicate_species_rows_agree_on_everything_the_battle_reads():
    from gopvpsim.data import load_gamemaster
    gm = load_gamemaster()
    by_name = {}
    for mon in gm['pokemon']:
        by_name.setdefault(mon['speciesName'], []).append(mon)
    dupes = {n: rows for n, rows in by_name.items() if len(rows) > 1}
    assert dupes, 'expected the gamemaster to still carry duplicate rows'
    divergent = []
    for name, rows in sorted(dupes.items()):
        first, last = rows[0], rows[-1]
        # The index really does hand back the LAST row, not the first.
        # (Compared by speciesId, not identity: load_gamemaster() re-parses
        # the JSON per call, so the index holds its own copies.)
        assert first['speciesId'] != last['speciesId']
        assert find_pokemon_entry(name)['speciesId'] == last['speciesId']
        for key in _BATTLE_RELEVANT_KEYS:
            if first.get(key) != last.get(key):
                divergent.append(f'{name}.{key}: '
                                 f'{first.get(key)!r} != {last.get(key)!r}')
    assert not divergent, (
        'duplicate gamemaster rows now disagree on a battle-relevant field, '
        'so first-match (the old linear scans) and last-match (the '
        'speciesName index) no longer simulate the same:\n'
        + '\n'.join(divergent))


# ---------------------------------------------------------------------------
# Class 6: deep_dive.py -- False-on-miss and fall-back-on-miss
# ---------------------------------------------------------------------------

FORM_CHANGE_SPECIES = 'Aegislash (Shield)'
SIBLING_FORM_SPECIES = 'Morpeko (Hangry)'


def _deep_dive():
    return _load_script('deep_dive_script', 'deep_dive.py')


@pytest.mark.parametrize('species,expected', [
    (KNOWN_SPECIES, False),          # plain entry, no formChange key
    (FORM_CHANGE_SPECIES, True),     # declares its own formChange
    (SIBLING_FORM_SPECIES, True),    # only reachable via the REVERSE scan
])
def test_species_has_form_change_hits(species, expected):
    """The sibling case is the one that still needs a scan over
    gm['pokemon'] -- it asks which entry points AT this speciesId, which
    the speciesName index cannot answer."""
    dd = _deep_dive()
    dd._FORM_CHANGE_SPECIES_CACHE.clear()
    assert dd._species_has_form_change(species) is expected


def test_species_has_form_change_miss_is_false_not_a_raise(monkeypatch):
    """A raising accessor here would abort IV dedup for the whole sweep
    instead of falling back to the conservative per-IV grouping."""
    dd = _deep_dive()
    dd._FORM_CHANGE_SPECIES_CACHE.clear()
    monkeypatch.setattr(dd, 'find_pokemon_entry', _misser)
    assert dd._species_has_form_change(KNOWN_SPECIES) is False
    dd._FORM_CHANGE_SPECIES_CACHE.clear()


def test_opp_robustness_groups_miss_falls_back_to_one_group_per_iv():
    """``_opp_robustness_groups`` reads its ``if opp_mon is None`` branch
    only because the lookup returns None; the arguments before ``ranked``
    are untouched on that path, so they can be dummies."""
    dd = _deep_dive()
    dd._FORM_CHANGE_SPECIES_CACHE.clear()
    ranked = [{'atk': 1.0, 'def_': 1.0, 'hp': 1, 'atk_iv': 0, 'def_iv': 15,
               'sta_iv': 15, 'level': 40.0} for _ in range(3)]
    fast, charged = get_default_moveset(KNOWN_SPECIES, 'great', shadow=False)
    groups = dd._opp_robustness_groups(
        None, KNOWN_SPECIES, fast, list(charged), False, (0, 15, 15),
        MISSING_SPECIES, fast, list(charged), False, 'great', ranked)
    assert groups == [[0], [1], [2]]
    dd._FORM_CHANGE_SPECIES_CACHE.clear()


# ---------------------------------------------------------------------------
# Class 7: deep_dive_lib/sweep.py -- raise-on-miss, preserved
# ---------------------------------------------------------------------------

def test_sweep_uses_the_raising_accessor():
    """Both sweep sites were bare ``next(...)`` with no default, i.e. they
    raised on miss. They must stay raising -- a None here would reach
    ``parse_types`` and die somewhere less legible."""
    _ensure_scripts_on_path()
    from deep_dive_lib import sweep
    with pytest.raises(KeyError):
        sweep.get_pokemon_entry(MISSING_SPECIES)
    assert sweep.get_pokemon_entry(KNOWN_SPECIES)['speciesName'] == KNOWN_SPECIES


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
    'scripts/deep_dive.py',
    'scripts/deep_dive_lib/render.py',
    'scripts/deep_dive_lib/sweep.py',
    'src/gopvpsim/anchors.py',
    'src/gopvpsim/breakpoints.py',
)

# Scans inside a covered file that the accessor genuinely cannot answer, so
# the guard would otherwise have to drop the whole file. (file, exact line).
_ALLOWED_SCANS = {
    # _build_species_id_to_name: builds the speciesId -> speciesName index
    # in one O(n) pass; not a per-species lookup at all.
    ('scripts/deep_dive.py',
     "return {m['speciesId']: m['speciesName'] for m in gm['pokemon']}"),
    # _species_has_form_change: the reverse direction -- "which entry's
    # formChange points AT this speciesId". The speciesName index cannot
    # answer it.
    ('scripts/deep_dive.py',
     "for m in load_gamemaster()['pokemon'])"),
}


def test_converted_files_have_no_linear_species_scans():
    import re
    # Both spellings of the subscript: a bound name (``gm['pokemon']``) and
    # the inline call (``load_gamemaster()['pokemon']``).
    scan = re.compile(r"for\s+\w+\s+in\s+[\w.]+(?:\(\))?\[['\"]pokemon['\"]\]")
    offenders = []
    for rel in _CONVERTED:
        for n, line in enumerate(
                (REPO_ROOT / rel).read_text().splitlines(), start=1):
            if line.lstrip().startswith('#'):
                continue
            if scan.search(line) and (rel, line.strip()) not in _ALLOWED_SCANS:
                offenders.append(f'{rel}:{n}: {line.strip()}')
    assert not offenders, (
        'linear gamemaster scan reintroduced; use '
        'gopvpsim.pokemon.find_pokemon_entry (None on miss) or '
        'get_pokemon_entry (KeyError on miss):\n' + '\n'.join(offenders))


def test_allowed_scans_are_all_still_present():
    """A stale allowlist entry silently widens the guard: it would keep
    excusing a line that no longer exists while the file drifts."""
    missing = [
        f'{rel}: {text}' for rel, text in sorted(_ALLOWED_SCANS)
        if text not in {
            ln.strip() for ln in (REPO_ROOT / rel).read_text().splitlines()}
    ]
    assert not missing, (
        'allowlisted scan no longer in the file; drop the entry:\n'
        + '\n'.join(missing))
