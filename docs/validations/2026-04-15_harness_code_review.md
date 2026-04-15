# PvPoke harness-driven code review (2026-04-15)

Research session: use the new headless Node harness
(`scripts/pvpoke_trace.js`, `scripts/verify_pvpoke_harness.py`, 27/27
oracle green) to systematically surface places where our sim diverges
from PvPoke or under-implements its behavior. **No fixes in this
session** — the deliverable is a prioritized findings report plus
pointers for follow-up work.

**Framing caveat (load-bearing).** "Divergence from PvPoke" is not
synonymous with "our bug." Several of our existing `xfail` tests
document cases where we believe PvPoke is making the wrong choice
(e.g. `bestChargedMove` cached against stale opponent form; Mimikyu
delays SS by one SC; Aegislash picks GB over SB). Every cluster
below still needs triage before being called a regression. Where the
evidence looks like "PvPoke throws a self-debuffing move, we correctly
demote it," that's a documentation task, not a fix.

## TL;DR

* **GL grid** (top-12 meta, C(12,2)=66 pairs × 9 shields = 594 sims):
  **0.3% winner flips, 2.7% |delta|>20, max delta 204.** Cluster
  surface is thin — mostly Forretress interactions, 1 Wigglytuff
  flip, 1 Azumarill edge case.
* **UL grid** (top-10 meta, 45 pairs × 9 shields = 405 sims):
  **1.5% winner flips, 7.9% |delta|>20, max delta 352.** Divergences
  are heavily concentrated on **Galarian Moltres** — appears in 28 of
  29 big-delta records. Deltas go both directions (Moltres-G over-
  and under-performs in our sim depending on matchup), so this is
  not a simple "we demote Brave Bird while PvPoke throws it"
  picture; it needs per-matchup localization.
* **Unimplemented-feature audit**: one concrete gap worth
  investigating (`needsBoost` plan reordering in ActionLogic.js:793-
  810), plus a handful of knobs PvPoke exposes that we don't
  (`buffChanceModifier`, `decisionMethod="random"`) that are unused
  in simulate-mode PvP and can stay missing until needed.
* **Test gaps**: the DP is today almost entirely oracle-verified.
  Three small unit tests against fabricated `_DPState` inputs would
  catch whole classes of regressions without running the harness.

Data artifacts:
* `scripts/harness_grid.py` (new) — runs the grid.
* `/tmp/grid_gl.json`, `/tmp/grid_ul.json` (uncommitted) — per-sim
  records with our vs PvPoke score, winner, turn count.

---

## 1. Divergence grid

Method: for each league, take the top-N non-shadow ranking entries
from `~/Documents/gopvpsim_cache/<league>.json`; build `Spec`
(speciesId, PvPoke `moveset` default, **rank-1 IVs by stat product**);
pair every spec with every other; simulate all 9 shield scenarios
through both `scripts/pvpoke_trace.js` and our
`gopvpsim.battle.simulate(..., charged_policy=pvpoke_dp)`; compare
`pvpoke_score` and winner.

Methodology gotcha caught mid-session: the grid initially used
`simulate()`'s default `bait_with_cheapest` policy instead of
`pvpoke_dp` → 16% winner flips. Switching to `pvpoke_dp` dropped
this to 0.3% (GL) / 1.5% (UL). The CLI script `scripts/battle.py`
already defaults to `pvpoke_dp` so this is a `simulate()` default
mismatch, not a sim bug. Leaving the `simulate()` default as-is
(changing it would silently alter unrelated callers), but calling
it out: **every oracle-comparable script must pass
`charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp`.**

### 1a. Great League (594 sims)

| metric             | count | %    |
| ------------------ | ----- | ---- |
| winner flips       | 2     | 0.3% |
| &#124;Δ&#124; > 20 | 16    | 2.7% |
| &#124;Δ&#124; > 50 | 6     | 1.0% |
| max &#124;Δ&#124;  | 204   |      |

Top deltas:

| matchup                          | shields | ours      | pvpoke    | Δ p1 |
| -------------------------------- | ------- | --------- | --------- | ---- |
| empoleon vs forretress           | 2-2     | 178 / 821 | 382 / 617 | -204 |
| forretress vs feraligatr         | 2-2     | 765 / 234 | 617 / 382 | +148 |
| azumarill vs feraligatr          | 1-2     | 361 / 638 | 261 / 738 | +100 |
| jellicent vs azumarill           | 2-2     | 680 / 319 | 756 / 243 | -76  |
| wigglytuff vs altaria            | 1-2     | 671 / 328 | 741 / 258 | -70  |
| wigglytuff vs altaria (**FLIP**) | 0-2     | 500 / 500 | 569 / 430 | -69  |

**Species appearing in |Δ|>50**: forretress×2, feraligatr×2,
altaria×2, wigglytuff×2, azumarill×2, jellicent×1, empoleon×1.
No single species dominates.

