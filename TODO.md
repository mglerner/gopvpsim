## Deferred cleanup: backwards-compatibility removal pass

Once we've verified all the oracle/sim tests (including direct human
review by Michael), run a dedicated session to **remove
backwards-compatibility shims, historical artifacts, and
"just-in-case" abstractions** that accumulated during feature work.
The goal is to simplify the code now that we've confirmed the new
behavior is right.

Concrete candidates to audit (grows as we spot them):

- **`gopvpsim.evolution_lines.get_final_form()`** — kept alongside the
  new `get_final_forms()` for callers that "know they're dealing with
  unambiguous chains." Delete once nothing in the codebase calls it.
  Currently used only by tests.
- **`pvpoke_dp(intended_pruning=...)`** — the flag toggles between
  "PvPoke's actual JS behavior (dead-code dominance checks)" and
  "apparently intended behavior." If we're confident one branch is
  right, collapse to that and drop the flag.
- **Anything flagged with "historical" / "legacy" / "backcompat"** in
  code comments — grep for these when the session starts.
- **Gobattlekit threshold schema compatibility** in
  `gopvpsim.user_collection.check_thresholds` — once gobattlekit has
  actually migrated to use the shared module and we've confirmed it
  works, we may want to simplify the dict schema or unify with
  pogo-simulator's TOML anchor schema. But not before gobattlekit's
  migration lands.

Do NOT start this cleanup pass until Michael has explicitly signed
off that the current oracle tests pass human verification. This rule
exists because "simplification" mid-feature-work tends to silently
break invariants that weren't yet nailed down by tests.

## Battle simulator

* **File PvPoke bug reports** — Seven bugs found in PvPoke's JS:
  1. BattleState `.hp`/`.oppHealth` naming inconsistency (dead-code dominance checks)
  2. bestChargedMove using `move.damage` (undefined at init) instead of `move.power`
  3. bestChargedMove not recomputed on opponent form change (stale DPE cache)
  4. Aegislash selects Gyro Ball over Shadow Ball (same cost, strictly less damage)
  5. Mimikyu delays Shadow Sneak by 1 SC (suboptimal timing, costs 13 score points)
  6. initializeMove's buff-adjusted `move.dpe` is overwritten by
     selectBestChargedMove before use. Pokemon.js:849-864 computes a
     buff multiplier that inflates DPE for self-atk-buff and opp-def-
     debuff moves, but Pokemon.js:791-796 (inside the same `resetMoves`
     call) immediately resets `move.dpe = move.damage / move.energy`
     on every activeChargedMove. So the buff-adjusted DPE only affects
     the priority-shuffle ordering (lines 711-787); it never reaches
     the bait-wait ratio check (ActionLogic.js:843) or any later
     consumer, despite looking like it should. Likely intent was for
     the buff adjustment to persist through the ratio check. Discovered
     2026-04-14 while resolving our Divergence 2.
  7. needsBoost / non-guaranteed-buff plan selection is dead code.
     ActionLogic.js:539 unconditionally zeros `changeTTKChance`, so
     `stateList` never accumulates chance-<1 plans; and `needsBoost`
     (line 793) is never assigned `true`, so the line 868 plan-reorder
     gate is inert. Empirically 0 "needs the BOOST" log hits across
     the 4 GL meta species whose default moveset has a chance-<1
     charged move (Tinkaton, Corviknight, Clefable, Drapion).
     Discovered 2026-04-15; writeup in DEVELOPER_NOTES.md §7.

* **Resolve known PvPoke divergences** — ~~Three~~ One remaining intentional
  implementation difference tracked in DEVELOPER_NOTES.md "Known divergences."
  1. ~~selfBuffing flag scope~~ RESOLVED 2026-04-14: broadened to match PvPoke
  2. ~~Bait-wait DPE ratio~~ RESOLVED 2026-04-14: was misdiagnosed; PvPoke
     also uses raw DPE in the 1.5 ratio check (selectBestChargedMove
     overwrites buff-adjusted values). Real gap was the priority-shuffle
     (Pokemon.js:711-787), now ported.
  3. bestChargedMove recomputed per-turn vs PvPoke's init-time cache --
     keeping ours (intentional, more correct; see DEVELOPER_NOTES.md)

