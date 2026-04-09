
// ---- State ----
var state = {
  movesetIdx: 0,
  scenarioMode: __SCENARIO_MODE_DEFAULT__,
  oppIvMode: '__OPP_IV_MODE_DEFAULT__',
  colorMode: 'threshold',
  yAxisMode: 'avgScore',
};
var yValues, yRanks, refYValues, refYRanks;
// Updated by computeView() based on the active y-axis mode. Read by
// hover text, layout title, and the summary table column header so a
// single source of truth controls how the y-axis labels itself.
var currentYLabel = 'Avg Battle Score';
var currentYMax = null;  // for "X / N" formatting on wins-based modes
var currentYIsSparse = false;  // true for winsMirror; false otherwise
var lockedIdx = -1;
var tierColors = __TIER_COLORS_JS__;
var tierNames = __TIER_NAMES_JS__;
var nIvs = DATA.nIvs, nS = DATA.nScenarios, nO = DATA.nOpponents;

// ---- Helpers ----
function getScoreKey(mi, mode) { return mi + '_' + mode; }
function getScores(mi, mode) { return SCORES[getScoreKey(mi, mode)]; }

// Viridis interpolator: lets the slayer overlay color untiered points
// the same way the base "Other" trace would (matching Plotly's built-in
// 'Viridis' colorscale). Plotly doesn't let one trace mix string colors
// with a colorscale, so we'd otherwise have to split the slayer overlay
// into tiered/untiered sub-traces; computing per-point colors in JS
// keeps it as a single legend entry.
var VIRIDIS_STOPS = [
  [0.0, [68, 1, 84]], [0.1, [72, 35, 116]], [0.2, [64, 67, 135]],
  [0.3, [52, 94, 141]], [0.4, [41, 120, 142]], [0.5, [32, 144, 140]],
  [0.6, [34, 167, 132]], [0.7, [68, 190, 112]], [0.8, [121, 209, 81]],
  [0.9, [189, 222, 38]], [1.0, [253, 231, 36]]
];
function viridisColor(t) {
  if (!isFinite(t)) return 'rgb(68,1,84)';
  if (t <= 0) return 'rgb(68,1,84)';
  if (t >= 1) return 'rgb(253,231,36)';
  for (var i = 1; i < VIRIDIS_STOPS.length; i++) {
    if (t <= VIRIDIS_STOPS[i][0]) {
      var t0 = VIRIDIS_STOPS[i-1][0], t1 = VIRIDIS_STOPS[i][0];
      var c0 = VIRIDIS_STOPS[i-1][1], c1 = VIRIDIS_STOPS[i][1];
      var f = (t - t0) / (t1 - t0);
      var r = Math.round(c0[0] + f * (c1[0] - c0[0]));
      var g = Math.round(c0[1] + f * (c1[1] - c0[1]));
      var b = Math.round(c0[2] + f * (c1[2] - c0[2]));
      return 'rgb(' + r + ',' + g + ',' + b + ')';
    }
  }
  return 'rgb(253,231,36)';
}

function getActiveScenarioIndices() {
  if (state.scenarioMode === 'avg') {
    var arr = []; for (var i=0; i<nS; i++) arr.push(i); return arr;
  }
  return [parseInt(state.scenarioMode)];
}

