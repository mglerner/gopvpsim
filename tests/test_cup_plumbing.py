"""Cup plumbing single-sourcing (DRY review 2026-08-05 entry 6).

The July 2026 cup work reproduced the same three facts -- a cup's key, its
mechanical league, and its display name -- in parallel across the library, the
dive renderer, the dive card, the website index and the dive runner. These
tests pin the consolidated versions:

* ``gopvpsim.data`` owns ONE cup registry plus the public rankings accessors
  (``get_rankings_for`` / ``rankings_cache_path``) the scripts used to
  reimplement from private names.
* ``build_website_index._CUP_SUFFIXES`` is DERIVED from that registry, and the
  cup-index heading uses the same ``cup_pretty_name`` the dive page bakes in
  (the two fallbacks disagreed: "Bastille Cup" vs "Bastille").
* ``deep_dive_card.cup_label_and_snapshot`` is the one header formatter for
  both the full dive page and the standalone card, and it never blanks the
  archive line just because the snapshot date is unavailable.
* ``run_website_dives.check_cup_slugs`` fails BEFORE hours of simulation when
  a cup dive's slug breaks the ``<species>-<cup>-cup`` convention the website
  index routes on.

Pure-Python; nothing here simulates a battle or hits the network.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gopvpsim import data as gpdata  # noqa: E402

import deep_dive_card as dc  # noqa: E402
import run_website_dives as rwd  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "build_website_index", REPO_ROOT / "scripts" / "build_website_index.py")
bwi = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(bwi)


# ---- data.py: one registry, one set of accessors ---------------------------

def test_registry_is_the_rankings_allow_list():
    """The known-cups check reads the registry, so a cup can't be listed for
    rankings but missing from the name/league table (or vice versa)."""
    assert gpdata._CUPS_WITH_RANKINGS == frozenset(gpdata.CUP_REGISTRY)
    with pytest.raises(ValueError) as e:
        gpdata.load_cup_rankings('definitely-not-a-cup', 1500)
    assert 'equinox' in str(e.value)  # names the valid set


def test_cup_pretty_name_has_one_fallback():
    """One derivation for an unnamed cup, everywhere. deep_dive said
    '<Key> Cup' where build_website_index said '<Key>' for the same cup."""
    assert gpdata.cup_pretty_name('equinox') == 'Equinox Cup'
    assert gpdata.cup_pretty_name('bastille') == 'Bastille Cup'
    assert gpdata.cup_pretty_name('nosuchcup') == 'Nosuchcup Cup'
    assert gpdata.cup_pretty_name(None) is None
    assert gpdata.cup_pretty_name('') is None


def test_cup_dive_league_only_for_plumbed_cups():
    assert gpdata.cup_dive_league('equinox') == 'great'
    assert gpdata.cup_dive_league('bastille') is None   # rankings only
    assert gpdata.cup_dive_league('nosuchcup') is None


def test_rankings_cache_path_matches_the_fetch_key():
    """The path a renderer stats for the 'as of' date must be the file
    _fetch_json actually writes: <league>.json / rankings_<cup>_<cp>.json."""
    assert gpdata.rankings_cache_path('great').name == 'great.json'
    assert (gpdata.rankings_cache_path('great', cup='equinox').name
            == 'rankings_equinox_1500.json')
    assert (gpdata.rankings_cache_path('ultra', cup='equinox').name
            == 'rankings_equinox_2500.json')
    assert gpdata.rankings_cache_path('great').parent == gpdata.CACHE_DIR


def test_get_rankings_for_routes_cup_to_the_league_cp(monkeypatch):
    calls = {}
    monkeypatch.setattr(gpdata, 'load_rankings',
                        lambda league: calls.setdefault('league', league))
    monkeypatch.setattr(gpdata, 'load_cup_rankings',
                        lambda cup, cp: calls.setdefault('cup', (cup, cp)))
    gpdata.get_rankings_for('great')
    assert calls == {'league': 'great'}
    calls.clear()
    gpdata.get_rankings_for('ultra', cup='equinox')
    assert calls == {'cup': ('equinox', 2500)}


# ---- build_website_index: suffixes derived from the registry ---------------

def test_cup_suffixes_derived_from_registry():
    expected = {f'{k}-cup': (info.dive_league, k, gpdata.cup_pretty_name(k))
                for k, info in gpdata.CUP_REGISTRY.items() if info.dive_league}
    assert bwi._CUP_SUFFIXES == expected
    assert 'equinox-cup' in bwi._CUP_SUFFIXES
    # A rankings-only cup has no dive plumbing, so no slug suffix to route on.
    assert 'bastille-cup' not in bwi._CUP_SUFFIXES


def test_cup_index_heading_uses_the_shared_pretty_name():
    """An unnamed cup's heading reads '<Key> Cup' -- the same string the dive
    page bakes in -- instead of the old bare '<Key>' fallback."""
    dives = [{'slug': 'corviknight-equinox-cup', 'title': 'x',
              'description': 'd', 'href': 'corviknight-equinox-cup/index.html'}]
    assert '<h2>Equinox Cup</h2>' in bwi.render_cup_index(dives)
    assert bwi._cup_status_line('bastille', {}) is not None
    # Direct check of the formatter both pages share.
    assert gpdata.cup_pretty_name('bastille') == 'Bastille Cup'


# ---- W8: one slug parser, one title formatter ------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("slug,expected", [
    # The acceptance case: the retired fallback parser took the FIRST token as
    # the species, so a leading 'shadow' token became an empty species name and
    # the title carried a doubled space ("Shadow  Corviknight").
    ('shadow-corviknight-great-league', 'Shadow Corviknight (Great League)'),
    ('shadow-sableye-great-league', 'Shadow Sableye (Great League)'),
    ('galarian-corsola-great-league', 'Galarian Corsola (Great League)'),
    ('shadow-alolan-ninetales-ultra-league',
     'Shadow Alolan Ninetales (Ultra League)'),
    # Trailing-token spellings were already correct and must stay byte-identical.
    ('corviknight-shadow-great-league', 'Shadow Corviknight (Great League)'),
    ('forretress-shadow-bug-bite-great-league',
     'Shadow Forretress Bug Bite (Great League)'),
    ('oinkologne-great-league', 'Oinkologne (Male) (Great League)'),
    ('oinkologne-female-great-league', 'Oinkologne (Female) (Great League)'),
    ('aegislash-blade-ultra-league', 'Aegislash (Blade) (Ultra League)'),
    ('corviknight-equinox-cup', 'Corviknight (Equinox Cup)'),
])
def test_pretty_title_has_no_doubled_space(slug, expected):
    title = bwi._slug_to_pretty_title(slug)
    assert '  ' not in title
    assert title == expected


@pytest.mark.integration
def test_pretty_title_inherits_the_multiword_species_fix():
    """The title formatter now rides on _parse_dive_slug, so multi-word
    species get the longest-known-prefix match the fallback parser never got."""
    assert (bwi._slug_to_pretty_title('mr-mime-shadow-great-league')
            == 'Shadow Mr Mime (Great League)')
    assert (bwi._slug_to_pretty_title('tapu-fini-shadow-master-league')
            == 'Shadow Tapu Fini (Master League)')


def test_pretty_title_empty_for_unparseable_slug():
    """One parser means one 'this isn't a dive slug' answer."""
    assert bwi._slug_to_pretty_title('guides') == ''
    assert bwi._slug_to_pretty_title('forretress-shadow') == ''
    assert bwi._parse_dive_slug('guides') is None


