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


def test_categorize_slayers_smoke():
    """Verify categorize_slayers runs on a minimal survivor list."""
    survivors = [
        {'focal_idx': 0, 'iv': (15, 0, 0), 'atk': 110.0, 'def_': 120.0,
         'hp': 130, 'total_wins': 5, 'avg_score': 550.0, 'n_pairs': 5},
        {'focal_idx': 1, 'iv': (0, 15, 15), 'atk': 95.0, 'def_': 140.0,
         'hp': 145, 'total_wins': 3, 'avg_score': 520.0, 'n_pairs': 5},
        {'focal_idx': 2, 'iv': (10, 10, 10), 'atk': 105.0, 'def_': 130.0,
         'hp': 138, 'total_wins': 4, 'avg_score': 530.0, 'n_pairs': 5},
    ]

    categories = deep_dive.categorize_slayers(survivors)
    assert isinstance(categories, dict)
    # Should always have Bulk Slayer (structural heuristic)
    assert 'Bulk Slayer' in categories


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
