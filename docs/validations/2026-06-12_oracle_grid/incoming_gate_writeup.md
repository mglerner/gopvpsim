# Incoming-gate deviation FALSIFIED — extra selfDefenseDebuffing routing in pvpoke_simulate_shield (2026-06-12, evidence only, NO code changed)

**Status: deviation falsified by trace + probe. Third instance of the
2026-06-11 pattern (after the OMT self-debuffing KO-override and the
bait-wait `not cm_self_debuf[1]` hold): a pre-existing extra condition
the reference lacks, carrying a plausible comment, producing real
margin errors. Fix is a one-line removal, deferred to a post-batch
session (engine is frozen for tonight's dive batch — cache hash).**

## The gate (ours)

`src/gopvpsim/battle.py:200` in `pvpoke_simulate_shield`:

    use_heuristic_incoming = sb_subroute or self_def_debuffing

where `self_def_debuffing = move.get('selfDefenseDebuffing', False)`
(battle.py:187) is a property of the **incoming** move. When it is
true, the defender's shield decision is routed through `would_shield`
(battle.py:201-202) instead of the simulate-mode default
`use_shield = True`.

Introduced with `pvpoke_simulate_shield` itself in commit `ead46c1`
(2026-04-15, "Fix buff meter, add pvpoke_simulate_shield, add trace
flags"). The docstring (battle.py:166-170) claims: "This mirrors
Battle.js: useShield = true, then overridden for move.selfBuffing and
move.selfDefensiveDebuffing" — the second half of that claim is
**false** for the incoming move.

## The reference (PvPoke)

`Battle.js:1083-1101` (local clone @ 9b7407782, the same code
`scripts/pvpoke_trace.js` executes):

    var useShield = true;                                   // 1084
    var shieldDecision = ActionLogic.wouldShield(...);      // 1087
    // "Don't shield early PUP's, Acid Sprays, or similar moves"
    if( (! sandbox) && move.buffs && move.selfBuffing){     // 1090
        if( (move.buffTarget == "self" && move.buffs[0] > 0) ||
            (move.buffTarget == "opponent" && move.buffs[1] < 0)){
            useShield = shieldDecision.value;
        }
        if( move.buffTarget == "both" && ... ){ useShield = shieldDecision.value; }
    }

The ONLY occurrence of `selfDefenseDebuffing` in Battle.js is line
1105, and it tests `defender.bestChargedMove.selfDefenseDebuffing` —
the **defender's own** move (the "save shields for my post-debuff
fragility window" branch we already ported 2026-04-15). The incoming
move's selfDefenseDebuffing flag routes nothing in the reference:
`git log -S 'move.selfDefenseDebuffing' -- src/js/battle/Battle.js`
in the clone returns no commits — the condition never existed there.

Note: a self-DEF-debuffing nuke like Superpower is NOT `selfBuffing`
(GameMaster.js:873 sets selfBuffing only for positive self-buffs and
guaranteed opponent debuffs), so Battle.js:1090 does not catch it and
PvPoke simply always-shields it. Our gate re-routes exactly that
class of move.

## Carrier moves (gate-only routing, full gamemaster)

BRAVE_BIRD [0,-3], CLANGING_SCALES [0,-1], CLOSE_COMBAT [0,-2],
DRAGON_ASCENT [0,-1], HIGH_JUMP_KICK [0,-4], MIND_BLOWN [0,-4],
SUPER_POWER [-1,-1], VOLT_TACKLE [0,-1], V_CREATE [0,-3],
WILD_CHARGE [0,-2]. None of these is routed by the reference's
Battle.js:1090 sub-filter (none has a positive self-buff or opponent
debuff). Every shielded defender facing these moves is exposed.

## Decisive trace — Tinkaton vs Malamar, GL, [1,0]

Defaults: Tinkaton FAIRY_WIND + GIGATON_HAMMER/BULLDOZE, defaultIVs
L25 4/15/14; Malamar PSYWAVE + SUPER_POWER/FOUL_PLAY, defaultIVs
L23.5 4/15/15. Tinkaton 1 shield, Malamar 0.

OURS (baseline, `trace_shields=True`), the decision at T20:

    T 20: shield(Tinkaton sh=1 vs SUPER_POWER [incoming selfDefDebuff]): → wouldShield=False

(`wouldShield(Tinkaton hp=105 sh=1, Malamar→SUPER_POWER dmg=46 ...):
fast_dmg=2 cycle=23 → False [none]` — Psywave pressure is far too low
for any wouldShield clause to fire.) Tinkaton TANKS the Superpower.
Result: **702/297**, chargedLog
`['Tinkaton: Gigaton Hammer', 'Malamar: Superpower']`.

PVPOKE (harness, same cell): Tinkaton shields. Result: **861/138**,
chargedLog `['Tinkaton: Gigaton Hammer', 'Malamar: Superpower (shielded)']`.
Its decisionLog never consults wouldShield for this decision —
useShield stays at the line-1084 default.

PROBE (`/tmp/oracle_grid_expansion/probe_incoming_gate.py`, passes a
reference-exact policy through simulate()'s pluggable
`shield_policy_{0,1}` kwargs — zero engine edits): with the single
condition removed, our cell becomes **861/138** with chargedLog
byte-identical to PvPoke.

## Score impact (GL top-20 grid, 3420 cells, results in /tmp/oracle_grid_expansion/)

Re-running every cell sim-side with the reference-exact policy
against the stored harness ground truth:

    baseline:  3086/3420 exact
    patched:   3098/3420 exact   (+12 fixed, 0 broken)

The 12 fixed cells are exactly the cells where the gate is reachable
in this pool (Malamar = only Superpower carrier; defender must hold
shields): tinkaton-vs-malamar [1,0] [1,1] [1,2] [2,0] [2,1] [2,2] and
the mirror-image malamar-vs-tinkaton [0,1] [0,2] [1,1] [1,2] [2,1]
[2,2]. Margin error up to **±159** (e.g. [1,0]: ours 702 vs PvPoke
861) with no winner flips in this pool — but a 159-point margin error
is far above the breakpoint-analysis noise floor, and HJK/Brave Bird
users in other leagues can plausibly flip winners.

## Divergence-policy verdict (CLAUDE.md three questions)

1. *Does PvPoke produce a demonstrably better outcome?* Yes. Shielding
   the incoming Superpower keeps Tinkaton at +159. Our gate only
   declines the shield when `would_shield` says the defender can
   afford to tank — but "can survive" is not "should tank": the
   defender burns 46 HP to save a shield it never gets better value
   for. Same failure shape as the OMT override (traded real HP for a
   theoretical consideration).
2. *Does our deviation have a defensible reason?* No trace or probe
   ever supported it; the comment claims reference parity that the
   reference does not contain. It is a port error, not a deviation.
3. *Would matching PvPoke make us worse for the use case?* No —
   breakpoint/bulkpoint work needs faithful margins; 159-point margin
   noise on every shielded self-def-debuff nuke is strictly worse.

**Recommendation (post-batch fix session):**
- battle.py:200 → `use_heuristic_incoming = sb_subroute` (and drop
  `self_def_debuffing` from line 187 and the trace tag at 204-209).
- Re-run the 153-cell audit + full suite + benchmark; expect only the
  12 grid cells (and any audit fixtures involving these carriers) to
  move toward PvPoke.

## Related findings queued for the same session (probe-verified / flagged)

1. **`_estimate_best_cm` family (probe-verified, 38 more cells).** The
   defender-bestCM branch (battle.py:214-215) enters on our max-DPE
   estimate, but PvPoke's `selectBestChargedMove` (Pokemon.js:790-822)
   runs AFTER the activeChargedMoves shuffle and has a literal
   `move.moveId != "SUPER_POWER"` carve-out plus .03/.3 dpe
   thresholds — so PvPoke-Malamar's bestChargedMove is FOUL PLAY, the
   branch never fires, and PvPoke always-shields where we route to
   wouldShield. Probe (`probe_bestcm_family.py`: faithful
   selectBestChargedMove port in the policy): +38 cells fixed, 0
   broken (3086 → 3136 with both patches). Max |d| 205
   (quagsire_shadow-vs-malamar [1,1]).
2. **bandaid[910] index deltas (flagged, unprobed).** Our port
   (battle.py:1613-1627) checks `not cm_self_buff[first_idx]` where
   ActionLogic.js:930 checks `! poke.activeChargedMoves[0].selfBuffing`,
   and estimates the opponent's best move by max damage where PvPoke
   uses `opponent.bestChargedMove`. Same shape (subtly different
   condition vs reference); no grid cell pinned to it yet.
3. **Shadow CMP family (204 cells, signature-tagged — see
   grid_summary.md).** Our `.atk` folds the shadow ×1.2
   (pokemon.py:195) and battle.py compares `.atk` everywhere
   (use_priority battle.py:2312, action sort 2405/2432, OMT 677,
   wouldShield-cycle 241, TTL 372/397/459, DP 1038); PvPoke compares
   shadow-free `stats.atk` (Battle.js:255/831/1116,
   ActionLogic.js:10/106/181/307 — shadowAtkMult lives only in
   DamageCalculator/getEffectiveStat). Consequences: base-vs-shadow
   same-IV mirrors have EQUAL stats.atk in PvPoke → usePriority=false
   → a charged-fainted mon's same-turn charged move stays valid
   (Battle.js:454/471) → mutual-KO 500/500 draws (we produce a
   winner); and cross-species CMP order flips wherever the ×1.2
   changes the comparison (e.g. quagsire_shadow vs feraligatr [0,0]:
   PvPoke decisionLog shows Feraligatr's Hydro Cannon winning CMP at
   T11; ours fires Quagsire first; winner flips). This one needs its
   own design discussion: matching PvPoke is NOT obviously right for
   the real game (live-game CMP is widely believed to ignore the
   shadow bonus, which would make PvPoke correct — verify before
   porting).
