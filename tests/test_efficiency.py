"""Tests for the Pareto efficient-IV frontier helper."""

import random

from gopvpsim.efficiency import efficient_frontier


def _brute_force(triples):
    """Reference O(n^2) frontier: i efficient iff no j strictly dominates it."""
    n = len(triples)
    out = [True] * n
    for i in range(n):
        ai, di, hi = triples[i]
        for j in range(n):
            if i == j:
                continue
            aj, dj, hj = triples[j]
            if aj >= ai and dj >= di and hj >= hi and (aj > ai or dj > di or hj > hi):
                out[i] = False
                break
    return out


def test_empty():
    assert efficient_frontier([]) == []


def test_dominated_pair():
    # B is strictly worse on all three -> not efficient; A is efficient.
    triples = [(10, 10, 10), (9, 9, 9)]
    assert efficient_frontier(triples) == [True, False]


def test_identical_triples_both_efficient():
    # Strict-inequality dominance: identical triples never dominate each other.
    triples = [(5, 5, 5), (5, 5, 5)]
    assert efficient_frontier(triples) == [True, True]


def test_3d_tradeoff_both_efficient():
    # A beats B on atk+def; B beats A on hp -> neither dominates -> both efficient.
    a = (10, 10, 1)
    b = (1, 1, 10)
    assert efficient_frontier([a, b]) == [True, True]


def test_partial_tie_not_dominating():
    # Equal atk+def, equal hp on two; a third ties atk+def but lower hp -> dominated.
    triples = [(5, 5, 5), (5, 5, 5), (5, 5, 4)]
    assert efficient_frontier(triples) == [True, True, False]


def test_one_strict_win_dominates():
    # Equal on two stats, j strictly higher on the third -> i dominated.
    triples = [(5, 5, 5), (5, 5, 6)]
    assert efficient_frontier(triples) == [False, True]


def test_hand_set_matches_brute_force():
    triples = [
        (10, 10, 10),  # global best -> efficient
        (10, 9, 11),   # tradeoff vs best -> efficient
        (9, 9, 9),     # dominated by best -> not
        (11, 8, 8),    # best atk -> efficient
        (8, 11, 8),    # best def -> efficient
        (8, 8, 12),    # best hp -> efficient
        (7, 7, 7),     # dominated -> not
    ]
    assert efficient_frontier(triples) == _brute_force(triples)


def test_random_matches_brute_force():
    rng = random.Random(20260622)
    for _ in range(50):
        n = rng.randint(0, 40)
        triples = [
            (rng.randint(0, 6), rng.randint(0, 6), rng.randint(0, 6))
            for _ in range(n)
        ]
        assert efficient_frontier(triples) == _brute_force(triples), triples
