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
    """Synthesize a build_slayer_archetypes-style dict.

    Anchors-First Slayer = IVs 0 and 1 (high atk).
    CMP-First Slayer = IVs 2 and 3.
    Empty Archetype = empty (drop-empty-buckets case).
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
        'Anchors-First Slayer': [_row(1, 132), _row(0, 45)],  # 1 first (more wins)
        'CMP-First Slayer': [_row(3, 90), _row(2, 80)],
        'Empty Archetype': [],
    }


def test_build_categories_slayer_kinds_only():
    data_obj = _make_data_obj()
    slayer = _make_slayer_categories(data_obj)
    cats = build_iv_categories(data_obj, slayer)

    by_name = {c.name: c for c in cats}
    # Two archetypes + two tier + composites
    assert 'Anchors-First Slayer' in by_name
    assert 'CMP-First Slayer' in by_name
    assert 'Empty Archetype' not in by_name  # empty buckets dropped

    atk = by_name['Anchors-First Slayer']
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
    """The Annihilape 13/0/11-style case: an IV in BOTH an archetype and
    a stat-cutoff tier should surface as a composite category."""
    data_obj = _make_data_obj()
    slayer = _make_slayer_categories(data_obj)
    cats = build_iv_categories(data_obj, slayer)
    by_name = {c.name: c for c in cats}

    # IV 1 is the only one in BOTH Anchors-First Slayer and Top 5%.
    comp_name = 'Anchors-First Slayer ∩ Top 5%'
    assert comp_name in by_name, f"missing composite; got {sorted(by_name)}"
    comp = by_name[comp_name]
    assert comp.kind == 'composite'
    assert comp.members == [1]
    assert comp.source_categories == ['Anchors-First Slayer', 'Top 5%']
    assert comp.source_tier == 'Top 5%'
    assert comp.stat_cutoffs == {'atk': 128, 'def': None, 'hp': 139}
    # member_meta merged from both parents
    assert comp.member_meta[1]['total_wins'] == 132
    assert comp.member_meta[1]['iv'] == (15, 5, 10)


def test_no_composite_when_no_intersection():
    """If no IV lives in both a slayer and a tier category, no composite
    is emitted (we don't manufacture empty intersections)."""
    data_obj = _make_data_obj()
    # Custom dict where the archetype covers IVs that AREN'T in any tier.
    slayer = {
        'Anchors-First Slayer': [{
            'iv': (data_obj['ivA'][0], data_obj['ivD'][0], data_obj['ivS'][0]),
            'atk': data_obj['ivAtk'][0],
            'def_': data_obj['ivDef'][0],
            'hp': data_obj['ivHp'][0],
            'total_wins': 100,
            'avg_score': 500.0,
            '_anchor_tags': {},
        }],
        'CMP-First Slayer': [],
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
        'bait': 'bait',
        'outcome': 'win',
    }]
    assert lic.member_meta[0]['score'] == 600

    cress = by_name['Beats rank 1 Cresselia in the 2v2']
    assert cress.members == [3]


def test_matchup_branch_skipped_without_matchup_data():
    data_obj = _make_data_obj()
    cats = build_iv_categories(data_obj)
    assert all(c.kind != 'matchup' for c in cats)


