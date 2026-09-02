<!-- TODO.md is a LIVE BACKLOG, not an append-only chronological log. Keep it
short: completed/shipped work moves to CHANGELOG.md (root-cause writeups,
dates, SHAs) or docs/TODO_archive.md (verbatim session batches); only OPEN
items and forward-looking design notes live here. When you finish an item,
delete its bullet or move the writeup out -- do not leave a 'DONE/RESOLVED'
narrative inline. This convention was set 2026-06-27 after the file hit ~1980
lines of mostly-completed chronological batches. -->

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
  post-Worlds bundle (see the Worlds checklist below).

## Cramorant -- open items (port/campaign/publish record: CHANGELOG 2026-08-24..27 + TODO_archive)

- REBALANCE re-verify (Michael 2026-08-25): a big move rebalance is
  expected ~2 weeks post-Worlds. When it lands: gamemaster-delta
  migration as usual, PLUS re-run the policy-lab verification corpus
  (~10 min) -- the strat's fitted constants were tuned on
  pre-rebalance move data, and the EDGE constants (0.022 DPT, 1v0
  aggr 2.0, 2v1 dpt_max 0.0155, 55-energy one-opponent patch)
  re-verify at FULL resolution with a worst-slice margin target of
  +0.5 (disclosures: docs/validations/cramorant_strict_bar_2026_08_26
  .md). This is also the standing argument for mechanism-not-names
  round-6 discriminators (they re-derive from new numbers at battle
  time).
- OPEN VALUE (next campaign): UL Dive+Surf 2v2 under the OLD tank was
  +15-21k flips at passing rating; a per-build tank discriminator
  would recover it (sheet v5 ships zero there).
- Upstream bug-report candidates (pvpoke): the two `move.moveID`
  typos (ActionLogic.js:368, :1239 -- the latter makes opponents
  never shield a lethal Dive, plausibly inflating published Cramorant
  scores; H4 in docs/cramorant_policy_plan.md measures it). Draft
  after checking whether the campaign produced the H4 numbers;
  follows docs/pvpoke_bug_reports.md conventions.
- Hard-counters lists: RE-DERIVE from the sheet-v5 rebaked tensors
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

## Worlds 2026 -- surfaces FROZEN through Aug 30; post-Worlds checklist

Worlds is Aug 28-30. The full arc (sessions 1-5, the 08-14 publish,
the Thievul moveset fork, the robustness/mirror deep pages, Greninja +
Annihilape, verify_worlds green at 555 pair pages / 0 deferred) is
recorded in CHANGELOG 2026-08-10..27 and docs/TODO_archive.md; plan of
record: docs/worlds_prep_plan.md.

STANDING RULES while the surface lives: publish only with Michael's
explicit per-instance go; long bakes detached + run-to-completion;
legacy engine only, both bait modes, never the sweep cache, no
`*_great.toml`; before ANY Worlds render, re-pin the gamemaster:
`git -C ../pvpoke show f60a41199:src/data/gamemaster.json >
~/Documents/gopvpsim_cache/gamemaster.json` (the cache currently holds
the LIVE blob, restored + hash-verified 2026-08-27; while a pin is up:
no Cramorant sims, and ~63 Cramorant-family test failures are expected
pin artifacts).

POST-WORLDS checklist (after 08-30):

- DECIDED (Michael, 2026-08-31): the Worlds surfaces **RETIRE at the
  Twilight Trails site update** -- "I don't think anyone will ever look
  at it post-Worlds." Publish-path unblocking is DONE ahead of that:
  `verify_worlds.py` is out of the `run_ship_gates.py` roster (it
  failed from main on all six stamps, and because the roster is shared
  by all four entry points it blocked EVERY publish path, not just a
  Worlds one), and the `publish_website.sh` Worlds re-render is now
  opt-in behind `WORLDS_RERENDER=1`. The 593 pages stay published
  exactly as shipped until the retire lands; `scripts/verify_worlds.py`
  is unchanged, so a rebake can still run it by hand.
  Correction to the old note here: the pinned worktree did NOT green
  the gate either -- the gamemaster stamp reads the machine-level
  cache, which holds the live blob. There was no clean publish path
  from any tree.
  NB the next publish must carry a full dive-page re-render -- the
  publish gate sentinel `userdata/.cards_rerender_pending` is SET as of
  2026-08-31 and blocks it until then. Two render-only fixes are
  waiting: (a) dead tooltips on the shipped pages' best-buddy L51 half
  (hydration bug fixed 061d93c); (b) the cup dive banner's false "this
  dive is kept as a dated archive" claim, removed from deep_dive.py
  2026-08-31 -- the 5 shipped *-equinox-cup pages still render it.
  Neither touched file is engine-hashed, so there is no sim cost.
  BEFORE re-rendering, settle the vintage question: the render path
  reads LIVE gamemaster/rankings while scores come frozen from the
  blob, so re-rendering a page that advertises "snapshot as of
  2026-08-26" against today's gamemaster mixes vintages.
