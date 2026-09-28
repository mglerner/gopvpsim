<!-- TODO.md is a LIVE BACKLOG, not an append-only chronological log. Keep it
short: completed/shipped work moves to CHANGELOG.md (root-cause writeups,
dates, SHAs) or docs/TODO_archive.md (verbatim session batches); only OPEN
items and forward-looking design notes live here. When you finish an item,
delete its bullet or move the writeup out -- do not leave a 'DONE/RESOLVED'
narrative inline. This convention was set 2026-06-27 after the file hit ~1980
lines of mostly-completed chronological batches. -->

## OPEN: Bake speed (2026-09-25 scout)

Plan of record, with file:line evidence and the verified attribution of the
2026-09-20 chain's 37.7 h: `docs/perf/2026-09-25_bake_attribution_and_cruft_scout.md`.
More than half of that bake ran on one core of 18 (the two render passes
alone were 12.4 h). Ranked options, all **MERGED 2026-09-25** (R1-R6; plus the sweep-side
memo ea32bd9 on 09-27); none touches an engine-hashed file:

- R1 -- memoize the rank-1 `iv_rank` lookup render-side (`_opp_link_data`,
  per Michael's Q2 ruling; ~1.7 h/bake).
- R2 -- `aggregate_flips_by_anchor`: compute once per render pass (the
  narrative and analysis call it with identical inputs), then vectorize
  (~5.9-7.9 h/bake).
- R3 -- skip the second render pass on no-op best-buddy dives (~4.6 h/bake;
  drops the L51 `<template>` on those pages, Michael's Q3 go).
- R4 -- `find_matchup_boundaries` once per (mode, sweep) per pass (~1.2 h).
- R5 -- run the four ship gates concurrently (~470 s per roster run).
- R6 -- attribution guards: flag a system sleep inside the bake window, a
  sleep bucket in `bake_timing_report.py`, log all-miss sweeps (`0/n`).

Every render change ships behind the `scripts/replay_render_diff.py`
byte-diff. Measured on the 2026-09-26/27 bake: 2.01x awake, 2.76x
single-core (docs/perf/... 'Measured'; CHANGELOG 2026-09-26/27). Not ranked: `--jobs N` dive overlap (the "parallelize the dive
step" plan below, re-scoped 2026-09-27 for the measured 4.9-11.6 GB peak RSS
per render).

**Storage and cache, DONE 2026-09-25** (commands and counts in the doc's
"Results" section): the two pre-Aegislash snapshots deleted (~46 GB), both
signature migrations applied (sweep 239,091 blessed / 43,077 unlinked;
slayer 150 / 0), the 153,376 legacy-mechanics `515a0a95171b` columns GC'd
(46 GB), the 99 legacy slayer entries and 258 superseded replay blobs (9.5
GB) removed. Disk 752 -> 650 GiB used. Every remaining sweep column is at
engine d78c67fd06a7 / gamemaster 6d6e9a7bc32d, so the "apply the migrations
before the next engine bump" gate is satisfied. Undecided: the 12
test-pinned replay blobs already missing from disk (re-pin or drop; the
tests skip on them today).

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

The signature-dedup exactness fix (a4ca14e), its migrations (b6e369a,
applied 2026-09-25) and the 2026-09-26/27 bake + 2026-09-27 publish are done.
Still open: no re-run of the statfx lab's plain-PvPoke cross-check against
the 09-26/27 tensors is recorded -- run it once (expect 0 of 165 class pages
mismatching; it was 25 of 165 on the 9ac12a2754a1 bake) to close the loop.

## Thievul CD -- residue (shipped record: CHANGELOG 2026-08-15/16 + TODO_archive)

- MICHAEL: reply to u/LeansCenter on the r/TheSilphArena launch thread
  (as u/SpaceBearAI; open since 2026-08-15). Drafted bullets: 44W-44L
  -> 62W-25L at 1-1/rank-1 IVs/88-mon pool; IW+PR beats PvPoke's
  NS+IW default by ~14 wins; PvPoke overall GL rank 122 -> 41.
  Context: docs/thievul_cd_plan.md:85-109. Their post-rebalance
  IV-reshuffle question becomes actionable when the ~2-week rebalance
  lands.
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

The 2026-09-10..27 narrative (rebalance re-verify, deep re-verification
campaign, stale-article audit, sheet v6 -> v7, certification + publish
guard) is closed and condensed in CHANGELOG. What stays here is the standing
runbook and the genuinely open items.

**Standing runbook after every bake that touches Cramorant** (post-bake
verification last DONE 2026-09-27, sheet v7; the site published 2026-09-27):

    python scripts/cramorant_certify.py --league both --selftest 5 --out \
        userdata/certify/cramorant_record.json
    python scripts/render_pogodives_strategy_article.py --out <scratch>   # rehearse
    python scripts/render_pogodives_strategy_article.py
    python scripts/cramorant_certify.py --check-record userdata/certify/cramorant_record.json

`publish_website.sh` runs the last check itself and refuses to publish a
rendered Cramorant page that is missing from, or differs from, the record.

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
- **Jumpluff / Kingdra at 0v1 (sheet v7's accepted cost, CHANGELOG
  2026-09-27).** v7's `surf_gate_dpe` 2.25 excludes the two-type-step ratios
  (~2.65-2.75) that let the (0,1) tier throw a resisted Surf into Araquanid;
  Jumpluff and Kingdra sit in the same ratio band, so they now fall back to
  plain (about -165 rating on fights Cramorant loses anyway, 0 flips; page
  mean +12.5 -> +10.5). Accept as documented, or look for a discriminator
  that separates them from Araquanid (Mirror Coat) -- a new campaign, not a
  retune.
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
- **PvPoke Reports 8 and 9 -- drafted, NOT FILED**
  (`docs/pvpoke_bug_reports.md`). Report 9 (`hasActed` survives
  `Pokemon.reset()`; Michael 2026-09-12: "make report 9 a TODO for later";
  standalone copy `~/coding/reports/pvpoke-report9-hasacted-2026-09-15.html`)
  plausibly also explains Report 3's unresolved 429-vs-510. Report 8 = the
  two `move.moveID` typos (the draft cites ActionLogic.js:368 and :1239;
  on the local pvpoke checkout, 78b1e66db, they sit at :368 and :1255 --
  the latter makes defenders never shield a lethal Cramorant Dive). Both
  bugs are still present there. Check the
  tracker for duplicates first; if Report 9 is fixed upstream, the Lapras
  page-level pin (446) in `tests/test_pvpoke_sandbox.py` and the article
  test's run1==run2 gate start failing -- delete the pin, keep the gate.

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
oracle cell ever drifts. (b) The opponent-pool question -- whether
Cramorant (GL rank 13) enters `gl_top50_plus_cs.txt` / `ul_top60.txt`
as an OPPONENT for other species' dives -- is a Michael curation call;
until then no shipped dive sims against it.

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
- **Before ANY Worlds re-render:** re-pin the gamemaster the pages were baked
  at (`git -C ../pvpoke show f60a41199:src/data/gamemaster.json >
  ~/Documents/gopvpsim_cache/gamemaster.json`), restore the live blob after;
  the render path reads live gamemaster/rankings while scores come frozen
  from the blob. `WORLDS_RERENDER=1` is the opt-in in `publish_website.sh`;
  `verify_worlds.py` is out of the ship-gate roster (5985777) and runs by
  hand only. Legacy mechanics are gone (4b6342b), so a 2027 bake is a
  new-mechanics bake.
- **Standing Worlds bake/publish rules (carry into any revival):** publish
  only on Michael's explicit per-instance go; long bakes detached and
  run-to-completion; Worlds modules never touch the sweep cache (pinned by
  `tests/test_worlds_bake_guards.py`); no `*_great.toml` from a Worlds bake.

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

Michael, 2026-08-31: once the full move-update data is live, **every
article gets a per-article regen / no-regen decision** -- we do not
blanket-regenerate. The gate is meta relevance in **open + cups**: an
article about a species that is far out of the meta on both does not
earn a regen, however stale its numbers.

The surface (62 rendered dirs under `userdata/website/articles/`):

- **61 `*-ml-iv-guide`** dirs, driven by `opponent_pools/master_top60.txt`
  (`run_iv_guides.py`). ML is where Lugia's new Earth Power lands, so
  this is not a low-churn surface.
- **`cramorant-pogodives-strategy`** -- couples to the fitted-constant
  re-verification already in `docs/rebalance_checklist.md` section A
  step 3; don't regen it before that passes.
- **`articles/oinkologne-cd-2026-05.toml`** -- still all PLACEHOLDER
  bodies, so nothing is shipped and nothing is wrong today. Worth
  knowing before anyone picks it up: its comparison axis is Mud Slap
  vs Tackle/Take Down, and **Take Down goes 5->14 power with increased
  energy gain**, which can invert the article's thesis. Decide
  regen-vs-drop on the meta test above before spending an authoring
  session on it.

DECIDED (Michael, 2026-08-31) -- **no staleness markers; the live site
is centered on current live stuff.** A no-regen article is REMOVED from
the site rather than left up with a caveat. This satisfies the
never-ship-unflagged-known-wrong rule by not shipping the wrong page at
all, which is stronger than flagging it.

TOOLING READY (built 2026-08-31, ahead of the rebalance):
`scripts/archive_article.py --slug <slug> --vintage YYYY-MM-DD [--stamp
<hash>]` copies a live article to a dated snapshot slug and marks the
copy; the index renders snapshots in a collapsed Archive block. Design
+ rationale: `docs/article_archive_plan.md`. `--vintage` is deliberately
REQUIRED -- archiving happens after the new data lands, so the live
gamemaster stamp at that moment is the NEW one and defaulting to it
would mislabel the snapshot.

Mechanism if you instead DELETE outright: remove the rendered dir from
`userdata/website/articles/`, then re-run `build_website_index.py`.
The index discovers articles by scanning
`userdata/website/articles/*/meta.toml`
(`build_website_index.py:49,1007`), so the card disappears on its own,
and `publish_website.sh` rsyncs with `--delete` (:105), so the live
page goes with it. No hand-editing of index.html.

If a removed article is worth keeping, it archives in the **git repo**,
not on the site. Wrinkle to solve when it first comes up: `userdata/`
is gitignored (`.gitignore:43`), so archiving a *rendered* page needs a
tracked path -- the cheap alternative is to keep only the source
(`articles/*.toml` is already tracked) and re-render from it if ever
wanted.

Still open, Michael's: what counts as "in the meta" for the cups half,
given the season ships eight of them (Willpower, Retro, Mega Color,
Little, Fantasy, Halloween, GO LAIC, Mega Catch).

## Site lifecycle policy (Michael, 2026-09-02)

Standing shape, seasons repeat:

1. A new season is announced.
2. Things get added to the site progressively through the season
   (cups, event/CD articles, condensed-meta surfaces).
3. **At the start of the next season, ALL of it comes down**, and the
   new season's surfaces get added as needed. Rinse, repeat.

The live site is centered on current live content; nothing is left up
carrying a staleness caveat (see "Article regen triage"). Retired
surfaces are re-renderable from their replay blobs, and articles worth
keeping archive as dated snapshots via
`scripts/archive_article.py` (docs/article_archive_plan.md).

**What a season-start bake actually covers.** The chain
(`overnight_redive.sh`) already does more than "GL/UL/ML dives":

- `run_website_dives.py` -- 100 dive entries (GL + UL + ML)
- `run_iv_guides.py` over `master_top60` -- 61 ML IV guides, a separate
  multi-hour job and ~60% of the article surface
- 4 comparison renders + the GL matchup web (need sims)
- Reader's guides, index rebuild, ship gates (render-only)

Opponent-pool freshness is a code-level guard since e8ac919 (2026-09-02):
`run_website_dives.py` hard-fails on stale pools (`--allow-stale-pools`
overrides). Record: CHANGELOG 2026-09-02.

## NEXT BAKE: mirror population as opponent columns (Michael, 2026-09-22)

**BUILT 2026-09-28 (merged to main; bake ON, paragraph render-gated OFF).**
The prerequisite below is done; what is left is Michael's review of item
(g) and the wording, then the next bake populates the blobs and a re-render
opens the gate.

- Bake side: `scripts/deep_dive_lib/mirror_population.py`, called from
  `deep_dive.main` after every other sweep and before the blob is dumped;
  `--mirror-population` / `--no-mirror-population`, default ON (skipped
  under `--no-replay-dump`, which has no reader for it). Schema in the
  module docstring, stored as `state['mirror_population']` (version 1).
  `iv_sweep` gained an opt-in `opp_ivs=` (explicit per-opponent IVs); column
  keying and computation are unchanged, CACHE_VERSION unchanged.
- Cost, measured 2026-09-28 on Melmetal GL (5 movesets, a machine at load
  ~25 shared with other agents): 31 members, 224 column-sweeps (about 22
  columns x 2 bait modes x 5 movesets), 39-47 s per dive including ~10 s of
  build selection, against a ~4 min budget. The 2026-09-20 estimate of
  ~0.7 s per column-sweep was ~4x high: one `iv_sweep` call covers all of
  an arm's columns.
- Page side: `deep_dive_builds.population_facts` +
  `deep_dive_which_build.population_sentences`; the "The mirror" paragraph
  reads the population where the blob has one and falls back to the cohort
  paragraph otherwise (old blobs render byte-identical; harness-verified).
- Hash impact: NONE on the engine hash (45cf73a2d23d before and after; no
  engine-hashed file touched). The BLOB schema changed, so a page shows the
  population only after a re-dive; a warm re-dive re-sims just the
  population's columns (~40-50 s per 5-moveset dive, cold).
- Still open: (a) wording (Michael); (b) one scenario (the 1v1) is printed,
  all nine are in the facts; (c) league cap only -- a best-buddy (L51)
  section keeps the cohort paragraph; (d) the plot's mirror trace and its
  caption still read the cohort; (e) the thresholds-TOML override list
  (candidate 3) stays deferred; (f) the population paragraph is NOT gated on
  the mirror being a decision cell (the cohort paragraph is), so it appears
  on arms that had no mirror paragraph before (Melmetal GL arms 1-2) --
  Michael to confirm; (g) first real numbers (Melmetal GL 09-27 blob): most
  builds' median member beats 0-5% of the rank list in the 1v1 from the
  focal's seat (the column always baits; no antisymmetry), so the 1v1
  mirror reads as lost for nearly everyone -- worth a look before shipping.
  **Probed 2026-09-28, and it is the seat convention, not the spreads:** a
  spread against ITSELF (same IVs and level both seats) scores 500 in the
  1v1 on the Dynamic Punch arm but 363-404 on the Hyper Beam, Rock Slide and
  Thunderbolt arms, and the builds' own members score 248-270 against
  themselves (the 0v0 self-mirror is 342-390 there too). The optimizing row
  loses to the always-baiting column with identical stats, so "Build 1 beats
  0%" is an AI-convention statement a reader would take for an IV one. The
  paragraph is therefore behind `deep_dive_which_build.RENDER_MIRROR_POPULATION
  = False` (pinned by `test_render_gate_keeps_the_cohort_paragraph_until_reviewed`);
  the bake stays ON so the next bake stores the data, and opening the gate
  is a re-render, not a re-dive. **Michael's call** on the framing: print
  the self-mirror baseline beside every count, score both seats and print
  the symmetric mean, sweep the column under pvpoke_dp as well (doubles the
  ~40 s), or drop the 1v1 sentence for the CMP cuts alone (which are
  seat-free).

**Did NOT ride the 2026-09-26/27 bake** (decision 2026-09-26: timing bake
first -- measure the sped-up render layer on its own; this note is the only
written record of that call). Verified
2026-09-27: no population-sweep code has landed on main since c2bd1e9
(09-22), so the prerequisite below is still unbuilt and still gates the
next bake that carries it.

**Clones cleaned up 2026-09-22:** the seeded-lattice and mirror-proto
prototypes now live as branches `experiment/seeded-lattice-2026-09-17` and
`experiment/mirror-proto-2026-09-21` in this repo (local only); the three
clone directories are deleted.

**Status 2026-09-22 (Michael): WAIT.** Not worth its own bake; it rides the
next bake that happens for another reason. PRE-LAUNCH PREREQUISITE for that
bake: build the population sweep + the block that reads it FIRST (one agent
round, ~half a day, additive columns, no hash bump), so the bake carries it
for free. The gamemaster_subset narrowing (sim-read fields only, prevents
UI-only PvPoke churn from cooling the cache) also rides that bake ONLY IF it
is cold for its own reasons; never force a cold bake for it.

Decision: "the mirrors I will meet" = (1) PvPoke's rank-ordered IV list for
the focal, top N (bulk-first by construction), PLUS (2) the page's own
builds -- each named build's most-winning member and SP1 (what our readers
will build once the page exists). Labelled separately on the page. The
Nash mirror-slayer cohort is NOT this (prototype 2026-09-21,
`userdata/analysis/2026-09-21_mirror_proto/report.md`: attack-first on
Melmetal GL, bimodal on Shadow Sableye, never converged); it stays as the
Slayer Builds input. The render-only CMP line against that cohort ships
first (branch `mirror-line`) and is replaced by these numbers when the
bake lands.

Michael, 2026-09-22 (after the four previews on branch `mirror-line`,
d66a78d): the cohort version is NOT rendered site-wide. Its content
reduces to "pick the highest attack you have inside the build you chose"
plus what that attack buys (Melmetal GL and Azumarill: nothing; Melmetal
UL: the fork clears both cuts with every member). DONE on `mirror-line`:
the block is two sentences under the builds table, and everything behind
it is kept and still pinned for the population version to reuse --
mirror_surface, the decision cells / cohort-rate / Spearman facts (now
computed and NOT rendered), the trace, the glossary terms. The population
version earns the block because it compares ACROSS builds ("Build 3 wins
the 1v1 mirror against 40% of common Melmetals; Build 2 against 85% and
gives up these four matchups").

Shape (bake-side, changes the blob schema -- own bake, own hash bump):
- After the main sweeps and BEFORE render, compute builds
  (`deep_dive_builds.compute_builds`, ~2 s) so (2) is known; then sweep the
  focal grid against the mirror population as extra opponent columns: same
  species+form as the focal (and the other shadow form when it is in the
  pool), explicit IVs, level = under-cap max, default moveset; sweep cache
  keys columns on opponent IVs already (`sweep_cache.column_key_fields`),
  so they warm like any other column.
- Store under `state['mirror_population']`: the member list (source tag:
  'pvpoke_rank' / 'build:<role>' / 'sp1', IVs, stats), and per-member
  per-scenario scores (4096 x 9 x M), both bait modes; opponent-IV modes do
  not apply (the IVs are the point).
- Size cap: N = 20 from the rank list + up to ~6 build members => ~26
  columns x 2 bait sweeps x movesets. Measured 2026-09-20: ~0.7 s per
  column-sweep, so ~3 min per 5-moveset dive, ~6 h across the corpus,
  warm afterwards.
- Page: the "The mirror" block (from `mirror-line`) reads this instead of
  the cohort: per scenario, the share of the population each build's
  members beat (median, min); the CMP quantiles (a_50 / a_75, strict
  engine rule) from the population's attack; "Build 2 beats 83% of common
  Melmetal builds in the 1v1 and wins CMP against 71%". Optional: a
  thresholds-TOML override list for species where Michael knows what the
  community runs (candidate 3, deferred).
- Guards: the population must include SP1 and the rank list's #1; a test
  that the per-scenario mirror-vs-population numbers reproduce from the
  stored scores; the vintage stamp covers it.

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

## PLAN ONLY: parallelize the dive step (re-scoped 2026-09-27: <=6.9 h ceiling, memory-bound)

**PLAN ONLY -- do not implement without Michael's go** (his call 2026-09-12:
"make a plan for it, but don't implement"). Was "HIGH PRIORITY, ~13h/bake";
the 2026-09-25 render speedups (R1-R4, R3, the sweep-side rank-1 memo
ea32bd9) shrank the serial tail this plan targets, so the prize is now
smaller and the memory risk is the gating question.

### Measured, on the 2026-09-26/27 bake (current numbers)

`docs/perf/2026-09-25_bake_attribution_and_cruft_scout.md` "Measured" (chain
`overnight_20260926_102139.log`, 136 dives, pmset sleep windows subtracted):
dive step **17.9 h awake**, of which the single-core render/analysis bucket is
**6.9 h -> serial share 39%** (6.9 / 17.9); pool sims 11.0 h. The
2026-09-12 version of this section reported 13.4 h serial / 32% of a 41.8 h
step, from the old marker-inheriting report, which undercounted serial time
(on the 09-20 bake it read 15.5 h serial vs 18.6 h by per-dive attribution,
per 1f9ba3c) -- compare absolute hours, not shares. Absolute serial time fell
from 19.0 h (09-20, same 136 dives) to 6.9 h, and the sweep-side memo
(ea32bd9, merged after that bake, not yet in a measured bake) should take
roughly another 2-2.4 h off it. `run_website_dives.py:304` still launches
each dive with a blocking `subprocess.run` in a loop -- strictly serial, no
`--jobs` -- so during those hours 17 of 18 cores idle.

The 2026-09-12 report caveats are fixed: GL + UL rows of one species no
longer merge (3c299aa keys on species + league), and 1f9ba3c attributes
from the per-dive ms logs with a sleep bucket instead of inheriting chain-log
markers.

### The prize

Overlapping 2-3 dives fills each other's render tails. Ceiling is the serial
bucket: 6.9 h measured; ~4.5-5 h once the ea32bd9 memo lands in a bake
(projection, not measured), so roughly 13 h instead of 17.9 h awake --
about a third of the "~13 h" this section claimed on 2026-09-12.

### The risk: memory, not cores

The 2026-09-12 plan said "0.8 GB per dive process, 64 GB machine". That is
contradicted by two measurements: the 2026-09-25 scout saw 2.5-8.5 GB RSS per
dive's render state, and `scripts/replay_render_diff.py`'s harness measured
4.9-11.6 GB **peak RSS per render** (tinkaton_great 4.9, melmetal_great 4.9,
guzzlord_great 5.5, jellicent_ultra 6.3, cramorant_ultra 11.6 GB; measured
at `--jobs 5` on a shared machine, 2026-09-25). Three concurrent
Cramorant-sized render tails would reach ~35 GB before the sweep pools' own
footprint, on a 64 GB machine. Needs a measured concurrent-RSS probe and a
lens-grid review (`docs/predive_checklist.md`, resource/concurrency lens)
before any `--jobs` default above 1.

### Implementation plan

1. **Per-dive log capture (do this FIRST, it is load-bearing).** Dive stdout is
   currently inherited straight into the chain log. Concurrent dives would
   interleave into mush AND break `chain_status.py`, which parses that log's
   `[N/M] slug` banners and `Done in X.X min` markers. Give each dive its own
   file, then have the parent emit the banner lines itself.
2. **Split `--reserve-cpus` across workers.** The chain passes
   `--reserve-cpus 0` and `deep_dive_lib/sweep.py:833` computes
   `min(cpu_count() - reserve, len(chunks))`, so each dive asks for all 18.
   Three concurrent dives would ask for 54. Divide the budget by the job count
   (18 cores / 3 jobs -> `--reserve-cpus 12` each), and note the render tail
   uses ONE core regardless, so the ideal is oversubscribing slightly.
3. **Add `--jobs N` to `run_website_dives.py`**, defaulting to 1 so nothing
   changes until asked for. A small process pool over the DIVES list.
4. **Verify cache safety before trusting it.** `put_column`'s sidecar write is
   atomic (tmp + `os.replace`, `sweep_cache.py:208-215`) but the tmp filename
   is FIXED (`<name>.tmp`), so two writers to the SAME column collide.
   Concurrent dives have different focals -> different columns -> safe today.
   Confirm that still holds for the mirror-slayer and signature-dedup paths,
   which are the ones that write outside the plain focal column.
5. **Do NOT touch the ML guide tail.** `run_iv_guides.py --jobs 1` is serial ON
   PURPOSE -- it is the fix for the 2026-06-27 oversubscription bug, and its
   preflight hard-fails when `jobs x per-guide workers > cores`. Also pointless
   now: the whole ML tail measured **3.9 min** for 60 guides on 2026-09-12
   (48 profiles x 60 opponents at `DEFAULT_IV_FLOOR = 12`, vs 4096 IVs x 76
   opponents x 9 scenarios for a GL dive); 204 s on the 2026-09-26/27 bake.
6. **Memory IS the constraint** (see "The risk" above): cap concurrency by
   measured peak RSS, not core count; the old "0.8 GB per dive" figure is
   wrong by 3-15x.

### Measurement pitfall

Counting workers by grepping `deep_dive.py` in `ps` output MISSES the forked
pool children and reports `procs=1 cpu%=0` during sweeps -- i.e. it makes a
saturated machine look idle. Count the process tree by ppid. (This produced a
wrong reading on 2026-09-10 that had to be retracted.)

## Re-dive runbook

**Twilight Trails (2026-09-08) one-shot gate:** before any
`migrate_cache.py --apply`, hardlink-snapshot the sweep cache --
`cp -al ~/.cache/gopvpsim/sweep ~/.cache/gopvpsim/sweep_pre_twilight`.
The migration unlinks the `.npz` score planes of the affected columns,
which ARE the pre-rebalance per-spread scores a before/after comparison
needs. Full rationale + the rest of the sequence:
`docs/rebalance_checklist.md` section A step 1. Baseline vintage pin
(pvpoke 46bd08a77 / stamp c431557dcc76): DEVELOPER_NOTES
"Pre-rebalance data vintage pin".

For the next cold re-dive: `docs/predive_checklist.md` is the STANDING
pre-cold-dive gate; run `overnight_redive.sh` and watch with
`scripts/chain_status.py --chain overnight`. (Last bake: **2026-08-06/08**,
the v8 entries-12+13 engine -- ALL GREEN, mixed-vintage recovery proven;
see CHANGELOG "2026-08-06/08". LID STAYS OPEN for the whole bake.)

A failed chain step that has since been diagnosed and fixed goes in
`docs/chain_resolutions.toml` (read by `verify_overnight.py` check [1/5]) --
do NOT edit `overnight_status.txt` or the chain log to force the gate green.

**Don't use `publish_website.sh` (dry run) to ask "is the site current?"** It
regenerates guides + `index.html` on every invocation, so it rewrites the files
it then compares by mtime; it always reports a ~18-path delta even when the
content is identical. Compare content instead (md5 vs the live URLs, or
`rsync --checksum`). Detail in CHANGELOG "2026-08-04".

## DRY review 2026-08-05: fully executed -- open residue only

The review (`docs/reviews/2026-08-05_dry_review.md`) is fully executed
and signed off (plotly shim accepted as-is 2026-08-08, overlay-hue
aliasing recorded as a decision in docs/palette_governance.md section
6); the record lives in CHANGELOG and the report's status header.

Standing reference: the report's "Do NOT do" section lists the
intentional duplicates and refuted claims -- check it before
re-reporting any DRY finding.

## Engine bug-hunt round 2 (2026-07-03): 16 confirmed findings need triage

`docs/reviews/2026-07-02_engine_bug_hunt_round2.md` — 1 HIGH, 7 medium,
8 low; 0 uncertain; all double-skeptic-verified. ("No shipped winner flips
in sampled cells" held for the hunt's own samples; the NB-1 bounding sweep
below later found one on a wider grid.)

**Still open:**
- **js-parity residue** (LOW): only the winsMirror branch inside the
  SHA-pinned `deep_dive_engine.js` region (~:1497-1511) still uses the
  literal "Gives up vs #1" header for a fourth metric (a mirror-cohort
  win-shortfall COUNT). Renaming costs a REGION_SHA256 re-stamp
  (`patch_dive_gives_up_column.py` + its pin test) -- fold into whatever
  next pays that re-stamp. (History: -1/-2/-4 + -5's honest-claim half
  fixed in the DRY arc; -3 fixed `8c1f98e`; -5's follow-on closed
  `c911eff`; BP-3 fixed `fa1bd1d`, and "BP-4" was a typo -- the round2
  report has no such finding.)

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

## Top-N opponent filter + limited-cup dives (planned 2026-07-02)

From Reddit launch-post feedback (u/LeansCenter): (a) evaluate a focal vs
only the top 10/20/50 meta opponents, (b) limited-cup dives (Sunshine Cup
etc.), separate/composable. Full plan with recon evidence, phasing, and the
open decisions (UI shape, cup pilot choice, rollout vehicle):
`docs/topn_cup_filter_plan.md`. Headlines: top-N is a client-side mask over
the already-embedded SCORES_GZ grid plus a bake-time `oppMetaRank` field and
an honesty banner over the full-pool baked sections; cups are a pool+rankings
feature (PvPoke publishes cup rankings; sweep cache warm-serves overlapping
columns; ~minutes per focal, not a re-bake).

**Phases 1-2 SHIPPED** (2026-07; CHANGELOG "2026-07-03" + TODO_archive).
**Phase 3 remains**: more cups, legality-filter eval, app-side cup
toggles, mega engine -- see the plan doc.

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

## Form-change "starts in alt form" dives + on-page descriptions (POST-PUBLISH)

*(2026-06-26, Michael)* Aegislash got fixed pre-launch (relabeled "Starts
Blade" + a top-of-page form-change note on both GL dives) because it was the
only form-change dive that read as confusing on the site. The rest is
deferred post-publish:

- **If a Morpeko dive is ever added, it must carry a form-change note at the
  top too** (Full Belly <-> Hangry toggles AURA_WHEEL Electric/Dark after
  each charged move). Same `_FORM_CHANGE_NOTES` mechanism.

## Limited-availability mons: real IV floors for ML sweeps (PARALLEL, post-ship)

*(2026-06-25, scratch_thoughts)* The ML IV-guide sweeps assume a 12/12/12 IV
floor (right for traded / grind-able species). But some mons you only get one
or two of in PoGo -- mostly mythicals (Marshadow, Hoopa, Zygarde) but NOT all
(Genesect is grind-able; Marshadow/Hoopa/Zygarde are not). Their real-world IV
floor is LOWER than 12/12/12, so the shipped ML guide can't evaluate a
legitimately owned spread (Michael's Marshadow is 11/13/11). Steps: (1)
enumerate which species are in the limited-availability category, (2) determine
each one's IRL IV floor (research-reward / quest-encounter IVs), (3) re-run the
ML sweep for any with a floor below 12/12/12. Independent of everything else --
fire as a PARALLEL task, ship whatever is done, re-ship the corrected guides
later (they finish after the UI decisions, or get rewritten during UI rework).
FLAG (never-ship-unflagged-known-wrong rule): until corrected, the limited-mon
ML guides ship with a floor that is wrong for them -- decide whether to add an
"assumes a 12/12/12 IV floor" caveat on those pages or ship unflagged.

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

- **R3 removal candidate.** Meta Coverage "Shield asymmetry
  dominates the extremes" explanatory paragraph — currently
  hidden; re-evaluate for removal post-ship if hide reads as
  bloat.

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

The S7 dead-code removal pass ran 2026-06-12 (see CHANGELOG). Still open
(deliberately NOT cut in S7):

- **parse_types lazy alias in data.py** — the 2026-08-10 relocation
  (engine-hash batch) moved `parse_types` to `moves.py`, but
  `../gobattlekit/tools/threshold_export/export_thresholds.py` imports
  it from `gopvpsim.data` by name (pinned by
  `tests/test_gobattlekit_api_pin.py`), so `data.py` keeps a lazy
  PEP-562 `__getattr__` alias. Post-Worlds: switch gobattlekit's import
  to `gopvpsim.moves`, re-pin the api-pin test, then delete the alias.
- **Gobattlekit threshold schema compatibility** in
  `gopvpsim.user_collection.check_thresholds` (and `as_legacy_dict` in
  thresholds.py) — once gobattlekit has actually migrated to use the
  shared module and we've confirmed it works, we may want to simplify
  the dict schema or unify with pogo-simulator's TOML anchor schema.
  But not before gobattlekit's migration lands. **The gobattlekit
  threshold pipeline actively consumes both as of 2026-06-12 — do not
  touch without coordinating.**
- **§I consolidations** (L11 gamemaster index, L15 unified
  invalidate_caches + effective-stats primitive, L6 league descriptor,
  D9 SweepConfig, D14 tier recompute, R11 shared scenario/color
  helpers, W8 slug parser, W10 badge renderer, T8 conftest deep_dive
  loader) — deferred from S7: D9/D14/T8 are seams the dedicated
  deep_dive.py split session will rework anyway, and the library
  consolidations (L6/L11/L15) are behavior-adjacent refactors, not
  deletions. Bundle them with the split session or their natural
  feature sessions.

## Battle simulator

* **PvPoke bug reports: FILED 2026-07-16** (CHANGELOG has the full
  writeup): pvpoke/pvpoke #378 Gyro Ball, #379 Morpeko, #380 dead
  pruning, #381 DPE overwrite, #382 bestChargedMove question. Residual
  opens:
  - **Report 5 (needsBoost retired-or-returning question) held back** —
    paste-ready in `docs/pvpoke_bug_reports.md`; if filed later, adjust
    the opener's "5 reports today" line and re-check
    `git log 10fd1a6e4..master -- src/js/` first.
  - **Engage with Matt's responses** as they come (volunteer,
    ~two-week cycles; don't re-ping).
  - **[investigation, unexplained] site-vs-headless 429/510
    discrepancy:** pvpoke.com single-battle UI gives 429 where headless
    runs of the byte-identical engine + gamemaster + inputs give 510
    (Aegislash SB-only vs Azumarill, the knife-edge "3 turns can flip"
    cells; reproduces at both April and July vintages, robust to
    bait/OMT/levels/IVs sweeps). Some UI-side battle setup input we
    haven't identified. Detail in `docs/pvpoke_bug_reports.md` header.
    Low priority, but don't cite harness battle ratings as
    site-reproducible in razor-thin cells until resolved.

* **Known PvPoke divergences** — DEVELOPER_NOTES "Known divergences"
  is the single source of truth (bestChargedMove per-turn recompute,
  the near-KO plan cluster, the battle-timeout guard). Re-audit
  anytime: `python scripts/audit_oracle_harness.py` (covers GL + UL;
  current baseline 207 cells = 172 exact + 35 documented; re-audited
  2026-08-06 A/B at origin/main vs the entry-13 batch, identical both
  sides -- the old 170+37 went stale at the hunt2 merge).

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

* **pvpoke.com/battle browser round-trip for the iv-tech oracles**
  (the one human step left from the old "No-bait oracle tests" entry;
  everything else DONE 2026-08-08, AFK churn `000ea87`+`cc64923`, both
  reference claims REPRODUCE with mechanisms read off battle timelines
  -- Tinkaton 0-1 vs Shadow Altaria bulkpoint at def=143.04, Spidops 1s
  vs Altaria Sky-Attack reduction -- and the "more forgiving win
  threshold" follow-up resolved: bait-ON wins for every spread are real,
  the reference's claim is specifically no-bait). Round-trip the key
  cells at pvpoke.com/battle when convenient.

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

* **Split `scripts/deep_dive.py` — steps 1-5 DONE (2026-08-06/08, DRY
  review entry 12; `7b665ac` + follow-ons).** 8032 -> **5077** lines. The
  landed layout differs from the original plan in *naming*, not in
  substance: the anchor-flip and slayer code went to the pre-existing
  2026-04-12 modules (`deep_dive_analysis.py`, `deep_dive_rendering.py`,
  `deep_dive_slayer.py`) rather than to new `deep_dive_lib/anchor_flips
  .py` / `deep_dive_lib/slayer.py`, and three modules nobody planned
  fell out of the cut (`opponents.py`, `score_pack.py`, `shields.py`).
  Landed homes: `build_iv_categories` deep_dive_lib/categories.py:23;
  `aggregate_flips_by_anchor` deep_dive_analysis.py:363 +
  `render_anchor_flip_bullets` deep_dive_rendering.py:1358 (deep_dive.py
  keeps alias shims for the tests); `iterative_slayer_discovery`
  deep_dive_slayer.py:245 with the spawn worker `slayer_iter_worker`
  :149 pinned by `tests/test_deep_dive_lib_workers.py:155` — do NOT
  "finish" targets 2-3 by creating the originally-planned filenames,
  that would churn working test-pinned code and break spawn-mode worker
  resolution; `categorize_slayers` was superseded, not moved (see
  `src/gopvpsim/anchors.py:858`); `generate_analysis_sections`
  deep_dive_lib/render.py:504; sweep foursome deep_dive_lib/sweep.py.
  **What's actually left (open):** two functions are ~69% of the
  remaining 5077 lines — `generate_interactive_html` (:1254, ~1874:
  page assembly, the `var DATA` emit, the collection panel) and `main`
  (:3440, ~1637: arg parsing + orchestration, fine where it is). A
  step 6 would be "extract the page-assembly half into
  `deep_dive_lib/page.py`", with `build_collection_data()` (see "Tests
  to add") as its natural first, smallest slice. Not scheduled.
  **Doc gap:** DEVELOPER_NOTES has no `deep_dive_lib` entry — the only
  layout description is `deep_dive_lib/__init__.py`'s docstring; worth
  a paragraph next time that file is touched. No dedicated
  `test_render.py`/`test_sweep.py` yet.

## Moveset / variant comparison tool

* **N=3 / N=4 renderer support for `compare_loadouts.py`** — MVP
  (N=2) shipped 2026-04-18. N=4 ceiling covers the canonical
  (moveset × form) cross (e.g. Forretress: Volt Switch / Bug Bite ×
  Shadow / normal). Remaining work: N=3 and N=4 renderer support,
  plus verdict templating for N-way ranking (MVP keeps verdict
  simple, just for Male-vs-Female).

  Design constraint: stay loadout-list-keyed, not A/B-keyed
  (`loadouts: list[LoadoutSpec]`, pairwise-delta iteration via
  `itertools.combinations`). N=4 ceiling: more than 4 makes the
  matchup-delta table unreadable. Don't design past this.

## User-facing documentation (post-arc)

The Reader's Guide arc shipped 2026-04-23/24 — infrastructure
(`build_guides.py`, landing page, dev-count sentinels), plus seven
guide bodies, ALL at `authorship=both` as of 2026-07 (the old
"pending review" note here was stale). A 56-agent staleness audit ran
2026-07-07 (43 findings applied; detail in TODO_archive). An eighth
guide, **Matchup Clusters** (`guides/matchup-clusters/`), was drafted
at `authorship=ai` and promoted to `both` 2026-07-07 (`1368bce`).

Open follow-ups:

- **Review the IV Robustness guide** (`guides/iv-robustness/`,
  published 2026-08-15 at `authorship=ai` -> promote to `both`).
  General robustness methodology (planes, cohorts/probes, W/L/? grids,
  curves, reach/deny, honesty rails) with the Worlds pages as the
  worked example. Follow-up when convenient: link the guide FROM the
  Worlds hub/cheat sheets -- that means re-rendering Worlds surfaces,
  so it requires the gamemaster re-pin first (see the Worlds NOTE
  above); don't do it casually.
- **Glossary gap:** `docs/concepts.md` does not define the envelope-crosser
  vocabulary the dives print (`elevated-band-crosser` /
  `depressed-band-crosser`, `deep_dive_rendering.py:~1551`); found closing
  the Shadow Sableye GL bands reminder (CHANGELOG 2026-09-22).
- **Two stale screenshots** (low): `envelope-position/screenshots/
  envelope-example.png` (pre-rename "Top Picks" legend) and
  `iv-flavor-guide/screenshots/flavor-example.png` (pre-2026-06-25
  purple theme; zone is teal now) — retake from HEAD-rendered dives
  when convenient.
- **Round-3 screenshots** if/when reader confusion surfaces a
  specific gap (round-1 + round-2 screenshots shipped via `32fae84`
  and `e449b38`).
- **Add topics** beyond the five shipped — Michael asked that the
  topic list be a conversation at the start of the task, not a
  fixed scope. Plan a session to (a) add topics surfaced by
  an HSH Discord member / new readers, (b) reorder by current reader
  confusion, (c) decide whether related topics merge.

The IV Flavor Guide write-up is owed to an HSH Discord member per
`project_acidic_arisen_writeup_commitment.md` (NB: that memory file
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

## Turn system (new mechanics) -- open residue

The 2026-09-02..10 history (the wait decision, the 09-03 re-port 104 -> 1,
the default flip, PvPoke shipping to master, the oracle / test / pool
re-baseline, the tripwire re-pin) and the 2026-09-22 legacy guard are in
CHANGELOG 2026-09-02..03 and 2026-09-09..10. Open:

- **Aegislash x Azumarill, 6 oracle cells -- RESOLVED 2026-09-27** (our
  bug: Shield-form charged moves were priced at the Shield atk; PvPoke uses
  the Blade atk the throw lands with). Root cause, pre/post values, the
  1080-cell sample, the deliberate atk-stage deviation and the cache
  predicate are in CHANGELOG 2026-09-27; `scripts/mechanics_notice.py` is
  deleted and the three VANISHED un-xfail candidates are all cleared.
  Still open from that work:
  - **Re-bake / page caveat:** both Aegislash GL dives and every GL dive's
    Aegislash opponent rows were baked with the bug (published, un-flagged).
    Migrate with `aegislash_blade_atk_20260927`; the push is Michael's call.
  - **`deep_dive_brief.py` G-caveat:** `CAVEAT_SPECIES = ('Aegislash',)`
    still stamps "(engine divergence vs PvPoke)" on Aegislash cells and
    excludes them from floors/rungs; the divergence it discloses is fixed.
    Retiring it changes published prose (and its test pins) -- decide with
    the re-bake.
  - Follow-ups F1-F4 from the diagnosis, each its own item: farm-gate
    ordering vs PvPoke's farm-down early return (decide only now that the
    damage fix is in; its touched set is also "Aegislash either side");
    the residual non-Aegislash-cause cells in the 1080 sample (Pachirisu
    level cap, Moltres-G, Thievul, ...); Blade Gyro-Ball-into-shield
    first-throw log differences; Registeel (2,1) log-only residual.
- **Threshold-TOML prose (3b(c) of the 2026-09-09 re-vet):** 182
  descriptions cited a decimal number in prose; each one whose underlying
  threshold moved is now a wrong published sentence. d363b1d has since
  archived the 58 derived stat-cutoff spreads, so re-count first
  (`grep -hE '^\s*description\s*=.*[0-9]+\.[0-9]+' thresholds/*.toml`
  finds 135 single-line hits on 2026-09-25; not the same method). Where a
  value is re-derivable we can propose it, but which bulkpoint defines a
  named spread is editorial and stays Michael's; ship-mode narrative
  policy applies.
- **Worlds artifact tests are skipped, not broken** (066e528, Michael
  2026-09-10: "no need to rederive any worlds stuff, that'll come again in
  a year"): `test_worlds_meta.py::test_generator_is_idempotent`,
  `test_worlds_bake_guards.py::test_one_pair_bake_is_idempotent_and_clean`,
  `test_build_worlds_pair_pages.py::test_reach_reproduces_dragapultsim_guarantee`.
  Re-deriving would overwrite the record of what was published under the
  engine that produced it. Un-skip when the 2027 Worlds cycle starts, or
  earlier if the IV-robustness work needs them.

DUP DOM IDS: measured 2026-09-10, NOT a blocker, but the de-dupe item that
the pre-dive checklist says "TODO carries" is no longer in this file, so it is
restored here.

Live-DOM state on a 5-moveset dive page (Melmetal GL, after stripping BOTH
`<script>` and `<template>` -- see the checklist's Lens 4):

    duplicated ids            240   all of the form af-<hash>
    multiplicity              2-5   (tracks the moveset count)
    duplicated anchor targets   0   of 60 -- navigation is UNAFFECTED
    referenced by href=#/JS/aria  0 -- nothing looks them up

So they are invalid HTML that nothing depends on. Emitted by
deep_dive_rendering.anchor_group_id once per moveset section. Worth cleaning
for standards-compliance, not for behaviour; do it when the renderer is next
open, and re-measure with the template-stripping trigger.

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

## Backlog (someday / maybe) — see `docs/TODO_backlog.md`

The long-tail design notes / research reproductions / UI wishlist live in
`docs/TODO_backlog.md` (split out 2026-06-28 to keep this file readable in one
shot). All still open — detail preserved verbatim there. Index of what's there:

- **Policies to add** — Selective baiting, random buff/debuff modes, EV-based
  baiting, new-mechanics decision-layer re-optimization.
- **Analysis goals** — RyanSwag-style matchup-flip annotations + wins y-axis,
  meta-wide slayer reference, SwagTips/reddit/iv-tech reproductions, the
  Tinkaton scatter-cluster + clustering-methodology investigations.
- **Slayer card UX** — signal-loss systemic audit (saturation of slayer/tier
  badges).
- **Slayer iteration cleanup** — Max-Wins column, Lurgan-as-opponent re-run,
  validation-doc reframe.
- **HTML output paths** — orphaned-artifact detector,
  mirror-slayer table size (mechanism removed; demote-vs-optimize).
- **Dive card** — High-HP strictly-dominated-spread bug, opponent-IV
  robustness axis, signature-dedup notes.
- **Upcoming plan-mode session** — dive/article content + information
  architecture (articles-vs-dives taxonomy, card placement, ML enrichment).
- **CD article generator** — S8 envelope-annotation wiring.
- **Deep-dive narrative** — (move-display DRY lifted to Refactoring above),
  catch-phrase tier, narrative-flavor plot tiers, TOML composite categories,
  RyanSwag-style autogenerated section.
- **Reproducibility** — non-reproducible opponent data (fingerprint + logging).
- **UI / Display** — scatter color modes, pretty-print names, CLI help
  enumeration, table sorting, client-side anchor add/remove.
- **Schema simplification** — TOML simplification triggers (collect friction).

---

Historical/shipped work lives in `CHANGELOG.md`; long-tail open backlog in
`docs/TODO_backlog.md`.