// ---- Compute view ----
//
// computeYValues dispatches on state.yAxisMode to produce the y-axis
// values for every IV. Modes:
//
//   'avgScore'   mean PvPoke score across selected scenarios + opponents
//                (the original behavior)
//   'winsPvpoke' count of (opp, scenario) pairs the IV wins (score >= 500)
//                against the PvPoke-default opponent IV cohort
//   'winsRank1'  same against rank-1-stat-product opponent IVs
//   'winsMirror' total mirror-match wins from the slayer iteration's
//                final round. SPARSE: only the slayer survivors have a
//                value here. Returns NaN for missing IVs so the trace
//                builders can filter them out cleanly.
//
// Wins modes ignore state.oppIvMode and state.scenarioMode for source
// selection (winsPvpoke always reads pvpoke scores, etc.) but do
// honor scenarioMode for which scenarios contribute to the count.
function computeYValues(mi) {
  var mode = state.yAxisMode || 'avgScore';
  var sis = getActiveScenarioIndices();
  var nSel = sis.length;

  if (mode === 'winsMirror') {
    // Sparse mode: pull from DATA.mirrorWinsByIv. Missing IVs become
    // NaN so downstream trace builders can detect and skip them.
    var mw = DATA.mirrorWinsByIv || {};
    var out = new Float64Array(nIvs);
    for (var iv = 0; iv < nIvs; iv++) {
      out[iv] = (mw[iv] !== undefined) ? mw[iv] : NaN;
    }
    return out;
  }

  // Pick the underlying score array for the active mode.
  var scoreMode;
  if (mode === 'winsPvpoke') scoreMode = 'pvpoke';
  else if (mode === 'winsRank1') scoreMode = 'rank1';
  else scoreMode = state.oppIvMode;  // 'avgScore' uses the active oppIvMode
  var scores = getScores(mi, scoreMode);
  if (!scores) return null;

  if (mode === 'winsPvpoke' || mode === 'winsRank1') {
    var winCounts = new Float64Array(nIvs);
    for (var ivW = 0; ivW < nIvs; ivW++) {
      var c = 0;
      for (var kW = 0; kW < nSel; kW++) {
        var siW = sis[kW];
        var baseW = ivW * nS * nO + siW * nO;
        for (var oiW = 0; oiW < nO; oiW++) {
          if (scores[baseW + oiW] >= 500) c++;
        }
      }
      winCounts[ivW] = c;
    }
    return winCounts;
  }

  // 'avgScore' (default)
  var avgs = new Float64Array(nIvs);
  for (var iv2 = 0; iv2 < nIvs; iv2++) {
    var sum = 0;
    for (var k2 = 0; k2 < nSel; k2++) {
      var si2 = sis[k2];
      var base2 = iv2 * nS * nO + si2 * nO;
      for (var oi2 = 0; oi2 < nO; oi2++) sum += scores[base2 + oi2];
    }
    avgs[iv2] = sum / (nSel * nO);
  }
  return avgs;
}

// Helper: is this y-mode "sparse" (missing values represented as NaN)?
// Used by all trace builders to skip points instead of plotting NaN.
function isSparseMode(mode) {
  return mode === 'winsMirror';
}

function computeRanks(avgs) {
  var indices = new Array(nIvs);
  for (var i=0; i<nIvs; i++) indices[i] = i;
  // NaN entries (from sparse y-modes) get pushed to the end so they
  // don't accidentally get rank #1 — JS's default sort treats NaN
  // comparisons as "equal," producing undefined ordering otherwise.
  indices.sort(function(a,b) {
    var va = avgs[a], vb = avgs[b];
    var na = isNaN(va), nb = isNaN(vb);
    if (na && nb) return 0;
    if (na) return 1;
    if (nb) return -1;
    return vb - va;
  });
  var ranks = new Uint16Array(nIvs);
  for (var r=0; r<nIvs; r++) ranks[indices[r]] = r + 1;
  return ranks;
}

function computeView() {
  // Look up the active mode's label/maxValue from DATA.yAxisModes so
  // hover, layout, and table all read from one source of truth.
  var mode = state.yAxisMode || 'avgScore';
  currentYLabel = 'Avg Battle Score';
  currentYMax = null;
  if (DATA.yAxisModes) {
    for (var ym = 0; ym < DATA.yAxisModes.length; ym++) {
      if (DATA.yAxisModes[ym].id === mode) {
        currentYLabel = DATA.yAxisModes[ym].label;
        currentYMax = DATA.yAxisModes[ym].maxValue;
        break;
      }
    }
  }
  currentYIsSparse = isSparseMode(mode);

  yValues = computeYValues(state.movesetIdx);
  yRanks = computeRanks(yValues);
  if (DATA.referenceIdx >= 0 && DATA.referenceIdx !== state.movesetIdx) {
    refYValues = computeYValues(DATA.referenceIdx);
    refYRanks = computeRanks(refYValues);
  } else {
    refYValues = null;
    refYRanks = null;
  }
}