def test_matchup_sibling_variant_dupes_merge():
    """An alt-moveset opponent variant ('Forretress (Bug Bite)') that yields
    the IDENTICAL winning-IV set as its base ('Forretress') in the same
    scenario collapses into ONE card naming both variants. The non-duplicate
    base opponent and the form-tagged opponent stay separate."""
    data_obj = _make_data_obj()
    n_ivs = data_obj['nIvs']
    nS, nO = 1, 4  # scen 0v0; opponents: Forretress, Forretress (Bug Bite),
    #                Medicham, Aegislash (Blade)
    scores_flat = [0.0] * (n_ivs * nS * nO)

    def _set(iv, oi, val):
        scores_flat[iv * nS * nO + 0 * nO + oi] = val

    # Forretress (oi 0) and Forretress (Bug Bite) (oi 1): IVs 0,1 win -> same set
    for oi in (0, 1):
        _set(0, oi, 600); _set(1, oi, 700)
    # Medicham (oi 2): IV 3 wins -> distinct partition, no sibling
    _set(3, 2, 999)
    # Aegislash (Blade) (oi 3): IVs 0,1 win -> SAME set as Forretress, but a
    # different base opponent (form tag, never folds) -> must NOT merge.
    _set(0, 3, 600); _set(1, 3, 700)

    matchup_data = {
        'scores_flat': scores_flat,
        'nS': nS, 'nO': nO,
        'scenarios': [(0, 0)],
        'opponents': ['Forretress', 'Forretress (Bug Bite)',
                      'Medicham', 'Aegislash (Blade)'],
        'opp_iv_mode': 'pvpoke',
        'win_threshold': 500,
    }
    cats = build_iv_categories(data_obj, matchup_data=matchup_data)
    matchup_cats = [c for c in cats if c.kind == 'matchup']
    names = {c.name for c in matchup_cats}

    # 4 raw cards -> 3 after the Forretress pair merges.
    assert len(matchup_cats) == 3
    # The merged card uses the base name and drops the moveset tag.
    assert 'Beats PvPoke default Forretress in the 0v0' in names
    # The Aegislash (Blade) form variant is preserved separately.
    assert 'Beats PvPoke default Aegislash (Blade) in the 0v0' in names
    assert 'Beats PvPoke default Medicham in the 0v0' in names

    merged = next(c for c in matchup_cats
                  if c.name == 'Beats PvPoke default Forretress in the 0v0')
    # Both variants recorded in matchup_conditions; winning IVs preserved.
    merged_opps = {mc['opponent'] for mc in merged.matchup_conditions}
    assert merged_opps == {'Forretress', 'Forretress (Bug Bite)'}
    assert merged.members == [0, 1]


def test_matchup_variant_diff_iv_set_not_merged():
    """Same base opponent + scenario but a DIFFERENT winning-IV set must NOT
    merge -- the dedup key includes the full member set."""
    data_obj = _make_data_obj()
    n_ivs = data_obj['nIvs']
    nS, nO = 1, 2  # Quagsire, Quagsire (Aqua Tail+Stone Edge)
    scores_flat = [0.0] * (n_ivs * nS * nO)

    def _set(iv, oi, val):
        scores_flat[iv * nS * nO + 0 * nO + oi] = val

    _set(0, 0, 600); _set(1, 0, 700)            # Quagsire: IVs 0,1
    _set(0, 1, 600); _set(2, 1, 700)            # variant: IVs 0,2 -> differs

    matchup_data = {
        'scores_flat': scores_flat,
        'nS': nS, 'nO': nO,
        'scenarios': [(0, 0)],
        'opponents': ['Quagsire', 'Quagsire (Aqua Tail+Stone Edge)'],
        'opp_iv_mode': 'pvpoke',
        'win_threshold': 500,
    }
    cats = build_iv_categories(data_obj, matchup_data=matchup_data)
    matchup_cats = [c for c in cats if c.kind == 'matchup']
    assert len(matchup_cats) == 2  # different IV sets -> stay separate


# ---------------------------------------------------------------------------
# Renderer tests — verify _render_notable_ivs_section produces the
# expected HTML structure for the Annihilape 13/0/11-style case.
# ---------------------------------------------------------------------------

def _make_render_data_obj():
    """Same shape as _make_data_obj but with the extra fields the
    renderer reads (spRanks, etc.)."""
    d = _make_data_obj()
    d['spRanks'] = [10, 1767, 100, 200]
    return d


