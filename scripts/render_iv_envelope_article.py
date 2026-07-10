#!/usr/bin/env python
"""Render an IV-envelope JSON (from iv_envelope_analysis.py) into a
XehrFelrose-style ML IV guide article, matching the pogo-dives website
dark article house style with a sticky sidebar nav. Re-run freely to tweak
presentation without re-simulating.

Usage: python scripts/render_iv_envelope_article.py userdata/dives/<slug>_iv_envelope.json

Writes userdata/website/articles/<slug>-ml-iv-guide/{index.html,meta.toml}.
No gameplay/teambuilding judgment is rendered -- only the simulated mechanics
and matchups. The reader decides what matters.
"""
import sys, os, json, html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
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
import pvpoke_links

QUAD_LABEL = {
    'nobb_vs_nonbb': 'No best buddy, vs a non-best-buddy meta',
    'nobb_vs_bb':    'No best buddy, vs a best-buddy meta',
    'wbb_vs_nonbb':  'Best buddy, vs a non-best-buddy meta',
    'wbb_vs_bb':     'Best buddy, vs a best-buddy meta',
}
# Attribution. The format, structure, and much of the terminology of this
# article are adapted from XehrFelrose's Master League IV deep dives. Credit
# is rendered prominently (top credit box, Terms note, and footer). The numbers
# are independently re-simulated with this project's engine.
CREDIT_NAME = 'XehrFelrose'
CREDIT_URL = 'https://www.youtube.com/watch?v=6N3lXp39qtQ'

# Limited-availability species: research/quest/raid-day-only mons you can
# realistically own only one or a few of, with NO way to re-roll for IVs. In
# game their IV floor is the research-encounter floor (10/10/10), well below
# this guide's default 12/12/12 sweep floor -- so a legitimately-owned sub-12
# spread can fall off the bottom of the grid. The banner is floor-aware: a
# guide swept at the real 10/10/10 floor (--iv-floor 10) tells the reader they
# ARE covered; one still at 12/12/12 warns that sub-12 spreads fall off. As of
# 2026-06-28 every species currently in this set has been reswept at the 10/10/10
# floor (see run_iv_guides.FLOOR_10_SPECIES), so all shipped guides hit the
# "covered" branch; the 12/12/12 warning branch stays live as the fallback for
# any future limited species added before its own re-sweep lands. Match
# d['species'] verbatim.
# NOTE (2026-06-27): Eternatus is treated as limited regardless of trade
# status -- Michael's call that it is rare enough to count as special. It is
# resweept at the 10/10/10 floor (see run_iv_guides.FLOOR_10_SPECIES).
LIMITED_AVAILABILITY = frozenset({
    'Marshadow',
    'Meloetta (Aria)',
    'Jirachi',
    'Keldeo (Ordinary)',
    'Keldeo (Resolute)',
    'Eternatus',
    'Zygarde (Complete Forme)',
})

QUAD_ORDER = ['nobb_vs_nonbb', 'nobb_vs_bb', 'wbb_vs_nonbb', 'wbb_vs_bb']
QUAD_SHORT = {
    'nobb_vs_nonbb': 'non-BB vs non-BB',
    'nobb_vs_bb':    'non-BB vs BB',
    'wbb_vs_nonbb':  'BB vs non-BB',
    'wbb_vs_bb':     'BB vs BB',
}
STAT_LABEL = {'atk': 'Attack', 'def': 'Defense', 'hp': 'HP'}
# Short label for the per-stat IV column header + close-call IV tags, so a row
# self-identifies its stat ("13 Atk") even when the reader has scrolled past
# the section heading.
STAT_ABBR = {'atk': 'Atk', 'def': 'Def', 'hp': 'HP'}
CLOSE_CALL_KIND_LABEL = {
    'shield': 'shield spent',
    'neardeath': 'near-death win',
    'energy': 'energy banked',
}

# Sidebar nav: (anchor id, label, [(sub id, sub label), ...]).
NAV = [
    ('covers', 'What this covers', []),
    ('terms', 'Terms to know', []),
    ('build', 'The build', []),
    ('checkmyivs', 'Check my IVs', []),
    ('meta', 'Vs the meta', []),
    ('bestbuddy', 'What best buddy changes', []),
    ('attack', 'Attack IVs', [(f'atk-{q}', QUAD_SHORT[q]) for q in QUAD_ORDER]),
    ('defense', 'Defense IVs', [(f'def-{q}', QUAD_SHORT[q]) for q in QUAD_ORDER]),
    ('hp', 'HP IVs', [(f'hp-{q}', QUAD_SHORT[q]) for q in QUAD_ORDER]),
    ('recommended', 'Recommended IVs', [
        ('rec-bb', 'BB vs BB'),
        ('rec-nobb', 'non-BB vs BB'),
        ('rec-bb-nonbb', 'BB vs non-BB'),
        ('rec-nobb-nonbb', 'non-BB vs non-BB'),
    ]),
    ('method', 'Method & caveats', []),
]


def esc(s):
    return html.escape(str(s))


def _a(name, link=None, fsh=1, osh=1):
    """A matchup name, linked to its pvpoke.com battle when a linker is given.
    Best-effort: any failure to build the URL falls back to plain text, so a
    bad link can never break a render."""
    if link is None:
        return esc(name)
    try:
        url = link(name, fsh, osh)
    except Exception:
        url = None
    return (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(name)}</a>'
            if url else esc(name))


def _linker(d, ivs, my_level, opp_level):
    """Return f(opp_display, fsh, osh) -> pvpoke battle URL for this focal at
    these IVs/levels vs that opponent at the given shields."""
    b = d['build']
    def fn(opp_display, fsh, osh):
        return pvpoke_links.battle_url(
            d['species'], d.get('shadow', False), ivs, my_level,
            b['fast'], b['charged'], opp_display, opp_level, fsh, osh)
    return fn


def joinm(lst, link=None, fsh=1, osh=1):
    return (", ".join(_a(x, link, fsh, osh) for x in lst) if lst
            else '<span class="none">-</span>')


EVEN_LABELS = {'0-0', '1-1', '2-2'}


def _sh_class(lab):
    return 'sh-even' if lab in EVEN_LABELS else 'sh-uneven'


def tagged_lines(by_sh, shields, link=None):
    """One <div> per shield label with drops, tagged sh-even/sh-uneven so the
    shield-view toggle can hide the uneven ones client-side."""
    out = []
    for lab in shields:
        opps = by_sh.get(lab, [])
        if opps:
            fsh, osh = lab.split('-')
            out.append(f'<div class="sh-line {_sh_class(lab)}"><b>{esc(lab)}</b> '
                       + ", ".join(_a(o, link, fsh, osh) for o in opps) + '</div>')
    return out


def join_drops(drop_strings, link=None,
               empty='<span class="none">drops nothing (Premium)</span>'):
    """Inline 'Name shield, ...' for lists of 'Name s-s' strings, linking each
    name to its battle at the parsed shield count."""
    if not drop_strings:
        return empty
    parts = []
    for s in drop_strings:
        name, lab = s.rsplit(' ', 1)
        fsh, osh = lab.split('-')
        parts.append(f'{_a(name, link, fsh, osh)} {esc(lab)}')
    return ", ".join(parts)


def drop_cell(by_sh, shields, empty_text='-', link=None):
    """Compact 'matchups dropped' cell: tagged lines + a JS-managed empty
    marker (shown when no lines are visible in the current shield view)."""
    lines = tagged_lines(by_sh, shields, link)
    if not lines:
        # No drops at all (in any view) -> static marker, no toggle needed.
        return f'<span class="none">{empty_text}</span>'
    return (f'<div class="dropcell"><span class="empty-marker none hidden">{empty_text}</span>'
            + "".join(lines) + '</div>')


def drops_to_by_sh(drop_strings):
    """Convert ['Opp Name 1-2', ...] -> {'1-2': ['Opp Name'], ...}."""
    by_sh = {}
    for s in drop_strings:
        opp, lab = s.rsplit(' ', 1)
        by_sh.setdefault(lab, []).append(opp)
    return by_sh


def _combo_key(ivs):
    return "/".join(str(v) for v in ivs)


def iv_box_blob(d):
    """Compact per-combo data the client-side 'check my IVs' box reads.

    The 64-combo recommended set is the single backbone: every baked 12-15 combo
    carries its stats, dropped matchups, and (new) per-combo close-calls per
    quadrant. Single-stat combos (one stat below 15) additionally get the
    breakpoint/bulkpoint/CMP detail from the per-stat sections -- that is
    Michael's 15/15/14 vs 15/14/15 showcase case; multi-stat combos honestly get
    win/loss/close only. Keyed by 'a/d/h'. Only baked IVs (12-15) appear; the box
    flags anything else as out of range and never guesses."""
    iv_range = d['iv_range']
    lo, hi = min(iv_range), max(iv_range)
    combos = {}
    for r in d['recommended']:
        key = _combo_key(r['ivs'])
        combos[key] = {
            'stats': {'bb': r['pvp_bb'], 'nobb': r['pvp_nobb']},
            'drops': r['drops'],
            'cc': r.get('close_calls', {q: [] for q in r['drops']}),
        }
    # Overlay single-stat mechanic detail (bp/bulk/CMP) onto the matching combo
    # keys, per quadrant. Shield-independent, so keyed only by quadrant.
    for stat, slot in (('atk', 0), ('def', 1), ('hp', 2)):
        for iv in [v for v in iv_range if v != 15]:
            spread = [15, 15, 15]
            spread[slot] = iv
            key = _combo_key(spread)
            if key not in combos:
                continue
            mech = {}
            for q in QUAD_ORDER:
                qe = d['quadrants'][q][stat][str(iv)]
                m = {}
                if stat == 'atk':
                    if qe.get('breakpoints_lost'):
                        m['bp'] = qe['breakpoints_lost']
                    if qe.get('cmp_lost'):
                        m['cmp'] = qe['cmp_lost']
                elif stat == 'def':
                    if qe.get('bulkpoints_lost'):
                        m['bulk'] = qe['bulkpoints_lost']
                if m:
                    mech[q] = m
            combos[key]['single'] = True
            if mech:
                combos[key]['mech'] = mech
    return {
        'shields': d['shields'],
        'quadrants': QUAD_ORDER,
        'quadrant_labels': {q: QUAD_SHORT[q] for q in QUAD_ORDER},
        'headline': d['headline_quadrant'],
        'iv_lo': lo, 'iv_hi': hi,
        'combos': combos,
    }


