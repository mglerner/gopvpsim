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
    per_opponent_wins = [0] * n_o
    per_opponent_n = n_ivs * n_s
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
    per_scenario_rate = [w / per_scenario_n for w in per_scenario_wins]
    per_opponent_rate = [w / per_opponent_n for w in per_opponent_wins]
    win_rate = total_wins / expected

    return {
        'label': label,
        'pretty_label': pretty,
        'win_rate': win_rate,
        'per_scenario_win_rate': per_scenario_rate,
        'per_opponent_win_rate': per_opponent_rate,
        'scenarios': data['scenarios'],
        'opponents': data['opponents'],
        'tiers': data.get('tiers') or [],
        'iv_tiers': data.get('ivTiers') or [],
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
    return {
        'movesets': movesets,
        'scenarios': scenarios,
        'opponents': opponents,
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
        - fm is the 0-based index into the species' sorted fastMovePool
        - cm1 / cm2 are 1-based indices into the sorted chargedMovePool
          (0 is reserved as an empty slot in PvPoke)
        - "2-1" = chargedMoveCount=2, shieldBaiting=1 (copied from
          PvPoke's own rankings link, so the landed page matches what
          users see from the rankings UI)

    Returns None if any index can't be resolved (falls back to a
    plain-text moveset label on the caller's side).
    """
    cp = LEAGUE_CP.get(league)
    if cp is None:
        return None
    fm_pool, cm_pool = _species_move_pools(gm, species_id)
    if not fm_pool or not cm_pool:
        return None
    if fast_move_id not in fm_pool:
        return None
    fm_idx = fm_pool.index(fast_move_id)
    cm_idxs = []
    for cm in charged_move_ids:
        if cm not in cm_pool:
            return None
        cm_idxs.append(cm_pool.index(cm) + 1)
    while len(cm_idxs) < 2:
        cm_idxs.append(0)
    move_str = f'{fm_idx}-{cm_idxs[0]}-{cm_idxs[1]}'
    shields_str = f'{shields[0]}{shields[1]}'
    return (f'https://pvpoke.com/battle/multi/{cp}/all/'
            f'{species_id}/{shields_str}/{move_str}/2-1/')


def _parse_moveset_label(label: str) -> tuple[str, list[str]]:
    """Split 'FAST / CM1, CM2' into (fast_id, [cm1_id, cm2_id])."""
    if '/' not in label:
        return label.strip(), []
    fast, rest = label.split('/', 1)
    charged = [c.strip() for c in rest.split(',') if c.strip()]
    return fast.strip(), charged


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

    header_lines = [
        '<p class="matchup-delta-intro">Best CD-move moveset vs best old-default moveset, '
        'by overall win rate. Per-opponent win rate averaged across all 9 shield scenarios '
        'and 4096 IV spreads. "Flip" marks rows where the winner changes across the 50% axis '
        '(the same threshold the verdict section uses).</p>',
        '<ul class="matchup-delta-movesets">',
        _link_item(best_cd, cd_url),
        _link_item(best_default, df_url),
        '</ul>',
    ]

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

    body_rows = []
    for name, cd_r, df_r, delta_pp, flip in rows:
        row_class = 'matchup-delta-flip' if flip else ''
        flip_cell = ('<span class="flip-badge">Flip</span>'
                     if flip else '')
        delta_class = 'delta-pos' if delta_pp > 0 else 'delta-neg' if delta_pp < 0 else ''
        body_rows.append(
            f'<tr class="{row_class}">'
            f'<td>{html.escape(name)}</td>'
            f'<td>{100 * df_r:.1f}%</td>'
            f'<td>{100 * cd_r:.1f}%</td>'
            f'<td class="{delta_class}">{delta_pp:+.1f}</td>'
            f'<td>{flip_cell}</td>'
            f'</tr>'
        )

    cd_name = html.escape(cd_entry.get('name', cd_move))
    default_entry = _lookup_move(gm, default_fast_id)
    default_name = html.escape(
        default_entry.get('name', default_fast_id) if default_entry else default_fast_id)

    table = (
        '<table class="matchup-delta">'
        '<thead><tr>'
        '<th scope="col">Opponent</th>'
        f'<th scope="col">{default_name} WR</th>'
        f'<th scope="col">{cd_name} WR</th>'
        '<th scope="col">&#916; (pp)</th>'
        '<th scope="col">Flip?</th>'
        '</tr></thead>'
        '<tbody>' + ''.join(body_rows) + '</tbody>'
        '</table>'
    )
    summary = (
        f'<p class="matchup-delta-summary">{flip_count} of '
        f'{len(opponents)} opponents flip across the 50% win axis.</p>'
    )
    return '\n'.join(header_lines) + '\n' + table + '\n' + summary


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
    iv_tiers = best_cd.get('iv_tiers') or []
    n_ivs = best_cd.get('n_ivs', 0)
    if not tiers:
        return render_placeholder(
            'iv-recommendations', 'IV Recommendations',
            'Dive data has no tiers for the best CD moveset.')

    member_counts = [0] * len(tiers)
    for ti in iv_tiers:
        if 0 <= ti < len(tiers):
            member_counts[ti] += 1

    dive_slug = article.get('links', {}).get('deep_dive_slug', '')
    fast, charged = _parse_moveset_label(best_cd['label'])
    moveset_file = (
        f'index_m0_{fast.lower()}_{"_".join(c.lower() for c in charged)}.html'
    )
    dive_href = f'../../{dive_slug}/{moveset_file}#dd-threshold-tiers' if dive_slug else ''

    cards = []
    for t, members in zip(tiers, member_counts):
        name = (t.get('name') or '').replace('<br>', ' - ')
        atk = t.get('attack') or 0
        def_ = t.get('defense') or 0
        hp = t.get('stamina') or 0
        cutoff_bits = []
        if atk:
            cutoff_bits.append(f'atk&ge;{atk:.2f}')
        if def_:
            cutoff_bits.append(f'def&ge;{def_:.2f}')
        if hp:
            cutoff_bits.append(f'hp&ge;{hp:g}')
        cutoffs = ', '.join(cutoff_bits) if cutoff_bits else 'no cutoff'
        desc = (t.get('toml_description') or t.get('desc') or '').strip()
        pct = (100.0 * members / n_ivs) if n_ivs else 0.0
        cards.append(
            '<div class="iv-rec-card">'
            f'<h3>{html.escape(name)}</h3>'
            f'<p class="iv-rec-cutoffs">Cutoff: {cutoffs}</p>'
            f'<p class="iv-rec-members">{members} of {n_ivs} IVs qualify '
            f'({pct:.1f}%).</p>'
            + (f'<p class="iv-rec-desc">{html.escape(desc)}</p>' if desc else '')
            + '</div>'
        )
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
    elif section_id == 'matchup-delta' and dive is not None:
        body_html = _render_matchup_delta_section(cd_move, species, league, dive)
    elif section_id == 'iv-recommendations' and dive is not None:
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
  p.matchup-delta-intro {{ font-size: 14px; color: #b8c4d8; }}
  p.matchup-delta-summary {{ font-size: 13px; color: #9bb0d0; margin-top: 8px; }}
  ul.matchup-delta-movesets {{ margin: 4px 0 10px 20px; padding: 0;
                               font-size: 14px; }}
  ul.matchup-delta-movesets li {{ margin: 2px 0; }}
  table.matchup-delta {{ border-collapse: collapse; margin: 10px 0;
                         width: 100%; font-size: 13px; }}
  table.matchup-delta th, table.matchup-delta td {{ border: 1px solid #0f3460;
        padding: 5px 9px; text-align: left; }}
  table.matchup-delta thead th {{ background: #16213e; color: #c8a2d0; }}
  table.matchup-delta tbody td {{ background: #0f162a; color: #e0e0e0; }}
  table.matchup-delta tr.matchup-delta-flip td {{ background: #2a2333;
        border-color: #5b3d6d; }}
  table.matchup-delta td.delta-pos {{ color: #9be89b; font-weight: 600; }}
  table.matchup-delta td.delta-neg {{ color: #e89b9b; font-weight: 600; }}
  table.matchup-delta .flip-badge {{ display: inline-block; background: #5b3d6d;
        color: #e8c8f0; padding: 1px 6px; border-radius: 10px; font-size: 11px;
        font-weight: 600; text-transform: uppercase; }}
  p.iv-rec-intro {{ font-size: 14px; color: #b8c4d8; }}
  div.iv-rec-grid {{ display: grid; gap: 10px;
                     grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                     margin: 10px 0; }}
  div.iv-rec-card {{ background: #0f162a; border: 1px solid #0f3460;
                     border-left: 3px solid #c8a2d0; border-radius: 6px;
                     padding: 10px 12px; font-size: 13px; }}
  div.iv-rec-card h3 {{ color: #c8a2d0; font-size: 14px; margin: 0 0 4px 0;
                        border-bottom: none; padding-bottom: 0; }}
  p.iv-rec-cutoffs {{ color: #9ab0d8; margin: 2px 0; font-family: monospace;
                      font-size: 12px; }}
  p.iv-rec-members {{ color: #b8c4d8; margin: 2px 0; }}
  p.iv-rec-desc {{ color: #8ea1bd; margin: 4px 0 0 0; font-style: italic;
                   font-size: 12px; }}
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
