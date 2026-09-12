#!/usr/bin/env python
"""Re-simulate one Cramorant dive-tensor slice through the production
battle path, optionally under modified strategy knobs or sheet rows.

The retuning instrument (rebuilt 2026-09-12; the 2026-08-26 campaign's
mini_sweep.py lived in a scratchpad and was lost). A "slice" is one
(league, moveset page, start scenario, opponent-IV mode, bait mode) --
every opponent in the dive's pool x a sample of Cramorant's 4096 IV
spreads. Both tiers (plain PvPoke and PoGoDives) are simmed for every
cell, so the output is directly the strict-bar metrics for that slice
(net win flips and mean rating delta, plus per-opponent breakdown).

Verification discipline (from the strict-bar campaign): at SHIPPED knobs
and with --check-tensor, every simmed cell must equal the rendered page's
tensor integer-exactly, or the run aborts -- that proves the instrument
is on the production path before any variant is trusted. Stride screens
ALIAS the stamina IV axis (iv index = atk*256 + def*16 + sta, so stride 8
covers only sta {0, 8}); use a coprime stride (--stride 7, 13, 17 ...)
for screening and --stride 1 for certification.

    python scripts/cramorant_mini_sweep.py --league great \\
        --page index_m4_peck_hydro_pump_surf.html --scenario 2v2 \\
        --opp-ivs pvpoke --bait nobait --stride 13 --check-tensor
    ... --knob _POGODIVES_TANK_AGGRESSIVE=1.9 \\
        --sheet '{"(2, 2)": {"gate": "always", "tank_aggr": null, "tank_rule": "lead"}}'
    ... --opponents Corviknight,"Corviknight (Shadow)"    (subset)

Knobs are battle.py module globals; sheet rows are keys of
_POGODIVES_SHEET given as "(a, b)" strings (value null = exempt). All are
restored on exit. Runs go through gopvpsim.battle.simulate directly and
never touch the sweep cache. Output: a JSON with per-cell scores for both
tiers and a printed summary.
"""
from __future__ import annotations

import argparse
import ast
import functools
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

import gopvpsim.battle as B  # noqa: E402
from gopvpsim.battle import pogodives_dp, pvpoke_dp, simulate  # noqa: E402
from cramorant_policy_lab import make_bp  # noqa: E402
from cramorant_certify import SCENARIOS, load_page, species_from_link  # noqa: E402


def parse_knob(s):
    name, _, val = s.partition('=')
    if not hasattr(B, name):
        raise SystemExit(f'unknown knob {name}')
    return name, ast.literal_eval(val)


def apply_overrides(knobs, sheet):
    saved = {n: getattr(B, n) for n, _ in knobs}
    saved_sheet = dict(B._POGODIVES_SHEET)
    for n, v in knobs:
        setattr(B, n, v)
    for k, row in sheet.items():
        B._POGODIVES_SHEET[ast.literal_eval(k)] = row
    return saved, saved_sheet


def restore(saved, saved_sheet):
    for n, v in saved.items():
        setattr(B, n, v)
    B._POGODIVES_SHEET.clear()
    B._POGODIVES_SHEET.update(saved_sheet)