# ---- shared page shell / stylesheet ---------------------------------------

def test_cup_index_carries_the_grouped_listing_css():
    """render_cup_index renders the SAME _render_dives_grouped markup as the
    main index, so it must ship the same rules; its hand-copied stylesheet
    omitted .dives-box / .scroll-hint / li.dive.empty."""
    page = bwi.render_cup_index([])
    for rule in ('.dives-box', '.dives-scroll', '.scroll-hint',
                 'li.dive.empty'):
        assert rule in page
    assert bwi._index_css() in page


def test_both_landing_pages_use_one_shell():
    index = bwi.render_index([], [], [])
    cups = bwi.render_cup_index([])
    for page in (index, cups):
        assert page.startswith('<!DOCTYPE html>')
        assert '<style>' in page and '</style>' in page
        assert bwi.PVPOKE_ATTRIBUTION_HTML in page
        assert page.rstrip().endswith('</html>')
    # The discord line is index-only chrome, passed through the shell.
    assert 'TitanTrainers15' in index
    assert 'TitanTrainers15' not in cups


# ---- shared cup header formatter (dive page + standalone card) -------------

def test_cup_header_non_cup_dive_is_plain_league():
    assert dc.cup_label_and_snapshot(None, 'Great League', None) == \
        ('Great League', '')
    assert dc.cup_label_and_snapshot('', 'Great League', '2026-07-03') == \
        ('Great League', '')


