#!/usr/bin/env python
"""Build the Worlds 2026 website pages: hub + robustness matrix + cheat sheets.

Plan: docs/worlds_prep_plan.md (products 1-3). Root-level files only
(``worlds.html`` + ``worlds-<species_id>.html``), like ``cups.html``:
same-directory links survive file:// browsing, root pages are auto-gated
by ship_surfaces.py, and the whole product retires by deleting
``worlds*.html`` + the index card.

READ-ONLY consumer of ``worlds/planes/`` via worlds_render_data --
deliberately OUTSIDE worlds_planes._WORLDS_SOURCE_FILES (a renderer edit
must not cold the Tier-1 plane bake).

Honesty rules baked in (never-present-known-wrong):

* refuses to render if any Tier-1 cell is missing from the planes
  (coverage_check) or the manifest stamps disagree with the current
  engine/gamemaster -- a partial or mixed-vintage page must not ship;
* every page carries the provenance line (engine/gamemaster/worlds_code
  stamps, bake date) and the usage-predates-rebalance flag;
* every link is emitted only against a file that EXISTS on disk (pair
  pages, dive slugs) -- a dead link fails the ship gate
  (verify_article_links). The hub's dimmed-cell popover carries its
  cheat-sheet deep link in a data- attribute, which that gate cannot
  follow, so verify_worlds resolves those refs instead;
* prose is auto-gen structure from meta.toml data only (ship-mode
  narrative policy); the "deliberately not built" block states the
  non-expert constraint.

Run before build_website_index.py (publish_website.sh ordering) so the
index card sees worlds.html.
"""
import html
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from build_website_index import _page_shell, WEBSITE_DIR  # noqa: E402
import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402
from worlds_bake import resolve_moveset  # noqa: E402

SCEN_LABELS = ['0-0', '0-1', '0-2', '1-0', '1-1', '1-2', '2-0', '2-1', '2-2']

WORLDS_CSS = """
  .badge { display: inline-block; padding: 1px 8px; border-radius: 4px;
           font-size: 12px; font-weight: 700; background: var(--surface-2);
           border: 1px solid var(--border-2); margin-left: 6px; }
  .badge-played { color: var(--win); }
  .badge-played-star { color: var(--tie); }
  .badge-model { color: var(--accent); }
  .badge-forced { color: var(--flip); }
  .badge-banned { color: var(--loss); border-color: var(--loss); }
  .prov { color: var(--text-muted); font-size: 13px; border: 1px solid
          var(--border); border-radius: 4px; padding: 8px 12px;
          margin: 14px 0; }
  .prov code { font-size: 12px; }
  table.meta, table.rejects { border-collapse: collapse; width: 100%;
          font-size: 14px; }
  table.meta th, table.meta td, table.rejects th, table.rejects td {
          border-bottom: 1px solid var(--border); padding: 5px 8px;
          text-align: left; vertical-align: top; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .table-scroll { overflow-x: auto; }
  .g9 { display: inline-grid; grid-template-columns: 14px repeat(3, 20px);
        gap: 2px; vertical-align: top; margin: 2px 10px 2px 0; }
  .g9 .sc { width: 20px; height: 20px; border-radius: 3px;
            display: inline-block; color: #ffffff; font-size: 11px;
            font-weight: 700; text-align: center; line-height: 20px; }
  .g9 .glab { color: var(--text-muted); font-size: 10px; line-height: 20px;
              text-align: center; }
  .g9 .gcorner { font-size: 9px; line-height: 10px; text-align: right;
                 color: var(--text-muted); }
  .gcap { display: block; color: var(--text-muted); font-size: 11px;
          text-align: center; margin-top: 1px; }
  .digin summary { cursor: pointer; color: var(--accent); font-size: 12px; }
  .digin table { border-collapse: collapse; font-size: 12px; margin: 6px 0; }
  .digin th, .digin td { border-bottom: 1px solid var(--border);
          padding: 2px 7px; text-align: right;
          font-variant-numeric: tabular-nums; }
  .digin th { color: var(--text-muted); font-weight: 600; }
  .digin td.amb { color: var(--flip); font-weight: 700; }
  .sc-green { background: var(--win); }
  .sc-red { background: var(--loss); }
  .sc-amber { background: var(--flip); }
  .sc-miss { background: var(--border-2); }
  /* Full-width matrix breakout (Michael 2026-08-18): the matrix is
     allowed OUT of the 760px text column so a wide window shows the
     whole grid without scrolling. width:max-content shrink-wraps the
     table; the viewport cap (minus a gutter wider than any scrollbar)
     keeps the PAGE body from ever scrolling horizontally and falls
     back to in-container scrolling on narrow viewports. left/transform
     centers it on the body's center, which is the viewport center. */
  figure.matrix-fig { margin: 0 0 10px; }
  .matrix-scroll { position: relative; left: 50%;
                   transform: translateX(-50%);
                   width: max-content; max-width: calc(100vw - 34px);
                   overflow-x: auto; border: 1px solid var(--border);
                   border-radius: 4px; }
  figcaption.matrix-cap { color: var(--text-muted); font-size: 13px;
                   margin: 0 0 18px; }
  figcaption.matrix-cap p { margin: 0 0 8px; }
  table.matrix { border-collapse: collapse; }
  table.matrix th { font-size: 11px; padding: 2px 3px;
                    color: var(--text-muted); font-weight: 600; }
  table.matrix th.colhead { writing-mode: vertical-rl;
                    transform: rotate(180deg); white-space: nowrap;
                    text-align: left; }
  table.matrix th.rowhead { text-align: right; white-space: nowrap; }
  table.matrix td { padding: 2px; border: 1px solid var(--border); }
  .gridlink { text-decoration: none; color: inherit; }
  .mini { display: grid; grid-template-columns: repeat(3, 7px);
          grid-auto-rows: 7px; gap: 1px; }
  .mini i { border-radius: 1px; }
  .mini .g { background: var(--win); } .mini .r { background: var(--loss); }
  .mini .a { background: var(--flip); }
  /* Emphasis is INVERTED vs the 2026-08-11 scheme (Michael 2026-08-18):
     the IV-decided cells are the punchline, so they render at full
     strength with no border, and the settled cells are dimmed back.
     Hover/focus restores a dimmed cell to full strength so nothing is
     permanently hard to read. */
  td.pair-dim .mini { opacity: 0.45; filter: saturate(0.55); }
  td.pair-dim:hover .mini, td.pair-dim:focus-within .mini { opacity: 1;
          filter: none; }
  .ndbtn { background: none; border: 0; padding: 0; margin: 0;
           display: block; cursor: pointer; }
  .ndbtn:focus-visible { outline: 2px solid var(--accent);
           outline-offset: 1px; }
  .ndpop { position: absolute; z-index: 30; max-width: 340px;
           background: var(--surface-2); color: var(--text);
           border: 1px solid var(--border-2); border-radius: 6px;
           padding: 10px 26px 10px 12px; font-size: 13px;
           line-height: 1.45; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.3); }
  .ndpop[hidden] { display: none; }
  .ndpop p { margin: 0 0 6px; }
  .ndpop a { display: block; margin-top: 5px; }
  .ndpop button.ndpop-x { position: absolute; top: 2px; right: 4px;
           background: none; border: 0; color: var(--text-muted);
           font-size: 15px; line-height: 1; cursor: pointer;
           padding: 2px 5px; }
  .legend { color: var(--text-muted); font-size: 13px; margin: 8px 0 16px; }
  .legend .sc { width: 12px; height: 12px; vertical-align: -1px; }
  table.sheet { border-collapse: collapse; width: 100%; font-size: 14px; }
  table.sheet th, table.sheet td { border-bottom: 1px solid var(--border);
          padding: 6px 8px; text-align: left; vertical-align: middle; }
  .flags { color: var(--flip); font-size: 12px; white-space: nowrap; }
  .mband { color: var(--text-muted); font-size: 12px;
           font-variant-numeric: tabular-nums; white-space: nowrap; }
  .notbuilt { border-left: 3px solid var(--border-2); padding: 2px 12px;
              color: var(--text-muted); font-size: 14px; margin: 16px 0; }
"""