def run_slice(data, league, scenario, opp_ivs, bait, ivs, opponents=None,
              log_cells=()):
    """Return {(iv, oi): (pv, pg)} plus timelines for log_cells."""
    ms = data['movesets'][0]
    si = SCENARIOS.index(scenario)
    shields = (si // 3, si % 3)
    names = data['opponents']
    opp_idx = [i for i, n in enumerate(names) if opponents is None or n in opponents]
    if opponents is not None and len(opp_idx) != len(opponents):
        raise SystemExit(f'unknown opponent(s): {set(opponents) - set(names)}')
    pv_pol = pvpoke_dp if bait == 'bait' else functools.partial(pvpoke_dp, bait_shields=False)
    pg_pol = pogodives_dp if bait == 'bait' else functools.partial(pogodives_dp, bait_shields=False)
    out, logs = {}, {}
    for oi in opp_idx:
        link = data['oppLinks'][oi]
        mv = link['moves'].split('-')
        clean, shadow = species_from_link(link)
        opp = make_bp(clean, league, shadow, mv[0], mv[1:],
                      ivs=tuple(link['byMode'][opp_ivs]['ivs']))
        for iv in ivs:
            cram = make_bp('Cramorant', league, False, ms['fast'], ms['charged'],
                           ivs=(data['ivA'][iv], data['ivD'][iv], data['ivS'][iv]))
            want_log = (iv, oi) in log_cells
            scores = []
            for pol in (pv_pol, pg_pol):
                cram.reset_for_battle(shields[0], opp)
                opp.reset_for_battle(shields[1], cram)
                r = simulate(cram, opp, charged_policy_0=pol,
                             charged_policy_1=pvpoke_dp, log=want_log)
                scores.append(r.pvpoke_score(0))
                if want_log:
                    logs.setdefault((iv, oi), []).append(r.timeline)
            out[(iv, oi)] = tuple(scores)
    return out, logs


def summarize(cells, names):
    a = np.array([v[0] for v in cells.values()], dtype=np.int32)
    b = np.array([v[1] for v in cells.values()], dtype=np.int32)
    gained = int(((a < 500) & (b >= 500)).sum())
    lost = int(((a >= 500) & (b < 500)).sum())
    per_opp = {}
    for (iv, oi), (x, y) in cells.items():
        d = per_opp.setdefault(names[oi], [0, 0, 0.0, 0])
        d[0] += (x < 500 <= y); d[1] += (x >= 500 > y); d[2] += y - x; d[3] += 1
    return {
        'n': int(a.size), 'net': gained - lost, 'gained': gained, 'lost': lost,
        'mean': float((b - a).mean()), 'changed': int((a != b).sum()),
        'per_opp': {k: {'net': v[0] - v[1], 'mean': v[2] / v[3], 'n': v[3]}
                    for k, v in per_opp.items()},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--website', default=str(REPO / 'userdata' / 'website'))
    ap.add_argument('--league', required=True, choices=['great', 'ultra'])
    ap.add_argument('--page', default='index.html',
                    help='moveset page file name inside cramorant-<league>-league/')
    ap.add_argument('--scenario', required=True, choices=SCENARIOS)
    ap.add_argument('--opp-ivs', default='pvpoke', choices=['pvpoke', 'rank1'])
    ap.add_argument('--bait', default='bait', choices=['bait', 'nobait'])
    ap.add_argument('--stride', type=int, default=13,
                    help='IV index stride (use a coprime of 16; 1 = all 4096)')
    ap.add_argument('--iv-offset', type=int, default=0)
    ap.add_argument('--ivs', default=None,
                    help='explicit comma-separated IV indices (overrides stride)')
    ap.add_argument('--opponents', default=None,
                    help='comma-separated opponent display names (default: whole pool)')
    ap.add_argument('--knob', action='append', default=[], metavar='NAME=VALUE')
    ap.add_argument('--sheet', default=None,
                    help='JSON {"(a, b)": row-or-null} overriding _POGODIVES_SHEET rows')
    ap.add_argument('--check-tensor', action='store_true',
                    help='abort unless every cell equals the page tensor (shipped knobs only)')
    ap.add_argument('--log', default=None,
                    help='comma-separated "iv:oppname" cells to capture both timelines for')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    page = Path(args.website) / f'cramorant-{args.league}-league' / args.page
    data, tensors = load_page(page)
    names = data['opponents']
    n_opp = len(names)
    if args.ivs:
        ivs = [int(x) for x in args.ivs.split(',')]
    else:
        ivs = list(range(args.iv_offset, 4096, args.stride))
    opponents = None
    if args.opponents:
        opponents = [o.strip() for o in args.opponents.split(',')]
    log_cells = set()
    for spec in (args.log.split(',') if args.log else []):
        iv_s, _, oname = spec.partition(':')
        log_cells.add((int(iv_s), names.index(oname)))

    knobs = [parse_knob(k) for k in args.knob]
    sheet = json.loads(args.sheet) if args.sheet else {}
    if args.check_tensor and (knobs or sheet):
        raise SystemExit('--check-tensor is only meaningful at shipped knobs')
    saved, saved_sheet = apply_overrides(knobs, sheet)
    t0 = time.time()
    try:
        cells, logs = run_slice(data, args.league, args.scenario, args.opp_ivs,
                                args.bait, ivs, opponents, log_cells)
    finally:
        restore(saved, saved_sheet)
    elapsed = time.time() - t0

    si = SCENARIOS.index(args.scenario)
    bsuf = '' if args.bait == 'bait' else ':nobait'
    pv_t = tensors[f'0_{args.opp_ivs}{bsuf}'].reshape(4096, 9, n_opp)
    pg_t = tensors[f'0_{args.opp_ivs}{bsuf}:pogodives'].reshape(4096, 9, n_opp)
    tensor_cells = {k: (int(pv_t[k[0], si, k[1]]), int(pg_t[k[0], si, k[1]])) for k in cells}
    mism = [k for k in cells if cells[k] != tensor_cells[k]]
    # Baseline plain-PvPoke tier must ALWAYS match the tensor (knobs only touch pogodives).
    pv_mism = [k for k in cells if cells[k][0] != tensor_cells[k][0]]

    live = summarize(cells, names)
    shipped = summarize(tensor_cells, names)
    print(f'{args.league} {data["movesets"][0]["label"]} {args.scenario} '
          f'{args.opp_ivs}/{args.bait}: {live["n"]} cells in {elapsed:.1f}s '
          f'(stride {args.stride if not args.ivs else "explicit"})')
    if knobs or sheet:
        print(f'  overrides: knobs={dict(knobs)} sheet={sheet}')
    print(f'  SHIPPED (tensor): net {shipped["net"]:+d} mean {shipped["mean"]:+.3f}')
    print(f'  THIS RUN        : net {live["net"]:+d} mean {live["mean"]:+.3f} '
          f'changed-vs-plain {live["changed"]}')
    if pv_mism:
        print(f'  WARNING: plain-PvPoke tier differs from the tensor in {len(pv_mism)} '
              f'cells -- page is not today\'s engine/gamemaster; do not trust deltas')
    if args.check_tensor:
        print(f'  tensor check: {len(cells) - len(mism)}/{len(cells)} integer-exact')
        if mism:
            for k in mism[:10]:
                print(f'    iv={k[0]} {names[k[1]]}: live {cells[k]} tensor {tensor_cells[k]}')
            raise SystemExit('instrument is NOT on the production path; aborting')
    worst = sorted(live['per_opp'].items(), key=lambda kv: (kv[1]['net'], kv[1]['mean']))[:8]
    print('  worst opponents (this run): ' + ', '.join(
        f"{k} ({v['net']:+d}, {v['mean']:+.1f})" for k, v in worst))
    if knobs or sheet:
        delta = {k: (live['per_opp'][k]['net'] - shipped['per_opp'][k]['net'],
                     live['per_opp'][k]['mean'] - shipped['per_opp'][k]['mean'])
                 for k in live['per_opp']}
        moved = sorted((k for k in delta if delta[k] != (0, 0.0)),
                       key=lambda k: delta[k][0])
        print('  vs shipped, opponents that moved: ' + ', '.join(
            f"{k} ({delta[k][0]:+d}, {delta[k][1]:+.1f})" for k in moved[:12]))
    for (iv, oi), tls in logs.items():
        for tier, tl in zip(('plain PvPoke', 'PoGoDives'), tls):
            print(f'\n--- timeline iv={iv} ({data["ivA"][iv]}/{data["ivD"][iv]}/'
                  f'{data["ivS"][iv]}) vs {names[oi]} [{tier}] score '
                  f'{cells[(iv, oi)][0 if tier.startswith("plain") else 1]}')
            print('\n'.join(tl))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({
            'args': vars(args), 'elapsed_s': elapsed, 'live': live,
            'shipped': shipped, 'tensor_mismatches': len(mism),
            'cells': [{'iv': k[0], 'opp': names[k[1]], 'pv': v[0], 'pg': v[1],
                       'tensor_pv': tensor_cells[k][0], 'tensor_pg': tensor_cells[k][1]}
                      for k, v in cells.items()]}, indent=1))
        print(f'\nwrote {args.out}')


if __name__ == '__main__':
    main()
