<!-- TODO.md is a LIVE BACKLOG, not an append-only chronological log. Keep it
short: completed/shipped work moves to CHANGELOG.md (root-cause writeups,
dates, SHAs) or docs/TODO_archive.md (verbatim session batches); only OPEN
items and forward-looking design notes live here. When you finish an item,
delete its bullet or move the writeup out -- do not leave a 'DONE/RESOLVED'
narrative inline. This convention was set 2026-06-27 after the file hit ~1980
lines of mostly-completed chronological batches. -->

## Re-dive runbook

For the next cold re-dive: `docs/predive_checklist.md` is the STANDING
pre-cold-dive gate; run `overnight_redive.sh` and watch with
`scripts/chain_status.py --chain overnight`. (Last bake: CHANGELOG.md
"2026-06-28".)

## ENGINE BATCH READY FOR REVIEW/MERGE: branch `hunt2` (2026-07-03)

Four engine fixes are implemented, verified, and committed on branch
`hunt2` (worktree `~/coding/hunt2/gopvpsim`), batched because this new
machine's cache is test-only (every real dive is cold anyway, so no
migration predicates were built): `3f7e144` NB-1 selection freeze (final
verdict on the bounding sweep's FIX recommendation), `e17d868` FC-1
Aegislash revert energy, `0acdc8e` OMT turns_planned divisor, `a36930e`
would_shield doc-only (investigated: faithful port, not a bug). Final
engine hash `51bf823c217a`. Verification: new fixtures oracle-equal (Group
D flipped to must-pass), suite 1213 passed (2 pre-existing new-machine
fixture failures), audit harness IMPROVED to 172 exact + 35 documented
(two Tinkaton-vs-Aegislash cells now exact), perf -2.4% vs machine-local
baseline. MICHAEL: review + merge `hunt2` -> main before the first real
production dives. NB merge will likely conflict in DEVELOPER_NOTES.md
(both branches edited it) — take hunt2's engine-section rewrites AND
main's F2/self-debuff/IV-floor edits; docs/reviews files are
identical-content on both sides.

## Engine bug-hunt round 2 (2026-07-03): 16 confirmed findings need triage

`docs/reviews/2026-07-02_engine_bug_hunt_round2.md` — 1 HIGH, 7 medium,
8 low; 0 uncertain; all double-skeptic-verified. ("No shipped winner flips
in sampled cells" held for the hunt's own samples; the NB-1 bounding sweep
below later found one on a wider grid.)

**FIXED on main (Opus, 2026-07-03) — the non-engine-batch, non-contested slice:**
- **F1** (`57137e4`): `migrate_cache.py` `used`-set now unions form-change
  swapped-in moves via new single-sourced `formchange.form_change_swapped_moves`;
  regression test builds a minimal one-move gm delta. **Adversarially verified
  COMPLETE**: the only battle-time move swaps are Aegislash (fast) + Morpeko
  (charged); Mimikyu swaps none; no other foreign move-read exists in the four
  engine files; no wrongly-blessing scenario remains. NB: the helper lives in
  `formchange.py` (engine-hash file) -> F1 bumps the engine hash on main by a
  behavior-neutral function; harmless on the cold machine, flagged for the
  hunt2 merge (fresh final hash; different regions, should merge clean). No past
  migration was tainted (the one prior `--from-gamemaster` run, skarmory_mega,
  was purely additive).
- **F2 doc** (`57137e4`): the `self_debuff_either_side` static-flag caveat is
  now documented in the predicate docstring + a Registeel FB+ZC test assertion
  (measured harmless in `69876ee`; the "AURA_WHEEL is the only swap" line is
  corrected). Trap for the next predicate author recorded, not silently false.
- **BP-1** (`2931d1d`): `breakpoints()` returns `[]` for power-0 moves instead
  of ZeroDivisionError (was silently dropping every anchor for the whole
  Aegislash-Shield GL dive). **BP-2** (`cc70593`): CLI now forwards
  `--shadow-atk/--shadow-def` into the damage math (was header-only).
- **JIT-COV-1** (`22c0a0b`): 2 settrace-verified parity matchups now cover the
  ttl-cmp-bonus / dedup-keep / atk-stage-clamp+4 kernel branches (were unpinned).
- Full suite after: 1216 passed / 14 xfailed / 2 pre-existing new-machine
  fixture failures (`test_export_owned_breakdown`, missing `userdata/website`).
- **Out-of-scope note surfaced by the F1 verification:** `anchors.py` calls
  `get_moves()` but is NOT in `sweep_cache._ENGINE_FILES` — a separate
  engine-hash-coverage question (anchors feed breakpoint analysis, not the
  cached 1v1 column scores), worth a look but not a delta hole.

**hunt2 engine batch MERGED to main (`2a63b65`, 2026-07-03, Michael-approved):**
NB-1 (selection freeze) + FC-1 (Aegislash revert energy) + OMT (turns_planned
divisor) + would_shield-as-documented. Fast-forward from `a86b0fd`; full suite on
the merged tree 1234 passed / 14 xfailed / 2 pre-existing fixture failures.
battle.py byte-identical to the audit-passed hunt2 engine. OMT is the cold-forcing
change (touched set not statically characterizable), so the merged engine needs a
cold re-dive — everything else in this batch rides it for free.

**DONE post-merge (Opus, 2026-07-03):**
- **JIT-COV-2** (`02627fe`): inline comment at the JIT `final_state = _DPState(0,
  ...)` site — `energy=0` is inert (no consumer reads `.energy`). Comment-only on an
  engine-hash file; rides the OMT-forced cold re-dive.
- **PROP-1** (`fe2c443`): DEVELOPER_NOTES "Key implementation details" now documents
  the exact-`cmp_atk`-tie -> player-index (p0-first) resolution as a PvPoke-faithful
  known property.
- **anchors.py `_ENGINE_FILES` question** (was the F1 out-of-scope note): checked —
  **BENIGN**. Engine-hash caches store only sim column scores; anchors.py feeds
  breakpoint analysis and is strictly downstream (no engine file imports it, anchors
  recompute fresh each dive), so it needs no engine-hash coverage. Caveat: replay
  blobs / gobattlekit thresholds exported before BP-1 carry old anchors by design —
  re-export any shipped ones that matter.

**Still DEFERRED:**
- **js-parity-1..5** (LOW): shipped-page JS contradictions; the top-N session
  owns `deep_dive_engine.js` / `deep_dive.py`. Leave until it lands.

**Still needs Michael / on branch hunt2:**
- **[medium, divergence-policy decision] NB-1 — BOUNDING SWEEP DONE
  2026-07-03, recommendation = FIX; Michael's call pending.** Sweep
  (140 matchups / 1260 cells vs pinned oracle, 8 mechanism traces):
  76 diffs, 7 flips, effectively all 36 GL diffs touch the shipped surface,
  incl. a shipped winner flip (Forretress (Shadow) vs Cradily GL 1-0, ours
  413 LOSS vs oracle 588 WIN). Recommendation: freeze dpe-derived selection
  at init stages PvPoke-style across all THREE consumer sites, keep the
  don't-bait dpeRatio-staleness site as a documented divergence (PvPoke's
  side is a cache-artifact bug), with a proven `nb1_selection_freeze`
  migration predicate (dynamic-flag-audited) and FC-1 as a clean co-bump
  option. Full footprint tables, predicate proof, xfail/fixture specs:
  `docs/reviews/2026-07-03_nb1_bounding_sweep.md`.
