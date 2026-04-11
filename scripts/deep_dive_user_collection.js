// Pure-JS port of gopvpsim.user_collection + evolution_lines + pokemon
// stat calc primitives. DOM-free: runnable under node for the
// scripts/verify_js_parser.py equivalence harness, and included in the
// interactive deep dive HTML where it powers the paste-box / overlay UI.
//
// This file is the browser-side mirror of src/gopvpsim/user_collection.py.
// The two MUST agree row-for-row on the same input — verify_js_parser.py
// is the enforcement mechanism. When touching this file, re-run the
// verify script before committing.
//
// Exposed API (all functions attached to the global `POGOCollection`
// object so the node harness and the dive HTML can both see them):
//
//   parseCsvText(text)            → [mon, ...]
//   getSpeciesName(name, form, isShadow)
//   ivsToStatsAtCap(baseAtk, baseDef, baseSta, a, d, s, opts)
//   matchMons(mons, thresholds, opts)   → {species: [record, ...]}
//
// The `matchMons` contract matches Python's `match_mons`, not the
// browser-specific "check against the tiers embedded in this dive" flow.
// The dive UI constructs a single-species thresholds dict on the fly
// from DATA.tiers and calls matchMons with it — that keeps the library
// general-purpose while still serving the interactive page cleanly.

