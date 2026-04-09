"""
Tests for ``IVCategory`` + ``build_iv_categories`` in ``scripts/deep_dive.py``.

These verify the unified IV-category framework: slayer kinds, threshold-tier
kinds, and the slayer ∩ tier composite kinds (the round-one foundation for
SwagTips-style structured IV deep dives). The tests use a synthetic
``data_obj`` and a synthetic slayer-categories dict so they have no
dependency on the gamemaster or on a real deep-dive run.

Like ``test_flip_aggregator.py``, the script is imported via ``importlib``
because it lives in ``scripts/`` rather than the gopvpsim package.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"

_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)

IVCategory = deep_dive.IVCategory
build_iv_categories = deep_dive.build_iv_categories


def _make_data_obj():
    """4 synthetic IVs with two threshold tiers ("Top 5%", "Good")."""
    # IV index → (atk, def, hp). Hand-picked so each IV lands in a
    # distinct tier combination:
    #   0: high atk, low def, low hp  → no tier
    #   1: high atk, mid def, high hp → Top 5% (and Good by inclusion)
    #   2: mid atk, mid def, mid hp   → Good only
    #   3: low atk, high def, high hp → Good only
    iv_a_iv = [15, 15, 10, 0]
    iv_d_iv = [0, 5, 10, 15]
    iv_s_iv = [0, 10, 10, 15]
    iv_atk = [128.0, 128.5, 122.0, 100.0]
    iv_def = [98.0, 100.0, 105.0, 110.0]
    iv_hp = [120, 139, 135, 145]

    # Tier definitions (atk floor, def floor, hp floor):
    #   "Top 5%" requires atk≥128 AND hp≥139
    #   "Good"   requires atk≥120 AND hp≥130
    tiers = [
        {'name': 'Top 5%', 'attack': 128, 'defense': 0, 'stamina': 139,
         'desc': 'Top 5% by avg score', 'color': '#fff'},
        {'name': 'Good', 'attack': 120, 'defense': 0, 'stamina': 130,
         'desc': 'Top 20% by avg score', 'color': '#aaa'},
    ]
    iv_all_tiers = [[], [0, 1], [1], [1]]

    return {
        'nIvs': 4,
        'ivA': iv_a_iv, 'ivD': iv_d_iv, 'ivS': iv_s_iv,
        'ivAtk': iv_atk, 'ivDef': iv_def, 'ivHp': iv_hp,
        'tiers': tiers,
        'ivAllTiers': iv_all_tiers,
    }


def _make_slayer_categories(data_obj):
    """Synthesize a categorize_slayers-style dict.

    Atk Slayer = IVs 0 and 1 (high atk).
    Bulk Slayer = IVs 2 and 3 (mid/high def + hp).
    CMP Slayer empty.
    """
    def _row(idx, total_wins):
        return {
            'iv': (data_obj['ivA'][idx], data_obj['ivD'][idx],
                   data_obj['ivS'][idx]),
            'atk': data_obj['ivAtk'][idx],
            'def_': data_obj['ivDef'][idx],
            'hp': data_obj['ivHp'][idx],
            'total_wins': total_wins,
            'avg_score': 500.0,
            '_anchor_tags': {},  # tagged but with empty per-parent lists
        }

    return {
        'Atk Slayer': [_row(1, 132), _row(0, 45)],  # 1 first (more wins)
        'Bulk Slayer': [_row(3, 90), _row(2, 80)],
        'CMP Slayer': [],
    }


def test_build_categories_slayer_kinds_only():
    data_obj = _make_data_obj()
    slayer = _make_slayer_categories(data_obj)
    cats = build_iv_categories(data_obj, slayer)

    by_name = {c.name: c for c in cats}
    # Three slayer + two tier + composites
    assert 'Atk Slayer' in by_name
    assert 'Bulk Slayer' in by_name
    assert 'CMP Slayer' not in by_name  # empty buckets dropped

    atk = by_name['Atk Slayer']
    assert atk.kind == 'slayer'
    assert atk.members == [0, 1]  # sorted ascending
    assert 1 in atk.member_meta
    assert atk.member_meta[1]['total_wins'] == 132


def test_build_categories_tier_kinds():
    data_obj = _make_data_obj()
    cats = build_iv_categories(data_obj, slayer_categories=None)
    by_name = {c.name: c for c in cats}

    assert 'Top 5%' in by_name
    assert 'Good' in by_name

    top5 = by_name['Top 5%']
    assert top5.kind == 'tier'
    assert top5.members == [1]
    assert top5.stat_cutoffs == {'atk': 128, 'def': None, 'hp': 139}
    assert top5.source_tier == 'Top 5%'

    good = by_name['Good']
    assert good.members == [1, 2, 3]  # inclusive: Top 5% IVs are also Good


def test_composite_categories_intersection():
    """The Annihilape 13/0/11-style case: an IV in BOTH Atk Slayer and
    a stat-cutoff tier should surface as a composite category."""
    data_obj = _make_data_obj()
    slayer = _make_slayer_categories(data_obj)
    cats = build_iv_categories(data_obj, slayer)
    by_name = {c.name: c for c in cats}

    # IV 1 is the only one in BOTH Atk Slayer and Top 5%.
    comp_name = 'Atk Slayer ∩ Top 5%'
    assert comp_name in by_name, f"missing composite; got {sorted(by_name)}"
    comp = by_name[comp_name]
    assert comp.kind == 'composite'
    assert comp.members == [1]
    assert comp.source_categories == ['Atk Slayer', 'Top 5%']
    assert comp.source_tier == 'Top 5%'
    assert comp.stat_cutoffs == {'atk': 128, 'def': None, 'hp': 139}
    # member_meta merged from both parents
    assert comp.member_meta[1]['total_wins'] == 132
    assert comp.member_meta[1]['iv'] == (15, 5, 10)


def test_no_composite_when_no_intersection():
    """If no IV lives in both a slayer and a tier category, no composite
    is emitted (we don't manufacture empty intersections)."""
    data_obj = _make_data_obj()
    # Custom slayer dict where Atk Slayer covers IVs that AREN'T in any tier.
    slayer = {
        'Atk Slayer': [{
            'iv': (data_obj['ivA'][0], data_obj['ivD'][0], data_obj['ivS'][0]),
            'atk': data_obj['ivAtk'][0],
            'def_': data_obj['ivDef'][0],
            'hp': data_obj['ivHp'][0],
            'total_wins': 100,
            'avg_score': 500.0,
            '_anchor_tags': {},
        }],
        'Bulk Slayer': [],
        'CMP Slayer': [],
    }
    cats = build_iv_categories(data_obj, slayer)
    composites = [c for c in cats if c.kind == 'composite']
    assert composites == []


def test_empty_data_obj_returns_empty():
    assert build_iv_categories({'nIvs': 0}) == []


def test_matchup_categories_emit_non_trivial_partitions():
    """Round-one matchup branch: each (opponent, scenario) pair where
    some-but-not-all IVs win the matchup becomes a 'matchup' category.
    Carries declarative matchup_conditions for the future bait-axis
    sweep to extend without disturbing the data model.
    """
    data_obj = _make_data_obj()
    n_ivs = data_obj['nIvs']
    # 2 scenarios × 2 opponents. Score grid hand-built so:
    #   (opp 0, scen 0): IVs 0, 1 win → non-trivial → emit
    #   (opp 0, scen 1): everyone wins → degenerate → skip
    #   (opp 1, scen 0): no one wins → degenerate → skip
    #   (opp 1, scen 1): IV 3 alone wins → non-trivial → emit
    nS, nO = 2, 2
    scores_flat = [0.0] * (n_ivs * nS * nO)

    def _set(iv, si, oi, val):
        scores_flat[iv * nS * nO + si * nO + oi] = val

    # opp 0, scen 0
    _set(0, 0, 0, 600); _set(1, 0, 0, 700)
    _set(2, 0, 0, 100); _set(3, 0, 0, 200)
    # opp 0, scen 1: all win
    for iv in range(n_ivs):
        _set(iv, 1, 0, 800)
    # opp 1, scen 0: none win (all 0.0 already)
    # opp 1, scen 1: only IV 3 wins
    _set(3, 1, 1, 999)

    matchup_data = {
        'scores_flat': scores_flat,
        'nS': nS, 'nO': nO,
        'scenarios': [(0, 0), (2, 2)],
        'opponents': ['Lickitung', 'Cresselia'],
        'opp_iv_mode': 'rank1',
        'win_threshold': 500,
    }
    cats = build_iv_categories(data_obj, matchup_data=matchup_data)
    matchup_cats = [c for c in cats if c.kind == 'matchup']
    assert len(matchup_cats) == 2

    by_name = {c.name: c for c in matchup_cats}
    assert 'Beats rank 1 Lickitung in the 0v0' in by_name
    assert 'Beats rank 1 Cresselia in the 2v2' in by_name

    lic = by_name['Beats rank 1 Lickitung in the 0v0']
    assert lic.members == [0, 1]
    assert lic.matchup_conditions == [{
        'opponent': 'Lickitung',
        'opponent_ivs': 'rank1',
        'scenario': (0, 0),
        'bait': None,
        'outcome': 'win',
    }]
    assert lic.member_meta[0]['score'] == 600

    cress = by_name['Beats rank 1 Cresselia in the 2v2']
    assert cress.members == [3]


def test_matchup_branch_skipped_without_matchup_data():
    data_obj = _make_data_obj()
    cats = build_iv_categories(data_obj)
    assert all(c.kind != 'matchup' for c in cats)