- **[medium, NEW from the sweep] OMT `turns_planned` divisor port
  infidelity** (battle.py:749-750 vs ActionLogic.js:306): unintentional,
  PvPoke strictly better in all traced cells (the -24 Oinkologne family,
  3 shipped-oriented). Touched set not statically characterizable ->
  fixing it forces a COLD re-dive; batch with the next cold-forcing change,
  do NOT ride the NB-1 bump.
- **[medium, NEW from the sweep, our own bug] would_shield/always-shield
  internal inconsistency:** the don't-bait override consumes
  `would_shield=False` while the active shield policy always shields
  (Florges vs Seismitoad UL 2-1 inflated +201). Independent of PvPoke
  fidelity; needs its own look. Detail in the sweep doc (carve-out
  section).
- **FC-1** Aegislash mid-flight-revert energy divergence — FIXED on branch
  hunt2 (`e17d868`); merges to main with the engine batch.
- Remaining report lows not yet actioned: **BP-3/BP-4** (Aegislash whole-level
  rounding gaps in iv_breakpoints/iv_bulkpoints), **FC-2** (Blade->Shield revert
  clamp rationale stale vs oracle) — details in the report; low, unscheduled.

The `hunt2` worktree (`~/coding/hunt2/`, engine @ c7f9ba2 + pvpoke @
00f0afe7f, own venv) is KEPT so the report's repro commands run as written;
delete with `git worktree remove` (both repos) once the batch is merged and
repros are no longer needed. The `--p1-bait/--p2-bait` pvpoke_trace.js flags
(first no-bait oracle) are on main.

