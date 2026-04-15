"""Rendering helpers for IV deep dive HTML output.

Functions that produce HTML fragments (hover text, tier badges, matchup
bullets, etc.) for injection into the interactive deep dive page.  Pure
HTML generation -- no simulation or analysis logic.
"""
import hashlib
import math
import re

from dataclasses import dataclass, field
from typing import Optional

import deep_dive_analysis as analysis
from gopvpsim.anchors import derive_short_name


# ---------------------------------------------------------------------------
# Shared data types and utilities
# ---------------------------------------------------------------------------


@dataclass
class AnalysisContext:
    """Read-only bundle of pre-computed data for analysis section renderers.

    Built once by ``generate_analysis_sections`` in deep_dive.py, then
    passed to each ``render_*`` function in this module.  No renderer
    mutates the context (``anchor_passing_sink`` is populated as a
    documented side-effect by the results renderer).
    """
    data_obj: dict
    scores_flat: list
    nIvs: int
    nS: int
    nO: int
    scenarios: list
    opponents: list
    opp_iv_mode: str
    opp_label: str
    moveset_idx: int
    moveset_label: str
    ref_iv: int
    ref_atk: float
    ref_def: float
    score_arrays: dict
    scene_ranks: list
    avg_ranks: list
    avg_scores: list
    ranked: list
    flips: dict
    flip_summary: list
    flip_map: dict
    rec_candidates: list
    hp_list: list
    anchor_flip_records: list
    all_matchup_boundaries: list
    effective_tiers: list
    has_toml_tiers: bool
    slayer_iter_result: Optional[dict]
    resolved_anchors_top: list
    opp_info_cache: dict
    focal_types: list
    focal_moves: list
    anchor_passing_sink: Optional[dict]


# ---------------------------------------------------------------------------
# Opponent color-coding
# ---------------------------------------------------------------------------

_OPP_COLORS = [
    '#ff6b6b', '#ffd93d', '#6bcb77', '#4d96ff',
    '#ff922b', '#cc5de8', '#20c997', '#74c0fc',
    '#ff8787', '#ffe066', '#8ce99a', '#91a7ff',
    '#ffa94d', '#e599f7', '#63e6be', '#a5d8ff',
]


def _opp_color(name):
    """Deterministic color for an opponent name (case-insensitive)."""
    h = int(hashlib.md5(name.lower().encode()).hexdigest(), 16)
    return _OPP_COLORS[h % len(_OPP_COLORS)]


def _opp_b(name):
    """Wrap an opponent name in a colored <b> tag."""
    return f'<b style="color:{_opp_color(name)}">{name}</b>'


def _opp_strong(color_key, display_text=None):
    """Wrap text in a colored <strong> tag using the opponent's color."""
    if display_text is None:
        display_text = color_key
    return f'<strong style="color:{_opp_color(color_key)}">{display_text}</strong>'


# ---------------------------------------------------------------------------
# Deep dive CSS
# ---------------------------------------------------------------------------

DEEP_DIVE_CSS = """
.dd-section { background: #16213e; padding: 16px 20px; border-radius: 8px; margin: 20px 0; }
.dd-h2 { color: #e94560; font-size: 1.3rem; margin: 0 0 12px 0; border-bottom: 1px solid #0f3460; padding-bottom: 6px; }
.dd-h3 { color: #58a6ff; font-size: 1rem; margin: 14px 0 8px 0; }
.dd-table { border-collapse: collapse; margin: 8px 0 12px; font-size: 0.82rem; width: 100%; }
.dd-table.dd-narrow { width: auto; }
.dd-table th, .dd-table td { padding: 4px 8px; border: 1px solid #0f3460; text-align: left; }
.dd-table th { background: #0f3460; color: #58a6ff; font-weight: 600; }
.dd-table td { background: #1a1a2e; }
.dd-table tr:hover td { background: #16213e; }
.dd-gain { color: #3fb950; }
.dd-loss { color: #f85149; }
.dd-strong { font-weight: 700; color: #FFD700; }
.dd-rank-good { color: #3fb950; font-weight: 600; }
.dd-rank-bad { color: #f85149; }
.dd-small { font-size: 0.82rem; color: #8b949e; margin: 4px 0; }
.dd-callout { background: #0f3460; border-left: 3px solid #58a6ff; padding: 8px 12px; margin: 10px 0; border-radius: 0 4px 4px 0; font-size: 0.85rem; }
.dd-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.75rem; font-weight: 600; }
.dd-methods-dl { margin: 8px 0; }
.dd-methods-dl dt { color: #58a6ff; font-weight: 600; margin-top: 8px; }
.dd-methods-dl dd { margin-left: 16px; font-size: 0.88rem; color: #aaa; }
.dd-flip-detail { margin: 6px 0; }
.dd-flip-detail summary { cursor: pointer; padding: 4px 0; font-size: 0.9rem; }
.dd-flip-detail summary:hover { color: #58a6ff; }
.dd-rec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr)); gap: 12px; margin: 12px 0; }
.dd-rec-card { background: #0f3460; border: 1px solid #1a3a6e; border-radius: 6px; padding: 12px; }
.dd-rec-card h4 { color: #e94560; margin: 0 0 6px; font-size: 1rem; }
.dd-rec-card p { margin: 3px 0; font-size: 0.88rem; }
.dd-prose { font-size: 0.88rem; color: #b0b8c4; margin: 4px 0 8px 0; font-style: italic; }
.dd-threshold-list { list-style: none; padding: 0; margin: 8px 0; }
.dd-threshold-list li { padding: 4px 0 4px 12px; border-left: 2px solid #0f3460; margin: 4px 0; font-size: 0.88rem; }
.dd-threshold-list .dd-loss-item { border-left-color: #f85149; }
.dd-opp-label { color: #8b949e; font-size: 0.75rem; }
.dd-slayer-top td { background: #1e2d4a; }
.dd-slayer-top td:first-child { border-left: 3px solid #58a6ff; }
.dd-slayer-hidden { display: none; }
.dd-slayer-hidden.dd-slayer-shown { display: table-row; }
.dd-slayer-toggle { background:#0f3460; color:#58a6ff; border:1px solid #1a3a6e;
  padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem;
  margin-top:4px; }
.dd-slayer-toggle:hover { background:#1a3a6e; color:#fff; }
.dd-anchor-tag { display:inline-block; background:#0f3460; color:#58a6ff;
  padding:1px 6px; border-radius:3px; font-size:0.72rem; margin:1px 2px 1px 0;
  font-family:monospace; cursor:help; }
.dd-anchor-tag:hover { background:#1a3a6e; color:#fff; }
.dd-anchor-tag-count { color:#d29922; font-weight:600; }
.dd-anchor-tags-cell { max-width: 480px; }
.dd-anchor-tags-cell .dd-anchor-tag { vertical-align: baseline; }
/* The badges live inside an inner <div> rather than directly in the <td>
   because <td> uses display: table-cell, which silently ignores max-height
   in every major browser. Capping the cell to ~2 lines requires a real
   block-level wrapper. The wrapper itself is click-toggleable: clicking
   anywhere on the cell whitespace flips that one cell between compact
   and expanded; clicking a specific badge triggers its hover tooltip
   instead (badges keep cursor:help to signal hover-only). */
.dd-anchor-tags-inner { white-space: normal; line-height: 1.5;
  cursor: pointer; }
/* Compact mode: cap tag cells at ~2 lines so survivor rows stay readable.
   The "Expand all tags" toggle in the slayer section header removes this
   class from every inner div to reveal the full badge wall. */
.dd-anchor-tags-inner.dd-tags-compact { max-height: 3em; overflow: hidden;
  position: relative; }
.dd-anchor-tags-inner.dd-tags-compact::after { content: ""; position: absolute;
  bottom: 0; left: 0; right: 0; height: 1.5em; pointer-events: none;
  background: linear-gradient(transparent, #16213e); }
.dd-tags-toggle { background:#0f3460; color:#58a6ff; border:1px solid #1a3a6e;
  padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem;
  margin:6px 0; }
.dd-tags-toggle:hover { background:#1a3a6e; color:#fff; }
.dd-filter-hidden { display: none !important; }
.dd-filter-toggle { background:#0f3460; color:#58a6ff; border:1px solid #1a3a6e;
  padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem;
  margin:6px 0 4px 0; }
.dd-filter-toggle:hover { background:#1a3a6e; color:#fff; }
.dd-filter-panel { background:#0a1a30; border:1px solid #1a3a6e; border-radius:4px;
  padding:8px 10px; margin:4px 0 8px 0; font-size:0.78rem; }
.dd-filter-panel-group { margin-bottom:6px; padding-bottom:4px;
  border-bottom:1px solid #16213e; }
.dd-filter-panel-group:last-child { border-bottom:none; }
.dd-filter-master { font-weight:600; color:#58a6ff; display:block; }
.dd-filter-children { margin:2px 0 0 18px; display:flex; flex-wrap:wrap;
  gap:4px 10px; }
.dd-filter-children label { font-family:monospace; font-size:0.72rem;
  color:#b0b8c4; cursor:pointer; }
.dd-filter-children label:hover { color:#fff; }
.dd-filter-controls { margin-top:6px; padding-top:6px; border-top:1px solid #16213e;
  display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.dd-filter-controls button { background:#1a3a6e; color:#fff; border:none;
  padding:3px 8px; border-radius:3px; cursor:pointer; font-size:0.75rem; }
.dd-filter-controls button:hover { background:#264a8a; }
.dd-filter-status { color:#8b949e; font-size:0.72rem; margin-left:auto; }
.dd-auto-marker { color:#d29922; font-size:0.7rem; font-weight:400;
  font-style:italic; }
/* Notable IVs section: dd-notable-only is a section-level class that
   hides every dd-not-notable card. The header checkbox toggles the
   class via ddNotableToggle(); default state is "only notable". */
.dd-notable-only .dd-not-notable { display: none; }
.dd-rec-card.dd-notable { border-color: #d29922; }
/* Per-card "Show all N" expand: overflow members render with
   dd-iv-hidden and become visible when ddNotableExpand() adds
   dd-iv-shown. Same pattern as the slayer-card row expand. */
.dd-rec-card .dd-iv-hidden { display: none; }
.dd-rec-card .dd-iv-hidden.dd-iv-shown { display: block; }
.dd-iv-toggle { background:#0f3460; color:#58a6ff; border:1px solid #1a3a6e;
  padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem;
  margin-top:6px; }
.dd-iv-toggle:hover { background:#1a3a6e; color:#fff; }
.dd-collapsible { margin: 4px 0; }
.dd-collapsible > summary { list-style: none; }
.dd-collapsible > summary::-webkit-details-marker { display: none; }
.dd-collapsible > summary::before { content: "\\25b6"; display: inline-block;
  margin-right: 6px; font-size: 0.7em; transition: transform 0.15s; color: #58a6ff; }
.dd-collapsible[open] > summary::before { transform: rotate(90deg); }
.dd-expert-zone { border-left: 4px solid #d29922; padding-left: 16px; margin: 16px 0; }
.dd-expert-zone h3 { color: #d29922; margin: 0 0 10px 0; }
.dd-expert-source { color: #8b949e; font-size: 0.82rem; font-style: italic; margin: 0 0 12px 0; }
.dd-expert-anchors { margin: 10px 0; }
.dd-expert-anchors li { margin: 4px 0; }
.dd-narrative-zone { border-left: 4px solid #9b59b6; padding: 12px 0 12px 16px; margin: 20px 0; }
.dd-narrative-prose { font-size: 0.9rem; color: #c8ccd4; line-height: 1.6; margin: 6px 0; }
.dd-narrative-rec { color: #3fb950; font-weight: 600; }
.dd-narrative-loss { color: #f85149; font-size: 0.88rem; font-style: italic; margin: 8px 0 4px 0; }
.dd-sim-zone { border-left: 4px solid #58a6ff; padding-left: 16px; margin: 16px 0; }
.dd-sim-zone > h3 { color: #58a6ff; margin: 0 0 10px 0; }
"""

def parse_mode(composite_mode):
    """Decompose a composite mode string into (opp_iv_mode, bait_mode).

    Accepted forms:
      'pvpoke'         -> ('pvpoke', 'bait')     # bait-on default
      'rank1'          -> ('rank1',  'bait')
      'pvpoke:bait'    -> ('pvpoke', 'bait')
      'pvpoke:nobait'  -> ('pvpoke', 'nobait')
      'rank1:nobait'   -> ('rank1',  'nobait')

    Legacy callers that only know the opp-iv axis can pass
    ``'pvpoke'``/``'rank1'`` and get the bait-on default.
    """
    if ':' in composite_mode:
        opp_iv, bait = composite_mode.split(':', 1)
        return opp_iv, bait
    return composite_mode, 'bait'


def compose_mode(opp_iv_mode, bait_mode='bait'):
    """Inverse of ``parse_mode``. Bait-on collapses to the bare opp-iv form
    so existing keys (e.g. ``f'{mi}_pvpoke'``) stay unchanged when bait mode
    isn't part of the sweep."""
    if bait_mode == 'nobait':
        return f'{opp_iv_mode}:nobait'
    return opp_iv_mode


def mode_pretty_label(composite_mode):
    """Human-readable label for a composite mode, e.g. for dropdowns."""
    opp_iv, bait = parse_mode(composite_mode)
    opp_label = 'PvPoke Defaults' if opp_iv == 'pvpoke' else 'Rank 1'
    if bait == 'nobait':
        return f'{opp_label}, no bait'
    return opp_label


@dataclass
class IVCategory:
    """A named IV grouping with explicit provenance.

    Abstracts over the several sources of named IV groupings the deep dive
    already produces (anchor-driven slayer categories, stat-cutoff threshold
    tiers, future matchup-conditional categories) so a single renderer can
    surface them all uniformly. Composite categories (intersections of
    multiple parents) are the framework's payoff: ``13/0/11 is the rare
    bulk-floor slayer`` falls out as ``Atk Slayer ∩ Top 5%`` with one IV.

    Fields are intentionally permissive: a slayer kind populates
    ``source_anchors``, a tier kind populates ``source_tier`` and
    ``stat_cutoffs``, a composite populates ``source_categories``, a
    future matchup kind populates ``matchup_conditions``. The renderer
    inspects whichever fields are set.

    ``member_meta`` carries per-IV info the renderer needs (e.g. mirror
    wins, the original IV triple) without forcing the renderer to plumb
    extra data structures alongside the category list.
    """
    name: str
    kind: str  # 'slayer' | 'tier' | 'structural' | 'composite' | 'matchup'
    members: list  # canonical IV indices, sorted ascending
    description: str = ''
    # Provenance -- exactly which upstream sources built this category.
    source_categories: list = field(default_factory=list)  # composites
    source_anchors: list = field(default_factory=list)     # slayer kinds
    source_tier: object = None                             # tier kinds (str or None)
    # Membership predicates -- declarative; multiple shapes coexist.
    stat_cutoffs: object = None  # dict {'atk', 'def', 'hp'} or None
    matchup_conditions: object = None
    # Per-member info: maps canonical IV index -> dict with whatever
    # the renderer needs (total_wins, avg_score, original triple, etc.).
    member_meta: dict = field(default_factory=dict)


def hover_text(r, tier_name=None, ref_per_opp=None, ref_label=None,
                opponent_names=None, shield_scenarios=None):
    """Build hover text for a single IV result.

    If ref_per_opp is provided (the rank-1 IV's per-opponent scores),
    show which matchups were gained/lost compared to rank 1.
    """
    lines = [
        f"IVs: {r['atk_iv']}/{r['def_iv']}/{r['sta_iv']}",
        f"L{r['level']} CP{r['cp']}",
        f"Atk:{r['atk']:.2f} Def:{r['def_']:.2f} HP:{r['hp']}",
        f"SP Rank: #{r['sp_rank']} | Battle Rank: #{r['battle_rank']}",
        f"Avg Score: {r['avg_score']:.1f}",
    ]
    if tier_name:
        lines.append(f"Tier: {tier_name}")

    # Matchup diffs vs rank 1
    if ref_per_opp and opponent_names and shield_scenarios and 'per_opp' in r:
        my_opp = r['per_opp']
        if my_opp is not ref_per_opp:  # skip for rank 1 itself
            lines.append(f'')
            lines.append(f'vs {ref_label}:')
            for si, (s_focal, s_opp) in enumerate(shield_scenarios):
                gained = []
                lost = []
                for oi, opp_name in enumerate(opponent_names):
                    key = (si, oi)
                    my_score = my_opp.get(key, 0)
                    ref_score = ref_per_opp.get(key, 0)
                    my_win = my_score >= 500
                    ref_win = ref_score >= 500
                    # Short name for display
                    short = opp_name.split('(')[0].strip()[:12]
                    if my_win and not ref_win:
                        gained.append(short)
                    elif not my_win and ref_win:
                        lost.append(short)
                scenario_label = f'{s_focal}v{s_opp}'
                parts = []
                if gained:
                    parts.append(f'+{",".join(gained)}')
                if lost:
                    parts.append(f'-{",".join(lost)}')
                if parts:
                    lines.append(f'  {scenario_label}: {" | ".join(parts)}')
                else:
                    lines.append(f'  {scenario_label}: (same matchups)')

    return '<br>'.join(lines)



