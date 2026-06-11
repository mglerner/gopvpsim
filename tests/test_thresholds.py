"""Tests for gopvpsim.thresholds — TOML schema, legacy JSON, anchor parsing."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gopvpsim import thresholds as th


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Spread parsing
# ---------------------------------------------------------------------------

class TestSpreads:
    def test_stat_cutoff_spread(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.high_atk]
            attack = 127.0
            defense = 103.0
            stamina = 0
            description = "test"
        """)
        reg = th.load_toml(p)
        sp = reg.get_spread("Annihilape", "Great", "high_atk")
        assert isinstance(sp, th.StatCutoffSpread)
        assert sp.attack == 127.0
        assert sp.defense == 103.0
        assert sp.stamina == 0
        assert sp.description == "test"
        # Membership
        assert sp.contains(atk=130, def_=105, hp=130) is True
        assert sp.contains(atk=126, def_=105, hp=130) is False  # atk too low
        assert sp.contains(atk=130, def_=100, hp=130) is False  # def too low
        assert sp.contains(atk=130, def_=105, hp=0) is True     # sta=0 = no constraint

    def test_iv_list_spread(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.lurgan_ape]
            ivs = [[11, 10, 2], [15, 12, 5], [15, 15, 0]]
        """)
        reg = th.load_toml(p)
        sp = reg.get_spread("Annihilape", "Great", "lurgan_ape")
        assert isinstance(sp, th.IvListSpread)
        assert len(sp.ivs) == 3
        assert sp.contains(15, 12, 5) is True
        assert sp.contains(15, 12, 4) is False

    def test_spread_mutual_exclusion_errors(self, tmp_path):
        """A spread with BOTH ivs and stat-cutoff fields must raise."""
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.bad]
            attack = 127.0
            ivs = [[15, 15, 15]]
        """)
        with pytest.raises(th.ThresholdError, match="either 'ivs' or stat-cutoff"):
            th.load_toml(p)

    def test_spread_empty_errors(self, tmp_path):
        """A spread with NEITHER ivs nor stat-cutoff must raise."""
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.bad]
            description = "nothing"
        """)
        with pytest.raises(th.ThresholdError, match="either 'ivs' or stat-cutoff"):
            th.load_toml(p)

    def test_iv_out_of_range_errors(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.bad]
            ivs = [[16, 0, 0]]
        """)
        with pytest.raises(th.ThresholdError, match="IV component"):
            th.load_toml(p)


# ---------------------------------------------------------------------------
# Anchor parsing
# ---------------------------------------------------------------------------

