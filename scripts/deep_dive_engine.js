
// ---- State ----
var state = {
  movesetIdx: 0,
  scenarioMode: __SCENARIO_MODE_DEFAULT__,
  oppIvMode: '__OPP_IV_MODE_DEFAULT__',
  colorMode: 'threshold',
  yAxisMode: 'avgScore',
  // User-collection state — populated by loadCollection() after the
  // user pastes/uploads a Poke Genie CSV. Null until then.
  //   userRecords: array of {mon, stats, matched, canonicalIvIdx, onGrid}
  //                where canonicalIvIdx is the index into DATA.ivA/D/S
  //                for this mon's IV triple, or -1 if the exact triple
  //                isn't one of the dive's simulated IVs.
  //   userStatus:  short text for the status-line span.
  //   showOnlyMine: when true, the scatter filters to ONLY user-owned
  //                 IVs (base traces drop points for non-owned IVs).
  userRecords: null,
  userStatus: '',
  showOnlyMine: false,
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
// Short name for matchup diff opponents. 4 chars is the sweet spot:
// compact enough that a scenario row with 4 gained + 4 lost fits on
// one readable line even on 61-opponent dives, still long enough to
// disambiguate (Med=Medicham, Ann=Annihilape, Tink=Tinkaton, etc).
// Occasional collision (e.g. Stunfisk vs Stunfisk Galarian both →
// Stun) is acceptable — context usually makes it clear and the full
// opponent list is in the dive metadata anyway.
function shortName(name) { return name.split('(')[0].trim().substring(0, 4); }

// Abbreviate Python-side anchor parent ids like "corviknight_shadow"
// for display in the "Clears:" hover line. 4-char base + "_s" suffix
// for shadow variants preserves the shadow distinction without
// blowing up the tooltip width:
//   corviknight          -> corv
//   dusknoir_shadow      -> dusk_s
//   stunfisk_galarian    -> stun
//   feraligatr_shadow    -> fera_s
function shortParentName(name) {
  if (!name) return '';
  var n = String(name);
  var isShadow = false;
  var suf = '_shadow';
  if (n.length > suf.length && n.substring(n.length - suf.length) === suf) {
    isShadow = true;
    n = n.substring(0, n.length - suf.length);
  }
  // Strip any trailing form suffix like "_galarian" / "_alola" — we
  // lose the form distinction, but 4 chars is already lossy and the
  // focal point of the Clears line is just rough opponent identity.
  n = n.split('_')[0];
  n = n.split(' ')[0].split('(')[0].trim().substring(0, 4);
  return isShadow ? n + '_s' : n;
}

// Push a label + comma-separated item list to `lines`, wrapping
// onto multiple lines when a single line would exceed `maxWidth`
// chars. Continuation lines get an indent matching the label's
// visual width, so "Clears: a, b, c" wraps as:
//     Clears: a, b,
//             c, d
// instead of a single ultra-wide line that forces the whole hover
// tooltip to expand horizontally.
function appendWrappedListLines(lines, label, items, maxWidth) {
  if (!items || items.length === 0) return;
  var indent = new Array(label.length + 2).join(' ');  // "Clears:".length + 1 space
  var current = label + ' ';
  var first = true;
  for (var i = 0; i < items.length; i++) {
    var sep = (i < items.length - 1) ? ', ' : '';
    var token = items[i] + sep;
    if (!first && (current.length + token.length) > maxWidth) {
      lines.push(current.replace(/\s+$/, ''));
      current = indent + token;
    } else {
      current += token;
      first = false;
    }
  }
  lines.push(current.replace(/\s+$/, ''));
}

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
  // Names are abbreviated via shortParentName (4-char base + _s for
  // shadow) and the resulting list is line-wrapped on comma boundaries
  // so the tooltip stays compact even when an IV clears many anchors.
  if (DATA.anchorClearByIv && DATA.anchorClearByIv[iv]) {
    var clears = DATA.anchorClearByIv[iv].map(shortParentName);
    appendWrappedListLines(lines, 'Clears:', clears, 45);
  }

  // User collection annotation: if the user has any mons at this exact
  // canonical IV triple, append a "Yours:" block here so the info
  // appears on EVERY trace's hover (base Other, tier, slayer, anchor,
  // AND user overlay) instead of only on the user overlay. Previously
  // only the user overlay trace constructed this text, so hovering a
  // base/tier point would silently omit user info even if owned.
  //
  // Uses the ownedByIv lookup cache (populated in loadCollection)
  // instead of linearly scanning state.userRecords. For collections
  // in the hundreds-to-thousands of mons, the old O(n) scan per IV
  // was rebuilding 4096 × N every time buildTraces ran.
  if (state.userRecords && state.userRecords.length > 0) {
    var owned = (state.ownedByIv && state.ownedByIv[iv]) || [];
    if (owned.length > 0) {
      // Sort by current CP descending so the best in-game search
      // target leads.
      owned.sort(function(a, b) { return b.mon.cp - a.mon.cp; });
      lines.push('');
      lines.push('<b>\u2605 Yours (' + owned.length + '):</b>');
      for (var urL = 0; urL < Math.min(owned.length, 4); urL++) {
        var rcL = owned[urL];
        var mc = (rcL.stats && rcL.stats.cp != null) ? rcL.stats.cp : '?';
        var ml = (rcL.stats && rcL.stats.level != null) ? rcL.stats.level : '?';
        var parts = [
          '  <b>CP ' + rcL.mon.cp + '</b> @ L' + rcL.mon.level +
          ' \u2192 CP ' + mc + ' @ L' + ml,
        ];
        if (rcL.csvSpecies && rcL.csvSpecies !== DATA.species) {
          parts.push('    (' + (rcL.mon.is_shadow ? 'Shadow ' : '') +
                     rcL.csvSpecies + ')');
        } else if (rcL.mon.is_shadow) {
          parts.push('    (Shadow)');
        }
        if (rcL.mon.lucky) parts[parts.length - 1] += ' \u2728';
        if (rcL.matched && rcL.matched.length > 0) {
          parts.push('    Qualifies: ' + rcL.matched.join(', '));
        }
        for (var pp = 0; pp < parts.length; pp++) lines.push(parts[pp]);
      }
      if (owned.length > 4) {
        lines.push('  +' + (owned.length - 4) + ' more');
      }
    }
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
    // Cap per direction so the tooltip stays a reasonable size on
    // dives with large opponent pools (61 for GL top50+CS dives ×
    // 9 scenarios × 2 moveset comparisons = massive tooltip
    // without this). Overflow rendered as "+N more".
    var DIFF_CAP = 4;
    function fmt(arr, sign) {
      if (arr.length === 0) return null;
      var head = arr.slice(0, DIFF_CAP).join(',');
      var more = arr.length > DIFF_CAP ? ('+' + (arr.length - DIFF_CAP)) : '';
      return sign + head + more;
    }
    var parts = [];
    var g = fmt(gained, '+'); if (g) parts.push(g);
    var l = fmt(lost, '-'); if (l) parts.push(l);
    lines.push('  '+lab+': '+(parts.length ? parts.join(' | ') : '(same)'));
  }
}

