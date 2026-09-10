#!/usr/bin/env python
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

sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))
from gopvpsim.data import (  # noqa: E402
    cup_dive_league, cup_slug_suffix,
)

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

# DIVES is now DERIVED FROM THE OPPONENT POOLS (2026-09-10). The 949-line
# hand-written literal that used to live here is in git history at cc5363c~1.
#
# It was replaced because the two lists had drifted badly: 31 of the 71 GL
# pool species had no page (everything the rebalance and the tier lists
# brought in), while 24 dive focals were absent from the pool. Nothing
# regenerated one from the other and nothing warned when they diverged.
#
# Equivalence was checked before the swap -- all 24 literal-only slugs were
# genuine drops and ZERO were artifacts of the generator's slug rule, so no
# live URL changes spelling. See
# docs/validations/2026-09-10_dive_registry_equivalence.md.
#
# Editorial content that cannot be derived (moveset pins, the Forretress
# two-fast-move split, non-default reference lines, Cramorant's policy,
# per-species top_movesets, which dives use hand-authored thresholds) lives
# in dive_registry.DIVE_OVERRIDES / EXTRA_DIVES / SLUG_EXCEPTIONS.
from dive_registry import all_dives as _all_dives

DIVES = _all_dives()


# When set by --reserve-cpus on the CLI, overrides every dive's per-entry
# reserve_cpus (e.g. 0 to use ALL cores for an unattended overnight run; the
# per-dive default of 1 exists for keeping a core free during interactive work).
_RESERVE_OVERRIDE = None


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
    if dive.get('policy', 'pvpoke') != 'pvpoke':
        cmd += ['--policy', dive['policy']]
    cmd += ['--reference', dive.get('reference', 'auto')]

    if dive.get('no_thresholds'):
        cmd += ['--no-thresholds']
    if dive.get('shadow'):
        cmd += ['--shadow']
    # Limited-cup dive: labeling + cup-rankings overlay on top of --league.
    # The cup pool bakes each opponent's cup moveset inline, so the active-
    # variants auto-merge must be skipped (it would re-append base-species
    # variants alongside the cup-moveset opponents).
    if dive.get('cup'):
        cmd += ['--cup', dive['cup'], '--no-active-variants']

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
        '--reserve-cpus', str(_RESERVE_OVERRIDE if _RESERVE_OVERRIDE is not None
                              else dive.get('reserve_cpus', 1)),
    ]

    # Best-buddy / L51 toggle. 'best_buddy' may be 'on'/'off'/'auto' (default
    # 'auto' = on for Great + Ultra; no-op species show the toggle but it does
    # nothing, with no extra sims). 'best_buddy_display' (50/51)
    # picks which level the page opens on. Per-species TOML can also set these;
    # the CLI flag here wins over the TOML.
    if 'best_buddy' in dive:
        cmd += ['--best-buddy', dive['best_buddy']]
    if 'best_buddy_display' in dive:
        cmd += ['--best-buddy-display', str(dive['best_buddy_display'])]

    if 'extra_args' in dive:
        cmd += dive['extra_args']

    return cmd


def check_cup_slugs(dives):
    """Preflight: every cup dive's slug must be `<species>-<cup>-cup`.

    THREE layers key on this one convention and none of them can see the
    others: this script PRODUCES the slug, build_website_index ROUTES on the
    `-<cup>-cup` suffix (a mismatch silently files the dive in the evergreen
    league lists instead of the cup index, or drops it entirely), and
    verify_overnight globs it. A typo would still render a perfectly good
    dive -- hours of sim -- and only show up as a missing cup-index entry, so
    fail loudly BEFORE the dives run.

    Also checks the cup is registered with a dive league (gopvpsim.data
    CUP_REGISTRY) matching the entry's league: an unregistered cup gets no
    slug suffix in the index, so its dives could never be routed.

    Raises ValueError listing every offending entry.
    """
    problems = []
    for d in dives:
        cup = d.get('cup')
        if not cup:
            continue
        slug = d['slug']
        suffix = '-' + cup_slug_suffix(cup)
        if not slug.endswith(suffix):
            problems.append(
                f"{slug!r}: cup {cup!r} dive slug must end with {suffix!r}")
        league = cup_dive_league(cup)
        if league is None:
            problems.append(
                f"{slug!r}: cup {cup!r} is not in gopvpsim.data.CUP_REGISTRY "
                f"with a dive_league; the website index cannot route it")
        elif league != d['league']:
            problems.append(
                f"{slug!r}: cup {cup!r} is registered as a {league!r} league "
                f"cup but this dive says {d['league']!r}")
    if problems:
        raise ValueError("Cup dive slug preflight failed:\n  "
                         + "\n  ".join(problems))