def threshold_desc(thresh):
    """Human-readable description of a threshold."""
    parts = []
    if thresh['attack'] > 0:
        parts.append(f"Atk≥{thresh['attack']}")
    if thresh['defense'] > 0:
        parts.append(f"Def≥{thresh['defense']}")
    if thresh['stamina'] > 0:
        parts.append(f"HP≥{thresh['stamina']}")
    return ', '.join(parts) if parts else '(no requirements)'



def opp_importance(scores_flat, nIvs, nS, nO, si, top_set, opponents):
    """Rank opponents by how much they differentiate top_set from population."""
    results = []
    for oi in range(nO):
        top_avg = sum(scores_flat[iv * nS * nO + si * nO + oi] for iv in top_set) / len(top_set)
        all_avg = sum(scores_flat[iv * nS * nO + si * nO + oi] for iv in range(nIvs)) / nIvs
        results.append({'opponent': opponents[oi], 'top_avg': top_avg, 'all_avg': all_avg, 'gap': top_avg - all_avg})
    results.sort(key=lambda x: abs(x['gap']), reverse=True)
    return results



def iv_label(data, iv):
    return f"{data['ivA'][iv]}/{data['ivD'][iv]}/{data['ivS'][iv]}"



def tier_badge_html(data, iv):
    """Show badges for ALL tiers this IV meets, not just the primary one."""
    all_tiers = data.get('ivAllTiers', [])
    if iv < len(all_tiers) and all_tiers[iv]:
        badges = []
        for ti in all_tiers[iv]:
            t = data['tiers'][ti]
            badges.append(f'<span class="dd-badge" style="background:{t["color"]};color:#000">{t["name"]}</span>')
        return ' ' + ' '.join(badges)
    # Fallback to single tier
    ti = data['ivTiers'][iv]
    if ti < 0:
        return ''
    t = data['tiers'][ti]
    return f' <span class="dd-badge" style="background:{t["color"]};color:#000">{t["name"]}</span>'



def _bait_suffix(entry):
    """Return a parenthetical bait-mode suffix for a flip entry, or ''."""
    bm = entry.get('bait_modes', set())
    if bm == {'bait'}:
        return ' (bait only)'
    elif bm == {'nobait'}:
        return ' (no-bait only)'
    return ''


def prose_flip_summary(flip_data, max_gains=3, max_losses=2, has_bait_axis=False):
    """Generate a natural-language summary of matchup gains/losses.

    Returns a string like "gains Togekiss 1v2, G. Stunfisk 2v0; loses Steelix 0v2, 1v2"
    """
    parts = []
    gains = flip_data.get('gains', [])
    losses = flip_data.get('losses', [])
    if gains:
        # Sort by delta descending
        top = sorted(gains, key=lambda e: e['iv_score'] - e['ref_score'], reverse=True)[:max_gains]
        gain_strs = [f'{e["opponent"]} {e["scenario"]}{_bait_suffix(e) if has_bait_axis else ""}' for e in top]
        extra = len(gains) - len(top)
        s = 'gains ' + ', '.join(gain_strs)
        if extra > 0:
            s += f' (+{extra} more)'
        parts.append(s)
    if losses:
        top = sorted(losses, key=lambda e: e['ref_score'] - e['iv_score'], reverse=True)[:max_losses]
        loss_strs = [f'{e["opponent"]} {e["scenario"]}{_bait_suffix(e) if has_bait_axis else ""}' for e in top]
        extra = len(losses) - len(top)
        s = 'loses ' + ', '.join(loss_strs)
        if extra > 0:
            s += f' (+{extra} more)'
        parts.append(s)
    return '; '.join(parts) if parts else 'no matchup flips'



def format_stat_cutoffs(cutoffs):
    """Render an IVCategory.stat_cutoffs dict as a human-readable string,
    e.g. ``atk≥128, hp≥139``. Returns '' if no constraints are set."""
    if not cutoffs:
        return ''
    parts = []
    if cutoffs.get('atk'):
        parts.append(f"atk≥{cutoffs['atk']:g}")
    if cutoffs.get('def'):
        parts.append(f"def≥{cutoffs['def']:g}")
    if cutoffs.get('hp'):
        parts.append(f"hp≥{cutoffs['hp']:g}")
    return ', '.join(parts)



def composite_tradeoff_prose(member_idx, comp_cat, parent_categories, data_obj):
    """Auto-generate the per-member tradeoff prose for a composite category.

    The Annihilape 13/0/11 wording is the literal target:
        "Sole Atk Slayer that also clears the Top 5% bulk floor (HP≥139).
         Trades mirror dominance (45/132 wins, vs 132/132 for the top
         survivors) for the broader-meta bulk floor."

    Inputs:
        member_idx: canonical IV index of the member to describe.
        comp_cat: the composite IVCategory.
        parent_categories: dict of name → IVCategory for the parent
            slayer/tier categories the composite was built from. Used
            to compute the "max wins in cohort" baseline.
        data_obj: for stat lookups (used by callers; this helper itself
            only reads parent_categories).

    Returns a single string sentence (HTML-safe; no tags).
    """
    if not comp_cat.source_categories or len(comp_cat.source_categories) < 2:
        return ''
    slayer_name, tier_name = comp_cat.source_categories[0], comp_cat.source_categories[1]
    slayer_parent = parent_categories.get(slayer_name)
    n_in_comp = len(comp_cat.members)

    # Identity sentence
    if n_in_comp == 1:
        identity = (f"The sole {slayer_name} that also clears "
                    f"the {tier_name} threshold")
    else:
        identity = (f"One of {n_in_comp} {slayer_name} members "
                    f"that also clear the {tier_name} threshold")
    cutoffs = format_stat_cutoffs(comp_cat.stat_cutoffs)
    if cutoffs:
        identity += f" ({cutoffs})"
    identity += '.'

    # Tradeoff sentence — compute against the slayer cohort's max wins.
    tradeoff = ''
    if slayer_parent and slayer_parent.member_meta:
        all_wins = [
            meta.get('total_wins', 0)
            for meta in slayer_parent.member_meta.values()
        ]
        max_wins = max(all_wins) if all_wins else 0
        this_wins = (slayer_parent.member_meta.get(member_idx, {})
                     .get('total_wins', 0))
        if max_wins > 0 and this_wins < max_wins:
            tradeoff = (f" Trades mirror dominance ({this_wins}/{max_wins} wins, "
                        f"vs {max_wins}/{max_wins} for the top {slayer_name} "
                        f"survivors) for the {tier_name} cutoff.")
        elif max_wins > 0 and this_wins == max_wins:
            tradeoff = (f" Carries top {slayer_name} mirror wins "
                        f"({this_wins}/{max_wins}) AND clears the {tier_name} "
                        f"cutoff — no tradeoff.")
    return identity + tradeoff



def matchup_subtitle(cat):
    """Render an IVCategory.matchup_conditions list as a one-line summary
    (e.g. ``rank 1 Lickitung · 0v0 · win`` or ``· no bait`` when nobait).
    Returns '' for non-matchup categories."""
    if not cat.matchup_conditions:
        return ''
    bits = []
    for c in cat.matchup_conditions:
        opp = c.get('opponent', '?')
        opp_iv = c.get('opponent_ivs', '?')
        oppiv_label = ('PvPoke default' if opp_iv == 'pvpoke'
                        else 'rank 1' if opp_iv == 'rank1' else opp_iv)
        scen = c.get('scenario', (0, 0))
        bait = c.get('bait')
        outcome = c.get('outcome', 'win')
        b = f'{oppiv_label} {opp} · {scen[0]}v{scen[1]} · {outcome}'
        if bait == 'nobait':
            b += ' · no bait'
        elif bait == 'bait' and 'only' in cat.name:
            b += ' · with bait'
        bits.append(b)
    return ' | '.join(bits)



def render_matchup_boundary_bullets(boundaries, has_bait_axis=False,
                                     toggle_id=None, top_n=10):
    """Render matchup-flipping boundaries as HTML <li> bullets.

    Format: "141.66 Def + 138 HP flips Medicham (1v1, 1v2 no bait) [85 IVs]"

    When *has_bait_axis* is True and a boundary only fires in one bait
    mode, the scenario string is annotated with "no bait" or "with bait".

    When *toggle_id* is set and there are more than *top_n* bullets,
    the excess are hidden behind a show/hide toggle button.
    """
    lines = []
    for i, b in enumerate(boundaries):
        scen_str = ', '.join(
            f'{s[0]}v{s[1]}' for s in sorted(b['scenarios']))
        bait_modes = b.get('bait_modes', set())
        if has_bait_axis and len(bait_modes) == 1:
            bait_tag = 'no bait' if 'nobait' in bait_modes else 'with bait'
            scen_str += f' {bait_tag}'
        hp_str = ''
        if b.get('hp_threshold') is not None:
            hp_str = (f' + <span class="dd-strong">'
                      f'{b["hp_threshold"]} HP</span>')
        stat_label = 'Atk' if b.get('stat') == 'atk' else 'Def'
        hidden = ''
        if toggle_id and i >= top_n:
            hidden = f' class="dd-iv-hidden" data-tier-card="{toggle_id}"'
        lines.append(
            f'<li{hidden}><span class="dd-strong">'
            f'{b["threshold"]:.2f} {stat_label}</span>{hp_str} '
            f'flips {_opp_b(b["opponent"])} '
            f'(<span class="dd-gain">{scen_str}</span>) '
            f'<span class="dd-small">[{b["n_passing"]} IVs]</span></li>'
        )
    if toggle_id and len(boundaries) > top_n:
        n = len(boundaries)
        lines.append(
            f'<button class="dd-iv-toggle" onclick="'
            f"(function(btn){{"
            f"var items=document.querySelectorAll("
            f"'[data-tier-card=&quot;{toggle_id}&quot;]');"
            f"var shown=items.length>0&&"
            f"items[0].classList.contains('dd-iv-shown');"
            f"items.forEach(function(r){{"
            f"r.classList.toggle('dd-iv-shown',!shown);}});"
            f"btn.textContent=shown?"
            f"'Show all {n} boundaries':'Collapse to top {top_n}';"
            f"}})(this)"
            f'">Show all {n} boundaries</button>'
        )
    return lines



def anchor_group_id(parent, opponent, target_stat, move_id):
    """Deterministic short id for an anchor bullet's (parent, opponent,
    target_stat, move_id) group. Used as a DOM attribute so JS can
    look up which of the user's canonical IVs pass this specific
    bullet and fill in a "— yours: 0/15/15, 1/14/15" annotation.
    """
    import hashlib as _hl
    key = '|'.join(str(x) for x in (parent, opponent, target_stat, move_id or ''))
    return 'af-' + _hl.md5(key.encode('utf-8')).hexdigest()[:10]



