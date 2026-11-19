# project-hygiene: build notes

> **Archived 2026-11-18.** Point-in-time record; paths below under the
> session scratchpad, `project-hygiene/`, `_runs/` and the other build
> dirs no longer exist. The skill is installed at
> `~/coding/dotfiles/claude/skills/project-hygiene/` (dotfiles `affa74d`).

Date: 2026-11-17. Written by the completeness critic at the end of the
build. Everything marked "checked" was run or read in that last step;
everything else is labelled with who reported it.

Build dir: `/Users/mglerner/coding/gopvpsim/docs/reviews/2026-11-17_project_hygiene/project-hygiene`.
Nothing is installed yet: `~/.claude/skills/project-hygiene/` does not
hold this build. Nothing was committed in gopvpsim or DNA.

## What was built

One global skill: a short `SKILL.md` (13.4k chars; v1 was 10.6k) for the
standard pass (scan -> judge -> triage table in chat -> apply -> verify),
ending in a menu of optional extras. Each extra has a one-line reason
computed by the scanner, a rough cost, and its own file in `references/`
that is read only when picked. Each is also invocable directly
(`/project-hygiene code|claims|deep|registered-move|gate`).

| Path                                   | What                                                                              |
| -------------------------------------- | --------------------------------------------------------------------------------- |
| `SKILL.md`                             | the standard pass, the model (kinds, registered, no_edit), the menu step          |
| `write-time-rules.md`                  | template of rules for a project's instructions file, with the gopvpsim example    |
| `references/config.md`                 | `.hygiene.toml` schema (every key in `core.py` is documented; checked by script)  |
| `references/baseline.md`               | baseline file, commands, workflow                                                 |
| `references/code-review.md`            | the `code` extra                                                                  |
| `references/claims-vs-source.md`       | the `claims` extra                                                                |
| `references/deep-review.md`            | the `deep` extra (7 lenses, 2 refuters per finding, critic, HTML report)          |
| `references/registered-moves.md`       | the `registered-move` extra                                                       |
| `references/repo-gate.md`              | contract for a repo's own commit check (`gate`)                                   |
| `project-config/gopvpsim.hygiene.toml` | example config for gopvpsim, reflecting the 2026-11-17 decisions                  |
| `hygiene_scan.py`                      | entry: PEP 723 header (python >= 3.11, pyyaml), argparse only                     |
| `hygiene/`                             | the scanner, 19 files, 4,849 lines                                                |
| `tests/`                               | 20 test files, @NTESTS@ tests, plus `tests/data/hygiene-{key,metric}-vector.json` |
| `MODULE_PLAN.md`                       | build-time plan and change log of the integration and review-fix rounds           |
| `_runs/`, `_tmp/`, `_regress/`         | scratch and evidence from the build; not part of the skill                        |

### Modules (`hygiene/`)

| Module           | Checks / role                                                                                             | Spec       |
| ---------------- | --------------------------------------------------------------------------------------------------------- | ---------- |
| `core.py`        | config loader, git helpers (`-z` path listings), Repo, kinds, Finding, baseline key, metrics, registries  | s0, s1     |
| `report.py`      | Report, `scan`, `--brief`                                                                                 |            |
| `baseline.py`    | `baseline init / check / prune / accept / mark-deep`                                                      | s1         |
| `budgets.py`     | BUDGET, the Budgets table, whole-set size and growth                                                      | s4         |
| `banned.py`      | BANNED (`retired_terms` is sugar for it)                                                                  | s2         |
| `echo.py`        | CODE, ECHO, the `claims` menu reason                                                                      | s3         |
| `flags.py`       | FLAG-AGE                                                                                                  | s14        |
| `noedit.py`      | NOEDIT, `baseline freeze`                                                                                 | s5         |
| `plugins.py`     | EXT (`extra_checkers`), PLUGIN, `derive`                                                                  | s9         |
| `pre.py`         | PRE, incl. unpushed commits touching no_edit files and known-failing tests                                | s8         |
| `registered.py`  | REGISTERED, `removed --strict`, the `registered-move` menu reason                                         | s6         |
| `checks_refs.py` | REFS-path, -mem, -cite, -line, -tmp, -bare, -flag                                                         | s7         |
| `checks_mem.py`  | MEM, MEM-index, MEM-volatile, MEM-size, MEM-link                                                          | s13        |
| `checks_docs.py` | SECT, DONE, AGED, DUP-recipe, DUP-para, DUP-sha, PLAN (v1)                                                |            |
| `resume.py`      | RESUME: one "Resume here" block, first section of its file, under a line cap                              | (gopvpsim) |
| `code_extra.py`  | PY-PARSE, CONFIG-PARSE, RUFF, TESTS, COLLECT, FORBID, ABS, ORPHAN, DUPCONST; `code`; the code menu reason | s11        |
| `menu.py`        | the menu, the `deep` and `gate` reasons                                                                   | s12, s15   |
| `removed.py`     | `removed` (loss check of a change; rename-aware)                                                          |            |

### Command line

`HS` = `uv run --script <skill dir>/hygiene_scan.py`.