// ---- User collection ----
//
// Lazy-init: called the first time the user loads a CSV. Sets up the
// POGOCollection module constants from DATA.collection (CPM table,
// shadow multipliers). Idempotent.
var _collectionInitDone = false;
function ensureCollectionReady() {
  if (_collectionInitDone) return true;
  if (!DATA.collection) return false;
  if (typeof POGOCollection === 'undefined') {
    console.error('POGOCollection module missing — paste-box will not work');
    return false;
  }
  POGOCollection.setConstants({
    cpm:            DATA.collection.cpm,
    shadowAtkBonus: DATA.collection.shadowAtkBonus,
    shadowDefMult:  DATA.collection.shadowDefMult,
  });
  _collectionInitDone = true;
  return true;
}

// Build a canonical-IV-index lookup on first use. This maps "a,d,s" →
// index into DATA.ivA/D/S, so we can find the scatter-plot position
// of any user-owned IV that happens to be in the dive's simulated set.
var _canonicalIvIdx = null;
function getCanonicalIvIdx() {
  if (_canonicalIvIdx != null) return _canonicalIvIdx;
  var out = {};
  for (var i = 0; i < nIvs; i++) {
    out[DATA.ivA[i] + ',' + DATA.ivD[i] + ',' + DATA.ivS[i]] = i;
  }
  _canonicalIvIdx = out;
  return out;
}