def check_opponent_pools(*, allow_stale=False):
    """Preflight: committed opponent pools must match live rankings.

    Pools are the INPUT to every dive here. Until 2026-09-02 nothing
    regenerated or checked them -- build_opponent_pool.py appeared in ZERO of
    overnight_redive.sh / run_website_dives.py / publish_website.sh /
    phase2_preship.sh -- so a season-start bake against stale pools was wrong
    everywhere at once, silently, with the chain exiting SUCCESS.

    It bites hardest at a REBALANCE: new rankings change pool MEMBERSHIP, not
    just order, and a new opponent is a new cache column, so it is not
    migrate-able either. Hours of sim, all against the wrong meta.

    Fails on live species MISSING from a pool (opponents every dive would be
    blind to). Deliberate hand-extensions and recorded curation calls do not
    fail -- see scripts/verify_opponent_pools.py.

    ``allow_stale`` (CLI ``--allow-stale-pools``) is the deliberate override
    for re-running a dive against a PINNED historical pool; it prints what it
    is ignoring rather than staying quiet.
    """
    import verify_opponent_pools as vp
    rows = vp.run()
    bad = [r for r in rows if r['status'] in ('DRIFT', 'MISSING', 'ERROR')]
    if not bad:
        return
    lines = []
    for r in bad:
        lines.append(f"{r['pool']}: {r['status']}")
        for sp in r.get('added') or []:
            lines.append(f"    live now, missing from pool: {sp}")
        if r.get('detail'):
            lines.append(f"    {r['detail']}")
    msg = ("Opponent-pool preflight failed:\n  " + "\n  ".join(lines)
           + "\n\nPools are the INPUT to every dive; baking against these "
             "produces wrong scores everywhere at once, and new opponents are "
             "new cache columns (not migrate-able).\n"
             "Regenerate:  python scripts/build_opponent_pool.py <recipe>\n"
             "Inspect:     python scripts/verify_opponent_pools.py\n"
             "Override:    --allow-stale-pools (only for a deliberate "
             "re-dive against a pinned historical pool)")
    if allow_stale:
        print("WARNING: --allow-stale-pools set; proceeding despite:\n" + msg)
        return
    raise ValueError(msg)


def main():
    check_cup_slugs(DIVES)

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filter', nargs='?', default=None,
                        help='Substring filter on slug (e.g. "tinkaton", "ultra")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print commands without running them')
    parser.add_argument('--allow-stale-pools', action='store_true',
                        help='Proceed even when opponent pools have drifted '
                             'from live rankings. Only for a deliberate '
                             're-dive against a pinned historical pool.')
    parser.add_argument('--reserve-cpus', type=int, default=None,
                        help='Override every dive\'s --reserve-cpus (e.g. 0 to '
                             'use all cores for an unattended run; default keeps '
                             'each dive\'s per-entry value, normally 1)')
    args = parser.parse_args()

    # After argparse so --help works without a network fetch, but BEFORE any
    # dive runs: the whole point is to fail in seconds rather than hours.
    check_opponent_pools(allow_stale=args.allow_stale_pools)

    global _RESERVE_OVERRIDE
    _RESERVE_OVERRIDE = args.reserve_cpus

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
    # Copy-paste monitor recipe (Michael's standing ask: every dive/chain
    # kick should hand over the watch command for a second terminal).
    print("\nMonitor in a second terminal:\n"
          "  watch -c -n 5 scripts/chain_status.py --chain overnight\n",
          flush=True)
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

        # Auto-generate the species-narrative block post-dive. The
        # patcher reads the dive's embedded SCORES_GZ + DATA and fills
        # empty intro.body / meta_role.good_at / meta_role.bad_at from
        # templates in scripts/auto_gen_narrative.py. Idempotent with
        # --force; fires for every species with dive data (CD species
        # get the CD-vs-baseline comparison, non-CD species like
        # Aegislash get the standalone stats rollup via B2 templates).
        # Runs per-dive so a failure doesn't block later dives.
        dive_dir = os.path.join(WEBSITE_DIR, dive['slug'])
        if os.path.isdir(dive_dir):
            patcher = os.path.join(SCRIPT_DIR, 'patch_dive_species_narrative.py')
            patch_cmd = ['python', patcher, dive_dir, '--force']
            print(f"  Patching narrative: {' '.join(patch_cmd)}")
            patch_result = subprocess.run(patch_cmd, cwd=REPO_ROOT)
            if patch_result.returncode != 0:
                print(f"  [WARN] narrative patch failed for {dive['slug']} "
                      f"(rc={patch_result.returncode}); continuing.")
        else:
            # Near-unreachable (a nonzero dive already sys.exit(1)s above),
            # but skipping the patch silently is the one path that emits no
            # line for verify_overnight to scan. Same WARN wording so the
            # existing scan catches it -- the literal substring
            # "WARN] narrative patch failed" is the contract with
            # verify_overnight.scan_narrative_warnings.
            print(f"  [WARN] narrative patch failed for {dive['slug']} "
                  f"(no dive dir at {dive_dir}); continuing.")

    if not args.dry_run:
        print(f"\nAll {len(dives)} dive(s) complete.")
        print("Run 'python scripts/build_website_index.py' to rebuild the index.")


if __name__ == '__main__':
    main()
