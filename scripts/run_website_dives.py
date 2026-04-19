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
    # Order is deliberate: Oinkologne pair first so the CD article can
    # regenerate earliest if the later dives slip. Tinkaton next (GL then
    # UL). Aegislash pair last, GL before UL per the D2 decision on
    # 2026-04-18. `--reserve-cpus 1` on every entry per the
    # `feedback_reserve_cpu_for_dives` discipline so local work stays
    # responsive if someone else lands on the box mid-run.
    {
        'species': 'Oinkologne',
        'league': 'great',
        'slug': 'oinkologne-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'reference': 'TACKLE,BODY_SLAM,TRAILBLAZE',
    },
    {
        'species': 'Oinkologne (Female)',
        'league': 'great',
        'slug': 'oinkologne-female-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'reference': 'TACKLE,BODY_SLAM,TRAILBLAZE',
    },
    {
        'species': 'Tinkaton',
        'league': 'great',
        'slug': 'tinkaton-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'reference': 'FAIRY_WIND,BULLDOZE,PLAY_ROUGH',
    },
    {
        'species': 'Tinkaton',
        'league': 'ultra',
        'slug': 'tinkaton-ultra-league',
        'html_base': 'index.html',
        'opponents': 60,
        'no_thresholds': True,
    },
    # Aegislash (Blade) isn't in PvPoke rankings; pass --fast / --charged
    # explicitly via extra_args and --no-thresholds so the auto-loader
    # doesn't search for aegislash_blade.toml in the ranking-keyed paths.
    # Canonical Shield moveset from get_default_moveset is mirrored on
    # Blade so the hypothetical always-Blade comparison is apples-to-
    # apples.
    #
    # Aegislash GL dives are intentionally ABSENT from the overnight
    # chain (decision 2026-04-19): they run out-of-band against the
    # cs_2026_orlando_top32.txt pool (24+ actual meta species from the
    # 2026 Orlando CS finals) for a faster / CS-relevant snapshot.
    # Only the UL pair stays in the overnight DIVES list. If you need
    # to re-dive Aegislash GL, run deep_dive.py directly against that
    # pool (see the commit trailing this block for the canonical
    # command).
    {
        'species': 'Aegislash (Blade)',
        'league': 'ultra',
        'slug': 'aegislash-blade-ultra-league',
        'html_base': 'index.html',
        'opponents': 60,
        'no_thresholds': True,
        'extra_args': ['--fast', 'PSYCHO_CUT',
                       '--charged', 'SHADOW_BALL,FLASH_CANNON'],
        'reference': 'PSYCHO_CUT,SHADOW_BALL,FLASH_CANNON',
    },
    {
        'species': 'Aegislash (Shield)',
        'league': 'ultra',
        'slug': 'aegislash-shield-ultra-league',
        'html_base': 'index.html',
        'opponents': 60,
        'no_thresholds': True,
        'reference': 'AEGISLASH_CHARGE_PSYCHO_CUT,SHADOW_BALL,FLASH_CANNON',
    },
    # Forretress 4-way: normal vs shadow × Bug Bite vs Volt Switch, same
    # charged moves (Sand Tomb + Rock Tomb — PvPoke default, also the CS
    # meta standard for both fast-move variants). Against the Orlando
    # 2026 top-32 pool. Goal is a fast-move + shadow comparison article
    # built post-dive via compare_loadouts.py. top_movesets=1 because
    # fast+charged are both pinned; only one moveset matches.
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-volt-switch-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/cs_2026_orlando_top32.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'extra_args': ['--fast', 'VOLT_SWITCH',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB',
    },
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-bug-bite-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/cs_2026_orlando_top32.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'extra_args': ['--fast', 'BUG_BITE',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'BUG_BITE,SAND_TOMB,ROCK_TOMB',
    },
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-shadow-volt-switch-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/cs_2026_orlando_top32.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'shadow': True,
        'extra_args': ['--fast', 'VOLT_SWITCH',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB',
    },
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-shadow-bug-bite-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/cs_2026_orlando_top32.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'shadow': True,
        'extra_args': ['--fast', 'BUG_BITE',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'BUG_BITE,SAND_TOMB,ROCK_TOMB',
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
        '--reserve-cpus', str(dive.get('reserve_cpus', 1)),
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
