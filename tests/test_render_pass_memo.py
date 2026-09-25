"""The per-pass render memo (deep_dive_lib/render.py, 2026-09-25 R2/R4).

One level pass renders moveset 0's narrative and then its analysis, and
both used to call ``aggregate_flips_by_anchor`` with identical inputs for
every opp-IV mode -- half of all aggregator calls in a bake were exact
duplicates. ``deep_dive._render_level_body`` now hands both a fresh
``pass_memo`` dict per pass and the aggregator runs once per mode.

The memo is a perf refactor, so the rendered artifact must not change
(proved by ``scripts/replay_render_diff.py`` on five real blobs). What this
file pins is the memo's own contract, which the byte-diff can only catch
on blobs that happen to exercise it:

* same inputs -> the aggregator runs ONCE, and each caller gets records
  equal to a direct call;
* every caller gets its OWN record dicts and lists (callers set
  rec['bait_modes'] / rec['energy_modes'] and merge them across modes, so
  a shared record would leak one consumer's modes into the other), while
  rec['anchor'] stays the very same anchor object;
* different inputs (another scores list, other scenarios/opponents) are a
  miss, never a stale hit;
* debug_stats is filled on a hit exactly as a direct call fills it;
* pass_memo=None is the direct call, every time.

R4 routes ``find_matchup_boundaries`` through the same memo: it ran three
times per (mode, sweep) per pass (narrative, analysis census, analysis
boundary list). Its entries are keyed per sweep, and mutating a stat list
in place (a new ivDef object on data_obj) is a miss.
"""
import random
from dataclasses import dataclass

from tests.conftest import load_deep_dive

load_deep_dive()                                  # puts scripts/ on sys.path
from deep_dive_lib import render                  # noqa: E402


@dataclass
class _Anchor:
    name: str
    opponent: str
    target_stat: str
    threshold_value: float
    strict: bool = False


def _inputs(seed=0, nIvs=64, nS=3, nO=2):
    rng = random.Random(seed)
    scen = [(0, 0), (1, 1), (2, 2)][:nS]
    opps = [f'OPP_{i}' for i in range(nO)]
    atk = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    dfn = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    hp = [rng.randint(100, 200) for _ in range(nIvs)]
    scores = []
    for iv in range(nIvs):
        for _si in range(nS):
            for oi in range(nO):
                win = (atk[iv] if oi == 0 else dfn[iv]) >= 125
                if rng.random() < 0.05:
                    win = not win
                scores.append(700 if win else 300)
    data_obj = {'ivAtk': atk, 'ivDef': dfn, 'ivHp': hp}
    anchors = [_Anchor('a', 'OPP_0', 'atk', 125.0),
               _Anchor('d', 'OPP_1', 'def', 125.0),
               _Anchor('ghost', 'NOPE', 'def', 125.0)]
    return scores, nIvs, nS, nO, anchors, data_obj, scen, opps


def _counting(monkeypatch):
    calls = []
    real = render._aggregate_flips_by_anchor

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(render, '_aggregate_flips_by_anchor', spy)
    return calls, real


def test_same_inputs_compute_once_and_match_direct(monkeypatch):
    calls, real = _counting(monkeypatch)
    args = _inputs()
    direct = real(*args)
    assert len(direct) == 2, 'fixture must emit records (anti-vacuity)'
    memo = {}
    first = render._memo_aggregate_flips(memo, ('agg', 0, 'pvpoke'), *args)
    second = render._memo_aggregate_flips(
        memo, ('agg', 0, 'pvpoke'), *args[:6],
        [list(s) for s in args[6]], list(args[7]))   # rebuilt, equal lists
    assert len(calls) == 1
    assert first == direct and second == direct


def test_each_caller_gets_independent_records(monkeypatch):
    _counting(monkeypatch)
    args = _inputs()
    memo = {}
    first = render._memo_aggregate_flips(memo, 'k', *args)
    for rec in first:
        rec['bait_modes'] = {'bait'}
        rec['scenarios'].append((9, 9))
        rec['passing_ivs'].append(-1)
    second = render._memo_aggregate_flips(memo, 'k', *args)
    for a, b in zip(first, second):
        assert 'bait_modes' not in b
        assert (9, 9) not in b['scenarios'] and -1 not in b['passing_ivs']
        assert a is not b and a['anchor'] is b['anchor']