class TestAnchors:
    def test_cmp_anchor(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.lurgan]
            ivs = [[15, 12, 0]]

            [Annihilape.Great.anchors.cmp_vs_lurgan]
            kind = "cmp"
            spread = "lurgan"
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "cmp_vs_lurgan")
        assert isinstance(a, th.CmpAnchor)
        assert a.spread == "lurgan"
        assert a.strict is True  # default

    def test_cmp_anchor_non_strict(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.lurgan]
            ivs = [[15, 12, 0]]

            [Annihilape.Great.anchors.cmp_vs_lurgan]
            kind = "cmp"
            spread = "lurgan"
            strict = false
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "cmp_vs_lurgan")
        assert a.strict is False

    def test_bp_level_1(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_counter_5]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            move = "COUNTER"
            deals_at_least = 5
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_counter_5")
        assert isinstance(a, th.DamageBreakpointAnchor)
        assert a.level == 1
        assert a.move == "COUNTER"
        assert a.deals_at_least == 5

    def test_bp_level_2(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_above]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            above_atk = 127.23
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_above")
        assert a.level == 2
        assert a.above_atk == 127.23

    def test_bp_level_3_bare(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_any]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_any")
        assert a.level == 3
        assert a.moves is None

    def test_bp_level_3_with_moves_filter(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_any]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            moves = ["COUNTER", "LOW_KICK"]
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_any")
        assert a.level == 3
        assert a.moves == ("COUNTER", "LOW_KICK")

    def test_bp_level_1_missing_move_errors(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            deals_at_least = 5
        """)
        with pytest.raises(th.ThresholdError, match="'deals_at_least' .* no 'move'"):
            th.load_toml(p)

    def test_bp_level_conflict_errors(self, tmp_path):
        """Can't specify both deals_at_least (L1) and above_atk (L2)."""
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            move = "COUNTER"
            deals_at_least = 5
            above_atk = 127.23
        """)
        with pytest.raises(th.ThresholdError, match="cannot specify both"):
            th.load_toml(p)

    def test_bp_moves_filter_invalid_on_level_1(self, tmp_path):
        """The 'moves' filter is only valid on Level 3."""
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            move = "COUNTER"
            deals_at_least = 5
            moves = ["LOW_KICK"]
        """)
        with pytest.raises(th.ThresholdError, match="'moves' filter"):
            th.load_toml(p)

    def test_unknown_anchor_kind_errors(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "stat_product"
        """)
        with pytest.raises(th.ThresholdError, match="unknown or missing kind"):
            th.load_toml(p)

    def test_opponent_ref_def_variants(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.a]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            opponent_ivs = [0, 15, 15]

            [Annihilape.Great.anchors.b]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            opponent_spread = "some_spread"
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "a")
        assert a.opponent_ivs == (0, 15, 15)
        assert a.opponent_spread is None
        b = reg.get_anchor("Annihilape", "Great", "b")
        assert b.opponent_spread == "some_spread"
        assert b.opponent_ivs is None

    # ---- bulkpoint anchors ----

    def test_blkp_level_1(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_body_slam_at_most_5]
            kind = "bulkpoint"
            opponent = "Lickitung"
            move = "BODY_SLAM"
            takes_at_most = 5
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_body_slam_at_most_5")
        assert isinstance(a, th.BulkpointAnchor)
        assert a.kind == "bulkpoint"
        assert a.level == 1
        assert a.move == "BODY_SLAM"
        assert a.takes_at_most == 5

    def test_blkp_level_2(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_above_lurgan_def]
            kind = "bulkpoint"
            opponent = "Lickitung"
            above_def = 102.9
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_above_lurgan_def")
        assert isinstance(a, th.BulkpointAnchor)
        assert a.level == 2
        assert a.above_def == 102.9

    def test_blkp_level_3_bare(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_blkp_any]
            kind = "bulkpoint"
            opponent = "Lickitung"
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_blkp_any")
        assert a.level == 3
        assert a.moves is None

    def test_blkp_level_3_with_moves_filter(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.ltung_blkp_charged]
            kind = "bulkpoint"
            opponent = "Lickitung"
            moves = ["BODY_SLAM", "POWER_WHIP"]
        """)
        reg = th.load_toml(p)
        a = reg.get_anchor("Annihilape", "Great", "ltung_blkp_charged")
        assert a.level == 3
        assert a.moves == ("BODY_SLAM", "POWER_WHIP")

    def test_blkp_level_1_missing_move_errors(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "bulkpoint"
            opponent = "Lickitung"
            takes_at_most = 5
        """)
        with pytest.raises(th.ThresholdError, match="'takes_at_most' .* no 'move'"):
            th.load_toml(p)

    def test_blkp_level_conflict_errors(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "bulkpoint"
            opponent = "Lickitung"
            move = "BODY_SLAM"
            takes_at_most = 5
            above_def = 100.0
        """)
        with pytest.raises(th.ThresholdError, match="cannot specify both"):
            th.load_toml(p)

    def test_blkp_moves_filter_invalid_on_level_1(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "bulkpoint"
            opponent = "Lickitung"
            move = "BODY_SLAM"
            takes_at_most = 5
            moves = ["POWER_WHIP"]
        """)
        with pytest.raises(th.ThresholdError, match="'moves' filter"):
            th.load_toml(p)

    def test_blkp_opponent_ref_mutual_exclusion(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "bulkpoint"
            opponent = "Lickitung"
            opponent_ivs = [15, 15, 15]
            opponent_spread = "foo"
        """)
        with pytest.raises(th.ThresholdError, match="cannot specify both"):
            th.load_toml(p)

    def test_opponent_ref_def_mutual_exclusion(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.anchors.bad]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
            opponent_ivs = [0, 15, 15]
            opponent_spread = "foo"
        """)
        with pytest.raises(th.ThresholdError, match="cannot specify both"):
            th.load_toml(p)


# ---------------------------------------------------------------------------
# Shared (cross-species) resolution
# ---------------------------------------------------------------------------

class TestSharedResolution:
    def test_shared_spread_lookup(self, tmp_path):
        p = _write(tmp_path, "shared.toml", """
            [shared.Great.spreads.lickitung_default]
            ivs = [[0, 15, 15]]

            [Annihilape.Great.anchors.ltung_any]
            kind = "damage_breakpoint"
            opponent = "Lickitung"
        """)
        reg = th.load_toml(p)
        # Anchor is on Annihilape; spread is on shared.
        sp = reg.get_spread("Annihilape", "Great", "lickitung_default")
        assert sp is not None
        assert isinstance(sp, th.IvListSpread)

    def test_species_wins_on_collision(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [shared.Great.spreads.foo]
            attack = 100.0

            [Annihilape.Great.spreads.foo]
            attack = 127.0
        """)
        reg = th.load_toml(p)
        sp = reg.get_spread("Annihilape", "Great", "foo")
        assert sp.attack == 127.0  # species wins
        # Lookup on a different species falls back to shared
        sp2 = reg.get_spread("Tinkaton", "Great", "foo")
        assert sp2.attack == 100.0


