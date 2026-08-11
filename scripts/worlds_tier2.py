#!/usr/bin/env python
"""Worlds 2026 Tier-2 bake: full joint outcome grids for amber pairs.

Plan: docs/worlds_prep_plan.md ("Tier 2 -- joint grids"). For each
IV-decided (amber) pair, both directions x both bait modes, the FULL
grid: every focal IV spread (all 4096, iv_rank order) x the opponent
cohort (top-512 SP union attack band, Tier-1's exact cohort) x 9 shield
scenarios. Worklist is usage-ranked with a HARD wall-clock budget --
pairs not reached are recorded as ``deferred`` in the manifest and the
amber pages print them, never silently omit them.

Storage: ``worlds/planes/tier2/*.npz`` (COMPRESSED -- a raw uint16
score grid is ~38MB per direction-bait; np.savez_compressed brings the
pair family into the low GB) with its OWN manifest + stamps. The
Tier-2 producer stamp (``tier2_code_hash``) is deliberately separate
from worlds_planes._WORLDS_SOURCE_FILES: adding this file to the
Tier-1 producer tuple would stale the 1,860-plane Tier-1 manifest for
no reason.

Guardrails inherited from the Tier-1 driver (worlds_bake): sweep-cache
poison, engine-cleanliness preflight, moveset legality, non-memoized
mid-bake engine digest, stamp-mismatch refusal, npz-first/manifest-
second write ordering.

``--clean-sample N`` additionally bakes N seeded-random NON-amber
pairs, tagged ``clean_sample`` in the manifest -- the inputs for the
amber screen's measured false-negative rate (plan: "MEASURED ... and
printed").
"""
import argparse
import hashlib
import multiprocessing
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

import worlds_planes as wp
import worlds_bake as wb
import worlds_render_data as wrd
from worlds_tier2_worker import tier2_task_worker  # noqa: F401

TIER2_DIR = wp.PLANES_DIR / 'tier2'
TIER2_SCHEMA = 1

_TIER2_SOURCE_FILES = (
    REPO / 'scripts' / 'worlds_tier2_worker.py',
    REPO / 'scripts' / 'deep_dive_lib' / 'robustness.py',
    REPO / 'scripts' / 'deep_dive_lib' / 'sweep.py',
    REPO / 'scripts' / 'deep_dive_signature.py',
)


def tier2_code_hash():
    h = hashlib.md5()
    for p in _TIER2_SOURCE_FILES:
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def fresh_stamps():
    base = wp.fresh_stamps()
    return {'schema': TIER2_SCHEMA, 'mechanics': base['mechanics'],
            'engine': base['engine'], 'gamemaster': base['gamemaster'],
            'tier2_code': tier2_code_hash()}


STAMP_KEYS = ('schema', 'mechanics', 'engine', 'gamemaster', 'tier2_code')


def stamp_mismatches(manifest):
    cur = fresh_stamps()
    return [(k, manifest.get(k), cur[k])
            for k in STAMP_KEYS if manifest.get(k) != cur[k]]


def plane_filename(focal_id, opp_id, bait):
    return f'{focal_id}__vs__{opp_id}__{"bait" if bait else "nobait"}__t2.npz'


def load_manifest(tier2_dir=TIER2_DIR):
    p = wp.out_path('manifest.json', tier2_dir)
    if not p.exists():
        return None
    import json
    return json.loads(p.read_text())


def save_manifest(manifest, tier2_dir=TIER2_DIR):
    Path(tier2_dir).mkdir(parents=True, exist_ok=True)
    from sweep_cache import write_sidecar
    write_sidecar(wp.out_path('manifest.json', tier2_dir), manifest)


def write_grid(name, arrs, tier2_dir=TIER2_DIR):
    """Atomic COMPRESSED npz write through the guarded path constructor
    (cache_base.write_planes is uncompressed; Tier-2 grids need the
    compression, so this is a sibling with the same tmp+replace)."""
    path = wp.out_path(name, tier2_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'wb') as f:
        np.savez_compressed(f, **arrs)
    os.replace(tmp, path)