- Worktree `gopvpsim-worlds`: REMOVED 2026-08-31. Its only working-tree
  delta was `scripts/worlds_meta.py`, verified byte-identical to
  `main` before removal (the Greninja/Annihilape editorial was already
  committed); the three symlinks were unlinked individually first so
  nothing could follow them into the main repo.
- Retire together: `thresholds/thievul.toml` [Thievul.cd_prep], the
  worlds/meta.toml `injected_move_ids` declarations + their on-page
  disclosures (build_worlds_pages.py:569-660), and the 4 injection
  guards in tests/test_worlds_bake_guards.py (3 currently
  auto-skipping under the live gamemaster, as designed).
- Aegislash rebake decision: the Cramorant port changes
  aegislash_shield modeling (161 measured cell flips vs Shadow
  Sableye; cold rebake = 57h). LEGALITY INPUT (verified 2026-08-27,
  Play! handbook second-Tuesday rule): Cramorant debuted 08-18 ->
  eligible 09-01 -> NOT Worlds-legal, so the question is purely
  Aegislash sim fidelity; if the surface retires after 08-30 the
  rebake case is weak. (Thievul's Icy Wind: eligible 08-25 -> legal;
  meta.toml's conclusion stands.)
- cmp_atk 1-ULP shadow-tie fix (deferred past Worlds; Michael
  2026-08-10): carry pre-shadow atk on BattlePokemon; own hash bump +
  a test recording the pre-fix values + a no-shadow-either-side
  migration predicate -- do NOT fold into a neutral batch. Pinned by
  tests/test_worlds_tier0.py::test_cmp_shadow_roundtrip_artifact_is_real.

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

Non-gating polish (open): (a) a11y -- badge text 4.36:1 in
pokemon-dark; hub matrix mini-grids are color-only (cheat sheets are
the text alternative); (b) optional session-6 survival strip (scoped
2026-08-11: tied to the reach table's LIVE plan only, one row per
attainable incoming fast tier, fast-pressure-only arithmetic
labeled, own adversarial round before ship); (c) optional
pooled-usage display (usage_recent_pooled_pct in meta.toml, unshown).
Planning artifacts preserved in userdata/worlds_planning/.

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

## PARKED: PvPoke upstream drift 2026-08-31..09-01 (megas) -- SEPARATE TASK

Michael pulled ../pvpoke on 2026-09-02: master 7b96d91fb -> 56bc6a8b1.
The PVPOKE-ENGINE tripwire is FIRING as designed
(`tests/test_rebalance_tripwire.py::test_pvpoke_engine_matches_last_vetted_commit`,
drifted: Pokemon.js, DamageCalculator.js, ActionLogic.js; last vetted
78c64048a). Do NOT re-pin the digest fixture without doing the
`docs/rebalance_checklist.md` section B re-vet -- the pin IS the record
that we read the diff.

Because the test is in the fast tier, `verify_tests` fails, so the ship
gates and every publish path are blocked until this is addressed. That
is correct behaviour, not a bug.

Headlines (these resolve BOTH open caveats in the
`project_mega_league_sims` memory -- what was "unverified" now has an
upstream implementation to read):

- `574aeb0da` Updated Action Logic for **third charged attacks**, +
  **Mega Bonus damage multiplier**. Our engine has an `n_cms > 2`
  guard, and a Mega bonus damage multiplier is a mechanic we do not
  model at all.
- `bd8c5d889` **Mega Level select** for Pokemon.
- `feba66f47` **Super Mega tag, default Mega Level to 4**, fixed battle
  logic. The memory noted that nothing in our data model or PvPoke's
  gamemaster carried a Mega Level; PvPoke now has one, with a default.
- `e86688bd1` Rankings updates + consistency score for Mega Evolutions.

Gamemaster moved too: live cache stamp is now `219c5741f21a`
(= 56bc6a8b1). The pre-rebalance baseline pin (`46bd08a77` ->
`c431557dcc76`, DEVELOPER_NOTES) is UNAFFECTED and still recovers
correctly -- that is what it was for.

NB `origin/new-mechanics` and `origin/twilight-trails` are still NOT
merged into master as of 56bc6a8b1.

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

**The gap: opponent pools are NOT in any chain.** Verified 2026-09-02:
`build_opponent_pool.py` appears in ZERO of overnight_redive.sh /
run_website_dives.py / publish_website.sh / phase2_preship.sh, and
`opponent_pools/gl_top50_plus_cs.txt` is still stamped "Generated
2026-06-10". The pools are the INPUT to every dive, so a season-start
bake against stale pools is wrong everywhere at once -- silently, with
the chain exiting SUCCESS. It is not a step anyone forgets; there is no
step.

This bites hardest at a rebalance, because new rankings change pool
MEMBERSHIP, not just order (the pool header records the June 2026
rebalance pulling in Umbreon, Milotic, Dondozo, Primeape). New
opponents are new columns, so they are not cache-migrate-able either.

TODO: make pool regeneration step 0 of the chain, or add a preflight
that hard-fails when the pools' recorded rankings vintage does not
match live (per the lens-grid rule: a cheap lens becomes a code-level
guard, not a checklist sentence).

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
