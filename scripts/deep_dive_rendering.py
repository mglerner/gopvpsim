"""Rendering helpers for IV deep dive HTML output.

Functions that produce HTML fragments (hover text, tier badges, matchup
bullets, etc.) for injection into the interactive deep dive page.  Pure
HTML generation -- no simulation or analysis logic.
"""
import hashlib
import html as _html
import json
import math
import re

from dataclasses import dataclass, field
from typing import Optional

import deep_dive_analysis as analysis
from gopvpsim.anchors import derive_short_name
from render_article import format_block_attribution, format_body
from auto_gen_narrative import classify_atk_weight, atk_weight_tip


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
# Tooltip registry (deduplicate title= attribute values)
# ---------------------------------------------------------------------------
# A single Oinkologne GL dive emits ~87k title= attributes but only
# ~1.6k unique values (every anchor-tag badge carries the same tooltip
# across hundreds of IV cells). Rather than interpolate the full text
# inline, the renderer registers each tooltip here and emits
# data-t="<short-id>". At page load a DOMContentLoaded pass looks up
# DATA.tooltips[id] and sets the .title attribute on each tagged node.
#
# Saves ~18 MB on an Oinkologne-shape dive, ~300 KB on a Tinkaton-shape
# dive. See docs/s11_html_size_audit.md for full budget.


class _TooltipRegistry:
    # Base-62 alphabet starting with letters; 62^2=3844 so the common
    # case (~1.6k unique tooltips) is covered by 2-char ids.
    _ALPHA = (
        'abcdefghijklmnopqrstuvwxyz'
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        '0123456789'
    )

    def __init__(self):
        self._by_text: dict[str, str] = {}
        self._ordered: list[str] = []

    def reset(self) -> None:
        self._by_text.clear()
        self._ordered.clear()

    def register(self, text: str) -> str:
        if not text:
            return ''
        cached = self._by_text.get(text)
        if cached is not None:
            return cached
        sid = self._encode(len(self._ordered))
        self._ordered.append(text)
        self._by_text[text] = sid
        return sid

    @classmethod
    def _encode(cls, n: int) -> str:
        a = cls._ALPHA
        if n < len(a):
            return a[n]
        out = []
        while n:
            out.append(a[n % len(a)])
            n //= len(a)
        return ''.join(reversed(out))

    def dump(self) -> dict[str, str]:
        return {self._encode(i): t for i, t in enumerate(self._ordered)}

    def count(self) -> int:
        return len(self._ordered)


_TOOLTIPS = _TooltipRegistry()


def reset_tooltip_registry() -> None:
    _TOOLTIPS.reset()


def dump_tooltip_registry() -> dict[str, str]:
    return _TOOLTIPS.dump()


def tooltip_count() -> int:
    return _TOOLTIPS.count()


def tooltip_attr(text: str) -> str:
    """Return ' data-t="<sid>"' for interpolation into an open HTML tag.

    Registers `text` in the module-global registry; deep_dive.py dumps
    the registry into DATA.tooltips at emit time, and runtime JS maps
    data-t back to el.title on DOMContentLoaded.

    Returns '' if text is falsy, so callers can interpolate
    unconditionally without guard logic.
    """
    if not text:
        return ''
    return f' data-t="{_TOOLTIPS.register(text)}"'


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
    """Deterministic color for an opponent name (case-insensitive).

    Hashes the *gamemaster* name (not the prettified display name) so
    the colour stays stable across the 2026-05-17 shadow/regional
    renaming convention. ``Forretress (Shadow)`` and
    ``Shadow Forretress`` always read the same colour because both
    map to the same gamemaster ``speciesName`` upstream.
    """
    h = int(hashlib.md5(name.lower().encode()).hexdigest(), 16)
    return _OPP_COLORS[h % len(_OPP_COLORS)]


def _opp_b(name):
    """Wrap an opponent name in a colored <b> tag.

    Display text is run through ``pretty_species`` so the rendered
    name follows the modifier-first convention (`Shadow Forretress`,
    `Galarian Corsola`, etc.). The color hash still uses the
    gamemaster name for stability across the rename.
    """
    from gopvpsim.display import pretty_species
    return f'<b style="color:{_opp_color(name)}">{pretty_species(name)}</b>'


def _opp_strong(color_key, display_text=None):
    """Wrap text in a colored <strong> tag using the opponent's color.

    If ``display_text`` isn't supplied, the prettified form of
    ``color_key`` is used as the visible text. The color hash always
    uses the raw ``color_key`` for stability.
    """
    from gopvpsim.display import pretty_species
    if display_text is None:
        display_text = pretty_species(color_key)
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
.dd-callout { --sidebar-color: #58a6ff; --sidebar-width: 3px;
  background: #0f3460; padding: 8px 12px 8px 16px; margin: 10px 0;
  border-radius: 0 4px 4px 0; font-size: 0.85rem; }
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
.dd-threshold-list li { --sidebar-color: #0f3460; --sidebar-width: 2px;
  padding: 4px 0 4px 14px; margin: 4px 0; font-size: 0.88rem; }