BADGE_CLASS = {'PLAYED': 'badge-played', 'PLAYED*': 'badge-played-star',
               'MODEL': 'badge-model', 'FORCED': 'badge-forced'}


def esc(s):
    return html.escape(str(s), quote=True)


def rule_divergence(badge, rule):
    """How a badge_rule disagrees with the literal badge, as display
    text, or '' when there is nothing to say.

    Two cases the old ``if rule and rule != badge`` guard got wrong:

    * FORCED is editorial BY DEFINITION -- classify_badge never returns
      it, so a FORCED entry's rule is always empty. That is not a
      divergence and printing one would be noise on every FORCED row.
    * an empty rule under any OTHER badge means the mechanical rule no
      longer awards it, which is exactly what must be SHOWN -- and the
      old guard silently hid it, because '' is falsy. Live PvPoke ranks
      move: on 2026-08-18 a rankings refresh pushed Sableye (Shadow)
      from rank 30 to 31, so its rule went MODEL -> '' while its literal
      badge stayed MODEL, and the page would have kept asserting MODEL
      with no caveat.
    """
    if badge == 'FORCED' or rule == badge:
        return ''
    return rule or 'no badge'


def badge_html(entry_or_badge):
    """Badge span. Given a full entry, a badge_rule that disagrees with
    the literal badge is SHOWN (the plan records both precisely so the
    divergence is visible -- e.g. Altaria (Shadow) is PLAYED because it
    was split out of a pooled PLAYED row, while the per-variant rule
    says MODEL)."""
    if isinstance(entry_or_badge, dict):
        badge = entry_or_badge['badge']
        rule = entry_or_badge.get('badge_rule', badge)
    else:
        badge, rule = entry_or_badge, entry_or_badge
    cls = BADGE_CLASS.get(badge, 'badge-model')
    label = esc(badge)
    div = rule_divergence(badge, rule)
    if div:
        label += f' <small>(rule: {esc(div)})</small>'
    return f'<span class="badge {cls}">{label}</span>'


def display_moveset(entry):
    """The moveset in SIMMED slot order. meta.toml alphabetizes ids; the
    bake restores PvPoke-default order via resolve_moveset, and slot
    order is PvPoke-visible for equal-energy charged moves (Empoleon,
    Togekiss, Aegislash, Sableye) -- the page must show the order the
    numbers were produced under."""
    fast_id, charged_ids = resolve_moveset(entry)
    id2name = dict(zip(entry['charged_move_ids'], entry['charged_moves']))
    charged = [id2name.get(c, c) for c in charged_ids]
    return entry['fast_move'], charged


def sheet_filename(species_id):
    return f'worlds-{species_id}.html'


def sheet_row_id(opp_species_id):
    """Anchor id of a cheat sheet's row for ``opp_species_id``. ONE
    definition, used both to stamp the row (render_cheat_sheet) and to
    aim the hub popover at it, so the two cannot drift."""
    return f'vs-{opp_species_id}'


# PvPoke's own rewrite for the short battle path accepts only
# [a-zA-Z_]+ for the two species segments (pvpoke src/.htaccess rule
# "battle/([\\d-]+)/([a-zA-Z_]+)/([a-zA-Z_]+)/(\\d+)"). Any id outside
# that charset would 404, so we emit NO link rather than a broken one.
_PVPOKE_ID_OK = re.compile(r'[A-Za-z_]+\Z')


def pvpoke_battle_url(focal_id, opp_id, cp=1500, shields='11'):
    """PvPoke single-battle URL at BOTH sides' PvPoke defaults.

    Deliberately the bare-speciesId form (no level/IV/moveset segments):
    PvPoke's parser takes a one-segment poke string as "just select this
    species" and applies its own default IVs, level and moveset
    (Interface.js: ``if(arr.length == 1) setPokemon(val)``). That is
    what the popover advertises -- it is NOT our probe spread, and the
    label says so. Returns None when either id is unlinkable."""
    if not (_PVPOKE_ID_OK.match(focal_id) and _PVPOKE_ID_OK.match(opp_id)):
        return None
    return f'https://pvpoke.com/battle/{cp}/{focal_id}/{opp_id}/{shields}/'


def dive_slug_map(entries, website_dir=WEBSITE_DIR):
    """{species_id: '<slug>/index.html'} for entries whose classic dive
    dir actually exists -- link only what resolves (ship-gate rule).
    Candidate slugs are generated, existence-checked, never guessed
    into links."""
    out = {}
    for e in entries:
        base = e['species'].lower()
        cands = []
        if '(' in base:  # regional/form parens: "corsola (galarian)"
            stem, paren = base.split('(', 1)
            stem, paren = stem.strip(), paren.strip(') ').strip()
            cands += [f'{paren}-{stem}', f'{stem}-{paren}']
        else:
            cands.append(base.replace(' ', '-'))
        if e['species_id'] == 'aegislash_shield':
            cands = ['aegislash-shield']
        fast_tok = e['fast_move_id'].lower().replace('_', '-')
        slugs = []
        for c in cands:
            c = c.replace(' ', '-')
            if e['shadow']:
                slugs += [f'{c}-shadow-great-league',
                          f'{c}-shadow-{fast_tok}-great-league']
            else:
                slugs += [f'{c}-great-league',
                          f'{c}-{fast_tok}-great-league']
        for slug in slugs:
            if (Path(website_dir) / slug / 'index.html').exists():
                out[e['species_id']] = f'{slug}/index.html'
                break
    return out


