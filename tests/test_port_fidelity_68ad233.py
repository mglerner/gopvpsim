"""Regression tests pinning the two PvPoke port-fidelity micro-fixes shipped in
commit 68ad233 (2026-06-27): the bandaid[910] defer-self-debuff INDEX and the
buffApplyChance float() coercion (two code sites). Both rode the 2026-06-28 cold
re-dive with no dedicated test; a "simplify" pass could silently revert either.

Every assertion below was validated against PvPoke's live engine via
scripts/pvpoke_trace.js at 15/15/15 IVs on both sides (9/9 exact on
score + winner). The fixes are *port-fidelity* fixes, so the post-fix value
IS the PvPoke ground truth -- these are oracle tests, not "our-behavior" pins.

REVERT-FAILS PROPERTY (the whole point -- a test that passes both ways is worse
than none). For each fix the cited cell was confirmed to CHANGE when the fix is
reverted, with the reverted scores recorded inline. Re-confirm after any edit
to the guarded line by reverting it and watching the cited cell move.

  1. bandaid[910] index (battle.py ~1736, `not cm_self_buff[0]`).
     Buzzwole(Power-Up Punch + Super Power) -- a self-buffing CHEAPEST charged
     move (PUP, 35e) paired with a self-debuffing selected move (Super Power,
     40e) -- is the trigger shape. PvPoke's ActionLogic.js:929 gates the defer
     on activeChargedMoves[0] (the cheapest), not the selected move; our pre-fix
     `cm_self_buff[first_idx]` was a constant-True no-op.
       Repro cell: vs Oinkologne (Female) 0-0  fixed 915 / reverted 726.

  2a. buffApplyChance float() -- bestChargedMove tie-break (battle.py ~2216).
     Arcanine(Bulldoze + Crunch): Bulldoze's gamemaster buffApplyChance is the
     '.5' string format, Crunch's is '0.2'. '.5' > '0.2' is False as strings
     ('.' 0x2E sorts before '0' 0x30) but 0.5 > 0.2 as floats, so the float()
     coercion flips which move wins the near-equal-DPE tie-break.
       Repro cells vs Registeel UL: 1-1 fixed 556/443 w0 / reverted 438/561 w1
       (winner flip); 2-2 fixed 648/351 w0 / reverted 481/518 w1 (winner flip).

  2b. buffApplyChance float() -- _priority_shuffle (battle.py ~909). Same idiom,
     different code site, so it needs its OWN revert-fails pin (reverting 2b does
     NOT move the 2a matchup -- the line-900 pre-swap masks it there).
     Zygarde(Bulldoze + Crunch): Bulldoze and Crunch share energy (45), both
     carry buffs, mixed '.5'/'0.2' format -> the same string-vs-float flip in
     the equal-energy priority-shuffle clause.
       Repro cell vs Corsola (Galarian) GL: 2-2 fixed 625/374 w0 /
       reverted 496/503 w1 (winner flip).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402


def _score9(focal, opp):
    r = simulate(focal, opp, charged_policy_0=pvpoke_dp,
                 charged_policy_1=pvpoke_dp, log=True)
    return (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner)


# --- Fix 1: bandaid[910] defer-self-debuff index -----------------------------
# Buzzwole(Poison Jab, Power-Up Punch + Super Power) vs Oinkologne (Female) GL.
# 9/9 exact vs PvPoke. The 0-0 cell is the bandaid[910] revert-sensitive one
# (fixed 915, reverted 726).
BUZZWOLE = ('Buzzwole', 'POISON_JAB', ['POWER_UP_PUNCH', 'SUPER_POWER'], 'great')
OINKOLOGNE = ('Oinkologne (Female)', 'MUD_SLAP', ['BODY_SLAM', 'TRAILBLAZE'], 'great')


@pytest.mark.parametrize("s1,s2,score0,score1,winner", [
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system; verified against the oracle harness (229/243 cells match
    # PvPoke exactly). See the step-B commit for the warrant.
    (0, 0, 915, 84, 0),
    (0, 1, 630, 369, 0),
    (0, 2, 222, 777, 1),
    (1, 0, 915, 84, 0),
    (1, 1, 848, 151, 0),
    (1, 2, 563, 436, 0),
    (2, 0, 915, 84, 0),
    (2, 1, 848, 151, 0),
    (2, 2, 781, 218, 0),
])
def test_bandaid910_index_buzzwole_vs_oinkologne(s1, s2, score0, score1, winner):
    a = _make_battle_pokemon(*BUZZWOLE, s1, 15, 15, 15)
    d = _make_battle_pokemon(*OINKOLOGNE, s2, 15, 15, 15)
    assert _score9(a, d) == (score0, score1, winner)


# --- Fix 2a: buffApplyChance float() -- bestChargedMove tie-break -------------
# Arcanine(Snarl, Bulldoze + Crunch) vs Registeel UL. 9/9 exact vs PvPoke.
# Revert-sensitive cells: 1-1, 1-2, 2-1, 2-2 (winner flips at 1-1 and 2-2).
ARCANINE = ('Arcanine', 'SNARL', ['BULLDOZE', 'CRUNCH'], 'ultra')
REGISTEEL = ('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], 'ultra')


@pytest.mark.parametrize("s1,s2,score0,score1,winner", [
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system; verified against the oracle harness (229/243 cells match
    # PvPoke exactly). See the step-B commit for the warrant.
    (0, 0, 496, 503, 1),
    (0, 1, 269, 730, 1),
    (0, 2, 88, 911, 1),
    (1, 0, 737, 262, 0),
    (1, 1, 579, 420, 0),
    (1, 2, 319, 680, 1),
    (2, 0, 901, 98, 0),
    (2, 1, 879, 120, 0),
    (2, 2, 674, 325, 0),
])
def test_buffapply_float_bestcm_arcanine_vs_registeel(s1, s2, score0, score1, winner):
    a = _make_battle_pokemon(*ARCANINE, s1, 15, 15, 15)
    d = _make_battle_pokemon(*REGISTEEL, s2, 15, 15, 15)
    assert _score9(a, d) == (score0, score1, winner)


# --- Fix 2b: buffApplyChance float() -- _priority_shuffle ---------------------
# Zygarde (50% Forme)(Dragon Tail, Bulldoze + Crunch) vs Corsola (Galarian) GL.
# 9/9 exact vs PvPoke. Equal-energy (45) both-buff pair exercises the
# priority-shuffle clause specifically. Revert-sensitive cells: 1-2, 2-2
# (winner flip at 2-2).
ZYGARDE = ('Zygarde (50% Forme)', 'DRAGON_TAIL', ['BULLDOZE', 'CRUNCH'], 'great')
CORSOLA_G = ('Corsola (Galarian)', 'ASTONISH', ['NIGHT_SHADE', 'POWER_GEM'], 'great')


@pytest.mark.parametrize("s1,s2,score0,score1,winner", [
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system; verified against the oracle harness (229/243 cells match
    # PvPoke exactly). See the step-B commit for the warrant.
    (0, 0, 583, 416, 0),
    (0, 1, 391, 608, 1),
    (0, 2, 223, 776, 1),
    (1, 0, 751, 248, 0),
    (1, 1, 447, 552, 1),
    (1, 2, 276, 723, 1),
    (2, 0, 751, 248, 0),
    (2, 1, 595, 404, 0),
    (2, 2, 595, 404, 0),
])
def test_buffapply_float_priority_shuffle_zygarde_vs_corsola(s1, s2, score0, score1, winner):
    a = _make_battle_pokemon(*ZYGARDE, s1, 15, 15, 15)
    d = _make_battle_pokemon(*CORSOLA_G, s2, 15, 15, 15)
    assert _score9(a, d) == (score0, score1, winner)
