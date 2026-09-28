"""Regression pins for the 2026-09-28 DP farm-down insertion-order port.

PvPoke's DP (ActionLogic.js, the per-move loop in decideAction) inserts the
farm-down state BEFORE each charged move's expansion; until this port we
inserted it once AFTER all expansions (battle.py pvpoke_dp near-KO loop and
the numba kernel in _dp_jit.py). The two orders differ only on a same-turn
tie between the farm-down state and a ready charged-move state, which needs
`fm_to_ko * fast_turns == 1`: a 1-turn fast move whose single hit KOs. There
PvPoke pops the farm-down state first (keeps farming, keeps the energy); we
popped the charged state first (threw).

These are oracle pins: every expected value below was reproduced on PvPoke
master 78b1e66db via scripts/pvpoke_trace.js (score, winner, and chargedLog
all exact). The side whose DP moves is the one with the 1-turn fast move:
Corviknight (Sand Attack) and Kingdra (Dragon Breath).

REVERT-FAILS PROPERTY. Pre-port values (our engine at main b82ca59), recorded
so a revert is caught:
  vs Corviknight (1,1)  pre 434/565 w1, log ended "... Aegislash: Shadow Ball,
                        Corviknight: Air Cutter"; PvPoke 444/555 w1
  vs Corviknight (1,2)  pre 104/895 w1 (same trailing Air Cutter); PvPoke
                        114/885 w1
  vs Kingdra (2,2)      pre 173/826 w1, trailing "Kingdra: Swift"; PvPoke
                        191/808 w1
  Shield Air Slash vs Registeel (2,1)  (the F4 residual of the 2026-09-27
                        Aegislash diagnosis) pre 400/600 w1 with a trailing
                        "Registeel: Flash Cannon (shielded)" (log-only);
                        PvPoke 400/600 w1 without it. Lock On is 1-turn.

Setup: Aegislash (Blade), Psycho Cut / Shadow Ball + Gyro Ball (the F4 pin:
Aegislash (Shield), Aegislash Charge (Air Slash) / Shadow Ball + Flash
Cannon), 4/14/15 vs 15/15/15, Great League, level cap 50 (the production
cap; neither side reaches it under 1500 CP, so the 1080-cell sampler's
max_level=51 default gives the same cells). Opponent movesets are get_default_moveset(...,
'great') as of 2026-09-28, spelled out so upstream rankings drift cannot
silently re-aim the pins.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon, _extract_battle_log  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402

AEGI = ('Aegislash (Blade)', 'PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL'])
OPPS = {
    'Corviknight': ('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'IRON_HEAD']),
    'Kingdra': ('Kingdra', 'DRAGON_BREATH', ['SURF', 'SWIFT']),
    'Registeel': ('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST']),
}
AEGI_SHIELD_AS = ('Aegislash (Shield)', 'AEGISLASH_CHARGE_AIR_SLASH',
                  ['SHADOW_BALL', 'FLASH_CANNON'])
SB = 'Aegislash (Blade): Shadow Ball'
FC = 'Registeel: Flash Cannon'


@pytest.mark.parametrize("opp,s1,s2,score0,score1,winner,log", [
    # pre-port: 434/565 w1, log + ['Corviknight: Air Cutter']
    ('Corviknight', 1, 1, 444, 555, 1,
     [SB + ' (shielded)', 'Corviknight: Air Cutter (shielded)',
      'Corviknight: Iron Head', SB]),
    # pre-port: 104/895 w1, log + ['Corviknight: Air Cutter']
    ('Corviknight', 1, 2, 114, 885, 1,
     [SB + ' (shielded)', 'Corviknight: Air Cutter (shielded)',
      'Corviknight: Iron Head', SB + ' (shielded)']),
    # pre-port: 173/826 w1, log + ['Kingdra: Swift']
    ('Kingdra', 2, 2, 191, 808, 1,
     [SB + ' (shielded)', 'Kingdra: Swift (shielded)',
      'Kingdra: Surf (shielded)', 'Kingdra: Surf', SB + ' (shielded)']),
    # F4. pre-port: 400/600 w1, log + [FC + ' (shielded)']
    ('Registeel', 2, 1, 400, 600, 1,
     [FC, FC, FC, SB + ' (shielded)', FC + ' (shielded)', SB]),
])
def test_farmdown_order_matches_pvpoke(opp, s1, s2, score0, score1, winner, log):
    focal = AEGI_SHIELD_AS if opp == 'Registeel' else AEGI
    a = _make_battle_pokemon(*focal, 'great', s1, 4, 14, 15, max_level=50)
    o_species, o_fast, o_charged = OPPS[opp]
    d = _make_battle_pokemon(o_species, o_fast, o_charged, 'great', s2,
                             15, 15, 15, max_level=50)
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                 log=True, mechanics='new')
    got_log = _extract_battle_log(r)
    assert got_log, "empty chargedLog: the comparison would be vacuous"
    assert (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner) == \
        (score0, score1, winner)
    assert got_log == log