# ---------------------------------------------------------------------------
# Registry merging
# ---------------------------------------------------------------------------

class TestMerge:
    def test_overlay_wins_on_collision(self, tmp_path):
        base = _write(tmp_path, "base.toml", """
            [Annihilape.Great.spreads.foo]
            attack = 100.0
            [Annihilape.Great.spreads.bar]
            attack = 110.0
        """)
        overlay = _write(tmp_path, "overlay.toml", """
            [Annihilape.Great.spreads.foo]
            attack = 127.0
            [Annihilape.Great.spreads.baz]
            attack = 130.0
        """)
        reg = th.load_toml(base).merge(th.load_toml(overlay))
        assert reg.get_spread("Annihilape", "Great", "foo").attack == 127.0  # overlay won
        assert reg.get_spread("Annihilape", "Great", "bar").attack == 110.0  # preserved
        assert reg.get_spread("Annihilape", "Great", "baz").attack == 130.0  # new

    def test_overlay_does_not_clobber_other_leagues(self, tmp_path):
        base = _write(tmp_path, "base.toml", """
            [Annihilape.Great.spreads.foo]
            attack = 100.0
            [Annihilape.Ultra.spreads.foo]
            attack = 200.0
        """)
        overlay = _write(tmp_path, "overlay.toml", """
            [Annihilape.Great.spreads.foo]
            attack = 127.0
        """)
        reg = th.load_toml(base).merge(th.load_toml(overlay))
        assert reg.get_spread("Annihilape", "Great", "foo").attack == 127.0
        assert reg.get_spread("Annihilape", "Ultra", "foo").attack == 200.0


# ---------------------------------------------------------------------------
# Legacy JSON support
# ---------------------------------------------------------------------------

class TestLegacyJson:
    def test_legacy_json_loads(self, tmp_path):
        p = tmp_path / "annihilape.json"
        p.write_text("""
            {
                "High Atk": {"attack": 125.0, "defense": 103.0, "stamina": 0},
                "Balanced": {"attack": 122.0, "defense": 106.0, "stamina": 136}
            }
        """)
        reg = th.load_legacy_json(p, species="Annihilape")
        sp = reg.get_spread("Annihilape", "Great", "High Atk")
        assert isinstance(sp, th.StatCutoffSpread)
        assert sp.attack == 125.0
        assert sp.defense == 103.0

    def test_legacy_json_missing_key_errors(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text('{"x": {"attack": 125.0, "defense": 103.0}}')  # no stamina
        with pytest.raises(th.ThresholdError, match="missing key 'stamina'"):
            th.load_legacy_json(p, species="Annihilape")

    def test_load_file_auto_detects(self, tmp_path):
        toml_p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.x]
            attack = 127.0
        """)
        json_p = tmp_path / "b.json"
        json_p.write_text('{"x": {"attack": 127.0, "defense": 0, "stamina": 0}}')

        reg_toml = th.load_file(toml_p)
        reg_json = th.load_file(json_p, species="Annihilape")
        assert reg_toml.get_spread("Annihilape", "Great", "x").attack == 127.0
        assert reg_json.get_spread("Annihilape", "Great", "x").attack == 127.0

    def test_load_file_json_without_species_errors(self, tmp_path):
        p = tmp_path / "b.json"
        p.write_text('{}')
        with pytest.raises(th.ThresholdError, match="requires an explicit species"):
            th.load_file(p)


# ---------------------------------------------------------------------------
# Legacy dict adapter
# ---------------------------------------------------------------------------

class TestLegacyAdapter:
    def test_as_legacy_dict_skips_iv_lists(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
            [Annihilape.Great.spreads.high_atk]
            attack = 127.0

            [Annihilape.Great.spreads.lurgan]
            ivs = [[15, 12, 0]]
        """)
        reg = th.load_toml(p)
        legacy = th.as_legacy_dict(reg, "Annihilape", "Great")
        assert "high_atk" in legacy
        assert "lurgan" not in legacy  # IV-list spreads excluded
        assert legacy["high_atk"]["attack"] == 127.0


