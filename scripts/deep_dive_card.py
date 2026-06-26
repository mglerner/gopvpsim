"""Compact, screenshot-able "dive card" renderer.

A single-glance spec sheet for a deep dive: species + typing + sprite, the
recommended moveset, up to six distinct target IV spreads with their role labels,
two headline win-rate numbers (our single-IV convention and a top-512
opponent-IV robustness number), and key wins / losses. It sits at the top
of every dive page (embedded variant) and also exports as a self-contained
single-file HTML (standalone variant).

Independent reproduction of the *look* of a publicly-posted infographic
(boxes + colors via CSS, real sprites). All fields are auto-generated from
our own simulation data -- no editorial prose -- so it is ship-mode clean.

``build_card_model`` is a pure transform of (data_obj + card_ctx) into a
``CardModel``; ``render_card_html`` turns a model into HTML. The score-
layout-aware extraction (single-IV win-rate, key wins/losses) happens
upstream in deep_dive.generate_analysis_sections and arrives via card_ctx,
so this module needs no simulation and is trivially unit-testable.
"""
from __future__ import annotations

import html
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gopvpsim.display import apply_dive_title_override, pretty_species  # noqa: E402
from gopvpsim.theme import (  # noqa: E402
    data_theme_attr,
    theme_css,
    theme_head_script,
    theme_picker_html,
)
from deep_dive_analysis import pretty_moveset  # noqa: E402

# Hard cap on rendered recommendation spreads. Mirrors deep_dive.REC_MAX_SPREADS
# (kept as a local literal to avoid a circular import: deep_dive imports this
# module). card_ctx already passes a pre-trimmed list of chosen spreads, so this
# slice is a belt-and-suspenders bound; the .ddcard-spreads auto-fit grid wraps
# up to 6 cards cleanly.
REC_MAX_SPREADS = 6


@dataclass
class Spread:
    """One recommended IV spread shown as a mini-card."""
    iv_str: str            # "0/15/14"
    atk: float
    def_: float
    hp: int
    cp: int
    sp_rank: int           # stat-product rank (1 = bulkiest)
    style: str             # role label, e.g. "Attack Weight"
    is_efficient: bool = False  # globally Pareto-efficient IV (crown)
    cover_breakpoints: list = field(default_factory=list)  # named opps (BP) census
    cover_bulkpoints: list = field(default_factory=list)   # named opps (bulk) census
    n_breakpoint_opps: int = 0  # census count of distinct BP opponents cleared
    n_bulkpoint_opps: int = 0   # census count of distinct bulk opponents cleared
    n_breakpoint_newly: int = 0  # BP opps the boost newly guarantees (vs base form)
    flip_fd: dict | None = None  # raw flip data; rendered + linked at render time
    flip_has_bait: bool = False


@dataclass
class WinRate:
    frac: float            # 0..1
    pool: int              # number of opponents
    scenarios: int         # shield scenarios averaged
    k: int | None = None   # opponent-IV cohort size (robustness only)

    @property
    def pct(self) -> str:
        # round half up (predictable for a headline %, vs round-half-to-even)
        return f'{int(self.frac * 100 + 0.5)}%'


@dataclass
class CardModel:
    species_display: str
    shadow: bool
    types: list[str]                      # title-cased, e.g. ["Steel", "Flying"]
    league_display: str
    cp_cap: int
    moveset: str                          # pretty "Sand Attack / Air Cutter, Payback"
    spreads: list[Spread]
    single_iv: WinRate | None
    robust: WinRate | None
    key_wins: list[tuple[str, float]] = field(default_factory=list)
    key_losses: list[tuple[str, float]] = field(default_factory=list)
    sprite_uri: str | None = None
    two_number_ones: dict | None = None  # battle-#1 vs stat-product-#1 explainer
    base_form_display: str | None = None  # item 5: "vs non-shadow X" base label
    sibling_trade: dict | None = None  # form-level break/bulkpoint trade vs sibling


