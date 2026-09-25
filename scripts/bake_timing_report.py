#!/usr/bin/env python
"""How much of a bake runs parallel vs on a single core vs asleep.

Written 2026-09-10 to re-derive the TODO "dives run serially" numbers from a
COMPLETE chain log. The first pass at those numbers used a single cut point
per dive -- everything after the last "Running <moveset>..." line counted as
serial tail -- which OVERSTATES the serial share, because the mirror-slayer
rounds emit heavy parallel sim work ("Round 2: ... sims to run", "sim
progress: N/100 chunks") *after* that cut.

This classifies each inter-timestamp INTERVAL by the marker on the line that
opened it, so interleaved parallel and serial work is attributed correctly.
A line with no marker keeps the previous line's kind.

Ground truth for the two buckets, measured on the 2026-09-10 bake:
  * parallel -- 20-proc tree, summed 1626% CPU (~16.3 of 18 cores), 0% idle
  * serial   -- parent at 99-100% CPU, no workers alive
    (deep_dive_analysis.py and deep_dive_narrative.py contain no Pool /
    multiprocessing at all, so every phase they own is single-core)

2026-09-25 corrections (the 2026-09-20 bake read 21.9 h parallel / 15.5 h
serial here; per-dive attribution put it at 16.8 h parallel / 18.6 h serial
/ 1.8 h asleep):
  * Only the openers of a worker pool are parallel: "signature dedup" and the
    "progress:" lines of the sweep, "Round N: ... need sim" and "sim
    progress" of the slayer, and screening. The intervals opened by
    "N sims in", "sweep cache: h/n", "Running <moveset>...", "sim done in",
    "Replay state", "Split mode" and "Writing HTML" are parent-side
    single-core work (sweep setup, signature grouping, replay dump, page
    preamble) and used to inherit "parallel" from the line before.
  * A 'sleep' bucket. Slept time comes from `pmset -g log` (the default on
    macOS; --pmset-log reads a saved dump when the live log has rolled past
    the bake), subtracted from each interval it overlaps. Without a pmset
    log that covers the whole bake, any non-parallel interval longer than
    SLEEP_GAP_S is filed as sleep by heuristic: the longest awake serial
    interval on 2026-09-20 was ~80 s. The heuristic is a LOWER BOUND -- it
    misses sleep inside shorter intervals and inside pool phases -- and
    finds 1.38 h of that bake's 1.82 h.
  * The per-dive millisecond logs named by the chain log's "Log file:" lines
    are preferred when every one of them is still on disk; they carry full
    dates, so midnight and multi-day bakes need no guessing. The chain log
    (second-resolution [HH:MM:SS] stamps) is the fallback, and --chain-only
    forces it.

Usage:
    scripts/bake_timing_report.py [CHAIN_LOG]      # default: newest
        [--chain-only] [--pmset-log FILE | --no-pmset]
"""
import argparse
import datetime
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PARALLEL = re.compile(
    r'sim progress|progress: \d+/\d+ chunks|Round \d+: \d+ opponents \(|'
    r'Screening \d+|signature dedup|Screened in')
SERIAL = re.compile(
    r'Generating analysis|Rendering results|Analysis sections complete|'
    r'narrative|mirror-synth|Auto-derived|Synthesized|Rendering .* section|'
    r'[\d,]+ sims in |sweep cache:|Running .*\.\.\.|sim done in|'
    r'Replay state|Split mode|Writing HTML')
DIVE = re.compile(r'CLI: python scripts/deep_dive\.py (\S+(?: \([^)]*\))?)')
STAMP = re.compile(r'\[(\d\d):(\d\d):(\d\d)\]')
DIVE_STAMP = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})\]')
LOG_FILE = re.compile(r'Log file: (\S+\.log)')
CHAIN_NAME = re.compile(r'overnight_(\d{8})_\d{6}')

# Heuristic sleep cut, used only when no pmset data is available.
SLEEP_GAP_S = 600


def _kind(line):
    if PARALLEL.search(line):
        return 'parallel'
    if SERIAL.search(line):
        return 'serial'
    return None


