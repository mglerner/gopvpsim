// ============================================================
// Shared "compare builds" unified table.
//
// One tier-sorted table (Flips -> Win in both -> Lose in both) over a set of
// candidate builds, used by BOTH the deep dive (deep_dive_engine.js) and the
// ML / IV guide (render_iv_envelope_article.py). Replaces the older separate
// cmpFlipPanel / cmpMarginPanel: flips now carry the HP bar + energy the margin
// view had, so every decision-relevant matchup shows full detail in one place.
//
// This file hardcodes NO level / cp / league: those live only in each host's
// window.cmpBattleUrl. So the ML guide (fixed L50/L51 master, levels from
// quadrant_levels) and the GL/UL/ML deep dive (per-candidate DATA.ivLv levels,
// per-mode opponent spreads, cp from DATA.cpCap) both feed the same table.
//
// Globals expected on the host page: DATA {nOpponents, nScenarios, scenarios,
// opponentsDisplay}; optional selectedOppSet() (opponent filter); optional
// window.cmpBattleUrl (per-cell battle links).
//
//   live  = [{ a, d, s, iv, key }, ...]     (iv indexes the grids; key = "a/d/s")
//   cases = [{ key, label, def, alt, altCap, altIsBuddy, energy }, ...]
//           Case column shown iff cases.length > 1; alt / energy optional.
//   opts  = { em, showBB, ccLookup, title, subtitle, legend, emptyHtml }
//           ccLookup(caseKey, buildKey, oppDisplay, shieldLabel)
//                 -> { kind, margin, label } | null   (close-call badge; optional)
// ============================================================
var CMP_MARGIN_MIN = 0.15;  // leftover-HP spread (max-min) to count as a swing

function cmpVal(grid, iv, si, oi) {
  return grid[iv * DATA.nScenarios * DATA.nOpponents + si * DATA.nOpponents + oi];
}
// leftover-HP% proxy: exact for a clean KO win (score-500)/500; |.| for losses.
function cmpHp(score) { return Math.max(-1, Math.min(1, (score - 500) / 500)); }
function cmpScenLabel(si) { var s = DATA.scenarios[si]; return s[0] + '-' + s[1]; }
function cmpEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, function(c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
  });
}

// Wrap a per-build result cell's inner HTML in a link to that exact pvpoke
// battle, when the host page supplies window.cmpBattleUrl(oi, si, build, quad).
// build = {a,d,s,iv} (iv = grid index, for hosts whose focal level varies per
// candidate, e.g. the deep dive; the ML guide reads level from the case/quad
// instead and ignores it). quad here is the case key. No-op when the host
// provides no builder, so a consumer that hasn't wired one keeps plain-text
// cells. Best-effort: any failure falls back to the bare inner HTML.
function cmpCellLink(oi, si, build, inner, quad) {
  if (typeof window.cmpBattleUrl !== 'function') return inner;
  var url;
  try { url = window.cmpBattleUrl(oi, si, build, quad || window.CMP_CUR_QUAD); }
  catch (e) { url = null; }
  return url ? '<a class="cmp-cell-a" href="' + url + '" target="_blank" rel="noopener">'
             + inner + '</a>' : inner;
}

