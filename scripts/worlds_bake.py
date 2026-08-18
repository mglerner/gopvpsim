#!/usr/bin/env python
"""Worlds 2026 Tier-1 bake driver: idempotent, manifest-driven, guarded.

Plan: docs/worlds_prep_plan.md. Bakes the (pair, direction, bait-mode)
outcome planes into ``worlds/planes/`` -- 2 focal probe spreads (rank-1
SP + max-atk-within-top-512) x opponent cohort (top-512 SP union
best-SP-per-atk-IV) x 9 shield scenarios, legacy engine, signature
dedup -- and only for keys missing from the manifest, so a late meta
add re-bakes exactly the new pairs.

Sequencing note (TODO.md "Worlds 2026"): the pending behavior-neutral
engine-hash batch must land BEFORE the first real bake, or wait until
after Worlds -- the manifest records the engine hash at first bake and
every later bake must match or be refused (--rebake-all is the only
deletion path). There is deliberately NO "did that batch land?" check
here: the driver cannot distinguish that commit from any other, so the
enforced invariant is single-vintage planes + a clean engine tree.

Guardrails as code (the {layer} x {lens} rule; tests:
tests/test_worlds_bake_guards.py):

* the sweep cache is POISONED before any sim -- any code path that
  reaches SweepCache.get_column/put_column raises instead of
  overwriting trusted GL columns in place. NB macOS pools spawn fresh
  children that do NOT inherit the poison; that is fine because
  put_column only ever runs in the parent (deep_dive_lib/sweep.py), and
  the worker (deep_dive_lib.robustness.plane_task_worker) has no cache
  code at all -- do not "fix" the poison into the workers;
* engine cleanliness: git-porcelain over the engine-hash file set must
  be clean, and a NON-memoized engine digest is compared before/after
  the bake (sweep_cache.engine_hash() memoizes per process, so calling
  it twice can never detect a mid-bake edit);
* every meta moveset id is validated against the species' legal
  gamemaster pool first -- make_battle_pokemon has no legality guard,
  and an Aegislash form-move mixup builds a plausible-looking inverted
  monster instead of crashing (2026-08-10 audit). The ONE documented
  hole is the per-entry ``injected_move_ids`` CD carve-out (see
  preflight_moveset_legality): declared in meta.toml, proven against
  upstream eliteMoves + the pvpoke commit log, and disclosed on the
  rendered pages;
* a producer-code edit refuses to extend an existing manifest, with
  ``--bless-worlds-code`` as the audited, one-shot, operator-opt-in
  alternative to a cold re-bake (see WORLDS_CODE_LINEAGE);
* stamp mismatches REFUSE (worlds_planes.stamp_mismatches); charged-move
  order follows the shipped dive (get_default_moveset order) whenever
  the chosen set equals the default set, because meta.toml's sorted ids
  are an alphabetization artifact and slot order is PvPoke-visible for
  equal-energy moves.
"""
import argparse
import hashlib
import itertools
import multiprocessing
import subprocess
import sys
import time
import tomllib
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))

from gopvpsim.data import get_default_moveset, load_gamemaster
from gopvpsim.pokemon import iv_rank, find_pokemon_entry

import worlds_planes as wp
from deep_dive_lib.robustness import plane_task_worker

SCENARIOS = [(sf, so) for sf in range(3) for so in range(3)]
TOP_K = 512

# The cleanliness file set: the sweep-cache engine hash inputs (src files
# + deep_dive_signature.py -- see sweep_cache._ENGINE_FILES) PLUS the
# worlds_code_hash sources -- a dirty producer file would stamp its WIP
# hash into a fresh manifest and silently bake unreviewed code.
ENGINE_TREE = ('src/gopvpsim', 'scripts/deep_dive_signature.py',
               *(str(p.relative_to(wp.REPO))
                 for p in wp._WORLDS_SOURCE_FILES))
_ENGINE_SRC_FILES = ('battle.py', '_dp_jit.py', 'moves.py', 'formchange.py',
                     'pokemon.py')

