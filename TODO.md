<!-- Live backlog: open items and forward-looking notes only. Finished work =
one condensed CHANGELOG.md entry + delete the bullet (gated, .hygiene.toml). -->

## Resume here

Current state and next steps only. Replace in place, max 40 lines (gated);
detail lives in the sections below.

- TODO.md is at its 90,000-char placeholder cap: trim before adding.
- Next: the first hygiene cleanup pass, per
  docs/reviews/2026-11-17_project_hygiene/REPORT.md section 6. Michael
  approves the triage table before any edit; then reset the TODO cap to
  ~1.5x the post-groom size.
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
  were baked 09-27 at the 09-17 pools (a85d62e), so they miss every pool change
  since (383518b, 410bd5e, 75d13b6; `git diff a85d62e -- opponent_pools/`):
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

## FUTURE: PoGoDives strategy page (Michael, 2026-09-24)

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

## Dive tensors vs per-profile truth -- residue (record: CHANGELOG 2026-09-23..25)

- Re-run the statfx lab's plain-PvPoke cross-check once on the current
  tensors (expect 0 of 165 class pages mismatching; it was 25 of 165 on the
  9ac12a2754a1 bake) to close the loop.

## Thievul CD -- residue (shipped record: CHANGELOG 2026-08-15/16 + TODO_archive)

- MICHAEL: reply to u/LeansCenter on the r/TheSilphArena launch thread
  (as u/SpaceBearAI; open since 2026-08-15). Drafted bullets: 44W-44L
  -> 62W-25L at 1-1/rank-1 IVs/88-mon pool; IW+PR beats PvPoke's
  NS+IW default by ~14 wins; PvPoke overall GL rank 122 -> 41.
  Context: docs/thievul_cd_plan.md:85-109. Their post-rebalance
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
  post-Worlds bundle (see the Worlds "dormant until 2027" section below).

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
  `cramorant_sensitivity.py` updated.
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
  inert, 460a63e), the 2-1 cheat-sheet row, Methods' "no negative cell
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
  IS in `gl_top50_plus_cs.txt` (since f92bec1) and `ul_top60.txt` and is an
  opponent in every bake; `verify_opponent_pools.py` labels it "curated out"
  only because `curated_out = excluded & live` (:181, :208). Decide keep
  (today's reality) or exclude in the recipe; fix the label either way.

**Lens-grid item, OPEN: the data-cache TTL keeper.** A launch-time
preflight should refuse a bare `run_website_dives.py` run without the TTL
keeper, or the runner should own the keeper. 88bec7b (2026-09-20) pins the
data cache (`GOPVPSIM_PIN_DATA_CACHE=1`) only inside `overnight_redive.sh`;
a direct `run_website_dives.py` launch -- how the 2026-09-12 rebake ran,
letting the live gamemaster refresh mid-bake -- is still unpinned.

- OPEN VALUE (next campaign): UL Dive+Surf 2v2 under the OLD tank was
  +15-21k flips at passing rating; a per-build tank discriminator
  would recover it (sheet v5 ships zero there).
- Hard-counters lists: RE-DERIVE from the current-sheet (v7) tensors
  before any public surface carries one. Both earlier rosters (the
  static-tank "five losers" and the lead40-derived set) predate the
  shipped sheet.
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

ACCEPTED TEST DEBT (per policy, recorded): (a) the dive-ASAP gate's
fresh-vs-frozen `move.damage` divergence (documented at the rule in
battle.py) has no discriminating test -- needs a post-missile-debuff
re-dive scenario where the two damage bases differ; write it if such an
oracle cell ever drifts. (b) The opponent-pool curation call: see
"Opponent-pool curation" under Michael's open decisions above.

## Worlds 2026 -- code DORMANT until 2027 (record: CHANGELOG 2026-08-10..27, 2026-08-31..09-25)

Worlds (Aug 28-30) is over. Michael 2026-09-25 (perf-doc Q4 "no"): the
Worlds code, tests and `worlds/planes` stay in the repo DORMANT until 2027
-- no retire/delete pass now. The pages are off the site (no `worlds*.html`
in `userdata/website/`; publish rsyncs with `--delete`). Plan of record for
a revival: `docs/worlds_prep_plan.md`. Still open:

- **Retire-together bundle (rides the 2027 decision):** `thresholds/thievul.toml`
  `[Thievul.cd_prep]` (still present 2026-09-27), the `worlds/meta.toml`
  `injected_move_ids` declarations + their on-page disclosures in
  `build_worlds_pages.py`, and the injection guards in
  `tests/test_worlds_bake_guards.py`.
- Before ANY Worlds re-render or bake: docs/worlds_prep_plan.md "Revival
  standing rules" (gamemaster re-pin, `WORLDS_RERENDER=1`, publish/bake
  rules; a 2027 bake is new-mechanics).
