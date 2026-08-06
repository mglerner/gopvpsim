"""One descriptor owns every per-league fact (DRY review 2026-08-05 entry 13 / L6).

Before the descriptor, four hand-maintained dicts carried overlapping league
facts and had drifted: ``pokemon.LEAGUE_CAPS`` and ``data._LEAGUE_CP`` were
missing 'little' while ``pokemon.LEAGUE_CP`` and ``pokemon.LEAGUE_MAX_LEVEL``
had it, so every ``LEAGUE_CAPS[league]`` path raised KeyError on a league the
docstrings advertised. These tests pin the single table and both of the
KeyError paths the review reproduced live.
"""
import pytest

import gopvpsim.data as data
from gopvpsim.pokemon import (
    LEAGUES, LEAGUE_CAPS, LEAGUE_CP, LEAGUE_MAX_LEVEL, MAX_CPM_LEVEL,
    Pokemon, bestbuddy_caps, iv_rank,
)

# (cp cap, max power-up level, has open non-cup rankings)
EXPECTED = {
    'little': (500,   51.0, False),
    'great':  (1500,  50.0, True),
    'ultra':  (2500,  50.0, True),
    'master': (10000, 51.0, True),
}


def test_descriptor_rows():
    assert {name: tuple(row) for name, row in LEAGUES.items()} == EXPECTED


def test_derived_dicts_cover_exactly_the_descriptor():
    assert set(LEAGUE_CAPS) == set(LEAGUES)
    assert set(LEAGUE_MAX_LEVEL) == set(LEAGUES)
    assert LEAGUE_CAPS == {n: row.cp for n, row in LEAGUES.items()}
    assert LEAGUE_MAX_LEVEL == {n: row.max_level for n, row in LEAGUES.items()}


def test_league_cp_is_league_caps():
    """The two names were the drifting pair; there is one set of CP caps."""
    assert LEAGUE_CP is LEAGUE_CAPS


def test_little_is_a_full_member():
    assert LEAGUE_CAPS['little'] == 500
    assert LEAGUE_MAX_LEVEL['little'] == 51.0
    assert bestbuddy_caps('little') == (51.0, MAX_CPM_LEVEL)


# ---------------------------------------------------------------------------
# The two paths that raised KeyError('little') before the descriptor
# ---------------------------------------------------------------------------

def test_at_best_level_little_league(mock_gm):
    p = Pokemon.at_best_level('Testmon', 15, 15, 15, league='little')
    assert p.cp <= LEAGUE_CAPS['little']
    assert p.level <= LEAGUE_MAX_LEVEL['little']


def test_iv_rank_little_league(mock_gm):
    ranked = iv_rank('Testmon', league='little')
    assert len(ranked) == 4096
    assert all(e['cp'] <= LEAGUE_CAPS['little'] for e in ranked)


def test_unknown_league_still_raises(mock_gm):
    with pytest.raises(KeyError):
        Pokemon.at_best_level('Testmon', 15, 15, 15, league='kiddie')
    with pytest.raises(KeyError):
        iv_rank('Testmon', league='kiddie')


# ---------------------------------------------------------------------------
# data.py reads the descriptor instead of its own copy
# ---------------------------------------------------------------------------

def test_data_league_cp_matches_the_descriptor():
    for name, row in LEAGUES.items():
        assert data._league_cp(name) == row.cp


def test_data_league_cp_unknown_league_raises_keyerror():
    """The historical ``_LEAGUE_CP[league]`` failure mode, which
    get_rankings_for / rankings_cache_path docstrings advertise."""
    with pytest.raises(KeyError):
        data._league_cp('kiddie')


def test_rankings_cache_path_little_cup():
    assert data.rankings_cache_path('little', cup='little').name == \
        'rankings_little_500.json'


def test_load_rankings_little_fails_loudly():
    """'little' is a real league with a real CP cap, but PvPoke publishes no
    open Little rankings -- it only runs as a limited cup. Say so instead of
    404ing later or pretending the league does not exist."""
    with pytest.raises(ValueError, match='only as a limited cup'):
        data.load_rankings('little')


def test_load_rankings_unknown_league_still_raises():
    with pytest.raises(ValueError, match='Unknown league'):
        data.load_rankings('kiddie')
