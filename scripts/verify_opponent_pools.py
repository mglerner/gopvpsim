#!/usr/bin/env python
"""Hard-fail when a committed opponent pool has drifted from live rankings.

WHY THIS EXISTS
---------------
Opponent pools are the INPUT to every dive: `deep_dive.py --opponents-file`
reads them, and every score, threshold, spread and published page is computed
against whatever species they name. Nothing regenerated them and nothing
checked them -- `build_opponent_pool.py` appears in ZERO of
`overnight_redive.sh`, `run_website_dives.py`, `publish_website.sh` and
`phase2_preship.sh` (verified 2026-09-02). So a season-start bake against
stale pools is wrong everywhere at once, silently, with the chain exiting
SUCCESS.

This bites hardest at a REBALANCE, because new rankings change pool
MEMBERSHIP, not just order -- and a new opponent is a new cache column, so it
is not migrate-able either. The June 2026 rebalance pulled Umbreon, Milotic,
Dondozo and Primeape into the GL pool; nothing would have told us.

Per the lens-grid rule (CLAUDE.md): a cheap lens becomes a code-level guard
that cannot silently regress. This is the "input-freshness" cell.

WHAT IT CHECKS
--------------
* RECIPE-BACKED pools (`build_opponent_pool.RECIPES`): re-run the recipe
  against live data and diff MEMBERSHIP against the committed file. Any
  add/remove fails.
* RANKINGS-DERIVED pools with no recipe (`ul_top60`, `master_top60`): compare
  against the live top-N for that league. These were hand-built, so the check
  is a staleness signal rather than a regeneration.
* TOURNAMENT pools (`cs_*`): SKIPPED by design. They record which species were
  actually used at a past event -- a historical fact that cannot drift.

Ordering is deliberately NOT checked: dives iterate the whole pool, so order
is presentation. Membership is what changes the work.

Usage:
    python scripts/verify_opponent_pools.py            # check all, exit 1 on drift
    python scripts/verify_opponent_pools.py --quiet    # only report problems
    python scripts/verify_opponent_pools.py --json     # machine-readable
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'src'))
sys.path.insert(0, os.path.join(REPO, 'scripts'))

POOL_DIR = os.path.join(REPO, 'opponent_pools')

# Pools built from a past tournament's rosters. Historical facts; they do not
# track live rankings and must never be "refreshed".
TOURNAMENT_PREFIXES = ('cs_',)

# Hand-built pools with no recipe, checked against a live rankings top-N.
# (league, N). N is the size the file's own header claims it was built at.
RANKINGS_DERIVED = {
    'ul_top60.txt': ('ultra', 60),
    'master_top60.txt': ('master', 60),
}

# Species deliberately kept OUT of a pool, with the reason. Without this the
# guard reports an open curation decision as rot, and a guard that cries wolf
# is a guard nobody reads. An entry here is reported (so the decision stays
# visible) but does not fail.
#
# Add one ONLY for a decision someone actually made. "We have not looked at it
# yet" is drift, not an exclusion.
CURATED_EXCLUSIONS = {
    'gl_top50_plus_cs': {
        'Cramorant': ('open curation call (TODO.md, Cramorant accepted test '
                      'debt (b)): whether Cramorant enters the pool as an '
                      'OPPONENT for other species dives is Michael\'s to '
                      'decide; until then no shipped dive sims against it'),
    },
    'ul_top60.txt': {
        'Cramorant': ('same open curation call as the GL pool'),
    },
}


def _read_pool(path):
    """Species names from a pool file, in file order.

    Mirrors deep_dive's reader: skip blanks and `#` comments, and take the
    part before any `|` override (`'Forretress | fast=BUG_BITE'`).
    """
    names = []
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            names.append(line.split('|', 1)[0].strip())
    return names


def _live_top_n(league, n):
    from gopvpsim.data import load_rankings
    return [r['speciesName'] for r in load_rankings(league)[:n]]


def check_recipe_pool(name, recipe):
    """Recompute a recipe pool and diff membership against the committed file."""
    path = os.path.join(POOL_DIR, f'{name}.txt')
    if not os.path.exists(path):
        return {'pool': name, 'status': 'MISSING', 'detail': path}
    committed = set(_read_pool(path))
    result = recipe()
    # recipes return either a name list or (names, header)
    live_names = result[0] if isinstance(result, tuple) else result
    live = {n.split('|', 1)[0].strip() for n in live_names}

    excluded = CURATED_EXCLUSIONS.get(name, {})
    # THE failure direction: a live species the pool does not contain. Those
    # are meta entrants every dive would be blind to.
    missing = sorted(live - committed - set(excluded))
    # The other direction is informational: pool entries the recipe no longer
    # produces. Some are deliberate hand-extensions (dive focals that never
    # cleared the auto recipe -- see the pool headers), so this must NOT fail;
    # it only tells you what a regeneration would drop.
    extra = sorted(committed - live)
    return {
        'pool': name, 'status': 'DRIFT' if missing else 'OK',
        'committed': len(committed), 'live': len(live),
        'added': missing, 'removed': extra,
        'curated_out': sorted(set(excluded) & live),
        'reasons': excluded,
    }


def check_rankings_pool(fname, league, n):
    """Compare a hand-built pool against the live top-N of its league.

    Reported as membership drift rather than "wrong": these pools are curated
    (unions, hand-extensions), so extra entries are expected. What matters is
    live top-N species MISSING from the pool -- those are meta entrants a dive
    would never sim against.
    """
    path = os.path.join(POOL_DIR, fname)
    if not os.path.exists(path):
        return {'pool': fname, 'status': 'MISSING', 'detail': path}
    committed = set(_read_pool(path))
    live = set(_live_top_n(league, n))
    excluded = CURATED_EXCLUSIONS.get(fname, {})
    missing = sorted(live - committed - set(excluded))
    return {
        'pool': fname, 'status': 'DRIFT' if missing else 'OK',
        'committed': len(committed), 'live': len(live),
        'added': missing,          # live top-N absent from the pool
        'removed': [],             # curated extras are not drift
        'curated_out': sorted(set(excluded) & live),
        'reasons': excluded,
    }


def run():
    from build_opponent_pool import RECIPES
    rows = []
    for name, recipe in sorted(RECIPES.items()):
        if name.startswith(TOURNAMENT_PREFIXES):
            rows.append({'pool': name, 'status': 'SKIP',
                         'detail': 'tournament roster; historical, cannot drift'})
            continue
        try:
            rows.append(check_recipe_pool(name, recipe))
        except Exception as e:               # a recipe that cannot run is drift
            rows.append({'pool': name, 'status': 'ERROR',
                         'detail': f'{type(e).__name__}: {e}'})
    for fname, (league, n) in sorted(RANKINGS_DERIVED.items()):
        try:
            rows.append(check_rankings_pool(fname, league, n))
        except Exception as e:
            rows.append({'pool': fname, 'status': 'ERROR',
                         'detail': f'{type(e).__name__}: {e}'})
    return rows


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--quiet', action='store_true',
                    help='only print pools with a problem')
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    args = ap.parse_args()

    rows = run()
    if args.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            if args.quiet and r['status'] in ('OK', 'SKIP'):
                continue
            head = f"  {r['status']:8s} {r['pool']}"
            if r['status'] in ('OK', 'DRIFT'):
                head += f"  ({r['committed']} committed, {r['live']} live)"
            print(head)
            if r.get('detail'):
                print(f"           {r['detail']}")
            for s_ in r.get('added') or []:
                print(f"           MISSING from pool (live now): {s_}")
            for s_ in r.get('curated_out') or []:
                print(f"           curated out: {s_}")
                print(f"             reason: {r['reasons'][s_]}")
            extras = r.get('removed') or []
            if extras and not args.quiet:
                print(f"           (informational) {len(extras)} pool entries "
                      f"the recipe no longer produces -- some are deliberate "
                      f"hand-extensions; a regeneration would drop them:")
                print(f"             {', '.join(extras)}")

    bad = [r for r in rows if r['status'] in ('DRIFT', 'MISSING', 'ERROR')]
    if bad:
        print(f"\nOPPONENT POOLS STALE: {len(bad)} of {len(rows)} need attention.")
        print("Pools are the INPUT to every dive -- a bake against these is "
              "wrong everywhere at once, and new opponents are new cache "
              "columns (not migrate-able).")
        print("Regenerate a recipe pool with:")
        for r in bad:
            if r['status'] == 'DRIFT' and not r['pool'].endswith('.txt'):
                print(f"    python scripts/build_opponent_pool.py {r['pool']}")
        print("Hand-built pools (ul_top60, master_top60) need a curation pass.")
        return 1
    print(f"\nAll {len(rows)} opponent pools match live rankings.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
