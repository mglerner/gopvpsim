<!-- TODO_backlog.md holds the long-tail "someday / maybe" design notes,
research reproductions, and UI/analysis wishlist split out of TODO.md on
2026-06-28 so TODO.md stays small enough to read in one shot. These are
genuinely-open items, NOT shipped work (shipped work lives in CHANGELOG.md).
Read this on demand when picking up exploratory/feature work; TODO.md's
"Backlog (someday / maybe)" section indexes what's here. Promote an item back
to TODO.md when it becomes near-term actionable. -->

# TODO backlog (someday / maybe)

Long-tail design notes and wishlist split out of `TODO.md`. Each entry is
open work; the detail (empirical findings, file:line pointers, measured
precedents) is preserved verbatim. Near-term actionable items live in
`TODO.md`; shipped work lives in `CHANGELOG.md`.

## Policies to add

* **Re-optimize the new-mechanics decision layer (POST-SHIP, deferred
  2026-06-24).** Phase 1 shipped pure plumbing: under `--mechanics new` the
  decision layer runs LEGACY decisions, which corpus-testing showed are
  near-optimal on the new clock (the post-mortem-charged-survival resolution
  property already delivers the edge a decision change would chase). BUT we
  knowingly leave a real, reproducible sub-optimality on the table: there is a
  floor-clean win (Aegislash (Shield) vs Talonflame (Shadow) [0,0] 515->595 via
  `decisive-commit globalmax@1.25`) we dropped as a single edge cell, and we have
  no *generalizable* counter-strategy — every broad "commit early because I'll
  die" formulation breaks the no-regression floor on shield-bait-timing species
  (Tinkaton/Mantine/Jumpluff-S/Quagsire-S) because the opponent baits/farms
  instead of throwing. Full writeup, the specific cases, why nothing generalizes,
  the recommended DP-internal direction (`_calc_turns_to_live`/`fire_now` made
  natively charged-survives-death-aware), the resume harness
  (`scripts/corpus_policy_driver.py` + the non-regression floor methodology), and
  the coverage gaps (GL-only — UL/ML untested; curated ~20-focal subset) all live
  in `docs/validations/new_mechanics_decision_layer_2026_06_24.md`. Come back to
  this after launch.

* **PvPoke "Selective" baiting** — PvPoke's UI offers a bait toggle; "Selective"
  uses the same ActionLogic.js DP to decide *whether* baiting is worthwhile given
  current state (turnsToLive, bestChargedMove by DPE, minimumCycleThreshold).

* **Random buff/debuff** — For chance-based buffs (< 1), PvPoke uses a
  deterministic buffApplyMeter that fires every 1/chance activations. We should
  also support running many sims with random rolls, to find win conditions
  (e.g. if first Air Cutter boosts, you win, otherwise you lose). Options:
  deterministic (current), random, always-hit, never-hit, double-boost.

* **EV-based baiting** — our own novel policy: parameterize the bait decision by
  an estimated P(opponent shields). P~0 → fire best-DPE move; P~1 → bait with
  cheapest.

* **Cramorant UL Dive+Surf 2v2 tank discriminator (parked 2026-11-18 from
  TODO; next strat campaign).**
  - OPEN VALUE (next campaign): UL Dive+Surf 2v2 under the OLD tank was
    +15-21k flips at passing rating; a per-build tank discriminator
    would recover it (sheet v5 ships zero there).
  [2026-11-18: the shipped sheet is now v8 (CHANGELOG 2026-09-28); whether
  v6-v8 recover any of this cell was not re-checked.]

## Features to add

(Form Change shipped 2026-04-14 for Morpeko/Aegislash/Mimikyu;
bait-axis as a deep-dive sim dimension shipped; DP cycle-timing
move selection closed 2026-04-15 as not-a-real-issue.)

* **Energy-lead axis (safe-switch / closer matchup flips) — CORE
  AXIS SHIPPED + TESTED 2026-06-12 (commit 9889555); the web-oracle
  CALIBRATION was never built (see the two caveats below).** The `--energy-lead` axis
  (default `off`) is plumbed through `deep_dive.py`: energy-lead
  values are fast-move multiples `[0, 1, 2]` (cold start + 1/2 fast
  moves of carry-over), converted to raw energy per moveset and
  clamped at the reachable bound (focal clamping), then folded into
  the composite mode string and the column cache key. Pinned by
  `tests/test_energy_lead.py` (8 passed).

  Two sketch sub-items did NOT ship as written and stay out of
  scope:
  - The calibration test landed on **Azumarill**, not the proposed
    Shadow Sableye web-oracle calibration. No web-oracle calibration
    was built (and none is planned here).
  - The throwaway precedent script
    `scripts/check_sableye_energy_lead.py` was deliberately **KEPT**
    (not deleted) as the end-to-end engine-feasibility record from
    the 2026-06-03 scoping run.

* **compare_loadouts N-way verdict** (parked 2026-11-18 from TODO): N=3/N=4
  rendering shipped (53ade3c, 2026-04-22: all-N-in-row matchup table); the
  verdict line still lists per-loadout win rates without an N-way ranking.
  Stay loadout-list-keyed; N=4 ceiling (parse_spec hard-caps it).

* **ML guide "what do I get by best-buddying these?" view** (parked
  2026-11-18 from TODO) — the "All
  cases" IV-compare view (shipped 2026-06-28, `5b882dc`) hides
  best-buddy-conditional flips by default and badges their count
  ("N best-buddy flips hidden"). A natural follow-up is a dedicated
  summary that answers, for the user's candidate spreads, *what
  matchups best-buddying unlocks/loses* — e.g. "best-buddy 15/15/14 to
  win Solgaleo 2-1 + Kyurem 2-2; 15/14/15 gains nothing." The data is
  already there (the alt grids / sibling quadrant rows); this is a
  rendering/summarization feature, not new sim. Deferred 2026-06-28 by
  Michael ("don't want to engineer that now").

* **Team/multi-mon simulation** (parked 2026-11-18 from TODO) — currently
  only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support. When this
  lands, honor `reset_on_switch`: Morpeko must re-enter in Full Belly on
  every switch-in (confirmed in-game 2026-06-06; see DEVELOPER_NOTES §8).
  Also port the MATCH-level 240 s clock (Michael, 2026-06-11): the real
  game's timer spans the whole 3v3, charged-move animations consume it,
  and games are genuinely won on time — see DEVELOPER_NOTES "Battle
  timeout" divergence entry for PvPoke's clock semantics to mirror.

* **gobattlekit owned-mon breakdown screen** (parked 2026-11-18 from TODO;
  queued 2026-06-21). Remaining: the Toga screen (model on gobattlekit
  `screens/user_iv_checker.py`) reading the bundle from
  `scripts/export_owned_breakdown_bundle.py` (`c1ea231`), + parity vectors.
  Plan: `docs/owned_mon_breakdown_plan.md`.

### PoGoDives strategy page (Michael, 2026-09-24) (parked 2026-11-18 from TODO)

Expand the Cramorant strategy article into ONE PoGoDives-strategy page with
a section per strat: Cramorant (the existing content), the stat-effect strat
(Drain Punch-style "throw the effect move into a predicted shield"; plan:
docs/statfx_strat_plan.md), and room for later ones. Not started.

Today: `scripts/render_pogodives_strategy_article.py` ->
`userdata/website/articles/cramorant-pogodives-strategy/`. Carry over its
contracts: every number recomputed from the rendered dive tensors at render
time; showcase links computed and gated by verify_url (never hardcoded --
the 2026-09-12 stale-link incident); authorship "both" with Michael's
review; ASCII-only prose; publish only on Michael's explicit go.

Prerequisites for the stat-effect section: the rule ported into the engine
behind the PoGoDives marker, certified per page it ships on (Sableye DP+FP
pages first), a migrate_cache predicate for the tier change, and a rebake,
so the section's numbers can come from real PoGoDives-tier tensors. Also
decide: keep the old slug (Cramorant dive pages link to it) or move to a
general slug with the old one redirecting. Toggle copy is already approved
(plan doc, "Page copy"); the page should also state the shield-prediction
dependence (the fragility results).

### Cramorant strategy article pair (parked 2026-11-18 from TODO)

Same article family as "PoGoDives strategy page" just above.

- Hard-counters lists: RE-DERIVE from the current-sheet (v7) tensors
  before any public surface carries one. Both earlier rosters (the
  static-tank "five losers" and the lead40-derived set) predate the
  shipped sheet. [2026-11-18: the current sheet is v8 (CHANGELOG
  2026-09-28).]
