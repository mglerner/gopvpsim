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
GUIDES_DIR = WEBSITE_DIR / 'guides'
INDEX_PATH = WEBSITE_DIR / 'index.html'


_LEAGUE_SUFFIXES = {
    'great-league': 'Great League',
    'ultra-league': 'Ultra League',
    'master-league': 'Master League',
}

# Slug tokens that classify as variant axes (not part of the base-species
# group key). Regional tags stay in the group key (a Galarian form is a
# different dex entry); shadow / gender / alternate-form tokens are
# variants of the same species and collapse under one group.
_REGIONAL = {'galarian', 'alolan', 'hisuian', 'paldean'}
_FORM_PAREN = {'blade', 'shield', 'busted', 'disguised',
               'super', 'large', 'small', 'average', 'hangry'}
_LEAGUE_ORDER = {'great': 0, 'ultra': 1, 'master': 2}


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
    # Lazy import — display module needs gamemaster data; calling at
    # module-import time bloats fast paths that don't need this.
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / 'src'))
    from gopvpsim.display import pretty_species_from_slug  # type: ignore[import-not-found]

    for suffix, pretty in _LEAGUE_SUFFIXES.items():
        if slug.endswith('-' + suffix):
            core = slug[:-(len(suffix) + 1)]  # strip "-great-league" etc.
            tokens = core.split('-')
            # Identify the boundary between the species-name slug
            # tokens (which feed pretty_species_from_slug) and any
            # variant-descriptor tokens (moveset names, etc.) that
            # follow. We consume tokens greedily into the species
            # portion as long as each consumed token is either part
            # of the bare species name or one of the known
            # regional/shadow/form tags. Once we hit a token that
            # isn't, the rest are variant descriptors.
            #
            # Tokens we consume into the species slug:
            #   * Regional / shadow tags: shadow, galarian, alolan,
            #     hisuian, paldean
            #   * Form tags: female, male, blade, shield, busted,
            #     disguised, super, large, small, average, hangry
            #
            # pretty_species_from_slug handles regional + female
            # promotion; other form tags get re-parenthesised inline.
            REGIONAL = {'shadow', 'galarian', 'alolan', 'hisuian',
                        'paldean'}
            FORM_PAREN = {'blade', 'shield', 'busted', 'disguised',
                          'super', 'large', 'small', 'average',
                          'hangry'}
            # Always take the first token (it's the bare species).
            species_tokens = [tokens[0]] if tokens else []
            extra_form_parens: list[str] = []
            i = 1
            while i < len(tokens):
                t = tokens[i]
                if t in REGIONAL or t == 'female':
                    species_tokens.append(t)
                    i += 1
                elif t in FORM_PAREN:
                    extra_form_parens.append(t.capitalize())
                    i += 1
                else:
                    break
            species_slug = '_'.join(species_tokens)
            species_display = pretty_species_from_slug(species_slug)
            for fp in extra_form_parens:
                species_display = f'{species_display} ({fp})'
            # Remaining tokens are variant descriptors (moveset names,
            # etc.). Capitalize each.
            variant_parts = [t.capitalize() for t in tokens[i:]]
            species_plus_variant = ' '.join(
                [species_display] + variant_parts).strip()
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