// Parse CSV text + run matchMons against the dive's thresholds, then
// build a per-record overlay list. Records carry both qualifying and
// non-qualifying mons (non-qualifying = owned but doesn't hit any
// tier) so the UI can show them as a distinct marker. Off-grid mons
// (exact IV triple not in dive's simulated set) get canonicalIvIdx = -1.
function loadCollection(csvText) {
  if (!ensureCollectionReady()) {
    setCollectionStatus('collection support unavailable for this dive', '#ff6b6b');
    return;
  }
  var mons;
  try {
    mons = POGOCollection.parseCsvText(csvText);
  } catch (e) {
    setCollectionStatus('Parse error: ' + e.message, '#ff6b6b');
    return;
  }
  if (mons.length === 0) {
    setCollectionStatus('No rows parsed (empty CSV?)', '#ff6b6b');
    return;
  }

  // matchMons returns ONLY mons that hit at least one tier. To surface
  // non-qualifying-but-owned mons too, we also walk every mon through
  // the same stat-calc path and record an empty `matched` list when
  // nothing hits. The code below mirrors matchMons' internal logic
  // but is deliberately local — we need the "didn't match anything"
  // branch too.
  var coll = DATA.collection;
  var speciesKey = coll.speciesKey;
  var leagueLabel = coll.leagueLabel;
  var pokemonIndex = coll.pokemonIndex;
  var preToFinals = coll.preToFinals;
  var rankLookup = coll.rankLookup;
  var leagueCap = coll.leagueCap;
  var maxLevel = coll.maxLevel;

  // Build the species thresholds dict from the LIVE DATA.tiers array
  // (populated after generate_analysis_sections ran), not from the
  // stale snapshot in coll.thresholds. The snapshot was taken before
  // auto-derive kicked in, so any dive without a TOML (or with a
  // TOML for a different league than the dive) had empty tier
  // names — every user mon fell through to "no qualification" even
  // when the scatter legend showed real tiers.
  var liveTiers = DATA.tiers || [];
  var tierNames = [];
  var speciesThresholds = {};
  for (var lti = 0; lti < liveTiers.length; lti++) {
    var lt = liveTiers[lti];
    if (!lt || !lt.name) continue;
    tierNames.push(lt.name);
    speciesThresholds[lt.name] = {
      attack:  lt.attack  || 0,
      defense: lt.defense || 0,
      stamina: lt.stamina || 0,
    };
  }

  var tierCounts = {};
  for (var ti = 0; ti < tierNames.length; ti++) tierCounts[tierNames[ti]] = 0;

  // Slayer membership: mons whose canonical IV index is in the dive's
  // DATA.slayerIvs set are "slayer" even if they don't hit any tier.
  // DATA.slayerCatsByIv gives the specific Atk/Bulk/CMP labels per IV.
  var slayerIvSet = {};
  if (DATA.slayerIvs) {
    for (var sii = 0; sii < DATA.slayerIvs.length; sii++) {
      slayerIvSet[DATA.slayerIvs[sii]] = true;
    }
  }
  var slayerCount = 0;

  var ivIdxMap = getCanonicalIvIdx();
  var records = [];
  var ownedCount = 0, qualifyingCount = 0, offGridCount = 0, overCapCount = 0;

  for (var mi = 0; mi < mons.length; mi++) {
    var mon = mons[mi];
    var csvSpecies = POGOCollection.getSpeciesName(mon.name, mon.form, mon.is_shadow);
    // Does this mon pertain to the dive's species? Direct match or
    // walkup via preToFinals.
    var matches = (csvSpecies === speciesKey);
    if (!matches) {
      var finals = POGOCollection.getFinalForms(csvSpecies, preToFinals);
      if (finals.indexOf(speciesKey) >= 0) matches = true;
    }
    if (!matches) continue;

    var base = pokemonIndex[speciesKey];
    var stats = POGOCollection.ivsToStatsAtCap(
      base.atk, base.def, base.hp,
      mon.atk_iv, mon.def_iv, mon.sta_iv,
      { shadow: mon.is_shadow, maxLevel: maxLevel, maxCp: leagueCap }
    );
    if (stats == null) continue;

    // Rank (for hover / onlytop). Default 4096 if lookup missing.
    var ivKey = mon.atk_iv + ',' + mon.def_iv + ',' + mon.sta_iv;
    var rank = 4096;
    var rlSpecies = rankLookup && rankLookup[speciesKey];
    var rlBranch  = rlSpecies && rlSpecies[mon.is_shadow ? 'shadow' : 'normal'];
    if (rlBranch && rlBranch[ivKey] != null) rank = rlBranch[ivKey];
    stats.rank = rank;

    var matched = [];
    for (var tname in speciesThresholds) {
      if (!speciesThresholds.hasOwnProperty(tname)) continue;
      var t = speciesThresholds[tname];
      if (stats.attack  < (t.attack  || 0)) continue;
      if (stats.defense < (t.defense || 0)) continue;
      if (stats.stamina < (t.stamina || 0)) continue;
      matched.push(tname);
    }
    for (var k = 0; k < matched.length; k++) {
      if (tierCounts[matched[k]] != null) tierCounts[matched[k]]++;
    }

    var canonicalIdx = ivIdxMap[ivKey];
    if (canonicalIdx == null) canonicalIdx = -1;
    if (canonicalIdx < 0) offGridCount++;
    ownedCount++;

    // Over-cap detection: if the mon's CURRENT level (from the CSV)
    // is higher than the best fitted level we just computed, it means
    // evolving this mon at its current level would produce a final
    // form whose CP exceeds the league cap. Since Pokemon GO has no
    // way to reduce a mon's level, that makes it INELIGIBLE for this
    // league entirely — the stats we computed above are for a
    // hypothetical lower level the mon can't actually reach.
    //
    // We flag these with isOverCap=true so the UI can mark them
    // clearly (the power-up column shows "OVER" instead of the
    // misleading "✓"). They still show up in tier matches because
    // the cross-league comparison is sometimes useful ("this spread
    // would clear GH Great if it fit, but it doesn't — consider UL
    // instead").
    var isOverCap = (mon.level != null && stats.level != null &&
                     mon.level > stats.level);
    if (isOverCap) overCapCount++;
    if (matched.length > 0) qualifyingCount++;

    // Slayer membership: check if this canonical IV is in the
    // dive's slayerIvSet and pull category labels.
    var slayerCats = null;
    if (canonicalIdx >= 0 && slayerIvSet[canonicalIdx]) {
      slayerCats = (DATA.slayerCatsByIv && DATA.slayerCatsByIv[canonicalIdx]) || [];
      slayerCount++;
    }

    records.push({
      mon:             mon,
      csvSpecies:      csvSpecies,
      slayerCats:      slayerCats,
      isOverCap:       isOverCap,
      stats:           stats,
      matched:         matched,
      canonicalIvIdx:  canonicalIdx,
      ivKey:           ivKey,
    });
  }

  state.userRecords = records;

  // Build canonical-iv → [records] lookup once so buildHoverText's
  // "Yours:" section is O(1) per IV instead of O(n) linear scan.
  // For large collections (~600 mons) this is the difference between
  // a snappy hover and a multi-second freeze when building traces.
  var ownedByIv = {};
  for (var oir = 0; oir < records.length; oir++) {
    var oirRec = records[oir];
    if (oirRec.canonicalIvIdx < 0) continue;
    if (!ownedByIv[oirRec.canonicalIvIdx]) ownedByIv[oirRec.canonicalIvIdx] = [];
    ownedByIv[oirRec.canonicalIvIdx].push(oirRec);
  }
  state.ownedByIv = ownedByIv;

  // Status line + tier-card counts.
  var parts = [mons.length + ' rows parsed'];
  parts.push(ownedCount + ' match this dive');
  parts.push(qualifyingCount + ' qualify for >= 1 tier');
  if (slayerCount > 0) parts.push(slayerCount + ' slayer');
  if (overCapCount > 0) parts.push(overCapCount + ' already over cap');
  if (offGridCount > 0) parts.push(offGridCount + ' off-grid (not in simulated set)');
  setCollectionStatus(parts.join(' \u00b7 '), '#9be89b');
  updateTierCardCounts(tierCounts);
  renderMatchesList();
  annotateAnchorBullets();
  updateView();
}

// For each anchor-flip bullet in the analysis layer, look up which of
// the user's owned IVs land in the bullet's precomputed passing set
// and fill the placeholder '<span data-anchor-id="…">' with a short
// "— yours: 0/15/15, 1/14/14" annotation (first 3 hits + "+N more").
// Called from loadCollection after state.userRecords is populated.
// Clears all spans when userRecords is null (called from
// clearCollection).
function annotateAnchorBullets() {
  var spans = document.querySelectorAll('span.user-anchor-hits[data-anchor-id]');
  if (!spans || spans.length === 0) return;

  if (!state.userRecords || state.userRecords.length === 0 ||
      !DATA.anchorFlipSets) {
    for (var i = 0; i < spans.length; i++) {
      spans[i].textContent = '';
      spans[i].removeAttribute('title');
    }
    return;
  }

  // Owned canonical indices → user record (for IV display).
  var ownedByIdx = {};
  for (var r = 0; r < state.userRecords.length; r++) {
    var rec = state.userRecords[r];
    if (rec.canonicalIvIdx >= 0) ownedByIdx[rec.canonicalIvIdx] = rec;
  }

  for (var s = 0; s < spans.length; s++) {
    var span = spans[s];
    var anchorId = span.getAttribute('data-anchor-id');
    var passing = DATA.anchorFlipSets[anchorId] || [];
    var hits = [];
    for (var p = 0; p < passing.length; p++) {
      var ivIdx = passing[p];
      var ownedRec = ownedByIdx[ivIdx];
      if (ownedRec) hits.push(ownedRec);
    }
    if (hits.length === 0) {
      span.textContent = ' - none of yours';
      span.style.color = '#6c7a89';
      span.removeAttribute('title');
      continue;
    }
    // Sort hits by current CP descending so the highest-CP mon the
    // user already owns leads the list (best in-game search target).
    hits.sort(function(a, b) { return b.mon.cp - a.mon.cp; });
    var shown = hits.slice(0, 3).map(function(h) {
      return 'CP' + h.mon.cp + ' ' + h.mon.atk_iv + '/' + h.mon.def_iv + '/' + h.mon.sta_iv;
    }).join(', ');
    var extra = hits.length > 3 ? (' +' + (hits.length - 3) + ' more') : '';
    span.textContent = ' - yours: ' + shown + extra;
    span.style.color = '#9be89b';
    // Full list in the title tooltip for power users.
    var fullList = hits.map(function(h) {
      return 'CP' + h.mon.cp + ' ' + h.mon.atk_iv + '/' + h.mon.def_iv + '/' + h.mon.sta_iv;
    }).join(', ');
    span.setAttribute('title', fullList);
  }
}

