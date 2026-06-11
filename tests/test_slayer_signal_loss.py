"""Slayer-table signal-loss remedy (2026-06-11, Michael's 4+3 hybrid):

- Option 4: anchor parents cleared by EVERY emitted build are hoisted
  out of the per-row badge cells (the table emits them once in a
  callout instead).
- Option 3: the remaining per-row badges are rarity-coded by their
  clear rate within the table (<=25% rare, <=60% uncommon).

The Oinkologne GL scatter is the acceptance case: its slayer tags were
non-discriminating because the atk breakpoint sat below premium-bulk
IVs, so every build cleared everything.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.path.join(str(REPO_ROOT), 'scripts'))
_spec = importlib.util.spec_from_file_location(
    "deep_dive_rendering", REPO_ROOT / "scripts" / "deep_dive_rendering.py")
rendering = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(rendering)


def _sub(parent, label='x', kind='damage_breakpoint'):
    return SimpleNamespace(label=label, name=label, kind=kind,
                           parent_display_name=parent.title())


def _rows():
    """4 rows: 'omni' cleared by all; 'mid' by 2/4; 'rare' by 1/4."""
    rows = []
    for i in range(4):
        tags = {'omni': [_sub('omni')]}
        if i < 2:
            tags['mid'] = [_sub('mid')]
        if i == 0:
            tags['rare'] = [_sub('rare')]
        rows.append({'_anchor_tags': tags})
    return rows


def test_parent_clear_stats():
    rates, saturated = rendering._parent_clear_stats(_rows())
    assert saturated == {'omni'}
    assert rates['omni'] == 1.0
    assert rates['mid'] == 0.5
    assert rates['rare'] == 0.25


def test_saturated_parent_skipped_and_rarity_coded():
    rows = _rows()
    rates, saturated = rendering._parent_clear_stats(rows)
    cell, _title = rendering._anchor_tags_cell(
        rows[0], parent_rates=rates, skip_parents=saturated)
    assert 'omni' not in cell          # hoisted (option 4)
    assert 'dd-tag-rare' in cell         # rare badge hot (option 3)
    assert 'dd-tag-uncommon' in cell     # mid badge coded
    # The rate line rides the tooltip REGISTRY (badges emit data-t ids,
    # not inline title text).
    registry = ' '.join(rendering._TOOLTIPS.dump().values()) \
        if isinstance(rendering._TOOLTIPS.dump(), dict) \
        else ' '.join(rendering._TOOLTIPS.dump())
    assert 'cleared by 25%' in registry


def test_row_with_only_saturated_parents_says_common_set():
    rows = _rows()
    rates, saturated = rendering._parent_clear_stats(rows)
    cell, _title = rendering._anchor_tags_cell(
        rows[3], parent_rates=rates, skip_parents=saturated)
    assert 'common set only' in cell


def test_no_context_behaves_as_before():
    rows = _rows()
    cell, _title = rendering._anchor_tags_cell(rows[0])
    # All three badges, no rarity classes (legacy call shape).
    for p in ('omni', 'mid', 'rare'):
        assert p in cell.lower()
    assert 'dd-tag-rare' not in cell and 'dd-tag-uncommon' not in cell
