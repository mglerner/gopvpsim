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

import datetime as _dt
import html
import re
import shutil
import sys
import tomllib
from pathlib import Path

import markdown  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDES_SRC = REPO_ROOT / 'guides'
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'
GUIDES_OUT = WEBSITE_DIR / 'guides'

sys.path.insert(0, str(REPO_ROOT / 'src'))
from gopvpsim.attribution import (  # noqa: E402
    PVPOKE_ATTRIBUTION_SHORT,
    support_footer_html,
)
from gopvpsim.theme import (  # noqa: E402
    data_theme_attr,
    theme_css,
    theme_head_script,
    theme_picker_html,
)

# Verification-count scalars used by dev:* tokens. DEVELOPER_NOTES.md
# is the source of truth; the numbers live in prose, each wrapped in
# HTML-comment sentinels ``<!-- sync:KEY -->VALUE<!-- /sync -->`` that
# the markdown renderer hides but we parse here. ``verify_dev_counts.py``
# cross-checks derivable keys against live code on each commit.
DEV_COUNTS_SOURCE_PATH = REPO_ROOT / 'DEVELOPER_NOTES.md'

# Reference dive used for data-token resolution when a guide TOML
# doesn't override. The Male GL dive + CD article were retired
# 2026-06-25 (see TODO.md); Female Oinkologne GL is the surviving
# Oinkologne dive, so readers can click through and see the numbers.
DEFAULT_REFERENCE = {
    'species': 'Oinkologne (Female)',
    'league': 'great',
    'dive_slug': 'oinkologne-female-great-league',
}


# --------------------------------------------------------------------
# Reference-dive data access
# --------------------------------------------------------------------

def _dive_data(dive_slug: str) -> dict | None:
    """Return the parsed dive DATA for the main index.html, or None.

    Uses generate_article's _load_dive_data helper so the dict shape
    matches what auto_gen_narrative consumes - makes future data-token
    resolvers drop-in without re-parsing. Also hoists a couple of
    top-level dive fields (species, league) that the loader doesn't
    surface but that token resolvers need for display strings.
    """
    sys.path.insert(0, str(REPO_ROOT / 'scripts'))
    sys.path.insert(0, str(REPO_ROOT / 'src'))
    from generate_article import _load_dive_data, _extract_js_assignment  # type: ignore[import-not-found]
    import json as _json
    dive_dir = WEBSITE_DIR / dive_slug
    if not dive_dir.is_dir():
        return None
    try:
        parsed = _load_dive_data(dive_dir)
    except SystemExit:
        return None
    # _load_dive_data intentionally returns only the moveset-shaped
    # fields. Re-open index.html to pull species/league off the
    # top-level DATA; avoids touching generate_article.py just to add a
    # field the CD-article flow doesn't need.
    idx = dive_dir / 'index.html'
    try:
        content = idx.read_text()
        top = _json.loads(_extract_js_assignment(content, 'DATA'))
        parsed['species'] = top.get('species') or ''
        parsed['league'] = top.get('league') or ''
    except Exception:
        pass
    return parsed


# --------------------------------------------------------------------
# Token resolution
# --------------------------------------------------------------------

_DEV_COUNTS_SENTINEL_RE = re.compile(
    r'<!--\s*sync:([A-Za-z_][A-Za-z0-9_]*)\s*-->(.+?)<!--\s*/sync\s*-->',
    flags=re.DOTALL,
)


def _load_verification_counts() -> dict:
    """Extract dev-count scalars from DEVELOPER_NOTES.md sentinels.

    Every sentinel pair ``<!-- sync:KEY -->VALUE<!-- /sync -->`` in
    the file contributes one entry. VALUE is coerced to int when the
    stripped text parses cleanly, otherwise left as a string.

    Returns ``{}`` if the file is absent (keeps the guide build from
    hard-failing in partial checkouts). Callers that need the strict
    verifier should use ``scripts/verify_dev_counts.py`` instead.
    """
    if not DEV_COUNTS_SOURCE_PATH.is_file():
        return {}
    text = DEV_COUNTS_SOURCE_PATH.read_text()
    out: dict = {}
    for m in _DEV_COUNTS_SENTINEL_RE.finditer(text):
        key = m.group(1)
        raw = m.group(2).strip()
        try:
            out[key] = int(raw)
        except ValueError:
            out[key] = raw
    return out


