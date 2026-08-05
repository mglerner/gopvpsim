"""owned_breakdown.rank1_spread must be iv_rank's rank 1 (DRY review 2026-08-05).

The old hand-rolled loop diverged from gopvpsim.pokemon.iv_rank on the
tie-break (first-enumerated lowest-IV spread vs PvPoke's higher-IV-sum
rule) and missed the Aegislash (Blade) whole-level rounding; 9 of the
top-80 GL meta species disagreed with the website column and the
gobattlekit bundle. rank1_spread is now a thin wrapper; this pins the
contract so a re-hand-roll re-fails here.

Uses the cached gamemaster (same dependency as test_battle.py).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import LEAGUE_MAX_LEVEL, iv_rank  # noqa: E402
from owned_breakdown import rank1_spread  # noqa: E402

# Divergent-under-the-old-code species from the review's reproduction,
# plus the whole-level-rounding special case.
CASES = [
    ('Umbreon', 'great'),
    ('Medicham', 'great'),
    ('Talonflame', 'great'),
    ('Aegislash (Blade)', 'great'),
    ('Registeel', 'ultra'),
]


@pytest.mark.parametrize('species,league', CASES)
def test_rank1_spread_is_iv_rank_rank1(species, league):
    max_level = LEAGUE_MAX_LEVEL.get(league, 51.0)
    top = iv_rank(species, league=league, max_level=max_level)[0]
    assert rank1_spread(species, league, max_level) == (
        top['atk_iv'], top['def_iv'], top['sta_iv'])


def test_tie_break_prefers_higher_iv_sum():
    # The property the old code violated: among equal stat products at
    # the top, the canonical rank 1 has the max IV sum. Verify on a
    # species the review reproduced (Medicham GL has floor-rounding ties).
    entries = iv_rank('Medicham', league='great',
                      max_level=LEAGUE_MAX_LEVEL['great'])
    top_sp = entries[0]['stat_product']
    tied = [e for e in entries if e['stat_product'] == top_sp]
    best_sum = max(e['atk_iv'] + e['def_iv'] + e['sta_iv'] for e in tied)
    got = entries[0]
    assert got['atk_iv'] + got['def_iv'] + got['sta_iv'] == best_sum