_LETTER = {'green': 'W', 'red': 'L', 'amber': '?'}


def _pct(f):
    """Exact-honest percentage: only true 0/1 print as 0%/100%; an
    IV-decided fraction keeps a decimal so 511/512 shows as 99.8%,
    never a settled-looking 100% (adversarial-verify finding)."""
    f = float(f)
    if f in (0.0, 1.0):
        return f'{100 * f:.0f}%'
    return f'{100 * f:.1f}%'


def _grid9(slice_, opp_name, bait_label, alt_slice=None):
    """One 3x3 scenario grid in PvPoke's battle-matrix layout (rows =
    own shields top to bottom, columns = opponent shields left to
    right -- Michael 2026-08-10, for visual consistency with PvPoke's
    matchup pages). Each cell carries a W/L/? letter (the outcome must
    not be color-alone: phones cannot hover and the three fills are
    near-isoluminant in grayscale) and an exact-count tooltip.

    ``alt_slice``: the collapsed bait-independent form (Michael
    2026-08-11) -- the caller has verified the two bait modes' win
    counts are IDENTICAL per scenario, so one grid represents both
    exactly; only the margin band may differ, so the tooltip unions it
    and says so."""
    head = ('<span class="gcorner"></span>'
            + ''.join(f'<span class="glab">{c}</span>' for c in '012'))
    if slice_ is None:
        cells = ''.join(
            f'<span class="glab">{r}</span>' + ''.join(
                '<span class="sc sc-miss"></span>' for _ in range(3))
            for r in '012')
        return (f'<span class="g9" title="no plane">{head}{cells}</span>'
                f'<span class="gcap">{esc(bait_label)}</span>')
    parts = [head]
    for i, st in enumerate(slice_.status):
        if i % 3 == 0:
            parts.append(f'<span class="glab">{i // 3}</span>')
        lo, hi = int(slice_.margin_lo[i]), int(slice_.margin_hi[i])
        if alt_slice is not None:
            lo = min(lo, int(alt_slice.margin_lo[i]))
            hi = max(hi, int(alt_slice.margin_hi[i]))
            band = f'margin {lo:+d}..{hi:+d} across both modes'
        else:
            band = f'margin {lo:+d}..{hi:+d}'
        tip = (f'{bait_label} {SCEN_LABELS[i]} vs {opp_name}: beats '
               f'{int(slice_.wins[i])} of {slice_.n} spreads ({band})')
        parts.append(f'<span class="sc sc-{st}" title="{esc(tip)}">'
                     f'{_LETTER[st]}</span>')
    return (f'<span class="g9">{"".join(parts)}</span>'
            f'<span class="gcap">{esc(bait_label)}</span>')


_SLICE_COLS = [(s, c, b) for b in (True, False)
               for s in ('rank1', 'maxatk512') for c in ('top512', 'atkband')]
_SLICE_ABBR = {('rank1', 'top512'): 'r1/512', ('rank1', 'atkband'): 'r1/atk',
               ('maxatk512', 'top512'): 'maxA/512',
               ('maxatk512', 'atkband'): 'maxA/atk'}


def pair_link_map(website_dir=WEBSITE_DIR):
    """{frozenset({a, b}): filename} for pair detail pages that EXIST on
    disk -- links are only emitted against real files (ship-gate rule)."""
    out = {}
    for p in Path(website_dir).glob('worlds-pair-*.html'):
        stem = p.name[len('worlds-pair-'):-len('.html')]
        if '--' in stem:
            a, b = stem.split('--', 1)
            out[frozenset((a, b))] = p.name
    return out


def joint_iv_link_map(website_dir=WEBSITE_DIR):
    """{frozenset({focal_slug, opp_slug}): (filename, display)} for
    PUBLISHED joint-IV robustness deep pages -- pairs/*.toml whose
    publish slug exists on disk (links only against real files, the
    ship-gate rule pair_link_map follows)."""
    from joint_iv_config import default_publish_slug, load_pair
    out = {}
    for toml in sorted((REPO / 'pairs').glob('*.toml')):
        try:
            cfg = load_pair(toml)
        except Exception:
            continue
        slug = default_publish_slug(cfg)
        if not (Path(website_dir) / slug).exists():
            continue
        focal = cfg.focal + (' (Shadow)' if cfg.focal_shadow else '')
        opp = cfg.opponent + (' (Shadow)' if cfg.opp_shadow else '')
        out[frozenset((cfg.focal_slug, cfg.opp_slug))] = (
            slug, f'{focal} vs {opp}')
    return out


def _digin(cell, opp_name, pair_link=None, pair_amber=False, deep=None):
    """Per-row expansion: the FULL Tier-1 data for this direction as
    exact beats-N counts -- every probe spread x cohort x bait slice,
    per scenario. This is the interim dig-in for IV-decided cells until
    the session-4 per-pair detail pages (closed-form atk/def cutoffs +
    full 4096x512 grids) replace it with links."""
    heads = ''.join(
        f'<th>{"bait" if b else "no-bait"}<br>{_SLICE_ABBR[(s, c)]}</th>'
        for s, c, b in _SLICE_COLS)
    rows = []
    for i in range(9):
        tds = []
        for s, c, b in _SLICE_COLS:
            sl = cell.slices.get((s, c, b))
            if sl is None:
                tds.append('<td>-</td>')
                continue
            amb = ' class="amb"' if sl.status[i] == 'amber' else ''
            tds.append(f'<td{amb}>{int(sl.wins[i])}/{sl.n}</td>')
        rows.append(f'<tr><th>{SCEN_LABELS[i]}</th>{"".join(tds)}</tr>')
    if pair_link:
        link_html = (f' <a href="{esc(pair_link)}">Full detail page (all '
                     '4096 of your spreads + reach/deny cutoffs)</a>.')
    elif pair_amber:
        link_html = (' The full-grid detail page for this pair is '
                     'deferred by the Tier-2 bake budget.')
    else:
        # Non-amber pairs were never on the Tier-2 worklist -- saying
        # "deferred" here was false for 128 rows (verify catch,
        # 2026-08-11).
        link_html = (' No detail page: this pair is not flagged '
                     'IV-decided.')
    if deep:
        link_html += (f' <a href="{esc(deep[0])}">Deep joint-IV analysis '
                      f'({esc(deep[1])}: every spread of both sides, '
                      'breakpoints, denial)</a>.')
    if getattr(cell, 'probe_missed', lambda: False)():
        link_html += (
            ' NOTE: the probe slices above look settled -- the '
            'IV-dependence here was found by the FULL Tier-2 grid (all '
            '4096 focal spreads), which the two-probe screen missed; '
            'the detail page shows where.')
    return (f'<details class="digin"><summary>details</summary>'
            f'<div class="table-scroll"><table>'
            f'<tr><th>scen</th>{heads}</tr>{"".join(rows)}</table></div>'
            f'<p class="legend">Exact spreads-beaten counts vs {esc(opp_name)}'
            ' for every slice: probe spread (r1 = rank-1 SP, maxA = max '
            'attack in top-512) x opponent cohort (512 = top-512 SP, atk = '
            'best-SP-per-attack-IV band; the cohorts overlap) x bait mode. '
            f'Highlighted = IV-decided.{link_html}</p></details>')