IV_CHECK_JS = r"""
(function(){
  var D = JSON.parse(document.getElementById('ivc-data').textContent);
  var inEl = document.getElementById('ivc-input');
  var qEl  = document.getElementById('ivc-quad');
  var bbEl = document.getElementById('ivc-bb');
  var bbWrap = document.getElementById('ivc-bb-wrap');
  var out  = document.getElementById('ivc-out');
  var note = document.getElementById('ivc-note');
  var KIND = { shield:'shield spent', neardeath:'near-death win',
               energy:'energy banked' };

  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

  function parseSpreads(text){
    return text.split(',').map(function(t){ return t.trim(); })
      .filter(function(t){ return t.length; })
      .map(function(t){
        var nums = t.split(/[\/\s-]+/).map(function(n){ return parseInt(n,10); });
        return { raw: t, ivs: nums };
      });
  }

  // -> {raw, status:'ok'|'range'|'parse', key?, label, data?}
  function classify(sp){
    if (sp.ivs.length !== 3 || sp.ivs.some(function(n){ return isNaN(n); }))
      return { raw: sp.raw, status: 'parse', label: esc(sp.raw) + ' (unrecognized)' };
    if (sp.ivs.some(function(v){ return v < D.iv_lo || v > D.iv_hi; }))
      return { raw: sp.raw, status: 'range',
               label: sp.ivs.join('/') + ' (out of range; this guide covers '
                      + D.iv_hi + ' down to ' + D.iv_lo + ')' };
    var key = sp.ivs.join('/');
    if (!(key in D.combos))
      return { raw: sp.raw, status: 'range', label: key + ' (not baked)' };
    return { raw: sp.raw, status: 'ok', key: key, label: key, data: D.combos[key] };
  }

  // Raw battle score for one column/(opp,shield) from the shared cmp grid, or
  // null when the grid is absent (pre-grid guides). Lets cell() separate a
  // dropped TIE from a dropped loss: with no reachable in-sim timeout a battle
  // always ends in a faint, so score == 500 happens ONLY on a double-KO -- a
  // genuine tie -- never a win (a live winner scores > 500) or loss (< 500).
  function cellScore(col, quad, opp, sh){
    if (typeof CMP_READY === 'undefined' || !CMP_READY) return null;
    var grid = (typeof SCORES_CMP !== 'undefined') ? SCORES_CMP[quad] : null;
    if (!grid || col.status !== 'ok') return null;
    var iv = CMP_IDX[col.key]; if (iv == null) return null;
    var oi = DATA.opponentsDisplay.indexOf(opp); if (oi < 0) return null;
    for (var si = 0; si < DATA.nScenarios; si++)
      if (cmpScenLabel(si) === sh) return cmpVal(grid, iv, si, oi);
    return null;
  }
  // status of one column for one (opp, shield): {kind:'win'|'tie'|'loss'|'cc'|'na', cc?}
  function cell(col, quad, opp, sh){
    if (col.status !== 'ok') return { kind: 'na' };
    var tag = opp + ' ' + sh;
    if ((col.data.drops[quad] || []).indexOf(tag) !== -1)
      // dropped a matchup the hundo wins; score 500 = double-KO tie, else a loss
      return { kind: cellScore(col, quad, opp, sh) === 500 ? 'tie' : 'loss' };
    var ccs = (col.data.cc || {})[quad] || [];
    for (var i = 0; i < ccs.length; i++)
      if (ccs[i].opp === opp && ccs[i].shield === sh)
        return { kind: 'cc', cc: ccs[i] };
    return { kind: 'win' };
  }

  // signature for the "columns differ?" test. Two close calls are equal only if
  // kind AND margin match, so a barely-survives vs comfortably-wins still differs.
  function sig(c){
    if (c.kind === 'cc') return 'cc:' + c.cc.kind + ':' + c.cc.margin;
    return c.kind;
  }

  // Seed candidate (opp,shield) cells only from columns that HAVE data (a loss
  // or a close call). A clean-win-everywhere opponent never enters, so it can
  // never produce a row.
  function candidates(ok, quad){
    var set = {};
    ok.forEach(function(c){
      (c.data.drops[quad] || []).forEach(function(tag){
        var i = tag.lastIndexOf(' ');
        set[tag] = [tag.slice(0, i), tag.slice(i + 1)];
      });
      ((c.data.cc || {})[quad] || []).forEach(function(x){
        set[x.opp + ' ' + x.shield] = [x.opp, x.shield];
      });
    });
    return Object.keys(set).map(function(k){ return set[k]; });
  }

  // The (opp,shield) cells whose status differs across the in-range columns.
  function diffRows(ok, quad){
    return candidates(ok, quad).filter(function(cs){
      var sigs = ok.map(function(c){ return sig(cell(c, quad, cs[0], cs[1])); });
      for (var i = 1; i < sigs.length; i++) if (sigs[i] !== sigs[0]) return true;
      return false;
    });
  }

  // --- "All" case: one merged table across every case ----------------------
  // Reuses the shared globals from cmp_panels.js (cmpVal/cmpHp/cmpScenLabel/
  // CMP_MARGIN_MIN) plus the per-quadrant score+energy grids. Gated on
  // CMP_READY, so by the time it runs the shared script is loaded.
  // Version-B cell: win/loss score on top, faded best-buddy flip where a toggle
  // crosses the win line, then the leftover-HP bar (+ energy on wins).
  function cmpBarHtml(score){
    var hp = cmpHp(score), pct = Math.round(Math.abs(hp) * 100);
    var win = score > 500, tie = score === 500, lo = win && Math.abs(hp) < 0.2;
    var cls = 'cmp-bar' + (win ? (lo ? ' lo' : '') : (tie ? '' : ' loss'));
    // A nonzero margin that rounds to 0 shows "<1" so a thin win never reads as
    // dead/zero; an exact tie shows a bare "0% HP". The " HP" disambiguates it
    // from the adjacent "+N energy" line.
    var sign = tie ? '' : (win ? '+' : '&minus;');
    var num = (!tie && pct === 0) ? '&lt;1' : pct;
    return '<span class="' + cls + '"><span style="width:' + Math.min(100, pct)
      + '%"></span></span><span class="cmp-hpv">' + sign + num + '% HP</span>';
  }
  function allCellHtml(oi, si, build, quad, score, altScore, altIsBuddy, altCap, en, em, showMark, cc){
    var win = score > 500, tie = score === 500;
    var txt = '<span class="' + (win ? 'cmp-win' : tie ? 'cmp-tie' : 'cmp-lose')
      + '">' + (win ? 'win ' : tie ? 'tie ' : 'loss ') + score + '</span>';
    if (cc)   // close-call badge (shield spent / near-death / energy banked)
      txt += ' <span class="cc-tag cc-' + cc.kind + '" title="' + esc(cc.margin) + '">'
        + esc(KIND[cc.kind] || cc.kind) + '</span>';
    if (showMark && altScore != null && (score > 500) !== (altScore > 500)){
      var aw = altScore > 500, at = altScore === 500;
      var albl = aw ? 'win ' : at ? 'tie ' : 'loss ';
      var ds = altIsBuddy ? 'on' : 'off';
      var dw = (altIsBuddy ? 'turn best-buddy ON' : 'turn best-buddy OFF')
        + ' (to L' + altCap + ')';
      txt += ' <span class="cmp-altmark" title="' + dw + ': ' + albl + altScore + '">'
        + '<span class="cmp-flip">&#10022;' + ds + '&rarr;</span>'
        + '<span class="' + (aw ? 'cmp-win' : at ? 'cmp-tie' : 'cmp-lose') + '">'
        + albl + altScore + '</span></span>';
    }
    var enHtml = '';
    if (en != null && em && win){
      var parts = [];
      if (em.fast && em.fast.gain > 0) parts.push((en / em.fast.gain).toFixed(1) + em.fast.abbr);
      (em.charged || []).forEach(function(cm){
        if (cm.cost > 0) parts.push((en / cm.cost).toFixed(1) + cm.abbr); });
      enHtml = '<br><span class="cmp-env">+' + Math.round(en) + ' energy</span>'
        + (parts.length ? '<br><span class="cmp-env">' + parts.join(' &middot; ') + '</span>' : '');
    }
    var inner = '<span class="cmp-celltext">' + txt + '</span>' + cmpBarHtml(score);
    return '<td>' + cmpCellLink(oi, si, build, inner, quad) + enHtml + '</td>';
  }
  function renderAllView(ok, showBB){
    if (typeof CMP_READY === 'undefined' || !CMP_READY){
      // Distinguish "grids still decoding" from "this guide has no grids at all"
      // (older/pre-grid JSON) -- the latter would otherwise spin forever now
      // that "All cases" is the default Case.
      if (!document.getElementById('cmp-data'))
        return '<p class="sub">The &#8220;All cases&#8221; view needs the cross-case '
          + 'score grids, which this guide does not include. Pick a specific Case above.</p>';
      return '<p class="sub">Computing all cases (decoding score grids)...</p>';
    }
    var live = ok.map(function(c){
      var iv = CMP_IDX[c.key]; if (iv == null) return null;
      var p = c.key.split('/');
      return { key:c.key, iv:iv, a:+p[0], d:+p[1], s:+p[2] };
    }).filter(function(x){ return x; });
    if (live.length < 2)
      return '<p class="sub">Enter two or more baked, in-range spreads to compare across all cases.</p>';
    var QLABEL = {};
    for (var qi = 0; qi < qEl.options.length; qi++)
      QLABEL[qEl.options[qi].value] = qEl.options[qi].text;
    var em = window.CMP_ENERGY_MOVES;
    var rows = [];
    var hiddenBB = 0;   // collapsed view: rows that expanding best-buddy would reveal
    function sgn(v){ return v > 500 ? 'W' : v < 500 ? 'L' : 'T'; }
    Object.keys(SCORES_CMP).forEach(function(quad){
      var grid = SCORES_CMP[quad]; if (!grid) return;
      var altGrid = SCORES_CMP[CMP_BB_PAIR[quad]] || null;
      var altCap = CMP_ALTCAP[quad], altIsBuddy = CMP_ALTCAP[quad] > CMP_MYCAP[quad];
      var eg = (window.CMP_ENERGY || {})[quad] || null;
      for (var oi = 0; oi < DATA.nOpponents; oi++){
        for (var si = 0; si < DATA.nScenarios; si++){
          var scores = live.map(function(r){ return cmpVal(grid, r.iv, si, oi); });
          var altScores = altGrid ? live.map(function(r){ return cmpVal(altGrid, r.iv, si, oi); }) : null;
          var alts = showBB ? altScores : null;   // only USE the alt for tiering/marking when expanded
          var hasW = false, hasL = false;
          scores.forEach(function(v){ if (v > 500) hasW = true; else if (v < 500) hasL = true; });
          // Per-spread signature: primary outcome, plus the best-buddy-toggled
          // outcome when expanded. The row is an IV decision (a flip) only when
          // these signatures DIFFER across spreads. If every spread behaves the
          // same -- e.g. all win at best-buddy and all drop to the same loss
          // without it -- the IV pick changes nothing, so it is NOT a flip, and
          // the best-buddy marker would be identical noise (suppressed below).
          var sigs = scores.map(function(v, k){ return sgn(v) + (alts ? sgn(alts[k]) : ''); });
          var sigDiffer = sigs.some(function(s){ return s !== sigs[0]; });
          // Per-spread close-call (shield spent / near-death / energy banked) for
          // this quad/opp/scenario, from the ivc-data blob -- the same source the
          // per-Case table uses. Orthogonal to leftover HP: a spread can spend a
          // shield with ~0 HP-% difference, which the bar misses. So a close-call
          // that DIFFERS across spreads is its own reason to show the row.
          var oppN = DATA.opponentsDisplay[oi], shL = cmpScenLabel(si);
          var ccs = live.map(function(r){
            var lst = ((D.combos[r.key] && D.combos[r.key].cc) || {})[quad] || [];
            for (var z = 0; z < lst.length; z++)
              if (lst[z].opp === oppN && lst[z].shield === shL) return lst[z];
            return null;
          });
          var ccSig = ccs.map(function(c){ return c ? (c.kind + ':' + c.margin) : ''; });
          var ccDiffer = ccSig.some(function(s){ return s !== ccSig[0]; });
          var hps = scores.map(cmpHp);
          var hpSpread = Math.max.apply(null, hps) - Math.min.apply(null, hps);
          var delta = Math.max.apply(null, scores) - Math.min.apply(null, scores);
          var tier, include;
          if (sigDiffer){ tier = 0; include = true; }                  // flip: the pick changes the result
          else if (hasW){ tier = 1; include = hpSpread >= CMP_MARGIN_MIN || ccDiffer; } // win-both: margin swing or close-call
          else if (hasL){ tier = 2; include = hpSpread >= CMP_MARGIN_MIN || ccDiffer; } // lose-both: margin swing or close-call
          else { include = false; }                                    // all-tie
          if (!include){
            // collapsed view: would expanding best-buddy reveal this row? Primary
            // sigs are identical here, so a difference can only come from the alt.
            if (!showBB && altScores){
              var fsig = scores.map(function(v, k){ return sgn(v) + sgn(altScores[k]); });
              if (fsig.some(function(s){ return s !== fsig[0]; })) hiddenBB++;
            }
            continue;
          }
          rows.push({ quad:quad, oi:oi, si:si, tier:tier, delta:delta,
                      scores:scores, alts:alts, ccs:ccs, altIsBuddy:altIsBuddy, altCap:altCap, eg:eg,
                      showMark:(showBB && sigDiffer) });
        }
      }
    });
    if (!rows.length)
      return '<p class="sub">No matchups differ enough across these spreads in any case.</p>';
    rows.sort(function(a, b){ return a.tier - b.tier || b.delta - a.delta; });
    var nFlip = rows.filter(function(r){ return r.tier === 0; }).length;
    var TIERNAME = ['Flips - your IV pick changes the result', 'Win in both', 'Lose in both'];
    var h = '<div class="cmp-panel"><h4 class="cmp-marg-h">All cases'
      + ' <span class="cmp-count">' + rows.length + ' matchup' + (rows.length === 1 ? '' : 's')
      + (nFlip ? ', ' + nFlip + ' flip' + (nFlip === 1 ? '' : 's') : '')
      + ' &middot; scroll for all</span>'
      + (hiddenBB ? ' <span class="cmp-bbhint" title="Check &quot;Expand best-buddy '
          + 'flips&quot; above to break these out">' + hiddenBB + ' best-buddy flip'
          + (hiddenBB === 1 ? '' : 's') + ' hidden until you Expand above</span>' : '')
      + '</h4>'
      + '<p class="cmp-psub">Every case, merged. Flips first (your pick changes the '
      + 'result), then matchups you win in both, then lose in both - each ordered by '
      + 'score gap, biggest first.</p>'
      + '<div class="cmp-scroll-wrap"><div class="cmp-scroll"><table class="cmp-tbl"><thead><tr><th>Case</th><th>Matchup</th>'
      + live.map(function(r){ return '<th>' + r.a + '/' + r.d + '/' + r.s + '</th>'; }).join('')
      + '</tr></thead><tbody>';
    var lastTier = -1;
    rows.forEach(function(row){
      if (row.tier !== lastTier){
        h += '<tr class="tier-row"><td colspan="' + (2 + live.length) + '">'
          + TIERNAME[row.tier] + '</td></tr>';
        lastTier = row.tier;
      }
      h += '<tr><td class="cmp-case">' + esc(QLABEL[row.quad] || row.quad) + '</td>'
        + '<td class="cmp-m">' + esc(DATA.opponentsDisplay[row.oi]) + ' &middot; ' + cmpScenLabel(row.si) + '</td>';
      for (var k = 0; k < row.scores.length; k++){
        var en = row.eg ? cmpVal(row.eg, live[k].iv, row.si, row.oi) : null;
        h += allCellHtml(row.oi, row.si, live[k], row.quad,
                         row.scores[k], row.alts ? row.alts[k] : null,
                         row.altIsBuddy, row.altCap, en, em, row.showMark, row.ccs[k]);
      }
      h += '</tr>';
    });
    h += '</tbody></table></div></div>'
      + '<div class="cmp-leg"><b>What appears here:</b> a matchup is shown only '
      + 'when your spreads actually differ - they disagree on the win (a flip), '
      + (showBB ? 'or respond to best-buddy differently, ' : '')
      + 'or they all win / all lose but their leftover HP differs by '
      + Math.round(CMP_MARGIN_MIN * 100) + '%+, or one spends a shield / barely '
      + 'survives / banks less energy (a close call) where another does not. '
      + 'Rows where every spread behaves identically are hidden. Bars = leftover '
      + 'HP% at battle end (from the '
      + 'score); energy = leftover charge on a win.'
      + (showBB ? ' Faded &#10022;on/off marks the spread(s) whose result flips '
          + 'when you toggle your best-buddy.' : ' Best-buddy flip cases are merged '
          + 'in; check "Expand best-buddy flips" to break out the ones where the '
          + 'flip differs between your spreads.')
      + '</div></div>';
    return h;
  }

  // Scroll-aware bottom fade: hide it once the box is scrolled to the bottom (or
  // when the content doesn't overflow at all), show it whenever there is more
  // below. Re-wired after every render since out.innerHTML is rebuilt.
  function wireScrollFade(){
    var sc = out.querySelector('.cmp-scroll');
    if (!sc) return;
    var wrap = sc.closest('.cmp-scroll-wrap');
    if (!wrap) return;
    function upd(){
      var atBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight <= 2;
      wrap.classList.toggle('at-bottom', atBottom);
    }
    sc.addEventListener('scroll', upd);
    upd();
  }

  function render(){
    var cols = parseSpreads(inEl.value).map(classify);
    var quad = qEl.value;
    if (bbWrap) bbWrap.style.display = (quad === 'all') ? '' : 'none';
    out.innerHTML = '';
    note.innerHTML = '';
    if (!cols.length){ note.textContent = 'Enter at least one spread above.'; return; }

    var bad = cols.filter(function(c){ return c.status !== 'ok'; });
    if (bad.length)
      note.innerHTML = 'Skipped: ' + bad.map(function(c){
        return '<span class="ivc-bad">' + c.label + '</span>'; }).join(', ')
        + '. Only baked, in-range spreads are compared.';

    var ok = cols.filter(function(c){ return c.status === 'ok'; });
    if (!ok.length) return;

    if (quad === 'all'){ out.innerHTML += renderAllView(ok, !!(bbEl && bbEl.checked)); wireScrollFade(); return; }

    var rows = diffRows(ok, quad);
    rows.sort(function(a, b){
      return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : (a[1] < b[1] ? -1 : 1); });

    var h = ['<table class="ivc-table"><thead><tr><th>Opponent</th>'
             + '<th class="num">Shields</th>'];
    var lvkey = quad.indexOf('wbb') === 0 ? 'bb' : 'nobb';
    cols.forEach(function(c){
      var lab = c.status === 'ok' ? esc(c.label)
                : '<span class="ivc-bad">' + esc(c.raw) + '</span>';
      var st = '';
      if (c.status === 'ok'){
        var pv = c.data.stats[lvkey];
        st = '<br><span class="sub">' + pv[0] + ' / ' + pv[1] + ' / ' + pv[2] + '</span>';
      }
      h.push('<th class="ivc-cell">' + lab + st + '</th>');
    });
    h.push('</tr></thead><tbody>');

    if (!rows.length){
      var elsewhere = false;
      for (var qi = 0; qi < qEl.options.length; qi++){
        var oq = qEl.options[qi].value;
        if (oq !== quad && diffRows(ok, oq).length){ elsewhere = true; break; }
      }
      var msg = 'No matchups differ across these spreads in this case. They win '
        + 'and lose the same matchups, with the same close-call status.';
      if (elsewhere) msg += ' They DO differ in another Case; try the Case '
        + 'selector above.';
      h.push('<tr><td colspan="' + (2 + cols.length) + '" class="sub">'
        + msg + '</td></tr>');
    } else {
      rows.forEach(function(cs){
        var opp = cs[0], sh = cs[1];
        // Row-level battle-link keys: opponent index + scenario index, so each
        // per-build win/loss cell links to that exact pvpoke battle (no-op when
        // window.cmpBattleUrl / the score-grid embed is absent -> plain text).
        var oi = DATA.opponentsDisplay.indexOf(opp), si = -1;
        for (var _s = 0; _s < DATA.nScenarios; _s++)
          if (cmpScenLabel(_s) === sh) { si = _s; break; }
        h.push('<tr><td>' + esc(opp) + '</td><td class="num">' + esc(sh) + '</td>');
        cols.forEach(function(c){
          var st = cell(c, quad, opp, sh);
          function lk(inner){
            if (typeof cmpCellLink !== 'function' || oi < 0 || si < 0 || c.status !== 'ok')
              return inner;
            var p = c.key.split('/');
            return cmpCellLink(oi, si, { a:+p[0], d:+p[1], s:+p[2] }, inner, quad);
          }
          if (st.kind === 'na'){ h.push('<td class="ivc-cell none">-</td>'); return; }
          if (st.kind === 'loss'){ h.push('<td class="ivc-cell ivc-loss">' + lk('loss') + '</td>'); return; }
          if (st.kind === 'tie'){ h.push('<td class="ivc-cell ivc-tie">' + lk('tie') + '</td>'); return; }
          if (st.kind === 'cc'){
            h.push('<td class="ivc-cell ivc-win">' + lk('win') + ' <span class="cc-tag cc-'
              + esc(st.cc.kind) + '" title="' + esc(st.cc.margin) + '">'
              + esc(KIND[st.cc.kind] || st.cc.kind) + '</span></td>'); return;
          }
          h.push('<td class="ivc-cell ivc-win">' + lk('win') + '</td>');
        });
        h.push('</tr>');
      });
    }
    h.push('</tbody></table>');
    out.innerHTML = h.join('');

    var anyMulti = ok.some(function(c){ return !c.data.single; });
    if (ok.length === 1)
      out.innerHTML += '<p class="sub">Enter two or more spreads to compare '
        + 'where they differ.</p>';
    if (anyMulti)
      out.innerHTML += '<p class="sub">Breakpoint, bulkpoint, and CMP detail is '
        + 'only computed for spreads that drop a single stat (such as 15/15/14). '
        + 'Multi-stat spreads show win, loss, and close calls only.</p>';

    // Shared HP-margin + best-buddy-flip panels (scripts/cmp_panels.js). They
    // need the raw per-matchup score, so they appear only when the packed score
    // grids have decoded (CMP_READY) and 2+ in-range spreads are entered. The
    // decoder calls window._cmpBoxRerender on ready, so a fast typist sees the
    // panels fill in a moment later rather than never.
    if (ok.length >= 2 && typeof CMP_READY !== 'undefined' && CMP_READY
        && typeof cmpFlipPanel === 'function') {
      var liveRows = ok.map(function(c){
        var iv = CMP_IDX[c.key];
        if (iv == null) return null;
        var p = c.key.split('/');
        return { c: { a: +p[0], d: +p[1], s: +p[2] }, iv: iv };
      }).filter(function(x){ return x; });
      if (liveRows.length >= 2) {
        window.CMP_CUR_QUAD = quad;   // cmpCellLink links resolve to this Case
        var altQ = CMP_BB_PAIR[quad];
        var grids = { def: SCORES_CMP[quad], alt: SCORES_CMP[altQ] || null,
                      altCap: CMP_ALTCAP[quad],
                      // alt is the powered-UP (best-buddy) level only when the
                      // alt quadrant's my-level exceeds the selected Case's.
                      altIsBuddy: CMP_ALTCAP[quad] > CMP_MYCAP[quad] };
        // Banked-energy line under the HP bars: the margin panel shows it when
        // the energy grid for this Case AND the move energetics are present
        // (absent on pre-energy JSON -> HP bars only, graceful).
        var energyCtx = { eg: { def: (window.CMP_ENERGY || {})[quad] || null, alt: null },
                          em: window.CMP_ENERGY_MOVES };
        out.innerHTML += cmpFlipPanel(liveRows, grids)
                       + cmpMarginPanel(liveRows, grids, energyCtx);
      }
    }
  }

  window._cmpBoxRerender = render;
  document.getElementById('ivc-go').addEventListener('click', render);
  inEl.addEventListener('keydown', function(e){ if (e.key === 'Enter') render(); });
  qEl.addEventListener('change', render);
  if (bbEl) bbEl.addEventListener('change', render);
})();
"""


