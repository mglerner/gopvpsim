"""Minior: PvPoke's form-change port (pvpoke 4d2908fac + 38f70320d, ported
2026-10-24) and the four port-fidelity fixes the port exposed.

Minior is the first `battle_start` + `hp`-trigger form changer. The stored
Core (218/131) enters every simulated battle as Meteor (116/194) at a
higher battle level that keeps its CP under the cap, and drops ONE WAY to
Core as soon as its HP falls strictly below 50% off any damage (fast or
charged, shielded or not). HP is Core's throughout (changeForm never
rewrites stats.hp). While a Meteor shell is on the field BOTH sides sit on
their charged energy (ActionLogic.js:254-263) and the shell is not shielded
against a hit it can take twice (wouldShield, ActionLogic.js:1256).
'Minior (Core only)' is our synthetic variant (data.SPECIES_VARIANTS): the
same stored Core spreads with the form change stripped, i.e. a Minior that
re-enters battle already flipped (PvPoke resetOnSwitch=false).

Provenance: every oracle cell below was validated against PvPoke's live JS
engine at 38f70320d via scripts/audit_oracle_harness.py (`--only minior`:
90/90 exact on score + winner + chargedLog, 2026-10-24). None of the ten
matchups carries a documented divergence. Re-audit anytime with:

    python scripts/audit_oracle_harness.py --only minior

Four engine fixes shipped with the port (all PvPoke-exact afterwards, with
the REVERT-FAILS cell recorded inline, model: test_port_fidelity_68ad233):

  1. New-mechanics fast landings resolve in queue order (queued turn, then
     seat), and a landing that flips the defender's form (Meteor -> Core)
     re-prices the fast moves still in flight.
       azumarill_vs_minior 1-1: fixed 641/358, pre-fix 646/353.
  2. turnsToLive walks the defender's charged moves in its FROZEN
     post-shuffle order (Pokemon.js resetMoves), not ascending energy.
       Minior vs Drapion 1-1: fixed 680/319, pre-fix 461/538 (winner flip).
       Carbink vs Malamar 2-2: fixed 406/593, pre-fix 399/600 (no Minior).
  3. The DP "stack two self-debuffing moves" expansion, BOTH twins
     (ActionLogic.js:668-717 ready, :764-808 not-ready). 496 of 14,022
     scanned GL cells moved, all 496 onto PvPoke's value.
       Minior vs Malamar 0-0: fixed 599/400, pre-fix 612/387.
       Malamar vs Dunsparce 2-1: fixed 784/215, ready-twin-only 640/359.
  4. Battle-start freeze ORDER: per seat, in PvPoke Battle.start order,
     the seat's move selection is frozen against the opponent AS IT STANDS,
     then that seat's battle_start change fires. So seat 0 freezes against
     CORE when Minior sits in seat 1, and against METEOR when Minior leads.
       Ariados vs Minior 2-1: fixed 625/375, pre-fix 265/734 (winner flip).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon, _extract_battle_log  # noqa: E402
from gopvpsim.battle import (  # noqa: E402
    simulate, pvpoke_dp, would_shield, _apply_hp_form_trigger, ENERGY_CAP,
)
from gopvpsim import formchange  # noqa: E402
from gopvpsim.data import species_id, get_default_moveset  # noqa: E402
from gopvpsim.pokemon import Pokemon, get_pokemon_entry  # noqa: E402


def _run(p1_args, p2_args, s1, s2):
    # p_args = (species, fast, charged, league, atk_iv, def_iv, sta_iv);
    # _make_battle_pokemon takes shields between league and the IVs.
    a = _make_battle_pokemon(*p1_args[:4], s1, *p1_args[4:])
    d = _make_battle_pokemon(*p2_args[:4], s2, *p2_args[4:])
    r = simulate(a, d, charged_policy_0=pvpoke_dp,
                 charged_policy_1=pvpoke_dp, log=True)
    return (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)),
            r.winner, _extract_battle_log(r))


def _score(p1_args, p2_args, s1, s2):
    return _run(p1_args, p2_args, s1, s2)[:3]


MINIOR = ('Minior (Core)', 'ROLLOUT', ['ACROBATICS', 'POWER_GEM'], 'great',
          5, 14, 15)                                  # PvPoke GL default IVs
MINIOR_AP = ('Minior (Core)', 'ROLLOUT', ['ACROBATICS', 'ANCIENT_POWER'],
             'great', 5, 14, 15)
MINIOR_TD = ('Minior (Core)', 'TAKE_DOWN', ['ACROBATICS', 'POWER_GEM'],
             'great', 5, 14, 15)
MINIOR_MIRROR_OPP = ('Minior (Core)', 'ROLLOUT', ['ACROBATICS', 'ANCIENT_POWER'],
                     'great', 10, 6, 10)
CORE_ONLY = ('Minior (Core only)', 'ROLLOUT', ['ACROBATICS', 'POWER_GEM'],
             'great', 5, 14, 15)
AZU = ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], 'great', 4, 15, 13)
MEDICHAM = ('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], 'great',
            7, 15, 14)
REGISTEEL = ('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], 'great',
             15, 15, 15)
CORVIKNIGHT = ('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], 'great',
               4, 12, 14)
CRAMORANT = ('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'], 'great', 5, 15, 15)
MIMIKYU = ('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], 'great',
           5, 13, 15)
DRAPION = ('Drapion', 'POISON_STING', ['CRUNCH', 'AQUA_TAIL'], 'great', 6, 14, 15)
MALAMAR = ('Malamar', 'PSYWAVE', ['SUPER_POWER', 'FOUL_PLAY'], 'great', 4, 15, 15)
DUNSPARCE = ('Dunsparce', 'BITE', ['DRILL_RUN', 'ROCK_SLIDE'], 'great', 4, 15, 13)
ARIADOS = ('Ariados', 'POISON_STING', ['LUNGE', 'FOUL_PLAY'], 'great', 4, 14, 14)
CARBINK = ('Carbink', 'ROCK_THROW', ['ROCK_SLIDE', 'MOONBLAST'], 'great',
           5, 15, 13)


# ===========================================================================
# Oracle cells: 10 matchups x 9 shield scenarios, all PvPoke-exact
# (scripts/audit_oracle_harness.py --only minior, 90/90, 2026-10-24).
# The 'Minior (Core only)' logs read 'Minior (Core)' because the variant is
# simmed as PvPoke's Core with the form change stripped (the harness folds
# the label the same way).
# ===========================================================================

# minior_vs_azumarill
MINIOR_VS_AZUMARILL_CELLS = [
    (0, 0, 522, 477, 0, ['Minior (Meteor): Acrobatics', 'Azumarill: Ice Beam', 'Minior (Core): Acrobatics']),
    (0, 1, 348, 651, 1, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam', 'Minior (Core): Acrobatics']),
    (0, 2, 104, 895, 1, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam', 'Minior (Core): Acrobatics (shielded)']),
    (1, 0, 725, 274, 0, ['Minior (Meteor): Acrobatics', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics']),
    (1, 1, 353, 646, 1, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics', 'Azumarill: Ice Beam']),
    (1, 2, 109, 890, 1, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics (shielded)', 'Azumarill: Ice Beam']),
    (2, 0, 725, 274, 0, ['Minior (Meteor): Acrobatics', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics']),
    (2, 1, 630, 369, 0, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem']),
    (2, 2, 403, 596, 1, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem (shielded)', 'Minior (Core): Acrobatics']),
]

# minior_vs_medicham
MINIOR_VS_MEDICHAM_CELLS = [
    (0, 0, 585, 414, 0, ['Minior (Meteor): Acrobatics', 'Medicham: Ice Punch', 'Minior (Core): Acrobatics']),
    (0, 1, 747, 252, 0, ['Minior (Meteor): Acrobatics (shielded)', 'Minior (Core): Acrobatics']),
    (0, 2, 102, 897, 1, ['Minior (Meteor): Acrobatics (shielded)', 'Minior (Core): Acrobatics (shielded)', 'Medicham: Ice Punch']),
    (1, 0, 761, 238, 0, ['Minior (Meteor): Acrobatics', 'Medicham: Ice Punch (shielded)', 'Minior (Meteor): Power Gem']),
    (1, 1, 747, 252, 0, ['Minior (Meteor): Acrobatics (shielded)', 'Minior (Core): Acrobatics']),
    (1, 2, 117, 882, 1, ['Minior (Meteor): Acrobatics (shielded)', 'Minior (Core): Acrobatics (shielded)', 'Medicham: Ice Punch (shielded)', 'Medicham: Ice Punch']),
    (2, 0, 761, 238, 0, ['Minior (Meteor): Acrobatics', 'Medicham: Ice Punch (shielded)', 'Minior (Meteor): Power Gem']),
    (2, 1, 747, 252, 0, ['Minior (Meteor): Acrobatics (shielded)', 'Minior (Core): Acrobatics']),
    (2, 2, 527, 472, 0, ['Minior (Meteor): Acrobatics (shielded)', 'Minior (Core): Power Gem (shielded)', 'Medicham: Dynamic Punch (shielded)', 'Minior (Core): Acrobatics']),
]

# minior_ap_vs_registeel
MINIOR_AP_VS_REGISTEEL_CELLS = [
    (0, 0, 340, 660, 1, ['Registeel: Flash Cannon', 'Minior (Core): Acrobatics', 'Minior (Core): Ancient Power', 'Registeel: Flash Cannon']),
    (0, 1, 248, 752, 1, ['Registeel: Flash Cannon', 'Minior (Core): Ancient Power (shielded)', 'Minior (Core): Acrobatics', 'Registeel: Flash Cannon']),
    (0, 2, 80, 920, 1, ['Registeel: Flash Cannon', 'Minior (Core): Ancient Power (shielded)', 'Minior (Core): Acrobatics (shielded)', 'Registeel: Flash Cannon']),
    (1, 0, 312, 688, 1, ['Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics', 'Minior (Meteor): Acrobatics', 'Registeel: Flash Cannon']),
    (1, 1, 200, 800, 1, ['Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics (shielded)', 'Minior (Meteor): Acrobatics', 'Registeel: Flash Cannon']),
    (1, 2, 88, 912, 1, ['Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics (shielded)', 'Minior (Meteor): Acrobatics (shielded)', 'Registeel: Flash Cannon']),
    (2, 0, 452, 548, 1, ['Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics', 'Minior (Meteor): Acrobatics', 'Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics', 'Registeel: Flash Cannon']),
    (2, 1, 340, 660, 1, ['Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics (shielded)', 'Minior (Meteor): Acrobatics', 'Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics', 'Registeel: Flash Cannon']),
    (2, 2, 228, 772, 1, ['Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics (shielded)', 'Minior (Meteor): Acrobatics (shielded)', 'Registeel: Flash Cannon (shielded)', 'Minior (Meteor): Acrobatics', 'Registeel: Flash Cannon']),
]

# minior_takedown_vs_corviknight
MINIOR_TAKEDOWN_VS_CORVIKNIGHT_CELLS = [
    (0, 0, 430, 570, 1, ['Corviknight: Payback', 'Minior (Core): Power Gem', 'Corviknight: Payback']),
    (0, 1, 183, 816, 1, ['Corviknight: Payback', 'Minior (Core): Power Gem (shielded)', 'Corviknight: Payback']),
    (0, 2, 183, 816, 1, ['Corviknight: Payback', 'Minior (Core): Power Gem (shielded)', 'Corviknight: Payback']),
    (1, 0, 630, 369, 0, ['Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem', 'Corviknight: Payback', 'Minior (Core): Power Gem']),
    (1, 1, 493, 506, 1, ['Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Corviknight: Payback', 'Minior (Core): Power Gem', 'Corviknight: Air Cutter']),
    (1, 2, 246, 753, 1, ['Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Corviknight: Payback', 'Minior (Core): Power Gem (shielded)', 'Corviknight: Air Cutter']),
    (2, 0, 833, 166, 0, ['Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem', 'Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem']),
    (2, 1, 558, 441, 0, ['Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem', 'Corviknight: Payback', 'Minior (Core): Power Gem']),
    (2, 2, 473, 526, 1, ['Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Corviknight: Payback (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Minior (Meteor): Power Gem', 'Corviknight: Payback']),
]

# azumarill_vs_minior
AZUMARILL_VS_MINIOR_CELLS = [
    (0, 0, 477, 522, 1, ['Minior (Meteor): Acrobatics', 'Azumarill: Ice Beam', 'Minior (Core): Acrobatics']),
    (0, 1, 274, 725, 1, ['Minior (Meteor): Acrobatics', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics']),
    (0, 2, 274, 725, 1, ['Minior (Meteor): Acrobatics', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics']),
    (1, 0, 651, 348, 0, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam', 'Minior (Core): Acrobatics']),
    (1, 1, 641, 358, 0, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics', 'Azumarill: Ice Beam']),
    (1, 2, 369, 630, 1, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem']),
    (2, 0, 895, 104, 0, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam', 'Minior (Core): Acrobatics (shielded)']),
    (2, 1, 884, 115, 0, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics (shielded)', 'Azumarill: Ice Beam']),
    (2, 2, 591, 408, 0, ['Minior (Meteor): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem (shielded)', 'Minior (Core): Acrobatics']),
]

# cramorant_vs_minior
CRAMORANT_VS_MINIOR_CELLS = [
    (0, 0, 373, 626, 1, ['Cramorant: Dive', 'Minior (Core): Power Gem', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    (0, 1, 175, 824, 1, ['Cramorant: Dive (shielded)', 'Minior (Meteor): Power Gem', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    (0, 2, 175, 824, 1, ['Cramorant: Dive (shielded)', 'Minior (Meteor): Power Gem', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    (1, 0, 773, 226, 0, ['Minior (Meteor): Power Gem (shielded)', 'Cramorant: Hydro Pump']),
    (1, 1, 166, 833, 1, ['Minior (Meteor): Power Gem (shielded)', 'Cramorant: Hydro Pump (shielded)', 'Minior (Meteor): Power Gem']),
    (1, 2, 166, 833, 1, ['Minior (Meteor): Power Gem (shielded)', 'Cramorant: Hydro Pump (shielded)', 'Minior (Meteor): Power Gem']),
    (2, 0, 773, 226, 0, ['Minior (Meteor): Power Gem (shielded)', 'Cramorant: Hydro Pump']),
    (2, 1, 642, 357, 0, ['Minior (Meteor): Power Gem (shielded)', 'Cramorant: Dive (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Cramorant (Gulping): Hydro Pump']),
    (2, 2, 500, 500, None, ['Minior (Meteor): Power Gem (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gulping): Dive (shielded)', 'Cramorant (Gulping): Dive', 'Minior (Core): Power Gem (shielded)', 'Minior (Core): Power Gem', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
]

# minior_vs_mimikyu
MINIOR_VS_MIMIKYU_CELLS = [
    (0, 0, 590, 409, 0, ['Minior (Meteor): Power Gem', 'Mimikyu (Busted): Shadow Sneak', 'Minior (Core): Power Gem']),
    (0, 1, 168, 831, 1, ['Minior (Meteor): Power Gem (shielded)', 'Mimikyu: Shadow Sneak', 'Minior (Core): Power Gem', 'Mimikyu (Busted): Shadow Sneak']),
    (0, 2, 168, 831, 1, ['Minior (Meteor): Power Gem (shielded)', 'Mimikyu: Shadow Sneak', 'Minior (Core): Power Gem (shielded)', 'Mimikyu: Shadow Sneak']),
    (1, 0, 567, 432, 0, ['Minior (Meteor): Power Gem', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Shadow Sneak', 'Minior (Core): Power Gem']),
    (1, 1, 158, 841, 1, ['Minior (Meteor): Power Gem (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Minior (Meteor): Power Gem', 'Mimikyu (Busted): Shadow Sneak']),
    (1, 2, 177, 822, 1, ['Minior (Meteor): Power Gem (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Minior (Meteor): Acrobatics (shielded)', 'Mimikyu: Shadow Sneak']),
    (2, 0, 738, 261, 0, ['Minior (Meteor): Power Gem', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Minior (Core): Power Gem']),
    (2, 1, 630, 369, 0, ['Minior (Meteor): Power Gem (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Minior (Meteor): Power Gem', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Minior (Core): Acrobatics']),
    (2, 2, 266, 733, 1, ['Minior (Meteor): Power Gem (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Minior (Core): Power Gem (shielded)', 'Minior (Core): Power Gem', 'Mimikyu (Busted): Shadow Sneak']),
]

# minior_mirror
MINIOR_MIRROR_CELLS = [
    (0, 0, 603, 396, 0, ['Minior (Meteor): Ancient Power', 'Minior (Core): Power Gem']),
    (0, 1, 197, 802, 1, ['Minior (Meteor): Ancient Power', 'Minior (Core): Power Gem (shielded)', 'Minior (Meteor): Ancient Power']),
    (0, 2, 197, 802, 1, ['Minior (Meteor): Ancient Power', 'Minior (Core): Power Gem (shielded)', 'Minior (Meteor): Ancient Power']),
    (1, 0, 504, 495, 0, ['Minior (Meteor): Ancient Power (shielded)', 'Minior (Meteor): Power Gem', 'Minior (Core): Ancient Power']),
    (1, 1, 572, 427, 0, ['Minior (Meteor): Ancient Power (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Minior (Meteor): Ancient Power', 'Minior (Core): Power Gem']),
    (1, 2, 252, 747, 1, ['Minior (Meteor): Ancient Power (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Minior (Core): Ancient Power']),
    (2, 0, 801, 198, 0, ['Minior (Meteor): Ancient Power (shielded)', 'Minior (Meteor): Power Gem', 'Minior (Core): Ancient Power (shielded)']),
    (2, 1, 774, 225, 0, ['Minior (Meteor): Ancient Power (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Minior (Meteor): Ancient Power (shielded)', 'Minior (Meteor): Power Gem']),
    (2, 2, 394, 605, 1, ['Minior (Meteor): Ancient Power (shielded)', 'Minior (Meteor): Power Gem (shielded)', 'Minior (Core): Ancient Power (shielded)', 'Minior (Core): Power Gem (shielded)', 'Minior (Core): Ancient Power']),
]

# minior_core_only_vs_azumarill
MINIOR_CORE_ONLY_VS_AZUMARILL_CELLS = [
    (0, 0, 251, 748, 1, ['Minior (Core): Power Gem', 'Azumarill: Ice Beam']),
    (0, 1, 81, 918, 1, ['Minior (Core): Acrobatics (shielded)', 'Azumarill: Ice Beam']),
    (0, 2, 81, 918, 1, ['Minior (Core): Acrobatics (shielded)', 'Azumarill: Ice Beam']),
    (1, 0, 635, 364, 0, ['Minior (Core): Power Gem', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem']),
    (1, 1, 390, 609, 1, ['Minior (Core): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics', 'Azumarill: Ice Beam']),
    (1, 2, 146, 853, 1, ['Minior (Core): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem (shielded)', 'Azumarill: Ice Beam']),
    (2, 0, 635, 364, 0, ['Minior (Core): Power Gem', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem']),
    (2, 1, 405, 594, 1, ['Minior (Core): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Acrobatics']),
    (2, 2, 162, 837, 1, ['Minior (Core): Power Gem (shielded)', 'Azumarill: Ice Beam (shielded)', 'Minior (Core): Power Gem (shielded)']),
]

# minior_core_only_vs_medicham
MINIOR_CORE_ONLY_VS_MEDICHAM_CELLS = [
    (0, 0, 212, 787, 1, ['Minior (Core): Power Gem', 'Medicham: Ice Punch']),
    (0, 1, 60, 939, 1, ['Minior (Core): Power Gem (shielded)', 'Medicham: Ice Punch']),
    (0, 2, 60, 939, 1, ['Minior (Core): Power Gem (shielded)', 'Medicham: Ice Punch']),
    (1, 0, 743, 256, 0, ['Medicham: Ice Punch (shielded)', 'Minior (Core): Acrobatics']),
    (1, 1, 527, 472, 0, ['Minior (Core): Power Gem (shielded)', 'Medicham: Dynamic Punch (shielded)', 'Minior (Core): Acrobatics']),
    (1, 2, 131, 868, 1, ['Minior (Core): Power Gem (shielded)']),
    (2, 0, 743, 256, 0, ['Medicham: Ice Punch (shielded)', 'Minior (Core): Acrobatics']),
    (2, 1, 527, 472, 0, ['Minior (Core): Power Gem (shielded)', 'Medicham: Dynamic Punch (shielded)', 'Minior (Core): Acrobatics']),
    (2, 2, 131, 868, 1, ['Minior (Core): Power Gem (shielded)']),
]

_ORACLE = [
    ('minior_vs_azumarill', MINIOR, AZU, MINIOR_VS_AZUMARILL_CELLS),
    ('minior_vs_medicham', MINIOR, MEDICHAM, MINIOR_VS_MEDICHAM_CELLS),
    ('minior_ap_vs_registeel', MINIOR_AP, REGISTEEL, MINIOR_AP_VS_REGISTEEL_CELLS),
    ('minior_takedown_vs_corviknight', MINIOR_TD, CORVIKNIGHT,
     MINIOR_TAKEDOWN_VS_CORVIKNIGHT_CELLS),
    ('azumarill_vs_minior', AZU, MINIOR, AZUMARILL_VS_MINIOR_CELLS),
    ('cramorant_vs_minior', CRAMORANT, MINIOR, CRAMORANT_VS_MINIOR_CELLS),
    ('minior_vs_mimikyu', MINIOR, MIMIKYU, MINIOR_VS_MIMIKYU_CELLS),
    ('minior_mirror', MINIOR, MINIOR_MIRROR_OPP, MINIOR_MIRROR_CELLS),
    ('minior_core_only_vs_azumarill', CORE_ONLY, AZU,
     MINIOR_CORE_ONLY_VS_AZUMARILL_CELLS),
    ('minior_core_only_vs_medicham', CORE_ONLY, MEDICHAM,
     MINIOR_CORE_ONLY_VS_MEDICHAM_CELLS),
]


@pytest.mark.parametrize(
    "p1,p2,s1,s2,score0,score1,winner,log",
    [pytest.param(p1, p2, *cell, id=f"{label}-{cell[0]}{cell[1]}")
     for label, p1, p2, cells in _ORACLE for cell in cells])
def test_minior_oracle_cells(p1, p2, s1, s2, score0, score1, winner, log):
    got = _run(p1, p2, s1, s2)
    want_log = [e.replace(' (Core only)', ' (Core)') for e in log]
    got_log = [e.replace(' (Core only)', ' (Core)') for e in got[3]]
    assert (got[0], got[1], got[2], got_log) == (score0, score1, winner,
                                                want_log)


def test_minior_oracle_fixture_is_nontrivial():
    """Oracle-parity guard: every matchup has a charged-move log in at
    least one cell and the two seats' scores sum to ~1000."""
    for label, _p1, _p2, cells in _ORACLE:
        assert len(cells) == 9, label
        assert any(cell[5] for cell in cells), label
        assert all(999 <= cell[2] + cell[3] <= 1000 for cell in cells), label


