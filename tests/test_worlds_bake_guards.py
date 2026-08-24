"""Worlds bake-driver guardrails (scripts/worlds_bake.py).

The plan's standing rules as CODE (docs/worlds_prep_plan.md
"Guardrails"): the bake never touches the sweep cache, never emits a
bundler-colliding filename, never bakes on (or across) an engine edit,
and is idempotent from its manifest. Each guard gets both the
mechanism test and -- for the source scans -- a positive control per
the testing policy (a scanner that can't find the real call sites is a
dead scanner).
"""
import ast
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT / 'src', REPO_ROOT / 'scripts'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import worlds_bake as wb  # noqa: E402
import worlds_planes as wp  # noqa: E402

WORLDS_MODULES = ('worlds_planes.py', 'worlds_bake.py', 'worlds_tier0.py',
                  'deep_dive_lib/robustness.py')
ALLOWED_SWEEP_CACHE_IMPORTS = {'engine_hash', 'gamemaster_hash',
                               'gamemaster_subset', 'write_sidecar'}
FORBIDDEN_CALLEES = {'SweepCache', 'put_column', 'get_column', 'iv_sweep',
                     'focal_key_fields', 'column_key_fields'}


def _scan(path):
    """(imported-from-sweep_cache names, forbidden callee hits)."""
    tree = ast.parse((REPO_ROOT / 'scripts' / path).read_text())
    imported, hits = set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'sweep_cache':
            imported |= {a.name for a in node.names}
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == 'sweep_cache':
                    imported.add('<module>')
        if isinstance(node, ast.Call):
            callee = node.func
            name = (callee.attr if isinstance(callee, ast.Attribute)
                    else callee.id if isinstance(callee, ast.Name) else None)
            if name in FORBIDDEN_CALLEES:
                hits.append((path, node.lineno, name))
    return imported, hits


def test_no_worlds_module_touches_the_sweep_cache():
    for mod in WORLDS_MODULES:
        imported, hits = _scan(mod)
        assert not hits, f'sweep-cache call in {mod}: {hits}'
        bad = imported - ALLOWED_SWEEP_CACHE_IMPORTS - {'<module>'}
        assert not bad, f'{mod} imports sweep_cache names {bad}'
        assert '<module>' not in imported or mod == 'worlds_bake.py', (
            f'{mod} imports the whole sweep_cache module')


def test_sweep_cache_scanner_finds_the_real_call_sites():
    """Positive control + floor: the same scanner over the module that
    LEGITIMATELY uses the cache must find its call sites (>= 3 today:
    SweepCache(), get_column, put_column -- floor set below the count
    per policy)."""
    _imported, hits = _scan('deep_dive_lib/sweep.py')
    assert len(hits) >= 3, f'dead scanner: only found {hits}'
    assert {h[2] for h in hits} >= {'put_column', 'get_column'}


def test_bake_poison_makes_cache_calls_raise():
    import sweep_cache as swc
    orig_put, orig_get = swc.SweepCache.put_column, swc.SweepCache.get_column
    try:
        wb.install_sweep_cache_poison()
        cache = swc.SweepCache.__new__(swc.SweepCache)
        with pytest.raises(RuntimeError, match='never touch the sweep'):
            cache.put_column('k', {}, {})
        with pytest.raises(RuntimeError, match='never touch the sweep'):
            cache.get_column('k', {})
    finally:
        swc.SweepCache.put_column = orig_put
        swc.SweepCache.get_column = orig_get


def test_fresh_engine_digest_is_not_memoized(tmp_path, monkeypatch):
    """The mid-bake guard exists BECAUSE sweep_cache.engine_hash memoizes;
    both properties are pinned so a future de-memoization triggers a
    review instead of leaving a silently redundant guard."""
    import sweep_cache as swc
    assert swc.engine_hash() == swc.engine_hash()      # memoized value
    d1 = wb.fresh_engine_digest()
    assert d1 == wb.fresh_engine_digest()              # deterministic
    # Point the digest at a scratch tree and mutate it: the digest must
    # move (a memoized implementation would not re-read the bytes).
    src = tmp_path / 'src' / 'gopvpsim'
    src.mkdir(parents=True)
    for name in wb._ENGINE_SRC_FILES:
        (src / name).write_text('x = 1\n')
    monkeypatch.setattr(wb, 'REPO', tmp_path)
    a = wb.fresh_engine_digest()
    (src / 'battle.py').write_text('x = 2\n')
    b = wb.fresh_engine_digest()
    assert a != b


