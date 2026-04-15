#!/usr/bin/env node
// Headless harness that loads PvPoke's browser JS under Node, runs
// Battle.simulate() on an arbitrary 1v1 matchup, and emits JSON with the
// PvPoke score, winner, turn count, and decisionLog. ActionLogic DP-plan
// probes are wired in a follow-up pass.
//
// See /Users/mglerner/.claude/plans/parsed-greeting-river.md for the full
// plan this is implementing.

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// ---------- CLI ----------

const USAGE = `Usage: node scripts/pvpoke_trace.js \\
  --pvpoke-root <path>                   PvPoke clone root (required)
  --p1 <speciesId>     --p2 <speciesId>
  --p1-fast <moveId>   --p2-fast <moveId>
  --p1-charged <id1[,id2]>   --p2-charged <id1[,id2]>
  --p1-ivs <a/d/s>     --p2-ivs <a/d/s>
  --p1-level <L>       --p2-level <L>
  --p1-shields <N>     --p2-shields <N>
  --cp <1500|2500|10000>

Writes JSON to stdout: {score, winner, turns, decisionLog, dpPlans}.
`;

function parseArgs(argv) {
  const out = {};
  const flags = new Set([
    '--pvpoke-root', '--p1', '--p2', '--p1-fast', '--p2-fast',
    '--p1-charged', '--p2-charged', '--p1-ivs', '--p2-ivs',
    '--p1-level', '--p2-level', '--p1-shields', '--p2-shields', '--cp',
  ]);
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--help' || a === '-h') { out.help = true; continue; }
    if (!flags.has(a)) { throw new Error(`unknown arg: ${a}`); }
    const v = argv[++i];
    if (v === undefined) { throw new Error(`missing value for ${a}`); }
    out[a.slice(2)] = v;
  }
  return out;
}

function requireArg(args, name) {
  if (args[name] === undefined) { throw new Error(`missing --${name}`); }
  return args[name];
}

function parseIVs(s) {
  const parts = s.split('/').map(Number);
  if (parts.length !== 3 || parts.some(n => Number.isNaN(n))) {
    throw new Error(`bad IVs "${s}", expected a/d/s`);
  }
  return { atk: parts[0], def: parts[1], hp: parts[2] };
}

function parseCharged(s) {
  return s.split(',').map(x => x.trim()).filter(Boolean);
}

// ---------- Browser-global shims ----------

// PvPoke's browser JS expects these to exist at eval time. None of the
// code paths we exercise (Battle.simulate and its callees) actually use
// them, but the files reference them at top level.
function installShims() {
  global.window = {
    localStorage: { getItem: () => null, setItem: () => {} },
  };
  global.host = 'localhost';
  global.webRoot = '';
  global.siteVersion = 0;
  global.settings = { gamemaster: 'gamemaster' };
  global.customData = null;
  global.customRankingInterface = undefined;
  // Minimal jQuery surface. $ is callable (returns a no-op chainable that
  // swallows DOM operations) with .ajax/.each as statics. GameMaster.js
  // calls both $(selector) for DOM manipulation and $.ajax for data load.
  const chain = new Proxy(function(){}, {
    get: () => chain,
    apply: () => chain,
  });
  const $ = function() { return chain; };
  // Stash the success callback; bootGameMaster fires it AFTER
  // createInstance() finishes attaching methods to `object`. In the
  // browser $.ajax is async so createSearchMaps/etc are already defined
  // by the time success runs — we mimic that ordering manually.
  $.ajax = (opts) => {
    global.__pvpoke_ajax_success = opts.success;
    return { always: () => {}, done: () => {}, fail: () => {} };
  };
  $.each = (arr, fn) => {
    if (Array.isArray(arr)) arr.forEach((v, i) => fn(i, v));
    else if (arr && typeof arr === 'object') {
      for (const k of Object.keys(arr)) fn(k, arr[k]);
    }
  };
  global.$ = $;
  // Bare-minimum InterfaceMaster: getInstance().init is called in the
  // gamemaster load callback. We want it to be a no-op so we don't pull
  // in any DOM-bound interface code.
  global.InterfaceMaster = {
    getInstance: () => ({ init: () => {} }),
  };
  global.updateFormatSelect = () => {};
  global.updateCupSelect = () => {};
}

