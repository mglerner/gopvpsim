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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system; verified against the oracle harness (229/243 cells match
    # PvPoke exactly). See the step-B commit for the warrant.
    (0, 0, 412, 587, 1),
    (0, 1, 257, 742, 1),
    (0, 2, 102, 897, 1),
    (1, 0, 573, 426, 0),
    (1, 1, 423, 576, 1),
    (1, 2, 269, 730, 1),
    (2, 0, 725, 274, 0),
    (2, 1, 625, 375, 0),
    (2, 2, 625, 375, 0),
])
def test_shadow_quagsire_vs_gastrodon_fire_now_cmp(s1, s2, score0, score1, winner):
    a = _make_battle_pokemon(*SQ[:4], s1, 0, 15, 15, shadow=True)
    d = _make_battle_pokemon(*GA[:4], s2, 0, 15, 15)
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp, log=True)
    assert (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner) == (score0, score1, winner)


# ---------------------------------------------------------------------------
# The exact shadow-vs-plain CMP tie (2026-09-20; TODO.md:514-518)
# ---------------------------------------------------------------------------

Q = ('Quagsire', 'MUD_SHOT', ['AQUA_TAIL', 'STONE_EDGE'], 'great')


@pytest.mark.parametrize("ivs,s0,s1,pre_fix", [
    # PRE-FIX scores (p0 = the shadow), measured 2026-09-20 on the engine
    # at 36037e51a2ee by restoring the old ``atk / SHADOW_ATK_BONUS``
    # property and re-running. The artifact flips the winner in BOTH
    # directions, so this is not a one-sided rounding bias.
    ((0, 15, 15), 0, 0, (585, 414, 0)),
    ((0, 15, 15), 1, 1, (545, 454, 0)),
    ((0, 15, 15), 2, 2, (506, 493, 0)),
    ((0, 15, 14), 1, 1, (451, 548, 1)),
])
def test_an_exact_raw_attack_tie_is_a_cmp_tie(ivs, s0, s1, pre_fix):
    """A shadow and a plain mon with the same raw attack must TIE on CMP.

    Same species, same IVs, one shadow: the shadow multiplier changes
    damage and bulk but not the pre-shadow attack, so CMP is an exact tie
    and the engine drops priority entirely (``use_priority`` False, PROP-1
    player-index order). The fight is then a genuine simultaneous double-KO
    -- both sides end on 0 HP at turn 36 -- and scores 500/500.

    PRE-FIX ``cmp_atk`` reconstructed the shadow side's raw attack as
    ``atk / SHADOW_ATK_BONUS``, and that round trip comes back one ULP low
    for these spreads. The tie became a loss for the shadow, priority came
    back on, one side threw first, and one side walked away alive: the
    ``pre_fix`` triples above. Those are not just different scores, they
    are different WINNERS.
    """
    a = _make_battle_pokemon(*Q, s0, *ivs, shadow=True)
    b = _make_battle_pokemon(*Q, s1, *ivs)
    assert a.shadow and not b.shadow
    assert a.atk != b.atk and a.def_ != b.def_      # really is a shadow
    assert a.raw_atk == b.raw_atk                   # ... on an exact CMP tie
    assert a.cmp_atk == b.cmp_atk                   # pre-fix: a was 1 ULP low
    r = simulate(a, b, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)
    got = (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner)
    assert got != pre_fix
    assert got == (500, 500, None), got
    assert a.hp == 0 and b.hp == 0                  # simultaneous KO


def test_the_shadow_round_trip_is_gone_from_cmp():
    """``cmp_atk`` reads a carried value, never a division.

    The float fact itself is unchanged -- ``fl(fl(x*6/5)/(6/5))`` is still
    one ULP low for Quagsire 0/15/14, and tests/test_worlds_tier0.py still
    pins it. What this asserts is that the artifact no longer reaches the
    comparison: the shadow mon's ``cmp_atk`` is its true pre-shadow attack,
    which is what the plain twin's is.
    """
    import math
    from gopvpsim.pokemon import SHADOW_ATK_BONUS
    a = _make_battle_pokemon(*Q, 1, 0, 15, 14, shadow=True)
    b = _make_battle_pokemon(*Q, 1, 0, 15, 14)
    round_trip = a.atk / SHADOW_ATK_BONUS
    assert round_trip == math.nextafter(b.atk, -math.inf)   # the artifact
    assert a.cmp_atk != round_trip                          # pre-fix: equal
    assert a.cmp_atk == b.atk == a.raw_atk
