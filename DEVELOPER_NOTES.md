# Developer Notes

## Current status (2026-04-06)

<!-- sync:test_count -->618<!-- /sync --> tests collected. The original PvPoke battle-correctness
core was 102 + 9 shadow + 9 Corviknight mirror = 120; the remainder are
unit and integration tests added since. The simulator matches PvPoke's
simulate-mode score table exactly (±0) for <!-- sync:pvpoke_matchups_verified -->8<!-- /sync --> matchups
(<!-- sync:pvpoke_cells_verified -->72<!-- /sync --> cells). The 3 original failures were all Mienfoo vs
Medicham, root-caused to a `bestChargedMove` selection difference and
resolved 2026-04-06 (see below).

### Verified correct
- **Type effectiveness**: All <!-- sync:type_chart_cells_verified -->324<!-- /sync --> matchups match PvPoke exactly
- **Damage formula**: Verified against manual calculation
- **Buff/debuff mechanics**: Guaranteed buff (Beedrill 9/9), chance buff
  (Corviknight 9/9), self-debuff meter threshold
- **DP queue insertion**: Three PvPoke strategies ported (farm-down <=,
  ready <=+dedup, not-ready <)
- **selfBuffing/selfDebuffing flags**: Match PvPoke's chance thresholds
  (==1 for selfBuffing, >=0.5 for selfDebuffing)
- **Shield policy**: pvpoke_simulate_shield uses precomputed flags
- **Shadow Pokemon**: ×1.2 atk / ×(5/6) def multipliers match PvPoke's
  SHADOW_ATK=1.2, SHADOW_DEF=0.83333331. Shadow Swampert vs Registeel 9/9.
- **Both-side buffs**: Corviknight mirror (Air Cutter only) 9/9. Both mons'
  buffApplyMeter fires independently; unbuffed Air Cutter does 18, buffed does 23.

### Previously failing matchups — all fixed

Mienfoo vs Medicham (9/9) resolved by the `would_shield` buff-reset
ordering and CMP cancellation fixes. Full root-cause writeup in
`CHANGELOG.md` under `2026-04-04 to 2026-04-06`.

## PvPoke bugs found

<!-- sync:pvpoke_bugs_documented -->4<!-- /sync --> bugs documented below (sections 1, 2, 3, 7 — numbering
reflects discovery order; section 4 was retracted 2026-04-15 and is
excluded from the count).

### 1. BattleState .hp/.oppHealth naming inconsistency

**File**: `ActionLogic.js:1187` (class definition) vs lines 479, 600, 697

PvPoke's `BattleState` stores `.oppHealth` and `.oppShields`, but the
dominance checks reference `.hp` and `.shields` (undefined in JS →
always false → dead code). The dedup check at line 545 correctly uses
`.oppHealth`.

We added an `intended_pruning` flag to `pvpoke_dp` that toggles between
PvPoke's actual behavior (dead-code pruning, `False`) and the apparently
intended behavior (functional pruning, `True`).

### 2. bestChargedMove not recomputed on opponent form change

**File**: `Pokemon.js:791-822` (selectBestChargedMove) and
`Pokemon.js:2344` (changeForm calls resetMoves on self only)

PvPoke computes `bestChargedMove` at init time using actual damage
against the opponent's current stats, then caches it on the Pokemon
object. When the **opponent** changes form (e.g., Aegislash
Shield->Blade, dramatically changing defense), the attacker's
`bestChargedMove` is NOT recomputed. Only the form-changing Pokemon's
own `resetMoves()` is called.

Concrete example: Azu's IB (15 dmg, 55 energy, DPE 0.273) vs PR
(18 dmg, 60 energy, DPE 0.300) against Aegislash Shield form. DPE
diff is 0.027 < 0.03 threshold, so PvPoke picks IB (cheaper, locked
at init). Against Blade form (low def), DPE diff grows to 0.062 >
0.03, and PR becomes clearly better - but PvPoke still uses IB. Our
code recomputes per turn, which we believe is more correct.

### 3. Aegislash selects Gyro Ball over Shadow Ball

**File**: `ActionLogic.js` (near-KO DP or bestChargedMove selection)

PvPoke selects Gyro Ball (Steel, 80 power, 50 energy) over Shadow
Ball (Ghost, 100 power, 50 energy) for Aegislash vs Azumarill in
multi-shield scenarios. Both moves cost identical energy, have the
same type effectiveness (1.0x) and STAB (1.2x) against Water/Fairy.
SB does strictly more damage (49 vs 39 in Shield form, 101 vs 81 in
Blade form). Confirmed: Aegislash with SB-only scores 429 vs 376
with SB+GB in the 1v2 scenario, meaning GB availability actively
hurts Aegislash's score. Root cause unclear - may be in the near-KO
DP's plan selection or a bandaid condition.

