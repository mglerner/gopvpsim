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
    """(decided, max_minority_share) over the focal-top-512 x
    opp-top-512 block: decided iff some scenario is non-constant
    (someone wins AND someone loses) -- the full-grid ground truth the
    Tier-1 two-probe-spread screen approximates. The minority share
    says how big the losing minority is (a 3-cell minority of 262k is
    'technically decided, negligibly')."""
    if grid is None:
        return False, 0.0
    w = grid['won'][:512][:, grid['top512_mask'], :]
    decided, worst = False, 0.0
    for si in range(w.shape[2]):
        n_true = int(w[:, :, si].sum())
        n = w[:, :, si].size
        if 0 < n_true < n:
            decided = True
            worst = max(worst, min(n_true, n - n_true) / n)
    return decided, worst


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
        decided, worst = False, 0.0
        for ent in ents:
            d, ws = grid_decided(t2.read_grid(ent['file'], tier2_dir))
            decided = decided or d
            worst = max(worst, ws)
        rows.append((pair, decided, worst))
    return {'n': len(rows), 'fn': sum(1 for _p, d, _w in rows if d),
            'pairs': rows}
