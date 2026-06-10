# 2026-06-10 — Damage-signature dedup in IV sweeps (arc S3)

Arc session S3 (`~/.claude/plans/perf-correctness-arc-2026-06.md`).
Goal: a provably exact multi-x reduction in sweep sims, exploiting
the fact that damage floors — the very reason breakpoints exist —
collapse many distinct stat lines onto identical battles.

## The theorem

A battle's evolution is fully determined by the engine's inputs. The
audit of `battle.py` / `_dp_jit.py` (this session) found that the
focal Pokemon's stats enter a battle through exactly three channels:

1. **Damage tables.** Every damage number flows through
   `moves.damage(power, atk * stage_mult, def_ * stage_mult, eff,
   stab)` — floor-quantized. (`_ensure_dmg_cache`,
   `_ensure_dp_cache`; `_dp_jit` consumes only the prebuilt tables.)
2. **CMP.** Pairwise attack comparisons between the two combatants —
   battle.py lines 227, 358, 422, 625, 1005, 2153, 2246, 2273. The
   engine uses `>`, `>=`, `<`, and `!=` flavors, so the signature
   carries the **3-way sign** of (focal.atk − opp.atk), not a boolean.
3. **HP.** Integer max HP.

Everything else (moves, types, energy, cooldowns, buff config, form
triggers, shield counts) is identical across the IV profiles of one
sweep. Therefore: two profiles whose damage tables (both directions),
CMP sign, and HP all match vs a given opponent fight bit-identical
battles in every shield scenario — sim one, fan the score out.

Three subtleties the signature handles (`scripts/deep_dive_signature.py`):

- **Stat stages.** Damage depends on the (atk stage, def stage) pair,
  range −4..+4 each. A stage axis is included in the table only when
  something can move it: `_apply_move_buffs` (buffTarget-aware,
  `buffApplyChance > 0` — the deterministic meter fires eventually),
  `would_shield`'s temporary projection (which IGNORES buffTarget:
  any charged move with `buffs[0] > 0` shifts the thrower's atk
  stage, otherwise `buffs[1]` shifts the decider's def stage), and
  form-change `nativeStatBuffs`. Unmovable axes pin to stage 0 and
  contribute one damage row instead of nine.
- **Form changes.** For Aegislash/Mimikyu/Morpeko (either side) the
  signature includes damage tables and CMP signs for every
  (focal form × opponent form) combination, built from
  `build_form_change_state`'s per-IV alt stats — exactly the values
  `apply_form_change` installs mid-battle. This addresses the S1
  hazard note: a signature computed only against the default form
  would wrongly merge IVs whose Blade forms differ.
- **Float exactness.** `damage_vec` mirrors `moves.damage`'s operand
  order left-to-right; IEEE-754 float64 elementwise numpy ops are
  bit-identical to Python scalar float ops, so the vectorized floors
  match `math.floor` per element (pinned by
  `tests/test_signature_dedup.py`).

## Implementation

`iv_sweep` (deep_dive.py) computes signature groups per opponent in
the parent (vectorized, ~10s of ms per opponent), then dispatches
(representative profile, opponent) pairs to the existing worker pool
— ~100 chunks as before, so load balancing is unchanged. The worker
contract changed from "profile × all opponents" to "(profile,
opponent) pair × all scenarios"; scores fan out to group members in
the parent. `--no-signature-dedup` restores the per-profile path.
The per-dive dedup factor is logged at sweep start
(`signature dedup: P profiles x O opponents -> N representative
pairs (F.FFx)`).

## Verification (the point of the session)

`scripts/verify_signature_dedup.py` runs the full sweep both ways and
asserts the rounded canonical arrays AND the raw per-IV float scores
are exactly equal. 2026-06-10 run — great league, top-20 rankings
opponents + Aegislash (Shield) appended (covers opponent-side form
change), all 9 shield scenarios, 774,144 score cells per species per
mode:

| Species            | Why chosen                      | Dedup factor | Wall-clock | Result |
| ------------------ | ------------------------------- | ------------ | ---------- | ------ |
| Azumarill          | no buff moves anywhere          | 4.50x        | 4.07x      | EXACT  |
| Tinkaton           | Bulldoze (opp def debuff) + Zap | 2.23x        | 2.13x      | EXACT  |
|                    | Cannon/Icy-Wind-class opponents |              |            |        |
| Tinkaton (nobait)  | bait-axis policy independence   | 2.23x        | 2.16x      | EXACT  |
| Aegislash (Shield) | focal form change, per-IV sweep | 1.43x        | 1.36x      | EXACT  |

Unit-level coverage (`tests/test_signature_dedup.py`, +5 tests,
sentinel 724→729): bitwise damage_vec == moves.damage across real
swept stats × all 9 stage multipliers × STAB/SE/NVE/0-power moves;
member-vs-representative score equality where EVERY group member is
simmed (Tinkaton and Aegislash (Shield)); axis-movability cases.

## Reading the factors

- **No-buff matchups dedup hardest** (Azumarill 4.5x): only the
  stage-0 damage rows + CMP + HP discriminate, and damage floors
  collapse aggressively.
- **Buff moves shrink the win** (Tinkaton 2.2x): a movable stage axis
  multiplies the damage-table rows by up to 9, and profiles must
  agree at every reachable stage, not just stage 0. Still exact —
  just more conservative. (Refinement headroom: restrict to stages
  actually reachable from the specific buff deltas, e.g. Bulldoze
  can only push opp def DOWN; not worth it until a dive shows a
  pathological pool.)
- **Form-change species gain least but still gain** (Aegislash
  1.43x): the S1 per-IV expansion (4,096 sims-per-opponent where
  stat-profile dedup would have given ~2,000) is more than clawed
  back — effective groups average 2,861/opponent, and unlike
  stat-profile dedup this is provably exact under form mechanics.
- The bait axis shares the grouping exactly (identical
  28,063-pair partition both modes), as designed — the signature is
  policy-independent.

Real-dive expectation: website GL dives (~60 opponents, 9 scenarios,
mixed-buff pools) should land between the Tinkaton and Azumarill
factors per moveset sweep, i.e. **roughly 2-4x less sweep wall-clock**.
S6's full re-dive will provide the real-world numbers.

## Engine untouched

`battle.py`, `_dp_jit.py`, `moves.py` unchanged (read-only audit), so
the 2,278 sims/s regression gate did not require a re-run; the oracle
harness is likewise unaffected. The change surface is
`scripts/deep_dive.py` (sweep orchestration), the new
`scripts/deep_dive_signature.py`, and tests.

## Future options (not done)

- Slayer-iteration rounds (`deep_dive_slayer.py`) could reuse
  `signature_groups` — S2 already cut those rounds ~95x, so the
  marginal win is small; revisit if slayer phases grow again.
- The signature is the principled key for any future battle-level
  cross-dive cache (S4 question from Michael, 2026-06-10): keyed on
  (signature, opponent identity, scenario) it would be exact across
  dives — but measured overlap between an X-dive and a Y-dive is ~18
  of ~2M sims (the single pool-IV × pool-IV cell), the same wall the
  2026-04-07 pvpoke_dp memoization probe hit. Not worth building;
  S4's whole-sweep disk cache remains the plan.
