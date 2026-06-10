"""Regression tests for find_matchup_boundaries (vectorized 2026-06-10).

The vectorized implementation in deep_dive_analysis.py must return
records identical to the original pure-Python scan loops. The original
is preserved here verbatim as the reference oracle and both are run on
randomized inputs engineered to exercise phase 1 (single-stat
partition), phase 2 (stat + HP co-condition), and the degenerate
no-flip cases.
"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from deep_dive_analysis import find_matchup_boundaries


def _reference_find_matchup_boundaries(scores_flat, nIvs, nS, nO,
                                       data_obj, scenarios, opponents,
                                       sweep_stat='def',
                                       win_threshold=500,
                                       pass_winrate_min=0.75,
                                       fail_winrate_max=0.25,
                                       min_passing=3):
    """The pre-2026-06-10 implementation, verbatim (loops + grouping)."""
    if nIvs == 0 or nO == 0:
        return []

    if sweep_stat == 'atk':
        stat_vals = data_obj['ivAtk']
    else:
        stat_vals = data_obj['ivDef']
    hp_vals = data_obj.get('ivHp', [])
    unique_stats = sorted({stat_vals[iv] for iv in range(nIvs)})

    results = []

    for oi in range(nO):
        opp = opponents[oi]

        for si in range(nS):
            wins = [scores_flat[iv * nS * nO + si * nO + oi] >= win_threshold
                    for iv in range(nIvs)]

            total_wins = sum(1 for w in wins if w)
            if total_wins == 0 or total_wins == nIvs:
                continue

            best_stat = None
            best_hp = None

            for stat_thresh in unique_stats:
                passing = [iv for iv in range(nIvs)
                           if stat_vals[iv] >= stat_thresh]
                failing = [iv for iv in range(nIvs)
                           if stat_vals[iv] < stat_thresh]
                if len(passing) < min_passing or not failing:
                    continue

                pw = sum(1 for iv in passing if wins[iv]) / len(passing)
                fw = sum(1 for iv in failing if wins[iv]) / len(failing)

                if pw >= pass_winrate_min and fw <= fail_winrate_max:
                    best_stat = stat_thresh
                    best_hp = None
                    break

            if best_stat is None and hp_vals:
                for stat_thresh in unique_stats:
                    s_passing = [iv for iv in range(nIvs)
                                 if stat_vals[iv] >= stat_thresh]
                    s_failing = [iv for iv in range(nIvs)
                                 if stat_vals[iv] < stat_thresh]
                    if len(s_passing) < min_passing or not s_failing:
                        continue
                    pw_raw = sum(1 for iv in s_passing if wins[iv])
                    if pw_raw == 0:
                        continue
                    if pw_raw / len(s_passing) < 0.3:
                        continue

                    pass_hps = sorted({hp_vals[iv] for iv in s_passing})
                    found_hp = None
                    for hp_floor in reversed(pass_hps):
                        sub_pass = [iv for iv in s_passing
                                    if hp_vals[iv] >= hp_floor]
                        sub_fail = s_failing + [
                            iv for iv in s_passing
                            if hp_vals[iv] < hp_floor]
                        if len(sub_pass) < min_passing or not sub_fail:
                            continue
                        spw = sum(1 for iv in sub_pass
                                  if wins[iv]) / len(sub_pass)
                        sfw = sum(1 for iv in sub_fail
                                  if wins[iv]) / len(sub_fail)
                        if (spw >= pass_winrate_min
                                and sfw <= fail_winrate_max):
                            found_hp = hp_floor
                        else:
                            if found_hp is not None:
                                break
                    if found_hp is not None:
                        best_stat = stat_thresh
                        best_hp = found_hp
                        break

            if best_stat is not None:
                n_pass = sum(
                    1 for iv in range(nIvs)
                    if stat_vals[iv] >= best_stat
                    and (best_hp is None or hp_vals[iv] >= best_hp)
                )
                results.append({
                    'opponent': opp,
                    'scenario': scenarios[si],
                    'threshold': best_stat,
                    'stat': sweep_stat,
                    'hp_threshold': best_hp,
                    'n_passing': n_pass,
                })

    grouped: dict = {}
    for r in results:
        key = (r['opponent'], r['threshold'], r['hp_threshold'])
        if key not in grouped:
            grouped[key] = {
                'opponent': r['opponent'],
                'threshold': r['threshold'],
                'stat': r['stat'],
                'hp_threshold': r['hp_threshold'],
                'n_passing': r['n_passing'],
                'scenarios': [],
            }
        grouped[key]['scenarios'].append(r['scenario'])

    return sorted(grouped.values(),
                  key=lambda r: (r['threshold'], r['opponent']))


def _make_inputs(seed, nIvs=80, nS=4, nO=5, hp_coupled=False):
    """Random inputs with stat-correlated wins so partitions exist.

    hp_coupled=True makes wins depend on (stat, hp) jointly so the
    phase-2 HP co-condition path fires.
    """
    rng = random.Random(seed)
    # Stats with duplicates (realistic: many IVs share effective stats).
    stat_pool = [round(95.0 + 0.37 * k, 2) for k in range(20)]
    ivDef = [rng.choice(stat_pool) for _ in range(nIvs)]
    ivAtk = [round(rng.choice(stat_pool) + 20.0, 2) for _ in range(nIvs)]
    ivHp = [rng.randint(120, 135) for _ in range(nIvs)]

    scores = []
    for iv in range(nIvs):
        for si in range(nS):
            for oi in range(nO):
                stat_cut = stat_pool[3 + (oi * 3 + si) % 14]
                if hp_coupled:
                    win = (ivDef[iv] >= stat_cut and ivHp[iv] >= 128)
                else:
                    win = ivDef[iv] >= stat_cut
                # ~6% noise keeps the winrate bands non-trivial
                if rng.random() < 0.06:
                    win = not win
                scores.append(700.0 if win else 300.0)

    data_obj = {'ivDef': ivDef, 'ivAtk': ivAtk, 'ivHp': ivHp}
    scenarios = [(s, s) for s in range(nS)]
    opponents = [f'Opp{oi}' for oi in range(nO)]
    return scores, nIvs, nS, nO, data_obj, scenarios, opponents


@pytest.mark.parametrize('seed', range(8))
@pytest.mark.parametrize('sweep_stat', ['def', 'atk'])
@pytest.mark.parametrize('hp_coupled', [False, True])
def test_matches_reference(seed, sweep_stat, hp_coupled):
    args = _make_inputs(seed, hp_coupled=hp_coupled)
    got = find_matchup_boundaries(*args, sweep_stat=sweep_stat)
    want = _reference_find_matchup_boundaries(*args, sweep_stat=sweep_stat)
    assert got == want


def test_matches_reference_no_hp():
    scores, nIvs, nS, nO, data_obj, scenarios, opponents = _make_inputs(99)
    del data_obj['ivHp']
    args = (scores, nIvs, nS, nO, data_obj, scenarios, opponents)
    assert (find_matchup_boundaries(*args)
            == _reference_find_matchup_boundaries(*args))


def test_value_types_preserved():
    """Thresholds must be the original Python objects from data_obj
    (an np.float64 would render '141.0' where the int rendered '141')."""
    args = _make_inputs(3, hp_coupled=True)
    for rec in find_matchup_boundaries(*args):
        assert type(rec['threshold']) is float
        assert rec['hp_threshold'] is None or type(rec['hp_threshold']) is int


def test_empty_inputs():
    assert find_matchup_boundaries(
        [], 0, 0, 0, {'ivDef': [], 'ivAtk': []}, [], []) == []
