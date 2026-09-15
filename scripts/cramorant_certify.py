#!/usr/bin/env python
"""Certify the PoGoDives Cramorant strategy sheet against the strict bar,
at FULL resolution, from the rendered dive pages' score tensors.

The bar (Michael, 2026-08-25; docs/validations/cramorant_strict_bar_
2026_08_26.md): for EVERY start scenario, in EVERY slice = (league x
moveset page x opponent-IV mode x bait mode x level cap), the PoGoDives
tier must be >= 0 on BOTH mean rating delta and net win flips versus the
plain-PvPoke tier. A slice-scenario is a "cell"; no negative cell ships.

Why tensors: every rendered Cramorant dive page embeds the full
4096-IV x 9-scenario x pool score tensor for both tiers, both opp-IV
modes, both bait modes and both caps (16 tensors), so the whole grid --
5 movesets x 2 leagues x 2 x 2 x 2 x 9 = 720 cells -- is a few seconds
of numpy, and it is the SAME data the pages show readers. The 2026-09-10
re-verify ran the lab instead (1 moveset, 1 IV spread, its own metric)
and could not be compared to the bar; this replaces that.

Also reported, per cell: the per-opponent offenders (any opponent whose
own net flips or mean delta is negative), a top-100-stat-product lens
(the 2026-08-26 skeptic lens), and an exemption check: scenarios the
sheet maps to None (plain PvPoke) must be byte-identical between tiers.

    python scripts/cramorant_certify.py [--website DIR] [--league both]
        [--out JSON] [--selftest N]

--selftest N re-simulates N random (IV, opponent, scenario) cells per
league through the production battle path and asserts integer equality
with the tensor -- the instrument check (stride screens alias the sta
axis, so full tensors are the only complete data; but a tensor is only
as good as its provenance, and this proves it is today's engine).
Exit code 1 if any cell fails the bar or the exemption check.
"""
from __future__ import annotations

import argparse
import base64
import glob
import gzip
import json
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

SCENARIOS = ['0v0', '0v1', '0v2', '1v0', '1v1', '1v2', '2v0', '2v1', '2v2']
OPP_IV_MODES = ('pvpoke', 'rank1')
BAITS = (('bait', ''), ('nobait', ':nobait'))
CAPS = (('50', ''), ('51', '@51'))
TOP_SP = 100


def load_page(path):
    """(data, {key: np.ndarray[4096*9*n_opp] uint16}) from a dive page."""
    html = Path(path).read_text()
    m = re.search(r'<script>var DATA = (\{.*?\});\nvar SCORES_GZ = (\{.*?\});\n',
                  html, re.S)
    if not m:
        raise SystemExit(f'{path}: no DATA/SCORES_GZ block')
    data = json.loads(m.group(1))
    tensors = {}
    for k, b64 in json.loads(m.group(2)).items():
        raw = gzip.decompress(base64.b64decode(b64))
        tensors[k] = np.frombuffer(raw, dtype='<u2')
    return data, tensors


def species_from_link(link):
    """(speciesName, is_shadow) for a dive-page oppLink, via its PvPoke
    speciesId -- robust to moveset-variant display names such as
    'Thievul (Sucker Punch / Night Slash+Icy Wind)'."""
    from gopvpsim.data import load_gamemaster
    sid = link['id']
    shadow = sid.endswith('_shadow')
    if shadow:
        sid = sid[:-len('_shadow')]
    by_id = species_from_link._by_id
    if by_id is None:
        by_id = species_from_link._by_id = {
            p['speciesId']: p['speciesName'] for p in load_gamemaster()['pokemon']}
    return by_id[sid], shadow


species_from_link._by_id = None


def exempt_scenarios():
    """Start scenarios the shipped sheet maps to None (plain PvPoke)."""
    from gopvpsim.battle import _POGODIVES_SHEET
    return {f'{a}v{b}' for (a, b), row in _POGODIVES_SHEET.items()
            if row is None}


