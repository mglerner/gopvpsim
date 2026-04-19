#!/usr/bin/env python3
"""Compute whole-script ETA for the overnight re-dive chain.

Reads the overnight wrapper log (argv[1]) and emits two stdout lines:
  line 1: "~{HhMm} remaining, done ~{HH:MM}"
  line 2: "{n_done}/{n_total} dives complete; {bucket_avgs}"

Intended to be called from scripts/overnight_status.sh so the pinned
status box carries a whole-script ETA alongside per-dive progress.

Method:
  * Enumerate all dive slugs in chain order from run_website_dives.py's
    "Found N dive(s) to run:" block at the top of the wrapper log.
  * Bucket dives by type: gl_full / ul_full / forretress. Different
    buckets have very different runtimes (GL top-50 vs Forretress with
    top-movesets=1), so a global average would lie.
  * Parse completed dives from "[N/M] slug" banners paired with the
    following "Done in X.X min" marker.
  * For the currently-running dive, find its start timestamp from the
    next "[HH:MM:SS]" log line after the latest banner, subtract
    from now to get elapsed, then estimate remaining = bucket_avg -
    elapsed (clamped >= 0).
  * For not-yet-started dives, use bucket_avg of the classify() group.
  * Use fallback baselines when a bucket has no completed dives yet;
    these are loose approximations, sharpen as real completions arrive.
  * Add a fixed ~5 min allowance for post-dive steps 2-10 of
    overnight_redive.sh (patch anchors, article gen, compare renders,
    Aegislash narrative drafts, site index, link verify).

Silent if the wrapper log can't be parsed or no dives have been
enumerated yet — exits 0 with no output so the shell caller can skip
the ETA line.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Loose fallback baselines (minutes) for when a bucket has no completed
# data yet. Calibrated from observation of dive 1 in progress: Phase 2
# (5 movesets × ~2min), Interactive sweep (5 movesets × several IV/
# bait/shield sub-sweeps × ~2min each), mirror-slayer (4 rounds × sub-
# sweeps). Real completions overwrite these quickly; these numbers just
# keep the ETA from collapsing below reality before any dive completes.
FALLBACKS = {
    'gl_full':    40.0,  # Oinkologne M/F, Tinkaton GL: top-50 + mirror-slayer + all sub-axes
    'ul_full':    35.0,  # Tinkaton UL, Aegislash Blade/Shield UL: 60 opps, similar scale
    'forretress': 6.0,   # CS top-32 pool, top-movesets=1, much faster
    'post_dive':  5.0,   # total for steps 2-10 of overnight_redive.sh
}


def classify(slug: str) -> str:
    if slug.startswith('forretress-'):
        return 'forretress'
    if slug.endswith('-ultra-league'):
        return 'ul_full'
    return 'gl_full'


def _fmt_minutes(total_min: float) -> str:
    total_min = max(0.0, total_min)
    hours = int(total_min // 60)
    mins = int(total_min % 60)
    if hours > 0:
        return f'{hours}h{mins:02d}m'
    return f'{mins}m'


def main(wrapper_log_path: str) -> int:
    log_path = Path(wrapper_log_path)
    if not log_path.exists():
        return 0
    text = log_path.read_text()

    # Enumerate all dive slugs in chain order from the "Found N dive(s)" block.
    slugs = re.findall(
        r'^\s*-\s+([a-z-]+-(?:great|ultra|master)-league)\s*$',
        text, re.MULTILINE,
    )
    if not slugs:
        return 0

    # Pair each "[N/M] slug" banner with the next "Done in X min" marker
    # to determine which dives completed and how long each took.
    completed: dict[str, float] = {}
    banner_re = re.compile(
        r'\[(\d+)/(\d+)\]\s+([a-z-]+-(?:great|ultra|master)-league)'
    )
    done_re = re.compile(r'Done in ([\d.]+) min')

    current_slug = None
    for line in text.splitlines():
        m = banner_re.search(line)
        if m:
            current_slug = m.group(3)
            continue
        m = done_re.search(line)
        if m and current_slug:
            completed[current_slug] = float(m.group(1))
            current_slug = None

    # Latest banner in the log = currently-running dive (unless its
    # "Done in X min" has already landed, in which case we're between
    # dives or past the dive block entirely).
    all_banners = list(banner_re.finditer(text))
    current_dive = None
    current_start: datetime | None = None
    if all_banners:
        last_banner = all_banners[-1]
        last_slug = last_banner.group(3)
        if last_slug not in completed:
            current_dive = last_slug
            # Find the next "[HH:MM:SS] ..." log line after the banner —
            # that's this dive's start timestamp.
            after = text[last_banner.end():]
            ts_match = re.search(r'\[(\d{2}):(\d{2}):(\d{2})\]', after)
            if ts_match:
                now = datetime.now()
                h, mi, s = map(int, ts_match.groups())
                candidate = now.replace(hour=h, minute=mi, second=s, microsecond=0)
                # Handle "ran past midnight" by subtracting a day if needed.
                if candidate > now:
                    candidate -= timedelta(days=1)
                current_start = candidate

    # Bucket averages from completed dives; fall back to fixed baselines.
    buckets: dict[str, list[float]] = {'gl_full': [], 'ul_full': [], 'forretress': []}
    for slug, mins in completed.items():
        buckets[classify(slug)].append(mins)

    bucket_avg: dict[str, float] = {}
    bucket_source: dict[str, str] = {}
    for b, vals in buckets.items():
        if vals:
            bucket_avg[b] = sum(vals) / len(vals)
            bucket_source[b] = f'n={len(vals)}'
        else:
            bucket_avg[b] = FALLBACKS[b]
            bucket_source[b] = 'fallback'

    # Sum remaining dive time: current dive gets (avg - elapsed), other
    # not-yet-started dives get full bucket_avg.
    total_remaining_min = 0.0
    for slug in slugs:
        if slug in completed:
            continue
        est = bucket_avg[classify(slug)]
        if slug == current_dive and current_start is not None:
            elapsed_min = (datetime.now() - current_start).total_seconds() / 60
            total_remaining_min += max(0.0, est - elapsed_min)
        else:
            total_remaining_min += est

    # Fixed post-dive-pipeline allowance.
    total_remaining_min += FALLBACKS['post_dive']

    eta_str = _fmt_minutes(total_remaining_min)
    done_at = datetime.now() + timedelta(minutes=total_remaining_min)
    done_str = done_at.strftime('%H:%M')

    n_done = len(completed)
    n_total = len(slugs)

    bucket_bits = []
    for b in ('gl_full', 'ul_full', 'forretress'):
        bucket_bits.append(f'{b}={bucket_avg[b]:.0f}m ({bucket_source[b]})')

    print(f'~{eta_str} remaining, done ~{done_str}')
    print(f'{n_done}/{n_total} dives complete; ' + ', '.join(bucket_bits))
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(0)
    sys.exit(main(sys.argv[1]))
