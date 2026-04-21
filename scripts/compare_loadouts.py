#!/usr/bin/env python3
"""Compare two or more Pokemon loadouts via their deep-dive win-rate data.

Usage: python scripts/compare_loadouts.py <spec.toml>

See comparisons/oinkologne-male-vs-female.toml for the canonical TOML
schema example (slug, title, league, [[loadouts]] blocks). Output lands
under userdata/website/comparisons/<slug>/.

The rendered HTML fragment is also exposed via build_comparison_fragment
so generate_article.py can inline the same content into a CD-article
section without re-reading the file.

Design notes:
* Data model is loadouts: list[LoadoutSpec] (not A/B-keyed). Pairwise
  deltas are computed with itertools.combinations so N=3 / N=4 are a
  renderer extension, not a data-model rewrite.
* Win rate is the consumer-facing metric (fraction of matchups with
  battle-rating >= 500), matching the dive scatter's winsPvpoke y-axis
  and the article verdict line.
* Opponents are aligned by display name. Only opponents present in
  every loadout's dive are shown.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import gzip
import html
import itertools
import json
import struct
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from gopvpsim.data import (  # type: ignore[import-not-found]
    load_gamemaster,
    get_default_moveset,
    parse_types,
)
from render_article import sidebar_css  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'
COMPARISONS_DIR = WEBSITE_DIR / 'comparisons'

LEAGUE_CP = {'great': 1500, 'ultra': 2500, 'master': 10000}


@dataclasses.dataclass(frozen=True)
class LoadoutSpec:
    """A single loadout to include in the comparison.

    ``label`` is the display name (column header). ``dive_slug`` points at
    an existing deep-dive directory under ``userdata/website/``; the
    comparator reads the moveset HTML matching ``fast_move`` +
    ``charged_moves`` inside that directory.
    """
    label: str
    species: str
    dive_slug: str
    fast_move: str
    charged_moves: tuple[str, ...]
    shadow: bool = False

    @property
    def moveset_label(self) -> str:
        return f'{self.fast_move} / {", ".join(self.charged_moves)}'


def _extract_js_assignment(content: str, var_name: str) -> str:
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
    raw = gzip.decompress(base64.b64decode(b64))
    n = len(raw) // 2
    return list(struct.unpack(f'<{n}H', raw))


def _moveset_slug(fast_move: str, charged_moves: tuple[str, ...]) -> str:
    parts = [fast_move.lower()] + [c.lower() for c in charged_moves]
    return '_'.join(parts)


def _find_moveset_file(dive_dir: Path, spec: LoadoutSpec) -> Path:
    """Find the split-movesets HTML for this loadout's exact moveset.

    Matches on filename slug (``mud_slap_body_slam_trailblaze``), which is
    how ``deep_dive.py --split-movesets`` composes the suffix. Falls back
    to scanning ``DATA.movesets[0].label`` when the slug convention does
    not hit (e.g. reference / landing file).
    """
    slug = _moveset_slug(spec.fast_move, spec.charged_moves)
    for candidate in sorted(dive_dir.glob(f'index_m*_{slug}.html')):
        return candidate
    for candidate in sorted(dive_dir.glob('index*.html')):
        try:
            content = candidate.read_text()
            data_blob = _extract_js_assignment(content, 'DATA')
        except (ValueError, OSError):
            continue
        data = json.loads(data_blob)
        movesets = data.get('movesets') or []
        if not movesets:
            continue
        ms_label = movesets[0].get('label') or ''
        if ms_label == spec.moveset_label:
            return candidate
    raise FileNotFoundError(
        f'No dive HTML in {dive_dir} matches loadout '
        f'{spec.label!r}: {spec.moveset_label}')


def load_loadout_data(spec: LoadoutSpec) -> dict:
    """Parse one loadout's dive HTML into aligned win-rate arrays."""
    dive_dir = WEBSITE_DIR / spec.dive_slug
    if not dive_dir.is_dir():
        sys.exit(f'Loadout {spec.label!r}: dive directory not found: {dive_dir}')
    path = _find_moveset_file(dive_dir, spec)
    content = path.read_text()
    data = json.loads(_extract_js_assignment(content, 'DATA'))
    scores_gz = json.loads(_extract_js_assignment(content, 'SCORES_GZ'))
    if '0_pvpoke' not in scores_gz:
        raise ValueError(f'{path}: SCORES_GZ missing "0_pvpoke"')
    scores = _decompress_scores(scores_gz['0_pvpoke'])

    n_ivs = data['nIvs']
    n_s = data['nScenarios']
    n_o = data['nOpponents']
    expected = n_ivs * n_s * n_o
    if len(scores) != expected:
        raise ValueError(
            f'{path}: score length {len(scores)} != nIvs*nS*nO={expected}')

    per_scenario_wins = [0] * n_s
    per_opponent_wins = [0] * n_o
    total_wins = 0
    for iv in range(n_ivs):
        base_iv = iv * n_s * n_o
        for si in range(n_s):
            base = base_iv + si * n_o
            for oi in range(n_o):
                if scores[base + oi] >= 500:
                    per_scenario_wins[si] += 1
                    per_opponent_wins[oi] += 1
                    total_wins += 1

    per_scenario_rate = [w / (n_ivs * n_o) for w in per_scenario_wins]
    per_opponent_rate = [w / (n_ivs * n_s) for w in per_opponent_wins]
    win_rate = total_wins / expected

    movesets = data.get('movesets') or []
    pretty = spec.moveset_label
    if movesets and movesets[0].get('prettyLabel'):
        pretty = movesets[0]['prettyLabel']

    return {
        'spec': spec,
        'path': path,
        'win_rate': win_rate,
        'per_scenario_win_rate': per_scenario_rate,
        'per_opponent_win_rate': per_opponent_rate,
        'scenarios': data['scenarios'],
        'opponents': data['opponents'],
        'opponent_label': data.get('opponentLabel') or '',
        'pretty_label': pretty,
        'n_ivs': n_ivs,
    }


