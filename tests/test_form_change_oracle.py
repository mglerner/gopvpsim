"""Form-change oracle fixtures: 4 matchups x 9 shield cells (2026-06-12).

Pre-publish gap fill for the S6 re-dive: previously every form-change
species had exactly ONE oracle opponent (Azumarill), and the
Blade-as-focal / opponent-side-Aegislash surfaces had no 9-cell
coverage at all despite being live in every published GL dive.

Provenance: every cell was validated against PvPoke's live JS engine
via scripts/audit_oracle_harness.py (160 exact + 29 documented
divergences baseline, 2026-06-12). Cells commented "PvPoke-divergent"
pin OUR documented-divergent behavior; the divergence reasons (PvPoke
bug #3 Gyro-Ball-over-Shadow-Ball, bug #8 Hangry stickiness, the
near-KO plan-choice cluster) are documented per-matchup in the audit
harness MATCHUPS list and DEVELOPER_NOTES. Re-audit anytime with:

    python scripts/audit_oracle_harness.py --only form_change

These fixtures exist so plain pytest (no node, no PvPoke clone) pins
the audited behavior against regressions.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon, _extract_battle_log  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402


def _run(p1_args, p2_args, s1, s2, max_level=51.0):
    # p_args = (species, fast, charged, league, atk_iv, def_iv, sta_iv);
    # _make_battle_pokemon takes shields between league and the IVs.
    a = _make_battle_pokemon(*p1_args[:4], s1, *p1_args[4:],
                             max_level=max_level)
    d = _make_battle_pokemon(*p2_args[:4], s2, *p2_args[4:],
                             max_level=max_level)
    r = simulate(a, d, charged_policy_0=pvpoke_dp,
                 charged_policy_1=pvpoke_dp, log=True)
    return (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)),
            r.winner, _extract_battle_log(r))


AEGI_BLADE = ('Aegislash (Blade)', 'PSYCHO_CUT',
              ['SHADOW_BALL', 'GYRO_BALL'], 'great')
AEGI_SHIELD = ('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
               ['SHADOW_BALL', 'GYRO_BALL'], 'great')
AZU = ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], 'great')
MIMIKYU = ('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], 'great')
MEDICHAM = ('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], 'great')
MORPEKO = ('Morpeko (Full Belly)', 'THUNDER_SHOCK',
           ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS'], 'great')
GFISK = ('Stunfisk (Galarian)', 'MUD_SHOT',
         ['ROCK_SLIDE', 'EARTHQUAKE'], 'great')
TINKATON_UL = ('Tinkaton', 'FAIRY_WIND',
               ['GIGATON_HAMMER', 'BULLDOZE'], 'ultra')
AEGI_SHIELD_UL = ('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
                  ['SHADOW_BALL', 'GYRO_BALL'], 'ultra')


@pytest.mark.parametrize("s1,s2,score0,score1,winner,log", [
    (0, 0, 358, 641, 1, ['Aegislash (Blade): Shadow Ball', 'Azumarill: Play Rough']),
    (0, 1, 96, 903, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Play Rough']),
    (0, 2, 96, 903, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Play Rough']),
    (1, 0, 698, 301, 0, ['Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam (shielded)', 'Aegislash (Blade): Shadow Ball']),
    (1, 1, 400, 599, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Ice Beam (shielded)', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball']),  # PvPoke-divergent cell (see audit harness)
    (1, 2, 138, 861, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Ice Beam (shielded)', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)']),  # PvPoke-divergent cell (see audit harness)
    (2, 0, 655, 344, 0, ['Aegislash (Blade): Shadow Ball', 'Azumarill: Play Rough (shielded)', 'Aegislash (Blade): Shadow Ball']),
    (2, 1, 514, 485, 0, ['Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Play Rough (shielded)', 'Aegislash (Blade): Shadow Ball']),
    (2, 2, 183, 816, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)']),
])
def test_aegislash_blade_focal_vs_azumarill(s1, s2, score0, score1,
                                            winner, log):
    """Blade-as-focal: Blade->Shield reversion-on-shielding in battle.

    The reversion mechanics are PvPoke-identical (verified vs
    Pokemon.js changeForm: stat swap AND fast-move swap both ways).
    """
    ss0, ss1, sw, slog = _run((*AEGI_BLADE, 4, 14, 15),
                              (*AZU, 4, 15, 13), s1, s2)
    assert (ss0, ss1, sw) == (score0, score1, winner), \
        f"{s1}v{s2}: scores/winner moved"
    assert slog == log, f"{s1}v{s2}: chargedLog moved"


@pytest.mark.parametrize("s1,s2,score0,score1,winner,log", [
    (0, 0, 226, 773, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (0, 1, 226, 773, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (0, 2, 226, 773, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (1, 0, 625, 374, 0, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam']),  # PvPoke-divergent cell (see audit harness)
    (1, 1, 359, 640, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam (shielded)', 'Aegislash (Blade): Shadow Ball']),  # PvPoke-divergent cell (see audit harness)
    (1, 2, 359, 640, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam (shielded)', 'Aegislash (Blade): Shadow Ball']),  # PvPoke-divergent cell (see audit harness)
    (2, 0, 887, 112, 0, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Ice Beam']),  # PvPoke-divergent cell (see audit harness)
    (2, 1, 489, 510, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Play Rough (shielded)', 'Aegislash (Blade): Shadow Ball']),  # PvPoke-divergent cell (see audit harness)
    (2, 2, 489, 510, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Play Rough (shielded)', 'Aegislash (Blade): Shadow Ball']),  # PvPoke-divergent cell (see audit harness)
])
def test_azumarill_vs_aegislash_shield_opponent_side(s1, s2, score0,
                                                     score1, winner, log):
    """Opponent-side Aegislash across the full grid (every GL dive
    carries these rows). Divergent cells are PvPoke bug #3 seen from
    the opponent side; Azumarill's own move choices agree everywhere."""
    ss0, ss1, sw, slog = _run((*AZU, 4, 15, 13),
                              (*AEGI_SHIELD, 4, 14, 15), s1, s2)
    assert (ss0, ss1, sw) == (score0, score1, winner), \
        f"{s1}v{s2}: scores/winner moved"
    assert slog == log, f"{s1}v{s2}: chargedLog moved"


