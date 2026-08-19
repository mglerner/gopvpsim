#!/usr/bin/env python
"""Worlds robustness deep-dive shortlist: amber pairs ranked by combined usage.

Ranks every IV-decided (amber) Worlds pair by COMBINED recent usage
(usage_recent_pct[a] + usage_recent_pct[b]) to pick candidates for the
Thievul-grade joint-IV robustness treatment (docs/joint_iv_reuse_plan.md).

NB this deliberately differs from ``worlds_tier2.amber_worklist``'s bake
ordering (max usage, ties by sum): the bake wanted "the most-played mon's
pairs first"; the shortlist wants "the most-played MATCHUP first".

The amber set is recomputed from the Tier-1 planes (the same authority
the Tier-2 bake used) and cross-checked against the Tier-2 manifest's
amber set (baked non-clean-sample pairs). A disagreement is printed and
flagged per-row, never silently dropped.

Interestingness columns per row:
- which directions are amber and how many of the 9 scenarios each,
- SPREAD-FLIP marker (probe spreads land on opposite uniform outcomes --
  pure focal-IV decidedness),
- "closest split": the cohort fraction nearest 0.5 across every slice of
  both directions (0.50 = maximally contested; 0.99 = one stray spread).

Usage:
    python scripts/worlds_shortlist.py [--top N] [--md FILE]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import worlds_render_data as wrd
import worlds_tier2 as wt2


def manifest_amber_pairs(manifest):
    """Unordered amber pairs implied by the Tier-2 manifest: every baked
    pair not tagged clean_sample (the FN-measurement sample)."""
    pairs = set()
    for key, entry in manifest.get('entries', {}).items():
        focal, opp, _bait = key.rsplit('|', 2)
        if not entry.get('clean_sample', False):
            pairs.add(tuple(sorted((focal, opp))))
    return pairs


def _dir_info(cell):
    """(is_amber, n_amber_scenarios, closest_split) for one direction."""
    closest = None
    for s in cell.slices.values():
        for f in s.frac:
            f = float(f)
            if 0.0 < f < 1.0 and (closest is None
                                  or abs(f - 0.5) < abs(closest - 0.5)):
                closest = f
    return cell.amber, len(cell.amber_scenarios()), closest


def shortlist_rows(entries, cells, manifest_pairs=None):
    """Ranked shortlist rows (dicts), combined recent usage descending."""
    usage = {e['species_id']: e['usage_recent_pct'] for e in entries}
    name = {e['species_id']: e['name'] for e in entries}
    badge = {e['species_id']: e['badge'] for e in entries}
    amber = sorted({tuple(sorted(k)) for k, c in cells.items()
                    if not c.missing and c.amber})
    rows = []
    for a, b in amber:
        ab, ba = cells[(a, b)], cells[(b, a)]
        ab_amber, ab_n, ab_close = _dir_info(ab)
        ba_amber, ba_n, ba_close = _dir_info(ba)
        splits = [x for x in (ab_close, ba_close) if x is not None]
        rows.append({
            'pair': (a, b),
            'names': (name[a], name[b]),
            'badges': (badge[a], badge[b]),
            'usage': (usage[a], usage[b]),
            'combined': usage[a] + usage[b],
            'amber_dirs': (ab_amber, ba_amber),
            'amber_scen': (ab_n, ba_n),
            'spread_flip': bool(ab.spread_flip_scenarios()
                                or ba.spread_flip_scenarios()),
            'closest_split': (min(splits, key=lambda f: abs(f - 0.5))
                              if splits else None),
            'in_tier2': (manifest_pairs is None
                         or tuple(sorted((a, b))) in manifest_pairs),
        })
    rows.sort(key=lambda r: (-r['combined'], -max(r['usage']), r['pair']))
    return rows


def format_table(rows, top=None):
    lines = []
    header = (f"{'#':>3}  {'pair':<42} {'comb%':>6} {'usage%':>11} "
              f"{'dirs':>4} {'scen':>5} {'flip':>4} {'split':>5}  t2")
    lines.append(header)
    lines.append('-' * len(header))
    for i, r in enumerate(rows[:top] if top else rows, 1):
        dirs = ('<>' if all(r['amber_dirs'])
                else '->' if r['amber_dirs'][0] else '<-')
        split = (f"{r['closest_split']:.2f}"
                 if r['closest_split'] is not None else '--')
        lines.append(
            f"{i:>3}  {r['names'][0] + ' / ' + r['names'][1]:<42} "
            f"{r['combined']:>6.1f} "
            f"{r['usage'][0]:>5.1f}+{r['usage'][1]:<5.1f} "
            f"{dirs:>4} {r['amber_scen'][0]}+{r['amber_scen'][1]:<3} "
            f"{'Y' if r['spread_flip'] else '.':>4} {split:>5}  "
            f"{'ok' if r['in_tier2'] else 'MISSING'}")
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--top', type=int, default=None,
                    help='print only the top N rows (default: all)')
    ap.add_argument('--md', type=Path, default=None,
                    help='also write the full table to FILE as markdown')
    args = ap.parse_args()

    meta = wrd.load_meta()
    entries = meta['entries']
    cells = wrd.build_all_cells(entries)
    n_missing, missing = wrd.coverage_check(cells, entries)
    if n_missing:
        sys.exit(f'ABORT: Tier-1 planes incomplete ({n_missing} missing): '
                 f'{missing[:5]} ...')

    manifest = wt2.load_manifest()
    mpairs = manifest_amber_pairs(manifest) if manifest else None
    rows = shortlist_rows(entries, cells, mpairs)

    recomputed = {r['pair'] for r in rows}
    if mpairs is not None and mpairs != recomputed:
        extra = sorted(mpairs - recomputed)
        gone = sorted(recomputed - mpairs)
        print(f'WARNING: tier2-manifest amber set disagrees with Tier-1 '
              f'recompute: {len(extra)} manifest-only {extra[:4]}, '
              f'{len(gone)} recompute-only {gone[:4]}', file=sys.stderr)

    print(f'{len(rows)} amber pairs (of '
          f'{len(entries) * (len(entries) - 1) // 2} meta pairs), ranked by '
          f'combined recent usage:\n')
    print(format_table(rows, args.top))
    if args.md:
        cols = ('rank | pair | combined% | usage A+B | amber dirs | '
                'amber scenarios | spread flip | closest split | tier2')
        md = ['# Worlds amber-pair shortlist (combined recent usage)', '',
              '| ' + cols + ' |',
              '| ' + ' | '.join('---' for _ in cols.split('|')) + ' |']
        for i, r in enumerate(rows, 1):
            dirs = ('both' if all(r['amber_dirs'])
                    else 'A->B' if r['amber_dirs'][0] else 'B->A')
            split = (f"{r['closest_split']:.2f}"
                     if r['closest_split'] is not None else '--')
            md.append(
                f"| {i} | {r['names'][0]} / {r['names'][1]} "
                f"| {r['combined']:.1f} "
                f"| {r['usage'][0]:.1f}+{r['usage'][1]:.1f} | {dirs} "
                f"| {r['amber_scen'][0]}+{r['amber_scen'][1]} "
                f"| {'yes' if r['spread_flip'] else 'no'} | {split} "
                f"| {'ok' if r['in_tier2'] else 'MISSING'} |")
        args.md.write_text('\n'.join(md) + '\n')
        print(f'\nfull table -> {args.md}')


if __name__ == '__main__':
    main()
