"""
Regression tests for ``probe_tier_cutoff_flips`` in
``scripts/deep_dive_analysis.py``. The function was vectorised with
numpy in S8a; these tests pin down the observable behavior against a
pure-Python reference so the two implementations stay byte-equivalent
on the outputs the narrative + rendering layers consume.
"""
from __future__ import annotations

import importlib.util
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = REPO_ROOT / "scripts" / "deep_dive_analysis.py"

_spec = importlib.util.spec_from_file_location("deep_dive_analysis", ANALYSIS_PATH)
analysis = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(analysis)


def _reference_probe(data_obj, score_arrays_all, moveset_idx,
                     atk_cut, def_cut, hp_cut,
                     scenarios, opponents,
                     pass_winrate_min=0.75, fail_winrate_max=0.25):
    """Pre-S8a pure-Python implementation, frozen as the oracle."""
    nIvs = data_obj.get('nIvs', 0)
    nS = len(scenarios)
    nO = len(opponents)
    if nIvs == 0 or nO == 0:
        return []
    passing = []
    failing = []
    for iv in range(nIvs):
        meets = True
        if atk_cut > 0 and data_obj['ivAtk'][iv] < atk_cut:
            meets = False
        if def_cut > 0 and data_obj['ivDef'][iv] < def_cut:
            meets = False
        if hp_cut > 0 and data_obj['ivHp'][iv] < hp_cut:
            meets = False
        (passing if meets else failing).append(iv)
    if not passing or not failing:
        return []
    results = []
    all_modes = data_obj.get('oppIvModes', ['pvpoke'])
    for mode in all_modes:
        key = f'{moveset_idx}_{mode}'
        scores_flat = score_arrays_all.get(key, [])
        if not scores_flat:
            continue
        for si, scen in enumerate(scenarios):
            for oi, opp in enumerate(opponents):
                pw = sum(1 for iv in passing
                         if scores_flat[iv * nS * nO + si * nO + oi] > 500
                         ) / len(passing)
                fw = sum(1 for iv in failing
                         if scores_flat[iv * nS * nO + si * nO + oi] > 500
                         ) / len(failing)
                if pw >= pass_winrate_min and fw <= fail_winrate_max:
                    results.append({
                        'opponent': opp,
                        'scenario': scen,
                        'opp_iv_mode': mode,
                        'pass_wr': pw,
                        'fail_wr': fw,
                    })
    return results


# Per-cell win rules: (stat, cut). Each (mode, scenario, opponent) cell
# picks one, and an IV wins that cell iff its stat clears the cut. The
# mixture is deliberate — cuts that line up with a probed tier cutoff make
# the 0.75/0.25 winrate gate fire, cuts that straddle or key off another
# stat make it stay silent, so the oracle emits a partial (not saturated)
# record set.
_WIN_RULES = [
    ('def', 140.0),
    ('def', 145.0),
    ('atk', 130.0),
    ('hp', 130),
    ('def', 120.0),
    ('atk', 125.0),
    ('def', 138.0),
    ('hp', 160),
]


def _make_inputs(seed, nIvs=256, nS=9, nO=5, modes=('pvpoke', 'rank1')):
    """Random inputs whose SCORES are coupled to the IV stats being probed.

    The pre-2026-08-09 version drew scores as i.i.d. ``randint(0, 1000)``,
    independent of ivAtk/ivDef/ivHp. Both winrates then sat at ~0.50 and
    the ``pass_wr >= 0.75 and fail_wr <= 0.25`` conjunction — the entire
    body of the function under test — never fired: the oracle produced 0
    records in 20/20 (seed x cutoff) cases, so every comparison below was
    empty-vs-empty and the file passed with the production function gutted.

    Scores are now generated the way tests/test_matchup_boundaries.py
    does it (``win = ivDef[iv] >= stat_cut`` plus ~6% noise), just with a
    per-cell rule table so atk/def/hp cutoffs all get exercised.
    """
    rng = random.Random(seed)
    scenarios = [[s0, s1] for s0 in range(3) for s1 in range(3)][:nS]
    opponents = [f'OPP_{i}' for i in range(nO)]
    iv_atk = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    iv_def = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    iv_hp = [rng.randint(100, 200) for _ in range(nIvs)]
    data_obj = {
        'nIvs': nIvs,
        'ivAtk': iv_atk,
        'ivDef': iv_def,
        'ivHp': iv_hp,
        'oppIvModes': list(modes),
    }
    by_stat = {'atk': iv_atk, 'def': iv_def, 'hp': iv_hp}
    score_arrays = {}
    for mi, mode in enumerate(modes):
        flat = []
        for iv in range(nIvs):
            for si in range(nS):
                for oi in range(nO):
                    stat, cut = _WIN_RULES[(si * nO + oi + mi) % len(_WIN_RULES)]
                    win = by_stat[stat][iv] >= cut
                    if rng.random() < 0.06:   # ~6% noise, as in the sibling
                        win = not win         # boundaries fixture
                    flat.append(700 if win else 300)
        score_arrays[f'0_{mode}'] = flat
    return data_obj, score_arrays, scenarios, opponents


