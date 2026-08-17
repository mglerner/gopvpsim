# Joint IV robustness: reuse plan (drafted 2026-08-17, post-Thievul-CD)

Author: Claude Fable 5 (session synthesis), human-guided by Michael.
Status: PLAN — nothing here is implemented; scope sessions from it.

Two goals, from Michael's framing at the close of the Thievul CD arc:

1. **A generic kit**: bundle the Thievul-vs-Licki pipeline into a
   `focal x opponent` joint IV robustness toolset any pair can run.
2. **Automatic candidate detection**: rank which matchups deserve the
   treatment — pairs that are BOTH meta-important AND genuinely
   IV/breakpoint/bulkpoint-sensitive — instead of waiting for a
   discord thread to nominate one.

The load-bearing observation: **we have built this machine twice.**
The Worlds pipeline (2026-08) is the *many-pairs, shallow* version
(closed-form screen -> probe planes -> amber flags -> joint grids for
flagged pairs, batch-rendered pages). The Thievul work (2026-08-16/17)
is the *one-pair, deep* version (full 4096x4096 grids both movesets,
mechanism layer, recommendations, an interactive page with a
CSV-personalized build table, adversarial review to convergence).
Reuse = marry them: Worlds' detection funnel feeding the Thievul-grade
deep dive.

## 1. Inventory: what generalizes as-is vs. what is Thievul-shaped

Generic today (reuse verbatim):

- **Sim core**: `deep_dive_lib/robustness.py` (`opp_plane`,
  `plane_task_worker`, signature dedup) — species-agnostic, test-pinned
  exact, spawn-safe. Both Worlds and Thievul bakes run on it.
- **Grid storage**: `worlds_planes.pack_won/unpack_won/margin` +
  compressed npz with iv_rank-order axes and per-grid manifest. The
  Thievul manifest schema (engine/gamemaster stamps, per-grid moveset/
  bait, axis-order note) is the right generic shape.
- **Probe/screen machinery**: `worlds_bake.probe_spreads` (rank-1-SP +
  max-atk-in-top-512), `worlds_tier0` closed-form cutoffs
  (`guarantee_cutoff`, `ko_cutoff`, `staged_damage`, boundary
  re-confirmation), the amber-screen concept (measured FN rate).
- **Opponent side of the page**: `build_thievul_licki_page.py` +
  `thievul_licki_page.js` derive opponent identity, movesets, slots,
  labels, cross-links from `manifest.json` + `breakpoints.meta` — that
  was the Lickitung->Lickilicky retarget generalization.
- **Assemble/denial layers**: `thievul_licki_assemble.py` (per-grid
  3-way scenario classification with stated rules, tie disclosure,
  basis-labeled cards) and `thievul_licki_denial.py` (opponent-axis
  marginals, closed-form wall/ladder, cross-checked) are already
  manifest-driven; opponent-generic, focal-hardcoded.

Thievul-shaped (the generalization work):

- **Focal identity**: `FOCAL = 'Thievul'` constants in bake /
  breakpoints / assemble / denial / builder; focal moveset lists;
  'Thievul' strings in JS templates (the same sweep the opponent side
  already got). Mechanical but must be swept with the rendered-label
  asserts, not by grep alone (lesson: slot-label leaks).
- **Meta-wins step** (`thievul_licki_meta.py`): reads THE Thievul dive
  replay blob. Generic form: any focal we have dived has a
  `userdata/replay/*_<league>.replay.pkl.gz`; the step needs a blob
  locator + the focal's moveset-index mapping. Focals without a dive
  get pages with the meta panels in their honest-absent state (the
  builder already renders visible absence).
- **Breakpoints script**: the slot system (`meta.move_slots`) was the
  retrofit that made opponents generic; a config-driven move list
  finishes the job for focal. Keep the 4-layer verification block
  (formula samples, sim timelines, stage checks, regression diff) as a
  REQUIRED part of the generic script.
