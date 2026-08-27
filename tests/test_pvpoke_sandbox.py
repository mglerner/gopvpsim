"""pvpoke_sandbox: replayable pvpoke.com link generation + verification.

Adopted 2026-08-27 after two adversarial reviews (skeptic_sandbox_lib /
skeptic_sandbox_links, scratchpad); these tests pin the six gating
fixes those reviews mandated, each of which FAILS against the pre-fix
library. Needs node + the ../pvpoke checkout, hence local_artifacts.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

pytestmark = pytest.mark.local_artifacts

_PVPOKE = Path(__file__).resolve().parents[2] / 'pvpoke'
if not _PVPOKE.exists():
    pytest.skip('../pvpoke checkout not present', allow_module_level=True)

from pvpoke_sandbox import (  # noqa: E402
    PokeSpec,
    move_pools,
    sandbox_url,
    timeline_to_actions,
    verify_url,
)


def test_no_phantom_return_in_pools():
    """Gating fix 1: the level25CP gate must match JS semantics --
    kingler at 1500 has NO RETURN entry (pre-fix: phantom RETURN
    shifted every later index; VICE_GRIP decoded as WATER_PULSE)."""
    fast, charged = move_pools('kingler', 1500)
    assert 'RETURN' not in charged
    assert 'VICE_GRIP' in charged


def test_single_charged_move_pads_move_segment():
    """Gating fix 3: one-charged-move specs emit a trailing -0 so
    PvPoke does not auto-select a second charged move."""
    spec = PokeSpec('cramorant', level=26.0, ivs=(5, 15, 13),
                    fast='PECK', charged=['DIVE'])
    url = sandbox_url(1500, spec, PokeSpec('azumarill', level=43.0,
                                           ivs=(4, 15, 13), fast='BUBBLE',
                                           charged=['ICE_BEAM']),
                      (0, 0), [])
    segs = url.rstrip('/').split('/')
    assert segs[-3].endswith('-0') and segs[-2].endswith('-0')


def test_mirror_timeline_refused():
    """Gating fix 2: mirror matches cannot be actor-attributed from
    names; timeline_to_actions must refuse rather than silently
    misattribute (pre-fix: every action went to player 0)."""
    from gopvpsim.battle import simulate, pvpoke_dp
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from cramorant_policy_lab import make_bp
    a = make_bp('Cramorant', 'great', False, 'PECK', ['DIVE', 'FLY'])
    b = make_bp('Cramorant', 'great', False, 'PECK', ['DIVE', 'FLY'])
    a.reset_for_battle(1, b)
    b.reset_for_battle(1, a)
    r = simulate(a, b, charged_policy_0=pvpoke_dp,
                 charged_policy_1=pvpoke_dp, log=True)
    with pytest.raises(ValueError):
        timeline_to_actions(r, a, b)


def test_level_cap_sandbox_url_refused():
    """Gating fix 6: sandbox routing rejects CP-dash-cap segments
    upstream (.htaccess uses (\\d+) for sandbox rules); the lib must
    refuse loudly instead of emitting a 404 link."""
    spec = PokeSpec('cramorant', level=26.0, ivs=(5, 15, 13),
                    fast='PECK', charged=['DIVE', 'FLY'])
    other = PokeSpec('azumarill', level=43.0, ivs=(4, 15, 13),
                     fast='BUBBLE', charged=['ICE_BEAM', 'PLAY_ROUGH'])
    with pytest.raises(ValueError):
        sandbox_url(1500, spec, other, (0, 0), [], level_cap=40)


def test_verify_url_reproduces_showcase_and_start_state():
    """Gating fixes 4+5 and the E1 gate: verify_url decodes the URL
    STRING (routing + dropdown indices + pinned spread + actions) and
    runs PvPoke's Battle.js. Showcase 1 (GL Azumarill 0-0) must
    reproduce the certified 674 with the exact end state; and an
    energy-segment URL must actually apply the start state (pre-fix:
    start_hp was silently clobbered -- a false green)."""
    url = ('https://pvpoke.com/battle/sandbox/1500/'
           'cramorant-26-5-15-13-4-4-1-1/azumarill-43-4-15-13-4-4-1-1/'
           '00/0-1-2/0-2-3/15.100000-19.110000-28.101000/')
    got = verify_url(url)
    assert round(got['score'][0]) == 674
    assert got['hp'] == [44, 0]
    assert got['shields'] == [0, 0]
    # start-state grammar: identity control (full HP, zero energy) must
    # match the plain run exactly; a lowered start_hp must not.
    ident = verify_url(url.replace('/00/', '/00/').replace(
        '/15.100000', '/126-191/0-0/15.100000'))
    assert round(ident['score'][0]) == 674
    hurt = verify_url(url.replace('/15.100000',
                                  '/60-191/0-0/15.100000'))
    assert round(hurt['score'][0]) != 674


# ---------------------------------------------------------------------------
# Cancelled charged decisions (KO-edge encoder gap, resolved 2026-08-27)
# ---------------------------------------------------------------------------

def _cramorant_lapras_ul_1_1():
    """The KO-edge reference cell: UL Cramorant (L50 15/15/15, PECK /
    Dive+Fly, PoGoDives tier) vs Lapras (L36 15/15/15, PSYWAVE /
    Sparkling Aria+Ice Beam), 1-1 shields. Cramorant's Fly KOs Lapras on
    turn 37 while Lapras has Sparkling Aria decided, so the CMP loser's
    charged move is cancelled."""
    from gopvpsim.battle import (pogodives_dp, pogodives_shield, pvpoke_dp,
                                 simulate)
    from cramorant_policy_lab import make_bp
    a = make_bp('Cramorant', 'ultra', False, 'PECK', ['DIVE', 'FLY'],
                ivs=(15, 15, 15))
    b = make_bp('Lapras', 'ultra', False, 'PSYWAVE',
                ['SPARKLING_ARIA', 'ICE_BEAM'], ivs=(15, 15, 15))
    a.reset_for_battle(1, b)
    b.reset_for_battle(1, a)
    r = simulate(a, b, charged_policy_0=pogodives_dp,
                 charged_policy_1=pvpoke_dp,
                 shield_policy_0=pogodives_shield, log=True)
    return a, b, r


def test_cancelled_charged_is_logged_only_under_log():
    """battle.py log_cancel: a charged move that was DECIDED and then
    cancelled leaves a timeline line, gated on log=True like every other
    timeline append. Pre-fix the cancel was silent, which is what left
    timeline_to_actions with nothing to encode (test below)."""
    from gopvpsim.battle import (pogodives_dp, pogodives_shield, pvpoke_dp,
                                 simulate)
    from cramorant_policy_lab import make_bp
    _a, _b, r = _cramorant_lapras_ul_1_1()
    assert r.pvpoke_score(0) == 662 and r.hp_remaining == [51, 0]
    cancels = [ln for ln in r.timeline if 'CANCELLED' in ln]
    assert cancels == ['T 37: Lapras Sparkling Aria CANCELLED (cmp_ko)'], (
        f'expected exactly the turn-37 CMP cancel, got {cancels}')
    # The wording is parsed by pvpoke_sandbox._CANCEL_RE and must stay
    # clear of every OTHER timeline consumer's key (see log_cancel's
    # comment): no " uses ", no U+2192, no "dmg".
    line, = cancels
    assert ' uses ' not in line and '→' not in line and 'dmg' not in line

    # log=False: same fight, no timeline at all.
    a = make_bp('Cramorant', 'ultra', False, 'PECK', ['DIVE', 'FLY'],
                ivs=(15, 15, 15))
    b = make_bp('Lapras', 'ultra', False, 'PSYWAVE',
                ['SPARKLING_ARIA', 'ICE_BEAM'], ivs=(15, 15, 15))
    a.reset_for_battle(1, b)
    b.reset_for_battle(1, a)
    quiet = simulate(a, b, charged_policy_0=pogodives_dp,
                     charged_policy_1=pvpoke_dp,
                     shield_policy_0=pogodives_shield, log=False)
    assert quiet.pvpoke_score(0) == 662, 'logging must not change the fight'
    assert not any('CANCELLED' in ln for ln in quiet.timeline)


def test_cancelled_charged_is_encoded_as_an_action():
    """KO-edge encoder gap: timeline_to_actions only emitted charged moves
    that RESOLVED, so the turn-37 Sparkling Aria left no action and
    PvPoke's sandbox threw Lapras' naturally-due Psywave instead --
    replaying a fight 2 damage different from ours (link read 656 / HP
    [49, 0] against the sim's 662 / HP [51, 0]).

    Encoder-level pin (pure Python, no node): the cancelled decision must
    be encoded as player 1's charged move 0 on turn 37. PvPoke cancels the
    same action for the same reason (Battle.js:462-490), so the link is a
    faithful replay; the round-trip through Battle.js is pinned by
    test_cancelled_charged_sandbox_replays_the_same_fight below."""
    a, b, r = _cramorant_lapras_ul_1_1()
    acts, auto = timeline_to_actions(r, a, b)
    tokens = [x.token() for x in acts]
    assert '37.110000' in tokens, (
        f'the cancelled turn-37 Sparkling Aria was not encoded: {tokens}')
    # ... alongside the Fly that caused the KO, on the same turn.
    assert '37.101000' in tokens, f'{tokens}'
    assert auto == [(26, 'Gulp Missile (Arrokuda)')], auto


def test_cancelled_charged_sandbox_replays_the_same_fight():
    """The publish gate, end to end through the real URL: the link built
    from timeline_to_actions' OWN output must make PvPoke's Battle.js
    reproduce the sim exactly (662, HP [51, 0], shields [0, 0]).

    Pre-fix the encoder emitted the action list without the turn-37
    Sparkling Aria and the same link read 656 / HP [49, 0] -- PvPoke
    threw Lapras' naturally-due Psywave on the KO turn instead. That
    exact pre-fix script is re-run below as a control, so this test
    fails if the fix regresses AND if the reference cell drifts."""
    from gopvpsim.pokemon import Pokemon
    a, b, r = _cramorant_lapras_ul_1_1()
    acts, _auto = timeline_to_actions(r, a, b)
    pa = Pokemon.at_best_level('Cramorant', 15, 15, 15, league='ultra')
    pb = Pokemon.at_best_level('Lapras', 15, 15, 15, league='ultra')
    s0 = PokeSpec('cramorant', level=pa.level, ivs=(15, 15, 15),
                  fast='PECK', charged=['DIVE', 'FLY'])
    s1 = PokeSpec('lapras', level=pb.level, ivs=(15, 15, 15),
                  fast='PSYWAVE', charged=['SPARKLING_ARIA', 'ICE_BEAM'])
    url = sandbox_url(2500, s0, s1, (1, 1), acts)
    got = verify_url(url)
    assert (round(got['score'][0]), got['hp'], got['shields']) == (
        662, [51, 0], [0, 0]), (
        f'the link does not replay the sim (662 / [51, 0]): {url}')
    assert round(got['score'][0]) == r.pvpoke_score(0)

    # Control: the pre-fix action script (identical but for the missing
    # cancelled action) replays a DIFFERENT fight.
    pre = url.replace('-37.110000/', '/')
    assert pre != url, f'the cancelled action is missing from {url}'
    was = verify_url(pre)
    assert (round(was['score'][0]), was['hp']) == (656, [49, 0]), (
        'the pre-fix control no longer reproduces the encoder gap; the '
        'reference cell has drifted and this pin needs re-deriving')


def test_cancel_line_wording_change_is_a_hard_error():
    """Coupling guard: _CANCEL_RE is pinned to battle.py's wording, and a
    line that says CANCELLED but does not parse must raise rather than
    silently drop the action (the failure mode this whole fix removes)."""
    import types
    a, b, r = _cramorant_lapras_ul_1_1()
    broken = types.SimpleNamespace(timeline=[
        ln.replace('CANCELLED (cmp_ko)', 'CANCELLED (cmp_ko) [reworded]')
        if 'CANCELLED' in ln else ln
        for ln in r.timeline])
    with pytest.raises(ValueError, match='unparseable cancelled-charged'):
        timeline_to_actions(broken, a, b)
