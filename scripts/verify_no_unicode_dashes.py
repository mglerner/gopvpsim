#!/usr/bin/env python3
"""Verify no em-dash / en-dash in public-facing rendered HTML.

Scans each HTML file for em-dash (U+2014) and en-dash (U+2013) in
user-visible text and in user-facing attribute values (``title``,
``alt``, ``aria-label``). Skips *text* inside ``<style>``, ``<pre>``,
and ``<code>`` elements since those carry source-like text where
Unicode dashes are either unavoidable or intentional (quoted terminal
output, code samples).

``<script>`` is a special case: its *code* is out of scope, but its
STRING LITERALS are in scope, because script-generated prose is real
reader-visible prose. Script-driven pages (the joint-IV robustness
pages render ~100% of their prose from inlined app JS) used to get a
clean bill regardless of content -- the gate simply could not see
them (TODO.md "Ship-gate gap", found by the 2026-08-17 thievul
pre-publish review). ``js_string_literals()`` closes that: it is the
inverse of ``tests/test_win_boundary.strip_js`` -- that helper blanks
literals to leave code, this one keeps literals and drops code.

Two documented carve-outs inside ``<script>``, both narrow and both
covered by tests in ``tests/test_ship_gate_detectors.py``:

  - **Vendored third-party bundles** (``VENDOR_SCRIPT_MARKERS``): the
    inlined Plotly bundle carries genuine em/en-dashes in its i18n
    table and in a GLSL shader comment. It is not our prose and we do
    not edit it. An unrecognized third-party bundle FIRES the gate
    rather than being skipped, so this stays loud.
  - **``console.*`` arguments**: developer-console output, never
    rendered to a reader. ``scripts/deep_dive_engine.js:984`` is the
    one such string in the tree today.

Comments, regex literals, identifiers, and property names are all
out of scope: only string/template literals are read.

Rule origin: generated public-facing prose should use ASCII hyphens
only (see CLAUDE.md / feedback memory "No em-dashes in public-facing
text"). Markdown / comments / commit messages / source code remain
free to use em-dashes; this tool only checks the rendered HTML that
ships.

Usage:
    python scripts/verify_no_unicode_dashes.py PATH [PATH ...]
    python scripts/verify_no_unicode_dashes.py --ship

The ``--ship`` flag expands to the Oinkologne pre-ship surface set
mirroring ``verify_article_links.py``:

  - userdata/website/index.html (site index)
  - the CD article
  - the standalone compare page
  - both dive landings + every moveset split under each

Exit code 0 when clean, 1 when any hit is found.
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'

EM_DASH = '—'
EN_DASH = '–'

# Tags whose text content is source-like and not in scope for the
# ASCII-hyphen rule. html.parser already routes <script>/<style>
# contents to handle_data without entering nested-tag mode, so we only
# need to track which enclosing tag is active to skip the data.
# <script> is here because its CODE is out of scope; its string
# literals are scanned separately (see js_string_literals).
SKIP_TEXT_IN = frozenset({'script', 'style', 'pre', 'code'})

# Every source spelling that RENDERS as an em/en dash. The HTML-text
# side gets these for free (HTMLParser convert_charrefs=True), but
# script bodies arrive raw in CDATA mode, so a literal must be decoded
# before it is checked -- otherwise '—' and '&mdash;' are silent
# ways past the gate. Order matters only for the cheap pre-filter.
_DASH_ESCAPES = {
    '\\u2014': EM_DASH, '\\u2013': EN_DASH,
    '&mdash;': EM_DASH, '&ndash;': EN_DASH,
    '&#8212;': EM_DASH, '&#8211;': EN_DASH,
    '&#x2014;': EM_DASH, '&#x2013;': EN_DASH,
    '&#X2014;': EM_DASH, '&#X2013;': EN_DASH,
}
# Cheap substring pre-filter: skip the (expensive) literal walk for any
# script body that cannot possibly contain a dash in any spelling.
# Deliberately case-SENSITIVE: JS only accepts a lowercase \u escape, so
# a case-blind match would decode the literal text "\U2014" (which JS
# renders as "U2014") into a phantom em dash.
_DASH_TRIGGERS = (EM_DASH, EN_DASH, *sorted(_DASH_ESCAPES))
_DASH_ESCAPE_RE = re.compile(
    '|'.join(re.escape(k) for k in sorted(_DASH_ESCAPES)))

# Third-party bundles we inline verbatim. Their string tables carry
# genuine Unicode dashes (Plotly's i18n map; a GLSL shader comment),
# they are not our prose, and we do not edit them. Matched against the
# HEAD of a <script> body so a *new* unrecognized bundle fires the gate
# instead of being silently skipped.
VENDOR_SCRIPT_MARKERS = ('plotly.js v',)
_VENDOR_HEAD_CHARS = 500

# Callees whose string arguments are developer-console output, never
# reader-visible prose. Matched against the innermost enclosing call.
_CONSOLE_CALL_RE = re.compile(r'(?:^|\.)console\.[A-Za-z_$][\w$]*$')

# Characters after which a `/` starts a regex literal rather than a
# division (same disambiguation as tests/test_win_boundary.strip_js).
_RE_PRECEDERS = set('(,=:[!&|?{};+-*%~^<>\n')
_CALLEE_RE = re.compile(r'[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*$')


def _is_vendored(body: str) -> bool:
    """True for an inlined third-party bundle (see VENDOR_SCRIPT_MARKERS)."""
    head = body[:_VENDOR_HEAD_CHARS]
    if not head.lstrip().startswith('/*'):
        return False
    return any(marker in head for marker in VENDOR_SCRIPT_MARKERS)


def _decode_js_literal(seg: str) -> str:
    """Render-equivalent form of a JS string-literal body.

    Only the dash spellings matter here, so this deliberately does NOT
    implement full JS unescaping -- it maps the escape/entity spellings
    of em/en dash onto the characters they render as, and leaves
    everything else alone.
    """
    return _DASH_ESCAPE_RE.sub(lambda m: _DASH_ESCAPES[m.group(0)], seg)


def _callee_before(text: str, paren: int) -> str:
    """The callee text immediately left of the ``(`` at ``paren``, or ''."""
    # Bounded lookback: callee names are short, and O(len(text)) slicing
    # per '(' would be quadratic on a 250 KB app bundle. Truncating a
    # long chain can only LOSE a console.* match (-> in scope), never
    # invent one, so the window is safe in the loud direction.
    left = text[max(0, paren - 200):paren].rstrip()
    m = _CALLEE_RE.search(left)
    if m is None or m.end() != len(left):
        return ''
    return re.sub(r'\s+', '', m.group(0))


def js_string_literals(text: str, base: int = 0,
                       callee: str = '') -> list[tuple[int, str, str]]:
    """Extract every string-literal body from JS source.

    Returns ``(offset, raw_segment, enclosing_callee)`` triples, where
    ``offset`` is ``base`` plus the segment's index in ``text`` (``base``
    exists so the recursive ``${...}`` pass reports positions in the
    OUTER source). Handles ``'``/``"`` strings, template literals (their text
    parts, with ``${...}`` expressions scanned recursively), backslash
    escapes, ``//`` and ``/* */`` comments, and regex literals. Code,
    comments, and regex sources are dropped -- this is the inverse of
    ``tests/test_win_boundary.strip_js``.

    ``enclosing_callee`` is the innermost function being called at the
    literal's position (``'console.error'``, ``'JSON.parse'``, ...) or
    ``''`` when the literal is not a call argument. Ambiguity resolves
    to ``''``, i.e. IN scope: a parse the walker cannot follow makes the
    gate louder, never quieter.
    """
    out: list[tuple[int, str, str]] = []
    calls: list[str] = [callee]
    i, n = 0, len(text)
    prev_sig = '\n'
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in '\'"':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == c or text[j] == '\n':
                    break
                j += 1
            out.append((base + i + 1, text[i + 1:j], calls[-1]))
            prev_sig = 'x'
            i = min(j + 1, n)
            continue
        if c == '`':
            j = seg_start = i + 1
            while j < n:
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == '`':
                    break
                if ch == '$' and j + 1 < n and text[j + 1] == '{':
                    out.append((base + seg_start, text[seg_start:j], calls[-1]))
                    depth, k = 1, j + 2
                    while k < n and depth:
                        if text[k] == '{':
                            depth += 1
                        elif text[k] == '}':
                            depth -= 1
                        elif text[k] in '\'"`':
                            quote = text[k]
                            k += 1
                            while k < n and text[k] != quote:
                                k += 2 if text[k] == '\\' else 1
                        k += 1
                    out.extend(js_string_literals(text[j + 2:k - 1],
                                                  base + j + 2, calls[-1]))
                    j = seg_start = k
                    continue
                j += 1
            out.append((base + seg_start, text[seg_start:j], calls[-1]))
            prev_sig = 'x'
            i = min(j + 1, n)
            continue
        if c == '/' and prev_sig in _RE_PRECEDERS:
            j, in_class = i + 1, False
            while j < n:
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == '\n':
                    break            # not a regex after all; bail
                if ch == '[':
                    in_class = True
                elif ch == ']':
                    in_class = False
                elif ch == '/' and not in_class:
                    j += 1
                    break
                j += 1
            prev_sig = 'x'
            i = j
            continue
        if c == '(':
            calls.append(_callee_before(text, i))
        elif c == ')' and len(calls) > 1:
            calls.pop()
        if not c.isspace():
            prev_sig = c
        i += 1
    return out


def scan_script_body(body: str) -> list[tuple[str, int, str]]:
    """Dash hits in the string literals of one ``<script>`` body.

    Returns ``(kind, offset_into_body, snippet)``. Vendored bundles and
    ``console.*`` arguments are skipped (see the module docstring).
    """
    if _is_vendored(body):
        return []
    if not any(t in body for t in _DASH_TRIGGERS):
        return []
    hits = []
    for off, seg, callee in js_string_literals(body):
        if _CONSOLE_CALL_RE.search(callee):
            continue
        value = _decode_js_literal(seg)
        if EM_DASH not in value and EN_DASH not in value:
            continue
        for ch, kind in ((EM_DASH, 'em'), (EN_DASH, 'en')):
            if ch in value:
                hits.append((kind, off, _snippet(value, value.find(ch))))
    return hits


def _snippet(text: str, idx: int, half: int = 30) -> str:
    """Single-line context window around ``idx`` for terminal output."""
    lo = max(0, idx - half)
    hi = min(len(text), idx + half + 1)
    out = text[lo:hi].replace('\n', ' ').replace('\t', ' ')
    while '  ' in out:
        out = out.replace('  ', ' ')
    return out.strip()


# Attribute values that render to users (tooltip, alt text, screen-
# reader label). Other attributes carry machine strings (class, id,
# href, data-*) and aren't in scope.
USER_VISIBLE_ATTRS = frozenset({'title', 'alt', 'aria-label'})


class _DashScanner(HTMLParser):
    """Collect em/en-dash hits, with their source line and a context snippet."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # Stack of open tag names so we know whether we're inside a
        # SKIP_TEXT_IN context. Using a list-as-stack; pop on close.
        self._stack: list[str] = []
        # Accumulated hits: list of (kind, lineno, col, tag_or_attr, snippet)
        self.hits: list[tuple[str, int, int, str, str]] = []
        # Inlined <script> body being collected. None when not inside a
        # <script>; the line number is taken from the first data chunk
        # (getpos() at the start tag points at '<script', not the body).
        self._script: list[str] | None = None
        self._script_line = 0

    # ------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._stack.append(tag)
        if tag == 'script':
            self._script, self._script_line = [], 0
        self._scan_attrs(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        # Self-closing (e.g. <img ... />). Don't push onto stack.
        self._scan_attrs(tag, attrs)

    def handle_endtag(self, tag):
        if tag == 'script' and self._script is not None:
            self._scan_script(''.join(self._script))
            self._script = None
        # Pop the most recent matching tag if present (tolerate malformed
        # HTML by skipping silently when mismatched — the link verifier
        # does the same).
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._script is not None:
            if not self._script:
                self._script_line = self.getpos()[0]
            self._script.append(data)
            return
        if self._stack and self._stack[-1] in SKIP_TEXT_IN:
            return
        self._scan_text(data, container=self._stack[-1] if self._stack else '')

    def _scan_script(self, body: str) -> None:
        """Reader-visible prose generated by inlined app JS (TODO gap)."""
        for kind, off, snippet in scan_script_body(body):
            nl = body.rfind('\n', 0, off)
            lineno = self._script_line + body.count('\n', 0, off)
            col = off - nl - 1 if nl != -1 else off
            self.hits.append((kind, lineno, col, '<script> string literal',
                              snippet))

    # ------------------------------------------------------------------
    def _scan_attrs(self, tag: str, attrs):
        for k, v in attrs:
            if v is None or k not in USER_VISIBLE_ATTRS:
                continue
            self._scan_text(v, container=f'<{tag} {k}=...>')

    def _scan_text(self, text: str, *, container: str) -> None:
        if EM_DASH not in text and EN_DASH not in text:
            return
        lineno, col = self.getpos()
        for ch, kind in ((EM_DASH, 'em'), (EN_DASH, 'en')):
            idx = text.find(ch)
            while idx != -1:
                snippet = _snippet(text, idx)
                self.hits.append((kind, lineno, col + idx, container, snippet))
                idx = text.find(ch, idx + 1)


def _find_ship_surfaces() -> list[Path]:
    """Every user-facing HTML the publish rsync will ship.

    Single-sourced in ship_surfaces.py (shared with the link gate;
    DRY review 2026-08-05 entry 3a).
    """
    from ship_surfaces import find_ship_surfaces
    return find_ship_surfaces(WEBSITE_DIR)


def scan_file(path: Path) -> list[tuple[str, int, int, str, str]]:
    text = path.read_text()
    scanner = _DashScanner()
    scanner.feed(text)
    return scanner.hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('paths', nargs='*', type=Path,
                        help='HTML files to scan.')
    parser.add_argument('--ship', action='store_true',
                        help='Scan the Oinkologne pre-ship surface set.')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress per-file summaries; print hits only.')
    args = parser.parse_args()

    surfaces: list[Path] = list(args.paths)
    if args.ship:
        surfaces = _find_ship_surfaces() + surfaces

    if not surfaces:
        parser.error('Provide paths, or pass --ship for the pre-ship set.')

    total_hits = 0
    for path in surfaces:
        try:
            hits = scan_file(path)
        except Exception as exc:
            print(f'{path}: could not read ({exc})')
            return 1
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        if not args.quiet:
            status = 'OK' if not hits else f'{len(hits)} hit(s)'
            print(f'{rel}: {status}')
        for kind, lineno, col, container, snippet in hits:
            print(f'  {rel}:{lineno}:{col}  {kind}-dash  in {container}'
                  f'  "{snippet}"')
        total_hits += len(hits)

    print()
    if total_hits:
        print(f'{total_hits} hit(s) across {len(surfaces)} file(s).')
        return 1
    print(f'No em/en-dashes in user-facing text across '
          f'{len(surfaces)} file(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