- **Naming**: promote `scripts/thievul_licki_*.py` to a generic family
  (e.g. `scripts/joint_iv_{bake,meta,breakpoints,assemble,denial}.py` +
  `build_joint_iv_page.py` + `joint_iv_page.js`), driven by one pair
  config (see section 2). Thievul-vs-Lickilicky becomes the first
  config instance; its published pages must rebuild byte-identically
  (modulo timestamps) from the renamed kit — that regression IS the
  acceptance test for the rename (precedent: the breakpoints
  generalization's byte-identical Lickitung diff).

## 2. Part 1 — the kit

One config per pair (TOML, mirroring the bake's OPPONENTS dict):

    [pair]
    league = "great"
    focal = "Thievul"
    opponent = "Lickilicky"
    # explicit movesets; grids = cross of these x bait modes
    focal_movesets = [["SUCKER_PUNCH", "ICY_WIND", "PLAY_ROUGH"],
                      ["SUCKER_PUNCH", "NIGHT_SLASH", "ICY_WIND"]]
    opponent_moveset = ["ROLLOUT", "BODY_SLAM", "SHADOW_BALL"]
    injected_moves = ["ICY_WIND"]   # CD-lag injections, disclosed on-page
    replay_blob = "userdata/replay/20260815_183454_Thievul_great.replay.pkl.gz"  # optional

Pipeline (unchanged 6 steps, config-driven): bake -> meta (optional) ->
breakpoints -> assemble -> denial -> page. Output dirs keyed by pair
slug; publish copies remain gated behind `--publish-out` + Michael's
explicit per-instance authorization (standing rule, memory-recorded).

Costs, measured this session (M-series, 14 workers, ~48-76k sims/s
pool-wide with signature dedup): a 4-grid 4096x4096x9 pair = ~130-270M
sims = **40-95 min**. Breakpoints/assemble/denial/page: minutes.

Verification policy is PART OF THE KIT, not optional garnish — the
Thievul arc's central lesson. Bake ships with cell-level re-sim spot
checks; breakpoints with its 4-layer block; denial with the
closed-form-vs-grid asserts; the page with the headless suite
(positive-controlled absence pins, the scope guard, privacy sweep).
And a publish REQUIRES at least one independent fresh-eyes review
round (the 3-lens workflow found 4 blockers + ~15 majors that 683
author-side checks could not see; round 2 found 1 blocker in a round-1
fix; convergence took 3 rounds). Budget reviews into any new pair's
publish, every time.

## 3. Part 2 — automatic candidate detection

Staged funnel, cheap to expensive; stages 0-1 are the Worlds amber
screen generalized beyond the Worlds roster:

- **Importance weight** (free): PvPoke usage/rankings for both species
  (rankings cache), optionally tournament lists (`worlds/meta.toml`).
  Score_importance = f(usage_focal, usage_opp); "known big meta
  threat" = high opponent weight.
- **Tier 0 — closed-form sensitivity** (ms/pair): for each side's
  moves, do damage-tier boundaries cross the OTHER side's attainable
  stat range (`worlds_tier0` cutoffs vs iv_rank ranges)? Weighted by
  margin proximity: a boundary inside a blowout is worthless. The
  session gives both calibration poles: Thievul-vs-Lickilicky 1-1
  (boundary + 52-point score cliff at the breakpoint -> maximal
  signal) and Thievul-vs-Tinkaton (boundaries technically absent /
  fight 171+ points from flippable -> zero signal; SP damage flat 4
  across the whole atk range).
- **Tier 1 — probe planes** (seconds/pair): 2-4 probe spreads x
  opponent cohort x 9 scenarios via `plane_task_worker`
  (Worlds-measured: 1,860 planes / 7.06M sims / 115 s). Sensitivity
  signals: probe-outcome flips, score mass near 500, per-scenario
  variance. Flag amber like Worlds did (60/720 there), and MEASURE the
  false-negative rate on a sampled clean set (Worlds did; keep it).
- **Tier 2 — the queue**: score = sensitivity x importance, ranked.
  Top of queue -> full kit run (Part 1). The queue page itself is a
  useful artifact ("matchups whose outcome most depends on IVs").

Scale check: GL top-30 x top-30 = 870 ordered pairs; Tier 0 for all in
seconds, Tier 1 for all in roughly an hour at Worlds throughput; a
handful of Tier-2 deep dives per week fits the machine. The funnel
also naturally re-runs after balance patches (gamemaster-delta
migration rules in CLAUDE.md apply).

## 3b. Caching (adopt existing patterns, don't invent)

The expensive artifacts are the joint grids (40-95 min/pair) and, at
fleet scale, the Tier-1 probe planes (re-screened after every patch).
Policy per artifact:

- **Joint grids**: the npz + stamped manifest already IS the cache;
  add the invalidation policy. Default: stamp mismatch = stale = back
  on the bake queue (a stale stamp is a safe miss, never served —
  sweep-cache discipline). Warm paths: (a) gamemaster patches bless
  automatically via the `migrate_cache.py` delta computation — a
  grid's manifest records both species and every move used, so
  "untouched by this patch" is a computable predicate, no hand proof
  (v7 sweep-cache precedent); (b) engine bumps default to re-bake,
  with the CLAUDE.md one-localized-fix-per-bump migration escape
  hatch when justified.
- **Tier-1 probe planes**: ride the Worlds planes pattern (or its
  literal storage layer): per-pair `entry_sim_digest` over species +
  moveset identity, stamp checks, manifest-delta invalidation. This is
  where caching pays most — 870 pairs x every balance patch.
- **NOT the sweep cache**: joint grids are pair-planes, not
  per-opponent columns over dive pools; separate namespace. Bonus: the
  engine-iteration `--no-sweep-cache` discipline stays irrelevant to
  this pipeline.
- **GC**: fold the new namespace into the standing "gc_cache.py should
  cover every namespace" TODO; the readable stamps in the manifest
  make grid-level reclaim straightforward from day one.
- **Cheap derived blobs** (meta-wins extraction, breakpoints, denial,
  reco): recompute-on-demand, inputs already stamped; no machinery.

## 3c. Feedback into the normal dives (phased)

- **Phase A — links (with the kit, low risk)**: the kit maintains a
  registry of published robustness pages keyed by (focal, opponent,
  league); dive renders decorate matching opponent rows with the link
  (post-render patcher precedent: `patch_dive_envelope_tags.py`, so
  shipped dives can be retrofitted without re-simming). Reverse links
  already exist.
- **Phase B — spread call-outs via thresholds (later, guarded)**:
  robustness runs EMIT per-opponent spread/anchor DATA into
  `thresholds/*.toml` (the existing curated-matchup-facts vehicle;
  ship-mode narrative policy untouched — it gates prose blocks, not
  data). Two mandatory guardrails: (1) scope labeling — call-outs
  render as a distinct "matchup tech" category, never mixed into the
  main IV tiers, conditions attached (moveset/bait/scenario/cohort);
  a single-matchup optimum can contradict the whole-meta rec (rank-1
  vs the smasher, 2026-08-16), and a conditional claim traveling
  without its conditions is exactly the 6/15/5 failure mode. (2)
  vintage gating — call-outs carry engine+gamemaster stamps; a dive
  render drops stale ones VISIBLY rather than serving them
  (input-freshness lens; stale is a safe miss).

## 4. Open decisions (Michael)

- Kit naming + where configs live (`pairs/*.toml` vs entries in one
  registry file); whether the rename lands before or after the next
  pair is attempted.
- Meta-wins semantics for focals without a dive (omit panels vs run a
  small fresh pool sweep as part of the kit).
- Detection importance function (usage product? max? tournament-list
  boost?) and the amber threshold — decide against a measured FN rate,
  not aesthetics.
- Whether detection output ships as a public page or stays an internal
  queue.
- Session split suggestion: (S1) rename + focal generalization with
  byte-identical rebuild acceptance; (S2) Tier-0/1 screen over GL
  top-30 with FN measurement; (S3) first auto-nominated pair run
  end-to-end as the kit's shakedown.

## 5. Standing constraints carried forward

- `--no-sweep-cache` discipline does not apply here (this pipeline
  never touches the sweep cache), but the PINNED-gamemaster discipline
  does: grids, breakpoints, and page must agree on vintage; the bake
  aborts on axis mismatch and the builder on stamp mismatch. Re-pin
  from pvpoke git history when the TTL refetch drifts (offline-safe
  recipe in `docs/thievul_licki_analysis.md`).
- Ship-mode narrative policy: pages render computed statements only;
  no hand-authored numbers (enforced by the no-hand-authored asserts).
- Publishing: explicit per-instance authorization from Michael, always
  (memory: feedback-publish-requires-explicit-authorization).
- Known gate gap: `verify_no_unicode_dashes` cannot see
  script-generated prose (TODO.md entry, 2026-08-17); the kit's page
  suite must keep carrying its own ASCII assert until the gate learns
  to read inlined app JS.
