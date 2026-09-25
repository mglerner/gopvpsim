# 2026-09-25 Bake attribution + cruft scout (ultracode, 91 agents, read-only)

Source: friday-big-swing-scout workflow, 10 Opus scouts + 2 Opus refuters per top finding (40/40 survived) + Fable synthesis. Numbers are from the 2026-09-20 chain (userdata/logs/2026-09/overnight_20260920_164044.log and its 136 per-dive logs). Nothing was edited or deleted; this is the plan input.

1. WHERE THE 37.7H GOES (2026-09-20 chain, 135,644 s = 37.68 h; verified figures)

Chain envelope: dive step 134,522 s = 37.37 h (99.2%); all 8 non-dive steps 1,122 s = 0.31 h, of which run_ship_gates 885 s (pytest 413.5 s + link/dash/dev-count scans ~471 s), ML IV guides 194 s (warm), Reader's Guides 29 s, matchup webs 13 s. Inside the dive step, the 136 per-dive logs span 37.26 h; the remaining 0.11 h (384 s) is inter-dive process startup + narrative patcher.

  phase (inside the 37.26 h of dive logs)                   hours   single-core?   note
  sweep sims, pool (signature dedup -> 'N sims in')         15.38   no (18 wkrs)   only 42.2% of 268,024 columns hit; ebf5944 shadow bump ~10-11 h of it (both refuters)
  mirror-slayer sims, pool (L50 0.72 + L51 0.66)             1.35   no             L51 re-convergence runs with cache=None (unverified sub-finding)
  screening                                                  0.10   yes (no Pool)  tail-and-gates read of sweep.py:121-216; trivial either way
  render passes (narrative + analysis + results), 2 per pg  12.38   YES            pass1 6.19 + pass2 6.19; pass2 on the 100 no-op best-buddy dives = 4.61 h pure duplicate
    of which aggregate_flips_by_anchor (8 calls/pass)      ~7.0-8.9 YES            1426 passes x 8 x 2.2-2.8 s; half the calls are exact duplicates
    of which find_matchup_boundaries (24 calls/pass)       ~1.8    YES            16 of 24 per pass redundant (~1.2 h)
  pre-sim sweep setup (rank-1 iv_rank, metadata, lookup)     2.61   YES            ~1.7-2.1 h is uncached iv_rank (63-76 ms x ~63 opps x 1,432 rank-1 sweeps + L51)
  page preamble ('HTML written' -> next narrative)           1.88   YES            ~1.7-1.8 h is uncached iv_rank in _opp_link_data (2 rank1 modes x ~71 opps x 713 pages)
  which_build (once per dive)                                0.70   YES
  page assembly ('Analysis complete' -> 'Writing HTML')      0.63   YES            pack_u16 listcomp + gzip-9, ~3 s/file
  sweep_cache_post (signature grouping) + replay dump        0.32   YES
  system sleep (two clamshell sleeps, 09-21 06:36 + 16:49)   1.82   n/a            Jellicent UL 2134 s / 912 s / 597 s gaps and Charjabug-shadow ~2500 s are sleep, not code
  ------------------------------------------------------------------
  parallel awake 16.83 h / single-core awake 18.61 h / sleep 1.82 h = 37.26 h

Attribution residual: 'Done in' minus log span sums to 240 s over 136 dives (median 1.7 s); the OTHER bucket is 0.000 h. So the unattributed remainder is ~0.1-0.2 h total. bake_timing_report.py's 21.9 h parallel / 15.5 h serial is wrong: it files 'sims in' / 'Running...' / Replay/Split intervals as parallel and has no sleep bucket; the orchestration refuters put true serial at 20.3-20.5 h (54-55%) once the ~2 h of per-sweep fixed cost inside 'sims in' windows is counted, vs 18.6 h by log-attribution's per-second bucketing. Either way: >50% of the bake is one core on an 18-core box.

Corrections to TODO.md:107 (verified by 4 refuters): 'sweep sims were only ~1.4 h' is the mirror-slayer 'sim done in' sum (1.374 h); sweep pool time was 15.4 h. And 'next bake ~35-40 h migrated' is roughly right but NOT nearly-warm: the engine hash is now d78c67fd06a7 (a4ca14e), the built signature migration re-sims 15.3% (43,077 columns), and non-shadow key churn (09-17 pool regen, new movesets) cost ~2.9-3.6 h of all-miss GL sweeps last time.