// ---- Hover text ----
function shortName(name) { return name.split('(')[0].trim().substring(0, 12); }

function buildHoverText(iv) {
  var a = DATA.ivA[iv], d = DATA.ivD[iv], s = DATA.ivS[iv];
  // Format the y-value line based on the active mode. Wins-based modes
  // show "X / N" using the precomputed currentYMax; avg-score shows
  // a one-decimal float.
  var yv = yValues[iv];
  var yLine;
  if (currentYMax != null && isFinite(yv)) {
    yLine = currentYLabel + ': ' + Math.round(yv) + ' / ' + currentYMax;
  } else if (isFinite(yv)) {
    yLine = currentYLabel + ': ' + yv.toFixed(1);
  } else {
    yLine = currentYLabel + ': (no data)';
  }
  var lines = [
    'IVs: '+a+'/'+d+'/'+s,
    'L'+DATA.ivLv[iv]+' CP'+DATA.ivCp[iv],
    'Atk:'+DATA.ivAtk[iv].toFixed(2)+' Def:'+DATA.ivDef[iv].toFixed(2)+' HP:'+DATA.ivHp[iv],
    'SP Rank: #'+DATA.spRanks[iv]+' | Y Rank: #'+yRanks[iv],
    yLine,
  ];
  var tier = DATA.ivTiers[iv];
  if (tier >= 0) lines.push('Tier: '+tierNames[tier]);
  // Slayer membership: shown for any IV that landed in an Atk/Bulk/CMP
  // Slayer category during iterative slayer discovery.
  if (DATA.slayerCatsByIv && DATA.slayerCatsByIv[iv]) {
    lines.push('Slayer: '+DATA.slayerCatsByIv[iv].join(', '));
  }
  // Anchor-clear membership: which named anchors (mirror BP, etc.) the
  // IV passes among those for which we emitted a matchup-flip bullet.
  if (DATA.anchorClearByIv && DATA.anchorClearByIv[iv]) {
    lines.push('Clears: '+DATA.anchorClearByIv[iv].join(', '));
  }

  // Diff vs reference IV (PvPoke default or rank 1, depending on opp IV mode)
  var refIv = (state.oppIvMode === 'rank1') ? DATA.rank1RefIvIdx : DATA.pvpokeRefIvIdx;
  var refDesc = (state.oppIvMode === 'rank1') ? 'SP Rank 1' : 'Default IVs';
  if (refIv >= 0 && iv !== refIv) {
    lines.push('');
    lines.push('vs '+refDesc+' ('+DATA.ivA[refIv]+'/'+DATA.ivD[refIv]+'/'+DATA.ivS[refIv]+'):');
    appendMatchupDiff(lines, state.movesetIdx, iv, state.movesetIdx, refIv);
  }

  // Diff vs reference moveset (same IV)
  if (refYValues && DATA.referenceIdx >= 0 && DATA.referenceIdx !== state.movesetIdx) {
    lines.push('');
    lines.push('vs Ref ('+DATA.movesets[DATA.referenceIdx].prettyLabel+'):');
    appendMatchupDiff(lines, state.movesetIdx, iv, DATA.referenceIdx, iv);
  }

  return lines.join('<br>');
}