def _resolve_tokens(
    body: str,
    guide_tokens: dict,
    *,
    dive: dict | None,
    dev_counts: dict,
    guide_slug: str,
) -> tuple[str, list[str]]:
    """Replace ``{{token}}`` placeholders. Returns (resolved, unresolved).

    Resolution order:
      1. Literal scalar entries in ``[tokens]`` of the guide TOML.
      2. ``dive:`` prefixed tokens resolved via ``_resolve_dive_token``.
      3. ``dev:`` prefixed tokens resolved via sync sentinels in
         ``DEVELOPER_NOTES.md``.
      4. Otherwise the placeholder is left intact and its name is
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
        if name.startswith('dev:'):
            key = name[len('dev:'):]
            if key in dev_counts:
                return str(dev_counts[key])
        unresolved.append(f'{guide_slug}:{name}')
        return match.group(0)

    resolved = _re.sub(r'\{\{\s*([^}]+?)\s*\}\}', _replace, body)
    return resolved, unresolved


def _resolve_dive_token(suffix: str, dive: dict | None) -> str | None:
    """Resolve a ``dive:<suffix>`` token against the reference dive.

    Vocabulary (extend as guides land):
      - ``species_display``: pretty species label from the first moveset.
      - ``moveset_count``: count of movesets in the dive.
      - ``opponent_count``: count of opponents scored.
      - ``scenario_count``: count of shield scenarios simulated.
      - ``iv_space_size``: number of IV spreads swept (always 4096 for
        a full dive; pulled from the data so we never hardcode).
      - ``tier_count``: number of threshold-tier cards on the featured
        moveset (= the moveset analyzed in ``index.html``).
      - ``top_tier_name``: display name of the first threshold tier.
      - ``top_tier_atk_cutoff`` / ``top_tier_def_cutoff`` /
        ``top_tier_sta_cutoff``: the first tier's three stat cutoffs,
        rounded to 2 decimals. A cutoff of exactly 0 renders as ``0``
        (meaning "no cutoff on that stat"), otherwise rendered with
        two digits.
      - ``top_tier_clear_count``: how many of the 4096 IVs clear the
        first tier's cutoffs.
      - ``envelope_rider_top_count`` / ``envelope_rider_bottom_count``:
        how many named IV categories on the featured moveset classify
        as riders above / below the Anchor IVs band. Sourced from
        ``envelopePositions`` (see ``compute_envelope_positions``).
      - ``envelope_straddler_count``: how many categories straddle the
        anchor band (``elevated-band-crosser`` + ``depressed-band-
        crosser`` combined).
      - ``envelope_classified_count``: total categories with a
        non-sparse envelope classification. Equals the sum of the
        three counts above.

    Returns None when the dive is missing or the token isn't known.
    """
    if dive is None:
        return None
    movesets = dive.get('movesets') or []
    featured = movesets[0] if movesets else None
    env_map = (dive.get('envelopePositions') or {}).get('0') or {}
    if suffix.startswith('envelope_'):
        rt = rb = cross = 0
        for entry in env_map.values():
            if not isinstance(entry, dict):
                continue
            shape = entry.get('shape')
            if shape == 'envelope-rider-top':
                rt += 1
            elif shape == 'envelope-rider-bottom':
                rb += 1
            elif shape in ('elevated-band-crosser', 'depressed-band-crosser'):
                cross += 1
        if suffix == 'envelope_rider_top_count':
            return str(rt)
        if suffix == 'envelope_rider_bottom_count':
            return str(rb)
        if suffix == 'envelope_straddler_count':
            return str(cross)
        if suffix == 'envelope_classified_count':
            return str(rt + rb + cross)
    if suffix == 'species_display':
        # Prefer the hoisted top-level species; fall back to the first
        # moveset's pretty label only if the species field is missing.
        sp = (dive.get('species') or '').strip()
        if sp:
            return sp
        for m in movesets:
            label = (m.get('pretty_label') or m.get('label') or '').strip()
            if label:
                return label.split('/', 1)[0].strip().title()
        return None
    if suffix == 'league_display':
        league = (dive.get('league') or '').strip()
        return league.title() + ' League' if league else None
    if suffix == 'moveset_count':
        return str(len(movesets))
    if suffix == 'opponent_count':
        return str(len(dive.get('opponents') or []))
    if suffix == 'scenario_count':
        return str(len(dive.get('scenarios') or []))
    if featured is None:
        return None
    if suffix == 'iv_space_size':
        return str(featured.get('n_ivs', 0) or 0)
    tiers = featured.get('tiers') or []
    iv_all = featured.get('iv_all_tiers') or []
    if suffix == 'tier_count':
        # B4 (mercuryish review): count of *rendered tier cards* on the
        # featured moveset. The dive's auto-derive path filters the
        # broad "General" tier out of data['tiers'] (it would dominate
        # the plot legend) but still renders it as a tier card. So
        # tier_count needs the pre-filter count; effectiveTierCount
        # carries it when present, falling back to len(tiers) for the
        # TOML-tiers path (no General fallback there).
        eff = featured.get('effective_tier_count')
        return str(eff if eff is not None else len(tiers))
    if not tiers:
        return None
    t0 = tiers[0]
    if suffix == 'top_tier_name':
        # Post-2026-04-23 tier-name unify: the tier-card badge and the
        # Plotly legend both display ``t['name']`` (the flavor-matched
        # name), so a single resolver covers both surfaces. Prior
        # implementations needed an ``original_name`` fallback because
        # the card rendered the pre-rename label; that's no longer
        # true.
        name = (t0.get('name') or '').strip()
        return name or None
    if suffix in ('top_tier_atk_cutoff',
                  'top_tier_def_cutoff',
                  'top_tier_sta_cutoff'):
        key = {'top_tier_atk_cutoff': 'attack',
               'top_tier_def_cutoff': 'defense',
               'top_tier_sta_cutoff': 'stamina'}[suffix]
        raw = t0.get(key)
        if raw is None:
            return None
        # An unused axis stores 0 exactly; preserve that rendering so
        # guide prose can say "def 0 / sta 0" and read naturally.
        if raw == 0:
            return '0'
        return f'{float(raw):.2f}'
    if suffix == 'top_tier_clear_count':
        count = 0
        for iv_tier_list in iv_all:
            if 0 in iv_tier_list:
                count += 1
        return str(count)
    return None


# --------------------------------------------------------------------
# Markdown -> HTML
# --------------------------------------------------------------------

def _render_markdown(body: str) -> str:
    # toc extension auto-slugifies every heading into an id attribute so
    # article / dive pointers can target specific subsections via
    # `guides/<slug>/#heading-slug`. permalink=False keeps the rendered
    # heading clean (no anchor icon).
    return markdown.markdown(
        body,
        extensions=['extra', 'sane_lists', 'smarty', 'toc'],
        extension_configs={'toc': {'permalink': False}},
        output_format='html5',
    )


# --------------------------------------------------------------------
# Stylesheet + page shell
# --------------------------------------------------------------------

_GUIDE_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
       sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px;
       background: var(--bg); color: var(--text); line-height: 1.6; }
h1 { color: var(--title); }
h2 { color: var(--heading); border-bottom: 1px solid var(--border);
     padding-bottom: 6px; margin-top: 32px;
     font-size: 1.15em; font-weight: 700; letter-spacing: .02em; }
h3 { color: var(--heading); margin-top: 24px; font-weight: 700; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code { background: var(--surface); padding: 2px 6px; border-radius: 2px;
       border: 1px solid var(--border); font-size: 0.92em; }
pre { background: var(--surface); padding: 12px 16px; border-radius: 2px;
      border: 1px solid var(--border); overflow-x: auto; margin: 16px 0;
      font-size: 0.9em; line-height: 1.5;
      width: fit-content; max-width: 100%; }
pre code { background: transparent; padding: 0; font-size: inherit;
           border: 0; }
ul, ol { padding-left: 22px; }
li { margin: 4px 0; }
figure { margin: 20px 0; }
figure img { max-width: 100%; height: auto; display: block;
             border-radius: 2px; }
figcaption { color: var(--text-muted); font-size: 14px; margin-top: 8px;
             font-style: italic; }
.coming-soon { background: var(--callout-bg); padding: 20px; border-radius: 0;
               border: 1px solid var(--callout-ai); color: var(--callout-fg); }
.breadcrumb { color: var(--text-muted); font-size: 14px; margin-bottom: 20px; }
.breadcrumb a { color: var(--accent); }
.guide-list { list-style: none; padding: 0; }
.guide-list li { background: var(--surface); padding: 14px 18px;
                 border-radius: 2px; margin-bottom: 14px; }
.guide-list li p { margin: 6px 0 0 0; color: var(--text-muted); font-size: 14px; }
.guide-list li.coming-soon-entry a { color: var(--text-muted); cursor: not-allowed; }
.guide-list li.coming-soon-entry .badge {
    font-size: 12px; color: var(--callout-ai); margin-left: 8px; }
.about { color: var(--text-muted); font-size: 13px; margin-top: 40px;
         border-top: 1px solid var(--border); padding-top: 12px; }
.authorship-banner { padding: 10px 14px; border-radius: 0;
                     margin: 0 0 18px 0; font-size: 14px;
                     background: var(--callout-bg); color: var(--callout-fg);
                     border: 1px solid var(--sidebar-color, var(--text-muted)); }
.authorship-banner.ai     { --sidebar-color: var(--callout-ai); }
.authorship-banner.auto   { --sidebar-color: var(--callout-auto); }
.authorship-banner.both   { --sidebar-color: var(--callout-both); }
.authorship-banner.expert { --sidebar-color: var(--callout-expert); }
.auth-chip { display: inline-block; padding: 1px 8px; border-radius: 4px;
             font-weight: 600; background: var(--callout-bg); color: var(--callout-fg);
             border: 1px solid var(--sidebar-color, var(--text-muted)); }
.auth-chip.ai     { --sidebar-color: var(--callout-ai); }
.auth-chip.auto   { --sidebar-color: var(--callout-auto); }
.auth-chip.both   { --sidebar-color: var(--callout-both); }
.auth-chip.expert { --sidebar-color: var(--callout-expert); }
"""


