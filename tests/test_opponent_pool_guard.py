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
    # The loop above goes vacuous whenever every committed pool exactly matches
    # its recipe -- which is the NORMAL state right after a regeneration (as of
    # 2026-09-09 it is the state of all 8). It used to assert that some pool
    # carried extras, which made a freshly-regenerated repo fail a test about
    # classification logic. Pin the rule directly instead.


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


def test_curated_inclusions_are_shared_with_the_generator():
    """The inclusion table must live with the RECIPES, not with the checker.

    If the checker owned its own copy, a regeneration would drop the
    hand-extension and the checker would immediately fail it -- "remember to
    re-add X" every rebuild, which is exactly the manual step that let the
    pools go stale. One table, applied by build_opponent_pool and enforced
    here.
    """
    import build_opponent_pool as bop
    assert hasattr(bop, 'CURATED_INCLUSIONS')
    assert vp._required('gl_top50_plus_cs') is not None
    # every entry needs a real reason, same bar as the exclusions
    for pool, entries in bop.CURATED_INCLUSIONS.items():
        for species, reason in entries.items():
            assert isinstance(reason, str) and len(reason) > 25, (pool, species)


def test_a_missing_curated_inclusion_fails_the_guard():
    """A required species absent from a pool is the failing direction.

    Same treatment as a live meta entrant the pool lacks: it is an opponent
    every dive would be blind to.
    """
    import build_opponent_pool as bop
    rows = {r['pool']: r for r in vp.run()}
    for pool, entries in bop.CURATED_INCLUSIONS.items():
        r = rows.get(pool) or rows.get(pool.removesuffix('.txt'))
        if r is None or r['status'] == 'SKIP':
            continue
        committed = set(vp._read_pool(
            __import__('os').path.join(vp.POOL_DIR,
                                       pool if pool.endswith('.txt')
                                       else pool + '.txt')))
        for species in entries:
            if species not in committed:
                assert r['status'] == 'DRIFT', (
                    f'{pool} is missing required {species} but the guard '
                    f'reports {r["status"]}')
                assert species in (r.get('added') or []), (
                    f'{pool}: {species} missing but not named in the report')


def test_recipes_actually_apply_their_inclusions():
    """Regeneration must produce a pool the checker then accepts.

    Behavioural, not a source scan: runs the real recipe and asserts the
    required species comes out. A recipe that forgot the apply_inclusions call
    would leave the checker permanently red after every rebuild.
    """
    import build_opponent_pool as bop
    for pool in ('gl_top50_plus_cs', 'gl_top30_plus_cs_top100'):
        required = bop.CURATED_INCLUSIONS.get(pool) or {}
        if not required:
            continue
        result = bop.RECIPES[pool]()
        names = result[0] if isinstance(result, tuple) else result
        produced = {n.split('|', 1)[0].strip() for n in names}
        for species in required:
            assert species in produced, (
                f'recipe {pool} does not emit required {species}; it is '
                f'probably missing an apply_inclusions() call')


def test_extras_alone_never_fail_a_pool(tmp_path, monkeypatch):
    """A pool carrying recipe-absent extras is OK; only a MISSING species drifts.

    The behavioural positive control for the rule above, built rather than
    borrowed from repo state so it keeps working when every pool matches its
    recipe. Writes a pool that is the recipe output PLUS a species no recipe
    can produce, and asserts the status stays OK.
    """
    import build_opponent_pool as bop
    key = 'gl_top50_plus_cs'
    produced = bop.RECIPES[key]()
    names = produced[0] if isinstance(produced, tuple) else produced
    names = [n.split('|', 1)[0].strip() for n in names]
    pool = tmp_path / f'{key}.txt'
    pool.write_text('# synthetic\n' + '\n'.join(names) + '\nBulbasaur\n')
    monkeypatch.setattr(vp, 'POOL_DIR', str(tmp_path))
    row = {r['pool']: r for r in vp.run()}.get(key)
    assert row is not None, 'synthetic pool was not checked'
    assert 'Bulbasaur' in (row.get('removed') or []), (
        'the extra was not reported at all; the guard has stopped surfacing '
        'the informational direction')
    assert not row.get('added'), 'synthetic pool should lack nothing'
    assert row['status'] == 'OK', (
        f"extras alone flipped the status to {row['status']}; a pool with a "
        f"deliberate hand-extension would now fail the bake")


def test_every_pool_entry_resolves_to_a_ranked_species():
    """A pool name the DIVE cannot look up is an opponent silently dropped.

    Regression, 2026-09-09. PvPoke ranks some form-change species under the
    BASE speciesId while displaying the CHANGED form's name: `Mimikyu (Busted)`
    is the display name for sid `mimikyu`, `Morpeko (Hangry)` for
    `morpeko_full_belly`. A pool regeneration wrote those DISPLAY names, and
    `get_default_moveset` maps a name back through the gamemaster -- yielding
    `mimikyu_busted`, which is not a ranked id. Both were dropped from every GL
    dive with only a log warning, Mimikyu being ItsAxn's #1 meta-defining pick.

    The pool guard could not see this: it compares NAMES against the same
    rankings the recipe read, so a display name matched itself and looked
    perfectly healthy. Only asking "does the consumer resolve it?" catches it.

    Tournament pools are exempt: they record a past event's roster, and a
    species that has since left the rankings is a historical fact.
    """
    from gopvpsim.data import get_default_moveset
    unresolvable = []
    for path in sorted((REPO / 'opponent_pools').glob('*.txt')):
        if path.name.startswith(vp.TOURNAMENT_PREFIXES):
            continue
        league = ('ultra' if path.name.startswith('ul_')
                  else 'master' if 'master' in path.name else 'great')
        for raw in path.read_text().splitlines():
            entry = raw.split('#')[0].strip()
            if not entry:
                continue
            name = entry.split('|')[0].strip()
            shadow = '(Shadow)' in name
            base = name.replace('(Shadow)', '').strip()
            try:
                get_default_moveset(base, league, shadow=shadow)
            except Exception:
                unresolvable.append(f'{path.name}: {name}')
    assert not unresolvable, (
        'pool entries the dive cannot resolve (each is an opponent every dive '
        f'silently drops): {unresolvable}')


def test_the_resolvable_name_helper_actually_rewrites_display_names():
    """Positive control: the helper must CHANGE the two known display names.

    Without this, the test above would keep passing if resolvable_name were
    reduced to `return row['speciesName']` -- as long as nobody regenerated a
    pool. Pins the transform itself, not just today's committed files.
    """
    import build_opponent_pool as bop
    from gopvpsim.data import load_rankings
    rows = {r['speciesName']: r for r in load_rankings('great')}
    checked = 0
    for display, expected in (('Mimikyu (Busted)', 'Mimikyu'),
                              ('Morpeko (Hangry)', 'Morpeko (Full Belly)')):
        row = rows.get(display)
        if row is None:
            continue          # PvPoke renamed or unranked it; not this test's job
        checked += 1
        assert bop.resolvable_name(row) == expected, (
            f'{display!r} must map to {expected!r} (the name derived from its '
            f'rankings speciesId), got {bop.resolvable_name(row)!r}')
    assert checked, (
        'neither known display-name case is present in the GL rankings any '
        'more; find a current one or this control is dead')