def _align_opponents(loadouts_data: list[dict]) -> list[str]:
    """Intersect opponent lists across loadouts, preserving first-loadout order."""
    first = loadouts_data[0]['opponents']
    shared = set(first)
    for ld in loadouts_data[1:]:
        shared &= set(ld['opponents'])
    return [name for name in first if name in shared]


def _moveset_fast_move(label: str) -> str:
    return label.split('/', 1)[0].strip()


def _species_base_stats(gm: dict, species_name: str) -> dict | None:
    target = species_name.strip().lower()
    for p in gm['pokemon']:
        if (p.get('speciesName') or '').lower() == target:
            return p.get('baseStats')
    return None


def _species_id(gm: dict, species_name: str) -> str | None:
    target = species_name.strip().lower()
    for p in gm['pokemon']:
        if (p.get('speciesName') or '').lower() == target:
            return p.get('speciesId')
    return None


def _species_move_pools(gm: dict, species_id: str) -> tuple[list[str], list[str]]:
    for p in gm['pokemon']:
        if p.get('speciesId') == species_id:
            return sorted(p.get('fastMoves') or []), sorted(p.get('chargedMoves') or [])
    return [], []


def _pvpoke_move_segment(gm: dict, species_id: str, fast: str,
                         charged: list[str]) -> str | None:
    fm_pool, cm_pool = _species_move_pools(gm, species_id)
    if not fm_pool or not cm_pool:
        return None
    fm_part = str(fm_pool.index(fast)) if fast in fm_pool else fast
    cm_parts: list[str] = []
    for cm in charged:
        cm_parts.append(str(cm_pool.index(cm) + 1) if cm in cm_pool else cm)
    while len(cm_parts) < 2:
        cm_parts.append('0')
    return f'{fm_part}-{cm_parts[0]}-{cm_parts[1]}'


