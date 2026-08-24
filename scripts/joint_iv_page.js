// Joint-IV robustness page app.
// DOM + Plotly driver for the standalone pages built by
// scripts/build_joint_iv_page.py -- one per analyzed focal/opponent pair.
// BOTH species, both movesets and the focal breakpoint move are read from
// TL_DATA; no species or move name is spelled anywhere in this file.
//
// HARD RULE: this file contains NO analysis numbers. Every number it
// paints comes from the TL_DATA blob the builder injects. When a piece
// of TL_DATA is absent (the sim was still baking at build time), the
// panel that needs it renders a VISIBLE "not baked yet" placeholder --
// never a silent fallback, never a made-up number.
//
// TL_DATA keys consumed (the builder/assembly contract):
//   meta {generated, engine, gamemaster, total_sims, scenarios[9],
//         grids{label:{focal_fast,focal_charged,bait,shape,pretty}},
//         movesets{label:pretty}, opp_moveset, provenance, notes[],
//         named_builds[{label,ivs[3]}], missing[]}
//   thievul / licki -- the focal / opponent side tables (opaque slot
//         names, frozen across pairs; they name the ARRAYS, not a species)
//         {ivs[[a,d,s]], level[], cp[], atk[], def[], hp[]}
//   cov {label: {all:[4096*9], top512:[4096*9]}}
//   meta_wins {pool_n, wins_11:[4096], note}
//   won_b64 {label: {si: base64(gzip(packbits(4096x4096 bool)))}}
//   breakpoints {sp_damage_vs_licki_rank1:[4096], tables[], verdicts[]}
//   reco {cards[{title, subtitle, spread, rank, lines[], caveats[],
//         metrics{cov512_11, meta_wins_11}}], pool_n, notes[]}
//         -- the TL;DR band renders the first 3-4 cards' metrics VERBATIM
//   collection {cpm, shadowAtkBonus, shadowDefMult, pokemonIndex,
//               preToFinals, leagueCaps, rankLookup, thresholds,
//               league, leagueLabel, leagueCap, maxLevel, requireGender,
//               focalSpecies, oppSpecies, oppFinalSpecies}
(function () {
  'use strict';

  var D = (typeof TL_DATA !== 'undefined') ? TL_DATA : {};
  var META = D.meta || {};
  var N = 4096;
  var NS = 9;
  // Species names come from the DATA, never from a literal here: the same
  // file renders every analyzed pair. The internal side keys stay
  // 'thievul'/'licki' because they name the TL_DATA arrays, not the
  // species. No fallback name: a missing identity is shown as missing
  // (the HARD RULE above), because a confidently wrong species name is a
  // made-up number's twin.
  var FOCAL = META.focal || '[focal species missing from meta]';
  var OPP = META.opponent || '[opponent species missing from meta]';

  // ---- tiny DOM helpers ----
  function $(id) { return document.getElementById(id); }
  // A community shorthand that is AMBIGUOUS between two real species (the
  // assembly's [assemble] opp_display_short) is expanded to the analyzed
  // species wherever it appears, including in text the assembly generated.
  // \b keeps the full species names untouched.
  //
  // MISSING TL_DATA FIELD: the shorthand itself is the one opponent word
  // this file cannot read from the blob -- the assembly config knows it
  // ([assemble] opp_display_short) but the builder does not copy it into
  // meta. Until it does, the shorthand below is pair-specific; it is an
  // inert no-op on any pair that does not use it, never a wrong word.
  var OPP_SHORT = 'Licki';
  function expandOppShorthand(s) {
    var w = OPP_SHORT;
    if (!w || w === OPP) return String(s === null || s === undefined ? '' : s);
    return String(s === null || s === undefined ? '' : s)
      .replace(new RegExp('\\b' + w + '\\b', 'g'), OPP)
      .replace(new RegExp('\\b' + w + 's\\b', 'g'), OPP + ' spreads');
  }
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function setHtml(id, html) { var n = $(id); if (n) n.innerHTML = html; }
  // Three different causes used to share one (wrong) headline. The
  // headline now names the actual cause: absent data, a browser that
  // cannot gunzip, or something the reader typed.
  function missingBox(msg, kind) {
    var head = (kind === 'browser') ? 'This browser cannot read the data.'
      : (kind === 'input') ? 'Nothing to show for that input.'
      : 'Data not baked yet.';
    // The message is a full sentence following a full stop, so it is
    // capitalised here rather than at each of the ~12 call sites.
    return '<div class="tl-missing"><strong>' + head + '</strong> '
      + esc(capFirst(msg)) + '</div>';
  }
  function showMissing(id, msg, kind) {
    setHtml(id, missingBox(msg, kind));
  }
  // "3 spread(s)" is a placeholder, not English. Every counted noun on the
  // page goes through this.
  function plural(n, one, many) {
    return commas(n) + ' ' + (n === 1 ? one : (many || one + 's'));
  }
  function fmt(x, dp) {
    if (x === null || x === undefined || isNaN(x)) return '-';
    return Number(x).toFixed(dp === undefined ? 1 : dp);
  }

  // ---- theme plumbing (mirrors deep_dive_engine.js themeColor/plotChrome) ----
  var _themeCache = {};
  function themeColor(name) {
    if (Object.prototype.hasOwnProperty.call(_themeCache, name)) {
      return _themeCache[name];
    }
    var v = '';
    try {
      v = getComputedStyle(document.documentElement)
        .getPropertyValue(name).trim();
    } catch (e) { v = ''; }
    _themeCache[name] = v;
    return v;
  }
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
      ink: themeColor('--text'),
      gold: themeColor('--notable'),
      muted: themeColor('--text-muted')
    };
  }
  var TIER_TOKENS = ['--tier-1', '--tier-2', '--tier-3', '--tier-4',
                     '--tier-5', '--tier-6', '--tier-7', '--tier-8'];
  function tierColor(i) { return themeColor(TIER_TOKENS[i % TIER_TOKENS.length]); }

  function baseLayout(title, xTitle, yTitle) {
    var c = plotChrome();
    return {
      title: title,
      xaxis: { title: xTitle, gridcolor: c.grid, zerolinecolor: c.grid },
      yaxis: { title: yTitle, gridcolor: c.grid, zerolinecolor: c.grid },
      paper_bgcolor: c.paper, plot_bgcolor: c.plot,
      font: { color: c.font }, hovermode: 'closest',
      legend: {
        bgcolor: c.legendBg, bordercolor: c.legendBorder, borderwidth: 1,
        x: 1.02, xanchor: 'left', y: 1, yanchor: 'top'
      },
      hoverlabel: {
        bgcolor: c.hoverBg, bordercolor: c.hoverBorder,
        font: { size: 11, color: c.font, family: 'monospace' },
        namelength: -1, align: 'left'
      },
      margin: { r: 190, t: 46 }
    };
  }

  // ---- data presence ----
  var GRID_LABELS = Object.keys(D.cov || {});
  var HAS_GRIDS = GRID_LABELS.length > 0;
  var HAS_META_WINS = !!(D.meta_wins && D.meta_wins.wins_11);
  var HAS_BP = !!D.breakpoints;
  var HAS_RECO = !!D.reco;
  var WON = D.won_b64 || {};
  // Byte-identical grids embed ONCE; the alias map points the duplicate
  // label at the stored copy (see the IDENTICAL GRIDS rail).
  var WON_ALIAS = D.won_b64_alias || {};
  Object.keys(WON_ALIAS).forEach(function (lb) {
    if (!WON[lb] && WON[WON_ALIAS[lb]]) { WON[lb] = WON[WON_ALIAS[lb]]; }
  });
  var LEAGUE_CAP_TEXT = (D.collection && D.collection.leagueCap)
    ? ('CP ' + D.collection.leagueCap) : 'league CP';

  function scenarioLabel(si) {
    var sc = META.scenarios || [];
    return sc[si] !== undefined ? sc[si] : String(si);
  }

  // ---- IV index helpers ----
  function ivIndex(side, a, d, s) {
    var ivs = (D[side] || {}).ivs;
    if (!ivs) return -1;
    for (var i = 0; i < ivs.length; i++) {
      if (ivs[i][0] === a && ivs[i][1] === d && ivs[i][2] === s) return i;
    }
    return -1;
  }
  function ivStr(side, i) {
    var ivs = (D[side] || {}).ivs;
    if (!ivs || !ivs[i]) return '?';
    return ivs[i][0] + '/' + ivs[i][1] + '/' + ivs[i][2];
  }
  function statLine(side, i) {
    var t = D[side] || {};
    if (!t.ivs || !t.ivs[i]) return '';
    return 'IVs ' + ivStr(side, i) + ' (rank ' + (i + 1) + ')'
      + '<br>L' + t.level[i] + ' CP ' + t.cp[i]
      + '<br>atk ' + fmt(t.atk[i], 2) + ' def ' + fmt(t.def[i], 2)
      + ' hp ' + t.hp[i];
  }

  // ---- state ----
  // Default grid: PvPoke's own default moveset when it is embedded, so the
  // page opens on the build most readers actually run rather than on
  // whichever grid happens to be first in the manifest.
  var DEFAULT_GRID = (function () {
    if (!HAS_GRIDS) return null;
    var want = META.default_moveset_label;
    if (want && (D.cov || {})[want]) return want;
    // No grid-label literal as a second guess: the blob either names the
    // default moveset or it does not, and the manifest order is the only
    // other thing this file knows.
    return GRID_LABELS[0];
  })();
  var state = {
    label: DEFAULT_GRID,
    // si = sf*3+so. 1-1 is the scenario people plan around, and on the
    // DEFAULT grid it is IV-sensitive rather than saturated, so the first
    // paint shows real structure. Saturation is detected from the data, so
    // if a grid ever makes 1-1 flat the panels say so instead of showing
    // a blank wall.
    si: 4,
    scenarioAll: false,
    cohort: 'all',
    customText: '',
    user: [],         // [{side, idx, label, cp}]
    overCap: [],      // scanned mons that can no longer BE the analyzed build
    basis: 'primary', // which moveset the ranked table ranks FOR
    cliffColor: 'sp', // cliff panel colouring: sp | def | hp
    // coverage panel: grid (3x3, DEFAULT -- the all-9 view is the
    // discoverable one; Michael 2026-08-19) | single
    covView: 'grid',
    heatRange: null,  // null = whole 4096x4096; else {i0,i1,j0,j1} indices
    heatNamed: true
  };
  // The ranked table follows the selected grid's moveset, and that must
  // hold on the FIRST paint too -- no change event fires at startup.
  state.basis = basisForMoveset(msKeyOf(state.label));

  // ---- won_b64 decode (gzip via DecompressionStream; file:// safe) ----
  var _wonCache = {};
  function haveWon(label, si) {
    return !!(WON[label] && WON[label][String(si)]);
  }
  function haveWonAll(label) {
    for (var si = 0; si < NS; si++) { if (!haveWon(label, si)) return false; }
    return true;
  }
  function decodeWon(label, si) {
    var key = label + ':' + si;
    if (_wonCache[key]) return _wonCache[key];
    var b64 = (WON[label] || {})[String(si)];
    if (!b64) return Promise.reject(new Error('no won slice ' + key));
    var p = (function () {
      var bin = atob(b64);
      var raw = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) raw[i] = bin.charCodeAt(i);
      if (typeof DecompressionStream === 'undefined') {
        return Promise.reject(new Error(
          'this browser has no DecompressionStream(gzip)'));
      }
      var stream = new Blob([raw]).stream()
        .pipeThrough(new DecompressionStream('gzip'));
      return new Response(stream).arrayBuffer().then(function (buf) {
        return new Uint8Array(buf);
      });
    })();
    _wonCache[key] = p;
    return p;
  }
  function bitAt(bytes, fi, oi) {
    var idx = fi * N + oi;
    return (bytes[idx >> 3] & (0x80 >> (idx & 7))) !== 0;
  }

  // A gzip-less browser is not missing data; say so.
  function decodeKind(err) {
    return /DecompressionStream/i.test(String(err && err.message))
      ? 'browser' : 'data';
  }
  function decodeMsg(err) {
    var m = String(err && err.message || err);
    return /DecompressionStream/i.test(m)
      ? 'the per-matchup win grids are gzip-compressed and this browser '
        + 'does not support DecompressionStream(gzip), so the heatmap, the '
        + 'drill-down and the narrow cohorts cannot be decoded here. The '
        + 'aggregated panels still work. Recent Chrome, Edge, Firefox and '
        + 'Safari all support it.'
      : 'win-grid decode failed: ' + m;
  }
  var CAN_GUNZIP = (typeof DecompressionStream !== 'undefined');

  // ---- cohorts ----
  function parseRanks(text) {
    var out = [];
    var seen = {};
    var parts = String(text || '').split(/[,\s]+/);
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      if (!p) continue;
      var m = p.match(/^(\d+)\s*-\s*(\d+)$/);
      if (m) {
        var lo = parseInt(m[1], 10), hi = parseInt(m[2], 10);
        for (var r = lo; r <= hi; r++) {
          if (r >= 1 && r <= N && !seen[r]) { seen[r] = 1; out.push(r - 1); }
        }
        continue;
      }
      var mi = p.match(/^(\d+)\/(\d+)\/(\d+)$/);
      if (mi) {
        var ix = ivIndex('licki', +mi[1], +mi[2], +mi[3]);
        if (ix >= 0 && !seen[ix + 1]) { seen[ix + 1] = 1; out.push(ix); }
        continue;
      }
      var v = parseInt(p, 10);
      if (!isNaN(v) && v >= 1 && v <= N && !seen[v]) {
        seen[v] = 1; out.push(v - 1);
      }
    }
    return out;
  }
  var _cohortWarn = '';
  function cohortIndices() {
    if (state.cohort === 'all') return null;            // handled by cov table
    if (state.cohort === 'top512') return null;          // handled by cov table
    if (state.cohort === 'top100') {
      var a = [];
      for (var i = 0; i < 100; i++) a.push(i);
      return a;
    }
    if (state.cohort === 'rank1') return [0];
    var raw = String(state.customText || '').split(/[,\s]+/)
      .filter(Boolean);
    var got = parseRanks(state.customText);
    // Tokens that parsed to nothing used to vanish silently, unlike the
    // drill-down inputs which warn.
    var kept = {};
    got.forEach(function (i) { kept[i + 1] = 1; });
    var dropped = raw.filter(function (tok) {
      var mm = tok.match(/^(\d+)\s*-\s*(\d+)$/);
      if (mm) {
        for (var r2 = +mm[1]; r2 <= +mm[2]; r2++) {
          if (kept[r2]) return false;
        }
        return true;
      }
      var mi = tok.match(/^(\d+)\/(\d+)\/(\d+)$/);
      if (mi) return ivIndex('licki', +mi[1], +mi[2], +mi[3]) < 0;
      var v2 = parseInt(tok, 10);
      return !(!isNaN(v2) && v2 >= 1 && v2 <= N);
    });
    // A standalone SENTENCE (leading space, terminal period) that callers
    // append after their own punctuation -- it used to be glued onto the
    // end of the cohort label mid-clause, which produced "...spread(s)
    // Ignored 2 entry/entries ...: 99999.." with no break and a doubled
    // period.
    _cohortWarn = dropped.length
      ? ' Ignored ' + dropped.length
        + (dropped.length === 1 ? ' entry' : ' entries')
        + ' this page could not read as a rank or an IV triple in the '
        + 'analyzed grid: ' + dropped.slice(0, 5).join(', ') + '.'
      : '';
    return got;
  }
  function cohortLabel() {
    if (state.cohort === 'all') return 'all 4096 ' + OPP + ' spreads';
    if (state.cohort === 'top512') return 'top 512 ' + OPP + ' spreads (by stat product)';
    if (state.cohort === 'top100') return 'top 100 ' + OPP + ' spreads (by stat product)';
    if (state.cohort === 'rank1') return 'rank-1 ' + OPP + ' only';
    var c = cohortIndices() || [];
    return 'custom ' + OPP + ' cohort (' + plural(c.length, 'spread') + ')';
  }
  // The ignored-entry warning, as a sentence to append AFTER the caller's
  // own period. cohortLabel() no longer carries it (it was rendering
  // mid-clause with a doubled period). cohortIndices() must have run
  // first, which every caller of cohortLabel() guarantees.
  function cohortWarnText() { return _cohortWarn; }

  // ---- coverage ----
  // Returns a Promise of {pct: Float64Array(4096), denom, note} or
  // {missing: 'reason'}.
  // siOpt: compute for THAT scenario instead of the dropdown's (the 3x3
  // small-multiples view needs all nine independently).
  function coverage(siOpt) {
    var oneSi = (typeof siOpt === 'number') ? siOpt : null;
    if (!HAS_GRIDS || !state.label) {
      return Promise.resolve({ missing:
        'no simulation grid is embedded in this page yet' });
    }
    var tbl = D.cov[state.label] || {};
    var fromTable = (state.cohort === 'all') ? tbl.all
      : (state.cohort === 'top512') ? tbl.top512 : null;
    if (fromTable) {
      var denom = (state.cohort === 'all') ? N : 512;
      var out = new Float64Array(N);
      if (oneSi === null && state.scenarioAll) {
        for (var i = 0; i < N; i++) {
          var acc = 0;
          for (var si = 0; si < NS; si++) acc += fromTable[i * NS + si];
          out[i] = 100 * acc / (NS * denom);
        }
      } else {
        var useSi = (oneSi === null) ? state.si : oneSi;
        for (var j = 0; j < N; j++) {
          out[j] = 100 * fromTable[j * NS + useSi] / denom;
        }
      }
      return Promise.resolve({ pct: out, denom: denom, note: '' });
    }
    // Cohort needs the raw win bitmap.
    var cohort = cohortIndices() || [];
    if (!cohort.length) {
      return Promise.resolve({ kind: 'input', missing:
        'the custom ' + OPP + ' cohort is empty - enter ranks (e.g. "1-50") '
        + 'or IV triples (e.g. "15/15/14") in the box above.'
        // What was typed and ignored is the actionable half; dropping it
        // for the generic message left a reader who typed only
        // unparseable tokens with no clue why the box did nothing.
        + cohortWarnText() });
    }
    var sis = (oneSi !== null) ? [oneSi]
      : (state.scenarioAll ? [0, 1, 2, 3, 4, 5, 6, 7, 8] : [state.si]);
    for (var k = 0; k < sis.length; k++) {
      if (!haveWon(state.label, sis[k])) {
        return Promise.resolve({ missing:
          'the full win grid for ' + state.label + ' scenario '
          + scenarioLabel(sis[k]) + ' is not embedded in this page, so this '
          + 'cohort cannot be computed (the All-4096 and Top-512 cohorts '
          + 'still work - they are pre-aggregated)' });
      }
    }
    var coh = new Int32Array(cohort);
    return Promise.all(sis.map(function (si) {
      return decodeWon(state.label, si);
    })).then(function (slices) {
      var out2 = new Float64Array(N);
      for (var fi = 0; fi < N; fi++) {
        var c = 0;
        for (var s = 0; s < slices.length; s++) {
          var bytes = slices[s];
          for (var q = 0; q < coh.length; q++) {
            if (bitAt(bytes, fi, coh[q])) c++;
          }
        }
        out2[fi] = 100 * c / (slices.length * coh.length);
      }
      return { pct: out2, denom: coh.length, note: '' };
    }, function (err) {
      return { kind: decodeKind(err), missing: decodeMsg(err) };
    });
  }

  // ---- named / user markers ----
  // breakpoints.named_spreads and reco.named_builds overlap heavily -- rank
  // 1 is named three times across the two sources ("rank-1 stat product",
  // "rank1", "no-meta-cost"), 456 and 534 twice each. Concatenating them
  // painted the same row two or three times with three separate labels,
  // which is what turned the right edge of every panel into a jumble. One
  // ROW = one entry = one merged label, deduped by rank.
  function shortName(label, idx) {
    var s = String(label || '').trim();
    s = s.replace(/^#\d+\s*/, '');              // reco prefixes "#752 "
    var iv = ivStr('thievul', idx);
    if (s.indexOf(iv) === 0) s = s.slice(iv.length).trim();
    s = s.replace(/^\((.*)\)$/, '$1').trim();   // "(smasher)" -> "smasher"
    // Drop names that carry no information beyond the tag already shown:
    // the IV string itself, its punctuation-free key form, or a bare rank.
    var bare = s.replace(/[^0-9a-z]/gi, '').toLowerCase();
    var ivBare = iv.replace(/[^0-9]/g, '');
    if (!bare) return '';
    if (bare === ivBare) return '';
    if (bare === 'rank' + (idx + 1)) return '';
    if (/^rank\d*$/.test(bare)) return '';
    return s;
  }
  function namedBuilds() {
    var raw = [];
    var ns = (D.breakpoints || {}).named_spreads;
    if (ns) {
      Object.keys(ns).forEach(function (k) {
        raw.push({ label: ns[k].label || k, ivs: ns[k].ivs, rank: ns[k].rank });
      });
    }
    // META.named_builds is merged ALWAYS, not only as a fallback: the
    // blob's label for 6/15/5 is the bare IV tag (which shortName drops as
    // redundant), while META carries the informative "6/15/5 (discord
    // claim)" -- the claim this page exists to test. Everything here is
    // deduped by rank and by name, so merging cannot double-paint a row.
    raw = raw.concat(META.named_builds || []);
    raw = raw.concat((D.reco && D.reco.named_builds) || []);
    var byIdx = {}, order = [];
    raw.forEach(function (b) {
      var idx = (b.ivs)
        ? ivIndex('thievul', b.ivs[0], b.ivs[1], b.ivs[2])
        : (b.rank !== undefined && b.rank !== null ? b.rank - 1 : -1);
      if (idx < 0 || idx >= N) return;
      if (!byIdx[idx]) { byIdx[idx] = []; order.push(idx); }
      var nm = shortName(b.label, idx);
      if (nm && byIdx[idx].indexOf(nm) < 0) byIdx[idx].push(nm);
    });
    return order.sort(function (a, b) { return a - b; }).map(function (idx) {
      var names = byIdx[idx];
      var tag = '#' + (idx + 1) + ' ' + ivStr('thievul', idx);
      return {
        idx: idx, tag: tag, names: names,
        label: tag + (names.length ? ' - ' + names.join(' / ') : '')
      };
    });
  }
  function commas(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  // ---- per-grid saturation, computed from the embedded coverage ----
  // cov[label] carries, for EVERY embedded grid, how many opponent spreads
  // each focal spread beats in each scenario. A scenario is SATURATED for a
  // cohort when the MINIMUM coverage equals the denominator. This is
  // recomputed for the SELECTED grid instead of being frozen into a single
  // headline, because the answer is moveset-dependent: a conclusion that
  // holds for one charged-move pair need not hold for PvPoke's default one.
  var _satCache = {};
  function saturationForGrid(label) {
    if (!label) return null;
    if (_satCache[label]) return _satCache[label];
    var tbl = (D.cov || {})[label];
    if (!tbl) return null;
    var out = { all: [], top512: [], hopeless: [], source: 'page',
                mismatch: '' };
    [['all', N], ['top512', 512]].forEach(function (pair) {
      var arr = tbl[pair[0]], denom = pair[1];
      if (!arr) { out[pair[0]] = null; return; }
      for (var si = 0; si < NS; si++) {
        var sat = true, mx = 0;
        for (var i = 0; i < N; i++) {
          var c = arr[i * NS + si];
          if (c !== denom) sat = false;
          if (c > mx) mx = c;
        }
        if (sat) out[pair[0]].push(scenarioLabel(si));
        if (pair[0] === 'all' && mx === 0) {
          out.hopeless.push(scenarioLabel(si));
        }
      }
    });
    // The assembly ships its own per-grid classification. We keep the
    // page's computed sets (they carry BOTH cohorts) but cross-check, so a
    // disagreement is shown rather than one of them silently winning.
    var pg = ((D.reco || {}).per_grid_scenarios || {})[label]
      || ((D.reco || {}).saturated_by_grid || {})[label]
      || ((D.reco || {}).saturated_scenarios_by_grid || {})[label];
    if (pg) {
      var rs = Array.isArray(pg) ? pg
        : (pg.saturated_win || pg.all || pg.all_4096 || null);
      if (rs && rs.slice().sort().join(',')
          !== (out.all || []).slice().sort().join(',')) {
        out.mismatch = ' DISAGREEMENT: the recommendation blob lists '
          + (rs.length ? rs.join(', ') : 'none')
          + ' as saturated for this grid, but the embedded coverage counts '
          + 'give ' + ((out.all || []).length ? out.all.join(', ') : 'none')
          + ' - trust neither until that is resolved.';
      }
      // The blob's "hopeless" is a rounded/editorial rule; the page's is
      // literal (zero wins anywhere). Where they differ, say exactly how
      // many wins are actually left rather than picking a side.
      var rh = pg.hopeless || [];
      var extra = rh.filter(function (s) {
        return out.hopeless.indexOf(s) < 0;
      });
      if (extra.length) {
        var arrAll = ((D.cov || {})[label] || {}).all;
        out.nearly = extra.map(function (s) {
          var si = (META.scenarios || []).indexOf(s);
          var best = 0, tot = 0;
          if (arrAll && si >= 0) {
            for (var i = 0; i < N; i++) {
              var c = arrAll[i * NS + si];
              tot += c;
              if (c > best) best = c;
            }
          }
          return s + ' (best spread beats ' + best + ' of ' + N + '; '
            + commas(tot) + ' winning matchups in all)';
        });
      }
    }
    _satCache[label] = out;
    return out;
  }
  function scenarioComplement(list) {
    var have = {}, out = [];
    (list || []).forEach(function (s) { have[s] = 1; });
    for (var si = 0; si < NS; si++) {
      var lb = scenarioLabel(si);
      if (!have[lb]) out.push(lb);
    }
    return out;
  }
  function satSentence(label) {
    var s = saturationForGrid(label);
    if (!s) return '';
    var pretty = gridPretty(label);
    var isDefault = (META.default_moveset_label === label);
    var head = pretty + (isDefault
      ? ' (PvPoke\'s default ' + FOCAL + ' moveset)' : '');
    if (!(s.all || []).length && !(s.top512 || []).length
        && !(s.hopeless || []).length) {
      return head + ': NO shield scenario is decided either way - IV choice '
        + 'can change the result in all 9.' + (s.mismatch || '');
    }
    var bits = [];
    if (s.all) {
      bits.push((s.all.length
        ? 'every ' + FOCAL + ' spread beats every one of the 4096 ' + OPP
          + ' spreads at ' + s.all.join(', ')
        : 'no scenario is saturated against all 4096 ' + OPP + ' spreads'));
    }
    if (s.top512) {
      bits.push('against the top-512 cohort: '
        + (s.top512.length ? s.top512.join(', ') : 'none'));
    }
    var nearlyKeys = (s.nearly || []).map(function (x) {
      return String(x).split(' ')[0];
    });
    // A scenario saturated for the top-512 cohort but not for all-4096
    // must not be listed as decided AND still-decidable with no
    // explanation; it is called out separately.
    var cohortOnly = (s.top512 || []).filter(function (x) {
      return (s.all || []).indexOf(x) < 0;
    });
    var rest = scenarioComplement(
      (s.all || []).concat(s.hopeless || []).concat(nearlyKeys));
    return head + ': ' + bits.join('; ')
      + ((s.hopeless || []).length
        ? '. UNWINNABLE for every spread at ' + s.hopeless.join(', ') : '')
      + ((s.nearly || []).length
        ? '. The recommendation blob also treats ' + s.nearly.join('; ')
          + ' as unwinnable' : '')
      + (rest.length ? '. IV choice can still decide '
          // Each undecided scenario carries its measured CEILING --
          // grouping a 28%-max scenario with two 100% ones under one
          // clause read as equally winnable (2026-08-19 verify).
          + rest.map(function (lbl) {
              var si2 = (META.scenarios || []).indexOf(lbl);
              var top = (dig(D, 'cov.' + label + '.top512') || []);
              var bestN = 0;
              if (si2 >= 0 && top.length) {
                for (var ii = si2; ii < top.length; ii += NS) {
                  if (top[ii] > bestN) { bestN = top[ii]; }
                }
              }
              return lbl + (top.length && si2 >= 0
                ? ' (best spread ' + fmt(100 * bestN / 512, 1) + '%)'
                : '');
            }).join(', ')
          + '.'
        : '. No scenario is left for IV choice to decide.')
      + (cohortOnly.length
        ? ' (' + cohortOnly.join(', ') + ' is saturated against the '
          + 'top-512 cohort only, so it appears in both lists: decided if '
          + 'you only meet top-512 ' + OPP + ', still IV-decidable across '
          + 'all 4096.)'
        : '')
      + (s.mismatch || '');
  }

  // The disclosure of the cliff rule is GENERATED from the rule itself --
  // by running cliffExplanation over synthetic inputs that hit each branch
  // and quoting what it actually says. Hand-written parallel prose drifted
  // from the code inside a single batch; this cannot.
  function cliffRuleText() {
    // A FIXED pointer, so the disclosure is state-free: the live pointer
    // varies with the grid dropdown, which made an "exactly these four"
    // enumeration change under the reader.
    var FIXED_PTR = 'switch the shield scenario (the caption names the '
      + 'ones this page computes as still IV-decidable) to see where it '
      + 'does.';
    function probe(pcts, clsPattern) {
      var fakeCov = { pct: pcts };
      var fakeSc = { cls: clsPattern, hi: 7, tier: [] };
      return cliffExplanation(fakeSc, fakeCov, FIXED_PTR).text;
    }
    var n = N;
    function build(vals) {
      // one third of the space in each breakpoint class, at the given
      // class means, so the branch under test is the one that fires
      var pcts = new Float64Array(n), cls = new Uint8Array(n);
      for (var i = 0; i < n; i++) {
        var k = i % 3;
        cls[i] = k;
        pcts[i] = vals[k];
      }
      return { pcts: pcts, cls: cls };
    }
    var flat = build([50, 50, 50]);
    var rise = build([10, 50, 90]);
    var inv = build([90, 50, 10]);
    // Branch 4 is "not rising, but not inverted by CLIFF_INVERSION_PP
    // either" -- so the means must go DOWN a little, not up.
    var mild = build([52, 51, 50]);
    return 'CLIFF PANEL RULE (generated from the code that renders it, by '
      + 'running the same function on synthetic inputs): the sentence above '
      + 'that panel is computed, never authored. It reports the mean '
      + 'coverage of each ' + focalMove() + ' breakpoint class and whether '
      + 'those means rise -- it never attributes the outcome to the breakpoint, '
      + 'to bulk, or to any other cause, because nothing on this page '
      + 'measures explanatory power. The four things it can say are '
      + 'exactly these: (1) when the whole coverage range spans '
      + FLAT_RANGE_PP + ' point or less -- "'
      + probe(flat.pcts, flat.cls) + '"; (2) when the means rise -- "'
      + probe(rise.pcts, rise.cls) + '"; (3) when they are inverted by at '
      + 'least ' + CLIFF_INVERSION_PP + ' points -- "'
      + probe(inv.pcts, inv.cls) + '"; (4) otherwise -- "'
      + probe(mild.pcts, mild.cls) + '".';
  }

  // ---- saturation (a flat series is a finding, not a broken plot) ----
  var COV_Y_RANGE = [0, 102];
  function coverageSaturation(pct) {
    var mn = Infinity, mx = -Infinity;
    for (var i = 0; i < pct.length; i++) {
      if (pct[i] < mn) mn = pct[i];
      if (pct[i] > mx) mx = pct[i];
    }
    if (!(mx - mn <= 1e-9)) return { note: '', text: '' };
    // One keyword per DIRECTION. "SATURATED" was used for both the
    // all-win and the all-loss case, and a reader meeting it on an
    // all-loss panel reads "you win everything". The three words match
    // the TL;DR band's vocabulary exactly.
    var key, what;
    if (mn >= 100 - 1e-9) {
      key = 'ALREADY WON';
      what = 'every one of the ' + pct.length + ' ' + FOCAL + ' spreads '
        + 'beats every ' + OPP + ' in this cohort';
    } else if (mn <= 1e-9) {
      key = 'UNWINNABLE';
      what = 'no ' + FOCAL + ' spread beats any ' + OPP + ' in this cohort';
    } else {
      key = 'FLAT';
      what = 'all ' + pct.length + ' ' + FOCAL + ' spreads sit at exactly '
        + fmt(mn, 1) + '%';
    }
    // Where to look instead is COMPUTED (sensitivePointer). A hardcoded
    // pair sent readers at 0-1, which this very page labels unwinnable.
    var ptr = sensitivePointer(state.label);
    return {
      note: ' ' + key + ': ' + what + ' in this scenario, so IV choice does '
        + 'not decide anything here - ' + ptr,
      text: capFirst(what) + '.<br>IV choice '
        + 'does not matter in this scenario - ' + ptr
    };
  }
  function satAnnotation(text, c) {
    return {
      xref: 'paper', yref: 'paper', x: 0.5, y: 0.5, xanchor: 'center',
      yanchor: 'middle', showarrow: false, text: text,
      font: { color: c.ink, size: 13 }, bgcolor: c.legendBg,
      bordercolor: c.legendBorder, borderwidth: 1, borderpad: 8,
      opacity: 0.95
    };
  }

  // ---- joint win heatmap (hero panel) ----
  // The whole 4096 x 4096 joint IV space in one picture. Every cell is
  // computed HERE, in the browser, from the same decoded win bitmap the
  // drill-down uses -- there is no second, pre-binned copy of the data that
  // could disagree with it. Zooming re-bins the visible window, and once a
  // window is small enough every cell is one literal simulated matchup.
  // Drawn plot area in CSS pixels (.tl-heat is 760px tall; plotly's
  // default bottom margin is 80 and the layout sets t=46, l/r=150 against
  // a ~1140px body). Only used to express a 2px frame offset in rank
  // units, so an approximation is fine.
  // ONE approximation of the drawn plot area, used by both the hover
  // frame offset and the named-label collision spacing (they disagreed by
  // 14% when each carried its own constant).
  var HEAT_PX_H = 634;
  var HEAT_PX_W = 840;
  var HEAT_BINS = 256;   // overview bins per axis
  var _heatTimer = null;
  var POPCNT = (function () {
    var t = new Uint8Array(256);
    for (var i = 0; i < 256; i++) {
      var c = 0, v = i;
      while (v) { c += v & 1; v >>= 1; }
      t[i] = c;
    }
    return t;
  })();
  // Set bits of focal row fi over opponent indices [o0, o1). Rows are
  // byte-aligned (N = 4096 = 512 bytes/row), so whole bytes go through the
  // popcount table and only the two ragged ends are walked bit by bit.
  function rowCount(bytes, fi, o0, o1) {
    var s = fi * N + o0, e = fi * N + o1;
    if (e <= s) return 0;
    var c = 0, b;
    var sb = s >> 3, eb = e >> 3;
    if (sb === eb) {
      for (b = s; b < e; b++) if (bytes[b >> 3] & (0x80 >> (b & 7))) c++;
      return c;
    }
    for (b = s; b < ((sb + 1) << 3); b++) {
      if (bytes[b >> 3] & (0x80 >> (b & 7))) c++;
    }
    for (var by = sb + 1; by < eb; by++) c += POPCNT[bytes[by]];
    for (b = eb << 3; b < e; b++) {
      if (bytes[b >> 3] & (0x80 >> (b & 7))) c++;
    }
    return c;
  }
  // Smallest power-of-two bin that keeps an axis at or under HEAT_BINS
  // cells. 4096 spreads -> 16; 900 -> 4; 220 -> 1 (exact cells). Chosen
  // per axis, so a tall narrow window gets fine columns and coarse rows.
  var HEAT_BIN_STEPS = [1, 2, 4, 8, 16];
  function heatBinSize(span) {
    for (var i = 0; i < HEAT_BIN_STEPS.length; i++) {
      if (Math.ceil(span / HEAT_BIN_STEPS[i]) <= HEAT_BINS) {
        return HEAT_BIN_STEPS[i];
      }
    }
    return HEAT_BIN_STEPS[HEAT_BIN_STEPS.length - 1];
  }
  function heatEdges(start, n, bin) {
    var nb = Math.ceil(n / bin);
    var e = new Int32Array(nb + 1);
    for (var k = 0; k <= nb; k++) {
      e[k] = Math.min(start + k * bin, start + n);
    }
    return e;
  }
  function heatRange() {
    return state.heatRange || { i0: 0, i1: N - 1, j0: 0, j1: N - 1 };
  }
  function heatCellText(fi, oi, cnt, nsl) {
    var T = D.thievul || {}, L = D.licki || {};
    return FOCAL + ' #' + (fi + 1) + ' ' + ivStr('thievul', fi)
      + ' (L' + (T.level ? T.level[fi] : '?')
      + ', CP ' + (T.cp ? T.cp[fi] : '?') + ')'
      + '<br>vs ' + OPP + ' #' + (oi + 1) + ' ' + ivStr('licki', oi)
      + ' (L' + (L.level ? L.level[oi] : '?')
      + ', CP ' + (L.cp ? L.cp[oi] : '?') + ')'
      + '<br>result: ' + (nsl === 1
        ? (cnt > 0 ? 'WIN' : 'LOSS')
        : 'won ' + cnt + ' of ' + nsl + ' shield scenarios');
  }
  function heatBinText(i0, i1, j0, j1, c, tot) {
    return FOCAL + ' ranks ' + (i0 + 1) + '-' + (i1 + 1)
      + ' (best in bin ' + ivStr('thievul', i0) + ')'
      + '<br>vs ' + OPP + ' ranks ' + (j0 + 1) + '-' + (j1 + 1)
      + ' (best in bin ' + ivStr('licki', j0) + ')'
      // Thousands separators, like the caption's copy of the same
      // denominator -- "2304" here vs "2,304" there read as two numbers.
      + '<br>won ' + commas(c) + ' of ' + commas(tot)
      + ' (' + fmt(100 * c / tot, 1) + '%)';
  }
  // Bin the decoded slices over an index window. Hover strings are built
  // ONLY for the cells actually drawn (never 4096x4096 of them).
  function heatBin(slices, r) {
    var nr = r.i1 - r.i0 + 1, nc = r.j1 - r.j0 + 1;
    var binY = heatBinSize(nr), binX = heatBinSize(nc);
    var ye = heatEdges(r.i0, nr, binY), xe = heatEdges(r.j0, nc, binX);
    var nby = ye.length - 1, nbx = xe.length - 1;
    // Exact cells only when BOTH axes are down to one rank per cell.
    var full = (binY === 1 && binX === 1);
    var z = [], txt = [], xc = [], yc = [], bx, by, s, fi;
    for (bx = 0; bx < nbx; bx++) xc.push((xe[bx] + xe[bx + 1] + 1) / 2);
    for (by = 0; by < nby; by++) {
      yc.push((ye[by] + ye[by + 1] + 1) / 2);
      var acc = new Float64Array(nbx);
      for (s = 0; s < slices.length; s++) {
        for (fi = ye[by]; fi < ye[by + 1]; fi++) {
          for (bx = 0; bx < nbx; bx++) {
            acc[bx] += rowCount(slices[s], fi, xe[bx], xe[bx + 1]);
          }
        }
      }
      var zrow = new Array(nbx), trow = new Array(nbx);
      var rows = ye[by + 1] - ye[by];
      for (bx = 0; bx < nbx; bx++) {
        var cols = xe[bx + 1] - xe[bx];
        var tot = slices.length * rows * cols;
        var cnt = acc[bx];
        zrow[bx] = cnt / tot;
        trow[bx] = full
          ? heatCellText(ye[by], xe[bx], cnt, slices.length)
          : heatBinText(ye[by], ye[by + 1] - 1, xe[bx], xe[bx + 1] - 1,
                        cnt, tot);
      }
      z.push(zrow); txt.push(trow);
    }
    return { z: z, text: txt, x: xc, y: yc, full: full, ye: ye, xe: xe,
             nby: nby, nbx: nbx, binY: binY, binX: binX,
             rowsPerBin: binY, colsPerBin: binX,
             // ONE source for "how many outcomes are behind a cell": the
             // caption and the hover text both read these, so they cannot
             // disagree by a factor of 9 the way they did when the caption
             // counted matchups and the hover counted matchups x
             // scenarios.
             nSlices: slices.length,
             cellDenom: binY * binX * slices.length,
             nr: nr, nc: nc };
  }
  // Diverging scale on the page's own outcome tokens: --loss ... neutral
  // ... --win, with 0.5 (an even split) sitting on the neutral midpoint.
  // Both ends are the same colors the win/loss tables use, in every theme.
  function heatScale() {
    var lo = themeColor('--loss') || '#c31c1c';
    var mid = themeColor('--matrix-tie-bg') || '#888888';
    var hi = themeColor('--win') || '#247934';
    return [[0, lo], [0.5, mid], [1, hi]];
  }
  function heatSlicePick() {
    if (!HAS_GRIDS || !state.label) {
      return { missing: 'no simulation grid is embedded in this page yet, '
        + 'so there is nothing to draw here.' };
    }
    var sis = [];
    if (state.scenarioAll) {
      for (var si = 0; si < NS; si++) sis.push(si);
    } else {
      sis.push(state.si);
    }
    for (var k = 0; k < sis.length; k++) {
      if (!haveWon(state.label, sis[k])) {
        return { missing: (state.scenarioAll
            ? 'the "all 9 (mean)" view needs the full win grid for every '
              + 'shield scenario, and '
            : 'this view needs the full win grid, and ')
          + state.label + ' scenario ' + scenarioLabel(sis[k])
          + ' is not embedded in this page (the pre-aggregated coverage '
          + 'panels below still work; this heatmap needs the per-matchup '
          + 'bitmap)' };
      }
    }
    return { sis: sis };
  }
  // Overlay for spreads YOU own (manual entries + Poke Genie CSV). Owned
  // focal spreads are rows, owned opponent spreads are columns, and an
  // intersection is a
  // real simulated matchup -- so it gets a ring, its exact win/loss in the
  // hover, and (once zoomed to per-matchup cells) an outline around the
  // cell itself. Counts are capped so a 200-mon CSV cannot bury the plot;
  // whatever is dropped is SAID in the caption, never dropped silently.
  var OVL_LINE_CAP = 40;    // guide lines per axis
  var OVL_MARK_CAP = 400;   // intersection rings
  function heatOverlay(r, slices, c) {
    var out = { shapes: [], trace: null, note: '' };
    var mine = { thievul: [], licki: [] };
    state.user.forEach(function (u) {
      if (mine[u.side]) mine[u.side].push(u);
    });
    if (!mine.thievul.length && !mine.licki.length) return out;
    function visible(side, lo, hi) {
      return mine[side].slice().sort(function (a, b) {
        return a.idx - b.idx;
      }).filter(function (u) { return u.idx >= lo && u.idx <= hi; });
    }
    var visT = visible('thievul', r.i0, r.i1);
    var visL = visible('licki', r.j0, r.j1);
    var capT = visT.slice(0, OVL_LINE_CAP);
    var capL = visL.slice(0, OVL_LINE_CAP);
    var gold = c.gold || '#b68a14';
    capT.forEach(function (u) {
      out.shapes.push({
        type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y',
        y0: u.idx + 1, y1: u.idx + 1,
        line: { color: gold, width: 1.5, dash: 'dash' }
      });
    });
    capL.forEach(function (u) {
      out.shapes.push({
        type: 'line', yref: 'paper', y0: 0, y1: 1, xref: 'x',
        x0: u.idx + 1, x1: u.idx + 1,
        line: { color: gold, width: 1.5, dash: 'dash' }
      });
    });
    // Cell-level outlines only when the grid is drawing exact cells --
    // same rule the binning uses, so the two can never disagree.
    var full = (heatBinSize(r.i1 - r.i0 + 1) === 1
      && heatBinSize(r.j1 - r.j0 + 1) === 1);
    var xs = [], ys = [], hv = [], capped = false, a, b, s;
    for (a = 0; a < capT.length && !capped; a++) {
      for (b = 0; b < capL.length; b++) {
        if (xs.length >= OVL_MARK_CAP) { capped = true; break; }
        var t = capT[a], l = capL[b], cnt = 0;
        for (s = 0; s < slices.length; s++) {
          if (bitAt(slices[s], t.idx, l.idx)) cnt++;
        }
        xs.push(l.idx + 1);
        ys.push(t.idx + 1);
        hv.push('YOURS: ' + t.label + ' #' + (t.idx + 1) + ' '
          + ivStr('thievul', t.idx)
          + '<br>vs YOURS: ' + l.label + ' #' + (l.idx + 1) + ' '
          + ivStr('licki', l.idx)
          + '<br>result: ' + (slices.length === 1
            ? (cnt ? 'WIN' : 'LOSS')
            : 'won ' + cnt + ' of ' + slices.length + ' shield scenarios'));
        if (full) {
          out.shapes.push({
            type: 'rect', xref: 'x', yref: 'y',
            x0: l.idx + 0.5, x1: l.idx + 1.5,
            y0: t.idx + 0.5, y1: t.idx + 1.5,
            line: { color: gold, width: 2 }, fillcolor: 'rgba(0,0,0,0)'
          });
        }
      }
    }
    if (xs.length) {
      out.trace = {
        type: 'scatter', mode: 'markers', name: 'your spreads',
        x: xs, y: ys, hovertext: hv,
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 13, symbol: 'circle-open', color: gold,
                  line: { width: 2, color: gold } }
      };
    }
    var msg = ' YOUR SPREADS: gold dashed lines mark them (rows = your '
      + FOCAL + ', columns = your ' + OPP + ')'
      + (xs.length
        ? '; ' + plural(xs.length, 'ring') + ' mark matchups where you own both '
          + 'sides' + (full ? ', outlined at cell level in this zoom' : '')
        : (mine.thievul.length && mine.licki.length
          ? ' - no matchup where you own both sides falls inside the '
            + 'current zoom window, so there is nothing to ring here'
          : ' - you own spreads on only one side, so there is no '
            + 'intersection to ring'))
      + '.';
    var caps = [];
    if (visT.length > capT.length) {
      caps.push('drawing ' + capT.length + ' of ' + visT.length
        + ' owned ' + FOCAL + ' rows (overlay cap ' + OVL_LINE_CAP + ')');
    }
    if (visL.length > capL.length) {
      caps.push('drawing ' + capL.length + ' of ' + visL.length
        + ' owned ' + OPP + ' columns (overlay cap ' + OVL_LINE_CAP + ')');
    }
    if (capped) {
      caps.push('intersection rings capped at ' + OVL_MARK_CAP);
    }
    var offT = mine.thievul.length - visT.length;
    var offL = mine.licki.length - visL.length;
    if (offT || offL) {
      caps.push(offT + ' owned ' + FOCAL + ' and ' + offL + ' owned '
        + OPP + ' spreads fall outside the current zoom window');
    }
    out.note = msg + (caps.length ? ' NOT ALL DRAWN: ' + caps.join('; ')
      + '.' : '');
    return out;
  }
  function drawHeat() {
    var host = $('tl-heat');
    if (!host) return;
    var pick = heatSlicePick();
    if (pick.missing) {
      showMissing('tl-heat', pick.missing);
      setHtml('tl-heat-note', '');
      return;
    }
    if (host.innerHTML.indexOf('tl-heat-plot') < 0) {
      host.innerHTML = '<div id="tl-heat-plot" class="tl-heat"></div>';
    }
    var r = heatRange();
    Promise.all(pick.sis.map(function (si) {
      return decodeWon(state.label, si);
    })).then(function (slices) {
      var b = heatBin(slices, r);
      var c = plotChrome();
      var traces = [{
        type: 'heatmap', x: b.x, y: b.y, z: b.z, text: b.text,
        hovertemplate: '%{text}<extra></extra>',
        colorscale: heatScale(), zmin: 0, zmax: 1, zsmooth: false,
        xgap: 0, ygap: 0,
        colorbar: {
          // On a MIRROR both names collapse; seat labels keep the two
          // ends and the two axes distinguishable (2026-08-20 review M4).
          title: { text: (FOCAL === OPP ? 'row-seat win %'
                          : FOCAL + ' win %'), side: 'right' },
          thickness: 12, tickmode: 'array',
          tickvals: [0, 0.25, 0.5, 0.75, 1],
          ticktext: (FOCAL === OPP
            ? ['0 (column seat wins)', '25', '50', '75',
               '100 (row seat wins)']
            : ['0 (' + OPP + ' wins)', '25', '50', '75',
               '100 (' + FOCAL + ' wins)'])
        }
      }];
      var layout = baseLayout(
        gridPretty(state.label) + ' - ' + scenarioText(),
        OPP + ' stat-product rank (1 = best)'
          + (FOCAL === OPP ? ' - opponent seat (columns)' : ''),
        FOCAL + ' stat-product rank (1 = best)'
          + (FOCAL === OPP ? ' - your seat (rows)' : ''));
      layout.xaxis.range = [r.j0 + 0.5, r.j1 + 1.5];
      layout.yaxis.range = [r.i1 + 1.5, r.i0 + 0.5];   // rank 1 at the top
      layout.hovermode = 'closest';
      layout.margin = { l: 150, r: 150, t: 46 };   // l: named-build gutter
      layout.showlegend = false;
      var shapes = [], anns = [], namedNote = '';
      if (state.heatNamed) {
        // One dotted line per unique rank. Labels sit INSIDE the plot at
        // the right edge (they can never reach the colorbar), on a plate
        // so they stay legible over red or green. Ranks whose labels would
        // land within LABEL_MIN_PX of each other are COMBINED into one
        // label rather than stacked -- #1/#3/#21 are 3px apart at full
        // zoom and no amount of nudging makes three labels fit there. The
        // full names of every marked build are in the caption.
        var LABEL_MIN_PX = 14;
        var vis = namedBuilds().filter(function (nb) {
          return nb.idx >= r.i0 && nb.idx <= r.i1;
        });
        var pxPerRank = HEAT_PX_H / (r.i1 - r.i0 + 1);
        var groups = [];
        vis.forEach(function (nb) {
          shapes.push({
            type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y',
            y0: nb.idx + 1, y1: nb.idx + 1,
            line: { color: c.ink, width: 1, dash: 'dot' }
          });
          var px = (nb.idx - r.i0) * pxPerRank;
          var g = groups.length ? groups[groups.length - 1] : null;
          if (g && (px - g.px) < LABEL_MIN_PX) {
            g.members.push(nb);
          } else {
            groups.push({ px: px, members: [nb] });
          }
        });
        groups.forEach(function (g) {
          var txt;
          if (g.members.length === 1) {
            txt = g.members[0].tag;
          } else {
            txt = g.members.slice(0, 3).map(function (m) {
              return '#' + (m.idx + 1);
            }).join(' / ');
            if (g.members.length > 3) {
              txt += ' +' + (g.members.length - 3) + ' more (see caption)';
            }
          }
          // LEFT gutter: inside the margin, right-anchored against the
          // axis. On the right they covered the data and collided with
          // the colorbar title.
          anns.push({
            xref: 'paper', x: -0.012, xanchor: 'right', yref: 'y',
            y: g.members[0].idx + 1, yanchor: 'middle', showarrow: false,
            text: txt, font: { color: c.ink, size: 10 },
            bgcolor: c.legendBg, bordercolor: c.legendBorder,
            borderwidth: 1, borderpad: 2, opacity: 0.92
          });
        });
        if (vis.length) {
          // Hover carries the full merged name for each marked row.
          traces.push({
            type: 'scatter', mode: 'markers', name: 'named builds',
            x: vis.map(function () { return r.j1 + 1; }),
            y: vis.map(function (nb) { return nb.idx + 1; }),
            hovertext: vis.map(function (nb) { return nb.label; }),
            hovertemplate: '%{hovertext}<extra></extra>',
            marker: { size: 9, color: c.ink, symbol: 'diamond-open',
                      line: { width: 2, color: c.ink } }
          });
          namedNote = ' Named builds marked (dotted rows): '
            + vis.map(function (nb) { return nb.label; }).join('; ') + '.';
        }
      }
      // A uniform slice is a FINDING, not a broken render: say so on the
      // plot, with the count computed from what is actually displayed.
      var zmn = Infinity, zmx = -Infinity;
      b.z.forEach(function (row) {
        row.forEach(function (v) {
          if (v < zmn) zmn = v;
          if (v > zmx) zmx = v;
        });
      });
      var uniform = (zmn === 1 && zmx === 1) ? 1
        : ((zmn === 0 && zmx === 0) ? 0 : null);
      var totalCells = b.nr * b.nc * pick.sis.length;
      var satNote = '';
      if (uniform !== null) {
        satNote = ' ' + (uniform ? 'ALREADY WON' : 'UNWINNABLE') + ': all '
          + commas(totalCells) + ' matchups in this view are ' + FOCAL
          + (uniform ? ' wins' : ' losses')
          + ' - IV choice does not decide anything here.';
        anns.push({
          xref: 'paper', yref: 'paper', x: 0.5, y: 0.5,
          xanchor: 'center', yanchor: 'middle', showarrow: false,
          text: 'All ' + commas(totalCells) + ' matchups in this view: '
            + FOCAL + ' ' + (uniform ? 'WINS' : 'LOSES') + ' every one.'
            + '<br>IV choice does not matter in this scenario - '
            + sensitivePointer(state.label),
          font: { color: c.ink, size: 13 },
          bgcolor: c.legendBg, bordercolor: c.legendBorder,
          borderwidth: 1, borderpad: 8, opacity: 0.95
        });
      }
      // ---- your own spreads, in the page's gold "yours" convention ----
      // Owned focal spreads are ROWS, owned opponent spreads are
      // COLUMNS; where you own
      // both, the intersection is one real simulated matchup and gets a
      // ring (plus a cell outline once the zoom is at per-matchup
      // resolution). Everything here comes from the IV-input panel, so a
      // CSV load / manual add / clear redraws it through refresh().
      var ov = heatOverlay(r, slices, c);
      shapes = shapes.concat(ov.shapes);
      if (ov.trace) traces.push(ov.trace);
      layout.shapes = shapes;
      layout.annotations = anns;
      layout.showlegend = traces.length > 1;   // heatmap itself has no entry
      // Remember what the plot is showing so the hover handler can turn a
      // hovered cell back into its bin band (and restore the base shapes).
      _heatBaseShapes = shapes;
      _heatBaseAnns = anns;
      _heatBins = { ye: b.ye, xe: b.xe, r: r };
      Plotly.react('tl-heat-plot', traces, layout,
                   { responsive: true, scrollZoom: false });
      var gd = $('tl-heat-plot');
      if (gd && typeof gd.on === 'function' && !gd._tlHeatBound) {
        gd._tlHeatBound = true;
        gd.on('plotly_relayout', onHeatRelayout);
        gd.on('plotly_hover', onHeatHover);
        gd.on('plotly_unhover', onHeatUnhover);
      }
      var cell = b.full
        ? (pick.sis.length === 1
          ? 'one cell = ONE simulated matchup (win or loss)'
          : 'one cell = ONE ' + FOCAL + '-vs-' + OPP + ' pair across '
            + b.nSlices + ' shield scenarios (' + b.cellDenom
            + ' outcomes), colored by the fraction ' + FOCAL + ' wins')
        : 'one cell = ' + fmt(b.rowsPerBin, 0) + ' x '
          + fmt(b.colsPerBin, 0) + ' = '
          + fmt(b.rowsPerBin * b.colsPerBin, 0) + ' matchups'
          + (b.nSlices > 1
            ? ' x ' + b.nSlices + ' shield scenarios = '
              + commas(b.cellDenom) + ' outcomes' : '')
          + ', colored by the fraction ' + FOCAL + ' wins';
      setHtml('tl-heat-note',
        'Rows: all 4096 ' + FOCAL + ' IV spreads, stat-product rank 1 at '
        + 'the TOP. Columns: all 4096 ' + OPP + ' IV spreads, rank 1 at the '
        + 'LEFT. Both '
        + 'axes are stat-product rank order, so the bulkiest spreads sit '
        + 'top and left. Showing ' + FOCAL + ' ranks ' + (r.i0 + 1) + '-'
        + (r.i1 + 1) + ' x ' + OPP + ' ranks ' + (r.j0 + 1) + '-' + (r.j1 + 1)
        + ' as ' + b.nby + ' x ' + b.nbx + ' cells: ' + cell + '. '
        // The highlight follows the BINNING: at 16-rank bins it is a
        // 16-spread band, not one spread's row. Saying "row"/"column"
        // with no width let a reader believe they were looking at a
        // single matchup's neighbourhood.
        + 'Hover any cell to outline it across the visible window: '
        + (b.rowsPerBin === 1 && b.colsPerBin === 1
          ? 'at this zoom each cell is one spread, so the highlight is '
            + 'that single ' + FOCAL + ' row and that single ' + OPP
            + ' column'
          : 'the highlight is a band ' + plural(b.rowsPerBin, FOCAL + ' rank')
            + ' tall and ' + plural(b.colsPerBin, OPP + ' rank')
            + ' wide -- the current bin size, not one spread; the '
            + 'hover text names the exact rank range')
        + ((r.i0 > 0 || r.i1 < N - 1 || r.j0 > 0 || r.j1 < N - 1)
          ? ', within the zoomed slice of the full grid'
          : ', which is currently the whole grid')
        + '. '
        + 'Zoom (box-select or the zoom tool) to re-bin the visible window: '
        + 'each axis independently picks the smallest bin of 1, 2, 4, 8 or '
        + '16 ranks that keeps it under ' + HEAT_BINS + ' cells, so zooming '
        + 'in sharpens until every cell is one matchup. Double-click / '
        + '"reset axes" returns to the whole grid. Grid: ' + esc(gridPretty(state.label)) + '; '
        + esc(scenarioText()) + (state.scenarioAll
          ? ' - each cell averages all 9 scenarios' : '')
        + '. The ' + OPP + '-cohort control does NOT apply here: this panel '
        + 'always shows all 4096 x 4096 matchups. Ties (score exactly 500) '
        + 'count as losses.' + esc(satNote) + esc(ov.note)
        + esc(namedNote));
    }, function (err) {
      showMissing('tl-heat', decodeMsg(err), decodeKind(err));
      setHtml('tl-heat-note', '');
    });
  }
  // Which scenarios are actually IV-sensitive on THIS grid? Never a
  // hardcoded pair: on some datasets 0-1 is unwinnable for every spread,
  // so pointing a reader at it would be pointing at a wall of red.
  // Point at scenarios where IVs MATERIALLY change the result, ranked by
  // how much they do. "Not saturated" was too weak a test: 1-0 varies by
  // 5 spreads out of 4096, so sending a reader there was sending them to
  // another flat wall.
  // The pointer is computed from the per-scenario coverage table, which
  // exists for the all-4096 and top-512 cohorts only. Printed inside a
  // cohort-scoped sentence under a NARROW cohort it could send the reader
  // to another flat panel, so under those cohorts it is not printed at all
  // (fixedPtr lets the rule disclosure quote a state-free version).
  function pointerAvailable() {
    return state.cohort === 'all' || state.cohort === 'top512';
  }
  function sensitivePointer(label, fixedPtr) {
    if (fixedPtr) return fixedPtr;
    if (!pointerAvailable()) {
      return 'try the all-4096 or top-512 cohort, or another shield '
        + 'scenario.';
    }
    var s = saturationForGrid(label);
    if (!s) return 'try another shield scenario.';
    var nearly = (s.nearly || []).map(function (x) {
      return String(x).split(' ')[0];
    });
    var rest = scenarioComplement(
      (s.all || []).concat(s.hopeless || []).concat(nearly));
    var tbl = (D.cov || {})[label] || {};
    // The SAME cohort the sentence is scoped to.
    var arr = (state.cohort === 'top512') ? tbl.top512 : tbl.all;
    var cDenom = (state.cohort === 'top512') ? 512 : N;
    var scored = rest.map(function (sc) {
      var si = (META.scenarios || []).indexOf(sc);
      if (!arr || si < 0) return { sc: sc, range: Infinity };
      var mn = Infinity, mx = -Infinity;
      for (var i = 0; i < N; i++) {
        var v = arr[i * NS + si];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      return { sc: sc, range: 100 * (mx - mn) / cDenom };
    }).filter(function (o) { return o.range >= FLAT_RANGE_PP; })
      .sort(function (a, b) { return b.range - a.range; });
    if (!scored.length) {
      return 'no scenario on this grid separates the spreads by more than '
        + FLAT_RANGE_PP + ' point.';
    }
    var names = scored.map(function (o) { return o.sc; });
    // List every IV-decidable scenario -- 'and 1 more' hid one of three
    // (2026-08-19 review note); there are at most nine.
    return 'switch the shield scenario (' + names.join(', ')
      + ') to see where it does.';
  }
  // ---- hover stripes ----
  // Hovering a cell outlines the ENTIRE row (that focal spread against
  // every opponent) and the ENTIRE column (that opponent against every
  // focal spread), so you can see what a spread does across the whole
  // axis rather than in one cell. Binned view outlines the bin band;
  // full-resolution view outlines the single rank.
  function hexToRgba(hex, a) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
    if (!m) return 'rgba(127,127,127,' + a + ')';
    var n = parseInt(m[1], 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ','
      + (n & 255) + ',' + a + ')';
  }
  var _heatBaseShapes = [];
  var _heatBaseAnns = [];
  var _heatBins = null;
  var _hoverTimer = null;
  var _hoverKey = '';
  function bandFor(edges, rank) {
    // edges are 0-based index boundaries; rank is a 1-based axis value
    var idx = Math.round(rank) - 1;
    for (var k = 0; k + 1 < edges.length; k++) {
      if (idx >= edges[k] && idx < edges[k + 1]) {
        return [edges[k] + 0.5, edges[k + 1] + 0.5];
      }
    }
    return null;
  }
  function onHeatHover(ev) {
    if (!ev || !ev.points || !ev.points.length || !_heatBins) return;
    var pt = ev.points[0];
    if (pt.x === undefined || pt.y === undefined) return;
    var key = pt.x + ':' + pt.y;
    if (key === _hoverKey) return;
    _hoverKey = key;
    if (_hoverTimer) clearTimeout(_hoverTimer);
    _hoverTimer = setTimeout(function () {
      _hoverTimer = null;
      var row = bandFor(_heatBins.ye, pt.y);
      var col = bandFor(_heatBins.xe, pt.x);
      if (!row && !col) return;
      // FRAME ONLY -- never a colour layer over the cells. A translucent
      // ink fill tinted the data underneath (saturated green read as
      // reddish-brown), so the band is marked by its border alone: a 2px
      // ink edge over a wider light halo so it survives both palette
      // extremes. The frame is drawn just OUTSIDE the band (expanded by
      // ~2px worth of ranks) so it cannot cover the cells it points at.
      var c = plotChrome();
      var halo = { color: hexToRgba(themeColor('--surface-2'), 0.95),
                   width: 4 };
      var edge = { color: c.ink, width: 2 };
      var CLEAR = 'rgba(0,0,0,0)';
      var rr = _heatBins.r;
      var spanY = (rr.i1 - rr.i0 + 1), spanX = (rr.j1 - rr.j0 + 1);
      var dy = 2 * spanY / HEAT_PX_H;    // 2px, expressed in ranks
      var dx = 2 * spanX / HEAT_PX_W;
      var extra = [];
      function band(spec) {
        extra.push(Object.assign({}, spec, { line: halo,
                                             fillcolor: CLEAR }));
        extra.push(Object.assign({}, spec, { line: edge,
                                             fillcolor: CLEAR }));
      }
      if (row) {
        band({ type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y',
               y0: row[0] - dy, y1: row[1] + dy });
      }
      if (col) {
        band({ type: 'rect', yref: 'paper', y0: 0, y1: 1, xref: 'x',
               x0: col[0] - dx, x1: col[1] + dx });
      }
      // A few pixels of band cannot be made obvious by thickness alone
      // (4096 ranks / 256 bins over ~630px is ~2.5px per bin, and the
      // arithmetic does not improve much short of a 1400px-tall plot). So
      // the band is ALSO pointed at from the margins: a caret in the left
      // gutter and one under the x-axis, at the band's centre. They are
      // POINTERS, not extents -- they sit outside the data area entirely,
      // and the hover text states the exact rank range.
      // Carets on ALL FOUR margins, so the crosshair is findable no matter
      // which edge of the grid the eye is near.
      var carets = [];
      var caretFont = { color: c.ink, size: 15 };
      if (row) {
        var ymid = (row[0] + row[1]) / 2;
        carets.push({
          xref: 'paper', x: -0.006, xanchor: 'right', yref: 'y', y: ymid,
          yanchor: 'middle', showarrow: false, text: '&gt;',
          font: caretFont
        });
        carets.push({
          xref: 'paper', x: 1.006, xanchor: 'left', yref: 'y', y: ymid,
          yanchor: 'middle', showarrow: false, text: '&lt;',
          font: caretFont
        });
      }
      if (col) {
        var xmid = (col[0] + col[1]) / 2;
        carets.push({
          yref: 'paper', y: -0.012, yanchor: 'top', xref: 'x', x: xmid,
          xanchor: 'center', showarrow: false, text: '^', font: caretFont
        });
        carets.push({
          yref: 'paper', y: 1.012, yanchor: 'bottom', xref: 'x', x: xmid,
          xanchor: 'center', showarrow: false, text: 'v', font: caretFont
        });
      }
      try {
        Plotly.relayout('tl-heat-plot', {
          shapes: _heatBaseShapes.concat(extra),
          annotations: _heatBaseAnns.concat(carets)
        });
      } catch (e) { /* a redraw raced us; the next hover fixes it */ }
    }, 60);
  }
  function onHeatUnhover() {
    if (_hoverTimer) clearTimeout(_hoverTimer);
    _hoverTimer = null;
    _hoverKey = '';
    try {
      Plotly.relayout('tl-heat-plot', { shapes: _heatBaseShapes,
                                        annotations: _heatBaseAnns });
    } catch (e) { /* nothing drawn yet */ }
  }
  function clampIdx(v) { return Math.max(0, Math.min(N - 1, v)); }
  function applyHeatRelayout(ev) {
    var cur = heatRange();
    if (ev['xaxis.autorange'] || ev['yaxis.autorange']) {
      if (state.heatRange === null) return;
      state.heatRange = null;
      drawHeat();
      return;
    }
    var xr = ev['xaxis.range']
      || [ev['xaxis.range[0]'], ev['xaxis.range[1]']];
    var yr = ev['yaxis.range']
      || [ev['yaxis.range[0]'], ev['yaxis.range[1]']];
    function span(rr, lo, hi) {
      if (!rr || rr[0] === undefined || rr[0] === null
          || rr[1] === undefined || rr[1] === null) {
        return [lo, hi];
      }
      var a = clampIdx(Math.ceil(Math.min(rr[0], rr[1]) - 1));
      var b = clampIdx(Math.floor(Math.max(rr[0], rr[1]) - 1));
      if (b < a) b = a;
      return [a, b];
    }
    var nx = span(xr, cur.j0, cur.j1);
    var ny = span(yr, cur.i0, cur.i1);
    if (nx[0] === cur.j0 && nx[1] === cur.j1
        && ny[0] === cur.i0 && ny[1] === cur.i1) {
      return;   // our own react() echo, or a pan that changed nothing
    }
    state.heatRange = { i0: ny[0], i1: ny[1], j0: nx[0], j1: nx[1] };
    drawHeat();
  }
  // Plotly re-emits plotly_relayout for OUR OWN patches -- including the
  // {shapes, annotations} update the hover stripes push on every cell.
  // Those carry no axis keys, and because the debounce timer is shared
  // they used to REPLACE a pending zoom that had not fired yet: drag to
  // zoom, leave the cursor on the plot (which is where it already is
  // after a drag), and the zoom was silently dropped. Only range events
  // may touch the timer.
  function isRangeEvent(ev) {
    for (var k in ev) {
      if (/^[xy]axis\.(range|autorange)/.test(k)) return true;
    }
    return false;
  }
  function onHeatRelayout(ev) {
    if (!ev || !isRangeEvent(ev)) return;
    if (_heatTimer) clearTimeout(_heatTimer);
    _heatTimer = setTimeout(function () {
      _heatTimer = null;
      applyHeatRelayout(ev);
    }, 150);
  }

  // ---- TL;DR band ----
  // Reads reco only. Values are printed VERBATIM (this band computes
  // nothing) and labels are DERIVED FROM THE KEY ITSELF -- `cov512_00`
  // says "0-0 shields" because the key says 00, not because anything here
  // assumes which scenario matters. Which metrics exist is the assembly's
  // call: on a grid where a scenario is saturated it emits `cov512_00`
  // instead of `cov512_11`, and the preference list below just takes the
  // first one that is actually present.
  // dp defaults to "as given"; coverage percentages are pinned to 2dp so
  // the band and the reco cards can never print the same number twice with
  // different precision.
  function metricText(v, dp) {
    if (v === null || v === undefined) return '-';
    if (typeof v === 'string') return v;
    if (typeof v === 'number') {
      if (dp !== undefined) return fmt(v, dp);
      return (Math.abs(v % 1) > 1e-9) ? fmt(v, 1) : String(v);
    }
    return String(v);
  }
  // "one of 7 tied; tiebreak: stat-product rank" -- rendered only from
  // fields the assembly actually provides.
  function tieText(c) {
    if (typeof c.tie_note === 'string' && c.tie_note) return c.tie_note;
    var ti = c.tie || (c.metrics || {}).tie;
    if (ti && typeof ti === 'object') {
      var n = ti.n_tied !== undefined ? ti.n_tied : ti.n;
      var tb = ti.tiebreak || ti.tie_break || '';
      var mt = ti.metric || '';
      if (n !== undefined || tb) {
        return (n !== undefined ? 'one of ' + n + ' tied' : 'tied')
          + (mt ? ' on ' + mt : '')
          + (tb ? '; tiebreak: ' + tb : '');
      }
    }
    // Fall back to the assembly's own generated sentence. This is a
    // CROSS-FILE contract: pluralising the assembler's string silently
    // broke this parser once, so the pattern accepts either spelling AND
    // makes the tiebreak clause optional (some cards emit none, and
    // requiring it dropped those cards' counts too). The producing side is
    // the assembly's tie_line(); the guard that runs one through
    // the other is tests/test_thievul_tie_roundtrip.py. The structured
    // `tie` field above is the primary path.
    var out = '';
    (c.lines || []).forEach(function (l) {
      var m2 = String(l).match(
        /^(\d+) spreads?(?:\(s\))? tie on ([^;]+)(?:; tiebreak chain: (.+))?$/);
      if (m2) out = 'one of ' + m2[1] + ' tied on ' + m2[2]
        + (m2[3] ? '; tiebreak: ' + m2[3] : '');
    });
    if (!out && typeof c.subtitle === 'string') {
      var m3 = c.subtitle.match(/tiebreak:\s*(.+)$/i);
      if (m3) out = 'tiebreak: ' + m3[1];
    }
    return out;
  }
  // Cards may carry `spread` as a plain string or as the assembly's
  // object ({ivs, rank, level, cp, ...}). Both render; neither becomes
  // "[object Object]".
  function spreadText(c) {
    var sp = c.spread, ivs = null, rank = c.rank;
    if (sp && typeof sp === 'object' && !Array.isArray(sp)) {
      ivs = sp.ivs;
      if (sp.rank !== undefined && sp.rank !== null) rank = sp.rank;
    } else if (Array.isArray(sp)) {
      ivs = sp;
    } else if (typeof sp === 'string' && sp) {
      return sp + (rank ? ' (rank ' + rank + ')' : '');
    } else if (c.ivs) {
      ivs = c.ivs;
    }
    if (!ivs || !ivs.length) return '';
    return ivs.join('/') + (rank ? ' (rank ' + rank + ')' : '');
  }
  var COV_PREF = ['cov512_11', 'cov512_00', 'cov512_01', 'cov512_02',
                  'cov_all_00'];
  // "tiebreak: 1-1 coverage > 0-0 coverage > ..." -> "1-1". Read from the
  // card's own stated chain so the headline number matches what the card
  // says it ranked on.
  function cardPrimaryScenario(c) {
    var src = String(c.subtitle || '') + ' '
      + ((c.lines || []).join(' '));
    var m = src.match(/tiebreak(?:\s+chain)?:\s*(\d-\d)\s+coverage/i);
    return m ? m[1] : null;
  }
  // Internal moveset key -> the label the rest of the page uses.
  function msLabelFromKey(key) {
    var lb = GRID_LABELS.filter(function (g) {
      return msKeyOf(g) === key;
    })[0];
    return lb ? msAbbrev(lb) : String(key);
  }
  // Which grid is a card actually computed on? Cards may say so
  // structurally (c.grid); otherwise the per-grid metric objects carry a
  // `pretty` tag (e.g. "<fast>/<c1>+<c2>, baiting") and the assembly's
  // subtitle names
  // that same tag, so the card's own basis is recoverable from the data
  // instead of being assumed to be the primary grid. Without a match we
  // fall back to the primary grid (and the label still says which grid the
  // number came from, so nothing is mislabeled either way).
  function cardGrid(c) {
    if (c.grid) return c.grid;
    if (c.primary_grid) return c.primary_grid;
    var m = c.metrics || {}, sub = String(c.subtitle || ''), best = null;
    Object.keys(m).forEach(function (k) {
      var g = m[k];
      if (!g || typeof g !== 'object' || !g.pretty) return;
      var tag = String(g.pretty).split(',')[0].trim();
      if (!tag || sub.indexOf(tag) < 0) return;
      if (best === null || (/_bait$/.test(k) && !/_bait$/.test(best))) {
        best = k;
      }
    });
    return best || (D.reco || {}).primary_grid || null;
  }
  function metricLabel(key) {
    var m = key.match(/^cov512_(\d)(\d)$/);
    if (m) {
      return 'top-512 ' + OPP + ' beaten (' + m[1] + '-' + m[2]
        + ' shields)';
    }
    m = key.match(/^cov_all_(\d)(\d)$/);
    if (m) {
      return 'all-4096 ' + OPP + ' beaten (' + m[1] + '-' + m[2]
        + ' shields)';
    }
    if (key === 'meta_wins_11') return 'meta wins (1-1 shields)';
    return key.replace(/_/g, ' ');
  }
  // Where IV choice cannot matter, PER GRID -- computed live, so it
  // follows the grid dropdown and always names the moveset it describes.
  function satBlock() {
    var labels = GRID_LABELS.slice();
    if (!labels.length) return '';
    // Byte-identical grids get ONE bullet naming both: two bullets with
    // word-for-word identical findings read as a rendering bug.
    var dupOf = {};
    (META.duplicate_grids || []).forEach(function (g) {
      g.slice(1).forEach(function (lb) { dupOf[lb] = g[0]; });
    });
    var alias = {};
    (META.duplicate_grids || []).forEach(function (g) {
      alias[g[0]] = g.slice(1);
    });
    var rows = labels.filter(function (lb) { return !dupOf[lb]; })
      .map(function (lb) {
        var s = satSentence(lb);
        if (!s) return '';
        var also = (alias[lb] || []).map(gridPretty);
        var isCur = (lb === state.label || (alias[lb] || [])
          .indexOf(state.label) >= 0);
        return '<li' + (isCur ? ' class="tl-sat-current"' : '') + '>'
          + esc(s)
          // ONE parenthetical, not two: "identical to X" and "which is
          // the same grid" said the same thing, and "(selected)" then
          // followed as a second bare aside.
          + (also.length || isCur
            ? ' <em>(' + [].concat(
                // 'selected' FIRST: trailing it after 'byte-identical
                // to X, no bait' read as marking no-bait selected
                // (2026-08-20 review m7)
                isCur ? ['currently selected in Controls'] : [],
                also.length ? ['byte-identical to ' + esc(also.join(', '))]
                  : []).join('; ') + ')</em>'
            : '') + '</li>';
      }).filter(Boolean).join('');
    if (!rows) return '';
    return '<div class="tl-satblock"><strong>Where IV choice cannot '
      + 'matter</strong> (computed from the embedded grids, per moveset):'
      + '<ul>' + rows + '</ul></div>';
  }
  function renderTldr() {
    if (!HAS_RECO || !(D.reco.cards || []).length) {
      showMissing('tl-tldr',
        'the short version (recommended spreads and their headline numbers) '
        + 'lands after the sim grids bake -- the recommendation blob is '
        + 'computed in the assembly phase and is not embedded in this page '
        + 'yet. The panels below already work off whatever IS embedded.'
        + ' The per-moveset saturation summary below is computed by this '
        + 'page from the embedded grids and does not need it.');
      var sb = satBlock();
      if (sb) {
        setHtml('tl-tldr', $('tl-tldr').innerHTML + sb);
      }
      // Derived from every VISIBLE card, not cards[0]: the band showed the
    // cohort-only explanation while three of four cards were flagged
    // "(not the selected grid)".
    var bridge = '';
    var shown = (D.reco.cards || []).slice(0, 4);
    var offGridNames = [];
    shown.forEach(function (c) {
      var g = cardGrid(c);
      if (g && g !== state.label) {
        var nm = gridPretty(g);
        if (offGridNames.indexOf(nm) < 0) offGridNames.push(nm);
      }
    });
    var offGridCards = shown.filter(function (c) {
      var g = cardGrid(c);
      return g && g !== state.label;
    }).length;
    if (offGridNames.length) {
      bridge = (offGridCards === shown.length
        ? 'All ' + shown.length + ' cards are computed on '
        : offGridCards + ' of these ' + shown.length
          + ' cards are computed on ')
        + esc(offGridNames.join(' and '))
        + ', while the panels below are showing '
        + esc(gridPretty(state.label))
        + ' - each card carries its own grid chip, and switching the grid '
        + 'in Controls puts them on the same footing. ';
    }
    if (shown.length) {
      bridge += 'Card numbers use the top-512 cohort, while the panels '
        + 'below follow the cohort control (which starts on all 4096), so '
        + 'the same spread can read differently in the two places. ';
    }
    setHtml('tl-tldr-link', bridge + '');
      return;
    }
    var poolN = (D.reco.pool_n !== undefined && D.reco.pool_n !== null)
      ? D.reco.pool_n
      : ((D.meta_wins || {}).pool_n);
    var cardGridDefault = D.reco.primary_grid || null;
    var cards = (D.reco.cards || []).slice(0, 4).map(function (c) {
      var m = c.metrics || {};
      // Which grid produced these numbers? Cards may name their own; else
      // the blob's primary_grid. Never leave it unlabeled.
      var cGrid = cardGrid(c) || cardGridDefault;
      var gridLab = cGrid ? ' - ' + gridPretty(cGrid) : '';
      function metricDiv(key, suffix, dp) {
        return '<div class="tl-tldr-metric"><span class="tl-tldr-num">'
          + esc(metricText(m[key], dp)) + esc(suffix || '')
          + '</span><span class="tl-tldr-lab">' + esc(metricLabel(key))
          + esc(gridLab) + '</span></div>';
      }
      var bits = [];
      // Schema A (flat): metrics.cov512_00 = 95.12
      // Schema B (per grid): metrics[gridLabel] = {"1-1": 100.0, ...,
      //                       pretty: "<fast>/<c1>+<c2>, baiting"}
      // Both are rendered from the data; neither is assumed.
      var covDone = false;
      for (var k = 0; k < COV_PREF.length; k++) {
        if (typeof m[COV_PREF[k]] === 'number') {
          bits.push('<div class="tl-tldr-metric"><span class="tl-tldr-num">'
            + esc(covText(m[COV_PREF[k]])) + '%</span>'
            + '<span class="tl-tldr-lab">' + esc(metricLabel(COV_PREF[k]))
            + esc(gridLab) + '</span></div>');
          covDone = true;
          break;
        }
      }
      if (!covDone && cGrid && m[cGrid] && typeof m[cGrid] === 'object') {
        var g = m[cGrid];
        // The card states its OWN tiebreak chain; its headline number must
        // be that chain's primary metric, not the global pick order (which
        // belongs to the reco's primary grid and can name a scenario this
        // card never ranked on).
        var own = cardPrimaryScenario(c);
        var picks = (own && typeof g[own] === 'number') ? [own]
          : (D.reco.pick_scenarios || []).filter(function (s) {
            return typeof g[s] === 'number';
          });
        if (!picks.length) {
          picks = Object.keys(g).filter(function (s) {
            return typeof g[s] === 'number';
          });
        }
        if (picks.length) {
          bits.push('<div class="tl-tldr-metric"><span class="tl-tldr-num">'
            + esc(covText(g[picks[0]])) + '%</span>'
            + '<span class="tl-tldr-lab">top-512 ' + esc(OPP)
            + ' beaten (' + esc(picks[0]) + ' shields) - '
            + esc(g.pretty || gridPretty(cGrid)) + '</span></div>');
        }
      }
      var mw = m.meta_wins_11;
      if (typeof mw === 'number') {
        bits.push(metricDiv('meta_wins_11',
          (poolN !== undefined && poolN !== null) ? ' / ' + poolN : ''));
      } else if (mw && typeof mw === 'object') {
        // Keyed by moveset slug ({<arm>: 58, <arm2>: 45}); show the one
        // belonging
        // to this card's grid, named.
        var msKey = cGrid ? String(cGrid).split('_')[0] : null;
        var useKey = (msKey && mw[msKey] !== undefined)
          ? msKey : Object.keys(mw)[0];
        if (useKey !== undefined && typeof mw[useKey] === 'number') {
          bits.push('<div class="tl-tldr-metric"><span class="tl-tldr-num">'
            + esc(mw[useKey])
            + ((poolN !== undefined && poolN !== null) ? ' / ' + esc(poolN)
              : '')
            + '</span><span class="tl-tldr-lab">meta wins (1-1 shields) - '
            + esc(msLabelFromKey(useKey)) + '</span></div>');
        }
      }
      var spread = spreadText(c);
      var tie = expandOppShorthand(tieText(c));
      var basisPretty = c.basis_pretty || (cGrid ? gridPretty(cGrid) : '');
      var isDefaultGrid = (cGrid === state.label);
      return '<div class="tl-card tl-tldr-card"><h4>'
        + esc(expandOppShorthand(c.title || ''))
        + '</h4>'
        + (basisPretty
          ? '<div class="tl-chip '
            + (isDefaultGrid ? 'tl-chip-ok' : 'tl-chip-warn')
            + '" title="' + esc(isDefaultGrid
              ? 'Computed on the grid currently selected in Controls.'
              : 'Computed on a DIFFERENT grid than the one selected in '
                + 'Controls (' + gridPretty(state.label) + ').')
            + '">' + esc(basisPretty)
            + esc(isDefaultGrid ? '' : ' (not the selected grid)')
            + '</div>' : '')
        + (spread ? '<div class="tl-card-spread">' + esc(spread)
          + '</div>' : '')
        + (tie ? '<div class="tl-card-caveat">' + esc(tie) + '</div>' : '')
        + (bits.length ? '<div class="tl-tldr-metrics">' + bits.join('')
          + '</div>' : '')
        + '</div>';
    }).join('');
    var headline = '';
    if (D.reco.headline) {
      headline = '<p class="tl-tldr-headline">'
        + esc(expandOppShorthand(D.reco.headline))
        + (D.reco.primary_grid
          ? ' <span class="tl-tldr-qual">[that sentence is for '
            + esc(gridPretty(D.reco.primary_grid)) + ' only]</span>'
          : '')
        + '</p>';
    }
    setHtml('tl-tldr', headline + satBlock() + cards);
    // Derived from every VISIBLE card, not cards[0]: the band showed the
    // cohort-only explanation while three of four cards were flagged
    // "(not the selected grid)".
    var bridge = '';
    var shown = (D.reco.cards || []).slice(0, 4);
    var offGridNames = [];
    shown.forEach(function (c) {
      var g = cardGrid(c);
      if (g && g !== state.label) {
        var nm = gridPretty(g);
        if (offGridNames.indexOf(nm) < 0) offGridNames.push(nm);
      }
    });
    var offGridCards = shown.filter(function (c) {
      var g = cardGrid(c);
      return g && g !== state.label;
    }).length;
    if (offGridNames.length) {
      bridge = (offGridCards === shown.length
        ? 'All ' + shown.length + ' cards are computed on '
        : offGridCards + ' of these ' + shown.length
          + ' cards are computed on ')
        + esc(offGridNames.join(' and '))
        + ', while the panels below are showing '
        + esc(gridPretty(state.label))
        + ' - each card carries its own grid chip, and switching the grid '
        + 'in Controls puts them on the same footing. ';
    }
    if (shown.length) {
      bridge += 'Card numbers use the top-512 cohort, while the panels '
        + 'below follow the cohort control (which starts on all 4096), so '
        + 'the same spread can read differently in the two places. ';
    }
    setHtml('tl-tldr-link', bridge +
      'The grid below shows every one of the ' + N + ' x ' + N
      + ' ' + FOCAL + '-vs-' + OPP + ' matchups; below it are the cliff '
      + '(coverage vs attack) and frontier (attack vs rank) panels, then '
      + 'the full panels (coverage, Pareto, '
      + 'drill-down, mechanism), then the Recommendations cards'
      + (D.licki_denial ? ', and finally the anti-' + FOCAL + ' ' + OPP
        + ' section' : '') + '.');
  }

  // ---- headline-move breakpoint classes (the cliff / frontier colour) ----
  // Three states a spread can be in against the analyzed opponent: it
  // reaches the higher damage tier of the focal headline move (see
  // focalMoveId) against EVERY opponent spread, against the rank-1 one
  // only, or against neither. All three come from the closed-form layer's
  // own arrays.
  var CLIFF_COLORS = ['#2563eb', '#0d9488', '#d97706'];
  function spClasses() {
    var bp = D.breakpoints || {}, sp = null;
    // The move id is read from the blob (focalMoveId), never spelled.
    try { sp = bp.thievul_offense.moves[focalMoveId()]; }
    catch (e) { sp = null; }
    if (!sp) return null;
    var tier = sp.tier_vs_rank1_licki_by_spread;
    var geAll = (sp.ge_hi_tier_count_by_spread || {}).all;
    var bpk = sp.breakpoint_vs_rank1_licki || {};
    var hi = bpk.hi_tier;
    if (!tier || hi === undefined || hi === null) return null;
    var nAll = ((bp.meta || {}).cohort_sizes || {}).all || N;
    var cls = new Uint8Array(N);
    for (var i = 0; i < N; i++) {
      cls[i] = (geAll && geAll[i] >= nAll) ? 2 : ((tier[i] >= hi) ? 1 : 0);
    }
    var fc = sp.full_coverage_vs_all_licki || {};
    return {
      cls: cls, hi: hi, tier: tier,
      groups: [
        { k: 2, name: 'clears the ' + focalMoveAbbr() + ' breakpoint vs EVERY '
            + OPP, color: CLIFF_COLORS[0] },
        { k: 1, name: 'clears it vs the rank-1 ' + OPP + ' only',
          color: CLIFF_COLORS[1] },
        { k: 0, name: 'misses the ' + focalMoveAbbr() + ' breakpoint',
          color: CLIFF_COLORS[2] }
      ],
      thresholds: [
        { x: bpk.min_thievul_atk_for_hi_tier,
          label: 'clears vs rank-1 ' + OPP },
        { x: fc.min_thievul_atk_for_hi_tier_vs_every_licki,
          label: 'clears vs every ' + OPP }
      ].filter(function (o) { return typeof o.x === 'number'; })
    };
  }
  // Label placement that cannot run off the plot: points near the top get
  // their label BELOW, and labels that would collide horizontally are
  // staggered across left/centre/right anchors.
  function labelPositions(xs, ys, yTop) {
    var order = xs.map(function (x, i) { return i; }).sort(function (a, b) {
      return xs[a] - xs[b];
    });
    var pos = new Array(xs.length);
    var span = Math.max.apply(null, xs) - Math.min.apply(null, xs) || 1;
    var lastX = -Infinity, slot = 0;
    order.forEach(function (i) {
      if ((xs[i] - lastX) / span < 0.06) {
        slot = (slot + 1) % 3;
      } else {
        slot = 0;
      }
      lastX = xs[i];
      var vert = (ys[i] >= yTop) ? 'bottom' : 'top';
      pos[i] = vert + [' center', ' right', ' left'][slot];
    });
    return pos;
  }
  function thresholdShapes(sc, c) {
    return (sc.thresholds || []).map(function (th) {
      return {
        type: 'line', yref: 'paper', y0: 0, y1: 1, xref: 'x',
        x0: th.x, x1: th.x,
        line: { color: c.muted, width: 1, dash: 'dash' }
      };
    });
  }
  function thresholdAnnotations(sc, c, light) {
    // Pinned to the very top INSIDE edge. On the cliff the points reach
    // every height, so the chips are small and unbacked there; elsewhere a
    // faint plate keeps them readable.
    return (sc.thresholds || []).map(function (th, i) {
      var a = {
        xref: 'x', x: th.x, yref: 'paper', y: 1,
        xanchor: 'left', yanchor: 'top', showarrow: false,
        text: ' ' + th.label + ' (atk ' + th.x + ')',
        font: { color: c.muted, size: light ? 9 : 10 }
      };
      if (light) {
        a.bgcolor = hexToRgba(themeColor('--surface-2'), 0.55);
        a.borderpad = 1;
        a.y = 1 - i * 0.045;
      } else {
        a.bgcolor = c.legendBg;
        a.borderpad = 2;
        a.opacity = 0.9;
        a.y = 0.97 - i * 0.07;
      }
      return a;
    });
  }

  // ---- does the headline breakpoint explain the current view? ----
  // Mean coverage per breakpoint class, for whatever grid/scenario/cohort
  // is selected. The classes are ordered misses -> rank-1-only -> all, so
  // if the breakpoint drives the outcome the means rise across them. When
  // they do not, the colouring would quietly imply an explanation the data
  // does not support -- so the panel says so instead.
  // Coverage range (percentage points) below which a view counts as flat:
  // no causal claim is made about it in either direction.
  var FLAT_RANGE_PP = 1.0;
  // Below this the means merely fail to rise; at or above it they are
  // meaningfully INVERTED and the sentence says so in those words.
  var CLIFF_INVERSION_PP = 5.0;
  function capFirst(s) {
    s = String(s || '');
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  }
  // ptrOverride: a FIXED pointer string, used only by the rule disclosure
  // so its quoted examples do not vary with the grid dropdown.
  function cliffExplanation(sc, cov, ptrOverride) {
    var sums = [0, 0, 0], counts = [0, 0, 0];
    for (var i = 0; i < N; i++) {
      var k = sc.cls[i];
      sums[k] += cov.pct[i];
      counts[k] += 1;
    }
    var means = sums.map(function (s, k) {
      return counts[k] ? s / counts[k] : null;
    });
    var present = [0, 1, 2].filter(function (k) { return counts[k] > 0; });
    var vals = present.map(function (k) { return means[k]; });
    var monotone = true;
    for (var j = 1; j < vals.length; j++) {
      if (vals[j] < vals[j - 1] - 1e-9) monotone = false;
    }
    var gap = vals.length > 1 ? (vals[vals.length - 1] - vals[0]) : 0;
    var txt = present.map(function (k) {
      return ['misses', 'rank-1 only', 'clears vs all'][k] + ' '
        + fmt(means[k], 1) + '%';
    }).join(' / ');
    var cmn = Infinity, cmx = -Infinity;
    for (var q = 0; q < cov.pct.length; q++) {
      if (cov.pct[q] < cmn) cmn = cov.pct[q];
      if (cov.pct[q] > cmx) cmx = cov.pct[q];
    }
    // NO CAUSAL LANGUAGE. This panel measures one thing -- coverage by
    // headline-move breakpoint class -- so it reports exactly that: the
    // class means, whether they rise, and how wide the spread is. It does
    // not attribute the outcome to the breakpoint, to bulk, or to
    // anything else, because nothing here measures explanatory power.
    if (cmx - cmn <= FLAT_RANGE_PP) {
      var same = (cmx - cmn <= 1e-9);
      return {
        text: 'Nothing separates the spreads in this view: all '
          + commas(cov.pct.length) + ' ' + FOCAL + ' spreads sit '
          + (same ? 'at ' + fmt(cmn, 1) + '%'
            : 'between ' + fmt(cmn, 1) + '% and ' + fmt(cmx, 1) + '% (a '
              + fmt(cmx - cmn, 2) + '-point spread)') + '.'
          // No pointer here: the ALREADY WON / UNWINNABLE / FLAT banner
          // appended to this same caption carries it, and printing both
          // repeated one sentence verbatim inside one caption.
          + (ptrOverride ? ' ' + capFirst(ptrOverride) : ''),
        means: means, monotone: true, gap: 0, flat: true
      };
    }
    return {
      text: 'Mean coverage by ' + focalMove() + ' breakpoint class: '
        + txt + '. '
        + (monotone
          ? 'The means rise across the classes, by ' + fmt(gap, 1)
            + ' points from lowest to highest.'
          : (vals.length > 1
              && vals[0] - vals[vals.length - 1] >= CLIFF_INVERSION_PP
            ? 'The means run the OTHER way here: spreads that MISS the '
              + 'breakpoint average ' + fmt(vals[0], 1) + '%, while '
              + 'spreads that clear it against every ' + OPP + ' average '
              + fmt(vals[vals.length - 1], 1) + '% -- '
              + fmt(vals[0] - vals[vals.length - 1], 1) + ' points LOWER.'
            : 'The means do not rise across the classes: spreads that miss '
              + 'the breakpoint average at least as much coverage as '
              + 'spreads that clear it.'))
        + ' Coverage across all ' + commas(cov.pct.length) + ' spreads '
        + 'ranges ' + fmt(cmn, 1) + '% to ' + fmt(cmx, 1) + '%.',
      means: means, monotone: monotone, gap: gap, flat: false
    };
  }

  // ---- panel: the cliff (coverage vs attack) ----
  // Single-hue sequential ramp for the continuous colourings, same blue
  // family as the "clears vs every" class so the panel reads as one system.
  var CLIFF_RAMP = [[0, '#eff6ff'], [0.25, '#93c5fd'], [0.5, '#3b82f6'],
                    [0.75, '#1d4ed8'], [1, '#1e3a8a']];
  function renderCliff(cov) {
    var host = $('tl-cliff');
    if (!host) return;
    if (cov.missing) {
      showMissing('tl-cliff', cov.missing, cov.kind);
      setHtml('tl-cliff-note', '');       // never leave stale numbers up
      return;
    }
    var sc = spClasses();
    if (!sc) {
      showMissing('tl-cliff', 'the closed-form breakpoint layer is not '
        + 'embedded in this page, so ' + focalMove() + ' breakpoint classes '
        + 'cannot be computed.');
      setHtml('tl-cliff-note', '');
      return;
    }
    host.innerHTML = '<div id="tl-cliff-plot" class="tl-plot"></div>';
    var T = D.thievul, c = plotChrome();
    var mode = state.cliffColor || 'sp';
    var traces = [];
    if (mode === 'sp') {
      traces = sc.groups.map(function (g) {
        var xs = [], ys = [], hv = [];
        for (var i = 0; i < N; i++) {
          if (sc.cls[i] !== g.k) continue;
          xs.push(T.atk[i]);
          ys.push(cov.pct[i]);
          hv.push(cliffHover(i, cov, sc));
        }
        return {
          type: 'scattergl', mode: 'markers', name: g.name,
          x: xs, y: ys, hovertext: hv,
          hovertemplate: '%{hovertext}<extra></extra>',
          marker: { size: 4, color: g.color, opacity: 0.65 }
        };
      });
    } else {
      var vals = (mode === 'def') ? T.def : T.hp;
      var xs2 = [], ys2 = [], hv2 = [], cv = [];
      for (var i2 = 0; i2 < N; i2++) {
        xs2.push(T.atk[i2]);
        ys2.push(cov.pct[i2]);
        cv.push(vals[i2]);
        hv2.push(cliffHover(i2, cov, sc));
      }
      traces.push({
        type: 'scattergl', mode: 'markers',
        name: (mode === 'def') ? 'defense' : 'HP',
        x: xs2, y: ys2, hovertext: hv2,
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: {
          size: 4, opacity: 0.7, color: cv, colorscale: CLIFF_RAMP,
          colorbar: { title: { text: (mode === 'def') ? 'defense' : 'HP',
                               side: 'right' }, thickness: 12 }
        }
      });
    }
    addMarkerOverlays(traces, function (i) { return T.atk[i]; },
                      function (i) { return cov.pct[i]; }, cov, c, false);
    var layout = baseLayout(
      gridPretty(state.label) + ' - ' + scenarioText(),
      FOCAL + ' effective attack',
      OPP + ' spreads beaten (%)');
    layout.yaxis.range = COV_Y_RANGE;
    layout.margin = { r: 190, t: 70, b: 60 };
    layout.shapes = thresholdShapes(sc, c);
    var sat = coverageSaturation(cov.pct);
    layout.annotations = thresholdAnnotations(sc, c, true)
      .concat(sat.note ? [satAnnotation(sat.text, c)] : []);
    Plotly.react('tl-cliff-plot', traces, layout, { responsive: true });
    var ex = cliffExplanation(sc, cov);
    // Neutral pointer only: naming a colouring is not an explanation, and
    // this panel must never imply one stat "explains" a view.
    var colourSays = (mode === 'sp')
      ? 'Colour is the ' + focalMove() + ' breakpoint class from the '
        + 'closed-form layer; colour by defense or HP to inspect other stat '
        + 'relationships.'
      : 'Colour is each spread\'s '
        + (mode === 'def' ? 'defense' : 'HP')
        + ' (single-hue ramp, darker = higher); the "' + focalMoveAbbr()
        + ' breakpoint class" '
        + 'setting colours by breakpoint class instead.';
    setHtml('tl-cliff-note',
      '<strong>' + esc(ex.text) + '</strong> ' + esc(colourSays) + ' '
      + 'Each dot is one of the 4096 ' + esc(FOCAL) + ' IV spreads: x is '
      + 'its effective attack, y is the share of the selected ' + esc(OPP)
      + ' cohort it beats. Dashed lines are the attack values where the '
      + esc(focalMove()) + ' breakpoint starts clearing. Follows the '
      + 'controls above: ' + esc(gridPretty(state.label)) + ', '
      + esc(scenarioText()) + ', cohort ' + esc(cohortLabel()) + '.'
      + esc(cohortWarnText())
      + esc(sat.note)
      + ' Diamonds are named builds, gold stars your own spreads (hover '
      + 'for names).');
  }
  function cliffHover(i, cov, sc) {
    return statLine('thievul', i)
      + '<br>coverage ' + fmt(cov.pct[i], 1) + '%'
      + '<br>' + focalMoveAbbr() + ' vs rank-1 ' + OPP + ': ' + sc.tier[i]
      + ' dmg (' + sc.hi + ' clears)';
  }

  // ---- panel: off the frontier (attack vs stat-product rank) ----
  function renderFrontier() {
    var host = $('tl-frontier');
    if (!host) return;
    var sc = spClasses();
    if (!sc) {
      showMissing('tl-frontier', 'the closed-form breakpoint layer is not '
        + 'embedded in this page, so this panel cannot be drawn.');
      setHtml('tl-frontier-note', '');
      return;
    }
    host.innerHTML = '<div id="tl-frontier-plot" class="tl-plot"></div>';
    var T = D.thievul, c = plotChrome();
    var traces = sc.groups.map(function (g) {
      var xs = [], ys = [], hv = [];
      for (var i = 0; i < N; i++) {
        if (sc.cls[i] !== g.k) continue;
        xs.push(T.atk[i]);
        ys.push(i + 1);
        hv.push(statLine('thievul', i) + '<br>attack ' + fmt(T.atk[i], 2)
          + '<br>' + focalMoveAbbr() + ' vs rank-1 ' + OPP + ': '
          + sc.tier[i] + ' dmg (' + sc.hi + ' clears)');
      }
      return {
        type: 'scattergl', mode: 'markers', name: g.name,
        x: xs, y: ys, hovertext: hv,
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 4, color: g.color, opacity: 0.65 }
      };
    });
    addMarkerOverlays(traces, function (i) { return T.atk[i]; },
                      function (i) { return i + 1; }, null, c, true);
    var layout = baseLayout(
      'Attack vs stat product (all 4096 spreads)',
      FOCAL + ' effective attack',
      FOCAL + ' stat-product rank (1 = best, log scale)');
    layout.yaxis.type = 'log';
    layout.yaxis.range = [Math.log(N + 200) / Math.LN10, -0.02];
    layout.yaxis.autorange = false;
    layout.margin = { r: 190, t: 90, b: 60 };
    layout.shapes = thresholdShapes(sc, c);
    layout.annotations = thresholdAnnotations(sc, c);
    Plotly.react('tl-frontier-plot', traces, layout, { responsive: true });
    // STATIC. This caption claimed control-independence in a sentence
    // that itself tracked the colour control -- two rounds running. The
    // colour here is fixed by construction, so the sentence has no state
    // to read and cannot drift again.
    setHtml('tl-frontier-note',
      'Reading guide: UP is a better stat-product rank, RIGHT is more '
      + 'attack, and the frontier -- the upper-right edge -- is where IV '
      + 'tech lives, because those spreads buy attack without giving up '
      + 'rank. Colour here is ALWAYS the ' + esc(focalMove())
      + ' breakpoint class '
      + '(fixed for this panel; the colour control above applies to the '
      + 'cliff panel only), and the dashed lines are the same breakpoint '
      + 'thresholds. The picture itself is the IV space: it does not '
      + 'change with the moveset/bait grid, the shield scenario or the '
      + esc(OPP) + ' cohort. Only your own spreads (gold stars) and the '
      + 'named builds are overlaid on it.');
  }

  // Named builds (deduped) + your own spreads, as overlay traces on any
  // x/y projection of the 4096 spreads.
  function addMarkerOverlays(traces, xOf, yOf, cov, c, withText) {
    var nb = namedBuilds();
    if (nb.length && withText === false) {
      traces.push({
        type: 'scatter', mode: 'markers', name: 'named builds',
        x: nb.map(function (b) { return xOf(b.idx); }),
        y: nb.map(function (b) { return yOf(b.idx); }),
        hovertext: nb.map(function (b) {
          return b.label + '<br>' + statLine('thievul', b.idx)
            + (cov ? '<br>coverage ' + fmt(cov.pct[b.idx], 1) + '%' : '');
        }),
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 9, color: c.ink, symbol: 'diamond-open',
                  line: { width: 2, color: c.ink } }
      });
    } else if (nb.length) {
      var xs = nb.map(function (b) { return xOf(b.idx); });
      var ys = nb.map(function (b) { return yOf(b.idx); });
      var yTop = Math.max.apply(null, ys)
        - 0.12 * (Math.max.apply(null, ys) - Math.min.apply(null, ys));
      traces.push({
        type: 'scatter', mode: 'markers+text', name: 'named builds',
        x: xs, y: ys,
        text: nb.map(function (b) { return b.tag; }),
        textposition: labelPositions(xs, ys, yTop),
        textfont: { color: c.ink, size: 9 },
        cliponaxis: false,
        hovertext: nb.map(function (b) {
          return b.label + '<br>' + statLine('thievul', b.idx)
            + (cov ? '<br>coverage ' + fmt(cov.pct[b.idx], 1) + '%' : '');
        }),
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 9, color: c.ink, symbol: 'diamond-open',
                  line: { width: 2, color: c.ink } }
      });
    }
    var mine = state.user.filter(function (u) { return u.side === 'thievul'; });
    if (mine.length) {
      traces.push({
        type: 'scatter', mode: 'markers', name: 'your spreads',
        x: mine.map(function (u) { return xOf(u.idx); }),
        y: mine.map(function (u) { return yOf(u.idx); }),
        hovertext: mine.map(function (u) {
          return 'YOURS: ' + u.label + '<br>' + statLine('thievul', u.idx)
            + (typeof u.cp === 'number' ? '<br>your CP ' + u.cp : '')
            + (cov ? '<br>coverage ' + fmt(cov.pct[u.idx], 1) + '%' : '');
        }),
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 12, color: c.gold, symbol: 'star',
                  line: { width: 1, color: c.ink } }
      });
    }
  }

  // ---- main scatter ----
  function colorGroups() {
    // Color = the headline move's damage tier vs the rank-1 opponent, when
    // the breakpoint layer is present; otherwise fall back to effective
    // attack (and SAY SO on the page).
    var bp = D.breakpoints || {};
    var dmg = null;
    try {
      dmg = bp.thievul_offense.moves[focalMoveId()]
        .tier_vs_rank1_licki_by_spread;
    } catch (e) { dmg = null; }
    if (!dmg) dmg = bp.sp_damage_vs_licki_rank1;
    if (dmg && dmg.length === N) {
      var byVal = {};
      for (var i = 0; i < N; i++) {
        var v = dmg[i];
        if (!byVal[v]) byVal[v] = [];
        byVal[v].push(i);
      }
      var vals = Object.keys(byVal).map(Number).sort(function (a, b) {
        return a - b;
      });
      return {
        mode: 'tier',
        groups: vals.map(function (v, gi) {
          return { name: focalMoveAbbr() + ' ' + v + ' dmg', idx: byVal[v],
                   color: tierColor(gi) };
        }),
        note: 'Color = ' + focalMove() + ' damage per hit vs the rank-1 '
          + OPP + ' (from the closed-form breakpoint layer).'
      };
    }
    return {
      mode: 'atk',
      groups: null,
      note: 'Color = effective attack (FALLBACK - the closed-form '
        + 'breakpoint layer is not embedded in this page, so damage tiers '
        + 'are not available).'
    };
  }

  function renderScatter(cov) {
    var host = $('tl-scatter');
    if (!host) return;
    if (cov.missing) {
      showMissing('tl-scatter', cov.missing, cov.kind);
      setHtml('tl-scatter-note', '');
      return;
    }
    host.innerHTML = '<div id="tl-scatter-plot" class="tl-plot"></div>';
    var T = D.thievul;
    var cg = colorGroups();
    var mw = HAS_META_WINS ? metaWinsArray() : null;
    var x = new Array(N), hov = new Array(N);
    for (var i = 0; i < N; i++) {
      x[i] = i + 1;
      hov[i] = FOCAL + ' ' + statLine('thievul', i)
        + '<br>coverage ' + fmt(cov.pct[i], 1) + '%'
        + (mw ? '<br>meta wins ' + fmt(mw.vals[i], 0) + '/'
          + D.meta_wins.pool_n + ' (' + mw.note + ')' : '');
    }
    var traces = [];
    if (cg.mode === 'tier') {
      cg.groups.forEach(function (g) {
        traces.push({
          type: 'scattergl', mode: 'markers', name: g.name,
          x: g.idx.map(function (i2) { return x[i2]; }),
          y: g.idx.map(function (i2) { return cov.pct[i2]; }),
          text: g.idx.map(function (i2) { return hov[i2]; }),
          hovertemplate: '%{text}<extra></extra>',
          marker: { size: 5, color: g.color, opacity: 0.75 }
        });
      });
    } else {
      traces.push({
        type: 'scattergl', mode: 'markers', name: FOCAL + ' spreads',
        x: x, y: Array.prototype.slice.call(cov.pct), text: hov,
        hovertemplate: '%{text}<extra></extra>',
        marker: {
          size: 5, opacity: 0.75, color: T.atk,
          colorscale: 'Viridis',
          colorbar: { title: 'atk', thickness: 10 }
        }
      });
    }
    var c = plotChrome();
    var nb = namedBuilds();
    if (nb.length) {
      // Markers + legend + HOVER only. On-plot text labels piled up
      // illegibly here (10 named ranks, several within a few ranks of each
      // other); the names live in the hover, the TL;DR band and the reco
      // cards instead.
      traces.push({
        type: 'scattergl', mode: 'markers', name: 'named builds',
        x: nb.map(function (b) { return b.idx + 1; }),
        y: nb.map(function (b) { return cov.pct[b.idx]; }),
        hovertext: nb.map(function (b) {
          return b.label + '<br>' + statLine('thievul', b.idx)
            + '<br>coverage ' + fmt(cov.pct[b.idx], 1) + '%';
        }),
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 11, color: c.ink, symbol: 'diamond-open',
                  line: { width: 2, color: c.ink } }
      });
    }
    var mine = state.user.filter(function (u) { return u.side === 'thievul'; });
    if (mine.length) {
      traces.push({
        type: 'scattergl', mode: 'markers', name: 'yours',
        x: mine.map(function (u) { return u.idx + 1; }),
        y: mine.map(function (u) { return cov.pct[u.idx]; }),
        hovertext: mine.map(function (u) {
          return 'YOURS: ' + u.label + '<br>' + statLine('thievul', u.idx)
            + '<br>coverage ' + fmt(cov.pct[u.idx], 1) + '%';
        }),
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 12, color: c.gold, symbol: 'star',
                  line: { width: 1, color: c.ink } }
      });
    }
    var layout = baseLayout(
      gridPretty(state.label) + ' - ' + scenarioText(),
      FOCAL + ' stat-product rank (1 = best)',
      OPP + ' spreads beaten (%)');
    layout.xaxis.range = [N + 60, -60];
    // Fixed y range: a flat 100% series otherwise auto-zooms to a 99-101%
    // window, which reads as a broken plot rather than "everything wins".
    layout.yaxis.range = COV_Y_RANGE;
    var sat = coverageSaturation(cov.pct);
    if (sat.note) {
      layout.annotations = [satAnnotation(sat.text, c)];
    }
    Plotly.react('tl-scatter-plot', traces, layout, { responsive: true });
    setHtml('tl-scatter-note',
      'Grid: ' + esc(gridPretty(state.label)) + '; ' + esc(scenarioText())
      + '. ' + esc(cg.note) + ' Cohort: ' + esc(cohortLabel()) + '. '
      + 'Denominator ' + plural(cov.denom, OPP + ' spread')
      + (state.scenarioAll ? ' x 9 scenarios' : '') + '.'
      + esc(cohortWarnText())
      + esc(sat.note)
      + ' Named builds are the diamond markers - hover for the name.');
  }

  // ---- coverage panel: 3x3 small multiples over all nine scenarios ----
  // "Should I build THIS IV" is really a question about all nine shield
  // scenarios at once. Tiles whose outcome is already decided (every
  // spread wins / no spread wins) are drawn as a flat labelled panel
  // instead of a dot cloud, so the eye goes straight to the scenarios
  // where IVs actually change something.
  // 3x3 small-multiples geometry, in paper coords. GRID_TOP leaves room
  // under the chart title for the top row's scenario labels; the gap
  // between rows (GRID_PITCH - GRID_H) has to hold one label line.
  var GRID_TOP = 0.955, GRID_PITCH = 0.325, GRID_H = 0.27;
  var GRID_LABEL_SHIFT = 3;   // pixels above its own subplot's top edge
  function renderScatterGrid(covs) {
    var host = $('tl-scatter');
    if (!host) return;
    var bad = covs.filter(function (c) { return c && c.missing; })[0];
    if (bad) {
      showMissing('tl-scatter', bad.missing, bad.kind);
      setHtml('tl-scatter-note', '');
      return;
    }
    host.innerHTML = '<div id="tl-scatter-plot" class="tl-plot '
      + 'tl-plot-grid"></div>';
    var c = plotChrome();
    var cg = colorGroups();
    var nb = namedBuilds();
    var mine = state.user.filter(function (u) { return u.side === 'thievul'; });
    var traces = [], anns = [], layout = {}, live = 0, flat = 0;
    var shownLegend = {};
    for (var si = 0; si < NS; si++) {
      var sf = Math.floor(si / 3), so = si % 3;
      var suffix = si === 0 ? '' : String(si + 1);
      var xa = 'x' + suffix, ya = 'y' + suffix;
      // Rows start BELOW paper-top: each subplot carries a scenario label
      // just above it, and the top row previously ran to y=1.0, which
      // pushed its label out of the plotting area and into the title.
      var x0 = so * 0.345, y1 = GRID_TOP - sf * GRID_PITCH;
      layout['xaxis' + suffix] = {
        domain: [x0, x0 + 0.30], anchor: ya,
        range: [N + 60, -60], gridcolor: c.grid, zerolinecolor: c.grid,
        showticklabels: (sf === 2), tickfont: { size: 9 }
      };
      layout['yaxis' + suffix] = {
        domain: [Math.max(0, y1 - GRID_H), y1], anchor: xa,
        range: COV_Y_RANGE, gridcolor: c.grid, zerolinecolor: c.grid,
        showticklabels: (so === 0), tickfont: { size: 9 }
      };
      var pct = covs[si].pct;
      var mn = Infinity, mx = -Infinity;
      for (var i = 0; i < N; i++) {
        if (pct[i] < mn) mn = pct[i];
        if (pct[i] > mx) mx = pct[i];
      }
      // The label sits ON its own subplot's top edge (y = 1 in that
      // subplot's domain) and is nudged up a few PIXELS, so it is
      // attached to its tile at any plot height. The old y = 1.13 was 13%
      // of the tile height above the tile -- most of the inter-row gap --
      // so every label floated against the tile ABOVE it, and the top
      // row's labels collided with the chart title.
      anns.push({
        xref: xa + ' domain', yref: ya + ' domain', x: 0.5, y: 1,
        yshift: GRID_LABEL_SHIFT,
        xanchor: 'center', yanchor: 'bottom', showarrow: false,
        text: '<b>' + scenarioLabel(si) + '</b>',
        font: { color: c.ink, size: 11 }
      });
      // Decided tiles: say what they are, do not draw 4096 identical dots.
      var decided = null;
      if (mn >= 100 - 1e-9) {
        decided = 'every ' + FOCAL + ' spread beats every ' + OPP + ' here';
      } else if (mx <= 1e-9) {
        decided = 'no ' + FOCAL + ' spread beats any ' + OPP + ' here';
      } else if (mx < 1) {
        decided = 'no ' + FOCAL + ' spread wins more than ' + fmt(mx, 2)
          + '% here';
      }
      if (decided) {
        flat++;
        anns.push({
          xref: xa + ' domain', yref: ya + ' domain', x: 0.5, y: 0.5,
          xanchor: 'center', yanchor: 'middle', showarrow: false,
          text: decided, font: { color: c.muted, size: 10 },
          bgcolor: c.legendBg, bordercolor: c.legendBorder,
          borderwidth: 1, borderpad: 4, align: 'center'
        });
        // one invisible point keeps the subplot's axes alive
        traces.push({ type: 'scatter', mode: 'markers', x: [N / 2],
                      y: [50], xaxis: xa, yaxis: ya, showlegend: false,
                      hoverinfo: 'skip',
                      marker: { size: 0.1, color: 'rgba(0,0,0,0)' } });
        continue;
      }
      live++;
      var groups = (cg.mode === 'tier') ? cg.groups
        : [{ name: FOCAL + ' spreads', idx: null, color: c.muted }];
      groups.forEach(function (g) {
        var xs = [], ys = [], hv = [];
        var idxs = g.idx;
        if (idxs) {
          for (var q = 0; q < idxs.length; q++) {
            xs.push(idxs[q] + 1);
            ys.push(pct[idxs[q]]);
            hv.push(statLine('thievul', idxs[q]) + '<br>'
              + scenarioLabel(si) + ' coverage ' + fmt(pct[idxs[q]], 1) + '%');
          }
        } else {
          for (var q2 = 0; q2 < N; q2++) {
            xs.push(q2 + 1);
            ys.push(pct[q2]);
            hv.push(statLine('thievul', q2) + '<br>' + scenarioLabel(si)
              + ' coverage ' + fmt(pct[q2], 1) + '%');
          }
        }
        traces.push({
          type: 'scattergl', mode: 'markers', name: g.name,
          legendgroup: g.name, showlegend: !shownLegend[g.name],
          x: xs, y: ys, hovertext: hv,
          hovertemplate: '%{hovertext}<extra></extra>',
          xaxis: xa, yaxis: ya,
          marker: { size: 3, color: g.color, opacity: 0.6 }
        });
        shownLegend[g.name] = 1;
      });
      // Named builds + your own spreads go ONLY on the live tiles.
      if (nb.length) {
        traces.push({
          type: 'scatter', mode: 'markers', name: 'named builds',
          legendgroup: 'named builds',
          showlegend: !shownLegend['named builds'],
          x: nb.map(function (b) { return b.idx + 1; }),
          y: nb.map(function (b) { return pct[b.idx]; }),
          hovertext: nb.map(function (b) {
            return b.label + '<br>' + scenarioLabel(si) + ' coverage '
              + fmt(pct[b.idx], 1) + '%';
          }),
          hovertemplate: '%{hovertext}<extra></extra>',
          xaxis: xa, yaxis: ya,
          marker: { size: 7, color: c.ink, symbol: 'diamond-open',
                    line: { width: 1.5, color: c.ink } }
        });
        shownLegend['named builds'] = 1;
      }
      if (mine.length) {
        traces.push({
          type: 'scatter', mode: 'markers', name: 'your spreads',
          legendgroup: 'your spreads',
          showlegend: !shownLegend['your spreads'],
          x: mine.map(function (u) { return u.idx + 1; }),
          y: mine.map(function (u) { return pct[u.idx]; }),
          hovertext: mine.map(function (u) {
            return 'YOURS: ' + u.label + '<br>' + scenarioLabel(si)
              + ' coverage ' + fmt(pct[u.idx], 1) + '%';
          }),
          hovertemplate: '%{hovertext}<extra></extra>',
          xaxis: xa, yaxis: ya,
          marker: { size: 10, color: c.gold, symbol: 'star',
                    line: { width: 1, color: c.ink } }
        });
        shownLegend['your spreads'] = 1;
      }
    }
    layout.title = gridPretty(state.label)
      + ' - all 9 shield scenarios (rows: your shields, columns: theirs)';
    layout.paper_bgcolor = c.paper;
    layout.plot_bgcolor = c.plot;
    layout.font = { color: c.font, size: 11 };
    layout.hovermode = 'closest';
    layout.hoverlabel = {
      bgcolor: c.hoverBg, bordercolor: c.hoverBorder,
      font: { size: 11, color: c.font, family: 'monospace' },
      namelength: -1, align: 'left'
    };
    layout.legend = { bgcolor: c.legendBg, bordercolor: c.legendBorder,
                      borderwidth: 1, x: 1.01, xanchor: 'left', y: 1,
                      yanchor: 'top' };
    layout.margin = { l: 55, r: 210, t: 70, b: 45 };
    layout.annotations = anns;
    Plotly.react('tl-scatter-plot', traces, layout, { responsive: true });
    setHtml('tl-scatter-note',
      'One tile per shield scenario: rows are YOUR shields (0/1/2), '
      + 'columns are the ' + esc(OPP) + '\'s. Each dot is one of the 4096 '
      + esc(FOCAL) + ' spreads (x = stat-product rank, y = share of the '
      + 'cohort beaten, shared 0-100% scale). ' + esc(cg.note) + ' '
      + flat + ' of 9 tiles are already decided and are drawn as a label '
      + 'instead of a dot cloud; the other ' + live + ' are where IVs '
      + 'change the result, and only those carry the named-build diamonds '
      + 'and your gold stars. Every dot is plotted -- nothing is thinned '
      + 'or sampled. This view follows the grid and cohort controls ('
      + esc(gridPretty(state.label)) + ', ' + esc(cohortLabel())
      + ') and IGNORES the shield-scenario dropdown, since it shows all '
      + 'nine at once.' + esc(cohortWarnText()));
  }

  // ---- pareto ----
  // Meta wins for the CURRENT grid + scenario when the richer per-grid
  // table is present; otherwise the contract's fixed 1-1 array, labeled.
  function metaWinsArray() {
    var MW = D.meta_wins;
    if (!MW) return null;
    var byGrid = MW.wins || null;
    if (byGrid && state.label && byGrid[state.label]) {
      var byS = byGrid[state.label];
      if (state.scenarioAll) {
        var keys = Object.keys(byS);
        if (keys.length) {
          var acc = new Float64Array(N);
          keys.forEach(function (k) {
            var a = byS[k];
            for (var i = 0; i < N; i++) acc[i] += a[i];
          });
          for (var j = 0; j < N; j++) acc[j] /= keys.length;
          return { vals: acc, note: 'mean over ' + keys.length
            + ' shield scenarios, grid ' + gridPretty(state.label) };
        }
      } else {
        var arr = byS[scenarioLabel(state.si)];
        if (arr) {
          return { vals: arr, note: 'shields ' + scenarioLabel(state.si)
            + ', grid ' + gridPretty(state.label) };
        }
      }
    }
    if (MW.wins_11) {
      return { vals: MW.wins_11, note: 'FIXED at ' + (MW.wins_11_key
        || '1-1 shields, landing-build moveset') + ' - it does NOT follow '
        + 'the grid/scenario dropdowns' };
    }
    return null;
  }

  function renderPareto(cov) {
    if (!HAS_META_WINS) {
      setHtml('tl-pareto-note', '');
      showMissing('tl-pareto',
        'meta_wins (per-IV wins vs the dive pool at 1-1) is not embedded '
        + 'in this page, so the Pareto panel cannot be drawn.');
      return;
    }
    if (cov.missing) {
      showMissing('tl-pareto', cov.missing, cov.kind);
      setHtml('tl-pareto-note', '');
      return;
    }
    var mw = metaWinsArray();
    if (!mw) {
      showMissing('tl-pareto',
        'meta_wins carries no usable win array for this selection.');
      return;
    }
    var host = $('tl-pareto');
    host.innerHTML = '<div id="tl-pareto-plot" class="tl-plot"></div>';
    var W = mw.vals;
    var pts = [];
    for (var i = 0; i < N; i++) pts.push({ i: i, w: W[i], c: cov.pct[i] });
    // Pareto frontier: maximize both meta wins and opponent coverage.
    var order = pts.slice().sort(function (a, b) {
      return (b.w - a.w) || (b.c - a.c);
    });
    var front = [], bestC = -1;
    for (var k = 0; k < order.length; k++) {
      if (order[k].c > bestC) { front.push(order[k]); bestC = order[k].c; }
    }
    var frontSet = {};
    front.forEach(function (p) { frontSet[p.i] = 1; });
    var c = plotChrome();
    function hov(p) {
      return statLine('thievul', p.i)
        + '<br>meta wins ' + fmt(p.w, 0) + '/' + D.meta_wins.pool_n
        + '<br>' + OPP + ' coverage ' + fmt(p.c, 1) + '%';
    }
    var rest = pts.filter(function (p) { return !frontSet[p.i]; });
    var traces = [{
      type: 'scattergl', mode: 'markers', name: 'dominated',
      x: rest.map(function (p) { return p.w; }),
      y: rest.map(function (p) { return p.c; }),
      hovertext: rest.map(hov), hovertemplate: '%{hovertext}<extra></extra>',
      marker: { size: 4, color: c.muted, opacity: 0.5 }
    }, {
      type: 'scattergl', mode: 'markers', name: 'Pareto frontier',
      x: front.map(function (p) { return p.w; }),
      y: front.map(function (p) { return p.c; }),
      hovertext: front.map(hov), hovertemplate: '%{hovertext}<extra></extra>',
      marker: { size: 8, color: themeColor('--win') }
    }];
    var nb = namedBuilds();
    if (nb.length) {
      // Hover-only names here too (see renderScatter).
      traces.push({
        type: 'scattergl', mode: 'markers', name: 'named builds',
        x: nb.map(function (b) { return W[b.idx]; }),
        y: nb.map(function (b) { return cov.pct[b.idx]; }),
        hovertext: nb.map(function (b) {
          return b.label + '<br>' + hov({ i: b.idx, w: W[b.idx],
                                          c: cov.pct[b.idx] });
        }),
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 11, color: c.ink, symbol: 'diamond-open',
                  line: { width: 2, color: c.ink } }
      });
    }
    var mine = state.user.filter(function (u) { return u.side === 'thievul'; });
    if (mine.length) {
      traces.push({
        type: 'scattergl', mode: 'markers', name: 'yours',
        x: mine.map(function (u) { return W[u.idx]; }),
        y: mine.map(function (u) { return cov.pct[u.idx]; }),
        hovertext: mine.map(function (u) {
          return 'YOURS: ' + u.label + '<br>'
            + hov({ i: u.idx, w: W[u.idx], c: cov.pct[u.idx] });
        }),
        hovertemplate: '%{hovertext}<extra></extra>',
        marker: { size: 12, color: c.gold, symbol: 'star',
                  line: { width: 1, color: c.ink } }
      });
    }
    var layout = baseLayout(
      'Meta wins vs ' + OPP + ' coverage',
      'Meta wins (out of ' + D.meta_wins.pool_n + ')',
      OPP + ' spreads beaten (%)');
    layout.yaxis.range = COV_Y_RANGE;
    var psat = coverageSaturation(cov.pct);
    if (psat.note) layout.annotations = [satAnnotation(psat.text, c)];
    Plotly.react('tl-pareto-plot', traces, layout, { responsive: true });
    setHtml('tl-pareto-note',
      // Reading guide FIRST, like every other panel: the frontier is
      // defined, the tradeoff named, and its size stated -- three green
      // dots with no caption look equally like the finding and like a
      // broken render.
      // The DEFINITION is the one renderPareto actually computes (the
      // upper-right staircase, one point per step), so the printed size is
      // the size of the set the sentence describes. The old wording
      // defined a different set and printed this count beside it, off by
      // up to 4,095. The trade-off claim is gone: it was asserted in every
      // state, including the flat ones where no trade-off exists.
      'Reading guide: RIGHT is more meta wins, UP is more ' + esc(OPP)
      + ' beaten. The <strong>frontier</strong> (highlighted) is the '
      + 'upper-right staircase: a spread is on it when no other spread has '
      + 'at least as many meta wins AND at least as much coverage; exact '
      + 'ties are drawn once. That is '
      // Count SPREADS whose (wins, coverage) sits on a frontier step,
      // not the steps themselves (678 spreads rendered as "1" --
      // 2026-08-19 verify medium).
      + esc(fmt((function () {
          var steps = {};
          front.forEach(function (f) { steps[f.w + '|' + f.c] = true; });
          return pts.filter(function (p) {
            return steps[p.w + '|' + p.c];
          }).length;
        })(), 0)) + ' of ' + esc(commas(N))
      + ' spreads here - every other point is at or behind a step of it. '
      + 'Meta axis: ' + esc(mw.note) + '. '
      + (D.meta_wins && D.meta_wins.pool_has_opponent
        ? 'NOTE: the meta-wins axis counts the whole dive pool, which '
          + 'INCLUDES this page\'s own ' + esc(OPP) + ' matchup -- the '
          + 'two axes are not fully independent. '
        : '')
      + esc(D.meta_wins.note || '')
      + ' ' + esc(OPP) + ' cohort: ' + esc(cohortLabel()) + '.'
      + esc(cohortWarnText())
      + esc(psat.note)
      + ' Named builds are the diamond markers - hover for the name.');
  }

  // ---- drill-down ----
  var _drillWarn = '';
  // Owned opponent spreads are offered as drill-down targets: the species
  // dropdown promises this, so it has to be true.
  function ownedLickiOptions() {
    return state.user.filter(function (u) { return u.side === 'licki'; });
  }
  function syncDrillPicker() {
    var sel = $('tl-drill-mine');
    if (!sel) return;
    var owned = ownedLickiOptions();
    sel.innerHTML = '';
    var o0 = document.createElement('option');
    o0.value = '';
    o0.textContent = owned.length
      ? 'jump to one of your ' + OPP + '...'
      : '(add your ' + OPP + ' above to pick them here)';
    sel.appendChild(o0);
    owned.forEach(function (u) {
      var o = document.createElement('option');
      o.value = String(u.idx + 1);
      o.textContent = u.label + ' ' + ivStr('licki', u.idx)
        + ' (rank ' + (u.idx + 1) + ')';
      sel.appendChild(o);
    });
    sel.disabled = !owned.length;
  }
  function drillLickiIndex() {
    var v = ($('tl-drill-licki') || {}).value || '';
    var ranks = parseRanks(v);
    if (!ranks.length && String(v).trim()) {
      _drillWarn += ' Could not read "' + String(v).trim() + '" as a '
        + OPP + ' rank or IV triple, so rank 1 is shown instead.';
    }
    return ranks.length ? ranks[0] : 0;
  }
  function drillThievulIndex() {
    var v = ($('tl-drill-thievul') || {}).value || '';
    var t = String(v).trim();
    var m = t.match(/^(\d+)\/(\d+)\/(\d+)$/);
    if (m) {
      var ix = ivIndex('thievul', +m[1], +m[2], +m[3]);
      if (ix < 0) {
        _drillWarn += ' ' + t + ' is not a ' + FOCAL + ' spread in the '
          + 'analyzed grid, so rank 1 is shown instead.';
      }
      return ix >= 0 ? ix : 0;
    }
    var r = parseInt(t, 10);
    if (!(!isNaN(r) && r >= 1 && r <= N) && t) {
      _drillWarn += ' Could not read "' + t + '" as a ' + FOCAL + ' rank '
        + 'or IV triple, so rank 1 is shown instead.';
    }
    return (!isNaN(r) && r >= 1 && r <= N) ? r - 1 : 0;
  }

  function renderDrill() {
    if (!HAS_GRIDS || !state.label) {
      showMissing('tl-drill-out',
        'no simulation grid is embedded in this page yet.');
      return;
    }
    var sis = [];
    for (var si = 0; si < NS; si++) {
      if (haveWon(state.label, si)) sis.push(si);
    }
    if (!sis.length) {
      showMissing('tl-drill-out',
        'the per-spread win grid (won_b64) for ' + state.label + ' is not '
        + 'embedded in this page, so the drill-down cannot be computed. '
        + 'The aggregate coverage panels above are unaffected.');
      return;
    }
    _drillWarn = '';
    var oi = drillLickiIndex();
    var fi = drillThievulIndex();
    setHtml('tl-drill-out', '<p class="tl-note">Computing...</p>');
    Promise.all(sis.map(function (s) { return decodeWon(state.label, s); }))
      .then(function (slices) {
        // Panel A: per-focal win COUNT vs the chosen opponent, out of the
        // embedded scenarios (a raw "6 of 9" reads; the old 66.7% did not).
        var denom = slices.length;
        var wins = new Int32Array(N);
        var wonScen = new Array(N);
        for (var f = 0; f < N; f++) {
          var c = 0, wl = [], ll = [];
          for (var s = 0; s < denom; s++) {
            if (bitAt(slices[s], f, oi)) { c++; wl.push(scenarioLabel(sis[s])); }
            else { ll.push(scenarioLabel(sis[s])); }
          }
          wins[f] = c;
          wonScen[f] = { won: wl, lost: ll };
        }
        // Panel B: which opponents beat the chosen focal (current scenario).
        // Under "all 9 (mean)" the table cannot average, so it shows ONE
        // scenario -- deterministically the first embedded one, not
        // whatever the reader happened to select before switching. Two
        // readers in the same state must see the same table.
        var scIdx = state.scenarioAll ? 0 : sis.indexOf(state.si);
        var useIdx = scIdx >= 0 ? scIdx : 0;
        var scUsed = sis[useIdx];
        var losses = [];
        for (var o = 0; o < N; o++) {
          if (!bitAt(slices[useIdx], fi, o)) losses.push(o);
        }
        var host = $('tl-drill-out');
        host.innerHTML =
          '<div id="tl-drill-plot" class="tl-plot"></div>'
          + '<p class="tl-note" id="tl-drill-note"></p>'
          + '<div id="tl-hardest"></div>';
        var c2 = plotChrome();
        var hv = new Array(N);
        for (var q = 0; q < N; q++) {
          hv[q] = statLine('thievul', q) + '<br>wins ' + wins[q] + ' of '
            + plural(denom, 'embedded scenario')
            + '<br>won: ' + (wonScen[q].won.join(', ') || 'none')
            + '<br>lost: ' + (wonScen[q].lost.join(', ') || 'none');
        }
        // Same headline-move damage-tier palette as the main scatter.
        var dcg = colorGroups();
        var traces = [];
        if (dcg.mode === 'tier') {
          dcg.groups.forEach(function (g) {
            traces.push({
              type: 'scattergl', mode: 'markers', name: g.name,
              x: g.idx.map(function (i2) { return i2 + 1; }),
              y: g.idx.map(function (i2) { return wins[i2]; }),
              text: g.idx.map(function (i2) { return hv[i2]; }),
              hovertemplate: '%{text}<extra></extra>',
              marker: { size: 4, color: g.color, opacity: 0.7 }
            });
          });
        } else {
          var xs = [], ys = [];
          for (var q2 = 0; q2 < N; q2++) { xs.push(q2 + 1); ys.push(wins[q2]); }
          traces.push({
            type: 'scattergl', mode: 'markers', name: FOCAL + ' spreads',
            x: xs, y: ys, hovertext: hv,
            hovertemplate: '%{hovertext}<extra></extra>',
            marker: { size: 4, color: c2.muted, opacity: 0.6 }
          });
        }
        var mine = state.user.filter(function (u) {
          return u.side === 'thievul';
        });
        if (mine.length) {
          traces.push({
            type: 'scattergl', mode: 'markers', name: 'yours',
            x: mine.map(function (u) { return u.idx + 1; }),
            y: mine.map(function (u) { return wins[u.idx]; }),
            hovertext: mine.map(function (u) {
              return 'YOURS: ' + u.label + '<br>' + hv[u.idx];
            }),
            hovertemplate: '%{hovertext}<extra></extra>',
            marker: { size: 12, color: c2.gold, symbol: 'star',
                      line: { width: 1, color: c2.ink } }
          });
        }
        var layout = baseLayout(
          'vs ' + OPP + ' ' + ivStr('licki', oi) + ' (' + OPP + ' rank '
            + (oi + 1) + ') - ' + gridPretty(state.label),
          FOCAL + ' stat-product rank (1 = best)',
          'shield scenarios won (of ' + denom + ')');
        layout.xaxis.range = [N + 60, -60];
        var tv = [], tt = [];
        for (var k2 = 0; k2 <= denom; k2++) {
          tv.push(k2);
          tt.push(k2 + '/' + denom);
        }
        layout.yaxis.tickmode = 'array';
        layout.yaxis.tickvals = tv;
        layout.yaxis.ticktext = tt;
        layout.yaxis.range = [0, denom + 0.5];
        Plotly.react('tl-drill-plot', traces, layout, { responsive: true });
        setHtml('tl-drill-note',
          'Grid: ' + esc(gridPretty(state.label))
          + ' (follows the grid dropdown above). '
          + 'Scenario slices embedded for this grid: '
          + sis.map(scenarioLabel).join(', ')
          + '.' + esc(_drillWarn)
          + ' Each dot is one ' + FOCAL + ' spread; the y value counts how '
          + 'many '
          + 'of those ' + denom + ' shield scenarios it wins against this '
          + OPP + ' (hover lists which). ' + esc(dcg.note)
          + ' Ties (score == 500) count as losses.'
          // STATIC and true in every state: this sentence was wrong under
          // "all 9 (mean)" when it promised the table follows the
          // dropdown. The table names its own scenario in its heading.
          + ' This plot does NOT follow the shield-scenario dropdown -- it '
          + 'shows all ' + denom + ' scenarios at once, by construction. '
          + 'The table below shows ONE scenario, named in its heading.');
        var rows = losses.slice(0, 40).map(function (o2) {
          var L = D.licki;
          return '<tr><td>' + (o2 + 1) + '</td><td>' + ivStr('licki', o2)
            + '</td><td>' + L.level[o2] + '</td><td>' + L.cp[o2]
            + '</td><td>' + fmt(L.atk[o2], 2) + '</td><td>'
            + fmt(L.def[o2], 2) + '</td><td>' + L.hp[o2] + '</td></tr>';
        }).join('');
        setHtml('tl-hardest',
          '<h4>' + esc(OPP) + ' spreads that the ' + esc(FOCAL) + ' '
          + esc(ivStr('thievul', fi)) + ' (' + esc(FOCAL)
          + ' stat-product rank ' + (fi + 1) + ') does NOT beat '
          + '(loss or tie) at ' + esc(scenarioLabel(scUsed)) + ' on '
          + esc(gridPretty(state.label)) + '</h4>'
          + '<p class="tl-note">' + losses.length + ' of ' + N
          + ' ' + esc(OPP) + ' spreads are not beaten (a tie, score '
          + 'exactly 500, is counted here too - the win grid records "did '
          + FOCAL + ' win", so ties and losses are indistinguishable in it)'
          + (FOCAL === OPP
            ? '. MIRROR NOTE: the anchor spread itself appears in this '
              + 'list - that row is its own diagonal tie, not a loss'
            : '')
          + (state.scenarioAll
            ? ' (the dropdown is on "all 9 (mean)", which this table cannot '
              + 'average - it lists the first embedded scenario, '
              + esc(scenarioLabel(scUsed)) + ')'
            : (scUsed !== state.si
              ? ' (shown for ' + esc(scenarioLabel(scUsed))
                + ' - the selected scenario is not embedded as a full grid)'
              : ''))
          + (losses.length
            ? '. First ' + Math.min(40, losses.length)
              + ' listed by ' + esc(OPP) + ' stat-product rank.</p>'
            : '.</p>')
          + (losses.length
            ? '<div class="tl-scroll"><table class="tl"><tr><th>' + esc(OPP)
              + ' rank</th>'
              + '<th>IVs</th><th>level</th><th>CP</th><th>atk</th>'
              + '<th>def</th><th>hp</th></tr>' + rows + '</table></div>'
            : '<p class="tl-note">None - this ' + esc(FOCAL) + ' spread '
              + 'beats every '
              + esc(OPP) + ' spread in this scenario.</p>'));
      }, function (err) {
        showMissing('tl-drill-out', decodeMsg(err), decodeKind(err));
      });
  }

  // ---- mechanism (breakpoints) ----
  function renderTableSpec(t) {
    var head = '<tr>' + (t.columns || []).map(function (c) {
      return '<th>' + esc(c) + '</th>';
    }).join('') + '</tr>';
    var body = (t.rows || []).map(function (r) {
      return '<tr>' + r.map(function (v) {
        return '<td>' + esc(v) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<h4>' + esc(t.title || '') + '</h4>'
      + (t.note ? '<p class="tl-note">' + esc(t.note) + '</p>' : '')
      + '<div class="tl-scroll"><table class="tl">' + head + body
      + '</table></div>';
  }
  // The breakpoint layer keeps its KEY names fixed across opponents so one
  // renderer reads every file: "lick_*", "body_slam_*" and "power_whip_*"
  // name the fast, first-charged and second-charged SLOTS, not those moves.
  // The move actually in each slot comes from meta.move_slots.
  function prettyMove(id) {
    if (!id) return '';
    return String(id).split('_').map(function (w) {
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    }).join(' ');
  }
  // Move-slot names come from the blob. When a slot is missing the label
  // says so IN PLACE OF a name -- an earlier fallback substituted the
  // moves the key names were coined for, which on another opponent would
  // have been a made-up number's twin: a confident wrong word with
  // nothing marking it.
  function slotNames() {
    var ms = ((D.breakpoints || {}).meta || {}).move_slots || {};
    function slot(key) {
      return prettyMove(ms[key])
        || '[move slot "' + key + '" missing from breakpoints.meta]';
    }
    return { fast: slot('fast'), c1: slot('charged_1'),
             c2: slot('charged_2') };
  }
  // ---- the FOCAL move slot: the same device, on the other side ----
  // The closed-form layer classifies exactly ONE focal move -- the
  // "headline" move whose damage tier the cliff / frontier / scatter
  // colourings and all the breakpoint prose are about. WHICH move that is
  // is read from the blob, never spelled here: it is the single entry in
  // the focal offense table carrying the per-spread tier array. If the
  // breakpoint layer is absent altogether, the embedded grids' own
  // focal_fast stands in (the layer is built for that move). If neither
  // decides it, the label SAYS SO in place of a name -- the same rule
  // slotNames() follows, and for the same reason.
  //
  // MISSING TL_DATA FIELD: scripts/joint_iv_breakpoints.py already knows
  // this move as HEADLINE (+ its configurable HA abbreviation) but does
  // not emit either. A `meta.headline_move` / `meta.headline_abbr` pair
  // beside the existing `meta.move_slots` would make both reads direct
  // and would carry a pair's custom abbreviation, which the derivation
  // below cannot see.
  var _focalMoveId;
  function focalMoveId() {
    if (_focalMoveId !== undefined) return _focalMoveId;
    var mv = ((D.breakpoints || {}).thievul_offense || {}).moves || {};
    var hits = Object.keys(mv).filter(function (k) {
      return mv[k] && mv[k].tier_vs_rank1_licki_by_spread;
    });
    if (hits.length !== 1) {
      var seen = {}, g = META.grids || {};
      Object.keys(g).forEach(function (k) {
        if (g[k] && g[k].focal_fast) seen[g[k].focal_fast] = 1;
      });
      hits = Object.keys(seen);
    }
    _focalMoveId = (hits.length === 1) ? hits[0] : null;
    return _focalMoveId;
  }
  function focalMove() {
    return prettyMove(focalMoveId())
      || '[focal breakpoint move missing from breakpoints/meta.grids]';
  }
  // Its abbreviation, derived the way the analysis layer's own default is
  // (initials of the move id's words), so the two agree by construction.
  function focalMoveAbbr() {
    var id = focalMoveId();
    if (!id) return '[focal move missing]';
    return String(id).split('_').map(function (w) {
      return w.charAt(0).toUpperCase();
    }).join('');
  }
  // Spread-summary rows as produced by the breakpoint layer (claims /
  // named_spreads entries share one shape).
  function spreadCols() {
    var s = slotNames();
    var fm = focalMove();
    return [
      ['label', 'build'], ['ivs', 'IVs'], ['rank', 'rank (stat product)'],
      ['level', 'level'], ['cp', 'CP'], ['atk', 'atk'], ['def', 'def'],
      ['hp', 'hp'],
      ['sp_dmg_vs_rank1_licki', fm + ' dmg vs rank-1 ' + OPP],
      ['sp_ge_hi_frac.all', fm + ' tier coverage (all 4096)'],
      ['sp_ge_hi_frac.top512', fm + ' tier coverage (top 512)'],
      ['body_slam_dmg_from_rank1_licki', s.c1 + ' taken'],
      ['body_slams_to_ko', s.c1 + ' hits to KO'],
      ['hp_margin_over_prev_bs_tier', 'HP over prev ' + s.c1 + ' tier'],
      ['power_whips_to_ko', s.c2 + ' hits to KO'],
      ['lick_dmg_from_rank1_licki', s.fast + ' taken']
    ];
  }
  function dig(o, path) {
    var parts = path.split('.');
    var cur = o;
    for (var i = 0; i < parts.length; i++) {
      if (cur === null || cur === undefined) return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }
  function cellText(v) {
    if (v === null || v === undefined) return '-';
    if (Array.isArray(v)) return v.join('/');
    if (typeof v === 'boolean') return v ? 'yes' : 'no';
    return String(v);
  }
  function spreadTable(rows, title, note) {
    if (!rows || !rows.length) return '';
    var cols = spreadCols().filter(function (c) {
      // An all-dashes column is noise; drop it rather than ship it.
      return rows.some(function (r) {
        var v = dig(r, c[0]);
        return v !== undefined && v !== null && v !== '';
      });
    });
    var head = '<tr>' + cols.map(function (c) {
      return '<th>' + esc(c[1]) + '</th>';
    }).join('') + '</tr>';
    var body = rows.map(function (r) {
      return '<tr>' + cols.map(function (c) {
        return '<td>' + esc(cellText(dig(r, c[0]))) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return (title ? '<h4>' + esc(title) + '</h4>' : '')
      + (note ? '<p class="tl-note">' + esc(note) + '</p>' : '')
      + '<div class="tl-scroll"><table class="tl">' + head + body
      + '</table></div>';
  }
  function kvTable(obj, keys) {
    var rows = keys.filter(function (k) {
      return dig(obj, k[0]) !== undefined;
    }).map(function (k) {
      return '<tr><td>' + esc(k[1]) + '</td><td>'
        + esc(cellText(dig(obj, k[0]))) + '</td></tr>';
    }).join('');
    return rows
      ? '<div class="tl-scroll"><table class="tl">' + rows + '</table></div>'
      : '';
  }

  // Generic renderer for the breakpoint layer's `answers` block: nested
  // objects become nested tables, keyed by the JSON key itself. Nothing is
  // relabeled or reinterpreted -- the page shows what A2 computed.
  function objListTable(list) {
    var cols = [];
    list.forEach(function (r) {
      Object.keys(r).forEach(function (k) {
        if (cols.indexOf(k) < 0) cols.push(k);
      });
    });
    return '<div class="tl-scroll"><table class="tl"><tr>'
      + cols.map(function (c) {
        return '<th>' + esc(answerLabel(c)) + '</th>';
      }).join('') + '</tr>'
      + list.map(function (r) {
        return '<tr>' + cols.map(function (c) {
          return '<td>' + esc(cellText(r[c])) + '</td>';
        }).join('') + '</tr>';
      }).join('') + '</table></div>';
  }
  // A few keys in the breakpoint layer are CONTINUOUS cutoffs rather than
  // stats any real spread has; the generic renderer would otherwise paint
  // them under a name that reads like a realized value.
  var ANSWER_LABELS = {
    // A 30-word parenthetical inside a two-column cell is unreadable; the
    // caveat it carried is the "is constant" row directly above it.
    body_slams_to_ko_stage0_value:
      'value reported at attack stage 0 (see the by-stage histogram below '
      + 'when "is constant" says no)',
    max_thievul_def_still_taking_tier_hi:
      'defense cutoff for the higher damage tier (continuous tier '
      + 'boundary, NOT a defense any real spread has)',
    min_thievul_atk_for_hi_tier:
      'attack needed for the higher damage tier (continuous tier '
      + 'boundary, NOT a realized spread stat)',
    // The shipped blob spells this one with a "_vs_every_<opp>" tail, so
    // the exact-key lookup above never fired and the unattainable cutoff
    // printed bare beside a sibling that DID carry the caveat.
    min_thievul_atk_for_hi_tier_vs_every_licki:
      'attack needed for the higher damage tier against every opponent '
      + '(continuous tier boundary, NOT a realized spread stat)'
  };
  // The breakpoint layer's key names are frozen SLOT spellings for the
  // opponent ("lickitung"/"licki") and focal ("thievul") halves; the
  // SPECIES they name is whatever this dataset analyzes, so they are
  // relabeled here rather than leaking a literal key like
  // `max_lickitung_cmp_atk` into the page. The headline move's own keys
  // are already spelled from the move (`<move>_tier_boundary`), so they
  // need no substitution -- only underscores become spaces.
  function ivify(s) {
    // 61515 / 615 are IV triples written without separators. JS \b does
    // NOT match between a digit and an underscore, so split on underscores
    // FIRST -- otherwise "615_vs_61515" never matched at all.
    return String(s).split('_').map(function (part) {
      if (/^\d{6}$/.test(part)) {
        return +part.slice(0, 2) + '/' + +part.slice(2, 4) + '/'
          + +part.slice(4, 6);
      }
      if (/^\d{5}$/.test(part)) {
        return +part.slice(0, 1) + '/' + +part.slice(1, 3) + '/'
          + +part.slice(3, 5);
      }
      if (part === '615') return '6/15/5';
      return part;
    }).join('_');
  }
  function answerLabel(k) {
    if (ANSWER_LABELS[k]) return ANSWER_LABELS[k];
    var s = ivify(String(k)).replace(/_/g, ' ')
      .replace(/\blickitung\b/gi, OPP)
      .replace(/\blicki\b/gi, OPP)
      .replace(/\bthievul\b/gi, FOCAL);
    // The key names the SLOT ("power whip" = second charged move), not the
    // move: on this dataset that slot may be something else entirely.
    // Species substitution runs first, so "lick" here can only be the
    // fast-move slot, never the tail of an opponent species name.
    var sn = slotNames();
    s = s.replace(/\bpower whips\b/gi, sn.c2 + ' hits')
      .replace(/\bpower whip\b/gi, sn.c2)
      .replace(/\bbody slams\b/gi, sn.c1 + ' hits')
      .replace(/\bbody slam\b/gi, sn.c1)
      .replace(/\blicks\b/gi, sn.fast + ' hits')
      .replace(/\blick\b/gi, sn.fast)
      .replace(/\bto ko\b/g, 'to KO')
      // The blob's key names spell comparisons out ("n_..._ge_tier_hi");
      // rendered raw they read as a typo ("taking ge tier hi").
      .replace(/\bge\b/g, 'at or above')
      .replace(/\ble\b/g, 'at or below')
      .replace(/\btier hi\b/g, 'the high tier')
      .replace(/\bstage0\b/g, 'stage 0')
      // raw key fragments that read as typos in prose (2026-08-19
      // review): the headline-move abbreviation, compaction shorthands
      .replace(new RegExp('\\b' + focalMoveAbbr().toLowerCase()
        + '\\b', 'g'), focalMove().toLowerCase())
      .replace(/\bsta15\b/g, 'sta-15')
      .replace(/\btop512\b/g, 'top-512')
      .replace(/\bfrac\b/g, 'fraction');
    return s;
  }
  // A STAGE MAP is {attack stage: value} -- keys 0,-1,-2,... Its values are
  // damages or hit counts, NOT counts of anything, so it must never be
  // totalled or labelled "spreads".
  function isStageMap(v, key) {
    if (!v || typeof v !== 'object' || Array.isArray(v)) return false;
    var keys = Object.keys(v);
    if (!keys.length) return false;
    var anyNeg = false;
    for (var i = 0; i < keys.length; i++) {
      if (!/^-?\d+$/.test(keys[i])) return false;
      if (+keys[i] > 0) return false;          // stages are 0 or negative
      if (+keys[i] < 0) anyNeg = true;
    }
    return anyNeg || /stage/i.test(String(key || ''));
  }
  function stageMapHtml(label, v, key, owner) {
    var subject = cleanSubject(label)
      + (owner ? ' for ' + owner : '');
    var rows = Object.keys(v).sort(function (a, b) { return b - a; })
      .map(function (k) {
        var val = v[k];
        return '<tr><td>' + esc(k) + '</td><td>'
          + esc(typeof val === 'object' ? JSON.stringify(val) : val)
          + '</td></tr>';
      }).join('');
    return '<p class="tl-note"><strong>' + esc(subject) + '</strong> by '
      + esc(OPP) + ' attack stage (no shields or healing; one value per '
      + 'stage, not a distribution).</p>'
      + '<div class="tl-scroll"><table class="tl"><tr>'
      + '<th>' + esc(OPP) + ' attack stage</th><th>value</th></tr>'
      + rows + '</table></div>';
  }
  // A histogram is {bucket: count} with numeric keys and numeric values.
  function isHistogram(v) {
    if (!v || typeof v !== 'object' || Array.isArray(v)) return false;
    var keys = Object.keys(v);
    if (!keys.length) return false;
    for (var i = 0; i < keys.length; i++) {
      if (!/^-?\d+$/.test(keys[i])) return false;
      if (typeof v[keys[i]] !== 'number') return false;
    }
    return true;
  }
  // "never actually thrown" adjacency, straight from the probe block.
  function neverThrownNote(moveName) {
    var rc = ((D.breakpoints || {}).verification || {})
      .resisted_charged_sim_checks || [];
    for (var i = 0; i < rc.length; i++) {
      if (rc[i].thrown_with_default_moveset === false
          && prettyMove(rc[i].move) === moveName) {
        return ' Note: the engine never throws ' + moveName + ' when the '
          + OPP + ' runs its own default charged pair (see the '
          + 'resisted-charged probe below), so '
          + 'this is a bulk reference rather than damage you routinely '
          + 'take.';
      }
    }
    return '';
  }
  // A one-bucket histogram is a SENTENCE, not a table.
  function cleanSubject(label) {
    return String(label).replace(/\s*histogram\s*/ig, ' ')
      .replace(/\s*stage 0\s*/i, ' ')
      // The callers append "by <opponent> attack stage" themselves, so a
      // label that already carries the phrase -- in either the bare "by
      // stage" form or the key-derived "by <opponent> atk stage" form --
      // doubled it.
      .replace(/\s*\bby stage\b\s*/ig, ' ')
      .replace(new RegExp('\\s*by (?:' + OPP + '|' + FOCAL
        + ') atk stage\\s*', 'ig'), ' ')
      .replace(/\s+/g, ' ').trim();
  }
  // What is being counted? A key naming PAIRS counts focal x opponent
  // matchups (4096^2), not spreads (4096). Getting this wrong turned a
  // pair total into "16,777,216 <focal> spreads".
  function countedUnit(key) {
    return /pair/i.test(String(key || ''))
      ? FOCAL + ' x ' + OPP + ' matchup pairs'
      : FOCAL + ' spreads';
  }
  function histogramHtml(label, v, key) {
    var keys = Object.keys(v);
    var total = 0;
    keys.forEach(function (k) { total += v[k]; });
    // "Shadow Ball hits to KO stage 0 histogram" -> subject "Shadow Ball",
    // measure "hits to KO", so the sentence reads like a sentence. When
    // there is no "hits ..." tail the subject is used ONCE, not twice.
    var subject = cleanSubject(label);
    var parts = subject.match(/^(.*?)\s+(hits? .*)$/);
    var moveName = parts ? parts[1] : '';
    var measure = parts ? parts[2] : subject;
    var note = neverThrownNote(moveName || subject.split(' ')[0]);
    var unit = countedUnit(key);
    var atStage = /stage\s*0/i.test(String(key || label))
      ? 'attack stage 0, ' : '';
    if (keys.length === 1) {
      return '<p class="tl-note"><strong>'
        + esc(moveName ? moveName + ': ' : '')
        + esc(keys[0]) + ' ' + esc(measure) + '</strong> - identical for '
        + 'all ' + commas(total) + ' ' + esc(unit) + ' ('
        + atStage + 'additive model).' + esc(note) + '</p>';
    }
    var rows = keys.map(function (k) {
      return '<tr><td>' + esc(k) + '</td><td>' + commas(v[k]) + '</td></tr>';
    }).join('');
    return '<p class="tl-note"><strong>'
      + esc(moveName ? moveName + ' ' : '') + esc(measure)
      + '</strong>, over all ' + commas(total) + ' ' + esc(unit)
      + ' (' + atStage + 'additive model):' + esc(note) + '</p>'
      + '<div class="tl-scroll"><table class="tl"><tr><th>value</th>'
      + '<th>' + esc(unit) + '</th></tr>' + rows
      + '</table></div>';
  }
  function answersHtml(o, depth) {
    var rows = [], sub = [];
    // A block carrying an `order` list is a PER-BUILD comparison: its
    // sibling arrays are positional, one entry per named build. Rendered
    // as "7, 6" with the key hidden in a trailing "order" row, the reader
    // had to scroll to the bottom and mentally zip every row. Given the
    // names, it becomes a real table with named columns -- the same
    // treatment the by-stage block already gets.
    var orderNames = (Array.isArray(o.order) && o.order.length > 1)
      ? o.order.map(function (x) { return ivify(String(x)); }) : null;
    // n_spreads_taking_{1,2}_lick_* are FIXED 1-damage / 2-damage buckets
    // written for the pair the schema was coined on. When the layer ships
    // a histogram
    // instead, those buckets read 0 and would be misleading -- so they are
    // relabeled (never dropped) and the histogram is named as the answer.
    var hasHist = !!o.fast_move_dmg_histogram_vs_rank1;
    var sn = slotNames();
    Object.keys(o).forEach(function (k) {
      var v = o[k];
      var label = answerLabel(k);
      // The order list becomes the column header, so it is not also a row.
      if (orderNames && k === 'order') return;
      if (hasHist && /^n_spreads_taking_\d_lick_vs_rank1$/.test(k)) {
        label = label + ' (a fixed 1/2-damage bucket carried over from the '
          + 'original schema - it does not apply to ' + sn.fast + ', see '
          + 'the histogram below)';
      }
      // The layer's own note explains those keys using the ORIGINAL
      // schema's move name. Quoting it verbatim on a page whose fast move
      // is something else reads as a mistake, so the page states the same
      // fact naming both the slot and the move actually in it.
      if (k === 'fast_move_dmg_histogram_note') {
        v = 'The n_spreads_taking_1/2_<fast-move slot> keys above are '
          + 'fixed 1-damage and 2-damage buckets from the original schema. '
          + 'The fast-move slot here is ' + sn.fast + ', which does not '
          + 'deal those amounts, so both read 0 - use the histogram '
          + 'instead.';
      }
      if (k === 'fast_move_dmg_histogram_vs_rank1') {
        // histogramHtml appends "over all N <focal> spreads" itself, so
        // the label must not also say "by number of spreads".
        label = sn.fast + ' damage taken from the rank-1 ' + OPP;
      }
      if (v === null || typeof v !== 'object') {
        rows.push([label, cellText(v)]);
      } else if (Array.isArray(v)) {
        if (v.length && typeof v[0] === 'object') {
          sub.push('<h5>' + esc(label) + '</h5>' + objListTable(v));
        } else if (orderNames && v.length === orderNames.length) {
          rows.push([label, v.map(function (x) { return String(x); })]);
        } else if (v.length <= 16) {
          rows.push([label, v.join(', ')]);
        } else {
          rows.push([label, v.length + ' values']);
        }
      } else if (isStageMap(v, k)
                 && !Object.keys(v).some(function (kk) {
                   return v[kk] && typeof v[kk] === 'object';
                 })) {
        sub.push(stageMapHtml(label, v, k, o.ivs
          ? (Array.isArray(o.ivs) ? o.ivs.join('/') : String(o.ivs))
          : ''));
      } else if (isStageMap(v, k) && Object.keys(v).some(function (kk) {
        return Array.isArray(v[kk]);
      })) {
        // stage -> ARRAY of per-build values. The array is positional, so
        // it is labelled from the sibling `order` list; raw indices 0/1
        // are unreadable.
        var names = (o.order && Array.isArray(o.order)) ? o.order : null;
        sub.push('<h5>' + esc(cleanSubject(label)) + ' by ' + esc(OPP)
          + ' attack stage, per build'
          + (names ? ' (' + esc(names.map(function (x) {
            return ivify(String(x));
          }).join(' vs ')) + ')' : '') + '</h5>'
          + (names ? '' : '<p class="tl-note">Rows are positional and this '
            + 'block ships no name list, so they are shown by index.</p>')
          + '<div class="tl-scroll"><table class="tl"><tr><th>' + esc(OPP)
          + ' attack stage</th>'
          + (names || (v[Object.keys(v)[0]] || []).map(function (_, ix) {
            return 'index ' + ix;
          })).map(function (nm) {
            return '<th>' + esc(ivify(String(nm))) + '</th>';
          }).join('') + '</tr>'
          + Object.keys(v).sort(function (a, b) { return b - a; })
            .map(function (st) {
              return '<tr><td>' + esc(st) + '</td>'
                + (v[st] || []).map(function (cell) {
                  return '<td>' + esc(cellText(cell)) + '</td>';
                }).join('') + '</tr>';
            }).join('') + '</table></div>');
      } else if (isStageMap(v, k)) {
        // stage -> histogram: label each stage, then render its histogram
        sub.push('<h5>' + esc(cleanSubject(label)) + ' by ' + esc(OPP)
          + ' attack stage</h5>'
          + Object.keys(v).sort(function (a, b) { return b - a; })
            .map(function (st) {
              return '<p class="tl-note">' + esc(OPP) + ' attack stage '
                + esc(st) + ':</p>'
                + (isHistogram(v[st])
                  ? histogramHtml(cleanSubject(label), v[st], k)
                  : answersHtml(v[st], depth + 1));
            }).join(''));
      } else if (isHistogram(v)) {
        sub.push(histogramHtml(label, v, k));
      } else if (depth >= 3) {
        rows.push([label, JSON.stringify(v).slice(0, 300)]);
      } else {
        sub.push('<h5>' + esc(label) + '</h5>' + answersHtml(v, depth + 1));
      }
    });
    var nCol = orderNames ? orderNames.length : 1;
    var tbl = rows.length
      ? '<div class="tl-scroll"><table class="tl">'
        + (orderNames
          ? '<tr><th></th>' + orderNames.map(function (nm) {
              return '<th>' + esc(nm) + '</th>';
            }).join('') + '</tr>'
          : '')
        + rows.map(function (r) {
          if (Array.isArray(r[1])) {
            return '<tr><td>' + esc(r[0]) + '</td>'
              + r[1].map(function (cell) {
                return '<td>' + esc(cell) + '</td>';
              }).join('') + '</tr>';
          }
          return '<tr><td>' + esc(r[0]) + '</td><td'
            + (nCol > 1 ? ' colspan="' + nCol + '"' : '') + '>' + esc(r[1])
            + '</td></tr>';
        }).join('') + '</table></div>'
      : '';
    return tbl + sub.join('');
  }

  // Stat boundaries must never be shown rounded: 122.1 is not an attack
  // any spread has. Cross-check the emitted "value" fields against the
  // file's OWN atk_values list and say so when they disagree.
  // The table shows the ATTAINABLE value, with the blob's rounded
  // boundary named as such beside it -- printing 122.1 as "lowest attack
  // that clears" put a number on the page that no spread can have, one
  // line above a note saying exactly that.
  function attainableBpk(bpk) {
    var vals = null;
    try { vals = D.breakpoints.spread_index.thievul.atk_values; }
    catch (e) { vals = null; }
    if (!vals || !vals.length) return bpk;
    var need = bpk.min_thievul_atk_for_hi_tier;
    if (typeof need !== 'number') return bpk;
    // Order-independent (the list happens to be sorted; nothing promises
    // it): hi = smallest value at or above the cutoff, lo = largest below.
    var lo = null, hi = null;
    for (var i = 0; i < vals.length; i++) {
      if (vals[i] >= need) { if (hi === null || vals[i] < hi) hi = vals[i]; }
      else if (lo === null || vals[i] > lo) { lo = vals[i]; }
    }
    var out = {}, k;
    for (k in bpk) {
      if (Object.prototype.hasOwnProperty.call(bpk, k)) out[k] = bpk[k];
    }
    function sub(key, attain) {
      var v = bpk[key];
      if (typeof v !== 'number' || attain === null) return;
      if (vals.indexOf(v) >= 0) return;
      out[key] = attain + ' (attainable; the blob reports the rounded '
        + 'boundary ' + v + ', which no ' + FOCAL + ' spread has)';
    }
    sub('lowest_thievul_atk_value_clearing', hi);
    sub('highest_thievul_atk_value_failing', lo);
    return out;
  }
  function bpAttainNote(bpk) {
    var vals = null;
    try { vals = D.breakpoints.spread_index.thievul.atk_values; }
    catch (e) { vals = null; }
    if (!vals || !vals.length) return '';
    var out = [];
    [['lowest_thievul_atk_value_clearing', 'lowest attack that clears'],
     ['highest_thievul_atk_value_failing', 'highest attack that fails']]
      .forEach(function (pair) {
        var v = bpk[pair[0]];
        if (typeof v !== 'number' || vals.indexOf(v) >= 0) return;
        var need = bpk.min_thievul_atk_for_hi_tier;
        var nearest = null;
        for (var i = 0; i < vals.length; i++) {
          if (typeof need === 'number' && vals[i] >= need) {
            nearest = vals[i];
            break;
          }
        }
        out.push('"' + pair[1] + '" is reported as ' + v
          + ', which is NOT one of the ' + vals.length + ' attack values '
          + FOCAL + ' spreads can actually have (it is a rounded boundary)'
          + (nearest !== null ? '; the lowest attainable attack at or above '
            + 'the ' + need + ' cutoff is ' + nearest : ''));
      });
    return out.length
      ? '<div class="tl-missing"><strong>Rounded stat boundary.</strong> '
        + esc(out.join('. ')) + '.</div>'
      : '';
  }
  function renderMechanism() {
    if (!HAS_BP) {
      showMissing('tl-mech',
        'breakpoints.json (the closed-form damage/bulk layer) is not '
        + 'embedded in this page, so the mechanism tables and the explicit '
        + 'read-outs on the "6/15/5" and "15 HP" claims are unavailable.');
      return;
    }
    var bp = D.breakpoints;
    var P = [];
    if (bp.meta && bp.meta.model) {
      P.push('<div class="tl-rail">' + esc(bp.meta.model) + '</div>');
    }
    if (bp.survival && bp.survival.model) {
      P.push('<div class="tl-rail">Survival model: '
        + esc(bp.survival.model) + '</div>');
    }

    // -- the breakpoint layer's own answers block --
    if (bp.answers) {
      P.push('<h3>Closed-form answers</h3>'
        + '<p class="tl-note">Rendered verbatim from breakpoints.json '
        + '"answers" - key names are the analysis script\'s own.</p>'
        + answersHtml(bp.answers, 0));
    }

    // -- claim A: a named spread vs the headline-move breakpoint --
    var A = (bp.claims || {}).a_615_best_for_sp_bp;
    if (A) {
      P.push('<div class="tl-verdict"><div class="tl-verdict-claim">'
        + 'What about the 6/15/5 spread?</div>'
        + '<div class="tl-verdict-detail">' + esc(A.claim)
        + (/\bLicki\b/.test(String(A.claim || ''))
          ? ' <em>(quoted verbatim; "Licki" here means ' + esc(OPP)
            + ', the species this page analyzes)</em>' : '')
        + '</div>'
        + '<div class="tl-verdict-call">Clears the ' + esc(focalMove())
        + ' breakpoint '
        + 'vs the rank-1 ' + esc(OPP) + ': '
        + cellText(A.clears_bp_vs_rank1_licki)
        + '. At MAXIMUM ' + esc(focalMove()) + ' coverage (all-4096 cohort): '
        + cellText(dig(A, 'is_615_at_max_coverage.all'))
        + '; (top-512 cohort): '
        + cellText(dig(A, 'is_615_at_max_coverage.top512')) + '.</div>'
        + '<div class="tl-verdict-detail">These are read-outs of the '
        + 'closed-form damage layer only (no shields, energy or timing); '
        + 'the simulated grids above are what decide fights.</div></div>');
      P.push(kvTable(A, [
        ['spread.ivs', '6/15/5 IVs'],
        ['spread.rank', 'stat-product rank'],
        ['spread.level', 'level'], ['spread.cp', 'CP'],
        ['spread.atk', 'atk'], ['spread.def', 'def'], ['spread.hp', 'hp'],
        ['spread.sp_dmg_vs_rank1_licki',
         focalMoveAbbr() + ' damage vs rank-1 ' + OPP],
        ['spread.sp_ge_hi_frac.all',
         'fraction of all 4096 ' + OPP + ' it reaches the higher '
         + focalMoveAbbr() + ' tier on'],
        ['spread.sp_ge_hi_frac.top512', 'same, top-512 ' + OPP + ' cohort'],
        ['max_ge_hi_frac.all', 'best achievable fraction (all 4096)'],
        ['n_spreads_at_max_coverage.all',
         FOCAL + ' spreads at that best fraction (all 4096)'],
        ['n_spreads_strictly_better_than_615.all',
         FOCAL + ' spreads strictly better than 6/15/5 (all 4096)'],
        ['n_spreads_tied_with_615.all', 'spreads tied with 6/15/5 (all 4096)'],
        ['coverage_rank_of_615.all', 'coverage rank of 6/15/5 (all 4096)'],
        ['n_spreads_strictly_better_than_615.rank1',
         'spreads strictly better than 6/15/5 (rank-1 ' + OPP + ' only)'],
        ['best_iv_rank_at_max_coverage',
         'best stat-product rank among max-coverage spreads'],
        ['best_stat_product_spread_at_max_coverage.ivs',
         'that spread\'s IVs']
      ]));
      P.push(spreadTable(A.max_coverage_examples,
        'Example spreads at maximum ' + focalMove() + ' coverage',
        'From breakpoints.json claims.a_615_best_for_sp_bp.'
        + 'max_coverage_examples.'));
    }

    // -- claim B: "do you not want 15 hp" --
    var B = (bp.claims || {}).b_15_hp;
    if (B) {
      P.push('<div class="tl-verdict"><div class="tl-verdict-claim">'
        + 'What about 15 HP?</div>'
        + '<div class="tl-verdict-detail">' + esc(B.claim) + '</div>'
        + '<div class="tl-verdict-call">'
        + cellText(B.n_sta15_clearing_sp_bp_vs_rank1) + ' of '
        + cellText(B.n_sta15_spreads) + ' sta-15 spreads clear the '
        + esc(focalMove()) + ' breakpoint vs the rank-1 ' + esc(OPP)
        + '. The best sta-15 spread by stat product is rank '
        + cellText(B.best_rank_sta15)
        + ', and it does not clear the breakpoint; the best sta-15 spread '
        + 'that DOES clear it is a different spread, at stat-product rank '
        + cellText(B.best_rank_sta15_clearing_bp)
        + ' (both are in the two tables below).</div></div>');
      var dc = B.direct_comparison_6_15_5_vs_6_15_15;
      if (dc) {
        P.push(spreadTable(Object.keys(dc).map(function (k) {
          var r = dc[k];
          if (r && !r.label) r.label = k;
          return r;
        }), 'Direct comparison: 6/15/5 vs 6/15/15', ''));
      }
      P.push(spreadTable(B.best_sta15_by_iv_rank,
        'Best sta-15 spreads by stat-product rank', ''));
      P.push(spreadTable(B.best_sta15_clearing_bp_by_iv_rank,
        'Best sta-15 spreads that clear the ' + focalMoveAbbr()
        + ' breakpoint', ''));
      if (B.sta15_max_coverage_spread) {
        P.push(spreadTable([B.sta15_max_coverage_spread],
          'Best sta-15 spread by ' + focalMove() + ' coverage', ''));
      }
    }

    // -- per-move breakpoint mechanics --
    var mv = dig(bp, 'thievul_offense.moves') || {};
    // Focal moves the producer PROVED never fly in this matchup (the
    // stage probe's debuff_unreachable record) get the same never-thrown
    // disclosure the opponent's unused moves already get -- a tier table
    // with no caveat reads as damage you actually deal (2026-08-19
    // review).
    var neverThrown = {};
    Object.keys(dig(bp, 'verification') || {}).forEach(function (k) {
      var m2 = /^(.*)_stage_check$/.exec(k);
      if (m2 && (dig(bp, 'verification')[k] || {}).debuff_unreachable) {
        neverThrown[m2[1].toUpperCase()] = true;
      }
    });
    Object.keys(mv).forEach(function (name) {
      var m = mv[name];
      var rows = (m.tier_boundaries || []).map(function (t) {
        return '<tr><td>' + esc(t.tier_from) + ' -> ' + esc(t.tier_to)
          + '</td><td>' + esc(t.min_atk_over_def) + '</td></tr>';
      }).join('');
      var bpk = m.breakpoint_vs_rank1_licki;
      P.push('<h4>' + esc(prettyMove(name)) + ' (' + esc(FOCAL) + ' -> '
        + esc(dig(bp, 'thievul_offense.defender') || OPP) + ')</h4>'
        + (neverThrown[name.toUpperCase()]
          ? '<p class="tl-note"><strong>Note:</strong> the engine never '
            + 'threw ' + esc(prettyMove(name)) + ' in any probe fight of '
            + 'this matchup (see the verification block), so these tiers '
            + 'are a reference, not damage you routinely deal here -- '
            + 'and they are why the bait and no-bait grids can be '
            + 'byte-identical.</p>' : '')
        + '<p class="tl-note">' + esc(m.damage_identity || '') + ', K = '
        + esc(m.damage_constant_K) + '. Damage tiers reachable: '
        + esc((m.tiers || []).join(', ')) + '.</p>'
        + (rows
          ? '<div class="tl-scroll"><table class="tl"><tr><th>tier step</th>'
            + '<th>min atk/def</th></tr>' + rows + '</table></div>' : '')
        + (bpk ? bpAttainNote(bpk) : '')
        + (bpk ? kvTable(attainableBpk(bpk), [
            ['licki_ivs', 'rank-1 ' + OPP + ' IVs'],
            ['licki_def', 'its defense'],
            ['base_tier', 'damage below the breakpoint'],
            ['hi_tier', 'damage above the breakpoint'],
            ['min_thievul_atk_for_hi_tier', 'attack needed for the high tier'],
            ['lowest_thievul_atk_value_clearing', 'lowest attack that clears'],
            ['highest_thievul_atk_value_failing', 'highest attack that fails'],
            ['n_spreads_clearing', FOCAL + ' spreads that clear it']
          ]) : ''));
    });

    // -- survival for named + user spreads --
    var surv = dig(bp, 'survival.per_thievul_spread_vs_rank1_licki_stage0');
    if (surv) {
      var sn = slotNames();
      var picks = namedBuilds().concat(
        state.user.filter(function (u) { return u.side === 'thievul'; })
          .map(function (u) { return { label: 'YOURS: ' + u.label,
                                       idx: u.idx }; }));
      var srows = picks.map(function (p) {
        return '<tr><td>' + esc(p.label) + '</td><td>'
          + esc(ivStr('thievul', p.idx)) + '</td><td>' + (p.idx + 1)
          + '</td><td>' + esc(surv.hp[p.idx]) + '</td><td>'
          + esc(surv.body_slam_dmg[p.idx]) + '</td><td>'
          + esc(surv.body_slams_to_ko[p.idx]) + '</td><td>'
          + esc(surv.hp_margin_over_prev_bs_tier[p.idx]) + '</td><td>'
          + esc(surv.power_whip_dmg[p.idx]) + '</td><td>'
          + esc(surv.power_whips_to_ko[p.idx]) + '</td><td>'
          + esc(surv.lick_dmg[p.idx]) + '</td></tr>';
      }).join('');
      // If the layer's own probe says the engine never throws one of these
      // moves with the default moveset, say it HERE, next to its columns.
      var rcv = ((bp.verification || {}).resisted_charged_sim_checks || [])
        .filter(function (r) { return r.thrown_with_default_moveset === false; });
      var rcNote = rcv.length
        ? ' ' + rcv.map(function (r) { return prettyMove(r.move); })
            .join(' and ') + ' is never thrown by the engine when the '
          + OPP + ' runs its own default charged pair (see the '
          + 'resisted-charged probe below), so '
          + 'those columns describe damage you will rarely actually take.'
        : '';
      P.push('<h4>Bulk vs the rank-1 ' + esc(OPP) + ' (stage 0)</h4>'
        + '<p class="tl-note">Named builds plus any spread you added under '
        + '"Your IVs". Additive model, no shields or healing.'
        + esc(rcNote) + '</p>'
        + '<div class="tl-scroll"><table class="tl"><tr><th>build</th>'
        + '<th>IVs</th><th>rank (stat product)</th><th>hp</th><th>'
        + esc(sn.c1)
        + ' dmg</th><th>' + esc(sn.c1) + ' to KO</th><th>hp over prev '
        + esc(sn.c1) + ' tier</th><th>' + esc(sn.c2) + ' dmg</th><th>'
        + esc(sn.c2) + ' to KO</th><th>' + esc(sn.fast) + ' dmg</th></tr>'
        + srows + '</table></div>');
    }

    // -- CMP --
    if (bp.cmp) {
      P.push('<h4>CMP (charge move priority)</h4>'
        + '<p class="tl-note">' + esc(bp.cmp.definition || '') + '</p>'
        + '<div class="tl-verdict"><div class="tl-verdict-call">'
        + esc(bp.cmp.verdict || '') + '</div></div>'
        + kvTable(bp.cmp, [
            ['min_thievul_cmp_atk', 'lowest ' + FOCAL + ' CMP attack'],
            ['min_thievul_spread', 'that spread'],
            ['max_lickitung_cmp_atk', 'highest ' + OPP + ' CMP attack'],
            ['max_lickitung_spread', 'that spread'],
            ['margin', 'margin']
          ]));
    }

    // -- verification --
    var ver = bp.verification;
    if (ver) {
      var fs = ver.formula_samples || [];
      var bad = fs.filter(function (r) { return r.match === false; }).length;
      var sc = ver.sim_checks || [];
      var scBad = sc.filter(function (r) { return r.match === false; }).length;
      // The attack-stage cross-check is keyed "<debuff move>_stage_check",
      // so the KEY names the focal move that lowers the opponent's attack
      // -- read it instead of spelling a move here. Its inner arrays are
      // frozen charged-slot-1 SLOT keys, relabeled from meta.move_slots
      // like everything else on the opponent's move axis.
      var stKey = Object.keys(ver).filter(function (k) {
        return /_stage_check$/.test(k);
      })[0];
      P.push('<h4>Verification (from breakpoints.json)</h4>'
        + '<p class="tl-note">Closed-form vs independent formula: '
        + (fs.length - bad) + '/' + fs.length + ' samples match. '
        + 'Closed-form vs the battle engine: ' + (sc.length - scBad) + '/'
        + sc.length + ' checks match.'
        + (stKey && ver[stKey].debuff_unreachable
          // Honest-absence branch: the producer recorded WHY the check
          // could not run; rendering the missing verdict key as "-"
          // suppressed that explanation (2026-08-19 review blocker).
          ? ' ' + esc(prettyMove(stKey.replace(/_stage_check$/, '')))
            + ' stage check: NOT TESTABLE in this matchup -- '
            + esc(ver[stKey].note || 'the debuff move was never thrown in '
              + 'any probe fight') : '')
        + (stKey && !ver[stKey].debuff_unreachable
          ? ' ' + esc(prettyMove(stKey.replace(/_stage_check$/, '')))
            + ' stage check: observed ' + esc(slotNames().c1)
            + ' damages all found in '
            + 'the closed-form stage set: '
            + cellText(ver[stKey].all_observed_in_closed_form_set)
            + '.' : '')
        + '</p>'
        + ((bad || scBad)
          ? '<div class="tl-missing"><strong>Verification mismatch.</strong> '
            + 'Some samples in breakpoints.json did not match; treat this '
            + 'section as unverified.</div>' : ''));
      // Resisted-charged probes: these record moves the engine may never
      // actually throw, which is itself a page-worthy fact.
      var rc = ver.resisted_charged_sim_checks || [];
      if (rc.length) {
        P.push('<h5>Resisted charged-move probes</h5>'
        + '<p class="tl-note">The ' + esc(OPP) + ' in this analysis '
        + 'carries its default charged pair, so a move can be on the '
        + 'moveset and still never be thrown: the engine picks by its own '
        + 'policy across all nine shield scenarios. That is what these '
        + 'probes record.</p>'
          + (ver.resisted_charged_note
            ? '<p class="tl-note">' + esc(ver.resisted_charged_note) + '</p>'
            : '')
          + '<div class="tl-scroll"><table class="tl"><tr><th>move</th>'
          + '<th>type</th><th>effectiveness vs ' + esc(FOCAL) + '</th>'
          + '<th>thrown with the default moveset?</th>'
          + '<th>damage (by stage)</th></tr>'
          + rc.map(function (r) {
            return '<tr><td>' + esc(prettyMove(r.move)) + '</td><td>'
              + esc(r.move_type || '') + '</td><td>'
              + esc(cellText(r.effectiveness_vs_thievul)) + 'x</td><td>'
              + (r.thrown_with_default_moveset === false
                ? 'NO - with the ' + esc(OPP) + ' default charged pair the '
                + 'engine never chose it, so this probe forced it'
                : cellText(r.thrown_with_default_moveset))
              + '</td><td>'
              + esc((r.sim_damages_in_order || []).join(', ')) + '</td></tr>';
          }).join('') + '</table></div>');
      }
    }

    // Optional generic blocks (assembly may append these).
    (bp.verdicts || []).forEach(function (v) {
      P.push('<div class="tl-verdict"><div class="tl-verdict-claim">'
        + esc(v.claim) + '</div><div class="tl-verdict-call">'
        + esc(v.verdict) + '</div>'
        + (v.detail ? '<div class="tl-verdict-detail">' + esc(v.detail)
          + '</div>' : '') + '</div>');
    });
    (bp.tables || []).forEach(function (t) { P.push(renderTableSpec(t)); });
    (bp.notes || []).forEach(function (n) {
      P.push('<p class="tl-note">' + esc(n) + '</p>');
    });
    P.push('<p class="tl-note">This whole section is the closed-form '
      + 'damage / bulk layer: it does NOT follow the grid, scenario or '
      + 'cohort controls, and it models no shields, energy or timing.</p>');
    setHtml('tl-mech', P.join(''));
  }

  // ---- recommendations ----
  function renderReco() {
    if (!HAS_RECO) {
      showMissing('tl-reco',
        'the recommendation blob is computed in the assembly phase (after '
        + 'the grids finish baking) and is not embedded in this page yet.');
      return;
    }
    var recoGrid = D.reco.primary_grid || null;
    var cards = (D.reco.cards || []).map(function (c) {
      var cGrid = cardGrid(c) || recoGrid;
      // The chain is already in the subtitle for these cards; printing
      // it again as a caveat is noise.
      var tie = tieText(c);
      if (tie && String(c.subtitle || '').indexOf('iebreak') >= 0) tie = '';
      return '<div class="tl-card"><h4>' + esc(expandOppShorthand(c.title || ''))
        + '</h4>'
        + (c.subtitle ? '<div class="tl-card-sub">'
          + esc(expandOppShorthand(c.subtitle)) + '</div>' : '')
        + (cGrid ? '<div class="tl-card-sub">Numbers on this card come '
          + 'from: ' + esc(gridPretty(cGrid)) + '</div>' : '')
        + (tie ? '<div class="tl-card-caveat">' + esc(tie) + '</div>' : '')
        + (spreadText(c) ? '<div class="tl-card-spread">'
          + esc(spreadText(c)) + '</div>' : '')
        + '<ul>' + (c.lines || []).map(function (l) {
          return '<li>' + esc(expandOppShorthand(l)) + '</li>';
        }).join('') + '</ul>'
        + ((c.caveats || []).length
          ? '<div class="tl-card-caveat">' + (c.caveats || []).map(function (x) {
              return esc(x);
            }).join('<br>') + '</div>' : '')
        + '</div>';
    }).join('');
    var notes = (D.reco.notes || []).map(function (n) {
      return '<p class="tl-note">' + esc(expandOppShorthand(n)) + '</p>';
    }).join('');
    setHtml('tl-reco', (cards || missingBox(
      'the recommendation blob has no cards.'))
      + '<p class="tl-note">These cards are computed once, in the assembly '
      + 'step, and do NOT follow the grid / scenario / cohort controls: '
      + 'each card states the grid its numbers come from.</p>' + notes);
  }

  // ---- anti-focal (opponent-axis) denial sections ----
  // Every number here comes from TL_DATA.licki_denial, which
  // scripts/joint_iv_denial.py recomputes from the same baked grids
  // and cross-checks against the research run. Nothing is authored.
  function denialPct(v, n) { return fmt(100 * v / n, 1) + '%'; }
  // The breakpoint-clearing population key carries its own count
  // (bp2992 for Thievul, bp435 for Wigglytuff, ...). Module scope: it
  // is read by the verdict, the wall table, the ranked table AND
  // renderYourDenial -- a function-local var crashed the last of those
  // the first time a reader added opponent-side spreads (2026-08-20).
  function denBpKey() {
    var pops = dig(D, 'licki_denial.meta.populations') || {};
    return Object.keys(pops).filter(function (k) {
      return k !== 'all4096' && k !== 'top512';
    })[0] || 'bp2992';
  }
  function renderDenial() {
    var host = $('tl-denial');
    if (!host) return;
    var DEN = D.licki_denial;
    if (!DEN) {
      // The builder omits the section entirely when the input is absent
      // (an archived page must not carry an eternal placeholder), so if
      // the host somehow exists there is nothing honest to draw.
      setHtml('tl-denial', '');
      return;
    }
    var m = DEN.meta || {}, cf = DEN.closed_form || {};
    // closed_form is keyed by the two MOVE names it models (the focal
    // headline move and the opponent's fast move), so the keys are
    // pair-specific. Pick them out by the field each block carries rather
    // than by spelling a move: the wall block defines a wall_condition,
    // the attack-route block a top_tier_condition.
    var sp = {}, ro = {};
    Object.keys(cf).forEach(function (k) {
      var e = cf[k];
      if (!e || typeof e !== 'object') return;
      if (e.wall_condition !== undefined) sp = e;
      else if (e.top_tier_condition !== undefined) ro = e;
    });
    var pops = m.populations || {};
    var P = [];

    P.push('<p class="tl-note">' + esc(m.definition || '')
      + ' Read down the opponent axis of the same grids: for each of the '
      + commas(N) + ' ' + esc(OPP) + ' IV spreads, how many ' + esc(FOCAL)
      + ' spreads it beats or ties, against three ' + esc(FOCAL)
      + ' populations ('
      + Object.keys(pops).map(function (k) {
        return commas(pops[k]) + ' = '
          + ((m.population_notes || {})[k] || k);
      }).join('; ') + ').</p>');

    // (a) verdict box -- three computed read-outs
    var BP_KEY = denBpKey();
    var bpPop = pops[BP_KEY];
    var wallCell = (DEN.wall_table || {}).cell || '';
    var wallRows = (DEN.wall_table || {}).rows || [];
    var best = wallRows[0];
    var vparts = [];
    var wallGrid = wallCell.split('|')[0], wallScen = wallCell.split('|')[1];
    // ANTI-RECURRENCE: a sentence about what the PAGE defaults to must read
    // the static default, never the current selection. Binding this to
    // state.label made the sentence lie the moment a reader touched the
    // grid dropdown.
    var defGrid = DEFAULT_GRID;
    var sameGrid = (wallGrid === defGrid);
    if (bpPop && best) {
      // The verdict adjective is DERIVED from the denial fraction; the
      // original hardcoded "there is no <opp> answer", which was true for
      // Thievul (a handful of 2992) and the exact opposite on Wigglytuff
      // (435/435 denied -- 2026-08-19 review blocker).
      var bpFrac = best.denies[BP_KEY] / bpPop;
      var bpVerdict = (bpFrac >= 1 ? 'the ' + esc(OPP) + ' answer is total:'
        : bpFrac >= 0.75 ? 'the ' + esc(OPP) + ' answer is near-total:'
        : bpFrac >= 0.25 ? 'the ' + esc(OPP) + ' answer is partial:'
        : 'there is no real ' + esc(OPP) + ' answer:');
      vparts.push('<li><strong>In one cell -- ' + esc(gridAbbrev(wallGrid))
        + ' ' + esc(wallScen) + ', against the '
        + commas(bpPop) + ' breakpoint-clearing ' + esc(FOCAL)
        + ' spreads -- ' + bpVerdict + '</strong> the '
        + 'best defense step denies ' + best.denies[BP_KEY] + ' of them. '
        // LATENT-BUG GUARD: "selected above" is a claim about the
        // dropdown, and sameGrid compares against the STATIC default --
        // the same binding mismatch that was a blocker in the sibling
        // branch. It is unreachable on both shipped pages; fixed here so
        // the next opponent page cannot inherit it.
        + (sameGrid ? 'That is also the grid this page defaults to.'
          : 'On ' + esc(gridAbbrev(defGrid)) + ', the grid this page '
            + 'defaults to, the picture differs -- see the ranked table '
            + 'below, where several builds deny most or all of that same '
            + 'population.') + '</li>');
    }
    if (best) {
      // Rank is INTERPOLATED (the original hardcoded "rank-1" while
      // naming the rank-2 build -- 2026-08-19 review), the cost
      // adjective follows the actual rank, and the build NAMED for the
      // top-512 sentence is picked BY top-512 denial (SP rank as
      // tiebreak) -- the all-4096 argmax merely reported its top-512
      // number, naming rank 2 where rank 1 ties (2026-08-19 verify).
      var best512 = wallRows.slice().sort(function (a, b) {
        return (b.denies.top512 - a.denies.top512) || (a.rank - b.rank);
      })[0] || best;
      var costTxt = (best512.rank === 1 ? 'zero'
        : best512.rank <= 50 ? 'near-zero' : 'a real');
      vparts.push('<li><strong>Against the top-512 ' + esc(FOCAL)
        + ' spreads in that same cell (' + esc(gridAbbrev(wallGrid)) + ' '
        + esc(wallScen) + '), rank ' + best512.rank
        + ' is the best answer:</strong> '
        + esc(best512.ivs.join('/')) + ' (defense '
        + best512.def + ') denies '
        + denialPct(best512.denies.top512, pops.top512) + ' of them, at '
        + costTxt + ' stat-product '
        + 'cost' + (best512.rank > 50 ? ' (rank ' + best512.rank + ')' : '')
        + '.</li>');
    }
    // The bait lever is per moveset: on a grid whose bait/no-bait pair is
    // byte-identical it is provably a no-op, and saying otherwise would
    // contradict this page's own IDENTICAL GRIDS rail.
    var byCell = {};
    (DEN.sensitive_cells || []).forEach(function (c) {
      byCell[c.grid + '|' + c.scenario] = c;
    });
    // Which two cells? The bait / no-bait pair of the PRIMARY moveset,
    // found through the grid metadata rather than through a grid-label
    // literal, at the scenario people plan around.
    var BAIT_SCEN = '1-1';
    var bMs = msKeyOf(primaryGrid()), bGrid = null, nGrid = null;
    GRID_LABELS.forEach(function (lb) {
      if (msKeyOf(lb) !== bMs) return;
      var g = (META.grids || {})[lb] || {};
      if (g.bait === true && bGrid === null) bGrid = lb;
      if (g.bait === false && nGrid === null) nGrid = lb;
    });
    var baited = bGrid ? byCell[bGrid + '|' + BAIT_SCEN] : null;
    var unbaited = nGrid ? byCell[nGrid + '|' + BAIT_SCEN] : null;
    var dupPairs = (META.duplicate_grids || []);
    var noopGrids = [];
    dupPairs.forEach(function (g) {
      if (g.length > 1) noopGrids.push(msAbbrev(g[0]));
    });
    // Are the bait/no-bait grids of the primary arm byte-identical?
    // Then denial.json only carries ONE of them, byCell has a single
    // entry, and the !=-presence fallback below would fabricate a
    // 'lever' sentence that contradicts the IDENTICAL GRIDS banner
    // (fired on the Lickilicky mirror, 2026-08-20 review M2). The
    // truthful bullet is 'baiting changes nothing'.
    var baitPairIsDup = dupPairs.some(function (g) {
      return g.indexOf(bGrid) >= 0 && g.indexOf(nGrid) >= 0;
    });
    if (bGrid && nGrid && baitPairIsDup) {
      vparts.push('<li><strong>Whether ' + esc(FOCAL) + ' baits changes '
        + 'nothing on ' + esc(msAbbrev(bGrid)) + ':</strong> the bait '
        + 'and no-bait grids are byte-identical, so the bait lever does '
        + 'not exist in this matchup (see the IDENTICAL GRIDS note '
        + 'below).</li>');
    }
    if (bGrid && nGrid && !baitPairIsDup && !!baited !== !!unbaited) {
      // One side of the bait pair has no sensitive cell at this scenario
      // (it is saturated or hopeless there) -- that IS the lever, and
      // silence hid it on the bait-dependent Corviknight page
      // (2026-08-19 verify). State it from the reco classification.
      var clsOf = function (lb) {
        var pg = dig(D, 'reco.per_grid_scenarios') || {};
        var e = pg[lb] || {};
        if ((e.saturated_win || []).indexOf(BAIT_SCEN) >= 0) {
          return 'a ' + FOCAL + ' sweep regardless of IVs';
        }
        if ((e.hopeless || []).indexOf(BAIT_SCEN) >= 0) {
          return 'hopeless for ' + FOCAL + ' regardless of IVs';
        }
        return 'IV-decided';
      };
      vparts.push('<li><strong>Whether ' + esc(FOCAL) + ' baits is a '
        + 'bigger lever than any IV at ' + esc(BAIT_SCEN)
        + ':</strong> with baiting the cell is '
        + esc(clsOf(bGrid)) + '; without, it is '
        + esc(clsOf(nGrid)) + '.</li>');
    }
    if (baited && unbaited) {
      vparts.push('<li><strong>Whether ' + esc(FOCAL) + ' baits is a '
        + 'bigger lever than any ' + esc(OPP) + ' IV -- on the '
        + esc(msAbbrev(bGrid)) + ' '
        + 'moveset:</strong> at ' + esc(BAIT_SCEN) + ' the mean denial is '
        + denialPct(baited.all4096.mean, baited.all4096.pop_n)
        + ' of all ' + commas(N) + ' when ' + esc(FOCAL) + ' baits and '
        + denialPct(unbaited.all4096.mean, unbaited.all4096.pop_n)
        + ' when it does not.'
        + (noopGrids.length
          ? ' On ' + esc(noopGrids.join(' / ')) + ' baiting changes '
            + 'nothing at all: those bait and no-bait grids are '
            + 'byte-identical, so the lever does not exist there.'
          : '') + '</li>');
    }
    if (FOCAL === OPP) {
      vparts.push('<li><strong>Mirror note:</strong> on a mirror, denial '
        + 'is the coverage measurement read from the opposite seat (plus '
        + 'ties), so this section and the coverage panels must -- and do '
        + '-- agree; they are one measurement, not two independent '
        + 'analyses.</li>');
    }
    P.push('<div class="tl-verdict-denial"><h4>Verdict</h4><ul>'
      + vparts.join('') + '</ul></div>');

    // (b) the defense wall
    if (wallRows.length) {
      P.push('<h3>The defense wall</h3>'
        + '<p class="tl-note">' + esc(sp.identity || '') + ', so '
        + esc(sp.wall_condition || '') + '. The maximum ' + esc(OPP)
        + ' defense in the species is ' + esc(sp.max_opponent_def)
        + ', which walls ' + commas(sp.max_def_walls_n_focal) + ' of '
        + commas(N) + ' ' + esc(FOCAL) + ' spreads ('
        + fmt(100 * sp.max_def_walls_n_focal / N, 1) + '%) and '
        + (sp.walls_median_focal ? 'does' : 'does NOT')
        + ' wall a median-attack ' + esc(FOCAL) + '. Closed form and grid '
        + 'agree: at the rank-1 ' + esc(OPP) + ' defense ('
        + esc(sp.rank1_opponent_def) + ') the wall holds exactly '
        + commas(sp.n_focal_walled_by_rank1_def) + ' spreads, which is the '
        + commas(sp.n_focal_below_breakpoint) + ' that sit below the '
        + esc(focalMove()) + ' breakpoint.</p>'
        + '<div class="tl-scroll"><table class="tl"><tr>'
        + '<th>' + esc(OPP) + ' rank</th><th>IVs</th><th>level</th>'
        + '<th>CP</th><th>defense</th><th>denies (all ' + commas(N)
        + ')</th><th>denies (top 512)</th><th>denies (breakpoint set)</th>'
        + '</tr>'
        + wallRows.map(function (w) {
          return '<tr><td>' + w.rank + '</td><td>' + esc(w.ivs.join('/'))
            + '</td><td>' + w.level + '</td><td>' + w.cp + '</td><td>'
            + w.def + '</td><td>' + commas(w.denies.all4096) + '</td><td>'
            + commas(w.denies.top512) + '</td><td>'
            + commas(w.denies[denBpKey()]) + '</td></tr>';
        }).join('') + '</table></div>');
    }

    // (c) the opponent fast-move ladder. Its blob key is spelled from the
    // move ("<fast move>_ladder"), so it is found by shape, not by name.
    var ladderKey = Object.keys(DEN).filter(function (k) {
      return /_ladder$/.test(k) && Array.isArray(DEN[k]);
    })[0];
    var ladder = (ladderKey ? DEN[ladderKey] : null) || [];
    var ladderNote = ladderKey ? DEN[ladderKey + '_note'] : null;
    if (!ladder.length && ladderNote) {
      P.push('<h3>The attack route: the ' + esc(slotNames().fast)
        + ' ladder</h3>'
        + '<p class="tl-note">' + esc(ladderNote) + '</p>');
    }
    if (ladder.length) {
      P.push('<h3>The attack route: the ' + esc(slotNames().fast)
        + ' ladder</h3>'
        + '<p class="tl-note">' + esc(ro.identity || '') + ', so '
        + esc(ro.top_tier_condition || '') + '. ' + esc(OPP)
        + ' attack across the species runs '
        + esc((ro.opponent_atk_range || []).join(' to ')) + '.</p>'
        + '<div class="tl-scroll"><table class="tl"><tr>'
        + '<th>land the higher tier on...</th><th>' + esc(FOCAL)
        + ' defense</th><th>' + esc(OPP) + ' attack needed</th>'
        + '<th>' + esc(OPP) + ' spreads qualifying</th></tr>'
        + ladder.map(function (l) {
          return '<tr><td>' + esc(l.target) + '</td><td>' + l.focal_def
            + '</td><td>' + l.opponent_atk_needed + '</td><td>'
            + commas(l.n_opponent_qualifying) + '</td></tr>';
        }).join('') + '</table></div>');
    }

    // (d) ranked builds + the rule and the caveat, adjacent
    // Render EVERY shipped ranked build (the table scrolls); the old
    // 12-row slice contradicted prose citing the top-25
    // (2026-08-19 review).
    var ranked = (DEN.ranked_builds || []);
    var named = DEN.named_builds || [];
    var rule = DEN.composite_rule || {};
    if (ranked.length) {
      var cells = rule.cells || [];
      var cellHead = cells.map(function (c) {
        return '<th title="all 4096 / top 512 / breakpoint set">'
          + esc(cellLabel(c)) + '</th>';
      }).join('');
      function buildRows(rows, withNote) {
        return rows.map(function (b) {
          return '<tr><td>' + esc(b.ivs.join('/')) + '</td><td>' + b.rank
            + '</td><td>' + b.cp + '</td><td>' + b.stat_product_pct
            + '%</td>'
            + cells.map(function (c) {
              var v = (b.per_cell || {})[c] || {};
              // sub-1% non-zero denial reads as exactly zero when
              // truncated (2026-08-19 verify)
              var f1 = function (x) {
                return (x > 0 && x < 1) ? '&lt;1' : fmt(x, 0);
              };
              return '<td>' + f1(v.all4096) + ' / ' + f1(v.top512)
                + ' / ' + f1(v[denBpKey()]) + '</td>';
            }).join('')
            + (withNote ? '<td>' + esc(b.note || '') + '</td>' : '')
            + '</tr>';
        }).join('');
      }
      P.push('<h3>Ranked anti-' + esc(FOCAL) + ' builds</h3>'
        + '<p class="tl-note"><strong>How this ranking is computed:</strong> '
        + esc(rule.formula || '') + ' over these cells: '
        + esc(cells.map(cellLabel).join(', '))
        + ' (' + esc(rule.cell_selection || '')
        + '). This is ' + esc(rule.caveat || '') + '. '
        + '<strong>And the cost is only proxied:</strong> '
        + esc((DEN.caveats || [])[1] || '') + '</p>'
        + '<div class="tl-scroll"><table class="tl"><tr><th>IVs</th>'
        + '<th>rank (stat product)</th><th>CP</th><th>stat product</th>'
        + cellHead + '</tr>' + buildRows(ranked, false) + '</table></div>'
        + '<p class="tl-note">Cells are % of (all ' + commas(N)
        + ' / top 512 / breakpoint-clearing ' + commas(bpPop || 0)
        + ') ' + esc(FOCAL) + ' spreads denied.</p>');
      if (named.length) {
        P.push('<h4>Named ' + esc(OPP) + ' builds</h4>'
          + '<div class="tl-scroll"><table class="tl"><tr><th>IVs</th>'
          + '<th>rank (stat product)</th><th>CP</th><th>stat product</th>'
          + cellHead + '<th>why it is here</th></tr>'
          + buildRows(named, true) + '</table></div>');
      }
    }

    // (e) YOUR opponent spreads
    P.push(renderYourDenial(DEN, rule));

    // ties + provenance
    var ties = DEN.ties || {};
    var tieBits = Object.keys(ties).map(function (g) {
      return gridPretty(g) + ': ' + commas(ties[g].cells) + ' tied cells ('
        + fmt(100 * ties[g].frac_of_cells, 4) + '% of that grid, '
        + commas(ties[g].vs_bp_clearing) + ' of them against a '
        + 'breakpoint-clearing ' + FOCAL + ')';
    });
    P.push('<p class="tl-note">Ties count for ' + esc(OPP)
      + ' in every number above. Tie load: ' + esc(tieBits.join('; '))
      // The producing script names itself in the blob (meta.generated_from),
      // so this citation cannot outlive a rename of the kit.
      + '. Recomputed by <code>' + esc(m.generated_from || 'the denial layer')
      + '</code> from the same baked grids as the rest of this page'
      + (((m.cross_check || {}).agrees === true)
        ? ' and cross-checked against the research run\'s saved marginals ('
          + (m.cross_check.compared || 0) + ' arrays, exact agreement).'
        : '.') + '</p>');
    setHtml('tl-denial', P.join(''));
  }

  // (e) the payoff for entering your own opponent spreads
  function renderYourDenial(DEN, rule) {
    var mine = state.user.filter(function (u) { return u.side === 'licki'; });
    if (!mine.length) {
      return '<h3>Your ' + esc(OPP) + '</h3>'
        + '<p class="tl-note tl-user-empty">Add your own ' + esc(OPP)
        + ' spreads under "Your IVs" (pick the ' + esc(OPP) + ' option '
        + 'whose label mentions the heatmap overlay and this section -- '
        + 'the second one in the species dropdown -- or paste a Poke '
        + 'Genie CSV) and they are ranked here by '
        + 'the same denial metrics.</p>';
    }
    var cells = rule.cells || [];
    var byRank = {};
    (DEN.ranked_builds || []).concat(DEN.named_builds || [])
      .forEach(function (b) { byRank[b.rank] = b; });
    // Rows the blob does not carry are computed from the marginals it does:
    // only ranked/named builds ship per-cell numbers, so anything else is
    // shown with its rank and CP and an explicit "not in the shipped
    // table" note rather than a fabricated number.
    var rows = mine.map(function (u) {
      var b = byRank[u.idx + 1];
      return '<tr><td>' + esc(u.label) + '</td><td>'
        + esc(ivStr('licki', u.idx)) + '</td><td>'
        + (typeof u.cp === 'number' ? esc(u.cp) : '-') + '</td><td>'
        + (u.idx + 1) + '</td>'
        + cells.map(function (c) {
          var v = b ? ((b.per_cell || {})[c] || {}) : null;
          return '<td>' + (v ? fmt(v.all4096, 0) + ' / ' + fmt(v.top512, 0)
            + ' / ' + fmt(v[denBpKey()], 0) : '-') + '</td>';
        }).join('')
        + '<td>' + (b ? esc(b.note || '') + (b.composite_rank
          ? ' (composite rank ' + b.composite_rank + ')' : '')
          : 'outside the ' + ((DEN.ranked_builds || []).length
              ? 'top-' + (DEN.ranked_builds || []).length + ' ranked'
              : 'ranked')
            + ((DEN.named_builds || []).length ? ' / named' : '')
            + ' set shipped with this page')
        + '</td></tr>';
    }).join('');
    return '<h3>Your ' + esc(OPP) + '</h3>'
      + '<div class="tl-scroll"><table class="tl"><tr><th>source</th>'
      + '<th>IVs</th><th>CP now (as scanned)</th>'
      + '<th>rank (stat product)</th>'
      + cells.map(function (c) {
        return '<th>' + esc(cellLabel(c)) + '</th>';
      }).join('') + '<th>note</th></tr>' + rows + '</table></div>'
      + '<p class="tl-note">Cells are % of (all ' + commas(N)
      + ' / top 512 / breakpoint-clearing) ' + esc(FOCAL) + ' spreads your '
      + esc(OPP) + ' denies. Per-cell numbers ship only for the ranked and '
      + 'named builds above; a spread outside that set shows its rank and '
      + 'CP with the gap stated rather than a guessed number.</p>';
  }

  // ---- your IVs ----
  // Returns false when this exact spread is already listed, so callers can
  // report "matched N (M were duplicate spreads)" instead of claiming more
  // rows than the table shows. On a duplicate we keep the HIGHEST scanned
  // CP, because the CP column exists so you can find the mon in-game and
  // the strongest copy is the one you would evolve.
  function addUser(side, idx, label, opts) {
    opts = opts || {};
    for (var i = 0; i < state.user.length; i++) {
      var u = state.user[i];
      if (u.side === side && u.idx === idx) {
        if (typeof opts.cp === 'number'
            && (typeof u.cp !== 'number' || opts.cp > u.cp)) {
          u.cp = opts.cp;
        }
        return false;
      }
    }
    state.user.push({ side: side, idx: idx, label: label,
                      cp: (typeof opts.cp === 'number') ? opts.cp : null,
                      note: opts.note || '' });
    return true;
  }

  // ---- verdict-table plumbing (all read from TL_DATA) ----
  // The primary grid is a property of the RECOMMENDATION, not of the
  // dropdown: if it followed state.label then "primary" and "other" would
  // swap meaning every time the grid changed, and the basis toggle would
  // be meaningless.
  function primaryGrid() {
    var pg = (D.reco || {}).primary_grid;
    if (pg && (D.cov || {})[pg]) return pg;
    return GRID_LABELS.length ? GRID_LABELS[0] : state.label;
  }
  // Which basis corresponds to a given moveset key?
  function basisForMoveset(ms) {
    return (ms === msKeyOf(primaryGrid())) ? 'primary' : 'other';
  }
  function msKeyOf(label) { return String(label || '').split('_')[0]; }
  // Cell headers must distinguish bait from no-bait: msAbbrev names the
  // moveset only, so a moveset's bait and no-bait grids rendered alike.
  function gridAbbrev(label) {
    var g = (META.grids || {})[label] || {};
    var bait = (g.bait === false) ? ' no-bait'
      : (g.bait === true ? ' bait' : '');
    return msAbbrev(label) + bait;
  }
  function cellLabel(cellKey) {
    var parts = String(cellKey).split('|');
    return gridAbbrev(parts[0]) + ' ' + parts[1];
  }
  function msAbbrev(label) {
    var g = (META.grids || {})[label] || {};
    var ch = g.focal_charged || [];
    if (!ch.length) return msKeyOf(label).toUpperCase();
    return ch.map(function (m) {
      return String(m).split('_').map(function (w) {
        return w.charAt(0).toUpperCase();
      }).join('');
    }).join('+');
  }
  // The bait grid on the OTHER moveset -- the moveset-robustness check.
  function otherMovesetGrid(primary) {
    var pk = msKeyOf(primary), pick = null;
    GRID_LABELS.forEach(function (lb) {
      if (msKeyOf(lb) === pk) return;
      if (pick === null || /_bait$/.test(lb)) {
        if (pick === null || !/_bait$/.test(pick)) pick = lb;
      }
    });
    return pick;
  }
  // ---- build basis ----
  // The ranking answers "which of MY mons should I build" -- and that
  // depends on which moveset you intend to run. Basis 'primary' ranks on
  // the reco's primary grid and its pick scenarios; basis 'other' ranks on
  // the other moveset's bait grid over ITS OWN sensitive scenarios, in the
  // same priority order the assembly used. Everything is read from the
  // blob; nothing about which scenarios matter is assumed here.
  function scenarioPriority() {
    var rule = String((D.reco || {}).scenario_priority_rule || '');
    var m = rule.match(/fixed order ([0-9\-,\s]+)/);
    if (m) {
      var order = m[1].split(',').map(function (s) { return s.trim(); })
        .filter(Boolean);
      if (order.length) return order;
    }
    return (META.scenarios || []).slice();
  }
  function basisGrid() {
    var pg = primaryGrid();
    if (state.basis === 'other') return otherMovesetGrid(pg) || pg;
    return pg;
  }
  function crossGrid() {
    var pg = primaryGrid(), og = otherMovesetGrid(pg);
    return (state.basis === 'other') ? pg : og;
  }
  function basisPicks() {
    var lb = basisGrid();
    if (state.basis !== 'other') return pickScenarios();
    var sc = META.scenarios || [];
    var pgs = ((D.reco || {}).per_grid_scenarios || {})[lb] || {};
    var sens = pgs.sensitive;
    if (!sens || !sens.length) {
      var s = saturationForGrid(lb);
      var nearly = ((s && s.nearly) || []).map(function (x) {
        return String(x).split(' ')[0];
      });
      sens = s ? scenarioComplement((s.all || [])
        .concat(s.hopeless || []).concat(nearly)) : sc.slice();
    }
    var order = scenarioPriority();
    var ranked = order.filter(function (x) { return sens.indexOf(x) >= 0; });
    sens.forEach(function (x) {
      if (ranked.indexOf(x) < 0) ranked.push(x);
    });
    var want = Math.max(1, pickScenarios().length);
    return ranked.slice(0, want).map(function (lbl) {
      return { label: lbl, si: sc.indexOf(lbl) };
    }).filter(function (o) { return o.si >= 0; });
  }
  function basisLabel(lb) {
    return msAbbrev(lb) + ' (' + gridPretty(lb) + ')';
  }
  function pickScenarios() {
    var sc = META.scenarios || [];
    var want = (D.reco || {}).pick_scenarios || [];
    var out = [];
    want.forEach(function (s) {
      var si = sc.indexOf(s);
      if (si >= 0) out.push({ label: s, si: si });
    });
    if (!out.length) out.push({ label: scenarioLabel(state.si), si: state.si });
    return out;
  }
  function cov512Pct(label, idx, si) {
    var tbl = (D.cov || {})[label];
    if (!tbl || !tbl.top512) return null;
    return 100 * tbl.top512[idx * NS + si] / 512;
  }
  function spTierArray() {
    var bp = D.breakpoints || {};
    try {
      return bp.thievul_offense.moves[focalMoveId()]
        .tier_vs_rank1_licki_by_spread || null;
    } catch (e) { return bp.sp_damage_vs_licki_rank1 || null; }
  }
  // The verdict table is anchored to the RECOMMENDATION's basis, not to
  // the grid/scenario dropdowns: the reco tiebreak chain ends in "meta
  // wins (<primary grid>, 1-1)", so ranking on whatever scenario the
  // reader happens to be exploring would reorder the recommendation. The
  // caption says this out loud.
  var RECO_META_SCEN = '1-1';
  var OTHER_ROBUST_PCT = 80;
  // ...and its negative counterpart: without it a spread that collapses to
  // 0% on the other moveset still read as all-green.
  var OTHER_COLLAPSE_PCT = 40;
  // The same bar applied to the RANKED moveset itself. Without it a
  // spread could be worst-in-class on the very basis the table sorts by
  // and still show no warning -- the cross-moveset chips only ever
  // described the OTHER grid. "Build this one" is gated on the same
  // number, so the page never recommends a spread it would warn about.
  var BASIS_WEAK_PCT = OTHER_COLLAPSE_PCT;
  // Coverage percentages are printed at ONE precision everywhere -- the
  // TL;DR band (covText), the verdict table, and the reco cards' lines,
  // which scripts/joint_iv_assemble.py formats at the same single
  // decimal. One quantity, one rendering.
  var COV_DP = 1;
  // The band reads the same stored values the reco cards' generated lines
  // print, and BOTH now render at COV_DP -- the assemble script formats
  // its card lines with the same one decimal. Rendering the stored 2dp
  // repr here is what put "97.27%" in the band next to "97.3%" in the
  // table for the identical quantity.
  function covText(v) {
    if (typeof v !== 'number') return metricText(v);
    return fmt(v, COV_DP);
  }
  function recoMetaWins() {
    var MW = D.meta_wins;
    if (!MW) return null;
    var pg = basisGrid();
    var byGrid = MW.wins || {};
    var byS = byGrid[pg];
    if (byS) {
      if (byS[RECO_META_SCEN]) {
        return { vals: byS[RECO_META_SCEN],
                 note: 'shields ' + RECO_META_SCEN + ', grid '
                   + gridPretty(pg) + ' (fixed - it does NOT follow the '
                   + 'controls, because the ranking is the '
                   + 'recommendation\'s)' };
      }
      var k0 = Object.keys(byS)[0];
      if (k0) {
        return { vals: byS[k0], note: 'shields ' + k0 + ', grid '
          + gridPretty(pg) + ' (fixed)' };
      }
    }
    if (MW.wins_11) {
      return { vals: MW.wins_11, note: (MW.wins_11_key || '1-1 shields')
        + ' (fixed)' };
    }
    return null;
  }
  function spHiTier() {
    try {
      return D.breakpoints.thievul_offense.moves[focalMoveId()]
        .breakpoint_vs_rank1_licki.hi_tier;
    } catch (e) { return null; }
  }
  // Why a scenario is NOT a ranking column: it is either already decided
  // (saturated or hopeless on this basis grid) or it lost the priority
  // cut. Computed per basis, so the answer changes with the toggle.
  function notShownText(lb, picks) {
    var s = saturationForGrid(lb);
    if (!s) return '';
    var shown = {};
    picks.forEach(function (p) { shown[p.label] = 1; });
    var sat = (s.all || []).filter(function (x) { return !shown[x]; });
    var hop = (s.hopeless || []).filter(function (x) { return !shown[x]; });
    var nearly = (s.nearly || []).map(function (x) {
      return String(x).split(' ')[0];
    }).filter(function (x) { return !shown[x] && hop.indexOf(x) < 0; });
    var rest = scenarioComplement((s.all || []).concat(s.hopeless || [])
      .concat(nearly)).filter(function (x) { return !shown[x]; });
    var bits = [];
    if (sat.length) {
      bits.push(sat.join(', ') + ' - every ' + FOCAL + ' spread beats '
        + 'every ' + OPP + ' there on this build, so IVs cannot separate '
        + 'them');
    }
    if (hop.length) {
      bits.push(hop.join(', ') + ' - lost regardless of IVs');
    }
    if (nearly.length) {
      bits.push(nearly.join(', ') + ' - effectively lost regardless of IVs '
        + '(see the summary at the top)');
    }
    if (rest.length) {
      bits.push(rest.join(', ') + ' - IV-sensitive, but below the top '
        + picks.length + ' in the assembly\'s priority order');
    }
    return bits.length
      ? ' Not shown as ranking columns: ' + bits.join('; ') + '.' : '';
  }
  // The visible reason beside a chip. Three cases, one template each:
  //   over cap  -- SAME sentence for focal and opponent rows (a focal
  //                over-cap row used to get the chip and nothing else),
  //                stating the criterion that was actually CHECKED: the
  //                scanned level is above the analyzed build's level. The
  //                old wording asserted a CP fact nobody computed and the
  //                adjacent "CP now" cell contradicted it.
  //   opponent  -- what the spread is used for, as a properly conjoined
  //                list (the optional third item used to land after an
  //                existing "and").
  //   focal     -- nothing; the row's numbers ARE the verdict.
  function verdictNote(r) {
    if (r.overCap) {
      var lv = (r.u.level !== undefined && r.u.level !== null)
        ? 'L' + r.u.level : 'its scanned level';
      var gl = (r.u.gridLevel !== undefined && r.u.gridLevel !== null)
        ? 'L' + r.u.gridLevel : 'the analyzed build\'s level';
      return ' <span class="tl-note">scanned at ' + esc(lv) + ', above the '
        + esc(LEAGUE_CAP_TEXT) + '-capped build for these IVs (' + esc(gl)
        + '), and power-ups are one-way - so this one can no longer BE that '
        + 'build. It is not fed to the other panels.</span>';
    }
    if (r.focal) return '';
    var uses = ['the heatmap overlay', 'the drill-down picker'];
    if (D.licki_denial) uses.push('the anti-' + FOCAL + ' section');
    var list = uses.length > 1
      ? uses.slice(0, -1).join(', ') + ' and ' + uses[uses.length - 1]
      : uses[0];
    // The row's species cell shows the species AS SCANNED, so this
    // sentence names that species and adds the analyzed form the same way
    // the "Build this one:" line does ("scored as the X it becomes").
    var scanned = r.u.label || OPP;
    var asWhat = (scanned !== OPP)
      ? ' (scored as the ' + esc(OPP) + ' it becomes)' : '';
    return ' <span class="tl-note">not ranked here - this ' + esc(scanned)
      + asWhat + ' spread feeds ' + esc(list) + '.</span>';
  }
  // A ranked verdict table, not a matching log: every column is a number
  // you would use to decide which of YOUR mons to build, and the row order
  // IS the recommendation (the reco blob's own tiebreak chain).
  function renderUser() {
    var picks = basisPicks();
    var pg = basisGrid();
    var og = crossGrid();
    var tiers = spTierArray();
    var hiTier = spHiTier();
    var mw = HAS_META_WINS ? recoMetaWins() : null;
    var poolN = (D.meta_wins || {}).pool_n;
    var primarySi = picks[0] ? picks[0].si : state.si;

    var rows = state.user.map(function (u, i) {
      var focal = (u.side === 'thievul');
      var covs = picks.map(function (p) {
        return focal ? cov512Pct(pg, u.idx, p.si) : null;
      });
      var otherPct = (focal && og) ? cov512Pct(og, u.idx, primarySi) : null;
      var tier = (focal && tiers && tiers.length > u.idx)
        ? tiers[u.idx] : null;
      var wins = (focal && mw && mw.vals) ? mw.vals[u.idx] : null;
      // Every chip carries its own definition AND this spread's numbers
      // in the tooltip, so no chip is a bare adjective.
      var chips = [];
      if (focal && covs.length && covs.every(function (c) {
        return c !== null && c >= 100 - 1e-9;
      })) {
        chips.push(['ok', 'full coverage',
          'full coverage FOR THIS BASIS: 100% of the top-512 ' + OPP
          + ' beaten at '
          + picks.map(function (p) { return p.label; }).join(' and ')
          + ' on ' + gridPretty(pg) + ' (this spread: '
          + covs.map(function (c) { return fmt(c, 1) + '%'; }).join(', ')
          + '). Switch the build-basis control to score it for the other '
          + 'moveset.']);
      }
      if (tier !== null && hiTier !== null && tier < hiTier) {
        chips.push(['warn', 'misses ' + focalMove() + ' bp',
          'misses the ' + focalMove() + ' breakpoint: it does ' + tier
          + ' damage vs the rank-1 ' + OPP + '; ' + hiTier
          + ' is needed to clear it']);
      }
      if (focal && covs[0] !== null && covs[0] <= BASIS_WEAK_PCT) {
        chips.push(['warn', 'weak on ' + msAbbrev(pg),
          'weak on the moveset this table RANKS BY: beats only '
          + fmt(covs[0], 1) + '% of the top-512 ' + OPP + ' at '
          + picks[0].label + ' on ' + gridPretty(pg) + ', at or below the '
          + BASIS_WEAK_PCT + '% bar. Being top of this table means "best '
          + 'of what you own", not "good".']);
      }
      if (otherPct !== null && otherPct <= OTHER_COLLAPSE_PCT) {
        chips.push(['warn', 'collapses on ' + msAbbrev(og),
          'collapses on ' + msAbbrev(og) + ': beats only '
          + fmt(otherPct, 1) + '% of the top-512 ' + OPP + ' at '
          + scenarioLabel(primarySi) + ' on the ' + gridPretty(og)
          + ' grid, versus ' + fmt(covs[0], 1) + '% on this basis. Not '
          + 'moveset-robust.']);
      }
      if (otherPct !== null && otherPct >= OTHER_ROBUST_PCT) {
        chips.push(['ok', msAbbrev(og) + ' robust',
          msAbbrev(og) + ' robust: beats >= ' + OTHER_ROBUST_PCT
          + '% of the top-512 ' + OPP + ' at ' + scenarioLabel(primarySi)
          + ' on the ' + gridPretty(og) + ' grid (this spread: '
          + fmt(otherPct, 1) + '%)']);
      }
      return { u: u, i: i, focal: focal, covs: covs, otherPct: otherPct,
               tier: tier, wins: wins, chips: chips, overCap: false };
    });
    // Over-cap mons: kept OUT of state.user (so the plot overlays are
    // untouched) but shown here, because "you cannot build this one" is
    // exactly the verdict the table exists to give.
    (state.overCap || []).forEach(function (o) {
      rows.push({ u: o, i: -1, focal: (o.side === 'thievul'), covs:
        picks.map(function () { return null; }), otherPct: null,
        tier: null, wins: null,
        chips: [['warn', 'over cap',
          'over cap: scanned L' + o.level + ' > analyzed cap L'
          + o.gridLevel + '; power-ups are one-way, so this one can no '
          + 'longer be the analyzed build']],
        overCap: true });
    });

    // Sort = the reco tiebreak chain: pick-scenario coverage in order,
    // then meta wins, then stat-product rank. Over-cap and non-focal rows
    // sink to the bottom (they have no coverage to rank on).
    rows.sort(function (a, b) {
      if (a.overCap !== b.overCap) return a.overCap ? 1 : -1;
      if (a.focal !== b.focal) return a.focal ? -1 : 1;
      for (var k = 0; k < picks.length; k++) {
        var av = (a.covs[k] === null) ? -1 : a.covs[k];
        var bv = (b.covs[k] === null) ? -1 : b.covs[k];
        if (av !== bv) return bv - av;
      }
      var aw = (a.wins === null) ? -1 : a.wins;
      var bw = (b.wins === null) ? -1 : b.wins;
      if (aw !== bw) return bw - aw;
      return a.u.idx - b.u.idx;
    });

    if (!rows.length) {
      setHtml('tl-user-list', '<p class="tl-note tl-user-empty">Paste or '
        + 'pick your Poke Genie CSV above (or add a spread by hand) and '
        + 'your ' + esc(FOCAL) + ' are ranked here: coverage vs the '
        + 'top-512 ' + esc(OPP) + ', meta wins, and which one to build.'
        + '</p>');
      return;
    }

    var covHead = picks.map(function (p) {
      return '<th>top-512 @ ' + esc(p.label) + '</th>';
    }).join('');
    var otherHead = og
      ? '<th>' + esc(msAbbrev(og)) + ' ' + esc(scenarioLabel(primarySi))
        + '</th>' : '';
    var head = '<tr><th>species</th><th>IVs</th>'
      + '<th title="The CP of the mon as scanned from your CSV, so you can '
      + 'find it in-game. Every other number on the row describes the '
      + 'CP-capped build of that IV spread, not the scanned mon.">'
      + 'CP now (as scanned)</th>'
      + '<th title="Stat-product rank of this IV spread, 1 = best. The '
      + esc(focalMove()) + ' column is damage, not a rank.">'
      + 'rank (stat product)'
      + '</th>' + covHead + otherHead
      + '<th title="' + esc(focalMove())
      + ' damage vs the rank-1 opponent.">'
      + esc(focalMove()) + ' dmg</th>'
      + '<th>meta wins' + (poolN ? ' /' + esc(poolN) : '') + '</th>'
      + '<th>verdict</th><th></th></tr>';
    var body = rows.map(function (r, ri) {
      var u = r.u;
      var cells = picks.map(function (p, k) {
        return '<td>' + (r.covs[k] === null ? '-'
          : fmt(r.covs[k], 1) + '%') + '</td>';
      }).join('');
      var otherCell = og
        ? '<td>' + (r.otherPct === null ? '-' : fmt(r.otherPct, 1) + '%')
          + '</td>' : '';
      var chips = r.chips.map(function (c) {
        return '<span class="tl-chip tl-chip-' + c[0] + '" title="'
          + esc(c[2] || c[1]) + '">' + esc(c[1]) + '</span>';
      }).join(' ');
      return '<tr' + (ri === 0 && !r.overCap && r.focal
          ? ' class="tl-user-top"' : '') + '>'
        + '<td>' + esc(u.label) + '</td>'
        + '<td>' + esc(u.ivs || ivStr(u.side, u.idx)) + '</td>'
        + '<td>' + (typeof u.cp === 'number' ? esc(u.cp) : '-') + '</td>'
        + '<td>' + (u.idx >= 0 ? (u.idx + 1) : '-') + '</td>'
        + cells + otherCell
        + '<td>' + (r.tier === null ? '-' : esc(r.tier)) + '</td>'
        + '<td>' + (r.wins === null ? '-' : esc(fmt(r.wins, 0))) + '</td>'
        + '<td>' + chips + verdictNote(r) + '</td>'
        + '<td>' + (r.i >= 0
          ? '<button data-drop="' + r.i + '">remove</button>' : '')
        + '</td></tr>';
    }).join('');
    var topRow = rows[0];
    // "Build this one" is a RECOMMENDATION, so it is gated on the top row
    // clearing the same bar the weak chip uses -- otherwise the page would
    // tell a reader whose best spread beats 12% of the cohort to build it.
    // Below the bar it still names the best row, but as "the best of what
    // you own", with the number, and it does not recommend.
    var topOk = topRow && topRow.focal && !topRow.overCap
      && topRow.covs[0] !== null && topRow.covs[0] > BASIS_WEAK_PCT;
    var topName = topRow && topRow.u
      ? esc(topRow.u.label)
        + (topRow.u.label !== FOCAL ? ' (scored as the ' + esc(FOCAL)
          + ' it becomes)' : '') + ' ' + esc(topRow.u.ivs
          || ivStr(topRow.u.side, topRow.u.idx))
        + (typeof topRow.u.cp === 'number' ? ' (CP ' + esc(topRow.u.cp)
          + ')' : '')
      : '';
    setHtml('tl-user-list',
      (topOk
        ? '<p class="tl-note"><strong>Build this one:</strong> ' + topName
          + ' - top of the ranking below.</p>'
        : (topRow && topRow.focal && !topRow.overCap
          ? '<p class="tl-note"><strong>Nothing here clears the bar.</strong> '
            + 'Your best spread, ' + topName + ', beats '
            + fmt(topRow.covs[0], 1) + '% of the top-512 ' + esc(OPP)
            + ' at ' + esc(picks[0].label) + ' on ' + esc(gridPretty(pg))
            + ' -- at or below the ' + BASIS_WEAK_PCT + '% bar, so it is '
            + 'the best of what you own rather than a build recommendation.'
            + '</p>'
          : ''))
      + '<div class="tl-scroll"><table class="tl">' + head + body
      + '</table></div>'
      + '<p class="tl-note">Ranked for <strong>'
      + esc(msAbbrev(pg)) + '</strong> (' + esc(gridPretty(pg))
      + ')' + (basisForMoveset(msKeyOf(state.label)) === state.basis
        ? ' - this follows the moveset of the grid selected in Controls'
        : ' - MANUALLY OVERRIDDEN: the grid selected in Controls is '
          + esc(msAbbrev(state.label)) + ', so this ranking does NOT match '
          + 'it until you change the grid moveset again')
      + '. Sorted by the '
      + 'recommendation\'s own tiebreak '
      + 'chain: top-512 coverage at '
      + picks.map(function (p) { return p.label; }).join(', then ')
      + ', then meta wins, then stat-product rank. Coverage columns are the '
      + 'percentage of the top-512 ' + esc(OPP) + ' spreads beaten on '
      + esc(gridPretty(pg)) + (og
        ? '; the ' + esc(msAbbrev(og)) + ' column is the same scenario on '
          + esc(gridPretty(og)) + ' (the moveset-robustness check)' : '')
      + '. The ' + esc(focalMove()) + ' column is damage vs the rank-1 '
      + esc(OPP)
      + (hiTier !== null ? ' (' + esc(hiTier) + ' clears the breakpoint)'
        : '')
      + '. Meta wins: ' + esc(mw ? mw.note : 'not embedded')
      + '. CP now is the CP scanned from your CSV, so you can find the '
      + 'mon in-game; rows added by hand have no scanned CP and show "-". '
      + 'This table is anchored to the BUILD BASIS selected '
      + 'above (top-512 cohort, ' + esc(RECO_META_SCEN) + ' meta on that '
      + 'grid) and deliberately does NOT follow the shield-scenario or '
      + 'cohort controls in Controls above.' + esc(notShownText(pg, picks))
      + '</p>');
    var host = $('tl-user-list');
    if (!host) return;
    Array.prototype.forEach.call(host.querySelectorAll('button[data-drop]'),
      function (b) {
        b.addEventListener('click', function () {
          state.user.splice(+b.getAttribute('data-drop'), 1);
          renderUser(); refresh();
        });
      });
  }

  function loadCsv(text) {
    var C = D.collection;
    if (!C || typeof POGOCollection === 'undefined') {
      setHtml('tl-csv-status', missingBox(
        'the collection blob is not embedded in this page.'));
      return;
    }
    var mons, res;
    try {
      POGOCollection.setConstants({
        cpm: C.cpm, shadowAtkBonus: C.shadowAtkBonus,
        shadowDefMult: C.shadowDefMult
      });
      mons = POGOCollection.parseCsvText(text);
      // Raw data lines the parser produced nothing for (blank/unreadable)
      // -- 'Parsed 2,524 rows' from a 2,526-row export left 2 rows
      // unaccounted (2026-08-19 review).
      var rawDataLines = text.split(/\r?\n/).filter(function (l) {
        return l.trim() !== '';
      }).length - 1;   // minus the header
      var unparsed = Math.max(0, rawDataLines - mons.length);
      res = POGOCollection.matchMons(mons, C.thresholds, {
        league: C.league, maxLevel: C.maxLevel,
        pokemonIndex: C.pokemonIndex, preToFinals: C.preToFinals,
        leagueCaps: C.leagueCaps, rankLookup: C.rankLookup,
        requireGender: C.requireGender || null
      });
    } catch (e) {
      setHtml('tl-csv-status',
        '<div class="tl-missing"><strong>CSV parse failed.</strong> '
        + esc(e.message) + '</div>');
      return;
    }
    var added = 0, dupes = 0, offGrid = 0, overCapN = 0, other = [],
      matchedMons = [];
    Object.keys(res).forEach(function (sp) {
      res[sp].forEach(function (r) {
        if (r.mon) matchedMons.push(r.mon);
        var side = (sp === C.focalSpecies) ? 'thievul'
          : (sp === C.oppSpecies) ? 'licki' : null;
        if (!side) {
          other.push(sp + ' ' + r.mon.atk_iv + '/' + r.mon.def_iv + '/'
                     + r.mon.sta_iv);
          return;
        }
        var idx = ivIndex(side, r.mon.atk_iv, r.mon.def_iv, r.mon.sta_iv);
        if (idx < 0) { offGrid++; return; }
        // Species AS SCANNED. That it is analyzed as the final form is
        // implicit (the whole page is about that species) and the cohort
        // text says so; repeating it on every row is noise.
        var nm = r.csv_species || sp;
        // No evolve / power-up notes: anyone reading this already knows a
        // A pre-evolution must be evolved. The only level fact worth a
        // warning is
        // "you are already ABOVE the analyzed build and cannot power down".
        var gridLevel = (D[side] || {}).level[idx];
        var actual = (r.mon && typeof r.mon.level === 'number')
          ? r.mon.level : null;
        if (actual !== null && actual > gridLevel) {
          var seenOC = false;
          for (var oc = 0; oc < state.overCap.length; oc++) {
            if (state.overCap[oc].side === side
                && state.overCap[oc].idx === idx) {
              var prev = state.overCap[oc];
              if (r.mon && typeof r.mon.cp === 'number'
                  && (typeof prev.cp !== 'number' || r.mon.cp > prev.cp)) {
                prev.cp = r.mon.cp;
              }
              seenOC = true;
              break;
            }
          }
          if (seenOC) { dupes++; return; }
          state.overCap.push({
            side: side, idx: idx, label: nm,
            ivs: ivStr(side, idx),
            cp: (r.mon && typeof r.mon.cp === 'number') ? r.mon.cp : null,
            level: actual, gridLevel: gridLevel
          });
          overCapN++;
          return;
        }
        if (addUser(side, idx, nm, {
          cp: (r.mon && typeof r.mon.cp === 'number') ? r.mon.cp : null
        })) {
          added++;
        } else {
          dupes++;
        }
      });
    });
    if (C.focalSpecies === C.oppSpecies) {
      // MIRROR: the side router above can only ever hit the focal slot
      // (sp === C.focalSpecies wins first -- 2026-08-20 review M3), so
      // the denial panel's 'or paste a CSV' promise was inert. A scanned
      // mon on a mirror is both 'your build' and 'opponent tech':
      // propagate CSV-added focal entries to the opponent slot too.
      // addUser dedups, and the counters deliberately keep counting each
      // physical mon once.
      state.user.filter(function (u) { return u.side === 'thievul'; })
        .forEach(function (u) {
          addUser('licki', u.idx, u.label,
                  {cp: (typeof u.cp === 'number') ? u.cp : null});
        });
    }
    // Rows of an analyzed species that the matcher produced nothing for.
    // The usual cause is mechanical and checkable: at the scanned level the
    // FINAL form is already over the league CP cap, and power-ups are
    // one-way -- so there is no legal build. We compute that CP and say so
    // rather than dropping the row in silence.
    var dropped = [];
    // EVERY parsed row must land in exactly one bucket. Round 4 narrowed
    // this loop to the analyzed species to fix a mislabelled report, and
    // thereby dropped unbuildable rows of a merely-READ species in total
    // silence. The species list decides the WORDING, never whether the
    // row is reported.
    var analyzed = C.analyzedSpecies || C.collectionSpecies || [];
    var known = C.collectionSpecies || [];
    var notRead = 0;
    mons.forEach(function (mon) {
      if (matchedMons.indexOf(mon) >= 0) return;
      if (known.indexOf(mon.name) < 0) { notRead++; return; }
      if (analyzed.indexOf(mon.name) < 0) {
        // Read but not ranked (a species this page reads but does not
        // rank, e.g. the opponent's other evolution). It
        // belongs in the "related species" bucket, with the reason when
        // there is one, NOT in the analyzed-species footnote.
        // NEUTRAL wording, the same string the sibling `dropped` path
        // uses: "no usable build at L20" claims a level-based reason,
        // which is false for a shadow row (the real reason is that this
        // page analyzes no shadow forms).
        other.push(mon.name + ' ' + mon.atk_iv + '/' + mon.def_iv + '/'
          + mon.sta_iv + ' - no build in the analyzed grid');
        return;
      }
      // The species ITSELF comes first: when the analyzed opponent is a
      // MID-line species, a scanned one IS the analyzed species, and
      // looking only at what it evolves into classified it as an
      // over-cap final form -- so it fell
      // out of the over-cap branch entirely and was reported under the
      // wrong species. preToFinals maps a final form to itself, so the
      // dedupe keeps this a no-op for every already-final species.
      var finals = [mon.name].concat(
        ((C.preToFinals || {})[mon.name] || []).filter(function (s) {
          return s !== mon.name;
        }));
      // OVER-CAP rows never reach the matcher's output at all (no level
      // at or above the scanned one keeps them under the cap), so they are
      // classified HERE. They belong in the verdict table with an "over
      // cap" chip -- that is the answer the reader needs -- rather than in
      // a footnote.
      var oside = null, oidx = -1;
      for (var fi2 = 0; fi2 < finals.length; fi2++) {
        var s2 = (finals[fi2] === C.focalSpecies) ? 'thievul'
          : (finals[fi2] === C.oppSpecies) ? 'licki' : null;
        if (!s2) continue;
        var ix2 = ivIndex(s2, mon.atk_iv, mon.def_iv, mon.sta_iv);
        if (ix2 >= 0) { oside = s2; oidx = ix2; break; }
      }
      if (oside !== null
          && typeof mon.level === 'number'
          && mon.level > (D[oside] || {}).level[oidx]) {
        var dup = false;
        for (var oc2 = 0; oc2 < state.overCap.length; oc2++) {
          if (state.overCap[oc2].side === oside
              && state.overCap[oc2].idx === oidx) {
            if (typeof mon.cp === 'number'
                && (typeof state.overCap[oc2].cp !== 'number'
                  || mon.cp > state.overCap[oc2].cp)) {
              state.overCap[oc2].cp = mon.cp;
            }
            dup = true;
            break;
          }
        }
        if (dup) { dupes++; }
        if (!dup) {
          state.overCap.push({
            side: oside, idx: oidx,
            label: mon.name,
            ivs: ivStr(oside, oidx),
            cp: (typeof mon.cp === 'number') ? mon.cp : null,
            level: mon.level, gridLevel: (D[oside] || {}).level[oidx]
          });
          overCapN++;
        }
        return;
      }
      var why = '';
      for (var f = 0; f < finals.length; f++) {
        var base = (C.pokemonIndex || {})[finals[f]];
        if (!base) continue;
        try {
          var cpAtLevel = POGOCollection.computeCp(
            base.atk, base.def, base.hp,
            mon.atk_iv, mon.def_iv, mon.sta_iv, mon.level);
          if (cpAtLevel > C.leagueCap) {
            why = 'as ' + finals[f] + ' at your level ' + mon.level
              + ' it would be CP ' + cpAtLevel + ', over the '
              + C.leagueCap + ' cap, and power-ups are one-way';
          }
        } catch (e) { /* fall through to the generic wording */ }
      }
      dropped.push(mon.name + ' ' + mon.atk_iv + '/' + mon.def_iv + '/'
        + mon.sta_iv + ' (L' + mon.level + ')'
        + (why ? ' - ' + why : ' - no build in the analyzed grid'));
    });
    // CLOSURE: the buckets must add up to what was parsed. This is a
    // visible statement, not a silent invariant -- the last two rounds
    // both lost rows in a bucket that stopped being reached.
    var accounted = added + dupes + overCapN + offGrid + other.length
      + dropped.length + notRead;
    var unaccounted = mons.length - accounted;
    setHtml('tl-csv-status',
      '<p class="tl-note">Parsed ' + plural(mons.length, 'row')
      + (unparsed ? ' (' + plural(unparsed, 'raw line')
        + ' not readable as a row)' : '') + '; added '
      + plural(added, 'new spread') + ' to the table'
      + (dupes ? '; ' + plural(dupes, 'row') + ' collapsed into a spread already '
        + 'listed, keeping the highest scanned CP (duplicate IVs in your '
        + 'export, or a re-paste of the same file)' : '')
      + (overCapN ? '; ' + overCapN + ' already above the analyzed build\'s '
        + 'level, listed in the table with an "over cap" verdict' : '')
      + (offGrid ? '; ' + offGrid + ' off-grid (not in the 4096)' : '')
      + (other.length
        ? '; ' + plural(other.length, 'row') + ' of a related species this page '
          + 'reads but does not analyze, so they are listed here rather '
          + 'than ranked (' + esc(other.slice(0, 6).join(', '))
          + (other.length > 6 ? '; and ' + (other.length - 6) + ' more' : '')
          + ')'
        : '')
      + (notRead
        ? '; ' + plural(notRead, 'row') + ' of a species this page does '
          + 'not read (a full export lists your whole collection; only '
          + esc(known.join(', ')) + ' are read here)'
        : '')
      + (unaccounted
        ? '; INTERNAL ACCOUNTING ERROR - the categories above '
          + (unaccounted > 0
            ? 'leave ' + plural(unaccounted, 'row') + ' unclassified'
            : 'count ' + plural(-unaccounted, 'row') + ' twice')
          + ' (please report this; every row should fall in exactly one '
          + 'category)'
        : '')
      + '. Nothing leaves your browser.</p>'
      + (dropped.length
        ? '<p class="tl-note">' + plural(dropped.length, 'row') + ' of the analyzed '
          + 'species produced no usable build: '
          + esc(dropped.slice(0, 6).join('; '))
          + (dropped.length > 6 ? '; and ' + (dropped.length - 6) + ' more'
            : '') + '.</p>'
        : ''));
    renderUser();
    refresh();
  }

  // ---- controls / banners ----
  function gridPretty(label) {
    var g = (META.grids || {})[label];
    if (!g) return String(label);
    return g.pretty || (g.focal_fast + ' + ' + (g.focal_charged || []).join('/')
      + (g.bait ? ', baiting' : ', no bait'));
  }
  function scenarioText() {
    return state.scenarioAll ? 'all 9 shield scenarios (mean)'
      : 'shields ' + scenarioLabel(state.si) + ' (you-opponent)';
  }
  function renderBanners() {
    // b = the collapsed methodology list; top = the always-visible strip
    // under the controls. A rail goes in exactly ONE of them, so the two
    // can never drift apart.
    var b = [], top = [];
    if (META.provenance) b.push(esc(META.provenance));
    (META.notes || []).forEach(function (n) {
      b.push(esc(expandOppShorthand(n)));
    });
    // Cohort weighting. This page does NOT model the ladder population --
    // it has no data on which spreads you actually meet -- so it says what
    // the two cohorts ARE and leaves the choice to the reader.
    if (state.cohort === 'all' || state.cohort === 'top512') {
      top.push(esc(OPP) + ' cohort weighting is a MODELING CHOICE: '
        + esc(cohortLabel()) + '. Nothing in this analysis measures which '
        + esc(OPP) + ' spreads people actually run, so neither cohort is '
        + '"the real one" - the all-4096 and top-512 numbers differ, and '
        + 'comparing both is the honest read.');
    } else {
      top.push(esc(OPP) + ' cohort: ' + esc(cohortLabel())
        + ' - a narrow cohort. Compare against the all-4096 and top-512 '
        + 'views before concluding.' + esc(cohortWarnText()));
    }
    // The level range of the analyzed opponent grid, computed here (finding:
    // every spread in the denominator is an XL build, which the old text
    // wrongly framed as what separates the cohorts).
    var LV = (D.licki || {}).level;
    if (LV && LV.length) {
      var lmin = LV[0], lmax = LV[0];
      for (var li = 1; li < LV.length; li++) {
        if (LV[li] < lmin) lmin = LV[li];
        if (LV[li] > lmax) lmax = LV[li];
      }
      b.push('Every one of the 4096 ' + esc(OPP) + ' spreads in the '
        + 'denominator is the CP-capped best build for its IVs, level '
        + lmin + ' to ' + lmax + (lmax > 40
          ? ' - i.e. ALL of them need XL candy (above level 40). This page '
            + 'assumes the ' + esc(OPP) + ' you face is maxed; a level-40 '
            + esc(OPP) + ' is not in this grid at all.'
          : '.'));
    }
    b.push(esc(cliffRuleText()));
    // Meta-wins axis: state the ACTUAL current binding, not a fixed claim.
    var mwb = metaWinsArray();
    if (mwb) {
      top.push('Meta-wins axis is currently bound to: ' + esc(mwb.note)
        + '. It follows the grid/scenario controls unless that note says '
        + 'otherwise.');
    }
    top.push('Ties (battle score exactly 500) count as LOSSES, matching '
      + 'the worlds-grid convention.');
    // Collapse byte-identical grids: offering four when two are one grid
    // contradicts the IDENTICAL GRIDS rail four sentences above.
    var dupGroups = META.duplicate_grids || [];
    var dropped = {};
    dupGroups.forEach(function (g) {
      g.slice(1).forEach(function (lb) { dropped[lb] = g[0]; });
    });
    var distinctGrids = GRID_LABELS.filter(function (lb) {
      return !dropped[lb];
    });
    if (distinctGrids.length > 1) {
      b.push('Moveset robustness: switch the grid dropdown ('
        + esc(distinctGrids.map(gridPretty).join(' / '))
        + ') and check whether the conclusion survives.'
        + (Object.keys(dropped).length
          ? ' (' + esc(Object.keys(dropped).map(gridPretty).join(' / '))
            + ' is not listed here because it is byte-identical to another '
            + 'grid; it stays selectable in the dropdown, marked '
            + '"identical to", so nothing disappears silently.)'
          : ''));
    } else if (GRID_LABELS.length > 1 && distinctGrids.length === 1) {
      b.push('Moveset robustness: the ' + GRID_LABELS.length
        + ' embedded grids collapse to ONE distinct grid (the others are '
        + 'byte-identical), so this page establishes nothing about '
        + 'moveset or bait robustness.');
    } else if (!GRID_LABELS.length) {
      b.push('NO simulation grid is embedded in this build, so this page '
        + 'makes no claim at all about which spreads beat ' + esc(OPP)
        + '.');
    } else if (GRID_LABELS.length === 1) {
      b.push('Only ONE grid is embedded ('
        + esc(gridPretty(GRID_LABELS[0]))
        + '), so moveset-robustness of any conclusion is NOT established '
        + 'by this page.');
    }
    function railHtml(list) {
      return list.map(function (t) {
        return '<div class="tl-rail">' + t + '</div>';
      }).join('');
    }
    setHtml('tl-rails', railHtml(top));
    setHtml('tl-banner', railHtml(b));
  }

  function refresh() {
    renderBanners();
    renderTldr();      // the saturation summary is per-grid
    renderUser();      // the verdict table follows the grid/scenario too
    syncDrillPicker(); // your opponent spreads are drill-down targets
    renderDrill();     // ...and so do YOUR gold stars in the drill-down
    renderDenial();    // ...and your own opponent spreads over there
    drawHeat();
    renderMechanism();
    coverage().then(function (cov) {
      renderPareto(cov);
      renderCliff(cov);
      if (state.covView === 'grid') {
        var all = [];
        for (var si = 0; si < NS; si++) all.push(coverage(si));
        Promise.all(all).then(renderScatterGrid);
      } else {
        renderScatter(cov);
      }
    });
    renderFrontier();
  }

  // ---- init ----
  function initControls() {
    var g = $('tl-grid');
    if (g) {
      if (!GRID_LABELS.length) {
        var o0 = document.createElement('option');
        o0.value = ''; o0.textContent = '(no grid baked)';
        g.appendChild(o0); g.disabled = true;
      }
      // Same policy everywhere: the byte-identical grid stays selectable
      // (so nothing silently disappears) but is MARKED, exactly as the
      // rail and the summary describe it.
      var dupOfLabel = {};
      (META.duplicate_grids || []).forEach(function (grp) {
        grp.slice(1).forEach(function (lb) { dupOfLabel[lb] = grp[0]; });
      });
      GRID_LABELS.forEach(function (lb) {
        var o = document.createElement('option');
        o.value = lb;
        o.textContent = gridPretty(lb)
          + (dupOfLabel[lb]
            ? ' (identical to ' + gridPretty(dupOfLabel[lb]) + ')' : '');
        g.appendChild(o);
      });
      if (state.label) g.value = state.label;
      g.addEventListener('change', function () {
        var prevMs = msKeyOf(state.label);
        state.label = g.value;
        var newMs = msKeyOf(state.label);
        // Changing MOVESET re-points the ranked table at that moveset;
        // a bait-only change within the same moveset leaves it alone. The
        // basis control remains a manual override -- last writer wins, so
        // a manual choice holds until the next moveset change.
        if (newMs !== prevMs) {
          state.basis = basisForMoveset(newMs);
          var bsel = $('tl-basis');
          if (bsel) bsel.value = state.basis;
        }
        refresh();
      });
    }
    var s = $('tl-scenario');
    if (s) {
      for (var si = 0; si < NS; si++) {
        var o = document.createElement('option');
        o.value = String(si);
        o.textContent = scenarioLabel(si) + ' shields (you-opponent)';
        s.appendChild(o);
      }
      var oa = document.createElement('option');
      oa.value = 'all'; oa.textContent = 'all 9 (mean)';
      s.appendChild(oa);
      s.value = String(state.si);
      s.addEventListener('change', function () {
        state.scenarioAll = (s.value === 'all');
        if (!state.scenarioAll) state.si = +s.value;
        refresh();
      });
    }
    var c = $('tl-cohort');
    if (c) {
      [['all', 'All 4096 ' + OPP],
       ['top512', 'Top 512 by stat product'],
       ['top100', 'Top 100 by stat product'],
       ['rank1', 'Rank 1 only'],
       ['custom', 'Custom (ranks / IV triples)']].forEach(function (p) {
        var o = document.createElement('option');
        o.value = p[0];
        o.textContent = p[1]
          + ((p[0] === 'top100' || p[0] === 'rank1' || p[0] === 'custom')
             && state.label
             && (!haveWon(state.label, state.si) || !CAN_GUNZIP)
            ? (CAN_GUNZIP ? ' (needs full win grid)'
              : ' (needs gzip support this browser lacks)') : '');
        c.appendChild(o);
      });
      c.value = state.cohort;
      c.addEventListener('change', function () {
        state.cohort = c.value;
        var box = $('tl-cohort-custom');
        if (box) box.style.display = (c.value === 'custom') ? '' : 'none';
        refresh();
      });
    }
    var cc = $('tl-cohort-custom-input');
    if (cc) {
      cc.addEventListener('change', function () {
        state.customText = cc.value; refresh();
      });
    }
    var cv = $('tl-cov-view');
    if (cv) {
      [['single', 'one scenario (follows the dropdown)'],
       ['grid', 'all 9 scenarios']].forEach(function (pair) {
        var o = document.createElement('option');
        o.value = pair[0];
        o.textContent = pair[1];
        cv.appendChild(o);
      });
      cv.value = state.covView;
      cv.addEventListener('change', function () {
        state.covView = cv.value;
        refresh();
      });
    }
    // NB: unique handle name on purpose -- a duplicate `var` in
    // this function is what silently killed the custom-cohort
    // input (the reviewer's blocker), and `clr` is taken below
    // by the Clear-all button.
    var cliffSel = $('tl-cliff-color');
    if (cliffSel) {
      [['sp', 'colour: ' + focalMoveAbbr() + ' breakpoint class'],
       ['def', 'colour: defense'],
       ['hp', 'colour: HP']].forEach(function (pair) {
        var o = document.createElement('option');
        o.value = pair[0];
        o.textContent = pair[1];
        cliffSel.appendChild(o);
      });
      cliffSel.value = state.cliffColor;
      cliffSel.addEventListener('change', function () {
        state.cliffColor = cliffSel.value;
        coverage().then(renderCliff);
        renderFrontier();   // its caption cross-references this setting
      });
    }
    var bs = $('tl-basis');
    if (bs) {
      var pg0 = primaryGrid(), og0 = otherMovesetGrid(pg0);
      [['primary', pg0], ['other', og0]].forEach(function (pair) {
        if (!pair[1]) return;
        var o = document.createElement('option');
        o.value = pair[0];
        o.textContent = 'rank for ' + msAbbrev(pair[1]);
        bs.appendChild(o);
      });
      if (bs.children.length < 2 && bs.parentNode
          && bs.parentNode.style) {
        // A one-option dropdown is a dead control (single-arm pairs --
        // 2026-08-19 review); the basis is unambiguous, so hide it.
        bs.parentNode.style.display = 'none';
      }
      bs.value = state.basis;
      bs.addEventListener('change', function () {
        // Accept only the values this select actually offers; anything
        // else (programmatic writes, stale restores) falls back to the
        // moveset-derived default instead of rendering a
        // self-contradicting override banner (2026-08-19 verify).
        state.basis = (bs.value === 'primary' || bs.value === 'other')
          ? bs.value : basisForMoveset(msKeyOf(state.label));
        renderUser();
      });
    }
    var hn = $('tl-heat-named');
    if (hn) {
      hn.checked = state.heatNamed;
      hn.addEventListener('change', function () {
        state.heatNamed = !!hn.checked;
        drawHeat();
      });
    }
    var dmine = $('tl-drill-mine');
    if (dmine) {
      dmine.addEventListener('change', function () {
        if (!dmine.value) return;
        var box = $('tl-drill-licki');
        if (box) box.value = dmine.value;
        renderDrill();
      });
    }
    ['tl-drill-licki', 'tl-drill-thievul'].forEach(function (id) {
      var n = $(id);
      if (n) n.addEventListener('change', renderDrill);
    });
    var go = $('tl-drill-go');
    if (go) go.addEventListener('click', renderDrill);

    var add = $('tl-manual-add');
    if (add) {
      add.addEventListener('click', function () {
        var side = ($('tl-manual-species') || {}).value || 'thievul';
        var a = +($('tl-manual-a') || {}).value;
        var d = +($('tl-manual-d') || {}).value;
        var st = +($('tl-manual-s') || {}).value;
        var idx = ivIndex(side, a, d, st);
        if (idx < 0) {
          setHtml('tl-manual-status',
            '<span class="tl-warn">' + esc(a + '/' + d + '/' + st)
            + ' is not in the analyzed grid for that species.</span>');
          return;
        }
        // addUser() returns false when the spread is already listed.
        // Discarding that made the button a silent no-op -- the CSV path
        // reports its collapsed duplicates, so this one did too little.
        var ok = addUser(side, idx, (side === 'thievul' ? FOCAL : OPP), {});
        setHtml('tl-manual-status', ok ? ''
          : '<span class="tl-note">' + esc(a + '/' + d + '/' + st)
            + ' is already in your table (nothing added).</span>');
        renderUser(); refresh();
      });
    }
    var clr = $('tl-user-clear');
    if (clr) {
      clr.addEventListener('click', function () {
        state.user = []; state.overCap = []; renderUser(); refresh();
      });
    }
    var csvBtn = $('tl-csv-load');
    if (csvBtn) {
      csvBtn.addEventListener('click', function () {
        loadCsv(($('tl-csv') || {}).value || '');
      });
    }
    var csvFile = $('tl-csv-file');
    if (csvFile) {
      csvFile.addEventListener('change', function () {
        var f = csvFile.files && csvFile.files[0];
        if (!f) return;
        var rd = new FileReader();
        rd.onload = function () { loadCsv(String(rd.result)); };
        rd.readAsText(f);
      });
    }
    // IV selects
    ['tl-manual-a', 'tl-manual-d', 'tl-manual-s'].forEach(function (id) {
      var sel = $(id);
      if (!sel) return;
      for (var v = 0; v <= 15; v++) {
        var o = document.createElement('option');
        o.value = String(v); o.textContent = String(v); sel.appendChild(o);
      }
      sel.value = '15';
    });
  }

  // A link to a collapsed <details> scrolls to a closed summary, so open
  // it explicitly -- on click and on a #tl-methodology deep link.
  function wireMethodologyLink() {
    var det = document.getElementById('tl-methodology');
    if (!det) return;
    function openIt() {
      try { det.open = true; } catch (e) { /* older engines */ }
    }
    if ((location.hash || '') === '#tl-methodology') openIt();
    var links = document.querySelectorAll
      ? document.querySelectorAll('a[href="#tl-methodology"]') : [];
    Array.prototype.forEach.call(links, function (a) {
      a.addEventListener('click', openIt);
    });
    window.addEventListener('hashchange', function () {
      if ((location.hash || '') === '#tl-methodology') openIt();
    });
  }
  function init() {
    initControls();
    wireMethodologyLink();
    renderUser();
    renderTldr();
    renderReco();
    refresh();
    renderDrill();
    // Re-render on theme change (drop the memo first).
    try {
      var obs = new MutationObserver(function () {
        _themeCache = {};
        refresh();
      });
      obs.observe(document.documentElement,
                  { attributes: true, attributeFilter: ['data-theme'] });
    } catch (e) { /* no observer: charts keep the load-time theme */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
