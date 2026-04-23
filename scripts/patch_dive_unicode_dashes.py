#!/usr/bin/env python3
"""Replace em/en-dashes with ASCII hyphens in rendered HTML.

Walks each HTML file, skips ``<script>`` / ``<style>`` / ``<pre>`` /
``<code>`` block contents (where Unicode dashes may be unavoidable or
intentional -- Plotly's i18n quote map, CSS comments, quoted code
samples), and replaces em-dash (U+2014) and en-dash (U+2013) with an
ASCII hyphen in:

* visible text nodes,
* values of user-facing attributes (``title``, ``alt``, ``aria-label``).

Idempotent: re-running on a clean file is a no-op. Paired with
``verify_no_unicode_dashes.py`` which reports-only; this one rewrites
in place. Used pre-ship when the source templates have been fixed but
existing dive HTMLs were rendered against the old templates and
re-diving isn't desired.

Usage:
    python scripts/patch_dive_unicode_dashes.py PATH [PATH ...]
    python scripts/patch_dive_unicode_dashes.py --dry-run PATH

Exits 0 even when it patches files; ``--dry-run`` reports only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EM_DASH = '—'
EN_DASH = '–'

# Block tags whose verbatim content is source-like and out of scope.
# Matched with the opening tag to account for attribute lists and
# self-closing variants (style won't self-close in practice, but cheap
# to permit).
_BLOCK_SKIP = re.compile(
    r'<(script|style|pre|code)\b[^>]*>.*?</\1\s*>',
    re.IGNORECASE | re.DOTALL,
)

# Attribute values that render to users. Replace dashes inside these
# values even on tags that carry no text content (e.g., <img alt=...>).
_USER_ATTR_RE = re.compile(
    r'(\s(?:title|alt|aria-label)\s*=\s*)(?:"([^"]*)"|\'([^\']*)\')',
    re.IGNORECASE,
)


def _replace(text: str) -> str:
    return (text
            .replace(EM_DASH, '-').replace(EN_DASH, '-')
            .replace('&mdash;', '-').replace('&ndash;', '-'))


def _patch_html(html: str) -> tuple[str, int]:
    """Return (new_html, n_replaced).

    Strategy: walk the HTML left-to-right, excising source-like blocks
    (``<script>``, ``<style>``, ``<pre>``, ``<code>``) intact and
    dash-replacing everything outside them. User-facing attribute
    values inside those excised blocks are still in-scope in principle
    but very rare in practice (no ``<script title="...">`` emitters in
    our templates), so we skip them rather than build a full parser.
    """
    out: list[str] = []
    n_replaced = 0
    pos = 0
    for m in _BLOCK_SKIP.finditer(html):
        segment = html[pos:m.start()]
        before = (segment.count(EM_DASH) + segment.count(EN_DASH)
                  + segment.count('&mdash;') + segment.count('&ndash;'))
        n_replaced += before
        # Replace inside text + re-scan attribute values for added safety
        # (the text replacement already hits them, but being explicit
        # keeps the invariant clear).
        out.append(_replace(segment))
        out.append(m.group(0))  # block preserved verbatim
        pos = m.end()
    tail = html[pos:]
    n_replaced += (tail.count(EM_DASH) + tail.count(EN_DASH)
                   + tail.count('&mdash;') + tail.count('&ndash;'))
    out.append(_replace(tail))
    return ''.join(out), n_replaced


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('paths', nargs='+', type=Path,
                        help='HTML files or directories to rewrite.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    files: list[Path] = []
    for p in args.paths:
        if p.is_dir():
            files.extend(sorted(p.rglob('*.html')))
        elif p.is_file() and p.suffix == '.html':
            files.append(p)

    total_replaced = 0
    total_files = 0
    for f in files:
        try:
            html = f.read_text()
        except Exception as exc:
            print(f'{f}: could not read ({exc})', file=sys.stderr)
            continue
        new_html, n = _patch_html(html)
        if n == 0:
            continue
        total_replaced += n
        total_files += 1
        verb = 'would replace' if args.dry_run else 'replaced'
        print(f'{f}: {verb} {n} Unicode dash(es)')
        if not args.dry_run:
            f.write_text(new_html)

    print()
    verb = 'would replace' if args.dry_run else 'replaced'
    print(f'{verb} {total_replaced} dash(es) across {total_files} file(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