def test_bake_aborts_on_dirty_engine_tree(monkeypatch, capsys):
    real_run = subprocess.run

    def fake_run(cmd, **kw):
        if 'status' in cmd:
            class R:
                stdout = ' M src/gopvpsim/battle.py\n'
            return R()
        return real_run(cmd, **kw)

    monkeypatch.setattr(wb.subprocess, 'run', fake_run)
    with pytest.raises(SystemExit, match='engine tree is dirty'):
        wb.preflight_engine_clean(allow_dirty=False)
    wb.preflight_engine_clean(allow_dirty=True)        # override path works


def test_moveset_legality_preflight():
    """The real meta passes; the Aegislash form-move mixup (Blade species
    with the Shield fast id) is exactly the silent-corruption path the
    2026-08-10 audit found -- it must FAIL here, loudly."""
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    wb.preflight_moveset_legality(entries)             # no exit
    doctored = [{
        'name': 'Aegislash (Blade)',
        'species': 'Aegislash (Blade)',
        'species_id': 'aegislash_blade',
        'shadow': False,
        'fast_move_id': 'AEGISLASH_CHARGE_PSYCHO_CUT',  # Shield-only id
        'charged_move_ids': ['SHADOW_BALL', 'GYRO_BALL'],
    }]
    with pytest.raises(SystemExit, match='legality'):
        wb.preflight_moveset_legality(doctored)


def test_resolve_moveset_restores_dive_order():
    """meta.toml alphabetizes charged ids; when the chosen set equals the
    PvPoke default set the driver must use the DEFAULT order (slot order
    is PvPoke-visible for equal-energy moves -- Aegislash's two 50s)."""
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    aegis = next(e for e in entries if e['species_id'] == 'aegislash_shield')
    assert aegis['charged_move_ids'] == ['GYRO_BALL', 'SHADOW_BALL']  # sorted
    fast, charged = wb.resolve_moveset(aegis)
    assert fast == 'AEGISLASH_CHARGE_PSYCHO_CUT'
    assert charged == ['SHADOW_BALL', 'GYRO_BALL']     # the dive/oracle order
    # A modal-disagreeing entry keeps its meta order untouched.
    forre = next(e for e in entries
                 if e['species_id'] == 'forretress_shadow')
    assert forre['default_disagrees'] is True
    assert wb.resolve_moveset(forre) == (forre['fast_move_id'],
                                         forre['charged_move_ids'])


def test_one_pair_bake_is_idempotent_and_clean(tmp_path):
    """End-to-end on one real pair at k=6, 2 scenarios: first bake sims
    and writes npz+manifest; second bake is a pure skip (0 tasks); the
    output dir contains ONLY npz + manifest.json; a deleted npz forces a
    re-bake despite the manifest entry."""
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    two = [e for e in entries
           if e['species_id'] in ('lickilicky', 'azumarill')]
    assert len(two) == 2
    scen = [(0, 0), (1, 1)]
    baked, _ = wb.bake(two, planes_dir=tmp_path, k=6, scenarios=scen,
                       workers=0)
    assert baked == 4                                  # 2 directions x 2 bait
    files = sorted(p.name for p in tmp_path.rglob('*') if p.is_file())
    assert files and all(f.endswith('.npz') or f == 'manifest.json'
                         for f in files)
    manifest = wp.load_manifest(tmp_path)
    assert len(manifest['entries']) == 4
    for entry in manifest['entries'].values():
        assert entry['won_shape'][2] == len(scen)
        assert entry['n_sims'] > 0

    baked2, _ = wb.bake(two, planes_dir=tmp_path, k=6, scenarios=scen,
                        workers=0)
    assert baked2 == 0                                 # idempotent skip

    victim = next(iter(manifest['entries'].values()))['file']
    wp.out_path(victim, tmp_path).unlink()
    baked3, _ = wb.bake(two, planes_dir=tmp_path, k=6, scenarios=scen,
                        workers=0)
    assert baked3 == 1                                 # only the missing one

    # Planes are readable and non-trivial (mixed outcomes across cells).
    back = wp.read_plane(victim, tmp_path)
    assert back['won'].shape[0] == 2                   # 2 probe spreads
    key = wp.pair_key('lickilicky', 'azumarill', True)
    f = manifest['entries'][key]['file']
    plane = wp.read_plane(f, tmp_path)
    assert plane['won'].any() and not plane['won'].all()


