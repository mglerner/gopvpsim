"""Mega Level 4's level ceiling of 52 (PvPoke Pokemon.js:294-297).

PvPoke published this on 2026-09-02 (`82a974ffa`, "Mega Level 4 CP Boost") as
its quantification of Niantic's unquantified "greatly enhanced CP" for a
higher Mega Level. It is an INTERPRETATION, not a Niantic-published rule --
see MEGA_LEVEL_4_MAX_LEVEL -- but it is the oracle we cross-check against, and
before it PvPoke modelled no stat effect of Mega Level at all.

pvpoke 426e5e9f3 (2026-11-11) RETRACTED it for Master League ("Level 4 Megas
no longer receive a 2-level boost in Mega Master League"; the raise is now
gated on targetCP < 10000). In GL/UL a mega sits far below level 50 anyway,
so the raise never binds anywhere and a Master League supermega gets the
ordinary ceiling. Before the retraction ours gave Mewtwo (Mega X) 15/15/15
level 52 / 7076 CP in Master League (pre-fix value, pinned below).

PvPoke's guard leaks: setLevel/setIV call initialize(false), and `false <
10000` re-raises the cap to 52 (DEVELOPER_NOTES "PvPoke bugs found" #12). We
follow the default-load path, initialize(10000).

Expected values are captured from a RUNNING PvPoke at d02018eb6 (a debug copy
of scripts/pvpoke_trace.js printing level/cp/stats right after
initialize(10000), before any setIV), not derived from our own code. PvPoke's
default ML ceiling is 50, ours is 51 (best buddy), so the stat comparison
pins max_level=50.
"""
import pytest

from gopvpsim.pokemon import (CPM, LEAGUE_MAX_LEVEL, MAX_CPM_LEVEL,
                              MEGA_LEVEL_4_MAX_LEVEL, MEGA_LEVEL_SUPERMEGA,
                              Pokemon, bestbuddy_caps, mega_level)

# speciesName -> PvPoke's resolved values at 15/15/15, CP cap 10000, on the
# default-load path (initialize(10000)) at d02018eb6.
PVPOKE_ML = {
    'Mewtwo (Mega X)': dict(level=50.0, cp=6910, atk=347.88420975208254,
                            def_=193.26900541782365, hp=204),
    'Dragonite (Mega)': dict(level=50.0, cp=5452, atk=263.85420739650704,
                             def_=226.88100636005385, hp=188),
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
def test_supermega_master_league_stats_match_pvpoke(species):
    """Level, CP and HP exact; atk/def to the documented CPM[50] gap.

    Level 50 uses Niantic's published 0.84029999 where PvPoke carries the
    full float expansion (test_ordinary_levels_keep_the_game_published_cpm):
    a ~3e-8 CPM gap times a ~250-350 stat, so atk/def differ by ~1e-5 -- the
    same gap every ordinary level-50 mon has. max_level=50 because that is PvPoke's default ML ceiling.
    """
    want = PVPOKE_ML[species]
    p = Pokemon.at_best_level(species, 15, 15, 15, league='master',
                              max_level=50.0)
    assert mega_level(species) == MEGA_LEVEL_SUPERMEGA
    assert p.level == want['level']
    assert p.cp == want['cp']
    assert p.atk == pytest.approx(want['atk'], abs=1e-4)
    assert p.def_ == pytest.approx(want['def_'], abs=1e-4)
    assert p.hp == want['hp']


def test_ordinary_levels_keep_the_game_published_cpm():
    """The rest of the table stays on the GAME's values, not PvPoke's.

    Documents the deliberate inconsistency the mega levels introduced: a
    supermega matches PvPoke exactly, an ordinary mon differs by ~3e-8 at
    level 50 because we use Niantic's published 0.84029999 where PvPoke uses
    the full float expansion. That gap predates this work and is documented
    in docs/validations/2026-09-02_pvpoke_mega_revet.md as changing no cell.
    """
    assert CPM[50.0] == 0.84029999
    assert CPM[50.0] != 0.840300023555755
    assert abs(CPM[50.0] - 0.840300023555755) < 1e-7


def test_non_supermegas_and_non_megas_are_unaffected():
    """Ordinary Master League mons, supermega or not, stay <= 51."""
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


def test_master_league_supermega_gets_the_ordinary_ceiling():
    """No +2 levels in Master League since pvpoke 426e5e9f3.

    Pre-fix (pvpoke 82a974ffa..e02bde78d) ours gave 52.0 / 7076 CP here. Now a
    supermega's default ceiling is the ordinary Master League one (51, best
    buddy), the same as Dialga's. The table still stops at 52.
    """
    assert MEGA_LEVEL_4_MAX_LEVEL == 52.0
    assert 52.5 not in CPM and 53.0 not in CPM
    for species in sorted(PVPOKE_ML):
        p = Pokemon.at_best_level(species, 15, 15, 15, league='master')
        assert p.level == LEAGUE_MAX_LEVEL['master'] == 51.0, (species, p.level)
    assert Pokemon.at_best_level('Mewtwo (Mega X)', 15, 15, 15,
                                 league='master').cp != 7076
