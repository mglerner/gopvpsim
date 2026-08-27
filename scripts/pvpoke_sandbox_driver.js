#!/usr/bin/env node
// General headless driver for PvPoke's Battle.js, with SANDBOX action support.
//
// Given a battle spec (two Pokemon + shields + optional starting state) and an
// optional sandbox action string, runs PvPoke's own simulator and prints its
// outcome as JSON.  With no --actions it runs PvPoke's AI (the plain-battle
// baseline); with --actions it runs sandbox mode, where NO AI runs for either
// side and every charged move must be listed.
//
// This is the verification half of pvpoke_sandbox_lib.py: a sandbox URL is only
// trustworthy once this driver, fed the same action string, reproduces our
// engine's score.  Derived from gopvpsim scripts/pvpoke_trace.js (browser shims
// + loader), minus that script's ActionLogic instrumentation.
//
// Usage:
//   node pvpoke_sandbox.js --pvpoke-root <path> --cp <1500|2500|10000>
//     --p1 <speciesId> --p1-fast <MOVE> --p1-charged <MOVE[,MOVE]> --p1-shields <N>
//     --p2 ... (same)
//     [--p1-ivs a/d/s] [--p1-level L] [--p1-bait 0|1|2]
//     [--p1-hp N] [--p1-energy N] [--p1-cooldown MS] [--p1-buffs atk,def]
//     [--p1-shadow-type shadow|purified] [--level-cap N]
//     [--actions '15.100000-19.110000']
//
// Omitting --pN-ivs uses PvPoke's league-default spread for that species.
// Env DMG_TRACE=1 dumps every charged-move damage calculation to stderr.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const CHARGE_MULTIPLIERS = [1, .95, .75, .5, .25];

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) throw new Error('bad arg ' + a);
    out[a.slice(2)] = argv[++i];
  }
  return out;
}
function parseIVs(s) { const p = s.split('/').map(Number); return { atk: p[0], def: p[1], hp: p[2] }; }

// ---------- browser-global shims (PvPoke's JS is written for a page) ----------
function installShims() {
  global.window = { localStorage: { getItem: () => null, setItem: () => {} } };
  global.host = 'localhost'; global.webRoot = ''; global.siteVersion = 0;
  global.settings = { gamemaster: 'gamemaster' };
  global.customData = null; global.customRankingInterface = undefined;
  const chain = new Proxy(function () {}, { get: () => chain, apply: () => chain });
  const $ = function () { return chain; };
  $.ajax = (opts) => {
    global.__pvpoke_ajax_success = opts.success;
    return { always: () => {}, done: () => {}, fail: () => {} };
  };
  $.each = (arr, fn) => {
    if (Array.isArray(arr)) arr.forEach((v, i) => fn(i, v));
    else if (arr && typeof arr === 'object') { for (const k of Object.keys(arr)) fn(k, arr[k]); }
  };
  global.$ = $;
  global.InterfaceMaster = { getInstance: () => ({ init: () => {} }) };
  global.updateFormatSelect = () => {}; global.updateCupSelect = () => {};
  global.gtag = () => {};
}

function evalFile(fp) { vm.runInThisContext(fs.readFileSync(fp, 'utf8'), { filename: fp }); }

function loadPvPoke(root) {
  const jsDir = path.join(root, 'src', 'js');
  for (const rel of ['GameMaster.js', 'battle/DamageCalculator.js',
    'battle/timeline/TimelineAction.js', 'battle/timeline/TimelineEvent.js',
    'battle/actions/ActionLogic.js', 'pokemon/Player.js', 'pokemon/Pokemon.js',
    'battle/Battle.js']) evalFile(path.join(jsDir, rel));
}

function bootGameMaster(root) {
  const data = JSON.parse(fs.readFileSync(path.join(root, 'src', 'data', 'gamemaster.json'), 'utf8'));
  global.__pvpoke_gm_data = data;
  const gm = GameMaster.getInstance();
  global.__pvpoke_ajax_success(data);
  if (!gm.data || !gm.data.pokemon) throw new Error('gamemaster not loaded');
  return gm;
}