def _sort_key(r):
    return (r['opp_iv_mode'], tuple(r['scenario']), r['opponent'])


def _equal_result_lists(a, b):
    if len(a) != len(b):
        return False
    a_s = sorted(a, key=_sort_key)
    b_s = sorted(b, key=_sort_key)
    for ra, rb in zip(a_s, b_s):
        if _sort_key(ra) != _sort_key(rb):
            return False
        if abs(ra['pass_wr'] - rb['pass_wr']) > 1e-12:
            return False
        if abs(ra['fail_wr'] - rb['fail_wr']) > 1e-12:
            return False
    return True


def test_matches_reference_random_inputs():
    for seed in range(5):
        data_obj, score_arrays, scenarios, opponents = _make_inputs(seed)
        analysis._invalidate_np_caches()
        for (ac, dc, hc) in [(0.0, 140.0, 130),
                             (130.0, 0.0, 0),
                             (0.0, 145.0, 0),
                             (125.0, 138.0, 140)]:
            ref = _reference_probe(data_obj, score_arrays, 0,
                                   ac, dc, hc, scenarios, opponents)
            # Anti-vacuity: an empty-vs-empty comparison proves nothing.
            # Measured floor over seeds 0..19 x these 4 cuts is 5 records
            # (typical 15-33); a fixture that stops clearing the winrate
            # gate must fail loudly here rather than pass silently.
            assert ref, (
                f'oracle produced no records for seed={seed} '
                f'cut=({ac},{dc},{hc}) — fixture no longer exercises the '
                f'winrate gate, so the parity check below is vacuous')
            got = analysis.probe_tier_cutoff_flips(
                data_obj, score_arrays, 0,
                ac, dc, hc, scenarios, opponents)
            assert _equal_result_lists(ref, got), (
                f'seed={seed} cut=({ac},{dc},{hc}) ref={len(ref)} got={len(got)}')


def _reachable_cut_control(data_obj, score_arrays, scenarios, opponents):
    """The same fixture DOES yield flips at a reachable cut.

    Without this, `got == []` below is satisfied by any function that
    always returns [] — which is exactly how this file used to pass with
    the production implementation gutted.
    """
    analysis._invalidate_np_caches()
    control = analysis.probe_tier_cutoff_flips(
        data_obj, score_arrays, 0,
        0.0, 140.0, 0, scenarios, opponents)
    assert control, 'control cut produced no flips — fixture is dead'


def test_empty_when_no_ivs_meet_cut():
    data_obj, score_arrays, scenarios, opponents = _make_inputs(0)
    _reachable_cut_control(data_obj, score_arrays, scenarios, opponents)
    analysis._invalidate_np_caches()
    # Cut higher than any IV stat -> no passers
    got = analysis.probe_tier_cutoff_flips(
        data_obj, score_arrays, 0,
        0.0, 999.0, 0, scenarios, opponents)
    assert got == []


def test_empty_when_all_ivs_meet_cut():
    data_obj, score_arrays, scenarios, opponents = _make_inputs(0)
    _reachable_cut_control(data_obj, score_arrays, scenarios, opponents)
    analysis._invalidate_np_caches()
    # Cut below any IV stat -> no failers
    got = analysis.probe_tier_cutoff_flips(
        data_obj, score_arrays, 0,
        0.0, 1.0, 0, scenarios, opponents)
    assert got == []


def test_missing_scores_key_skips_mode():
    data_obj, score_arrays, scenarios, opponents = _make_inputs(0)
    # Remove one mode's scores
    del score_arrays['0_rank1']
    analysis._invalidate_np_caches()
    ref = _reference_probe(data_obj, score_arrays, 0,
                           0.0, 140.0, 130, scenarios, opponents)
    assert ref, 'oracle produced no records — comparison would be vacuous'
    got = analysis.probe_tier_cutoff_flips(
        data_obj, score_arrays, 0,
        0.0, 140.0, 130, scenarios, opponents)
    # The surviving mode must still produce results — without this floor
    # the all() below is satisfied by an empty list.
    assert got
    # All returned entries must be from the remaining mode
    assert all(r['opp_iv_mode'] == 'pvpoke' for r in got)
    assert _equal_result_lists(ref, got)


def test_zero_nIvs_returns_empty():
    _reachable_cut_control(*_make_inputs(0))
    data_obj = {'nIvs': 0, 'ivAtk': [], 'ivDef': [], 'ivHp': [],
                'oppIvModes': ['pvpoke']}
    scenarios = [[0, 0]]
    opponents = ['OPP']
    analysis._invalidate_np_caches()
    got = analysis.probe_tier_cutoff_flips(
        data_obj, {}, 0, 0.0, 140.0, 0, scenarios, opponents)
    assert got == []
