#!/usr/bin/env python3
"""Regenerate userdata/website/index.html from per-dive and article meta.toml files.

Scans userdata/website/*/meta.toml for deep dives and
userdata/website/articles/*/meta.toml for articles. Emits a single
landing page with separate sections for each content type.

Dive/article metadata schema (per subdir ``meta.toml``):

    title       = "Tinkaton - Great League IV Deep Dive"
    description = "Free text, can be multi-line."
    landing     = "tinkaton_gl_toml.html"   # relative to the subdir

Deleting a subdir automatically removes its index entry next run. The
script is idempotent; re-running without adding anything writes the
same bytes.

Usage:
    python scripts/build_website_index.py
"""
from __future__ import annotations

import html
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'
ARTICLES_DIR = WEBSITE_DIR / 'articles'
INDEX_PATH = WEBSITE_DIR / 'index.html'


def load_entries(base_dir: Path, *, href_prefix: str = '') -> list[dict]:
    """Return one dict per valid subdir with a meta.toml, sorted by title."""
    if not base_dir.exists():
        return []
    entries = []
    for sub in sorted(base_dir.iterdir()):
        if not sub.is_dir():
            continue
        meta_path = sub / 'meta.toml'
        if not meta_path.exists():
            print(f"  skip {sub.name}/: no meta.toml", file=sys.stderr)
            continue
        with open(meta_path, 'rb') as f:
            meta = tomllib.load(f)
        missing = [k for k in ('title', 'description', 'landing')
                   if k not in meta]
        if missing:
            print(f"  skip {sub.name}/: meta.toml missing {missing}",
                  file=sys.stderr)
            continue
        landing_path = sub / meta['landing']
        if not landing_path.exists():
            print(f"  skip {sub.name}/: landing file "
                  f"{meta['landing']!r} does not exist",
                  file=sys.stderr)
            continue
        entries.append({
            'slug': sub.name,
            'title': meta['title'],
            'description': meta['description'].strip(),
            'landing': meta['landing'],
            'href': f"{href_prefix}{sub.name}/{meta['landing']}",
        })
    entries.sort(key=lambda d: d['title'].lower())
    return entries


def _render_entry_list(entries: list[dict], empty_msg: str) -> str:
    items = []
    for d in entries:
        items.append(
            '  <li class="dive">\n'
            f'    <a href="{html.escape(d["href"])}">'
            f'<b>{html.escape(d["title"])}</b></a>\n'
            f'    <p>{html.escape(d["description"])}</p>\n'
            '  </li>'
        )
    if not items:
        items.append(f'  <li><i>{html.escape(empty_msg)}</i></li>')
    return '\n'.join(items)


def render_index(dives: list[dict], articles: list[dict]) -> str:
    dives_html = _render_entry_list(dives, 'No dives published yet.')
    articles_html = _render_entry_list(articles, 'No articles published yet.')

    articles_section = ''
    if articles:
        articles_section = (
            '\n<h2>Articles</h2>\n'
            '<ul>\n'
            f'{articles_html}\n'
            '</ul>\n'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Pokemon Go PvP Deep Dives</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
         sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px;
         background: #1a1a2e; color: #e0e0e0; line-height: 1.5; }}
  h1 {{ color: #e94560; }}
  h2 {{ color: #c8a2d0; border-bottom: 1px solid #0f3460;
        padding-bottom: 6px; }}
  a {{ color: #9be89b; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  ul {{ list-style: none; padding: 0; }}
  li.dive {{ background: #16213e; padding: 14px 18px; border-radius: 6px;
             margin-bottom: 14px; }}
  li.dive p {{ margin: 6px 0 0 0; color: #aaa; font-size: 14px; }}
  .about {{ color: #888; font-size: 13px; margin-top: 30px;
            border-top: 1px solid #0f3460; padding-top: 12px; }}
</style>
</head>
<body>
<h1>Pokemon Go PvP Deep Dives</h1>
<p>Interactive IV / moveset deep dives generated from a homebrew battle
simulator that matches PvPoke's simulate-mode scores. Click a title to
open the dive. Each page is self-contained and runs in your browser.</p>
<h2>Deep Dives</h2>
<ul>
{dives_html}
</ul>
{articles_section}
<p class="about">Built with <a href="https://github.com/pvpoke/pvpoke">PvPoke</a>
game data. If you find something broken or surprising, email me.</p>
</body>
</html>
"""


def main() -> int:
    if not WEBSITE_DIR.exists():
        print(f"error: {WEBSITE_DIR} does not exist", file=sys.stderr)
        return 1
    dives = load_entries(WEBSITE_DIR)
    articles = load_entries(ARTICLES_DIR, href_prefix='articles/')
    index_html = render_index(dives, articles)
    INDEX_PATH.write_text(index_html)
    print(f"Wrote {INDEX_PATH} ({len(dives)} dive(s), {len(articles)} article(s))")
    for d in dives:
        print(f"  - [dive] {d['title']} -> {d['href']}")
    for a in articles:
        print(f"  - [article] {a['title']} -> {a['href']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
