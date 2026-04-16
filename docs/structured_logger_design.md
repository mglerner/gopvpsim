# Structured logger for `scripts/deep_dive.py` — S1 design

**Status:** design only; planning output for S2 implementation.
**Owning plan:** `~/.claude/plans/post-s5-oinkologne-arc.md` S1 → S2.
**Motivation:** TODO.md "Diagnostics / observability" — stdout buffering
makes live `tail -f` unreliable, no per-run log file, no timestamps,
no severity levels, no way to distinguish "stalled" from "quiet."

---

## 1. Scope

### In scope
- `scripts/deep_dive.py` (86 `print(` calls)
- `scripts/deep_dive_slayer.py` (5 `print(` calls)

These are the two modules in the deep-dive pipeline that emit
status/progress text. S2 ports both.

### Out of scope
- `scripts/deep_dive_rendering.py` (0 prints — rendering helpers)
- `scripts/deep_dive_analysis.py` (0 prints — aggregation helpers)
- `scripts/deep_dive_narrative.py` (0 prints — renderer)
- `scripts/slayer_cache.py` (0 prints)
- `gopvpsim/` core library — no prints to port, and `battle.py` already
  imports `logging` for its own purposes; we don't touch it.
- Other `scripts/*.py` that print (analyze_deep_dive, augment_deep_dive,
  battle, breakpoints, etc.) — they don't participate in a deep-dive
  run. They can convert opportunistically later, per plan.

### Scale note
The plan's "~6100 lines" / "60+ print calls" estimates are stale.
`scripts/deep_dive.py` is 4149 lines today; 86+5 = **91 print sites**
to port.

---

## 2. Classification table

Severity taxonomy matches Python `logging` levels:

- **DEBUG** — aggregator internals, per-IV enumeration dumps. Off by
  default; `--verbose` routes to the log file.
- **INFO** — phase starts/ends, timings, pool sizes, config echo,
  progress counts. The default signal.
- **WARNING** — skipped / malformed inputs, failed file loads, anchor
  resolution failures. User needs to see these.
- **RESULT** — final ranking tables (Top-20) and written-file
  confirmations. Treated as `INFO` at the logger level but emitted
  through a no-prefix formatter so the tabular output stays aligned.

### `scripts/deep_dive.py` — 86 sites

