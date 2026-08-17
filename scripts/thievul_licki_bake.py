#!/usr/bin/env python
"""Bake full 4096x4096 IV joint grids: Thievul vs Lickitung (Great League).

One-off robustness bake for the 2026-08-16 Thievul CD "IV tech" question
(HSH discord: is 6/15/5 the best spread for the Sucker Punch breakpoint
on Lickitung, or do you want 15 HP?). Every Thievul IV spread (4096) vs
every Lickitung IV spread (4096) across all 9 shield scenarios.

Reuses the Worlds Tier-1 core (`deep_dive_lib.robustness.plane_task_worker`)
with `cohort=list(range(4096))`, sharding the focal 4096 across the pool
(the Tier-2 per-grid layout caps a single pair at 4 cores; this doesn't).
Row/column order on BOTH axes is canonical `iv_rank(..., league='great')`
order (stat-product rank, 1-indexed rank = row index + 1).

Output: userdata/thievul_licki/<label>.npz + manifest.json (provenance).
Storage mirrors worlds_tier2: packed `won` (authority) + raw uint16 score.

Grids baked (Lickitung always LICK / BODY_SLAM + POWER_WHIP, the PvPoke
GL rankings default; opponent always baits, matching the dive convention):
  iwpr_bait    SP / ICY_WIND + PLAY_ROUGH, focal baits   (shipped dive landing build)
  iwpr_nobait  SP / ICY_WIND + PLAY_ROUGH, focal no-bait
  nsiw_bait    SP / NIGHT_SLASH + ICY_WIND, focal baits  (PvPoke post-CD default)

ICY_WIND is not in the pinned gamemaster's Thievul pool (pre-CD lag; see
thresholds/thievul.toml [Thievul.cd_prep]) -- make_battle_pokemon takes move
ids directly and has no legality guard, so injection here is just naming it.
"""
import json
import multiprocessing as mp
import os
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deep_dive_lib.robustness import plane_task_worker  # noqa: E402
import sweep_cache  # noqa: E402
import worlds_planes as wp  # noqa: E402

from gopvpsim.pokemon import iv_rank  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent

FOCAL = 'Thievul'
LEAGUE = 'great'
SCENARIOS = [(sf, so) for sf in range(3) for so in range(3)]
CHUNK = 64  # focal spreads per pool task

# Per-opponent config. 2026-08-16: the first bake ran vs Lickitung, but
# the community's "Licki" is Lickilicky (GL #1; Lickitung is out of the
# meta pool) -- Michael's pvpoke cross-check exposed the mismatch, and
# our engine reproduces his Thievul vs Lickilicky 3x3 exactly (9/9).
# Bait-on grids first: npz files are written per-grid as they complete,
# so analysis starts on them while the no-bait grids bake.
OPPONENTS = {
    'lickitung': {
        'species': 'Lickitung',
        'opp_fast': 'LICK',
        'opp_charged': ['BODY_SLAM', 'POWER_WHIP'],
        'out_dir': REPO / 'userdata' / 'thievul_licki',
        'grids': [
            ('iwpr_bait',   'SUCKER_PUNCH', ['ICY_WIND', 'PLAY_ROUGH'], True),
            ('iwpr_nobait', 'SUCKER_PUNCH', ['ICY_WIND', 'PLAY_ROUGH'], False),
            ('nsiw_bait',   'SUCKER_PUNCH', ['NIGHT_SLASH', 'ICY_WIND'], True),
        ],
    },
    'lickilicky': {
        'species': 'Lickilicky',
        'opp_fast': 'ROLLOUT',
        'opp_charged': ['BODY_SLAM', 'SHADOW_BALL'],
        'out_dir': REPO / 'userdata' / 'thievul_lickilicky',
        'grids': [
            ('iwpr_bait',    'SUCKER_PUNCH', ['ICY_WIND', 'PLAY_ROUGH'], True),
            ('nsiw_bait',    'SUCKER_PUNCH', ['NIGHT_SLASH', 'ICY_WIND'], True),
            ('iwpr_nobait',  'SUCKER_PUNCH', ['ICY_WIND', 'PLAY_ROUGH'], False),
            ('nsiw_nobait',  'SUCKER_PUNCH', ['NIGHT_SLASH', 'ICY_WIND'], False),
        ],
    },
}


def ranked_arrays(species):
    ranked = iv_rank(species, league=LEAGUE)
    ivs = np.array([(r['atk_iv'], r['def_iv'], r['sta_iv']) for r in ranked],
                   dtype=np.int64)
    levels = np.array([r['level'] for r in ranked], dtype=np.float64)
    return ranked, ivs, levels