def test_render_notable_ivs_emits_composite_card():
    data_obj = _make_render_data_obj()
    slayer = _make_slayer_categories(data_obj)
    cats = deep_dive.build_iv_categories(data_obj, slayer)
    html = deep_dive.rendering.render_notable_ivs_section(cats, data_obj, 'pvpoke')

    assert html  # non-empty
    # Composite card title is present
    assert 'Anchors-First Slayer ∩ Top 5%' in html
    # Notability filter checkbox is present
    assert 'dd-notable-only-cb' in html
    assert 'Show only notable categories' in html
    # The composite member (IV 1) is listed with its IV triple
    assert '15/5/10' in html
    # Tradeoff prose mentions the wins ratio (132 is max, this IV has 132 too)
    # Actually IV 1 has 132 wins which IS the max, so prose should say "no tradeoff"
    assert 'no tradeoff' in html


def test_render_notable_ivs_returns_empty_when_no_targets():
    """No composites and no matchups → empty section."""
    data_obj = _make_render_data_obj()
    cats = deep_dive.build_iv_categories(data_obj)  # tier-only
    html = deep_dive.rendering.render_notable_ivs_section(cats, data_obj, 'pvpoke')
    assert html == ''


def test_render_notable_ivs_includes_matchup_card():
    data_obj = _make_render_data_obj()
    n_ivs = data_obj['nIvs']
    nS, nO = 1, 1
    scores_flat = [0.0] * (n_ivs * nS * nO)
    scores_flat[1 * nS * nO + 0 * nO + 0] = 800  # only IV 1 wins

    matchup_data = {
        'scores_flat': scores_flat,
        'nS': nS, 'nO': nO,
        'scenarios': [(2, 2)],
        'opponents': ['Lickitung'],
        'opp_iv_mode': 'rank1',
        'win_threshold': 500,
    }
    cats = deep_dive.build_iv_categories(
        data_obj, matchup_data=matchup_data
    )
    html = deep_dive.rendering.render_notable_ivs_section(cats, data_obj, 'rank1')
    assert 'Beats rank 1 Lickitung in the 2v2' in html
    # bait='bait' (default) should NOT add a 'no bait' annotation
    assert 'no bait' not in html
    assert '15/5/10' in html  # IV 1's triple


def test_render_notable_ivs_card_expand_button():
    """When a category has more members than max_members_shown, every
    member must still be present in the HTML (overflow rows hidden via
    a CSS class so the per-card expand button can reveal them). The
    'Show all N' button must be present for the user to find the
    hidden IVs."""
    # Build a matchup category with 8 winners; default max_members_shown=5.
    n_ivs = 8
    iv_a_iv = list(range(n_ivs))
    data_obj = {
        'nIvs': n_ivs,
        'ivA': iv_a_iv, 'ivD': [0] * n_ivs, 'ivS': [0] * n_ivs,
        'ivAtk': [120.0] * n_ivs, 'ivDef': [100.0] * n_ivs,
        'ivHp': [130] * n_ivs, 'spRanks': list(range(1, n_ivs + 1)),
        'tiers': [], 'ivAllTiers': [[] for _ in range(n_ivs)],
    }
    nS, nO = 1, 1
    scores_flat = [800.0] * (n_ivs * nS * nO)  # everyone wins
    # Make IV 0 lose so it's not a degenerate partition
    scores_flat[0] = 0.0
    matchup_data = {
        'scores_flat': scores_flat,
        'nS': nS, 'nO': nO,
        'scenarios': [(0, 0)],
        'opponents': ['Whiscash'],
        'opp_iv_mode': 'pvpoke',
        'win_threshold': 500,
    }
    cats = deep_dive.build_iv_categories(
        data_obj, matchup_data=matchup_data
    )
    # 7 winners (IVs 1-7), max_members_shown defaults to 5 → 2 hidden
    html = deep_dive.rendering.render_notable_ivs_section(cats, data_obj, 'pvpoke')

    # Every winning IV's triple is in the HTML, even ones beyond
    # max_members_shown.
    for iv_a in range(1, 8):
        assert f'{iv_a}/0/0' in html, f'missing IV {iv_a}/0/0'
    # IV 0 is the loser, should not appear
    assert '0/0/0' not in html
    # Hidden-row marker class is on the overflow rows
    assert 'dd-iv-hidden' in html
    # Expand button is present with the right total count
    assert 'Show all 7' in html
    # JS helper is loaded
    assert 'ddNotableExpand' in html