* **Audit existing oracle tests against the PvPoke harness** — Now
  that `scripts/pvpoke_trace.js` + `scripts/verify_pvpoke_harness.py`
  exist and 27/27 pass, extend the verify script to cover ALL
  PvPoke-oracle test cases currently in `tests/test_battle.py` (and
  anywhere else we've hand-typed a PvPoke score or move sequence into
  a test/docstring/comment). Typos and user-entry errors may have
  silently crept in over time; the harness is cheap to run and gives
  a definitive check against PvPoke. Scope: enumerate all existing
  fixtures, feed each to the harness, flag any where the harness
  disagrees with the recorded PvPoke numbers. Fix typos; separately
  flag genuine PvPoke divergences for follow-up.

* **Speed test** -- compare our speed vs the PvPoke JS code, look for
  ways we can speed ours up.

* ~~**Forretress/Azu 0-shield score divergence**~~ — **RESOLVED 2026-04-15.**
  Not a DP plan-selection bug after all. Root cause: our OMT
  (`_optimize_move_timing`) had a `defender.hp > _fast_dmg` gate that
  preferred fast-KO over charged-KO "because scores identical." That
  assumption held only for instant-fast; under mid-cooldown timing a
  delayed fast cost 3 turns of Azu damage on Forr (T37 fires charged
  immediately in PvPoke; ours waits for fast that lands at T40). Gate
  removed. GL grid max |Δ| 15→0 across all 405 pairs.
  Investigation landmark: decideLog entry/return tracing added to
  scripts/pvpoke_trace.js (PvPoke's decideAction-level entry/exit log)
  was the tool that localized this — earlier dpPlan-level traces missed
  it because the divergence was upstream of the DP. Full writeup in
  DEVELOPER_NOTES.md "Resolved divergences" 2026-04-15 OMT entry.

* ~~**Near-KO DP non-debuf swap (Lapras [1,2] flip)**~~ — **Closed
  2026-04-15 followup, not fixing.** Original hypothesis ("near-KO
  branch needs a symmetric non-debuf swap") was wrong. The actual
  mechanism is PvPoke's post-DP bandaid[885] (our port: bandaid[866]
  at battle.py:1541), which relies on a `.damage` side effect from
  OMT line 320. Faithfully mirroring PvPoke fires the swap in ALL 6
  MG cluster cases — the `damage/opp.hp < 0.8` test doesn't separate
  Lapras (0.70) from Jellicent (0.62) / Corv (~0.6). Net: matching
  PvPoke inverts the 6:1 ratio (resolves Lapras, regresses 6 cluster
  clear-wins). Per CLAUDE.md divergence policy, ours is defensibly
  better overall. Keeping the `_cached_damage` subgate at
  battle.py:652 as the intentional deviation; xfails stay. Full
  writeup in DEVELOPER_NOTES.md "Near-KO DP plan choice".

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

* ~~**Baiting policy as a deep-dive sim axis**~~ — **SHIPPED.** `--bait
  {on,off,both}` sweeps the selected modes; with `--bait both` the HTML
  renders a Bait dropdown (`deep_dive.py:2678-2683`) alongside Shields
  and Opponent-IVs. Scatter, threshold/flip aggregator, anchor-clear
  overlay, and bait-differential matchup cards
  (`deep_dive_rendering.py:2840-2910`) all consume `state.oppIvMode`
  with the `:nobait` suffix so they react to the dropdown. Confirmed
  2026-04-16 while scoping S3 histogram. Remaining open items are
  policy-enumeration (Selective, EV-based) under "Policies to add"
  above — distinct from the axis plumbing. S16/S17 in the post-S5 arc
  still tracks post-ship design polish (named bait modes in bullets),
  but nothing is blocking.

## Features to add

* **Form Change** — ✅ **Done 2026-04-14.** Morpeko (toggle Aura Wheel
  Electric/Dark), Aegislash (Shield<->Blade stat/move/level swap),
  Mimikyu (disguise absorbs first unshielded hit, -1 def stage).
  Data-driven via gamemaster formChange field. Oracle tests: Morpeko
  6/9, Aegislash 1/9, Mimikyu 6/9 match PvPoke exactly; remaining
  mismatches are the GB/SB cascade (PvPoke bug #3) and Mimikyu SS
  timing (PvPoke bug #5), pinned as xfails. Next: Mimikyu deep dive
  with form change narrative.

* ~~**DP cycle-timing move selection**~~ — **CLOSED 2026-04-15,
  not an actual issue.** Original claim: our DP picks PR over IB in
  Azu vs Aegislash 0v0 where IB yields more total damage via an extra
  throw. Verified independently in two sessions (2026-04-15): current
  sim throws Ice Beam twice in Azu vs Aegislash 0v0 and lands on the
  same score PvPoke does (773). The concrete example was resolved
  incidentally by one or more of: the bestChargedMove DPE threshold
  port (fca1b7c), the activeChargedMoves priority-shuffle port
  (68a306d), and the raw-DPE / atk_stage fixes around 2026-04-15. The
  full oracle audit (115/115 matches PvPoke harness) shows no
  remaining cycle-timing symptoms in any form-change or basic 0v0
  fixture. Do NOT re-queue without a new concrete failing case.

## Tests to add

* **No-bait oracle tests from iv-tech deep dives** — `pvpoke_dp` now
  accepts `bait_shields=False`. Sanity tests for the farm-down gate
  landed in `test_battle.py` (see `test_pvpoke_dp_no_bait_*`), but we
  should add real-world oracle cases from the HSH #iv-tech deep dives
  in `docs/*.md`. Candidates (each asserts that `bait_shields=False`
  still wins the cited matchup):

  1. **Tinkaton vs Medicham 1-1** — ✅ **Done 2026-04-12**
     `docs/tinkaton_deep_dive_reference.md:25`. "141.66 defense with
     138 hp lets you … win the 1s *without baiting*." Covered by
     `test_tinkaton_wins_1v1_vs_medicham_no_bait` parametrized over
     both rank #1 (5/15/15 NBB) and default (7/15/14) Medicham and
     both bait modes. Tinkaton 1/14/14 (def=141.66 exactly, hp=143)
     wins all 4 cases at score 520. Note: `bait_shields` has no
     observable effect here (near-KO DP phase bypasses farm-down bait
     branches); the test confirms bait-off doesn't break the matchup.
     **Open followup**: our sim has a more forgiving win threshold
     than the reference — many Tinkaton spreads below def=141.66 also
     win the 1v1 (e.g. 0/10/15 at def=138.96 wins). The reference's
     141.66 threshold may be overly conservative, or our sim is
     missing a nuance. Worth round-tripping at pvpoke.com/battle.

  2. **Tinkaton vs rank #1 Azumarill 1-2** — ✅ **Done 2026-04-12**
     `docs/tinkaton_deep_dive_reference.md:27`. "143.03 defense gives
     a bulkpoint vs rank #1 azu which flips the 1-2s (*no baiting
     required*)." Covered by
     `test_tinkaton_def_143_flips_1v2_vs_rank1_azumarill` which
     asserts the directional def-bulkpoint flip: Tink 1/14/14
     (def=141.66) LOSES 1v2 at score 397; Tink 0/14/9 (def=143.04)
     WINS 1v2 at score 535. Crossing def=143.03 flips the matchup as
     predicted. The "no baiting required" qualifier is verified by
     parametrizing over both bait modes (bait_shields irrelevant in
     this matchup, same scores either way).

  3. **Tinkaton vs rank #1 shadow Altaria 0-1** —
     `docs/tinkaton_deep_dive_reference.md:31`. "143.04 defense with
     141 hp … win the 0-1s *without baiting*." Note: reference also
     flags inconsistency due to shadow IV variance.

  4. **Spidops vs rank #1 Altaria 1s** —
     `docs/spidops_deep_dive_reference.md:35`. "140.67 defense with
     132+ hp flips the 1s vs the rank #1 altaria *without baits* by
     reducing sky attack damage."

  5. **Corviknight vs default-IV Shadow Sableye** — ✅ **Done 2026-04-12**
     `docs/corviknight_deep_dive_reference.md:58`. Both halves of the
     reference claim verified by:
     - `test_corviknight_max_def_wins_1v1_vs_default_shadow_sableye`
       (parametrized over bait modes — 1v1 "flips without baiting")
     - `test_corviknight_2v2_vs_default_shadow_sableye_flips_with_bait`
       (2v2 "flips with bait twice" — directional A/B: bait-on wins
       531, bait-off loses 288). This is the strongest oracle we have
       for the `bait_shields` gate: if farm-down baiting regresses, the
       2v2 test flips and catches it.

  Each test should parametrize over `bait_shields=[True, False]`
  when the reference makes a directional claim (cases 1, 5
  especially). For cases where the reference only asserts the
  no-bait result, test only `bait_shields=False`.

  Priority: low-to-medium. These are integration oracles, not
  correctness-blocking — the simple unit tests in `test_battle.py`
  already prove the gate works. Pick these up in a session where you
  can verify exact movesets/IVs at pvpoke.com/battle.

* **Form Change** — ✅ **Done 2026-04-14.** Oracle tests shipped:
  Morpeko 9/9, Aegislash 5/9 + 4 xfails (PvPoke bug #3 GB/SB cascade),
  Mimikyu 9/9 match PvPoke harness.
  Form changes DO affect opponent shielding (Aegislash Shield form
  suppresses shields if damage < half HP) and baiting (Mimikyu
  opponents break disguise ASAP with cheapest charged move).

* **Auto-anchor fallback gating tests** — `build_auto_anchors()` and
  the per-kind gating logic are currently only verified by smoke runs
  against real Annihilape data. Add explicit unit tests for the
  gating cases (no kinds existing → all three fire; one kind existing
  → other two fire; all three existing → empty registry).
  *Note: bulkpoint gating tests landed in 2026-04-08; this entry now
  covers the broader BP/CMP gating coverage gap.*

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

## CD article generator (new, 2026-04-16)

* **Python article generator** *(design + implementation, replaces the
  Claude-authored-prose path that was scrapped mid-S5)* — the article
  page must be a Python-generated, simulation-data-derived artifact,
  not prose written by Claude mimicking JRE's GamePress/pokemongohub
  writing style. JRE writes for money; shipping Claude prose in his
  voice is not acceptable. Target state:

  **Default path** — `scripts/generate_article.py <species> <league> <cd_move>`
  reads the threshold TOML, the deep dive data (or re-runs it), and
  the gamemaster, then emits mechanical article content:
  - **Move comparison table**: fast moves side-by-side (power, energy,
    turns, DPT, EPT, type, STAB flag)
  - **Meta coverage summary**: avg battle rating per moveset, wins vs
    rank-1 meta opponents in each shield scenario (numbers, not prose)
  - **Matchup delta table**: per-opponent score diff between the new
    CD move and the old default (Mud Slap vs Tackle), highlighting
    flips
  - **IV recommendations**: rendered directly from `thresholds/<sp>.toml`
    (tiers, named anchors, with the existing threshold-tier renderer)
  - **Links**: each moveset mention links to either (a) our deep-dive
    split-moveset page, (b) PvPoke's multi-battle page (URL format
    `pvpoke.com/battle/multi/<cp>/all/<mon>/<shields>/<fmIdx>-<cm1Idx>-<cm2Idx>/<ivLevel>`),
    or both
  - **Verdict**: template-selected from avg-score delta sign and
    magnitude ("clear upgrade" if Δ > 10%, "sidegrade" if |Δ| < 5%, etc.)
  No hand-authored prose; reads as a spec sheet + data tables.

  **Optional augmentation path** — the existing `articles/*.toml`
  `[[sections]]` prose slots become an opt-in override. Renderer
  precedence: if `authorship="expert"` or `"both"` and a section has
  body text, use it; if `authorship="auto"`, use the Python-generated
  default for that section. Lets a human (or Claude-in-a-session,
  with genuine review) write real analysis without blocking on it.

  **Related work that should land before / alongside this:**
  - **Battle-rating histogram** as a new deep-dive section: JRE's
    articles link to PvPoke's multi-battle histogram (wins/losses
    distribution across the meta) per moveset. Our dive already has
    the underlying `score1` data at 0-1000 scale; binning it into a
    Plotly histogram per moveset is the minimum viable feature. Lets
    the article link to a local histogram instead of PvPoke, which
    matters because our sim has real divergences from PvPoke and we
    want the article's numbers to match what the linked page shows.
  - **Slug convention fix**: the `articles/*.toml` filename uses
    underscores, but `thresholds/*.toml`'s `[Species.article] slug`
    field and the `userdata/website/<dive>/` directories use hyphens.
    Decide whether to rename article TOMLs to use hyphens (matches
    convention + makes `render_article.py`'s stem-derived slug work
    without threshold-slug drift) or change the threshold slug to
    underscores (makes the existing filename work). The deep-dive
    "Related Article" link currently 404s because of this mismatch.
  - **Female Oinkologne dive**: the May 2026 CD affects both Male and
    Female Oinkologne, which have meaningfully different base stats
    (186/153/242 vs 169/162/251) and the generator needs to handle
    both. See memory `project_female_oinkologne.md`.

  **Paced as a separate arc**, not squeezed into the remaining
  Lechonk CD prep sessions. Realistic structure: (1) design doc +
  histogram feature, (2) generator skeleton + move-table + verdict,
  (3) matchup-delta table + PvPoke-link helper, (4) Female dive
  integration + site-index update. Oinkologne CD (May 9) is the
  natural ship target but not a hard deadline if the work needs more
  time.

  **Watch item for S8 (envelope-position annotation surfacing):** when
  the per-category envelope-position metric (S4) gets surfaced as
  in-card annotations in the IV recommendations section, audit whether
  `render_notable_ivs_section`'s existing UX caps
  (`notable_max_count=5`, `max_members_shown=5`) still feel right with
  an extra shape-tag line per card. Not an action item yet — S4's
  metric doesn't add new category *types*, only a classification, so
  the cap isn't currently under pressure. Flagging so the audit
  doesn't get discovered at render-time in S8.

## Deep-dive narrative

* **SwagTips narrative follow-ups (Goodra + Aegislash dives)** — the
  renderer module `scripts/deep_dive_narrative.py` (1016 lines, purple
  "IV Flavor Guide" zone between Expert Analysis gold and Simulation
  Deep Dive blue) is in place. Remaining in the 3-session SwagTips arc
  per `~/.claude/plans/flickering-swinging-micali.md`: (2) ~~Goodra
  test-drive dive~~ **Done 2026-04-16** (Lechonk CD prep Session 2;
  see "Narrative renderer polish gated on Oinkologne" below for items
  logged but not fixed), and (3) Aegislash form-change dive that
  stress-tests narrative generation when the species swaps moves/stats
  mid-battle.

* **Narrative renderer polish gated on Oinkologne** — surfaced during
  the Goodra test-drive (2026-04-16, Lechonk CD prep Session 2). Items
  are cosmetic; holding until Session 4 (Oinkologne deep dive) reveals
  which actually bite on a different species before fixing
  speculatively.
  1. **General-tier 3-stat signature** — `Premium Bulk (116.30 Atk,
     125.35 Def, 109 HP)` on moveset 0 shows atk, def, and HP even
     though the "Premium Bulk" name signals bulk is the narrative
     anchor. `_stat_signature` suppresses the non-primary axis only
     for specialist flavors (those with `primary_axis` set by tier
     name); General tiers keep all populated axes. Rule for "when
     should a General tier treat one axis as primary" is unclear —
     maybe "if tier name contains 'Bulk'/'Slayer'/etc.", but General
     is by definition unnamed. Revisit on Oinkologne if the General
     signature reads confusingly.
  2. **22-IV catch-phrase edge case** — `_catch_phrase` caps at 500
     catches as "very rare". The 22-IV Altaria Slayer on Goodra
     moveset 4 shows `~129-258 for a 50-75% chance`, which is under
     the cap but still a large number; arguably should have a middle
     "rare" tier. Wait for Oinkologne to see what catch counts
     actually land in the 50-300 range before adding a tier.
  3. **Session 2 validation note** — most Goodra narrative thresholds
     that diverge from RyanSwag's June 2024 reference are explained
     by opponent-pool shift (Lickitung/Gligar/Mantine/Pelipper no
     longer in PvPoke GL top-21), not renderer bugs. Session 4 /
     Oinkologne should not re-litigate these; they are expected data
     differences per the existing "format and reasoning style, not
     exact stats" principle.
  4. **Identical-stat flavors not merged** — surfaced on Oinkologne
     Tackle moveset (Session 4): "Quagsire Slayer" and "Quagsire
     (Shadow) Slayer" have identical stat signatures (123.97 Atk,
     153 HP) and 0 IVs each. When two opponent-derived flavors share
     the same stat thresholds, they should be merged into one flavor
     named after both opponents (e.g. "Quagsire / Shadow Quagsire
     Slayer"). The merge should happen in the narrative renderer's
     flavor-derivation logic, not downstream.
  5. **Narrative flavors not reflected in Plotly scatter tiers** —
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

* **Export Notable IVs cards to external scanner tool** — The user has a
  separate tool that scans their existing pokemon collection against
  IV target specs. Each Notable IVs card represents a target the user
  might want to feed to that scanner: composite cards have stat
  cutoffs (`atk≥X, def≥Y, hp≥Z`) and matchup cards have an exhaustive
  IV list. Add per-card "Copy to clipboard" buttons (matchup cards →
  IV triples; composite cards → stat cutoffs). Possible "Copy all
  visible" button at the section header for the typical "filter to
  notable, copy everything" flow. **Format unknown until user
  specifies what their scanner accepts** — could be plain comma-
  separated triples (`0/8/15, 0/11/11, ...`), Pokegenie/CalcyIV search
  strings, JSON, or something specific to the scanner. Ask before
  implementing. Discovered 2026-04-09 while reviewing the first
  Annihilape Notable IVs render — a 16-IV matchup card with no way
  to extract its members surfaced the gap.

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

* ~~**Bait-axis matchup categories**~~ — **SHIPPED.** Confirmed
  2026-04-16 while scoping S3 histogram. Non-bait matchup cards
  populate `bait` from `parse_mode(opp_iv_mode)[1]`
  (`deep_dive.py:415-423`); the bait-differential builder in
  `deep_dive_rendering.py:2840-2910` emits "Beats … with bait only" /
  "… no bait only" cards keyed on `(opponent, scenario, bait)`; and
  `matchup_subtitle()` at `deep_dive_rendering.py:517-538` renders the
  ``· no bait`` / ``· with bait`` suffix. Follow-up UX polish (richer
  narrative phrasing, merging adjacent bait cards) lives in S17 of the
  post-S5 arc, not here.

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

* ~~**Threshold Tiers intro: document multi-axis anchor filtering**~~ —
  **Done 2026-04-16** (Lechonk CD prep Session 1). Intro rewritten as
  short lead + nested `<ul>` covering subset, crossed-cutoff, and
  slayer-axis IV-count cases. Rendering gained (a) an "Anchors we get
  for free" collapsed `<details>` per tier, surfacing anchors on axes
  the tier doesn't cut off but every IV still clears, and (b) a
  parent-tier diff callout in the header (e.g. `(−73 vs Balanced,
  def-sacrificing / hp-low spreads excluded)`) when a tier's IVs are
  a strict subset of a looser tier's. Verified against Annihilape m0
  (`High Bulk` tier: 5 primary def-bulk bullets, 1 free atk-mirror
  anchor, −73 vs Balanced callout).

## Diagnostics / observability

* **Switch deep_dive.py from print statements to a structured logger**
  *(two sessions: planning + implementation)* — Recurring friction during
  dive runs: stdout buffering makes live monitoring unreliable (analysis
  phase goes silent for minutes while CPU is at 100%); piping through
  `head` or `tee` introduces SIGPIPE / buffer-sync issues; no per-run
  log file means `tail -f` races against the TTY; cache conflicts
  between parallel dives (prevented by policy, but not diagnosable when
  it happens); and no way to distinguish "stalled" from "working but
  quiet." A real logger (Python `logging` module or structured JSON
  logger) would give: (a) per-run log files with unique run IDs,
  (b) timestamps on every message for elapsed-time reasoning,
  (c) unbuffered writes to the log file (bypassing stdout pipe
  buffering), (d) severity levels (progress vs. warnings vs. results),
  (e) a machine-readable format for post-hoc analysis of run times.
  **Planning session**: audit all print() calls, classify by severity,
  design the log format and file layout. **Implementation session**:
  port prints to logger calls, add per-run log file rotation, verify
  `tail -f` works cleanly on the log file during a real dive.

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

## Schema simplification

* **TOML simplification triggers** *(collect friction, don't act yet)* —
  Worry surfaced 2026-04-09: the legacy JSON threshold files were three
  keys; the current TOML schema is ~530 lines of docs and Annihilape's
  hand-authored file is ~180 lines. Sample size of one species (plus a
  one-line tinkaton stub) is too small to design a simplification
  against — Annihilape is also the *worst* canary because its
  Lurgan/mercuryish historical provenance pressure makes it
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

## Refactoring

* **Split `scripts/deep_dive.py`** *(deferred from 2026-04-09; not
  blocking, but file is now ~6100 lines as of 2026-04-10)* — After the structured IV
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

Historical/shipped work lives in `CHANGELOG.md`.
