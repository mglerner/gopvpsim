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
import base64
import gzip
import html
import json
import logging
import struct
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from render_article import (  # type: ignore[import-not-found]
    format_body,
    render_authorship_banner,
    render_obsolescence_banner,
    WEBSITE_DIR,
    ARTICLES_DIR,
    _toml_string,
)

from gopvpsim.data import load_gamemaster, get_default_moveset, parse_types  # type: ignore[import-not-found]

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


def _extract_js_assignment(content: str, var_name: str) -> str:
    """Return the JSON literal assigned to `var <var_name> = ...;` in content.

    Slices between the `var <name> = ` token and the first `;\n` after it.
    Raises ValueError if the marker isn't found.
    """
    marker = f'var {var_name} = '
    i = content.find(marker)
    if i < 0:
        marker = f'{var_name} = '
        i = content.find(marker)
        if i < 0:
            raise ValueError(f'{var_name} assignment not found')
    start = i + len(marker)
    end = content.index(';\n', start)
    return content[start:end]


def _decompress_scores(b64: str) -> list[int]:
    """Decode one SCORES_GZ entry into a flat list of uint16 scores."""
    raw = gzip.decompress(base64.b64decode(b64))
    n = len(raw) // 2
    return list(struct.unpack(f'<{n}H', raw))


def _load_one_dive_file(path: Path) -> dict:
    """Parse one dive HTML sibling into win-rate summaries.

    Reads the embedded DATA JSON for labels + scenario shape, decompresses
    SCORES_GZ['0_pvpoke'], and counts wins (score >= 500, matching the
    scatter plot's `winsPvpoke` y-axis definition). pvpoke (bait-on) is
    the default dive view; mirroring it keeps the verdict consistent with
    what a dive reader sees on landing.
    """
    content = path.read_text()
    data_blob = _extract_js_assignment(content, 'DATA')
    data = json.loads(data_blob)

    if not data.get('movesets'):
        raise ValueError(f'{path}: no movesets in DATA')
    moveset = data['movesets'][0]
    label = moveset.get('label') or ''
    pretty = moveset.get('prettyLabel') or label

    scores_blob = _extract_js_assignment(content, 'SCORES_GZ')
    scores_gz = json.loads(scores_blob)
    key = '0_pvpoke'
    if key not in scores_gz:
        raise ValueError(f'{path}: SCORES_GZ missing {key!r}')
    scores = _decompress_scores(scores_gz[key])

    n_ivs = data['nIvs']
    n_s = data['nScenarios']
    n_o = data['nOpponents']
    expected = n_ivs * n_s * n_o
    if len(scores) != expected:
        raise ValueError(
            f'{path}: score length {len(scores)} != nIvs*nS*nO={expected}')

    per_scenario_wins = [0] * n_s
    per_scenario_n = n_ivs * n_o
    total_wins = 0
    for iv in range(n_ivs):
        base_iv = iv * n_s * n_o
        for si in range(n_s):
            base = base_iv + si * n_o
            w = 0
            for oi in range(n_o):
                if scores[base + oi] >= 500:
                    w += 1
            per_scenario_wins[si] += w
            total_wins += w
    per_scenario_rate = [w / per_scenario_n for w in per_scenario_wins]
    win_rate = total_wins / expected

    return {
        'label': label,
        'pretty_label': pretty,
        'win_rate': win_rate,
        'per_scenario_win_rate': per_scenario_rate,
        'scenarios': data['scenarios'],
    }


def _load_dive_data(dive_dir: Path) -> dict:
    """Load dive summary across all sibling HTML files in dive_dir.

    Returns:
        {
          'movesets': [ {label, pretty_label, avg_score, per_scenario_avg, scenarios}, ... ],
          'scenarios': list of [shields_a, shields_b] pairs,
        }
    """
    if not dive_dir.is_dir():
        sys.exit(f'Dive directory does not exist: {dive_dir}')
    # Pick up index.html + index_m*.html (split-moveset siblings).
    files = sorted(dive_dir.glob('index.html')) + sorted(dive_dir.glob('index_m*.html'))
    if not files:
        sys.exit(f'No index*.html dive files in {dive_dir}')
    movesets = []
    scenarios = None
    for f in files:
        parsed = _load_one_dive_file(f)
        movesets.append(parsed)
        if scenarios is None:
            scenarios = parsed['scenarios']
    return {'movesets': movesets, 'scenarios': scenarios}


def _moveset_fast_move(label: str) -> str:
    """Extract the fast move id from a moveset label like 'FAST / CM1, CM2'."""
    return label.split('/', 1)[0].strip()


def _lookup_move(gm: dict, move_id_or_name: str) -> dict | None:
    """Case-insensitive lookup by moveId or display name in gamemaster moves."""
    target = move_id_or_name.strip().lower()
    for m in gm['moves']:
        if m.get('moveId', '').lower() == target:
            return m
        if m.get('name', '').lower() == target:
            return m
    return None


