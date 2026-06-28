#!/usr/bin/env python
"""Formatted status display for a running dive chain.

Supports any chain that follows the overnight_redive.sh shape:

* a single-line status file that the wrapper updates at each [STEP]
* a wrapper log under userdata/logs/YYYY-MM/<prefix>_YYYYMMDD_HHMMSS.log
  with "[N/M] slug" banners and "Done in X.X min" markers for each dive
* per-dive logs under userdata/logs/YYYY-MM/YYYYMMDD_HHMMSS_*.log
  emitted by deep_dive.py

Invocation::

    scripts/chain_status.py --chain overnight
    scripts/chain_status.py --chain single
    watch -n 5 scripts/chain_status.py --chain overnight

The ``single`` preset watches the most recent standalone
``python scripts/deep_dive.py ...`` run — it picks the freshest
per-dive log by mtime, with no wrapper-log required. Dives are run
serially (see memory ``feedback_serial_dives``), so a bare
``pgrep deep_dive.py`` unambiguously finds the live dive.

Escape hatch for a one-off chain::

    scripts/chain_status.py \\
        --status-file userdata/logs/foo_status.txt \\
        --pgrep foo_chain.sh \\
        --wrapper-log-glob 'userdata/logs/2026-*/foo_*.log'

Replaces the hardcoded scripts/overnight_status.sh. Whole-script ETA is
delegated to scripts/overnight_eta.py via subprocess, so the two scripts
stay in sync on bucket baselines / cross-midnight / overshoot handling.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from glob import glob
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Path globs use these literal calendar-month dirs. Kept as a module constant
# so a future 'next-CD' chain type can override just the log-dir without
# restating the whole glob shape.
LOG_DIR_GLOB = 'userdata/logs/20[0-9][0-9]-*'  # decade-safe: 2026-* went blind on 2027-01-01

# Preset chain configurations. Each is (status_file, pgrep_pattern,
# wrapper_log_glob). Per-dive log glob is shared since deep_dive.py writes
# one pattern regardless of which wrapper drove it.
CHAINS = {
    'overnight': {
        'status_file': 'userdata/logs/overnight_status.txt',
        'pgrep': 'overnight_redive.sh',
        'wrapper_log_glob': f'{LOG_DIR_GLOB}/overnight_*.log',
    },
    # Single-dive preset: for ad-hoc `python scripts/deep_dive.py ...`
    # runs that aren't driven by a wrapper script. Sentinel status_file
    # and wrapper_log_glob keep the main() flow happy; the most-recent
    # per-dive log (by mtime) is picked automatically because no
    # chain-start epoch is available to bound the candidate set.
    #
    # The pgrep pattern anchors on `python` + `deep_dive.py` so it
    # doesn't false-match this very invocation's `watch` command
    # (whose args contain the string `deep_dive.py` when a prior
    # session used --pgrep with the bare name).
    'single': {
        'status_file': '/dev/null',
        'pgrep': r'python.*deep_dive\.py',
        'wrapper_log_glob': f'{LOG_DIR_GLOB}/__no_wrapper__.log',
    },
}

# Per-dive logs: YYYYMMDD_HHMMSS_<slug>.log. Exclude wrapper-log prefixes
# so this glob doesn't swallow overnight_/retrofit_ wrapper files.
PER_DIVE_LOG_GLOB = f'{LOG_DIR_GLOB}/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*.log'

# ANSI colors. Auto-disabled on non-TTY or when --no-color is passed.
_USE_COLOR = True


def c(code: str, text: str) -> str:
    """Wrap text in ANSI color code, or pass through when color is off."""
    return f'{code}{text}\033[0m' if _USE_COLOR else text


def bold(t): return c('\033[1m', t)
def dim(t):  return c('\033[2m', t)
def green(t): return c('\033[32m', t)
def yellow(t): return c('\033[33m', t)
def red(t):    return c('\033[31m', t)
def cyan(t):   return c('\033[36m', t)
def eta_accent(t): return c('\033[1;95m', t)


def terminal_width() -> int:
    """Detect terminal width, clamped to [60, 140]. Falls back to 80."""
    try:
        w = shutil.get_terminal_size(fallback=(80, 24)).columns
    except Exception:
        w = 80
    return min(max(w, 60), 140)


def terminal_height() -> int:
    """Detect terminal height (rows), clamped to [20, 200]. Falls back to 24.

    Used to grow the variable-length sections (live dive-log tail, ML
    completion history) so a tall `watch` pane fills with useful context
    instead of stopping a third of the way down.
    """
    try:
        h = shutil.get_terminal_size(fallback=(80, 24)).lines
    except Exception:
        h = 24
    return min(max(h, 20), 200)


def rule(width: int) -> None:
    print('─' * width)


def fmt_elapsed(seconds: int) -> str:
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m{seconds % 60:02d}s'
    return f'{seconds // 3600}h{(seconds % 3600) // 60:02d}m'


def find_pid(pattern: str) -> int | None:
    """pgrep -f <pattern>; return first matching PID or None."""
    try:
        r = subprocess.run(['pgrep', '-f', pattern],
                           capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None


def pid_etime(pid: int) -> str | None:
    """ps -p <pid> -o etime=; returns the string as ps formats it, or None."""
    try:
        r = subprocess.run(['ps', '-p', str(pid), '-o', 'etime='],
                           capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    val = r.stdout.strip()
    return val or None


def latest_file(pattern: str) -> Path | None:
    """Return the most-recently-modified file matching ``pattern``, or None."""
    matches = [Path(p) for p in glob(pattern)]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def strip_log_prefix(line: str) -> str:
    """Drop the ``[YYYY-MM-DD HH:MM:SS] LEVEL module:`` prefix from a log line.

    Matches the pattern deep_dive_logging.py emits. Returns the line
    unchanged when no prefix is present.
    """
    return re.sub(r'^\[[^\]]+\] +[A-Z]+ +[a-z_]+: *', '', line)


def truncate(text: str, max_width: int) -> str:
    return text if len(text) <= max_width else text[: max_width - 3] + '...'


def print_status(status_file: Path, width: int) -> None:
    if not status_file.exists():
        return
    line = status_file.read_text().strip()
    if not line:
        return
    if 'SUCCESS' in line:
        colorized = green(line)
    elif 'FAIL' in line or 'FATAL' in line:
        colorized = red(line)
    elif 'STEP' in line:
        colorized = yellow(line)
    else:
        colorized = line
    print(f'  Step: {colorized}')


def parse_wrapper_dive_banner(wrapper_log: Path) -> tuple[str | None, str | None]:
    """Extract the latest [N/M] + slug from the wrapper log."""
    try:
        text = wrapper_log.read_text()
    except OSError:
        return None, None
    banners = re.findall(
        # [a-z0-9-]: slugs can carry digits (porygon2-great-league);
        # a digit-less class silently dropped those Dive lines.
        r'\[(\d+/\d+)\]\s+([a-z0-9-]+-(?:great|ultra|master)-league)',
        text,
    )
    if not banners:
        return None, None
    nm, slug = banners[-1]
    return f'[{nm}]', slug


def dive_elapsed_seconds(per_dive_log: Path) -> int | None:
    """Seconds since the per-dive log's first-line timestamp."""
    try:
        first_line = per_dive_log.open().readline()
    except OSError:
        return None
    m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', first_line)
    if not m:
        return None
    try:
        start = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    return int((datetime.now() - start).total_seconds())


