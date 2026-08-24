<!-- TODO.md is a LIVE BACKLOG, not an append-only chronological log. Keep it
short: completed/shipped work moves to CHANGELOG.md (root-cause writeups,
dates, SHAs) or docs/TODO_archive.md (verbatim session batches); only OPEN
items and forward-looking design notes live here. When you finish an item,
delete its bullet or move the writeup out -- do not leave a 'DONE/RESOLVED'
narrative inline. This convention was set 2026-06-27 after the file hit ~1980
lines of mostly-completed chronological batches. -->

## Thievul CD — dive PUBLISHED 2026-08-15; residue only (CD is Sun 08-16)

Dive shipped and live-verified at pogodives.com/thievul-great-league/
(4 pages: landing = SP / Icy Wind + Play Rough, the 62W-25L 1-1 build;
pre-CD reference SP / NS+PR rendered as m3). Plan + verified numbers:
`docs/thievul_cd_plan.md`. **The CD article was DROPPED by Michael's
decision 2026-08-15** — the `thresholds/thievul.toml` article slug
stays pre-registered but inert (the renderer only emits the link when
the article dir exists). **CD-day addendum (2026-08-16): the Thievul-vs-Licki IV-robustness
analysis SHIPPED** -- full 4096x4096 joint IV grids vs Lickilicky
(primary; 4 moveset/bait grids) and Lickitung (secondary), published as
`thievul-lickilicky-robustness.html` + `thievul-lickitung-robustness.html`
with an index card. Pipeline + contract: `docs/thievul_licki_analysis.md`
(pipeline: the generic `joint_iv_*` kit since 2026-08-19 -- `pairs/thievul_*.toml`; data in gitignored `userdata/thievul_lick*`).
Post-publish residue: (a) RESOLVED 2026-08-19: Michael okayed
committing the CD-day poke_genie fixture (commit 1b5ce69); (b) the
pinned gamemaster cache TTL-refreshed to `e6050f77bf06` during the
session (disclosed on-page; re-pin from pvpoke `f60a41199` before any
Worlds re-render, per the Worlds NOTE above).
Residue: (a) Michael's reply to u/LeansCenter
on the r/TheSilphArena launch thread (bullets drafted in-session
2026-08-15: 44W-44L -> 62W-25L at 1-1/rank-1 IVs/88-mon pool; IW+PR
beats PvPoke's NS+IW default by ~14 wins; PvPoke overall GL rank
122 -> 41); (b) Michael's HSH discord message
(`docs/hsh_message_notes.md`); (c) post-CD cleanup: delete the
`[cd_prep]` table once the un-pinned gamemaster stably lists Icy Wind.
CONFIRMED CAUGHT UP 2026-08-24 (live gamemaster lists Icy Wind for
Thievul; the 4 injection guards in test_worlds_bake_guards.py now
auto-skip on a caught-up gamemaster and re-arm under the Worlds pin).
POST-WORLDS (after 08-30): retire cd_prep + the worlds_meta
`injected_move_ids` declarations + those 4 guards together.

## Cramorant (engine port SHIPPED 2026-08-24; dives + policy campaign queued)

The Gulp Missile engine port (pvpoke 78c64048a) landed 2026-08-24 with
81 oracle-exact fixture cells + a 36-cell audit extension and a 52-agent
adversarial review (all 19 confirmed findings fixed same-day; record in
DEVELOPER_NOTES "Form change gotchas" item 5). Queued next, in order:

1. **Sweep-cache migrations** (recipe per the Worlds precedent): the
   gamemaster leg runs from the PRE-port engine tree (`--from-gamemaster
   8f1d6cca5c0f --old-gamemaster-file
   userdata/gamemaster_vintages/gamemaster_8f1d6cca5c0f.json`, ~147k
   blessed / ~2k re-sim), then the engine leg (`--from-engine
   5839391a7596 --predicate cramorant_port_20260824`).
