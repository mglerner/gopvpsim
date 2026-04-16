"""Structured logger for the deep-dive pipeline.

See ``docs/structured_logger_design.md`` for the design rationale. The
public surface is small:

- ``init_logger(...)`` — parent-process setup. Attaches two stdout
  handlers (one timestamp-prefixed for INFO/WARNING, one plain for
  RESULT) and one FileHandler that captures everything. Returns the
  logger and the resolved log path.
- ``worker_log_setup(log_path, verbose)`` — called from inside each
  ``multiprocessing.Pool`` initializer so worker records land in the
  same file as the parent's. Spawn-mode workers (default on macOS) do
  not inherit the parent's handlers; an explicit re-attach is required.
- ``get_logger()`` — returns the shared ``deep_dive`` logger. Safe to
  call from any module; emits nothing until handlers are attached.
- ``RESULT`` — custom level (25, between INFO and WARNING) used for the
  Top-N table and the ``=``-banner, which need to render on stdout
  without a timestamp prefix.
"""
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

LOGGER_NAME = 'deep_dive'

RESULT = 25
logging.addLevelName(RESULT, 'RESULT')


def _result(self, msg, *args, **kwargs):
    if self.isEnabledFor(RESULT):
        self._log(RESULT, msg, args, **kwargs)


if not hasattr(logging.Logger, 'result'):
    logging.Logger.result = _result


_FILE_FMT = '[%(asctime)s.%(msecs)03d] %(levelname)-7s %(name)s: %(message)s'
_FILE_DATEFMT = '%Y-%m-%d %H:%M:%S'


class _StdoutFormatter(logging.Formatter):
    """Short HH:MM:SS prefix, WARNING tag, no level-for-INFO."""

    def format(self, record):
        ts = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        msg = record.getMessage()
        if record.levelno == logging.WARNING:
            return f'[{ts}] WARNING: {msg}'
        return f'[{ts}] {msg}'


class _ExcludeLevelFilter(logging.Filter):
    def __init__(self, level):
        super().__init__()
        self._level = level

    def filter(self, record):
        return record.levelno != self._level


class _OnlyLevelFilter(logging.Filter):
    def __init__(self, level):
        super().__init__()
        self._level = level

    def filter(self, record):
        return record.levelno == self._level


def _file_formatter():
    return logging.Formatter(fmt=_FILE_FMT, datefmt=_FILE_DATEFMT)


def _sanitize(s):
    """Lower-case, whitespace/punctuation to underscores, collapsed."""
    s = (s or '').lower().replace(' ', '_')
    s = re.sub(r'[^a-z0-9_-]+', '_', s)
    return s.strip('_') or 'run'


def _default_log_root():
    here = Path(__file__).resolve().parent  # scripts/
    return here.parent / 'userdata' / 'logs'


def _resolve_log_path(species, league, shadow, log_file, log_dir):
    """Return the Path this run writes to, or None to disable the file handler."""
    if log_file is not None:
        if log_file in ('/dev/null', os.devnull):
            return None
        return Path(log_file)
    base = Path(log_dir) if log_dir else _default_log_root()
    now = datetime.now()
    month_dir = base / now.strftime('%Y-%m')
    parts = [
        now.strftime('%Y%m%d_%H%M%S'),
        _sanitize(species),
        _sanitize(league),
    ]
    if shadow:
        parts.append('shadow')
    return month_dir / ('_'.join(parts) + '.log')


def _refresh_latest_symlink(log_path):
    """Atomically point ``<logs_root>/latest.log`` at ``log_path``.

    Only fires when ``log_path`` lives under a directory whose parent is
    named ``logs`` (i.e. it followed the monthly-subdir convention). A
    custom ``--log-file`` outside that tree does not update the symlink.
    """
    log_path = Path(log_path)
    if log_path.parent.parent.name != 'logs':
        return
    logs_root = log_path.parent.parent
    latest = logs_root / 'latest.log'
    tmp = logs_root / 'latest.log.new'
    try:
        target = log_path.relative_to(logs_root)
    except ValueError:
        return
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(str(target), str(tmp))
    os.replace(str(tmp), str(latest))


def init_logger(species, league, shadow=False, *,
                verbose=False, quiet=False,
                log_file=None, log_dir=None):
    """Configure the ``deep_dive`` logger in the parent process.

    Returns ``(logger, log_path)``. ``log_path`` is the Path receiving
    records, or ``None`` when the file handler is suppressed (e.g.
    ``--log-file /dev/null``).
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.propagate = False

    std_handler = logging.StreamHandler(sys.stdout)
    std_handler.setLevel(logging.WARNING if quiet else logging.INFO)
    std_handler.addFilter(_ExcludeLevelFilter(RESULT))
    std_handler.setFormatter(_StdoutFormatter())
    logger.addHandler(std_handler)

    result_handler = logging.StreamHandler(sys.stdout)
    result_handler.setLevel(RESULT)
    result_handler.addFilter(_OnlyLevelFilter(RESULT))
    result_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(result_handler)

    log_path = _resolve_log_path(species, league, shadow, log_file, log_dir)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), mode='a',
                                           encoding='utf-8')
        file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        file_handler.setFormatter(_file_formatter())
        logger.addHandler(file_handler)
        _refresh_latest_symlink(log_path)

    return logger, log_path


def worker_log_setup(log_path, verbose=False):
    """Re-open the FileHandler inside a ``multiprocessing`` worker.

    POSIX ``write()`` calls under ``PIPE_BUF`` (4 KiB) are atomic when
    opened in append mode, which is comfortably more than any log record
    we emit — concurrent workers can share the same file without extra
    locking.
    """
    if log_path is None:
        return
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.propagate = False
    fh = logging.FileHandler(str(log_path), mode='a', encoding='utf-8')
    fh.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh.setFormatter(_file_formatter())
    logger.addHandler(fh)


def get_logger():
    return logging.getLogger(LOGGER_NAME)