# Type -> accent color (matches common PvP type palettes; used for chips and
# the no-sprite fallback block).
_TYPE_COLORS = {
    'normal': '#9099a1', 'fire': '#ff9d55', 'water': '#4d90d5',
    'electric': '#f4d23c', 'grass': '#63bc5a', 'ice': '#73cec0',
    'fighting': '#ce4069', 'poison': '#ab6ac8', 'ground': '#d97746',
    'flying': '#8fa8dd', 'psychic': '#fa7179', 'bug': '#90c12c',
    'rock': '#c7b78b', 'ghost': '#5269ac', 'dragon': '#0a6dc4',
    'dark': '#5a5366', 'steel': '#5a8ea1', 'fairy': '#ec8fe6',
}


def _league_display(league: str) -> str:
    return {'great': 'Great League', 'ultra': 'Ultra League',
            'master': 'Master League'}.get(league, league.title())


def _pretty_opp(name: str) -> str:
    try:
        return pretty_species(name)
    except Exception:  # noqa: BLE001
        return name


def build_card_model(data_obj, card_ctx, *, types, shadow=None,
                     robust_winrate=None, sprite_uri=None) -> CardModel:
    """Pure transform: (dive data_obj + analysis card_ctx) -> CardModel.

    ``card_ctx`` is the dict deep_dive.generate_analysis_sections stashed on
    ``data_obj['_cardCtx']`` (rec_candidates, rec_idx, flips, key_wins/losses,
    single_iv_winrate, ...). ``types`` is the focal's lowercase gamemaster
    type list. ``shadow`` is the focal's shadow flag -- pass it explicitly
    (data_obj has no 'shadow' key; the flag lives on the render kwargs); the
    data_obj/card_ctx fallback exists only for synthetic-dict unit tests.
    ``robust_winrate`` is the optional opponent-IV robustness dict
    {'frac','pool','k','scenarios'} computed by the caller (sims).
    """
    species = data_obj['species']
    if shadow is None:
        shadow = bool(data_obj.get('shadow') or card_ctx.get('shadow'))
    else:
        shadow = bool(shadow)
    disp = apply_dive_title_override(pretty_species(species))
    if shadow and 'Shadow' not in disp:
        disp = f'Shadow {disp}'

    movesets = data_obj.get('movesets') or [{}]
    moveset = movesets[0].get('prettyLabel') or movesets[0].get('label') or ''
    if moveset and '/' in moveset and 'prettyLabel' not in movesets[0]:
        moveset = pretty_moveset(moveset)

    rec_candidates = card_ctx.get('rec_candidates') or []
    flips = card_ctx.get('flips') or {}
    has_bait = card_ctx.get('has_bait_axis', False)
    iv_efficient = data_obj.get('ivEfficient') or []
    spreads = []
    for rc in rec_candidates[:REC_MAX_SPREADS]:
        iv = rc['iv']
        spreads.append(Spread(
            iv_str=f"{data_obj['ivA'][iv]}/{data_obj['ivD'][iv]}/{data_obj['ivS'][iv]}",
            atk=data_obj['ivAtk'][iv], def_=data_obj['ivDef'][iv],
            hp=data_obj['ivHp'][iv], cp=data_obj['ivCp'][iv],
            sp_rank=data_obj['spRanks'][iv], style=rc.get('style', ''),
            cover_breakpoints=rc.get('cover_breakpoints') or [],
            cover_bulkpoints=rc.get('cover_bulkpoints') or [],
            n_breakpoint_opps=rc.get('n_breakpoint_opps') or 0,
            n_bulkpoint_opps=rc.get('n_bulkpoint_opps') or 0,
            n_breakpoint_newly=rc.get('n_breakpoint_newly') or 0,
            flip_fd=flips.get(iv), flip_has_bait=has_bait,
            is_efficient=bool(iv_efficient[iv]) if iv < len(iv_efficient) else False,
        ))

    # Item 5: base-form label for the "N newly guaranteed vs base form" line.
    # Derive the display from the base species (+shadow) so it can't drift from
    # a stale baked string; the base form is always non-shadow today.
    _base_form = card_ctx.get('base_form')
    base_form_display = None
    if _base_form:
        _bs = _base_form['species']
        _bdisp = pretty_species(_bs)
        if _base_form.get('shadow') and 'Shadow' not in _bdisp:
            _bdisp = f'Shadow {_bdisp}'
        base_form_display = _bdisp

    def _wr(d, is_robust=False):
        if not d:
            return None
        return WinRate(frac=d['frac'], pool=d['pool'],
                       scenarios=d.get('scenarios', 1),
                       k=d.get('k') if is_robust else None)

    # Prettify the two-#1s example opponent lists (stored raw upstream), mirroring
    # how key_wins/losses are prettified.
    tno = card_ctx.get('two_number_ones')
    if tno:
        tno = dict(tno)
        tno['gives_up'] = [_pretty_opp(n) for n in tno.get('gives_up', [])]
        tno['wins_bigger'] = [_pretty_opp(n) for n in tno.get('wins_bigger', [])]

    return CardModel(
        species_display=disp, shadow=shadow,
        types=[t.title() for t in types],
        league_display=_league_display(data_obj['league']),
        cp_cap=data_obj.get('cpCap', 0),
        moveset=moveset, spreads=spreads,
        single_iv=_wr(card_ctx.get('single_iv_winrate')),
        robust=_wr(robust_winrate, is_robust=True),
        key_wins=[(_pretty_opp(n), s) for n, s in card_ctx.get('key_wins', [])],
        key_losses=[(_pretty_opp(n), s) for n, s in card_ctx.get('key_losses', [])],
        sprite_uri=sprite_uri,
        two_number_ones=tno,
        base_form_display=base_form_display,
        sibling_trade=card_ctx.get('sibling_trade'),
    )


