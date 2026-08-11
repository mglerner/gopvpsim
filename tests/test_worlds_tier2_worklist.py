"""worlds_tier2 worklist semantics: clean means clean in BOTH directions.

Regression for the 2026-08-10 sampler bug: a pair with ONE amber
direction was admitted to the clean (FN-measurement) sample because the
set-comprehension tested directions independently -- 7 of the first 15
"clean" pairs were amber-worklist members, contaminating the
preliminary FN reading (the two dramatic "misses" were true positives).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import worlds_tier2 as t2  # noqa: E402


def _cell(amber):
    return SimpleNamespace(missing=False, amber=amber)


def test_clean_sample_requires_both_directions_clean():
    cells = {
        ('a', 'b'): _cell(True), ('b', 'a'): _cell(False),   # half-amber
        ('a', 'c'): _cell(False), ('c', 'a'): _cell(False),  # clean
        ('b', 'c'): _cell(True), ('c', 'b'): _cell(True),    # amber
    }
    sample = t2.clean_sample([], cells, 10)
    assert sample == [('a', 'c')]
    # And the amber worklist takes the complement's amber side, so the
    # two sets can never overlap.
    amber = {tuple(sorted(k)) for k, c in cells.items()
             if not c.missing and c.amber}
    assert not (set(sample) & amber)
