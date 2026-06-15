# Forretress DP plan-order divergence — localized (2026-06-12)

Cells: `corsola_galarian <-> forretress` [1,1]/[1,2] (4 cells, |d| 159/117)
and `forretress <-> kingdra` [1,1]/[1,2]/[2,2] (8 cells, |d| 82/25/8 + 2
log-only), the top clusters among the 80 UNKNOWN cells in
`userdata/oracle_grid_2026-06-12/`.

## Verdict

**(b) NEW mechanism — post-DP bandaid input freshness.** NOT the
documented near-KO bandaid[866]/[885] family: in the failing cells
`has_deb=False` (Sand Tomb debuffs the *opponent*, it is not
selfDebuffing), the near-KO DP plans are **identical on both sides**
([SAND_TOMB, ROCK_TOMB] at the divergent decision), and bandaid[866]
never executes. The divergence is in the *inputs* the post-DP bandaid
chain reads:

- **Ours** feeds the bandaids `cm_dpe` / `cm_dmgs` from
  `_ensure_dp_cache`, which is rebuilt per (opponent, stat stages) —
  i.e. damage and dpe are **fresh at the current stat stages**
  (battle.py:1019-1030, comment + cache fetch).
- **PvPoke** feeds them cached move properties: `move.dpe` is written
  ONLY at battle init (Pokemon.js:792/796, the inline best-CM loop at
  the end of `resetMoves`, called from `Pokemon.reset`,
  Pokemon.js:1848; also initializeMove Pokemon.js:845) and is **never
  refreshed mid-battle**; `move.damage` is refreshed only
  opportunistically (initializeMove Pokemon.js:831-839 at init; OMT
  side effects ActionLogic.js:320 — gated on `opponent.shields == 0` —
  and ActionLogic.js:336 — refreshes the *opponent's* moves when the
  deciding mon runs OMT; wouldShield ActionLogic.js:1121). The two
  properties visibly desync: PvPoke's own dpPlans dump at
  kingdra-fight T22 shows SAND_TOMB `damage=28` (fresh, post-debuff)
  alongside `dpe=0.575` (stale root value 23/40).

The trigger in every failing cell is **Forretress's Sand Tomb landing
its guaranteed opponent-def debuff** (debuffs apply through shields).
After the stage change, our ratios move; PvPoke's don't; both cells
straddle the bandaid chain's hard 1.5 thresholds.

## Cell 1: corsola_galarian <-> forretress [1,1] (|d| 159)

Both engines reach an **identical state** at T26: Forretress E=56,
HP=71; Corsola HP=78, 1 shield, def stage -1 (from the unshielded T21
Sand Tomb). Both DPs output plan [SAND_TOMB, ROCK_TOMB].

- **PvPoke** (trace `scratch_oracle_grid/traces/corsola_galarian__forretress__1v1.json`):
  decideLog T26 `return_action` line 995 (= final post-DP throw,
  ActionLogic.js:993); decisionLog: *"uses Sand Tomb because it thinks
  that using 1 moves afterwards is the best plan"* / *"wants to use
  Rock Tomb after it uses Sand Tomb"*. The "Don't bait if the opponent
  won't shield" gate (ActionLogic.js:856-864) computes
  `dpeRatio = (RT.damage/50)/(ST.damage/40)` from **stale** damages
  18/33 (dpPlans T26 confirms; OMT's poke-side refresh at :320 was
  gated out because Corsola held a shield) → **1.4667 < 1.5** → no
  override → throws Sand Tomb. Corsola shields it; debuff still
  applies (def -2); RT later hits for 50.
- **Ours** (sys.settrace line capture, `linetrace_out.txt`): execution
  enters battle.py:1502-1507 and **line 1507 `first_idx = 1`
  executes** — the same gate, but with stage-fresh damages 22/42:
  `dpe ratio = 0.84/0.55 = 1.5273 > 1.5`, `would_shield(RT) = False`
  → override → throws **Rock Tomb**. Corsola shields it (no debuff —
  RT has none), and the fight unspools differently.

Decisive trace excerpt (ours, trace_dp):

    T 26: DP-trace[Forretress]: raw plan first=SAND_TOMB max_dmg=ROCK_TOMB has_deb=False turn=14 hp=-5 shields=0 iters=7
    T 26: DP[near-ko]: Forretress fires ROCK_TOMB (energy=56, plan_first=SAND_TOMB max_dmg=ROCK_TOMB)

Probe numbers (`probe_dpe.py`): ours cms=[ST,RT], dmgs=[22,42],
dpe=[0.55,0.84], ratio 1.5273, would_shield(RT)=False; PvPoke stale
(33/50)/(18/40)=1.4667.