| Command                                                | Does                                                   | Runs repo code            |
| ------------------------------------------------------ | ------------------------------------------------------ | ------------------------- |
| `HS scan --repo P [--config F] [--max N] [--only IDS]` | full report, Summary, "Not checked", menu              | yes, and lists each       |
| `HS scan --repo P --brief`                             | 2-4 lines: caps, counts, could-not-run, extras         | no                        |
| `HS menu --repo P`                                     | the menu only                                          | no                        |
| `HS removed --repo P [REV or A..B] [--strict]`         | lost tokens, cited headings removed, protected lines   | no                        |
| `HS removed --repo P --dirs OLD NEW`                   | the same for two directories (memory snapshot vs live) | no                        |
| `HS code --repo P [--only IDS]`                        | the code extra                                         | TESTS and COLLECT: pytest |
| `HS baseline init / check / prune [--code]`            | write / compare / shrink `.hygiene-baseline.json`      | yes, and lists each       |
| `HS baseline check --list`                             | also KNOWN items with keys                             | yes                       |
| `HS baseline accept KEY --note ".." [--code]`          | mark an item (or a NEW finding) accepted               | yes                       |
| `HS baseline freeze PATH...`                           | record a no_edit file's blob hash in its manifest      | derive plugins            |
| `HS baseline mark-deep [REV]`                          | set `last_deep_rev`                                    | no                        |

Exit codes: 0, except `baseline check` (1 on FAIL), `removed --strict`
(1 when a registered line is lost) and a bad `--repo` or config (message,
non-zero). `--repo` must be the top of a git work tree.

"Repo code" = `extra_checkers`, `[[plugin]]` commands, `[[echo]]` `cmd`
sources, and (code extra) the test suite. The scanner writes only from
the `baseline` subcommands.

### Config keys (`.hygiene.toml`; details in `references/config.md`)

- Top level: `main_branch`, `doc_dirs`, kind lists `open`, `history`,
  `frozen`, `instructions`, `living` (a list the repo sets REPLACES the
  default; `living` beats the other four; this is the "docs/ defaults
  overridable" decision), `plans`, `out_of_scope`, `no_edit`,
  `protected_patterns`, `retired_terms`, `ref_ignore`, `extra_checkers`,
  `section_lines`, `stale_days`, `warn_frac`, `memory_dir`,
  `memory_index_chars`, `memory_stale_days`, `caps`, `caps_from`.
- Tables: `[[banned]]`, `[[echo]]`, `[budgets]`, `[[no_edit_group]]`,
  `[[registered]]`, `[refs]`, `[[plugin]]`, `[code]`, `[flags]`,
  `[resume]`, `[scope]`, `[forbid]`, `[abs]`, `[gate]`, `[local]`.
- Not in the spec, added on purpose: `[code] pytest_args`, `[code]
  dupconst_tests` (round 2), `living`,
  `memory_stale_days`, `[resume]`, `[local]`, `[abs] severity`, and the
  four tables DNA's committed config already carries (`[scope]`,
  `[forbid]`, `[abs]`, `[gate]`).
- An unknown top-level key is fatal (typo protection). A repo check's
  private keys go under `[local]`.

### Decisions reflected (checked by reading the files)

- gopvpsim example config: CHANGELOG is the one history sink;
  `docs/TODO_archive.md` frozen; TODO `done = "no-rise"` and a char cap;
  `dates = "no-rise"` on CLAUDE.md and DEVELOPER_NOTES.md; one `[resume]`
  block; `[code] default = false`, `pytest_args = ["-m", "not slow"]`;
  engine-hash files as a no_edit group with its consequence.
- SKILL.md and `write-time-rules.md`: moves into history are condensed
  and cite the pre-move commit; the session-start read is the Resume
  block plus TODO's heading list; exactly one block, capped, replaced in
  place; leakage watched by `dates` no-rise and MEM-volatile.
- v1 bug fixed: no REFS check reads `~/.claude/CLAUDE.md` any more (the
  gopvpsim REFS sections name no path from it; the DUP-recipe / DUP-para
  hits against it are the really-duplicated Karpathy block).
- Repo checks share only the config, the baseline format and the key
  vector. The vector equals DNA's `hygiene/key-vector.json` (3 cases,
  compared as parsed JSON).

## How to run

Scanner (offline uv cache already has pyyaml):

    UV_CACHE_DIR=<cache> UV_OFFLINE=1 uv run --script <build>/hygiene_scan.py scan --repo <repo> [--config <file>]

Tests. The prescribed `uv run --with pytest --with pyyaml ...` does NOT
work offline: pytest is not in the uv cache (checked: "pytest was not
found in the cache"; without `--no-project` uv also tries to build
gopvpsim). PACKAGE NEEDED IN THE UV CACHE: pytest. What works:

    cd <build> && PYTHONDONTWRITEBYTECODE=1 \
      PYTHONPATH=<uvcache>/archive-v0/MmaHr3i1ME1Enz_c \
      /Users/mglerner/coding/gopvpsim/.venv/bin/python -m pytest tests -q -p no:cacheprovider

(the PYTHONPATH entry is the cached PyYAML, so the yaml tests run too).

Install, when Michael says so (dotfiles is not writable from this
session): copy `SKILL.md`, `write-time-rules.md`, `hygiene_scan.py`,
`hygiene/`, `references/`, `project-config/` to
`~/.claude/skills/project-hygiene/`. Do not copy `_runs/`, `_tmp/`,
`_regress/`, `MODULE_PLAN.md`, `BUILD_NOTES.md`; keep `tests/` with the
source. ruff must be on PATH (it is: `~/.local/bin/ruff`; fallback
`uvx ruff`).

