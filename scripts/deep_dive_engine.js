
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
  // Anchor IVs overlay rendering mode (the ring/identity hue is
  // --cat-anchors; it was a fixed cyan before the theme shim):
  //   'filled'  - per-point fill, opacity 0.65 (current default; context
  //               layer that doesn't overwhelm slayer / top-picks)
  //   'outline' - transparent fill with a --cat-anchors border ring; the band
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

// ---- Theme-aware Plotly chrome (the getComputedStyle shim) ----
//
// Plotly draws into its own SVG/WebGL canvas and cannot resolve CSS custom
// properties, so every color handed to it has to be a literal. Before this
// shim the three canvases (main scatter, rating histogram, cluster panels)
// carried a hardcoded dark-navy palette -- #1a1a2e paper / #16213e plot /
// #e0e0e0 font -- that belongs to no theme in theme.py. On a light-default
// site that is three permanently dark charts, and it is a
// palette_governance.md section-1 violation (literal palette hex outside
// _TOKENS).
//
// The fix is the shim palette_governance.md section 8 specifies: resolve the
// tokens at chart-build time off the ACTIVE [data-theme] block. THEME_FALLBACK
// is the DEFAULT_THEME resolution injected from the same theme.py _TOKENS
// values (deep_dive._THEME_FALLBACK_HEX), used only when getComputedStyle
// yields nothing -- so no code path can paint a color that is not a theme.py
// value. Resolutions are memoized; the observer at the bottom of this file
// drops the memo and re-renders whenever data-theme changes.
var THEME_FALLBACK = __THEME_FALLBACK_JS__;
var _themeVarCache = {};
function themeColor(name) {
  if (Object.prototype.hasOwnProperty.call(_themeVarCache, name)) {
    return _themeVarCache[name];
  }
  var v = '';
  try {
    v = getComputedStyle(document.documentElement)
          .getPropertyValue(name).trim();
  } catch (e) { v = ''; }
  if (!v) v = THEME_FALLBACK[name] || '';
  _themeVarCache[name] = v;
  return v;
}
// Resolve a 'var(--token)' string to the active theme's literal. Anything that
// is not a bare var() reference (a '#hex', an 'rgba(...)') passes through, so
// this is safe to wrap around any color the Python side may have baked.
var _CSS_VAR_RE = /^var\(\s*(--[A-Za-z0-9-]+)\s*\)$/;
function resolveThemeColor(c, fallback) {
  var m = (typeof c === 'string') ? c.match(_CSS_VAR_RE) : null;
  if (!m) return c;
  return themeColor(m[1]) || fallback;
}
// Tier marker color for tier index ti. tierVars[ti] is the raw 'var(--tier-N)'
// the badge uses, so resolving it here makes badge == card == marker in EVERY
// theme (before the shim, markers were pinned to the DEFAULT_THEME column).
// tierColors[ti] stays the fallback.
function tierColor(ti) { return resolveThemeColor(tierVars[ti], tierColors[ti]); }
// One chrome spec for all three canvases. Roles, not raw tokens, so a canvas
// asks for "the recessive neutral" rather than picking a token itself.
//
//   paper transparent  -- the chart's margin area inherits whatever card holds
//                         it (page --bg for #plot, --surface for the cluster
//                         panels inside .dd-section); one spec, three correct
//                         backgrounds, in all four themes.
//   plot   --surface-2 -- a plotting rectangle that reads as slightly distinct
//                         from its container in both light and dark themes.
function plotChrome() {
  return {
    paper: 'rgba(0,0,0,0)',
    plot: themeColor('--surface-2'),
    font: themeColor('--text'),
    grid: themeColor('--border-2'),
    legendBg: themeColor('--surface'),
    legendBorder: themeColor('--border-2'),
    hoverBg: themeColor('--surface-2'),
    hoverBorder: themeColor('--text-muted'),
    rule: themeColor('--text-muted'),  // reference lines (tie centerline)
    ink: themeColor('--text'),         // high-contrast neutral marks
  };
}

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
// SCORES / ENERGY grid keys. The separator and the best-buddy suffix are the
// Python bake's wire contract (deep_dive_rendering.score_key); they live here
// ONCE and every reader goes through these two functions -- pinned by
// tests/test_js_score_key_parity.py.
var SCORE_KEY_SEP = '_';
var SCORE_KEY_L51 = '@51';
// Key of a specific level's grid: atL51 picks the parallel best-buddy grid the
// dive embedded. Callers that need BOTH levels (the compare widget's
// current/alt pair) pass the flag explicitly.
function getScoreKeyAt(mi, mode, atL51) {
  return mi + SCORE_KEY_SEP + mode + (atL51 ? SCORE_KEY_L51 : '');
}
// True when the page is currently showing the best-buddy (L51) grid. The
// suffix is only ever used when an L51 grid is actually present (DATA.ivL51),
// so non-best-buddy dives are unaffected.
function atL51View() { return state.levelMode === '51' && !!DATA.ivL51; }
// Score key for the CURRENT level view.
function getScoreKey(mi, mode) { return getScoreKeyAt(mi, mode, atL51View()); }
function getScores(mi, mode) { return SCORES[getScoreKey(mi, mode)]; }

// ---- Composite mode grammar: base[:nobait][:eN][:pogodives] ----
// Mirrors deep_dive_rendering.parse_mode / parse_energy / compose_mode. These
// strings are the score-lookup keys, so a divergence lands in the silent
// fallback path and renders a different mode than the dropdowns show; the
// round trip is pinned by tests/test_js_score_key_parity.py.
function parseModeBase(mode) {
  if (!mode) return 'pvpoke';
  var i = mode.indexOf(':');
  return i >= 0 ? mode.substring(0, i) : mode;
}
function parseModeBait(mode) {
  return (String(mode || '').split(':').slice(1).indexOf('nobait') >= 0)
    ? 'nobait' : 'bait';
}
function parseModeEnergy(mode) {
  var parts = String(mode || '').split(':').slice(1);
  for (var i = 0; i < parts.length; i++) {
    if (/^e\d+$/.test(parts[i])) return parseInt(parts[i].substring(1), 10);
  }
  return 0;
}
function parseModePolicy(mode) {
  return (String(mode || '').split(':').slice(1).indexOf('pogodives') >= 0)
    ? 'pogodives' : 'pvpoke';
}
function composeMode(base, bait, energyLead, policy) {
  var mode = base;
  if (bait === 'nobait') mode += ':nobait';
  if (energyLead) mode += ':e' + energyLead;
  if (policy && policy !== 'pvpoke') mode += ':' + policy;
  return mode;
}

// ---- Shield-scenario label ----
// Baked by Python (DATA.scenarioLabels, deep_dive_rendering.scenario_label);
// never re-formed here. The '{a}v{b}' form is load-bearing -- it keys the
// matchup-cluster payload -- so the fallback exists only for a DATA blob
// predating the field.
function scenLabel(si) {
  var labels = DATA.scenarioLabels;
  if (labels && labels[si] != null) return labels[si];
  var s = DATA.scenarios[si];
  return s[0] + 'v' + s[1];
}

// ---- Level ceilings ----
// Baked from pokemon.bestbuddy_caps / MAX_CPM_LEVEL into DATA.levelCaps
// (league default cap, best-buddy alt cap, hard CPM-table ceiling). The table
// below is a fallback for a DATA blob that predates the field and is pinned to
// the Python constants by tests/test_js_wire_contract.py -- the same
// deliberate-fallback pattern as deep_dive_user_collection.js's shadow/league
// constants.
var LEVEL_CAP_FALLBACK = { default: 50.0, alt: 51.0, maxCpm: 51.0 };
function levelCap(which) {
  var caps = DATA.levelCaps || {};
  return caps[which] != null ? caps[which] : LEVEL_CAP_FALLBACK[which];
}

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
  // Round 7: the Matchup clusters section moved out of the prose block to
  // the top of the page, so it needs a host/template pair of its own. It is
  // only EMITTED on a page with no "Which one to build?" section, where the
  // clusters render as a sibling; when the section exists the clusters are
  // nested inside it and ride the section's pair instead.
  _bbInitHost('dd-bb-clusters-host', 'dd-bb-clusters-tmpl');
  // 2026-09-20: the whole section, not just the clusters inside it. Before
  // this the toggle left the headline, the answer strip, the table and the
  // figures at the league cap while the clusters nested inside them swapped
  // to L51 -- one block, two levels.
  _bbInitHost('dd-bb-wb-host', 'dd-bb-wb-tmpl');
  var dd = String((DATA.bestBuddy && DATA.bestBuddy.defaultDisplay) || 50);
  if (dd === '51') {
    var chk = document.getElementById('dd-bb-toggle');
    if (chk) chk.checked = true;
    setBestBuddyLevel('51');
  }
}

// Which <details> inside `host` the reader has OPEN, by id. The stored
// host halves are the markup as first rendered -- every <details> closed --
// so without carrying this across the swap, a Best Buddy tick collapses the
// Matchup clusters section, whose own <details> moved INSIDE this host in
// round 7, and throws away its nine minis and the reader's place on the page
// (measured in headless Chrome, 2026-09-17: detOpen true -> false,
// minis 9 -> 0).
function _bbOpenIn(host) {
  var ids = [];
  if (!host.querySelectorAll) return ids;
  host.querySelectorAll('details[id]').forEach(function(d) {
    if (d.open) ids.push(d.id);
  });
  return ids;
}

// Re-open them after the swap, and dispatch the `toggle` the lazy-draw path
// listens for: setting .open fires one asynchronously on its own, but the
// figures should be back before the reader looks, and both draw paths are
// idempotent (mcRenderPending skips a rendered root; wbRefresh redraws only
// a section that is open and on screen).
function _bbReopen(ids) {
  for (var i = 0; i < ids.length; i++) {
    var d = document.getElementById(ids[i]);
    if (!d || d.open) continue;
    d.open = true;
    try { d.dispatchEvent(new Event('toggle', {bubbles: false})); } catch (e) {}
  }
}

// ---- "Which one to build?" state across a best-buddy swap ----
// The host swap replaces the section's whole DOM with the other level's
// server-rendered markup, which comes back in its FIRST-RENDER state: every
// figure on its default tab, every Shield-scenario select on "all". The
// <details> open set is carried for every host by _bbOpenIn/_bbReopen; these
// two carry the rest, so a reader who narrowed the figure to 1v1 on the
// "Builds" tab is still there after ticking Best Buddy.
//
// The Build-criteria preset is deliberately NOT snapshotted: it lives in the
// page's controls strip, which the swap never touches. It is re-APPLIED to
// the fresh markup instead (wbApplyPreset picks which server-rendered
// .wb-preset block is visible and which summary sentence the collapsed line
// carries) -- read from the one place that holds it, not copied.
function _wbSnapshot() {
  var root = _wbRoot();
  if (!root) return null;
  var sel = root.querySelector('select.wb-scen');
  var views = {};
  root.querySelectorAll('.wb-plotbox').forEach(function(b) {
    views[b.getAttribute('data-group') || ''] = _wbBoxView(b);
  });
  return { scen: sel ? sel.value : null, views: views };
}

// Re-apply it to whatever is in the host NOW. Draws nothing: the caller
// reopens the <details> straight after, and that toggle is what renders --
// so the panels are built once, already on the right tab and scenario.
function _wbRestore(snap) {
  var root = _wbRoot();
  if (!root || !snap) return;
  root.querySelectorAll('.wb-plotbox').forEach(function(box) {
    var want = snap.views[box.getAttribute('data-group') || ''];
    if (!want || want === _wbBoxView(box)) return;
    var tabs = box.querySelectorAll('.wb-tab');
    var hit = null;
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].getAttribute('data-view') === want) hit = tabs[i];
    }
    // A view this level's section does not offer leaves the box on its
    // default tab rather than on a tab with no figure behind it.
    if (!hit) return;
    box.setAttribute('data-wb-view', want);
    for (var j = 0; j < tabs.length; j++) {
      tabs[j].setAttribute('aria-selected', tabs[j] === hit ? 'true' : 'false');
    }
  });
  if (snap.scen) _wbSyncScen(root, snap.scen);
  wbApplyPreset(root);
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
    if (!host || _bbHostHTML[hid][mode] == null) continue;
    var wasOpen = _bbOpenIn(host);
    var wbSnap = (hid === 'dd-bb-wb-host') ? _wbSnapshot() : null;
    host.innerHTML = _bbHostHTML[hid][mode];
    // Before the reopen, so the toggle that reopen fires draws each panel
    // once, on the tab and scenario the reader left it on.
    if (wbSnap) _wbRestore(wbSnap);
    _bbReopen(wasOpen);
  }
  // Re-hydrate title= from DATA.tooltips on whatever we just swapped in. The
  // <template> halves carry data-t="" but never title=: the DOMContentLoaded
  // tooltip pass uses document.querySelectorAll, which does not descend into
  // <template> content, so without this every tooltip on the L51 prose/card
  // is silently missing after a toggle (and from page load when
  // defaultDisplay is 51).
  if (window.ddPopulateTooltips) window.ddPopulateTooltips();
  // The swap replaced the Matchup clusters section's DOM, so its stat-plane
  // panels and its all-scenarios mini-grid are empty divs again. Before
  // round 7 the section rode inside a collapsible that was closed by
  // default, so the toggle-open pass always got there first; now it can be
  // open across a best-buddy toggle.
  mcRenderPending();
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
  // "All (by build criteria)": the scenarios the page's Build criteria
  // preset weights. Every shipped preset weights 0 or 1, so a weighted
  // count IS a count over a subset of scenarios and the rest of this file
  // -- computeYValues, the Top-IVs table, the histograms -- needs no notion
  // of a weight at all. A page with no preset knob never reaches here.
  if (state.scenarioMode === 'wbavg') {
    var sub = (typeof wbPresetScenIndices === 'function')
            ? wbPresetScenIndices() : null;
    if (sub && sub.length) return sub;
    var all = []; for (var j=0; j<nS; j++) all.push(j); return all;
  }
  return [parseInt(state.scenarioMode)];
}

// The scatter's y-axis TITLE (not currentYLabel, which also names the hover
// line and a table column). Under Shields = "All (by build criteria)" the
// values average a SUBSET of the shield scenarios and the plot said nothing
// about which: the axis read "Avg Battle Score", identical to "All (equal
// weight)", and the only signal was the muted line in the controls strip,
// which is scrolled off by the time a reader is looking at the chart
// (2026-09-16 review). The section's own plot has always labelled its axis.
function yAxisTitle() {
  if (state.scenarioMode !== 'wbavg') return currentYLabel;
  var tag = (typeof wbPresetScenLabel === 'function')
          ? wbPresetScenLabel() : null;
  return tag ? (currentYLabel + ' (' + tag + ')') : currentYLabel;
}

// ---- Opponent filter (client-side subset) ----
//
// state.selectedOpps is a Uint8Array(nO) of 1/0 (1 = shown), or null before
// init (treated as "all shown"). state.oppMaskVersion bumps on every change so
// per-render caches keyed on it recompute. The filter masks the AGGREGATE
// views that sum over opponents -- scatter y-values, the Top-IVs table,
// histograms, Matchups Kept, the hover matchup-diff lists, the per-shield
// deltas, and the paste-box "Gives up vs #1" list -- but NOT the Python-baked
// sections (infographic card, threshold tiers, "Which one to build?",
// narrative), which are computed full-pool at bake time. The honesty banner
// names that split. It must name a surface that is still ON the page: the
// composite-score picks block was one of them until round 8 retired it, and
// for one round the banner went on pointing at a block that no longer
// existed (2026-09-17 round 8 review).
// The "Comparing builds" widget (cmpSummary / cmpBestAvg / cmpUnifiedTable)
// ALSO follows the filter -- its wins/avg/gives-up and the unified compare
// table recompute over the selected subset (Michael's call 2026-07-03), so
// every score surface on the page moves together.
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
      + 'checked. The infographic card, threshold tiers, "Which one to build?", and narrative are '
      + 'computed against the full ' + nO + '-opponent pool and do <b>not</b> react to this filter.' + snap;
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
// ---- All-scenarios small-multiples (2026-08-25) ----
// Pure per-scenario pool-average -- reads the embedded score arrays
// directly; deliberately ignores opponent filters and yAxis modes so the
// minis are a stable, simple reference view (the main plot is the rich
// one). No state is touched: toggling the grid never re-renders the page.
function computeScenarioAvgPure(mi, si) {
  var scores = getScores(mi, state.oppIvMode);
  if (!scores) return null;
  var avgs = new Float64Array(nIvs);
  for (var iv = 0; iv < nIvs; iv++) {
    var base = iv * nS * nO + si * nO, sum = 0;
    for (var oi = 0; oi < nO; oi++) sum += scores[base + oi];
    avgs[iv] = sum / nO;
  }
  return avgs;
}

