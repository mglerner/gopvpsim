#!/usr/bin/env python
"""Stratified live-sim probe of a rendered dive page against today's engine.

For every opponent on a dive page, re-sim three focal IV spreads (the
PvPoke-reference spread, the rank-1 spread, one random one) x 2 bait
modes x 9 shield scenarios at the page's PvPoke opponent IVs, and compare
each PvPoke score with the baked tensor. Cheaper than a re-dive, broader
than a hand-picked cell check: it tells you whether a shipped page is
still integer-exact under the current engine + gamemaster, and if not,
which opponents moved and whether any winner flipped.

Used 2026-11-05 to clear Thievul GL (4,320/4,320) and to catch the stale
Superpower / Psycho Boost cells on the shipped Tinkaton GL/UL pages
(TODO.md "PvPoke sync 2026-11-05").

Usage (from the repo root, with the data cache pinned so nothing refetches):

    GOPVPSIM_PIN_DATA_CACHE=1 PROBE_OUT=probe.json \\
        .venv/bin/python scripts/probe_page_cells.py userdata/website/<dir>/index.html ...

PROBE_OUT gets a JSON map {page: {opponent: [(iv_idx, scenario, bait,
baked, live), ...]}}; an empty inner map means the page is exact.
"""
import functools
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('GOPVPSIM_PIN_DATA_CACHE', '1')
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / 'src'))
sys.path.insert(0, str(_HERE))

import numpy as np

from cramorant_certify import SCENARIOS, load_page
from cramorant_policy_lab import make_bp
from gopvpsim import data as gdata
from gopvpsim.battle import is_win, pvpoke_dp, simulate

gm = gdata.load_gamemaster()
id2name = {p['speciesId']: p['speciesName'] for p in gm['pokemon']}


def probe(path, seed=0):
    d, t = load_page(path)
    n_opp = len(d['opponents'])
    shape = (4096, 9, n_opp)
    league = d['league']
    ms = d['movesets'][0]
    print(f'== {path}: {d["species"]} {league} {ms["label"]} n_opp={n_opp}')
    rng = np.random.default_rng(seed)
    bad = tot = 0
    bad_by_opp = {}
    for oi in range(n_opp):
        link = d['oppLinks'][oi]
        mv = link['moves'].split('-')
        sid = link['id']
        shadow = sid.endswith('_shadow')
        clean = id2name[sid[:-7] if shadow else sid]
        iv_idxs = [d['pvpokeRefIvIdx'], d['rank1RefIvIdx'], int(rng.integers(4096))]
        for iv in iv_idxs:
            for bait, suf in (('bait', ''), ('nobait', ':nobait')):
                pv = t[f'0_pvpoke{suf}'].reshape(shape)
                for si in range(9):
                    foc = make_bp(d['species'], league, False, ms['fast'], ms['charged'],
                                  ivs=(d['ivA'][iv], d['ivD'][iv], d['ivS'][iv]))
                    opp = make_bp(clean, league, shadow, mv[0], mv[1:],
                                  ivs=tuple(link['byMode']['pvpoke']['ivs']))
                    foc.reset_for_battle(si // 3, opp)
                    opp.reset_for_battle(si % 3, foc)
                    pol = (pvpoke_dp if bait == 'bait'
                           else functools.partial(pvpoke_dp, bait_shields=False))
                    r = simulate(foc, opp, charged_policy_0=pol, charged_policy_1=pvpoke_dp)
                    got = r.pvpoke_score(0)
                    want = int(pv[iv, si, oi])
                    tot += 1
                    if got != want:
                        bad += 1
                        bad_by_opp.setdefault(d['opponents'][oi], []).append(
                            (iv, SCENARIOS[si], bait, want, got))
    print(f'   {tot - bad}/{tot} cells integer-exact; '
          f'opponents with moved cells: {len(bad_by_opp)}')
    for o, cells in bad_by_opp.items():
        flips = sum(1 for c in cells if is_win(c[3]) != is_win(c[4]))
        print(f'   {o}: {len(cells)} moved, {flips} winner flips; e.g. {cells[:3]}')
    return bad_by_opp


def main():
    out = {p: probe(p) for p in sys.argv[1:]}
    if os.environ.get('PROBE_OUT'):
        with open(os.environ['PROBE_OUT'], 'w') as fh:
            json.dump(out, fh, indent=1, default=str)


if __name__ == '__main__':
    main()