### Open follow-ups (non-gating; render/tooling-only ones re-render from replay)

- **[render DRY] score-key `{mi}_{mode}@51` parity (Python<->JS).** Open-coded in
  `deep_dive.py` + `deep_dive_engine.js`; consistent today, loud failure mode.
  Optional belt-and-suspenders parity test only (it's a cache/render data
  contract, not a refactor target).
- **[tooling, silent-incompleteness] verify_overnight UL opponent-count
  assertion.** The completeness guard is GL-only; a UL opponent silently
  deranked by a fresh gamemaster would drop from every UL dive and still pass the
  gate GREEN. LATENT (UL 68/68 resolve on the current gamemaster). Needs a
  marker/expected-count design decision before asserting.
- **[tooling] F3: narrative auto-gen patch is WARN-not-FAIL** (`run_website_dives.py`
  ~624). Low; optional: surface the WARN where `verify_overnight` scans.
- **[render] `#opp-<slug>` canonical landing.** `#opp-` links land on the
  first-rendered mention; pick one canonical per-opponent target. Low; render-only.
- **[render] wrap long Plotly legend entries.** Anchor/spec-card spread labels
  (e.g. `Fortified Gyarados (Shadow) (Dragon Breath / Aqua Tail+Twister) (151.27+
  Def)`) overflow the legend far to the right (seen on Mandibuzz GL, 2026-07-04).
  Plotly doesn't wrap legend text natively -- insert `<br>` into the trace
  `name` at a word-boundary target width when building the scatter legend in
  `scripts/deep_dive_rendering.py` (trace `name=` construction). Render-only, not
  an engine file (no cache invalidation). Apply AFTER the current bake, then batch
  re-render all dives from their `userdata/replay/*.replay.pkl.gz` blobs (no
  re-sim) + rebuild the index for a consistent legend across the site.

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

**Phase 1 (client-side opponent filter) SHIPPED** (`b8b561e`, `f5741a3`).

**Phase 2 (Equinox Cup pilot) IMPLEMENTED + VERIFIED 2026-07-03, awaiting
Michael's review before publish** (gopvpsim `aa8dac8..3c153fb`; gobattlekit
`0c1bd5c`). Done: cup rankings loader (`data.py`); `recipe_equinox_great` +
committed `opponent_pools/equinox_great.txt`; `--cup` labeling overlay
(cup-sourced oppMetaRank/rankSnapshot, cup-named title/card + archive banner,
replay-blob `cup` marker); flat `<species>-equinox-cup` slugs + separate
archive-friendly `cups/index.html` + "Limited Cups" card; gobattlekit
threshold-export collision guard (cup blobs -> `<species>_<cup>.toml`);
`verify_overnight` `*-cup` coverage. Five pilot dives run locally cache-ON
(Corviknight/Mantine/Mandibuzz/Toucannon/Clodsire); page-render 67/67,
index-presence + bundler dry-run green, suite 1245 passed. NOT pushed / NOT
published -- pending review. Audit report:
`~/coding/reports/gopvpsim-equinox-cup-pilot-2026-07-03.html`. The cup-index
live/archived status is auto-derived from PvPoke's `formats[].showFormat` on
each build (no hand-maintained rotation list); a rotated-out cup auto-flips to
"archived snapshot". Phase 3 (more cups,
legality-filter eval, app-side cup toggles, mega engine) remains -- see the
plan doc.

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
"Gives up vs #1" column) and as a Python reference (`scripts/owned_breakdown.py`).

- **Scope (decided):** GL + UL, the species we've already dived (zero new sims,
  smallest mobile bundle).
