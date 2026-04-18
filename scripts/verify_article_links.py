#!/usr/bin/env python3
"""Verify href integrity across generated website HTML.

For each HTML file passed on the command line, extracts every href,
classifies it as anchor (same-page fragment), internal file, or
external, and verifies that internals resolve -- both the target path
and, when a #fragment is present, that the target ID exists on the
target page. External URLs are counted and pattern-checked (pvpoke.com
URLs only) but never HTTP-fetched; rate limits + slowness make that a
follow-up tool if we ever need it.

Scope gap (deliberate): onclick handlers aren't scanned. A typical
dive page has ~1000 onclick attributes that construct PvPoke URLs at
runtime from JS-side variables (species IDs, moveset IDs). Static
verification would be fragile -- the URLs don't exist as literals --
so we trust the dive's data model rather than try to statically
verify constructed URLs. If a future regression surfaces stale
onclick-driven links, add a targeted scan rather than expanding this
tool's scope wholesale.

Usage:
    python scripts/verify_article_links.py PATH [PATH ...]
    python scripts/verify_article_links.py --ship

The --ship flag expands to the Oinkologne pre-ship surface set:
  - userdata/website/index.html (site index)
  - the CD article
  - both dive landings + every moveset split under each
  - the standalone compare page

Exit code is 0 when there are zero broken internal refs, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'


class _HrefAndIdExtractor(HTMLParser):
    """Pull every href=... and id=... off real HTML tags.

    A regex-based scanner misfires on the minified Plotly and sortable-
    table JS we inline into the dive HTML, because those payloads
    contain literal "href=" substrings (and ": id" hash keys) inside
    JS string concatenation. html.parser ignores tag-shaped syntax
    inside <script> / <style> bodies by design, which is exactly what
    we want.
    """

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        for k, v in attrs:
            if v is None:
                continue
            if k == 'href':
                self.hrefs.append(v)
            elif k == 'id':
                self.ids.add(v)

    # <area>, <link>, etc. fire as startendtag in some parsers; handle
    # both for robustness.
    def handle_startendtag(self, tag: str, attrs):
        self.handle_starttag(tag, attrs)


def _parse(text: str) -> _HrefAndIdExtractor:
    parser = _HrefAndIdExtractor()
    parser.feed(text)
    return parser


def _find_ship_surfaces() -> list[Path]:
    """Return the pre-ship surface set for --ship.

    Anchored on the Oinkologne CD at time of writing. Future CDs will
    want a config flag or a pattern sweep; for now this is a plain list
    maintained by hand.
    """
    article = (WEBSITE_DIR / 'articles'
               / 'oinkologne-cd-2026-05' / 'index.html')
    compare = (WEBSITE_DIR / 'comparisons'
               / 'oinkologne-male-vs-female' / 'index.html')
    site_index = WEBSITE_DIR / 'index.html'

    surfaces = [site_index, article, compare]
    for dive_slug in ('oinkologne-great-league', 'oinkologne-female-great-league'):
        dive_dir = WEBSITE_DIR / dive_slug
        if not dive_dir.is_dir():
            continue
        surfaces.append(dive_dir / 'index.html')
        for p in sorted(dive_dir.glob('index_m*.html')):
            surfaces.append(p)
    return [s for s in surfaces if s.exists()]


def _classify(href: str) -> str:
    if href.startswith('#'):
        return 'anchor'
    parsed = urlparse(href)
    if parsed.scheme in ('http', 'https'):
        return 'external'
    if parsed.scheme in ('mailto', 'javascript', 'data'):
        return 'other'
    return 'internal'


def _load_ids(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        try:
            text = path.read_text()
        except Exception:
            cache[path] = set()
        else:
            cache[path] = _parse(text).ids
    return cache[path]


def _verify_internal(src: Path, href: str,
                     id_cache: dict[Path, set[str]]) -> str | None:
    """Return None if OK, else an error message."""
    parsed = urlparse(href)
    path_part = unquote(parsed.path)
    frag = parsed.fragment

    if path_part:
        target = (src.parent / path_part).resolve()
        if target.is_dir():
            target = target / 'index.html'
        if not target.exists():
            return f'path not found: {target}'
    else:
        target = src  # same-file fragment reference

    if frag:
        ids = _load_ids(target, id_cache)
        if frag not in ids:
            return f'#{frag} missing in {target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target}'
    return None


def _verify_anchor(src: Path, href: str,
                   id_cache: dict[Path, set[str]]) -> str | None:
    frag = href.lstrip('#')
    if not frag:
        return None  # bare "#" is a top-of-page anchor
    ids = _load_ids(src, id_cache)
    if frag not in ids:
        return f'#{frag} missing in self'
    return None


def _spot_check_external(href: str) -> str | None:
    """Lightweight pattern check for known external URL shapes."""
    parsed = urlparse(href)
    host = parsed.netloc.lower()
    if 'pvpoke.com' in host:
        # Expected shapes we emit:
        #   pvpoke.com/battle/<league>/<species>/<shields>/<moves>/...
        #   pvpoke.com/battle/multi/<league>/all/<species>/...
        # Basic sanity: path should start with /battle/ and have >= 2
        # further segments.
        parts = [p for p in parsed.path.split('/') if p]
        if not parts or parts[0] != 'battle':
            return f'unexpected pvpoke.com path: {parsed.path}'
        if len(parts) < 3:
            return f'truncated pvpoke.com path: {parsed.path}'
    return None


def verify_file(path: Path, id_cache: dict[Path, set[str]]) -> tuple[list[str], list[str]]:
    """Return (errors, hrefs) for `path`. hrefs is the flat list so
    the main loop can tally classification counts without re-parsing.
    """
    try:
        text = path.read_text()
    except Exception as exc:
        return [f'{path}: could not read ({exc})'], []

    parsed = _parse(text)
    id_cache[path] = parsed.ids  # cache eagerly: we just parsed the file

    errors: list[str] = []
    for href in parsed.hrefs:
        kind = _classify(href)
        if kind == 'anchor':
            err = _verify_anchor(path, href, id_cache)
        elif kind == 'internal':
            err = _verify_internal(path, href, id_cache)
        elif kind == 'external':
            err = _spot_check_external(href)
        else:
            err = None
        if err:
            errors.append(f'{path.name}: href={href!r}: {err}')
    return errors, parsed.hrefs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', type=Path,
                        help='HTML files to scan.')
    parser.add_argument('--ship', action='store_true',
                        help='Scan the Oinkologne pre-ship surface set.')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress per-file summaries; print errors only.')
    args = parser.parse_args()

    surfaces: list[Path] = list(args.paths)
    if args.ship:
        surfaces = _find_ship_surfaces() + surfaces

    if not surfaces:
        parser.error('Provide paths, or pass --ship for the pre-ship set.')

    id_cache: dict[Path, set[str]] = {}
    total_hrefs = 0
    total_errors = 0
    counts = {'anchor': 0, 'internal': 0, 'external': 0, 'other': 0}
    for path in surfaces:
        errs, file_hrefs = verify_file(path, id_cache)
        for h in file_hrefs:
            counts[_classify(h)] += 1
        total_hrefs += len(file_hrefs)
        if not args.quiet:
            status = 'OK' if not errs else f'{len(errs)} error(s)'
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path
            print(f'{rel}: {len(file_hrefs)} hrefs, {status}')
        for e in errs:
            print(f'  {e}')
        total_errors += len(errs)

    print()
    print(f'Scanned {len(surfaces)} file(s), {total_hrefs} href(s) '
          f'({counts["internal"]} internal, {counts["anchor"]} anchor, '
          f'{counts["external"]} external, {counts["other"]} other).')
    if total_errors:
        print(f'{total_errors} error(s) found.')
        return 1
    print('No broken internal refs.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
