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
    """Pre-S8a pure-Python implementation, frozen as the oracle.

    TIE SEMANTICS (decided by Michael, 2026-08-10): a score of exactly
    ``win_threshold`` (500) is a TIE, not a win — ``> win_threshold``,
    matching ``battle.is_win``/PvPoke and the sibling probe/losses
    paths. History: pre-S8a production used ``>=``; the S8a
    vectorisation (8a7fdc7) silently corrected it to ``>``, and this
    oracle — transcribed from the pre-S8a code — carried the old
    ``>=`` until 2026-08-10, masked because the fixture emitted only
    700/300. The fixture now plants exact-500 cells (losses vs OPP_0)
    and test_tie_score_is_not_a_win pins the boundary directly, so a
    production regression to ``>=`` fails this file.
    """
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
                     if scores_flat[iv*nS*nO+si*nO+oi] > win_threshold) / len(passing)
            fw = sum(1 for iv in failing
                     if scores_flat[iv*nS*nO+si*nO+oi] > win_threshold) / len(failing)
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
                                 if scores_flat[iv*nS*nO+si*nO+oi] > win_threshold
                                 ) / len(sub_pass)
                        fw = sum(1 for iv in sub_fail
                                 if scores_flat[iv*nS*nO+si*nO+oi] > win_threshold
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


# Per-opponent win rules, keyed to the anchor thresholds used below so
# the anchors' partitions actually separate wins from losses:
#   (stat, cut, hp_floor). An IV wins a cell iff it clears the cut — and,
# when hp_floor is not None, also clears the HP floor, which is what
# drives the aggregator's phase-2 (HP co-condition) path.
# Scenario index selects the variant: si % 3 == 0 -> plain cut,
# 1 -> hp-coupled, 2 -> unrelated rule (a deliberate no-flip control).
# A rule that carries its own hp_floor is hp-coupled in variants 0 and 1
# alike, which is how OPP_2 keeps phase 1 silent and forces phase 2.
_OPP_RULES = {
    0: ('atk', 130.0, None),   # matches anchor atk_mid -> phase 1 fires
    1: ('def', 130.0, None),   # matches anchor def_mid -> phase 1 fires
    2: ('def', 145.0, 150),    # def_high, HP-coupled in every scenario
    3: ('atk', 140.0, None),   # matches anchor atk_high_strict
    4: ('def', 148.0, None),   # def_very_high: tiny passing group
}


def _make_inputs(seed, nIvs=256, nS=9, nO=5):
    """Random inputs whose SCORES are coupled to the anchored stats.

    The pre-2026-08-09 version drew scores as i.i.d. ``randint(0, 1000)``,
    independent of ivAtk/ivDef/ivHp. Both winrates then sat at ~0.50 and
    the ``pw >= 0.75 and fw <= 0.25`` conjunction never fired: the oracle
    produced 0 records across all 4 seeds (180 phase-1 and 3384 HP-
    refinement gate evaluations, 0 hits), so the parity comparisons were
    empty-vs-empty and 4 of 5 tests passed with the production function
    gutted.

    Scores are now generated the way tests/test_matchup_boundaries.py does
    it (win depends on the swept stat, optionally co-conditioned on HP,
    plus ~6% noise), keyed per opponent to the anchor that names it.
    """
    rng = random.Random(seed)
    scenarios = [[s0, s1] for s0 in range(3) for s1 in range(3)][:nS]
    opponents = [f'OPP_{i}' for i in range(nO)]
    iv_atk = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    iv_def = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    # Plant one stat EXACTLY on the strict anchor's threshold. `strict`
    # selects `>` over `>=`, so it is observable only when some IV sits on
    # the boundary; a continuous 2-decimal draw hits 140.00 with p ~ 1/5000
    # and never did across the seeds this file runs. Without this, dropping
    # the strict branch in production passes every test in this file.
    iv_atk[0] = 140.0
    iv_hp = [rng.randint(100, 200) for _ in range(nIvs)]
    data_obj = {'ivAtk': iv_atk, 'ivDef': iv_def, 'ivHp': iv_hp}
    by_stat = {'atk': iv_atk, 'def': iv_def}
    scores_flat = []
    for iv in range(nIvs):
        for si in range(nS):
            for oi in range(nO):
                stat, cut, hp_floor = _OPP_RULES[oi % len(_OPP_RULES)]
                variant = si % 3
                if variant == 2:
                    # No-flip control: keyed off a stat no anchor cuts on.
                    win = iv_hp[iv] >= 110
                else:
                    win = by_stat[stat][iv] >= cut
                    if hp_floor is not None or variant == 1:
                        win = win and iv_hp[iv] >= (hp_floor or 140)
                if rng.random() < 0.06:   # ~6% noise, as in the sibling
                    win = not win         # boundaries fixture
                # Losses vs OPP_0 are EXACT TIES (500), pinning the
                # tie-is-not-a-win boundary through the parity tests: a
                # production regression to ``>= win_threshold`` turns
                # OPP_0's failing cohort into ~100% "winners" and kills
                # its phase-1 flip, diverging from the oracle.
                loss = 500 if oi == 0 else 300
                scores_flat.append(700 if win else loss)
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
        # Near-miss of OPP_0 on OPP_0's own win rule (atk >= 130), so a
        # production bug that resolved an unknown name to a real opponent
        # (index-0 fallback, prefix match) would emit a record the oracle
        # doesn't. Cf. test_unknown_opponent_is_skipped.
        _FakeAnchor('unknown_opp', 'OPP_0_TYPO', 'atk', 130.0),
    ]
    saw_hp_threshold = False
    for seed in range(4):
        data_obj, scores_flat, scenarios, opponents = _make_inputs(seed)
        nIvs = len(data_obj['ivAtk'])
        nS = len(scenarios)
        nO = len(opponents)
        ref = _reference_aggregate(
            scores_flat, nIvs, nS, nO, anchors, data_obj, scenarios, opponents)
        # Anti-vacuity: [] == [] proves nothing. Measured over seeds 0..19
        # the oracle emits a record for all 5 pool anchors every time.
        assert ref, (
            f'oracle produced no records for seed={seed} — fixture no '
            f'longer exercises the winrate gate, so the parity check '
            f'below is vacuous')
        got = analysis.aggregate_flips_by_anchor(
            scores_flat, nIvs, nS, nO, anchors, data_obj, scenarios, opponents)
        assert _recs_to_comparable(ref) == _recs_to_comparable(got), (
            f'seed={seed}: ref={_recs_to_comparable(ref)} got={_recs_to_comparable(got)}')
        saw_hp_threshold |= any(r['hp_threshold'] is not None for r in ref)
    # The HP co-condition (phase 2) is the harder half of the function;
    # without this the fixture could drift to phase-1-only and still pass.
    assert saw_hp_threshold, 'no seed exercised the HP-refinement path'


