# New-mechanics decision layer: is the AI legacy-brained? (2026-06-24)

Point-in-time writeup of the Phase-1 investigation for the `--mechanics new`
turn system (the 2026-06-23 in-game PvP change). **Status: RESOLVED for ship.**
Result: ship pure plumbing (new == legacy decisions) + the threading scaffold;
the decision layer does not need re-optimization for the new clock right now.
**There is a real, reproducible sub-optimality we are knowingly deferring
post-ship — see "Known sub-optimal cases (come back to this)" below.**

## The question

Under `mechanics='new'` only the RESOLUTION layer changed (fast damage/energy
resolve end-of-turn; a charged move chosen turn N resolves at the START of N+1
AND survives the thrower's death). The DECISION layer (`pvpoke_dp`,
`_calc_turns_to_live`, `_optimize_move_timing`, `would_shield`) still runs the
LEGACY heuristics. Phase 1's HARD GATE: is that AI playing sensibly, or is it a
"legacy-brained pilot on a new clock" producing plausible-but-wrong numbers?

## Method

Three background workflows, all measuring against a **hard non-regression
floor**: for every matchup x shield, `score(new-resolution + candidate-decisions)`
must be >= `score(new-resolution + legacy-decisions)`. The legacy heuristics are
PvPoke-validated, so "never play worse than legacy does on the new clock" is the
floor; gains on top of it are the goal. There is NO external oracle for the new
clock (PvPoke never implemented it).

Tooling (kept as the resume mechanism — see "How to resume"):
- `scripts/corpus_new_decisions.py` — per-focal corpus: regressions + the
  decisive-commit candidate detector (focal lost holding chargeable energy).