class _Buckets:
    """Interval accumulator shared by the chain-log and per-dive paths."""

    def __init__(self, sleeps):
        self.sleeps = sleeps
        self.out = defaultdict(lambda: defaultdict(float))
        self.seen_keys = {}

    def key(self, line):
        d = DIVE.search(line)
        if not d:
            return None
        # Key on species + LEAGUE, not species alone. Keying on the name
        # collapsed a species' GL and UL dives into one summed row (81
        # rows for 135 dives on the 2026-09-10 bake). The totals stayed
        # correct -- every interval was still counted once -- but the
        # per-dive breakdown silently merged two different dives.
        lg = re.search(r'--league (\w+)', line)
        cur = f'{d.group(1)} [{lg.group(1)[:2]}]' if lg else d.group(1)
        # Same species+league can legitimately appear twice (a re-run, or
        # the split-moveset passes), so disambiguate rather than merge.
        if cur in self.seen_keys:
            self.seen_keys[cur] += 1
            cur = f'{cur}#{self.seen_keys[cur]}'
        else:
            self.seen_keys[cur] = 1
        return cur

    def add(self, dive, kind, t0, t1):
        dt = t1 - t0
        if dt <= 0:
            return
        if self.sleeps is None:
            if kind != 'parallel' and dt > SLEEP_GAP_S:
                self.out[dive]['sleep'] += dt
            else:
                self.out[dive][kind] += dt
            return
        from pmset_sleep import overlap_seconds
        slept = min(dt, overlap_seconds(self.sleeps, t0, t1))
        self.out[dive]['sleep'] += slept
        self.out[dive][kind] += dt - slept


def _walk(rows, acc, cur=None):
    """rows: (epoch_seconds, line). Each interval goes to its opener's kind."""
    prev_t, prev_kind = None, None
    for t, line in rows:
        if prev_t is not None and cur:
            acc.add(cur, prev_kind, prev_t, t)
        k = acc.key(line)
        if k:
            cur = k
        kind = _kind(line)
        if kind:
            prev_kind = kind
        prev_t = t
    return cur


def _chain_rows(path):
    """[HH:MM:SS] lines of a chain log as absolute epoch seconds.

    The stamps carry no date, so the date starts at the chain log's filename
    stamp (else 1970-01-01, which is fine for everything but pmset overlap)
    and rolls forward whenever the clock reads earlier than the line before.
    """
    m = CHAIN_NAME.search(Path(path).name)
    day = (datetime.datetime.strptime(m.group(1), '%Y%m%d') if m
           else datetime.datetime(1970, 1, 1))
    prev = None
    for line in Path(path).read_text(errors='replace').splitlines():
        s = STAMP.search(line)
        if not s:
            continue
        h, mi, se = (int(x) for x in s.groups())
        secs = h * 3600 + mi * 60 + se
        if prev is not None and secs < prev:
            day += datetime.timedelta(days=1)
        prev = secs
        yield (day + datetime.timedelta(seconds=secs)).timestamp(), line


def _dive_rows(path):
    for line in Path(path).read_text(errors='replace').splitlines():
        s = DIVE_STAMP.match(line)
        if s:
            t = datetime.datetime.strptime(s.group(1), '%Y-%m-%d %H:%M:%S.%f')
            yield t.timestamp(), line


def classify(path, sleeps=None):
    """Chain log -> {dive: {'parallel'|'serial'|'sleep'|None: seconds}}.

    ``sleeps`` is a list of pmset sleep windows (pmset_sleep); None means
    use the SLEEP_GAP_S heuristic instead.
    """
    acc = _Buckets(sleeps)
    _walk(_chain_rows(path), acc)
    return acc.out


def classify_dive_logs(paths, sleeps=None):
    """Per-dive millisecond logs -> the same shape as classify()."""
    acc = _Buckets(sleeps)
    for p in paths:
        _walk(_dive_rows(p), acc)
    return acc.out