def _mini_cell(row, focal_name, opp_name, pair_link=None,
               focal_id=None, opp_id=None):
    """Matrix cell: 3x3 mini-grid of headline per-scenario status.

    Emphasis (Michael 2026-08-18, inverting the 2026-08-11 scheme): an
    IV-DECIDED direction renders at full strength and unadorned; a
    direction that is settled in every tested slice is dimmed back
    (``pair-dim``), so the punchline cells pop instead of the settled
    ones carrying the loud outline.

    An IV-decided cell whose pair page exists links to it (unchanged).
    A cell with NO pair page used to be inert; it now opens the
    dismissible not-IV-decided popover, whose text/links the hub script
    builds from these data attributes."""
    if row.get('missing'):
        return '<td title="missing plane">?</td>'
    cls = {'green': 'g', 'red': 'r', 'amber': 'a'}
    boxes = ''.join(f'<i class="{cls[s]}"></i>' for s in row['status'])
    tips = ', '.join(f'{SCEN_LABELS[i]} {_pct(f)}'
                     for i, f in enumerate(row['frac']))
    tip = f'{focal_name} vs {opp_name} (rank-1 spread, top-512, bait): {tips}'
    td_cls = '' if row['amber'] else ' class="pair-dim"'
    mini = f'<span class="mini">{boxes}</span>'
    # Link whenever the pair page EXISTS -- gating on this direction's
    # amber flag left 8 pairs linked from only one matrix cell while
    # both cheat sheets linked them (verify catch, 2026-08-11).
    if pair_link:
        mini = f'<a href="{esc(pair_link)}">{mini}</a>'
    elif focal_id and opp_id:
        # No detail page for this pair. Two honest cases, and the
        # popover must not conflate them: settled-in-every-slice (no
        # page was ever owed) vs IV-decided-but-Tier-2-deferred.
        kind = 'deferred' if row['amber'] else 'clean'
        pv = pvpoke_battle_url(focal_id, opp_id)
        pv_attr = f' data-pv="{esc(pv)}"' if pv else ''
        mini = (f'<button type="button" class="ndbtn" data-kind="{kind}" '
                f'data-f="{esc(focal_name)}" data-o="{esc(opp_name)}" '
                f'data-sheet="{sheet_filename(focal_id)}'
                f'#{sheet_row_id(opp_id)}"{pv_attr}>{mini}</button>')
    return f'<td{td_cls} title="{esc(tip)}">{mini}</td>'


def injected_entries(meta):
    """Meta entries running a move the PINNED sim gamemaster does not
    list in their species pool (meta.toml ``injected_move_ids``; see
    worlds_bake.preflight_moveset_legality). Data-driven, so the
    disclosure appears and disappears with the declaration."""
    return [e for e in meta['entries'] if e.get('injected_move_ids')]


def injection_chip(entry):
    """Short inline marker for a moveset cell. Empty for entries with no
    injection, so nothing is claimed about the other 31."""
    if not entry.get('injected_move_ids'):
        return ''
    moves = ' + '.join(esc(m) for m in entry.get('injected_moves')
                       or entry['injected_move_ids'])
    return (f' <span class="mband">({moves} injected: the pinned sim '
            'gamemaster predates the CD)</span>')


DEEP_ANALYSIS_PAGES = {
    # (species, "which fork is this") -> a root-level page carrying the
    # full treatment of that fork. Linked only if the file exists.
    'Thievul': ('thievul-lickilicky-robustness.html',
                'the full Night Slash vs Play Rough treatment'),
}


def fork_siblings(entry, entries):
    """Other meta entries that are the SAME species+shadow as this one --
    i.e. the other arms of a moveset fork. Empty for every unforked
    entry, which is all of them until 2026-08-18."""
    return [e for e in entries
            if e['species'] == entry['species']
            and bool(e['shadow']) == bool(entry['shadow'])
            and e['species_id'] != entry['species_id']]


def fork_html(entry, entries, website_dir=WEBSITE_DIR):
    """Cross-link block for a fork arm: names the fork axis in one line,
    links every sibling arm's cheat sheet, and links the deep-analysis
    page when one exists on disk (ship-gate rule: never link a file we
    have not checked for)."""
    sibs = fork_siblings(entry, entries)
    if not sibs:
        return ''
    mine = ' + '.join(esc(m) for m in display_moveset(entry)[1])
    links = []
    for s in sibs:
        theirs = ' + '.join(esc(m) for m in display_moveset(s)[1])
        links.append(f'<a href="{sheet_filename(s["species_id"])}">'
                     f'{esc(s["name"])}</a> ({theirs})')
    deep = DEEP_ANALYSIS_PAGES.get(entry['species'])
    deep_html = ''
    if deep and (Path(website_dir) / deep[0]).exists():
        deep_html = (f' For {esc(deep[1])}, see '
                     f'<a href="{esc(deep[0])}">{esc(deep[0])}</a>.')
    return ('<p class="section-intro"><strong>This is one arm of a '
            f'{len(sibs) + 1}-way moveset fork.</strong> '
            f'{esc(entry["name"])} runs {mine}; the other '
            f'{"arm is" if len(sibs) == 1 else "arms are"} '
            + ', '.join(links) + '. Same species, same fast move, same '
            'stats and same IV ladder - only the second charged move '
            'differs, so every row below is directly comparable between '
            f'the arms.{deep_html}</p>')


def injection_html(entry):
    """The full, unabbreviated disclosure block for an entry's own cheat
    sheet. Prints meta.toml's authored injection_note verbatim -- the
    reader is entitled to the whole provenance on the page whose numbers
    depend on it, not a summary of it."""
    if not entry.get('injected_move_ids'):
        return ''
    moves = ' + '.join(esc(m) for m in entry.get('injected_moves')
                       or entry['injected_move_ids'])
    note = entry.get('injection_note', '')
    return ('<div class="prov"><strong>Move injection: '
            f'{moves}.</strong> {esc(note)} Every number on this page was '
            'simmed with that move; the rest of the moveset, and both '
            "sides' stats, come from the pinned gamemaster unchanged.</div>")