# Sets up the globals the shared cmp_panels.js + the box's panel block read:
# a minimal DATA (grid sizing), the combo->grid-index map, the same-meta
# opposite-your-BB pairing for the ✦ flip overlay, and an async decode of the
# packed score grids (DecompressionStream, identical pipeline to the deep dive).
CMP_SETUP_JS = r"""
(function(){
  var el = document.getElementById('cmp-data');
  if (!el) return;
  var CMPDATA = JSON.parse(el.textContent);
  window.DATA = { nOpponents: CMPDATA.opponentsDisplay.length,
                  nScenarios: CMPDATA.scenarios.length,
                  scenarios: CMPDATA.scenarios,
                  opponentsDisplay: CMPDATA.opponentsDisplay };
  window.CMP_IDX = {};
  CMPDATA.combos.forEach(function(c, i){ window.CMP_IDX[c.join('/')] = i; });
  // Same meta best-buddy status, opposite YOUR best-buddy status: the ✦ flip
  // overlay shows what powering yourself to L51 (or down to L50) changes.
  window.CMP_BB_PAIR = { nobb_vs_nonbb:'wbb_vs_nonbb', wbb_vs_nonbb:'nobb_vs_nonbb',
                         nobb_vs_bb:'wbb_vs_bb', wbb_vs_bb:'nobb_vs_bb' };
  window.CMP_ALTCAP = {};   // alt quadrant's MY level (the ✦ flip target)
  window.CMP_MYCAP = {};    // selected quadrant's MY level (the current view)
  for (var q in CMPDATA.quadrant_levels) {
    var alt = window.CMP_BB_PAIR[q];
    window.CMP_MYCAP[q] = Math.round(CMPDATA.quadrant_levels[q][0]);
    window.CMP_ALTCAP[q] = (alt && CMPDATA.quadrant_levels[alt])
      ? Math.round(CMPDATA.quadrant_levels[alt][0]) : 51;
  }
  // Battle-link builder for the compare cells. The hard parts (speciesId,
  // movesets) are resolved server-side in scripts/pvpoke_links.py and embedded
  // in CMPDATA.focalLink / CMPDATA.oppLinks; this only fills the per-build IVs,
  // per-quadrant levels, and shields into the URL. The skeleton MUST mirror
  // pvpoke_links.battle_url (that docstring is the source of truth for the
  // format). Returns null (-> plain text) whenever a piece is missing.
  window.cmpBattleUrl = function(oi, si, build, quad) {
    var fl = CMPDATA.focalLink, ol = (CMPDATA.oppLinks || [])[oi];
    var lv = (CMPDATA.quadrant_levels || {})[quad], sc = CMPDATA.scenarios[si];
    if (!fl || !ol || !lv || !sc || !build) return null;
    var p1 = fl.id + '-' + lv[0] + '-' + build.a + '-' + build.d + '-' + build.s + '-4-4-1-1';
    var p2 = ol.id + '-' + lv[1] + '-15-15-15-4-4-1-1';
    return 'https://pvpoke.com/battle/10000/' + p1 + '/' + p2 + '/'
      + sc[0] + '' + sc[1] + '/' + fl.moves + '/' + ol.moves + '/';
  };
  window.SCORES_CMP = {};
  window.CMP_ENERGY = {};                       // quadrant -> flat leftover-energy
  window.CMP_ENERGY_MOVES = CMPDATA.energy_moves || null;
  window.CMP_READY = false;
  async function decodeGrid(b64) {
    var bin = Uint8Array.from(atob(b64), function(c){ return c.charCodeAt(0); });
    var ds = new DecompressionStream('gzip');
    var w = ds.writable.getWriter(); w.write(bin); w.close();
    var chunks = [], reader = ds.readable.getReader();
    while (true) { var r = await reader.read(); if (r.done) break; chunks.push(r.value); }
    var total = chunks.reduce(function(s, c){ return s + c.byteLength; }, 0);
    var merged = new Uint8Array(total), off = 0;
    for (var i = 0; i < chunks.length; i++) { merged.set(chunks[i], off); off += chunks[i].byteLength; }
    return Array.from(new Uint16Array(merged.buffer));
  }
  (async function(){
    for (var qq in CMPDATA.grids) window.SCORES_CMP[qq] = await decodeGrid(CMPDATA.grids[qq]);
    var eg = CMPDATA.energy_grids || {};        // absent on pre-energy JSON
    for (var qe in eg) window.CMP_ENERGY[qe] = await decodeGrid(eg[qe]);
    window.CMP_READY = true;
    if (window._cmpBoxRerender) window._cmpBoxRerender();
  })();
})();
"""