- `scripts/corpus_policy_driver.py` — `compare(focal, shadow, focal_policy)`:
  sweeps a focal vs the full GL pool x 9 shields under `new`, contrasting a
  candidate focal policy against the forced-legacy baseline (opponent forced
  legacy in BOTH runs, so only the focal's decision varies). Returns per-cell
  regressions (floor violations) and gains. Self-test: candidate==legacy -> 0/0.

Decision changes were tested as **pluggable policies** (wrapping `pvpoke_dp`
with mechanics-gated overrides) — no `battle.py` edits needed to measure.

## Finding (the core thesis)

**The new turn rules barely change optimal DECISIONS; they change RESOLUTION.**
Legacy decisions on the new clock are near-optimal. The reason is structural and
showed up identically across every lever tested:

> The single most-anticipated new-mechanics decision edge -- "fire a held
> charged before you die so it still lands post-mortem" -- is ALREADY delivered
> by the RESOLUTION layer, not the decision layer. Under `new`, the legacy DP's
> waited-for high-damage move already lands on the dying turn because the charged
> survives death. So the classic "died holding an unfired better move" pathology
> that a decision change would repair simply does not exist anymore.

Empirically confirmed: across 5 focals, **208 cells** end with the focal dead
holding an affordable charged move, and every one is a CORRECT bait/farm
end-state where the held move resolves post-mortem -- not a wait-to-death loss.

Every attempt to commit charges more aggressively collides with the same wall:
OMT delays and farm-holds protect ENERGY ECONOMY and SHIELD-BAIT timing, not
death timing, and post-mortem survival does NOT make skipping them safe. Firing
early hands free value to opponents who farm/bait instead of throwing.

### Reverted / cut attempts and why they regressed

| Attempt                                                             | Floor result                              | Killer case                                                                                                                                      |
| ------------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| TTL+1 / OMT+1 (charged-KO lands +1)                                 | regressed                                 | Aegislash (Blade) vs Tinkaton [2,1] 644 -> 132 (inflated ttl made `fire_now` DELAY the lethal charge; glass cannon bled out)                     |
| Broad decisive-commit (fire if opp's *affordable* charged could KO) | regressed                                 | Feraligatr vs Jumpluff (S) [1,0] 908 -> 398 (opp was baiting, didn't throw; premature commit)                                                    |
| farm-gate-death-commit (NARROWED)                                   | **regressed beyond Aegislash**            | Tinkaton vs Talonflame [2,0] 569 -> 423; +5 more, net -517 over 20 focals. Was floor-clean on the 2 Aegislash forms ONLY -- a sampling artifact. |
| anti-bait-wait-to-death                                             | washout + 1 violation                     | post-mortem survival already lands the waited move                                                                                               |
| shield-timing under new                                             | grounded washout (0/0, 3249 cells)        | the +1 is symmetric on the only turn-clock-dependent shield gate (selfDefenseDebuffing cycle-KO) and cancels                                     |
| less-eager-OMT                                                      | helps_with_regressions (29 reg / 79 gain) | the 0-regression narrowing is a pure washout (pre-OMT lethal-throw already fires it)                                                             |

## Known sub-optimal cases (COME BACK TO THIS, post-ship)

We are knowingly shipping a strategy that is **provably beaten in at least one
reproducible case**, because no *generalizable* counter-strategy clears the floor.

**The one floor-clean, reproducible win we are NOT taking:**
`decisive-commit-fast-lethal, globalmax@1.25` -- when the focal is about to die
to the opponent's fast (`hp <= 1.25 * opp_fast_dmg`), `opp.shields == 0`, the
legacy choice is to delay (`base is None`), and the focal's affordable-best
charged is ALSO its global-max-damage charged, commit it now.
- **0 floor violations across 20 focals / 12,969 cells**, verified.
- **Exactly ONE gain cell:** Aegislash (Shield) vs Talonflame (Shadow) [0,0]
  515 -> 595 (+80). Mechanism: its post-mortem Shadow Ball lands T20 instead of
  legacy's T26, banking ~146 chip earlier.
- Threshold ceiling is load-bearing: at THRESH=1.5 it reintroduces an
  Aegislash (Shield) vs Dewgong [2,2] 403 -> 390 violation. 1.25 is the verified
  ceiling.
- We DROP it because a single +80 edge cell is not worth a bolt-on special-case
  branch ahead of the DP (surgical-change policy).

**Why there's no generalizable counter-strategy (the open problem):** the
"commit early because I'll die" idea is right in isolation but the trigger keyed
on the opponent's *affordable* (threat-ceiling) charged fires when the opponent
is actually baiting/farming and won't throw it, so the early commit burns the
focal's energy/shield-bait economy. Every broad formulation breaks the floor on
shield-bait-timing species (Tinkaton, Mantine, Jumpluff-S, Quagsire-S). The only
safe trigger (provably-dead-to-fast-this-turn) overlaps almost entirely with the
existing `fire_now` TTL=1 logic, leaving just the single Aegislash cell.

**Recommended future direction:** the genuine fix, if pursued, likely belongs
INSIDE the DP -- `_calc_turns_to_live` / the `fire_now` path -- making the plan
natively aware of charged-survives-death (so it values committing the best
already-held charge on the dying turn) rather than a bolt-on commit branch. That
is a battle.py-internal change with real regression surface; do it only with the
corpus floor as the gate, and only if a broader class of gains is found.

## Coverage caveats (close these before any broad claim)

1. **Great League only.** UL and ML are untested. Mimikyu is PvPoke #1 in BOTH
   GL and UL, so a UL corpus pass matters. The decision code is league-agnostic,
   but the floor guarantee has only been established for GL.
2. **Focal coverage is a curated ~20-species subset, not all ~71.** The
   opponent side is the full GL meta; the focal side is the timing-sensitive +
   meta-relevant subset. The farm-gate floor breach was caught precisely BECAUSE
   the adversary widened the focal set beyond the lever's sample -- a reminder
   that floor guarantees must be re-established corpus-wide, never assumed from a
   sample.

## How to resume

1. Confirm the baseline is still clean: `python scripts/corpus_policy_driver.py
   --focal "<species>"` (candidate==legacy -> 0/0).
2. Express a candidate as a focal policy wrapping `pvpoke_dp(..., 'legacy')` with
   a `mechanics=='new'` override; run `compare()` across ALL dive-relevant focals
   (extend to UL/ML pools), require ZERO floor violations.
3. The `globalmax@1.25` win and the farm-gate breaches above are the regression
   fixtures any new attempt must reproduce/avoid.
