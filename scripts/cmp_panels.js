// ============================================================
// Shared "compare candidates" close-call panels.
//
// Lifted out of deep_dive_engine.js so the ML / IV-guide pages
// (scripts/render_iv_envelope_article.py) can render the SAME flip /
// margin panels over a fixed set of named builds, instead of the
// deep-dive's typed-in candidate box. Both consumers load this file as a
// plain <script> before their own page logic, so these become globals.
//
// Dependencies are explicit: each function reads grid sizing from a
// global `DATA` object that the host page must define with at least
// {nOpponents, nScenarios, scenarios, opponentsDisplay}. cmpMarginPanel's
// energy annotation is passed in (energyCtx), NOT read from the engine's
// state -- so the guide supplies its own packed grids without the
// deep-dive's cmpEnergyGrids()/state plumbing.
//
//   live  = [{ c: {a, d, s}, iv: <grid index> }, ...]   (iv indexes the grid)
//   grids = { def: <flat scores>, alt: <flat scores|null>, altCap: <level> }
//   energyCtx = { eg: { def, alt }, em: energyMoves } | undefined
// ============================================================
var CMP_ROWS = 8;           // rows shown per close-call table
var CMP_MARGIN_MIN = 0.15;  // leftover-HP spread (max-min) to count as a swing

function cmpVal(grid, iv, si, oi) {
  return grid[iv * DATA.nScenarios * DATA.nOpponents + si * DATA.nOpponents + oi];
}
// Wrap a per-build result cell's inner HTML in a link to that exact pvpoke
// battle, when the host page supplies window.cmpBattleUrl(oi, si, build, quad).
// build = {a,d,s}; quad defaults to window.CMP_CUR_QUAD (the panels only render
// one Case at a time). No-op when the host provides no builder -- the deep dive
// currently doesn't, so its cells stay plain text (unchanged). Best-effort: any
// failure falls back to the bare inner HTML, so a bad link never breaks a cell.
function cmpCellLink(oi, si, build, inner, quad) {
  if (typeof window.cmpBattleUrl !== 'function') return inner;
  var url;
  try { url = window.cmpBattleUrl(oi, si, build, quad || window.CMP_CUR_QUAD); }
  catch (e) { url = null; }
  return url ? '<a class="cmp-cell-a" href="' + url + '" target="_blank" rel="noopener">'
             + inner + '</a>' : inner;
}
// leftover-HP% proxy: exact for a clean KO win (score-500)/500; |.| for losses.
function cmpHp(score) { return Math.max(-1, Math.min(1, (score - 500) / 500)); }
function cmpScenLabel(si) { var s = DATA.scenarios[si]; return s[0] + '-' + s[1]; }

// Clickable "+N more" row. Rows past CMP_ROWS are rendered with class
// "cmp-xtra" (hidden via CSS); clicking this cell toggles "cmp-all" on the
// table to reveal/hide them. data-n/data-noun let the toggle rebuild the label.
function cmpMoreRow(colspan, n, noun) {
  return '<tr class="cmp-more-row"><td colspan="' + colspan +
    '" class="cmp-more" onclick="cmpToggleMore(this)" data-n="' + n +
    '" data-noun="' + noun + '">+' + n + ' ' + noun + '</td></tr>';
}
function cmpToggleMore(td) {
  var tbl = td.closest('table');
  if (!tbl) return;
  var open = tbl.classList.toggle('cmp-all');
  td.textContent = open ? ('show fewer ↑')
    : ('+' + td.getAttribute('data-n') + ' ' + td.getAttribute('data-noun'));
}
window.cmpToggleMore = cmpToggleMore;