def _cmp_panels_js():
    """The shared compare-panel functions (also injected into the deep dive)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cmp_panels.js')
    with open(p) as f:
        return f.read()


def _cmp_embed(d):
    """cmp-data blob + shared panels + setup/decoder, or '' when the JSON
    predates the score grids (older guides still render; panels just never
    appear)."""
    cmp = d.get('cmp_scores')
    if not cmp:
        return ''
    # Battle-link pieces (render-time, no re-sim): the focal's speciesId+moves
    # and each opponent's speciesId+moves, so the client-side compare panels can
    # link every per-build result cell to that exact pvpoke.com battle. Resolved
    # via the same helpers battle_url uses, so the two link paths can't drift.
    b = d['build']
    cmp = dict(cmp)  # don't mutate d's cached blob
    cmp['focalLink'] = pvpoke_links.focal_link_data(
        d['species'], d.get('shadow', False), b['fast'], b['charged'])
    cmp['oppLinks'] = [pvpoke_links.opponent_link_data(o)
                       for o in cmp['opponentsDisplay']]
    blob = json.dumps(cmp, separators=(',', ':'))
    return (f'<script type="application/json" id="cmp-data">{blob}</script>\n'
            f'<script>{_cmp_panels_js()}</script>\n'
            f'<script>{CMP_SETUP_JS}</script>\n')


def iv_check_box(d):
    # INTENTIONAL UI divergence from the deep-dive "Compare my candidates" widget
    # (deep_dive.py), which uses per-stat Atk/Def/HP + Lvl spinners + an Add
    # button. Here we use a single comma-separated paste-box: an ML guide is fixed
    # L50/L51 Master with no shadow toggle, so there is no per-candidate level or
    # shadow to enter -- a paste-box is the lighter affordance. Both feed the SAME
    # shared cmp_panels.js flip/margin panels; only the input differs.
    blob = json.dumps(iv_box_blob(d), separators=(',', ':'))
    quad_opts = '<option value="all" selected>All cases</option>' + "".join(
        f'<option value="{esc(q)}">{esc(QUAD_SHORT[q])}</option>' for q in QUAD_ORDER)
    lo = min(d['iv_range'])
    hi = max(d['iv_range'])
    return f"""<h2 id="checkmyivs">Check my IVs</h2>