# ===========================================================================
# Revert-fails pins for the four fidelity fixes (PvPoke-exact after).
# ===========================================================================

def test_fix1_fast_landing_queue_order_azumarill_vs_minior_1v1():
    # pre-fix 646/353: Azumarill's Bubble landed before Minior's same-turn
    # Rollout and the Core flip was priced against the wrong fast damage.
    assert _score(AZU, MINIOR, 1, 1) == (641, 358, 0)


def test_fix2_ttl_frozen_order_minior_vs_drapion_1v1():
    # pre-fix 461/538 w1: TTL walked Drapion's moves ascending-energy
    # (Aqua Tail, Crunch) instead of the frozen [Crunch, Aqua Tail].
    assert _score(MINIOR, DRAPION, 1, 1) == (680, 319, 0)


def test_fix2_ttl_frozen_order_carbink_vs_malamar_2v2_no_minior():
    # The same fix moves a cell with no Minior on the field (the only
    # non-Minior movers in a 13,338-cell GL scan were this cell's two
    # seats): pre-fix 399/600.
    assert _score(CARBINK, MALAMAR, 2, 2) == (406, 593, 1)


def test_fix3_stack_two_ready_twin_minior_vs_malamar_0v0():
    # pre-fix 612/387: Malamar at 2x Super Power energy threw one at a time.
    assert _score(MINIOR, MALAMAR, 0, 0) == (599, 400, 0)