def _pvpoke_multi_url(gm: dict, species_id: str, league: str,
                      shields: tuple[int, int], fast: str,
                      charged: list[str]) -> str | None:
    cp = LEAGUE_CP.get(league)
    if cp is None:
        return None
    seg = _pvpoke_move_segment(gm, species_id, fast, charged)
    if seg is None:
        return None
    return (f'https://pvpoke.com/battle/multi/{cp}/all/'
            f'{species_id}/{shields[0]}{shields[1]}/{seg}/2-1/')


def _resolve_opponent(name: str) -> tuple[str, str, bool]:
    base = name
    if base.endswith(' (atk-weighted)'):
        base = base[:-len(' (atk-weighted)')]
    is_shadow = base.endswith(' (Shadow)')
    if is_shadow:
        base = base[:-len(' (Shadow)')]
    slug = base.lower().replace(' ', '_').replace('(', '').replace(')', '')
    if is_shadow:
        slug += '_shadow'
    return slug, base, is_shadow


def _pvpoke_single_url(gm: dict, league: str, shields: tuple[int, int],
                       focal_species_id: str, focal_fast: str,
                       focal_charged: list[str], opp_species_id: str,
                       opp_fast: str, opp_charged: list[str]) -> str | None:
    cp = LEAGUE_CP.get(league)
    if cp is None:
        return None
    focal_seg = _pvpoke_move_segment(gm, focal_species_id, focal_fast, focal_charged)
    opp_seg = _pvpoke_move_segment(gm, opp_species_id, opp_fast, opp_charged)
    if focal_seg is None or opp_seg is None:
        return None
    return (f'https://pvpoke.com/battle/{cp}/{focal_species_id}/'
            f'{opp_species_id}/{shields[0]}{shields[1]}/'
            f'{focal_seg}/{opp_seg}/')


def _format_move_stats(move: dict, species_types: list[str]) -> dict:
    power = move.get('power', 0)
    energy_gain = move.get('energyGain', 0)
    cooldown_ms = move.get('cooldown', 500)
    turns = move.get('turns')
    if turns is None:
        turns = max(1, int(round(cooldown_ms / 500)))
    dpt = power / turns if turns else 0.0
    ept = energy_gain / turns if turns else 0.0
    move_type = (move.get('type') or '').lower()
    return {
        'name': move.get('name', move.get('moveId', '')),
        'type': move_type,
        'power': power,
        'energy_gain': energy_gain,
        'turns': turns,
        'dpt': dpt,
        'ept': ept,
        'stab': move_type in species_types,
    }


def _lookup_move(gm: dict, move_id: str) -> dict | None:
    target = move_id.strip().lower()
    for m in gm['moves']:
        if m.get('moveId', '').lower() == target or m.get('name', '').lower() == target:
            return m
    return None


def _types_for(gm: dict, species_name: str) -> list[str]:
    target = species_name.strip().lower()
    for p in gm['pokemon']:
        if (p.get('speciesName') or '').lower() == target:
            return parse_types(p)
    return []


def _render_base_stats_table(loadouts_data: list[dict], gm: dict) -> str:
    rows: list[tuple[str, list[str]]] = []
    atks = [_species_base_stats(gm, ld['spec'].species) or {} for ld in loadouts_data]
    rows.append(('Attack', [str(s.get('atk', '')) for s in atks]))
    rows.append(('Defense', [str(s.get('def', '')) for s in atks]))
    rows.append(('Stamina', [str(s.get('hp', '')) for s in atks]))
    header = (
        '<thead><tr>'
        '<th scope="col">Base Stat</th>'
        + ''.join(f'<th scope="col">{html.escape(ld["spec"].label)}</th>'
                  for ld in loadouts_data)
        + '</tr></thead>'
    )
    body = []
    for label, vals in rows:
        body.append(
            f'<tr><th scope="row">{html.escape(label)}</th>'
            + ''.join(f'<td>{html.escape(v)}</td>' for v in vals)
            + '</tr>'
        )
    return (
        '<table class="base-stat-compare">'
        + header
        + '<tbody>' + ''.join(body) + '</tbody>'
        + '</table>'
    )