// Render a grouped-by-tier list of matching mons so the user can
// decide which to power up. Each tier is its own table sorted by
// battle rank ascending (best first, not current CP) because "rank
// in this dive" is the real answer to "should I power this up?".
// Current CP is shown prominently because that's how the user
// searches in-game. The power-up cost column flags mons as
// "ready" (already maxed), "cheap", or "expensive" based on level
// delta — critical for the UL candy-constrained case.
//
// Each record is also annotated with its yRank (battle rank in the
// active moveset/scenario) so the tier list answers "which of mine
// is actually rank #1" at a glance.
function renderMatchesList() {
  var el = document.getElementById('collection-matches');
  if (!el) return;
  if (!state.userRecords || state.userRecords.length === 0) {
    el.innerHTML = '';
    return;
  }

  // Tier names come from the LIVE DATA.tiers array (populated after
  // analysis sections ran), not DATA.collection.tierNames (which is
  // the stale pre-analysis snapshot and was empty on auto-derive
  // dives). This mirrors the fix in loadCollection.
  var liveTiers = DATA.tiers || [];
  var tierNames = [];
  for (var lti = 0; lti < liveTiers.length; lti++) {
    if (liveTiers[lti] && liveTiers[lti].name) tierNames.push(liveTiers[lti].name);
  }

  // Group qualifying records by tier. A mon that qualifies for
  // multiple tiers appears once per tier.
  var byTier = {};
  for (var i = 0; i < tierNames.length; i++) byTier[tierNames[i]] = [];
  for (var r = 0; r < state.userRecords.length; r++) {
    var rec = state.userRecords[r];
    for (var m = 0; m < rec.matched.length; m++) {
      var tn = rec.matched[m];
      if (byTier[tn]) byTier[tn].push(rec);
    }
  }
  // Slayer group: mons whose IV hit slayer categories, regardless of
  // whether they hit any tier. These are the "not strictly qualifying
  // but still worth powering up for mirror-match slaying" candidates.
  var slayerRecs = [];
  for (var rS = 0; rS < state.userRecords.length; rS++) {
    if (state.userRecords[rS].slayerCats) slayerRecs.push(state.userRecords[rS]);
  }

  // Attach ranks to each record. Two separate ranks:
  //
  //   _battleRank: battle (y-axis) rank in the active plot moveset /
  //                scenario / opp-iv mode. Dive-dependent — requires
  //                the IV to actually be in the simulated set. Set to
  //                null for off-grid mons.
  //
  //   _spRank: stat product rank across ALL 4096 IV triples for the
  //            species, pure-math and independent of the dive. Always
  //            available via DATA.collection.rankLookup (or via
  //            DATA.spRanks for on-grid mons). Used as the
  //            sort-fallback when battle rank isn't available.
  var useBattleRank = (typeof yRanks !== 'undefined' && yRanks != null);
  var rankLookup = (DATA.collection && DATA.collection.rankLookup) || {};
  var collSpecies = (DATA.collection && DATA.collection.speciesKey) || '';
  function lookupSpRank(rec) {
    // On-grid: use DATA.spRanks — same data, cheaper lookup.
    if (rec.canonicalIvIdx >= 0) return DATA.spRanks[rec.canonicalIvIdx];
    // Off-grid: consult the precomputed rank lookup.
    var spBlock = rankLookup[collSpecies];
    if (!spBlock) return null;
    var branch = spBlock[rec.mon.is_shadow ? 'shadow' : 'normal'];
    if (!branch) return null;
    var key = rec.mon.atk_iv + ',' + rec.mon.def_iv + ',' + rec.mon.sta_iv;
    var r = branch[key];
    return (r != null) ? r : null;
  }
  for (var r2 = 0; r2 < state.userRecords.length; r2++) {
    var rec2 = state.userRecords[r2];
    var iv = rec2.canonicalIvIdx;
    rec2._battleRank = (iv >= 0 && useBattleRank) ? yRanks[iv] : null;
    rec2._spRank = lookupSpRank(rec2);
    // _rank is the primary sort key: battle rank when available, SP
    // rank otherwise. Null-safe: records without either end up last.
    if (rec2._battleRank != null) rec2._rank = rec2._battleRank;
    else if (rec2._spRank != null) rec2._rank = rec2._spRank;
    else rec2._rank = 99999;
  }

  function powerUpText(rc) {
    if (rc.isOverCap) return '<span style="color:#e94560">OVER</span>';
    var curLv = rc.mon.level;
    var maxLv = rc.stats ? rc.stats.level : null;
    if (curLv == null || maxLv == null) return '?';
    var d = maxLv - curLv;
    if (d <= 0) return '\u2713';
    var halfLevels = Math.round(d * 2);
    return '+' + halfLevels + ' \u00bdL';
  }

  var sectionIdx = 0;
  var MAX_VISIBLE = 5;

  // Render one grouped section. `extras` is an optional list of
  // {header, cell} objects where `cell(rc)` returns HTML for that
  // row's extra cell. Used to add cross-info columns — e.g. the
  // slayer section shows both "Slayer type" and "Also in" (which
  // tiers the slayer mon ALSO clears), and tier sections could
  // optionally show a "Slayer?" column too.
  function renderSection(heading, recs, extras, sortKey) {
    if (!recs || recs.length === 0) return '';
    if (sortKey === 'atk') {
      recs.sort(function(a, b) {
        var aa = (a.stats ? a.stats.atk : 0), ba = (b.stats ? b.stats.atk : 0);
        if (aa !== ba) return ba - aa;
        return a._rank - b._rank;
      });
    } else {
      recs.sort(function(a, b) {
        if (a._rank !== b._rank) return a._rank - b._rank;
        return b.mon.cp - a.mon.cp;
      });
    }
    var sid = 'matches-section-' + (sectionIdx++);
    var h = '<h5>' + heading + ' - ' + recs.length + ' of yours</h5>';
    h += '<table><tr>' +
         '<th title="Battle rank in the active moveset / opp-IV mode. Dash for off-grid mons whose exact IV was not simulated.">Battle</th>' +
         '<th title="Stat product rank (pure math, computed for all 4096 IV triples). Always available.">SP</th>' +
         '<th>Current CP</th><th>IVs</th>' +
         '<th>Atk</th><th>Def</th><th>HP</th>' +
         '<th>Species</th><th>Power-up</th><th>Max CP</th>';
    if (extras) {
      for (var xh = 0; xh < extras.length; xh++) {
        h += '<th>' + escapeHtml(extras[xh].header) + '</th>';
      }
    }
    h += '</tr>';
    for (var k = 0; k < recs.length; k++) {
      var rc = recs[k];
      var cls = '';
      if (rc.mon.is_shadow) cls += ' shadow';
      if (rc.mon.lucky) cls += ' lucky';
      // Inline display:none for rows past MAX_VISIBLE. Was previously
      // done via a .matches-hidden-row CSS class, but that CSS lives
      // in the Python HTML generator — existing dives patched via
      // patch_dive_engine.py didn't get the CSS update, so the class
      // toggled with no visual effect. Inline style is self-contained.
      var attr = ' data-section="' + sid + '"';
      if (cls) attr += ' class="' + cls.trim() + '"';
      if (k >= MAX_VISIBLE) attr += ' style="display:none"';
      h += '<tr' + attr + '>';
      var brTxt = (rc._battleRank != null) ? ('#' + rc._battleRank) : '-';
      var spTxt = (rc._spRank != null)     ? ('#' + rc._spRank)     : '-';
      h += '<td class="rank">' + brTxt + '</td>';
      h += '<td class="rank-sp">' + spTxt + '</td>';
      h += '<td><b>CP ' + rc.mon.cp + '</b></td>';
      h += '<td>' + rc.mon.atk_iv + '/' + rc.mon.def_iv + '/' + rc.mon.sta_iv + '</td>';
      h += '<td>' + (rc.stats ? rc.stats.atk.toFixed(2) : '?') + '</td>';
      h += '<td>' + (rc.stats ? rc.stats.def.toFixed(2) : '?') + '</td>';
      h += '<td>' + (rc.stats ? rc.stats.hp : '?') + '</td>';
      h += '<td>' + escapeHtml(rc.csvSpecies || '') +
           (rc.mon.lucky ? ' \u2728' : '') +
           (rc.mon.is_shadow ? ' \u263d' : '') + '</td>';
      h += '<td>' + powerUpText(rc) + '</td>';
      h += '<td>' + (rc.stats ? rc.stats.cp : '?') + '</td>';
      if (extras) {
        for (var xc = 0; xc < extras.length; xc++) {
          h += '<td>' + extras[xc].cell(rc) + '</td>';
        }
      }
      h += '</tr>';
    }
    h += '</table>';
    // Show/hide toggle for sections with more than MAX_VISIBLE rows.
    if (recs.length > MAX_VISIBLE) {
      var hiddenCount = recs.length - MAX_VISIBLE;
      h += '<button class="matches-toggle-btn" ' +
           'onclick="toggleMatchesSection(\'' + sid + '\', this)" ' +
           'data-hidden-count="' + hiddenCount + '">' +
           'Show ' + hiddenCount + ' more \u2193</button>';
    }
    return h;
  }

  // Helper: list-or-dash cell for tier/slayer cross-info columns.
  function listOrDash(arr) {
    return (arr && arr.length > 0) ? escapeHtml(arr.join(', ')) : '-';
  }
  // Helper: filter out the current tier from a mon's matched list so
  // the "Also in" column for a tier section doesn't list the tier
  // itself (redundant with the section heading).
  function otherTiersExcept(rc, excludeTier) {
    var out = [];
    for (var ot = 0; ot < (rc.matched || []).length; ot++) {
      if (rc.matched[ot] !== excludeTier) out.push(rc.matched[ot]);
    }
    return out;
  }

  var html = '';
  for (var ti = 0; ti < tierNames.length; ti++) {
    // Per-tier section. "Also in" shows other tiers this mon clears
    // + any slayer categories it hits, so the user can see at a
    // glance whether a tier-qualifying mon is also a mirror-match
    // specialist. Closure captures the current tier name.
    (function(currentTierName, tierIdx) {
      // Def-side tiers sort by Atk desc (contrarian stat); atk-side by battle rank
      var tier = liveTiers[tierIdx];
      var isDefTier = tier && (tier.defense || 0) > 0 && !(tier.attack || 0);
      html += renderSection(
        escapeHtml(currentTierName),
        byTier[currentTierName],
        [
          { header: 'Also in', cell: function(rc) {
              var also = otherTiersExcept(rc, currentTierName);
              if (rc.slayerCats && rc.slayerCats.length > 0) {
                also = also.concat(rc.slayerCats);
              }
              return listOrDash(also);
          } }
        ],
        isDefTier ? 'atk' : null
      );
    })(tierNames[ti], ti);
  }
  // Slayer section: two extra columns — specific slayer categories
  // AND which tiers this slayer mon ALSO clears (blank for slayer-
  // only mons, populated for mons that are both slayer + tier).
  html += renderSection(
    'Slayer IVs',
    slayerRecs,
    [
      { header: 'Slayer type', cell: function(rc) { return listOrDash(rc.slayerCats); } },
      { header: 'Also in',     cell: function(rc) { return listOrDash(rc.matched); } }
    ]
  );

  if (html === '') {
    html = '<p style="font-size:12px;color:#888;margin:8px 0">' +
           'No mons in your collection qualify for any tier or slayer category.</p>';
  }
  el.innerHTML = html;
}

