"""Pins the per-round ``SlayerCache.save()`` flush (backlog-47).

A crash partway through ``iterative_slayer_discovery`` should lose at most
one round's sims, not the whole discovery run. Two guards:

- Round-trip: ``save()`` then a fresh load preserves the cached scores.
- In-loop placement: ``iterative_slayer_discovery`` calls ``cache.save()``
  *inside* the per-round ``for round_idx`` loop. The round-trip alone is
  true-by-construction and would not catch a save that only fires after the
  loop (i.e. once at the end), so this AST guard checks the placement.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Load slayer_cache standalone (no heavy gopvpsim imports). save()/put()/get()
# never touch the deferred sweep_cache hash path, so no extra wiring needed.
_spec = importlib.util.spec_from_file_location(
    "slayer_cache", REPO_ROOT / "scripts" / "slayer_cache.py")
slayer_cache = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(slayer_cache)


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(slayer_cache, 'CACHE_DIR', tmp_path)
    c = slayer_cache.SlayerCache(cache_key='unit_roundtrip', disk=True)
    c.put(0, 1, [501, 499])
    c.put(2, 3, [600])
    c.save()

    # A fresh instance reads the flushed data back from disk.
    c2 = slayer_cache.SlayerCache(cache_key='unit_roundtrip', disk=True)
    assert c2.get(0, 1) == (501, 499)
    assert c2.get(2, 3) == (600,)


def test_save_is_called_inside_round_loop():
    """cache.save() must live inside the per-round loop, not only after it."""
    src = (REPO_ROOT / "scripts" / "deep_dive_slayer.py").read_text()
    tree = ast.parse(src)
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef)
                and n.name == 'iterative_slayer_discovery')
    round_loop = next(
        n for n in ast.walk(func)
        if isinstance(n, ast.For)
        and isinstance(n.target, ast.Name)
        and n.target.id == 'round_idx')
    saves = [
        n for n in ast.walk(round_loop)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == 'save'
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == 'cache'
    ]
    assert saves, "cache.save() not found inside the per-round for round_idx loop"
