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

from gopvpsim.display import pretty_species  # noqa: E402
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
    cover_breakpoints: list = field(default_factory=list)  # named opps (BP) vs ref
    cover_bulkpoints: list = field(default_factory=list)   # named opps (bulk) vs ref
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
    disp = pretty_species(species)
    if shadow and 'Shadow' not in disp:
        disp = f'Shadow {disp}'

    movesets = data_obj.get('movesets') or [{}]
    moveset = movesets[0].get('prettyLabel') or movesets[0].get('label') or ''
    if moveset and '/' in moveset and 'prettyLabel' not in movesets[0]:
        moveset = pretty_moveset(moveset)

    rec_candidates = card_ctx.get('rec_candidates') or []
    flips = card_ctx.get('flips') or {}
    has_bait = card_ctx.get('has_bait_axis', False)
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
            flip_fd=flips.get(iv), flip_has_bait=has_bait,
        ))

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
        return prose_flip_summary(fd, max_gains=2, max_losses=1,
                                  has_bait_axis=has_bait,
                                  name_html=_name_html(link_opps))
    except Exception:  # noqa: BLE001
        return ''


CARD_CSS = """
.ddcard { background:#16213e; border:1px solid #0f3460; border-radius:10px;
  padding:18px 20px; margin:0 0 18px; color:#e6ecf5;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.ddcard a { color:#58a6ff; text-decoration:none; }
.ddcard-head { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
.ddcard-sprite { width:88px; height:88px; flex:0 0 auto; image-rendering:auto;
  background:#0f3460; border-radius:10px; }
.ddcard-spriteph { width:88px; height:88px; flex:0 0 auto; border-radius:10px;
  display:flex; align-items:center; justify-content:center; font-weight:700;
  font-size:28px; color:#0b1020; }
.ddcard-title { flex:1 1 240px; }
.ddcard-title h2 { margin:0; font-size:1.5rem; color:#fff; }
.ddcard-shadow { color:#b07cff; font-weight:700; }
.ddcard-chips { margin:6px 0; }
.ddcard-chip { display:inline-block; padding:2px 10px; border-radius:12px;
  font-size:0.78rem; font-weight:700; color:#0b1020; margin-right:6px; }
.ddcard-move { color:#cdd6e5; font-size:0.92rem; margin-top:4px; }
.ddcard-move b { color:#58a6ff; }
.ddcard-wr { display:flex; gap:14px; flex-wrap:wrap; margin:14px 0 4px; }
.ddcard-wr-box { flex:1 1 200px; background:#0f3460; border:1px solid #1a3a6e;
  border-radius:8px; padding:10px 12px; }
.ddcard-wr-box .pct { font-size:1.7rem; font-weight:800; color:#3fb950; }
.ddcard-wr-box .lbl { font-size:0.72rem; color:#8b949e; text-transform:uppercase;
  letter-spacing:0.03em; }
.ddcard-wr-box .sub { font-size:0.74rem; color:#9bb0d0; margin-top:2px; }
.ddcard-spreads { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px; margin:12px 0; }
.ddcard-spread { background:#0f3460; border:1px solid #1a3a6e; border-radius:8px;
  padding:9px 11px; }
.ddcard-spread .role { color:#e94560; font-weight:700; font-size:0.82rem;
  text-transform:uppercase; letter-spacing:0.02em; }
.ddcard-spread .iv { font-size:1.25rem; font-weight:800; color:#fff; margin:2px 0; }
.ddcard-spread .stats { font-size:0.78rem; color:#9bb0d0; }
.ddcard-spread .flips { font-size:0.74rem; color:#8b949e; margin-top:4px; }
.ddcard-spread .cover { font-size:0.74rem; color:#9be0a6; margin-top:4px; }
.ddcard-spread .cover b { color:#e6ecf5; font-weight:700; }
.ddcard-oplink { color:inherit; text-decoration:underline;
  text-decoration-style:dotted; text-decoration-color:#5a7; }
.ddcard-oplink:hover { text-decoration-style:solid; }
.ddcard-cols { display:flex; gap:18px; flex-wrap:wrap; margin-top:8px; }
.ddcard-col { flex:1 1 200px; }
.ddcard-col h4 { margin:0 0 4px; font-size:0.8rem; text-transform:uppercase;
  letter-spacing:0.03em; }
.ddcard-col.wins h4 { color:#3fb950; }
.ddcard-col.losses h4 { color:#f85149; }
.ddcard-col ul { margin:0; padding-left:18px; font-size:0.85rem; color:#cdd6e5; }
.ddcard-foot { font-size:0.72rem; color:#8b949e; margin-top:12px;
  border-top:1px solid #0f3460; padding-top:8px; }
.ddcard-note { background:#0f3460; border-left:3px solid #f0b429;
  border-radius:6px; padding:9px 12px; margin:4px 0 12px; font-size:0.82rem;
  color:#cdd6e5; line-height:1.4; }
.ddcard-note b { color:#fff; }
.ddcard-note .iv { color:#f0b429; font-weight:800; }
"""


