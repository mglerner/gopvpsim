# Parallelize the dive step (plan only)

Status: PLAN ONLY -- do not implement without Michael's go.

(Moved verbatim from TODO.md "PLAN ONLY: parallelize the dive step
(re-scoped 2026-09-27: <=6.9 h ceiling, memory-bound)" on 2026-11-18; two
pointer fixes noted inline. The "Measurement pitfall" subsection moved to
`docs/predive_checklist.md`, lens 3.)

**PLAN ONLY -- do not implement without Michael's go** (his call 2026-09-12:
"make a plan for it, but don't implement"). Was "HIGH PRIORITY, ~13h/bake";
the 2026-09-25 render speedups (R1-R4, R3, the sweep-side rank-1 memo
c4083f1) shrank the serial tail this plan targets, so the prize is now
smaller and the memory risk is the gating question.

## Measured, on the 2026-09-26/27 bake (current numbers)

`docs/perf/2026-09-25_bake_attribution_and_cruft_scout.md` "Measured" (chain
`overnight_20260926_102139.log`, 136 dives, pmset sleep windows subtracted):
dive step **17.9 h awake**, of which the single-core render/analysis bucket is
**6.9 h -> serial share 39%** (6.9 / 17.9); pool sims 11.0 h. The
2026-09-12 version of this section reported 13.4 h serial / 32% of a 41.8 h
step, from the old marker-inheriting report, which undercounted serial time
(on the 09-20 bake it read 15.5 h serial vs 18.6 h by per-dive attribution,
per c0f1037) -- compare absolute hours, not shares. Absolute serial time fell
from 19.0 h (09-20, same 136 dives) to 6.9 h, and the sweep-side memo
(c4083f1, merged after that bake, not yet in a measured bake) should take
roughly another 2-2.4 h off it. `run_website_dives.py:304` still launches
each dive with a blocking `subprocess.run` in a loop -- strictly serial, no
`--jobs` -- so during those hours 17 of 18 cores idle.

(Note 2026-11-18: the 2-2.4 h saving is still a projection. The 2026-09-27/28
GL-only re-dive ran after c4083f1 -- 76 dives in 209 min, CHANGELOG
"2026-09-27/28 -- Great League re-dive" -- but was not serial/parallel
attributed.)

The 2026-09-12 report caveats are fixed: GL + UL rows of one species no
longer merge (ac2d7e1 keys on species + league), and c0f1037 attributes
from the per-dive ms logs with a sleep bucket instead of inheriting chain-log
markers.

## The prize

Overlapping 2-3 dives fills each other's render tails. Ceiling is the serial
bucket: 6.9 h measured; ~4.5-5 h once the c4083f1 memo lands in a bake
(projection, not measured), so roughly 13 h instead of 17.9 h awake --
about a third of the "~13 h" this section claimed on 2026-09-12.

## The risk: memory, not cores

The 2026-09-12 plan said "0.8 GB per dive process, 64 GB machine". That is
contradicted by two measurements: the 2026-09-25 scout saw 2.5-8.5 GB RSS per
dive's render state, and `scripts/replay_render_diff.py`'s harness measured
4.9-11.6 GB **peak RSS per render** (tinkaton_great 4.9, melmetal_great 4.9,
guzzlord_great 5.5, jellicent_ultra 6.3, cramorant_ultra 11.6 GB; measured
at `--jobs 5` on a shared machine, 2026-09-25). Three concurrent
Cramorant-sized render tails would reach ~35 GB before the sweep pools' own
footprint, on a 64 GB machine. Needs a measured concurrent-RSS probe and a
lens-grid review (`docs/predive_checklist.md`, resource/concurrency lens)
before any `--jobs` default above 1.

## Implementation plan

1. **Per-dive log capture (do this FIRST, it is load-bearing).** Dive stdout is
   currently inherited straight into the chain log. Concurrent dives would
   interleave into mush AND break `chain_status.py`, which parses that log's
   `[N/M] slug` banners and `Done in X.X min` markers. Give each dive its own
   file, then have the parent emit the banner lines itself.
2. **Split `--reserve-cpus` across workers.** The chain passes
   `--reserve-cpus 0` and `deep_dive_lib/sweep.py:848` computes
   `min(cpu_count() - reserve, len(chunks))`, so each dive asks for all 18.
   Three concurrent dives would ask for 54. Divide the budget by the job count
   (18 cores / 3 jobs -> `--reserve-cpus 12` each), and note the render tail
   uses ONE core regardless, so the ideal is oversubscribing slightly.
   (Line ref updated from :833 on 2026-11-18.)
3. **Add `--jobs N` to `run_website_dives.py`**, defaulting to 1 so nothing
   changes until asked for. A small process pool over the DIVES list.
4. **Verify cache safety before trusting it.** `put_column`'s sidecar write is
   atomic (tmp + `os.replace`, `sweep_cache.py:208-215`) but the tmp filename
   is FIXED (`<name>.tmp`), so two writers to the SAME column collide.
   Concurrent dives have different focals -> different columns -> safe today.
   Confirm that still holds for the mirror-slayer and signature-dedup paths,
   which are the ones that write outside the plain focal column.
5. **Do NOT touch the ML guide tail.** `run_iv_guides.py --jobs 1` is serial ON
   PURPOSE -- it is the fix for the 2026-06-27 oversubscription bug, and its
   preflight hard-fails when `jobs x per-guide workers > cores`. Also pointless
   now: the whole ML tail measured **3.9 min** for 60 guides on 2026-09-12
   (48 profiles x 60 opponents at `DEFAULT_IV_FLOOR = 12`, vs 4096 IVs x 76
   opponents x 9 scenarios for a GL dive); 204 s on the 2026-09-26/27 bake.
6. **Memory IS the constraint** (see "The risk" above): cap concurrency by
   measured peak RSS, not core count; the old "0.8 GB per dive" figure is
   wrong by 3-15x.
