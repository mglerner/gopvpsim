"""Regression: the fire_now double-fire CMP gate must use the shadow-FREE
attack (cmp_atk), not the shadow-boosted .atk.

The shadow x1.2 multiplier boosts DAMAGE, not charged-move PRIORITY. The
2026-06-13 shadow-CMP migration switched 9 CMP comparison sites to cmp_atk;
the double-fire gate in pvpoke_dp's fire_now branch (battle.py ~:1177-1188)
was the missed 10th site. With the bug, any defender whose attack stat sits
between a shadow attacker's cmp_atk and its boosted atk wrongly trips the
"I win CMP, fire twice" branch -- which flips real winners.

Found by the 2026-06-27 adversarial engine bug-hunt; see
docs/reviews/2026-06-27_engine_bug_hunt.md. Every cell below was validated
against PvPoke's live engine via scripts/pvpoke_trace.js (Shadow Quagsire vs
Gastrodon, IVs 0/15/15 both). The 2v1 cell is the bug signature: pre-fix our
sim said Quagsire won 625/375; PvPoke (and the fix) say Gastrodon wins
459/540.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402

SQ = ('Quagsire', 'MUD_SHOT', ['AQUA_TAIL', 'MUD_BOMB'], 'great')   # shadow
GA = ('Gastrodon', 'MUD_SLAP', ['BODY_SLAM', 'EARTH_POWER'], 'great')


@pytest.mark.parametrize("s1,s2,score0,score1,winner", [
    (0, 0, 412, 587, 1),
    (0, 1, 257, 742, 1),
    (0, 2, 102, 897, 1),
    (1, 0, 597, 402, 0),
    (1, 1, 423, 576, 1),
    (1, 2, 269, 730, 1),
    (2, 0, 725, 274, 0),
    (2, 1, 459, 540, 1),   # <- winner-flip cell the cmp_atk fix corrects
    (2, 2, 333, 666, 1),
])
def test_shadow_quagsire_vs_gastrodon_fire_now_cmp(s1, s2, score0, score1, winner):
    a = _make_battle_pokemon(*SQ[:4], s1, 0, 15, 15, shadow=True)
    d = _make_battle_pokemon(*GA[:4], s2, 0, 15, 15)
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp, log=True)
    assert (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner) == (score0, score1, winner)
