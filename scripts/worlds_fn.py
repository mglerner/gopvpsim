#!/usr/bin/env python
"""Amber-screen false-negative rate from the Tier-2 clean-sample grids.

Plan: "The amber screen's false-negative rate is MEASURED (full grids
on ~15 sampled 'clean' pairs) and printed." This module is a READ-ONLY
consumer of the Tier-2 grids and deliberately lives OUTSIDE
worlds_tier2._TIER2_SOURCE_FILES -- an FN-analysis edit must not stale
the Tier-2 manifest (the same producer/consumer boundary as
worlds_render_data vs worlds_planes; adding these functions to
worlds_tier2.py mid-bake would have invalidated the running bake's
stamp, which is exactly the mistake the boundary exists to prevent).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

import worlds_tier2 as t2  # noqa: E402


def grid_decided(grid):
    """(decided, max_minority_share, max_spread_impact) over the
    focal-top-512 x opp-top-512 block.

    decided: some scenario is non-constant (someone wins AND someone
    loses) -- the full-grid ground truth the Tier-1 two-probe-spread
    screen approximates.

    max_minority_share: the largest minority side of any scenario's
    CELL block, whichever side it is (a 3-cell minority of 262k is
    'technically decided, negligibly'). NB this is a share of
    spread-PAIR cells, not of spreads, and the minority can be the
    WINNING side -- do not render it as 'at most X% of your IVs lose'
    (the first hub wording made exactly that misread easy;
    verify catch 2026-08-11).

    max_spread_impact: the reader-relevant quantity -- the largest
    fraction, over scenarios, of the FOCAL top-512 spreads whose
    outcome is not uniform across the opponent block (their result
    depends on the opponent's IV roll)."""
    if grid is None:
        return False, 0.0, 0.0
    w = grid['won'][:512][:, grid['top512_mask'], :]
    decided, worst_cell, worst_impact = False, 0.0, 0.0
    n_rows = w.shape[0]
    for si in range(w.shape[2]):
        blk = w[:, :, si]
        n_true = int(blk.sum())
        if 0 < n_true < blk.size:
            decided = True
            worst_cell = max(worst_cell,
                             min(n_true, blk.size - n_true) / blk.size)
            row_sums = blk.sum(axis=1)
            mixed_rows = int(((row_sums > 0)
                              & (row_sums < blk.shape[1])).sum())
            worst_impact = max(worst_impact, mixed_rows / n_rows)
    return decided, worst_cell, worst_impact


def fn_rate(tier2_dir=t2.TIER2_DIR):
    """None until clean-sample grids exist; else
    {'n', 'fn', 'pairs': [((a, b), decided, worst_share), ...]}."""
    manifest = t2.load_manifest(tier2_dir)
    if manifest is None:
        return None
    by_pair = {}
    for key, ent in manifest.get('entries', {}).items():
        if not ent.get('clean_sample'):
            continue
        focal, opp, _bait = key.split('|')
        by_pair.setdefault(tuple(sorted((focal, opp))), []).append(ent)
    complete = {p: ents for p, ents in by_pair.items() if len(ents) == 4}
    if not complete:
        return None
    rows = []
    for pair, ents in sorted(complete.items()):
        decided, worst_cell, worst_impact = False, 0.0, 0.0
        for ent in ents:
            d, wc, wi = grid_decided(t2.read_grid(ent['file'], tier2_dir))
            decided = decided or d
            worst_cell = max(worst_cell, wc)
            worst_impact = max(worst_impact, wi)
        rows.append((pair, decided, worst_cell, worst_impact))
    return {'n': len(rows), 'fn': sum(1 for r in rows if r[1]),
            'pairs': rows}