def print_dive_info(wrapper_log: Path | None,
                    per_dive_log: Path | None,
                    width: int) -> None:
    if wrapper_log is None:
        return
    nm, slug = parse_wrapper_dive_banner(wrapper_log)
    if nm is None:
        return
    elapsed = (dive_elapsed_seconds(per_dive_log)
               if per_dive_log is not None else None)
    elapsed_str = fmt_elapsed(elapsed) if elapsed is not None else '?'
    print(f'  {bold("Dive")} {cyan(nm)} {bold(slug or "?")}  '
          f'elapsed {green(elapsed_str)}')


_ETA_LINE_RE = re.compile(
    r'sim progress:\s*(\d+)/(\d+)\s+chunks\s*\(\d+%\),\s*'
    r'elapsed\s+(\d+)s,\s*eta\s+(\d+)s'
)

# Anchors used to project a rough dive-level ETA: one of these phrases
# appears in the active log → we look for the SAME phrase in a recent
# completed dive log and use its (anchor_ts → 'Done.' last-line ts) gap
# as the projected remaining-after-anchor time. Listed latest-anchor
# first so the most-specific match wins.
_DIVE_ETA_ANCHORS = [
    'Interactive sweep',     # most precise: post-mirror, the long sweep block
    'Mirror slayer iteration',
    'Phase 2',
    'Phase 1: Screening',
]