# Authorship banner vocabulary for guides. Parallels the CD-article
# variants (see ``render_article.render_authorship_banner``) but adds
# an ``ai`` tier to distinguish LLM-drafted prose from template-filled
# ``auto`` output. When a guide's TOML omits ``authorship``, we default
# to ``ai`` because every guide currently in the tree was LLM-drafted;
# a human rewrite should set the field explicitly to promote the
# banner colour.
_AUTHORSHIP_BANNERS = {
    'ai': ("This guide was drafted by an LLM from the site's "
           'methodology; it has not been reviewed by a human expert.'),
    'auto': 'Auto-generated from simulation data.',
    'both': 'Drafted by an LLM, reviewed and edited by TitanTrainers15 and others.',
    'expert': 'Written by a human analyst.',
}


def _render_authorship_banner(kind: str | None) -> str:
    """Return the HTML banner for a guide's authorship tier, or ''.

    ``kind`` of ``None`` falls back to ``ai`` (see rationale above).
    An unknown value warns to stderr and is treated as ``ai`` so a
    typo doesn't silently strip attribution.
    """
    resolved = (kind or 'ai').strip().lower()
    if resolved not in _AUTHORSHIP_BANNERS:
        print(f'warning: unknown authorship={kind!r}; treating as ai',
              file=sys.stderr)
        resolved = 'ai'
    text = _AUTHORSHIP_BANNERS[resolved]
    return (f'<div class="authorship-banner {resolved}">'
            f'{html.escape(text)}</div>\n')