def _name_html(link_opps):
    """Opponent-name renderer: a #opp-<slug> link when the card is embedded in
    its dive, else just escaped text (a standalone card has no dive to link to,
    so links would dangle). Uses the dive's own ``opp_slug`` so the card link
    and the dive anchor agree across naming variants (Galarian/Shadow forms)."""
    if link_opps:
        from deep_dive_rendering import opp_slug
        return lambda o: (f'<a class="ddcard-oplink" href="#opp-{opp_slug(o)}">'
                          f'{html.escape(o)}</a>')
    return html.escape


def _flip_html(fd, has_bait, link_opps):
    if not fd:
        return ''
    try:
        from deep_dive_rendering import prose_flip_summary
        prose = prose_flip_summary(fd, max_gains=2, max_losses=1,
                                   has_bait_axis=has_bait,
                                   name_html=_name_html(link_opps))
        if not prose or prose == 'no matchup flips':
            return prose
        # The flip is measured against the stat-product #1 (reference) IV; label
        # it so the lead spread's gains/loses line is not read as absolute.
        return f'vs stat-product #1: {prose}'
    except Exception:  # noqa: BLE001
        return ''


CARD_CSS = """
.ddcard { background:var(--surface); border:1px solid var(--border); border-radius:2px;
  padding:18px 20px; margin:0 0 18px; color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.ddcard a { color:var(--accent); text-decoration:none; }
.ddcard-head { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
.ddcard-sprite { width:88px; height:88px; flex:0 0 auto; image-rendering:auto;
  background:var(--surface-2); border-radius:2px; }
.ddcard-spriteph { width:88px; height:88px; flex:0 0 auto; border-radius:2px;
  display:flex; align-items:center; justify-content:center; font-weight:700;
  font-size:28px; }
.ddcard-title { flex:1 1 240px; }
.ddcard-title h2 { margin:0; font-size:1.5rem; color:var(--title); }
.ddcard-shadow { color:var(--accent); font-weight:700; }
.ddcard-chips { margin:6px 0; }
.ddcard-chip { display:inline-block; padding:2px 10px; border-radius:4px;
  font-size:0.78rem; font-weight:700; margin-right:6px; }
.ddcard-move { color:var(--text); font-size:0.92rem; margin-top:4px; }
.ddcard-move b { color:var(--accent); }
.ddcard-spreads { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px; margin:12px 0; }
.ddcard-spread { background:var(--surface-2); border:1px solid var(--border-2); border-radius:2px;
  padding:9px 11px; }
.ddcard-spread .role { color:var(--title); font-weight:700; font-size:0.82rem;
  text-transform:uppercase; letter-spacing:0.02em; }
.ddcard-spread .iv { font-size:1.25rem; font-weight:800; color:var(--heading); margin:2px 0; }
.ddcard-spread .stats { font-size:0.78rem; color:var(--text-muted); }
.ddcard-spread .flips { font-size:0.74rem; color:var(--text-muted); margin-top:4px; }
.ddcard-spread .cover { font-size:0.74rem; color:var(--energy); margin-top:4px; }
.ddcard-spread .cover b { color:var(--text); font-weight:700; }
.ddcard-spread .cover .cover-count { color:var(--text); font-weight:700; }
.cover-toggle { position:absolute; opacity:0; width:0; height:0; }
.cover-rest { display:none; }
.cover-toggle:checked ~ .cover-rest { display:inline; }
.cover-more { color:var(--accent); cursor:pointer; white-space:nowrap;
  text-decoration:underline; text-decoration-style:dotted; }
.cover-more .cm-hide { display:none; }
.cover-toggle:checked ~ .cover-more .cm-show { display:none; }
.cover-toggle:checked ~ .cover-more .cm-hide { display:inline; }
.ddcard-oplink { color:inherit; text-decoration:underline;
  text-decoration-style:dotted; text-decoration-color:var(--accent); }
.ddcard-oplink:hover { text-decoration-style:solid; }
/* Key Wins / Key Losses are a CARD-LEVEL summary for the recommended IV -- NOT
   per-spread. So they live in ONE full-width panel that spans all the spread
   columns (a single wide box vs the N narrow spread cards), with a green-wins /
   red-losses split. Spanning the whole width prevents the "spread 1 wins,
   spread N loses" misread that column-aligning them would imply, for any N. */
.ddcard-matchups { display:flex; flex-wrap:wrap; margin-top:8px;
  background:var(--surface-2); border:1px solid var(--border); border-radius:2px;
  overflow:hidden; }
.ddcard-mcol { flex:1 1 200px; padding:9px 14px; }
.ddcard-mcol + .ddcard-mcol { border-left:1px solid var(--border); }
.ddcard-mcol h4 { margin:0 0 4px; font-size:0.8rem;
  letter-spacing:0.03em; }
.ddcard-mcol.wins h4 { color:var(--win); }
.ddcard-mcol.losses h4 { color:var(--loss); }
.ddcard-mcol ul { margin:0; padding-left:18px; font-size:0.85rem; color:var(--text); }
.ddcard-foot { font-size:0.72rem; color:var(--text-muted); margin-top:12px;
  border-top:1px solid var(--border); padding-top:8px; }
.ddcard-note { background:var(--callout-bg); border:1px solid var(--callout-expert);
  border-radius:0; padding:9px 12px; margin:4px 0 12px; font-size:0.82rem;
  color:var(--callout-fg); line-height:1.4; }
.ddcard-note b { color:var(--callout-strong); }
.ddcard-note .iv { color:var(--flip); font-weight:800; }
.ddcard-wr-line { font-size:0.84rem; color:var(--text-muted); margin:10px 0 4px;
  border:1px solid var(--border-2); border-radius:2px; padding:8px 12px;
  background:var(--surface-2); }
.ddcard-wr-line .pct { color:var(--win); font-weight:800; }
.ddcard-wr-line .sep { color:var(--text-muted); margin:0 8px; }
.ddcard-wr-line .pool { color:var(--text-muted); }
.ddcard-sib { font-size:0.8rem; color:var(--callout-fg); margin:10px 0; padding:7px 12px;
  border:1px solid var(--accent); border-radius:0; background:var(--callout-bg); }
.ddcard-sib-head b { color:var(--callout-strong); font-weight:800; }
.ddcard-sib-detail { font-size:0.74rem; color:var(--text-muted); margin-top:3px; }
.ddcard-sib-detail .sib-bp { color:var(--energy); }
.ddcard-sib-detail .sib-blk { color:var(--tie); }
.ddcard-sib-foot { font-size:0.66rem; color:var(--text-muted); margin-top:4px;
  font-style:italic; }
"""