_LOG_TS_RE = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]')

_PHASE2_TOTAL_RE = re.compile(r'Phase 2 \[\d+/(\d+)\]')


def _phase2_total(text: str):
    """Return the total moveset count from the first 'Phase 2 [N/M]' line,
    or None if no Phase 2 marker is present yet."""
    m = _PHASE2_TOTAL_RE.search(text)
    return int(m.group(1)) if m else None


def _format_eta_seconds(secs: int) -> str:
    if secs < 60:
        return f'{secs}s'
    m, s = divmod(secs, 60)
    if m < 60:
        return f'{m}m {s:02d}s'
    h, m = divmod(m, 60)
    return f'{h}h {m:02d}m'


def _parse_log_ts(line: str):
    """Parse the leading '[YYYY-MM-DD HH:MM:SS.mmm]' timestamp; None if absent."""
    m = _LOG_TS_RE.match(line)
    if m is None:
        return None
    try:
        return datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S.%f')
    except ValueError:
        return None


def _find_anchor_ts(log_path: Path, anchor: str):
    """Earliest timestamp of a log line containing ``anchor``, or None."""
    try:
        with open(log_path) as f:
            for line in f:
                if anchor in line:
                    ts = _parse_log_ts(line)
                    if ts is not None:
                        return ts
    except OSError:
        pass
    return None


def _find_completed_reference_log(active_log: Path, anchor: str,
                                   active_phase2_total: int | None,
                                   max_age_days: int = 14):
    """Most recent finished dive log (containing 'Done.' as a deep_dive line)
    that also contains ``anchor`` and isn't the active log itself.

    When ``active_phase2_total`` is known (active dive has hit Phase 2), only
    references with the same Phase 2 moveset count match — a top_movesets=3
    reference would over-estimate a top_movesets=1 active dive's remaining
    work by ~3x.

    Bounded to logs younger than ``max_age_days``."""
    log_dir = active_log.parent.parent  # userdata/logs/
    cutoff = datetime.now().timestamp() - max_age_days * 86400
    candidates = []
    for month_dir in sorted(log_dir.glob('20*'), reverse=True):
        for log in month_dir.glob('20*_*.log'):
            if log == active_log:
                continue
            if log.stat().st_mtime < cutoff:
                continue
            candidates.append(log)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for log in candidates:
        try:
            with open(log) as f:
                text = f.read()
        except OSError:
            continue
        # Quick sniff: does it have BOTH the anchor AND 'Done.' as a
        # deep_dive log line (rather than the literal token in some other
        # context)? Match the structured logger's format prefix.
        if anchor not in text:
            continue
        if not re.search(r'INFO\s+deep_dive: Done\.', text):
            continue
        if active_phase2_total is not None:
            ref_total = _phase2_total(text)
            if ref_total != active_phase2_total:
                continue  # different dive shape; would mis-estimate
        return log
    return None


def _last_log_ts(log_path: Path):
    """Last timestamped log line's parsed datetime, or None."""
    try:
        with open(log_path) as f:
            last = None
            for line in f:
                ts = _parse_log_ts(line)
                if ts is not None:
                    last = ts
            return last
    except OSError:
        return None


def _project_dive_eta(active_log: Path):
    """Project a rough dive ETA by replaying a recent completed dive's
    elapsed-from-anchor-to-'Done.' against the active dive's anchor.

    Returns (eta_seconds, anchor, reference_log_name) or (None, None, None)
    when no usable reference exists.
    """
    if not active_log.exists():
        return None, None, None
    # Pick the latest anchor present in the active log.
    try:
        active_text = active_log.read_text()
    except OSError:
        return None, None, None
    chosen_anchor = None
    for a in _DIVE_ETA_ANCHORS:
        if a in active_text:
            chosen_anchor = a
            break
    if chosen_anchor is None:
        return None, None, None
    active_anchor_ts = _find_anchor_ts(active_log, chosen_anchor)
    if active_anchor_ts is None:
        return None, None, None
    active_phase2_total = _phase2_total(active_text)
    ref = _find_completed_reference_log(
        active_log, chosen_anchor, active_phase2_total)
    if ref is None:
        return None, None, None
    ref_anchor_ts = _find_anchor_ts(ref, chosen_anchor)
    ref_done_ts = _last_log_ts(ref)
    if ref_anchor_ts is None or ref_done_ts is None:
        return None, None, None
    ref_delta = (ref_done_ts - ref_anchor_ts).total_seconds()
    active_elapsed_since_anchor = (
        datetime.now() - active_anchor_ts).total_seconds()
    remaining = int(ref_delta - active_elapsed_since_anchor)
    if remaining < 0:
        remaining = 0
    return remaining, chosen_anchor, ref.name


