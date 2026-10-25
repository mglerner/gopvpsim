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
              "..."``, a section sign, a comment-prefixed line wrap before
              the quote) in a scanned file names a heading or a ``**N.
              ...**`` item of the notes, matched case-insensitive on word
              boundaries. A miss in an ENGINE-HASH file
              (sweep_cache._ENGINE_FILES + deep_dive_signature.py) is a
              warning, because fixing a comment there bumps the sweep cache
              hash and must ride the next engine change; a miss in a
              point-in-time doc (docs/validations, docs/reviews,
              docs/TODO_archive.md) is a warning too.
  outbound    every quoted citation FROM the notes to CLAUDE.md, TODO.md or
              CHANGELOG.md names a phrase that exists there (CHANGELOG: a
              heading), and every quoted citation of the notes' OWN sections
              resolves; every backticked repo path in the notes exists
              (``path.py:LINE`` and trailing CLI args tolerated; ``userdata/``
              misses only warn, it is gitignored); every ``tests/x.py::name``
              (``::Class::method``, ``[case]`` too) names a def / async def /
              class / assignment at that position, resolved with ``ast`` and
              seeing through if/try/with blocks. A backticked path may wrap
              a line after ``::`` or inside an identifier at ``_``; a token
              that starts with a repo-path prefix but fits no path grammar
              warns instead of being skipped silently (globs ``*``,
              ``<placeholder>`` and ``{a,b}`` forms, and directories, are
              skipped by design).

NOT checked (so do not read a green run as "every pointer resolves"):
unquoted prose references ("the re-dive entry"), ``file:line`` numbers in
either direction, bare basenames (``battle.py``), directories (``docs/x/``),
identifiers, commit SHAs, item numbers written outside the quotes, a second
quoted item in the same sentence, curly SINGLE quotes, a single-quoted name
containing an apostrophe (skipped, not mis-resolved), ``::member`` on a
non-``.py`` path, globs / placeholders / brace forms / directories in
backticks, files outside
SCAN_DIRS/SCAN_FILES or with a suffix outside SCAN_SUFFIXES, and (in the
hook, whose index export never holds the gitignored ``userdata/``) any
``userdata/`` path.

Usage::

    python scripts/verify_dev_notes.py            # report; exit 3 on failure
    python scripts/verify_dev_notes.py --quiet    # failures only
    python scripts/verify_dev_notes.py --print-scan-paths   # for the hook

Exit codes: 0 clean, 3 = DRIFT_EXIT (failures); anything else is a crash --
1 is a Python traceback, 2 an argparse usage error or a missing script --
and the hook tells them apart. Run by hand it scans the working tree,
untracked files included. Pass ``--repo-root`` to point at another checkout
(the hook passes an index export built from ``--print-scan-paths``; the
tests a synthetic repo).
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

# Exit code for failures; 1 and 2 are taken by tracebacks and argparse.
DRIFT_EXIT = 3

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
SCAN_FILES = ('CLAUDE.md', 'TODO.md', 'README.md', '.gitignore')
SCAN_SUFFIXES = {'.py', '.md', '.js', '.toml', '.txt', '.sh', '.json', '.html'}

_SENTINEL_RE = re.compile(r'<!--\s*sync:([A-Za-z_][A-Za-z0-9_]*)\s*-->')
# A quoted citation of a doc section: ``DOC "name"``, ``DOC 'name'``,
# ```DOC.md` "name"``, ``DOC.md section "name"``, ``DOC's "name"``, curly
# double quotes, an optional section sign, and a comment-prefixed line wrap
# between name and quote. The quoted span may cross a line break inside a
# comment or docstring, so it is normalised before matching (comment
# prefixes and whitespace collapsed). Guards: the name must not be preceded
# by a word char, a quote or a slash (so the string literal
# "DEVELOPER_NOTES.md" and a path are not citations); at most ONE line
# break between name and quote (so a mention at the end of a paragraph
# cannot pair with a quote paragraphs later); a single-quoted name must
# follow whitespace and its closing quote must not be followed by a word
# char (so 'DEVELOPER_NOTES.md' and an apostrophe inside the name do not
# open or truncate one).
_CITE_RE = re.compile(
    r'(?<![\w"\'/])`?(DEVELOPER_NOTES|CLAUDE\.md|TODO(?:\.md)?|CHANGELOG(?:\.md)?)'
    r"(?:\.md)?`?(?:'s)?,?[ \t]*(?:\n[ \t]*)?(?:(?:#(?!#)|//)[ \t]*)?(?:section\s+)?"
    r'(?:§\s*)?'
    r'(?:"([^"]{3,140})"|(?<=\s)\'([^\']{3,140})\'(?!\w)|“([^”]{3,140})”)')
# A backticked repo path (matched against a normalised backtick span),
# optionally ``:LINE[-LINE]``, ``::member`` chain, ``[case]``, CLI args.
_PATH_PREFIXES = ('src', 'scripts', 'tests', 'docs', 'guides', 'articles',
                  'thresholds', 'opponent_pools', 'userdata')
_PATH_RE = re.compile(
    r'^((?:' + '|'.join(_PATH_PREFIXES) + r')/[\w./-]+?\.(?:py|md|js|toml|json|'
    r'txt|sh|html|log|csv|cfg|ya?ml|gz|pkl))'
    r'(?:#[\w-]+)?'  # a markdown anchor is tolerated, not resolved
    r'(?::\d[\d,\-]*)?((?:::[A-Za-z_]\w*)*)(?:\[[^\]]*\])?(?:\s.*)?$', re.S)