// leftover-HP bar for one score: wins fill green from the left, losses fill red
// from the right (mirror across the 500 centerline). Metric is clamped to
// +-100% by cmpHp so the bar never overflows.
function cmpBarHtml(score) {
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

// One per-build result cell: win/loss score, optional close-call badge, optional
// faded best-buddy flip mark, the HP bar, and (on wins) the leftover-energy
// breakdown; wrapped in its pvpoke battle link when the host provides one.
function cmpCellHtml(oi, si, build, caseKey, score, altScore, altIsBuddy, altCap, en, em, showMark, cc) {
  var win = score > 500, tie = score === 500;
  var txt = '<span class="' + (win ? 'cmp-win' : tie ? 'cmp-tie' : 'cmp-lose')
    + '">' + (win ? 'win ' : tie ? 'tie ' : 'loss ') + score + '</span>';
  if (cc)   // close-call badge (shield spent / near-death / energy banked)
    txt += ' <span class="cc-tag cc-' + cc.kind + '" title="' + cmpEsc(cc.margin) + '">'
      + cmpEsc(cc.label || cc.kind) + '</span>';
  if (showMark && altScore != null && (score > 500) !== (altScore > 500)) {
    // Toggling best-buddy crosses the win line: show the alt-level outcome with
    // its score, faded (cmp-altmark) as the secondary result. Direction-aware:
    // altIsBuddy true means the alt grid is the powered-UP (best-buddy) level.
    var aw = altScore > 500, at = altScore === 500;
    var albl = aw ? 'win ' : at ? 'tie ' : 'loss ';
    var ds = altIsBuddy ? 'on' : 'off';
    var dw = (altIsBuddy ? 'turn best-buddy ON' : 'turn best-buddy OFF') + ' (to L' + altCap + ')';
    txt += ' <span class="cmp-altmark" title="' + dw + ': ' + albl + altScore + '">'
      + '<span class="cmp-flip">&#10022;' + ds + '&rarr;</span>'
      + '<span class="' + (aw ? 'cmp-win' : at ? 'cmp-tie' : 'cmp-lose') + '">'
      + albl + altScore + '</span></span>';
  }
  var enHtml = '';
  if (en != null && em && win) {   // banked energy only meaningful on a win
    var parts = [];                // count first + tight (no space) so it reads "4.0SC"
    if (em.fast && em.fast.gain > 0) parts.push((en / em.fast.gain).toFixed(1) + em.fast.abbr);
    (em.charged || []).forEach(function(cm) {
      if (cm.cost > 0) parts.push((en / cm.cost).toFixed(1) + cm.abbr);
    });
    enHtml = '<br><span class="cmp-env">+' + Math.round(en) + ' energy</span>'
      + (parts.length ? '<br><span class="cmp-env">' + parts.join(' &middot; ') + '</span>' : '');
  }
  var inner = '<span class="cmp-celltext">' + txt + '</span>' + cmpBarHtml(score);
  return '<td>' + cmpCellLink(oi, si, build, inner, caseKey) + enHtml + '</td>';
}

// The unified compare table. Iterates every (case, opponent, scenario) cell,
// keeps only rows where the builds actually differ -- tier 0 a win/loss flip,
// tier 1/2 a same-outcome margin swing or a differing close call -- and renders
// them tier-sorted with per-build cells. Honors the opponent filter when the
// host provides selectedOppSet(). Returns opts.emptyHtml (default '') when
// nothing qualifies.
function cmpUnifiedTable(live, cases, opts) {
  opts = opts || {};
  var em = opts.em || null, showBB = !!opts.showBB, ccLookup = opts.ccLookup || null;
  var multiCase = cases.length > 1;
  var nO = DATA.nOpponents, nS = DATA.nScenarios;
  var selSet = (typeof selectedOppSet === 'function') ? selectedOppSet() : null;
  var rows = [], hiddenBB = 0;   // hiddenBB: rows that expanding best-buddy would reveal
  function sgn(v) { return v > 500 ? 'W' : v < 500 ? 'L' : 'T'; }
  cases.forEach(function(cs) {
    var grid = cs.def; if (!grid) return;
    var altGrid = cs.alt || null, altCap = cs.altCap, altIsBuddy = !!cs.altIsBuddy;
    var eg = cs.energy || null;
    for (var oi = 0; oi < nO; oi++) {
      if (selSet && !selSet[oi]) continue;  // opponent filtered out
      for (var si = 0; si < nS; si++) {
        var scores = live.map(function(r) { return cmpVal(grid, r.iv, si, oi); });
        var altScores = altGrid ? live.map(function(r) { return cmpVal(altGrid, r.iv, si, oi); }) : null;
        var alts = showBB ? altScores : null;   // only USE the alt for tiering/marking when expanded
        var hasW = false, hasL = false;
        scores.forEach(function(v) { if (v > 500) hasW = true; else if (v < 500) hasL = true; });
        // Per-spread signature: primary outcome, plus the best-buddy-toggled
        // outcome when expanded. The row is an IV decision (a flip) only when
        // these signatures DIFFER across spreads -- an all-same row (incl. all
        // best-buddy-flipping identically) is not a decision and is suppressed.
        var sigs = scores.map(function(v, k) { return sgn(v) + (alts ? sgn(alts[k]) : ''); });
        var sigDiffer = sigs.some(function(s) { return s !== sigs[0]; });
        // Per-spread close-call (shield spent / near-death / energy banked),
        // supplied by the host via ccLookup. Orthogonal to leftover HP: a spread
        // can spend a shield with ~0 HP-% difference, so a close call that
        // DIFFERS across spreads is its own reason to show the row.
        var oppN = DATA.opponentsDisplay[oi], shL = cmpScenLabel(si);
        var ccs = live.map(function(r) { return ccLookup ? ccLookup(cs.key, r.key, oppN, shL) : null; });
        var ccSig = ccs.map(function(c) { return c ? (c.kind + ':' + c.margin) : ''; });
        var ccDiffer = ccSig.some(function(s) { return s !== ccSig[0]; });
        var hps = scores.map(cmpHp);
        var hpSpread = Math.max.apply(null, hps) - Math.min.apply(null, hps);
        var delta = Math.max.apply(null, scores) - Math.min.apply(null, scores);
        var tier, include;
        if (sigDiffer) { tier = 0; include = true; }                        // flip: the pick changes the result
        else if (hasW) { tier = 1; include = hpSpread >= CMP_MARGIN_MIN || ccDiffer; }  // win-both: margin swing or close call
        else if (hasL) { tier = 2; include = hpSpread >= CMP_MARGIN_MIN || ccDiffer; }  // lose-both: margin swing or close call
        else { include = false; }                                           // all-tie
        if (!include) {
          // collapsed view: would expanding best-buddy reveal this row? Primary
          // sigs are identical here, so a difference can only come from the alt.
          if (!showBB && altScores) {
            var fsig = scores.map(function(v, k) { return sgn(v) + sgn(altScores[k]); });
            if (fsig.some(function(s) { return s !== fsig[0]; })) hiddenBB++;
          }
          continue;
        }
        rows.push({ caseKey: cs.key, caseLabel: cs.label, oi: oi, si: si, tier: tier,
          delta: delta, scores: scores, alts: alts, ccs: ccs, altIsBuddy: altIsBuddy,
          altCap: altCap, eg: eg, showMark: (showBB && sigDiffer) });
      }
    }
  });
  if (!rows.length) return opts.emptyHtml || '';
  rows.sort(function(a, b) { return a.tier - b.tier || b.delta - a.delta; });
  var nFlip = rows.filter(function(r) { return r.tier === 0; }).length;
  var TIERNAME = ['Flips - your IV pick changes the result', 'Win in both', 'Lose in both'];
  var baseCols = (multiCase ? 2 : 1);   // (Case?) + Matchup
  var h = '<div class="cmp-panel"><h4 class="cmp-marg-h">'
    + (opts.title || 'Matchups your picks decide differently')
    + ' <span class="cmp-count">' + rows.length + ' matchup' + (rows.length === 1 ? '' : 's')
    + (nFlip ? ', ' + nFlip + ' flip' + (nFlip === 1 ? '' : 's') : '')
    + ' &middot; scroll for all</span>'
    + (hiddenBB ? ' <span class="cmp-bbhint" title="Check &quot;Expand best-buddy flips&quot; above to break these out">'
        + hiddenBB + ' best-buddy flip' + (hiddenBB === 1 ? '' : 's')
        + ' hidden until you Expand above</span>' : '')
    + '</h4>'
    + (opts.subtitle ? '<p class="cmp-psub">' + opts.subtitle + '</p>' : '')
    + '<div class="cmp-scroll-wrap"><div class="cmp-scroll"><table class="cmp-tbl"><thead><tr>'
    + (multiCase ? '<th>Case</th>' : '') + '<th>Matchup</th>'
    + live.map(function(r) { return '<th>' + r.a + '/' + r.d + '/' + r.s + '</th>'; }).join('')
    + '</tr></thead><tbody>';
  var lastTier = -1;
  rows.forEach(function(row) {
    if (row.tier !== lastTier) {
      h += '<tr class="tier-row"><td colspan="' + (baseCols + live.length) + '">'
        + TIERNAME[row.tier] + '</td></tr>';
      lastTier = row.tier;
    }
    h += '<tr>' + (multiCase ? '<td class="cmp-case">' + cmpEsc(row.caseLabel || row.caseKey) + '</td>' : '')
      + '<td class="cmp-m">' + cmpEsc(DATA.opponentsDisplay[row.oi]) + ' &middot; ' + cmpScenLabel(row.si) + '</td>';
    for (var k = 0; k < row.scores.length; k++) {
      var en = row.eg ? cmpVal(row.eg, live[k].iv, row.si, row.oi) : null;
      h += cmpCellHtml(row.oi, row.si, live[k], row.caseKey, row.scores[k],
        row.alts ? row.alts[k] : null, row.altIsBuddy, row.altCap, en, em, row.showMark, row.ccs[k]);
    }
    h += '</tr>';
  });
  h += '</tbody></table></div></div>'
    + (opts.legend ? '<div class="cmp-leg">' + opts.legend + '</div>' : '')
    + '</div>';
  return h;
}