// Show/hide toggle handler for the collapsible matches-list sections.
// Uses inline display style on rows (skipping the first 5, which
// always stay visible). Global so the button's onclick handler can
// reach it from the renderMatchesList output.
function toggleMatchesSection(sid, btn) {
  var rows = document.querySelectorAll('tr[data-section="' + sid + '"]');
  if (rows.length === 0) return;
  var isExpanding = btn.textContent.indexOf('Show') === 0;
  for (var i = 5; i < rows.length; i++) {
    rows[i].style.display = isExpanding ? '' : 'none';
  }
  var count = btn.getAttribute('data-hidden-count');
  btn.textContent = isExpanding ? ('Hide ' + count + ' \u2191') : ('Show ' + count + ' more \u2193');
}

// Minimal HTML escape for values that go into innerHTML (species names,
// tier names). Prevents a stray '<' in a custom TOML tier name from
// breaking the match list layout.
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function clearCollection() {
  state.userRecords = null;
  state.ownedByIv = null;
  state.showOnlyMine = false;
  var chk = document.getElementById('collection-only-chk');
  if (chk) chk.checked = false;
  var ta = document.getElementById('collection-csv');
  if (ta) ta.value = '';
  setCollectionStatus('', '#aaa');
  updateTierCardCounts({});
  renderMatchesList();
  annotateAnchorBullets();
  updateView();
}