def load_entries(base_dir: Path, *, href_prefix: str = '',
                 exclude: frozenset[str] = frozenset()) -> list[dict]:
    """Return one dict per valid subdir, sorted by title.

    Prefers ``meta.toml`` (authored schema) when present; falls back
    to deriving title + landing from the dir's ``index.html`` for
    dives that don't carry a meta.toml yet. Dirs with neither are
    skipped. ``exclude`` holds subdir basenames to skip wholesale
    (used to exclude the ``articles/`` / ``comparisons/`` / ``guides/``
    container subdirs when scanning the site root for dives).
    """
    if not base_dir.exists():
        return []
    entries = []
    for sub in sorted(base_dir.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in exclude:
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
            # Curated = an authored meta.toml exists (vs HTML-derived
            # fallback). Drives whether the grouped dives list surfaces
            # the description as a hover tooltip.
            'curated': meta_path.exists(),
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


def _parse_dive_slug(slug: str) -> dict | None:
    """Split a dive slug into base species (group key) + variant axes.

    Returns None when the slug has no recognised league suffix or no
    species token (caller falls back to rendering it ungrouped).

    Group key = bare species + regional tags (Galarian etc.) — same dex
    entry. Variant axes = shadow flag, gender, alternate form (Blade/
    Shield/...), moveset tokens, and league. Examples:

      forretress-shadow-bug-bite-great-league
        → species "Forretress", variant ["Shadow", "Bug", "Bite"], great
      tinkaton-ultra-league
        → species "Tinkaton", variant [], ultra
      galarian-corsola-great-league
        → species "Galarian Corsola", variant [], great
      oinkologne-female-great-league
        → species "Oinkologne", gender "female", great
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / 'src'))
    from gopvpsim.display import pretty_species_from_slug  # type: ignore[import-not-found]

    core = league_key = league_pretty = None
    for suffix, pretty in _LEAGUE_SUFFIXES.items():
        if slug.endswith('-' + suffix):
            core = slug[:-(len(suffix) + 1)]
            league_key = suffix.split('-')[0]
            league_pretty = pretty
            break
    if core is None:
        return None

    shadow = False
    gender = None
    regional: list[str] = []
    forms: list[str] = []
    name_tokens: list[str] = []
    for t in core.split('-'):
        if t == 'shadow':
            shadow = True
        elif t in _REGIONAL:
            regional.append(t)
        elif t in ('female', 'male'):
            gender = t
        elif t in _FORM_PAREN:
            forms.append(t)
        else:
            name_tokens.append(t)
    if not name_tokens:
        return None

    bare = name_tokens[0]
    moveset_tokens = name_tokens[1:]
    group_slug = '_'.join([bare] + regional)
    species_display = pretty_species_from_slug(group_slug)
    # Drop the gender parenthetical for the group heading — the group
    # spans both genders; the per-variant chip carries Male/Female.
    for g in (' (Male)', ' (Female)'):
        if species_display.endswith(g):
            species_display = species_display[: -len(g)]
            break

    variant_tokens: list[str] = []
    if shadow:
        variant_tokens.append('Shadow')
    variant_tokens += [f.capitalize() for f in forms]
    if gender:
        variant_tokens.append(gender.capitalize())
    variant_tokens += [t.capitalize() for t in moveset_tokens]

    return {
        'group_key': group_slug,
        'species_display': species_display,
        'shadow': shadow,
        'gender': gender,
        'variant_tokens': variant_tokens,
        'league_key': league_key,
        'league_pretty': league_pretty,
    }


def _group_dives(dives: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collapse per-variant dive entries under one base-species group.

    Returns (groups, leftovers). Each group is
    ``{'species': str, 'entries': [{'entry', 'label'}, ...]}`` sorted by
    species; leftovers are entries whose slug didn't parse (rendered
    ungrouped with their full title).
    """
    groups: dict[str, dict] = {}
    leftovers: list[dict] = []
    for d in dives:
        p = _parse_dive_slug(d['slug'])
        if p is None:
            leftovers.append(d)
            continue
        g = groups.setdefault(
            p['group_key'],
            {'species': p['species_display'], 'rows': []})
        g['rows'].append({'entry': d, 'parse': p})

    result: list[dict] = []
    for g in groups.values():
        rows = g['rows']
        multi_league = len({r['parse']['league_key'] for r in rows}) > 1
        has_female = any(r['parse']['gender'] == 'female' for r in rows)
        for r in rows:
            p = r['parse']
            toks = list(p['variant_tokens'])
            # A genderless sibling in a group that also has a Female form
            # is the Male form (Oinkologne etc.).
            if has_female and p['gender'] is None and not toks:
                toks = ['Male']
            label = ' '.join(toks)
            if multi_league:
                label = (f'{label} ({p["league_pretty"]})'.strip()
                         if label else p['league_pretty'])
            r['label'] = label or 'Regular'
        rows.sort(key=lambda r: (
            _LEAGUE_ORDER.get(r['parse']['league_key'], 9),
            r['parse']['shadow'],
            1 if r['parse']['gender'] == 'female' else 0,  # Male before Female
            r['label'].lower()))
        result.append({'species': g['species'], 'entries': rows})
    result.sort(key=lambda g: g['species'].lower())
    leftovers.sort(key=lambda d: d['title'].lower())
    return result, leftovers


def _render_dives_grouped(dives: list[dict], empty_msg: str) -> str:
    if not dives:
        return f'  <li><i>{html.escape(empty_msg)}</i></li>'
    groups, leftovers = _group_dives(dives)
    items: list[str] = []
    for g in groups:
        species = html.escape(g['species'])
        rows = g['entries']
        if len(rows) == 1:
            d = rows[0]['entry']
            p = rows[0]['parse']
            # No sibling chips to carry the variant axes, so fold them
            # into the display name (Shadow hoisted to a prefix, the rest
            # appended): shadow-sableye -> "Shadow Sableye", not "Sableye".
            non_shadow = [t for t in p['variant_tokens'] if t != 'Shadow']
            name = g['species']
            if p['shadow']:
                name = f'Shadow {name}'
            if non_shadow:
                name = f'{name} ' + ' '.join(non_shadow)
            suffix = ('' if p['league_key'] == 'great'
                      else f' ({html.escape(p["league_pretty"])})')
            title_attr = (f' title="{html.escape(d["description"])}"'
                          if d.get('curated') else '')
            items.append(
                '  <li class="dive">'
                f'<b><a href="{html.escape(d["href"])}"{title_attr}>'
                f'{html.escape(name)}</a></b>{suffix}'
                '</li>')
        else:
            chips = []
            for r in rows:
                d = r['entry']
                title_attr = (f' title="{html.escape(d["description"])}"'
                              if d.get('curated') else '')
                chips.append(
                    f'<a class="chip" href="{html.escape(d["href"])}"'
                    f'{title_attr}>{html.escape(r["label"])}</a>')
            items.append(
                '  <li class="dive">'
                f'<span class="species">{species}</span>'
                f'<span class="variants">{"".join(chips)}</span>'
                '</li>')
    for d in leftovers:
        items.append(
            '  <li class="dive">'
            f'<b><a href="{html.escape(d["href"])}">'
            f'{html.escape(d["title"])}</a></b>'
            '</li>')
    return '\n'.join(items)


def render_index(dives: list[dict],
                 articles: list[dict],
                 comparisons: list[dict],
                 *,
                 guides_landing: dict | None = None) -> str:
    dives_html = _render_dives_grouped(dives, 'No dives published yet.')
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

    guides_section = ''
    if guides_landing:
        title = html.escape(guides_landing.get('title') or "Reader's Guide")
        desc = html.escape(guides_landing.get('description') or '')
        href = html.escape(guides_landing.get('href') or 'guides/')
        desc_html = f'<p>{desc}</p>' if desc else ''
        guides_section = (
            '\n<h2>Reader\'s Guide</h2>\n'
            '<ul>\n'
            f'<li class="dive"><a href="{href}">{title}</a>\n'
            f'{desc_html}\n'
            '</li>\n'
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
  .section-intro {{ color: #aaa; font-size: 14px; margin: 0 0 14px 0; }}
  .species {{ font-weight: bold; color: #e0e0e0; margin-right: 10px; }}
  a.chip {{ display: inline-block; background: #0f3460; color: #9be89b;
            padding: 2px 10px; border-radius: 11px; margin: 3px 6px 3px 0;
            font-size: 13px; }}
  a.chip:hover {{ background: #1b4b80; text-decoration: none; }}
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
<p class="section-intro">Each dive simulates all 4,096 IVs against the meta
across all 9 shield scenarios, with per-opponent matchup data, IV-tier
recommendations, and an interactive stat-product scatter. Pick a variant to
open it.</p>
<ul>
{dives_html}
</ul>
{articles_section}{comparisons_section}{guides_section}
<p class="about">Built with <a href="https://github.com/pvpoke/pvpoke">PvPoke</a>
game data. If you find something broken or surprising, email me.</p>
</body>
</html>
"""


def main() -> int:
    if not WEBSITE_DIR.exists():
        print(f"error: {WEBSITE_DIR} does not exist", file=sys.stderr)
        return 1
    dives = load_entries(
        WEBSITE_DIR,
        exclude=frozenset({'articles', 'comparisons', 'guides'}),
    )
    articles = load_entries(ARTICLES_DIR, href_prefix='articles/')
    comparisons = load_entries(COMPARISONS_DIR, href_prefix='comparisons/')

    # Guides landing-page entry. build_guides.py writes
    # guides/meta.toml with {title, description, landing}; surface a
    # single "Reader's Guide" link on the top-level index when present.
    guides_landing: dict | None = None
    guides_meta = GUIDES_DIR / 'meta.toml'
    if guides_meta.is_file():
        try:
            with open(guides_meta, 'rb') as f:
                meta = tomllib.load(f)
            guides_landing = {
                'title': meta.get('title') or "Reader's Guide",
                'description': meta.get('description') or '',
                'href': 'guides/' + (meta.get('landing') or 'index.html'),
            }
        except tomllib.TOMLDecodeError:
            guides_landing = None

    index_html = render_index(dives, articles, comparisons,
                              guides_landing=guides_landing)
    INDEX_PATH.write_text(index_html)
    print(f"Wrote {INDEX_PATH} ({len(dives)} dive(s), "
          f"{len(articles)} article(s), {len(comparisons)} comparison(s))")
    for d in dives:
        print(f"  - [dive] {d['title']} -> {d['href']}")
    for a in articles:
        print(f"  - [article] {a['title']} -> {a['href']}")
    for c in comparisons:
        print(f"  - [comparison] {c['title']} -> {c['href']}")
    if guides_landing:
        print(f"  - [guides] {guides_landing['title']} -> {guides_landing['href']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
