"""Regression: in NO-BAIT analysis we keep a self-debuff closer from throwing
its nuke into a guaranteed shield -- an INTENTIONAL divergence from PvPoke.

pvpoke_dp's bandaid[929] (battle.py ~1731) swaps a self-debuffing max-damage
move to a cheaper non-debuffing move when the opponent would shield it. PvPoke
gates this swap on baitShields (ActionLogic.js:947); we do NOT. When
would_shield is True the move is shielded either way (1 dmg), so the swap is
avoid-waste (skip the -atk/-def on a throw that is shielded regardless), not
bait tempo -- and it is consistent with the ungated [910]/[918] self-debuff
timing. PvPoke's gated line throws the self-debuffing nuke into the shield:
strictly dominated.

There is no PvPoke oracle for this: scripts/pvpoke_trace.js cannot set
baitShields, so the no-bait dimension is never compared upstream and this is
invisible to the (bait-on) oracle suite. This test therefore pins OUR
verified-correct behavior. Full writeup: DEVELOPER_NOTES "Known divergences",
docs/pvpoke_divergences.md #6.

Measured (2026-06-27 A/B, focal no-bait vs bait-on opponent, GL+UL self-debuff
focals x 9 shields): gating to match PvPoke would change 1184 focal-score cells
and flip 284 winners, ALL focal-wins-ungated -> loses-gated, zero the other way.
Traced cell pinned below: Malamar vs Furret 1-1, ours 769 vs gated 237.
"""
import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402

NOBAIT = functools.partial(pvpoke_dp, bait_shields=False)


def _malamar_charged_throws(timeline):
    return [ln for ln in timeline
            if 'Malamar uses' in ln
            and ('Foul Play' in ln or 'Superpower' in ln or 'Super Power' in ln)]


def test_nobait_keeps_self_debuff_nuke_out_of_a_shield():
    # Malamar: Super Power (self-debuffing nuke) + Foul Play (cheaper, non-debuff).
    mal = _make_battle_pokemon('Malamar', 'PSYWAVE', ['SUPER_POWER', 'FOUL_PLAY'],
                               'great', 1, 15, 15, 15)
    fur = _make_battle_pokemon('Furret', 'SUCKER_PUNCH', ['SWIFT', 'TRAILBLAZE'],
                               'great', 1, 15, 15, 15)
    mal.reset_for_battle(1, opponent=fur)
    fur.reset_for_battle(1, opponent=mal)
    # Focal no-bait, opponent bait-ON -- exactly the dive's bait-off dimension.
    r = simulate(mal, fur, charged_policy_0=NOBAIT, charged_policy_1=pvpoke_dp, log=True)
    # We win: the swap avoids dumping Super Power into the shield + eating -atk/-def.
    # (Gating bandaid[929] to match PvPoke flips this to a loss.)
    assert r.pvpoke_score(0) > 500
    # The first charged move Malamar commits is Foul Play, NOT the self-debuffing
    # Super Power (which would just be shielded).
    throws = _malamar_charged_throws(r.timeline)
    assert throws, 'expected a Malamar charged throw in the timeline'
    assert 'Foul Play' in throws[0], f'expected Foul Play first, got: {throws[0]}'
