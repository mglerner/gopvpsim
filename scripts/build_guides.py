#!/usr/bin/env python3
"""Regenerate userdata/website/guides/ from guides/ source templates.

Reader's-guide pipeline. Source tree:

    guides/
      index.toml                 # landing page metadata + intro body
      <slug>/
        guide.toml               # per-guide metadata
        body.md                  # hand-authored markdown with {{tokens}}
        screenshots/             # optional, source-tracked, compressed

Output tree (gitignored, rebuilt every run):

    userdata/website/guides/
      index.html
      meta.toml
      <slug>/
        index.html
        meta.toml
        figures/                 # auto-generated figures (e.g. Plotly)
        screenshots/             # copied from source

A guide with ``coming_soon = true`` in its ``guide.toml`` renders a
stub page and shows as "coming soon" on the landing page, so the
navigation shape lands with the first ship even when content lags.

Token resolution: ``body.md`` may contain ``{{token_name}}``
placeholders. Tokens declared in ``[tokens]`` of the guide's TOML
(scalar strings) are resolved verbatim. Data-derived tokens prefixed
``dive:`` are resolved against the reference-dive data object (see
``_resolve_dive_token``); the reference dive is chosen via
``reference_species`` / ``reference_league`` keys in the guide's TOML,
or falls back to ``DEFAULT_REFERENCE`` below.

Idempotent: re-running without source changes produces the same bytes
on disk.

Usage:
    python scripts/build_guides.py
"""
from __future__ import annotations

import html
import shutil
import sys
import tomllib
from pathlib import Path

import markdown  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDES_SRC = REPO_ROOT / 'guides'
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'
GUIDES_OUT = WEBSITE_DIR / 'guides'

# Reference dive used for data-token resolution when a guide TOML
# doesn't override. Oinkologne Male GL matches the shipping CD so
# readers can click through and see the same numbers.
DEFAULT_REFERENCE = {
    'species': 'Oinkologne',
    'league': 'great',
    'dive_slug': 'oinkologne-great-league',
}


# --------------------------------------------------------------------
# Reference-dive data access
# --------------------------------------------------------------------

def _dive_data(dive_slug: str) -> dict | None:
    """Return the parsed dive DATA for the main index.html, or None.

    Uses generate_article's _load_dive_data helper so the dict shape
    matches what auto_gen_narrative consumes - makes future data-token
    resolvers drop-in without re-parsing.
    """
    sys.path.insert(0, str(REPO_ROOT / 'scripts'))
    sys.path.insert(0, str(REPO_ROOT / 'src'))
    from generate_article import _load_dive_data  # type: ignore[import-not-found]
    dive_dir = WEBSITE_DIR / dive_slug
    if not dive_dir.is_dir():
        return None
    try:
        return _load_dive_data(dive_dir)
    except SystemExit:
        return None


# --------------------------------------------------------------------
# Token resolution
# --------------------------------------------------------------------

def _resolve_tokens(
    body: str,
    guide_tokens: dict,
    *,
    dive: dict | None,
    guide_slug: str,
) -> tuple[str, list[str]]:
    """Replace ``{{token}}`` placeholders. Returns (resolved, unresolved).

    Resolution order:
      1. Literal scalar entries in ``[tokens]`` of the guide TOML.
      2. ``dive:`` prefixed tokens resolved via ``_resolve_dive_token``.
      3. Otherwise the placeholder is left intact and its name is
         appended to the unresolved list for the caller to warn on.
    """
    import re as _re
    unresolved: list[str] = []

    def _replace(match: '_re.Match[str]') -> str:
        name = match.group(1).strip()
        if name in guide_tokens and isinstance(guide_tokens[name], (str, int, float)):
            return str(guide_tokens[name])
        if name.startswith('dive:'):
            val = _resolve_dive_token(name[len('dive:'):], dive)
            if val is not None:
                return val
        unresolved.append(f'{guide_slug}:{name}')
        return match.group(0)

    resolved = _re.sub(r'\{\{\s*([^}]+?)\s*\}\}', _replace, body)
    return resolved, unresolved


def _resolve_dive_token(suffix: str, dive: dict | None) -> str | None:
    """Resolve a ``dive:<suffix>`` token against the reference dive.

    v1 vocabulary (extend as guides land):
      - ``species_display``: pretty species label from the first moveset.
      - ``moveset_count``: count of movesets in the dive.
      - ``opponent_count``: count of opponents scored.

    Returns None when the dive is missing or the token isn't known.
    """
    if dive is None:
        return None
    if suffix == 'species_display':
        movesets = dive.get('movesets') or []
        for m in movesets:
            label = (m.get('pretty_label') or m.get('label') or '').strip()
            if label:
                return label.split('/', 1)[0].strip().title()
        return None
    if suffix == 'moveset_count':
        return str(len(dive.get('movesets') or []))
    if suffix == 'opponent_count':
        return str(len(dive.get('opponents') or []))
    return None


