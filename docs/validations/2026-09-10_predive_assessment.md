# Pre-dive assessment, 2026-09-10

Run per `docs/predive_checklist.md` before the post-rebalance cold bake. The
change surface since the last bake is the largest this repo has had: new turn
system, 95 -> 135 dives, a pool-derived dive registry never run in anger, megas
in the pool for the first time, 58 spreads retired, a new publish gate.

Grid is {L1 engine, L2 cache, L3 orchestration, L4 data, L5 rendered,
L6 docs} x the seven lenses.

## Clean

| lens | trigger | result |
| ---- | ------- | ------ |
| 1 value correctness (L1) | `pytest tests/test_battle.py` | 245 pass, 13 xfail |
| 6 cache soundness (L2) | `engine_hash()` | `e4d380ec3e5e`; cold by construction -- `mechanics` is in both cache keys and nothing was ever baked under `new`, so migration is moot |
| 7 known-issue triage (L6) | grep `XXX:` | 0 markers |
| 5 input freshness (L4) | reference pins vs PvPoke defaults | 1 differs (Thievul PLAY_ROUGH) and it is a deliberate editorial call |
| 3 resource/concurrency (L3) | grep Pool/jobs/reserve | `run_iv_guides` already hardened after the 2026-06-27 oversubscription bug; chain runs it `--jobs 1`; 18 physical cores |
| -- pre-launch | `verify_dev_counts.py` | all sentinels green (test_count 2245) |
| -- pre-launch | cache vs pvpoke master | cache `pokemon+moves` hashes IDENTICAL to pvpoke a93147bf1 (`6e67f7d7c5a1`), zero differing top-level keys |

## Findings

**Duplicate DOM ids: FALSE ALARM, and the checklist trigger caused it.** First
pass measured 484 duplicated ids and 59 of 60 in-page anchor targets
duplicated -- navigation jumping to the wrong section. Wrong: the Lens-4
trigger says to strip `<script>` but not `<template>`, and the best-buddy L51
pass renders a second full copy of the dive body into `<template>`s (1.8 MB
here) with a deliberate anchor-registry reset. Template content is inert.
Stripping it: 484 -> 240 duplicated ids, and **0 of 60** anchor targets
affected. The 240 remaining are all `af-<hash>`, pre-existing since at least
the July bake, and confirmed inert -- none is referenced by `href=#`, by any JS
lookup, or by `aria`/`for`. Trigger fixed in the checklist; the dangling
"TODO carries the de-dupe item" pointer restored to TODO.md.

**Gamemaster backup created.** The checklist wants a copy of the pinned blob
somewhere the run cannot overwrite; the only preserved vintages were August.
`userdata/_preserved/gamemaster_vintages/gamemaster_66b3cba2840d_2026-09-10_prebake.json`
now holds the blob this bake runs against, with the recovery recipe beside it.

## Open at the time of writing

* **Spread tiers (L5): SETTLED, and the feared regression did not happen.**
  Ran a diagnostic Tinkaton dive -- Tinkaton lost 7 authored spreads, the most
  of any species. The page renders normally: the Threshold Tiers section is
  present with **14 distinct tier cards**, no empty state, no breakage. The
  tiers are ANCHOR-derived, and anchors were never retired, so losing the
  authored spreads cost the page its expert-named cutoff regions but not the
  section itself.

  Two stale references remain, both cosmetic:

  - `thresholds/tinkaton.toml`'s ANCHOR descriptions still cite numbers from
    the retired spreads ("Discover all Azumarill bulkpoints. 143.03 def flips
    1-2"). That one is still TRUE -- Azumarill's kit was untouched by the
    rebalance -- but the ~182 such descriptions include some derived against
    the 32 opponents whose movesets DID change. Already tracked as the
    threshold-TOML re-vet.
  - The renderer's own glossary hardcodes `GH Great` / `GH Good` as its worked
    example of a tier ("e.g. GH Great = Def >= 143.03, HP >= 138"). Those
    tiers no longer exist on any page, so the glossary now teaches the concept
    with an example a reader cannot find. Worth swapping for a live tier when
    the renderer is next open.
* **Chain smoke test.** `build_matchup_web.py`, `run_iv_guides.py`,
  `build_website_index.py` and `run_ship_gates.py` have not been run since the
  rebalance. They are the steps that consume hours 10-13 of the bake and would
  be discovered broken only there.
* **Lid-close sleep.** `pmset sleep 0` is set and `overnight_redive.sh` calls
  `caffeinate`, but nothing prevents clamshell sleep without an external
  display. The 2026-08-06 bake lost 18h that way. Launch-keyboard item.
