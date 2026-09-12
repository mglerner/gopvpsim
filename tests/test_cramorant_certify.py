"""cramorant_certify: strict-bar metrics from dive tensors.

Pure-function pins on synthetic tensors (no page, no node); the real-page
run is the ship instrument itself (scripts/cramorant_certify.py
--selftest N proves it against live sims).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from cramorant_certify import cell_stats, per_opponent  # noqa: E402


def _pair(n_opp=3):
    pv = np.full((4096, 9, n_opp), 480, dtype=np.uint16)
    pg = pv.copy()
    return pv, pg


def test_cell_stats_counts_flips_both_ways_and_mean():
    pv, pg = _pair()
    # scenario 4: opponent 0 flips 480 -> 520 for the first 100 IVs (gained),
    # opponent 1 flips 480 -> 400 for 10 IVs, after being a win (pv 510).
    pg[:100, 4, 0] = 520
    pv[:10, 4, 1] = 510
    pg[:10, 4, 1] = 400
    st = cell_stats(pv, pg, 3, 4)
    assert (st['gained'], st['lost'], st['net']) == (100, 10, 90)
    assert st['changed'] == 110
    assert st['cells'] == 4096 * 3
    expected_mean = (100 * 40 + 10 * (-110)) / (4096 * 3)
    assert abs(st['mean'] - expected_mean) < 1e-9
    # untouched scenario: byte-identical tiers
    st0 = cell_stats(pv, pg, 3, 0)
    assert (st0['net'], st0['mean'], st0['changed']) == (0, 0.0, 0)


def test_cell_stats_iv_mask_restricts_to_top_sp():
    pv, pg = _pair()
    pg[:100, 4, 0] = 520
    mask = np.zeros(4096, dtype=bool)
    mask[50:] = True
    st = cell_stats(pv, pg, 3, 4, mask)
    assert st['gained'] == 50 and st['cells'] == (4096 - 50) * 3


def test_per_opponent_lists_only_negative_opponents_worst_first():
    pv, pg = _pair()
    pv[:, 8, 0] = 510; pg[:, 8, 0] = 510; pg[:20, 8, 0] = 400   # A: -20 net
    pg[:, 8, 1] = 481                                          # B: +0 net, +1 mean
    pv[:, 8, 2] = 510; pg[:, 8, 2] = 510; pg[:5, 8, 2] = 400    # C: -5 net
    offs = per_opponent(pv, pg, ['A', 'B', 'C'], 8)
    assert [o['opp'] for o in offs] == ['A', 'C']
    assert offs[0]['net'] == -20 and offs[1]['net'] == -5
