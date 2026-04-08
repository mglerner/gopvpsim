"""Tests for gopvpsim.anchors — display-name derivation, resolution,
auto-anchor synthesis, IV tagging."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gopvpsim import anchors as A
from gopvpsim import thresholds as T


# ---------------------------------------------------------------------------
# Pure-function tests (no gamemaster needed)
# ---------------------------------------------------------------------------

class TestDeriveDisplayName:
    """Locks in the abbreviation rules used for HTML badge text."""

    @pytest.mark.parametrize("raw,expected", [
        # _bp_any → root
        ("cresselia_bp_any", "cresselia"),
        ("lickitung_bp_any", "lickitung"),
        ("umbreon_bp_any", "umbreon"),
        ("mirror_bp_any", "mirror"),
        # _bp_above_X → root↑X
        ("lickitung_bp_above_lurgan", "lickitung\u2191lurgan"),
        # cmp_vs_X → cmp:X
        ("cmp_vs_lurgan", "cmp:lurgan"),
        ("cmp_vs_cohort", "cmp:cohort"),
        # _bp_<other> → root:<other>  (Level 1 explicit fallback)
        ("lickitung_bp_counter_5", "lickitung:counter_5"),
        # auto_ prefix is stripped first, then rules re-applied
        ("auto_corviknight_bp_any", "corviknight"),
        ("auto_cmp_vs_cohort", "cmp:cohort"),
        ("auto_quagsire_shadow_bp_any", "quagsire_shadow"),
        # No matching pattern → unchanged
        ("custom_anchor", "custom_anchor"),
    ])
    def test_derives(self, raw, expected):
        assert A.derive_display_name(raw) == expected


class TestResolvedAnchorPasses:
    """Strict vs non-strict comparison semantics."""

    def test_strict_above(self):
        a = A.ResolvedAnchor(name="x", parent="x", kind="cmp",
                              threshold_atk=100.0, strict=True)
        assert a.passes(100.5) is True
        assert a.passes(100.0) is False  # tie fails strict
        assert a.passes(99.9) is False

    def test_non_strict_above(self):
        a = A.ResolvedAnchor(name="x", parent="x", kind="cmp",
                              threshold_atk=100.0, strict=False)
        assert a.passes(100.5) is True
        assert a.passes(100.0) is True   # tie passes non-strict
        assert a.passes(99.9) is False


class TestTagIv:
    """tag_iv groups passing anchors by parent."""

    def test_groups_by_parent(self):
        # Two anchors share a parent ("foo"), one is alone ("bar"). All
        # passable; all should appear in the result, grouped.
        anchors = [
            A.ResolvedAnchor(name="foo::a", parent="foo", kind="damage_breakpoint",
                              threshold_atk=100, strict=False, label="a"),
            A.ResolvedAnchor(name="foo::b", parent="foo", kind="damage_breakpoint",
                              threshold_atk=110, strict=False, label="b"),
            A.ResolvedAnchor(name="bar", parent="bar", kind="cmp",
                              threshold_atk=120, strict=False, label="bar"),
        ]
        tags = A.tag_iv(125.0, anchors)
        assert set(tags.keys()) == {"foo", "bar"}
        assert len(tags["foo"]) == 2
        assert len(tags["bar"]) == 1

    def test_excludes_failing(self):
        anchors = [
            A.ResolvedAnchor(name="foo::a", parent="foo", kind="damage_breakpoint",
                              threshold_atk=100, strict=False, label="a"),
            A.ResolvedAnchor(name="foo::b", parent="foo", kind="damage_breakpoint",
                              threshold_atk=130, strict=False, label="b"),
        ]
        # Atk 125 passes the 100 threshold but not the 130 — only 'a' is tagged.
        tags = A.tag_iv(125.0, anchors)
        assert "foo" in tags
        assert len(tags["foo"]) == 1
        assert tags["foo"][0].label == "a"

    def test_empty_when_nothing_passes(self):
        anchors = [
            A.ResolvedAnchor(name="x", parent="x", kind="cmp",
                              threshold_atk=200, strict=False),
        ]
        assert A.tag_iv(100.0, anchors) == {}


# ---------------------------------------------------------------------------
# build_auto_anchors gating (mostly pure — only the CMP path needs gamemaster)
# ---------------------------------------------------------------------------

class TestBuildAutoAnchorsGating:
    """Gating logic for the auto-fallback layer.

    The Atk path (one Level 3 BP anchor per opponent) doesn't touch the
    gamemaster. The CMP path computes effective atk from survivor IVs, which
    needs Pokemon.at_best_level — we test that with real data in
    TestBuildAutoAnchorsCmp below.
    """

    def test_neither_kind_existing_creates_both_bp_and_cmp_paths(self, monkeypatch):
        # Mock Pokemon.at_best_level so we don't need the gamemaster for the
        # CMP path; return a synthetic Pokemon with predictable atk.
        from gopvpsim import pokemon
        class FakeMon:
            def __init__(self, atk_iv):
                self.atk = 100.0 + atk_iv  # 100, 115, 130 etc

        def fake(species, a, d, s, league='great', shadow=False):
            return FakeMon(a)

        monkeypatch.setattr(pokemon.Pokemon, "at_best_level", fake)

        reg = A.build_auto_anchors(
            species="Annihilape",
            league="great",
            opponent_species=["Lickitung", "Cresselia"],
            survivor_ivs=[(15, 0, 0), (10, 0, 0), (5, 0, 0)],
            existing_anchor_kinds=set(),
        )
        sp = reg.species("Annihilape")
        lt = sp.leagues["Great"]
        anchor_names = set(lt.anchors.keys())
        # Expect BP anchors for both opponents + the cmp anchor
        assert "auto_lickitung_bp_any" in anchor_names
        assert "auto_cresselia_bp_any" in anchor_names
        assert "auto_cmp_vs_cohort" in anchor_names
        # And the synthetic cohort spread
        assert A.AUTO_COHORT_SPREAD_NAME in lt.spreads

    def test_existing_bp_suppresses_only_bp_path(self, monkeypatch):
        from gopvpsim import pokemon
        class FakeMon:
            atk = 115.0
        monkeypatch.setattr(pokemon.Pokemon, "at_best_level",
                             lambda *a, **k: FakeMon())

        reg = A.build_auto_anchors(
            species="Annihilape", league="great",
            opponent_species=["Lickitung"],
            survivor_ivs=[(15, 0, 0)],
            existing_anchor_kinds={"damage_breakpoint"},  # has BPs
        )
        sp = reg.species("Annihilape")
        lt = sp.leagues["Great"]
        anchor_names = set(lt.anchors.keys())
        # No auto BPs (suppressed by existing kind), but auto CMP fired
        assert "auto_lickitung_bp_any" not in anchor_names
        assert "auto_cmp_vs_cohort" in anchor_names

    def test_existing_cmp_suppresses_only_cmp_path(self):
        # No survivors needed for the BP-only path (gamemaster-free)
        reg = A.build_auto_anchors(
            species="Annihilape", league="great",
            opponent_species=["Lickitung", "Quagsire"],
            survivor_ivs=None,
            existing_anchor_kinds={"cmp"},
        )
        sp = reg.species("Annihilape")
        lt = sp.leagues["Great"]
        anchor_names = set(lt.anchors.keys())
        assert "auto_lickitung_bp_any" in anchor_names
        assert "auto_quagsire_bp_any" in anchor_names
        assert "auto_cmp_vs_cohort" not in anchor_names

    def test_both_kinds_existing_returns_empty_registry(self):
        reg = A.build_auto_anchors(
            species="Annihilape", league="great",
            opponent_species=["Lickitung"],
            survivor_ivs=[(15, 0, 0)],
            existing_anchor_kinds={"damage_breakpoint", "cmp"},
        )
        # Empty by_species when nothing was added
        assert reg.by_species == {}

    def test_no_opponents_skips_bp_path(self):
        reg = A.build_auto_anchors(
            species="Annihilape", league="great",
            opponent_species=[],
            survivor_ivs=None,
            existing_anchor_kinds=set(),
        )
        # Empty: no opponents → no BPs, no survivors → no CMP
        assert reg.by_species == {}

    def test_dedupes_repeated_opponents(self):
        reg = A.build_auto_anchors(
            species="Annihilape", league="great",
            opponent_species=["Lickitung", "Lickitung", "Cresselia"],
            existing_anchor_kinds=set(),
        )
        sp = reg.species("Annihilape")
        lt = sp.leagues["Great"]
        # Lickitung gets one anchor, not two
        assert "auto_lickitung_bp_any" in lt.anchors
        assert "auto_cresselia_bp_any" in lt.anchors
        assert len(lt.anchors) == 2

    def test_opponent_name_with_spaces_and_parens(self):
        reg = A.build_auto_anchors(
            species="Annihilape", league="great",
            opponent_species=["Quagsire (Shadow)"],
            existing_anchor_kinds=set(),
        )
        sp = reg.species("Annihilape")
        lt = sp.leagues["Great"]
        # Slug strips parens and lowercases
        assert "auto_quagsire_shadow_bp_any" in lt.anchors


class TestBuildAutoAnchorsCmpThreshold:
    """The CMP cohort uses the 75th percentile of effective atk.

    This is the focal-in-own-cohort fix: 'strictly beat max' is unreachable
    when the focal IV is itself a member of the cohort, so we use top-quartile
    threshold + non-strict comparison instead.
    """

    def test_cmp_threshold_is_75th_percentile_non_strict(self, monkeypatch):
        from gopvpsim import pokemon
        # Build 10 fake survivors with atk values 100..109
        fake_atks = list(range(100, 110))

        class FakeMon:
            def __init__(self, atk):
                self.atk = float(atk)

        # Map (a_iv) → distinct atk so dedup keeps all 10
        ivs = [(i, 0, 0) for i in range(10)]
        atk_by_a = dict(zip(range(10), fake_atks))

        def fake(species, a, d, s, league='great', shadow=False):
            return FakeMon(atk_by_a[a])

        monkeypatch.setattr(pokemon.Pokemon, "at_best_level", fake)

        reg = A.build_auto_anchors(
            species="Annihilape", league="great",
            opponent_species=[],   # skip BP path
            survivor_ivs=ivs,
            existing_anchor_kinds=set(),
        )
        sp = reg.species("Annihilape")
        lt = sp.leagues["Great"]
        # Anchor exists
        assert "auto_cmp_vs_cohort" in lt.anchors
        anchor = lt.anchors["auto_cmp_vs_cohort"]
        assert isinstance(anchor, T.CmpAnchor)
        assert anchor.strict is False  # CRITICAL: focal-in-own-cohort fix

        # Underlying spread is StatCutoffSpread, not IvListSpread
        spread = lt.spreads[A.AUTO_COHORT_SPREAD_NAME]
        assert isinstance(spread, T.StatCutoffSpread)

        # 75th percentile of [100..109] (sorted): index = int(0.75 * 10) = 7,
        # so threshold = 107.0
        assert spread.attack == 107.0


# ---------------------------------------------------------------------------
# Integration: real Annihilape TOML, real gamemaster
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def annihilape_registry():
    p = REPO_ROOT / "thresholds" / "annihilape.toml"
    if not p.exists():
        pytest.skip("thresholds/annihilape.toml not present")
    return T.load_toml(p)


@pytest.fixture
def annihilape_focal_context():
    """Build (focal_moves, focal_types) for an Annihilape Low Kick / Rage Fist /
    Close Combat moveset using the real gamemaster."""
    from gopvpsim.moves import get_moves
    from gopvpsim.data import load_gamemaster, parse_types
    fast, charged = get_moves()
    gm = load_gamemaster()
    entry = next(m for m in gm['pokemon'] if m['speciesName'] == 'Annihilape')
    types = parse_types(entry)
    moves = [fast['LOW_KICK'], charged['RAGE_FIST'], charged['CLOSE_COMBAT']]
    return moves, types


class TestResolveAnchorsAnnihilape:
    """End-to-end resolution against the committed Annihilape TOML."""

    def test_cmp_vs_lurgan_resolves_to_max_lurgan_atk(
        self, annihilape_registry, annihilape_focal_context,
    ):
        moves, types = annihilape_focal_context
        resolved = A.resolve_anchors(
            annihilape_registry, "Annihilape", "great",
            moves, types, atk_min=115.0, atk_max=132.0,
        )
        cmp_anchors = [r for r in resolved if r.kind == "cmp"]
        cmp_lurgan = [r for r in cmp_anchors if r.parent == "cmp_vs_lurgan"]
        assert len(cmp_lurgan) == 1
        # Lurgan max atk is around 127.78 (max-atk Lurgan IV at L17)
        assert 127.0 < cmp_lurgan[0].threshold_atk < 128.5
        assert cmp_lurgan[0].strict is True   # explicit anchors stay strict

    def test_lickitung_bp_above_lurgan_resolves_to_close_combat_step(
        self, annihilape_registry, annihilape_focal_context,
    ):
        """Level 2 anchor: smallest atk > 127.2 at which any focal move's
        damage to Lickitung steps up."""
        moves, types = annihilape_focal_context
        resolved = A.resolve_anchors(
            annihilape_registry, "Annihilape", "great",
            moves, types, atk_min=115.0, atk_max=132.0,
        )
        l2 = [r for r in resolved if r.parent == "lickitung_bp_above_lurgan"]
        # Level 2 produces exactly one ResolvedAnchor (the next BP)
        assert len(l2) == 1
        # Threshold is strictly above the 127.2 floor
        assert l2[0].threshold_atk > 127.2
        # Per the previous smoke test it lands on close_combat → 125 dmg
        assert l2[0].move_id == "CLOSE_COMBAT"

    def test_level_3_anchor_expands_to_multiple_sub_anchors(
        self, annihilape_registry, annihilape_focal_context,
    ):
        moves, types = annihilape_focal_context
        resolved = A.resolve_anchors(
            annihilape_registry, "Annihilape", "great",
            moves, types, atk_min=115.0, atk_max=132.0,
        )
        # lickitung_bp_any is a Level 3 anchor → multiple sub-anchors
        ltung_subs = [r for r in resolved if r.parent == "lickitung_bp_any"]
        assert len(ltung_subs) > 1
        # All share the parent name
        assert all(r.parent == "lickitung_bp_any" for r in ltung_subs)
        # All share the parent display name (derived from auto_-stripped name)
        assert all(r.parent_display_name == "lickitung" for r in ltung_subs)

    def test_resolved_anchors_have_display_names(
        self, annihilape_registry, annihilape_focal_context,
    ):
        moves, types = annihilape_focal_context
        resolved = A.resolve_anchors(
            annihilape_registry, "Annihilape", "great",
            moves, types, atk_min=115.0, atk_max=132.0,
        )
        # Every resolved anchor has a non-empty parent_display_name
        for r in resolved:
            assert r.parent_display_name, (
                f"anchor {r.name} (parent {r.parent}) has empty display name"
            )

    def test_high_atk_iv_passes_cmp_vs_lurgan(
        self, annihilape_registry, annihilape_focal_context,
    ):
        """A 15/x/x Annihilape (atk 129.44) should beat the Lurgan max (~127.78)."""
        from gopvpsim.pokemon import Pokemon
        moves, types = annihilape_focal_context
        resolved = A.resolve_anchors(
            annihilape_registry, "Annihilape", "great",
            moves, types, atk_min=115.0, atk_max=132.0,
        )
        focal = Pokemon.at_best_level("Annihilape", 15, 2, 4, league="great")
        tags = A.tag_iv(focal.atk, resolved)
        # cmp_vs_lurgan is one of the parents tagged
        assert "cmp_vs_lurgan" in tags

    def test_low_atk_iv_fails_cmp_vs_lurgan(
        self, annihilape_registry, annihilape_focal_context,
    ):
        """A 0/x/x Annihilape (atk ~124) should NOT beat the Lurgan max."""
        from gopvpsim.pokemon import Pokemon
        moves, types = annihilape_focal_context
        resolved = A.resolve_anchors(
            annihilape_registry, "Annihilape", "great",
            moves, types, atk_min=115.0, atk_max=132.0,
        )
        focal = Pokemon.at_best_level("Annihilape", 0, 15, 15, league="great")
        tags = A.tag_iv(focal.atk, resolved)
        assert "cmp_vs_lurgan" not in tags

    def test_unknown_species_returns_empty(self, annihilape_registry,
                                            annihilape_focal_context):
        moves, types = annihilape_focal_context
        resolved = A.resolve_anchors(
            annihilape_registry, "NotARealSpecies", "great",
            moves, types, atk_min=100.0, atk_max=140.0,
        )
        assert resolved == []