def render_anchor_flip_bullets(records, anchor_passing_sink=None,
                               has_bait_axis=False):
    """Render anchor-flip records as RyanSwag-style HTML <li> bullets.

    Grouping grain is ``(parent, opponent, target_stat, move_id)``.
    Within each group we take the *minimum* threshold value: Level 3
    parents expand into one sub-anchor per (move, damage tier), and a
    higher-tier sub-anchor is automatically subsumed by its lower-tier
    sibling for matchup-flipping purposes (anything that crosses the
    high tier necessarily crosses the low one). The min threshold is
    "the smallest stat at which this move starts driving any flip
    against this opponent" — the actionable number.

    Result: one bullet per (parent, opponent, move) triple, e.g.
        "96.62 Def for lickilicky bulk (Hyper Beam) vs Lickilicky (0v1, 1v2)"
    Sub-anchors with no ``move_id`` (Level 1/2 anchors) keep their
    own bullet and omit the move parenthetical entirely.

    When *has_bait_axis* is True and a flip only fires in one bait
    mode, the scenario string is annotated with "no bait" or
    "with bait".

    Bullets are sorted within each (parent, opponent) family by
    threshold ascending so increasing-stat bulkpoints read top-to-bottom
    in the order a player would clear them.

    When ``anchor_passing_sink`` is a dict, each emitted bullet
    populates it with ``{anchor_id: sorted(passing_iv_idx_list)}``
    where the passing set is the union across all sub-anchors in the
    group. The sink-provided path also injects a
    ``<span class="user-anchor-hits" data-anchor-id="…"></span>``
    placeholder into every bullet so the JS can fill it in with
    "— yours: a/d/s, a/d/s" after a Poke Genie CSV is loaded.
    """
    # Group: (parent, opponent, target_stat, move_id) -> list of records.
    groups: dict = {}
    order: list = []  # preserve first-seen order for stable output
    for rec in records:
        a = rec['anchor']
        key = (a.parent, rec['opponent'], a.target_stat, a.move_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(rec)

    # Sort groups within each (parent, opponent) family by min threshold
    # so a parent with multiple moves reads in ascending stat order.
    def _group_sort_key(key):
        recs = groups[key]
        min_thresh = min(r['anchor'].threshold_value for r in recs)
        # Primary: parent+opponent groups stay together (preserve original
        # first-seen order via index). Secondary: ascending threshold.
        return (order.index(key) // 1000, key[0], key[1], min_thresh)
    # Stable group ordering: keep parents+opponents in original first-seen
    # order, then sort within by min threshold. Use a two-pass approach
    # so different parents/opponents don't interleave.
    family_order: list = []
    families: dict = {}
    for key in order:
        family = (key[0], key[1], key[2])  # parent, opponent, target_stat
        if family not in families:
            families[family] = []
            family_order.append(family)
        families[family].append(key)
    for family in family_order:
        families[family].sort(
            key=lambda k: min(r['anchor'].threshold_value for r in groups[k])
        )

    lines = []
    for family in family_order:
        for key in families[family]:
            recs = groups[key]
            first = recs[0]['anchor']
            stat_label = 'Atk' if first.target_stat == 'atk' else 'Def'
            anchor_label = first.parent_display_name or first.label or first.parent

            min_thresh = min(r['anchor'].threshold_value for r in recs)

            move_str = ''
            if first.move_id:
                move_str = f' ({analysis.pretty_name(first.move_id)})'

            # Scenarios: union across sub-anchors of the same group
            # (different damage tiers of the same move usually flip
            # the same scenarios, but if they diverge we show all).
            scen_set = set()
            for r in recs:
                for s in r['scenarios']:
                    scen_set.add(tuple(s))
            scen_strs = ', '.join(f'{s[0]}v{s[1]}' for s in sorted(scen_set))

            # Bait modes: union across sub-anchors (same pattern).
            bait_union = set()
            for r in recs:
                bait_union |= r.get('bait_modes', set())
            if has_bait_axis and len(bait_union) == 1:
                bait_tag = ('no bait' if 'nobait' in bait_union
                            else 'with bait')
                scen_strs += f' {bait_tag}'

            # HP co-condition: if any record in the group carries an
            # hp_threshold, show it alongside the def threshold.
            hp_thresholds = [r.get('hp_threshold') for r in recs
                             if r.get('hp_threshold') is not None]
            hp_str = ''
            if hp_thresholds:
                hp_str = (f' + <span class="dd-strong">{min(hp_thresholds)}'
                          f' HP</span>')

            # Anchor id + passing-IV union for the user-collection
            # annotation layer. Only populated when a sink was passed.
            anchor_span = ''
            if anchor_passing_sink is not None:
                anchor_id = anchor_group_id(
                    first.parent, recs[0]['opponent'],
                    first.target_stat, first.move_id,
                )
                # Union passing_ivs across every sub-anchor in the group.
                # Any IV in the union meets at least one sub-anchor's
                # flip condition for this (parent, opponent, move) bullet.
                union = set()
                for r in recs:
                    for iv in r.get('passing_ivs', []) or []:
                        union.add(iv)
                # Store once per anchor_id. If the same id appears in
                # multiple grouping passes (e.g. tier-filtered + flat
                # list), the underlying record set is identical, so
                # overwriting is a no-op.
                anchor_passing_sink[anchor_id] = sorted(union)
                anchor_span = (
                    f' <span class="user-anchor-hits" '
                    f'data-anchor-id="{anchor_id}"></span>'
                )

            opp_name = recs[0]["opponent"]
            opp_c = _opp_color(opp_name)
            lines.append(
                f'<li><span class="dd-strong">{min_thresh:.2f} {stat_label}</span>'
                f'{hp_str} '
                f'for <b style="color:{opp_c}">{anchor_label}</b>'
                f'{move_str} vs {_opp_b(opp_name)} '
                f'(<span class="dd-gain">{scen_strs}</span>)'
                f'{anchor_span}</li>'
            )
    return lines




def render_notable_ivs_section(categories, data_obj, opp_iv_mode,
                                  notable_max_pct=0.05,
                                  notable_max_count=5,
                                  max_members_shown=5,
                                  recommendations_html=''):
    """Render the "Notable IVs" HTML section from a list of IVCategory.

    Surfaces composite (slayer ∩ tier) and matchup categories — the
    intersections that the SwagTips-style structured-IV-categories goal
    is about. Pure slayer and pure tier categories already have
    dedicated UI elsewhere on the page; this section is *additive*,
    not a replacement, for round one.

    Args:
        categories: full list from build_iv_categories(). Pure
            slayer/tier kinds are filtered out at render time so the
            section stays focused on intersections.
        data_obj: the JS-bound data object (for IV labels, sp ranks).
        opp_iv_mode: 'pvpoke' or 'rank1' (used for the prose).
        notable_max_pct: float — categories with member count <= this
            fraction of nIvs are tagged dd-notable. The UI checkbox
            defaults to "show only notable" using this class.
        notable_max_count: hard cap on the notable bucket regardless
            of pct (e.g. ≤ 5 members is always notable).
        max_members_shown: per-card cap on listed members before the
            "expand" toggle.

    Returns: HTML string. Empty string if no notable categories exist.
    """
    n_ivs = data_obj.get('nIvs', 0) or 1
    parent_categories = {c.name: c for c in categories
                         if c.kind in ('slayer', 'tier', 'structural')}
    target = [c for c in categories if c.kind in ('composite', 'matchup')]
    if not target:
        return ''

    # Per-card unique counter so the JS expand toggle can address each
    # card individually. Resets per call to _render_notable_ivs_section,
    # which is fine because the section is rendered once per page.
    card_uid = 0

    # Sort: composites first (the headline), then matchups, with smaller
    # categories first within each kind so the most distinctive cards
    # land at the top of the grid.
    kind_order = {'composite': 0, 'matchup': 1}
    target.sort(key=lambda c: (kind_order.get(c.kind, 99), len(c.members), c.name))

    n_notable = sum(1 for c in target
                    if len(c.members) <= notable_max_count
                    or len(c.members) <= notable_max_pct * n_ivs)

    parts = []
    parts.append(
        f'<details class="dd-collapsible" id="dd-notable-ivs">'
        f'<summary class="dd-h3" style="cursor:pointer">'
        f'Notable IVs &amp; Recommendations '
        f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
        f'({n_notable} notable of {len(target)} categories)</span>'
        f'</summary>\n')
    parts.append(
        '<p class="dd-small">Cross-category IVs and notable matchup '
        'wins. Composite cards (slayer&nbsp;∩&nbsp;tier) surface IVs '
        'that satisfy a slayer anchor <em>and</em> a stat-cutoff '
        'threshold tier — the rare intersections that trade some '
        'slayer optimum for a broader-meta floor (or vice versa). '
        'Matchup cards surface non-trivial '
        '(opponent,&nbsp;scenario)&nbsp;partitions for selective '
        'matchups. Pure slayer cards live in the Mirror Slayer '
        'Iteration block below; pure tier cards in the Threshold Tiers '
        'section above.</p>\n'
    )

    # Notability filter checkbox. Default ON: show only small,
    # distinctive categories. JS toggles a class on the section
    # container; each card carries dd-notable / dd-not-notable.
    parts.append("""<script>
function ddNotableToggle(cb) {
  var sec = document.getElementById('dd-notable-ivs-section');
  if (!sec) return;
  sec.classList.toggle('dd-notable-only', cb.checked);
}
function ddNotableExpand(cardId, btn, nHidden, nVisible) {
  // Per-card "Show all N" / "Collapse" toggle. Flips dd-iv-shown
  // on every dd-iv-hidden row inside this card so the overflow
  // members appear or disappear in place. Same pattern as the
  // slayer-card expand toggle.
  var card = document.getElementById(cardId);
  if (!card) return;
  var rows = card.querySelectorAll('.dd-iv-hidden');
  if (!rows.length) return;
  var nowShown = rows[0].classList.contains('dd-iv-shown');
  rows.forEach(function(r) { r.classList.toggle('dd-iv-shown', !nowShown); });
  btn.textContent = nowShown
    ? ('Show all ' + (nHidden + nVisible))
    : ('Collapse to top ' + nVisible);
}
</script>
""")
    parts.append(
        '<div class="dd-callout"><label>'
        '<input type="checkbox" id="dd-notable-only-cb" checked '
        'onchange="ddNotableToggle(this)"> '
        'Show only notable categories '
        f'(≤ {int(notable_max_pct * 100)}% of cohort or '
        f'≤ {notable_max_count} members). Uncheck to see every '
        'non-trivial intersection.</label></div>\n'
    )

    parts.append(
        '<div id="dd-notable-ivs-section" class="dd-notable-only">\n'
    )
    parts.append('<div class="dd-rec-grid">\n')

    for cat in target:
        n_members = len(cat.members)
        is_notable = (n_members <= notable_max_count
                      or n_members <= notable_max_pct * n_ivs)
        notable_cls = 'dd-notable' if is_notable else 'dd-not-notable'

        card_uid += 1
        card_id = f'dd-notable-card-{card_uid}'
        parts.append(f'<div class="dd-rec-card {notable_cls}" id="{card_id}">\n')
        parts.append(
            f'<h4>{cat.name} '
            f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
            f'({n_members} IV{"s" if n_members != 1 else ""})'
            f'</span></h4>\n'
        )
        # Description and provenance subtitle
        if cat.kind == 'composite':
            cutoffs = format_stat_cutoffs(cat.stat_cutoffs)
            sub = (f'{" + ".join(cat.source_categories)}'
                   + (f' · {cutoffs}' if cutoffs else ''))
            parts.append(f'<p class="dd-small dd-prose">{sub}</p>\n')
        elif cat.kind == 'matchup':
            sub = matchup_subtitle(cat)
            if sub:
                parts.append(f'<p class="dd-small dd-prose">{sub}</p>\n')

        # Member list — sort by total_wins desc when available, else
        # by IV index. Render every member; rows past max_members_shown
        # get the dd-iv-hidden class and the expand button toggles
        # dd-iv-shown on them (matching the slayer-card pattern).
        def _sort_key(idx):
            wins = cat.member_meta.get(idx, {}).get('total_wins', 0)
            return (-wins, idx)
        members_sorted = sorted(cat.members, key=_sort_key)

        # Cap total rendered members to avoid multi-MB HTML for large
        # matchup cards (e.g. 2200 IVs beating Lapras). Top members by
        # wins are the most informative; the rest add bytes but no signal.
        max_members_rendered = 30
        for row_i, m_idx in enumerate(members_sorted[:max_members_rendered]):
            triple = (data_obj['ivA'][m_idx],
                      data_obj['ivD'][m_idx],
                      data_obj['ivS'][m_idx])
            atk = data_obj['ivAtk'][m_idx]
            def_ = data_obj['ivDef'][m_idx]
            hp = data_obj['ivHp'][m_idx]
            sp_rank = data_obj['spRanks'][m_idx]
            label = f'{triple[0]}/{triple[1]}/{triple[2]}'
            row_cls = ' class="dd-iv-hidden"' if row_i >= max_members_shown else ''
            parts.append(
                f'<p{row_cls}><b>{label}</b> &mdash; '
                f'atk {atk:.2f}, def {def_:.2f}, hp {hp}, '
                f'SP&nbsp;#{sp_rank}</p>\n'
            )
            if cat.kind == 'composite':
                prose = composite_tradeoff_prose(
                    m_idx, cat, parent_categories, data_obj
                )
                if prose:
                    prose_cls = ' dd-iv-hidden' if row_i >= max_members_shown else ''
                    parts.append(
                        f'<p class="dd-prose{prose_cls}">{prose}</p>\n'
                    )
        if n_members > max_members_rendered:
            parts.append(
                f'<p class="dd-iv-hidden dd-small">'
                f'… {n_members - max_members_rendered} more not rendered '
                f'(top {max_members_rendered} shown)</p>\n'
            )

        if n_members > max_members_shown:
            n_hidden = n_members - max_members_shown
            parts.append(
                f'<button class="dd-iv-toggle" '
                f'onclick="ddNotableExpand(\'{card_id}\', this, '
                f'{n_hidden}, {max_members_shown})">'
                f'Show all {n_members}'
                f'</button>\n'
            )
        parts.append('</div>\n')  # rec-card

    parts.append('</div>\n')  # rec-grid
    parts.append('</div>\n')  # dd-notable-ivs-section

    # Recommendations sub-section is injected by the caller via
    # the recommendations_html parameter (rendered separately because
    # the data it needs lives in render_results_section's scope).
    if recommendations_html:
        parts.append(recommendations_html)

    parts.append('</details>\n')  # dd-collapsible
    return ''.join(parts)












def render_threshold_tier_cards(data_obj, anchor_flip_records,
                                  avg_ranks, flip_map,
                                  max_members_shown=10,
                                  max_members_rendered=50,
                                  override_tiers=None,
                                  score_arrays=None,
                                  moveset_idx=0,
                                  flips_detail=None,
                                  matchup_boundaries=None,
                                  anchor_passing_sink=None,
                                  has_bait_axis=False):
    """RyanSwag-style threshold tier cards.

    Each tier becomes a card whose headline is the tier's stat-target spec
    (``atk≥X, def≥Y, hp≥Z``) and whose body is the set of anchor-flip
    bullets that the tier's spec actually clears, plus a collapsed table
    of the tier's member IVs.

    Filter rule: an anchor with ``target_stat='atk'`` belongs to a tier iff
    the tier specifies an atk cutoff and that cutoff is ``>=`` the anchor's
    threshold value (i.e. the tier clears the anchor). Symmetric for def.
    Overlap across tiers is intentional.

    Args:
        override_tiers: optional list of tier dicts to use instead of
            ``data_obj['tiers']``. Used by the auto-derive path when the
            TOML doesn't supply tiers.
    """
    tiers = override_tiers if override_tiers is not None else data_obj.get('tiers', [])
    if not tiers:
        return ''
    n_ivs = data_obj.get('nIvs', 0)
    iv_tiers_precomputed = data_obj.get('ivTiers') if override_tiers is None else None
    scenarios = [tuple(s) for s in data_obj.get('scenarios', [])]
    opponents = data_obj.get('opponents', [])

    parts = []
    parts.append('<h3 class="dd-h3" id="dd-threshold-tiers">Threshold Tiers</h3>\n')
    parts.append(
        '<p class="dd-small">Stat-target headlines from <code>thresholds/'
        '*.toml</code>, each grouped with the named anchors its spec '
        'clears and the IV spreads that meet it. Within each tier card, '
        'bullets are grouped by opponent and sorted by the required stat '
        '(Def or Atk) ascending — read top-to-bottom in the order a '
        'player would clear them as their stat grows. Tiers may share '
        'bullets — a stricter tier above also clears everything a looser '
        'tier below clears, and the overlap is intentional. The flat '
        'list of every anchor (regardless of tier) lives in '
        '<em>Anchor-Driven Matchup Flips</em> below.</p>\n'
    )
    parts.append('<div class="dd-rec-grid">\n')

    for ti, t in enumerate(tiers):
        atk_cut = t.get('attack', 0) or 0
        def_cut = t.get('defense', 0) or 0
        hp_cut = t.get('stamina', 0) or 0
        cutoff_bits = []
        if atk_cut > 0:
            cutoff_bits.append(f'atk≥{atk_cut:.2f}')
        if def_cut > 0:
            cutoff_bits.append(f'def≥{def_cut:.2f}')
        if hp_cut > 0:
            cutoff_bits.append(f'hp≥{hp_cut:g}')
        cutoffs_str = ', '.join(cutoff_bits) if cutoff_bits else 'no cutoff'

        # Filter: which anchor records does this tier clear?
        tier_records = []
        for rec in anchor_flip_records:
            a = rec['anchor']
            tv = getattr(a, 'threshold_value', None)
            if tv is None:
                continue
            stat = a.target_stat
            if stat == 'atk' and atk_cut > 0 and atk_cut >= tv:
                tier_records.append(rec)
            elif stat == 'def' and def_cut > 0 and def_cut >= tv:
                tier_records.append(rec)

        # Tier membership: use precomputed ivTiers when available (TOML path),
        # else compute on the fly from stat cutoffs (auto-derive path).
        if iv_tiers_precomputed is not None:
            tier_ivs = [iv for iv in range(n_ivs)
                        if iv_tiers_precomputed[iv] == ti]
        else:
            tier_ivs = []
            for iv in range(n_ivs):
                meets = True
                if atk_cut > 0 and data_obj['ivAtk'][iv] < atk_cut:
                    meets = False
                if def_cut > 0 and data_obj['ivDef'][iv] < def_cut:
                    meets = False
                if hp_cut > 0 and data_obj['ivHp'][iv] < hp_cut:
                    meets = False
                if meets:
                    tier_ivs.append(iv)
        n_members = len(tier_ivs)

        color = t.get('color', '#888')
        # Slug for the "N of yours qualify" placeholder. Must match the
        # JS computation in deep_dive_engine.js updateTierCardCounts.
        import re as _re
        _tier_slug = _re.sub(r'^-|-$', '',
                             _re.sub(r'[^a-z0-9]+', '-', t['name'].lower()))
        parts.append('<div class="dd-rec-card">\n')
        parts.append(
            f'<h4>'
            f'<span class="dd-badge" style="background:{color};color:#000">'
            f'{t["name"]}</span> '
            f'<span class="dd-small" style="font-weight:400;color:#b0b8c4">'
            f'· {cutoffs_str}</span> '
            f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
            f'({n_members} IV{"s" if n_members != 1 else ""})'
            f'</span> '
            f'<span id="tier-card-yours-{_tier_slug}" '
            f'class="dd-small" '
            f'style="font-weight:400;color:#ff40ff;display:none"></span>'
            f'</h4>\n'
        )
        # --- Auto-generated prose summary for the card ---
        if tier_records:
            # Collect unique opponents whose anchors this tier clears
            tier_opps = sorted({r['opponent'] for r in tier_records})
            # Count only — no sink here; the actual rendered bullets
            # below populate the sink.
            n_bullets = len(render_anchor_flip_bullets(
                tier_records, has_bait_axis=has_bait_axis))
            scen_set = set()
            for r in tier_records:
                for s in r['scenarios']:
                    scen_set.add(tuple(s))
            prose_parts = []
            if tier_opps:
                opp_str = ', '.join(tier_opps[:4])
                if len(tier_opps) > 4:
                    opp_str += f', +{len(tier_opps) - 4} more'
                prose_parts.append(
                    f'Clears {n_bullets} anchor'
                    f'{"s" if n_bullets != 1 else ""} across '
                    f'{len(scen_set)} shield scenario'
                    f'{"s" if len(scen_set) != 1 else ""}, '
                    f'covering {opp_str}.'
                )
            if t.get('desc'):
                prose_parts.append(t['desc'])
            if prose_parts:
                parts.append(
                    f'<p class="dd-prose">{" ".join(prose_parts)}</p>\n'
                )
        elif t.get('desc'):
            parts.append(f'<p class="dd-prose">{t["desc"]}</p>\n')

        # --- Anchor-flip bullets (collapsed past 5) ---
        max_bullets_visible = 5
        if tier_records:
            bullets = render_anchor_flip_bullets(
                tier_records, anchor_passing_sink=anchor_passing_sink,
                has_bait_axis=has_bait_axis)
            if bullets:
                tier_card_uid = f'dd-tier-{ti}'
                n_vis = min(len(bullets), max_bullets_visible)
                parts.append('<ul class="dd-threshold-list">\n')
                parts.append('\n'.join(bullets[:n_vis]))
                if len(bullets) > max_bullets_visible:
                    for b in bullets[max_bullets_visible:]:
                        parts.append(
                            f'\n<li class="dd-iv-hidden" '
                            f'data-tier-card="{tier_card_uid}">{b[4:]}'
                        )  # strip leading <li> since we're adding class
                    parts.append('\n</ul>\n')
                    n_hidden = len(bullets) - max_bullets_visible
                    parts.append(
                        f'<button class="dd-slayer-toggle" '
                        f'onclick="(function(btn){{'
                        f'var items=document.querySelectorAll('
                        f'\'[data-tier-card=\\&quot;{tier_card_uid}\\&quot;]\');'
                        f'var shown=items.length>0&&items[0].classList.contains(\'dd-iv-shown\');'
                        f'items.forEach(function(r){{r.classList.toggle(\'dd-iv-shown\',!shown);}});'
                        f'btn.textContent=shown'
                        f'?\'Show all {len(bullets)} anchors\''
                        f':\'Collapse to top {n_vis}\';'
                        f'}})(this)">Show all {len(bullets)} anchors</button>\n'
                    )
                else:
                    parts.append('\n</ul>\n')
        elif cutoff_bits:
            parts.append(
                '<p class="dd-small">No named anchors fall within '
                "this tier's spec.</p>\n"
            )

        # --- Matchup-flipping boundaries covered by this tier ---
        if matchup_boundaries:
            tier_mbs = []
            for mb in matchup_boundaries:
                mb_thresh = mb['threshold']
                mb_stat = mb.get('stat', 'def')
                mb_hp = mb.get('hp_threshold')
                # Does this tier's spec cover this boundary?
                if mb_stat == 'def':
                    if def_cut <= 0 or def_cut < mb_thresh:
                        continue  # tier has no def cutoff or too low
                else:  # atk
                    if atk_cut <= 0 or atk_cut < mb_thresh:
                        continue  # tier has no atk cutoff or too low
                if mb_hp is not None and hp_cut > 0 and hp_cut < mb_hp:
                    continue  # tier's hp isn't high enough
                tier_mbs.append(mb)
            # Filter out opponents already shown by anchor bullets
            anchor_opps = {r['opponent'] for r in tier_records}
            new_mbs = [mb for mb in tier_mbs
                       if mb['opponent'] not in anchor_opps]
            if new_mbs:
                mb_bullets = render_matchup_boundary_bullets(
                    new_mbs, has_bait_axis=has_bait_axis,
                    toggle_id=f'mb-tier-{ti}', top_n=10)
                if mb_bullets:
                    parts.append(
                        '<p class="dd-small" style="margin-top:6px">'
                        '<b style="color:#3fb950">Matchup-flipping '
                        'boundaries</b> (full-battle stat targets, not '
                        'just damage tiers):</p>\n'
                    )
                    parts.append('<ul class="dd-threshold-list">\n')
                    parts.append('\n'.join(mb_bullets))
                    parts.append('\n</ul>\n')

        # --- Tier-cutoff probe: matchup flips at the tier's own spec ---
        # Catches flips that fall between Level 3 sub-anchor thresholds
        # (e.g. acidicArisen's 143.03 def vs Azu lives between damage
        # tiers at 142.34 and 144.41).
        if score_arrays and (atk_cut > 0 or def_cut > 0):
            probe_results = analysis.probe_tier_cutoff_flips(
                data_obj, score_arrays, moveset_idx,
                atk_cut, def_cut, hp_cut,
                scenarios, opponents,
            )
            if probe_results:
                # Group by opponent, union scenarios
                _probe_opps: dict = {}
                for pr in probe_results:
                    _probe_opps.setdefault(pr['opponent'], set()).add(
                        tuple(pr['scenario']))
                # Filter out opponents already covered by anchor bullets
                _anchor_opps = {r['opponent'] for r in tier_records}
                _new_opps = {o for o in _probe_opps if o not in _anchor_opps}
                if _new_opps:
                    parts.append(
                        '<p class="dd-small" style="margin-top:6px">'
                        '<b style="color:#d29922">Additional matchup flips '
                        'at this tier\'s spec</b> (not explained by a single '
                        'anchor — may involve HP or multi-stat interactions):'
                        '</p>\n'
                    )
                    parts.append('<ul class="dd-threshold-list">\n')
                    for opp in sorted(_new_opps):
                        scens = sorted(_probe_opps[opp])
                        scen_str = ', '.join(f'{s[0]}v{s[1]}' for s in scens)
                        parts.append(
                            f'<li>vs {_opp_b(opp)} '
                            f'(<span class="dd-gain">{scen_str}</span>)'
                            f'</li>\n'
                        )
                    parts.append('</ul>\n')

        # --- Member IVs (collapsed, with expand toggle) ---
        if tier_ivs:
            tier_ivs.sort(key=lambda iv: avg_ranks[iv])
            parts.append(
                f'<details class="dd-flip-detail">'
                f'<summary>Member IVs ({n_members})</summary>\n'
            )
            parts.append('<table class="dd-table dd-narrow">\n')
            parts.append(
                '<tr><th>IV</th><th>Atk</th><th>Def</th><th>HP</th>'
                '<th>Avg rank</th>'
                '<th title="Matchup wins gained minus lost vs the '
                'PvPoke default reference IV. Hover each cell for '
                'the gain/loss breakdown.">Net flips</th></tr>\n'
            )
            n_to_render = min(len(tier_ivs), max_members_rendered)
            n_truncated = len(tier_ivs) - n_to_render
            for row_i, iv in enumerate(tier_ivs[:n_to_render]):
                triple = (data_obj['ivA'][iv], data_obj['ivD'][iv],
                          data_obj['ivS'][iv])
                _g, _l, net = flip_map.get(iv, (0, 0, 0))
                nc = 'dd-gain' if net > 0 else ('dd-loss' if net < 0 else '')
                # Build hover text with matchup names when available
                fd = (flips_detail or {}).get(iv)
                if fd:
                    hover_lines = []
                    if fd.get('gains'):
                        gain_names = [f"{e['opponent']} {e['scenario']}"
                                      for e in fd['gains'][:6]]
                        hover_lines.append(f"Gained: {', '.join(gain_names)}")
                        if len(fd['gains']) > 6:
                            hover_lines[-1] += f' +{len(fd["gains"])-6} more'
                    if fd.get('losses'):
                        loss_names = [f"{e['opponent']} {e['scenario']}"
                                      for e in fd['losses'][:6]]
                        hover_lines.append(f"Lost: {', '.join(loss_names)}")
                        if len(fd['losses']) > 6:
                            hover_lines[-1] += f' +{len(fd["losses"])-6} more'
                    flip_hover = '\n'.join(hover_lines) if hover_lines else f'net {net:+d}'
                else:
                    flip_hover = (f'+{_g} gained, -{_l} lost vs reference IV '
                                  f'(net {net:+d})')
                row_cls = (' class="dd-slayer-hidden"'
                           if row_i >= max_members_shown else '')
                parts.append(
                    f'<tr{row_cls}>'
                    f'<td>{triple[0]}/{triple[1]}/{triple[2]}</td>'
                    f'<td>{data_obj["ivAtk"][iv]:.2f}</td>'
                    f'<td>{data_obj["ivDef"][iv]:.2f}</td>'
                    f'<td>{data_obj["ivHp"][iv]}</td>'
                    f'<td>#{avg_ranks[iv]}</td>'
                    f'<td class="{nc}" title="{flip_hover}">'
                    f'{net:+d}</td></tr>\n'
                )
            if n_truncated > 0:
                parts.append(
                    f'<tr class="dd-slayer-hidden"><td colspan="6" '
                    f'class="dd-small">… {n_truncated} more not rendered '
                    f'(top {n_to_render} by avg rank shown)</td></tr>\n'
                )
            parts.append('</table>\n')
            n_expandable = min(n_to_render, n_members)
            if n_expandable > max_members_shown:
                parts.append(
                    f'<button class="dd-slayer-toggle" '
                    f'onclick="(function(btn){{'
                    f'var t=btn.previousElementSibling;'
                    f'var rows=t.querySelectorAll(\'tr.dd-slayer-hidden\');'
                    f'var shown=rows.length>0&&rows[0].classList.contains(\'dd-slayer-shown\');'
                    f'rows.forEach(function(r){{r.classList.toggle(\'dd-slayer-shown\',!shown);}});'
                    f'btn.textContent=shown'
                    f'?\'Show top {n_expandable} IVs\''
                    f':\'Collapse to top {max_members_shown}\';'
                    f'}})(this)">Show top {n_expandable} IVs</button>\n'
                )
            parts.append('</details>\n')
        else:
            # Mirror the existing tier-summary "0 spreads" callout: tell the
            # reader whether nothing reaches the spec or whether everything
            # also clears a stricter tier above (the tier-priority artifact).
            all_meeting = 0
            for iv in range(n_ivs):
                meets = True
                if atk_cut > 0 and data_obj['ivAtk'][iv] < atk_cut:
                    meets = False
                if def_cut > 0 and data_obj['ivDef'][iv] < def_cut:
                    meets = False
                if hp_cut > 0 and data_obj['ivHp'][iv] < hp_cut:
                    meets = False
                if meets:
                    all_meeting += 1
            if all_meeting > 0:
                parts.append(
                    f'<p class="dd-small">{all_meeting} IV spread'
                    f'{"s" if all_meeting != 1 else ""} meet this spec, '
                    f'but all also qualify for a stricter tier above.</p>\n'
                )
            else:
                parts.append(
                    '<p class="dd-small">0 IV spreads can reach this spec '
                    'at this CP cap.</p>\n'
                )

        parts.append('</div>\n')  # rec-card
    parts.append('</div>\n')  # rec-grid
    return ''.join(parts)


def generate_threshold_descriptions(flips, data, avg_scores, ranked, opp_iv_mode,
                                    has_bait_axis=False):
    """Generate HSH/RyanSwag-style threshold descriptions from flip data.

    Returns list of HTML paragraphs describing key stat thresholds with
    matchup justification.
    """
    # Collect all unique (opponent, scenario) flips across IVs and find
    # which stat change drives the flip
    opp_label = 'PvPoke default' if parse_mode(opp_iv_mode)[0] == 'pvpoke' else 'rank 1'

    # Group flips by opponent+scenario to find common themes
    opp_scene_gains = {}  # (opp, scene) -> list of (iv, delta)
    opp_scene_losses = {}
    opp_scene_bait = {}   # (opp, scene) -> union of bait_modes across entries
    for iv, fd in flips.items():
        for e in fd['gains']:
            key = (e['opponent'], e['scenario'])
            opp_scene_gains.setdefault(key, []).append((iv, e['iv_score'] - e['ref_score']))
            opp_scene_bait.setdefault(key, set()).update(e.get('bait_modes', set()))
        for e in fd['losses']:
            key = (e['opponent'], e['scenario'])
            opp_scene_losses.setdefault(key, []).append((iv, e['ref_score'] - e['iv_score']))
            opp_scene_bait.setdefault(key, set()).update(e.get('bait_modes', set()))

    lines = []

    # Attack thresholds: flips where higher-atk IVs gain matchups
    # Defense/HP thresholds: flips where higher-bulk IVs gain matchups
    # We identify these by checking the stat profile of IVs that gain vs lose

    # Most common gain matchups (by how many IVs gain them)
    gain_counts = sorted(opp_scene_gains.items(), key=lambda x: len(x[1]), reverse=True)
    for (opp, scene), iv_deltas in gain_counts[:6]:
        n = len(iv_deltas)
        avg_delta = sum(d for _, d in iv_deltas) / n
        # What stat distinguishes IVs that get this gain?
        gain_ivs = [iv for iv, _ in iv_deltas]
        gain_atk = sum(data['ivAtk'][iv] for iv in gain_ivs) / len(gain_ivs)
        gain_def = sum(data['ivDef'][iv] for iv in gain_ivs) / len(gain_ivs)
        gain_hp = sum(data['ivHp'][iv] for iv in gain_ivs) / len(gain_ivs)
        pop_atk = sum(data['ivAtk'][iv] for iv in ranked[:50]) / 50
        pop_def = sum(data['ivDef'][iv] for iv in ranked[:50]) / 50
        pop_hp = sum(data['ivHp'][iv] for iv in ranked[:50]) / 50

        # Which stat differs most?
        diffs = [('Atk', gain_atk - pop_atk, gain_atk),
                 ('Def', gain_def - pop_def, gain_def),
                 ('HP', gain_hp - pop_hp, gain_hp)]
        dominant = max(diffs, key=lambda x: abs(x[1]))

        if abs(dominant[1]) < 0.5 and dominant[0] != 'HP':
            stat_note = ''
        elif dominant[1] > 0:
            stat_note = f' (favors higher {dominant[0]}, avg {dominant[2]:.1f})'
        else:
            stat_note = f' (favors lower {dominant[0]}, avg {dominant[2]:.1f})'

        bait_badge = ''
        if has_bait_axis:
            bm = opp_scene_bait.get((opp, scene), set())
            if bm == {'bait'}:
                bait_badge = ' <span class="dd-badge" style="background:#1a3a6e;color:#58a6ff">[bait only]</span>'
            elif bm == {'nobait'}:
                bait_badge = ' <span class="dd-badge" style="background:#1a3a6e;color:#58a6ff">[no-bait only]</span>'

        opp_c = _opp_color(opp)
        lines.append(
            f'<li><b style="color:{opp_c}">{opp} {scene}</b> &mdash; '
            f'{n} of top IVs gain this matchup vs {opp_label} opponent '
            f'(avg +{avg_delta:.0f} score){stat_note}{bait_badge}</li>'
        )

    # Most common loss matchups
    loss_counts = sorted(opp_scene_losses.items(), key=lambda x: len(x[1]), reverse=True)
    if loss_counts:
        lines.append('<li class="dd-loss-item"><b>Common losses:</b> ')
        loss_parts = []
        for (opp, scene), iv_deltas in loss_counts[:4]:
            n = len(iv_deltas)
            loss_parts.append(f'{_opp_b(opp)} {scene} ({n} IVs)')
        lines.append(', '.join(loss_parts) + '</li>')

    return lines


def scenario_ranks(scores_flat, nIvs, nS, nO):
    """Compute per-scenario ranks and overall average ranks/scores."""
    scene_ranks = []
    for si in range(nS):
        ss = [sum(scores_flat[iv * nS * nO + si * nO + oi] for oi in range(nO)) for iv in range(nIvs)]
        order = sorted(range(nIvs), key=lambda i: ss[i], reverse=True)
        ranks = [0] * nIvs
        for r, idx in enumerate(order):
            ranks[idx] = r + 1
        scene_ranks.append(ranks)
    avg_scores = [sum(scores_flat[iv * nS * nO + si * nO + oi] for si in range(nS) for oi in range(nO)) / (nS * nO) for iv in range(nIvs)]
    avg_order = sorted(range(nIvs), key=lambda i: avg_scores[i], reverse=True)
    avg_ranks = [0] * nIvs
    for r, idx in enumerate(avg_order):
        avg_ranks[idx] = r + 1
    return scene_ranks, avg_ranks, avg_scores, avg_order




















def detect_banding(stat_values, scores, stat_name):
    """Detect banding: group IVs by discrete stat value, compute F-ratio and eta^2."""
    groups = {}
    for sv, sc in zip(stat_values, scores):
        key = int(sv) if stat_name == 'hp' else round(sv, 2)
        groups.setdefault(key, []).append(sc)
    if len(groups) < 3:
        return None
    grand_mean = sum(scores) / len(scores)
    n_total = len(scores)
    gmeans = {k: sum(v)/len(v) for k, v in groups.items()}
    ssb = sum(len(v) * (gmeans[k] - grand_mean)**2 for k, v in groups.items())
    ssw = sum(sum((x - gmeans[k])**2 for x in v) for k, v in groups.items())
    df_b, df_w = len(groups) - 1, n_total - len(groups)
    f_ratio = (ssb / df_b) / (ssw / df_w) if df_w and ssw else float('inf')
    eta_sq = ssb / (ssb + ssw) if (ssb + ssw) else 0
    sorted_keys = sorted(gmeans)
    jumps = []
    for i in range(len(sorted_keys) - 1):
        k1, k2 = sorted_keys[i], sorted_keys[i + 1]
        jumps.append((k1, k2, gmeans[k2] - gmeans[k1], len(groups[k1]), len(groups[k2])))
    jumps.sort(key=lambda x: abs(x[2]), reverse=True)
    return {'stat_name': stat_name, 'n_groups': len(groups), 'f_ratio': f_ratio,
            'eta_squared': eta_sq, 'correlation': pearson_r(stat_values, scores),
            'top_jumps': jumps[:5], 'group_means': gmeans}


def detect_clusters(scores, data):
    """Gap analysis: find natural breakpoints in sorted score distribution."""
    si = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ss = [scores[i] for i in si]
    gaps = [(i, ss[i-1] - ss[i]) for i in range(1, len(ss))]
    gap_vals = sorted(g[1] for g in gaps)
    med = gap_vals[len(gap_vals) // 2]
    sig = [(i, g) for i, g in gaps if g > 3 * med and i <= len(scores) // 4]
    sig.sort(key=lambda x: x[1], reverse=True)
    boundaries = sorted(set([0] + [g[0] for g in sig[:5]] + [len(scores)]))
    clusters = []
    for j in range(len(boundaries) - 1):
        s, e = boundaries[j], boundaries[j + 1]
        idx = si[s:e]
        scs = ss[s:e]
        if not scs:
            continue
        clusters.append({
            'rank_range': (s + 1, e), 'size': e - s,
            'score_range': (min(scs), max(scs)),
            'atk': (min(data['ivAtk'][i] for i in idx), sum(data['ivAtk'][i] for i in idx)/len(idx), max(data['ivAtk'][i] for i in idx)),
            'def': (min(data['ivDef'][i] for i in idx), sum(data['ivDef'][i] for i in idx)/len(idx), max(data['ivDef'][i] for i in idx)),
            'hp': (min(data['ivHp'][i] for i in idx), sum(data['ivHp'][i] for i in idx)/len(idx), max(data['ivHp'][i] for i in idx)),
            'indices': idx,
        })
    return clusters, sig[:5]






def pearson_r(xs, ys):
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx)**2 for x in xs))
    dy = math.sqrt(sum((y - my)**2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


# ---------------------------------------------------------------------------
# Mirror slayer iteration HTML
# ---------------------------------------------------------------------------

def render_mirror_slayer_html(ctx_or_slayer=None, *, slayer_iter_result=None,
                              data_obj=None, moveset_idx=0):
    """Render the Mirror Slayer Iteration section of the Results pane.

    Accepts either an ``AnalysisContext`` as the first positional arg or
    explicit keyword args (``slayer_iter_result``, ``data_obj``,
    ``moveset_idx``).  Returns an HTML string (empty if no slayer
    iteration ran).
    """
    if ctx_or_slayer is not None and isinstance(ctx_or_slayer, AnalysisContext):
        slayer_iter_result = ctx_or_slayer.slayer_iter_result
        data_obj = ctx_or_slayer.data_obj
        moveset_idx = ctx_or_slayer.moveset_idx
    if not slayer_iter_result or not slayer_iter_result.get('final'):
        return ''
    parts = []

    metric_label = slayer_iter_result.get('metric', 'all')
    max_rounds_arg = slayer_iter_result.get('max_rounds_arg', 4)
    metric_explain = {
        'all': 'all 9 shield scenarios count toward win totals',
        'even': 'only even shields (0v0/1v1/2v2) count toward win totals',
        'even-strict': 'only IVs that win ALL three even shields against an opponent get credit',
    }.get(metric_label, '')
    rounds_run = slayer_iter_result.get('rounds_run', 0)
    converged = slayer_iter_result.get('converged', False)
    final_pool = len(slayer_iter_result.get('final', []))
    parts.append(
        f'<details class="dd-collapsible">'
        f'<summary class="dd-h3" style="cursor:pointer">'
        f'Mirror Slayer Iteration '
        f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
        f'({final_pool} survivors, {rounds_run} round{"s" if rounds_run != 1 else ""}, '
        f'{"converged" if converged else "max rounds reached"})</span>'
        f'</summary>\n'
    )

    # Iteration details -- collapsed by default
    parts.append(
        '<details class="dd-flip-detail">'
        '<summary>Iteration details</summary>\n'
    )
    parts.append(f'<p>Nash-style iterative discovery of IVs that beat the '
                 f'{data_obj.get("species", "mirror")} mirror match. '
                 f'Each round tests focal IVs against the previous round\'s top winners. '
                 f'Survivors are classified into RyanSwag\'s three patterns.</p>\n')
    parts.append(f'<p class="dd-small"><b>Metric:</b> <code>{metric_label}</code> '
                 f'({metric_explain}) | <b>Max rounds:</b> {max_rounds_arg}</p>\n')
    parts.append(f'<p class="dd-small">'
                 f'{slayer_iter_result.get("cache_stats", "")}</p>\n')
    history = slayer_iter_result.get('history', [])
    if history:
        parts.append('<table class="dd-table dd-narrow">\n')
        parts.append('<tr><th>Round</th><th>Survivors</th><th>Max Wins</th><th>Top Avg Score</th></tr>\n')
        for ri, top in enumerate(history):
            if not top:
                continue
            parts.append(f'<tr><td>{ri}</td><td>{len(top)}</td>'
                         f'<td>{top[0]["total_wins"]}</td>'
                         f'<td>{top[0]["avg_score"]:.1f}</td></tr>\n')
        parts.append('</table>\n')
    parts.append('</details>\n')

    # Categorized survivors
    categories = slayer_iter_result.get('categories', {})
    resolved_anchors = slayer_iter_result.get('resolved_anchors', []) or []

    # Summarize resolved anchors (for the intro paragraph and
    # Level 3 sub-anchor distribution report).
    anchor_parents: dict[str, list] = {}
    for a in resolved_anchors:
        anchor_parents.setdefault(a.parent, []).append(a)

    CATEGORY_DESCRIPTIONS = {
        'Atk Slayer': 'IVs that clear at least one named damage '
                      'breakpoint against a notable opponent. Membership '
                      'is binary per breakpoint: an IV is in this '
                      'category iff its effective attack reaches the '
                      'minimum needed to deal one extra damage with some '
                      'move against some named opponent &mdash; not just '
                      '&ldquo;has higher attack than other survivors.&rdquo; '
                      'Each row&rsquo;s Tags column lists the specific '
                      'breakpoint(s) cleared (hover for the move&nbsp;+&nbsp;'
                      'tier detail). <strong>Hidden if no survivor '
                      'clears any named breakpoint</strong> &mdash; an '
                      'empty Atk Slayer box means no anchors fired '
                      'against the current opponent set.',
        'Bulk Slayer': 'IVs that either (a) have HP and defense both at '
                       'or above the survivor-pool median (structural '
                       'high-bulk pool, always shown) <strong>or</strong> '
                       '(b) clear at least one named <em>bulkpoint</em> '
                       'anchor against a notable opponent &mdash; '
                       'reaching a defense tier at which one of the '
                       'opponent&rsquo;s threat moves deals strictly '
                       'less damage to the focal. Each row&rsquo;s Tags '
                       'column shows which bulkpoint(s) the IV clears '
                       '(badges with the &ldquo;b&rdquo; suffix or '
                       '&ldquo;&uarr;&rdquo; reference markers); hover '
                       'for the move&nbsp;+&nbsp;damage&nbsp;tier '
                       'detail. The structural pool is the default '
                       'fallback when no bulkpoint anchors are '
                       'configured for the species.',
        'CMP Slayer': 'IVs whose raw attack beats at least one named '
                      'CMP anchor (e.g., the max attack of a reference '
                      'cohort). Wins Charge Move Priority against the '
                      'cohort when both fire a charged move on the same '
                      'turn. <strong>Hidden if no survivor clears any '
                      'CMP anchor</strong>.',
    }

    if categories:
        # Build a map of IV -> set of non-empty categories it appears in
        iv_categories = {}
        for cat_name, cat_ivs in categories.items():
            if not cat_ivs:
                continue
            for r in cat_ivs:
                iv_categories.setdefault(r['iv'], set()).add(cat_name)

        if resolved_anchors:
            n_parents = len(anchor_parents)
            n_subs = len(resolved_anchors)
            parts.append(
                f'<p class="dd-small">Each survivor is tagged with the '
                f'set of named anchors it passes. {n_parents} parent '
                f'anchor(s) resolved to {n_subs} concrete threshold '
                f'check(s) — Level&nbsp;3 discover-mode anchors expand '
                f'into a family of sub-anchors (one per discovered '
                f'(move,&nbsp;tier) breakpoint). See the Tags column in '
                f'each category for per-IV detail. IVs that fit '
                f'<em>multiple</em> categories are marked with extra '
                f'cross-category badges.</p>\n'
            )
        else:
            parts.append(
                '<p class="dd-small">No named anchors are configured '
                'for this species/league (or none resolved against the '
                'survivor cohort). Atk Slayer and CMP Slayer will be '
                'empty; Bulk Slayer remains as a structural '
                'HP+def-above-median view. Add anchors to the species '
                '<code>thresholds/*.toml</code> file to enable '
                'breakpoint-based categorization.</p>\n'
            )

        # JS for the filter panel -- defined once, used by all cards.
        parts.append("""<script>
function ddSlayerApplyFilter(cardId) {
  var table = document.getElementById(cardId + '-table');
  if (!table) return;
  var checked = new Set();
  document.querySelectorAll('.dd-anchor-cb[data-card="' + cardId + '"]:checked').forEach(function(cb) {
    checked.add(cb.getAttribute('data-anchor-idx'));
  });
  var showAllCb = document.querySelector('.dd-show-all-mons[data-card="' + cardId + '"]');
  var showAll = showAllCb ? showAllCb.checked : false;
  var visible = 0, total = 0;
  table.querySelectorAll('tr[data-anchors]').forEach(function(row) {
    total++;
    var passes;
    if (showAll) {
      passes = true;
    } else {
      var raw = row.getAttribute('data-anchors') || '';
      var rowAnchors = raw.split(' ').filter(Boolean);
      if (rowAnchors.length === 0) {
        passes = false;
      } else {
        passes = rowAnchors.some(function(a) { return checked.has(a); });
      }
    }
    row.classList.toggle('dd-filter-hidden', !passes);
    if (passes) visible++;
  });
  document.querySelectorAll('.dd-anchor-master[data-card="' + cardId + '"]').forEach(function(master) {
    var grp = master.getAttribute('data-parent-grp');
    var children = document.querySelectorAll('.dd-anchor-cb[data-card="' + cardId + '"][data-parent-grp="' + grp + '"]');
    var n = 0, t = 0;
    children.forEach(function(c) { t++; if (c.checked) n++; });
    master.checked = (n === t);
    master.indeterminate = (n > 0 && n < t);
  });
  var counter = document.getElementById(cardId + '-visible-count');
  if (counter) counter.textContent = visible + ' / ' + total;
}
function ddSlayerToggleMaster(cb) {
  var card = cb.getAttribute('data-card');
  var grp = cb.getAttribute('data-parent-grp');
  var checked = cb.checked;
  document.querySelectorAll('.dd-anchor-cb[data-card="' + card + '"][data-parent-grp="' + grp + '"]').forEach(function(c) { c.checked = checked; });
  ddSlayerApplyFilter(card);
}
function ddSlayerResetFilter(cardId, defaultShowAll) {
  document.querySelectorAll('.dd-anchor-cb[data-card="' + cardId + '"]').forEach(function(c) { c.checked = true; });
  var sa = document.querySelector('.dd-show-all-mons[data-card="' + cardId + '"]');
  if (sa) sa.checked = defaultShowAll;
  ddSlayerApplyFilter(cardId);
}
function ddSlayerToggleFilterPanel(cardId) {
  var p = document.getElementById(cardId + '-filter');
  if (!p) return;
  var hidden = (p.style.display === 'none' || p.style.display === '');
  p.style.display = hidden ? 'block' : 'none';
}
function ddToggleTagsCompact(btn) {
  // Toggle the dd-tags-compact class on every inner tag wrapper across all
  // slayer cards. The wrapper is a <div> nested inside the <td> because
  // <td> uses display:table-cell which ignores max-height. Default state
  // is "compact" (capped at ~2 lines with a fade gradient at the bottom).
  // Click expands to full height so the badge wall is fully visible.
  // Mixed prior state (some cells individually toggled) is collapsed onto
  // a single state based on the first cell's current class.
  var inners = document.querySelectorAll('.dd-anchor-tags-inner');
  if (!inners.length) return;
  var nowExpanded = inners[0].classList.contains('dd-tags-compact');
  inners.forEach(function(c) { c.classList.toggle('dd-tags-compact', !nowExpanded); });
  btn.textContent = nowExpanded ? 'Compact tags' : 'Expand all tags';
}
function ddToggleTagsCompactCell(event) {
  // Per-cell click toggle. Flips the dd-tags-compact class on just the
  // clicked inner wrapper. Ignores clicks that originated inside an
  // anchor badge so badge hover tooltips keep working without
  // accidentally collapsing or expanding the cell. The bulk button
  // still works on top of any per-cell state -- it forces every cell to
  // a single state based on the first cell.
  if (event.target.closest('.dd-anchor-tag')) return;
  event.currentTarget.classList.toggle('dd-tags-compact');
}
</script>
""")

        parts.append(
            '<button class="dd-tags-toggle" '
            'onclick="ddToggleTagsCompact(this)">Expand all tags</button>\n'
        )
        parts.append('<div class="dd-rec-grid">\n')
        CAT_ABBREV = {'Atk Slayer': 'A', 'Bulk Slayer': 'B', 'CMP Slayer': 'C'}
        CAT_COLORS = {'Atk Slayer': '#f85149', 'Bulk Slayer': '#3fb950',
                      'CMP Slayer': '#d29922'}
        # Unique ID per card to scope filter JS -- moveset index + category index.
        _table_uid = 0
        _ms_prefix = f"ms{moveset_idx}"
        for cat_name, cat_ivs in categories.items():
            if not cat_ivs:
                continue  # hide empty categories (Atk/CMP when no anchors fired)
            desc = CATEGORY_DESCRIPTIONS.get(cat_name, '')
            n_total = len(cat_ivs)
            n_visible = min(n_total, 10)  # top N visible by default
            # Top-quartile highlighting: first ceil(n_total / 4) rows
            n_quartile = max(1, (n_total + 3) // 4)

            _table_uid += 1
            card_id = f"{_ms_prefix}-slayer-{_table_uid}"

            # Determine which anchor kinds apply to this category card.
            # Bulk Slayer surfaces all kinds (bulkpoint anchors are its
            # native kind; bp/cmp tags also show as cross-info).
            want_kinds = {
                'Atk Slayer': {'damage_breakpoint'},
                'CMP Slayer': {'cmp'},
                'Bulk Slayer': {'damage_breakpoint', 'cmp', 'bulkpoint'},
            }.get(cat_name, {'damage_breakpoint', 'cmp', 'bulkpoint'})

            # Build the per-card sub-anchor index. anchor_parents was computed
            # earlier from resolved_anchors. We filter to only sub-anchors
            # whose kind matches this category, and assign each a stable
            # integer index for the data-anchors row attribute and the
            # filter checkboxes. Order: parent name asc, then threshold asc.
            card_anchor_index: dict[tuple, int] = {}
            card_parent_to_subs: dict[str, list] = {}
            for parent in sorted(anchor_parents.keys()):
                relevant_subs = [s_ for s_ in anchor_parents[parent]
                                 if s_.kind in want_kinds]
                if not relevant_subs:
                    continue
                relevant_subs.sort(key=lambda x: x.threshold_value)
                for sub in relevant_subs:
                    key = (parent, sub.label or sub.name)
                    if key in card_anchor_index:
                        continue
                    idx = len(card_anchor_index)
                    card_anchor_index[key] = idx
                    card_parent_to_subs.setdefault(parent, []).append((idx, sub))

            # Per-card default for "show all mons":
            # Bulk Slayer is structural, so untagged rows must be visible by
            # default. Atk/CMP Slayer membership requires anchor pass, so
            # default off.
            any_tagless = any(
                not any(
                    any(s_.kind in want_kinds for s_ in subs)
                    for subs in r.get('_anchor_tags', {}).values()
                )
                for r in cat_ivs
            )
            default_show_all = any_tagless
            show_all_attr = ' checked' if default_show_all else ''

            parts.append(f'<div class="dd-rec-card">\n')
            parts.append(
                f'<h4>{cat_name} '
                f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
                f'({n_total} survivor{"s" if n_total != 1 else ""})'
                f'</span></h4>\n'
            )
            if desc:
                parts.append(f'<p class="dd-small dd-prose">{desc}</p>\n')

            # Filter panel toggle button + collapsed panel body
            if card_anchor_index:
                n_anchors_total = len(card_anchor_index)
                parts.append(
                    f'<button class="dd-filter-toggle" '
                    f'onclick="ddSlayerToggleFilterPanel(\'{card_id}\')">'
                    f'Filter anchors ({n_anchors_total})'
                    f'</button>\n'
                )
                parts.append(
                    f'<div class="dd-filter-panel" id="{card_id}-filter" '
                    f'style="display:none">\n'
                )
                for parent, subs_list in card_parent_to_subs.items():
                    parts.append('<div class="dd-filter-panel-group">\n')
                    is_auto = parent.startswith('auto_')
                    auto_marker = (
                        ' <span class="dd-auto-marker">(auto)</span>'
                        if is_auto else ''
                    )
                    parts.append(
                        f'<label class="dd-filter-master">'
                        f'<input type="checkbox" class="dd-anchor-master" '
                        f'data-card="{card_id}" data-parent-grp="{parent}" '
                        f'checked '
                        f'onchange="ddSlayerToggleMaster(this)"> '
                        f'{parent} ({len(subs_list)}){auto_marker}'
                        f'</label>\n'
                    )
                    parts.append('<div class="dd-filter-children">\n')
                    for idx, sub in subs_list:
                        label = sub.label or sub.name
                        parts.append(
                            f'<label><input type="checkbox" class="dd-anchor-cb" '
                            f'data-card="{card_id}" data-parent-grp="{parent}" '
                            f'data-anchor-idx="{idx}" checked '
                            f'onchange="ddSlayerApplyFilter(\'{card_id}\')"> '
                            f'{label}</label>\n'
                        )
                    parts.append('</div>\n')  # children
                    parts.append('</div>\n')  # group
                # Controls row
                sa_default_js = 'true' if default_show_all else 'false'
                parts.append('<div class="dd-filter-controls">\n')
                parts.append(
                    f'<button onclick="ddSlayerResetFilter(\'{card_id}\', '
                    f'{sa_default_js})">Reset</button>\n'
                )
                parts.append(
                    f'<label><input type="checkbox" class="dd-show-all-mons" '
                    f'data-card="{card_id}"{show_all_attr} '
                    f'onchange="ddSlayerApplyFilter(\'{card_id}\')"> '
                    f'Show all mons (ignore filter)</label>\n'
                )
                parts.append(
                    f'<span class="dd-filter-status">visible: '
                    f'<span id="{card_id}-visible-count">{n_total} / {n_total}</span>'
                    f'</span>\n'
                )
                parts.append('</div>\n')  # controls
                parts.append('</div>\n')  # filter-panel

            # Table
            parts.append(
                f'<table class="dd-table dd-narrow" id="{card_id}-table">\n'
            )
            parts.append(
                '<tr><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th>'
                '<th>Wins</th><th>Avg</th><th>Also</th><th>Tags</th></tr>\n'
            )
            for idx, r in enumerate(cat_ivs):
                a, d, s = r['iv']
                # Cross-category badges
                others = sorted(iv_categories.get(r['iv'], set()) - {cat_name})
                badges = ''
                for o in others:
                    ab = CAT_ABBREV.get(o, '?')
                    col = CAT_COLORS.get(o, '#888')
                    badges += (
                        f'<span class="dd-badge" '
                        f'style="background:{col};color:#000" '
                        f'title="{o}">{ab}</span> '
                    )

                # Ultra-short tag rendering: one badge per parent.
                # Badge VISIBLE TEXT uses derive_short_name() -- typically
                # 3-6 characters (e.g. "lic", "mirb", "lic^lur", "c:lur").
                # The badge HOVER tooltip carries the long form
                # (parent_display_name) plus the per-sub-anchor labels
                # (e.g. "close_combat->125, rage_fist->78"), so the
                # abbreviation stays decipherable. The cell-level title=
                # also includes the full parent name for fallback hover.
                tag_bits = []
                row_anchor_indices = []
                # Per-row counters for the cell-level summary tooltip.
                # Each parent contributes once to its kind bucket and
                # n_subs to the total sub-anchor count.
                n_parents_by_kind = {
                    'damage_breakpoint': 0,
                    'bulkpoint': 0,
                    'cmp': 0,
                }
                n_total_subs = 0
                for parent in sorted(r.get('_anchor_tags', {}).keys()):
                    subs = r['_anchor_tags'][parent]
                    relevant = [s_ for s_ in subs if s_.kind in want_kinds]
                    if not relevant:
                        continue
                    labels = sorted({s_.label or s_.name for s_ in relevant})
                    for s_ in relevant:
                        key = (parent, s_.label or s_.name)
                        if key in card_anchor_index:
                            row_anchor_indices.append(card_anchor_index[key])
                    # Long form (filter panel + tooltip) and short form
                    # (visible badge text). Both derive from the parent
                    # name; long form is also stored on the resolved
                    # anchor as parent_display_name in case the TOML
                    # set it explicitly.
                    long_name = (relevant[0].parent_display_name or parent)
                    short = derive_short_name(parent)
                    n_subs = len(labels)
                    if n_subs == 1:
                        badge_text = short
                        sub_labels_text = labels[0]
                        # For single-sub-anchor parents (Level 1, Level 2,
                        # CMP) the badge has no count suffix and the
                        # tooltip leads with "clears <single sub-anchor>".
                        hover_first_line = (
                            f'{long_name} \u00b7 clears {sub_labels_text}'
                        )
                    else:
                        badge_text = (f'{short}'
                                      f'<span class="dd-anchor-tag-count">'
                                      f'\u00d7{n_subs}</span>')
                        sub_labels_text = ", ".join(labels)
                        # For Level 3 discover-mode parents the badge
                        # shows "<short>xN"; the tooltip explains that
                        # xN means "this IV passes N of the parent's
                        # sub-anchors" so the abbreviation isn't cryptic.
                        hover_first_line = (
                            f'{long_name} \u00b7 '
                            f'clears {n_subs} sub-anchors'
                        )
                    # Hover tooltip on the badge: long display name +
                    # explicit count meaning + full anchor name +
                    # the sub-anchor labels.
                    hover_text_str = (
                        f'{hover_first_line}\n'
                        f'{parent}\n'
                        f'{sub_labels_text}'
                    )
                    hover_attr = hover_text_str.replace('"', '&quot;')
                    tag_bits.append(
                        f'<span class="dd-anchor-tag" title="{hover_attr}">'
                        f'{badge_text}</span>'
                    )
                    # Tally for the cell-level summary tooltip. Use the
                    # kind from the first relevant ResolvedAnchor (all
                    # share kind for a given parent).
                    kind = relevant[0].kind
                    if kind in n_parents_by_kind:
                        n_parents_by_kind[kind] += 1
                    n_total_subs += n_subs
                tags_cell = ' '.join(tag_bits) if tag_bits else '&mdash;'
                # Cell-level title is now a one-line summary instead of
                # the previous per-parent dump (which was 2000+ chars
                # and literally taller than a screen for rows with 40+
                # parents). Per-badge tooltips still hold the per-anchor
                # detail, so this summary just gives an at-a-glance
                # signal of how many parents the row clears and the
                # kind breakdown.
                n_total_parents = sum(n_parents_by_kind.values())
                if n_total_parents == 0:
                    cell_title_attr = 'No anchors cleared'
                else:
                    kind_parts = []
                    if n_parents_by_kind['damage_breakpoint']:
                        kind_parts.append(
                            f"{n_parents_by_kind['damage_breakpoint']} brkp"
                        )
                    if n_parents_by_kind['bulkpoint']:
                        kind_parts.append(
                            f"{n_parents_by_kind['bulkpoint']} blkp"
                        )
                    if n_parents_by_kind['cmp']:
                        kind_parts.append(
                            f"{n_parents_by_kind['cmp']} cmp"
                        )
                    cell_title_attr = (
                        f'Clears {n_total_parents} anchors '
                        f'({" \u00b7 ".join(kind_parts)}) '
                        f'\u00b7 {n_total_subs} sub-anchors total. '
                        f'Hover any badge for per-anchor detail.'
                    )
                data_anchors = ' '.join(str(i) for i in sorted(set(row_anchor_indices)))

                # Row classes: collapse-hidden beyond top N until expanded;
                # highlighted if in the top quartile.
                row_cls_parts = []
                if idx < n_quartile:
                    row_cls_parts.append('dd-slayer-top')
                if idx >= n_visible:
                    row_cls_parts.append('dd-slayer-hidden')
                row_cls = f'class="{" ".join(row_cls_parts)}" ' if row_cls_parts else ''

                parts.append(
                    f'<tr {row_cls}data-anchors="{data_anchors}">'
                    f'<td>{a}/{d}/{s}</td>'
                    f'<td>{r["atk"]:.2f}</td>'
                    f'<td>{r["def_"]:.2f}</td>'
                    f'<td>{r["hp"]}</td>'
                    f'<td class="dd-gain">{r["total_wins"]}</td>'
                    f'<td>{r["avg_score"]:.1f}</td>'
                    f'<td>{badges}</td>'
                    f'<td class="dd-anchor-tags-cell" '
                    f'title="{cell_title_attr}">'
                    f'<div class="dd-anchor-tags-inner dd-tags-compact" '
                    f'onclick="ddToggleTagsCompactCell(event)">'
                    f'{tags_cell}</div></td></tr>\n'
                )
            parts.append('</table>\n')

            # Expand-all toggle if there are hidden rows
            if n_total > n_visible:
                parts.append(
                    f'<button class="dd-slayer-toggle" '
                    f'onclick="(function(btn){{'
                    f'var t=document.getElementById(\'{card_id}-table\');'
                    f'var rows=t.querySelectorAll(\'tr.dd-slayer-hidden\');'
                    f'var shown=rows.length>0 && rows[0].classList.contains(\'dd-slayer-shown\');'
                    f'rows.forEach(function(r){{r.classList.toggle(\'dd-slayer-shown\', !shown);}});'
                    f'btn.textContent=shown?\'Show all {n_total}\':\'Collapse to top {n_visible}\';'
                    f'}})(this)" >'
                    f'Show all {n_total}'
                    f'</button>\n'
                )
            parts.append('</div>\n')  # rec-card
        parts.append('</div>\n')  # rec-grid

        # Level 3 sub-anchor distribution: for each Level 3 parent, show
        # how many survivors clear each sub-anchor. This is the
        # "discover-mode" output -- what BPs and bulkpoints actually
        # matter here. Includes both damage_breakpoint (atk-side) and
        # bulkpoint (def-side) Level 3 parents; the per-row "Threshold"
        # cell is annotated with " atk" or " def" so the two kinds are
        # visually distinct in a single combined table.
        level3_parents = []
        for parent, subs in anchor_parents.items():
            if len(subs) > 1 and all(
                s_.kind in ('damage_breakpoint', 'bulkpoint') for s_ in subs
            ):
                level3_parents.append((parent, subs))
        if level3_parents and slayer_iter_result.get('final'):
            all_survivors = slayer_iter_result['final']
            parts.append(
                '<h4 class="dd-h3" style="margin-top:16px">'
                'Level&nbsp;3 sub-anchor distribution '
                '(breakpoints + bulkpoints)</h4>\n'
            )
            parts.append(
                '<p class="dd-small">For each discover-mode anchor, how '
                'many survivors in the full cohort clear each '
                '(move,&nbsp;tier) sub-anchor. Atk-side rows are '
                'breakpoints (focal&nbsp;atk needed to deal more damage); '
                'def-side rows are bulkpoints (focal&nbsp;def needed to '
                'take less damage). Use this to identify which '
                'sub-anchors actually matter for this species — '
                'high-count rows are the ones worth promoting '
                'to Level&nbsp;1 in the TOML.</p>\n'
            )
            for parent, subs in sorted(level3_parents):
                opp_name = subs[0].opponent if subs[0].opponent else parent
                parts.append(
                    f'<details class="dd-flip-detail">'
                    f'<summary>{_opp_strong(opp_name, parent)} '
                    f'<span class="dd-small">({len(subs)} sub-anchors)'
                    f'</span></summary>\n'
                )
                parts.append('<table class="dd-table dd-narrow">\n')
                parts.append(
                    '<tr><th>Sub-anchor</th><th>Threshold</th>'
                    '<th>Clears</th><th>%</th></tr>\n'
                )
                # Sort sub-anchors by threshold ascending (easier tiers first)
                subs_sorted = sorted(subs, key=lambda x: x.threshold_value)
                for sub in subs_sorted:
                    n_clear = sum(
                        1 for sv in all_survivors
                        if sub.passes(sv['atk'], sv['def_'])
                    )
                    pct = 100.0 * n_clear / len(all_survivors) if all_survivors else 0
                    # Annotate threshold with which stat it targets so
                    # bp/blkp aren't visually conflated.
                    stat_label = 'atk' if sub.target_stat == 'atk' else 'def'
                    parts.append(
                        f'<tr><td>{sub.label}</td>'
                        f'<td>{sub.threshold_value:.2f} {stat_label}</td>'
                        f'<td>{n_clear}/{len(all_survivors)}</td>'
                        f'<td>{pct:.0f}%</td></tr>\n'
                    )
                parts.append('</table>\n')
                parts.append('</details>\n')

    parts.append('</details>\n')  # dd-collapsible
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Analysis section renderers (behind the toggle)
# ---------------------------------------------------------------------------

def render_analysis_alpha_html(scores_flat, nIvs, nS, nO, scenarios,
                               opponents, avg_scores, hp_list, data_obj,
                               opp_label):
    """Render the experimental alpha analysis (banding + clusters).

    Returns an HTML string for the content inside the alpha-features div.
    """
    parts = []

    # -- Banding (#3: sort by eta-squared, label opp IV mode) --
    parts.append('<div class="dd-section" id="dd-banding">\n')
    parts.append('<h2 class="dd-h2">Banding &amp; Stat Correlations</h2>\n')
    parts.append(f'<p>Which stats create visible bands in the scatter plot? '
                 f'Sorted by &eta;&sup2; (variance explained). '
                 f'Computed vs <b>{opp_label}</b> opponent IVs.</p>\n')

    # Compute all banding data first, then sort by avg eta-squared
    banding_rows = []
    for si_or_avg in list(range(nS)) + ['avg']:
        if si_or_avg == 'avg':
            sc = avg_scores
            label = '<strong>Average</strong>'
            is_avg = True
        else:
            si = si_or_avg
            sc = [sum(scores_flat[iv * nS * nO + si * nO + oi] for oi in range(nO)) / nO for iv in range(nIvs)]
            s0, s1 = scenarios[si]
            label = f'{s0}v{s1}'
            is_avg = False
        bands = [('Atk', detect_banding(data_obj['ivAtk'], sc, 'atk')),
                 ('Def', detect_banding(data_obj['ivDef'], sc, 'def')),
                 ('HP', detect_banding(hp_list, sc, 'hp'))]
        dominant = max(bands, key=lambda x: x[1]['eta_squared'] if x[1] else 0)
        max_eta = dominant[1]['eta_squared'] if dominant[1] else 0
        banding_rows.append({'label': label, 'bands': bands, 'dominant': dominant,
                             'max_eta': max_eta, 'is_avg': is_avg})

    # Sort non-avg rows by max eta-squared descending (#3)
    non_avg = [r for r in banding_rows if not r['is_avg']]
    avg_row = [r for r in banding_rows if r['is_avg']]
    non_avg.sort(key=lambda r: r['max_eta'], reverse=True)
    sorted_rows = non_avg + avg_row

    parts.append('<table class="dd-table"><tr><th>Scenario</th><th>Atk <em>r</em></th><th>Atk &eta;&sup2;</th><th>Def <em>r</em></th><th>Def &eta;&sup2;</th><th>HP <em>r</em></th><th>HP &eta;&sup2;</th><th>Dominant</th></tr>\n')
    for row in sorted_rows:
        style = ' style="border-top:2px solid #e94560"' if row['is_avg'] else ''
        line = f'<tr{style}><td>{row["label"]}</td>'
        for name, b in row['bands']:
            if b:
                rc = ' class="dd-strong"' if abs(b['correlation']) > 0.3 else ''
                ec = ' class="dd-strong"' if b['eta_squared'] > 0.3 else ''
                line += f'<td{rc}>{b["correlation"]:+.3f}</td><td{ec}>{b["eta_squared"]:.3f}</td>'
            else:
                line += '<td>-</td><td>-</td>'
        d = row['dominant']
        line += f'<td><strong>{d[0]}</strong> ({d[1]["eta_squared"]:.3f})</td></tr>\n'
        parts.append(line)
    parts.append('</table>\n')

    # HP banding detail (#4: add narrative column)
    avg_hp_band = detect_banding(hp_list, avg_scores, 'hp')
    if avg_hp_band and avg_hp_band['top_jumps']:
        parts.append('<h3 class="dd-h3">Largest HP band jumps (average score)</h3>\n')
        parts.append('<table class="dd-table dd-narrow"><tr><th>HP below</th><th>HP above</th><th>Score jump</th><th>Likely cause</th></tr>\n')
        for k1, k2, diff, n1, n2 in avg_hp_band['top_jumps'][:5]:
            cls = 'dd-gain' if diff > 0 else 'dd-loss'
            hp_below_ivs = [i for i in range(nIvs) if data_obj['ivHp'][i] == int(k1)]
            hp_above_ivs = [i for i in range(nIvs) if data_obj['ivHp'][i] == int(k2)]
            cause = ''
            if hp_below_ivs and hp_above_ivs:
                opp_diffs = []
                for oi in range(nO):
                    below_avg = sum(sum(scores_flat[iv * nS * nO + si * nO + oi] for si in range(nS)) / nS for iv in hp_below_ivs) / len(hp_below_ivs)
                    above_avg = sum(sum(scores_flat[iv * nS * nO + si * nO + oi] for si in range(nS)) / nS for iv in hp_above_ivs) / len(hp_above_ivs)
                    opp_diffs.append((opponents[oi], above_avg - below_avg))
                opp_diffs.sort(key=lambda x: abs(x[1]), reverse=True)
                top_causes = [f'{o} ({d:+.0f})' for o, d in opp_diffs[:2] if abs(d) > 1]
                cause = ', '.join(top_causes) if top_causes else 'distributed across opponents'
            parts.append(f'<tr><td>{int(k1)}</td><td>{int(k2)}</td><td class="{cls}">{diff:+.1f}</td><td class="dd-small">{cause}</td></tr>\n')
        parts.append('</table>\n')
    parts.append('</div>\n')

    # -- Clusters per scenario --
    parts.append(f'<div class="dd-section" id="dd-clusters">\n<h2 class="dd-h2">Cluster Analysis (Per-Scenario)</h2>\n')
    parts.append(f'<p>Computed vs <b>{opp_label}</b> opponent IVs. '
                 f'Clusters are detected by sorting all {nIvs} IVs by their average score '
                 f'for a given scenario and scanning for score gaps that exceed 3&times; '
                 f'the median gap between consecutive IVs. Unlike k-means, this does not '
                 f'assume a fixed number of clusters &mdash; it finds natural breakpoints '
                 f'where performance drops sharply. '
                 f'The top-5 IVs listed below can be located on the graph above by hovering '
                 f'to find the matching stat product and score.</p>\n')
    for si in range(nS):
        s0, s1 = scenarios[si]
        sc = [sum(scores_flat[iv * nS * nO + si * nO + oi] for oi in range(nO)) / nO for iv in range(nIvs)]
        clusters, sig_gaps = detect_clusters(sc, data_obj)
        top50 = set(sorted(range(nIvs), key=lambda i: sc[i], reverse=True)[:50])
        opp_imp = opp_importance(scores_flat, nIvs, nS, nO, si, top50, opponents)
        scene_label = f'{s0}v{s1}'
        if s0 == s1:
            scene_label += {0: ' (no shields)', 1: ' (even)', 2: ' (double shield)'}.get(s0, '')
        elif s0 > s1:
            scene_label += ' (shield adv.)'
        else:
            scene_label += ' (shield disadv.)'
        parts.append(f'<h3 class="dd-h3">{scene_label}</h3>\n')
        scene_ranked = sorted(range(nIvs), key=lambda i: sc[i], reverse=True)
        if sig_gaps:
            top_cluster_size = sig_gaps[0][0]
            top_cluster_ivs = scene_ranked[:top_cluster_size]
            tc_sp_min = min(data_obj['spRanks'][iv] for iv in top_cluster_ivs)
            tc_sp_max = max(data_obj['spRanks'][iv] for iv in top_cluster_ivs)
            tc_score_min = sc[scene_ranked[top_cluster_size - 1]]
            tc_score_max = sc[scene_ranked[0]]
            parts.append(f'<p>{len(sig_gaps)} significant gap(s). '
                         f'Top cluster: {top_cluster_size} IVs, '
                         f'scores {tc_score_min:.0f}&ndash;{tc_score_max:.0f} '
                         f'(SP ranks {tc_sp_min}&ndash;{tc_sp_max}). '
                         f'<b>On graph:</b> look for Y &ge; {tc_score_min:.0f} '
                         f'with SP rank {tc_sp_min}&ndash;{tc_sp_max} on X axis.</p>\n')
        else:
            parts.append('<p>Smooth gradient (no gaps &gt; 3&times; median).</p>\n')
        parts.append('<table class="dd-table dd-narrow"><tr><th>#</th><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th><th>SP</th><th>Score</th><th>Tier</th></tr>\n')
        for rank in range(5):
            iv = scene_ranked[rank]
            sp = data_obj['ivSp'][iv]
            parts.append(f'<tr><td>{rank+1}</td><td>{iv_label(data_obj, iv)}</td><td>{data_obj["ivAtk"][iv]:.2f}</td><td>{data_obj["ivDef"][iv]:.2f}</td><td>{data_obj["ivHp"][iv]}</td><td>{sp:.0f}</td><td>{sc[iv]:.1f}</td><td>{tier_badge_html(data_obj, iv)}</td></tr>\n')
        parts.append('</table>\n')
        pos = [d for d in opp_imp if d['gap'] > 0][:3]
        neg = [d for d in opp_imp if d['gap'] < 0][:2]
        pos_str = ', '.join(f'{d["opponent"]} ({d["gap"]:+.0f})' for d in pos)
        neg_str = ', '.join(f'{d["opponent"]} ({d["gap"]:+.0f})' for d in neg)
        line = f'<p class="dd-small"><b>Top differentiators:</b> {pos_str}'
        if neg:
            line += f' | <b>Sacrifices:</b> {neg_str}'
        parts.append(line + '</p>\n')
    parts.append('</div>\n')

    return ''.join(parts)


def render_analysis_volatility_html(data_obj, nIvs, nS, scenarios,
                                    scene_ranks, avg_ranks, ranked,
                                    opp_label):
    """Render the Rank Volatility section. Returns an HTML string."""
    parts = []
    parts.append(f'<div class="dd-section" id="dd-volatility">\n<h2 class="dd-h2">Rank Volatility</h2>\n')
    parts.append(f'<p>Each IV is ranked separately for each shield scenario '
                 f'(vs <b>{opp_label}</b> opponent IVs). '
                 f'The numbers in the table are that IV\'s rank out of {nIvs} '
                 f'for each scenario. '
                 f'High range = scenario specialist; low range = generalist.</p>\n')
    parts.append('<table class="dd-table"><tr><th>IVs</th>')
    for s0, s1 in scenarios:
        parts.append(f'<th title="Rank out of {nIvs} IVs in the {s0}v{s1} shield scenario (1 = best)">{s0}v{s1}</th>')
    parts.append(f'<th title="Overall rank when averaging across all scenarios">Avg</th>'
                 f'<th title="Difference between best and worst scenario rank (lower = more consistent)">Range</th>'
                 f'<th>Tier</th></tr>\n')
    for iv in ranked[:15]:
        row = f'<tr><td>{iv_label(data_obj, iv)}</td>'
        ranks_for_iv = [scene_ranks[si][iv] for si in range(nS)]
        for r in ranks_for_iv:
            cls = ''
            if r <= 10:
                cls = ' class="dd-rank-good"'
            elif r > 1000:
                cls = ' class="dd-rank-bad"'
            row += f'<td{cls} title="Rank {r} out of {nIvs}">{r}</td>'
        rng = max(ranks_for_iv) - min(ranks_for_iv)
        row += f'<td><b>{avg_ranks[iv]}</b></td><td>{rng}</td><td>{tier_badge_html(data_obj, iv)}</td></tr>\n'
        parts.append(row)
    parts.append('</table>\n')

    # Most stable top-50
    top50_vols = [(iv, max(scene_ranks[si][iv] for si in range(nS)) - min(scene_ranks[si][iv] for si in range(nS))) for iv in ranked[:50]]
    top50_vols.sort(key=lambda x: x[1])
    parts.append('<h3 class="dd-h3">Most stable top-50 IVs</h3>\n')
    parts.append('<table class="dd-table dd-narrow"><tr><th>IVs</th><th>Avg</th><th>Best</th><th>Worst</th><th title="Best rank minus worst rank">Range</th><th>Tier</th></tr>\n')
    for iv, rng in top50_vols[:8]:
        best = min(scene_ranks[si][iv] for si in range(nS))
        worst = max(scene_ranks[si][iv] for si in range(nS))
        parts.append(f'<tr><td>{iv_label(data_obj, iv)}</td><td>{avg_ranks[iv]}</td><td class="dd-rank-good">{best}</td><td>{worst}</td><td>{rng}</td><td>{tier_badge_html(data_obj, iv)}</td></tr>\n')
    parts.append('</table></div>\n')

    return ''.join(parts)


def render_analysis_flips_html(data_obj, flip_summary, flips, avg_scores,
                               ranked, ref_iv, opp_label, opp_info_cache,
                               focal_moves, focal_types, ref_atk, ref_def,
                               has_bait_axis=False):
    """Render the Matchup Flip Table section. Returns an HTML string."""
    parts = []
    parts.append(f'<div class="dd-section" id="dd-flips">\n<h2 class="dd-h2">Matchup Flip Table</h2>\n')
    parts.append(f'<p>Matchups crossing 500-point boundary vs reference '
                 f'({iv_label(data_obj, ref_iv)}, {opp_label}).</p>\n')

    parts.append('<table class="dd-table"><tr><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th><th>Avg</th><th>Gains</th><th>Loses</th><th>Net</th><th>Tier</th></tr>\n')
    for iv, g, l, net in flip_summary[:25]:
        nc = 'dd-gain' if net > 0 else ('dd-loss' if net < 0 else '')
        parts.append(f'<tr><td>{iv_label(data_obj, iv)}</td><td>{data_obj["ivAtk"][iv]:.2f}</td><td>{data_obj["ivDef"][iv]:.2f}</td><td>{data_obj["ivHp"][iv]}</td><td>{avg_scores[iv]:.1f}</td><td class="dd-gain">{g}</td><td class="dd-loss">{l}</td><td class="{nc}"><b>{net:+d}</b></td><td>{tier_badge_html(data_obj, iv)}</td></tr>\n')
    parts.append('</table>\n')

    # Detail flips for notable IVs -- with breakpoint narration
    notable = [x for x in flip_summary if abs(x[3]) >= 3 or x[0] in set(ranked[:5])]
    for iv, g, l, net in notable[:8]:
        fd = flips[iv]
        prose = prose_flip_summary(fd, has_bait_axis=has_bait_axis)
        parts.append(f'<details class="dd-flip-detail"><summary>{iv_label(data_obj, iv)} &mdash; <span class="dd-gain">+{g}</span>/<span class="dd-loss">-{l}</span> (net {net:+d}){tier_badge_html(data_obj, iv)}</summary>\n')
        parts.append(f'<p class="dd-prose">{prose}</p>\n')
        focal_atk_iv = data_obj['ivAtk'][iv]
        focal_def_iv = data_obj['ivDef'][iv]
        focal_hp_iv = data_obj['ivHp'][iv]
        ref_hp_val2 = data_obj['ivHp'][ref_iv]
        for label_text, entries, cls, is_gain in [('Gains', fd['gains'], 'dd-gain', True),
                                                   ('Losses', fd['losses'], 'dd-loss', False)]:
            if entries:
                entries_sorted = sorted(entries, key=lambda e: abs(e['iv_score'] - e['ref_score']), reverse=True)
                parts.append(f'<table class="dd-table dd-narrow"><tr><th>Scen.</th><th>Opponent</th><th>Ref</th><th>IV</th><th>&Delta;</th><th>Why</th></tr>\n')
                for e in entries_sorted:
                    d = e['iv_score'] - e['ref_score']
                    narr = ''
                    opp_name = e['opponent']
                    if opp_name in opp_info_cache and focal_moves:
                        oi = opp_info_cache[opp_name]
                        narr = analysis.narrate_flip(
                            focal_atk_iv, focal_def_iv, focal_hp_iv,
                            ref_atk, ref_def, ref_hp_val2,
                            oi['atk'], oi['def_'], opp_name,
                            focal_moves, oi['moves'],
                            focal_types, oi['types'],
                            is_gain=is_gain,
                        )
                    opp_cell = e['opponent']
                    if has_bait_axis:
                        ebm = e.get('bait_modes', set())
                        if ebm == {'bait'}:
                            opp_cell += ' <span class="dd-badge" style="background:#1a3a6e;color:#58a6ff">[bait only]</span>'
                        elif ebm == {'nobait'}:
                            opp_cell += ' <span class="dd-badge" style="background:#1a3a6e;color:#58a6ff">[no-bait only]</span>'
                    parts.append(f'<tr><td>{e["scenario"]}</td><td>{opp_cell}</td><td>{e["ref_score"]}</td><td class="{cls}">{e["iv_score"]}</td><td class="{cls}">{d:+d}</td><td class="dd-small">{narr}</td></tr>\n')
                parts.append('</table>\n')
        parts.append('</details>\n')
    parts.append('</div>\n')

    return ''.join(parts)


def render_analysis_methods_html(nIvs, nS, nO, data_obj, moveset_label,
                                 opp_iv_mode, ref_iv, opp_label):
    """Render the Methods documentation section. Returns an HTML string."""
    return f"""
<div class="dd-section" id="dd-methods">
<h2 class="dd-h2">Methods</h2>
<p>Automated analysis of {nIvs} IV spreads across {nS} shield scenarios against
{nO} opponents ({data_obj.get('opponentLabel', '')}).</p>
<p><strong>Moveset:</strong> {analysis.pretty_moveset(moveset_label)} | <strong>Opp IVs:</strong> {opp_iv_mode}
| <strong>Reference IV:</strong> {iv_label(data_obj, ref_iv)} (PvPoke default)</p>
<dl class="dd-methods-dl">
  <dt>Rank volatility</dt>
  <dd>Each IV is ranked 1&ndash;{nIvs} for each scenario independently. The range (best rank minus
  worst rank) shows how scenario-dependent performance is. Low range = generalist; high range = specialist.</dd>
  <dt>Matchup flip analysis</dt>
  <dd>For each IV, we check every (opponent, scenario) pair and compare to the reference IV
  ({iv_label(data_obj, ref_iv)}, {opp_label}). A &ldquo;flip&rdquo; occurs when one IV wins
  (score &ge; 500) and the other loses (&lt; 500). Net flips = gains &minus; losses.</dd>
  <dt>Breakpoint/bulkpoint narration</dt>
  <dd>For each flip, we compute per-hit damage from each move at the focal IV and reference IV
  stats. Damage changes are reported as breakpoints (your moves do more damage), bulkpoints
  (opponent moves do less damage), or their losses. HP differences are also shown.</dd>
</dl>
<div id="dd-alpha-methods" style="display:none">
<h3 class="dd-h3">Experimental methods</h3>
<dl class="dd-methods-dl">
  <dt>Banding detection</dt>
  <dd>IVs grouped by discrete stat value. F-ratio and &eta;&sup2; (fraction of total score
  variance explained by stat grouping, 0&ndash;1 scale) measure how much each stat creates
  visible bands. Pearson <em>r</em> shows correlation direction (positive = higher stat &rarr; higher score).</dd>
  <dt>Cluster detection (gap analysis)</dt>
  <dd>All {nIvs} IVs are sorted by their average score for a given scenario. We compute the
  score difference between each consecutive pair. The median of these differences is the
  &ldquo;typical&rdquo; gap. Gaps exceeding 3&times; the median indicate a natural break between
  performance tiers. This is <em>not</em> k-means or similar &mdash; it assumes no fixed cluster
  count and finds breakpoints where performance drops sharply.</dd>
  <dt>Opponent importance</dt>
  <dd>For each scenario, the average score of the top 50 IVs against each opponent is compared
  to the population average. Large positive gaps show which opponents the top cluster dominates;
  negative gaps show where it sacrifices performance.</dd>
</dl>
</div>
</div>
"""


def _render_iv_recommendations(rec_candidates, flips, opp_label, data_obj,
                               ref_iv, ref_atk, ref_def, opp_info_cache,
                               focal_moves, focal_types, has_bait_axis=False):
    """Render the top-3 IV recommendation cards as an HTML fragment.

    Returned HTML is injected into the Notable IVs & Recommendations
    section by ``render_results_section``.
    """
    if not rec_candidates:
        return ''
    parts = []
    parts.append('<h4 class="dd-h3" style="margin-top:18px">Top Picks</h4>\n')
    parts.append(
        f'<p class="dd-small">Top candidates by average score, matchup flips, '
        f'and rank stability vs {opp_label} opponents.</p>\n')
    parts.append('<div class="dd-rec-grid">\n')
    for rc in rec_candidates[:3]:
        iv = rc['iv']
        nc = 'dd-gain' if rc['net'] > 0 else ('dd-loss' if rc['net'] < 0 else '')
        fd = flips.get(iv, {'gains': [], 'losses': []})
        prose = prose_flip_summary(fd, max_gains=2, max_losses=1, has_bait_axis=has_bait_axis)
        parts.append('<div class="dd-rec-card">\n')
        style_color = '#58a6ff' if rc['style'] == 'Bait Robust' else '#e94560'
        parts.append(f'<h4 style="color:{style_color}">{rc["style"]}: {iv_label(data_obj, iv)}{tier_badge_html(data_obj, iv)}</h4>\n')
        parts.append(f'<p>Atk={data_obj["ivAtk"][iv]:.2f}, Def={data_obj["ivDef"][iv]:.2f}, HP={data_obj["ivHp"][iv]}, SP #{data_obj["spRanks"][iv]}</p>\n')
        parts.append(f'<p>Avg score rank: <b>#{rc["avg_rank"]}</b> ({rc["avg_score"]:.1f})</p>\n')
        parts.append(f'<p>Flips vs {opp_label} ref: <span class="dd-gain">+{rc["gains"]}</span>/<span class="dd-loss">-{rc["losses"]}</span> = <span class="{nc}"><b>{rc["net"]:+d}</b></span></p>\n')
        parts.append(f'<p class="dd-prose">{prose}</p>\n')
        focal_atk_rc = data_obj['ivAtk'][iv]
        focal_def_rc = data_obj['ivDef'][iv]
        focal_hp_rc = data_obj['ivHp'][iv]
        ref_hp_val = data_obj['ivHp'][ref_iv]
        bp_lines = []
        for is_gain, entries in [(True, fd.get('gains', [])[:2]), (False, fd.get('losses', [])[:1])]:
            for e in entries:
                opp_name = e['opponent']
                if opp_name in opp_info_cache and focal_moves:
                    oi = opp_info_cache[opp_name]
                    narr = analysis.narrate_flip(
                        focal_atk_rc, focal_def_rc, focal_hp_rc,
                        ref_atk, ref_def, ref_hp_val,
                        oi['atk'], oi['def_'], opp_name,
                        focal_moves, oi['moves'],
                        focal_types, oi['types'],
                        is_gain=is_gain,
                    )
                    if narr:
                        bp_lines.append(narr)
        if bp_lines:
            parts.append(f'<p class="dd-small"><b style="color:#58a6ff">Key changes</b><br>{"<br>".join(bp_lines)}</p>\n')
        parts.append('</div>\n')
    parts.append('</div>\n')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Results section renderer
# ---------------------------------------------------------------------------

def render_results_section(data_obj, moveset_label, opp_label,
                           effective_tiers, anchor_flip_records,
                           all_matchup_boundaries, score_arrays,
                           moveset_idx, flips, flip_map, avg_ranks,
                           avg_scores, rec_candidates, slayer_iter_result,
                           opp_info_cache, focal_moves, focal_types,
                           ref_atk, ref_def, ref_iv, opp_iv_mode,
                           scores_flat, nS, nO, scenarios, opponents,
                           anchor_passing_sink, has_toml_tiers, ranked,
                           hp_list, nIvs, has_bait_axis=False):
    """Render the always-visible Deep Dive Results section.

    Returns an HTML string. Computation (anchor aggregation, tier
    derivation, matchup boundaries) is done by the caller; this function
    only assembles HTML from pre-computed data.
    """
    parts = []

    parts.append('<div class="dd-section" id="dd-recommendations">\n')
    parts.append(f'<h2 class="dd-h2">Deep Dive Results</h2>\n')
    parts.append(f'<p>Moveset: {analysis.pretty_moveset(moveset_label)}. '
                 f'Vs {opp_label} opponents.</p>\n')

    # -- Partition by source for two-zone rendering --
    expert_tiers = [t for t in effective_tiers if t.get('source')]
    sim_tiers = [t for t in effective_tiers if not t.get('source')]
    expert_anchor_recs = [r for r in anchor_flip_records
                          if r['anchor'].source]
    sim_anchor_recs = [r for r in anchor_flip_records
                       if not r['anchor'].source]
    has_expert_content = bool(expert_tiers) or bool(expert_anchor_recs)

    # Collect unique source attributions for the expert zone header
    expert_sources = set()
    for t in expert_tiers:
        if t.get('source'):
            expert_sources.add(t['source'])
    for r in expert_anchor_recs:
        if r['anchor'].source:
            expert_sources.add(r['anchor'].source)

    # ================================================================
    # Expert Analysis zone
    # ================================================================
    if has_expert_content:
        source_label = ', '.join(sorted(expert_sources))
        parts.append('<div class="dd-expert-zone">\n')
        parts.append(f'<h3>Expert Analysis ({source_label})</h3>\n')
        parts.append(
            '<details class="dd-glossary" style="margin:0 0 12px 0;font-size:0.9rem">\n'
            '<summary style="cursor:pointer;color:#d29922">What am I looking at? (glossary)</summary>\n'
            '<ul style="margin:8px 0 4px 18px;line-height:1.55;color:#c9d1d9">\n'
            '<li><b>Tier</b> (a.k.a. <i>spread</i>) &mdash; a named stat-cutoff region, e.g. '
            '"GH Great = Def &ge; 143.03, HP &ge; 138." Any IV meeting all the cutoffs is in the tier.</li>\n'
            '<li><b>Anchor</b> &mdash; a yes/no rule applied to one IV, e.g. "clears the Medicham '
            'Dynamic Punch bulkpoint." Each anchor reduces to a single numeric threshold.</li>\n'
            '<li><b>Breakpoint</b> &mdash; an <i>attack</i> threshold at which one of your moves '
            'deals +1 more integer damage to a specific opponent.</li>\n'
            '<li><b>Bulkpoint</b> &mdash; a <i>defense</i> threshold at which one of an opponent\'s '
            'moves deals 1 less integer damage to you. The defensive mirror of a breakpoint.</li>\n'
            '<li><b>Matchup-flipping boundary</b> &mdash; a full-battle stat target: the smallest '
            'stat increase that turns a simulated loss into a win against a specific opponent and '
            'shield scenario (not just a damage-tier change).</li>\n'
            '</ul>\n'
            '<p style="margin:6px 0 0 0;font-size:0.82rem;color:#8b949e">'
            'Full definitions in <code>docs/concepts.md</code>.</p>\n'
            '</details>\n'
        )

        # Expert tier cards
        if expert_tiers:
            expert_tier_cards = render_threshold_tier_cards(
                data_obj, expert_anchor_recs, avg_ranks, flip_map,
                override_tiers=expert_tiers,
                score_arrays=score_arrays, moveset_idx=moveset_idx,
                flips_detail=flips,
                matchup_boundaries=all_matchup_boundaries,
                anchor_passing_sink=anchor_passing_sink,
                has_bait_axis=has_bait_axis,
            )
            if expert_tier_cards:
                parts.append(expert_tier_cards)

        # Expert anchor summaries with TOML descriptions
        # Group by parent anchor name to avoid duplicates from Level 3 expansion
        seen_parents = set()
        expert_summary_bullets = []
        for rec in expert_anchor_recs:
            a = rec['anchor']
            if a.parent in seen_parents:
                continue
            seen_parents.add(a.parent)
            stat_label = 'Atk' if a.target_stat == 'atk' else 'Def'
            desc = a.description or f'{a.opponent} {a.kind}'
            opp_c = _opp_color(a.opponent)
            expert_summary_bullets.append(
                f'<li><span class="dd-strong" style="color:{opp_c}">'
                f'{a.opponent}</span> '
                f'({stat_label}-side) - {desc}</li>'
            )
        if expert_summary_bullets:
            parts.append('<ul class="dd-expert-anchors">\n')
            parts.append('\n'.join(expert_summary_bullets))
            parts.append('\n</ul>\n')
            parts.append(
                '<p class="dd-small" style="color:#8b949e">'
                'Full breakpoint details in '
                '<a href="#dd-stat-thresholds" style="color:#58a6ff" onclick="var el=document.getElementById(\'dd-stat-thresholds\');if(el)el.open=true;">'
                'Stat Thresholds &amp; Matchup Flips</a> below.</p>\n'
            )

        parts.append('</div>\n')  # end expert zone

    # ================================================================
    # Simulation Deep Dive zone
    # ================================================================
    parts.append('<div class="dd-sim-zone">\n')
    parts.append('<h3>Simulation Deep Dive</h3>\n')

    # -- Sim-only Tier Cards (if any auto-derived tiers exist) --
    if sim_tiers:
        sim_tier_cards = render_threshold_tier_cards(
            data_obj, sim_anchor_recs, avg_ranks, flip_map,
            override_tiers=sim_tiers,
            score_arrays=score_arrays, moveset_idx=moveset_idx,
            flips_detail=flips,
            matchup_boundaries=all_matchup_boundaries,
            anchor_passing_sink=anchor_passing_sink,
            has_bait_axis=has_bait_axis,
        )
        if sim_tier_cards:
            parts.append(sim_tier_cards)

    # -- IV Recommendations (rendered first, injected into Notable IVs) --
    rec_html = _render_iv_recommendations(
        rec_candidates, flips, opp_label, data_obj, ref_iv, ref_atk,
        ref_def, opp_info_cache, focal_moves, focal_types,
        has_bait_axis=has_bait_axis)

    # -- Notable IVs & Recommendations --
    from deep_dive import build_iv_categories
    slayer_categories_for_ivcat = None
    if slayer_iter_result:
        slayer_categories_for_ivcat = slayer_iter_result.get('categories')
    matchup_data_for_ivcat = {
        'scores_flat': scores_flat,
        'nS': nS, 'nO': nO,
        'scenarios': scenarios,
        'opponents': opponents,
        'opp_iv_mode': opp_iv_mode,
        'win_threshold': 500,
    }
    iv_categories_all = build_iv_categories(
        data_obj,
        slayer_categories=slayer_categories_for_ivcat,
        matchup_data=matchup_data_for_ivcat,
    )

    # -- Bait-differential matchup cards --
    # When both bait modes were swept, find (opponent, scenario) pairs
    # where the win set differs between bait-on and bait-off. Emit
    # categories for "only wins with bait" and "only wins without bait".
    if has_bait_axis and score_arrays is not None:
        nobait_mode = compose_mode(parse_mode(opp_iv_mode)[0], 'nobait')
        nobait_key = f'{moveset_idx}_{nobait_mode}'
        nobait_scores = score_arrays.get(nobait_key, [])
        n_ivs = data_obj['nIvs']
        win_threshold = 500
        opp_iv_base = parse_mode(opp_iv_mode)[0]
        opp_iv_label = ('PvPoke default' if opp_iv_base == 'pvpoke'
                        else 'rank 1')
        iv_a = data_obj.get('ivA', [])
        iv_d = data_obj.get('ivD', [])
        iv_s = data_obj.get('ivS', [])
        if nobait_scores and len(nobait_scores) >= n_ivs * nS * nO:
            for oi, opp_name in enumerate(opponents):
                if oi >= nO:
                    break
                for si, scen in enumerate(scenarios):
                    if si >= nS:
                        break
                    bait_wins = set()
                    nobait_wins = set()
                    for iv in range(n_ivs):
                        idx = iv * nS * nO + si * nO + oi
                        if scores_flat[idx] >= win_threshold:
                            bait_wins.add(iv)
                        if nobait_scores[idx] >= win_threshold:
                            nobait_wins.add(iv)
                    # "Only wins with bait" = bait_wins - nobait_wins
                    only_bait = sorted(bait_wins - nobait_wins)
                    # "Only wins without bait" = nobait_wins - bait_wins
                    only_nobait = sorted(nobait_wins - bait_wins)
                    scen_label = f'{scen[0]}v{scen[1]}'
                    for members, bait_tag, bait_val in [
                        (only_bait, 'with bait', 'bait'),
                        (only_nobait, 'no bait', 'nobait'),
                    ]:
                        if not members or len(members) == n_ivs:
                            continue
                        meta = {}
                        for iv in members:
                            s_bait = scores_flat[iv * nS * nO + si * nO + oi]
                            s_nobait = nobait_scores[iv * nS * nO + si * nO + oi]
                            meta[iv] = {
                                'iv': ((iv_a[iv], iv_d[iv], iv_s[iv])
                                       if iv < len(iv_a) else None),
                                'score': s_bait if bait_val == 'bait' else s_nobait,
                            }
                        name = (f'Beats {opp_iv_label} {opp_name} '
                                f'in the {scen_label} {bait_tag} only')
                        iv_categories_all.append(IVCategory(
                            name=name,
                            kind='matchup',
                            members=members,
                            description=(
                                f'IVs that beat {opp_iv_label} {opp_name} '
                                f'in the {scen_label} only {bait_tag} '
                                f'(lose in the other bait mode).'
                            ),
                            matchup_conditions=[{
                                'opponent': opp_name,
                                'opponent_ivs': opp_iv_mode,
                                'scenario': (scen[0], scen[1]),
                                'bait': bait_val,
                                'outcome': 'win',
                            }],
                            member_meta=meta,
                        ))

    notable_html = render_notable_ivs_section(
        iv_categories_all, data_obj, opp_iv_mode,
        recommendations_html=rec_html,
    )
    if notable_html:
        parts.append(notable_html)

    # -- Mirror Slayer Iteration --
    slayer_html = render_mirror_slayer_html(
        slayer_iter_result=slayer_iter_result,
        data_obj=data_obj, moveset_idx=moveset_idx)
    if slayer_html:
        parts.append(slayer_html)

    # -- Stat Thresholds & Matchup Flips (merged section) --
    threshold_descs = generate_threshold_descriptions(flips, data_obj, avg_scores, ranked, opp_iv_mode,
                                                      has_bait_axis=has_bait_axis)
    mb_bullets = []
    if all_matchup_boundaries:
        _sorted_mbs = sorted(
            all_matchup_boundaries,
            key=lambda m: (0 if m.get('stat', 'def') == 'def' else 1,
                           m['threshold'], m['opponent']),
        )
        mb_bullets = render_matchup_boundary_bullets(
            _sorted_mbs, has_bait_axis=has_bait_axis,
            toggle_id='mb-standalone', top_n=10)
    anchor_bullets = []
    if anchor_flip_records:
        anchor_bullets = render_anchor_flip_bullets(
            anchor_flip_records, anchor_passing_sink=anchor_passing_sink,
            has_bait_axis=has_bait_axis)

    has_any_threshold = threshold_descs or mb_bullets or anchor_bullets
    if has_any_threshold:
        # Summary counts for the collapsed header
        summary_parts = []
        if threshold_descs:
            summary_parts.append(f'{len(threshold_descs)} key flips')
        if mb_bullets:
            summary_parts.append(f'{len(mb_bullets)} boundaries')
        if anchor_bullets:
            summary_parts.append(f'{len(anchor_bullets)} anchors')
        summary_text = ', '.join(summary_parts)

        parts.append(
            f'<details class="dd-collapsible" id="dd-stat-thresholds">'
            f'<summary class="dd-h3" style="cursor:pointer">'
            f'Stat Thresholds &amp; Matchup Flips '
            f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
            f'({summary_text})</span>'
            f'</summary>\n')

        # Key Matchup Thresholds — the high-level overview, always visible on expand
        if threshold_descs:
            parts.append('<h4 class="dd-h3">Key Matchup Thresholds</h4>\n')
            parts.append(f'<p>Matchups that flip vs {opp_label} opponents, '
                         f'ordered by how many top IVs benefit:</p>\n')
            parts.append('<ul class="dd-threshold-list">\n')
            parts.append('\n'.join(threshold_descs))
            parts.append('\n</ul>\n')

        # Matchup-Flipping Boundaries — nested collapsible
        if mb_bullets:
            parts.append(
                f'<details class="dd-collapsible">'
                f'<summary class="dd-h3" style="cursor:pointer">'
                f'Matchup-Flipping Boundaries '
                f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
                f'({len(mb_bullets)} boundaries)</span>'
                f'</summary>\n')
            parts.append(
                '<p>The minimum def or atk (+ HP) at which a matchup outcome '
                'actually changes from loss to win. These are higher than '
                'damage-tier boundaries because multiple damage changes must '
                'accumulate across a full battle to flip the result. '
                f'Vs {opp_label} opponents.</p>\n'
            )
            parts.append('<ul class="dd-threshold-list">\n')
            parts.append('\n'.join(mb_bullets))
            parts.append('\n</ul>\n')
            parts.append('</details>\n')

        # Anchor-Driven Matchup Flips — nested collapsible
        if anchor_bullets:
            parts.append(
                f'<details class="dd-collapsible">'
                f'<summary class="dd-h3" style="cursor:pointer">'
                f'Anchor-Driven Matchup Flips '
                f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
                f'({len(anchor_bullets)} anchors)</span>'
                f'</summary>\n')
            parts.append(
                '<p>Damage-tier boundaries from named anchors - the def/atk '
                'at which a specific move\'s damage steps up or down by 1. '
                'These are necessary but not always sufficient to flip a '
                'matchup (see Matchup-Flipping Boundaries above for the '
                f'actual stat targets). Vs {opp_label} opponents.</p>\n'
            )
            parts.append('<ul class="dd-threshold-list">\n')
            parts.append('\n'.join(anchor_bullets))
            parts.append('\n</ul>\n')
            parts.append('</details>\n')

        parts.append('</details>\n')  # outer collapsible

    parts.append('</div>\n')  # end sim zone

    parts.append('</div>\n')

    return ''.join(parts)
