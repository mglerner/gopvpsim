# Developer Notes

## Current status (2026-04-06)

99/102 integration tests pass. The simulator matches PvPoke's simulate-mode
score table exactly (±0) for 7 matchups (63 cells). The 3 remaining failures
are all Mienfoo vs Medicham, root-caused to a `bestChargedMove` selection
difference (see below).

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

### Remaining 3 failures: Mienfoo vs Medicham (1v0, 1v1, 2v1)

Root cause: `bestChargedMove` selection. PvPoke selects it in
`initializeStats` using `move.damage / move.energy`, but `move.damage`
is undefined at init time (only set later as a side effect of
`wouldShield`). This gives NaN DPE, so bestChargedMove defaults to the
cheapest move. Our code uses actual DPE computed per call, picking HJK
instead of LS. This changes whether Mienfoo enters the DP or stays in
farm-down mode. See "PvPoke bugs" below — this is likely a PvPoke bug.

## PvPoke bugs found

Two bugs in PvPoke's JavaScript that we've identified and documented.
Both should be reported upstream.

### 1. BattleState .hp/.oppHealth naming inconsistency

**File**: `ActionLogic.js:1187` (class definition) vs lines 479, 600, 697

PvPoke's `BattleState` stores `.oppHealth` and `.oppShields`, but the
dominance checks reference `.hp` and `.shields` (undefined in JS →
always false → dead code). The dedup check at line 545 correctly uses
`.oppHealth`.

We added an `intended_pruning` flag to `pvpoke_dp` that toggles between
PvPoke's actual behavior (dead-code pruning, `False`) and the apparently
intended behavior (functional pruning, `True`).

### 2. bestChargedMove uses undefined move.damage

**File**: `Pokemon.js:791`

`bestChargedMove` is selected using `move.damage / move.energy` for DPE.
But `move.damage` is only set later as a side effect of `wouldShield`
(ActionLogic.js line 1103). At init time, `move.damage` is undefined →
`move.dpe = NaN` → DPE comparison always fails → defaults to cheapest move.

PvPoke probably intended `move.power / move.energy` (raw DPE).

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
