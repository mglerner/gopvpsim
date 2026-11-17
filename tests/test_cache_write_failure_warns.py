"""A failed cache write must be LOUD, not silent (2026-11-17).

Before this, ``SweepCache.put_column`` and ``SlayerCache.save`` ended in a bare
``except Exception: pass``. Three dives run inside the Claude sandbox (Minior
10-24, Tinkaton 11-05 and 11-17) could not write ``~/.cache`` (EPERM) and
cached nothing, with no log line at all; it was found only by noticing that no
column was newer than 2026-09-28. Pre-fix value: zero WARNING records.

The writes stay best-effort (no raise), but the first failure per cache kind
in a process logs a WARNING and later ones drop to DEBUG, so an unwritable
cache says so once per run instead of once per column.
"""
import logging
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import slayer_cache  # noqa: E402
import sweep_cache  # noqa: E402


def _unwritable_dir(tmp_path):
    # A directory path whose parent is a regular file: mkdir always fails,
    # on any OS and as any user (a chmod-based setup would pass under root).
    blocker = tmp_path / 'not_a_dir'
    blocker.write_text('x')
    return blocker / 'cache'


def _warnings(caplog, kind):
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and kind in r.getMessage()]


def test_sweep_put_column_failure_warns_once(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', _unwritable_dir(tmp_path))
    monkeypatch.setattr(sweep_cache, '_WRITE_FAILURE_WARNED', set(), raising=False)
    caplog.set_level(logging.DEBUG, logger='deep_dive')
    cache = sweep_cache.SweepCache({'species': 'Azumarill', 'league': 'great'})
    planes = {'score': np.zeros((8, 2)), 'energy': np.zeros((8, 2))}
    cache.put_column({'opp': 'a'}, planes)   # must not raise
    cache.put_column({'opp': 'b'}, planes)
    warns = _warnings(caplog, 'sweep cache')
    assert len(warns) == 1, [r.getMessage() for r in caplog.records]
    assert 'NOT being cached' in warns[0].getMessage()
    # The second failure is still recorded, just quieter.
    assert any(r.levelno == logging.DEBUG and 'sweep cache' in r.getMessage()
               for r in caplog.records)


def test_slayer_save_failure_warns(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(slayer_cache, 'CACHE_DIR', _unwritable_dir(tmp_path))
    monkeypatch.setattr(sweep_cache, '_WRITE_FAILURE_WARNED', set(), raising=False)
    caplog.set_level(logging.DEBUG, logger='deep_dive')
    c = slayer_cache.SlayerCache(cache_key='unit_unwritable', disk=True)
    c.put(0, 1, [501])
    c.save()   # must not raise
    assert len(_warnings(caplog, 'slayer cache')) == 1


def test_successful_write_does_not_warn(tmp_path, monkeypatch, caplog):
    # Positive control: a writable cache logs nothing at WARNING, so the
    # assertions above are about the failure, not about put_column itself.
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(sweep_cache, '_WRITE_FAILURE_WARNED', set(), raising=False)
    caplog.set_level(logging.DEBUG, logger='deep_dive')
    cache = sweep_cache.SweepCache({'species': 'Azumarill', 'league': 'great'})
    cache.put_column({'opp': 'a'}, {'score': np.zeros((8, 2)),
                                    'energy': np.zeros((8, 2))})
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert cache.get_column({'opp': 'a'}, 8, 2) is not None