## Tests (checked)

- 225 passed, 0 failed, 0 skipped, 367 s: the full run AFTER the three
  small edits below (before them: 225 passed, 372 s).
- ruff `--select F,E9` clean on `hygiene/`, `tests/`, `hygiene_scan.py`.
  All skill files are ASCII; no `XXX:` markers; no `__pycache__`.
- The suite takes about 6 min: nearly every test builds a git repo and
  runs whole scans as subprocesses (slowest single test 5.8 s).

Edits made in this step:

1. `references/config.md`, `references/repo-gate.md`: the `lines` metric
   was still described as `len(text.splitlines())`. The code and DNA's
   check use `text.count("\n")` plus 1 for an unterminated last line. A
   repo-check author copying the old text would have diverged on form
   feeds.
2. `hygiene/code_extra.py`: the listed pytest command is now shell-quoted
   (it printed `-m not slow tests`).
3. `hygiene_scan.py` docstring: no longer points at `MODULE_PLAN.md`,
   which is not installed.

## Scan results (checked, 2026-11-17)

### gopvpsim @ 1b6904d, `project-config/gopvpsim.hygiene.toml`

| Run                                       | Time  |
| ----------------------------------------- | ----- |
| `scan` (full; runs `verify_dev_notes.py`) | 2.3 s |
| `scan --brief`                            | 2.1 s |
| `scan` with no config                     | 2.1 s |
| `removed HEAD~10..HEAD`                   | 1.5 s |
| `baseline check` (no baseline file yet)   | 2.4 s |
| `code --only` the 7 static checks         | 1 s   |
| `code --only TESTS` (`-m "not slow"`)     | 273 s |
| `code --only COLLECT`                     | 1 s   |

| Check        | Count | Note                                                       |
| ------------ | ----- | ---------------------------------------------------------- |
| BUDGET       | 0     | 2 over a warn budget: TODO 89,491 > 60,000; CLAUDE 26,422  |
| PRE          | 3     | 1 extra worktree, 2 unmerged branches                      |
| NOEDIT       | 0     | group and consequence are printed; no manifest             |
| SECT         | 16    |                                                            |
| DONE         | 29    | 18 of them in TODO.md (the `done:TODO.md` metric)          |
| AGED         | 12    |                                                            |
| RESUME       | 1     | fail: no Resume block yet (expected until the first groom) |
| REFS-path    | 5     | 2 are proposed files, not dead ones (see OPEN 9)           |
| REFS-mem     | 8     | plus 4 in frozen/history, not listed                       |
| REFS-cite    | 24    | plus 13 in frozen/history                                  |
| REFS-line    | 6     |                                                            |
| REFS-tmp     | 9     |                                                            |
| DUP-recipe   | 8     |                                                            |
| DUP-para     | 1     |                                                            |
| DUP-sha      | 2     |                                                            |
| PLAN         | 6     |                                                            |
| CODE         | 3     | warn                                                       |
| BANNED       | 1     | warn (`### Pole model` heading in docs/concepts.md)        |
| MEM-index    | 26    |                                                            |
| MEM-volatile | 12    |                                                            |
| MEM-size     | 5     |                                                            |
| MEM-link     | 3     | info                                                       |
| EXT          | 4     | `verify_dev_notes.py` exit 0, 2 warning lines              |
| RUFF         | 82    | isolated F401,F811,F821,F841,E9                            |
| ABS          | 6     |                                                            |
| ORPHAN       | 1     | info                                                       |
| DUPCONST     | 117   | 97 unequal sites (warn), mostly test fixtures              |
| PY-PARSE     | 0     |                                                            |
| CONFIG-PARSE | 0     |                                                            |
| TESTS        | 15    | 6 FAILED + 9 SKIPPED of 3,123 passed (see below)           |
| COLLECT      | 0     | bare pytest collects 3,304 tests                           |

Menu: code (not pre-selected), claims (3 disagree), deep (live set 866
KB), gate (6 rules, no baseline). `baseline check` without a baseline:
FAIL (1 failing = RESUME), three no-rise metrics UNRECORDED, TODO chars
89,491 under `cap:90000`.

TESTS ledger on gopvpsim, first real run: it works (ledger plugin loaded,
skips carry their reasons, `git status` unchanged after). It reported 6
FAILED tests in the fast tier. NOT diagnosed here, and the run was inside
the Bash sandbox, so some may be sandbox effects:
`test_cramorant.py::test_default_moveset_and_none_padding`,
`test_mega_cup_registry.py::test_gl_excludes_are_honoured_upstream`,
`test_mega_level_cap.py::test_non_supermegas_and_non_megas_are_unaffected`,
`test_ml_guide_progress.py::test_print_ml_guides_parses_synthetic_wrapper`,
`test_precommit_hook.py::test_deletion_only_commit_still_runs_the_gate`,
`test_verify_overnight_pool_containment.py::test_real_dives_contain_their_declared_pools`.
Michael should look at these whatever happens to the skill.

### DNA @ 4c56dad, read-only