Combined serial-fix ceiling (inferred, overlaps removed): no-op pass2 skip 4.6 + aggregate dedup/vectorize on the remaining 903 passes ~3.9-5.0 + iv_rank memo 3.2-4.0 + boundaries dedup ~0.75 + pack_u16 ~0.2 = ~12.7-14.5 h off the 18.6 h serial. Same-shape bake 37.3 h -> ~23-25 h; with a mostly-warm sweep cache the serial share would then be ~5 h out of ~10-12 h.

2. RANKED OPTIONS FOR TODAY (rank = payoff x confidence / effort; none touches _ENGINE_FILES = battle/_dp_jit/moves/formchange/pokemon + scripts/deep_dive_signature.py, confirmed at sweep_cache.py:117-138)

R1. iv_rank memo. Memoize resolve_opp_ivs's rank1 branch in scripts/deep_dive_lib/opponents.py (key: species, league, shadow, parse_mode base), NOT in pokemon.py. Saves 3.2-4.0 h/bake (sweep side 1.7-2.1 h + page side 1.6-1.8 h). Effort: hours. Cache hash: none; output ints identical. Risk: one refuter flagged the 'bump CACHE_VERSION for any scripts/ worker-code change' convention (sweep_cache.py:53-57, 78-83) -- resolve_opp_ivs runs parent-side but feeds opp_cache column keys; needs Michael's ruling (Q2). Fallback with zero ambiguity: memo at _opp_link_data in deep_dive.py:1536-1559, captures ~1.7 h. Add cache_clear for tests that swap MOCK_GAMEMASTER. Backed by: log-attribution iv_rank, render-path iv_rank, analysis-path iv_rank, orchestration rank-1 (all 4 survived, 8 votes). Fan-out: one agent.

R2. aggregate_flips_by_anchor: compute once per pass + vectorize. Narrative (render.py:377) and analysis (render.py:950) call it with identical inputs; hand the narrative's records to the analysis (deep copies; callers mutate rec['bait_modes']/['energy_modes'], narrative adds energy_modes). Then replace the Python per-anchor loop (deep_dive_analysis.py:373-516) with the scratchpad prototype (int32 win matrix, mask @ W, memo by partition bytes; identical records on 3 blobs, 4.2-4.8x). Saves 5.9-7.9 h/bake today, ~3.9-5.0 h after R3. Effort: dedup hours, vectorize a day. Cache hash: none. Risk: HP-floor scan order / >= vs > semantics; gate = byte-identical replay diff. Backed by analysis-path finding (2 votes, payoff confirmed or raised). Fan-out: ONE agent for dedup+vectorize+R4 (all edit the same render.py sites).

R3. Skip the no-op best-buddy second render pass. deep_dive.py:5494-5509 sets _bb_noop and aliases scores_l51=scores; :1696 then runs a full second _render_level_body (:2867-2912). Saves 4.6 h/bake (523 pages x ~32 s). Effort: a day. Cache hash: none. Risk: pass2 is NOT byte-identical -- element ids are renumbered and a misleading 'builds pinned to the league cap' note is appended; skipping means dropping the L51 <template> on no-op pages, which changes the rendered artifact and tests/test_dive_dom_ids.py. Precedent already in tree: _bb_section_active (deep_dive.py:3575) skips the no-op which-build section, and deep_dive_engine.js:245-250 _bbInitHost tolerates a missing template (per refuter 2). Backed by log-attribution + orchestration findings (4 votes). Fan-out: one careful hand, after R1 lands (both touch deep_dive.py).

R4. find_matchup_boundaries once per (mode, sweep) per pass (render.py:404 / :760 / :977; deep-copy the mb dicts). Saves ~1.2 h/bake today, ~0.75 h after R3. Effort: hours. Cache: none. 2 votes confirmed. Rides with R2's agent.

R5. Ship-gate step: run the four SHIP_GATES concurrently in run_ship_gates.run_gates and verify_overnight.py:531-541, so the step becomes ~max(pytest 413 s, dash 298 s) = -470 s per roster run; optionally also a per-file pool inside verify_article_links.py / verify_no_unicode_dashes.py (measured 12 workers: 57.7 s vs 503 s, identical 691,888-href output). ~24 min per bake->publish cycle (3 roster runs). Effort: hours. Cache: none. Note: a pass-stamp to skip reruns is worth only ~1 run (~15 min) and publish-time reuse is blocked because build_guides embeds date.today() (refuter-corrected). Fan-out: one agent, fully independent.

