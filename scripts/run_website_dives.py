#!/usr/bin/env python3
"""Run deep dives for all website entries (or a filtered subset).

Reads meta.toml from each userdata/website/<slug>/ directory, extracts
the [dive] section, and runs scripts/deep_dive.py with those args.

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

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11


WEBSITE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'userdata', 'website',
)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEEP_DIVE = os.path.join(SCRIPT_DIR, 'deep_dive.py')


def find_dives(filter_str=None):
    """Yield (slug, meta_dict) for each dive with a [dive] section."""
    if not os.path.isdir(WEBSITE_DIR):
        print(f"Website directory not found: {WEBSITE_DIR}", file=sys.stderr)
        return
    for slug in sorted(os.listdir(WEBSITE_DIR)):
        meta_path = os.path.join(WEBSITE_DIR, slug, 'meta.toml')
        if not os.path.isfile(meta_path):
            continue
        if filter_str and filter_str.lower() not in slug.lower():
            continue
        with open(meta_path, 'rb') as f:
            meta = tomllib.load(f)
        if 'dive' not in meta:
            print(f"  [skip] {slug}: no [dive] section in meta.toml")
            continue
        yield slug, meta


def build_command(slug, meta):
    """Build the deep_dive.py command list from meta.toml [dive] section."""
    dive = meta['dive']
    species = dive['species']
    league = dive['league']
    html_base = dive.get('html_base', f'{slug}.html')
    html_path = os.path.join(WEBSITE_DIR, slug, html_base)

    cmd = [sys.executable, DEEP_DIVE, species, '--league', league]

    # Optional args with defaults matching our standard website config
    if 'opponents' in dive:
        cmd += ['--opponents', str(dive['opponents'])]
    if 'opponents_file' in dive:
        cmd += ['--opponents-file', dive['opponents_file']]
    cmd += ['--top-movesets', str(dive.get('top_movesets', 5))]
    cmd += ['--opp-ivs', dive.get('opp_ivs', 'both')]
    cmd += ['--bait', dive.get('bait', 'both')]

    if dive.get('reference'):
        cmd += ['--reference', dive['reference']]
    else:
        cmd += ['--reference', 'auto']

    if dive.get('no_thresholds'):
        cmd += ['--no-thresholds']

    if dive.get('shadow'):
        cmd += ['--shadow']

    # Standard flags for website output
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

    # Extra raw args (escape hatch for unusual flags)
    if 'extra_args' in dive:
        cmd += dive['extra_args']

    return cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filter', nargs='?', default=None,
                        help='Substring filter on slug (e.g. "tinkaton", "ultra")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print commands without running them')
    args = parser.parse_args()

    dives = list(find_dives(args.filter))
    if not dives:
        print("No matching dives found.")
        return

    print(f"Found {len(dives)} dive(s) to run:\n")
    for slug, _ in dives:
        print(f"  - {slug}")
    print()

    for i, (slug, meta) in enumerate(dives):
        cmd = build_command(slug, meta)
        cmd_str = ' '.join(cmd)
        print(f"{'='*60}")
        print(f"[{i+1}/{len(dives)}] {slug}")
        print(f"{'='*60}")
        print(f"  {cmd_str}\n")

        if args.dry_run:
            continue

        t0 = time.time()
        result = subprocess.run(cmd, cwd=os.path.dirname(SCRIPT_DIR))
        elapsed = time.time() - t0
        if result.returncode != 0:
            print(f"\n  [FAILED] {slug} (exit code {result.returncode})")
            print(f"  Stopping. Fix the issue and re-run.")
            sys.exit(1)
        print(f"\n  Done in {elapsed/60:.1f} min\n")

    if not args.dry_run:
        print(f"\nAll {len(dives)} dive(s) complete.")
        print("Run 'python scripts/build_website_index.py' to rebuild the index.")


if __name__ == '__main__':
    main()
