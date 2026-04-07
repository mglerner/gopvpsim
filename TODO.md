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


* **Slayer ideas** -- for the slayer IVs, it may not be possible to
  represent them as IV thresholds. They really may just be a
  collection of specific IVs. But we should at least categorize the IV
  spreads that they're using. And if it *is* possible to describe them
  as IV thresholds, we should give that description in addition to the table.

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