function appendMatchupDiff(lines, mi1, iv1, mi2, iv2) {
  var s1 = getScores(mi1, state.oppIvMode);
  var s2 = getScores(mi2, state.oppIvMode);
  var sis = getActiveScenarioIndices();
  for (var k=0; k<sis.length; k++) {
    var si = sis[k];
    var gained = [], lost = [];
    for (var oi=0; oi<nO; oi++) {
      var sc1 = s1[iv1*nS*nO + si*nO + oi];
      var sc2 = s2[iv2*nS*nO + si*nO + oi];
      var w1 = sc1 >= 500, w2 = sc2 >= 500;
      if (w1 && !w2) gained.push(shortName(DATA.opponents[oi]));
      else if (!w1 && w2) lost.push(shortName(DATA.opponents[oi]));
    }
    var sc = DATA.scenarios[si];
    var lab = sc[0]+'v'+sc[1];
    var parts = [];
    if (gained.length) parts.push('+'+gained.join(','));
    if (lost.length) parts.push('-'+lost.join(','));
    lines.push('  '+lab+': '+(parts.length ? parts.join(' | ') : '(same)'));
  }
}

// ---- Build Plotly traces ----
function buildTraces() {
  computeView();
  var cm = state.colorMode || 'threshold';
  var hasTiers = tierNames.length > 0;
  var traces = [];

  // otherMin/Max are computed during the threshold-mode "Other" trace
  // build below and reused by the slayer overlay so untiered slayer
  // points are colored on the same Viridis range Plotly uses for the
  // base Other trace. Initialized here so they're in scope outside the
  // if branch as well.
  var otherMin = Infinity, otherMax = -Infinity;
  if (cm === 'threshold' && hasTiers) {
    // --- Threshold tier coloring ---
    var otherX=[], otherY=[], otherText=[], otherColor=[];
    for (var iv=0; iv<nIvs; iv++) {
      if (currentYIsSparse && !isFinite(yValues[iv])) continue;
      if (!DATA.ivAllTiers[iv] || DATA.ivAllTiers[iv].length === 0) {
        otherX.push(DATA.spRanks[iv]);
        otherY.push(yValues[iv]);
        otherText.push(buildHoverText(iv));
        otherColor.push(yValues[iv]);
        if (yValues[iv] < otherMin) otherMin = yValues[iv];
        if (yValues[iv] > otherMax) otherMax = yValues[iv];
      }
    }
    if (otherX.length) {
      traces.push({
        name:'Other', x:otherX, y:otherY, text:otherText,
        mode:'markers', type:'scattergl', hoverinfo:'text',
        marker:{size:2, color:otherColor, colorscale:'Viridis', opacity:0.15}
      });
    }
    // Tier traces are collected separately and appended AFTER the
    // slayer/anchor overlays so they render on top (Plotly z-order =
    // trace insertion order).
    var _tierTraces = [];
    for (var ti=0; ti<tierNames.length; ti++) {
      var tx=[], ty=[], tt=[];
      for (var iv=0; iv<nIvs; iv++) {
        if (currentYIsSparse && !isFinite(yValues[iv])) continue;
        if (DATA.ivAllTiers[iv] && DATA.ivAllTiers[iv].indexOf(ti) >= 0) {
          tx.push(DATA.spRanks[iv]);
          ty.push(yValues[iv]);
          tt.push(buildHoverText(iv));
        }
      }
      if (tx.length) {
        _tierTraces.push({
          name:tierNames[ti]+' ('+DATA.tiers[ti].desc+')',
          x:tx, y:ty, text:tt,
          mode:'markers', type:'scattergl', hoverinfo:'text',
          marker:{size:7, color:tierColors[ti], opacity:0.9,
                   line:{width:1, color:'#000'}}
        });
      }
    }
  } else {
    // --- Stat or score coloring (single trace) ---
    var ax=[], ay=[], at=[], ac=[];
    var cLabel = 'Avg Score';
    for (var iv=0; iv<nIvs; iv++) {
      if (currentYIsSparse && !isFinite(yValues[iv])) continue;
      ax.push(DATA.spRanks[iv]);
      ay.push(yValues[iv]);
      at.push(buildHoverText(iv));
      if (cm === 'hp') { ac.push(DATA.ivHp[iv]); cLabel = 'HP'; }
      else if (cm === 'def') { ac.push(DATA.ivDef[iv]); cLabel = 'Defense'; }
      else if (cm === 'atk') { ac.push(DATA.ivAtk[iv]); cLabel = 'Attack'; }
      else { ac.push(yValues[iv]); }
    }
    // Use a colorscale that's bright against dark background
    var cscale = (cm === 'hp') ? 'YlOrRd' : (cm === 'def') ? 'Blues' : (cm === 'atk') ? 'RdYlGn' : 'Viridis';
    traces.push({
      name:'All IVs (colored by '+cLabel+')', x:ax, y:ay, text:at,
      mode:'markers', type:'scattergl', hoverinfo:'text',
      marker:{size:3.5, color:ac, colorscale:cscale, opacity:0.6,
               colorbar:{title:cLabel, len:0.6},
               reversescale: (cm === 'atk')}
    });
  }

  // ---- Slayer IV overlay ----
  // Always rendered (regardless of color mode) so users can see slayer
  // spreads in context. Coloring depends on the active color mode:
  //
  // * Threshold mode: fill = the IV's tier color (or white if untiered),
  //   border = gold to distinguish slayer points from non-slayer points
  //   in the same tier. The fill matches "what color this point would
  //   be if it weren't a slayer" so users can visually map a slayer
  //   star-diamond back to its tier identity.
  //
  // * Stat/score modes (HP/Def/Atk/Score): fill = gold so the slayer
  //   points are clearly distinct from the colorscale gradient of the
  //   base trace. (Per-point colorscale matching is awkward in Plotly
  //   when mixed with fixed tier colors, and gold reads cleanly against
  //   any of the stat colorscales we use.)
  //
  // SVG `scatter` is used (not scattergl) because scattergl has limited
  // symbol support and can't render `star-diamond`; the slayer set is
  // small enough (~tens of points) that SVG performance is fine.
  //
  // Defensive: validate each entry is a non-negative integer index into
  // the IV arrays. A bad entry (e.g. an IV triple that wasn't translated
  // to a canonical index) would otherwise produce undefined x/y values
  // and cause Plotly to silently fail to render the *entire* plot.
  // Build O(1) lookup sets for slayer and anchor-clear membership.
  // A point may belong to one set, the other, or both. Marker symbol
  // depends on which sets it's in:
  //   * slayer only       → triangle-down
  //   * anchor-clear only → triangle-up
  //   * both              → hexagram
  // Each set gets its own legend entry ("Slayer IVs", "Anchor IVs")
  // so they can be isolated independently. "Both" points are drawn
  // twice (once per trace) on top of each other with the same hexagram
  // symbol — visually identical, hover works on either.
  var slayerSet = {};
  if (DATA.slayerIvs) {
    for (var ssi = 0; ssi < DATA.slayerIvs.length; ssi++) {
      slayerSet[DATA.slayerIvs[ssi]] = true;
    }
  }
  var anchorSet = {};
  if (DATA.anchorClearIvs) {
    for (var asi = 0; asi < DATA.anchorClearIvs.length; asi++) {
      anchorSet[DATA.anchorClearIvs[asi]] = true;
    }
  }

  // Per-IV color: matches "what the point would look like in its base
  // trace." In threshold mode, tier color if tiered or per-point Viridis
  // matched against the Other trace's range if untiered. In stat/score
  // modes, a fixed gold fill so the overlay stays distinct from the
  // colorscale gradient.
  function overlayFill(iv) {
    if (cm === 'threshold' && hasTiers) {
      var t = DATA.ivTiers[iv];
      if (t >= 0) return tierColors[t];
      var range = otherMax - otherMin;
      var t01 = (range > 0) ? (yValues[iv] - otherMin) / range : 0.5;
      return viridisColor(t01);
    }
    return '#FFD700';
  }

  function overlaySymbol(iv) {
    var inSlayer = !!slayerSet[iv];
    var inAnchor = !!anchorSet[iv];
    if (inSlayer && inAnchor) return 'hexagram';
    if (inSlayer) return 'triangle-down';
    return 'triangle-up';  // anchor only
  }

  // Build one trace per overlay set. Defensive: validate each entry
  // is a non-negative integer index into the IV arrays. A bad entry
  // (e.g. an IV triple that wasn't translated to a canonical index)
  // would otherwise produce undefined x/y values and cause Plotly to
  // silently fail to render the *entire* plot.
  function buildOverlayTrace(name, ivList, borderColor) {
    if (!ivList || ivList.length === 0) return null;
    var ox = [], oy = [], ot = [], ocol = [], osym = [];
    for (var k = 0; k < ivList.length; k++) {
      var iv = ivList[k];
      if (typeof iv !== 'number' || iv < 0 || iv >= nIvs) continue;
      var sp = DATA.spRanks[iv];
      var av = yValues[iv];
      if (typeof sp !== 'number' || typeof av !== 'number') continue;
      // In sparse y-modes (winsMirror), drop IVs with no value.
      if (currentYIsSparse && !isFinite(av)) continue;
      ox.push(sp);
      oy.push(av);
      ot.push(buildHoverText(iv));
      ocol.push(overlayFill(iv));
      osym.push(overlaySymbol(iv));
    }
    if (ox.length === 0) return null;
    return {
      name: name,
      x: ox, y: oy, text: ot,
      mode: 'markers', type: 'scatter', hoverinfo: 'text',
      marker: {
        size: 5,
        color: ocol,
        symbol: osym,
        opacity: 0.85,
        line: { width: 1, color: borderColor }
      }
    };
  }

  var slayerTrace = buildOverlayTrace('Slayer IVs', DATA.slayerIvs, '#FFD700');
  if (slayerTrace) traces.push(slayerTrace);
  var anchorTrace = buildOverlayTrace('Anchor IVs', DATA.anchorClearIvs, '#00ffff');
  if (anchorTrace) traces.push(anchorTrace);

  // Tier traces go LAST so they render on top of overlays.
  if (typeof _tierTraces !== 'undefined') {
    for (var _ti = 0; _ti < _tierTraces.length; _ti++) {
      traces.push(_tierTraces[_ti]);
    }
  }

  return traces;
}