def _render_moveset_table(loadouts_data: list[dict], gm: dict) -> str:
    """Fast-move + charged-move stat side-by-side, one column per loadout."""
    col_bundles = []
    for ld in loadouts_data:
        spec = ld['spec']
        types = _types_for(gm, spec.species)
        fast = _lookup_move(gm, spec.fast_move)
        charged = [_lookup_move(gm, c) for c in spec.charged_moves]
        fast_stats = _format_move_stats(fast, types) if fast else None
        charged_stats = [_format_move_stats(c, types) if c else None
                         for c in charged]
        col_bundles.append((ld, fast_stats, charged_stats, types))

    header = (
        '<thead><tr>'
        '<th scope="col">Move</th>'
        + ''.join(f'<th scope="col">{html.escape(ld["spec"].label)}</th>'
                  for ld in loadouts_data)
        + '</tr></thead>'
    )

    def fmt_fast(stats: dict | None) -> str:
        if not stats:
            return 'unknown'
        stab = ' (STAB)' if stats['stab'] else ''
        return (f'{html.escape(stats["name"])}{stab} '
                f'<span class="move-aside">{stats["power"]} pwr, '
                f'{stats["energy_gain"]} eg, {stats["turns"]}t '
                f'({stats["dpt"]:.2f} DPT, {stats["ept"]:.2f} EPT)</span>')

    def fmt_charged(stats: dict | None) -> str:
        if not stats:
            return 'unknown'
        stab = ' (STAB)' if stats['stab'] else ''
        energy = stats.get('energy', 0) if hasattr(stats, 'get') else 0
        return (f'{html.escape(stats["name"])}{stab} '
                f'<span class="move-aside">{stats["power"]} pwr'
                + (f', {energy} energy' if energy else '') + '</span>')

    rows = ['<tr><th scope="row">Fast</th>'
            + ''.join(f'<td>{fmt_fast(s)}</td>' for _, s, _, _ in col_bundles)
            + '</tr>']
    max_cm = max(len(s[2]) for s in col_bundles)
    for idx in range(max_cm):
        cells = []
        for _, _, cms, _ in col_bundles:
            if idx < len(cms):
                cells.append(f'<td>{fmt_charged(cms[idx])}</td>')
            else:
                cells.append('<td>-</td>')
        label = f'Charged {idx + 1}'
        rows.append(
            f'<tr><th scope="row">{html.escape(label)}</th>' + ''.join(cells) + '</tr>'
        )

    return (
        '<table class="moveset-compare">'
        + header
        + '<tbody>' + ''.join(rows) + '</tbody>'
        + '</table>'
    )


