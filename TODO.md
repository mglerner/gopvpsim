## Battle simulator

* **File PvPoke bug reports** — Two bugs found in PvPoke's JS:
  1. BattleState `.hp`/`.oppHealth` naming inconsistency (dead-code dominance checks)
  2. bestChargedMove using `move.damage` (undefined at init) instead of `move.power`

## Policies to add

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

* **Baiting policy as a deep-dive sim axis** — Currently, baiting is a
  property baked into a single simulation run, not an output dimension
  swept across the IV grid. RyanSwag-style threshold callouts mix
  shield count with bait mode ("2-2 *no bait*, 2-1 *farm*") and even
  move-restriction ("0-0 *Ice Punch only*"). To reproduce that
  editorial nuance faithfully, the deep dive sims need a baiting-policy
  axis (and ideally a move-restriction axis) alongside the existing
  shield-scenario axis. Open design questions: which bait modes to
  enumerate (no-bait / always-bait / Selective / EV-based?), does the
  existing PvPoke "Selective" implementation suffice, where in the UI
  do we expose the new dropdown, how badly does the multiplied sim
  count hurt runtime. Cross-ref: the "RyanSwag-style matchup-flip
  annotations" Phase 1 work intentionally ships *without* this axis;
  this TODO is the natural follow-up that lets the bullet format
  upgrade from "(2-2, 2-1, 0-0)" to "(2-2 no bait, 2-1 farm, 0-0 Ice
  Punch only)". Discovered 2026-04-09 while scoping Phase 1.

## Features to add

* **Form Change** — Morpeko. Aegislash. Mimikyu. These are all
  implemented in pvpoke, so we can check against their results. As
  soon as we get Mimikyu's form change added, we should do a Mimikyu
  deep dive. The form change deep dives should include some text about
  how their individual form changes work.

## Tests to add

* **Form Change** — Morpeko. Aegislash. Eventually Mimikyu. Low
  priority. Do this when we add the form change features. Do the form
  changes affect the shielding strategy and/or baiting strategy of the
  opponent? Probably. Make sure we test enough explicit battle
  timelines from pvpoke to confirm.

* **Auto-anchor fallback gating tests** — `build_auto_anchors()` and
  the per-kind gating logic are currently only verified by smoke runs
  against real Annihilape data. Add explicit unit tests for the
  gating cases (no kinds existing → all three fire; one kind existing
  → other two fire; all three existing → empty registry).
  *Note: bulkpoint gating tests landed in 2026-04-08; this entry now
  covers the broader BP/CMP gating coverage gap.*

## Analysis goals

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

* **Send mercuryish a Discord message about the Lurgan 102.9 def floor**
  — Our 2026-04-08 bulkpoint Level 3 enumeration against the Annihilape
  mirror found that the historical Lurgan Ape `def ≥ 102.9` floor is
  *unrecoverable* from current sims: the next bulkpoint above 102.9
  (`shadow_ball ≤149` at def 103.34) is unreachable for today's
  converged cohort (max def ~101.30). The 102.9 floor predates Rage Fist,
  so the threat-move set has shifted. Ask mercuryish whether the
  historical calibration was against a Counter or Close Combat tier
  transition, or against something more niche (Shadow Ball / Night Slash).
  This is the missing context that would let us promote a specific
  bulkpoint to a Level 1 anchor with full provenance.

* **Rename `mercuryish` → `acidicArisen` throughout the codebase** —
  acidicArisen is their preferred username on HSH's Discord; we've been
  using the older `mercuryish` handle in code, comments, docs, validation
  writeups, and TOML provenance fields. Sweep the repo (code, docs/,
  thresholds/, DEVELOPER_NOTES.md, TODO.md, validation writeups) and
  update references. Discovered 2026-04-09.

## Slayer card UX (post-bulkpoint shipped 2026-04-08)

* **Slayer-card signal-loss audit + design discussion** *(needs design
  before implementing; broader than originally scoped)* — With Level 3
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

* **"Show clusters" section is always visible** — it sits above the
  interactive scatter plot but should be gated behind the "Show
  experimental analysis (banding, clusters)" checkbox in the Deep Dive
  Analysis section. The checkbox already toggles `#dd-alpha` and
  `#dd-alpha-methods`; the cluster-display block needs to either move
  inside `#dd-alpha` or be hidden by the same JS handler. Discovered
  2026-04-08.

## Slayer iteration cleanup

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
  to reflect mercuryish testimony (Discord, 2026-04-08) and the
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