.dd-threshold-list .dd-loss-item { --sidebar-color: #f85149; }
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
.dd-anchor-tag.dd-tag-rare { background:#5a3a00; color:#ffd166; }
.dd-anchor-tag.dd-tag-rare:hover { background:#7a5200; color:#fff; }
.dd-anchor-tag.dd-tag-uncommon { background:#1a4731; color:#7ee787; }
.dd-anchor-tag.dd-tag-uncommon:hover { background:#256d4a; color:#fff; }
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
/* Atk-weight badges on Notable IV member rows. Classifies each spread
   as rank-1 / no-atk / slight / heavy / bulk-max / atk-tilt relative
   to the stat-product-max IV (RyanSwag T2 vocabulary). Muted colors
   so badges read as annotation, not emphasis. */
.dd-atk-weight { display:inline-block; padding:1px 7px; border-radius:3px;
  font-size:0.72rem; font-weight:500; text-transform:lowercase;
  margin-left:6px; letter-spacing:0.02em; cursor:help; }
.dd-atk-weight-rank-1 { background:#1e2d4a; color:#58a6ff; }
.dd-atk-weight-no-atk-weight { background:#1b2b1b; color:#7db87d; }
.dd-atk-weight-slight-atk-weight { background:#2a2617; color:#d29922; }
.dd-atk-weight-heavy-atk-weight { background:#3a1f1f; color:#e94560; }
.dd-atk-weight-bulk-max { background:#1b2a33; color:#8ed1d1; }
.dd-atk-weight-atk-tilt { background:#2a1f2a; color:#c8a2d0; }
/* Envelope-position tag (category-level, sits right after the card
   subtitle). Colored by shape: rider-top/elev = above band (green
   family), rider-bottom/dep = below band (red family). The numeric
   detail lives in the title= tooltip. */
.dd-env-tag { font-size:0.82rem; margin:2px 0 4px; padding:3px 8px;
  border-radius:3px; border-left:3px solid transparent; cursor:help;
  display:inline-block; }
.dd-env-rider-top    { background:#132a1c; color:#9be89b; border-left-color:#3fb950; }
.dd-env-elev-crosser { background:#162318; color:#7db87d; border-left-color:#2f8135; }
.dd-env-dep-crosser  { background:#2a1e16; color:#d29922; border-left-color:#b07214; }
.dd-env-rider-bottom { background:#2a181b; color:#e77173; border-left-color:#c04547; }
.dd-collapsible { margin: 4px 0; }
.dd-collapsible > summary { list-style: none; }
.dd-collapsible > summary::-webkit-details-marker { display: none; }
.dd-collapsible > summary::before { content: "\\25b6"; display: inline-block;
  margin-right: 6px; font-size: 0.7em; transition: transform 0.15s; color: #58a6ff; }
.dd-collapsible[open] > summary::before { transform: rotate(90deg); }
.dd-expert-zone { --sidebar-color: #d29922;
  padding: 10px 0 10px 20px; margin: 16px 0; }
.dd-expert-zone h3 { color: #d29922; margin: 0 0 10px 0; }
.dd-expert-source { color: #8b949e; font-size: 0.82rem; font-style: italic; margin: 0 0 12px 0; }
.dd-expert-anchors { margin: 10px 0; }
.dd-expert-anchors li { margin: 4px 0; }
.dd-narrative-zone { --sidebar-color: #9b59b6;
  padding: 12px 0 12px 20px; margin: 20px 0; }
.dd-narrative-prose { font-size: 0.9rem; color: #c8ccd4; line-height: 1.6; margin: 6px 0; }
.dd-narrative-rec { color: #3fb950; font-weight: 600; }
.dd-narrative-loss { color: #f85149; font-size: 0.88rem; font-style: italic; margin: 8px 0 4px 0; }
.dd-sim-zone { --sidebar-color: #58a6ff;
  padding: 10px 0 10px 20px; margin: 16px 0; }
.dd-sim-zone > h3 { color: #58a6ff; margin: 0 0 10px 0; }
.dd-species-narrative { margin: 20px 0; }
/* Collapsed-by-default narrative wrapper so the Plotly scatter (the
 * dive's centerpiece) lands at the top of the page; readers expand
 * for prose. The summary line sits where the old H2/H3 headers
 * would have been and inherits the same gold accent. */
.dd-species-narrative-details > summary {
  cursor: pointer;
  color: #d29922;
  font-weight: 600;
  font-size: 1.0rem;
  padding: 6px 0 6px 20px;
  list-style: none;
}
.dd-species-narrative-details > summary::-webkit-details-marker { display: none; }
.dd-species-narrative-details > summary::before {
  content: "▸ ";
  display: inline-block;
  transition: transform 0.15s ease-out;
}
.dd-species-narrative-details[open] > summary::before {
  content: "▾ ";
}
.dd-species-narrative-details > summary:hover { color: #e0ae3a; }
.dd-species-narrative .dd-narrative-block {
  --sidebar-color: #d29922;
  padding: 10px 0 10px 20px;
  margin: 8px 0;
}
.dd-species-narrative .dd-narrative-block.authored-ai {
  --sidebar-color: #e8903a;
}
.dd-species-narrative .dd-narrative-block.authored-auto {
  --sidebar-color: #5b8dd9;
}
.dd-species-narrative .dd-narrative-block > h2,
.dd-species-narrative .dd-narrative-block > h3 {
  color: var(--sidebar-color);
  margin: 0 0 8px 0;
}
.dd-species-narrative .dd-narrative-block > h2 { font-size: 1.15rem; }
.dd-species-narrative .dd-narrative-block > h3 { font-size: 1.0rem; }
.dd-species-narrative p { margin: 8px 0; }
.dd-species-narrative .narrative-attribution { color: #8b949e;
  font-size: 0.82rem; margin: 6px 0 0 0; font-style: italic; }

/* ==== Shared sidebar pattern (2026-04-19 refactor) ====
 * Any element in the selector list below gets a rounded-cap
 * pseudo-element sidebar on its left edge instead of a hand-written
 * border-left. The bar is drawn by ::before as an absolutely-
 * positioned rectangle with border-radius, inset 4px from the top
 * and bottom of the element's padding box so adjacent elements
 * with the same colour still read as distinct blocks.
 *
 * Adding a new zone class: add the class name to all three selector
 * lists (base, ::before, none for colour - use --sidebar-color
 * directly in the class's own rule), then set --sidebar-color in
 * that class's own definition. Optional: --sidebar-width override
 * (defaults to 4px) for narrower nested bars.
 *
 * Kept here as a grouped block, adjacent to each zone's
 * semantic/padding rules above, so a single grep for a zone name
 * lands on both the class definition and the shared pattern. */
.dd-expert-zone,
.dd-narrative-zone,
.dd-sim-zone,
.dd-callout,
.dd-species-narrative .dd-narrative-block,
.dd-threshold-list li {
  position: relative;
  border-left: none;
}
.dd-expert-zone::before,
.dd-narrative-zone::before,
.dd-sim-zone::before,
.dd-callout::before,
.dd-species-narrative .dd-narrative-block::before,
.dd-threshold-list li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: var(--sidebar-width, 4px);
  border-radius: calc(var(--sidebar-width, 4px) / 2);
  background: var(--sidebar-color, #8b949e);
}
"""

def parse_mode(composite_mode):
    """Decompose a composite mode string into (opp_iv_mode, bait_mode).

    Accepted forms:
      'pvpoke'           -> ('pvpoke', 'bait')     # bait-on default
      'rank1'            -> ('rank1',  'bait')
      'pvpoke:bait'      -> ('pvpoke', 'bait')
      'pvpoke:nobait'    -> ('pvpoke', 'nobait')
      'rank1:nobait'     -> ('rank1',  'nobait')
      'pvpoke:nobait:e1' -> ('pvpoke', 'nobait')   # energy tag ignored here

    Legacy callers that only know the opp-iv axis can pass
    ``'pvpoke'``/``'rank1'`` and get the bait-on default. The energy-lead
    tag (``:eN``) is parsed separately via ``parse_energy`` so the
    many existing 2-tuple call sites stay unchanged.
    """
    parts = composite_mode.split(':')
    bait = 'nobait' if 'nobait' in parts[1:] else 'bait'
    return parts[0], bait


def parse_energy(composite_mode):
    """Energy-lead axis value from a composite mode string, in FAST-MOVE
    MULTIPLES (not raw energy): 'pvpoke:e1' -> 1 means "one fast move of
    stored energy". 0 (no tag) is the cold-start default. Fast-move
    multiples keep mode keys uniform across movesets whose fast moves
    generate different energy; the sweep converts to raw energy."""
    for p in composite_mode.split(':')[1:]:
        if len(p) > 1 and p[0] == 'e' and p[1:].isdigit():
            return int(p[1:])
    return 0


def compose_mode(opp_iv_mode, bait_mode='bait', energy_lead=0):
    """Inverse of ``parse_mode``/``parse_energy``. Bait-on and energy-0
    collapse to the bare opp-iv form so existing keys (e.g.
    ``f'{mi}_pvpoke'``) stay unchanged when those axes aren't swept."""
    mode = opp_iv_mode
    if bait_mode == 'nobait':
        mode += ':nobait'
    if energy_lead:
        mode += f':e{energy_lead}'
    return mode


def mode_pretty_label(composite_mode):
    """Human-readable label for a composite mode, e.g. for dropdowns."""
    opp_iv, bait = parse_mode(composite_mode)
    opp_label = 'PvPoke Defaults' if opp_iv == 'pvpoke' else 'Rank 1'
    if bait == 'nobait':
        opp_label = f'{opp_label}, no bait'
    energy = parse_energy(composite_mode)
    if energy:
        plural = 's' if energy > 1 else ''
        opp_label = f'{opp_label}, +{energy} fast move{plural} energy'
    return opp_label


@dataclass
class IVCategory:
    """A named IV grouping with explicit provenance.

    Abstracts over the several sources of named IV groupings the deep dive
    already produces (anchor-driven slayer categories, stat-cutoff threshold
    tiers, future matchup-conditional categories) so a single renderer can
    surface them all uniformly. Composite categories (intersections of
    multiple parents) are the framework's payoff: ``13/0/11 is the rare
    bulk-floor slayer`` falls out as ``Anchors-First Slayer ∩ Top 5%``
    with one IV.

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

    # Tradeoff sentence - compute against the slayer cohort's max wins.
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
                        f"cutoff - no tradeoff.")
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
                                     toggle_id=None, top_n=10,
                                     emit_opponent_ids=False):
    """Render matchup-flipping boundaries as HTML <li> bullets.

    Format: "141.66 Def + 138 HP flips Medicham (1v1, 1v2 no bait) [85 IVs]"

    When *has_bait_axis* is True and a boundary only fires in one bait
    mode, the scenario string is annotated with "no bait" or "with bait".

    When the energy-lead axis was swept and a boundary never fires from
    a cold start (0 not in its ``energy_modes``), the scenario string is
    annotated with the minimum lead, e.g. "needs +1 fast move energy".
    No kwarg needed: without the axis every record carries
    ``energy_modes == {0}`` and the annotation stays silent.

    When *toggle_id* is set and there are more than *top_n* bullets,
    the excess are hidden behind a show/hide toggle button.

    When *emit_opponent_ids* is True, the first <li> emitted for each
    opponent carries ``id="opp-<slug>"`` so external pages (e.g. the CD
    article's Matchup Delta table) can deep-link directly to that
    opponent's first boundary bullet. Only enable at the standalone
    (section-level) call site -- the tier-card-nested call also renders
    these bullets but enabling ids in both contexts produces duplicate
    DOM ids and the browser lands in a tier card rather than the
    standalone section.
    """
    lines = []
    seen_opponents: set[str] = set()
    for i, b in enumerate(boundaries):
        scen_str = ', '.join(
            f'{s[0]}v{s[1]}' for s in sorted(b['scenarios']))
        bait_modes = b.get('bait_modes', set())
        if has_bait_axis and len(bait_modes) == 1:
            bait_tag = 'no bait' if 'nobait' in bait_modes else 'with bait'
            scen_str += f' {bait_tag}'
        energy_modes = b.get('energy_modes', set())
        if energy_modes and 0 not in energy_modes:
            _emin = min(energy_modes)
            scen_str += (f', needs +{_emin} fast move'
                         f'{"s" if _emin > 1 else ""} energy')
        hp_str = ''
        if b.get('hp_threshold') is not None:
            hp_str = (f' + <span class="dd-strong">'
                      f'{b["hp_threshold"]} HP</span>')
        stat_label = 'Atk' if b.get('stat') == 'atk' else 'Def'
        hidden = ''
        if toggle_id and i >= top_n:
            hidden = f' class="dd-iv-hidden" data-tier-card="{toggle_id}"'
        opp_id = ''
        if emit_opponent_ids and b['opponent'] not in seen_opponents:
            seen_opponents.add(b['opponent'])
            opp_id = f' id="opp-{opp_slug(b["opponent"])}"'
        lines.append(
            f'<li{hidden}{opp_id}><span class="dd-strong">'
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
    bullet and fill in a "- yours: 0/15/15, 1/14/15" annotation.
    """
    import hashlib as _hl
    key = '|'.join(str(x) for x in (parent, opponent, target_stat, move_id or ''))
    return 'af-' + _hl.md5(key.encode('utf-8')).hexdigest()[:10]


def opp_slug(name: str) -> str:
    """Slugify an opponent display name for deep-link anchor ids.

    'Stunfisk (Galarian)' -> 'stunfisk-galarian'. Shared with
    ``generate_article.py`` so the
    article's Matchup Delta opponent links land on the matching
    ``#opp-<slug>`` id inside the dive's standalone Matchup-Flipping
    Boundaries / Anchor-Driven Matchup Flips sections.
    """
    return re.sub(r'^-|-$', '',
                  re.sub(r'[^a-z0-9]+', '-', name.lower()))


def render_species_narrative(narrative: dict) -> str:
    """Render the per-species editorial narrative zone for a dive.

    Consumes free-form prose from the threshold TOML's species table:

        [Species.intro]        body = "..."
        [Species.meta_role]    good_at / bad_at / team_role / body
        [Species.verdict]      editorial / outlook

    Field shape mirrors the article TOML's same-named blocks exactly, so
    prose can migrate from `articles/<slug>.toml` to
    `thresholds/<species>.toml` with no rewriting. Each block supports the
    same optional `author = "..."` attribution field (see
    ``render_article.format_block_attribution``) so AI-drafted prose is
    visually distinguishable from human-authored prose.

    Render position is the top of the dive (above the interactive
    scatter/dashboard), matching RyanSwag's lead-with-why pattern.
    Styled as ``dd-species-narrative`` - gold left border, same visual
    weight as the downstream gold ``dd-expert-zone`` so a reader
    recognizes the two as the same editorial register.

    Returns an empty string when none of the three sub-blocks are
    populated. The caller skips the wrapper entirely in that case so
    dives without narrative (most species today) render unchanged.
    """
    if not narrative:
        return ''

    intro_block = narrative.get('intro') or {}
    meta_role_block = narrative.get('meta_role') or {}
    verdict_block = narrative.get('verdict') or {}

    intro_body = (intro_block.get('body') or '').strip()
    mr_body_override = (meta_role_block.get('body') or '').strip()
    mr_field_parts = []
    # ``wrap`` appended last so the Meta Role block ends with the F8
    # closing-sentence synthesis (STYLE_CONFORMANCE C11).
    for field in ('good_at', 'bad_at', 'team_role', 'wrap'):
        txt = (meta_role_block.get(field) or '').strip()
        if txt:
            mr_field_parts.append(txt)
    mr_has_content = bool(mr_body_override or mr_field_parts)
    verdict_editorial = (verdict_block.get('editorial') or '').strip()
    verdict_outlook = (verdict_block.get('outlook') or '').strip()
    verdict_has_content = bool(verdict_editorial or verdict_outlook)

    if not (intro_body or mr_has_content or verdict_has_content):
        return ''

    # Build the summary label from the blocks actually present so the
    # collapsed state tells the reader what's hidden. Default-closed so
    # the Plotly scatter (the dive's centerpiece) is immediately
    # visible at the top of the page; one click expands the prose.
    present_labels = []
    if intro_body:
        present_labels.append('Overview')
    if mr_has_content:
        present_labels.append('Meta Role')
    if verdict_has_content:
        present_labels.append('Verdict')
    summary_text = ' · '.join(present_labels) if present_labels else 'Species overview'

    parts = ['<section class="dd-species-narrative">\n']
    parts.append('<details class="dd-species-narrative-details">\n')
    parts.append(f'<summary>{summary_text}</summary>\n')

    if intro_body:
        parts.append(f'<div class="dd-narrative-block {_authored_by_class(intro_block)}">\n')
        parts.append('<h2>Overview</h2>\n')
        parts.append(format_body(intro_body))
        parts.append('\n')
        parts.append(format_block_attribution(intro_block))
        parts.append('\n</div>\n')

    if mr_has_content:
        parts.append(f'<div class="dd-narrative-block {_authored_by_class(meta_role_block)}">\n')
        parts.append('<h3>Meta Role</h3>\n')
        if mr_body_override:
            parts.append(format_body(mr_body_override))
        else:
            parts.append(format_body('\n\n'.join(mr_field_parts)))
        parts.append('\n')
        parts.append(format_block_attribution(meta_role_block))
        parts.append('\n</div>\n')

    if verdict_has_content:
        parts.append(f'<div class="dd-narrative-block {_authored_by_class(verdict_block)}">\n')
        parts.append('<h3>Verdict</h3>\n')
        joined = []
        if verdict_editorial:
            joined.append(verdict_editorial)
        if verdict_outlook:
            joined.append(verdict_outlook)
        parts.append(format_body('\n\n'.join(joined)))
        parts.append('\n')
        parts.append(format_block_attribution(verdict_block))
        parts.append('\n</div>\n')

    parts.append('</details>\n')
    parts.append('</section>\n')
    return ''.join(parts)


def _authored_by_class(block: dict) -> str:
    """Map the optional ``authored_by`` enum to a CSS modifier class.

    Values: ``"human"`` (default, gold), ``"ai"`` (orange),
    ``"mixed"`` (gold - a human co-signed so treat as human register),
    ``"auto"`` (blue - deterministically data-derived from dive data
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


def render_anchor_flip_bullets(records, anchor_passing_sink=None,
                               has_bait_axis=False,
                               emit_opponent_ids=False,
                               strip_bulk_suffix=False):
    """Render anchor-flip records as RyanSwag-style HTML <li> bullets.

    Grouping grain is ``(parent, opponent, target_stat, move_id)``.
    Within each group we take the *minimum* threshold value: Level 3
    parents expand into one sub-anchor per (move, damage tier), and a
    higher-tier sub-anchor is automatically subsumed by its lower-tier
    sibling for matchup-flipping purposes (anything that crosses the
    high tier necessarily crosses the low one). The min threshold is
    "the smallest stat at which this move starts driving any flip
    against this opponent" - the actionable number.

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
    "- yours: a/d/s, a/d/s" after a Poke Genie CSV is loaded.
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
    seen_opponents: set[str] = set()
    for family in family_order:
        for key in families[family]:
            recs = groups[key]
            first = recs[0]['anchor']
            stat_label = 'Atk' if first.target_stat == 'atk' else 'Def'
            anchor_label = first.parent_display_name or first.label or first.parent
            # B2: drop the trailing " bulk" disambiguator when rendered
            # inside a tier card whose only target axis is def. The
            # suffix exists to distinguish brkp from blkp inside the
            # Bulk Slayer card (where both can appear); a def-only tier
            # card has no breakpoint risk to disambiguate against.
            if strip_bulk_suffix and anchor_label.endswith(' bulk'):
                anchor_label = anchor_label[: -len(' bulk')]

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

            # Energy-lead: annotate flips that never fire from a cold
            # start (kwarg-free — see render_matchup_boundary_bullets).
            energy_union = set()
            for r in recs:
                energy_union |= r.get('energy_modes', set())
            if energy_union and 0 not in energy_union:
                _emin = min(energy_union)
                scen_strs += (f', needs +{_emin} fast move'
                              f'{"s" if _emin > 1 else ""} energy')

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
            opp_id = ''
            if emit_opponent_ids and opp_name not in seen_opponents:
                seen_opponents.add(opp_name)
                opp_id = f' id="opp-{opp_slug(opp_name)}"'
            lines.append(
                f'<li{opp_id}><span class="dd-strong">{min_thresh:.2f} {stat_label}</span>'
                f'{hp_str} '
                f'for <b style="color:{opp_c}">{anchor_label}</b>'
                f'{move_str} vs {_opp_b(opp_name)} '
                f'(<span class="dd-gain">{scen_strs}</span>)'
                f'{anchor_span}</li>'
            )
    return lines




_ENV_SHAPE_LABEL = {
    'envelope-rider-top':     'Rides top of anchor band',
    'envelope-rider-bottom':  'Rides bottom of anchor band',
    'elevated-band-crosser':  'Straddles band (net +)',
    'depressed-band-crosser': 'Straddles band (net -)',
    'sparse':                 None,
}
_ENV_SHAPE_SLUG = {
    'envelope-rider-top':     'rider-top',
    'envelope-rider-bottom':  'rider-bottom',
    'elevated-band-crosser':  'elev-crosser',
    'depressed-band-crosser': 'dep-crosser',
}


def _render_envelope_tag(env_entry):
    """Compact category-level envelope-position annotation for a card.

    Returns an HTML `<p>` (or empty string for sparse / missing data).
    Five possible shapes from deep_dive_analysis.compute_envelope_positions;
    'sparse' skips rendering because too-few-members/anchors means the
    metric is unreliable, not informational.
    """
    if not env_entry:
        return ''
    shape = env_entry.get('shape')
    label = _ENV_SHAPE_LABEL.get(shape)
    if not label:
        return ''
    slug = _ENV_SHAPE_SLUG.get(shape, 'default')
    mean_d = env_entry.get('mean_delta', 0.0)
    spread = env_entry.get('spread', 0.0)
    n_members = env_entry.get('n_members', 0)
    n_anchors = env_entry.get('n_anchors', 0)
    sign = '+' if mean_d >= 0 else ''
    tip = (f'Avg battle-score delta vs the anchor-IV band at matching '
           f'stat-product rank. {sign}{mean_d:.1f} average, spread '
           f'{spread:.1f} (stdev) across {n_members} members and '
           f'{n_anchors} anchor IVs.')
    tip_attr = tip.replace('"', '&quot;')
    return (f'<p class="dd-env-tag dd-env-{slug}" title="{tip_attr}">'
            f'<b>Envelope:</b> {label} '
            f'<span class="dd-small" style="font-weight:400">'
            f'(avg {sign}{mean_d:.1f}, spread {spread:.1f})'
            f'</span></p>\n')


def render_notable_ivs_section(categories, data_obj, opp_iv_mode,
                                  notable_max_pct=0.05,
                                  notable_max_count=5,
                                  max_members_shown=5,
                                  envelope_positions=None,
                                  recommendations_html=''):
    """Render the "Notable IVs" HTML section from a list of IVCategory.

    Surfaces composite (slayer ∩ tier) and matchup categories - the
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
        notable_max_pct: float - categories with member count <= this
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

    # Per-card slug is derived from the category name so external pages
    # (CD article IV Recommendations, cross-species comparisons) can
    # deep-link to a specific card with a stable href. Name-derived
    # slugs survive reordering of the category list across re-dives
    # (unlike the old uid counter). A uid counter is kept only as a
    # disambiguator when two category names slugify to the same string.
    card_uid = 0
    seen_slugs: set[str] = set()

    # Sort: composites first (the headline), then matchups, with smaller
    # categories first within each kind so the most distinctive cards
    # land at the top of the grid.
    kind_order = {'composite': 0, 'matchup': 1}
    target.sort(key=lambda c: (kind_order.get(c.kind, 99), len(c.members), c.name))

    # Rank-1 (stat-product-max) IV for the atk-weight badge classifier.
    # Only emitted when spRanks is available; spRanks entries are 1-
    # indexed (1 == stat-product-max). Fall back silently if the array
    # is missing so older data-objs still render.
    _sp_ranks = data_obj.get('spRanks') or []
    _rank1_idx: Optional[int] = None
    for _i, _r in enumerate(_sp_ranks):
        if _r == 1:
            _rank1_idx = _i
            break
    _rank1_stats = None
    if _rank1_idx is not None:
        _rank1_stats = {
            'atk': data_obj['ivAtk'][_rank1_idx],
            'def': data_obj['ivDef'][_rank1_idx],
            'sta': data_obj['ivHp'][_rank1_idx],
        }

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
        'threshold tier - the rare intersections that trade some '
        'slayer optimum for a broader-meta floor (or vice versa). '
        'Matchup cards surface non-trivial '
        '(opponent,&nbsp;scenario)&nbsp;partitions for selective '
        'matchups. Pure slayer-archetype cards live in the Slayer '
        'Builds block below; pure tier cards in the Threshold Tiers '
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
        name_slug = opp_slug(cat.name)
        if not name_slug or name_slug in seen_slugs:
            name_slug = f'{name_slug or "cat"}-{card_uid}'
        seen_slugs.add(name_slug)
        card_id = f'notable-{name_slug}'
        parts.append(f'<div class="dd-rec-card {notable_cls}" id="{card_id}">\n')
        parts.append(
            f'<h4>{cat.name} '
            f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
            f'({n_members} IV spread{"s" if n_members != 1 else ""})'
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

        # Envelope-position annotation (S4/P3): category-level summary
        # of how this card's members sit vs the anchor-IV band at the
        # same stat-product rank. Only present when the caller passed an
        # envelope_positions dict (i.e., anchor band and avg_scores were
        # available at compute time). Skipped on matchup cards because
        # those categories are typically huge (thousands of members) with
        # tiny mean deltas - the envelope metric is designed for small,
        # curated categories (composite, tier, structural) where the
        # distinction vs the anchor band is diagnostic.
        if envelope_positions and cat.kind != 'matchup':
            env_html = _render_envelope_tag(envelope_positions.get(cat.name))
            if env_html:
                parts.append(env_html)

        # Member list - sort by total_wins desc when available, else
        # by IV index. Render every member; rows past max_members_shown
        # get the dd-iv-hidden class and the expand button toggles
        # dd-iv-shown on them (matching the slayer-card pattern).
        def _sort_key(idx):
            wins = cat.member_meta.get(idx, {}).get('total_wins', 0)
            return (-wins, idx)
        members_sorted = sorted(cat.members, key=_sort_key)

        # Scanner export (2026-06-11; format confirmed from gobattlekit's
        # user-thresholds loader): per-card copy button emitting a
        # paste-ready JSON fragment in the shared check_thresholds schema
        # {species: {League: {card-name: spec}}}. Composite cards export
        # their stat cutoffs; matchup (and cutoff-less) cards export the
        # EXPLICIT member IV list -- but only up to 300 members: a
        # truncated scanner spec silently misses owned mons, so beyond
        # that the button is omitted rather than wrong (huge matchup
        # cards aren't meaningful scan targets anyway).
        _species = data_obj.get('species') or 'Species'
        _league_t = (data_obj.get('league') or 'great').capitalize()
        _spec = None
        if cat.kind == 'composite' and cat.stat_cutoffs:
            _spec = {
                'attack': round(float(cat.stat_cutoffs.get('atk', 0) or 0), 2),
                'defense': round(float(cat.stat_cutoffs.get('def', 0) or 0), 2),
                'stamina': int(cat.stat_cutoffs.get('hp', 0) or 0),
            }
        elif n_members <= 300:
            _spec = {
                'attack': 0, 'defense': 0, 'stamina': 0,
                'ivs': [[data_obj['ivA'][m], data_obj['ivD'][m],
                         data_obj['ivS'][m]] for m in members_sorted],
            }
        if _spec is not None:
            _scanner_json = _html.escape(
                json.dumps({_species: {_league_t: {cat.name: _spec}}}),
                quote=True)
            parts.append(
                f'<button class="dd-iv-toggle" style="margin:2px 0 6px 0" '
                f'data-scanner-json="{_scanner_json}" '
                f'onclick="copyScannerJson(this)" '
                f'title="Copy this card as a gobattlekit user-threshold '
                f'JSON fragment (paste into the IV scanner)">'
                f'Copy for IV scanner</button>\n'
            )

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
            badge = ''
            if _rank1_stats is not None:
                _weight = classify_atk_weight(
                    {'atk': atk, 'def': def_, 'sta': hp},
                    _rank1_stats,
                )
                _slug = _weight.replace(' ', '-')
                _tip = atk_weight_tip(_weight)
                badge = (f' <span class="dd-atk-weight '
                         f'dd-atk-weight-{_slug}"{tooltip_attr(_tip)}>'
                         f'{_weight}</span>')
            parts.append(
                f'<p{row_cls}><b>{label}</b>{badge} - '
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
        '(Def or Atk) ascending - read top-to-bottom in the order a '
        'player would clear them as their stat grows. The flat list of '
        'every anchor (regardless of tier) lives in <em>Anchor-Driven '
        'Matchup Flips</em> below. New to tier cards? The '
        '<a href="../guides/threshold-tiers/">Threshold Tiers guide</a> '
        'walks through what the stat cutoffs and member counts mean. '
        'A tier\'s anchors come from two passes over the anchor list:</p>\n'
        '<ul class="dd-small" style="margin-top:2px">\n'
        '<li><b>Primary bullets</b> - the tier has a cutoff on the '
        "anchor's target axis (atk or def) that meets or exceeds the "
        'anchor\'s threshold. Consequences:\n'
        '<ul>\n'
        '<li><i>Subset case:</i> if tier A is strictly stricter than '
        'tier B on the anchor axis, A\'s bullet list is a superset of '
        'B\'s. Overlap is intentional.</li>\n'
        '<li><i>Crossed-cutoff case:</i> tier A has only an atk cutoff, '
        'tier B has only a def cutoff - neither is a subset of the '
        'other. Atk anchors appear only on A; def anchors only on B.</li>\n'
        '<li><i>Slayer-axis IV-count case:</i> two tiers can list the '
        'same atk anchor but have different member-IV counts because a '
        'stricter tier\'s def cutoff excludes def-sacrificing spreads '
        'that the looser tier keeps. Check the (−N vs parent) callout '
        'on the tier header to spot this at a glance.</li>\n'
        '</ul></li>\n'
        '<li><b>Anchors we get for free</b> (collapsed) - the tier has '
        'no cutoff on the anchor\'s target axis, but every IV in the '
        'tier clears the anchor\'s threshold anyway. These would be '
        'silently dropped by the primary filter; we surface them in a '
        'separate collapsed block so the card isn\'t misleading.</li>\n'
        '</ul>\n'
    )
    parts.append('<div class="dd-rec-grid">\n')

    # --- First pass: compute tier_ivs for every tier so we can detect
    # parent/superset relationships in the main pass.
    tier_ivs_by_idx: list = []
    tier_cutoffs_by_idx: list = []
    for ti_pre, t_pre in enumerate(tiers):
        atk_cut_p = t_pre.get('attack', 0) or 0
        def_cut_p = t_pre.get('defense', 0) or 0
        hp_cut_p = t_pre.get('stamina', 0) or 0
        tier_cutoffs_by_idx.append((atk_cut_p, def_cut_p, hp_cut_p))
        if iv_tiers_precomputed is not None:
            tier_ivs_p = [iv for iv in range(n_ivs)
                          if iv_tiers_precomputed[iv] == ti_pre]
        else:
            tier_ivs_p = []
            for iv in range(n_ivs):
                meets = True
                if atk_cut_p > 0 and data_obj['ivAtk'][iv] < atk_cut_p:
                    meets = False
                if def_cut_p > 0 and data_obj['ivDef'][iv] < def_cut_p:
                    meets = False
                if hp_cut_p > 0 and data_obj['ivHp'][iv] < hp_cut_p:
                    meets = False
                if meets:
                    tier_ivs_p.append(iv)
        tier_ivs_by_idx.append(set(tier_ivs_p))

    for ti, t in enumerate(tiers):
        atk_cut, def_cut, hp_cut = tier_cutoffs_by_idx[ti]
        cutoff_bits = []
        if atk_cut > 0:
            cutoff_bits.append(f'atk≥{atk_cut:.2f}')
        if def_cut > 0:
            cutoff_bits.append(f'def≥{def_cut:.2f}')
        if hp_cut > 0:
            cutoff_bits.append(f'hp≥{hp_cut:g}')
        cutoffs_str = ', '.join(cutoff_bits) if cutoff_bits else 'no cutoff'

        tier_ivs = sorted(tier_ivs_by_idx[ti])
        n_members = len(tier_ivs)
        tier_iv_set = tier_ivs_by_idx[ti]

        # --- Filter 1: primary records - tier has a cutoff on the
        # anchor's axis that meets/exceeds the threshold.
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

        # --- Filter 2: "anchors we get for free" - tier has no cutoff on
        # the anchor's axis, but every IV in tier_ivs still clears the
        # threshold. Empty tiers skip this (vacuous-truth avoidance).
        free_records = []
        if tier_ivs:
            # Build a set of primary (parent, opponent, target_stat, move_id)
            # keys so we don't duplicate a bullet that's already primary.
            primary_keys = {
                (r['anchor'].parent, r['opponent'],
                 r['anchor'].target_stat, r['anchor'].move_id)
                for r in tier_records
            }
            for rec in anchor_flip_records:
                a = rec['anchor']
                tv = getattr(a, 'threshold_value', None)
                if tv is None:
                    continue
                stat = a.target_stat
                # Only consider axes where the tier has NO cutoff.
                if stat == 'atk' and atk_cut > 0:
                    continue
                if stat == 'def' and def_cut > 0:
                    continue
                key = (a.parent, rec['opponent'], stat, a.move_id)
                if key in primary_keys:
                    continue
                # Check every IV in tier clears this threshold.
                stat_arr = (data_obj['ivAtk'] if stat == 'atk'
                            else data_obj['ivDef'] if stat == 'def'
                            else None)
                if stat_arr is None:
                    continue
                if all(stat_arr[iv] >= tv for iv in tier_ivs):
                    free_records.append(rec)

        # --- Parent-tier diff: find the smallest strict superset tier and
        # compute the IV-count delta. Used for a "−N IVs vs ParentName"
        # header callout that exposes the slayer-axis case.
        parent_idx = None
        parent_size = None
        for tj in range(len(tiers)):
            if tj == ti:
                continue
            other = tier_ivs_by_idx[tj]
            if len(other) <= n_members:
                continue
            if tier_iv_set.issubset(other):
                if parent_size is None or len(other) < parent_size:
                    parent_size = len(other)
                    parent_idx = tj
        parent_diff_html = ''
        if parent_idx is not None and parent_size is not None:
            delta = parent_size - n_members
            parent_name = tiers[parent_idx].get('name', f'tier {parent_idx}')
            # Identify which axes this tier tightens vs the parent.
            p_atk, p_def, p_hp = tier_cutoffs_by_idx[parent_idx]
            tighter_axes = []
            if atk_cut > 0 and (p_atk == 0 or atk_cut > p_atk):
                tighter_axes.append('atk-sacrificing')
            if def_cut > 0 and (p_def == 0 or def_cut > p_def):
                tighter_axes.append('def-sacrificing')
            if hp_cut > 0 and (p_hp == 0 or hp_cut > p_hp):
                tighter_axes.append('hp-low')
            axis_note = ''
            if tighter_axes:
                axis_note = f' ({" / ".join(tighter_axes)} spreads excluded)'
            parent_diff_html = (
                f' <span class="dd-small" '
                f'style="font-weight:400;color:#d29922" '
                f'title="This tier is a strict subset of the '
                f'&quot;{parent_name}&quot; tier on IV membership. '
                f'The primary-bullet list may look similar, but '
                f'member IVs differ.">'
                f'(−{delta} vs {parent_name}{axis_note})</span>'
            )

        color = t.get('color', '#888')
        # Slug for the "N of yours qualify" placeholder. Must match the
        # JS computation in deep_dive_engine.js updateTierCardCounts.
        # Slug off ``original_name`` when present so the anchor id stays
        # stable across the 2026-04-23 tier-name unify, where the badge
        # text (t['name']) flips from "Lapras Atk" to "Lapras Slayer" but
        # the deep-link slug "tier-card-lapras-atk" needs to keep
        # matching the article-side ``_tier_card_href`` computation.
        import re as _re
        _slug_source = (t.get('original_name') or t.get('name') or '').lower()
        _tier_slug = _re.sub(r'^-|-$', '',
                             _re.sub(r'[^a-z0-9]+', '-', _slug_source))
        # Anchor id on the visible card container so external pages (e.g.
        # the CD article) can deep-link directly to a tier card. The
        # ``tier-card-yours-`` span below is paste-box machinery and is
        # display:none until populated, so it cannot be a scroll target.
        parts.append(
            f'<div class="dd-rec-card" id="tier-card-{_tier_slug}">\n'
        )
        parts.append(
            f'<h4>'
            f'<span class="dd-badge" style="background:{color};color:#000">'
            f'{t["name"]}</span> '
            f'<span class="dd-small" style="font-weight:400;color:#b0b8c4">'
            f'· {cutoffs_str}</span> '
            f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
            f'({n_members} IV spread{"s" if n_members != 1 else ""})'
            f'</span>'
            f'{parent_diff_html} '
            f'<span id="tier-card-yours-{_tier_slug}" '
            f'class="dd-small" '
            f'style="font-weight:400;color:#ff40ff;display:none"></span>'
            f'</h4>\n'
        )
        # --- Goal line from the TOML `description` field ---
        # Rendered first, styled as the authored goal statement (mirrors
        # the Flavor Guide's tone). Distinct from the auto-generated
        # "Clears N anchors ..." summary below, which is a mechanical
        # count.
        toml_desc = (t.get('toml_description') or '').strip()
        if toml_desc:
            parts.append(
                f'<p class="dd-prose" style="color:#d29922;font-style:italic;'
                f'margin-bottom:4px">Goal: {toml_desc}</p>\n'
            )

        # --- Auto-generated prose summary for the card ---
        if tier_records:
            # Collect unique opponents whose anchors this tier clears
            tier_opps = sorted({r['opponent'] for r in tier_records})
            # Count only - no sink here; the actual rendered bullets
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
            # B2: in a def-only tier card (no atk cutoff), every bullet
            # is a bulkpoint by construction, so the " bulk" suffix on
            # each anchor label is redundant noise. Strip it. Bulk
            # Slayer card (render_notable_ivs_section) and the flat
            # Anchor-Driven Matchup Flips section keep the suffix
            # because they can mix brkp + blkp anchors.
            _strip_bulk = (def_cut > 0 and atk_cut == 0)
            bullets = render_anchor_flip_bullets(
                tier_records, anchor_passing_sink=anchor_passing_sink,
                has_bait_axis=has_bait_axis,
                strip_bulk_suffix=_strip_bulk)
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

        # --- "Anchors we get for free" - anchors on axes this tier
        # doesn't cutoff, but every IV in tier clears anyway. Collapsed.
        if free_records:
            free_bullets = render_anchor_flip_bullets(
                free_records, has_bait_axis=has_bait_axis)
            if free_bullets:
                free_top_n = 3
                free_uid = f'dd-tier-free-{ti}'
                parts.append(
                    f'<details class="dd-flip-detail" '
                    f'style="margin-top:6px">'
                    f'<summary><b style="color:#58a6ff">'
                    f'Anchors we get for free</b> '
                    f'<span class="dd-small" style="color:#8b949e">'
                    f'({len(free_bullets)} cleared by every IV in this tier '
                    f'despite no cutoff on the relevant axis)'
                    f'</span></summary>\n'
                )
                n_vis_free = min(len(free_bullets), free_top_n)
                parts.append('<ul class="dd-threshold-list">\n')
                parts.append('\n'.join(free_bullets[:n_vis_free]))
                if len(free_bullets) > free_top_n:
                    for b in free_bullets[free_top_n:]:
                        parts.append(
                            f'\n<li class="dd-iv-hidden" '
                            f'data-tier-card="{free_uid}">{b[4:]}'
                        )
                    parts.append('\n</ul>\n')
                    n_hidden_free = len(free_bullets) - free_top_n
                    parts.append(
                        f'<button class="dd-slayer-toggle" '
                        f'onclick="(function(btn){{'
                        f'var items=document.querySelectorAll('
                        f'\'[data-tier-card=\\&quot;{free_uid}\\&quot;]\');'
                        f'var shown=items.length>0&&items[0].classList.contains(\'dd-iv-shown\');'
                        f'items.forEach(function(r){{r.classList.toggle(\'dd-iv-shown\',!shown);}});'
                        f'btn.textContent=shown'
                        f'?\'Show all {len(free_bullets)} free anchors\''
                        f':\'Collapse to top {n_vis_free}\';'
                        f'}})(this)">Show all {len(free_bullets)} free anchors</button>\n'
                    )
                else:
                    parts.append('\n</ul>\n')
                parts.append('</details>\n')

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
                # A boundary with an HP rider is covered only when the tier
                # ALSO constrains HP at or above it. A tier with NO HP
                # cutoff used to pass this filter and claim coverage of
                # e.g. "141.66 Def + 138 HP" boundaries its sub-138-HP
                # members don't actually flip (2026-06-11 review, R5).
                if mb_hp is not None and (hp_cut <= 0 or hp_cut < mb_hp):
                    continue  # tier doesn't (sufficiently) constrain HP
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
                        'anchor - may involve HP or multi-stat interactions):'
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
            # Per-shield Score Δ vs rank-1 (0v0, 1v1, 2v2). Uses the
            # pvpoke-default / bait-on score mode; dropdown reactivity
            # to Shields / Opp-IV / Bait is future XL-candy-tool work
            # (see TODO.md "Pre-ship: XL-candy-decision tool" + the
            # JS-populated Mirror CMP % / Score Δ plan).
            _target_scens = [(0, 0), (1, 1), (2, 2)]
            _target_scen_labels = ['0v0', '1v1', '2v2']
            _scen_list = [tuple(s) for s in data_obj.get('scenarios', [])]
            _target_scen_idx = []
            for pair in _target_scens:
                try:
                    _target_scen_idx.append(_scen_list.index(pair))
                except ValueError:
                    _target_scen_idx.append(None)
            _scores_flat = (score_arrays.get(f'{moveset_idx}_pvpoke')
                            if score_arrays else None)
            _n_opps = data_obj.get('nOpponents', 0)
            _n_scen = len(_scen_list)
            _rank1_iv = data_obj.get('rank1RefIvIdx')
            _per_scen_rank1: list = [None, None, None]
            _have_per_shield = (_scores_flat is not None
                                and _rank1_iv is not None
                                and _n_opps > 0)
            if _have_per_shield:
                for i, si in enumerate(_target_scen_idx):
                    if si is None:
                        continue
                    base = _rank1_iv * _n_scen * _n_opps + si * _n_opps
                    s = sum(_scores_flat[base + oi] for oi in range(_n_opps))
                    _per_scen_rank1[i] = s / _n_opps
            # Column count: 6 fixed + 3 per-shield (if available).
            n_cols = 9 if _have_per_shield else 6
            parts.append('<table class="dd-table dd-narrow">\n')
            if _have_per_shield:
                _shield_header = ''.join(
                    f'<th title="Avg score minus the rank-1-by-stat-product '
                    f'IV\'s avg score, both at the {lbl} shield scenario. '
                    f'Positive = this IV outscores rank-1 in {lbl}.">'
                    f'{lbl} Δ</th>'
                    for lbl in _target_scen_labels
                )
            else:
                _shield_header = ''
            parts.append(
                '<tr><th>IV</th><th>Atk</th><th>Def</th><th>HP</th>'
                '<th>Avg rank</th>'
                '<th title="Matchup wins gained minus lost vs the '
                'PvPoke default reference IV. Hover each cell for '
                'the gain/loss breakdown.">Net flips</th>'
                f'{_shield_header}</tr>\n'
            )
            n_to_render = min(len(tier_ivs), max_members_rendered)
            n_truncated = len(tier_ivs) - n_to_render
            for row_i, iv in enumerate(tier_ivs[:n_to_render]):
                triple = (data_obj['ivA'][iv], data_obj['ivD'][iv],
                          data_obj['ivS'][iv])
                _g, _l, net = flip_map.get(iv, (0, 0, 0))
                nc = 'dd-gain' if net > 0 else ('dd-loss' if net < 0 else '')
                # Build hover text with matchup names when available.
                # Full list (no truncation) so mirror-specific matchups
                # like "Tinkaton 1v1" / "Tinkaton 2v2" land visibly
                # instead of being hidden behind a "+N more" tail - the
                # person-deciding-which-IV-to-build needs every flip
                # entry to distinguish lead-vs-closer builds.
                fd = (flips_detail or {}).get(iv)
                if fd:
                    hover_lines = []
                    if fd.get('gains'):
                        gain_names = [f"{e['opponent']} {e['scenario']}"
                                      for e in fd['gains']]
                        hover_lines.append(f"Gained: {', '.join(gain_names)}")
                    if fd.get('losses'):
                        loss_names = [f"{e['opponent']} {e['scenario']}"
                                      for e in fd['losses']]
                        hover_lines.append(f"Lost: {', '.join(loss_names)}")
                    flip_hover = '\n'.join(hover_lines) if hover_lines else f'net {net:+d}'
                else:
                    flip_hover = (f'+{_g} gained, -{_l} lost vs reference IV '
                                  f'(net {net:+d})')
                # Per-shield Δ cells.
                _shield_cells = ''
                if _have_per_shield:
                    for i, si in enumerate(_target_scen_idx):
                        if si is None or _per_scen_rank1[i] is None:
                            _shield_cells += '<td class="dd-small">-</td>'
                            continue
                        base = iv * _n_scen * _n_opps + si * _n_opps
                        s = sum(_scores_flat[base + oi] for oi in range(_n_opps))
                        iv_avg = s / _n_opps
                        d = iv_avg - _per_scen_rank1[i]
                        cls = ('dd-gain' if d > 0.05
                               else ('dd-loss' if d < -0.05 else ''))
                        _shield_cells += f'<td class="{cls}">{d:+.1f}</td>'
                row_cls = (' class="dd-slayer-hidden"'
                           if row_i >= max_members_shown else '')
                parts.append(
                    f'<tr{row_cls}>'
                    f'<td>{triple[0]}/{triple[1]}/{triple[2]}</td>'
                    f'<td>{data_obj["ivAtk"][iv]:.2f}</td>'
                    f'<td>{data_obj["ivDef"][iv]:.2f}</td>'
                    f'<td>{data_obj["ivHp"][iv]}</td>'
                    f'<td>#{avg_ranks[iv]}</td>'
                    f'<td class="{nc}"{tooltip_attr(flip_hover)}>'
                    f'{net:+d}</td>'
                    f'{_shield_cells}</tr>\n'
                )
            if n_truncated > 0:
                parts.append(
                    f'<tr class="dd-slayer-hidden"><td colspan="{n_cols}" '
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
        top = ranked[:50]
        ntop = len(top) or 1   # divide by the actual count, not a literal 50
        pop_atk = sum(data['ivAtk'][iv] for iv in top) / ntop
        pop_def = sum(data['ivDef'][iv] for iv in top) / ntop
        pop_hp = sum(data['ivHp'][iv] for iv in top) / ntop

        # Which stat differs most?
        diffs = [('Atk', gain_atk - pop_atk, gain_atk),
                 ('Def', gain_def - pop_def, gain_def),
                 ('HP', gain_hp - pop_hp, gain_hp)]
        dominant = max(diffs, key=lambda x: abs(x[1]))

        # Minimum interesting difference: 0.5 for the continuous stats,
        # a full point for integer HP. (The old rule exempted HP from
        # suppression entirely, so a 0.2-HP "preference" printed as
        # "favors higher HP" — 2026-06-11 review, R13.)
        min_delta = 1.0 if dominant[0] == 'HP' else 0.5
        if abs(dominant[1]) < min_delta:
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
            f'<li><b style="color:{opp_c}">{opp} {scene}</b> - '
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

def _parent_clear_stats(rows):
    """Per-parent clear rates over a table's emitted rows.

    Returns (rates, saturated): rates maps parent -> fraction of rows
    clearing at least one of its sub-anchors; saturated is the set of
    parents cleared by EVERY row. Feeds the signal-loss remedy
    (2026-06-11, Michael's 4+3 hybrid pick): saturated parents are
    hoisted into a single "every build clears" callout instead of
    repeating on each row, and the remaining badges are rarity-coded.
    """
    n = len(rows)
    if n == 0:
        return {}, set()
    counts: dict = {}
    for r in rows:
        for parent, subs in (r.get('_anchor_tags', {}) or {}).items():
            if subs:
                counts[parent] = counts.get(parent, 0) + 1
    rates = {p: c / n for p, c in counts.items()}
    saturated = {p for p, c in counts.items() if c == n}
    return rates, saturated


def _anchor_tags_cell(r, parent_rates=None, skip_parents=None):
    """Badge-wall HTML + cell-level summary tooltip for a row's anchor tags.

    One badge per parent anchor. Badge VISIBLE TEXT uses
    derive_short_name() -- typically 3-6 characters (e.g. "lic", "mirb",
    "lic^lur", "c:lur"). The badge HOVER tooltip carries the long form
    (parent_display_name) plus the per-sub-anchor labels (e.g.
    "close_combat->125, rage_fist->78"), so the abbreviation stays
    decipherable. The returned cell title is a one-line summary (parent
    count + kind breakdown) rather than a per-parent dump.

    Returns (tags_cell_html, cell_title_text).
    """
    tag_bits = []
    n_parents_by_kind = {'damage_breakpoint': 0, 'bulkpoint': 0, 'cmp': 0}
    n_total_subs = 0
    n_skipped = 0
    anchor_tags = r.get('_anchor_tags', {}) or {}
    for parent in sorted(anchor_tags.keys()):
        subs = anchor_tags[parent]
        if not subs:
            continue
        if skip_parents and parent in skip_parents:
            # Saturated parent: hoisted into the table-level
            # "every build below clears" callout (option 4).
            n_skipped += 1
            continue
        labels = sorted({s_.label or s_.name for s_ in subs})
        long_name = (subs[0].parent_display_name or parent)
        short = derive_short_name(parent)
        n_subs = len(labels)
        if n_subs == 1:
            badge_text = short
            sub_labels_text = labels[0]
            # Single-sub-anchor parents (Level 1, Level 2, CMP): no count
            # suffix; the tooltip leads with "clears <single sub-anchor>".
            hover_first_line = f'{long_name} · clears {sub_labels_text}'
        else:
            badge_text = (f'{short}<span class="dd-anchor-tag-count">'
                          f'×{n_subs}</span>')
            sub_labels_text = ", ".join(labels)
            # Level 3 discover-mode parents: badge shows "<short>xN"; the
            # tooltip explains that xN means "this IV passes N of the
            # parent's sub-anchors" so the abbreviation isn't cryptic.
            hover_first_line = f'{long_name} · clears {n_subs} sub-anchors'
        rate = (parent_rates or {}).get(parent)
        rarity_cls = ''
        rate_line = ''
        if rate is not None:
            # Rarity coding (option 3): the rarer a parent is within
            # this table's builds, the hotter its badge.
            if rate <= 0.25:
                rarity_cls = ' dd-tag-rare'
            elif rate <= 0.60:
                rarity_cls = ' dd-tag-uncommon'
            rate_line = f'\ncleared by {rate:.0%} of the builds in this table'
        hover_text_str = (
            f'{hover_first_line}\n'
            f'{parent}\n'
            f'{sub_labels_text}'
            f'{rate_line}'
        )
        tag_bits.append(
            f'<span class="dd-anchor-tag{rarity_cls}"'
            f'{tooltip_attr(hover_text_str)}>'
            f'{badge_text}</span>'
        )
        kind = subs[0].kind
        if kind in n_parents_by_kind:
            n_parents_by_kind[kind] += 1
        n_total_subs += n_subs
    if tag_bits:
        tags_cell = ' '.join(tag_bits)
    elif n_skipped:
        # Everything this row clears is in the shared callout above.
        tags_cell = '<span style="color:#8b949e">common set only</span>'
    else:
        tags_cell = '-'
    n_total_parents = sum(n_parents_by_kind.values())
    if n_total_parents == 0:
        cell_title = 'No anchors cleared'
    else:
        kind_parts = []
        if n_parents_by_kind['damage_breakpoint']:
            kind_parts.append(f"{n_parents_by_kind['damage_breakpoint']} brkp")
        if n_parents_by_kind['bulkpoint']:
            kind_parts.append(f"{n_parents_by_kind['bulkpoint']} blkp")
        if n_parents_by_kind['cmp']:
            kind_parts.append(f"{n_parents_by_kind['cmp']} cmp")
        cell_title = (
            f'Clears {n_total_parents} anchors '
            f'({" · ".join(kind_parts)}) '
            f'· {n_total_subs} sub-anchors total. '
            f'Hover any badge for per-anchor detail.'
        )
    return tags_cell, cell_title


def render_mirror_slayer_html(ctx_or_slayer=None, *, slayer_iter_result=None,
                              data_obj=None, moveset_idx=0):
    """Render the Slayer Builds section of the Results pane.

    Two first-class archetype tables (Anchors-First, CMP-First) built by
    ``build_slayer_archetypes``, plus the Nash-iteration round diagnostics
    in a collapsed details block. Accepts either an ``AnalysisContext`` as
    the first positional arg or explicit keyword args
    (``slayer_iter_result``, ``data_obj``, ``moveset_idx``).  Returns an
    HTML string (empty if no slayer iteration ran).
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
        'all': 'per opponent, credit = shield scenarios won / 9',
        'even': 'per opponent, credit = even shields (0v0/1v1/2v2) won / 3',
        'even-strict': 'per opponent, credit = 1 only when ALL three even shields are won',
    }.get(metric_label, '')
    rounds_run = slayer_iter_result.get('rounds_run', 0)
    converged = slayer_iter_result.get('converged', False)
    final_pool = len(slayer_iter_result.get('final', []))
    categories = slayer_iter_result.get('categories', {})
    n_af = len(categories.get('Anchors-First Slayer', []) or [])
    n_cf = len(categories.get('CMP-First Slayer', []) or [])
    parts.append(
        f'<details class="dd-collapsible">'
        f'<summary class="dd-h3" style="cursor:pointer">'
        f'Slayer Builds '
        f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
        f'({n_af} anchors-first, {n_cf} cmp-first; mirror population '
        f'{final_pool}, {rounds_run} round{"s" if rounds_run != 1 else ""}, '
        f'{"converged" if converged else "max rounds reached"})</span>'
        f'</summary>\n'
    )
    parts.append(
        f'<p class="dd-small dd-prose">Two mirror-focused build archetypes '
        f'for {data_obj.get("species", "this species")}. '
        f'<strong>Anchors-First</strong>: lock in the named break/bulkpoints, '
        f'then take as much Charge Move Priority as possible. '
        f'<strong>CMP-First</strong> (the &ldquo;lab mon&rdquo;): take the '
        f'max-attack spreads and see which anchors they keep or sacrifice. '
        f'Both are computed directly from the anchor thresholds - the '
        f'Nash-style mirror iteration below only supplies the opponent '
        f'population that the CMP and mirror-wins columns are measured '
        f'against.</p>\n'
    )

    # Iteration details -- collapsed by default
    parts.append(
        '<details class="dd-flip-detail">'
        '<summary>Mirror population (iteration details)</summary>\n'
    )
    parts.append(f'<p>Nash-style iterative discovery of the '
                 f'{data_obj.get("species", "mirror")} mirror opponent '
                 f'population. Each round tests focal IVs against the '
                 f'previous round\'s top pool under a graded metric '
                 f'(fractional wins, avg-score tiebreak), so the pool cap '
                 f'holds instead of exploding on integer-win ties.</p>\n')
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

    # Archetype cards
    resolved_anchors = slayer_iter_result.get('resolved_anchors', []) or []

    # Summarize resolved anchors (for the intro paragraph and
    # Level 3 sub-anchor distribution report).
    anchor_parents: dict[str, list] = {}
    for a in resolved_anchors:
        anchor_parents.setdefault(a.parent, []).append(a)

    CATEGORY_DESCRIPTIONS = {
        'Anchors-First Slayer': (
            'Hit the important break/bulkpoints first, then win Charge '
            'Move Priority as much as possible. Members clear the '
            '<em>maximum achievable number</em> of counted anchor '
            'parents - explicit TOML anchors always count, '
            'auto-generated ones only when they are selective (cleared '
            'by less than half the IV space, so &ldquo;everyone passes '
            'it&rdquo; anchors can&rsquo;t saturate the archetype). '
            'Ranked by Top-Mirror CMP&nbsp;%, then attack. '
            '<strong>Hidden when no counted anchor resolves.</strong>'),
        'CMP-First Slayer': (
            'The &ldquo;lab mon&rdquo; build: win Charge Move Priority '
            'first, pick up anchors as a secondary goal. Rows are the '
            'max-attack spreads in the IV space, ranked by attack; the '
            'Anchors column reports what each clears vs sacrifices - '
            'no anchor is required for membership.'),
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
            n_counted = next(
                (r['n_counted_parents'] for civs in categories.values()
                 for r in civs if 'n_counted_parents' in r), 0)
            parts.append(
                f'<p class="dd-small">Each row is tagged with the '
                f'set of named anchors it passes. {n_parents} parent '
                f'anchor(s) resolved to {n_subs} concrete threshold '
                f'check(s) - Level&nbsp;3 discover-mode anchors expand '
                f'into a family of sub-anchors (one per discovered '
                f'(move,&nbsp;tier) breakpoint). {n_counted} parent(s) '
                f'are counted for Anchors-First membership. See the '
                f'Tags column for per-IV detail; IVs that fit '
                f'<em>both</em> archetypes are marked with '
                f'cross-category badges.</p>\n'
            )
        else:
            parts.append(
                '<p class="dd-small">No named anchors are configured '
                'for this species/league (or none resolved). '
                'Anchors-First Slayer will be empty; CMP-First Slayer '
                'still ranks the max-attack spreads. Add anchors to the '
                'species <code>thresholds/*.toml</code> file to enable '
                'the anchor checklist.</p>\n'
            )

        # Tag-compactness JS -- defined once, used by all cards.
        parts.append("""<script>
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
        CAT_ABBREV = {'Anchors-First Slayer': 'AF', 'CMP-First Slayer': 'CF'}
        CAT_COLORS = {'Anchors-First Slayer': '#f85149',
                      'CMP-First Slayer': '#d29922'}
        # Hard cap on rows emitted into the HTML per card. Anchors-First
        # membership can be broad when the max-cleared anchor tier is easy;
        # the full member set still feeds the scatter overlay and Notable
        # IVs, but the table emits at most this many rows and the note
        # under the table says how many were dropped (no silent caps).
        HTML_ROW_CAP = 100
        _table_uid = 0
        _ms_prefix = f"ms{moveset_idx}"
        for cat_name, cat_ivs in categories.items():
            if not cat_ivs:
                continue  # hide empty archetypes (Anchors-First w/o anchors)
            desc = CATEGORY_DESCRIPTIONS.get(cat_name, '')
            n_total = len(cat_ivs)
            emitted = cat_ivs[:HTML_ROW_CAP]
            n_emitted = len(emitted)
            n_visible = min(n_emitted, 10)  # top N visible by default
            # Top-quartile highlighting: first ceil(n_emitted / 4) rows
            n_quartile = max(1, (n_emitted + 3) // 4)

            _table_uid += 1
            card_id = f"{_ms_prefix}-slayer-{_table_uid}"
            # External-link anchor on the rec-card div, derived from the
            # category name (e.g. 'mirror-anchors-first-slayer'). card_id
            # above is the moveset-scoped prefix for the expand toggle so
            # handles don't collide across movesets on a single page.
            mirror_slug = f'mirror-{opp_slug(cat_name)}'

            parts.append(f'<div class="dd-rec-card" id="{mirror_slug}">\n')
            parts.append(
                f'<h4>{cat_name} '
                f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
                f'({n_total} IV{"s" if n_total != 1 else ""})'
                f'</span></h4>\n'
            )
            if desc:
                parts.append(f'<p class="dd-small dd-prose">{desc}</p>\n')

            # Signal-loss remedy (2026-06-11, Michael's 4+3 hybrid pick):
            # parents cleared by EVERY emitted build say so ONCE here
            # instead of repeating on each row, and the per-row badges
            # that remain are rarity-coded by their clear rate within
            # this table. Cohort = the emitted rows (what the reader
            # sees; membership beyond the HTML cap feeds the scatter
            # and Notable IVs unchanged).
            parent_rates, saturated = _parent_clear_stats(emitted)
            if saturated:
                sat_bits = []
                for parent in sorted(saturated):
                    long_name = parent
                    for _r in emitted:
                        _subs = (_r.get('_anchor_tags', {}) or {}).get(parent)
                        if _subs:
                            long_name = _subs[0].parent_display_name or parent
                            break
                    sat_bits.append(
                        f'<span class="dd-anchor-tag"'
                        f'{tooltip_attr(long_name + chr(10) + parent + chr(10) + "cleared by every build in this table")}>'
                        f'{derive_short_name(parent)}</span>'
                    )
                parts.append(
                    f'<p class="dd-small" style="margin:4px 0">'
                    f'Every build below clears: {" ".join(sat_bits)} '
                    f'<span style="color:#8b949e">(omitted from the '
                    f'per-row badges; remaining badges are color-coded '
                    f'by rarity within this table)</span></p>\n'
                )

            # Table
            parts.append(
                f'<table class="dd-table dd-narrow" id="{card_id}-table">\n'
            )
            parts.append(
                '<tr><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th>'
                f'<th{tooltip_attr("Counted anchor parents cleared / total counted. Hover the badges for per-anchor detail.")}>Anchors</th>'
                f'<th{tooltip_attr("Fraction of the top-50 same-species IVs (by avg battle score) whose atk this row ties or beats.")}>Top-Mirror CMP&nbsp;%</th>'
                f'<th{tooltip_attr("Same atk comparison, vs the Nash-converged mirror population (see iteration details above).")}>Nash CMP&nbsp;%</th>'
                f'<th{tooltip_attr("Expected matchups won vs the mirror population (fractional shield-scenario credit) / population size.")}>Mirror Wins</th>'
                '<th>Avg</th><th>Also</th></tr>\n'
            )
            for idx, r in enumerate(emitted):
                a, d, s = r['iv']
                # Cross-archetype badges
                others = sorted(iv_categories.get(r['iv'], set()) - {cat_name})
                badges = ''
                for o in others:
                    ab = CAT_ABBREV.get(o, '?')
                    col = CAT_COLORS.get(o, '#888')
                    badges += (
                        f'<span class="dd-badge" '
                        f'style="background:{col};color:#000"'
                        f'{tooltip_attr(o)}>{ab}</span> '
                    )

                tags_cell, cell_title_attr = _anchor_tags_cell(
                    r, parent_rates=parent_rates, skip_parents=saturated)
                anchors_count = (f"{r.get('n_parents_cleared', 0)}/"
                                 f"{r.get('n_counted_parents', 0)}")
                tm = r.get('top_mirror_cmp')
                nc = r.get('nash_cmp')
                tm_cell = f'{tm:.0f}%' if tm is not None else '-'
                nc_cell = f'{nc:.0f}%' if nc is not None else '-'
                npairs = r.get('n_pairs', 0)
                mw_cell = (f"{r.get('frac_wins', 0.0):.1f}/{npairs}"
                           if npairs else '-')

                # Row classes: collapse-hidden beyond top N until expanded;
                # highlighted if in the top quartile.
                row_cls_parts = []
                if idx < n_quartile:
                    row_cls_parts.append('dd-slayer-top')
                if idx >= n_visible:
                    row_cls_parts.append('dd-slayer-hidden')
                row_cls = f' class="{" ".join(row_cls_parts)}"' if row_cls_parts else ''

                parts.append(
                    f'<tr{row_cls}>'
                    f'<td>{a}/{d}/{s}</td>'
                    f'<td>{r["atk"]:.2f}</td>'
                    f'<td>{r["def_"]:.2f}</td>'
                    f'<td>{r["hp"]}</td>'
                    f'<td class="dd-anchor-tags-cell"'
                    f'{tooltip_attr(cell_title_attr)}>'
                    f'<b>{anchors_count}</b> '
                    f'<div class="dd-anchor-tags-inner dd-tags-compact" '
                    f'onclick="ddToggleTagsCompactCell(event)">'
                    f'{tags_cell}</div></td>'
                    f'<td class="dd-gain">{tm_cell}</td>'
                    f'<td>{nc_cell}</td>'
                    f'<td>{mw_cell}</td>'
                    f'<td>{r["avg_score"]:.1f}</td>'
                    f'<td>{badges}</td></tr>\n'
                )
            parts.append('</table>\n')

            # Expand toggle if there are hidden rows
            if n_emitted > n_visible:
                parts.append(
                    f'<button class="dd-slayer-toggle" '
                    f'onclick="(function(btn){{'
                    f'var t=document.getElementById(\'{card_id}-table\');'
                    f'var rows=t.querySelectorAll(\'tr.dd-slayer-hidden\');'
                    f'var shown=rows.length>0 && rows[0].classList.contains(\'dd-slayer-shown\');'
                    f'rows.forEach(function(r){{r.classList.toggle(\'dd-slayer-shown\', !shown);}});'
                    f'btn.textContent=shown?\'Show all {n_emitted}\':\'Collapse to top {n_visible}\';'
                    f'}})(this)" >'
                    f'Show all {n_emitted}'
                    f'</button>\n'
                )
            if n_total > n_emitted:
                parts.append(
                    f'<p class="dd-small">Showing the top {n_emitted} of '
                    f'{n_total} member IVs by this archetype\'s ranking; '
                    f'{n_total - n_emitted} more are in the cohort (all '
                    f'still appear in the scatter overlay).</p>\n'
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
                'sub-anchors actually matter for this species - '
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
        if d[1] is not None:
            line += f'<td><strong>{d[0]}</strong> ({d[1]["eta_squared"]:.3f})</td></tr>\n'
        else:
            # All three stats had <3 distinct values (heavily floored or
            # tiny IV pools) — detect_banding returned None for every
            # band, and max() handed back a None entry. Render a dash
            # instead of crashing the whole dive render.
            line += '<td>-</td></tr>\n'
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
                 f'assume a fixed number of clusters - it finds natural breakpoints '
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
                         f'scores {tc_score_min:.0f}-{tc_score_max:.0f} '
                         f'(SP ranks {tc_sp_min}-{tc_sp_max}). '
                         f'<b>On graph:</b> look for Y &ge; {tc_score_min:.0f} '
                         f'with SP rank {tc_sp_min}-{tc_sp_max} on X axis.</p>\n')
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
            row += f'<td{cls}{tooltip_attr(f"Rank {r} out of {nIvs}")}>{r}</td>'
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
        parts.append(f'<details class="dd-flip-detail"><summary>{iv_label(data_obj, iv)} - <span class="dd-gain">+{g}</span>/<span class="dd-loss">-{l}</span> (net {net:+d}){tier_badge_html(data_obj, iv)}</summary>\n')
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
  <dd>Each IV is ranked 1-{nIvs} for each scenario independently. The range (best rank minus
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
  variance explained by stat grouping, 0-1 scale) measure how much each stat creates
  visible bands. Pearson <em>r</em> shows correlation direction (positive = higher stat &rarr; higher score).</dd>
  <dt>Cluster detection (gap analysis)</dt>
  <dd>All {nIvs} IVs are sorted by their average score for a given scenario. We compute the
  score difference between each consecutive pair. The median of these differences is the
  &ldquo;typical&rdquo; gap. Gaps exceeding 3&times; the median indicate a natural break between
  performance tiers. This is <em>not</em> k-means or similar - it assumes no fixed cluster
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
            '<li><b>Tier</b> (a.k.a. <i>spread</i>) - a named stat-cutoff region, e.g. '
            '"GH Great = Def &ge; 143.03, HP &ge; 138." Any IV meeting all the cutoffs is in the tier.</li>\n'
            '<li><b>Anchor</b> - a yes/no rule applied to one IV, e.g. "clears the Medicham '
            'Dynamic Punch bulkpoint." Each anchor reduces to a single numeric threshold.</li>\n'
            '<li><b>Breakpoint</b> - an <i>attack</i> threshold at which one of your moves '
            'deals +1 more integer damage to a specific opponent.</li>\n'
            '<li><b>Bulkpoint</b> - a <i>defense</i> threshold at which one of an opponent\'s '
            'moves deals 1 less integer damage to you. The defensive mirror of a breakpoint.</li>\n'
            '<li><b>Matchup-flipping boundary</b> - a full-battle stat target: the smallest '
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

    # -- Envelope-position metric (S4) --
    # Per-category position relative to the Anchor IVs band at matching
    # SP rank. Stashed on data_obj so the S6+ article generator can pull
    # it without re-running the aggregator. Keyed by moveset_idx because
    # the band + category membership differ per moveset.
    anchor_iv_indices = data_obj.get('anchorClearIvs') or []
    sp_ranks = data_obj.get('spRanks') or []
    envelope_positions = None
    if anchor_iv_indices and sp_ranks and avg_scores:
        envelope_positions = analysis.compute_envelope_positions(
            iv_categories_all, sp_ranks, avg_scores, anchor_iv_indices,
        )
        data_obj.setdefault('envelopePositions', {})[str(moveset_idx)] = (
            envelope_positions
        )

    notable_html = render_notable_ivs_section(
        iv_categories_all, data_obj, opp_iv_mode,
        recommendations_html=rec_html,
        envelope_positions=envelope_positions,
    )
    if notable_html:
        parts.append(notable_html)

    # -- Slayer Builds --
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
            toggle_id='mb-standalone', top_n=10,
            emit_opponent_ids=True)
    anchor_bullets = []
    if anchor_flip_records:
        anchor_bullets = render_anchor_flip_bullets(
            anchor_flip_records, anchor_passing_sink=anchor_passing_sink,
            has_bait_axis=has_bait_axis,
            emit_opponent_ids=True)

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

        # Key Matchup Thresholds - the high-level overview, always visible on expand
        if threshold_descs:
            parts.append('<h4 class="dd-h3">Key Matchup Thresholds</h4>\n')
            parts.append(f'<p>Matchups that flip vs {opp_label} opponents, '
                         f'ordered by how many top IVs benefit:</p>\n')
            parts.append('<ul class="dd-threshold-list">\n')
            parts.append('\n'.join(threshold_descs))
            parts.append('\n</ul>\n')

        # Matchup-Flipping Boundaries - nested collapsible
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

        # Anchor-Driven Matchup Flips - nested collapsible
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