// Close calls where candidates DISAGREE on win/loss, or best-buddy flips one.
function cmpFlipPanel(live, grids) {
  var nO = DATA.nOpponents, nS = DATA.nScenarios, found = [];
  // Honor the opponent filter when this file is loaded alongside the dive's
  // filter panel; guarded so ML-guide pages (no panel, no helper) are unaffected.
  var selSet = (typeof selectedOppSet === 'function') ? selectedOppSet() : null;
  for (var oi = 0; oi < nO; oi++) for (var si = 0; si < nS; si++) {
    if (selSet && !selSet[oi]) continue;  // opponent filtered out
    var vals = live.map(function(r) { return cmpVal(grids.def, r.iv, si, oi); });
    // Outcome categories: win (>500), tie (==500), loss (<500). The candidates
    // "disagree" when they span more than one category -- this catches
    // win-vs-loss, win-vs-tie AND tie-vs-loss (the last was orphaned when ties
    // were split off the loss side). An all-same row (incl. all-tie) is not a
    // flip and, unless all win/all lose with a margin, lives in neither panel.
    var hasWin = false, hasTie = false, hasLoss = false, minNear = 999;
    vals.forEach(function(v) {
      if (v > 500) hasWin = true; else if (v === 500) hasTie = true; else hasLoss = true;
      minNear = Math.min(minNear, Math.abs(v - 500));
    });
    var distinct = (hasWin ? 1 : 0) + (hasTie ? 1 : 0) + (hasLoss ? 1 : 0);
    var bbFlip = false;
    if (grids.alt) live.forEach(function(r) {
      var d = cmpVal(grids.def, r.iv, si, oi), a = cmpVal(grids.alt, r.iv, si, oi);
      if ((d > 500) !== (a > 500)) bbFlip = true;  // best-buddy crosses the win line
    });
    // Any real disagreement (distinct>1) or best-buddy flip is decision-relevant
    // regardless of margin -- do NOT gate on closeness, or a genuine win-vs-loss
    // split (e.g. 565 vs 430) or a bb flip with a far-from-500 base (560->440)
    // would be silently dropped from BOTH panels. minNear only orders the rows.
    if (distinct > 1 || bbFlip)
      found.push({ oi: oi, si: si, vals: vals, near: minNear });
  }
  found.sort(function(a, b) { return a.near - b.near; });
  if (!found.length) return '';
  var h = '<div class="cmp-panel"><h4 class="cmp-flip-h">Matchups your picks decide differently</h4>' +
    '<p class="cmp-psub">Where the spread choice - or toggling best-buddy ' +
    '(<span class="cmp-flip">✦</span>) - changes the win/tie/loss outcome. The fights your ' +
    'IV pick actually decides, closest calls first.</p>';
  h += '<table class="cmp-tbl"><tr><th>Matchup</th>' +
    live.map(function(r) { return '<th>' + r.c.a + '/' + r.c.d + '/' + r.c.s + '</th>'; }).join('') + '</tr>';
  found.forEach(function(f, _ri) {
    h += '<tr' + (_ri >= CMP_ROWS ? ' class="cmp-xtra"' : '') + '><td class="cmp-m">' + DATA.opponentsDisplay[f.oi] + ' &middot; ' + cmpScenLabel(f.si) + '</td>';
    live.forEach(function(r, k) {
      // 500 is a simultaneous KO -> a TIE, not a loss (PvPoke convention; the
      // win-count still uses >500, so a tie counts as neither).
      var d = f.vals[k];
      var cls = d > 500 ? 'cmp-win' : (d === 500 ? 'cmp-tie' : 'cmp-lose');
      var lbl = d > 500 ? 'win ' : (d === 500 ? 'tie ' : 'loss ');
      var mark = '';
      if (grids.alt) {
        var a = cmpVal(grids.alt, r.iv, f.si, f.oi);
        if ((d > 500) !== (a > 500)) {  // toggling best-buddy crosses the win line
          // Show the alt-level outcome with its score, colored like a normal cell
          // (green win / amber tie / red loss) -- not a flat amber word. The
          // parenthetical is direction-aware: grids.altIsBuddy true means the alt
          // grid is the powered-UP (best-buddy) level; false means powered down.
          var acls = a > 500 ? 'cmp-win' : (a === 500 ? 'cmp-tie' : 'cmp-lose');
          var albl = a > 500 ? 'win ' : (a === 500 ? 'tie ' : 'loss ');
          // Direction-aware: altIsBuddy true means the alt grid is the powered-UP
          // (best-buddy) level, so toggling TURNS BEST-BUDDY ON ('+'); false means
          // it turns best-buddy OFF ('-'). The whole mark is wrapped in cmp-altmark
          // so CSS can fade it -- it's the secondary outcome, less important than
          // the primary win/loss this spread actually gets.
          var dirState = grids.altIsBuddy ? 'on' : 'off';
          var dirWord = grids.altIsBuddy
            ? 'turn best-buddy ON (to L' + grids.altCap + ')'
            : 'turn best-buddy OFF (to L' + grids.altCap + ')';
          mark = ' <span class="cmp-altmark" title="' + dirWord + ': ' + albl + a + '">'
            + '<span class="cmp-flip">✦' + dirState + '→</span>'
            + '<span class="' + acls + '">' + albl + a + '</span></span>';
        }
      }
      h += '<td class="' + cls + '">' + cmpCellLink(f.oi, f.si, r.c, lbl + d) + mark + '</td>';
    });
    h += '</tr>';
  });
  if (found.length > CMP_ROWS) h += cmpMoreRow(live.length + 1, found.length - CMP_ROWS, 'more close calls');
  return h + '</table></div>';
}

