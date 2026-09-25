"""System-sleep windows from macOS ``pmset -g log``.

Shared by verify_overnight.py (goes red when a chain slept) and
bake_timing_report.py (puts slept time in its own bucket). Born from the
2026-09-20 bake: two lid-close (clamshell) sleeps cost 1.82 h and were first
misread as render-code gaps, because no tool looked at the power log.

What counts: every ``Sleep ... Entering Sleep state due to '<reason>' ...
N secs`` line, as the window [stamp, stamp + N). The trailing N is how long
the machine stayed asleep before its next (Dark)Wake, so summing the windows
gives slept wall-clock. A lid-close shows up as one 'Clamshell Sleep' entry
followed by a run of 'Maintenance Sleep' / 'Sleep Service Back to Sleep'
entries separated by ~45 s DarkWakes; all of them count, the DarkWakes do
not. On 2026-09-20 this sums to 6,543 s = 1.82 h, which matches the per-dive
log attribution. "Entering DarkWake state" lines carry no duration and are
skipped.

The log is a rolling window (about a week on this machine), so a caller
should compare ``first_stamp`` with the start of the span it asks about.
"""
from __future__ import annotations

import datetime
import re
import subprocess

# 2026-09-21 06:35:57 -0400 Sleep  <TAB>Entering Sleep state due to
# 'Clamshell Sleep':TCPKeepAlive=active Using Batt (Charge:4%) 921 secs
_STAMP = r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [-+]\d{4})'
_SLEEP_RE = re.compile(
    _STAMP + r" Sleep\s+Entering Sleep state due to '([^']*)'.*?(\d+) secs")
_ANY_RE = re.compile(r'^' + _STAMP + r' ')


def _epoch(stamp: str) -> float:
    return datetime.datetime.strptime(
        stamp, '%Y-%m-%d %H:%M:%S %z').timestamp()


def read_pmset_log(timeout: float = 120) -> str | None:
    """``pmset -g log`` output, or None when it cannot be had.

    None covers every way this can be unavailable: not macOS (no pmset
    binary), pmset failing, or pmset hanging past ``timeout``. The caller
    reports that as a SKIP; it is never an error.
    """
    try:
        r = subprocess.run(['pmset', '-g', 'log'], capture_output=True,
                           text=True, errors='replace', timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def parse_sleep_windows(text: str):
    """-> (windows, first_stamp) from a ``pmset -g log`` dump.

    ``windows`` is a list of (start_epoch, end_epoch, reason). ``first_stamp``
    is the epoch of the earliest timestamped line of any kind, or None when
    the text has no timestamped line at all -- that is the "unparseable"
    signal (a log with zero sleeps still has thousands of other lines).
    """
    first = None
    windows = []
    for line in text.splitlines():
        m = _ANY_RE.match(line)
        if not m:
            continue
        if first is None:
            first = _epoch(m.group(1))
        s = _SLEEP_RE.match(line)
        if s:
            t0 = _epoch(s.group(1))
            windows.append((t0, t0 + int(s.group(3)), s.group(2)))
    return windows, first


def overlap_seconds(windows, a: float, b: float) -> float:
    """Seconds of [a, b) that fall inside any sleep window."""
    total = 0.0
    for s, e, _reason in windows:
        lo, hi = max(a, s), min(b, e)
        if hi > lo:
            total += hi - lo
    return total