def build_tasks(cfg, label, focal_fast, focal_charged, bait, focal_spreads):
    tasks = []
    cohort = list(range(4096))
    for lo in range(0, len(focal_spreads), CHUNK):
        tasks.append({
            'grid': label,
            'lo': lo,
            'focal_species': FOCAL,
            'focal_fast': focal_fast,
            'focal_charged': focal_charged,
            'focal_shadow': False,
            'focal_spreads': focal_spreads[lo:lo + CHUNK],
            'opponent': cfg['species'],
            'opp_fast': cfg['opp_fast'],
            'opp_charged': cfg['opp_charged'],
            'opp_shadow': False,
            'league': LEAGUE,
            'scenarios': SCENARIOS,
            'cohort': cohort,
            'bait': bait,
        })
    return tasks


def _worker(task):
    won, score, n_sims = plane_task_worker(task)
    return task['grid'], task['lo'], won, score, n_sims


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--opponent', choices=sorted(OPPONENTS),
                    default='lickitung')
    ap.add_argument('--workers', type=int, default=max(1, mp.cpu_count() - 4))
    ap.add_argument('--smoke', action='store_true',
                    help='tiny run: 8 focal spreads, first grid only')
    args = ap.parse_args()

    cfg = OPPONENTS[args.opponent]
    out_dir = cfg['out_dir']
    opp_slug = cfg['species'].lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    focal_ranked, focal_ivs, focal_levels = ranked_arrays(FOCAL)
    opp_ranked, opp_ivs, opp_levels = ranked_arrays(cfg['species'])
    n_focal, n_opp = len(focal_ranked), len(opp_ranked)
    assert n_focal == 4096 and n_opp == 4096, (n_focal, n_opp)
    focal_spreads = [tuple(map(int, row)) for row in focal_ivs]

    grids = cfg['grids']
    if args.smoke:
        grids = grids[:1]
        focal_spreads = focal_spreads[:8]
    shards_per_grid = (len(focal_spreads) + CHUNK - 1) // CHUNK

    all_tasks = []
    for label, ff, fc, bait in grids:
        all_tasks.extend(build_tasks(cfg, label, ff, fc, bait, focal_spreads))
    print(f'{len(all_tasks)} tasks ({len(grids)} grids x '
          f'{len(focal_spreads)} focal spreads / {CHUNK}), '
          f'{args.workers} workers, opponent {cfg["species"]}', flush=True)

    manifest = {
        'engine': sweep_cache.engine_hash(),
        'gamemaster': sweep_cache.gamemaster_hash(),
        'mechanics': 'legacy',
        'focal': FOCAL, 'opponent': cfg['species'], 'league': LEAGUE,
        'opp_fast': cfg['opp_fast'], 'opp_charged': cfg['opp_charged'],
        'scenarios': SCENARIOS,
        'axis_order': 'iv_rank stat-product order, both axes '
                      '(row/col i = rank i+1)',
        'opp_always_baits': True,
        'grids': {},
        'total_sims': 0,
        'wall_seconds': None,
    }
    grid_info = {label: (ff, fc, bait) for label, ff, fc, bait in grids}

    def write_grid(label):
        """Write one finished grid npz + refresh the manifest in place."""
        parts = sorted(acc[label].items())
        won = np.concatenate([w for _, (w, _) in parts])
        score = np.concatenate([s for _, (_, s) in parts])
        assert won.shape == (len(focal_spreads), n_opp, len(SCENARIOS))
        packed, shape = wp.pack_won(won)
        fname = f'thievul_{label}__vs__{opp_slug}.npz'
        tmp = out_dir / (fname + '.tmp.npz')
        np.savez_compressed(
            tmp, won_packed=packed, won_shape=np.array(shape),
            score=score, focal_ivs=focal_ivs[:len(focal_spreads)],
            focal_levels=focal_levels[:len(focal_spreads)],
            opp_ivs=opp_ivs, opp_levels=opp_levels,
            scenarios=np.array(SCENARIOS))
        os.replace(tmp, out_dir / fname)
        ff, fc, bait = grid_info[label]
        manifest['grids'][label] = {
            'file': fname, 'focal_fast': ff, 'focal_charged': fc,
            'bait': bait, 'shape': list(won.shape),
        }
        manifest['total_sims'] = total_sims
        manifest['wall_seconds'] = round(time.time() - t_start, 1)
        (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print(f'wrote {fname} shape={won.shape} '
              f'won_frac={won.mean():.4f}', flush=True)
        del acc[label]

    acc = {label: {} for label, *_ in grids}
    total_sims = 0
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

    for label in [lb for lb, *_ in grids if lb in acc]:
        if acc[label]:
            write_grid(label)
    print(f'done: {total_sims:,} sims in '
          f'{round(time.time() - t_start, 1):,}s', flush=True)


if __name__ == '__main__':
    main()
