"""cramorant_certify: strict-bar metrics from dive tensors.

Pure-function pins on synthetic tensors (no page, no node); the real-page
run is the ship instrument itself (scripts/cramorant_certify.py
--selftest N proves it against live sims).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from cramorant_certify import (cell_stats, check_record, page_key,  # noqa: E402
                               page_sha256, per_opponent)


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


def test_check_record_publish_guard(tmp_path):
    """Publish guard (2026-09-27): every rendered page must be in the
    certification record with an unchanged sha256, and the record must be
    clean. Pre-guard a fifth moveset page could ship with no certification
    (check_record did not exist)."""
    gl = tmp_path / 'cramorant-great-league'
    gl.mkdir()
    a, b = gl / 'index.html', gl / 'index_m4_peck_fly_surf.html'
    a.write_text('page a')
    b.write_text('page b')
    assert page_key(b) == 'great/index_m4_peck_fly_surf.html'
    clean = {'bar_failures': 0, 'exemption_violations': 0,
             'selftest_mismatches': 0,
             'pages': {page_key(a): {'sha256': page_sha256(a)},
                       page_key(b): {'sha256': page_sha256(b)}}}
    assert check_record(clean, str(tmp_path), ['great']) == []
    # A new, never-certified moveset page.
    (gl / 'index_m5_peck_new.html').write_text('page c')
    probs = check_record(clean, str(tmp_path), ['great'])
    assert len(probs) == 1 and 'index_m5_peck_new.html' in probs[0]
    (gl / 'index_m5_peck_new.html').unlink()
    # A re-rendered page (different bytes) is uncertified.
    b.write_text('page b, re-baked')
    assert any('changed' in p for p in check_record(clean, str(tmp_path), ['great']))
    b.write_text('page b')
    # A dirty or pre-guard record never passes.
    assert check_record({**clean, 'bar_failures': 8}, str(tmp_path), ['great'])
    assert check_record({k: v for k, v in clean.items() if k != 'pages'},
                        str(tmp_path), ['great'])
    # No rendered pages at all is a failure, not a vacuous pass.
    assert check_record(clean, str(tmp_path / 'nowhere'), ['great'])