def print_eta(wrapper_log: Path | None,
              per_dive_log: Path | None = None) -> None:
    """Surface a runtime ETA.

    Wrapper-driven chains (overnight, retrofit) shell out to
    overnight_eta.py for SCRIPT/DIVE/BUCKETS lines (bucket-mean
    averaging across past runs needs the wrapper log's per-dive
    START/DONE banners).

    Ad-hoc single-dive runs (--chain single) have no wrapper log;
    fall back to scanning the latest per-dive log for the most
    recent `sim progress: ... eta <N>s` line that deep_dive.py emits
    during chunk processing. Surfaced verbatim — covers Phase 2 sweep
    AND mirror slayer rounds since both share the format. No attempt
    to roll up post-current-phase work; that estimate is the user's
    job.
    """
    if wrapper_log is not None:
        try:
            r = subprocess.run(
                ['python', str(REPO_ROOT / 'scripts' / 'overnight_eta.py'),
                 str(wrapper_log)],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            return
        script_line = dive_line = buckets_line = None
        for line in r.stdout.splitlines():
            if line.startswith('SCRIPT:'):
                script_line = line[len('SCRIPT: '):]
            elif line.startswith('DIVE:'):
                dive_line = line[len('DIVE: '):]
            elif line.startswith('BUCKETS:'):
                buckets_line = line[len('BUCKETS: '):]
        if script_line:
            print(f'  {eta_accent("► SCRIPT ETA: " + script_line)}')
        if dive_line:
            print(f'  {cyan("  dive ETA: " + dive_line)}')
        if buckets_line:
            print(f'    {dim(buckets_line)}')
        return

    # Single-dive fallback: scan the per-dive log for the latest progress line.
    if per_dive_log is None or not per_dive_log.exists():
        return
    last_match = None
    try:
        with open(per_dive_log) as f:
            for line in f:
                m = _ETA_LINE_RE.search(line)
                if m:
                    last_match = m
    except OSError:
        return
    if last_match is not None:
        chunks_done, chunks_total, elapsed_s, eta_s = (
            int(last_match.group(i)) for i in (1, 2, 3, 4))
        pct = 100 * chunks_done // chunks_total if chunks_total else 0
        print(f'  {eta_accent("► CURRENT-PHASE ETA: " + _format_eta_seconds(eta_s))}'
              f'  {dim(f"({chunks_done}/{chunks_total} chunks, {pct}%, "
                       f"elapsed {_format_eta_seconds(elapsed_s)})")}')

    # Dive-level rough ETA: replay a recent completed dive's elapsed-from-
    # anchor-to-'Done.' against the active dive's matching anchor. Rough
    # because dive shape (top_movesets, opponent count, mirror-slayer-cold)
    # varies; calibrate against actual completion rather than treating as
    # ground truth.
    dive_eta_s, anchor, ref_name = _project_dive_eta(per_dive_log)
    if dive_eta_s is not None:
        print(f'  {eta_accent("► DIVE ETA (rough): " + _format_eta_seconds(dive_eta_s))}'
              f'  {dim(f"(anchor: {anchor!r}, ref: {ref_name})")}')