- **Architecture:** EXTRACT per-IV dropped-vs-rank-1 from existing dive grids
  (no re-sim) — the dive embeds the full 4096-IV score grid. gobattlekit has NO
  battle engine and must not get one (lean iOS build); it consumes pre-baked
  data + recomputes only the analytic layer on-device.
- **One remaining build step** (step 1, the bitmask exporter, SHIPPED
  2026-06-29 in `c1ea231`: `bitmask_from_dive` + `--bitmask` on
  `scripts/export_owned_breakdown_bundle.py`, with roundtrip + size tests in
  `tests/test_export_owned_breakdown.py`; the top-K-stat-product bake was a
  DEAD END — those spreads all give up nothing; owned mons have arbitrary
  IVs):
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

DONE (2026-06-28) for the known slice: the seven species in
`run_iv_guides.FLOOR_10_SPECIES` (Marshadow, Meloetta (Aria), Jirachi, Keldeo
(Ordinary), Keldeo (Resolute), Zygarde (Complete Forme), Eternatus) are reswept
at the 10/10/10 research floor; their envelope JSONs span iv 15..10 and their
rendered guides carry the floor-aware "covered" banner (the never-ship-unflagged
FLAG is resolved for them). The enumeration research ran 2026-07-03
(adversarially-verified deep-research sweep):
`docs/reviews/2026-07-03_limited_availability_iv_floors.md`. Headlines: all
seven existing floor-10 assignments CONFIRMED; NO new species verifiably needs
adding; Melmetal is explicitly NOT limited (Mystery Box is indefinitely
repeatable). Michael RATIFIED the no-change verdict 2026-07-03. The
SHADOW-legendary gap was CLOSED 2026-07-03 (Opus, deep-research pass, appended
to the same doc): 12/12/12 safe for all 17; "1/1/1 shadow floor" is folklore
(real floors 6/6/6 Giovanni / 6/6/6 Shadow Raid); none genuinely one-shot.
STILL OPEN (both need Michael, both optional/low): (a) OPTIONAL belt-and-
suspenders -- evaluate Dialga/Latias/Lugia/Reshiram (Shadow) down to 6/6/6 in
their ML guides (the four Giovanni-primary legendaries whose grindability is
only medium-confidence; worst-case floor is a bounded 6/6/6); (b) re-run the
audit when Eternatus returns (Niantic announced it will).

## Pre-ship arc — residual open polish

The 2026-04/06 pre-ship arc shipped (site published 2026-06-07; see
CHANGELOG.md). The minor polish residue:

- **G16 — methodology-details guide pointer.** Replace the
  in-article hidden-but-present methodology prose with a one-line
  guide pointer (the hide layer is already in place; G16 is the
  last-mile substitution). ~30 min.

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

* **File PvPoke bug reports** *(NO URGENCY — Michael's explicit call
  2026-06-11: he'll file when he has time to engage with any upstream
  responses; do not nag)* — paste-ready GitHub-issue drafts live in
  `docs/pvpoke_bug_reports.md` (2026-06-11): 7 curated reports
  — the list below minus the retracted Mimikyu timing item (#5, our
  own logging artifact) and the debunked-premise bestChargedMove item
  (#2, initializeMove DOES set move.damage at init; the real issue
  there is the DPE-overwrite, drafted as report 4) — plus the new
  Blade→Shield CPM-table overflow found 2026-06-11. Filing them
  upstream is Michael's action. (The discovery list formerly
  enumerated here duplicated DEVELOPER_NOTES "PvPoke bugs found"
  and the drafts doc — those two are the sources of truth.)

