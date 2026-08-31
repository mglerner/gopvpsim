#!/usr/bin/env python
"""Widen the sticky sidebar nav in already-rendered ML IV-guide HTML so the
recommended-table sub-nav labels stop wrapping.

The canonical fix is the renderer CSS (nav.toc flex 190px -> 260px); a fresh
render picks it up automatically. This patcher exists only for guide HTML that
was rendered BEFORE that change and won't be re-rendered. It is an exact-string
CSS swap, so it is idempotent (a no-op on already-current files) and safe to run
any time, including after a batch finishes.

Usage:
  python scripts/patch_iv_guide_nav_width.py            # all guides under userdata/website
  python scripts/patch_iv_guide_nav_width.py PATH ...   # specific index.html files
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = 'flex:0 0 190px'
NEW = 'flex:0 0 260px'


def targets(argv):
    if argv:
        return argv
    # Exact suffixes only. A bare '*-ml-iv-guide*' also matches the dated
    # archive snapshots ('florges-ml-iv-guide-2026-08-31'), and this script
    # is documented as safe to run any time -- it must not rewrite HTML that
    # is frozen by design. See docs/article_archive_plan.md.
    base = os.path.join(ROOT, 'userdata', 'website', 'articles')
    return (glob.glob(os.path.join(base, '*-ml-iv-guide', 'index.html'))
            + glob.glob(os.path.join(base, '*-ml-iv-guide-even', 'index.html')))


def main():
    files = targets(sys.argv[1:])
    patched = already = skipped = 0
    for path in files:
        try:
            html = open(path).read()
        except OSError:
            skipped += 1
            continue
        if OLD in html:
            open(path, 'w').write(html.replace(OLD, NEW))
            patched += 1
            print(f'patched  {os.path.relpath(path, ROOT)}')
        elif NEW in html:
            already += 1
        else:
            skipped += 1
            print(f'skip (no nav width found)  {os.path.relpath(path, ROOT)}')
    print(f'\n{len(files)} file(s): {patched} patched, {already} already current, '
          f'{skipped} skipped.')


if __name__ == '__main__':
    main()