@pytest.mark.parametrize("s1,s2,score0,score1,winner,log", [
    (0, 0, 929, 70, 0, ['Medicham: Ice Punch', 'Mimikyu (Busted): Play Rough']),
    (0, 1, 873, 126, 0, ['Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch', 'Mimikyu (Busted): Shadow Sneak']),
    (0, 2, 644, 355, 0, ['Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Medicham: Ice Punch', 'Mimikyu (Busted): Shadow Sneak']),
    (1, 0, 929, 70, 0, ['Medicham: Ice Punch (shielded)', 'Mimikyu: Play Rough']),
    (1, 1, 873, 126, 0, ['Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch (shielded)', 'Mimikyu: Shadow Sneak']),
    (1, 2, 813, 186, 0, ['Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch', 'Mimikyu (Busted): Shadow Sneak']),
    (2, 0, 929, 70, 0, ['Medicham: Ice Punch (shielded)', 'Mimikyu: Play Rough']),
    (2, 1, 873, 126, 0, ['Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch (shielded)', 'Mimikyu: Shadow Sneak']),
    (2, 2, 813, 186, 0, ['Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Medicham: Ice Punch (shielded)', 'Mimikyu: Shadow Sneak']),
])
def test_mimikyu_vs_medicham_fast_pressure(s1, s2, score0, score1,
                                           winner, log):
    """Disguise vs Counter pressure: PvPoke-exact in all 9 cells."""
    ss0, ss1, sw, slog = _run((*MIMIKYU, 5, 13, 15),
                              (*MEDICHAM, 7, 15, 14), s1, s2)
    assert (ss0, ss1, sw) == (score0, score1, winner), \
        f"{s1}v{s2}: scores/winner moved"
    assert slog == log, f"{s1}v{s2}: chargedLog moved"