function setCollectionStatus(text, color) {
  var el = document.getElementById('collection-status');
  if (!el) return;
  el.textContent = text;
  el.style.color = color || '#aaa';
}

// Fill in "N of yours qualify" annotations on tier cards. Tier cards
// emit empty spans with ids `tier-card-yours-<slug>` where slug is
// the tier name lowercased with non-alphanumerics replaced with '-'.
// If a card's span is missing (older template or filtered out), this
// is a silent no-op.
function updateTierCardCounts(tierCounts) {
  // Read from live DATA.tiers (post-analysis) rather than the stale
  // pre-analysis DATA.collection.tierNames snapshot — same reason as
  // the fix in loadCollection/renderMatchesList.
  var liveTiers = DATA.tiers || [];
  for (var i = 0; i < liveTiers.length; i++) {
    var t = liveTiers[i];
    if (!t || !t.name) continue;
    var n = t.name;
    var slug = n.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    var el = document.getElementById('tier-card-yours-' + slug);
    if (!el) continue;
    var c = tierCounts[n];
    if (c == null || !state.userRecords) {
      el.textContent = '';
      el.style.display = 'none';
    } else {
      el.textContent = c + ' of yours qualify';
      el.style.display = '';
    }
  }
}

// Wire up DOM event handlers once, on init. Guarded against being
// called twice in dev reload scenarios.
var _collectionHandlersWired = false;
function wireCollectionHandlers() {
  if (_collectionHandlersWired) return;
  if (!DATA.collection) return;
  var panel = document.getElementById('collection-panel');
  if (!panel) return;
  _collectionHandlersWired = true;

  document.getElementById('collection-load-btn').addEventListener('click', function() {
    var ta = document.getElementById('collection-csv');
    loadCollection(ta.value);
  });
  document.getElementById('collection-clear-btn').addEventListener('click', clearCollection);
  document.getElementById('collection-file-btn').addEventListener('click', function() {
    document.getElementById('collection-file-input').click();
  });
  document.getElementById('collection-file-input').addEventListener('change', function(ev) {
    var file = ev.target.files && ev.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function(e) {
      var text = e.target.result;
      document.getElementById('collection-csv').value = text;
      loadCollection(text);
    };
    reader.readAsText(file);
  });
  document.getElementById('collection-only-chk').addEventListener('change', function(ev) {
    state.showOnlyMine = ev.target.checked;
    updateView();
  });
}

