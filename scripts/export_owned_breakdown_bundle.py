#!/usr/bin/env python
"""Bake the owned-mon breakdown artifact for gobattlekit by EXTRACTING per-IV
dropped-vs-rank-1 matchups from already-rendered deep-dive HTML -- no re-sim.

Each dive embeds the full 4096-IV x scenario x opponent score grid (SCORES_GZ).
For every IV we emit the matchups the rank-1 spread wins but this IV loses (even
shields), against the dive's default opponents (moveset 0, oppIvMode 'pvpoke',
baiting on) -- the same view the website "Gives up vs #1" column uses, so the
two agree. The on-device screen looks up an owned mon's IV in this artifact.

Convention note: this uses the DIVE's opponents (their PvPoke-default IVs), so
it matches the website column. The Python CLI (owned_breakdown.py) uses
opponents at 15/15/15 (the iv_envelope convention) and will differ slightly.

Compact: only IVs that actually drop something are stored; an IV absent from
`drops` gives up nothing vs rank-1.

Output JSON: {"<League> League": {"<species>": {
  "rank1": [a, d, h],
  "drops": {"a/d/h": ["Opp shf-sho", ...], ...}   # non-empty only
}}}

Usage:
  python scripts/export_owned_breakdown_bundle.py --out userdata/breakdown_bundle.json \\
      userdata/website/tinkaton-great-league/index.html ...
  # default: every userdata/website/*/index.html landing dive
"""
import argparse
import base64
import glob
import gzip
import json
import os
import struct

EVEN = {(0, 0), (1, 1), (2, 2)}


def parse_dive(path):
    h = open(path).read()
    i = h.index('var DATA = ') + len('var DATA = ')
    j = h.index(';\nvar SCORES_GZ = ')
    data = json.loads(h[i:j])
    k = j + len(';\nvar SCORES_GZ = ')
    m = h.index(';\n', k)
    sgz = json.loads(h[k:m])
    return data, sgz


def decode(b64):
    raw = gzip.decompress(base64.b64decode(b64))
    return struct.unpack(f'<{len(raw) // 2}H', raw)


def breakdown_from_dive(path):
    data, sgz = parse_dive(path)
    key = (next((k for k in sgz if k.endswith('_pvpoke')), None)
           or next(iter(sgz)))
    scores = decode(sgz[key])
    nO, nS = data['nOpponents'], data['nScenarios']
    opps = data.get('opponentsDisplay') or data['opponents']
    scen = data['scenarios']
    ref = data['rank1RefIvIdx']
    even_idx = [si for si, sc in enumerate(scen) if tuple(sc) in EVEN]

    def winset(iv):
        base = iv * nS * nO
        return {(oi, si) for si in even_idx for oi in range(nO)
                if scores[base + si * nO + oi] > 500}  # 500 = tie, not a win

    refw = winset(ref)
    drops = {}
    for iv in range(data['nIvs']):
        lost = refw - winset(iv)
        if not lost:
            continue
        a, d, s = data['ivA'][iv], data['ivD'][iv], data['ivS'][iv]
        drops[f"{a}/{d}/{s}"] = sorted(
            f"{opps[oi]} {scen[si][0]}-{scen[si][1]}" for (oi, si) in lost)
    rank1 = [data['ivA'][ref], data['ivD'][ref], data['ivS'][ref]]
    return data['species'], data['league'], {'rank1': rank1, 'drops': drops}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dives', nargs='*',
                    help='dive landing HTML files (default: all website landings)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    dives = a.dives or glob.glob(os.path.join('userdata', 'website', '*', 'index.html'))
    bundle = {}
    for path in sorted(dives):
        try:
            species, league, entry = breakdown_from_dive(path)
        except (ValueError, KeyError) as e:
            print(f"skip {path}: {type(e).__name__} {e}")
            continue
        section = bundle.setdefault(f"{league.capitalize()} League", {})
        section[species] = entry
        print(f"{species} ({league}): {len(entry['drops'])} IVs give up something")

    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(bundle, f, separators=(',', ':'))
    size = os.path.getsize(a.out)
    print(f"\nwrote {a.out} ({size / 1024:.0f} KB, "
          f"{sum(len(v) for v in bundle.values())} species)")


if __name__ == '__main__':
    main()
