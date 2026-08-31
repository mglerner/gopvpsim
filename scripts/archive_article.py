#!/usr/bin/env python
"""Archive a rendered article as a dated, immutable snapshot.

Pattern (decided 2026-08-31; full rationale in
``docs/article_archive_plan.md``): the BARE slug is always the current
article, so every inbound link keeps working and always lands on live
data. Archiving COPIES the current render to a vintage-stamped slug and
marks the copy; the bare slug is then regenerated in place by the
normal article pipeline.

    articles/clodsire-equinox-cup              always current
    articles/clodsire-equinox-cup-2026-08-31   frozen snapshot

That is what lets the same cup recur across seasons with a move
rebalance in between: next season regenerates the bare slug and files
another stamped copy beside the first.

``--vintage`` is REQUIRED and never guessed. Archiving happens AFTER the
new data has landed, so the live gamemaster stamp at archive time is the
NEW one -- defaulting to it would label the snapshot with data it was
not built on. The operator states what the article was built on.

Usage:
    archive_article.py --slug cramorant-pogodives-strategy \\
        --vintage 2026-08-31 --stamp c431557dcc76
    archive_article.py --slug ... --vintage ... --dry-run
"""
import argparse
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = REPO_ROOT / 'userdata' / 'website' / 'articles'

VINTAGE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
STAMP_RE = re.compile(r'^[0-9a-f]{12}$')

# Written verbatim into the archived copy's meta.toml. build_website_index
# reads it back to route the entry into the collapsed Archive block.
ARCHIVE_BLOCK = """
[archive]
# Written by scripts/archive_article.py -- this directory is a frozen
# snapshot. The bare slug {of!r} carries the current version.
of      = "{of}"
vintage = "{vintage}"
{stamp_line}"""


def archive_slug(slug, vintage, stamp=None, articles_dir=ARTICLES_DIR,
                 force=False, dry_run=False, out=sys.stdout):
    """Copy ``slug`` to ``<slug>-<vintage>`` and mark the copy archived.

    Returns the destination Path. Raises SystemExit(2) with a specific
    message on any precondition failure -- this runs by hand at a
    moment (mid-rebalance) when a silent half-done archive would be
    worse than a refusal.
    """
    if ('/' in slug or os.sep in slug or slug in ('', '.', '..')):
        # A trailing slash is what shell tab-completion produces. Path()
        # normalizes it for is_dir(), but f'{slug}-{vintage}' would yield
        # '<slug>/-<vintage>' -- a nested dir that load_entries (depth-1)
        # cannot see, so it is invisible to the index AND to the
        # dropped_pages guard, while ship_surfaces' rglob still rsyncs it
        # live. Refuse rather than silently publish an unreachable page.
        raise SystemExit(
            f'error: --slug must be a bare directory name, got {slug!r}')
    if not VINTAGE_RE.match(vintage):
        raise SystemExit(f'error: --vintage must be YYYY-MM-DD, got {vintage!r}')
    if stamp is not None and not STAMP_RE.match(stamp):
        raise SystemExit(
            f'error: --stamp must be 12 lowercase hex chars (the sweep_cache '
            f'v7 narrow gamemaster hash), got {stamp!r}')

    src = articles_dir / slug
    if not src.is_dir():
        raise SystemExit(f'error: no such article directory: {src}')
    meta_path = src / 'meta.toml'
    if not meta_path.exists():
        raise SystemExit(
            f'error: {slug}/ has no meta.toml. Only articles with an authored '
            f'meta.toml can be archived -- an HTML-title-fallback entry would '
            f'lose its identity in the copy.')
    meta_text = meta_path.read_text()
    try:
        meta = tomllib.loads(meta_text)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f'error: {slug}/meta.toml is not valid TOML: {e}')
    if 'archive' in meta:
        raise SystemExit(
            f'error: {slug}/ is already an archived snapshot (its meta.toml '
            f'carries [archive]). Archive the CURRENT article at the bare '
            f'slug, not a snapshot.')

    dest = articles_dir / f'{slug}-{vintage}'
    if dest.exists():
        if not force:
            raise SystemExit(
                f'error: {dest.name}/ already exists. Refusing to overwrite an '
                f'existing snapshot -- pass --force only if you are certain it '
                f'is wrong.')
        if not dry_run:
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

    stamp_line = f'stamp   = "{stamp}"\n' if stamp else ''
    block = ARCHIVE_BLOCK.format(of=slug, vintage=vintage,
                                 stamp_line=stamp_line)

    print(f'archive {slug}/ -> {dest.name}/', file=out)
    print(f'  vintage {vintage}' + (f'  stamp {stamp}' if stamp else ''),
          file=out)
    if dry_run:
        print('  (dry run -- nothing written)', file=out)
        return dest

    new_meta = meta_text.rstrip('\n') + '\n' + block
    try:
        tomllib.loads(new_meta)
    except tomllib.TOMLDecodeError as e:
        # The block is appended as text (no TOML writer dependency), so a slug
        # needing escapes would corrupt the document. Fail before copying.
        raise SystemExit(
            f'error: appending the [archive] block would produce invalid '
            f'TOML ({e}). Slug {slug!r} likely needs escaping.')
    shutil.copytree(src, dest)
    (dest / 'meta.toml').write_text(new_meta)
    print(f'  wrote {dest / "meta.toml"}', file=out)
    print(f'  the bare slug {slug}/ is untouched -- regenerate it, or delete '
          f'it if the article is not coming back', file=out)
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--slug', required=True,
                    help='article directory under userdata/website/articles/')
    ap.add_argument('--vintage', required=True,
                    help='YYYY-MM-DD of the DATA the article was built on '
                         '(not today) -- never guessed, see the module docstring')
    ap.add_argument('--stamp', default=None,
                    help='optional sweep_cache v7 narrow gamemaster hash '
                         '(12 hex chars)')
    ap.add_argument('--articles-dir', default=None, type=Path,
                    help=argparse.SUPPRESS)
    ap.add_argument('--force', action='store_true',
                    help='overwrite an existing snapshot directory')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)
    archive_slug(args.slug, args.vintage, stamp=args.stamp,
                 articles_dir=args.articles_dir or ARTICLES_DIR,
                 force=args.force, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
