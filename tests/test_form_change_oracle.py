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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system; verified against the oracle harness (229/243 cells match
    # PvPoke exactly). See the step-B commit for the warrant.
    (0, 0, 321, 678, 1, ['Aegislash (Blade): Shadow Ball', 'Azumarill: Play Rough']),
    (0, 1, 86, 913, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Play Rough']),
    (0, 2, 86, 913, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Play Rough']),
    # (1,0)/(2,0) PvPoke-exact since 2026-09-27 (Shield-form charged
    # estimate at Blade atk). Pre-fix ours: (1,0) 570/429 with an extra
    # 'Azumarill: Ice Beam' before the last Shadow Ball; (2,0) 580/419
    # with an extra 'Azumarill: Ice Beam (shielded)'.
    (1, 0, 712, 287, 0, ['Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam (shielded)', 'Aegislash (Blade): Shadow Ball']),
    (1, 1, 528, 471, 0, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Ice Beam (shielded)', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (1, 2, 361, 638, 1, ['Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Ice Beam (shielded)', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system; verified against the oracle harness (229/243 cells match
    # PvPoke exactly). See the step-B commit for the warrant.
    (0, 0, 248, 751, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (0, 1, 248, 751, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (0, 2, 248, 751, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (1, 0, 651, 348, 0, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam']),
    # (1,1)/(1,2) PvPoke-exact since 2026-09-27 (Shield-form charged
    # estimate at Blade atk). Pre-fix ours: (1,1) 435/564, same log;
    # (1,2) 449/550 with an extra 'Azumarill: Play Rough (shielded)'.
    (1, 1, 381, 618, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam (shielded)', 'Aegislash (Blade): Shadow Ball']),
    (1, 2, 381, 618, 1, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball', 'Azumarill: Ice Beam (shielded)', 'Aegislash (Blade): Shadow Ball']),
    (2, 0, 887, 112, 0, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Azumarill: Ice Beam']),
    (2, 1, 617, 382, 0, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball']),
    (2, 2, 617, 382, 0, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Aegislash (Blade): Shadow Ball']),
])
def test_azumarill_vs_aegislash_shield_opponent_side(s1, s2, score0,
                                                     score1, winner, log):
    """Opponent-side Aegislash across the full grid (every GL dive
    carries these rows). All nine cells PvPoke-exact (2026-09-27)."""
    ss0, ss1, sw, slog = _run((*AZU, 4, 15, 13),
                              (*AEGI_SHIELD, 4, 14, 15), s1, s2)
    assert (ss0, ss1, sw) == (score0, score1, winner), \
        f"{s1}v{s2}: scores/winner moved"
    assert slog == log, f"{s1}v{s2}: chargedLog moved"


CRADILY = ('Cradily', 'ACID', ['ROCK_TOMB', 'GRASS_KNOT'], 'great')
_RT_GB = ['Aegislash (Blade): Gyro Ball (shielded)',
          'Cradily: Rock Tomb (shielded)', 'Cradily: Rock Tomb',
          'Cradily: Rock Tomb']


@pytest.mark.parametrize("s1,s2,score0,score1,winner,log,pvpoke", [
    (1, 1, 301, 698, 1,
     _RT_GB + ['Aegislash (Blade): Gyro Ball',
               'Aegislash (Blade): Shadow Ball'], (545, 454, 0)),
    (1, 2, 301, 698, 1,
     _RT_GB + ['Aegislash (Blade): Gyro Ball',
               'Aegislash (Blade): Shadow Ball'], (240, 759, 1)),
    (2, 2, 363, 636, 1,
     _RT_GB + ['Aegislash (Blade): Gyro Ball (shielded)',
               'Cradily: Rock Tomb (shielded)',
               'Aegislash (Blade): Shadow Ball',
               'Aegislash (Blade): Gyro Ball'], (363, 636, 1)),
])
def test_cradily_vs_aegislash_blade_estimate_stage_divergence(
        s1, s2, score0, score1, winner, log, pvpoke):
    """DIVERGENCE PIN (our value; PvPoke's rides in the message).

    Rock Tomb drops Aegislash's atk stage. After its shielded Gyro Ball
    reverts it to Shield form, PvPoke prices the Shield form's charged moves
    at the raw, stage-blind Blade atk; we apply the current stage, so our
    estimate equals the damage the throw really deals (BattlePokemon.
    _charged_atk_base; DEVELOPER_NOTES "Form change gotchas" item 6). PvPoke's
    choice is internally inconsistent and not better on outcomes (in the
    1080-cell sample the stage choice decides 15 cells, 3 of 4 winner flips
    in Aegislash's favour under ours), so we keep ours. A stage-blind variant
    reproduces PvPoke's score, winner and chargedLog on all three cells
    (audit_oracle_harness.py cradily_vs_aegislash_blade_form_change xfails).
    Before the 2026-09-27 estimate fix these cells were (1,1)/(1,2) the
    same and (2,2) 367/632.
    """
    ss0, ss1, sw, slog = _run((*CRADILY, 4, 14, 14),
                              (*AEGI_BLADE, 4, 14, 15), s1, s2)
    note = f" [divergence pin: PvPoke master gives {pvpoke}]"
    assert (ss0, ss1, sw) == (score0, score1, winner), \
        f"{s1}v{s2}: scores/winner moved{note}"
    assert slog == log, f"{s1}v{s2}: chargedLog moved{note}"


MOLTRES_G = ('Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'],
             'great')
AEGI_SHIELD_GB_FIRST = ('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
                        ['GYRO_BALL', 'SHADOW_BALL'], 'great')
_MG_LOG = ['Moltres (Galarian): Fly', 'Moltres (Galarian): Fly',
           'Aegislash (Blade): Gyro Ball']


def test_aegislash_shield_vs_moltres_g_first_throw_divergence():
    """DIVERGENCE PIN, PvPoke bugs found #10 (our value; PvPoke's rides in
    the message).

    Shield-start Aegislash, input order [SHADOW_BALL, GYRO_BALL]. Our
    priority shuffle's clause 1 (same energy -> higher damage to slot 0) is
    live at the first Shield-form shuffle because reset_for_battle restores
    clause 4's stamp, so slot 0 is Gyro Ball (Ghost is resisted by Moltres-G).
    PvPoke's clause-4 stamp persists across its pre-fight resetMoves() calls,
    clause 1 is dead, and slot 0 is the input order: its last-gasp throw is
    the resisted Shadow Ball. Arbitrary and worse where it matters; not
    ported (audit_oracle_harness.py aegislash_shield_vs_moltres_galarian).
    """
    ss0, ss1, sw, slog = _run((*AEGI_SHIELD, 4, 14, 15),
                              (*MOLTRES_G, 15, 15, 15), 0, 0)
    note = (" [divergence pin: PvPoke master gives 308/691 w1 with "
            "'Aegislash (Blade): Shadow Ball' as the last throw]")
    assert (ss0, ss1, sw) == (408, 591, 1), f"0v0: scores/winner moved{note}"
    assert slog == _MG_LOG, f"0v0: chargedLog moved{note}"


def test_aegislash_shield_vs_moltres_g_gb_first_matches_pvpoke():
    """POSITIVE CONTROL for #10: the same fight with the charged INPUT order
    swapped to [GYRO_BALL, SHADOW_BALL]. PvPoke's slot 0 is then Gyro Ball
    as well, and the fight is PvPoke-exact (408/591 w1 and this chargedLog
    on both engines, harness-verified 2026-09-28; the audit's
    aegislash_shield_gb_first_vs_moltres_galarian row keeps it verified).
    If this ever differs from the divergence pin above, the divergence is
    no longer just the first-throw slot choice.
    """
    ss0, ss1, sw, slog = _run((*AEGI_SHIELD_GB_FIRST, 4, 14, 15),
                              (*MOLTRES_G, 15, 15, 15), 0, 0)
    assert (ss0, ss1, sw) == (408, 591, 1), "0v0: scores/winner moved"
    assert slog == _MG_LOG, "0v0: chargedLog moved"


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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system; verified against the oracle harness (229/243 cells match
    # PvPoke exactly). See the step-B commit for the warrant.
    (0, 0, 702, 297, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Aegislash (Blade): Shadow Ball']),
    (0, 1, 299, 700, 1, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (0, 2, 299, 700, 1, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (1, 0, 949, 50, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Aegislash (Blade): Shadow Ball (shielded)']),
    (1, 1, 924, 75, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze']),
    (1, 2, 397, 602, 1, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (2, 0, 949, 50, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze', 'Aegislash (Blade): Shadow Ball (shielded)']),
    (2, 1, 924, 75, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze']),
    (2, 2, 893, 106, 0, ['Tinkaton: Bulldoze', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze (shielded)', 'Aegislash (Blade): Shadow Ball (shielded)', 'Tinkaton: Bulldoze']),
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