| Line(s)                            | Phase                        | What                                       | Severity   |
| ---------------------------------- | ---------------------------- | ------------------------------------------ | ---------- |
| 131                                | opponent-pool load           | group entries not in gamemaster            | WARNING    |
| 541, 554, 563                      | moveset validation           | move not in current move pool              | WARNING    |
| 687                                | phase-1 screen               | "skipping screen phase" (≤1 moveset)       | INFO       |
| 690                                | phase-1 screen               | "Phase 1: Screening N movesets"            | INFO       |
| 716                                | phase-1 screen               | "Screened in Xs. Top movesets:"            | INFO       |
| 718                                | phase-1 screen               | per-moveset avg-score line                 | INFO       |
| 720, 721                           | phase-1 screen               | pruned count + blank                       | INFO       |
| 954                                | sim chunking                 | "progress: X/Y chunks"                     | INFO (*)   |
| 1035                               | rendering                    | "Downloading Plotly.js ..."                | INFO       |
| 1413                               | rendering                    | "HTML written to ..."                      | RESULT     |
| 1437                               | rendering                    | "no default moveset" warning               | WARNING    |
| 1668                               | analysis-section setup       | "Generating analysis sections..."          | INFO       |
| 1834                               | anchor-flip aggregator       | mode + debug line                          | DEBUG      |
| 1867                               | matchup-boundary analysis    | "Matchup boundaries: N found"              | INFO       |
| 1879                               | threshold derivation         | "Auto-derived N threshold tier(s)"         | INFO       |
| 3033                               | interactive rendering        | "Interactive HTML written to ..."          | RESULT     |
| 3325                               | CLI echo                     | "CLI: ..." args line                       | INFO       |
| 3327                               | CLI echo                     | IV floor                                   | INFO       |
| 3368, 3388, 3411, 3432             | TOML / overlay / anchor load | failure warnings                           | WARNING    |
| 3374, 3386, 3398, 3409, 3445       | TOML / anchor load           | successful-load echoes                     | INFO       |
| 3470                               | TOML load                    | spread/anchor counts                       | INFO       |
| 3473–3476                          | banner                       | `=`×60 species header                      | RESULT (†) |
| 3480                               | config                       | moveset-count summary                      | INFO       |
| 3505, 3509, 3523, 3527, 3545, 3548 | opponent pool                | pool-construction notices                  | INFO       |
| 3535, 3558, 3584                   | opponent pool                | skipped opponent warnings                  | WARNING    |
| 3589                               | opponent pool                | TOML anchor opponents added                | INFO       |
| 3594, 3595, 3598, 3599             | config echo                  | shields / opp-IVs / thresholds / blank     | INFO       |
| 3624                               | phase-2                      | "Phase 2 [M/N]: <label>"                   | INFO       |
| 3625                               | phase-2                      | "Simming 4096 IVs × N opponents"           | INFO       |
| 3638                               | phase-2                      | sim elapsed + rate                         | INFO       |
| 3645, 3647                         | phase-2                      | auto-discovered thresholds                 | INFO       |
| 3676, 3677, 3682, 3692, 3694, 3696 | mirror slayer                | per-threshold winner counts                | INFO       |
| 3702                               | slayer-iter                  | "Mirror slayer iteration ..."              | INFO       |
| 3744                               | slayer-iter                  | "Slayer iteration skipped: ..."            | WARNING    |
| 3758, 3760                         | slayer-iter                  | rounds / cache-stats                       | INFO       |
| 3769                               | slayer-iter                  | per-round pool size                        | INFO       |
| 3868                               | anchor resolution            | "Resolved N anchors"                       | INFO       |
| 3872                               | anchor resolution            | resolution failure                         | WARNING    |
| 3887                               | classification               | "Final survivors classified into ..."      | INFO       |
| 3894, 3905                         | classification               | per-category IV enumeration                | DEBUG      |
| 3923                               | classification               | "Threshold hits: ..."                      | INFO       |
| 3926, 3932, 3933, 3943, 3944       | ranking                      | Top-20 header + rows + blank               | RESULT     |
| 3976                               | interactive expand           | "auto-expanding to all 9 shield scenarios" | INFO       |
| 3986                               | interactive sweep            | "Interactive sweep [M/N] ..."              | INFO       |
| 3997                               | interactive sweep            | sim elapsed + rate                         | INFO       |
| 4017                               | interactive sweep            | "Running <moveset> ..."                    | INFO       |
| 4027                               | interactive sweep            | sim elapsed                                | INFO       |
| 4048                               | reference sweep              | "Reference sweep: <label>"                 | INFO       |
| 4061                               | reference sweep              | sim elapsed + rate                         | INFO       |
| 4088                               | split mode                   | "Split mode: emitting N files"             | INFO       |
| 4120                               | split mode                   | "only one moveset surviving"               | WARNING    |
| 4145                               | bookend                      | "Done."                                    | INFO       |

(*) `scripts/deep_dive.py:954` is the one the "Better slayer iteration
progress reporting" TODO calls out — it's currently the only progress
signal across long chunked sims. Timestamps alone will make it more
useful; see §5 opportunistic cleanup.

(†) The `=`×60 banner is visual rather than semantic. Emit through the
plain-formatter path so it lands unadorned on both stdout and file.

### `scripts/deep_dive_slayer.py` — 5 sites