<p class="sub">Paste one or more candidate spreads as <code>atk/def/hp</code>
(for example <code>15/15/14, 15/14/15</code>), and this builds a PvPoke-style
matchups table showing <b>only the matchups where those spreads differ</b>.
Spreads that agree everywhere are hidden, so the table stays scannable. This
guide covers IVs {hi} down to {lo}; the richest close-call detail is on spreads
that drop a single stat. Enter <b>two or more</b> spreads and you also get a
leftover-HP margin view (how much more convincingly each wins) and a ✦ marker
for matchups that flip when you toggle your own best-buddy (L50 &harr; L51) in
the selected Case.</p>
<div class="ivcheck panel">
  <div class="ivcheck-controls">
    <input id="ivc-input" type="text" placeholder="15/15/14, 15/14/15"
           autocomplete="off" spellcheck="false" aria-label="Candidate IV spreads">
    <label class="sub">Case <select id="ivc-quad">{quad_opts}</select></label>
    <label id="ivc-bb-wrap" class="sub" style="display:none">
      <input id="ivc-bb" type="checkbox"> Expand best-buddy (&#10022;) flips</label>
    <button id="ivc-go" type="button">Compare</button>
  </div>
  <div id="ivc-note" class="sub"></div>
  <div id="ivc-out"></div>
</div>
<script type="application/json" id="ivc-data">{blob}</script>
<script>{IV_CHECK_JS}</script>
{_cmp_embed(d)}"""


def style():
    return """
  /* Palette comes from the shared theme tokens (gopvpsim.theme.theme_css);
     this renderer references only var(--token). */
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:var(--bg); color:var(--text); line-height:1.6; margin:0; }
  a { color:var(--accent); text-decoration:none; }
  a:hover { text-decoration:underline; }
  .topbar { max-width:1180px; margin:0 auto; padding:32px 16px 0; }
  h1 { color:var(--title); margin:0 0 6px; }
  h2 { color:var(--heading); border-bottom:1px solid var(--border);
       padding-bottom:6px; margin-top:34px; scroll-margin-top:14px;
       font-size:1.15em; font-weight:700; letter-spacing:.02em; }
  h3 { color:var(--heading); margin-top:20px; font-size:1.05em; font-weight:700; }
  h4 { color:var(--text-muted); margin:12px 0 4px; font-size:.95em; }
  code { background:var(--surface); padding:2px 5px; border-radius:2px; font-size:.9em; }
  p { margin:10px 0; }
  .sub { color:var(--text-muted); font-size:.92em; }
  .none { color:var(--text-muted); }
  nav.toc .nav-toggle { margin-bottom:10px; padding-bottom:9px;
                  border-bottom:1px solid var(--border); }
  nav.toc .nav-toggle strong { display:block; color:var(--heading); font-size:12px;
                  letter-spacing:.02em; margin-bottom:5px; }
  nav.toc .nav-toggle label { display:inline-block; color:var(--text);
                  margin-right:12px; padding:2px 0; cursor:pointer; font-size:12px; }
  nav.toc .nav-toggle input { margin-right:6px; vertical-align:middle; }
  .sh-line { line-height:1.4; }
  body.shields-even .sh-uneven { display:none; }
  .hidden { display:none; }
  table { border-collapse:collapse; width:100%; margin:.6em 0 1.3em; font-size:.88em; }
  th, td { border:1px solid var(--border); padding:5px 9px; text-align:left; vertical-align:top; }
  thead th { background:var(--surface); color:var(--heading); }
  tbody td { background:var(--surface-2); color:var(--text); }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  caption { text-align:left; font-weight:600; color:var(--heading); padding:.3em 0; }
  /* Callouts: all-sides border carries the tier (orange=AI-drafted,
     gold=expert/source, red=limited-availability caution). */
  .banner, .credit, .limited-banner { background:var(--callout-bg);
            color:var(--callout-fg); border:1px solid var(--border);
            border-radius:0; padding:10px 14px; margin:16px 0; font-size:14px; }
  .banner strong, .credit strong, .limited-banner strong { color:var(--callout-strong); }
  .banner { border-color:var(--callout-ai); }       /* AI-drafted */
  .credit { border-color:var(--callout-expert); }   /* expert/source */
  .limited-banner { border-color:var(--loss); }     /* limited-availability */
  .credit a { color:var(--accent); }
  .twocol { display:flex; gap:2em; flex-wrap:wrap; }
  .twocol > div { flex:1; min-width:240px; }
  .terms dt { font-weight:600; margin-top:.5em; color:var(--heading); }
  .terms dd { margin:0 0 .2em 1.2em; color:var(--text); }
  .panel { background:var(--callout-bg); color:var(--callout-fg);
           border:1px solid var(--callout-auto); border-radius:0;
           padding:10px 14px; margin:12px 0; }
  footer { color:var(--text-muted); font-size:13px; margin-top:40px;
           border-top:1px solid var(--border); padding-top:12px; }
  /* layout + sidebar */
  .layout { display:flex; gap:28px; max-width:1180px; margin:8px auto 0;
            padding:0 16px 40px; align-items:flex-start; }
  nav.toc { position:sticky; top:14px; flex:0 0 260px; font-size:13px;
            background:var(--surface); border-radius:2px; padding:12px 14px;
            max-height:calc(100vh - 28px); overflow-y:auto; }
  nav.toc strong { color:var(--heading); display:block; margin-bottom:6px;
            font-size:12px; letter-spacing:.02em; }
  nav.toc a { display:block; color:var(--accent); padding:2px 0; }
  nav.toc .subnav { display:flex; flex-wrap:wrap; gap:1px 10px;
            padding:0 0 4px 12px; line-height:1.3; }
  nav.toc a.sub { padding:0; font-size:11.5px;
            color:var(--text-muted); white-space:nowrap; }
  nav.toc a.sub:hover { color:var(--accent); }
  main { flex:1; min-width:0; }
  main h2:first-child { margin-top:6px; }
  .close-calls ul { margin:4px 0 8px; padding-left:20px; }
  .close-calls > div { margin-top:6px; }
  .close-calls li { margin:2px 0; }
  .cc-tag { display:inline-block; font-size:.78em; padding:0 5px;
            border-radius:4px; vertical-align:middle; background:var(--surface); }
  .cc-shield { color:var(--accent); }
  .cc-energy { color:var(--energy); }
  .cc-neardeath { color:var(--loss); }
  /* check-my-ivs box */
  .ivcheck-controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center;
            margin-bottom:8px; }
  #ivc-input { flex:1; min-width:220px; background:var(--surface-2); color:var(--text);
            border:1px solid var(--border); border-radius:2px; padding:6px 9px;
            font-size:14px; }
  #ivc-quad { background:var(--surface-2); color:var(--text); border:1px solid var(--border);
            border-radius:2px; padding:5px 6px; }
  #ivc-go { background:var(--accent); color:var(--on-accent); border:none; border-radius:2px;
            padding:6px 14px; cursor:pointer; font-size:14px; }
  #ivc-go:hover { filter:brightness(1.1); }
  #ivc-note { margin:4px 0 8px; }
  .ivc-bad { color:var(--loss); }
  td.ivc-cell, th.ivc-cell { text-align:center; }
  td.ivc-win { color:var(--accent); }
  td.ivc-loss { color:var(--loss); font-weight:600; }
  td.ivc-tie { color:var(--tie); font-weight:600; }
  /* near-miss marker in the recommended table */
  .nm-flag { font-size:.7em; color:var(--tie); text-decoration:none;
            vertical-align:super; font-weight:700; }
  .nm-flag:hover { color:var(--title); }
  /* shared compare panels (scripts/cmp_panels.js): HP-margin bars + ✦ flip.
     Ported from the deep-dive's .cmp-* rules so the panels render identically
     in the guide. */
  .cmp-panel { background:var(--surface-2); border:1px solid var(--border-2); border-radius:2px;
            padding:11px 14px; margin:12px 0 14px; }
  .cmp-panel h4 { margin:0 0 3px; font-size:.92em; }
  .cmp-flip-h { color:var(--flip); } .cmp-marg-h { color:var(--accent-2); }
  .cmp-psub { font-size:.8em; color:var(--text-muted); margin:0 0 9px; }
  .cmp-tbl { border-collapse:collapse; width:100%; font-size:.86em; margin:0; }
  .cmp-tbl th, .cmp-tbl td { text-align:left; padding:5px 9px;
            border:none; border-bottom:1px solid var(--bar-track); white-space:nowrap; }
  .cmp-tbl th { color:var(--text-muted); font-weight:600; font-size:.8em; background:none; }
  .cmp-tbl td { background:none; }
  .cmp-m { color:var(--text); }
  /* Per-build result cells link to their pvpoke battle; inherit the win/loss
     color instead of the default link accent so the cell still reads as a
     result, with a subtle hover underline as the affordance. */
  a.cmp-cell-a { color:inherit; text-decoration:none; }
  a.cmp-cell-a:hover { text-decoration:underline; }
  .cmp-win { color:var(--win); font-weight:700; }
  .cmp-lose { color:var(--loss); font-weight:700; }
  .cmp-tie { color:var(--tie); font-weight:700; }
  .cmp-flip { color:var(--flip); }
  .cmp-altmark { opacity:0.5; font-weight:400; }
  .cmp-more { color:var(--text-muted); font-size:0.76rem; font-style:italic;
    cursor:pointer; text-decoration:underline dotted; }
  .cmp-more:hover { color:var(--text); }
  .cmp-tbl tr.cmp-xtra { display:none; }
  .cmp-tbl.cmp-all tr.cmp-xtra { display:table-row; }
  .cmp-bar { display:inline-block; vertical-align:middle; width:64px; height:9px;
            background:var(--bar-track); border-radius:2px; overflow:hidden; margin-right:6px; }
  .cmp-bar > span { display:block; height:100%; background:var(--win); }
  .cmp-bar.lo > span { background:var(--tie); }
  .cmp-bar.loss { display:flex; justify-content:flex-end; }
  .cmp-bar.loss > span { flex:none; background:var(--loss); }
  .cmp-hpv { font-size:.82em; color:var(--text-muted); }
  .cmp-env { font-size:.78em; color:var(--energy); }
  .cmp-leg { font-size:.78em; color:var(--text-muted); margin-top:5px; }
  /* "All cases" merged view: scrolling box, sticky header, tier dividers */
  .cmp-count { font-size:.72em; font-weight:600; color:var(--text-muted);
               text-transform:none; letter-spacing:0; }
  .cmp-bbhint { font-size:.72em; font-weight:600; color:var(--flip);
                text-transform:none; letter-spacing:0; cursor:help; }
  .cmp-scroll-wrap { position:relative; }
  /* tall, aggressive bottom fade so "there is more below" is unmistakable even
     on a short view -- reaches fully solid well before the bottom edge */
  .cmp-scroll-wrap::after { content:''; position:absolute; left:1px; right:1px; bottom:1px;
                height:104px; pointer-events:none; border-radius:0 0 2px 2px;
                opacity:1; transition:opacity .12s ease;
                background:linear-gradient(rgba(0,0,0,0), var(--surface-2) 58%); }
  .cmp-scroll-wrap.at-bottom::after { opacity:0; }
  .cmp-scroll { max-height:62vh; overflow-y:auto; border:1px solid var(--border-2);
                border-radius:2px; }
  .cmp-scroll thead th { position:sticky; top:0; z-index:2; background:var(--surface-2); }
  .cmp-case { color:var(--text-muted); }
  .cmp-celltext { display:block; margin-bottom:3px; }
  /* tier divider pins just below the column header. top is in EM of the td's
     own .74em font, so the header height (~28px ~= 2.75 of those em) maps to
     ~2.75em; the header's higher z-index covers any sub-px overlap cleanly. */
  .tier-row td { position:sticky; top:2.75em; z-index:1; background:var(--callout-bg);
                 color:var(--callout-strong); font-weight:700; font-size:.74em;
                 text-transform:uppercase; letter-spacing:.05em; padding:4px 9px; }
  @media (max-width:820px) {
    .layout { flex-direction:column; align-items:stretch; }
    /* Collapsed into the column: a full-width sticky bar (mirrors the deep-dive
       nav). Span the width (border-box so 100% + padding fits), flow the
       top-level links onto a wrapping row, hide the secondary sub-jump links to
       keep it short, and stick to the top on scroll. align-items:stretch on
       .layout fills the column-flex cross axis (the wide rule uses flex-start). */
    nav.toc { position:sticky; top:0; z-index:5; flex:none; width:100%;
              max-width:none; box-sizing:border-box; max-height:none;
              overflow:visible; display:flex; flex-wrap:wrap; gap:2px 14px;
              align-items:center; }
    nav.toc strong, nav.toc .nav-toggle { width:100%; }
    nav.toc a { display:inline-block; padding:1px 0; }
    nav.toc .subnav { display:none; }
  }
