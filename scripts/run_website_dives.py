#!/usr/bin/env python3
"""Run deep dives for the website, sequentially.

Dive configurations live in the DIVES list below. Each entry specifies
the species, league, output slug, and any non-default flags. The script
builds the full deep_dive.py command and runs dives one at a time.

Usage:
    python scripts/run_website_dives.py                  # all dives
    python scripts/run_website_dives.py tinkaton          # slug substring filter
    python scripts/run_website_dives.py --dry-run         # show commands only
"""

import argparse
import os
import subprocess
import sys
import time


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
WEBSITE_DIR = os.path.join(REPO_ROOT, 'userdata', 'website')
DEEP_DIVE = os.path.join(SCRIPT_DIR, 'deep_dive.py')

# ---- Dive configurations ----
# Each dict must have: species, league, slug, html_base
# Optional overrides (defaults shown):
#   opponents: 20            (top N from rankings)
#   opponents_file: None     (overrides opponents)
#   top_movesets: 5
#   opp_ivs: 'both'
#   bait: 'both'
#   reference: 'auto'
#   no_thresholds: False
#   shadow: False
#   extra_args: []           (escape hatch for unusual flags)

DIVES = [
    {
        'species': 'Tinkaton',
        'league': 'great',
        'slug': 'tinkaton-great-league',
        'html_base': 'tinkaton_gl_toml.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'reference': 'FAIRY_WIND,BULLDOZE,PLAY_ROUGH',
    },
    {
        'species': 'Tinkaton',
        'league': 'ultra',
        'slug': 'tinkaton-ultra-league-nofloor',
        'html_base': 'tinkaton_ul_nofloor.html',
        'opponents': 20,
        'no_thresholds': True,
    },
]


def build_command(dive):
    """Build the deep_dive.py command list from a dive config dict."""
    html_path = os.path.join(WEBSITE_DIR, dive['slug'], dive['html_base'])

    cmd = [sys.executable, DEEP_DIVE, dive['species'],
           '--league', dive['league']]

    if 'opponents_file' in dive:
        cmd += ['--opponents-file', dive['opponents_file']]
    elif 'opponents' in dive:
        cmd += ['--opponents', str(dive['opponents'])]

    cmd += ['--top-movesets', str(dive.get('top_movesets', 5))]
    cmd += ['--opp-ivs', dive.get('opp_ivs', 'both')]
    cmd += ['--bait', dive.get('bait', 'both')]
    cmd += ['--reference', dive.get('reference', 'auto')]

    if dive.get('no_thresholds'):
        cmd += ['--no-thresholds']
    if dive.get('shadow'):
        cmd += ['--shadow']

    cmd += [
        '--html', html_path,
        '--interactive',
        '--standalone',
        '--mirror-slayer',
        '--mirror-slayer-metric', 'all',
        '--mirror-slayer-rounds', '4',
        '--mirror-slayer-pool', '30',
        '--mirror-slayer-show', '20',
        '--split-movesets',
    ]

    if 'extra_args' in dive:
        cmd += dive['extra_args']

    return cmd


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filter', nargs='?', default=None,
                        help='Substring filter on slug (e.g. "tinkaton", "ultra")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print commands without running them')
    args = parser.parse_args()

    dives = DIVES
    if args.filter:
        dives = [d for d in dives
                 if args.filter.lower() in d['slug'].lower()]

    if not dives:
        print("No matching dives found.")
        return

    print(f"Found {len(dives)} dive(s) to run:\n")
    for d in dives:
        print(f"  - {d['slug']}")
    print()

    for i, dive in enumerate(dives):
        cmd = build_command(dive)
        cmd_str = ' '.join(cmd)
        print(f"{'='*60}")
        print(f"[{i+1}/{len(dives)}] {dive['slug']}")
        print(f"{'='*60}")
        print(f"  {cmd_str}\n")

        if args.dry_run:
            continue

        t0 = time.time()
        result = subprocess.run(cmd, cwd=REPO_ROOT)
        elapsed = time.time() - t0
        if result.returncode != 0:
            print(f"\n  [FAILED] {dive['slug']} (exit code {result.returncode})")
            print(f"  Stopping. Fix the issue and re-run.")
            sys.exit(1)
        print(f"\n  Done in {elapsed/60:.1f} min\n")

    if not args.dry_run:
        print(f"\nAll {len(dives)} dive(s) complete.")
        print("Run 'python scripts/build_website_index.py' to rebuild the index.")


if __name__ == '__main__':
    main()