- Strategy article PAIR (Michael 2026-08-25, queued): (1) playing
  Cramorant and (2) playing AGAINST Cramorant -- the shipped
  cramorant-pogodives-strategy article covers the PoGoDives strat
  itself, not this pair. Evidence base = the lab campaign: dive-early
  numbers (the 1.5-vs-3.0 gate, the Kingdra exception), the prey-tank
  rule + "tank unless clearly ahead", the shield-economy structure
  (better with shields on the board, the shield-ahead tax), the
  missile HP-breakpoint family (floor(15%*maxHP)+1 steps); vs-side:
  energy stacking, don't-shield-weak-hits, the re-derived
  hard-counters set (bullet above), and the carefully-caveated
  withhold finding (our crude withhold counter-policy BACKFIRED --
  baseline Cramorant won MORE vs withholding opponents, +628 vs +233
  W-L -- don't oversell). TONE: warm toward PvPoke on public surfaces
  (feedback-pvpoke-tone). SHIP-MODE POLICY applies: narrative TOML
  blocks are Michael's prose or honest auto-gen; Claude supplies
  verified bullets + data sections only. Vehicle: articles/*.toml +
  render_article.py.

### Condensed-meta funnel bundle (queued 2026-08-19, Michael) (parked 2026-11-18 from TODO, with Worlds dormant)

Bundle the whole Worlds chain for reuse on future condensed metas
(limited cups with ~20 real picks): meta table -> Tier-0/1 planes ->
amber screen -> Tier-2 grids -> hub/matrix/cheat sheets -> joint-IV
deep pages. The chain is now proven end-to-end (the 08-19..27 runs).
Inventory: `worlds_bake/planes/tier0/tier2/
render_data/build_worlds_pages/verify_worlds` are already meta.toml-
driven; the Worlds-hardcoded parts are `worlds_meta.py` (entry list +
badges are literals; needs a cup-roster config + a usage source that
isn't the Worlds Dracoviz corpus), the `worlds/` output paths + page
copy, and the `worlds_`-prefixed naming. `joint_iv_from_worlds.py` +
`worlds_shortlist.py` bridge to the deep-page kit and generalize with
the same meta-config handle. PvPoke publishes per-cup rankings
(topn_cup_filter_plan.md), so cup default movesets have a source.
Standing publish/bake/pin constraints: docs/worlds_prep_plan.md "Revival
standing rules".

### Old/new mechanics user toggle (POST-SHIP) (parked 2026-11-18 from TODO)

*(2026-06-26, Michael)* Post-ship idea, flagged so it is not lost; do NOT
pre-ship or design heavily yet. If the site/app gets traction, P!P-series /
Worlds competitors may want it for prep, and **Worlds runs on the OLD battle
mechanics**. So expose a user-facing toggle between old and new mechanics on
the dive site. [Corrected 2026-11-18: that was true of the 2026 Worlds
campaign, but our engine no longer treats legacy as a peer: legacy mechanics
are opt-in only -- `simulate()` raises on `mechanics='legacy'` unless
`GOPVPSIM_ALLOW_LEGACY_MECHANICS=1` is set (`2615c6e`;
`src/gopvpsim/battle.py`), and nothing is hardcoded to legacy, Worlds
included (`4b6342b`). A toggle would mean re-supporting legacy as a
first-class mode.]

Light design notes (not yet designed):
- Preference storage: cookies (never used here) vs radio buttons vs a query
  param. Look at what PvPoke does for its "Preview next season" version as
  prior art before picking.
- Cache: [corrected 2026-11-18: the sweep cache has keyed on the
  turn-mechanics model since 2026-09-02 (`scripts/sweep_cache.py`
  `mechanics` field; `scripts/deep_dive.py` cache_key), so old-vs-new
  results already cache separately and a `new`-mechanics dive no longer
  force-disables the cache. The original note said the cache-rework did not
  key on the turn model and that keying it meant extending
  `sweep_cache`/`migrate_cache`.]

## Analysis goals

* **RyanSwag atk-weighted spreads may be outdated** — The
  `thresholds/_shared.toml` atk-weighted variants (Medicham 7/15/14,
  Lickitung 10/15/14 + 10/14/13) are sourced from RyanSwag's 2024
  methodology video and archived GamePress deep dives. Moves and meta
  have shifted since (Counter nerf, Rage Fist, Low Kick buff, new
  species). Periodically re-evaluate:
  1. Is the species itself still meta-relevant? (Lickitung dropped out
     of the GL top-50 in the current pool; Lickilicky is more common.)
  2. Is the *atk-weighted* variant still the one competitive players
     prepare against, or has the community shifted to a different
     high-atk IV?
  3. Does the variant's atk stat still cross meaningful breakpoints
     against current focal species, or did a move rebalance collapse
     the BP distinction?
  Not urgent — the current spreads work as "the 2024 community-cited
  variants RyanSwag uses, verified by the methodology video." But the
  longer the spreads sit without review, the more likely they drift
  from the live meta. Revisit whenever a new atk-weighted variant
  lands in a future deep dive, or annually.

* **RyanSwag-style matchup-flip annotations + wins-based y-axis**
  *(in progress 2026-04-09)* — Extend deep dives to call out *which
  specific matchups flip at which IV thresholds, in which shield
  scenarios* (e.g. "103.54 Def for the mirror BP vs Annihilape: 2-2
  no bait, 2-1 farm, 0-0 Ice Punch only"). The flip infrastructure
  already exists (`_find_flips`, `_narrate_flip`,
  `_generate_threshold_descriptions` in `scripts/deep_dive.py`); the
  gaps are: (a) the aggregator collapses scenarios instead of naming
  them, (b) threshold descriptions are stat-shape heuristics, not
  tied to named anchors (mirror BP, etc.), (c) flips are computed
  against a single reference IV, not multiple baselines.
  **Phase 1 (text)**: Extend the aggregator to emit per-anchor
  bullets that name the scenarios where each anchor's flip occurs;
  tie threshold descriptions to anchor names from the resolver.
  **Phase 2 (graph)**: Add a wins-based y-axis to the interactive
  scatter plot, with three baseline traces — vs rank-1, vs PvPoke
  default, vs mirror-converged cohort. Single shared flip table
  feeds both phases. **Caveat**: move parameters have changed since
  the original RyanSwag dives; we are reproducing the *format and
  reasoning style*, not the exact stats. **Cross-ref**: this work
  may resolve (or substantially shift) the "Slayer-card signal-loss
  audit" item below — both are about surfacing differentiating
  signal where current heuristics produce vacuous output. Re-read
  the audit item before starting Phase 2 renderer changes.

* **Meta-wide slayer reference (ambitious)** — With the slayer anchor
  system AND bulkpoint anchor system shipped, we can systematically run
  `--mirror-slayer` (with anchors) on the top 30 GL meta picks and build
  a meta-wide reference of "the converged slayer cohort + named anchors"
  for every relevant species. Each species gets its own
  `thresholds/<species>.toml` with hand-picked anchors against its key
  opponents (and the auto-fallback layer fills the gaps). The output:
  a per-species HTML deep dive plus a top-level summary table of which
  IVs are slayer-quality across the meta. This is the natural extension
  of the Annihilape work to the rest of the format. Could be paced as
  2-5 species per session to keep momentum without burning out on TOML
  authoring. Goodra, Clodsire, Carbink, Galarian Stunfisk, Tinkaton,
  Medicham, Annihilape (already done) are obvious starting points —
  they're in the existing dive history. Anything in the championship-
  series group is a candidate.

* **Reproduce SwagTips-style IV deep dives** — articles like the old GamePress
  Carbink and Annihilape PvP IV deep dives. Use Pokemon Go Championship Series
  event data (most common mons/movesets) as the modern test pool. Sim all 4096
  IVs of competitive mons against rank 1s, find interesting IV targets, check
  for hidden corebreakers. Consider atk-weighted IVs for CMP tie priority.

* **Reverse-engineer anchor intent from tournament CPs — TRIED, ABANDONED
  (don't re-queue).** The idea was to take dracoviz per-mon CPs, enumerate
  4096 IVs × valid levels per entry, filter to the matching CP, and cluster
  the candidates into anchor categories to infer what spread each player
  aimed for. Attempted; **there just isn't enough data** — a single CP value
  is consistent with too many IV/level spreads to constrain the anchor, and
  the tournament field is too small to disambiguate by aggregation. Dead end
  with currently-available tournament data; only revisit if a far larger /
  richer per-mon dataset (e.g. actual IVs, not just CPs) appears.

* **Compare to reddit IV spectrum post** —
  https://www.reddit.com/r/TheSilphArena/comments/z11xr0/theorycrafting_iv_spectrum_graphs/
  Reproduce the method (move parameters have changed since then).

* **Reproduce iv-tech channel analysis** from HSH's Discord.

* ~~Tinkaton scatter-cluster questions~~ + ~~**Reinvestigate clustering
  methodology**~~ — **DONE 2026-07-07** (CHANGELOG "2026-07-07 — matchup-
  fingerprint clusters"). The methodology re-evaluation ran on a loaner
  machine 2026-07-04..06 (report:
  `~/coding/reports/gopvpsim-cluster-methodology-2026-07-05.html`, incl.
  per-question answers to the Tinkaton scatter items: the 1v1 top-right
  cluster is the Lickilicky/Mimikyu/Mantine/Lapras/Dondozo bulkpoint
  region, all unnamed; 2v2 bands are win-count tiers; the 0v0 GH-Good
  anomaly no longer reproduces post-engine-fixes; the average washes out
  because scenarios reward opposite stat axes). The shipped replacement
  is the matchup-fingerprint clusters section in every dive's Dive
  Analysis block (`scripts/deep_dive_matchup_clusters.py`); the old
  gap/banding experimental block is retired. Still-open follow-ups from
  the report, deliberately not built: a "Color By: matchup cluster" mode
  on the MAIN scatter (labels are already embedded per-section; the
  wrinkle is that main-scatter color modes follow the moveset/mode
  dropdowns while cluster labels are per-moveset-0/default-mode), and
  polygon/hull overlays (mockup:
  `gopvpsim-cluster-polygons-mockup-2026-07-06.html`).

* **Visualize where stat product misleads (stat-product as a Color By
  option + battle-score y-axis)** *(requested 2026-06-24)* — Make it easy to
  SEE at a glance when ranking by stat product is a bad guide. Two pieces:
  (1) add "stat product" (or stat-product rank) to the interactive scatter's
  Color By dropdown (currently HP/Def/Atk); (2) offer battle score (avg,
  and/or per-scenario wins) as the y-axis. Then a high-stat-product (bright)
  marker sitting LOW on the battle-score y-axis visually exposes the
  mismatch — exactly the "stat product != performance" cases (low-DPE or
  level-capped mons where the attack step between adjacent IVs is tiny, so
  premium-bulk IVs and high-atk IVs perform nearly the same). Cross-ref the
  wins-based-y-axis work in the "RyanSwag-style matchup-flip annotations +
  wins-based y-axis" item above (shared y-axis machinery) and the clustering
  item (Color By already reveals banding). Don't build in the
  new-mechanics session.

* **Send an HSH Discord member a Discord message about the Lurgan 102.9 def floor**
  — Our 2026-04-08 bulkpoint Level 3 enumeration against the Annihilape
  mirror found that the historical Lurgan Ape `def ≥ 102.9` floor is
  *unrecoverable* from current sims: the next bulkpoint above 102.9
  (`shadow_ball ≤149` at def 103.34) is unreachable for today's
  converged cohort (max def ~101.30). The 102.9 floor predates Rage Fist,
  so the threat-move set has shifted. Ask an HSH Discord member whether the
  historical calibration was against a Counter or Close Combat tier
  transition, or against something more niche (Shadow Ball / Night Slash).
  This is the missing context that would let us promote a specific
  bulkpoint to a Level 1 anchor with full provenance.

* **Speed test** (parked 2026-11-18 from TODO) -- compare our speed vs the
  PvPoke JS code, look for
  ways we can speed ours up. *(Partly addressed 2026-06-10: holistic
  perf review found and fixed a 2.0x engine regression dating to the
  2026-04-15 correctness arc — see DEVELOPER_NOTES "Performance
  baseline" for the regression gate and `docs/perf/` for the writeup.
  The vs-PvPoke-JS throughput comparison itself remains open.)*

* **Limited-availability mons: real IV floors for ML sweeps -- optional
  residue** (parked 2026-11-18 from TODO).
  Resolved slice (floor-10 resweeps, enumeration research, shadow-legendary
  gap) recorded in TODO_archive + `docs/reviews/2026-07-03_limited_availability_iv_floors.md`.
  STILL OPEN (both need Michael, both optional/low): (a) OPTIONAL belt-and-
  suspenders -- evaluate Dialga/Latias/Lugia/Reshiram (Shadow) down to 6/6/6 in
  their ML guides (the four Giovanni-primary legendaries whose grindability is
  only medium-confidence; worst-case floor is a bounded 6/6/6); (b) re-run the
  audit when Eternatus returns (Niantic announced it will).

* **Aegislash 1080-sample residue (investigation, parked; parked 2026-11-18
  from TODO):**
  - *Still undetermined in the 1080 sample* (fwd seat, after emulating
    both #10 and F2b; score mismatches unless marked log): Aegislash-S vs
    Thievul (2,0) log, (2,1), (2,2); Feraligatr (1,2); Rillaboom (1,1),
    (2,1); Dewgong (2,2); Seismitoad (1,1), (2,1); Cradily (0,0), (1,0),
    (1,1), (2,0), (2,1), (2,2); Aegislash-B vs Deoxys-D (2,2);
    Electrode-H (2,1), (2,2); Turtonator (1,0), (2,0); Cradily (1,1),
    (2,1); Seismitoad (1,0), (2,0), (2,1); Stunfisk-G (2,2); Morpeko
    Full Belly (Blade (2,1) score; Shield (1,x)/(2,x) and Blade (2,0)/(2,2)
    log). Plausible but UNTRACED attributions: Morpeko cells = bug #8,
    Cradily cells = the deliberate estimate-stage choice (the audited
    Cradily row uses 4/14/14, the sample 15/15/15).

* **"Does IV choice still matter once you're bulky?" metric** (parked
  2026-11-18 from TODO):

  IDEA, parked 2026-09-09 (Michael: re-think after more dives land): a
  "does IV choice still matter once you're bulky?" number for the dive page.
  Metric is the RATIO, not the absolute spread -- what fraction of the full
  4096-spread score range still shows up among the bulkiest 10%:

      Melmetal UL   full 25.8   top-10% 12.0   kept 47%
      DD GL         full 31.2   top-10% 13.9   kept 45%
      Melmetal GL   full 39.4   top-10% 12.7   kept 32%
      DD UL         full 72.3   top-10% 12.8   kept 18%

  The absolute top-decile range is nearly constant (12.0-13.9 across all four)
  and so carries NO information; only the denominator separates them. DD UL has
  the widest total spread of the four yet the flattest top end -- almost all its
  value is in being bulky at all. Melmetal UL keeps its gradient all the way up,
  which is the "worth digging in before spending resources" case.

  Caveat that needs resolving with more data: points-gained tells a different
  story than shape. Best-vs-median inside the top decile is 4.9 for Melmetal UL
  vs 7.5 for DD UL, i.e. DD UL rewards optimization MORE in raw points while
  having the flatter shape. Which of the two a reader actually needs is the open
  question. Computable from the replay blob alone -- no re-simming.

## Slayer card UX (post-bulkpoint shipped 2026-04-08)

* **Slayer-card signal-loss — REMEDY SHIPPED 2026-06-11 (Michael's
  pick: the 4+3 hybrid).** Slayer Builds tables now hoist parents
  cleared by EVERY emitted build into a single "Every build below
  clears:" callout (option 4) and rarity-code the remaining per-row
  badges by within-table clear rate (option 3; ≤25% hot, ≤60% mid).
  Verified on the Oinkologne replay: all 143 parents hoisted, ~360KB
  lighter HTML, rows read "common set only" — which surfaced the
  deeper diagnosis: **Anchors-First saturation is STRUCTURAL**
  (membership = clearing the max parent set), so within-table
  differentiation lives in the CMP%/atk columns by design. The S2
  note's "all-counted-parents membership or tighter selectivity gate"
  is the follow-up if real within-table spread is wanted. The
  SYSTEMIC audit below (other surfaces: threshold-tier dropdown,
  banding, Notable-IVs badges) remains open. *(original entry kept
  for the audit scope:)* — With Level 3
  auto-bulkpoint enumeration shipped, every survivor in the converged
  cohort passes nearly every parent's *lowest* sub-anchor (which is
  trivially cleared). Result: Bulk Slayer membership = 100% of the
  survivor pool, no signal. Same effective problem for Atk Slayer with
  auto-BP enumeration. **We will almost certainly find similar
  signal-loss in other places once we go looking** — e.g. the CMP
  Slayer top-quartile fallback may saturate too on some species, the
  banding-by-color analysis in the interactive HTML may have similar
  issues, and the threshold-tier dropdown may produce vacuous tiers
  on some cohorts. Treat this as a **systemic audit** rather than a
  local Bulk Slayer fix. Possible fixes for the immediate Bulk Slayer
  case, none ideal:
  1. **Minimum interesting threshold gate**: in the resolver, suppress
     sub-anchors whose lowest tier is cleared by 100% of the cohort.
     Pros: simple, applies uniformly. Cons: cohort-dependent (two
     dives with different cohorts get different anchor sets).
  2. **Show only differentiating parents in row badges**: render
     a parent's badge only when this row passes *more* sub-anchors
     than the cohort median for that parent. Pros: highlights what's
     unique. Cons: hides structure that's "everyone passes 6/6", which
     is sometimes information.
  3. **Tier badges by significance**: color-code badges by how rare
     the row's sub-anchor count is in the cohort. Pros: keeps all info,
     adds signal. Cons: more visual complexity.
  4. **Hide parents with 100% pass rate from the filter panel and
     row badges, surface them once in a "everyone passes" callout**.
     Pros: cleanest. Cons: extra renderer state to track.
  Pick one (or a hybrid) before implementing. This is *not* the same
  bug as the cell-level tooltip dump (fixed 2026-04-09 separately).
  When this is worked, sweep the rest of the slayer/threshold/banding
  output for similar "everyone passes the lowest tier" patterns.

  **Observed instance — Oinkologne GL (2026-04-19).** Dive 1 of the
  overnight re-dive; Mud Slap / Body Slam / Trailblaze scatter under
  `userdata/website/oinkologne-great-league/index_m0_*.html`. Slayer
  IVs (yellow markers) cluster in the top-RIGHT of the scatter — i.e.
  rank-1-ish stat product *and* high avg battle score — instead of
  the traditional Lurgan-Ape-style LEFT-cluster where slayers sit at
  worse bulk in exchange for higher attack. Mechanism: Oinkologne
  caps at level ~22-23 at GL CP, so the atk range across IV spreads
  is narrow, *and* Mud Slap's low DPE means the damage step between
  adjacent atk values is small — so the slayer atk breakpoint lands
  below where rank-1-bulk IVs already sit, making the "slayer" tag
  non-discriminating against premium bulk. Concrete real-world
  instance of the signal-loss concern this TODO flags. Worth using
  as the first test case when the audit happens; if the chosen
  remedy doesn't differentiate the Oinkologne scatter, it's not
  solving the problem.

## Slayer iteration cleanup

* **Mirror-slayer re-look — RESOLVED 2026-06-10 (arc S2).** Archetypes
  + graded tie metric shipped per Michael's four design decisions;
  full writeup in CHANGELOG.md (2026-06-10 S2 entry). The dracoviz
  tournament-CP item under "Analysis goals" could eventually supply
  an *empirical* mirror population to replace the Nash pool.

* **Investigate inconsistent slayer Max Wins column** *(cosmetic, not
  blocking — ranking is correct)* — Yesterday's
  `annihilape_*_old.html` files report Max Wins values in the round
  table that aren't multiples of `n_even` (3) — e.g. round 2 max=41.
  Today's runs with the same code (and same metric=even-strict) produce
  values that ARE multiples of 3 (round 2 max=123 = 41×3). The
  converged pool sizes match exactly (round 1 = 66 in both), so the
  iteration logic is consistent and IV ranking is preserved; only
  the displayed Max Wins column number differs. Either the metric
  semantics changed between runs, or the HTML rendering uses a
  different code path that I haven't found. Check git history of
  `iterative_slayer_discovery` for any silent shifts. Discovered
  2026-04-08, deferred as task #13.

* **Re-run Annihilape mirror slayer with Lurgan as an explicit
  opponent variant** — Hypothesis 2 from the validation doc was that
  the community optimizes against a broader opponent set (PvPoke
  defaults + atk-weighted + Lurgan-style hand-builds). With the new
  TOML format, we can put the Lurgan spread in as a named opponent IV
  cohort and re-run mirror iteration to see whether our convergence
  shifts. If atk 129.44 still wins, hypothesis 1 (outdated community
  spread) is confirmed; if it shifts toward 127, hypothesis 2 is
  confirmed.

* **Update `docs/validations/2026-04-07_annihilape_mirror_slayer_iteration.md`**
  to reflect an HSH Discord member testimony (Discord, 2026-04-08) and the
  bulkpoint Level 3 enumeration finding (2026-04-09): the community
  Lurgan Ape spread is a *historical anchor* calibrated to a Lickitung
  BP near atk 127.23, predating Counter nerf, Rage Fist addition, and
  Low Kick buff. Current expert advice is to push higher attack than
  the Lurgan baseline, which matches our converged result. Reframe
  the validation doc from "we disagree with community" to "we converge
  to current expert practice; the published Lurgan spread is a frozen
  historical reference." Also note the 102.9 def floor knowledge-
  recovery investigation conclusion (unrecoverable from today's data).

## HTML output paths

* **Orphaned-artifact detector for the publish pipeline** *(noted
  2026-06-21 during the PvPoke-attribution site-wide re-render)* — Stale
  files accumulate under `userdata/dives/` and `userdata/website/` that
  nothing links to and that were simply never deleted. Concrete instance
  found: some ML IV-guides have BOTH a current
  `<slug>_iv_envelope_all9.json` (the canonical `--all-shields` artifact
  the site is built from) AND an older-format `<slug>_iv_envelope.json`
  left over from before the all-shields switch. The site links only to
  the `_all9`-derived guide HTML; the plain-`_iv_envelope` JSON (and any
  HTML it once produced) is an orphan. (This is why the re-render had to
  dedup-by-slug-prefer-`_all9`; that nuance only exists because the old
  artifacts were never cleaned up.) Build a pipeline step / tool that:
  (a) enumerates generated artifacts (`userdata/dives/*.json`,
  `userdata/website/**`), (b) cross-references what the site index +
  pages actually link to (and what the current renderers would produce),
  (c) reports the orphans for review, and (d) optionally deletes with a
  `--execute` gate (dry-run default, like `scripts/clean_logs.py`).
  Don't auto-delete without the gate. Separate session.

* **Mirror-slayer iteration tables blow up HTML size for high-anchor
  species — MECHANISM REMOVED 2026-06-10 (arc S2)** — the redesigned
  Slayer Builds renderer emits at most 100 rows per archetype table,
  drops the per-row `data-anchors` attribute entirely (the filter-panel
  JS that consumed it is deleted), and the tie-explosion fix caps the
  survivor pool at `--mirror-slayer-pool`. The 60.7MB pathology can't
  recur on future renders; re-dive Jumpluff (S6) to shrink the
  published file. Historical detail below kept for the record.
  *(original entry, 2026-06-05)* —
  Jumpluff regular GL dive HTML is 60.7 MB (vs Ninetales 15.2 MB,
  Shadow Sableye 17.6 MB, etc.). 47 MB of the 60 MB lives in the
  analysis-sections body, almost entirely in two tables:

      ms0-slayer-1-table   12.0 MB  (vs Ninetales 0.31 MB)  37x
      ms0-slayer-2-table   33.6 MB  (vs Ninetales 0.72 MB)  44x

  Mechanism: each row enumerates its anchor membership inline via two
  bloated paths. Per-row HTML is ~9,696 bytes, and slayer-1 alone has
  1,608 rows.

  1. `<tr ... data-anchors="0 1 2 3 4 ... 1607">` — space-separated
     list of every anchor-index the IV passes. For Jumpluff (3,161
     resolved anchors, 133 parents, 1,607 IVs in round-3 mirror-
     slayer pool) the cross-product is ~1607 rows × ~1000+ anchor
     refs per row, all serialized into HTML attributes.
  2. Inline `<span class="dd-anchor-tag" data-t="...">opp_abbrev<span
     class="dd-anchor-tag-count">xN</span></span>` per opponent that
     the IV passes, repeated per row. For Jumpluff this is dozens of
     spans per row times 1,608 rows.

  Ninetales has the same renderer path but ~280 anchors and a much
  smaller pool, so the cross-product stays under 1 MB per table.
  Bug is pre-existing (not introduced by recent renderer work);
  Jumpluff just happens to be the first species where the anchor
  count + pool size hit the pathological corner.

  **Open meta-question before optimizing — do we even need this so
  accessible?** Michael's framing 2026-06-05: "the mirror slayer
  code isn't perfect yet." If the underlying mirror-slayer logic is
  still likely to change substantively (anchor enumeration heuristics,
  pool-shrink criteria, score-margin tiebreaks, etc.), heavy renderer
  optimization is premature investment in a moving target. The
  cheaper path is to *demote* the mirror-slayer iteration tables —
  put them behind a collapsed-by-default `<details>` (or behind the
  experimental-analysis toggle that already gates clusters/banding)
  — until we have higher confidence that the displayed numbers are
  worth surfacing prominently. That's near-zero renderer work and
  immediately reduces user-facing surface area for code we're not
  yet ready to ship-quality-promote. Decide demote-vs-optimize
  before picking from the optimization options below.

  **Optimization options** *(only relevant if mirror-slayer is
  promoted from "experimental" to ship-quality output)*:

  1. **Compress data-anchors to a per-IV bitmap** in the DATA blob.
     1,607 IVs × 3,161 anchors = 5M bits = ~640 KB compressed via
     base64. Each `<tr>` gets `data-iv-idx="N"` and the JS resolves
     the anchor set from the DATA bitmap at hover time. ~10x size
     reduction; cleanest fix.
  2. **Cap displayed rows to `--mirror-slayer-show`**. The chain
     passes `--mirror-slayer-show 20` but the rendered table emits
     all 1,608 rows. Likely the flag only affects log/summary output,
     not the HTML rows. Wire it through. Simple win.
  3. **Truncate anchor-tag spans per row** to top-N opponents
     (`tin×5 tog×11 ... +24 more`). Cosmetic; doesn't help if data-
     anchors stays inline.
  4. **Move per-row enumeration into a collapsed `<details>`**.
     Same total bytes; lazy-loaded in the browser. Doesn't fix file
     size; only helps initial render latency.

  The right combo when ship-quality time comes is probably (1) + (2):
  cap rows to the flagged N, then bitmap-compress what remains.
  Until then, demoting the section gives most of the operational win
  for none of the engineering cost.

* **Non-interactive `generate_html` — RESOLVED 2026-06-12 (arc S7)**
  — the static path was deleted outright (it had been crashing on a
  `NameError` since the S1 era with nobody noticing). `--html` now
  implies `--interactive`, so the old smoke-test trap (run without
  the flag, conclude nothing rendered) is gone too.

## Dive card — open follow-ups

*(Shipped 2026-06-22, commit e6ff5af: compact screenshot-able spec-sheet
card atop every dive + standalone `--card-out` export, with two headline
win-rates — single-IV and a top-512 opponent-IV robustness number. Built
to reproduce the Dragapult-Sim/Lundberger infographic look. First dive:
Shadow Corviknight GL pre-release, `userdata/dives/shadow_corviknight*.html`.)*

* **Card "High HP" pole surfaced a strictly-dominated spread (fix (a)
  RESOLVED 2026-06-25, 810f53c; design sub-question (b) still open).** On the
  UL Mimikyu card the High HP pole highlighted
  `0/15/15` (148.7 atk / 179.8 def / 135 hp, **CP 2319** — nowhere near the
  2500 cap — SP #702, NO crown marker). That spread is strictly dominated:
  `1/15/15` has the same def + hp but higher atk. We should never headline a
  strictly-dominated spread. Likely causes / fixes to weigh:
  (a) **The real disqualifier is the STATS, not the CP** — `0/15/15` is bad
  because it is strictly dominated (`1/15/15` weakly-dominates it on
  atk/def/hp), not merely because its CP is low. Primary fix: a
  strict-dominance filter (drop any candidate that another reachable spread
  weakly-dominates on atk/def/hp). Do NOT hard-gate on CP — a far-from-cap
  spread can still be worth building (e.g. a meta-relevant mon that maxes at
  L51 and still never reaches the league cap). If CP is used at all it is a
  soft clue only, and the right comparison is "far below the MAX achievable
  CP for THIS species in THIS league" (already accounts for L51-capped mons),
  never "far below the league cap (2500)"; (b) consider REQUIRING the crown
  marker (or whatever marks a
  rank-relevant / non-dominated spread) for a spread to appear on the top
  card — open question whether to hard-require it. Pick after looking at the
  pole-selection code. Cross-ref the spread-selection rework in "Upcoming
  plan-mode session" item 4 (distinctness-gated greedy cap) — this is the
  same surface; fold the dominance/CP-floor fix into that work or do it as a
  focused card-pole bugfix first. Concrete repro: UL Mimikyu card,
  Shadow Claw / Play Rough + Shadow Sneak. Do NOT fix in the new-mechanics
  session.
  **RESOLVED (a) 2026-06-25, 810f53c:** both poles now carry `ivAtk` as the
  final tie-break (deep_dive.py:3280-3282 attack pole, :3311-3313 bulk pole),
  so a pure def+hp / hp+def tie can no longer headline the lower-atk,
  strictly-dominated spread. Regression-pinned by
  `tests/test_card_pole_tiebreak.py` -- the poles are EXEMPT from the
  `_eff_mask` strict-dominance filter, so the tie-break key is their only
  guard, and the test covers both a synthetic efficient-frontier check and a
  source tripwire on the key. Sub-question (b) (hard-require the crown marker
  for a spread to headline the card) is the open design call, untouched here.

* **Opponent-IV robustness as a first-class sim axis (plan item 1.8).**
  Today `opp_iv_robustness` is computed ad hoc for the rec IV only, as a
  card headline. A full opponent-IV dimension in `deep_dive.py` (parallel
  to the bait / energy-lead axes) would let the WHOLE analysis report
  robustness per matchup (not just the headline) — e.g. "this IV beats
  G. Stunfisk regardless of which top-512 IV it rolled." Larger effort;
  cross-ref the "attack-weighted opponent variants" entry (same
  opponent-IV-variance theme) and the Tinkaton/Altaria shadow-IV-variance
  caveats. Do NOT build until there's a concrete consumer.

* **Robustness headline speed — signature dedup landed, gain modest.**
  `opp_iv_robustness` now uses the damage-signature dedup
  (`deep_dive_signature.signature_groups`) for fixed-form opponents
  (`dedup='signature'`, default), verified bit-identical to no-dedup
  (`test_opp_iv_robustness_signature_dedup_is_exact`). But the top-512
  stat-product cohort has diverse damage signatures, so it only collapses
  ~1.5× (less for shadow opponents) — the ~5.5 min full-pool headline drops
  to ~3.5-4 min, not the 4-5× originally hoped. `--card-robust-k` still
  caps the cohort for fast smokes. If robustness needs to be genuinely fast
  (e.g. card on every published dive), the lever is caching the per-(focal-
  IV, opponent) robustness result, not tighter exact dedup (1.5× is the
  exact-dedup ceiling here).

* **`deep_dive_signature` CMP column — FIXED 2026-06-22, NO published
  pollution found.** `signature_groups` built the CMP column from
  *effective* atk, but the engine decides CMP on unboosted `cmp_atk`
  (2026-06-13 fix). For shadow-MISMATCHED pairs the two boundaries differ by
  the ×1.2 shadow factor, so a profile could in principle mis-group.
  **Measured impact first:** focal sweep with signature-dedup vs the
  CMP-safe path across 12 shadow-mismatched matchups (both directions, incl.
  the published shadow dives), all 9 shields, all 4096 IVs = 442,368 cells →
  **0 differences**. Reason it never bites: two IVs share a signature group
  only if their *damage* tables match, which pins effective atk to a band
  finer than the 20% CMP gap, so a group can't straddle the real CMP
  boundary. Fixed anyway for hygiene: threaded each side's shadow flag into
  the side struct and compute the CMP column on `atk/1.2` (same-shadow and
  non-shadow pairs are unchanged by construction). Also closed a latent
  cache gap: `engine_hash` now hashes `scripts/deep_dive_signature.py`
  (covers BOTH sweep + slayer caches; slayer reuses engine_hash). No re-dive
  needed.

* **`_species_has_form_change` keys on the form name (latent nit).** It is
  exact for today's meta only because the sole stat-divergent form-change
  opponent (Aegislash) is pool-named by a formChange-bearing form. A future
  stat-divergent toggle/set species whose pool name lacks the formChange
  key (cf. Morpeko (Hangry), harmless today since its forms share
  baseStats) would be silently misgrouped by the robustness dedup. Fix by
  resolving to the base speciesId and checking both forms if that ships.
  (Comment in place at the function.)

* **Sprite slug for non-base forms.** `sprite_data_uri` derives the
  pokemondb slug from the PvPoke speciesId; regional/gendered forms
  (`farfetchd-galarian`, `indeedee-female`, ...) may not match pokemondb's
  path and 404 → graceful CSS typing-block fallback. Add a slug-override
  map only if/when a non-base-form dive wants its real sprite.

## Upcoming plan-mode session: dive/article content + information architecture

A dedicated plan-mode session (fresh, not mid-stream) to settle WHAT the
dives/articles/card show and HOW it's organized, before nailing down card
placement. Scoped with Michael 2026-06-22. Collected items:

1. **Articles vs dives distinction.** It's murky. Today: a *deep dive* =
   one species' full interactive IV/moveset analysis; a *CD article* =
   editorial CD-move writeup linking to dives; *ML IV-guides* = a third
   thing (XehrFelrose-style). Decide: merge, or rename "CD articles" ->
   "articles" + clarify the taxonomy + site nav.

2. **Dive content + organization audit.** Some info looks
   duplicated/overlapping across sections; the organization may not be
   clear. Take a hard look at what a dive should show and in what order
   (this is the "what should the dive actually present" question, which is
   why it's plan-mode not a patch).

3. **Card placement.** Graph-as-headline vs card-at-top. The card injection
   point is a ~one-line move; decide AFTER 1+2. (Card currently sits above
   "Deep Dive Results", below the interactive scatter.)

4. **Breakpoint-coverage card spreads (was card item 3).** The current
   spread selection (top-3 rec_candidates by composite score) clusters near
   rank-1 -- e.g. Shadow Corviknight showed 0/13/14 (SP#1) and 0/12/14
   (SP#4) as near-twins. Replace/augment with a HYBRID: keep our anchors
   (rank-1 bulk + max-atk/CMP) + add breakpoint-coverage spreads (each
   targeting a named opponent's break/bulkpoint, using the anchor data we
   already compute), and dedupe near-identical spreads. Variable **2-6**
   spreads via a **distinctness-gated greedy cap**: order by priority, add a
   candidate only if it clears/wins a materially different set than those
   already shown; floor 2 (bulk + attack poles), cap 6, stop early when no
   candidate adds distinct value; tunable threshold. Consider also a
   "newly-cleared breakpoints" list like Dragapult-Sim's "18 guaranteed
   breakpoints".

5. **ML IV-guide article enrichment (Michael loves these; strong automation
   example).** Today they report net wins/losses -- the biggest part of the
   story. Add the matchup-QUALITY delta: gained/lost break/bulkpoints that
   meaningfully change post-match state (how much HP/energy we vs the
   opponent have left), EVEN WHEN the win/loss doesn't flip. E.g. "still
   wins vs X but banks a charged move of energy for the next mon" or "loses
   the bulkpoint vs Y so you eat one more Y charged move". We already
   compute break/bulkpoints (anchor system) and have post-match HP/energy in
   the sim; this is surfacing the MARGIN, not just the binary flip. Connect
   to: the energy-lead axis (post-match energy carry-over), post-debuff
   breakpoints, and the matchup-flip annotation work. Generated from sim
   data, no hand-authoring -> stays ship-mode clean.
   **CLUTTER is the central design risk (Michael, 2026-06-22): he wants to
   explore this but NOT at the cost of the articles' concision** -- their
   value is partly that they're clean and scannable. So this is a "surface
   the MEANINGFUL margin deltas only" problem, not "show every
   break/bulkpoint": needs a significance filter (only deltas big enough to
   change a shield/energy decision) and likely progressive disclosure
   (collapsed-by-default detail / a one-line summary / top-N), consistent
   with the project's "hide don't remove" + signal-loss patterns. Decide the
   default-visible surface vs the drill-down in the plan session -- overlaps
   directly with audit item 2 (content + organization).

## CD article generator — open follow-ups

The Python article generator (`scripts/generate_article.py`) shipped
across Post-S5 Sessions S6-S10 (2026-04-17/18). Open polish:

- **S8 envelope-annotation wiring on the article surface** — S4's
  `envelopePositions` dict is keyed by Notable-IVs category name
  (`Atk Slayer`, `Lapras Atk`, etc.); the article's IV
  Recommendations section renders `tier` cards (stat-cutoff-based,
  from `data_obj['tiers']`), so the annotations don't have a natural
  slot. Two paths: (a) add a Notable-IVs card block to the article
  IV-recs section and annotate those directly, or (b) build a
  tier-name → category-name mapping and attach the envelope annotation
  to whichever tier exposes the anchor that backs the category. (a)
  is simpler but duplicates dive content; (b) reuses presentation
  but needs a naming bridge. Defer until someone has an opinion.
  Watch item: when S8 lands, audit `render_notable_ivs_section`'s
  UX caps (`notable_max_count=5`, `max_members_shown=5`) under the
  extra shape-tag line.

## Pre-ship arc -- residual open polish (parked 2026-11-18 from TODO)

The 2026-04/06 pre-ship arc shipped (site published 2026-06-07; see
CHANGELOG.md). The minor polish residue (the Favicon item stays in TODO.md
"Site polish"):

- **G16 — methodology-details guide pointers (remaining half).** The
  comparison-page block shipped `95fcf74` (wrong win-rate boundary
  fixed + derived counts + guide pointer) and the Meta Coverage half
  shipped earlier (`e6d431c`). Remaining, both in
  `generate_article.py` and both currently regeneration-unverifiable
  (the male-Oinkologne article was retired in `7df5165`, so no article
  renders from HEAD): (a) `:1835-1848` Opponent-IVs/Bait recap ->
  pointer at `guides/cd-article/body.md#dropdown-control` (anchor
  confirmed present); (b) `:2461-2469` "About these tiers" --
  move-THEN-point: the no-1:1-mapping fact must first be ADDED to the
  guide's IV Recommendations section, else a bare pointer deletes
  information.

- **G1 + G2 + G7 — richer auto-gen prose template** [post-ship,
  recommended]. F1 Meta Role, F2 key-flips callout, and
  F-fast/charge-moves shipped as deterministic rollups; JRE-style
  prose ("Mud Slap takes Male Oinkologne from 0% to 76.6% vs
  Steelix — the signature upgrade") would close the register
  gap. Template change, not Claude-drafted prose, so
  ship-policy-clean. 0.5-1 session. Benefits every future dive.
  Bundles with **Row D** — bulk-vs-peers paragraph (micro-gap from
  original §3.D, never made it through F1's auto-gen template).

- **F-tier-name-cleanup** [post-ship] — simplify IV-rec tier card
  names (current: `Steelix (Shadow) Slayer -   (Wigglytuff Slayer
  -   (Wigglytuff Atk))`) to RyanSwag's name/signature convention
  per `docs/ryanswag_methodology_gap_analysis.md` (the earlier pointer,
  the gitignored `docs/reference_deep_dives/ryanswag/STYLE_ANALYSIS.md`,
  is no longer on disk; repointed 2026-11-18).
  Bundles with S5a rename work in post-S5 arc.

- **F-shadow-narrative** [post-ship] — Shadow-variant comparison
  prose block for species that have shadow forms (not applicable
  to Oinkologne ship).

- **F5** [post-ship, gated ≥3-5 shipped articles] —
  multi-article-reader cross-linking footer. Not worth building
  until cross-reference surface is large enough.

- **Personal-collection: `scripts/suggest_builds.py`.** CLI
  helper: takes `--species`, `--league`, `--roles lead,closer`,
  path to a PokeGenie CSV export, and the shipped dive HTML.
  Parses Top IVs + Anchors + Matchup Flip tables, intersects with
  the collection, prints a ranked shortlist per role with the key
  tradeoffs (atk/HP/def, anchor flips, score Δ, XL/dust cost).
  Maybe 2-3 hours; deprioritize if scatter paste-box overlay +
  Mirror CMP columns are enough.

- **P2 single-form opponent links.** `_render_matchup_delta_section`
  (line 1954) doesn't yet link opponent cells — applies to
  non-CD articles that aren't per-form. Extend when the first
  such article actually ships.

- **P3 article-surface design question.** Dive-side envelope-tag
  retrofit shipped 2026-04-23 (`patch_dive_envelope_tags.py`);
  a category-card surface on the CD article itself (linking
  envelope-shape to a specific "Cost to XL" judgment) remains
  the original P3 question and has not been addressed.

- **Cross-form opponent expansion (parked).** Item 4 (auto-
  form-sibling expansion in `build_opponent_pool.py`) — design
  done but parked pending review of rendered Oinkologne article;
  decide pool-level vs render-level filter for hypothetical-form
  rows.

## Deep-dive narrative — open polish

* **Move display-name shown two incompatible ways on one page (DRY, confirmed
  2026-06-28 round-3, 2/2 skeptics, already-inconsistent).** Two helpers derive
  a move's label: `auto_gen_narrative._gm_move_display` (scripts/auto_gen_narrative.py:90-107)
  uses the gamemaster `name` field; `deep_dive_analysis.pretty_name`/`pretty_moveset`
  (scripts/deep_dive_analysis.py:72-83, also `generate_article.py:1848,1969` and
  `iv_envelope_analysis.py:226`) always title-case the raw moveId. For ~39 moves
  the labels already differ on the SAME dive page — e.g. header "Super Power" vs
  narrative "Superpower"; "Power Up Punch" vs "Power-Up Punch"; "Natures Madness"
  vs "Nature's Madness"; "Hidden Power Bug" vs "Hidden Power (Bug)". Cosmetic
  (no number changes), but a real inconsistency. Fix: single-source move display
  (have `pretty_name` consult the gamemaster name like `_gm_move_display`, or
  route both through one helper). Broad multi-file touch + ship-narrative-
  adjacent (auto-gen prose), so do it deliberately, not unattended. Render-only.

* **22-IV catch-phrase edge case** — `_catch_phrase` caps at 500
  catches as "very rare". The 22-IV Altaria Slayer on Goodra moveset
  4 shows `~129-258 for a 50-75% chance` — under the cap but still
  a large number; arguably should have a middle "rare" tier. Wait
  for more species in the 50-300 range before adding a tier.

* **Narrative flavors not reflected in Plotly scatter tiers** —
  surfaced on Oinkologne Tackle moveset (Session 4): the IV Flavor
  Guide derives 4 flavors (Premium Bulk, Quag Slayer, Shadow Quag
  Slayer, G-Corsola Slayer) but the Plotly scatter only shows
  "Top 5%" because the anchor-flip aggregation system found too
  few records to derive named tiers. The two tier systems (anchor-
  flip-derived plot tiers and narrative-derived flavors) are
  independent; when the anchor system falls back to "Top 5%" only,
  the plot loses all the structure the narrative found. Consider
  feeding narrative flavors back as plot tier annotations, at least
  as a fallback when anchor-derived tiers are sparse.

* **Hand-named composite categories via TOML** *(round 2 of structured
  IV categories)* — Round 1 shipped 2026-04-09 (commits f3aa4ad, 8ff4469,
  79e2e87, b344356) as the unified `IVCategory` framework with
  literal-intersection naming (`Atk Slayer ∩ Top 5%`). The natural next
  step is a `[Species.Great.categories.<name>]` TOML table that lets
  the user assign a memorable display name + custom description to a
  specific intersection (`bulk_floor_slayer`, `compromise_slayer`,
  etc.) and override the literal name with the playstyle name. Schema
  sketch: `includes_anchors = [...]` + `includes_tier = "..."` +
  `display_priority = N`. Defer until the auto-derived path proves
  useful on Tinkaton + 1-2 more species — single point of data
  doesn't yet justify the schema work.

* **RyanSwag-style autogenerated deep-dive section** *(own arc, scope
  after post-S5 arc ships)* — With the narrative renderer,
  namesake/merge/conformance fixes (S5a), article generator (S6-S10),
  histogram (S3), envelope metric (S4), matchup-flip attribution (S13),
  post-debuff breakpoints (S15), and bait-axis-in-narrative (S17) all
  shipped, revisit whether the deep dive (or a dedicated section of it)
  should autogenerate a prose output that looks like a RyanSwag
  GamePress article — same 5-part structure (intro, moveset discussion,
  PvP IV tables, per-league analysis, wrap-up), same prose style, but
  generated from our simulation data instead of Claude mimicking
  RyanSwag's voice. Not a session in the current post-S5 arc: (a)
  that arc is already 17 sessions + Aegislash, bail-prone; (b) the
  shape depends on what the renderer ends up capable of after S5a/
  S6-S10 settle. This is its own arc when the time comes.
  **Prerequisite check before opening**: confirm S5a items C1/C2/C3/C5
  shipped (name-signature coupling, namesake guarantee, 2-axis support,
  identical-stat merge). Those fixes are the RyanSwag-conformance
  floor; autogen doesn't make sense on a renderer that still produces
  name-signature mismatches. Separate from the JRE/CD article work in
  S6-S10, which has a different audience and format — **don't conflate
  them**; the CD article is mechanical spec-sheet + data tables, this
  is narrative prose structured like RyanSwag's articles.
  Flagged 2026-04-17 by Michael.

## Reproducibility

* **Deep dives have non-reproducible opponent data** — `scripts/deep_dive.py`
  fetches PvPoke rankings (`great`, `ultra`, `master`) from GitHub via a
  24-hour-TTL on-disk cache at `~/Documents/gopvpsim_cache/`. Two dives
  with the same CLI args can produce *substantially* different opponent
  sets if the cache was refreshed between them — not "Annihilape moved
  one spot," but "the entire top 20 changed." Discovered 2026-04-09 while
  trying to byte-equality-verify a JS rename refactor: the post-rename HTML
  vs the pre-rename backup HTML disagreed on the opponent list because
  the cache had been refreshed (likely by a `pytest` invocation that
  triggered `load_rankings`) between the runs that generated each file.
  CLI-args embedding (already shipped, see `format_cli_args`) lets a reader
  reproduce the *command*; this gap means it doesn't fully reproduce the
  *data*. Possible fixes:
    1. Embed a small "data fingerprint" in the HTML at run time: hash +
       mtime + first-N species of the rankings list. Lets a reader spot
       drift without enabling reproduction.
    2. Add a `--rankings-snapshot DATE_OR_HASH` flag that pins to a
       specific cache state for full reproduction. Requires durably
       archiving rankings snapshots, e.g. under
       `userdata/rankings_snapshots/`.
    3. At minimum, log the `great.json` mtime + first-5 species at run
       start so users notice when their dive's opponent set is unusual.
  Option 1 + option 3 together is probably the right starting point —
  cheap, doesn't require any new infra.
  *Update 2026-06-10 (arc S4):* the sweep disk cache key now hashes
  gamemaster content and keys opponents by their *resolved* IVs +
  movesets (see DEVELOPER_NOTES "Sweep disk cache"), so cached scores
  can never silently mix data vintages — but the HTML fingerprint /
  run-start logging for human-visible drift detection (options 1+3)
  remains open.

## Cache GC: prune all namespaces + dive-script opt-in prompt (parked 2026-11-18 from TODO)

Make `scripts/gc_cache.py` able to prune **every** cache namespace, and wire a
prune option into the dive scripts wherever caches get created.

- **GC coverage.** Today only `sweep/` has vintage-aware pruning (gamemaster in
  `meta.json`); `slayer/` and `iv_envelope/` are report-only because they bake
  gamemaster+engine into opaque filename hashes with no readable vintage. Give
  those two a readable vintage (sidecar or meta file at write time) so GC can
  apply the same N-1 retention to them. (`iv_envelope/` may be retired instead
  once the ML path moves onto the sweep cache — cache-rework Phase 6.)
  [2026-11-18: the sweep cache (v7) now stamps the gamemaster per column, not
  in `meta.json` (`gc_cache.plan_v7_columns`); `slayer/` and `iv_envelope/`
  are still report-only.]
- **Dive-script opt-in.** Wherever a cache is created (`deep_dive.py`,
  `deep_dive_slayer.py`, the IV-envelope/ML path, sweep), add a prune option
  that **defaults to "don't prune."** When the run is a *full* dive of a whole
  league (UL / GL / ML), **ask Michael whether to prune** before/after the dive
  rather than silently keeping or silently deleting.
- Retention target stays N-1 (current gamemaster + 1 prior), matching the
  existing `gc_cache.py --keep-vintages 2` default.

## Accepted test debt

* **Cramorant dive-ASAP gate** (parked 2026-11-18 from TODO's Cramorant
  section; item (b) of that record stays in TODO). ACCEPTED TEST DEBT (per
  policy, recorded): (a) the dive-ASAP gate's
  fresh-vs-frozen `move.damage` divergence (documented at the rule in
  battle.py) has no discriminating test -- needs a post-missile-debuff
  re-dive scenario where the two damage bases differ; write it if such an
  oracle cell ever drifts.

## UI / Display

* **Additional scatter plot color modes** — The current color scheme has some dark
  points that are hard to see against the background. Add a dropdown with alternate
  color modes (e.g. color by stat product rank, color by HP, color by attack,
  single bright color for non-threshold IVs). Should be a JS dropdown next to the
  existing moveset/scenario selectors.

* **Pretty-print move and species names in reports** — HTML output, analysis
  sections, and console summaries should use natural casing (e.g. "Gigaton Hammer"
  not "GIGATON_HAMMER", "Galarian Stunfisk" not "STUNFISK_GALARIAN"). The CLI
  argument parsing can stay uppercase/underscore for ease of typing.

* **List all valid options in CLI help** — Flags like `--group` and `--charged`
  should enumerate all valid choices in `--help` output (e.g. list all known
  PvPoke groups, list all legal moves for the species). Currently only a few
  example group names are shown. Get user input before fully
  implementing this, though, because listing all legal moves might
  make the help text too long.

* **Table sorting** We have a lot of tables that would be a bit more
  useful if we made it so that clicking on the headers sorted the
  table by that column (the standard thing where you click it once to
  sort descending, and a little arrow appears to show how you've
  sorted, then you click it again to reverse the sort order, the arrow
  changes direction, you click on another column to sort by that
  column and the arrow from the first column goes away, etc).

* **Client-side add / remove anchors + thresholds** *(an HSH Discord member
  request, 2026-04-26)* — Today's TOML-edit flow requires a local
  clone, a re-dive, and a PR. An HSH Discord member asked whether a per-species
  in-browser surface could let readers add their own custom anchors
  (or hide existing ones) on a single dive without affecting the
  rest of the site. Use case: cut visual noise by hiding anchors
  the reader doesn't care about, or pin a custom matchup the dive
  doesn't already surface. Scope:

  1. **Hide**: a per-tier-card "hide this anchor" toggle that
     adds/removes the anchor from the rendered bullet list and the
     scatter-plot tier coloring. Pure client-side; saved to
     `localStorage` keyed by dive slug. Should be the easier of
     the two paths.
  2. **Add**: a "create custom anchor" surface that lets the reader
     pick an opponent + threshold and have it render on the current
     dive's tier cards / bullets / scatter. Harder — the threshold
     would need to be evaluated against the dive's cached score
     data without re-simulating. Possibly limited to "stat cutoff
     only, no per-move sub-anchors."

  Until this lands, the Under the Hood guide notes the TOML-edit-
  via-PR flow as the only option.

**Architecture note (2026-04-07)**: The BeeWare/iOS-pure-Python constraint
has been DROPPED. Mobile is no longer a meaningful use case for the deep
dive scripts. We can now use numba, Cython, C extensions, etc. — though
the core `gopvpsim/` library should still avoid making mobile impossible
in case we want to revisit it. The optimization work below targets the
desktop deep-dive workflow.

**Round 1 + Round 2 + chunking optimizations are SHIPPED** (see Shipped
section). Real-world impact: 9hr → 6 min on the actual deep-dive workload.
Round 3 (numba JIT for the inner sim loop) was deprioritized because
fastmath was confirmed a dead-end and the workload is no longer the
bottleneck.

* **Better slayer iteration progress reporting** — The current progress
  prints fire only when a `pool.imap_unordered` chunk completes. With
  10 chunks each taking ~85 minutes, the first progress line doesn't
  appear for 85 minutes. *Partly addressed in 2026-04-07 by chunking
  to ~100 chunks (commit 8498ec4), but consider further refinement
  if individual chunks become slow again.*

* **Incremental slayer cache flush** — The slayer iteration cache
  (`SlayerCache` in `scripts/slayer_cache.py`) currently does one read
  at startup and one save at the end. If a long run crashes mid-iteration
  (e.g. 28 minutes into a 30-minute run), all the work done in that run
  is lost. Add periodic flush to disk after each slayer round so a crash
  loses at most one round's worth of sims. Tiny code change, big peace
  of mind.

* **Form-change path speedup (Aegislash Shield, Mimikyu, Morpeko)**
  — **MOSTLY RESOLVED 2026-06-10 as a misattribution.** The ~10×
  Shield-vs-Blade gap was dominated by the engine-wide pvpoke_dp
  regression (per-call stage-table rebuild, fixed in `5e25e28` — see
  DEVELOPER_NOTES "Performance baseline"), which Shield's battle shape
  (charge-farm → near-KO DP every turn) amplified. Post-fix smoke
  measurement (Phase 2, 3 opponents, 1v1): Shield 4,800-6,900 sims/s
  vs Blade 5,200-5,700 — parity. The hypotheses below were never the
  dominant cost. Keep this entry only as a pointer: if a future
  mirror-slayer-scale Aegislash (Shield) run still looks slow
  relative to Blade, re-measure before reaching for the plan below.

  *Original 2026-04-19 observation (pre-fix):* Mirror-slayer Round 1
  on Aegislash (Shield)
  projected ~25-30 min per moveset (~10× the Blade-side baseline) at
  ~700 sims/s vs the 7,000 sims/s Phase 2 baseline. Correctness is fine
  (validated by `tests/test_aegislash_vs_azumarill_form_change`); the
  9.5M-sim scale just magnifies the form-change per-sim overhead.

  **Suspected dominant costs** (unprofiled):

  1. `apply_form_change(bp, opponent)` does a full state swap: base
     stats (atk/def/hp), active moveset, `bestChargedMove` reselection,
     per-move cached damage tables invalidated. Fires every time
     Aegislash (Shield) lands its first charged move, which is nearly
     every sim in a mirror-slayer scale run.
  2. Per-turn `attacker.current_form_trigger` / `defender.current_form_trigger`
     property evaluation on every charged-move event, even for species
     with no form change (no-ops but not free). Cheap individually;
     compounded across 9.5M sims it adds up.
  3. Damage-and-timing caches that key on (attacker form, opponent) get
     stale on form change and rebuild from scratch the next call. If
     caching is per-form, the form swap is a mandatory invalidation.

  **Why Shield hits this harder than Blade:** Shield-focal transforms
  on every charged move (every battle). Blade-focal transforms only
  when Aegislash *shields* an opponent's charged move — conditional
  on shield count and policy — so the code path runs much less often.

  **Perf session plan** (~2 hours):

  * `cProfile` or `py-spy` on `scripts/deep_dive.py 'Aegislash (Shield)'`
    with `--opponents 3 --mirror-slayer-rounds 1`, compare to same
    command on Aegislash (Blade). Flame graph diff highlights the
    form-change-only hot path.
  * Likely interventions: (a) precompute both forms' damage tables
    up front and swap by pointer, (b) lazy-invalidate damage caches
    per-opponent rather than per-form, (c) inline the form-trigger
    checks into a single type-dispatch so non-form-change species
    pay zero per-turn cost.
  * Success criterion: Shield mirror-slayer within 2× Blade's rate
    (rather than today's 10×).

  Deferred because correctness is fine and Aegislash isn't on the
  pre-ship critical path. Pull forward if Aegislash becomes a frequent
  dive target post-CD.

## Schema simplification

* **TOML simplification triggers** *(collect friction, don't act yet)* —
  Worry surfaced 2026-04-09: the legacy JSON threshold files were three
  keys; the current TOML schema is ~530 lines of docs and Annihilape's
  hand-authored file is ~180 lines. Sample size of one species (plus a
  one-line tinkaton stub) is too small to design a simplification
  against — Annihilape is also the *worst* canary because its
  Lurgan/an HSH Discord member historical provenance pressure makes it
  documentation-heavy in ways most species won't be.
  **Action**: when authoring the *next* species TOML (Tinkaton CD prep,
  Goodra, etc.), aim for the smallest file possible — lean on the
  auto-fallback hard, skip provenance you don't need. If you reach for
  a schema feature and it feels heavy, write a one-liner here noting
  *which* feature and *why*. Three friction observations in a row is
  the action threshold; until then, collect.
  **Two candidates already named** without acting:
  1. The Level 1/2/3 anchor distinction is a doc artifact, not a
     schema artifact — the resolver just looks at which optional
     fields are populated. Could be re-presented as "fill in whichever
     fields you know" instead of three named precision tiers. Doc
     rewrite, not code rewrite — cheap whenever it stops feeling
     helpful to teach the levels separately.
  2. The mandatory spread/anchor split is overhead for one-off CMP
     anchors. Most species would benefit from inlining `ivs = [...]`
     or `above_atk = X` directly on the anchor instead of needing a
     separate `[spreads.x]` table. Don't *remove* the split — it earns
     its keep when multiple anchors share a spread (cf. Annihilape's
     `lurgan_ape` referenced by both `cmp_vs_lurgan` and
     `lickitung_brkp_above_lurgan`) — just make it optional.
  **Meta-rule**: distinguish complexity that *enables provenance*
  (description fields, source fields, the multiple breakpoint
  precision levels) from complexity that's *structural overhead*
  (deep nesting, mandatory spread/anchor split for one-offs).
  Simplifications target the second category; don't accidentally cut
  the first.

## User-facing documentation (Reader's Guides) (parked 2026-11-18 from TODO)

- **Round-3 screenshots** if/when reader confusion surfaces a
  specific gap (round-1 + round-2 screenshots shipped via `32fae84`
  and `e449b38`).
- **Add topics** beyond the five shipped — Michael asked that the
  topic list be a conversation at the start of the task, not a
  fixed scope. Plan a session to (a) add topics surfaced by
  an HSH Discord member / new readers, (b) reorder by current reader
  confusion, (c) decide whether related topics merge.

[2026-11-18: `32fae84` and `e449b38` are not valid objects in this repo
(the screenshots predate it or the shas were rewritten); `guides/` now holds
9 guides, not five.]

## Shared user_collection module — Option-2 migration prep (parked 2026-11-18 from TODO)

*(from gobattlekit's 2026-06-11/12 deep review, sections F/J — CP9 +
CP12. Not urgent; gobattlekit is otherwise ready to consume
`gopvpsim.user_collection` and has aligned its matching semantics to
ours. The CP4 over-leveled-mon fix and CP13 Burmy→Mothim fix shipped
here 2026-06-12; these are the remaining seams.)*

* **Split heavy deps into extras** — `pyproject.toml` hard-requires
  `numpy` + `markdown`, but the `user_collection` import path
  (user_collection → evolution_lines + pokemon → data) needs neither.
  numpy on iOS via BeeWare is a real packaging problem. Move them to
  an extra (e.g. `gopvpsim[sim]`) so a mobile app can take a core
  dependency. Note the user_collection docstring's "stdlib only"
  claim is false at package level until `certifi` (imported by
  data.py at module load) is also dealt with.

* **Injectable gamemaster/CPM source** — `match_mons` hardwires
  `get_pokemon_index()` → data.py's network-backed cache
  (`~/Documents/gopvpsim_cache/`, 24h TTL, NoDataError when offline
  with no cache). gobattlekit needs to supply its own bundled +
  ETag-cached gamemaster. Add a provider injection point (parameter
  or settable loader) on match_mons / get_pokemon_index /
  evolution_lines.

* **Golden parity-vector emitter** *(seeded by the gobattlekit
  threshold-pipeline session, 2026-06-12)* — a script that emits
  (species, IVs, level) → (stats, CP, rank) fixtures from our
  canonical primitives, checked into gobattlekit as test vectors so
  its stat math can't drift from ours. Complements the CSV parity
  corpus below (that one covers parsing/matching; this covers the
  arithmetic).

* **Shared CSV parity corpus (CP12)** — a small synthetic CSV
  (shadow, over-cap, out-of-range, gendered, branched-evo rows) +
  golden expected-results JSON, checked into BOTH repos and run by
  both suites, so the row-for-row contract can't silently drift
  again (it demonstrably did: gender, shadow, level-gating). Until
  Option 2 deletes the duplicate implementation, this is the only
  tripwire.

* **Gobattlekit threshold schema compatibility** (from TODO "Deferred
  cleanup: backwards-compatibility removal pass") in
  `gopvpsim.user_collection.check_thresholds` (and `as_legacy_dict` in
  thresholds.py) — once gobattlekit has actually migrated to use the
  shared module and we've confirmed it works, we may want to simplify
  the dict schema or unify with pogo-simulator's TOML anchor schema.
  But not before gobattlekit's migration lands. **The gobattlekit
  threshold pipeline actively consumes both as of 2026-06-12 — do not
  touch without coordinating.**

## Worlds 2026 -- dormant residue (parked 2026-11-18 from TODO)

Moved from TODO.md "Worlds 2026 -- code DORMANT until 2027"; TODO keeps the
revival trigger ("Worlds 2026 -- dormant until 2027": the Revival standing
rules pointer and the 2027 test un-skip).

Worlds (Aug 28-30) is over. Michael 2026-09-25 (perf-doc Q4 "no"): the
Worlds code, tests and `worlds/planes` stay in the repo DORMANT until 2027
-- no retire/delete pass now. The pages are off the site (no `worlds*.html`
in `userdata/website/`; publish rsyncs with `--delete`). Plan of record for
a revival: `docs/worlds_prep_plan.md`. Still open:

- **Retire-together bundle (rides the 2027 decision):** `thresholds/thievul.toml`
  `[Thievul.cd_prep]` (present 2026-11-18), the `worlds/meta.toml`
  `injected_move_ids` declarations + their on-page disclosures in
  `build_worlds_pages.py`, and the injection guards in
  `tests/test_worlds_bake_guards.py`.
- Link the IV Robustness guide FROM the Worlds hub/cheat sheets at the next
  Worlds re-render (needs the gamemaster re-pin in docs/worlds_prep_plan.md
  "Revival standing rules").

DECISIONS / EDITORIAL for Michael:

- Corviknight vs Shadow Quagsire per-spread scatter for
  r/TheSilphArena (the surviving lead after the skipped Discord
  post). OPEN QUESTION before drafting: which scenario? (memory says
  the 2-2 scatter; the original reminder pointed at 0-shield;
  re-verified data shows real structure in both 0-0, win_frac_all
  0.809, and 2-2, 0.86, while 1-1 is near-hopeless at 0.004.)
  Editorial findings, durable copy:
  ~/coding/reports/gopvpsim-worlds-2026-refresh-2026-08-27.html
  (core-breaker top-5: Medicham, Azumarill, Guzzlord, Aegislash-S,
  Mantine -- Mantine out-breaks Greninja 2:1 IV-robustly; Greninja
  27/35, its case is the energy-lead snowball; Annihilape 9th, #1 on
  the strict tier; HSH Greninja verification: 5/6 breaks confirmed,
  Tinkaton refuted).
- Deferred mirror bakes (Michael-approved deferral):
  empoleon__vs__empoleon and feraligatr__vs__feraligatr.
- Deferred joint-IV review minors (all in the 319c8a2 commit
  message): duplicate-grid double embedding (~826KB/page),
  pareto-axis self-inclusion, one-option basis dropdown, wall-table
  25-vs-12 wording, CSV dropped-row accounting, raw key fragments in
  the answers dump, sim-count phrasing.

Non-gating polish, dormant with the rest: a11y (badge text 4.36:1 in
pokemon-dark; hub mini-grids color-only), the optional session-6 survival
strip (scoped 2026-08-11), the optional pooled-usage display
(`usage_recent_pooled_pct`, unshown). Planning artifacts:
`userdata/worlds_planning/`.
