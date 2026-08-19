#!/usr/bin/env python
"""Probe-expansion FN screen for the Worlds non-amber ("clean") pairs.

The Tier-1 amber screen tests TWO focal probe spreads (rank-1 SP,
max-atk-in-top-512) and has a MEASURED false-negative rate: 4 of 21
sampled clean pairs turned amber under full Tier-2 grids (~19%), which
the hub discloses. This screen re-tests every currently-clean pair with
EXTRA extreme focal probes; any new within-cohort mix or probe-flip is
amber evidence the two standard probes missed. More probes can only ADD
ambers (monotone) -- existing planes and pages are not touched.

Extra probes per focal (from the full 4096 iv_rank table, deduped):
  max-atk, max-def, max-hp, worst-SP (rank 4096), mid-SP (rank 2048).
Cohorts, scenarios, bait modes and the amber rules match
worlds_render_data (within-cohort mix; opposite-uniform probe flip --
here ANY pair of probes incl. the two standard ones, whose per-scenario
fracs are read from the existing Tier-1 planes).

Output: userdata/worlds_probe_expand/results.json + a printed table of
pairs that WOULD flip amber. Decisions about re-tagging pages/hub stay
with Michael (this script changes no shipped artifact).

Usage:
    python scripts/worlds_probe_expand.py [--workers N] [--limit N]
"""
import argparse
import json
import multiprocessing as mp
import pathlib
import sys
import time

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from deep_dive_lib.robustness import plane_task_worker  # noqa: E402
import worlds_bake as wb  # noqa: E402
import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402

from gopvpsim.pokemon import iv_rank  # noqa: E402

OUT_DIR = REPO / 'userdata' / 'worlds_probe_expand'


def extra_probes(species, shadow):
    """Extreme focal spreads beyond the two standard probes, deduped,
    with stable labels. All from the FULL 4096 table -- the point is to
    reach corners the top-512 convention never samples."""
    ranked = iv_rank(species, league='great', shadow=shadow)
    picks = {
        'max_atk': max(ranked, key=lambda e: e['atk']),
        'max_def': max(ranked, key=lambda e: e['def_']),
        'max_hp': max(ranked, key=lambda e: e['hp']),
        'worst_sp': ranked[-1],
        'mid_sp': ranked[2047],
    }
    std = set()
    for e in (ranked[0],
              max(ranked[:512], key=lambda x: x['atk'])):
        std.add((e['atk_iv'], e['def_iv'], e['sta_iv']))
    out, seen = [], set(std)
    for tag, e in picks.items():
        iv = (e['atk_iv'], e['def_iv'], e['sta_iv'])
        if iv in seen:
            continue
        seen.add(iv)
        out.append((tag, iv))
    return out


def clean_pairs(entries):
    cells = wrd.build_all_cells(entries)
    n_missing, missing = wrd.coverage_check(cells, entries)
    if n_missing:
        sys.exit(f'ABORT: Tier-1 planes incomplete ({n_missing} missing)')
    amber = {tuple(sorted(k)) for k, c in cells.items()
             if not c.missing and c.amber}
    every = {tuple(sorted(k)) for k in cells}
    return sorted(every - amber), cells


def standard_probe_fracs(cell):
    """Per (spread_tag, cohort, bait) -> frac(9,) from the Tier-1 planes,
    so probe-flips can be tested against the standard probes too."""
    return {(s, c, b): sl.frac
            for (s, c, b), sl in cell.slices.items()}


