# Perf+correctness arc — cumulative speedup scorecard

Running tally for the 2026-06 arc
(`~/.claude/plans/perf-correctness-arc-2026-06.md`). Update this file
as S4-S6 land; S6's full re-dive supplies the end-to-end real-dive
numbers that the per-component measurements below only estimate.

All figures measured 2026-06-10 on Michael's machine, current
gamemaster. "Engine sims/s" is the canonical single-process benchmark
(`python scripts/profile_slayer.py --n-focal 60 --n-opp 20`); sweep
figures are multiprocess wall-clock from
`scripts/verify_signature_dedup.py` (great league, 21 opponents, all
9 scenarios, 4096 IVs).

## Component measurements

| Change                            | Metric                         | Before   | After       | Factor        |
| --------------------------------- | ------------------------------ | -------- | ----------- | ------------- |
| Engine regression fix (`5e25e28`, | engine sims/s (single core)    | 1,121    | 2,278       | **2.03x**     |
| pre-arc, same day)                |                                |          |             |               |
| S1 form-change plumbing           | engine sims/s                  | 2,278    | 2,254       | 0.99x (cost)  |
|                                   | form-species sweep sims        | —        | 1.1-1.35x   | cost, those   |
|                                   |                                |          | more        | species only  |
| S2 mirror-slayer redesign         | slayer round-1 sims (Tinkaton  | 8.2M     | 86k         | **~95x**      |
|                                   | GL smoke)                      |          |             |               |
|                                   | slayer phase wall (smoke dive) | dominant | 20.7s (27%) | no longer the |
|                                   |                                |          |             | bottleneck    |
| S3 signature dedup                | sweep wall-clock, no-buff      | 37.8s    | 9.3s        | **4.07x**     |
|                                   | species (Azumarill)            |          |             |               |
|                                   | sweep wall-clock, buff moveset | 29.6s    | 13.9s       | **2.13x**     |
|                                   | (Tinkaton, either bait mode)   |          |             |               |
|                                   | sweep wall-clock, form-change  | 47.7s    | 35.2s       | **1.36x**     |
|                                   | focal (Aegislash (Shield))     |          |             |               |

Correctness shipped alongside (not speed, but why the arc exists):
S1 wired real form mechanics into every dive worker (Aegislash
(Shield) top-IV avg 237.9 → 390.7 — published numbers were wrong,
not slow); S2 replaced the tie-exploding slayer iteration with the
two first-class archetypes; S3 is provably score-neutral (raw-float
equality on 774k cells per verified species).

## Compounding: what a dive's sweep phase costs now

Relative to the morning of 2026-06-10 (regressed engine, no dedup),
the per-moveset IV sweep is:

- typical no-buff moveset: 2.03 × 4.07 ≈ **8.3x faster**
- typical buff-carrying moveset: 2.03 × 2.13 ≈ **4.3x faster**
- Aegislash-class form changer: 2.03 × 1.36 ≈ **2.8x faster**
  (and now simulating the right battles)

Relative to the *believed* baseline (the stale 2026-04-07 "26k
sims/s" figure, i.e. post-regression-fix engine), the sweep phase
alone is 1.4-4.1x faster — S3's contribution.

A full website dive ≈ (3-6 sweeps per moveset-mode combo) + slayer
phase + analysis/render. Sweeps and slayer were the two dominant
terms entering the arc; with sweeps 2-4x cheaper and slayer ~95x
fewer sims, expect analysis + HTML render to surface as the next
visible cost — re-profile before locking S5 targets (note in plan
S3 section).

## Historical context (pre-arc, for perspective)

The 2026-04 optimization rounds (numpy round 1+2, chunking) took the
original deep-dive workload from ~9hr to ~6min; the 2026-04-15
correctness arc then silently halved the engine for eight weeks
(found+fixed at the start of this arc — see
`docs/perf/2026-06-10_holistic_perf_review.md`, and the regression
gate in DEVELOPER_NOTES "Performance baseline" that exists so it
can't happen silently again).

## Still to land (update this file when they do)

- **S4** replay-from-saved-state + sweep disk cache: re-runs of an
  unchanged dive command → near-zero sims; renderer iteration
  without re-simming.
- **S5** round-3 numpy buffers + farm-down JIT: est. 25-35%
  single-core engine headroom (gates apply hard; highest-risk
  session).
- **S6** full re-dive: the real end-to-end before/after for the
  website chain — record actual dive wall-clocks here.