def test_different_inputs_miss(monkeypatch):
    calls, _ = _counting(monkeypatch)
    args = list(_inputs())
    memo = {}
    render._memo_aggregate_flips(memo, 'k', *args)
    other_scores = list(args[0])                 # equal VALUES, new object
    render._memo_aggregate_flips(memo, 'k', other_scores, *args[1:])
    assert len(calls) == 2
    fewer_opps = args[:7] + [['OPP_0', 'OPP_X']]
    render._memo_aggregate_flips(memo, 'k', other_scores, *fewer_opps[1:])
    assert len(calls) == 3


def test_debug_stats_on_hit_match_direct(monkeypatch):
    _, real = _counting(monkeypatch)
    args = _inputs()
    want = {}
    real(*args, debug_stats=want)
    assert want['unknown_opponent'] == 1 and want['emitted'] == 2
    memo = {}
    render._memo_aggregate_flips(memo, 'k', *args)       # miss, no stats
    got = {}
    render._memo_aggregate_flips(memo, 'k', *args, debug_stats=got)
    assert got == want


def test_no_memo_is_direct(monkeypatch):
    calls, _ = _counting(monkeypatch)
    args = _inputs()
    render._memo_aggregate_flips(None, 'k', *args)
    render._memo_aggregate_flips(None, 'k', *args)
    assert len(calls) == 2


def _counting_mb(monkeypatch):
    calls = []
    real = render._find_matchup_boundaries

    def spy(*a, **k):
        calls.append(k.get('sweep_stat'))
        return real(*a, **k)
    monkeypatch.setattr(render, '_find_matchup_boundaries', spy)
    return calls, real


def _mb_args():
    scores, nIvs, nS, nO, _anchors, data_obj, scen, opps = _inputs()
    return scores, nIvs, nS, nO, data_obj, scen, opps


def test_boundaries_computed_once_per_sweep(monkeypatch):
    calls, real = _counting_mb(monkeypatch)
    args = _mb_args()
    memo = {}
    for sweep in ('def', 'atk', 'def', 'atk', 'def', 'atk'):
        got = render._memo_matchup_boundaries(
            memo, ('mb', 0, 'pvpoke', sweep), *args, sweep)
        want = real(*args, sweep_stat=sweep)
        assert want, f'fixture must emit {sweep} boundaries (anti-vacuity)'
        assert got == want
    assert calls == ['def', 'atk']


def test_boundary_copies_are_independent(monkeypatch):
    _counting_mb(monkeypatch)
    args = _mb_args()
    memo = {}
    first = render._memo_matchup_boundaries(memo, 'k', *args, 'def')
    for mb in first:
        mb['bait_modes'] = {'bait'}
        mb['scenarios'].append((9, 9))
    second = render._memo_matchup_boundaries(memo, 'k', *args, 'def')
    for a, b in zip(first, second):
        assert a is not b and 'bait_modes' not in b
        assert (9, 9) not in b['scenarios']


def test_boundary_memo_misses_on_new_inputs(monkeypatch):
    calls, _ = _counting_mb(monkeypatch)
    scores, nIvs, nS, nO, data_obj, scen, opps = _mb_args()
    memo = {}
    render._memo_matchup_boundaries(
        memo, 'k', scores, nIvs, nS, nO, data_obj, scen, opps, 'def')
    data_obj['ivDef'] = list(data_obj['ivDef'])          # new list object
    render._memo_matchup_boundaries(
        memo, 'k', scores, nIvs, nS, nO, data_obj, scen, opps, 'def')
    render._memo_matchup_boundaries(                     # same key, atk
        memo, 'k', scores, nIvs, nS, nO, data_obj, scen, opps, 'atk')
    assert calls == ['def', 'def', 'atk']
    render._memo_matchup_boundaries(
        None, 'k', scores, nIvs, nS, nO, data_obj, scen, opps, 'atk')
    assert calls == ['def', 'def', 'atk', 'atk']
