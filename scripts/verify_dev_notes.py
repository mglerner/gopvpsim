#!/usr/bin/env python
"""Keep DEVELOPER_NOTES.md readable in one shot and its pointers resolvable.

DEVELOPER_NOTES.md is the session-startup read (CLAUDE.md). Two things rot
it: it grows past the size a single Read returns (2026-10-24: 2,034 lines /
118k chars against its own ~52k cap, found only when a session noticed it
had read half), and the cross-references between it and the rest of the
repo go stale (14 dangling ``DEVELOPER_NOTES "Section"`` citations the same
day, most of them months old). Both are mechanical, so both are gated here;
``.githooks/pre-commit`` runs this on every commit. Semantic rot -- prose
that no longer matches the code -- is NOT detectable here; the re-vetting
procedure (docs/rebalance_checklist.md section B) carries that review.

Checks (``run_checks`` returns ``(failures, warnings)``):

  size        ``len(DEVELOPER_NOTES.md)`` <= ``CHAR_CAP`` characters.
  sentinels   every ``<!-- sync:KEY -->`` key that verify_dev_counts.py
              knows appears exactly once, and none appears in CHANGELOG.md
              (build_guides.py parses the notes alone; a copy elsewhere is
              a second source of truth).
  inbound     every quoted citation ``DEVELOPER_NOTES "Section name"`` in
              the repo names a heading or a numbered bold item of the
              notes (case-insensitive substring). A miss in an ENGINE-HASH
              file (sweep_cache._ENGINE_FILES + deep_dive_signature.py) is
              a warning, because fixing a comment there bumps the sweep
              cache hash and must ride the next engine change; a miss in a
              point-in-time doc (docs/validations, docs/reviews,
              docs/TODO_archive.md) is a warning too.
  outbound    every quoted citation FROM the notes to CLAUDE.md, TODO.md
              or CHANGELOG.md names a phrase that exists there (CHANGELOG:
              a heading); every backticked repo path in the notes exists;
              every ``tests/x.py::name`` names a def/class in that file.

Usage::

    python scripts/verify_dev_notes.py            # report, exit 1 on failure
    python scripts/verify_dev_notes.py --quiet    # failures only

Pass ``--repo-root`` to point at another checkout (the tests use a
synthetic one).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The notes' own stated cap (see the HTML comment at its top): ~25k-token
# read limit at ~2.36 chars/token, with margin.
CHAR_CAP = 52_000

NOTES = 'DEVELOPER_NOTES.md'
CHANGELOG = 'CHANGELOG.md'

# Files whose bytes feed sweep_cache.engine_hash(); a comment edit there
# invalidates every cached column, so a dangling pointer only WARNS.
ENGINE_HASH_FILES = frozenset({
    'src/gopvpsim/battle.py', 'src/gopvpsim/_dp_jit.py',
    'src/gopvpsim/moves.py', 'src/gopvpsim/formchange.py',
    'src/gopvpsim/pokemon.py', 'scripts/deep_dive_signature.py',
})

# The checker and its tests quote the citation pattern itself.
SELF_FILES = ('scripts/verify_dev_notes.py', 'tests/test_verify_dev_notes.py')

# Point-in-time records: they cite the notes as they were when written.
HISTORICAL_PREFIXES = ('docs/validations/', 'docs/reviews/', 'docs/TODO_archive.md')

# Where inbound citations are looked for.
SCAN_DIRS = ('src', 'scripts', 'tests', 'docs', 'guides', 'articles',
             'thresholds', 'opponent_pools')
SCAN_FILES = ('CLAUDE.md', 'TODO.md', 'README.md')
SCAN_SUFFIXES = {'.py', '.md', '.js', '.toml', '.txt', '.sh', '.json', '.html'}

_SENTINEL_RE = re.compile(r'<!--\s*sync:([A-Za-z_][A-Za-z0-9_]*)\s*-->')
# A quoted citation of a doc section. The quoted span may cross a line
# break inside a Python comment or docstring, so it is normalised before
# matching (``#`` runs and whitespace collapsed).
_CITE_RE = re.compile(
    r'(DEVELOPER_NOTES|CLAUDE\.md|TODO(?:\.md)?|CHANGELOG(?:\.md)?)'
    r'(?:\.md)?\s*["\u201c]([^"\u201d]{3,140})["\u201d]')
_PATH_RE = re.compile(
    r'`((?:src|scripts|tests|docs|guides|articles|thresholds|opponent_pools|'
    r'userdata)/[\w./-]+?\.(?:py|md|js|toml|json|txt|sh|html|log)'
    r'(?:::[A-Za-z_]\w*)?)`')


def _norm(s: str) -> str:
    # Comment prefixes (``#``, ``//``) and backticks are not part of a name.
    s = s.replace('#', ' ').replace('//', ' ').replace('`', '')
    return re.sub(r'\s+', ' ', s).strip().lower()


def _anchors(notes_text: str) -> list[str]:
    """Headings and numbered bold items of the notes, normalised."""
    out = []
    for line in notes_text.splitlines():
        if line.startswith('#'):
            out.append(_norm(line.lstrip('#')))
        else:
            m = re.match(r'\*\*(\d+\.\s[^*]+)\*\*', line)
            if m:
                out.append(_norm(m.group(1)))
    return out


def _headings(text: str) -> list[str]:
    return [_norm(l.lstrip('#')) for l in text.splitlines() if l.startswith('#')]


def _resolves(quote: str, anchors: list[str]) -> bool:
    q = _norm(quote)
    return any(q in a for a in anchors)


def _iter_repo_files(root: Path):
    for name in SCAN_FILES:
        p = root / name
        if p.is_file():
            yield p
    for d in SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob('*')):
            if p.is_file() and p.suffix in SCAN_SUFFIXES:
                yield p


def _load_known_keys(root: Path) -> set[str]:
    """The sentinel keys verify_dev_counts.py checks (import, with fallback)."""
    script = root / 'scripts' / 'verify_dev_counts.py'
    if script.is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location('_vdc', script)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            return set(mod.ALL_KEYS)
        except Exception:  # pragma: no cover - a broken sibling script
            pass
    return set()


def run_checks(root: Path = REPO_ROOT) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    notes_path = root / NOTES
    if not notes_path.is_file():
        return [f'{NOTES} missing'], warnings
    notes = notes_path.read_text()

    # --- size ------------------------------------------------------------
    n = len(notes)
    if n > CHAR_CAP:
        failures.append(
            f'size: {NOTES} is {n:,} chars, cap {CHAR_CAP:,} '
            f'(over by {n - CHAR_CAP:,}). Trim, or move dated history to '
            f'{CHANGELOG}; see the note at the top of the file.')

    # --- sentinels -------------------------------------------------------
    counts: dict[str, int] = {}
    for m in _SENTINEL_RE.finditer(notes):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    for key in sorted(_load_known_keys(root)):
        c = counts.get(key, 0)
        if c != 1:
            failures.append(f'sentinels: sync:{key} appears {c}x in {NOTES} (want 1)')
    cl_path = root / CHANGELOG
    changelog = cl_path.read_text() if cl_path.is_file() else ''
    for m in _SENTINEL_RE.finditer(changelog):
        failures.append(f'sentinels: sync:{m.group(1)} leaked into {CHANGELOG}')

    # --- inbound citations -----------------------------------------------
    anchors = _anchors(notes)
    for p in _iter_repo_files(root):
        rel = p.relative_to(root).as_posix()
        if rel in (NOTES, CHANGELOG) or rel in SELF_FILES:
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for m in _CITE_RE.finditer(text):
            if m.group(1) != 'DEVELOPER_NOTES':
                continue
            quote = m.group(2)
            if _resolves(quote, anchors):
                continue
            line_no = text.count('\n', 0, m.start()) + 1
            msg = (f'inbound: {rel}:{line_no} cites DEVELOPER_NOTES '
                   f'"{_norm(quote)}" -- no such heading/item')
            if rel in ENGINE_HASH_FILES:
                warnings.append(msg + ' (engine-hash file: fix with the next engine bump)')
            elif rel.startswith(HISTORICAL_PREFIXES):
                warnings.append(msg + ' (point-in-time doc)')
            else:
                failures.append(msg)

    # --- outbound citations ----------------------------------------------
    targets = {
        'CLAUDE.md': (root / 'CLAUDE.md', False),
        'TODO': (root / 'TODO.md', False),
        'TODO.md': (root / 'TODO.md', False),
        'CHANGELOG': (cl_path, True),
        'CHANGELOG.md': (cl_path, True),
    }
    cache: dict[Path, str] = {}
    for m in _CITE_RE.finditer(notes):
        kind, quote = m.group(1), m.group(2)
        if kind == 'DEVELOPER_NOTES':
            continue
        path, headings_only = targets[kind]
        if path not in cache:
            cache[path] = path.read_text() if path.is_file() else ''
        hay = _headings(cache[path]) if headings_only else [_norm(cache[path])]
        if not _resolves(quote, hay):
            line_no = notes.count('\n', 0, m.start()) + 1
            failures.append(
                f'outbound: {NOTES}:{line_no} cites {kind} "{_norm(quote)}" '
                f'-- not found in {path.name}'
                + (' headings' if headings_only else ''))

    for m in _PATH_RE.finditer(notes):
        token = m.group(1)
        path_part, _, member = token.partition('::')
        target = root / path_part
        line_no = notes.count('\n', 0, m.start()) + 1
        if not target.exists():
            msg = f'outbound: {NOTES}:{line_no} names `{path_part}` which does not exist'
            # userdata/ is gitignored, machine-local evidence: warn only.
            (warnings if path_part.startswith('userdata/') else failures).append(msg)
            continue
        if member and target.suffix == '.py':
            src = target.read_text()
            if not re.search(rf'^\s*(?:def|class)\s+{re.escape(member)}\b', src, re.M):
                failures.append(
                    f'outbound: {NOTES}:{line_no} names `{token}` but '
                    f'{path_part} defines no `{member}`')

    return failures, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--quiet', action='store_true', help='failures only')
    ap.add_argument('--repo-root', type=Path, default=REPO_ROOT)
    args = ap.parse_args()

    failures, warnings = run_checks(args.repo_root)
    if warnings and not args.quiet:
        print('warnings (not blocking):')
        for w in warnings:
            print(f'  - {w}')
    if failures:
        print(f'\nERROR: {NOTES} checks failed:', file=sys.stderr)
        for f in failures:
            print(f'  - {f}', file=sys.stderr)
        return 1
    if not args.quiet:
        notes_len = len((args.repo_root / NOTES).read_text())
        print(f'{NOTES}: {notes_len:,}/{CHAR_CAP:,} chars; all pointers resolve.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