def test_fix3_stack_two_not_ready_twin_malamar_vs_dunsparce_2v1():
    # With only the READY twin ported this cell read 640/359 (36 cells
    # regressed); the NOT-READY twin (ActionLogic.js:764-808) restores it.
    assert _score(MALAMAR, DUNSPARCE, 2, 1) == (784, 215, 0)


def test_fix4_freeze_order_ariados_vs_minior_2v1():
    # pre-fix 265/734 w1: Ariados froze [Lunge, Foul Play] against METEOR
    # (dpe 0.58/0.80, rotated); PvPoke freezes seat 0 before Minior's
    # battle_start change, against CORE (1.0/1.4, [Foul Play, Lunge]).
    assert _score(ARIADOS, MINIOR, 2, 1) == (625, 375, 0)


def test_fix4_freeze_order_is_seat_dependent():
    """Minior leading: the opponent freezes against Meteor instead. The
    seat-swapped cell is a different fight, not a mirror image."""
    assert _score(MINIOR, ARIADOS, 1, 2) == (734, 265, 0)


# ===========================================================================
# Level math (formchange._minior_meteor_level / _minior_core_level)
# ===========================================================================

def _bases():
    return (get_pokemon_entry('Minior (Core)')['baseStats'],
            get_pokemon_entry('Minior (Meteor)')['baseStats'])


