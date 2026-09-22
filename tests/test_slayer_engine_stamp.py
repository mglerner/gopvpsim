"""The slayer cache's engine stamp must see the slayer worker.

Gap found 2026-09-20, closed 2026-09-22. ``slayer_cache``'s engine stamp was
``sweep_cache.engine_hash()`` verbatim, which hashes the five ``gopvpsim/``
engine files plus ``scripts/deep_dive_signature.py``. It does NOT hash
``scripts/deep_dive_slayer.py`` -- the worker that builds every mirror pair
and drives every ``simulate()`` call behind a slayer column.

Pre-fix value: ``slayer_cache._current_stamps()[0] == sweep_cache.engine_hash()``
exactly, so editing the slayer worker's sim logic left the stamp identical and
the cache kept serving pre-edit columns. That is a wrong-answer hazard, not a
stale-cache one: a stale stamp is a safe miss, an UNCHANGED stamp over changed
behaviour is a silent wrong serve.

The fix is a separate ``slayer_cache.slayer_engine_hash()``. The SWEEP stamp
must not move -- ~153,000 sweep columns carry it, and the sweep never reads
the slayer worker.
"""
import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

import slayer_cache  # noqa: E402
import sweep_cache  # noqa: E402

WORKER = REPO / 'scripts' / 'deep_dive_slayer.py'


def _fresh_stamps():
    """Both stamps with the per-process memos cleared."""
    sweep_cache._ENGINE_HASH = None
    slayer_cache._SLAYER_ENGINE_HASH = None
    return sweep_cache.engine_hash(), slayer_cache.slayer_engine_hash()


@pytest.fixture
def worker_bytes_restored():
    """Restore scripts/deep_dive_slayer.py byte-for-byte, whatever happens.

    This test edits a real repo source file, because the contract under test
    is literally "the stamp responds to that file's content on disk" and a
    monkeypatched path would prove only that the helper composes two strings.
    """
    original = WORKER.read_bytes()
    try:
        yield original
    finally:
        WORKER.write_bytes(original)
        assert WORKER.read_bytes() == original, (
            'FAILED TO RESTORE scripts/deep_dive_slayer.py -- check git diff')
        _fresh_stamps()


def test_the_slayer_stamp_moves_with_the_worker_and_the_sweep_stamp_does_not(
        worker_bytes_restored):
    """The whole fix, end to end, against the real file.

    Pre-fix both assertions failed the same way: the slayer stamp WAS the
    sweep stamp, so neither moved when the worker changed.
    """
    original = worker_bytes_restored
    sweep_before, slayer_before = _fresh_stamps()

    WORKER.write_bytes(original + b'\n# stamp-sensitivity probe\n')
    sweep_after, slayer_after = _fresh_stamps()

    assert slayer_after != slayer_before, (
        'editing scripts/deep_dive_slayer.py did not move the slayer engine '
        'stamp -- a change to the slayer worker is invisible to the slayer '
        'cache, which will serve pre-edit mirror columns')
    assert sweep_after == sweep_before, (
        'editing scripts/deep_dive_slayer.py moved the SWEEP engine stamp; '
        'that stales ~153,000 sweep columns for a file the sweep never reads')


def test_the_two_stamps_are_not_the_same_value(worker_bytes_restored):
    """Pre-fix they were identical. Distinctness is the fix's visible shape.

    Also a guard against a future "simplification" that routes the slayer
    stamp back through sweep_cache.engine_hash().
    """
    sweep_stamp, slayer_stamp = _fresh_stamps()
    assert slayer_stamp != sweep_stamp, (
        'the slayer stamp equals the sweep stamp; it did until 2026-09-22 '
        'and that is exactly the bug')
    assert len(slayer_stamp) == len(sweep_stamp) == 12


def test_the_worker_is_not_in_the_sweep_engine_file_set():
    """The structural half: the sweep cache must not grow a scripts/ input.

    sweep_cache hashes gopvpsim/ files by name plus one explicit extra
    (deep_dive_signature.py, which does change sweep scores). The slayer
    worker must stay out of both.
    """
    assert 'deep_dive_slayer.py' not in sweep_cache._ENGINE_FILES
    src = (REPO / 'scripts' / 'sweep_cache.py').read_text()
    fn_start = src.index('def engine_hash(')
    fn_end = src.index('\ndef ', fn_start + 1)
    assert 'deep_dive_slayer' not in src[fn_start:fn_end], (
        'sweep_cache.engine_hash() now reads the slayer worker; that moves '
        'the sweep stamp and stales every cached sweep column')
    # Positive control: the scan reaches real body text, so it cannot pass
    # because the slice came out empty.
    assert 'deep_dive_signature' in src[fn_start:fn_end]


def test_the_slayer_cache_stamps_its_sidecars_with_the_slayer_hash():
    """The consumer, not just the helper.

    _current_stamps() is what load() compares against and save() writes, so a
    correct slayer_engine_hash() that nothing calls would be a no-op fix.
    """
    _fresh_stamps()
    engine, gamemaster = slayer_cache._current_stamps()
    assert engine == slayer_cache.slayer_engine_hash()
    assert engine != sweep_cache.engine_hash()
    assert gamemaster == sweep_cache.gamemaster_hash(), (
        'the slayer gamemaster stamp is deliberately shared with the sweep '
        'cache; only the engine half forks')


def test_migrate_cache_targets_the_slayer_stamp_for_slayer_migrations():
    """migrate_cache must bless slayer sidecars with the stamp they are read
    against, or every "warm" column becomes a guaranteed miss."""
    mc = importlib.import_module('migrate_cache')
    src = Path(mc.__file__).read_text()
    for fn in ('migrate_slayer_engine', 'migrate_slayer_gamemaster'):
        start = src.index(f'def {fn}(')
        end = src.index('\ndef ', start + 1)
        body = src[start:end]
        assert 'slayer_cache.slayer_engine_hash()' in body, (
            f'{fn} does not use the slayer engine stamp')
    # Positive control on the slice: both bodies really were read.
    assert 'def migrate_slayer_engine(' in src