// ---- Summary table ----
function updateSummaryTable() {
  // Get top 10 by battle rank
  var indices = [];
  for (var i=0; i<nIvs; i++) indices.push(i);
  indices.sort(function(a,b) { return yRanks[a] - yRanks[b]; });
  var top = indices.slice(0, 10);

  var hasTiers = tierNames.length > 0;
  var h = '<table><tr><th>Y Rank</th><th>IVs</th><th>Level</th><th>CP</th>';
  h += '<th>Atk</th><th>Def</th><th>HP</th><th>SP Rank</th><th>'+currentYLabel+'</th>';
  if (hasTiers) h += '<th>Tier</th>';
  h += '</tr>';
  for (var k=0; k<top.length; k++) {
    var iv = top[k];
    // In sparse y-modes, the top-by-yRanks list still includes IVs
    // with NaN y-values; skip those so the table only lists ranked IVs.
    if (currentYIsSparse && !isFinite(yValues[iv])) continue;
    var tier = DATA.ivTiers[iv];
    h += '<tr><td>#'+yRanks[iv]+'</td>';
    h += '<td>'+DATA.ivA[iv]+'/'+DATA.ivD[iv]+'/'+DATA.ivS[iv]+'</td>';
    h += '<td>'+DATA.ivLv[iv]+'</td><td>'+DATA.ivCp[iv]+'</td>';
    h += '<td>'+DATA.ivAtk[iv].toFixed(2)+'</td><td>'+DATA.ivDef[iv].toFixed(2)+'</td>';
    h += '<td>'+DATA.ivHp[iv]+'</td><td>#'+DATA.spRanks[iv]+'</td>';
    h += '<td>'+(isFinite(yValues[iv]) ? yValues[iv].toFixed(1) : '\u2014')+'</td>';
    if (hasTiers) {
      if (tier >= 0) {
        h += '<td><span class="tier-badge" style="background:'+tierColors[tier]+';color:#000">'+tierNames[tier]+'</span></td>';
      } else h += '<td>\u2014</td>';
    }
    h += '</tr>';
  }
  h += '</table>';
  document.getElementById('summary').innerHTML = h;
}

