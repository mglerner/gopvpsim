"""Seat-ambiguous stage-probe attribution (scripts/joint_iv_breakpoints.py).

Guard commit 373bae8 ("joint_iv: seat-aware stage-probe attribution for
same-species pairs"); pre-guard SHA 438a5ef.

On a same-species pair whose OPPONENT also carries the focal's
attack-debuff move, a timeline line ("Thievul uses Icy Wind -> ...")
cannot be attributed to a seat.  Pre-guard, the opponent's own throws
made the `iw_count > 0` test a FALSE POSITIVE: an honest
`debuff_unreachable` finding was masked and the run died instead with
"ABORT: no stage probe observed the Icy Wind debuff".  The guard counts
the focal's throws from the OPPONENT's post-fight attack stage
(``simulate`` mutates ``lp``), aborts when another move in either kit
can also move that stage, and SKIPS (never trusts) a candidate fight in
which a chance self-buff's engine meter could already have fired.

The behavioral tests monkeypatch ``simulate`` for the stage-probe
fights only -- the sim_check probes that run first are delegated to the
real engine, so their closed-form assertions still bite.  Each test
records the value observed at the pre-guard SHA.
"""
import ast
import json
import math
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / 'scripts'))

import joint_iv_breakpoints as bp  # noqa: E402
from battle import make_battle_pokemon  # noqa: E402  (scripts/battle.py)
from gopvpsim.battle import _apply_move_buffs  # noqa: E402

_SCRIPT = _ROOT / 'scripts' / 'joint_iv_breakpoints.py'
_REAL_SIMULATE = bp.simulate
_REAL_GET_MOVES = bp.get_moves

# battle.py's timeline emits a genuine U+2192 between move and damage
# ("Thievul uses Icy Wind U+2192 24 dmg"); the script's parser splits on
# it, so the canned lines must carry it.  Spelled as an escape to keep
# this file ASCII.
_ARROW = chr(0x2192)

# A true mirror: both seats are Thievul, both carry Icy Wind (the
# opponent-attack debuff) -- the seat-ambiguous shape the guard exists
# for.  Written to tmp_path so the test never depends on a shipped
# pairs/*.toml (those differ between HEAD and the pre-guard SHA).
_PAIR_TOML = '''
[pair]
league = "great"
focal = "Thievul"
focal_shadow = false
focal_slug = "thievul"
opponent = "Thievul"
opponent_shadow = false
opponent_slug = "thievul"
opponent_fast = "SUCKER_PUNCH"
opponent_charged = ["ICY_WIND", "NIGHT_SLASH"]
data_dir = "userdata/joint_iv/test_seat_ambiguous"
injected_moves = []

[breakpoints]
opp_key = "opp"
opp_short = "opp"
assert_focal_default_moveset = false
assert_opponent_default_moveset = false

[[grids]]
label = "iwns_bait"
focal_fast = "SUCKER_PUNCH"
focal_charged = ["ICY_WIND", "NIGHT_SLASH"]
bait = true
'''

_FAST_LINE = 'T  2: Thievul fast %s 4 dmg, energy 7' % _ARROW
# Shielded throws carry no stage information, so they land in the
# name-ambiguous `uses <move>` count WITHOUT contributing an observable
# ladder sample -- exactly the shape that made the pre-guard count a
# false positive.
_IW_SHIELDED = 'T 11: Thievul uses Icy Wind %s SHIELDED (1 dmg)' % _ARROW
_NS_SHIELDED = 'T 13: Thievul uses Night Slash %s SHIELDED (1 dmg)' % _ARROW


def _write_pair(tmp_path):
    p = tmp_path / 'pair.toml'
    p.write_text(_PAIR_TOML)
    return p


# The auto-probe candidate ladder is six fights (default, 1 shield,
# 2 shields, then three extreme-spread builds) at both HEAD and the
# pre-guard SHA; none of the canned fights below observes the ladder, so
# all six run.
_N_CANDIDATES = 6


def _patch_probe_sims(monkeypatch, cfg_path, timeline, atk_stage):
    """Cann the stage-probe fights ONLY; every other fight stays real.

    main() simulates in three places: one sim_check fight per focal ARM
    (closed-form `match` assertions -- must stay real), then the
    stage-probe candidates, then the resisted-move probes (which assert
    a real hit landed).  Only the middle window is canned, and it gets
    the post-fight `lp.atk_stage` the guard reads (simulate mutates lp).
    """
    n_real = len(bp.focal_arms(bp.load_pair(cfg_path)))
    calls = []
    canned = []

    def fake_simulate(tp, lp, **kw):
        calls.append(kw)
        if not n_real < len(calls) <= n_real + _N_CANDIDATES:
            return _REAL_SIMULATE(tp, lp, **kw)
        canned.append(len(calls))
        lp.atk_stage = atk_stage        # simulate() mutates lp
        return types.SimpleNamespace(timeline=list(timeline))

    monkeypatch.setattr(bp, 'simulate', fake_simulate)
    return canned, n_real


