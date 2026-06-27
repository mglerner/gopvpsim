"""Key-sensitivity tests for ``scripts/slayer_cache.py``.

Pins the 2026-06-11 review fixes:

- D2: the key must include ``iv_floor`` — cache entries are keyed by
  positional iv_meta indices, and the floor changes the index↔IV mapping,
  so floored and floorless runs must not share a file.
- D3: ``_move_hash`` must include the buff fields (rebalances routinely
  tweak only buffs/buffApplyChance), and the key embeds the engine-source
  hash so engine edits invalidate without a manual CACHE_VERSION bump.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "slayer_cache", REPO_ROOT / "scripts" / "slayer_cache.py")
slayer_cache = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(slayer_cache)

# slayer_cache's key embeds sweep_cache's engine/gamemaster hashes via a
# deferred import resolved against sys.modules — make it loadable.
import sys
if "sweep_cache" not in sys.modules:
    _sw_spec = importlib.util.spec_from_file_location(
        "sweep_cache", REPO_ROOT / "scripts" / "sweep_cache.py")
    _sw = importlib.util.module_from_spec(_sw_spec)
    assert _sw_spec.loader is not None
    sys.modules["sweep_cache"] = _sw
    _sw_spec.loader.exec_module(_sw)


_FAST = {'moveId': 'F', 'power': 5, 'energy': 0, 'energyGain': 8,
         'cooldown': 1000, 'type': 'normal'}
_CM = {'moveId': 'C', 'power': 60, 'energy': 45, 'energyGain': 0,
       'type': 'normal', 'buffs': [0, -1], 'buffTarget': 'opponent',
       'buffApplyChance': '1'}
_STATS = {'atk': 100, 'def': 100, 'hp': 100}


def _key(**overrides):
    kw = dict(species='Testmon', league='great', shadow=False,
              fast_move=_FAST, charged_moves=[_CM], base_stats=_STATS,
              shield_scenarios=[(1, 1)], iv_floor=None)
    kw.update(overrides)
    return slayer_cache.compute_cache_key(**kw)


def test_iv_floor_changes_key():
    assert _key(iv_floor=None) != _key(iv_floor=(4, 0, 0))
    assert _key(iv_floor=(4, 0, 0)) != _key(iv_floor=(0, 4, 0))
    # Same floor -> same key (stability).
    assert _key(iv_floor=(4, 0, 0)) == _key(iv_floor=(4, 0, 0))


def test_buff_fields_change_key():
    nerfed = dict(_CM, buffApplyChance='0.5')
    assert _key(charged_moves=[nerfed]) != _key()
    rebuffed = dict(_CM, buffs=[0, -2])
    assert _key(charged_moves=[rebuffed]) != _key()


def test_engine_hash_is_embedded():
    # Same inputs, different memoized engine hash -> different key.
    import sweep_cache as sw
    base = _key()
    orig = sw._ENGINE_HASH
    try:
        sw._ENGINE_HASH = 'deadbeef0000'
        assert _key() != base
    finally:
        sw._ENGINE_HASH = orig


def test_scenario_list_changes_key():
    all_nine = [(a, b) for a in range(3) for b in range(3)]
    assert _key(shield_scenarios=all_nine) != _key()


def test_focal_max_level_changes_key():
    # Bug #4 (2026-06-27): the focal level cap lifts the whole mirror cohort's
    # per-IV levels, so a Master mirror-slayer run at L50 must not serve an
    # L51 run's cached scores.
    assert _key(focal_max_level=50.0) != _key(focal_max_level=51.0)
    # Default (None) is its own bucket, distinct from an explicit cap.
    assert _key(focal_max_level=None) != _key(focal_max_level=51.0)
    # Same cap -> same key (stability).
    assert _key(focal_max_level=51.0) == _key(focal_max_level=51.0)
