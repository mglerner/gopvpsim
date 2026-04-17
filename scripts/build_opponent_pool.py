#!/usr/bin/env python3
"""
Generate an opponent-pool text file for ``deep_dive.py --opponents-file``.

The committed pool files under ``opponent_pools/`` (e.g.
``gl_top50_plus_cs.txt``) are regeneratable via this script so they can
be refreshed when PvPoke's rankings or groups drift. Each pool file is
a newline-delimited list of PvPoke ``speciesName`` values; blank lines
and ``#`` comments are ignored by the deep_dive parser.

Usage::

    # Regenerate the default GL pool (top 50 rankings ∪ championshipseries).
    python scripts/build_opponent_pool.py gl_top50_plus_cs

    # Write to a custom path.
    python scripts/build_opponent_pool.py gl_top50_plus_cs \
        --out /tmp/pool.txt

List known recipes with ``--list``. The recipes are hardcoded here
rather than parameterized because "top 50 + championshipseries" is a
specific meta-analyst choice and the point of committing the resulting
file is to make the dives reproducible against a named pool.
"""
import argparse
import datetime
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'src'))

from gopvpsim.data import load_gamemaster, load_group, load_rankings  # noqa: E402


def _id_to_name_map():
    gm = load_gamemaster()
    return {m['speciesId']: m['speciesName'] for m in gm['pokemon']}


def _cs_names():
    """Return the championshipseries group as PvPoke speciesName values."""
    id_to_name = _id_to_name_map()
    names = []
    for entry in load_group('championshipseries'):
        if isinstance(entry, str):
            names.append(id_to_name.get(entry, entry))
        elif isinstance(entry, dict):
            sid = entry.get('speciesId') or entry.get('id')
            if sid:
                names.append(id_to_name.get(sid, sid))
    return names


def recipe_gl_top50_plus_cs():
    """Top 50 GL rankings union PvPoke championshipseries group.

    PvPoke's championshipseries adds bulky mons that don't clear the
    rankings' top 50 cut (Talonflame, Togekiss, Furret, Diggersby,
    Politoed, Togekiss, etc.) plus a few meta-niche picks. The union is
    the opponent pool we use for "real" GL deep dives where you want
    comprehensive coverage.
    """
    top50 = [r['speciesName'] for r in load_rankings('great')[:50]]
    cs = _cs_names()
    seen, union = set(), []
    for n in top50 + cs:
        if n not in seen:
            seen.add(n)
            union.append(n)
    return union, (f'Top 50 GL overall rankings (PvPoke) union the '
                   f'championshipseries group. {len(union)} unique species.')


def recipe_gl_top30_plus_cs_top100():
    """Top 30 GL rankings union championshipseries members ranked <= 100.

    Smaller opponent pool for faster deep dives. Drops the deepest CS
    entries (Politoed #101, Togekiss #106, Steelix #147, Piloswines
    #235/#256) while keeping every CS mon within realistic meta reach.
    Lands at ~42 species vs 61 for gl_top50_plus_cs. Deep dives scale
    worse than O(N^2), so trimming the pool is a large time win.
    Shadow/non-shadow pairs are deliberately both kept when both fall
    inside the cuts — the stat-multiplier shifts make them distinct
    prep targets, not near-duplicates.
    """
    rankings = load_rankings('great')
    rank = {r['speciesName']: i + 1 for i, r in enumerate(rankings)}
    top30 = [r['speciesName'] for r in rankings[:30]]
    cs_filt = [n for n in _cs_names() if rank.get(n, 10**9) <= 100]
    seen, union = set(), []
    for n in top30 + cs_filt:
        if n not in seen:
            seen.add(n)
            union.append(n)
    return union, (f'Top 30 GL overall rankings (PvPoke) union '
                   f'championshipseries members ranked <= 100. '
                   f'{len(union)} unique species.')


RECIPES = {
    'gl_top50_plus_cs': recipe_gl_top50_plus_cs,
    'gl_top30_plus_cs_top100': recipe_gl_top30_plus_cs_top100,
}


def write_pool(names, header, out_path):
    with open(out_path, 'w') as f:
        f.write(f'# {header}\n')
        f.write(f'# Generated {datetime.date.today()} by '
                f'scripts/build_opponent_pool.py\n')
        f.write('# Format: one PvPoke speciesName per line; '
                'blank lines and # comments ignored.\n\n')
        for n in names:
            f.write(n + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('recipe', nargs='?',
                   help='Recipe name (see --list).')
    p.add_argument('--out', metavar='PATH',
                   help='Override output path (default: opponent_pools/<recipe>.txt).')
    p.add_argument('--list', action='store_true', help='List available recipes.')
    args = p.parse_args()

    if args.list or not args.recipe:
        print('Available recipes:')
        for name, fn in RECIPES.items():
            doc = (fn.__doc__ or '').strip().splitlines()[0]
            print(f'  {name:25s} {doc}')
        return 0

    if args.recipe not in RECIPES:
        print(f'Unknown recipe: {args.recipe}', file=sys.stderr)
        print(f'Available: {", ".join(sorted(RECIPES))}', file=sys.stderr)
        return 2

    names, header = RECIPES[args.recipe]()
    out = args.out or os.path.join(REPO, 'opponent_pools', f'{args.recipe}.txt')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_pool(names, header, out)
    print(f'Wrote {len(names)} species to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