2. **GL + UL dives**: `run_website_dives.py cramorant` (registry entries
   added; detached; form change -> per-IV sims, Aegislash-slow). LOCAL
   render only -- publishing needs Michael's explicit go, as always.
3. **Policy campaign** (Michael 2026-08-24, standing resource
   authorization): three tiers -- PvPoke default (shipped), never-bait
   (the dives' standard `--bait both` axis), and the **"PoGoDives
   strat"** overlay (`pogodives_dp`/`pogodives_shield`: tuned Cramorant
   cases, byte-identical `pvpoke_dp` fallback for every non-Cram
   situation, test-pinned; future non-Cram cases land one evidenced
   entry at a time). Full plan: `docs/cramorant_policy_plan.md` (knob
   globals, lab script, grid sweep, agent analysis panel, adversarial
   robustness round incl. the opponent-withholds counter and the
   lethal-Dive-shield-bug-fixed opponent, synthesis writeup).
4. **Upstream bug-report candidates** (pvpoke): the two `move.moveID`
   typos (ActionLogic.js:368, :1239 -- the latter makes opponents never
   shield a lethal Dive, plausibly inflating published Cramorant
   scores; H4 in the plan doc measures it). Draft after the campaign's
   H4 numbers exist; follows the docs/pvpoke_bug_reports.md conventions.

ACCEPTED TEST DEBT (per policy, recorded): (a) the dive-ASAP gate's
fresh-vs-frozen `move.damage` divergence (documented at the rule in
battle.py) has no discriminating test -- needs a post-missile-debuff
re-dive scenario where the two damage bases differ; write it if such an
oracle cell ever drifts. (b) The opponent-pool question -- whether
Cramorant (GL rank 13) enters `gl_top50_plus_cs.txt` / `ul_top60.txt`
as an OPPONENT for other species' dives -- is a Michael curation call;
until then no shipped dive sims against it.

## Worlds robustness deep dives -- IN PROGRESS (session started 2026-08-19)

The queued session ran 2026-08-19: shortlist SHIPPED
(`scripts/worlds_shortlist.py`, 455 amber pairs by combined usage, full
table `userdata/worlds_shortlist.md`); reuse-plan S1 COMPLETE (the
`joint_iv_*` kit replaced `thievul_licki_*`; acceptance record at
commit 8feec47, honesty-delta wording changes documented at 319c8a2;
memory: project-joint-iv-kit); pair pages baking/building through the
day via detached chains (`userdata/joint_iv/bake_chain*.log`), each
bake cross-checked exact vs the Worlds Tier-2 grids. Pages land in
`userdata/dives/<focal>_vs_<opp>_iv_robustness.html` -- LOCAL ONLY,
nothing published.