// ---------- PvPoke loader ----------

function evalFile(filePath) {
  const src = fs.readFileSync(filePath, 'utf8');
  vm.runInThisContext(src, { filename: filePath });
}

function evalSource(src, filename) {
  vm.runInThisContext(src, { filename });
}

// String-inject DP-plan probes into ActionLogic.js. Anchored on the
// exact `finalState = ...` lines so that PvPoke drift shows up as a
// loud "anchor not found" error rather than silently missing a probe.
function instrumentActionLogic(src) {
  // Insert a trace hook inside the terminal-state detection for debug.
  const termAnchor = '\t\t\t\tstateList.push(currState);';
  if (src.includes(termAnchor)) {
    src = src.replace(
      termAnchor,
      `\t\t\t\tif (typeof global.__pvpoke_term_trace === 'function') { global.__pvpoke_term_trace(battle, poke, currState); }\n${termAnchor}`
    );
  }
  const probes = [
    {
      anchor: '\t\t\tfinalState = stateList[0];',
      tag: 'single',
    },
    {
      anchor: '\t\t\tfinalState = bestPlan;',
      tag: 'needsBoost',
    },
    {
      anchor: '\t\t\tfinalState = stateList[stateList.length - 1];',
      tag: 'default',
    },
  ];
  for (const p of probes) {
    if (!src.includes(p.anchor)) {
      throw new Error(`instrumentation anchor not found: ${p.anchor}`);
    }
    src = src.replace(
      p.anchor,
      `${p.anchor}\n\t\t\tglobal.__pvpoke_dp_trace(battle, poke, opponent, finalState, '${p.tag}'); // TRACE:`
    );
  }
  // Also trace the final thrown move right before the TimelineAction
  // is constructed (captures all post-assignment bandaid adjustments).
  const throwAnchor = '\t\taction = new TimelineAction(\n\t\t\t"charged",';
  if (!src.includes(throwAnchor)) {
    throw new Error('instrumentation anchor not found: charged TimelineAction');
  }
  src = src.replace(
    throwAnchor,
    `\t\tglobal.__pvpoke_dp_trace(battle, poke, opponent, finalState, 'thrown'); // TRACE:\n${throwAnchor}`
  );
  return src;
}

function loadPvPoke(pvpokeRoot) {
  const jsDir = path.join(pvpokeRoot, 'src', 'js');
  // ActionLogic.js gets loaded via text+instrument; the rest are plain.
  const plainFiles = [
    'GameMaster.js',
    'battle/DamageCalculator.js',
    'battle/timeline/TimelineAction.js',
    'battle/timeline/TimelineEvent.js',
    'pokemon/Player.js',
    'pokemon/Pokemon.js',
    'battle/Battle.js',
  ];
  const actionLogicPath = path.join(jsDir, 'battle/actions/ActionLogic.js');
  evalFile(path.join(jsDir, plainFiles[0]));                          // GameMaster.js
  evalFile(path.join(jsDir, plainFiles[1]));                          // DamageCalculator.js
  const alRaw = fs.readFileSync(actionLogicPath, 'utf8');
  evalSource(instrumentActionLogic(alRaw), actionLogicPath);
  for (const rel of plainFiles.slice(2)) {
    evalFile(path.join(jsDir, rel));
  }
}

