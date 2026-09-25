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
    python scripts/verify_article_links.py --ship --jobs 1   # serial

Files are verified in a worker pool (--jobs, default
min(12, cpu_count - 2)) and results are printed in input order, so the
report is identical to a serial run (checked 2026-09-25 on the real
site tree by diffing both). The default leaves cores free for the fast
test tier, which run_ship_gates.py runs at the same time.

The --ship flag expands to the Oinkologne pre-ship surface set:
  - userdata/website/index.html (site index)
  - the CD article
  - both dive landings + every moveset split under each
  - the standalone compare page

Exit code is 0 when there are zero broken internal refs, 1 otherwise.
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from collections import Counter
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
    """Every user-facing HTML the publish rsync will ship.

    Single-sourced in ship_surfaces.py (shared with the unicode-dash
    gate; DRY review 2026-08-05 entry 3a).
    """
    from ship_surfaces import find_ship_surfaces
    return find_ship_surfaces(WEBSITE_DIR)


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
        # further segments. A bare homepage link (the Under the Hood
        # guide's "data comes from PvPoke" citation) is legitimate.
        parts = [p for p in parsed.path.split('/') if p]
        if not parts:
            return None
        if parts[0] != 'battle':
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


def default_jobs() -> int:
    """Pool size when --jobs is not given: min(12, cpu_count - 2), >= 1."""
    return max(1, min(12, (os.cpu_count() or 1) - 2))


# Per-process id cache for _verify_one. With --jobs 1 this is the single
# cache main() used to keep; in a pool each worker has its own. The
# cache only saves re-parsing target pages (a page's ids do not depend
# on which process parsed it), so splitting it changes no result.
_ID_CACHE: dict[Path, set[str]] = {}


def _verify_one(path: Path) -> tuple[list[str], int, Counter]:
    """verify_file for one surface, reduced to what main() prints.

    Returns (errors, href count, per-class counts), not the href list:
    sending ~690k hrefs back through the pool pipe costs more than
    counting them where they were parsed.
    """
    errs, hrefs = verify_file(path, _ID_CACHE)
    return errs, len(hrefs), Counter(_classify(h) for h in hrefs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', type=Path,
                        help='HTML files to scan.')
    parser.add_argument('--ship', action='store_true',
                        help='Scan the Oinkologne pre-ship surface set.')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress per-file summaries; print errors only.')
    parser.add_argument('-j', '--jobs', type=int, default=default_jobs(),
                        help='Worker processes (default min(12, cpu_count-2)); '
                             '1 runs serially in-process. The report is the '
                             'same either way.')
    args = parser.parse_args()

    surfaces: list[Path] = list(args.paths)
    if args.ship:
        surfaces = _find_ship_surfaces() + surfaces

    if not surfaces:
        parser.error('Provide paths, or pass --ship for the pre-ship set.')

    total_hrefs = 0
    total_errors = 0
    counts = {'anchor': 0, 'internal': 0, 'external': 0, 'other': 0}
    jobs = max(1, min(args.jobs, len(surfaces)))
    pool = multiprocessing.Pool(jobs) if jobs > 1 else None
    try:
        # imap, not imap_unordered: results come back in surface order,
        # so the printed report is the serial one.
        results = (pool.imap(_verify_one, surfaces) if pool
                   else map(_verify_one, surfaces))
        for path, (errs, n_hrefs, file_counts) in zip(surfaces, results):
            for kind, n in file_counts.items():
                counts[kind] += n
            total_hrefs += n_hrefs
            if not args.quiet:
                status = 'OK' if not errs else f'{len(errs)} error(s)'
                try:
                    rel = path.relative_to(REPO_ROOT)
                except ValueError:
                    rel = path
                print(f'{rel}: {n_hrefs} hrefs, {status}')
            for e in errs:
                print(f'  {e}')
            total_errors += len(errs)
    finally:
        if pool:
            pool.terminate()

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