* **Known PvPoke divergences** — DEVELOPER_NOTES "Known divergences"
  is the single source of truth (bestChargedMove per-turn recompute,
  the near-KO plan cluster, the battle-timeout guard). Re-audit
  anytime: `python scripts/audit_oracle_harness.py` (covers GL + UL;
  current baseline 207 cells = 170 exact + 37 documented).

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
  (`c20071e`); the deep_dive.py extraction waits for the top-N/cup session
  to land (file conflict). Original context: no test pins
  `_collection_data['maxLevel']` to `LEAGUE_MAX_LEVEL.get(league)`, so a
  future re-hardcode could silently re-introduce the GL/UL "owned mons one
  level too high" bug. Also worth folding in: the latent dead-code `51.0`
  fallbacks in `deep_dive_user_collection.js:275` (`ivsToStatsAtCap` default,
  caller always passes maxLevel) and `:344` (`matchMons`, zero live call sites)
  — single-source these to a league-aware ceiling if matchMons is ever wired up.
  **Round-4 (2026-06-28) found the same-class `51.0` latent default in the
  shared library `src/gopvpsim/user_collection.py:209` (`ivs_to_stats_at_cap`)
  and `:263` (`compute_rank_lookup`).** NOT currently wrong (every shipped
  deep_dive bake site overrides it), but it's a league-unaware default that a
  future caller could hit. **This module is consumed by gobattlekit** (CLAUDE.md
  "gobattlekit" / shared `user_collection`), so changing the default signature
  needs cross-repo coordination — do NOT change unattended; either make the
  default `None` + derive from `league` (like `owned_breakdown.py` `786d437`),
  or require an explicit cap, after checking gobattlekit's call sites. The JS
  regression guard `verify_js_parser.py:152,302` ALSO hardcodes `51.0` with
  `league='great'`, so it can't catch a league-awareness regression — fix the
  fixture to the league-derived ceiling when adding the strong pin above.

* **No-bait oracle tests from iv-tech deep dives** — `pvpoke_dp`
  accepts `bait_shields=False`; sanity tests for the farm-down gate
  landed in `test_battle.py` (see `test_pvpoke_dp_no_bait_*`).
  Real-world oracle cases from the HSH #iv-tech deep dives still
  open:

  1. **Tinkaton vs rank #1 shadow Altaria 0-1** —
     `docs/tinkaton_deep_dive_reference.md:31`. "143.04 defense with
     141 hp … win the 0-1s *without baiting*." Reference also flags
     inconsistency due to shadow IV variance.
  2. **Spidops vs rank #1 Altaria 1s** —
     `docs/spidops_deep_dive_reference.md:35`. "140.67 defense with
     132+ hp flips the 1s vs the rank #1 altaria *without baits* by
     reducing sky attack damage."

  (Tinkaton vs Medicham 1-1, Tinkaton vs rank #1 Azumarill 1-2, and
  Corviknight vs default-IV Shadow Sableye all shipped 2026-04-12.)

  Open followup from case 1: our sim has a more forgiving win
  threshold than the reference (many Tinkaton spreads below
  def=141.66 win the 1v1, e.g. 0/10/15 at def=138.96). Reference may
  be overly conservative, or our sim is missing a nuance. Worth
  round-tripping at pvpoke.com/battle.

  Each remaining test should parametrize over `bait_shields=[True,
  False]` when the reference makes a directional claim. Priority:
  low-to-medium — integration oracles, not correctness-blocking.

* **Auto-anchor fallback gating tests** — `build_auto_anchors()` and
  the per-kind gating logic are currently only verified by smoke runs
  against real Annihilape data. Add explicit unit tests for the
  gating cases (no kinds existing → all three fire; one kind existing
  → other two fire; all three existing → empty registry).
  *Note: bulkpoint gating tests landed in 2026-04-08; this entry now
  covers the broader BP/CMP gating coverage gap.*

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

* **Move display-name single-source (DRY, confirmed 2026-06-28).** Two helpers
  derive a move's label two incompatible ways on the same dive page — header
  "Super Power" vs narrative "Superpower" (~39 moves): `auto_gen_narrative._gm_move_display`
  uses the gamemaster `name`; `deep_dive_analysis.pretty_name`/`pretty_moveset`
  title-cases the raw moveId. Route both through one helper (have `pretty_name`
  consult the gamemaster name). Cosmetic, render-only, but broad multi-file +
  ship-narrative-adjacent — do deliberately. Full detail: backlog "Deep-dive
  narrative — open polish".

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
2026-07-07 (43 confirmed findings applied — reference-dive drift from
the 2026-06-25 Male->Female repoint, renamed sections, swapped-tint /
inverted-axis errors, the per-kind auto-anchor gating description; all
factual, voice-preserving). An eighth guide, **Matchup Clusters**
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
- **Features to add** — energy-lead axis (safe-switch / closer matchup flips) —
  SHIPPED 2026-06-12.
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
