"""
Tests for ``compute_envelope_positions`` in
``scripts/deep_dive_analysis.py``.

Synthetic cases drive the four live shape classifications plus the sparse
guard, so the Tinkaton UL reference screenshots can be validated against
reproducible numbers rather than eyeballed scatter plots.

The script lives in ``scripts/`` (not the gopvpsim package), imported via
``importlib`` - same pattern as ``test_iv_categories.py``.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = REPO_ROOT / "scripts" / "deep_dive_analysis.py"

_spec = importlib.util.spec_from_file_location("deep_dive_analysis",
                                               ANALYSIS_PATH)
deep_dive_analysis = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive_analysis)

compute_envelope_positions = deep_dive_analysis.compute_envelope_positions


@dataclass
class _Cat:
    """Minimal IVCategory stand-in; the metric only needs .name/.members."""
    name: str
    members: list


def _linear_band(n, slope=0.1, noise_pattern=None):
    """Synthetic avg_score for an N-IV band where score grows with SP rank.

    Ranks are 1-based and SP-rank 1 = best, so the score should *decrease*
    with SP rank in the synthetic layout. We instead use ``score = -slope
    * rank + k + noise`` so the visual "top-right cluster with best scores
    at rank 1" is reproduced. Returned indexing is parallel to sp_ranks.
    """
    k = 560.0
    noise_pattern = noise_pattern or [0.0] * n
    sp_ranks = list(range(1, n + 1))
    scores = [k - slope * r + noise_pattern[i % len(noise_pattern)]
              for i, r in enumerate(sp_ranks)]
    return sp_ranks, scores


def _eval_metric(members, sp_ranks, scores, anchors):
    return compute_envelope_positions(
        [_Cat('cat', members)], sp_ranks, scores, anchors)['cat']


# ---- Shape classification ----

def _disjoint_band_and_members(n_anchors=200, n_members=10, offset=10.0):
    """Disjoint anchor + member IVs sharing the same linear band.

    Members are appended after the anchor block so their local anchor
    neighborhood is pure (no self-contamination via the K-nearest
    average). Returns (sp_ranks, scores, anchors, members). Members
    alternate across SP ranks so the neighborhoods are representative
    of the whole band, not just one end.
    """
    total = n_anchors + n_members
    sp_ranks = [0] * total
    scores = [0.0] * total
    k = 560.0
    slope = 0.1
    # Anchors occupy every other rank from 1..2*n_anchors.
    # Members fill the remaining ranks interleaved among the anchors.
    anchors = []
    members = []
    rank = 1
    for i in range(n_anchors):
        sp_ranks[i] = rank
        scores[i] = k - slope * rank
        anchors.append(i)
        rank += 2
    rank = 2
    for j in range(n_members):
        idx = n_anchors + j
        sp_ranks[idx] = rank
        scores[idx] = k - slope * rank + offset
        members.append(idx)
        rank += 2 * (n_anchors // max(n_members, 1))
    return sp_ranks, scores, anchors, members


def test_envelope_rider_top_tight_cluster():
    """Members uniformly above the band with low spread -> rider-top."""
    sp_ranks, scores, anchors, members = _disjoint_band_and_members(
        n_anchors=200, n_members=10, offset=10.0)
    result = _eval_metric(members, sp_ranks, scores, anchors)
    assert result['shape'] == 'envelope-rider-top'
    # With disjoint members + anchors the expected value comes from pure
    # band neighbors, so mean_delta matches the injected offset within
    # a slope-times-half-rank wobble from uneven SP spacing.
    assert abs(result['mean_delta'] - 10.0) < 0.5
    assert result['spread'] < 2.0
    assert result['n_members'] == len(members)
    assert result['n_anchors'] == len(anchors)


def test_envelope_rider_bottom_tight_cluster():
    """Members uniformly below the band -> rider-bottom."""
    sp_ranks, scores, anchors, members = _disjoint_band_and_members(
        n_anchors=200, n_members=10, offset=-10.0)
    result = _eval_metric(members, sp_ranks, scores, anchors)
    assert result['shape'] == 'envelope-rider-bottom'
    assert abs(result['mean_delta'] + 10.0) < 0.5
    assert result['spread'] < 2.0


def test_elevated_band_crosser_wide_spread():
    """Members elevated on average but spread across the band."""
    n = 200
    sp_ranks, scores = _linear_band(n)
    anchors = list(range(n))
    members = list(range(0, n, 10))
    # Alternate +15, +15, -5, -5: mean ~ +5 but spread is large (~10).
    # |mean_delta| < shape_ratio (1.5) * spread -> band-crosser.
    crossed = list(scores)
    deltas = [15.0, 15.0, -5.0, -5.0]
    for i, m in enumerate(members):
        crossed[m] = scores[m] + deltas[i % len(deltas)]
    result = _eval_metric(members, sp_ranks, crossed, anchors)
    assert result['shape'] == 'elevated-band-crosser'
    assert result['mean_delta'] > 0
    assert result['spread'] > result['mean_delta']  # spread dominates


def test_depressed_band_crosser_wide_spread():
    """Members depressed on average with spread across the band."""
    n = 200
    sp_ranks, scores = _linear_band(n)
    anchors = list(range(n))
    members = list(range(0, n, 10))
    crossed = list(scores)
    deltas = [5.0, 5.0, -15.0, -15.0]
    for i, m in enumerate(members):
        crossed[m] = scores[m] + deltas[i % len(deltas)]
    result = _eval_metric(members, sp_ranks, crossed, anchors)
    assert result['shape'] == 'depressed-band-crosser'
    assert result['mean_delta'] < 0


# ---- Sparse / degenerate guards ----

def test_sparse_when_too_few_members():
    """Members below the min_members floor classify as sparse."""
    n = 100
    sp_ranks, scores = _linear_band(n)
    anchors = list(range(n))
    members = [0, 1]  # default min_members=3
    result = _eval_metric(members, sp_ranks, scores, anchors)
    assert result['shape'] == 'sparse'
    assert result['n_members'] == 2


def test_sparse_when_no_anchors():
    """Empty anchor band -> sparse regardless of member count."""
    n = 100
    sp_ranks, scores = _linear_band(n)
    members = list(range(10))
    result = _eval_metric(members, sp_ranks, scores, anchors=[])
    assert result['shape'] == 'sparse'
    assert result['n_anchors'] == 0


def test_empty_members_skipped():
    """Categories with zero members are dropped entirely."""
    n = 100
    sp_ranks, scores = _linear_band(n)
    anchors = list(range(n))
    out = compute_envelope_positions(
        [_Cat('empty', []), _Cat('ok', list(range(0, n, 10)))],
        sp_ranks, scores, anchors)
    assert 'empty' not in out
    assert 'ok' in out


def test_zero_spread_still_classifies_as_rider():
    """spread==0 shouldn't divide-by-zero; |mean|>=1.5*0 holds for any
    non-zero mean, so the category rides the appropriate edge."""
    n = 100
    sp_ranks, scores = _linear_band(n)
    anchors = list(range(n))
    # Skip 0 from members so each member sits strictly above its local
    # anchor neighborhood (neighbors extend to both sides of each member).
    members = list(range(5, n, 10))
    boosted = list(scores)
    for m in members:
        boosted[m] = scores[m] + 3.0  # exactly +3 for every member
    result = _eval_metric(members, sp_ranks, boosted, anchors)
    # Some tiny spread is expected from boundary asymmetry at the ends of
    # the band; the shape stays "rider-top" because the boost (+3) is
    # large vs residual spread.
    assert result['shape'] == 'envelope-rider-top'


# ---- Multiple categories in one call ----

def test_multiple_categories_returned_independently():
    """Mixed rider/crosser categories in one call preserve per-cat results."""
    n = 200
    sp_ranks, scores = _linear_band(n)
    anchors = list(range(n))

    rider_members = list(range(0, n, 10))
    crosser_members = list(range(5, n, 10))

    scores_adj = list(scores)
    for m in rider_members:
        scores_adj[m] = scores[m] + 12.0
    for i, m in enumerate(crosser_members):
        scores_adj[m] = scores[m] + [15.0, -10.0][i % 2]

    out = compute_envelope_positions(
        [_Cat('rider', rider_members), _Cat('crosser', crosser_members)],
        sp_ranks, scores_adj, anchors)
    assert out['rider']['shape'] == 'envelope-rider-top'
    assert out['crosser']['shape'] in (
        'elevated-band-crosser', 'depressed-band-crosser')
