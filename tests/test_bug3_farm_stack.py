"""Regression: the farm-down ("many-cycle") branch must STACK self-debuffing
charged moves -- hold the throw until energy is within one fast-move-gain of
the cap so the debuffing moves land back-to-back near the end -- instead of
firing one at first affordability and then spending extra turns at -atk.

This ports PvPoke ActionLogic.js:399-405 (the "Stack self debuffing moves"
gate), which our farm-down early-return omitted. Bug #3 from the 2026-06-27
adversarial engine bug-hunt; see docs/reviews/2026-06-27_engine_bug_hunt.md.

The gate only fires when the selected farm-down move is self-debuffing -- i.e.
the focal's moveset is self-debuff-dominant (no non-debuffing alt within 2x
DPE). Pinsir (Fury Cutter / Close Combat + Super Power) vs the bulky wall
Cresselia is the canonical case: both charged moves are self-debuffing, so
the farm-swap can't dodge the debuff and the stack gate engages. Pre-fix our
0-0 score was 631 (Pinsir fires Close Combat early at ~T15); post-fix it is
656 (Pinsir stacks the debuffing throws near T25-26), matching PvPoke.

Every cell below was validated against PvPoke's live engine via
scripts/pvpoke_trace.js at 15/15/15 IVs both sides (9/9 exact on winner +
score).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402

PINSIR = ('Pinsir', 'FURY_CUTTER', ['CLOSE_COMBAT', 'SUPER_POWER'], 'great')
CRESSELIA = ('Cresselia', 'PSYCHO_CUT', ['GRASS_KNOT', 'MOONBLAST'], 'great')


@pytest.mark.parametrize("s1,s2,score0,score1,winner", [
    (0, 0, 656, 343, 0),   # <- repro cell: 631 (early fire) -> 656 (stacked)
    (0, 1, 325, 674, 1),
    (0, 2, 325, 674, 1),
    (1, 0, 813, 186, 0),
    (1, 1, 351, 648, 1),
    (1, 2, 351, 648, 1),
    (2, 0, 813, 186, 0),
    (2, 1, 757, 242, 0),
    (2, 2, 681, 318, 0),
])
def test_pinsir_vs_cresselia_farm_stack(s1, s2, score0, score1, winner):
    a = _make_battle_pokemon(*PINSIR, s1, 15, 15, 15)
    d = _make_battle_pokemon(*CRESSELIA, s2, 15, 15, 15)
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp, log=True)
    assert (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner) == (score0, score1, winner)
