"""Tests for ``scripts/build_website_index`` slug parsing + grouping.

The site-index card titles and the grouped Deep Dives section both
derive from dive directory slugs, so a regression in the slug rewrite
or the group-by-species collapse would break the public-facing landing
page silently. Mercuryish flagged the original "Forretress (Shadow)" →
"Shadow Forretress" rewrite (G4); ``_slug_to_pretty_title`` tests pin
that format. ``_parse_dive_slug`` / ``_group_dives`` tests pin the
group-by-species layout (one card per base species, variant chips).
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from build_website_index import (  # noqa: E402
    _slug_to_pretty_title,
    _parse_dive_slug,
    _group_dives,
    load_entries,
)


@pytest.mark.integration
@pytest.mark.parametrize("slug,expected", [
    # Plain species, no form / regional / shadow tags.
    ("tinkaton-great-league",            "Tinkaton (Great League)"),
    ("lapras-great-league",              "Lapras (Great League)"),

    # Regional / shadow: modifier hoists to a leading prefix per the
    # 2026-05-17 naming rewrite (mercuryish G4).
    ("forretress-shadow-great-league",         "Shadow Forretress (Great League)"),
    ("corsola-galarian-great-league",          "Galarian Corsola (Great League)"),
    ("stunfisk-galarian-great-league",         "Galarian Stunfisk (Great League)"),
    ("ninetales-alolan-great-league",          "Alolan Ninetales (Great League)"),

    # Shadow + regional stacks: Shadow goes outermost.
    ("weezing-galarian-shadow-great-league",   "Shadow Galarian Weezing (Great League)"),

    # In-battle form changes keep their parenthetical (Shield/Blade/etc.
    # are sub-form tags, not regional flavors).
    ("aegislash-blade-great-league",     "Aegislash (Blade) (Great League)"),
    ("aegislash-shield-great-league",    "Aegislash (Shield) (Great League)"),

    # Gender disambiguation: Oinkologne has a Female sibling in the
    # gamemaster, so the bare slug gains "(Male)".
    ("oinkologne-great-league",          "Oinkologne (Male) (Great League)"),
    ("oinkologne-female-great-league",   "Oinkologne (Female) (Great League)"),

    # Compound slugs with moveset descriptors after the species.
    # The species portion goes through pretty_species_from_slug; the
    # remaining tokens are capitalized and appended verbatim.
    ("forretress-shadow-bug-bite-great-league",
        "Shadow Forretress Bug Bite (Great League)"),

    # Ultra and Master league suffixes.
    ("lapras-ultra-league",              "Lapras (Ultra League)"),
])
def test_slug_to_pretty_title(slug, expected):
    assert _slug_to_pretty_title(slug) == expected


def test_unrecognized_slug_returns_empty():
    """Slugs missing the trailing league suffix should return '' so the
    caller falls back to the HTML <title> tag."""
    assert _slug_to_pretty_title("forretress-shadow") == ''
    assert _slug_to_pretty_title("guides") == ''


# ---------------------------------------------------------------------------
# Grouped Deep Dives section (group-by-species with variant chips)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("slug,group_key,species,shadow,gender,variant,league", [
    # Moveset descriptor + infix shadow token.
    ("forretress-shadow-bug-bite-great-league",
     "forretress", "Forretress", True, None, ["Shadow", "Bug", "Bite"], "great"),
    ("forretress-bug-bite-great-league",
     "forretress", "Forretress", False, None, ["Bug", "Bite"], "great"),
    # Prefix shadow token (different slug order, same classification).
    ("shadow-jumpluff-great-league",
     "jumpluff", "Jumpluff", True, None, ["Shadow"], "great"),
    # Regional stays in the group key (different dex entry); prefix order.
    ("galarian-corsola-great-league",
     "corsola_galarian", "Galarian Corsola", False, None, [], "great"),
    # Gender is a variant axis; the group heading drops "(Male)/(Female)".
    ("oinkologne-female-great-league",
     "oinkologne", "Oinkologne", False, "female", ["Female"], "great"),
    ("oinkologne-great-league",
     "oinkologne", "Oinkologne", False, None, [], "great"),
    # Alternate form is a variant axis.
    ("aegislash-shield-great-league",
     "aegislash", "Aegislash", False, None, ["Shield"], "great"),
    # League is recorded for the multi-league chip decision.
    ("tinkaton-ultra-league",
     "tinkaton", "Tinkaton", False, None, [], "ultra"),
])
def test_parse_dive_slug(slug, group_key, species, shadow, gender, variant, league):
    p = _parse_dive_slug(slug)
    assert p is not None
    assert p['group_key'] == group_key
    assert p['species_display'] == species
    assert p['shadow'] == shadow
    assert p['gender'] == gender
    assert p['variant_tokens'] == variant
    assert p['league_key'] == league


def test_parse_dive_slug_unrecognized():
    assert _parse_dive_slug("forretress-shadow") is None  # no league suffix
    assert _parse_dive_slug("great-league") is None        # no species token


def _entry(slug):
    return {'slug': slug, 'title': slug, 'description': 'x', 'curated': False}


def _labels(groups, species):
    g = next(g for g in groups if g['species'] == species)
    return [r['label'] for r in g['entries']]


def test_group_dives_collapses_variants_and_orders_chips():
    dives = [_entry(s) for s in [
        "forretress-bug-bite-great-league",
        "forretress-volt-switch-great-league",
        "forretress-shadow-bug-bite-great-league",
        "forretress-shadow-volt-switch-great-league",
        "tinkaton-great-league",
        "tinkaton-ultra-league",
        "oinkologne-great-league",
        "oinkologne-female-great-league",
        "jumpluff-great-league",
        "shadow-jumpluff-great-league",
        "dewgong-great-league",
    ]]
    groups, leftovers = _group_dives(dives)
    assert leftovers == []
    species = [g['species'] for g in groups]
    # One group per base species, sorted alphabetically.
    assert species == ["Dewgong", "Forretress", "Jumpluff", "Oinkologne",
                       "Tinkaton"]
    # Non-shadow before shadow.
    assert _labels(groups, "Forretress") == [
        "Bug Bite", "Volt Switch", "Shadow Bug Bite", "Shadow Volt Switch"]
    # League becomes the chip label when a group spans leagues.
    assert _labels(groups, "Tinkaton") == ["Great League", "Ultra League"]
    # Genderless sibling of a Female form is labeled Male, and ordered first.
    assert _labels(groups, "Oinkologne") == ["Male", "Female"]
    # Bare form labeled "Regular" alongside its Shadow sibling.
    assert _labels(groups, "Jumpluff") == ["Regular", "Shadow"]
    # Single-variant species is its own one-entry group.
    assert _labels(groups, "Dewgong") == ["Regular"]


def test_group_dives_keeps_unparseable_as_leftovers():
    dives = [_entry("forretress-bug-bite-great-league"),
             {'slug': 'weird-no-league', 'title': 'Weird', 'description': 'x',
              'curated': False}]
    groups, leftovers = _group_dives(dives)
    assert [g['species'] for g in groups] == ["Forretress"]
    assert [d['title'] for d in leftovers] == ["Weird"]


# ---- load_entries() dropped-page completeness guard (F1, 2026-06-27) ----

def _make_page(base, name, *, index=True, meta=None):
    """Create base/name/ with an optional index.html and optional meta.toml."""
    d = base / name
    d.mkdir(parents=True)
    if index:
        (d / 'index.html').write_text('<html><title>T</title></html>')
    if meta is not None:
        d.joinpath('meta.toml').write_text(meta)
    return d


def test_load_entries_flags_dropped_rendered_page(tmp_path):
    # A dir with a rendered index.html but a meta.toml missing the required
    # 'title' key is a real page made unreachable -> must be recorded so the
    # builder can hard-fail instead of silently shipping it.
    _make_page(tmp_path, 'bad-great-league',
               meta='description = "d"\nlanding = "index.html"\n')
    dropped = []
    entries = load_entries(tmp_path, dropped_pages=dropped)
    assert entries == []
    assert dropped == ['{}/bad-great-league'.format(tmp_path.name)]


def test_load_entries_does_not_flag_non_page_dir(tmp_path):
    # A dir with NO index.html is not a rendered page; skipping it is correct
    # and must NOT be recorded as a dropped page (no false positive).
    _make_page(tmp_path, 'assets', index=False)
    dropped = []
    entries = load_entries(tmp_path, dropped_pages=dropped)
    assert entries == []
    assert dropped == []


def test_load_entries_valid_page_not_dropped(tmp_path):
    # A well-formed page is returned and never recorded as dropped.
    _make_page(tmp_path, 'good-great-league',
               meta='title = "Good"\ndescription = "d"\nlanding = "index.html"\n')
    dropped = []
    entries = load_entries(tmp_path, dropped_pages=dropped)
    assert [e['slug'] for e in entries] == ['good-great-league']
    assert dropped == []