# ---------------------------------------------------------------------------
# Inline --anchor parser
# ---------------------------------------------------------------------------

class TestInlineAnchor:
    def test_parse_cmp_with_ivs(self):
        name, anchor = th.parse_inline_anchor(
            "cmp_vs_v2:kind=cmp,ivs=15/3/2;15/2/4;15/5/0"
        )
        assert name == "cmp_vs_v2"
        assert isinstance(anchor, th.CmpAnchor)
        assert anchor._inline_ivs == [(15, 3, 2), (15, 2, 4), (15, 5, 0)]

    def test_parse_bp_level_1(self):
        name, anchor = th.parse_inline_anchor(
            "ltung:kind=damage_breakpoint,opponent=Lickitung,move=COUNTER,deals_at_least=5"
        )
        assert name == "ltung"
        assert isinstance(anchor, th.DamageBreakpointAnchor)
        assert anchor.level == 1
        assert anchor.move == "COUNTER"
        assert anchor.deals_at_least == 5

    def test_parse_bp_level_2(self):
        name, anchor = th.parse_inline_anchor(
            "above:kind=damage_breakpoint,opponent=Lickitung,above_atk=127.23"
        )
        assert anchor.level == 2
        assert anchor.above_atk == 127.23

    def test_parse_bp_level_3_with_moves(self):
        name, anchor = th.parse_inline_anchor(
            "any:kind=damage_breakpoint,opponent=Lickitung,moves=COUNTER;LOW_KICK"
        )
        assert anchor.level == 3
        assert anchor.moves == ("COUNTER", "LOW_KICK")

    def test_missing_name_errors(self):
        with pytest.raises(th.ThresholdError, match="missing name"):
            th.parse_inline_anchor("kind=cmp,spread=foo")

    def test_missing_kind_errors(self):
        with pytest.raises(th.ThresholdError, match="missing 'kind'"):
            th.parse_inline_anchor("foo:spread=bar")

    def test_bad_iv_entry_errors(self):
        with pytest.raises(th.ThresholdError, match="bad ivs entry"):
            th.parse_inline_anchor("foo:kind=cmp,ivs=15/3")


# ---------------------------------------------------------------------------
# Real files load without error
# ---------------------------------------------------------------------------

class TestRepoFiles:
    def test_annihilape_toml_loads(self):
        repo_root = Path(__file__).resolve().parent.parent
        p = repo_root / "thresholds" / "annihilape.toml"
        if not p.exists():
            pytest.skip("thresholds/annihilape.toml not present")
        reg = th.load_toml(p)
        sp = reg.get_spread("Annihilape", "Great", "lurgan_ape")
        assert isinstance(sp, th.IvListSpread)
        assert len(sp.ivs) == 27
        a = reg.get_anchor("Annihilape", "Great", "cmp_vs_lurgan")
        assert isinstance(a, th.CmpAnchor)
        a2 = reg.get_anchor("Annihilape", "Great", "lickitung_brkp_above_lurgan")
        assert a2.level == 2
        a3 = reg.get_anchor("Annihilape", "Great", "cresselia_brkp_any")
        assert a3.level == 3

    def test_tinkaton_toml_loads(self):
        repo_root = Path(__file__).resolve().parent.parent
        p = repo_root / "thresholds" / "tinkaton.toml"
        if not p.exists():
            pytest.skip("thresholds/tinkaton.toml not present")
        reg = th.load_toml(p)
        sp = reg.get_spread("Tinkaton", "Great", "GH Great")
        assert isinstance(sp, th.StatCutoffSpread)
        assert sp.defense == 143.03


class TestLeagueKeyCaseNormalization:
    """2026-06-11 review finding L10: '[Tinkaton.great]' (lowercase) parsed
    fine and then silently never resolved — the resolver only queries the
    canonical capitalization. Case-variant known-league keys now normalize
    on load."""

    def test_lowercase_league_key_normalizes(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
[Testmon.great.spreads.x]
attack = 120.0
""")
        reg = th.load_toml(p)
        sp = reg.species("Testmon")
        assert "Great" in sp.leagues
        assert "great" not in sp.leagues

    def test_canonical_key_unchanged(self, tmp_path):
        p = _write(tmp_path, "a.toml", """
[Testmon.Great.spreads.x]
attack = 120.0
""")
        reg = th.load_toml(p)
        assert "Great" in reg.species("Testmon").leagues