def read_grid(name, tier2_dir=TIER2_DIR):
    path = wp.out_path(name, tier2_dir)
    if not path.exists():
        return None
    try:
        with np.load(path) as z:
            raw = {k: z[k] for k in z.files}
    except Exception:
        return None
    raw['won'] = wp.unpack_won(raw['won_packed'], tuple(raw['won_shape']))
    return raw


def amber_worklist(entries, cells=None):
    """Usage-ranked unordered amber pairs [(rank_key, (id_a, id_b)),...]
    from the Tier-1 planes. Rank = max recent usage of the two entries
    (ties: combined usage), descending."""
    if cells is None:
        cells = wrd.build_all_cells(entries)
    n_missing, missing = wrd.coverage_check(cells, entries)
    if n_missing:
        sys.exit(f'ABORT: Tier-1 planes incomplete ({n_missing} missing) -- '
                 'bake Tier 1 before Tier 2')
    usage = {e['species_id']: e['usage_recent_pct'] for e in entries}
    pairs = sorted({tuple(sorted(k)) for k, c in cells.items()
                    if not c.missing and c.amber})
    ranked = sorted(pairs, key=lambda p: (max(usage[p[0]], usage[p[1]]),
                                          usage[p[0]] + usage[p[1]]),
                    reverse=True)
    return ranked, cells


def clean_sample(entries, cells, n, seed=20260810):
    """Seeded sample of NON-amber pairs for the FN-rate measurement."""
    clean = sorted({tuple(sorted(k)) for k, c in cells.items()
                    if not c.missing and not c.amber})
    rng = random.Random(seed)
    return sorted(rng.sample(clean, min(n, len(clean))))


def pair_tasks(pair, resolved):
    """The 4 (direction, bait) tasks for one unordered pair."""
    a, b = pair
    tasks = []
    for focal_id, opp_id in ((a, b), (b, a)):
        f, o = resolved[focal_id], resolved[opp_id]
        union, t_mask, a_mask = o['cohort']
        for bait in (True, False):
            tasks.append({
                'key': wp.pair_key(focal_id, opp_id, bait),
                'file': plane_filename(focal_id, opp_id, bait),
                'focal_species': f['entry']['species'],
                'focal_fast': f['moveset'][0],
                'focal_charged': f['moveset'][1],
                'focal_shadow': f['entry']['shadow'],
                'opponent': o['entry']['species'],
                'opp_fast': o['moveset'][0],
                'opp_charged': o['moveset'][1],
                'opp_shadow': o['entry']['shadow'],
                'league': 'great',
                'scenarios': list(wb.SCENARIOS),
                'cohort': union,
                'top512_mask': t_mask,
                'atkband_mask': a_mask,
                'bait': bait,
            })
    return tasks


