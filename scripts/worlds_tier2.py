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

from gopvpsim.pokemon import Pokemon, iv_rank, find_pokemon_entry, LEAGUE_CAPS
from gopvpsim.moves import get_moves, parse_types
from gopvpsim.battle import simulate, pvpoke_dp

import worlds_planes as wp
import worlds_bake as wb
import worlds_render_data as wrd
from deep_dive_lib.sweep import make_battle_pokemon
from deep_dive_lib.robustness import _species_has_form_change

TIER2_DIR = wp.PLANES_DIR / 'tier2'
TIER2_SCHEMA = 1

_TIER2_SOURCE_FILES = (
    REPO / 'scripts' / 'worlds_tier2.py',
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


def tier2_task_worker(task):
    """One (direction, bait) full grid. Module-level for spawn pickling;
    never prints (worker stdout convention).

    Structure: for each opponent cohort row (a FIXED opponent instance),
    signature-dedup the full 4096-spread focal side against it and sim
    one representative per group x 9 scenarios, fanning out to members.
    Mirrors robustness.opp_plane with the varying/fixed roles swapped.
    Form-change FOCAL species get no dedup (their alt-form stats are
    non-linear in raw IVs; same rule as _opp_robustness_groups) -- the
    plan's "expensive pair-family".
    """
    import functools
    import deep_dive_signature as _sig

    league = task['league']
    league_cp = LEAGUE_CAPS[league]
    fast_db, charged_db = get_moves()
    focal_ranked = iv_rank(task['focal_species'], league=league,
                           shadow=task['focal_shadow'])
    opp_ranked_full = iv_rank(task['opponent'], league=league,
                              shadow=task['opp_shadow'])
    opp_rows = [opp_ranked_full[i] for i in task['cohort']]
    scen = list(task['scenarios'])
    nf, no, ns = len(focal_ranked), len(opp_rows), len(scen)

    focal_mon = find_pokemon_entry(task['focal_species'])
    focal_types = parse_types(focal_mon)
    fm = dict(fast_db[task['focal_fast']])
    cms = [dict(charged_db[c]) for c in task['focal_charged']]
    dedup = not _species_has_form_change(task['focal_species'])
    if dedup:
        profile_list = [(None, r['atk'], r['def_'], r['hp'],
                         r['atk_iv'], r['def_iv'], r['sta_iv'], r['level'])
                        for r in focal_ranked]
        swept = _sig.build_focal_side(focal_mon, focal_types, fm, cms,
                                      profile_list, league_cp,
                                      task['focal_shadow'])
    opp_mon = find_pokemon_entry(task['opponent'])
    opp_fm = dict(fast_db[task['opp_fast']])
    opp_cms = [dict(charged_db[c]) for c in task['opp_charged']]

    if task['bait']:
        focal_policy = pvpoke_dp
    else:
        focal_policy = functools.partial(pvpoke_dp, bait_shields=False)

    won = np.zeros((nf, no, ns), dtype=bool)
    score = np.zeros((nf, no, ns), dtype=np.uint16)
    n_sims = 0
    # Focal BattlePokemon are rebuilt per (group rep, row); the opponent
    # instance is fixed per row.
    for oi, orow in enumerate(opp_rows):
        opp_bp = make_battle_pokemon(
            task['opponent'], task['opp_fast'], task['opp_charged'], league,
            2, orow['atk_iv'], orow['def_iv'], orow['sta_iv'],
            shadow=task['opp_shadow'])
        if dedup:
            opp_pk = Pokemon.at_best_level(
                task['opponent'], orow['atk_iv'], orow['def_iv'],
                orow['sta_iv'], league=league, shadow=task['opp_shadow'])
            fixed = _sig.build_opp_side({
                'types': parse_types(opp_mon), 'fm': opp_fm, 'cms': opp_cms,
                'atk': opp_bp.atk, 'def_': opp_bp.def_, 'mon': opp_mon,
                'ivs': (orow['atk_iv'], orow['def_iv'], orow['sta_iv']),
                'level': opp_pk.level, 'shadow': task['opp_shadow'],
            }, league_cp)
            groups = [m for _r, m in _sig.signature_groups(swept, fixed)]
        else:
            groups = [[i] for i in range(nf)]
        fill = np.zeros(nf, dtype=np.int64)
        for members in groups:
            rep = focal_ranked[members[0]]
            focal_bp = make_battle_pokemon(
                task['focal_species'], task['focal_fast'],
                task['focal_charged'], league, 2,
                rep['atk_iv'], rep['def_iv'], rep['sta_iv'],
                shadow=task['focal_shadow'])
            for si, (sf, so) in enumerate(scen):
                focal_bp.reset_for_battle(sf, opponent=opp_bp)
                opp_bp.reset_for_battle(so, opponent=focal_bp)
                res = simulate(focal_bp, opp_bp,
                               charged_policy_0=focal_policy,
                               charged_policy_1=pvpoke_dp,
                               mechanics=task.get('mechanics', 'legacy'))
                sc = res.pvpoke_score(0)
                n_sims += 1
                idx = np.asarray(members)
                won[idx, oi, si] = sc > 500
                score[idx, oi, si] = sc
            fill[members] += 1
        if not (fill == 1).all():
            bad = np.flatnonzero(fill != 1)
            raise RuntimeError(
                f'tier2 dedup not a partition at opp row {oi}: '
                f'{len(bad)} positions, first {bad[0]}')

    packed, shape = wp.pack_won(won)
    arrs = {
        'won_packed': packed,
        'won_shape': np.asarray(shape, dtype=np.int64),
        'score': score,
        'focal_ivs': np.asarray(
            [(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in focal_ranked],
            dtype=np.int64),
        'focal_levels': np.asarray([r['level'] for r in focal_ranked]),
        'opp_ivs': np.asarray(
            [(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in opp_rows],
            dtype=np.int64),
        'opp_levels': np.asarray([r['level'] for r in opp_rows]),
        'scenarios': np.asarray(scen, dtype=np.int64),
        'top512_mask': np.asarray(task['top512_mask'], dtype=bool),
        'atkband_mask': np.asarray(task['atkband_mask'], dtype=bool),
    }
    if int(arrs['score'].max(initial=0)) > 1000:
        raise RuntimeError('score out of pvpoke range')
    return arrs, n_sims


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
    done_pairs = 0
    total_sims = 0
    with multiprocessing.Pool(workers) as pool:
        pending = []          # [(pair, is_clean, [(task, async_result)])]
        it = iter(todo)
        exhausted = False
        # Keep enough pairs in flight to saturate the pool (4 tasks per
        # pair), +1 so a finishing pair never idles workers.
        window = max(2, workers // 4 + 1)
        while True:
            while (not exhausted and len(pending) < window):
                if (time.time() - start) / 60 > budget_minutes:
                    exhausted = True
                    break
                try:
                    pair, is_clean, tasks = next(it)
                except StopIteration:
                    exhausted = True
                    break
                pending.append((pair, is_clean, [
                    (t, pool.apply_async(tier2_task_worker, (t,)))
                    for t in tasks]))
            if not pending:
                break
            pair, is_clean, jobs = pending.pop(0)
            for t, ar in jobs:
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
            save_manifest(manifest, tier2_dir)
            done_pairs += 1
            el = (time.time() - start) / 60
            print(f'  [{done_pairs}] {pair[0]}|{pair[1]}'
                  f'{" (clean)" if is_clean else ""} done, {el:.1f} min '
                  'elapsed')
    # Deferred = worklist pairs still not fully baked (recomputed, not
    # tracked incrementally, so a re-run shrinks it naturally).
    manifest['deferred'] = [
        list(pair) for pair, _is_clean in worklist
        if any(not baked_ok(t['key'])
               for t in pair_tasks(pair, resolved))]
    save_manifest(manifest, tier2_dir)
    dt = time.time() - start
    print(f'Baked {done_pairs} pairs, {total_sims} sims in {dt / 60:.1f} min '
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