- Link the IV Robustness guide FROM the Worlds hub/cheat sheets at the next
  Worlds re-render (needs the gamemaster re-pin above).
- **Un-skip at the 2027 cycle** (or earlier if IV-robustness needs them):
  the three Worlds artifact tests skipped in 066e528
  (`test_worlds_meta.py`, `test_worlds_bake_guards.py`,
  `test_build_worlds_pair_pages.py`; reason in each skip marker).

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

## Condensed-meta funnel bundle (queued 2026-08-19, Michael)

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
Standing publish/bake/pin constraints: see the Worlds section above.

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

## Mirror population -- open residue (built 2026-09-28, 60481e5 / 6ad44b7; record: CHANGELOG 2026-09-28)

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
- **Rankings-vintage sensitivity** (9adc094, e9c70ed): opponent PvPoke
  ranks are a LIVE read at render time (`build_opp_meta_ranks` ->
  `get_rankings_for`), so a rankings refresh can change a page's verdict
  with no sim change (2026-09-15: Charjabug 60 -> 41 deleted Melmetal's
  floor). Bakes now see one vintage via the chain's data-cache pin
  (88bec7b; the direct-launch gap is the TTL-keeper item in the Cramorant
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
  the BP-3 fix `fa1bd1d`, which strictly reduced the mismatch.)
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
  (`deep_dive_matchup_clusters.py:649-652`) is a FOURTH convention
  (argsort over the 2dp display arrays); it now diverges from the
  unified three post-`8c1f98e`. Fixing changes rendered cluster
  "SP #a-#b" labels.

## Top-N opponent filter + limited-cup dives -- Phase 3

Phases 1-2 shipped (CHANGELOG 2026-07-03). Open: Phase 3 -- more cups,
legality-filter eval, app-side cup toggles (needs a coordinated
`default_thresholds.toml` format axis), mega engine. Plan:
`docs/topn_cup_filter_plan.md`.

## Cache GC: prune all namespaces + dive-script opt-in prompt

Make `scripts/gc_cache.py` able to prune **every** cache namespace, and wire a
prune option into the dive scripts wherever caches get created.

- **GC coverage.** Today only `sweep/` has vintage-aware pruning (gamemaster in
  `meta.json`); `slayer/` and `iv_envelope/` are report-only because they bake
  gamemaster+engine into opaque filename hashes with no readable vintage. Give
  those two a readable vintage (sidecar or meta file at write time) so GC can
  apply the same N-1 retention to them. (`iv_envelope/` may be retired instead
  once the ML path moves onto the sweep cache — cache-rework Phase 6.)
- **Dive-script opt-in.** Wherever a cache is created (`deep_dive.py`,
  `deep_dive_slayer.py`, the IV-envelope/ML path, sweep), add a prune option
  that **defaults to "don't prune."** When the run is a *full* dive of a whole
  league (UL / GL / ML), **ask Michael whether to prune** before/after the dive
  rather than silently keeping or silently deleting.
- Retention target stays N-1 (current gamemaster + 1 prior), matching the
  existing `gc_cache.py --keep-vintages 2` default.

## NEXT SESSION (queued 2026-06-21): gobattlekit owned-mon breakdown screen

Build the "which of my mons should I build?" breakdown in the gobattlekit iOS
app — the same feature already live on the website (the deep-dive paste-box
"Gives up vs #1" column) and as a Python CLI (`scripts/owned_breakdown.py` —
one of three sibling metrics that deliberately do NOT match each other; see
its header, corrected in `c911eff`).

- **Scope (decided):** GL + UL, the species we've already dived (zero new sims,
  smallest mobile bundle).
- **Architecture:** EXTRACT per-IV dropped-vs-rank-1 from existing dive grids
  (no re-sim) — the dive embeds the full 4096-IV score grid. gobattlekit has NO
  battle engine and must not get one (lean iOS build); it consumes pre-baked
  data + recomputes only the analytic layer on-device.
- **One remaining build step** (step 1, the bitmask exporter, shipped
  2026-06-29 `c1ea231` -- details in TODO_archive):
  2. **Toga screen** modeled on `gobattlekit/src/gobattlekit/screens/user_iv_checker.py`,
     reading the baked artifact (bundle like `default_thresholds.toml` via
     `tools/threshold_export/`); resolve owned mons through their evolution line;
     **add parity vectors** to gobattlekit `tests/test_parity_vectors.py`.
