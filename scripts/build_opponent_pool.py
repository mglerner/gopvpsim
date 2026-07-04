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
import collections
import datetime
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'src'))

from gopvpsim.data import (load_gamemaster, load_group, load_rankings,  # noqa: E402
                           load_cup_rankings)

_CP_BY_LEAGUE = {'great': 1500, 'ultra': 2500, 'master': 10000}


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


# --- Championship-series tournament pools ---
#
# Dracoviz publishes per-team rosters (see scripts/fetch_dracoviz_tournament.py);
# we snapshot one JSON dump per tournament under docs/tournament_data/. These
# recipes consume a dump and emit an opponent pool ordered by in-practice
# usage frequency, filtered by `final_rank <= cutoff`. Useful for questions
# like "what should I actually prep against?" where PvPoke's curated
# championshipseries group is too broad or stale.

# Dracoviz encodes regional/form variants as "[<name> [<form> Form]]" or
# "[<name> [<form> Forme]]". Extract the inner form name.
_FORM_RE = re.compile(r'^\[[^[]+\[(.+?) (?:Form|Forme)\]\]$')

# Species where Dracoviz drops the form distinction but PvPoke treats
# forms as separate entries; default to the GL-competitive pick.
_FORM_DEFAULTS = {
    'Gourgeist':  'Super',     # Super is the GL meta size
    'Aegislash':  'Shield',    # GL registers in Shield form (Blade triggers mid-battle)
}


def _dracoviz_to_pvpoke_name(mon):
    """Convert a Dracoviz roster entry to a PvPoke speciesName string."""
    name = mon['name']
    form = mon.get('form', '')
    if form:
        m = _FORM_RE.match(form)
        base = f'{name} ({m.group(1)})' if m else name
    elif name in _FORM_DEFAULTS:
        base = f'{name} ({_FORM_DEFAULTS[name]})'
    else:
        base = name
    if mon.get('shadow', False):
        base = f'{base} (Shadow)'
    return base


def _load_tournament_rosters(dump_name):
    path = os.path.join(REPO, 'docs', 'tournament_data', f'{dump_name}.json')
    with open(path) as f:
        return json.load(f)


def _tournament_pool(dump_name, rank_cutoff, label):
    """Order species by in-tournament appearance count (desc), filtered to
    teams with ``final_rank <= rank_cutoff`` (``None`` = all teams).

    Entries whose normalized name isn't in PvPoke's gamemaster (off-meta
    picks the sim can't score) are skipped with a warning — those teams
    still contribute their other five members to the pool.
    """
    rosters = _load_tournament_rosters(dump_name)
    if rank_cutoff is not None:
        rosters = [r for r in rosters
                   if r.get('final_rank', 10**9) <= rank_cutoff]

    gm = load_gamemaster()
    known = {m['speciesName'] for m in gm['pokemon']}

    counts = collections.Counter()
    skipped = collections.Counter()
    for r in rosters:
        for mon in r['roster']:
            nm = _dracoviz_to_pvpoke_name(mon)
            if nm in known:
                counts[nm] += 1
            else:
                skipped[nm] += 1

    if skipped:
        print(f'[warn] {sum(skipped.values())} mon entries '
              f'({len(skipped)} unique names) not in PvPoke gamemaster, '
              f'skipped:', file=sys.stderr)
        for nm, n in skipped.most_common():
            print(f'  {n:3d}  {nm!r}', file=sys.stderr)

    names = [n for n, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    header = (f'{label}. {len(names)} unique species from {len(rosters)} '
              f'teams, ordered by appearance count (most-used first).')
    return names, header


def recipe_cs_2026_orlando_all():
    """Every species used on any 2026-Orlando team (all 156 rosters)."""
    return _tournament_pool('cs_2026_orlando', None,
                            'Championship Series Orlando 2026, all teams')


def recipe_cs_2026_orlando_top32():
    """Species used by any team finishing top-32 at 2026-Orlando."""
    return _tournament_pool('cs_2026_orlando', 32,
                            'Championship Series Orlando 2026, top-32 finishers')


def recipe_cs_2026_orlando_top8():
    """Species used by any team finishing top-8 at 2026-Orlando (corebreaker-hunting pool)."""
    return _tournament_pool('cs_2026_orlando', 8,
                            'Championship Series Orlando 2026, top-8 finishers')


# --- Limited-cup meta pools ---
#
# A cup dive is mechanically Great League (CP 1500), but its opponent pool is
# the cup meta, and each opponent uses the cup's recommended moveset (which can
# differ from the open-GL moveset). Membership comes from PvPoke's curated
# `groups/<cup>.json` meta (plan Decision 4: the ~20-species curated meta, not
# a rankings top-N slice); movesets are baked from the cup rankings (Decision
# 6) as inline `| fast= | charged=` overrides so deep_dive.py needs no cup
# awareness to sim the pool. active_variants is intentionally NOT merged for
# cup dives (the cup DIVE must pass --no-active-variants).


def recipe_cup_meta(cup, league, cup_pretty):
    """Curated cup meta as an opponent pool, movesets baked from cup rankings."""
    cp = _CP_BY_LEAGUE[league]
    id_to_name = _id_to_name_map()
    rankings = load_cup_rankings(cup, cp)
    rank = {r['speciesId']: i + 1 for i, r in enumerate(rankings)}
    mv = {r['speciesId']: r['moveset'] for r in rankings}
    rows = []
    for e in load_group(cup):
        if isinstance(e, dict):
            sid = e.get('speciesId') or e.get('id')
        else:
            sid = e
        name = id_to_name.get(sid, sid)
        if sid in mv:
            fast, charged = mv[sid][0], mv[sid][1:]
        elif isinstance(e, dict):  # unranked in cup rankings: use the group moveset
            fast, charged = e.get('fastMove'), e.get('chargedMoves', [])
        else:
            raise ValueError(f'{sid!r} in {cup} group has no moveset source')
        rows.append((rank.get(sid, 10**9),
                     f"{name} | fast={fast} | charged={','.join(charged)}"))
    lines = [line for _, line in sorted(rows, key=lambda x: (x[0], x[1]))]
    header = (
        f'{cup_pretty} ({league.capitalize()} League CP {cp}) curated meta '
        f'({len(lines)} species), ordered by cup rank; movesets baked from the '
        f'{cup} cup rankings. Lines carry inline "| fast= | charged=" overrides '
        f'(one opponent per line); active_variants intentionally NOT merged '
        f'(dive with --no-active-variants).')
    return lines, header


def recipe_equinox_great():
    """Devon Equinox Cup (GL 1500) curated 20-species meta, cup movesets."""
    return recipe_cup_meta('equinox', 'great', 'Equinox Cup')


RECIPES = {
    'gl_top50_plus_cs': recipe_gl_top50_plus_cs,
    'equinox_great': recipe_equinox_great,
    'gl_top30_plus_cs_top100': recipe_gl_top30_plus_cs_top100,
    'cs_2026_orlando_all': recipe_cs_2026_orlando_all,
    'cs_2026_orlando_top32': recipe_cs_2026_orlando_top32,
    'cs_2026_orlando_top8': recipe_cs_2026_orlando_top8,
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
