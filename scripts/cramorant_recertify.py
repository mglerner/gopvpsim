#!/usr/bin/env python
"""Re-certify CHANGED sheet rows against the strict bar by re-simulating
every slice of the affected start scenarios through the production path
(cramorant_mini_sweep.run_slice) under a candidate set of knob / sheet
overrides, and printing a cramorant_certify-style table.

The certifier can only read baked tensors (the shipped sheet). When a row
changes, its scenarios must be re-simmed: per scenario, 5 moveset pages x
2 opp-IV modes x 2 bait modes x 2 caps = 40 slices per league, 4096 IVs x
pool each at --stride 1 (the bar) -- about 620k sims per slice, so budget
minutes per slice on a loaded machine; screen at a coprime stride first.

    python scripts/cramorant_recertify.py --website ... --league both \
        --scenarios 2v2 --stride 13 \
        --sheet '{"(2, 2)": {"gate": "always", "tank_aggr": 2.2, "tank_rule": "lead_ready"}}' \
        [--knob NAME=VALUE ...] [--pages index.html,...] [--out JSON]

Unchanged scenarios are NOT re-simmed here; the certifier already covers
them from the tensors. The plain-PvPoke tier of every cell is checked
against the tensor (it cannot move under pogodives-only overrides); a
mismatch means the page is not today's engine and the run aborts.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

from cramorant_certify import BAITS, CAPS, OPP_IV_MODES, SCENARIOS, TOP_SP, load_page  # noqa: E402
from cramorant_mini_sweep import apply_overrides, parse_knob, restore, run_slice, summarize  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--website', default=str(REPO / 'userdata' / 'website'))
    ap.add_argument('--league', default='both', choices=['great', 'ultra', 'both'])
    ap.add_argument('--scenarios', required=True,
                    help='comma-separated start scenarios whose rows changed, e.g. 2v2,1v1')
    ap.add_argument('--pages', default=None,
                    help='comma-separated page file names (default: every index*.html)')
    ap.add_argument('--stride', type=int, default=13)
    ap.add_argument('--knob', action='append', default=[], metavar='NAME=VALUE')
    ap.add_argument('--sheet', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    leagues = ['great', 'ultra'] if args.league == 'both' else [args.league]
    scenarios = [s for s in args.scenarios.split(',') if s]
    for s in scenarios:
        if s not in SCENARIOS:
            raise SystemExit(f'bad scenario {s}')
    knobs = [parse_knob(k) for k in args.knob]
    sheet = json.loads(args.sheet) if args.sheet else {}
    ivs = list(range(0, 4096, args.stride))
    rows, t0 = [], time.time()
    saved, saved_sheet = apply_overrides(knobs, sheet)
    try:
        for league in leagues:
            pages = sorted(glob.glob(f'{args.website}/cramorant-{league}-league/index*.html'))
            if args.pages:
                keep = set(args.pages.split(','))
                pages = [p for p in pages if Path(p).name in keep]
            for page in pages:
                data, tensors = load_page(page)
                names = data['opponents']; n_opp = len(names)
                sp = np.asarray(data['spRanks'])
                for scen in scenarios:
                    si = SCENARIOS.index(scen)
                    for mode in OPP_IV_MODES:
                        for bait, bsuf in BAITS:
                            for cap, csuf in CAPS:
                                cells, _ = run_slice(data, league, scen, mode, bait,
                                                     ivs, cap=int(cap))
                                pv_t = tensors[f'0_{mode}{bsuf}{csuf}'].reshape(4096, 9, n_opp)
                                pg_t = tensors[f'0_{mode}{bsuf}:pogodives{csuf}'].reshape(4096, 9, n_opp)
                                bad = [k for k, v in cells.items() if v[0] != int(pv_t[k[0], si, k[1]])]
                                if bad:
                                    raise SystemExit(f'{page} {scen} {mode}/{bait}/@{cap}: plain tier '
                                                     f'differs from tensor in {len(bad)} cells -- stale page')
                                live = summarize(cells, names)
                                shipped = summarize({k: (int(pv_t[k[0], si, k[1]]),
                                                         int(pg_t[k[0], si, k[1]])) for k in cells}, names)
                                top = {k: v for k, v in cells.items() if sp[k[0]] <= TOP_SP}
                                live_top = summarize(top, names) if top else {'net': 0, 'mean': 0.0}
                                offenders = sorted(((k, v) for k, v in live['per_opp'].items()
                                                    if v['net'] < 0 or v['mean'] < 0),
                                                   key=lambda kv: (kv[1]['net'], kv[1]['mean']))
                                row = {'league': league, 'page': Path(page).name,
                                       'moveset': data['movesets'][0]['label'], 'scenario': scen,
                                       'opp_ivs': mode, 'bait': bait, 'cap': cap, 'n': live['n'],
                                       'net': live['net'], 'mean': live['mean'],
                                       'shipped_net': shipped['net'], 'shipped_mean': shipped['mean'],
                                       'top_sp_net': live_top['net'], 'top_sp_mean': live_top['mean'],
                                       'offenders': [{'opp': k, **v} for k, v in offenders[:8]],
                                       'bar_ok': live['net'] >= 0 and live['mean'] >= 0}
                                rows.append(row)
                                flag = '' if row['bar_ok'] else '  <-- FAIL'
                                print(f"{league:5s} {row['moveset']:24s} {scen} {mode:6s}/{bait:6s}/@{cap} "
                                      f"net {live['net']:+6d} (was {shipped['net']:+6d}) "
                                      f"mean {live['mean']:+7.3f} (was {shipped['mean']:+7.3f}) "
                                      f"top100 {live_top['net']:+4d}/{live_top['mean']:+6.2f} "
                                      f"[{time.time() - t0:.0f}s]{flag}", flush=True)
    finally:
        restore(saved, saved_sheet)
    fails = [r for r in rows if not r['bar_ok']]
    print(f'\n{len(rows)} slices, {len(fails)} fail the bar; stride {args.stride}; '
          f'overrides knobs={dict(knobs)} sheet={sheet}')
    for r in fails:
        offs = ', '.join(f"{o['opp']} ({o['net']:+d}, {o['mean']:+.1f})" for o in r['offenders'][:5])
        print(f"  FAIL {r['league']} {r['moveset']} {r['scenario']} {r['opp_ivs']}/{r['bait']}/@{r['cap']}: "
              f"net {r['net']:+d} mean {r['mean']:+.3f} | {offs}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({'args': vars(args), 'rows': rows}, indent=1))
        print(f'wrote {args.out}')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
