<!-- Live backlog: open items and forward-looking notes only. Finished work =
one condensed CHANGELOG.md entry + delete the bullet (gated, .hygiene.toml). -->

## Resume here

Current state and next steps only. Replace in place, max 40 lines (gated);
detail lives in the sections below.

- First hygiene groom done (2bc45b4..close-out): TODO 89,491 -> ~30k chars,
  cap now 45,000 (`.hygiene.toml`). Over the cap: close or park, don't raise.
- Groom follow-ups done 2026-11-19: CLAUDE.md b-i and memory m2-m12
  (CHANGELOG 2026-11-19).
- `opponent_pools/master_top60.txt:5` cites TODO "Reproducibility" (now in
  docs/TODO_backlog.md; pool file is data, left alone). Agent worktree
  .claude/worktrees/agent-ab8b90f5b273c7934 has an uncommitted edit to
  src/gopvpsim/pokemon.py (engine-hash file): keep or discard?
- 18 slow-tier `local_artifacts` tests in tests/test_which_build_section.py
  fail at HEAD (e.g. expects "55 of 87", page says "guarantees 40"); likely
  rankings drift from the 11-17 refresh. Look before the next full-suite gate.
- Publishing waits on Michael's go: Tinkaton GL + UL and the Minior pages
  are local only ("PvPoke sync 2026-11-17", "Minior -- open items"); a
  Cramorant UL re-dive is owed before any Cramorant publish.
- Before the next bake: refresh the mega rankings; the bake is cold.

## Minior -- open items (port shipped 2026-10-24; record: CHANGELOG 2026-10-24)

Michael 2026-10-24: "take your recommendation. we can improve later" -- the
port is PvPoke-exact on its 90 oracle cells; these are the loose ends.

- **Medicham vs Minior links:** before linking any Medicham-vs-Minior PvPoke
  battle from a page, check which seat PvPoke puts Medicham in (seat 1
  reproduces our 1-2/2-2 numbers; DEVELOPER_NOTES Minior "2 of 702"). Any
  re-sweep pins `level=50` for Lickitung.
