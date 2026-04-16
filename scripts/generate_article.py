#!/usr/bin/env python3
"""Generate a CD article HTML page from simulation data + threshold TOML.

Usage:
    python scripts/generate_article.py <species> <league> <cd_move>

Example:
    python scripts/generate_article.py Oinkologne great "Mud Slap"

Output lands in userdata/website/articles/<slug>/ where <slug> is sourced
from thresholds/<species>.toml under [<Species>.article] slug.

Design: docs/article_generator_design.md
Schema: docs/article_schema.md (shared with render_article.py)

S6 scope: skeleton only. Section bodies are labelled TODO placeholders;
S7 / S8 fill in real content (move table, verdict, matchup delta, IV
recommendations). See the design doc for the authorship precedence
rule.
"""
from __future__ import annotations

import argparse
import html
import logging
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_article import (  # type: ignore[import-not-found]
    format_body,
    render_authorship_banner,
    render_obsolescence_banner,
    WEBSITE_DIR,
    ARTICLES_DIR,
    _toml_string,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_DIR = REPO_ROOT / 'thresholds'
ARTICLES_SRC_DIR = REPO_ROOT / 'articles'

logger = logging.getLogger('generate_article')


CANONICAL_SECTIONS = [
    ('intro', 'Introduction',
     'S6 (template)'),
    ('move-comparison', 'Move Comparison',
     'S7: move-by-move stat table (power, energy, turns, DPT, EPT, type, STAB).'),
    ('meta-coverage', 'Meta Coverage',
     'S7/S8: per-moveset avg score + win counts by shield scenario.'),
    ('matchup-delta', 'Matchup Delta',
     'S8: per-opponent score diff between CD moveset and old default; flip highlights.'),
    ('iv-recommendations', 'IV Recommendations',
     'S8: threshold-tier cards from thresholds/<species>.toml; optional envelope annotations.'),
    ('verdict', 'Verdict',
     'S7: one line picked by avg-score delta magnitude (upgrade / sidegrade / etc.).'),
]

PLACEHOLDER_SENTINEL = 'PLACEHOLDER'


def load_threshold_slug(species: str) -> tuple[Path, str]:
    """Resolve the article slug from thresholds/<species>.toml.

    Returns (toml_path, slug). Errors loudly if the slug is missing.
    """
    lower = species.lower()
    path = THRESHOLDS_DIR / f'{lower}.toml'
    if not path.exists():
        sys.exit(f"No threshold TOML for species {species!r} at {path}")
    with open(path, 'rb') as f:
        data = tomllib.load(f)
    species_block = data.get(species)
    if not species_block:
        sys.exit(
            f"{path}: no top-level [{species}] table. Check the species "
            f"casing matches the threshold TOML.")
    article_block = species_block.get('article') or {}
    slug = article_block.get('slug')
    if not slug:
        sys.exit(
            f"{path}: [{species}.article] slug field is required for the "
            f"article generator to know where to write output.")
    return path, slug


def load_article_toml(slug: str) -> tuple[Path, dict]:
    """Load articles/<slug>.toml. Returns (path, parsed dict).

    Unlike render_article.load_article this is permissive — the generator
    can supply defaults for any missing field. But if the file does not
    exist at all we bail, because the front-matter (species, cd_date,
    author, description, framing) is still hand-curated.
    """
    path = ARTICLES_SRC_DIR / f'{slug}.toml'
    if not path.exists():
        sys.exit(
            f"No article TOML at {path}. Create it with at least the "
            f"front-matter fields (title, species, cd_date, author, "
            f"description, framing, obsolescence, links) before running "
            f"the generator. See docs/article_schema.md.")
    with open(path, 'rb') as f:
        data = tomllib.load(f)
    return path, data


def resolve_dive_dir(article: dict, dive_dir_override: Path | None) -> Path:
    if dive_dir_override is not None:
        return dive_dir_override
    slug = article.get('links', {}).get('deep_dive_slug')
    if not slug:
        sys.exit(
            "Article TOML is missing [links] deep_dive_slug; pass "
            "--dive-dir explicitly if the dive lives elsewhere.")
    return WEBSITE_DIR / slug


def build_override_map(article: dict, authorship: str) -> dict[str, str]:
    """Collect expert-supplied section bodies keyed by heading.

    Empty + PLACEHOLDER-prefixed bodies are dropped (they fall back to
    generator output). Only applies under `authorship=both`.
    """
    if authorship != 'both':
        return {}
    overrides: dict[str, str] = {}
    canonical_headings = {h for _, h, _ in CANONICAL_SECTIONS}
    for sec in article.get('sections') or []:
        heading = (sec.get('heading') or '').strip()
        body = (sec.get('body') or '').strip()
        if not heading or not body:
            continue
        if body.startswith(PLACEHOLDER_SENTINEL):
            continue
        if heading not in canonical_headings:
            logger.warning(
                "Override section heading %r is not in the canonical "
                "section list; skipping.", heading)
            continue
        overrides[heading] = body
    return overrides


def render_placeholder(section_id: str, heading: str, todo: str) -> str:
    """Render a labelled placeholder block for a stubbed section body."""
    return (
        f'<div class="todo-placeholder" id="{html.escape(section_id)}-todo">'
        f'<strong>TODO</strong>: {html.escape(todo)}'
        f'</div>'
    )


def render_intro_section(article: dict) -> str:
    """Template-rendered intro paragraph from front-matter.

    S6 uses this as a proof-of-life; S7/S8 may revise once the broader
    template tone is settled.
    """
    species = html.escape(article.get('species', ''))
    cd_move = html.escape(article.get('cd_move', ''))
    cd_date = html.escape(article.get('cd_date', ''))
    framing = html.escape(article.get('framing', ''))
    return (
        f'<p>{species} picks up <strong>{cd_move}</strong> on Community Day '
        f'({cd_date}). This page collects the mechanical comparison '
        f'(move stats, meta coverage, per-opponent matchup shifts, IV '
        f'thresholds) so you can decide whether to chase a catch. '
        f'Framing: <em>{framing}</em>.</p>'
    )


def render_section(section_id: str, heading: str, todo: str,
                   article: dict, overrides: dict[str, str]) -> str:
    if heading in overrides:
        body_html = format_body(overrides[heading])
    elif section_id == 'intro':
        body_html = render_intro_section(article)
    else:
        body_html = render_placeholder(section_id, heading, todo)
    return (
        f'<section id="{html.escape(section_id)}">\n'
        f'<h2>{html.escape(heading)}</h2>\n'
        f'{body_html}\n'
        f'</section>'
    )


def resolve_dive_title(dive_dir: Path, species_fallback: str) -> str:
    meta_path = dive_dir / 'meta.toml'
    if meta_path.exists():
        with open(meta_path, 'rb') as f:
            dive_meta = tomllib.load(f)
        return dive_meta.get('title', f'{species_fallback} IV Deep Dive')
    return f'{species_fallback} IV Deep Dive'


def resolve_dive_link(article: dict) -> str:
    slug = article['links']['deep_dive_slug']
    return f'../../{slug}/'


def render_html(article: dict, authorship: str, dive_dir: Path,
                league: str, cd_move: str) -> str:
    title = html.escape(article.get('title', article.get('species', 'Article')))
    species = html.escape(article.get('species', ''))
    cd_move_disp = html.escape(cd_move or article.get('cd_move', ''))
    cd_date = html.escape(article.get('cd_date', ''))
    author = html.escape(article.get('author', ''))
    framing = html.escape(article.get('framing', ''))
    league_disp = html.escape(league.capitalize() + ' League')

    obsolescence = article.get('obsolescence') or {
        'status': 'current', 'as_of': '', 'note': ''
    }
    banner = render_obsolescence_banner(obsolescence)
    authorship_banner = render_authorship_banner(authorship)
    dive_link = resolve_dive_link(article)
    dive_title = html.escape(resolve_dive_title(dive_dir, article.get('species', '')))

    overrides = build_override_map(article, authorship)

    sections_html = '\n\n'.join(
        render_section(sid, heading, todo, article, overrides)
        for sid, heading, todo in CANONICAL_SECTIONS
    )

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
  .related {{ background: #16213e; padding: 12px 16px; border-radius: 6px;
              margin: 16px 0; border-left: 3px solid #9be89b; }}
  .obsolete-banner {{ background: #3d1f1f; border: 1px solid #e94560;
                      padding: 12px 16px; border-radius: 6px;
                      margin-bottom: 20px; color: #f0a0a0; }}
  .authorship-banner {{ padding: 10px 16px; border-radius: 6px;
                        margin-bottom: 16px; font-size: 14px; }}
  .authorship-banner.expert {{ background: #2a2000; border-left: 3px solid #d4a017;
                               color: #e8d48b; }}
  .authorship-banner.both {{ background: #1f2a1a; border-left: 3px solid #7db87d;
                             color: #a8d8a8; }}
  .authorship-banner.auto {{ background: #1a2333; border-left: 3px solid #5b8dd9;
                             color: #8ab4f8; }}
  .framing {{ display: inline-block; padding: 2px 10px; border-radius: 12px;
              font-size: 13px; font-weight: 600; text-transform: uppercase;
              background: #0f3460; color: #8ab4f8; }}
  .todo-placeholder {{ background: #1a2333; border: 1px dashed #5b8dd9;
                       border-radius: 6px; padding: 10px 14px; color: #8ab4f8;
                       font-size: 14px; margin: 10px 0; }}
  footer {{ color: #666; font-size: 13px; margin-top: 40px;
            border-top: 1px solid #0f3460; padding-top: 12px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">
  Community Day: {cd_date} | {species} | {league_disp} | <span class="framing">{framing}</span>
</div>
{authorship_banner}{banner}
<div class="related">
  Simulation Deep Dive: <a href="{html.escape(dive_link)}">{dive_title}</a>
</div>

{sections_html}

<footer>
  By {author} | Generated from simulation data by
  <code>scripts/generate_article.py</code>. Built with
  <a href="https://github.com/pvpoke/pvpoke">PvPoke</a> game data.
</footer>
</body>
</html>
"""


def write_meta_toml(slug_dir: Path, article: dict, authorship: str) -> None:
    title = article.get('title', '')
    desc = (article.get('description') or '').strip()
    meta_content = (
        f'title = {_toml_string(title)}\n'
        f'description = {_toml_string(desc)}\n'
        f'authorship = {_toml_string(authorship)}\n'
        f'landing = "index.html"\n'
    )
    (slug_dir / 'meta.toml').write_text(meta_content)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Generate a CD article HTML page from sim data + TOML.')
    parser.add_argument('species', help='Display-form species name (e.g. Oinkologne).')
    parser.add_argument('league', choices=['great', 'ultra', 'master'],
                        help='League for the article.')
    parser.add_argument('cd_move', help='Community Day fast move (e.g. "Mud Slap").')
    parser.add_argument('--article-toml', type=Path, default=None,
                        help='Override the default articles/<slug>.toml lookup.')
    parser.add_argument('--dive-dir', type=Path, default=None,
                        help='Override the default dive directory lookup.')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Info-level logging to stderr.')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(levelname)s %(name)s: %(message)s',
        stream=sys.stderr,
    )

    _, slug = load_threshold_slug(args.species)
    logger.info('Resolved slug %r for species %r', slug, args.species)

    if args.article_toml is not None:
        with open(args.article_toml, 'rb') as f:
            article = tomllib.load(f)
        article_path = args.article_toml
    else:
        article_path, article = load_article_toml(slug)
    logger.info('Loaded article front-matter from %s', article_path)

    authorship = article.get('authorship', 'auto')
    if authorship == 'expert':
        sys.exit(
            f"Article {slug!r} is expert-authored (authorship='expert'). "
            f"Use scripts/render_article.py instead; generate_article.py "
            f"is for auto / both.")
    if authorship not in ('auto', 'both'):
        sys.exit(
            f"Unknown authorship value {authorship!r}; expected one of "
            f"'auto', 'both', 'expert'.")

    dive_dir = resolve_dive_dir(article, args.dive_dir)
    logger.info('Resolved dive dir: %s', dive_dir)

    slug_dir = ARTICLES_DIR / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    article_html = render_html(
        article, authorship=authorship, dive_dir=dive_dir,
        league=args.league, cd_move=args.cd_move,
    )
    index_path = slug_dir / 'index.html'
    index_path.write_text(article_html)

    write_meta_toml(slug_dir, article, authorship)

    print(f'Wrote {index_path}')
    print(f'Wrote {slug_dir / "meta.toml"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