- **Full plan + findings + file:line pointers:** `docs/owned_mon_breakdown_plan.md`.
  Memory: `project_owned_mon_breakdown.md`. Convention note: web + iOS use the
  dive's opponent IVs; the Python CLI uses 15/15/15 (they differ slightly).

## Old/new mechanics user toggle (POST-SHIP)

*(2026-06-26, Michael)* Post-ship idea, flagged so it is not lost; do NOT
pre-ship or design heavily yet. If the site/app gets traction, P!P-series /
Worlds competitors may want it for prep, and **Worlds runs on the OLD battle
mechanics**. So expose a user-facing toggle between old and new mechanics on
the dive site.

Light design notes (not yet designed):
- Preference storage: cookies (never used here) vs radio buttons vs a query
  param. Look at what PvPoke does for its "Preview next season" version as
  prior art before picking.
- Cache: the cache-rework (shipped 2026-06-27, CHANGELOG) does NOT key on the
  turn model, so a `new`-mechanics dive force-disables the sweep cache today.
  Adding a real toggle means keying the cache by mechanics so old-vs-new
  results cache separately while our engine stays current — extend
  `sweep_cache`/`migrate_cache` rather than re-deriving them.

## Morpeko dive is missing its form-change note

- **A Morpeko dive must carry a form-change note at the top** (Full Belly
  <-> Hangry toggles AURA_WHEEL Electric/Dark after each charged move; same
  `_FORM_CHANGE_NOTES` mechanism, `scripts/deep_dive.py`). The trigger has
  fired: a Morpeko (Full Belly) GL dive exists locally in
  `userdata/website/morpeko-full-belly-great-league/` (rendered 2026-09-27)
  WITHOUT the note (`_FORM_CHANGE_NOTES` has no Morpeko entry). Add the
  entry and re-render from replay; publish-blocking if the page is live.

## Limited-availability mons: real IV floors for ML sweeps (PARALLEL, post-ship)

Resolved slice (floor-10 resweeps, enumeration research, shadow-legendary
gap) recorded in TODO_archive + `docs/reviews/2026-07-03_limited_availability_iv_floors.md`.
STILL OPEN (both need Michael, both optional/low): (a) OPTIONAL belt-and-
suspenders -- evaluate Dialga/Latias/Lugia/Reshiram (Shadow) down to 6/6/6 in
their ML guides (the four Giovanni-primary legendaries whose grindability is
only medium-confidence; worst-case floor is a bounded 6/6/6); (b) re-run the
audit when Eternatus returns (Niantic announced it will).

## Pre-ship arc — residual open polish

The 2026-04/06 pre-ship arc shipped (site published 2026-06-07; see
CHANGELOG.md). The minor polish residue:

- **Favicon.** pogodives.com has never had one (the 2026-08-27 publish
  removed DreamHost's 0-byte placeholder `favicon.ico`/`favicon.gif`,
  provisioned 08-24 -- we never made a real one). To add: drop
  `favicon.ico` (or PNG + `<link rel="icon">` in the templates) into
  `userdata/website/`; it then rides every publish. Candidate art: the
  Cramorant HOME sprite / a dive-flag glyph.

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
  per `docs/reference_deep_dives/ryanswag/STYLE_ANALYSIS.md`.
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
  rows. See memory `project_form_change_pool_expansion_parked.md`.

## Deferred cleanup: backwards-compatibility removal pass

- **parse_types lazy alias in data.py** (`data.py:637` `__getattr__`):
  gobattlekit's `tools/threshold_export/export_thresholds.py:55` still
  imports it from `gopvpsim.data`. Unblocked (Worlds 2026 is over): switch
  that import to `gopvpsim.moves`, re-pin
  `tests/test_gobattlekit_api_pin.py`, delete the alias.
- **Gobattlekit threshold schema compatibility** in
  `gopvpsim.user_collection.check_thresholds` (and `as_legacy_dict` in
  thresholds.py) — once gobattlekit has actually migrated to use the
  shared module and we've confirmed it works, we may want to simplify
  the dict schema or unify with pogo-simulator's TOML anchor schema.
  But not before gobattlekit's migration lands. **The gobattlekit
  threshold pipeline actively consumes both as of 2026-06-12 — do not
  touch without coordinating.**

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

* **Speed test** -- compare our speed vs the PvPoke JS code, look for
  ways we can speed ours up. *(Partly addressed 2026-06-10: holistic
  perf review found and fixed a 2.0x engine regression dating to the
  2026-04-15 correctness arc — see DEVELOPER_NOTES "Performance
  baseline" for the regression gate and `docs/perf/` for the writeup.
  The vs-PvPoke-JS throughput comparison itself remains open.)*

