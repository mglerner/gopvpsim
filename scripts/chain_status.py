#!/usr/bin/env python
"""Formatted status display for a running dive chain.

Supports any chain that follows the overnight_redive.sh / retrofit_3_dives.sh
shape:

* a single-line status file that the wrapper updates at each [STEP]
* a wrapper log under userdata/logs/YYYY-MM/<prefix>_YYYYMMDD_HHMMSS.log
  with "[N/M] slug" banners and "Done in X.X min" markers for each dive
* per-dive logs under userdata/logs/YYYY-MM/YYYYMMDD_HHMMSS_*.log
  emitted by deep_dive.py

Invocation::

    scripts/chain_status.py --chain overnight
    scripts/chain_status.py --chain retrofit
    scripts/chain_status.py --chain single
    watch -n 5 scripts/chain_status.py --chain retrofit

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
LOG_DIR_GLOB = 'userdata/logs/2026-*'

# Preset chain configurations. Each is (status_file, pgrep_pattern,
# wrapper_log_glob). Per-dive log glob is shared since deep_dive.py writes
# one pattern regardless of which wrapper drove it.
CHAINS = {
    'overnight': {
        'status_file': 'userdata/logs/overnight_status.txt',
        'pgrep': 'overnight_redive.sh',
        'wrapper_log_glob': f'{LOG_DIR_GLOB}/overnight_*.log',
    },
    'retrofit': {
        'status_file': 'userdata/logs/retrofit_status.txt',
        'pgrep': 'retrofit_3_dives.sh',
        'wrapper_log_glob': f'{LOG_DIR_GLOB}/retrofit_*.log',
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
        r'\[(\d+/\d+)\]\s+([a-z-]+-(?:great|ultra|master)-league)',
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


def print_eta(wrapper_log: Path | None) -> None:
    """Shell out to overnight_eta.py for SCRIPT/DIVE/BUCKETS lines."""
    if wrapper_log is None:
        return
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


def print_latest_log(per_dive_log: Path | None, width: int) -> None:
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

    # Tail: last 6 non-blank lines, each truncated to width.
    nonblank = [ln for ln in lines if ln.strip()]
    for line in nonblank[-6:]:
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
    print_eta(wrapper_log)
    rule(width)
    print_latest_log(per_dive_log, width)
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