def provenance_html(meta, manifest):
    baked = sorted({e.get('baked', '?')
                    for e in manifest.get('entries', {}).values()})
    # Site-wide disclosure: an injected move changes the numbers on every
    # surface that pair touches, not just its own cheat sheet, so it
    # rides the provenance line every Worlds page already carries.
    inj = injected_entries(meta)
    inj_html = ''
    if inj:
        parts = ', '.join(
            f'{esc(e["name"])} ({" + ".join(esc(m) for m in (e.get("injected_moves") or e["injected_move_ids"]))})'
            for e in inj)
        inj_html = (
            f'<strong>Community Day move injected for {parts}:</strong> the '
            'pinned sim gamemaster predates that Community Day, so the move '
            'was admitted into the species pool deliberately; upstream '
            'PvPoke already lists it. Full provenance on the affected '
            f'{"entry\'s" if len(inj) == 1 else "entries\'"} cheat '
            f'{"sheet" if len(inj) == 1 else "sheets"}. ')
    return (
        '<div class="prov">'
        f'Format: <strong>{esc(meta["format"])}</strong>, '
        f'{esc(meta["mechanics"])}. '
        f'Usage: {meta["usage_teams_recent"]} recent teams across '
        f'{meta["usage_events_recent"]} open-GL events (Dracoviz corpus, '
        f'events since {esc(meta["usage_recent_cutoff"])}; the EUIC/LAIC/'
        'NAIC Internationals are excluded as limited-meta events). Shares '
        'are team-level and per-variant (Shadow counted separately from '
        'the base form). '
        '<strong>The June 2026 rebalance went live in-game 2026-06-02</strong> '
        '(1 p.m. PDT, with the GBL Season 27 switchover), so all recent '
        'corpus events predate it EXCEPT the final one - Turin, '
        '2026-06-06/07, played post-rebalance. Model-side ranks are fully '
        'post-rebalance. '
        f'Sim: legacy engine, planes baked {esc("/".join(baked))}, '
        f'engine <code>{esc(manifest["engine"])}</code>, gamemaster '
        f'<code>{esc(manifest["gamemaster"])}</code>, producer '
        f'<code>{esc(manifest["worlds_code"])}</code>. '
        'Cohorts: opponent top-512 by stat product, plus best-SP-per-'
        'attack-IV band (labeled separately, never pooled). Focal probe '
        'spreads: rank-1 SP and max-attack within top-512. '
        + inj_html + '</div>')


LEGEND = ('<p class="legend"><span class="sc sc-green">W</span> beats every '
          'cohort spread &nbsp; <span class="sc sc-amber">?</span> '
          'IV-decided (some spreads win, some lose) &nbsp; <span class="sc '
          'sc-red">L</span> beats no cohort spread (an exact 500-500 tie '
          'counts as not beaten). Every 3x3 grid uses PvPoke\'s '
          'battle-matrix layout: rows = own shields 0/1/2 top to bottom, '
          'columns = opponent shields left to right (scenario labels read '
          'own-opp, e.g. 2-1 = you keep two shields, they keep one). '
          'Bait modes '
          'apply to the FOCAL side only -- in the no-bait line the '
          'opponent still baits, so the two directions of a no-bait pair '
          'describe different battles and their sheets need not mirror. '
          'Hover (desktop) for exact spread counts and score margins; on '
          'phones the cheat sheets\' W/L/? letters and IV-decided column '
          'carry the outcome. The hub matrix itself is a color-only '
          'overview -- its row links open the text-carrying cheat sheet. '
          'IV-decided pairs with baked Tier-2 grids link to a full '
          'per-pair detail page -- click the 3x3 grid itself (cheat '
          'sheets), the matrix cell (hub), or the details expander; any '
          'budget-deferred pairs are listed on the hub.</p>')

# One shared popover element + one delegated listener for the whole
# matrix: ~130 inert cells would otherwise need ~130 hidden divs. All
# reader-visible strings are ASCII (verify_no_unicode_dashes does not
# see inside <script>; see the TODO ship-gate-gap note).
POPOVER_HTML = """
<div class="ndpop" id="ndpop" hidden role="dialog" aria-live="polite"
     aria-labelledby="ndpop-msg">
  <button type="button" class="ndpop-x" id="ndpop-x"
          aria-label="Close">x</button>
  <p id="ndpop-msg"></p>
  <a id="ndpop-sheet"></a>
  <a id="ndpop-pv" target="_blank"
     rel="noopener">PvPoke default-vs-default battle</a>
</div>
<script>
(function () {
  var pop = document.getElementById('ndpop');
  if (!pop) { return; }
  var msg = document.getElementById('ndpop-msg');
  var sheet = document.getElementById('ndpop-sheet');
  var pv = document.getElementById('ndpop-pv');
  var opener = null;
  function hide() { pop.hidden = true; opener = null; }
  function show(btn) {
    var f = btn.getAttribute('data-f');
    var o = btn.getAttribute('data-o');
    msg.textContent = btn.getAttribute('data-kind') === 'deferred'
      ? f + ' vs ' + o + ': IV-decided, but the full-grid detail page'
        + ' for this pair is deferred by the Tier-2 bake budget. The'
        + ' cheat sheet still carries the full Tier-1 data.'
      : f + ' vs ' + o + ': not IV-decided in any tested slice. Every'
        + ' probe spread, opponent cohort and bait mode gives the same'
        + ' outcome in all 9 shield scenarios, so there is no per-pair'
        + ' detail page for it.';
    sheet.href = btn.getAttribute('data-sheet');
    sheet.textContent = 'Cheat sheet row: ' + f + ' vs ' + o;
    var url = btn.getAttribute('data-pv');
    if (url) { pv.href = url; pv.hidden = false; }
    else { pv.removeAttribute('href'); pv.hidden = true; }
    pop.hidden = false;
    var r = btn.getBoundingClientRect();
    var left = r.left + window.pageXOffset + (r.width / 2)
               - (pop.offsetWidth / 2);
    var max = document.documentElement.clientWidth - pop.offsetWidth - 8;
    if (left > max) { left = max; }
    if (left < 8) { left = 8; }
    pop.style.left = left + 'px';
    pop.style.top = (r.bottom + window.pageYOffset + 6) + 'px';
    opener = btn;
  }
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('.ndbtn') : null;
    if (btn) {
      ev.preventDefault();
      if (opener === btn) { hide(); } else { show(btn); }
      return;
    }
    if (!pop.hidden && !pop.contains(ev.target)) { hide(); }
  });
  document.getElementById('ndpop-x').addEventListener('click', function () {
    var b = opener;
    hide();
    if (b) { b.focus(); }
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && !pop.hidden) {
      var b = opener;
      hide();
      if (b) { b.focus(); }
    }
  });
}());
</script>
"""

