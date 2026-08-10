#!/usr/bin/env python
"""Worlds 2026 Tier-1 bake driver: idempotent, manifest-driven, guarded.

Plan: docs/worlds_prep_plan.md. Bakes the (pair, direction, bait-mode)
outcome planes into ``worlds/planes/`` -- 2 focal probe spreads (rank-1
SP + max-atk-within-top-512) x opponent cohort (top-512 SP union
best-SP-per-atk-IV) x 9 shield scenarios, legacy engine, signature
dedup -- and only for keys missing from the manifest, so a late meta
add re-bakes exactly the new pairs.

Sequencing note (TODO.md "Worlds 2026"): the pending behavior-neutral
engine-hash batch must land BEFORE the first real bake, or wait until
after Worlds -- the manifest records the engine hash at first bake and
every later bake must match or be refused (--rebake-all is the only
deletion path). There is deliberately NO "did that batch land?" check
here: the driver cannot distinguish that commit from any other, so the
enforced invariant is single-vintage planes + a clean engine tree.

Guardrails as code (the {layer} x {lens} rule; tests:
tests/test_worlds_bake_guards.py):

* the sweep cache is POISONED before any sim -- any code path that
  reaches SweepCache.get_column/put_column raises instead of
  overwriting trusted GL columns in place. NB macOS pools spawn fresh
  children that do NOT inherit the poison; that is fine because
  put_column only ever runs in the parent (deep_dive_lib/sweep.py), and
  the worker (deep_dive_lib.robustness.plane_task_worker) has no cache
  code at all -- do not "fix" the poison into the workers;
* engine cleanliness: git-porcelain over the engine-hash file set must
  be clean, and a NON-memoized engine digest is compared before/after
  the bake (sweep_cache.engine_hash() memoizes per process, so calling
  it twice can never detect a mid-bake edit);
* every meta moveset id is validated against the species' legal
  gamemaster pool first -- make_battle_pokemon has no legality guard,
  and an Aegislash form-move mixup builds a plausible-looking inverted
  monster instead of crashing (2026-08-10 audit);
* stamp mismatches REFUSE (worlds_planes.stamp_mismatches); charged-move
  order follows the shipped dive (get_default_moveset order) whenever
  the chosen set equals the default set, because meta.toml's sorted ids
  are an alphabetization artifact and slot order is PvPoke-visible for
  equal-energy moves.
"""
import argparse
import hashlib
import itertools
import multiprocessing
import subprocess
import sys
import time
import tomllib
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

from gopvpsim.data import get_default_moveset
from gopvpsim.pokemon import iv_rank, find_pokemon_entry

import worlds_planes as wp
from deep_dive_lib.robustness import plane_task_worker

SCENARIOS = [(sf, so) for sf in range(3) for so in range(3)]
TOP_K = 512

# The engine-cleanliness file set: the sweep-cache engine hash inputs
# (src files + deep_dive_signature.py -- see sweep_cache._ENGINE_FILES).
ENGINE_TREE = ('src/gopvpsim', 'scripts/deep_dive_signature.py')
_ENGINE_SRC_FILES = ('battle.py', '_dp_jit.py', 'moves.py', 'formchange.py',
                     'pokemon.py')


def fresh_engine_digest():
    """Re-reads the engine sources on EVERY call (sweep_cache.engine_hash
    is memoized per process and would report the start value forever)."""
    h = hashlib.md5()
    for name in _ENGINE_SRC_FILES:
        h.update((REPO / 'src' / 'gopvpsim' / name).read_bytes())
    sig = REPO / 'scripts' / 'deep_dive_signature.py'
    if sig.exists():
        h.update(sig.read_bytes())
    return h.hexdigest()


def install_sweep_cache_poison():
    """Make any sweep-cache read/write raise. put_column's internal
    try/except is its BODY -- replacing the method means the raise
    propagates to the caller (verified in the guards audit)."""
    import sweep_cache as swc

    def _forbidden(*_a, **_k):
        raise RuntimeError(
            'Worlds bake must never touch the sweep disk cache '
            '(put_column overwrites trusted GL columns in place)')

    swc.SweepCache.put_column = _forbidden
    swc.SweepCache.get_column = _forbidden


