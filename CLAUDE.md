# PoGo PvP Battle Simulator

## Session startup
At the start of every new session, before doing other work, read these
files so you have current context on what's planned, what's broken, and
what's been verified:

- `TODO.md` — pending features, known bugs, design notes for upcoming work
- `DEVELOPER_NOTES.md` — verification status, PvPoke comparison results,
  known bugs we've found in PvPoke

You don't need to re-read them every turn — once per session is enough.
Mention briefly in your first substantive reply that you've read them
(e.g., "Caught up on TODO.md and DEVELOPER_NOTES.md.") so the user
knows the startup happened.

**`CHANGELOG.md` is NOT part of the session-startup read.** It holds
completed/shipped work for historical reference (dates, commit SHAs,
root-cause writeups of old bugs). Consult it on-demand when the user
asks "when did we ship X" or "why did we fix Y," not as routine
context.

## Project goal
A pure Python library for Pokemon Go PvP battle simulation, focused on
breakpoint/bulkpoint analysis. Will be used by CLI scripts and eventually
a BeeWare mobile app.

## General coding guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Architecture
- `data.py` — load and cache PvPoke's gamemaster.json
- `pokemon.py` — stat calculation (CP, level, IV, stat product)
- `moves.py` — move data, damage formula, type effectiveness
- `battle.py` — battle simulation loop with pluggable shield/bait policies
- `breakpoints.py` — breakpoint and bulkpoint analysis

## gobattlekit (downstream consumer)