NOT_BUILT = (
    '<div class="notbuilt"><p><strong>Deliberately not built:</strong> '
    'team composition, lead/switch/closer roles, energy management lines, '
    'or "best 6" advice. This analysis is IV-robustness arithmetic on 1v1 '
    'sims, not necessarily expert-level competitive advice. What IS '
    'here: who beats whom across the opponent\'s plausible IV spreads, '
    'per shield scenario, both bait modes.</p></div>')


def render_meta_table(entries, slug_map):
    rows = []
    for e in entries:
        fast, charged = display_moveset(e)
        moves = f'{esc(fast)} / ' + ' + '.join(esc(m) for m in charged)
        src = e['moveset_source']
        mv_note = (f' <span class="mband">(field-modal '
                   f'{e["moveset_modal_pct"]:.0f}%, n={e["moveset_n"]}'
                   + ('; differs from PvPoke default' if e['default_disagrees']
                      else '') + ')</span>') if src == 'modal' else ''
        dive = slug_map.get(e['species_id'])
        dive_html = (f' <a class="chip" href="{esc(dive)}">dive</a>'
                     if dive else '')
        name = (f'<a href="{sheet_filename(e["species_id"])}">'
                f'{esc(e["name"])}</a>')
        rows.append(
            f'<tr><td>{name}{badge_html(e)}{dive_html}</td>'
            f'<td class="num">{e["usage_recent_pct"]:.1f}%</td>'
            f'<td class="num">{e["current_rank"]}</td>'
            f'<td>{moves}{mv_note}{injection_chip(e)}</td></tr>')
    return ('<div class="table-scroll"><table class="meta">'
            '<tr><th>Entry (cheat sheet)</th><th class="num">recent '
            'usage</th><th class="num">rank</th><th>moveset</th></tr>'
            + ''.join(rows) + '</table></div>')


def render_rejects_table(rejects):
    rows = []
    for r in rejects:
        badge = ('<span class="badge badge-banned">BANNED</span>'
                 if r['banned'] else '')
        cur = r.get('current_rank')
        rows.append(
            f'<tr><td>{esc(r["name"])}{badge}</td>'
            f'<td class="num">{r["usage_recent_pct"]:.1f}%</td>'
            f'<td class="num">{cur if cur is not None else "-"}</td>'
            f'<td>{esc(r["reason"])}</td></tr>')
    return ('<div class="table-scroll"><table class="rejects">'
            '<tr><th>Candidate</th><th class="num">recent usage</th>'
            '<th class="num">rank</th><th>why not in the meta</th></tr>'
            + ''.join(rows) + '</table></div>')


def render_matrix(entries, cells, links=None):
    ids = [e['species_id'] for e in entries]
    names = {e['species_id']: e['name'] for e in entries}
    links = links or {}
    rows_html = ['<tr><th></th>' + ''.join(
        f'<th class="colhead">{esc(names[o])}</th>' for o in ids) + '</tr>']
    summary = wrd.matrix_summary(cells, entries)
    for f in ids:
        tds = []
        for o in ids:
            if f == o:
                tds.append('<td></td>')
            else:
                tds.append(_mini_cell(summary[(f, o)], names[f], names[o],
                                      links.get(frozenset((f, o))),
                                      focal_id=f, opp_id=o))
        rows_html.append(
            f'<tr><th class="rowhead"><a href="{sheet_filename(f)}">'
            f'{esc(names[f])}</a></th>' + ''.join(tds) + '</tr>')
    return ('<div class="matrix-scroll"><table class="matrix">'
            + ''.join(rows_html) + '</table></div>')


def tier2_status_html(entries, fn, deferred, n_pages):
    """Hub block: what Tier-2 has baked, what is deferred, and the
    MEASURED false-negative rate of the amber screen (or an explicit
    not-yet-measured line -- never silence)."""
    names = {e['species_id']: e['name'] for e in entries}
    if fn is None:
        fn_html = ('<p class="section-intro">Amber-screen false-negative '
                   'rate: not yet measured (clean-sample grids not '
                   'baked).</p>')
    else:
        worst_impact = max((r[3] for r in fn['pairs'] if r[1]),
                           default=0.0)
        worst_cell = max((r[2] for r in fn['pairs'] if r[1]), default=0.0)
        fn_html = (
            f'<p class="section-intro">Amber-screen check: of '
            f'{fn["n"]} sampled clean (not-flagged) pairs given the full '
            f'4096-spread treatment, <strong>{fn["fn"]}</strong> show '
            'some IV-dependence in the top-512 x top-512 block. Worst '
            f'case, {100 * worst_impact:.1f}% of a focal\'s top-512 '
            'spreads have an outcome that depends on the opponent\'s IV '
            f'roll in some scenario (largest mixed-cell share of a '
            f'block: {100 * worst_cell:.2f}%). The amber flags are a '
            'screen, not a proof of settledness; detail pages select '
            'their scenarios from the full grids, not the screen.</p>')
    if deferred:
        listed = ', '.join(f'{esc(names.get(a, a))} / {esc(names.get(b, b))}'
                           for a, b in deferred[:20])
        more = (f' (+{len(deferred) - 20} more)'
                if len(deferred) > 20 else '')
        def_html = (f'<p class="section-intro">{len(deferred)} IV-decided '
                    f'pairs are deferred by the Tier-2 bake budget (usage-'
                    f'ranked worklist): {listed}{more}. A deferred pair '
                    'still has full Tier-1 data on the cheat sheets.</p>')
    else:
        # The zero state is STATED, not silent. This block previously
        # read "N IV-decided pairs are deferred by the Tier-2 bake
        # budget", so rendering nothing when the backlog clears would
        # leave a reader unable to tell complete coverage from a section
        # that quietly disappeared (2026-08-19, when the last 22 were
        # baked and the deferred list hit zero).
        def_html = ('<p class="section-intro">Nothing is deferred: every '
                    'IV-decided pair in the meta has a full-grid detail '
                    'page.</p>')
    cmp_html = ''
    if (Path(WEBSITE_DIR) / 'worlds-cmp.html').exists():
        cmp_html = ('<p class="section-intro"><a href="worlds-cmp.html">'
                    'CMP board</a>: meta-wide charge-move-priority order '
                    'with per-pair IV flip thresholds for the contested '
                    'pairs.</p>')
    if (Path(WEBSITE_DIR) / 'worlds-explorer.html').exists():
        cmp_html += ('<p class="section-intro"><a href="worlds-explorer'
                     '.html">IV explorer</a>: enter your IVs and level, '
                     'see the breakpoints you reach and the bulkpoints '
                     f'you hold vs all {len(entries)} entries.</p>')
    return (f'<h2>Per-pair detail pages ({n_pages} baked)</h2>'
            f'{fn_html}{def_html}{cmp_html}')