def _render_pairwise_table(a: dict, b: dict, shared_opponents: list[str],
                           gm: dict, league: str) -> tuple[str, int]:
    a_map = dict(zip(a['opponents'], a['per_opponent_win_rate']))
    b_map = dict(zip(b['opponents'], b['per_opponent_win_rate']))

    a_spec: LoadoutSpec = a['spec']
    b_spec: LoadoutSpec = b['spec']
    a_label = html.escape(a_spec.label)
    b_label = html.escape(b_spec.label)

    a_sid = _species_id(gm, a_spec.species)

    # Rank entries by signed delta so the biggest A-wins-over-B deltas lead.
    entries = []
    shields = (1, 1)
    for name in shared_opponents:
        a_r = a_map[name]
        b_r = b_map[name]
        delta_pp = 100.0 * (a_r - b_r)
        entries.append((name, a_r, b_r, delta_pp))
    entries.sort(key=lambda e: e[3], reverse=True)

    rows = []
    flip_count = 0
    for name, a_r, b_r, delta_pp in entries:
        a_wins = a_r >= 0.5
        b_wins = b_r >= 0.5
        flip = a_wins != b_wins
        if flip:
            flip_count += 1
            flip_dir = 'pos' if delta_pp > 0 else 'neg'
            row_cls = f'matchup-delta-flip matchup-delta-flip-{flip_dir}'
            badge_cls = f'flip-badge flip-{flip_dir}'
            if delta_pp > 0:
                badge_label = f'+{a_spec.label}'
                tooltip = (f'{a_spec.label} wins this matchup where '
                           f'{b_spec.label} loses it (aggregate win rate '
                           f'crosses the 50% line).')
            else:
                badge_label = f'+{b_spec.label}'
                tooltip = (f'{b_spec.label} wins this matchup where '
                           f'{a_spec.label} loses it (aggregate win rate '
                           f'crosses the 50% line).')
        else:
            row_cls = ''
            badge_cls = 'flip-badge flip-none'
            badge_label = 'No flip'
            if a_r >= 0.5 and b_r >= 0.5:
                tooltip = 'Both loadouts win this matchup on aggregate (both above 50%).'
            elif a_r < 0.5 and b_r < 0.5:
                tooltip = 'Both loadouts lose this matchup on aggregate (both below 50%).'
            else:
                tooltip = 'No flip across the 50% line.'

        opp_slug, opp_base, opp_is_shadow = _resolve_opponent(name)
        opp_url = None
        if a_sid is not None:
            try:
                opp_fast_id, opp_charged_ids = get_default_moveset(
                    opp_base, league, shadow=opp_is_shadow)
            except KeyError:
                opp_fast_id, opp_charged_ids = None, None
            if opp_fast_id:
                opp_url = _pvpoke_single_url(
                    gm, league, shields,
                    focal_species_id=a_sid,
                    focal_fast=a_spec.fast_move,
                    focal_charged=list(a_spec.charged_moves),
                    opp_species_id=opp_slug,
                    opp_fast=opp_fast_id,
                    opp_charged=list(opp_charged_ids or []),
                )

        if opp_url:
            badge_html = (
                f'<a class="{badge_cls}" href="{html.escape(opp_url)}" '
                f'target="_blank" rel="noopener" '
                f'title="{html.escape(tooltip)}">{html.escape(badge_label)}</a>'
            )
        else:
            badge_html = (
                f'<span class="{badge_cls} flip-unlinked" '
                f'title="{html.escape(tooltip)}">{html.escape(badge_label)}</span>'
            )

        delta_cls = 'delta-pos' if delta_pp > 0 else 'delta-neg' if delta_pp < 0 else ''
        rows.append(
            f'<tr class="{row_cls}">'
            f'<td>{html.escape(name)}</td>'
            f'<td>{100 * a_r:.1f}%</td>'
            f'<td>{100 * b_r:.1f}%</td>'
            f'<td class="{delta_cls}">{delta_pp:+.1f}</td>'
            f'<td>{badge_html}</td>'
            f'</tr>'
        )

    table = (
        '<table class="matchup-delta sortable" '
        'data-default-sort="3" data-default-dir="desc">'
        '<thead><tr>'
        '<th scope="col" data-sort="str">Opponent</th>'
        f'<th scope="col" data-sort="pct" '
        f'title="Win rate with {a_label}. Varies all 4096 focal IVs x 9 shield '
        f'scenarios; opponent fixed at PvPoke-default IVs. Win = battle rating '
        f'&ge; 500.">{a_label} Win Rate</th>'
        f'<th scope="col" data-sort="pct" '
        f'title="Win rate with {b_label}. Varies all 4096 focal IVs x 9 shield '
        f'scenarios; opponent fixed at PvPoke-default IVs.">{b_label} Win Rate</th>'
        '<th scope="col" data-sort="num" '
        'title="Change in win rate in percentage points (first column minus second).'
        '">&#916; (pp)</th>'
        '<th scope="col" data-sort="bool" '
        'title="Whether the matchup crosses the 50% win line between the '
        'two loadouts.">Flip?</th>'
        '</tr></thead>'
        '<tbody>' + ''.join(rows) + '</tbody>'
        '</table>'
    )
    return table, flip_count