function bootGameMaster(pvpokeRoot) {
  const gmJson = path.join(pvpokeRoot, 'src', 'data', 'gamemaster.json');
  const data = JSON.parse(fs.readFileSync(gmJson, 'utf8'));
  // Prime the shim so $.ajax can hand it to GameMaster's success callback.
  global.__pvpoke_gm_data = data;
  // getInstance() constructs `object`, kicks off $.ajax (which the shim
  // queues), then attaches all the methods (createSearchMaps, etc) onto
  // `object` before returning. Now we can fire the stashed success
  // callback against a fully-formed object.
  const gm = GameMaster.getInstance();
  if (typeof global.__pvpoke_ajax_success !== 'function') {
    throw new Error('GameMaster did not request data via $.ajax');
  }
  global.__pvpoke_ajax_success(data);
  if (!gm.data || !gm.data.pokemon) {
    throw new Error('GameMaster did not populate data after ajax callback');
  }
  return gm;
}

// ---------- Matchup setup ----------

function buildPokemon(battle, spec) {
  const poke = new Pokemon(spec.species, 0, battle);
  if (!poke.speciesId) {
    throw new Error(`unknown species: ${spec.species}`);
  }
  poke.initialize(battle.getCP());
  // autoLevel=true makes each setIV walk the level down until CP<=cap,
  // which is what we want when overriding the default rank-1 IVs that
  // initialize() just loaded. Without this, setIV re-runs initialize()
  // at the previous (default-IV) level and CP ends up over the cap.
  poke.autoLevel = true;
  poke.setIV('atk', spec.ivs.atk);
  poke.setIV('def', spec.ivs.def);
  poke.setIV('hp', spec.ivs.hp);
  if (spec.level !== undefined) {
    poke.setLevel(spec.level, false);
  }
  poke.selectMove('fast', spec.fast);
  for (let i = 0; i < spec.charged.length; i++) {
    poke.selectMove('charged', spec.charged[i], i);
  }
  // initialize() seeds chargedMoves with up to 2 defaults from the pool.
  // If the caller wants only 1 charged move, we must explicitly drop the
  // trailing slot by passing id="none" (Pokemon.js:927 clears the slot).
  while (poke.chargedMoves.length > spec.charged.length) {
    poke.selectMove('charged', 'none', poke.chargedMoves.length - 1);
  }
  poke.setShields(spec.shields);
  return poke;
}

// ---------- Score (mirrors Ranker.js:325-332) ----------

function pvpokeScore(poke, opp) {
  const health = poke.hp / poke.stats.hp;
  const damage = (opp.stats.hp - opp.hp) / opp.stats.hp;
  return Math.floor((health + damage) * 500);
}

// ---------- Main ----------

