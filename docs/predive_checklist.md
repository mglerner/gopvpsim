# Pre-dive assessment checklist

Run this before any **cold re-dive** (`scripts/overnight_redive.sh`). A cold
bake ties up the machine for hours; any engine/operational bug found *after* it
starts costs a *second* multi-hour bake. The pre-dive window is the
high-leverage moment to catch problems -- treat it as a gate, not a courtesy.

## The DRY principle

> Scope a pre-dive assessment as a **{system-layer} x {failure-lens} grid**,
> where each lens carries its own **near-mechanical trigger** (a git / grep /
> dry-run command) -- NOT as a walk of the artifacts you happen to read. The
> costly bugs hide in the cells no one's eyes land on: the layer that *runs*
> rather than renders, and the lens that asks *"does it survive / does it
> act?"* rather than *"is the number right?"*

That is the whole point. A location walk ("look at the engine, the artifacts")
re-derives the worry list from memory each time and misses whatever you forgot.
A lens grid is reusable: you apply a fixed set of lenses, each with a command
that *finds* the worry for you.

### Provenance (why this exists)

On 2026-06-27 a thorough, adversarial pre-dive assessment still missed two real
bugs because the prompt was *location*-oriented instead of *lens*-oriented:

- **ML oversubscription** (L3 orchestration x change-propagation lens): the
  cache-rework made one ML guide saturate all cores, but `overnight_redive.sh`
  still launched N concurrent guides. Not an engine-correctness bug -- it only
  manifests at *run* time as CPU thrash / OOM-killed (silently incomplete) guides.
- **Dead `(+N more)` affordance** (L5 rendered-UI x affordance lens): the text
  looked clickable but did nothing. The *data* was correct, so any numbers-match
  audit sailed straight past it.

Both live in grid cells the location walk never visited. Running the lens grid
afterward (this doc) found them plus a stale-moveset data bug and two
silent-incompleteness holes that would have shipped wrong/partial in the bake.

## System layers

| id  | layer                                | where                                                                                                  |
| --- | ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| L1  | engine / math correctness            | `src/gopvpsim/{battle,_dp_jit,moves,formchange,pokemon}.py` (the engine-hash set)                      |
| L2  | cache / invalidation                 | `scripts/{sweep_cache,slayer_cache,migrate_cache,gc_cache}.py`                                         |
| L3  | orchestration / pipeline             | `overnight_redive.sh`, `run_iv_guides.py`, `run_website_dives.py` -- the things that consume the hours |
| L4  | data / input (gamemaster)            | `gamemaster.json`, `opponent_pools/*.txt`, the `DIVES` list                                            |
| L5  | rendered output (view + interaction) | `deep_dive_rendering.py`, `deep_dive_card.py` -> `userdata/website/*/index.html`                       |
| L6  | docs / process / invariants          | `TODO.md`, `DEVELOPER_NOTES.md`, `CLAUDE.md`                                                           |

The original prompt named only L1 and (weakly) L5. L2/L3/L4 were never pointed
at. Bias fresh-eyes agents toward the under-covered cells (L3-resource,
L5-affordance, change-propagation), not just the engine math.

## Failure lenses (apply each with its trigger)

1. **Value / numerical correctness** (L1). Does the engine compute the right
   damage / breakpoint / score?
   - trigger: `python -m pytest tests/test_battle.py -q`; for an engine edit,
     spot-check `scripts/battle.py <focal> <opp> --pvpoke-scores`. An
     *unexplained* fixture flip is the signal (divergence-from-PvPoke alone is
     not a bug -- see CLAUDE.md gate).