## Shared user_collection module — Option-2 migration prep

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

## Tests to add

* **pvpoke.com/battle round-trip for the iv-tech no-bait oracles**
  (Tinkaton 0-1 vs Shadow Altaria, Spidops 1s vs Altaria): click through
  the key cells on the site when convenient (human step).

## Refactoring

* **Pain points captured during real debugging** — see memory file
  `project_post_ship_cleanup_pain_points.md` (silent early-returns
  with no logging, no replay-from-saved-state mode, hardcoded magic
  numbers assuming `nS=9`, parallel call-site duplication,
  free-form-string opponent identity, `data_obj`-as-mutable-bag,
  `id()`-keyed caches). Specific friction encountered while
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

## Moveset / variant comparison tool

* **compare_loadouts N-way verdict:** N=3/N=4 rendering shipped (53ade3c,
  2026-04-22: all-N-in-row matchup table); the verdict line still lists
  per-loadout win rates without an N-way ranking. Stay loadout-list-keyed;
  N=4 ceiling (parse_spec hard-caps it).

## User-facing documentation (Reader's Guides)

- **Review the IV Robustness guide** (`guides/iv-robustness/`, at
  `authorship=ai` -> promote to `both`).
- **Glossary gap:** `docs/concepts.md` does not define the envelope-crosser
  vocabulary the dives print (`elevated-band-crosser` /
  `depressed-band-crosser`, `deep_dive_rendering.py:~1551`); found closing
  the Shadow Sableye GL bands reminder (CHANGELOG 2026-09-22).
- **Round-3 screenshots** if/when reader confusion surfaces a
  specific gap (round-1 + round-2 screenshots shipped via `32fae84`
  and `e449b38`).
- **Add topics** beyond the five shipped — Michael asked that the
  topic list be a conversation at the start of the task, not a
  fixed scope. Plan a session to (a) add topics surfaced by
  an HSH Discord member / new readers, (b) reorder by current reader
  confusion, (c) decide whether related topics merge.

The IV Flavor Guide write-up is owed to an HSH Discord member per
`project_tinkaton_expert_writeup_commitment.md` (NB: that memory file
lives in the retired pogo-simulator project's memory dir,
`~/.claude/projects/-Users-mglerner-coding-MGLPoGo-pogo-simulator/memory/`,
not this project's) — the guide sits at `both` today; promoting it to
`expert` is the closing of that commitment.

## Low priority

* **ML guide "what do I get by best-buddying these?" view** — the "All
  cases" IV-compare view (shipped 2026-06-28, `b494b28`) hides
  best-buddy-conditional flips by default and badges their count
  ("N best-buddy flips hidden"). A natural follow-up is a dedicated
  summary that answers, for the user's candidate spreads, *what
  matchups best-buddying unlocks/loses* — e.g. "best-buddy 15/15/14 to
  win Solgaleo 2-1 + Kyurem 2-2; 15/14/15 gains nothing." The data is
  already there (the alt grids / sibling quadrant rows); this is a
  rendering/summarization feature, not new sim. Deferred 2026-06-28 by
  Michael ("don't want to engineer that now").

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support. When this
  lands, honor `reset_on_switch`: Morpeko must re-enter in Full Belly on
  every switch-in (confirmed in-game 2026-06-06; see DEVELOPER_NOTES §8).
  Also port the MATCH-level 240 s clock (Michael, 2026-06-11): the real
  game's timer spans the whole 3v3, charged-move animations consume it,
  and games are genuinely won on time — see DEVELOPER_NOTES "Battle
  timeout" divergence entry for PvPoke's clock semantics to mirror.

## Turn-system / Aegislash residue

History: CHANGELOG 2026-09-02..03, 2026-09-09..10, 2026-09-27/28.

- **Aegislash Blade-atk fix (CHANGELOG 2026-09-27, 2026-09-27/28): publish
  pending.** The GL re-dive is local; published GL pages still carry the old
  Aegislash numbers + G-caveat stamp until the next push (Michael's call).
- **F1 (decide):** farm-gate ordering vs PvPoke's farm-down early return
  (touched set: Aegislash either side). F2a/F3/F4 closed (CHANGELOG
  2026-09-28).
- **Aegislash 1080-sample residue (investigation, parked):**
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
- **Threshold-TOML prose (3b(c) of the 2026-09-09 re-vet):** 182
  descriptions cited a decimal number in prose; each one whose underlying
  threshold moved is now a wrong published sentence. d363b1d has since
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

## Backlog (someday / maybe)

Long-tail design notes, research reproductions and the UI wishlist live in
`docs/TODO_backlog.md`; finished work in `CHANGELOG.md`.