def cell_stats(pv, pg, n_opp, si, iv_mask=None):
    """Bar metrics for one scenario: pv/pg are [4096, 9, n_opp] views."""
    a = pv[:, si, :]
    b = pg[:, si, :]
    if iv_mask is not None:
        a, b = a[iv_mask], b[iv_mask]
    a = a.astype(np.int32)
    b = b.astype(np.int32)
    gained = int(((a < 500) & (b >= 500)).sum())
    lost = int(((a >= 500) & (b < 500)).sum())
    return {'net': gained - lost, 'gained': gained, 'lost': lost,
            'mean': float((b - a).mean()),
            'changed': int((a != b).sum()),
            'cells': int(a.size)}


def per_opponent(pv, pg, opponents, si):
    a = pv[:, si, :].astype(np.int32)
    b = pg[:, si, :].astype(np.int32)
    out = []
    for oi, name in enumerate(opponents):
        x, y = a[:, oi], b[:, oi]
        net = int(((x < 500) & (y >= 500)).sum()) - int(((x >= 500) & (y < 500)).sum())
        mean = float((y - x).mean())
        if net < 0 or mean < 0:
            out.append({'opp': name, 'net': net, 'mean': round(mean, 3)})
    return sorted(out, key=lambda d: (d['net'], d['mean']))


def certify_page(path, league, exempt):
    data, tensors = load_page(path)
    n_opp = len(data['opponents'])
    shape = (4096, 9, n_opp)
    ms = data['movesets'][0]['label']
    sp = np.asarray(data['spRanks'])
    top = sp <= TOP_SP
    cells = []
    for mode in OPP_IV_MODES:
        for bait, bsuf in BAITS:
            for cap, csuf in CAPS:
                kpv = f'0_{mode}{bsuf}{csuf}'
                kpg = f'0_{mode}{bsuf}:pogodives{csuf}'
                if kpv not in tensors or kpg not in tensors:
                    raise SystemExit(f'{path}: missing tensor {kpv} / {kpg}')
                pv = tensors[kpv].reshape(shape)
                pg = tensors[kpg].reshape(shape)
                for si, scen in enumerate(SCENARIOS):
                    st = cell_stats(pv, pg, n_opp, si)
                    st_top = cell_stats(pv, pg, n_opp, si, top)
                    cell = {
                        'league': league, 'moveset': ms, 'page': Path(path).name,
                        'opp_ivs': mode, 'bait': bait, 'cap': cap,
                        'scenario': scen, **st,
                        'top_sp_net': st_top['net'], 'top_sp_mean': st_top['mean'],
                        'exempt': scen in exempt,
                        'offenders': per_opponent(pv, pg, data['opponents'], si),
                    }
                    cell['bar_ok'] = st['net'] >= 0 and st['mean'] >= 0
                    cell['exempt_ok'] = (not cell['exempt']) or st['changed'] == 0
                    cells.append(cell)
    return cells