**Localized finding — Empoleon vs Forretress 2-2 (Δ=-204).**
Traced with `trace_dp=True`. Empoleon's `Metal Sound` (fast move,
opponent-atk debuff) repeatedly lowers Forretress's atk stage. In
our sim, **Forretress never throws a charged move for the entire
31-turn battle** (only Volt Switch). PvPoke's Forretress throws two
Sand Tombs (both shielded). Hypothesis: our DP evaluates Sand Tomb
damage against the *current* (debuffed) atk stage and decides the
charged move isn't worth throwing vs the farm-down value — but
PvPoke's DP still surfaces a throw-ST plan. Could be: (a) our
per-turn damage recompute against Empoleon's atk-stage interacts
badly with the farm-down branch; (b) a missing bandaid. Needs
follow-up session. **Not a Moltres/self-debuff-demote
misclassification** — Forretress is the quiet side here.

### 1b. Ultra League (405 sims)

| metric             | count | %    |
| ------------------ | ----- | ---- |
| winner flips       | 6     | 1.5% |
| &#124;Δ&#124; > 20 | 32    | 7.9% |
| &#124;Δ&#124; > 50 | 29    | 7.2% |
| max &#124;Δ&#124;  | 352   |      |

**Species in |Δ|>50**: **moltres_galarian×28**, jellicent×5,
lapras×5, regidrago×5, corviknight×4, tinkaton×4, empoleon×2,
feraligatr×2, florges×2, dondozo×1.

**Galarian Moltres concentration is the single biggest finding
of this session.** 28/29 big-delta records involve Moltres-G.
Moveset: `SUCKER_PUNCH / FLY, BRAVE_BIRD`. Deltas run both ways:

| matchup                        | shields   | Δ p1 | turns ours / pv |
| ------------------------------ | --------- | ---- | --------------- |
| lapras vs moltres_galarian     | 0-1       | +352 | 27 / 33         |
| moltres_galarian vs regidrago  | 1-0       | -178 | 24 / 29         |
| empoleon vs moltres_galarian   | 0-2       | -171 | 26 / 27         |
| moltres_galarian vs feraligatr | 2-1       | +171 | 30 / 31         |
| moltres_galarian vs florges    | 2-0       | +165 | 30 / 31         |
| jellicent vs moltres_galarian  | 0-{0,1,2} | -146 | 23 / 29         |

Candidate causes (not yet localized — these are hypotheses for a
follow-up localization session, same paradigm as the Forr/Azu DP
writeup):

1. **Brave Bird self-debuff demote**. Brave Bird is -3 atk
   self-debuff, cost 55. Our bandaids at `battle.py:1378-1420`
   (lines [866], [876]) aggressively deprioritize self-debuffing
   moves. If PvPoke throws BB more eagerly than we do, the
   matchups where *Moltres dies before farming enough energy for
   BB* will favor PvPoke, and *matchups where BB is strictly bad*
   will favor us. The bi-directional delta pattern is consistent
   with this.
2. **Sucker Punch fast-move timing**. Sucker Punch is a 2-turn,
   7-damage, 7-energy fast move. No PvPoke-specific timing
   interaction expected, but worth double-checking our turn
   accounting against the harness `decisionLog`.
3. **Opponent-DP side**. In matchups where opponent's DP differs,
   the delta may not be Moltres-G's own play at all. Need to trace
   the harness `dpPlans` to see which side's plan diverges.

**Not regressions (likely)**:
* UL lapras vs moltres-G 0-1: our Moltres dies slower (33→27 turns
  in our favor; we beat PvPoke by 352). Plausibly "we shield
  better" or "PvPoke throws BB and gets nuked" — may well be
  current-xfail territory.
* UL jellicent vs moltres-G 0-1/0-2 (-146 three times at identical
  scores): PvPoke gives Moltres shields that don't matter; the
  0-{0,1,2} columns collapsing to the same output suggests PvPoke
  never uses any shields Moltres has — consistent with a plan where
  Moltres doesn't throw charged moves until fast-move KO against
  Jellicent. Worth a `xfail` documentation pass if we confirm.

### 1c. Score-sum sanity

Both sides' `pvpoke_score` always sum to 999 (floor rounding of
two halves, 500 per side → max 1000, floor-of-0 corner case brings
one case to 998). Spot-checked 20 records; no conservation
violations. Harness and our sim agree on the invariant.

---

## 2. Unimplemented-feature audit

PvPoke reference:
* `~/coding/MGLPoGo/pvpoke/src/js/battle/actions/ActionLogic.js` (1215 lines)
* `~/coding/MGLPoGo/pvpoke/src/js/pokemon/Pokemon.js` (2502 lines)
* `~/coding/MGLPoGo/pvpoke/src/js/battle/Battle.js` (1987 lines)

