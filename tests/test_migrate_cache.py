"""Tests for scripts/migrate_cache.py — selective sweep-cache invalidation.

Pins the bug-#1 shadow_xor predicate (2026-06-27): after a localized engine
fix, a column is AFFECTED iff exactly one side is shadow; both-shadow and
both-non-shadow columns are provably unchanged and get blessed (re-stamped)
so the re-dive serves them warm, while shadow-XOR columns are deleted to
re-sim cold.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sweep_cache = sys.modules.get("sweep_cache") or _load("sweep_cache")
migrate_cache = sys.modules.get("migrate_cache") or _load("migrate_cache")


def _focal_fields(shadow):
    return sweep_cache.focal_key_fields(
        species='Azumarill', league='great', shadow=shadow,
        fast_id='BUBBLE', charged_ids=['ICE_BEAM'],
        iv_floor=None, shield_scenarios=[(0, 0)], bait_mode='bait')


def _col_fields(opp_shadow):
    return sweep_cache.column_key_fields(
        opp_species='Medicham', opp_shadow=opp_shadow, opp_ivs=(15, 15, 15),
        opp_level=50.0, opp_fast_id='COUNTER', opp_charged_ids=['PSYCHIC'])


def _put(focal_shadow, opp_shadow):
    """Write a 1x1 column for (focal_shadow, opp_shadow) and return its
    sidecar path."""
    cache = sweep_cache.SweepCache(_focal_fields(focal_shadow))
    cf = _col_fields(opp_shadow)
    cache.put_column(cf, {'score': np.zeros((1, 1)), 'energy': np.zeros((1, 1))})
    return cache._col_path(cf).with_suffix('.json')


def _stamp(json_path):
    return sweep_cache.SweepCache.read_stamp(json_path)


def test_shadow_xor_predicate():
    p = migrate_cache.PREDICATES['shadow_xor']
    assert p({'shadow': False}, {'shadow': False}) is False  # both non-shadow
    assert p({'shadow': True}, {'shadow': True}) is False    # both shadow
    assert p({'shadow': True}, {'shadow': False}) is True    # XOR
    assert p({'shadow': False}, {'shadow': True}) is True    # XOR


def test_migrate_blesses_unaffected_deletes_affected(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'oldengine000')

    # Four columns under two focal dirs, all stamped at the old engine.
    unaff_nn = _put(focal_shadow=False, opp_shadow=False)  # both non-shadow
    unaff_ss = _put(focal_shadow=True, opp_shadow=True)    # both shadow
    aff_a = _put(focal_shadow=False, opp_shadow=True)      # XOR
    aff_b = _put(focal_shadow=True, opp_shadow=False)      # XOR
    for sc in (unaff_nn, unaff_ss, aff_a, aff_b):
        assert _stamp(sc) == 'oldengine000'

    # Engine changes (a localized shadow-only fix).
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'newengine111')

    # Dry-run touches nothing.
    migrate_cache.migrate(tmp_path, 'oldengine000', 'shadow_xor', apply=False)
    assert _stamp(unaff_nn) == 'oldengine000'
    assert aff_a.exists()

    # Apply: unaffected re-stamped to the new engine (warm), affected deleted.
    migrate_cache.migrate(tmp_path, 'oldengine000', 'shadow_xor', apply=True)
    assert _stamp(unaff_nn) == 'newengine111'
    assert _stamp(unaff_ss) == 'newengine111'
    assert unaff_nn.with_suffix('.npz').exists()  # .npz untouched by bless
    for aff in (aff_a, aff_b):
        assert not aff.exists()
        assert not aff.with_suffix('.npz').exists()


def test_migrate_skips_other_gamemaster(tmp_path, monkeypatch):
    # A column whose focal dir carries a different gamemaster vintage must be
    # left alone — the predicate models only the engine delta.
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'oldengine000')
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'oldgm')
    sc = _put(focal_shadow=False, opp_shadow=False)  # unaffected, but old GM

    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'newengine111')
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'newgm')
    migrate_cache.migrate(tmp_path, 'oldengine000', 'shadow_xor', apply=True)
    # Untouched: still old engine stamp (would never be read under new GM dir).
    assert _stamp(sc) == 'oldengine000'