# --------------------------------------------------------------------
# Markdown -> HTML
# --------------------------------------------------------------------

def _render_markdown(body: str) -> str:
    return markdown.markdown(
        body,
        extensions=['extra', 'sane_lists', 'smarty'],
        output_format='html5',
    )


# --------------------------------------------------------------------
# Stylesheet + page shell
# --------------------------------------------------------------------

_GUIDE_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
       sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px;
       background: #1a1a2e; color: #e0e0e0; line-height: 1.6; }
h1 { color: #e94560; }
h2 { color: #c8a2d0; border-bottom: 1px solid #0f3460;
     padding-bottom: 6px; margin-top: 32px; }
h3 { color: #c8a2d0; margin-top: 24px; }
a { color: #9be89b; text-decoration: none; }
a:hover { text-decoration: underline; }
code { background: #16213e; padding: 2px 6px; border-radius: 3px;
       font-size: 0.92em; }
ul, ol { padding-left: 22px; }
li { margin: 4px 0; }
figure { margin: 20px 0; }
figcaption { color: #aaa; font-size: 14px; margin-top: 8px;
             font-style: italic; }
.coming-soon { background: #16213e; padding: 20px; border-radius: 6px;
               border-left: 3px solid #d29922; color: #ccc; }
.breadcrumb { color: #888; font-size: 14px; margin-bottom: 20px; }
.breadcrumb a { color: #9be89b; }
.guide-list { list-style: none; padding: 0; }
.guide-list li { background: #16213e; padding: 14px 18px;
                 border-radius: 6px; margin-bottom: 14px; }
.guide-list li p { margin: 6px 0 0 0; color: #aaa; font-size: 14px; }
.guide-list li.coming-soon-entry a { color: #888; cursor: not-allowed; }
.guide-list li.coming-soon-entry .badge {
    font-size: 12px; color: #d29922; margin-left: 8px; }
.about { color: #888; font-size: 13px; margin-top: 40px;
         border-top: 1px solid #0f3460; padding-top: 12px; }
"""


def _render_page(*, title: str, body_html: str,
                 breadcrumb_html: str = '') -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{_GUIDE_CSS}</style>
</head>
<body>
{breadcrumb_html}
{body_html}
<p class="about">Part of <a href="../../">the PvP deep dive site</a>.
Explainers regenerate from current dive data every publish, so numbers
stay in sync with the methodology.</p>
</body>
</html>
"""


# --------------------------------------------------------------------
# Per-guide build
# --------------------------------------------------------------------

def _load_guide(sub: Path) -> dict | None:
    toml_path = sub / 'guide.toml'
    if not toml_path.is_file():
        return None
    with open(toml_path, 'rb') as f:
        data = tomllib.load(f)
    data['_src_dir'] = sub
    return data


def _build_guide(guide: dict,
                 *, total_unresolved: list[str]) -> dict:
    src_dir: Path = guide['_src_dir']
    slug = guide.get('slug') or src_dir.name
    title = guide.get('title') or slug.replace('-', ' ').title()
    description = guide.get('description') or ''
    coming_soon = bool(guide.get('coming_soon'))

    out_dir = GUIDES_OUT / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Body: markdown file, or "coming soon" placeholder.
    body_md_path = src_dir / 'body.md'
    if coming_soon or not body_md_path.is_file():
        body_html = (
            '<div class="coming-soon">'
            f'<strong>Coming soon:</strong> {html.escape(description)}'
            '</div>'
        )
    else:
        body_md = body_md_path.read_text()
        tokens = guide.get('tokens') or {}
        ref = {
            'species': guide.get('reference_species')
                       or DEFAULT_REFERENCE['species'],
            'league': guide.get('reference_league')
                      or DEFAULT_REFERENCE['league'],
            'dive_slug': guide.get('reference_dive_slug')
                         or DEFAULT_REFERENCE['dive_slug'],
        }
        dive = _dive_data(ref['dive_slug'])
        resolved_body, unresolved = _resolve_tokens(
            body_md, tokens, dive=dive, guide_slug=slug)
        total_unresolved.extend(unresolved)
        body_html = _render_markdown(resolved_body)

    # Copy any source-tracked screenshots so the rendered guide can
    # reference them as "screenshots/<name>".
    src_shots = src_dir / 'screenshots'
    if src_shots.is_dir():
        dest = out_dir / 'screenshots'
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src_shots, dest)

    breadcrumb = (
        '<p class="breadcrumb">'
        '<a href="../../">Home</a> / '
        '<a href="../">Reader\'s Guide</a> / '
        f'{html.escape(title)}</p>'
    )
    page_html = _render_page(
        title=f'{title} - Reader\'s Guide',
        body_html=f'<h1>{html.escape(title)}</h1>\n{body_html}',
        breadcrumb_html=breadcrumb,
    )
    (out_dir / 'index.html').write_text(page_html)

    # Per-guide meta.toml for the site-index builder.
    meta_out = (
        f'title = "{_toml_escape(title)}"\n'
        f'description = "{_toml_escape(description)}"\n'
        'landing = "index.html"\n'
    )
    (out_dir / 'meta.toml').write_text(meta_out)

    return {
        'slug': slug,
        'title': title,
        'description': description,
        'coming_soon': coming_soon,
        'order': int(guide.get('order') or 999),
    }


def _toml_escape(s: str) -> str:
    # Basic TOML string escape. meta.toml is machine-read only, so we
    # don't need full quoting - just protect against " and \.
    return s.replace('\\', '\\\\').replace('"', '\\"')


# --------------------------------------------------------------------
# Landing page
# --------------------------------------------------------------------

def _build_landing(index_meta: dict, guides: list[dict]) -> None:
    title = index_meta.get('title') or 'Reader\'s Guide'
    description = index_meta.get('description') or ''
    intro_md = index_meta.get('body') or ''
    intro_html = _render_markdown(intro_md) if intro_md else ''

    guides_sorted = sorted(guides, key=lambda g: (g['order'], g['slug']))
    items: list[str] = []
    for g in guides_sorted:
        cls = 'coming-soon-entry' if g['coming_soon'] else ''
        title_html = html.escape(g['title'])
        desc_html = html.escape(g['description'])
        badge = ('<span class="badge">coming soon</span>'
                 if g['coming_soon'] else '')
        if g['coming_soon']:
            link = f'<span>{title_html}</span>{badge}'
        else:
            link = f'<a href="{g["slug"]}/">{title_html}</a>'
        items.append(
            f'<li class="{cls}">{link}'
            + (f'<p>{desc_html}</p>' if desc_html else '')
            + '</li>'
        )
    items_html = '\n'.join(items) if items else '<li>No guides yet.</li>'

    body_html = (
        f'<h1>{html.escape(title)}</h1>\n'
        f'{intro_html}\n'
        f'<ul class="guide-list">\n{items_html}\n</ul>'
    )
    breadcrumb = '<p class="breadcrumb"><a href="../">Home</a> / Reader\'s Guide</p>'
    page = _render_page(
        title='Reader\'s Guide',
        body_html=body_html,
        breadcrumb_html=breadcrumb,
    )
    GUIDES_OUT.mkdir(parents=True, exist_ok=True)
    (GUIDES_OUT / 'index.html').write_text(page)

    meta_out = (
        f'title = "{_toml_escape(title)}"\n'
        f'description = "{_toml_escape(description)}"\n'
        'landing = "index.html"\n'
    )
    (GUIDES_OUT / 'meta.toml').write_text(meta_out)


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------

def main() -> int:
    if not GUIDES_SRC.is_dir():
        print(f'error: {GUIDES_SRC} does not exist', file=sys.stderr)
        return 1

    index_toml_path = GUIDES_SRC / 'index.toml'
    if index_toml_path.is_file():
        with open(index_toml_path, 'rb') as f:
            index_meta = tomllib.load(f)
    else:
        index_meta = {}

    guides_built: list[dict] = []
    total_unresolved: list[str] = []
    for sub in sorted(p for p in GUIDES_SRC.iterdir() if p.is_dir()):
        g = _load_guide(sub)
        if g is None:
            continue
        built = _build_guide(g, total_unresolved=total_unresolved)
        guides_built.append(built)

    _build_landing(index_meta, guides_built)

    if total_unresolved:
        print('warning: unresolved tokens:', file=sys.stderr)
        for t in total_unresolved:
            print(f'  {t}', file=sys.stderr)

    print(f'Wrote {GUIDES_OUT}/index.html '
          f'({len(guides_built)} guide(s))')
    for g in guides_built:
        tag = '  [coming-soon]' if g['coming_soon'] else ''
        print(f"  - {g['title']} -> {g['slug']}/{tag}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