def _chip(t):
    c = _TYPE_COLORS.get(t.lower(), '#8b949e')
    return f'<span class="ddcard-chip" style="background:{c}">{html.escape(t)}</span>'


def _sprite_html(m: CardModel):
    if m.sprite_uri:
        return (f'<img class="ddcard-sprite" alt="{html.escape(m.species_display)}" '
                f'src="{m.sprite_uri}">')
    # Typing-colored fallback block (no AI artwork; just a colored initial).
    c = _TYPE_COLORS.get(m.types[0].lower(), '#5a8ea1') if m.types else '#5a8ea1'
    initial = html.escape(m.species_display[:1].upper())
    return (f'<div class="ddcard-spriteph" style="background:{c}">{initial}</div>')


def _wr_box(wr: WinRate, label, sub):
    if not wr:
        return ''
    return (f'<div class="ddcard-wr-box"><div class="pct">{wr.pct}</div>'
            f'<div class="lbl">{html.escape(label)}</div>'
            f'<div class="sub">{html.escape(sub)}</div></div>')


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


_COVER_MAX_OPPS = 10  # truncate long coverage lists on the card; "+N more"


def _cover_html(s: Spread, link_opps=False):
    """Named opponent-coverage bullets (Dragapult-Sim style). Empty when the
    spread clears no notable tier (incl. the no-anchor fallback, where cover_*
    lists are empty). Long lists (the bulk pole can list ~10 opponents) are
    truncated with a "+N more" tail. Opponent names link to their dive row when
    ``link_opps``."""
    _nm = _name_html(link_opps)

    def _join(opps):
        head = ', '.join(_nm(o) for o in opps[:_COVER_MAX_OPPS])
        extra = len(opps) - _COVER_MAX_OPPS
        return head + (f' +{extra} more' if extra > 0 else '')
    lines = []
    if s.cover_breakpoints:
        lines.append(f'<div class="cover"><b>Breakpoints</b> '
                     f'{_join(s.cover_breakpoints)}</div>')
    if s.cover_bulkpoints:
        lines.append(f'<div class="cover"><b>Bulkpoints</b> '
                     f'{_join(s.cover_bulkpoints)}</div>')
    return ''.join(lines)


def _spread_html(s: Spread, link_opps=False):
    role = f'<div class="role">{html.escape(s.style)}</div>' if s.style else ''
    cover = _cover_html(s, link_opps)
    _fh = _flip_html(s.flip_fd, s.flip_has_bait, link_opps)
    flips = f'<div class="flips">{_fh}</div>' if _fh else ''
    return (f'<div class="ddcard-spread">{role}'
            f'<div class="iv">{html.escape(s.iv_str)}</div>'
            f'<div class="stats">{s.atk:.1f} atk / {s.def_:.1f} def / {s.hp} hp'
            f' &middot; CP {s.cp} &middot; SP #{s.sp_rank}</div>{cover}{flips}</div>')


def _col(title, items, cls):
    if not items:
        return ''
    lis = ''.join(
        f'<li>{html.escape(n)} <span style="color:#8b949e">({s:.0f})</span></li>'
        for n, s in items)
    return (f'<div class="ddcard-col {cls}"><h4>{html.escape(title)}</h4>'
            f'<ul>{lis}</ul></div>')


def render_card_html(model: CardModel, *, standalone: bool) -> str:
    """Render a CardModel to HTML. ``standalone`` wraps it in a full document
    with CARD_CSS inlined; otherwise returns just the <section> (the dive
    page already carries CARD_CSS)."""
    m = model
    name = html.escape(m.species_display)
    chips = ''.join(_chip(t) for t in m.types)
    wr = (_wr_box(m.single_iv, 'Win rate (single IV)',
                  f'{m.single_iv.pool} opponents, all {m.single_iv.scenarios} '
                  'shield scenarios')
          if m.single_iv else '')
    wr += (_wr_box(m.robust, f'Win rate (top-{m.robust.k or 512} opp IVs)',
                   f'{m.robust.pool} opponents, all {m.robust.scenarios} shield '
                   f'scenarios, each swept across its top-{m.robust.k or 512} '
                   'stat-product IVs')
           if m.robust else '')
    spreads = ''.join(_spread_html(s, link_opps=not standalone)
                      for s in m.spreads)
    wins = _col('Key wins', m.key_wins, 'wins')
    losses = _col('Key losses', m.key_losses, 'losses')
    cols = (f'<div class="ddcard-cols">{wins}{losses}</div>'
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
  <div class="ddcard-wr">{wr}</div>
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
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - dive card</title>
<style>body{{background:#0b1020;margin:0;padding:18px;}}
.ddcard{{max-width:760px;margin:0 auto;}}
{CARD_CSS}</style></head>
<body>{section}</body></html>"""
