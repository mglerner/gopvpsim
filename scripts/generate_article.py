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

from compare_loadouts import (  # type: ignore[import-not-found]
    COMPARE_CSS,
    build_comparison_fragment,
    load_loadout_data,
    parse_spec as parse_comparison_spec,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_DIR = REPO_ROOT / 'thresholds'
ARTICLES_SRC_DIR = REPO_ROOT / 'articles'
COMPARISONS_SRC_DIR = REPO_ROOT / 'comparisons'

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
    ('form-comparison', 'Male vs Female',
     'S10: pairwise win-rate delta between forms. Source: [form_comparison].spec in the article TOML.'),
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


OPP_IV_MODE_KEYS = ('pvpoke', 'pvpoke:nobait', 'rank1', 'rank1:nobait')


def _aggregate_wins(scores: list[int], n_ivs: int, n_s: int, n_o: int
                    ) -> dict:
    """Count wins into per-scenario / per-opponent / total summaries."""
    per_scenario_wins = [0] * n_s
    per_opponent_wins = [0] * n_o
    total_wins = 0
    for iv in range(n_ivs):
        base_iv = iv * n_s * n_o
        for si in range(n_s):
            base = base_iv + si * n_o
            w = 0
            for oi in range(n_o):
                if scores[base + oi] >= 500:
                    w += 1
                    per_opponent_wins[oi] += 1
            per_scenario_wins[si] += w
            total_wins += w
    per_scenario_n = n_ivs * n_o
    per_opponent_n = n_ivs * n_s
    expected = n_ivs * n_s * n_o
    return {
        'win_rate': total_wins / expected,
        'per_scenario_win_rate': [w / per_scenario_n for w in per_scenario_wins],
        'per_opponent_win_rate': [w / per_opponent_n for w in per_opponent_wins],
    }


def _load_one_dive_file(path: Path) -> dict:
    """Parse one dive HTML sibling into win-rate summaries.

    Reads the embedded DATA JSON for labels + scenario shape and
    decompresses every available SCORES_GZ variant to aggregate per
    (opp_iv_mode, bait_mode) into win-rate summaries. The 'pvpoke'
    (default-IV, bait-on) view is the top-level `win_rate` /
    `per_scenario_win_rate` / `per_opponent_win_rate` for backwards
    compat with callers that predate the toggle. Every variant is
    available in `variants[mode]` for the article's opponent-IV
    dropdown.
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

    n_ivs = data['nIvs']
    n_s = data['nScenarios']
    n_o = data['nOpponents']
    expected = n_ivs * n_s * n_o

    variants: dict[str, dict] = {}
    for mode in OPP_IV_MODE_KEYS:
        gz_key = f'0_{mode}'
        if gz_key not in scores_gz:
            continue
        scores = _decompress_scores(scores_gz[gz_key])
        if len(scores) != expected:
            raise ValueError(
                f'{path}: {gz_key} score length {len(scores)} != {expected}')
        variants[mode] = _aggregate_wins(scores, n_ivs, n_s, n_o)

    if 'pvpoke' not in variants:
        raise ValueError(f'{path}: SCORES_GZ missing 0_pvpoke')
    base = variants['pvpoke']

    return {
        'label': label,
        'pretty_label': pretty,
        'win_rate': base['win_rate'],
        'per_scenario_win_rate': base['per_scenario_win_rate'],
        'per_opponent_win_rate': base['per_opponent_win_rate'],
        'variants': variants,
        'scenarios': data['scenarios'],
        'opponents': data['opponents'],
        'opponent_label': data.get('opponentLabel') or '',
        'tiers': data.get('tiers') or [],
        'iv_tiers': data.get('ivTiers') or [],
        'iv_all_tiers': data.get('ivAllTiers') or [],
        'n_ivs': n_ivs,
    }


def _load_dive_data(dive_dir: Path) -> dict:
    """Load dive summary across all sibling HTML files in dive_dir.

    Each moveset entry carries its own per-opponent/per-scenario win-rate
    arrays plus the ``tiers`` / ``ivTiers`` blobs from that sibling's
    DATA. The top-level ``opponents`` list is the canonical opponent
    order shared across all siblings (they re-use the same scenario
    grid), so the article generator can trust index-alignment when
    comparing two movesets.
    """
    if not dive_dir.is_dir():
        sys.exit(f'Dive directory does not exist: {dive_dir}')
    files = sorted(dive_dir.glob('index.html')) + sorted(dive_dir.glob('index_m*.html'))
    if not files:
        sys.exit(f'No index*.html dive files in {dive_dir}')
    movesets = []
    scenarios = None
    opponents = None
    for f in files:
        parsed = _load_one_dive_file(f)
        movesets.append(parsed)
        if scenarios is None:
            scenarios = parsed['scenarios']
        if opponents is None:
            opponents = parsed['opponents']
    opponent_label = ''
    for m in movesets:
        if m.get('opponent_label'):
            opponent_label = m['opponent_label']
            break
    return {
        'movesets': movesets,
        'scenarios': scenarios,
        'opponents': opponents,
        'opponent_label': opponent_label,
    }


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


def _scenario_short(scenario: list[int]) -> str:
    """Tight column header for a shield scenario: ``0v0``, ``0v1``, etc."""
    return f'{scenario[0]}v{scenario[1]}'


def _wr_cell(wr: float) -> str:
    """Table cell for a win rate value. Green >50%, red <50%, neutral =50%.
    Uses the same delta-pos / delta-neg color classes as the matchup
    delta table so the article reads consistently.
    """
    cls = 'delta-pos' if wr > 0.5 else 'delta-neg' if wr < 0.5 else ''
    return f'<td class="num {cls}">{100 * wr:.1f}%</td>'


def _render_meta_coverage_per_form_section(cd_move: str, forms: list[dict],
                                           gm: dict) -> str:
    """Compact per-form x per-shield-scenario win-rate grid.

    Rows: one per form (each running its best CD moveset). Columns: the
    9 shield scenarios (0v0 through 2v2). Cells: win rate as a percentage,
    colored green above 50%, red below, neutral at exactly 50%. Keeps
    the view to 2 rows x 9 columns for two-form articles so readers can
    scan "where is each form strongest?" at a glance.
    """
    cd_entry = _lookup_move(gm, cd_move)
    cd_name = cd_entry.get('name', cd_move) if cd_entry else cd_move
    scenarios = forms[0]['best_cd'].get('scenarios') or []
    if not scenarios:
        return render_placeholder(
            'meta-coverage', 'Meta Coverage',
            'Dive data missing scenarios list; cannot render grid.')

    per_form_counts = sorted({len(f.get('opponents') or []) for f in forms})
    n_ivs = forms[0]['best_cd'].get('n_ivs', 0)
    if len(per_form_counts) == 1:
        n_opponents = per_form_counts[0]
        pool_phrase = f'{n_opponents} opponents'
        per_cell_sims = n_ivs * n_opponents
        sims_phrase = f' = {per_cell_sims:,} simulated matchups'
    else:
        pool_phrase = (f'{per_form_counts[0]}-{per_form_counts[-1]} '
                       f'opponents depending on form')
        sims_phrase = ''

    intro = (
        f'<p class="meta-coverage-intro">Each form\'s <code>'
        f'{html.escape(cd_name)}</code> win rate across all 9 shield '
        f'scenarios. Green above 50%, red below. Shield asymmetry '
        f'dominates the extremes - 2v0 is essentially a free win and '
        f'0v2 essentially a free loss regardless of species or form - '
        f'so the interesting reading is <em>within a column</em>: does '
        f'form choice swing the outcome at a given shield count? Most '
        f'players give the even-shield scenarios (0v0, 1v1, 2v2) more '
        f'weight when team-building, though shield use varies by '
        f'playstyle.</p>'
        f'<p class="meta-coverage-intro">Each cell averages <strong>'
        f'{n_ivs:,} focal IVs &times; {pool_phrase}</strong>'
        f'{sims_phrase} at that shield count. Opponents are held fixed '
        f'at PvPoke-default IVs (and moves) with bait-on behavior; '
        f'cells are <em>not</em> restricted to the rank-1 focal IV, '
        f'and they are <em>not</em> collapsed to a single default-vs-'
        f'default battle. Win = battle rating &ge; 500. Each form uses '
        f'its own dive\'s opponent pool (including a self-mirror but '
        f'not yet the sibling form as an opponent, which is why the '
        f'Matchup Delta table above reports a slightly smaller '
        f'intersection count).</p>'
    )

    header_cells = ['<th scope="col">Form</th>']
    for sc in scenarios:
        header_cells.append(
            f'<th scope="col" class="num" '
            f'title="{html.escape(_scenario_label(sc))}">'
            f'{_scenario_short(sc)}</th>'
        )

    body_rows = []
    for f in forms:
        col_cls = FORM_COL_CLASS.get(f['label'], '')
        col_suffix = f' {col_cls}' if col_cls else ''
        short = FORM_SYMBOLS.get(f['label'], html.escape(f['label']))
        form_label = f['label']
        row_cells = [
            f'<th scope="row" class="{col_cls}" title="{html.escape(form_label)}">'
            f'{short}</th>'
        ]
        rates = f['best_cd'].get('per_scenario_win_rate') or []
        for si, wr in enumerate(rates):
            # Same delta-pos/neg coloring as matchup-delta; no form-tint
            # on the cell background (the row header carries the form cue,
            # and tinting every cell would fight the green/red signal).
            cls = ('num delta-pos' if wr > 0.5
                   else 'num delta-neg' if wr < 0.5 else 'num')
            row_cells.append(
                f'<td class="{cls}" data-mc-form="{form_label}" '
                f'data-mc-sc="{si}">{100 * wr:.1f}%</td>'
            )
        body_rows.append(
            f'<tr class="meta-row{col_suffix}">' + ''.join(row_cells) + '</tr>'
        )

    control = _render_opp_iv_toggle_control()

    table = (
        '<table class="meta-coverage" id="mc-perform-table">'
        '<thead><tr>' + ''.join(header_cells) + '</tr></thead>'
        '<tbody>' + ''.join(body_rows) + '</tbody>'
        '</table>'
    )
    return control + '\n' + intro + '\n' + table


def _render_opp_iv_toggle_control() -> str:
    """Dropdown control that switches Meta Coverage and Matchup Delta
    between the four (Opponent IVs x Bait) variants. Other sections
    (Verdict, Form Comparison, IV Recommendations, Move Comparison)
    stay fixed at PvPoke-default + bait-on and ignore this toggle; the
    caption below the control calls that out so readers aren't
    surprised.
    """
    oppiv_options = ''.join(
        f'<option value="{html.escape(mode)}">{html.escape(label)}</option>'
        for mode, label in OPP_IV_MODE_LABELS.items()
    )
    bait_options = ''.join(
        f'<option value="{html.escape(mode)}">{html.escape(label)}</option>'
        for mode, label in BAIT_MODE_LABELS.items()
    )
    return (
        '<div class="article-opp-iv-control">'
        '<label><span class="control-label">Opponent IVs:</span> '
        f'<select class="article-opp-iv-mode">{oppiv_options}</select></label>'
        '<label><span class="control-label">Bait:</span> '
        f'<select class="article-bait-mode">{bait_options}</select></label>'
        '<p class="article-opp-iv-caption">This toggle rewrites the '
        'numbers in <strong>Meta Coverage</strong> (below) and '
        '<strong>Matchup Delta</strong> (next section). <strong>Verdict'
        '</strong>, <strong>Form Comparison</strong>, <strong>IV '
        'Recommendations</strong>, and <strong>Move Comparison</strong> '
        'stay at PvPoke-default opponent IVs with bait on, independent '
        'of this control. "Rank 1" uses each opponent\'s highest-'
        'stat-product IVs; "Never" disables bait-first shielding in the '
        'sim.</p>'
        '</div>'
    )


def _render_meta_coverage_section(cd_move: str, species: str,
                                  league: str, dive: dict) -> str:
    """Single-form fallback: one row showing the best CD moveset's WR per
    scenario. Used when no ``[form_comparison]`` is set in the article TOML.
    """
    cd_entry = _lookup_move(gm := load_gamemaster(), cd_move)
    cd_name = cd_entry.get('name', cd_move) if cd_entry else cd_move
    cd_id = cd_entry['moveId'] if cd_entry else None
    if cd_id is None:
        return render_placeholder(
            'meta-coverage', 'Meta Coverage',
            f'Move {cd_move!r} not found in gamemaster.')

    cd_movesets = [m for m in dive['movesets']
                   if _moveset_fast_move(m['label']) == cd_id]
    if not cd_movesets:
        return render_placeholder(
            'meta-coverage', 'Meta Coverage',
            f'No CD-move ({cd_id}) moveset in dive data.')
    best_cd = max(cd_movesets, key=lambda m: m['win_rate'])
    scenarios = dive.get('scenarios') or []
    if not scenarios:
        return render_placeholder(
            'meta-coverage', 'Meta Coverage',
            'Dive data missing scenarios list; cannot render grid.')

    n_ivs = best_cd.get('n_ivs', 0)
    n_opponents = len(dive.get('opponents') or [])
    per_cell_sims = n_ivs * n_opponents
    intro = (
        f'<p class="meta-coverage-intro"><code>{html.escape(cd_name)}</code> '
        f'win rate across all 9 shield scenarios. Green above 50%, red '
        f'below. Shield asymmetry dominates the extremes - 2v0 is '
        f'essentially a free win and 0v2 essentially a free loss - '
        f'and most players give the even-shield columns (0v0, 1v1, '
        f'2v2) more weight when team-building, though shield use '
        f'varies by playstyle.</p>'
        f'<p class="meta-coverage-intro">Each cell averages <strong>'
        f'{n_ivs:,} focal IVs &times; {n_opponents} opponents</strong> '
        f'= {per_cell_sims:,} simulated matchups at that shield count, '
        f'with opponents held fixed at PvPoke-default IVs (and moves) '
        f'with bait-on behavior. Win = battle rating &ge; 500. '
        f'Per-opponent detail is in the Matchup Delta table above.</p>'
    )
    header_cells = ['<th scope="col">Moveset</th>']
    for sc in scenarios:
        header_cells.append(
            f'<th scope="col" class="num" '
            f'title="{html.escape(_scenario_label(sc))}">'
            f'{_scenario_short(sc)}</th>'
        )
    row_cells = [
        f'<th scope="row">{html.escape(best_cd["pretty_label"] or best_cd["label"])}</th>'
    ]
    for wr in (best_cd.get('per_scenario_win_rate') or []):
        row_cells.append(_wr_cell(wr))
    table = (
        '<table class="meta-coverage">'
        '<thead><tr>' + ''.join(header_cells) + '</tr></thead>'
        '<tbody><tr>' + ''.join(row_cells) + '</tr></tbody>'
        '</table>'
    )
    return intro + '\n' + table


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


LEAGUE_CP = {'great': 1500, 'ultra': 2500, 'master': 10000}


def _species_id(gm: dict, species: str) -> str | None:
    """Return the gamemaster speciesId for a display-form name."""
    target = species.strip().lower()
    for p in gm['pokemon']:
        if (p.get('speciesName') or '').lower() == target:
            return p.get('speciesId')
    for p in gm['pokemon']:
        if (p.get('speciesId') or '').lower() == target.replace(' ', '_'):
            return p.get('speciesId')
    return None


def _species_move_pools(gm: dict, species_id: str) -> tuple[list[str], list[str]]:
    """Return (fastMovePool, chargedMovePool) sorted by moveId ascending.

    Mirrors PvPoke's Pokemon.js sort at the bottom of the pool setup, which
    determines the moveset indices used in battle/multi URLs.
    """
    for p in gm['pokemon']:
        if p.get('speciesId') == species_id:
            fm = sorted(p.get('fastMoves') or [])
            cm = sorted(p.get('chargedMoves') or [])
            return fm, cm
    return [], []


def _pvpoke_move_segment(gm: dict, species_id: str,
                         fast_move_id: str,
                         charged_move_ids: list[str]) -> str | None:
    """Build the '<fm>-<cm1>-<cm2>' segment PvPoke uses in battle URLs.

    Default encoding: fast index is 0-based into the sorted
    fastMovePool; charged indices are 1-based into the sorted
    chargedMovePool (PvPoke reserves 0 as the empty slot). Whenever a
    move isn't in the species' pool - typical for unreleased CD moves
    that haven't been added to the gamemaster upstream - PvPoke falls
    back to embedding the moveId string directly (Pokemon.js:2102-2117,
    the ``isCustom || hardMovesetLinks`` branch). The rendered CD-move
    segment looks like ``MUD_SLAP-1-3`` instead of ``0-1-3``; the
    server-side router accepts both forms. Returns None only when the
    species pool itself can't be resolved.
    """
    fm_pool, cm_pool = _species_move_pools(gm, species_id)
    if not fm_pool or not cm_pool:
        return None
    if fast_move_id in fm_pool:
        fm_part = str(fm_pool.index(fast_move_id))
    else:
        fm_part = fast_move_id  # custom / unreleased: moveId string
    cm_parts: list[str] = []
    for cm in charged_move_ids:
        if cm in cm_pool:
            cm_parts.append(str(cm_pool.index(cm) + 1))
        else:
            cm_parts.append(cm)
    while len(cm_parts) < 2:
        cm_parts.append('0')
    return f'{fm_part}-{cm_parts[0]}-{cm_parts[1]}'


def pvpoke_multi_battle_url(gm: dict, species_id: str, league: str,
                            shields: tuple[int, int],
                            fast_move_id: str,
                            charged_move_ids: list[str]) -> str | None:
    """Build a pvpoke.com battle/multi URL for this species + moveset.

    URL shape follows PvPoke's own RankingInterface.js construction:
        battle/multi/<cp>/all/<species>/<shields>/<fm>-<cm1>-<cm2>/2-1/
    where:
        - cp is league-capped (1500 / 2500 / 10000)
        - shields concatenates both starting shield counts (e.g. "11")
        - moveset segment is built by ``_pvpoke_move_segment``, which
          embeds moveIds directly for unreleased/custom moves
        - "2-1" = chargedMoveCount=2, shieldBaiting=1 (copied from
          PvPoke's own rankings link, so the landed page matches what
          users see from the rankings UI)

    Returns None only when the species' move pool can't be resolved.
    """
    cp = LEAGUE_CP.get(league)
    if cp is None:
        return None
    move_str = _pvpoke_move_segment(gm, species_id, fast_move_id, charged_move_ids)
    if move_str is None:
        return None
    shields_str = f'{shields[0]}{shields[1]}'
    return (f'https://pvpoke.com/battle/multi/{cp}/all/'
            f'{species_id}/{shields_str}/{move_str}/2-1/')


def _resolve_opponent_for_url(display_name: str) -> tuple[str, str, bool]:
    """Split an opponent row label into (url_species_id, base_species_name, is_shadow).

    - "Steelix"                  -> ("steelix", "Steelix", False)
    - "Steelix (Shadow)"         -> ("steelix_shadow", "Steelix", True)
    - "Medicham (atk-weighted)"  -> ("medicham", "Medicham", False)
    The URL species id matches PvPoke's aliasId for the battle page. The
    base species name is the one we feed to ``get_default_moveset`` to
    look up the reference moveset.
    """
    name = display_name
    if name.endswith(' (atk-weighted)'):
        name = name[:-len(' (atk-weighted)')]
    is_shadow = name.endswith(' (Shadow)')
    if is_shadow:
        name = name[:-len(' (Shadow)')]
    slug = name.lower().replace(' ', '_').replace('(', '').replace(')', '')
    if is_shadow:
        slug = slug + '_shadow'
    return slug, name, is_shadow


def pvpoke_single_battle_url(gm: dict, league: str, shields: tuple[int, int],
                             focal_species_id: str,
                             focal_fast_id: str,
                             focal_charged_ids: list[str],
                             opp_species_id: str,
                             opp_fast_id: str,
                             opp_charged_ids: list[str]) -> str | None:
    """Build a pvpoke.com single-battle URL for a specific 1v1 at default IVs.

    Shape mirrors PvPoke's RankingInterface.js:1090:
        battle/<cp>/<focal>/<opp>/<shields>/<fm1-cm1-cm2>/<fm2-cm1-cm2>/
    Both move index triples follow the same encoding as multi-battle
    URLs (fast 0-based, charged 1-based) but sourced from each species'
    own sorted move pool. Returns None if any pool lookup fails.
    """
    cp = LEAGUE_CP.get(league)
    if cp is None:
        return None
    focal_moves = _pvpoke_move_segment(
        gm, focal_species_id, focal_fast_id, focal_charged_ids)
    opp_moves = _pvpoke_move_segment(
        gm, opp_species_id, opp_fast_id, opp_charged_ids)
    if focal_moves is None or opp_moves is None:
        return None
    shields_str = f'{shields[0]}{shields[1]}'
    return (f'https://pvpoke.com/battle/{cp}/'
            f'{focal_species_id}/{opp_species_id}/{shields_str}/'
            f'{focal_moves}/{opp_moves}/')


def _parse_moveset_label(label: str) -> tuple[str, list[str]]:
    """Split 'FAST / CM1, CM2' into (fast_id, [cm1_id, cm2_id])."""
    if '/' not in label:
        return label.strip(), []
    fast, rest = label.split('/', 1)
    charged = [c.strip() for c in rest.split(',') if c.strip()]
    return fast.strip(), charged


def _collect_per_form_best_movesets(form_spec: dict, cd_move: str,
                                    gm: dict) -> list[dict] | None:
    """For each loadout in the form_comparison spec, load its dive and pick
    the best CD-move + best default-fast movesets. Returns one dict per
    form with aligned opponents / per-opponent win-rate arrays.

    Returns None if any loadout's dive is missing required movesets; the
    caller falls back to the single-form renderer in that case.
    """
    cd_entry = _lookup_move(gm, cd_move)
    if cd_entry is None:
        return None
    cd_id = cd_entry['moveId']
    league = form_spec['league']
    forms: list[dict] = []
    for lo_spec in form_spec['loadout_specs']:
        dive_dir = WEBSITE_DIR / lo_spec.dive_slug
        if not dive_dir.is_dir():
            return None
        try:
            dive_data = _load_dive_data(dive_dir)
        except SystemExit:
            return None
        try:
            default_fast_id, _ = get_default_moveset(lo_spec.species, league)
        except KeyError:
            return None
        cd_ms = [m for m in dive_data['movesets']
                 if _moveset_fast_move(m['label']) == cd_id]
        df_ms = [m for m in dive_data['movesets']
                 if _moveset_fast_move(m['label']) == default_fast_id]
        if not cd_ms or not df_ms:
            return None
        best_cd = max(cd_ms, key=lambda m: m['win_rate'])
        best_default = max(df_ms, key=lambda m: m['win_rate'])
        forms.append({
            'label': lo_spec.label,
            'species': lo_spec.species,
            'species_id': _species_id(gm, lo_spec.species),
            'dive_slug': lo_spec.dive_slug,
            'league': league,
            'best_cd': best_cd,
            'best_default': best_default,
            'opponents': dive_data['opponents'],
            'opponent_label': dive_data.get('opponent_label') or '',
            'default_fast_id': default_fast_id,
            'cd_id': cd_id,
        })
    return forms


OPP_IV_MODE_LABELS = {
    'pvpoke': 'PvPoke default',
    'rank1': 'Rank 1',
}
BAIT_MODE_LABELS = {
    'bait': 'Selective (bait on)',
    'nobait': 'Never (bait off)',
}


def _article_toggle_script(payload: dict, form_labels: list[str],
                           cd_name: str, default_name: str,
                           total_opponents: int) -> str:
    """Embed the variants payload + toggle JS handler.

    The handler binds ``change`` on the two selects the Meta Coverage
    section emitted and mutates Meta Coverage / Matchup Delta cells in
    place. Verdict / Form Comparison / IV Recommendations / Move
    Comparison are intentionally untouched; the caption above the
    dropdowns tells readers which sections respond to the control.
    """
    payload_json = json.dumps(payload)
    labels_json = json.dumps(form_labels)
    cd_json = json.dumps(cd_name)
    default_json = json.dumps(default_name)
    # Total count is embedded as a literal since it's stable across
    # variants (opp-IV mode doesn't add or drop opponents).
    script = (
        '<script>\n'
        f'var ARTICLE_VARIANTS = {payload_json};\n'
        f'var ARTICLE_FORM_LABELS = {labels_json};\n'
        f'var ARTICLE_CD_NAME = {cd_json};\n'
        f'var ARTICLE_DEFAULT_NAME = {default_json};\n'
        f'var ARTICLE_TOTAL_OPPS = {total_opponents};\n'
        '(function() {\n'
        '  function wrSide(wr) {\n'
        '    if (wr > 0.5) return 1; if (wr < 0.5) return -1; return 0;\n'
        '  }\n'
        '  function fmtDelta(d) {\n'
        "    return (d >= 0 ? '+' : '') + d.toFixed(1);\n"
        '  }\n'
        '  function applyMetaCoverage(variant) {\n'
        '    ARTICLE_FORM_LABELS.forEach(function(lbl) {\n'
        '      var fd = variant[lbl]; if (!fd) return;\n'
        '      fd.cd.per_sc.forEach(function(wr, i) {\n'
        "        var cell = document.querySelector('td[data-mc-form=\"' + lbl + '\"][data-mc-sc=\"' + i + '\"]');\n"
        '        if (!cell) return;\n'
        "        cell.textContent = (100 * wr).toFixed(1) + '%';\n"
        "        cell.classList.remove('delta-pos');\n"
        "        cell.classList.remove('delta-neg');\n"
        "        if (wr > 0.5) cell.classList.add('delta-pos');\n"
        "        else if (wr < 0.5) cell.classList.add('delta-neg');\n"
        '      });\n'
        '    });\n'
        '  }\n'
        '  function applyMatchupDelta(variant) {\n'
        "    var table = document.getElementById('mf-split-perform');\n"
        '    if (!table) return;\n'
        "    var rows = table.querySelectorAll('tbody tr[data-opponent]');\n"
        '    var flipsPerForm = {};\n'
        '    ARTICLE_FORM_LABELS.forEach(function(f) { flipsPerForm[f] = 0; });\n'
        '    rows.forEach(function(row) {\n'
        "      var opp = row.getAttribute('data-opponent');\n"
        '      var anyFlip = false, anyPos = false, anyNeg = false;\n'
        '      var cdSides = {};\n'
        '      ARTICLE_FORM_LABELS.forEach(function(lbl) {\n'
        '        var fd = variant[lbl]; if (!fd) return;\n'
        '        var cdr = fd.cd.per_opp[opp]; var dfr = fd.df.per_opp[opp];\n'
        '        if (cdr == null || dfr == null) return;\n'
        '        var delta = 100 * (cdr - dfr);\n'
        '        var flip = (cdr >= 0.5) !== (dfr >= 0.5);\n'
        '        cdSides[String(wrSide(cdr))] = true;\n'
        '        if (flip) {\n'
        '          anyFlip = true; flipsPerForm[lbl]++;\n'
        '          if (delta > 0) anyPos = true; else anyNeg = true;\n'
        '        }\n'
        "        var deltaCell = row.querySelector('td[data-md-role=\"' + lbl + '-delta\"]');\n"
        '        if (deltaCell) {\n'
        '          deltaCell.textContent = fmtDelta(delta);\n'
        "          deltaCell.classList.remove('delta-pos');\n"
        "          deltaCell.classList.remove('delta-neg');\n"
        "          if (delta > 0) deltaCell.classList.add('delta-pos');\n"
        "          else if (delta < 0) deltaCell.classList.add('delta-neg');\n"
        '        }\n'
        "        var dfCell = row.querySelector('td[data-md-role=\"' + lbl + '-df-wr\"]');\n"
        "        if (dfCell) dfCell.textContent = (100 * dfr).toFixed(1) + '%';\n"
        "        var cdCell = row.querySelector('td[data-md-role=\"' + lbl + '-cd-wr\"]');\n"
        "        if (cdCell) cdCell.textContent = (100 * cdr).toFixed(1) + '%';\n"
        "        var flipCell = row.querySelector('td[data-md-role=\"' + lbl + '-flip\"]');\n"
        '        if (flipCell) {\n'
        "          var badge = flipCell.querySelector('.flip-badge');\n"
        '          if (badge) {\n'
        "            var cls, text, tip;\n"
        '            if (flip) {\n'
        "              if (delta > 0) {\n"
        "                cls = 'flip-pos'; text = '+Flip';\n"
        "                tip = lbl + ': ' + ARTICLE_CD_NAME + ' wins this matchup where the old default loses it (crosses the 50% line).';\n"
        '              } else {\n'
        "                cls = 'flip-neg'; text = '-Flip';\n"
        "                tip = lbl + ': old default wins this matchup where ' + ARTICLE_CD_NAME + ' loses it (crosses the 50% line).';\n"
        '              }\n'
        '            } else {\n'
        "              cls = 'flip-none'; text = 'No flip';\n"
        "              if (cdr >= 0.5 && dfr >= 0.5) tip = lbl + ': both movesets win on aggregate.';\n"
        "              else if (cdr < 0.5 && dfr < 0.5) tip = lbl + ': both movesets lose on aggregate.';\n"
        "              else tip = lbl + ': no flip across the 50% line.';\n"
        '            }\n'
        "            var unlinked = badge.classList.contains('flip-unlinked');\n"
        "            badge.className = 'flip-badge ' + cls + (unlinked ? ' flip-unlinked' : '');\n"
        '            badge.textContent = text;\n'
        "            badge.setAttribute('title', tip);\n"
        '          }\n'
        '        }\n'
        '      });\n'
        "      var rowCls = '';\n"
        "      if (anyFlip && anyPos && !anyNeg) rowCls = 'matchup-delta-flip matchup-delta-flip-pos';\n"
        "      else if (anyFlip && anyNeg && !anyPos) rowCls = 'matchup-delta-flip matchup-delta-flip-neg';\n"
        "      else if (anyFlip) rowCls = 'matchup-delta-flip';\n"
        '      row.className = rowCls;\n'
        "      row.setAttribute('data-form-split', Object.keys(cdSides).length > 1 ? 'split' : 'same');\n"
        '    });\n'
        "    var summary = document.getElementById('md-perform-summary');\n"
        '    if (summary) {\n'
        '      var parts = ARTICLE_FORM_LABELS.map(function(f) {\n'
        "        return f + ': ' + flipsPerForm[f];\n"
        "      }).join(', ');\n"
        "      summary.textContent = 'Flips across the 50% win line by form (out of ' + ARTICLE_TOTAL_OPPS + ' opponents): ' + parts + '.';\n"
        '    }\n'
        "    var splitCount = table.querySelectorAll('tbody tr[data-form-split=\"split\"]').length;\n"
        "    var countSpan = document.querySelector('.mf-split-count');\n"
        '    if (countSpan) countSpan.textContent = splitCount;\n'
        '  }\n'
        '  function applyToggle() {\n'
        "    var oppSel = document.querySelector('.article-opp-iv-mode');\n"
        "    var baitSel = document.querySelector('.article-bait-mode');\n"
        '    if (!oppSel || !baitSel) return;\n'
        "    var key = baitSel.value === 'nobait' ? oppSel.value + ':nobait' : oppSel.value;\n"
        '    var variant = ARTICLE_VARIANTS[key];\n'
        '    if (!variant) return;\n'
        '    applyMetaCoverage(variant);\n'
        '    applyMatchupDelta(variant);\n'
        '  }\n'
        '  function bind() {\n'
        "    document.querySelectorAll('.article-opp-iv-mode, .article-bait-mode').forEach(function(sel) {\n"
        "      sel.addEventListener('change', applyToggle);\n"
        '    });\n'
        '  }\n'
        "  if (document.readyState === 'loading') {\n"
        "    document.addEventListener('DOMContentLoaded', bind);\n"
        '  } else {\n'
        '    bind();\n'
        '  }\n'
        '})();\n'
        '</script>\n'
    )
    return script


def _build_variants_payload(forms: list[dict]) -> dict:
    """Return a JSON-serialisable mapping of opp-IV-mode keys to per-form
    win-rate data for use by the article's opponent-IV dropdown.

    Shape:
        {
          'pvpoke': {
            'Male': {
              'cd': {'per_opp': {opp: wr, ...}, 'per_sc': [wr, ...], 'wr': x},
              'df': {...}
            },
            'Female': {...}
          },
          'pvpoke:nobait': {...}, 'rank1': {...}, 'rank1:nobait': {...}
        }

    Per-opponent lookup is keyed by opponent name (the same string used
    in the Matchup Delta rows' ``data-opponent`` attribute) so the JS
    toggle can address cells without relying on index alignment.
    """
    payload: dict[str, dict] = {}
    modes = set()
    for f in forms:
        modes.update((f['best_cd'].get('variants') or {}).keys())
        modes.update((f['best_default'].get('variants') or {}).keys())
    for mode in modes:
        payload[mode] = {}
        for f in forms:
            cd = f['best_cd']
            df = f['best_default']
            cd_var = (cd.get('variants') or {}).get(mode)
            df_var = (df.get('variants') or {}).get(mode)
            if cd_var is None or df_var is None:
                continue
            opponents = f['opponents']
            cd_by_opp = dict(zip(opponents, cd_var['per_opponent_win_rate']))
            df_by_opp = dict(zip(opponents, df_var['per_opponent_win_rate']))
            payload[mode][f['label']] = {
                'cd': {
                    'wr': cd_var['win_rate'],
                    'per_sc': cd_var['per_scenario_win_rate'],
                    'per_opp': cd_by_opp,
                },
                'df': {
                    'wr': df_var['win_rate'],
                    'per_sc': df_var['per_scenario_win_rate'],
                    'per_opp': df_by_opp,
                },
            }
    return payload


def _render_matchup_delta_per_form_section(cd_move: str, forms: list[dict],
                                           gm: dict) -> str:
    """Wide per-form matchup-delta table: each form contributes 4 columns
    (old WR, CD WR, signed delta, flip badge) alongside the shared opponent
    column. Rows sort by the mean delta across forms so the biggest
    overall improvements lead; readers can click any column header to
    re-sort.
    """
    cd_entry = _lookup_move(gm, cd_move)
    cd_name = cd_entry.get('name', cd_move) if cd_entry else cd_move

    shared = set(forms[0]['opponents'])
    for f in forms[1:]:
        shared &= set(f['opponents'])
    ordered_opponents = [o for o in forms[0]['opponents'] if o in shared]

    rows = []
    per_form_flip_count = [0] * len(forms)
    shields = (1, 1)

    entries = []
    for opp in ordered_opponents:
        per_form_cells = []
        deltas = []
        for fi, f in enumerate(forms):
            cd_map = dict(zip(f['opponents'], f['best_cd']['per_opponent_win_rate']))
            df_map = dict(zip(f['opponents'], f['best_default']['per_opponent_win_rate']))
            cd_r = cd_map[opp]
            df_r = df_map[opp]
            delta_pp = 100.0 * (cd_r - df_r)
            deltas.append(delta_pp)
            per_form_cells.append((f, cd_r, df_r, delta_pp))
        mean_delta = sum(deltas) / len(deltas)
        entries.append((opp, per_form_cells, mean_delta))

    entries.sort(key=lambda e: e[2], reverse=True)

    def _badge_and_class(f, cd_r, df_r, delta_pp, opp) -> tuple[str, str]:
        cd_wins = cd_r >= 0.5
        df_wins = df_r >= 0.5
        flip = cd_wins != df_wins
        opp_slug, opp_base, opp_is_shadow = _resolve_opponent_for_url(opp)
        fast_id = _parse_moveset_label(f['best_cd']['label'])[0]
        charged_ids = _parse_moveset_label(f['best_cd']['label'])[1]
        opp_url: str | None = None
        if f['species_id']:
            try:
                opp_fast_id, opp_charged_ids = get_default_moveset(
                    opp_base, f['league'], shadow=opp_is_shadow)
            except KeyError:
                opp_fast_id, opp_charged_ids = None, None
            if opp_fast_id:
                opp_url = pvpoke_single_battle_url(
                    gm, f['league'], shields,
                    focal_species_id=f['species_id'],
                    focal_fast_id=fast_id,
                    focal_charged_ids=charged_ids,
                    opp_species_id=opp_slug,
                    opp_fast_id=opp_fast_id,
                    opp_charged_ids=list(opp_charged_ids or []),
                )

        form_label = html.escape(f['label'])
        if flip:
            flip_dir = 'pos' if delta_pp > 0 else 'neg'
            cls = f'flip-badge flip-{flip_dir}'
            text = '+Flip' if delta_pp > 0 else '-Flip'
            if delta_pp > 0:
                tip = (f'{form_label}: {cd_name} wins this matchup where the '
                       f'old default loses it (crosses the 50% line).')
            else:
                tip = (f'{form_label}: old default wins this matchup where '
                       f'{cd_name} loses it (crosses the 50% line).')
        else:
            cls = 'flip-badge flip-none'
            text = 'No flip'
            if cd_r >= 0.5 and df_r >= 0.5:
                tip = f'{form_label}: both movesets win on aggregate.'
            elif cd_r < 0.5 and df_r < 0.5:
                tip = f'{form_label}: both movesets lose on aggregate.'
            else:
                tip = f'{form_label}: no flip across the 50% line.'

        if opp_url:
            badge = (f'<a class="{cls}" href="{html.escape(opp_url)}" '
                     f'target="_blank" rel="noopener" '
                     f'title="{html.escape(tip)}">{text}</a>')
        else:
            badge = (f'<span class="{cls} flip-unlinked" '
                     f'title="{html.escape(tip)}">{text}</span>')
        return badge, ('flip' if flip else 'noflip')

    def _col_class(label: str) -> str:
        low = label.lower()
        return low if low in ('male', 'female') else ''

    def _wr_side(wr: float) -> int:
        """Three-way classifier for win-rate vs the 50% line.
        Returns 1 (win), -1 (loss), or 0 (coin-flip, exactly 0.5). Exactly
        50% is its own bucket so a 55%-vs-50% pair counts as a disagreement
        rather than both being lumped as wins.
        """
        if wr > 0.5:
            return 1
        if wr < 0.5:
            return -1
        return 0

    body_rows = []
    form_split_count = 0
    for opp, per_form_cells, mean_delta in entries:
        any_flip = False
        any_positive = False
        any_negative = False
        cd_sides = {_wr_side(cd_r) for _, cd_r, _, _ in per_form_cells}
        form_split = len(cd_sides) > 1
        if form_split:
            form_split_count += 1
        verdict_cells: list[str] = []
        diag_cells: list[str] = []
        for fi, (f, cd_r, df_r, delta_pp) in enumerate(per_form_cells):
            badge, flip_tag = _badge_and_class(f, cd_r, df_r, delta_pp, opp)
            if flip_tag == 'flip':
                any_flip = True
                per_form_flip_count[fi] += 1
                if delta_pp > 0:
                    any_positive = True
                else:
                    any_negative = True
            col = _col_class(f['label'])
            col_suffix = f' {col}' if col else ''
            form_label = f['label']
            delta_cls = ('num delta-pos' if delta_pp > 0
                         else 'num delta-neg' if delta_pp < 0
                         else 'num')
            verdict_cells.append(
                f'<td class="{delta_cls}{col_suffix}" '
                f'data-md-role="{form_label}-delta">{delta_pp:+.1f}</td>')
            flip_td_cls = col if col else ''
            if flip_td_cls:
                verdict_cells.append(
                    f'<td class="{flip_td_cls}" '
                    f'data-md-role="{form_label}-flip">{badge}</td>')
            else:
                verdict_cells.append(
                    f'<td data-md-role="{form_label}-flip">{badge}</td>')
            diag_prefix = ' diag-start' if fi == 0 else ''
            diag_cells.append(
                f'<td class="num{diag_prefix}{col_suffix}" '
                f'data-md-role="{form_label}-df-wr">{100 * df_r:.1f}%</td>')
            diag_cells.append(
                f'<td class="num{col_suffix}" '
                f'data-md-role="{form_label}-cd-wr">{100 * cd_r:.1f}%</td>')
        if any_flip and any_positive and not any_negative:
            row_cls = 'matchup-delta-flip matchup-delta-flip-pos'
        elif any_flip and any_negative and not any_positive:
            row_cls = 'matchup-delta-flip matchup-delta-flip-neg'
        elif any_flip:
            row_cls = 'matchup-delta-flip'
        else:
            row_cls = ''
        split_attr = ' data-form-split="split"' if form_split else ' data-form-split="same"'
        row = (
            f'<tr class="{row_cls}"{split_attr} '
            f'data-opponent="{html.escape(opp, quote=True)}">'
            f'<td>{html.escape(opp)}</td>'
            + ''.join(verdict_cells)
            + ''.join(diag_cells)
            + '</tr>'
        )
        body_rows.append(row)

    # Header: Opponent | (Δ + Flip) per form | (old WR + new WR) per form.
    # Full form names live in tooltips; short symbols (♂/♀) go in the
    # visible header to keep the 9-column table compact.
    def _short(label: str) -> str:
        return {'Male': '&#9794;', 'Female': '&#9792;'}.get(label, html.escape(label))

    header_cells = ['<th scope="col" data-sort="str">Opponent</th>']
    # Verdict half: Δ and Flip for each form.
    for f in forms:
        flabel = html.escape(f['label'])
        fshort = _short(f['label'])
        col = _col_class(f['label'])
        col_suffix = f' {col}' if col else ''
        header_cells.append(
            f'<th scope="col" class="num{col_suffix}" data-sort="num" '
            f'title="{flabel} change in win rate in percentage points '
            f'(CD minus old default).">{fshort} &#916; (pp)</th>'
        )
        flip_class_attr = f' class="{col}"' if col else ''
        header_cells.append(
            f'<th scope="col"{flip_class_attr} data-sort="bool" '
            f'title="{flabel}: whether the aggregate matchup crosses '
            f'the 50% win line.">{fshort} Flip?</th>'
        )
    # Diagnostic half: old WR then new WR for each form.
    for fi, f in enumerate(forms):
        flabel = html.escape(f['label'])
        fshort = _short(f['label'])
        default_name = f['default_fast_id'].replace('_', ' ').title()
        col = _col_class(f['label'])
        col_suffix = f' {col}' if col else ''
        diag_cls = ' diag-start' if fi == 0 else ''
        header_cells.append(
            f'<th scope="col" class="num{diag_cls}{col_suffix}" '
            f'data-sort="pct" '
            f'title="{flabel} win rate with the old default fast move '
            f'({default_name}).">{fshort} {default_name} WR</th>'
        )
        header_cells.append(
            f'<th scope="col" class="num{col_suffix}" data-sort="pct" '
            f'title="{flabel} win rate with the CD move ({html.escape(cd_name)}).">'
            f'{fshort} {html.escape(cd_name)} WR</th>'
        )

    # Default sort: the mean-delta column isn't present, so fall back to
    # the first form's delta (col index 3) which is a useful proxy.
    intro_lines = [
        '<p class="matchup-delta-intro">Per-opponent win-rate deltas for '
        'each form side-by-side: old-default fast move vs the CD fast '
        'move. Click any column header to re-sort.</p>'
    ]
    pool_label = (forms[0].get('opponent_label') or '').strip()
    if pool_label:
        intro_lines.append(
            f'<p class="matchup-delta-pool"><strong>Opponents:</strong> '
            f'{len(ordered_opponents)} species shared across both form '
            f'dives ({html.escape(pool_label)}).</p>'
        )

    n_ivs = forms[0]['best_cd'].get('n_ivs', 0)
    n_scenarios = len(forms[0]['best_cd'].get('scenarios') or []) or 9
    per_cell_sims = n_ivs * n_scenarios
    intro_lines.append(
        f'<p class="matchup-delta-intro">Each cell averages <strong>'
        f'{n_ivs:,} focal IVs &times; {n_scenarios} shield scenarios '
        f'= {per_cell_sims:,} simulated matchups</strong> at one (form, '
        f'opponent) pair. Cells are <em>not</em> restricted to the '
        f'rank-1 focal IV and <em>not</em> collapsed to a single '
        f'default-vs-default battle. The Opponent IVs / Bait toggle '
        f'above Meta Coverage rewrites these numbers to alternate '
        f'variants (Rank 1 opponents, bait-off shielding, etc.); the '
        f'default view shows PvPoke-default opponent IVs with bait on. '
        f'Win = battle rating &ge; 500.</p>'
    )

    moveset_lines = ['<ul class="matchup-delta-movesets">']
    for f in forms:
        flabel = html.escape(f['label'])
        for which, ms in (('CD', f['best_cd']),
                          ('Old default', f['best_default'])):
            fast, cms = _parse_moveset_label(ms['label'])
            pretty = html.escape(ms['pretty_label'] or ms['label'])
            url = (pvpoke_multi_battle_url(gm, f['species_id'], f['league'],
                                           shields, fast, cms)
                   if f['species_id'] else None)
            if url:
                link_txt = (f'<li>{flabel} {which}: <code>{pretty}</code> - '
                            f'<a href="{html.escape(url)}" target="_blank" '
                            f'rel="noopener">view on PvPoke multi-battle</a></li>')
            else:
                link_txt = f'<li>{flabel} {which}: <code>{pretty}</code></li>'
            moveset_lines.append(link_txt)
    moveset_lines.append('</ul>')

    delta_help = (
        '<details class="matchup-delta-legend">'
        '<summary>How to read the &#916; column</summary>'
        '<p>The &#916; measures how much the CD move changed '
        '<em>this form\'s</em> win rate against this opponent, not which '
        'form is stronger. A form that was already winning with the old '
        'move has less room to gain than one that was losing. '
        'Hypothetical: &#9794; goes 30% &rarr; 50% (&#916; +20), &#9792; '
        'goes 55% &rarr; 60% (&#916; +5) on the same opponent. &#9792; is '
        'stronger both before and after, but the CD move was a bigger '
        'upgrade for &#9794; because &#9794; had more room to grow.</p>'
        '</details>'
    )
    moveset_lines.append(delta_help)

    summary_bits = ', '.join(
        f'{html.escape(f["label"])}: {per_form_flip_count[fi]}'
        for fi, f in enumerate(forms)
    )

    form_labels = ' and '.join(
        f'<span class="form-label {_col_class(f["label"])}">'
        f'{_short(f["label"])}</span>'
        for f in forms
    )
    filter_control = (
        '<p class="mf-split-filter">'
        '<label><input type="checkbox" class="mf-split-toggle" '
        'data-target="mf-split-perform"> '
        f'Show only matchups where {form_labels} disagree at the 50% '
        f'win line after evolving to {html.escape(cd_name)} - i.e. one '
        f'form wins on aggregate (above 50%), loses (below 50%), or ties '
        f'(exactly 50%) while the other lands in a different bucket '
        f'(<span class="mf-split-count">{form_split_count}</span> of '
        f'{len(entries)} opponents).</label></p>'
    )
    table = (
        filter_control
        + '<div class="matchup-delta-scroll">'
        '<table id="mf-split-perform" '
        'class="matchup-delta matchup-delta-perform sortable" '
        'data-default-sort="1" data-default-dir="desc">'
        '<thead><tr>' + ''.join(header_cells) + '</tr></thead>'
        '<tbody>' + ''.join(body_rows) + '</tbody>'
        '</table>'
        '</div>'
    )

    payload = _build_variants_payload(forms)
    default_fast_id = forms[0].get('default_fast_id') or ''
    default_name = default_fast_id.replace('_', ' ').title() if default_fast_id else 'old default'
    form_labels = [f['label'] for f in forms]
    toggle_script = _article_toggle_script(
        payload=payload,
        form_labels=form_labels,
        cd_name=cd_name,
        default_name=default_name,
        total_opponents=len(entries),
    )
    # Give the flip-summary paragraph an id so the JS can rewrite it
    # when the toggle changes; also the matchup-delta-summary wrapper.
    summary = (f'<p id="md-perform-summary" class="matchup-delta-summary">'
               f'Flips across the 50% win line by form (out of '
               f'{len(entries)} opponents): {summary_bits}.</p>')

    return ('\n'.join(intro_lines) + '\n'
            + '\n'.join(moveset_lines) + '\n'
            + table + '\n' + summary + '\n' + toggle_script)

    return ('\n'.join(intro_lines) + '\n'
            + '\n'.join(moveset_lines) + '\n'
            + table + '\n' + summary)


def _render_matchup_delta_section(cd_move: str, species: str, league: str,
                                  dive: dict) -> str:
    """Per-opponent win-rate diff between best CD and best old-default moveset.

    Rows sort by signed Δ descending so the biggest CD improvements lead.
    A "flip" badge marks rows where the sign crosses the 50% win axis in
    either direction - same axis the verdict section uses, so callouts are
    consistent across the article.
    """
    gm = load_gamemaster()
    cd_entry = _lookup_move(gm, cd_move)
    if cd_entry is None:
        return render_placeholder(
            'matchup-delta', 'Matchup Delta',
            f'Move {cd_move!r} not found in gamemaster; cannot render table.')
    cd_id = cd_entry['moveId']

    try:
        default_fast_id, _ = get_default_moveset(species, league)
    except KeyError as exc:
        return render_placeholder('matchup-delta', 'Matchup Delta',
                                  f'No default moveset: {exc}')

    cd_movesets = [m for m in dive['movesets']
                   if _moveset_fast_move(m['label']) == cd_id]
    default_movesets = [m for m in dive['movesets']
                        if _moveset_fast_move(m['label']) == default_fast_id]
    if not cd_movesets or not default_movesets:
        return render_placeholder(
            'matchup-delta', 'Matchup Delta',
            f'Dive missing CD ({cd_id}) or default ({default_fast_id}) moveset.')

    best_cd = max(cd_movesets, key=lambda m: m['win_rate'])
    best_default = max(default_movesets, key=lambda m: m['win_rate'])

    opponents = dive['opponents']
    if (len(best_cd['per_opponent_win_rate']) != len(opponents)
            or len(best_default['per_opponent_win_rate']) != len(opponents)):
        return render_placeholder(
            'matchup-delta', 'Matchup Delta',
            'Per-opponent arrays do not match opponent list length.')

    species_id = _species_id(gm, species)
    shields_pair = (1, 1)
    cd_fast, cd_cms = _parse_moveset_label(best_cd['label'])
    df_fast, df_cms = _parse_moveset_label(best_default['label'])
    cd_url = (pvpoke_multi_battle_url(gm, species_id, league, shields_pair,
                                      cd_fast, cd_cms)
              if species_id else None)
    df_url = (pvpoke_multi_battle_url(gm, species_id, league, shields_pair,
                                      df_fast, df_cms)
              if species_id else None)

    def _link_item(ms: dict, url: str | None) -> str:
        label = html.escape(ms['pretty_label'] or ms['label'])
        if url:
            return (f'<li><code>{label}</code> - '
                    f'<a href="{html.escape(url)}" target="_blank" rel="noopener">'
                    f'view on PvPoke multi-battle</a></li>')
        return f'<li><code>{label}</code></li>'

    pool_label = (dive.get('opponent_label') or '').strip()
    pool_line = ''
    if pool_label:
        pool_line = (
            f'<p class="matchup-delta-pool"><strong>Opponents:</strong> '
            f'{len(opponents)} species - {html.escape(pool_label)}. '
            f'This is the opponent pool the deep dive was simulated against; '
            f'pool recipes live in <code>opponent_pools/</code>. '
            f'For the Great League default (<code>gl_top50_plus_cs.txt</code>) '
            f'that is the top 50 overall PvPoke rankings unioned with the '
            f'Championship Series group, plus the focal species itself and any '
            f'atk-weighted IV variants the shared thresholds file specifies.</p>'
        )

    header_lines = [
        '<p class="matchup-delta-intro">Per-opponent breakdown of how the '
        'Community Day moveset compares to the old default, aggregated '
        'across all shield scenarios and every IV spread of the focal '
        'species. Click a column header to sort; column definitions are '
        'below.</p>',
    ]
    if pool_line:
        header_lines.append(pool_line)
    header_lines.extend([
        '<ul class="matchup-delta-movesets">',
        _link_item(best_cd, cd_url),
        _link_item(best_default, df_url),
        '</ul>',
    ])

    rows = []
    cd_rates = best_cd['per_opponent_win_rate']
    df_rates = best_default['per_opponent_win_rate']
    flip_count = 0
    for name, cd_r, df_r in zip(opponents, cd_rates, df_rates):
        delta_pp = 100.0 * (cd_r - df_r)
        cd_wins_side = cd_r >= 0.5
        df_wins_side = df_r >= 0.5
        flip = cd_wins_side != df_wins_side
        if flip:
            flip_count += 1
        rows.append((name, cd_r, df_r, delta_pp, flip))

    rows.sort(key=lambda r: r[3], reverse=True)

    cd_name_plain = cd_entry.get('name', cd_move)
    default_entry_for_flip = _lookup_move(gm, default_fast_id)
    default_name_plain = (default_entry_for_flip.get('name', default_fast_id)
                          if default_entry_for_flip else default_fast_id)

    drill_shields = (1, 1)
    link_suffix = (
        f'1-1 shields, {species} at PvPoke-default IVs with '
        f'{cd_name_plain}, opponent at PvPoke-default IVs and moveset. '
        f'The aggregate table row averages over all 4096 {species} IVs '
        f'and all 9 shield scenarios, so a single battle may not land '
        f'on the majority side.'
    )

    body_rows = []
    for name, cd_r, df_r, delta_pp, flip in rows:
        opp_slug, opp_base, opp_is_shadow = _resolve_opponent_for_url(name)
        opp_url = None
        if species_id is not None:
            try:
                opp_fast_id, opp_charged_ids = get_default_moveset(
                    opp_base, league, shadow=opp_is_shadow)
            except KeyError:
                opp_fast_id, opp_charged_ids = None, None
            if opp_fast_id:
                opp_url = pvpoke_single_battle_url(
                    gm, league, drill_shields,
                    focal_species_id=species_id,
                    focal_fast_id=cd_fast, focal_charged_ids=cd_cms,
                    opp_species_id=opp_slug,
                    opp_fast_id=opp_fast_id,
                    opp_charged_ids=list(opp_charged_ids or []),
                )

        if flip:
            flip_dir = 'pos' if delta_pp > 0 else 'neg'
            row_class = f'matchup-delta-flip matchup-delta-flip-{flip_dir}'
            badge_class = f'flip-badge flip-{flip_dir}'
            if delta_pp > 0:
                label = '+Flip'
                verdict = (f'{cd_name_plain} wins this matchup where '
                           f'{default_name_plain} loses it (aggregate win '
                           f'rate crosses the 50% line).')
            else:
                label = '-Flip'
                verdict = (f'{default_name_plain} wins this matchup where '
                           f'{cd_name_plain} loses it (aggregate win rate '
                           f'crosses the 50% line).')
        else:
            row_class = ''
            badge_class = 'flip-badge flip-none'
            label = 'No flip'
            if cd_r >= 0.5 and df_r >= 0.5:
                verdict = (f'Both movesets win this matchup on aggregate '
                           f'(both above 50%).')
            elif cd_r < 0.5 and df_r < 0.5:
                verdict = (f'Both movesets lose this matchup on aggregate '
                           f'(both below 50%).')
            else:
                verdict = 'No flip across the 50% line.'

        tooltip = f'{verdict} Opens in PvPoke: {link_suffix}'
        if opp_url:
            badge_html = (
                f'<a class="{badge_class}" href="{html.escape(opp_url)}" '
                f'target="_blank" rel="noopener" '
                f'title="{html.escape(tooltip)}">{label}</a>'
            )
        else:
            badge_html = (
                f'<span class="{badge_class} flip-unlinked" '
                f'title="{html.escape(verdict)} (PvPoke link unavailable '
                f'for this opponent.)">{label}</span>'
            )

        delta_class = 'delta-pos' if delta_pp > 0 else 'delta-neg' if delta_pp < 0 else ''
        body_rows.append(
            f'<tr class="{row_class}">'
            f'<td>{html.escape(name)}</td>'
            f'<td>{100 * df_r:.1f}%</td>'
            f'<td>{100 * cd_r:.1f}%</td>'
            f'<td class="{delta_class}">{delta_pp:+.1f}</td>'
            f'<td>{badge_html}</td>'
            f'</tr>'
        )

    cd_name = html.escape(cd_name_plain)
    default_name = html.escape(default_name_plain)

    species_name = html.escape(species)
    legend = (
        '<details class="matchup-delta-legend" open>'
        '<summary><strong>What the columns mean</strong></summary>'
        '<ul>'
        f'<li><strong>{default_name} Win Rate</strong> / '
        f'<strong>{cd_name} Win Rate</strong>: fraction of simulated '
        f'matchups against that opponent that {species_name} wins '
        f'(battle rating &ge; 500). What varies per cell: all 4096 '
        f'{species_name} IV spreads &times; all 9 shield scenarios (0-0, '
        f'0-1, 0-2, 1-0, 1-1, 1-2, 2-0, 2-1, 2-2) = 36,864 simulations. '
        f'The opponent\'s IV spread is held fixed at <em>PvPoke\'s '
        f'default</em> (the IV spread pvpoke.com/battle uses by default '
        f'for that species in this league), with normal shield-bait '
        f'behavior. A handful of opponents whose name ends in '
        f'<code>(atk-weighted)</code> use the attack-weighted IV spread '
        f'from <code>thresholds/_shared.toml</code> instead, which is '
        f'the community-prepared-against variant for CMP tie priority.'
        f'</li>'
        f'<li><strong>&Delta; (pp)</strong>: change in win rate from the '
        f'{default_name} moveset to the {cd_name} moveset, in '
        f'<em>percentage points</em> (so 20.0% &rarr; 68.0% reads as '
        f'<code>+48.0</code>). "pp" is the standard shorthand for '
        f'percentage-point differences.</li>'
        f'<li><strong>Flip?</strong>: whether the aggregate win rate '
        f'against this opponent crosses the 50% line between the two '
        f'movesets. <span class="flip-badge flip-pos">+Flip</span> means '
        f'{cd_name} wins the matchup where {default_name} loses it '
        f'(old win rate below 50%, new at or above); '
        f'<span class="flip-badge flip-neg">-Flip</span> means '
        f'{default_name} wins where {cd_name} loses; '
        f'<span class="flip-badge flip-none">No flip</span> means both '
        f'movesets land on the same side of the 50% line. Each badge '
        f'is a link to PvPoke\'s single-battle page for that matchup at '
        f'1-1 shields, {species_name} and opponent both at PvPoke-default '
        f'IVs, using the {cd_name} moveset. The single-battle view shows '
        f'only one of the 36,864 simulations averaged into this row, so '
        f'the on-page outcome can land in the minority side of the '
        f'aggregate win rate; use the link to inspect the matchup, '
        f'not to confirm the aggregate.</li>'
        '</ul>'
        '</details>'
    )

    table = (
        '<table class="matchup-delta sortable" data-default-sort="3" data-default-dir="desc">'
        '<thead><tr>'
        '<th scope="col" data-sort="str">Opponent</th>'
        f'<th scope="col" data-sort="pct" title="Win rate with {default_name} moveset. Varies all 4096 {species_name} IVs x 9 shield scenarios; opponent fixed at PvPoke-default IVs. Win = battle rating >= 500.">{default_name} Win Rate</th>'
        f'<th scope="col" data-sort="pct" title="Win rate with {cd_name} moveset. Varies all 4096 {species_name} IVs x 9 shield scenarios; opponent fixed at PvPoke-default IVs. Win = battle rating >= 500.">{cd_name} Win Rate</th>'
        '<th scope="col" data-sort="num" title="Change in win rate, in percentage points (CD win rate minus old-default win rate).">&#916; (pp)</th>'
        '<th scope="col" data-sort="bool" title="Aggregate matchup crosses the 50% win line: +Flip = CD wins where old default lost, -Flip = old default wins where CD loses.">Flip?</th>'
        '</tr></thead>'
        '<tbody>' + ''.join(body_rows) + '</tbody>'
        '</table>'
    )
    summary = (
        f'<p class="matchup-delta-summary">{flip_count} of '
        f'{len(opponents)} opponents flip across the 50% win line between '
        f'these two movesets.</p>'
    )
    return '\n'.join(header_lines) + '\n' + legend + '\n' + table + '\n' + summary


FORM_SYMBOLS = {'Male': '&#9794;', 'Female': '&#9792;'}
FORM_COL_CLASS = {'Male': 'male', 'Female': 'female'}


def _tier_slug(name: str) -> str:
    """Derive the dive's ``tier-card-yours-<slug>`` id from a tier name.

    The dive renderer emits ids based on the innermost anchor label, e.g.
    ``Lapras Slayer<br>  (Lapras Atk)`` -> ``lapras-atk``, ``Steelix (Shadow)
    Slayer<br>  (Wigglytuff Slayer<br>  (Wigglytuff Atk))`` ->
    ``wigglytuff-atk``. Deepest parenthesised segment after splitting by
    ``<br>`` wins; plain leaf names (``Talonflame Atk``) slug directly.
    """
    import re
    parts = (name or '').split('<br>')
    badge = parts[-1].strip()
    while badge.startswith('(') and badge.endswith(')'):
        badge = badge[1:-1].strip()
    slug = re.sub(r'[^a-z0-9]+', '-', badge.lower()).strip('-')
    return slug


def _tier_card_href(tier_name: str, dive_slug: str,
                    moveset_file: str) -> str | None:
    """Return a hyperlink anchor for the matching tier card in the dive,
    or None when either piece is missing. Article dive paths are relative
    to ``userdata/website/articles/<slug>/index.html``.

    Targets ``#tier-card-<slug>`` (on the visible card ``<div>``), not
    the legacy ``tier-card-yours-<slug>`` span which is ``display:none``
    until paste-box populates it and therefore cannot be scrolled to.
    Older dive HTML is patched in place by
    ``scripts/patch_dive_tier_anchors.py``; fresh dives emit this id
    natively.
    """
    if not dive_slug or not moveset_file:
        return None
    slug = _tier_slug(tier_name)
    if not slug:
        return None
    return f'../../{dive_slug}/{moveset_file}#tier-card-{slug}'


def _render_tier_card(tier: dict, members: int, n_ivs: int,
                      form_label: str = '',
                      link_href: str | None = None) -> str:
    """Shared tier-card HTML for both single-form and per-form sections.

    ``link_href`` wraps the card title in an anchor to the corresponding
    tier card in the relevant dive. The heading keeps its purple color
    (see CSS ``div.iv-rec-card h3 a`` override) so the link is
    discoverable on hover without visually competing with the normal
    green link color used elsewhere.
    """
    name = (tier.get('name') or '').replace('<br>', ' - ')
    atk = tier.get('attack') or 0
    def_ = tier.get('defense') or 0
    hp = tier.get('stamina') or 0
    cutoff_bits = []
    if atk:
        cutoff_bits.append(f'atk&ge;{atk:.2f}')
    if def_:
        cutoff_bits.append(f'def&ge;{def_:.2f}')
    if hp:
        cutoff_bits.append(f'hp&ge;{hp:g}')
    cutoffs = ', '.join(cutoff_bits) if cutoff_bits else 'no cutoff'
    desc = (tier.get('toml_description') or tier.get('desc') or '').strip()
    pct = (100.0 * members / n_ivs) if n_ivs else 0.0

    symbol = FORM_SYMBOLS.get(form_label, '')
    cls_suffix = ' ' + FORM_COL_CLASS[form_label] if form_label in FORM_COL_CLASS else ''
    heading_prefix = f'{symbol} ' if symbol else ''

    escaped_name = html.escape(name)
    if link_href:
        heading_html = (
            f'{heading_prefix}<a href="{html.escape(link_href)}" '
            f'title="Jump to this tier in the deep dive">{escaped_name}</a>'
        )
    else:
        heading_html = f'{heading_prefix}{escaped_name}'

    return (
        f'<div class="iv-rec-card{cls_suffix}">'
        f'<h3>{heading_html}</h3>'
        f'<p class="iv-rec-cutoffs">Cutoff: {cutoffs}</p>'
        f'<p class="iv-rec-members">{members} of {n_ivs} IVs qualify '
        f'({pct:.1f}%).</p>'
        + (f'<p class="iv-rec-desc">{html.escape(desc)}</p>' if desc else '')
        + '</div>'
    )


def _render_iv_recommendations_per_form_section(cd_move: str,
                                                forms: list[dict],
                                                article: dict) -> str:
    """Tier cards for every form, flowing in a single grid. ♂/♀ symbols
    and blue/pink tints distinguish form membership.
    """
    cards: list[str] = []
    dive_links: list[tuple[str, str]] = []
    for f in forms:
        best_cd = f['best_cd']
        tiers = best_cd.get('tiers') or []
        iv_all_tiers = best_cd.get('iv_all_tiers') or []
        n_ivs = best_cd.get('n_ivs', 0)
        if not tiers:
            continue
        # Count IVs that CLEAR each tier's cutoffs (not tier-exclusive
        # assignment). Using ivAllTiers matches the dive's per-tier IV
        # count so an atk tier whose cutoff is cleared by IVs that ALSO
        # clear a stricter tier still shows its real clear count.
        member_counts = [0] * len(tiers)
        for iv_tier_list in iv_all_tiers:
            for ti in iv_tier_list:
                if 0 <= ti < len(tiers):
                    member_counts[ti] += 1
        fast, charged = _parse_moveset_label(best_cd['label'])
        moveset_file = (
            f'index_m0_{fast.lower()}_{"_".join(c.lower() for c in charged)}.html'
        )
        for t, m in zip(tiers, member_counts):
            href = _tier_card_href(t.get('name') or '', f['dive_slug'], moveset_file)
            cards.append(_render_tier_card(t, m, n_ivs,
                                           form_label=f['label'],
                                           link_href=href))
        dive_links.append(
            (f['label'], f'../../{f["dive_slug"]}/{moveset_file}#dd-threshold-tiers')
        )

    if not cards:
        return render_placeholder(
            'iv-recommendations', 'IV Recommendations',
            'No tier data found for any form\'s best CD moveset.')

    link_items = ', '.join(
        f'<a href="{html.escape(url)}">{html.escape(label)} dive</a>'
        for label, url in dive_links
    )
    intro = (
        f'<p class="iv-rec-intro">Tier cutoffs from each form\'s best CD '
        f'moveset. Cards are colored by form (&#9794; blue / &#9792; pink) '
        f'and flow together in the grid below. Tier names differ between '
        f'forms because base stats differ, so there is no 1:1 mapping - '
        f'read the cards as two separate sets sharing a grid. For the '
        f'per-anchor matchup bullets backing each tier, follow through '
        f'to each deep dive\'s Threshold Tiers section: {link_items}.</p>'
    )
    return intro + '\n<div class="iv-rec-grid">' + '\n'.join(cards) + '</div>'


def _render_iv_recommendations_section(cd_move: str, species: str,
                                       league: str, dive: dict,
                                       article: dict) -> str:
    """Minimal tier-card view from the dive's embedded DATA.

    The full anchor-flip-backed renderer (render_threshold_tier_cards in
    scripts/deep_dive_rendering.py) needs the deep-dive pipeline's
    precomputed anchor_flip_records / flip_map / matchup_boundaries,
    which are not embedded in the dive DATA blob. For S8 we render a
    condensed tier view - stat cutoffs, member counts, per-tier
    description - and link out to the dive's full Threshold Tiers
    section for the bullet-level detail.
    """
    gm = load_gamemaster()
    cd_entry = _lookup_move(gm, cd_move)
    if cd_entry is None:
        return render_placeholder(
            'iv-recommendations', 'IV Recommendations',
            f'Move {cd_move!r} not found in gamemaster; cannot pick best CD moveset.')
    cd_id = cd_entry['moveId']

    cd_movesets = [m for m in dive['movesets']
                   if _moveset_fast_move(m['label']) == cd_id]
    if not cd_movesets:
        return render_placeholder(
            'iv-recommendations', 'IV Recommendations',
            f'No CD-move ({cd_id}) moveset in dive data.')
    best_cd = max(cd_movesets, key=lambda m: m['win_rate'])

    tiers = best_cd.get('tiers') or []
    iv_all_tiers = best_cd.get('iv_all_tiers') or []
    n_ivs = best_cd.get('n_ivs', 0)
    if not tiers:
        return render_placeholder(
            'iv-recommendations', 'IV Recommendations',
            'Dive data has no tiers for the best CD moveset.')

    # Count IVs that clear each tier's cutoffs (matches the dive's own
    # per-tier count, not the tier-exclusive assignment).
    member_counts = [0] * len(tiers)
    for iv_tier_list in iv_all_tiers:
        for ti in iv_tier_list:
            if 0 <= ti < len(tiers):
                member_counts[ti] += 1

    dive_slug = article.get('links', {}).get('deep_dive_slug', '')
    fast, charged = _parse_moveset_label(best_cd['label'])
    moveset_file = (
        f'index_m0_{fast.lower()}_{"_".join(c.lower() for c in charged)}.html'
    )
    dive_href = f'../../{dive_slug}/{moveset_file}#dd-threshold-tiers' if dive_slug else ''

    cards = [
        _render_tier_card(
            t, m, n_ivs,
            link_href=_tier_card_href(t.get('name') or '', dive_slug, moveset_file),
        )
        for t, m in zip(tiers, member_counts)
    ]
    pretty = html.escape(best_cd['pretty_label'] or best_cd['label'])
    intro = (
        f'<p class="iv-rec-intro">Tier cutoffs from the best CD moveset '
        f'(<code>{pretty}</code>). Each tier is a named band of IV spreads '
        f'sharing a stat target. For the per-anchor matchup bullets backing '
        f'each tier, follow through to the deep dive\'s '
    )
    if dive_href:
        intro += (f'<a href="{html.escape(dive_href)}">Threshold Tiers '
                  f'section</a>.</p>')
    else:
        intro += 'Threshold Tiers section.</p>'

    return intro + '\n<div class="iv-rec-grid">' + '\n'.join(cards) + '</div>'


def _derive_framing(species: str, league: str, cd_move: str,
                    dive: dict | None) -> str | None:
    """Return a one-word framing tag ('upgrade' / 'downgrade' / 'sidegrade')
    derived from the same scenario-count classifier the Verdict section
    uses. Keeps the header pill and the Verdict line from disagreeing
    when the TOML's hand-set ``framing`` predates the dive data.

    Returns None if the dive data isn't available or best movesets
    can't be resolved - in which case the caller should fall back to
    the TOML's framing field.
    """
    if dive is None:
        return None
    gm = load_gamemaster()
    cd_entry = _lookup_move(gm, cd_move)
    if cd_entry is None:
        return None
    cd_id = cd_entry['moveId']
    try:
        default_fast_id, _ = get_default_moveset(species, league)
    except KeyError:
        return None
    cd_ms = [m for m in dive['movesets']
             if _moveset_fast_move(m['label']) == cd_id]
    df_ms = [m for m in dive['movesets']
             if _moveset_fast_move(m['label']) == default_fast_id]
    if not cd_ms or not df_ms:
        return None
    best_cd = max(cd_ms, key=lambda m: m['win_rate'])
    best_df = max(df_ms, key=lambda m: m['win_rate'])
    wins = losses = 0
    for cd_r, df_r in zip(best_cd['per_scenario_win_rate'],
                          best_df['per_scenario_win_rate']):
        if cd_r > df_r:
            wins += 1
        elif cd_r < df_r:
            losses += 1
    total = len(best_cd['per_scenario_win_rate'])
    if total == 0:
        return None
    majority = (2 * total + 2) // 3
    if wins == total:
        return 'upgrade'
    if losses == total:
        return 'downgrade'
    if wins >= majority and wins > losses:
        return 'upgrade'
    if losses >= majority and losses > wins:
        return 'downgrade'
    return 'sidegrade'


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


def _load_form_comparison_spec(article: dict) -> dict | None:
    """Read the [form_comparison] block and resolve the referenced spec TOML.

    Returns the parsed compare-spec dict (with loadout_specs). Absent block
    or missing spec file returns None; bad schemas fail loudly.
    """
    block = article.get('form_comparison')
    if not block:
        return None
    spec_ref = block.get('spec')
    if not spec_ref:
        sys.exit('[form_comparison] is set but missing the spec field.')
    spec_path = (REPO_ROOT / spec_ref).resolve()
    if not spec_path.exists():
        sys.exit(f'[form_comparison].spec path not found: {spec_path}')
    return parse_comparison_spec(spec_path)


def _render_form_comparison_section(article: dict) -> str | None:
    """Return the form-comparison fragment, or None when nothing is wired.

    The per-form Matchup Delta table already covers pairwise form-vs-form
    win rates via its ♂/♀ Mud Slap WR columns, so the form-comparison
    section drops its own matchup-delta sub-table to avoid duplication.
    Base stats, moveset, and verdict remain unique to this section.
    """
    spec = _load_form_comparison_spec(article)
    if spec is None:
        return None
    loadouts_data = [load_loadout_data(s) for s in spec['loadout_specs']]
    gm = load_gamemaster()
    return build_comparison_fragment(
        loadouts_data=loadouts_data,
        league=spec['league'],
        gm=gm,
        title=spec.get('title', ''),
        summary=spec.get('summary', ''),
        include_matchup_delta=False,
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
    elif section_id == 'meta-coverage' and dive is not None:
        form_spec = _load_form_comparison_spec(article)
        mc_forms = (_collect_per_form_best_movesets(form_spec, cd_move, load_gamemaster())
                    if form_spec else None)
        if mc_forms and len(mc_forms) >= 2:
            body_html = _render_meta_coverage_per_form_section(
                cd_move, mc_forms, load_gamemaster())
        else:
            body_html = _render_meta_coverage_section(cd_move, species, league, dive)
    elif section_id == 'matchup-delta' and dive is not None:
        form_spec = _load_form_comparison_spec(article)
        forms = (_collect_per_form_best_movesets(form_spec, cd_move, load_gamemaster())
                 if form_spec else None)
        if forms and len(forms) >= 2:
            body_html = _render_matchup_delta_per_form_section(
                cd_move, forms, load_gamemaster())
        else:
            body_html = _render_matchup_delta_section(cd_move, species, league, dive)
    elif section_id == 'form-comparison':
        fragment = _render_form_comparison_section(article)
        if fragment is None:
            return ''
        body_html = fragment
        block = article.get('form_comparison') or {}
        heading = block.get('heading', heading)
    elif section_id == 'iv-recommendations' and dive is not None:
        form_spec = _load_form_comparison_spec(article)
        iv_forms = (_collect_per_form_best_movesets(form_spec, cd_move, load_gamemaster())
                    if form_spec else None)
        if iv_forms and len(iv_forms) >= 2:
            body_html = _render_iv_recommendations_per_form_section(
                cd_move, iv_forms, article)
        else:
            body_html = _render_iv_recommendations_section(
                cd_move, species, league, dive, article)
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
    toml_framing = (article.get('framing') or '').strip()
    derived_framing = _derive_framing(species_name, league, cd_move, dive)
    if authorship == 'auto' and derived_framing:
        framing_plain = derived_framing
    elif derived_framing and not toml_framing:
        framing_plain = derived_framing
    else:
        framing_plain = toml_framing
    if derived_framing and toml_framing and derived_framing != toml_framing \
            and authorship != 'auto':
        logger.warning(
            'Front-matter framing %r disagrees with the sim-derived %r; '
            'keeping the TOML value because authorship=%s. Under '
            'authorship=auto the derived value would override.',
            toml_framing, derived_framing, authorship)
    framing = html.escape(framing_plain)
    article = dict(article)  # shallow copy to avoid mutating caller's dict
    article['framing'] = framing_plain

    rendered_sections = [
        render_section(sid, heading, todo, article, overrides,
                       species=species_name, league=league, cd_move=cd_move,
                       dive=dive)
        for sid, heading, todo in CANONICAL_SECTIONS
    ]
    sections_html = '\n\n'.join(s for s in rendered_sections if s.strip())

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
  h3 {{ color: #c8a2d0; margin-top: 18px; font-size: 1.05em; }}
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
  p.meta-coverage-intro {{ font-size: 14px; color: #b8c4d8; }}
  div.article-opp-iv-control {{ background: #16213e; padding: 10px 14px;
         border-radius: 6px; margin: 10px 0; border-left: 3px solid #5b8dd9; }}
  div.article-opp-iv-control label {{ display: inline-block;
         margin-right: 16px; font-size: 13px; color: #b8c4d8; }}
  div.article-opp-iv-control span.control-label {{ color: #c8a2d0;
         font-weight: 500; }}
  div.article-opp-iv-control select {{ background: #0f162a; color: #e0e0e0;
         border: 1px solid #3d5580; border-radius: 3px; padding: 2px 6px;
         font-size: 13px; margin-left: 4px; }}
  p.article-opp-iv-caption {{ font-size: 12px; color: #8ea1bd;
         margin: 6px 0 0 0; }}
  table.meta-coverage {{ border-collapse: collapse; margin: 12px 0;
         width: 100%; font-size: 13px; }}
  table.meta-coverage th, table.meta-coverage td {{
         border: 1px solid #0f3460; padding: 5px 9px; text-align: left; }}
  table.meta-coverage thead th {{ background: #16213e; color: #c8a2d0; }}
  table.meta-coverage tbody th {{ background: #12192e; color: #9ab0d8;
         font-weight: 500; font-size: 15px; }}
  table.meta-coverage tbody td {{ background: #0f162a; color: #e0e0e0; }}
  table.meta-coverage th.num, table.meta-coverage td.num {{
         text-align: right; font-variant-numeric: tabular-nums; }}
  table.meta-coverage td.delta-pos {{ color: #9be89b; font-weight: 600; }}
  table.meta-coverage td.delta-neg {{ color: #e89b9b; font-weight: 600; }}
  table.meta-coverage tbody th.male {{ color: rgba(91,141,217,1); }}
  table.meta-coverage tbody th.female {{ color: rgba(217,108,145,1); }}
  p.verdict-line {{ background: #1a2e1f; border-left: 3px solid #7db87d;
                    padding: 10px 14px; color: #cfe8cf; border-radius: 6px; }}
  p.matchup-delta-intro {{ font-size: 14px; color: #b8c4d8; }}
  p.matchup-delta-summary {{ font-size: 13px; color: #9bb0d0; margin-top: 8px; }}
  ul.matchup-delta-movesets {{ margin: 4px 0 10px 20px; padding: 0;
                               font-size: 14px; }}
  ul.matchup-delta-movesets li {{ margin: 2px 0; }}
  table.matchup-delta {{ border-collapse: collapse; margin: 10px 0;
                         width: 100%; font-size: 13px; }}
  div.matchup-delta-scroll {{ overflow-x: auto; margin: 10px 0;
         max-width: 100%; }}
  table.matchup-delta-perform {{ font-size: 12px; min-width: 640px; }}
  table.matchup-delta-perform th, table.matchup-delta-perform td {{
         padding: 4px 6px; }}
  table.matchup-delta-perform thead th {{ white-space: normal;
         vertical-align: bottom; line-height: 1.25; }}
  table.matchup-delta-perform tbody td {{ white-space: nowrap; }}
  table.matchup-delta-perform th.num,
  table.matchup-delta-perform td.num {{ text-align: right;
         font-variant-numeric: tabular-nums; }}
  table.matchup-delta-perform th.diag-start,
  table.matchup-delta-perform td.diag-start {{ border-left: 2px solid #3d5580; }}
  /* M/F column tints. Non-flip rows get a faint blue/pink wash; flip
     rows layer the same wash on top of their green/red row color via
     multi-background so the form lane stays visible. */
  table.matchup-delta-perform td.male {{ background: rgba(91,141,217,0.20); }}
  table.matchup-delta-perform td.female {{ background: rgba(217,108,145,0.20); }}
  table.matchup-delta-perform thead th.male {{ background: rgba(91,141,217,0.22); }}
  table.matchup-delta-perform thead th.female {{ background: rgba(217,108,145,0.22); }}
  table.matchup-delta-perform tr.matchup-delta-flip-pos td {{ background: #152b1a; }}
  table.matchup-delta-perform tr.matchup-delta-flip-neg td {{ background: #2b1515; }}
  table.matchup-delta-perform tr.matchup-delta-flip-pos td.male {{
        background: linear-gradient(rgba(91,141,217,0.22),rgba(91,141,217,0.22)), #152b1a; }}
  table.matchup-delta-perform tr.matchup-delta-flip-pos td.female {{
        background: linear-gradient(rgba(217,108,145,0.22),rgba(217,108,145,0.22)), #152b1a; }}
  table.matchup-delta-perform tr.matchup-delta-flip-neg td.male {{
        background: linear-gradient(rgba(91,141,217,0.22),rgba(91,141,217,0.22)), #2b1515; }}
  table.matchup-delta-perform tr.matchup-delta-flip-neg td.female {{
        background: linear-gradient(rgba(217,108,145,0.22),rgba(217,108,145,0.22)), #2b1515; }}
  p.mf-split-filter {{ margin: 10px 0 6px 0; font-size: 13px; color: #b8c4d8;
         background: #12192e; padding: 8px 12px; border-radius: 4px;
         border-left: 3px solid #c8a2d0; }}
  p.mf-split-filter label {{ cursor: pointer; }}
  p.mf-split-filter input {{ margin-right: 6px; vertical-align: middle; }}
  span.form-label.male {{ color: rgba(91,141,217,1); font-weight: 600; }}
  span.form-label.female {{ color: rgba(217,108,145,1); font-weight: 600; }}
  table.matchup-delta-perform.filter-split tbody tr[data-form-split="same"] {{
        display: none; }}
  table.matchup-delta th, table.matchup-delta td {{ border: 1px solid #0f3460;
        padding: 5px 9px; text-align: left; }}
  table.matchup-delta thead th {{ background: #16213e; color: #c8a2d0; }}
  table.matchup-delta tbody td {{ background: #0f162a; color: #e0e0e0; }}
  table.matchup-delta tr.matchup-delta-flip td {{ border-color: #5b3d6d; }}
  table.matchup-delta td.delta-pos {{ color: #9be89b; font-weight: 600; }}
  table.matchup-delta td.delta-neg {{ color: #e89b9b; font-weight: 600; }}
  .flip-badge {{ display: inline-block; padding: 1px 8px; border-radius: 10px;
        font-size: 11px; font-weight: 600; text-transform: uppercase;
        text-decoration: none; }}
  a.flip-badge:hover {{ text-decoration: underline; filter: brightness(1.15); }}
  .flip-badge.flip-pos {{ background: #1f3a1f; color: #9be89b;
        border: 1px solid #7db87d; }}
  .flip-badge.flip-neg {{ background: #3a1f1f; color: #e89b9b;
        border: 1px solid #b87d7d; }}
  .flip-badge.flip-none {{ background: #1a2333; color: #8ea1bd;
        border: 1px solid #3d5580; }}
  .flip-badge.flip-unlinked {{ opacity: 0.75; cursor: help; }}
  table.matchup-delta tr.matchup-delta-flip-pos td {{ background: #152b1a; }}
  table.matchup-delta tr.matchup-delta-flip-neg td {{ background: #2b1515; }}
  details.matchup-delta-legend {{ background: #12192e; border-left: 3px solid #c8a2d0;
        border-radius: 4px; padding: 8px 12px; font-size: 13px; color: #b8c4d8;
        margin: 8px 0; }}
  details.matchup-delta-legend summary {{ cursor: pointer; color: #c8a2d0;
        font-weight: 500; }}
  details.matchup-delta-legend ul {{ margin: 8px 0 0 0; padding-left: 20px; }}
  details.matchup-delta-legend li {{ margin: 4px 0; }}
  p.matchup-delta-pool {{ background: #16213e; border-left: 3px solid #5b8dd9;
        padding: 8px 12px; border-radius: 4px; font-size: 13px; color: #b8c4d8;
        margin: 8px 0; }}
  table.sortable thead th {{ cursor: pointer; user-select: none; }}
  table.sortable thead th:hover {{ background: #1e2b4a; }}
  table.sortable thead th.sort-asc::after {{ content: " \\25B2"; color: #9be89b;
        font-size: 10px; }}
  table.sortable thead th.sort-desc::after {{ content: " \\25BC"; color: #9be89b;
        font-size: 10px; }}
  p.iv-rec-intro {{ font-size: 14px; color: #b8c4d8; }}
  div.iv-rec-grid {{ display: grid; gap: 10px;
                     grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                     margin: 10px 0; }}
  div.iv-rec-card {{ background: #0f162a; border: 1px solid #0f3460;
                     border-left: 3px solid #c8a2d0; border-radius: 6px;
                     padding: 10px 12px; font-size: 13px; }}
  div.iv-rec-card.male {{ background: linear-gradient(rgba(91,141,217,0.14),
                          rgba(91,141,217,0.14)), #0f162a;
                          border-left-color: rgba(91,141,217,0.8); }}
  div.iv-rec-card.female {{ background: linear-gradient(rgba(217,108,145,0.14),
                            rgba(217,108,145,0.14)), #0f162a;
                            border-left-color: rgba(217,108,145,0.8); }}
  div.iv-rec-card h3 {{ color: #c8a2d0; font-size: 14px; margin: 0 0 4px 0;
                        border-bottom: none; padding-bottom: 0; }}
  div.iv-rec-card h3 a {{ color: inherit; text-decoration: none; }}
  div.iv-rec-card h3 a:hover {{ text-decoration: underline;
                                filter: brightness(1.1); }}
  p.iv-rec-cutoffs {{ color: #9ab0d8; margin: 2px 0; font-family: monospace;
                      font-size: 12px; }}
  p.iv-rec-members {{ color: #b8c4d8; margin: 2px 0; }}
  p.iv-rec-desc {{ color: #8ea1bd; margin: 4px 0 0 0; font-style: italic;
                   font-size: 12px; }}
  footer {{ color: #666; font-size: 13px; margin-top: 40px;
            border-top: 1px solid #0f3460; padding-top: 12px; }}
{COMPARE_CSS}</style>
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
<script>
(function() {{
  function parseCell(cell, kind) {{
    var t = cell.textContent.trim();
    if (kind === 'num') {{
      return parseFloat(t.replace(/[+,]/g, '')) || 0;
    }}
    if (kind === 'pct') {{
      return parseFloat(t.replace('%', '')) || 0;
    }}
    if (kind === 'bool') {{
      if (t.indexOf('+Flip') !== -1) return 2;
      if (t.indexOf('-Flip') !== -1) return -1;
      if (t.indexOf('No flip') !== -1) return 0;
      return t.length > 0 ? 1 : 0;
    }}
    return t.toLowerCase();
  }}
  function sortTable(table, colIdx, kind, dir) {{
    var tbody = table.querySelector('tbody');
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var sign = dir === 'desc' ? -1 : 1;
    rows.sort(function(a, b) {{
      var va = parseCell(a.cells[colIdx], kind);
      var vb = parseCell(b.cells[colIdx], kind);
      if (va < vb) return -1 * sign;
      if (va > vb) return 1 * sign;
      return 0;
    }});
    rows.forEach(function(r) {{ tbody.appendChild(r); }});
    var ths = table.querySelectorAll('thead th');
    ths.forEach(function(th) {{
      th.classList.remove('sort-asc');
      th.classList.remove('sort-desc');
    }});
    ths[colIdx].classList.add(dir === 'desc' ? 'sort-desc' : 'sort-asc');
  }}
  document.querySelectorAll('.mf-split-toggle').forEach(function(cb) {{
    cb.addEventListener('change', function(e) {{
      var id = cb.getAttribute('data-target');
      var table = document.getElementById(id);
      if (table) table.classList.toggle('filter-split', e.target.checked);
    }});
  }});
  document.querySelectorAll('table.sortable').forEach(function(table) {{
    var ths = table.querySelectorAll('thead th');
    ths.forEach(function(th, idx) {{
      var kind = th.getAttribute('data-sort') || 'str';
      th.addEventListener('click', function() {{
        var current = th.classList.contains('sort-asc') ? 'asc'
                    : th.classList.contains('sort-desc') ? 'desc' : null;
        var next;
        if (current === 'asc') next = 'desc';
        else if (current === 'desc') next = 'asc';
        else next = (kind === 'num' || kind === 'pct' || kind === 'bool') ? 'desc' : 'asc';
        sortTable(table, idx, kind, next);
      }});
    }});
    // Apply default sort indicator if specified.
    var defIdx = parseInt(table.getAttribute('data-default-sort') || '', 10);
    var defDir = table.getAttribute('data-default-dir') || 'desc';
    if (!isNaN(defIdx) && ths[defIdx]) {{
      ths[defIdx].classList.add(defDir === 'desc' ? 'sort-desc' : 'sort-asc');
    }}
  }});
}})();
</script>
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
