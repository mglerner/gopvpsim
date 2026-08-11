/* Worlds 2026 IV explorer (plan product 5).
 *
 * Consumes the BAKED closed-form DATA blob (worlds_explorer_data.py):
 * damage-tier ladders vs each opponent's rank-1 anchor, in EFFECTIVE
 * stat space. This module contains NO damage arithmetic and NO damage
 * constants -- the browser only does stat math (delegated to the
 * parity-tested POGOCollection) and threshold comparisons
 * (tests/test_worlds_explorer_js.py scans for the absence of the
 * float32 damage-constant family and pins the delegation).
 *
 * init() THROWS on any missing constant/table -- no fallbacks at all
 * (the setConstants-cpm precedent; a fallback nothing reads in
 * production is guaranteed to rot).
 *
 * Cutoff semantics (worlds_tier0 contracts):
 *   breakpoint reached:  eff_atk >= row.atk   (row.atk null = floor tier)
 *   damage taken >= tier iff eff_def <= row.def; the bulkpoint against
 *   that tier is HELD iff eff_def > row.def (strict -- def_cutoff's
 *   asymmetric contract).
 */
(function (global) {
  'use strict';

  var DATA = null;
  var POGO = null;

  function init(data, pogo) {
    var req = ['entries', 'pairs', 'cpm', 'leagueCap', 'maxLevel',
               'shadowAtkBonus', 'shadowDefMult'];
    for (var i = 0; i < req.length; i++) {
      if (data == null || data[req[i]] == null) {
        throw new Error('WorldsIV.init: missing DATA.' + req[i]);
      }
    }
    POGO = pogo;
    if (!POGO || typeof POGO.ivsToStatsAtCap !== 'function') {
      throw new Error('WorldsIV.init: POGOCollection is required');
    }
    POGO.setConstants({
      cpm: data.cpm,
      shadowAtkBonus: data.shadowAtkBonus,
      shadowDefMult: data.shadowDefMult
    });
    DATA = data;
  }

  function statsFor(mineId, a, d, s, level) {
    var me = DATA.entries[mineId];
    if (!me) throw new Error('unknown species_id: ' + mineId);
    var bs = me.baseStats;
    if (level == null) {
      return POGO.ivsToStatsAtCap(bs.atk, bs.def, bs.hp, a, d, s, {
        shadow: me.shadow,
        maxCp: DATA.leagueCap,
        maxLevel: DATA.maxLevel
      });
    }
    var raw = POGO.battleStats(bs.atk, bs.def, bs.hp, a, d, s, level);
    var sAtk = me.shadow ? DATA.shadowAtkBonus : 1.0;
    var sDef = me.shadow ? DATA.shadowDefMult : 1.0;
    return {
      level: level,
      cp: POGO.computeCp(bs.atk, bs.def, bs.hp, a, d, s, level),
      attack: raw.atk * sAtk,
      defense: raw.def * sDef,
      stamina: raw.hp
    };
  }

  /* Ladder read-outs. rows are sorted ascending by tier; rows[0] is the
   * floor tier (cutoff null = held/reached everywhere in range). */
  function reachedTier(rows, effAtk) {
    var cur = null, next = null;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (r.atk == null || effAtk >= r.atk) {
        cur = r;
      } else {
        next = r;
        break;
      }
    }
    return { tier: cur ? cur.tier : null, next: next };
  }

  function takenTier(rows, effDef) {
    /* damage taken >= rows[i].tier iff effDef <= rows[i].def
     * (row 0: def null = always taken). Returns the highest tier
     * taken, plus the cutoff you'd need to EXCEED to shed it. */
    var taken = rows[0], shed = null;
    for (var i = 1; i < rows.length; i++) {
      var r = rows[i];
      if (effDef <= r.def) {
        taken = r;
      } else {
        break;
      }
    }
    if (taken && taken.def != null) shed = taken.def;
    return { tier: taken ? taken.tier : null, shedAbove: shed };
  }

  function evaluate(mineId, a, d, s, level) {
    if (DATA == null) throw new Error('WorldsIV: init() first');
    var st = statsFor(mineId, a, d, s, level);
    if (!st) return null;
    var me = DATA.entries[mineId];
    /* The baked ladders cover best-level spreads (atk_range/def_range).
     * A manually under-leveled build can sit BELOW those ranges, where
     * the ladder floor row would silently read one tier low/high --
     * flag it out-of-range instead (parity test caught the silent
     * clamp on Fearow @25.5, 2026-08-11). */
    var atkOOR = st.attack < me.atk_range[0] || st.attack > me.atk_range[1];
    var defOOR = st.defense < me.def_range[0] || st.defense > me.def_range[1];
    var out = {
      level: st.level, cp: st.cp,
      attack: st.attack, defense: st.defense, stamina: st.stamina,
      overCap: st.cp > DATA.leagueCap,
      atkOutOfRange: atkOOR, defOutOfRange: defOOR,
      opponents: {}
    };
    var ids = Object.keys(DATA.entries);
    for (var i = 0; i < ids.length; i++) {
      var oppId = ids[i];
      if (oppId === mineId) continue;
      var pair = DATA.pairs[mineId + '|' + oppId];
      if (!pair) throw new Error('missing pair: ' + mineId + '|' + oppId);
      if (pair.excluded) {
        out.opponents[oppId] = { excluded: true };
        continue;
      }
      var bp = null;
      if (!atkOOR) {
        bp = [];
        for (var j = 0; j < pair.bp.length; j++) {
          var m = pair.bp[j];
          var r = reachedTier(m.rows, st.attack);
          bp.push({ move: m.move, tier: r.tier,
                    nextTier: r.next ? r.next.tier : null,
                    nextAtk: r.next ? r.next.atk : null });
        }
      }
      var bulk = null;
      if (!defOOR) {
        bulk = [];
        for (var k = 0; k < pair.bulk.length; k++) {
          var bm = pair.bulk[k];
          var t = takenTier(bm.rows, st.defense);
          bulk.push({ move: bm.move, taken: t.tier,
                      shedAbove: t.shedAbove });
        }
      }
      out.opponents[oppId] = {
        bp: bp, bulk: bulk, stage_flag: !!pair.stage_flag
      };
    }
    return out;
  }

  var api = { init: init, evaluate: evaluate, statsFor: statsFor };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.WorldsIV = api;
})(typeof window !== 'undefined' ? window : this);