2. **Change-propagation / blast-radius** (cross-cutting -- L1+L2+L3). For every
   change since the last bake, list the contracts it altered -- functional AND
   non-functional (CPU / parallelism / memory / process-count / file-layout) --
   then verify EVERY downstream consumer was updated. Incomplete-refactor bugs
   hide in the un-updated consumer, never in the changed file. (This is the ML
   miss.)
   - trigger: `git log --oneline <last-dive-sha>..HEAD -- scripts/ src/gopvpsim/`
     (seed `<last-dive-sha>` from the latest DEVELOPER_NOTES re-dive entry). For
     each touched module, `grep -rn '<symbol>' scripts/ src/gopvpsim/ *.sh` and
     ask of each caller: "does the new behavior -- including how many
     processes / cores / how much RAM it now uses -- still match what this caller
     assumes?"

3. **Resource / concurrency viability** (L3). Will the producer survive a
   multi-hour unattended run -- no oversubscription, OOM-kill, deadlock, or
   silently-incomplete output? Orthogonal to correctness.
   - trigger: `grep -rn 'Pool(\|ThreadPoolExecutor\|cpu_count\|--jobs\|--reserve\|--reserve-cpus' scripts/`;
     for each launcher reconcile `(concurrent jobs) x (workers per job)` against
     physical cores and flag any product > cores. Then dry-run a small slice
     **with >=2 concurrent jobs** (the oversubscription only shows with >=2)
     while watching `top -l 0 -o cpu`, and confirm the emitted count == expected
     count (no silent drop).

4. **Affordance / interaction contract** (L5). Every signifier of interactivity
   must map to a real behavior, and every element that should act must signal
   it. A dead/false affordance renders perfectly and passes any numbers-match
   pass. (This is the `(+N more)` miss.) Both directions:
   looks-interactive-but-isn't, and looks-static-but-should-act.
   - trigger: render a representative page (e.g.
     `userdata/website/kingdra-great-league/index.html`) AND grep:
     `grep -onE 'more\)|show more|expand|toggle|class="[^"]*(toggle|cover|expand|sortable)[^"]*"|cursor:pointer|data-sort' index.html`.
     For each interactive-looking hit confirm a real backing control exists
     (`<input>`/`<label for>`/`href`/handler). Also
     `grep -oE 'id="[^"]*"' index.html | sort | uniq -d` for duplicate anchors
     that break deep-link nav. Click one to confirm.

5. **Input-freshness / diff validation** (L4). Before an expensive run consumes a
   refreshed input, diff it against last-known-good and sanity-check the delta. A
   wrong gamemaster silently poisons every downstream hour.
   - trigger: snapshot then `diff <(jq -S . /tmp/gm.prev) <(jq -S . <gamemaster>)`;
     for any dive-set species whose moves changed, confirm against `eliteMoves` +
     the pvpoke git log per the CLAUDE.md CD-prep rule (don't infer a pending CD
     move from a pool absence). Also: do the hardcoded `reference` movesets in
     `run_website_dives.py` still match `get_default_moveset(...)`? (This is the
     Oinkologne stale-TACKLE miss.)

6. **Cache soundness / migration-vs-cold** (L2). After an engine edit, confirm
   `engine_hash()` actually changed (so stale columns are safe misses), and check
   whether the touched set is a clean boolean predicate over column metadata -- if
   so, a migration warm-serves instead of a cold bake.
   - trigger: `python -c "from scripts.sweep_cache import engine_hash; print(engine_hash())"`
     before vs after (must differ). Then apply the CLAUDE.md migration check;
     verify any predicate covers the ENTIRE engine delta since `from_engine`.

7. **Known-issue / backlog triage** (L6). What have we already flagged that this
   dive should resolve or must not regress?
   - trigger: read `TODO.md` + `DEVELOPER_NOTES.md` top-to-bottom;
     `grep -rn 'XXX:\|TODO\|FIXME\|xfail' scripts/ src/gopvpsim/ tests/`; confirm
     each open item is fixed-in-batch or consciously deferred (not silently
     shipped).

## The reusable prompt

Paste this (or point an agent fleet at it) before a cold re-dive. It is
lens-oriented and would have caught both 2026-06-27 misses:

> We're about to start a cold re-dive that ties up this machine for hours, and
> any engine/operational bug found after it starts costs a second multi-hour
> bake. Do NOT scope this by "the files I personally read." Instead, run the
> pre-dive assessment as a {layer} x {lens} grid and report findings
> cell-by-cell. Layers: (L1) engine/math, (L2) cache, (L3) orchestration/
> pipeline, (L4) data/gamemaster, (L5) rendered HTML+UI, (L6) docs/process.
> Apply each lens using its mechanical trigger -- do not rely on remembering the
> specific worry:
>
> 1. Value correctness (L1): `pytest tests/test_battle.py -q`; investigate any fixture flip.
> 2. Change-propagation (L1+L2+L3): `git log --oneline <last-dive-sha>..HEAD -- scripts/ src/gopvpsim/`; for each changed module, grep every caller / orchestration script and confirm it honors the NEW invariants -- explicitly including non-functional ones (cores / processes / RAM).
> 3. Resource/concurrency viability (L3): grep `Pool(|ThreadPoolExecutor|cpu_count|--jobs|--reserve`; reconcile (jobs) x (workers/job) vs physical cores and flag any product > cores; dry-run a slice with >=2 concurrent jobs while watching CPU/RAM; confirm emitted count == expected count.
> 4. Affordance contract (L5): render a representative page; every element that LOOKS interactive ('+N more', show/less, toggles, sortable headers, link-styled text) must have a real backing control; `grep id= | sort | uniq -d` for dup anchors. Numbers being right is not enough -- exercise the controls.
> 5. Input freshness (L4): jq-diff the gamemaster vs prior; check moveset deltas (and the hardcoded `reference` pins) against eliteMoves + the pvpoke git log per the CD-prep rule.
> 6. Cache soundness (L2): confirm `engine_hash()` changed; decide migration-predicate vs cold per the CLAUDE.md check.
> 7. Known-issue triage (L6): read TODO.md + DEVELOPER_NOTES.md; grep XXX:/TODO/FIXME.
>
> For each lens ask not only "are results correct?" but "will the hours-long
> unattended run finish complete, on a survivable footprint, with every shipped
> artifact behaving as it signals?" Lean on adversarial/fresh-eyes agents, but
> point them at the empty grid cells (L3-resource, L5-affordance,
> change-propagation) -- not just the engine math.

## Hardenings (turn lenses into guards that cannot silently regress)

A lens you have to *remember to apply* will eventually be skipped. Where cheap,
convert it into a code-level guard:

- **Concurrency preflight (DONE 2026-06-27).** `run_iv_guides.py` prints
  `jobs x per-guide-workers` and HARD-FAILS if that exceeds physical cores
  (`--allow-oversubscribe` to override). The resource lens, baked into code, so
  the ML-oversubscription bug cannot recur silently.
- **ML completeness gate (DONE 2026-06-27).** `verify_overnight.py` check [5]
  asserts every ML-pool species has a fresh `_iv_envelope_all9.json` and surfaces
  any `[WARN] ML IV guides` line -- the silent-incompleteness lens, baked into the
  morning gate. (The ML bake is best-effort WARN-not-FAIL by design, so neither
  the `[FAIL]` scan nor the `SUCCESS` status line catches a partial ML run.)
- **Structural affordance diff (TODO -- not yet built).** Replace the affordance
  grep's literal token list with: collect the text of every *real* interactive
  control (`label`/`a`/`button`/backed toggle) on a page, then flag any other
  text node that mimics one. Catches NEW dead-affordance shapes (e.g. the
  sortable-looking comparison-table headers with no sort JS) without pre-listing
  each fingerprint.

The red-team caution that produced these: the lenses above were authored *after*
the two misses, so they risk being hindsight-fitted (a grep curated to the exact
bug). The code-level guards are the antidote -- they hold regardless of who is
auditing or whether anyone remembers the lens.