* **Non-interactive `generate_html` is now strictly worse than interactive**
  — `generate_analysis_sections` (line 2046, which produces the slayer
  iteration display, breakpoint narration, banding analysis, clusters,
  etc.) is *only* called from `generate_interactive_html` (line 2866),
  not from `generate_html` (line 1242). Without `--interactive`, the HTML
  shows just the top-N table, the plot, and a brief methodology footer —
  none of the slayer analysis. Fix: either deprecate the non-interactive
  path entirely, or refactor so both paths render the analysis sections.
  Discovered 2026-04-08 during anchor-system smoke testing — it's easy
  to mistakenly run a smoke test without `--interactive` and conclude
  nothing rendered.

## Deep-dive narrative

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

* **Bait-axis matchup categories** — Round 1 of structured IV
  categories shipped `kind='matchup'` cards keyed by
  `(opponent, scenario)` with the `bait` field on `matchup_conditions`
  reserved as `None`. Once the "Baiting policy as a deep-dive sim
  axis" TODO above lands, the matchup-category builder needs to also
  iterate the bait dimension so we get cards like "Beats rank-1
  Lickitung in the 2v2 no-bait." The data model already handles this
  cleanly — only the builder loop and the `_matchup_subtitle()`
  renderer need updating.

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

## Performance

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

* **HTML file size** -- Are our deep dive/interactive HTML files
  getting too big? Latest fresh Annihilape HTML is ~25 MB; explicit is
  ~23 MB. Mostly the embedded data + the wall of badge spans.

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

## Refactoring

* **Split `scripts/deep_dive.py`** *(deferred from 2026-04-09; not
  blocking, but file is now ~5100 lines)* — After the structured IV
  categories shipped, the file is approaching the size where edits
  start fighting the line-cap. Concrete extraction targets, in rough
  order of independence:
  1. **`scripts/deep_dive_lib/categories.py`** — `IVCategory` dataclass,
     `build_iv_categories()`, `_stat_cutoffs_from_anchors()`,
     `_format_stat_cutoffs()`, `_composite_tradeoff_prose()`,
     `_matchup_subtitle()`. Pure-Python, already isolated, already has
     unit tests in `tests/test_iv_categories.py`. Easiest move.
  2. **`scripts/deep_dive_lib/anchor_flips.py`** — `_aggregate_flips_by_anchor()`,
     `_render_anchor_flip_bullets()`. Pure-Python, already isolated,
     already has tests in `tests/test_flip_aggregator.py`.
  3. **`scripts/deep_dive_lib/slayer.py`** — `iterative_slayer_discovery()`,
     `categorize_slayers()`, `_slayer_iter_worker()`, related helpers.
     The multiprocessing entry points complicate this — workers are
     resolved by qualified name, so the move requires careful import
     plumbing.
  4. **`scripts/deep_dive_lib/render.py`** — `generate_analysis_sections()`,
     the per-section helpers (`_render_notable_ivs_section`,
     `_iv_label`, `_tier_badge_html`, `_threshold_desc`,
     `_hover_text`, etc.), the CSS string. This is the actual monster
     (~1500 lines and growing). Needs a small "renderer context"
     dataclass first to avoid passing a 15-arg tuple around.
  5. **`scripts/deep_dive_lib/sweep.py`** — `iv_sweep()`, the worker
     init/run pair, `screen_movesets()`, `compute_iv_metadata()`,
     `group_ivs_by_stat_profile()`. Numba-touching code; same
     multiprocessing import-plumbing concern as slayer.
  Remaining in `scripts/deep_dive.py` after all five steps: argument
  parsing, the top-level orchestration in `main()`, and the legacy
  non-interactive `generate_html()` (already on the chopping block —
  see "Non-interactive `generate_html` is now strictly worse" above).
  Test split: each module gets its own `tests/test_<module>.py`; the
  existing tests already prove the importlib pattern works for
  modules that can't import from `gopvpsim` directly.
  **Recommendation**: do this in a dedicated session, not interleaved
  with feature work — refactor diffs and feature diffs shouldn't ride
  the same commit. Mechanical (file moves + import fixes) so it
  shouldn't take long once started; the risk is multiprocessing
  worker resolution and CSS-string fragment positioning.

## Low priority

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support.

---

# Shipped

Items here have been completed and are kept for context. Move them
out (delete) when they're no longer useful as historical reference —
generally a few weeks after they've stabilized in production.

## 2026-04-09 — Structured IV categories (round 1)

