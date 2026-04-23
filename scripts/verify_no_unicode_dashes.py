#!/usr/bin/env python3
"""Verify no em-dash / en-dash in public-facing rendered HTML.

Scans each HTML file for em-dash (U+2014) and en-dash (U+2013) in
user-visible text and in user-facing attribute values (``title``,
``alt``, ``aria-label``). Skips content inside ``<script>``,
``<style>``, ``<pre>``, and ``<code>`` elements since those carry
source-like text where Unicode dashes are either unavoidable
(Plotly's i18n map, minified JS) or intentional (quoted terminal
output, code samples).

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
SKIP_TEXT_IN = frozenset({'script', 'style', 'pre', 'code'})

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

    # ------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._stack.append(tag)
        self._scan_attrs(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        # Self-closing (e.g. <img ... />). Don't push onto stack.
        self._scan_attrs(tag, attrs)

    def handle_endtag(self, tag):
        # Pop the most recent matching tag if present (tolerate malformed
        # HTML by skipping silently when mismatched — the link verifier
        # does the same).
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._stack and self._stack[-1] in SKIP_TEXT_IN:
            return
        self._scan_text(data, container=self._stack[-1] if self._stack else '')

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
                snippet = self._snippet(text, idx)
                self.hits.append((kind, lineno, col + idx, container, snippet))
                idx = text.find(ch, idx + 1)

    @staticmethod
    def _snippet(text: str, idx: int, half: int = 30) -> str:
        lo = max(0, idx - half)
        hi = min(len(text), idx + half + 1)
        # Strip trailing/leading whitespace so terminal output stays
        # single-line. Replace internal whitespace runs with a single
        # space.
        out = text[lo:hi].replace('\n', ' ').replace('\t', ' ')
        while '  ' in out:
            out = out.replace('  ', ' ')
        return out.strip()


def _find_ship_surfaces() -> list[Path]:
    """Return the pre-ship surface set (mirrors verify_article_links.py)."""
    article = (WEBSITE_DIR / 'articles'
               / 'oinkologne-cd-2026-05' / 'index.html')
    compare = (WEBSITE_DIR / 'comparisons'
               / 'oinkologne-male-vs-female' / 'index.html')
    site_index = WEBSITE_DIR / 'index.html'

    surfaces = [site_index, article, compare]
    for dive_slug in ('oinkologne-great-league',
                      'oinkologne-female-great-league'):
        dive_dir = WEBSITE_DIR / dive_slug
        if not dive_dir.is_dir():
            continue
        surfaces.append(dive_dir / 'index.html')
        for p in sorted(dive_dir.glob('index_m*.html')):
            surfaces.append(p)
    return [s for s in surfaces if s.exists()]


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