def _on_chip_text(fill: str) -> str:
    """Pick '#000' or '#fff' for text drawn ON a type-brand chip fill, by the
    fill's WCAG relative luminance, so dark types (dark, ghost, dragon, poison,
    fighting) get light text instead of a forced near-black. The _TYPE_COLORS
    fills are out-of-contract brand hex, so the on-text is computed here rather
    than tokenized. Non-hex fills (the var() fallback) default to light text.
    Per THEME_PHASE2_SPEC section 4."""
    if not (fill.startswith('#') and len(fill) == 7):
        return '#fff'
    def _lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    lum = (0.2126 * _lin(int(fill[1:3], 16))
           + 0.7152 * _lin(int(fill[3:5], 16))
           + 0.0722 * _lin(int(fill[5:7], 16)))
    return '#000' if lum > 0.179 else '#fff'


def _chip(t):
    c = _TYPE_COLORS.get(t.lower(), 'var(--text-muted)')
    return (f'<span class="ddcard-chip" style="background:{c};'
            f'color:{_on_chip_text(c)}">{html.escape(t)}</span>')


def _sprite_html(m: CardModel):
    if m.sprite_uri:
        return (f'<img class="ddcard-sprite" alt="{html.escape(m.species_display)}" '
                f'src="{m.sprite_uri}">')
    # Typing-colored fallback block (no AI artwork; just a colored initial).
    c = _TYPE_COLORS.get(m.types[0].lower(), _TYPE_COLORS["steel"]) if m.types else _TYPE_COLORS["steel"]
    initial = html.escape(m.species_display[:1].upper())
    return (f'<div class="ddcard-spriteph" style="background:{c};'
            f'color:{_on_chip_text(c)}">{initial}</div>')