def render_hub(meta, cells, manifest, slug_map, links=None, fn=None,
               deferred=None, jmap=None):
    entries = meta['entries']
    n_amber = sum(1 for c in cells.values() if not c.missing and c.amber)
    deep_html = ''
    if jmap:
        items = ''.join(
            f'<li><a href="{esc(slug)}">{esc(label)}</a></li>'
            for slug, label in sorted(jmap.values(), key=lambda v: v[1]))
        deep_html = (
            '<h2>Deep joint-IV analyses</h2>'
            '<p class="section-intro">Hand-picked high-usage IV-decided '
            'pairs get the full treatment: every spread of BOTH sides '
            f'(4096 x 4096 x 9 shield scenarios per moveset/bait grid), '
            'closed-form breakpoints, denial tech for the other side, and '
            'a paste-your-collection checker. The cheat-sheet rows for '
            'these pairs link the same pages.</p>'
            f'<ul class="deeplist">{items}</ul>')
    # Order (Michael 2026-08-18): matrix FIRST -- it is the punchline --
    # then the meta table, then the candidates, with format/provenance
    # last. The matrix's reading instructions moved from above the grid
    # to a figcaption below it, so the picture is the first thing on
    # screen.
    body = f"""
<h2>Robustness matrix</h2>
<figure class="matrix-fig">
{render_matrix(entries, cells, links)}
<figcaption class="matrix-cap">
<p>Row = the focal Pokemon (its rank-1-SP spread), column = the opponent
(its top-512 SP spreads). Each cell shows all 9 shield scenarios.
<strong>IV-decided cells are drawn at full strength</strong>; a cell whose
outcome is settled in every tested slice (either probe spread, either
cohort, either bait mode) is dimmed back - {n_amber} of {len(cells)}
directions are IV-decided. Never aggregated to one number.</p>
<p>Click any cell that has a per-pair detail page to open it - a pair earns
one by being IV-decided in EITHER direction, so a dimmed cell can still be
a link. A cell with no detail page opens a short note instead, with links
to that pair's cheat sheet row and to the equivalent battle on pvpoke.com
at PvPoke's own default IVs and movesets (not our probe spread). Hover or
keyboard-focus restores a dimmed cell to full strength.</p>
{LEGEND}
<p>Accessibility note: the dimmed fills carry less contrast than the
full-strength ones, and dimmed cells are exactly the settled ones, so
nothing on this page depends on reading them. The hub matrix stays a
color-only overview either way; the text alternative is the cheat sheet,
reachable from each row label, from the dimmed-cell note, and from the
meta table below.</p>
</figcaption>
</figure>
{tier2_status_html(entries, fn, deferred or [], len(links or {}))}
{deep_html}
<h2>The meta ({len(entries)} entries)</h2>
<p class="section-intro">Badge rules (mechanical): PLAYED = top-{meta["badge_usage_top"]}
recent usage AND top-{meta["badge_rank_top"]} current rank; PLAYED* = top-usage but
current rank sank below {meta["badge_rank_top"]}; MODEL = current top-{meta["badge_rank_top"]}
rank with no meaningful tournament footprint; FORCED = editorial include
(reason shown on its cheat sheet). Movesets are the field-modal set when
modal share >= {meta["moveset_modal_min_pct"]:.0f}%, else the PvPoke default;
disagreements are shown as data. <strong>The {len(entries)}-entry list
itself is a human decision</strong> (recorded in scripts/worlds_meta.py),
not rule-derived: the badges label the chosen list mechanically, and some
current top-{meta["badge_rank_top"]}-rank species stayed out (they appear
in the candidates table below). Moveset slot order shown is the order the
sims ran under (PvPoke default order when the sets agree).</p>
{render_meta_table(entries, slug_map)}
<h2>Candidates that stayed out</h2>
<p class="section-intro">The usage top-{meta["reject_top_n"]} that did not
make the meta, plus the banned row. Collapsed-rank PLAYED* entries above are
shown as data; we do not claim nerf vs model error.</p>
{render_rejects_table(meta['rejects'])}
{NOT_BUILT}
<h2>Format and provenance</h2>
{provenance_html(meta, manifest)}
<p><a href="index.html">Back to all dives</a></p>
{POPOVER_HTML}
"""
    return _page_shell(
        title='Worlds 2026 - Great League IV robustness',
        heading='Worlds 2026: open Great League robustness',
        intro_html=('<p>Which meta matchups are decided by IVs? A 9-scenario '
                    'robustness matrix, per-species cheat sheets (click a '
                    'row label or a name in the meta table), and the '
                    'candidate table for the Worlds 2026 open Great League '
                    'meta. Format, usage corpus and sim provenance are at '
                    'the foot of the page.</p>'),
        body_html=body,
        extra_css=WORLDS_CSS)