function buildPokemon(battle, spec) {
  const poke = new Pokemon(spec.species, 0, battle);
  if (!poke.speciesId) throw new Error('unknown species: ' + spec.species);
  poke.initialize(battle.getCP());
  if (spec.ivs) {
    // autoLevel walks the level down until CP <= cap after each setIV, which is
    // what we want when overriding the rank-1 default that initialize() loaded.
    poke.autoLevel = true;
    poke.setIV('atk', spec.ivs.atk); poke.setIV('def', spec.ivs.def); poke.setIV('hp', spec.ivs.hp);
    if (spec.level !== undefined) poke.setLevel(spec.level, false);
  }
  poke.selectMove('fast', spec.fast);
  for (let i = 0; i < spec.charged.length; i++) poke.selectMove('charged', spec.charged[i], i);
  while (poke.chargedMoves.length > spec.charged.length)
    poke.selectMove('charged', 'none', poke.chargedMoves.length - 1);
  poke.setShields(spec.shields);
  poke.baitShields = spec.bait;
  if (spec.shadowType && spec.shadowType !== 'normal') poke.setShadowType(spec.shadowType);
  return poke;
}

// Starting HP / energy / buffs / cooldown MUST be applied after
// battle.setNewPokemon(), whose initialize() ends with
// `this.hp = this.stats.hp; this.startHp = this.hp;` (Pokemon.js:369-370) and
// silently clobbers setStartHp.  Getting this wrong makes the verification
// loop green against a fight the link does not describe.
function applyStartState(poke, spec) {
  if (spec.buffs) poke.setStartBuffs(spec.buffs);
  if (spec.hp !== undefined) poke.setStartHp(spec.hp);
  if (spec.energy !== undefined) poke.setStartEnergy(spec.energy);
  if (spec.cooldown !== undefined) poke.startCooldown = spec.cooldown;
}

// Pokemon.js:2124 getBattleRating (via Battle.js:665) -- the number the battle
// page shows and the one BattleResult.pvpoke_score mirrors. Scale EACH ratio by
// 500 and then sum; do NOT use Ranker.js:329's floor((health + damage) * 500),
// which sums first and lands 1 low on exact fractions (e.g. 46/125 + 1 -> 683
// instead of 684).
function score(poke, opp) {
  return Math.floor((500 * ((opp.stats.hp - opp.hp) / opp.stats.hp)) + (500 * (poke.hp / poke.stats.hp)));
}

