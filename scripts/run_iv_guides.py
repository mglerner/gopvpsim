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
import pathlib
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.join(ROOT, 'scripts', 'iv_envelope_analysis.py')
RENDER = os.path.join(ROOT, 'scripts', 'render_iv_envelope_article.py')
INDEX = os.path.join(ROOT, 'scripts', 'build_website_index.py')
DEFAULT_POOL = os.path.join(ROOT, 'opponent_pools', 'master_top60.txt')
PY = sys.executable

# Untradeable mythical / Routes-only mons whose real IRL IV floor is the
# 10/10/10 research/raid-reward minimum, NOT the 12/12/12 lucky-trade floor the
# sweep otherwise assumes. These are swept at floor 10 automatically so a
# legitimately-owned sub-12 spread is evaluable (e.g. an 11/13/11 Marshadow).
# Eternatus is included regardless of its trade status: Michael's call
# (2026-06-27) is that it is rare enough to count as special / one-per-account
# in practice, so the 10/10/10 research floor is the right one. Names must
# match the pool entries verbatim.
FLOOR_10_SPECIES = frozenset({
    'Marshadow',
    'Meloetta (Aria)',
    'Jirachi',
    'Keldeo (Ordinary)',
    'Keldeo (Resolute)',
    'Zygarde (Complete Forme)',
    'Eternatus',
})
DEFAULT_IV_FLOOR = 12


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


def run_one(species, iv_floor=DEFAULT_IV_FLOOR):
    json_path = os.path.join(
        'userdata', 'dives', f'{json_slug(species)}_iv_envelope_all9.json')
    t0 = time.time()
    floor_args = [] if iv_floor == DEFAULT_IV_FLOOR else ['--iv-floor', str(iv_floor)]
    # Drop any stale per-guide log so iv_guides_status.py / chain_status.py read
    # only THIS run's phase lines. iv_envelope_analysis's init_logger re-creates
    # the dir/file (it appends, so a leftover log from a prior run would
    # otherwise show an out-of-date "current phase").
    pathlib.Path(ROOT, 'userdata', 'logs', 'iv_guides',
                 f'{json_slug(species)}.log').unlink(missing_ok=True)
    a = subprocess.run([PY, ANALYSIS, '--all-shields', *floor_args, species],
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
    ap.add_argument('--no-index-refresh', action='store_true',
                    help='do not rebuild the website index after each guide')
    ap.add_argument('--iv-floor', type=int, default=DEFAULT_IV_FLOOR,
                    help='default per-stat IV floor for ALL species (default '
                         f'{DEFAULT_IV_FLOOR}). The FLOOR_10_SPECIES set is '
                         'always swept at 10 regardless of this.')
    a = ap.parse_args()

    def floor_for(sp):
        # Limited-availability mythicals: their real floor (10) wins even when
        # the run default is 12, so a plain full bake corrects them in one pass.
        return 10 if sp in FLOOR_10_SPECIES else a.iv_floor

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
    print(f'{len(species)} species to generate.', flush=True)
    floor10 = [s for s in species if s in FLOOR_10_SPECIES]
    if floor10:
        print(f'Sweeping at the 10/10/10 floor (limited-availability): '
              f'{", ".join(floor10)}', flush=True)
    print(flush=True)
    if not species:
        return

    results, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(run_one, s, floor_for(s)): s for s in species}
        for n, fut in enumerate(as_completed(futs), 1):
            sp, ok, info, dt = fut.result()
            floor_tag = ' [floor 10]' if sp in FLOOR_10_SPECIES else ''
            print(f'[{n}/{len(species)}] {"OK  " if ok else "FAIL"} '
                  f'{sp}{floor_tag} ({dt / 60:.1f} min) {info}', flush=True)
            results.append((sp, ok, info))
            # Refresh the website index as each new guide lands. This loop runs
            # in the main thread, so the rebuilds are serialized (no race on
            # index.html) even though the dives ran concurrently.
            if ok and not a.no_index_refresh:
                subprocess.run([PY, INDEX], cwd=ROOT, capture_output=True)

    bad = [r for r in results if not r[1]]
    print(f'\nDone in {(time.time() - t0) / 60:.1f} min: '
          f'{len(results) - len(bad)} ok, {len(bad)} failed.')
    for sp, _, info in bad:
        print(f'  FAILED {sp}: {info}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