def _species_types(gm: dict, species: str) -> list[str]:
    """Return the lowercase type list for a species (display form)."""
    species_id = species.lower().replace(' ', '_').replace('(', '').replace(')', '')
    for p in gm['pokemon']:
        if p.get('speciesId') == species_id:
            return parse_types(p)
    return []


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


def _format_move_stats(move: dict, species_types: list[str]) -> dict:
    """Shape a gamemaster move dict into display stats for the comparison table."""
    power = move.get('power', 0)
    energy_gain = move.get('energyGain', 0)
    cooldown_ms = move.get('cooldown', 500)
    turns = move.get('turns')
    if turns is None:
        turns = max(1, int(round(cooldown_ms / 500)))
    dpt = power / turns if turns else 0.0
    ept = energy_gain / turns if turns else 0.0
    move_type = (move.get('type') or '').lower()
    stab = move_type in species_types
    return {
        'name': move.get('name', move.get('moveId', '')),
        'type': move_type or '',
        'power': power,
        'energy_gain': energy_gain,
        'turns': turns,
        'dpt': dpt,
        'ept': ept,
        'stab': stab,
    }


def _render_move_comparison_section(cd_move: str, species: str,
                                    league: str) -> str:
    """Render the fast-move comparison table (CD move vs PvPoke default)."""
    gm = load_gamemaster()
    cd = _lookup_move(gm, cd_move)
    if cd is None:
        return render_placeholder(
            'move-comparison', 'Move Comparison',
            f'Move {cd_move!r} not found in gamemaster; cannot render table.')

    try:
        default_fast_id, _ = get_default_moveset(species, league)
    except KeyError as exc:
        return render_placeholder(
            'move-comparison', 'Move Comparison',
            f'No PvPoke default moveset: {exc}')
    default_move = _lookup_move(gm, default_fast_id)
    if default_move is None:
        return render_placeholder(
            'move-comparison', 'Move Comparison',
            f'Default fast move {default_fast_id!r} not found in gamemaster.')

    types = _species_types(gm, species)
    old = _format_move_stats(default_move, types)
    new = _format_move_stats(cd, types)

    def fmt_val(key: str, info: dict) -> str:
        if key == 'stab':
            return 'yes' if info['stab'] else 'no'
        if key in ('dpt', 'ept'):
            return f'{info[key]:.2f}'
        return html.escape(str(info[key]))

    rows = [
        ('Fast move', 'name'),
        ('Type', 'type'),
        ('Power', 'power'),
        ('Energy gain', 'energy_gain'),
        ('Turns (500ms each)', 'turns'),
        ('DPT (damage/turn)', 'dpt'),
        ('EPT (energy/turn)', 'ept'),
        ('STAB', 'stab'),
    ]
    header = (
        '<thead><tr>'
        '<th scope="col">Stat</th>'
        f'<th scope="col">Old default: {html.escape(old["name"])}</th>'
        f'<th scope="col">CD move: {html.escape(new["name"])}</th>'
        '</tr></thead>'
    )
    body_rows = []
    for label, key in rows:
        body_rows.append(
            f'<tr><th scope="row">{html.escape(label)}</th>'
            f'<td>{fmt_val(key, old)}</td>'
            f'<td>{fmt_val(key, new)}</td></tr>'
        )
    table = (
        '<table class="move-compare">'
        + header
        + '<tbody>' + ''.join(body_rows) + '</tbody>'
        + '</table>'
    )
    note = (
        f'<p class="move-compare-note">Stats from PvPoke gamemaster. '
        f'STAB flags match against {html.escape(species)} types: '
        f'{html.escape(", ".join(types) or "unknown")}.</p>'
    )
    return table + note


def _scenario_label(scenario: list[int]) -> str:
    """Format a [shields_a, shields_b] pair as '0 shields vs 2 shields' etc."""
    a, b = scenario
    a_str = '1 shield' if a == 1 else f'{a} shields'
    b_str = '1 shield' if b == 1 else f'{b} shields'
    return f'{a_str} vs {b_str}'


def _classify_verdict(wins: int, ties: int, losses: int, total: int,
                      cd_move_name: str) -> str:
    """Lead-line text from per-scenario win counts.

    Scenario count is the natural axis for the headline; the overall win-
    rate delta is reported in the detail line below the headline.
    """
    majority = (2 * total + 2) // 3  # >=2/3, rounded up: 6 of 9, 7 of 10, etc.
    if wins == total:
        return f'Clear upgrade: {cd_move_name} wins every shield scenario.'
    if losses == total:
        return 'Clear downgrade: the old default wins every shield scenario.'
    if wins >= majority and wins > losses:
        return f'Upgrade in {wins} of {total} shield scenarios.'
    if losses >= majority and losses > wins:
        return f'Downgrade in {losses} of {total} shield scenarios.'
    return (f'Mixed: {wins} of {total} scenarios favor {cd_move_name}, '
            f'{losses} favor the old default.')