# --- One-shot blessed worlds_code predecessors ------------------------------
#
# A producer-code edit normally REFUSES to extend an existing manifest
# (worlds_planes module docstring), and the only escape is --rebake-all.
# CLAUDE.md's migration doctrine ("before a cold re-dive, check for a
# tractable migration first") applies here exactly as it does to the sweep
# cache: when the ENTIRE producer delta since a given worlds_code hash
# provably cannot change any already-baked plane, the old stamp may be
# blessed forward instead of cold re-baking.
#
# Same two soundness guards as migrate_cache's predicates, plus a third:
#
#  1. the reason must cover the FULL delta since that hash, not just the
#     fix that motivated it -- so bless only alongside ONE localized change;
#  2. entries are one-shot: pinned to a single predecessor hash, consumed by
#     the bake that re-stamps the manifest, never re-applied afterwards;
#  3. blessing NEVER happens implicitly -- it requires the operator to pass
#     --bless-worlds-code <predecessor hash> on the command line, and the
#     manifest permanently records the blessing in `worlds_code_lineage`.
#
# `git diff <the commit that produced the predecessor hash>..HEAD --
#  scripts/worlds_planes.py scripts/worlds_bake.py
#  scripts/deep_dive_lib/robustness.py scripts/deep_dive_lib/sweep.py`
# is the mechanical check that a reason below is complete.
WORLDS_CODE_LINEAGE = {
    '653d776f9028': (
        '2026-08-18, Thievul Icy Wind. FULL producer delta since '
        '653d776f9028 (git diff 157bf71..HEAD over the four '
        '_WORLDS_SOURCE_FILES): worlds_bake.py only -- (a) the '
        'injected_move_ids carve-out in preflight_moveset_legality plus its '
        'load_gamemaster import and all_move_ids helper, (b) this lineage '
        'block and its --bless-worlds-code plumbing. worlds_planes.py, '
        'deep_dive_lib/robustness.py and deep_dive_lib/sweep.py are '
        'byte-unchanged. Neither (a) nor (b) executes inside a sim: (a) is a '
        'pre-bake legality CHECK whose only behavior change is to widen the '
        'accepted pool for entries carrying a non-empty injected_move_ids '
        'list -- no pre-Thievul meta entry has that field, so the check '
        'still accepts and rejects exactly what it did before for all 31 of '
        'them; (b) only affects stamp comparison. Every one of the 1,860 '
        'planes baked under 653d776f9028 is therefore bit-identical under '
        'the new hash.'),
    'e8a362c4dcc7': (
        '2026-08-18, Thievul moveset fork (Michael: Thievul enters as TWO '
        'builds, NS+IW and IW+PR). FULL producer delta since e8a362c4dcc7 '
        '(git diff 2c8816d..HEAD over the four _WORLDS_SOURCE_FILES): '
        'worlds_bake.py only -- (a) preflight_moveset_legality now resolves '
        'the gamemaster entry via e.get("gamemaster_name") or e["name"], '
        'because a fork arm\'s display name is not a speciesName, (b) this '
        'lineage entry. worlds_planes.py, deep_dive_lib/robustness.py and '
        'deep_dive_lib/sweep.py are byte-unchanged. (a) is again a pre-bake '
        'CHECK that reads no plane input, and it resolves IDENTICALLY for '
        'all 32 already-baked entries: 31 of them have no gamemaster_name '
        'field at all (so the expression is literally e["name"]), and the '
        'thievul entry\'s new gamemaster_name is "Thievul" -- exactly the '
        'name it was looked up under when its 124 planes were baked. Every '
        'one of the 1,984 planes baked under e8a362c4dcc7 is therefore '
        'bit-identical under the new hash. NB the display-name and '
        'usage-lookup changes live in worlds_meta.py, which is NOT a '
        'producer source and cannot affect a plane; the sim-relevant meta '
        'fields (species_id, species, shadow, fast_move_id, '
        'charged_move_ids) of all 32 existing entries are unchanged, which '
        'worlds_planes.meta_delta re-checks independently at bake time.'),
}