| Line | Phase               | What                                     | Severity |
| ---- | ------------------- | ---------------------------------------- | -------- |
| 304  | slayer-iter round   | "Round N: M opponents ..."               | INFO     |
| 344  | slayer sim chunking | "sim progress: X/Y chunks"               | INFO     |
| 350  | slayer sim          | "sim done in Xs ..."                     | INFO     |
| 361  | slayer cache merge  | "cache merge: Xs" (already `flush=True`) | INFO     |
| 363  | slayer-iter round   | "Round N: M opponents, all cache hits"   | INFO     |

---

## 3. Format + layout design

### Library choice — stdlib `logging`

Default. No `structlog`, no JSON. Reasons:
- One-developer project; no log aggregator consuming output.
- Michael reads logs live (`tail -f`) and post-hoc. Human-readable wins.
- `logging.FileHandler` auto-flushes per record, which solves the
  stdout-buffering pain point from `project_unbuffered_dive_output.md`
  without any custom code.
- If a later use case demands JSON (e.g., a dashboard over cron'd
  overnight dives), the `Formatter` is swappable without re-porting
  call sites.

### Per-run log file — location and naming

**Location:** `userdata/logs/YYYY-MM/{run_id}.log` (gitignored;
persists across reboots; matches `userdata/dives/` convention in
`DEVELOPER_NOTES.md` §"Deep dive output file layout"). Monthly
subdirs so the live directory never grows past ~50-100 files and
bulk-delete of an old month is a one-liner
(`rm -rf userdata/logs/2025-04/`).

**File name format:**
`{YYYYMMDD}_{HHMMSS}_{species}_{league}[_shadow].log`

Example: `userdata/logs/2026-04/20260416_143052_oinkologne_great.log`

Sortable by timestamp; `ls` in a month subdir is self-explanatory;
shadow runs distinguishable. CLI override: `--log-file PATH`.

**Latest-run symlink:** the logger init also maintains
`userdata/logs/latest.log` as a symlink pointing at the current run's
log file. Canonical monitoring command becomes
`tail -f userdata/logs/latest.log`, no globbing needed. Create the
symlink atomically (write `latest.log.new` then `rename`) so a
concurrent `tail -f` never lands on a broken symlink mid-switch.

**Rotation:** none at the handler level. One file per run is the unit.

