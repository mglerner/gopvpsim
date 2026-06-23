"""Pareto-efficiency of IV spreads (orgodemir's "efficient IV" concept).

An IV spread is *efficient* (globally Pareto-optimal) if no OTHER spread for
the same species/league dominates it -- where spread j dominates spread i when
j is >= i on all three scaled stats (Attack, Defense, Stamina/HP at the league
cap, shadow multipliers already applied) and strictly > on at least one.
Dominated spreads waste free stats.

Dominance uses STRICT inequality on the "at least one" clause, so identical
(atk, def, hp) triples never dominate each other and all share the same
efficient/not-efficient verdict.

Credit: orgodemir (u/orgodemir),
https://www.reddit.com/r/TheSilphArena/comments/yxzg7f/
"""

from __future__ import annotations


def efficient_frontier(triples):
    """Return a parallel list of booleans flagging the Pareto frontier.

    `triples` is a sequence of (atk, def, hp) scaled-stat triples. Result[i]
    is True iff no other triple j dominates i, i.e. there is NO j with
    atk_j >= atk_i and def_j >= def_i and hp_j >= hp_i and at least one strict
    inequality.

    Strict-inequality dominance: identical triples are all efficient.
    """
    n = len(triples)
    if n == 0:
        return []

    # Sort by atk desc, then def desc, then hp desc. Scanning in this order,
    # every triple seen before the current one has atk >= the current atk, so
    # it is a candidate dominator. For each earlier point we already know
    # atk_seen >= atk_cur; it dominates the current point iff also def >= d and
    # hp >= h with at least one STRICT inequality across all three stats. The
    # strict win can come from atk (atk_seen > atk_cur) or from def/hp, so we
    # keep atk in `seen` and test `(sa > a or sd > d or sh > h)`. This excludes
    # the all-equal case, so identical triples never dominate each other.
    #
    # We scan against `seen` (every earlier triple), not just the confirmed-
    # efficient ones: if a dominated point P would dominate the current point,
    # then by transitivity whatever dominates P also dominates the current
    # point, so including dominated candidates never yields a wrong verdict. The
    # O(n^2) worst case over 4096 IVs is a few ms at build time.
    order = sorted(range(n),
                   key=lambda i: (triples[i][0], triples[i][1], triples[i][2]),
                   reverse=True)

    efficient = [True] * n
    seen = []  # (atk, def, hp) of every triple already scanned (atk >= current)
    for idx in order:
        a, d, h = triples[idx]
        for sa, sd, sh in seen:
            if sd >= d and sh >= h and (sa > a or sd > d or sh > h):
                efficient[idx] = False
                break
        seen.append((a, d, h))

    return efficient
