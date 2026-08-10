"""
Tests for ``scripts/worlds_meta.py`` and the committed ``worlds/meta.toml``.

Two layers, per the testing policy:

* Rule tests run on FROZEN mini-fixtures, never live data -- the badge
  definitions, the per-variant modal rule, and the duplicate-aware resolver
  are pinned against hand-built inputs so a gamemaster/rankings refresh can
  never quietly rewrite what they assert.
* Contract tests pin the shipped artifact (``worlds/meta.toml``): entry
  count, the Mimikyu ban, ``format_confirmed``, move ids that actually
  resolve, and the ship-mode / iOS-bundler guards.

Nothing here hits the network: the live-data tests read the warm
gamemaster/rankings disk cache (conftest pins ``CACHE_TTL`` to infinity for
the whole session, so an existing cache file is used as-is).
"""
from __future__ import annotations

import collections
import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
META_PATH = REPO_ROOT / 'worlds' / 'meta.toml'
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'worlds_meta.py'


def _load_worlds_meta():
    """Load ``scripts/worlds_meta.py`` by path (it is a script, not a module)."""
    mod = sys.modules.get('worlds_meta')
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location('worlds_meta', SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules['worlds_meta'] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop('worlds_meta', None)
        raise
    return mod


wm = _load_worlds_meta()


# ---------------------------------------------------------------------------
# Badge definitions -- frozen mini-fixture, no live data
# ---------------------------------------------------------------------------

# (usage_rank, current_rank) -> badge, straight off the plan's definitions:
#   PLAYED  = top-25 recent usage AND top-30 current rank
#   PLAYED* = top-25 usage, current rank sank below 30
#   MODEL   = current top-30 rank, no meaningful tournament footprint
#   ''      = neither axis (FORCED is editorial and never computed)
BADGE_FIXTURE = [
    ((1, 2), 'PLAYED'),        # Lickilicky shape
    ((25, 30), 'PLAYED'),      # both bounds inclusive
    ((2, 48), 'PLAYED*'),      # Wigglytuff shape: usage in, rank sank
    ((25, 31), 'PLAYED*'),     # one past the rank bound
    ((26, 30), 'MODEL'),       # one past the usage bound
    ((46, 12), 'MODEL'),       # Ninetales shape: rebalance riser
    ((0, 17), 'MODEL'),        # never seen in the corpus at all
    ((32, 65), ''),            # Aegislash shape: neither axis (it is FORCED)
    ((100, 53), ''),           # Mantine shape: neither axis (it is FORCED)
    ((0, 0), ''),              # unranked and unseen
]


@pytest.mark.parametrize('ranks,expected', BADGE_FIXTURE)
def test_classify_badge_definitions(ranks, expected):
    """The badge rule is the plan's definition, pinned on frozen inputs."""
    assert wm.classify_badge(*ranks) == expected


def test_badge_bounds_are_the_documented_ones():
    """The cut values themselves are part of the definition."""
    assert wm.BADGE_USAGE_TOP == 25
    assert wm.BADGE_RANK_TOP == 30


# ---------------------------------------------------------------------------
# Per-variant modal rule -- the Forretress shape, on a frozen mini-fixture
# ---------------------------------------------------------------------------

def _mon(name, fast, c1, c2, shadow=False):
    return {'name': name, 'form': '', 'shadow': shadow,
            'fast': fast, 'charge1': c1, 'charge2': c2}


def _fixture_events():
    """One synthetic open-GL event with the Forretress shape.

    Non-shadow Testress runs Volt Switch 30x; shadow Testress runs Bug Bite
    20x and Volt Switch 5x. POOLED, Volt Switch is modal (35 of 55, 64%) --
    so a pooled counter would hand the shadow variant Volt Switch. Per
    variant, the shadow modal is Bug Bite at 80% of n=25, which is what the
    rule must produce.
    """
    teams = []
    for i in range(30):
        teams.append({'_id': '68000000' + f'{i:016x}', 'final_rank': i + 1,
                      'roster': [_mon('Testress', 'Volt Switch',
                                      'Rock Tomb', 'Sand Tomb')]})
    for i in range(20):
        teams.append({'_id': '68000000' + f'{i + 30:016x}', 'final_rank': i + 31,
                      'roster': [_mon('Testress', 'Bug Bite',
                                      'Rock Tomb', 'Sand Tomb', shadow=True)]})
    for i in range(5):
        teams.append({'_id': '68000000' + f'{i + 50:016x}', 'final_rank': i + 51,
                      'roster': [_mon('Testress', 'Volt Switch',
                                      'Rock Tomb', 'Sand Tomb', shadow=True)]})
    return [('testville', '2026-04', teams)]


class _FakeResolver:
    """Just enough Resolver surface for choose_moveset on the fixture."""

    def move_id(self, display_name, species_name):
        return display_name.upper().replace(' ', '_')

    def move_name(self, move_id):
        return move_id.replace('_', ' ').title()


def test_pooled_modal_differs_from_per_variant_modal():
    """The fixture is only interesting if pooling really would flip it."""
    events = _fixture_events()
    pooled = collections.Counter()
    for _slug, _month, records in events:
        for rec in records:
            for mon in rec['roster']:
                pooled[mon['fast']] += 1
    assert pooled.most_common(1)[0][0] == 'Volt Switch'   # pooled says VS

    usage = wm.Usage(events)
    shadow_modal = usage.movesets['Testress (Shadow)'].most_common(1)[0][0]
    assert shadow_modal[0] == 'Bug Bite'                  # per variant: BB


def test_per_variant_modal_wins_over_default(monkeypatch):
    """Shadow variant takes its OWN modal, not the pooled/default fast move."""
    usage = wm.Usage(_fixture_events())
    monkeypatch.setattr(wm, 'get_default_moveset',
                        lambda *a, **k: ('VOLT_SWITCH',
                                         ['ROCK_TOMB', 'SAND_TOMB']))
    chosen = wm.choose_moveset('Testress (Shadow)', 'Testress', True,
                               usage, _FakeResolver())
    assert chosen['moveset_source'] == 'modal'
    assert chosen['fast_move_id'] == 'BUG_BITE'
    assert chosen['moveset_n'] == 25
    assert chosen['moveset_modal_pct'] == 80.0
    assert chosen['default_disagrees'] is True
    assert chosen['default_fast_move_id'] == 'VOLT_SWITCH'


def test_weak_modal_falls_back_to_default(monkeypatch):
    """Under the 60%/n>=20 bar, PvPoke's default wins (the Quagsire shape)."""
    usage = wm.Usage(_fixture_events())
    monkeypatch.setattr(wm, 'get_default_moveset',
                        lambda *a, **k: ('VOLT_SWITCH',
                                         ['ROCK_TOMB', 'SAND_TOMB']))
    # Non-shadow Testress is 100% Volt Switch but... make the bar bite by
    # asking for a variant with n below MODAL_MIN_N.
    usage.movesets['Tinymon'] = collections.Counter(
        {('Bug Bite', ('Rock Tomb', 'Sand Tomb')): 19})
    chosen = wm.choose_moveset('Tinymon', 'Tinymon', False,
                               usage, _FakeResolver())
    assert chosen['moveset_source'] == 'default'
    assert chosen['fast_move_id'] == 'VOLT_SWITCH'
    assert chosen['moveset_n'] == 19       # below MODAL_MIN_N == 20
    assert chosen['moveset_modal_pct'] == 100.0


def test_modal_rule_thresholds_are_the_documented_ones():
    assert wm.MODAL_MIN_PCT == 60.0
    assert wm.MODAL_MIN_N == 20


def test_bare_form_rows_are_not_dropped():
    """Dracoviz writes both "[X [Galarian Form]]" and a bare "Galarian Form"."""
    bracketed = {'name': 'Corsola', 'form': '[Corsola [Galarian Form]]'}
    bare = {'name': 'Corsola', 'form': 'Galarian Form'}
    assert wm.dracoviz_display_name(bracketed) == 'Corsola (Galarian)'
    assert wm.dracoviz_display_name(bare) == 'Corsola (Galarian)'


def test_dracoviz_shadow_and_pooled_names():
    mon = {'name': 'Altaria', 'form': '', 'shadow': True}
    assert wm.dracoviz_display_name(mon) == 'Altaria (Shadow)'
    assert wm.dracoviz_display_name(mon, pooled=True) == 'Altaria'


def test_clean_move_strips_legacy_marker_and_bracket_forms():
    assert wm._clean_move('Psywave*') == 'Psywave'
    assert wm._clean_move('Weather Ball [Fire]') == 'Weather Ball (Fire)'


# ---------------------------------------------------------------------------
# Duplicate-aware resolver -- frozen mini-fixture
# ---------------------------------------------------------------------------

_FIXTURE_GAMEMASTER = {
    # 'Cradily' appears twice; the duplicate-tagged twin is LAST, which is
    # exactly what makes data.species_id()'s last-wins dict resolve to it.
    'pokemon': [
        {'speciesId': 'cradily', 'speciesName': 'Cradily',
         'fastMoves': ['ACID'], 'chargedMoves': ['ROCK_SLIDE']},
        {'speciesId': 'cradily_b', 'speciesName': 'Cradily',
         'tags': ['shadoweligible', 'duplicate', 'duplicate1500'],
         'fastMoves': ['ACID'], 'chargedMoves': ['ROCK_SLIDE']},
        {'speciesId': 'aegislash_shield', 'speciesName': 'Aegislash (Shield)',
         'fastMoves': ['AEGISLASH_CHARGE_PSYCHO_CUT'],
         'chargedMoves': ['GYRO_BALL', 'SHADOW_BALL']},
    ],
    'moves': [
        {'moveId': 'ACID', 'name': 'Acid'},
        {'moveId': 'ROCK_SLIDE', 'name': 'Rock Slide'},
        {'moveId': 'PSYCHO_CUT', 'name': 'Psycho Cut'},
        {'moveId': 'AEGISLASH_CHARGE_PSYCHO_CUT', 'name': 'Psycho Cut'},
        {'moveId': 'GYRO_BALL', 'name': 'Gyro Ball'},
        {'moveId': 'SHADOW_BALL', 'name': 'Shadow Ball'},
    ],
}

_FIXTURE_RANKINGS = [
    {'speciesId': 'aegislash_shield', 'speciesName': 'Aegislash (Blade)'},
    {'speciesId': 'cradily', 'speciesName': 'Cradily'},
    {'speciesId': 'cradily_b', 'speciesName': 'Cradily'},
]


@pytest.fixture
def fixture_resolver(monkeypatch):
    monkeypatch.setattr(wm, 'load_gamemaster', lambda: _FIXTURE_GAMEMASTER)
    monkeypatch.setattr(wm, 'load_rankings', lambda league: _FIXTURE_RANKINGS)
    return wm.Resolver()


def test_resolver_prefers_non_duplicate_entry(fixture_resolver):
    """'Cradily' must resolve to `cradily` (rank 2), not `cradily_b` (rank 3)."""
    assert fixture_resolver.species_id('Cradily') == 'cradily'
    assert fixture_resolver.current_rank('Cradily') == 2


def test_resolver_matches_naive_last_wins_only_on_the_duplicate(fixture_resolver):
    """Positive control: the naive last-wins index really would pick the twin."""
    naive = {p['speciesName']: p['speciesId']
             for p in _FIXTURE_GAMEMASTER['pokemon']}
    assert naive['Cradily'] == 'cradily_b'          # the trap is real
    assert fixture_resolver.species_id('Cradily') != naive['Cradily']


def test_resolver_ranks_by_species_id_not_display_name(fixture_resolver):
    """PvPoke ranks Aegislash (Shield) under the name 'Aegislash (Blade)'."""
    assert fixture_resolver.current_rank('Aegislash (Shield)') == 1


def test_resolver_disambiguates_move_names_by_legal_pool(fixture_resolver):
    """'Psycho Cut' is ambiguous; Aegislash (Shield) needs the form-specific id."""
    got = fixture_resolver.move_id('Psycho Cut', 'Aegislash (Shield)')
    assert got == 'AEGISLASH_CHARGE_PSYCHO_CUT'


def test_resolver_hard_fails_on_unmapped_move_name(fixture_resolver):
    with pytest.raises(SystemExit):
        fixture_resolver.move_id('Not A Move', 'Cradily')


def test_resolver_unranked_species_is_zero(fixture_resolver):
    assert fixture_resolver.current_rank('Nosuchmon') == 0
    assert fixture_resolver.species_id('Nosuchmon') is None


# ---------------------------------------------------------------------------
# The committed artifact
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def meta():
    assert META_PATH.exists(), f'{META_PATH} is not committed'
    with open(META_PATH, 'rb') as f:
        return tomllib.load(f)


def test_meta_parses_with_31_entries(meta):
    assert len(meta['entries']) == 31
    names = [e['name'] for e in meta['entries']]
    assert len(set(names)) == 31, 'duplicate entry names'


def test_meta_has_no_mimikyu_entry(meta):
    """Mimikyu is banned at Worlds: it may only appear as a reject row."""
    assert not [e for e in meta['entries'] if 'Mimikyu' in e['name']]
    banned = [r for r in meta['rejects'] if r.get('banned')]
    assert len(banned) == 1
    assert banned[0]['name'] == 'Mimikyu'
    assert banned[0]['current_rank'] == 1
    assert len(banned[0]['citations']) == 2


def test_meta_format_header(meta):
    assert meta['format_confirmed'] is True
    assert meta['format'] == 'open GL 1500 + Play! banned list'
    assert meta['mechanics'].startswith('legacy')


def test_meta_badges_are_the_planned_ones(meta):
    """Badge vocabulary is closed; FORCED entries carry their provenance."""
    counts = collections.Counter(e['badge'] for e in meta['entries'])
    assert set(counts) == {'PLAYED', 'PLAYED*', 'MODEL', 'FORCED'}
    assert counts['FORCED'] == 2
    forced = [e for e in meta['entries'] if e['badge'] == 'FORCED']
    assert {e['name'] for e in forced} == {'Aegislash (Shield)', 'Mantine'}
    for e in forced:
        assert len(e['forced_reason']) > 80, e['name']
    for e in meta['entries']:
        if e['badge'] != 'FORCED':
            assert 'forced_reason' not in e, e['name']


def test_meta_move_ids_resolve_against_the_gamemaster(meta):
    """Every shipped move id must be a real fast/charged move PvPoke knows."""
    from gopvpsim.moves import get_moves
    fast, charged = get_moves()
    assert fast and charged, 'move tables are empty -- cold cache?'
    for e in meta['entries']:
        assert e['fast_move_id'] in fast, (e['name'], e['fast_move_id'])
        assert len(e['charged_move_ids']) == 2, e['name']
        for mid in e['charged_move_ids']:
            assert mid in charged, (e['name'], mid)
        assert e['default_fast_move_id'] in fast, e['name']
        for mid in e['default_charged_move_ids']:
            assert mid in charged, (e['name'], mid)


def test_meta_aegislash_uses_the_form_specific_fast_move(meta):
    """The Shield form's Psycho Cut is AEGISLASH_CHARGE_PSYCHO_CUT."""
    aegi, = [e for e in meta['entries'] if e['name'] == 'Aegislash (Shield)']
    assert aegi['fast_move_id'] == 'AEGISLASH_CHARGE_PSYCHO_CUT'


def test_meta_species_ids_are_not_the_duplicate_twins(meta):
    """No entry or reject may carry a `duplicate`-tagged speciesId."""
    from gopvpsim.data import load_gamemaster
    dupes = {p['speciesId'] for p in load_gamemaster()['pokemon']
             if 'duplicate' in (p.get('tags') or [])}
    assert dupes, 'gamemaster has no duplicate-tagged entries -- scan is dead'
    for row in meta['entries'] + meta['rejects']:
        assert row['species_id'] not in dupes, row['name']


def test_meta_carries_no_narrative_or_authorship_keys():
    """Ship-mode policy: data only. No authored_by anywhere in the file."""
    text = META_PATH.read_text()
    assert 'authored_by' not in text


def test_worlds_dir_has_no_great_toml():
    """iOS bundler collision guard: `*_great.toml` is the threshold-export glob.

    ``../gobattlekit``'s bundler globs ``*_great.toml``; a Worlds output that
    matched would be swept into the app's default thresholds. Positive
    control below proves the glob is spelled right.
    """
    worlds = META_PATH.parent
    assert worlds.is_dir()
    assert list(worlds.rglob('*.toml')), 'nothing in worlds/ -- scan is dead'
    # rglob, not glob: worlds/planes/ (session 2) is a subdirectory a
    # non-recursive scan would silently skip.
    assert not list(worlds.rglob('*_great.toml'))


def test_great_toml_glob_positive_control(tmp_path):
    """The guard's glob really does catch the shape it is guarding against,
    including one level down (the rglob upgrade's whole point)."""
    (tmp_path / 'lickilicky_great.toml').write_text('x = 1\n')
    assert list(tmp_path.rglob('*_great.toml'))
    sub = tmp_path / 'planes'
    sub.mkdir()
    (sub / 'azumarill_great.toml').write_text('x = 1\n')
    assert len(list(tmp_path.rglob('*_great.toml'))) == 2


# ---------------------------------------------------------------------------
# Live regeneration
#
# These read all 33 open-GL tournament dumps plus the warm gamemaster /
# rankings cache and still land at ~0.05s each, so they carry no `slow`
# mark -- they belong in the fast tier where the ship gate sees them.
# ---------------------------------------------------------------------------

def test_generator_is_idempotent():
    """Regenerating must reproduce the committed file byte-for-byte."""
    text, _usage, _resolver = wm.generate()
    assert text == META_PATH.read_text()


def test_recent_bucket_denominators_match_the_committed_file(meta):
    """The committed denominators are the ones the corpus actually yields."""
    usage = wm.Usage(wm.load_events())
    assert len(usage.recent) == meta['usage_events_recent']
    assert usage.teams_recent == meta['usage_teams_recent']
    assert usage.teams_topcut == meta['usage_teams_topcut']
    # Buenos Aires is a September-2025 backfill: it must NOT be recent.
    assert 'buenos_aires' not in {slug for slug, _m, _r in usage.recent}
    # The three limited-meta Internationals are excluded entirely.
    assert not ({slug for slug, _m, _r in usage.events}
                & wm.LIMITED_META_EVENTS)
