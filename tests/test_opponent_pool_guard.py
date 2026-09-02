"""Opponent pools must be checked before a bake, and the check must be wired in.

Pools are the INPUT to every dive. Until 2026-09-02 nothing regenerated or
checked them: `build_opponent_pool.py` appeared in ZERO of
`overnight_redive.sh`, `run_website_dives.py`, `publish_website.sh` and
`phase2_preship.sh`, so a season-start bake against stale pools was wrong
everywhere at once, silently, with the chain exiting SUCCESS.

These tests pin the guard's LOGIC and its WIRING separately. The wiring half
matters more: a correct checker nobody calls is exactly the failure mode this
replaced, and it is invisible to every test that only exercises the checker.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

import verify_opponent_pools as vp  # noqa: E402


def test_checker_runs_and_covers_every_committed_pool():
    """Every .txt in opponent_pools/ must be reachable by some check.

    A pool nobody checks is a pool that rots -- so the floor is coverage, not
    a pass/fail count.
    """
    rows = vp.run()
    assert rows, 'checker returned nothing'
    checked = {r['pool'].removesuffix('.txt') for r in rows}
    on_disk = {p.stem for p in (REPO / 'opponent_pools').glob('*.txt')}
    uncovered = on_disk - checked
    assert not uncovered, (
        f'opponent pools with no check: {sorted(uncovered)}. Add a recipe, a '
        f'RANKINGS_DERIVED entry, or a TOURNAMENT_PREFIXES skip.')


def test_tournament_pools_are_skipped_not_checked():
    """They record a past event's rosters -- a historical fact that cannot drift.

    Checking them against live rankings would produce permanent false drift,
    and a guard that always fails is a guard nobody reads.
    """
    rows = {r['pool']: r for r in vp.run()}
    tourney = [k for k in rows if k.startswith(vp.TOURNAMENT_PREFIXES)]
    assert tourney, 'no tournament pools found; has the naming changed?'
    for k in tourney:
        assert rows[k]['status'] == 'SKIP', (k, rows[k]['status'])


def test_missing_from_pool_is_the_failing_direction():
    """Only live-species-absent fails; pool extras are informational.

    Both directions are reported, but they mean different things: a species
    the pool lacks is an opponent every dive is blind to, while a species the
    recipe no longer produces is often a deliberate hand-extension (dive
    focals that never cleared the auto cut -- see the pool headers). Failing
    on the second would make the guard unusable.
    """
    rows = vp.run()
    recipe_rows = [r for r in rows if r['status'] in ('OK', 'DRIFT')]
    assert recipe_rows, 'no comparable pools'
    for r in recipe_rows:
        expect = 'DRIFT' if r.get('added') else 'OK'
        assert r['status'] == expect, (
            f"{r['pool']}: status {r['status']} but added={r.get('added')}; "
            f"only the 'missing from pool' direction may fail")
    # positive control: at least one pool carries extras, so the rule above
    # is actually exercised rather than vacuously true
    assert any(r.get('removed') for r in recipe_rows), (
        'no pool has recipe-absent extras; this test is not discriminating')


def test_curated_exclusions_carry_a_reason_and_do_not_fail():
    """An open curation call must be visible but must not block a bake.

    Without this the guard reports a decision someone deliberately made as
    rot, gets ignored, and stops working. Every entry needs a real reason
    string -- "we have not looked at it" is drift, not an exclusion.
    """
    assert vp.CURATED_EXCLUSIONS, 'no exclusions recorded'
    for pool, entries in vp.CURATED_EXCLUSIONS.items():
        for species, reason in entries.items():
            assert isinstance(reason, str) and len(reason) > 30, (
                f'{pool}/{species}: reason too thin to justify an exclusion')
    rows = {r['pool']: r for r in vp.run()}
    # an excluded species must never appear in the failing set
    for pool, entries in vp.CURATED_EXCLUSIONS.items():
        r = rows.get(pool) or rows.get(pool + '.txt')
        if r is None:
            continue
        for species in entries:
            assert species not in (r.get('added') or []), (
                f'{species} is curated out of {pool} but still reported as '
                f'missing')


def test_the_guard_is_actually_wired_into_the_dive_runner():
    """A checker nobody calls is the exact failure mode this replaced.

    Source-scan rather than behaviour: importing run_website_dives is
    expensive and calling main() would try to run dives. Tolerant regex plus
    a positive control, per the testing policy.
    """
    src = (REPO / 'scripts' / 'run_website_dives.py').read_text()
    assert 'def check_opponent_pools' in src, 'guard function is gone'
    assert 'check_opponent_pools(' in src.split('def check_opponent_pools', 1)[1], \
        'guard is defined but never called'
    assert '--allow-stale-pools' in src, 'deliberate override is gone'
    # positive control: the sibling preflight is still wired the same way, so
    # a refactor that guts BOTH is visible rather than silently passing
    assert 'check_cup_slugs(DIVES)' in src


def test_the_guard_runs_before_any_dive_starts():
    """Fail in seconds, not after hours of sim.

    Pins ORDER: the pool check must precede the dive loop. Getting this wrong
    turns a fast preflight into a very expensive one.
    """
    src = (REPO / 'scripts' / 'run_website_dives.py').read_text()
    body = src.split('def main(', 1)[1]
    call = body.index('check_opponent_pools(')
    # the reserve-cpus assignment is the first thing the dive machinery needs
    reserve = body.index('_RESERVE_OVERRIDE = args.reserve_cpus')
    assert call < reserve, (
        'check_opponent_pools runs after dive setup has begun; it must be the '
        'first thing after argparse')