def _run_main(tmp_path, monkeypatch, timeline, atk_stage, get_moves=None):
    cfg_path = _write_pair(tmp_path)
    out = tmp_path / 'breakpoints.json'
    canned, _n_real = _patch_probe_sims(monkeypatch, cfg_path, timeline,
                                        atk_stage)
    if get_moves is not None:
        monkeypatch.setattr(bp, 'get_moves', get_moves)
    monkeypatch.setattr(sys, 'argv', ['joint_iv_breakpoints.py',
                                      str(cfg_path), '--out', str(out)])
    bp.main()
    # Non-triviality control: every candidate fight must actually have
    # been the canned one, or the assertions below would be vacuous.
    assert len(canned) == _N_CANDIDATES, canned
    data = json.loads(out.read_text())
    return data['verification']['icy_wind_stage_check']


def _moves_with_guaranteed_night_slash():
    """get_moves() with Night Slash's self-atk buff made GUARANTEED.

    Thievul's real Night Slash is a 12.5% chance buff; a guaranteed one
    is the unsound case the guard must refuse outright.  Copies the move
    dict so the shared move cache is never mutated.
    """
    fast, charged = _REAL_GET_MOVES()
    charged = {k: dict(v) for k, v in charged.items()}
    charged['NIGHT_SLASH']['buffApplyChance'] = '1'
    return fast, charged


def _extract_meter_can_fire():
    """The guard's nested `_meter_can_fire`, pulled out by ast.

    It lives inside ``main()`` (it closes over nothing), so a direct
    unit test has to lift the FunctionDef out of the source.  Pre-guard
    438a5ef defines it 0 times.
    """
    tree = ast.parse(_SCRIPT.read_text())
    fns = [n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef) and n.name == '_meter_can_fire']
    assert len(fns) == 1, (
        'expected exactly one _meter_can_fire definition in %s, found %d '
        '(pre-guard 438a5ef: 0 -- the buff-meter bound did not exist)'
        % (_SCRIPT.name, len(fns)))
    ns = {'math': math}
    exec(compile(ast.Module(body=fns, type_ignores=[]), str(_SCRIPT), 'exec'),
         ns)
    return ns['_meter_can_fire']


def _engine_first_fire(chance, max_throws):
    """First throw index (1-based) on which the ENGINE's buff meter fires.

    Independent oracle for `_meter_can_fire`: drives
    gopvpsim.battle._apply_move_buffs, the code the bound is a model of.
    Returns None if it never fires within `max_throws`.
    """
    atk = make_battle_pokemon('Thievul', 'SUCKER_PUNCH',
                              ['ICY_WIND', 'NIGHT_SLASH'], 'great', 1,
                              0, 15, 11, shadow=False)
    dfn = make_battle_pokemon('Thievul', 'SUCKER_PUNCH',
                              ['ICY_WIND', 'NIGHT_SLASH'], 'great', 1,
                              0, 15, 11, shadow=False)
    mv = {'moveId': 'TEST_CHANCE_BUFF', 'name': 'Test Chance Buff',
          'buffs': [1, 0], 'buffTarget': 'self',
          'buffApplyChance': repr(chance)}
    for n in range(1, max_throws + 1):
        _apply_move_buffs(atk, dfn, mv)
        if atk.atk_stage != 0:
            return n
    return None


# ---------------------------------------------------------------------------
# (a)/(b) throw attribution: the name count is not evidence; the stage is
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_opponent_only_throws_record_debuff_unreachable(tmp_path,
                                                        monkeypatch):
    """Opponent-only Icy Wind + atk_stage 0 -> honest debuff_unreachable.

    Pre-guard 438a5ef: the shielded 'Thievul uses Icy Wind' line made
    `iw_count > 0` -> any_thrown True -> SystemExit
    "ABORT: no stage probe observed the Icy Wind debuff (tried 6
    candidate fights; the move WAS thrown in at least one ...)".
    """
    chk = _run_main(tmp_path, monkeypatch,
                    timeline=[_FAST_LINE, _IW_SHIELDED], atk_stage=0)
    assert chk['debuff_unreachable'] is True
    assert chk['candidates_tried'] == 6
    assert 'never thrown' in chk['note']