@pytest.mark.parametrize("ivs,core_level,meteor_whole,meteor_half", [
    # (5/14/15 is PvPoke's GL default). Whole-level walk = what PvPoke's
    # simulator runs (the dead half-level clause, DEVELOPER_NOTES "PvPoke
    # bugs found" #11); half = what its site UI displays. They disagree
    # for ~1/3 of GL spreads (the middle two rows).
    ((5, 14, 15), 24.0, 44.0, 44.0),
    ((10, 6, 10), 24.5, 43.0, 43.5),
    ((12, 14, 12), 23.5, 40.0, 40.5),
    ((2, 12, 14), 24.5, 47.0, 47.0),
    ((0, 0, 0), 27.0, 51.5, 51.5),
    ((15, 15, 15), 22.5, 38.0, 38.0),
])
def test_meteor_level_from_stored_core_gl(ivs, core_level, meteor_whole,
                                          meteor_half, monkeypatch):
    _core, meteor = _bases()
    assert Pokemon.at_best_level('Minior (Core)', *ivs,
                                 league='great').level == core_level
    monkeypatch.setattr(formchange, 'MINIOR_HALF_LEVEL_STEP', False)
    assert formchange._minior_meteor_level(core_level, 1500, meteor,
                                           *ivs) == meteor_whole
    monkeypatch.setattr(formchange, 'MINIOR_HALF_LEVEL_STEP', True)
    assert formchange._minior_meteor_level(core_level, 1500, meteor,
                                           *ivs) == meteor_half