def print_latest_log(per_dive_log: Path | None, width: int,
                     max_tail: int = 6) -> None:
    if per_dive_log is None or not per_dive_log.exists():
        print(f'  {dim("No per-dive log found yet.")}')
        return
    basename = per_dive_log.name
    mtime = per_dive_log.stat().st_mtime
    age = int(datetime.now().timestamp() - mtime)
    print(f'  {bold("Latest dive log:")} {basename}')
    print(f'  {dim(f"last line {fmt_elapsed(age)} ago")}')

    try:
        lines = per_dive_log.read_text().splitlines()
    except OSError:
        return

    # Phase: most recent banner-ish line (moveset / sweep / mirror-slayer
    # round boundary). These scroll off fast under progress-%. Pinning
    # the latest match gives the "what coarse sub-step am I in" answer.
    phase_re = re.compile(r'Phase [0-9]|Interactive sweep|Mirror slayer|iteration round|Simming')
    phase = None
    for line in reversed(lines):
        if phase_re.search(line):
            phase = strip_log_prefix(line)
            break
    if phase:
        print(f'  {bold("Phase:")} {cyan(truncate(phase, width - 12))}')

    rule(width)

    # Tail: last `max_tail` non-blank lines, each truncated to width.
    # max_tail grows with terminal height so a tall pane shows the dive's
    # narrative so far (Phase 1 results, moveset pick, Phase 2 start) rather
    # than just the latest few chunk-progress lines.
    nonblank = [ln for ln in lines if ln.strip()]
    for line in nonblank[-max_tail:]:
        clean = strip_log_prefix(line)
        print(f'  {truncate(clean, width - 4)}')


def print_step_transitions(wrapper_log: Path | None, width: int) -> None:
    if wrapper_log is None:
        return
    try:
        text = wrapper_log.read_text()
    except OSError:
        return
    relevant = [
        ln for ln in text.splitlines()
        if re.search(r'\[(STEP|DONE|FAIL|FATAL)\]', ln)
    ]
    if not relevant:
        return
    print(f'  {bold("Recent step transitions:")}')
    for line in relevant[-3:]:
        # Drop the leading date; keep the HH:MM:SS timestamp for context.
        clean = re.sub(r'^[0-9-]+ ', '', line)
        if 'FAIL' in clean or 'FATAL' in clean:
            print(f'  {red(truncate(clean, width - 4))}')
        elif 'DONE' in clean:
            print(f'  {green(truncate(clean, width - 4))}')
        elif 'STEP' in clean:
            print(f'  {yellow(truncate(clean, width - 4))}')
        else:
            print(f'  {truncate(clean, width - 4)}')


def chain_start_epoch(wrapper_log: Path | None) -> int | None:
    """Parse <prefix>_YYYYMMDD_HHMMSS.log filenames to get chain-start epoch.

    Works for overnight_*, retrofit_*, and any future <prefix>_* wrapper
    since it just extracts the two numeric groups from the basename.
    """
    if wrapper_log is None:
        return None
    m = re.search(r'_(\d{8})_(\d{6})\.log$', wrapper_log.name)
    if not m:
        return None
    try:
        dt = datetime.strptime(f'{m.group(1)} {m.group(2)}', '%Y%m%d %H%M%S')
    except ValueError:
        return None
    return int(dt.timestamp())


def print_recent_products(wrapper_log: Path | None, width: int,
                          max_products: int = 10) -> None:
    html_root = REPO_ROOT / 'userdata' / 'website'
    if not html_root.is_dir():
        return
    start_epoch = chain_start_epoch(wrapper_log)

    entries: list[tuple[float, Path]] = []
    for p in html_root.rglob('*.html'):
        try:
            entries.append((p.stat().st_mtime, p))
        except OSError:
            continue
    if not entries:
        return
    entries.sort(key=lambda e: e[0], reverse=True)

    # Main index.html first within each bucket (it's the landing click);
    # split-moveset index_m*.html are secondary.
    def bucket_key(e):
        mtime, path = e
        is_new = start_epoch is not None and mtime >= start_epoch
        is_main = path.name == 'index.html'
        # Lower tuple sorts first. New > Pre; within each, main > split.
        return (0 if is_new else 1, 0 if is_main else 1)

    entries.sort(key=lambda e: (bucket_key(e), -e[0]))
    new_count = sum(1 for m, _ in entries
                    if start_epoch is not None and m >= start_epoch)
    display = entries[:max_products]

    print(f'  {bold("Recent products:")}  '
          f'{dim(f"(new: {new_count}, shown: {len(display)})")}')
    now = datetime.now().timestamp()
    for mtime, path in display:
        age = int(now - mtime)
        if age < 60:
            age_str = f'{age}s ago'
        elif age < 3600:
            age_str = f'{age // 60}m ago'
        else:
            age_str = f'{age // 3600}h{(age % 3600) // 60:02d}m ago'
        tag = (green('new') if start_epoch is not None and mtime >= start_epoch
               else dim('pre'))
        try:
            rel = str(path.relative_to(REPO_ROOT))
        except ValueError:
            rel = str(path)
        max_rel = width - 18
        if len(rel) > max_rel:
            rel = '...' + rel[-(max_rel - 3):]
        print(f'  {tag}  {dim(age_str.ljust(9))}  {rel}')