def _wr_line(single: WinRate | None, robust: WinRate | None) -> str:
    """Compact one-row win-rate summary (replaces the two big stat boxes).

    Shows the single-IV % and the top-k opponent-IV robustness % side by side,
    followed by the shared "N opponents, all S shield scenarios" note. Much
    smaller than the prior two-box layout, freeing vertical space for the
    sibling-trade bar. Renders whatever subset is present."""
    if not single and not robust:
        return ''
    parts = []
    if single:
        parts.append(f'<span class="pct">{single.pct}</span> single-IV')
    if robust:
        k = robust.k or 512
        parts.append(f'<span class="pct">{robust.pct}</span> top-{k} robustness')
    ref = single or robust
    note = (f'<span class="pool">{ref.pool} opponents, all {ref.scenarios} '
            f'shield scenarios</span>')
    body = '<span class="sep">&middot;</span>'.join(parts + [note])
    return f'<div class="ddcard-wr-line">{body}</div>'


def _two_ones_html(t: dict | None) -> str:
    """Explainer shown only when our headline metric (battle score) and stat
    product disagree on the #1 IV, and especially when the stat-product #1 wins
    more matchups. We pitch battle score as the better metric, so the gap needs
    explaining rather than hiding. Auto-generated, ship-mode clean."""
    if not t:
        return ''
    bs = html.escape(str(t['bs_iv']))
    sp = html.escape(str(t['sp_iv']))
    N, M, tot = t['bs_wins'], t['sp_wins'], t['total']
    A, B = t['bs_score'], t['sp_score']
    # "picking up": the few matchups the stat-product #1 wins that battle-#1 gives
    # up (empty -> the clause is dropped).
    gu = t.get('gives_up') or []
    pick = ''
    if gu:
        n = t.get('gives_up_n') or len(gu)
        more = f' (+{n - len(gu)} more)' if n > len(gu) else ''
        pick = ', picking up ' + ', '.join(html.escape(o) for o in gu) + more
    if t.get('sp_wins_more'):
        body = (f'The <span class="iv">{sp}</span> (#1 stat product) wins more '
                f'matchups here ({M} vs {N} of {tot}){pick}. We still lead with '
                f'<span class="iv">{bs}</span> (#1 battle score) because it wins '
                f'more <b>convincingly</b>: average battle score {A} vs {B} (out '
                f'of 1000; 500 is an even fight).')
    else:
        body = (f'The <span class="iv">{bs}</span> (#1 battle score) wins {N} of '
                f'{tot} meta matchups; the <span class="iv">{sp}</span> (#1 stat '
                f'product) wins {M}{pick}. The <span class="iv">{bs}</span> also '
                f'wins more <b>convincingly</b>: average battle score {A} vs {B} '
                f'(out of 1000; 500 is an even fight).')
    return f'<div class="ddcard-note"><b>Why this IV?</b> {body}</div>'


_BAR_MAX_OPPS = 6  # opponent names shown before the "+K more" toggle on the bar


