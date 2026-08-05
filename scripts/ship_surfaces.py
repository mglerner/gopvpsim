"""Single source for "every user-facing HTML the publish rsync ships".

publish_website.sh rsyncs the WHOLE userdata/website/ tree (--delete),
so every ship gate must enumerate the same surface set. This module is
that enumeration; verify_article_links.py and verify_no_unicode_dashes.py
both import it (they used to carry byte-identical private copies, and
both missed root-level pages other than index.html -- cups.html and
support.html shipped with zero checks; DRY review 2026-08-05 entry 3a).

Enumerated from the site tree rather than a hardcoded list: the old
frozen Oinkologne-era set silently decayed as new dives, articles, and
guides shipped (2026-06-11 review, W9).
"""
from pathlib import Path

# Containers whose whole subtree is user-facing (vs dive dirs, where only
# the landing + split-moveset pages ship as entry points).
DEEP_CONTAINERS = ('articles', 'comparisons', 'guides')


def find_ship_surfaces(website_dir: Path) -> list:
    """Every user-facing HTML file under ``website_dir``.

    - ALL root-level ``*.html`` (index.html, cups.html, support.html,
      and anything added later -- root pages ship, so root pages gate);
    - the full ``index*.html`` subtree of the deep containers;
    - each dive dir's ``index.html`` + ``index_m*.html`` split pages.
    """
    website_dir = Path(website_dir)
    surfaces = list(sorted(website_dir.glob('*.html')))
    for sub in sorted(website_dir.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in DEEP_CONTAINERS:
            surfaces.extend(sorted(sub.rglob('index*.html')))
        else:
            # Dive dirs: landing page + split-moveset pages.
            surfaces.extend(sorted(sub.glob('index.html')))
            surfaces.extend(sorted(sub.glob('index_m*.html')))
    return [s for s in surfaces if s.exists()]
