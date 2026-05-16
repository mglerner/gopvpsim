"""Tests for ``gopvpsim.display.pretty_species``."""
from __future__ import annotations

import pytest

from gopvpsim.display import pretty_species


# ---------------------------------------------------------------------------
# Cases that don't depend on the gamemaster (no female-sibling check
# applies)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    # Bare species without sibling forms — pass through unchanged.
    ("Forretress",        "Forretress"),
    ("Lapras",            "Lapras"),
    # Single regional/shadow modifier — hoisted to prefix.
    ("Forretress (Shadow)",        "Shadow Forretress"),
    ("Corsola (Galarian)",         "Galarian Corsola"),
    ("Ninetales (Alolan)",         "Alolan Ninetales"),
    ("Stunfisk (Galarian)",        "Galarian Stunfisk"),
    ("Moltres (Galarian)",         "Galarian Moltres"),
    # Two-modifier stack — Shadow always outermost.
    ("Weezing (Galarian) (Shadow)", "Shadow Galarian Weezing"),
    # In-battle form changes — NOT touched (Shield/Blade/Busted/etc.
    # are sub-form tags, not regional flavors).
    ("Aegislash (Shield)",        "Aegislash (Shield)"),
    ("Aegislash (Blade)",         "Aegislash (Blade)"),
    ("Mimikyu (Busted)",          "Mimikyu (Busted)"),
    ("Mimikyu (Disguised)",       "Mimikyu (Disguised)"),
    ("Pumpkaboo (Super)",         "Pumpkaboo (Super)"),
    ("Gourgeist (Super)",         "Gourgeist (Super)"),
    # Shadow + in-battle form: Shadow strips off, sub-form parenthetical
    # stays. (Hypothetical — no shadow Aegislash exists today, but the
    # behavior should be correct if Niantic ever ships one.)
    ("Aegislash (Shadow)",        "Shadow Aegislash"),
])
def test_pretty_species_basic(name, expected):
    assert pretty_species(name) == expected


# ---------------------------------------------------------------------------
# Idempotence: pretty_species(pretty_species(x)) == pretty_species(x).
# The output never has a trailing regional parenthetical for the
# strip loop to bite on a second time.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Forretress",
    "Forretress (Shadow)",
    "Corsola (Galarian)",
    "Weezing (Galarian) (Shadow)",
    "Aegislash (Shield)",
    "Mimikyu (Busted)",
    "Oinkologne",
    "Oinkologne (Female)",
])
def test_pretty_species_idempotent(name):
    once = pretty_species(name)
    twice = pretty_species(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Gender disambiguation — depends on what's in the live gamemaster.
# Oinkologne has a (Female) sibling form per PvPoke's data; the bare
# "Oinkologne" should pick up a (Male) suffix.
# ---------------------------------------------------------------------------

def test_oinkologne_male_gets_male_suffix():
    """The bare 'Oinkologne' (Male form) has a (Female) sibling in
    the gamemaster, so it should display as 'Oinkologne (Male)' to
    read symmetrically with 'Oinkologne (Female)'."""
    assert pretty_species("Oinkologne") == "Oinkologne (Male)"


def test_oinkologne_female_is_unchanged():
    """The Female form already carries the qualifier; pretty_species
    should not touch it."""
    assert pretty_species("Oinkologne (Female)") == "Oinkologne (Female)"


def test_oinkologne_male_idempotent_after_suffix():
    """Calling pretty_species twice on the bare Male name produces the
    same '... (Male)' result, not '... (Male) (Male)'."""
    once = pretty_species("Oinkologne")
    twice = pretty_species(once)
    assert once == twice == "Oinkologne (Male)"


# ---------------------------------------------------------------------------
# Species without female sibling forms must NOT pick up the (Male)
# suffix even though the female-sibling check is a positive filter.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Forretress",
    "Lapras",
    "Tinkaton",
    "Aegislash (Shield)",
    "Aegislash (Blade)",
])
def test_no_male_suffix_without_female_sibling(name):
    """Species with no Female sibling should never gain a (Male) tag.
    This catches regressions where the female-sibling set is populated
    incorrectly (e.g. matching on any '(' in the name)."""
    assert "(Male)" not in pretty_species(name)
