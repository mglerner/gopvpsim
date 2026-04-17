"""
Regression tests for ``aggregate_flips_by_anchor`` in
``scripts/deep_dive_analysis.py``. Vectorised with numpy in S8a (commit
TODO) after profiling showed this function was 86% of narrative compute
time — not the probe/losses path the original S8a plan called out.
Tests pin the observable output against a frozen pure-Python oracle.
"""
from __future__ import annotations

import importlib.util
import random
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = REPO_ROOT / "scripts" / "deep_dive_analysis.py"

_spec = importlib.util.spec_from_file_location("deep_dive_analysis", ANALYSIS_PATH)
analysis = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(analysis)


@dataclass
class _FakeAnchor:
    """Minimal ResolvedAnchor shim for tests — only the attributes the
    aggregator reads are implemented."""
    name: str
    opponent: str
    target_stat: str  # 'atk' | 'def'
    threshold_value: float
    strict: bool = False

    def passes(self, atk: float, def_: float) -> bool:
        v = atk if self.target_stat == 'atk' else def_
        return v > self.threshold_value if self.strict else v >= self.threshold_value


def _reference_aggregate(scores_flat, nIvs, nS, nO,
                         resolved_anchors, data_obj, scenarios, opponents,
                         win_threshold=500,
                         pass_winrate_min=0.75, fail_winrate_max=0.25):
    """Pre-S8a pure-Python implementation, frozen as the oracle."""
    opp_idx_by_name = {}
    for oi, name in enumerate(opponents):
        opp_idx_by_name[name] = oi
        opp_idx_by_name[name.lower()] = oi
    records = []
    for anchor in resolved_anchors:
        if not anchor.opponent:
            continue
        oi = opp_idx_by_name.get(anchor.opponent)
        if oi is None:
            oi = opp_idx_by_name.get(anchor.opponent.lower())
        if oi is None:
            continue
        passing, failing = [], []
        for iv in range(nIvs):
            atk = data_obj['ivAtk'][iv]
            def_ = data_obj['ivDef'][iv]
            if anchor.passes(atk, def_):
                passing.append(iv)
            else:
                failing.append(iv)
        if not passing or not failing:
            continue
        flipped_scenarios = []
        for si in range(nS):
            pw = sum(1 for iv in passing
                     if scores_flat[iv*nS*nO+si*nO+oi] >= win_threshold) / len(passing)
            fw = sum(1 for iv in failing
                     if scores_flat[iv*nS*nO+si*nO+oi] >= win_threshold) / len(failing)
            if pw >= pass_winrate_min and fw <= fail_winrate_max:
                flipped_scenarios.append(scenarios[si])
        if flipped_scenarios:
            records.append({
                'anchor': anchor, 'opponent': anchor.opponent,
                'scenarios': flipped_scenarios, 'direction': 'gain',
                'hp_threshold': None, 'passing_ivs': list(passing),
            })
            continue
        if anchor.target_stat == 'def' and len(passing) > 1:
            hp_vals = data_obj.get('ivHp', [])
            if hp_vals:
                pass_hps = sorted({hp_vals[iv] for iv in passing})
                best_hp, best_scenarios = None, []
                for hp_floor in reversed(pass_hps):
                    sub_pass = [iv for iv in passing if hp_vals[iv] >= hp_floor]
                    sub_fail_extra = [iv for iv in passing if hp_vals[iv] < hp_floor]
                    sub_fail = failing + sub_fail_extra
                    if not sub_pass or not sub_fail:
                        continue
                    hp_flipped = []
                    for si in range(nS):
                        pw = sum(1 for iv in sub_pass
                                 if scores_flat[iv*nS*nO+si*nO+oi] >= win_threshold
                                 ) / len(sub_pass)
                        fw = sum(1 for iv in sub_fail
                                 if scores_flat[iv*nS*nO+si*nO+oi] >= win_threshold
                                 ) / len(sub_fail)
                        if pw >= pass_winrate_min and fw <= fail_winrate_max:
                            hp_flipped.append(scenarios[si])
                    if hp_flipped:
                        best_hp = hp_floor
                        best_scenarios = hp_flipped
                    else:
                        if best_hp is not None:
                            break
                if best_hp is not None and best_scenarios:
                    records.append({
                        'anchor': anchor, 'opponent': anchor.opponent,
                        'scenarios': best_scenarios, 'direction': 'gain',
                        'hp_threshold': best_hp,
                        'passing_ivs': [iv for iv in passing if hp_vals[iv] >= best_hp],
                    })
    return records


