"""Behavioral tests for scripts/deep_dive_logging.py.

195 LOC, imported by 9 modules including both dive entry points, and until
now zero direct tests.  The failure mode is silent by construction:
``worker_log_setup`` returns early on ``log_path is None`` (:181-182), and a
worker whose logger has no handlers simply DROPS its INFO records -- Python's
lastResort only surfaces WARNING and above.  Nothing fails; a multi-hour
overnight dive just loses its worker-side record.  2026-08-09 test-suite
review, blind-spots E6.

Two live call sites thread ``log_path`` into the pool initializer by hand
(scripts/deep_dive_lib/sweep.py:410, scripts/deep_dive_slayer.py:137), so the
spawn-delivery test below runs a REAL ``Pool(2)`` rather than asserting on
handler bookkeeping -- spawn children do not inherit the parent's handlers,
which is the entire reason ``worker_log_setup`` exists.
"""
import logging
import multiprocessing
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import deep_dive_logging as ddl  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_deep_dive_logger():
    """Snapshot/restore the PROCESS-GLOBAL ``deep_dive`` logger.

    ``init_logger`` and ``worker_log_setup`` both call
    ``logging.getLogger('deep_dive')`` and strip every existing handler
    (:144-145, :185-186).  Without this fixture each test in this file would
    leave a FileHandler pointed at a deleted ``tmp_path`` attached for the
    rest of the session -- which breaks unrelated tests only under a
    different collection order, i.e. the worst possible way to find out.
    """
    logger = logging.getLogger(ddl.LOGGER_NAME)
    saved = (list(logger.handlers), logger.level, logger.propagate)
    try:
        yield logger
    finally:
        for h in list(logger.handlers):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
        logger.handlers, logger.level, logger.propagate = (
            list(saved[0]), saved[1], saved[2])


def _file_handlers(logger):
    return [h for h in logger.handlers if isinstance(h, logging.FileHandler)]


# ---------------------------------------------------------------------------
# init_logger: file handler, /dev/null suppression
# ---------------------------------------------------------------------------

def test_init_logger_writes_records_to_the_resolved_file(tmp_path):
    logger, log_path = ddl.init_logger('Bastiodon', 'great',
                                       log_dir=tmp_path / 'logs', quiet=True)
    assert log_path is not None
    logger.info('hello from the parent')
    logger.result('a result line')
    for h in _file_handlers(logger):
        h.flush()
    text = Path(log_path).read_text()
    assert 'hello from the parent' in text
    assert 'a result line' in text


def test_init_logger_suppresses_the_file_handler_for_dev_null(tmp_path):
    """``--log-file /dev/null`` must mean NO file handler, not a handler on
    /dev/null: the dive fixtures rely on it to stay side-effect free."""
    logger, log_path = ddl.init_logger('Bastiodon', 'great',
                                       log_file='/dev/null', quiet=True)
    assert log_path is None
    assert _file_handlers(logger) == []
    # ...but stdout handlers are still attached, so the run is not silent.
    assert len(logger.handlers) == 2


def test_init_logger_debug_records_reach_the_file_only_when_verbose(tmp_path):
    logger, log_path = ddl.init_logger('Bastiodon', 'great', quiet=True,
                                       log_file=str(tmp_path / 'quiet.log'))
    logger.debug('invisible-marker')
    for h in _file_handlers(logger):
        h.flush()
    assert 'invisible-marker' not in Path(log_path).read_text()

    logger, log_path = ddl.init_logger('Bastiodon', 'great', quiet=True,
                                       verbose=True,
                                       log_file=str(tmp_path / 'verbose.log'))
    logger.debug('visible-marker')
    for h in _file_handlers(logger):
        h.flush()
    assert 'visible-marker' in Path(log_path).read_text()


# ---------------------------------------------------------------------------
# latest.log symlink
# ---------------------------------------------------------------------------

