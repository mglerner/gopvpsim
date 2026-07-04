"""FC-1: a fast move landing after an Aegislash Blade->Shield mid-flight revert
credits the CURRENT form's fast-move energy, not the stale queued move's.

When Aegislash (Blade) shields an incoming charged move while its own multi-turn
fast (Psycho Cut / Air Slash) is still in flight, the activate_shield revert
swaps its fast move to the Shield-form CHARGE variant. The in-flight fast then
resolves with damage from the NEW move (already correct) but, before the
2026-07-03 fix, energy from the OLD queued move dict: +9 (Blade's Psycho Cut)
instead of +6 (the Shield charge variant). That was an internally inconsistent
old-move-energy / new-move-damage mix. PvPoke uses the current move for both and
hard-codes energyGain=6 in shield form (Battle.js processAction); the Shield
charge variant's gamemaster energyGain is already 6, so crediting the current
fast move matches PvPoke. Full writeup:
docs/reviews/2026-07-02_engine_bug_hunt_round2.md (FC-1).

These cells are load-bearing for the fix (their score changes when the +9/+6
energy changes) AND equal the PvPoke oracle after it -- including a corrected
winner flip. Aegislash runs SHADOW_BALL only (single charged move) to avoid the
unrelated Gyro-Ball bug #3. Pinned to the sweep gamemaster (md5 363e44f3...,
sim-relevant subset identical to the worktree's live gamemaster); hard-coded
movesets/levels/scores, 15/15/15 opponents, Aegislash 4/14/15, bait-on both
sides.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402


def _run(opp_species, opp_fast, opp_charged, s_aegi, s_opp):
    # Aegislash (Shield) 4/14/15 -> L46; SHADOW_BALL only.
    aegi = _make_battle_pokemon('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
                                ['SHADOW_BALL'], 'great', s_aegi, 4, 14, 15)
    opp = _make_battle_pokemon(opp_species, opp_fast, opp_charged, 'great',
                               s_opp, 15, 15, 15)
    aegi.reset_for_battle(s_aegi, opponent=opp)
    opp.reset_for_battle(s_opp, opponent=aegi)
    r = simulate(aegi, opp, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)
    return round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner


@pytest.mark.parametrize("opp_species,opp_fast,opp_charged,s_aegi,s_opp,oracle", [
    # Jumpluff L34, 1-1. Load-bearing: pre-fix 719/280, post-fix (energy 6)
    # 654/345 == oracle. Winner unchanged (Aegislash wins).
    ('Jumpluff', 'FAIRY_WIND', ['ENERGY_BALL', 'ACROBATICS'], 1, 1, (654, 345, 0)),
    # Jumpluff L34, 1-2. Pre-fix 553/446, post-fix 561/438 == oracle.
    ('Jumpluff', 'FAIRY_WIND', ['ENERGY_BALL', 'ACROBATICS'], 1, 2, (561, 438, 0)),
    # Gligar L28, 2-1. CORRECTED WINNER FLIP: pre-fix 571/428 (Aegislash WINS)
    # -> post-fix 492/508 (Aegislash LOSES) == oracle winner 1.
    ('Gligar', 'WING_ATTACK', ['NIGHT_SLASH', 'DIG'], 2, 1, (492, 508, 1)),
])
def test_fc1_revert_energy_matches_oracle(opp_species, opp_fast, opp_charged,
                                          s_aegi, s_opp, oracle):
    assert _run(opp_species, opp_fast, opp_charged, s_aegi, s_opp) == oracle
