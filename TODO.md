## >> NEXT ACTION (2026-06-27 PM): cold re-dive (pre-redive sweep COMPLETE)

Multiple pre-redive sessions have landed, plus a full {layer}x{lens} pre-dive
sweep (2026-06-27, session 3) that caught 3 launch-gating issues the earlier
location-oriented passes missed. The re-dive is irreducibly **COLD** (the
float32 fix forces it; the legacy cache is all-None-stamped). ONE step remains:

0. **STANDING PRE-LAUNCH GATE: run `docs/predive_checklist.md`** before every
   cold re-dive (it has a ready-to-paste prompt). The DRY lesson: scope the
   check as a {layer}x{lens} grid, not a walk of files you happen to read --
   see the checklist + CLAUDE.md "Pre-dive assessment". Session-3's run is
   recorded in the session-3 batch below; its findings are folded in.
1. **Cold re-dive** (`overnight_redive.sh`) -- fresh, long-running, monitored
   session: re-dive on the new engine + refreshed gamemaster, review,
   re-publish, then GC the legacy cache. Watch live with `watch -c -n5
   'scripts/chain_status.py --chain overnight'` (+ `scripts/iv_guides_status.py`
   once the ML step starts). NB the ML bake now runs SERIAL (one guide, all
   cores) -- see the parallelism item below.

### Pre-dive {layer}x{lens} sweep (2026-06-27 PM, session 3)

Ran the first full grid sweep (now `docs/predive_checklist.md`). It caught what
the earlier location-oriented passes missed. LANDED before launch:

- **[GATING, data] Oinkologne (Female) GL reference TACKLE -> MUD_SLAP** -- Mud
  Slap CD shipped (in fastMoves + eliteMoves, PvPoke default); the TACKLE pin was
  a pre-CD leftover from the removed CD article. `run_website_dives.py`.
- **[GATING, silent-incompleteness] ML bake failures now visible.** The ML tail
  step is WARN-not-FAIL by design, so the chain printed SUCCESS and the morning
  verifier was blind to a partial/OOM ML bake. Fixed: `overnight_redive.sh` final
  status surfaces ML failure; `verify_overnight.py` check [5] asserts every
  ML-pool species has a fresh `_iv_envelope_all9.json` + flags any ML WARN line.
- **[hardening, resource lens -> code guard] `run_iv_guides.py` concurrency
  preflight** prints `jobs x per-guide-workers` and HARD-FAILS if > physical
  cores (`--allow-oversubscribe` to override) -- the ML-oversubscription bug
  can't recur silently.
- **[render correctness] `pvp_damage` DRY/precision fix** -- `deep_dive_analysis.py`
  re-implemented damage with double-precision 1.3/1.2; now imports
  `moves.BONUS`/`STAB_MULTIPLIER` (bit-for-bit with the engine; was wrong on
  5394/5.6M boundary cases). Render-path narrative cells only; no engine-hash bump.
- **[render correctness] win-count 500 boundary unified to `> 500`** (500 = tie,
  per vendored PvPoke `BattleHistogram.js`/`Interface.js`). The Python census was
  right; the JS overlay's `>= 500` was the bug. Fixed all JS win-classification
  sites + Python `_won_set`. Render/overlay only.

FAST-FOLLOW backlog from the sweep (non-gating, render/tooling-only,
re-renderable via replay -- do NOT block launch; ~17 confirmed findings, top ones):

**Session-4 (2026-06-27 PM, Claude AFK churn) resolved most of these -- see
the commits below. Remaining open items kept at the bottom.**

- **[DONE] [med, dead affordance]** comparison pages (`compare_loadouts.py`)
  sortable-header affordance with no sort JS -- DROPPED the `sortable` class +
  its cursor/hover CSS so headers no longer signal interactivity (kept the
  `data-sort` th type-hints as latent metadata). Articles keep their working
  sorter; only the comparison path lacked the JS.
  *Enhancement follow-up (low):* articles already ship a generic
  `table.sortable` click-sorter (`generate_article.py` ~3440-3505) that reads
  the SAME `th data-sort` type-hint scheme compare_loadouts uses. Wiring it up
  for the comparison pages is a clean reuse -- ideally extract a shared helper
  (e.g. into `render_article.py`) and use it from both files rather than
  duplicating the JS. Needs click-testing of the bool/pct/num cell parsing +
  the sort-arrow CSS. Render-only.
- **[DONE] [med, silent-incompleteness]** `build_matchup_web.py` partial-matrix
  exit-0 -- now HARD-FAILS on any pool-resolution skip on a non-limited run
  (`--allow-skipped` override, mirrors `run_iv_guides.py --allow-oversubscribe`).
- **[DONE/n-a] Tinkaton GL** reference -- already handled by commit `1651217`
  (drop stale PLAY_ROUGH; track get_default_moveset). Full L4 reference-pin
  freshness re-check this session: all pins fresh or intentional variants
  (Forretress BUG_BITE variants; Mimikyu-Busted pins == base Mimikyu default;
  Sableye GL same charged-move SET in a different ORDER -- cosmetic, our sim
  baits by policy not list order). The Oinkologne/Tinkaton stale-pin class is
  fully resolved.
- **[DONE] [low] DRY/cleanup:** `LEAGUE_CP` re-declarations consolidated to the
  canonical `gopvpsim.pokemon.LEAGUE_CP` (`generate_article.py`,
  `compare_loadouts.py`). `gc_cache.py`'s `iv_envelope` iteration is
  INTENTIONAL (report-only surfacing of the legacy dir for manual pruning; the
  `if d.is_dir()` guard makes it a no-op once deleted) -- closed as not-a-bug.
- **[DONE] [test-side + broader] win-set `>= 500` -> `> 500`.** Session-3's
  "unified ALL win-classification sites" claim was FALSE (adversarial skeptic
  pass): `>= 500` (counts a 500 TIE as a win) was still live in
  `deep_dive_analysis` (find_flips, probe_tier_cutoff), `deep_dive_narrative`
  (_flavor_max_winrates, _find_losses_vs_general), `deep_dive_slayer` (4 win
  counts), `export_owned_breakdown_bundle`, `generate_article`,
  `compare_loadouts` (+ user-facing title/doc text). All unified to `> 500`;
  the two desync-prone reimplementation tests fixed in lockstep with their
  production targets. JS path was already `> 500`, so the whole surface is now
  consistent. Render/analysis-only, rides the cold pass.

**Still open (low):**
- score-key `{mi}_{mode}@51` format open-coded in Python and JS (DRY) -- NOT
  touched this session: it is a cache/render data contract, too risky to
  refactor unattended. Do it deliberately with a re-render check.
- `overnight_eta.py` doesn't model the ~7h ML tail (ETA accuracy, enhancement).
- **No shared win-predicate constant.** The `> 500` / `500 = tie` boundary is
  open-coded at ~dozens of Python+JS sites. A shared `is_win(score)` / WIN_TIE
  constant would have prevented the session-3 incomplete-unification entirely.
  Deferred (broad, cross-language touch); flagged as the real DRY root-cause.

### Session-4 adversarial round-2 (2026-06-27 PM, fresh-eyes finder fleet)

Three independent adversarial finders run over the under-covered grid cells
(each self-refuting). Results:

- **[CLEAN] L2 cache-key completeness.** Audited every key in
  `sweep_cache`/`slayer_cache`/`cache_base`/ML path. ALL complete -- every
  result-affecting input is in the key, the per-column engine stamp, the
  `required_planes` gate, or the `mechanics != 'legacy'` cache disable (verified
  wired + un-bypassable). Bug #4 (slayer focal-level-cap) confirmed fixed.
  No findings (high confidence).
- **[CLEAN, doc-only fixes landed] L1 cmp_atk migration.** The shadow-strip
  CMP migration is COMPLETE in code (all 13 order-deciding sites use
  `cmp_atk`; the 6 remaining `.atk` are damage/stat/construction). Landed: two
  stale comments that predated the fix (`deep_dive_signature.py` docstring,
  `_dp_jit.py` param comments) corrected to `cmp_atk`.
- **[FIXED] L3 orchestration F1** -- `build_website_index.py` could drop a
  rendered page (unreachable from nav) and exit 0. Now hard-fails on a dropped
  page-with-index.html (`--allow-skipped` override); the chain runs it
  un-overridden. Also dropped the stale `40 dives`/`Twenty`/`36+4` literals in
  `overnight_redive.sh`.

**Still open from round-2 (orchestration, LOW-MED -- for Michael):**
- **F2 [low-med]** split-moveset page absence is undetectable by
  `verify_overnight.py` check [2] (it asserts present-file *freshness*, never a
  *missing* file). A dive that writes `index.html` but is short a `index_m*.html`
  split page ships unnoticed. Proposed: in check [2], cross-check each fresh
  dive dir's `index_m*.html` count against the `top_movesets` declared for that
  slug in `run_website_dives.DIVES` (import it DRY, the way check [5] imports
  `run_iv_guides`). Not done: it depends on `deep_dive.py`'s own split-write
  hard-fail behavior, which I didn't audit (L5, out of the finder's scope).
- **F3 [low]** narrative auto-gen patch is WARN-not-FAIL + unverified
  (`run_website_dives.py` ~624). Low severity -- empty narrative blocks are an
  accepted ship state (human fills them) -- but it's the same WARN-not-FAIL
  shape. Optional: surface the WARN in a form `verify_overnight` scans.

### Pre-redive adversarial assessment batch (2026-06-27 PM, session 2)

An ultracode adversarial assessment (8 fresh-eyes finders over the engine +
chain, each finding independently refuted/prioritized) was run before committing
to the hours-long cold bake. It refuted 11/13 raw findings and surfaced ONE real
launch-blocker plus several free ride-alongs; all landed, all ride the cold pass:

- **A1 [BLOCKER] SHADOW_DEF_MULT was `5/6`, not the game's value** -- fixed to
  `float32(5/6) = 0.8333333134651184` (`fb2f9de` -> `f7f9509`). `5/6` (float64
  0.8333333333) is ~2.8e-8 too large, so we dealt ~1 LESS damage to shadow
  defenders at floor() breakpoint boundaries (the deliverable). The GAME stores
  this as float32; PvPoke's `0.83333331` is an imprecise float64 transcription
  (~3.5e-9 low), so we match the GAME, not PvPoke -- a deliberate, documented
  game-over-oracle choice (DEVELOPER_NOTES "Engine constant sourcing"). Hid
  because the only shadow oracle fixture (Shadow Swampert vs Registeel) sits
  off-boundary. Also fixed a stale `5/6` copy in `deep_dive_user_collection.js`
  + added `tests/test_js_shadow_constants.py` drift tripwire.