def test_latest_symlink_points_at_the_new_run(tmp_path):
    logs_root = tmp_path / 'logs'
    _logger, log_path = ddl.init_logger('Bastiodon', 'great',
                                        log_dir=logs_root, quiet=True)
    latest = logs_root / 'latest.log'
    assert latest.is_symlink()
    # Stored RELATIVE to the logs root, so the tree stays relocatable.
    assert not os.path.isabs(os.readlink(latest))
    assert latest.resolve() == Path(log_path).resolve()
    # The staging file must not survive the atomic replace.
    assert not (logs_root / 'latest.log.new').exists()


def test_latest_symlink_is_a_noop_for_a_log_file_outside_the_logs_tree(tmp_path):
    """A custom ``--log-file`` must not repoint the shared latest.log."""
    outside = tmp_path / 'somewhere' / 'custom.log'
    outside.parent.mkdir(parents=True)
    outside.write_text('')
    ddl._refresh_latest_symlink(outside)
    # Nothing may appear beside the log file, nor one level up (where a
    # guard-less version would drop `<tmp_path>/latest.log`). is_symlink()
    # rather than exists(), which is False for a dangling link.
    assert [p.name for p in outside.parent.iterdir()] == ['custom.log']
    assert not (tmp_path / 'latest.log').is_symlink()
    assert not (tmp_path / 'latest.log').exists()


def test_latest_symlink_replaces_a_previous_one(tmp_path):
    logs_root = tmp_path / 'logs'
    first = logs_root / '2026-01' / 'a.log'
    second = logs_root / '2026-02' / 'b.log'
    for p in (first, second):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('')
    ddl._refresh_latest_symlink(first)
    ddl._refresh_latest_symlink(second)
    assert (logs_root / 'latest.log').resolve() == second.resolve()


# ---------------------------------------------------------------------------
# worker_log_setup, through a REAL spawn pool
# ---------------------------------------------------------------------------

def _worker_emit(marker):
    """Module scope so a spawn child can resolve it by qualified name."""
    from deep_dive_logging import get_logger
    get_logger().info(marker)
    return (marker, os.getpid())


def test_spawn_workers_deliver_their_records_to_the_parents_log_file(tmp_path):
    log_path = tmp_path / 'workers.log'
    log_path.write_text('')
    markers = [f'worker-record-{i}' for i in range(4)]

    ctx = multiprocessing.get_context('spawn')
    with ctx.Pool(2, initializer=ddl.worker_log_setup,
                  initargs=(str(log_path), False)) as pool:
        returned = pool.map(_worker_emit, markers)

    assert [m for m, _pid in returned] == markers
    # Anti-vacuity: the records must have crossed a process boundary. If this
    # ever ran in-process the parent's own handlers would carry them and the
    # test would say nothing about worker_log_setup.
    assert os.getpid() not in {pid for _m, pid in returned}

    text = log_path.read_text()
    missing = [m for m in markers if m not in text]
    assert not missing, (
        f'{len(missing)} of {len(markers)} worker records never reached '
        f'{log_path}: {missing}\nfile contents:\n{text}')


def test_worker_log_setup_is_a_noop_when_there_is_no_log_path():
    """The ``/dev/null`` dive path passes ``log_path=None`` to every worker.

    It must leave the logger alone rather than raising -- and, because the
    early return means the worker has NO handlers, this is also the exact
    configuration in which worker INFO records are silently dropped. Pinned
    so that behavior is at least a decision on the record.
    """
    logger = logging.getLogger(ddl.LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    ddl.worker_log_setup(None)
    assert logger.handlers == []


def test_worker_log_setup_replaces_handlers_rather_than_stacking_them(tmp_path):
    """Re-running setup must not duplicate every record."""
    log_path = tmp_path / 'dup.log'
    ddl.worker_log_setup(str(log_path))
    ddl.worker_log_setup(str(log_path))
    logger = logging.getLogger(ddl.LOGGER_NAME)
    assert len(_file_handlers(logger)) == 1
    logger.info('once-only')
    for h in _file_handlers(logger):
        h.flush()
    assert log_path.read_text().count('once-only') == 1