# --- ML IV-guide phase (the run_iv_guides.py tail step) ---------------------
# When the overnight chain enters the ML-guide bake, the dive-cadence machinery
# above goes stale: there's no fresh per-dive deep_dive log, and overnight_eta
# extrapolates dive timings into a nonsense ETA. Detect the phase from the
# status line and show an ML-native block instead (parsed from the [n/N] OK/FAIL
# completion lines run_iv_guides tees into the wrapper log, plus live worker
# CPU% for stall-spotting). Mirrors scripts/iv_guides_status.py.

_ML_DONE_RE = re.compile(
    r'^\[(\d+)/(\d+)\]\s+(OK|FAIL)\s+(.+?)\s+\(([\d.]+)\s*min\)\s*(.*)$')


def in_ml_phase(status_file: Path) -> bool:
    """True while the current chain step is the ML IV-guide bake.

    The status file holds only the latest [STEP] line (overwritten per step),
    so a plain substring test is unambiguous: it says 'ML IV guides' during the
    bake and the next step's text afterward.
    """
    try:
        return 'ML IV guides' in status_file.read_text()
    except OSError:
        return False


def _ml_live_workers() -> int:
    try:
        r = subprocess.run(['pgrep', '-f', 'iv_envelope_analysis'],
                           capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 0
    return len([x for x in r.stdout.split() if x.strip()])


def _ml_species_from_cmd(cmd: str) -> str:
    """Pull the focal species out of an iv_envelope_analysis.py command line,
    dropping flags (handles species with spaces/parens, e.g. 'Dialga (Origin)').
    Mirrors iv_guides_status._species_from_cmd so the slug -> per-guide-log
    mapping below resolves the SAME path the worker wrote."""
    after = cmd.split('iv_envelope_analysis.py', 1)[-1].split()
    toks, i = [], 0
    while i < len(after):
        t = after[i]
        if t in ('--all-shields', '--no-cache'):
            i += 1
        elif t in ('--pool', '--iv-floor'):
            i += 2
        else:
            toks.append(t)
            i += 1
    return ' '.join(toks) or '?'


def _ml_slug(species: str) -> str:
    """iv_envelope_analysis's per-guide log slug (same formula it uses)."""
    return species.lower().replace(' ', '_').replace('(', '').replace(')', '')


def _ml_worker_phase(species: str) -> str:
    """Current phase of a live worker = last meaningful line of its per-guide
    log (userdata/logs/iv_guides/<slug>.log), stripped of the structured-logger
    prefix. Empty string when the log isn't there yet (worker just started)."""
    path = REPO_ROOT / 'userdata' / 'logs' / 'iv_guides' / f'{_ml_slug(species)}.log'
    try:
        lines = [ln.rstrip('\n') for ln in path.read_text().splitlines()
                 if ln.strip()]
    except OSError:
        return ''
    return strip_log_prefix(lines[-1]) if lines else ''


def _ml_active_workers() -> list[tuple[str, float]]:
    """(species, cpu%) per live iv_envelope_analysis worker, for stall-spotting
    (cpu% near 0 on a worker that should be simming = wedged or machine slept)."""
    try:
        out = subprocess.run(['ps', '-axo', '%cpu=,command='],
                             capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        return []
    rows = []
    for line in out.splitlines():
        if 'iv_envelope_analysis.py' not in line or 'pgrep' in line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            cpuf = float(parts[0])
        except ValueError:
            cpuf = 0.0
        rows.append((_ml_species_from_cmd(parts[1]), cpuf))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def print_ml_guides(wrapper_log: Path | None, width: int,
                    fill_budget: int = 8) -> None:
    total = concurrency = None
    done: list[tuple[bool, str, float]] = []  # (ok, species, minutes)
    if wrapper_log is not None:
        try:
            for line in wrapper_log.read_text().splitlines():
                m = re.search(r'running up to (\d+) concurrent', line)
                if m:
                    concurrency = int(m.group(1))
                m = re.match(r'(\d+) species to generate', line)
                if m:
                    total = int(m.group(1))
                m = _ML_DONE_RE.match(line)
                if m:
                    total = int(m.group(2))
                    done.append(
                        (m.group(3) == 'OK', m.group(4), float(m.group(5))))
        except OSError:
            pass

    running = _ml_live_workers()
    n_done = len(done)
    n_ok = sum(1 for d in done if d[0])
    n_fail = n_done - n_ok
    tot = total or (n_done + running)
    pending = max(0, tot - n_done - running)
    times = [d[2] for d in done]
    avg = sum(times) / len(times) if times else 0.0

    print(f'  {bold("ML IV guides")}  {dim("(run_iv_guides.py tail step)")}')
    bar_w = max(10, min(32, width - 28))
    frac = (n_done / tot) if tot else 0.0
    fill = int(bar_w * frac)
    bar = green('#' * fill) + dim('-' * (bar_w - fill))
    print(f'  [{bar}] {bold(f"{n_done}/{tot}")}  ({frac * 100:4.1f}%)')
    print('  ' + '   '.join([
        green(f'ok {n_ok}'),
        (red if n_fail else dim)(f'fail {n_fail}'),
        cyan(f'running {running}'),
        yellow(f'pending {pending}'),
    ]))

    if avg:
        slots = concurrency or max(1, running)
        eta_s = int((tot - n_done) * avg * 60 / max(1, slots))
        done_at = datetime.fromtimestamp(datetime.now().timestamp() + eta_s)
        print(f'  {eta_accent("► ML ETA: ~" + _format_eta_seconds(eta_s))}'
              f'  {dim(f"(avg {avg:.0f} min/guide, {slots}-wide, "
                       f"done ~{done_at:%H:%M})")}')
    elif running:
        print(f'  {dim("ETA: computing — cold first-wave guides run ~45-118 min, "
                       "so no completions land until that wave finishes")}')

    workers = _ml_active_workers()
    if workers:
        shown = '  '.join(
            f'{sp} {(red if cpu < 20 else green)(f"{cpu:.0f}%")}'
            for sp, cpu in workers[:6])
        more = dim(f'  +{len(workers) - 6} more') if len(workers) > 6 else ''
        print(f'  {dim("workers cpu%:")} {shown}{more}')
        # Per-worker current phase (last line of each guide's per-guide log),
        # so the watcher sees motion WITHIN a guide, not just that it's running.
        for sp, _cpu in workers[:6]:
            phase = _ml_worker_phase(sp)
            if phase:
                print(f'    {cyan(truncate(f"{sp}: {phase}", width - 6))}')
        n_low = sum(1 for _, cpu in workers if cpu < 20)
        if n_low:
            print(f'  {red(f"WARN: {n_low} worker(s) <20% CPU — possible stall "
                           "(or the machine slept)")}')
    if done:
        # Completed guides, newest first, one per line so a tall pane fills
        # with the run's history instead of a single truncated line. Reserve
        # the rows the worker/cpu block above already used; show at least 4.
        n_show = max(4, fill_budget - len(workers[:6]) - 2)
        print(f'  {dim("completed (newest first):")}')
        for ok, sp, m in reversed(done[-n_show:]):
            mark = green('OK  ') if ok else red('FAIL')
            print(f'    {mark} {truncate(f"{sp}  {m:.0f}m", width - 12)}')
        if len(done) > n_show:
            print(f'    {dim(f"... +{len(done) - n_show} earlier")}')