- **B2 bandaid[910] defer-self-debuff read the wrong index** -- `cm_self_buff[
  first_idx]` -> `cm_self_buff[0]` (activeChargedMoves[0], per ActionLogic.js:929)
  (`c5c515e`). Real port bug; ZERO shipped-default impact.
- **B3 `buffApplyChance` string-compare** -- `float()`-coerced in `_priority_
  shuffle` + the bestChargedMove tie-break (`c5c515e`); same class as #7. ~Nil
  shipped-default impact.
- **ML-sweep parallelism** -- post-cache-rework each guide fans across all cores
  via `iv_sweep`, so the old concurrent-guides model (overnight `--reserve 0`)
  oversubscribed ~10x on a 10-core host (thrash + OOM-kill/missing-guide risk;
  the cache is corruption-SAFE -- atomic .npz writes, disjoint focal dirs, torn
  files self-heal as a miss -- so no wrong data, but a thrashed run could ship an
  INCOMPLETE bake). Fixed: `run_iv_guides.py` defaults to SERIAL, overnight uses
  `--jobs 1` (the GL/UL pattern) (`fd52021`).
- **UI flip "(+N more)" was dead text** -- now a real no-JS inline expander in
  all 3 contexts, with the toggle markup DRY'd into one `cover_toggle_html`
  helper + single `COVER_TOGGLE_CSS` (`85e7284`). Output-neutral (re-render
  byte-identical).
- **Duplicate `id="opp-<slug>"` anchors** -- each opponent's deep-link anchor was
  emitted by multiple sections (5 open-coded sites + 2 per-fn seen-sets) -> ~57
  duplicate ids/page (invalid HTML; browser jumps to first only). DRY'd into one
  render-scoped `opp_anchor_id()` helper + registry (reset per page in
  `generate_interactive_html`); first mention per opponent emits, rest skip
  (`fc40c17`). Net 86 ids/86 distinct, 0 dups, all 72 `#opp-` links resolve, slug
  set preserved. Render-only. "Flavor 1" (de-dup, land on first-rendered mention)
  -- see the Flavor-2 future fix below.
- **Cleanup**: deleted the stale `pogo-simulator/` husk (a 16K symlink-to-gopvpsim
  shell; completes the long-deferred `pogo-simulator -> gopvpsim` rename).

Final gate (whole batch): full suite 1100p/14xf, oracle audit clean, benchmark
3,436 sims/s.

FUTURE FIX (render-only, NOT a launch blocker -- re-renderable via replay
anytime): **`#opp-` canonical landing ("Flavor 2").** Today (`fc40c17`) a
`#opp-<slug>` link lands on the *first-rendered* mention of that opponent, which
is inconsistent across opponents (sometimes a rich `dd-opp-row` detail breakdown,
sometimes a bare name span in a coverage list, sometimes a flip-list `<li>`).
Flavor 2 = pick ONE canonical per-opponent target (prefer the `dd-opp-row` detail
when present, else the breakpoint `<li>`) so every link lands on the most useful
spot consistently. Deferred because (a) it changes nav behavior and (b) needs a
canonical-target design decision (not every opponent has a `dd-opp-row`). Links
were unused so this is low priority; do it as a focused render change + replay
re-render when convenient.

### Session-1 pre-redive batch (2026-06-27 PM) -- also rides the cold pass

(ML-sweep progress reporting also LANDED 2026-06-27: `df51527` route
iv_envelope_analysis progress through the structured logger / `3d0b2e8` unlink
stale per-guide log per run / `2d82b51` watch views surface per-worker phase /
`0a207a0` tests -- per-guide `userdata/logs/iv_guides/<slug>.log` with phase
lines, surfaced by `iv_guides_status.py` + `chain_status.py`.)

Session-1 commits (all ride the cold pass for free):
- **#2 float32 damage constants** -- DONE (`4e57321`). STAB/BONUS/super-effective
  now use float32-truncated doubles matching the game/PvPoke. Boundary-scattered,
  no clean predicate -> this is what makes the re-dive cold (so everything else
  this session rides it for free).
- **#5 bandaid[929] no-bait swap** -- DOCUMENTED as a kept divergence (`0fcc290`);
  `docs/pvpoke_divergences.md` #6 + `tests/test_bandaid929_nobait_divergence.py`.
  Ungated on `bait_shields` on purpose (PvPoke's gated line is strictly
  dominated); NO engine behavior change. (Measured: gating would flip 284 winners,
  all in our favor.)
- **#7 `_cm_debuf_delta` dead branch** -- FIXED + vetted (`377c48e`). The
  guaranteed-self-buff arm was a `'1' == 1` str/int dead branch; now
  `float(...) == 1.0`, matching PvPoke (JS `"1"==1` coerces). Empirically +
  structurally ZERO dive impact (0/10458 cells, 0/~900k DP-decision probes);
  ultracode-vetted (oracle clean 37 divergences, suite green, bench 3,482 sims/s).
  `tests/test_cm_debuf_delta.py`. REMOVES a divergence (not added to the
  divergences doc).
- **Scanner-button render polish** -- the "Copy for IV scanner" button now also
  renders on Threshold Tier cards (`08f5c8a`) and Slayer Builds archetype cards
  (`96a1c48`), DRY'd into `_scanner_button_html` / `_cutoff_scanner_spec` helpers
  (`bd48fc9`). Render-only, no engine/cache impact.
- **Pool resolution re-checked** on the refreshed gamemaster: GL 78/78, UL 68/68
  resolve -- no silent shrinkage.

Sibling-bug status for context: **#1** (`fire_now` cmp_atk) is in `main`
(`b1b58f1`) -- the cold pass subsumes its old warm shadow-XOR re-dive plan, now
moot. **#3** (farm-down self-debuff stacking) FIXED in `main` (`7a55d43`), 0
shipped-cell impact.

Reminder: while editing engine files, run dives with `--no-sweep-cache` until
trusted (see CLAUDE.md "Sweep cache" + "Before a cold re-dive, check for a
tractable migration").

## ML-sweep progress reporting (DONE 2026-06-27 PM)

**DONE** -- shipped in `df51527` / `3d0b2e8` / `2d82b51` / `0a207a0` (see NEXT
ACTION above for the summary + verification). Original task notes kept below for
reference.

*(2026-06-27 PM, Michael)* The GL/UL dives have nice structured progress
reporting; the ML IV-guide sweeps do not -- a long ML bake runs mostly silent.

GOAL: give the ML sweeps the SAME progress reporting as the GL/UL dives, and
BAKE IT INTO THE WATCH SCRIPT so the cold ML bake is observable live during the
re-dive.

- **Match the dive's mechanism**, don't reinvent: the dives use the structured
  logger (`scripts/deep_dive_logging.py`; `docs/structured_logger_design.md`;
  CLAUDE.md "Debugging conventions") writing to a status file that the watch
  view tails. NO bare `print()` from workers (multiprocessing -- route through
  `logger.*`).
- **Watch-script parity**: the GL/UL side is watched via
  `scripts/chain_status.py` (+ `scripts/iv_guides_status.py` once the ML step
  starts), tailing `userdata/logs/...`. The ML sweep should emit
  per-guide / per-quadrant / per-opponent progress into that same surface so a
  single `watch` view covers the whole chain.
- **Start points**: `scripts/run_iv_guides.py` (driver),
  `scripts/iv_envelope_analysis.py` (per-guide sweep),
  `scripts/iv_guides_status.py` (existing ML watch view -- may already be a
  partial hook), and how the dive chain wires `chain_status.py`.
- **Why now**: do it in a FRESH session before launching the cold re-dive, so
  the ~hours-long ML bake in that re-dive is watchable instead of silent.

----

## OVERNIGHT 2026-06-27 (NOW MERGED into `main`; branch deleted 2026-06-27)

A Claude overnight session. **All five commits below are now in `main`** (the
branch `overnight/2026-06-26` was an ancestor of `main` via the cache-rework
merge, and was deleted 2026-06-27). Nothing was auto-published to the live
site -- publish is still the separate gated step. Commits:

**Done (pending your review):**
- **Mimikyu (Busted) starts-busted GL + UL dives** + the engine change they
  needed: a focal that STARTS in a terminal alt form now carries its native
  stat buffs (the Busted -1 def, which `reset_for_battle` was silently
  re-zeroing). Validated by equivalence to the PvPoke-oracle in-battle bust
  (PvPoke's *direct* `mimikyu_busted` build is the wrong oracle -- it skips
  `nativeStatBuffs`). Dives built into `userdata/website/mimikyu-busted-*`.
  `tests/test_mimikyu_starts_busted.py`.
- **Limited-mon ML IV-floor correction** (the never-ship-unflagged item
  below): `--iv-floor` flag + floor-aware renderer (no stale "12" labels) +
  `run_iv_guides.py` auto-sweeps the 6 untradeable mythicals
  (Marshadow/Meloetta/Jirachi/Keldeo x2/Zygarde-Complete) at 10/10/10.
  Eternatus is now also in the floor-10 set (Michael 2026-06-27: rare enough
  to count as special, trade status irrelevant). Floor-12 path verified
  byte-equivalent; floor-10
  render validated synthetically.
- **Engine bug #1 [HIGH] FIXED**: the `fire_now` double-fire CMP gate used
  shadow-boosted `.atk` (missed 10th site of the 2026-06-13 cmp_atk
  migration) -- flipped real winners. Oracle-verified, `tests/test_fire_now_cmp_shadow.py`.

**Running when you wake:** the full ML re-bake (`run_iv_guides.py`, 61 guides
= 55 @ floor 12 fresh cmp-JS + 6 @ floor 10) -- ~94 min/batch, so it runs
into the day; whatever's done is in `userdata/`, unpublished.
**Blast-radius note:** the bake started on the PRE-bug-#1 engine, so any
Master SHADOW guide it produced may carry the #1 behavior -- re-bake the
shadow ML guides after you accept the #1 fix.

**Bug-hunt follow-ups (open) -- full report `docs/reviews/2026-06-27_engine_bug_hunt.md`:**
- **#2 [MED]** damage formula uses exact `1.3/1.2/1.6` not the game's
  float32-truncated constants -> off-by-one on breakpoint boundaries. Real,
  but shifts many fixtures; needs a broad re-vet (not auto-applied).
- **#3 [MED] FIXED 2026-06-27** -- farm-down now stacks self-debuffing moves
  (PvPoke ActionLogic.js:399-405 `energyToReach` gate). Adversarially verified
  (suite 1075p; 0/2160 default-meta cells changed; 162/162 firing configs +
  Malamar single-best match PvPoke; 378-cell scan moved 23 toward PvPoke, broke
  0). Zero impact on shipped default-moveset dives. `tests/test_bug3_farm_stack.py`,
  DEVELOPER_NOTES "#3 ... RESOLVED".
- **#3-followup [NEW, open]** the bug #3 verification's 378-cell both-self-debuff
  oracle exposed ~117 PvPoke divergences (7 winner-flips) on the BROADER
  both-self-debuff population (Lurantis LEAF_STORM+SUPER_POWER vs Cresselia,
  Blaziken BRAVE_BIRD+OVERHEAT vs Registeel, ...) that PRE-DATE #3 (already
  disagreed under the old engine, so independent of the stacking fix). Likely
  the near-KO-DP / `_optimize_move_timing` self-debuff-timing deviation cluster,
  possibly an uncharacterized separate issue. Investigate: re-run the
  both-self-debuff grid old-vs-new to confirm pre-existing, localize via
  `--trace-dp`, then decide keep-as-divergence (CLAUDE.md policy) vs fix. These
  are non-default movesets, so low ship-priority.
