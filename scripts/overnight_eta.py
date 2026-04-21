#!/usr/bin/env python3
"""Compute whole-script ETA for the overnight re-dive chain.

Reads the overnight wrapper log (argv[1]) and emits up to three tagged
stdout lines:

  SCRIPT: ~{HhMm} remaining, done ~{HH:MM}
  DIVE: ~{HhMm} remaining, done ~{HH:MM}         (only when a dive is running)
  BUCKETS: {n_done}/{n_total} dives complete; {bucket_avgs}

Tags let the shell caller grep each independently without position
coupling. DIVE is suppressed when there is no currently-running dive
(chain hasn't started, or we're between dives / past the dive block).

Intended to be called from scripts/chain_status.py so the pinned
status box carries both a whole-script ETA and a current-dive ETA
alongside per-dive progress.

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

# Fallback baselines (minutes) for when a bucket has no completed
# data yet. Recalibrated 2026-04-20 from scripts/summarize_perf.py
# output against the 2026-04-19 overnight chain's 10 per-dive logs:
#
#   gl_full:       median 62.7m across 3 dives (Oink M/F, Tink GL)
#   ul_full:       mean 76.2m across 2 dives (Tink UL, Aegis Shield UL)
#   forretress_cs: median 25.3m across 4 dives (skips the 47m Bug Bite
#                  outlier which appears throughput-limited, not
#                  structural)
#
# Known misclassification: Aegislash Blade UL pins both --fast and
# --charged so only 1 moveset runs (~26min total), but classify() here
# puts it in ul_full (expects ~76m). Net effect: overestimates Blade
# UL's remaining time by ~50min when Blade is the current dive. Bounded
# impact on the whole-script ETA; fix only if a future chain's Blade-
# like dive count grows. The summarizer's more precise taxonomy
# (ul_pinned / forretress_cs / etc.) lives in scripts/summarize_perf.py
# because it has access to the CLI flags via the logs, which
# classify() here doesn't.
FALLBACKS = {
    'gl_full':    63.0,
    'ul_full':    76.0,
    'forretress': 25.0,
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
    # not-yet-started dives get full bucket_avg. Track current-dive
    # remaining separately so we can surface it as its own line.
    total_remaining_min = 0.0
    current_dive_remaining: float | None = None
    current_dive_overshoot: bool = False
    for slug in slugs:
        if slug in completed:
            continue
        est = bucket_avg[classify(slug)]
        if slug == current_dive and current_start is not None:
            elapsed_min = (datetime.now() - current_start).total_seconds() / 60
            if elapsed_min >= est:
                # We've exceeded the baseline; "0m remaining" is
                # misleading because the dive is clearly not about to
                # finish. Flag overshoot so the caller can show a
                # hedged signal instead of a false-precision number.
                current_dive_overshoot = True
                current_dive_remaining = 0.0
            else:
                current_dive_remaining = est - elapsed_min
            total_remaining_min += current_dive_remaining
        else:
            total_remaining_min += est

    # Fixed post-dive-pipeline allowance.
    total_remaining_min += FALLBACKS['post_dive']

    now = datetime.now()
    eta_str = _fmt_minutes(total_remaining_min)
    done_str = (now + timedelta(minutes=total_remaining_min)).strftime('%H:%M')

    n_done = len(completed)
    n_total = len(slugs)

    bucket_bits = []
    for b in ('gl_full', 'ul_full', 'forretress'):
        bucket_bits.append(f'{b}={bucket_avg[b]:.0f}m ({bucket_source[b]})')

    print(f'SCRIPT: ~{eta_str} remaining, done ~{done_str}')
    if current_dive_remaining is not None:
        if current_dive_overshoot:
            # Past the baseline -- don't claim a number we don't
            # have. Show how far past, and note the baseline will
            # recalibrate once this dive completes.
            elapsed_min = (now - current_start).total_seconds() / 60
            print(f'DIVE: running long ({_fmt_minutes(elapsed_min)} elapsed vs '
                  f'{_fmt_minutes(bucket_avg[classify(current_dive)])} baseline)')
        else:
            dive_eta_str = _fmt_minutes(current_dive_remaining)
            dive_done_str = (now + timedelta(minutes=current_dive_remaining)).strftime('%H:%M')
            print(f'DIVE: ~{dive_eta_str} remaining, done ~{dive_done_str}')
    print(f'BUCKETS: {n_done}/{n_total} dives complete; ' + ', '.join(bucket_bits))
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(0)
    sys.exit(main(sys.argv[1]))