def _render_verdict(loadouts_data: list[dict]) -> str:
    """Win-rate framing for the lead line, matching the CD article."""
    parts = []
    for ld in loadouts_data:
        spec: LoadoutSpec = ld['spec']
        parts.append(
            f'<code>{html.escape(spec.label)}</code> wins '
            f'<strong>{100 * ld["win_rate"]:.1f}%</strong> of simulated '
            f'matchups'
        )
    joined = '; '.join(parts)
    return f'<p class="verdict-line">{joined}.</p>'


def build_comparison_fragment(loadouts_data: list[dict], league: str,
                              gm: dict, title: str,
                              summary: str = '',
                              include_matchup_delta: bool = True) -> str:
    """Return the HTML fragment for embedding in an article section.

    Contents: base-stat table, moveset-stat table, verdict, and (when
    ``include_matchup_delta`` is True) one matchup-delta table per
    unordered pair of loadouts plus a flip-count roll-up. Articles that
    already render per-form matchup-delta tables elsewhere should pass
    ``include_matchup_delta=False`` to avoid duplicating that content.
    """
    shared = _align_opponents(loadouts_data)

    bits: list[str] = []
    lead = (f'{len(shared)} opponents are common to all loadouts')
    bits.append(
        f'<details class="methodology-details compare-lead-details">'
        f'<summary>About these numbers</summary>'
        f'<p>{lead}. Win rate = fraction of simulations (4096 focal IVs '
        f'x 9 shield scenarios) where the focal species scores at '
        f'least 500.</p>'
        f'</details>'
    )

    dive_items = []
    for ld in loadouts_data:
        label = html.escape(ld['spec'].label)
        slug = ld['spec'].dive_slug
        species = html.escape(ld['spec'].species)
        dive_items.append(
            f'<li><strong>{label}:</strong> {species} '
            f'(<a href="../../{slug}/">deep dive</a>)</li>'
        )
    bits.append('<ul class="compare-dives">' + ''.join(dive_items) + '</ul>')

    if summary:
        summary_html = html.escape(summary.strip()).replace('\n\n', '</p><p>')
        bits.append(f'<p class="compare-summary">{summary_html}</p>')

    bits.append('<h3>Base Stats</h3>')
    bits.append(_render_base_stats_table(loadouts_data, gm))

    bits.append('<h3>Moveset</h3>')
    bits.append(_render_moveset_table(loadouts_data, gm))

    bits.append('<h3>Verdict</h3>')
    bits.append(_render_verdict(loadouts_data))

    if include_matchup_delta:
        pairs = list(itertools.combinations(loadouts_data, 2))
        per_pair_heading = len(pairs) > 1
        for a, b in pairs:
            if per_pair_heading:
                pair_heading = f'{a["spec"].label} vs {b["spec"].label}'
                bits.append(f'<h3>{html.escape(pair_heading)}</h3>')
            else:
                bits.append('<h3>Matchup Delta</h3>')
            table, flips = _render_pairwise_table(a, b, shared, gm, league)
            bits.append(table)
            bits.append(
                f'<p class="matchup-delta-summary">{flips} of {len(shared)} '
                f'opponents flip across the 50% win line between '
                f'{html.escape(a["spec"].label)} and '
                f'{html.escape(b["spec"].label)}.</p>'
            )

    return '\n'.join(bits)


COMPARE_CSS = """
table.base-stat-compare, table.moveset-compare {
  border-collapse: collapse; margin: 12px 0; width: 100%; font-size: 14px;
}
table.base-stat-compare th, table.base-stat-compare td,
table.moveset-compare th, table.moveset-compare td {
  border: 1px solid #0f3460; padding: 6px 10px; text-align: left;
}
table.base-stat-compare thead th, table.moveset-compare thead th {
  background: #16213e; color: #c8a2d0;
}
table.base-stat-compare tbody th, table.moveset-compare tbody th {
  background: #12192e; color: #9ab0d8; font-weight: 500;
}
table.base-stat-compare tbody td, table.moveset-compare tbody td {
  background: #0f162a; color: #e0e0e0;
}
span.move-aside { color: #8ea1bd; font-size: 12px; }
p.compare-lead { font-size: 14px; color: #b8c4d8; }
p.compare-summary { --sidebar-color: #7db87d;
  font-size: 14px; color: #cfe8cf; background: #1a2e1f;
  padding: 10px 14px 10px 18px; border-radius: 6px; }
ul.compare-dives { margin: 6px 0 10px 20px; padding: 0; font-size: 14px; }
ul.compare-dives li { margin: 2px 0; }
details.methodology-details { --sidebar-color: #5b8dd9;
  background: #12192e; border-radius: 4px;
  padding: 8px 12px 8px 16px; font-size: 13px; color: #b8c4d8;
  margin: 8px 0; }
details.methodology-details summary { cursor: pointer;
  color: #c8a2d0; font-weight: 500; }
details.methodology-details p { margin: 8px 0 0 0; }
"""