R6. Attribution guards (no hours saved, stops the next misdiagnosis): verify_overnight.py greps `pmset -g log` for 'Clamshell Sleep' inside the bake window and goes red; the chain's TTL-touch loop logs a WARNING when wall-clock minus monotonic jumps (catches the 2026-08-06 18 h case too); bake_timing_report.py parses per-dive ms logs, adds 'Replay state|Split mode|Writing HTML|Running ...' as serial openers and a sleep bucket (tests/test_eta_and_timing_report.py:103,120 pin classify); sweep.py:780-782 logs 'sweep cache: 0/n' too (overnight_eta.py:167 _CACHE_RE never sees all-miss sweeps; re-check the 0.5 warm cutoff). Effort: hours. Cache: none (sweep.py logging is not hashed; confirm it does not trip the CACHE_VERSION convention -- it is a log line, not worker plumbing). Fan-out: one agent.

R7. Storage reclaim, ~104 GB verified: rm the sweep_pre_aegislash_20260915 dir (46.1 GB unique, engine e4d380ec3e5e = pre-Aegislash-fix, 4 bumps behind) + slayer_pre_aegislash_20260915 (1.36 GB); then gc_cache --keep-vintages 1 drops the 153,376 legacy 515a0a95171b columns (47.4 GB, freed only once the snapshot copies are gone) and delete the 99 legacy slayer entries (1.12 GB); prune 258 superseded replay blobs (9.5 GB) with keep set = website-referenced (136) + test-pinned (19, incl. tests/test_deep_dive_builds.py:44-52 stem pins) + newest-per-key -- NOT plain newest-per-key (it would delete the two live Forretress Volt Switch page sources). Effort: hours. Risk: irreversible; disk is 42% used with 1.0 TiB free (df), so this is hygiene, not pressure. Gated on Q1. Fan-out: one agent after the go.

R8. Cruft fan-out (section 4): ~1,124 script lines + ~700-735 TODO lines + ~155-165 dead-code lines + 4 test fixes, all verified. Effort: hours each, highly parallel (5 agents on disjoint files). Cache: none as long as deep_dive_slayer.py and _ENGINE_FILES are untouched.