Unified `IVCategory` framework abstracting over slayer categories,
threshold tiers, and their intersections. New "Notable IVs" HTML
section surfaces composite (slayer ∩ tier) cards and matchup
(opponent, scenario) cards with auto-generated tradeoff prose.
Annihilape `13/0/11` lands as the canonical example: "The sole Atk
Slayer that also clears the Top 5% threshold (hp≥139). Trades mirror
dominance (45/132 wins, vs 132/132 for the top Atk Slayer survivors)
for the Top 5% cutoff." Section is gated behind a "show only notable"
header checkbox (≤ 5% of cohort or ≤ 5 members, default on). Round 1
ships zero TOML changes — composite + matchup categories are
auto-derived from existing infrastructure. Bait dimension on
`matchup_conditions` is reserved (`None`) until the bait-axis sweep
TODO lands. Commits: `f3aa4ad` (dataclass + builder), `8ff4469`
(matchup branch), `79e2e87` (renderer), `b344356` (wire-in). Cross-ref:
"Hand-named composite categories via TOML" and "Bait-axis matchup
categories" in Deep-dive narrative for round 2 followups.

## 2026-04-08 / 2026-04-09 — Bulkpoint anchor system

Def-side mirror of `damage_breakpoint` anchors. Three precision levels
(L1 explicit, L2 reference-anchored via `above_def`, L3 discover-and-tag),
parser, resolver, auto-fallback, tests, docs, Annihilape TOML entries.
Bulk Slayer category gained dual membership (structural HP+def OR
clears at least one named bulkpoint). `ResolvedAnchor` generalized to
`target_stat` with `threshold_value` so the same passes() machinery
handles both atk and def side. Commits: `13665dc` (main feature +
brkp/blkp rename + tag UX + CLI args embed — should have been split,
see commit message), `8f9369d` (clarify ×N count in hover tooltip),
`7ed5765` + `967bb09` (Compact/Expand toggle for tag cells).

**Headline finding** from running the new system on Annihilape
explicit: the historical Lurgan Ape `def ≥ 102.9` floor is *not*
recoverable as a single (move, tier) bulkpoint. The next bulkpoint
above 102.9 is `shadow_ball ≤149` at def 103.34, but 0/66 of today's
converged cohort can reach it (max cohort def ~101.30). The 102.9
floor predates Rage Fist, so the threat-move set has shifted; today's
optimization trades def for atk and lands well below the historical
baseline. Don't promote anything to Level 1 from this enumeration —
follow up via Discord with mercuryish to recover historical context
(see "Send mercuryish a Discord message" in Analysis goals).

## 2026-04-08 — bp → brkp short-name rename

Renamed all anchor name slugs from `_bp_` to `_brkp_` so the
breakpoint short form is unambiguous against the new bulkpoint
`_blkp_` short form. The Python kind discriminator stays
`damage_breakpoint` (full word); only the slug-style short forms
changed. Touched anchors.py, build_auto_anchors, annihilape.toml
anchor table keys, tests, and docs. Part of commit `13665dc`.

## 2026-04-08 — Ultra-short anchor abbreviations + Compact tags toggle