def render_cheat_sheet(entry, meta, cells, manifest, slug_map, links=None,
                       website_dir=WEBSITE_DIR, jmap=None):
    entries = meta['entries']
    names = {e['species_id']: e['name'] for e in entries}
    links = links or {}
    sid = entry['species_id']
    rows = []
    for opp in entries:
        oid = opp['species_id']
        if oid == sid:
            continue
        cell = cells[(sid, oid)]
        bait = cell.slices.get(('rank1', 'top512', True))
        nobait = cell.slices.get(('rank1', 'top512', False))
        flags = cell.amber_scenarios()
        flag_html = ('<span class="flags">IVs decide: '
                     + ', '.join(SCEN_LABELS[i] for i in flags) + '</span>'
                     if flags else '')
        # Closest-scenario readout (Michael 2026-08-11, replacing the
        # cross-scenario min..max band: 94% of those bands straddled
        # zero and restated the grid). One (scenario, mode): the margin
        # band nearest zero -- a zero-containing band (mixed outcomes or
        # an exact tie) is maximally close, tie-broken by the smaller
        # band extreme. Per-scenario, so nothing aggregates.
        best = None
        for mode, s in (('bait', bait), ('no-bait', nobait)):
            if s is None:
                continue
            for i in range(len(s.frac)):
                lo, hi = int(s.margin_lo[i]), int(s.margin_hi[i])
                close = 0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
                key = (close, max(abs(lo), abs(hi)))
                if best is None or key < best[0]:
                    best = (key, mode, i, lo, hi)
        if best is not None:
            _k, mode, i, lo, hi = best
            mband = (f'<span class="mband">closest: {SCEN_LABELS[i]} '
                     f'({mode}) {lo:+d}..{hi:+d}</span>')
        else:
            mband = '<span class="mband">missing</span>'
        oname = names[oid]
        plink = links.get(frozenset((sid, oid)))
        rev = cells.get((oid, sid))
        pair_amber = cell.amber or (rev is not None and not rev.missing
                                    and rev.amber)
        # Collapse to ONE grid when the bait modes' win counts are
        # IDENTICAL per scenario (Michael 2026-08-11) -- exact-equality
        # collapse only, so nothing displayed can differ between the
        # modes except the margin band, which the tooltip unions.
        bait_indep = (bait is not None and nobait is not None
                      and bait.n == nobait.n
                      and (bait.wins == nobait.wins).all())
        if bait_indep:
            grids = (f'<span style="display:inline-block">'
                     f'{_grid9(bait, oname, "bait-independent", nobait)}'
                     '</span>')
        else:
            grids = (f'<span style="display:inline-block">'
                     f'{_grid9(bait, oname, "bait")}</span>'
                     f'<span style="display:inline-block">'
                     f'{_grid9(nobait, oname, "no-bait")}</span>')
        # The 3x3 grids click through to the pair detail page (Michael
        # 2026-08-14); link only against a file that exists (ship-gate
        # rule), same as _mini_cell.
        if plink:
            grids = f'<a class="gridlink" href="{esc(plink)}">{grids}</a>'
        _deep = (jmap or {}).get(frozenset((sid, oid)))
        # Row anchor: the hub's dimmed-cell popover deep-links here
        # (sheet_row_id is the single definition of the id).
        rows.append(
            f'<tr id="{sheet_row_id(oid)}">'
            f'<td><a href="{sheet_filename(oid)}">{esc(oname)}</a><br>'
            f'{_digin(cell, oname, plink, pair_amber, _deep)}</td>'
            f'<td>{grids}</td>'
            f'<td>{flag_html}</td><td>{mband}</td></tr>')
    forced = entry.get('forced_reason')
    forced_html = (f'<p class="section-intro"><strong>Why it is in the '
                   f'meta:</strong> {esc(forced)}</p>' if forced else '')
    # Selection provenance moved OFF the rows and heading into this
    # end-of-page paragraph (Michael 2026-08-11: badge chips carried
    # too much visual weight for what is selection metadata, not
    # matchup info). The hub's meta table keeps the full per-entry
    # badge display and legend.
    own_badge = entry['badge']
    rule = entry.get('badge_rule', own_badge)
    _div = rule_divergence(own_badge, rule)
    rule_note = (f' (the mechanical rule says {esc(_div)}; the divergence '
                 'is deliberate and explained on the hub)'
                 if _div else '')
    provenance_tail = (
        '<p class="section-intro">Selection provenance: this entry is '
        f'badged <strong>{esc(own_badge)}</strong>{rule_note}. Badges '
        'describe how each species earned its meta slot (PLAYED = '
        'tournament usage + current rank; PLAYED* = usage but rank '
        'collapsed post-rebalance; MODEL = rank only, no tournament '
        'footprint; FORCED = editorial include) -- definitions and '
        'per-entry data in the <a href="worlds.html">hub meta '
        'table</a>.</p>')
    fast, charged = display_moveset(entry)
    moves = f'{esc(fast)} / ' + ' + '.join(esc(m) for m in charged)
    dive = slug_map.get(sid)
    dive_html = (f' <a class="chip" href="{esc(dive)}">full IV dive</a>'
                 if dive else '')
    body = f"""
<p class="section-intro">Moveset: <strong>{moves}</strong>
({esc(entry['moveset_source'])}{'; differs from PvPoke default'
    if entry['default_disagrees'] else ''}){injection_chip(entry)}.
Focal spread: its rank-1 stat-product spread (hover cells for cohort
sizes and margins).{dive_html}</p>
{fork_html(entry, entries, website_dir)}
{injection_html(entry)}
{forced_html}
{LEGEND}
<div class="table-scroll"><table class="sheet">
<tr><th>Opponent</th><th>shield matchups (rows = own shields,
columns = opponent's; bait / no-bait)</th>
<th>IV-decided</th><th>closest scenario (score margin)</th></tr>
{''.join(rows)}
</table></div>
<p>"IVs decide" unions every slice (both probe spreads, both cohorts,
both bait modes) - the strips show only the headline slice, so a flag
can name a scenario whose strip looks settled.</p>
{NOT_BUILT}
{provenance_tail}
<p><a href="worlds.html">Back to the Worlds 2026 hub</a></p>
"""
    return _page_shell(
        title=f'{entry["name"]} - Worlds 2026 cheat sheet',
        heading=f'{entry["name"]} at Worlds 2026',
        intro_html=provenance_html(meta, manifest),
        body_html=body,
        extra_css=WORLDS_CSS)


def build(website_dir=WEBSITE_DIR, planes_dir=wp.PLANES_DIR,
          meta_path=wp.META_TOML):
    meta = wrd.load_meta(meta_path)
    entries = meta['entries']
    manifest = wp.load_manifest(planes_dir)
    if manifest is None:
        sys.exit('ABORT: no planes manifest -- run worlds_bake.py first')
    mismatches = wp.stamp_mismatches(manifest)
    if mismatches:
        sys.exit('ABORT: manifest stamps do not match the current '
                 f'engine/gamemaster/producer: {mismatches} -- a page '
                 'rendered from mixed vintages must not ship')
    cells = wrd.build_all_cells(entries, planes_dir)
    n_missing, missing = wrd.coverage_check(cells, entries)
    if n_missing:
        sys.exit(f'ABORT: {n_missing} Tier-1 cells missing from the planes '
                 f'(e.g. {missing[:4]}) -- refusing to render a silently '
                 'partial page')
    website_dir = Path(website_dir)
    website_dir.mkdir(parents=True, exist_ok=True)
    slug_map = dive_slug_map(entries, website_dir)
    links = pair_link_map(website_dir)
    # Tier-2 extras are OPTIONAL (session-3 pages rendered without them);
    # when the tier2 manifest exists, the hub gains the FN-rate block and
    # the deferred list.
    fn = None
    deferred = []
    try:
        import worlds_fn
        import worlds_tier2
        t2m = worlds_tier2.load_manifest()
        if t2m is not None:
            fn = worlds_fn.fn_rate()
            deferred = [tuple(p) for p in t2m.get('deferred', [])]
    except ImportError:
        pass
    jmap = joint_iv_link_map(website_dir)
    (website_dir / 'worlds.html').write_text(
        render_hub(meta, cells, manifest, slug_map, links, fn, deferred,
                   jmap))
    for e in entries:
        (website_dir / sheet_filename(e['species_id'])).write_text(
            render_cheat_sheet(e, meta, cells, manifest, slug_map, links,
                               website_dir, jmap))
    print(f'Wrote worlds.html + {len(entries)} cheat sheets to '
          f'{website_dir} ({len(cells)} cells, '
          f'{sum(1 for c in cells.values() if c.amber)} IV-decided '
          'directions).')
    return 0


if __name__ == '__main__':
    sys.exit(build())
