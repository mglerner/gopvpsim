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
