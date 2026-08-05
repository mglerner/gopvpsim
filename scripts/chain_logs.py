"""Single source for picking "the newest overnight chain log".

Three tools need it (verify_overnight, overnight_eta, chain_status)
and each once had its own rule -- path sort, filename-stamp sort, and
mtime. The stamp rule is the correct one: the monthly subdir is
unreliable (overnight_redive.sh hardcoded 2026-04 until 2026-08-04, so
July logs are filed under 2026-04/ on disk), which makes a path sort
order runs wrong across month dirs, and mtime lies after any copy or
touch. Sort by the YYYYMMDD_HHMMSS stamp in the filename, which the
chain writes exactly once at launch. (DRY review 2026-08-05 entry 3c.)
"""
import re
from pathlib import Path

_STAMP_RE = re.compile(r'overnight_(\d{8}_\d{6})')


def run_stamp(path) -> str:
    """Sortable YYYYMMDD_HHMMSS from an overnight_*.log name ('' if none)."""
    m = _STAMP_RE.search(Path(path).name)
    return m.group(1) if m else ''


def newest_chain_log(logs_dir) -> Path | None:
    """Newest overnight_*.log under logs_dir/*/, by filename stamp."""
    logs = sorted(Path(logs_dir).glob('*/overnight_*.log'), key=run_stamp)
    return logs[-1] if logs else None
