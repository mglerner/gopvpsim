"""Per-slug cold-timing seed table for the overnight-chain ETA estimator
(scripts/overnight_eta.py, built 2026-06-28).

Pins the load-bearing properties of `_build_slug_timing_table`:

- A slug's seed is its time from the MOST-RECENT cold-chain run.
- "Most recent" is by the filename timestamp, not the path -- today's
  20260628 log can be filed under the 2026-04 month dir, so a path sort
  would order runs wrong across month dirs.
- Warm re-render runs (high aggregate sweep-cache hit ratio) are skipped
  entirely, so a warm re-render of the whole pool can't under-seed the
  next cold chain.
- The current run's own log is excluded from the table (its completed
  dives are read from its own banners; the table only seeds the
  not-yet-completed ones).
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import overnight_eta as oe  # noqa: E402


def _dive(idx, total, slug, minutes, cache_lines=()):
    """One dive block: a [N/M] banner, optional sweep-cache lines, a Done."""
    lines = [f"[{idx}/{total}] {slug}"]
    for hits, tot in cache_lines:
        lines.append(f"[02:00:00]       sweep cache: {hits}/{tot} opponent columns hit")
    lines.append(f"  Done in {minutes} min")
    return "\n".join(lines)


def _write_run(month_dir: Path, stamp: str, dives) -> Path:
    """Write an overnight_<stamp>.log under month_dir from a list of _dive()."""
    month_dir.mkdir(parents=True, exist_ok=True)
    path = month_dir / f"overnight_{stamp}.log"
    path.write_text("\n".join(dives) + "\n")
    return path


def test_agg_hit_ratio_cold_vs_warm():
    # No cache lines at all -> None (pre-cache-era or fully-cold all-miss).
    assert oe._agg_hit_ratio("[1/1] x-great-league\n  Done in 5 min\n") is None
    # A fully-cold chain prints a few hits (intra-chain sibling warming) but
    # stays well below the warm threshold.
    cold = "sweep cache: 1/87 opponent columns hit\nsweep cache: 6/522 opponent columns hit\n"
    r = oe._agg_hit_ratio(cold)
    assert r is not None and r < oe.WARM_RUN_HIT_RATIO
    # A warm re-render hits nearly every column.
    warm = "sweep cache: 62/62 opponent columns hit\nsweep cache: 74/74 opponent columns hit\n"
    assert oe._agg_hit_ratio(warm) > oe.WARM_RUN_HIT_RATIO


def test_most_recent_cold_run_wins(tmp_path):
    logs = tmp_path / "logs"
    apr = logs / "2026-04"
    # Two cold runs for the same slug; the later stamp must win.
    _write_run(apr, "20260601_000000",
               [_dive(1, 1, "medicham-great-league", "20.0")])
    _write_run(apr, "20260610_000000",
               [_dive(1, 1, "medicham-great-league", "11.0")])
    current = _write_run(apr, "20260628_000000",
                         [_dive(1, 1, "medicham-great-league", "99.0")])
    table = oe._build_slug_timing_table(current)
    # Current run excluded (not its own 99.0); most-recent prior cold = 11.0.
    assert table["medicham-great-league"] == 11.0


def test_warm_render_run_is_skipped(tmp_path):
    logs = tmp_path / "logs"
    apr = logs / "2026-04"
    # Older COLD run: the real cold time.
    _write_run(apr, "20260620_000000",
               [_dive(1, 1, "sableye-great-league", "49.0", cache_lines=[(1, 100)])])
    # Newer WARM re-render: fast, must NOT overwrite the cold seed.
    _write_run(apr, "20260624_000000",
               [_dive(1, 1, "sableye-great-league", "3.0", cache_lines=[(100, 100)])])
    current = _write_run(apr, "20260628_000000", [_dive(1, 1, "x-great-league", "5.0")])
    table = oe._build_slug_timing_table(current)
    assert table["sableye-great-league"] == 49.0


def test_sort_by_filename_stamp_across_month_dirs(tmp_path):
    logs = tmp_path / "logs"
    # The LATER run (20260628) is filed under an EARLIER month dir (2026-04),
    # mirroring the real-world misfiling; the EARLIER run (20260627) sits in
    # 2026-06. A path sort would pick 20260627; a stamp sort picks 20260628.
    _write_run(logs / "2026-06", "20260627_000000",
               [_dive(1, 1, "tinkaton-ultra-league", "30.0")])
    _write_run(logs / "2026-04", "20260628_000000",
               [_dive(1, 1, "tinkaton-ultra-league", "40.6")])
    current = _write_run(logs / "2026-04", "20260629_000000",
                         [_dive(1, 1, "x-great-league", "5.0")])
    table = oe._build_slug_timing_table(current)
    assert table["tinkaton-ultra-league"] == 40.6


def test_current_run_excluded(tmp_path):
    logs = tmp_path / "logs"
    apr = logs / "2026-04"
    current = _write_run(apr, "20260628_000000",
                         [_dive(1, 1, "only-here-great-league", "7.0")])
    table = oe._build_slug_timing_table(current)
    # The slug exists ONLY in the current run, which is excluded -> absent.
    assert "only-here-great-league" not in table
