"""Dive-slug parsing in scripts/build_website_index.py.

Pins the 2026-06-11 W8 fix: multi-word species (Mr. Mime, Tapu Fini,
Porygon-Z) span several hyphen tokens, and the old first-token-is-the-
species rule grouped them as species "Mr"/"Tapu"/"Porygon" with the
rest as variant chips. The parser now longest-prefix-matches against
gamemaster species slugs, with single-token behavior unchanged.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "build_website_index", REPO_ROOT / "scripts" / "build_website_index.py")
bwi = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(bwi)


@pytest.mark.integration
@pytest.mark.parametrize("slug,species_display,variants", [
    # Multi-word species: the W8 fix proper.
    ('mr-mime-great-league', 'Mr Mime', []),
    ('tapu-fini-great-league', 'Tapu Fini', []),
    # Single-word slugs: behavior must be byte-identical to before
    # (these cover every published dive-dir shape today).
    ('tinkaton-ultra-league', 'Tinkaton', []),
    ('shadow-sableye-great-league', 'Sableye', ['Shadow']),
    ('oinkologne-female-great-league', 'Oinkologne', ['Female']),
    ('aegislash-blade-ultra-league', 'Aegislash', ['Blade']),
    ('forretress-shadow-bug-bite-great-league', 'Forretress',
     ['Shadow', 'Bug', 'Bite']),
])
def test_parse_dive_slug(slug, species_display, variants):
    parsed = bwi._parse_dive_slug(slug)
    assert parsed is not None
    assert parsed['species_display'] == species_display
    assert parsed['variant_tokens'] == variants


@pytest.mark.integration
def test_multiword_species_group_key_is_whole_name():
    parsed = bwi._parse_dive_slug('mr-mime-great-league')
    assert parsed['group_key'] == 'mr_mime'
    # The old parser produced group_key 'mr' with 'Mime' as a variant.
    assert parsed['variant_tokens'] == []


# ---- Limited-cup slugs (Phase 2 top-N/cup plan) ----

@pytest.mark.integration
@pytest.mark.parametrize("slug,species_display,cup,variants", [
    ('corviknight-equinox-cup', 'Corviknight', 'equinox', []),
    ('mantine-equinox-cup', 'Mantine', 'equinox', []),
    ('moltres-galarian-equinox-cup', 'Galarian Moltres', 'equinox', []),
    ('gyarados-shadow-equinox-cup', 'Gyarados', 'equinox', ['Shadow']),
])
def test_parse_cup_slug(slug, species_display, cup, variants):
    parsed = bwi._parse_dive_slug(slug)
    assert parsed is not None
    assert parsed['species_display'] == species_display
    assert parsed['cup'] == cup
    assert parsed['league_key'] == 'great'  # cup implies its mechanical league
    assert parsed['variant_tokens'] == variants


@pytest.mark.integration
def test_league_slug_has_no_cup():
    """A normal league dive parses with cup=None (never routed to the cup index)."""
    parsed = bwi._parse_dive_slug('corviknight-great-league')
    assert parsed is not None and parsed['cup'] is None


@pytest.mark.integration
def test_cup_pretty_title_names_the_cup():
    # HTML-fallback title says the cup, not a bare league.
    assert bwi._slug_to_pretty_title('corviknight-equinox-cup') == \
        'Corviknight (Equinox Cup)'


@pytest.mark.integration
def test_render_cup_index_lists_dive_and_rebases_href():
    """render_cup_index groups by cup and links each dive with a '../' prefix
    (the cup index lives one dir below the flat cup-dive dirs)."""
    cup_dives = [{
        'slug': 'corviknight-equinox-cup',
        'title': 'Corviknight (Equinox Cup)',
        'description': 'x',
        'href': 'corviknight-equinox-cup/index.html',
    }]
    html = bwi.render_cup_index(cup_dives)
    assert 'Equinox Cup' in html
    assert '../corviknight-equinox-cup/index.html' in html
    # The main-index back-link is present.
    assert '../index.html' in html