The sibling app `../gobattlekit` consumes our spreads read-only — we
never call into it; it pulls from us. Flow: a per-species
`thresholds/*.toml` + a deep-dive replay blob
(`userdata/replay/*.replay.pkl.gz`) →
`../gobattlekit/tools/threshold_export/export_thresholds.py` (see its
README) → `bundle_into_app.py` merges into
`src/gobattlekit/data/default_thresholds.toml`. **The bundler is
Great-league only** (`glob("*_great.toml")`); Ultra/Master targets are
hand-maintained in `default_thresholds.toml` and preserved verbatim
across re-bundles. Don't change the `default_thresholds.toml`
nested-dict schema without coordinating. (Discoverability detail only —
read the export tool's README/code for the real contract; it lives with
the code and won't drift.)

## CD-move prep: verify the gamemaster actually lags before injecting

The `cd_prep` TOML table injects a CD move into the legal pool for
pre-CD dives. Before reaching for it, **confirm the gamemaster really
lags**: check the species' `eliteMoves` in the gamemaster and the
pvpoke git log. PvPoke often updates *ahead* of a CD, in which case the
move is already legal and injection is wrong. Inferring "the CD move is
the one missing from the pool" is a trap — absence is ambiguous (could
be "pending" or "the species just can't learn it"). `eliteMoves` + the
commit history are unambiguous. (Baxcalibur 2026-06: the CD move Glaive
Rush was already an `eliteMoves` entry; Brick Break was absent only
because Baxcalibur can't learn it — not a pending CD move.)

## When our sim diverges from PvPoke

**Divergence from PvPoke is not the same as a bug.** PvPoke is the
reference implementation we cross-check against, but it has known bugs
(see DEVELOPER_NOTES "PvPoke bugs found"), and many of its choices are
arbitrary in ways that don't affect the 1v1 score.

Before changing our sim's behavior to match PvPoke's, ask:

1. **Does PvPoke produce a demonstrably better outcome here?** A
   different chargedLog or move sequence is not, by itself, evidence
   that PvPoke is right. Check whether scores, winners, and the
   actual fight outcome differ — and if they don't, PvPoke's choice is
   cosmetic.
2. **Does our deviation have a defensible reason?** Examples of
   intentional deviations already in the codebase: we recompute
   `bestChargedMove` per-turn instead of caching it (PvPoke bug #2);
   we throw self-debuffing moves only when fast-KO won't suffice
   (battle.py:_optimize_move_timing); we fire SS on the optimal turn
   for Mimikyu instead of delaying. These are all places we believe
   we're right and PvPoke is wrong or arbitrary.
3. **Would matching PvPoke make us worse for the actual use case?**
   The use case is breakpoint / bulkpoint analysis for real PvP
   teambuilding. PvPoke optimizes for 1v1 score; we sometimes care
   about post-KO state, multi-mon energy carry-over, etc.

If the answer to all three is "PvPoke isn't better and we have a
defensible reason," **document the divergence and don't change
behavior.** Add an xfail with a specific reason (not "PvPoke says X,
we say Y" but "PvPoke X is arbitrary because Z; we Y because W"), and
add an inline comment at the relevant code site explaining the gate
we're keeping.

If the answer is "PvPoke is right and we should match," fix our code
and update the test fixture to PvPoke ground truth.

Most subtle: when a fix accidentally improves multiple cases (e.g.
the 2026-04-15 raw_dpe fix made Mimikyu xpass), inspect each XPASS
case to confirm the fight is actually identical, not just the score.
Score-coincidence is a real failure mode that the chargedLog
assertions exist to catch.

## Sweep cache: use `--no-sweep-cache` while changing the engine

The sweep disk cache (`scripts/sweep_cache.py`, cache-rework v7) keys a
column on focal + opponent but **NOT** the engine hash OR the gamemaster
hash — both are per-column stamps in the `.json` sidecar (v6 engine, v7
gamemaster). A stale stamp is a safe miss (re-simmed, never served), so
correctness is always protected. But `put_column` overwrites a column **in
place**, so running a dive/sweep **with the cache on under a work-in-progress
engine overwrites the trusted columns** with WIP results — you lose the warm
backup (not correctness) for everything you re-ran.

So when you're iterating on engine code (`battle.py`, `_dp_jit.py`,
`moves.py`, `formchange.py`, `pokemon.py`), run dives with
**`--no-sweep-cache`**. Only bake with the cache on once the engine change is
trusted; then re-bake, or bless selectively with `scripts/migrate_cache.py`
(`--from-engine` for an engine fix, `--from-gamemaster --old-gamemaster-file`
for a gamemaster/balance patch). The v7 gamemaster hash is NARROWED to
`md5(pokemon + moves)`, so non-sim gamemaster churn (timestamp/cups/formats/
rankings) no longer invalidates the cache at all. GC keeps v7 dirs always
(gamemaster is per-column) and reclaims at column granularity, so cache work
never deletes your trusted columns. Full mechanics + the warm re-dive recipe:
DEVELOPER_NOTES "Sweep disk cache".

### Before a cold re-dive, check for a tractable migration first

An engine edit changes the engine hash, so **every** cached column goes stale
and the default consequence is a *cold* re-dive (re-sim everything — many
hours across the website chain). Before eating that, ask: **is this change's
touched set cleanly characterizable by a boolean predicate over stored column
metadata?** If yes and the proof is tractable, write + prove a predicate and
warm-serve the rest with `scripts/migrate_cache.py` (`--from-engine <old>
--predicate <name>`) instead of cold re-diving. The sidecars already store
both sides' movesets, shadow flags, species, IVs, level, and gamemaster hash,
so most localized fixes (shadow-only, self-debuff-move-only, form-change-only,
…) are expressible **without** a schema change — a new predicate is just one
boolean function plus its proof. Don't pre-build predicates speculatively
(you can't write one until you know the fix); add them on demand, gated by
this check.

Two soundness guards, or this will quietly serve stale scores:

- **The predicate must cover the ENTIRE engine delta since `from_engine`, not
  just the one fix you have in mind.** If two engine changes share one hash
  bump, a predicate for only one of them wrongly blesses columns the other
  touched. This is why migration pairs with *one localized fix per bump*.
- **Skip the migration when you're batching with a broad fix that forces cold
  anyway.** A boundary-scattered change with no clean predicate (e.g. the
  float32 damage-constant fix) makes the whole batched delta unmigrate-able,
  so a co-batched localized fix just rides the cold re-dive for free.

Predicates are one-shot: each is pinned to a specific `--from-engine` hash,
never re-run after its migration, and doesn't interact with the others — so
there's no growing ruleset to maintain (delete or keep them as history).

**Gamemaster changes (v7) are migrate-able too, and without a hand-proven
predicate.** A gamemaster edit changes only the per-column gamemaster stamp
(v7), and the affected set is COMPUTED from the actual pokemon/moves delta by
`migrate_cache.py --from-gamemaster <stamp> --old-gamemaster-file <old blob>`
— no per-change boolean to write. A column is re-simmed iff a gamemaster entry
the battle reads for it (base species entry, transitively-expanded form-change
alt forms, or a move it uses) changed or was removed; a purely-additive delta
(e.g. "a new species was added") blesses everything. Keep the OLD
gamemaster.json blob around (pull it from the pvpoke git history) so the delta
can be computed. The narrowed `md5(pokemon + moves)` hash means non-sim churn
(timestamp/cups/formats/rankings) never invalidates in the first place.

## Pre-dive assessment: scope it as a {layer} x {lens} grid

**Before any cold re-dive, run the pre-dive checklist in
`docs/predive_checklist.md`** (it carries a ready-to-paste prompt). The cold
bake ties up the machine for hours; an engine/operational bug found *after* it
starts costs a *second* multi-hour bake, so this is a gate, not a courtesy.

The DRY principle (why the checklist exists):

> Scope the assessment as a **{system-layer} x {failure-lens} grid**, each lens
> carrying its own near-mechanical trigger (a git/grep/dry-run command) — NOT as
> a walk of the files you happen to read. The costly bugs hide in the cells no
> one's eyes land on: the layer that *runs* rather than renders (orchestration,
> cache), and the lens that asks *"does it survive / does it act?"* rather than
> *"is the number right?"* (resource/concurrency, affordance, change-propagation,
> input-freshness).

This was learned the hard way (2026-06-27): a thorough but *location*-oriented
assessment ("look at the engine / the artifacts") missed an ML-oversubscription
bug (orchestration layer) and a dead `(+N more)` UI affordance (rendered layer)
because no probe was positioned in those grid cells. Two lenses are now baked
into code as guards that can't silently regress: `run_iv_guides.py`'s
concurrency preflight and `verify_overnight.py`'s ML-completeness check. See the
checklist for the full grid, triggers, and the remaining TODO hardening.

## Key design decisions
- Core `gopvpsim/` library is pure Python (keeps mobile option open).
  Deep dive scripts (`scripts/`) may use numba/Cython/C extensions for speed.
- Data sourced from PvPoke's open-source JSON (github.com/pvpoke/pvpoke)
- Battle policies are pluggable — shield decisions, bait decisions, and
  charge move timing are separate from the core simulation loop
- Damage formula: floor(0.5 * 1.3 * Power * Atk/Def * Effectiveness * STAB) + 1
  (the 1.3 is PvPoke's global PvP bonus multiplier; chargeMultiplier=1 in simulation)
- Validate all stat calculations against PvPoke before writing battle logic

## Charge move timing
Always finish current fast move before throwing a charge move (don't waste turns).
Charge move timing policy is pluggable.

## Baiting
Start with fixed heuristic (throw cheap move first). Later: EV-based baiting
parameterized by opponent shield probability.

## Shielding
Pluggable policy. Simulate all three shield scenarios (0-0, 1-1, 2-2).

## CLI scripts
- `scripts/battle.py` — simulate a 1v1 matchup across all 9 shield scenarios
  Flags: `--stats`, `--show-damage`, `--trace-dp`, `--trace-shields`, `--debug`, `--pvpoke-scores`
- `scripts/breakpoints.py` — show breakpoints/bulkpoints for a given attacker/move/defender

## Running Python
This project requires Python **3.13+** (`pyproject.toml` `requires-python =
">=3.13"`). The environment is **uv-managed** (switched from pyenv
2026-06-15): `uv venv` created `.venv/` (Python 3.13.x), and `.envrc`
auto-activates `.venv/bin` via **direnv** when you enter the directory.
`uv.lock` is committed for reproducibility.

**How bare `python` resolves depends on the shell:**

- **Interactive terminal (Michael's shell, Emacs/eglot):** direnv is
  hooked in, so `.venv/bin` is on PATH and bare `python` is correct.
  **Always invoke `python`, never `python3`** — `python3` resolves to
  the macOS-default `/usr/bin/python3` (3.9.6) and fails on stdlib
  imports like `tomllib`.
- **Claude Code's Bash tool (non-interactive shell):** direnv is **NOT**
  loaded, so bare `python` is *not found*. Claude must invoke project
  Python one of these ways — prefer the first:
  - `direnv exec . <cmd>` — loads `.envrc`, puts `.venv/bin` on PATH,
    so the command's internal bare-`python`/`#!/usr/bin/env python`
    calls all resolve. **This is how to launch scripts and chains**
    (e.g. `direnv exec . scripts/overnight_redive.sh`).
  - `.venv/bin/python …` — direct interpreter, fine for one-off
    `-c` checks.
  - `uv run python …` — resolves the project env without direnv.

Script shebangs all use `#!/usr/bin/env python`, which lands on
`.venv/bin/python` whenever the venv is on PATH (no per-script edits
were needed for the uv switch).

**Install / fresh-machine setup:** `uv venv` → `uv pip install -e
".[dev,perf]"` → `direnv allow`. Runtime deps are declared in
`pyproject.toml` (currently `certifi`, `markdown`, `numpy`); `[dev]`
adds `pytest`; `[perf]` adds `numba`. **Do not skip `[perf]`:**
`_dp_jit.py` falls back to a pure-Python inner loop without numba, and
deep dives run several × slower (the 2026-06-15 uv switch initially
missed `[perf]`, which is the kind of regression to watch for).

## Testing
- `python -m pytest tests/test_battle.py -q` — run all battle tests (99/102 passing)
- Tests verify scores against PvPoke ground truth from pvpoke.com/battle/
- **Default movesets** — when a test or sim needs "the default moveset" for a
  species in a given league, ALWAYS call `gopvpsim.data.get_default_moveset(
  species, league, shadow=False)` which reads PvPoke's rankings file. Never
  guess from the gamemaster's `fastMoves`/`chargedMoves` lists — those are
  the legal-move *pool* (everything the species can learn), not PvPoke's
  meta recommendation. Guessing from the pool silently produces off-meta
  movesets that look plausible but don't match PvPoke's UI defaults, which
  turns oracle tests against reference writeups into noise. (Learned the
  hard way 2026-04-12 on the Corviknight vs Shadow Sableye oracle test.)

## Documentation
- `docs/concepts.md` — vocabulary used in deep-dive HTML outputs and threshold files
  (spread, anchor, slayer category, breakpoint, bulkpoint, CMP). Read this first.
- `docs/threshold_schema.md` — TOML schema for `thresholds/*.toml` files. Assumes
  familiarity with `concepts.md`.
- `DEVELOPER_NOTES.md` — verification status, PvPoke comparison, bugs found.
- `docs/validations/` — point-in-time experiment writeups.

## Debugging conventions (deep-dive scripts)

`scripts/deep_dive.py` and `scripts/deep_dive_slayer.py` emit progress
through the structured logger in `scripts/deep_dive_logging.py`
(see `docs/structured_logger_design.md` and DEVELOPER_NOTES "Log file
layout"). Do **not** introduce new `print()` calls that end up in a
commit — they bypass the log file, they don't honor `--quiet`/`--verbose`,
and they buffer badly when emitted from a multiprocessing worker.

`print()` is fine for live iteration inside a session. To keep it from
sneaking into a commit, prefix every ad-hoc debug print with the literal
sigil `XXX:` — e.g. `print(f"XXX: got {result}")`. The rule:

- **During a session:** use `print("XXX: ...")` freely wherever it helps.
- **Before committing:** grep for `XXX:` in touched files. For each hit,
  either delete it or convert to `logger.debug(...)` (gated by
  `--verbose`) if the signal deserves to live. Commit should contain
  zero `XXX:` markers.
- **For worker processes:** never commit bare `print()` from a
  multiprocessing worker. Always route through `logger.*()` so the
  record lands in the file with the rest.

Permanent progress messages use `logger.info(...)`, warnings use
`logger.warning(...)`, final-output tables and the species banner use
`logger.result(...)` (plain formatter, no timestamp). DEBUG records only
reach the file handler when `--verbose` is passed.

## Markdown formatting
All `*.md` files in this project should be formatted by `scripts/format_md.py`,
which keeps them readable in a raw text editor (currently: pads pipe-table cells
so columns line up). A PostToolUse hook in `.claude/settings.json` runs it
automatically after Edit/Write/MultiEdit. To format manually: `python
scripts/format_md.py [FILE ...]` (no args = walk the whole repo). The script is
idempotent.

This formatter was promoted to a general dotfiles tool: the canonical copy now
lives at `~/coding/dotfiles/scripts/format_md.py` (symlinked to
`~/.local/bin/format-md.py`) and runs on *every* repo via a global Claude
`PostToolUse` hook in `~/.claude/settings.json`. This project keeps its **own**
vendored copy + project hook on purpose, so it stays self-contained and its
tests pass standalone — meaning `.md` edits here get formatted twice
(idempotent, harmless). The two copies are intentional duplicates: if you change
the formatter in either place, port the change to the other (the dotfiles copy
uses a `python3` shebang; otherwise they're identical).

## Ship-mode narrative policy
Files under `articles/` and `thresholds/` render into public-facing
CD articles and per-species deep dives. Their `[intro]`,
`[meta_role]`, and `[Species.*]` narrative blocks must not carry
Claude-drafted prose. When drafting for these blocks:

1. **Default to suggesting an auto-gen template** rather than writing
   prose directly. `scripts/auto_gen_narrative.py` exposes
   `render_intro` / `render_good_at` / `render_bad_at`; the renderer
   auto-fills empty fields at dive/article render time.
2. **If the block can't be auto-gen'd honestly** (teambuilding
   synergies, editorial catch-priority / XL / ETM judgment, meta
   speculation), say so and recommend leaving the block empty for
   the human. Do NOT fill it with Claude prose to make the section
   look complete.
3. **A human override always wins.** Non-empty TOML prose beats the
   auto-gen template; the renderer prefers authored content when
   present. That's the way to ship expert-authored narrative without
   fighting the templates.

The `.githooks/pre-commit` hook enforces this by rejecting any
commit that leaves `authored_by = "ai"` in a ship-tracked TOML. To
activate the hook, run once per clone:

    git config core.hooksPath .githooks

Exploration-mode is unchanged: session chat, `/tmp/` analysis,
`docs/` design notes, and plan files can carry Claude prose freely.
Only the path-gated ship-mode TOMLs are restricted.

See `docs/auto_gen_narrative_plan.md` for the full rollout
rationale.

## Out of scope for now
Adaptive/game-tree search (minimax). Web app UI.