def test_core_level_from_ui_selected_meteor_gl():
    """The inverse formula (Pokemon.js:2574) always steps half levels: a
    UI-selected L44 Meteor at 5/14/15 is a L23 Core (not the L24 it came
    from -- the two formulas are not inverses, which is PvPoke's choice)."""
    core, _meteor = _bases()
    assert formchange._minior_core_level(44.0, 1500, core, 5, 14, 15) == 23.0
    assert formchange._minior_core_level(43.0, 1500, core, 10, 6, 10) == 22.5


def test_meteor_level_ul_clamps_to_our_cpm_table():
    """DELIBERATE DIVERGENCE: Meteor cannot reach 2500 CP, so PvPoke leaves
    it at its table end (55); ours ends at 52. UL Minior is unverified
    in-game and outside every pool (docs/pvpoke_divergences.md)."""
    _core, meteor = _bases()
    assert Pokemon.at_best_level('Minior (Core)', 5, 14, 15,
                                 league='ultra').level == 50.0
    assert formchange._minior_meteor_level(50.0, 2500, meteor,
                                           5, 14, 15) == 52.0
    assert formchange._MINIOR_PVPOKE_LEVEL_CAP == 55.0


def test_meteor_form_stats_keep_core_hp():
    bp = _make_battle_pokemon(*MINIOR[:4], 1, *MINIOR[4:])
    forms = bp._form_change.forms
    assert [f.species_id for f in forms] == ['minior_core', 'minior_meteor']
    assert (forms[0].trigger, forms[0].target_idx) == ('battle_start', 1)
    assert (forms[1].trigger, forms[1].target_idx, forms[1].hp_amount) == \
        ('hp', 0, 0.5)
    assert (round(forms[1].atk, 4), round(forms[1].def_, 4)) == \
        (98.0463, 168.5424)           # Meteor at L44
    assert (round(forms[0].atk, 4), round(forms[0].def_, 4)) == \
        (145.9391, 94.8932)           # Core at L24
    assert bp.hp == bp.max_hp == 111  # Core's HP, never recomputed
    assert bp.active_form_sid == 'minior_core'   # pre-simulate: stored form