def render_standalone_html(title: str, description: str,
                           fragment: str, dive_links: list[tuple[str, str]],
                           authored_by: str = '') -> str:
    """Wrap the fragment in a full HTML page for the comparisons/ URL."""
    # Reuse the article stylesheet look-and-feel; duplicate the matchup-delta
    # styles so the standalone page renders correctly on its own.
    dive_link_html = ''
    if dive_links:
        items = ''.join(
            f'<li><a href="{html.escape(url)}">{html.escape(label)}</a></li>'
            for label, url in dive_links
        )
        dive_link_html = f'<div class="related"><strong>Source dives</strong><ul>{items}</ul></div>'

    author_html = f'<footer>By {html.escape(authored_by)}</footer>' if authored_by else ''
    _sidebar_css = sidebar_css([
        '.related', 'p.verdict-line',
        'p.compare-summary', 'details.methodology-details',
    ])
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
         sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px;
         background: #1a1a2e; color: #e0e0e0; line-height: 1.6; }}
  h1 {{ color: #e94560; margin-bottom: 6px; }}
  h2, h3 {{ color: #c8a2d0; border-bottom: 1px solid #0f3460;
        padding-bottom: 6px; margin-top: 30px; }}
  h3 {{ border-bottom: none; margin-top: 18px; font-size: 1.05em; }}
  a {{ color: #9be89b; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  p {{ margin: 10px 0; }}
  code {{ background: #16213e; padding: 2px 5px; border-radius: 3px;
          font-size: 0.9em; }}
  .related {{ --sidebar-color: #9be89b;
              background: #16213e; padding: 12px 16px 12px 20px;
              border-radius: 6px; margin: 16px 0; }}
  .related ul {{ margin: 6px 0 0 0; padding-left: 20px; }}
  table.matchup-delta {{ border-collapse: collapse; margin: 10px 0;
                         width: 100%; font-size: 13px; }}
  table.matchup-delta th, table.matchup-delta td {{ border: 1px solid #0f3460;
        padding: 5px 9px; text-align: left; }}
  table.matchup-delta thead th {{ background: #16213e; color: #c8a2d0; }}
  table.matchup-delta tbody td {{ background: #0f162a; color: #e0e0e0; }}
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
  p.verdict-line {{ --sidebar-color: #7db87d;
                    background: #1a2e1f; padding: 10px 14px 10px 18px;
                    color: #cfe8cf; border-radius: 6px; }}
  p.matchup-delta-summary {{ font-size: 13px; color: #9bb0d0; margin-top: 8px; }}
  table.sortable thead th {{ cursor: pointer; user-select: none; }}
  table.sortable thead th:hover {{ background: #1e2b4a; }}
  footer {{ color: #666; font-size: 13px; margin-top: 40px;
            border-top: 1px solid #0f3460; padding-top: 12px; }}
{COMPARE_CSS}
{_sidebar_css}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>{html.escape(description)}</p>
{dive_link_html}
{fragment}
{author_html}
</body>
</html>
"""


def _toml_string(s: str) -> str:
    """Serialise a Python string to TOML basic-string form.

    Escapes backslashes and double-quotes so description fields
    containing quoted phrases round-trip correctly. Multi-line
    strings use triple-quoted form (which already handles inner
    single quotes) with any literal triple-quote run inside the
    content escaped defensively.
    """
    if '\n' in s:
        # Triple-quoted multi-line: only need to guard against a
        # literal triple-quote run inside the content.
        escaped = s.replace('"' * 3, '\\"\\"\\"')
        return f'"""\n{escaped}\n"""'
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def parse_spec(spec_path: Path) -> dict:
    with open(spec_path, 'rb') as f:
        data = tomllib.load(f)
    missing = [k for k in ('slug', 'title', 'league', 'loadouts') if k not in data]
    if missing:
        sys.exit(f'Spec TOML missing fields: {missing}')
    if len(data['loadouts']) < 2:
        sys.exit('Spec must declare at least 2 loadouts')
    if len(data['loadouts']) > 4:
        sys.exit('Spec declares more than 4 loadouts; MVP renderer caps at N=4')
    loadouts: list[LoadoutSpec] = []
    for raw in data['loadouts']:
        loadouts.append(LoadoutSpec(
            label=raw['label'],
            species=raw['species'],
            dive_slug=raw['dive_slug'],
            fast_move=raw['fast_move'],
            charged_moves=tuple(raw['charged_moves']),
            shadow=bool(raw.get('shadow', False)),
        ))

    # Optional `order = [label, ...]` field reorders loadouts for display
    # (column order in comparison tables, card order in IV recs, etc.).
    # Labels not present in `order` keep their relative declaration order
    # at the end, so a partial list still works. Unknown labels fail
    # loudly so typos don't silently no-op.
    order = data.get('order')
    if order is not None:
        if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
            sys.exit(f"{spec_path}: 'order' must be a list of label strings.")
        known = {lo.label for lo in loadouts}
        unknown = [lbl for lbl in order if lbl not in known]
        if unknown:
            sys.exit(
                f"{spec_path}: 'order' references unknown label(s) "
                f"{unknown}; known labels: {sorted(known)}.")
        by_label = {lo.label: lo for lo in loadouts}
        ordered: list[LoadoutSpec] = []
        for lbl in order:
            ordered.append(by_label.pop(lbl))
        for lo in loadouts:
            if lo.label in by_label:
                ordered.append(lo)
                del by_label[lo.label]
        loadouts = ordered

    data['loadout_specs'] = loadouts
    return data


def run_comparison(spec: dict) -> tuple[str, list[dict]]:
    """Load data for every loadout and render the fragment. Return both."""
    loadouts_data = [load_loadout_data(s) for s in spec['loadout_specs']]
    gm = load_gamemaster()
    fragment = build_comparison_fragment(
        loadouts_data=loadouts_data,
        league=spec['league'],
        gm=gm,
        title=spec['title'],
        summary=spec.get('summary', ''),
    )
    return fragment, loadouts_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Compare two-or-more Pokemon loadouts by win rate.')
    parser.add_argument('spec_toml', type=Path, help='Comparison spec TOML.')
    parser.add_argument('--out-dir', type=Path, default=None,
                        help='Override default output dir.')
    args = parser.parse_args()

    spec = parse_spec(args.spec_toml)
    fragment, loadouts_data = run_comparison(spec)

    slug = spec['slug']
    out_dir = args.out_dir or (COMPARISONS_DIR / slug)
    out_dir.mkdir(parents=True, exist_ok=True)

    dive_links = [
        (ld['spec'].label, f'../../{ld["spec"].dive_slug}/')
        for ld in loadouts_data
    ]
    description = spec.get('summary', '') or spec['title']
    page = render_standalone_html(
        title=spec['title'],
        description=description,
        fragment=fragment,
        dive_links=dive_links,
        authored_by=spec.get('author', ''),
    )
    index_path = out_dir / 'index.html'
    index_path.write_text(page)

    meta = (
        f'title = {_toml_string(spec["title"])}\n'
        f'description = {_toml_string(description.strip())}\n'
        f'landing = "index.html"\n'
    )
    (out_dir / 'meta.toml').write_text(meta)

    print(f'Wrote {index_path}')
    print(f'Wrote {out_dir / "meta.toml"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
