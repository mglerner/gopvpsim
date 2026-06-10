# 2026-06-10 — Holistic performance review (and fixes)

Motivation (Michael): "I'm not sure that we did a great job of
actually identifying the causes of slow performance earlier." He was
right. This review combined fresh cProfile data, a controlled
old-code-vs-new-code benchmark, and a structural read of the engine
and orchestration layers.

## Headline finding: a silent 2.0x engine regression

The battle engine had been running at **half** its post-optimization
speed since 2026-04-15, and the canonical "26k sims/s" figure from
2026-04-07 was measured *before* the regression and never re-checked.

Controlled measurement (same machine, same gamemaster cache,
`profile_slayer.py --n-focal 60 --n-opp 20`):

| Code                                   | sims/s |
| -------------------------------------- | ------ |
| `a57c39f` (post-round-2, 2026-04-07)   | 2,255  |
| `d419306` (HEAD before this session)   | 1,121  |
| `154536a` (after this session's fixes) | 2,278  |

This fully reconciles the long-standing discrepancy between the
2026-04-07 benchmark (~26k sims/s on interactive sweeps) and every
real dive since 2026-04-19 (7-13k sims/s in
`docs/perf/2026-04-19_overnight_chain_perf.md`): 26k ÷ 2 ≈ 13k.
There was no need for memory-pressure or dedup-failure theories —
the engine itself had halved.

## Root cause

Commit `141eee1` (2026-04-15, "Fix Forr/Azu DP: track atk_stage
through near-KO plan rollout") — a correct and necessary fix — rebuilt
a 9-row per-atk-stage damage table via `calc_damage` on **every**
`pvpoke_dp` call, plus 7 `np.asarray` conversions per call at the
numba JIT boundary, plus a per-call re-sort and priority-shuffle of
the charged moves.

cProfile evidence (7,200 sims, pre-fix): `moves.damage()` called
6.0M times ≈ 27 per DP call ≈ exactly the stage-table rebuild with
2 charged moves; ~97% of all damage computations were this rebuild.
`np.asarray` 1.5M calls. This was the same per-call-marshaling
failure mode the 2026-04-07 "round 3 false start" writeup had
already diagnosed (and shelved) for `_calc_turns_to_live`.

## Fixes shipped this session

1. **`5e25e28`** — `BattlePokemon._ensure_dp_cache`: per-(opponent,
   stat-stages) cache holding the priority-shuffled move order,
   per-move scalar arrays, the 9-stage damage tables, and the numpy
   buffers the JIT consumes. The root-stage row of the cached table
   doubles as the JIT's `cm_dmgs` argument. Form change invalidates
   it on both sides. Effect: 1,121 → 2,205 sims/s (1.97x).
   Total function calls per profile run dropped 60.4M → 29.2M.
2. **`154536a`** — gated hot-path string formatting: `log_event`
   call-site f-strings (previously evaluated even with `log=False`)
   and `would_shield`'s reason strings (previously built with
   `_shield_trace` off). Effect: 2,205 → 2,278 sims/s.

Validation for both: full suite 696 passed + 14 xfailed;
`scripts/audit_oracle_harness.py` 108 cells = 98 exact matches + the
same 10 documented divergences as before the change (Morpeko bug #8,
Aegislash bug #3). Behavior-identical against live PvPoke.

## Tried and rejected

* **Multi-entry DP cache (one entry per stat-stage pair).** Built it,
  measured it, reverted it: damage-call count was identical because
  stat stages *ratchet* monotonically within a battle (debuffs stack
  down, buffs stack up) — stage pairs are first-visits, not revisits,
  so keeping old entries buys nothing.
* **`raw_dpe`/`actual_dpe` precompute** (1.6M calls, ~5%): the call
  sites pass move dicts from several contexts; converting to indexed
  lookups is a fiddly refactor for a small win. Left for a future
  session if profiling ever shows it matters.

## Form-change "10x slowdown" was a misattribution

TODO's "Form-change path speedup" item (2026-04-19) blamed
form-change-specific costs for Aegislash (Shield) running ~10x slower
than Blade. Post-fix smoke dives (Phase 2, 3 opponents): Shield
4,800-6,900 sims/s vs Blade 5,200-5,700 — **parity**. Shield's battle
shape (charge-farm to ~100 energy → near-KO DP every decision) had
simply amplified the per-call stage-table rebuild. TODO updated; the
planned 2-hour form-change perf session is no longer needed.

## End-to-end confirmation (multiprocess sweep path)

Tinkaton GL smoke dive post-fix (`--opponents 20 --reserve-cpus 1`,
9 workers), Fairy Wind / Gigaton Hammer, Play Rough — the same
moveset the 2026-04-19 report measured:

| Path                              | 2026-04-19 (10 workers) | 2026-06-10 (9 workers) |
| --------------------------------- | ----------------------- | ---------------------- |
| Interactive sweep (all 9 shields) | 9,413-9,983 sims/s      | 16,073-16,947 sims/s   |
| Phase 2 (1v1 only)                | —                       | 13,306 sims/s          |
| Mirror-slayer Round 1             | —                       | ~11,900 sims/s         |

~1.7x aggregate with one fewer worker (~1.9x per-worker). Caveats:
the 04-19 run used the full ~65-opponent pool and pre-June gamemaster
data, so this is consistent-with rather than a controlled measurement
of the 2x engine fix reaching the sweep workers.

## Claims from the review that did NOT survive verification

For the record, since this review was explicitly about not
misidentifying causes again:

* "Stat-profile dedup is broken (1.34x vs expected 3.5x)" — **no**.
  `group_ivs_by_stat_profile` dedups correctly on exact effective
  stats; the achieved ratio (~1.45x on Oinkologne) is inherent to
  each species' level/CPM structure. The 3.5x expectation was
  invented; the CHANGELOG's "~1.7x" was a different species.
* "Memory pressure / L3 contention explains the benchmark-vs-real
  gap" — unnecessary; the engine regression explains it.
* "Bug Bite vs Volt Switch 2x throughput difference is an
  inefficiency" — it's battle length (lower fast-move damage means
  longer battles); per-turn cost is roughly constant.

## Remaining opportunities (not done, roughly ranked)

0. ~~Cross-mode opponent-IV dedup in interactive sweeps~~ — **measured
   2026-06-10, dead end.** Rank-1 IVs equal PvPoke-default IVs for
   0/30 top GL opponents and 1/30 top UL opponents (PvPoke defaults
   use trade-floor IVs like 4/x/x; rank-1 is usually 0-atk). The
   `--opp-ivs both` re-sims are genuinely different battles; there is
   no duplicated column to share.
1. **`_calc_turns_to_live`** is called once per `pvpoke_dp` call
   (~230k per profile run, ~11% cumulative); state-dependent so not
   trivially cacheable, but worth a look if more engine speed is
   needed.
3. **Phase 2 1v1 results discarded** when interactive mode re-runs
   all 9 scenarios (~1/9 duplicated work).
4. **HTML size pathology** (Jumpluff 60.7MB) — already tracked in
   TODO with a demote-vs-optimize decision pending.
5. **Round-3 numpy buffers for `_calc_turns_to_live`** — the original
   plan in the perf memory file; less pressing now that the DP-side
   asarray churn is gone.

## Regression gate

DEVELOPER_NOTES.md now has a "Performance baseline (regression gate)"
section: after any change to `battle.py` / `_dp_jit.py` / `moves.py`,
re-run `python scripts/profile_slayer.py --n-focal 60 --n-opp 20`
and investigate any >10% drop before committing. Current baseline:
**2,278 sims/s** at `154536a`.