@pytest.mark.slow
def test_negative_opponent_atk_stage_counts_as_thrown(tmp_path, monkeypatch):
    """No 'uses Icy Wind' line at all, but lp.atk_stage < 0 -> thrown.

    The debuff landed (the opponent ended the fight at -1) even though
    the pooled name count is 0.  Pre-guard 438a5ef recorded
    `debuff_unreachable: True` here -- a false NEGATIVE, the mirror of
    case (a).
    """
    chk = _run_main(tmp_path, monkeypatch, timeline=[_FAST_LINE],
                    atk_stage=-1)
    assert 'debuff_unreachable' not in chk, chk
    # Positive control: the throw was counted, so the run lands on the
    # thrown-but-unobservable finding instead.
    assert chk['debuff_thrown_only_shielded'] is True


# ---------------------------------------------------------------------------
# (c) another guaranteed mover of the opponent's attack stage -> abort
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_guaranteed_opponent_self_atk_buff_aborts(tmp_path, monkeypatch):
    """A guaranteed self-atk buff in the opponent's kit is unsound.

    With Night Slash's buff guaranteed, a post-fight stage cannot be
    read as "the focal threw the debuff N times", so the pair must be
    refused loudly.  Pre-guard 438a5ef had no such check: it completed
    and recorded `debuff_unreachable: True` from the name count.
    """
    cfg_path = _write_pair(tmp_path)
    out = tmp_path / 'breakpoints.json'
    _patch_probe_sims(monkeypatch, cfg_path, [_FAST_LINE], 0)
    monkeypatch.setattr(bp, 'get_moves', _moves_with_guaranteed_night_slash)
    monkeypatch.setattr(sys, 'argv', ['joint_iv_breakpoints.py',
                                      str(cfg_path), '--out', str(out)])
    with pytest.raises(SystemExit,
                       match=r"can also move the opponent's attack stage"):
        bp.main()


# ---------------------------------------------------------------------------
# (d) the chance-self-buff meter bound skips unsound candidate fights
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_meter_bound_skips_candidate_at_seven_night_slashes(tmp_path,
                                                            monkeypatch):
    """7 pooled Night Slashes (12.5%) can fire the meter -> skip the fight.

    All 6 candidates are skipped, so the recorded finding must disclose
    the skips and count 0 fights tried.  Pre-guard 438a5ef: no skip
    logic and `iw_count > 0` -> SystemExit "ABORT: no stage probe
    observed the Icy Wind debuff".
    """
    chk = _run_main(tmp_path, monkeypatch,
                    timeline=[_FAST_LINE, _IW_SHIELDED] + [_NS_SHIELDED] * 7,
                    atk_stage=0)
    assert chk['debuff_unreachable'] is True
    assert chk['candidates_tried'] == 0
    assert '6 further candidate(s) skipped' in chk['note']


@pytest.mark.slow
def test_meter_bound_keeps_candidate_at_six_night_slashes(tmp_path,
                                                          monkeypatch):
    """6 pooled Night Slashes cannot fire the meter -> the fight counts.

    Same canned fight as the 7-throw case bar one Night Slash: nothing
    is skipped, so all 6 candidates are tried and the disclosure is
    absent.  Pre-guard 438a5ef: SystemExit, as above.
    """
    chk = _run_main(tmp_path, monkeypatch,
                    timeline=[_FAST_LINE, _IW_SHIELDED] + [_NS_SHIELDED] * 6,
                    atk_stage=0)
    assert chk['debuff_unreachable'] is True
    assert chk['candidates_tried'] == 6
    # (the standing 'not silently skipped' phrase is why this pins the
    # skip DISCLOSURE, not the bare word)
    assert 'candidate(s) skipped' not in chk['note']


def test_meter_can_fire_boundaries():
    """The bound itself: 12.5% fires on throw 7, and 50% is special-cased.

    A chance of exactly 0.5 starts the meter at 0.0 rather than at the
    chance (Pokemon.js:696-700), which moves its first firing from throw
    1 to throw 2.  Pre-guard 438a5ef: `_meter_can_fire` does not exist.
    """
    fn = _extract_meter_can_fire()
    assert fn(0.125, 6) is False
    assert fn(0.125, 7) is True
    assert fn(0.5, 1) is False       # the c == 0.5 special case
    assert fn(0.5, 2) is True
    # Without the special case the meter would start at 0.5 and fire on
    # the first throw; this is the line that pins it.
    assert fn(0.4, 1) is False and fn(0.6, 1) is True


def test_meter_can_fire_matches_engine_meter():
    """Oracle parity against gopvpsim.battle._apply_move_buffs.

    The bound is a model of the engine's deterministic buff meter, so
    for every chance it must agree with the engine on which throw first
    fires -- including the 0.5 special case and the float-drift schedule
    (0.1 procs on use 10, not 9).
    """
    fn = _extract_meter_can_fire()
    for chance in (0.125, 0.1, 0.2, 0.3, 0.5, 0.75):
        first = _engine_first_fire(chance, 12)
        assert first is not None, chance     # non-trivial comparison
        for n in range(0, 13):
            assert fn(chance, n) is (n >= first), (chance, n, first)
