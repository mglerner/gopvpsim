#!/usr/bin/env python
"""Batch-generate XehrFelrose-style ML IV guides for a pool of species.

Each guide is one ``iv_envelope_analysis.py --all-shields`` run (single-process,
~one core, tens of minutes) followed by a fast ``render_iv_envelope_article.py``
call. Because each dive uses exactly one core, several can run at once and still
leave cores free: concurrency defaults to (physical cores - --reserve), honoring
the project policy of keeping a CPU free for interactive work. This is the
reserve-aware analogue of deep_dive.py's --reserve-cpus, lifted to the
cross-species level (the analysis script itself has no internal worker pool).

Usage:
  python scripts/run_iv_guides.py                       # whole master_top60 pool
  python scripts/run_iv_guides.py --species "Metagross" "Kyogre"
  python scripts/run_iv_guides.py --jobs 4 --reserve 1
  python scripts/run_iv_guides.py --skip-existing       # skip already-built guides
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.join(ROOT, 'scripts', 'iv_envelope_analysis.py')
RENDER = os.path.join(ROOT, 'scripts', 'render_iv_envelope_article.py')
DEFAULT_POOL = os.path.join(ROOT, 'opponent_pools', 'master_top60.txt')
PY = sys.executable


def physical_cores():
    """Physical (not hyperthread) core count, so we don't oversubscribe the
    CPU-bound sims. sysctl on macOS; os.cpu_count() elsewhere as a fallback."""
    if sys.platform == 'darwin':
        try:
            return int(subprocess.check_output(
                ['sysctl', '-n', 'hw.physicalcpu']).strip())
        except Exception:
            pass
    return os.cpu_count() or 2


def json_slug(species):
    return species.lower().replace(' ', '_').replace('(', '').replace(')', '')


def article_slug(species):
    return species.lower().replace(' ', '-').replace('(', '').replace(')', '')


def read_pool(path):
    species = []
    with open(path) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            # Tolerate inline pool overrides ("Species | fast=...") -> just the name.
            species.append(line.split('|', 1)[0].strip())
    return species


def _last_err(proc):
    err = (proc.stderr or '').strip()
    return err.splitlines()[-1] if err else f'exit {proc.returncode}'


def run_one(species):
    json_path = os.path.join(
        'userdata', 'dives', f'{json_slug(species)}_iv_envelope_all9.json')
    t0 = time.time()
    a = subprocess.run([PY, ANALYSIS, '--all-shields', species],
                       cwd=ROOT, capture_output=True, text=True)
    if a.returncode != 0:
        return species, False, f'analysis failed: {_last_err(a)}', time.time() - t0
    r = subprocess.run([PY, RENDER, json_path],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return species, False, f'render failed: {_last_err(r)}', time.time() - t0
    return species, True, f'{article_slug(species)}-ml-iv-guide', time.time() - t0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pool', default=DEFAULT_POOL,
                    help='opponent-pool file listing the species (default: master_top60)')
    ap.add_argument('--species', nargs='*',
                    help='explicit species list (overrides --pool)')
    ap.add_argument('--reserve', type=int, default=1,
                    help='physical cores to leave free (default 1)')
    ap.add_argument('--jobs', type=int, default=None,
                    help='max concurrent dives (default: physical cores - reserve)')
    ap.add_argument('--skip-existing', action='store_true',
                    help='skip species whose article dir already exists')
    a = ap.parse_args()

    species = a.species if a.species else read_pool(a.pool)
    if a.skip_existing:
        kept = []
        for s in species:
            d = os.path.join(ROOT, 'userdata', 'website', 'articles',
                             f'{article_slug(s)}-ml-iv-guide')
            (print(f'skip (exists): {s}') if os.path.isdir(d) else kept.append(s))
        species = kept

    cores = physical_cores()
    jobs = a.jobs if a.jobs is not None else max(1, cores - a.reserve)
    print(f'Detected {cores} physical cores; reserving {a.reserve}; '
          f'running up to {jobs} concurrent dives.')
    print(f'{len(species)} species to generate.\n', flush=True)
    if not species:
        return

    results, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(run_one, s): s for s in species}
        for n, fut in enumerate(as_completed(futs), 1):
            sp, ok, info, dt = fut.result()
            print(f'[{n}/{len(species)}] {"OK  " if ok else "FAIL"} '
                  f'{sp} ({dt / 60:.1f} min) {info}', flush=True)
            results.append((sp, ok, info))

    bad = [r for r in results if not r[1]]
    print(f'\nDone in {(time.time() - t0) / 60:.1f} min: '
          f'{len(results) - len(bad)} ok, {len(bad)} failed.')
    for sp, _, info in bad:
        print(f'  FAILED {sp}: {info}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