Not ranked for today: pack_u16 numpy (verified byte-identical but only ~0.2 h; do it opportunistically inside R2's agent), --jobs N dive overlap (unverified; render state is 2.5-8.5 GB RSS per dive, not 0.8 GB; needs lens-grid review), fork-per-split-file render (unverified, up to ~20 GB), persistent Pool (0.37 h, forces CACHE_VERSION bump), savez_compressed columns (disk only, unverified).

3. RECOMMENDED SEQUENCE

Hour 0 (human): answer section 5; branch off main; agree that every render change ships behind a replay byte-diff.

Hour 0-1 (Agent H, blocking for R1-R4): build a render-diff harness in scripts/ or the scratchpad: render 5 blobs (Tinkaton GL, Jellicent UL, Guzzlord GL, Melmetal GL no-op, Cramorant UL) with render_dive_html, html_path/card_path redirected outside userdata/, GOPVPSIM_PIN_DATA_CACHE=1, network blocked (the scouts' time_replay.py / timed_render.py already do this); store HEAD baselines. Diff mode A = raw bytes; mode B = bytes after normalizing counter-based element ids (needed only for R3).

Hour 0-4, concurrent agents (disjoint files):
  - Agent 1: R1 iv_rank memo (opponents.py or deep_dive.py per Q2) -> harness mode A + fast tier.
  - Agent 2: R2 dedup, then R4, then R2 vectorize, then pack_u16 (render.py, deep_dive_analysis.py, score_pack.py) -> harness mode A after each step, one commit each.
  - Agent 3: R5 gates concurrency + scanner pool (run_ship_gates.py, verify_overnight.py, verify_article_links.py, verify_no_unicode_dashes.py); prove identical output on today's tree.
  - Agent 4: R6 guards + bake_timing_report + sweep.py 0/n log line + TODO.md:107 number fix.
  - Agents 5-9: cruft fan-out, one file domain each: (5) script deletes + stale orchestration comments; (6) TODO.md -> CHANGELOG moves (single owner of TODO.md/CHANGELOG.md); (7) tests (xfail conversion, body-less skip, stale comments, fire_now mutant check); (8) out-of-hash dead code in deep_dive.py/brief/builds/rendering/which_build + F401 prune excluding deep_dive_slayer.py; (9) cache/docstring fixes in sweep_cache.py, sweep.py, deep_dive.py:5516 and, if Q7 says yes, CLAUDE.md/DEVELOPER_NOTES corrections with each claim re-checked against code before editing (those findings were not refuter-verified).
  - Agent 10 (after Q1 go): R7 storage; write the replay keep-list script first, print it, then delete.

Hour 4-8: R3 no-op pass2 skip, one careful hand, on top of Agent 1's merge (both touch deep_dive.py); harness mode B on the no-op blobs, mode A on the active-best-buddy blobs (must be untouched); update test_dive_dom_ids pins; run fast tier.

Hour 8-9: merge, run the full fast tier once, re-time one replay render before/after (Jellicent UL 2-file replay was 158 s wall, Tinkaton GL 52 s) and record the numbers in CLAUDE.md Testing / TODO (the fast-tier numbers there are already stale: 63bbc14 measured 228 s, not 310 s). Commit small, push.

Must wait for a human decision: R7 deletes (Q1), R1 placement (Q2), R3 template drop (Q3), Worlds retire (Q4), replay keep policy (Q5), CLAUDE.md/DEVELOPER_NOTES edits (Q7), applying the signature migrations (Q6; a prerequisite for the next bake, not for today's code).

Do NOT do today: any byte change to battle.py / pokemon.py / moves.py / formchange.py / _dp_jit.py / deep_dive_signature.py (that includes the in-hash dead code: compute_default_ivs, the legacy-mechanics path, pvpoke_shield/use_first_available/_form_is_alt, allow_dead_attacker) -- TODO.md:94-96 forbids another engine-hashed change before the built migrations are applied, and it would cold the cache; any edit to scripts/deep_dive_slayer.py, including pruning its 11 unused imports (slayer_cache.py:135-163 hashes that file into the slayer stamp); sweep.py worker plumbing / persistent Pool (CACHE_VERSION bump); --jobs N or fork-per-file render (unverified, memory unmeasured live); removing legacy mechanics (engine hash + the mechanics='new' cache-key stamp at sweep_cache.py:283 / slayer_cache.py:127); launching a bake; taking a new cp -al snapshot before the old one is dropped; gc_cache with default vintages (it keeps the legacy columns anyway).

4. CRUFT CLEANUP (V = both refuters failed to refute; U = scout-only, unverified)

Scripts (V, delete, 5 files / 1,124 lines):
  - scripts/status_tick.sh (101): hard-codes userdata/logs/2026-04 and a 20260419_ glob; chain_status.py --chain overnight replaces it.
  - scripts/verify_pvpoke_harness.py (188): April-era hand-typed PvPoke scores, 19/27 no longer match the 09-09 re-pinned fixtures; audit_oracle_harness.py covers the same matchups live.
  - scripts/patch_iv_guide_nav_width.py (59): 0 of 60 guides still carry 'flex:0 0 190px'; renderer emits 260px at render_iv_envelope_article.py:764.
  - scripts/dialga_origin_etm_analysis.py + palkia_origin_etm_analysis.py (386+390): 'Do not import' one-offs, 82% shared; result lives in ~/coding/reports/dialga-palkia-origin-etm-ml-2026-06-19.html (note SHAs 48a8de9/4171011 in its provenance line and in etm_iv_floor_sweep.py:4).
  U: worlds_probe_expand.py (236), joint_iv_index.py (99), etm_iv_floor_sweep.py (224, named in a test docstring), corpus_new_decisions.py, summarize_perf.py, rerender_status.py -- each needs a one-line answer from Michael; Worlds cluster (~5,970 script + ~3,400 test lines) is Q4.

TODO.md (V, MOVE to CHANGELOG -- it has no entry after 2026-08-27 -- ~705-735 lines out of 2,285):
  - 'Turn system' 1899-2285 (sits after the file's own footer): ~300-310 out; keep ~77-85 residue (DUP DOM af- ids, IV-ratio IDEA, Worlds un-skip note, 3b(c) prose, Aegislash x Azumarill 6-cell trace with mechanics_notice.py deletion folded under it, un-xfail candidates).
  - Cramorant hand-off 135-340: ~140-150 out; KEEP the three decisions 271-300, the TTL-keeper lens item 163-165 (88bec7b pins the cache only in overnight_redive.sh, not run_website_dives.py -- NOT closed), and the post-bake verification runbook 245-269 (no evidence it ran after 09-20; the strategy article is still the 09-12 render).
  - Six DONE sections (1113-1194, 1269-1304, 1334-1376, 1067-1111, 744-784, 812-828): ~255-265 out; keep the season policy 788-810, the band-crosser glossary gap, and the battle.py:3424-3426 'UNVALIDATED' comment as a next-engine-bump line.
  - Duplicates: ~10 lines (Report 9 at 341-344 folds into 291-302; Guzzlord/gate clauses trimmed from 397-400, keep P-C/P-D; 130-131 is a deliberate pointer).
  - Line-level: :107 '~1.4 h' -> 15.4 h pool sweeps (+1.4 h slayer); :98-104 resolved ship-gate note can go (docs/chain_resolutions.toml keeps it).
  U: campaign/stale-article/rebalance 345-530 (~150), Worlds 567-667 (~70), BUILD BRIEF 896-1065 (~130), signature-dedup diagnosis 32-107 (~55, keep 83-96 verbatim), stale-premise rewrites (~40), contradictory pogodives-constants advice, plus a guard test that fails on '^##+ DONE' headers (needs a positive control per the testing policy).

Docs / comments:
  V: stale numbers in run_ship_gates.py:27-28 (44 s -> ~310-414 s), overnight_redive.sh:4-6 (44 dives -> 136), :15-16 ('~7h cold' ML tail: unmeasured, flag it), :289-290 and phase2_preship.sh:116 (2 of 4 gates named), verify_overnight.py:33-34, run_iv_guides.py:7/14-16/21/128-130/191 (16-worker cap is gone; '--jobs 2' now ABORTs at the preflight), verify_tests.py:22-24 ('runs twice' -> 3x); sweep_cache.py:26-34 ('.npy one score column' -> multi-plane .npz), sweep.py:652-653 ('Capturing forces the disk cache off' is false), deep_dive.py:5516 cache=None rationale predates slayer v4.
  U (re-verify each against code before editing, then fine): DEVELOPER_NOTES.md:112-170 turn-model section (says default legacy / UNVALIDATED / cache force-disabled; all false), ~330 lines of dated history to CHANGELOG, CACHE_VERSION 7 -> 8; CLAUDE.md:145-149 two of three 'intentional deviation' examples (bestChargedMove per-turn; Mimikyu SS) and :174/:190 'v7' / 'GC keeps v7 dirs'; CLAUDE.md fast-tier 310 s / '~245 of 310' (63bbc14: 228 s / 125 s); 7 docs/ status headers; ~335 lines of closed-event docs to archive; ~10 '(deleted 7126f1b)' annotations; README setup missing `git config core.hooksPath .githooks`; docs/rebalance_checklist.md 'near-zero disk' snapshot claim.

Tests (V):
  - tests/test_battle.py 13 strict xfails pinned to April legacy values (12/13 scores differ from the current engine): 5 become plain PvPoke-certified pins (Aegi (0,1)=348, (0,2)=112, (1,2)=382, (2,2)=382 with Shadow Ball logs; Corvi (0,0) MG=456), 2 Aegi divergence pins recording ours 564/550 vs PvPoke 618, 6 MG divergence pins recording both (Jellicent 531/670/670 vs 639/779/779, Corvi 580/689 vs 652/760, Lapras 482 vs 611); PvPoke values are on disk in docs/validations/2026-09-09_oracle_new_vs_master_raw.txt; fix the :1753-1760 docstring and the MG block comment.
  - tests/test_pogodives.py:408-420 body-less skip: delete (~15 lines, cite f116674~1).
  - tests/test_nb1_selection_freeze.py: 5 stale oracle comments (:70 :78 :95 :98 :160) + 'Group D xfails' docstring; also test_bug3_farm_stack.py:15-16 and test_pokemon.py:530.
  - tests/test_fire_now_cmp_shadow.py: reverting battle.py:1804-1805 changes 0/9 cells (fire_now branch reached 7x but never with 2x charged energy). Step 1: run the 2-line mutant against the fast tier to see if anything else catches it; step 2: fixture search or a direct unit assertion on the gate inputs; fix the docstring either way.
  U: Icy Wind always-skip guards and Worlds DORMANT skips (Q4), 47 clean-first gate_recompute runs (~29 s fast tier), session-scoped W.prepare memo (~137 s full suite, memory caveat), node-skip marker + 4 _node helpers, 6 replay-blob lookup copies, 4 identical script loaders, cross-imported test helpers, 21 legacy-coupled tests (only if legacy is ever removed).

Dead code, in_hash=false (V, ~155-165 lines):
  - deep_dive.py:715-786 _form_damage_census (72, self-declared UNUSED).
  - deep_dive.py 25 of its 76 re-export aliases have no reader (~30-35 lines with the orphaned 'Moved to ...' headers at 789-797; update the 802-804 comment).
  - deep_dive_brief SHIELD_LABELS/axis_plane/COVERAGE_ROWS/DEGRADATION_RUNGS/_rung_line/render_arm; deep_dive_builds TYPICAL/NOTABLE_ROLE_ORDER; deep_dive_rendering tooltip_count + orphaned _TooltipRegistry.count(); deep_dive_which_build family_legend/family_counts (~38-45).
  - ruff F401: 48 names, net -15 physical lines, in deep_dive.py (keep get_rankings_for: tests/test_opp_meta_ranks.py:141 reads it; revise the :104-112 comment), anchors.py, breakpoints.py, user_collection.py, deep_dive_rendering.py, categories.py, render.py. EXCLUDE deep_dive_slayer.py (11 names) -- it is hashed into the slayer stamp.
  U (out of hash): categories._base_opponent dup of matchup_clusters.base_opponent (~30, watch the import cycle), _authored_by_class/_default_log_root/_esc dups (~30), attribution.PVPOKE_ATTRIBUTION_TEXT, test-only public-API symbols (product decision).
  In_hash=true (U, NOT today, batch with the next forced-cold bump): pokemon.py compute_default_ivs chain ~173 + _LEVEL_CAP_EXCLUSIONS; battle.py legacy else-branch ~45 + mechanics param threaded through 13 no-op policies + 2 unused imports/2 locals + allow_dead_attacker + orphan 'deferred' comments; pvpoke_shield/use_first_available/_form_is_alt ~26; _dp_jit fast_damage. ~250-300 lines; cache-key stamp for mechanics='new' must stay byte-identical.

Storage (V, ~104 GB): sweep_pre_aegislash_20260915 46.1 GB; legacy 515a0a95171b sweep columns 47.4 GB (needs both copies gone); replay blobs 9.5 GB / 258 files (keep-set rule above); slayer_pre_aegislash 1.36 GB + 99 legacy slayer entries 1.12 GB (do not use 'stamp != current' as the rule: the 150 live 9ac12a2754a1 entries are also stale under HEAD until the slayer migration is applied). U: worlds/planes 7.0 GiB (archive off-disk, Q4), .git cruft pack 0.8 GB (git gc --prune=now drops old stashes), cramorant_lab v6 3.4 GB (compress), analysis previews 1.2 GiB (keep .md/.py, drop .html), userdata/dives 0.25 GB.

Total verified payoff: ~1,124 script lines + ~705-735 TODO lines + ~155-165 dead-code lines + 3 stale-comment sites + 1 dead test + 13 non-signal xfails made real + ~104 GB; ~445 more TODO lines, ~110+330 DEVELOPER_NOTES lines and ~13 GB are scout-only.

5. OPEN QUESTIONS (answers change the work)

Q1. Delete both pre-Aegislash snapshots (sweep 46.1 GB, slayer 1.36 GB; they hold the only copy of e4d380ec3e5e Blade-leaking scores, nothing schedules a before/after diff), and then gc_cache --keep-vintages 1 to drop the 153,376 legacy columns (+47.4 GB)? Irreversible.
Q2. Is a parent-side memo in scripts/deep_dive_lib/opponents.py 'worker code' under the CACHE_VERSION bump convention (sweep_cache.py:78-83)? Yes -> render-only memo in deep_dive.py (~1.7 h); no -> opponents.py memo (~3.2-4.0 h).
Q3. For no-op best-buddy dives, accept dropping the L51 <template> (rendered artifact changes on 100 dives; the misleading 'builds pinned to league cap' note disappears; DOM-id pins updated), or require an id-namespaced copy that keeps the artifact byte-equivalent?
Q4. Execute the 2026-08-31 Worlds retire now (scripts minus worlds_planes.py, 13 test modules, publish_website.sh block, index card, Icy Wind guards, 3 DORMANT skips, worlds/planes 7 GiB archived), or leave dormant until 2027? Decides ~9k lines of the cruft pass.
Q5. Replay prune keep-set: website-referenced + test-pinned + newest-per-key, including the 3 departed species (Shadow Dragonair, Shadow Kingdra, Galarian Moltres)? And should the 12 test-pinned blobs already missing from disk be re-pinned or dropped from the tests?
Q6. Apply the two built signature migrations now (TODO.md:83-90; 43,077 columns to re-sim, ~26 min single-threaded)? Not needed for today's code, but it is the gate on every later engine-side item and on the next bake.
Q7. May agents edit CLAUDE.md and DEVELOPER_NOTES.md today (the session-startup reads) on the docs scout's unverified findings, provided each claim is re-checked against code first -- or defer those two files to a separate verified pass?
Q8. TODO -> CHANGELOG style: condensed dated entries (~20-30 lines each, SHAs cited) or verbatim moves into docs/TODO_archive.md? And add the '^##+ DONE' guard test?
## Appendix: storage + migration steps (Michael runs by hand, 2026-09-25)

Michael's decisions (2026-09-25): Q1 yes, Q2 yes (render-only memo), Q3 yes
(drop the L51 template on no-op pages), Q4 no (Worlds stays dormant), Q5
default keep-set, Q6 yes, Q7 defer, Q8 condensed CHANGELOG entries. The
auto-mode classifier refused to let agents delete outside the repo, so the
irreversible steps below are for a human shell, in this order. Every step is
preceded by its own look-before-you-leap check; stop at the first surprise.

    # 0. preflight: main, engine hash d78c67fd06a7, stamps, free space
    git rev-parse --short HEAD
    (cd scripts && ../.venv/bin/python -c "import sweep_cache as s; print(s.engine_hash())")
    direnv exec . python scripts/migrate_cache.py --list-stamps
    direnv exec . python scripts/migrate_cache.py --list-stamps --slayer
    df -h ~

    # 1. drop the pre-Aegislash hardlink snapshots (46.1 GB + 1.36 GB unique)
    ls ~/.cache/gopvpsim/
    rm -rf ~/.cache/gopvpsim/sweep_pre_aegislash_20260915 ~/.cache/gopvpsim/slayer_pre_aegislash_20260915

    # 2. apply the built signature migrations (dry-run first; expect
    #    sweep 239,091 blessed / 43,077 deleted; slayer 150 / 0)
    direnv exec . python scripts/migrate_cache.py --from-engine 9ac12a2754a1 --predicate signature_regroup_20260923
    direnv exec . python scripts/migrate_cache.py --from-engine 9ac12a2754a1 --predicate signature_regroup_20260923 --apply
    direnv exec . python scripts/migrate_cache.py --slayer --from-engine 9ac12a2754a1 --predicate signature_fix_slayer_20260923
    direnv exec . python scripts/migrate_cache.py --slayer --from-engine 9ac12a2754a1 --predicate signature_fix_slayer_20260923 --apply
    # If the dry-run blesses ~0 columns, the live gamemaster stamp has moved
    # since the bake and the engine migration is skipping everything: see
    # TODO/CHANGELOG 2026-09-15 for the gamemaster-vintage swap recipe.

    # 3. GC the 153,376 legacy-mechanics columns (47.4 GB) -- read
    #    scripts/gc_cache.py first; dry-run must list ONLY 515a0a95171b
    direnv exec . python scripts/gc_cache.py --help

    # 4. replay-blob prune (9.5 GB): keep-set = site-referenced + test-pinned
    #    + newest per key. NOT plain newest-per-key (it would delete the two
    #    live Forretress Volt Switch page sources). No script exists yet;
    #    write the keep/delete lists first and read them before deleting.

Also pending a human: the 12 test-pinned replay blobs already missing from
disk (tests skip on them today) -- re-pin or drop, undecided.