**Periodic cleanup:** new `scripts/clean_logs.py`, dry-run by default.
Flags:
- `--execute` — required to actually delete/move anything (safety gate).
- `--older-than Nd` — target anything older than N days (mtime-based,
  not filename-based, so it's robust to any future format changes).
- `--archive` — instead of deleting, move matched content to
  `userdata/logs/archive/YYYY-MM/` (cold storage; also gitignored).
- `--keep-last N` — alternative policy: keep the N most recent logs
  across all months, purge/archive everything else.

No auto-purge inside `deep_dive.py`. Explicit beats implicit;
silent deletions on every dive start would surprise.

### Stdout vs log file routing

| Level   | stdout                           | log file            |
| ------- | -------------------------------- | ------------------- |
| DEBUG   | suppressed                       | only if `--verbose` |
| INFO    | default-on; `--quiet` suppresses | always              |
| WARNING | always                           | always              |
| RESULT  | always (plain formatter)         | always              |

Two handlers on the root deep-dive logger:
- `StreamHandler(sys.stdout)` — level filter per `--quiet`/default/
  `--verbose`; human-readable formatter.
- `FileHandler(log_path)` — level filter per `--verbose` (DEBUG) vs
  default (INFO); full-detail formatter.

### Formatters

**Stdout** — short timestamp, no level prefix for INFO, one-line
WARNING prefix. Current output mostly reads fine with a time prefix
bolted on; no need for level-per-line noise.

```
datefmt = "%H:%M:%S"
fmt     = "[%(asctime)s] %(message)s"                       # INFO
fmt     = "[%(asctime)s] WARNING: %(message)s"              # WARNING
fmt     = "%(message)s"                                     # RESULT / banner
```

Route RESULT / banner records through a separate handler whose
formatter is `%(message)s` (no timestamp) so the Top-20 table and the
`====` banner render exactly as today. Simplest implementation: a
custom `logging.Filter` that splits on a marker attribute (`extra={"plain": True}`)
and routes to a second StreamHandler with the plain formatter.
Decision deferred to S2 — if the split-handler dance gets noisy, the
Top-20 table can stay as a direct `print()` with an inline comment
explaining why.

**Log file** — full timestamps, level, logger name. Machine-grep'able.

```
datefmt = "%Y-%m-%d %H:%M:%S"
fmt     = "[%(asctime)s.%(msecs)03d] %(levelname)-7s %(name)s: %(message)s"
```

### Structured fields

Attach a run ID via logger name or `LoggerAdapter`. Initial pass: set
the root logger name to the run ID (`deep_dive.{run_id}`), so the
`%(name)s` token in the file formatter carries it. No `extra={}`
threaded through call sites — keeps the port mechanical.

### CLI surface

New flags on `scripts/deep_dive.py`:

- `--verbose` — DEBUG to log file; unchanged stdout.
- `--quiet` — suppress INFO on stdout; log file unchanged.
- `--log-file PATH` — override auto-generated log path. Passing
  `--log-file /dev/null` disables the file handler.
- `--log-dir DIR` — override default `userdata/logs/`. Useful for
  `run_website_dives.py` batch runs that want a single dated directory.

No changes to existing flags. `--quiet` and `--verbose` are not
mutually exclusive in the common sense — `--quiet --verbose` means
"stdout is quiet but the log file has everything." Matches logging
convention.

---

## 4. Scope-guard note for S2

### S2 touches
- `scripts/deep_dive.py` — port all 86 `print(` sites to `logger.*()`.
  Add logger-init helper (probably a new `deep_dive_logging.py` module
  since `scripts/` doesn't have a shared utility file; or inline at the
  top of `deep_dive.py`, which is fine too — decision in S2). Logger
  init also creates the monthly subdir if missing and refreshes the
  `userdata/logs/latest.log` symlink.
- `scripts/deep_dive_slayer.py` — port all 5 sites. Re-use the same
  logger-init from `deep_dive.py`; worker processes need a
  per-process logger re-init (multiprocessing caveat — workers don't
  inherit handlers from parent; S2 needs to pass the log path to
  worker init and re-open a FileHandler per worker, or have workers
  log to stdout and let the parent's handler multiplex).
- `scripts/clean_logs.py` — new small script (likely <100 lines).
  Dry-run default; `--execute` required. See §3 "Periodic cleanup"
  for flag list. Can be cron'd if you want set-and-forget.
- `DEVELOPER_NOTES.md` — add a "Log file layout" subsection parallel
  to the existing "Deep dive output file layout" section. Content:
  where logs live (`userdata/logs/YYYY-MM/`), the `latest.log`
  symlink convention, how to tail live runs, and a short
  `clean_logs.py` usage example (dry-run first, `--execute` to
  actually delete). This is the "how it works once shipped"
  counterpart to this S1 doc's "why it's shaped this way" focus —
  S1 stays as the design record; DEVELOPER_NOTES captures the
  steady-state reference material future sessions will read.

### S2 does NOT touch
- Core library `gopvpsim/` — out of scope.
- Other scripts (`analyze_deep_dive.py`, `augment_deep_dive.py`,
  `battle.py`, `breakpoints.py`, etc.) — they don't participate in
  a deep-dive run. Opportunistic later.
- `scripts/deep_dive_rendering.py`, `deep_dive_analysis.py`,
  `deep_dive_narrative.py`, `slayer_cache.py` — 0 print calls each;
  nothing to port.

### Multiprocessing caveat (flagged for S2)

`deep_dive.py` uses `multiprocessing.Pool` in several spots
(screening, sweep, slayer iteration — search `pool.imap_unordered`
and `pool.map`). Worker processes inherit the logger *name* but not
its *handlers* on macOS with `spawn` start method. S2 must either:

- (a) Re-initialise the logger inside each worker's init fn, pointing
  at the same log path (`FileHandler` append mode is safe for
  concurrent writes on one file; kernel-level line buffering is
  adequate for short log records).
- (b) Have workers `print()` to stdout and let a single collector log
  in the parent — works for progress lines but loses per-worker
  context.

Recommendation for S2: option (a). Pass `log_path` through
`pool_init_args` next to the existing worker initialiser (whatever it
is — S2 verifies). `multiprocessing-logging` exists as a third-party
helper but adds a dep for limited gain.

### Opportunistic side-cleanup — two adjacent TODOs

Per the plan, S2 may fold these in "only if the core logger port
finishes comfortably."

**Natural to fold into S2:**
- **"Better slayer iteration progress reporting"** (TODO.md
  Performance). The progress prints at `deep_dive.py:954` and
  `deep_dive_slayer.py:344` fire only on chunk completion. Once
  timestamps are attached via the logger, the `tail -f` gaps become
  *visible* (you can see "no new line for 30 min" at a glance), which
  is often enough — the user's 2026-04-07 chunking commit 8498ec4
  already dropped the gap from 85 min to ~10 min per chunk. Don't
  add new progress prints in S2; just gain "the logger makes the
  existing ones useful" for free and close the TODO.

**NOT natural to fold into S2:**
- **"Incremental slayer cache flush"** (TODO.md Performance). Lives in
  `scripts/slayer_cache.py`, which has zero prints. It's a durability
  fix (crash-mid-iteration loses all sims in the cache), not an
  observability fix. Different motivation, different file, different
  code path. If S2 has genuine time left AND Michael prefers folding
  it in, keep it as a **separate commit** from the logger port so the
  two concerns don't braid in the diff. Default recommendation: defer
  to its own dedicated session or mini-task, not S2.

---

## 5. Validation gate for S2

Per plan S2 "Done when": a real Oinkologne-sized dive runs, writes a
well-formed per-run log file, and `tail -f` on that file shows smooth
timestamped progress without buffering stalls.

Concrete S2 smoke test (small, per `feedback_small_dives_first.md`):

```
python scripts/deep_dive.py oinkologne --league great --opponents 10 \
    --top-movesets 1 --interactive &
tail -f userdata/logs/*oinkologne*.log
```

Pass criteria:
1. A log file exists at `userdata/logs/{run_id}.log` during the run.
2. `tail -f` shows each progress line within ~1 second of emission
   (no minutes-long buffering stalls).
3. Every existing stdout message today appears on stdout with a
   timestamp prefix and the same wording (WARNINGs now prefixed with
   `WARNING:`).
4. `--verbose` adds aggregator DEBUG lines (line 1834, per-category
   IV enumeration at 3894–3905) to the log file only.
5. `--quiet` suppresses INFO on stdout; WARNINGs still visible;
   log file unchanged.

---

## 6. What S1 explicitly deferred to S2

- **Split-handler decision for RESULT / banner rendering** — whether
  the Top-20 table routes through a separate no-timestamp handler or
  stays as `print()`. Either is defensible; S2 picks based on how
  ugly the filter-based routing looks in practice.
- **Per-process logger init strategy** — option (a) vs (b) above.
  Flagged; S2 implements.
- **Logger-init placement** — new `deep_dive_logging.py` helper vs
  inline at the top of `deep_dive.py`. Small call either way.

---

## 7. Resolved questions

**Log file default location (2026-04-16):** `userdata/logs/` with
monthly subdirs (`YYYY-MM/`). Confirmed by Michael. `--log-dir`
overrides if you want to point a specific run elsewhere.

**Periodic cleanup (2026-04-16):** explicit script
(`scripts/clean_logs.py`), dry-run by default. No auto-purge inside
`deep_dive.py`. Rationale: silent deletions are surprising; explicit
`--execute` gate means you only delete when you mean to. See §3
"Periodic cleanup" for the flag list.