## Cell 2: forretress <-> kingdra [1,1] (and [1,2]/[2,2])

First observable divergence at Forretress E=40 (PvPoke T22): the
**bait-wait gate + its selfBuffing exemption**
(ActionLogic.js:838-853 / battle.py:1471-1485).

- **PvPoke** (clone instrumented with console.error at the gate;
  reverted afterward): `baitwait-gate poke=forretress E=40
  baitShields=1 oppShields=1 active=[SAND_TOMB:dpe=0.575:dmg=28,
  ROCK_TOMB:dpe=0.84:dmg=53] fs0=SAND_TOMB:dpe=0.575:dmg=28` — the
  inner bait branch ENTERS (E=40<50, 0.84>0.575), then the exemption
  *"Don't go for baits if you have an effective self buffing move"*
  (ActionLogic.js:843-846) kills it: stale ratio `0.84/0.575 = 1.4609
  <= 1.5` AND `activeChargedMoves[0].selfBuffing` — **Sand Tomb IS
  selfBuffing in PvPoke**: GameMaster.js:873-875 sets
  `selfBuffing = true` for any `buffApplyChance == 1` move with
  `buffTarget == "opponent"` (guaranteed opponent debuff counts).
  → bait=false → throws the second Sand Tomb at T22 (E=40).
- **Ours**: our `selfBuffing` semantics already match
  (moves.py:190-201 — verified behaviorally: we throw the first ST at
  T13 through the same exemption, pre-debuff ratio 1.4609). But after
  the T13 debuff our dpe is stage-fresh: [0.7, 1.06], ratio
  `1.06/0.7 = 1.5143 > 1.5` → exemption fails → bait-wait returns
  None at T22 (trace: `DP-trace[Forretress]: bait-wait for ROCK_TOMB`)
  → second ST delayed to T26 (E=56, where the energy precondition
  fails). The 4-turn slip reorders Kingdra's Surfs around the ST and
  cascades (worse in [1,2]/[2,2] where more shields stretch the fight).

Same 1.5-threshold straddle, same stale-vs-fresh cause, different
bandaid.

## CLAUDE.md three-question test

1. **Is PvPoke demonstrably better?** No. The diverging agent
   (Forretress) does *better* under our policy in the two big
   clusters: corsola [1,1] ours 489 vs PvPoke 330 (+159), kingdra
   [2,2] +82; PvPoke is marginally better only in kingdra [1,2]/[1,1]
   (-25/-8). PvPoke's behavior is a stale-cache artifact, not a
   policy: its own .damage and .dpe disagree with each other
   mid-battle.
2. **Defensible reason for our deviation?** Yes: evaluating bandaid
   heuristics at the current stat stages is the principled reading of
   the same heuristics; we already recompute stage-aware damage inside
   the DP itself (DEVELOPER_NOTES 2026-04-15 Forretress/Azumarill
   entry), so fresh bandaid inputs are consistent with our engine's
   design.
3. **Would matching make us worse for the use case?** Matching
   requires *porting staleness*: freezing a `cm_dpe_root` snapshot at
   battle start for the bandaid ratio checks AND replicating PvPoke's
   opportunistic .damage refresh sites (OMT :320/:336, wouldShield
   :1121) to get the don't-bait gate's exact inputs. The second part
   is load-bearing for exact parity (corsola T26 needs *stale*
   .damage, which a mere root-stage snapshot would supply, but kingdra
   T22 needs *fresh* .damage with *stale* .dpe). Doable but ugly, and
   it would flip the corsola cells to PvPoke's worse-for-Forretress
   line.

**Decision recommendation: keep our behavior; document + tag the
cells known-mechanism** (same posture as the near-KO bandaid family).
If exact-parity pressure grows, the fix sketch above
(root-stage dpe snapshot + refresh-site modeling) is the packet.

Refinement to an existing note: DEVELOPER_NOTES' bait-wait landmark
("selectBestChargedMove overwrites .dpe to raw damage/energy, same as
our actual_dpe") is right about raw-vs-buff-adjusted but missed the
freshness axis: PvPoke's raw .dpe is raw-at-init (root stages,
frozen); ours is raw-at-current-stage.

## Coverage of the 80 unknowns