Ours:
* `src/gopvpsim/battle.py` (2105 lines), `src/gopvpsim/_dp_jit.py` (366 lines)

### Summary

| Feature                                                           | Status                       | Plausible impact                   | Fix sketch                                                                                                                |
| ----------------------------------------------------------------- | ---------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `needsBoost` plan-pick (ActionLogic.js:793-810)                   | **Missing**                  | Medium (buff races)                | Track `turnsToKO` both sides; when opp KO first, pick stateList member with highest `.chance`                             |
| Chance-<1 buff handling in DP (ActionLogic.js:519-535)            | **Implemented**              | —                                  | Shipped 2026-04-15 via `atk_stage`; partial-chance contributions correctly zeroed                                         |
| Form-change coverage (Pokemon.js:2344 `changeForm`)               | **Implemented (3 families)** | Low — no new forms in current meta | Gamemaster-driven; Morpeko/Aegislash/Mimikyu handled; Eiscue/Palafin/Cramorant would need new handlers if they enter meta |
| selfDebuffing demote heuristics (ActionLogic.js:861-935 bandaids) | **Implemented**              | —                                  | All 5 bandaids at battle.py:1365-1512                                                                                     |
| `selectBestChargedMove` / `resetMoves` / `initializeMove`         | **Implemented (inlined)**    | —                                  | priority-shuffle replicated in `pvpoke_dp` 2026-04-14                                                                     |
| `buffChanceModifier` (Battle.js:72, setter at line 227)           | **Missing**                  | None in PvP simulate               | Not used in `Battle.simulate()`; emulator-only                                                                            |
| `decisionMethod="random"` (Battle.js:28)                          | **Missing**                  | None in PvP simulate               | Not used in simulate; emulator-only                                                                                       |
| Energy-lead / timing knobs (Battle.js raidMode, sandbox, etc.)    | **N/A**                      | None                               | Raid/sandbox codepaths are not PvP simulate                                                                               |
| CMP tie-break / priority                                          | **Implemented**              | —                                  | `use_priority = (p0.atk != p1.atk)` at battle.py:1860                                                                     |

### Detail on `needsBoost`

