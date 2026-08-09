#!/usr/bin/env python
"""Status box for a running render-only chain (rerender_YYYYMMDD.sh).

The re-render counterpart of ``chain_status.py --chain overnight`` -- same
palette, same watch idiom:

    watch -n 5 -c 'scripts/rerender_status.py'
    while true; do clear; scripts/rerender_status.py; sleep 5; done

Parses the newest ``userdata/logs/*/rerender_*.log`` (override with
``--log``): chain [STEP] transitions, rerender_dive_cards' ``[n/total] OK
name (Ns)`` progress rows, the ML-guide tally, FAIL-* markers, and the
terminal COMPLETE line. Live workers come from the process table, so the
"rendering now" row shows the actual blobs in flight.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chain_status import (  # noqa: E402
    bold, cyan, dim, eta_accent, green, red, rule, terminal_width, yellow,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The chain script's step labels, in order (rerender_20260805.sh lineage).
STEP_ORDER = [
    'dive re-render from replay blobs',
    'ML guide re-render from saved JSONs',
    'comparison pages',
    'matchup web',
    'reader guides',
    'website index',
    'ship gates',
]

_STEP_RE = re.compile(r'^\[(\d\d:\d\d:\d\d)\] \[STEP\] (.+)$', re.M)
_ROW_RE = re.compile(r'^\[(\d+)/(\d+)\] (OK|FAIL) (\S+) \(([\d.]+)s\)', re.M)
_TOTAL_RE = re.compile(r'(\d+) blob\(s\) within')
_ML_RE = re.compile(r'ML guides: (\d+) ok, (\d+) failed')
_FAILMARK_RE = re.compile(r'^FAIL-\S+', re.M)
_DONE_RE = re.compile(r'RENDER CHAIN COMPLETE')


def newest_log() -> str | None:
    logs = sorted(glob.glob(os.path.join(REPO, 'userdata', 'logs', '*',
                                         'rerender_*.log')))
    return logs[-1] if logs else None


def live_workers() -> list[str]:
    """Basenames of replay blobs currently being rendered (process table)."""
    try:
        out = subprocess.run(['pgrep', '-fl', 'replay_analysis.py'],
                             capture_output=True, text=True).stdout
    except FileNotFoundError:
        return []
    blobs = []
    for line in out.splitlines():
        m = re.search(r'([\w().-]+)\.replay\.pkl\.gz', line)
        if m:
            blobs.append(m.group(1).replace('.replay.pkl', ''))
    return blobs


def chain_alive() -> bool:
    r = subprocess.run(
        ['pgrep', '-f', r'rerender_\d+\.sh|rerender_dive_cards\.py'],
        capture_output=True, text=True)
    return bool(r.stdout.strip())


def hms_to_today(hms: str, ref: float) -> float:
    """Log [HH:MM:SS] -> epoch, anchored to the log's own mtime day."""
    day = datetime.fromtimestamp(ref).strftime('%Y-%m-%d')
    t = datetime.strptime(f'{day} {hms}', '%Y-%m-%d %H:%M:%S').timestamp()
    return t - 86400 if t > ref + 60 else t  # step logged before midnight


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--log', help='chain log (default: newest rerender_*.log)')
    a = ap.parse_args()

    log_path = a.log or newest_log()
    width = min(terminal_width(), 78)
    print(bold(cyan(f'RERENDER STATUS  ({datetime.now():%H:%M:%S})')))
    rule(width)
    if not log_path or not os.path.exists(log_path):
        print(red('no rerender_*.log found under userdata/logs/'))
        return 1
    text = open(log_path).read()
    mtime = os.path.getmtime(log_path)
    alive = chain_alive()
    complete = bool(_DONE_RE.search(text))
    failmarks = _FAILMARK_RE.findall(text)

    liveness = (green(bold('COMPLETE')) if complete else
                green(bold('RUNNING')) if alive else
                red(bold('DEAD (chain gone, no COMPLETE line)')))
    print(f'  {os.path.basename(log_path)}  {liveness}')
    if failmarks:
        print('  ' + red(bold('CHAIN FAILED: ' + ', '.join(failmarks))))

    # ---- step checklist -------------------------------------------------
    # Log step lines carry suffixes ("dive re-render from replay blobs
    # (97 dives)"), so match by prefix.
    steps_seen = _STEP_RE.findall(text)

    def seen_at(name):
        return next((i for i, (_t, n) in enumerate(steps_seen)
                     if n.startswith(name)), None)

    last_idx = len(steps_seen) - 1
    print()
    for name in STEP_ORDER:
        i = seen_at(name)
        if i is None:
            print(f'  {dim("-")} {dim(name)}')
            continue
        started = steps_seen[i][0]
        if complete or i < last_idx:
            print(f'  {green("+")} {name} {dim("(" + started + ")")}')
        else:
            print(f'  {cyan(">")} {bold(name)} {dim("(" + started + ")")}'
                  f'  {cyan("<- running")}')

    # ---- dive-phase progress -------------------------------------------
    rows = _ROW_RE.findall(text)
    m_total = _TOTAL_RE.search(text)
    total = int(m_total.group(1)) if m_total else (int(rows[-1][1]) if rows else 0)
    if total:
        n_done = len(rows)
        n_fail = sum(1 for r in rows if r[2] == 'FAIL')
        times = [float(r[4]) for r in rows]
        workers = live_workers()
        print()
        print(f'  {bold("dive re-renders")}  {dim("(replay blobs -> HTML, no sims)")}')
        bar_w = max(10, min(32, width - 28))
        frac = n_done / total
        fill = int(bar_w * frac)
        bar = green('#' * fill) + dim('-' * (bar_w - fill))
        print(f'  [{bar}] {bold(f"{n_done}/{total}")}  ({frac * 100:4.1f}%)')
        print('  ' + '   '.join([
            green(f'ok {n_done - n_fail}'),
            (red if n_fail else dim)(f'fail {n_fail}'),
            cyan(f'rendering {len(workers)}'),
            yellow(f'pending {max(0, total - n_done - len(workers))}'),
        ]))
        if workers:
            print(f'  {dim("now: " + ", ".join(sorted(workers)[:4]))}')
        if times and n_done < total and (alive and not complete):
            step1 = next((t for t, n in steps_seen
                          if n.startswith(STEP_ORDER[0])), None)
            if step1:
                elapsed = mtime - hms_to_today(step1, mtime)
                rate = n_done / elapsed if elapsed > 0 else 0
                if rate > 0:
                    eta_s = (total - n_done) / rate
                    print(f'  avg {sum(times) / len(times):.0f}s/blob   '
                          + eta_accent(f'dive phase ETA ~{eta_s / 60:.0f} min'))
        for r in rows:
            if r[2] == 'FAIL':
                print('  ' + red(f'FAIL {r[3]}'))

    # ---- ML tally + tail ------------------------------------------------
    m_ml = _ML_RE.search(text)
    if m_ml:
        ok, fail = int(m_ml.group(1)), int(m_ml.group(2))
        print()
        print(f'  {bold("ML guides")}: ' + green(f'{ok} ok')
              + ('   ' + red(f'{fail} FAILED') if fail else ''))
    if complete:
        print()
        print('  ' + green(bold('RENDER CHAIN COMPLETE -- ready for verify + publish')))
    rule(width)
    return 0


if __name__ == '__main__':
    sys.exit(main())
