#!/usr/bin/env python
"""Remove website dive directories whose dive is no longer in the registry.

WHY. The dive list derives from the opponent pools (scripts/dive_registry.py),
so a pool regeneration can DROP a dive: on 2026-09-17 the top-60 cut moved
and Galarian Moltres, Shadow Dragonair and Shadow Kingdra left the list.
Nothing removed their pages: run_website_dives.py only writes the dives it is
given, build_website_index.py lists whatever directories exist, and
publish_website.sh mirrors the local tree with ``rsync --delete`` -- which
deletes only what is absent LOCALLY. So a dropped dive stayed published and
indexed, baked under older assumptions than every neighbour, with nothing on
the page saying so. Michael's expectation (2026-09-17) was the opposite:
"drop them as dives" should remove them from the site.

WHAT. Dry-run by default: print every ``*-league`` directory under
userdata/website that is not a registry slug, and exit 1 when there is at
least one (publish_website.sh uses that as a gate). ``--apply`` deletes
them. Only dive-shaped directories (``<slug>-<league>-league``) are ever
considered; articles/, comparisons/, guides/, matchups/ and every other
non-dive path are untouched by construction.

The replay blobs under userdata/replay are NOT touched, and the sweep cache
keeps the dive's columns, so a dropped dive can be resurrected warm: add it
back (curated inclusion, or it re-enters the rank cut) and re-bake or
re-render.

Usage::

    python scripts/prune_unlisted_dives.py           # list, exit 1 if any
    python scripts/prune_unlisted_dives.py --apply   # delete them
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

DEFAULT_SITE = os.path.join(REPO_ROOT, 'userdata', 'website')
LEAGUE_SUFFIXES = ('-great-league', '-ultra-league', '-master-league')


def is_dive_dir(name):
    """A dive page directory is ``<slug>`` ending in one of the league suffixes."""
    return name.endswith(LEAGUE_SUFFIXES)


def unlisted_dive_dirs(site_dir, slugs):
    """Dive-shaped directories under ``site_dir`` whose name is not a registry slug."""
    if not os.path.isdir(site_dir):
        return []
    listed = set(slugs)
    out = []
    for name in sorted(os.listdir(site_dir)):
        path = os.path.join(site_dir, name)
        if os.path.isdir(path) and is_dive_dir(name) and name not in listed:
            out.append(name)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--site', default=DEFAULT_SITE,
                    help='website tree to scan (default: userdata/website)')
    ap.add_argument('--apply', action='store_true',
                    help='delete the unlisted dive directories (default: list only)')
    args = ap.parse_args(argv)

    from dive_registry import all_dives
    slugs = [d['slug'] for d in all_dives()]
    gone = unlisted_dive_dirs(args.site, slugs)
    if not gone:
        print(f'no unlisted dive directories under {args.site}')
        return 0
    verb = 'removing' if args.apply else 'unlisted (would remove with --apply)'
    print(f'{len(gone)} dive directories not in the registry -- {verb}:')
    for name in gone:
        print(f'  {name}')
        if args.apply:
            shutil.rmtree(os.path.join(args.site, name))
    if args.apply:
        print('done; replay blobs and cache columns are untouched')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
