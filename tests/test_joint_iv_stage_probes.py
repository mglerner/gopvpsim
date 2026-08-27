"""Stage-probe guards in ``scripts/joint_iv_breakpoints.py`` (f47e87f).

Two guards ship in that commit, and neither had a test:

1. **Grid-condition probes.** The stage probe used to call
   ``simulate(tp, lp, log=True)`` -- i.e. the engine default
   ``bait_with_cheapest`` -- while every grid the pages are built from
   runs ``pvpoke_dp`` on both seats (``deep_dive_lib/robustness.py``
   ``opp_plane``).  Under the default policy a NS+IW Thievul never banks
   to 45 energy, so the probe declared Icy Wind "never thrown" while the
   grids throw it in ~70-85% of fights (2026-08-24 mirror review,
   blocker 1).  The probe now passes ``charged_policy_0`` /
   ``charged_policy_1`` = ``pvpoke_dp``, and the
   ``stage_probe_engine_default_policy`` flag pins the OLD policy for the
   shipped ``thievul_lickilicky`` / ``thievul_lickitung`` anchors.  That
   flag is an ABSENCE pin (the kwargs must not be passed), so it carries
   a positive control: the same config with the flag off must show the
   kwargs, or the absence assertion would be vacuous.

2. **``debuff_thrown_only_shielded``.** A third honest outcome for the
   stage check: the debuff move DOES fly, but no unshielded
   charged-slot-1 hit lands in any candidate fight (the DP throws Icy
   Wind only as shield bait), so the unshielded damage ladder has no
   observable instance.  The branch only matters WITH the policy fix:
   under grid conditions the throw count is nonzero while every hit is
   shielded, and without the branch that state falls through to
   ``ABORT: no stage probe observed the Icy Wind debuff`` (reproduced
   at HEAD by removing only the item-4 branch).

Pre-fix values, observed by running this file against efd93ba:

* every ``simulate`` call in the run carried ``{'log': True}`` only --
  ``charged_policy_0`` / ``charged_policy_1`` were never passed;
* the all-shielded canned fight did NOT abort there: under the old
  engine-default policy the probes never funded Icy Wind at all, so
  main() exited 0 recording ``{"debuff_unreachable": true, ...,
  "candidates_tried": 6}`` and the guard assertion fails with
  ``KeyError: 'debuff_thrown_only_shielded'``.

The canned fights leave the engine alone and rewrite only the probe
fights' TIMELINE (the branch reads ``bs_hits`` and the throw count out of
it), so the sim_check probes that run first -- which parse only FAST-move
lines -- keep their real numbers and their assertions stay live.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / 'scripts'
_PAIRS = _ROOT / 'pairs'

sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT / 'src'))

# Each test runs the real main() end to end (~1.6-3.4s a piece, ~10s
# for the file).  Deliberately NOT module-marked slow: these byte-pin
# the shipped thievul anchor pages, so they should run in the
# verify_tests.py ship gate (-m "not slow"); pyproject defines slow as
# ">~10s" per test.  Only the vintage-exposed end-to-end mirror test
# below carries the slow mark.

# battle.py's timeline emits a genuine U+2192 ("Thievul uses Icy Wind
# -> 38 dmg"); spelled as an escape so this file stays ASCII.
_ARROW = '\u2192'
_IW_HIT = 'Icy Wind ' + _ARROW

# The cross-arm Thievul pair: same species on both seats (so the stage
# probe takes the seat-ambiguous path and counts the focal's throws from
# the opponent's post-fight attack stage), IW+PR on the opponent seat so
# no chance self-buff can move that stage.  At HEAD its probe OBSERVES
# the ladder, which is what makes the canned fights below meaningful.
_CROSS_ARM = _PAIRS / 'thievul__vs__thievul_iw_pr.toml'
# The true IW+PR mirror: the real fight that produced the new key.
_IWPR_MIRROR = _PAIRS / 'thievul_iw_pr__vs__thievul_iw_pr.toml'
# The shipped anchor page that pins the old probe policy.
_SHIPPED = _PAIRS / 'thievul_lickilicky.toml'

_POLICY_KWARGS = ('charged_policy_0', 'charged_policy_1')


def _load():
    """A FRESH ``joint_iv_breakpoints`` module object.

    Each test swaps the module's ``simulate`` binding, so tests get
    their own module rather than sharing one mutated global.
    """
    spec = importlib.util.spec_from_file_location(
        'joint_iv_breakpoints_under_test',
        _SCRIPTS / 'joint_iv_breakpoints.py')
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_shipped_anchor_configs_pass_key_validation():
    """Every ``[breakpoints]`` key the shipped thievul anchors set is
    declared in ``_BP_KNOWN``.

    Pre-fix observed value: ``stage_probe_engine_default_policy`` was
    READ at the probe (f47e87f) but never added to ``_BP_KNOWN``, so
    both shipped anchor pages died at startup with ``ABORT:
    [breakpoints] unknown keys ['stage_probe_engine_default_policy']``
    and could not be rebuilt at all (found by the 2026-08-27
    adversarial test review).
    """
    mod = _load()
    for pair_path in (_SHIPPED, _PAIRS / 'thievul_lickitung.toml'):
        bp_cfg = mod.load_pair(pair_path).section('breakpoints')
        unknown = set(bp_cfg) - mod._BP_KNOWN
        assert not unknown, (pair_path.name, sorted(unknown))


def _n_presim_calls(mod, pair_path):
    """How many ``simulate`` calls happen before the candidate loop.

    Same expression main() uses for its sim_check probe list: an
    explicit ``[breakpoints.sim_probes]`` table, else one probe per
    focal arm.
    """
    cfg = mod.load_pair(pair_path)
    bp_cfg = cfg.section('breakpoints')
    n = len(bp_cfg.get('sim_probes') or mod.focal_arms(cfg))
    assert n >= 1, 'no sim_check probes: the call-index split is bogus'
    return n


class _Calls:
    """Recorded ``simulate`` kwargs, in call order."""

    def __init__(self):
        self.kwargs = []


def _install_spy(mod, transform=None, n_pre=0):
    """Delegate to the real ``simulate``, recording kwargs.

    ``transform(i, timeline) -> timeline`` rewrites the timeline of
    candidate-loop call ``i`` (0-based within the loop); earlier calls
    are passed through untouched.
    """
    real = mod.simulate
    rec = _Calls()

    def spy(tp, lp, **kwargs):
        res = real(tp, lp, **kwargs)
        idx = len(rec.kwargs)
        rec.kwargs.append(dict(kwargs))
        if transform is not None and idx >= n_pre:
            res.timeline = transform(idx - n_pre, list(res.timeline))
        return res

    mod.simulate = spy
    return rec


def _run(mod, pair_path, out_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['joint_iv_breakpoints.py',
                                      str(pair_path), '--out', str(out_path)])
    mod.main()


def _shield(line):
    """Turn an unshielded Icy Wind hit into a shielded one."""
    if _IW_HIT not in line or 'SHIELDED' in line:
        return line
    return line.split(_ARROW)[0] + _ARROW + ' SHIELDED (1 dmg)'


def _icy_wind_ladder_vs_rank1(mod):
    """Closed-form Icy Wind damage by attack stage, rank-1 vs rank-1.

    That is candidate 0's fight for a Thievul-vs-Thievul pair (the ``{}``
    candidate: both seats rank-1, 0 shields), so ``[0]`` is the value an
    unshielded hit lands for while the ladder has not moved.
    """
    rows = mod.spread_table('Thievul', 'great', False)['rows']
    _fast, charged = mod.get_moves()
    iw = charged['ICY_WIND']
    species = {p['speciesName']: p
               for p in mod.load_gamemaster()['pokemon']}['Thievul']
    types = mod.parse_types(species)
    return {st: mod.damage(iw['power'],
                           rows[0]['atk'] * mod._stat_stage_mult(st),
                           rows[0]['def_'], iw['type'], types, types)
            for st in mod.FULL_STAGES}


def _stage_check(out_path):
    ver = json.loads(Path(out_path).read_text())['verification']
    return ver['icy_wind_stage_check']


# --------------------------------------------------------------- item 3

def test_stage_probe_runs_under_grid_conditions(tmp_path, monkeypatch):
    """Every candidate probe fight is simulated with pvpoke_dp on BOTH
    seats -- the conditions the grids run under.

    Pre-f47e87f the candidate loop called ``simulate(tp, lp, log=True)``
    and this assertion fails with ``charged_policy_0`` absent.
    """
    mod = _load()
    rec = _install_spy(mod)
    _run(mod, _CROSS_ARM, tmp_path / 'bp.json', monkeypatch)

    probe_calls = rec.kwargs[_n_presim_calls(mod, _CROSS_ARM):]
    assert probe_calls, ('the candidate loop never simulated anything; the '
                         'policy pin would be vacuous')
    for kwargs in probe_calls:
        for name in _POLICY_KWARGS:
            # Pre-fix the candidate calls carried {'log': True} only.
            assert name in kwargs, (name, sorted(kwargs))
            assert kwargs[name] is mod.pvpoke_dp, (name, kwargs[name])


def test_engine_default_policy_flag_pins_the_shipped_probe(tmp_path,
                                                           monkeypatch):
    """``stage_probe_engine_default_policy = true`` keeps the shipped
    thievul_lickilicky probe on the engine default.

    Absence pin (no policy kwargs anywhere in the run) plus a positive
    control: the same config with the flag off DOES pass pvpoke_dp, so a
    probe that stopped honoring the flag cannot pass both halves.  The
    stage-check payload is pinned too -- it is the number the shipped
    page renders.
    """
    out = tmp_path / 'shipped.json'
    mod = _load()
    rec = _install_spy(mod)
    _run(mod, _SHIPPED, out, monkeypatch)

    assert rec.kwargs, 'nothing was simulated'
    for kwargs in rec.kwargs:
        for name in _POLICY_KWARGS:
            assert name not in kwargs, (
                'the pinned probe was re-simulated under grid conditions; '
                'the shipped page is no longer byte-stable')

    check = _stage_check(out)
    assert check['sim_body_slam_damages_in_order'] == [37, 30]
    assert check['closed_form_body_slam_by_stage'] == {
        '0': 37, '-1': 30, '-2': 25, '-3': 22, '-4': 19}
    assert check['icy_winds_thrown'] == 2
    assert check['all_observed_in_closed_form_set']

    # Positive control: flip the flag off, same everything else.
    body = _SHIPPED.read_text()
    flag_on = 'stage_probe_engine_default_policy = true'
    assert flag_on in body, 'the shipped anchor no longer sets the flag'
    off = tmp_path / 'flag_off.toml'
    off.write_text(body.replace(
        flag_on, 'stage_probe_engine_default_policy = false'))

    mod2 = _load()
    rec2 = _install_spy(mod2)
    _run(mod2, off, tmp_path / 'flag_off.json', monkeypatch)
    with_policy = [kwargs for kwargs in rec2.kwargs
                   if all(name in kwargs for name in _POLICY_KWARGS)]
    assert with_policy, (
        'with the flag off the probe still did not use grid conditions, so '
        'the absence assertion above proves nothing')
    for kwargs in with_policy:
        for name in _POLICY_KWARGS:
            assert kwargs[name] is mod2.pvpoke_dp, (name, kwargs[name])


# --------------------------------------------------------------- item 4

def test_debuff_thrown_but_every_slot1_hit_shielded_records_the_key(
        tmp_path, monkeypatch):
    """Canned fights: the debuff flies, every slot-1 hit is shielded.

    Observed at efd93ba: no abort -- the old default-policy probes
    never threw Icy Wind, so the run recorded ``debuff_unreachable``
    and this test fails with ``KeyError:
    'debuff_thrown_only_shielded'``.  (The ``ABORT: no stage probe
    observed ...`` fall-through is the item-4-branch-only
    counterfactual: reproducible at HEAD by deleting just that
    branch.)
    """
    mod = _load()
    n_pre = _n_presim_calls(mod, _CROSS_ARM)

    def only_shielded(_i, timeline):
        return [_shield(line) for line in timeline]

    rec = _install_spy(mod, transform=only_shielded, n_pre=n_pre)
    out = tmp_path / 'bp.json'
    _run(mod, _CROSS_ARM, out, monkeypatch)

    assert len(rec.kwargs) > n_pre, 'no candidate fight ran'
    check = _stage_check(out)
    assert check['debuff_thrown_only_shielded'] is True
    assert check['candidates_tried'] >= 6  # floor, not == (scan policy)
    assert 'no unshielded Icy Wind hit landed' in check['note']
    assert 'still applies through shields' in check['note']
    # The recorded finding must not masquerade as an observed ladder.
    assert 'sim_body_slam_damages_in_order' not in check
    assert 'debuff_unreachable' not in check


def test_unshielded_stage0_only_hit_still_aborts(tmp_path, monkeypatch):
    """Same canned fights plus ONE unshielded slot-1 hit at stage 0.

    The new branch must not swallow this: an unshielded hit landed, so
    the ladder was testable and simply was not exercised -- an operator
    fixes it with ``[breakpoints] stage_probe``.  Differs from the test
    above only by the injected line.
    """
    mod = _load()
    n_pre = _n_presim_calls(mod, _CROSS_ARM)
    ladder = _icy_wind_ladder_vs_rank1(mod)
    assert len(set(ladder.values())) > 1, (
        'the ladder is flat, so a stage-0 hit would count as observed and '
        'this test would not reach the abort it is checking')
    stage0 = ladder[0]

    def stage0_hit_in_candidate_0(i, timeline):
        timeline = [_shield(line) for line in timeline]
        if i == 0:
            timeline.append('T 99: Thievul uses Icy Wind %s %d dmg'
                            % (_ARROW, stage0))
        return timeline

    _install_spy(mod, transform=stage0_hit_in_candidate_0, n_pre=n_pre)
    with pytest.raises(SystemExit) as excinfo:
        _run(mod, _CROSS_ARM, tmp_path / 'bp.json', monkeypatch)
    assert 'no stage probe observed the Icy Wind debuff' in str(excinfo.value)


@pytest.mark.slow
def test_iwpr_mirror_records_thrown_only_shielded_end_to_end(tmp_path,
                                                             monkeypatch):
    """The real fight the branch was written for, no canning.

    The IW+PR mirror's DP throws Icy Wind only as shield bait, so the
    unshielded ladder has no instance under grid conditions.  A failure
    here means the engine or the gamemaster moved and this pair now
    behaves differently -- check the shipped page before "fixing" it.
    """
    mod = _load()
    out = tmp_path / 'bp.json'
    _run(mod, _IWPR_MIRROR, out, monkeypatch)
    check = _stage_check(out)
    assert check['debuff_thrown_only_shielded'] is True
    assert check['candidates_tried'] >= 6  # floor, not == (scan policy)
