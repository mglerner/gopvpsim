#!/usr/bin/env python3
"""Render an EXPERT-authored CD article TOML into a self-contained HTML page.

This renderer is ONLY for articles with ``authorship = "expert"`` — it
emits the TOML's ``[[sections]]`` verbatim with minimal framing. For
``authorship = "auto"`` or ``"both"`` (data-driven articles), use
``scripts/generate_article.py`` instead; it renders the full article
with stats tables, meta coverage grids, matchup deltas, etc., reading
from the per-species dive data.

Running this script against a non-expert article will clobber a
richer previously-rendered HTML with a placeholder-only skeleton;
``main()`` guards against that by refusing to run.

Usage:
    python scripts/render_article.py articles/<expert-slug>.toml

Output lands in userdata/website/articles/<slug>/ with:
  - index.html  (the article page)
  - meta.toml   (for the site-index builder)

Schema: docs/article_schema.md
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'
ARTICLES_DIR = WEBSITE_DIR / 'articles'

sys.path.insert(0, str(REPO_ROOT / 'src'))
from gopvpsim.attribution import PVPOKE_ATTRIBUTION_HTML  # noqa: E402  # type: ignore[import-not-found]


def load_article(path: Path) -> dict:
    with open(path, 'rb') as f:
        data = tomllib.load(f)
    required = ['title', 'species', 'cd_date', 'author', 'description',
                'cd_move', 'framing', 'authorship', 'obsolescence', 'links',
                'sections']
    missing = [k for k in required if k not in data]
    if missing:
        sys.exit(f"Article TOML missing required fields: {missing}")
    if data['obsolescence'].get('status') not in ('current', 'obsolete'):
        sys.exit("obsolescence.status must be 'current' or 'obsolete'")
    if not data['sections']:
        sys.exit("Article must have at least one [[sections]] entry")
    return data


def format_body(text: str) -> str:
    """Minimal text formatting: paragraphs, bold, italic, code."""
    text = text.strip()
    paragraphs = re.split(r'\n\s*\n', text)
    result = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        p = html.escape(p)
        p = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p)
        p = re.sub(r'\*(.+?)\*', r'<em>\1</em>', p)
        p = re.sub(r'`(.+?)`', r'<code>\1</code>', p)
        result.append(f'<p>{p}</p>')
    return '\n'.join(result)


def authored_by_class(block: dict) -> str:
    """Map the optional ``authored_by`` enum to a CSS modifier class.

    Values: ``"human"`` (default, gold), ``"ai"`` (orange),
    ``"mixed"`` (gold — a human co-signed so treat as human register),
    ``"auto"`` (blue — deterministically data-derived from dive data
    by ``scripts/auto_gen_narrative.py``; not human-reviewed and
    not LLM-drafted). Unknown or missing values fall back to
    ``"human"``. The returned string is always one of
    ``authored-human``, ``authored-ai``, ``authored-mixed``,
    ``authored-auto`` (never empty); callers concatenate it into a
    space-separated class list.

    The enum is explicit because the free-form ``author`` string is
    too fragile to color-code via substring matching ("Drafted by
    Claude, not yet human-reviewed" vs "Drafted by Claude, reviewed
    by Michael" read as different provenance even though both contain
    "Claude").
    """
    val = (block.get('authored_by') or 'human').strip().lower()
    if val not in {'human', 'ai', 'mixed', 'auto'}:
        val = 'human'
    return f'authored-{val}'


# Shared sidebar pattern CSS fragment (2026-04-19 refactor, mirrors the
# dive-side pattern in deep_dive_rendering.py DEEP_DIVE_CSS).
#
# Any element whose class appears in the SIDEBAR_SELECTORS list below
# gets a rounded-cap ::before pseudo-element bar on its left edge
# instead of a hand-written border-left. Each class sets its own
# --sidebar-color (and optional --sidebar-width, default 3px) and
# drops its `border-left` declaration. Adjust left-padding to roughly
# (old value + 4px) so text keeps a visible gap from the bar.
#
# The article-side pattern uses 3px default width (matching the
# existing 3px solid borders we're replacing). Dive-side uses 4px;
# the two pages are allowed to differ stylistically.
#
# This string is substituted via .format(selectors_base=..., selectors_before=...)
# where each file passes its own comma-separated selector list.
SIDEBAR_CSS_TEMPLATE = """
/* ==== Shared sidebar pattern (2026-04-19 refactor) ==== */
{selectors_base} {{
  position: relative;
  border-left: none;
}}
{selectors_before} {{
  content: "";
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: var(--sidebar-width, 3px);
  border-radius: calc(var(--sidebar-width, 3px) / 2);
  background: var(--sidebar-color, #8b949e);
}}
"""


def sidebar_css(selectors: list[str]) -> str:
    """Return the shared sidebar ::before CSS block for the given class list.

    ``selectors`` is a list of full CSS selectors (e.g.
    ``['.related', 'div.key-flips', 'details.methodology-details']``).
    The template emits a grouped rule that zeroes each element's
    border-left and gives them ``position: relative``, then a grouped
    ``::before`` rule that draws the rounded-cap bar. Each affected
    class still owns its ``--sidebar-color`` + padding.
    """
    base = ',\n'.join(selectors)
    before = ',\n'.join(f'{s}::before' for s in selectors)
    return SIDEBAR_CSS_TEMPLATE.format(
        selectors_base=base, selectors_before=before,
    )


def format_block_attribution(block: dict) -> str:
    """Render an optional per-block `author` attribution line.

    When a narrative block (`[intro]`, `[meta_role]`, `[verdict]` in the
    article TOML; or `[Species.intro]` / `[Species.meta_role]` /
    `[Species.verdict]` in the dive-side threshold TOML) carries an
    `author = "..."` field, this appends a muted italic paragraph at
    the end of the block so a reader can tell human-authored prose
    from AI-drafted prose without relying on the page-top authorship
    banner.

    Empty or missing `author` returns the empty string; callers
    unconditionally concatenate, so blocks that predate the field
    render unchanged.

    Phrasing is author-controlled and rendered verbatim (HTML-escaped).
    Typical values: "Drafted by Claude (Opus 4.7), not yet human-
    reviewed" / "Michael Lerner" / "Drafted by Claude, reviewed by
    Michael". The renderer does not prepend "By" or similar — the
    TOML author owns the phrasing.
    """
    author = (block.get('author') or '').strip()
    if not author:
        return ''
    return (
        '<p class="narrative-attribution">'
        f'<em>{html.escape(author)}</em></p>'
    )


def resolve_dive_link(article: dict) -> str:
    slug = article['links']['deep_dive_slug']
    return f'../../{slug}/'


def render_obsolescence_banner(obs: dict) -> str:
    if obs['status'] == 'current':
        return ''
    note = obs.get('note', '').strip()
    as_of = obs.get('as_of', '')
    note_html = f' {html.escape(note)}' if note else ''
    return (
        '<div class="obsolete-banner">'
        f'<strong>This article is outdated</strong> (as of {html.escape(as_of)}).{note_html}'
        '</div>\n'
    )


def render_authorship_banner(authorship: str) -> str:
    if authorship == 'expert':
        return (
            '<div class="authorship-banner expert">'
            'This article is written by a human analyst.'
            '</div>\n'
        )
    if authorship == 'both':
        return (
            '<div class="authorship-banner both">'
            'Human-written analysis supported by simulation data.'
            '</div>\n'
        )
    if authorship == 'auto':
        return (
            '<div class="authorship-banner auto">'
            'This article is auto-generated from simulation data.'
            '</div>\n'
        )
    return ''


def render_html(article: dict) -> str:
    title = html.escape(article['title'])
    species = html.escape(article['species'])
    cd_move = html.escape(article['cd_move'])
    cd_date = html.escape(article['cd_date'])
    author = html.escape(article['author'])
    framing = html.escape(article['framing'])

    banner = render_obsolescence_banner(article['obsolescence'])
    authorship_banner = render_authorship_banner(article.get('authorship', ''))
    dive_link = resolve_dive_link(article)

    # Try to read the dive's meta.toml for a proper title
    dive_slug = article['links']['deep_dive_slug']
    dive_meta_path = WEBSITE_DIR / dive_slug / 'meta.toml'
    if dive_meta_path.exists():
        with open(dive_meta_path, 'rb') as f:
            dive_meta = tomllib.load(f)
        dive_title = html.escape(dive_meta.get('title', f'{species} IV Deep Dive'))
    else:
        dive_title = f'{species} IV Deep Dive'

    sections_html = []
    for sec in article['sections']:
        heading = html.escape(sec['heading'])
        body = format_body(sec['body'])
        sections_html.append(f'<h2>{heading}</h2>\n{body}')
    sections_block = '\n\n'.join(sections_html)

    _sidebar_css = sidebar_css([
        '.related', '.authorship-banner',
    ])
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
         sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px;
         background: #1a1a2e; color: #e0e0e0; line-height: 1.6; }}
  h1 {{ color: #e94560; margin-bottom: 6px; }}
  h2 {{ color: #c8a2d0; border-bottom: 1px solid #0f3460;
        padding-bottom: 6px; margin-top: 30px; }}
  a {{ color: #9be89b; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  p {{ margin: 10px 0; }}
  code {{ background: #16213e; padding: 2px 5px; border-radius: 3px;
          font-size: 0.9em; }}
  .meta {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
  .related {{ --sidebar-color: #9be89b;
              background: #16213e; padding: 12px 16px 12px 20px;
              border-radius: 6px; margin: 16px 0; }}
  .obsolete-banner {{ background: #3d1f1f; border: 1px solid #e94560;
                      padding: 12px 16px; border-radius: 6px;
                      margin-bottom: 20px; color: #f0a0a0; }}
  .authorship-banner {{ padding: 10px 16px 10px 20px; border-radius: 6px;
                        margin-bottom: 16px; font-size: 14px; }}
  .authorship-banner.expert {{ --sidebar-color: #d4a017;
                               background: #2a2000; color: #e8d48b; }}
  .authorship-banner.both {{ --sidebar-color: #7db87d;
                             background: #1f2a1a; color: #a8d8a8; }}
  .authorship-banner.auto {{ --sidebar-color: #5b8dd9;
                             background: #1a2333; color: #8ab4f8; }}
  .framing {{ display: inline-block; padding: 2px 10px; border-radius: 12px;
              font-size: 13px; font-weight: 600; text-transform: uppercase;
              background: #0f3460; color: #8ab4f8; }}
  .narrative-attribution {{ color: #8b949e; font-size: 0.85rem;
                            margin: 6px 0 0 0; font-style: italic; }}
  footer {{ color: #666; font-size: 13px; margin-top: 40px;
            border-top: 1px solid #0f3460; padding-top: 12px; }}
  {_sidebar_css}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">
  Community Day: {cd_date} | {species} | <span class="framing">{framing}</span>
</div>
{authorship_banner}{banner}
<div class="related">
  Simulation Deep Dive: <a href="{html.escape(dive_link)}">{dive_title}</a>
</div>

{sections_block}

<footer>
  <p>By {author}</p>
  <p>{PVPOKE_ATTRIBUTION_HTML}</p>
</footer>
</body>
</html>
"""


def write_meta_toml(slug_dir: Path, article: dict) -> None:
    title = article['title']
    desc = article['description'].strip()
    authorship = article.get('authorship', 'auto')
    meta_content = (
        f'title = {_toml_string(title)}\n'
        f'description = {_toml_string(desc)}\n'
        f'authorship = {_toml_string(authorship)}\n'
        f'landing = "index.html"\n'
    )
    (slug_dir / 'meta.toml').write_text(meta_content)


def _toml_string(s: str) -> str:
    if '\n' in s:
        return f'"""\n{s}\n"""'
    return f'"{s}"'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Render a CD article TOML into HTML.')
    parser.add_argument('toml_path', type=Path,
                        help='Path to the article TOML file')
    args = parser.parse_args()

    article = load_article(args.toml_path)
    slug = args.toml_path.stem

    # Guard: this renderer is for expert-authored articles only. Running
    # it against an `auto` / `both` article would clobber the richer
    # generate_article.py output with a placeholder skeleton. Symmetric
    # with the same check in generate_article.py main() which refuses
    # `expert` articles.
    authorship = article.get('authorship', 'expert')
    if authorship != 'expert':
        sys.exit(
            f"Article {slug!r} has authorship={authorship!r}, not 'expert'. "
            f"Use scripts/generate_article.py instead; this renderer emits "
            f"[[sections]] verbatim and would clobber the data-driven HTML.")

    slug_dir = ARTICLES_DIR / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    article_html = render_html(article)
    index_path = slug_dir / 'index.html'
    index_path.write_text(article_html)

    write_meta_toml(slug_dir, article)

    print(f'Wrote {index_path}')
    print(f'Wrote {slug_dir / "meta.toml"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