# ===========================================================================
# Battle mechanics: hp trigger, hold rule, shield rule, trigger guard
# ===========================================================================

def _meteor_vs_azu(minior_shields=1, azu_shields=1):
    bp = _make_battle_pokemon(*MINIOR[:4], minior_shields, *MINIOR[4:])
    azu = _make_battle_pokemon(*AZU[:4], azu_shields, *AZU[4:])
    bp.change_form(azu, 1)
    assert bp.active_form_sid == 'minior_meteor'
    return bp, azu


def test_hp_trigger_is_strict_half_one_way_and_not_on_ko():
    bp, azu = _meteor_vs_azu()
    bp.hp = 56                        # 56/111 >= 0.5: shell holds
    assert _apply_hp_form_trigger(bp, azu) is False
    assert bp.active_form_sid == 'minior_meteor'
    bp.hp = 55                        # 55/111 < 0.5: flips
    assert _apply_hp_form_trigger(bp, azu) is True
    assert bp.active_form_sid == 'minior_core'
    assert round(bp.atk, 4) == 145.9391
    bp.hp = 30                        # Core's trigger is battle_start: stays
    assert _apply_hp_form_trigger(bp, azu) is False
    assert bp.active_form_sid == 'minior_core'
    bp2, azu2 = _meteor_vs_azu()
    bp2.hp = 0                        # KO'd: no change (Battle.js hp > 0)
    assert _apply_hp_form_trigger(bp2, azu2) is False


