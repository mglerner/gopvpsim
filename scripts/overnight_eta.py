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
  * Build a per-slug cold-timing table from PRIOR overnight logs (see
    _build_slug_timing_table): each slug's most-recent cold-chain time.
    This is the primary estimate for a not-yet-started dive -- a
    heavyweight (shadow-sableye ~49m) and a lightweight (mimikyu-busted
    ~4m) share the gl_full bucket but differ ~10x, so a per-species seed
    beats a bucket mean. Bucket means are used only for slugs the table
    has never seen.
  * Bucket dives by type: gl_full / ul_full / forretress -- the
    never-seen-slug fallback. Different buckets have very different
    runtimes (GL top-50 vs Forretress with top-movesets=1), so a global
    average would lie.
  * Parse completed dives from "[N/M] slug" banners paired with the
    following "Done in X.X min" marker.
  * For the currently-running dive, find its start timestamp from the
    next "[HH:MM:SS]" log line after the latest banner, subtract
    from now to get elapsed, then estimate remaining = est - elapsed
    (clamped >= 0), where est is the per-slug seed if known else bucket_avg.
  * For not-yet-started dives, use the per-slug seed if known, else
    bucket_avg of the classify() group.
  * Use fallback baselines when a bucket has no completed dives yet;
    these are loose approximations, sharpen as real completions arrive.
  * If the CURRENT run is itself a warm re-render (high cache-hit ratio),
    cold per-slug seeds don't apply -- disable them and lean on this run's
    own (fast) bucket means instead.
  * Add a fixed ~5 min allowance for the light post-dive steps
    (compare renders, matchup web, site index, link verify), PLUS a
    loose ML-bake allowance (step 7b, run_iv_guides.py, ~7h cold) until
    the chain enters that step -- it's the dominant tail, so omitting it
    made the whole-script ETA under-report by hours.

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
# data yet. Recalibrated 2026-06-28 from the 2026-06-25 cold overnight
# chain's 40 per-dive logs (overnight_20260625_021003.log) -- the prior
# 2026-04-20 baselines (gl 63 / ul 80 / forretress 25) were ~3-6x too
# high after the 2.0x engine-regression fix + cache-rework cut per-dive
# cold time, which made the launch-time ETA (44 dives x 63m) read ~52h
# when the real cold run lands ~16-20h. Measured cold means:
#
#   gl_full:    mean 10.2m, median 8.3m  (n=32)
#   ul_full:    mean 24.6m, median 22.3m (n=4)
#   forretress: mean  9.3m, median  9.1m (n=4)
#
# Rounded slightly up for headroom (cold dives, and this run's pool
# differs). These are only the cold-start guess; the estimator replaces
# each bucket with that run's own completed-dive mean as dives finish.
#
# Known misclassification: Aegislash Blade UL pins both --fast and
# --charged so only 1 moveset runs (~26min total), but classify() here
# puts it in ul_full. Bounded impact on the whole-script ETA; fix only
# if a future chain's Blade-like dive count grows. The summarizer's more
# precise taxonomy lives in scripts/summarize_perf.py.
FALLBACKS = {
    'gl_full':    11.0,
    'ul_full':    25.0,
    'forretress': 10.0,
    'post_dive':  5.0,   # comparison renders + matchup web + index + verify (steps 4-9, sans ML)
    # Step 7b: the run_iv_guides.py Master-league ML bake (~60 guides, serial /
    # all-cores-each). A ~7h cold tail per overnight_redive.sh's own header; the
    # single biggest post-dive cost, so omitting it made the whole-script ETA
    # under-report by hours. Loose fallback only -- once the bake STARTS,
    # chain_status.py shows the data-driven ML block (in_ml_phase) instead of
    # this line, so this number only ever covers the not-yet-reached ML step.
    'ml_tail':    420.0,
}


def classify(slug: str) -> str:
    if slug.startswith('forretress-'):
        return 'forretress'
    if slug.endswith('-ultra-league'):
        return 'ul_full'
    return 'gl_full'


# A run whose aggregate sweep-cache hit ratio exceeds this is a warm
# re-render, not a cold re-dive. Cold chains land ~0-38% (a fully-cold
# all-miss sweep prints NO cache line, so the ratio stays low even with
# some intra-chain sibling warming); warm re-renders land ~63-100%. 0.5
# sits in the empty gap between the two populations.
WARM_RUN_HIT_RATIO = 0.5

_CACHE_RE = re.compile(r'sweep cache:\s+(\d+)/(\d+) opponent columns hit')
_BANNER_RE = re.compile(r'\[(\d+)/(\d+)\]\s+([a-z-]+-(?:great|ultra|master)-league)')
_DONE_RE = re.compile(r'Done in ([\d.]+) min')


def _run_stamp(path: Path) -> str:
    """Sortable YYYYMMDD_HHMMSS from an overnight_*.log name.

    Sort by the filename stamp, NOT the path: the monthly subdir is
    unreliable (today's 20260628 log can be filed under 2026-04), so a
    path sort would order runs wrong across month dirs.
    """
    m = re.search(r'overnight_(\d{8}_\d{6})', path.name)
    return m.group(1) if m else ''


