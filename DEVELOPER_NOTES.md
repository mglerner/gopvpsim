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

### 4. Mimikyu SS timing: delayed by 1 Shadow Claw

**File**: Unknown - may be in fast-move damage delivery timing

PvPoke delays Mimikyu's first Shadow Sneak by one extra Shadow Claw
(8 SCs instead of 7 before firing SS) in the Mimikyu vs Azumarill
matchup. Mimikyu reaches 56 energy (50 needed for SS) after 7 SCs at
turn 14, and should fire SS at turn 15. Instead PvPoke queues an 8th
SC, lets Azu's IB break the disguise, then fires SS afterward.

Our code fires SS at the first opportunity (7 SCs), which is strictly
better for Mimikyu: it burns Azu's shield sooner, shortening the
battle by ~2 turns and landing 1 extra Shadow Claw (5 dmg = 13 score
points). Confirmed by score comparison: our Mimikyu gets 363 vs
PvPoke's 350 in the 0v1 scenario, and the +/-13 delta is consistent
across all three affected shield scenarios.

Exact root cause in PvPoke's code unclear - extensive code reading
found no OMT trigger, farm-down delay, or decision-ordering issue
that would explain the delay. May require running PvPoke locally
with debug logging.

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