// ---- Methodology ----
function updateMethodology() {
  var scenSel = document.getElementById('scenario-sel');
  var scenDesc = scenSel ? scenSel.options[scenSel.selectedIndex].text : '__SHIELD_DESC_DEFAULT__';
  var modeDesc = state.oppIvMode === 'rank1' ? 'stat-product rank 1 IVs' :
    "PvPoke\'s default IVs (the IVs pvpoke.com uses when you load a matchup)";
  var h = '<hr style="border-color:#0f3460; margin-top:30px">';
  h += '<strong>Methodology</strong><br>';
  h += 'Each of the '+nIvs+' valid IV spreads is leveled to the highest level under the ';
  h += '__LEAGUE_TITLE__ League CP cap (__LEAGUE_CP_CAP__). For each IV, a battle is simulated ';
  h += 'against each of the '+nO+' opponents in the __OPP_DESC_ESCAPED__ pool ';
  h += 'in the '+scenDesc+' shield scenario(s), using the pvpoke_dp policy. ';
  h += 'Opponents use '+modeDesc+' at their best level.<br><br>';
  h += '<strong>Avg Battle Score</strong> = mean PvPoke score across opponents/scenarios. ';
  h += '500 = tie, &gt;500 = win, &lt;500 = loss.<br>';
  h += '<strong>Battle Rank</strong> = position when sorted by Avg Battle Score (desc). ';
  h += '<strong>Stat Product Rank</strong> (x-axis) = traditional PvP IV rank (Atk\u00d7Def\u00d7HP).';
  document.getElementById('methodology').innerHTML = h;
}

