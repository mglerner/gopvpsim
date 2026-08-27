#!/usr/bin/env node
// URL -> outcome: the round-trip validator behind pvpoke_sandbox_lib.verify_url().
//
// Takes a pvpoke.com battle/sandbox URL *string*, routes it through a port of
// src/.htaccess rules 42-48, decodes the query the way Interface.js
// loadGetData() does (dropdown option lists rebuilt exactly as PokeSelect.js
// builds them), and runs PvPoke's real Battle.js on the result.
//
// It deliberately shares no code with the URL *builder*: the dropdown-index
// segment is the only nontrivial encoding in a battle link, and a spec-based
// driver (pvpoke_sandbox.js) cannot exercise it at all.  `resolved` in the
// output is the moveset PvPoke actually built from the indices -- that is what
// makes a mis-indexed link obvious rather than merely wrong-scored.
//
// Structure and the .htaccess port are adapted from the review instrument
// $S/rev_url_run.js (adversarial review, 2026-08-27).
//
// Usage:  node pvpoke_url_run.js <url> [--default-ivs gamemaster|maximize|scale]
//         PVPOKE_ROOT=<path>  (default ~/coding/pvpoke)
//
// --default-ivs emulates the visitor's Settings -> Default IV's, which is what
// decides the spread for any URL that does NOT pin one.  pvpoke.com ships
// "gamemaster" (header.php:64).
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm'), os = require('os');
const ROOT = process.env.PVPOKE_ROOT || path.join(os.homedir(), 'coding', 'pvpoke');
const CHARGE_MULTIPLIERS = [1, .95, .75, .5, .25];

function installShims() {
  global.window = { localStorage: { getItem: () => null, setItem: () => {} } };
  global.host = 'localhost'; global.webRoot = ''; global.siteVersion = 0;
  global.settings = { gamemaster: 'gamemaster' };
  global.customData = null; global.customRankingInterface = undefined;
  const chain = new Proxy(function () {}, { get: () => chain, apply: () => chain });
  const $ = function () { return chain };
  $.ajax = (o) => { global.__s = o.success; return { always: () => {}, done: () => {}, fail: () => {} } };
  $.each = (a, f) => {
    if (Array.isArray(a)) a.forEach((v, i) => f(i, v));
    else if (a && typeof a === 'object') for (const k of Object.keys(a)) f(k, a[k]);
  };
  global.$ = $; global.InterfaceMaster = { getInstance: () => ({ init: () => {} }) };
  global.updateFormatSelect = () => {}; global.updateCupSelect = () => {}; global.gtag = () => {};
}
const ev = fp => vm.runInThisContext(fs.readFileSync(fp, 'utf8'), { filename: fp });