// ---- Build Plotly traces ----
function buildTraces() {
  computeView();
  var cm = state.colorMode || 'threshold';
  var hasTiers = tierNames.length > 0;
  var traces = [];

  // --- User collection state captured for this frame ---
  // `ownedIdxSet` maps canonicalIvIdx → the record so the user overlay
  // can look up hover info. `isOwned` is the filter predicate used by
  // every trace loop when "Show only my mons" is active.
  var ownedIdxSet = {};
  if (state.userRecords) {
    for (var _ur = 0; _ur < state.userRecords.length; _ur++) {
      var _rec = state.userRecords[_ur];
      if (_rec.canonicalIvIdx >= 0) ownedIdxSet[_rec.canonicalIvIdx] = _rec;
    }
  }
  function isOwnedFilter(iv) {
    return !state.showOnlyMine || (ownedIdxSet[iv] != null);
  }

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
      if (!isOwnedFilter(iv)) continue;
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
        marker:{size:2, color:otherColor, colorscale:'Viridis', opacity:0.4},
        hoverlabel:{bordercolor:'#888'}
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
        if (!isOwnedFilter(iv)) continue;
        if (DATA.ivAllTiers[iv] && DATA.ivAllTiers[iv].indexOf(ti) >= 0) {
          tx.push(DATA.spRanks[iv]);
          ty.push(yValues[iv]);
          tt.push(buildHoverText(iv));
        }
      }
      if (tx.length) {
        _tierTraces.push({
          name:tierNames[ti],
          x:tx, y:ty, text:tt,
          mode:'markers', type:'scattergl', hoverinfo:'text',
          marker:{size:7, color:tierColors[ti], opacity:0.9,
                   line:{width:1, color:'#000'}},
          hoverlabel:{bordercolor:tierColors[ti]}
        });
      }
    }
  } else {
    // --- Stat or score coloring (single trace) ---
    var ax=[], ay=[], at=[], ac=[];
    var cLabel = 'Avg Score';
    for (var iv=0; iv<nIvs; iv++) {
      if (currentYIsSparse && !isFinite(yValues[iv])) continue;
      if (!isOwnedFilter(iv)) continue;
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
               reversescale: (cm === 'atk')},
      hoverlabel:{bordercolor:'#888'}
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
  var recSet = {};
  if (DATA.recIvs) {
    for (var rsi = 0; rsi < DATA.recIvs.length; rsi++) {
      recSet[DATA.recIvs[rsi]] = true;
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
    var inRec = !!recSet[iv];
    // 'star' replaces 'hexagram' because hexagram isn't supported in
    // scattergl and we need this trace to be gl to match tier +
    // Other + user-overlay traces — mixing svg and gl trace types
    // breaks hover hit detection on overlapping points.
    if (inRec) return 'diamond';
    if (inSlayer && inAnchor) return 'star';
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
      // "Show only my mons" filter: slayer/anchor overlay traces
      // must obey the same filter as the base Other/tier traces.
      // Without this, the wins-vs-rank1 y-axis mode (where most
      // visible points are slayer/anchor rather than Other) makes
      // the filter look broken — it was filtering the base trace
      // correctly, just not the overlays.
      if (!isOwnedFilter(iv)) continue;
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
      // scattergl (not svg scatter) so hover hit detection stays
      // consistent when slayer/anchor points overlap tier + user
      // overlay traces. Mixing svg + gl breaks hover on multi-trace
      // overlaps — see commit 0305924 for the user overlay version
      // of this same fix.
      mode: 'markers', type: 'scattergl', hoverinfo: 'text',
      marker: {
        size: 6,
        color: ocol,
        symbol: osym,
        opacity: 0.85,
        line: { width: 1, color: borderColor }
      },
      hoverlabel: { bordercolor: borderColor }
    };
  }

  var slayerTrace = buildOverlayTrace('Slayer IVs', DATA.slayerIvs, '#FFD700');
  if (slayerTrace) traces.push(slayerTrace);
  var anchorTrace = buildOverlayTrace('Anchor IVs', DATA.anchorClearIvs, '#00ffff');
  if (anchorTrace) traces.push(anchorTrace);
  var recTrace = buildOverlayTrace('Top Picks', DATA.recIvs, '#e94560');
  if (recTrace) traces.push(recTrace);

  // Tier traces go next so they render on top of slayer/anchor overlays.
  // Sort largest first so smallest tiers (most selective) draw on top.
  if (typeof _tierTraces !== 'undefined') {
    _tierTraces.sort(function(a, b) { return b.x.length - a.x.length; });
    for (var _ti = 0; _ti < _tierTraces.length; _ti++) {
      traces.push(_tierTraces[_ti]);
    }
  }

  // ---- User collection overlay (z-order: TOP, above tier traces) ----
  //
  // Two traces: one for mons that qualify for ≥1 tier ("Your IVs
  // (qualifying)") drawn prominently, and one for owned-but-non-
  // qualifying mons ("Your IVs (owned)") drawn faintly so the user
  // can see what they already own vs what they're missing. Off-grid
  // mons (canonicalIvIdx === -1) are not plotted — their IV wasn't
  // in the dive's simulated set, so there's no (x, y) to place them
  // at. The status line reports the off-grid count separately.
  //
  // These MUST render after tier traces — solid tier-color circles
  // at size 7 opacity 0.9 would otherwise completely cover the
  // transparent-fill user rings. Appending last puts them on top
  // regardless of tier density.
  //
  // Border color is bright white (qualifying) and light gray (owned)
  // rather than magenta — magenta rings on magenta/red tier colors
  // disappeared in testing; white reads cleanly against every
  // existing tier color and against the Viridis background.
  if (state.userRecords && state.userRecords.length > 0) {
    var qualX=[], qualY=[], qualText=[];
    var ownX=[],  ownY=[],  ownText=[];
    // Tiny y-offset so user-overlay points aren't at the EXACT same
    // (x, y) as the underlying tier / slayer / anchor markers. When
    // 5 traces overlap at a single coordinate (tier 0 + tier 1 +
    // slayer + anchor + user overlay) Plotly scattergl's hover
    // hit-detection gives up and shows nothing on hover. Nudging
    // the user ring by ~0.02 y-units (under 0.5 pixel at typical
    // plot heights) gives each user ring a distinct closest point
    // for hit detection without any visible offset. See the
    // iv=3648 debugging session for the full story.
    var yRange = 1;
    if (yValues.length >= 2) {
      var _yMin = Infinity, _yMax = -Infinity;
      for (var _yi = 0; _yi < yValues.length; _yi++) {
        var _yv = yValues[_yi];
        if (isFinite(_yv)) {
          if (_yv < _yMin) _yMin = _yv;
          if (_yv > _yMax) _yMax = _yv;
        }
      }
      yRange = Math.max(1, _yMax - _yMin);
    }
    var Y_NUDGE = yRange * 0.0005;

    // Iterate unique owned IV indices (not userRecords) so we hit each
    // scatter point once. The ownedByIv cache groups records by IV,
    // so anyQualified is "does any record in this IV's group have a
    // non-empty matched list OR slayer category" — tier hits and
    // slayer membership both earn the white-circle treatment.
    var ownedByIv = state.ownedByIv || {};
    for (var ivKey in ownedByIv) {
      if (!ownedByIv.hasOwnProperty(ivKey)) continue;
      var iv = parseInt(ivKey, 10);
      if (iv < 0 || iv >= nIvs) continue;
      var sp = DATA.spRanks[iv], yv = yValues[iv];
      if (currentYIsSparse && !isFinite(yv)) continue;
      var fullText = buildHoverText(iv);
      var recsAtIv = ownedByIv[ivKey];
      var anyQualified = !!recSet[iv];
      if (!anyQualified) {
        for (var urD = 0; urD < recsAtIv.length; urD++) {
          if ((recsAtIv[urD].matched && recsAtIv[urD].matched.length > 0)
              || (recsAtIv[urD].slayerCats && recsAtIv[urD].slayerCats.length > 0)) {
            anyQualified = true; break;
          }
        }
      }
      // Apply the nudge upward (positive y direction) so the user
      // ring sits just above the base marker. "Above" is chosen so
      // the matchup-diff block (which renders under the cursor by
      // default in Plotly) has more space below the hovered point.
      var nudgedY = yv + Y_NUDGE;
      if (anyQualified) {
        qualX.push(sp); qualY.push(nudgedY); qualText.push(fullText);
      } else {
        ownX.push(sp); ownY.push(nudgedY); ownText.push(fullText);
      }
    }
    // Hover strategy: user-overlay traces carry their own
    // hoverinfo:'text' with the exact same text buildHoverText
    // produces for the underlying base trace at each IV. Whichever
    // of (user overlay, tier, slayer, Other) Plotly's "closest"
    // picks, the tooltip is correct — the "★ Yours:" block is in
    // every trace's text via buildHoverText.
    //
    // Earlier attempt used hoverinfo:'skip' to make user overlays
    // "invisible to hover," thinking Plotly would fall through to
    // the next-closest trace. It doesn't — when closest lands on a
    // skip trace, Plotly just shows NO tooltip instead of cascading.
    // That silently broke hover on any user point where the ring
    // was marginally closer to the cursor than the underlying
    // marker. The legend-overlap bug (commit 43d9341) that was the
    // original motivation for 'skip' is fixed, so 'text' is safe.
    if (ownX.length > 0) {
      traces.push({
        name: 'Yours - other', x: ownX, y: ownY, text: ownText,
        mode: 'markers', type: 'scattergl', hoverinfo: 'text',
        marker: {
          size: 9, color: '#cccccc', symbol: 'circle-open',
          opacity: 0.9, line: { width: 1.5, color: '#cccccc' }
        },
        hoverlabel: { bordercolor: '#cccccc' }
      });
    }
    if (qualX.length > 0) {
      traces.push({
        name: 'Yours - notable', x: qualX, y: qualY, text: qualText,
        mode: 'markers', type: 'scattergl', hoverinfo: 'text',
        marker: {
          size: 13, color: '#ffffff', symbol: 'circle-open',
          opacity: 1.0, line: { width: 2, color: '#ffffff' }
        },
        hoverlabel: { bordercolor: '#ffffff' }
      });
    }
    // Dev log: one line per render so if the overlay stays invisible
    // the browser console explains why.
    if (typeof console !== 'undefined' && console.log) {
      console.log('[collection] render:',
                  'records=' + state.userRecords.length,
                  'qual=' + qualX.length,
                  'owned=' + ownX.length);
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
    h += '<td>'+(isFinite(yValues[iv]) ? yValues[iv].toFixed(1) : '-')+'</td>';
    if (hasTiers) {
      if (tier >= 0) {
        h += '<td><span class="tier-badge" style="background:'+tierColors[tier]+';color:#000">'+tierNames[tier]+'</span></td>';
      } else h += '<td>-</td>';
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
  var bsel = document.getElementById('bait-sel');
  if (osel || bsel) {
    var base = osel ? osel.value : (DATA.oppIvModes[0] || 'pvpoke').split(':')[0];
    var bait = bsel ? bsel.value : 'bait';
    state.oppIvMode = (bait === 'nobait') ? (base + ':nobait') : base;
  }
  var csel = document.getElementById('color-sel');
  if (csel) state.colorMode = csel.value;
  var ysel = document.getElementById('yaxis-sel');
  if (ysel) state.yAxisMode = ysel.value;
  lockedIdx = -1;

  // Swap per-moveset narrative zones
  var narDivs = document.querySelectorAll('.dd-narrative-moveset');
  for (var i = 0; i < narDivs.length; i++) {
    narDivs[i].style.display = (parseInt(narDivs[i].getAttribute('data-moveset')) === state.movesetIdx) ? 'block' : 'none';
  }

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
    // fixedrange:false enables Plotly's native drag-to-zoom and
    // double-click-to-reset on both axes. Useful for drilling into
    // dense clusters without click-to-pin from the matches list.
    xaxis: {title:'Stat Product Rank (1=best)', range:[xMax+xPad, xMin-xPad]},
    yaxis: {title:currentYLabel, range:[yMin-yPad, yMax+yPad]},
    paper_bgcolor:'#1a1a2e', plot_bgcolor:'#16213e',
    font:{color:'#e0e0e0'}, hovermode:'closest',
    // Legend pinned explicitly OUTSIDE the plot area so it never
    // covers top-right hover tooltips (the rank-1 points on the
    // inverted x-axis are in the corner that Plotly's default
    // top-right legend position sits on, and tooltips there were
    // rendering under the legend box).
    legend: {
      bgcolor:'rgba(22,33,62,0.8)', bordercolor:'#0f3460', borderwidth:1,
      x: 1.02, xanchor: 'left', y: 1, yanchor: 'top',
    },
    // Explicit hoverlabel so tooltip sizing and font are deterministic
    // — namelength:-1 disables trace-name truncation so we see the
    // full "★ Yours:" block. Background and font are uniform across
    // traces, but the BORDER color is set per-trace (via
    // trace.hoverlabel.bordercolor) so each trace's tooltip picks up
    // a color matching its marker — tier color for tier traces,
    // gold for slayer, cyan for anchor, gray for Other, white for
    // user overlay. The layout-level bordercolor here is just a
    // fallback for traces that forget to set one.
    hoverlabel: {
      bgcolor: '#2a2a4a', bordercolor: '#888',
      font: { size: 11, color: '#e0e0e0', family: 'monospace' },
      namelength: -1, align: 'left',
    },
    margin: { r: 180 },  // reserve room for the outside legend
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
// Expose updateView globally so inline onchange="updateView()" handlers
// work even when the engine runs inside an async IIFE (for gzip score
// decompression).
window.updateView = updateView;
updateView();
// Hook up the collection panel handlers now that updateView has run
// once (nIvs, DATA, etc. are all in scope). Safe even if DATA.collection
// is null — the wire function bails early in that case.
wireCollectionHandlers();