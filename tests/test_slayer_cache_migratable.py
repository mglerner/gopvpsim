"""v5 slayer cache: per-file engine/gamemaster sidecar STAMP (migratable).

Pins the 2026-06-29 re-schema that mirrors the sweep cache v6/v7 design: the
engine + gamemaster hashes moved out of the opaque filename and into a
``{key}.json`` sidecar, so a stale stamp is a SAFE MISS (re-sim, never serve
stale) and migrate_cache can warm-bless the unaffected entries.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
slayer_cache = sys.modules.get("slayer_cache") or _load("slayer_cache")


def _fresh(monkeypatch, tmp_path, eng='eng_cur', gm='gm_cur'):
    monkeypatch.setattr(slayer_cache, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', eng)
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', gm)


def test_save_writes_sidecar_with_stamp_and_scenario(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    scen = {'species': 'Pangoro', 'league': 'great', 'shadow': False,
            'fast': 'KARATE_CHOP', 'charged': ['CLOSE_COMBAT', 'NIGHT_SLASH']}
    c = slayer_cache.SlayerCache(cache_key='Pangoro_great_abc', disk=True,
                                 scenario=scen)
    c.put(0, 1, [501, 499])
    c.save()
    side = tmp_path / 'Pangoro_great_abc.json'
    assert side.exists()
    d = json.loads(side.read_text())
    assert d['engine'] == 'eng_cur' and d['gamemaster'] == 'gm_cur'
    assert d['scenario'] == scen


def test_matching_stamp_is_a_hit(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    c = slayer_cache.SlayerCache(cache_key='k', disk=True, scenario={})
    c.put(0, 1, [600])
    c.save()
    # Fresh instance, SAME engine+gamemaster -> warm load.
    c2 = slayer_cache.SlayerCache(cache_key='k', disk=True)
    assert c2.get(0, 1) == (600,)


def test_stale_engine_stamp_is_a_safe_miss(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path, eng='eng_old')
    c = slayer_cache.SlayerCache(cache_key='k', disk=True, scenario={})
    c.put(0, 1, [600])
    c.save()
    # Engine bumps -> the cached pkl must NOT be served (stale).
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'eng_new')
    c2 = slayer_cache.SlayerCache(cache_key='k', disk=True)
    assert c2.get(0, 1) is None        # miss, not a stale serve
    assert c2.data == {}


def test_stale_gamemaster_stamp_is_a_safe_miss(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path, gm='gm_old')
    c = slayer_cache.SlayerCache(cache_key='k', disk=True, scenario={})
    c.put(0, 1, [600])
    c.save()
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_new')
    c2 = slayer_cache.SlayerCache(cache_key='k', disk=True)
    assert c2.get(0, 1) is None


def test_pkl_without_sidecar_is_a_miss(tmp_path, monkeypatch):
    # A bare .pkl (e.g. a pre-v5 file or a half-write) with no sidecar must not
    # be served — the stamp is unverifiable.
    _fresh(monkeypatch, tmp_path)
    import pickle
    (tmp_path).mkdir(parents=True, exist_ok=True)
    with open(tmp_path / 'k.pkl', 'wb') as f:
        pickle.dump({(0, 1): (600,)}, f)
    c = slayer_cache.SlayerCache(cache_key='k', disk=True)
    assert c.get(0, 1) is None
    assert c.data == {}


def test_torn_sidecar_write_leaves_no_stale_stamp(tmp_path, monkeypatch):
    # Red-team finding (2026-06-29): save() must REMOVE the old sidecar before
    # writing the new pkl. Otherwise a torn sidecar write leaves new-pkl +
    # OLD-vintage sidecar, and a later engine DOWNGRADE to that vintage serves
    # stale scores. Simulate the torn write and assert the pkl is left
    # stamp-less (a safe miss), never beside a surviving old stamp.
    import os as _os
    # 1. Complete save at engine A.
    _fresh(monkeypatch, tmp_path, eng='eng_A')
    a = slayer_cache.SlayerCache(cache_key='k', disk=True, scenario={})
    a.put(0, 0, [111])
    a.save()
    assert (tmp_path / 'k.json').exists()
    # 2. Save at engine B, but make the sidecar's final os.replace fail (torn).
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'eng_B')
    real_replace = _os.replace
    def flaky_replace(src, dst):
        if str(dst).endswith('.json'):
            raise OSError('simulated torn sidecar write')
        return real_replace(src, dst)
    monkeypatch.setattr(slayer_cache.os, 'replace', flaky_replace)
    b = slayer_cache.SlayerCache(cache_key='k', disk=True, scenario={})
    b.put(0, 0, [222])     # B-vintage score
    b.save()               # sidecar write fails, swallowed by best-effort
    monkeypatch.setattr(slayer_cache.os, 'replace', real_replace)
    # The OLD (engine_A) sidecar must be GONE — not surviving beside the B pkl.
    assert not (tmp_path / 'k.json').exists()
    # 3. Downgrade back to engine A: must MISS (no sidecar), never serve B data.
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'eng_A')
    c = slayer_cache.SlayerCache(cache_key='k', disk=True)
    assert c.get(0, 0) is None
    assert c.data == {}


def test_read_stamp_roundtrips(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    scen = {'species': 'X', 'charged': ['CLOSE_COMBAT']}
    c = slayer_cache.SlayerCache(cache_key='k', disk=True, scenario=scen)
    c.put(0, 0, [500])
    c.save()
    eng, gm, got = slayer_cache.read_stamp(tmp_path / 'k.json')
    assert (eng, gm) == ('eng_cur', 'gm_cur')
    assert got == scen