### 7. needsBoost / non-guaranteed-buff plan selection is dead code

**File**: `ActionLogic.js:515-539, 793-810, 868` (decideAction DP)

PvPoke's code looks like it accumulates a `stateList` of KO-bearing
terminal DP states tagged with `.chance` (product of `buffApplyChance`
values along the path), then picks the highest-chance plan when
`opponent.turnsToKO != -1 && poke.turnsToKO > opponent.turnsToKO`
(logged as "changes its plan because it needs the BOOST to win or
debuff"). Line 868 gates a downstream plan-reorder on the same flag.

Two independent faults render the whole system inert in simulate mode:

1. **Line 539: `changeTTKChance = 0;`** (unconditional, with comment
   "DISABLE THE NON-GUARANTEED BUFF EVALUATION SYSTEM"). This fires
   at the top of every move-evaluation iteration, after lines 519-536
   would have set `changeTTKChance` to the move's `buffApplyChance`.
   Every chance-<1 DPQueue push (lines 613, 631, 661, 680, 710, 728,
   756, 774) is gated on `if (changeTTKChance != 0)` → always false.
   So `stateList` only ever accumulates chance-1 plans.
2. **`needsBoost` is declared `false` on line 793 and is never
   assigned `true` anywhere in the file** (grep confirms). The
   "else if (... poke.turnsToKO > opponent.turnsToKO)" branch picks
   `bestPlan` but doesn't flip the flag. So the `if (!needsBoost)`
   gate at line 868 always fires — the plan-reorder branch is never
   actually gated.

**Empirical confirmation 2026-04-15**: ran `scripts/pvpoke_trace.js`
across all 9 shield scenarios for the four GL species carrying
`0 < buffApplyChance < 1` moves in their default movesets (Tinkaton+
Bulldoze, Corviknight+AirCutter, Clefable+Moonblast, Drapion+Crunch)
vs common opponents. The "needs the BOOST" decision log message never
fired — 0 hits across 36 sims. Matches the static analysis.

**Our stance**: we intentionally do NOT port stateList accumulation
or the needsBoost trigger. Doing so would *diverge* from PvPoke's
actual observable behavior in the direction of a feature PvPoke has
explicitly disabled. Our first-KO-terminal pick matches PvPoke's
effective single-plan behavior.

If PvPoke ever removes line 539 or fixes the `needsBoost = true`
assignment, revisit — the enumeration of affected meta species above
still applies.

### 4. Mimikyu SS timing — RETRACTED 2026-04-15

This was a phantom bug. We thought our Mimi threw Shadow Sneak one
turn earlier than PvPoke (363 vs 350), but harness localization
revealed the divergence was in our timeline OUTPUT, not behavior.
Our `simulate()` disguise-bust branch logged only "disguise busted"
without emitting the standard `X uses Y → Z dmg` line for the
throw that triggered it. So `_extract_battle_log` saw N-1 entries
where PvPoke's harness saw N — making it look like PvPoke threw an
"extra" opening Ice Beam. Once the missing log line was added, our
chargedLog matches PvPoke's exactly across all 9 Mimi vs Azu shield
combos. Mimi's actual SS timing was correct all along; the
"363 vs 350" score difference came from earlier raw_dpe issues
(also fixed 2026-04-15), not from SS timing. See the 2026-04-15
"Localization meta-finding" entry below for the broader lesson.

## Open divergences

(none currently outstanding — see "Known divergences" for intentional ones)

## Known divergences from PvPoke implementation

Places where our code intentionally does NOT match PvPoke's
implementation. Each is a potential source of score mismatches if we
hit an edge case. Fix these before assuming a score difference is a
PvPoke bug.

### Near-KO DP plan choice: nuke-with-self-debuff vs serial-Fly (intentional)

**Mechanism (localized 2026-04-15 followup session):** The divergence
is NOT a difference in the near-KO DP's plan output — both sims' DPs
return `[BRAVE_BIRD]` as `finalState`. The divergence is in a
**post-DP bandaid**: PvPoke's ActionLogic.js line 885-887 (our port:
battle.py:1541-1558, bandaid[866]) swaps `finalState.moves[0]` from
the self-debuffing nuke to `activeChargedMoves[0]` (Fly) whenever:

    opp.shields == 0
    AND finalState.moves[0].selfDebuffing
    AND finalState.moves[0].energy > 50
    AND poke.hp / poke.stats.hp > 0.5
    AND finalState.moves[0].damage / opp.hp < 0.8