// (Round 9: toggleAllScenarios / renderAllScenarios lived here -- the
// Matchup clusters section\'s own nine-mini grid. It drew the same nine
// shield scenarios on the same x axis as the "Which one to build?" grid
// directly above it, so the two are ONE grid now: _wbAllScen, parameterised
// by what is on Y and what the colour is. DRY rule D2, round 9.)
// Is `el` inside a <details> that is closed?
//
// Measured, not assumed (headless Chrome, 2026-09-17, on the round-7
// preview): a closed <details> is NOT display:none in current Chrome. Its
// contents keep layout boxes -- #allscen-grid reported offsetParent BODY and
// clientWidth 661 with its section closed, and nine minis drawn inside it
// came out 212px wide and correct. So the usual "is it on screen"
// guards (offsetParent, clientWidth) all PASS inside a closed section, and
// "don't draw until the reader opens it" has to ask the <details> itself.
// Nine 4096-point panels is not work to do at page load for a figure nobody
// has asked for yet.
function _inClosedDetails(el) {
  var d = el.closest ? el.closest('details') : null;
  while (d) {
    if (!d.open) return true;
    d = d.parentElement ? d.parentElement.closest('details') : null;
  }
  return false;
}

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
          if (isWin(scores[baseW + oiW])) c++;  // exactly 500 is a tie (PvPoke)
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
    var _prefix = state.movesetIdx + SCORE_KEY_SEP;
    var _fallback = null;
    for (var _sk in SCORES) {
      if (_sk.indexOf(_prefix) === 0 && SCORES[_sk]) {
        _fallback = _sk.substring(_prefix.length);
        // Strip the best-buddy suffix: the remainder is a MODE string that
        // goes into state.oppIvMode + the dropdowns, and getScoreKey re-adds
        // '@51' from the level toggle. Leaving it on made every subsequent
        // lookup miss (and put '@51' in the dropdown value).
        if (_fallback.length > SCORE_KEY_L51.length &&
            _fallback.indexOf(SCORE_KEY_L51, _fallback.length - SCORE_KEY_L51.length) >= 0) {
          _fallback = _fallback.substring(0, _fallback.length - SCORE_KEY_L51.length);
        }
        break;
      }
    }
    if (_fallback) {
      state.oppIvMode = _fallback;
      var _osel = document.getElementById('oppiv-sel');
      if (_osel) _osel.value = parseModeBase(_fallback);
      var _bsel = document.getElementById('bait-sel');
      if (_bsel) _bsel.value = parseModeBait(_fallback);
      var _esel = document.getElementById('energy-sel');
      if (_esel) _esel.value = String(parseModeEnergy(_fallback));
      var _psel = document.getElementById('policy-sel');
      if (_psel) _psel.value = parseModePolicy(_fallback);
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
        lines.push('  <b>CP ' + rcL.mon.cp + '</b>' +
                   (rcL.mon.level != null ? ' @ L' + rcL.mon.level : '') +
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
      var w1 = isWin(sc1), w2 = isWin(sc2);  // exactly 500 is a tie (PvPoke)
      if (w1 && !w2) gained.push(shortName(DATA.opponents[oi]));
      else if (!w1 && w2) lost.push(shortName(DATA.opponents[oi]));
    }
    var lab = scenLabel(si);
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
      : (DATA.bestBuddy.defaultCap || levelCap('default'));
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
  wbRefresh();
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
    // On-grid: use DATA.spRanks — same convention as rankLookup (unrounded
    // stat product, IV-sum-descending tiebreak), and a cheaper lookup.
    // Caveat: on a --species-iv-floor dive the grid is a SUBSET, so spRanks
    // is dense-ranked 1..n over that subset while rankLookup stays a global
    // 1..4096 rank. Those two scales interleave in the same column here.
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
      var lab = scenLabel(si);
      for (var oi = 0; oi < nO; oi++) {
        if (selSetGU && !selSetGU[oi]) continue;  // opponent filtered out
        var refW = isWin(_guScores[_guRefIv * nS * nO + si * nO + oi]);  // 500=tie
        var myW = isWin(_guScores[iv * nS * nO + si * nO + oi]);
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
  wbRefresh();
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
  // Blank level = "current level unknown": the collection pipeline then
  // uses the best under-cap level it fits for the IVs, which is what the
  // page assumes for every grid spread. The old default of 50 made every
  // manual entry on a Great League page "OVER" the cap by construction
  // (Michael, 2026-09-17).
  var levelRaw = document.getElementById('manual-level').value;
  var level = (levelRaw == null || String(levelRaw).trim() === '') ? null : parseFloat(levelRaw);
  var isShadow = document.getElementById('manual-shadow').checked;
  if (!isFinite(atkIv) || atkIv < 0 || atkIv > 15) return null;
  if (!isFinite(defIv) || defIv < 0 || defIv > 15) return null;
  if (!isFinite(staIv) || staIv < 0 || staIv > 15) return null;
  // Hard ceiling is the CPM table's top level (DATA.levelCaps.maxCpm), not the
  // league cap: a pasted/typed mon may legitimately be above the league cap.
  if (level != null && (!isFinite(level) || level < 1 || level > levelCap('maxCpm'))) return null;
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
    wbRefresh();
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
                (m.level != null ? ' L' + m.level : '');
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
    // Slug baked by Python (deep_dive_rendering.tier_slug -> DATA.tiers[i]
    // .slug), the same helper that emitted the card's anchor id. The
    // fallback covers a DATA blob predating the field; a mismatch here is a
    // silent no-op (the count never appears), which is why it is baked.
    var slug = t.slug || (t.original_name || t.name).toLowerCase()
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
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
      // #e94560 is a categorical identity hue (shared with the Spec Card
      // Spreads overlay below) and clears 3:1 on every themed plot fill, so
      // it rides through unchanged; the RING is what needed theming -- a
      // white ring vanishes on a light fill.
      size: 14, color: '#e94560', symbol: 'diamond',
      opacity: 1.0, line: { width: 2, color: themeColor('--text') }
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
        hoverlabel:{bordercolor:themeColor('--text-muted')}
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
          // The 1px ring is a SEPARATION ring (keeps adjacent tier dots from
          // fusing), so it wears the plot fill, not a fixed black that only
          // separates against a dark canvas.
          // symbol is pinned to Plotly's own default ('circle') on purpose, not
          // for looks: it is the channel that tells a tier dot apart from the
          // overlay traces whose identity hue ALIASES a tier hue
          // (--cat-anchors == --tier-1, --notable ~= --tier-8; see the two
          // DISCLOSED HUE COLLISION notes at the overlay sites). Emitting it
          // explicitly is behavior-identical and lets a test hold the channel.
          marker:{size:_markerSize, color:tierColor(ti), symbol:'circle',
                   opacity:_markerOpacity,
                   line:{width:1, color:themeColor('--surface-2')}},
          hoverlabel:{bordercolor:tierColor(ti)}
        });
      }
    }
  } else if (cm === 'cluster') {
    // --- Matchup-fingerprint cluster coloring ---
    // var (not let): read back below, after the overlay traces are pushed.
    var _clusterTraces = null;
    // Labels come from the live Matchup clusters section's inline JSON
    // payload (baked for moveset 0 + the default opp-IV mode at this
    // page's displayed level; the best-buddy swap keeps the live section
    // and DATA arrays level-consistent). On any other moveset/mode the
    // labels would not describe the displayed grid, so render neutral
    // points and say so in the legend instead of mis-coloring.
    var mcPay = _mcPayloadPage();
    var mcHasScens = !!(mcPay && mcPay.scens &&
                        Object.keys(mcPay.scens).length > 0);
    var mcOk = mcHasScens && _mcLabelsApply();
    var mcScen = null;
    if (mcOk) {
      // The Shields dropdown drives this. 'avg' (all scenarios at once) maps
      // to the payload's combined entry -- the concatenated fingerprint over
      // every non-degenerate scenario -- which is the same question the
      // averaged y-axis is asking. It used to fall through to the payload
      // default (1v1) and colored by a single scenario without saying so.
      var sis0 = getActiveScenarioIndices();
      var allKey0 = mcPay.allKey || 'all';
      // Under the weighted entry the combined partition to colour by is the
      // one for THIS preset, not the nine-scenario one.
      if (state.scenarioMode === 'wbavg') {
        var pk0 = (typeof wbActivePresetKey === 'function')
                ? wbActivePresetKey() : null;
        var mapped0 = (pk0 && mcPay.allByPreset) ? mcPay.allByPreset[pk0] : null;
        if (mapped0 && mcPay.scens[mapped0]) mcScen = mapped0;
      }
      if (mcScen) {
        // already resolved above
      } else if (state.scenarioMode === 'avg' && mcPay.scens[allKey0]) {
        mcScen = allKey0;
      } else if (sis0.length === 1) {
        var lbl0 = scenLabel(sis0[0]);
        if (mcPay.scens[lbl0]) mcScen = lbl0;
      }
      if (!mcScen && mcPay.scens[mcPay['default']]) mcScen = mcPay['default'];
      if (!mcScen) mcOk = false;
    }
    if (mcOk) {
      var msc = mcPay.scens[mcScen];
      var mcDisp = msc.display || mcScen;
      var ctr = [];
      // Legend key naming which scenario's clusters are on screen (and the
      // one-time y-axis switch, when it fired). Carries no points: the
      // cluster names below carry the rule, not the scenario.
      ctr.push({
        name: wrapLegendName('Matchup clusters: ' + mcDisp +
                             (_mcYAxisSwitched
                              ? " (y-axis switched to 'Wins vs PvPoke " +
                                "default' once: the clusters are horizontal " +
                                'bands there; switch it back any time)' : '')),
        // [null], not []: Plotly builds the legend from calcdata, and a trace
        // with NO points gets no legend entry at all -- this note key was
        // invisible on every clustered dive, and its missing entry is what
        // put every later legend item one row out of step with its trace
        // (see the C0 isolation bug below). One null point renders nothing
        // and legends normally. Verified in Plotly 2.35.2 against a page
        // built from this engine.
        x: [null], y: [null], text: [],
        mode: 'markers', type: 'scattergl', hoverinfo: 'skip',
        legendrank: 100,
        marker: {size: 6, color: themeColor('--text-muted'), opacity: 0.55}
      });
      for (var c0 = 0; c0 < msc.k; c0++) {
        // B2: the legend carries the depth-1 stat rule when the tree root
        // separates that cluster cleanly. Python emits the string (null
        // otherwise); nothing here formats a threshold.
        var mcRule0 = (msc.rules && msc.rules[c0]) ? ': ' + msc.rules[c0] : '';
        ctr.push({
          name: wrapLegendName('C' + c0 + mcRule0 +
                               ' (n=' + msc.sizes[c0] + ')'),
          x: [], y: [], text: [],
          mode: 'markers', type: 'scattergl', hoverinfo: 'text',
          // Legend position, independent of draw order: these traces are
          // pushed LAST (z-order, below) but the color mode the reader chose
          // reads first in the legend, in cluster order, as it always did.
          legendrank: 101 + c0,
          marker: {size: 4, color: mcPay.palette[c0 % mcPay.palette.length],
                   opacity: 0.75},
          hoverlabel: {bordercolor: mcPay.palette[c0 % mcPay.palette.length]}
        });
      }
      for (var civ = 0; civ < nIvs; civ++) {
        if (currentYIsSparse && !isFinite(yValues[civ])) continue;
        if (!isOwnedFilter(civ)) continue;
        var clab = msc.labels[civ];
        // +1: ctr[0] is the legend note key, so cluster c lives at c + 1.
        if (clab == null || !ctr[clab + 1]) continue;
        ctr[clab + 1].x.push(DATA.spRanks[civ]);
        ctr[clab + 1].y.push(yValues[civ]);
        ctr[clab + 1].text.push(buildHoverText(civ) +
                            '<br>Matchup cluster: C' + clab + ' (' + mcDisp + ')');
      }
      // Collected, not pushed: Plotly z-order is insertion order, and the
      // anchor / Efficient / slayer overlays are pushed further down. The
      // color mode a reader selected should own the top of the canvas, which
      // is the same reason the tier traces are appended after the overlays;
      // they are appended alongside them below.
      //
      // This is NOT what made C0 isolate to an empty plot (Michael's
      // screenshots). That was the legend/trace off-by-one above: the note
      // key carried no points, so it got no legend entry, every later legend
      // row addressed the trace BEFORE its own, and hovering "C0" brightened
      // the empty note trace and dimmed C0 to 0.03. Measured on a rendered
      // preview page in headless Chrome (7 traces, 6 legend rows, legend row
      // 4 -> trace 5). Two fixes, both kept: the null point above, and
      // _legendTraceIndex below, which reads the index Plotly itself bound to
      // the legend node instead of counting DOM position.
      _clusterTraces = [];
      for (var c1 = 0; c1 < ctr.length; c1++) {
        if (c1 === 0 || ctr[c1].x.length) _clusterTraces.push(ctr[c1]);
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
        marker: {size: 2.5, color: themeColor('--text-muted'), opacity: 0.45},
        hoverlabel: {bordercolor: themeColor('--text-muted')}
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
    // Sequential/diverging magnitude ramps (Plotly built-ins). These are NOT
    // theme-stepped: each ramp has one end that washes out against one of the
    // themed plot fills (YlOrRd's pale end on a light fill, Blues' dark end on
    // a dark fill). Authoring per-theme ramps needs new theme.py tokens --
    // deferred with the rest of the categorical-identity slice; see the
    // "Deferred, not themed" note above plotChrome's call sites.
    var cscale = (cm === 'hp') ? 'YlOrRd' : (cm === 'def') ? 'Blues' : (cm === 'atk') ? 'RdYlGn' : 'Viridis';
    traces.push({
      name:wrapLegendName('All IVs (colored by '+cLabel+')'), x:ax, y:ay, text:at,
      mode:'markers', type:'scattergl', hoverinfo:'text',
      marker:{size:3.5, color:ac, colorscale:cscale, opacity:0.6,
               colorbar:{title:cLabel, len:0.6},
               reversescale: (cm === 'atk')},
      hoverlabel:{bordercolor:themeColor('--text-muted')}
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
  // colorscale gradient -- that gold is --notable, whose theme.py comment
  // names this exact role ("slayer-overlay gold"). No tier markers are on
  // screen in stat/score modes, so sharing a hue family with --tier-8 gold
  // cannot collide here.
  function overlayFill(iv) {
    if (cm === 'threshold' && hasTiers) {
      var t = DATA.ivTiers[iv];
      if (t >= 0) return tierColor(t);
      var range = otherMax - otherMin;
      var t01 = (range > 0) ? (yValues[iv] - otherMin) / range : 0.5;
      return viridisColor(t01);
    }
    return themeColor('--notable');
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
  //
  // Overlay identity hues. Two of the four are theme tokens whose theme.py
  // comment names this exact role; the other two are literal hex that clears
  // 3:1 on EVERY themed plot fill (measured: #a020f0 3.09 dark / 4.82 light,
  // #e94560 4.28 dark / 3.48 light), so they survive the themed canvas
  // unchanged and re-valuing them would need new theme.py tokens.
  //
  // Deferred, not themed (needs new _TOKENS entries -- out of this change's
  // file set): #a020f0, #e94560, the cluster "Yours" gold, and the built-in
  // magnitude colorscales. Each is called out at its site.
  var anchorOutline = (state.anchorDisplayMode === 'outline');
  // In outline mode this hue IS the only ink on the marker, so a fixed cyan
  // (1.14:1 on a light fill) would erase the whole anchor envelope. --cat-anchors
  // is the anchors-category hue the dive's own slayer cards already use.
  //
  // DISCLOSED HUE COLLISION (sign-off item; see docs/theme_rollout_status.md,
  // "Plotly canvas/marker recoloring"): --cat-anchors is a byte-identical alias
  // of --tier-1 in all four themes (1.00:1) -- theme.py aliases them on purpose
  // as CHIP context, a decision made when the two families were never drawn on
  // one canvas. In the default threshold color mode they now are. The retired
  // cyan was 2.83-4.08:1 from tier-1, so this IS a measurable loss of hue
  // separation, traded for a hue that survives a light fill at all. What
  // carries the separation instead:
  //   filled (default) - subdued => markerLineWidth 0, so this hue reaches only
  //                      the hover-label border; the fill is the point's OWN
  //                      tier color, same as the tier trace's.
  //   outline          - ring-vs-fill (transparent center; tier dots are solid)
  //                      plus size 6 vs the tier trace's 7/9.
  //   both             - symbol (overlaySymbol: triangle-up / star /
  //                      triangle-down) vs the tier trace's pinned 'circle'.
  // Re-encoding the hue needs a NON-ALIASED _TOKENS entry, i.e. theme.py --
  // out of this change's file set, so it is disclosed rather than fixed.
  var anchorTrace = buildOverlayTrace('Anchor IVs', DATA.anchorClearIvs,
                                      themeColor('--cat-anchors'), true, anchorOutline);
  if (anchorTrace) traces.push(anchorTrace);
  // Efficient (Pareto) overlay: the globally Pareto-optimal IV spreads
  // ("efficient" - no other spread for this species/league
  // beats them on all three scaled stats). Subdued + a distinct
  // 'cross' symbol so this large set reads as context, like Anchor IVs,
  // without fighting the rarer slayer/rec sets that draw on top.
  var effTrace = buildOverlayTrace('Efficient (Pareto)', effIvs, '#a020f0', true, false, false, 'cross',
    '<br>Efficient IV: no other spread beats it on all of atk/def/hp.');
  if (effTrace) traces.push(effTrace);
  // DISCLOSED HUE COLLISION (same sign-off item as the anchor hue above):
  // --notable sits 1.03-1.12:1 from --tier-8 in all four themes (theme.py
  // aliases tier-8 == catw-rank1 and values --notable a hair off it), so on a
  // tier-8-colored fill this borderColor ring effectively vanishes; the retired
  // #FFD700 was 2.53-3.64:1 from tier-8. Against every OTHER tier fill the ring
  // still separates, and in stat/score color mode no tier trace exists at all.
  // Non-color separation from the tier traces: symbol (triangle-down / star /
  // diamond via overlaySymbol vs the tier trace's pinned 'circle') and size
  // (6 vs 7/9). A non-aliased gold would need a new theme.py token -> out of
  // this change's file set.
  var slayerTrace = buildOverlayTrace('Slayer IVs', DATA.slayerIvs,
                                      themeColor('--notable'));
  if (slayerTrace) traces.push(slayerTrace);
  // Spec Card Spreads draws last (after tier traces, below) would be
  // ideal, but tier traces must own the top z-order for hover. Pushing
  // here (after slayer) keeps it above the larger overlays; the
  // bigHighlight size + outline keep the few card spreads legible even
  // when a tier circle sits on the same point.
  var recTrace = buildOverlayTrace('Spec Card Spreads', DATA.recIvs, '#e94560', false, false, true);
  if (recTrace) traces.push(recTrace);

  // Matchup-cluster traces go on top of the overlays, for the same reason
  // the tier traces do: the color mode a reader selected has to be the thing
  // they can isolate. Order inside the group is left as built (legend note
  // key first, then C0..Ck) so the legend reads in cluster order.
  if (typeof _clusterTraces !== 'undefined' && _clusterTraces) {
    for (var _ci = 0; _ci < _clusterTraces.length; _ci++) {
      traces.push(_clusterTraces[_ci]);
    }
  }

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
        // circle-open: the color IS the ring, so this is a NEUTRAL, not an
        // identity hue. --text-muted keeps it recessive-but-present in both
        // directions; the old #cccccc was 1.46:1 on a light plot fill.
        marker: {
          size: 6, color: themeColor('--text-muted'), symbol: 'circle-open',
          opacity: 0.7, line: { width: 1, color: themeColor('--text-muted') }
        },
        hoverlabel: { bordercolor: themeColor('--text-muted') }
      });
    }
    if (qualX.length > 0) {
      // Notable ring: size 13 -> 9, line width 2 -> 1.5. Still larger
      // and fuller-opacity than "other" so the "worth noticing" visual
      // hierarchy is preserved.
      traces.push({
        name: 'Yours - notable', x: qualX, y: qualY, text: qualText,
        mode: 'markers', type: 'scattergl', hoverinfo: 'text',
        // Same neutral-ring reasoning as "Yours - other", one step louder:
        // --text is the page's highest-contrast ink in every theme (#ffffff
        // was 1.00:1 against the pokemon-light plot fill -- literally erased).
        marker: {
          size: 9, color: themeColor('--text'), symbol: 'circle-open',
          opacity: 1.0, line: { width: 1.5, color: themeColor('--text') }
        },
        hoverlabel: { bordercolor: themeColor('--text') }
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
// THE one rule for "does atk a CMP-beat atk b", shared by every mirror-CMP
// surface (_computeMirrorCmpPct, _computeTopMirrorCmpPct, cmpMirror). Both
// sides are rounded to 2dp (the dive's display precision) before the compare
// so float drift doesn't lie: Tinkaton UL's cohort atk of 142.8509983 would
// otherwise beat the max-atk IV's display atk of 142.85 by 0.001 and return
// 0% for every IV in the grid -- a numeric, not semantic, difference. Ties
// count as beating since PvP CMP at exactly-equal atk resolves on move
// priority or a coin flip, not a guaranteed loss. cmpMirror once used raw
// values with a 1e-6 epsilon instead, so one page could show "100% mirror
// CMP" and "Loses mirror CMP" for the same IV (DRY review 2026-08-05).
function _atkBeats(a, b) {
  return Math.round(a * 100) / 100 >= Math.round(b * 100) / 100;
}

// Fraction of the cohort whose atk this IV at least TIES, per _atkBeats.
function _computeMirrorCmpPct(iv) {
  var cohort = DATA.mirrorCohortAtk;
  if (!cohort || cohort.length === 0) return NaN;
  var myAtk = DATA.ivAtk[iv];
  if (!isFinite(myAtk)) return NaN;
  var beaten = 0;
  for (var i = 0; i < cohort.length; i++) {
    if (_atkBeats(myAtk, cohort[i])) beaten++;
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
  var beaten = 0;
  for (var j = 0; j < cohort.length; j++) {
    if (_atkBeats(myAtk, cohort[j])) beaten++;
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
      if (isWin(scores[iv * nS * nO + sis[k] * nO + oi])) sceneWins++;  // 500=tie
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
    h += '(you filtered the opponent set; the card, tiers, "Which one to build?" and narrative above still use all '+nO+') ';
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

// B5 state. The cluster bands are HORIZONTAL lines on a wins y-axis (each
// band is a set of spreads with the same win count) and a smear on the
// averaged-score axis, so the first time the reader picks cluster coloring
// the y-axis moves with them -- ONCE. `_mcYAxisNudged` makes it a nudge
// rather than a lock: switch back and it stays back. `_mcYAxisSwitched`
// tells the legend to say it happened.
var _mcYAxisNudged = false;
var _mcYAxisSwitched = false;
function _selHasValue(sel, v) {
  if (!sel) return false;
  for (var i = 0; i < sel.options.length; i++) {
    if (sel.options[i].value === v) return true;
  }
  return false;
}

function updateView() {
  // Read state from dropdowns
  var msel = document.getElementById('moveset-sel');
  if (msel) state.movesetIdx = parseInt(msel.value);
  var ssel = document.getElementById('scenario-sel');
  if (ssel) state.scenarioMode = ssel.value;
  var osel = document.getElementById('oppiv-sel');
  var bsel = document.getElementById('bait-sel');
  var esel = document.getElementById('energy-sel');
  var psel = document.getElementById('policy-sel');
  if (osel || bsel || esel || psel) {
    var base = osel ? osel.value : parseModeBase(DATA.oppIvModes[0] || 'pvpoke');
    var bait = bsel ? bsel.value : 'bait';
    var elead = esel ? parseInt(esel.value) : 0;
    var pol = psel ? psel.value : 'pvpoke';
    state.oppIvMode = composeMode(base, bait, elead > 0 ? elead : 0, pol);
  }
  // All-scenarios grid: keep the minis in sync with moveset/mode and the
  // highlight in sync with the Shields dropdown (cheap; no-op when the
  // grid is closed).
  var csel = document.getElementById('color-sel');
  if (csel) state.colorMode = csel.value;
  var ysel = document.getElementById('yaxis-sel');
  if (ysel) state.yAxisMode = ysel.value;
  // The legend's "y-axis switched to ..." note is a claim about the axis as
  // it stands; a reader who switches back must stop reading it. (The NUDGE
  // itself stays spent -- _mcYAxisNudged is never cleared -- so switching
  // back keeps it back.)
  if (state.yAxisMode !== 'winsPvpoke') _mcYAxisSwitched = false;
  // Spend the one-shot nudge only where the clusters can actually be drawn:
  // on a non-default moveset / opponent-IV mode the cluster branch renders
  // neutral points, and consuming the nudge there would mean the reader
  // never gets it on the view it was written for.
  if (state.colorMode === 'cluster' && !_mcYAxisNudged && _mcLabelsApply()) {
    _mcYAxisNudged = true;
    if (state.yAxisMode === 'avgScore' && _selHasValue(ysel, 'winsPvpoke')) {
      ysel.value = 'winsPvpoke';
      state.yAxisMode = 'winsPvpoke';
      _mcYAxisSwitched = true;
    }
  }
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

  var chrome = plotChrome();
  var layout = {
    title: DATA.movesets[state.movesetIdx].prettyLabel,
    // fixedrange:false enables Plotly's native drag-to-zoom and
    // double-click-to-reset on both axes. Useful for drilling into
    // dense clusters without click-to-pin from the matches list.
    // gridcolor/zerolinecolor are set explicitly: Plotly's defaults are
    // tuned for a white paper and disappear against a themed plot fill.
    xaxis: {title:'Stat Product Rank (1=best)', range:[xMax+xPad, xMin-xPad],
            gridcolor: chrome.grid, zerolinecolor: chrome.grid},
    yaxis: {title:yAxisTitle(), range:[yMin-yPad, yMax+yPad],
            gridcolor: chrome.grid, zerolinecolor: chrome.grid},
    paper_bgcolor: chrome.paper, plot_bgcolor: chrome.plot,
    font:{color: chrome.font}, hovermode:'closest',
    // Legend pinned explicitly OUTSIDE the plot area so it never
    // covers top-right hover tooltips (the rank-1 points on the
    // inverted x-axis are in the corner that Plotly's default
    // top-right legend position sits on, and tooltips there were
    // rendering under the legend box). It sits over transparent paper,
    // so it needs an opaque themed fill of its own.
    legend: {
      bgcolor: chrome.legendBg, bordercolor: chrome.legendBorder, borderwidth:1,
      x: 1.02, xanchor: 'left', y: 1, yanchor: 'top',
    },
    // Explicit hoverlabel so tooltip sizing and font are deterministic
    // — namelength:-1 disables trace-name truncation so we see the
    // full "★ Yours:" block. Background and font are uniform across
    // traces, but the BORDER color is set per-trace (via
    // trace.hoverlabel.bordercolor) so each trace's tooltip picks up
    // a color matching its marker — tier color for tier traces,
    // gold for slayer, anchor hue for anchor, muted for Other, ink for
    // user overlay. The layout-level bordercolor here is just a
    // fallback for traces that forget to set one.
    hoverlabel: {
      bgcolor: chrome.hoverBg, bordercolor: chrome.hoverBorder,
      font: { size: 11, color: chrome.font, family: 'monospace' },
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

// Back-compat alias for the two call sites below; the grammar itself lives in
// parseModeBase (see "Composite mode grammar" up top).
function parse_oppiv_base(mode) { return parseModeBase(mode); }

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
      if (isWin(v)) wins++;
      else if (isLoss(v)) losses++;
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
    var hChrome = plotChrome();
    var layout = {
      xaxis: {title: 'Battle Rating (Avg: ' + avg + ')',
              range: [0, 1000], tickvals: [0, 250, 500, 750, 1000],
              fixedrange: true, showgrid: false, zeroline: false},
      yaxis: {title: 'Matches', rangemode: 'tozero',
              fixedrange: true, showgrid: false, zeroline: false},
      paper_bgcolor: hChrome.paper, plot_bgcolor: hChrome.plot,
      font: {color: hChrome.font, size: 11},
      margin: {t: 10, b: 48, l: 56, r: 16},
      bargap: 0.04,
      shapes: [{
        type: 'line', x0: winRating(), x1: winRating(),  // tie centerline
        yref: 'paper', y0: 0, y1: 1,
        line: {color: hChrome.rule, width: 1, dash: 'dash'},
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
// The trace index Plotly bound to a legend node, NOT the node's position in
// the legend. The two differ whenever a trace is missing from the legend (a
// pointless trace gets no entry) or legendrank reorders it, and the
// difference is silent: the reader hovers one key and a different trace
// lights up. Falls back to the DOM position when the binding is not there.
function _legendTraceIndex(el, fallback) {
  try {
    var d = el.__data__;
    var item = Array.isArray(d) ? d[0] : d;
    if (Array.isArray(item)) item = item[0];
    var tr = item && item.trace;
    if (tr && typeof tr.index === 'number') return tr.index;
  } catch (e) { /* fall through to the DOM position */ }
  return fallback;
}

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
      // Resolved at EVENT time, not wiring time: Plotly reuses these nodes
      // across react calls, so the binding a handler closed over could be a
      // previous render's.
      el.addEventListener('mouseenter', function() {
        if (lockedIdx<0) highlightTrace(_legendTraceIndex(el, idx)); });
      el.addEventListener('mouseleave', function() { if (lockedIdx<0) restoreAll(); });
      el.addEventListener('click', function() {
        var ti = _legendTraceIndex(el, idx);
        if (lockedIdx===ti) { lockedIdx=-1; restoreAll(); }
        else { lockedIdx=ti; highlightTrace(ti); }
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
// CMP_MARGIN_MIN and the cmpVal/cmpHp/cmpScenLabel/cmpCellLink/cmpBarHtml/
// cmpCellHtml/cmpUnifiedTable functions now live in the shared
// scripts/cmp_panels.js (loaded as a <script> before this engine), so the ML
// IV-guide pages can reuse the exact same unified compare table. They read grid
// sizing from the global DATA.

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
  var mi = state.movesetIdx, mode = state.oppIvMode;
  var bb = DATA.bestBuddy || {};
  var atL51 = atL51View();
  return {
    def: SCORES[getScoreKeyAt(mi, mode, atL51)],
    alt: DATA.ivL51 ? SCORES[getScoreKeyAt(mi, mode, !atL51)] : null,
    altCap: atL51 ? (bb.defaultCap || levelCap('default'))
                  : (bb.altCap || levelCap('alt')),
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
  var mi = state.movesetIdx, mode = state.oppIvMode, atL51 = atL51View();
  return { def: ENERGY[getScoreKeyAt(mi, mode, atL51)] || null,
           alt: DATA.ivL51 ? (ENERGY[getScoreKeyAt(mi, mode, !atL51)] || null) : null };
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
    var v = cmpVal(g, iv, si, oi); tot += v; if (isWin(v)) wins++;
  }
  return { wins: wins, n: nS * oppDen, avg: tot / (nS * oppDen) };
}
// "Avg score behind best": avg-score gap to the best battle-IV in the active
// grid. Deliberately NOT called "Gives up vs #1" -- the collection table's
// column of that name counts DROPPED MATCHUPS against the current y-axis #1,
// while this is a score-point gap against the best-average IV, so one name for
// both would put two different units under one label.
// Cache key is the active grid's score key (moveset + mode + level) plus the
// mask signature, so a selection change re-finds the best (else it would
// compare candidates against a full-pool best under a filter).
function cmpBestAvg() {
  var key = getScoreKey(state.movesetIdx, state.oppIvMode) + oppMaskSig();
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
  // Same 2dp/ties-beat rule as the CMP % columns -- the old raw-value
  // 1e-6 epsilon disagreed with them at display-precision boundaries.
  return _atkBeats(DATA.ivAtk[iv], cohort[0]);
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
// Prefill the widget from ANOTHER section (today: the "Which one to build?"
// button). Replaces the candidate list rather than appending, so the button is
// idempotent -- two clicks give the same cards, not a doubled list that trips
// CMP_MAX. `list` is an array of [atk, def, hp] IV triples; out-of-range,
// non-integer and duplicate entries are dropped, and the same 0-15 validation
// cmpAdd applies to typed input applies here. Returns how many were kept.
function cmpSetCandidates(list) {
  var out = [], seen = {};
  function okIv(x) { return x >= 0 && x <= 15; }
  for (var i = 0; i < list.length && out.length < CMP_MAX; i++) {
    var t = list[i] || [];
    var a = parseInt(t[0], 10), d = parseInt(t[1], 10), sv = parseInt(t[2], 10);
    if (!(okIv(a) && okIv(d) && okIv(sv))) continue;
    var k = a + '/' + d + '/' + sv;
    if (seen[k]) continue;
    seen[k] = 1;
    out.push({ a: a, d: d, s: sv, level: null });
  }
  state.compareCandidates = out;
  cmpStatus('', 'var(--text-muted)');
  cmpRender();
  return out.length;
}
window.cmpSetCandidates = cmpSetCandidates;
function cmpStatus(t, c) {
  var el = document.getElementById('cmp-status'); if (el) { el.textContent = t; el.style.color = c; }
}

// Battle link for a compare-panel cell -> the exact pvpoke.com fight for this
// candidate build vs this opponent, at the selected shields, opp-IV mode, and
// best-buddy level. Mirrors pvpoke_links.battle_url's URL skeleton (that
// docstring is the source of truth for the format). The opponent (level, IVs)
// + moveset come from DATA.oppLinks (resolved server-side to match the sim);
// focal level from DATA.ivLv / ivL51 (best-buddy toggle), focal moves from the
// active moveset, focal IVs from the candidate. Returns null (cmpCellLink then
// renders plain text) when any piece is missing. build = {a,d,s,iv}.
window.cmpBattleUrl = function(oi, si, build) {
  var fl = DATA.focalLink, ol = (DATA.oppLinks || [])[oi], sc = DATA.scenarios[si];
  if (!fl || !ol || !sc || !build || build.iv == null) return null;
  // Structured move ids, split ONCE by Python (deep_dive_rendering
  // .parse_moveset_label -> DATA.movesets[i].fast/.charged). Never re-split
  // the display label here: the label is a display string, and a parser drift
  // yields a wrong-but-200 pvpoke URL that no link checker can see.
  var ms = (DATA.movesets || [])[state.movesetIdx] || {};
  var fast = ms.fast, chg = ms.charged || [];
  if (!fast || chg.length < 2 || !chg[0] || !chg[1]) return null;
  var lvArr = atL51View() ? DATA.ivL51.ivLv : DATA.ivLv;
  var flv = (lvArr || [])[build.iv];
  if (flv == null) return null;
  var om = ol.byMode[state.oppIvMode] || ol.byMode.pvpoke
        || ol.byMode[Object.keys(ol.byMode)[0]];
  if (!om) return null;
  var p1 = fl.id + '-' + flv + '-' + build.a + '-' + build.d + '-' + build.s + '-4-4-1-1';
  var p2 = ol.id + '-' + om.lvl + '-' + om.ivs[0] + '-' + om.ivs[1] + '-' + om.ivs[2] + '-4-4-1-1';
  // A mega's THIRD charged move gets a 4th part; PvPoke's parser routes any
  // alphabetic part through addNewMove(..., moveIndex = i-1), and a 4-part
  // segment also suppresses its "deselect the 3rd charged move" branch
  // (Interface.js:1959-1967, :1995). Mirrors pvpoke_links.moveset_segment.
  var seg = fast + '-' + chg[0] + '-' + chg[1] + (chg[2] ? '-' + chg[2] : '');
  return 'https://pvpoke.com/battle/' + DATA.cpCap + '/' + p1 + '/' + p2 + '/'
    + sc[0] + '' + sc[1] + '/' + seg + '/' + ol.moves + '/';
};

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
    h += '<div class="cmp-row" title="Average battle-score points behind the ' +
      'best-average IV in this dive, over all shield scenarios and the selected ' +
      'opponents. Score points, not matchups."><span>Avg score behind best</span>' +
      '<b class="' + guc + '">' + gu + '</b></div>';
    h += xrow('Anchors cleared', cmpAnchors(iv) + ' opp');
    var mir = cmpMirror(iv);
    if (mir !== null) h += '<div class="cmp-pill ' + (mir ? '' : 'cmp-pill-lose') + '">' +
      (mir ? 'Wins mirror CMP' : 'Loses mirror CMP') + '</div>';
    h += '</div>';
  });
  h += '</div>';

  var live = rows.filter(function(r) { return r.iv >= 0; });
  if (live.length >= 2) {
    // Shared unified compare table (scripts/cmp_panels.js), single Case for the
    // current view. Best-buddy ✦ marks show only when this dive carries the L51
    // grid (grids.alt); energy from the current state's grid. Battle links track
    // the live moveset / opp-IV mode / level via window.cmpBattleUrl.
    var eg = cmpEnergyGrids();
    var liveU = live.map(function(r) {
      return { a: r.c.a, d: r.c.d, s: r.c.s, iv: r.iv, key: r.c.a + '/' + r.c.d + '/' + r.c.s };
    });
    var cmpCases = [{ key: '_cur', label: null, def: grids.def, alt: grids.alt,
      altCap: grids.altCap, altIsBuddy: grids.altIsBuddy, energy: eg ? eg.def : null }];
    h += cmpUnifiedTable(liveU, cmpCases, {
      em: (DATA.movesets[state.movesetIdx] || {}).energyMoves,
      showBB: !!grids.alt,
      title: 'Comparing your builds',
      subtitle: 'Matchups these spreads decide differently, or win/lose with a '
        + 'different margin. Flips first, then win in both, then lose in both.',
      legend: 'Bars = leftover HP% at battle end (from the score); energy = leftover '
        + 'charge on a win. Rows where every spread behaves identically are hidden.'
        + (grids.alt ? ' Faded &#10022;on/off marks a spread whose result flips at '
            + 'the other best-buddy level.' : '')
    });
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
// The Build criteria preset a shared link carried, applied BEFORE the first
// render: the scatter's weighted Shields entry and the clusters "all
// scenarios" option both read the knob, so a hash applied afterwards would
// draw the default once and then jump.
wbApplyPresetHash();
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

// The page's cluster payload, read from whichever Matchup clusters section is
// live (the best-buddy swap replaces the section wholesale). Three surfaces
// need it now -- the section's own panels, the main scatter's cluster color
// mode, and the all-scenarios mini-grid -- so the lookup and the
// "do the baked labels describe what is on screen" gate live here once.
function _mcPayloadPage() {
  var root = document.querySelector('.dd-mc-root');
  return root ? _mcPayload(root) : null;
}

// Labels are baked for moveset 0 at the default opp-IV mode. On any other
// moveset/mode they would not describe the displayed grid, so every consumer
// falls back to uncolored points rather than mis-coloring.
function _mcLabelsApply() {
  return state.movesetIdx === 0 &&
         (!DATA.oppIvModes || state.oppIvMode === DATA.oppIvModes[0]);
}

// Legend / title text for one scenario key: "K=2, silhouette 0.65, split
// atk 148.06", or the short no-clusters note. Python emits every number and
// every string; this only concatenates them. Words are spelled out ("sil"
// and a bare "atk < 148.06" read as an abbreviation and a filter condition
// to a reader who has met neither before).
function _mcHeadline(pay, lbl) {
  if (!pay) return '';
  var sc = pay.scens ? pay.scens[lbl] : null;
  if (sc) {
    return 'K=' + sc.k + ', silhouette ' + Number(sc.sil).toFixed(2) +
           (sc.split ? ', split ' + sc.split : '');
  }
  var dg = pay.degenerate ? pay.degenerate[lbl] : null;
  if (dg) return dg.short || (dg.degenerate ? 'degenerate' : 'no clusters');
  return '';
}

// One scattergl trace spec for the cluster panels. The per-cluster traces and
// the owned-mon overlay differ ONLY in name + marker (and whether their arrays
// arrive prebuilt), so the shared plumbing -- type/mode/hoverinfo -- is named
// once here rather than typed twice (DRY review 2026-08-05 entry 14
// ride-along). Purely cosmetic: both call sites produce the same objects they
// did as literals.
function _mcTrace(name, marker, x, y, text) {
  return {type: 'scattergl', mode: 'markers',
          x: x || [], y: y || [], text: text || [],
          hoverinfo: 'text', name: name, marker: marker};
}

// The scenario key one Matchup clusters section is actually showing.
// Identity for every '{a}v{b}' option; for the "all scenarios" option it is
// the partition of the page's Build criteria preset -- the option re-labels
// itself, so its value stays the stable key and the mapping lives here.
function _mcEffectiveScen(payload, value) {
  var allKey = payload.allKey || 'all';
  if (value !== allKey || !payload.allByPreset) return value;
  var pk = (typeof wbActivePresetKey === 'function') ? wbActivePresetKey() : null;
  var mapped = pk ? payload.allByPreset[pk] : null;
  return (mapped && payload.scens[mapped]) ? mapped : value;
}

function _mcRenderRoot(root) {
  var payload = _mcPayload(root);
  if (!payload) return;
  var scen = _mcEffectiveScen(
    payload, root.getAttribute('data-mc-scen') || payload['default']);
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
  var mcChrome = plotChrome();
  panels.forEach(function(p) {
    var proj = (p.getAttribute('data-proj') || 'atk,def').split(',');
    var xs = axes[proj[0]], ys = axes[proj[1]];
    if (!xs || !ys) return;
    var traces = [];
    for (var c = 0; c < sc.k; c++) {
      // Same legend rule the main scatter carries (Python emits the
      // string; null when the depth-1 root does not separate that cluster).
      traces.push(_mcTrace('C' + c +
                           ((sc.rules && sc.rules[c]) ? ': ' + sc.rules[c] : '') +
                           ' (n=' + sc.sizes[c] + ')',
                           {size: 4,
                            color: payload.palette[c % payload.palette.length],
                            opacity: 0.75}));
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
        // Gold fill + an --text ring: the ring, not the fill, is what makes
        // the star locatable, so it stays visible on a light plot fill where
        // gold alone is ~1.3:1. The fill keeps the star distinguishable from
        // CLUSTER_PALETTE's own gold; symbol + legend carry identity anyway.
        traces.push(_mcTrace('Yours (' + ox.length + ')',
                             {size: 11, symbol: 'star', color: '#ffd700',
                              opacity: 1,
                              line: {width: 1.5, color: mcChrome.ink}},
                             ox, oy, otxt));
      }
    }
    var layout = {
      xaxis: {title: titles[proj[0]], showgrid: false, zeroline: false},
      yaxis: {title: titles[proj[1]], showgrid: false, zeroline: false},
      paper_bgcolor: mcChrome.paper, plot_bgcolor: mcChrome.plot,
      font: {color: mcChrome.font, size: 11},
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

function mcSetScenario(root, value) {
  if (!root) return;
  var payload = _mcPayload(root);
  if (value) root.setAttribute('data-mc-scen', value);
  var want = root.getAttribute('data-mc-scen') ||
             (payload ? payload['default'] : '');
  var shown = payload ? _mcEffectiveScen(payload, want) : want;
  root.querySelectorAll('.dd-mc-scen-block').forEach(function(b) {
    b.style.display = (b.getAttribute('data-scen') === shown) ? 'block' : 'none';
  });
  _mcRenderRoot(root);
}
window.mcSetScenario = mcSetScenario;

// Draw every clusters section that is on screen and not yet drawn. Three
// callers: the toggle-open hook, the page-load pass, and the best-buddy swap
// (which replaces the section's DOM with an undrawn copy).
function mcRenderPending() {
  document.querySelectorAll('.dd-mc-root:not([data-mc-rendered])').forEach(
    function(root) { if (root.offsetParent !== null) _mcRenderRoot(root); });
}

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
mcRenderPending();

// ---------------------------------------------------------------------------
// "Which one to build?" section (scripts/deep_dive_which_build.py).
//
// One scattergl panel owned by the section, drawn the same way the Matchup
// clusters panels are: server-side JSON carrying thresholds and marked
// spreads only, every per-IV array read from the DATA / SCORES blobs the page
// already embeds once. Axes are the main scatter's: stat-product rank
// (reversed) against matchups won.
//
// The panel is deliberately INERT to the page's dropdowns. The line above it
// was derived at the league cap, over every baked shield scenario and the
// whole opponent pool, with PvPoke-default opponent IVs; following the
// Shields / Opponent-IV / Bait selectors or the opponent filter would draw a
// grid the printed numbers were never measured on. The note under the panel
// says so on the page.
// ---------------------------------------------------------------------------
// Located by CLASS, like the clusters section's .dd-mc-root: the section is
// optional (a dive with no replay blob renders no brief), and a literal
// getElementById for a conditionally-emitted id is exactly what
// tests/test_dive_dom_ids.py exists to flag.
function _wbRoot() { return document.querySelector('.wb-root'); }

function _wbPayload(root) {
  var s = root.querySelector('script.wb-data');
  if (!s) return null;
  try { return JSON.parse(s.textContent); } catch (e) { return null; }
}

// The per-IV arrays this section's numbers are about. Since 2026-09-20 the
// section is rendered ONCE PER LEVEL and swapped by setBestBuddyLevel, so
// the copy on screen was derived at whatever level DATA.iv* currently holds
// -- which is exactly what a threshold must be compared against. (It used to
// pin itself to the stashed L50 arrays, because only one L50 copy existed
// and the toggle would otherwise have compared an L50 line to L51 stats.)
function wbLevelArrays() {
  return DATA;
}

// Keyed on the LEVEL as well as (moveset, mode, scenario): the two levels
// are different score grids, and a cache that could not tell them apart
// would serve the league cap's win counts to the best-buddy section.
var _wbWinsCache = {};
// Matchups won, per IV, at the league cap: over ALL baked scenarios and ALL
// opponents (the brief's own denominator, its `total_cells`) when `si` is
// null, or inside ONE shield scenario when the section's Shield scenario
// control names it. Same win predicate as everywhere else on the page
// (isWin: score > 500), and the same flat (iv, scenario, opponent) decoding
// the main plot's winsPvpoke mode and computeScenarioAvgPure use -- only the
// scenario loop's bounds move, so there is one decoding on the page and not
// two that can drift.
function wbWins(mi, mode, si) {
  var key = getScoreKey(mi, mode) + SCORE_KEY_SEP +
            (si == null ? 'all' : si);
  if (_wbWinsCache[key]) return _wbWinsCache[key];
  var g = getScores(mi, mode);
  if (!g) return null;
  var nO = DATA.nOpponents, nS = DATA.nScenarios, n = DATA.nIvs;
  var lo = (si == null) ? 0 : si, hi = (si == null) ? nS : si + 1;
  var out = new Float64Array(n);
  for (var iv = 0; iv < n; iv++) {
    var c = 0, base0 = iv * nS * nO;
    for (var sj = lo; sj < hi; sj++) {
      var base = base0 + sj * nO;
      for (var oi = 0; oi < nO; oi++) { if (isWin(g[base + oi])) c++; }
    }
    out[iv] = c;
  }
  _wbWinsCache[key] = out;
  return out;
}

// The label the section's "every scenario" entry carries. Kept in step with
// deep_dive_which_build.ALL_SCEN by tests/test_which_build_section.py.
var WB_ALL_SCEN = 'all';

// Which shield scenario the section's own control names, as an index into
// the page's DATA.scenarioLabels -- null for "all". The lookup goes through
// scenLabel() rather than a parallel list in the payload, so the option the
// reader picked and the slice of the score grid it selects are the same
// vocabulary by construction.
// Round 9: every figure in the section is a `.wb-plotbox` -- tabs, its own
// Shield-scenario control, a panel and a caption.
//
// The tab a box is on. The attribute is the state; the tab strip's
// aria-selected follows it, so nothing reads the buttons to find the view.
function _wbBoxView(box) {
  return box ? (box.getAttribute('data-wb-view') || '') : '';
}

function _wbScen(root, pay) {
  var sel = root.querySelector('select.wb-scen');
  var v = sel ? sel.value : WB_ALL_SCEN;
  if (!v || v === WB_ALL_SCEN || !pay.scen) return null;
  for (var si = 0; si < DATA.nScenarios; si++) {
    if (scenLabel(si) === v && pay.scen[v]) {
      return { idx: si, label: v, entry: pay.scen[v] };
    }
  }
  return null;
}

// Section palette. Declared as CSS custom properties on #dd-which-build (with
// a dark-theme override) so the colors live with the rest of the section's
// styling and re-theme with the picker like everything else.
//
// WB_FALLBACK is the LIGHT-theme half of that declaration, copied. Same
// deliberate-fallback pattern as LEVEL_CAP_FALLBACK / THEME_FALLBACK above:
// getComputedStyle can come back empty (an environment that did not apply the
// inline <style>), and a trace with no color is a legend entry pointing at
// invisible points. The copy is pinned to the CSS by
// tests/test_which_build_section.py so the two cannot drift.
var WB_FALLBACK = {
  '--wb-line': '#7a4fc0', '--wb-below': '#7f858f', '--wb-alt': '#a63089',
  '--wb-mark1': '#16706a', '--wb-mark2': '#2f5fd0'
};
// The rung ramp has exactly as many steps as the page prints rungs, emitted
// as --wb-r0..--wb-r(n-1) by deep_dive_which_build.ramp_css (and repeated in
// the payload's rungColors as the light-theme fallback). A fixed six-color
// ramp painted the 6th and 7th rung of a seven-rung page the same color, on
// the one view whose whole encoding is color.
function _wbColors(root, pay) {
  var cs = getComputedStyle(root);
  function v(n) { var x = cs.getPropertyValue(n).trim(); return x || WB_FALLBACK[n]; }
  var ramp = [], fb = (pay && pay.rungColors) || [];
  var nR = (pay && pay.rungs) ? pay.rungs.length : 0;
  for (var k = 0; k < nR; k++) {
    var got = cs.getPropertyValue('--wb-r' + k).trim();
    ramp.push(got || fb[k] || WB_FALLBACK['--wb-line']);
  }
  // The SCENARIO ladder's own ramp (--wb-s*), sized server-side to the
  // longest ladder the Shield scenario control can select. It is separate
  // from --wb-r* because a scenario's ladder can be longer than the page's
  // own: read off the page ramp, its overflow rungs fell back to one color
  // and two steps of the encoding became indistinguishable.
  var sramp = [], sfb = (pay && pay.scenColors) || [];
  var nS = (pay && pay.nScenRamp) || 0;
  for (var k2 = 0; k2 < nS; k2++) {
    var got2 = cs.getPropertyValue('--wb-s' + k2).trim();
    sramp.push(got2 || sfb[k2] || WB_FALLBACK['--wb-line']);
  }
  return {
    line: v('--wb-line'),
    below: v('--wb-below'),
    alt: v('--wb-alt'),
    mark1: v('--wb-mark1'),
    mark2: v('--wb-mark2'),
    rungs: ramp,
    scenRungs: sramp
  };
}

// Membership masks, packed server-side (deep_dive_which_build.mask_b64).
//
// The page's DATA.ivAtk / ivDef are rounded to 2 dp, while a line is a
// full-precision value, so `DATA.ivAtk[i] >= T` mis-sides every spread inside
// the rounding window -- 19 of 4096 on the Shadow Sableye grid, drawn in the
// wrong color under a sentence saying the split is exact. The masks are
// computed from the same full-precision plane the brief selected the line on,
// and their counts are checked against the page's printed counts before they
// are packed, so the plot and the prose cannot disagree. 512 bytes each.
var _wbMaskCache = {};
function _wbMask(b64) {
  if (_wbMaskCache[b64]) return _wbMaskCache[b64];
  var bin = atob(b64), out = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  _wbMaskCache[b64] = out;
  return out;
}
function _wbBit(m, i) { return (m[i >> 3] >> (i & 7)) & 1; }

// Is spread `i` at or above one line? Two encodings, because the two kinds
// of line cost differently:
//
//   * the page's OWN line and its rungs carry a packed membership mask --
//     one 512-byte classification each, which is the right price for the
//     values the whole section is about;
//   * a per-scenario line carries a `cut` in the page's own 2-dp array plus
//     the indices that comparison gets wrong (deep_dive_which_build.
//     rounded_cut). There can be a dozen of those on one page, and they cost
//     a float and (so far always) an empty list instead.
//
// Both are exact, and both were checked against the brief's own counts
// before they were emitted.
function _wbOn(L, line, i) {
  if (line.mask != null) return _wbBit(_wbMask(line.mask), i);
  var arr = (line.axis === 'def') ? L.ivDef
          : (line.axis === 'hp') ? L.ivHp : L.ivAtk;
  var on = (arr[i] >= line.cut) ? 1 : 0;
  var w = line.wrong;
  if (w && w.length) {
    if (!line._w) {
      line._w = {};
      for (var k = 0; k < w.length; k++) line._w[w[k]] = 1;
    }
    if (line._w[i]) on = on ? 0 : 1;
  }
  return on;
}

// Grid index of an IV triple. The IV arrays are level-invariant, so this
// needs no level view.
function _wbIvIdx(t) {
  for (var i = 0; i < DATA.nIvs; i++) {
    if (DATA.ivA[i] === t[0] && DATA.ivD[i] === t[1] && DATA.ivS[i] === t[2]) return i;
  }
  return -1;
}

// Hover body shared by every view: who the spread is, then its side of
// whatever the current view is grouping by.
function _wbHover(i, L, wins, side, den) {
  return DATA.ivA[i] + '/' + DATA.ivD[i] + '/' + DATA.ivS[i] +
         ' at L' + Number(L.ivLv[i]).toFixed(1) +
         '<br>atk ' + Number(L.ivAtk[i]).toFixed(2) +
         ' / def ' + Number(L.ivDef[i]).toFixed(2) +
         ' / hp ' + L.ivHp[i] +
         '<br>wins ' + wins[i] + ' of ' +
         (den == null ? (DATA.nScenarios * DATA.nOpponents) : den) +
         '<br>' + side;
}

// Which side of a line one spread is on, in the order the words are read:
// "attack at or above the 148.10 line", not "at or above attack 148.10".
// `line` is anything carrying axisWord + printed: the payload itself for the
// page's own line, or one entry of pay.scen[S].lines for a scenario's.
function _wbSideOf(line, on) {
  return line.axisWord + (on ? ' at or above the ' : ' below the ') +
         line.printed + ' line';
}
function _wbSide(pay, on) { return _wbSideOf(pay, on); }

// The line the CURRENT panel is drawing, or null when it draws none: the
// page's own line under "all", the lowest of that scenario's lines under a
// single one. Marked spreads and the collection overlay say their side of
// THIS line, which is the one the legend and the caption are about.
function _wbActiveLine(pay, scen) {
  if (scen) {
    var sl = scen.entry.lines || [];
    return sl.length ? sl[0] : null;
  }
  if (!pay.hasFloor) return null;
  return { axisWord: pay.axisWord, printed: pay.printed,
           mask: pay.rungs[0].mask };
}

// Which PLANE the section panel is drawing on for this render.
//
//   'rank'  -- stat-product rank (x) against matchups won (y). Every view
//              the section had through v4.
//   'stats' -- defense (x) against HP (y), where a two-stat box IS a
//              rectangle and an attack-floor-plus-staircase build IS a
//              staircase. The 2026-09-16 review's item 8: the page called
//              one build "the bulk rectangle" and never drew a rectangle,
//              because no view had axes it could be one on.
//
// Set once per wbRenderRoot call, read by every trace builder, so one
// switch moves the whole panel instead of six call sites each deciding.
var _wbPlaneMode = 'rank';

function _wbXY(L, i, wins) {
  return (_wbPlaneMode === 'stats')
    ? [L.ivDef[i], L.ivHp[i]]
    : [L.spRanks[i], wins[i]];
}

// Marker area by attack on the stats view: the third stat, which the two
// axes cannot show. A flat size there would draw 4096 points that differ on
// a stat the plot never mentions.
function _wbAtkSizes(L, ivs) {
  var lo = Infinity, hi = -Infinity, i;
  for (i = 0; i < DATA.nIvs; i++) {
    var a = L.ivAtk[i];
    if (a < lo) lo = a;
    if (a > hi) hi = a;
  }
  var span = (hi > lo) ? (hi - lo) : 1;
  return ivs.map(function (iv) {
    return 2.5 + 5.5 * ((L.ivAtk[iv] - lo) / span);
  });
}

function _wbTrace(name, color, symbol, size, opacity) {
  return { type: 'scattergl', mode: 'markers', x: [], y: [], text: [],
           hoverinfo: 'text', name: name,
           marker: { size: size, color: color, symbol: symbol || 'circle',
                     opacity: opacity == null ? 0.75 : opacity },
           hoverlabel: { bordercolor: color } };
}

// "7/2/14@49.5" -> [7, 2, 14]. The builds payload writes spreads the way the
// analysis modules do (with the level), and _wbIvIdx wants the triple.
function _wbIvTriple(s) {
  var p = String(s).split('@')[0].split('/');
  return [parseInt(p[0], 10), parseInt(p[1], 10), parseInt(p[2], 10)];
}

function _wbIvStr(i) {
  return i < 0 ? '?' : (DATA.ivA[i] + '/' + DATA.ivD[i] + '/' + DATA.ivS[i]);
}

// One marked spread's side of the line the panel is drawing, for its hover
// and its legend key.
function _wbSideAt(L, line, i) {
  if (!line || i < 0) return 'no line on this panel';
  // (callers that know WHICH scenario has no line say so themselves)
  return _wbSideOf(line, _wbOn(L, line, i));
}

// A named spread (rank-1, an example, the most-winning spread) as its own
// one-point trace: distinct symbol, a text label on the point, and a legend
// entry that carries the IVs.
function _wbMarkTrace(label, iv, color, symbol, L, wins, side, den, mini) {
  if (iv < 0) return null;
  var t = _wbTrace(label, color, symbol, 13, 1);
  if (!mini) {
    t.mode = 'markers+text';
    t.textposition = 'top center';
    t.textfont = { size: 10, color: color };
  }
  t.marker.line = { width: 1.5, color: plotChrome().ink };
  var mp = _wbXY(L, iv, wins);
  t.x = [mp[0]];
  t.y = [mp[1]];
  // `text` is the on-point label (mode carries 'text'); `hovertext` is the
  // hover card. Putting the multi-line hover body in `text` would print the
  // whole card next to the marker. On a 200px mini there is no room for
  // nine of those labels, so the mini variant keeps only the hover.
  if (!mini) {
    t.text = [DATA.ivA[iv] + '/' + DATA.ivD[iv] + '/' + DATA.ivS[iv]];
  }
  t.hovertext = [_wbHover(iv, L, wins, side, den)];
  return t;
}

// Every spread in one grey group, for a view that has nothing to split the
// grid by: a single shield scenario with no line of its own, or one the
// Matchup clusters section did not cluster. Drawn rather than blanked so the
// reader still sees the population the caption is talking about.
function _wbMutedTrace(L, wins, colors, den, side) {
  var t = _wbTrace('All spreads', colors.below, 'circle', 3, 0.4);
  for (var i = 0; i < DATA.nIvs; i++) {
    var mp = _wbXY(L, i, wins);
    t.x.push(mp[0]); t.y.push(mp[1]);
    t.text.push(_wbHover(i, L, wins, side, den));
  }
  t.name += ' (' + t.x.length + ')';
  return t;
}

// Group every spread for one view. Returns {traces, missing}: the population
// traces (the caller adds the marked spreads and the collection overlay), and
// whether the view had nothing to draw -- today only the clusters view, when
// the section baked no labels for this panel's moveset and mode.
function _wbGroups(pay, view, L, wins, colors, scen, den) {
  var n = DATA.nIvs, i;
  var traces = [];
  // ---- one shield scenario, on the two threshold views ------------------
  // The page's line and its rungs are whole-grid claims. With one scenario
  // selected these two views draw THAT scenario's own ladder instead
  // (deep_dive_brief.scenario_lines: the same exact / gate / near-exact cut
  // pool, restricted to cells in this shield state and to the decision
  // band), which is a different set of values with different owners. The
  // trade is a whole-grid trade and is left alone; clusters reads the label
  // set for this scenario further down.
  if (scen && (view === 'line' || view === 'rungs')) {
    var sl = scen.entry.lines || [];
    if (!sl.length) {
      return { traces: [_wbMutedTrace(L, wins, colors, den,
                                      'no line in ' + scen.label + ' shields')],
               missing: false };
    }
    var use = (view === 'line') ? [sl[0]] : sl;
    var sbelow = _wbTrace('Below ' + use[0].label, colors.below, 'circle', 3, 0.5);
    var sts = use.map(function(r, k) {
      return _wbTrace((use.length === 1 ? 'At or above ' : '') + r.label,
                      (use.length === 1 ? colors.line
                                        : (colors.scenRungs[k] ||
                                           colors.rungs[k] || colors.line)),
                      'circle', 4);
    });
    for (i = 0; i < n; i++) {
      var shit = -1;
      for (var sk = 0; sk < use.length; sk++) {
        if (_wbOn(L, use[sk], i)) shit = sk;
      }
      var str = shit < 0 ? sbelow : sts[shit];
      str.x.push(L.spRanks[i]); str.y.push(wins[i]);
      str.text.push(_wbHover(i, L, wins, shit < 0
        ? _wbSideOf(use[0], false)
        : (use.length === 1 ? _wbSideOf(use[0], true)
                            : 'highest line cleared: ' + use[shit].full),
        den));
    }
    sbelow.name += ' (' + sbelow.x.length + ')';
    if (use.length === 1) sts[0].name += ' (' + sts[0].x.length + ')';
    traces.push(sbelow);
    for (var sk2 = 0; sk2 < sts.length; sk2++) {
      if (sts[sk2].x.length) traces.push(sts[sk2]);
    }
    return { traces: traces, missing: false };
  }
  if (view === 'line') {
    var lineMask = _wbMask(pay.rungs[0].mask);
    var above = _wbTrace('At or above the line', colors.line, 'circle', 4);
    var below = _wbTrace('Below the line', colors.below, 'circle', 3, 0.5);
    for (i = 0; i < n; i++) {
      var on = _wbBit(lineMask, i);
      var t = on ? above : below;
      t.x.push(L.spRanks[i]); t.y.push(wins[i]);
      t.text.push(_wbHover(i, L, wins, _wbSide(pay, on), den));
    }
    above.name += ' (' + above.x.length + ')';
    below.name += ' (' + below.x.length + ')';
    traces.push(below, above);
  } else if (view === 'rungs') {
    var rmasks = pay.rungs.map(function(r) { return _wbMask(r.mask); });
    var below2 = _wbTrace('Below the line', colors.below, 'circle', 3, 0.5);
    var rts = pay.rungs.map(function(r, k) {
      // No '(N)' on a rung key. Every count in the prose above is CUMULATIVE
      // ("2220 reach it"), while a drawn rung group is the spreads whose
      // HIGHEST cleared rung is that one -- 250 of the 2220 on the Shadow
      // Sableye page. The same label carrying both numbers on one screen is
      // the ambiguity; the hover says which relation it is.
      return _wbTrace(r.label, colors.rungs[k] || colors.line, 'circle', 4);
    });
    for (i = 0; i < n; i++) {
      var hit = -1;
      for (var k = 0; k < pay.rungs.length; k++) {
        if (_wbBit(rmasks[k], i)) hit = k;
      }
      var tr = hit < 0 ? below2 : rts[hit];
      tr.x.push(L.spRanks[i]); tr.y.push(wins[i]);
      tr.text.push(_wbHover(i, L, wins, hit < 0
        ? _wbSide(pay, false)
        : 'highest rung cleared: ' + (pay.rungs[hit].full ||
                                      pay.rungs[hit].label), den));
    }
    traces.push(below2);
    for (var k2 = 0; k2 < rts.length; k2++) {
      if (rts[k2].x.length) traces.push(rts[k2]);
    }
    below2.name += ' (' + below2.x.length + ')';
  } else if (view === 'trade') {
    var tLine = _wbMask(pay.rungs[0].mask);
    var tAlt = pay.alt ? _wbMask(pay.alt.mask) : null;
    var cl = _wbTrace('At or above the line', colors.line, 'circle', 4);
    // "below the line" in the key because the group DRAWN here is the bulk
    // rectangle minus the line's own spreads -- the two can overlap, and a
    // count that silently excluded the overlap would contradict the caption's
    // printed rectangle count.
    var al = _wbTrace(pay.alt ? 'Bulk alternative, below the line: ' + pay.alt.label
                              : 'Bulk alternative, below the line',
                      colors.alt, 'square', 5);
    var ne = _wbTrace('Neither', colors.below, 'circle', 3, 0.45);
    for (i = 0; i < n; i++) {
      var side, tt;
      if (_wbBit(tLine, i)) { tt = cl; side = _wbSide(pay, true); }
      else if (tAlt && _wbBit(tAlt, i)) {
        tt = al; side = 'in the bulk alternative (' + pay.alt.label +
                        '), ' + _wbSide(pay, false);
      } else { tt = ne; side = 'neither'; }
      tt.x.push(L.spRanks[i]); tt.y.push(wins[i]);
      tt.text.push(_wbHover(i, L, wins, side, den));
    }
    ne.name += ' (' + ne.x.length + ')';
    cl.name += ' (' + cl.x.length + ')';
    al.name += ' (' + al.x.length + ')';
    traces.push(ne, cl);
    if (al.x.length) traces.push(al);
  } else if (view === 'rank1') {
    var all = _wbTrace('All spreads', colors.below, 'circle', 3, 0.45);
    for (i = 0; i < n; i++) {
      all.x.push(L.spRanks[i]); all.y.push(wins[i]);
      all.text.push(_wbHover(i, L, wins, 'no line on this page', den));
    }
    all.name += ' (' + all.x.length + ')';
    traces.push(all);
  } else if (view === 'clusters') {
    // The Matchup clusters section's own labels, read from ITS payload. No
    // second clustering runs here: a section that printed a different
    // partition under the same name would be worse than no view at all.
    var mcPay = _mcPayloadPage();
    // The clusters section bakes its labels for moveset 0 at the default
    // opponent-IV mode. This panel is pinned to ITS OWN moveset and mode, so
    // the labels describe what is on screen exactly when the two agree --
    // which is NOT _mcLabelsApply()'s question (that one tracks the scatter's
    // live dropdowns, and this panel deliberately ignores them).
    var mcApplies = _wbMcApplies(pay, mcPay);
    if (!mcApplies || !mcPay.scens) return { traces: [], missing: true };
    // With the section's Shield scenario control set, the view draws THAT
    // scenario's clusters -- the clusters payload carries every scenario it
    // could cluster, not only the combined fingerprint. A scenario it could
    // NOT cluster is a muted grid whose caption is that section's own
    // degenerate sentence (wbRenderRoot reads it); an empty panel with no
    // explanation is the one outcome worse than not offering the view.
    var want = scen ? scen.label
      : (pay.clusterScen && mcPay.scens[pay.clusterScen]
         ? pay.clusterScen : mcPay['default']);
    var sc = mcPay.scens[want];
    if (!sc) {
      if (scen) {
        return { traces: [_wbMutedTrace(L, wins, colors, den,
                          'no matchup clusters in ' + scen.label + ' shields')],
                 missing: false };
      }
      return { traces: [], missing: true };
    }
    // Cluster names. sc.rules[c] is the clusters section's own depth-1 rule,
    // printed by Python, and null whenever that split is not an iff for the
    // cluster -- which is the usual case, and left "C0 (n=2072)" under a
    // caption that talks about a split at atk 148.68 with no way to tell
    // which color is which side. Where there is a split to lean on, the side
    // each cluster MOSTLY sits on is named instead. The threshold string is
    // the payload's (`sc.split`); nothing here formats a number.
    var sides = _wbClusterSides(sc, L);
    var cts = [];
    for (var c = 0; c < sc.k; c++) {
      var cname = 'C' + c;
      if (sc.rules && sc.rules[c]) cname += ': ' + sc.rules[c];
      else if (sides && sides[c]) cname += ': ' + sides[c].label;
      cts.push(_wbTrace(cname + ' (n=' + sc.sizes[c] + ')',
                        mcPay.palette[c % mcPay.palette.length], 'circle', 4));
    }
    for (i = 0; i < n; i++) {
      var lab = sc.labels[i];
      if (lab == null || !cts[lab]) continue;
      cts[lab].x.push(L.spRanks[i]); cts[lab].y.push(wins[i]);
      cts[lab].text.push(_wbHover(i, L, wins, 'matchup cluster C' + lab +
                                  ' (' + (sc.display || want) + ')' +
                                  ((sides && sides[lab])
                                     ? '; ' + sides[lab].hover : ''), den));
    }
    for (var c3 = 0; c3 < cts.length; c3++) {
      if (cts[c3].x.length) traces.push(cts[c3]);
    }
  }
  return { traces: traces, missing: false };
}

// Which side of the clusters section's own depth-1 split each cluster mostly
// sits on. `sc.split` is that section's string ('atk 148.68'); the stat word
// selects the page's own array and the value is read back out of the same
// string, so the two sections cannot print different thresholds.
function _wbClusterSides(sc, L) {
  if (!sc.split) return null;
  var bits = String(sc.split).split(/\s+/);
  var arr = {atk: L.ivAtk, def: L.ivDef, hp: L.ivHp}[bits[0]];
  var thr = parseFloat(bits[1]);
  if (!arr || !isFinite(thr)) return null;
  var above = [], tot = [];
  for (var c = 0; c < sc.k; c++) { above.push(0); tot.push(0); }
  for (var i = 0; i < DATA.nIvs; i++) {
    var lab = sc.labels[i];
    if (lab == null || lab >= sc.k) continue;
    tot[lab]++;
    if (arr[i] >= thr) above[lab]++;
  }
  var out = [];
  for (var c2 = 0; c2 < sc.k; c2++) {
    if (!tot[c2]) { out.push(null); continue; }
    var share = above[c2] / tot[c2];
    var on = share >= 0.5;
    var pctTxt = Math.round((on ? share : 1 - share) * 100) + '%';
    out.push({
      label: 'mostly ' + (on ? 'at or above ' : 'below ') + sc.split,
      hover: pctTxt + ' of it is ' + (on ? 'at or above ' : 'below ') + sc.split
    });
  }
  return out;
}

// Do the Matchup clusters section's baked labels describe what THIS panel is
// drawing? That section bakes for moveset 0 at the default opponent-IV mode,
// and the panel is pinned to its own moveset and mode. Shared by the view
// (which draws nothing when they disagree) and by the caption (which must not
// then describe groups the reader cannot see).
function _wbMcApplies(pay, mcPay) {
  return !!(mcPay && pay.mi === 0 &&
            (!DATA.oppIvModes || pay.mode === DATA.oppIvModes[0]));
}

// Your pasted collection, on this panel, in every view -- same gold star the
// cluster panels use, hover naming the mon and its side of the line.
function _wbOwnedTrace(pay, L, wins, line, den, noLine, sideFn, borderFn) {
  if (!state.ownedByIv) return null;
  // The same tiny y-nudge the cluster panels and the main scatter apply, for
  // the same measured reason: a star sitting at the EXACT coordinates of a
  // scattergl population point loses the hover contest (3 of 24 stars hovered
  // as the wrong spread when the cluster panel shipped without it), and then
  // the overlay's whole point -- "Yours: <mon>" on hover -- is gone. The
  // y-axis is an integer win count, so 0.05% of the range is invisible.
  var ymin = Infinity, ymax = -Infinity;
  for (var w = 0; w < wins.length; w++) {
    if (wins[w] < ymin) ymin = wins[w];
    if (wins[w] > ymax) ymax = wins[w];
  }
  var ynudge = (isFinite(ymin) && ymax > ymin) ? (ymax - ymin) * 0.0005 : 0;
  var ox = [], oy = [], ot = [], ob = [];
  for (var key in state.ownedByIv) {
    var i = parseInt(key, 10);
    if (!(i >= 0 && i < DATA.nIvs)) continue;
    var names = state.ownedByIv[i].map(function(r) {
      return ((r.mon && r.mon.name) || 'mon') + ' CP' +
             ((r.stats && r.stats.cp) || '?');
    }).join(', ');
    var side = sideFn ? sideFn(i)
             : line ? _wbSideAt(L, line, i)
             : (noLine || 'no line on this page');
    var mp = _wbXY(L, i, wins);
    // The nudge is on the y axis, which is a win count on the rank plane and
    // an integer HP on the stats plane -- a 0.05%-of-range offset is
    // invisible on either, and the hover contest it wins is the same one.
    oy.push(mp[1] + (_wbPlaneMode === 'stats' ? 0.02 : ynudge));
    ox.push(mp[0]);
    ot.push('Yours: ' + names + '<br>' + _wbHover(i, L, wins, side, den));
    // Round 8 item 3(a): the star's BORDER is the colour of the build it is
    // in. A collection of 40 stars on one plot answered "you own these
    // spreads" and nothing else; the border answers "and this one is a
    // Build 1 spread" without a click. The fill stays gold on every star --
    // that is what says "yours" -- so the build reads as an outline.
    ob.push(borderFn ? borderFn(i) : plotChrome().ink);
  }
  if (!ox.length) return null;
  var t = _wbTrace('Yours (' + ox.length + ')', '#ffd700', 'star', 12, 1);
  t.marker.line = { width: 2, color: borderFn ? ob : plotChrome().ink };
  t.x = ox; t.y = oy; t.text = ot;
  return t;
}

// ---- round 8 item 3: where one spread sits, for the collection overlay --
// The four answers in the order they are asked, which is also the order the
// "Your collection" list groups by: a build first (a spread in a build is in
// that build, whatever else contains it), then the wide region, then a
// family, then nothing. Returns {kind, i} with `i` the build or family
// index, so the star's border colour and the list's group heading are read
// off ONE classification rather than two that could disagree.
function _wbOwnWhere(pay, block, i) {
  var b = _wbBuildOf(pay.bp, block, i);
  if (b >= 0 && block.builds[b].role !== 'wide') return { kind: 'build', i: b };
  for (var w = 0; w < block.builds.length; w++) {
    if (block.builds[w].role !== 'wide') continue;
    var wm = pay.bp.regions[block.builds[w].region].mask;
    if (wm && _wbBit(_wbMask(wm), i)) return { kind: 'wide', i: w };
  }
  var fams = _wbFamilies(pay, block);
  for (var f = 0; f < fams.length; f++) {
    if (fams[f].mask && _wbBit(_wbMask(fams[f].mask), i)) {
      return { kind: 'family', i: f };
    }
  }
  return { kind: 'none', i: -1 };
}

// The colour that classification is drawn in. A build takes its own hue; the
// wide region takes Build 1's at the tint its ring is drawn in; a family
// takes its seed standout's marker colour, the colour of the ring it is
// already drawn as; nothing takes the muted grey the population uses.
function _wbOwnColorOf(pay, block, bcol, colors, w) {
  if (w.kind === 'build' || w.kind === 'wide') {
    return _wbBuildCol(block, bcol, w.i, colors.line);
  }
  if (w.kind === 'family') {
    return _wbFamilyColor(_wbFamilies(pay, block)[w.i], colors);
  }
  return colors.below;
}

function _wbOwnColor(pay, block, bcol, colors, i) {
  return _wbOwnColorOf(pay, block, bcol, colors,
                       _wbOwnWhere(pay, block, i));
}

// The reader-facing name of that classification. "only" on the wide and
// family headings because both contain build members too, and a heading
// that did not say so would look like a fourth build.
function _wbOwnGroupName(pay, block, w) {
  if (w.kind === 'build') return _wbBuildName(block, w.i);
  if (w.kind === 'wide') return _wbBuildName(block, w.i) + ' only';
  if (w.kind === 'family') {
    return _wbFamilyName(_wbFamilies(pay, block)[w.i]) + ' only';
  }
  return 'In no build';
}

// What one owned spread's hover says about where it sits. The build's own
// guarantee sentence when a build holds it; otherwise the region or family
// that does, named, so a star outside every build never reads as bare.
function _wbOwnSide(pay, block, scen, i) {
  var w = _wbOwnWhere(pay, block, i);
  if (w.kind === 'build') return _wbBuildSide(pay, block, w.i, scen);
  if (w.kind === 'wide') {
    return _wbBuildSide(pay, block, -1, scen) + '; inside ' +
           _wbBuildName(block, w.i);
  }
  if (w.kind === 'family') {
    var f = _wbFamilies(pay, block)[w.i];
    return _wbBuildSide(pay, block, -1, scen) + '; inside the ' +
           _wbFamilyName(f).charAt(0).toLowerCase() +
           _wbFamilyName(f).slice(1) + ' (' + _wbFamilyCounts(f) +
           ', not a build)';
  }
  return _wbBuildSide(pay, block, -1, scen);
}

// ---- round 8 item 3(b): "Your collection", grouped by build -------------
// The stars say WHERE each owned spread sits; this says WHICH spreads those
// are, in one place, grouped the way the reader's question is shaped ("what
// have I already got for Build 1?"). Drawn from the same collection state
// and the same classification the stars use, so the two cannot disagree,
// and re-rendered whenever the collection or the Build-criteria preset
// changes. Hidden outright when the collection is empty.
function _wbYours(root, pay, block, wins, den) {
  var box = root.querySelector('.wb-yours');
  if (!box) return;
  function clear() { box.hidden = true; box.innerHTML = ''; }
  if (!state.ownedByIv || !block || !pay.bp) return clear();
  var groups = [], byKey = {};
  function bucket(w) {
    var k = w.kind + ':' + w.i;
    if (!byKey[k]) {
      byKey[k] = { w: w, rows: [] };
      groups.push(byKey[k]);
    }
    return byKey[k];
  }
  var n = 0;
  for (var key in state.ownedByIv) {
    var i = parseInt(key, 10);
    if (!(i >= 0 && i < DATA.nIvs)) continue;
    var recs = state.ownedByIv[i];
    // The CURRENT CP, only when the collection actually knows one. A manual
    // entry typed with the level field blank knows neither a level nor a
    // current CP -- ``mon.cp`` is 0 there, and printing "CP 0" beside a
    // spread is worse than printing nothing (headless probe, 2026-09-17).
    // The page's own FITTED CP is not a substitute: it is what the spread
    // would be at the cap, not what the reader's mon is now.
    var cps = [];
    for (var r = 0; r < recs.length; r++) {
      var mon = recs[r].mon || {};
      if (mon.level == null || !(mon.cp > 0)) continue;
      if (cps.indexOf(mon.cp) < 0) cps.push(mon.cp);
    }
    var bits = [ 'SP #' + DATA.spRanks[i],
                 'wins ' + wins[i] + ' of ' + den ];
    if (cps.length) bits.push('CP ' + cps.join('/'));
    bucket(_wbOwnWhere(pay, block, i)).rows.push({
      iv: _wbIvStr(i), sp: DATA.spRanks[i],
      text: _wbIvStr(i) + ' (' + bits.join(', ') + ')' });
    n++;
  }
  if (!n) return clear();
  var bcol = _wbBuildColors(root, pay.bp), colors = _wbColors(root, pay);
  var rank = { build: 0, wide: 1, family: 2, none: 3 };
  groups.sort(function (a, b) {
    return (rank[a.w.kind] - rank[b.w.kind]) || (a.w.i - b.w.i);
  });
  var out = ['<p class="wb-mem-head">Your collection, by build</p>'];
  for (var g = 0; g < groups.length; g++) {
    var grp = groups[g];
    grp.rows.sort(function (a, b) { return a.sp - b.sp; });
    out.push('<p class="wb-yours-head"><span class="wb-yours-dot" ' +
             'style="background:' +
             _wbOwnColorOf(pay, block, bcol, colors, grp.w) + '"></span>' +
             escapeHtml(_wbOwnGroupName(pay, block, grp.w)) + ' (' +
             grp.rows.length + ')</p><ul class="wb-yours-list">');
    for (var rr = 0; rr < grp.rows.length; rr++) {
      out.push('<li>' + escapeHtml(grp.rows[rr].text) + '</li>');
    }
    out.push('</ul>');
  }
  box.innerHTML = out.join('');
  box.hidden = false;
}

// Legend hover isolates a group, the same affordance the main scatter has.
// Scoped to this panel and guarded per legend node (Plotly's d3 join reuses
// them across react calls).
function _wbWireLegend(panel, ops) {
  var attempts = 0;
  var gen = (panel._wbLegendGen || 0) + 1;
  panel._wbLegendGen = gen;
  // Read at EVENT time, not captured: Plotly's d3 join reuses legend nodes
  // across react calls, so a handler wired under "the line" would otherwise
  // restore that view's opacities after the reader switched to "the rungs".
  panel._wbOps = ops;
  function tryAttach() {
    if (panel._wbLegendGen !== gen) return;
    var items = panel.querySelectorAll('.legend .traces');
    if (items.length === 0 && attempts < 50) { attempts++; setTimeout(tryAttach, 100); return; }
    items.forEach(function(el, idx) {
      if (el._wbWired) return;
      el._wbWired = true;
      el.style.cursor = 'pointer';
      el.addEventListener('mouseenter', function() {
        var cur = panel._wbOps || [];
        var ti = _legendTraceIndex(el, idx);
        for (var j = 0; j < cur.length; j++) {
          Plotly.restyle(panel, { 'marker.opacity': (j === ti) ? 1 : 0.03 }, [j]);
        }
      });
      el.addEventListener('mouseleave', function() {
        var cur = panel._wbOps || [];
        for (var j = 0; j < cur.length; j++) {
          Plotly.restyle(panel, { 'marker.opacity': cur[j] }, [j]);
        }
      });
    });
  }
  tryAttach();
}

// ---------------------------------------------------------------------------
// "Which one to build?" v4: BUILDS
// ---------------------------------------------------------------------------
// The section's primary object is now 2-3 BUILDS -- regions of the IV grid --
// selected under the page's Build criteria preset. Python renders every
// preset's tables and sentences server-side (one hidden .wb-preset block
// each) and ships the numbers this file needs in pay.bp; nothing here
// formats a threshold or writes a sentence about the data.
//
// The knob drives exactly three things, and the note under the control strip
// says so: this section, the Matchup clusters "all scenarios" partition, and
// the scatter's Shields = "All (by build criteria)" entry. Everything else on
// the page counts all nine shield scenarios equally.

var WB_PRESET_SEL = 'build-criteria-sel';
var WB_HASH_KEY = 'bc';

// The active preset key. The page-level <select> is the single source of
// truth (the section, the clusters section and the scatter all read it), and
// the payload's own default is the fallback for a page that emitted no knob.
function wbPreset(pay) {
  var sel = document.getElementById(WB_PRESET_SEL);
  var v = sel ? sel.value : null;
  if (pay && pay.bp) {
    if (v && pay.bp.presets[v]) return v;
    return pay.bp.default;
  }
  return v;
}
window.wbPreset = wbPreset;

function wbPresetBlock(pay) {
  var k = wbPreset(pay);
  return (pay && pay.bp && k) ? pay.bp.presets[k] : null;
}

// Matchups won per IV, weighted by a per-scenario weight vector. Same win
// predicate and the same flat (iv, scenario, opponent) decoding as wbWins and
// as the main plot's winsPvpoke mode; only the weights are new. Every shipped
// preset weights 0 or 1, so the result is an integer count.
var _wbWWinsCache = {};
function wbWinsWeighted(mi, mode, weights) {
  var key = mi + SCORE_KEY_SEP + mode + SCORE_KEY_SEP + weights.join('');
  if (_wbWWinsCache[key]) return _wbWWinsCache[key];
  var g = SCORES[mi + SCORE_KEY_SEP + mode];
  if (!g) return null;
  var nO = DATA.nOpponents, nS = DATA.nScenarios, n = DATA.nIvs;
  var out = new Float64Array(n);
  for (var iv = 0; iv < n; iv++) {
    var c = 0, base0 = iv * nS * nO;
    for (var sj = 0; sj < nS; sj++) {
      var w = weights[sj] || 0;
      if (!w) continue;
      var base = base0 + sj * nO;
      for (var oi = 0; oi < nO; oi++) { if (isWin(g[base + oi])) c += w; }
    }
    out[iv] = c;
  }
  _wbWWinsCache[key] = out;
  return out;
}
window.wbWinsWeighted = wbWinsWeighted;

// How many matchups the weighted y-axis is out of.
function wbWeightedDen(weights) {
  var s = 0;
  for (var i = 0; i < weights.length; i++) s += (weights[i] || 0);
  return s * DATA.nOpponents;
}

// One colour per build, from the section's CSS custom properties with the
// payload's light-theme values as the deliberate fallback (same pattern as
// WB_FALLBACK above).
function _wbBuildColors(root, bp) {
  var cs = getComputedStyle(root), out = [];
  var fb = (bp && bp.colors) || [];
  for (var k = 0; k < 3; k++) {
    var got = cs.getPropertyValue('--wb-b' + k).trim();
    out.push(got || fb[k] || '#7a4fc0');
  }
  return out;
}

// Which build (index into block.builds) holds spread i, or -1.
function _wbBuildOf(bp, block, i) {
  for (var b = 0; b < block.builds.length; b++) {
    var m = bp.regions[block.builds[b].region].mask;
    if (m && _wbBit(_wbMask(m), i)) return b;
  }
  return -1;
}

function _wbBuildName(block, b) {
  var roles = { primary: 'Build 1 (primary)', fork: 'Build 2 (fork)',
                rank1: 'Build 3 (bulk)', wide: 'Build 1 wide' };
  return roles[block.builds[b].role] || ('Build ' + (b + 1));
}

// A lighter tint of one build colour, for the wide region drawn under Build
// 1. Alpha, not a mix toward a fixed white: the panel has a light and a dark
// theme and a hard-coded blend would be invisible on one of them.
function _wbTint(col) {
  var m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec((col || '').trim());
  if (!m) return col;
  return 'rgba(' + parseInt(m[1], 16) + ',' + parseInt(m[2], 16) + ','
         + parseInt(m[3], 16) + ',0.40)';
}

// The colour for one payload build. The wide region is not a build a reader
// picks, so it borrows the PRIMARY's colour at a lighter tint rather than
// taking a fourth hue the legend would read as a third build.
function _wbBuildCol(block, bcol, k, fallback) {
  var role = block.builds[k] && block.builds[k].role;
  if (role === 'wide') {
    var pi = 0;
    for (var j = 0; j < block.builds.length; j++) {
      if (block.builds[j].role === 'primary') { pi = j; break; }
    }
    return _wbTint(bcol[pi] || fallback);
  }
  return bcol[k] || fallback;
}

// Marker geometry of the wide region's CONTAINMENT RING. A larger hollow
// marker (scattergl paints '-open' symbols with marker.color) drawn around
// EVERY one of the region's members, under everything else, so a build's
// members read as solid dots inside rings and the spreads only the wider
// rule reaches read as rings with a faint centre. Through round 6 the wide
// trace carried only the spreads no build held, which drew "Build 1 wide" as
// a region BESIDE Build 1 instead of around it (2026-09-17 round 7 item 3).
var WB_RING_SYMBOL = 'circle-open';
var WB_RING_SIZE = 9;

// ---- round 8 item 1: the FAMILY marker ----------------------------------
// A family is the region grown around a standout that sits in no build. It
// is NOT a build and it is not the wide region either, so it must be
// readable as neither: it takes no build hue (it is drawn in its own
// standout's marker colour, so the ring and the marker at its centre read as
// one object) and it does not reuse the wide region's plain open circle. An
// open circle with a centre dot, one size larger than the wide ring, is a
// mark nothing else on this panel draws.
var WB_FAM_SYMBOL = 'circle-open-dot';
var WB_FAM_SIZE = 12;

// Section-plot geometry (round 8 item 4). The panel is one full-width row
// with its legend underneath it; these are the pixel quantities that layout
// is built from, named once so the panel's CSS height, its bottom margin and
// its legend anchor cannot drift apart.
var WB_PANEL_H = 400;      // panel height with a single legend row
var WB_PLOT_T = 8;         // top margin
var WB_LEG_PER_ROW = 3;    // legend keys a wide panel fits across (a GUESS)
var WB_LEG_ROW_H = 18;     // one wrapped legend row
var WB_LEG_GAP = 44;       // x-axis title + breathing room above the legend
var WB_LEG_PAD = 6;        // below the last legend row
// The PLOT AREA is the invariant of this layout: the legend grows the panel
// downward and never eats the plot. Everything else is derived from it.
var WB_PLOT_AREA = WB_PANEL_H - WB_PLOT_T -
                   (WB_LEG_GAP + WB_LEG_PAD + WB_LEG_ROW_H);

// The height the legend's wrapped keys NEED, in px, or 0 before it exists.
// ``_fullLayout.legend._height`` is the right reading and the drawn
// background rect is the wrong one: Plotly caps a horizontal legend's drawn
// height at HALF the graph's height and makes the overflow a scroll box, so
// the rect reports the cap (303px inside a 608px graph whose legend really
// wants 342) and a layout sized from it converges on the cap instead of on
// the content. ``_height`` is the uncapped content height and does not move
// when the panel grows (measured in headless Chrome, 2026-09-17: 342 at
// graph heights 608, 900 and 1000). The rect is kept as a fallback for a
// Plotly that stops exposing ``_height``, and it is never worse than the
// trace-count guess it replaces.
function _wbLegendHeight(panel) {
  var lg = panel && panel._fullLayout && panel._fullLayout.legend;
  if (lg && lg._height > 0) return lg._height;
  var g = panel && panel.querySelector && panel.querySelector('g.legend');
  if (g) {
    var bg = g.querySelector('rect.bg');
    if (bg) {
      var h = parseFloat(bg.getAttribute('height'));
      if (h > 0) return h;
    }
    if (g.getBBox) {
      try {
        var b = g.getBBox();
        if (b && b.height > 0) return b.height;
      } catch (e) { /* not laid out yet */ }
    }
  }
  return 0;
}

// The bottom margin (and so the panel height) a legend of this measured
// height needs. One place, so the first guess and the correction cannot
// disagree about what "room for the legend" means.
function _wbLegBottom(legH) {
  return WB_LEG_GAP + WB_LEG_PAD + Math.ceil(legH);
}

// Draw-measure-relayout. Deriving the legend's height from the TRACE COUNT
// is wrong at any width where Plotly fits fewer keys per row than
// WB_LEG_PER_ROW guesses, or where wrapLegendName gives a key two or three
// lines: on a 604px-wide panel (a 900px viewport) an eleven-key legend needs
// 342px and the count formula reserved 72, so six keys -- both standout
// keys, both most-winning-member keys and the SP1 key among them -- fell
// outside the plot's own overflow:hidden. Clipped keys are not merely
// invisible: elementFromPoint misses them, so legend-hover isolation is dead
// for exactly the marks a reader most wants isolated (2026-09-17 round 8
// review). So the count is only the FIRST GUESS; the legend's real height is
// measured after the draw and the panel is grown to hold it, with the PLOT
// AREA as the invariant.
//
// The redraw is a relayout carrying ``autosize``, NOT a second
// ``Plotly.react``: react does not re-read the graph div's height at all
// (measured in headless Chrome -- style.height 685 -> 900 left
// _fullLayout.height at 608 through react and a tick), while
// ``relayout(gd, {autosize: true})`` picks the new container height up
// synchronously and leaves the responsive WIDTH behaviour alone, which
// setting layout.height outright would not.
//
// Converges in one correction: the legend's content height is a function of
// the panel's WIDTH, which a height change does not move. The pass cap is a
// guard, not a search.
function _wbFitLegend(panel, layout) {
  for (var pass = 0; pass < 4; pass++) {
    var legH = _wbLegendHeight(panel);
    if (!legH) return pass;
    var legB = _wbLegBottom(legH);
    if (Math.abs(legB - layout.margin.b) <= 1) return pass;
    layout.margin.b = legB;
    layout.legend.y = -WB_LEG_GAP / WB_PLOT_AREA;
    panel.style.height = (WB_PLOT_T + WB_PLOT_AREA + legB) + 'px';
    Plotly.relayout(panel, { autosize: true, 'margin.b': legB,
                             'legend.y': layout.legend.y });
  }
  return 4;
}

// One family's name, exactly as the table row and the standout paragraph
// spell it. Formatted here rather than shipped because it is three payload
// numbers in a fixed order, not a sentence -- the rule string inside it IS
// authored in Python and travels verbatim.
function _wbFamilyCounts(f) {
  return f.size + ' spreads, guarantees ' + f.nG + ' of ' + f.nDec;
}

function _wbFamilyName(f) {
  return 'Family around ' + String(f.iv).split('@')[0];
}

// A family's colour is its SEED standout's marker colour: the most-winning
// spread is drawn in mark2 and the highest-average-score spread in mark1
// (see _wbBuildMarks), and the ring around each has to match the mark at its
// centre or the two read as unrelated objects.
function _wbFamilyColor(f, colors) {
  return (f.kind === 'score') ? colors.mark1 : colors.mark2;
}

// Silent when the rule reproduces the member list exactly, which is the only
// case in which "the rule IS the region" needs no qualifying. The describer
// accepts a rule from 0.95 fidelity up and prefers the SIMPLEST over the most
// faithful, so an inexact one has to say so on the mark a reader hovers, the
// same way the table row's fidelity clause does (2026-09-17 round 8 review).
function _wbFamilyFid(f) {
  if (typeof f.jac !== 'number' || f.jac >= 0.999) return '';
  return ' (the rule is a ' + Math.round(f.jac * 100) +
         '% description of it, not an exact one)';
}

// One ring trace per family, over every member of the region. Drawn UNDER
// everything else for the same reason the wide ring is: they are context
// around points other traces own, and a larger marker on top would hide both
// the build member inside it and the standout at the centre.
// One preset's families, resolved. The preset carries indices into the
// payload's single family table (the regions are preset-independent, so the
// masks travel once).
function _wbFamilies(pay, block) {
  var out = [], idx = (block && block.families) || [];
  var all = (pay.bp && pay.bp.families) || [];
  for (var k = 0; k < idx.length; k++) {
    if (all[idx[k]]) out.push(all[idx[k]]);
  }
  return out;
}

function _wbFamilyTraces(pay, block, L, wins, colors, den) {
  var out = [], fams = _wbFamilies(pay, block);
  for (var k = 0; k < fams.length; k++) {
    var f = fams[k];
    if (!f.mask) continue;
    var m = _wbMask(f.mask);
    var nm = _wbFamilyName(f);
    // The name only, for the same reason the builds' keys are (round 9 item
    // 4): the family's rule and its two counts are on its row in the table.
    var t = _wbTrace(wrapLegendName(nm, 34),
                     _wbFamilyColor(f, colors), WB_FAM_SYMBOL, WB_FAM_SIZE, 1);
    var side = 'in the ' + nm.charAt(0).toLowerCase() + nm.slice(1) + ' -- ' +
               f.size + ' spreads guaranteeing ' + f.nG + ' of ' + f.nDec +
               ' decision matchups, not a build' + _wbFamilyFid(f);
    for (var i = 0; i < DATA.nIvs; i++) {
      if (!_wbBit(m, i)) continue;
      var mp = _wbXY(L, i, wins);
      t.x.push(mp[0]); t.y.push(mp[1]);
      t.text.push(_wbHover(i, L, wins, side, den));
    }
    if (t.x.length) out.push(t);
  }
  return out;
}

// The builds view: every spread, coloured by the build it belongs to.
function _wbBuildGroups(pay, L, wins, colors, den, root, scen) {
  var bp = pay.bp, block = wbPresetBlock(pay);
  var bcol = _wbBuildColors(root, bp);
  var none = _wbTrace('In no build', colors.below, 'circle', 3, 0.45);
  var wideIdx = -1;
  for (var w0 = 0; w0 < block.builds.length; w0++) {
    if (block.builds[w0].role === 'wide') wideIdx = w0;
  }
  var ivsOf = [];
  var ts = block.builds.map(function(b, k) {
    // On the stats plane the legend has to carry the ATTACK cut: it is part
    // of the rule and the two axes cannot show it, so two spreads at the
    // same defense and HP can sit on opposite sides of a boundary the plot
    // draws nothing for.
    // Round 9 item 4: the key is the NAME. The rule used to ride in it
    // ("Build 1 wide: Atk >= 148.70 and Def + 1.7*HP >= 301.928 (644)"),
    // which is why the legend needed 141-341 px and the keys overprinted;
    // the table directly above carries the rule on the build's own row.
    var note = (_wbPlaneMode === 'stats' && b.plane && b.plane.atkNote)
             ? (' [' + b.plane.atkNote + ', not on these axes]') : '';
    var ring = (k === wideIdx);
    return _wbTrace(_wbBuildName(block, k) + note,
                    _wbBuildCol(block, bcol, k, colors.line),
                    ring ? WB_RING_SYMBOL : 'circle',
                    ring ? WB_RING_SIZE : 4, ring ? 1 : 0.85);
  });
  ivsOf.push([]);
  for (var q = 0; q < ts.length; q++) ivsOf.push([]);
  // One side string per build, not per point: it is fixed by (build,
  // scenario) and _wbGuaranteedInScen walks every decision cell to build
  // it. Nine minis x 4096 spreads is where that started to show.
  var sides = {};
  function sideFor(b, ringed) {
    var kk = ((b < 0) ? 'x' : b) + (ringed ? '|w' : '');
    if (sides[kk] == null) {
      var sd = _wbSideWithWide(pay, block, b, scen, wideIdx, ringed);
      // Round 9 item 4 took the rule OUT of the legend key (it is on the
      // build's row in the table directly above, and in the key it needed
      // 141-341 px of legend). It belongs on the hover instead: a reader who
      // points at a coloured dot is asking what region it is in.
      if (b >= 0 && block.builds[b] && block.builds[b].desc) {
        sd += ' -- ' + block.builds[b].desc;
      }
      sides[kk] = sd;
    }
    return sides[kk];
  }
  // The wide region's membership mask, read BEFORE the per-point pass: a
  // build's OWN members can sit inside the region, and their hover is the
  // only place that containment shows where the dots hide the rings.
  var wmask = null;
  if (wideIdx >= 0) {
    var wreg = bp.regions[block.builds[wideIdx].region];
    wmask = (wreg && wreg.mask) ? _wbMask(wreg.mask) : null;
  }
  for (var i = 0; i < DATA.nIvs; i++) {
    var b = _wbBuildOf(bp, block, i);
    // A spread the WIDE rule reaches and no build holds gets the muted
    // centre dot; its ring comes from the pass below. Its hover leads with
    // "in none of the builds" and then names the region -- one point, two
    // labels, in the order that cannot be misread.
    var extra = (b === wideIdx);
    var ringed = (b >= 0) && !!(wmask && _wbBit(wmask, i));
    var t = (b < 0 || extra) ? none : ts[b];
    var mp = _wbXY(L, i, wins);
    t.x.push(mp[0]); t.y.push(mp[1]);
    ivsOf[(b < 0 || extra) ? 0 : b + 1].push(i);
    t.text.push(_wbHover(i, L, wins, sideFor(b, ringed), den));
  }
  // The ring trace gets EVERY member of the region, which is the whole
  // point of the change -- so its legend count IS the region's own size,
  // the number the table row and the summary line give for it, and the
  // round-6 "(x of N not already in a build)" phrasings are gone. Its own
  // hover names the region and nothing else: hovering a RING is the gesture
  // that asks about the region.
  if (wideIdx >= 0) {
    var wt = ts[wideIdx], wside = sideFor(wideIdx, false);
    for (var wi = 0; wmask && wi < DATA.nIvs; wi++) {
      if (!_wbBit(wmask, wi)) continue;
      var wp = _wbXY(L, wi, wins);
      wt.x.push(wp[0]); wt.y.push(wp[1]);
      ivsOf[wideIdx + 1].push(wi);
      wt.text.push(_wbHover(wi, L, wins, wside, den));
    }
  }
  none.name += ' (' + none.x.length + ')';
  for (var k2 = 0; k2 < ts.length; k2++) {
    ts[k2].name = wrapLegendName(ts[k2].name + ' (' + ts[k2].x.length + ')',
                                 34);
  }
  if (_wbPlaneMode === 'stats') {
    // Attack is the stat neither axis carries, so it is the marker size.
    // The muted "in no build" points stay small and flat: sizing 3000 grey
    // points by a stat the reader is not being asked about is noise.
    for (var k4 = 0; k4 < ts.length; k4++) {
      // The ring keeps ONE size on both planes: it is a containment
      // outline, and scaling it by attack would let the dot inside it poke
      // through the ring at the high-attack end.
      if (k4 === wideIdx) continue;
      ts[k4].marker.size = _wbAtkSizes(L, ivsOf[k4 + 1]);
    }
  }
  // Rings FIRST, so they draw under every other trace: they are the context
  // around Build 1, and the larger marker on top would hide both the build
  // it is context for and the muted centre the extras need.
  var out = [];
  // The family rings sit under even the wide ring: a family can contain
  // members of a build AND spreads the wide rule reaches, and it is the
  // outermost annotation of the three.
  out = out.concat(_wbFamilyTraces(pay, block, L, wins, colors, den));
  if (wideIdx >= 0) out.push(ts[wideIdx]);
  out.push(none);
  for (var k3 = 0; k3 < ts.length; k3++) {
    if (k3 !== wideIdx && ts[k3].x.length) out.push(ts[k3]);
  }
  return { traces: out, missing: false };
}

// Every MARKED spread the builds views draw on top of the population: SP1,
// each build's most-winning member, and the two standouts. Factored out of
// wbRenderRoot for round 7, because the nine per-scenario minis mark the
// same spreads with the same symbols and colours -- a second hand-kept copy
// of this block is exactly how the panel and the minis would drift. `mini`
// drops the on-point IV labels (no room on a 200px panel); nothing else
// differs.
function _wbBuildMarks(pay, pblock, L, wins, colors, den, scen, root, mini) {
  var out = [];
  var bcolors = _wbBuildColors(root, pay.bp);
  var br1 = _wbIvIdx(_wbIvTriple(pay.bp.rank1.iv));
  var br1t = _wbMarkTrace('Stat-product rank-1 (SP1)', br1, colors.mark1,
                          'diamond', L, wins,
                          'the stat-product rank-1 spread; ' +
                          _wbBuildSide(pay, pblock,
                                       _wbBuildOf(pay.bp, pblock, br1), scen),
                          den, mini);
  if (br1t) out.push(br1t);
  for (var mb = 0; mb < pblock.builds.length; mb++) {
    // The wide region gets no triangle: the caption calls each triangle "a
    // build's most-winning member", and it is not a build -- it is the
    // region around Build 1 (2026-09-17 round 5).
    if (pblock.builds[mb].role === 'wide') continue;
    var mwi = _wbIvIdx(_wbIvTriple(pblock.builds[mb].mostWinning.iv));
    var mwt = _wbMarkTrace(
      _wbBuildName(pblock, mb) + ': most-winning member', mwi,
      bcolors[mb] || colors.mark2, 'triangle-up', L, wins,
      'wins the most matchups inside ' + _wbBuildName(pblock, mb) +
      ' in the shields this preset counts (' +
      pblock.builds[mb].mostWinning.wins + ' of ' +
      pblock.builds[mb].mostWinning.den + ')', den, mini);
    if (mwt) out.push(mwt);
  }
  var gbi2 = _wbIvIdx(_wbIvTriple(pay.bp.gridBest.iv));
  if (gbi2 >= 0) {
    // Named by its SCOPE, not just "the most": it is the all-nine winner,
    // so under a narrower preset it is deliberately not the highest point
    // on an axis that is counting fewer matchups.
    // Round 6: the canonical short name leads, the scope follows it
    // in brackets, so the legend, the section head, the card title and
    // the threat chips all start with the same words.
    var gbScope = 'all ' + DATA.nScenarios + ' shield scenarios';
    var gbt2 = _wbMarkTrace('Most matchups won (' + gbScope + ')',
                            gbi2, colors.mark2, 'square-open', L, wins,
                            'wins the most matchups over ' + gbScope +
                            ' (' + pay.bp.gridBest.wins + '); ' +
                            _wbBuildSide(pay, pblock,
                                         _wbBuildOf(pay.bp, pblock, gbi2),
                                         scen),
                            den, mini);
    if (gbt2) out.push(gbt2);
  }
  // The section's SECOND standout. It is the maximum of the main
  // scatter's own default y axis, which this panel does not draw, so it
  // gets a marker of its own rather than being left to look like any
  // other point (2026-09-16 review item 3).
  var bsi = pay.bp.bestScore ? _wbIvIdx(_wbIvTriple(pay.bp.bestScore.iv)) : -1;
  if (bsi >= 0 && bsi !== gbi2) {
    var bst = _wbMarkTrace('Highest avg battle score', bsi,
                           colors.mark1, 'x-open', L, wins,
                           'the highest Avg Battle Score on the scatter (' +
                           pay.bp.bestScore.avgStr + '); ' +
                           _wbBuildSide(pay, pblock,
                                        _wbBuildOf(pay.bp, pblock, bsi),
                                        scen),
                           den, mini);
    if (bst) out.push(bst);
  }
  _wbStaggerLabels(out);
  return out;
}

// Alternate the on-point labels top / bottom, in the order the marks were
// built, so two named spreads at the same rank do not print over each other.
function _wbStaggerLabels(traces) {
  var k = 0;
  for (var i = 0; i < traces.length; i++) {
    var t = traces[i];
    if (!t || t.mode !== 'markers+text') continue;
    t.textposition = (k % 2) ? 'bottom center' : 'top center';
    k++;
  }
}

// ---- the section's own all-shield-scenarios grid (round 7 item 2) --------
// Nine minis, one per baked scenario, on the section plot's x axis
// (stat-product rank, reversed) against matchups won in THAT scenario out of
// the opponent pool. Same builds, same colours, same marked spreads as the
// panel above it -- the question is where each build's members band above
// the rest, shield state by shield state, which the weighted panel answers
// once and this answers nine times. Win counts come from the page's own
// score grid through wbWins (win = score > 500): no new payload.
//
// Offered on the builds view only. The stats view has its own plane and the
// three threshold views are not coloured by builds, so a grid of
// build-coloured minis under either would be a legend the panel above does
// not carry.
var WB_MINI_SCALE = 0.62;   // the panel's marker sizes are for 400px, not 200
function _wbMiniShrink(traces) {
  for (var i = 0; i < traces.length; i++) {
    var m = traces[i].marker;
    if (m && typeof m.size === 'number') {
      m.size = Math.max(2, Math.round(m.size * WB_MINI_SCALE * 10) / 10);
    }
    if (m && m.line && typeof m.line.width === 'number') m.line.width = 1;
  }
}

var _wbAllScenKey = null;   // what the minis on screen were built for

// Plotly.purge before dropping the divs, not innerHTML = '' alone. These are
// scattergl panels, so each one holds a WebGL context; a browser caps how
// many are live (~16) and drops the oldest when the cap is passed. Nine
// minis beside the main scatter, the section panel and the three cluster
// panels is close enough to that cap that LEAKING a set on every Show /
// Build-criteria change would blank plots elsewhere on the page.
function _wbClearMinis(grid) {
  var kids = Array.prototype.slice.call(grid.children);
  for (var i = 0; i < kids.length; i++) {
    if (window.Plotly && Plotly.purge) { try { Plotly.purge(kids[i]); } catch (e) {} }
  }
  grid.innerHTML = '';
}

// The ONE nine-mini grid (round 9, DRY rule D2). It replaces this section's
// build-coloured grid AND the Matchup clusters section's cluster-coloured
// one, which drew the same nine scenarios on the same x axis one directly
// above the other. Two toggles carry the difference between them: what is on
// Y (matchups won in that shield state, or avg battle score there) and what
// the colour is (this preset's builds, or that scenario's matchup clusters).
function _wbAllScenMode(box, cls, dflt) {
  var sel = box ? box.querySelector('select.' + cls) : null;
  return (sel && sel.value) || dflt;
}

// The clusters colouring, for one scenario, as Plotly traces. Reads the
// Matchup clusters section's OWN payload: no second clustering runs here, and
// a scenario it did not cluster falls back to one muted trace rather than
// inventing groups.
function _wbClusterMiniTraces(si, L, y) {
  var mPay = _mcPayloadPage();
  var lbl = scenLabel(si);
  var sc = (mPay && mPay.scens) ? mPay.scens[lbl] : null;
  if (!sc || !sc.labels) return null;
  var out = [];
  for (var c = 0; c < sc.k; c++) {
    out.push({x: [], y: [], mode: 'markers', type: 'scattergl',
              hoverinfo: 'skip',
              marker: {size: 2.5, opacity: 0.6,
                       color: mPay.palette[c % mPay.palette.length]}});
  }
  for (var i = 0; i < DATA.nIvs; i++) {
    var c1 = sc.labels[i];
    if (c1 == null || !out[c1]) continue;
    out[c1].x.push(L.spRanks[i]);
    out[c1].y.push(y[i]);
  }
  return out;
}

function _wbAllScen(root, box, force) {
  var grid = box ? box.querySelector('.wb-allscen-grid') : null;
  var capEl = box ? box.querySelector('.wb-allscen-caption') : null;
  var ctl = box ? box.querySelector('.wb-allscen-ctl') : null;
  if (!grid) return;
  var pay = _wbPayload(root);
  var pblock = pay ? wbPresetBlock(pay) : null;
  var on = !!(pblock && _wbBoxView(box) === 'allscen');
  grid.hidden = !on;
  if (capEl) capEl.hidden = !on;
  if (ctl) ctl.hidden = !on;
  if (!on) { _wbClearMinis(grid); _wbAllScenKey = null; return; }
  var yMode = _wbAllScenMode(box, 'wb-allscen-y', 'wins');
  var cMode = _wbAllScenMode(box, 'wb-allscen-color', 'build');
  var key = [wbActivePresetKey(), pay.mi, pay.mode, DATA.nScenarios,
             yMode, cMode].join('|');
  if (!force && key === _wbAllScenKey && grid.children.length) return;
  _wbAllScenKey = key;
  _wbClearMinis(grid);
  // Every mini is the RANK plane whatever the panel last drew: the flag is
  // global and a stale 'stats' would silently swap both axes.
  _wbPlaneMode = 'rank';
  var L = wbLevelArrays(), colors = _wbColors(root, pay);
  var chrome = plotChrome(), den = DATA.nOpponents;
  var scenSel = box.querySelector('select.wb-scen');
  for (var si = 0; si < DATA.nScenarios; si++) {
    (function(si) {
      var d = document.createElement('div');
      d.className = 'wb-allscen-mini';
      d.style.cursor = 'pointer';
      grid.appendChild(d);
      var wins = wbWins(pay.mi, pay.mode, si);
      if (!wins) return;
      var y = wins, yTitle = 'Wins (of ' + den + ')';   // one shield state
      if (yMode === 'score') {
        var sc = computeScenarioAvgPure(pay.mi, si);
        if (sc) { y = sc; yTitle = 'Avg battle score'; }
      }
      var traces = null;
      if (cMode === 'cluster') traces = _wbClusterMiniTraces(si, L, y);
      if (!traces) {
        var sObj = { idx: si, label: scenLabel(si) };
        traces = _wbBuildGroups(pay, L, y, colors, den, root, sObj).traces
          .concat(_wbBuildMarks(pay, pblock, L, y, colors, den, sObj,
                                root, true));
        _wbMiniShrink(traces);
      }
      Plotly.newPlot(d, traces, {
        title: { text: scenLabel(si) + ' shields', font: { size: 11 } },
        margin: { l: 42, r: 6, t: 24, b: 28 }, showlegend: false,
        xaxis: { autorange: 'reversed', showgrid: false, zeroline: false,
                 title: { text: 'SP rank', font: { size: 9 } } },
        // The denominator on the axis, not only in the caption: each mini
        // counts ONE shield state, so its scale is the opponent pool and not
        // the panel's (scenarios x opponents) above it.
        yaxis: { showgrid: true, gridcolor: chrome.grid, zeroline: false,
                 title: { text: yTitle, font: { size: 9 } } },
        paper_bgcolor: chrome.paper, plot_bgcolor: chrome.plot,
        font: { color: chrome.font, size: 9 },
        hoverlabel: { bgcolor: chrome.hoverBg, bordercolor: chrome.hoverBorder }
      }, { displayModeBar: false, responsive: true });
      // Clicking a mini narrows the section's own Shield-scenario control to
      // it -- the gesture the clusters grid carried, kept.
      d.addEventListener('click', function() {
        if (!scenSel) return;
        scenSel.value = scenLabel(si);
        wbSelectView(scenSel);   // -> _wbSyncScen: every handle, one value
      });
    })(si);
  }
}

// The outlines the stats view draws around each build, as Plotly shapes.
// One case per describable shape, and NOTHING for a build no rule fits: an
// outline its members do not fill would be the one dishonesty this view
// cannot afford, so those builds are their points and nothing else.
function _wbPlaneShapes(block, bcol, L) {
  var dLo = Infinity, dHi = -Infinity, hLo = Infinity, hHi = -Infinity, i;
  for (i = 0; i < DATA.nIvs; i++) {
    if (L.ivDef[i] < dLo) dLo = L.ivDef[i];
    if (L.ivDef[i] > dHi) dHi = L.ivDef[i];
    if (L.ivHp[i] < hLo) hLo = L.ivHp[i];
    if (L.ivHp[i] > hHi) hHi = L.ivHp[i];
  }
  var dPad = (dHi - dLo) * 0.03 || 1, hPad = (hHi - hLo) * 0.03 || 1;
  var x0b = dLo - dPad, x1b = dHi + dPad, y0b = hLo - hPad, y1b = hHi + hPad;
  var shapes = [];
  function line(x0, y0, x1, y1, col) {
    // A zero-length segment draws nothing. Consecutive HP steps that share
    // one defense floor emitted one per shared pair (2026-09-16 round-3
    // review: one dead shape on the flat staircase, three on the 1v1 one).
    if (x0 === x1 && y0 === y1) return;
    shapes.push({ type: 'line', x0: x0, y0: y0, x1: x1, y1: y1,
                  line: { color: col, width: 2 } });
  }
  for (var k = 0; k < block.builds.length; k++) {
    var pl = block.builds[k].plane;
    var col = _wbBuildCol(block, bcol, k, '#888');
    if (!pl || pl.kind === 'none') continue;
    if (pl.kind === 'box') {
      var x0 = (pl.def && pl.def[0] != null) ? pl.def[0] : x0b;
      var x1 = (pl.def && pl.def[1] != null) ? pl.def[1] : x1b;
      var y0 = (pl.hp && pl.hp[0] != null) ? pl.hp[0] : y0b;
      var y1 = (pl.hp && pl.hp[1] != null) ? pl.hp[1] : y1b;
      shapes.push({ type: 'rect', x0: x0, y0: y0, x1: x1, y1: y1,
                    line: { color: col, width: 2 },
                    fillcolor: 'rgba(0,0,0,0)' });
    } else if (pl.kind === 'stair') {
      // steps are [HP, defense needed at that HP]. HP is an integer stat, so
      // each step owns the half-open band around its own HP row, and the
      // boundary is the vertical segments plus the connectors between them.
      var st = pl.steps.slice().sort(function (a, b) { return a[0] - b[0]; });
      for (var j = 0; j < st.length; j++) {
        var h = st[j][0], d = st[j][1];
        var yTop = (j === st.length - 1) ? y1b : (h + st[j + 1][0]) / 2;
        var yBot = (j === 0) ? (h - 0.5) : (h + st[j - 1][0]) / 2;
        line(d, yBot, d, yTop, col);
        if (j < st.length - 1) line(d, yTop, st[j + 1][1], yTop, col);
      }
    } else if (pl.kind === 'line') {
      // Def + k*HP >= c, so the boundary is Def = c - k*HP.
      line(pl.c - pl.k * y0b, y0b, pl.c - pl.k * y1b, y1b, col);
    }
  }
  return shapes;
}

// How many of one region's guaranteed cells sit in one shield scenario.
// Reads the region's guarantee bits against the payload's decision-cell
// axis, whose first field is the scenario index -- the same packing the
// membership masks use, unpacked by the same two helpers.
function _wbGuaranteedInScen(bp, regionIdx, si) {
  var reg = bp.regions[regionIdx];
  if (!reg || !reg.bits) return null;
  var bits = _wbMask(reg.bits), n = 0;
  for (var c = 0; c < bp.cells.length; c++) {
    if (bp.cells[c][0] === si && _wbBit(bits, c)) n++;
  }
  return n;
}

// What membership buys, for a hover. Counts only: the cells themselves are
// listed in the server-rendered table two inches above, and a hover card is
// not where a reader reads 55 matchup names. With one shield scenario
// selected it answers for THAT scenario, which is the question the control
// just asked.
function _wbBuildSide(pay, block, b, scen) {
  // Not "the builds below": the builds table sits ABOVE the plot since the
  // section moved to the top of the page (round 7).
  if (b < 0) return 'in none of the builds';
  var bd = block.builds[b];
  if (scen) {
    var n = _wbGuaranteedInScen(pay.bp, bd.region, scen.idx);
    if (n != null) {
      return _wbBuildName(block, b) + ': guarantees ' + n +
             ' decision matchups in ' + scen.label + ' shields (' + bd.nG +
             ' over every scenario)';
    }
  }
  return _wbBuildName(block, b) + ': guarantees ' + bd.nG + ' of ' +
         pay.bp.nDecision + ' decision matchups (' + bd.nGmat + ' material)';
}

// A spread can wear TWO labels at once now that the wide region rings every
// one of its members: the build that holds it (or none) AND the region
// around it. Order matters -- "in none of the builds" comes FIRST for a
// spread the wide rule reaches that no build holds, so its hover can never
// read as membership in a build, and a build member inside the region gets
// the containment appended (where dots crowd, the ring under them is
// invisible, so the hover is the only place it shows).
function _wbSideWithWide(pay, block, b, scen, wideIdx, inWide) {
  if (!inWide || wideIdx < 0) return _wbBuildSide(pay, block, b, scen);
  var wname = _wbBuildName(block, wideIdx);
  if (b === wideIdx) {
    var w = _wbBuildSide(pay, block, wideIdx, scen)
              .replace(wname + ': guarantees', wname + ', which guarantees');
    return _wbBuildSide(pay, block, -1, scen) + '; inside ' + w;
  }
  return _wbBuildSide(pay, block, b, scen) + '; inside ' + wname;
}

// The UpSet panel: which named sets each candidate region is made of.
// Rows = the lattice's named sets (size and guaranteed cells in the label),
// columns = the selected builds plus the next few candidate regions. Bar =
// region size, the number above it = the decision matchups it guarantees,
// selected columns in their build's colour.
function _wbUpset(root, pay) {
  var host = root.querySelector('.wb-upset');
  if (!host || !pay.bp) return;
  var bp = pay.bp, block = wbPresetBlock(pay);
  if (!block) { host.innerHTML = ''; return; }
  var chrome = plotChrome();
  var bcol = _wbBuildColors(root, bp);
  var cols = block.cols, rows = block.lattice;
  var colOfBuild = {};
  for (var b = 0; b < block.builds.length; b++) {
    // The wide region has no UpSet column (col === null): it is not one of
    // the candidate regions the panel ranks.
    if (block.builds[b].col == null) continue;
    colOfBuild[block.builds[b].col] = b;
  }
  // Under a narrow preset the number ABOVE the bar is the weighted count --
  // the one the ranking used and the one the table and the prose lead with.
  // Drawing the all-nine count there made the ties invisible: nine regions
  // tie at 13 of the 16 1v1 cells on Shadow Sableye arm 0 while their
  // all-nine counts differ (2026-09-16 review).
  var flatPreset = (block.scens.length === pay.bp.scenLabels.length);
  var x = [], y = [], colors = [], texts = [], ticks = [];
  for (var c = 0; c < cols.length; c++) {
    x.push(c); y.push(cols[c].size);
    var bi = colOfBuild[c];
    colors.push(bi == null ? chrome.grid : (bcol[bi] || chrome.ink));
    texts.push((flatPreset ? cols[c].nG : cols[c].nGw) + '');
    ticks.push(cols[c].combo);
  }
  var bar = { type: 'bar', x: x, y: y, marker: { color: colors },
              text: texts, textposition: 'outside', cliponaxis: false,
              textfont: { size: 10, color: chrome.font },
              hoverinfo: 'text', name: 'spreads',
              hovertext: cols.map(function(cc, ci) {
                return (colOfBuild[ci] != null
                        ? _wbBuildName(block, colOfBuild[ci]) + '<br>' : '') +
                       cc.combo + ': ' + cc.size + ' spreads<br>' +
                       (flatPreset ? '' :
                        (cc.nGw + ' of the ' + block.nDecW +
                         ' decision matchups in the shields this preset ' +
                         'counts -- the number drawn above the bar, and ' +
                         'the one the ranking uses<br>')) +
                       cc.nG + ' decision matchups guaranteed over all ' +
                       pay.bp.scenLabels.length + ' scenarios (' +
                       cc.nGmat + ' material)<br>' +
                       (cc.memb ? 'sets ' + cc.memb.split('').join(' + ')
                                : 'constructed box, not an intersection'); }) };
  var dx = [], dy = [], dc = [];
  for (var r = 0; r < rows.length; r++) {
    for (var c2 = 0; c2 < cols.length; c2++) {
      var on = cols[c2].memb.indexOf(rows[r].key) >= 0;
      dx.push(c2); dy.push(r);
      var bi2 = colOfBuild[c2];
      dc.push(on ? (bi2 == null ? chrome.font : (bcol[bi2] || chrome.ink))
                 : chrome.grid);
    }
  }
  var dots = { type: 'scattergl', mode: 'markers', x: dx, y: dy,
               xaxis: 'x', yaxis: 'y2', hoverinfo: 'skip',
               marker: { size: 9, color: dc }, showlegend: false };
  // Two lines per row: the set's TARGET on the first, its counts on the
  // second. Plotly honours <br> in tick text, so this halves the width the
  // margin has to carry without dropping a word.
  var rowTicks = rows.map(function (rr) {
    return rr.key + ' ' + rr.short + '<br>' + rr.size + ' spreads / ' +
           rr.nG + ' guaranteed';
  });
  var widest = 0;
  rowTicks.forEach(function (t) {
    t.split('<br>').forEach(function (ln) {
      if (ln.length > widest) widest = ln.length;
    });
  });
  var tickMargin = Math.max(90, Math.min(300, Math.ceil(widest * 5.4) + 16));
  var layout = {
    barmode: 'group', showlegend: false,
    xaxis: { domain: [0, 1], anchor: 'y2', tickvals: x, ticktext: ticks,
             tickfont: { size: 9 }, showgrid: false, zeroline: false },
    yaxis: { domain: [0.52, 1], title: 'spreads in region',
             showgrid: true, gridcolor: chrome.grid, zeroline: false },
    yaxis2: { domain: [0, 0.46], tickvals: rows.map(function(_r, i) { return i; }),
              ticktext: rowTicks,
              tickfont: { size: 9 }, autorange: 'reversed',
              showgrid: false, zeroline: false },
    paper_bgcolor: chrome.paper, plot_bgcolor: chrome.plot,
    font: { color: chrome.font, size: 10 },
    // The left margin is MEASURED from the labels rather than fixed at
    // 230px: the pre-v5 rows ("A two-stat box for 0v1 Empoleon (665 spreads
    // / 42 guaranteed)") ran off the left edge of the plot and the reader
    // could not tell which set a row was (2026-09-16 review item 1). The
    // labels now wrap onto two lines, and the margin is the longest LINE at
    // the 9px tick font, which is ~5.4px per character in the stack Plotly
    // falls back to, plus room for the tick itself.
    margin: { t: 16, b: 30, l: tickMargin, r: 8 }
  };
  Plotly.react(host, [bar, dots], layout,
               { responsive: true, displayModeBar: false });
}

// The members list inside one build's expander: top N by stat product, then
// a control that renders the rest. Built in the browser from the region's
// membership mask and the page's own IV arrays, so a 318-spread build costs
// the page 512 bytes rather than 318 strings.
// v5 (2026-09-16 review item 7): the IV spreads and nothing else. The
// level and the stat-product rank were two columns of noise beside the one
// thing a reader is copying into the game's search bar, and at 25 rows they
// made the list three times as tall as the spreads it lists. The order is
// unchanged -- bulkiest first -- and the count is in the header above.
function _wbMemberRows(out, L, from, to, rows) {
  for (var k = from; k < to && k < rows.length; k++) {
    var i = rows[k];
    out.push(DATA.ivA[i] + '/' + DATA.ivD[i] + '/' + DATA.ivS[i]);
  }
}

// "Is mine in one of these?" -- the section's entry point to the page's own
// collection panel (round 9 item 3). It opens and scrolls to the ONE panel,
// so there is still one CSV loader (loadCollection) and one manual-entry
// form; the answer comes back into .wb-yours, under the builds table.
var _wbCameFromSection = false;

function wbOpenCollection(btn) {
  var panel = document.getElementById('collection-panel');
  if (!panel) return;
  if (panel.tagName === 'DETAILS') panel.open = true;
  // One-shot: the next successful load or manual add scrolls the reader
  // back to the answer, which is up here under the builds table. Round 9
  // sent them down and left them there (2026-09-19 round-10 review).
  _wbCameFromSection = true;
  panel.scrollIntoView({ block: 'center' });
  var ta = document.getElementById('collection-csv');
  if (ta && ta.focus) { try { ta.focus(); } catch (e) {} }
}
window.wbOpenCollection = wbOpenCollection;

// Called by wbRefresh once the collection has changed: if the reader got to
// the panel through the section's own entry point, bring them back to it.
function wbReturnFromCollection() {
  if (!_wbCameFromSection) return;
  _wbCameFromSection = false;
  var mine = document.querySelector('.wb-mine');
  if (mine && mine.scrollIntoView) {
    mine.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function wbRenderMembers(box, all) {
  var root = box.closest('.wb-root');
  var pay = root ? _wbPayload(root) : null;
  if (!pay || !pay.bp) return;
  var block = pay.bp.presets[box.getAttribute('data-preset')];
  if (!block) return;
  var bd = block.builds[parseInt(box.getAttribute('data-build'), 10)];
  if (!bd) return;
  var m = _wbMask(pay.bp.regions[bd.region].mask);
  var L = wbLevelArrays();
  var idx = [];
  for (var i = 0; i < DATA.nIvs; i++) if (_wbBit(m, i)) idx.push(i);
  idx.sort(function(a, b) { return L.spRanks[a] - L.spRanks[b]; });
  var topN = pay.bp.topN || 25;
  var show = all ? idx.length : Math.min(topN, idx.length);
  var out = [];
  _wbMemberRows(out, L, 0, show, idx);
  var html = out.join(', ');
  if (!all && idx.length > show) {
    html += ', <button type="button" class="wb-val" ' +
            'onclick="if(window.wbShowAllMembers)wbShowAllMembers(this)">' +
            'Show all ' + idx.length + '</button>';
  }
  box.innerHTML = html;
}

// Reveal the guarantee rows this scenario group shipped hidden. The rows
// are server-rendered (same _g_row_html as the visible ones), so this only
// unhides them -- the page never promises rows it does not carry.
//
// A group can carry TWO reveals -- the capped tail and the near-free tail
// (2026-09-16 review item 4) -- so the button names the class it owns in
// data-reveal and each one reveals only its own rows. Defaults to the
// capped tail's class, which is what the pre-v5 control did.
// One reveal, for the guarantee lists' hidden <li> rows AND the notable
// entries' inline "+N" spans (round 9 item 5). Scoped to the nearest list or,
// for an inline run, the button's own parent -- never the whole document, so
// two "+N" controls in one entry do not fire each other.
function wbMoreRows(btn) {
  var cls = btn.getAttribute('data-reveal') || 'wb-hid';
  var scope = btn.closest('ul') || btn.parentElement;
  if (!scope) return;
  scope.querySelectorAll('.' + cls).forEach(function(el) { el.hidden = false; });
  var own = btn.closest('li');
  if (own && own.classList.contains('wb-more')) own.hidden = true;
  else if (own && own.classList.contains('wb-free')) own.hidden = true;
  else btn.hidden = true;
}
window.wbMoreRows = wbMoreRows;

function wbShowAllMembers(btn) {
  var box = btn.closest('.wb-mem');
  if (box) wbRenderMembers(box, true);
}
window.wbShowAllMembers = wbShowAllMembers;

// "Compare these": stat-product rank-1 plus every build's most-winning
// member, in build order. The same widget the section's other Compare button
// fills, so a reader lands on one comparison table and not two.
function wbCompareBuilds(btn) {
  var root = btn.closest('.wb-root');
  var pay = root ? _wbPayload(root) : null;
  if (!pay || !pay.bp) return;
  var block = wbPresetBlock(pay);
  if (!block) return;
  var list = [];
  function push(iv) {
    var p = iv.split('@')[0].split('/');
    var t = [parseInt(p[0], 10), parseInt(p[1], 10), parseInt(p[2], 10)];
    for (var k = 0; k < list.length; k++) {
      if (list[k][0] === t[0] && list[k][1] === t[1] && list[k][2] === t[2]) return;
    }
    list.push(t);
  }
  push(pay.bp.rank1.iv);
  for (var b = 0; b < block.builds.length; b++) {
    // Not the wide region: it is not a build to build, so its most-winning
    // member is not a candidate the comparison table is about.
    if (block.builds[b].role === 'wide') continue;
    push(block.builds[b].mostWinning.iv);
  }
  // ... and the two standouts the block above names, so a reader who just
  // read "it is in none of the builds" and clicked Compare finds it here
  // (2026-09-16 review item 3). push() deduplicates, so a standout that IS
  // a build's most-winning member does not appear twice.
  var so = block.standouts || [];
  for (var t = 0; t < so.length; t++) push(so[t].iv);
  if (window.cmpSetCandidates) window.cmpSetCandidates(list);
  var span = btn.parentNode.querySelector('.wb-spreads');
  if (span) {
    span.textContent = list.map(function(t) {
      return t[0] + '/' + t[1] + '/' + t[2]; }).join(', ');
  }
  var sec = document.getElementById('cmp-section');
  if (sec) {
    sec.open = true;
    sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}
window.wbCompareBuilds = wbCompareBuilds;

// Fill the visible preset block's member lists. Called from the panel
// render, which is why it does NOT touch the summary line or the preset
// blocks' visibility: the Shield-scenario control re-renders the panel, and
// a control that rewrote the one sentence a reader reads would make the
// verdict depend on a dropdown they may never touch
// (tests/test_which_build_section.py pins that boundary).
function wbFillMembers(root) {
  root.querySelectorAll('.wb-preset:not([hidden]) .wb-mem').forEach(
    function(box) { wbRenderMembers(box, false); });
}

// Show the active preset's server-rendered block, hide the others, and put
// that preset's summary sentence in the collapsed <summary>. Every string
// here was authored and word-gated in Python; this only chooses which one.
// Called by the Build criteria knob and by the hash applied at load -- the
// two places a PRESET change comes from.
function wbApplyPreset(root) {
  var pay = _wbPayload(root);
  if (!pay || !pay.bp) return;
  var key = wbPreset(pay), block = pay.bp.presets[key];
  if (!block) return;
  root.querySelectorAll('.wb-preset').forEach(function(el) {
    el.hidden = (el.getAttribute('data-preset') !== key);
  });
  var head = root.querySelector('.wb-head');
  if (head && block.summary) head.textContent = block.summary;
  wbFillMembers(root);
}

// ---- the Build criteria knob -----------------------------------------------
// The knob drives exactly three surfaces, and the muted line under the
// control strip names them: this section, the Matchup clusters "all
// scenarios" partition, and the scatter's Shields = "All (by build
// criteria)" entry. Nothing else on the page re-weights.

// The selected preset key, from the page-level <select>.
function wbActivePresetKey() {
  var sel = document.getElementById(WB_PRESET_SEL);
  return sel ? sel.value : null;
}
window.wbActivePresetKey = wbActivePresetKey;

// The scenario INDICES the active preset weights, for the scatter.
function wbPresetScenIndices() {
  var root = _wbRoot();
  var pay = root ? _wbPayload(root) : null;
  var key = wbActivePresetKey();
  if (!pay || !pay.bp || !key || !pay.bp.presets[key]) return null;
  var want = pay.bp.presets[key].scens || [];
  var out = [];
  for (var si = 0; si < DATA.nScenarios; si++) {
    if (want.indexOf(scenLabel(si)) >= 0) out.push(si);
  }
  return out;
}
window.wbPresetScenIndices = wbPresetScenIndices;

// The same scenarios as words, for the scatter's y-axis title. Spelled the
// way the section's own plot spells them, so a reader flipping between the
// two meets one phrasing.
function wbPresetScenLabel() {
  var root = _wbRoot();
  var pay = root ? _wbPayload(root) : null;
  var key = wbActivePresetKey();
  if (!pay || !pay.bp || !key || !pay.bp.presets[key]) return null;
  var s = pay.bp.presets[key].scens || [];
  if (!s.length) return null;
  if (s.length === pay.bp.scenLabels.length) {
    return 'all ' + s.length + ' shield scenarios';
  }
  return s.join(' / ') + ' shields';
}
window.wbPresetScenLabel = wbPresetScenLabel;

// The Matchup clusters section's "all scenarios" option, re-pointed and
// re-labelled for the active preset. The label text comes from the clusters
// payload (Python spelled it); this only selects which one.
function wbSyncClusterAllOption() {
  document.querySelectorAll('.dd-mc-root').forEach(function(root) {
    var pay = _mcPayload(root);
    if (!pay || !pay.allByPreset) return;
    var allKey = pay.allKey || 'all';
    var cur = root.getAttribute('data-mc-scen') || pay['default'];
    // Only the combined entry moves with the Build criteria setting; a
    // single shield state is the same partition under every setting. The
    // K / silhouette numbers the old <option> carried are printed in the
    // block's own headline, which this re-render replaces.
    if (cur === allKey) mcSetScenario(root, allKey);
  });
}

// The whole switch: remember it in the URL hash, re-render the section, the
// clusters "all scenarios" view and -- when the scatter is on the weighted
// entry -- the scatter.
function wbSetPreset(key) {
  var sel = document.getElementById(WB_PRESET_SEL);
  if (sel && key && sel.value !== key) sel.value = key;
  _wbSyncCriteriaHandles(sel ? sel.value : key);
  _wbWriteHash(sel ? sel.value : key);
  var root = _wbRoot();
  if (root) {
    // ALWAYS apply the preset: it swaps which server-rendered block is
    // visible and which summary sentence the collapsed line carries, and
    // wbRenderRoot deliberately does not touch either (the Shield-scenario
    // control shares that path). Then redraw the panel if it is on screen,
    // or drop the rendered flag so the next open redraws it.
    wbApplyPreset(root);
    if (root.open && root.offsetParent !== null) wbRenderRoot(root);
    else root.removeAttribute('data-wb-rendered');
  }
  wbSyncClusterAllOption();
  if (state.scenarioMode === 'wbavg' && typeof updateView === 'function') {
    updateView();
  }
}
window.wbSetPreset = wbSetPreset;

// The section's MIRROR of the Build criteria control (round 9 item 1). Two
// handles, one setter: the strip's <select id="build-criteria-sel"> and the
// section's <select class="wb-criteria"> both call wbSetPreset, and this puts
// the chosen value on every handle that is not the one the reader touched.
// The URL hash stays the single source of truth across a reload.
function _wbSyncCriteriaHandles(key) {
  if (!key) return;
  document.querySelectorAll('select.wb-criteria').forEach(function(m) {
    if (m.value !== key) m.value = key;
  });
}

// Persist the preset in the URL hash so a link carries it. Same hash the
// histogram deep links use, so the two must not clobber each other: only
// this key is rewritten.
function _wbWriteHash(key) {
  if (!key) return;
  var parts = (location.hash || '').replace(/^#/, '').split('&')
                .filter(function(p) { return p && p.indexOf(WB_HASH_KEY + '=') !== 0; });
  parts.push(WB_HASH_KEY + '=' + encodeURIComponent(key));
  try {
    history.replaceState(null, '', location.pathname + location.search +
                         '#' + parts.join('&'));
  } catch (e) { location.hash = parts.join('&'); }
}

// Apply the hash's preset (if any) to every surface, at load.
function wbApplyPresetHash() {
  var sel = document.getElementById(WB_PRESET_SEL);
  if (!sel) return;
  var m = (location.hash || '').match(
    new RegExp('[#&]' + WB_HASH_KEY + '=([^&]+)'));
  var want = m ? decodeURIComponent(m[1]) : null;
  if (want) {
    for (var i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value === want) { sel.value = want; break; }
    }
  }
  _wbSyncCriteriaHandles(sel.value);
  var root = _wbRoot();
  if (root) wbApplyPreset(root);
  wbSyncClusterAllOption();
}
window.wbApplyPresetHash = wbApplyPresetHash;

// Draw ONE plot box. Round 9 split this out of wbRenderRoot so the section's
// three figures -- the main tabbed one, the single-stat line expander's and
// the "Why these regions" expander's -- go through one renderer rather than
// three: same tab dispatch, same Shield-scenario control, same caption path.
function wbRenderBox(root, box) {
  if (!root || !box) return;
  var pay = _wbPayload(root);
  var panel = box.querySelector('.wb-panel');
  if (!pay || !panel) return;
  var L = wbLevelArrays();
  var scen = _wbScen(box, pay);
  var view0 = _wbBoxView(box) || (pay.views[0] && pay.views[0].id);
  var pblock = wbPresetBlock(pay);
  // The builds view's y axis is the PRESET-WEIGHTED win count -- the same
  // number the builds were ranked on -- unless the section's own Shield
  // scenario control has narrowed the panel to one scenario, which moves the
  // axis and nothing else (the selection stays the preset's).
  // The stats view re-draws the BUILDS on the defense / HP plane, so it
  // shares their grouping, their colours and their weighted win count; only
  // the two axes and the region outlines are its own.
  _wbPlaneMode = (view0 === 'stats' && pblock) ? 'stats' : 'rank';
  var weighted = ((view0 === 'builds' || view0 === 'stats')
                  && !scen && pblock);
  var wins = weighted ? wbWinsWeighted(pay.mi, pay.mode, pblock.weights)
                      : wbWins(pay.mi, pay.mode, scen ? scen.idx : null);
  // The y-axis denominator moves with the control and nothing else does:
  // over every scenario it is (scenarios x opponents), inside one it is the
  // opponent pool, and under the weighted axis it is (weighted scenarios x
  // opponents).
  var den = weighted ? wbWeightedDen(pblock.weights)
          : scen ? DATA.nOpponents : (DATA.nScenarios * DATA.nOpponents);
  var cap = box.querySelector('.wb-caption');
  if (!wins) {
    panel.innerHTML = '';
    if (cap) cap.textContent = 'This dive did not bake the score grid this ' +
      'panel reads, so it is not drawn.';
    root.setAttribute('data-wb-rendered', '1');
    return;
  }
  // The merged nine-mini grid is a FIGURE OF ITS OWN, not a colouring of
  // the panel: on its tab the panel is empty and hidden, the grid is the
  // figure, and the box's one caption (filled below) is the grid's.
  if (view0 === 'allscen' && pblock) {
    panel.hidden = true;
    var gcap = box.querySelector('.wb-caption');
    if (gcap) {
      for (var gv = 0; gv < pay.views.length; gv++) {
        if (pay.views[gv].id === 'allscen') gcap.textContent = pay.views[gv].caption;
      }
    }
    wbFillMembers(root);
    _wbYours(root, pay, pblock, wins, den);
    _wbAllScen(root, box, false);
    return;
  }
  panel.hidden = false;
  var view = view0;
  var colors = _wbColors(root, pay);
  var g = ((view === 'builds' || (view === 'stats' && pblock)) && pblock)
        ? _wbBuildGroups(pay, L, wins, colors, den, root, scen)
        : _wbGroups(pay, view, L, wins, colors, scen, den);
  var traces = g.traces.slice();
  // The trade is a whole-grid claim, so its marked spreads keep saying their
  // side of the PAGE's line even under a single scenario; the two threshold
  // views say their side of the line actually drawn.
  var line = (view === 'trade') ? _wbActiveLine(pay, null)
                                : _wbActiveLine(pay, scen);
  // The example spreads are named for where they sit relative to the PAGE's
  // line ("highest stat product above the line", "bulkiest above the line"),
  // and under a single shield scenario these two views draw a DIFFERENT line.
  // Both halves of that are wrong on screen: on a scenario with no line the
  // keys claim one exists, and on a scenario WITH one the marker is plotted
  // inside the "Below <scenario line>" group while its own key says "above
  // the line" -- the contradiction is visible in the plot. So the examples
  // are dropped for any single scenario on the threshold views. Rank-1 stays:
  // it is the spread a reader already owns and its key makes no claim about
  // any line.
  var hideExamples = !!(scen && (view === 'line' || view === 'rungs'));
  // Whose absence it is. On a page with NO line the emptiness is a property
  // of the page, not of the selected shield state (which may well carry a
  // threshold of its own -- the rank-1 caption says so), and the collection
  // overlay must not assert otherwise.
  var noLine = (scen && pay.hasFloor)
                    ? ('no line in ' + scen.label + ' shields')
                    : 'no line on this page';
  if (pay.hasFloor && (view === 'line' || view === 'rungs' || view === 'trade')) {
    var r1i = _wbIvIdx(pay.rank1.iv);
    // Every marked point says its side of the line as well as its role: the
    // role alone ("the stat-product rank-1 spread") is the one hover on the
    // panel that did not answer the question the panel is about.
    var r1t = _wbMarkTrace('Stat-product rank-1 (SP1)', r1i, colors.mark1, 'diamond',
                           L, wins, 'the stat-product rank-1 spread; ' +
                           (line ? _wbSideAt(L, line, r1i) : noLine), den);
    if (r1t) traces.push(r1t);
    for (var e = 0; hideExamples ? false : e < pay.examples.length; e++) {
      var ei = _wbIvIdx(pay.examples[e].iv);
      // The reader label, not the brief's selection rule: the rules are
      // written in the audit's vocabulary ("most cells won among clearers
      // with SP >= 95%"), which is exactly what the voice gate keeps out of
      // the prose this legend sits under.
      var elabel = pay.examples[e].label || pay.examples[e].rule;
      var et = _wbMarkTrace(_wbIvStr(ei) + ': ' + elabel, ei, colors.mark2,
                            'triangle-up', L, wins,
                            elabel + '; ' + _wbSideAt(L, line, ei), den);
      if (et) traces.push(et);
    }
    if (pay.bestAbove && !hideExamples) {
      var bi = _wbIvIdx(pay.bestAbove.iv);
      var bt = _wbMarkTrace(_wbIvStr(bi) + ': ' + pay.bestAbove.label, bi,
                            colors.mark2, 'triangle-down', L, wins,
                            pay.bestAbove.label + '; ' + _wbSideAt(L, line, bi),
                            den);
      if (bt) traces.push(bt);
    }
  }
  if ((view === 'builds' || view === 'stats') && pblock) {
    traces = traces.concat(
      _wbBuildMarks(pay, pblock, L, wins, colors, den, scen, root, false));
  }
  if (!pay.hasFloor && view === 'rank1') {
    var nr1 = _wbIvIdx(pay.rank1.iv);
    var nr1t = _wbMarkTrace('Stat-product rank-1 (SP1)', nr1, colors.mark1, 'diamond',
                            L, wins, 'the stat-product rank-1 spread', den);
    if (nr1t) traces.push(nr1t);
    var gbi = _wbIvIdx(pay.gridBest.iv);
    if (gbi !== nr1) {
      var gbt = _wbMarkTrace('Most matchups won', gbi, colors.mark2,
                             'triangle-up', L, wins, 'wins the most matchups',
                             den);
      if (gbt) traces.push(gbt);
    }
  }
  var ownSide = null, ownBorder = null;
  if ((view === 'builds' || view === 'stats') && pblock) {
    // On the builds view a pasted mon's question is "is it in a build, and
    // what does that get me" -- not which side of the line it is on. Round 8
    // item 3 widens that answer past the builds: the wide region and the
    // family are exactly what a reader told "in no build" asks about next,
    // and the star's border carries the same classification as a colour.
    ownSide = function(i) { return _wbOwnSide(pay, pblock, scen, i); };
    var ownCols = _wbBuildColors(root, pay.bp);
    ownBorder = function(i) {
      return _wbOwnColor(pay, pblock, ownCols, colors, i);
    };
  }
  var ownT = _wbOwnedTrace(pay, L, wins, line, den, noLine, ownSide,
                           ownBorder);
  if (ownT) traces.push(ownT);

  var chrome = plotChrome();
  // ---- round 8 item 4: the legend lives BELOW the plot, always ----------
  // Through round 7 a legend of more than six keys went VERTICAL on the
  // right of the panel. That was affordable while the panel shared its row
  // with the UpSet and was already narrow; now the scatter owns the
  // section's full width, and a right-hand legend spends that width on
  // text. Wrapping a horizontal legend costs HEIGHT, so the panel grows
  // downward to hold the legend and the plot area above it is never
  // squeezed. The legend's top is pinned WB_LEG_GAP px under the x-axis
  // title in paper units, and the bottom margin is exactly deep enough to
  // hold the gap plus the legend. The row count below is only a FIRST GUESS
  // at the legend's height, close enough to keep the corrective redraw to
  // one; _wbFitLegend then measures the legend and sizes the panel from
  // that (round 8 review -- the guess is wrong by 3x at 900px).
  var legRows = Math.max(1, Math.ceil(traces.length / WB_LEG_PER_ROW));
  var legB = _wbLegBottom(legRows * WB_LEG_ROW_H);
  var panelH = WB_PLOT_T + WB_PLOT_AREA + legB;
  panel.style.height = panelH + 'px';
  var legY = -WB_LEG_GAP / WB_PLOT_AREA;
  var layout = {
    xaxis: (_wbPlaneMode === 'stats')
      ? { title: 'Defense', showgrid: true, gridcolor: chrome.grid,
          zeroline: false }
      : { title: 'Stat product rank', autorange: 'reversed',
          showgrid: false, zeroline: false },
    // The denominator in the title: the main scatter's own "Wins vs PvPoke
    // default" axis honours the Shields dropdown, so a reader flipping
    // between the two meets two different scales. This one never moves, and
    // says what it is out of.
    yaxis: (_wbPlaneMode === 'stats')
      ? { title: 'HP', showgrid: true, gridcolor: chrome.grid,
          zeroline: false }
      : { title: (weighted
              ? (pblock.scens.length === DATA.nScenarios
                 ? ('Matchups won, all ' + DATA.nScenarios +
                    ' shield scenarios (of ' + den + ')')
                 : ('Matchups won in ' + pblock.scens.join(' / ') +
                    ' shields (of ' + den + ')'))
              : scen
              ? ('Matchups won in ' + scen.label + ' shields (of ' +
                 DATA.nOpponents + ' opponents)')
              : ('Matchups won (of ' +
                 (DATA.nScenarios * DATA.nOpponents) + ')')),
          showgrid: true, gridcolor: chrome.grid, zeroline: false },
    paper_bgcolor: chrome.paper, plot_bgcolor: chrome.plot,
    font: { color: chrome.font, size: 11 },
    margin: { t: WB_PLOT_T, b: legB, l: 56, r: 8 },
    showlegend: true,
    legend: { orientation: 'h', y: legY, yanchor: 'top', x: 0,
              xanchor: 'left', bgcolor: chrome.legendBg,
              bordercolor: chrome.legendBorder, borderwidth: 1 },
    hoverlabel: { bgcolor: chrome.hoverBg, bordercolor: chrome.hoverBorder }
  };
  if (_wbPlaneMode === 'stats' && pblock) {
    layout.shapes = _wbPlaneShapes(pblock, _wbBuildColors(root, pay.bp), L);
  }
  if (g.missing) {
    layout.annotations = [{
      text: 'No cluster labels apply to this view.',
      showarrow: false, xref: 'paper', yref: 'paper', x: 0.5, y: 0.5,
      font: { color: chrome.font, size: 12 }
    }];
  }
  Plotly.react(panel, traces, layout,
               { responsive: true, displayModeBar: false });
  // ...and now that the legend exists, let ITS height set the panel's.
  _wbFitLegend(panel, layout);
  _wbWireLegend(panel, traces.map(function(t) { return t.marker.opacity; }));
  if (cap) {
    var capText = '';
    for (var vi = 0; vi < pay.views.length; vi++) {
      if (pay.views[vi].id === view) capText = pay.views[vi].caption;
    }
    if (scen && scen.entry.captions && scen.entry.captions[view] != null) {
      // No per-scenario caption for a view that draws every scenario:
      // the view's own caption stands (scenario_payload skips it).
      capText = scen.entry.captions[view] || capText;
    }
    // The one caption this section does not author: a scenario the Matchup
    // clusters section could not cluster is explained in THAT section's own
    // words, counts and all, rather than in a second sentence about the
    // same absence.
    if (scen && view === 'clusters') {
      var mcP = _mcPayloadPage();
      var msc = _wbMcApplies(pay, mcP) && mcP.scens && mcP.scens[scen.label];
      if (_wbMcApplies(pay, mcP) && !msc) {
        var dg = mcP.degenerate && mcP.degenerate[scen.label];
        if (dg) capText = (dg.display || scen.label) + ': ' + dg.reason + '.';
      } else if (msc) {
        // The all-scenario clusters caption is a FINDING (K, silhouette,
        // where the split lands against the printed line); the per-scenario
        // one was a pointer. The clusters payload carries that scenario's own
        // K and its depth-1 split as a Python-formatted string, so the
        // per-scenario caption can say the same kind of thing without this
        // file formatting a threshold.
        // `display` is the clusters section's own spelling and ALREADY
        // carries the word ("0v1 shields"); only the bare label needs it.
        capText = "The Matchup clusters section's own groups for " +
          (msc.display || (scen.label + ' shields')) + ": " + msc.k +
          " groups" + (msc.split ? ", split at " + msc.split : "") +
          ", drawn here on the same axes.";
      }
    }
    // The one number a rank-1 caption can add client-side, and the one the
    // negative page's reader is actually after: what rank-1 wins in THIS
    // shield state, and whether anything beats it.
    if (scen && view === 'rank1') {
      var r1x = _wbIvIdx(pay.rank1.iv), best = -1;
      for (var q = 0; q < wins.length; q++) if (wins[q] > best) best = wins[q];
      if (r1x >= 0) {
        capText += ' In ' + scen.label + ' shields the stat-product rank-1 ' +
          'spread wins ' + wins[r1x] + ' of ' + den +
          ', and the most any spread wins is ' + best + '.';
      }
    }
    cap.textContent = capText;
  }
  if (pay.bp) wbFillMembers(root);
  // "Your collection", grouped by build: same collection state and same
  // classification the stars above it use, so the two cannot disagree. It
  // re-renders here, which is every place the collection or the preset can
  // have changed.
  _wbYours(root, pay, pblock, wins, den);
  // The per-scenario minis last: they reuse this render's grouping helpers,
  // and a Build-criteria change or a tab change has to move them too.
  _wbAllScen(root, box, false);
}

// Draw every box of the section that is on screen. A box inside a closed
// expander is skipped and picked up by the toggle hook: Plotly sizes to zero
// inside a closed <details>.
function wbRenderRoot(root) {
  if (!root) return;
  var boxes = root.querySelectorAll('.wb-plotbox');
  for (var i = 0; i < boxes.length; i++) {
    if (_inClosedDetails(boxes[i])) continue;
    wbRenderBox(root, boxes[i]);
  }
  // The set panel is not a tab of any figure -- round 9 moved it into the
  // "Why these regions" expander with the clusters, where it answers the
  // question it is about. It is drawn once per root render, and only when
  // that expander is open (Plotly sizes to zero inside a closed <details>).
  var pay = _wbPayload(root);
  var up = root.querySelector('.wb-upset');
  if (pay && pay.bp && up && !_inClosedDetails(up) && up.offsetParent !== null) {
    _wbUpset(root, pay);
  }
  root.setAttribute('data-wb-rendered', '1');
}

// The section's ONE scenario setter (DRY rule D2). The figure box, the two
// expanders' boxes and the clusters subsection are four panels that all
// answer "in which shield state?", and round 9 gave each its own unlinked
// handle: narrowing the figure to 1v1 left the other three on "all" with no
// signal. One value, every handle.
function _wbSyncScen(root, value) {
  if (!root || !value) return;
  root.querySelectorAll('select.wb-scen').forEach(function(s) {
    if (s.value !== value) s.value = value;
  });
  root.querySelectorAll('.dd-mc-root').forEach(function(mc) {
    var pay = _mcPayload(mc);
    if (!pay) return;
    var want = (value === WB_ALL_SCEN) ? (pay.allKey || 'all') : value;
    // A scenario the clusters pass never computed leaves them where they
    // are rather than blanking the panels.
    if (!mc.querySelector('.dd-mc-scen-block[data-scen="' +
                          (window.CSS && CSS.escape ? CSS.escape(want) : want) +
                          '"]')) return;
    mcSetScenario(mc, want);
  });
}

// The section's ONE view dispatcher (DRY rule D2). Every control that
// changes what a figure shows calls it: the three tab strips, each box's
// Shield-scenario select, and the merged grid's two toggles. A tab carries
// its view in data-view and owns the box it sits in; a select carries none
// and only asks for a redraw.
function wbSelectView(el) {
  var root = (el.closest && el.closest('.wb-root')) || _wbRoot();
  if (!root) return;
  var box = el.closest ? el.closest('.wb-plotbox') : null;
  var view = el.getAttribute ? el.getAttribute('data-view') : null;
  if (box && view) {
    box.setAttribute('data-wb-view', view);
    var tabs = box.querySelectorAll('.wb-tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].setAttribute('aria-selected', tabs[i] === el ? 'true' : 'false');
    }
  }
  // A Shield-scenario change is a SECTION-level change: every open panel
  // and the clusters subsection follow it, so the whole root redraws.
  if (el.classList && el.classList.contains('wb-scen')) {
    _wbSyncScen(root, el.value);
    wbRenderRoot(root);
    return;
  }
  if (box) wbRenderBox(root, box);
  else wbRenderRoot(root);
}
window.wbSelectView = wbSelectView;

// Collection load / clear and theme switches both change what the panel
// should draw. A closed section drops its rendered flag instead, so it picks
// the change up on its next open (Plotly sizes to zero inside a closed
// <details>).
function wbRefresh() {
  var root = _wbRoot();
  if (!root || !root.hasAttribute('data-wb-rendered')) return;
  if (root.offsetParent !== null && root.open) wbRenderRoot(root);
  else root.removeAttribute('data-wb-rendered');
  wbReturnFromCollection();
}
window.wbRefresh = wbRefresh;

// "Compare these spreads": prefill the page's Compare candidates widget with
// rank-1 plus the spreads this section names, then open it and scroll there.
function wbCompare(btn) {
  var root = btn.closest('.wb-root') || _wbRoot();
  var pay = root ? _wbPayload(root) : null;
  if (!pay) return;
  var list = [pay.rank1.iv];
  if (pay.hasFloor) {
    for (var i = 0; i < pay.examples.length; i++) list.push(pay.examples[i].iv);
    // The spread the headline names as winning the most above the line, when
    // the example rules' stat-product filter left it out: a reader who read
    // that sentence and clicked this button did not find it in the widget.
    if (pay.bestAbove) list.push(pay.bestAbove.iv);
  } else if (pay.gridBest) {
    list.push(pay.gridBest.iv);
  }
  if (window.cmpSetCandidates) window.cmpSetCandidates(list);
  var sec = document.getElementById('cmp-section');
  if (sec) {
    sec.open = true;
    sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}
window.wbCompare = wbCompare;

// The printed line value expands to the spreads that reach it: top 25 by
// stat product, then a control for the rest. Built here rather than baked:
// a 2220-row table server-side would be ~150 KB of markup per moveset file
// for a list most readers never open, and every column it needs is already
// in DATA.
function _wbClearerRows(L, from, to, rows) {
  var h = '';
  for (var i = from; i < to && i < rows.length; i++) {
    var iv = rows[i];
    h += '<tr><td>' + DATA.ivA[iv] + '/' + DATA.ivD[iv] + '/' + DATA.ivS[iv] +
         '</td><td>' + Number(L.ivAtk[iv]).toFixed(2) +
         '</td><td>' + Number(L.ivDef[iv]).toFixed(2) +
         '</td><td>' + L.ivHp[iv] +
         '</td><td>L' + Number(L.ivLv[iv]).toFixed(1) +
         '</td><td>#' + L.spRanks[iv] + '</td></tr>';
  }
  return h;
}

function wbRenderClearers(box, all) {
  var root = _wbRoot();
  var pay = root ? _wbPayload(root) : null;
  if (!pay || !pay.hasFloor) return;
  var L = wbLevelArrays();
  var mask = _wbMask(pay.rungs[0].mask);
  var rows = [];
  for (var i = 0; i < DATA.nIvs; i++) { if (_wbBit(mask, i)) rows.push(i); }
  rows.sort(function(a, b) { return L.spRanks[a] - L.spRanks[b]; });
  var shown = all ? rows.length : Math.min(pay.topN || 25, rows.length);
  var h = '<p style="margin:0 0 6px">The ' + rows.length + ' spreads at or above ' +
    pay.axisWord + ' ' + pay.printed + ', by stat product' +
    (all ? '' : ' (top ' + shown + ')') + ':</p>' +
    '<table><thead><tr><th>IV</th><th>Atk</th><th>Def</th><th>HP</th>' +
    '<th>Level</th><th>SP rank</th></tr></thead><tbody>' +
    _wbClearerRows(L, 0, shown, rows) + '</tbody></table>';
  if (!all && rows.length > shown) {
    h += '<button type="button" class="wb-btn" style="margin-top:6px" ' +
         'onclick="wbShowAllClearers(this)">Show all ' + rows.length + '</button>';
  }
  box.innerHTML = h;
}

function wbToggleClearers(btn) {
  var root = _wbRoot();
  if (!root) return;
  var box = root.querySelector('.wb-clearers');
  if (!box) return;
  if (!box.hidden) { box.hidden = true; return; }
  box.hidden = false;
  wbRenderClearers(box, false);
}
window.wbToggleClearers = wbToggleClearers;

function wbShowAllClearers(btn) {
  var root = _wbRoot();
  var box = root && root.querySelector('.wb-clearers');
  if (box) wbRenderClearers(box, true);
}
window.wbShowAllClearers = wbShowAllClearers;

// Lazy render on first open, and a resize when an already-rendered panel
// comes back into view -- same two reasons as the cluster panels.
document.addEventListener('toggle', function(ev) {
  var det = ev.target;
  if (!det || !det.open || !det.classList) return;
  var root = det.classList.contains('wb-root') ? det : det.closest('.wb-root');
  if (!root) return;
  if (!root.hasAttribute('data-wb-rendered')) {
    if (root.offsetParent !== null) wbRenderRoot(root);
    return;
  }
  // An inner expander (the single-stat line, "Why these regions") that just
  // opened holds a plot box Plotly could not size while it was closed, and a
  // set panel that was never drawn. Draw what is now on screen, then resize
  // what was already drawn.
  wbRenderRoot(root);
  root.querySelectorAll('.wb-panel').forEach(function(p) {
    if (p.children.length && window.Plotly && Plotly.Plots) {
      try { Plotly.Plots.resize(p); } catch (e) {}
    }
  });
}, true);

// ---- Re-theme the canvases when the theme picker flips data-theme ----
//
// theme.py's picker sets data-theme on <html>. CSS re-themes instantly, but
// Plotly is holding literals resolved at its last build, so the charts would
// keep the OLD theme's chrome until some other interaction happened to
// re-render them. Drop the memo and re-run the render entry points:
// updateView() redraws the scatter and calls updateHistograms() itself;
// mcRefreshAll() redraws the cluster panels.
//
// Guarded on MutationObserver and wrapped per call so a page that renders no
// scatter (or an environment without the API) simply keeps its initial
// resolution instead of throwing during a theme switch.
if (typeof MutationObserver !== 'undefined' && document.documentElement) {
  new MutationObserver(function() {
    _themeVarCache = {};
    try { updateView(); } catch (e) {}
    try { mcRefreshAll(); } catch (e) {}
    try { wbRefresh(); } catch (e) {}
  }).observe(document.documentElement,
             {attributes: true, attributeFilter: ['data-theme']});
}
