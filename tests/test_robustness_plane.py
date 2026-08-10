"""The bool-plane robustness core (deep_dive_lib/robustness.py).

Worlds 2026 session-2 split: ``opp_plane`` is the per-(opponent IV,
scenario) core the Worlds bake driver pool-parallelizes; the historical
``opp_iv_robustness`` (wins, total) wrapper is pinned separately in
tests/test_deep_dive_card.py. These tests pin the NEW contract: the
wrapper is exactly a reduction of the plane, the scenario axis is
positional, the partition guard fails loud, and the module stays
importable without deep_dive (spawn-mode pool requirement).
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
for p in (REPO_ROOT / 'src', SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gopvpsim.pokemon import iv_rank  # noqa: E402
from deep_dive_lib import robustness  # noqa: E402

# Small-k GL fixture: Shadow Corviknight vs Azumarill is the same pair the
# wrapper tests use; both directions produce mixed win/loss planes at k=16
# (asserted below -- an all-True or all-False plane would make the
# equivalence checks vacuous).
FOCAL = ('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True)
OPP = ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], False)


def _focal_ivs():
    r1 = iv_rank(FOCAL[0], league='great', shadow=FOCAL[3])[0]
    return (r1['atk_iv'], r1['def_iv'], r1['sta_iv'])


def _args(scenarios):
    fs, ff, fc, fsh = FOCAL
    os_, of, oc, osh = OPP
    return (fs, ff, fc, fsh, _focal_ivs(), os_, of, oc, osh,
            'great', scenarios)


def test_wrapper_is_exactly_a_plane_reduction():
    """(wins, total) == (won.sum(), won.size) as plain Python floats, on a
    non-trivial plane (some wins AND some losses, per the oracle-parity
    non-triviality rule)."""
    args = _args([(0, 0), (1, 1), (2, 2)])
    won, score, ranked, n_sims = robustness.opp_plane(*args, k=16)
    wrapped = robustness.opp_iv_robustness(*args, k=16)
    assert wrapped == (float(won.sum()), float(won.size))
    assert type(wrapped[0]) is float and type(wrapped[1]) is float
    assert won.any() and not won.all()          # non-trivial
    assert won.shape == (len(ranked), 3)
    assert score.dtype == np.uint16
    assert (score <= 1000).all()
    # won is the authority, but on non-tie cells it must agree with score
    assert ((score > 500) == won).all()
    # dedup means strictly fewer sims than cells for this fixed-form pair
    assert n_sims < won.size
    assert n_sims % 3 == 0                       # groups x scenarios


def test_duplicate_scenarios_stay_distinct_columns():
    """The scenario axis is positional: [(1,1), (1,1)] doubles the
    denominator instead of collapsing (the session-1 probe keyed cells by
    scenario VALUE and would have silently halved it)."""
    single = robustness.opp_iv_robustness(*_args([(1, 1)]), k=8)
    double = robustness.opp_iv_robustness(*_args([(1, 1), (1, 1)]), k=8)
    assert double[1] == 2 * single[1]
    assert double[0] == 2 * single[0]


def test_generator_scenarios_are_materialized():
    """A generator argument must not be exhausted by the first dedup
    group."""
    gen = ((sf, so) for sf, so in [(1, 1), (2, 2)])
    res = robustness.opp_iv_robustness(*_args(gen), k=8)
    assert res[1] == 8 * 2


def test_cohort_indices_override_topk():
    """Explicit cohort indices index the FULL ranked list (Worlds
    atk-weighted cohorts reach far beyond top-k) and set plane row
    order."""
    args = _args([(1, 1)])
    full = iv_rank(OPP[0], league='great', shadow=OPP[3])
    cohort = [len(full) - 1, 0, 5]               # deliberately unsorted
    won, score, ranked, _ = robustness.opp_plane(*args, cohort=cohort, k=8)
    assert won.shape == (3, 1)
    assert [r['atk_iv'] for r in ranked] == [
        full[i]['atk_iv'] for i in cohort]
    assert [r['stat_product'] for r in ranked] == [
        full[i]['stat_product'] for i in cohort]


def test_partition_guard_fails_loud(monkeypatch):
    """A grouping that drops a position must raise, never return a plane
    with silent False rows."""
    real = robustness._opp_robustness_groups

    def dropper(*a, **kw):
        return real(*a, **kw)[1:]                # lose one group

    monkeypatch.setattr(robustness, '_opp_robustness_groups', dropper)
    with pytest.raises(RuntimeError, match='not a partition'):
        robustness.opp_plane(*_args([(1, 1)]), k=8)


def test_no_bait_plane_differs_and_wrapper_stays_bait_on():
    """focal_bait=False is a real axis and the wrapper never exposes it
    (always bait-on, matching the historical behavior).

    Fixture: Lickilicky (Body Slam 35 / Shadow Ball 55 -- the classic
    cheap-bait spread) vs Shadow Quagsire, which at k=24 differs in 49
    score cells AND flips 24 win cells between bait modes (measured
    2026-08-10; Corviknight vs Azumarill, the other fixtures' pair, is
    genuinely bait-insensitive at small k)."""
    r1 = iv_rank('Lickilicky', league='great', shadow=False)[0]
    args = ('Lickilicky', 'ROLLOUT', ['BODY_SLAM', 'SHADOW_BALL'], False,
            (r1['atk_iv'], r1['def_iv'], r1['sta_iv']),
            'Quagsire', 'MUD_SHOT', ['AQUA_TAIL', 'STONE_EDGE'], True,
            'great', [(sf, so) for sf in range(3) for so in range(3)])
    on = robustness.opp_plane(*args, k=24, focal_bait=True)
    off = robustness.opp_plane(*args, k=24, focal_bait=False)
    assert not np.array_equal(on[1], off[1])     # scores differ somewhere
    assert not np.array_equal(on[0], off[0])     # ... and wins flip too
    wrapped = robustness.opp_iv_robustness(*args, k=24)
    assert wrapped == (float(on[0].sum()), float(on[0].size))


def test_module_imports_without_deep_dive():
    """Spawn-mode pool children import deep_dive_lib.robustness directly;
    it must never drag the deep_dive orchestrator in (the same invariant
    deep_dive_lib/__init__.py documents for sweep)."""
    code = (
        'import sys; sys.path.insert(0, "src"); sys.path.insert(0, "scripts")\n'
        'import deep_dive_lib.robustness\n'
        'assert "deep_dive" not in sys.modules, "robustness imported deep_dive"\n'
        'print("OK")\n'
    )
    out = subprocess.run([sys.executable, '-c', code], cwd=REPO_ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert 'OK' in out.stdout


def test_plane_task_worker_stacks_spreads():
    """The pool entry point returns (won, score, n_sims) stacked over the
    task's focal spreads, aligned with per-spread opp_plane calls."""
    cohort = list(range(8))
    r1 = iv_rank(FOCAL[0], league='great', shadow=FOCAL[3])[0]
    r2 = iv_rank(FOCAL[0], league='great', shadow=FOCAL[3])[1]
    task = {
        'focal_species': FOCAL[0], 'focal_fast': FOCAL[1],
        'focal_charged': FOCAL[2], 'focal_shadow': FOCAL[3],
        'focal_spreads': [(r1['atk_iv'], r1['def_iv'], r1['sta_iv']),
                          (r2['atk_iv'], r2['def_iv'], r2['sta_iv'])],
        'opponent': OPP[0], 'opp_fast': OPP[1], 'opp_charged': OPP[2],
        'opp_shadow': OPP[3], 'league': 'great',
        'scenarios': [(0, 0), (1, 1)], 'cohort': cohort, 'bait': True,
    }
    won, score, n_sims = robustness.plane_task_worker(task)
    assert won.shape == (2, 8, 2) and score.shape == (2, 8, 2)
    # BOTH spreads compared to independent references: the session-2a
    # version checked index 0 only, and a worker mutant that re-simmed
    # spread 0 for every spread survived the whole fast tier (proven
    # 2026-08-10 review) -- exactly the rank1-vs-maxatk axis the Worlds
    # planes exist to measure.
    for i in (0, 1):
        ref = robustness.opp_plane(
            FOCAL[0], FOCAL[1], FOCAL[2], FOCAL[3], task['focal_spreads'][i],
            OPP[0], OPP[1], OPP[2], OPP[3], 'great', [(0, 0), (1, 1)],
            cohort=cohort)
        assert np.array_equal(won[i], ref[0]), f'spread {i}'
        assert np.array_equal(score[i], ref[1]), f'spread {i}'
    # Non-trivial fixture: the two spreads' planes actually differ
    # (score column 1 is 559 vs 556 today), so the per-index refs bite.
    assert not np.array_equal(score[0], score[1])
