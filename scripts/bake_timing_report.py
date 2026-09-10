#!/usr/bin/env python
"""How much of a bake runs parallel vs on a single core.

Written 2026-09-10 to re-derive the TODO "dives run serially" numbers from a
COMPLETE chain log. The first pass at those numbers used a single cut point
per dive -- everything after the last "Running <moveset>..." line counted as
serial tail -- which OVERSTATES the serial share, because the mirror-slayer
rounds emit heavy parallel sim work ("Round 2: ... sims to run", "sim
progress: N/100 chunks") *after* that cut.

This classifies each inter-timestamp INTERVAL by the marker on the line that
opened it, so interleaved parallel and serial work is attributed correctly.

Ground truth for the two buckets, measured on the 2026-09-10 bake:
  * parallel -- 20-proc tree, summed 1626% CPU (~16.3 of 18 cores), 0% idle
  * serial   -- parent at 99-100% CPU, no workers alive
    (deep_dive_analysis.py and deep_dive_narrative.py contain no Pool /
    multiprocessing at all, so every phase they own is single-core)

Usage:
    scripts/bake_timing_report.py [CHAIN_LOG]      # default: newest
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PARALLEL = re.compile(
    r'sim progress|sims in|Round \d+:|Screening \d+|signature dedup|'
    r'sweep cache|Screened in')
SERIAL = re.compile(
    r'Generating analysis|Rendering results|Analysis sections complete|'
    r'narrative|mirror-synth|Auto-derived|Synthesized|Rendering .* section')
DIVE = re.compile(r'CLI: python scripts/deep_dive\.py (\S+(?: \([^)]*\))?)')
STAMP = re.compile(r'\[(\d\d):(\d\d):(\d\d)\]')


def _secs(m):
    h, mi, s = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + s


def classify(path):
    """-> {dive: {'parallel': s, 'serial': s, 'other': s}} in wall-clock seconds."""
    out = defaultdict(lambda: defaultdict(float))
    cur, prev_t, prev_kind = None, None, None
    for line in Path(path).read_text(errors='replace').splitlines():
        m = STAMP.search(line)
        if not m:
            continue
        t = _secs(m)
        if prev_t is not None and cur and t >= prev_t:
            dt = t - prev_t
            # A midnight rollover would read as a huge negative jump; the
            # guard above drops it rather than poisoning the totals.
            if dt < 3600:
                out[cur][prev_kind] += dt
        d = DIVE.search(line)
        if d:
            cur = d.group(1)
        kind = ('parallel' if PARALLEL.search(line)
                else 'serial' if SERIAL.search(line) else None)
        if kind:
            prev_kind = kind
        prev_t = t
    return out


def main():
    log = (Path(sys.argv[1]) if len(sys.argv) > 1 else
           max((REPO / 'userdata/logs').glob('*/overnight_*.log'),
               key=lambda p: p.stat().st_mtime))
    data = classify(log)
    assert data, f'parsed 0 dives from {log} -- markers may have drifted'

    print(f'{log}\n')
    print(f"{'dive':<30}{'parallel':>10}{'serial':>9}{'other':>8}{'serial%':>9}")
    tot = defaultdict(float)
    for dive, b in data.items():
        p, s, o = b['parallel'], b['serial'], b[None]
        known = p + s
        for k, v in (('parallel', p), ('serial', s), ('other', o)):
            tot[k] += v
        pct = f'{100 * s / known:.0f}%' if known else '--'
        print(f'{dive[:29]:<30}{p:>9.0f}s{s:>8.0f}s{o:>7.0f}s{pct:>9}')

    known = tot['parallel'] + tot['serial']
    print(f'\n  {len(data)} dive(s); '
          f"parallel {tot['parallel'] / 3600:.1f}h, "
          f"serial {tot['serial'] / 3600:.1f}h, "
          f"unclassified {tot['other'] / 3600:.1f}h")
    if known:
        print(f"  SERIAL SHARE: {100 * tot['serial'] / known:.0f}% "
              f'of classified time')
    # Unclassified is reported, never hidden: a large bucket means the markers
    # drifted and the headline share is not trustworthy.
    share = tot['other'] / (known + tot['other']) if (known + tot['other']) else 0
    if share > 0.25:
        print(f'  WARNING: {100 * share:.0f}% unclassified -- markers likely '
              f'stale, treat the share above as unreliable')


if __name__ == '__main__':
    main()