// ---- Plot ----
var origOpacities = [];
function updateView() {
  // Read state from dropdowns
  var msel = document.getElementById('moveset-sel');
  if (msel) state.movesetIdx = parseInt(msel.value);
  var ssel = document.getElementById('scenario-sel');
  if (ssel) state.scenarioMode = ssel.value;
  var osel = document.getElementById('oppiv-sel');
  if (osel) state.oppIvMode = osel.value;
  var csel = document.getElementById('color-sel');
  if (csel) state.colorMode = csel.value;
  var ysel = document.getElementById('yaxis-sel');
  if (ysel) state.yAxisMode = ysel.value;
  lockedIdx = -1;

  var traces = buildTraces();
  origOpacities = traces.map(function(t) { return t.marker.opacity; });

  // Compute fixed axis ranges from all data
  var allX = [], allY = [];
  traces.forEach(function(t) { allX = allX.concat(t.x); allY = allY.concat(t.y); });
  var xMin = Math.min.apply(null, allX), xMax = Math.max.apply(null, allX);
  var yMin = Math.min.apply(null, allY), yMax = Math.max.apply(null, allY);
  var xPad = Math.max(1, (xMax-xMin)*0.02), yPad = Math.max(0.5, (yMax-yMin)*0.03);

  // Cluster overlay shapes. Hidden in non-avgScore y-modes because the
  // cluster gaps are derived from the avg-score distribution and would
  // be plotted at the wrong y-coordinates against any other metric.
  var shapes = [];
  var annotations = [];
  var clusterChk = document.getElementById('cluster-chk');
  if (clusterChk && clusterChk.checked && state.yAxisMode === 'avgScore') {
    var gapKey = state.movesetIdx + '_' + state.oppIvMode;
    var gapData = DATA.clusterGaps[gapKey];
    if (gapData) {
      var sis = getActiveScenarioIndices();
      // For "avg" mode, take the union of gaps across all scenarios (deduplicated)
      var gapYs = [];
      if (sis.length === nS) {
        // Average mode: use the gaps from each scenario, pick the most common
        var allGaps = [];
        for (var k=0; k<nS; k++) { allGaps = allGaps.concat(gapData[k] || []); }
        // Deduplicate within ±2 points
        allGaps.sort(function(a,b){ return b-a; });
        for (var g=0; g<allGaps.length; g++) {
          var dup = false;
          for (var h=0; h<gapYs.length; h++) { if (Math.abs(allGaps[g]-gapYs[h]) < 2) dup = true; }
          if (!dup) gapYs.push(allGaps[g]);
        }
      } else {
        gapYs = gapData[sis[0]] || [];
      }
      var clusterColors = ['rgba(233,69,96,0.5)', 'rgba(88,166,255,0.4)', 'rgba(63,185,80,0.3)'];
      for (var gi=0; gi<gapYs.length && gi<3; gi++) {
        shapes.push({
          type:'line', xref:'paper', x0:0, x1:1,
          y0:gapYs[gi], y1:gapYs[gi],
          line:{ color:clusterColors[gi], width:2, dash:'dash' }
        });
        annotations.push({
          xref:'paper', x:1.0, y:gapYs[gi], xanchor:'left',
          text:' Cluster ' + (gi+1) + ' boundary',
          showarrow:false, font:{size:10, color:clusterColors[gi]}
        });
      }
    }
  }

  var layout = {
    title: DATA.movesets[state.movesetIdx].prettyLabel,
    xaxis: {title:'Stat Product Rank (1=best)', range:[xMax+xPad, xMin-xPad], fixedrange:true},
    yaxis: {title:currentYLabel, range:[yMin-yPad, yMax+yPad], fixedrange:true},
    paper_bgcolor:'#1a1a2e', plot_bgcolor:'#16213e',
    font:{color:'#e0e0e0'}, hovermode:'closest',
    legend:{bgcolor:'rgba(22,33,62,0.8)', bordercolor:'#0f3460', borderwidth:1},
    shapes: shapes,
    annotations: annotations
  };

  Plotly.react('plot', traces, layout, {responsive:true});
  reattachLegendHandlers();
  updateSummaryTable();
  updateMethodology();
}

