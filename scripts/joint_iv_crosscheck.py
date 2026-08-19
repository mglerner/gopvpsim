#!/usr/bin/env python
"""Cross-check a joint-IV pair bake against the Worlds Tier-2 grids.

Where a matching Worlds Tier-2 grid exists (same focal/opponent
species_ids, movesets, shadow flags, league, bait mode, and engine +
gamemaster stamps), the kit's full 4096x4096 grid must agree EXACTLY
with the Tier-2 4096x~519-cohort grid on the overlapping opponent
columns -- two independent bake paths over the same engine. This is
free adversarial verification of the kit's axis/moveset bookkeeping
(NOT a shortcut: the kit still sims everything; see the 2026-08-19
session decision -- correctness over speed).

Opponent columns are matched by IV triple (the Tier-2 npz stores the
cohort's opp_ivs directly). Scenario order and focal axis are asserted
identical, not assumed. Any mismatch is a hard failure.

Usage:
    python scripts/joint_iv_crosscheck.py pairs/<pair>.toml
"""
import argparse
import json
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from joint_iv_config import load_pair  # noqa: E402
import worlds_planes as wp  # noqa: E402

TIER2_DIR = wp.PLANES_DIR / 'tier2'


def t2_filename(focal_id, opp_id, bait):
    return (f'{focal_id}__vs__{opp_id}__'
            f'{"bait" if bait else "nobait"}__t2.npz')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pair', help='pairs/<pair>.toml config path')
    args = ap.parse_args()
    cfg = load_pair(args.pair)

    manifest_path = cfg.data_dir / 'manifest.json'
    if not manifest_path.exists():
        sys.exit(f'ABORT: no kit manifest at {manifest_path}')
    manifest = json.loads(manifest_path.read_text())

    t2_manifest_path = TIER2_DIR / 'manifest.json'
    if not t2_manifest_path.exists():
        sys.exit('ABORT: no worlds tier2 manifest; nothing to check against')
    t2m = json.loads(t2_manifest_path.read_text())
    for stamp in ('engine', 'gamemaster'):
        if manifest[stamp] != t2m[stamp]:
            sys.exit(f'ABORT: {stamp} stamp differs (kit {manifest[stamp]} '
                     f'vs tier2 {t2m[stamp]}) -- vintages not comparable')

    # Movesets must match what the tier2 bake simmed (worlds/meta.toml).
    import worlds_render_data as wrd
    meta = wrd.load_meta()
    entries = {e['species_id']: e for e in meta['entries']}
    fe = entries.get(cfg.focal_slug)
    oe = entries.get(cfg.opp_slug)
    if fe is None or oe is None:
        sys.exit(f'ABORT: {cfg.focal_slug} / {cfg.opp_slug} not both in '
                 'worlds/meta.toml -- no tier2 reference for this pair')
    if (oe['fast_move_id'] != cfg.opp_fast
            or list(oe['charged_move_ids']) != list(cfg.opp_charged)
            or bool(oe['shadow']) != cfg.opp_shadow):
        sys.exit(f'ABORT: opponent moveset/shadow differs from the worlds '
                 f'meta entry; tier2 grids are not a reference here')

    checked = 0
    for grid in cfg.grids:
        if (grid.focal_fast != fe['fast_move_id']
                or list(grid.focal_charged) != list(fe['charged_move_ids'])):
            print(f'  {grid.label}: SKIP (focal moveset differs from the '
                  'worlds meta entry)')
            continue
        kit_path = cfg.data_dir / cfg.grid_filename(grid.label)
        if not kit_path.exists():
            print(f'  {grid.label}: SKIP (kit grid not baked yet)')
            continue
        key = wp.pair_key(cfg.focal_slug, cfg.opp_slug, grid.bait)
        ment = t2m['entries'].get(key)
        if ment is None:
            print(f'  {grid.label}: SKIP (no tier2 grid {key})')
            continue
        t2_path = TIER2_DIR / ment['file']
        kz = np.load(kit_path)
        tz = np.load(t2_path)

        if not np.array_equal(kz['scenarios'], tz['scenarios']):
            sys.exit(f'ABORT: scenario order differs for {grid.label}')
        if not np.array_equal(kz['focal_ivs'], tz['focal_ivs']):
            sys.exit(f'ABORT: focal IV axis differs for {grid.label}')
        if not np.array_equal(kz['focal_levels'], tz['focal_levels']):
            sys.exit(f'ABORT: focal level axis differs for {grid.label}')

        kit_opp = {tuple(iv): i for i, iv in enumerate(kz['opp_ivs'])}
        cols = []
        for iv, lv in zip(tz['opp_ivs'], tz['opp_levels']):
            i = kit_opp.get(tuple(iv))
            if i is None:
                sys.exit(f'ABORT: tier2 cohort spread {tuple(iv)} missing '
                         f'from the kit opponent axis ({grid.label})')
            if float(kz['opp_levels'][i]) != float(lv):
                sys.exit(f'ABORT: level mismatch for opp spread {tuple(iv)}')
            cols.append(i)
        cols = np.asarray(cols)

        kit_won = wp.unpack_won(kz['won_packed'], tuple(kz['won_shape']))
        t2_won = wp.unpack_won(tz['won_packed'], tuple(tz['won_shape']))
        same_won = bool((kit_won[:, cols, :] == t2_won).all())
        same_score = bool(
            (np.asarray(kz['score'])[:, cols, :]
             == np.asarray(tz['score'])).all())
        n = len(cols)
        print(f'  {grid.label}: vs {ment["file"]} ({n} cohort columns x '
              f'4096 x 9) won={"=" if same_won else "DIFFERS"} '
              f'score={"=" if same_score else "DIFFERS"}')
        if not (same_won and same_score):
            sys.exit(f'ABORT: kit grid disagrees with the tier2 grid on the '
                     f'cohort overlap ({grid.label}) -- axis or moveset '
                     'bookkeeping bug')
        checked += 1
    print(f'cross-check: {checked} grid(s) agree exactly with tier2 on the '
          'cohort overlap')
    if checked == 0:
        sys.exit('ABORT: cross-check checked NOTHING (no comparable grids) '
                 '-- do not cite it as passing')


if __name__ == '__main__':
    main()
