
// ---- State ----
var state = {
  movesetIdx: 0,
  scenarioMode: __SCENARIO_MODE_DEFAULT__,
  oppIvMode: '__OPP_IV_MODE_DEFAULT__',
  colorMode: 'threshold',
  yAxisMode: 'avgScore',
  // Best-buddy / level cap currently displayed: '50' (league default) or
  // '51' (best-buddy). Only ever '51' when DATA.ivL51 is present (the dive
  // carried a second L51 grid). Drives the score-key suffix in getScoreKey.
  levelMode: '50',
  // "Compare candidates" widget: up to 7 user-entered focal IV spreads
  // ({a,d,s,level}), compared side by side from the embedded grid.
  compareCandidates: [],
  // Anchor IVs overlay rendering mode:
  //   'filled'  - cyan fill, opacity 0.65 (current default; context
  //               layer that doesn't overwhelm slayer / top-picks)
  //   'outline' - transparent fill with a cyan border ring; the band
  //               stays visible as an envelope rather than a blob, so
  //               named-category traces riding the top/bottom edge
  //               (e.g. Annihilape Bulk in a Tinkaton dive) read
  //               clearly against it. Opt-in toggle, not default.
  anchorDisplayMode: 'filled',
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
  // Parsed mons from the last CSV load (empty array until Load is clicked).
  csvMons: [],
  // Mons the user entered one-at-a-time via the manual-entry form. These
  // are additive with csvMons: every reprocess combines the two lists.
  manualMons: [],
  // Ad-hoc "pin these IVs on the scatter" feature. Populated by
  // applyHighlight() from the highlight-input text field. Unlike
  // userRecords (persistent collection), this is a throwaway query set.
  // When non-empty, matching IVs render as red diamonds on top and
  // other traces dim to ~30% opacity.
  highlightIvs: [],
};
var yValues, yRanks, refYValues, refYRanks;
// Cached top-N same-species atk cohort for Top-Mirror CMP %. Invalidated
// by computeView() whenever yRanks / yValues change (moveset, scenario,
// or opp-IV dropdown). Null until first use.
var _topMirrorCohortAtks = null;
// Updated by computeView() based on the active y-axis mode. Read by
// hover text, layout title, and the summary table column header so a
// single source of truth controls how the y-axis labels itself.
var currentYLabel = 'Avg Battle Score';
var currentYMax = null;  // for "X / N" formatting on wins-based modes
var currentYIsSparse = false;  // true for winsMirror; false otherwise
var lockedIdx = -1;
var tierColors = __TIER_COLORS_JS__;
// Theme-aware 'var(--tier-N)' strings parallel to tierColors (same index,
// same order). The summary-table badge reads tierVars[tier] so it re-themes
// with CSS and matches the Plotly marker (tierColors[tier]) and the tier card
// for every tier including mirror -- no index reconstruction, no off-by-one.
var tierVars = __TIER_VARS_JS__;
var tierNames = __TIER_NAMES_JS__;
var nIvs = DATA.nIvs, nS = DATA.nScenarios, nO = DATA.nOpponents;

// Column-header tooltip strings for the three mirror-adjacent metrics.
// Declared once so the Top IVs table (_summaryColumns) and the Slayer IVs
// "of yours" table (renderSection extras) share a single source of truth.
// Each string appears once in the emitted HTML per table that uses it --
// the title attribute still inlines the text, but the JS source does not
// carry duplicate literals that would drift as copy evolves.
var HELP_MIRROR_SLAYER_CMP = '% of the Nash-converged slayer cohort whose attack you at least tie. Niche; often collapses to all-0 or all-100.';
var HELP_TOP_MIRROR_CMP = '% of the top-50 same-species IVs in this dive whose attack you at least tie. Ladder-realistic mirror cohort.';
var HELP_MATCHUPS_KEPT = 'Expected non-mirror matchups won, sampling scenarios uniformly: per opponent, (scenarios won / nSel) summed over opponents. Integer when a single scenario is selected; fractional when averaging. Denominator excludes the mirror entry.';
var HELP_PER_SHIELD_DELTA = 'Signed avg-score delta vs the best IV in this scenario: +ve beats the best IV here, 0 is the best IV, -ve trades score for something else (atk / HP / bulk). Frozen on the Shields axis so all three show regardless of dropdown; reacts to Opp-IVs + Bait.';

// ---- Helpers ----
// Score key is level-aware: in best-buddy (L51) view it reads the parallel
// '{mi}_{mode}@51' grid the dive embedded. The '@51' suffix is only added
// when an L51 grid is actually present (DATA.ivL51), so non-best-buddy dives
// are unaffected.
function getScoreKey(mi, mode) {
  return mi + '_' + mode + ((state.levelMode === '51' && DATA.ivL51) ? '@51' : '');
}
function getScores(mi, mode) { return SCORES[getScoreKey(mi, mode)]; }

// ---- Best-buddy / Level-51 toggle ----
// When DATA.ivL51 is present the dive carries a second (best-buddy L51) grid.
// Toggling REBINDS the per-IV metadata arrays on DATA (so every existing
// DATA.ivLv[iv]-style read stays correct) and flips the score-key suffix; the
// prose + card are swapped from their inert <template>s (only one level's
// element ids are ever live, so there is no id collision). One Plotly
// instance, fully recomputed on toggle.
var _BB_LEVEL_FIELDS = ['ivLv', 'ivCp', 'ivAtk', 'ivDef', 'ivHp', 'ivSp',
                        'spRanks', 'ivEfficient', 'ivTiers', 'ivAllTiers',
                        'rank1RefIvIdx'];
var _bbL50 = null;        // stashed league-default (L50) arrays
var _bbHostHTML = {};     // hostId -> { '50': html, '51': html }

function _bbInitHost(hostId, tmplId) {
  var host = document.getElementById(hostId);
  var tmpl = document.getElementById(tmplId);
  if (!host || !tmpl) return;
  _bbHostHTML[hostId] = { '50': host.innerHTML, '51': tmpl.innerHTML };
}

function _initBestBuddy() {
  if (!DATA.ivL51) return;
  _bbL50 = {};
  for (var i = 0; i < _BB_LEVEL_FIELDS.length; i++) {
    _bbL50[_BB_LEVEL_FIELDS[i]] = DATA[_BB_LEVEL_FIELDS[i]];
  }
  _bbInitHost('dd-bb-prose-host', 'dd-bb-prose-tmpl');
  _bbInitHost('dd-bb-card-host', 'dd-bb-card-tmpl');
  var dd = String((DATA.bestBuddy && DATA.bestBuddy.defaultDisplay) || 50);
  if (dd === '51') {
    var chk = document.getElementById('dd-bb-toggle');
    if (chk) chk.checked = true;
    setBestBuddyLevel('51');
  }
}

function setBestBuddyLevel(mode) {
  if (!DATA.ivL51 || !_bbL50) return;
  var src = (mode === '51') ? DATA.ivL51 : _bbL50;
  for (var i = 0; i < _BB_LEVEL_FIELDS.length; i++) {
    var f = _BB_LEVEL_FIELDS[i];
    if (src[f] !== undefined) DATA[f] = src[f];
  }
  state.levelMode = mode;
  for (var hid in _bbHostHTML) {
    var host = document.getElementById(hid);
    if (host && _bbHostHTML[hid][mode] != null) host.innerHTML = _bbHostHTML[hid][mode];
  }
  // If a collection is loaded, re-run it so each owned mon's stats / level /
  // CP / power-up recompute at the toggled cap (loadCollection ends with its
  // own updateView, so the scatter refreshes too). Otherwise refresh directly.
  var _hasColl = (state.csvMons && state.csvMons.length) ||
                 (state.manualMons && state.manualMons.length);
  if (_hasColl) {
    loadCollection(null);
  } else {
    updateView();
  }
  updateSummaryTable();
  // Compare widget reads the level-aware grid; recompute it on toggle too.
  if (typeof cmpRender === 'function' && state.compareCandidates.length) cmpRender();
}
window.setBestBuddyLevel = setBestBuddyLevel;

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

// ---- Opponent filter (client-side subset) ----
//
// state.selectedOpps is a Uint8Array(nO) of 1/0 (1 = shown), or null before
// init (treated as "all shown"). state.oppMaskVersion bumps on every change so
// per-render caches keyed on it recompute. The filter masks the AGGREGATE
// views that sum over opponents -- scatter y-values, the Top-IVs table,
// histograms, Matchups Kept, the hover matchup-diff lists, the per-shield
// deltas, and the paste-box "Gives up vs #1" list -- but NOT the Python-baked
// sections (infographic card, threshold tiers, Top Picks, narrative), which
// are computed full-pool at bake time. The honesty banner names that split.
// The "Comparing builds" widget (cmpSummary / cmpBestAvg / cmpFlipPanel /
// cmpMarginPanel) ALSO follows the filter -- its wins/avg/gives-up and the
// flip+margin panels recompute over the selected subset (Michael's call
// 2026-07-03), so every score surface on the page moves together.
function _oppSelCount() {
  var sel = state.selectedOpps;
  if (!sel) return nO;
  var c = 0; for (var i = 0; i < nO; i++) if (sel[i]) c++;
  return c;
}
// A partial selection is "active". Zero-checked is treated as all (avoids
// divide-by-zero) and therefore reads as inactive.
function oppFilterActive() {
  if (!state.selectedOpps) return false;
  var c = _oppSelCount();
  return c > 0 && c < nO;
}
// Lookup {oi:true} of shown opponents, or null when inactive (== all shown).
// Callers do `if (selSet && !selSet[oi]) continue;` so null means no filtering.
function selectedOppSet() {
  if (!oppFilterActive()) return null;
  var sel = state.selectedOpps, s = {};
  for (var i = 0; i < nO; i++) if (sel[i]) s[i] = true;
  return s;
}
// Cache-key fragment; changes whenever the selection changes.
function oppMaskSig() {
  return oppFilterActive() ? ('m' + (state.oppMaskVersion || 0)) : 'all';
}

// ---- Opponent filter: panel init + button handlers ----
// Display order: meta rank ascending (1 = best); unranked (null rank) sorted
// to the very end by display name. Built once from DATA on init.
function _oppFilterOrder() {
  var order = [];
  for (var i = 0; i < nO; i++) order.push(i);
  var ranks = DATA.oppMetaRank || [];
  var disp = DATA.opponentsDisplay || DATA.opponents;
  order.sort(function(a, b) {
    var ra = ranks[a], rb = ranks[b];
    var na = (ra == null), nb = (rb == null);
    if (na !== nb) return na ? 1 : -1;        // unranked -> end
    if (!na && ra !== rb) return ra - rb;      // by rank ascending
    var da = disp[a], db = disp[b];
    return da < db ? -1 : (da > db ? 1 : 0);   // then by display name
  });
  return order;
}
// Populate the checkbox list and seed state.selectedOpps (all checked). Called
// once at boot before the first updateView(). No-op if the panel isn't present.
function initOppFilter() {
  var list = document.getElementById('opp-filter-list');
  if (!list) return;
  state.selectedOpps = new Uint8Array(nO);
  for (var i = 0; i < nO; i++) state.selectedOpps[i] = 1;
  state.oppMaskVersion = 0;
  var ranks = DATA.oppMetaRank || [];
  var disp = DATA.opponentsDisplay || DATA.opponents;
  var order = _oppFilterOrder();
  var html = '';
  for (var k = 0; k < order.length; k++) {
    var oi = order[k];
    var r = ranks[oi];
    var badge = (r == null) ? '--' : ('#' + r);
    html += '<label style="font-size:12px;display:flex;gap:6px;align-items:center;'
          + 'white-space:nowrap;overflow:hidden">'
          + '<input type="checkbox" checked data-oi="' + oi + '" onchange="oppFilterCheckboxChanged()">'
          + '<span style="color:var(--text-muted);min-width:2.6em;text-align:right">' + badge + '</span>'
          + '<span style="overflow:hidden;text-overflow:ellipsis">' + disp[oi] + '</span>'
          + '</label>';
  }
  list.innerHTML = html;
  updateOppFilterBanner();
}
function _syncSelectedFromCheckboxes() {
  var boxes = document.querySelectorAll('#opp-filter-list input[type=checkbox]');
  for (var i = 0; i < boxes.length; i++) {
    var oi = parseInt(boxes[i].getAttribute('data-oi'), 10);
    state.selectedOpps[oi] = boxes[i].checked ? 1 : 0;
  }
  state.oppMaskVersion = (state.oppMaskVersion || 0) + 1;
}
function oppFilterCheckboxChanged() {
  _syncSelectedFromCheckboxes();
  updateOppFilterBanner();
  updateView();
  // The Comparing-builds widget reads the same grids -> refresh it on filter
  // change (updateView doesn't, mirroring setBestBuddyLevel's explicit call).
  if (typeof cmpRender === 'function' && state.compareCandidates.length) cmpRender();
}
function _setAllCheckboxes(pred) {
  var boxes = document.querySelectorAll('#opp-filter-list input[type=checkbox]');
  for (var i = 0; i < boxes.length; i++) {
    var oi = parseInt(boxes[i].getAttribute('data-oi'), 10);
    boxes[i].checked = pred(oi);
  }
  _syncSelectedFromCheckboxes();
  updateOppFilterBanner();
  updateView();
  if (typeof cmpRender === 'function' && state.compareCandidates.length) cmpRender();
}
function oppFilterAll() { _setAllCheckboxes(function() { return true; }); }
function oppFilterNone() { _setAllCheckboxes(function() { return false; }); }
// Top-N: check only opponents with a non-null meta rank <= n. Unranked never
// join a top-N cut (they have no rank), matching the "unranked -> end" intent.
function oppFilterTopN(n) {
  var ranks = DATA.oppMetaRank || [];
  _setAllCheckboxes(function(oi) { var r = ranks[oi]; return r != null && r <= n; });
}
window.oppFilterAll = oppFilterAll;
window.oppFilterNone = oppFilterNone;
window.oppFilterTopN = oppFilterTopN;
window.oppFilterCheckboxChanged = oppFilterCheckboxChanged;

// Banner + summary text. Banner shows ONLY on a genuine partial selection; it
// names exactly which surfaces honor the filter and which stay full-pool, so a
// filtered screenshot can't be mistaken for a full-meta result.
function updateOppFilterBanner() {
  var sel = _oppSelCount();
  var sumEl = document.getElementById('opp-filter-summary');
  if (sumEl) {
    sumEl.textContent = oppFilterActive() ? ('(' + sel + ' of ' + nO + ' shown)')
      : (sel === 0 ? '(none checked -- showing all)' : '(all shown)');
  }
  var banner = document.getElementById('opp-filter-banner');
  if (!banner) return;
  if (oppFilterActive()) {
    var snap = DATA.rankSnapshot ? (' Meta ranks as of ' + DATA.rankSnapshot + '.') : '';
    banner.style.display = 'block';
    banner.innerHTML = '<b>Filtered view.</b> The scatter, Top IVs table, histograms, and the '
      + 'Comparing-builds widget reflect the <b>' + sel + ' of ' + nO + '</b> opponents you have '
      + 'checked. The infographic card, threshold tiers, Top Picks, and narrative are computed '
      + 'against the full ' + nO + '-opponent pool and do <b>not</b> react to this filter.' + snap;
  } else {
    banner.style.display = 'none';
    banner.innerHTML = '';
  }
}
window.updateOppFilterBanner = updateOppFilterBanner;