def fresh_engine_digest():
    """Re-reads the engine sources on EVERY call (sweep_cache.engine_hash
    is memoized per process and would report the start value forever)."""
    h = hashlib.md5()
    for name in _ENGINE_SRC_FILES:
        h.update((REPO / 'src' / 'gopvpsim' / name).read_bytes())
    sig = REPO / 'scripts' / 'deep_dive_signature.py'
    if sig.exists():
        h.update(sig.read_bytes())
    return h.hexdigest()


def install_sweep_cache_poison():
    """Make any sweep-cache read/write raise. put_column's internal
    try/except is its BODY -- replacing the method means the raise
    propagates to the caller (verified in the guards audit)."""
    import sweep_cache as swc

    def _forbidden(*_a, **_k):
        raise RuntimeError(
            'Worlds bake must never touch the sweep disk cache '
            '(put_column overwrites trusted GL columns in place)')

    swc.SweepCache.put_column = _forbidden
    swc.SweepCache.get_column = _forbidden


def preflight_engine_clean(allow_dirty=False):
    out = subprocess.run(
        ['git', 'status', '--porcelain', '--', *ENGINE_TREE],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    dirty = [ln for ln in out.splitlines() if ln.strip()]
    print(f'Engine-cleanliness preflight: {len(dirty)} dirty path(s) '
          f'under the engine set.')
    if dirty and not allow_dirty:
        sys.exit('ABORT: engine tree is dirty -- a WIP engine edit must not '
                 'be baked into Worlds planes (and an engine-hash bump '
                 'stales the GL sweep cache; see TODO.md sequencing). '
                 'Commit/stash first, or pass --allow-dirty-engine.\n'
                 + '\n'.join(dirty))


def legal_move_ids(entry_name):
    mon = find_pokemon_entry(entry_name)
    if mon is None:
        return None, None
    fast = set(mon.get('fastMoves') or []) | set(mon.get('eliteMoves') or [])
    charged = (set(mon.get('chargedMoves') or [])
               | set(mon.get('eliteMoves') or []))
    return fast, charged


def all_move_ids():
    """Every moveId in the gamemaster's global moves db (NOT any one
    species' pool) -- the same validation surface deep_dive.py uses for
    its ``[Species.cd_prep]`` injections."""
    return {m['moveId'] for m in load_gamemaster()['moves']}


def preflight_moveset_legality(entries):
    """Every meta moveset id must be in the species' legal gamemaster
    pool. make_battle_pokemon builds ANY id it can look up, and the
    Aegislash form-move mixup is silent, not a crash.

    NARROW CD CARVE-OUT (2026-08-18, Thievul / Icy Wind). An entry may
    carry ``injected_move_ids``: ids admitted for THAT entry only, even
    though the PINNED sim gamemaster does not list them in the species'
    pool. This is the Worlds-side twin of the ``[Species.cd_prep]``
    table in ``thresholds/*.toml``, and it inherits that convention's
    guards, tightened:

    * the injection is DECLARED per entry in ``worlds/meta.toml`` (from
      ``worlds_meta.INJECTED_MOVES``), never inferred here from "the
      move is missing from the pool" -- CLAUDE.md's Baxcalibur trap;
    * ``worlds_meta`` only emits the field after proving the gamemaster
      lags via upstream ``eliteMoves`` + the pvpoke commit history, and
      hard-fails on a DEAD injection (one the entry does not run);
    * each injected id must still exist in the gamemaster's global moves
      db, so the move DATA is the pinned vintage's, not invented;
    * the widening is per-entry and per-id -- no other entry's pool
      moves, and an injected id that this entry does not use is an
      error, not a silently wider pool;
    * it is disclosed to readers (``injection_note`` -> the cheat sheet
      and the hub moveset cell), and printed loudly here.
    """
    errors = []
    moves_db = None
    for e in entries:
        # ``name`` is the DISPLAY label and is only gamemaster-resolvable
        # for entries whose identity is a real speciesId. A moveset-fork
        # arm ("Thievul (NS+IW)") carries the resolvable name separately;
        # every other entry has no such field, so this is byte-identical
        # to looking up e['name'] for all of them.
        gm_name = e.get('gamemaster_name') or e['name']
        fast, charged = legal_move_ids(gm_name)
        if fast is None:
            errors.append(f"{e['name']}: {gm_name!r} is not in the gamemaster")
            continue
        injected = list(e.get('injected_move_ids') or [])
        if injected:
            if moves_db is None:
                moves_db = all_move_ids()
            used = {e['fast_move_id'], *e['charged_move_ids']}
            for mid in injected:
                if mid not in moves_db:
                    errors.append(f"{e['name']}: injected {mid} is not in "
                                  'the gamemaster moves db')
                    continue
                if mid not in used:
                    errors.append(f"{e['name']}: injected {mid} is not used "
                                  'by this entry -- a dead injection must '
                                  'not widen the legality check')
                    continue
                fast = fast | {mid}
                charged = charged | {mid}
                print(f'  cd injection: {e["name"]} admits {mid} (absent '
                      f'from the pinned gamemaster pool; see meta.toml '
                      f'injection_note)')
        if e['fast_move_id'] not in fast:
            errors.append(f"{e['name']}: fast {e['fast_move_id']} not in "
                          f"legal pool {sorted(fast)}")
        for cid in e['charged_move_ids']:
            if cid not in charged:
                errors.append(f"{e['name']}: charged {cid} not legal")
    if errors:
        sys.exit('ABORT: meta moveset fails gamemaster legality:\n'
                 + '\n'.join(errors))


def resolve_moveset(entry):
    """(fast_id, charged_ids) in DIVE order: meta.toml sorts charged ids
    (an alphabetization artifact); whenever the chosen set equals the
    PvPoke default set, use the default's order so the planes are
    slot-for-slot comparable with the shipped dives and the oracle
    harness (charged slot order is PvPoke-visible for equal-energy
    moves -- Aegislash's SHADOW_BALL/GYRO_BALL both cost 50)."""
    fast = entry['fast_move_id']
    charged = list(entry['charged_move_ids'])
    try:
        d_fast, d_charged = get_default_moveset(
            entry['species'], 'great', shadow=entry['shadow'])
    except Exception:
        return fast, charged
    if fast == d_fast and sorted(charged) == sorted(d_charged):
        return d_fast, list(d_charged)
    return fast, charged


def load_meta():
    meta = tomllib.load(open(wp.META_TOML, 'rb'))
    return meta['entries']


_IV_RANK_MEMO: dict = {}


def _ranked(species, shadow):
    """Parent-side iv_rank memo: probe_spreads / cohort_indices /
    _finish_task each need the ranked list, and recomputing two full
    4096-IV rankings per task in the parent serializes the pool
    (2026-08-10 review). 62 unique (species, shadow) pairs total."""
    key = (species, bool(shadow))
    if key not in _IV_RANK_MEMO:
        _IV_RANK_MEMO[key] = iv_rank(species, league='great', shadow=shadow)
    return _IV_RANK_MEMO[key]


def probe_spreads(species, shadow):
    """Tier-1 focal probe spreads: rank-1 SP + max-atk within top-512
    (the session-1 go/no-go probe's convention)."""
    ranked = _ranked(species, shadow)
    top = ranked[:TOP_K]
    r1 = top[0]
    maxatk = max(top, key=lambda e: e['atk'])
    return [(r1['atk_iv'], r1['def_iv'], r1['sta_iv']),
            (maxatk['atk_iv'], maxatk['def_iv'], maxatk['sta_iv'])]


def cohort_indices(species, shadow):
    """(union_indices, top512_mask, atkband_mask) over the union rows.

    top-512 by SP, union best-SP-per-atk-IV (breakpoint-chasers run
    off-SP spreads; sweeping only top-512-SP would miss exactly the
    spreads this analysis is about). Masks label each union row's
    cohort membership for the renderers."""
    ranked = _ranked(species, shadow)
    top512 = list(range(min(TOP_K, len(ranked))))
    byatk, seen = [], set()
    for i, e in enumerate(ranked):
        if e['atk_iv'] not in seen:
            seen.add(e['atk_iv'])
            byatk.append(i)
        if len(seen) == 16:
            break
    union = sorted(set(top512) | set(byatk))
    t_set, a_set = set(top512), set(byatk)
    return (union,
            [i in t_set for i in union],
            [i in a_set for i in union])


def build_tasks(entries, manifest, planes_dir, k=TOP_K, scenarios=SCENARIOS,
                pair_limit=None):
    """The missing-from-manifest worklist. Each task is one
    (pair, direction, bait) plane -- plane_task_worker's input shape --
    tagged with its manifest key and filename."""
    resolved = {}
    for e in entries:
        resolved[e['species_id']] = {
            'entry': e,
            'moveset': resolve_moveset(e),
            'spreads': None,        # filled lazily below
            'cohort': None,
        }
    tasks = []
    pairs = list(itertools.combinations(entries, 2))
    if pair_limit is not None:
        pairs = pairs[:pair_limit]
    for a, b in pairs:
        for focal, opp in ((a, b), (b, a)):
            f = resolved[focal['species_id']]
            o = resolved[opp['species_id']]
            for bait in (True, False):
                key = wp.pair_key(focal['species_id'], opp['species_id'], bait)
                if wp.is_baked(manifest, key, planes_dir):
                    continue
                if f['spreads'] is None:
                    f['spreads'] = probe_spreads(focal['species'],
                                                 focal['shadow'])
                if o['cohort'] is None:
                    o['cohort'] = cohort_indices(opp['species'],
                                                 opp['shadow'])
                union, t_mask, a_mask = o['cohort']
                tasks.append({
                    'key': key,
                    'file': wp.plane_filename(focal['species_id'],
                                              opp['species_id'], bait),
                    'focal_species': focal['species'],
                    'focal_fast': f['moveset'][0],
                    'focal_charged': f['moveset'][1],
                    'focal_shadow': focal['shadow'],
                    'focal_spreads': f['spreads'],
                    'opponent': opp['species'],
                    'opp_fast': o['moveset'][0],
                    'opp_charged': o['moveset'][1],
                    'opp_shadow': opp['shadow'],
                    'league': 'great',
                    'scenarios': list(scenarios),
                    'cohort': union[:k] if k != TOP_K else union,
                    'top512_mask': t_mask[:k] if k != TOP_K else t_mask,
                    'atkband_mask': a_mask[:k] if k != TOP_K else a_mask,
                    'bait': bait,
                })
    return tasks


def _finish_task(task, result, manifest, planes_dir):
    """npz first, manifest entry second (worlds_planes ordering
    contract), then persist the manifest."""
    won, score, n_sims = result
    ranked = _ranked(task['opponent'], task['opp_shadow'])
    cohort_entries = [ranked[i] for i in task['cohort']]
    focal_ranked = _ranked(task['focal_species'], task['focal_shadow'])
    lvl = {(e['atk_iv'], e['def_iv'], e['sta_iv']): e['level']
           for e in focal_ranked}
    arrs = wp.plane_arrays(
        won, score,
        focal_ivs=task['focal_spreads'],
        focal_levels=[lvl[tuple(s)] for s in task['focal_spreads']],
        opp_ivs=[(e['atk_iv'], e['def_iv'], e['sta_iv'])
                 for e in cohort_entries],
        opp_levels=[e['level'] for e in cohort_entries],
        scenarios=task['scenarios'],
        top512_mask=task['top512_mask'],
        atkband_mask=task['atkband_mask'])
    wp.write_plane(task['file'], arrs, planes_dir)
    manifest['entries'][task['key']] = {
        'file': task['file'],
        'won_shape': list(won.shape),
        'n_sims': int(n_sims),
        'content_md5': wp.content_md5(arrs),
        'focal_tags': ['rank1', 'maxatk512'],
        'baked': date.today().isoformat(),
    }
    wp.save_manifest(manifest, planes_dir)


def bless_worlds_code(manifest, predecessor):
    """Re-stamp a manifest's worlds_code from a blessed predecessor.

    Refuses unless ``predecessor`` is BOTH the manifest's current stamp
    and a key of WORLDS_CODE_LINEAGE (so a typo, a stale flag left in a
    script, or a second unrelated producer edit all fail loudly rather
    than blessing something unproven). The blessing is written into the
    manifest as a permanent record, then consumed: the predecessor hash
    is no longer any manifest's stamp, so the entry cannot fire again.
    """
    stamped = manifest.get('worlds_code')
    current = wp.worlds_code_hash()
    if stamped != predecessor:
        sys.exit(f'ABORT: --bless-worlds-code {predecessor} but the manifest '
                 f'is stamped {stamped!r} -- refusing to bless a hash the '
                 'planes were not baked under.')
    if predecessor not in WORLDS_CODE_LINEAGE:
        sys.exit(f'ABORT: {predecessor} is not in WORLDS_CODE_LINEAGE. A '
                 'blessing needs a written proof that the FULL producer '
                 'delta since that hash cannot change any baked plane; '
                 'without one, re-bake (--rebake-all).')
    if stamped == current:
        print(f'worlds_code already {current}; nothing to bless.')
        return manifest
    reason = WORLDS_CODE_LINEAGE[predecessor]
    manifest.setdefault('worlds_code_lineage', []).append({
        'from': predecessor, 'to': current,
        'blessed': date.today().isoformat(), 'reason': reason,
    })
    manifest['worlds_code'] = current
    print(f'Blessed worlds_code {predecessor} -> {current} '
          f'({len(manifest["entries"])} existing planes kept).\n  {reason}')
    return manifest


def bake(entries, planes_dir=wp.PLANES_DIR, k=TOP_K, scenarios=SCENARIOS,
         pair_limit=None, workers=0, rebake_all=False, dry_run=False,
         bless=None):
    """The guarded bake. Returns (n_baked, n_skipped)."""
    old_manifest = wp.load_manifest(planes_dir)
    # Plan first, destroy later: --rebake-all plans against a FRESH
    # manifest but must not unlink anything until we are actually
    # committed to baking (--dry-run previews a full re-bake's cost; the
    # original ordering deleted every plane on that preview -- 2026-08-10
    # review, HIGH).
    manifest = None if rebake_all else old_manifest
    if manifest is None:
        manifest = {**wp.fresh_stamps(), 'created': date.today().isoformat(),
                    'meta_entries': {}, 'entries': {}}
    else:
        if bless:
            manifest = bless_worlds_code(manifest, bless)
        mismatches = wp.stamp_mismatches(manifest)
        if mismatches:
            lines = [f'  {k}: manifest {a!r} != current {b!r}'
                     for k, a, b in mismatches]
            sys.exit('ABORT: manifest stamp mismatch -- Worlds planes are a '
                     'single vintage by design (docs/worlds_prep_plan.md '
                     'Guardrails). Re-run with --rebake-all to DELETE '
                     'worlds/planes/*.npz and start a fresh manifest.\n'
                     + '\n'.join(lines))
        # Meta changes are a per-entry DELTA, not a stamp: an additive
        # row (the documented late-add path) extends the manifest and
        # bakes exactly the new pairs; a changed/removed entry
        # invalidates its planes and refuses.
        changed, removed, added = wp.meta_delta(manifest, entries)
        if changed or removed:
            sys.exit('ABORT: sim-relevant meta change for existing '
                     f'entries (changed: {changed or "-"}, removed: '
                     f'{removed or "-"}) -- their planes are stale. '
                     'Re-run with --rebake-all to start fresh.')
        if added:
            print(f'Meta extended by {len(added)} entries '
                  f'({", ".join(added)}): baking their pairs only.')
    manifest['meta_entries'] = wp.meta_sim_digests(entries)

    total_keys = len(wp.expected_tier1_keys(entries)) if pair_limit is None \
        else None
    tasks = build_tasks(entries, manifest, planes_dir, k=k,
                        scenarios=scenarios, pair_limit=pair_limit)
    n_skipped = (len(manifest['entries'])
                 if manifest['entries'] else 0)
    print(f'Worklist: {len(tasks)} planes to bake, '
          f'{n_skipped} already in the manifest'
          + (f' (target {total_keys} keys).' if total_keys else '.'))
    if dry_run or not tasks:
        return 0, n_skipped

    if rebake_all and old_manifest is not None:
        # Committed to baking: delete the old vintage and land the fresh
        # (empty) manifest in the same step, so no window exists where
        # the on-disk manifest points at deleted files.
        for entry in old_manifest.get('entries', {}).values():
            p = wp.out_path(entry['file'], planes_dir)
            if p.exists():
                p.unlink()
        wp.save_manifest(manifest, planes_dir)

    start_digest = fresh_engine_digest()
    t0 = time.time()
    baked = 0
    sims = 0
    if workers and workers > 1:
        with multiprocessing.Pool(workers) as pool:
            for task, result in zip(
                    tasks, pool.imap(plane_task_worker, tasks)):
                _finish_task(task, result, manifest, planes_dir)
                baked += 1
                sims += result[2]
                print(f'  [{baked}/{len(tasks)}] {task["key"]} '
                      f'({result[2]} sims)')
    else:
        for task in tasks:
            result = plane_task_worker(task)
            _finish_task(task, result, manifest, planes_dir)
            baked += 1
            sims += result[2]
            print(f'  [{baked}/{len(tasks)}] {task["key"]} '
                  f'({result[2]} sims)')
    dt = time.time() - t0
    print(f'Baked {baked} planes, {sims} sims in {dt:.1f}s '
          f'({sims / dt:.0f} sims/s).')

    if fresh_engine_digest() != start_digest:
        sys.exit('ABORT: engine sources changed MID-BAKE -- the planes '
                 'written this run are mixed-vintage. Delete them '
                 '(--rebake-all) after settling the engine.')
    return baked, n_skipped


def main():
    parser = argparse.ArgumentParser(
        description='Worlds 2026 Tier-1 plane bake (idempotent, '
                    'manifest-driven).',
        epilog='Sequencing rule (TODO.md "Worlds 2026"): the pending '
               'behavior-neutral engine-hash batch lands BEFORE the first '
               'real bake, or not at all until after Worlds -- the manifest '
               'pins one engine vintage for the whole campaign.')
    parser.add_argument('--pair-limit', type=int, default=None,
                        help='bake only the first N unordered pairs (smoke)')
    parser.add_argument('--workers', type=int,
                        default=max(1, multiprocessing.cpu_count() - 2))
    parser.add_argument('--dry-run', action='store_true',
                        help='print the worklist and exit')
    parser.add_argument('--rebake-all', action='store_true',
                        help='DELETE all planes + manifest and start fresh '
                             '(the only deletion path)')
    parser.add_argument('--allow-dirty-engine', action='store_true')
    parser.add_argument('--bless-worlds-code', metavar='HASH', default=None,
                        help='re-stamp the manifest from this blessed '
                             'predecessor worlds_code hash instead of '
                             'refusing (must be a WORLDS_CODE_LINEAGE key '
                             'AND the manifest\'s current stamp); the '
                             'blessing is recorded in the manifest')
    args = parser.parse_args()

    install_sweep_cache_poison()
    preflight_engine_clean(allow_dirty=args.allow_dirty_engine)
    entries = load_meta()
    preflight_moveset_legality(entries)
    bake(entries, pair_limit=args.pair_limit, workers=args.workers,
         rebake_all=args.rebake_all, dry_run=args.dry_run,
         bless=args.bless_worlds_code)
    return 0


if __name__ == '__main__':
    sys.exit(main())