def preflight_engine_clean(allow_dirty=False):
    out = subprocess.run(
        ['git', 'status', '--porcelain', '--', *ENGINE_TREE],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    dirty = [ln for ln in out.splitlines() if ln.strip()]
    print(f'Engine-cleanliness preflight: {len(dirty)} dirty path(s) '
          f'under the engine set.')
    if dirty and not allow_dirty:
        sys.exit('ABORT: engine tree is dirty -- a WIP engine edit must not '
                 'be baked into Worlds planes (and an engine-hash bump '
                 'stales the GL sweep cache; see TODO.md sequencing). '
                 'Commit/stash first, or pass --allow-dirty-engine.\n'
                 + '\n'.join(dirty))


def legal_move_ids(entry_name):
    mon = find_pokemon_entry(entry_name)
    if mon is None:
        return None, None
    fast = set(mon.get('fastMoves') or []) | set(mon.get('eliteMoves') or [])
    charged = (set(mon.get('chargedMoves') or [])
               | set(mon.get('eliteMoves') or []))
    return fast, charged


def preflight_moveset_legality(entries):
    """Every meta moveset id must be in the species' legal gamemaster
    pool. make_battle_pokemon builds ANY id it can look up, and the
    Aegislash form-move mixup is silent, not a crash."""
    errors = []
    for e in entries:
        fast, charged = legal_move_ids(e['name'])
        if fast is None:
            errors.append(f"{e['name']}: not in the gamemaster")
            continue
        if e['fast_move_id'] not in fast:
            errors.append(f"{e['name']}: fast {e['fast_move_id']} not in "
                          f"legal pool {sorted(fast)}")
        for cid in e['charged_move_ids']:
            if cid not in charged:
                errors.append(f"{e['name']}: charged {cid} not legal")
    if errors:
        sys.exit('ABORT: meta moveset fails gamemaster legality:\n'
                 + '\n'.join(errors))


def resolve_moveset(entry):
    """(fast_id, charged_ids) in DIVE order: meta.toml sorts charged ids
    (an alphabetization artifact); whenever the chosen set equals the
    PvPoke default set, use the default's order so the planes are
    slot-for-slot comparable with the shipped dives and the oracle
    harness (charged slot order is PvPoke-visible for equal-energy
    moves -- Aegislash's SHADOW_BALL/GYRO_BALL both cost 50)."""
    fast = entry['fast_move_id']
    charged = list(entry['charged_move_ids'])
    try:
        d_fast, d_charged = get_default_moveset(
            entry['species'], 'great', shadow=entry['shadow'])
    except Exception:
        return fast, charged
    if fast == d_fast and sorted(charged) == sorted(d_charged):
        return d_fast, list(d_charged)
    return fast, charged


def load_meta():
    meta = tomllib.load(open(wp.META_TOML, 'rb'))
    return meta['entries']


def probe_spreads(species, shadow):
    """Tier-1 focal probe spreads: rank-1 SP + max-atk within top-512
    (the session-1 go/no-go probe's convention)."""
    ranked = iv_rank(species, league='great', shadow=shadow)
    top = ranked[:TOP_K]
    r1 = top[0]
    maxatk = max(top, key=lambda e: e['atk'])
    return [(r1['atk_iv'], r1['def_iv'], r1['sta_iv']),
            (maxatk['atk_iv'], maxatk['def_iv'], maxatk['sta_iv'])]


def cohort_indices(species, shadow):
    """(union_indices, top512_mask, atkband_mask) over the union rows.

    top-512 by SP, union best-SP-per-atk-IV (breakpoint-chasers run
    off-SP spreads; sweeping only top-512-SP would miss exactly the
    spreads this analysis is about). Masks label each union row's
    cohort membership for the renderers."""
    ranked = iv_rank(species, league='great', shadow=shadow)
    top512 = list(range(min(TOP_K, len(ranked))))
    byatk, seen = [], set()
    for i, e in enumerate(ranked):
        if e['atk_iv'] not in seen:
            seen.add(e['atk_iv'])
            byatk.append(i)
        if len(seen) == 16:
            break
    union = sorted(set(top512) | set(byatk))
    t_set, a_set = set(top512), set(byatk)
    return (union,
            [i in t_set for i in union],
            [i in a_set for i in union])


def build_tasks(entries, manifest, planes_dir, k=TOP_K, scenarios=SCENARIOS,
                pair_limit=None):
    """The missing-from-manifest worklist. Each task is one
    (pair, direction, bait) plane -- plane_task_worker's input shape --
    tagged with its manifest key and filename."""
    resolved = {}
    for e in entries:
        resolved[e['species_id']] = {
            'entry': e,
            'moveset': resolve_moveset(e),
            'spreads': None,        # filled lazily below
            'cohort': None,
        }
    tasks = []
    pairs = list(itertools.combinations(entries, 2))
    if pair_limit is not None:
        pairs = pairs[:pair_limit]
    for a, b in pairs:
        for focal, opp in ((a, b), (b, a)):
            f = resolved[focal['species_id']]
            o = resolved[opp['species_id']]
            for bait in (True, False):
                key = wp.pair_key(focal['species_id'], opp['species_id'], bait)
                if wp.is_baked(manifest, key, planes_dir):
                    continue
                if f['spreads'] is None:
                    f['spreads'] = probe_spreads(focal['species'],
                                                 focal['shadow'])
                if o['cohort'] is None:
                    o['cohort'] = cohort_indices(opp['species'],
                                                 opp['shadow'])
                union, t_mask, a_mask = o['cohort']
                tasks.append({
                    'key': key,
                    'file': wp.plane_filename(focal['species_id'],
                                              opp['species_id'], bait),
                    'focal_species': focal['species'],
                    'focal_fast': f['moveset'][0],
                    'focal_charged': f['moveset'][1],
                    'focal_shadow': focal['shadow'],
                    'focal_spreads': f['spreads'],
                    'opponent': opp['species'],
                    'opp_fast': o['moveset'][0],
                    'opp_charged': o['moveset'][1],
                    'opp_shadow': opp['shadow'],
                    'league': 'great',
                    'scenarios': list(scenarios),
                    'cohort': union[:k] if k != TOP_K else union,
                    'top512_mask': t_mask[:k] if k != TOP_K else t_mask,
                    'atkband_mask': a_mask[:k] if k != TOP_K else a_mask,
                    'bait': bait,
                })
    return tasks


def _finish_task(task, result, manifest, planes_dir):
    """npz first, manifest entry second (worlds_planes ordering
    contract), then persist the manifest."""
    won, score, n_sims = result
    ranked = iv_rank(task['opponent'], league='great',
                     shadow=task['opp_shadow'])
    cohort_entries = [ranked[i] for i in task['cohort']]
    focal_ranked = iv_rank(task['focal_species'], league='great',
                           shadow=task['focal_shadow'])
    lvl = {(e['atk_iv'], e['def_iv'], e['sta_iv']): e['level']
           for e in focal_ranked}
    arrs = wp.plane_arrays(
        won, score,
        focal_ivs=task['focal_spreads'],
        focal_levels=[lvl[tuple(s)] for s in task['focal_spreads']],
        opp_ivs=[(e['atk_iv'], e['def_iv'], e['sta_iv'])
                 for e in cohort_entries],
        opp_levels=[e['level'] for e in cohort_entries],
        scenarios=task['scenarios'],
        top512_mask=task['top512_mask'],
        atkband_mask=task['atkband_mask'])
    wp.write_plane(task['file'], arrs, planes_dir)
    manifest['entries'][task['key']] = {
        'file': task['file'],
        'won_shape': list(won.shape),
        'n_sims': int(n_sims),
        'content_md5': wp.content_md5(arrs),
        'focal_tags': ['rank1', 'maxatk512'],
        'baked': date.today().isoformat(),
    }
    wp.save_manifest(manifest, planes_dir)


def bake(entries, planes_dir=wp.PLANES_DIR, k=TOP_K, scenarios=SCENARIOS,
         pair_limit=None, workers=0, rebake_all=False, dry_run=False):
    """The guarded bake. Returns (n_baked, n_skipped)."""
    manifest = wp.load_manifest(planes_dir)
    if manifest is not None and rebake_all:
        for entry in manifest.get('entries', {}).values():
            p = wp.out_path(entry['file'], planes_dir)
            if p.exists():
                p.unlink()
        manifest = None
    if manifest is None:
        manifest = {**wp.fresh_stamps(), 'created': date.today().isoformat(),
                    'entries': {}}
    else:
        mismatches = wp.stamp_mismatches(manifest)
        if mismatches:
            lines = [f'  {k}: manifest {a!r} != current {b!r}'
                     for k, a, b in mismatches]
            sys.exit('ABORT: manifest stamp mismatch -- Worlds planes are a '
                     'single vintage by design (docs/worlds_prep_plan.md '
                     'Guardrails). Re-run with --rebake-all to DELETE '
                     'worlds/planes/*.npz and start a fresh manifest.\n'
                     + '\n'.join(lines))

    total_keys = len(wp.expected_tier1_keys(entries)) if pair_limit is None \
        else None
    tasks = build_tasks(entries, manifest, planes_dir, k=k,
                        scenarios=scenarios, pair_limit=pair_limit)
    n_skipped = (len(manifest['entries'])
                 if manifest['entries'] else 0)
    print(f'Worklist: {len(tasks)} planes to bake, '
          f'{n_skipped} already in the manifest'
          + (f' (target {total_keys} keys).' if total_keys else '.'))
    if dry_run or not tasks:
        return 0, n_skipped

    start_digest = fresh_engine_digest()
    t0 = time.time()
    baked = 0
    sims = 0
    if workers and workers > 1:
        with multiprocessing.Pool(workers) as pool:
            for task, result in zip(
                    tasks, pool.imap(plane_task_worker, tasks)):
                _finish_task(task, result, manifest, planes_dir)
                baked += 1
                sims += result[2]
                print(f'  [{baked}/{len(tasks)}] {task["key"]} '
                      f'({result[2]} sims)')
    else:
        for task in tasks:
            result = plane_task_worker(task)
            _finish_task(task, result, manifest, planes_dir)
            baked += 1
            sims += result[2]
            print(f'  [{baked}/{len(tasks)}] {task["key"]} '
                  f'({result[2]} sims)')
    dt = time.time() - t0
    print(f'Baked {baked} planes, {sims} sims in {dt:.1f}s '
          f'({sims / dt:.0f} sims/s).')

    if fresh_engine_digest() != start_digest:
        sys.exit('ABORT: engine sources changed MID-BAKE -- the planes '
                 'written this run are mixed-vintage. Delete them '
                 '(--rebake-all) after settling the engine.')
    return baked, n_skipped


def main():
    parser = argparse.ArgumentParser(
        description='Worlds 2026 Tier-1 plane bake (idempotent, '
                    'manifest-driven).',
        epilog='Sequencing rule (TODO.md "Worlds 2026"): the pending '
               'behavior-neutral engine-hash batch lands BEFORE the first '
               'real bake, or not at all until after Worlds -- the manifest '
               'pins one engine vintage for the whole campaign.')
    parser.add_argument('--pair-limit', type=int, default=None,
                        help='bake only the first N unordered pairs (smoke)')
    parser.add_argument('--workers', type=int,
                        default=max(1, multiprocessing.cpu_count() - 2))
    parser.add_argument('--dry-run', action='store_true',
                        help='print the worklist and exit')
    parser.add_argument('--rebake-all', action='store_true',
                        help='DELETE all planes + manifest and start fresh '
                             '(the only deletion path)')
    parser.add_argument('--allow-dirty-engine', action='store_true')
    args = parser.parse_args()

    install_sweep_cache_poison()
    preflight_engine_clean(allow_dirty=args.allow_dirty_engine)
    entries = load_meta()
    preflight_moveset_legality(entries)
    bake(entries, pair_limit=args.pair_limit, workers=args.workers,
         rebake_all=args.rebake_all, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