Full scan and `baseline check` were run with
`_tmp/integrator-dna.hygiene.toml`: DNA's committed `.hygiene.toml` with
the `[[plugin]]` and the two derive-based `[[no_edit_group]]` tables
removed, so no DNA code ran. So NOEDIT and PLUGIN are NOT covered by
these numbers. With DNA's own config only `--brief` and `menu` were run
(they run no repo code; `--brief` says `could not run: PLUGIN
snakemake-inputs`). `git -C ~/coding/DNA status --short` was `?? .claude/`
before and after.

| Run                            | Time  |
| ------------------------------ | ----- |
| `scan` (plugin-free config)    | 1.0 s |
| `scan --brief` (own config)    | 1.0 s |
| `baseline check` (plugin-free) | 1.0 s |
| `removed --strict`             | 0.3 s |
| `code --only` 7 static checks  | < 1 s |

| Check        | Count | Note                                                           |
| ------------ | ----- | -------------------------------------------------------------- |
| BUDGET       | 0     | 3 over warn: memory zwc-project-state 309 > 60, CLAUDE, PLAN   |
| PRE          | 9     | 5 worktrees, 4 unmerged branches                               |
| SECT         | 1     |                                                                |
| DONE, AGED   | 0     | DNA has no open-kind file                                      |
| FLAG-AGE     | 8     | 6 older than 30 d                                              |
| REFS-path    | 1     |                                                                |
| REFS-line    | 1     |                                                                |
| REFS-bare    | 3     | warn: `parmdiff.py` (2), `accounts.py`                         |
| REFS-flag    | 1     | warn: `snakemake-trace.py --profile` (a wrapper passing it on) |
| REGISTERED   | 6     | matches the spec's 6 blocks                                    |
| ECHO         | 1     | fail: `protocol/README.md:11`, 19 vs 40                        |
| BANNED       | 11    | fail 7 (repo files), warn 4 (memory quotes)                    |
| MEM-index    | 3     |                                                                |
| MEM-volatile | 2     |                                                                |
| MEM-size     | 1     |                                                                |
| MEM-link     | 1     | info                                                           |
| RUFF         | 18    |                                                                |
| FORBID       | 20    | keys equal DNA's baseline: 20 of 20                            |
| ABS          | 99    | keys equal DNA's baseline: 99 of 99                            |
| ORPHAN       | 2     | info                                                           |
| DUPCONST     | 88    | 24 unequal sites                                               |
| PY-PARSE     | 0     |                                                                |
| CONFIG-PARSE | 0     |                                                                |

`baseline check` against DNA's committed baseline (127 items: ABS 99,
FORBID 20, BANNED 7, ECHO 1): PASS. BANNED KNOWN 7 (1 accepted), ECHO
KNOWN 1, 0 GONE; REFS-bare 3 and REFS-flag 1 print as lower-case `new`
(not gated). `removed --strict`: 6 blocks, 470 lines, 0 lost. Menu: code
`[x]`, claims, deep (274 KB), registered-move (PLAN.md 1654 lines, 6
blocks); no gate entry because the baseline exists. TESTS, COLLECT and
`baseline check --code` were not run on DNA (forbidden for this session).

### Scratch-repo lifecycle (checked, own repo in $TMPDIR)

gopvpsim-style config (done / dates no-rise, char cap, resume, no_edit
group, an `extra_checkers` script that writes a file):

- `scan --brief` and `menu` did not run the script; `baseline check` did
  and listed it.
- `init` -> 0 items, 2 metrics; `check` -> PASS.
- Planted a done line, a date in CLAUDE.md, a retired term and a second
  Resume block: `check` -> rc 1, 3 failing (`done` OVER, `dates` OVER,
  RESUME FAIL); the retired term is lower-case `new` (warn, by design).
- `--repo` on a non-git dir -> message and rc 1.

## Fix round 2 (DNA validation, 2026-11-17)

Raw evidence from the DNA session: its scratchpad `val/`. Suite after
the round: 269 passed, 0 failed, 0 skipped, 398 s
(`_runs/round2_tests_final.out`; 225 before, +44 in `test_round2.py`);
two older tests changed on purpose (`test_baseline.py`
`test_gate_limits_which_ids_fail`: an unconfigured gated BUDGET is now
NOT RUN; `test_code_extra.py` RUFF tag text). Tests for every
item are in `tests/test_round2.py`; each failed before its fix (run saved
in `_runs/round2_tests_before_fix.out`) except items 7 and 8, which were
already so and are now pinned end to end.

