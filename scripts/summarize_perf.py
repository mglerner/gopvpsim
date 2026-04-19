#!/usr/bin/env python3
"""Summarize per-dive perf from per-dive deep_dive.py logs.

Walks the given log directory (default: userdata/logs/2026-04/),
pulls the CLI header for species/league/shadow, parses phase-boundary
markers ("X,XXX,XXX sims in Y.Ys (Z sims/s)") and the coarse banner
structure (Phase N [i/k], Interactive sweep [i/k], Mirror slayer
iteration round [i/k]), and emits two markdown tables to stdout:

  1. Per-dive summary: species, league, shadow, total elapsed, total
     sims, aggregate throughput, bucket classification (gl_full /
     ul_full / forretress / aegislash_gl_pinned), wall-clock start.

  2. Per-phase breakdown: species+league, phase label, sims, seconds,
     sims/s, cumulative-elapsed within the dive.

Also prints a "fallback baseline recommendation" section: bucket-level
averages of total elapsed, to feed straight back into
scripts/overnight_eta.py's FALLBACKS dict. My initial calibration of
40m/35m/6m was ad-hoc (eyeballed mid-flight on dive 1); real chain
numbers want to land here as the new defaults.

Usage:
    python scripts/summarize_perf.py
    python scripts/summarize_perf.py --log-dir userdata/logs/2026-04
    python scripts/summarize_perf.py --since 20260419_170000

The `--since` filter matches the timestamp prefix of the log
filename (YYYYMMDD_HHMMSS), so pass the overnight chain's start time
to exclude older ad-hoc logs that predate the chain.

Output: stdout is markdown, intended for either piping to a
checked-in perf doc (docs/perf/*.md) or scan-in-terminal review.
Nothing is written to disk by this script.
"""
from __future__ import annotations

import argparse
import re
import shlex
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Matches the CLI line one of the first lines of every per-dive log:
# "[YYYY-MM-DD HH:MM:SS.msec] INFO    deep_dive: CLI: python scripts/deep_dive.py ..."
# Captured group 1 is the whole shell-quoted argv tail; we split it with
# shlex to get the positional species name (which may contain spaces,
# e.g. "Oinkologne (Female)") and the flag flags.
CLI_RE = re.compile(r'CLI: python scripts/deep_dive\.py\s+(.+)$')
TS_RE = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[.\d]*\]')
PHASE_BANNER_RE = re.compile(
    r'(Phase \d+ \[\d+/\d+\][^:]*:?\s*.*?|'
    r'Interactive sweep \[\d+/\d+\][^(]*\(.*?\)|'
    r'Mirror slayer iteration.*?round \d+/\d+)',
    re.IGNORECASE,
)
SIMS_COMPLETE_RE = re.compile(
    r'([\d,]+) sims in ([\d.]+)s \(([\d,]+) sims/s\)'
)


def _classify_bucket(species: str, league: str, shadow: bool,
                     pins_fast: bool, pins_charged: bool,
                     top_movesets: int) -> str:
    """Bucket classifier matching overnight_eta.py::classify().

    Three axes that drive dive runtime, in order of impact:
      1. top_movesets × (--fast/--charged pins): if the effective
         moveset count is 1 (either top_movesets=1 OR both fast AND
         charged are pinned), the dive does a single interactive
         sweep instead of 5. ~5x runtime difference.
      2. League-tied opponent pool size (UL 60 opps vs GL 65 +
         shared pool). Second-order.
      3. species name mostly cosmetic, but Forretress was set up as
         a CS-meta pinned dive and gets its own bucket so the ETA
         math can treat it differently from ad-hoc single-moveset
         runs.

    The overnight_eta.py classifier currently uses just (species,
    league) which is why Aegislash Blade UL (pinned) landed in the
    same ul_full bucket as Aegislash Shield UL (5 movesets),
    skewing the UL mean.
    """
    effective_movesets = 1 if (pins_fast and pins_charged) else top_movesets
    if species.lower().startswith('forretress') and effective_movesets == 1:
        return 'forretress_cs'
    if effective_movesets == 1:
        return f'{league[:2]}_pinned'
    if league == 'ultra':
        return 'ul_full'
    return 'gl_full'