def _agg_hit_ratio(text: str) -> float | None:
    """Aggregate sweep-cache hit fraction across one run's log.

    None when the run emitted no cache lines at all -- either pre-cache-era
    or a fully-cold all-miss chain; both are 'cold' for our purposes.
    """
    hits = total = 0
    for m in _CACHE_RE.finditer(text):
        hits += int(m.group(1))
        total += int(m.group(2))
    return (hits / total) if total else None


def _build_slug_timing_table(current_log: Path) -> dict[str, float]:
    """Per-slug cold-dive timing (minutes); most-recent COLD-CHAIN run wins.

    Scans sibling overnight_*.log files (across monthly subdirs) and keeps,
    for each dive slug, its "Done in X min" time from the most recent
    cold-chain run. Warm re-render runs are skipped entirely (see
    WARM_RUN_HIT_RATIO) so a warm re-render of the whole pool can't
    under-seed the next cold chain. Within a cold run each dive's actual
    in-chain time is kept verbatim -- it already includes the real
    intra-chain sibling cache warming (e.g. shadow-altaria served partly
    from altaria's freshly-populated columns) that a future cold chain will
    also see, so it is the right predictor, not a fully-cold standalone time.

    The current run is excluded: its completed dives are read from its own
    banners (actual times), and the table only seeds not-yet-completed ones.
    """
    logs_root = current_log.parent.parent  # userdata/logs/<month> -> userdata/logs
    cur_resolved = current_log.resolve()
    table: dict[str, float] = {}
    files = sorted(logs_root.glob('20*/overnight_*.log'), key=_run_stamp)
    for f in files:
        if f.resolve() == cur_resolved:
            continue
        try:
            text = f.read_text(errors='replace')
        except OSError:
            continue
        ratio = _agg_hit_ratio(text)
        if ratio is not None and ratio > WARM_RUN_HIT_RATIO:
            continue  # warm re-render -- not a representative cold-dive time
        cur = None
        for line in text.splitlines():
            m = _BANNER_RE.search(line)
            if m:
                cur = m.group(3)
                continue
            m = _DONE_RE.search(line)
            if m and cur:
                table[cur] = float(m.group(1))
                cur = None
    return table


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
    banner_re = _BANNER_RE
    done_re = _DONE_RE

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

    # Per-slug cold-timing seeds (most-recent cold-chain run per slug).
    # Primary estimate for a not-yet-completed dive; the bucket mean is the
    # fallback only for slugs the table has never seen. Disabled when THIS
    # run is itself a warm re-render -- cold per-slug times would then
    # over-estimate, so lean on this run's own (fast) bucket means.
    cur_ratio = _agg_hit_ratio(text)
    if cur_ratio is not None and cur_ratio > WARM_RUN_HIT_RATIO:
        slug_table: dict[str, float] = {}
    else:
        slug_table = _build_slug_timing_table(log_path)

    # Sum remaining dive time: current dive gets (est - elapsed), other
    # not-yet-started dives get full est (per-slug seed, else bucket_avg).
    # Track current-dive remaining separately so we can surface it as its
    # own line, and count how many remaining dives are per-slug-seeded.
    total_remaining_min = 0.0
    current_dive_remaining: float | None = None
    current_dive_overshoot: bool = False
    n_slug_seeded = 0
    for slug in slugs:
        if slug in completed:
            continue
        seed = slug_table.get(slug)
        if seed is not None:
            est = seed
            n_slug_seeded += 1
        else:
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

    # Fixed post-dive-pipeline allowance (comparison renders + matchup web +
    # index + link verify).
    total_remaining_min += FALLBACKS['post_dive']

    # ML IV-guide bake (step 7b) -- the dominant tail. Add it until the chain
    # actually enters it; once 'ML IV guides' appears in the wrapper log we're
    # in/past the bake (all dives done), and chain_status.py shows the
    # data-driven ML block instead of this SCRIPT line, so adding it then would
    # double-count. Guarded so standalone overnight_eta runs stay honest too.
    ml_started = 'ML IV guides' in text
    ml_tail_min = 0.0 if ml_started else FALLBACKS['ml_tail']
    total_remaining_min += ml_tail_min

    now = datetime.now()
    eta_str = _fmt_minutes(total_remaining_min)
    done_str = (now + timedelta(minutes=total_remaining_min)).strftime('%H:%M')

    n_done = len(completed)
    n_total = len(slugs)

    n_remaining = n_total - n_done
    bucket_bits = [f'slug-seed {n_slug_seeded}/{n_remaining} remaining']
    for b in ('gl_full', 'ul_full', 'forretress'):
        bucket_bits.append(f'{b}={bucket_avg[b]:.0f}m ({bucket_source[b]})')
    if ml_tail_min:
        bucket_bits.append(f'ml_tail={ml_tail_min:.0f}m (fallback)')

    ml_note = ' (incl. ~ML tail)' if ml_tail_min else ''
    print(f'SCRIPT: ~{eta_str} remaining{ml_note}, done ~{done_str}')
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