def test_hp_trigger_fires_off_a_fast_move_in_a_real_fight():
    """Medicham's Counter takes the shell under 50% without a charged
    move: the flip is logged right after a Counter, before Medicham has
    thrown anything, and both forms appear in the timeline."""
    a = _make_battle_pokemon(*MINIOR[:4], 2, *MINIOR[4:])
    d = _make_battle_pokemon(*MEDICHAM[:4], 2, *MEDICHAM[4:])
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                 log=True)
    tl = r.timeline
    assert 'Minior (Meteor) changed form (battle start)' in tl[0]
    flip = next(i for i, line in enumerate(tl)
                if 'Minior (Core) changed form (hp)' in line)
    before = [line for line in tl[:flip] if 'Medicham uses' in line]
    assert before and before[-1].endswith('Medicham uses Counter')
    assert all(line.endswith('uses Counter') for line in before)
    assert any('Minior (Meteor) uses Rollout' in line for line in tl[:flip])
    assert any('Minior (Core) uses Rollout' in line for line in tl[flip:])


def test_meteor_hold_rule_both_sides_hoard_energy():
    """ActionLogic.js:254-263: with a shell on the field the opponent
    holds a ready Ice Beam (55e) at 60 and 80 energy; at 90 another
    Bubble (11e) would overflow the cap, so it throws."""
    bp, azu = _meteor_vs_azu()
    fast_energy = azu.fast_move['energyGain']
    for energy, want_hold in ((60, True), (80, True), (90, False)):
        azu = _make_battle_pokemon(*AZU[:4], 1, *AZU[4:])
        azu.energy = energy
        got = pvpoke_dp(azu, bp)
        assert (got is None) == want_hold, (energy, got)
        assert (ENERGY_CAP - energy >= fast_energy) == want_hold


def test_core_opponent_does_not_hold():
    """Positive control: the same Azumarill at 60 energy throws into a
    Core (no shell anywhere)."""
    bp = _make_battle_pokemon(*CORE_ONLY[:4], 1, *CORE_ONLY[4:])
    azu = _make_battle_pokemon(*AZU[:4], 1, *AZU[4:])
    azu.energy = 60
    assert pvpoke_dp(azu, bp) is not None


def test_would_shield_spares_the_shell_against_a_hit_it_takes_twice():
    """ActionLogic.js:1256: no shield in Meteor form when damage*2 < hp.
    Ice Beam does 52 to the L44 shell (111 HP) -> saved for the Core,
    where the same move does 93 -> shielded."""
    bp, azu = _meteor_vs_azu()
    ice_beam = azu.charged_moves[0]
    assert ice_beam['moveId'] == 'ICE_BEAM'
    assert azu.charged_move_damage(ice_beam, bp) == 52
    assert would_shield(azu, bp, ice_beam) is False
    core = _make_battle_pokemon(*MINIOR[:4], 1, *MINIOR[4:])
    assert azu.charged_move_damage(ice_beam, core) == 93
    assert would_shield(azu, core, ice_beam) is True


def test_unknown_form_change_trigger_is_refused():
    """A gamemaster trigger battle.py does not dispatch is a NEW mechanic;
    refuse it rather than silently simming the stored form all battle
    (what happened to Minior for four days before the port)."""
    with pytest.raises(ValueError, match="not implemented"):
        formchange._check_trigger('bogus', 'minior_core')
    for trig in ('battle_start', 'hp', 'activate_charged', 'activate_shield',
                 'charged_move', 'charged_move_damage', 'none'):
        formchange._check_trigger(trig, 'x')   # known: no raise


# ===========================================================================
# 'Minior (Core only)' synthetic variant
# ===========================================================================

