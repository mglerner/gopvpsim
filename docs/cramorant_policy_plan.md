# Cramorant policy campaign — plan of record

*(Commissioned by Michael 2026-08-24: "for Cram, we want PvPoke's default,
a never-bait, and then our best guess at optimal." Standing resource
authorization for a large multi-agent campaign.)*

## The three tiers

1. **PvPoke default** — the shipped engine port (pvpoke `78c64048a`),
   oracle-verified cell-exact (72 cells). This stays the project default
   everywhere; nothing in this campaign changes shipped behavior.
2. **Never-bait** — already a standard dive axis: the GL/UL dives run
   `--bait both`, so the no-bait line is simmed and rendered on the
   normal pages. No new work.
3. **The "PoGoDives strat"** (Michael 2026-08-24; working name) — a
   candidate optimal policy, to be EARNED with corpus evidence per the
   rules below, not intuited. Architecture is decided up front:
   - A named overlay policy pair (`pogodives_dp` charged policy +
     `pogodives_shield`), implemented as a THIN DISPATCH: when a
     registered special case applies (initially: we are Cramorant, or
     we face Cramorant), apply the tuned rule; in every other situation
     delegate byte-identically to `pvpoke_dp` / PvPoke shielding. The
     non-Cram fallback is a hard invariant (test-pinned: with no
     Cramorant on either side, `pogodives_*` output == PvPoke-default
     output on the full corpus).
   - The special-case registry is the future home for beefed-up
     strategy in OTHER cases — additions land one evidenced case at a
     time, each with its own corpus proof, never by drift.
   - It SHIPS VISIBLY on the dive surfaces (decided in principle;
     exact UI — a policy toggle alongside the bait dropdown, or a
     separately rendered line — is settled when we build the render
     side, with the evidence in hand).

## Why PvPoke's logic is probably beatable (hypotheses to test)

PvPoke's Cramorant logic is five static heuristics bolted onto a DP that
cannot see Gulp Missile (it is not in `activeChargedMoves`, so it appears
in no KO math, no turnsToLive, no wouldShield projection, either side).
Specific seams:

- **H1 — the 1.5-DPE dive gate ignores missile EV.** Vs Azumarill
  (Peck/Dive/Fly) the gate means Cramorant NEVER dives and loses 0v0 by
  489/510 with Azumarill throwing two unshielded Ice Beams — one held
  prey converts an Ice Beam into ~29 flat damage + a guaranteed debuff.
- **H2 — the prey tank threshold (dmg*2.2 < hp) is crude.** Optimal
  tanking depends on shield economy and which prey is held.
- **H3 — prey CHOICE via Dive timing is unexplored.** Gulping (-1 def)
  vs Gorging (-2 atk) is set by the 50% line at Dive time, so Cramorant
  can choose by timing. PvPoke's commit message mentions "waits if just
  above 50% hp" but shipped no such code.
- **H4 — the opponent's lethal-Dive shield rule is inverted**
  (ActionLogic.js:1239, the moveID typo family): opponents never shield
  a lethal Dive. Fixing it opponent-side measures how much of published
  Cramorant strength is this bug (upstream-report ammunition), and our
  "optimal" must not depend on exploiting it.
- **H5 — the strongest counter-play is missing from PvPoke's opponent
  model**: withholding charged moves entirely vs a prey-holder when fast
  pressure suffices. Our candidate must survive it (robustness round).

## Method

### Knobs (engine globals, PvPoke-default values, experiment-only)

`battle.py` module globals, all defaulting to shipped PvPoke behavior —
the engine is byte-identical unless a lab process overrides them:

| knob                           | default | meaning                                         |
| ------------------------------ | ------- | ----------------------------------------------- |
| `_CRAM_DIVE_GATE_DPE`          | 1.5     | dive-ASAP fires iff nonGulp.dpe/gulp.dpe < this |
| `_CRAM_DIVE_GATE_HP`           | 1.3     | ...and opp.hp > nonGulp.damage * this           |
| `_CRAM_TANK_MULT`              | 2.2     | prey-holder tanks charged hits < hp/this        |
| `_CRAM_DELAY_GORGING`          | False   | skip dive-ASAP while hp>50% (choose Pikachu)    |
| `_CRAM_LETHAL_DIVE_SHIELD_FIX` | False   | opponent-side: shield a lethal Dive (bug fixed) |

**WARNING (sweep-cache discipline):** the sweep cache does NOT key on
these globals. Never run a cache-backed sweep/dive with non-default
values — the lab calls `simulate()` directly and never touches the
cache. Opponent 'withhold' counter-policy needs no knob (clean wrapper:
return None instead of throwing).

### Lab: `scripts/cramorant_policy_lab.py`

- Variants = named knob combinations (+ per-side policy wrappers).
- Corpus: GL `gl_top50_plus_cs.txt` + UL `ul_top60.txt` pools, PvPoke
  default IVs both sides, 9 shield cells x both bait modes per pair.
- Baseline sanity gate: the all-defaults variant must reproduce the
  no-knob engine bit-exactly (hard-fail otherwise).
- Output: per-cell JSON (variant, league, opp, cell, bait, score,
  winner) + flip lists vs baseline.
- Compute is cheap (~minutes at ~6.5k sims/s single-proc); the budget
  goes to analysis.

### Rounds

1. **Grid sweep**: knob grid (DPE gate {0, 1.5, 3.0, inf}, HP gate
   {1.0, 1.3}, tank {1.4, 1.8, 2.2, 2.6, always-shield},
   delay-gorging {on, off}) x leagues x baits.
2. **Agent analysis panel** (Opus): dominance analysis, per-opponent
   flip accounting, non-regression floors. The 2026-06-24 decision-layer
   lesson is the standing bar: candidate policies must beat the floor on
   the corpus, not in anecdotes; expect most intuitive "improvements" to
   wash out.
3. **Robustness round**: surviving candidates re-run vs (a) opponent
   withhold counter-policy, (b) `_CRAM_LETHAL_DIVE_SHIELD_FIX=True`
   opponents, (c) a spread of Cramorant/opponent IVs (rank-1 + extremes)
   to catch knife-edge overfitting.
4. **Adversarial verify**: independent skeptic agents re-derive the
   winner from the raw JSON; kill findings that don't reproduce.
5. **Synthesis**: writeup in `docs/validations/` (grids, flip tables,
   the chosen "best Cram" definition, and the explicit list of cells
   where it LOSES vs PvPoke-default), plus the H4 measurement packaged
   for an upstream bug report draft. The winning knob set is then
   frozen into `pogodives_dp` / `pogodives_shield` (the overlay pair in
   tier 3 above) with the non-Cram-fallback invariant test, and the
   dive-surface rendering becomes its own scoped task.

### Sequencing

Queued AFTER: (1) the port commit + adversarial-review fixes, (2) the
sweep-cache migrations, (3) the GL + UL website dives (detached, CPU
priority). The lab build can proceed while dives run (no engine-file
edits); experiments launch once dives finish.

## Out of scope (explicitly)

- Missile-aware DP state (holding-prey in the plan search): only if
  rounds 1-3 show the cheap knobs leave big wins on the table.
- Game-tree/minimax opponents (standing out-of-scope).
- Shipping any non-default policy as a dive default.