def _render_verdict_section(cd_move: str, species: str, league: str,
                            dive: dict) -> str:
    """One-line verdict from per-scenario win-rate deltas."""
    gm = load_gamemaster()
    cd_move_entry = _lookup_move(gm, cd_move)
    if cd_move_entry is None:
        return render_placeholder(
            'verdict', 'Verdict',
            f'Move {cd_move!r} not found in gamemaster; cannot score.')
    cd_move_id = cd_move_entry['moveId']

    try:
        default_fast_id, _ = get_default_moveset(species, league)
    except KeyError as exc:
        return render_placeholder('verdict', 'Verdict',
                                  f'No default moveset: {exc}')

    cd_movesets = [m for m in dive['movesets']
                   if _moveset_fast_move(m['label']) == cd_move_id]
    default_movesets = [m for m in dive['movesets']
                        if _moveset_fast_move(m['label']) == default_fast_id]

    if not cd_movesets:
        return render_placeholder(
            'verdict', 'Verdict',
            f'No CD-move ({cd_move_id}) moveset in dive data; cannot score.')
    if not default_movesets:
        sys.exit(
            f"Dive has no old-default-moveset ({default_fast_id}); rebuild the "
            f"dive with the reference moveset included "
            f"(e.g. --reference {default_fast_id},<cm1>,<cm2>) so the verdict "
            f"can compare against it.")

    best_cd = max(cd_movesets, key=lambda m: m['win_rate'])
    best_default = max(default_movesets, key=lambda m: m['win_rate'])

    wins = ties = losses = 0
    exception_scenarios: list[tuple[list[int], float, float]] = []
    for sc, cd_rate, df_rate in zip(
        dive['scenarios'],
        best_cd['per_scenario_win_rate'],
        best_default['per_scenario_win_rate'],
    ):
        if cd_rate > df_rate:
            wins += 1
        elif cd_rate < df_rate:
            losses += 1
            exception_scenarios.append((sc, cd_rate, df_rate))
        else:
            ties += 1
            exception_scenarios.append((sc, cd_rate, df_rate))
    total = len(best_cd['per_scenario_win_rate'])

    headline = _classify_verdict(wins, ties, losses, total,
                                 cd_move_entry.get('name', cd_move))

    delta_pp = 100.0 * (best_cd['win_rate'] - best_default['win_rate'])
    body = (
        f'<code>{html.escape(best_cd["pretty_label"])}</code> wins '
        f'{100 * best_cd["win_rate"]:.1f}% of simulated matchups vs '
        f'<code>{html.escape(best_default["pretty_label"])}</code>\'s '
        f'{100 * best_default["win_rate"]:.1f}% ({delta_pp:+.1f} percentage points).'
    )
    exception_text = ''
    if exception_scenarios:
        parts = []
        for sc, cd_rate, df_rate in exception_scenarios:
            label = _scenario_label(sc)
            if cd_rate == df_rate == 0:
                parts.append(f'{label}, where neither moveset wins any matchup')
            elif cd_rate == df_rate:
                parts.append(f'{label}, tied at {100 * cd_rate:.1f}%')
            else:
                parts.append(
                    f'{label} ({100 * cd_rate:.1f}% vs {100 * df_rate:.1f}%)')
        exception_text = f' The exception: {"; ".join(parts)}.'

    return (
        f'<p class="verdict-line">'
        f'<strong>{html.escape(headline)}</strong> '
        f'{body}'
        f'{html.escape(exception_text)}'
        f'</p>'
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
                   article: dict, overrides: dict[str, str],
                   *, species: str, league: str, cd_move: str,
                   dive: dict | None) -> str:
    if heading in overrides:
        body_html = format_body(overrides[heading])
    elif section_id == 'intro':
        body_html = render_intro_section(article)
    elif section_id == 'move-comparison':
        body_html = _render_move_comparison_section(cd_move, species, league)
    elif section_id == 'verdict' and dive is not None:
        body_html = _render_verdict_section(cd_move, species, league, dive)
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

    try:
        dive = _load_dive_data(dive_dir)
    except (ValueError, KeyError) as exc:
        logger.warning('Could not load dive data from %s: %s', dive_dir, exc)
        dive = None

    species_name = article.get('species', '')
    sections_html = '\n\n'.join(
        render_section(sid, heading, todo, article, overrides,
                       species=species_name, league=league, cd_move=cd_move,
                       dive=dive)
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
  table.move-compare {{ border-collapse: collapse; margin: 12px 0;
                        width: 100%; font-size: 14px; }}
  table.move-compare th, table.move-compare td {{ border: 1px solid #0f3460;
        padding: 6px 10px; text-align: left; }}
  table.move-compare thead th {{ background: #16213e; color: #c8a2d0; }}
  table.move-compare tbody th {{ background: #12192e; color: #9ab0d8;
                                 font-weight: 500; }}
  table.move-compare tbody td {{ background: #0f162a; color: #e0e0e0; }}
  p.move-compare-note {{ color: #8ea1bd; font-size: 13px; margin-top: 4px; }}
  p.verdict-line {{ background: #1a2e1f; border-left: 3px solid #7db87d;
                    padding: 10px 14px; color: #cfe8cf; border-radius: 6px; }}
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
