"""Tests for the rankings-cache reproducibility fingerprint + run-start log.

`rankings_fingerprint` is a pure read-only helper that captures the
drift-sensitive identity of a league's PvPoke rankings cache (path, mtime,
sha256 content hash, count, top-5). `log_run_start_fingerprint` emits that
fingerprint as a run-start log line; main() calls it on the
top-N-rankings resolution path so a dive's log alone pins the rankings
vintage it ran against.

The caplog test asserts the LOG LINE actually fires (the wiring), not just
that the pure helper returns a dict; a source assertion confirms main's
resolution path calls the emitter.
"""
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)

_FAKE_FP = {
    'cache_path': Path("/tmp/great.json"),
    'mtime': None,
    'mtime_str': '2026-06-28 12:00:00',
    'content_hash': 'abcdef0123456789' * 4,
    'count': 812,
    'top5': ['Azumarill', 'Medicham', 'Registeel', 'Lanturn', 'Swampert'],
}


def test_fingerprint_has_content_hash():
    """The pure helper returns a sha256 content hash over the cache bytes."""
    fp = deep_dive.rankings_fingerprint('great')
    if fp is None:
        pytest.skip("rankings cache not present on this machine")
    assert len(fp['content_hash']) == 64
    int(fp['content_hash'], 16)  # hex-decodable
    assert fp['count'] > 0
    assert len(fp['top5']) == 5


def test_run_start_log_line_fires(caplog, monkeypatch):
    """The run-start emitter logs an INFO line carrying the fingerprint.

    Monkeypatch the pure helper so the assertion is independent of whatever
    rankings vintage happens to be on disk; this exercises the log wiring
    (fingerprint -> logger.info), not just the helper's return value.
    """
    monkeypatch.setattr(deep_dive, 'rankings_fingerprint', lambda league: _FAKE_FP)
    with caplog.at_level(logging.INFO, logger=deep_dive.logger.name):
        fp = deep_dive.log_run_start_fingerprint('great')
    assert fp is _FAKE_FP
    line = '\n'.join(r.getMessage() for r in caplog.records)
    assert 'rankings cache:' in line
    assert 'great.json' in line
    assert _FAKE_FP['content_hash'][:12] in line
    assert 'Azumarill' in line


def test_run_start_log_skips_when_cache_absent(caplog, monkeypatch):
    """No log line (and no crash) when the cache file is missing."""
    monkeypatch.setattr(deep_dive, 'rankings_fingerprint', lambda league: None)
    with caplog.at_level(logging.INFO, logger=deep_dive.logger.name):
        fp = deep_dive.log_run_start_fingerprint('great')
    assert fp is None
    assert 'rankings cache:' not in '\n'.join(r.getMessage() for r in caplog.records)


def test_emitter_wired_into_resolution_path():
    """main()'s top-N-rankings resolution path calls the run-start emitter.

    Guards against the emitter being defined but never wired in: the log
    line must sit next to the get_top_opponents() resolution call.
    """
    src = DEEP_DIVE_PATH.read_text()
    assert 'log_run_start_fingerprint(args.league)' in src
    # The call precedes the opponent resolution it fingerprints.
    call_idx = src.index('log_run_start_fingerprint(args.league)')
    resolve_idx = src.index('opponents = get_top_opponents(args.league, args.opponents)')
    assert call_idx < resolve_idx
