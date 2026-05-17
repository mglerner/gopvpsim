"""Tests for ``scripts/build_website_index._slug_to_pretty_title``.

The site-index card titles derive from dive directory slugs, so a
regression in the slug→title rewrite would break the public-facing
landing page silently. Mercuryish flagged the original "Forretress
(Shadow)" → "Shadow Forretress" rewrite (G4); these tests pin the
output format.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from build_website_index import _slug_to_pretty_title  # noqa: E402


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