// --- .htaccess emulation (src/.htaccess lines 42-48) -----------------------
// NOTE the asymmetry that costs a level-capped sandbox link its route: the two
// sandbox rules match the CP segment with (\d+), the plain rules with ([\d-]+).
function route(urlPath) {
  const p = urlPath.replace(/^https?:\/\/[^/]+\//, '').replace(/^\/+/, '');
  let m;
  m = p.match(/^battle\/sandbox\/(\d+)\/([a-zA-Z_\d.-]+)\/([a-zA-Z_\d.-]+)\/(\d+)\/([\da-zA-Z_-]+)\/([\da-zA-Z_-]+)\/([\d-]+)\/([\d-]+)\/([\d.-]+).*$/);
  if (m) return { rule: 'sandbox+he', cp: m[1], p1: m[2], p2: m[3], s: m[4], m1: m[5], m2: m[6], h: m[7], e: m[8], sandbox: '1', a: m[9] };
  m = p.match(/^battle\/sandbox\/(\d+)\/([a-zA-Z_\d.-]+)\/([a-zA-Z_\d.-]+)\/(\d+)\/([\da-zA-Z_-]+)\/([\da-zA-Z_-]+)\/([\d.-]+).*$/);
  if (m) return { rule: 'sandbox', cp: m[1], p1: m[2], p2: m[3], s: m[4], m1: m[5], m2: m[6], sandbox: '1', a: m[7] };
  m = p.match(/^battle\/([\d-]+)\/([a-zA-Z_\d.-]+)\/([a-zA-Z_\d.-]+)\/(\d+)\/([\da-zA-Z_-]+)\/([\da-zA-Z_-]+)\/([\d-]+)\/([\d-]+).*$/);
  if (m) return { rule: 'battle+he', cp: m[1], p1: m[2], p2: m[3], s: m[4], m1: m[5], m2: m[6], h: m[7], e: m[8] };
  m = p.match(/^battle\/([\d-]+)\/([a-zA-Z_\d.-]+)\/([a-zA-Z_\d.-]+)\/(\d+)\/([\da-zA-Z_-]+)\/([\da-zA-Z_-]+).*$/);
  if (m) return { rule: 'battle', cp: m[1], p1: m[2], p2: m[3], s: m[4], m1: m[5], m2: m[6] };
  m = p.match(/^battle\/([\d-]+)\/([a-zA-Z_]+)\/([a-zA-Z_]+)\/(\d+).*$/);
  if (m) return { rule: 'battle-short', cp: m[1], p1: m[2], p2: m[3], s: m[4] };
  if (/^battle\/?$/.test(p)) return { rule: 'battle-bare' };
  return null;   // 404 -- no rewrite rule matched
}

// --- dropdown option lists, exactly as PokeSelect.js:190-245 builds them ----
const fastOptions = pk => pk.fastMovePool.map(m => m.moveId).concat(['custom']);
const chargedOptions = pk => ['none'].concat(pk.chargedMovePool.map(m => m.moveId)).concat(['custom']);
const extraOptions = pk => pk.hasThirdChargedMove()
  ? ['none'].concat(pk.extraChargedMovePool.map(m => m.moveId)).concat(['custom']) : [];

function main() {
  const url = process.argv[2];
  const dIdx = process.argv.indexOf('--default-ivs');
  const defaultIVs = dIdx > -1 ? process.argv[dIdx + 1] : 'gamemaster';

  // Route PvPoke's chatter to stderr BEFORE booting: GameMaster logs on load
  // and would otherwise corrupt the JSON on stdout.
  console.log = (...a) => process.stderr.write(a.join(' ') + '\n');
  installShims();
  for (const r of ['GameMaster.js', 'battle/DamageCalculator.js', 'battle/timeline/TimelineAction.js',
    'battle/timeline/TimelineEvent.js', 'battle/actions/ActionLogic.js', 'pokemon/Player.js',
    'pokemon/Pokemon.js', 'battle/Battle.js']) ev(path.join(ROOT, 'src', 'js', r));
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, 'src', 'data', 'gamemaster.json'), 'utf8'));
  const gm = GameMaster.getInstance(); global.__s(data);

  const get = route(url);
  if (!get) { process.stdout.write(JSON.stringify({ error: 'NO_REWRITE_RULE_MATCHED', url })); return; }

  const battle = new Battle();
  let cp, cap = 50;                        // leagueselect.php: every option is cap 50
  if (get.cp.indexOf('-') > -1) { cp = parseInt(get.cp.split('-')[0], 10); cap = parseInt(get.cp.split('-')[1], 10); }
  else cp = parseInt(get.cp, 10);
  battle.setCP(cp); battle.setLevelCap(cap);

  const pokes = [];
  for (const key of ['p1', 'p2']) {
    const idx = key === 'p2' ? 1 : 0, arr = get[key].split('-');
    const pk = new Pokemon(arr[0], idx, battle);
    if (!pk.speciesId) { process.stdout.write(JSON.stringify({ error: 'unknown species ' + arr[0] })); return; }
    pk.initialize(battle.getCP(), defaultIVs);   // PokeSelect.js:794 passes settings.defaultIVs
    pk.autoLevel = true;
    if (arr.length >= 8) {                       // Interface.js:1874
      pk.setIV('atk', arr[2]); pk.setIV('def', arr[3]); pk.setIV('hp', arr[4]);
      pk.setLevel(arr[1]);
      pk.setStartBuffs([parseInt(arr[5]) - 4, parseInt(arr[6]) - 4]);
      if (arr[7]) { pk.baitShields = parseInt(arr[7]); pk.optimizeMoveTiming = (parseInt(arr[8]) == 1); }
    }
    for (let i = 0; i < arr.length; i++) {
      if (arr[i] === 'shadow' || arr[i] === 'purified') pk.setShadowType(arr[i]);
      else if (arr[i] === 'd' && arr.length > i + 1) pk.startCooldown = parseInt(arr[i + 1]);
    }
    pokes.push(pk);
  }
  pokes[0].setShields(parseInt(get.s[0], 10));
  pokes[1].setShields(parseInt(get.s[1], 10));

  const resolved = [];
  for (const key of ['m1', 'm2']) {
    const idx = key === 'm2' ? 1 : 0, pk = pokes[idx];
    if (get[key] === undefined) { resolved.push(null); continue; }
    const arr = get[key].split('-');
    for (let i = 0; i < arr.length; i++) {           // literal MOVE_ID = custom move
      if (arr[i].match('([A-Z_]+)')) {
        const move = gm.getMoveById(arr[i]);
        const pool = (move.energyGain > 0) ? pk.fastMovePool : pk.chargedMovePool;
        pk.addNewMove(arr[i], pool, true, (move.energyGain > 0) ? 'fast' : 'charged', i - 1);
      }
    }
    const fastMoveId = fastOptions(pk)[parseInt(arr[0])];
    if (fastMoveId) pk.selectMove('fast', fastMoveId, 0);
    for (let i = 1; i < arr.length; i++) {
      if (arr[i].match('([A-Z_]+)')) continue;
      if (i < 3) pk.selectMove('charged', chargedOptions(pk)[parseInt(arr[i])], i - 1);
      else pk.selectMove('extra-charged', extraOptions(pk)[parseInt(arr[i])], 2);
    }
    if (arr.length < 4 && pk.extraChargedMovePool.length > 0 && pk.hasThirdChargedMove())
      pk.selectMove('extra-charged', 'none', 2);
    resolved.push({ fast: pk.fastMove ? pk.fastMove.moveId : null,
                    charged: pk.chargedMoves.map(m => m ? m.moveId : null) });
  }

  battle.setNewPokemon(pokes[0], 0, false);
  battle.setNewPokemon(pokes[1], 1, false);
  // h / e come after setNewPokemon: initialize() ends with startHp = stats.hp
  // and would clobber them (Pokemon.js:369-370).
  if (get.h) { const a = get.h.split('-'); pokes[0].setStartHp(parseInt(a[0])); pokes[1].setStartHp(parseInt(a[1])); }
  if (get.e) { const a = get.e.split('-'); pokes[0].setStartEnergy(parseInt(a[0])); pokes[1].setStartEnergy(parseInt(a[1])); }

  if (get.sandbox) {
    battle.setSandboxMode(true);
    const acts = [];
    if (get.a !== undefined && get.a !== '0') {
      for (const tok of get.a.split('-')) {
        const [tS, pS] = tok.split('.'); const turn = parseInt(tS, 10); const p = pS.split('');
        if (p[0] === '1') acts.push(new TimelineAction('charged', parseInt(p[1]), turn, parseInt(p[2]),
          { shielded: p[3] === '1', buffs: p[4] === '1', charge: p[5] ? CHARGE_MULTIPLIERS[parseInt(p[5], 10)] : 1 }));
        else if (p[0] === '2') acts.push(new TimelineAction('wait', parseInt(p[1]), turn, parseInt(p[2]), {}));
      }
    }
    battle.setActions(acts);
  }

  const useLog = []; const origUse = battle.useMove;
  battle.useMove = function (att, def, move, fs_, fb, ch) {
    const b = def.hp; const r = origUse(att, def, move, fs_, fb, ch);
    const pk = battle.getPokemon();
    useLog.push({ turn: battle.getTurns(), actor: att.index, move: move.moveId, hpLost: b - def.hp,
      attEnergy: att.energy, shields: [pk[0].shields, pk[1].shields] });
    return r;
  };
  battle.simulate();
  const pk = battle.getPokemon();
  // Pokemon.js:2124 getBattleRating (via Battle.js:665) -- the number the
  // battle page shows and the one BattleResult.pvpoke_score mirrors. Scale
  // EACH ratio by 500 and then sum; do NOT use Ranker.js:329's
  // floor((health + damage) * 500), which sums first and lands 1 low on
  // exact fractions (e.g. 46/125 + 1 -> 683 instead of 684).
  const score = (a, b) => Math.floor((500 * ((b.stats.hp - b.hp) / b.stats.hp)) + (500 * (a.hp / a.stats.hp)));
  const winner = (pk[0].hp > 0 && pk[1].hp <= 0) ? 0 : ((pk[1].hp > 0 && pk[0].hp <= 0) ? 1 : null);
  process.stdout.write(JSON.stringify({
    rule: get.rule, get, defaultIVs, resolved,
    score: [score(pk[0], pk[1]), score(pk[1], pk[0])], winner, turns: battle.getTurns(),
    hp: [pk[0].hp, pk[1].hp], maxHp: [pk[0].stats.hp, pk[1].stats.hp],
    shields: [pk[0].shields, pk[1].shields], level: [pk[0].level, pk[1].level],
    ivs: [pk[0].ivs, pk[1].ivs], cp: [pk[0].cp, pk[1].cp],
    statBuffs: [pk[0].startStatBuffs, pk[1].startStatBuffs],
    finalStatBuffs: [pk[0].statBuffs, pk[1].statBuffs], useLog,
  }));
}
try { main() } catch (e) { process.stderr.write('ERR: ' + e.message + '\n' + e.stack + '\n'); process.exit(1) }
