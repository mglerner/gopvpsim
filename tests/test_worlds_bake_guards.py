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