"""


def nav_html(compact=False):
    parts = []
    for i, l, subs in NAV:
        parts.append(f'<a href="#{i}">{esc(l)}</a>')
        if subs:
            # Flow the sub-links horizontally (wrapping) so the four
            # per-section jump links take ~one line instead of four.
            sub = "".join(f'<a class="sub" href="#{sid}">{esc(sl)}</a>'
                          for sid, sl in subs)
            parts.append(f'<div class="subnav">{sub}</div>')
    toggle = ("""<div class="nav-toggle"><strong>Shield view</strong>
<label><input type="radio" name="sv" value="all" checked> All 9 shields</label>
<label><input type="radio" name="sv" value="even"> Even only</label>
</div>""" if compact else "")
    return (f'<nav class="toc">{toggle}'
            f'<strong>On this page</strong>{"".join(parts)}</nav>')


def moveword(d):
    """Noun phrase for the build: signature-move override (BUILDS) vs the
    PvPoke default Master moveset. Used everywhere the prose names the build."""
    return ('its signature move' if d['build'].get('source') == 'signature'
            else 'its standard Master League moveset')


def build_card(d):
    b = d['build']
    bs = d['base_stats']
    return (f'<h2 id="build">The build</h2>\n<p class="sub">This guide assumes '
            f'<b>{esc(d["species"])}</b> with {moveword(d)}. Base stats '
            f'atk {bs["atk"]} / def {bs["def"]} / hp {bs["hp"]}.</p>\n'
            f'<ul><li>Fast: <code>{esc(b["fast"])}</code></li>'
            f'<li>Charged: {", ".join("<code>"+esc(c)+"</code>" for c in b["charged"])}</li></ul>\n')


def terms(d):
    shields = d['shields']
    if len(shields) > 3:
        shield_dd = ('Shield scenarios are written <b>you-opp</b> (your shields '
                     'first). This guide covers all ' + str(len(shields)) +
                     ' ordered scenarios (' + ", ".join(esc(s) for s in shields) +
                     '), so "you 2 / opp 1" (2-1) is distinct from "you 1 / opp 2" '
                     '(1-2). Even energy, standard movesets.')
    else:
        shield_dd = ('Even-shield scenarios, written you-opp: ' +
                     ", ".join(esc(s) for s in shields) +
                     '. Even energy, standard movesets.')
    return ("""<h2 id="terms">Terms to know</h2>