// ---- Compute view ----
//
// computeYValues dispatches on state.yAxisMode to produce the y-axis
// values for every IV. Modes:
//
//   'avgScore'   mean PvPoke score across selected scenarios + opponents
//                (the original behavior)
//   'winsPvpoke' count of (opp, scenario) pairs the IV wins (score > 500;
//                500 = tie, excluded -- matches PvPoke)
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

  var selSet = selectedOppSet();  // null == all opponents (no filter)

  if (mode === 'winsPvpoke' || mode === 'winsRank1') {
    var winCounts = new Float64Array(nIvs);
    for (var ivW = 0; ivW < nIvs; ivW++) {
      var c = 0;
      for (var kW = 0; kW < nSel; kW++) {
        var siW = sis[kW];
        var baseW = ivW * nS * nO + siW * nO;
        for (var oiW = 0; oiW < nO; oiW++) {
          if (selSet && !selSet[oiW]) continue;  // opponent filtered out
          if (scores[baseW + oiW] > 500) c++;  // >500=win; 500=tie (PvPoke)
        }
      }
      winCounts[ivW] = c;
    }
    return winCounts;
  }

  // 'avgScore' (default). Denominator is (selected scenarios) x (selected
  // opponents), so the mean stays a mean over exactly the shown subset.
  var oppDen = selSet ? _oppSelCount() : nO;
  var avgs = new Float64Array(nIvs);
  for (var iv2 = 0; iv2 < nIvs; iv2++) {
    var sum = 0;
    for (var k2 = 0; k2 < nSel; k2++) {
      var si2 = sis[k2];
      var base2 = iv2 * nS * nO + si2 * nO;
      for (var oi2 = 0; oi2 < nO; oi2++) {
        if (selSet && !selSet[oi2]) continue;  // opponent filtered out
        sum += scores[base2 + oi2];
      }
    }
    avgs[iv2] = sum / (nSel * oppDen);
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
  if (!yValues) {
    // The opp-IV and bait dropdowns are emitted independently, so a
    // dive built with a partial mode matrix lets the user select a
    // combination with no SCORES entry — this used to TypeError deep
    // in computeRanks and freeze the page mid-state (2026-06-11
    // review, W3). Fall back to the first mode that exists for this
    // moveset and resync the dropdowns to what is actually shown.
    var _prefix = state.movesetIdx + '_';
    var _fallback = null;
    for (var _sk in SCORES) {
      if (_sk.indexOf(_prefix) === 0 && SCORES[_sk]) {
        _fallback = _sk.substring(_prefix.length);
        break;
      }
    }
    if (_fallback) {
      state.oppIvMode = _fallback;
      var _osel = document.getElementById('oppiv-sel');
      if (_osel) _osel.value = _fallback.split(':')[0];
      var _bsel = document.getElementById('bait-sel');
      if (_bsel) _bsel.value = (_fallback.indexOf(':nobait') >= 0) ? 'nobait' : 'bait';
      var _esel = document.getElementById('energy-sel');
      if (_esel) {
        var _em = _fallback.match(/:e(\d+)/);
        _esel.value = _em ? _em[1] : '0';
      }
      yValues = computeYValues(state.movesetIdx);
    }
    if (!yValues) {
      // Last resort (e.g. a wins-mode whose source scores are absent):
      // render a flat plot instead of dying.
      console.warn('No score array for moveset ' + state.movesetIdx +
                   ' in any mode; rendering zeros');
      yValues = new Float64Array(nIvs);
    }
  }
  yRanks = computeRanks(yValues);
  // Top-Mirror cohort depends on the just-refreshed yRanks; invalidate
  // the cache so the next Top-Mirror CMP % read rebuilds it lazily.
  _topMirrorCohortAtks = null;
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
  // XL-candy-decision helpers. Per-shield Δ columns are frozen on
  // the Shields axis so hover always shows the full lead/mid/closer
  // split regardless of dropdown state. Mirror CMP % is
  // dropdown-independent (atk-based) and cohort-gated.
  var _d0 = _computePerShieldScoreDelta(iv, 0);
  var _d1 = _computePerShieldScoreDelta(iv, 1);
  var _d2 = _computePerShieldScoreDelta(iv, 2);
  function _fmtD(d) { return (d > 0 ? '+' : '') + d.toFixed(1); }
  var _parts = [];
  if (isFinite(_d0)) _parts.push('0v0 ' + _fmtD(_d0));
  if (isFinite(_d1)) _parts.push('1v1 ' + _fmtD(_d1));
  if (isFinite(_d2)) _parts.push('2v2 ' + _fmtD(_d2));
  if (_parts.length > 0) lines.push('Δ vs best: ' + _parts.join(' | '));
  var cmp = _computeMirrorCmpPct(iv);
  if (isFinite(cmp)) {
    lines.push('Mirror CMP: beats ' + cmp.toFixed(0) + '% of cohort');
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
      if (owned.length === 1) {
        // Single mon: full detail (CP/level path, shadow/lucky flags,
        // qualifying tiers). Informative for the common case.
        lines.push('<b>\u2605 Yours:</b>');
        var rcL = owned[0];
        var mc = (rcL.stats && rcL.stats.cp != null) ? rcL.stats.cp : '?';
        var ml = (rcL.stats && rcL.stats.level != null) ? rcL.stats.level : '?';
        lines.push('  <b>CP ' + rcL.mon.cp + '</b> @ L' + rcL.mon.level +
                   ' \u2192 CP ' + mc + ' @ L' + ml);
        if (rcL.csvSpecies && rcL.csvSpecies !== DATA.species) {
          lines.push('    (' + (rcL.mon.is_shadow ? 'Shadow ' : '') +
                     rcL.csvSpecies + (rcL.mon.lucky ? ' \u2728' : '') + ')');
        } else if (rcL.mon.is_shadow) {
          lines.push('    (Shadow' + (rcL.mon.lucky ? ' \u2728' : '') + ')');
        } else if (rcL.mon.lucky) {
          lines.push('    \u2728');
        }
        if (rcL.matched && rcL.matched.length > 0) {
          lines.push('    Qualifies: ' + rcL.matched.join(', '));
        }
      } else {
        // Multi-mon: collapse to a single CP-list line. Per-mon CP/
        // level/qualifying detail is already in the "of yours" tables
        // below the scatter, so duplicating it in hover just bloats
        // the tooltip until it vertical-clips against the plot edge.
        // One line, CPs descending, primary in-game search handle.
        var cps = owned.map(function(rc) { return 'CP ' + rc.mon.cp; });
        lines.push('<b>\u2605 Yours (' + owned.length + '):</b> ' + cps.join(', '));
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
  var selSetMD = selectedOppSet();  // null == all opponents; honor the filter
  for (var k=0; k<sis.length; k++) {
    var si = sis[k];
    var gained = [], lost = [];
    for (var oi=0; oi<nO; oi++) {
      if (selSetMD && !selSetMD[oi]) continue;  // opponent filtered out
      var sc1 = s1[iv1*nS*nO + si*nO + oi];
      var sc2 = s2[iv2*nS*nO + si*nO + oi];
      var w1 = sc1 > 500, w2 = sc2 > 500;  // >500=win; 500=tie (PvPoke)
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
    setCollectionStatus('collection support unavailable for this dive', 'var(--loss)');
    return;
  }
  // csvText === null means "reprocess with the current csvMons + manualMons"
  // (used by the manual-entry add/remove path). A string argument means
  // "reparse this CSV and replace csvMons."
  if (csvText != null) {
    try {
      state.csvMons = POGOCollection.parseCsvText(csvText);
    } catch (e) {
      setCollectionStatus('Parse error: ' + e.message, 'var(--loss)');
      return;
    }
  }
  var mons = (state.csvMons || []).concat(state.manualMons || []);
  if (mons.length === 0) {
    setCollectionStatus('No rows parsed (empty CSV?)', 'var(--loss)');
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
  // Off-grid stat-product rank lookup follows the toggle too: alt-cap table in
  // the L51 view when present (on-grid mons use the toggle-aware DATA.spRanks).
  var rankLookup = (state.levelMode === '51' && coll.rankLookupAlt)
    ? coll.rankLookupAlt : coll.rankLookup;
  var leagueCap = coll.leagueCap;
  // When the dive carries a best-buddy toggle, the collection follows it: in the
  // league-default (L50) view, owned mons are capped at the default level; in the
  // best-buddy (L51) view they may climb one more. Without a toggle, keep the
  // baked cap (historical behavior). setBestBuddyLevel re-runs loadCollection so
  // these stats recompute on toggle.
  var maxLevel = coll.maxLevel;
  if (DATA.bestBuddy) {
    maxLevel = (state.levelMode === '51')
      ? (DATA.bestBuddy.altCap || coll.maxLevel)
      : (DATA.bestBuddy.defaultCap || 50.0);
  }
  // Gender filter for gender-differentiated species (Oinkologne /
  // Meowstic / Indeedee). When the focal species is "X (Female)",
  // we set requireGender='female'; when bare "X" with a Female
  // sibling, requireGender='male'. Otherwise null = no filter.
  // CSV rows without a gender (older Poke Genie exports) pass
  // through unfiltered.
  var requireGender = coll.requireGender || null;

  // Build the species thresholds dict from the LIVE tiers array
  // (populated after generate_analysis_sections ran). Prefer
  // DATA.pasteTiers when present - it's the scatter-plot tiers
  // plus any narrative flavors that weren't already represented
  // (non-General only), so paste-box membership picks up flavors
  // like "Fortified Azumarill" that never made it into
  // DATA.tiers. Falls back to DATA.tiers on older dives.
  var liveTiers = DATA.pasteTiers || DATA.tiers || [];
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
    // Gender filter: skip mons whose CSV-recorded gender doesn't
    // match a gender-specific focal species. Blank-gender rows
    // pass through (older Poke Genie exports may not populate the
    // Gender column).
    if (requireGender && mon.gender && mon.gender !== requireGender) {
      continue;
    }
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
  var nCsv = (state.csvMons || []).length;
  var nManual = (state.manualMons || []).length;
  var rowLabel = (nManual > 0)
    ? (mons.length + ' rows (' + nCsv + ' csv, ' + nManual + ' manual)')
    : (mons.length + ' rows parsed');
  var parts = [rowLabel];
  parts.push(ownedCount + ' match this dive');
  parts.push(qualifyingCount + ' qualify for >= 1 tier');
  if (slayerCount > 0) parts.push(slayerCount + ' slayer');
  if (overCapCount > 0) parts.push(overCapCount + ' already over cap');
  if (offGridCount > 0) parts.push(offGridCount + ' off-grid (not in simulated set)');
  setCollectionStatus(parts.join(' \u00b7 '), 'var(--win)');
  updateTierCardCounts(tierCounts);
  renderMatchesList();
  annotateAnchorBullets();
  updateView();
  mcRefreshAll();
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
      span.style.color = 'var(--text-muted)';
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
    span.style.color = 'var(--win)';
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

  // Tier names come from the LIVE tiers array (populated after
  // analysis sections ran). Prefer DATA.pasteTiers so narrative
  // flavors show up here alongside plot tiers; falls back to
  // DATA.tiers on older dives. This mirrors the fix in
  // loadCollection.
  var liveTiers = DATA.pasteTiers || DATA.tiers || [];
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
  // Off-grid SP rank: alt-cap table in the best-buddy (L51) view when present.
  var rankLookup = (DATA.collection &&
                    ((state.levelMode === '51' && DATA.collection.rankLookupAlt)
                       ? DATA.collection.rankLookupAlt : DATA.collection.rankLookup)) || {};
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

  // Efficient-IV badges.
  //   _isCrown: the mon's IV is globally Pareto-efficient for this
  //             species/league (DATA.ivEfficient lookup; off-grid mons
  //             have no canonical index so cannot be crowned).
  //   _isTrophy: OUR addition. Among the user's QUALIFYING mons (those
  //             that matched >=1 tier), a mon earns a trophy if it
  //             dominates another qualifying mon on all three scaled
  //             stats and none of theirs dominates it (best of what they
  //             actually caught). Crown OUTRANKS trophy: a crowned mon
  //             shows only the crown.
  // Strict inequality (fact 2): identical (atk,def,hp) spreads never
  // dominate each other, so duplicate-IV mons tie and get the same badge.
  var _qualRecs = [];
  for (var rq = 0; rq < state.userRecords.length; rq++) {
    var _qrec = state.userRecords[rq];
    _qrec._isCrown = !!(DATA.ivEfficient && _qrec.canonicalIvIdx >= 0 &&
                        DATA.ivEfficient[_qrec.canonicalIvIdx]);
    _qrec._isTrophy = false;
    if (_qrec.matched && _qrec.matched.length > 0 && _qrec.stats) _qualRecs.push(_qrec);
  }
  function _dominates(a, b) {
    var aa = a.stats.attack, ad = a.stats.defense, ah = a.stats.stamina;
    var ba = b.stats.attack, bd = b.stats.defense, bh = b.stats.stamina;
    return aa >= ba && ad >= bd && ah >= bh && (aa > ba || ad > bd || ah > bh);
  }
  for (var qi = 0; qi < _qualRecs.length; qi++) {
    var domSomeone = false, dominated = false;
    for (var qj = 0; qj < _qualRecs.length; qj++) {
      if (qi === qj) continue;
      if (_dominates(_qualRecs[qi], _qualRecs[qj])) domSomeone = true;
      if (_dominates(_qualRecs[qj], _qualRecs[qi])) dominated = true;
    }
    // Crown outranks trophy: skip the trophy when already crowned.
    _qualRecs[qi]._isTrophy = !_qualRecs[qi]._isCrown && domSomeone && !dominated;
  }

  function powerUpText(rc) {
    if (rc.isOverCap) return '<span style="color:var(--title)">OVER</span>';
    var curLv = rc.mon.level;
    var maxLv = rc.stats ? rc.stats.level : null;
    if (curLv == null || maxLv == null) return '?';
    var d = maxLv - curLv;
    if (d <= 0) return '\u2713';
    // Show the gap in LEVELS (whole or .5), not a half-level count -- "+18 lv"
    // reads cleanly, where "+36 1/2L" looked like "36.5 levels".
    var lv = (Math.abs(d - Math.round(d)) < 1e-6) ? String(Math.round(d)) : d.toFixed(1);
    return '+' + lv + ' lv';
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
        var aa = (a.stats ? a.stats.attack : 0), ba = (b.stats ? b.stats.attack : 0);
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
    // Heading hugs its OWN table (small bottom margin, no top margin) -- the
    // card wrapper added at the return is what separates one section from the
    // next, so a heading like "Slayer IVs" can't visually attach to the table
    // above it.
    var h = '<h5 style="margin:0 0 8px;color:var(--heading)">' +
            heading + ' - ' + recs.length + ' of yours</h5>';
    h += '<table data-section="' + sid + '-tbl"><tr>';
    var sortHdr = function(label, colIdx, title) {
      var t = title ? ' title="' + title + '"' : '';
      return '<th style="cursor:pointer" onclick="sortMatchesTable(\'' + sid + '-tbl\',' + colIdx + ',this)"' + t + '>' + label + '</th>';
    };
    h += sortHdr('Battle', 0, 'Battle rank in the active moveset / opp-IV mode. Dash for off-grid mons whose exact IV was not simulated.');
    h += sortHdr('SP', 1, 'Stat product rank (pure math, computed for all 4096 IV triples). Always available.');
    h += sortHdr('Current CP', 2);
    h += '<th>IVs</th>';
    h += sortHdr('Atk', 4);
    h += sortHdr('Def', 5);
    h += sortHdr('HP', 6);
    h += '<th>Species</th><th>Power-up</th>';
    h += sortHdr('Max CP', 9);
    if (extras) {
      for (var xh = 0; xh < extras.length; xh++) {
        var _xhCls = extras[xh].cls ? (' class="' + extras[xh].cls + '"') : '';
        var _xhTitle = extras[xh].help ? (' title="' + extras[xh].help.replace(/"/g, '&quot;') + '"') : '';
        h += '<th' + _xhCls + _xhTitle + '>' + escapeHtml(extras[xh].header).replace(/\n/g, '<br>') + '</th>';
      }
    }
    h += '</tr>';
    for (var k = 0; k < recs.length; k++) {
      var rc = recs[k];
      var cls = '';
      if (rc.mon.is_shadow) cls += ' shadow';
      if (rc.mon.lucky) cls += ' lucky';
      // Inline display:none for rows past MAX_VISIBLE — self-contained,
      // no dependency on CSS that lives in the Python HTML generator.
      var attr = ' data-section="' + sid + '"';
      if (cls) attr += ' class="' + cls.trim() + '"';
      if (k >= MAX_VISIBLE) attr += ' style="display:none"';
      h += '<tr' + attr + '>';
      var brVal = (rc._battleRank != null) ? rc._battleRank : 99999;
      var spVal = (rc._spRank != null) ? rc._spRank : 99999;
      var atkVal = rc.stats ? rc.stats.attack : 0;
      var defVal = rc.stats ? rc.stats.defense : 0;
      var hpVal = rc.stats ? rc.stats.stamina : 0;
      var mcpVal = rc.stats ? rc.stats.cp : 0;
      h += '<td class="rank" data-sort="' + brVal + '">' + (brVal < 99999 ? '#' + brVal : '-') + '</td>';
      h += '<td class="rank-sp" data-sort="' + spVal + '">' + (spVal < 99999 ? '#' + spVal : '-') + '</td>';
      h += '<td data-sort="' + rc.mon.cp + '"><b>CP ' + rc.mon.cp + '</b></td>';
      h += '<td>' + rc.mon.atk_iv + '/' + rc.mon.def_iv + '/' + rc.mon.sta_iv + '</td>';
      h += '<td data-sort="' + atkVal.toFixed(4) + '">' + (rc.stats ? atkVal.toFixed(2) : '?') + '</td>';
      h += '<td data-sort="' + defVal.toFixed(4) + '">' + (rc.stats ? defVal.toFixed(2) : '?') + '</td>';
      h += '<td data-sort="' + hpVal + '">' + (rc.stats ? hpVal : '?') + '</td>';
      h += '<td>' + escapeHtml(rc.csvSpecies || '') +
           (rc.mon.lucky ? ' \u2728' : '') +
           (rc.mon.is_shadow ? ' \u263d' : '') +
           (rc._isCrown ? ' <span title="Efficient: globally Pareto-optimal IVs">\ud83d\udc51</span>'
              : (rc._isTrophy ? ' <span title="Best of your qualifying mons (dominates another of yours on all scaled stats)">\ud83c\udfc6</span>' : '')) +
           '</td>';
      h += '<td>' + powerUpText(rc) + '</td>';
      h += '<td data-sort="' + mcpVal + '">' + (rc.stats ? rc.stats.cp : '?') + '</td>';
      if (extras) {
        for (var xc = 0; xc < extras.length; xc++) {
          var _xcCls = extras[xc].cls ? (' class="' + extras[xc].cls + '"') : '';
          h += '<td' + _xcCls + '>' + extras[xc].cell(rc) + '</td>';
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
    // Wrap each section in its own card so the heading + table read as one
    // unit, clearly separated from the next section (no more "which table does
    // this heading belong to?" -- it belongs to the one inside its card).
    return '<div style="background:var(--surface-2);border:1px solid var(--border);' +
           'border-radius:8px;padding:11px 14px;margin:0 0 14px">' + h + '</div>';
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

  // "Gives up vs #1" -- the collection-table version of the IV-guide "what you
  // give up" breakdown, keyed to the CURRENT y-axis. The reference "#1" is the
  // IV ranked first on the active y-axis metric, and a dropped matchup is one
  // the #1 IV wins but this owned IV loses (same SCORES diff the scatter hover
  // uses, score > 500 = win; 500 = tie). On-grid only; off-grid '-'. winsMirror has no
  // per-opponent grid, so it shows the mirror-win shortfall (count only).
  var _guMode = state.yAxisMode || 'avgScore';
  var _guLabel = '#1';
  if (DATA.yAxisModes) {
    for (var _ym = 0; _ym < DATA.yAxisModes.length; _ym++) {
      if (DATA.yAxisModes[_ym].id === _guMode) { _guLabel = DATA.yAxisModes[_ym].label; break; }
    }
  }
  var givesUpHeader = 'Gives up vs #1\n(' + _guLabel + ')';
  var HELP_GIVES_UP = 'Matchups the #1 IV on the current y-axis (' + _guLabel +
    ') wins but this one loses, over the selected shields. Hover the number to ' +
    'list them. "0" = gives up nothing; "-" = off-grid IV (not simulated). ' +
    'Updates when you change the y-axis.';
  // Precompute the y-axis #1 IV + matching score source once per render.
  var _guRefIv = -1, _guScores = null;
  if (_guMode !== 'winsMirror') {
    if (typeof yValues !== 'undefined' && yValues) {
      var _bestV = -Infinity;
      for (var _gi = 0; _gi < nIvs; _gi++) {
        if (yValues[_gi] > _bestV) { _bestV = yValues[_gi]; _guRefIv = _gi; }
      }
    }
    _guScores = (_guMode === 'winsPvpoke') ? getScores(state.movesetIdx, 'pvpoke')
              : (_guMode === 'winsRank1') ? getScores(state.movesetIdx, 'rank1')
              : getScores(state.movesetIdx, state.oppIvMode);
  }
  function _cellGivesUp(rc) {
    var iv = rc.canonicalIvIdx;
    if (iv == null || iv < 0) return '-';
    if (_guMode === 'winsMirror') {
      var mw = DATA.mirrorWinsByIv;
      if (!mw) return '-';
      var dm = (DATA.mirrorWinsMax || 0) - (mw[iv] || 0);
      if (dm <= 0) return '<span style="color:var(--win)">0</span>';
      var mc = dm <= 3 ? 'var(--notable)' : 'var(--loss)';
      return '<span style="color:' + mc + '" title="fewer mirror-cohort wins ' +
             'than the #1 IV">' + dm + '</span>';
    }
    if (_guRefIv < 0 || !_guScores) return '-';
    if (iv === _guRefIv) return '<span style="color:var(--win)">#1</span>';
    var sis = getActiveScenarioIndices();
    var selSetGU = selectedOppSet();  // null == all opponents; honor the filter
    var lost = [];
    for (var k = 0; k < sis.length; k++) {
      var si = sis[k];
      var sc = DATA.scenarios[si];
      var lab = sc[0] + 'v' + sc[1];
      for (var oi = 0; oi < nO; oi++) {
        if (selSetGU && !selSetGU[oi]) continue;  // opponent filtered out
        var refW = _guScores[_guRefIv * nS * nO + si * nO + oi] > 500;  // 500=tie (PvPoke)
        var myW = _guScores[iv * nS * nO + si * nO + oi] > 500;
        if (refW && !myW) lost.push(shortName(DATA.opponents[oi]) + ' ' + lab);
      }
    }
    if (lost.length === 0) return '<span style="color:var(--win)">0</span>';
    // Show the whole list (the count is already in the cell); cap only to
    // avoid a pathological wall on a terrible IV that drops most matchups.
    var CAP = 40;
    var shown = lost.slice(0, CAP).join(', ');
    if (lost.length > CAP) shown += ', +' + (lost.length - CAP) + ' more';
    var color = lost.length <= 3 ? 'var(--notable)' : 'var(--loss)';
    return '<span style="color:' + color + '" title="' +
           shown.replace(/"/g, '&quot;') + '">' + lost.length + '</span>';
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
          { header: 'Also in', cls: 'wrap', cell: function(rc) {
              var also = otherTiersExcept(rc, currentTierName);
              if (rc.slayerCats && rc.slayerCats.length > 0) {
                also = also.concat(rc.slayerCats);
              }
              return listOrDash(also);
          } },
          { header: givesUpHeader, cell: _cellGivesUp, help: HELP_GIVES_UP }
        ],
        isDefTier ? 'atk' : null
      );
    })(tierNames[ti], ti);
  }
  // Slayer section: two extra columns — specific slayer categories
  // AND which tiers this slayer mon ALSO clears (blank for slayer-
  // only mons, populated for mons that are both slayer + tier).
  // Top-Mirror CMP % / Matchups Kept cell helpers: on-grid only
  // (canonicalIvIdx >= 0). Off-grid records show '-'. The helpers are
  // the same ones used by the Top IVs table, so numbers agree. /* SLAYER_NEW_COLS_v1 */
  function _cellTopMirror(rc) {
    var iv = rc.canonicalIvIdx;
    if (iv == null || iv < 0) return '-';
    var v = _computeTopMirrorCmpPct(iv);
    if (!isFinite(v)) return '-';
    var color = v >= 90 ? 'var(--win)' : (v >= 50 ? 'var(--notable)' : 'var(--text-muted)');
    return '<span style="color:' + color + '">' + v.toFixed(0) + '%</span>';
  }
  function _cellMatchupsKept(rc) {
    var iv = rc.canonicalIvIdx;
    if (iv == null || iv < 0) return '-';
    var v = _computeMatchupsKept(iv);
    if (!isFinite(v)) return '-';
    var den = _matchupsKeptDenom();
    var frac = den > 0 ? (v / den) : 0;
    var color = frac >= 0.8 ? 'var(--win)' : (frac >= 0.5 ? 'var(--notable)' : 'var(--text-muted)');
    var vStr = (Math.abs(v - Math.round(v)) < 1e-6) ? String(Math.round(v)) : v.toFixed(1);
    return '<span style="color:' + color + '">' + vStr + '/' + den + '</span>';
  }
  html += renderSection(
    'Slayer IVs',
    slayerRecs,
    [
      { header: 'Slayer type',      cls: 'wrap', cell: function(rc) { return listOrDash(rc.slayerCats); } },
      { header: 'Also in',          cls: 'wrap', cell: function(rc) { return listOrDash(rc.matched); } },
      { header: 'Top-Mirror CMP %', cell: _cellTopMirror,    help: HELP_TOP_MIRROR_CMP },
      { header: 'Matchups Kept',    cell: _cellMatchupsKept, help: HELP_MATCHUPS_KEPT },
      { header: givesUpHeader,      cell: _cellGivesUp,      help: HELP_GIVES_UP }
    ]
  );

  if (html === '') {
    html = '<p style="font-size:12px;color:var(--text-muted);margin:8px 0">' +
           'No mons in your collection qualify for any tier or slayer category.</p>';
  }
  el.innerHTML = html;
}

// Show/hide toggle handler for the collapsible matches-list sections.
// Uses inline display style on rows (skipping the first 5, which
// always stay visible). Global so the button's onclick handler can
// reach it from the renderMatchesList output.
// Shared row cap for collapsible match tables (toggle + sort must agree).
var MAX_VISIBLE_MATCH_ROWS = 5;

function toggleMatchesSection(sid, btn) {
  var rows = document.querySelectorAll('tr[data-section="' + sid + '"]');
  if (rows.length === 0) return;
  var isExpanding = btn.textContent.indexOf('Show') === 0;
  for (var i = MAX_VISIBLE_MATCH_ROWS; i < rows.length; i++) {
    rows[i].style.display = isExpanding ? '' : 'none';
  }
  var count = btn.getAttribute('data-hidden-count');
  btn.textContent = isExpanding ? ('Hide ' + count + ' \u2191') : ('Show ' + count + ' more \u2193');
}

// Sort a matches table by clicking column headers. Toggles asc/desc.
function sortMatchesTable(tblId, colIdx, thEl) {
  var tbl = document.querySelector('table[data-section="' + tblId + '"]');
  if (!tbl) return;
  var rows = Array.prototype.slice.call(tbl.querySelectorAll('tr[data-section]'));
  if (rows.length === 0) return;
  // Determine sort direction: toggle if same column clicked again
  var prevCol = tbl.getAttribute('data-sort-col');
  var prevDir = tbl.getAttribute('data-sort-dir') || 'asc';
  var dir;
  if (prevCol === String(colIdx)) {
    dir = (prevDir === 'asc') ? 'desc' : 'asc';
  } else {
    // Ranks sort asc by default (lower = better), stats sort desc (higher = better)
    dir = (colIdx <= 1) ? 'asc' : 'desc';
  }
  tbl.setAttribute('data-sort-col', colIdx);
  tbl.setAttribute('data-sort-dir', dir);
  // Update header arrows
  var ths = tbl.querySelectorAll('th');
  for (var i = 0; i < ths.length; i++) {
    var txt = ths[i].textContent.replace(/ [\u25B2\u25BC]$/, '');
    ths[i].textContent = txt;
  }
  thEl.textContent = thEl.textContent + (dir === 'asc' ? ' \u25B2' : ' \u25BC');
  // Capture collapsed state BEFORE sorting: after the sort, the row at
  // the cap index may be one that was visible pre-sort, so reading it
  // post-sort silently expanded a collapsed table while the toggle
  // button still said "Show N more" (2026-06-11 review, W4).
  var wasCollapsed = false;
  for (var r0 = MAX_VISIBLE_MATCH_ROWS; r0 < rows.length; r0++) {
    if (rows[r0].style.display === 'none') { wasCollapsed = true; break; }
  }
  // Sort rows by data-sort attribute on the target column
  rows.sort(function(a, b) {
    var ac = a.cells[colIdx], bc = b.cells[colIdx];
    var av = ac ? parseFloat(ac.getAttribute('data-sort') || '99999') : 99999;
    var bv = bc ? parseFloat(bc.getAttribute('data-sort') || '99999') : 99999;
    return dir === 'asc' ? av - bv : bv - av;
  });
  // Re-append in sorted order
  var tbody = rows[0].parentNode;
  for (var r = 0; r < rows.length; r++) {
    tbody.appendChild(rows[r]);
    // Preserve collapsed state: hide rows past the cap if collapsed
    if (wasCollapsed) {
      rows[r].style.display = (r < MAX_VISIBLE_MATCH_ROWS) ? '' : 'none';
    } else {
      rows[r].style.display = '';
    }
  }
}

// Copy a Notable-IVs card's gobattlekit user-threshold JSON fragment
// (built server-side into data-scanner-json) to the clipboard, with a
// transient button-label acknowledgement and an execCommand fallback
// for non-secure contexts (file:// pages).
function copyScannerJson(btn) {
  var payload = btn.getAttribute('data-scanner-json');
  if (!payload) return;
  var orig = btn.textContent;
  function done(ok) {
    btn.textContent = ok ? 'Copied!' : 'Copy failed';
    setTimeout(function() { btn.textContent = orig; }, 1500);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(payload).then(
      function() { done(true); }, function() { done(false); });
  } else {
    var ta = document.createElement('textarea');
    ta.value = payload;
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
    done(ok);
  }
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
  state.csvMons = [];
  state.manualMons = [];
  var chk = document.getElementById('collection-only-chk');
  if (chk) chk.checked = false;
  var ta = document.getElementById('collection-csv');
  if (ta) ta.value = '';
  setCollectionStatus('', 'var(--text-muted)');
  updateTierCardCounts({});
  renderMatchesList();
  annotateAnchorBullets();
  renderManualList();
  updateView();
  mcRefreshAll();
}

// ---- Manual one-at-a-time IV entry ----
//
// Users can add Pokemon one row at a time without pasting a CSV. Each
// manual entry builds the same mon object shape as the CSV parser
// (name, form, cp, atk_iv, def_iv, sta_iv, level, is_shadow, lucky)
// and stacks into state.manualMons. loadCollection(null) reprocesses
// the merged csvMons + manualMons list.

function populateManualSpeciesSelect() {
  var sel = document.getElementById('manual-species');
  if (!sel || !DATA.collection) return;
  var speciesKey = DATA.collection.speciesKey;
  var preToFinals = DATA.collection.preToFinals || {};
  // Valid species = the dive's species itself, plus any pre-evolution
  // whose finals include it. Tinkaton dive → Tinkatink, Tinkatuff, Tinkaton.
  var options = [speciesKey];
  for (var k in preToFinals) {
    if (!preToFinals.hasOwnProperty(k)) continue;
    if (k === speciesKey) continue;
    var finals = preToFinals[k] || [];
    if (finals.indexOf(speciesKey) >= 0) options.push(k);
  }
  // Final species first, then pre-evolutions alphabetical.
  options.sort(function(a, b) {
    if (a === speciesKey) return -1;
    if (b === speciesKey) return 1;
    return a.localeCompare(b);
  });
  sel.innerHTML = '';
  for (var i = 0; i < options.length; i++) {
    var opt = document.createElement('option');
    opt.value = options[i];
    opt.textContent = options[i];
    sel.appendChild(opt);
  }
}

// Parse the manual-entry form into a mon object matching parseCsvText's
// output shape. Returns null on invalid input; the caller surfaces an
// error to the status line.
function readManualForm() {
  function intVal(id) { return parseInt(document.getElementById(id).value, 10); }
  function floatVal(id) { return parseFloat(document.getElementById(id).value); }
  var species = document.getElementById('manual-species').value || '';
  var atkIv = intVal('manual-atk');
  var defIv = intVal('manual-def');
  var staIv = intVal('manual-hp');
  var level = floatVal('manual-level');
  var isShadow = document.getElementById('manual-shadow').checked;
  if (!isFinite(atkIv) || atkIv < 0 || atkIv > 15) return null;
  if (!isFinite(defIv) || defIv < 0 || defIv > 15) return null;
  if (!isFinite(staIv) || staIv < 0 || staIv > 15) return null;
  if (!isFinite(level) || level < 1 || level > 51) return null;
  // Dropdown values are full species keys ("Tinkaton", "Tinkatink",
  // "Corsola (Galarian)"). Split back into name + form for the mon
  // object; is_shadow comes from the checkbox, not the species string.
  var name = species;
  var form = '';
  var m = species.match(/^(.*)\s+\((.*)\)$/);
  if (m && m[2] !== 'Shadow') { name = m[1]; form = m[2]; }
  return {
    name: name,
    form: form,
    cp: 0,
    atk_iv: atkIv,
    def_iv: defIv,
    sta_iv: staIv,
    level: level,
    is_shadow: isShadow,
    lucky: false,
  };
}

function addManualMon() {
  var mon = readManualForm();
  if (mon == null) {
    setCollectionStatus('Manual entry invalid - check IVs (0-15) and level.', 'var(--loss)');
    return;
  }
  if (!state.manualMons) state.manualMons = [];
  state.manualMons.push(mon);
  renderManualList();
  loadCollection(null);
}

function removeManualMon(idx) {
  if (!state.manualMons) return;
  if (idx < 0 || idx >= state.manualMons.length) return;
  state.manualMons.splice(idx, 1);
  renderManualList();
  // If removing the last manual mon with no csv loaded, loadCollection
  // hits the "no rows" bail and never clears state. Do the cleanup here.
  if (state.manualMons.length === 0 && (!state.csvMons || state.csvMons.length === 0)) {
    state.userRecords = null;
    state.ownedByIv = null;
    setCollectionStatus('', 'var(--text-muted)');
    updateTierCardCounts({});
    renderMatchesList();
    annotateAnchorBullets();
    updateView();
    mcRefreshAll();
    return;
  }
  loadCollection(null);
}

function renderManualList() {
  var el = document.getElementById('manual-list');
  if (!el) return;
  var mons = state.manualMons || [];
  if (mons.length === 0) { el.innerHTML = ''; return; }
  var html = '<b>Manual entries (' + mons.length + '):</b> ';
  var chips = [];
  for (var i = 0; i < mons.length; i++) {
    var m = mons[i];
    var label = (m.is_shadow ? 'S ' : '') + escapeHtml(m.name) +
                (m.form ? ' (' + escapeHtml(m.form) + ')' : '') +
                ' ' + m.atk_iv + '/' + m.def_iv + '/' + m.sta_iv +
                ' L' + m.level;
    chips.push(
      '<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 6px;' +
      'background:var(--border);border-radius:3px">' + label +
      ' <a href="#" data-manual-idx="' + i + '" class="manual-remove" ' +
      'style="color:var(--loss);text-decoration:none;margin-left:4px">&times;</a></span>'
    );
  }
  el.innerHTML = html + chips.join('');
  var links = el.querySelectorAll('a.manual-remove');
  for (var j = 0; j < links.length; j++) {
    links[j].addEventListener('click', function(ev) {
      ev.preventDefault();
      var idx = parseInt(ev.currentTarget.getAttribute('data-manual-idx'), 10);
      removeManualMon(idx);
    });
  }
}

function setCollectionStatus(text, color) {
  var el = document.getElementById('collection-status');
  if (!el) return;
  el.textContent = text;
  el.style.color = color || 'var(--text-muted)';
}

// Fill in "N of yours qualify" annotations on tier cards. Tier cards
// emit empty spans with ids `tier-card-yours-<slug>` where slug is
// derived from `original_name` when present (falls back to `name`)
// so the id stays stable across the 2026-04-23 tier-name unify, which
// overwrites `name` with the narrative flavor name but preserves the
// pre-rename label on `original_name`. If a card's span is missing
// (older template or filtered out), this is a silent no-op.
function updateTierCardCounts(tierCounts) {
  // Read from the live tiers array (post-analysis) rather than the
  // stale pre-analysis DATA.collection.tierNames snapshot — same
  // reason as the fix in loadCollection/renderMatchesList. Prefer
  // DATA.pasteTiers so narrative-flavor tier cards get their "N of
  // yours qualify" annotation too.
  var liveTiers = DATA.pasteTiers || DATA.tiers || [];
  for (var i = 0; i < liveTiers.length; i++) {
    var t = liveTiers[i];
    if (!t || !t.name) continue;
    var n = t.name;
    var slugSource = t.original_name || t.name;
    var slug = slugSource.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
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
  // Manual entry: populate species options, wire Add button.
  populateManualSpeciesSelect();
  var addBtn = document.getElementById('manual-add-btn');
  if (addBtn) addBtn.addEventListener('click', addManualMon);
}

// ---- Highlight-specific-IVs feature ----
//
// Lazy-built map "a,d,s" -> canonicalIvIdx so applyHighlight can turn
// user-typed triples into trace indices without rescanning DATA.ivA
// every call. Built once on first use; cleared if (somehow) DATA
// changes, but in practice this dive is single-session static data.
var _ivLookupByTriple = null;
function _buildIvLookup() {
  var m = {};
  for (var i = 0; i < nIvs; i++) {
    m[DATA.ivA[i] + ',' + DATA.ivD[i] + ',' + DATA.ivS[i]] = i;
  }
  return m;
}

// Parse a user-typed highlight string into {validIdxs, invalidTokens}.
// Accepted separators within a triple: '/', '-', whitespace. Between
// triples: comma. Lenient about extra whitespace.
function _parseHighlightInput(text) {
  if (_ivLookupByTriple === null) _ivLookupByTriple = _buildIvLookup();
  var validIdxs = [];
  var invalidTokens = [];
  var seen = {};
  var parts = String(text || '').split(',');
  for (var p = 0; p < parts.length; p++) {
    var tok = parts[p].trim();
    if (!tok) continue;
    var nums = tok.split(/[\/\-\s]+/).filter(function(s){ return s !== ''; });
    if (nums.length !== 3) { invalidTokens.push(tok); continue; }
    var a = parseInt(nums[0], 10), d = parseInt(nums[1], 10), s = parseInt(nums[2], 10);
    if (!(a >= 0 && a <= 15 && d >= 0 && d <= 15 && s >= 0 && s <= 15)) {
      invalidTokens.push(tok); continue;
    }
    var idx = _ivLookupByTriple[a + ',' + d + ',' + s];
    if (idx == null) { invalidTokens.push(tok + ' (not in dive grid)'); continue; }
    if (seen[idx]) continue;
    seen[idx] = true;
    validIdxs.push(idx);
  }
  return { validIdxs: validIdxs, invalidTokens: invalidTokens };
}

function applyHighlight() {
  var inp = document.getElementById('highlight-input');
  var status = document.getElementById('highlight-status');
  if (!inp) return;
  var parsed = _parseHighlightInput(inp.value);
  state.highlightIvs = parsed.validIdxs;
  if (status) {
    var msg = '';
    if (parsed.validIdxs.length > 0) {
      msg += 'Highlighting ' + parsed.validIdxs.length + ' IV' +
             (parsed.validIdxs.length === 1 ? '' : 's');
    }
    if (parsed.invalidTokens.length > 0) {
      if (msg) msg += '; ';
      msg += 'ignored: ' + parsed.invalidTokens.join(', ');
      status.style.color = 'var(--loss)';
    } else {
      status.style.color = 'var(--win)';
    }
    status.textContent = msg;
  }
  updateView();
}

function clearHighlight() {
  var inp = document.getElementById('highlight-input');
  var status = document.getElementById('highlight-status');
  if (inp) inp.value = '';
  if (status) { status.textContent = ''; status.style.color = 'var(--text-muted)'; }
  state.highlightIvs = [];
  updateView();
}

// Build the red-diamond overlay trace for state.highlightIvs. Returns
// null when the highlight set is empty. Matches the hover-text format
// used by other traces so tooltips stay consistent.
//
// Hit-detection nudge: the diamond y is offset DOWNWARD by the same
// Y_NUDGE the "Yours" overlays use (but in the opposite direction) so
// it occupies a distinct closest-point in Plotly's scattergl hover
// routing. Without this, the diamond collides with both the base
// trace AND the "Yours - notable" ring at the same IV (for owned
// IVs), and the hover falls silently on some points -- reproducing
// the exact same class of bug that the Yours-overlay +Y_NUDGE was
// introduced to fix. See the comment above qualY at buildTraces
// (~line 1719) for the full history.
function _buildHighlightTrace() {
  if (!state.highlightIvs || state.highlightIvs.length === 0) return null;
  // Recompute yRange for the nudge magnitude. Same formula used for
  // the Yours overlays; kept local rather than plumbed through so
  // _buildHighlightTrace is self-contained.
  var _yMin = Infinity, _yMax = -Infinity;
  for (var _yi = 0; _yi < yValues.length; _yi++) {
    var _yv = yValues[_yi];
    if (isFinite(_yv)) {
      if (_yv < _yMin) _yMin = _yv;
      if (_yv > _yMax) _yMax = _yv;
    }
  }
  var yRange = Math.max(1, _yMax - _yMin);
  var NUDGE = -yRange * 0.0005;  // downward, opposite of Yours overlays
  var hx = [], hy = [], ht = [];
  for (var i = 0; i < state.highlightIvs.length; i++) {
    var iv = state.highlightIvs[i];
    if (currentYIsSparse && !isFinite(yValues[iv])) continue;
    hx.push(DATA.spRanks[iv]);
    hy.push(yValues[iv] + NUDGE);
    ht.push(buildHoverText(iv));
  }
  if (hx.length === 0) return null;
  return {
    name: 'Highlighted',
    x: hx, y: hy, text: ht,
    mode: 'markers', type: 'scattergl', hoverinfo: 'text',
    marker: {
      size: 14, color: '#e94560', symbol: 'diamond',
      opacity: 1.0, line: { width: 2, color: '#ffffff' }
    },
    hoverlabel: { bordercolor: '#e94560' }
  };
}

// Wrap long legend names at word boundaries (Plotly can't wrap natively;
// anchor/spec-card tier names like "Fortified Gyarados (Shadow) (Dragon
// Breath / Aqua Tail+Twister) (151.27+ Def)" otherwise push the legend far
// off-plot). Display-only: nothing compares trace.name programmatically.
function wrapLegendName(name, width) {
  width = width || 26;
  if (!name || name.length <= width) return name;
  var words = String(name).split(' ');
  var lines = [], cur = '';
  for (var i = 0; i < words.length; i++) {
    if (cur && (cur + ' ' + words[i]).length > width) {
      lines.push(cur); cur = words[i];
    } else {
      cur = cur ? cur + ' ' + words[i] : words[i];
    }
  }
  if (cur) lines.push(cur);
  return lines.join('<br>');
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
    //
    // Density-aware styling (added 2026-06-03): when one tier dominates
    // the IV pool (e.g. "Sableye Mirror Bulk" covers 100% of 4096 IVs
    // in the Shadow Sableye / Dazzling Gleam dive), a uniform size-7
    // opacity-0.9 wash drowns out the rare per-opponent Atk/Slayer
    // categories drawn on top — the z-order is correct but the visual
    // wash overwhelms the eye. Two compensations:
    //   1. Dominant tiers (>50% of IVs) fade to opacity 0.35 so the
    //      rare-tier markers on top can punch through visually.
    //   2. Tiny tiers (<5% of IVs) get marker size 9 instead of 7 so
    //      they're physically larger relative to the wash even when
    //      their color collides with the dominant tier.
    // Both gates use nIvs (full IV pool) as the denominator so the
    // styling is stable across opp-IV / bait / scenario toggles that
    // change yValues but not the underlying tier membership counts.
    var _tierTraces = [];
    var _tierDomThreshold = nIvs * 0.5;
    var _tierTinyThreshold = nIvs * 0.05;
    for (var ti=0; ti<tierNames.length; ti++) {
      var tx=[], ty=[], tt=[];
      // Tier membership count is independent of y-axis filtering — count
      // by ivAllTiers directly so the dominant/tiny gates don't flicker
      // when the user toggles a sparse y-axis mode (sparse drops some
      // IVs from tx, but tier identity hasn't changed).
      var _tierTotal = 0;
      for (var iv=0; iv<nIvs; iv++) {
        if (DATA.ivAllTiers[iv] && DATA.ivAllTiers[iv].indexOf(ti) >= 0) {
          _tierTotal++;
        }
      }
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
        var _isDom = _tierTotal > _tierDomThreshold;
        var _isTiny = _tierTotal < _tierTinyThreshold;
        var _markerSize = _isTiny ? 9 : 7;
        var _markerOpacity = _isDom ? 0.35 : 0.9;
        _tierTraces.push({
          name:wrapLegendName(tierNames[ti]),
          x:tx, y:ty, text:tt,
          mode:'markers', type:'scattergl', hoverinfo:'text',
          marker:{size:_markerSize, color:tierColors[ti],
                   opacity:_markerOpacity,
                   line:{width:1, color:'#000'}},
          hoverlabel:{bordercolor:tierColors[ti]}
        });
      }
    }
  } else if (cm === 'cluster') {
    // --- Matchup-fingerprint cluster coloring ---
    // Labels come from the live Matchup clusters section's inline JSON
    // payload (baked for moveset 0 + the default opp-IV mode at this
    // page's displayed level; the best-buddy swap keeps the live section
    // and DATA arrays level-consistent). On any other moveset/mode the
    // labels would not describe the displayed grid, so render neutral
    // points and say so in the legend instead of mis-coloring.
    var mcRoot0 = document.querySelector('.dd-mc-root');
    var mcPay = mcRoot0 ? _mcPayload(mcRoot0) : null;
    var mcHasScens = !!(mcPay && mcPay.scens &&
                        Object.keys(mcPay.scens).length > 0);
    var mcModeOk = state.movesetIdx === 0 &&
                   (!DATA.oppIvModes || state.oppIvMode === DATA.oppIvModes[0]);
    var mcOk = mcHasScens && mcModeOk;
    var mcScen = null;
    if (mcOk) {
      var sis0 = getActiveScenarioIndices();
      if (sis0.length === 1) {
        var st0 = DATA.scenarios[sis0[0]];
        var lbl0 = st0[0] + 'v' + st0[1];
        if (mcPay.scens[lbl0]) mcScen = lbl0;
      }
      if (!mcScen && mcPay.scens[mcPay['default']]) mcScen = mcPay['default'];
      if (!mcScen) mcOk = false;
    }
    if (mcOk) {
      var msc = mcPay.scens[mcScen];
      var ctr = [];
      for (var c0 = 0; c0 < msc.k; c0++) {
        ctr.push({
          name: 'C' + c0 + ' - ' + mcScen + ' (n=' + msc.sizes[c0] + ')',
          x: [], y: [], text: [],
          mode: 'markers', type: 'scattergl', hoverinfo: 'text',
          marker: {size: 4, color: mcPay.palette[c0 % mcPay.palette.length],
                   opacity: 0.75},
          hoverlabel: {bordercolor: mcPay.palette[c0 % mcPay.palette.length]}
        });
      }
      for (var civ = 0; civ < nIvs; civ++) {
        if (currentYIsSparse && !isFinite(yValues[civ])) continue;
        if (!isOwnedFilter(civ)) continue;
        var clab = msc.labels[civ];
        if (clab == null || !ctr[clab]) continue;
        ctr[clab].x.push(DATA.spRanks[civ]);
        ctr[clab].y.push(yValues[civ]);
        ctr[clab].text.push(buildHoverText(civ) +
                            '<br>Matchup cluster: C' + clab + ' (' + mcScen + ')');
      }
      for (var c1 = 0; c1 < ctr.length; c1++) {
        if (ctr[c1].x.length) traces.push(ctr[c1]);
      }
    } else {
      var ncx = [], ncy = [], nct = [];
      for (var niv = 0; niv < nIvs; niv++) {
        if (currentYIsSparse && !isFinite(yValues[niv])) continue;
        if (!isOwnedFilter(niv)) continue;
        ncx.push(DATA.spRanks[niv]);
        ncy.push(yValues[niv]);
        nct.push(buildHoverText(niv));
      }
      traces.push({
        name: wrapLegendName(mcHasScens
          ? 'Matchup clusters: available for the featured moveset with default opponent IVs only'
          : 'Matchup clusters: no robust cluster structure on this dive (see Dive Analysis)'),
        x: ncx, y: ncy, text: nct,
        mode: 'markers', type: 'scattergl', hoverinfo: 'text',
        marker: {size: 2.5, color: '#8899aa', opacity: 0.45},
        hoverlabel: {bordercolor: '#888'}
      });
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
      name:wrapLegendName('All IVs (colored by '+cLabel+')'), x:ax, y:ay, text:at,
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

  // Efficient (Pareto) overlay: index list derived from the boolean
  // DATA.ivEfficient (parallel over the canonical IV indices). This is
  // a lookup, not a recompute - the global Pareto frontier was computed
  // server-side (gopvpsim.efficiency) at render time.
  var effIvs = [];
  if (DATA.ivEfficient) {
    for (var efi = 0; efi < nIvs; efi++) {
      if (DATA.ivEfficient[efi]) effIvs.push(efi);
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
  //
  // outlineOnly flag is honored for the Anchor IVs overlay only: when
  // state.anchorDisplayMode === 'outline', the filled markers become
  // transparent rings so the named-category traces drawing on top can
  // be read against the envelope edge instead of fighting fill.
  function buildOverlayTrace(name, ivList, borderColor, subdued, outlineOnly, bigHighlight, forceSymbol, hoverSuffix) {
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
      ot.push(hoverSuffix ? (buildHoverText(iv) + hoverSuffix) : buildHoverText(iv));
      ocol.push(overlayFill(iv));
      osym.push(forceSymbol || overlaySymbol(iv));
    }
    if (ox.length === 0) return null;
    // Outline-only rendering: replace the per-point fill array with a
    // single transparent color so Plotly draws rings, and force a 1px
    // border in the legend color. Size bumps from 5 -> 6 to compensate
    // for losing the fill as a visual anchor.
    var markerColor = ocol;
    var markerOpacity = subdued ? 0.65 : 0.85;
    var markerLineWidth = subdued ? 0 : 1;
    var markerSize = subdued ? 5 : 6;
    if (outlineOnly) {
      markerColor = 'rgba(0,0,0,0)';
      markerOpacity = 0.9;
      markerLineWidth = 1;
      markerSize = 6;
    }
    // Spec Card Spreads: the chosen 2-6 card spreads. Render them larger
    // with a thick outline so this tiny, deliberately-curated set reads
    // as THE highlight on top of every other overlay (it draws last).
    if (bigHighlight) {
      markerOpacity = 1;
      markerLineWidth = 2;
      markerSize = 11;
    }
    return {
      name: wrapLegendName(name),
      x: ox, y: oy, text: ot,
      // scattergl (not svg scatter) so hover hit detection stays
      // consistent when slayer/anchor points overlap tier + user
      // overlay traces. Mixing svg + gl breaks hover on multi-trace
      // overlaps — see commit 0305924 for the user overlay version
      // of this same fix.
      mode: 'markers', type: 'scattergl', hoverinfo: 'text',
      marker: {
        size: markerSize,
        color: markerColor,
        symbol: osym,
        opacity: markerOpacity,
        line: { width: markerLineWidth, color: borderColor }
      },
      hoverlabel: { bordercolor: borderColor }
    };
  }

  // Push the anchor overlay FIRST so slayer/top-picks draw on top of
  // it. Anchor IVs are typically a much larger set (often hundreds)
  // and with full-size/full-opacity markers they visually dominate
  // the plot; subdued styling keeps them visible as context without
  // overwhelming the rarer slayer + recommended sets.
  var anchorOutline = (state.anchorDisplayMode === 'outline');
  var anchorTrace = buildOverlayTrace('Anchor IVs', DATA.anchorClearIvs, '#00ffff', true, anchorOutline);
  if (anchorTrace) traces.push(anchorTrace);
  // Efficient (Pareto) overlay: the globally Pareto-optimal IV spreads
  // ("efficient" - no other spread for this species/league
  // beats them on all three scaled stats). Subdued + a distinct
  // 'cross' symbol so this large set reads as context, like Anchor IVs,
  // without fighting the rarer slayer/rec sets that draw on top.
  var effTrace = buildOverlayTrace('Efficient (Pareto)', effIvs, '#a020f0', true, false, false, 'cross',
    '<br>Efficient IV: no other spread beats it on all of atk/def/hp.');
  if (effTrace) traces.push(effTrace);
  var slayerTrace = buildOverlayTrace('Slayer IVs', DATA.slayerIvs, '#FFD700');
  if (slayerTrace) traces.push(slayerTrace);
  // Spec Card Spreads draws last (after tier traces, below) would be
  // ideal, but tier traces must own the top z-order for hover. Pushing
  // here (after slayer) keeps it above the larger overlays; the
  // bigHighlight size + outline keep the few card spreads legible even
  // when a tier circle sits on the same point.
  var recTrace = buildOverlayTrace('Spec Card Spreads', DATA.recIvs, '#e94560', false, false, true);
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

    // Build a set of IV indices currently in the highlight set so we
    // can skip them in the user-overlay rings. Rationale: the ring
    // (circle-open) has hollow hit-detection, and when the highlight
    // diamond sits inside the ring's interior for an owned IV, Plotly
    // scattergl hover routing silently fails — cursor over the diamond
    // lands "inside the ring," which catches the hover but resolves to
    // nothing visible. Semantically the ring is also redundant for a
    // highlighted IV: the diamond is the explicit "look here" marker,
    // and the user typed the IV themselves, so they already know it's
    // in their collection. Dropping the ring for those IVs resolves
    // the hover bug without touching circle rendering (past bug
    // sensitivity per user; see commit 0305924).
    var _highlightSkip = {};
    if (state.highlightIvs) {
      for (var _hi = 0; _hi < state.highlightIvs.length; _hi++) {
        _highlightSkip[state.highlightIvs[_hi]] = true;
      }
    }
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
      if (_highlightSkip[iv]) continue;  // let the highlight diamond own this point
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
      // Size and opacity tuned down from 9/0.9 to 6/0.7 so the rings
      // don't visually dominate a dense scatter. Symbol, hoverinfo,
      // text, and line.color are unchanged -- past hover bugs make
      // those the no-touch zone; sizing alone doesn't affect routing.
      traces.push({
        name: 'Yours - other', x: ownX, y: ownY, text: ownText,
        mode: 'markers', type: 'scattergl', hoverinfo: 'text',
        marker: {
          size: 6, color: '#cccccc', symbol: 'circle-open',
          opacity: 0.7, line: { width: 1, color: '#cccccc' }
        },
        hoverlabel: { bordercolor: '#cccccc' }
      });
    }
    if (qualX.length > 0) {
      // Notable ring: size 13 -> 9, line width 2 -> 1.5. Still larger
      // and fuller-opacity than "other" so the "worth noticing" visual
      // hierarchy is preserved.
      traces.push({
        name: 'Yours - notable', x: qualX, y: qualY, text: qualText,
        mode: 'markers', type: 'scattergl', hoverinfo: 'text',
        marker: {
          size: 9, color: '#ffffff', symbol: 'circle-open',
          opacity: 1.0, line: { width: 1.5, color: '#ffffff' }
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

  // Highlight overlay: when the user has pinned specific IVs, dim every
  // other trace to ~30% opacity and draw the highlighted points on top
  // as red diamonds. This is additive to the existing "Yours" circle
  // overlays (they keep their opacity rules, just dimmed along with
  // everything else). Circle sizing/placement intentionally untouched
  // — past bugs in that area make it a no-touch zone for features that
  // don't strictly need to change markers.
  var _hiTrace = _buildHighlightTrace();
  if (_hiTrace) {
    var DIM_FACTOR = 0.3;
    for (var _di = 0; _di < traces.length; _di++) {
      var _tm = traces[_di].marker;
      if (_tm) {
        var _orig = (_tm.opacity != null) ? _tm.opacity : 1.0;
        _tm.opacity = _orig * DIM_FACTOR;
      }
    }
    traces.push(_hiTrace);
  }

  return traces;
}

// ---- Summary table ----
// Persistent sort state across re-renders. Default: ascending Y Rank
// (== descending Y-axis metric, the prior behavior).
//   col: 'yrank' | 'level' | 'cp' | 'atk' | 'def' | 'hp' | 'sp' | 'yval'
//   dir: 'asc' | 'desc'
var summarySort = { col: 'yrank', dir: 'asc' };

// Per-column descriptors. defaultDir = direction picked on FIRST click;
// clicking the already-active column toggles. value(iv) returns the
// numeric sort key. label is the column header text (yval column uses
// currentYLabel at render time since the Y-axis metric is dynamic).
//
// 'mirrorCmp' and the three per-shield Δ columns are the
// XL-candy-decision helpers (docs/todo.md "XL-candy-decision tool" +
// "Personal-collection decision tool follow-ups"). mirrorCmp is
// optional (cohort-gated); the three Δ columns are always present
// when score arrays exist and always surface per-scenario splits
// regardless of the Shields dropdown, so lead/mid/closer role
// picking doesn't collapse into one number.
function _summaryColumns() {
  var hasCohort = !!(DATA.mirrorCohortAtk && DATA.mirrorCohortAtk.length > 0);
  var cols = [
    { id: 'yrank', label: 'Y Rank',  defaultDir: 'asc',  value: function(iv){ return yRanks[iv]; } },
    { id: 'ivs',   label: 'IVs',     defaultDir: null,   value: null },
    { id: 'level', label: 'Level',   defaultDir: 'desc', value: function(iv){ return DATA.ivLv[iv]; } },
    { id: 'cp',    label: 'CP',      defaultDir: 'desc', value: function(iv){ return DATA.ivCp[iv]; } },
    { id: 'atk',   label: 'Atk',     defaultDir: 'desc', value: function(iv){ return DATA.ivAtk[iv]; } },
    { id: 'def',   label: 'Def',     defaultDir: 'desc', value: function(iv){ return DATA.ivDef[iv]; } },
    { id: 'hp',    label: 'HP',      defaultDir: 'desc', value: function(iv){ return DATA.ivHp[iv]; } },
    { id: 'sp',    label: 'SP Rank', defaultDir: 'asc',  value: function(iv){ return DATA.spRanks[iv]; } },
    { id: 'yval',  label: null,      defaultDir: 'desc', value: function(iv){ return yValues[iv]; } },
    { id: 'd0',    label: '0v0 Δ',   defaultDir: 'desc', value: function(iv){ return _computePerShieldScoreDelta(iv, 0); },
      help: HELP_PER_SHIELD_DELTA },
    { id: 'd1',    label: '1v1 Δ',   defaultDir: 'desc', value: function(iv){ return _computePerShieldScoreDelta(iv, 1); },
      help: HELP_PER_SHIELD_DELTA },
    { id: 'd2',    label: '2v2 Δ',   defaultDir: 'desc', value: function(iv){ return _computePerShieldScoreDelta(iv, 2); },
      help: HELP_PER_SHIELD_DELTA },
    { id: 'topMirrorCmp',  label: 'Top-Mirror CMP %', defaultDir: 'desc', value: function(iv){ return _computeTopMirrorCmpPct(iv); },
      help: HELP_TOP_MIRROR_CMP },
    { id: 'matchupsKept',  label: 'Matchups Kept',    defaultDir: 'desc', value: function(iv){ return _computeMatchupsKept(iv); },
      help: HELP_MATCHUPS_KEPT },
  ];
  if (hasCohort) {
    cols.push({ id: 'mirrorCmp', label: 'Mirror Slayer CMP %', defaultDir: 'desc',
                value: function(iv){ return _computeMirrorCmpPct(iv); },
                help: HELP_MIRROR_SLAYER_CMP });
  }
  // 'tier' deliberately not sortable: most IVs have tier === -1.
  cols.push({ id: 'tier',  label: 'Tier',    defaultDir: null,   value: null });
  return cols;
}

// Fraction of the Nash-converged mirror-slayer cohort (DATA.mirrorCohortAtk,
// sorted ascending) whose atk this IV at least TIES. Returns a percentage
// in [0, 100]. Sorted input + linear scan keeps this fast enough to call
// per-row on every sort (cohorts are typically <=30 mons). Returns NaN
// when no cohort is available so the sort comparator keeps those IVs at
// the end.
//
// Both sides are rounded to 2dp (the dive's display precision) before the
// compare so float drift doesn't lie. Without this, Tinkaton UL's cohort
// atk of 142.8509983 would beat the max-atk IV's display atk of 142.85 by
// 0.001 and return 0% for every IV in the grid -- a numeric, not semantic,
// difference. Ties count as beating since PvP CMP at exactly-equal atk
// resolves on move priority or a coin flip, not a guaranteed loss.
function _computeMirrorCmpPct(iv) {
  var cohort = DATA.mirrorCohortAtk;
  if (!cohort || cohort.length === 0) return NaN;
  var myAtk = DATA.ivAtk[iv];
  if (!isFinite(myAtk)) return NaN;
  var myAtkR = Math.round(myAtk * 100) / 100;
  var beaten = 0;
  for (var i = 0; i < cohort.length; i++) {
    var cR = Math.round(cohort[i] * 100) / 100;
    if (cR <= myAtkR) beaten++;
    else break;  // sorted ascending; stop at first strictly greater
  }
  return (beaten / cohort.length) * 100;
}

// Top-Mirror CMP %: fraction of the top-N same-species IVs in THIS dive
// (ranked by the active yMode's battle score) whose atk this IV at least
// ties. Unlike Mirror Slayer CMP % — which uses the Nash-converged
// slayer cohort and can collapse to a single atk value — Top-Mirror
// builds the cohort from IVs likely to show up on ladder, so the metric
// returns a meaningful 0-100 spread. Excludes the focal IV itself.
// Rounds both sides to 2dp and counts ties as beats, same as
// _computeMirrorCmpPct, so float drift doesn't lie.
var TOP_MIRROR_N = 50;
// Build the top-N-by-yRank same-species atk cohort once per view.
// Focal IV IS included in the cohort: self-compare ties (beats) at
// the ties-as-beat rule, so the metric reads "of the top-50 realistic
// mirrors (yourself among them), what fraction do you CMP." Stable
// denominator, no per-row exclusion bookkeeping.
function _buildTopMirrorCohort() {
  var want = TOP_MIRROR_N;
  var byRank = new Array(want);
  for (var i = 0; i < want; i++) byRank[i] = -1;
  for (var iv = 0; iv < nIvs; iv++) {
    var r = yRanks[iv];
    if (r >= 1 && r <= want) byRank[r - 1] = iv;
  }
  var atks = [];
  for (var k = 0; k < want; k++) {
    var ci = byRank[k];
    if (ci < 0) continue;
    if (!isFinite(yValues[ci])) continue;
    var a = DATA.ivAtk[ci];
    if (!isFinite(a)) continue;
    atks.push(Math.round(a * 100) / 100);
  }
  atks.sort(function(x, y){ return x - y; });  // asc for early-break scan
  return atks;
}
function _computeTopMirrorCmpPct(iv) {
  var myAtk = DATA.ivAtk[iv];
  if (!isFinite(myAtk)) return NaN;
  if (_topMirrorCohortAtks === null) _topMirrorCohortAtks = _buildTopMirrorCohort();
  var cohort = _topMirrorCohortAtks;
  if (cohort.length === 0) return NaN;
  var myAtkR = Math.round(myAtk * 100) / 100;
  var beaten = 0;
  for (var j = 0; j < cohort.length; j++) {
    if (cohort[j] <= myAtkR) beaten++;
    else break;  // sorted ascending
  }
  return (beaten / cohort.length) * 100;
}

// Matchups Kept: expected number of non-mirror opponents this IV
// would beat, sampling scenarios uniformly from the selected shield
// combos. Per opponent, credit = (scenarios won) / nSel; summed over
// opponents. Float-valued, denominator stays at nO - len(mirrorIdxs).
//
// For nSel = 1 (user picked a single shield scenario), credit is
// exactly {0, 1} and the sum reduces to the integer count of wins.
// For nSel > 1, the fractional credits give finer discrimination on
// top-tier species where nearly every IV wins the same set of core
// opponents -- previous integer thresholds (avg >= 500, then
// majority-of-scenarios) compressed Tinkaton UL to 5-7 unique values
// across 4096 IVs, which is too flat to distinguish among top picks.
// Fractional credit preserves the shield-scenario variance structure
// that those thresholds discarded.
//
// Uses the active oppIvMode score source (pvpoke / rank1), or pvpoke
// as a fallback when the active yMode is sparse (winsMirror).
function _computeMatchupsKept(iv) {
  var mirrorSet = {};
  var mirrorIdxs = DATA.mirrorOppIdxs || [];
  for (var mi = 0; mi < mirrorIdxs.length; mi++) mirrorSet[mirrorIdxs[mi]] = true;
  // Pick score source: active oppIvMode normally, pvpoke in sparse
  // winsMirror mode (slayer-only yMode decouples from a real score).
  var mode = state.yAxisMode || 'avgScore';
  var src = (mode === 'winsMirror') ? 'pvpoke' : state.oppIvMode;
  var scores = getScores(state.movesetIdx, src);
  if (!scores) return NaN;
  var sis = getActiveScenarioIndices();
  var nSel = sis.length;
  var selSet = selectedOppSet();  // null == all opponents; honor the filter
  var credit = 0;
  for (var oi = 0; oi < nO; oi++) {
    if (mirrorSet[oi]) continue;
    if (selSet && !selSet[oi]) continue;  // opponent filtered out
    var sceneWins = 0;
    for (var k = 0; k < nSel; k++) {
      if (scores[iv * nS * nO + sis[k] * nO + oi] > 500) sceneWins++;  // 500=tie (PvPoke)
    }
    credit += sceneWins / nSel;
  }
  return credit;
}

// Denominator for Matchups Kept display ("K/M"): non-mirror opponents that
// are currently shown. Under the opponent filter this shrinks to the selected
// non-mirror subset so K/M stays a true "of the ones you're looking at".
function _matchupsKeptDenom() {
  var mirrorIdxs = DATA.mirrorOppIdxs || [];
  var mirrorSet = {};
  for (var mi = 0; mi < mirrorIdxs.length; mi++) mirrorSet[mirrorIdxs[mi]] = true;
  var selSet = selectedOppSet();  // null == all opponents
  var d = 0;
  for (var oi = 0; oi < nO; oi++) {
    if (mirrorSet[oi]) continue;
    if (selSet && !selSet[oi]) continue;
    d++;
  }
  return d;
}

// Per-shield Score Δ helpers. Each IV gets one Δ per even-shield
// scenario (0v0 / 1v1 / 2v2); values are avg battle score across
// opponents at that specific scenario minus the rank-1 IV's avg at
// the same scenario. Unlike the former dropdown-reactive single Δ,
// these three columns always surface the per-scenario split so a
// reader can pick an IV for lead (~2v2-weighted), mid (~1v1) or
// closer (~0v0) role regardless of what the Shields dropdown is
// set to. Reacts to Opp-IVs + Bait (via scoreMode); frozen on the
// Shields axis.
//
// Cached per (movesetIdx, scoreMode) so dropdown shuffles don't
// rebuild the nIvs-length avg arrays on every sort.
var _perShieldCacheKey = null;
var _perShieldCache = {};  // shieldCount -> { avgByIv, rank1Score }
var _perShieldScenarioIdxCache = null;

function _perShieldScenarioIdx(shields) {
  // Find the scenarios index where scenarios[si] === [shields, shields].
  // Cache the full (0v0, 1v1, 2v2) mapping on first call.
  if (_perShieldScenarioIdxCache === null) {
    _perShieldScenarioIdxCache = { 0: -1, 1: -1, 2: -1 };
    var scs = DATA.scenarios || [];
    for (var si = 0; si < scs.length; si++) {
      var sc = scs[si];
      if (sc[0] === sc[1] && sc[0] >= 0 && sc[0] <= 2) {
        _perShieldScenarioIdxCache[sc[0]] = si;
      }
    }
  }
  var idx = _perShieldScenarioIdxCache[shields];
  return (idx === undefined) ? -1 : idx;
}

function _ensurePerShieldBaselines(mi) {
  // scoreMode tracks the y-axis mode / oppIvMode the same way
  // computeYValues does, so the Δ numbers match the "Score" column
  // semantically (avgScore vs winsPvpoke vs winsRank1 all key off
  // different score arrays).
  var mode = state.yAxisMode || 'avgScore';
  var scoreMode;
  if (mode === 'winsPvpoke') scoreMode = 'pvpoke';
  else if (mode === 'winsRank1') scoreMode = 'rank1';
  else scoreMode = state.oppIvMode;  // 'avgScore' follows the Opp-IV/Bait dropdown
  // Cache key includes the opponent-mask signature so a selection change
  // invalidates the per-shield baselines (they average over opponents).
  var key = mi + '|' + scoreMode + '|' + oppMaskSig();
  if (key === _perShieldCacheKey) return;
  _perShieldCacheKey = key;
  _perShieldCache = {};
  var scores = getScores(mi, scoreMode);
  if (!scores) return;
  var selSet = selectedOppSet();  // null == all opponents; honor the filter
  var oppDen = selSet ? _oppSelCount() : nO;
  var targets = [0, 1, 2];
  for (var t = 0; t < targets.length; t++) {
    var shields = targets[t];
    var si = _perShieldScenarioIdx(shields);
    if (si < 0) continue;
    var avgByIv = new Float64Array(nIvs);
    var bestScore = -Infinity;
    for (var iv = 0; iv < nIvs; iv++) {
      var base = iv * nS * nO + si * nO;
      var sum = 0;
      for (var oi = 0; oi < nO; oi++) {
        if (selSet && !selSet[oi]) continue;  // opponent filtered out
        sum += scores[base + oi];
      }
      var a = sum / oppDen;
      avgByIv[iv] = a;
      if (a > bestScore) bestScore = a;
    }
    _perShieldCache[shields] = { avgByIv: avgByIv, rank1Score: bestScore };
  }
}

function _computePerShieldScoreDelta(iv, shields) {
  _ensurePerShieldBaselines(state.movesetIdx);
  var b = _perShieldCache[shields];
  if (!b) return NaN;
  var my = b.avgByIv[iv];
  if (!isFinite(my)) return NaN;
  return my - b.rank1Score;
}

function _summarySortClick(colId) {
  var cols = _summaryColumns();
  var col = null;
  for (var i = 0; i < cols.length; i++) if (cols[i].id === colId) { col = cols[i]; break; }
  if (!col || !col.defaultDir) return;  // unsortable column
  if (summarySort.col === colId) {
    summarySort.dir = (summarySort.dir === 'asc') ? 'desc' : 'asc';
  } else {
    summarySort.col = colId;
    summarySort.dir = col.defaultDir;
  }
  updateSummaryTable();
}

function updateSummaryTable() {
  var nSel = document.getElementById('summary-n-sel');
  var N = nSel ? parseInt(nSel.value, 10) : 10;
  if (!isFinite(N) || N <= 0) N = 10;

  var cols = _summaryColumns();
  var hasTiers = tierNames.length > 0;

  // Resolve active sort column.
  var activeCol = null;
  for (var i = 0; i < cols.length; i++) if (cols[i].id === summarySort.col) { activeCol = cols[i]; break; }
  if (!activeCol || !activeCol.value) {
    summarySort.col = 'yrank'; summarySort.dir = 'asc';
    activeCol = cols[0];
  }

  // Comparator. NaN-tolerant: NaN values sort to the end regardless of dir.
  var sign = (summarySort.dir === 'asc') ? 1 : -1;
  var getv = activeCol.value;
  var cmp = function(a, b) {
    var va = getv(a), vb = getv(b);
    var na = isNaN(va), nb = isNaN(vb);
    if (na && nb) return 0;
    if (na) return 1;
    if (nb) return -1;
    return sign * (va - vb);
  };

  var hasCohort = !!(DATA.mirrorCohortAtk && DATA.mirrorCohortAtk.length > 0);

  var indices = [];
  for (var k = 0; k < nIvs; k++) indices.push(k);
  indices.sort(cmp);

  // Row-set: union of top-N by the active sort column AND (when a
  // Mirror-CMP cohort is available AND the active sort isn't already
  // Mirror CMP %) top-N by Mirror CMP %. Surfaces IVs picked
  // specifically for CMP coverage -- those lose the Y Rank ranking
  // and are invisible under the default "top 10 by battle score"
  // cut, which is the gap the XL-candy-decision tool closes. The
  // final row-set is re-sorted by the active column for stable
  // display order.
  var seen = {};
  var unionList = [];
  function _addIfRoom(iv) {
    if (seen[iv]) return false;
    // Respect sparse-mode NaN guard when the active sort is a
    // y-value-based column (e.g. winsMirror).
    if (currentYIsSparse &&
        (summarySort.col === 'yrank' || summarySort.col === 'yval') &&
        !isFinite(yValues[iv])) {
      return false;
    }
    seen[iv] = true;
    unionList.push(iv);
    return true;
  }
  // Primary bucket: top-N by the active sort.
  for (var pi = 0, added = 0; pi < indices.length && added < N; pi++) {
    if (_addIfRoom(indices[pi])) added++;
  }
  // Secondary bucket: top-N by Mirror CMP %, skipped when the
  // cohort is absent or the active sort already IS Mirror CMP % (so
  // it's redundant). Same per-bucket cap as the primary bucket.
  if (hasCohort && summarySort.col !== 'mirrorCmp') {
    var cmpIdx = [];
    for (var k3 = 0; k3 < nIvs; k3++) cmpIdx.push(k3);
    cmpIdx.sort(function(a, b) {
      var va = _computeMirrorCmpPct(a), vb = _computeMirrorCmpPct(b);
      var na = isNaN(va), nb = isNaN(vb);
      if (na && nb) return 0;
      if (na) return 1;
      if (nb) return -1;
      return vb - va;  // descending
    });
    for (var pi2 = 0, added2 = 0;
         pi2 < cmpIdx.length && added2 < N;
         pi2++) {
      // Stop once we hit CMP=0 (or NaN). Those IVs beat nothing in the
      // cohort, so they are not on the tradeoff frontier — adding them
      // just fills the union with low-atk noise when the cohort's atk
      // range exceeds most IVs' atk. cmpIdx is sorted desc, so seeing
      // zero means every remaining IV is also zero.
      var _cmpVal = _computeMirrorCmpPct(cmpIdx[pi2]);
      if (!isFinite(_cmpVal) || _cmpVal <= 0) break;
      if (_addIfRoom(cmpIdx[pi2])) added2++;
    }
  }
  // Re-sort the union by the active column so the display order
  // matches "click column header -> sort direction."
  unionList.sort(cmp);
  var top = unionList;

  var arrow = (summarySort.dir === 'asc') ? ' \u25B2' : ' \u25BC';

  // About-these-metrics box: explains the per-shield Δ trio plus the
  // mirror-adjacent columns (Top-Mirror CMP %, Matchups Kept, Mirror
  // Slayer CMP %). Collapsed by default so regulars are not slowed
  // down; sits above the table so new readers see it adjacent to the
  // headers.
  var h = '<details style="margin:0 0 8px 0;background:var(--surface-2);border:1px solid var(--border);border-radius:4px;padding:6px 10px">'
    + '<summary style="cursor:pointer;color:var(--text);font-weight:600">About these metrics (0v0 / 1v1 / 2v2 Δ, Top-Mirror CMP %, Matchups Kept, Mirror Slayer CMP %)</summary>'
    + '<div style="margin-top:8px;font-size:12px;line-height:1.5;color:var(--text)">'
    + '<p><b>0v0 Δ / 1v1 Δ / 2v2 Δ.</b> Per-even-shield signed avg-score delta vs the best IV in that specific scenario. These three columns are <em>frozen on the Shields axis</em> so all three show regardless of what the Shields dropdown is set to; they do react to Opp-IVs + Bait. Useful for role-specific IV picking: leads weight 2v2 Δ, closers weight 0v0 Δ, mid picks weight 1v1 Δ. Positive = beats the best IV in that scenario (rare; the best IV has 0), negative = trades score for something else (usually atk or bulk).</p>'
    + '<p>The next three columns all ask "how well does this IV compete in the mirror (same-species) matchup," but they answer it from different angles. Read them together, not individually.</p>'
    + '<p><b>Top-Mirror CMP %.</b> Of the top 50 IVs of this species in THIS dive (ranked by the active battle-score column), what fraction does this IV at least tie on attack? This is the "realistic ladder mirror" metric: your cohort is the IVs actually likely to appear on ladder, spanning a range of attack values, so the result spreads meaningfully from 0 to 100. The focal IV is counted in its own cohort, so the denominator stays at 50.</p>'
    + '<p><b>Matchups Kept.</b> Expected number of non-mirror opponents this IV beats, sampling shield scenarios uniformly. Per opponent, credit = (scenarios won / total scenarios), summed across all non-mirror opponents; the denominator is M = nOpponents minus the mirror. When you\'ve picked a single shield scenario, the number is an integer (you win each matchup or you don\'t). When averaging across all shield combinations, it is fractional (e.g. 34.2 / 59): two IVs that beat the same 30 opponents but under different shield-combination profiles rank differently, so the column discriminates even among top candidates. The mirror opponent is excluded because Top-Mirror CMP % and Mirror Slayer CMP % already cover the mirror axis.</p>'
    + '<p><b>Mirror Slayer CMP %.</b> Same atk-comparison idea as Top-Mirror, but against the Nash-converged mirror slayer cohort produced by <code>--mirror-slayer</code>. This cohort often collapses to a single attack value when one corner of the IV grid dominates mirror wins, so the column tends to read 0 or 100 for most rows. It is the niche "build expressly to beat other slayer-optimal builds" metric, not a general-purpose mirror target, and only appears when slayer iteration was requested on this dive.</p>'
    + '<p><b>Reading the tradeoff.</b> High Top-Mirror CMP % at low Matchups Kept is an overfit slayer build: you out-CMP your mirror peers but give up non-mirror matchups to do it. High on both is the sweet spot, the region a human tuner typically picks from. A high Mirror Slayer CMP % with a low Top-Mirror CMP % means you are optimizing for the Nash corner at the cost of the realistic ladder cohort.</p>'
    + '<p><b>When to invest.</b> When you expect the mirror to show up often on the ladder (Tinkaton UL, Corviknight GL, common CD species in the weeks after their event), sort by Top-Mirror CMP % to see which IVs are worth an XL-candy investment, an ETM, or a targeted trade. When the mirror is rare in your meta, Matchups Kept carries more weight and Top-Mirror CMP % is mostly informational.</p>'
    + '</div></details>';
  h += '<table>';
  h += '<tr>';
  for (var ci = 0; ci < cols.length; ci++) {
    var c = cols[ci];
    if (c.id === 'tier' && !hasTiers) continue;
    var label = (c.id === 'yval') ? currentYLabel : c.label;
    var sortable = !!c.defaultDir;
    var isActive = (summarySort.col === c.id);
    var content = label + (isActive ? arrow : '');
    // Header tooltip: column-specific help text when the column
    // declares one, or the sort hint otherwise.
    var tipBase = c.help ? c.help : (sortable ? 'Click to sort' : '');
    var tip = tipBase.replace(/"/g, '&quot;');
    if (sortable) {
      h += '<th style="cursor:pointer;user-select:none" onclick="_summarySortClick(\'' + c.id + '\')" title="' + tip + '">' + content + '</th>';
    } else if (tip) {
      h += '<th title="' + tip + '">' + content + '</th>';
    } else {
      h += '<th>' + content + '</th>';
    }
  }
  h += '</tr>';

  for (var k2 = 0; k2 < top.length; k2++) {
    var iv = top[k2];
    // Skip IVs with NaN y-values when sorting by yval/yrank in a sparse
    // Y-axis mode (e.g. winsMirror).
    if (currentYIsSparse && (summarySort.col === 'yrank' || summarySort.col === 'yval')
        && !isFinite(yValues[iv])) continue;
    var tier = DATA.ivTiers[iv];
    h += '<tr>';
    h += '<td>#' + yRanks[iv] + '</td>';
    h += '<td>' + DATA.ivA[iv] + '/' + DATA.ivD[iv] + '/' + DATA.ivS[iv] + '</td>';
    h += '<td>' + DATA.ivLv[iv] + '</td><td>' + DATA.ivCp[iv] + '</td>';
    h += '<td>' + DATA.ivAtk[iv].toFixed(2) + '</td><td>' + DATA.ivDef[iv].toFixed(2) + '</td>';
    h += '<td>' + DATA.ivHp[iv] + '</td><td>#' + DATA.spRanks[iv] + '</td>';
    h += '<td>' + (isFinite(yValues[iv]) ? yValues[iv].toFixed(1) : '-') + '</td>';
    // Per-shield Score Δ: one cell each for 0v0 / 1v1 / 2v2, value is
    // avg score across opponents at that scenario minus the best-IV's
    // avg at the same scenario. Frozen on the Shields axis so the
    // three cells show the full lead/mid/closer split regardless of
    // the Shields dropdown selection. Green positive / red negative /
    // neutral for exact zero (best IV at that shield).
    for (var _sh = 0; _sh < 3; _sh++) {
      var _d = _computePerShieldScoreDelta(iv, _sh);
      if (isFinite(_d)) {
        var _dStr = (_d > 0 ? '+' : '') + _d.toFixed(1);
        var _dColor = (_d > 0) ? 'var(--win)' : (_d < 0 ? 'var(--loss)' : 'var(--text)');
        h += '<td style="color:' + _dColor + '">' + _dStr + '</td>';
      } else {
        h += '<td>-</td>';
      }
    }
    // Top-Mirror CMP %: same colour buckets as Mirror Slayer CMP %.
    var tmc = _computeTopMirrorCmpPct(iv);
    if (isFinite(tmc)) {
      var tmcColor = tmc >= 90 ? 'var(--win)' : (tmc >= 50 ? 'var(--notable)' : 'var(--text-muted)');
      h += '<td style="color:' + tmcColor + '">' + tmc.toFixed(0) + '%</td>';
    } else {
      h += '<td>-</td>';
    }
    // Matchups Kept: fractional expected-wins value, displayed to 1dp
    // (integer when the fractional part is exactly 0, which happens
    // in single-scenario mode where credit is {0,1} per opponent).
    // Colour by win rate: >=80% green, 50-80% yellow, <50% dim.
    var mk = _computeMatchupsKept(iv);
    if (isFinite(mk)) {
      var mkDen = _matchupsKeptDenom();
      var mkFrac = mkDen > 0 ? (mk / mkDen) : 0;
      var mkColor = mkFrac >= 0.8 ? 'var(--win)' : (mkFrac >= 0.5 ? 'var(--notable)' : 'var(--text-muted)');
      var mkStr = (Math.abs(mk - Math.round(mk)) < 1e-6) ? String(Math.round(mk)) : mk.toFixed(1);
      h += '<td style="color:' + mkColor + '">' + mkStr + '/' + mkDen + '</td>';
    } else {
      h += '<td>-</td>';
    }
    if (hasCohort) {
      var cmp = _computeMirrorCmpPct(iv);
      if (isFinite(cmp)) {
        // Colour by bucket: >=90 green (beats effectively everyone),
        // 50-90 yellow (beats most), <50 dim (beats a minority).
        var cmpColor = cmp >= 90 ? 'var(--win)' : (cmp >= 50 ? 'var(--notable)' : 'var(--text-muted)');
        h += '<td style="color:' + cmpColor + '">' + cmp.toFixed(0) + '%</td>';
      } else {
        h += '<td>-</td>';
      }
    }
    if (hasTiers) {
      if (tier >= 0) {
        h += '<td><span class="tier-badge" style="color:' + tierVars[tier] + ';background:var(--surface-2)">' + tierNames[tier] + '</span></td>';
      } else h += '<td>-</td>';
    }
    h += '</tr>';
  }
  h += '</table>';

  var activeLabel = (activeCol.id === 'yval') ? currentYLabel : activeCol.label;
  var dirWord = (summarySort.dir === 'asc') ? 'ascending' : 'descending';
  h += '<p style="font-size:11px;color:var(--text-muted);margin:4px 0 0 0">'
    + 'Top ' + N + ' IVs, sorted by <b>' + activeLabel + '</b> (' + dirWord + '). '
    + 'Click another column header to re-sort; click the active column again to reverse.'
    + '</p>';
  document.getElementById('summary').innerHTML = h;
}

// ---- Methodology ----
function updateMethodology() {
  var scenSel = document.getElementById('scenario-sel');
  var scenDesc = scenSel ? scenSel.options[scenSel.selectedIndex].text : '__SHIELD_DESC_DEFAULT__';
  var modeDesc = state.oppIvMode === 'rank1' ? 'stat-product rank 1 IVs' :
    "PvPoke\'s default IVs (the IVs pvpoke.com uses when you load a matchup)";
  var h = '<hr style="border-color:var(--border); margin-top:30px">';
  h += '<strong>Methodology</strong><br>';
  h += 'Each of the '+nIvs+' valid IV spreads is leveled to the highest level under the ';
  h += '__LEAGUE_TITLE__ League CP cap (__LEAGUE_CP_CAP__). For each IV, a battle is simulated ';
  // Under an active opponent filter the scatter / table / histograms aggregate
  // over just the shown subset, so the methodology must state K of N (not N) to
  // stay honest about what the numbers on screen actually average over.
  if (oppFilterActive()) {
    h += 'against '+_oppSelCount()+' of the '+nO+' opponents in the __OPP_DESC_ESCAPED__ pool ';
    h += '(you filtered the opponent set; the card, tiers, Top Picks and narrative above still use all '+nO+') ';
  } else {
    h += 'against each of the '+nO+' opponents in the __OPP_DESC_ESCAPED__ pool ';
  }
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
  var esel = document.getElementById('energy-sel');
  if (osel || bsel || esel) {
    var base = osel ? osel.value : (DATA.oppIvModes[0] || 'pvpoke').split(':')[0];
    var bait = bsel ? bsel.value : 'bait';
    var elead = esel ? parseInt(esel.value) : 0;
    var mode = (bait === 'nobait') ? (base + ':nobait') : base;
    if (elead > 0) mode += ':e' + elead;
    state.oppIvMode = mode;
  }
  var csel = document.getElementById('color-sel');
  if (csel) state.colorMode = csel.value;
  var ysel = document.getElementById('yaxis-sel');
  if (ysel) state.yAxisMode = ysel.value;
  var asel = document.getElementById('anchor-display-sel');
  if (asel) state.anchorDisplayMode = asel.value;
  lockedIdx = -1;

  // Swap per-moveset narrative zones
  var narDivs = document.querySelectorAll('.dd-narrative-moveset');
  for (var i = 0; i < narDivs.length; i++) {
    narDivs[i].style.display = (parseInt(narDivs[i].getAttribute('data-moveset')) === state.movesetIdx) ? 'block' : 'none';
  }

  var traces = buildTraces();
  origOpacities = traces.map(function(t) { return t.marker.opacity; });
  // Refresh the collection table so the "Gives up vs #1" column tracks the
  // y-axis / opp-IV / moveset selection (no-op when no collection is loaded).
  renderMatchesList();

  // Compute fixed axis ranges from all data
  var allX = [], allY = [];
  traces.forEach(function(t) { allX = allX.concat(t.x); allY = allY.concat(t.y); });
  var xMin = Math.min.apply(null, allX), xMax = Math.max.apply(null, allX);
  var yMin = Math.min.apply(null, allY), yMax = Math.max.apply(null, allY);
  var xPad = Math.max(1, (xMax-xMin)*0.02), yPad = Math.max(0.5, (yMax-yMin)*0.03);

  // Layout shape/annotation collectors (the retired score-gap cluster
  // overlay used to populate these; the arrays stay because the layout
  // consumes them and future overlays may too).
  var shapes = [];
  var annotations = [];

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
  updateHistograms();
}

// ---- Histograms ----
//
// PvPoke-style per-matchup battle-rating histogram. For the reference
// IV (PvPoke default or rank-1, matching the Opponent-IVs dropdown),
// bin the score against each (opponent, scenario) pair under the
// active Shields / Opp-IVs / Bait state. Shape mirrors PvPoke's
// "Overall Results" multi-battle histogram so articles can link to
// our page and readers see comparable numbers.
//
// Only the active moveset's block is visible; anchor ids per moveset
// remain so articles can deep-link to `#histogram-<slug>` and the
// page-load hook will switch the moveset dropdown to match.
var HISTO_BIN_SIZE = 50;
var HISTO_N_BINS = 20;  // 0-1000 in 50-point bins — matches PvPoke

// Viridis-ish gradient from purple (low) through red to blue (high),
// matching PvPoke's coloring instinct (losses on the red/purple side,
// wins on the blue/teal side). One color per bin center.
var HISTO_STOPS = [
  [0.00, [88,  28, 135]],  // deep purple
  [0.25, [145, 40, 140]],  // magenta
  [0.50, [180, 60, 120]],  // dusty rose (tie region)
  [0.55, [110, 90, 170]],  // transition through lavender
  [0.75, [70, 120, 185]],  // mid blue
  [1.00, [50, 175, 210]],  // teal
];
function histoBinColor(t) {
  if (!isFinite(t) || t <= 0) return 'rgb(88,28,135)';
  if (t >= 1) return 'rgb(50,175,210)';
  for (var i = 1; i < HISTO_STOPS.length; i++) {
    if (t <= HISTO_STOPS[i][0]) {
      var t0 = HISTO_STOPS[i-1][0], t1 = HISTO_STOPS[i][0];
      var c0 = HISTO_STOPS[i-1][1], c1 = HISTO_STOPS[i][1];
      var f = (t - t0) / (t1 - t0);
      return 'rgb(' +
        Math.round(c0[0] + f * (c1[0] - c0[0])) + ',' +
        Math.round(c0[1] + f * (c1[1] - c0[1])) + ',' +
        Math.round(c0[2] + f * (c1[2] - c0[2])) + ')';
    }
  }
  return 'rgb(50,175,210)';
}

// Per-matchup score list for the reference IV at moveset `mi`, active
// scenarios, active opp-IV mode (with bait suffix). One value per
// (opponent, scenario) pair. This is the "Matches" distribution
// PvPoke's histogram bins.
function collectMatchScores(mi) {
  var scores = getScores(mi, state.oppIvMode);
  if (!scores) return null;
  var refIv = (parse_oppiv_base(state.oppIvMode) === 'rank1')
    ? DATA.rank1RefIvIdx : DATA.pvpokeRefIvIdx;
  if (refIv == null || refIv < 0) {
    // Fall back to rank-1-stat-product (yRank=1 under avgScore is not
    // necessarily the scatter's reference IV, but it's a reasonable
    // default if the Python side didn't populate a ref index).
    for (var iv = 0; iv < nIvs; iv++) {
      if (DATA.spRanks[iv] === 1) { refIv = iv; break; }
    }
  }
  if (refIv == null || refIv < 0) return null;
  var sis = getActiveScenarioIndices();
  var selSet = selectedOppSet();  // null == all opponents; honor the filter
  var out = [];
  for (var k = 0; k < sis.length; k++) {
    var si = sis[k];
    var base = refIv * nS * nO + si * nO;
    for (var oi = 0; oi < nO; oi++) {
      if (selSet && !selSet[oi]) continue;  // opponent filtered out
      out.push(scores[base + oi]);
    }
  }
  return {scores: out, refIv: refIv};
}

function parse_oppiv_base(mode) {
  if (!mode) return 'pvpoke';
  var i = mode.indexOf(':');
  return i >= 0 ? mode.substring(0, i) : mode;
}

function updateHistograms() {
  var blocks = document.querySelectorAll('.dd-histogram-moveset');
  if (!blocks.length) return;
  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    var mi = parseInt(block.getAttribute('data-moveset'));
    var active = (mi === state.movesetIdx);
    block.style.display = active ? 'block' : 'none';
    if (!active) continue;
    var plotDiv = block.querySelector('.dd-histogram-plot');
    var captionDiv = block.querySelector('.dd-histogram-caption');
    if (!plotDiv) continue;
    var gathered = collectMatchScores(mi);
    if (!gathered) continue;
    var matchScores = gathered.scores;
    var counts = new Array(HISTO_N_BINS);
    for (var b0 = 0; b0 < HISTO_N_BINS; b0++) counts[b0] = 0;
    var wins = 0, losses = 0, draws = 0, sum = 0, nMatches = 0;
    for (var m = 0; m < matchScores.length; m++) {
      var v = matchScores[m];
      if (!isFinite(v)) continue;
      var bi = Math.floor(v / HISTO_BIN_SIZE);
      if (bi < 0) bi = 0;
      if (bi >= HISTO_N_BINS) bi = HISTO_N_BINS - 1;
      counts[bi]++;
      nMatches++;
      sum += v;
      if (v > 500) wins++;
      else if (v < 500) losses++;
      else draws++;
    }
    var x = [], colors = [], hov = [];
    for (var b = 0; b < HISTO_N_BINS; b++) {
      var lo = b * HISTO_BIN_SIZE, hi = lo + HISTO_BIN_SIZE;
      var mid = lo + HISTO_BIN_SIZE / 2;
      x.push(mid);
      colors.push(histoBinColor(mid / 1000));
      hov.push('Rating ' + lo + '-' + hi + ': ' + counts[b] + ' matches');
    }
    var avg = nMatches > 0 ? Math.round(sum / nMatches) : 0;
    var trace = {
      type: 'bar', x: x, y: counts,
      // hovertext (not text) keeps the labels in the tooltip only — `text`
      // would render inside the bars when Plotly auto-picks textposition.
      hovertext: hov, hoverinfo: 'text', textposition: 'none',
      marker: {color: colors, line: {width: 0}},
      width: new Array(HISTO_N_BINS).fill(HISTO_BIN_SIZE * 0.92),
    };
    var layout = {
      xaxis: {title: 'Battle Rating (Avg: ' + avg + ')',
              range: [0, 1000], tickvals: [0, 250, 500, 750, 1000],
              fixedrange: true, showgrid: false, zeroline: false},
      yaxis: {title: 'Matches', rangemode: 'tozero',
              fixedrange: true, showgrid: false, zeroline: false},
      paper_bgcolor: '#1a1a2e', plot_bgcolor: '#16213e',
      font: {color: '#e0e0e0', size: 11},
      margin: {t: 10, b: 48, l: 56, r: 16},
      bargap: 0.04,
      shapes: [{
        type: 'line', x0: 500, x1: 500,
        yref: 'paper', y0: 0, y1: 1,
        line: {color: '#e0e0e0', width: 1, dash: 'dash'},
      }],
    };
    Plotly.react(plotDiv, [trace], layout,
                 {responsive: true, displayModeBar: false});
    if (captionDiv) {
      var pct = function(n) {
        return nMatches > 0
          ? ' (' + (100 * n / nMatches).toFixed(1) + '%)'
          : '';
      };
      var refLabel = (parse_oppiv_base(state.oppIvMode) === 'rank1')
        ? 'Rank 1' : 'PvPoke default';
      var refIvStr = DATA.ivA[gathered.refIv] + '/' +
                     DATA.ivD[gathered.refIv] + '/' +
                     DATA.ivS[gathered.refIv];
      captionDiv.innerHTML =
        '<b style="color:var(--win)">Wins: ' + wins + pct(wins) + '</b> &nbsp; ' +
        '<b style="color:var(--loss)">Losses: ' + losses + pct(losses) + '</b> &nbsp; ' +
        '<b>Draws: ' + draws + pct(draws) + '</b>' +
        '<div style="font-size:11px;color:var(--text-muted);margin-top:2px">' +
        'reference IV: ' + refLabel + ' (' + refIvStr + '), ' +
        nMatches + ' total matchups' +
        '</div>';
    }
  }
}

// On first load, if the URL hash points at a histogram block, switch
// the moveset dropdown to that block's moveset before the first
// updateView() fires so the anchored block is the visible one.
function applyHistogramHash() {
  var h = (window.location.hash || '').replace(/^#/, '');
  if (!h) return;
  var block = document.getElementById(h);
  if (!block || !block.classList.contains('dd-histogram-moveset')) return;
  var mi = parseInt(block.getAttribute('data-moveset'));
  if (isNaN(mi)) return;
  var msel = document.getElementById('moveset-sel');
  if (msel) {
    msel.value = String(mi);
  }
  state.movesetIdx = mi;
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
  // Plotly's graphDiv is an EventEmitter that persists across
  // Plotly.react calls, so gd.on() accumulates listeners every time
  // updateView runs. A node-style MaxListenersExceededWarning fires
  // around the 11th updateView (default 10 + 1). One-shot guard via
  // a graphDiv property keeps these listeners at exactly one each.
  if (!gd._legendHandlersAttached) {
    gd.on('plotly_legendclick', function() { return false; });
    gd.on('plotly_legenddoubleclick', function() { return false; });
    gd._legendHandlersAttached = true;
  }
  // Generation stamp: a dropdown change can fire updateView while a
  // previous tryAttach poller is still waiting — without the stamp, two
  // pollers double-attach to the same nodes.
  var gen = (gd._legendAttachGen || 0) + 1;
  gd._legendAttachGen = gen;
  var attempts = 0;
  function tryAttach() {
    if (gd._legendAttachGen !== gen) return;   // superseded by a newer render
    var items = gd.querySelectorAll('.legend .traces');
    if (items.length === 0 && attempts < 50) { attempts++; setTimeout(tryAttach, 100); return; }
    items.forEach(function(el, idx) {
      // Plotly's d3 join REUSES legend item nodes across Plotly.react
      // calls when the trace set is unchanged (the common dropdown
      // case), so unguarded addEventListener stacked N click handlers
      // — toggling the lock N times per click made click-to-lock
      // appear broken after a few dropdown changes (2026-06-11 review,
      // W6). Per-element guard keeps exactly one set of handlers.
      if (el._ddLegendWired) { return; }
      el._ddLegendWired = true;
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
window.updateSummaryTable = updateSummaryTable;
window._summarySortClick = _summarySortClick;
// Inline onclick handlers on the collection-matches tables reach these
// via window.*; without the assignments they live inside the engine IIFE
// and the handlers throw ReferenceError.
window.toggleMatchesSection = toggleMatchesSection;
window.sortMatchesTable = sortMatchesTable;
window.copyScannerJson = copyScannerJson;
// ============================================================
// "Compare candidates" widget -- a bounded N-way side-by-side of focal IV
// spreads YOU enter, read entirely from the embedded grid (no new sims).
// ============================================================
var CMP_MAX = 7;            // hard cap on candidate spreads
// CMP_ROWS / CMP_MARGIN_MIN and the cmpVal/cmpHp/cmpScenLabel/cmpFlipPanel/
// cmpMarginPanel functions now live in the shared scripts/cmp_panels.js
// (loaded as a <script> before this engine), so the ML IV-guide pages can
// reuse the exact same panels. They read grid sizing from the global DATA.

function cmpFindIv(a, d, s) {
  for (var i = 0; i < DATA.nIvs; i++) {
    if (DATA.ivA[i] === a && DATA.ivD[i] === d && DATA.ivS[i] === s) return i;
  }
  return -1;
}
// Score grids for the active moveset/mode. `def` follows the best-buddy level
// toggle (mirrors getScoreKey): L50 grid in default view, L51 grid in best-buddy
// view. `alt` is the OTHER level -- the cross-level flip overlay (L51 when
// viewing L50 = "powering up flips this"; L50 when viewing L51 = "without
// best-buddy"). altCap names the alt level for the marker.
function cmpGrids() {
  var base = state.movesetIdx + '_' + state.oppIvMode;
  var bb = DATA.bestBuddy || {};
  var atL51 = !!DATA.ivL51 && state.levelMode === '51';
  return {
    def: SCORES[base + (atL51 ? '@51' : '')],
    alt: DATA.ivL51 ? SCORES[base + (atL51 ? '' : '@51')] : null,
    altCap: atL51 ? (bb.defaultCap || 50) : (bb.altCap || 51),
    // The alt grid is the best-buddy (powered-up) level only when we are
    // currently viewing the non-best-buddy (L50) grid; viewing L51 makes the
    // alt the powered-DOWN level. Drives the ✦ tooltip wording in cmp_panels.js.
    altIsBuddy: !atL51,
  };
}
// Post-match ENERGY grids (only present with --compare-energy). Same key
// construction as cmpGrids (incl. the level toggle); null when absent ->
// the energy annotation is silently skipped (graceful degrade).
function cmpEnergyGrids() {
  if (typeof ENERGY === 'undefined') return { def: null, alt: null };
  var base = state.movesetIdx + '_' + state.oppIvMode;
  var atL51 = !!DATA.ivL51 && state.levelMode === '51';
  return { def: ENERGY[base + (atL51 ? '@51' : '')] || null,
           alt: DATA.ivL51 ? (ENERGY[base + (atL51 ? '' : '@51')] || null) : null };
}
// cmpVal / cmpHp / cmpScenLabel are defined in the shared scripts/cmp_panels.js.

// Per-candidate summary from the active grid (follows the level toggle).
// Honors the opponent filter: wins/avg are over the selected subset so the
// Comparing-builds widget stays consistent with the scatter/table/histograms.
function cmpSummary(iv) {
  var g = cmpGrids().def, nO = DATA.nOpponents, nS = DATA.nScenarios;
  var selSet = selectedOppSet();  // null == all opponents
  var oppDen = selSet ? _oppSelCount() : nO;
  var wins = 0, tot = 0;
  for (var si = 0; si < nS; si++) for (var oi = 0; oi < nO; oi++) {
    if (selSet && !selSet[oi]) continue;  // opponent filtered out
    var v = cmpVal(g, iv, si, oi); tot += v; if (v > 500) wins++;
  }
  return { wins: wins, n: nS * oppDen, avg: tot / (nS * oppDen) };
}
// "Gives up vs #1": avg-score gap to the best battle-IV in the active grid.
// Cache key carries the mask signature so a selection change re-finds the best
// (else it would compare candidates against a full-pool best under a filter).
function cmpBestAvg() {
  var key = state.movesetIdx + state.oppIvMode + state.levelMode + oppMaskSig();
  if (cmpBestAvg._cache && cmpBestAvg._key === key) return cmpBestAvg._cache;
  var best = -1;
  for (var iv = 0; iv < DATA.nIvs; iv++) { var a = cmpSummary(iv).avg; if (a > best) best = a; }
  cmpBestAvg._cache = best; cmpBestAvg._key = key;
  return best;
}
// Mirror CMP: does this IV's attack reach the converged-cohort attack? (wins the
// simultaneous-charged tiebreak in the mirror).
function cmpMirror(iv) {
  // Like-for-like: in best-buddy view use the best-buddy cohort + best-buddy
  // attack; in default view use the L50 cohort + L50 attack. DATA.ivAtk is
  // already rebound to the current level, so it pairs with the matching cohort.
  // If best-buddy view has no best-buddy cohort (e.g. slayer found none), the
  // pill is HIDDEN rather than shown against a wrong-level cohort.
  var atL51 = !!DATA.ivL51 && state.levelMode === '51';
  var cohort = atL51 ? DATA.mirrorCohortAtk51 : DATA.mirrorCohortAtk;
  if (!cohort || !cohort.length) return null;
  return DATA.ivAtk[iv] >= cohort[0] - 1e-6;
}
function cmpAnchors(iv) {
  var v = DATA.anchorClearByIv && DATA.anchorClearByIv[String(iv)];
  return v ? v.length : 0;
}

function cmpClear() { state.compareCandidates = []; cmpRender(); }
window.cmpClear = cmpClear;

function cmpAdd() {
  var a = parseInt(document.getElementById('cmp-a').value, 10);
  var d = parseInt(document.getElementById('cmp-d').value, 10);
  var s = parseInt(document.getElementById('cmp-s').value, 10);
  function ok(x) { return x >= 0 && x <= 15; }
  if (!(ok(a) && ok(d) && ok(s))) { cmpStatus('Enter Atk/Def/HP 0-15', 'var(--loss)'); return; }
  if (state.compareCandidates.length >= CMP_MAX) {
    cmpStatus('Max ' + CMP_MAX + ' -- remove one to add another', 'var(--notable)'); return;
  }
  for (var i = 0; i < state.compareCandidates.length; i++) {
    var c = state.compareCandidates[i];
    if (c.a === a && c.d === d && c.s === s) { cmpStatus('Already added', 'var(--notable)'); return; }
  }
  // Level field retired with the optional level input (dive grids score at
  // cap level only -- no arbitrary-level re-sim on the dive side); kept as
  // null so the cmpRender Power-up row stays a guarded no-op.
  state.compareCandidates.push({ a: a, d: d, s: s, level: null });
  cmpStatus('', 'var(--text-muted)');
  cmpRender();
}
window.cmpAdd = cmpAdd;
function cmpStatus(t, c) {
  var el = document.getElementById('cmp-status'); if (el) { el.textContent = t; el.style.color = c; }
}

function cmpRender() {
  var host = document.getElementById('cmp-body');
  var sec = document.getElementById('cmp-section');
  if (!host) return;
  var cands = state.compareCandidates;
  // Width breaks out toward full-bleed only as candidates accumulate.
  if (sec) sec.classList.toggle('cmp-wide', cands.length >= 4);
  var capEl = document.getElementById('cmp-cap');
  if (capEl) capEl.textContent = cands.length + ' / ' + CMP_MAX + ' added' +
    (cands.length >= CMP_MAX ? ' (full)' : '');
  if (cands.length === 0) {
    host.innerHTML = '<p class="cmp-empty">Add up to ' + CMP_MAX +
      ' of your IV spreads above to compare them side by side -- wins, mirror, ' +
      'and the close calls that actually decide the build.</p>';
    return;
  }
  var grids = cmpGrids(), nO = DATA.nOpponents, nS = DATA.nScenarios;
  // Resolve each candidate to a grid index (off-grid -> no battle data).
  var rows = cands.map(function(c) {
    var iv = cmpFindIv(c.a, c.d, c.s);
    return { c: c, iv: iv,
             sum: iv >= 0 ? cmpSummary(iv) : null };
  });
  var bestAvg = cmpBestAvg();

  // ---- candidate cards ----
  var h = '<div class="cmp-cards">';
  rows.forEach(function(r) {
    var c = r.c, iv = r.iv;
    var ivs = c.a + '/' + c.d + '/' + c.s;
    h += '<div class="cmp-card">';
    h += '<div class="cmp-iv">' + ivs + '<button class="cmp-x" title="remove" ' +
         'onclick="cmpRemove(' + c.a + ',' + c.d + ',' + c.s + ')">&times;</button></div>';
    if (iv < 0) { h += '<div class="cmp-sub">not in this dive’s simulated set</div></div>'; return; }
    h += '<div class="cmp-sub">' + DATA.ivAtk[iv].toFixed(1) + ' atk / ' +
         DATA.ivDef[iv].toFixed(1) + ' def / ' + DATA.ivHp[iv] + ' hp &middot; CP ' +
         DATA.ivCp[iv] + ' &middot; SP #' + DATA.spRanks[iv] + '</div>';
    function xrow(k, v) { return '<div class="cmp-row"><span>' + k + '</span><b>' + v + '</b></div>'; }
    if (c.level != null && DATA.ivLv[iv] != null) {
      var dlt = DATA.ivLv[iv] - c.level;
      var pu = dlt <= 0 ? '✓ maxed'
        : '+' + ((Math.abs(dlt - Math.round(dlt)) < 1e-6) ? Math.round(dlt) : dlt.toFixed(1)) + ' lv';
      h += xrow('Power-up', pu);
    }
    h += xrow('Wins (all shields)', r.sum.wins + ' / ' + r.sum.n);
    var gu = Math.round(bestAvg - r.sum.avg);
    var guc = gu <= 5 ? 'cmp-good' : (gu <= 20 ? 'cmp-mid' : 'cmp-bad');
    h += '<div class="cmp-row"><span>Gives up vs #1</span><b class="' + guc + '">' + gu + '</b></div>';
    h += xrow('Anchors cleared', cmpAnchors(iv) + ' opp');
    var mir = cmpMirror(iv);
    if (mir !== null) h += '<div class="cmp-pill ' + (mir ? '' : 'cmp-pill-lose') + '">' +
      (mir ? 'Wins mirror CMP' : 'Loses mirror CMP') + '</div>';
    h += '</div>';
  });
  h += '</div>';

  var live = rows.filter(function(r) { return r.iv >= 0; });
  if (live.length >= 2) {
    h += cmpFlipPanel(live, grids);
    // Energy context is read from the engine's state here; cmp_panels.js takes
    // it as a parameter so the guide can supply its own packed energy grids.
    h += cmpMarginPanel(live, grids,
      { eg: cmpEnergyGrids(), em: (DATA.movesets[state.movesetIdx] || {}).energyMoves });
  }
  host.innerHTML = h;
}

function cmpRemove(a, d, s) {
  state.compareCandidates = state.compareCandidates.filter(function(c) {
    return !(c.a === a && c.d === d && c.s === s);
  });
  cmpRender();
}
window.cmpRemove = cmpRemove;
// Exposed so the async ENERGY decoder (in the page's appended JS) can trigger a
// re-render once leftover-energy data is ready, if candidates are already shown.
window.cmpRender = cmpRender;

function cmpWireHandlers() {
  var add = document.getElementById('cmp-add');
  if (add) add.addEventListener('click', cmpAdd);
  cmpRender();
}

window.applyHighlight = applyHighlight;
window.clearHighlight = clearHighlight;
applyHistogramHash();
// Seed the opponent-filter panel (all checked) before the first render so
// state.selectedOpps exists; harmless no-op when the panel isn't in the page.
initOppFilter();
updateView();
// Capture the best-buddy L50/L51 grids + prose templates and apply the
// default display level (no-op unless the dive carried an L51 grid).
_initBestBuddy();
// Hook up the collection panel handlers now that updateView has run
// once (nIvs, DATA, etc. are all in scope). Safe even if DATA.collection
// is null — the wire function bails early in that case.
wireCollectionHandlers();
// "Compare candidates" widget (renders empty until you add a spread).
cmpWireHandlers();
// ---------------------------------------------------------------------------
// Matchup-fingerprint cluster panels (Dive Analysis > Matchup clusters).
// The section HTML + per-IV cluster labels are baked server-side by
// scripts/deep_dive_matchup_clusters.py; this code only draws the three
// stat-plane scattergl panels (atk/def, atk/hp, def/hp) colored by cluster.
// Panels render lazily on the first open of the enclosing <details> --
// Plotly sizes to zero inside a closed/hidden container -- and re-render
// after a best-buddy prose swap (the swap replaces the section's DOM, which
// clears the data-mc-rendered flag; DATA.ivAtk/ivDef/ivHp are already
// swapped to the matching level by setBestBuddyLevel, so coordinates and
// labels stay consistent).
function _mcPayload(root) {
  var s = root.querySelector('script.dd-mc-data');
  if (!s) return null;
  try { return JSON.parse(s.textContent); } catch (e) { return null; }
}

function _mcRenderRoot(root) {
  var payload = _mcPayload(root);
  if (!payload) return;
  var sel = root.querySelector('select.dd-mc-scen');
  var scen = sel ? sel.value : payload['default'];
  var sc = payload.scens[scen];
  var panels = root.querySelectorAll('.dd-mc-panel');
  var panelBox = root.querySelector('.dd-mc-panels');
  if (!sc) {
    // scenario with no robust clusters: clear stale panels and collapse
    // the container so three blank 320px boxes don't sit above the
    // "no cluster view" headline.
    panels.forEach(function(p) { Plotly.purge(p); p.innerHTML = ''; });
    if (panelBox) panelBox.style.display = 'none';
    root.setAttribute('data-mc-rendered', '1');
    return;
  }
  if (panelBox) panelBox.style.display = 'flex';
  var axes = {atk: DATA.ivAtk, def: DATA.ivDef, hp: DATA.ivHp};
  var titles = {atk: 'Attack', def: 'Defense', hp: 'HP'};
  var n = sc.labels.length;
  panels.forEach(function(p) {
    var proj = (p.getAttribute('data-proj') || 'atk,def').split(',');
    var xs = axes[proj[0]], ys = axes[proj[1]];
    if (!xs || !ys) return;
    var traces = [];
    for (var c = 0; c < sc.k; c++) {
      traces.push({type: 'scattergl', mode: 'markers', x: [], y: [],
                   text: [], hoverinfo: 'text',
                   name: 'C' + c + ' (n=' + sc.sizes[c] + ')',
                   marker: {size: 4, color: payload.palette[c % payload.palette.length],
                            opacity: 0.75}});
    }
    for (var i = 0; i < n; i++) {
      var t = traces[sc.labels[i]];
      t.x.push(xs[i]);
      t.y.push(ys[i]);
      t.text.push(DATA.ivA[i] + '/' + DATA.ivD[i] + '/' + DATA.ivS[i] +
                  ' - atk ' + Number(DATA.ivAtk[i]).toFixed(1) +
                  ' def ' + Number(DATA.ivDef[i]).toFixed(1) +
                  ' hp ' + DATA.ivHp[i] + ' - C' + sc.labels[i]);
    }
    // Owned-mon overlay: your pasted collection's on-grid spreads as gold
    // stars, hover naming the mon(s) + which cluster the spread sits in.
    // SVG scatter (not gl) for the star symbol - the owned set is small.
    // Off-grid spreads are skipped, same as the main scatter overlay.
    if (state.ownedByIv) {
      var ox = [], oy = [], otxt = [];
      for (var okey in state.ownedByIv) {
        var oidx = parseInt(okey, 10);
        if (!(oidx >= 0 && oidx < n)) continue;
        var recs = state.ownedByIv[oidx];
        var onames = recs.map(function(rr) {
          // fitted-at-cap CP uniformly: the panels plot at-cap stats, and
          // CSV current-CP vs manual fitted-CP would silently mix meanings
          var cp = (rr.stats && rr.stats.cp) || '?';
          return ((rr.mon && rr.mon.name) || 'mon') + ' CP' + cp;
        }).join(', ');
        ox.push(xs[oidx]);
        oy.push(ys[oidx]);
        otxt.push('Yours: ' + onames + ' - ' +
                  DATA.ivA[oidx] + '/' + DATA.ivD[oidx] + '/' + DATA.ivS[oidx] +
                  ' - cluster C' + sc.labels[oidx]);
      }
      if (ox.length) {
        // scattergl (not svg scatter) + a tiny y-nudge: an svg star at the
        // exact coordinates of a gl cluster point loses the hover contest
        // (verified live during review: 3/24 stars hovered as the wrong
        // spread) - same mechanism as the main plot's user overlay, same
        // fix (c0e782d precedent).
        var ymin = Infinity, ymax = -Infinity;
        for (var yi = 0; yi < n; yi++) {
          if (ys[yi] < ymin) ymin = ys[yi];
          if (ys[yi] > ymax) ymax = ys[yi];
        }
        var ynudge = (ymax - ymin) * 0.0005 || 0.001;
        for (var oyi = 0; oyi < oy.length; oyi++) oy[oyi] += ynudge;
        traces.push({type: 'scattergl', mode: 'markers', x: ox, y: oy,
                     text: otxt, hoverinfo: 'text',
                     name: 'Yours (' + ox.length + ')',
                     marker: {size: 11, symbol: 'star', color: '#ffd700',
                              opacity: 1, line: {width: 1.5, color: '#000'}}});
      }
    }
    var layout = {
      xaxis: {title: titles[proj[0]], showgrid: false, zeroline: false},
      yaxis: {title: titles[proj[1]], showgrid: false, zeroline: false},
      paper_bgcolor: '#1a1a2e', plot_bgcolor: '#16213e',
      font: {color: '#e0e0e0', size: 11},
      margin: {t: 8, b: 40, l: 48, r: 8},
      showlegend: true,
      legend: {orientation: 'h', y: -0.25},
    };
    Plotly.react(p, traces, layout, {responsive: true, displayModeBar: false});
  });
  root.setAttribute('data-mc-rendered', '1');
}

// Re-render every already-drawn panel set (collection load/clear changes
// the owned-mon overlay). Unrendered roots are left alone - they pick up
// the overlay on their first lazy render.
function mcRefreshAll() {
  document.querySelectorAll('.dd-mc-root[data-mc-rendered]').forEach(function(root) {
    if (root.offsetParent !== null) {
      _mcRenderRoot(root);
    } else {
      // hidden (e.g. inside a closed details): drop the rendered flag so
      // the next toggle-open re-renders with fresh collection state
      root.removeAttribute('data-mc-rendered');
    }
  });
}

function mcSelectScenario(sel) {
  var root = sel.closest('.dd-mc-root');
  if (!root) return;
  root.querySelectorAll('.dd-mc-scen-block').forEach(function(b) {
    b.style.display = (b.getAttribute('data-scen') === sel.value) ? 'block' : 'none';
  });
  _mcRenderRoot(root);
}
window.mcSelectScenario = mcSelectScenario;

// Lazy render: <details> toggle events don't bubble but are observable with
// a capturing listener, which also survives best-buddy innerHTML swaps.
document.addEventListener('toggle', function(ev) {
  var det = ev.target;
  if (!det || !det.open || !det.querySelectorAll) return;
  det.querySelectorAll('.dd-mc-root:not([data-mc-rendered])').forEach(function(root) {
    if (root.offsetParent !== null) _mcRenderRoot(root);
  });
  // Panels rendered while hidden can carry a zero-size layout; a resize on
  // open is a cheap no-op when sizing is already right.
  det.querySelectorAll('.dd-mc-root[data-mc-rendered] .dd-mc-panel').forEach(function(p) {
    if (p.children.length && window.Plotly && Plotly.Plots) {
      try { Plotly.Plots.resize(p); } catch (e) {}
    }
  });
}, true);

// Immediate pass for the edge case where the user opened the Dive Analysis
// details while the page was still loading (before this listener existed).
document.querySelectorAll('.dd-mc-root:not([data-mc-rendered])').forEach(function(root) {
  if (root.offsetParent !== null) _mcRenderRoot(root);
});