def test_cup_header_leads_with_the_cup_name():
    league_txt, snap = dc.cup_label_and_snapshot(
        'Equinox Cup', 'Great League', '2026-07-03')
    assert league_txt == 'Equinox Cup (Great League)'
    assert snap == 'snapshot as of 2026-07-03'


def test_cup_header_keeps_the_archive_line_without_a_date():
    """The missing no-date path: an un-stat-able rankings cache must not erase
    the archive claim, it must drop only the date it can't honestly name."""
    _, snap = dc.cup_label_and_snapshot('Equinox Cup', 'Great League', None)
    assert snap == 'dated snapshot'


def _cup_card_model(snapshot):
    return dc.CardModel(
        species_display='Corviknight', shadow=False,
        types=['Flying', 'Steel'],
        league_display='Great League', cp_cap=1500,
        moveset='Sand Attack / Air Cutter, Payback',
        spreads=[], single_iv=None, robust=None,
        cup_label='Equinox Cup', cup_snapshot=snapshot)


def test_card_renders_the_archive_line_with_and_without_a_date():
    with_date = dc.render_card_html(_cup_card_model("2026-07-03"), standalone=False)
    assert 'Equinox Cup (Great League)' in with_date
    assert 'Snapshot as of 2026-07-03 - archived cup meta' in with_date

    without_date = dc.render_card_html(_cup_card_model(None), standalone=False)
    assert 'Equinox Cup (Great League)' in without_date
    # Previously the whole line vanished, so the standalone card silently
    # dropped its "this is an archive" disclosure.
    assert 'Dated snapshot - archived cup meta' in without_date


def test_dive_page_banner_uses_the_shared_formatter():
    """Source pin: the full dive page must not re-derive the cup header."""
    src = (REPO_ROOT / 'scripts' / 'deep_dive.py').read_text()
    assert 'from deep_dive_card import cup_label_and_snapshot' in src
    assert "f'{cup_label} ({league.title()} League)'" not in src


# ---- run_website_dives slug preflight --------------------------------------

def test_shipped_dives_pass_the_cup_slug_preflight():
    rwd.check_cup_slugs(rwd.DIVES)


def test_preflight_rejects_a_misspelled_cup_slug():
    bad = [{'species': 'Corviknight', 'league': 'great',
            'slug': 'corviknight-equinox', 'cup': 'equinox'}]
    with pytest.raises(ValueError) as e:
        rwd.check_cup_slugs(bad)
    assert '-equinox-cup' in str(e.value)


def test_preflight_rejects_an_unregistered_cup():
    bad = [{'species': 'Corviknight', 'league': 'great',
            'slug': 'corviknight-nosuchcup-cup', 'cup': 'nosuchcup'}]
    with pytest.raises(ValueError) as e:
        rwd.check_cup_slugs(bad)
    assert 'CUP_REGISTRY' in str(e.value)


def test_preflight_rejects_a_league_mismatch():
    bad = [{'species': 'Corviknight', 'league': 'ultra',
            'slug': 'corviknight-equinox-cup', 'cup': 'equinox'}]
    with pytest.raises(ValueError) as e:
        rwd.check_cup_slugs(bad)
    assert "registered as a 'great'" in str(e.value)


def test_preflight_ignores_non_cup_dives():
    rwd.check_cup_slugs([{'species': 'Tinkaton', 'league': 'great',
                          'slug': 'tinkaton-great-league'}])


def test_index_router_accepts_every_shipped_cup_slug():
    """Close the loop: the slugs this runner PRODUCES must parse as cup dives
    for the index ROUTER, or they'd land in the evergreen league lists."""
    for d in rwd.DIVES:
        if not d.get('cup'):
            continue
        parsed = bwi._parse_dive_slug(d['slug'])
        assert parsed is not None, d['slug']
        assert parsed['cup'] == d['cup'], d['slug']
        assert parsed['league_key'] == d['league'], d['slug']