def selftest(path, league, n, seed=0):
    """Re-sim n random cells per tier and compare with the tensor."""
    from gopvpsim.battle import pogodives_dp, pvpoke_dp, simulate
    from cramorant_policy_lab import make_bp
    data, tensors = load_page(path)
    n_opp = len(data['opponents'])
    shape = (4096, 9, n_opp)
    rng = np.random.default_rng(seed)
    ms = data['movesets'][0]
    bad = 0
    for _ in range(n):
        iv = int(rng.integers(4096)); oi = int(rng.integers(n_opp))
        si = int(rng.integers(9)); mode = OPP_IV_MODES[int(rng.integers(2))]
        bait, bsuf = BAITS[int(rng.integers(2))]
        pv = tensors[f'0_{mode}{bsuf}'].reshape(shape)
        pg = tensors[f'0_{mode}{bsuf}:pogodives'].reshape(shape)
        cram = make_bp('Cramorant', league, False, ms['fast'], ms['charged'],
                       ivs=(data['ivA'][iv], data['ivD'][iv], data['ivS'][iv]))
        link = data['oppLinks'][oi]
        mv = link['moves'].split('-')
        clean, shadow = species_from_link(link)
        opp = make_bp(clean, league, shadow, mv[0], mv[1:],
                      ivs=tuple(link['byMode'][mode]['ivs']))
        shields = (si // 3, si % 3)
        got = []
        for pol in (pvpoke_dp, pogodives_dp):
            cram.reset_for_battle(shields[0], opp)
            opp.reset_for_battle(shields[1], cram)
            import functools
            cp = pol if bait == 'bait' else functools.partial(pol, bait_shields=False)
            r = simulate(cram, opp, charged_policy_0=cp, charged_policy_1=pvpoke_dp)
            got.append(r.pvpoke_score(0))
        want = (int(pv[iv, si, oi]), int(pg[iv, si, oi]))
        if tuple(got) != want:
            bad += 1
            print(f'  SELFTEST MISMATCH {league} {ms["label"]} iv={iv} '
                  f'{data["opponents"][oi]} {SCENARIOS[si]} {mode}/{bait}: '
                  f'tensor {want} live {tuple(got)}')
    print(f'  selftest {league} {Path(path).name}: {n - bad}/{n} cells '
          f'integer-exact')
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--website', default=str(REPO / 'userdata' / 'website'))
    ap.add_argument('--league', default='both', choices=['great', 'ultra', 'both'])
    ap.add_argument('--out', default=None, help='JSON path for the full cell list')
    ap.add_argument('--selftest', type=int, default=0, metavar='N',
                    help='re-sim N random cells per page against the tensor')
    args = ap.parse_args()
    leagues = ['great', 'ultra'] if args.league == 'both' else [args.league]
    exempt = exempt_scenarios()
    cells, selftest_bad = [], 0
    for league in leagues:
        pages = sorted(glob.glob(f'{args.website}/cramorant-{league}-league/index*.html'))
        if not pages:
            raise SystemExit(f'no rendered cramorant-{league}-league pages under {args.website}')
        for p in pages:
            cells.extend(certify_page(p, league, exempt))
            if args.selftest:
                selftest_bad += selftest(p, league, args.selftest)

    fails = [c for c in cells if not c['bar_ok']]
    exempt_fails = [c for c in cells if not c['exempt_ok']]
    live = [c for c in cells if not c['exempt']]
    print(f'\n{len(cells)} cells ({len(live)} live-row, {len(cells) - len(live)} exempt); '
          f'exempt scenarios: {sorted(exempt)}')
    print(f'bar failures: {len(fails)}   exemption violations: {len(exempt_fails)}')
    # Per-scenario roll-up across slices: worst mean / worst net / total net.
    print(f"\n{'league':6s} {'scen':4s} {'slices':>6s} {'min mean':>9s} {'min net':>8s} "
          f"{'total net':>10s} {'min top100 mean':>15s} {'min top100 net':>14s}")
    for league in leagues:
        for scen in SCENARIOS:
            cs = [c for c in cells if c['league'] == league and c['scenario'] == scen]
            print(f"{league:6s} {scen:4s} {len(cs):6d} {min(c['mean'] for c in cs):9.3f} "
                  f"{min(c['net'] for c in cs):8d} {sum(c['net'] for c in cs):10d} "
                  f"{min(c['top_sp_mean'] for c in cs):15.3f} "
                  f"{min(c['top_sp_net'] for c in cs):14d}")
    if fails:
        print('\nFAILING CELLS (bar):')
        for c in sorted(fails, key=lambda c: (c['net'], c['mean'])):
            offs = ', '.join(f"{o['opp']} ({o['net']:+d}, {o['mean']:+.2f})"
                             for o in c['offenders'][:6])
            print(f"  {c['league']} {c['moveset']:18s} {c['opp_ivs']}/{c['bait']}/@{c['cap']} "
                  f"{c['scenario']}: net {c['net']:+d} mean {c['mean']:+.3f}  offenders: {offs}")
    if exempt_fails:
        print('\nEXEMPTION VIOLATIONS (tiers differ in a None row):')
        for c in exempt_fails:
            print(f"  {c['league']} {c['moveset']} {c['opp_ivs']}/{c['bait']}/@{c['cap']} "
                  f"{c['scenario']}: {c['changed']} cells differ")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {'cells': cells, 'exempt': sorted(exempt),
             'bar_failures': len(fails), 'exemption_violations': len(exempt_fails),
             'selftest_mismatches': selftest_bad}, indent=1))
        print(f'\nwrote {args.out}')
    sys.exit(1 if (fails or exempt_fails or selftest_bad) else 0)


if __name__ == '__main__':
    main()