<dl class="terms">
<dt>Breakpoint</dt><dd>An attack-stat threshold where your fast move deals 1 more damage to a specific opponent. Most impactful on fast moves that fire every turn.</dd>
<dt>Bulkpoint</dt><dd>A defense-stat threshold where a specific opponent's fast move deals 1 less damage to you.</dd>
<dt>CMP (charge-move priority)</dt><dd>When both Pokemon throw a charged move on the same turn, the one with the higher attack stat goes first. "CMP lost" means a lower attack IV drops you below an opponent's attack, so you would lose that simultaneous-throw.</dd>
<dt>Shields (you-opp)</dt><dd>""" + shield_dd + """</dd>
<dt>BB (best buddy)</dt><dd>Best-buddy boost adds one level (L50 to L51). In Master League there is no CP cap, so that level fully applies.</dd>
<dt>Premium vs Thrifty IVs</dt><dd>Terminology from {credit_name} (<a href="{credit_url}">video</a>). Defined here mechanically, not as a gameplay call: a <b>Premium</b> spread drops no matchups versus a perfect (hundo) IV spread in the stated case; a <b>Thrifty</b> spread drops only the matchups listed next to it. Whether those matchups matter is your call.</dd>
</dl>
<p class="sub">These terms and the breakdown that follows are adapted from {credit_name}'s Master League IV deep dives.</p>
""").replace("{credit_name}", esc(CREDIT_NAME)).replace("{credit_url}", esc(CREDIT_URL))


def key_winloss(d):
    # Summarize wins/losses on the 3 EVEN shields (the high-level overview);
    # the full per-shield nuance lives in the per-stat tables below. Recomputed
    # from hundo_won so it is correct whether the JSON is even- or all-9-shield.
    out = ['<h2 id="meta">Versus the Master League meta</h2>']
    q = d['headline_quadrant']
    ml, ol = d['quadrant_levels'][q]
    evens = {'0-0', '1-1', '2-2'}
    all_opp = d['key_wins'] + d['key_losses'] + d['key_split']
    by_opp = {}
    for entry in d['hundo_won'][q]:
        opp, lab = entry.rsplit(' ', 1)
        by_opp.setdefault(opp, set()).add(lab)
    kw, kl, ks = [], [], []
    for o in all_opp:
        n = len(by_opp.get(o, set()) & evens)
        (kw if n == 3 else kl if n == 0 else ks).append(o)
    out.append(f'<p class="sub">Win/loss at a perfect IV on the 3 even shields '
               f'(0-0, 1-1, 2-2), in the <b>{esc(QUAD_LABEL[q].lower())}</b> case '
               f'(you L{int(ml)} vs opponents L{int(ol)}), vs the '
               f'{d["n_opponents"]}-strong Master top-60. The full per-shield '
               f'picture is in the stat tables below.</p>')
    # Perfect-IV summaries over the even shields; link to the headline quadrant
    # at a representative 1-1.
    link = _linker(d, (15, 15, 15), ml, ol)
    out.append('<div class="twocol">')
    out.append('<div><h3>Key wins</h3><ul>'
               + "".join(f"<li>{_a(x, link, 1, 1)}</li>" for x in kw) + '</ul></div>')
    out.append('<div><h3>Key losses</h3><ul>'
               + "".join(f"<li>{_a(x, link, 1, 1)}</li>" for x in kl) + '</ul></div>')
    out.append('</div>')
    if ks:
        out.append('<p class="sub"><b>Shield-dependent (split on even shields):</b> '
                   + joinm(ks, link, 1, 1) + '.</p>')
    return "\n".join(out) + "\n"


def bb_differences(d):
    hw = {q: set(v) for q, v in d['hundo_won'].items()}
    out = ['<h2 id="bestbuddy">What best buddy changes (at a perfect IV)</h2>',
           '<p class="sub">Matchups best buddy (L51) gains over not best-buddying (L50), holding the meta\'s best-buddy status fixed. Even shields, perfect IV.</p>',
           '<div class="panel">']
    for meta_label, wbb, nobb in [
            ('a non-best-buddy meta', 'wbb_vs_nonbb', 'nobb_vs_nonbb'),
            ('a best-buddy meta', 'wbb_vs_bb', 'nobb_vs_bb')]:
        gained = sorted(hw[wbb] - hw[nobb])
        lost = sorted(hw[nobb] - hw[wbb])
        # These are perfect-IV (15/15/15) matchups; link to the best-buddy
        # (L51) focal at this meta's level, with the entry's shields.
        my_lvl, opp_lvl = d['quadrant_levels'][wbb]
        link = _linker(d, (15, 15, 15), my_lvl, opp_lvl)
        out.append(f'<h4>Vs {meta_label}</h4>')
        out.append(f'<div><b>Gains:</b> '
                   f'{join_drops(gained, link, "<span class=\"none\">-</span>")}</div>')
        if lost:
            out.append(f'<div><b>Gives up:</b> {join_drops(lost, link)}</div>')
    out.append('</div>')
    return "\n".join(out) + "\n"


def close_calls_block(qd, iv_range, link_factory, stat):
    """Compact 'Close calls' callout for one quadrant of a stat section: kept
    wins whose post-match margin moved enough to matter, per dropped IV. Renders
    nothing when no IV in this quadrant has any close call (keeps the article
    scannable). link_factory(iv) -> a matchup linker at that dropped IV."""
    rows = []
    for iv in [v for v in iv_range if v != 15]:
        calls = qd[str(iv)].get('close_calls') or []
        if not calls:
            continue
        link = link_factory(iv)
        items = []
        for c in calls:
            fsh, osh = c['shield'].split('-')
            tag = esc(CLOSE_CALL_KIND_LABEL.get(c['kind'], c['kind']))
            items.append(f'<li>{_a(c["opp"], link, fsh, osh)} '
                         f'<span class="sub">{esc(c["shield"])}</span> '
                         f'<span class="cc-tag cc-{esc(c["kind"])}">{tag}</span>: '
                         f'{esc(c["margin"])}</li>')
        rows.append(f'<div><b>{iv} {STAT_ABBR[stat]}:</b><ul>'
                    + "".join(items) + '</ul></div>')
    if not rows:
        return ''
    return ('<div class="panel close-calls"><b>Close calls</b> '
            '<span class="sub">(still a win, but the post-match margin shifts '
            'enough to matter: a shield spent, a near-death survival, or roughly '
            'one fewer charged move of energy banked)</span>'
            + "".join(rows) + '</div>')


def stat_section(d, stat):
    sv = d['stat_values']
    out = [f'<h2 id="{stat if stat!="atk" else "attack"}">{STAT_LABEL[stat]} IVs</h2>'
           if stat == 'atk' else
           f'<h2 id="{"defense" if stat=="def" else "hp"}">{STAT_LABEL[stat]} IVs</h2>']
    out.append(f'<p class="sub">{STAT_LABEL[stat]} at a perfect IV: '
               f'<b>{sv["bb"][stat]["15"]}</b> at L51 (best buddy), '
               f'<b>{sv["nobb"][stat]["15"]}</b> at L50. '
               f'Each row drops only that one stat (the other two stay 15); '
               f'matchups shown are those given up versus a perfect IV.</p>')
    shields = d['shields']
    compact = len(shields) > 3
    drop_cols = (['Matchups dropped (you-opp)'] if compact
                 else [f'{s.split("-")[0]}s drops' for s in shields])
    slot = {'atk': 0, 'def': 1, 'hp': 2}[stat]
    for q in QUAD_ORDER:
        qd = d['quadrants'][q][stat]
        my_lvl, opp_lvl = d['quadrant_levels'][q]
        out.append(f'<h3 id="{stat}-{q}">{esc(QUAD_LABEL[q])}</h3>')
        if stat == 'atk':
            cols = [STAT_ABBR[stat], STAT_LABEL[stat], 'CMP lost', 'Breakpoint lost'] + drop_cols
        elif stat == 'def':
            cols = [STAT_ABBR[stat], STAT_LABEL[stat], 'Bulkpoint lost'] + drop_cols
        else:
            cols = [STAT_ABBR[stat], STAT_LABEL[stat]] + drop_cols
        out.append('<table><thead><tr>'
                   + "".join(f'<th class="num">{c}</th>' if i <= 1 else f'<th>{c}</th>'
                             for i, c in enumerate(cols)) + '</tr></thead><tbody>')
        for iv in [iv for iv in d['iv_range'] if iv != 15]:
            e = qd[str(iv)]
            drp = e['dropped']
            fivs = [15, 15, 15]
            fivs[slot] = iv
            link = _linker(d, fivs, my_lvl, opp_lvl)
            cells = [f'<td class="num">{iv}</td>',
                     f'<td class="num">{e["pvp_stat"]}</td>']
            # CMP/breakpoint/bulkpoint are shield-independent; link them at 1-1.
            if stat == 'atk':
                cells.append(f'<td>{joinm(e.get("cmp_lost", []), link, 1, 1)}</td>')
                cells.append(f'<td>{joinm(e.get("breakpoints_lost", []), link, 1, 1)}</td>')
            elif stat == 'def':
                cells.append(f'<td>{joinm(e.get("bulkpoints_lost", []), link, 1, 1)}</td>')
            if compact:
                cells.append(f'<td>{drop_cell(drp, shields, link=link)}</td>')
            else:
                for s in shields:
                    fsh, osh = s.split('-')
                    cells.append(f'<td>{joinm(drp.get(s, []), link, fsh, osh)}</td>')
            out.append('<tr>' + "".join(cells) + '</tr>')
        out.append('</tbody></table>')
        cc_block = close_calls_block(
            qd, d['iv_range'],
            lambda iv, slot=slot, ml=my_lvl, ol=opp_lvl: _linker(
                d, [15 if j != slot else iv for j in range(3)], ml, ol),
            stat)
        if cc_block:
            out.append(cc_block)
    return "\n".join(out) + "\n"


def rec_table(d, lvkey, meta_quad, title, note, anchor):
    rows = d['recommended']
    compact = len(d['shields']) > 3
    my_lvl, opp_lvl = d['quadrant_levels'][meta_quad]
    srt = sorted(rows, key=lambda r: (len(r['drops'][meta_quad]),
                                      -r[f'perfect_{lvkey}']))

    def _hidden_cost(r):
        # "Deceptive Premium": drops nothing but still spends a shield or banks a
        # charged move less. This is the ONLY case a per-row marker adds info the
        # Drops column doesn't already show -- a resource close-call on a row that
        # already drops matchups is redundant, and near-death wins fire on most
        # rows (noise). Often 0 (Garchomp has no deceptive-Premium rows); the full
        # near-miss detail lives in the Check my IVs box regardless.
        return (not r['drops'][meta_quad]) and any(
            c.get('kind') in ('shield', 'energy')
            for c in (r.get('close_calls') or {}).get(meta_quad, []))

    any_marker = any(_hidden_cost(r) for r in srt)
    legend = ('  A <span class="nm-flag">&#9650;</span> marks a spread that '
              'drops nothing but still spends a shield or banks a charged move '
              'less; see <a href="#checkmyivs">Check my IVs</a>.'
              if any_marker else '')
    out = [f'<h3 id="{anchor}">{esc(title)}</h3>',
           f'<p class="sub">{esc(note)}{legend}</p>']
    out.append('<table><thead><tr>'
               '<th class="num">CP</th><th class="num">IVs (A/D/HP)</th>'
               '<th class="num">IV %</th><th class="num">Atk</th>'
               '<th class="num">Def</th><th class="num">HP</th>'
               '<th>Drops vs a perfect IV</th></tr></thead><tbody>')
    for r in srt:
        a, dd, s = r['ivs']
        pa, pd, ph = r[f'pvp_{lvkey}']
        drops = r['drops'][meta_quad]
        near_miss = _hidden_cost(r)
        link = _linker(d, r['ivs'], my_lvl, opp_lvl)
        if compact:
            # grouped, shield-tagged lines so the toggle can hide uneven drops;
            # JS shows the Premium marker when no drops are visible in the view.
            dcell = drop_cell(drops_to_by_sh(drops), d['shields'],
                              'drops nothing (Premium)', link)
        else:
            dcell = join_drops(drops, link)
        iv_cell = f'{a}/{dd}/{s}'
        if near_miss:
            iv_cell += (' <a href="#checkmyivs" class="nm-flag" title="Drops '
                        'nothing but still spends a shield or banks a charged '
                        'move less; see Check my IVs">&#9650;</a>')
        out.append('<tr>'
                   f'<td class="num">{r[f"cp_{lvkey}"]}</td>'
                   f'<td class="num">{iv_cell}</td>'
                   f'<td class="num">{r[f"perfect_{lvkey}"]:.2f}%</td>'
                   f'<td class="num">{pa}</td><td class="num">{pd}</td>'
                   f'<td class="num">{ph}</td>'
                   f'<td>{dcell}</td></tr>')
    out.append('</tbody></table>')
    return "\n".join(out) + "\n"


def verdict(d):
    # vs-non-best-buddy-meta tables are present only when the analysis simmed
    # all four REC_QUADRANTS; older 2-quadrant JSON still renders (BB-meta only).
    has_nonbb = 'wbb_vs_nonbb' in d['recommended'][0]['drops']
    meta_note = (
        'The first two tables compare against a best-buddied meta (the '
        'realistic, harder case); the last two against a non-best-buddied meta, '
        'which is strictly easier.' if has_nonbb else
        'The realistic meta is best-buddied, so both tables compare against a '
        'best-buddy meta.')
    lo, hi = min(d['iv_range']), max(d['iv_range'])
    floor_note = (f'down to the {lo}/{lo}/{lo} research/raid-reward floor'
                  if lo <= 10 else
                  'the practical range above the 10/10/10 legendary catch floor')
    out = ['<h2 id="recommended">Recommended IVs</h2>',
           f'<p class="sub">Every spread with all three IVs from {lo} to {hi} '
           f'({floor_note}), sorted '
           'so the spreads that drop nothing come first. "Premium" drops no '
           'matchups versus a perfect IV in the stated case; everything else '
           f'lists exactly what it gives up. {meta_note}</p>']
    out.append(rec_table(
        d, 'bb', 'wbb_vs_bb',
        'If you best buddy (L51), vs a best-buddy meta',
        'CP and stats at L51; drops measured in the best-buddy vs best-buddy case.',
        'rec-bb'))
    out.append(rec_table(
        d, 'nobb', 'nobb_vs_bb',
        'If you do not best buddy (L50), vs a best-buddy meta',
        'CP and stats at L50; drops measured in the no-best-buddy vs best-buddy case.',
        'rec-nobb'))
    if has_nonbb:
        out.append(rec_table(
            d, 'bb', 'wbb_vs_nonbb',
            'If you best buddy (L51), vs a non-best-buddy meta',
            'CP and stats at L51; drops measured in the best-buddy vs '
            'no-best-buddy-meta case.',
            'rec-bb-nonbb'))
        out.append(rec_table(
            d, 'nobb', 'nobb_vs_nonbb',
            'If you do not best buddy (L50), vs a non-best-buddy meta',
            'CP and stats at L50; drops measured in the no-best-buddy vs '
            'no-best-buddy-meta case.',
            'rec-nobb-nonbb'))
    return "\n".join(out) + "\n"


def render(d):
    sp = esc(d['species'])
    credit_name = esc(CREDIT_NAME)
    credit_url = esc(CREDIT_URL)
    shieldconv = esc(d['shield_convention'])
    lo, hi = min(d['iv_range']), max(d['iv_range'])
    if d['species'] not in LIMITED_AVAILABILITY:
        limited_html = ""
    elif lo <= 10:
        # Swept at the real research floor: the owned-spread caveat no longer
        # applies, so the banner reassures instead of warning.
        limited_html = (f"""<div class="limited-banner"><strong>Limited-availability
