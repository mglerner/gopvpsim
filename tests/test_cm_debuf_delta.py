"""Regression: _cm_debuf_delta's guaranteed-self-buff arm (bug #7).

The raw gamemaster stores `buffApplyChance` as a STRING ('1' for guaranteed),
so the original `m.get('buffApplyChance') == 1` int-compare was always False --
a dead branch. PvPoke's JS does the same comparison with loose equality
(`"1" == 1` -> True, ActionLogic.js:575,584), so the "prefer the path with more
buff chances" credit fired there but not in our port. The fix compares as
`float(...) == 1.0`. These tests pin the corrected per-move delta so the dead
branch cannot silently come back.

The delta feeds only the DP dedup tie-break debuff count; it is value-neutral
inside a DP node (impact empirically + structurally zero -- see DEVELOPER_NOTES
"RESOLVED 2026-06-27 (bug #7)"), but it must stay faithful to PvPoke's count.
"""
from gopvpsim.battle import _cm_debuf_delta
from gopvpsim.moves import get_moves

_, _CM = get_moves()


def test_buffapplychance_is_a_string_in_the_gamemaster():
    # The whole point of the fix: the raw value is a STRING, not an int. If this
    # ever changes to a number upstream, the float() guard still works, but the
    # `== 1` regression these tests guard against would no longer be silent.
    assert _CM['POWER_UP_PUNCH']['buffApplyChance'] == '1'
    assert isinstance(_CM['POWER_UP_PUNCH']['buffApplyChance'], str)


def test_guaranteed_atk_self_buff_credits_minus_one():
    # Atk-buffing guaranteed self-buff moves: the string '1' must classify as
    # guaranteed (-1). A revert to `== 1` would yield 0 and fail here.
    for cid in ('POWER_UP_PUNCH', 'TRAILBLAZE', 'RAGE_FIST'):
        assert _cm_debuf_delta(_CM[cid]) == -1, cid


def test_guaranteed_pure_def_self_buff_credits_minus_one():
    # Pure-def self-buff moves (buffs [0, +1]) are the only class that can
    # actually re-rank a dedup tie (they leave atk_stage unchanged), so pin them.
    for cid in ('SKULL_BASH', 'DRAIN_PUNCH'):
        assert _cm_debuf_delta(_CM[cid]) == -1, cid


def test_self_debuffing_move_is_plus_one():
    assert _cm_debuf_delta(_CM['CLOSE_COMBAT']) == 1


def test_non_buff_move_is_zero():
    assert _cm_debuf_delta(_CM['HYDRO_CANNON']) == 0
