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

## Analysis goals

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


## HTML interactive output bugs

* **"Show clusters" section is always visible** — it sits above the
  interactive scatter plot but should be gated behind the "Show
  experimental analysis (banding, clusters)" checkbox in the Deep Dive
  Analysis section. The checkbox already toggles `#dd-alpha` and
  `#dd-alpha-methods`; the cluster-display block needs to either move
  inside `#dd-alpha` or be hidden by the same JS handler. Discovered
  2026-04-08.

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

### Bulkpoint anchor kind — design + implementation

Schema gap surfaced 2026-04-08 by mercuryish testimony on the Lurgan Ape:
the Lurgan spread is defined by `atk >= 127.2` AND `def >= 102.9`. The
atk side maps cleanly to our existing `damage_breakpoint` anchor (Level 2:
`above_atk = 127.2`). The def side is a *bulkpoint* — focal def crossing
a threshold to take less damage from some incoming move — and we have no
parallel anchor kind for it. mercuryish does not remember which specific
bulkpoint 102.9 keeps; recovering that knowledge requires the bulkpoint
infrastructure.

The library already has the math (`gopvpsim.breakpoints.bulkpoints`,
`def_for_damage`, `Bulkpoint` namedtuple) — only the anchor schema and
resolver wrapping is missing. The work is mostly mechanical, parallel to
the existing `damage_breakpoint` code path.

Required pieces:

* **Schema**: new `BulkpointAnchor` dataclass in
  `gopvpsim/thresholds.py` with the same three precision levels:
  - Level 1: `move` + `takes_at_most = N` (focal def must be high enough
    that the named opponent's named move deals ≤ N damage)
  - Level 2: `above_def = X` (smallest focal def above X at which any
    incoming move's damage steps down)
  - Level 3: bare anchor enumerates every bulkpoint against the opponent
    in the focal def range

* **Parser**: extend `_parse_anchor` for the new `kind = "bulkpoint"`
  discriminator. Mutual-exclusion rules mirror the BP side: can't combine
  `takes_at_most` and `above_def`, etc.

* **Resolver**: new branch in `gopvpsim/anchors.py` using
  `scan_bulkpoints()` from the breakpoints library. ResolvedAnchor needs
  a "what stat does this check" indicator (currently it's hardcoded to
  `threshold_atk` + `passes(focal_atk)`); generalize to a stat target
  (`threshold_value` + `target_stat: 'atk' | 'def'`). The bulkpoint
  resolver populates `target_stat = 'def'` and the categorize_slayers
  tag-iv logic checks `passes(focal_def)` for those.

* **categorize_slayers**: bulkpoint anchors route into **Bulk Slayer**
  (parallel to how breakpoint anchors route into Atk Slayer). Bulk Slayer
  membership becomes "structural HP+def above median **OR** clears at
  least one named bulkpoint." Hide-when-empty rule applies to the
  named-bulkpoint subset only; the structural pool is always shown.

* **HTML rendering**: filter panel + tag badges for bulkpoint anchors in
  the Bulk Slayer card. display_name derivation for the new anchor name
  pattern (likely `<opponent>_blkp_any` etc.).

* **Auto-fallback**: `build_auto_anchors` gains an auto-bulkpoint layer
  parallel to auto-Atk. One Level 3 bulkpoint anchor per opponent in the
  dive's opponent set; gated by `"bulkpoint" not in existing_kinds`.

* **Tests**: parsing variants, mutual exclusion errors, three precision
  levels, resolution against fixtures, fallback gating.

* **Docs**: update `docs/concepts.md` to introduce bulkpoint anchors as
  the def-side analog of damage_breakpoint anchors. Update
  `docs/threshold_schema.md` with the new TOML keys and a worked example.
  Likely also update the Annihilape TOML to add a Level 2 anchor for the
  102.9 def floor and a Level 3 mirror-bulkpoint discovery anchor.

Once shipped, run the discover-mode sweep against the Annihilape mirror
to identify which specific (move, tier) bulkpoint the 102.9 floor
preserves. That recovers the lost-to-history calibration knowledge from
the original Lurgan spread and lets us promote the discovered bulkpoint
to a Level 1 anchor with full provenance.

### Auto-anchor fallback — shipped 2026-04-08

When `--mirror-slayer` runs and the user provides no explicit anchors of a
given kind via `--thresholds`, `gopvpsim.anchors.build_auto_anchors`
synthesizes a fallback overlay so the Atk Slayer and CMP Slayer category
boxes still populate. Gating is per-kind: if you have explicit
`damage_breakpoint` anchors only, you get auto CMP filled in; if you have
explicit `cmp` only, you get auto BPs; if neither, both fire; if both,
neither auto fires.

Auto BP anchors create one Level 3 `damage_breakpoint` per opponent species
(named `auto_<species>_bp_any`), enumerating every breakpoint over **all**
focal moves (fast + charged). Earlier draft restricted to the focal fast
move only on the theory that fast-move BPs compound across many ticks while
charged-move +1s are one-off; that turned out to silently disable auto-Atk
for low-power-fast-move species like Annihilape (Low Kick power 5 produces
0–1 BPs against typical opponents). All-moves enumeration produces noisier
sub-anchor families but the filter panel + per-row tag abbreviation handle
the volume tolerably.

Auto CMP anchor uses **top quartile by atk in the survivor cohort**, not
"strictly beat the max." This is non-obvious and deserves a callout:

* **The focal IV is a member of its own cohort.** When the auto-CMP
  cohort = the converged survivor pool, "strictly beat max" is unreachable
  by definition — the highest-atk IV in the cohort can at best tie itself.
  My first cut used `strict=True` against an `IvListSpread` of the
  survivors and the CMP Slayer category came up empty for every fresh
  dive. Fix: compute the 75th-percentile effective atk over the cohort,
  wrap in a `StatCutoffSpread`, use a non-strict (`>=`) `CmpAnchor`. This
  always populates and matches the spirit of the old top-quartile-by-atk
  heuristic, now grounded in the actual converged survivors instead of
  the unfiltered 4096-IV space. Anchor name: `auto_cmp_vs_cohort`,
  display name: `cmp:cohort`.

* **The strict-max semantic is still correct for explicit external CMP
  anchors** like `cmp_vs_lurgan` in `thresholds/annihilape.toml`. There the
  cohort (Lurgan IVs) is external to the focal pool, so "strictly beat max"
  is a real, achievable threshold. Don't generalize the auto-CMP fix to
  the explicit case.

Auto markers: every auto-generated parent renders with a small italic
"(auto)" suffix in the filter panel UI so the user can see which anchors
came from runtime fallback vs the TOML. Display-name derivation strips the
`auto_` prefix first so badge text in the table cells stays clean
(`corviknight`, `cmp:cohort`, etc.).

Outstanding follow-ups for the auto-anchor system:

* **Add tests** for `build_auto_anchors()` and the gating logic. Currently
  only verified by smoke runs against the real Annihilape data.
* **Consider exposing a CLI flag** to opt out of auto fallback entirely
  (e.g. `--no-auto-anchors`) for users who only want their explicit set.
  Not built yet — wait until someone wants it.
* **Bulk Slayer anchor display**: when auto anchors fire, the Bulk Slayer
  card shows the anchor tags too (since `want_kinds = {bp, cmp}` for Bulk).
  This is fine but means a fresh dive's Bulk Slayer rows will be tagged
  with the auto anchors of any kind. Worth eyeballing whether that adds
  signal or noise.

### Slayer anchor system — shipped 2026-04-08

The TOML threshold schema (`docs/threshold_schema.md`), anchor resolver
(`gopvpsim/anchors.py`), and anchor-tagged `categorize_slayers` are all in
place. Atk Slayer and CMP Slayer now use named anchors instead of vacuous
median heuristics. Three follow-up observations from the smoke run:

* **Level 3 anchors are noisy on charged moves** — Close Combat and Rage
  Fist produce 10–15 BPs each across the survivor atk range because
  charged-move damage ladders are very fine-grained (every ~1 atk gives a
  +1 damage step). The tactically meaningful BPs are almost always on fast
  moves, since fast-move +1 damage compounds across many ticks per battle
  while a charged-move +1 is one-off. Two possible fixes:
  1. Add `moves = ["LOW_KICK"]` filters to L3 anchors in
     `thresholds/annihilape.toml` to scope discovery to fast moves only.
  2. Teach the resolver to filter out "micro-BPs" on high-power moves by
     default (e.g., suppress sub-anchors whose damage delta is < some
     fraction of the move's base damage).
  Decide which after looking at the rendered HTML.

* **`docs/validations/2026-04-07_annihilape_mirror_slayer_iteration.md`
  is now stale** — should be updated to reflect the mercuryish testimony
  (Discord, 2026-04-08): the community Lurgan Ape spread is a *historical
  anchor* calibrated to a Lickitung BP near atk 127.23, predating the
  Counter nerf, Rage Fist addition, and Low Kick buff. Current expert
  advice is to push higher attack than the Lurgan baseline for CMP wins
  and BP security against the mirror and Lickitung — which matches our
  converged result, not contradicts it. Reframe the validation doc from
  "we disagree with community" to "we converge to current expert
  practice; the published Lurgan spread is a frozen historical
  reference."

* **Re-run Annihilape mirror slayer with Lurgan as an explicit opponent
  variant** — Hypothesis 2 from the validation doc was that the community
  optimizes against a broader opponent set (PvPoke defaults + atk-weighted
  + Lurgan-style hand-builds). With the new TOML format, we can put the
  Lurgan spread in as a named opponent IV cohort and re-run mirror
  iteration to see whether our convergence shifts. If atk 129.44 still
  wins, hypothesis 1 (outdated community spread) is confirmed; if it
  shifts toward 127, hypothesis 2 is confirmed.

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

**Optimization priority order** (next session, highest impact first):

1. **Eliminate per-sim dict copies in BattlePokemon construction**
   — Each `simulate()` call currently does `dict(fm_template)` and
   `[dict(cm) for cm in cms_template]` for both focal and opponent.
   That's ~4 dict allocations per sim × ~40M sims per slayer round
   = 170M+ allocations. Many of these are likely redundant: if move
   templates are treated as immutable inside `simulate()` (verify by
   reading the simulate path), we can share them across sims.
   Estimated speedup: 2-3x. Smallest invasive change.

2. **Cache opponent BattlePokemon objects, reset mutable state between sims**
   — In a slayer round chunk, the same opponent IV is simulated against
   2430 focal profiles × 9 scenarios = 21,870 times. Currently we build
   a fresh BattlePokemon each time. Better: build once per (opp, scenario),
   then reset HP/energy/buffs between sims via a `reset()` method.
   Estimated speedup: 1.5-2x on top of #1.

3. **Add `__slots__` to `BattlePokemon` and `Move` classes**
   — Reduces attribute lookup cost and memory footprint. Easy change,
   small but real wins (5-15%).

4. **Numba JIT for the damage formula and inner sim loop**
   — Preferred over Cython because numba is quick to implement and
   leaves the code looking like Python in the easy cases. Annotate
   `_pvp_damage` and the tightest loops in `battle.py` with `@njit`.
   Type effectiveness lookups would need restructuring (numba doesn't
   like Python dicts well — use numpy arrays indexed by type enum).
   Estimated speedup: 5-10x for arithmetic-heavy paths. Try this AFTER
   #1 and #2 since profiling will show whether it's worth the cost.

5. **Profile-guided optimization** (do this BEFORE #4)
   — Run `py-spy` or `cProfile` on a real deep dive to find the actual
   hot spots. We're guessing about which functions matter most. Profile
   first, optimize second.

6. **Process pool reuse** — Currently we create a new `multiprocessing.Pool`
   for each iv_sweep call. Pool startup is ~1-2 seconds. Across a deep
   dive with 5 sweeps + 1 slayer iteration, that's ~10s of overhead.
   Minor but free.

**Why the speedup matters now**: A full Annihilape deep dive with
`--mirror-slayer --mirror-slayer-rounds 4 --mirror-slayer-metric even-strict`
currently takes ~90 minutes wall clock (the slayer round 1 is the
dominant cost at ~85 min). With the optimizations above stacked, we
should be able to bring that to under 10 minutes, making iterative
experimentation actually pleasant.

* **HTML file size** -- Are our deep dive/interactive HTML files
  getting too big?

* **Better slayer iteration progress reporting** — The current progress
  prints fire only when a `pool.imap_unordered` chunk completes. With
  10 chunks each taking ~85 minutes, the first progress line doesn't
  appear for 85 minutes. We need to either (a) chunk much more finely
  (e.g. 100-1000 chunks of 4-50 minutes each so prints fire every few
  minutes), or (b) have workers report progress via a shared counter
  (e.g. multiprocessing.Value) that the parent polls. Option (a) is
  simpler — just lower the chunk_size in iterative_slayer_discovery.
  Watch for diminishing returns due to pickle overhead per chunk.

* **Incremental slayer cache flush** — The slayer iteration cache
  (`SlayerCache` in `scripts/slayer_cache.py`) currently does one read
  at startup and one save at the end. If a long run crashes mid-iteration
  (e.g. 28 minutes into a 30-minute run), all the work done in that run
  is lost. Add periodic flush to disk after each slayer round so a crash
  loses at most one round's worth of sims. Tiny code change, big peace
  of mind.

## Low priority

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support.