Tag cells in slayer cards previously truncated badges horizontally
with `text-overflow: ellipsis` at 280px max-width, hiding most of
the badges past the first 2-3. Replaced with: (a) `derive_short_name`
function producing 3-6 char badge labels (cre, lic, mirb, lic↑lur,
c:lur, quasb...) with the long form preserved in the badge hover
tooltip, (b) cell wrapping enabled, max-width bumped to 480px,
(c) Compact/Expand toggle button at the top of the slayer card grid
that caps cells at ~2 lines via an inner `<div>` wrapper (the wrapper
is needed because `<td>` ignores `max-height` in CSS — fixed in
`967bb09` after the first attempt at the toggle didn't actually work).
Part of commit `13665dc` + the three follow-ups.

## 2026-04-08 — CLI args embedded in HTML output for forensics

`format_cli_args(args, parser)` builds the *fully-resolved* equivalent
invocation: every flag emitted with its actual value, including flags
whose value happens to equal the current parser default. Embedded in
HTML two places: a grep-able `<!-- CLI: ... -->` comment near the top
and a collapsed `<details>` footer at the bottom of `<body>`. Also
printed to console at startup as `CLI: ...`. Why fully-resolved
instead of literal user input: defaults can change between runs, so
a string that omits "default" flags becomes ambiguous when read later.
This is the forensic gold standard. Part of commit `13665dc`.

## 2026-04-08 — Slayer anchor system

The TOML threshold schema (`docs/threshold_schema.md`), anchor
resolver (`gopvpsim/anchors.py`), and anchor-tagged
`categorize_slayers` are all in place. Atk Slayer and CMP Slayer use
named anchors instead of vacuous median heuristics. Three precision
levels for damage_breakpoint anchors (L1 explicit, L2
reference-anchored, L3 discover-and-tag). Auto-fallback layer
synthesizes anchors at runtime when the user doesn't provide them
via TOML, gated per kind so explicit user input always wins. Commits
`beace47` (main) and `10a693c` (mercuryish testimony incorporated
into thresholds/annihilape.toml + anchors tests).

## 2026-04-07 — Battle simulator perf optimization (round 1 + round 2 + chunking)

Real-world impact: ~9hr → ~6 min on a full Annihilape mirror slayer
deep dive workload. Stack of optimizations:
* Damage cache + DP hoisting — +51% throughput (commit `3596fb4`)
* Numba JIT on the near-KO DP loop — +40% throughput (commit `a57c39f`)
* Stat profile dedup in `iv_sweep` — ~1.7x faster Phase 2 (commit `6ccb124`)
* Slayer iteration: dedup focal & opponent IVs by effective stats
  (commit `579aef7`)
* Slayer iteration: keep all IVs tied at top win count (commit `eb145a2`)
* Chunk count bumped from `n_workers` to ~100 for finer progress
  reporting (commit `8498ec4`)

Round 3 (numba JIT for the entire inner sim loop) was deprioritized
after round 1+2 made the workload tolerable; fastmath was confirmed
a dead-end during the round 1 work.

## 2026-04-07 — Iterative slayer discovery (Nash-style mirror match)

`scripts/deep_dive.py --mirror-slayer` runs Round 0 (focal IVs vs
PvPoke default opponent) then iterates Round k (focal IVs vs round
k-1's top survivors), stopping on convergence or `--mirror-slayer-rounds`.
Survivors are classified into RyanSwag-style Atk Slayer / Bulk Slayer
/ CMP Slayer categories. Disk cache at
`~/.cache/gopvpsim/slayer/<key>.pkl` keyed on species/league/shadow/
moves/scenarios so re-runs are near-instant. Commits `43b8784` (main),
`75fa8ce` (HTML rendering), `9cabba7` (cache key fix), `3b9d5fb`
(metric/rounds/pool/show CLI flags), `0dfcc98` (validation doc).

## 2026-04-06 — IV deep dive script + interactive HTML

`scripts/deep_dive.py` simulates all 4096 IV spreads of a focal
species against meta opponents across moveset combinations, with
threshold-tier coloring, custom group support, and an interactive
HTML mode (`--interactive`) with moveset/scenario/opp-IV switching
dropdowns. Commits `f0253d5` (script), `a4d18e5` (interactive mode),
`30452c6` (PvPoke default IVs for opponents), `4c7bcf9` (legend
isolation, matchup hover), `6924b1a` (`--standalone` inline Plotly).
Doc reorganization in `0ce1229` (CLAUDE.md, TODO.md, DEVELOPER_NOTES.md).

## 2026-04-04 to 2026-04-06 — Battle simulator correctness

Several rounds of bug fixing brought the battle simulator into
agreement with PvPoke's reference output:
* Three turn-model bugs: 1-turn FM timing, faintSource, FM fire order
  (commit `e036670`)
* Buff/debuff implementation (commit `6145aaa`)
* Buff meter, pvpoke_simulate_shield, trace flags (commit `ead46c1`)
* ActionLogic.js post-DP bandaids, sort cms by energy, raw_dpe
  (commit `f4d0eb3`)
* DP queue insertion strategies, intended_pruning flag (commit `44f3215`)
* Shadow Pokemon support (commit `8c5fb65`)
* `wouldShield` buff reset ordering, CMP cancellation (commit `5b07790`)
* All 9 Medicham vs Azumarill scenarios match PvPoke (commit `008d8e7`)

## 2026-04-01 — pvpoke_dp charged-move policy

Implemented PvPoke's `ActionLogic.js` DP-based charged-move decision
policy in Python (`gopvpsim.battle.pvpoke_dp`). Commit `62b9cfb`.

---

# Resolved (deeper history)

* **Slayer Ape / Lurgan Ape IV analysis** — Resolved 2026-04-08 by
  mercuryish Discord testimony. The community Lurgan Ape spread is a
  *historical floor* (`atk ≥ 127.2`, `def ≥ 102.9`) calibrated to a
  Lickitung breakpoint near atk 127.23, predating the Counter nerf,
  Rage Fist addition, and Low Kick buff. Our slayer iteration's
  convergence to atk 129.44 matches *current* expert advice (push
  higher than the Lurgan baseline for CMP wins and BP security against
  the mirror and Lickitung). The "we disagree with the community"
  framing in earlier analysis was wrong — we converge to current
  expert practice; Lurgan is a frozen historical reference.
