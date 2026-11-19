# Project-hygiene skill: report for Michael

> **Archived 2026-11-18.** Point-in-time record; paths below under the
> session scratchpad, `project-hygiene/`, `_runs/` and the other build
> dirs no longer exist. The skill is installed at
> `~/coding/dotfiles/claude/skills/project-hygiene/` (dotfiles `affa74d`).

Date: 2026-11-17. Repo state: main @ 1b6904d, clean. Nothing was written in the repo or in `~/.claude`.

**REPORT.md was not written to disk.** The Write tool refused it ("Subagents should return findings as text, not write report files") and I did not work around that. The full report text is below; save it as `REPORT.md` if you want the file. The other files were written (list at the end).

**Bottom line.** A skill alone would be the ninth manual groom, and the history says it would regrow. What the evidence supports is three pieces:

1. a cheap read-only scan that makes the state visible (built and run);
2. a bounded cleanup procedure with a real evidence and loss-safety standard (the SKILL.md);
3. two small commit-time checks in the repo that act on what gets *added*, not only on file size (specified here, not built, because they are code changes in the repo and need Michael's go).

Labels used below: **measured** = I ran the check in this step; **audit** = taken from the earlier audit stage and not re-run by me; **inferred** = a conclusion, not an observation.

## 1. Diagnosis

Sizes today (measured): TODO.md 89,625 B, DEVELOPER_NOTES.md (DN) 51,752 against a 52,000 cap (248 chars of headroom), CHANGELOG.md 261,747, CLAUDE.md 26,535 (509 lines), docs/TODO_backlog.md 51,732, docs/TODO_archive.md 65,842, memory dir 28 files / 87,815 B.

Root causes, in order of impact:

1. **Status text is added when work ships and never removed when it closes.**
   - Measured: 29 done-marker lines in 18 sections of the two open files.
   - Measured: TODO was groomed 2026-09-27 (93.7k -> 69.3k) and has regrown +20.3k over 31 commits (+656 B per commit).
   - Audit: about 25% of TODO bytes are actionable open work.
2. **No single home per fact, so closing an item is a write to 4-7 files and some copy is always missed.**
   - Audit: one finding landed in TODO, CHANGELOG, DN, a validation doc, the divergences doc, a memory file and the memory index.
   - Audit: duplication is paraphrase, not copy (4.2% verbatim 6-gram overlap), so grep-style dedup does not find it.
3. **Only a hard gate held, it covers one file, and it displaces text.**
   - Measured: DN went 117,649 -> 52,073 at the 10-24 gate and has stayed about flat since (-321 B over 15 commits).
   - Audit: with DN full, sessions wrote to TODO instead.
   - Caveat: this is one file over about 3.5 weeks of low activity. Treat "only hard gates hold" as suggestive, not proven.
4. **Grooming moves text; it does not remove it.**
   - Measured with the new `removed` check on the 08-27 groom (454f95f): TODO -22.7k, CHANGELOG +6.4k, TODO_archive +31.6k. The set grew 15.3k.
   - Measured: live (non-frozen) process files grew +73.6k in the last 30 days and +390k in the last 90.
5. **Dated narrative sits in files that must be true now.** Measured: DN has 57 ISO dates, project CLAUDE.md 19, global CLAUDE.md 1.
6. **Nothing checks truth, and pointers into TODO have no gate.**
   - Measured: 24 quoted section citations from live files name a heading that no longer exists (22 into TODO). One is in an engine-hash file: `src/gopvpsim/battle.py:3917` cites TODO "KO-EDGE".
   - Measured: 12 memory filenames are cited that are not in the memory dir.
   - Measured: `TODO.md:1397` says `CAVEAT_SPECIES = ('Aegislash',)`; the code has `()`. `TODO.md:657` says `RENDER_MIRROR_POPULATION = False`; the code has `True` (`scripts/deep_dive_which_build.py:4227`; a new find by the scan).
   - Measured: `.githooks/pre-commit:72` runs the checker with `--quiet`, so its warnings are never seen.
7. **The always-loaded layer has the same problem.**
   - Measured: 20 of 27 MEMORY.md index lines are over 150 chars (longest 469); 11 memory lines hold volatile repo status.
   - Measured examples: the Aegislash memory description says "not merged" (audit: the fix commit is on main); the WOTB memory names main as 679541e, which is 190 commits behind.
   - Measured: the project CLAUDE.md repeats the global Karpathy block (2 near-copy paragraphs).
8. **TODO is the only place guaranteed to be read next session**, so it is the rational place to dump "don't forget" text (inferred; raised by the root-cause critique). A cap on TODO works against that incentive unless the startup read changes. See open question 3.

What was tried and why it did not hold (audit, except where noted):

| Tried                              | Result                                  | Why                                   |
| ---------------------------------- | --------------------------------------- | ------------------------------------- |
| TODO "live backlog" header (06-27) | Failed; 29 done-marker lines (measured) | Convention; nothing fails when broken |
| DN soft-cap comment (06-28)        | Failed; DN reached 117.6k               | Same                                  |
| DN hard cap + pointer gate (10-24) | Held on size                            | No truth check; displaces text        |
| About 8 TODO grooming sessions     | Regrew each time                        | Fixes the stock, not the flow         |
| TODO_archive / TODO_backlog        | Idle (backlog 132 days, measured)       | Write-once stores nobody reads        |
| B.5 semantic pass                  | Works (9 wrong claims on 11-17)         | DN only; runs only on a PvPoke re-vet |

Corrections to the draft diagnosis, from the evidence critique:

- CLAUDE.md was not "never groomed"; it had one partial refresh (a9e0fac, per the critique; I did not re-check that commit).
- The data-cache recipe currently has one home. Measured: the full recipe is in TODO under "PvPoke sync 2026-11-17", and `feedback_sandbox_data_cache_refresh.md` points to it. The scan finds no duplicate. The divergent copy that caused the Mega Sableye miss is no longer there.
- "TODO exceeds the Read cap" is an inference; at 1,521 lines it is under the line limit.

## 2. What was built

### The skill: `project-hygiene`

I kept Michael's name for it rather than `process-hygiene`. `/project-hygiene` matches how he asks, and the description states the scope (process files, not code).

- **Model:** five file kinds (open, living, history, frozen, instructions) and one home per fact.
- **Step 1, scan:** read-only. If the model starts the skill on its own, it runs `--brief` and stops.
- **Step 2, judge:** each item is split into claims; evidence must be a check run that session. Another process file agreeing is not evidence. Claims about publishes, in-game readings, upstream filings or Michael's decisions go to him. A contradiction is "reconcile and ask".
- **Step 3, propose:** a triage table first; CLAUDE.md and memory changes need a yes per item.
- **Step 4, apply:** anchored by heading, not line number; citations repointed in the same commit; a ledger for every removed block; a memory snapshot before any memory edit; the set must shrink.
- **Step 5, verify:** at most two review rounds, with a stop rule.
- **Light path** for closing one item.

### The helper: `hygiene_scan.py`

Stdlib only. Without a config it runs on Python 3.9 (tested with `/usr/bin/python3`); the TOML config needs 3.11+. It takes about 3 seconds on gopvpsim and writes nothing (`git status` stayed clean).

| Check      | What it reports                                           | gopvpsim today   |
| ---------- | --------------------------------------------------------- | ---------------- |
| Budgets    | Chars vs cap, which cap binds, idle days, date counts     | 3 near/over      |
| Whole set  | Total by kind; 30- and 90-day change                      | +73.6k / 30d     |
| Growth     | Size change since the last groom, per commit              | TODO +656/commit |
| PRE        | Other worktrees, unmerged branches, dirty process files   | 3                |
| SECT       | Sections over 60 lines in open and instructions files     | 16               |
| DONE       | Done-markers in open files, grouped by section            | 29 lines         |
| AGED       | Stale triggers and headings older than 60 days            | 12               |
| REFS-path  | Cited paths that do not exist                             | 7                |
| REFS-mem   | Cited memory files that do not exist                      | 12               |
| REFS-cite  | Quoted section citations with no such heading             | 24               |
| REFS-line  | `file.md:LINE` citations (fragile under any move)         | 15               |
| DUP-recipe | Section pairs sharing the same command spans              | 8                |
| DUP-para   | Near-copy paragraphs                                      | 2                |
| DUP-sha    | Commits cited in 4+ files                                 | 2                |
| PLAN       | Idle docs whose header still says "not built"             | 6                |
| CODE       | `NAME = value` in docs that differs from the code         | 3                |
| RETIRED    | Configured retired terms still present                    | 1                |
| MEM-*      | Index line length and status words; volatile status; size | 26 / 11 / 5      |
| EXT        | The repo's own checker, run without `--quiet`             | 1 warning        |

`removed` is the loss-safety check. For a git range, the working tree, or two directories (a memory snapshot against the live dir), it lists the distinctive tokens from removed blocks that no longer appear in any live process file, headings removed while still cited, and protected lines that disappeared. It also prints "THE SET GREW" when a cleanup added bytes.

**How much the scan catches** (measured against the audits' findings):

- All 12 dead memory pointers.
- The `docs/todo.md` pointer in `scripts/deep_dive_engine.js:3056`.
- The Karpathy duplicate.
- 6 of the 7 stale plan headers (the seventh was touched 24 days ago, inside the 60-day idle window).
- 4 of the 5 stale memories the audits named.
- About 2 of the 9 TODO contradictions (the `CAVEAT_SPECIES` claim and the "16 confirmed findings need triage" heading). The rest are prose against prose, which is why step 2 exists.
- Known false positives: CODE 1 of 3 (`DATA = { ... }` in `docs/article_generator_design.md:81`); DONE includes at least one (`TODO.md:841`, "the tmp filename is FIXED").

### Config

Optional. The gopvpsim example names the frozen dirs, the six engine-hash files (`no_edit`), the ship-mode TOMLs (`out_of_scope`), the sync sentinels (`protected_patterns`), one retired term, and paths to ignore. With it, REFS-path drops from 26 hits to 7 (measured). The hard DN cap is read from `scripts/verify_dev_notes.py:CHAR_CAP`, so the number keeps one home and the pre-commit hook does not depend on the config. The TODO and CLAUDE.md budgets in the example (60k, 18k) are placeholders for the scan only.

## 3. Prevention (proposed; needs Michael's go; not built)

These are changes to `scripts/verify_dev_notes.py` and the hook, each with a test that fails without it, per the repo's testing policy.

| #   | Check                                                                                                             | Enforced?  |
| --- | ----------------------------------------------------------------------------------------------------------------- | ---------- |
| 1   | A staged TODO.md may not ADD a line with an uppercase done-marker (DONE, SHIPPED, RESOLVED, SUPERSEDED, MERGED)   | Hard fail  |
| 2   | TODO.md size cap, as a second constant next to `CHAR_CAP`; checked only when TODO.md is staged                    | Hard fail  |
| 3   | The ISO-date count in DN and CLAUDE.md may not rise in a commit                                                   | Warn first |
| 4   | The hook prints the checker's warning count and stops hiding it                                                   | n/a        |
| 5   | Optional SessionStart hook running `scan --brief` (two lines), so budget and memory drift are seen without asking | n/a        |

- Check 1 is the one that acts on the flow. It enforces "delete the bullet, write the CHANGELOG entry" at the moment the done text is written.
- Check 2 is a backstop. Set it after the first groom at about 1.5x the post-groom size, so it does not bind within a session or two. Checking only when TODO.md is staged means an engine commit is never blocked.
- When a gate fails, the message should offer the light path first (close the flagged items), and the full skill only if that is not enough.
- Still conventions, with no mechanical check: one home per fact, condensing history entries, what goes in memory. The scan is what shows drift there.

**Success criterion (falsifiable).** Over 30 days of active development: TODO stays under its cap with no groom commit, DONE stays at 0 in TODO, and the live set grows by less than half of today's +73.6k per 30 days. The scan prints all three. If the criterion is missed, revisit the design; do not just groom again.

## 4. Prior art

I did not fetch any URL in this step. The sources are what the audit stage reported; the links are ones I know from memory, and "no URL recorded" means the audits left none in the scratchpad.

| Source                                                                                                   | Taken                                                                                                                 |
| -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Anthropic `claude-md-improver` skill (github.com/anthropics/claude-plugins-official)                     | Report first, diffs after approval                                                                                    |
| Claude Code memory docs (https://code.claude.com/docs/en/memory)                                         | Keep CLAUDE.md short; one-line index entries                                                                          |
| agent-almanac `manage-memory`, `prune-agent-memory` (no URL recorded)                                    | Name the cap that binds; warn before the cap; memory is for what is not recorded elsewhere; snapshot before a rewrite |
| orchestkit `dream` (no URL recorded)                                                                     | Deterministic staleness checks; dry run by default                                                                    |
| ctxlint, AgentLint (no URL recorded)                                                                     | Stale file references                                                                                                 |
| Cline Memory Bank (https://docs.cline.bot/prompting/cline-memory-bank)                                   | Current state only in startup files; overwrite, not append                                                            |
| Caulfield, garden and stream (https://hapgood.us/2015/10/17/the-garden-and-the-stream-a-technopastoral/) | Stream content does not belong in garden files                                                                        |
| Diataxis (https://diataxis.fr/)                                                                          | One kind per document                                                                                                 |
| matklad, ARCHITECTURE.md (https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html)                     | Only stable facts; name symbols, not line numbers                                                                     |
| Nygard, ADRs (https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)                  | Mark a belief refuted; do not silently rewrite it                                                                     |

Rejected: towncrier and scriv changelog fragments, ADR numbering, per-doc freshness headers, Vale / lychee / jscpd as dependencies, and a git-blame age per section. Each adds machinery the evidence does not call for, and the repo avoids new dependencies. The draft also deferred the CLAUDE.md audit to `/doctor prompt-audit`; I dropped that because nobody ran it or checked that it exists in the installed version.

## 5. Critiques

### Accepted

- **Act on the flow, not only the stock** (root-cause). Added the added-line done-marker check, the "cap at 1.5x post-groom" rule, the growth-per-commit report and the success criterion.
- **Whole-set budget** (root-cause, safety, completeness). The scan reports the set total and its trend; `removed` flags a groom that grows the set.
- **Say which rules are enforced** (root-cause). See the table in section 3 and in `write-time-rules.md`.
- **Memory has no prevention and no undo** (root-cause, safety). Measured: the memory dir is not a git repo. The skill requires a snapshot first, `removed --dirs` afterwards, and a filename search before deleting. The `--brief` mode exists for a SessionStart hook.
- **The startup-read incentive** (root-cause). Recorded as cause 8 and open question 3.
- **Pointers into TODO have no gate** (safety). Measured 24 dangling ones. REFS-cite covers TODO, CLAUDE, CHANGELOG and DN; the skill requires repointing in the same commit, or a tombstone heading for no-edit files.
- **Evidence standard** (safety). Rewritten: atomic claims; history entries count only with a verified commit; outside-the-repo claims go to Michael; contradictions are reconciled, not deleted. The Minior case is the example in the skill, stated generically.
- **Token survival in place of `lost-lines`** (safety, simplicity, completeness). Built as `removed`. Frozen files do not count as a home.
- **Distill DN in place** (safety). The plan no longer moves DN ranges. I confirmed one of the cited ranges holds a standing rule ("pin `level=` in audit and sweep specs...").
- **Caps live in the repo checker** (safety, simplicity). The config points at the constant.
- **TODO cap fires only when TODO is staged** (safety).
- **Relocated rules leave a trigger pointer in a startup-read file** (safety).
- **No line-number anchors** (safety, evidence). The first-run plan below is anchored by heading.
- **DN distill before the TODO moves** (safety).
- **Reviewer briefs are read-only** (safety).
- **Sentinels are protected** (safety). `protected_patterns` in the config; `removed` flags them.
- **Memory format follows the harness** (safety). The skill sets no format; the 150-char index threshold is configurable.
- **Memory path is derived, not committed** (safety, completeness).
- **Split the skill from the one-time groom** (simplicity). The groom plan is in this report only.
- **Fewer kinds; rules in one place** (simplicity). Five kinds. The write-time rules are a template whose home is the project's CLAUDE.md.
- **No self-offer in the description; subagents only for large files; prior art out of the skill** (simplicity).
- **Cut ORPH, `--json`, `--only`, the `gate` subcommand** (simplicity).
- **Worktree and branch preflight; retired terms; line-citation list** (completeness).
- **All the evidence corrections** (backlog entries with open residue, the Refactoring wording, the mechanics-toggle item, the index-line counts). I verified these four in the repo.

### Rejected or only partly accepted

- **A cap or per-commit limit on CHANGELOG** (root-cause). Rejected. History is cold and is not read at startup; a cap there forces deleting history. The whole-set trend covers the concern.
- **Drop the config entirely** (simplicity). Partly. It is optional and the scan runs without it, but gopvpsim has project facts the scan cannot guess, and they cut REFS-path noise from 26 to 7.
- **Cut the CODE and PLAN checks** (simplicity). Rejected after measuring: CODE gave 2 true hits in 3, one of them new; PLAN gave 6 hits, all in the audits' list.
- **A transcript grep for re-taught lessons** (completeness). Rejected for v1. It is a salience problem, the transcripts are outside the repo, and I have no mechanical test for it. Open question 8.
- **A DUP threshold change to catch the data-cache recipe** (completeness). Not needed now: the recipe has one home today (measured). DUP-recipe already works at a threshold of two sections.
- **Global or one repo first** (completeness, simplicity). Kept as a global skill because the SKILL.md is project-neutral, but it is proven on one repo. Open question 7.

## 6. First-run plan for gopvpsim

This is an ordinary task run under the skill, not part of the skill. Items are anchored by heading. Re-run the scan and re-verify each item when applying; the line numbers in the audits are already stale by a line or two.

0. **Decide** open questions 1-4.
1. **Preflight.** One extra worktree and two unmerged experiment branches exist (measured; neither branch touches process files). Snapshot the memory dir.
2. **One sink.** Fix the TODO header comment to name CHANGELOG only. Freeze `docs/TODO_archive.md`; its header says "Nothing here is open work" above "Still open" blocks (audit).
3. **DN first, in place.** Strip dated narrative sentences only. Keep every heading, numbered item and sentinel. Fix "Current status (updated 2026-10-24)" (audit: the body holds 11-17 state). Headroom is whatever that yields.
4. **TODO claims with code evidence.**
   - `CAVEAT_SPECIES` under "Turn system": the code half is done; the published-page residue stays open.
   - `RENDER_MIRROR_POPULATION = False` under "NEXT BAKE: mirror population": the code has `True`.
5. **TODO contradictions: reconcile and ask.** Jumpluff "published" against "still open"; Report 9 "NOT FILED" against "superseded"; Minior UL "unverified in-game" against "confirmed 55" (this one is new engine work, not a stale line); "Last bake 2026-08-06/08"; "16 confirmed findings need triage"; the mechanics-toggle item (only its cache premise is false; whether the toggle is still wanted is Michael's call); farmdown "not yet applied".
6. **Done narrative to CHANGELOG, condensed, residue kept.** "OPEN: Bake speed", "NEXT BAKE: mirror population" (148 lines; the safety critique counts 4 code sites citing this heading, so repoint them or leave a tombstone), the resolved bullets under "Turn system", the deep_dive split steps under "Refactoring", the SUPERSEDED bullet under "Minior".
7. **Relocate non-tasks, with trigger pointers left in TODO or CLAUDE.md.** "Site lifecycle policy", the Cramorant runbook (keep the publish guard visible: the UL page needs a re-dive first), "Re-dive runbook", the Worlds standing rules, and "PLAN ONLY: parallelize" (to `docs/perf/`).
8. **Park.** The April-June polish sections and "NEXT SESSION (queued 2026-06-21)" (149 days old). In the backlog, two of the six DONE/RESOLVED entries have open residue ("design sub-question (b) still open", measured); split those.
9. **Pointers.**
   - The 24 dangling citations and 12 dead memory filenames from the scan.
   - `docs/todo.md` in `scripts/deep_dive_engine.js`.
   - `src/gopvpsim/user_collection.py` and `evolution_lines.py` are not engine-hash files (measured against `_ENGINE_FILES`), so their comments can be edited.
   - `battle.py:3917` cannot be edited: add a tombstone heading in TODO, or leave it.
   - `tests/test_fire_now_cmp_shadow.py:123` cites `TODO.md:514-518`; re-anchor it before moving that text.
10. **Satellite docs.** `docs/concepts.md` "Pole model"; the six stale plan headers; `pvpoke_bug_reports.md` Reports 3 and 7; the CHANGELOG fence artifact; "Open threads for next sessions" inside CHANGELOG (audit).
11. **CLAUDE.md, per item.** The Karpathy block (see question 6), the sweep-cache section, the Testing "History:" paragraph, "three" against "all 9" shield scenarios, and the write-time rules block.
12. **Memory, per item.** The 11 volatile lines, the 20 long index lines, and the five files over 4k chars.
13. **Gates last** (section 3), once TODO is under the chosen cap.

Audit items I did not re-verify and left out: the docs index, CHANGELOG entry ordering, and the ID numbering table.

## 7. Open questions

Design-setting (needed before the first run):

1. **Single sink.** Is CHANGELOG the only home for finished work, with `docs/TODO_archive.md` frozen?
2. **Condense or copy on moves to CHANGELOG.** I recommend condensing and citing the pre-move commit. The cost: the full text is then only in git.
3. **Startup read.** Change "read TODO.md every session" to "read the `Resume here` block and the heading list; grep the rest"? This is the lever on why TODO collects reminders. If the full read stays, the cap has to budget for reminders.
4. **Commit-time checks.** Are checks 1 and 2 in section 3 acceptable? Check 1 will sometimes trip on a legitimate word (`TODO.md:841` today). When the cap blocks a commit mid-feature, should the session groom then, or may it defer?

Can wait:

5. **Backlog.** Keep `docs/TODO_backlog.md` with a review trigger (the scan shows 132 idle days), or fold it into TODO and retire it?
6. **Karpathy block.** Dropping the project copy assumes the global CLAUDE.md is always loaded. That is false on another machine or in a collaborator's clone. Drop it anyway?
7. **Install.** Global at `~/coding/dotfiles/claude/skills/project-hygiene/` (the sandbox denies writes there, so Michael would copy it), or in this repo first? And `.hygiene.toml` at the repo root, or under `.claude/`?
8. **Re-taught lessons** (node harness, heartbeat). Should a later version grep session transcripts for "I thought we had documented"?
9. **B.5 scope.** Widen the semantic pass to `concepts.md`, the divergences doc and the bug-reports doc, and run it at hygiene time?
10. **Memory snapshots.** Where should they go (a dotfiles commit, the reports repo, or a scratch dir)?
11. **Cost ceiling for the first run.** It is 13 steps over about 1 MB of live text; earlier grooms used up to 9 agents on one section.

## Files written

- `/private/tmp/claude-1976725803/-Users-mglerner-coding-gopvpsim/079d4594-feed-4ac3-969a-9c296bd84fdc/scratchpad/skill/project-hygiene/SKILL.md` -- the skill.
- `/private/tmp/claude-1976725803/-Users-mglerner-coding-gopvpsim/079d4594-feed-4ac3-969a-9c296bd84fdc/scratchpad/skill/project-hygiene/hygiene_scan.py` -- the helper (`scan`, `removed`).
- `/private/tmp/claude-1976725803/-Users-mglerner-coding-gopvpsim/079d4594-feed-4ac3-969a-9c296bd84fdc/scratchpad/skill/project-hygiene/write-time-rules.md` -- template rules to propose for a project's CLAUDE.md.
- `/private/tmp/claude-1976725803/-Users-mglerner-coding-gopvpsim/079d4594-feed-4ac3-969a-9c296bd84fdc/scratchpad/skill/project-config/gopvpsim.hygiene.toml` -- example config (would be installed as `.hygiene.toml`).
- `/private/tmp/claude-1976725803/-Users-mglerner-coding-gopvpsim/079d4594-feed-4ac3-969a-9c296bd84fdc/scratchpad/skill/scan_output_gopvpsim.txt` -- the scan of gopvpsim @ 1b6904d (`--max 40`).
- `/private/tmp/claude-1976725803/-Users-mglerner-coding-gopvpsim/079d4594-feed-4ac3-969a-9c296bd84fdc/scratchpad/skill/removed_output_2026-08-27_groom.txt` -- `removed` run on the 08-27 groom, as a worked example.

Not written: `/private/tmp/claude-1976725803/-Users-mglerner-coding-gopvpsim/079d4594-feed-4ac3-969a-9c296bd84fdc/scratchpad/skill/REPORT.md` (Write tool refused; text is above).