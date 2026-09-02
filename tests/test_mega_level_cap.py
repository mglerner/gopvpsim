"""Mega Level 4 raises the level ceiling to 52 (PvPoke Pokemon.js:294-297).

PvPoke published this on 2026-09-02 (`82a974ffa`, "Mega Level 4 CP Boost") as
its quantification of Niantic's unquantified "greatly enhanced CP" for a
higher Mega Level. It is an INTERPRETATION, not a Niantic-published rule --
see MEGA_LEVEL_4_MAX_LEVEL -- but it is the oracle we cross-check against, and
before it PvPoke modelled no stat effect of Mega Level at all.

It only bites where a CP cap does not already bind, i.e. Master League: a GL
or UL mega sits far below level 50 anyway because its base stats are huge.

Expected values are captured from a RUNNING PvPoke at 79d04af74 (a probe that
instantiates Pokemon.js directly and reports the resolved level/cp/stats), not
derived from our own code.
"""
import pytest

from gopvpsim.pokemon import (CPM, MAX_CPM_LEVEL, MEGA_LEVEL_4_MAX_LEVEL,
                              MEGA_LEVEL_SUPERMEGA, Pokemon, bestbuddy_caps,
                              mega_level)

# speciesName -> PvPoke's resolved values at 15/15/15, CP cap 10000.
PVPOKE_ML = {
    'Mewtwo (Mega X)': dict(level=52.0, cp=7076, atk=352.024205803871,
                            def_=195.56900322437275, hp=206),
    'Dragonite (Mega)': dict(level=52.0, cp=5583, atk=266.9942044019698,
                             def_=229.58100378513325, hp=190),
}


def test_cpm_table_carries_the_mega_only_levels():
    """51.5 and 52.0 exist in the table; nothing else grew."""
    assert 51.5 in CPM and 52.0 in CPM
    assert max(CPM) == 52.0
    # exact PvPoke values (its cpms indices 101/102) -- these levels have no
    # Niantic-published CPM to truncate, unlike every entry below them
    assert CPM[51.5] == 0.847803702398935
    assert CPM[52.0] == 0.850300014019012


def test_the_ordinary_ceiling_did_not_move():
    """MAX_CPM_LEVEL must stay 51: it means 'what a normal build can reach'.

    This is the trap the decoupling exists for. MAX_CPM_LEVEL used to be
    `max(CPM)`, and it feeds bestbuddy_caps, the dive page's JS level
    ceilings and user_collection. Extending the table without decoupling
    would silently have let EVERY Master and Little mon best-buddy to 52.
    """
    assert MAX_CPM_LEVEL == 51.0
    assert MAX_CPM_LEVEL != max(CPM), (
        'MAX_CPM_LEVEL is back to max(CPM); the mega-only levels would leak '
        'into every ordinary level ceiling')
    for league in ('great', 'ultra', 'master', 'little'):
        default, alt = bestbuddy_caps(league)
        assert alt <= 51.0, (league, alt)


@pytest.mark.parametrize('species', sorted(PVPOKE_ML))
def test_supermega_master_league_stats_match_pvpoke_exactly(species):
    """Level, CP and every battle stat, bit-for-bit.

    Exact rather than approximate on purpose: the two mega-only CPM entries
    are PvPoke's own full-precision values, so there is no truncation gap to
    absorb here (unlike the rest of the table -- see
    test_ordinary_levels_keep_the_game_published_cpm).
    """
    want = PVPOKE_ML[species]
    p = Pokemon.at_best_level(species, 15, 15, 15, league='master')
    assert mega_level(species) == MEGA_LEVEL_SUPERMEGA
    assert p.level == want['level']
    assert p.cp == want['cp']
    assert p.atk == want['atk']
    assert p.def_ == want['def_']
    assert p.hp == want['hp']


def test_ordinary_levels_keep_the_game_published_cpm():
    """The rest of the table stays on the GAME's values, not PvPoke's.

    Documents the deliberate inconsistency the mega levels introduced: a
    supermega matches PvPoke exactly, an ordinary mon differs by ~3e-8 at
    level 50 because we use Niantic's published 0.84029999 where PvPoke uses
    the full float expansion. That gap predates this work and is documented
    in DEVELOPER_NOTES as changing no cell.
    """
    assert CPM[50.0] == 0.84029999
    assert CPM[50.0] != 0.840300023555755
    assert abs(CPM[50.0] - 0.840300023555755) < 1e-7


def test_non_supermegas_and_non_megas_are_unaffected():
    """Only Mega Level 4 gets the raise."""
    for species in ('Dialga', 'Metagross', 'Sableye (Mega)'):
        p = Pokemon.at_best_level(species, 15, 15, 15, league='master')
        assert p.level <= MAX_CPM_LEVEL, (species, p.level)
    # Sableye (Mega) is mega-tagged but NOT supermega -- the discriminator
    assert mega_level('Sableye (Mega)') is not None
    assert mega_level('Sableye (Mega)') != MEGA_LEVEL_SUPERMEGA


@pytest.mark.parametrize('league', ['great', 'ultra'])
def test_capped_leagues_are_unaffected_by_the_raise(league):
    """A CP cap binds far below 50 for a mega, so the ceiling never applies."""
    for species in sorted(PVPOKE_ML):
        p = Pokemon.at_best_level(species, 15, 15, 15, league=league)
        assert p.level < 50.0, (species, league, p.level)


def test_an_explicit_max_level_still_wins():
    """A pinned max_level must not be silently overridden.

    Oracle fixtures and historical re-dives ask for the level they mean; the
    mega raise is a CEILING, not a forced level. (This is also why
    tests/test_battle.py's _make_battle_pokemon, which passes max_level=51.0
    as its default, does not get level-52 megas.)
    """
    p = Pokemon.at_best_level('Mewtwo (Mega X)', 15, 15, 15,
                              league='master', max_level=50.0)
    assert p.level == 50.0
    p51 = Pokemon.at_best_level('Mewtwo (Mega X)', 15, 15, 15,
                                league='master', max_level=51.0)
    assert p51.level == 51.0


def test_mega_four_cap_is_flat_and_does_not_stack_with_best_buddy():
    """PvPoke clamps setLevelCap with min(levelCap, baseLevelCap).

    Both caps are set to 52, so best buddy cannot push a supermega to 53. Our
    table deliberately stops at 52 for the same reason -- a 53 entry would
    invite exactly that stacking.
    """
    assert MEGA_LEVEL_4_MAX_LEVEL == 52.0
    assert 52.5 not in CPM and 53.0 not in CPM
    p = Pokemon.at_best_level('Mewtwo (Mega X)', 15, 15, 15, league='master')
    assert p.level == MEGA_LEVEL_4_MAX_LEVEL
