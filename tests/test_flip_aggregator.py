"""
Tests for ``_aggregate_flips_by_anchor`` and ``_render_anchor_flip_bullets``
in ``scripts/deep_dive.py``.

These helpers produce RyanSwag-style "X Atk for Y vs Z (2v2, 1v1, 0v0)"
bullets from a deep-dive's score grid plus the resolved-anchor list. The
tests use synthetic score arrays and hand-built ``ResolvedAnchor`` objects
so they have no dependency on the gamemaster or on a real deep-dive run.

The script lives in ``scripts/`` (not the gopvpsim package), so we import
it via ``importlib`` — same pattern as ``test_format_md.py``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from gopvpsim.anchors import ResolvedAnchor

REPO_ROOT = Path(__file__).resolve().parents[1]
DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"

_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)


# ---------------------------------------------------------------------------
# Helpers to build synthetic test fixtures
# ---------------------------------------------------------------------------

def _make_data_obj(iv_atk_def_pairs):
    """Build a minimal data_obj with just the fields the aggregator reads."""
    return {
        'ivAtk': [a for a, _ in iv_atk_def_pairs],
        'ivDef': [d for _, d in iv_atk_def_pairs],
    }


def _make_scores(nIvs, nS, nO, fill):
    """Build a flat score array using ``fill(iv, si, oi) -> score``."""
    out = [0.0] * (nIvs * nS * nO)
    for iv in range(nIvs):
        for si in range(nS):
            for oi in range(nO):
                out[iv * nS * nO + si * nO + oi] = fill(iv, si, oi)
    return out


# ---------------------------------------------------------------------------
# _aggregate_flips_by_anchor
# ---------------------------------------------------------------------------

class TestAggregateFlipsByAnchor:
    """The aggregator should detect shield scenarios where an anchor
    cleanly partitions wins from losses against its named opponent."""

    def test_clean_atk_partition_one_scenario(self):
        # 4 IVs: half clear an atk threshold of 130, half don't.
        # Vs opponent 0: passing IVs win in scenario 0, failing IVs lose.
        # No other matchups flip cleanly.
        ivs = [(125, 100), (128, 100), (131, 100), (134, 100)]
        data_obj = _make_data_obj(ivs)
        opponents = ['Annihilape']
        scenarios = [(2, 2), (1, 1), (0, 0)]

        def fill(iv, si, oi):
            atk = data_obj['ivAtk'][iv]
            if si == 0:
                return 700 if atk >= 130 else 300
            return 500  # tie elsewhere — no flip signal

        scores = _make_scores(4, 3, 1, fill)
        anchor = ResolvedAnchor(
            name='lickitung_brkp_any',
            parent_display_name='lickitung',
            parent='lickitung_brkp_any',
            kind='damage_breakpoint',
            threshold_value=130.0,
            target_stat='atk',
            opponent='Annihilape',
        )

        records = deep_dive._aggregate_flips_by_anchor(
            scores, 4, 3, 1, [anchor], data_obj, scenarios, opponents,
        )

        assert len(records) == 1
        assert records[0]['anchor'] is anchor
        assert records[0]['opponent'] == 'Annihilape'
        assert records[0]['scenarios'] == [(2, 2)]
        assert records[0]['direction'] == 'gain'

    def test_multiple_scenarios_one_anchor(self):
        # Same setup but the partition is clean in 2 of 3 scenarios.
        ivs = [(125, 100), (128, 100), (131, 100), (134, 100)]
        data_obj = _make_data_obj(ivs)
        opponents = ['Mirror']
        scenarios = [(2, 2), (2, 1), (0, 0)]

        def fill(iv, si, oi):
            atk = data_obj['ivAtk'][iv]
            if si in (0, 1):
                return 600 if atk >= 130 else 400
            return 500

        scores = _make_scores(4, 3, 1, fill)
        anchor = ResolvedAnchor(
            name='mirror_brkp_any',
            parent_display_name='mirror BP',
            parent='mirror_brkp_any',
            kind='damage_breakpoint',
            threshold_value=130.0,
            target_stat='atk',
            opponent='Mirror',
        )

        records = deep_dive._aggregate_flips_by_anchor(
            scores, 4, 3, 1, [anchor], data_obj, scenarios, opponents,
        )
        assert len(records) == 1
        assert records[0]['scenarios'] == [(2, 2), (2, 1)]

    def test_def_anchor_partition(self):
        # Bulkpoint-style: target_stat='def', threshold 102.
        ivs = [(120, 98), (120, 101), (120, 103), (120, 105)]
        data_obj = _make_data_obj(ivs)
        opponents = ['Annihilape']
        scenarios = [(2, 2)]

        def fill(iv, si, oi):
            return 800 if data_obj['ivDef'][iv] >= 102 else 200

        scores = _make_scores(4, 1, 1, fill)
        anchor = ResolvedAnchor(
            name='mirror_blkp_any',
            parent_display_name='mirror bulk',
            parent='mirror_blkp_any',
            kind='bulkpoint',
            threshold_value=102.0,
            target_stat='def',
            opponent='Annihilape',
        )

        records = deep_dive._aggregate_flips_by_anchor(
            scores, 4, 1, 1, [anchor], data_obj, scenarios, opponents,
        )
        assert len(records) == 1
        assert records[0]['scenarios'] == [(2, 2)]

    def test_no_signal_when_everyone_wins(self):
        # Everyone wins regardless of anchor — no clean partition.
        ivs = [(125, 100), (135, 100)]
        data_obj = _make_data_obj(ivs)
        scores = _make_scores(2, 1, 1, lambda iv, si, oi: 700)
        anchor = ResolvedAnchor(
            name='x', parent_display_name='x', parent='x', kind='damage_breakpoint',
            threshold_value=130.0, target_stat='atk', opponent='Foo',
        )
        records = deep_dive._aggregate_flips_by_anchor(
            scores, 2, 1, 1, [anchor], data_obj, [(2, 2)], ['Foo'],
        )
        assert records == []

    def test_no_signal_when_everyone_passes_anchor(self):
        # All IVs clear the anchor → empty failing set → skip.
        ivs = [(140, 100), (145, 100)]
        data_obj = _make_data_obj(ivs)
        scores = _make_scores(2, 1, 1, lambda iv, si, oi: 700)
        anchor = ResolvedAnchor(
            name='x', parent_display_name='x', parent='x', kind='damage_breakpoint',
            threshold_value=130.0, target_stat='atk', opponent='Foo',
        )
        records = deep_dive._aggregate_flips_by_anchor(
            scores, 2, 1, 1, [anchor], data_obj, [(2, 2)], ['Foo'],
        )
        assert records == []

    def test_anchor_without_opponent_skipped(self):
        ivs = [(125, 100), (135, 100)]
        data_obj = _make_data_obj(ivs)
        scores = _make_scores(2, 1, 1, lambda iv, si, oi: 700 if iv == 1 else 300)
        anchor = ResolvedAnchor(
            name='cmp_vs_cohort', parent_display_name='cmp:cohort', parent='cmp_vs_cohort',
            kind='cmp', threshold_value=130.0, target_stat='atk', opponent=None,
        )
        records = deep_dive._aggregate_flips_by_anchor(
            scores, 2, 1, 1, [anchor], data_obj, [(2, 2)], ['Foo'],
        )
        assert records == []

    def test_unknown_opponent_skipped(self):
        # Anchor names an opponent that isn't in the deep dive's opponent list.
        ivs = [(125, 100), (135, 100)]
        data_obj = _make_data_obj(ivs)
        scores = _make_scores(2, 1, 1, lambda iv, si, oi: 700 if iv == 1 else 300)
        anchor = ResolvedAnchor(
            name='x', parent_display_name='x', parent='x', kind='damage_breakpoint',
            threshold_value=130.0, target_stat='atk', opponent='SomeoneElse',
        )
        records = deep_dive._aggregate_flips_by_anchor(
            scores, 2, 1, 1, [anchor], data_obj, [(2, 2)], ['Foo'],
        )
        assert records == []

    def test_passing_ivs_populated_on_record(self):
        # When a record is emitted, it should carry the canonical IV
        # indices that pass the anchor — used downstream by the
        # interactive plot's anchor-clear overlay.
        ivs = [(125, 100), (128, 100), (131, 100), (134, 100)]
        data_obj = _make_data_obj(ivs)
        opponents = ['Annihilape']
        scenarios = [(2, 2)]

        def fill(iv, si, oi):
            return 700 if data_obj['ivAtk'][iv] >= 130 else 300

        scores = _make_scores(4, 1, 1, fill)
        anchor = ResolvedAnchor(
            name='x', parent_display_name='x', parent='x',
            kind='damage_breakpoint', threshold_value=130.0,
            target_stat='atk', opponent='Annihilape',
        )
        records = deep_dive._aggregate_flips_by_anchor(
            scores, 4, 1, 1, [anchor], data_obj, scenarios, opponents,
        )
        assert len(records) == 1
        # Strict > 130 → IVs at 131 (idx 2) and 134 (idx 3) pass.
        assert sorted(records[0]['passing_ivs']) == [2, 3]

    def test_case_insensitive_opponent_match(self):
        ivs = [(125, 100), (135, 100)]
        data_obj = _make_data_obj(ivs)
        scores = _make_scores(2, 1, 1, lambda iv, si, oi: 700 if iv == 1 else 300)
        anchor = ResolvedAnchor(
            name='x', parent_display_name='x', parent='x', kind='damage_breakpoint',
            threshold_value=130.0, target_stat='atk', opponent='annihilape',
        )
        records = deep_dive._aggregate_flips_by_anchor(
            scores, 2, 1, 1, [anchor], data_obj, [(2, 2)], ['Annihilape'],
        )
        assert len(records) == 1


# ---------------------------------------------------------------------------
# _render_anchor_flip_bullets
# ---------------------------------------------------------------------------

class TestRenderAnchorFlipBullets:
    def test_atk_bullet_format(self):
        anchor = ResolvedAnchor(
            name='lickitung_brkp_any', parent_display_name='lickitung',
            parent='lickitung_brkp_any', kind='damage_breakpoint',
            threshold_value=127.23, target_stat='atk', opponent='Annihilape',
        )
        rec = {'anchor': anchor, 'opponent': 'Annihilape',
               'scenarios': [(2, 2), (2, 1), (0, 0)], 'direction': 'gain'}
        out = deep_dive._render_anchor_flip_bullets([rec])
        assert len(out) == 1
        bullet = out[0]
        assert '127.23 Atk' in bullet
        assert 'lickitung' in bullet
        assert 'Annihilape' in bullet
        # Renderer sorts scenarios into stable shield-pair order.
        assert '0v0, 2v1, 2v2' in bullet
        assert bullet.startswith('<li>')
        assert bullet.endswith('</li>')

    def test_def_bullet_format(self):
        anchor = ResolvedAnchor(
            name='mirror_blkp_any', parent_display_name='mirror bulk',
            parent='mirror_blkp_any', kind='bulkpoint',
            threshold_value=103.54, target_stat='def', opponent='Annihilape',
        )
        rec = {'anchor': anchor, 'opponent': 'Annihilape',
               'scenarios': [(2, 2)], 'direction': 'gain'}
        out = deep_dive._render_anchor_flip_bullets([rec])
        assert '103.54 Def' in out[0]
        assert 'mirror bulk' in out[0]
        assert '2v2' in out[0]

    def test_empty_input(self):
        assert deep_dive._render_anchor_flip_bullets([]) == []

    def test_sub_anchors_same_move_collapse_to_min_threshold(self):
        # Two Level 3 sub-anchors of the same parent + same move (different
        # damage tiers): should collapse to ONE bullet with the lower
        # threshold (the higher tier is subsumed by crossing the lower one).
        a1 = ResolvedAnchor(
            name='mirror_brkp_rage_fist_t1', parent_display_name='mirror',
            parent='mirror_brkp_any', kind='damage_breakpoint',
            threshold_value=121.39, target_stat='atk',
            opponent='Annihilape', move_id='RAGE_FIST',
        )
        a2 = ResolvedAnchor(
            name='mirror_brkp_rage_fist_t2', parent_display_name='mirror',
            parent='mirror_brkp_any', kind='damage_breakpoint',
            threshold_value=123.07, target_stat='atk',
            opponent='Annihilape', move_id='RAGE_FIST',
        )
        recs = [
            {'anchor': a1, 'opponent': 'Annihilape',
             'scenarios': [(0, 0), (1, 1)], 'direction': 'gain'},
            {'anchor': a2, 'opponent': 'Annihilape',
             'scenarios': [(1, 1), (2, 2)], 'direction': 'gain'},
        ]
        out = deep_dive._render_anchor_flip_bullets(recs)
        assert len(out) == 1
        bullet = out[0]
        # Min threshold only — higher tier is subsumed.
        assert '121.39 Atk' in bullet
        assert '123.07' not in bullet
        assert 'Rage Fist' in bullet
        # Union of scenarios across both sub-anchors.
        assert '0v0, 1v1, 2v2' in bullet

    def test_sub_anchors_different_moves_get_separate_bullets(self):
        # Same parent + opponent but different moves → two bullets,
        # sorted by ascending min threshold within the family.
        a1 = ResolvedAnchor(
            name='mirror_brkp_counter', parent_display_name='mirror',
            parent='mirror_brkp_any', kind='damage_breakpoint',
            threshold_value=121.39, target_stat='atk',
            opponent='Annihilape', move_id='COUNTER',
        )
        a2 = ResolvedAnchor(
            name='mirror_brkp_close_combat', parent_display_name='mirror',
            parent='mirror_brkp_any', kind='damage_breakpoint',
            threshold_value=123.07, target_stat='atk',
            opponent='Annihilape', move_id='CLOSE_COMBAT',
        )
        recs = [
            {'anchor': a2, 'opponent': 'Annihilape',
             'scenarios': [(2, 2)], 'direction': 'gain'},
            {'anchor': a1, 'opponent': 'Annihilape',
             'scenarios': [(2, 2)], 'direction': 'gain'},
        ]
        out = deep_dive._render_anchor_flip_bullets(recs)
        assert len(out) == 2
        # Within the family, ascending threshold: Counter (121.39)
        # comes before Close Combat (123.07).
        assert '121.39' in out[0]
        assert 'Counter' in out[0]
        assert '123.07' in out[1]
        assert 'Close Combat' in out[1]

    def test_different_parents_stay_separate(self):
        a1 = ResolvedAnchor(
            name='mirror_brkp_any', parent_display_name='mirror',
            parent='mirror_brkp_any', kind='damage_breakpoint',
            threshold_value=121.39, target_stat='atk', opponent='Annihilape',
        )
        a2 = ResolvedAnchor(
            name='lickitung_brkp_any', parent_display_name='lickitung',
            parent='lickitung_brkp_any', kind='damage_breakpoint',
            threshold_value=127.23, target_stat='atk', opponent='Annihilape',
        )
        recs = [
            {'anchor': a1, 'opponent': 'Annihilape',
             'scenarios': [(2, 2)], 'direction': 'gain'},
            {'anchor': a2, 'opponent': 'Annihilape',
             'scenarios': [(2, 2)], 'direction': 'gain'},
        ]
        out = deep_dive._render_anchor_flip_bullets(recs)
        assert len(out) == 2

    def test_same_parent_different_opponent_stays_separate(self):
        a1 = ResolvedAnchor(
            name='mirror_brkp_any', parent_display_name='mirror',
            parent='mirror_brkp_any', kind='damage_breakpoint',
            threshold_value=121.39, target_stat='atk', opponent='Annihilape',
        )
        a2 = ResolvedAnchor(
            name='mirror_brkp_any', parent_display_name='mirror',
            parent='mirror_brkp_any', kind='damage_breakpoint',
            threshold_value=121.39, target_stat='atk', opponent='Lickitung',
        )
        recs = [
            {'anchor': a1, 'opponent': 'Annihilape',
             'scenarios': [(2, 2)], 'direction': 'gain'},
            {'anchor': a2, 'opponent': 'Lickitung',
             'scenarios': [(2, 2)], 'direction': 'gain'},
        ]
        out = deep_dive._render_anchor_flip_bullets(recs)
        assert len(out) == 2

    def test_no_move_id_omits_move_list(self):
        # Level 1 / Level 2 anchors don't carry move_id; bullet should
        # not include a stray empty parenthetical.
        a = ResolvedAnchor(
            name='lurgan_ape_atk', parent_display_name='lurgan',
            parent='lurgan_ape_atk', kind='damage_breakpoint',
            threshold_value=127.23, target_stat='atk', opponent='Annihilape',
        )
        rec = {'anchor': a, 'opponent': 'Annihilape',
               'scenarios': [(2, 2)], 'direction': 'gain'}
        out = deep_dive._render_anchor_flip_bullets([rec])
        # No "()" left over from an empty move list
        assert '()' not in out[0]
        assert '127.23 Atk' in out[0]


# ---------------------------------------------------------------------------
# _render_threshold_tier_cards
# ---------------------------------------------------------------------------

def _make_tier_data_obj(n_ivs, tiers, tier_assignments, atk_vals, def_vals, hp_vals,
                        iv_triples=None):
    """Build a data_obj with the fields _render_threshold_tier_cards reads."""
    if iv_triples is None:
        iv_triples = [(0, 15, i) for i in range(n_ivs)]
    return {
        'nIvs': n_ivs,
        'tiers': tiers,
        'ivTiers': tier_assignments,
        'ivAtk': atk_vals,
        'ivDef': def_vals,
        'ivHp': hp_vals,
        'ivA': [t[0] for t in iv_triples],
        'ivD': [t[1] for t in iv_triples],
        'ivS': [t[2] for t in iv_triples],
    }


class TestRenderThresholdTierCards:
    """The new stat-target-forward tier cards should organise anchor-flip
    bullets under the tiers whose stat specs clear them, and list member
    IVs in a collapsed details block."""

    def test_basic_tier_card_with_matching_anchor(self):
        # One tier requiring atk >= 125, one anchor at atk 122.
        # The tier clears the anchor, so the bullet should appear.
        tiers = [{'name': 'Atk Weight', 'desc': 'High atk', 'color': '#f00',
                  'attack': 125, 'defense': 0, 'stamina': 0}]
        data_obj = _make_tier_data_obj(
            n_ivs=3, tiers=tiers,
            tier_assignments=[0, 0, -1],
            atk_vals=[126, 127, 120],
            def_vals=[100, 99, 105],
            hp_vals=[140, 139, 142],
        )
        anchor = ResolvedAnchor(
            name='bp', parent_display_name='lick BP', parent='bp',
            kind='damage_breakpoint', threshold_value=122.0,
            target_stat='atk', opponent='Lickitung',
        )
        records = [{'anchor': anchor, 'opponent': 'Lickitung',
                    'scenarios': [(1, 1)], 'direction': 'gain'}]

        html = deep_dive._render_threshold_tier_cards(
            data_obj, records,
            avg_ranks={0: 1, 1: 2, 2: 3},
            flip_map={0: (2, 0, 2), 1: (1, 0, 1), 2: (0, 0, 0)},
        )
        assert 'Threshold Tiers' in html
        assert 'Atk Weight' in html
        assert 'atk≥125' in html
        assert '122.00 Atk' in html      # anchor bullet
        assert 'lick BP' in html
        assert 'Member IVs (2)' in html   # two IVs in tier 0
        assert '126' in html or '127' in html  # member atk values

    def test_anchor_above_tier_cutoff_excluded(self):
        # Tier requires atk >= 120. Anchor threshold is 125.
        # The tier does NOT clear the 125 anchor — bullet should be absent.
        tiers = [{'name': 'Low Atk', 'desc': '', 'color': '#0f0',
                  'attack': 120, 'defense': 0, 'stamina': 0}]
        data_obj = _make_tier_data_obj(
            n_ivs=2, tiers=tiers,
            tier_assignments=[0, 0],
            atk_vals=[121, 122],
            def_vals=[100, 100],
            hp_vals=[140, 140],
        )
        anchor = ResolvedAnchor(
            name='bp', parent_display_name='high bp', parent='bp',
            kind='damage_breakpoint', threshold_value=125.0,
            target_stat='atk', opponent='Foo',
        )
        records = [{'anchor': anchor, 'opponent': 'Foo',
                    'scenarios': [(2, 2)], 'direction': 'gain'}]
        html = deep_dive._render_threshold_tier_cards(
            data_obj, records,
            avg_ranks={0: 1, 1: 2},
            flip_map={},
        )
        assert '125.00 Atk' not in html
        assert 'No named anchors' in html

    def test_def_anchor_included_when_tier_has_def_cutoff(self):
        tiers = [{'name': 'Bulk', 'desc': '', 'color': '#0f0',
                  'attack': 0, 'defense': 105, 'stamina': 0}]
        data_obj = _make_tier_data_obj(
            n_ivs=2, tiers=tiers,
            tier_assignments=[0, 0],
            atk_vals=[120, 120],
            def_vals=[106, 107],
            hp_vals=[140, 140],
        )
        anchor = ResolvedAnchor(
            name='blkp', parent_display_name='lick blkp', parent='blkp',
            kind='bulkpoint', threshold_value=103.0,
            target_stat='def', opponent='Lickitung',
        )
        records = [{'anchor': anchor, 'opponent': 'Lickitung',
                    'scenarios': [(2, 2)], 'direction': 'gain'}]
        html = deep_dive._render_threshold_tier_cards(
            data_obj, records,
            avg_ranks={0: 1, 1: 2},
            flip_map={},
        )
        assert '103.00 Def' in html
        assert 'lick blkp' in html

    def test_empty_tiers_returns_empty(self):
        data_obj = {'tiers': [], 'nIvs': 0}
        html = deep_dive._render_threshold_tier_cards(data_obj, [], {}, {})
        assert html == ''

    def test_auto_derived_tiers_render_with_bullets(self):
        """Tiers synthesized by _auto_derive_tiers should produce cards with
        matching anchor bullets when passed via override_tiers."""
        # Two opponents: one atk anchor, one def anchor
        a_atk = ResolvedAnchor(
            name='bp', parent_display_name='mirror', parent='bp',
            kind='damage_breakpoint', threshold_value=121.39,
            target_stat='atk', opponent='Mirror',
        )
        a_def = ResolvedAnchor(
            name='blkp', parent_display_name='sealeo blkp', parent='blkp',
            kind='bulkpoint', threshold_value=101.5,
            target_stat='def', opponent='Sealeo',
        )
        records = [
            {'anchor': a_atk, 'opponent': 'Mirror',
             'scenarios': [(0, 0), (1, 1)], 'direction': 'gain'},
            {'anchor': a_def, 'opponent': 'Sealeo',
             'scenarios': [(1, 2)], 'direction': 'gain'},
        ]
        data_obj = _make_tier_data_obj(
            n_ivs=4, tiers=[],  # no TOML tiers
            tier_assignments=[-1, -1, -1, -1],
            atk_vals=[120, 122, 125, 128],
            def_vals=[100, 102, 104, 106],
            hp_vals=[140, 140, 140, 140],
        )
        auto_tiers = deep_dive._auto_derive_tiers(records, data_obj)
        assert len(auto_tiers) >= 2
        # Should have a General tier and at least one specialist
        names = [t['name'] for t in auto_tiers]
        assert 'General' in names

        # Render with override_tiers — should produce bullets
        html = deep_dive._render_threshold_tier_cards(
            data_obj, records,
            avg_ranks={0: 1, 1: 2, 2: 3, 3: 4},
            flip_map={},
            override_tiers=auto_tiers,
        )
        assert '121.39 Atk' in html
        assert '101.50 Def' in html
        assert 'General' in html

    def test_no_records_still_renders_tier_headline(self):
        tiers = [{'name': 'Solo', 'desc': 'test', 'color': '#fff',
                  'attack': 130, 'defense': 0, 'stamina': 0}]
        data_obj = _make_tier_data_obj(
            n_ivs=1, tiers=tiers,
            tier_assignments=[0],
            atk_vals=[131],
            def_vals=[100],
            hp_vals=[140],
        )
        html = deep_dive._render_threshold_tier_cards(
            data_obj, [],
            avg_ranks={0: 1},
            flip_map={},
        )
        assert 'Solo' in html
        assert 'atk≥130' in html
        assert 'No named anchors' in html
