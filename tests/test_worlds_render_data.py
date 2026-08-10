"""worlds_render_data: plane -> matrix/cheat-sheet aggregation.

Synthetic planes with hand-computable fractions; strict green/red/amber
classification; the missing-plane path renders as missing rather than
silently skipping (never-present-known-wrong).
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402

SCEN = [(a, b) for a in range(3) for b in range(3)]


def _write_synthetic(planes_dir, focal_id, opp_id, bait, won, score):
    """One synthetic 2-spread x 4-cohort x 9-scenario plane."""
    arrs = wp.plane_arrays(
        won, score,
        focal_ivs=[(0, 15, 15), (12, 1, 15)],
        focal_levels=[24.0, 25.5],
        opp_ivs=[(0, 15, 14), (1, 15, 11), (4, 1, 12), (15, 15, 15)],
        opp_levels=[24.0, 24.0, 25.0, 22.5],
        scenarios=SCEN,
        top512_mask=[True, True, True, False],
        atkband_mask=[True, False, True, True])
    wp.write_plane(wp.plane_filename(focal_id, opp_id, bait), arrs,
                   planes_dir)


@pytest.fixture
def planes_dir(tmp_path):
    return tmp_path / 'planes'


def test_fractions_and_strict_classification(planes_dir):
    # Scenario 0: focal beats all 4 -> green everywhere.
    # Scenario 1: beats none -> red.
    # Scenario 2: beats cohort rows 0,1 only -> top512 frac 2/3 amber,
    #   atkband (rows 0,2,3) frac 1/3 amber.
    won = np.zeros((2, 4, 9), dtype=bool)
    won[:, :, 0] = True
    won[:, (0, 1), 2] = True
    score = np.where(won, 700, 300).astype(np.uint16)
    for bait in (True, False):
        _write_synthetic(planes_dir, 'a', 'b', bait, won, score)

    cell = wrd.build_cell('a', 'b', planes_dir)
    assert not cell.missing
    h = cell.headline           # rank1 spread, top512 cohort, bait on
    assert h.n == 3
    assert h.frac[0] == 1.0 and h.status[0] == 'green'
    assert h.frac[1] == 0.0 and h.status[1] == 'red'
    assert h.frac[2] == pytest.approx(2 / 3) and h.status[2] == 'amber'
    ab = cell.slices[('rank1', 'atkband', True)]
    assert ab.n == 3 and ab.frac[2] == pytest.approx(1 / 3)
    # Margin derives from score with sign (700-500 / 300-500), never wraps.
    assert h.margin_lo[0] == 200 and h.margin_hi[1] == -200
    assert cell.amber and 2 in cell.amber_scenarios()


def test_all_green_cell_is_not_amber(planes_dir):
    won = np.ones((2, 4, 9), dtype=bool)
    score = np.full(won.shape, 900, dtype=np.uint16)
    for bait in (True, False):
        _write_synthetic(planes_dir, 'a', 'b', bait, won, score)
    cell = wrd.build_cell('a', 'b', planes_dir)
    assert not cell.amber
    assert cell.amber_scenarios() == []
    assert set(cell.headline.status) == {'green'}


def test_511_of_512_style_cell_is_amber(planes_dir):
    """One losing spread in a big cohort IS IV-decided -- no epsilon."""
    won = np.ones((2, 4, 9), dtype=bool)
    won[0, 3, 4] = False        # rank1 spread, scenario 1-1, atkband row
    score = np.where(won, 700, 499).astype(np.uint16)
    for bait in (True, False):
        _write_synthetic(planes_dir, 'a', 'b', bait, won, score)
    cell = wrd.build_cell('a', 'b', planes_dir)
    assert cell.amber and cell.amber_scenarios() == [4]
    # headline (top512, rows 0-2) doesn't see row 3 -> still green there
    assert cell.headline.status[4] == 'green'
    assert cell.slices[('rank1', 'atkband', True)].status[4] == 'amber'


def test_spread_flip_is_amber_even_when_both_slices_uniform(planes_dir):
    """Focal-axis decidedness: rank1 loses the WHOLE cohort while
    maxatk512 beats the WHOLE cohort in scenario 3 -- every slice is
    uniform (no within-cohort mix) yet the pair is IV-decided. The
    within-cohort test alone missed this class (2026-08-10)."""
    won = np.zeros((2, 4, 9), dtype=bool)
    won[1, :, 3] = True          # maxatk512 spread sweeps scenario 1-0
    score = np.where(won, 700, 300).astype(np.uint16)
    for bait in (True, False):
        _write_synthetic(planes_dir, 'a', 'b', bait, won, score)
    cell = wrd.build_cell('a', 'b', planes_dir)
    # No slice shows a within-cohort mix...
    assert all('amber' not in s.status for s in cell.slices.values())
    # ...but the cell is amber via the spread flip.
    assert cell.spread_flip_scenarios() == [3]
    assert cell.amber
    assert cell.amber_scenarios() == [3]


def test_missing_plane_marks_cell_missing(planes_dir):
    won = np.ones((2, 4, 9), dtype=bool)
    score = np.full(won.shape, 700, dtype=np.uint16)
    _write_synthetic(planes_dir, 'a', 'b', True, won, score)  # bait only
    cell = wrd.build_cell('a', 'b', planes_dir)
    assert cell.missing                     # nobait plane absent
    entries = [{'species_id': 'a'}, {'species_id': 'b'}]
    cells = {('a', 'b'): cell, ('b', 'a'): wrd.build_cell('b', 'a',
                                                          planes_dir)}
    n_missing, missing = wrd.coverage_check(cells, entries)
    assert n_missing == 2 and ('a', 'b') in missing
    rows = wrd.matrix_summary(cells, entries)
    assert rows[('b', 'a')]['missing'] is True


def test_matrix_summary_shape_nontrivial(planes_dir):
    """Oracle-parity style non-triviality: the summary must carry real
    per-scenario variation, not a degenerate constant."""
    won = np.zeros((2, 4, 9), dtype=bool)
    won[:, :, ::2] = True
    score = np.where(won, 600, 400).astype(np.uint16)
    for f, o in (('a', 'b'), ('b', 'a')):
        for bait in (True, False):
            _write_synthetic(planes_dir, f, o, bait, won, score)
    entries = [{'species_id': 'a'}, {'species_id': 'b'}]
    cells = wrd.build_all_cells(entries, planes_dir)
    rows = wrd.matrix_summary(cells, entries)
    assert len(rows) == 2
    row = rows[('a', 'b')]
    assert row['missing'] is False
    assert set(row['status']) == {'green', 'red'}
    assert len(set(row['frac'])) == 2       # non-trivial variation