def test_core_only_variant_resolves_to_core_everywhere_but_the_sim():
    assert species_id('Minior (Core only)') == 'minior_core'
    assert get_default_moveset('Minior (Core only)', 'great') == \
        ('ROLLOUT', ['ACROBATICS', 'POWER_GEM'])
    assert get_default_moveset('Minior (Core)', 'great') == \
        get_default_moveset('Minior (Core only)', 'great')
    e = get_pokemon_entry('Minior (Core only)')
    assert e['speciesId'] == 'minior_core_only'
    assert e['formChange'] is None
    assert e['baseStats'] == get_pokemon_entry('Minior (Core)')['baseStats']
    core = Pokemon.at_best_level('Minior (Core)', 5, 14, 15, league='great')
    only = Pokemon.at_best_level('Minior (Core only)', 5, 14, 15,
                                 league='great')
    assert (only.level, only.cp, only.atk, only.def_, only.hp) == \
        (core.level, core.cp, core.atk, core.def_, core.hp)
    bp = _make_battle_pokemon(*CORE_ONLY[:4], 1, *CORE_ONLY[4:])
    assert bp._form_change is None


def test_core_only_variant_is_not_in_the_gamemaster_list():
    """Whole-gamemaster sweeps must never see the synthetic entry."""
    from gopvpsim.data import load_gamemaster
    names = {m['speciesName'] for m in load_gamemaster()['pokemon']}
    assert 'Minior (Core)' in names
    assert 'Minior (Core only)' not in names


def test_core_only_fights_differ_from_the_real_minior():
    """The variant exists because the shell phase matters: same spread,
    same opponent, different fight (Azumarill 1-1: 390 vs 641-for-Azu)."""
    assert _score(CORE_ONLY, AZU, 1, 1) == (390, 609, 1)
    assert _score(MINIOR, AZU, 1, 1) != _score(CORE_ONLY, AZU, 1, 1)


# ===========================================================================
# Reuse + worker-path equivalence (the dive workers rely on both)
# ===========================================================================

@pytest.mark.parametrize("p0,p1", [
    pytest.param(MINIOR, AZU, id='minior-azumarill'),
    pytest.param(AZU, MINIOR, id='azumarill-minior'),
    pytest.param(MINIOR, MINIOR_MIRROR_OPP, id='minior-mirror'),
    pytest.param(CORE_ONLY, MEDICHAM, id='core-only-medicham'),
])
def test_reset_for_battle_reuse_matches_fresh(p0, p1):
    """Model: tests/test_battle.py::test_reset_for_battle_reuse_matches_fresh.
    The battle_start change plus the one-way hp flip are exactly the state
    most likely to leak across the 9-scenario reuse loop (a Minior left in
    Core, or a stale frozen selection against the wrong form)."""
    all_nine = [(a, b) for a in range(3) for b in range(3)]

    def build(spec, shields):
        return _make_battle_pokemon(*spec[:4], shields, *spec[4:])

    def key(r):
        return (r.winner, r.turns, r.hp_remaining, r.energy_remaining,
                r.shields_remaining, round(r.pvpoke_score(0)),
                _extract_battle_log(r), r.timeline)

    fresh = [simulate(build(p0, s0), build(p1, s1),
                      charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                      log=True) for s0, s1 in all_nine]
    bp0, bp1 = build(p0, 0), build(p1, 0)
    for (s0, s1), expected in zip(all_nine, fresh):
        bp0.reset_for_battle(s0, opponent=bp1)
        bp1.reset_for_battle(s1, opponent=bp0)
        got = simulate(bp0, bp1, charged_policy_0=pvpoke_dp,
                       charged_policy_1=pvpoke_dp, log=True)
        assert key(got) == key(expected), (s0, s1)


def test_dive_worker_constructor_matches_direct_path():
    """deep_dive.make_battle_pokemon (the sweep/slayer workers' constructor,
    raw stats + attach_form_change) must sim identically to the
    oracle-verified from_pokemon path, Minior on either side and the
    variant too."""
    from tests.conftest import load_deep_dive
    deep_dive = load_deep_dive()

    def via_worker(spec, shields):
        return deep_dive.make_battle_pokemon(*spec[:4], shields, *spec[4:])

    for p0, p1 in ((MINIOR, AZU), (MEDICHAM, MINIOR), (CORE_ONLY, AZU)):
        for s0, s1 in ((0, 0), (1, 1), (2, 2), (2, 0)):
            direct = simulate(_make_battle_pokemon(*p0[:4], s0, *p0[4:]),
                              _make_battle_pokemon(*p1[:4], s1, *p1[4:]),
                              charged_policy_0=pvpoke_dp,
                              charged_policy_1=pvpoke_dp, log=True)
            worker = simulate(via_worker(p0, s0), via_worker(p1, s1),
                              charged_policy_0=pvpoke_dp,
                              charged_policy_1=pvpoke_dp, log=True)
            assert (worker.winner, round(worker.pvpoke_score(0)),
                    _extract_battle_log(worker)) == \
                (direct.winner, round(direct.pvpoke_score(0)),
                 _extract_battle_log(direct)), (p0[0], p1[0], s0, s1)