**OVERNIGHT OUTCOME (2026-08-20, pushed by ~03:35):** three site
pushes shipped -- (1) evening: 11 deep pages + links + 16 grid-amber
squares; (2) ~00:55: the 73-clean-pair audit landed (1.36B sims), FINAL
amber = 505/528 pairs (23 truly settled), 50 squares recolored from
grids with auto-generated detail pages; (3) ~03:35: three MIRROR pages
(lickilicky/wigglytuff/corviknight -- mirrors were an accidental
combinations() exclusion; all three are heavily IV-decided, e.g. the
Licki mirror's best build is rank-3182 15/3/3) + a fix for a latent
renderYourDenial crash. Mirror review round fixed 1 blocker + 3 majors.
All 11 deferred review minors shipped 2026-08-24 (28f2a4d) and
[meta.oracle] pins landed on all 18 eligible pairs (7360eb2).

**Round-2 mirrors (2026-08-24):** thievul x3 (true NS+IW mirror, IW+PR
mirror, NS+IW-vs-IW+PR cross-arm), quagsire-shadow, altaria -- built +
published-copy ready. DEFERRED to a later push (Michael-approved):
empoleon__vs__empoleon and feraligatr__vs__feraligatr mirror bakes.
Key finding baked into the kit (8ebb642): mirror grids are
seat-ASYMMETRIC by construction (row = optimized line, column =
always-baits dive convention), so there is NO antisymmetry invariant;
the MIRROR MATCH note is now data-driven (measured diagonal even-shield
wins). TEST DEBT: the new guards (measured mirror note branches in
build_joint_iv_page.py, seat-ambiguous stage attribution + buff-meter
bound in joint_iv_breakpoints.py, grid-condition stage probes +
debuff_thrown_only_shielded recording, f47e87f) shipped without
failing-first tests (publish-day time box). Review minor 4 (cross-arm
panel labels) shipped 2026-08-26 with the GTO-fill/outline bundle.

**TEST PLAN for the untested guards (write these; each test must FAIL
against the pre-guard commit named, per the testing policy; follow the
suite's scan rules -- floors below today's counts, positive controls
for absence pins):**

1. Mirror seat-asymmetry measurement (build_joint_iv_page.py, 8ebb642):
   unit-test the counting on tiny synthetic won arrays -- a 2x2x9 grid
   with a diagonal even-shield win must select the asymmetric MIRROR
   MATCH wording with the right count; an all-zero one must reproduce
   the round-1 wording BYTE-identically (pin the exact string -- the
   shipped licki/wiggly/corvi/quag-S pages depend on it).
2. Seat-ambiguous stage attribution (joint_iv_breakpoints.py, 373bae8):
   monkeypatch simulate to return a canned timeline + lp.atk_stage;
   assert (a) opponent-only throws with atk_stage==0 record
   debuff_unreachable (the pre-fix false positive: name-count > 0 must
   NOT count as thrown), (b) lp.atk_stage<0 counts as thrown, (c) a
   guaranteed opponent self-atk-buff aborts, (d) the Night Slash meter
   bound skips a candidate at 7 pooled throws (chance 0.125) and not
   at 6 (test _meter_can_fire directly for the c==0.5 special case
   too).
3. Grid-condition probes (f47e87f): capture simulate() kwargs via
   monkeypatch; assert charged_policy_0/1 are pvpoke_dp by default and
   ABSENT when stage_probe_engine_default_policy=true (byte-pin
   protection for thievul_lickilicky/lickitung).
4. debuff_thrown_only_shielded (f47e87f): canned fights where the
   debuff flies but every slot-1 hit is shielded must record the new
   key, not abort; a fight with an unshielded stage-0-only hit must
   still abort (stage_probe fixable).
5. Proportional fill + sliver floor (GTO fills): render a synthetic
   matrix row/grid9 slice and scan the HTML -- every amber gradient
   stop is within [1px,6px] (hub) / [5%,95%] (sheets); positive
   control: frac=0.999 must NOT render as a solid class (the floor is
   the whole point).
6. Amber outline channel: a cell solid in the headline slice with a
   corner-slice mix must render class "u"/"sc-u" and the origin
   annotation ('high-atk opp' etc. from Cell.amber_origins); negative
   control: headline-mixed cells never get the outline. Also pin
   amber_origins() keys == amber_scenarios() on a fixture cell.
7. JS side (joint_iv_page.js display labels, reEsc): stub-DOM harness
   render of the cross-arm page must contain both arm labels and no
   'by Thievul (NS+IW) atk stage' residue (the unescaped-regex failure
   mode reEsc exists for).

**DECISIONS FOR MICHAEL (2026-08-19 EOD):**

- **FN audit of the hub's green/red cells.** The probe-expansion screen
  (`scripts/worlds_probe_expand.py`,
  `userdata/worlds_probe_expand/results.json`) shows 45 of the 73
  non-amber pairs are IV-dependent under extra extreme probes -- 41 of
  them on the max-attack probe (realistic breakpoint-chaser corner),
  not junk-spread noise. The EXACT fix is one overnight bake:
  `direnv exec . python scripts/worlds_tier2.py --clean-sample 73
  --budget-minutes 720 --workers 14` (detached; idempotent; the 21
  already-baked clean pairs skip). Then the amber set is exact at
  cohort level and the hub's FN block can be retired/re-measured.
  Hub re-render = a Worlds render (gamemaster is pinned at 8f1d6cca5c0f
  and verified current, so safe today).
- **Shipped thievul pages carry two wording issues found by the pair-1
  review**: the 'IV tech without meta cost' card costs 5W on the
  lickilicky page (its own max-meta card shows 63W vs 58W), and the
  debuff-stage cross-check ladder was built from the rank-1 opponent
  instead of the simulated probe (stage -3 renders 21; correct is 22;
  `stage_ladder_from_rank1` in pairs/thievul_lickilicky.toml preserves
  the shipped bytes and documents it). Rebuilding with the current kit
  fixes both -- republishing is your call.
- **Deferred review minors** (all in the 319c8a2 commit message):
  duplicate-grid double embedding (~826KB/page), pareto-axis
  self-inclusion, one-option basis dropdown, wall-table 25-vs-12
  wording, CSV dropped-row accounting, raw key fragments in the
  answers dump, sim-count phrasing.

## Condensed-meta funnel bundle (queued 2026-08-19, Michael)

Bundle the whole Worlds chain for reuse on future condensed metas
(limited cups with ~20 real picks): meta table -> Tier-0/1 planes ->
amber screen -> Tier-2 grids -> hub/matrix/cheat sheets -> joint-IV
deep pages. Do it AFTER tonight's run proves the chain end-to-end
("when we're confident"). Inventory: `worlds_bake/planes/tier0/tier2/
render_data/build_worlds_pages/verify_worlds` are already meta.toml-
driven; the Worlds-hardcoded parts are `worlds_meta.py` (entry list +
badges are literals; needs a cup-roster config + a usage source that
isn't the Worlds Dracoviz corpus), the `worlds/` output paths + page
copy, and the `worlds_`-prefixed naming. `joint_iv_from_worlds.py` +
`worlds_shortlist.py` bridge to the deep-page kit and generalize with
the same meta-config handle. PvPoke publishes per-cup rankings
(topn_cup_filter_plan.md), so cup default movesets have a source.

Standing constraints unchanged: publish only with Michael's explicit
per-instance go; long bakes detached + run-to-completion; re-pin the
gamemaster from pvpoke f60a41199 before any Worlds render (verified at
the pin 2026-08-19 morning). **NOTE 2026-08-24: the data-cache
gamemaster was UN-pinned to the Cramorant vintage (pvpoke 78c64048a,
timestamp 2026-08-21) by the Cramorant session -- any Worlds render
(incl. the deferred empoleon/feraligatr mirror bakes) must first
re-pin: `git -C ../pvpoke show f60a41199:src/data/gamemaster.json >
~/Documents/gopvpsim_cache/gamemaster.json`.**

## Ship-gate gap (found by the 2026-08-17 thievul pre-publish review)

`verify_no_unicode_dashes.py --ship` scans page HTML but is blind to
reader-visible prose GENERATED by inlined `<script>` templates (the
thievul robustness pages render ~100% of their prose that way and got a
clean bill regardless of content). Extend the gate to extract string
literals from inlined app JS (or run pages through a headless renderer)
before trusting it on script-driven pages. Interim mitigation: the
thievul page suite carries its own ASCII assert.

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
staleness, *_great.toml glob). **Session-6 candidate (Michael 2026-08-11, scoped in-session):
survival strip on pair pages** -- the bulk half of the DragapultSim
framing ("this def/HP survives one more fast hit -> the turn that
funds the 2nd charged move"). Scoping decided to avoid ladder bloat:
(a) tied to the reach table's LIVE plan only (its n_fast implies the
turns you must survive), (b) one row per attainable incoming fast
tier: hits-survived by (def-tier x HP), with the shed-cutoff that buys
+1 hit, (c) fast-pressure-only arithmetic, labeled, grids as battle
truth, (d) new surface = its own adversarial round before ship. Not
publish-gating.

Worlds is Aug 28-30. **PUBLISHED 2026-08-14** (Michael's go;
`publish_website.sh --push`, live-verified at pogodives.com): 401/401
amber pairs baked + pages, verify_worlds OK, plus the same-day
pre-publish polish batch (`157bf71`: cheat-sheet grid links, moot deny
annotation, curve hover readout). Gamemaster held at the pre-Worlds
vintage 8f1d6cca5c0f throughout (only upstream delta: three added mega
forms, sim-irrelevant). NOTE: the data cache holds that pinned old
blob; the next TTL refetch returns to current -- fine now that the
site is published, but re-pin from pvpoke `f60a41199` before
re-rendering any Worlds surface pre-Worlds. REMAINING (all
non-gating): (a) a11y polish: badge text 4.36:1 in pokemon-dark, hub
matrix mini-grids color-only (cheat sheets are the text alternative);
(b) optional session-6 survival strip (scoped above).

**THIEVUL ADDED POST-PUBLISH (2026-08-18).** The Icy Wind Community Day
(08-16) made a Worlds-legal Thievul, so the meta grew 31 -> 33: Thievul
enters as a MOVESET FORK, two FORCED entries sharing Sucker Punch + Icy
Wind and differing on the second charged move -- `thievul` (NS+IW,
PvPoke's post-CD default) and `thievul_iw_pr` (IW+PR, the CD dive's
build). Rationale, mechanism and the scoped NS-vs-PR claims are in
`docs/worlds_prep_plan.md` ("The meta"). Highlights:

- **Icy Wind is INJECTED.** The pinned gamemaster 8f1d6cca5c0f predates
  the CD; upstream pvpoke `f754cd6fc` already lists it as an eliteMove,
  so the lag is proven (CLAUDE.md's cd_prep rule), not inferred. A
  per-entry `injected_move_ids` list in meta.toml is honored by
  `worlds_bake.preflight_moveset_legality` for the declaring entry only.
  Disclosed on both cheat sheets, the hub moveset cells, and the
  provenance line every Worlds page carries. **Retire the table (and its
  disclosures) once the un-pinned gamemaster stably lists the move.**
- **Two `worlds_code` bumps, both blessed forward, no cold re-bake.**
  `worlds_bake.WORLDS_CODE_LINEAGE` holds the one-shot written proofs;
  `--bless-worlds-code` is the explicit operator opt-in and the manifest
  records each blessing. All three Tier-1 bakes were verified additive:
  0 pre-existing manifest entries changed, 0 pre-existing npz touched.
- Tier-1 coverage 1,860 -> 2,112 (= C(33,2)*4). Amber pairs 401 -> 455.
  Tier-2: 432/455 fully baked; **23 deferred**, all Thievul pairs, all
  in the low-usage tail, listed on the hub by the standing mechanism.
  Extend by re-running `worlds_tier2.py` (idempotent) -- the cross-arm
  pair `thievul,thievul_iw_pr` is among them and needs
  `--include-pair` to jump the queue.
- **Operational lesson: run long bakes DETACHED.** Two harness-managed
  background bakes were killed mid-run. `os.fork`/`os.setsid` double-fork
  survives (macOS has no `setsid` binary). Per-grid manifest keying meant
  nothing was lost either time -- restarts resume.
- The FN-rate block still reports 4/21 from the ORIGINAL clean sample;
  that sample was drawn from the 31-entry meta and was deliberately not
  redrawn (redrawing would retag existing grids). The hub's wording is
  literally true; if a wider FN claim is ever wanted, re-sample
  explicitly.
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
