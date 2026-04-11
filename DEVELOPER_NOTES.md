# Developer Notes

## Current status (2026-04-06)

120 tests pass (102 original + 9 shadow + 9 Corviknight mirror). The simulator matches PvPoke's
simulate-mode score table exactly (±0) for 8 matchups (72 cells). The 3
remaining failures are all Mienfoo vs Medicham, root-caused to a
`bestChargedMove` selection difference (see below).

### Verified correct
- **Type effectiveness**: All 324 matchups match PvPoke exactly
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

### Previously failing: Mienfoo vs Medicham — FIXED (all 9/9)

Two bugs were found and fixed:

1. **wouldShield buff reset ordering** (battle.py `would_shield`):
   The charged-move threat loop ran BEFORE resetting the temporarily-
   applied stat buffs, inflating damage predictions. PvPoke resets
   buffs first (ActionLogic.js:1136-1140), then evaluates charged-move
   threat (lines 1145-1165). Fix: moved the reset before the loop.

2. **CMP (Charge Move Priority) cancellation** (battle.py `simulate`):
   When both Pokemon fire charged moves simultaneously, the lower-ATK
   Pokemon's move should be canceled if it was KO'd by the higher-ATK
   Pokemon's charged move (PvPoke Battle.js:464-467). Our code had an
   exception that always allowed both to fire. Fix: track `charged_ko`
   set and cancel if `use_priority` and attacker was KO'd by a charged
   move.

## Known divergences vs iv-tech reference writeups

### Corviknight 2v2 bait-twice vs Shadow Sableye (2026-04-12)

`docs/corviknight_deep_dive_reference.md:58` claims that max-def
Corviknight (0/15/2, def=135.47, "135.46 def") flips the 2-shield
matchup against default-IV Shadow Sableye (4/15/15 @ lvl 47) *"if you
bait twice"*. Our `pvpoke_dp` sim has Corviknight LOSING the 2s
regardless of bait mode (score 288, Corvi 0 HP, Sableye 53 HP):

- **bait_shields=True**:  Corvi throws Sky Attack at T17 and T30 (both
  shielded), then dies to Sableye Shadow Sneak at T37.
- **bait_shields=False**: Corvi throws Sky Attack at T15 and T28 (both
  shielded), then dies to Sableye Shadow Sneak at T37.

In neither mode does Corvi reach Payback (60 energy) — it dies before
accumulating the energy, so the "bait twice with Sky Attack then land a
big Payback" strategy the reference describes is unreachable in our sim.
Possible causes:

1. Our `pvpoke_dp` near-KO DP doesn't find a micro-optimal plan that
   squeezes in the Payback reach. This is plausible — PvPoke's real JS
   has a bunch of `optimizeMoveTiming` + DP knobs that interact in
   subtle ways and our port is exact for the cases we've tested but
   could have gaps.
2. The reference's claim is based on a human-optimal baiting strategy
   that neither PvPoke nor we can actually find via simulation.
3. The reference predates Sky Attack / Payback balance changes and no
   longer reflects the current matchup math.

The 1v1 claim from the same reference ("flips the 1 without baiting")
DOES match our sim — Corvi wins 1v1 in both bait modes. That's covered
by `test_corviknight_max_def_wins_1v1_vs_default_shadow_sableye` in
`tests/test_battle.py`.

Followup: consider round-tripping the 2v2 matchup at pvpoke.com/battle
to see which of the three hypotheses is correct. If it's (1), it's a
genuine pvpoke_dp gap to fix. If it's (2) or (3), we should update the
reference doc with a "divergence confirmed" note.

## PvPoke bugs found

### 1. BattleState .hp/.oppHealth naming inconsistency

**File**: `ActionLogic.js:1187` (class definition) vs lines 479, 600, 697

PvPoke's `BattleState` stores `.oppHealth` and `.oppShields`, but the
dominance checks reference `.hp` and `.shields` (undefined in JS →
always false → dead code). The dedup check at line 545 correctly uses
`.oppHealth`.

We added an `intended_pruning` flag to `pvpoke_dp` that toggles between
PvPoke's actual behavior (dead-code pruning, `False`) and the apparently
intended behavior (functional pruning, `True`).

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