def _render_page(*, title: str, body_html: str,
                 breadcrumb_html: str = '',
                 regenerated_stamp: str = '',
                 site_root: str = '../../') -> str:
    stamp_html = (
        f' Last regenerated {html.escape(regenerated_stamp)}.'
        if regenerated_stamp else ''
    )
    return f"""<!DOCTYPE html>
<html {data_theme_attr()}>
<head>
<meta charset="utf-8">
{theme_head_script()}
<title>{html.escape(title)}</title>
<style>{theme_css()}{_GUIDE_CSS}</style>
</head>
<body>
{theme_picker_html()}
{breadcrumb_html}
{body_html}
<p class="about">{PVPOKE_ATTRIBUTION_SHORT}</p>
<p class="about">Part of <a href="{html.escape(site_root)}">the PvP deep dive site</a>.
Explainers regenerate from current dive data every publish, so numbers
stay in sync with the methodology.{stamp_html}</p>
{support_footer_html(site_root)}</body>
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
                 *, total_unresolved: list[str],
                 dev_counts: dict,
                 regenerated_stamp: str) -> dict:
    src_dir: Path = guide['_src_dir']
    slug = guide.get('slug') or src_dir.name
    title = guide.get('title') or slug.replace('-', ' ').title()
    description = guide.get('description') or ''
    coming_soon = bool(guide.get('coming_soon'))
    authorship = guide.get('authorship')

    out_dir = GUIDES_OUT / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Body: markdown file, or "coming soon" placeholder. A stub guide
    # doesn't get an authorship banner - there's no prose to attribute
    # yet - so we suppress it below by leaving ``banner_html`` empty.
    body_md_path = src_dir / 'body.md'
    if coming_soon or not body_md_path.is_file():
        body_html = (
            '<div class="coming-soon">'
            f'<strong>Coming soon:</strong> {html.escape(description)}'
            '</div>'
        )
        banner_html = ''
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
            body_md, tokens, dive=dive, dev_counts=dev_counts,
            guide_slug=slug)
        total_unresolved.extend(unresolved)
        body_html = _render_markdown(resolved_body)
        banner_html = _render_authorship_banner(authorship)

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
        body_html=(f'<h1>{html.escape(title)}</h1>\n'
                   f'{banner_html}{body_html}'),
        breadcrumb_html=breadcrumb,
        regenerated_stamp=regenerated_stamp,
        site_root='../../',
    )
    (out_dir / 'index.html').write_text(page_html)

    # Per-guide meta.toml for the site-index builder.
    meta_out = (
        f'title = "{_toml_escape(title)}"\n'
        f'description = "{_toml_escape(description)}"\n'
        'landing = "index.html"\n'
    )
    (out_dir / 'meta.toml').write_text(meta_out)

    _order = guide.get('order')
    return {
        'slug': slug,
        'title': title,
        'description': description,
        'coming_soon': coming_soon,
        # `or` would treat a legitimate order=0 as missing; explicit None check.
        'order': 999 if _order is None else int(_order),
    }


def _toml_escape(s: str) -> str:
    # Basic TOML string escape. meta.toml is machine-read only, so we
    # don't need full quoting - just protect against " and \.
    return s.replace('\\', '\\\\').replace('"', '\\"')


# --------------------------------------------------------------------
# Landing page
# --------------------------------------------------------------------

def _build_landing(index_meta: dict, guides: list[dict],
                   *, regenerated_stamp: str) -> None:
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
        regenerated_stamp=regenerated_stamp,
        site_root='../',
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

    dev_counts = _load_verification_counts()
    regenerated_stamp = _dt.date.today().isoformat()

    guides_built: list[dict] = []
    total_unresolved: list[str] = []
    for sub in sorted(p for p in GUIDES_SRC.iterdir() if p.is_dir()):
        g = _load_guide(sub)
        if g is None:
            continue
        built = _build_guide(
            g, total_unresolved=total_unresolved,
            dev_counts=dev_counts,
            regenerated_stamp=regenerated_stamp,
        )
        guides_built.append(built)

    _build_landing(index_meta, guides_built,
                   regenerated_stamp=regenerated_stamp)

    print(f'Wrote {GUIDES_OUT}/index.html '
          f'({len(guides_built)} guide(s))')
    for g in guides_built:
        tag = '  [coming-soon]' if g['coming_soon'] else ''
        print(f"  - {g['title']} -> {g['slug']}/{tag}")

    # Hard-fail on unresolved tokens. Warning-only is too quiet: a
    # typo like ``{{dive:envelop_straddler_count}}`` would otherwise
    # ship with literal braces visible to readers, and publish_website.sh
    # wouldn't notice because `set -e` triggers on exit code, not stderr.
    if total_unresolved:
        print('error: unresolved tokens:', file=sys.stderr)
        for t in total_unresolved:
            print(f'  {t}', file=sys.stderr)
        print('Fix the token (check `_resolve_dive_token` vocabulary, '
              'DEVELOPER_NOTES.md sentinels, or guide [tokens] TOML '
              'entries) and rebuild.', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
