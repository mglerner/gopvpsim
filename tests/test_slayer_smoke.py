"""Smoke test for the slayer iteration pipeline.

Runs iterative_slayer_discovery with a tiny config (2 opponents, 1 round,
pool of 5) to verify the extracted module loads correctly and produces
the expected output structure.  Catches missing imports and broken
cross-module references.  Runs in ~10-15 seconds.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Load deep_dive.py as a module (it's a script, not a package).
# This also triggers the slayer/analysis/rendering module imports
# and the compute_iv_metadata injection.
DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)

from gopvpsim.data import get_default_moveset
from gopvpsim.pokemon import pvpoke_default_ivs


def test_slayer_iteration_smoke():
    """Minimal slayer iteration: 2 opponents, 1 round, pool of 5."""
    species = "Medicham"
    league = "great"
    shadow = False

    fast_id, charged_ids = get_default_moveset(species, league, shadow=shadow)
    _lv, *opp_iv = pvpoke_default_ivs(species, league)
    opp_iv = tuple(opp_iv)

    result = deep_dive.iterative_slayer_discovery(
        species, league, shadow,
        fast_id, charged_ids,
        shield_scenarios=[(1, 1)],
        initial_opp_iv=opp_iv,
        max_rounds=1,
        top_per_round=5,
    )

    # Verify return structure
    assert isinstance(result, dict)
    assert 'history' in result
    assert 'final' in result
    assert 'rounds_run' in result
    assert 'converged' in result
    assert result['rounds_run'] >= 1
    assert len(result['final']) > 0

    # Verify each survivor has expected fields
    for survivor in result['final']:
        assert 'focal_idx' in survivor
        assert 'iv' in survivor
        assert 'atk' in survivor
        assert 'def_' in survivor
        assert 'total_wins' in survivor
        assert 'frac_wins' in survivor

    # The graded metric must honor the pool cap: ties beyond
    # top_per_round only survive at EXACT (frac_wins, avg_score)
    # equality with the cutoff row, so any overflow rows must match
    # the cutoff key exactly.
    final = result['final']
    if len(final) > 5:
        cut = final[4]
        for r in final[5:]:
            assert (r['frac_wins'], r['avg_score']) == \
                (cut['frac_wins'], cut['avg_score'])

    # all_scores covers the full focal IV space (dense mirror-wins
    # surface for the archetype builder / winsMirror axis).
    assert 'all_scores' in result
    assert len(result['all_scores']) >= 4000  # ~4096 valid IVs
    sample = next(iter(result['all_scores'].values()))
    assert len(sample) == 4  # (total_wins, frac_wins, avg_score, n_pairs)


def test_cut_pool_exact_ties_only():
    """_cut_pool keeps the cap except on exact (frac_wins, avg_score)
    ties with the cutoff row."""
    import importlib.util as _ilu
    slayer_path = REPO_ROOT / "scripts" / "deep_dive_slayer.py"
    spec = _ilu.spec_from_file_location("dds", slayer_path)
    dds = _ilu.module_from_spec(spec)
    spec.loader.exec_module(dds)

    def row(frac, avg):
        return {'frac_wins': frac, 'avg_score': avg}

    # Sorted desc by (frac, avg). Cutoff row (index 2) ties rows 3-4
    # exactly; row 5 differs only in avg_score and must be dropped.
    scores = [row(3.0, 700), row(2.5, 650), row(2.0, 600),
              row(2.0, 600), row(2.0, 600), row(2.0, 599)]
    top = dds._cut_pool(scores, 3)
    assert len(top) == 5
    assert top[-1]['avg_score'] == 600

    # No ties at the cutoff: cap holds exactly.
    scores2 = [row(3.0, 700), row(2.5, 650), row(2.0, 600), row(1.5, 600)]
    assert len(dds._cut_pool(scores2, 3)) == 3

    # Fewer rows than the cap: everything kept.
    assert len(dds._cut_pool(scores2, 10)) == 4


def test_build_slayer_archetypes_smoke():
    """Verify build_slayer_archetypes on a synthetic sweep-results list."""
    results = [
        {'atk_iv': 15, 'def_iv': 0, 'sta_iv': 0, 'atk': 110.0,
         'def_': 120.0, 'hp': 130, 'avg_score': 550.0},
        {'atk_iv': 0, 'def_iv': 15, 'sta_iv': 15, 'atk': 95.0,
         'def_': 140.0, 'hp': 145, 'avg_score': 520.0},
        {'atk_iv': 10, 'def_iv': 10, 'sta_iv': 10, 'atk': 105.0,
         'def_': 130.0, 'hp': 138, 'avg_score': 530.0},
    ]

    # No anchors: Anchors-First is empty, CMP-First ranks by atk.
    categories = deep_dive.build_slayer_archetypes(results, cmp_first_n=2)
    assert isinstance(categories, dict)
    assert categories['Anchors-First Slayer'] == []
    cf = categories['CMP-First Slayer']
    assert len(cf) == 2
    assert cf[0]['iv'] == (15, 0, 0)  # max atk first
    assert cf[0]['n_counted_parents'] == 0

    # With an explicit anchor at atk > 100: two IVs clear it; the
    # Anchors-First archetype is exactly those, CMP-ranked.
    from gopvpsim.anchors import ResolvedAnchor
    anchor = ResolvedAnchor(
        name='opp_brkp_test', parent='opp_brkp_test',
        kind='damage_breakpoint', threshold_value=100.0,
        target_stat='atk', strict=True, label='test->100',
    )
    categories = deep_dive.build_slayer_archetypes(
        results, resolved_anchors=[anchor], cmp_first_n=2)
    af = categories['Anchors-First Slayer']
    assert [r['iv'] for r in af] == [(15, 0, 0), (10, 10, 10)]
    assert all(r['n_parents_cleared'] == 1 for r in af)
    assert all(r['n_counted_parents'] == 1 for r in af)
    assert 'opp_brkp_test' in af[0]['_anchor_tags']
    # Top-Mirror CMP%: cohort is all 3 IVs (ties count as beats).
    assert af[0]['top_mirror_cmp'] == 100.0


def test_build_slayer_archetypes_auto_anchor_selectivity():
    """Non-selective auto anchors (>=50% pass rate) must not count for
    Anchors-First membership; explicit anchors always count."""
    from gopvpsim.anchors import ResolvedAnchor
    results = [
        {'atk_iv': a, 'def_iv': 0, 'sta_iv': 0, 'atk': 100.0 + a,
         'def_': 120.0, 'hp': 130, 'avg_score': 500.0 + a}
        for a in range(4)
    ]
    # auto anchor passed by all 4 IVs -> not counted.
    easy_auto = ResolvedAnchor(
        name='auto_easy', parent='auto_easy', kind='damage_breakpoint',
        threshold_value=99.0, target_stat='atk', label='easy')
    categories = deep_dive.build_slayer_archetypes(
        results, resolved_anchors=[easy_auto])
    assert categories['Anchors-First Slayer'] == []
    # Same threshold as an explicit anchor -> counted, all 4 are members.
    easy_explicit = ResolvedAnchor(
        name='opp_easy', parent='opp_easy', kind='damage_breakpoint',
        threshold_value=99.0, target_stat='atk', label='easy')
    categories = deep_dive.build_slayer_archetypes(
        results, resolved_anchors=[easy_explicit])
    assert len(categories['Anchors-First Slayer']) == 4


def test_split_movesets_cache_and_file_creation():
    """Verify _build_split_file_list and _filter_moveset_data_for_split work.

    Exercises the split-movesets file planning and data filtering without
    running full HTML generation (which requires rich simulation data).
    """
    import os
    import tempfile

    # Meta entries are tuples: (atk_iv, def_iv, sta_iv, level, cp, atk, def_, hp, stat_product)
    fake_meta = [(0, 0, 0, 50.0, 1400, 100.0, 120.0, 130, 100*120*130)]
    moveset_data = [
        {'label': 'COUNTER / DYNAMIC_PUNCH, POWER_UP_PUNCH',
         'scores': {'pvpoke': [500]}, 'meta': fake_meta},
        {'label': 'PSYCHO_CUT / ICE_PUNCH, DYNAMIC_PUNCH',
         'scores': {'pvpoke': [500]}, 'meta': fake_meta},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, 'test.html')
        split_files = deep_dive._build_split_file_list(moveset_data, 0, base_path)

        assert len(split_files) == 2
        assert split_files[0]['moveset_idx'] == 0
        assert split_files[1]['moveset_idx'] == 1

        # Each split file contains only the current moveset (ref hover
        # is intentionally dropped in split mode to avoid doubling size).
        filtered, ref_idx = deep_dive._filter_moveset_data_for_split(
            moveset_data, 1, 0,
        )
        assert len(filtered) == 1
        assert filtered[0]['label'] == moveset_data[1]['label']

        filtered, ref_idx = deep_dive._filter_moveset_data_for_split(
            moveset_data, 0, 0,
        )
        assert len(filtered) == 1
        assert filtered[0]['label'] == moveset_data[0]['label']
