#!/usr/bin/env python
"""Keep DEVELOPER_NOTES.md readable in one shot and its pointers resolvable.

DEVELOPER_NOTES.md is the session-startup read (CLAUDE.md). Two things rot
it: it grows past the size a single Read returns (2026-10-24: 2,034 lines /
118k chars against its own ~52k cap, found only when a session noticed it
had read half), and the cross-references between it and the rest of the
repo go stale (about a dozen dangling DEVELOPER_NOTES pointers the same
day -- quoted, unquoted and line-range -- several broken by the trim
itself). The mechanical part is gated here; ``.githooks/pre-commit`` runs
this on every commit against an export of the INDEX, so the result is
about what is being committed, not the working tree. Semantic rot -- prose
that no longer matches the code -- is NOT detectable here; the re-vetting
procedure (docs/rebalance_checklist.md section B) carries that review.

Checks (``run_checks`` returns ``(failures, warnings)``):

  size        ``len(DEVELOPER_NOTES.md)`` <= ``CHAR_CAP`` characters (code
              points; the file must decode as UTF-8, non-ASCII only warns).
  sentinels   every ``<!-- sync:KEY -->`` key that verify_dev_counts.py
              knows appears exactly once, and none appears in CHANGELOG.md
              (build_guides.py parses the notes alone; a copy elsewhere is
              a second source of truth). A missing/unimportable/empty key
              set is itself a failure, never a silent pass.
  inbound     every quoted citation ``DEVELOPER_NOTES "Section name"`` (also
              ``'...'``, curly double quotes, a backticked file name,
              ``DEVELOPER_NOTES.md section "..."``, ``DEVELOPER_NOTES's
              "..."``, a comment-prefixed line wrap before the quote) in a
              scanned file names a heading or a ``**N. ...**`` item of the
              notes, matched case-insensitive on word boundaries. A miss in
              an ENGINE-HASH file (sweep_cache._ENGINE_FILES +
              deep_dive_signature.py) is a warning, because fixing a comment
              there bumps the sweep cache hash and must ride the next engine
              change; a miss in a point-in-time doc (docs/validations,
              docs/reviews, docs/TODO_archive.md) is a warning too.
  outbound    every quoted citation FROM the notes to CLAUDE.md, TODO.md or
              CHANGELOG.md names a phrase that exists there (CHANGELOG: a
              heading), and every quoted citation of the notes' OWN sections
              resolves; every backticked repo path in the notes exists
              (``path.py:LINE`` and trailing CLI args tolerated; ``userdata/``
              misses only warn, it is gitignored); every ``tests/x.py::name``
              (``::Class::method``, ``[case]`` too) names a def / async def /
              class / module-or-class-level assignment at that position,
              resolved with ``ast``.

NOT checked (so do not read a green run as "every pointer resolves"):
unquoted prose references ("the re-dive entry"), ``file:line`` numbers in
either direction, bare basenames (``battle.py``), directories (``docs/x/``),
identifiers, commit SHAs, item numbers written outside the quotes, a second
quoted item in the same sentence, curly SINGLE quotes, a single-quoted name
containing an apostrophe (skipped, not mis-resolved), and files outside
SCAN_DIRS/SCAN_FILES.

Usage::

    python scripts/verify_dev_notes.py            # report; exit 2 on failure
    python scripts/verify_dev_notes.py --quiet    # failures only
    python scripts/verify_dev_notes.py --print-scan-paths   # for the hook

Exit codes: 0 clean, 2 failures; anything else is a crash (the hook tells
them apart). Run by hand it scans the working tree, untracked files
included. Pass ``--repo-root`` to point at another checkout (the hook passes
an index export built from ``--print-scan-paths``; the tests a synthetic
repo).
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ~25k-token single-Read limit at ~2.36 chars/token, with margin. The
# notes' preamble states the same number; change both together.
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
SELF_FILES = ('scripts/verify_dev_notes.py', 'tests/test_verify_dev_notes.py',
              'tests/test_precommit_hook.py')

# Point-in-time records: they cite the notes as they were when written.
HISTORICAL_PREFIXES = ('docs/validations/', 'docs/reviews/', 'docs/TODO_archive.md')

# Where inbound citations are looked for. The hook exports exactly these
# (plus the notes and CHANGELOG) from the index via --print-scan-paths.
SCAN_DIRS = ('src', 'scripts', 'tests', 'docs', 'guides', 'articles',
             'thresholds', 'opponent_pools')
SCAN_FILES = ('CLAUDE.md', 'TODO.md', 'README.md')
SCAN_SUFFIXES = {'.py', '.md', '.js', '.toml', '.txt', '.sh', '.json', '.html'}

_SENTINEL_RE = re.compile(r'<!--\s*sync:([A-Za-z_][A-Za-z0-9_]*)\s*-->')
# A quoted citation of a doc section: ``DOC "name"``, ``DOC 'name'``,
# ```DOC.md` "name"``, ``DOC.md section "name"``, ``DOC's "name"``, curly
# double quotes, and a comment-prefixed line wrap between name and quote.
# The quoted span may cross a line break inside a comment or docstring, so
# it is normalised before matching (comment prefixes and whitespace
# collapsed). Guards: the name must not be preceded by a word char, a quote
# or a slash (so the string literal "DEVELOPER_NOTES.md" and a path are not
# citations); a single-quoted name must follow whitespace and its closing
# quote must not be followed by a word char (so 'DEVELOPER_NOTES.md' and
# an apostrophe inside the name do not open or truncate one).
_CITE_RE = re.compile(
    r'(?<![\w"\'/])`?(DEVELOPER_NOTES|CLAUDE\.md|TODO(?:\.md)?|CHANGELOG(?:\.md)?)'
    r"(?:\.md)?`?(?:'s)?,?\s*(?:(?:#+|//)\s*)?(?:section\s+)?"
    r'(?:"([^"]{3,140})"|(?<=\s)\'([^\']{3,140})\'(?!\w)|“([^”]{3,140})”)')
# A backticked repo path, optionally ``:LINE[-LINE]``, ``::member`` chain,
# ``[case]``, and CLI args after whitespace.
_PATH_RE = re.compile(
    r'`((?:src|scripts|tests|docs|guides|articles|thresholds|opponent_pools|'
    r'userdata)/[\w./-]+?\.(?:py|md|js|toml|json|txt|sh|html|log|csv|cfg|'
    r'ya?ml|gz|pkl))'
    r'(?::\d[\d,\-]*)?((?:::[A-Za-z_]\w*)*)(?:\[[^\]`]*\])?(?:\s[^`]*)?`')
_FENCE_RE = re.compile(r'^ {0,3}(```|~~~)')
_HEADING_RE = re.compile(r'#{1,6}\s')
# A bold numbered item; may wrap lines but not cross a blank line or a
# nested ``**``, so an unclosed item cannot swallow the next paragraph.
_BOLD_ITEM_RE = re.compile(r'\*\*(\d+\.\s(?:(?!\n[ \t]*\n|\*\*).)+?)\*\*', re.S)


def _norm(s: str) -> str:
    # Comment prefixes (``#``, ``//``) and backticks are not part of a name.
    s = s.replace('#', ' ').replace('//', ' ').replace('`', '')
    return re.sub(r'\s+', ' ', s).strip().lower()


def _strip_fences(text: str) -> str:
    out, fence = [], None
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if m and (fence is None or m.group(1) == fence):
            fence = None if fence else m.group(1)
            continue
        if fence is None:
            out.append(line)
    return '\n'.join(out)


def _headings(text: str) -> list[str]:
    return [_norm(l.lstrip('#')) for l in _strip_fences(text).splitlines()
            if _HEADING_RE.match(l)]


def _anchors(notes_text: str) -> list[str]:
    """Headings and ``**N. ...**`` items (wrapped ones too), normalised."""
    body = _strip_fences(notes_text)
    return _headings(body) + [_norm(m.group(1)) for m in _BOLD_ITEM_RE.finditer(body)]


def _resolves(quote: str, anchors: list[str]) -> bool:
    q = _norm(quote)
    if len(q) < 3:  # "###" normalises to nothing and would match everything
        return False
    pat = re.compile(r'(?<!\w)' + re.escape(q) + r'(?!\w)')
    return any(pat.search(a) for a in anchors)


def _cite_quote(m: re.Match) -> str:
    return next(g for g in m.groups()[1:] if g is not None)


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


def _load_known_keys(root: Path) -> set[str] | str:
    """ALL_KEYS of the sibling verify_dev_counts.py, or an error string."""
    script = root / 'scripts' / 'verify_dev_counts.py'
    if not script.is_file():
        return f'{script.relative_to(root)} missing'
    spec = importlib.util.spec_from_file_location('_vdc', script)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        keys = set(mod.ALL_KEYS)
    except Exception as e:  # noqa: BLE001 - any breakage must FAIL, not pass
        return f'could not load ALL_KEYS from verify_dev_counts.py: {e!r}'
    return keys or 'verify_dev_counts.ALL_KEYS is empty'


def _find_def(body: list[ast.stmt], name: str) -> ast.stmt | None:
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
            return n
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return n
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
            return n
    return None


def _member_defined(src: str, chain: list[str]) -> bool | None:
    """True/False, or None when the file does not parse."""
    try:
        body = ast.parse(src).body
    except SyntaxError:
        return None
    for i, name in enumerate(chain):
        node = _find_def(body, name)
        if node is None:
            return False
        if i < len(chain) - 1:
            if not isinstance(node, ast.ClassDef):
                return False
            body = node.body
    return True


def _read(p: Path) -> str:
    return p.read_text(encoding='utf-8', errors='replace')


def run_checks(root: Path = REPO_ROOT) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    notes_path = root / NOTES
    if not notes_path.is_file():
        return [f'{NOTES} missing'], warnings
    try:
        notes = notes_path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        return [f'size: {NOTES} is not valid UTF-8 ({e})'], warnings

    # --- size ------------------------------------------------------------
    n = len(notes)
    if n > CHAR_CAP:
        failures.append(
            f'size: {NOTES} is {n:,} chars, cap {CHAR_CAP:,} '
            f'(over by {n - CHAR_CAP:,}). Trim, or move dated history to '
            f'{CHANGELOG}; see the note at the top of the file.')
    non_ascii = sum(1 for c in notes if ord(c) > 127)
    if non_ascii:
        warnings.append(f'size: {NOTES} has {non_ascii} non-ASCII chars '
                        f'(CLAUDE.md asks for ASCII glyphs; `wc -c` will over-count)')

    # --- sentinels -------------------------------------------------------
    counts: dict[str, int] = {}
    for m in _SENTINEL_RE.finditer(notes):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    keys = _load_known_keys(root)
    if isinstance(keys, str):
        failures.append(f'sentinels: {keys}')
    else:
        for key in sorted(keys):
            c = counts.get(key, 0)
            if c != 1:
                failures.append(f'sentinels: sync:{key} appears {c}x in {NOTES} (want 1)')
    cl_path = root / CHANGELOG
    changelog = _read(cl_path) if cl_path.is_file() else ''
    for m in _SENTINEL_RE.finditer(changelog):
        failures.append(f'sentinels: sync:{m.group(1)} leaked into {CHANGELOG}')

    # --- inbound citations -----------------------------------------------
    anchors = _anchors(notes)
    for p in _iter_repo_files(root):
        rel = p.relative_to(root).as_posix()
        if rel in SELF_FILES:
            continue
        try:
            text = _read(p)
        except OSError:
            continue
        for m in _CITE_RE.finditer(text):
            if m.group(1) != 'DEVELOPER_NOTES':
                continue
            quote = _cite_quote(m)
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
        kind, quote = m.group(1), _cite_quote(m)
        line_no = notes.count('\n', 0, m.start()) + 1
        if kind == 'DEVELOPER_NOTES':
            if not _resolves(quote, anchors):
                failures.append(f'outbound: {NOTES}:{line_no} cites its own section '
                                f'"{_norm(quote)}" -- no such heading/item')
            continue
        path, headings_only = targets[kind]
        if path not in cache:
            cache[path] = _read(path) if path.is_file() else ''
        hay = _headings(cache[path]) if headings_only else [_norm(cache[path])]
        if not _resolves(quote, hay):
            failures.append(
                f'outbound: {NOTES}:{line_no} cites {kind} "{_norm(quote)}" '
                f'-- not found in {path.name}'
                + (' headings' if headings_only else ''))

    for m in _PATH_RE.finditer(notes):
        path_part, members = m.group(1), m.group(2)
        target = root / path_part
        line_no = notes.count('\n', 0, m.start()) + 1
        if not target.exists():
            msg = f'outbound: {NOTES}:{line_no} names `{path_part}` which does not exist'
            # userdata/ is gitignored, machine-local evidence: warn only.
            (warnings if path_part.startswith('userdata/') else failures).append(msg)
            continue
        if members and target.suffix == '.py':
            chain = members.split('::')[1:]
            ok = _member_defined(_read(target), chain)
            if ok is None:
                failures.append(f'outbound: {NOTES}:{line_no} names `{path_part}{members}` '
                                f'but {path_part} does not parse')
            elif not ok:
                failures.append(
                    f'outbound: {NOTES}:{line_no} names `{path_part}{members}` but '
                    f'{path_part} defines no `{"::".join(chain)}` there')

    return failures, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--quiet', action='store_true', help='failures only')
    ap.add_argument('--repo-root', type=Path, default=REPO_ROOT)
    ap.add_argument('--print-scan-paths', action='store_true',
                    help='print the repo paths the checker reads, one per line '
                         '(the pre-commit hook exports exactly these from the index)')
    args = ap.parse_args()

    if args.print_scan_paths:
        for p in (*SCAN_FILES, *SCAN_DIRS, NOTES, CHANGELOG):
            print(p)
        return 0

    failures, warnings = run_checks(args.repo_root)
    if warnings and not args.quiet:
        print('warnings (not blocking):')
        for w in warnings:
            print(f'  - {w}')
    if failures:
        print(f'\nERROR: {NOTES} checks failed:', file=sys.stderr)
        for f in failures:
            print(f'  - {f}', file=sys.stderr)
        return 2
    if not args.quiet:
        notes_len = len(_read(args.repo_root / NOTES))
        print(f'{NOTES}: {notes_len:,}/{CHAR_CAP:,} chars; quoted citations, '
              f'paths and test refs resolve ({len(warnings)} warnings).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
