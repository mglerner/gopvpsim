#!/usr/bin/env python
"""Bake full 4096x4096 IV joint grids for one joint-IV pair config.

Config-driven generalization of scripts/thievul_licki_bake.py (S1 of
docs/joint_iv_reuse_plan.md): every focal-vs-opponent identity, moveset,
shadow flag, grid label and output path comes from a pairs/*.toml file
(see scripts/joint_iv_config.py for the schema). The Thievul configs
reproduce the shipped bakes exactly -- verified by --check-rows, which
re-sims sampled rows of every existing grid and requires bit-exact
agreement with the stored npz.

Reuses the Worlds Tier-1 core (deep_dive_lib.robustness.plane_task_worker)
with cohort=list(range(4096)), sharding the focal 4096 across the pool.
Row/column order on BOTH axes is canonical iv_rank(..., league, shadow)
order (stat-product rank, 1-indexed rank = row index + 1). Win = pvpoke
score > 500 strict. Storage mirrors worlds_tier2: packed won (authority)
+ raw uint16 score. The opponent always baits (dive convention); bait in
[[grids]] is the FOCAL bait policy.

Idempotent per grid: a grid whose npz exists and whose manifest entry
matches the current engine+gamemaster stamps is skipped (worlds_tier2
precedent -- restarts after a kill resume where they left off). A stamp
mismatch on an existing manifest ABORTS (single vintage per data_dir by
design); --force rebakes everything.

Usage:
    python scripts/joint_iv_bake.py pairs/<pair>.toml [--workers N]
    python scripts/joint_iv_bake.py pairs/<pair>.toml --smoke
    python scripts/joint_iv_bake.py pairs/<pair>.toml --check-rows 8
"""
import argparse
import json
import multiprocessing as mp
import os
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deep_dive_lib.robustness import plane_task_worker  # noqa: E402
from joint_iv_config import load_pair, preflight_moveset_legality  # noqa: E402
import sweep_cache  # noqa: E402
import worlds_planes as wp  # noqa: E402

from gopvpsim.pokemon import iv_rank  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
SCENARIOS = [(sf, so) for sf in range(3) for so in range(3)]
CHUNK = 64  # focal spreads per pool task

# Rows re-simmed by --check-rows (beyond the first N): scattered across
# the SP-rank axis so the check exercises off-top spreads, not just the
# rank-1 neighborhood.
CHECK_SCATTER = (511, 512, 2048, 4095)


