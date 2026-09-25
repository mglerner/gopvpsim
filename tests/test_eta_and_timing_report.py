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


# --- 2026-09-25: serial openers, per-dive logs, and the sleep bucket -------
#
# The 2026-09-20 bake read 21.9 h parallel / 15.5 h serial here, with no
# sleep bucket. Per-dive attribution (and this script since the fix, on the
# same logs with `pmset -g log`) gives 16.84 h parallel / 18.60 h serial /
# 1.82 h sleep.

import datetime  # noqa: E402

import pmset_sleep  # noqa: E402

_DAY = datetime.datetime(2026, 9, 21)


def _dive_log(path, rows):
    """Write a per-dive log in deep_dive_logging's millisecond format."""
    lines = []
    for hms, msg in rows:
        lines.append(f'[2026-09-21 {hms}.000] INFO    deep_dive: {msg}')
    path.write_text('\n'.join(lines) + '\n')
    return path


def _epoch(hms):
    h, m, s = (int(x) for x in hms.split(':'))
    return (_DAY + datetime.timedelta(hours=h, minutes=m, seconds=s)).timestamp()


_CLI = 'CLI: python scripts/deep_dive.py Jellicent --league ultra --best-buddy auto'


def test_parent_side_openers_are_serial(tmp_path):
    """Each 10 s interval below is opened by a parent-side marker, except the
    sweep pool ('signature dedup' -> 'sims in'). Pre-fix every one of them
    inherited 'parallel' from the pool line before it: the old classifier
    read this same sequence (as a chain log) as 80 s parallel, 0 s serial."""
    log = _dive_log(tmp_path / 'd.log', [
        ('06:00:00', _CLI),
        ('06:00:00', '      signature dedup: 2373 profiles x 78 opponents -> 1 pairs'),
        ('06:00:10', '    660,852 sims in 10.0s (66,085 sims/s)'),
        ('06:00:20', '  Running Hex / Ice Beam, Shadow Ball (Rank 1)...'),
        ('06:00:30', '      sweep cache: 78/78 opponent columns hit'),
        ('06:00:40', '    0 sims in 0.0s'),
        ('06:00:50', 'Replay state: /x/y.replay.pkl.gz'),
        ('06:01:00', 'Split mode: emitting 5 per-moveset HTML files'),
        ('06:01:10', 'Writing HTML...'),
        ('06:01:20', 'Done.'),
    ])
    rows = btr.classify_dive_logs([log], sleeps=[])
    (b,) = rows.values()
    assert b['parallel'] == pytest.approx(10)
    assert b['serial'] == pytest.approx(70)
    assert b['sleep'] == 0


def test_a_pmset_sleep_window_lands_in_the_sleep_bucket(tmp_path):
    """The 09-21 06:35 lid-close, reduced: a 20-minute render gap with a
    known 600 s sleep window inside it. Pre-fix there was no sleep bucket:
    the old classifier read all 1,230 s as serial render time."""
    log = _dive_log(tmp_path / 'd.log', [
        ('06:30:00', _CLI),
        ('06:30:00', 'Rendering results section (moveset 0: HEX / ICE_BEAM)...'),
        ('06:50:00', 'Results section rendered in 1200.0s'),
        ('06:50:30', 'Done.'),
    ])
    sleeps = [(_epoch('06:35:00'), _epoch('06:45:00'), 'Clamshell Sleep')]
    (b,) = btr.classify_dive_logs([log], sleeps).values()
    assert b['sleep'] == pytest.approx(600)
    assert b['serial'] == pytest.approx(1230 - 600)
    # Same log, no pmset data: the heuristic files the whole > SLEEP_GAP_S
    # serial interval as sleep, and leaves the short one alone.
    (h,) = btr.classify_dive_logs([log], None).values()
    assert h['sleep'] == pytest.approx(1200)
    assert h['serial'] == pytest.approx(30)
    # Positive control: an empty pmset window list means "checked, no
    # sleep", so nothing moves out of serial.
    (z,) = btr.classify_dive_logs([log], []).values()
    assert z['sleep'] == 0 and z['serial'] == pytest.approx(1230)


def test_the_heuristic_leaves_long_pool_intervals_alone(tmp_path):
    """A cold sweep's pool legitimately runs for many minutes."""
    log = _dive_log(tmp_path / 'd.log', [
        ('06:00:00', _CLI),
        ('06:00:00', '      signature dedup: 3148 profiles x 76 opponents -> 1 pairs'),
        ('06:30:00', '    9,000,000 sims in 1800.0s'),
    ])
    (b,) = btr.classify_dive_logs([log], None).values()
    assert b['parallel'] == pytest.approx(1800) and b['sleep'] == 0


def test_real_pmset_lines_feed_the_bucket(tmp_path):
    """End to end through pmset_sleep's parser (verbatim 09-21 line). The
    per-dive stamps are local time, so build the log from the parsed window
    rather than hard-coding a timezone."""
    windows, _first = pmset_sleep.parse_sleep_windows(
        "2026-09-21 06:35:57 -0400 Sleep               \tEntering Sleep "
        "state due to 'Clamshell Sleep':TCPKeepAlive=active Using Batt "
        "(Charge:4%) 921 secs\n")
    (s, e, _r), = windows
    t0 = datetime.datetime.fromtimestamp(s - 60)
    t1 = datetime.datetime.fromtimestamp(e + 60)
    log = tmp_path / 'd.log'
    log.write_text(
        f'[{t0:%Y-%m-%d %H:%M:%S}.000] INFO    deep_dive: {_CLI}\n'
        f'[{t0:%Y-%m-%d %H:%M:%S}.000] INFO    deep_dive: Writing HTML...\n'
        f'[{t1:%Y-%m-%d %H:%M:%S}.000] INFO    deep_dive: Done.\n')
    (b,) = btr.classify_dive_logs([log], windows).values()
    assert b['sleep'] == pytest.approx(921)
    assert b['serial'] == pytest.approx(120)


def test_main_prefers_per_dive_logs_and_falls_back(tmp_path, capsys):
    d1 = _dive_log(tmp_path / '20260921_060000_jellicent_ultra.log', [
        ('06:00:00', _CLI), ('06:00:10', 'Writing HTML...'),
        ('06:00:20', 'Done.')])
    chain = tmp_path / 'overnight_20260921_055900.log'
    chain.write_text(
        f'[06:00:00] Log file: {d1}\n'
        f'[06:00:00] {_CLI}\n'
        '[06:00:10] Writing HTML...\n'
        '[06:00:20] Done.\n')
    btr.main([str(chain), '--no-pmset'])
    out = capsys.readouterr().out
    assert 'source: 1 per-dive logs' in out

    btr.main([str(chain), '--no-pmset', '--chain-only'])
    assert 'source: chain log' in capsys.readouterr().out

    d1.unlink()   # a rotated per-dive log -> the chain log, said out loud
    btr.main([str(chain), '--no-pmset'])
    out = capsys.readouterr().out
    assert 'source: chain log' in out and '1 of 1 per-dive logs missing' in out


def test_chain_log_intervals_survive_midnight(tmp_path):
    """Pre-fix a [23:59:50] -> [00:00:10] interval was dropped (0 s
    counted), as was any interval of an hour or more -- i.e. exactly the
    long sleeps."""
    log = tmp_path / 'overnight_20260920_235900.log'
    log.write_text(
        f'[23:59:50] {_CLI}\n'
        '[23:59:50] Writing HTML...\n'
        '[00:00:10] Done.\n')
    (b,) = btr.classify(log).values()
    assert b['serial'] == pytest.approx(20)