def _make_inputs(seed, nIvs=256, nS=9, nO=5):
    rng = random.Random(seed)
    scenarios = [[s0, s1] for s0 in range(3) for s1 in range(3)][:nS]
    opponents = [f'OPP_{i}' for i in range(nO)]
    data_obj = {
        'ivAtk': [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)],
        'ivDef': [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)],
        'ivHp': [rng.randint(100, 200) for _ in range(nIvs)],
    }
    scores_flat = [rng.randint(0, 1000) for _ in range(nIvs*nS*nO)]
    return data_obj, scores_flat, scenarios, opponents


def _recs_to_comparable(recs):
    """Normalise for comparison: sort passing_ivs, drop anchor object ref."""
    out = []
    for r in recs:
        out.append({
            'anchor_name': r['anchor'].name,
            'opponent': r['opponent'],
            'scenarios': [tuple(s) for s in r['scenarios']],
            'direction': r['direction'],
            'hp_threshold': r['hp_threshold'],
            'passing_ivs': sorted(r['passing_ivs']),
        })
    return sorted(out, key=lambda r: (r['anchor_name'], r['opponent']))


def test_matches_reference_random_inputs():
    anchors = [
        _FakeAnchor('def_mid', 'OPP_1', 'def', 130.0),
        _FakeAnchor('def_high', 'OPP_2', 'def', 145.0),
        _FakeAnchor('atk_mid', 'OPP_0', 'atk', 130.0),
        _FakeAnchor('atk_high_strict', 'OPP_3', 'atk', 140.0, strict=True),
        _FakeAnchor('def_very_high', 'OPP_4', 'def', 148.0),
        _FakeAnchor('unknown_opp', 'NOT_IN_POOL', 'def', 130.0),
    ]
    for seed in range(4):
        data_obj, scores_flat, scenarios, opponents = _make_inputs(seed)
        nIvs = len(data_obj['ivAtk'])
        nS = len(scenarios)
        nO = len(opponents)
        ref = _reference_aggregate(
            scores_flat, nIvs, nS, nO, anchors, data_obj, scenarios, opponents)
        got = analysis.aggregate_flips_by_anchor(
            scores_flat, nIvs, nS, nO, anchors, data_obj, scenarios, opponents)
        assert _recs_to_comparable(ref) == _recs_to_comparable(got), (
            f'seed={seed}: ref={_recs_to_comparable(ref)} got={_recs_to_comparable(got)}')


def test_anchor_with_no_opponent_is_skipped():
    data_obj, scores_flat, scenarios, opponents = _make_inputs(0)
    anchors = [_FakeAnchor('noop', '', 'def', 130.0)]
    got = analysis.aggregate_flips_by_anchor(
        scores_flat, len(data_obj['ivAtk']), len(scenarios), len(opponents),
        anchors, data_obj, scenarios, opponents)
    assert got == []


def test_unknown_opponent_is_skipped():
    data_obj, scores_flat, scenarios, opponents = _make_inputs(0)
    anchors = [_FakeAnchor('missing', 'NO_SUCH_OPP', 'def', 130.0)]
    got = analysis.aggregate_flips_by_anchor(
        scores_flat, len(data_obj['ivAtk']), len(scenarios), len(opponents),
        anchors, data_obj, scenarios, opponents)
    assert got == []


def test_case_insensitive_opponent_lookup():
    data_obj, scores_flat, scenarios, opponents = _make_inputs(0)
    # opponents are 'OPP_0' etc., anchor uses lowercase
    anchors = [_FakeAnchor('a', 'opp_1', 'def', 130.0)]
    ref = _reference_aggregate(
        scores_flat, len(data_obj['ivAtk']), len(scenarios), len(opponents),
        anchors, data_obj, scenarios, opponents)
    got = analysis.aggregate_flips_by_anchor(
        scores_flat, len(data_obj['ivAtk']), len(scenarios), len(opponents),
        anchors, data_obj, scenarios, opponents)
    assert _recs_to_comparable(ref) == _recs_to_comparable(got)


def test_debug_stats_populated():
    data_obj, scores_flat, scenarios, opponents = _make_inputs(0)
    anchors = [
        _FakeAnchor('ok', 'OPP_1', 'def', 130.0),
        _FakeAnchor('missing_opp', 'GHOST', 'def', 130.0),
        _FakeAnchor('no_opp', '', 'def', 130.0),
    ]
    stats = {}
    analysis.aggregate_flips_by_anchor(
        scores_flat, len(data_obj['ivAtk']), len(scenarios), len(opponents),
        anchors, data_obj, scenarios, opponents, debug_stats=stats)
    assert stats.get('considered') == 3
    assert stats.get('no_opponent') == 1
    assert stats.get('unknown_opponent') == 1
