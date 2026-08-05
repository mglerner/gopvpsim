"""Level-ceiling defaults in gopvpsim.user_collection are league-derived.

DRY review 2026-08-05 entry 9. Four entry points used to carry a
league-blind ``max_level = 51.0`` default (two of them alongside
``league='great'`` in the same signature). Level 51 is only reachable
with best buddy, and only one mon can hold that at a time, so GL/UL
builds top out at 50 -- a bare 51.0 is the "owned mons one level too
high" bug that already had to be fixed once at the deep-dive bake site.

These tests pin the derivation itself (not just today's numbers), so a
future re-hardcode fails here instead of shipping.
"""
import pytest

from gopvpsim.pokemon import (
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL, MAX_CPM_LEVEL, get_pokemon_index, iv_rank,
)
from gopvpsim.user_collection import (
    compute_rank_lookup, ivs_to_stats_at_cap, league_max_level,
    match_mons, max_level_for_cap, parse_csv_text,
)

# A species whose GL-optimal level lands ON the ceiling, so 50 vs 51 is
# observable. Base stats are supplied directly (no gamemaster needed).
_TINY = {'atk': 100, 'def': 100, 'hp': 100}


# ---------------------------------------------------------------------------
# The derivation helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('league', sorted(LEAGUE_MAX_LEVEL))
def test_league_max_level_matches_pokemon_table(league):
    assert league_max_level(league) == LEAGUE_MAX_LEVEL[league]


def test_league_max_level_unknown_league_falls_back_to_cpm_ceiling():
    assert league_max_level('no-such-league') == MAX_CPM_LEVEL


@pytest.mark.parametrize('league', sorted(LEAGUE_CAPS))
def test_max_level_for_cap_round_trips_through_the_league(league):
    assert max_level_for_cap(LEAGUE_CAPS[league]) == LEAGUE_MAX_LEVEL[league]


def test_max_level_for_cap_unknown_cap_falls_back_to_cpm_ceiling():
    assert max_level_for_cap(1234) == MAX_CPM_LEVEL


# ---------------------------------------------------------------------------
# The defaults themselves
# ---------------------------------------------------------------------------

def test_ivs_to_stats_at_cap_default_ceiling_is_the_great_league_cap():
    """Default max_cp is 1500, so the default ceiling must be great's 50.0
    -- not the CPM table's 51.0."""
    stats = ivs_to_stats_at_cap(_TINY['atk'], _TINY['def'], _TINY['hp'],
                                15, 15, 15)
    assert stats['level'] == LEAGUE_MAX_LEVEL['great'] == 50.0
    # The mon is nowhere near the CP cap: only the level ceiling is
    # deciding here, which is exactly what makes the default observable.
    assert stats['cp'] < LEAGUE_CAPS['great']
    explicit = ivs_to_stats_at_cap(_TINY['atk'], _TINY['def'], _TINY['hp'],
                                   15, 15, 15, max_level=51.0)
    assert explicit['level'] == 51.0


def test_ivs_to_stats_at_cap_default_ceiling_follows_the_cap():
    """Master's cap keeps 51.0 -- the derivation is per-league, not a
    blanket downgrade to 50."""
    stats = ivs_to_stats_at_cap(_TINY['atk'], _TINY['def'], _TINY['hp'],
                                15, 15, 15, max_cp=LEAGUE_CAPS['master'])
    assert stats['level'] == LEAGUE_MAX_LEVEL['master'] == 51.0


@pytest.mark.integration
def test_compute_rank_lookup_default_agrees_with_iv_rank_default():
    """compute_rank_lookup is a thin wrapper over iv_rank; with no
    max_level passed, both must resolve the same league ceiling.
    Lechonk's GL-optimal level sits at the ceiling, so a 51.0 default on
    either side changes the stat products and the ranks."""
    lookup = compute_rank_lookup('Lechonk', league='great')
    ranked = iv_rank('Lechonk', league='great')
    assert all(e['level'] <= LEAGUE_MAX_LEVEL['great'] for e in ranked)
    for e in ranked[:50]:
        assert lookup[(e['atk_iv'], e['def_iv'], e['sta_iv'])] == e['rank']


@pytest.mark.integration
def test_match_mons_default_ceiling_is_league_derived():
    """A Lechonk powered past the GL ceiling has no legal GL build:
    power-ups are one-way, so min_level > max_level yields no match. With
    a league-blind 51.0 default the level-50.5 row would still match."""
    idx = get_pokemon_index()
    assert 'Lechonk' in idx
    csv = (
        'Name,Form,CP,Atk IV,Def IV,Sta IV,Level Min,Shadow/Purified,Lucky\n'
        'Lechonk,,600,15,15,15,50.0,0,0\n'
        'Lechonk,,600,15,15,15,50.5,0,0\n'
    )
    thresholds = {'Lechonk': {'Great': {
        'permissive': {'attack': 0, 'defense': 0, 'stamina': 0}}}}
    matched = match_mons(parse_csv_text(csv), thresholds, league='great')
    levels = [r['mon']['level'] for r in matched.get('Lechonk', [])]
    assert levels == [50.0]
    # Explicit override still reaches 51 (best-buddy builds).
    matched_bb = match_mons(parse_csv_text(csv), thresholds,
                            league='great', max_level=51.0)
    assert len(matched_bb.get('Lechonk', [])) == 2