def _fmt_minutes(total_sec: float) -> str:
    if total_sec < 60:
        return f'{total_sec:.0f}s'
    m = int(total_sec // 60)
    s = int(total_sec % 60)
    return f'{m}m{s:02d}s'


def _parse_one_log(path: Path) -> Optional[dict]:
    """Parse a single per-dive log. Returns dive-summary dict or None."""
    try:
        text = path.read_text(errors='replace')
    except OSError:
        return None
    lines = text.splitlines()
    if not lines:
        return None

    # CLI header: shlex-split the whole argv tail so quoted species
    # names (e.g. "Oinkologne (Female)") parse as one token.
    cli_species = None
    cli_league = 'great'
    cli_shadow = False
    pins_fast = False
    pins_charged = False
    top_movesets = 5
    for line in lines[:20]:
        m = CLI_RE.search(line)
        if m:
            try:
                tokens = shlex.split(m.group(1))
            except ValueError:
                tokens = m.group(1).split()
            # First non-flag token is the positional species arg.
            for t in tokens:
                if not t.startswith('-'):
                    cli_species = t
                    break
            # Flag parsing: --flag VALUE or --flag=VALUE pairs.
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok in ('--league',) and i + 1 < len(tokens):
                    cli_league = tokens[i + 1]
                elif tok.startswith('--league='):
                    cli_league = tok.split('=', 1)[1]
                elif tok == '--shadow':
                    cli_shadow = True
                elif tok == '--fast':
                    pins_fast = True
                elif tok == '--charged':
                    pins_charged = True
                elif tok in ('--top-movesets',) and i + 1 < len(tokens):
                    try:
                        top_movesets = int(tokens[i + 1])
                    except ValueError:
                        pass
                elif tok.startswith('--top-movesets='):
                    try:
                        top_movesets = int(tok.split('=', 1)[1])
                    except ValueError:
                        pass
                i += 1
            break
    if cli_species is None:
        return None

    # First/last timestamp for total elapsed
    first_ts = None
    last_ts = None
    for line in lines:
        m = TS_RE.match(line)
        if m:
            first_ts = m.group(1)
            break
    for line in reversed(lines):
        m = TS_RE.match(line)
        if m:
            last_ts = m.group(1)
            break
    if not first_ts or not last_ts:
        return None
    try:
        t0 = datetime.strptime(first_ts, '%Y-%m-%d %H:%M:%S')
        t1 = datetime.strptime(last_ts, '%Y-%m-%d %H:%M:%S')
        total_sec = (t1 - t0).total_seconds()
    except ValueError:
        return None

    # Phase-boundary table — pair each "sims in Xs" with the most recent
    # banner line preceding it.
    phases: list[dict] = []
    current_banner = None
    total_sims = 0
    for line in lines:
        bm = PHASE_BANNER_RE.search(line)
        if bm:
            current_banner = bm.group(1).strip()
        sm = SIMS_COMPLETE_RE.search(line)
        if sm and current_banner:
            sims = int(sm.group(1).replace(',', ''))
            elapsed = float(sm.group(2))
            rate = int(sm.group(3).replace(',', ''))
            phases.append({
                'banner': current_banner,
                'sims': sims,
                'elapsed_s': elapsed,
                'rate': rate,
            })
            total_sims += sims

    bucket = _classify_bucket(cli_species, cli_league, cli_shadow,
                              pins_fast, pins_charged, top_movesets)
    aggregate_rate = int(total_sims / total_sec) if total_sec > 0 else 0

    return {
        'log_path': path,
        'species': cli_species,
        'league': cli_league,
        'shadow': cli_shadow,
        'bucket': bucket,
        'start_ts': first_ts,
        'end_ts': last_ts,
        'total_sec': total_sec,
        'total_sims': total_sims,
        'aggregate_rate': aggregate_rate,
        'phases': phases,
    }


def _collect_logs(log_dir: Path, since: Optional[str]) -> list[Path]:
    """Collect per-dive log files (skip overnight_ wrapper logs)."""
    out = []
    for p in sorted(log_dir.glob('*.log')):
        name = p.name
        if name.startswith('overnight_'):
            continue
        if since:
            ts_prefix = name.split('_', 2)[:2]
            if len(ts_prefix) == 2:
                ts_candidate = '_'.join(ts_prefix)
                if ts_candidate < since:
                    continue
        out.append(p)
    return out


def _render_summary(dives: list[dict]) -> str:
    parts = ['## Per-dive summary', '']
    parts.append(
        '| Start ts          | Species                | League | Sh | Bucket       | Total elapsed | Total sims     | Aggregate sims/s |'
    )
    parts.append(
        '| ----------------- | ---------------------- | ------ | -- | ------------ | ------------- | -------------- | ---------------- |'
    )
    for d in dives:
        sh = '✓' if d['shadow'] else ' '
        parts.append(
            f"| {d['start_ts']} | {d['species']:<22} | {d['league']:<6} | {sh}  | {d['bucket']:<12} | "
            f"{_fmt_minutes(d['total_sec']):<13} | {d['total_sims']:>14,} | {d['aggregate_rate']:>16,} |"
        )
    return '\n'.join(parts)


def _render_fallback_recommendations(dives: list[dict]) -> str:
    buckets: dict[str, list[float]] = defaultdict(list)
    for d in dives:
        buckets[d['bucket']].append(d['total_sec'])
    parts = ['## Fallback baseline recommendations', '',
             'Averages of per-dive total elapsed, by bucket. Plug these '
             'into `scripts/overnight_eta.py::FALLBACKS` as the new '
             'defaults (replacing the ad-hoc 40/35/6 guess).', '']
    parts.append('| Bucket       | N | Mean minutes | Median minutes | Min minutes | Max minutes |')
    parts.append('| ------------ | - | ------------ | -------------- | ----------- | ----------- |')
    for bucket in sorted(buckets):
        vals = sorted(buckets[bucket])
        n = len(vals)
        mean = sum(vals) / n / 60
        median = vals[n // 2] / 60
        vmin = vals[0] / 60
        vmax = vals[-1] / 60
        parts.append(
            f'| {bucket:<12} | {n} | {mean:>12.1f} | {median:>14.1f} | {vmin:>11.1f} | {vmax:>11.1f} |'
        )
    return '\n'.join(parts)


def _render_phase_breakdown(dives: list[dict], top_n: int = 5) -> str:
    """Per-phase breakdown for each dive (top N slowest phases each)."""
    parts = ['## Per-phase breakdown (slowest-first per dive)', '']
    for d in dives:
        label = f"{d['species']} ({d['league']}{'/Shadow' if d['shadow'] else ''})"
        parts.append(f'### {label}')
        parts.append('')
        if not d['phases']:
            parts.append('No phase markers parsed.')
            parts.append('')
            continue
        phases = sorted(d['phases'], key=lambda p: -p['elapsed_s'])[:top_n]
        parts.append('| Phase                                                            | Sims       | Elapsed | Sims/s |')
        parts.append('| ---------------------------------------------------------------- | ---------- | ------- | ------ |')
        for ph in phases:
            banner = ph['banner'][:64]
            parts.append(
                f'| {banner:<64} | {ph["sims"]:>10,} | {_fmt_minutes(ph["elapsed_s"]):>7} | {ph["rate"]:>6,} |'
            )
        parts.append('')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--log-dir', default='userdata/logs/2026-04',
                        help='Directory of per-dive logs (default: userdata/logs/2026-04)')
    parser.add_argument('--since', default=None,
                        help='Only include logs with filename timestamp >= this (YYYYMMDD_HHMMSS)')
    parser.add_argument('--top-phases', type=int, default=5,
                        help='Slowest-N phases to show per dive (default: 5)')
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.exists():
        sys.exit(f'log-dir not found: {log_dir}')

    paths = _collect_logs(log_dir, args.since)
    if not paths:
        sys.exit(f'No per-dive logs found in {log_dir}' +
                 (f' matching --since {args.since}' if args.since else ''))

    dives = []
    for p in paths:
        parsed = _parse_one_log(p)
        if parsed is not None:
            dives.append(parsed)

    if not dives:
        sys.exit('No parseable per-dive logs found.')

    print(f'# deep_dive.py perf summary ({len(dives)} dive log(s))')
    print()
    print(f'Source: `{log_dir}`')
    if args.since:
        print(f'Filter: `--since {args.since}`')
    print()
    print(_render_summary(dives))
    print()
    print(_render_fallback_recommendations(dives))
    print()
    print(_render_phase_breakdown(dives, top_n=args.top_phases))


if __name__ == '__main__':
    main()
