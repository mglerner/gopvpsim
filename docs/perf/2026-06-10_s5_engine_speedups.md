# 2026-06-10 — S5: TTL JIT + DP-cache precompute + reachable stage rows

Arc session S5 (`~/.claude/plans/perf-correctness-arc-2026-06.md`).
Goal was the remaining single-core engine headroom after the
regression fix (`5e25e28`/`154536a`). Shipped in four commits, each
gated on the full suite + oracle harness + the canonical benchmark.

Canonical benchmark throughout: `python scripts/profile_slayer.py
--n-focal 60 --n-opp 20` (Annihilape mirror, single process), warm
JIT cache, 3 runs per measurement.

## Results

| Commit    | Change                                        | sims/s (warm) | Step  |
| --------- | --------------------------------------------- | ------------- | ----- |
| `87c209c` | S4 baseline (re-measured this session)        | 2,294-2,299   | —     |
| `4c38c6a` | S5a: `_calc_turns_to_live` JIT, defender bufs | 2,334-2,344   | +1.8% |
| `40b0168` | S5b: reachable-rows-only DP stage tables      | 2,524-2,535   | +8.2% |
| `840bbd8` | S5c: DP-cache precompute + bandaid array-ify  | 3,028-3,099   | +20%  |
| `d4d8ed2` | S5d: explicit JIT signatures                  | 3,139-3,177   | +2-3% |

**Net: ~2,295 → ~3,160 sims/s, +37.5% single-core** — at the top of
the plan's 25-35% estimate. New regression-gate baseline: **3,160**.

End-to-end confirmation (multiprocess): Tinkaton GL smoke dive
(`--opponents 20 --reserve-cpus 1 --no-sweep-cache`, 9 workers, same
shape as the holistic-review measurement): interactive sweeps
21,157-23,792 sims/s vs 16,073-16,947 post-regression-fix — ~+33%
at the dive level.

## What each step did

**S5a — turnsToLive JIT (`_dp_jit._calc_ttl_jit`).** The round-3
false start (2026-04-07) died on per-call `np.asarray`; the fix is
int64 buffers (`_cached_charged_dmgs_np` / `_cm_energy_np`) rebuilt
alongside the damage cache, so the kernel call marshals nothing.
Honest accounting: most of the kernel savings go straight to numba
dispatch overhead (~0.5μs/call × 345k calls) because the TTL
exploration is tiny after pruning — hence only +1.8%. Kept because
it's exact, tested, and the dispatch cost is fixed while the kernel
cost scales with harder matchups.

**S5b — reachable stage rows.** `_ensure_dp_cache` rebuilt all 9
per-atk-stage damage rows via `calc_damage` on every rebuild (~97%
of all damage computations in the post-fix profile). Three
exactness-preserving observations:

1. The root-stage row equals the damage cache (identical
   `calc_damage` inputs) — reuse, don't recompute.
2. If no charged move carries a chance-1 atk-stage delta
   (`cm_buff_delta` all zero — most movesets), the plan exploration
   can never leave the current stage: the cache key pins the entry to
   one `atk_stage` and only buff deltas move the row index mid-plan.
   All rows alias the root row; zero stage-table damage calls.
3. Mixed movesets (Annihilape's +1-atk Rage Fist): rows above root
   are reachable only via a positive delta, below root only via a
   negative one — fill unreachable rows with the root reference.

The Annihilape benchmark is near worst-case for this change (Rage
Fist forces the eager path) and still gained +8.2%; zero-delta
species skip the stage loop entirely.

**S5c — DP-cache precompute + bandaid array-ify (the big one).**
PvPoke's bestChargedMove selection loop, `bestCycleDamage`, the
farm-down cycle threshold, and the debuf-swap selection depend only
on cache-key-stable inputs — moved verbatim from per-call `pvpoke_dp`
(~32 calls/sim) into the `_ensure_dp_cache` rebuild (~6/sim).
`pvpoke_dp` now reads per-slot arrays (`cm_dpe`, `cm_self_debuf`,
`cm_self_buff`, `cm_energy`, `cm_dmgs_root`) instead of re-deriving
`raw_dpe`/`actual_dpe` closures and `m.get(...)` per call site
(~20 sites across bait-wait + bandaids 861-929). Key simplification:
`raw_dpe(cms[i]) == actual_dpe(i)` given the damage cache (both are
cached-damage / energy since the 2026-04-15 raw_dpe fix), so the two
closures collapse into one precomputed `cm_dpe` array. Bandaid[866]'s
`_cached_damage` dict read is untouched — that's the intentional
OMT-side-effect subgate (DEVELOPER_NOTES near-KO divergence).

**S5d — explicit JIT signatures.** Both kernels compile eagerly at
import with pinned types (disk-cached); skips lazy type inference in
every worker process. Warm import 0.74s.

## Validation

Every step: full suite green (721 passed + 14 xfailed) and
`scripts/audit_oracle_harness.py` = 98 exact + the same 10 documented
divergences (Aegislash bug #3, Morpeko bug #8). Engine behavior is
bit-identical against live PvPoke; S5 changed where values are
computed, never what they are.

## Notes for the next profiler

Post-S5 profile shape (cProfile, same workload): `pvpoke_dp` body
remains the largest tottime block, but its per-call work is now
mostly the near-KO JIT call + `would_shield`/OMT branches.
`_ensure_dp_cache` keying/rebuild and `dict.get` on fast-move scalars
in `_calc_turns_to_live`'s wrapper are the visible residue. Nothing
left looks like >10% without restructuring (e.g. batching sims into
the JIT layer, which changes the engine's shape — out of S5 scope).
