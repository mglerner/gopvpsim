"""cramorant_policy_lab.load_pool must load BOTH league pools.

Pre-fix (2026-09-10..12): load_pool('great') raised
``AttributeError: 'list' object has no attribute 'split'`` on the two
Thievul rows of opponent_pools/gl_top50_plus_cs.txt that carry a
``charged=`` override -- _parse_opponent_pool_line returns that override
as a list, and the lab still split it as a string. The Great League half
of the PoGoDives strat certification (and the rebalance tripwire that
points at it) was un-runnable.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

pytestmark = pytest.mark.integration  # get_default_moveset reads rankings


@pytest.mark.parametrize('league, floor', [('great', 60), ('ultra', 50)])
def test_load_pool_loads_both_leagues(league, floor):
    from cramorant_policy_lab import load_pool
    pool, _skipped = load_pool(league)
    assert len(pool) >= floor
    for _display, _base, _shadow, fast, charged in pool:
        assert isinstance(fast, str) and fast
        assert isinstance(charged, list) and all(isinstance(c, str)
                                                 for c in charged)


def test_great_pool_keeps_the_moveset_override_rows():
    from cramorant_policy_lab import load_pool
    pool, _ = load_pool('great')
    thievul = [row for row in pool if row[1] == 'Thievul']
    # Two Thievul rows since 6a96aa8, distinguished by their charged sets.
    assert len(thievul) >= 2
    assert len({tuple(row[4]) for row in thievul}) == len(thievul)