def main() -> int:
    global _USE_COLOR

    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument('--chain', choices=list(CHAINS),
                   help='Preset chain (overnight, retrofit, single). '
                        '`single` tracks the most recent ad-hoc '
                        '`python scripts/deep_dive.py ...` run.')
    p.add_argument('--status-file', type=Path,
                   help='Override: single-line status file')
    p.add_argument('--pgrep', help='Override: pgrep pattern for chain liveness')
    p.add_argument('--wrapper-log-glob',
                   help='Override: glob for the wrapper log')
    p.add_argument('--per-dive-log-glob', default=PER_DIVE_LOG_GLOB,
                   help='Override: glob for per-dive logs '
                        '(default: userdata/logs/YYYY-MM/YYYYMMDD_*.log)')
    p.add_argument('--pid', type=int,
                   help='Override: chain PID (otherwise pgrep lookup)')
    p.add_argument('--no-color', action='store_true')
    args = p.parse_args()

    # Colors are on by default so `watch -c` renders correctly. Pipe-
    # through or capture-to-file: pass --no-color. Auto-detecting via
    # isatty() breaks the primary use case (watch -c), which routes
    # stdout through watch and reads !isatty().
    if args.no_color:
        _USE_COLOR = False

    # Resolve chain config: preset + per-flag overrides.
    if args.chain:
        preset = CHAINS[args.chain]
    else:
        preset = {}
    status_file = Path(args.status_file or preset.get('status_file') or '')
    pgrep_pattern = args.pgrep or preset.get('pgrep')
    wrapper_log_glob = args.wrapper_log_glob or preset.get('wrapper_log_glob')

    if not status_file or not pgrep_pattern or not wrapper_log_glob:
        p.error('--chain or all of --status-file/--pgrep/--wrapper-log-glob required')

    status_file = (REPO_ROOT / status_file if not status_file.is_absolute()
                   else status_file)
    width = terminal_width()
    height = terminal_height()
    # Lines the rest of the display consumes (header, pid/status/dive/eta,
    # section headers + rules, step transitions, recent products, refresh
    # hint, plus a couple for watch's own header). Conservative so we
    # under-fill by a few rows rather than overflow -- watch truncates the
    # BOTTOM when content exceeds the pane.
    _FIXED_OVERHEAD = 34
    fill_budget = max(6, height - _FIXED_OVERHEAD)

    # Header + PID liveness.
    label = (args.chain or 'CUSTOM').upper()
    print(bold(cyan(f'{label} DIVE STATUS  ({datetime.now():%H:%M:%S})')))
    rule(width)

    pid = args.pid or find_pid(pgrep_pattern)
    if pid and (etime := pid_etime(pid)):
        print(f'  PID {pid}  {green(bold("ALIVE"))}  (elapsed {etime.strip()})')
    else:
        print(f'  PID {pid or "?"}  {red(bold("DEAD / NOT FOUND"))}')

    print_status(status_file, width)

    wrapper_log = latest_file(str(REPO_ROOT / wrapper_log_glob))

    if in_ml_phase(status_file):
        # ML IV-guide bake: the dive per-dive-log / overnight_eta machinery is
        # stale here (no fresh deep_dive log; dive-cadence ETA is meaningless).
        # Show the ML-native progress block instead.
        print_ml_guides(wrapper_log, width, fill_budget)
        rule(width)
    else:
        # Per-dive log: most recent non-wrapper log within the selected
        # chain's run window. Lower bound: chain start epoch (from wrapper
        # log filename). Upper bound: now for a live chain (PID alive) /
        # wrapper-log mtime for a dead chain. Without the upper bound,
        # the overnight preset picks up per-dive logs from a later
        # retrofit run that also happen to land in userdata/logs/.
        start_epoch = chain_start_epoch(wrapper_log)
        if pid and wrapper_log is not None:
            end_epoch = None  # no upper bound needed for a live chain
        elif wrapper_log is not None:
            end_epoch = wrapper_log.stat().st_mtime + 60  # 1m slop past last step
        else:
            end_epoch = None
        per_dive_candidates = [
            Path(x) for x in glob(str(REPO_ROOT / args.per_dive_log_glob))
            if not Path(x).name.startswith(('overnight_', 'retrofit_'))
        ]
        if start_epoch is not None:
            per_dive_candidates = [
                p for p in per_dive_candidates
                if p.stat().st_mtime >= start_epoch
                and (end_epoch is None or p.stat().st_mtime <= end_epoch)
            ]
        per_dive_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        per_dive_log = per_dive_candidates[0] if per_dive_candidates else None

        print_dive_info(wrapper_log, per_dive_log, width)
        print_eta(wrapper_log, per_dive_log)
        rule(width)
        print_latest_log(per_dive_log, width, max_tail=min(fill_budget, 45))
        rule(width)

    print_step_transitions(wrapper_log, width)
    rule(width)
    print_recent_products(wrapper_log, width)
    rule(width)

    refresh_hint = f'scripts/chain_status.py --chain {args.chain}' if args.chain \
        else 'scripts/chain_status.py'
    print(f'  {dim(f"refresh: watch -n 5 -c {refresh_hint}")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
