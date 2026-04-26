"""
Regression tests for the opponents-file pool parser:
- ``_parse_opponent_pool_line`` (per-line format with optional pipe-delimited
  moveset overrides)
- ``parse_opponent_spec`` extension that consults the moveset-variant registry
  populated by ``register_opponent_variant``.

These tests exercise pure-Python pieces only; nothing here spins up a sim.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"

_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)


@pytest.fixture(autouse=True)
def _isolate_variant_registry():
    """Each test runs against a fresh registry so cross-test leaks don't hide bugs."""
    saved = dict(deep_dive._OPPONENT_VARIANT_REGISTRY)
    deep_dive._OPPONENT_VARIANT_REGISTRY.clear()
    yield
    deep_dive._OPPONENT_VARIANT_REGISTRY.clear()
    deep_dive._OPPONENT_VARIANT_REGISTRY.update(saved)


# ---- _parse_opponent_pool_line ------------------------------------------------

def test_bare_species_no_overrides():
    display, base, is_shadow, fast, charged = deep_dive._parse_opponent_pool_line(
        "Forretress")
    assert display == "Forretress"
    assert base == "Forretress"
    assert is_shadow is False
    assert fast is None
    assert charged is None


def test_bare_shadow_species():
    display, base, is_shadow, fast, charged = deep_dive._parse_opponent_pool_line(
        "Forretress (Shadow)")
    assert display == "Forretress (Shadow)"
    assert base == "Forretress"
    assert is_shadow is True
    assert fast is None
    assert charged is None


def test_fast_override_only():
    display, base, is_shadow, fast, charged = deep_dive._parse_opponent_pool_line(
        "Forretress | fast=BUG_BITE")
    assert display == "Forretress (Bug Bite)"
    assert base == "Forretress"
    assert is_shadow is False
    assert fast == "BUG_BITE"
    assert charged is None


def test_fast_override_on_shadow():
    display, base, is_shadow, fast, charged = deep_dive._parse_opponent_pool_line(
        "Forretress (Shadow) | fast=BUG_BITE")
    assert display == "Forretress (Shadow) (Bug Bite)"
    assert base == "Forretress"
    assert is_shadow is True
    assert fast == "BUG_BITE"
    assert charged is None


def test_charged_override_only():
    display, base, is_shadow, fast, charged = deep_dive._parse_opponent_pool_line(
        "Tinkaton | charged=PLAY_ROUGH,GIGATON_HAMMER")
    assert display == "Tinkaton (Play Rough+Gigaton Hammer)"
    assert base == "Tinkaton"
    assert is_shadow is False
    assert fast is None
    assert charged == ["PLAY_ROUGH", "GIGATON_HAMMER"]


def test_full_moveset_override():
    display, base, _, fast, charged = deep_dive._parse_opponent_pool_line(
        "Forretress | fast=BUG_BITE | charged=SAND_TOMB,ROCK_TOMB")
    assert display == "Forretress (Bug Bite / Sand Tomb+Rock Tomb)"
    assert base == "Forretress"
    assert fast == "BUG_BITE"
    assert charged == ["SAND_TOMB", "ROCK_TOMB"]


def test_whitespace_tolerated_around_separators():
    display, base, _, fast, charged = deep_dive._parse_opponent_pool_line(
        "Forretress  |  fast = BUG_BITE  ")
    assert base == "Forretress"
    assert fast == "BUG_BITE"
    assert charged is None
    assert display == "Forretress (Bug Bite)"


def test_galarian_form_in_species_name_preserved():
    """Species-form parens like '(Galarian)' must survive parsing — they're
    part of the canonical PvPoke speciesName, not a moveset variant."""
    display, base, is_shadow, fast, charged = deep_dive._parse_opponent_pool_line(
        "Corsola (Galarian)")
    assert display == "Corsola (Galarian)"
    assert base == "Corsola (Galarian)"
    assert is_shadow is False


def test_galarian_form_with_shadow():
    display, base, is_shadow, _, _ = deep_dive._parse_opponent_pool_line(
        "Stunfisk (Galarian) (Shadow)")
    assert display == "Stunfisk (Galarian) (Shadow)"
    assert base == "Stunfisk (Galarian)"
    assert is_shadow is True


def test_unknown_override_key_raises():
    with pytest.raises(ValueError, match="unknown override"):
        deep_dive._parse_opponent_pool_line("Forretress | shadow=true")


def test_missing_equals_raises():
    with pytest.raises(ValueError, match="missing '='"):
        deep_dive._parse_opponent_pool_line("Forretress | fast")


def test_empty_value_raises():
    with pytest.raises(ValueError, match="empty key or value"):
        deep_dive._parse_opponent_pool_line("Forretress | fast=")


def test_duplicate_override_key_raises():
    with pytest.raises(ValueError, match="duplicate override key"):
        deep_dive._parse_opponent_pool_line(
            "Forretress | fast=BUG_BITE | fast=VOLT_SWITCH")


# ---- parse_opponent_spec + variant registry ----------------------------------

def test_parse_opponent_spec_resolves_registered_variant():
    deep_dive.register_opponent_variant(
        "Forretress (Bug Bite)", "Forretress", is_shadow=False)
    base, variant, is_shadow = deep_dive.parse_opponent_spec("Forretress (Bug Bite)")
    assert base == "Forretress"
    assert variant == "moveset_variant"
    assert is_shadow is False


def test_parse_opponent_spec_resolves_registered_shadow_variant():
    deep_dive.register_opponent_variant(
        "Forretress (Shadow) (Bug Bite)", "Forretress", is_shadow=True)
    base, variant, is_shadow = deep_dive.parse_opponent_spec(
        "Forretress (Shadow) (Bug Bite)")
    assert base == "Forretress"
    assert variant == "moveset_variant"
    assert is_shadow is True


def test_parse_opponent_spec_unregistered_falls_through():
    """Unregistered names with parenthetical suffixes go through the legacy
    parser — vital so canonical PvPoke forms like '(Galarian)' still resolve."""
    base, variant, is_shadow = deep_dive.parse_opponent_spec("Corsola (Galarian)")
    assert base == "Corsola (Galarian)"
    assert variant is None
    assert is_shadow is False


def test_parse_opponent_spec_atk_weighted_unchanged():
    base, variant, is_shadow = deep_dive.parse_opponent_spec("Medicham (atk-weighted)")
    assert base == "Medicham"
    assert variant == "atk_weighted"
    assert is_shadow is False


def test_register_variant_idempotent():
    deep_dive.register_opponent_variant("F (X)", "F", is_shadow=False)
    deep_dive.register_opponent_variant("F (X)", "F", is_shadow=False)  # no-op


def test_register_variant_conflict_raises():
    deep_dive.register_opponent_variant("F (X)", "F", is_shadow=False)
    with pytest.raises(ValueError, match="already registered"):
        deep_dive.register_opponent_variant("F (X)", "G", is_shadow=False)
