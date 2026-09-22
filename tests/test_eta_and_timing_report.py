"""Two estimator fixes from 2026-09-12, both found by their symptoms.

1. `overnight_eta.FALLBACKS['ml_tail']` was a flat 420 minutes with no
   self-calibration, while gl_full / ul_full / forretress all learn from the
   run. The real tail measured 3.9 min, so every ETA printed during the
   Twilight Trails bake over-reported by ~7h.

2. `bake_timing_report.py` keyed its rows by species NAME, so a species with
   both a GL and a UL dive collapsed into one summed row -- 81 rows for a
   135-dive bake. Totals were right; the breakdown was not.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

import bake_timing_report as btr  # noqa: E402
import overnight_eta as oe  # noqa: E402


def test_ml_tail_prefers_a_measurement_over_the_fallback(tmp_path):
    """A past run's own completion line trains the estimate."""
    d = tmp_path / '2026-09'
    d.mkdir(parents=True)
    (d / 'ml_guides_x.log').write_text('Done in 3.9 min: 60 ok, 0 failed.\n')
    assert oe.measured_ml_tail_min(tmp_path) == pytest.approx(3.9)


def test_ml_tail_ignores_a_run_where_everything_failed(tmp_path):
    """An instant all-fail must not train the estimate toward zero."""
    d = tmp_path / '2026-09'
    d.mkdir(parents=True)
    (d / 'ml_guides_x.log').write_text('Done in 0.1 min: 0 ok, 60 failed.\n')
    assert oe.measured_ml_tail_min(tmp_path) is None


def test_ml_tail_falls_back_when_there_is_no_history(tmp_path):
    assert oe.measured_ml_tail_min(tmp_path) is None
    assert oe.FALLBACKS['ml_tail'] == 10.0, (
        'the ml_tail fallback was recalibrated 2026-09-22')


def test_the_ml_tail_fallback_is_within_headroom_of_its_measurement():
    """The fallback value itself, not just the preference order.

    Pre-fix value (until 2026-09-22): FALLBACKS['ml_tail'] == 420.0, against a
    measured 3.9 min -- ~108x high. The 2026-09-12 fix added
    measured_ml_tail_min() but deliberately LEFT the constant wrong, on the
    theory that a flagged wrong number is acceptable because it is last
    resort. It is not: on a machine with no ML history (a fresh clone, a
    rotated userdata/logs) the watcher prints that number with no measurement
    to override it, and ~7h of phantom ETA is exactly what the Twilight Trails
    bake showed.

    Ground truth is the one measurement we have, kept in
    oe.ML_TAIL_MEASUREMENT. The band is deliberately loose -- this pins "the
    fallback is calibrated against a real run", not a specific rounding.
    """
    measured = oe.ML_TAIL_MEASUREMENT['minutes']
    assert measured == 3.9 and oe.ML_TAIL_MEASUREMENT['guides_ok'] == 60, (
        'the recorded 2026-09-12 measurement changed; recalibrate the '
        'fallback against the new one rather than editing this test')
    fallback = oe.FALLBACKS['ml_tail']
    assert measured <= fallback <= 5 * measured, (
        f"ml_tail fallback {fallback}m is not within [1x, 5x] of the only "
        f"measurement we have ({measured}m on "
        f"{oe.ML_TAIL_MEASUREMENT['date']}). It was 420.0m -- ~108x -- until "
        f"2026-09-22.")


def test_a_historyless_machine_gets_the_fallback_not_a_phantom_tail(tmp_path):
    """The path that made the wrong constant visible, end to end.

    No ML history at all -> measured_ml_tail_min() is None -> the ETA adds
    FALLBACKS['ml_tail']. Pre-fix that added 7 hours to every printed ETA.
    """
    assert oe.measured_ml_tail_min(tmp_path) is None
    added = oe.FALLBACKS['ml_tail']
    assert added < 60, (
        f'a historyless machine would add {added / 60:.1f}h of ML tail to '
        f'every ETA; pre-fix this was 7.0h')


def test_timing_report_separates_the_same_species_in_two_leagues(tmp_path):
    """The collapse bug, reproduced minimally.

    Pre-fix both dives keyed to 'Azumarill' and the rows merged. Note the
    totals were never wrong, so a totals-only assertion would NOT have caught
    this -- which is why this checks row identity.
    """
    log = tmp_path / 'chain.log'
    log.write_text(
        "[10:00:00] CLI: python scripts/deep_dive.py Azumarill --league great\n"
        "[10:00:10] Running Bubble / Ice Beam...\n"
        "[10:01:00] Generating analysis sections...\n"
        "[10:02:00] CLI: python scripts/deep_dive.py Azumarill --league ultra\n"
        "[10:02:10] Running Bubble / Ice Beam...\n"
        "[10:03:00] Generating analysis sections...\n"
        "[10:04:00] done\n")
    rows = btr.classify(log)
    assert len(rows) == 2, f'GL and UL collapsed into: {list(rows)}'
    assert any('gr' in k for k in rows), list(rows)
    assert any('ul' in k for k in rows), list(rows)


def test_timing_report_totals_survive_the_key_change(tmp_path):
    """Positive control: splitting rows must not double-count time."""
    log = tmp_path / 'chain.log'
    log.write_text(
        "[10:00:00] CLI: python scripts/deep_dive.py Azumarill --league great\n"
        "[10:00:10] Running Bubble / Ice Beam...\n"
        "[10:01:10] Generating analysis sections...\n"
        "[10:02:10] CLI: python scripts/deep_dive.py Azumarill --league ultra\n"
        "[10:02:20] Running Bubble / Ice Beam...\n"
        "[10:03:20] Generating analysis sections...\n"
        "[10:04:20] done\n")
    rows = btr.classify(log)
    total = sum(v for b in rows.values() for v in b.values())
    # 10:00:00 -> 10:04:20 is 260s; the first stamp opens no interval.
    assert total == pytest.approx(260, abs=2), total