- **Minior GL pages: local only, publish on Michael's go** (CHANGELOG
  2026-10-24 (night)). Pre-publish: (a) `anchors.py` breakpoint/bulkpoint
  labels use CORE stats on both sides (~15% of spread pairs swap attack
  order across forms; labels only): caveat or decide; (b) the callout's
  "(Core only)" pointer is plain text, not a link; (c) the Core-only mirror
  has no PvPoke link (PvPoke can't start a Minior in Core): say so or hide
  the slot; (d) tier-card anchors read "Minior Core (Move)", not "Minior
  (Core)"; (e) the Mimikyu-ordering fix touches 2 of 693 cells. The hand-built
  UL/ML pools still read DRIFT and are not inputs; the pool preflight checks
  every pool, not the selected dives' (small runner change).
- **Minior UL pages: local only; the Core page's shell level is Michael's
  decision** (CHANGELOG 2026-10-25; readings:
  docs/validations/2026-10-25_minior_ul_level_readings.md). The 55 ceiling
  is confirmed in-game, so +6 CPM entries (PvPoke 52.5-55) are owed
  regardless. That is an engine bump that must first pin the Aegislash
  shield-level clamp (formchange.py:222 `max(CPM)`) at 52; predicate "Minior
  or Aegislash on either side". Below the ceiling PvPoke's formula is wrong
  too: low IV totals (<=20) get no boost (shell = Core + 0.5), threshold
  21-24, and the boost formula above it is open. Next: read the
  threshold-pinning Miniors listed in the doc, then decide the model. Until
  then the UL Core page keeps its caveat callout and stays unpublished; the
  Core-only page is unaffected.
- **Engine fix riding the next bump: Mimikyu break-disguise runs BEFORE
  turnsToLive** (found 2026-10-24 by the pre-dive L1 sweep, 2,106 Minior
  cells vs PvPoke 38f70320d, 31 mismatches, 30 catalogued, this the one
  new). PvPoke's order is turnsToLive (ActionLogic.js:38-207), the lethal
  throw (:210), THEN "opponent is Mimikyu, throw fastest charged ASAP"
  (:236-251); `pvpoke_dp` (battle.py ~1834-1858) checks the disguise first,
  so at low HP vs an intact disguise we throw the cheapest move where PvPoke
  throws the TTL max-damage move. Both break the disguise for 1; only
  leftover energy / debuff side effects differ. Pool scan (78 opponents x 9
  vs Mimikyu, 693 cells): 10 cells fit the pattern (Araquanid x3, Charjabug
  x2, Forretress (Shadow) x2, Oinkologne x2, Spidops), 2 change score
  (Forretress (Shadow) 1-1 289 -> PvPoke 411, Rock Tomb debuff lands;
  Oinkologne 1-2 439 -> 453), 0 winner flips; 8 of the 10 pattern-matched
  only. Fix = move the block after the lethal throw; migration predicate
  "Mimikyu on either side"; its own engine bump (one localized fix per bump).
  Raw: scratch agent_L1/results_mimikyu_scan.json (session-local).
- **`_minior_core_level` rounds with Python `round`** (banker's) where
  Pokemon.js uses `Math.round` (half-up) -- dead code for our dives, which
  always store Core; fix with a future engine bump.
- **Level rule:** `MINIOR_HALF_LEVEL_STEP` (False = PvPoke's simulator path).
  Re-check go-iv PR #48 and pvpoke master for a settled rule before a bake.
- **Report 11** (`docs/pvpoke_bug_reports.md`) stays a draft: Michael
  2026-10-24, not filing anything upstream while PvPoke has not responded to
  the 2026-07-16 batch.

## PvPoke sync 2026-11-17 -- open items (record: CHANGELOG 2026-11-05, 2026-11-17)

Re-vetted at pvpoke `d02018eb6` (DEVELOPER_NOTES "PvPoke re-vetting log"):
engine `a6dffb536332`, slayer `1294f3bbff20`, gamemaster `10d0d903c162`.

- **Mega rankings were NOT refreshed** (`rankings_mega_{1500,2500,10000}.json`
  in `~/Documents/gopvpsim_cache/` are 09-27): Mega Sableye still resolves to
  Shadow Claw / Foul Play + Dazzling Gleam (upstream GL adds Night Shade+),
  including on the 11-17 Tinkaton GL page. Upstream, 11 GL mega defaults
  differ (4 changed incl. Sableye (Mega), 7 newly ranked) and 18 UL (15
  changed, 3 new). Refresh (recipe below) before the next bake, then re-dive
  Tinkaton GL (UL has no mega opponents).
- **Publish Tinkaton GL + UL on Michael's go** (re-dived 11-17 on the
  current pools, local only, probe-verified; GL carries the Mega Sableye
  caveat above). `scripts/publish_website.sh` (dry run), then `--push`,
  outside the sandbox. It mirrors the WHOLE `userdata/website/` tree with
  rsync `--delete` and rebuilds the index itself, so the push also
  (a) ships the four local, unpublished Minior pages ("Minior -- open
  items" -- needs his go too, or move them aside first) and (b) removes
  the pruned diggersby / snorlax / shadow-snorlax GL pages from the live
  site. UL Snorlax pages stay.
- **Every other page is opponents short until re-dived.** The shipped pages
  were baked 09-27 at the 09-17 pools (68b7f1a), so they miss every pool change
  since (99e1219, 9a762de, e7478a5; `git diff 68b7f1a -- opponent_pools/`):
  e.g. UL lacks Golisopod (Shadow), Kingdra, Malamar, Toucannon (Shadow),
  Togekiss; GL top50 lacks Dunsparce, Dragonair (Shadow), Kingdra (Shadow) and
  still sims Diggersby / Snorlax / Snorlax (Shadow). Unbuilt registry slugs
  include dunsparce-great-league and togekiss-ultra-league
  (`dive_registry.all_dives()`).
- **The next bake is effectively COLD.** Every cached column is at engine
  `4b42f9d83690` (slayer `3a2ed21a79ce`) / gamemaster `6d6e9a7bc32d`, the
  09-28 bake (`migrate_cache.py --list-stamps`). The old migration plan
  (from 9856aa366b5d / 3d125a0e165f / 03e7b77024e9) matches zero columns,
  and each migrate mode needs the OTHER stamp current, so it cannot bless
  a column stale on both. Warm-serving would need a combined
  engine+gamemaster mode plus a predicate covering the whole
  `4b42f9d83690 -> a6dffb536332` delta (Minior port + Mega Level 4) -- a
  "tractable migration?" call (CLAUDE.md) before the next cold re-dive.
  Such a predicate must cover the Minior port: Minior on either side OR a
  SUPER_POWER / PSYCHO_BOOST user OR either side's frozen post-shuffle
  charged order != its LISTED order (not ascending-energy: Cramorant UL vs
  Dusknoir 470 -> 487,
  docs/validations/2026-10-24_cramorant_strat_recheck.md), plus a proof that
  fix 1's queue-order change is a no-op without a same-turn form flip. Not
  implemented.
- Headless mega ML batches: pin `--pN-level` or `initialize(10000)` without
  IV edits (DEVELOPER_NOTES PvPoke bug 12).
- **Thievul/Tinkaton candidate cull (Michael):** Nickit, Tinkatink and
  Tinkatuff cannot reach GL or UL (hundo L51 817 / 984 / 1495 CP) and IVs
  carry through evolution, so rank by the evolved form's page: paste the
  Poke Genie export into its collection box, or `owned_breakdown.py --csv`.
- Data-cache refresh: docs/rebalance_checklist.md section C (`cp` from
  ../pvpoke, incl. the mega rankings; sandboxed runs need
  `GOPVPSIM_PIN_DATA_CACHE=1`).
- Sub-entry gamemaster narrowing: hash only the sim-read FIELDS inside
  pokemon/moves entries, so UI-only PvPoke churn stops cooling the cache.
  Rides a bake ONLY if it is cold for its own reasons; never force a cold
  bake for it (Michael 2026-09-22). Today `sweep_cache.gamemaster_subset`
  hashes whole pokemon + moves.
- Before a cold re-dive: docs/predive_checklist.md (launch + watch lines
  are there).

## OPEN: Bake speed -- residue (record: CHANGELOG 2026-09-25, 2026-09-26/27)

- Undecided (perf doc Q5): the 12 test-pinned replay blobs already missing
  from disk -- re-pin or drop (the tests skip on them today).
- MICHAEL: the 258-blob superseded replay prune (9.5 GB; keep-set rule in
  `docs/perf/2026-09-25_bake_attribution_and_cruft_scout.md` R7) was left to
  you on 2026-09-25, not run by the session.
- Next lever: `--jobs N` dive overlap, `docs/parallelize_dive_plan.md`
  (memory-bound, 4.9-11.6 GB peak RSS per render).

## Dive tensors vs per-profile truth -- residue (record: CHANGELOG 2026-09-23..25)

- Re-run the statfx lab's plain-PvPoke cross-check once on the current
  tensors (expect 0 of 165 class pages mismatching; it was 25 of 165 on the
  9ac12a2754a1 bake) to close the loop.

## Thievul CD -- residue (shipped record: CHANGELOG 2026-08-15/16 + TODO_archive)

- MICHAEL: reply to u/LeansCenter on the r/TheSilphArena launch thread
  (as u/SpaceBearAI; open since 2026-08-15). Drafted bullets: 44W-44L
  -> 62W-25L at 1-1/rank-1 IVs/88-mon pool; IW+PR beats PvPoke's
  NS+IW default by ~14 wins; PvPoke overall GL rank 122 -> 41.
  Context: docs/thievul_cd_plan.md "The request". Their post-rebalance
  IV-reshuffle question is actionable now (the rebalance landed).
- MICHAEL: HSH discord message (docs/hsh_message_notes.md) -- the
  draft is pre-Worlds stale (bullets 1 and 5 are written as future
  events that have passed); refresh to post-Worlds framing before
  sending, or kill.
- Shipped thievul robustness pages carry two wording issues from the
  pair-1 review: the 'IV tech without meta cost' card costs 5W on the
  lickilicky page (its own max-meta card shows 63W vs 58W), and the
  debuff-stage cross-check ladder was built from the rank-1 opponent
  instead of the simulated probe (stage -3 renders 21; correct is 22;
  `stage_ladder_from_rank1` in pairs/thievul_lickilicky.toml
  preserves the shipped bytes and documents it). Rebuilding with the
  current kit fixes both -- republishing is Michael's call.
- `thresholds/thievul.toml` [cd_prep] retirement rides the
  post-Worlds bundle (see docs/TODO_backlog.md "Worlds 2026 -- dormant
  residue").

## Cramorant -- open items (record: CHANGELOG 2026-08-24..27, 2026-09-10..12, 2026-09-12, 2026-09-15, 2026-09-27)

**PUBLISH GUARD: a Cramorant UL re-dive is owed before ANY Cramorant
publish.** The shipped UL page predates the Minior-port TTL-order fix
(Dusknoir / Shadow Dusknoir / Seaking cells; CHANGELOG 2026-10-24 "PoGoDives
strat re-checked"). `--check-record` is sha256-only and would pass it:
before the next publish make it re-sim an opponent-stratified sample, or
raise `--selftest` N.

- After any bake touching Cramorant: run docs/cramorant_policy_plan.md
  "Post-bake certification runbook" (certify -> rehearse -> render ->
  `--check-record`; `publish_website.sh` enforces the last step).

**Michael's open decisions** (leave as-is until answered):

- **Guzzlord 2v2: documented cost or target?** GL Dive+Fly 2v2 nobait:
  -1559 win-cells, +72.6 mean (the rush pads rating onto lost fights and
  pays with 504-519 razor wins). RECOMMENDATION: documented cost -- it
  passes the bar, and every gate retune that removes it fails the UL
  Dive+Fly holdout by -320..-830 net. "Target" means a GL-only 2v2 gate
  conditional (M5 in `docs/validations/2026-09-12_cramorant_deep_vet.md`)
  and a new campaign.
- **Gate-column refactor.** `gate on iff opp_start_shields >=
  my_start_shields` reproduces all 9 rows. RECOMMENDATION: yes, as a
  behaviour-neutral hygiene commit on its own engine-hash bump
  (always-true blessing predicate, like `neutral_batch_20260810`), together
  with deleting the three dead constants (`_POGODIVES_GATE_DPT_MAX`,
  `_POGODIVES_GATE_MIN_ENERGY`, `_POGODIVES_TANK_CHEAP_FRAC`; still in
  `src/gopvpsim/battle.py` and `scripts/cramorant_sensitivity.py` as of
  2026-09-27) and their `cmp_dpt`/`cmp_dpt_e`/`cmp_ready_dpt`/`cheap`
  branches; needs `tests/test_pogodives.py`'s synthetic rows and
  `cramorant_sensitivity.py` updated. Same hash bump: repoint
  `log_cancel`'s `see TODO "KO-EDGE"` comment in battle.py (the KO-edge
  cancelled-action record is the CHANGELOG 2026-08-27 KO-edge
  entry; battle.py can't be touched alone).
- **P-C / P-D, next cycle** (deep-vet doc): P-C = the KO guard at 1v1
  (measured positive in GL); P-D = the constant-free 1v2 `lead_drained`
  (costs most of the row).
- **Jumpluff / Kingdra at 0v1 -- engine side DONE 2026-09-28 (sheet v8,
  rule R; CHANGELOG 2026-09-28 "PoGoDives sheet v8").** Row (0,1) keeps the
  early Surf while behind on HP fraction; stride-1 recert of the GL Peck /
  Fly + Surf page and byte-identity controls on every other page are in
  that entry. Still open: apply `migrate_cache.py --predicate
  cram_0v1_rule_r_20260928` (re-pin --from-engine to the base engine at
  merge), Cramorant GL re-dive, `cramorant_certify.py --out` record,
  article re-render (the 0-0/0-1 cheat-sheet row gained the Surf rule
  text -- Michael reviews), publish on Michael's go.
- **Article prose pass (ship-mode, Michael's).** The 2026-09-27 re-render
  refreshed every tensor-derived number, but the fixed prose in
  `scripts/render_pogodives_strategy_article.py` still carries claims the
  2026-09-12 audit flagged: the hero's "certified never worse ... in any of
  the nine shield scenarios ... on both win rate and average battle rating",
  the 1-1/1-2 row's "lead of 40+ percentage points" (the LEAD constant is
  inert, 5b29e84), the 2-1 cheat-sheet row, Methods' "no negative cell
  shipped", and the UL "honest flags" 2-1 headroom framing. The audit's
  counter-example to the hero and Methods claims (UL 0v1 Dondozo -2) was a
  single-spread artefact at full resolution (deep-vet doc), and the
  2026-09-27 certification reads 0 bar failures over 720 cells, so those two
  may now be defensible; re-read them against that record, not this note.
  Per the 2026-08-31 rule, stale public prose gets fixed or the page comes
  down. Outside this repo: the `~/coding/reports/pogo-reports.html`
  Cramorant card still states the v4 "every start scenario >= 0" claim.
- **PvPoke Report 8 -- drafted, NOT FILED** (`docs/pvpoke_bug_reports.md`):
  two `move.moveID` typos in ActionLogic.js, at :378 and :1271 on pvpoke
  d02018eb6 (2026-11-17); the :1271 one makes defenders never shield a
  lethal Cramorant Dive. Check the tracker for duplicates first. (Report 9
  was fixed upstream in e87448291, 2026-09-27: do not file.)
- **Opponent-pool curation (Cramorant accepted test debt (b)):** Cramorant
  IS in `gl_top50_plus_cs.txt` (since c0968bc) and `ul_top60.txt` and is an
  opponent in every bake; `verify_opponent_pools.py` labels it "curated out"
  only because `curated_out = excluded & live` (:181, :208). Decide keep
  (today's reality) or exclude in the recipe; fix the label either way.

**Lens-grid item, OPEN: the data-cache TTL keeper.** A launch-time
preflight should refuse a bare `run_website_dives.py` run without the TTL
keeper, or the runner should own the keeper. 7090ce0 (2026-09-20) pins the
data cache (`GOPVPSIM_PIN_DATA_CACHE=1`) only inside `overnight_redive.sh`;
a direct `run_website_dives.py` launch -- how the 2026-09-12 rebake ran,
letting the live gamemaster refresh mid-bake -- is still unpinned.

Parked in docs/TODO_backlog.md: the UL Dive+Surf 2v2 tank discriminator
("Policies to add"), the strategy article pair + hard-counters re-derive
("Features to add"), and accepted test debt (a) ("Accepted test debt").

ACCEPTED TEST DEBT (per policy, recorded): (b) The opponent-pool curation
call: see "Opponent-pool curation" under Michael's open decisions above.

## Worlds 2026 -- dormant until 2027

The rest of the dormant Worlds residue (retire-together bundle, editorial
decisions, deferred bakes, polish) is parked in docs/TODO_backlog.md
"Worlds 2026 -- dormant residue".

- Before ANY Worlds re-render or bake: docs/worlds_prep_plan.md "Revival
  standing rules" (gamemaster re-pin, `WORLDS_RERENDER=1`, publish/bake
  rules; a 2027 bake is new-mechanics).
- **Un-skip at the 2027 cycle** (or earlier if IV-robustness needs them):
  the three Worlds artifact tests skipped in e044959
  (`test_worlds_meta.py`, `test_worlds_bake_guards.py`,
  `test_build_worlds_pair_pages.py`; reason in each skip marker).

## Article regen triage (Twilight Trails, post-2026-09-08)

The per-article regen / no-regen triage (Michael 2026-08-31; gate = meta
relevance in open + cups) folds into the season-start teardown
(`docs/article_archive_plan.md`). Residue:

- **Oinkologne CD article** (`articles/oinkologne-cd-2026-05.toml`, never
  rendered, 6 PLACEHOLDER bodies): regen-vs-drop on the open+cups meta test
  before any authoring; Take Down 5->14 power can invert its Mud Slap vs
  Tackle/Take Down thesis.

Still open, Michael's: what counts as "in the meta" for the cups half,
given the season ships eight of them (Willpower, Retro, Mega Color,
Little, Fantasy, Halloween, GO LAIC, Mega Catch).

- At each new season's start ALL prior-season surfaces come down (Michael
  2026-09-02; no staleness markers, removal not caveats): policy, removal
  mechanism + season-start bake checklist in docs/article_archive_plan.md
  "Site lifecycle and removal policy".

## Mirror population -- open residue (built 2026-09-28, e83a834 / d5ca413; record: CHANGELOG 2026-09-28)

Decision of record: `docs/expert_verdict_plan.md` "Mirror population:
decision of record". Schema: the `scripts/deep_dive_lib/mirror_population.py`
module docstring.

- Corpus coverage: a page shows the population block only after a re-dive.
  The 2026-11-17 Tinkaton blobs carry `state['mirror_population']`; the
  rest of the corpus gets it on the next (cold) bake.
- Residue: (b) only the 1v1 scenario is printed (all nine are in
  `population_facts`); (c) league cap only -- an L51 section keeps the
  cohort paragraph; (d) the plot's mirror trace + caption still read the
  cohort; (e) a thresholds-TOML override list of what the community runs
  (candidate 3) is deferred; (f) the block is not gated on the mirror being
  a decision cell (the cohort paragraph was), so it appears on arms that had
  none (Melmetal GL arms 1-2) -- Michael to confirm.

## "Which one to build?" -- what is next (record: CHANGELOG 2026-09-12..22)

Design of record: `docs/expert_verdict_plan.md`. The build brief (v2/v3),
the spread-sets and builds-lattice analyses and the section's v4 (rounds
1-10) are shipped; see CHANGELOG. Open:

- **Retire the flavor guide's `[Recommended]` badge AND the "almost any will
  do" catch phrase** (Michael 2026-09-12, D10: two separate commits "when the
  brief ships"). NOT done: both still in `scripts/deep_dive_narrative.py`
  (:52, :1368, :1399) and the badge is on all 136 local dive pages
  (2026-09-27).
- **Shield scenarios in the section:** the v4 Build-criteria presets (all
  nine equal / even shields / 1v1 only) partly cover follow-up (1); a
  section-own selector over any one of the nine scenarios is not built.
  Follow-up (2), a usage prior over shield states (lead / safe swap /
  closer), needs an expert-supplied or usage-derived prior the sim does not
  have ("lead-and-closer" placeholder was skipped in v4).
- **Spread sets** (report `~/coding/reports/gopvpsim-spread-sets-2026-09-15.html`):
  (1) the per-arm set-keeping cut (18 per arm) still uses the old interest
  score; adopt the material-cells ranking and re-run the corpus (~2.5 h,
  nice'd); (2) extend the score column to the corpus; (3) export explicit
  IV lists to gobattlekit behind its four-target cap (the color-group plot
  half of this shipped as v4). Not re-verified item by item after v4:
  `deep_dive_builds.py` still ranks kept sets by `rank_interest`, and the
  gobattlekit export had not been run as of 2026-09-22.
- **Builds lattice** (report `~/coding/reports/gopvpsim-builds-lattice-2026-09-16.html`):
  (1) the lattice searches only the 18 named sets per arm (a hand-built
  (Def, HP) box out-guarantees every lattice region on 45 arms: the
  generators are the binding constraint); (2) decide the material /
  all-modes bars for headlines (the median build guarantees ZERO cells
  that are both material and survive all opponent IV/bait modes); (3)
  objective B under the prior needs the per-scenario win cube. Item (4),
  the product, shipped as v4.
- **Rankings-vintage sensitivity** (49507a3, 1d33e7c): opponent PvPoke
  ranks are a LIVE read at render time (`build_opp_meta_ranks` ->
  `get_rankings_for`), so a rankings refresh can change a page's verdict
  with no sim change (2026-09-15: Charjabug 60 -> 41 deleted Melmetal's
  floor). Bakes now see one vintage via the chain's data-cache pin
  (7090ce0; the direct-launch gap is the TTL-keeper item in the Cramorant
  section). Proper fix still open: stamp opponent facts (ranks, default
  builds) into the blob at dive time (expert_verdict_plan Phase 0 "blob
  stamping") so replay re-renders cannot drift; other test modules that read
  live rankings were not audited.

## PLAN ONLY: parallelize the dive step

- **Parallelize the dive step (`--jobs N` in run_website_dives.py): PLAN
  ONLY** -- do not implement without Michael's go (2026-09-12).
  Memory-bound (4.9-11.6 GB peak RSS per render), ceiling <=6.9 h serial.
  Plan + measurements: `docs/parallelize_dive_plan.md`.

## Engine bug-hunt round 2 (2026-07-02) -- open residue

(Report: `docs/reviews/2026-07-02_engine_bug_hunt_round2.md`; all 16
findings dispositioned, record CHANGELOG 2026-07-03 + 2026-08-09.)

- **js-parity residue** (LOW): winsMirror branch of the collection-table
  "Gives up vs #1" column (`deep_dive_engine.js` ~:1673-1711, inside the
  `patch_dive_gives_up_column.py` REGION_SHA256 pin) reuses that header for
  a mirror win-shortfall COUNT. Rename when something next pays the
  re-stamp.

### Open follow-ups (non-gating; render/tooling-only ones re-render from replay)

- **[cli] breakpoints max-level default divergence:**
  `iv_breakpoints`/`iv_bulkpoints` default attacker/defender max level
  to 51.0 while `iv_rank`/`at_best_level` default to LEAGUE_MAX_LEVEL
  (50.0 in GL/UL), so `scripts/breakpoints.py`'s rank column and damage
  table can disagree on level for EVERY species. Changing the default
  moves every CLI number -- needs its own scoped decision. (Surfaced by
  the BP-3 fix `89bf7b1`, which strictly reduced the mismatch.)
- **[render, product decision] js-parity-3 scale half:** on a
  `--species-iv-floor` dive, `spRanks` is dense 1..n over the pruned
  subset while `rankLookup` stays global 1..4096, and the JS column
  interleaves both scales. Fix = bake spRanks from
  `compute_rank_lookup` (rank table needed before the DATA block,
  alt-cap for the L51 twin, "(Shadow)" key path) -- and it changes what
  IV-floor pages display (rank 1 may not appear at all). Caveat
  documented at `deep_dive_engine.js:~1270` + `sp_rank_array`'s
  docstring.
- **[render] matchup_clusters' own SP rank**
  (`deep_dive_matchup_clusters.py:~980-983`) is a FOURTH convention
  (argsort over the 2dp display arrays); it now diverges from the
  unified three post-`881d415`. Fixing changes rendered cluster
  "SP #a-#b" labels.

## Top-N opponent filter + limited-cup dives -- Phase 3

Phases 1-2 shipped (CHANGELOG 2026-07-03). Open: Phase 3 -- more cups,
legality-filter eval, app-side cup toggles (needs a coordinated
`default_thresholds.toml` format axis), mega engine. Plan:
`docs/topn_cup_filter_plan.md`.

## Morpeko dive is missing its form-change note

- **A Morpeko dive must carry a form-change note at the top** (Full Belly
  <-> Hangry toggles AURA_WHEEL Electric/Dark after each charged move; same
  `_FORM_CHANGE_NOTES` mechanism, `scripts/deep_dive.py`). The trigger has
  fired: a Morpeko (Full Belly) GL dive exists locally in
  `userdata/website/morpeko-full-belly-great-league/` (rendered 2026-09-27)
  WITHOUT the note (`_FORM_CHANGE_NOTES` has no Morpeko entry). Add the
  entry and re-render from replay; publish-blocking if the page is live.

## Site polish

- **Favicon.** pogodives.com has never had one (the 2026-08-27 publish
  removed DreamHost's 0-byte placeholder `favicon.ico`/`favicon.gif`,
  provisioned 08-24 -- we never made a real one). To add: drop
  `favicon.ico` (or PNG + `<link rel="icon">` in the templates) into
  `userdata/website/`; it then rides every publish. Candidate art: the
  Cramorant HOME sprite / a dive-flag glyph.

## Deferred cleanup: backwards-compatibility removal pass

- **parse_types lazy alias in data.py** (`data.py:637` `__getattr__`):
  gobattlekit's `tools/threshold_export/export_thresholds.py:55` still
  imports it from `gopvpsim.data`. Unblocked (Worlds 2026 is over): switch
  that import to `gopvpsim.moves`, re-pin
  `tests/test_gobattlekit_api_pin.py`, delete the alias.

## Battle simulator

* **PvPoke upstream** (filed 2026-07-16 as #378-#382; record in CHANGELOG
  "Archived: PvPoke bugs found"). Open: Report 5 held back (paste-ready,
  `docs/pvpoke_bug_reports.md` "Holding back for now - Report 5"; if filed
  later, adjust the opener's "5 reports today" line and re-check
  `git log 10fd1a6e4..master -- src/js/` first); engage with Matt's
  replies as they come (don't re-ping); site 429 vs headless 510
  (Aegislash SB-only vs Azumarill) unexplained, possibly Report 9's
  double-sim root cause (fixed upstream e87448291), see that doc's header.
  Until resolved, don't cite harness ratings as site-reproducible in
  razor-thin cells.

* **Known PvPoke divergences** -- DEVELOPER_NOTES "Known divergences from
  PvPoke implementation" + `docs/pvpoke_divergences.md`; audit baseline
  lives in DEVELOPER_NOTES "Current status" (re-audit:
  `python scripts/audit_oracle_harness.py`).

## Tests to add

* **pvpoke.com/battle round-trip for the iv-tech no-bait oracles**
  (Tinkaton 0-1 vs Shadow Altaria, Spidops 1s vs Altaria): click through
  the key cells on the site when convenient (human step).

## Refactoring

* **Pain points captured during real debugging** — memory file
  `project_post_ship_cleanup_pain_points.md` in the retired
  pogo-simulator project's dir
  (`~/.claude/projects/-Users-mglerner-coding-MGLPoGo-pogo-simulator/memory/`):
  silent early-returns with no logging, hardcoded magic numbers
  assuming `nS=9`, parallel call-site duplication, free-form-string
  opponent identity, `data_obj`-as-mutable-bag (the note's
  replay-from-saved-state and `id()`-keyed-cache items are marked
  resolved there, arc S4). Specific friction encountered while
  diagnosing the 2026-04-25 mirror-tier-synthesis no-fire bug;
  read this *before* starting the deep_dive.py split below so the
  cuts address actual pain rather than aesthetic ones.

* **deep_dive.py split step 6 (not scheduled):** extract the page-assembly
  half of `generate_interactive_html` into `deep_dive_lib/page.py` (`main`
  stays). `build_collection_data()` is already extracted
  (tests/test_collection_data.py). Doc gap: DEVELOPER_NOTES has no
  `deep_dive_lib` entry (layout lives in `deep_dive_lib/__init__.py`); no
  dedicated test_render.py / test_sweep.py. Don't recreate the originally
  planned `deep_dive_lib/anchor_flips.py` / `slayer.py` (spawn workers are
  test-pinned in deep_dive_slayer.py).

## User-facing documentation (Reader's Guides)

- **Review the IV Robustness guide** (`guides/iv-robustness/`, at
  `authorship=ai` -> promote to `both`).
- **Glossary gap:** `docs/concepts.md` does not define the envelope-crosser
  vocabulary the dives print (`elevated-band-crosser` /
  `depressed-band-crosser`, `deep_dive_rendering.py:~1551`); found closing
  the Shadow Sableye GL bands reminder (CHANGELOG 2026-09-22).

The IV Flavor Guide write-up is owed to an HSH Discord member (the
write-up commitment note lives in the retired pogo-simulator project's
memory dir, not this project's) — the guide sits at `both` today; promoting it to
`expert` is the closing of that commitment.

## Turn-system / Aegislash residue

History: CHANGELOG 2026-09-02..03, 2026-09-09..10, 2026-09-27/28.

- **Aegislash Blade-atk fix (CHANGELOG 2026-09-27, 2026-09-27/28): publish
  pending.** The GL re-dive is local; published GL pages still carry the old
  Aegislash numbers + G-caveat stamp until the next push (Michael's call).
- **F1 (decide):** farm-gate ordering vs PvPoke's farm-down early return
  (touched set: Aegislash either side). F2a/F3/F4 closed (CHANGELOG
  2026-09-28).
- **Threshold-TOML prose (3b(c) of the 2026-09-09 re-vet):** 182
  descriptions cited a decimal number in prose; each one whose underlying
  threshold moved is now a wrong published sentence. e35db9f has since
  archived the 58 derived stat-cutoff spreads, so re-count first
  (`grep -hE '^\s*description\s*=.*[0-9]+\.[0-9]+' thresholds/*.toml`
  finds 135 single-line hits on 2026-09-25; not the same method). Where a
  value is re-derivable we can propose it, but which bulkpoint defines a
  named spread is editorial and stays Michael's; ship-mode narrative
  policy applies.
- **Duplicate `af-<hash>` DOM ids** (low, standards-only):
  `deep_dive_rendering.anchor_group_id` emits them once per moveset
  section; 0 anchor targets affected (measurement + template-stripping
  trigger: `docs/predive_checklist.md` Lens 4). Fix when the renderer is
  next open.

## Backlog (someday / maybe)

Long-tail design notes, research reproductions and the UI wishlist live in
`docs/TODO_backlog.md`; finished work in `CHANGELOG.md`.