// ---- Legend hover/click ----
function highlightTrace(idx) {
  var gd = document.getElementById('plot');
  for (var j=0; j<origOpacities.length; j++) {
    var op = (j===idx) ? Math.min(1.0, origOpacities[j]+0.15) : 0.03;
    Plotly.restyle(gd, {'marker.opacity':op}, [j]);
  }
}
function restoreAll() {
  var gd = document.getElementById('plot');
  for (var j=0; j<origOpacities.length; j++) {
    Plotly.restyle(gd, {'marker.opacity':origOpacities[j]}, [j]);
  }
}
function reattachLegendHandlers() {
  var gd = document.getElementById('plot');
  gd.on('plotly_legendclick', function() { return false; });
  gd.on('plotly_legenddoubleclick', function() { return false; });
  var attempts = 0;
  function tryAttach() {
    var items = gd.querySelectorAll('.legend .traces');
    if (items.length === 0 && attempts < 50) { attempts++; setTimeout(tryAttach, 100); return; }
    items.forEach(function(el, idx) {
      el.style.cursor = 'pointer';
      el.addEventListener('mouseenter', function() { if (lockedIdx<0) highlightTrace(idx); });
      el.addEventListener('mouseleave', function() { if (lockedIdx<0) restoreAll(); });
      el.addEventListener('click', function() {
        if (lockedIdx===idx) { lockedIdx=-1; restoreAll(); }
        else { lockedIdx=idx; highlightTrace(idx); }
      });
    });
  }
  tryAttach();
}

// ---- Init ----
updateView();