// Same result for all, but leftover-HP margin differs a lot.
function cmpMarginPanel(live, grids, energyCtx) {
  var nO = DATA.nOpponents, nS = DATA.nScenarios, found = [];
  var selSet = (typeof selectedOppSet === 'function') ? selectedOppSet() : null;
  for (var oi = 0; oi < nO; oi++) for (var si = 0; si < nS; si++) {
    if (selSet && !selSet[oi]) continue;  // opponent filtered out
    var vals = live.map(function(r) { return cmpVal(grids.def, r.iv, si, oi); });
    var allWin = vals.every(function(v) { return v > 500; });
    var allLose = vals.every(function(v) { return v < 500; });  // ties (==500) excluded
    if (!(allWin || allLose)) continue;          // disagreements/ties live in the flip panel
    var hps = vals.map(cmpHp), mn = Math.min.apply(null, hps), mx = Math.max.apply(null, hps);
    if (mx - mn >= CMP_MARGIN_MIN) found.push({ oi: oi, si: si, hps: hps, spread: mx - mn, win: allWin });
  }
  found.sort(function(a, b) { return b.spread - a.spread; });
  if (!found.length) return '';
  var h = '<div class="cmp-panel"><h4 class="cmp-marg-h">Same result, but the margin moves a lot</h4>' +
    '<p class="cmp-psub">All ' + (live.length === 2 ? 'both' : 'these') + ' get the same result, so a ' +
    'win-count shows nothing - but leftover HP (what you exit the battle with) differs. The ' +
    'robustness / "win more convincingly" axis.</p>';
  // Post-match energy (passed in via energyCtx, not read from engine state).
  // energyMoves carries the fast move's energy gain + each charged move's cost
  // so we can break leftover energy into fast-move-equivalents and fractions of
  // each charged move.
  energyCtx = energyCtx || {};
  var eg = energyCtx.eg || { def: null, alt: null };
  var em = energyCtx.em;
  var showEnergy = !!(eg.def && em);
  h += '<table class="cmp-tbl"><tr><th>Matchup</th>' +
    live.map(function(r) { return '<th>' + r.c.a + '/' + r.c.d + '/' + r.c.s + '</th>'; }).join('') + '</tr>';
  found.forEach(function(f, _ri) {
    h += '<tr' + (_ri >= CMP_ROWS ? ' class="cmp-xtra"' : '') + '><td class="cmp-m">' + DATA.opponentsDisplay[f.oi] + ' &middot; ' + cmpScenLabel(f.si) +
         (f.win ? '' : ' <span class="cmp-lose">(all lose)</span>') + '</td>';
    f.hps.forEach(function(hp, k) {
      var pct = Math.round(Math.abs(hp) * 100), lo = Math.abs(hp) < 0.2;
      var enHtml = '';
      if (showEnergy && f.win) {       // banked energy only meaningful on a win
        var en = cmpVal(eg.def, live[k].iv, f.si, f.oi);
        var parts = [];               // count first + tight (no space) so it reads "4.0SC"
        if (em.fast && em.fast.gain > 0)
          parts.push((en / em.fast.gain).toFixed(1) + em.fast.abbr);
        (em.charged || []).forEach(function(cm) {
          if (cm.cost > 0) parts.push((en / cm.cost).toFixed(1) + cm.abbr);
        });
        // Two lines: spell out "+N energy" on top, tight per-move breakdown
        // below -- eats vertical space to save horizontal as columns grow.
        enHtml = '<br><span class="cmp-env" title="Leftover energy as ' +
          'fast-move-equivalents and fractions of each charged move you ' +
          'exit the battle with">+' + Math.round(en) + ' energy</span>' +
          (parts.length ? '<br><span class="cmp-env">' + parts.join(' · ') + '</span>' : '');
      }
      // Wins fill green from the left; losses fill red from the right
      // (mirror image across the 500 centerline). 'lo' amber only marks
      // close *wins* -- a loss is always red regardless of how close.
      // (Metric is clamped to +-100% by cmpHp, so the bar never overflows.)
      var barCls = 'cmp-bar' + (f.win ? (lo ? ' lo' : '') : ' loss');
      var hpNum = (pct === 0) ? '&lt;1' : pct;   // thin margin never reads as 0
      var barInner = '<span class="' + barCls + '"><span style="width:' +
           Math.min(100, pct) + '%"></span></span><span class="cmp-hpv">' +
           (f.win ? '+' : '−') + hpNum + '% HP</span>';
      h += '<td>' + cmpCellLink(f.oi, f.si, live[k].c, barInner) + enHtml + '</td>';
    });
    h += '</tr>';
  });
  if (found.length > CMP_ROWS) h += cmpMoreRow(live.length + 1, found.length - CMP_ROWS, 'more');
  h += '</table><div class="cmp-leg">Bars = focal’s leftover HP% at battle end ' +
       '(from the score). Losses show how close you came.' +
       (showEnergy ? ' Energy = leftover charge you exit the battle with, shown as ' +
        'fast-move-equivalents then fractions of each charged move (by move ' +
        'initials).' : '') +
       '</div></div>';
  return h;
}