# A span may wrap lines but not cross a blank line, so one stray backtick
# cannot desynchronise every later span.
_BACKTICK_SPAN_RE = re.compile(r'`([^`\n](?:[^`\n]|\n(?![ \t]*\n))*)`')
# A fence opens with 3+ backticks or tildes (<= 3 spaces indent, optional
# info string) and closes with the same char, at least as many, nothing else.
_FENCE_RE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
_HEADING_RE = re.compile(r'#{1,6}\s')
# A bold numbered item; may wrap lines but not cross a blank line or a
# nested ``**``, so an unclosed item cannot swallow the next paragraph.
_BOLD_ITEM_RE = re.compile(r'\*\*(\d+\.\s(?:(?!\n[ \t]*\n|\*\*).)+?)\*\*', re.S)


def _norm(s: str) -> str:
    # Comment prefixes (``#``, ``//``) and backticks are not part of a name.
    s = s.replace('#', ' ').replace('//', ' ').replace('`', '')
    return re.sub(r'\s+', ' ', s).strip().lower()


def _strip_fences(text: str, keep_lines: bool = False) -> str:
    """Drop fenced code blocks; with ``keep_lines`` each dropped line
    becomes an empty one so line numbers still match the file."""
    out, fence = [], None
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if m and fence is None:
            fence = m.group(1)
        elif m and fence is not None and m.group(1)[0] == fence[0] \
                and len(m.group(1)) >= len(fence) and not m.group(2).strip():
            fence = None
        elif fence is None:
            out.append(line)
            continue
        if keep_lines:
            out.append('')
    return '\n'.join(out)


def _odd_backtick_paragraphs(text: str) -> list[int]:
    """First line of every blank-line-delimited paragraph (fences dropped)
    with an odd number of backticks. A stray backtick inverts span pairing
    for the rest of its paragraph and silently hides every ref there
    (round-5 review: four refs vanished behind one typo)."""
    out, start, count = [], None, 0
    for i, line in enumerate(_strip_fences(text, keep_lines=True).splitlines(), 1):
        if not line.strip():
            if count % 2:
                out.append(start)
            start, count = None, 0
            continue
        if start is None:
            start = i
        count += line.count('`')
    if count % 2:
        out.append(start)
    return out


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


def _path_tokens(notes: str):
    """Yield (line_no, normalised token) for every backticked span that
    starts with a repo path prefix. A span may wrap on either side of
    ``::`` or after an identifier ``_`` or a path ``/``; all are re-joined
    before matching. NOT checked: a second ref in the same span
    (`a.py::x b.py::gone` -- the tail after whitespace is read as CLI args).
    """
    for m in _BACKTICK_SPAN_RE.finditer(notes):
        tok = re.sub(r'\s*::\s*', '::', m.group(1))
        tok = re.sub(r'([_/])\n\s*', r'\1', tok)
        if re.match(r'(?:' + '|'.join(_PATH_PREFIXES) + r')/', tok):
            yield notes.count('\n', 0, m.start()) + 1, tok


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


def _flatten(body: list[ast.stmt]):
    """Statements of a body, seeing through if/try/with blocks."""
    for n in body:
        yield n
        if isinstance(n, (ast.If, ast.Try, ast.With)):
            for sub in ('body', 'orelse', 'finalbody'):
                yield from _flatten(getattr(n, sub, None) or [])
            for h in getattr(n, 'handlers', []):
                yield from _flatten(h.body)


def _names(t: ast.expr) -> list[str]:
    """Names BOUND by an assignment target: plain names and those inside
    tuple/list/starred unpacking. `obj.attr = 1` and `a[0] = 1` bind nothing."""
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        return [n for e in t.elts for n in _names(e)]
    if isinstance(t, ast.Starred):
        return _names(t.value)
    return []


def _targets(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Assign):
        return [n for t in node.targets for n in _names(t)]
    if isinstance(node, ast.AnnAssign):
        return _names(node.target)
    return []


def _find_def(body: list[ast.stmt], name: str) -> ast.stmt | None:
    for n in _flatten(body):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
            return n
        if name in _targets(n):
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

    for line_no in _odd_backtick_paragraphs(notes):
        failures.append(f'outbound: {NOTES}:{line_no} paragraph has an odd number of '
                        f'backticks; every ref after the stray one is paired wrong')

    for line_no, tok in _path_tokens(notes):
        m = _PATH_RE.match(tok)
        if not m:
            # A failure, not a warning: the hook runs --quiet and never shows
            # warnings, so an unchecked ref would otherwise pass unseen.
            if not re.search(r'[*<{]|/$', tok):  # globs, placeholders, braces, dirs: by design
                failures.append(f'outbound: {NOTES}:{line_no} backticked `{tok}` looks like a '
                                f'repo path but fits no checked form (a directory ends in `/`, '
                                f'a file carries its extension, a member is `::name`)')
            continue
        path_part, members = m.group(1), m.group(2)
        target = root / path_part
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
        return DRIFT_EXIT
    if not args.quiet:
        notes_len = len(_read(args.repo_root / NOTES))
        print(f'{NOTES}: {notes_len:,}/{CHAR_CAP:,} chars; quoted citations, '
              f'paths and test refs resolve ({len(warnings)} warnings).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