def dive_logs(chain_log):
    """-> (existing, missing) per-dive log paths the chain log names."""
    seen = []
    for line in Path(chain_log).read_text(errors='replace').splitlines():
        m = LOG_FILE.search(line)
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    paths = [Path(p) for p in seen]
    return ([p for p in paths if p.exists()],
            [p for p in paths if not p.exists()])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('chain_log', nargs='?', type=Path)
    ap.add_argument('--chain-only', action='store_true',
                    help='classify the chain log even when per-dive logs '
                         'are available')
    src = ap.add_mutually_exclusive_group()
    src.add_argument('--pmset-log', type=Path,
                     help='saved `pmset -g log` dump to read sleep from')
    src.add_argument('--no-pmset', action='store_true',
                     help=f'heuristic sleep only (non-parallel gaps > '
                          f'{SLEEP_GAP_S}s)')
    args = ap.parse_args(argv)
    log = args.chain_log or max(
        (REPO / 'userdata/logs').glob('*/overnight_*.log'),
        key=lambda p: p.stat().st_mtime)

    sleeps = None
    sleep_src = (f'heuristic lower bound (non-parallel gaps > {SLEEP_GAP_S}s; '
                 f'misses shorter sleeps and sleep inside pool phases)')
    if not args.no_pmset:
        from pmset_sleep import parse_sleep_windows, read_pmset_log
        text = (args.pmset_log.read_text(errors='replace') if args.pmset_log
                else read_pmset_log())
        windows, first = parse_sleep_windows(text) if text else ([], None)
        start = _first_stamp(log)
        if first is None:
            sleep_src += ' -- no usable pmset log'
        elif start is not None and start < first:
            # A rolled-over log cannot vouch for the bake's early hours, and
            # reporting its partial sleep as the total would understate it.
            sleep_src += (f' -- the pmset log starts '
                          f'{datetime.datetime.fromtimestamp(first):%Y-%m-%d %H:%M}'
                          f', after this bake did')
        else:
            sleeps = windows
            sleep_src = f'pmset ({args.pmset_log or "pmset -g log"})'

    have, missing = ([], []) if args.chain_only else dive_logs(log)
    if have and not missing:
        data = classify_dive_logs(have, sleeps)
        source = f'{len(have)} per-dive logs'
    else:
        data = classify(log, sleeps)
        source = 'chain log (second-resolution stamps)'
        if missing:
            source += f'; {len(missing)} of {len(have) + len(missing)} per-dive logs missing'
    assert data, f'parsed 0 dives from {log} -- markers may have drifted'

    print(f'{log}\n  source: {source}\n  sleep:  {sleep_src}\n')
    print(f"{'dive':<34}{'parallel':>10}{'serial':>9}{'sleep':>8}"
          f"{'other':>8}{'serial%':>9}")
    tot = defaultdict(float)
    for dive, b in data.items():
        p, s, z, o = b['parallel'], b['serial'], b['sleep'], b[None]
        known = p + s
        for k, v in (('parallel', p), ('serial', s), ('sleep', z),
                     ('other', o)):
            tot[k] += v
        pct = f'{100 * s / known:.0f}%' if known else '--'
        print(f'{dive[:33]:<34}{p:>9.0f}s{s:>8.0f}s{z:>7.0f}s{o:>7.0f}s'
              f'{pct:>9}')

    known = tot['parallel'] + tot['serial']
    print(f'\n  {len(data)} dive(s); '
          f"parallel {tot['parallel'] / 3600:.2f}h, "
          f"serial {tot['serial'] / 3600:.2f}h, "
          f"sleep {tot['sleep'] / 3600:.2f}h, "
          f"unclassified {tot['other'] / 3600:.2f}h")
    if known:
        print(f"  SERIAL SHARE: {100 * tot['serial'] / known:.0f}% "
              f'of classified awake time')
    # Unclassified is reported, never hidden: a large bucket means the markers
    # drifted and the headline share is not trustworthy.
    everything = known + tot['other']
    share = tot['other'] / everything if everything else 0
    if share > 0.25:
        print(f'  WARNING: {100 * share:.0f}% unclassified -- markers likely '
              f'stale, treat the share above as unreliable')


def _first_stamp(chain_log):
    """Epoch of the chain's first dated line, or None."""
    for t, _line in _chain_rows(chain_log):
        return t
    return None


if __name__ == '__main__':
    main()
