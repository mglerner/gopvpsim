#!/usr/bin/env python
"""Trim `userdata/logs/` — per the structured-logger design doc §3.

Dry-run by default; pass ``--execute`` to actually delete or archive.
Examples:

    # Preview: anything older than 14 days
    python scripts/clean_logs.py --older-than 14d

    # Archive (don't delete) runs older than 60 days
    python scripts/clean_logs.py --older-than 60d --archive --execute

    # Keep only the 50 most-recent runs across all month subdirs
    python scripts/clean_logs.py --keep-last 50 --execute
"""
import argparse
import re
import shutil
import sys
import time
from pathlib import Path


def _default_log_root():
    here = Path(__file__).resolve().parent
    return here.parent / 'userdata' / 'logs'


def _parse_duration(s):
    """Accept ``30d``, ``12h``, ``90m`` — return seconds."""
    m = re.fullmatch(r'\s*(\d+)\s*([dhm])\s*', s or '')
    if not m:
        raise argparse.ArgumentTypeError(
            f'--older-than expects N<d|h|m> (e.g. 30d), got {s!r}')
    n = int(m.group(1))
    unit = m.group(2)
    return n * {'d': 86400, 'h': 3600, 'm': 60}[unit]


def _gather_log_files(root):
    """All ``*.log`` files under month subdirs, newest first."""
    if not root.is_dir():
        return []
    files = []
    for month_dir in root.iterdir():
        if not month_dir.is_dir() or month_dir.name == 'archive':
            continue
        for f in month_dir.glob('*.log'):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            files.append((f, mtime))
    files.sort(key=lambda x: x[1], reverse=True)
    return files


def _human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def _relative_month(logs_root, month_dir):
    try:
        return month_dir.relative_to(logs_root.parent)
    except ValueError:
        return month_dir


def _archive_path(logs_root, log_file):
    """Mirror the month subdir under ``<logs_root>/archive/``."""
    month_dir = log_file.parent
    return logs_root / 'archive' / month_dir.name / log_file.name


def _prune_empty_month_dirs(logs_root, dry_run):
    for month_dir in sorted(logs_root.iterdir()):
        if not month_dir.is_dir() or month_dir.name == 'archive':
            continue
        if any(month_dir.iterdir()):
            continue
        if dry_run:
            print(f'  [dry-run] would rmdir empty {month_dir}')
        else:
            month_dir.rmdir()
            print(f'  rmdir {month_dir}')


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--log-dir', default=None, metavar='DIR',
                        help='Logs root to sweep (default: userdata/logs/).')
    parser.add_argument('--older-than', default=None, metavar='Nd',
                        help='Target files with mtime older than N days '
                             '(suffix d/h/m).')
    parser.add_argument('--keep-last', default=None, type=int, metavar='N',
                        help='Alternative policy: keep the N most-recent log '
                             'files, target everything else.')
    parser.add_argument('--archive', action='store_true',
                        help='Instead of deleting, move matched files to '
                             '<log-dir>/archive/YYYY-MM/. Still gitignored.')
    parser.add_argument('--execute', action='store_true',
                        help='Apply the plan. Without this flag, all output '
                             'is preview-only.')
    args = parser.parse_args()

    if args.older_than is None and args.keep_last is None:
        parser.error('pass --older-than Nd and/or --keep-last N')

    older_than_seconds = None
    if args.older_than is not None:
        older_than_seconds = _parse_duration(args.older_than)

    logs_root = Path(args.log_dir) if args.log_dir else _default_log_root()
    if not logs_root.exists():
        print(f'  log root {logs_root} does not exist; nothing to do.')
        return 0

    files = _gather_log_files(logs_root)
    if not files:
        print(f'  no *.log files under {logs_root}')
        return 0

    now = time.time()
    targeted = []
    for path, mtime in files:
        hit_age = (older_than_seconds is not None
                   and (now - mtime) > older_than_seconds)
        # keep-last is applied below (positional — needs sorted list);
        # here we just record the per-file decision for --older-than.
        if hit_age:
            targeted.append(('age', path, mtime))

    if args.keep_last is not None:
        # Skip the N newest; add everything else.
        already_set = {p for (_, p, _) in targeted}
        for path, mtime in files[args.keep_last:]:
            if path not in already_set:
                targeted.append(('keep-last', path, mtime))

    if not targeted:
        print(f'  nothing to clean under {logs_root} '
              f'({len(files)} files total).')
        return 0

    total_bytes = 0
    for _, path, _ in targeted:
        try:
            total_bytes += path.stat().st_size
        except OSError:
            pass

    action = 'archive' if args.archive else 'delete'
    mode = 'PLAN' if not args.execute else 'EXECUTE'
    print(f'  [{mode}] {action} {len(targeted)} file(s), '
          f'{_human_size(total_bytes)} total, under {logs_root}')

    for reason, path, mtime in targeted:
        age_days = (now - mtime) / 86400
        rel = path.relative_to(logs_root.parent) if logs_root in path.parents else path
        tag = f'[{reason}, {age_days:.1f}d]'
        if args.execute:
            if args.archive:
                dest = _archive_path(logs_root, path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(dest))
                print(f'  archived {rel} {tag} -> '
                      f'{dest.relative_to(logs_root.parent)}')
            else:
                path.unlink()
                print(f'  deleted {rel} {tag}')
        else:
            if args.archive:
                dest = _archive_path(logs_root, path)
                print(f'  [dry-run] would archive {rel} {tag} -> '
                      f'{dest.relative_to(logs_root.parent)}')
            else:
                print(f'  [dry-run] would delete {rel} {tag}')

    _prune_empty_month_dirs(logs_root, dry_run=not args.execute)

    if not args.execute:
        print('  (dry run — re-run with --execute to apply)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