| cluster                                     | cells | status                                                                |     |                                          |
| ------------------------------------------- | ----- | --------------------------------------------------------------------- | --- | ---------------------------------------- |
| corsola_galarian <-> forretress [1,1]/[1,2] | 4     | PROVEN (line trace + gate instrumentation)                            |     |                                          |
| forretress <-> kingdra (all)                | 8     | PROVEN [1,1]; same first-divergence signature in [1,2]/[2,2]/log-only |     |                                          |
| ninetales <-> forretress [2,2]              | 2     | same family (probable; ours keeps ST where PvPoke swaps to RT —       |     |                                          |
|                                             |       | reversed direction, consistent with stale-vs-fresh straddling;        |     |                                          |
|                                             |       | not traced,                                                           | d   | =8)                                      |
| forretress <-> malamar                      | 6     | same family (probable; ST debuff + RT timing slip; not traced)        |     |                                          |
| feraligatr <-> forretress                   | 4     | NOT this mechanism —                                                  | d   | <= 1 score-rounding family (grid item 9) |

So: **12 of 80 trace-proven, ~8 more same-family probable** (= up to
20 of 80; ~24 if the malamar log-only identity swaps are counted
against the same chain). The remaining unknown mass
(lickilicky/seaking, seaking/azumarill, guzzlord/malamar,
tinkaton/malamar residue, feraligatr ±1) is other families.

## tinkaton <-> malamar 0-shield residue (|d| 60/49/18): does NOT share the mechanism

At the first divergence (Malamar E=44, T12 in our trace) **no stat
stage has changed yet** — fresh and stale inputs are numerically
identical, so the freshness mechanism cannot apply. What actually
happens in ours: the near-KO DP itself flips its plan from
SUPER_POWER-first (held by bandaid[918] stack-wait through E=20..36)
to FOUL_PLAY-first at E=44, and FP (non-debuffing) sails through the
bandaid chain and fires immediately. PvPoke instead holds and throws
Superpower only after Tinkaton's first charged move. Distinct
mechanism (DP plan-timing / bandaid-chain interplay on the Malamar
side); needs its own decideLog comparison at [0,0].

While in that code, the two flagged bandaid[910] index deltas were
**verified as real port deltas** against the reference
(ActionLogic.js:928-934 vs battle.py:1613-1627):

1. PvPoke tests `! poke.activeChargedMoves[0].selfBuffing` (slot 0 of
   the shuffled list); ours tests `not cm_self_buff[first_idx]` (the
   planned first move). For Malamar these differ: slot 0 is FOUL_PLAY
   (not selfBuffing) while first_idx may be SUPERPOWER.
2. PvPoke gates on `opponent.bestChargedMove` (the
   shuffle-then-carve-out selection, Pokemon.js:790-822, incl. the
   literal `moveId != "SUPER_POWER"` clause); ours estimates by max
   actual damage. This is the SAME selectBestChargedMove-fidelity gap
   as the probe-verified bestcm_estimate family — the faithful port
   built for that fix should be reused here.

Neither delta is yet pinned to a failing cell (bandaid[910] requires
`moves[0].selfDebuffing`, which FP isn't, so it is not the residue's
first divergence) — they belong in the fix-packet as
fidelity/hardening items alongside the bestcm fix.

## Instrumentation ledger

- Clone (`~/coding/MGLPoGo/pvpoke`, @9b7407782): added 2 temporary
  `console.error` blocks ("XXX baitwait-gate", "XXX baitwait-inner")
  around ActionLogic.js:838-841. **Reverted** via
  `git checkout src/js/battle/actions/ActionLogic.js`; `git status`
  clean afterward.
- Our repo: read-only throughout (sys.settrace line capture +
  monkeypatched policy wrapper, no engine edits). Scratch scripts in
  `/tmp/forretress_localization/` (trace_ours.py, linetrace.py,
  probe_dpe.py, probe_kingdra.py, print_harness_cmd.py + outputs).

## What tomorrow's session should do

1. Reclassify in `grid_classified.json`: tag the 12 proven cells
   mechanism=`bandaid_stale_inputs` (corsola 4, kingdra 8); tag
   ninetales 2 + forr-malamar 6 `bandaid_stale_inputs?` pending a
   5-minute spot trace each; move feraligatr 4 to the rounding family.
2. Add the DEVELOPER_NOTES entry (this file is the draft): new
   intentional divergence "post-DP bandaid input freshness", with the
   1.5-threshold straddle numbers and the keep-ours rationale; xfail
   any oracle fixtures covering these cells with that reason.
3. Fold the two verified bandaid[910] index deltas into the
   incoming-gate/bestcm fix-packet (reuse the faithful
   selectBestChargedMove port for both battle.py:214 and
   battle.py:1618).
4. Tinkaton<->malamar 0-shield residue: own localization session;
   start from the [0,0] cell with a PvPoke decideLog and find where
   PvPoke's plan keeps SP-first at E≈44 where our DP flips to FP.