function main() {
  let args;
  try { args = parseArgs(process.argv.slice(2)); }
  catch (e) { process.stderr.write(e.message + '\n\n' + USAGE); process.exit(2); }
  if (args.help) { process.stdout.write(USAGE); return; }

  const pvpokeRoot = requireArg(args, 'pvpoke-root');
  const cp = parseInt(requireArg(args, 'cp'), 10);

  const spec1 = {
    species: requireArg(args, 'p1'),
    fast:    requireArg(args, 'p1-fast'),
    charged: parseCharged(requireArg(args, 'p1-charged')),
    ivs:     parseIVs(requireArg(args, 'p1-ivs')),
    level:   args['p1-level'] ? parseFloat(args['p1-level']) : undefined,
    shields: parseInt(requireArg(args, 'p1-shields'), 10),
  };
  const spec2 = {
    species: requireArg(args, 'p2'),
    fast:    requireArg(args, 'p2-fast'),
    charged: parseCharged(requireArg(args, 'p2-charged')),
    ivs:     parseIVs(requireArg(args, 'p2-ivs')),
    level:   args['p2-level'] ? parseFloat(args['p2-level']) : undefined,
    shields: parseInt(requireArg(args, 'p2-shields'), 10),
  };

  // Route PvPoke's console.log to stderr so stdout stays pure JSON.
  console.log = (...args) => { process.stderr.write(args.join(' ') + '\n'); };

  installShims();
  loadPvPoke(pvpokeRoot);
  bootGameMaster(pvpokeRoot);

  const battle = new Battle();
  battle.setCP(cp);

  const p1 = buildPokemon(battle, spec1);
  const p2 = buildPokemon(battle, spec2);

  battle.setNewPokemon(p1, 0, true);
  battle.setNewPokemon(p2, 1, true);

  // Wrap logDecision before simulate() to capture the turn-by-turn log.
  // Battle.js:1950 defines logDecision = function(pokemon, string){...};
  const decisionLog = [];
  const origLog = battle.logDecision.bind(battle);
  battle.logDecision = (pokemon, string) => {
    decisionLog.push({
      turn:    battle.getTurns(),
      actor:   pokemon ? pokemon.speciesId : null,
      name:    pokemon ? pokemon.speciesName : null,
      index:   pokemon ? pokemon.index : null,
      msg:     string,
    });
    return origLog(pokemon, string);
  };

  // DP probes: ActionLogic.js was string-injected in loadPvPoke to call
  // global.__pvpoke_dp_trace at each finalState assignment and before
  // each charged-move throw. Each entry captures the planned move
  // sequence so we can localize DP plan-selection divergences.
  const dpPlans = [];
  const termLog = [];
  global.__pvpoke_term_trace = (battle, poke, state) => {
    termLog.push({
      turn: battle.getTurns(),
      actor: poke ? poke.speciesId : null,
      stateTurn: state.turn,
      energy: state.energy,
      oppHealth: state.oppHealth,
      moves: (state.moves || []).map(m => m.moveId),
    });
  };
  global.__pvpoke_dp_trace = (battle, poke, opponent, finalState, tag) => {
    dpPlans.push({
      turn:      battle.getTurns(),
      actor:     poke ? poke.speciesId : null,
      index:     poke ? poke.index : null,
      tag,
      energy:    finalState ? finalState.energy : null,
      oppHealth: finalState ? finalState.oppHealth : null,
      oppShields: finalState ? finalState.oppShields : null,
      moves:     finalState && finalState.moves
                 ? finalState.moves.map(m => ({
                     id: m.moveId, energy: m.energy, dpe: m.dpe,
                     damage: m.damage,
                   }))
                 : [],
      pokeEnergy: poke ? poke.energy : null,
      pokeHP:     poke ? poke.hp : null,
      oppHP:      opponent ? opponent.hp : null,
    });
  };

  battle.simulate();

  const poke = battle.getPokemon();
  const score = [pvpokeScore(poke[0], poke[1]), pvpokeScore(poke[1], poke[0])];
  const winner = poke[0].hp > 0 ? 0 : 1;
  const turns = battle.getTurns();

  // Derive a Python-compatible chargedLog by classifying each "uses X"
  // entry as fast vs charged via the move catalog, pairing each charged
  // use with the defender's immediate "blocks with a shield" if any.
  const chargedNames = new Set();
  for (const p of poke) {
    for (const m of (p.chargedMoves || [])) chargedNames.add(m.name);
  }
  const chargedLog = [];
  for (let i = 0; i < decisionLog.length; i++) {
    const e = decisionLog[i];
    const m = e.msg.match(/^\s*uses\s+(.+)$/);
    if (!m) continue;
    const moveName = m[1];
    if (!chargedNames.has(moveName)) continue;
    let shielded = false;
    for (let j = i + 1; j < decisionLog.length && j <= i + 4; j++) {
      if (decisionLog[j].msg.includes('blocks with a shield')) {
        shielded = true; break;
      }
    }
    chargedLog.push(`${e.name}: ${moveName}${shielded ? ' (shielded)' : ''}`);
  }

  process.stdout.write(JSON.stringify({
    score, winner, turns, chargedLog, decisionLog, dpPlans, termLog,
  }, null, 2) + '\n');
}

try { main(); }
catch (e) {
  process.stderr.write(`pvpoke_trace error: ${e.message}\n${e.stack || ''}\n`);
  process.exit(1);
}