def bake(budget_minutes, workers, clean_n=0, pair_limit=None, dry_run=False,
         tier2_dir=TIER2_DIR):
    entries = wb.load_meta()
    wb.preflight_moveset_legality(entries)
    ranked_pairs, cells = amber_worklist(entries)
    sample = clean_sample(entries, cells, clean_n) if clean_n else []
    # Clean-sample pairs bake FIRST: the FN measurement is small, fixed
    # size, and the budget must not silently starve it behind 401 amber
    # pairs.
    worklist = [(p, True) for p in sample] + [(p, False) for p in ranked_pairs]
    if pair_limit is not None:
        worklist = worklist[:pair_limit]

    manifest = load_manifest(tier2_dir)
    if manifest is None:
        manifest = {**fresh_stamps(), 'created': date.today().isoformat(),
                    'entries': {}, 'deferred': []}
    else:
        mism = stamp_mismatches(manifest)
        if mism:
            sys.exit('ABORT: tier2 manifest stamp mismatch (single vintage '
                     f'by design): {mism}. Delete {tier2_dir} to start '
                     'fresh.')

    resolved = {e['species_id']: {
        'entry': e, 'moveset': wb.resolve_moveset(e),
        'cohort': wb.cohort_indices(e['species'], e['shadow'])}
        for e in entries}

    def baked_ok(key):
        ent = manifest['entries'].get(key)
        return ent is not None and wp.out_path(ent['file'],
                                               tier2_dir).exists()

    todo = []
    for pair, is_clean in worklist:
        tasks = [t for t in pair_tasks(pair, resolved)
                 if not baked_ok(t['key'])]
        if tasks:
            todo.append((pair, is_clean, tasks))
    print(f'Tier-2 worklist: {len(ranked_pairs)} amber pairs + '
          f'{len(sample)} clean-sample; {len(todo)} pairs need baking '
          f'({sum(len(t) for _, _, t in todo)} grids), budget '
          f'{budget_minutes} min, {workers} workers.')
    if dry_run or not todo:
        return

    start = time.time()
    start_digest = wb.fresh_engine_digest()
    done_grids = 0
    total_sims = 0
    with multiprocessing.Pool(workers) as pool:
        # Task-level admission + OUT-OF-ORDER harvest. The original loop
        # blocked on the OLDEST pair's results in admission order, so one
        # slow (Aegislash-family) pair idled every other worker behind it
        # -- observed live 2026-08-10: 3 of 16 workers busy. Admission
        # stays pair-atomic (a budget cutoff never half-admits a pair);
        # harvest is per-GRID as results become ready (idempotent-safe:
        # is_baked keys per grid, so a partially-harvested pair simply
        # re-bakes its missing grids on rerun).
        inflight = []         # [(task, is_clean, async_result)]
        it = iter(todo)
        exhausted = False
        window_tasks = workers + 4
        while inflight or not exhausted:
            while not exhausted and len(inflight) < window_tasks:
                if (time.time() - start) / 60 > budget_minutes:
                    exhausted = True
                    break
                try:
                    pair, is_clean, tasks = next(it)
                except StopIteration:
                    exhausted = True
                    break
                inflight.extend(
                    (t, is_clean, pool.apply_async(tier2_task_worker, (t,)))
                    for t in tasks)
            ready = [x for x in inflight if x[2].ready()]
            if not ready:
                time.sleep(1.0)
                continue
            for entry in ready:
                inflight.remove(entry)
                t, is_clean, ar = entry
                arrs, n_sims = ar.get()
                write_grid(t['file'], arrs, tier2_dir)
                manifest['entries'][t['key']] = {
                    'file': t['file'],
                    'won_shape': [int(x) for x in arrs['won_shape']],
                    'n_sims': int(n_sims),
                    'clean_sample': bool(is_clean),
                    'baked': date.today().isoformat(),
                }
                total_sims += n_sims
                done_grids += 1
                el = (time.time() - start) / 60
                print(f'  [{done_grids}] {t["key"]}'
                      f'{" (clean)" if is_clean else ""} '
                      f'({n_sims} sims), {el:.1f} min elapsed')
            save_manifest(manifest, tier2_dir)
    # Deferred = worklist pairs still not fully baked (recomputed, not
    # tracked incrementally, so a re-run shrinks it naturally).
    manifest['deferred'] = [
        list(pair) for pair, _is_clean in worklist
        if any(not baked_ok(t['key'])
               for t in pair_tasks(pair, resolved))]
    save_manifest(manifest, tier2_dir)
    dt = time.time() - start
    print(f'Baked {done_grids} grids, {total_sims} sims in {dt / 60:.1f} min '
          f'({total_sims / max(dt, 1):.0f} sims/s); '
          f'{len(manifest["deferred"])} pairs deferred.')
    if wb.fresh_engine_digest() != start_digest:
        sys.exit('ABORT: engine sources changed MID-BAKE -- tier2 grids '
                 'written this run are mixed-vintage; delete them.')


def main():
    ap = argparse.ArgumentParser(description='Worlds Tier-2 joint-grid bake')
    ap.add_argument('--budget-minutes', type=float, default=360.0,
                    help='hard wall-clock admission budget (default 6h)')
    ap.add_argument('--workers', type=int,
                    default=max(1, multiprocessing.cpu_count() - 2))
    ap.add_argument('--clean-sample', type=int, default=0,
                    help='also bake N seeded non-amber pairs (FN-rate '
                         'inputs); they bake FIRST')
    ap.add_argument('--pair-limit', type=int, default=None,
                    help='cap the worklist (smoke)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    wb.install_sweep_cache_poison()
    wb.preflight_engine_clean()
    bake(args.budget_minutes, args.workers, clean_n=args.clean_sample,
         pair_limit=args.pair_limit, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
