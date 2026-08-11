<!-- TODO.md is a LIVE BACKLOG, not an append-only chronological log. Keep it
short: completed/shipped work moves to CHANGELOG.md (root-cause writeups,
dates, SHAs) or docs/TODO_archive.md (verbatim session batches); only OPEN
items and forward-looking design notes live here. When you finish an item,
delete its bullet or move the writeup out -- do not leave a 'DONE/RESOLVED'
narrative inline. This convention was set 2026-06-27 after the file hit ~1980
lines of mostly-completed chronological batches. -->

## Worlds 2026 robustness analysis — IN PROGRESS (sessions 2-5 remain)

**Plan of record: `docs/worlds_prep_plan.md`** (read it before touching
anything Worlds). Session 1 DONE 2026-08-10 (`770a74d`): `worlds/meta.toml`
(31 entries) + `scripts/worlds_meta.py` + tests; go/no-go probe = GO
(60/720 amber, structured). Session 2 DONE 2026-08-10 (`4ef544d` +
`5c414c3` + `34a3803`): bool-plane core split into
`deep_dive_lib/robustness.py` (opp_plane + plane_task_worker; wrapper
semantics pinned), Tier-0 closed-form `scripts/worlds_tier0.py` (exact
bisected cutoffs; DragapultSim's Tinkaton-vs-Mantine numbers reproduced
<0.1 under the energy-legal 14-fast plan with guarantee-vs-per-spread
quantities paired correctly — see the plan doc's session-2 note), and
`scripts/worlds_planes.py` + `scripts/worlds_bake.py`
(manifest-stamped idempotent driver; dry-run verifies the full 1,860-key
Tier-1 worklist; guardrails are code + tests, incl. a sweep-cache poison
and a non-memoized mid-bake engine-digest check). Session 3 DONE 2026-08-10: engine batch + migration (above), Tier-1
bake (1,860/1,860 planes, 7.06M sims, 115s, manifest at the final
vintage), `worlds_render_data.py` + `build_worlds_pages.py` (hub +
31x31 matrix + 31 cheat sheets + index card, all root-level; ship
gates green), page layer adversarially verified (orientation + all
16,740 rendered numbers regenerated from planes, 0 mismatches; 84
independent re-sims exact) with the review's honesty findings fixed
(both-mode margin bands, exact spread counts, W/L/? letters,
focal-only no-bait + tie + corpus-convention disclosures, badge_rule
divergence shown, simmed moveset order). Session 4 DONE 2026-08-11 (overnight bake + morning consolidation):
Tier-2 joint grids for the top-66 usage-ranked amber pairs + 21 clean
FN samples (87 pairs, 348 grids, ~2.1B sims; 335 amber pairs deferred
by budget, listed on the hub -- extend by re-running
`worlds_tier2.py`, idempotent), 66 per-pair detail pages
(grid-selected scenarios, SVG robustness curves, boundary-confirmed
reach-or-deny with deny counts), measured FN-rate on the hub (4/21
clean pairs show IV-dependence; worst spread-impact printed), all
adversarially verified twice (second round forced the grid-based
scenario selector + wording fixes). Session 5 DONE 2026-08-11 except the publish itself: IV explorer
(worlds-explorer.html; baked closed-form ladders, zero damage
constants in JS, stat math delegated to POGOCollection, parity
bit-exact + engine-checked; conservative rounded-up cutoff display),
CMP board (worlds-cmp.html; union-cohort ranges after the hundo
blind-spot catch, ceiled thresholds, 1-ULP shadow-tie footnote
carried), `verify_worlds.py` registered as ship gate #5 (stamps,
coverage, page/deferred agreement, FN freshness, cmp/explorer
staleness, *_great.toml glob). Worlds is Aug 28-30. REMAINING:
(a) Michael's publish go (`publish_website.sh --push`); (b) a11y
polish still open: badge text 4.36:1 in pokemon-dark, hub matrix
mini-grids color-only (cheat sheets are the text alternative);
(c) optional Tier-2 budget extension (335 amber pairs deferred;
idempotent re-run).
Session-4 carry-in status (2026-08-10): rebalance date RESOLVED
(Forever Forward live in-game 2026-06-02 1pm PDT; Turin was
post-rebalance -- pages state the split; plan doc corrected).
DragapultSim trio PARTIALLY resolved (108.27 maps structurally to the
per-spread rank-1-anchor cutoff, ours 108.22; 165.73 deny stays
unmapped -- plan doc note). Still open for session 5: a11y polish
(badge text 4.36:1 in pokemon-dark; matrix mini-grid relies on cheat
sheets as its text alternative), optional pooled-usage display
(usage_recent_pooled_pct in meta.toml, unshown). Planning artifacts (design panel, judge
verdicts, evidence brief, probe script, usage JSON) preserved in
`userdata/worlds_planning/`. Standing rules: legacy engine only, both bait
modes, never the sweep cache, no `*_great.toml`, no `src/gopvpsim/` edits
mid-season. The behavior-neutral engine-hash batch LANDED as session 3's
first block (2026-08-10, per Michael's sequencing decision): wording fixes
+ parse_types relocation, one hash bump `1415857072fa -> <new>`, cache
warm-migrated (gamemaster leg first from a pre-batch tree — both stamps
were stale, see the session-3 commit message — then the fully-blessing
engine leg). The Tier-1 bake pins this final pre-Worlds vintage.

**DECIDED (Michael, 2026-08-10) — session-3 sequencing.** (1) DONE — the
engine-hash batch landed first (above). (2) The cmp_atk 1-ULP
shadow-tie artifact (session-2 float audit: divide-by-1.2 breaks 30 of
PvPoke's 227 exact shadow-twin CMP ties; pinned in
`tests/test_worlds_tier0.py::test_cmp_shadow_roundtrip_artifact_is_real`;
PROP-1 correction addendum in the round-2 review doc) is DEFERRED past
Worlds: planes + CMP board stay engine-consistent by construction, and
the session-5 CMP board must carry the footnote. Post-Worlds the fix
(carry pre-shadow atk on BattlePokemon) gets its own hash bump, a
test recording the pre-fix values, and a no-shadow-either-side
migration predicate — do NOT fold it into the neutral batch.

## Re-dive runbook

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
- **[render] compare_loadouts hardcoded sweep dims:** `:562`/`:804`/
  `:808` still say "4096 focal IVs x 9 shield scenarios" (their
  500-boundary wording is already correct); a non-4096 dive would
  render contradictory counts on one page. Follow-on to `95fcf74`.
- **[render, unchecked] L51 tooltip registry:**
  `reset_tooltip_registry()` runs once per file (`deep_dive.py:~1336`)
  -- the same bug class as the L51 opp-anchor registry fixed in
  `b43bd2d`. Nobody has checked whether the best-buddy template loses
  tooltip entries.
- **[tooling] verify_overnight step-[3/5] except-widening:** ValueError
  -> (ValueError, OSError) + the helper's Raises line, so a renamed
  pool file reports ERR instead of aborting the gate mid-step
  (latent-only; own small commit).

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

- **CD-prep tracking — delete `[cd_prep]` blocks** after the
  Oinkologne CD ships, or after PvPoke stably lists Mud Slap for
  2+ gamemaster refreshes. The auto-injection plumbing
  (`enumerate_movesets(..., cd_prep_fast=, cd_prep_charged=)`,
  commit `e61c14e`) stays.

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

* **Guard for the IV-scanner `maxLevel` single-source (fixed `725c184`).**
  **A full implementable design now exists:**
  `docs/reviews/2026-06-28_iv_scanner_maxlevel_strong_pin_design.md` (the
  cheap Option-1 pin: extract `build_collection_data()` from deep_dive.py +
  a 4-league unit test; supersedes this entry's "Heavy / needs a dive render
  + CSV fixture" framing, and refreshes this entry's stale SHA/line numbers).
  The `verify_js_parser.py` league-blindness half was fixed 2026-07-03
  (`c20071e`); the deep_dive.py extraction was waiting on the top-N/cup
  session (file conflict) -- that session LANDED (Phase 1 + Equinox Phase 2
  shipped; unblocked 2026-08-05), so the extraction is now schedulable.
  Original context: no test pins
  `_collection_data['maxLevel']` to `LEAGUE_MAX_LEVEL.get(league)`, so a
  future re-hardcode could silently re-introduce the GL/UL "owned mons one
  level too high" bug. **The whole 51.0 cluster half of this entry was
  FIXED 2026-08-05** (DRY review entries 9+10, `c956ed7`):
  `user_collection.py`'s four defaults are None-means-derive via
  `league_max_level`/`max_level_for_cap`, the
  `deep_dive_user_collection.js` mirrors derive from the league, and the
  `verify_js_parser.py` fixture is league-aware with Oinkologne +
  requireGender coverage. gobattlekit PORTS the module (its own copy still
  defaults 51 -- noted in the module docstring; pass caps explicitly when
  comparing). STILL OPEN here: only the `build_collection_data()`
  extraction + the 4-league unit test (the strong pin). The split
  session LANDED 2026-08-06/08 without touching this block, so it is
  unblocked and schedulable on its own. The design doc's Option 1 still
  applies but **every line number in it has drifted** — current anchors:
  dict built at `deep_dive.py:1937-1968` inside
  `generate_interactive_html`, target line `:1948` (`'maxLevel':
  LEAGUE_MAX_LEVEL.get(league, MAX_CPM_LEVEL)`), attached `:1969`,
  guarded at `:1875`, emitted `:2909`, consumed by
  `deep_dive_engine.js:961`. Two of the doc's three side-fixes already
  shipped (`verify_js_parser.py` league-aware `c20071e`;
  `user_collection.py` None-means-derive `c956ed7`). Traps: preserve
  the emitted dict's literal key order exactly (replay-vs-original
  diffing is byte-for-byte), and the helper must read `LEAGUE_MAX_LEVEL`
  at call time (main() MUTATES it for `--max-level`, `deep_dive.py:
  ~3796`). Fold in while there: `:1896` and `:4433` still pass a
  literal `LEAGUE_MAX_LEVEL.get(league, 51.0)` into
  `compute_rank_lookup`, restating the single source inconsistently.

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
guide, **Matchup Clusters**
(`guides/matchup-clusters/`), was drafted at `authorship=ai` for the
new dive section — MICHAEL: review + promote to `both`.

Open follow-ups:

- **Review the Matchup Clusters guide** (`authorship=ai` -> `both`).
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
`project_acidic_arisen_writeup_commitment.md` — promoting that
guide from `ai` to `expert` is the closing of that commitment.

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