(function (global) {
  'use strict';

  // -------------------------------------------------------------------------
  // Form name resolution — Poke Genie form → PvPoke speciesName suffix.
  // Mirrors FORM_MAP in src/gopvpsim/user_collection.py. '' / 'Normal'
  // map to null (no suffix applied).
  // -------------------------------------------------------------------------
  var FORM_MAP = {
    '':         null,
    'Normal':   null,
    'Alola':    'Alolan',
    'Galar':    'Galarian',
    'Hisui':    'Hisuian',
    'Paldea':   'Paldean',
    'Altered':  'Altered',
    'Origin':   'Origin',
    'Defense':  'Defense',
    'Speed':    'Speed',
    'Land':     'Land',
    'Sky':      'Sky',
    'Therian':  'Therian',
    'Confined': 'Confined',
    'Hero':     'Hero',
    'Average':  'Average',
    'Small':    'Small',
    'Large':    'Large',
    'Super':    'Super',
    'Pom-Pom':  'Pom-Pom',
    'Rainy':    'Rainy',
    'Snowy':    'Snowy',
    'Trash':    'Trash',
    'Mega':     'Mega'
  };

  function getSpeciesName(name, form, isShadow) {
    var suffix;
    if (FORM_MAP.hasOwnProperty(form)) {
      suffix = FORM_MAP[form];
    } else {
      // Unknown form passes through (PvPoke's extra variants like
      // 'Paldea Combat' are handled this way).
      suffix = form || null;
    }
    var species = name;
    if (suffix) species = name + ' (' + suffix + ')';
    if (isShadow) species = species + ' (Shadow)';
    return species;
  }

  // -------------------------------------------------------------------------
  // CSV parser. Poke Genie exports use quoted fields when a value contains
  // a comma, so we handle both quoted and unquoted fields. The minimal
  // correctness bar: parse the fixture identically to Python's csv.DictReader.
  // -------------------------------------------------------------------------

  function parseCsvLine(line) {
    var fields = [];
    var cur = '';
    var inQuote = false;
    var i = 0;
    while (i < line.length) {
      var ch = line.charAt(i);
      if (inQuote) {
        if (ch === '"') {
          if (i + 1 < line.length && line.charAt(i + 1) === '"') {
            // Escaped double-quote inside a quoted field.
            cur += '"';
            i += 2;
            continue;
          }
          inQuote = false;
          i += 1;
          continue;
        }
        cur += ch;
        i += 1;
        continue;
      }
      if (ch === '"') { inQuote = true; i += 1; continue; }
      if (ch === ',') { fields.push(cur); cur = ''; i += 1; continue; }
      cur += ch;
      i += 1;
    }
    fields.push(cur);
    return fields;
  }

  function parseCsvText(text) {
    if (text == null) return [];
    // Strip leading UTF-8 BOM (Poke Genie Android export writes one).
    if (text.charCodeAt(0) === 0xFEFF) text = text.substring(1);
    // Normalize line endings: \r\n → \n, standalone \r → \n.
    text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    var lines = text.split('\n');
    // Drop trailing empty line(s).
    while (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
    if (lines.length === 0) return [];

    var header = parseCsvLine(lines[0]);
    var col = {};
    for (var i = 0; i < header.length; i++) col[header[i]] = i;

    function required(name) {
      if (!(name in col)) {
        throw new Error('Poke Genie CSV missing required column: ' + name);
      }
      return col[name];
    }

    // Required columns — if any are missing the header is malformed and
    // we fail loudly. Per-row skips handle individual bad rows.
    var iName    = required('Name');
    var iForm    = required('Form');
    var iCp      = required('CP');
    var iAtk     = required('Atk IV');
    var iDef     = required('Def IV');
    var iSta     = required('Sta IV');
    var iLevel   = required('Level Min');
    var iShadow  = required('Shadow/Purified');
    var iLucky   = required('Lucky');

    var mons = [];
    for (var r = 1; r < lines.length; r++) {
      var row = parseCsvLine(lines[r]);
      try {
        var cp    = parseInt(row[iCp],   10);
        var atkIv = parseInt(row[iAtk],  10);
        var defIv = parseInt(row[iDef],  10);
        var staIv = parseInt(row[iSta],  10);
        var level = parseFloat(row[iLevel]);
        // NaN detection: parseInt('') → NaN. Python's int('') raises
        // ValueError which we catch-and-skip; mirror that here.
        if (!isFinite(cp) || !isFinite(atkIv) || !isFinite(defIv) ||
            !isFinite(staIv) || !isFinite(level)) continue;
        mons.push({
          name:      (row[iName]   || '').trim(),
          form:      (row[iForm]   || '').trim(),
          cp:        cp,
          atk_iv:    atkIv,
          def_iv:    defIv,
          sta_iv:    staIv,
          level:     level,
          is_shadow: (row[iShadow] || '').trim() === '1',
          lucky:     (row[iLucky]  || '').trim() === '1'
        });
      } catch (_e) {
        // Silent skip — same behavior as Python's except (KeyError, ValueError).
      }
    }
    return mons;
  }

  // -------------------------------------------------------------------------
  // Stat calculation. The CPM table and shadow multipliers are injected
  // from the embedding Python code — see POGOCollection.setConstants in
  // deep_dive.py. In the node harness we set them directly from a
  // Python-generated JSON blob so both code paths use identical numbers.
  // -------------------------------------------------------------------------

  var CPM = null;             // {level(float) → multiplier(float)}
  var SORTED_LEVELS = null;   // sorted list of levels present in CPM
  var SHADOW_ATK_BONUS = 6 / 5;
  var SHADOW_DEF_MULT  = 5 / 6;

  function setConstants(opts) {
    if (!opts || !opts.cpm) {
      throw new Error('POGOCollection.setConstants: opts.cpm is required');
    }
    CPM = opts.cpm;
    SORTED_LEVELS = Object.keys(CPM).map(parseFloat);
    SORTED_LEVELS.sort(function (a, b) { return a - b; });
    if (typeof opts.shadowAtkBonus === 'number') SHADOW_ATK_BONUS = opts.shadowAtkBonus;
    if (typeof opts.shadowDefMult  === 'number') SHADOW_DEF_MULT  = opts.shadowDefMult;
  }

  function cpmAt(level) {
    // JS object keys are strings. Accept either a number or a string.
    var key = (typeof level === 'number') ? level.toString() : level;
    if (!(key in CPM)) {
      // Fall back to trying '50' vs '50.0' (Python writes the integer
      // form when a level happens to be a whole number).
      var alt = parseFloat(key).toString();
      if (alt in CPM) return CPM[alt];
      // Or the other way: '50' stored as '50.0'
      var alt2 = (parseFloat(key).toFixed(1));
      if (alt2 in CPM) return CPM[alt2];
      throw new Error('CPM missing level: ' + level);
    }
    return CPM[key];
  }

  function computeCp(baseAtk, baseDef, baseSta, a, d, s, level) {
    var cpm = cpmAt(level);
    var raw = (baseAtk + a) *
              Math.sqrt(baseDef + d) *
              Math.sqrt(baseSta + s) *
              cpm * cpm / 10;
    return Math.max(10, Math.floor(raw));
  }

  function battleStats(baseAtk, baseDef, baseSta, a, d, s, level) {
    var cpm = cpmAt(level);
    return {
      atk: (baseAtk + a) * cpm,
      def: (baseDef + d) * cpm,
      hp:  Math.floor((baseSta + s) * cpm)
    };
  }

  function bestLevel(baseAtk, baseDef, baseSta, a, d, s, maxCp, maxLevel) {
    // Python pokemon.best_level walks the sorted level list and picks
    // the highest level whose CP is <= cap. Mirror that exactly.
    var best = null;
    for (var i = 0; i < SORTED_LEVELS.length; i++) {
      var lv = SORTED_LEVELS[i];
      if (lv > maxLevel) break;
      if (computeCp(baseAtk, baseDef, baseSta, a, d, s, lv) <= maxCp) {
        best = lv;
      }
    }
    return best;
  }

  function ivsToStatsAtCap(baseAtk, baseDef, baseSta, a, d, s, opts) {
    opts = opts || {};
    var shadow = !!opts.shadow;
    var maxLevel = (opts.maxLevel != null) ? opts.maxLevel : 51.0;
    var maxCp = (opts.maxCp != null) ? opts.maxCp : 1500;
    var lv = bestLevel(baseAtk, baseDef, baseSta, a, d, s, maxCp, maxLevel);
    if (lv == null) return null;
    var stats = battleStats(baseAtk, baseDef, baseSta, a, d, s, lv);
    var sAtk = shadow ? SHADOW_ATK_BONUS : 1.0;
    var sDef = shadow ? SHADOW_DEF_MULT  : 1.0;
    var attack  = stats.atk * sAtk;
    var defense = stats.def * sDef;
    var stamina = stats.hp;
    return {
      level:     lv,
      cp:        computeCp(baseAtk, baseDef, baseSta, a, d, s, lv),
      attack:    attack,
      defense:   defense,
      stamina:   stamina,
      stat_prod: Math.floor(attack * defense * stamina),
      bulk_prod: Math.floor(defense * stamina)
    };
  }

  // -------------------------------------------------------------------------
  // Evolution walkup — the caller embeds a precomputed reverse index
  // (`preToFinals[species] = [finalA, finalB, ...]`). Mirrors
  // gopvpsim.evolution_lines.get_final_forms().
  // -------------------------------------------------------------------------

  function getFinalForms(speciesName, preToFinals) {
    if (preToFinals && Object.prototype.hasOwnProperty.call(preToFinals, speciesName)) {
      return preToFinals[speciesName];
    }
    return [speciesName];
  }

  // -------------------------------------------------------------------------
  // Threshold matcher. Direct port of user_collection.match_mons. Callers
  // pass a `pokemonIndex` (species → baseStats) and a `preToFinals` map
  // in opts. Optional `rankLookup` mirrors the Python rank cache —
  // structure: {species: {shadowKey: {ivKey: rank}}}. If absent, ranks
  // default to 4096 so downstream 'onlytop' filters still work
  // conservatively.
  // -------------------------------------------------------------------------

  function ivTupleKey(a, d, s) { return a + ',' + d + ',' + s; }

  function matchTarget(stats, ivKey, target) {
    if (stats.attack  < (target.attack  || 0)) return false;
    if (stats.defense < (target.defense || 0)) return false;
    if (stats.stamina < (target.stamina || 0)) return false;
    if (target.ivs) {
      var hit = false;
      for (var i = 0; i < target.ivs.length; i++) {
        var t = target.ivs[i];
        if (t[0] + ',' + t[1] + ',' + t[2] === ivKey) { hit = true; break; }
      }
      if (!hit) return false;
    }
    if (target.onlytop != null && stats.rank > target.onlytop) return false;
    return true;
  }

  function capitalize(s) { return s.charAt(0).toUpperCase() + s.substring(1); }

  function matchMons(mons, thresholds, opts) {
    // opts: {league, maxLevel, includeEmpty, pokemonIndex, preToFinals, rankLookup}
    opts = opts || {};
    var league = opts.league || 'great';
    var maxLevel = (opts.maxLevel != null) ? opts.maxLevel : 51.0;
    var includeEmpty = !!opts.includeEmpty;
    var pokemonIndex = opts.pokemonIndex || {};
    var preToFinals = opts.preToFinals || null;
    var rankLookup = opts.rankLookup || null;
    var leagueCaps = opts.leagueCaps || { great: 1500, ultra: 2500, master: 10000 };
    var maxCp = leagueCaps[league];
    // NOTE: thresholds keys are the *capitalized* league label
    // ('Great'/'Ultra'/'Master') for compat with gobattlekit's historical
    // schema, while the rest of the API uses lowercase `league`. This
    // bridge MUST match user_collection.match_mons exactly.
    var leagueLabel = capitalize(league);

    function getRank(species, isShadow, ivKey) {
      if (!rankLookup) return 4096;
      var byShadow = rankLookup[species];
      if (!byShadow) return 4096;
      var shadowKey = isShadow ? 'shadow' : 'normal';
      var table = byShadow[shadowKey];
      if (!table) return 4096;
      var r = table[ivKey];
      return (r != null) ? r : 4096;
    }

    var results = {};

    for (var mi = 0; mi < mons.length; mi++) {
      var mon = mons[mi];
      var csvSpecies = getSpeciesName(mon.name, mon.form, mon.is_shadow);

      var targetsToTry = [];
      if (thresholds.hasOwnProperty(csvSpecies)) {
        targetsToTry.push(csvSpecies);
      } else {
        var finals = getFinalForms(csvSpecies, preToFinals);
        for (var fi = 0; fi < finals.length; fi++) {
          var f = finals[fi];
          if (thresholds.hasOwnProperty(f) && targetsToTry.indexOf(f) < 0) {
            targetsToTry.push(f);
          }
        }
      }
      if (targetsToTry.length === 0) continue;

      for (var ti = 0; ti < targetsToTry.length; ti++) {
        var finalSpecies = targetsToTry[ti];
        var speciesBlock = thresholds[finalSpecies];
        if (!speciesBlock || !speciesBlock[leagueLabel]) continue;
        var speciesThresholds = speciesBlock[leagueLabel];
        if (!pokemonIndex.hasOwnProperty(finalSpecies)) continue;

        var base = pokemonIndex[finalSpecies];
        var stats = ivsToStatsAtCap(
          base.atk, base.def, base.hp,
          mon.atk_iv, mon.def_iv, mon.sta_iv,
          { shadow: mon.is_shadow, maxLevel: maxLevel, maxCp: maxCp }
        );
        if (stats == null) continue;

        var ivKey = ivTupleKey(mon.atk_iv, mon.def_iv, mon.sta_iv);
        stats.rank = getRank(finalSpecies, mon.is_shadow, ivKey);

        var matched = [];
        for (var name in speciesThresholds) {
          if (!speciesThresholds.hasOwnProperty(name)) continue;
          if (matchTarget(stats, ivKey, speciesThresholds[name])) {
            matched.push(name);
          }
        }
        if (matched.length > 0) {
          if (!results[finalSpecies]) results[finalSpecies] = [];
          results[finalSpecies].push({
            mon:           mon,
            csv_species:   csvSpecies,
            final_species: finalSpecies,
            is_pre_evo:    csvSpecies !== finalSpecies,
            stats:         stats,
            matched:       matched
          });
        }
      }
    }

    if (includeEmpty) {
      for (var sp in thresholds) {
        if (!thresholds.hasOwnProperty(sp)) continue;
        if (!results[sp] && thresholds[sp][leagueLabel]) results[sp] = [];
      }
    }

    return results;
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------
  var POGOCollection = {
    FORM_MAP:         FORM_MAP,
    getSpeciesName:   getSpeciesName,
    parseCsvText:     parseCsvText,
    setConstants:     setConstants,
    bestLevel:        bestLevel,
    battleStats:      battleStats,
    computeCp:        computeCp,
    ivsToStatsAtCap:  ivsToStatsAtCap,
    getFinalForms:    getFinalForms,
    matchMons:        matchMons,
    ivTupleKey:       ivTupleKey
  };

  // Browser global + node module export, whichever is available.
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = POGOCollection;
  }
  global.POGOCollection = POGOCollection;
})(typeof globalThis !== 'undefined' ? globalThis :
   typeof window      !== 'undefined' ? window      :
   typeof global      !== 'undefined' ? global      : this);