def _task(args):
    focal, opp, bait, probes, cohort_info = args
    union, t_mask, a_mask = cohort_info
    task = {
        'focal_species': focal['species'],
        'focal_fast': focal['moveset'][0],
        'focal_charged': focal['moveset'][1],
        'focal_shadow': focal['shadow'],
        'focal_spreads': [iv for _, iv in probes],
        'opponent': opp['species'],
        'opp_fast': opp['moveset'][0],
        'opp_charged': opp['moveset'][1],
        'opp_shadow': opp['shadow'],
        'league': 'great',
        'scenarios': list(wb.SCENARIOS),
        'cohort': union,
        'bait': bait,
    }
    won, _score, n_sims = plane_task_worker(task)
    fr = {}
    for ctag, mask in (('top512', np.asarray(t_mask, bool)),
                       ('atkband', np.asarray(a_mask, bool))):
        if mask.sum() == 0:
            continue
        fr[ctag] = won[:, mask, :].mean(axis=1)   # (n_probes, 9)
    return fr, n_sims


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=None,
                    help='screen only the first N clean pairs (smoke)')
    args = ap.parse_args()

    meta = wrd.load_meta()
    entries = meta['entries']
    by_id = {e['species_id']: e for e in entries}
    pairs, cells = clean_pairs(entries)
    if args.limit:
        pairs = pairs[:args.limit]
    print(f'{len(pairs)} clean pairs to re-screen with extra probes')

    resolved = {}

    def resolve(sid):
        if sid not in resolved:
            e = by_id[sid]
            resolved[sid] = {
                'species': e['species'], 'shadow': e['shadow'],
                'moveset': (e['fast_move_id'], list(e['charged_move_ids'])),
                'probes': extra_probes(e['species'], e['shadow']),
                'cohort': wb.cohort_indices(e['species'], e['shadow']),
            }
        return resolved[sid]

    work = []
    for a, b in pairs:
        for focal_id, opp_id in ((a, b), (b, a)):
            f, o = resolve(focal_id), resolve(opp_id)
            for bait in (True, False):
                work.append(((a, b), focal_id, opp_id, bait,
                             (f, o['species'], o)))

    t0 = time.time()
    results = {}
    total = 0
    with mp.Pool(args.workers) as pool:
        payloads = [( _w[4][0], _w[4][2], _w[3],
                      _w[4][0]['probes'], _w[4][2]['cohort'])
                    for _w in work]
        for (pair, focal_id, opp_id, bait, _), (fr, n) in zip(
                work, pool.imap(_task, payloads)):
            total += n
            key = f'{focal_id}|{opp_id}|{"bait" if bait else "nobait"}'
            results[key] = {'pair': list(pair),
                            'fracs': {c: v.tolist() for c, v in fr.items()}}
    print(f'{total:,} sims in {time.time() - t0:,.0f}s')

    # Amber evaluation per pair: new mixes + probe flips (vs each other
    # AND vs the standard probes' fracs from the Tier-1 planes).
    flips = {}
    for (a, b) in pairs:
        findings = []
        for focal_id, opp_id in ((a, b), (b, a)):
            probes = resolve(focal_id)['probes']
            cell = cells[(focal_id, opp_id)]
            std = standard_probe_fracs(cell)
            for bait in (True, False):
                key = f'{focal_id}|{opp_id}|{"bait" if bait else "nobait"}'
                fr = results.get(key, {}).get('fracs', {})
                for ctag, mat in fr.items():
                    mat = np.asarray(mat)
                    for pi, (tag, iv) in enumerate(probes):
                        for si in range(9):
                            v = float(mat[pi, si])
                            if 0.0 < v < 1.0:
                                findings.append({
                                    'dir': f'{focal_id}->{opp_id}',
                                    'bait': bait, 'cohort': ctag,
                                    'probe': tag, 'ivs': list(iv),
                                    'scenario': si, 'kind': 'mix',
                                    'frac': v})
                    # probe flips: any two probes (extra x extra, or
                    # extra x standard) on opposite uniform outcomes
                    all_fracs = [(f'x:{tag}', np.asarray(mat[pi]))
                                 for pi, (tag, _) in enumerate(probes)]
                    for (stag, sc, sb), f9 in std.items():
                        if sc == ctag and sb == bait:
                            all_fracs.append((f's:{stag}', np.asarray(f9)))
                    for i in range(len(all_fracs)):
                        for j in range(i + 1, len(all_fracs)):
                            ta, fa = all_fracs[i]
                            tb, fb = all_fracs[j]
                            for si in range(9):
                                if {float(fa[si]), float(fb[si])} == {0.0, 1.0}:
                                    findings.append({
                                        'dir': f'{focal_id}->{opp_id}',
                                        'bait': bait, 'cohort': ctag,
                                        'probe': f'{ta} vs {tb}',
                                        'scenario': si, 'kind': 'flip'})
        if findings:
            flips[f'{a}|{b}'] = findings

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'results.json'
    out.write_text(json.dumps({
        'clean_pairs_screened': [list(p) for p in pairs],
        'extra_probe_tags': ['max_atk', 'max_def', 'max_hp', 'worst_sp',
                             'mid_sp'],
        'would_flip_amber': flips,
        'raw': results,
    }, indent=1))
    print(f'\n{len(flips)} of {len(pairs)} clean pairs WOULD FLIP AMBER '
          f'with the extra probes:')
    for pk, fs in sorted(flips.items()):
        kinds = {}
        for f in fs:
            kinds[f['kind']] = kinds.get(f['kind'], 0) + 1
        print(f'  {pk}: {len(fs)} finding(s) {kinds}')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
