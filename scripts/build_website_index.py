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
COMPARISONS_DIR = WEBSITE_DIR / 'comparisons'
INDEX_PATH = WEBSITE_DIR / 'index.html'


_LEAGUE_SUFFIXES = {
    'great-league': 'Great League',
    'ultra-league': 'Ultra League',
    'master-league': 'Master League',
}


def _slug_to_pretty_title(slug: str) -> str:
    """Convert a dive dir slug to a human-readable title.

    Pattern: ``{species}-[{variant}-]*{league}-league``. Splits off the
    trailing ``-great-league`` / ``-ultra-league`` / ``-master-league``
    as the league suffix; everything before that is the species +
    variant tokens (shadow flag, moveset id, form name, etc.).

    Example inputs → outputs:
      ``oinkologne-great-league`` → ``"Oinkologne (Great League)"``
      ``oinkologne-female-great-league`` → ``"Oinkologne (Female) (Great League)"``
      ``forretress-shadow-bug-bite-great-league`` →
          ``"Forretress Shadow Bug Bite (Great League)"``
      ``aegislash-blade-ultra-league`` → ``"Aegislash Blade (Ultra League)"``

    Returns empty string when the slug doesn't match the pattern (no
    league suffix) — caller falls back to the HTML title.
    """
    for suffix, pretty in _LEAGUE_SUFFIXES.items():
        if slug.endswith('-' + suffix):
            core = slug[:-(len(suffix) + 1)]  # strip "-great-league" etc.
            # Special-case the (form) parenthetical: species names
            # containing a form suffix (Oinkologne female, Aegislash
            # blade/shield) were slugified with dashes; recompose with
            # the form token parenthesised.
            tokens = [t.capitalize() for t in core.split('-')]
            # Heuristic: common form-suffix tokens get parenthesised
            # right after the species name. Matches the dive HTML
            # `<title>` convention (e.g. "Oinkologne (Female)").
            form_tokens = {'Female', 'Blade', 'Shield', 'Alolan',
                           'Galarian', 'Hisuian'}
            parts = [tokens[0]] if tokens else []
            i = 1
            while i < len(tokens) and tokens[i] in form_tokens:
                parts.append(f'({tokens[i]})')
                i += 1
            # Rest of the tokens are variant descriptors (shadow flag,
            # moveset words). Capitalise and join.
            if i < len(tokens):
                parts.append(' '.join(tokens[i:]))
            species_plus_variant = ' '.join(parts).strip()
            return f'{species_plus_variant} ({pretty})'
    return ''


def _fallback_meta_from_html(sub: Path) -> dict | None:
    """Derive ({title, description, landing}) by scanning the dir's index.html.

    Called when ``meta.toml`` is absent — lets freshly-generated deep
    dives appear on the index without deep_dive.py needing to emit a
    separate meta.toml alongside the HTML. Title comes from the slug
    (parsed into species + form + variant + league) when the slug
    shape is recognisable; falls back to the HTML ``<title>`` tag
    otherwise. Slug-based titling disambiguates Forretress-style
    multi-variant dirs that all share the same HTML ``<title>``.

    Returns None when the dir has no index.html (nothing to surface).
    """
    index_path = sub / 'index.html'
    if not index_path.exists():
        return None
    title = _slug_to_pretty_title(sub.name)
    if not title:
        # Slug didn't match the expected pattern; try the HTML title.
        try:
            head = index_path.read_text(errors='replace')[:8192]
        except Exception:
            return None
        import re as _re
        m = _re.search(r'<title>\s*([^<]+?)\s*</title>', head,
                       _re.IGNORECASE)
        if not m:
            return None
        title = m.group(1).strip()
    # Default description for auto-discovered dives. Good enough for
    # the landing page; curate by authoring a real meta.toml when the
    # dive deserves a richer blurb.
    description = ('Interactive IV / moveset deep dive. '
                   'Per-opponent matchup data, IV-tier recommendations, '
                   'and a scatter plot of 4,096 IVs by stat product.')
    return {
        'title': title,
        'description': description,
        'landing': 'index.html',
        '_fallback': True,  # debug only; stripped before use
    }


def load_entries(base_dir: Path, *, href_prefix: str = '') -> list[dict]:
    """Return one dict per valid subdir, sorted by title.

    Prefers ``meta.toml`` (authored schema) when present; falls back
    to deriving title + landing from the dir's ``index.html`` for
    dives that don't carry a meta.toml yet. Dirs with neither are
    skipped.
    """
    if not base_dir.exists():
        return []
    entries = []
    for sub in sorted(base_dir.iterdir()):
        if not sub.is_dir():
            continue
        meta_path = sub / 'meta.toml'
        meta: dict | None = None
        if meta_path.exists():
            with open(meta_path, 'rb') as f:
                meta = tomllib.load(f)
            missing = [k for k in ('title', 'description', 'landing')
                       if k not in meta]
            if missing:
                print(f"  skip {sub.name}/: meta.toml missing {missing}",
                      file=sys.stderr)
                continue
        else:
            meta = _fallback_meta_from_html(sub)
            if meta is None:
                print(f"  skip {sub.name}/: no meta.toml and no index.html "
                      f"title to fall back on", file=sys.stderr)
                continue
        landing_path = sub / meta['landing']
        if not landing_path.exists():
            # Fall back to index.html when the authored meta.toml points
            # at a stale filename (previous naming convention, renamed
            # after a re-dive, etc.). Keeps the curated title +
            # description while pointing at whatever landing the dive
            # currently emits.
            default_landing = sub / 'index.html'
            if default_landing.exists():
                print(f"  note {sub.name}/: meta.toml landing "
                      f"{meta['landing']!r} is stale, "
                      f"falling back to index.html",
                      file=sys.stderr)
                meta['landing'] = 'index.html'
                landing_path = default_landing
            else:
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


def render_index(dives: list[dict],
                 articles: list[dict],
                 comparisons: list[dict]) -> str:
    dives_html = _render_entry_list(dives, 'No dives published yet.')
    articles_html = _render_entry_list(articles, 'No articles published yet.')
    comparisons_html = _render_entry_list(comparisons, 'No comparisons published yet.')

    articles_section = ''
    if articles:
        articles_section = (
            '\n<h2>Articles</h2>\n'
            '<ul>\n'
            f'{articles_html}\n'
            '</ul>\n'
        )

    comparisons_section = ''
    if comparisons:
        comparisons_section = (
            '\n<h2>Comparisons</h2>\n'
            '<ul>\n'
            f'{comparisons_html}\n'
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
{articles_section}{comparisons_section}
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
    comparisons = load_entries(COMPARISONS_DIR, href_prefix='comparisons/')
    index_html = render_index(dives, articles, comparisons)
    INDEX_PATH.write_text(index_html)
    print(f"Wrote {INDEX_PATH} ({len(dives)} dive(s), "
          f"{len(articles)} article(s), {len(comparisons)} comparison(s))")
    for d in dives:
        print(f"  - [dive] {d['title']} -> {d['href']}")
    for a in articles:
        print(f"  - [article] {a['title']} -> {a['href']}")
    for c in comparisons:
        print(f"  - [comparison] {c['title']} -> {c['href']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