def test_bake_refuses_stamp_mismatch_without_deleting(tmp_path):
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    two = [e for e in entries
           if e['species_id'] in ('lickilicky', 'azumarill')]
    wb.bake(two, planes_dir=tmp_path, k=4, scenarios=[(1, 1)], workers=0)
    manifest = wp.load_manifest(tmp_path)
    manifest['engine'] = 'stale-engine'
    wp.save_manifest(manifest, tmp_path)
    npz_before = sorted(p.name for p in tmp_path.glob('*.npz'))
    with pytest.raises(SystemExit, match='stamp mismatch'):
        wb.bake(two, planes_dir=tmp_path, k=4, scenarios=[(1, 1)], workers=0)
    assert sorted(p.name for p in tmp_path.glob('*.npz')) == npz_before
    # --rebake-all IS the deletion path: fresh manifest, planes re-baked.
    baked, _ = wb.bake(two, planes_dir=tmp_path, k=4, scenarios=[(1, 1)],
                       workers=0, rebake_all=True)
    assert baked == 4
    assert wp.load_manifest(tmp_path)['engine'] != 'stale-engine'


def test_rebake_all_dry_run_deletes_nothing(tmp_path):
    """Session-2c deleted every plane on `--rebake-all --dry-run` (the
    natural 'preview the cost of a full re-bake' invocation) before the
    dry-run early-exit ran -- 2026-08-10 review, HIGH. Now planning is
    non-destructive: deletion happens only once the bake is committed."""
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    two = [e for e in entries
           if e['species_id'] in ('lickilicky', 'azumarill')]
    wb.bake(two, planes_dir=tmp_path, k=4, scenarios=[(1, 1)], workers=0)
    before = sorted(p.name for p in tmp_path.iterdir())
    manifest_before = wp.load_manifest(tmp_path)
    baked, _ = wb.bake(two, planes_dir=tmp_path, k=4, scenarios=[(1, 1)],
                       workers=0, rebake_all=True, dry_run=True)
    assert baked == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert wp.load_manifest(tmp_path) == manifest_before
    # The real (non-dry) rebake still works and never leaves the old
    # manifest pointing at deleted files.
    baked2, _ = wb.bake(two, planes_dir=tmp_path, k=4, scenarios=[(1, 1)],
                        workers=0, rebake_all=True)
    assert baked2 == 4


def test_incremental_meta_add_extends_without_deleting(tmp_path):
    """The plan's pinned late-add affordance (docs/worlds_prep_plan.md:
    'Adding a mon later = one meta.toml row + N new pairs simmed'):
    session-2c hashed the WHOLE meta.toml into a refuse-stamp, so ANY
    meta edit -- including the 580bfa7 prose fix -- forced --rebake-all.
    Pre-fix behavior: SystemExit 'stamp mismatch' here. Now: additive
    delta bakes exactly the new pairs, existing planes untouched."""
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    by_id = {e['species_id']: e for e in entries}
    two = [by_id['lickilicky'], by_id['azumarill']]
    wb.bake(two, planes_dir=tmp_path, k=3, scenarios=[(1, 1)], workers=0)
    npz_before = sorted(p.name for p in tmp_path.glob('*.npz'))
    assert len(npz_before) == 4

    three = two + [by_id['tinkaton']]
    baked, _ = wb.bake(three, planes_dir=tmp_path, k=3, scenarios=[(1, 1)],
                       workers=0)
    assert baked == 8                       # exactly the new pairs' planes
    assert set(npz_before) <= {p.name for p in tmp_path.glob('*.npz')}
    manifest = wp.load_manifest(tmp_path)
    assert len(manifest['entries']) == 12
    assert set(manifest['meta_entries']) == {'lickilicky', 'azumarill',
                                             'tinkaton'}

    # A sim-relevant CHANGE to an existing entry still refuses, without
    # deleting anything.
    doctored = [dict(by_id['lickilicky'],
                     charged_move_ids=['BODY_SLAM', 'EARTHQUAKE']),
                by_id['azumarill'], by_id['tinkaton']]
    with pytest.raises(SystemExit, match='sim-relevant meta change'):
        wb.bake(doctored, planes_dir=tmp_path, k=3, scenarios=[(1, 1)],
                workers=0)
    assert len(list(tmp_path.glob('*.npz'))) == 12


