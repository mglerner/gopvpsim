#!/usr/bin/env python
"""Append a [meta.oracle] table to every pair config that lacks one.

The oracle pins the meta extraction to a published headline number
(review m9): the rank-1 spread's W/L/T for the primary arm at
pvpoke-IVs / bait / 1-1, read from the pair's CURRENT meta_wins.npz.
From then on, joint_iv_meta --verify hard-fails if a re-extraction
drifts from the published claim. Pairs without a meta npz (honest
absences) and pairs already carrying an oracle are skipped, loudly.

Usage: python scripts/joint_iv_gen_oracles.py
"""
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from joint_iv_config import load_pair  # noqa: E402


def main():
    added = 0
    for toml in sorted((REPO / 'pairs').glob('*.toml')):
        cfg = load_pair(toml)
        if 'oracle' in cfg.section('meta'):
            print(f'{toml.name}: SKIP (oracle already pinned)')
            continue
        mw_path = cfg.data_dir / 'meta_wins.npz'
        if not mw_path.exists():
            why = ('honest absence (meta_wins.ABSENT)'
                   if (cfg.data_dir / 'meta_wins.ABSENT').exists()
                   else 'no meta_wins.npz (shared or not yet extracted)')
            print(f'{toml.name}: SKIP ({why})')
            continue
        arm = cfg.grids[0].label.rpartition('_')[0] or cfg.grids[0].label
        z = np.load(mw_path)
        wk = f'wins__{arm}__pvpoke__bait__1-1'
        tk = f'ties__{arm}__pvpoke__bait__1-1'
        if wk not in z or 'pool_n' not in z:
            print(f'{toml.name}: SKIP (no {wk} in the npz)')
            continue
        w = int(np.asarray(z[wk])[0])
        t = int(np.asarray(z[tk])[0]) if tk in z else 0
        pool = int(z['pool_n'])
        block = f"""
# Regression pin (review m9): the rank-1 spread's published headline
# W/L/T for the primary arm at pvpoke-IVs / bait / 1-1, read from the
# meta_wins.npz current at first publish. joint_iv_meta --verify fails
# if a re-extraction drifts from this claim.
[meta.oracle]
arm = "{arm}"
oppiv = "pvpoke"
bait = true
scenario = [1, 1]
rank = 1
want_w = {w}
want_l = {pool - w - t}
want_t = {t}
"""
        with open(toml, 'a') as f:
            f.write(block)
        print(f'{toml.name}: oracle pinned ({w}W {pool - w - t}L {t}T '
              f'of {pool})')
        added += 1
    print(f'{added} oracle(s) added')


if __name__ == '__main__':
    main()