def _resolvable_anchor_control(data_obj, scores_flat, scenarios, opponents):
    """The same fixture DOES yield records for a resolvable anchor.

    Without this, `got == []` below is satisfied by any function that
    always returns [] — which is exactly how these two tests used to pass
    with the production implementation gutted.
    """
    analysis._invalidate_np_caches()
    control = analysis.aggregate_flips_by_anchor(
        scores_flat, len(data_obj['ivAtk']), len(scenarios), len(opponents),
        [_FakeAnchor('control', 'OPP_1', 'def', 130.0)],
        data_obj, scenarios, opponents)
    assert control, 'control anchor produced no records — fixture is dead'


def test_anchor_with_no_opponent_is_skipped():
    # Reach note: the empty-opponent guard and the unknown-name guard chain
    # ('' is never in the opponent pool), so removing the former alone still
    # yields []. That guard's *counter* is pinned by
    # test_debug_stats_populated; this test pins the observable output.
    data_obj, scores_flat, scenarios, opponents = _make_inputs(0)
    _resolvable_anchor_control(data_obj, scores_flat, scenarios, opponents)
    anchors = [_FakeAnchor('noop', '', 'def', 130.0)]
    got = analysis.aggregate_flips_by_anchor(
        scores_flat, len(data_obj['ivAtk']), len(scenarios), len(opponents),
        anchors, data_obj, scenarios, opponents)
    assert got == []


def test_unknown_opponent_is_skipped():
    data_obj, scores_flat, scenarios, opponents = _make_inputs(0)
    _resolvable_anchor_control(data_obj, scores_flat, scenarios, opponents)
    # The anchor must be one that WOULD emit if the unknown name resolved to
    # a real opponent, or `got == []` is satisfied for the wrong reason. The
    # old ('NO_SUCH_OPP', def, 130.0) failed this: a production bug falling
    # back to opponent index 0 lands on OPP_0, whose win rule is atk-keyed,
    # so a def anchor found no clean scenario there and the test passed
    # anyway. Name is a near-miss of OPP_0 and the cut is OPP_0's own rule,
    # so both index-0 fallback and fuzzy/prefix matching are caught.
    anchors = [_FakeAnchor('missing', 'OPP_0_TYPO', 'atk', 130.0)]
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
    # Anti-vacuity: a lookup that resolved to nothing would compare
    # [] == [] and pass whether or not the lowercase alias works.
    assert ref, 'oracle produced no records — the lookup is untested'
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


def test_tie_score_is_not_a_win():
    """A score of exactly WIN_RATING (500) is a tie, not a win — decided
    2026-08-10 (matches battle.is_win/PvPoke; see _reference_aggregate's
    docstring for the history). Minimal direct pin, independent of the
    random parity fixture: the passing cohort scores exactly 500
    everywhere, so under tie-is-not-a-win NO scenario can clear the
    pass_winrate_min gate and no record may be emitted; nudging the same
    cells to 501 must emit one (anti-vacuity: proves the gate, not the
    fixture, is what stops the record)."""
    nIvs, nS, nO = 8, 3, 1
    scenarios = [[0, 0], [1, 1], [2, 2]]
    opponents = ['OPP_0']
    data_obj = {
        'ivAtk': [140.0] * 4 + [110.0] * 4,
        'ivDef': [120.0] * 8,
        'ivHp': [150] * 8,
    }
    anchors = [_FakeAnchor('atk_cut', 'OPP_0', 'atk', 130.0)]

    def scores(pass_score):
        flat = []
        for iv in range(nIvs):
            for _si in range(nS):
                flat.append(pass_score if data_obj['ivAtk'][iv] >= 130.0
                            else 300)
        return flat

    tied = analysis.aggregate_flips_by_anchor(
        scores(500), nIvs, nS, nO, anchors, data_obj, scenarios, opponents)
    assert tied == [], (
        f'exact-500 scores counted as wins (>= regression): {tied}')
    won = analysis.aggregate_flips_by_anchor(
        scores(501), nIvs, nS, nO, anchors, data_obj, scenarios, opponents)
    assert won, 'control failed: 501 scores should produce a flip record'