species.</strong> {sp} comes from research, quests, or other capped encounters,
so most trainers own only one or a few and cannot re-roll for IVs. Those
encounters floor at {lo}/{lo}/{lo} -- and this guide is swept all the way down
to that floor, so a legitimately-owned spread is covered here.</div>""")
    else:
        limited_html = (f"""<div class="limited-banner"><strong>Limited-availability
species: your IVs may be below this grid.</strong> {sp} comes from research,
quests, or other capped encounters, so most trainers own only one or a few and
cannot re-roll for IVs. Those encounters floor at 10/10/10, below this guide's
{lo}/{lo}/{lo} sweep floor -- so a legitimately-owned spread under {lo} in any
stat will not appear here. A floor-corrected re-sweep for this species is
planned.</div>""")
    compact = len(d['shields']) > 3
    toggle_script = ("""
<script>
function updShields(){
  var even = document.querySelector('input[name="sv"]:checked').value === 'even';
  document.body.classList.toggle('shields-even', even);
  document.querySelectorAll('.dropcell').forEach(function(c){
    var anyVisible = Array.prototype.some.call(
      c.querySelectorAll('.sh-line'), function(l){ return l.offsetParent !== null; });
    var m = c.querySelector('.empty-marker');
    if (m) m.classList.toggle('hidden', anyVisible);
  });
}
Array.prototype.forEach.call(document.querySelectorAll('input[name="sv"]'),
  function(r){ r.addEventListener('change', updShields); });
updShields();
</script>""" if compact else "")
    main_parts = [f"""<h2 id="covers">What this covers</h2>
<ul>
<li>{sp} against the Master League meta (PvPoke top-{d['n_opponents']}).</li>
<li>Attack, Defense, and HP IVs from {hi} down to {lo}, compared to a perfect IV.</li>
<li>The full grid of best-buddy / no-best-buddy, for you and for the meta.</li>
<li>The minimum recommended IV spreads, and exactly what each gives up.</li>
</ul>
"""]
    main_parts.append(terms(d))
    main_parts.append(build_card(d))
    main_parts.append(iv_check_box(d))
    main_parts.append(key_winloss(d))
    main_parts.append(bb_differences(d))
    for stat in ('atk', 'def', 'hp'):
        main_parts.append(stat_section(d, stat))
    main_parts.append(verdict(d))
    main_parts.append(f"""<h2 id="method">Method and caveats</h2>
<ul>
<li>Simulator: this project's PvPoke-style 1v1 engine. A win is a higher 1v1 battle rating than the opponent.</li>
<li>Opponents: <code>{esc(d['pool'])}</code>, all modeled at a perfect IV. {esc(d['shield_convention'])}.</li>
<li>Master League has no CP cap, so L50 (regular) and L51 (best buddy) are pure level steps on both sides.</li>
<li>Breakpoints/bulkpoints are for the fast move ({esc(d['build']['fast'])}); CMP uses the attack stat.</li>
<li>Each matchup name links to that exact battle on <a href="https://pvpoke.com">pvpoke.com</a>: this {sp} at the row's IVs and level on the left, the opponent at a perfect 15/15/15 on the right, with the stated shields. Links not tied to a single shield count -- CMP, breakpoint/bulkpoint, and the perfect-IV summary lists (key wins/losses and best-buddy changes) -- use 1-1. Opponent movesets are PvPoke's Master defaults. PvPoke's engine closely matches this project's but can differ in edge cases, so an outcome may occasionally not line up exactly.</li>
<li>{sp} modeled with {moveword(d)}. Data: <code>scripts/iv_envelope_analysis.py</code>; rendered by <code>scripts/render_iv_envelope_article.py</code>.</li>
<li>Format, structure, and terminology adapted from <a href="{credit_url}">{credit_name}'s Master League IV deep dives</a>. The numbers are independently re-simulated, not lifted from the video.</li>
</ul>
""")
    main_html = "\n".join(main_parts)
    return f"""<!DOCTYPE html>
<html lang="en" {data_theme_attr()}>
<head>
<meta charset="utf-8">
{theme_head_script()}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{sp} Master League IV Guide</title>
<style>{theme_css()}{style()}</style>
</head>
<body>
{theme_picker_html()}
<div class="topbar">
<h1>{sp}: Master League IV Guide</h1>
<p class="sub">How far your IVs can slip before this Master League attacker
gives up specific matchups, using {moveword(d)}. Breakpoints, bulkpoints, CMP,
and named matchups across the full best-buddy grid, over {shieldconv}.</p>
<div class="credit"><strong>Format credit:</strong> the structure, terminology,
and presentation of this guide are adapted from
<a href="{credit_url}">{credit_name}'s Master League IV deep dives</a>. In
particular the "Terms to know" vocabulary (including the "Premium" vs "Thrifty"
IV framing), and the per-stat by best-buddy by shield breakdown, follow
{credit_name}'s work. The numbers here are independently re-simulated with this
project's own engine, not taken from the video.</div>
<div class="banner"><strong>AI-drafted, not yet human-reviewed.</strong> The
data tables are auto-generated from this project's simulator; the explanatory
prose is Claude-drafted, restating {credit_name}'s framing in our own words. No
gameplay or teambuilding judgment is made here, only the mechanics and matchups.
A human should review the prose (and confirm the attribution is fair) before
this ships.</div>
{limited_html}
</div>
<div class="layout">
{nav_html(compact)}
<main>
{main_html}
<footer>Format adapted from <a href="{credit_url}">{credit_name}'s Master League
IV deep dives</a>; numbers independently simulated. Generated by
<code>scripts/iv_envelope_analysis.py</code> +
<code>scripts/render_iv_envelope_article.py</code>.
<br>{PVPOKE_ATTRIBUTION_SHORT}</footer>
{support_footer_html("../../")}</main>
</div>{toggle_script}
</body>
</html>
"""


def main():
    json_path = sys.argv[1]
    d = json.load(open(json_path))
    slug = (d['species'].lower().replace(' ', '-')
            .replace('(', '').replace(')', ''))
    # The all-9 guide is the canonical one (it has a built-in even-only toggle),
    # so it lives at the plain -ml-iv-guide path. A standalone even-only render
    # (if ever produced) gets a -even suffix so it won't clobber the canonical.
    variant_suffix = '-even' if d.get('variant') == 'even' else ''
    outdir = f"userdata/website/articles/{slug}-ml-iv-guide{variant_suffix}"
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'index.html'), 'w') as f:
        f.write(render(d))
    # authorship = "ai": data tables are auto-generated, but the explanatory
    # prose is Claude-drafted (the orange "ai" tier), so the whole article is
    # AI-drafted-pending-review until a human edits the prose. Kept out of
    # ship-tracked articles/*.toml so the pre-commit policy isn't bypassed.
    meta = (f'title       = "{d["species"]} Master League IV Guide"\n'
            f'description = "AI-drafted (auto data tables + Claude-drafted prose), not yet '
            f'human-reviewed. XehrFelrose-style IV deep dive for {d["species"]} in Master '
            f'League (with {moveword(d)}): breakpoints, bulkpoints, CMP, and named '
            f'matchups given up at each IV from {max(d["iv_range"])} to {min(d["iv_range"])}, across the full best-buddy grid '
            f'over {d["shield_convention"]}, plus recommended IV spreads. '
            f'Format/terminology adapted from {CREDIT_NAME} '
            f'({CREDIT_URL}); numbers independently simulated. Human review of the prose '
            f'needed before ship."\n'
            f'authorship  = "ai"\n'
            f'landing     = "index.html"\n')
    with open(os.path.join(outdir, 'meta.toml'), 'w') as f:
        f.write(meta)
    print(f"Wrote {outdir}/index.html and meta.toml")


if __name__ == '__main__':
    main()
