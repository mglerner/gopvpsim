#!/usr/bin/env python
"""Re-render dive HTML from saved replay blobs (no re-sim), then clear the
publish gate.

When a RENDER-side fix lands after a chain has already simmed (e.g. the
2026-06-25 card pole-dominance fix in generate_analysis_sections), the dives
shipped with the old renderer. Their HTML must be rebuilt -- but the sim data
is unchanged, so we replay each dive's saved userdata/replay/*.replay.pkl.gz
blob in place (to its original html_path via scripts/replay_analysis.py). No
re-simming; minutes, not hours.

This also clears the publish gate sentinel
(userdata/.cards_rerender_pending) on a fully-successful run, so
scripts/publish_website.sh stops refusing to publish.

Usage:
  python scripts/rerender_dive_cards.py                # blobs from the last 24h
  python scripts/rerender_dive_cards.py --since-hours 18
  python scripts/rerender_dive_cards.py --jobs 8       # parallel renders
  python scripts/rerender_dive_cards.py --dry-run      # list, don't render

Run it AFTER the overnight chain finishes (when the cores are free).
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from glob import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPLAY_GLOB = os.path.join(ROOT, 'userdata', 'replay', '*.replay.pkl.gz')
REPLAY_SCRIPT = os.path.join(ROOT, 'scripts', 'replay_analysis.py')
SENTINEL = os.path.join(ROOT, 'userdata', '.cards_rerender_pending')
PY = sys.executable


def _one(blob):
    """Replay a single blob in place (to its baked html_path)."""
    t0 = time.time()
    r = subprocess.run([PY, REPLAY_SCRIPT, blob],
                       cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0
    msg = '' if ok else (r.stderr.strip().splitlines() or ['exit %d' % r.returncode])[-1]
    return os.path.basename(blob), ok, msg, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since-hours', type=float, default=24.0,
                    help='only replay blobs modified within this many hours '
                         '(default 24 -- covers one overnight run)')
    ap.add_argument('--jobs', type=int, default=4,
                    help='concurrent renders (default 4)')
    ap.add_argument('--dry-run', action='store_true',
                    help='list the blobs that would be replayed, do nothing')
    a = ap.parse_args()

    cutoff = time.time() - a.since_hours * 3600
    # Ascending mtime so that if two blobs map to the same dive (a species
    # re-run within the window), the later one is rendered last and wins.
    blobs = sorted((p for p in glob(REPLAY_GLOB) if os.path.getmtime(p) >= cutoff),
                   key=os.path.getmtime)
    if not blobs:
        print(f'No replay blobs newer than {a.since_hours}h in '
              f'{os.path.dirname(REPLAY_GLOB)}.')
        return 0

    print(f'{len(blobs)} blob(s) within {a.since_hours}h to re-render '
          f'({a.jobs}-wide):', flush=True)
    for b in blobs:
        print(f'  {os.path.basename(b)}')
    if a.dry_run:
        print('\n(dry run -- nothing rendered, sentinel left in place)')
        return 0

    t0, results = time.time(), []
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = {ex.submit(_one, b): b for b in blobs}
        for n, fut in enumerate(as_completed(futs), 1):
            name, ok, msg, dt = fut.result()
            tag = 'OK  ' if ok else 'FAIL'
            print(f'[{n}/{len(blobs)}] {tag} {name} ({dt:.1f}s)'
                  + (f'  {msg}' if not ok else ''), flush=True)
            results.append((name, ok, msg))

    bad = [r for r in results if not r[1]]
    print(f'\nDone in {(time.time() - t0) / 60:.1f} min: '
          f'{len(results) - len(bad)} ok, {len(bad)} failed.')
    for name, _, msg in bad:
        print(f'  FAILED {name}: {msg}')

    if bad:
        print('\nSentinel NOT cleared (some renders failed). Fix and re-run.')
        return 1
    if os.path.exists(SENTINEL):
        os.remove(SENTINEL)
        print(f'\nCleared publish gate ({os.path.relpath(SENTINEL, ROOT)}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