def test_bake_aborts_when_engine_digest_changes_mid_bake(tmp_path,
                                                        monkeypatch):
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    two = [e for e in entries
           if e['species_id'] in ('lickilicky', 'azumarill')]
    digests = iter(['start', 'changed'])
    monkeypatch.setattr(wb, 'fresh_engine_digest', lambda: next(digests))
    with pytest.raises(SystemExit, match='MID-BAKE'):
        wb.bake(two, planes_dir=tmp_path, k=2, scenarios=[(1, 1)],
                workers=0, pair_limit=1)


def test_cohort_indices_shape():
    """top-512 SP union best-SP-per-atk-IV, with membership masks; the
    atk-band reaches beyond top-512 for low-atk species (Aegislash
    Shield's band bottoms out at rank 2609 -- the reason cohort indices
    exist at all)."""
    union, t_mask, a_mask = wb.cohort_indices('Lickilicky', False)
    assert len(union) == len(t_mask) == len(a_mask)
    assert sum(t_mask) == 512
    assert sum(a_mask) == 16
    union_a, _, a_mask_a = wb.cohort_indices('Aegislash (Shield)', False)
    beyond = [i for i, m in zip(union_a, a_mask_a) if m and i >= 512]
    assert beyond, 'atk-band cohort never left top-512 -- fixture stale?'


# ---------------------------------------------------------------------------
# CD-move injection carve-out (2026-08-18, Thievul / Icy Wind)
# ---------------------------------------------------------------------------

def _thievul_entry(**over):
    """A Thievul meta entry shaped like worlds_meta emits it."""
    e = {
        'name': 'Thievul', 'species': 'Thievul', 'species_id': 'thievul',
        'shadow': False,
        'fast_move_id': 'SUCKER_PUNCH',
        'charged_move_ids': ['ICY_WIND', 'NIGHT_SLASH'],
        'injected_move_ids': ['ICY_WIND'],
    }
    e.update(over)
    return e


# 2026-08-24: the LIVE data-cache gamemaster caught up on Thievul's Icy Wind
# (upstream pvpoke f754cd6fc landed; the cache left the Worlds pin during the
# Cramorant session). THREE injection guards below are contracts about the
# PINNED Worlds vintage (pvpoke f60a41199), which still lags -- they skip on
# a caught-up gamemaster and AUTO-RE-ARM whenever the cache is re-pinned for
# a Worlds render. (test_shipped_meta_declares_the_injection_it_needs is NOT
# skipped -- its all-species legality half holds on any vintage and only its
# anti-staleness half is vintage-gated inline.) Post-Worlds (after
# 2026-08-30): retire the cd_prep table + injection declarations and delete
# these guards per the test_icy_wind docstring (TODO "Worlds robustness").
_icy_wind_caught_up = pytest.mark.skipif(
    'ICY_WIND' in (wb.legal_move_ids('Thievul')[1] or set()),
    reason='live gamemaster lists Icy Wind for Thievul (off the Worlds pin); '
           'injection guards apply to the pinned vintage only -- see comment')


@_icy_wind_caught_up
def test_icy_wind_is_absent_from_thievul_pinned_pool():
    """The premise of the whole carve-out, pinned: our gamemaster really
    does lag. If this ever fails the gamemaster has moved off the Worlds
    pin (or upstream landed), and the injection must be retired, not
    kept -- CLAUDE.md's cd_prep rule."""
    fast, charged = wb.legal_move_ids('Thievul')
    assert fast is not None, 'Thievul missing from the gamemaster'
    assert 'ICY_WIND' not in charged
    assert 'ICY_WIND' not in fast
    # ... while the move itself exists in the global moves db, so the
    # injected move DATA is the pinned vintage's, not invented.
    assert 'ICY_WIND' in wb.all_move_ids()


@_icy_wind_caught_up
def test_injection_admits_the_declared_move():
    """PRE-FIX VALUE: without injected_move_ids this entry hard-exits
    ('charged ICY_WIND not legal') -- that was the behavior before
    2026-08-18 and is what the carve-out changes."""
    with pytest.raises(SystemExit, match='ICY_WIND'):
        wb.preflight_moveset_legality([_thievul_entry(injected_move_ids=[])])
    wb.preflight_moveset_legality([_thievul_entry()])      # no exit


@_icy_wind_caught_up
def test_injection_is_per_entry_and_never_widens_a_neighbour():
    """The widening must not leak: a second entry in the SAME call that
    does not declare the injection still fails on the same move id."""
    other = _thievul_entry(name='Thievul', species_id='thievul_copy',
                           injected_move_ids=[])
    with pytest.raises(SystemExit, match='ICY_WIND'):
        wb.preflight_moveset_legality([_thievul_entry(), other])