- **#4 [MED]** slayer disk-cache key omits the focal level cap -> stale
  cross-`--max-level` hits in Master mirror-slayer (silent-wrong output).
  Clean fix (key field + `CACHE_VERSION` bump), left for you to schedule.
- **#5 [MED/LOW]** `bandaid[929]` stack-switch missing the `bait_shields`
  gate -- decide gate-to-match vs document-as-divergence.
- Latent: `_cm_debuf_delta` `'1' == 1` str/int dead branch (cosmetic in
  tested cases, worth a cheap fix).

**Deliberately deferred:** the gobattlekit bitmask exporter (mobile-format
design choices better made with you awake).

## LAUNCHED 2026-06-25 02:10: the big re-dive (thread 2 / ship)

The overnight chain (`overnight_redive.sh`) was launched 2026-06-25 02:10,
all-cores, detached via `nohup`. It runs the 40 dives -> comparison pages ->
GL matchup web -> ML IV-guide bake (master_top60, ~7h cold) -> index ->
link verify. Realistic wall-clock ~14-18h. Prep commit `4f9846c` (NOT pushed).

Launch readiness was assessed by an adversarial workflow (verdict: NO-GO as
staged -- the chain would have run to completion but silently shipped wrong
output in 3 ways). What the prep session actually did to fix each gotcha:

1. **ML guides not in the chain -> FIXED.** Added `run_iv_guides.py
   --no-index-refresh --reserve 0` as a failure-tolerant tail step (runs
   OUTSIDE `step()` so one bad guide can't abort the final index+verify),
   sequenced before the index rebuild so the new Reshiram (Shadow) guide gets
   indexed. NB this is a second ~7h COLD job (the fresh pull orphaned the
   won-set caches); a cache-migration tool would NOT help (dives bypass the
   sweep cache under `--compare-energy`, and the guide's dominant cost -- the
   `score_set` rec-sweep -- is uncached by design; a naive re-key would also
   ship stale damage for rebalanced moves).
2. **Oink pages -> DELETED (not banner).** Decision flipped 2026-06-25 from
   "archive with banner" to "delete from the site" (no banner mechanism
   existed; Michael doesn't need the pages). Removed Steps 2 & 3 from
   `overnight_redive.sh` and deleted the 3 stale built dirs
   (`oinkologne-great-league`, `articles/oinkologne-cd-2026-05`,
   `comparisons/oinkologne-male-vs-female`). Female Oink dive stays (in DIVES).
   FOLLOW-UP: the orphaned source TOMLs (`articles/oinkologne-cd-2026-05.toml`,
   `comparisons/oinkologne-male-vs-female.toml`) and `build_guides.py`'s
   `oinkologne-great-league` reference are now dangling -- cosmetic cleanup,
   not a chain blocker.
3. **Stale "20 dives" label -> FIXED** (header + step label now say 40).
4. **Cradily UL gap -> ROOT-CAUSED + FIXED, and a SECOND species found.** It
   was NOT a shadow data gap: the bare names `Cradily` AND `Golisopod` resolve
   to GL-only clone slugs (`cradily_b` / `golisopodsh`) that are absent from UL
   rankings, so `get_default_moveset` silently dropped them from every UL dive
   (the prep's pool union missed both). Pinned the canonical UL default
   movesets inline in `ul_top60.txt` (`Cradily | fast=ACID |
   charged=ROCK_TOMB,GRASS_KNOT`; `Golisopod | fast=FURY_CUTTER |
   charged=X_SCISSOR,AQUA_JET`). (Aegislash was later removed from this pool
   entirely 2026-06-25 — not UL-viable; file renamed from
   `ul_top60_plus_aegislash.txt`.) UL pool now 68/68 resolve.
   FOLLOW-UP (deferred): make `species_id` league-aware so it prefers the
   canonical slug when the GL clone is absent for that league -- then drop the
   inline overrides. Cosmetic nit: the override labels these "Cradily (Acid /
   Rock Tomb+Grass Knot)" in UL tables (consistent with existing variant style).
5. Energy-default bypasses the sweep cache (full sim) -- expected cold-run cost.
6. **Morning check:** `python scripts/verify_overnight.py` (chain status,
   freshness, ship gates). Watch live: `watch -c -n 5 scripts/chain_status.py
   --chain overnight` and `scripts/iv_guides_status.py` once the ML step starts.
   Status file: `userdata/logs/overnight_status.txt`. Publish AFTER review via
   `scripts/publish_website.sh --push` (push still nod-gated).
   FOLLOW-UP (not done, low risk now that UL resolves 69/69): extend
   `verify_overnight.py` to assert UL opponent counts so a future silent pool
   shrink is caught the morning after, not shipped.

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
- **Two remaining build steps:**
  1. **Bitmask exporter.** `scripts/export_owned_breakdown_bundle.py` already
     extracts the breakdown but emits a full-list JSON that is **~25.6 MB for 15
     species — too big for mobile**. Add a per-IV BITMASK variant: 246 even-shield
     (opp × scenario) cells -> ~31 bytes/IV + a one-time names header, decoded
     on-device. (top-K-stat-product bake was a DEAD END — those spreads all give
     up nothing; owned mons have arbitrary IVs.)
  2. **Toga screen** modeled on `gobattlekit/src/gobattlekit/screens/user_iv_checker.py`,
     reading the baked artifact (bundle like `default_thresholds.toml` via
     `tools/threshold_export/`); resolve owned mons through their evolution line;
     **add parity vectors** to gobattlekit `tests/test_parity_vectors.py`.
- **Full plan + findings + file:line pointers:** `docs/owned_mon_breakdown_plan.md`.
  Memory: `project_owned_mon_breakdown.md`. Convention note: web + iOS use the
  dive's opponent IVs; the Python CLI uses 15/15/15 (they differ slightly).

## ML IV-guide compare panels (shipped 2026-06-24) — re-bake perf follow-up

The guide's "Check my IVs" box gained shared HP-margin + best-buddy-flip
panels (commits 7292132 / e3156e7), backed by a new `cmp_scores` block in
the `iv_envelope_analysis.py` JSON. `score_set()` captures the raw scores
from the 64-combo rec-table sweep but is **NOT cached** — `WonSetCache`
stores only booleans, so on a *warm* re-run the rec loop re-sims all 64
combos × 4 quadrants (~138k sims, ~tens of min/species).

**Follow-up for the thread-2 full re-bake:** teach `WonSetCache`
(`scripts/iv_envelope_cache.py`) to also store the per-combo score grid
(bump `CACHE_VERSION`), and have `score_set` read/write it, so the
re-bake reuses the warm cache instead of re-simming. Cold cost is
unchanged (those sims already ran for `drops`); this only fixes the warm
regression. All ~60 guides need a re-bake anyway to pick up `cmp_scores`,
so fold this into that run. See the `score_set` docstring.

## Sweep cache should store energy so `--compare-energy` warm re-dives work (POST-PUBLISH)

**LANDED 2026-06-27 (branch `cache-rework`, NOT merged/pushed).** The whole
bundle below shipped across 7 commits; design + sign-off in
`docs/design/2026-06-27_cache_rework_design.md`. What changed:

- **Bug #4** (slayer cache focal-level-cap key) FIXED (`slayer_cache` v4).
- **Energy plane**: sweep columns are now multi-plane `.npz`
  ({score,energy}); energy is always captured + stored, so the
  `capture_energy -> use_sweep_cache=False` bypass is gone and the default
  `--compare-energy` dive serves warm (it was previously running the cache
  *dead* on every default dive). `sweep_cache` v6; shared
  `scripts/cache_base.py` foundation.
- **Selective invalidation**: per-column engine STAMP (in the `.json`
  sidecar) + `scripts/migrate_cache.py` (`--list-stamps`; `--from-engine X
  --predicate shadow_xor --apply`). Blesses the columns a localized fix
  provably doesn't touch, deletes the rest.
- **ML/dive merge (T2)**: `iv_envelope_analysis` now runs on the shared
  `iv_sweep` engine (one sweep per quadrant; `won_set`/`score_set`/
  `result_metrics` are grid views), so ML re-bakes reuse warm columns +
  signature dedup. `WonSetCache` retired. Verified byte-identical to the old
  path on standard/shadow/floor-10.
- **GC**: `scripts/gc_cache.py` (keep current + N-1 gamemaster vintage;
  `--dry-run` default). ~45 GB / 140k stale columns now prunable.

**NOW-ENABLED FOLLOW-UP (next session): the warm bug-#1 re-dive.** With the
stamp + `migrate_cache` in place, apply the bug-#1 `fire_now` cmp_atk fix to
`battle.py` (it's on branch `overnight/2026-06-26`), then:
1. `python scripts/migrate_cache.py --list-stamps` to find the pre-fix
   engine stamp;
2. `migrate_cache.py --from-engine <pre-fix> --predicate shadow_xor --apply`
   to bless the unaffected (both-shadow / both-non-shadow) columns and drop
   the shadow-XOR ones;
3. re-dive / re-bake — only the shadow-XOR cells re-sim (warm), then
   re-publish. (Original bug-#1 scope/measurements are in the RESOLVED-#1
   DEVELOPER_NOTES entry.)

----

**HANDOFF 2026-06-27 (Michael) -- DO THIS BUNDLE NEXT, ahead of bug fixes.**
The shadow-CMP bug #1 fix (`docs/reviews/2026-06-27_engine_bug_hunt.md`) is
INTENTIONALLY DEFERRED until this cache session lands, because fixing it
edits `battle.py` -> bumps the engine-source hash -> invalidates the WHOLE
sweep cache -> forces a COLD full re-dive. The point of doing the cache
work first: make the post-fix re-dive WARM.

Two concrete requirements for this session, on top of the energy-column /
GC / ML-sweep-merge items already in this bundle:

1. **Selective invalidation by predicate.** Replace (or augment) the
   blunt all-or-nothing engine-source hash with a mechanism to invalidate
   only the cache columns a localized engine change actually touches. Bug
   #1's affected set is cleanly characterizable -- ONLY matchups where
   exactly one side is shadow (shadow-XOR; both-non-shadow and both-shadow
   are provably unaffected, since dividing both atks by 1.2 preserves the
   CMP inequality). So a "invalidate columns where focal-or-opponent is
   shadow, warm-serve the rest" tool turns the post-#1 re-dive from cold
   into a small warm recompute. Design the predicate-invalidation API so
   future localized fixes (not just shadow) can reuse it.

   **Measured impact of #1 (2026-06-27 scan), to scope the warm re-dive:**
   ran the GL pool's shadow-XOR matchups old-engine (`152daf82` = `b1b58f1^`)
   vs new, at 2 IV samples (15/15/15, 0/15/15) x 9 shields = 20,178 cells.
   Result: **35 cells changed (0.17%), 6 winner flips, max margin 273.**
   Small + localized -> a full cold re-bake just for #1 is overkill; this is
   exactly the warm-selective-re-dive case. The flips cluster on shadow
   attackers (Forretress-S, Ninetales-S, Quagsire-S, Jumpluff-S, Sealeo-S)
   vs a defender whose atk lands in the `cmp_atk..atk` window -- recurring
   window-defenders were **Talonflame, Milotic, Guzzlord, Gourgeist
   (Super), Dusclops(-S)**. A scoped warm re-dive can target guides/dives
   touching those species. (This was a 2-IV sample, not the full 4096-IV
   grid; a per-IV sweep of just those matchups gives the exact per-guide
   count if needed -- methodology: git worktree at `b1b58f1^` for the old
   battle.py, shadow-XOR pairs only, diff score+winner.)
2. **Roll in bug #4** (slayer disk-cache key omits the focal level cap ->
   stale cross-`--max-level` hits; `scripts/slayer_cache.py`
   `compute_cache_key`). Same machinery, same CACHE_VERSION-bump concern;
   mirror the sweep cache's `focal_max_level` field + add the
   `test_slayer_cache_key.py` level-cap separation case.

Then: fix #4 + #1, warm-re-dive the shadow-involved cells, re-publish. The
killed 2026-06-27 ML bake (45/61 done, pre-#1 engine) is throwaway -- the
warm re-dive regenerates everything incl. the floor-10 limited-mon config.

*(2026-06-25, post-ship arc -- comes AFTER publish/app/Reddit.)* Michael's
call: `--compare-energy` is good enough that we'll want it ON by default
basically always. But capturing post-match energy currently **force-disables
the sweep disk cache** (`deep_dive.py` ~1973: `capture_energy ->
use_sweep_cache = False`) because the cache stores only the float64 SCORE
column, no energy. So every `--compare-energy` dive is a COLD full sim, even on
a re-dive that would otherwise be a warm cache hit. (This is why tonight's
40-dive chain ran cold, and why dropping one UL opponent is an ~80-min re-sim
rather than a fast warm re-render.)

Rework the sweep cache (`scripts/sweep_cache.py`) to ALSO persist the
per-opponent ENERGY column alongside the score column (bump the cache version;
the key already covers moveset/scenarios/bait/engine/gamemaster). Then
`iv_sweep` serves `capture_energy` runs from the warm cache instead of
bypassing it, and `--compare-energy` becomes cheap enough to default ON.
Bundles with the `WonSetCache`-stores-scores follow-up above (same "cache
stores only part of what the warm path now needs" shape). Cold cost unchanged;
this only fixes the warm regression.

**Bundle: merge the ML-sweep and dive sim logic so the ML sweeps cache too.**
*(2026-06-25, same post-ship arc, AFTER the Reddit post -- bundle with the
energy-column rework above.)* The ML IV-guide sweeps (`run_iv_guides.py` ->
`iv_envelope_analysis.py`) run a SEPARATE analysis path from the dive
`iv_sweep`, and they do not touch the per-opponent sweep cache at all -- which
is why the 61-guide Master-league bake is a ~9h COLD job every time the
gamemaster hash changes. Both paths compute the same per-(focal-IV, opponent)
score columns, so they should share the `iv_sweep` + `sweep_cache` machinery:
merging the logic lets ML re-bakes reuse warm columns (a large win) and deletes
a duplicate sim path. Do it together with the energy-column rework above (same
cache, same "cache must store what the warm path needs" shape).

**Also fold in: cache size + stale-version GC.** The on-disk cache
(`~/.cache/gopvpsim/`) is ~45 GB (2026-06-25) and never prunes. Each
engine/gamemaster-hash bump ORPHANS the prior per-opponent columns instead of
overwriting them, so old versions pile up indefinitely: `sweep/` holds 1161
focalhash dirs (124 for `Tinkaton_great` alone -- many of them dead
old-gamemaster vintages), plus `slayer/` (269 dirs) and `iv_envelope/` (143).
Do NOT hand-delete the old caches (Michael's call); the rework should add a
version-aware GC / prune policy (e.g. keep the current gamemaster hash, maybe
N-1, drop older) so the cache stops growing unbounded. Note: an `iv_envelope/`
cache already exists, so the ML path DOES cache its analysis output -- it just
doesn't share the per-opponent SWEEP-column cache, which is the merge above.

## Old/new mechanics user toggle (POST-SHIP, bundles with the cache rework above)

*(2026-06-26, Michael)* Post-ship idea, flagged so it is not lost; do NOT
pre-ship or design heavily yet. If the site/app gets traction, P!P-series /
Worlds competitors may want it for prep, and **Worlds runs on the OLD battle
mechanics**. So expose a user-facing toggle between old and new mechanics on
the dive site.

Light design notes (not yet designed):
- Preference storage: cookies (never used here) vs radio buttons vs a query
  param. Look at what PvPoke does for its "Preview next season" version as
  prior art before picking.
- Sequencing: do this AFTER the cache rework above. The cache work should then
  also (1) key the cache so OUR engine stays at its most-recent level while
  still caching old-vs-new-mechanics results separately, and (2) add the
  stale-version GC (keep the current version, delete old after migrating;
  maybe not fully aggressive). Bundles with the "Sweep cache should store
  energy" and "cache size + stale-version GC" items above (same cache, same
  migration).

## Form-change "starts in alt form" dives + on-page descriptions (POST-PUBLISH)

*(2026-06-26, Michael)* Aegislash got fixed pre-launch (relabeled "Starts
Blade" + a top-of-page form-change note on both GL dives) because it was the
only form-change dive that read as confusing on the site. The rest is
deferred post-publish:

- **Mimikyu "starts busted" dives, GL and UL.** Rationale: real battles are
  3v3 with switching, but once Mimikyu is in Busted form it stays Busted for
  the rest of the battle regardless of swaps, so a "starts in Busted form"
  dive is legitimately useful (unlike a transient mid-fight state). Add a
  GL and a UL "starts busted" dive alongside the existing Disguise-intact
  dives. Mirrors the Aegislash (Blade) "starts in alt form" pattern: a focal
  species started in the alt form, form change still live.
- **Form-change descriptions on the Mimikyu dives** (disguise absorbs the
  first unshielded charged hit -> 1 dmg + permanent -1 def, then Busted for
  the rest of the battle). Reuse the `_FORM_CHANGE_NOTES` mechanism added in
  `scripts/deep_dive.py` (keyed by focal speciesName) -- just add Mimikyu
  keys; keep it qualitative/factual like the Aegislash notes.
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

## Pre-ship execution order (2026-04-18, for 2026-05-09 CD)

Pre-ship arc shipped: items 1-6 all done (cross-form re-dive,
JRE/RyanSwag comparison, F1-F5, P1-P5 polish, Mirror CMP reframe,
mirror-tier synth backfill, Dewgong flavor-name fix `dede396`), and the
site was published via `scripts/publish_website.sh --push` (2026-06-07).
Post-ship items formerly tracked as post-S5 arc S13-S17
(matchup-flip attribution, post-debuff breakpoints, bait policy) now
live in this file's "Analysis goals" / "Policies to add" sections —
the arc plan file was retired. The open follow-ups below are the
residue.

(HTTPS on the website, the Oinkologne NAIC re-dive, the full oracle
harness audit, and the Morpeko form-toggle resolution all shipped
2026-06-06/07 — see CHANGELOG.md.)

### Open follow-ups from the pre-ship arc

- **G16 — methodology-details guide pointer.** Replace the
  in-article hidden-but-present methodology prose with a one-line
  guide pointer (the hide layer is already in place; G16 is the
  last-mile substitution). Logged in
  `docs/jre_ryanswag_comparison.md` §14.4, ~30 min.

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

- **Aegislash UL apply — DISSOLVED 2026-06-11.** The S6 full re-dive
  regenerates all three candidate dives with envelope tags computed
  natively, so the retrofit patcher question is moot (patcher deleted
  in S7, 2026-06-12, along with the rest of the retrofit patcher set).
  Only relevant again for a page deliberately never re-dived — which
  would now need a fresh script.

- **Cross-form opponent expansion (parked).** Item 4 (auto-
  form-sibling expansion in `build_opponent_pool.py`) — design
  done but parked pending review of rendered Oinkologne article;
  decide pool-level vs render-level filter for hypothetical-form
  rows. See memory `project_form_change_pool_expansion_parked.md`.

## Deferred cleanup: backwards-compatibility removal pass

**S7 RAN 2026-06-12** (arc S7, Michael's greenlight 2026-06-11; see
CHANGELOG). Shipped: the §I dead-code register of
`docs/reviews/2026-06-11_fable5_deep_codebase_review.md` (E12
intended_pruning, L8 cmp_threshold, D11 set, static generate_html +
hover_text + load_thresholds bundle, R6 analyze/augment fossils, R14,
T5, 20 dead scripts incl. all retrofit patchers except the chain-live
patch_dive_species_narrative), plus this section's get_final_form and
intended_pruning candidates, plus the legacy/historical/backcompat
grep audit (nothing further actionable — remaining hits are protected
gobattlekit seams, live CLI surface, or documentation).

Still open (deliberately NOT cut in S7):

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
  current baseline 153 cells = 136 exact + 17 documented).

* **Deep-dive workers never wire up form changes — FIXED 2026-06-10
  (arc S1)** — `_sweep_worker` / `slayer_iter_worker` (and the phase-1
  screen via `make_battle_pokemon`) now thread IVs + level through the
  profile tuples / `opp_cache` and call `attach_form_change`, on BOTH
  the focal and opponent side. Form-change species sweep per-IV
  instead of per-stat-profile (alt-form stats depend on raw IVs +
  level; measured cost only 1.1-1.35x more sims, those species only).
  Equivalence pinned by `tests/test_dive_worker_form_change.py`
  (worker == `from_pokemon` == PvPoke oracle 773 cell). Smoke dive
  delta: Aegislash (Shield) UL top-IV avg score 237.9 → 390.7.

  **S6 targeted re-dive list (consequence of the old bug):**
  1. **Aegislash (Shield) GL + Aegislash (Blade) GL** — focal-side;
     biggest deltas (published dives simmed Shield with no Blade
     transform at all).
  2. **Every dive using `gl_top50_plus_cs.txt` or `ul_top60.txt`** —
     i.e. the whole website chain: `gl_top50_plus_cs.txt` carried
     Aegislash (Shield)+(Blade), so every GL dive's Aegislash opponent
     rows were simmed form-change-less. S6's full re-dive covers this;
     do NOT trim S6 to "just the form species." (`ul_top60.txt`, renamed
     from `ul_top60_plus_aegislash.txt`, no longer carries Aegislash as of
     2026-06-25 — not UL-viable.)
  3. **Blade-vs-Shield GL comparison page** (and the form-change
     guide screenshots if numbers moved visibly) — regenerate after
     the Aegislash re-dives.
  4. Mimikyu (no published dive — applies if/when dived) and Morpeko
     (in no current pool — applies when a pool adds it) need nothing
     now; the plumbing already covers them.

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

## Policies to add

* **Re-optimize the new-mechanics decision layer (POST-SHIP, deferred
  2026-06-24).** Phase 1 shipped pure plumbing: under `--mechanics new` the
  decision layer runs LEGACY decisions, which corpus-testing showed are
  near-optimal on the new clock (the post-mortem-charged-survival resolution
  property already delivers the edge a decision change would chase). BUT we
  knowingly leave a real, reproducible sub-optimality on the table: there is a
  floor-clean win (Aegislash (Shield) vs Talonflame (Shadow) [0,0] 515->595 via
  `decisive-commit globalmax@1.25`) we dropped as a single edge cell, and we have
  no *generalizable* counter-strategy — every broad "commit early because I'll
  die" formulation breaks the no-regression floor on shield-bait-timing species
  (Tinkaton/Mantine/Jumpluff-S/Quagsire-S) because the opponent baits/farms
  instead of throwing. Full writeup, the specific cases, why nothing generalizes,
  the recommended DP-internal direction (`_calc_turns_to_live`/`fire_now` made
  natively charged-survives-death-aware), the resume harness
  (`scripts/corpus_policy_driver.py` + the non-regression floor methodology), and
  the coverage gaps (GL-only — UL/ML untested; curated ~20-focal subset) all live
  in `docs/validations/new_mechanics_decision_layer_2026_06_24.md`. Come back to
  this after launch.

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

(Form Change shipped 2026-04-14 for Morpeko/Aegislash/Mimikyu;
bait-axis as a deep-dive sim dimension shipped; DP cycle-timing
move selection closed 2026-04-15 as not-a-real-issue.)

* **Energy-lead axis (safe-switch / closer matchup flips)**
  *(scoped 2026-06-03 during Shadow Sableye build advice
  conversation; needs its own session)* — Currently the battle sim
  always starts both Pokemon at energy 0. Real PvP often has the
  focal species arrive with energy carry-over: a **safe switch**
  brings the back-line attacker in with some fast moves already
  generated before the original swap; a **closer** has typically
  burned several fast moves before the opponent's final mon comes
  out. The same matchup can flip win/loss depending on whether the
  attacker enters with 0, 1, or 2 fast moves of accumulated
  energy.

  Implementation sketch (analogous to the shipped bait_shields
  axis):

  1. **Battle-engine plumbing** — `BattlePokemon.__init__` gains
     an `energy: int = 0` parameter (it likely already has the
     field as state; the change is making it an init arg that the
     sim honors at T0 instead of forcing 0). Symmetric defender
     energy too, for completeness (defender carry-over scenarios
     are rarer but exist).
  2. **Sim axis** — `deep_dive.py` already enumerates
     `(IV × moveset × opp_iv × bait × scenario)`. Add an
     `energy_lead` dimension with concrete values keyed off the
     attacker's fast-move energy generation: `[0, fast_energy,
     2*fast_energy]` = `[0, 8, 16]` for Shadow Claw, `[0, 10, 20]`
     for Counter, etc. Three buckets keeps the aggregator
     tractable.
  3. **Aggregator surface** — extend `_find_matchup_boundaries`
     and `_aggregate_flips_by_anchor` to detect when a matchup
     flips between energy-lead values. Natural display surface:
     the existing "Matchup-Flipping Boundaries" section, with
     a new line per matchup like "Flips vs Galarian Corsola
     1v1 when attacker has 1+ Shadow Claw of stored energy."
  4. **Cap on realistic values** — energy-lead values above
     `(max_energy - cheapest_charged_cost)` aren't reachable in
     practice (you'd have already thrown the charged move). The
     axis values need to be clamped per attacker; otherwise the
     analysis surfaces unreachable matchup flips.

  **Use case** — safe-switch / closer mons (Sableye, Quagsire,
  Drapion, Wigglytuff, Lickilicky, anything that eats a shield
  then comes back) are exactly the species whose dive
  recommendations are most miscalibrated against the energy-0
  assumption. After landing this axis, every shipped dive in the
  scope-fits category benefits.

  **Estimated scope** — half a day for the battle-engine change +
  axis plumbing in deep_dive.py; another half-session for the
  aggregator + matchup-flip narrative integration. Tests:
  parameterize existing oracle tests with `[0, 8, 16]` starting
  energy and confirm the deterministic ones still match.

  **Cross-ref**: bundles naturally with the "matchup-flip
  annotations" arc already in progress (under "Analysis goals"),
  since both extend the per-matchup flip aggregator.

  **Empirical precedent (2026-06-03):** the one-off script
  `scripts/check_sableye_energy_lead.py` validates the feature
  concept end-to-end against a real build decision. It sims 4
  candidate Sableye IVs × 4 movesets × 66 opponents × 9 shields ×
  {0, 8, 16} starting energy = 28,512 matchups in under a minute
  on 1 CPU. Findings that confirm the feature is worth the
  scope:

  1. Energy lead reshaped **~50 of 594** per-(IV, moveset)
     matchups in this case (2/11/13 + Drain Punch + Foul Play
     went 332 → 355 → 383 wins, +15% across the energy axis).
  2. The IV ranking was stable across energy levels for this
     pool — 2/11/13 won at energy 0 AND at energy 16 — so the
     feature doesn't reverse stat-product-based IV choices, it
     surfaces *additional* matchup data on top.
  3. The script's hack (mutate `bp.energy` after
     `make_battle_pokemon` returns; `BattlePokemon.initial_energy`
     already exists at the engine layer) confirms only the sim
     axis + aggregator + display surface need building — the
     battle engine is ready.

  When implementing the feature, fold the script's structure
  (per-IV, per-moveset, per-energy aggregate table + matchup-flip
  list) into the deep_dive.py aggregator output. The throwaway
  script can be deleted at that point — its existence is logged
  here for the precedent + the mutation-hack pattern that proved
  the engine-side feasibility.

  **Counter-intuitive cross-check (2026-06-03) — keep as a
  regression test when the feature ships:** the same one-off
  script run on 0/15/15 (rank-1 stat product) vs 2/11/13 (the
  pick that won via stat product alone) across the same energy
  axis showed 0/15/15 *gains more wins from energy lead than
  2/11/13 does* (+92 / +231 wins at 1-fast / 2-fast lead vs
  +80 / +217 for 2/11/13). This contradicts the natural intuition
  that "energy lead favors high-atk IVs because the first charged
  move hits harder" — for high-power moves that opponents shield
  with high probability (Foul Play 65-power in this case), the
  post-shield chip war is what the fight comes down to, and bulk
  wins chip wars regardless of the swing-throw dynamics. When the
  feature lands, Shadow Sableye should be a calibration-test
  species: if the aggregator surfaces atk-favored IVs as bigger
  energy-lead gainers for Sableye-class species (high-power
  shield-bait charged moves + Foul-Play-like primaries), that's a
  feature bug, not the genuine matchup math. The shape to look
  for: bulk-leaning IVs should gain MORE matchups as energy lead
  rises, against opponents whose damage profile rewards
  longevity over burst.

## Tests to add

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

* **Reverse-engineer anchor intent from tournament CPs — TRIED, ABANDONED
  (don't re-queue).** The idea was to take dracoviz per-mon CPs, enumerate
  4096 IVs × valid levels per entry, filter to the matching CP, and cluster
  the candidates into anchor categories to infer what spread each player
  aimed for. Attempted; **there just isn't enough data** — a single CP value
  is consistent with too many IV/level spreads to constrain the anchor, and
  the tournament field is too small to disambiguate by aggregation. Dead end
  with currently-available tournament data; only revisit if a far larger /
  richer per-mon dataset (e.g. actual IVs, not just CPs) appears.

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

* **Visualize where stat product misleads (stat-product as a Color By
  option + battle-score y-axis)** *(requested 2026-06-24)* — Make it easy to
  SEE at a glance when ranking by stat product is a bad guide. Two pieces:
  (1) add "stat product" (or stat-product rank) to the interactive scatter's
  Color By dropdown (currently HP/Def/Atk); (2) offer battle score (avg,
  and/or per-scenario wins) as the y-axis. Then a high-stat-product (bright)
  marker sitting LOW on the battle-score y-axis visually exposes the
  mismatch — exactly the "stat product != performance" cases (low-DPE or
  level-capped mons where the attack step between adjacent IVs is tiny, so
  premium-bulk IVs and high-atk IVs perform nearly the same). Cross-ref the
  wins-based-y-axis work in the "RyanSwag-style matchup-flip annotations +
  wins-based y-axis" item above (shared y-axis machinery) and the clustering
  item (Color By already reveals banding). Don't build in the
  new-mechanics session.

* **Send acidicArisen a Discord message about the Lurgan 102.9 def floor**
  — Our 2026-04-08 bulkpoint Level 3 enumeration against the Annihilape
  mirror found that the historical Lurgan Ape `def ≥ 102.9` floor is
  *unrecoverable* from current sims: the next bulkpoint above 102.9
  (`shadow_ball ≤149` at def 103.34) is unreachable for today's
  converged cohort (max def ~101.30). The 102.9 floor predates Rage Fist,
  so the threat-move set has shifted. Ask acidicArisen whether the
  historical calibration was against a Counter or Close Combat tier
  transition, or against something more niche (Shadow Ball / Night Slash).
  This is the missing context that would let us promote a specific
  bulkpoint to a Level 1 anchor with full provenance.

## Slayer card UX (post-bulkpoint shipped 2026-04-08)

* **Slayer-card signal-loss — REMEDY SHIPPED 2026-06-11 (Michael's
  pick: the 4+3 hybrid).** Slayer Builds tables now hoist parents
  cleared by EVERY emitted build into a single "Every build below
  clears:" callout (option 4) and rarity-code the remaining per-row
  badges by within-table clear rate (option 3; ≤25% hot, ≤60% mid).
  Verified on the Oinkologne replay: all 143 parents hoisted, ~360KB
  lighter HTML, rows read "common set only" — which surfaced the
  deeper diagnosis: **Anchors-First saturation is STRUCTURAL**
  (membership = clearing the max parent set), so within-table
  differentiation lives in the CMP%/atk columns by design. The S2
  note's "all-counted-parents membership or tighter selectivity gate"
  is the follow-up if real within-table spread is wanted. The
  SYSTEMIC audit below (other surfaces: threshold-tier dropdown,
  banding, Notable-IVs badges) remains open. *(original entry kept
  for the audit scope:)* — With Level 3
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

  **Observed instance — Oinkologne GL (2026-04-19).** Dive 1 of the
  overnight re-dive; Mud Slap / Body Slam / Trailblaze scatter under
  `userdata/website/oinkologne-great-league/index_m0_*.html`. Slayer
  IVs (yellow markers) cluster in the top-RIGHT of the scatter — i.e.
  rank-1-ish stat product *and* high avg battle score — instead of
  the traditional Lurgan-Ape-style LEFT-cluster where slayers sit at
  worse bulk in exchange for higher attack. Mechanism: Oinkologne
  caps at level ~22-23 at GL CP, so the atk range across IV spreads
  is narrow, *and* Mud Slap's low DPE means the damage step between
  adjacent atk values is small — so the slayer atk breakpoint lands
  below where rank-1-bulk IVs already sit, making the "slayer" tag
  non-discriminating against premium bulk. Concrete real-world
  instance of the signal-loss concern this TODO flags. Worth using
  as the first test case when the audit happens; if the chosen
  remedy doesn't differentiate the Oinkologne scatter, it's not
  solving the problem.

* **"Show clusters" section is always visible** — it sits above the
  interactive scatter plot but should be gated behind the "Show
  experimental analysis (banding, clusters)" checkbox in the Deep Dive
  Analysis section. The checkbox already toggles `#dd-alpha` and
  `#dd-alpha-methods`; the cluster-display block needs to either move
  inside `#dd-alpha` or be hidden by the same JS handler. Discovered
  2026-04-08.

## Slayer iteration cleanup

* **Mirror-slayer re-look — RESOLVED 2026-06-10 (arc S2).** Archetypes
  + graded tie metric shipped per Michael's four design decisions;
  full writeup in CHANGELOG.md (2026-06-10 S2 entry). The dracoviz
  tournament-CP item under "Analysis goals" could eventually supply
  an *empirical* mirror population to replace the Nash pool.

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
  to reflect acidicArisen testimony (Discord, 2026-04-08) and the
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

* **Orphaned-artifact detector for the publish pipeline** *(noted
  2026-06-21 during the PvPoke-attribution site-wide re-render)* — Stale
  files accumulate under `userdata/dives/` and `userdata/website/` that
  nothing links to and that were simply never deleted. Concrete instance
  found: some ML IV-guides have BOTH a current
  `<slug>_iv_envelope_all9.json` (the canonical `--all-shields` artifact
  the site is built from) AND an older-format `<slug>_iv_envelope.json`
  left over from before the all-shields switch. The site links only to
  the `_all9`-derived guide HTML; the plain-`_iv_envelope` JSON (and any
  HTML it once produced) is an orphan. (This is why the re-render had to
  dedup-by-slug-prefer-`_all9`; that nuance only exists because the old
  artifacts were never cleaned up.) Build a pipeline step / tool that:
  (a) enumerates generated artifacts (`userdata/dives/*.json`,
  `userdata/website/**`), (b) cross-references what the site index +
  pages actually link to (and what the current renderers would produce),
  (c) reports the orphans for review, and (d) optionally deletes with a
  `--execute` gate (dry-run default, like `scripts/clean_logs.py`).
  Don't auto-delete without the gate. Separate session.

* **Re-render published split-moveset dives** *(follow-up to the
  2026-06-10 split-analysis-cache fix)* — The fixed bug was worse than
  the original "wrong subheader" report: from 2026-04-12 to 2026-06-10
  every NON-LANDING split file shipped **moveset 0's entire analysis
  sections** (Deep Dive Results, tier cards, anchor bullets, matchup
  boundaries), not just its label. The landing page (moveset 0) of
  each dive was always correct. Any split dive published in that
  window needs a re-render (`scripts/run_website_dives.py` →
  `publish_website.sh`) for its secondary moveset pages to show their
  own analysis. See DEVELOPER_NOTES "All-in-one vs split-moveset
  HTML" history note.

* **Mirror-slayer iteration tables blow up HTML size for high-anchor
  species — MECHANISM REMOVED 2026-06-10 (arc S2)** — the redesigned
  Slayer Builds renderer emits at most 100 rows per archetype table,
  drops the per-row `data-anchors` attribute entirely (the filter-panel
  JS that consumed it is deleted), and the tie-explosion fix caps the
  survivor pool at `--mirror-slayer-pool`. The 60.7MB pathology can't
  recur on future renders; re-dive Jumpluff (S6) to shrink the
  published file. Historical detail below kept for the record.
  *(original entry, 2026-06-05)* —
  Jumpluff regular GL dive HTML is 60.7 MB (vs Ninetales 15.2 MB,
  Shadow Sableye 17.6 MB, etc.). 47 MB of the 60 MB lives in the
  analysis-sections body, almost entirely in two tables:

      ms0-slayer-1-table   12.0 MB  (vs Ninetales 0.31 MB)  37x
      ms0-slayer-2-table   33.6 MB  (vs Ninetales 0.72 MB)  44x

  Mechanism: each row enumerates its anchor membership inline via two
  bloated paths. Per-row HTML is ~9,696 bytes, and slayer-1 alone has
  1,608 rows.

  1. `<tr ... data-anchors="0 1 2 3 4 ... 1607">` — space-separated
     list of every anchor-index the IV passes. For Jumpluff (3,161
     resolved anchors, 133 parents, 1,607 IVs in round-3 mirror-
     slayer pool) the cross-product is ~1607 rows × ~1000+ anchor
     refs per row, all serialized into HTML attributes.
  2. Inline `<span class="dd-anchor-tag" data-t="...">opp_abbrev<span
     class="dd-anchor-tag-count">xN</span></span>` per opponent that
     the IV passes, repeated per row. For Jumpluff this is dozens of
     spans per row times 1,608 rows.

  Ninetales has the same renderer path but ~280 anchors and a much
  smaller pool, so the cross-product stays under 1 MB per table.
  Bug is pre-existing (not introduced by recent renderer work);
  Jumpluff just happens to be the first species where the anchor
  count + pool size hit the pathological corner.

  **Open meta-question before optimizing — do we even need this so
  accessible?** Michael's framing 2026-06-05: "the mirror slayer
  code isn't perfect yet." If the underlying mirror-slayer logic is
  still likely to change substantively (anchor enumeration heuristics,
  pool-shrink criteria, score-margin tiebreaks, etc.), heavy renderer
  optimization is premature investment in a moving target. The
  cheaper path is to *demote* the mirror-slayer iteration tables —
  put them behind a collapsed-by-default `<details>` (or behind the
  experimental-analysis toggle that already gates clusters/banding)
  — until we have higher confidence that the displayed numbers are
  worth surfacing prominently. That's near-zero renderer work and
  immediately reduces user-facing surface area for code we're not
  yet ready to ship-quality-promote. Decide demote-vs-optimize
  before picking from the optimization options below.

  **Optimization options** *(only relevant if mirror-slayer is
  promoted from "experimental" to ship-quality output)*:

  1. **Compress data-anchors to a per-IV bitmap** in the DATA blob.
     1,607 IVs × 3,161 anchors = 5M bits = ~640 KB compressed via
     base64. Each `<tr>` gets `data-iv-idx="N"` and the JS resolves
     the anchor set from the DATA bitmap at hover time. ~10x size
     reduction; cleanest fix.
  2. **Cap displayed rows to `--mirror-slayer-show`**. The chain
     passes `--mirror-slayer-show 20` but the rendered table emits
     all 1,608 rows. Likely the flag only affects log/summary output,
     not the HTML rows. Wire it through. Simple win.
  3. **Truncate anchor-tag spans per row** to top-N opponents
     (`tin×5 tog×11 ... +24 more`). Cosmetic; doesn't help if data-
     anchors stays inline.
  4. **Move per-row enumeration into a collapsed `<details>`**.
     Same total bytes; lazy-loaded in the browser. Doesn't fix file
     size; only helps initial render latency.

  The right combo when ship-quality time comes is probably (1) + (2):
  cap rows to the flagged N, then bitmap-compress what remains.
  Until then, demoting the section gives most of the operational win
  for none of the engineering cost.

* **Non-interactive `generate_html` — RESOLVED 2026-06-12 (arc S7)**
  — the static path was deleted outright (it had been crashing on a
  `NameError` since the S1 era with nobody noticing). `--html` now
  implies `--interactive`, so the old smoke-test trap (run without
  the flag, conclude nothing rendered) is gone too.

## Dive card — open follow-ups

*(Shipped 2026-06-22, commit e6ff5af: compact screenshot-able spec-sheet
card atop every dive + standalone `--card-out` export, with two headline
win-rates — single-IV and a top-512 opponent-IV robustness number. Built
to reproduce the Dragapult-Sim/Lundberger infographic look. First dive:
Shadow Corviknight GL pre-release, `userdata/dives/shadow_corviknight*.html`.)*

* **Card "High HP" pole surfaces a strictly-dominated spread (BUG, flagged
  2026-06-24).** On the UL Mimikyu card the High HP pole highlighted
  `0/15/15` (148.7 atk / 179.8 def / 135 hp, **CP 2319** — nowhere near the
  2500 cap — SP #702, NO crown marker). That spread is strictly dominated:
  `1/15/15` has the same def + hp but higher atk. We should never headline a
  strictly-dominated spread. Likely causes / fixes to weigh:
  (a) **The real disqualifier is the STATS, not the CP** — `0/15/15` is bad
  because it is strictly dominated (`1/15/15` weakly-dominates it on
  atk/def/hp), not merely because its CP is low. Primary fix: a
  strict-dominance filter (drop any candidate that another reachable spread
  weakly-dominates on atk/def/hp). Do NOT hard-gate on CP — a far-from-cap
  spread can still be worth building (e.g. a meta-relevant mon that maxes at
  L51 and still never reaches the league cap). If CP is used at all it is a
  soft clue only, and the right comparison is "far below the MAX achievable
  CP for THIS species in THIS league" (already accounts for L51-capped mons),
  never "far below the league cap (2500)"; (b) consider REQUIRING the crown
  marker (or whatever marks a
  rank-relevant / non-dominated spread) for a spread to appear on the top
  card — open question whether to hard-require it. Pick after looking at the
  pole-selection code. Cross-ref the spread-selection rework in "Upcoming
  plan-mode session" item 4 (distinctness-gated greedy cap) — this is the
  same surface; fold the dominance/CP-floor fix into that work or do it as a
  focused card-pole bugfix first. Concrete repro: UL Mimikyu card,
  Shadow Claw / Play Rough + Shadow Sneak. Do NOT fix in the new-mechanics
  session.

* **Opponent-IV robustness as a first-class sim axis (plan item 1.8).**
  Today `opp_iv_robustness` is computed ad hoc for the rec IV only, as a
  card headline. A full opponent-IV dimension in `deep_dive.py` (parallel
  to the bait / energy-lead axes) would let the WHOLE analysis report
  robustness per matchup (not just the headline) — e.g. "this IV beats
  G. Stunfisk regardless of which top-512 IV it rolled." Larger effort;
  cross-ref the "attack-weighted opponent variants" entry (same
  opponent-IV-variance theme) and the Tinkaton/Altaria shadow-IV-variance
  caveats. Do NOT build until there's a concrete consumer.

* **Robustness headline speed — signature dedup landed, gain modest.**
  `opp_iv_robustness` now uses the damage-signature dedup
  (`deep_dive_signature.signature_groups`) for fixed-form opponents
  (`dedup='signature'`, default), verified bit-identical to no-dedup
  (`test_opp_iv_robustness_signature_dedup_is_exact`). But the top-512
  stat-product cohort has diverse damage signatures, so it only collapses
  ~1.5× (less for shadow opponents) — the ~5.5 min full-pool headline drops
  to ~3.5-4 min, not the 4-5× originally hoped. `--card-robust-k` still
  caps the cohort for fast smokes. If robustness needs to be genuinely fast
  (e.g. card on every published dive), the lever is caching the per-(focal-
  IV, opponent) robustness result, not tighter exact dedup (1.5× is the
  exact-dedup ceiling here).

* **`deep_dive_signature` CMP column — FIXED 2026-06-22, NO published
  pollution found.** `signature_groups` built the CMP column from
  *effective* atk, but the engine decides CMP on unboosted `cmp_atk`
  (2026-06-13 fix). For shadow-MISMATCHED pairs the two boundaries differ by
  the ×1.2 shadow factor, so a profile could in principle mis-group.
  **Measured impact first:** focal sweep with signature-dedup vs the
  CMP-safe path across 12 shadow-mismatched matchups (both directions, incl.
  the published shadow dives), all 9 shields, all 4096 IVs = 442,368 cells →
  **0 differences**. Reason it never bites: two IVs share a signature group
  only if their *damage* tables match, which pins effective atk to a band
  finer than the 20% CMP gap, so a group can't straddle the real CMP
  boundary. Fixed anyway for hygiene: threaded each side's shadow flag into
  the side struct and compute the CMP column on `atk/1.2` (same-shadow and
  non-shadow pairs are unchanged by construction). Also closed a latent
  cache gap: `engine_hash` now hashes `scripts/deep_dive_signature.py`
  (covers BOTH sweep + slayer caches; slayer reuses engine_hash). No re-dive
  needed.

* **`_species_has_form_change` keys on the form name (latent nit).** It is
  exact for today's meta only because the sole stat-divergent form-change
  opponent (Aegislash) is pool-named by a formChange-bearing form. A future
  stat-divergent toggle/set species whose pool name lacks the formChange
  key (cf. Morpeko (Hangry), harmless today since its forms share
  baseStats) would be silently misgrouped by the robustness dedup. Fix by
  resolving to the base speciesId and checking both forms if that ships.
  (Comment in place at the function.)

* **Sprite slug for non-base forms.** `sprite_data_uri` derives the
  pokemondb slug from the PvPoke speciesId; regional/gendered forms
  (`farfetchd-galarian`, `indeedee-female`, ...) may not match pokemondb's
  path and 404 → graceful CSS typing-block fallback. Add a slug-override
  map only if/when a non-base-form dive wants its real sprite.

## Upcoming plan-mode session: dive/article content + information architecture

A dedicated plan-mode session (fresh, not mid-stream) to settle WHAT the
dives/articles/card show and HOW it's organized, before nailing down card
placement. Scoped with Michael 2026-06-22. Collected items:

1. **Articles vs dives distinction.** It's murky. Today: a *deep dive* =
   one species' full interactive IV/moveset analysis; a *CD article* =
   editorial CD-move writeup linking to dives; *ML IV-guides* = a third
   thing (XehrFelrose-style). Decide: merge, or rename "CD articles" ->
   "articles" + clarify the taxonomy + site nav.

2. **Dive content + organization audit.** Some info looks
   duplicated/overlapping across sections; the organization may not be
   clear. Take a hard look at what a dive should show and in what order
   (this is the "what should the dive actually present" question, which is
   why it's plan-mode not a patch).

3. **Card placement.** Graph-as-headline vs card-at-top. The card injection
   point is a ~one-line move; decide AFTER 1+2. (Card currently sits above
   "Deep Dive Results", below the interactive scatter.)

4. **Breakpoint-coverage card spreads (was card item 3).** The current
   spread selection (top-3 rec_candidates by composite score) clusters near
   rank-1 -- e.g. Shadow Corviknight showed 0/13/14 (SP#1) and 0/12/14
   (SP#4) as near-twins. Replace/augment with a HYBRID: keep our anchors
   (rank-1 bulk + max-atk/CMP) + add breakpoint-coverage spreads (each
   targeting a named opponent's break/bulkpoint, using the anchor data we
   already compute), and dedupe near-identical spreads. Variable **2-6**
   spreads via a **distinctness-gated greedy cap**: order by priority, add a
   candidate only if it clears/wins a materially different set than those
   already shown; floor 2 (bulk + attack poles), cap 6, stop early when no
   candidate adds distinct value; tunable threshold. Consider also a
   "newly-cleared breakpoints" list like Dragapult-Sim's "18 guaranteed
   breakpoints".

5. **ML IV-guide article enrichment (Michael loves these; strong automation
   example).** Today they report net wins/losses -- the biggest part of the
   story. Add the matchup-QUALITY delta: gained/lost break/bulkpoints that
   meaningfully change post-match state (how much HP/energy we vs the
   opponent have left), EVEN WHEN the win/loss doesn't flip. E.g. "still
   wins vs X but banks a charged move of energy for the next mon" or "loses
   the bulkpoint vs Y so you eat one more Y charged move". We already
   compute break/bulkpoints (anchor system) and have post-match HP/energy in
   the sim; this is surfacing the MARGIN, not just the binary flip. Connect
   to: the energy-lead axis (post-match energy carry-over), post-debuff
   breakpoints, and the matchup-flip annotation work. Generated from sim
   data, no hand-authoring -> stays ship-mode clean.
   **CLUTTER is the central design risk (Michael, 2026-06-22): he wants to
   explore this but NOT at the cost of the articles' concision** -- their
   value is partly that they're clean and scannable. So this is a "surface
   the MEANINGFUL margin deltas only" problem, not "show every
   break/bulkpoint": needs a significance filter (only deltas big enough to
   change a shield/energy decision) and likely progressive disclosure
   (collapsed-by-default detail / a one-line summary / top-N), consistent
   with the project's "hide don't remove" + signal-loss patterns. Decide the
   default-visible surface vs the drill-down in the plan session -- overlaps
   directly with audit item 2 (content + organization).

## CD article generator — open follow-ups

The Python article generator (`scripts/generate_article.py`) shipped
across Post-S5 Sessions S6-S10 (2026-04-17/18). Open polish:

- **S8 envelope-annotation wiring on the article surface** — S4's
  `envelopePositions` dict is keyed by Notable-IVs category name
  (`Atk Slayer`, `Lapras Atk`, etc.); the article's IV
  Recommendations section renders `tier` cards (stat-cutoff-based,
  from `data_obj['tiers']`), so the annotations don't have a natural
  slot. Two paths: (a) add a Notable-IVs card block to the article
  IV-recs section and annotate those directly, or (b) build a
  tier-name → category-name mapping and attach the envelope annotation
  to whichever tier exposes the anchor that backs the category. (a)
  is simpler but duplicates dive content; (b) reuses presentation
  but needs a naming bridge. Defer until someone has an opinion.
  Watch item: when S8 lands, audit `render_notable_ivs_section`'s
  UX caps (`notable_max_count=5`, `max_members_shown=5`) under the
  extra shape-tag line.

## Deep-dive narrative — open polish

* **22-IV catch-phrase edge case** — `_catch_phrase` caps at 500
  catches as "very rare". The 22-IV Altaria Slayer on Goodra moveset
  4 shows `~129-258 for a 50-75% chance` — under the cap but still
  a large number; arguably should have a middle "rare" tier. Wait
  for more species in the 50-300 range before adding a tier.

* **Narrative flavors not reflected in Plotly scatter tiers** —
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

* **RyanSwag-style autogenerated deep-dive section** *(own arc, scope
  after post-S5 arc ships)* — With the narrative renderer,
  namesake/merge/conformance fixes (S5a), article generator (S6-S10),
  histogram (S3), envelope metric (S4), matchup-flip attribution (S13),
  post-debuff breakpoints (S15), and bait-axis-in-narrative (S17) all
  shipped, revisit whether the deep dive (or a dedicated section of it)
  should autogenerate a prose output that looks like a RyanSwag
  GamePress article — same 5-part structure (intro, moveset discussion,
  PvP IV tables, per-league analysis, wrap-up), same prose style, but
  generated from our simulation data instead of Claude mimicking
  RyanSwag's voice. Not a session in the current post-S5 arc: (a)
  that arc is already 17 sessions + Aegislash, bail-prone; (b) the
  shape depends on what the renderer ends up capable of after S5a/
  S6-S10 settle. This is its own arc when the time comes.
  **Prerequisite check before opening**: confirm S5a items C1/C2/C3/C5
  shipped (name-signature coupling, namesake guarantee, 2-axis support,
  identical-stat merge). Those fixes are the RyanSwag-conformance
  floor; autogen doesn't make sense on a renderer that still produces
  name-signature mismatches. Separate from the JRE/CD article work in
  S6-S10, which has a different audience and format — **don't conflate
  them**; the CD article is mechanical spec-sheet + data tables, this
  is narrative prose structured like RyanSwag's articles.
  Flagged 2026-04-17 by Michael.

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
  *Update 2026-06-10 (arc S4):* the sweep disk cache key now hashes
  gamemaster content and keys opponents by their *resolved* IVs +
  movesets (see DEVELOPER_NOTES "Sweep disk cache"), so cached scores
  can never silently mix data vintages — but the HTML fingerprint /
  run-start logging for human-visible drift detection (options 1+3)
  remains open.

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

* **Client-side add / remove anchors + thresholds** *(mercuryish
  request, 2026-04-26)* — Today's TOML-edit flow requires a local
  clone, a re-dive, and a PR. Mercuryish asked whether a per-species
  in-browser surface could let readers add their own custom anchors
  (or hide existing ones) on a single dive without affecting the
  rest of the site. Use case: cut visual noise by hiding anchors
  the reader doesn't care about, or pin a custom matchup the dive
  doesn't already surface. Scope:

  1. **Hide**: a per-tier-card "hide this anchor" toggle that
     adds/removes the anchor from the rendered bullet list and the
     scatter-plot tier coloring. Pure client-side; saved to
     `localStorage` keyed by dive slug. Should be the easier of
     the two paths.
  2. **Add**: a "create custom anchor" surface that lets the reader
     pick an opponent + threshold and have it render on the current
     dive's tier cards / bullets / scatter. Harder — the threshold
     would need to be evaluated against the dive's cached score
     data without re-simulating. Possibly limited to "stat cutoff
     only, no per-move sub-anchors."

  Until this lands, the Under the Hood guide notes the TOML-edit-
  via-PR flow as the only option.

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

* **Form-change path speedup (Aegislash Shield, Mimikyu, Morpeko)**
  — **MOSTLY RESOLVED 2026-06-10 as a misattribution.** The ~10×
  Shield-vs-Blade gap was dominated by the engine-wide pvpoke_dp
  regression (per-call stage-table rebuild, fixed in `5e25e28` — see
  DEVELOPER_NOTES "Performance baseline"), which Shield's battle shape
  (charge-farm → near-KO DP every turn) amplified. Post-fix smoke
  measurement (Phase 2, 3 opponents, 1v1): Shield 4,800-6,900 sims/s
  vs Blade 5,200-5,700 — parity. The hypotheses below were never the
  dominant cost. Keep this entry only as a pointer: if a future
  mirror-slayer-scale Aegislash (Shield) run still looks slow
  relative to Blade, re-measure before reaching for the plan below.

  *Original 2026-04-19 observation (pre-fix):* Mirror-slayer Round 1
  on Aegislash (Shield)
  projected ~25-30 min per moveset (~10× the Blade-side baseline) at
  ~700 sims/s vs the 7,000 sims/s Phase 2 baseline. Correctness is fine
  (validated by `tests/test_aegislash_vs_azumarill_form_change`); the
  9.5M-sim scale just magnifies the form-change per-sim overhead.

  **Suspected dominant costs** (unprofiled):

  1. `apply_form_change(bp, opponent)` does a full state swap: base
     stats (atk/def/hp), active moveset, `bestChargedMove` reselection,
     per-move cached damage tables invalidated. Fires every time
     Aegislash (Shield) lands its first charged move, which is nearly
     every sim in a mirror-slayer scale run.
  2. Per-turn `attacker.current_form_trigger` / `defender.current_form_trigger`
     property evaluation on every charged-move event, even for species
     with no form change (no-ops but not free). Cheap individually;
     compounded across 9.5M sims it adds up.
  3. Damage-and-timing caches that key on (attacker form, opponent) get
     stale on form change and rebuild from scratch the next call. If
     caching is per-form, the form swap is a mandatory invalidation.

  **Why Shield hits this harder than Blade:** Shield-focal transforms
  on every charged move (every battle). Blade-focal transforms only
  when Aegislash *shields* an opponent's charged move — conditional
  on shield count and policy — so the code path runs much less often.

  **Perf session plan** (~2 hours):

  * `cProfile` or `py-spy` on `scripts/deep_dive.py 'Aegislash (Shield)'`
    with `--opponents 3 --mirror-slayer-rounds 1`, compare to same
    command on Aegislash (Blade). Flame graph diff highlights the
    form-change-only hot path.
  * Likely interventions: (a) precompute both forms' damage tables
    up front and swap by pointer, (b) lazy-invalidate damage caches
    per-opponent rather than per-form, (c) inline the form-trigger
    checks into a single type-dispatch so non-form-change species
    pay zero per-turn cost.
  * Success criterion: Shield mirror-slayer within 2× Blade's rate
    (rather than today's 10×).

  Deferred because correctness is fine and Aegislash isn't on the
  pre-ship critical path. Pull forward if Aegislash becomes a frequent
  dive target post-CD.

## Schema simplification

* **TOML simplification triggers** *(collect friction, don't act yet)* —
  Worry surfaced 2026-04-09: the legacy JSON threshold files were three
  keys; the current TOML schema is ~530 lines of docs and Annihilape's
  hand-authored file is ~180 lines. Sample size of one species (plus a
  one-line tinkaton stub) is too small to design a simplification
  against — Annihilape is also the *worst* canary because its
  Lurgan/acidicArisen historical provenance pressure makes it
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

* **Pain points captured during real debugging** — see memory file
  `project_post_ship_cleanup_pain_points.md` (silent early-returns
  with no logging, no replay-from-saved-state mode, hardcoded magic
  numbers assuming `nS=9`, parallel call-site duplication,
  free-form-string opponent identity, `data_obj`-as-mutable-bag,
  `id()`-keyed caches). Specific friction encountered while
  diagnosing the 2026-04-25 mirror-tier-synthesis no-fire bug;
  read this *before* starting the deep_dive.py split below so the
  cuts address actual pain rather than aesthetic ones.

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
(`build_guides.py`, landing page, dev-count sentinels), plus five
guide bodies: How This Works / Under the Hood, Envelope Position,
Threshold Tiers, IV Flavor Guide, CD Article, Deep-Dive Scatter.
Envelope Position + Threshold Tiers are at `authorship=both`; the
others are still `authorship=ai` pending Michael review.

Open follow-ups:

- **Promote remaining guides from `ai` to `both` / `expert`** as
  Michael reviews and edits each one.
- **Round-3 screenshots** if/when reader confusion surfaces a
  specific gap (round-1 + round-2 screenshots shipped via `32fae84`
  and `e449b38`).
- **Add topics** beyond the five shipped — Michael asked that the
  topic list be a conversation at the start of the task, not a
  fixed scope. Plan a session to (a) add topics surfaced by
  acidicArisen / new readers, (b) reorder by current reader
  confusion, (c) decide whether related topics merge.

The IV Flavor Guide write-up is owed to acidicArisen per
`project_acidic_arisen_writeup_commitment.md` — promoting that
guide from `ai` to `expert` is the closing of that commitment.

## Low priority

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support. When this
  lands, honor `reset_on_switch`: Morpeko must re-enter in Full Belly on
  every switch-in (confirmed in-game 2026-06-06; see DEVELOPER_NOTES §8).
  Also port the MATCH-level 240 s clock (Michael, 2026-06-11): the real
  game's timer spans the whole 3v3, charged-move animations consume it,
  and games are genuinely won on time — see DEVELOPER_NOTES "Battle
  timeout" divergence entry for PvPoke's clock semantics to mirror.

---

Historical/shipped work lives in `CHANGELOG.md`.