| #   | Change                                                                                                                                                                                                                                                                                                         | Where                                                            |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 1   | BLOCKER fixed: every `baseline` command runs the static code checks (PY-PARSE, CONFIG-PARSE, FORBID, ABS); only RUFF, TESTS, COLLECT, ORPHAN, DUPCONST need `--code`. A gated id that did not report prints `NOT RUN <id>: <why>`, is left out of `gate =`, and is named after `NOT RUN:` on the last line     | `baseline._collect`, `baseline.not_run`, `code_extra.STATIC_IDS` |
| 1   | audit: plugin that failed, no_edit derive that failed (`Report.partial`), check that could not run (ruff, pyyaml), unconfigured gated id: all NOT RUN now. ECHO `cmd` sources already gave a fail finding ("source unreadable"); EXT never gates (text only)                                                   | `report.Report`, `noedit.check_noedit`                           |
| 2   | REFS-flag reads CommonMark indented code blocks; a list item's indented continuation and a paragraph's indented lazy line are prose                                                                                                                                                                            | `checks_refs.indented_code`, `_cmd_lines`                        |
| 3   | RUFF no_edit tag: `[no_edit <id>: do not edit while finished runs list it; <consequence>]`; plain `no_edit`: `[no_edit: listed in no_edit; do not edit it (project rule)]`                                                                                                                                     | `code_extra.check_ruff`                                          |
| 4   | DUPCONST unequal msg gives every site's value and the outlier(s) (sites off the majority value; "no majority value" on a tie)                                                                                                                                                                                  | `code_extra.check_dupconst`                                      |
| 5   | REFS-path resolves against `git ls-files` only (dead_ok kept). Checked the others: REFS-bare / REFS-flag already used tracked files; REFS-mem reads the memory dir by design; ECHO json/yaml/py sources still read the disk file (a tracked source normally)                                                   | `checks_refs.check_refs`; `core.Repo.exists_exact` removed       |
| 6   | `removed --strict` (working tree): a lost line that an untracked, not-ignored file holds verbatim says "destination not tracked: git add it"                                                                                                                                                                   | `registered.strict_removed`, `_untracked_texts`                  |
| 7   | plugin `"checks"` was already implemented; docs now state the GONE rule in `config.md` and `repo-gate.md`                                                                                                                                                                                                      | docs only                                                        |
| 8   | hard caps absolute: already so; pinned for an `accepted` BUDGET item; docs say "confirmed by DNA"                                                                                                                                                                                                              | docs only                                                        |
| 9   | gate rule (NEW and severity fail and id in `[gate] fail` when set; supersedes spec s1) stated in `baseline.md`, `repo-gate.md`, `config.md`, SKILL.md step 1, `baseline.py` docstring                                                                                                                          | docs                                                             |
| 10  | `tests/data/hygiene-metric-vector.json` (DNA's 6 cases + `"a\nb"` -> 2). It found a real bug: `core.read` used `read_text()`, whose universal newlines made `a\rb\n` 2 lines (DNA: 1). Files are now read as bytes decoded as UTF-8 (also `code_extra.read_strict`). DNA's `measure()` gives the same 7 values | `core.read`, `code_extra.read_strict`                            |
| 11  | DUPCONST skips test files unless `[code] dupconst_tests = true`; DONE ignores FIXED as "constant" (`core.done_line`, `FIXED_CONST_RE`; the `done` metric uses it too); REFS-path skips a line saying the file is proposed ("would live at", "new file", "proposed", "to be created", "to create")              | `code_extra`, `core`, `checks_docs`, `checks_refs`               |

DONE before/after (`_runs/round2_done_diff_gopvpsim.out`, every tracked
`.md`): gopvpsim 182 -> 177 marker lines; the 5 that changed are all
FIXED-as-constant (TODO.md:841 "is FIXED (`<name>.tmp`)", cache design
:144 "a FIXED level", :146 "vs FIXED `15/15/15`", pvpoke_bug_reports:514
"the FIXED page", a review doc :208 "the FIXED value"). No status marker
was lost (TODO.md:171 "FIXED for the sandbox" still counts). DNA: 44 ->
41, all "the FIXED row(s)" in a frozen audit doc.

Count deltas (`_runs/round2_*`; same machine, same commits as the
`round2_before_*` runs; gopvpsim @ 1b6904d, DNA @ e8b0359 with
`_tmp/round2-dna-noplugin.hygiene.toml`):

| Repo     | Check            | Before | After  | Why                                                                                          |
| -------- | ---------------- | ------ | ------ | -------------------------------------------------------------------------------------------- |
| gopvpsim | DONE             | 29     | 28     | TODO.md:841 FIXED-as-constant dropped; `done:TODO.md` 18 -> 17                               |
| gopvpsim | REFS-path        | 5      | 6      | +1 `.claude/settings.local.json` (gitignored, on disk); proposed: 0 cut                      |
| gopvpsim | DUPCONST         | 117    | 46     | tests skipped; unequal sites 97 -> 28                                                        |
| gopvpsim | `baseline check` | FAIL 1 | FAIL 7 | ABS 6 now checked without `--code` (no `[gate]` list in this config)                         |
| DNA      | REFS-path        | 1      | 2      | +1 `cluster/analysis-loop.json` (runtime file, gitignored, on disk)                          |
| DNA      | DUPCONST         | 88     | 81     | tests skipped; unequal sites 24 -> 20                                                        |
| DNA      | `baseline check` | PASS   | PASS   | now also FORBID KNOWN 20, ABS KNOWN 99; `NOT RUN NOEDIT` (no groups in the plugin-free copy) |

Every other count is unchanged on both repos. `git status --short` was
the same before and after on both. Not re-run: TESTS (gopvpsim, 273 s;
untouched code path), anything with DNA's plugin, TESTS or COLLECT.

Left open by this round:

- REFS-path "proposed" removes none of gopvpsim's 5 today: their wording
  is a plan step ("3. `scripts/mechanics_notice.py`: export ..."), a
  feature title ("Personal-collection: `scripts/suggest_builds.py`"), "a
  small `scripts/measure_html_size.py` or inline". A rule wide enough for
  those would hide dead pointers; use `ref_ignore` or reword.
- The two new tracked-only REFS-path hits cite runtime/per-machine files
  on purpose; candidates for `ref_ignore` in each repo's config.
- ABS's default regex `/home/` matches URLs (`https://img.pokemondb.net/
  sprites/home/normal/...`): 2 of gopvpsim's 6 ABS hits. Not changed here.
- Our metric vector has 7 cases, DNA's 6: DNA may add `"a\nb"` -> 2.

## Fix round 3 (verifier residuals of round 2, 2026-11-17)

Two items came back from the round-2 verifiers; both were real and are
fixed. Tests: `tests/test_round3.py`, @NR3@ tests. The ECHO, FIXED and
REFS-path tests failed before their fix (`_runs/round3_tests_before_fix.out`:
13 failed, 11 passed; the 6 "still skipped" / 5 "still constant" cases are
positive controls that pass on both sides). The two REFS-path tests in
that first run read `rep.findings`, which REFS-path does not fill (it is a
text section), so they failed for the wrong reason; they were rewritten to
read the scan section and re-run against the old line-level rule, where
they fail for the right reason (`_runs/round3_tests_before_fix_refs.out`:
2 failed, 6 passed), then pass with the fix. Full suite: @FULL@
(`_runs/round3_tests_final.out`). ruff (F, E9) clean, ASCII, no
`__pycache__`.

| #   | Verdict and change                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Where                                                                                                                |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 1   | REAL. An `[[echo]]` source that fails ("echo <id> source unreadable") was baselined by `init` as debt, and every later `check` printed PASS with `gate = ECHO`. Now: ECHO sets `rep.partial` and `rep.unchecked` (the finding keys). Such a finding is never baselined; `check` prints it as FAIL (severity fail, gated), lists `NOT RUN ECHO` and leaves ECHO out of `gate =`; `init` refuses while any check could not run or is partial (DNA's rule); `accept` refuses the key | `echo.check_echo`, `report.Report.unchecked`, `baseline._base`, `_skipped`, `not_run`, `cmd_init/check/prune/accept` |
| 1   | REAL, found while writing the test: when a source that worked at `init` breaks, the rule's mismatch items turned GONE (ECHO was in `ran`), so `prune` would have dropped real debt. A partial check no longer counts as ran for GONE                                                                                                                                                                                                                                              | `baseline._base`                                                                                                     |
| 1   | Not changed (verifier agrees): a run whose only gated ids are NOT RUN still says PASS, rc 0, as DNA's SKIPPED                                                                                                                                                                                                                                                                                                                                                                     |                                                                                                                      |
| 11a | REAL. FIXED-as-constant was too broad: any "is/was FIXED <lower-case word>" and "is FIXED (`<sha>`)" dropped a done marker. Now: article or `vs` + FIXED + (code span or lower-case word); a copula + FIXED only before a code span that is not a 7-40 hex sha. "is FIXED now / but / today / locally / too / here / (`abc1234`)" count again                                                                                                                                     | `core.FIXED_CONST_RE`                                                                                                |
| 11b | REAL. PROPOSED_RE matched anywhere on the line and skipped every path on it ("Run scripts/x.py to create the index", "The proposed fix lives in scripts/x.py"). Now anchored to the path token: right before it "would live at/in", "new file", "proposed:", "add", "create", "write"; right after it "(proposed)", "(to be created)", ", to be created". "to create" alone is gone; round 2's pinned "add scripts/new_tool.py to create the index" stays skipped through "add"   | `checks_refs.PROPOSED_BEFORE_RE`, `PROPOSED_AFTER_RE`                                                                |
| 11  | Rejected as non-defects (verifier agrees): the 4 DUPCONST script sites that dropped had only test-file partners (by design). The round-2 notes called all 5 dropped DONE lines "constant"; pvpoke_bug_reports:514 and the bandaid910 review :208 mean "repaired". Neither is an open-work done marker nor in DONE scope, so no true positive is lost; wording corrected here, behaviour kept                                                                                      |                                                                                                                      |
| --  | Minor, not changed: DUPCONST's message says "majority value" where the value is a plurality (most common) when there are 3+ distinct values                                                                                                                                                                                                                                                                                                                                       | `code_extra.check_dupconst`                                                                                          |

Docs: `references/baseline.md` (unreadable inputs, `init` refusal),
`references/config.md` (`done` FIXED rule, REFS-path proposed rule), the
`baseline.py` docstring.

Re-scan (`_runs/round3_*`, same configs as round 2). DONE over every
tracked `.md` (`_runs/round3_done_diff.out`): gopvpsim 182 -> 177 and DNA
44 -> 41, the same lines as round 2 (DNA's 3 are PLAN.md:843 "a FIXED
target twist" and two "the FIXED row(s)" in the audit doc; round 2's note
said all three were in the audit doc). Scan Summary vs round 2: DNA
unchanged; gopvpsim PRE 3 -> 4 and REFS-path 6 -> 7, both caused by the
stray commit `2518127 "j"` now on gopvpsim main (unpushed: +1 PRE line;
its README.md:78 cites `docs/sub/page.md`: +1 REFS-path), not by this
round. `baseline check` output is byte-identical to round 2 on both
(gopvpsim FAIL 7, NOT RUN COLLECT, TESTS; DNA PASS, NOT RUN NOEDIT). A
plain `_collect` on both repos has no failed, partial or unchecked
check, so `init` would not refuse there. `git status --short` and HEAD
were the same before and after on both (`_runs/round3_*status*.out`).

## Known deviations from the spec (on purpose; DNA should confirm)

1. s1 says `baseline check` exits 1 on NEW. Here, as in DNA's
   `check.py`, only a NEW finding of severity fail fails, and with
   `[gate] fail` only for listed ids. `retired_terms` are warn, so they
   never gate; a term that must not come back needs a `[[banned]]` rule
   with `severity = "fail"`. `check` prints a note when a gated id has
   NEW warn findings. Round 2: confirmed by DNA; the docs now say the
   spec s1 wording is superseded.
2. s15 code menu reason: the menu never runs ruff or pytest, so without a
   code baseline it says the counts are unknown and gives file counts.
3. s9: a plugin may also print `"checks": [...]` (ids it owns), so that a
   clean run can mark its old items GONE. Protocol addition; round 2:
   accepted by the DNA session and documented in `config.md` and
   `repo-gate.md`.
4. s6: `removed --strict` is byte-exact per line, except that one indent
   shift applied to the whole block is allowed.
5. Hard budget caps are absolute here (a baselined BUDGET item does not
   excuse one). In DNA's `check.py` a hard-cap hit is an ordinary
   finding that the baseline can hold as KNOWN (read: check.py:218).
   Round 2: DNA confirmed absolute is the contract.
6. Memory findings are never baselined (per machine, untracked). RESUME
   is never baselined either: checked from the config every run.
7. `baseline accept KEY` also accepts the key of a NEW finding;
   `baseline mark-deep` exists because s12 names no writer for
   `last_deep_rev`.

## OPEN

Needs Michael:

1. Install to dotfiles (list above), and add pytest to the offline uv
   cache if the uv test command should work.
2. Placeholders in the gopvpsim config: TODO `chars.hard = 90000`
   (today's size rounded up) and `[resume] max_lines = 40`. Reset the cap
   to about 1.5x the post-groom size after the first groom.
3. gopvpsim's own commit check is NOT built: the extension of
   `scripts/verify_dev_notes.py` (done no-rise, TODO cap, dates no-rise,
   RESUME), its tests, and `.hygiene.toml` / `.hygiene-baseline.json` in
   the repo root. That is work in gopvpsim outside the build dir.
   gopvpsim's CLAUDE.md "Session startup" also still says to read all of
   TODO.md and DEVELOPER_NOTES.md.
4. The 6 failing gopvpsim fast-tier tests above.
5. A dangling commit in gopvpsim's reflog: a build agent committed by
   mistake and reset (`5012d82 "verbatim move"`, HEAD is back at
   1b6904d; checked with `git reflog`). Nothing is on a branch; it will
   expire on its own.
   A SECOND stray commit (`2518127 "j"`, author `a <a@b>`, from a
   round-2 verifier whose throwaway dir vanished so its commands ran in
   gopvpsim) was REMOVED by the main session with `git reset --keep
   1b6904d` after checking its diff (3 lines in .gitignore/README.md,
   unpushed). HEAD is 1b6904d again.
6. A fix-round agent ran DNA's plugin
   `hygiene/plugins/snakemake_inputs.py` three times through a full scan,
   against the rule for this build. It reported DNA's status unchanged.
7. DUPCONST on gopvpsim: 97 unequal sites, mostly test fixtures. Round
   2: tests are skipped by default (`[code] dupconst_tests`); 28 unequal
   sites left.
8. `baseline freeze --all` is not built (freeze takes explicit paths).
9. Known noise left in: REFS-path cannot tell a proposed file from a dead
   one (2 of 5 gopvpsim hits; round 2 added a phrase rule, round 3
   anchored it to the path token; it catches none of them, see "Fix
   round 2/3"); DONE matched FIXED used as
   "constant" (fixed in round 2, `done` metric too); DUP-recipe
   fires on one shared span of 40+ chars (schema examples). The reviewers'
   fixes for the last two were rejected as cross-implementation changes.
10. Cosmetic: BANNED NEW lines repeat the line text inside the message;
    the "whole set" line and the deep menu reason use different
    definitions of the live set (1,041 KB incl. history vs 866 KB).
11. `log --name-only` (PRE unpushed) can still mis-read a file name
    containing a quote, backslash or control character.
12. `_tmp/`, `_runs/`, `_regress/` still hold build scratch.

Not verified by anyone:

- The global scanner's NOEDIT / PLUGIN path against DNA's real plugin and
  `.hygiene-frozen.json` in a run whose output was kept (the fix agent's
  run is the only one; its counts are not recorded here).
- TESTS / COLLECT / `baseline check --code` on DNA.
- The `deep` extra: it is instructions only; no fan-out was executed.
- The skill driven end to end by an agent from `SKILL.md` on a real
  groom.

## Message for the DNA session (validation round)

Send this text:

> The global project-hygiene scanner is built (not installed yet). Please
> validate it against DNA; you own DNA, so you may run its plugin and
> tests, which the gopvpsim session could not.
>
> HS = `uv run --script /Users/mglerner/coding/gopvpsim/docs/reviews/2026-11-17_project_hygiene/project-hygiene/hygiene_scan.py`
> (write it out in full; read-only for you: do not edit anything under
> that directory, report instead). References are next to it:
> `SKILL.md`, `references/config.md`, `references/baseline.md`,
> `references/repo-gate.md`, and `BUILD_NOTES.md` (this summary).
>
> Config: none to write. Your committed `.hygiene.toml` @ 4c56dad loads
> as is, including `[scope]`, `[forbid]`, `[abs]`, `[gate]`. Do not add
> keys for the test; if a key is rejected, report it.
>
> Run, from the DNA root, noting `git status --short` before and after:
>
> 1. `HS scan --repo . --brief` (runs no repo code; expect `could not
>    run: PLUGIN snakemake-inputs`).
> 2. `HS scan --repo .` (runs your plugin: `--class sim`, `--class
>    analysis`, no args; the Summary lists each command).
> 3. `HS baseline check --repo . --list` and `python hygiene/check.py`
>    side by side.
> 4. `HS code --repo .` and `HS baseline check --repo . --code` (runs
>    your tests with your `[code] python`; minutes).
> 5. `HS removed --repo . --strict`.
> 6. In a scratch clone, the planted negative controls from the spec:
>    a one-character comment edit to `protocol/twist_cv.py`; a paraphrase
>    of one line inside the `PLAN.md` PRE-REGISTERED block during a move
>    (`removed --strict` must exit 1) and a verbatim move (must exit 0);
>    `python viz/collect.py runs/x --every-pss` in a README; a second
>    copy of "nmropt REST weight ramps linearly 1 -> 0"; one
>    `PAIR_HB_MIN` set to 3; a local commit touching a no_edit file.
>
> What to look for:
>
> - Step 3: the same pass/fail as `check.py`, and the same items. We
>   measured, without your plugin: BANNED KNOWN 7 (1 accepted), ECHO
>   KNOWN 1, FORBID 20 of 20 keys, ABS 99 of 99 keys, 0 GONE, PASS.
>   NOEDIT is the part we could not test: do the two programs agree on
>   the derived file sets, CHANGED / NEW input lines, and their keys
>   against `.hygiene-frozen.json`?
> - Step 2: every REGISTERED block (we see 6), ECHO `protocol/README.md:11`
>   19 vs 40, each no_edit group with its consequence, and no finding
>   under `[scope] exclude` paths. Tell us every false positive. Ones we
>   already see: REFS-bare `parmdiff.py` (CLAUDE.md:83, PLAN.md:1623) and
>   `accounts.py` (cluster/upstream-issues.md:68); REFS-flag
>   `snakemake-trace.py --profile` (workflow/README.md:34); 4 BANNED
>   warn hits in memory `zwc-project-state.md` that quote the rule on
>   purpose (memory is never baselined; the fix is a wider `allow`).
> - Step 4: TESTS should show the two known `cluster/test_dashboard.py`
>   failures if they still fail; COLLECT should be 0 now that
>   `pytest.ini` exists; RUFF should include
>   `protocol/analysis/compare_mg_dt.py` F841 tagged as a no_edit file
>   ("fix by hand only"). These ids are not in your `[gate] fail`, so
>   they print as lower-case `new` and do not fail.
> - Step 6: each plant fires, and nothing else changes.
> - Runtime (we see about 1 s per scan) and any traceback.
>
> Decisions we need from you:
>
> 1. Plugin protocol: may a plugin print `"checks": ["SMK-INPUT", ...]`
>    (the ids it owns), so a clean run can mark its old baseline items
>    GONE? Without it a plugin's fixed items never leave the baseline.
> 2. Hard budget caps: the global check treats `hard` as absolute; your
>    `check.py` lets the baseline hold a hard-cap hit as KNOWN. Which one
>    is the contract?
> 3. Gate rule: we copied yours (NEW and severity fail and id in
>    `[gate] fail`). The spec s1 text says "exit 1 only on NEW". Confirm
>    the spec should say what the code does.
> 4. `lines` metric = `text.count("\n")` + 1 for an unterminated last
>    line (your `measure()`). Add metric cases to the shared key vector?
>    We pin `a\fb\n`, `x<U+2028>y\n` and `a\rb\n` as 1 line each.
> 5. `[abs] severity` (default fail, as in your check) and RESUME
>    (gopvpsim only) are schema additions; `[local]` is the place for
>    keys only your check reads. Any objection?
> 6. Menu reason for `code` says "counts unknown" until a code baseline
>    exists, instead of the spec's "N ruff, M failing tests, K
>    uncollected". Acceptable?

## Main-session fixes after round 3 (2026-11-17)

- TESTS: pytest exit 5 (no tests collected) is an empty ledger when no
  test_*.py is tracked, and "could not run" (pointing at test_paths /
  pytest_args) when test files are tracked. Before, `baseline init --code`
  refused forever in a repo without tests.
- Metric vector made identical to DNA's hygiene/metric-vector.json (6 cases).
- DUPCONST wording: "most common value" (it is a plurality, not a majority).
- REFS-path skips cited paths that .gitignore matches (DNA validation:
  cluster/analysis-loop.json is a runtime state file). DNA REFS-path 2 -> 1
  (the real cluster/chain.py); gopvpsim 5 -> 4 (drops the gitignored
  docs/reference_deep_dives/ path).
- Stray commit 2518127 removed from gopvpsim main (see OPEN 5).
- Suite: 296 tests pass (the 2 yaml tests need the cached PyYAML on
  PYTHONPATH; ruff on PATH).
- DNA re-validation (DNA @ e8b0359): clean on every scenario; no objection
  to install.