function parseActionStr(actionStr) {
  const acts = [];
  if (actionStr === '0') return acts;
  for (const tok of actionStr.split('-')) {
    const [tStr, pStr] = tok.split('.');
    const turn = parseInt(tStr, 10);
    const p = pStr.split('');
    if (p[0] === '1') {
      acts.push(new TimelineAction('charged', parseInt(p[1]), turn, parseInt(p[2]), {
        shielded: p[3] === '1', buffs: p[4] === '1',
        charge: p[5] ? CHARGE_MULTIPLIERS[parseInt(p[5], 10)] : 1,
      }));
    } else if (p[0] === '2') {
      acts.push(new TimelineAction('wait', parseInt(p[1]), turn, parseInt(p[2]), {}));
    } else {
      throw new Error('unknown action type in token ' + tok);
    }
  }
  return acts;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const root = args['pvpoke-root'];
  const cp = parseInt(args.cp, 10);
  const mk = (n) => ({
    species: args[n], fast: args[n + '-fast'],
    charged: args[n + '-charged'].split(',').filter(Boolean),
    ivs: args[n + '-ivs'] ? parseIVs(args[n + '-ivs']) : null,
    level: args[n + '-level'] ? parseFloat(args[n + '-level']) : undefined,
    shields: parseInt(args[n + '-shields'], 10),
    bait: args[n + '-bait'] !== undefined ? parseInt(args[n + '-bait'], 10) : 1,
    hp: args[n + '-hp'] !== undefined ? parseInt(args[n + '-hp'], 10) : undefined,
    energy: args[n + '-energy'] !== undefined ? parseInt(args[n + '-energy'], 10) : undefined,
    cooldown: args[n + '-cooldown'] !== undefined ? parseInt(args[n + '-cooldown'], 10) : undefined,
    buffs: args[n + '-buffs'] ? args[n + '-buffs'].split(',').map(Number) : undefined,
    shadowType: args[n + '-shadow-type'],
  });
  // Keep stdout pure JSON; PvPoke chatters on console.log.
  console.log = (...a) => { process.stderr.write(a.join(' ') + '\n'); };

  installShims(); loadPvPoke(root); bootGameMaster(root);

  const battle = new Battle();
  battle.setCP(cp);
  if (args['level-cap'] !== undefined) battle.setLevelCap(parseInt(args['level-cap'], 10));
  const s1 = mk('p1'), s2 = mk('p2');
  const p1 = buildPokemon(battle, s1);
  const p2 = buildPokemon(battle, s2);
  battle.setNewPokemon(p1, 0, true);
  battle.setNewPokemon(p2, 1, true);
  applyStartState(p1, s1);
  applyStartState(p2, s2);

  let actionStr = null;
  if (args.actions !== undefined) {
    actionStr = args.actions;
    // setSandboxMode(true) seeds actions from the (empty) timeline; setActions
    // then installs ours.  Order matters.
    battle.setSandboxMode(true);
    battle.setActions(parseActionStr(actionStr));
  }

  const decisionLog = [];
  const origLog = battle.logDecision.bind(battle);
  battle.logDecision = (pokemon, string) => {
    decisionLog.push({
      turn: battle.getTurns(),
      name: pokemon ? pokemon.speciesName : null,
      index: pokemon ? pokemon.index : null, msg: string,
    });
    return origLog(pokemon, string);
  };

  if (process.env.DMG_TRACE) {
    const od = DamageCalculator.damage.bind(DamageCalculator);
    DamageCalculator.damage = function (att, def, move, charge, mode, players) {
      const r = od(att, def, move, charge, mode, players);
      if (move.category === 'charged') process.stderr.write(
        `DMG t=${battle.getTurns()} ${att.activeFormId} ${move.moveId} `
        + `atk=${att.getEffectiveStat(0)} def=${def.getEffectiveStat(1)} -> ${r}\n`);
      return r;
    };
  }

  // Per-move trace: HP/energy/shield/buff state after every move resolution.
  const useLog = [];
  const origUse = battle.useMove;
  battle.useMove = function (att, def, move, fs, fb, ch) {
    const before = def.hp;
    const r = origUse(att, def, move, fs, fb, ch);
    const pk = battle.getPokemon();
    useLog.push({
      turn: battle.getTurns(), actor: att.index, move: move.moveId,
      hpLost: before - def.hp, attHp: att.hp, defHp: def.hp,
      attEnergy: att.energy, shields: [pk[0].shields, pk[1].shields],
      buffs: [pk[0].statBuffs.slice(), pk[1].statBuffs.slice()],
      forms: [pk[0].activeFormId, pk[1].activeFormId],
    });
    return r;
  };

  battle.simulate();
  const poke = battle.getPokemon();
  let winner;
  if (poke[0].hp > 0 && poke[1].hp <= 0) winner = 0;
  else if (poke[1].hp > 0 && poke[0].hp <= 0) winner = 1;
  else winner = null;   // both down: PvPoke calls that a tie

  process.stdout.write(JSON.stringify({
    actionStr, sandbox: actionStr !== null,
    score: [score(poke[0], poke[1]), score(poke[1], poke[0])],
    winner, turns: battle.getTurns(),
    hp: [poke[0].hp, poke[1].hp], maxHp: [poke[0].stats.hp, poke[1].stats.hp],
    shields: [poke[0].shields, poke[1].shields],
    ivs: [poke[0].ivs, poke[1].ivs],
    statBuffs: [poke[0].startStatBuffs, poke[1].startStatBuffs],
    shadowType: [poke[0].shadowType, poke[1].shadowType],
    level: [poke[0].level, poke[1].level],
    cp: [poke[0].cp, poke[1].cp],
    stats: [poke[0].stats, poke[1].stats],
    fastPool: [poke[0].fastMovePool.map(m => m.moveId), poke[1].fastMovePool.map(m => m.moveId)],
    chargedPool: [poke[0].chargedMovePool.map(m => m.moveId), poke[1].chargedMovePool.map(m => m.moveId)],
    decisionLog, useLog,
  }, null, 1) + '\n');
}

try { main(); } catch (e) { process.stderr.write('ERR: ' + e.message + '\n' + e.stack + '\n'); process.exit(1); }