def _bar_opp_list(opps, link_opps):
    """Opponent list for the sibling-trade bar: a short head, then the tail
    behind a checkbox-hack "+K more" toggle (same no-JS pattern as the cover
    lists). Returns '' for an empty list."""
    if not opps:
        return ''
    _nm = _name_html(link_opps)
    head = ', '.join(_nm(o) for o in opps[:_BAR_MAX_OPPS])
    rest = opps[_BAR_MAX_OPPS:]
    if not rest:
        return head
    global _toggle_seq
    _toggle_seq += 1
    cid = f'sb{_toggle_seq}'
    tail = ', '.join(_nm(o) for o in rest)
    return (f'{head}<input type="checkbox" class="cover-toggle" id="{cid}">'
            f'<span class="cover-rest">, {tail}</span>'
            f'<label class="cover-more" for="{cid}">'
            f'<span class="cm-show"> +{len(rest)} more</span>'
            f'<span class="cm-hide"> less</span></label>')


def _sibling_trade_html(trade: dict | None, shadow=False, link_opps=False) -> str:
    """Form-level "newly guaranteed vs the sibling form" trade, rendered ONCE
    per card as a thin spanning bar (Dragapult-Sim style). Separate from the
    per-spread census: that is decisive-coverage per IV; this is the form trade
    (shadow<->non-shadow, Female<->Male) from the pure damage formula.

    The compute layer emits a trade for whichever side has a sibling. Two
    directions, keyed by ``focal_is_boosted``:

      * BOOSTED focal (a shadow or Female dive): the focal GAINS breakpoints
        from the extra attack and (for shadow) GIVES UP bulkpoints from the
        lower defense. Reads ``breakpoints_gained`` / ``bulkpoints_lost`` ->
        "Vs non-shadow X: +N breakpoints, -M bulkpoints from the shadow boost".
      * BARE focal (a non-shadow, shadow-eligible dive): the SIBLING is the
        shadow form, which gains breakpoints the focal can't reach, and the
        focal HOLDS bulkpoints the shadow gives up. Reads ``breakpoints_lost``
        (the shadow's gains) / ``bulkpoints_held`` (what the focal holds) ->
        "Vs Shadow X: shadow gains N breakpoints; you hold M bulkpoints".

    Gated to a non-empty trade with at least one breakpoint or bulkpoint in the
    relevant direction. ASCII only.
    """
    if not trade:
        return ''
    sib = html.escape(trade.get('sibling_display', 'the base form'))
    boosted = trade.get('focal_is_boosted', True)
    if boosted:
        # A shadow focal's sibling is the bare species; spell out "non-shadow"
        # so the trade reads unambiguously (this bar lives on the SHADOW dive).
        if shadow and 'non-shadow' not in sib.lower():
            sib = f'non-shadow {sib}'
        gained = trade.get('breakpoints_gained') or []
        given_up = trade.get('bulkpoints_lost') or []
    else:
        # Inverse: focal is the bare form, sibling is the shadow. The shadow
        # GAINS the breakpoints; the focal HOLDS the bulkpoints.
        gained = trade.get('breakpoints_lost') or []
        given_up = trade.get('bulkpoints_held') or []
    if not gained and not given_up:
        return ''

    parts = []
    if boosted:
        via = 'the shadow boost' if shadow else 'the extra attack'
        if gained:
            parts.append(f'<b>+{len(gained)}</b> guaranteed breakpoint'
                         f'{"" if len(gained) == 1 else "s"}')
        if given_up:
            parts.append(f'<b>-{len(given_up)}</b> bulkpoint'
                         f'{"" if len(given_up) == 1 else "s"}')
        headline = f'Vs {sib}: {", ".join(parts)} from {via}'
    else:
        if gained:
            parts.append(f'shadow gains <b>{len(gained)}</b> breakpoint'
                         f'{"" if len(gained) == 1 else "s"}')
        if given_up:
            parts.append(f'you hold <b>{len(given_up)}</b> bulkpoint'
                         f'{"" if len(given_up) == 1 else "s"}')
        headline = f'Vs {sib}: {"; ".join(parts)}'

    # Opponent lists. The breakpoint and bulkpoint sets are usually identical
    # (the extra atk and the lower def trade against the same bulky mons), so
    # collapse to ONE list when they match -- the headline counts already carry
    # the split. Show two lists only when the sets genuinely differ.
    bp_label = 'breaks' if boosted else 'shadow breaks'
    blk_label = 'gives up bulk vs' if boosted else 'you hold bulk vs'
    detail = []
    if gained and given_up and gained == given_up:
        one = _bar_opp_list(gained, link_opps)
        if one:
            detail.append(f'<span class="sib-bp">vs: {one}</span>')
    else:
        bp_list = _bar_opp_list(gained, link_opps)
        if bp_list:
            detail.append(f'<span class="sib-bp">{bp_label}: {bp_list}</span>')
        blk_list = _bar_opp_list(given_up, link_opps)
        if blk_list:
            detail.append(f'<span class="sib-blk">{blk_label}: {blk_list}</span>')
    detail_html = (f'<div class="ddcard-sib-detail">{" &middot; ".join(detail)}</div>'
                   if detail else '')
    # Basis footnote (ASCII, no em-dash): the bar counts the anchor-based
    # newly-guaranteed set vs the sibling form, at each opponent's default IV
    # (the same basis as the per-spread "N newly guaranteed" numbers).
    foot = ('<div class="ddcard-sib-foot">newly guaranteed vs the '
            f'{html.escape(trade.get("sibling_display", "base"))} form, '
            'by damage to each opponent\'s default IV</div>')
    return (f'<div class="ddcard-sib"><div class="ddcard-sib-head">{headline}</div>'
            f'{detail_html}{foot}</div>')


