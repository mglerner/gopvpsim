"""Regression tests for the IV Flavor Guide narrative renderer.

Covers the S5a narrative-polish fixes (2026-04-17):

- Item 6: name-signature coupling. "Premium Bulk" with an ADH
  signature is renamed to "General Good" per STYLE_ANALYSIS.md
  "Stat Signature Rule".
- Item 7: any 2-axis pair is a valid signature (AD, AH, DH).
- Item 1: namesake guarantee. A flavor named "{Opp} Slayer" must have
  at least one matchup against {Opp} in its gains list.
- Item 2: identical-stat merge. Two flavors sharing both stat signature
  and gains signature collapse to "{A} / {B} Slayer" (or "Fortified
  {A} / {B}"). Different signatures (e.g. Fortified Lapras at DH)
  must NOT merge with a Slayer at AH.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from deep_dive_narrative import (  # noqa: E402
    _axis_shape,
    _flavor_name_for_tier,
    _merge_flavor_names,
    _naming_opponents,
    _render_rank1_self_check,
    _stat_signature,
    enforce_namesake_guarantee,
    merge_identical_stat_flavors,
)


# ---------------------------------------------------------------------------
# Axis shape + name-signature coupling (items 6 + 7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('atk,def_,hp,expected', [
    (115.50, 93.67, 148, 'ADH'),
    (0, 93.67, 148, 'DH'),
    (123.74, 0, 149, 'AH'),
    (101.79, 127.34, 0, 'AD'),
    (123.74, 0, 0, 'A'),
    (0, 93.67, 0, 'D'),
    (0, 0, 148, 'H'),
    (0, 0, 0, ''),
])
def test_axis_shape(atk, def_, hp, expected):
    assert _axis_shape(atk, def_, hp) == expected


@pytest.mark.parametrize('atk,def_,hp,expected_name', [
    # Item 6: General with all three axes constrained -> General Good, not
    # Premium Bulk. Regression lock for the live Oinkologne m0 case that
    # rendered "Premium Bulk (115.50 Atk, 93.67 Def, 148 HP)" pre-fix.
    (115.50, 93.67, 148, 'General Good'),
    # General with DH only stays Premium Bulk (bulk-family convention).
    (0, 93.67, 148, 'Premium Bulk'),
    # General with A-only -> Attack Weight.
    (123.74, 0, 0, 'Attack Weight'),
    # General with nothing populated -> Premium Bulk fallback.
    (0, 0, 0, 'Premium Bulk'),
    # General with AD (no HP) -> General Good (still multi-axis).
    (101.79, 127.34, 0, 'General Good'),
    # General with AH (no Def) -> General Good.
    (123.74, 0, 149, 'General Good'),
])
def test_flavor_name_general(atk, def_, hp, expected_name):
    assert _flavor_name_for_tier('General', atk, def_, hp) == expected_name


def test_flavor_name_opponent_specific():
    # Auto-derived "Lapras Atk" tier with atk only -> "Lapras Slayer"
    assert _flavor_name_for_tier('Lapras Atk', 123.74, 0, 0) == 'Lapras Slayer'
    # Lapras Atk with HP enrichment still -> Lapras Slayer
    assert _flavor_name_for_tier('Lapras Atk', 123.74, 0, 149) == 'Lapras Slayer'
    # Auto-derived "Greedent Bulk" tier with def only -> "Fortified Greedent"
    assert _flavor_name_for_tier('Greedent Bulk', 0, 104.18, 0) == 'Fortified Greedent'
    assert _flavor_name_for_tier('Greedent Bulk', 0, 104.18, 153) == 'Fortified Greedent'
    # Generic Atk N+ / Bulk N+
    assert _flavor_name_for_tier('Atk 123+', 123.0, 0, 0) == 'Attack Weight'
    assert _flavor_name_for_tier('Bulk 140+', 0, 140.0, 0) == 'High Bulk'
    # TOML-defined names pass through
    assert _flavor_name_for_tier('GL-General Good', 122.94, 106.17, 136) == 'GL-General Good'


# ---------------------------------------------------------------------------
# Stat signature (item 7)
# ---------------------------------------------------------------------------

def test_stat_signature_shows_constrained_axes_only():
    # ADH
    assert _stat_signature(115.50, 93.67, 148) == '115.50 Atk, 93.67 Def, 148 HP'
    # DH (Premium Bulk family)
    assert _stat_signature(0, 93.67, 148) == '93.67 Def, 148 HP'
    # AH (pure Slayer)
    assert _stat_signature(123.74, 0, 149) == '123.74 Atk, 149 HP'
    # AD without HP -- legitimate per GFisk Pure Mirror Slayer
    assert _stat_signature(101.79, 127.34, 0) == '101.79 Atk, 127.34 Def'
    # Single axis
    assert _stat_signature(123.74, 0, 0) == '123.74 Atk'
    assert _stat_signature(0, 93.67, 0) == '93.67 Def'
    assert _stat_signature(0, 0, 148) == '148 HP'


# ---------------------------------------------------------------------------
# Namesake guarantee (item 1)
# ---------------------------------------------------------------------------

def test_naming_opponents_extraction():
    assert _naming_opponents('Lapras Slayer') == ['Lapras']
    assert _naming_opponents('Fortified Lapras') == ['Lapras']
    assert _naming_opponents('Lapras / Shadow Lapras Slayer') == [
        'Lapras', 'Lapras (Shadow)']
    assert _naming_opponents('Lapras Slayer (123.74+ Atk)') == ['Lapras']
    assert _naming_opponents('Premium Bulk') == []
    assert _naming_opponents('General Good') == []
    assert _naming_opponents('Attack Weight') == []
    assert _naming_opponents('High Bulk') == []


def test_namesake_guarantee_prepends_missing_opponent():
    # Live Oinkologne m0 bug: "Lapras Slayer" gains listed Altaria,
    # Charjabug, Diggersby but NOT Lapras. Fix: prepend a synthesized
    # gain from the closest matchup boundary against Lapras.
    flavors = [
        {'name': 'Lapras Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 149},
    ]
    tradeoffs = {
        'Lapras Slayer': {
            'gains': [
                {'opponent': 'Altaria', 'scenarios': [(2, 0)]},
                {'opponent': 'Charjabug', 'scenarios': [(0, 0)]},
                {'opponent': 'Diggersby', 'scenarios': [(2, 2)]},
            ],
            'losses': [],
        },
    }
    matchup_boundaries = [
        {'opponent': 'Lapras', 'stat': 'atk', 'threshold': 123.74,
         'scenarios': [(2, 1)], 'hp_threshold': 149},
    ]
    enforce_namesake_guarantee(flavors, tradeoffs, matchup_boundaries)
    gain_opps = [g['opponent'] for g in tradeoffs['Lapras Slayer']['gains']]
    assert 'Lapras' in gain_opps
    # Lapras is prepended so the intro prose mentions it first
    assert gain_opps[0] == 'Lapras'


def test_namesake_guarantee_no_op_when_opponent_already_present():
    flavors = [
        {'name': 'Lapras Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 149},
    ]
    original_gains = [
        {'opponent': 'Lapras', 'scenarios': [(2, 1)]},
        {'opponent': 'Altaria', 'scenarios': [(2, 0)]},
    ]
    tradeoffs = {
        'Lapras Slayer': {
            'gains': list(original_gains),
            'losses': [],
        },
    }
    matchup_boundaries = [
        {'opponent': 'Lapras', 'stat': 'atk', 'threshold': 123.74,
         'scenarios': [(1, 1)], 'hp_threshold': 149},
    ]
    enforce_namesake_guarantee(flavors, tradeoffs, matchup_boundaries)
    # Lapras was already in gains; nothing should have been added
    assert tradeoffs['Lapras Slayer']['gains'] == original_gains


def test_namesake_guarantee_front_moves_namesake_in_gains():
    # Regression test for the 2026-04-17 "Fortified Quagsire (Shadow)"
    # case: Quagsire WAS in gains but buried behind alphabetically-
    # earlier opponents (Charjabug, Cradily, ...), so prose showed
    # "gain ... the Charjabug 1-1, the Cradily 1-0, the Dusclops 0-1"
    # with no Quagsire mention in the first 3 items. Fix: front-move
    # every namesake gain so the prose leads with "the Quagsire X-Y".
    flavors = [
        {'name': 'Fortified Quagsire (Shadow)', 'is_general': False,
         'atk_cut': 0, 'def_cut': 104.45, 'hp_cut': 154},
    ]
    tradeoffs = {
        'Fortified Quagsire (Shadow)': {
            'gains': [
                {'opponent': 'Charjabug', 'scenarios': [(1, 1)]},
                {'opponent': 'Cradily', 'scenarios': [(1, 0)]},
                {'opponent': 'Dusclops', 'scenarios': [(0, 1)]},
                {'opponent': 'Quagsire', 'scenarios': [(0, 1)]},
                {'opponent': 'Quagsire (Shadow)', 'scenarios': [(1, 1)]},
                {'opponent': 'Sealeo', 'scenarios': [(2, 2)]},
            ],
            'losses': [],
        },
    }
    enforce_namesake_guarantee(flavors, tradeoffs, [], anchor_flip_records=[])
    gains = tradeoffs['Fortified Quagsire (Shadow)']['gains']
    # Both Quagsire variants must appear before any non-Quagsire gain.
    first_non_quag = next((i for i, g in enumerate(gains)
                           if not g['opponent'].startswith('Quagsire')), -1)
    quag_positions = [i for i, g in enumerate(gains)
                      if g['opponent'].startswith('Quagsire')]
    assert quag_positions, gains
    assert all(p < first_non_quag for p in quag_positions), gains


def test_namesake_guarantee_strips_shadow_suffix_for_comparison():
    # Regression test for the 2026-04-17 bug: when a tier is named after
    # a shadow variant (e.g. "Fortified Quagsire (Shadow)" from
    # auto_derive_tiers processing an anchor whose opponent was
    # "Quagsire (Shadow)"), the namesake check must compare at the
    # base-species level. Gains carry both "Quagsire" and
    # "Quagsire (Shadow)" entries; both reduce to base "Quagsire".
    flavors = [
        {'name': 'Fortified Quagsire (Shadow)', 'is_general': False,
         'atk_cut': 0, 'def_cut': 104.45, 'hp_cut': 154},
    ]
    tradeoffs = {
        'Fortified Quagsire (Shadow)': {
            'gains': [
                # Gains include the base species already -- the namesake
                # check should recognise this and NOT try to re-add it
                # (which would double the entry).
                {'opponent': 'Quagsire (Shadow)', 'scenarios': [(1, 1)]},
                {'opponent': 'Cradily', 'scenarios': [(1, 0)]},
            ],
            'losses': [],
        },
    }
    enforce_namesake_guarantee(flavors, tradeoffs, [], anchor_flip_records=[])
    gains = tradeoffs['Fortified Quagsire (Shadow)']['gains']
    # Should NOT add a duplicate Quagsire entry (namesake already satisfied
    # by the existing Quagsire (Shadow) gain at base level).
    quagsire_count = sum(1 for g in gains
                          if g['opponent'].startswith('Quagsire'))
    assert quagsire_count == 1, gains


def test_namesake_guarantee_falls_back_to_anchor_flip_records():
    # When matchup boundaries don't carry an entry for the namesake
    # opponent, enforce_namesake_guarantee should fall back to
    # anchor_flip_records (the stream that produced the tier's name
    # in the first place). Regression lock for the small-dive bug
    # found 2026-04-17 where Lapras Slayer's gains skipped Lapras
    # because all_matchup_boundaries didn't have an atk-side Lapras
    # entry even though the anchor-flip layer did.
    class _Anchor:
        def __init__(self, threshold_value, target_stat):
            self.threshold_value = threshold_value
            self.target_stat = target_stat

    flavors = [
        {'name': 'Lapras Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 0},
    ]
    tradeoffs = {
        'Lapras Slayer': {
            'gains': [{'opponent': 'Altaria', 'scenarios': [(2, 0)]}],
            'losses': [],
        },
    }
    anchor_flip_records = [
        {'opponent': 'Lapras',
         'anchor': _Anchor(123.74, 'atk'),
         'scenarios': [(2, 1)]},
    ]
    enforce_namesake_guarantee(
        flavors, tradeoffs, all_matchup_boundaries=[],
        anchor_flip_records=anchor_flip_records)
    gain_opps = [g['opponent'] for g in tradeoffs['Lapras Slayer']['gains']]
    assert 'Lapras' in gain_opps
    assert gain_opps[0] == 'Lapras'


def test_namesake_guarantee_skips_general_flavors():
    flavors = [
        {'name': 'Premium Bulk', 'is_general': True,
         'atk_cut': 0, 'def_cut': 93.67, 'hp_cut': 148},
    ]
    tradeoffs = {'Premium Bulk': {'gains': [], 'losses': []}}
    matchup_boundaries = [
        {'opponent': 'Lapras', 'stat': 'def', 'threshold': 100.0,
         'scenarios': [(2, 2)], 'hp_threshold': 148},
    ]
    enforce_namesake_guarantee(flavors, tradeoffs, matchup_boundaries)
    # General flavors aren't opponent-named; nothing to enforce
    assert tradeoffs['Premium Bulk']['gains'] == []


# ---------------------------------------------------------------------------
# Identical-stat merge (item 2)
# ---------------------------------------------------------------------------

def test_merge_flavor_names_slayer():
    assert (_merge_flavor_names(['Lapras Slayer', 'Lapras (Shadow) Slayer'])
            == 'Lapras / Shadow Lapras Slayer')


def test_merge_flavor_names_fortified():
    assert (_merge_flavor_names(['Fortified Altaria', 'Fortified Altaria (Shadow)'])
            == 'Fortified Altaria / Shadow Altaria')


def test_merge_flavor_names_family_mismatch_returns_none():
    # Slayer + Fortified are different families and must not merge
    assert _merge_flavor_names(['Lapras Slayer', 'Fortified Lapras']) is None


def test_merge_identical_stat_flavors_canonical_case():
    # Canonical Oinkologne m0 case: Lapras Slayer + Lapras (Shadow) Slayer
    # at identical (123.74 Atk, 149 HP) with identical gains.
    shared_gains = [
        {'opponent': 'Altaria', 'scenarios': [(2, 0)]},
        {'opponent': 'Charjabug', 'scenarios': [(0, 0)]},
    ]
    flavors = [
        {'name': 'Premium Bulk', 'is_general': True,
         'atk_cut': 0, 'def_cut': 93.67, 'hp_cut': 148},
        {'name': 'Lapras Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 149},
        {'name': 'Lapras (Shadow) Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 149},
    ]
    tradeoffs = {
        'Lapras Slayer': {'gains': list(shared_gains), 'losses': []},
        'Lapras (Shadow) Slayer': {'gains': list(shared_gains), 'losses': []},
    }
    merge_identical_stat_flavors(flavors, tradeoffs)
    names = [f['name'] for f in flavors]
    assert 'Lapras / Shadow Lapras Slayer' in names
    assert 'Lapras Slayer' not in names
    assert 'Lapras (Shadow) Slayer' not in names
    assert 'Lapras / Shadow Lapras Slayer' in tradeoffs


def test_merge_does_not_collapse_different_stat_signatures():
    # Negative test from S5a plan: Fortified Lapras (105.19 Def, 153 HP)
    # has a DH signature; must NOT merge with Lapras Slayer (AH signature)
    # even though both reference Lapras.
    flavors = [
        {'name': 'Lapras Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 149},
        {'name': 'Fortified Lapras', 'is_general': False,
         'atk_cut': 0, 'def_cut': 105.19, 'hp_cut': 153},
    ]
    tradeoffs = {
        'Lapras Slayer': {
            'gains': [{'opponent': 'Lapras', 'scenarios': [(2, 1)]}],
            'losses': [],
        },
        'Fortified Lapras': {
            'gains': [{'opponent': 'Lapras', 'scenarios': [(1, 1)]}],
            'losses': [],
        },
    }
    merge_identical_stat_flavors(flavors, tradeoffs)
    names = [f['name'] for f in flavors]
    assert 'Lapras Slayer' in names
    assert 'Fortified Lapras' in names


# ---------------------------------------------------------------------------
# Rank-1 self-check line (item 3)
# ---------------------------------------------------------------------------

def _mock_data_obj_with_rank1(r_atk, r_def, r_hp, r_atk_iv=0, r_def_iv=15, r_hp_iv=15):
    """Build a minimal data_obj exposing rank-1 IV fields for _render_rank1_self_check."""
    return {
        'rank1RefIvIdx': 0,
        'ivAtk': [r_atk],
        'ivDef': [r_def],
        'ivHp': [r_hp],
        'ivA': [r_atk_iv],
        'ivD': [r_def_iv],
        'ivS': [r_hp_iv],
    }


def test_rank1_self_check_meets_thresholds():
    flavors = [
        {'name': 'General Good', 'is_general': True, 'recommended': True,
         'atk_cut': 115.50, 'def_cut': 93.67, 'hp_cut': 148},
    ]
    data_obj = _mock_data_obj_with_rank1(116.0, 94.0, 149,
                                          r_atk_iv=0, r_def_iv=15, r_hp_iv=15)
    line = _render_rank1_self_check(flavors, data_obj, 'Oinkologne')
    assert 'meets the General Good thresholds' in line
    assert '0/15/15' in line


def test_rank1_self_check_flags_hp_shortfall():
    flavors = [
        {'name': 'General Good', 'is_general': True, 'recommended': True,
         'atk_cut': 115.50, 'def_cut': 93.67, 'hp_cut': 150},
    ]
    # Rank-1 has HP=148 (2 below the recommended 150 HP cut)
    data_obj = _mock_data_obj_with_rank1(120.0, 95.0, 148)
    line = _render_rank1_self_check(flavors, data_obj, 'Oinkologne')
    assert 'falls short on HP' in line
    assert 'needs 150' in line
    assert 'has 148' in line
    assert 'trading threshold reach for max stat product' in line


def test_rank1_self_check_handles_multi_axis_shortfall():
    flavors = [
        {'name': 'Lickitung Slayer', 'is_general': False, 'recommended': False,
         'atk_cut': 127.23, 'def_cut': 102.26, 'hp_cut': 132},
        {'name': 'General Good', 'is_general': True, 'recommended': True,
         'atk_cut': 115.50, 'def_cut': 93.67, 'hp_cut': 148},
    ]
    # Rank-1 falls short on both Def and HP (not Atk)
    data_obj = _mock_data_obj_with_rank1(120.0, 90.0, 147)
    line = _render_rank1_self_check(flavors, data_obj, 'Oinkologne')
    assert 'Def' in line
    assert 'HP' in line
    assert 'Atk' not in line  # Atk not short


def test_rank1_self_check_empty_when_no_ref_iv():
    flavors = [{'name': 'General Good', 'is_general': True, 'recommended': True,
                'atk_cut': 115.50, 'def_cut': 93.67, 'hp_cut': 148}]
    data_obj = {'rank1RefIvIdx': -1}
    assert _render_rank1_self_check(flavors, data_obj, 'Oinkologne') == ''


def test_merge_does_not_fire_when_gains_differ():
    # Same stat signature but different gains -> stay separate.
    flavors = [
        {'name': 'Lapras Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 149},
        {'name': 'Lapras (Shadow) Slayer', 'is_general': False,
         'atk_cut': 123.74, 'def_cut': 0, 'hp_cut': 149},
    ]
    tradeoffs = {
        'Lapras Slayer': {
            'gains': [{'opponent': 'Lapras', 'scenarios': [(2, 1)]}],
            'losses': [],
        },
        'Lapras (Shadow) Slayer': {
            'gains': [{'opponent': 'Lapras (Shadow)', 'scenarios': [(2, 1)]}],
            'losses': [],
        },
    }
    merge_identical_stat_flavors(flavors, tradeoffs)
    names = [f['name'] for f in flavors]
    assert 'Lapras Slayer' in names
    assert 'Lapras (Shadow) Slayer' in names
    assert 'Lapras / Shadow Lapras Slayer' not in names


# ---------------------------------------------------------------------------
# compute_flavor_tradeoffs: indirect losses gated on real win rate (R2)
# ---------------------------------------------------------------------------

def _tradeoff_inputs(atk_vals):
    """4-IV synthetic dive: one bulk-driven opponent (wins iff def>=100,
    i.e. IVs 0 and 1), one scenario, one mode. General = def>=100;
    specialist flavor = atk>=100 (membership controlled by atk_vals)."""
    from deep_dive_narrative import compute_flavor_tradeoffs
    data_obj = {
        'nIvs': 4,
        'ivAtk': atk_vals,
        'ivDef': [110.0, 110.0, 90.0, 90.0],
        'ivHp': [140, 140, 140, 140],
        'oppIvModes': ['pvpoke'],
    }
    # scores_flat layout: iv*nS*nO + si*nO + oi (nS=1, nO=1)
    scores = [700, 700, 300, 300]
    score_arrays = {'0_pvpoke': scores}
    flavors = [
        {'name': 'General Good', 'is_general': True,
         'atk_cut': 0, 'def_cut': 100.0, 'hp_cut': 0},
        {'name': 'X Slayer', 'is_general': False,
         'atk_cut': 100.0, 'def_cut': 0, 'hp_cut': 0},
    ]
    td = compute_flavor_tradeoffs(
        flavors, data_obj, score_arrays, 0,
        scenarios=[[1, 1]], opponents=['OppBulk'])
    return td


def test_indirect_loss_dropped_when_flavor_cohort_wins():
    # Flavor cohort = {IV0} (atk 105, def 110): its probe can't cleanly
    # partition the bulk-driven matchup (fail side is mixed), but the
    # cohort WINS it — the old set-difference called this a loss anyway.
    td = _tradeoff_inputs([105.0, 95.0, 95.0, 95.0])
    loss_opps = [l['opponent'] for l in td['X Slayer']['losses']]
    assert 'OppBulk' not in loss_opps


# ---------------------------------------------------------------------------
# refine_flavor_names dedup: mirror exemption + same-axis guard (R1)
# ---------------------------------------------------------------------------

def _flavor(name, gains, atk=0, def_=0, hp=0, general=False):
    f = {'name': name, 'is_general': general, 'recommended': general,
         'atk_cut': atk, 'def_cut': def_, 'hp_cut': hp,
         'n_qualifying': 10, 'stat_sig': 'x', 'tier_name': name}
    td = {'gains': [{'opponent': g, 'scenarios': [(1, 1)]} for g in gains],
          'losses': []}
    return f, td


def _run_refine(specs):
    from deep_dive_narrative import refine_flavor_names
    flavors, tradeoffs = [], {}
    for f, td in specs:
        flavors.append(f)
        tradeoffs[f['name']] = td
    refine_flavor_names(flavors, tradeoffs)
    return [f['name'] for f in flavors]


def test_mirror_tier_survives_subset_dedup():
    # The mirror tier's gains are a strict subset of Fortified Corv's —
    # the old dedup silently dropped it (the known pre-ship follow-up).
    names = _run_refine([
        _flavor('General Good', ['A', 'B', 'C'], def_=100, general=True),
        _flavor('Fortified Corviknight', ['Corviknight', 'Lickilicky'], def_=105),
        _flavor('Dewgong Mirror Bulk', ['Corviknight'], def_=107),
    ])
    assert 'Dewgong Mirror Bulk' in names


def test_cross_axis_subset_survives():
    # def-axis flavor whose gains subset an ATK-axis flavor's must NOT
    # be removed — the comment always said "same stat axis"; the code
    # never checked until 2026-06-11.
    names = _run_refine([
        _flavor('General Good', ['A'], def_=100, general=True),
        _flavor('Big Atk Slayer', ['X', 'Y', 'Z'], atk=120),
        _flavor('Fortified Sealeo', ['X', 'Y'], def_=108),
    ])
    assert 'Fortified Sealeo' in names


def test_same_axis_subset_still_removed():
    names = _run_refine([
        _flavor('General Good', ['A'], def_=100, general=True),
        _flavor('Fortified Corviknight', ['X', 'Y', 'Z'], def_=105),
        _flavor('Fortified Sealeo', ['X', 'Y'], def_=108),
    ])
    assert 'Fortified Sealeo' not in names
    assert 'Fortified Corviknight' in names


def test_indirect_loss_kept_when_flavor_cohort_loses():
    # Flavor cohort = {IV2} (atk 105, def 90): genuinely loses the
    # bulk-driven matchup General gains — must stay a loss.
    td = _tradeoff_inputs([95.0, 95.0, 105.0, 95.0])
    loss_opps = [l['opponent'] for l in td['X Slayer']['losses']]
    assert 'OppBulk' in loss_opps
