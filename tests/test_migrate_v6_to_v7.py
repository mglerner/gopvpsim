"""Tests for scripts/migrate_v6_to_v7.py — the one-shot v6->v7 sweep-cache
re-key (cache-rework v7, 2026-06-29).

Pins the adversarial-review safety properties: COPY (source intact),
idempotent/resumable (skip existing v7 target), correct re-key (target dir
== a live v7 dive's dir), and per-column gamemaster stamp = narrowed old hash.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sweep_cache = sys.modules.get("sweep_cache") or _load("sweep_cache")
mig = sys.modules.get("migrate_v6_to_v7") or _load("migrate_v6_to_v7")

# A tiny gamemaster blob; its full + narrowed hashes are computed, not pinned.
OLD_GM = {'timestamp': 't', 'cups': [1],
          'pokemon': [{'speciesId': 'azumarill', 'speciesName': 'Azumarill',
                       'baseStats': {'atk': 1, 'def': 1, 'hp': 1}}],
          'moves': [{'moveId': 'BUBBLE', 'power': 7}]}


def _write_v6_dir(cache_dir, full_hash, engine='eng_old'):
    """Write a v6 focal dir (gamemaster in the focal key/meta) with one column,
    via the v6-shaped meta + sidecar by hand."""
    meta = {'v': 6, 'species': 'Azumarill', 'league': 'great', 'shadow': False,
            'fast': 'BUBBLE', 'charged': ['ICE_BEAM'], 'iv_floor': None,
            'scenarios': [[0, 0], [1, 1]], 'bait': 'bait', 'energy_lead': 0,
            'focal_max_level': None, 'gamemaster': full_hash}
    # v6 dir name used the v6 key (with gamemaster); the exact name doesn't
    # matter for the test, only that meta drives the re-key target.
    d = cache_dir / f'Azumarill_great_{full_hash}'
    d.mkdir(parents=True)
    (d / 'meta.json').write_text(json.dumps(meta))
    col = {'species': 'Medicham', 'shadow': False, 'ivs': [0, 15, 15],
           'level': 23.5, 'fast': 'COUNTER', 'charged': ['PSYCHIC']}
    np.savez(open(d / 'col0.npz', 'wb'), score=np.arange(4.0).reshape(2, 2))
    (d / 'col0.json').write_text(json.dumps(
        {'engine': engine, 'gamemaster': None, 'col': col}))
    return d, meta


def test_rekey_copies_and_targets_live_v7_dir(tmp_path):
    full = mig._full_hash(OLD_GM)
    narrow = mig._narrow_hash(OLD_GM)
    src, meta = _write_v6_dir(tmp_path, full)

    mig.migrate(tmp_path, _gm_file(tmp_path), full, apply=True)

    # Source left intact (COPY, not move).
    assert src.exists() and (src / 'col0.npz').exists()

    # Target dir name == the dir a live v7 dive computes (same focal hash;
    # SweepCache uses the real CACHE_DIR, so compare names not full paths).
    target, _ = mig._v7_dir_for(tmp_path, meta)
    live = sweep_cache.SweepCache(_v7_focal(meta)).dir
    assert target.name == live.name and target.exists()

    # Column copied; sidecar re-stamped: gamemaster=narrowed-old, engine kept.
    side = json.loads((target / 'col0.json').read_text())
    assert side['gamemaster'] == narrow
    assert side['engine'] == 'eng_old'
    assert side['col']['species'] == 'Medicham'
    got = np.load(target / 'col0.npz')['score']
    assert np.array_equal(got, np.arange(4.0).reshape(2, 2))
    # New meta is v7 with no gamemaster.
    m7 = json.loads((target / 'meta.json').read_text())
    assert m7['v'] == sweep_cache.CACHE_VERSION and 'gamemaster' not in m7


def test_idempotent_skips_existing_target(tmp_path):
    full = mig._full_hash(OLD_GM)
    _write_v6_dir(tmp_path, full)
    mig.migrate(tmp_path, _gm_file(tmp_path), full, apply=True)
    target_count = sum(1 for d in tmp_path.iterdir()
                       if d.is_dir() and not d.name.startswith('.'))
    # A second run must not duplicate or clobber — target exists -> skipped.
    mig.migrate(tmp_path, _gm_file(tmp_path), full, apply=True)
    assert sum(1 for d in tmp_path.iterdir()
               if d.is_dir() and not d.name.startswith('.')) == target_count


def test_skips_other_gamemaster_vintage(tmp_path):
    full = mig._full_hash(OLD_GM)
    _write_v6_dir(tmp_path, full)
    other, _ = _write_v6_dir(tmp_path, 'other_full_hash')
    mig.migrate(tmp_path, _gm_file(tmp_path), full, apply=True)
    # The other-vintage v6 dir is untouched (still v6, still present).
    assert other.exists()
    assert json.loads((other / 'meta.json').read_text())['v'] == 6


# ---- helpers ----

def _gm_file(tmp_path):
    p = tmp_path / 'old_gm.json'
    p.write_text(json.dumps(OLD_GM))
    return str(p)


def _v7_focal(meta):
    return sweep_cache.focal_key_fields(
        species=meta['species'], league=meta['league'], shadow=meta['shadow'],
        fast_id=meta['fast'], charged_ids=meta['charged'],
        iv_floor=meta.get('iv_floor'),
        shield_scenarios=[tuple(s) for s in meta['scenarios']],
        bait_mode=meta['bait'], energy_lead=meta.get('energy_lead', 0),
        focal_max_level=meta.get('focal_max_level'))