_COVER_MAX_OPPS = 7  # names shown before the "+N more" toggle on the card

# Per-render counter for unique toggle ids (a card can carry several cover
# lists, and a dive page can carry several cards).
_toggle_seq = 0


def _cover_html(s: Spread, link_opps=False, base_form_display=None,
                shadow=False):
    """Named opponent-coverage bullets (Dragapult-Sim style). Lists the FULL
    census of opponents this spread clears a break/bulkpoint against, led by a
    count headline ("18 guaranteed breakpoints"). Empty when the spread clears
    nothing (incl. the no-anchor fallback, where cover_* lists are empty). Long
    lists collapse the tail behind a clickable "+N more" toggle: collapsed by
    default (so a screenshot stays tight), the full list reveals inline when
    clicked. Opponent names link to their dive row when ``link_opps``."""
    _nm = _name_html(link_opps)

    def _join(opps):
        global _toggle_seq
        head = ', '.join(_nm(o) for o in opps[:_COVER_MAX_OPPS])
        rest = opps[_COVER_MAX_OPPS:]
        if not rest:
            return head
        _toggle_seq += 1
        cid = f'cm{_toggle_seq}'
        tail = ', '.join(_nm(o) for o in rest)
        # Checkbox-hack toggle: works with no page JS, in both the embedded and
        # standalone card variants. Collapsed by default; the label shows
        # "+N more" collapsed and "less" expanded (CSS swaps the two spans).
        return (f'{head}<input type="checkbox" class="cover-toggle" id="{cid}">'
                f'<span class="cover-rest">, {tail}</span>'
                f'<label class="cover-more" for="{cid}">'
                f'<span class="cm-show"> +{len(rest)} more</span>'
                f'<span class="cm-hide"> less</span></label>')

    def _headline(n, label):
        return (f'<span class="cover-count">{n} guaranteed {label}'
                f'{"" if n == 1 else "s"}</span> ')
    lines = []
    if s.cover_breakpoints:
        lines.append(f'<div class="cover">{_headline(s.n_breakpoint_opps, "breakpoint")}'
                     f'{_join(s.cover_breakpoints)}</div>')
    if s.cover_bulkpoints:
        lines.append(f'<div class="cover">{_headline(s.n_bulkpoint_opps, "bulkpoint")}'
                     f'{_join(s.cover_bulkpoints)}</div>')
    # Item 5: breakpoints the boost newly guarantees over the base form. ASCII
    # only; rendered only when the gate applies (base_form_display present) and
    # the spread gains at least one breakpoint vs the base.
    if base_form_display and s.n_breakpoint_newly > 0:
        n = s.n_breakpoint_newly
        _via = 'by the shadow boost ' if shadow else ''
        lines.append(
            f'<div class="cover newly">{n} newly guaranteed {_via}'
            f'(vs {html.escape(base_form_display)})</div>')
    return ''.join(lines)


