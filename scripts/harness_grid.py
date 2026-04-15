#!/usr/bin/env python3
"""Harness-driven divergence grid: our sim vs PvPoke's Battle.simulate.

Samples top-N meta pairs per league, runs each matchup through both
scripts/pvpoke_trace.js (PvPoke reference) and gopvpsim.battle.simulate
(ours) across all 9 shield scenarios, and emits a JSON + summary of
score deltas and winner flips.

Run:
    python scripts/harness_grid.py --league great --top 10 --out /tmp/grid_gl.json
    python scripts/harness_grid.py --league ultra --top 8  --out /tmp/grid_ul.json

IV choice: rank-1 (max stat-product under CP cap) per species, computed
locally via gopvpsim.pokemon.iv_rank and passed to BOTH systems, so any
delta reflects sim/DP/policy divergence, not stat-calc drift.

Movesets: PvPoke's rankings `moveset` field (fast + 2 charged).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))

from gopvpsim.data import load_rankings, load_gamemaster, parse_types
from gopvpsim.pokemon import Pokemon, iv_rank, LEAGUE_CP
from gopvpsim.moves import get_moves
from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp

DEFAULT_PVPOKE_ROOT = Path.home() / 'coding' / 'MGLPoGo' / 'pvpoke'
HARNESS = REPO / 'scripts' / 'pvpoke_trace.js'


@dataclass
class Spec:
    species_id:    str
    species_name:  str
    fast:          str
    charged:       tuple
    atk_iv:        int
    def_iv:        int
    sta_iv:        int


def pick_top_species(league: str, top_n: int) -> list[dict]:
    """Return top-N non-shadow species (rankings entries)."""
    rankings = load_rankings(league)
    picked = []
    seen = set()
    for entry in rankings:
        sid = entry['speciesId']
        if sid.endswith('_shadow'):
            continue
        if sid in seen:
            continue
        seen.add(sid)
        picked.append(entry)
        if len(picked) >= top_n:
            break
    return picked


def build_spec(entry: dict, league: str) -> Spec:
    """Pick rank-1 IVs for a species entry + its PvPoke default moveset."""
    # rankings `moveset` = [fast, c1, c2]
    moveset = entry['moveset']
    fast = moveset[0]
    charged = tuple(moveset[1:])
    # Pick rank-1 IVs by stat product (mirrors PvPoke's default IV rank for
    # non-CMP-optimized cohorts). Cache the iv_rank result implicitly.
    species_name = entry['speciesName']
    ranks = iv_rank(species_name, league=league)
    # iv_rank returns entries sorted by stat_product descending
    ranks.sort(key=lambda r: -r['stat_product'])
    top = ranks[0]
    return Spec(
        species_id=entry['speciesId'],
        species_name=species_name,
        fast=fast,
        charged=charged,
        atk_iv=top['atk_iv'],
        def_iv=top['def_iv'],
        sta_iv=top['sta_iv'],
    )


def run_harness(spec1: Spec, spec2: Spec, shields: tuple,
                cp: int, pvpoke_root: Path) -> dict:
    cmd = [
        'node', str(HARNESS),
        '--pvpoke-root', str(pvpoke_root),
        '--cp', str(cp),
        '--p1', spec1.species_id,
        '--p1-fast', spec1.fast,
        '--p1-charged', ','.join(spec1.charged),
        '--p1-ivs', f'{spec1.atk_iv}/{spec1.def_iv}/{spec1.sta_iv}',
        '--p1-shields', str(shields[0]),
        '--p2', spec2.species_id,
        '--p2-fast', spec2.fast,
        '--p2-charged', ','.join(spec2.charged),
        '--p2-ivs', f'{spec2.atk_iv}/{spec2.def_iv}/{spec2.sta_iv}',
        '--p2-shields', str(shields[1]),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f'harness failed: {proc.stderr[:400]}')
    return json.loads(proc.stdout)


def make_bp(spec: Spec, league: str, shields: int,
            fast_moves, charged_moves, gm) -> BattlePokemon:
    poke = Pokemon.at_best_level(spec.species_name, spec.atk_iv, spec.def_iv,
                                 spec.sta_iv, league=league)
    mon = next((m for m in gm['pokemon']
                if m['speciesName'] == spec.species_name), None)
    if mon is None:
        raise KeyError(f'species not found in gamemaster: {spec.species_name}')
    types = parse_types(mon)
    fm = dict(fast_moves[spec.fast])
    cms = [dict(charged_moves[c]) for c in spec.charged]
    return BattlePokemon(
        species=spec.species_name, types=types,
        atk=poke.atk, def_=poke.def_, max_hp=poke.hp,
        fast_move=fm, charged_moves=cms, shields=shields,
    )


def run_ours(spec1: Spec, spec2: Spec, shields: tuple,
             league: str, ctx) -> dict:
    fast_moves, charged_moves, gm = ctx
    bp1 = make_bp(spec1, league, shields[0], fast_moves, charged_moves, gm)
    bp2 = make_bp(spec2, league, shields[1], fast_moves, charged_moves, gm)
    res = simulate(bp1, bp2,
                   charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)
    return {
        'score':  [int(res.pvpoke_score(0)), int(res.pvpoke_score(1))],
        'winner': res.winner if res.winner is not None else -1,
        'turns':  res.turns,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--league', choices=['great', 'ultra'], default='great')
    ap.add_argument('--top', type=int, default=10,
                    help='Use top-N species (pairwise, C(N,2) pairs)')
    ap.add_argument('--shields', choices=['all', 'even'], default='all',
                    help="all=9 scenarios; even=3 symmetric (0-0,1-1,2-2)")
    ap.add_argument('--pvpoke-root', type=Path, default=DEFAULT_PVPOKE_ROOT)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--limit-pairs', type=int, default=0,
                    help='Stop after N pairs (0=all)')
    args = ap.parse_args()

    if not args.pvpoke_root.exists():
        sys.exit(f'PvPoke root not found: {args.pvpoke_root}')

    cp = LEAGUE_CP[args.league]
    print(f'== Loading top-{args.top} {args.league} meta ==', flush=True)
    entries = pick_top_species(args.league, args.top)
    specs = [build_spec(e, args.league) for e in entries]
    for s in specs:
        print(f'   {s.species_id:30s} {s.fast}/{",".join(s.charged):30s} '
              f'ivs={s.atk_iv}/{s.def_iv}/{s.sta_iv}')

    pairs = list(itertools.combinations(range(len(specs)), 2))
    if args.limit_pairs:
        pairs = pairs[:args.limit_pairs]
    if args.shields == 'all':
        shield_pairs = [(a, b) for a in range(3) for b in range(3)]
    else:
        shield_pairs = [(0, 0), (1, 1), (2, 2)]

    fast_moves, charged_moves = get_moves()
    gm = load_gamemaster()
    ctx = (fast_moves, charged_moves, gm)

    n_sims = len(pairs) * len(shield_pairs)
    print(f'== Running {len(pairs)} pairs × {len(shield_pairs)} shields = {n_sims} sims ==',
          flush=True)

    results = []
    t0 = time.time()
    done = 0
    for (i, j) in pairs:
        s1, s2 = specs[i], specs[j]
        for sh in shield_pairs:
            try:
                ours = run_ours(s1, s2, sh, args.league, ctx)
            except Exception as e:
                ours = {'error': str(e)}
            try:
                pv = run_harness(s1, s2, sh, cp, args.pvpoke_root)
            except Exception as e:
                pv = {'error': str(e)}
            rec = {
                'league':   args.league,
                'p1':       s1.species_id,
                'p2':       s2.species_id,
                'shields':  list(sh),
                'ours':     ours,
                'pvpoke':   {k: pv.get(k) for k in ('score', 'winner', 'turns')}
                            if 'error' not in pv else pv,
            }
            # Delta/winner-flip summary
            if 'error' not in ours and 'error' not in pv:
                rec['delta_p1'] = ours['score'][0] - pv['score'][0]
                rec['delta_p2'] = ours['score'][1] - pv['score'][1]
                rec['winner_flip'] = (ours['winner'] != pv['winner'])
                rec['sum_ours'] = sum(ours['score'])
                rec['sum_pv']   = sum(pv['score'])
            results.append(rec)
            done += 1
            if done % 20 == 0 or done == n_sims:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 0
                eta = (n_sims - done) / rate if rate else 0
                print(f'   [{done:4d}/{n_sims}]  {elapsed:5.1f}s elapsed  '
                      f'{rate:5.2f} sims/s  ETA {eta:5.1f}s', flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        'league':  args.league,
        'top':     args.top,
        'specs':   [asdict(s) for s in specs],
        'results': results,
    }, indent=2))
    print(f'\nWrote {args.out}  ({len(results)} records)', flush=True)

    # Quick summary
    ok = [r for r in results
          if 'delta_p1' in r and 'error' not in r.get('ours', {})
          and 'error' not in r.get('pvpoke', {})]
    if not ok:
        print('No successful sims to summarize.')
        return
    big_delta = [r for r in ok if abs(r['delta_p1']) > 20]
    flips     = [r for r in ok if r['winner_flip']]
    print(f'\n== Summary ({len(ok)}/{len(results)} OK) ==')
    print(f'   winner flips:         {len(flips):3d}  ({100*len(flips)/len(ok):.1f}%)')
    print(f'   |delta_p1|>20:        {len(big_delta):3d}  ({100*len(big_delta)/len(ok):.1f}%)')
    print(f'   |delta_p1|>50:        {sum(1 for r in ok if abs(r["delta_p1"])>50):3d}')
    print(f'   max |delta_p1|:       {max(abs(r["delta_p1"]) for r in ok):3d}')
    # Top-5 biggest deltas
    biggest = sorted(ok, key=lambda r: -abs(r['delta_p1']))[:10]
    print('\n   top-10 deltas:')
    for r in biggest:
        flip = '  FLIP' if r['winner_flip'] else ''
        print(f'     {r["p1"]:22s} vs {r["p2"]:22s}  sh={r["shields"]}  '
              f'ours={r["ours"]["score"]}  pv={r["pvpoke"]["score"]}  '
              f'd1={r["delta_p1"]:+4d}{flip}')


if __name__ == '__main__':
    main()