PvPoke's `move.damage` field is set as a side effect of OMT line 320
(`activeChargedMoves[n].damage = DamageCalculator.damage(...)`),
which runs unconditionally per-move whenever `opponent.shields == 0`.
Our port caches damage at battle.py:652 but subgates the assignment
on `attacker.energy >= cm['energy']` — so in the Moltres-G cluster
(energy < BB's 55 at the T20 DP-entry state) our `_cached_damage`
stays `None`, bandaid[866] skips its `_cached_dmg / opp.hp < 0.8`
test, the DP plan is left alone, and bandaid[918] stacks BB until
energy reaches 100 → single-BB nuke instead of Fly-chain.

**Why we don't fix it:** faithfully mirroring PvPoke's OMT side
effect (so bandaid[866] fires when PvPoke's bandaid[885] would) swaps
BB → Fly in **all** MG cluster cases, not just Lapras. The bandaid's
`damage/opp.hp < 0.8` test doesn't discriminate:

- Lapras [1,2]:   BB 99 / hp 142 = 0.70 → fires (PvPoke's Fly plan wins; ours loses by 1 HP)
- Jellicent [0,0]: BB 99 / hp ~160 = 0.62 → fires (PvPoke's Fly plan worse by ~47 HP)
- Corviknight cluster: similar 0.6-0.7 ratios → fires (PvPoke's Fly plan worse by ~38 HP)

So the fix is all-or-nothing against a 6:1 weighting; matching PvPoke
inverts the ratio rather than improving it. Per CLAUDE.md "When our
sim diverges from PvPoke": PvPoke isn't demonstrably better overall,
and our deviation has a defensible reason (better HP retention in 6
of 7 cases). Keep the `_cached_damage` subgate as the intentional
deviation that implements this choice.

**Outcome comparison** — full magnitude across the cluster (UL top-8
harness, MG max HP=161, all cases MG wins in both sims):

| matchup           | ours MG HP | PvPoke MG HP | gap         |
| ----------------- | ---------- | ------------ | ----------- |
| Jellicent   [0,0] | 92  ( 57%) | ~45 ( 28%)   | +47 / +29pp |
| Jellicent   [0,1] | 137 ( 85%) | ~89 ( 55%)   | +48 / +30pp |
| Jellicent   [0,2] | 137 ( 85%) | ~89 ( 55%)   | +48 / +30pp |
| Corviknight [0,0] | 45  ( 28%) | ~7 (  4%)    | +38 / +24pp |
| Corviknight [0,1] | 71  ( 44%) | ~33 ( 20%)   | +38 / +24pp |
| Corviknight [0,2] | 97  ( 60%) | ~59 ( 37%)   | +38 / +23pp |

Consistently +23-30 percentage points (~38-48 raw HP). MG also KOs
6-12 turns earlier in our sim. The magnitude is what makes our
divergence defensible — if the gap were a few HP, PvPoke's plan
would be at-or-better than ours and we'd match. At 25-30pp the
post-KO carry-over difference is material for next-mon analysis.

**Caveat — Lapras [1,2] winner flip**: 1 of 7 cluster cases is a real
edge case where our plan is worse. Same root cause (MG picks BB, PvPoke
picks Fly-Fly-Fly), but Lapras is bulky enough (234 HP) that our BB's
atk debuff bites AND PvPoke's 3 Fly throws add up:
- Ours: Lapras barely wins 502/497 (MG 0 HP, Lapras 1 HP, 1-HP margin)
- PvPoke: MG wins 608/391 (MG ~34 HP, Lapras 0)

Here PvPoke's slower plan **is demonstrably better** — it correctly
predicts MG wins a close fight that our BB-nuke loses by 1 HP. Pinned
as its own xfail in `tests/test_battle.py` under `_MG_NEARKO_PLAN_FLIP`.

**Decision**: keep our DP behavior, net. Rationale is 6:1 weight of
clear-win cases (ours retains 23-30pp more HP) against 1 close-fight
flip. Per CLAUDE.md "When our sim diverges from PvPoke" policy: PvPoke
is better for close/bulky matchups, ours is better for clear-win HP
retention. Neither plan is universally right.

**Impact** (UL harness top-8): 7 cases show |Δ|>20 (jellicent×3 at
d1=-146, corviknight×3 at d1=-118, lapras×1 at d1=+111 with winner
flip). All MG-involving, all defender=MG or bulky-water-attacker.
GL unaffected (no top-8 GL species has this matchup shape).

**Revisit** if: (a) wider harness sampling adds more bulky opponents
that produce close-fight flips (shifts the 6:1 ratio); (b) we add a
shield-state / multi-mon model where next-mon HP carry-over isn't the
only scoring dimension; (c) a probabilistic/random DP mode would
prefer PvPoke's lower-variance multi-throw plan; (d) we find a
discriminator that separates Lapras-style bulky-comeback matchups
from Jellicent/Corv-style clear-wins (bandaid[885]'s existing
`damage/opp.hp < 0.8` test doesn't — all 6 cluster cases land in the
0.6-0.7 band alongside Lapras at 0.70).

**Closed lead (2026-04-15 followup):** "Port a non-debuf swap into
the near-KO DP branch" was the original session hypothesis. The
localization found the mechanism is PvPoke's post-DP bandaid[885],
not a near-KO plan-selection difference — so porting a near-KO swap
would diverge from PvPoke, not match it. Issue retired.

### Tie-break semantics on simultaneous-KO (score=500/500) — resolved 2026-04-15

Previously two harness cases showed up as "winner flips" on 500/500
double-KO ties:
- GL `wigglytuff vs azumarill [2,2]`
- UL `corviknight vs moltres_galarian [2,2]`

Root cause was in the harness scripts, not the sim: `pvpoke_trace.js`
collapsed PvPoke's native tie output (`winner.pokemon = false`) to
`winner=1` as a shortcut, while our sim correctly returned `None`.
`harness_grid.py` then mapped `None → -1` for JSON output, producing
a spurious flip.

Fix: `pvpoke_trace.js` now emits `winner: null` on genuine ties
(matching PvPoke's native semantics); `harness_grid.py` preserves
`None` end-to-end. Sim behavior unchanged. GL flips 1 → 0, UL flips
2 → 1 (the remaining UL flip is the real Lapras [1,2] divergence).

### Closed 2026-04-15: needsBoost — not implementing (PvPoke system is dead code)

Originally flagged as an open port. Full root-cause writeup is in
"PvPoke bugs found" §7 above. Short version: PvPoke's code looks
like it picks alternative plans from a `stateList` accumulated over
chance-<1 buff states, but (a) line 539 unconditionally zeros
`changeTTKChance` so no chance-<1 states ever reach `stateList`, and
(b) the `needsBoost` flag is never assigned `true`. Empirically
verified 0 "needs the BOOST" log hits across 36 sims covering every
GL-meta species whose default moveset includes a `buffApplyChance<1`
charged move (Tinkaton, Corviknight, Clefable, Drapion).

**Our single-plan behavior already matches PvPoke's observable
behavior.** Porting stateList+needsBoost would diverge from the
reference in the direction of a feature PvPoke has explicitly
disabled — exactly the anti-pattern the CLAUDE.md "When our sim
diverges from PvPoke" policy warns against.

Revisit only if PvPoke removes line 539 or fixes the
`needsBoost = true` assignment upstream.

### Resolved divergences (full writeups in CHANGELOG.md)

* **2026-04-15 — Defender-bestCM-selfDefenseDebuffing shield gate
  (UL Moltres-G score-margin cluster).** Ported PvPoke Battle.js:1105-
  1124. Our `pvpoke_simulate_shield` was always-shielding standard
  charged moves; PvPoke instead routes the shield decision through
  `wouldShield` whenever the **defender's own** `bestChargedMove` is
  `selfDefenseDebuffing` — defender saves shields for the post-debuff
  fragility window. Two sub-branches by attacker shields: if attacker
  has shields, override directly; if attacker has 0 shields, override
  only when defender's next charged-cycle would KO the attacker
  (cycleDamage and CMP-aware turn-comparison gates). Helper
  `_estimate_best_cm` selects the defender's best-actual-DPE charged
  move; `_cheapest_cm` proxies attacker.activeChargedMoves[0] (full
  priority shuffle from pvpoke_dp not factored out — pragmatic
  approximation, sufficient for the cases tested).
  Probe: MG vs Florges [2,0] previously d1=+230, now d1=0 (same
  chargedLog as before, but MG correctly skips shielding the second
  Disarming Voice → 9% HP remaining instead of 55%, matching PvPoke).
  UL grid: max |Δ| 230→146, |Δ|>20 18→7, winner flips 2→2 (no new
  flips introduced). GL grid: max |Δ|=0 across 405 pairs unchanged
  (no top-8 GL species default moveset has a selfDefenseDebuffing
  charged move). Tests 156p/6xf, oracle 27/27 unchanged.
  Localization landmark: trace_shields output revealed the gap
  immediately — `wouldShield(...) → False` followed one turn later
  by `shield(...): True (always shield)`. The helper text
  ("[defBestCM=BRAVE_BIRD selfDefDebuff, attShields=0, no cycleKO]")
  added to trace makes the new gate auditable from log inspection.

* **2026-04-14 — selfBuffing flag scope.** Now matches PvPoke's
  `GameMaster.js:873` definition (positive self-buffs *and*
  guaranteed opponent debuffs).
* **2026-04-14 — activeChargedMoves priority-shuffle.** All
  `resetMoves` shuffle clauses replicated in `pvpoke_dp`. **Keep in
  mind** when revisiting bait-wait: PvPoke's
  `selectBestChargedMove` overwrites `.dpe` to raw `damage/energy`
  *after* the priority-shuffle, so the 1.5 ratio check
  (`ActionLogic.js:843`) uses raw DPE, same as our `actual_dpe`.
  Buff-adjusted DPE only affects the shuffle ordering, not the
  ratio check.
* **2026-04-15 — Forretress/Azumarill DP plan-selection.** Near-KO
  DP now tracks attacker `atk_stage` and recomputes charged/fast
  damage at every reachable stage so stacked chance-1 opp-def
  debuffs accelerate plans the way PvPoke does. Azu/Forr
  (Sand+Rock) now matches PvPoke 9/9 exact. Gotcha preserved for
  future readers: raw gamemaster `buffApplyChance` is a string;
  compare via `float(...) != 1.0`.
* **2026-04-15 — Mimikyu disguise-bust missing log line (meta-lesson).**
  Pinned via the new chargedLog test assertions: when Azu's "break
  Mimi's disguise" charged throw lands on a still-disguised Mimikyu,
  the `simulate()` loop's disguise-bust branch (battle.py:2066-2075)
  emits `Mimikyu (Busted) disguise busted (1 dmg)` but skipped the
  standard `Azumarill uses Ice Beam → 1 dmg` line. So
  `_extract_battle_log` lost one entry, and PvPoke's chargedLog
  appeared to have one extra Azu IB at the front. Fix: emit the
  "uses" line in the disguise branch too. All 6 Mimikyu xfails (4
  AZU_OPENING_IB + 2 SS_DELAY) flipped to clean passes; PvPoke "bug
  #4" was retracted (see above). **Meta-lesson:** the audit in
  docs/validations/2026-04-15_harness_code_review.md correctly
  identified the disguise-handling DP path as implemented, but
  audited DP/policy features rather than the throw-dispatch logger.
  Log emission is downstream of the DP and isn't covered by oracle
  score tests, so divergences there were silent until chargedLog
  assertions were added. Future feature audits should include a
  pass over the timeline/log emission paths, not just the
  decision-making code.
* **2026-04-15 — Many-cycle non-debuff swap (Moltres-G cluster winner flip).**
  Ported PvPoke's ActionLogic.js lines 371-393: when bestChargedMove is
  selfDebuffing AND a cheaper non-debuffing alt exists with DPE ratio
  < 2x, drop the farm-down threshold from 2.0x to 1.1x cycles AND swap
  the first-throw to the non-debuffing alt. Without this, our near-KO DP
  picked the debuffing nuke (BrB) and bandaid [918] stacked, letting
  Lapras KO first. Concrete case: Lapras vs Moltres-G [0,1] at MG energy
  49 (Fly affordable, BrB not). PvPoke's MG throws Fly (61 free damage,
  no atk debuff, Lapras has 0 shields); our MG waited for BrB and died.
  Fix: compute min_cycle_thr=1.1 when the debuffing-best-with-cheaper-
  non-debuf-alt condition holds, and swap selected_idx to the non-debuf
  alt in the farm-down path. UL harness-grid max |Δ| 352→230, winner
  flips 4→2 (the Lapras[0,1] flip and one other resolved). Remaining
  MG-cluster deltas are score-margin only (same chargedLog order),
  investigated separately — see "Open divergences" below. GL grid
  unchanged (max |Δ|=0 across 405 pairs). Tests 156p/6xf, oracle 27/27.
  Localization landmark: instrumenting PvPoke ActionLogic.js with
  `console.error` at the many-cycle entry revealed that PvPoke's
  bestChargedMove computation uses raw `damage/energy` (post-STAB,
  post-effectiveness), not `power/energy` — an easy misread when
  eyeballing DPE.
* **2026-04-15 — OMT fast-also-KOs gate dropped.** The OMT KO-override
  had a `defender.hp > _fast_dmg` gate: if the fast move would ALSO KO,
  prefer fast over charged (rationale: "score identical, saves energy /
  animation / post-KO state"). Harness localized Forr vs Azu 1-0 (Δ=-15)
  to T37: Forr has e=64 (ST affordable) and Azu hp=17; fast_dmg=18>=17
  so the gate fires and Forr delays for fast. But Forr just fired VS at
  T36 (floating), so its next fast doesn't land until T40 — three extra
  turns of Azu damage on Forr. The "score identical" claim held only
  when the fast could fire immediately; under mid-cooldown timing it
  fails. Dropped the gate, keeping the self-debuffing clause. GL grid
  max |Δ| 15→0 across all 405 pairs. UL unchanged (Moltres-G is a
  different root cause). Test suite: 156 pass (one prior xfail converted
  to pass — Azu's final Ice Beam in Forr/Azu (2,0) chargedLog now
  matches PvPoke). Investigation landmark: decideLog entry/return
  tracing in scripts/pvpoke_trace.js (decideAction-level) was the tool
  that localized the divergence — earlier score/dpPlan-level traces
  missed it because the divergence was in OMT, upstream of the DP.
* **2026-04-15 — Farm-down boost-move override + raw_dpe fix.**
  Two linked DP gaps surfaced when localizing GL Empoleon vs
  Forretress 2-2 (Δ=-204). (1) When the near-KO DP returns a
  farm-down plan (no charged moves in the winning path), our code
  returned `None` and the Pokemon never threw. PvPoke
  (ActionLogic.js:813-823) instead force-pushes `getBoostMove()`
  — the LAST charged move in user order with chance≥0.5 buff
  and not selfDebuffing — so the debuff value lands on the
  opponent even when the KO is guaranteed by fast moves alone.
  Ported in `pvpoke_dp`: farm-down plans now substitute the
  boost move as `first_idx` and fall through the existing
  bandaid chain. (2) `raw_dpe` was `power/energy`, but PvPoke's
  `move.dpe` is `move.damage/move.energy` (type-effectiveness-
  aware, set by `selectBestChargedMove` at Pokemon.js:792 and
  overwriting the buff-adjusted DPE from `initializeMove`). Fixed
  to use cached actual damage. Together these close the
  Forretress cluster: GL grid max |Δ| 204→15, |Δ|>20 count
  16→0, |Δ|>50 count 6→0. UL grid unchanged (Moltres-G cluster
  has a different root cause). Side effect: 12 log-order test
  fixtures updated (scores/winners already matched PvPoke; only
  throw order was stale); 3 Mimikyu xfails now xpass. Oracle
  27/27 still green.

### 3. bestChargedMove computed per-turn, not cached at init (intentional)

**PvPoke**: `bestChargedMove` is computed once at init (and on self
form change via `resetMoves`). Not updated when the opponent changes
form or when stat stages change.

**Our code**: `best_idx` is recomputed every call to `pvpoke_dp` using
current damage values. We believe this is more correct: it responds to
stat stage changes mid-battle and to opponent form changes (e.g.,
Aegislash Shield->Blade dramatically changes defender's def, shifting
DPE thresholds). PvPoke's stale cache produces suboptimal move choices
when opponent stats change, as documented in PvPoke bug #2 above.

**Impact**: +134 delta on Aegislash 1v2/2v2 — our Azu correctly
switches to Play Rough (higher DPE against Blade form) while PvPoke
keeps using Ice Beam (cached against Shield form's def).

**Decision**: keep our per-turn recomputation. The only known
mismatches are in Aegislash scenarios where PvPoke's cached selection
is demonstrably worse.

## Threshold model: damage tiers vs matchup boundaries

The deep dive reports two kinds of stat threshold (2026-04-09/10):

**Damage-tier boundaries** (`_aggregate_flips_by_anchor`): the exact
def (or atk) at which `floor(0.5 * 1.3 * Power * Atk/Def * Eff * STAB) + 1`
steps by 1. These are pure-formula boundaries, invariant to battle
conditions (energy leads, bait policy, turn count). Discovered by
Level 3 anchor enumeration.

**Matchup-flipping boundaries** (`_find_matchup_boundaries`): the
minimum def (+HP) at which the overall battle outcome changes from loss
to win. Usually higher than the damage tier because multiple per-hit
reductions must accumulate across a full fight to change the turn count.
Found by sweeping def thresholds against sim results.

Both are shown in the HTML output: damage tiers in the "Anchor-Driven
Matchup Flips" section, matchup boundaries in "Matchup-Flipping
Boundaries" and in tier cards. The distinction matters for future
energy-lead work: damage tiers won't change, matchup boundaries will.

## Key implementation details

### DP queue insertion (pvpoke_dp)

PvPoke uses three different insertion strategies in the DP queue:
1. **Farm-down** (`<=`): insert after same-turn states
2. **Ready-move** (`<=` + dedup): dedup at exact turn, then insert after
3. **Not-ready-move** (`<`): insert before same-turn, giving charged-move
   KO paths priority over farm-down

The `<` for not-ready states is critical — it produced 2 exact PvPoke
matches and several closer scores for Azu vs Forretress.

### selfBuffing / selfDebuffing thresholds

PvPoke gates these flags on `buffApplyChance`:
- `selfBuffing`: chance == 1 only (guaranteed buffs)
- `selfDebuffing`: chance >= 0.5 (excludes low-chance like HJK at 10%)
- `DRAGON_ASCENT` is explicitly excluded from selfDebuffing

These flags control the shield policy: guaranteed self-buff moves use
the `wouldShield` heuristic, while chance-buff moves are always shielded.

### Form change gotchas

Two non-obvious behaviors discovered during form change implementation
(2026-04-14) that are easy to get wrong:

**1. HP does not scale on form change.** When Aegislash switches between
Shield form (97 atk, 272 def) and Blade form (272 atk, 97 def), the HP
and max_hp stay fixed at the starting form's values. PvPoke's
`Pokemon.js changeForm()` has the HP update explicitly commented out:
`//this.stats.hp = newStats.hp;` (line ~2365). This means Aegislash
keeps Shield form's HP even after transforming to Blade. It would be
natural to assume HP scales proportionally with the new form's stats,
but it doesn't.

**2. Aegislash Blade form uses whole levels only.** When Shield form
(level 46 in GL) transforms to Blade form, the game rounds DOWN to the
nearest whole level (not half level). In Pokemon Go you power up in
0.5-level increments, so a Blade form could theoretically be level 22.5
(1476 CP, under the 1500 cap), but the game puts it at level 22 (1443
CP) instead -- losing a half level of stats. PvPoke's `getFormStats()`
(Pokemon.js line ~2391) implements this via `newLevel--` (decrementing by
1, not 0.5). This was discovered by cascade1185
(https://x.com/cascade1185/status/2037456058265075782) and explained by
Caleb Peng (https://www.youtube.com/watch?v=OdHxOD6FZcg&t=167s). When
choosing which Aegislash to power up, players need to check that the
Blade form level lands on a favorable whole number.

## Deep dive output file layout

Deep dive HTML files (and the logs that come with them) generated by
`scripts/deep_dive.py` are user-specific scratch — never committed to
the repo. There are two valid locations depending on whether you might
want to revisit the file later:

* **`userdata/dives/`** — for deep dives you want to keep around:
  baseline runs, runs you'll compare against later, anything you might
  want to look at again after a reboot. The whole `userdata/` directory
  is in `.gitignore`, so the files persist on disk but never enter the
  git history. Create the directory if it doesn't exist
  (`mkdir -p userdata/dives`).

* **`/tmp/`** — for truly throwaway in-session iterations: smoke tests
  while you're tweaking renderer code, "let me see what this looks like
  with a different flag", etc. macOS clears `/tmp/` on reboot, so don't
  put anything there you'd be sad to lose. Within a session, `/tmp/`
  is fine and the convention I (and Claude) have been using for quick
  verification cycles.

When in doubt, prefer `userdata/dives/` — the cost of an extra
directory entry is nothing compared to the cost of accidentally losing
a 7-minute deep dive run to a reboot.

The convention applies to all output files from `scripts/deep_dive.py`:
the HTML itself, the `.log` redirect file if you used one, and any
ancillary data (cached cohort dumps, etc.). If you're scripting batch
runs that produce many dives, point `--html` at a path under
`userdata/dives/` rather than the repo root.

Reference deep dives that *should* live in the repo (e.g., the
validation HTMLs under `docs/validations/`) are a separate category —
those are checked in deliberately as point-in-time evidence and don't
follow this convention.

## Log file layout

`scripts/deep_dive.py` and `scripts/deep_dive_slayer.py` route all
progress, warnings, and final-output tables through a structured logger
(`scripts/deep_dive_logging.py`). Rationale and the per-call-site
classification live in `docs/structured_logger_design.md`; this section
is the steady-state reference.

**Per-run log file.** Every dive opens
`userdata/logs/YYYY-MM/YYYYMMDD_HHMMSS_<species>_<league>[_shadow].log`
and writes every INFO/WARNING/RESULT record (plus DEBUG when
`--verbose` is passed). The monthly subdir is created on demand. File
records carry a full `[YYYY-MM-DD HH:MM:SS.mmm] LEVEL   deep_dive: ...`
prefix so `grep -E '\] WARNING' userdata/logs/2026-04/*.log` is a
reasonable forensic starting point. As with `userdata/dives/`, the whole
`userdata/logs/` tree is gitignored — logs persist across reboots but
never enter the repo.

**Latest-run symlink.** Right after the file is opened, the logger
atomically refreshes `userdata/logs/latest.log` to point at the current
run. Canonical monitoring command:

```
tail -f userdata/logs/latest.log
```

The symlink is swapped via `rename(2)`, so a long-running `tail -f` from
another terminal never lands on a broken link mid-update — the previous
run's file stays open on the old inode until you stop tailing it.

**CLI flags** (on `scripts/deep_dive.py`):

- `--verbose` — promotes aggregator DEBUG records to the log file.
  Stdout is unchanged.
- `--quiet` — suppresses INFO on stdout; WARNINGs and the Top-20 /
  banner RESULT records still appear. The log file is unaffected.
- `--log-file PATH` — overrides the auto-generated log path. Use
  `/dev/null` to disable the file handler entirely.
- `--log-dir DIR` — relocates the logs root. Useful for batch runs
  that want their own dated directory. Ignored when `--log-file` is
  given.

**Worker processes.** Spawn-mode pool workers (default on macOS) do not
inherit the parent logger's handlers. Each pool's initializer calls
`deep_dive_logging.worker_log_setup(log_path, verbose=...)` — a bare
`print()` from a worker bypasses the log file *and* stdout buffering
kicks in. If you add a new multiprocessing surface, thread `log_path`
and `verbose` through `initargs` alongside the existing state. See
CLAUDE.md "Debugging conventions" for the commit-time rules around
ad-hoc debug prints.

**Periodic cleanup** via `scripts/clean_logs.py` (dry-run default):

```
# Preview what would go away
python scripts/clean_logs.py --older-than 30d

# Actually delete
python scripts/clean_logs.py --older-than 30d --execute

# Archive (move to userdata/logs/archive/YYYY-MM/) instead of deleting
python scripts/clean_logs.py --older-than 60d --archive --execute

# Keep only the 50 most recent runs across all months
python scripts/clean_logs.py --keep-last 50 --execute
```

No auto-purge inside `deep_dive.py` — deletions happen only when you
run the cleanup script with `--execute`. The archive subtree is
gitignored the same way the live tree is.

## All-in-one vs split-moveset HTML

The all-in-one interactive HTML (`--interactive` without `--split-movesets`)
generates the Deep Dive Results section (tier cards, anchor-flip bullets,
matchup boundaries, notable IVs) once for the top-ranked moveset only.
When the moveset dropdown changes, the Plotly scatter updates (score
data is embedded for all movesets) and the IV Flavor Guide narrative
zone swaps (per-moveset narratives are pre-rendered in hidden divs),
but the rest of the analysis stays fixed on the top moveset.

In `--split-movesets` mode each HTML file gets its own full call to
`generate_analysis_sections` with that file's moveset, so every section
reflects the correct moveset. This is the intended experience for the
website — all-in-one is primarily for quick interactive score-distribution
comparison during development.

## Article lifecycle

Articles live in `articles/*.toml` (source TOML, checked in) and render
to `userdata/website/articles/<slug>/` via `scripts/render_article.py`.
Full schema: `docs/article_schema.md`.

### Marking an article obsolete

When a CD move turns out to be strictly better/worse than the sidegrade
framing claimed, or the meta shifts enough that the analysis no longer
applies:

1. Edit the article TOML (e.g. `articles/oinkologne-cd-2026-05.toml`).
2. Change `[obsolescence]` fields:
   ```toml
   [obsolescence]
   status = "obsolete"
   as_of  = "2026-06-15"       # date you're marking it obsolete
   note   = "Mud Slap is strictly better in GL; sidegrade framing no longer applies."
   ```
3. Re-render: `python scripts/render_article.py articles/oinkologne-cd-2026-05.toml`
4. Republish: `scripts/publish_website.sh --push`

The renderer shows a red banner at the top of the page with the note
text and date. No other files need to change.

### Changing authorship level

The `authorship` field tracks content origin. Update it as the article
evolves:

- `auto` — scaffold / auto-generated placeholder content
- `both` — human has edited the prose, but it's backed by sim data
- `expert` — fully human-written analysis

Edit the field in the article TOML and re-render. The banner color
changes automatically (blue -> green -> gold).