def _spread_html(s: Spread, link_opps=False, base_form_display=None,
                 shadow=False):
    role = f'<div class="role">{html.escape(s.style)}</div>' if s.style else ''
    cover = _cover_html(s, link_opps, base_form_display, shadow)
    _fh = _flip_html(s.flip_fd, s.flip_has_bait, link_opps)
    flips = f'<div class="flips">{_fh}</div>' if _fh else ''
    # Crown ("efficient" = globally Pareto-optimal IV).
    crown = (' <span class="ddcard-crown" title="Efficient IV (Pareto-optimal): '
             'no other spread beats it on all of attack, defense and HP">'
             '\U0001F451</span>') if s.is_efficient else ''
    return (f'<div class="ddcard-spread">{role}'
            f'<div class="iv">{html.escape(s.iv_str)}{crown}</div>'
            f'<div class="stats">{s.atk:.1f} atk / {s.def_:.1f} def / {s.hp} hp'
            f' &middot; CP {s.cp} &middot; SP #{s.sp_rank}</div>{cover}{flips}</div>')


def _mcol(title, items, cls):
    """One half (wins or losses) of the full-width key-matchups panel. Returns
    '' when empty -- a missing side just leaves the present one full-width, so
    there is never an empty box or a left/right ambiguity."""
    if not items:
        return ''
    lis = ''.join(
        f'<li>{html.escape(n)} <span style="color:var(--text-muted)">({s:.0f})</span></li>'
        for n, s in items)
    return (f'<div class="ddcard-mcol {cls}"><h4>{html.escape(title)}</h4>'
            f'<ul>{lis}</ul></div>')


def render_card_html(model: CardModel, *, standalone: bool) -> str:
    """Render a CardModel to HTML. ``standalone`` wraps it in a full document
    with CARD_CSS inlined; otherwise returns just the <section> (the dive
    page already carries CARD_CSS)."""
    m = model
    name = html.escape(m.species_display)
    chips = ''.join(_chip(t) for t in m.types)
    wr = _wr_line(m.single_iv, m.robust)
    sib_bar = _sibling_trade_html(m.sibling_trade, shadow=m.shadow,
                                  link_opps=not standalone)
    spreads = ''.join(_spread_html(s, link_opps=not standalone,
                                   base_form_display=m.base_form_display,
                                   shadow=m.shadow)
                      for s in m.spreads)
    # One full-width panel (wins | losses), spanning all the spread columns so
    # it reads as a card-level summary rather than aligning to any one spread.
    wins = _mcol('Key wins', m.key_wins, 'wins')
    losses = _mcol('Key losses', m.key_losses, 'losses')
    cols = (f'<div class="ddcard-matchups">{wins}{losses}</div>'
            if (wins or losses) else '')

    section = f"""<section class="ddcard">
  <div class="ddcard-head">
    {_sprite_html(m)}
    <div class="ddcard-title">
      <h2>{name}</h2>
      <div class="ddcard-chips">{chips}</div>
      <div class="ddcard-move">{html.escape(m.league_display)} (CP {m.cp_cap}) &middot; <b>{html.escape(m.moveset)}</b></div>
    </div>
  </div>
  {wr}
  {sib_bar}
  {_two_ones_html(m.two_number_ones)}
  <div class="ddcard-spreads">{spreads}</div>
  {cols}
  <div class="ddcard-foot">Auto-generated from this project's simulation data.
  Win rate = shield-scenario matchups won (&gt;500), across all shield
  scenarios including asymmetric ones (0-1, 1-2, 2-1, ...).</div>
</section>"""

    if not standalone:
        return section
    return f"""<!DOCTYPE html>
<html lang="en" {data_theme_attr()}><head><meta charset="utf-8">
{theme_head_script()}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - dive card</title>
<style>{theme_css()}body{{background:var(--bg);margin:0;padding:18px;}}
.ddcard{{max-width:760px;margin:0 auto;}}
{CARD_CSS}</style></head>
<body>{theme_picker_html()}{section}</body></html>"""