@pytest.mark.parametrize("s1,s2,score0,score1,winner,log", [
    (0, 0, 95, 904, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Earthquake']),
    (0, 1, 95, 904, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Earthquake']),
    (0, 2, 95, 904, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Earthquake']),
    (1, 0, 450, 549, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Morpeko (Hangry): Aura Wheel', 'Stunfisk (Galarian): Earthquake']),
    (1, 1, 450, 549, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Morpeko (Hangry): Aura Wheel', 'Stunfisk (Galarian): Earthquake']),
    (1, 2, 218, 781, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Morpeko (Hangry): Psychic Fangs (shielded)', 'Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Earthquake']),  # PvPoke-divergent cell (see audit harness)
    (2, 0, 771, 228, 0, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Morpeko (Hangry): Aura Wheel', 'Stunfisk (Galarian): Earthquake (shielded)', 'Morpeko (Full Belly): Psychic Fangs']),  # PvPoke-divergent cell (see audit harness)
    (2, 1, 488, 511, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Morpeko (Hangry): Aura Wheel', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Morpeko (Full Belly): Psychic Fangs (shielded)', 'Stunfisk (Galarian): Rock Slide']),  # PvPoke-divergent cell (see audit harness)
    (2, 2, 252, 747, 1, ['Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Morpeko (Hangry): Psychic Fangs (shielded)', 'Morpeko (Full Belly): Psychic Fangs', 'Stunfisk (Galarian): Rock Slide (shielded)', 'Stunfisk (Galarian): Rock Slide']),  # PvPoke-divergent cell (see audit harness)
])
def test_morpeko_vs_gfisk_aura_wheel_type_flip(s1, s2, score0, score1,
                                               winner, log):
    """Hangry toggle where the Aura Wheel type flip changes the
    effectiveness class (Electric double-resisted, Dark merely
    steel-resisted vs ground/steel). Divergent cells are PvPoke bug #8
    (Hangry stickiness); our two-way toggle is in-game-verified."""
    ss0, ss1, sw, slog = _run((*MORPEKO, 5, 14, 15),
                              (*GFISK, 5, 15, 13), s1, s2)
    assert (ss0, ss1, sw) == (score0, score1, winner), \
        f"{s1}v{s2}: scores/winner moved"
    assert slog == log, f"{s1}v{s2}: chargedLog moved"


@pytest.mark.parametrize("s1,s2,score0,score1,winner,log", [
    (0, 0, 316, 683, 1, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    # (0,1)/(0,2): after the NB-1 selection-freeze (2026-07-03) these now match
    # the PvPoke oracle EXACTLY (score [306,693] winner 1 and chargedLog); the
    # divergence annotation was removed.
    (0, 1, 306, 693, 1, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (0, 2, 306, 693, 1, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (1, 0, 671, 328, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Tinkaton: Bulldoze']),  # PvPoke-divergent cell (see audit harness)
    (1, 1, 637, 362, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Tinkaton: Bulldoze']),  # PvPoke-divergent cell (bug #3 Gyro-Ball; shifted by 2026-07-03 NB-1 freeze, oracle winner 0 still matches)
    (1, 2, 408, 591, 1, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball']),  # PvPoke-divergent cell (shifted by 2026-07-03 NB-1 freeze; oracle winner 1 still matches)
    (2, 0, 946, 53, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze']),  # PvPoke-divergent cell (see audit harness)
    (2, 1, 912, 87, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze']),  # PvPoke-divergent cell (bug #3; shifted by 2026-07-03 NB-1 freeze, oracle winner 0 still matches)
    (2, 2, 620, 379, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball', 'Tinkaton: Bulldoze']),  # PvPoke-divergent cell (shifted by 2026-07-03 NB-1 freeze; oracle winner 0 still matches)
])
def test_tinkaton_ul_vs_aegislash_shield(s1, s2, score0, score1,
                                         winner, log):
    """UL Aegislash as opponent (live rows on the published Tinkaton UL
    dive). Levels pinned to 50 on both sides — PvPoke's UI default;
    best-buddy level 51 yields a level-39 Blade instead of 38, a
    different Pokemon. Divergent cells: bug #3 (Gyro Ball into the
    shield at (1,0)/(1,1)) + Tinkaton-side plan-timing, winner agrees
    in all 9."""
    ss0, ss1, sw, slog = _run((*TINKATON_UL, 12, 15, 15),
                              (*AEGI_SHIELD_UL, 15, 15, 15), s1, s2,
                              max_level=50.0)
    assert (ss0, ss1, sw) == (score0, score1, winner), \
        f"{s1}v{s2}: scores/winner moved"
    assert slog == log, f"{s1}v{s2}: chargedLog moved"