def test_dead_injection_is_an_error():
    """Declaring a move the entry does not run would widen the legality
    check for nothing -- exactly the silent hole the preflight exists to
    close."""
    dead = _thievul_entry(charged_move_ids=['NIGHT_SLASH', 'PLAY_ROUGH'])
    with pytest.raises(SystemExit, match='dead injection'):
        wb.preflight_moveset_legality([dead])


def test_injection_of_an_unknown_move_id_is_an_error():
    bogus = _thievul_entry(charged_move_ids=['NOT_A_MOVE', 'NIGHT_SLASH'],
                           injected_move_ids=['NOT_A_MOVE'])
    with pytest.raises(SystemExit, match='not in the gamemaster moves db'):
        wb.preflight_moveset_legality([bogus])


def test_shipped_meta_declares_the_injection_it_needs():
    """Contract at the boundary, split by gamemaster vintage (2026-08-24):

    ALWAYS (any vintage): every meta entry whose moveset leaves the
    species' legal pool must DECLARE the excess -- the all-species
    legality contract. This half must never be skipped: it is what
    catches a genuinely illegal moveset.

    PINNED VINTAGE ONLY: each declared injection must also be genuinely
    outside the pool (`==`, not `<=`). On a caught-up gamemaster the
    Thievul declaration is expectedly stale-but-harmless; retirement is
    tracked in TODO ("post-CD cleanup" + the POST-WORLDS note)."""
    caught_up = 'ICY_WIND' in (wb.legal_move_ids('Thievul')[1] or set())
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    declared = {e['species_id']: set(e.get('injected_move_ids') or [])
                for e in entries}
    assert declared.get('thievul') == {'ICY_WIND'}, \
        'the Thievul Icy Wind injection is the reason this exists'
    # Both arms of the moveset fork declare it independently -- the
    # carve-out is per ENTRY, not per species.
    assert declared.get('thievul_iw_pr') == {'ICY_WIND'}
    n_declared = 0
    for e in entries:
        fast, charged = wb.legal_move_ids(e.get('gamemaster_name') or e['name'])
        assert fast is not None, e['name']
        outside = ({e['fast_move_id']} - fast) | (
            set(e['charged_move_ids']) - charged)
        assert outside <= declared[e['species_id']], (
            f"{e['name']}: moveset leaves the legal pool on {sorted(outside)} "
            f"but declares only {sorted(declared[e['species_id']])}")
        if not caught_up:
            assert outside == declared[e['species_id']], (
                f"{e['name']}: declares {sorted(declared[e['species_id']])} "
                f"but only {sorted(outside)} is outside the pinned pool")
        n_declared += bool(declared[e['species_id']])
    assert n_declared >= 1                     # scanner self-test


# ---------------------------------------------------------------------------
# worlds_code lineage blessing
# ---------------------------------------------------------------------------

def test_bless_refuses_unproven_or_mismatched_predecessors():
    """Default-deny: blessing needs BOTH a written proof (a lineage key)
    and agreement with what the planes were actually baked under."""
    known = next(iter(wb.WORLDS_CODE_LINEAGE))
    with pytest.raises(SystemExit, match='not in WORLDS_CODE_LINEAGE'):
        wb.bless_worlds_code({'worlds_code': 'deadbeef0000', 'entries': {}},
                             'deadbeef0000')
    with pytest.raises(SystemExit, match='refusing to bless'):
        wb.bless_worlds_code({'worlds_code': 'somethingelse', 'entries': {}},
                             known)


def test_bless_restamps_and_records_the_lineage():
    known = next(iter(wb.WORLDS_CODE_LINEAGE))
    m = {'worlds_code': known, 'entries': {'a|b|bait': {}}}
    out = wb.bless_worlds_code(m, known)
    assert out['worlds_code'] == wp.worlds_code_hash()
    rec, = out['worlds_code_lineage']
    assert rec['from'] == known and rec['to'] == wp.worlds_code_hash()
    assert wb.WORLDS_CODE_LINEAGE[known] in rec['reason']
    # One-shot: the predecessor is no longer the stamp, so a second
    # blessing of the same hash cannot fire.
    with pytest.raises(SystemExit, match='refusing to bless'):
        wb.bless_worlds_code(out, known)