def ranked_arrays(species, league, shadow):
    ranked = iv_rank(species, league=league, shadow=shadow)
    ivs = np.array([(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in ranked],
                   dtype=np.int64)
    levels = np.array([r['level'] for r in ranked], dtype=np.float64)
    return ranked, ivs, levels


def grid_task(cfg, grid, focal_spreads, lo):
    return {
        'grid': grid.label,
        'lo': lo,
        'focal_species': cfg.focal,
        'focal_fast': grid.focal_fast,
        'focal_charged': list(grid.focal_charged),
        'focal_shadow': cfg.focal_shadow,
        'focal_spreads': focal_spreads,
        'opponent': cfg.opponent,
        'opp_fast': cfg.opp_fast,
        'opp_charged': list(cfg.opp_charged),
        'opp_shadow': cfg.opp_shadow,
        'league': cfg.league,
        'scenarios': SCENARIOS,
        'cohort': list(range(4096)),
        'bait': grid.bait,
    }


def _worker(task):
    won, score, n_sims = plane_task_worker(task)
    return task['grid'], task['lo'], won, score, n_sims


def load_manifest(cfg):
    p = cfg.data_dir / 'manifest.json'
    return json.loads(p.read_text()) if p.exists() else None


def check_rows(cfg, n_rows):
    """Re-sim sampled focal rows of every EXISTING grid and require exact
    equality with the stored npz -- the kit's bake-equivalence check
    (S1 acceptance for the thievul configs; a standing freshness spot
    check for any pair). Returns the number of grids checked."""
    manifest = load_manifest(cfg)
    if manifest is None:
        sys.exit(f'ABORT: --check-rows needs an existing manifest in '
                 f'{cfg.data_dir}')
    _, focal_ivs, _ = ranked_arrays(cfg.focal, cfg.league, cfg.focal_shadow)
    rows = sorted(set(range(n_rows)) | set(CHECK_SCATTER))
    checked = 0
    for grid in cfg.grids:
        fname = cfg.grid_filename(grid.label)
        path = cfg.data_dir / fname
        ment = manifest['grids'].get(grid.label)
        if ment is None or not path.exists():
            print(f'  check {grid.label}: SKIP (not baked)')
            continue
        if ment['file'] != fname:
            sys.exit(f'ABORT: manifest file {ment["file"]} != config '
                     f'naming {fname} for grid {grid.label}')
        z = np.load(path)
        won_ref = wp.unpack_won(z['won_packed'], tuple(z['won_shape']))
        score_ref = np.asarray(z['score'])
        spreads = [tuple(map(int, focal_ivs[r])) for r in rows]
        # Config axis convention must match the stored grid's own axis.
        stored_focal_ivs = np.asarray(z['focal_ivs'])
        for r in rows:
            if tuple(stored_focal_ivs[r]) != tuple(focal_ivs[r]):
                sys.exit(f'ABORT: focal axis mismatch at row {r} of '
                         f'{fname}: stored {tuple(stored_focal_ivs[r])} '
                         f'vs iv_rank {tuple(focal_ivs[r])}')
        won, score, n_sims = plane_task_worker(
            grid_task(cfg, grid, spreads, 0))
        same_won = bool((won == won_ref[rows]).all())
        same_score = bool((score == score_ref[rows]).all())
        status = 'OK' if (same_won and same_score) else 'MISMATCH'
        print(f'  check {grid.label}: rows {rows} ({n_sims} sims) '
              f'won={"=" if same_won else "DIFFERS"} '
              f'score={"=" if same_score else "DIFFERS"} -> {status}')
        if status != 'OK':
            sys.exit(f'ABORT: {fname} disagrees with a fresh re-sim -- '
                     'engine drift or config mismatch')
        checked += 1
    return checked


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pair', help='pairs/<pair>.toml config path')
    ap.add_argument('--workers', type=int, default=max(1, mp.cpu_count() - 4))
    ap.add_argument('--smoke', action='store_true',
                    help='tiny run: 8 focal spreads, first grid only, '
                         'written to <data_dir>/_smoke/')
    ap.add_argument('--check-rows', type=int, default=None, metavar='N',
                    help='no bake: re-sim the first N + scattered rows of '
                         'every existing grid, require exact npz agreement')
    ap.add_argument('--force', action='store_true',
                    help='rebake grids even if baked at current stamps')
    args = ap.parse_args()

    cfg = load_pair(args.pair)
    preflight_moveset_legality(cfg)
    engine = sweep_cache.engine_hash()
    gamemaster = sweep_cache.gamemaster_hash()
    print(f'pair {cfg.focal}{" (Shadow)" if cfg.focal_shadow else ""} vs '
          f'{cfg.opponent}{" (Shadow)" if cfg.opp_shadow else ""} '
          f'[{cfg.league}]; engine {engine} gamemaster {gamemaster}')

    if args.check_rows is not None:
        n = check_rows(cfg, args.check_rows)
        print(f'check-rows: {n} grid(s) verified exact')
        return

    out_dir = cfg.data_dir if not args.smoke else cfg.data_dir / '_smoke'
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    focal_ranked, focal_ivs, focal_levels = ranked_arrays(
        cfg.focal, cfg.league, cfg.focal_shadow)
    opp_ranked, opp_ivs, opp_levels = ranked_arrays(
        cfg.opponent, cfg.league, cfg.opp_shadow)
    n_focal, n_opp = len(focal_ranked), len(opp_ranked)
    assert n_focal == 4096 and n_opp == 4096, (n_focal, n_opp)
    focal_spreads = [tuple(map(int, row)) for row in focal_ivs]

    grids = list(cfg.grids)
    if args.smoke:
        grids = grids[:1]
        focal_spreads = focal_spreads[:8]

    manifest = None if args.smoke else load_manifest(cfg)
    if manifest is not None:
        stale = {k: (manifest.get(k), v) for k, v in
                 (('engine', engine), ('gamemaster', gamemaster))
                 if manifest.get(k) != v}
        if stale:
            sys.exit(f'ABORT: existing manifest in {cfg.data_dir} was baked '
                     f'at different stamps {stale}; single vintage per '
                     'data_dir by design. Move it aside to rebake fresh.')
        if not args.force:
            done = [g.label for g in grids
                    if g.label in manifest['grids']
                    and (cfg.data_dir / cfg.grid_filename(g.label)).exists()]
            if done:
                print(f'skipping already-baked grids: {done} '
                      '(--force to rebake)')
            grids = [g for g in grids if g.label not in done]
        if not grids:
            print('nothing to bake: all grids present at current stamps')
            return
    if manifest is None:
        manifest = {
            'engine': engine,
            'gamemaster': gamemaster,
            'mechanics': 'legacy',
            'focal': cfg.focal, 'opponent': cfg.opponent,
            'league': cfg.league,
            'opp_fast': cfg.opp_fast,
            'opp_charged': list(cfg.opp_charged),
            'scenarios': SCENARIOS,
            'axis_order': 'iv_rank stat-product order, both axes '
                          '(row/col i = rank i+1)',
            'opp_always_baits': True,
            'grids': {},
            'total_sims': 0,
            'wall_seconds': None,
            # additive vs the thievul-era schema; downstream steps
            # default these when absent from the older manifests
            'focal_shadow': cfg.focal_shadow,
            'opp_shadow': cfg.opp_shadow,
            'injected_moves': list(cfg.injected_moves),
            'pair_config': str(cfg.path.relative_to(REPO)),
            'kit': 'joint_iv',
        }

    shards_per_grid = (len(focal_spreads) + CHUNK - 1) // CHUNK
    all_tasks = []
    for g in grids:
        for lo in range(0, len(focal_spreads), CHUNK):
            all_tasks.append(
                grid_task(cfg, g, focal_spreads[lo:lo + CHUNK], lo))
    print(f'{len(all_tasks)} tasks ({len(grids)} grids x '
          f'{len(focal_spreads)} focal spreads / {CHUNK}), '
          f'{args.workers} workers', flush=True)

    grid_info = {g.label: g for g in grids}
    total_sims = manifest.get('total_sims', 0)

    def write_grid(label):
        parts = sorted(acc[label].items())
        won = np.concatenate([w for _, (w, _) in parts])
        score = np.concatenate([s for _, (_, s) in parts])
        assert won.shape == (len(focal_spreads), n_opp, len(SCENARIOS))
        packed, shape = wp.pack_won(won)
        fname = cfg.grid_filename(label)
        tmp = out_dir / (fname + '.tmp.npz')
        np.savez_compressed(
            tmp, won_packed=packed, won_shape=np.array(shape),
            score=score, focal_ivs=focal_ivs[:len(focal_spreads)],
            focal_levels=focal_levels[:len(focal_spreads)],
            opp_ivs=opp_ivs, opp_levels=opp_levels,
            scenarios=np.array(SCENARIOS))
        os.replace(tmp, out_dir / fname)
        g = grid_info[label]
        manifest['grids'][label] = {
            'file': fname, 'focal_fast': g.focal_fast,
            'focal_charged': list(g.focal_charged),
            'bait': g.bait, 'shape': list(won.shape),
        }
        manifest['total_sims'] = total_sims
        manifest['wall_seconds'] = round(time.time() - t_start, 1)
        (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print(f'wrote {out_dir / fname} shape={won.shape} '
              f'won_frac={won.mean():.4f}', flush=True)
        del acc[label]

    acc = {g.label: {} for g in grids}
    done = 0
    with mp.Pool(args.workers) as pool:
        for grid, lo, won, score, n_sims in pool.imap_unordered(
                _worker, all_tasks):
            acc[grid][lo] = (won, score)
            total_sims += n_sims
            done += 1
            el = time.time() - t_start
            print(f'[{done}/{len(all_tasks)}] {grid} lo={lo} '
                  f'sims={total_sims:,} elapsed={el:,.0f}s '
                  f'rate={total_sims / el:,.0f}/s', flush=True)
            if len(acc.get(grid, ())) == shards_per_grid:
                write_grid(grid)

    for label in [g.label for g in grids if g.label in acc]:
        if acc[label]:
            write_grid(label)
    print(f'done: {total_sims:,} sims in '
          f'{round(time.time() - t_start, 1):,}s', flush=True)


if __name__ == '__main__':
    main()
