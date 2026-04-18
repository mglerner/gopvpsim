#!/usr/bin/env python3
"""One-off patcher: add ``id="opp-<slug>"`` per-opponent anchors to
existing dive HTML.

The dive renderer now emits these ids natively on the first ``<li>``
for each opponent inside the standalone Matchup-Flipping Boundaries
and Anchor-Driven Matchup Flips sections, so an external page (the
CD article's Matchup Delta table) can deep-link directly to that
opponent's first boundary bullet. This script applies the same
transformation to already-built HTML in place so links work without
re-running ``deep_dive.py``.

Usage:
    python scripts/patch_dive_opp_anchors.py [--dry-run] PATH [PATH ...]

PATH can be a single .html file or a directory (walks recursively for
*.html). By default modifies files in place; --dry-run prints counts
without writing.

Mirrors ``scripts/patch_dive_tier_anchors.py``, which is the precedent
for this pattern (backfill a dive-HTML id so article-side deep links
resolve without a re-dive).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_SLUG_RE = re.compile(r'[^a-z0-9]+')


def opp_slug(name: str) -> str:
    """Matches ``deep_dive_rendering.opp_slug``. Drift breaks links."""
    return _SLUG_RE.sub('-', name.lower()).strip('-')


def _section_re(title: str) -> re.Pattern:
    return re.compile(
        r'<details class="dd-collapsible"><summary[^>]*>'
        + re.escape(title) + r'.*?</details>',
        re.DOTALL,
    )


BOUNDARIES_SECTION_RE = _section_re('Matchup-Flipping Boundaries')
ANCHORS_SECTION_RE = _section_re('Anchor-Driven Matchup Flips')

_LI_RE = re.compile(r'<li(?P<attrs>[^>]*)>(?P<body>.*?)</li>', re.DOTALL)
_BOUNDARIES_OPP_RE = re.compile(r' flips <b style="[^"]*">([^<]+)</b>')
_ANCHORS_OPP_RE = re.compile(r' vs <b style="[^"]*">([^<]+)</b>')
_HAS_ID_RE = re.compile(r'\sid=')


def _patch_section(section: str, opp_re: re.Pattern) -> tuple[str, int]:
    seen: set[str] = set()
    count = 0

    def _repl(m: re.Match) -> str:
        nonlocal count
        attrs = m.group('attrs')
        body = m.group('body')
        opp_m = opp_re.search(body)
        if not opp_m:
            return m.group(0)
        opp = opp_m.group(1)
        # Populate seen regardless of whether we tag this bullet, so on a
        # second pass over already-patched HTML the bullets that skipped
        # via _HAS_ID_RE still suppress duplicate tagging of their
        # later siblings.
        already_seen = opp in seen
        seen.add(opp)
        if already_seen or _HAS_ID_RE.search(attrs):
            return m.group(0)
        count += 1
        return f'<li{attrs} id="opp-{opp_slug(opp)}">{body}</li>'

    return _LI_RE.sub(_repl, section), count


def patch_html(html: str) -> tuple[str, int, int]:
    total_b = 0
    total_a = 0

    def _patch_boundaries(m: re.Match) -> str:
        nonlocal total_b
        new_section, n = _patch_section(m.group(0), _BOUNDARIES_OPP_RE)
        total_b += n
        return new_section

    def _patch_anchors(m: re.Match) -> str:
        nonlocal total_a
        new_section, n = _patch_section(m.group(0), _ANCHORS_OPP_RE)
        total_a += n
        return new_section

    html = BOUNDARIES_SECTION_RE.sub(_patch_boundaries, html, count=1)
    html = ANCHORS_SECTION_RE.sub(_patch_anchors, html, count=1)
    return html, total_b, total_a


def _iter_html_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == '.html' else []
    return sorted(path.rglob('*.html'))


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Backfill per-opponent anchor ids on existing dive HTML.')
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change without writing.')
    args = parser.parse_args()

    total_files = 0
    total_b = 0
    total_a = 0
    for root in args.paths:
        for path in _iter_html_files(root):
            html = path.read_text()
            new_html, nb, na = patch_html(html)
            if nb == 0 and na == 0:
                continue
            if new_html == html:
                # All matches were already patched.
                continue
            total_files += 1
            total_b += nb
            total_a += na
            verb = 'would patch' if args.dry_run else 'patched'
            print(f'{verb} {path}: {nb} boundaries + {na} anchors')
            if not args.dry_run:
                path.write_text(new_html)
    verb = 'would patch' if args.dry_run else 'patched'
    print(f'\n{verb} {total_b} boundary + {total_a} anchor ids '
          f'across {total_files} file(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
