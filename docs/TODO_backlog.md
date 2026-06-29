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

## Features to add

(Form Change shipped 2026-04-14 for Morpeko/Aegislash/Mimikyu;
bait-axis as a deep-dive sim dimension shipped; DP cycle-timing
move selection closed 2026-04-15 as not-a-real-issue.)

* **Energy-lead axis (safe-switch / closer matchup flips)**
  *(scoped 2026-06-03 during Shadow Sableye build advice
  conversation; needs its own session)* — Currently the battle sim
  always starts both Pokemon at energy 0. Real PvP often has the
  focal species arrive with energy carry-over: a **safe switch**
  brings the back-line attacker in with some fast moves already
  generated before the original swap; a **closer** has typically
  burned several fast moves before the opponent's final mon comes
  out. The same matchup can flip win/loss depending on whether the
  attacker enters with 0, 1, or 2 fast moves of accumulated
  energy.

  Implementation sketch (analogous to the shipped bait_shields
  axis):

  1. **Battle-engine plumbing** — `BattlePokemon.__init__` gains
     an `energy: int = 0` parameter (it likely already has the
     field as state; the change is making it an init arg that the
     sim honors at T0 instead of forcing 0). Symmetric defender
     energy too, for completeness (defender carry-over scenarios
     are rarer but exist).
  2. **Sim axis** — `deep_dive.py` already enumerates
     `(IV × moveset × opp_iv × bait × scenario)`. Add an
     `energy_lead` dimension with concrete values keyed off the
     attacker's fast-move energy generation: `[0, fast_energy,
     2*fast_energy]` = `[0, 8, 16]` for Shadow Claw, `[0, 10, 20]`
     for Counter, etc. Three buckets keeps the aggregator
     tractable.
  3. **Aggregator surface** — extend `_find_matchup_boundaries`
     and `_aggregate_flips_by_anchor` to detect when a matchup
     flips between energy-lead values. Natural display surface:
     the existing "Matchup-Flipping Boundaries" section, with
     a new line per matchup like "Flips vs Galarian Corsola
     1v1 when attacker has 1+ Shadow Claw of stored energy."
  4. **Cap on realistic values** — energy-lead values above
     `(max_energy - cheapest_charged_cost)` aren't reachable in
     practice (you'd have already thrown the charged move). The
     axis values need to be clamped per attacker; otherwise the
     analysis surfaces unreachable matchup flips.

  **Use case** — safe-switch / closer mons (Sableye, Quagsire,
  Drapion, Wigglytuff, Lickilicky, anything that eats a shield
  then comes back) are exactly the species whose dive
  recommendations are most miscalibrated against the energy-0
  assumption. After landing this axis, every shipped dive in the
  scope-fits category benefits.

  **Estimated scope** — half a day for the battle-engine change +
  axis plumbing in deep_dive.py; another half-session for the
  aggregator + matchup-flip narrative integration. Tests:
  parameterize existing oracle tests with `[0, 8, 16]` starting
  energy and confirm the deterministic ones still match.

  **Cross-ref**: bundles naturally with the "matchup-flip
  annotations" arc already in progress (under "Analysis goals"),
  since both extend the per-matchup flip aggregator.

  **Empirical precedent (2026-06-03):** the one-off script
  `scripts/check_sableye_energy_lead.py` validates the feature
  concept end-to-end against a real build decision. It sims 4
  candidate Sableye IVs × 4 movesets × 66 opponents × 9 shields ×
  {0, 8, 16} starting energy = 28,512 matchups in under a minute
  on 1 CPU. Findings that confirm the feature is worth the
  scope:

  1. Energy lead reshaped **~50 of 594** per-(IV, moveset)
     matchups in this case (2/11/13 + Drain Punch + Foul Play
     went 332 → 355 → 383 wins, +15% across the energy axis).
  2. The IV ranking was stable across energy levels for this
     pool — 2/11/13 won at energy 0 AND at energy 16 — so the
     feature doesn't reverse stat-product-based IV choices, it
     surfaces *additional* matchup data on top.
  3. The script's hack (mutate `bp.energy` after
     `make_battle_pokemon` returns; `BattlePokemon.initial_energy`
     already exists at the engine layer) confirms only the sim
     axis + aggregator + display surface need building — the
     battle engine is ready.

  When implementing the feature, fold the script's structure
  (per-IV, per-moveset, per-energy aggregate table + matchup-flip
  list) into the deep_dive.py aggregator output. The throwaway
  script can be deleted at that point — its existence is logged
  here for the precedent + the mutation-hack pattern that proved
  the engine-side feasibility.

  **Counter-intuitive cross-check (2026-06-03) — keep as a
  regression test when the feature ships:** the same one-off
  script run on 0/15/15 (rank-1 stat product) vs 2/11/13 (the
  pick that won via stat product alone) across the same energy
  axis showed 0/15/15 *gains more wins from energy lead than
  2/11/13 does* (+92 / +231 wins at 1-fast / 2-fast lead vs
  +80 / +217 for 2/11/13). This contradicts the natural intuition
  that "energy lead favors high-atk IVs because the first charged
  move hits harder" — for high-power moves that opponents shield
  with high probability (Foul Play 65-power in this case), the
  post-shield chip war is what the fight comes down to, and bulk
  wins chip wars regardless of the swing-throw dynamics. When the
  feature lands, Shadow Sableye should be a calibration-test
  species: if the aggregator surfaces atk-favored IVs as bigger
  energy-lead gainers for Sableye-class species (high-power
  shield-bait charged moves + Foul-Play-like primaries), that's a
  feature bug, not the genuine matchup math. The shape to look
  for: bulk-leaning IVs should gain MORE matchups as energy lead
  rises, against opponents whose damage profile rewards
  longevity over burst.

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

* When I look at our interactive plots of Fairy Wind/Bulldoze,Gigaton
  Hammer Tinkaton, against the PvPoke default IVs, the 1v1 sheilds has
  a clear cluster at the top right, and I'd liek to know what's
  distinguishing about it. Especially since none of our pre-programmed
  thresholds show up in it. The 2v2 shows a similar cluster, though
  some of our pre-programmed thresholds do show up there. And the 2v2
  has some clear mostly horizontal banding structure. That would be
  interesting to dig into. The 0v0 has a big chunk in the bottom right
  that does include several of our GH Good mons ... but those have far
  worse battle scores here than lots of other mons. What are they
  missing? It's weird that a lot of that structure (almost all of it,
  actually) washes out when we look at the average battle score across
  all scenarios. Well. Across all even shield scenarios. We should
  check against all scenarios when we fix that bug.

* **Reinvestigate clustering methodology** — Current gap analysis (>3× median
  gap in sorted scores) is a rough heuristic. Consider better approaches:
  density-based methods, stat-space clustering instead of score-space, or
  matchup-aware clustering (group IVs that win/lose the same matchups).
  The Color By dropdown (HP/Def/Atk) already reveals banding structure
  visually; the automated analysis should match what users see.

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

* **"Show clusters" section is always visible** — it sits above the
  interactive scatter plot but should be gated behind the "Show
  experimental analysis (banding, clusters)" checkbox in the Deep Dive
  Analysis section. The checkbox already toggles `#dd-alpha` and
  `#dd-alpha-methods`; the cluster-display block needs to either move
  inside `#dd-alpha` or be hidden by the same JS handler. Discovered
  2026-04-08.

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

* **Re-render published split-moveset dives** *(follow-up to the
  2026-06-10 split-analysis-cache fix)* — The fixed bug was worse than
  the original "wrong subheader" report: from 2026-04-12 to 2026-06-10
  every NON-LANDING split file shipped **moveset 0's entire analysis
  sections** (Deep Dive Results, tier cards, anchor bullets, matchup
  boundaries), not just its label. The landing page (moveset 0) of
  each dive was always correct. Any split dive published in that
  window needs a re-render (`scripts/run_website_dives.py` →
  `publish_website.sh`) for its secondary moveset pages to show their
  own analysis. See DEVELOPER_NOTES "All-in-one vs split-moveset
  HTML" history note.

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

* **Card "High HP" pole surfaces a strictly-dominated spread (BUG, flagged
  2026-06-24).** On the UL Mimikyu card the High HP pole highlighted
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