Confirmed read: ActionLogic.js:793-810 builds a plan list
(`stateList`) and, when `opponent.turnsToKO != -1 &&
poke.turnsToKO > opponent.turnsToKO`, picks the member with the
highest `.chance` field (log string: "changes its plan because it
needs the BOOST to win or debuff"). Line 868 gates a downstream
plan reordering on the same flag.

Our `pvpoke_dp` has no `turnsToKO`, no `needsBoost`, no stateList
— it runs until the first KO-bearing terminal pops from the
priority queue and returns a single `_DPState`. Evidence (grep):
no occurrence of `needsBoost`, `needs_boost`, `turnsToKO`, or
`turns_to_ko` anywhere in `src/`.

**Triage before fixing.** This may not bite the current grid —
the `.chance` field is only set by chance-<1 buff moves, which
our atk_stage port filters out (chance-1 only). Moves like
`ANCIENT_POWER` with `buffApplyChance < 1` would be the trigger.
If no current-meta species has a chance-<1 buff move in its
ranked moveset, `needsBoost` is dormant and the fix is low
priority. Worth a one-shot enumeration: grep the GL/UL rankings
for species with any `buffApplyChance < 1` move before deciding
priority.

### Notes on "implemented" claims

An Explore subagent's initial pass on the audit listed the
bandaids and form-change coverage as fully implemented. Spot-
checked lines 1365-1512 in `battle.py` against ActionLogic.js
861-935 — all five bandaids ([861], [866], [871], [876], [881])
are present and cite line numbers. Priority-shuffle replication
is documented in CHANGELOG 2026-04-14.

I did **not** exhaustively diff every Pokemon.js utility method.
A lower-confidence follow-up is worth doing: focused on
`initializeMove`'s `.chance` field propagation, since that's the
hook `needsBoost` reads.

---

## 3. Test-gap analysis

The DP is almost entirely oracle-verified (pytest integration
tests + harness). That's brittle: when the DP regresses, the
oracle tests tell you *that* the final score moved, not *which
state-transition rule* changed. Three small unit tests against
fabricated `_DPState` inputs or small `BattlePokemon` fixtures
would catch whole classes of regressions at the right altitude.

### Proposed tests

1. **`test_dp_insert_ready_dedup_preserves_atk_stage`**
   `_dp_insert_ready`'s phase-1 dedup was tightened 2026-04-15 to
   require equal `atk_stage`. A unit test that constructs two
   `_DPState` entries with same `(turn, energy, hp, shields)` but
   different `atk_stage`, calls `_dp_insert_ready` on the second,
   and asserts both survive would lock that invariant in. Currently
   only covered by Azu/Forr (Sand+Rock) oracle 9/9. If someone
   "simplifies" the dedup back, only the oracle catches it.

2. **`test_dp_atk_stage_damage_table_indexing`**
   Directly exercise `cm_dmgs_by_stage[stage + 4]` and
   `fast_dmg_by_stage[stage + 4]` with a fabricated attacker
   whose `_ensure_dmg_cache` was populated manually. Assert that
   a +1 atk stage yields exactly `_stat_stage_mult(1)` times the
   base damage (modulo the floor in `calc_damage`). The offset-by-4
   indexing is a frequent source of off-by-one regressions; a unit
   test is cheap insurance.

3. **`test_pvpoke_dp_farm_down_energy_vs_throw`**
   The CD cycle-timing issue (TODO: "DP cycle-timing move
   selection") is the known case where our DP picks high-DPE PR
   over low-DPE IB when IB allows an extra throw. A unit test that
   constructs a near-KO scenario where throwing the cheaper move
   yields *more* total damage, and asserts the expected choice,
   would both pin down current (wrong) behavior as `xfail` and
   serve as the regression gate when the fix lands.

4. **`test_selfdebuffing_bandaid_866_gate`**
   Bandaid [866] ("avoid self-debuff when shields down, opponent
   healthy, KO not guaranteed") gates on `move.damage / defender.hp
   < 0.8`, where `move.damage` is only populated as a side effect
   of OMT's can-KO check. A unit test that constructs the gating
   conditions with `_cached_damage` explicitly set to None, set
   below 0.8, and set above 0.8 would pin each branch. Currently
   this bandaid fires or doesn't based on upstream state that's
   not obvious from the test inputs.

5. **`test_pvpoke_dp_no_ko_fallback_returns_best_dpe`**
   When the DP can't find a KO state (e.g., very tanky opponent,
   low energy), `pvpoke_dp` falls back to the highest-actual_dpe
   affordable move. Construct a fixture where no KO is reachable
   and assert the fallback picks the expected index. One-liner
   test, catches regressions where future refactors forget the
   fallback path exists.

Priority: (1) and (2) are cheap and guard the atk_stage fix
that just shipped. (3) is worth doing alongside the DP
cycle-timing fix. (4) and (5) are nice-to-have.

---

## 4. Code-health observations

Per the "defer infra refactors until they hurt" feedback, only
flagging things that would reduce friction *for the specific
follow-ups this report names*.

* **`pvpoke_dp` is ~500 lines and cited 4 times above** (needsBoost
  addition, cycle-timing fix, self-debuff gate test, farm-down
  fallback test). If the next session touches any two of those,
  it's worth extracting the post-DP bandaid chain (lines
  1363-1512) into a named helper. Not before. The precompute
  section (lines 814-898) is also factorable but the coupling to
  `actual_dpe` / `raw_dpe` / `_get_dmg` closures makes the split
  non-trivial.
* **`_DPState` now carries 9 fields.** The dataclass is fine; but
  the `_dp_insert_*` dedup clauses reference them by positional
  attribute access, which made the 2026-04-15 `atk_stage` add more
  invasive than it needed to be. A `_DPState.dedup_key()` method
  that returns the tuple the insert functions compare on would
  localize future additions. Low priority.
* **Harness grid script (new in this session)**: `scripts/harness_
  grid.py` duplicates the BattlePokemon-building logic from
  `scripts/battle.py:make_battle_pokemon`. If a future session
  adds another harness-driven script, extract to a shared helper
  (`scripts/_battle_factory.py`). Two call sites isn't enough yet.

---

## 5. Follow-up agenda

In rough priority order:

1. **Localize the Empoleon vs Forretress 2-2 divergence (-204).**
   Forretress DP on opponent-debuffed-atk state never throws Sand
   Tomb. Single cleanest GL divergence. Same paradigm as the
   2026-04-15 atk_stage writeup — harness `dpPlans`, compare
   Forretress's finalState at the point our sim stays on VS.
2. **Triage the Galarian Moltres cluster (28 UL records).** Start
   with lapras vs moltres-G 0-1 (+352, our favor). Compare
   charged-move sequences via harness `chargedLog`. Likely
   outcome: 1-2 of these are existing xfails (PvPoke throws BB
   we correctly demote), 1-2 are real regressions.
3. **Enumerate current-meta species with any chance-<1 buff
   move** to decide `needsBoost` priority. If none, defer.
4. **Add the 3 high-priority unit tests** (dp_insert_ready
   dedup, atk_stage indexing, no-KO fallback) in a dedicated
   test-hardening session.
5. **Consider changing `simulate()`'s default `charged_policy`
   from `bait_with_cheapest` to `pvpoke_dp`.** The fact that this
   report almost shipped with bogus data because of that default
   is evidence the default is a trap. Needs a scan of every
   caller first — out of scope here.
