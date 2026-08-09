# Test-suite review -- 2026-08-09

> **Question (Michael):** "Is it what we want? Do we want more/less/
> different things? This whole codebase is mostly claude-automated (with
> obvious human input), so we need a solid (but not overdone/fragile)
> test system."
>
> **Method:** 1 inventory agent (per-file map, runtime, idiom census) +
> 5 independent lens reviewers (fragility, vacuity, blind spots,
> cost/hygiene, policy fit) + a 3-agent adversarial verify pass on every
> claim that anchors a recommendation, + orchestrator spot-checks. All
> heavyweight claims below were EXECUTED, not eyeballed: vacuity was
> proven by gutting production functions in-process, fragility by
> applying behavior-preserving edits and re-spelled antipatterns to a
> scratch tree, the cache hole by monkeypatching and re-hashing. Where
> reviewers contradicted each other, the contradiction was resolved by
> re-derivation and the loser is recorded in "Corrections" below.
> Baseline: 1776 tests at `281a40a` (1781+ with the 2026-08-09
> lanes), 115 files, 24,020 test LOC vs 52,590 source LOC.

## Verdict

**The suite is fundamentally the right shape for this codebase -- and
better than its reputation in three specific ways -- but it has three
structural problems, all fixable in roughly two sessions, none
requiring more total tests.**

What is right (and should be recognized as the house style, not
accident): the oracle layer (47 of 115 files pin against PvPoke ground
truth), the JS<->Python parity harnesses, render determinism
(byte-identical replay), 13 of 14 xfails carrying `strict=True` so an
XPASS-by-coincidence fails loudly, recorded-reverted-value fidelity
tests (`test_port_fidelity_68ad233.py` documents each fix's pre-fix
value inline), and genuine anti-vacuity discipline in 10 files. For a
codebase where most lines are model-written, this boundary-contract
layer is exactly the right investment -- the suite pins what the code
must DO at its edges (game math vs PvPoke, page vs replay, JS vs
Python) rather than how it is written.

The three structural problems:

1. **Nothing runs the suite mechanically.** `core.hooksPath` is unset
   and `.git/hooks/` is empty (the documented `git config
   core.hooksPath .githooks` was never run in this clone), there is no
   CI, and the ship-gate roster (`run_ship_gates.py`) checks links,
   dashes, and a doc sentinel -- never pytest. 1,781 tests protect the
   publish path only when a session remembers to run them. The
   discipline has held by convention (53 of 61 code commits since
   2026-08-01 shipped a test -- 87%, verified mechanically), but
   convention is the weakest link in an automated pipeline.
2. **A small set of tests is provably dead weight.** 13 tests across
   the three S8a numpy-vectorization files pass with the production
   function replaced by a type-correct do-nothing stub (their random
   fixtures never fire the selection gates, so oracle and
   implementation compare empty-to-empty in 100% of parametrized
   cases); the 33.9s permanently-xfailed gamemaster sweep -- 45% of
   suite wall time -- can never catch a regression by construction;
   and 72 parametrized turn-mechanics cells collapse to exactly 3
   distinct output signatures.
3. **The source-scan idiom is strong in its positive/derived form and
   silently broken in its negative form.** Measured on a scratch tree:
   5 strictly behavior-preserving edits (quote style, a space, an
   import split, a local rename, a comment) broke 4 tests in 3 files;
   meanwhile all 3 sampled "this antipattern must not come back"
   absence pins stayed green when the forbidden pattern was
   re-introduced with trivially different spelling. That is the exact
   wrong way round: churn on benign edits, silence on real
   regressions. 152 substring pins exist across 29 files; 72 are
   code-shaped (whitespace/rename-sensitive) and 19 are source-level
   absence pins (the silent class).

Plus one engine-adjacent correctness gap found by the review and
independently verified end-to-end: **`data.py:parse_types` is
damage-affecting but unhashed.** `battle.py:27` imports it at module
scope; its output feeds `calc_damage`'s type-effectiveness and STAB at
three damage sites; a code edit to it changes battle scores (measured:
3 of 4 sampled GL matchups moved, e.g. Skarmory vs Medicham 628 ->
295) while BOTH the engine hash and the v7/v8 gamemaster hash stay
unchanged -- so every cached sweep column would be wrongly served as
warm. Severity honestly stated: LOW probability (the function has
changed exactly once, in the commit that created it) x HIGH blast
radius (silent wrong scores, no self-heal -- unlike a stale stamp,
which is a safe miss). DEVELOPER_NOTES:384-388 already states the
design rule this violates, for constants; the function slipped
through.

**Do we want more/fewer tests?** Net roughly the same count, different
composition: ~-90 (dead/redundant/vacuous removed or replanted) and
~+40 (five blind-spot files + gate wiring + replacements), with the
default run dropping from ~94s to ~60s and an inner-loop tier at
~28s.

## Scorecard

| Dimension                             | Grade | One-line basis                                                                    |
| ------------------------------------- | ----- | --------------------------------------------------------------------------------- |
| Boundary contracts (oracle/parity)    | A     | 47 oracle files; strict xfails; recorded-reverted values; byte-identical replay   |
| Anti-vacuity discipline               | B+    | 10 files exemplary; 13 S8a tests + a few unguarded scans slipped through          |
| Fragility balance                     | C+    | positive/derived pins excellent; negative pins silently rotten; 72 code-shaped    |
| Coverage of what ships                | B     | pages well covered; JIT path, node-absent hole, ship-gate detectors, logging bare |
| Runtime/cost                          | B-    | 44s tier already exists unused; 45% of wall time is one dead xfail                |
| Mechanization                         | F     | no hook, no CI, gates never run pytest                                            |
| Policy legibility for future sessions | C     | discipline real but recoverable only by reading exemplary files; nothing codified |

## Confirmed findings

### F1. Mechanization gap (verified by orchestrator + policy lens)

`git config core.hooksPath` unset; `.git/hooks/` empty; no CI config
anywhere in the repo; `run_ship_gates.py` SHIP_GATES = links + dashes +
dev-counts. The renderer chains and `publish_website.sh` therefore
publish without any test execution. Note the pre-commit hook exists
and is documented (CLAUDE.md ship-mode section) -- it is simply not
activated in this clone, which also means the ship-mode
`authored_by="ai"` gate is not being enforced by git either.

### F2. Dead and vacuous tests (verified by gut-replication)

- `tests/test_probe_tier_cutoff_flips.py`: 5/5 tests pass with
  `probe_tier_cutoff_flips = lambda *a, **k: []`; 0/20 parametrized
  cases produce a non-empty oracle; the record-emission block
  (`deep_dive_analysis.py:1215-1223`) is never executed.
- `tests/test_find_losses_vs_general.py`: 4/4 pass with a `{}` stub
  (the `[]` stub fails on type -- vacuity confirmed with that
  refinement); 0/15 cases non-empty.
- `tests/test_aggregate_flips_by_anchor.py`: 4/5 pass gutted; only
  `test_debug_stats_populated` genuinely discriminates. 0/4 cases
  non-empty; both emission blocks never executed.
- Root cause, all three: `_make_inputs` draws scores
  `rng.randint(0,1000)` independent of the IV arrays, so win rates
  concentrate near 0.50 and the `>=0.75 AND <=0.25` selection
  conjunction never fires. The healthy sibling
  `tests/test_matchup_boundaries.py` couples scores to the swept stat
  (`win = ivDef >= stat_cut` + noise) and produces 317 oracle records;
  gutting its target fails 26/35 tests. The fix is a fixture replant,
  not new philosophy -- the repo already owns the correct pattern.
- `tests/test_pokemon.py:592` (`test_compute_default_ivs_matches_
  gamemaster_broadly`): permanently xfailed, non-strict, 33.9s = 45%
  of suite wall time, cannot fail. Measured today: 209/5208 = 4.01%
  mismatch. Replacement: a seeded n=200 sample with a two-sided band
  (`0.02 <= rate <= 0.06`, ~1.7s) as the default test, plus the full
  sweep as a non-xfailed `@pytest.mark.slow` banded assertion.
- `tests/test_new_turn_mechanics.py:~237`: 72 cells -> exactly 3
  distinct combined signatures (54/12/6 split; verified by
  re-execution). Keep 3-6 representative cells + the docstring.
- `tests/conftest.py`: two identical autouse TTL-pinning fixtures
  (`_pin_data_cache_ttl`, `_pin_gamemaster_cache`). Merge.

### F3. Pin fragility, both directions (verified on a scratch tree)

Measured: the 5-edit benign-refactor probe broke
`test_theme_key.py:28/:39`, `test_js_wire_contract.py:101/:102`, and
`test_ml_guide_progress.py:25`; the 3-antipattern re-introduction left
`test_verify_overnight_cup_glob.py`, `test_ship_surfaces.py`, and
`test_sidecar_primitives.py` green. Census: 152 substring pins / 29
files; 72 code-shaped; 37 absence pins of which 19 target source (the
silent-rot class; the other 18 target rendered HTML and are
legitimate). Historical churn cost so far is tiny (2 pin-repair
commits since June, both from upstream rankings drift) -- the cost is
latent, not incurred; the silent-rot side is the real defect.

Conversion targets, ranked (from the fragility lens, all verified
in-file): the 19 source absence pins (tolerant regex + positive
control, modeled on `test_gamemaster_lookup_sites.py:365-375`); ~8
"module X uses helper Y" import-text pins -> object identity
(`mc.scenario_label is rendering.scenario_label`, the idiom
`test_score_pack_round_trip.py:79-80` already uses); 3 "the bake emits
X" source pins -> assertions on the rendered `small_dive_html`
artifact; `test_ml_guide_progress.py:25`'s `"print(" not in src` ->
AST scan (it currently fires on a comment and misses `print (x)`);
whitespace-intolerant literals -> tolerant regexes.

KEEP untouched, named explicitly so a de-pinning pass cannot sweep
them up: the SHA-pinned region test (deliberate fragility, one-paste
repair, mechanically derived deps), the WARN producer/scanner contract
(derived, floored, anti-vacuous), the `>=`-floor + injection-probe
pattern in `test_dive_dom_ids.py` / `test_cmp_panel_css.py`, scanner
self-tests in `test_win_boundary.py`. **Do not reduce the number of
source scans overall** -- the two most recent scan additions each
closed a hole no behavioral test reached, and the win-boundary
constant drifted three times before its scans existed. The fix is
"derive, tolerate, floor", not "delete".

### F4. Blind spots that matter (verified; minimal tests designed)

1. **`_dp_jit.py` (525 LOC, the numba engine hot path): zero tests.**
   No JIT-vs-pure-Python equivalence pin, no forced-fallback test --
   in a project whose own CLAUDE.md records that a missing `[perf]`
   extra silently swaps implementations. Verified feasible and
   currently sound: `monkeypatch.setattr(battle, '_NEAR_KO_DP_JIT',
   None)` flips paths in-process; 2,133 real cells agree exactly in
   1.5s. The designed test (~6 matchups x 9 cells, tuple-equality on
   winner/scores/turns/hp/chargedLog, counting-shim anti-vacuity
   guard, skipif-no-numba) plus the overflow-sentinel case is ~40
   minutes of work and ~0.4s of runtime.
2. **Node-absent hole:** with node off PATH, 19 tests across 8 files
   skip and the suite exits 0 green -- 5,432 LOC of shipped JS
   silently uncovered on any machine without node. Fix: one loud
   env-gated node-presence check wired into the gate roster; keep the
   per-file skipifs.
3. **Ship gates are roster-tested, never behavior-tested** (2 of 3;
   verify_dev_counts got tests with `--update`). A dangling link or a
   unicode dash is the exact regression class the gates exist for, and
   nothing pins their detectors. Designed: positive+negative controls
   on hand-written HTML in tmp_path, no site tree needed.
4. **`deep_dive_logging.py`** (9 importers incl. 3 deep_dive_lib
   modules): a worker record silently dropping would fail nothing.
   Designed spawn-pool test measured working today (4/4 records land);
   needs a handler-snapshot fixture to avoid polluting the session
   logger.
5. **gobattlekit consumer surface:** 9 imported names across 5
   modules, zero pinned signatures. One `inspect.signature` pin file
   is cheap insurance given the cross-repo no-signature-change rule.

Explicitly LEFT OPEN (verified as fine): `cache_base.py` (the
"zero refs" was a matcher artifact -- 14 sweep-cache tests drive it
through real disk I/O), `patch_iv_guide_nav_width.py` (legacy-only,
self-reporting), `render_article.py` (dormant: zero valid TOML inputs
exist today), `rerender_dive_cards.py` (fails loud), and the ~14
one-off analysis scripts.

### F5. parse_types / engine-hash coverage hole (verified end-to-end)

Chain: `data.py:207-215` -> `battle.py:2049` (`BattlePokemon.
from_pokemon`) -> types consumed at `battle.py:2138-2139/2207-2208/
2388-2389` -> `moves.py:243-257` `calc_damage` (type effectiveness +
STAB). Also reaches form-change alt types (`formchange.py:212/:219`)
and the sweep worker (`deep_dive_lib/sweep.py:633/:660`). Neither
`engine_hash()` (literal 5-file tuple + signature file) nor
`gamemaster_hash` (JSON data only) nor the column key fields cover it.
The rest of battle.py's closure was checked and is clean --
`anchors.py`/`thresholds.py`/`user_collection.py` never load or are
key-covered; `data.py` is the sole hazard, and within it `parse_types`
the sole damage-affecting function (`get_default_moveset` re-keys, so
it is safe by construction). Also: the comment at `sweep_cache.py:
46-47` overclaims _ENGINE_FILES completeness and would discourage the
correct CACHE_VERSION bump.

Fix (next engine-hash bump window, alongside the queued comment-only
batch): move `parse_types` into a hashed module per the
DEVELOPER_NOTES:384-388 rule (or add `data.py` to _ENGINE_FILES --
cruder, more churn since data.py changes for non-sim reasons), plus an
`_ENGINE_FILES` self-check test that AST-walks battle.py's transitive
closure and asserts coverage modulo a named allowlist -- converting
the prose invariant into a guard.

### Corrections to earlier in-flight claims (kept per the
never-present-known-wrong rule)

- The inventory's "none of the 14 xfails are strict" was WRONG: 13 of
  14 ARE `strict=True` at HEAD (4 marker constants in test_battle.py);
  only `test_pokemon.py:592` is non-strict. The suite deserves credit
  here, not a finding.
- The inventory's "small_dive_html shared by 47 tests" was wrong: 11
  tests actually consume it (7 direct + 4 via `dive_id_rows`).
- The inventory's "cache_base.py zero test references" was a matcher
  artifact (see F4).
- The policy lens's "6 of 7 recent code commits shipped a test" was
  REFUTED as stated: the mechanically-defined population is 61 code
  commits since 2026-08-01, 53 with tests (87%), 8 without.
- The policy lens's "~40% of files assert on text" framing: file-level
  it is 46/115, but assertion-level it is ~96 of 2,560 asserts (3.8%)
  -- the structural-guard share is much smaller than the file count
  suggests.
- Suite wall time varies 76-94s by machine load; use ratios.

## Recommended plan (phased; nothing implemented without sign-off)

**Phase 1 -- mechanize (S, highest leverage per minute):**
`git config core.hooksPath .githooks` (and add it to the fresh-machine
setup steps); add a pytest step (`-m 'not slow'`, ~44s) to
`run_ship_gates.py` SHIP_GATES so every chain and publish inherits it;
add the loud node-presence gate. This turns the suite from a
convention into a mechanism, which is the entire ballgame for a
Claude-automated repo.

**Phase 2 -- fix the dead weight (M, one session):** replant the three
S8a fixtures (couple scores to the swept stat; verify by gut-test);
add `assert ref` non-emptiness lines to every oracle-parity
comparison; replace the 34s xfail with the sampled banded test +
slow-marked full sweep; shrink the 72-cell grid to its 3-6 distinct
signatures; merge the duplicate conftest fixtures; convert the 4
tracked-file `pytest.skip`s to hard asserts; add the two markers
(`render`, `local_artifacts`) and document the three tiers (~28s inner
loop / ~44s pre-push / ~60s gate). Do NOT set `addopts = -m 'not
slow'`.

**Phase 3 -- convert the fragile pins (M, one session):** the ranked
list in F3, plus one anti-vacuity floor for
`test_sidecar_primitives.py`. Include the six-line pin policy in
CLAUDE.md (draft below).

**Phase 4 -- close the blind spots (S each):** the five designed test
files in F4; the gobattlekit signature pin; the `_ENGINE_FILES`
self-check; `parse_types` relocation riding the next bump window with
the queued comment-only batch (one localized change per bump --
relocation is behavior-neutral, so the fully-blessing migration
predicate is trivially provable).

**Policy block for CLAUDE.md (draft -- adopt/edit with Michael):**

    ## Testing policy (adopted 2026-08; see docs/reviews/2026-08-09_test_suite_review.md)
    - Every behavior fix ships in the same commit as a test that FAILS
      without it; record the pre-fix value in the test (see
      test_port_fidelity_68ad233.py).
    - Pin contracts at boundaries (oracle scores, rendered artifacts,
      JS<->Py parity), not implementation shape.
    - Source-scan rules: prefer `is` identity over import-text; prefer
      the rendered artifact over the producing source; scan Python via
      ast/tokenize, JS via strip_js; absence pins need a tolerant regex
      PLUS a positive control; every scan needs a `>=` floor set below
      today's count or a scanner self-test; counts are floors, never ==.
    - Oracle-parity tests must assert the compared output is non-trivial
      ("both empty" is the default failure mode).
    - xfail is strict=True unless documented why not; permanent xfails
      are banned -- convert to a banded assertion on the measured rate.
    - New slow (>2s) tests get @pytest.mark.slow; blob-dependent tests
      get @pytest.mark.local_artifacts.
    - Do not add test-only dependencies (hypothesis, mutmut, xdist)
      without a decision recorded here.

**Explicit do-NOTs (so they are not re-litigated):** no
hypothesis/mutmut (the recorded-reverted-value idiom is the
proportionate substitute; measured cost-benefit in the cost lens); no
pytest-xdist (session fixtures duplicate per worker, the dive render
already saturates cores, a tmp-file race exists at `data.py:183`, and
the marker tier already buys the win); no wholesale de-pinning of the
scan idiom (F3's KEEP list).

## Provenance

Inventory: `scratchpad/testsuite_inventory.md` (576 lines). Lens
digests: `scratchpad/testsuite_lenses.txt`. Verify verdicts:
`scratchpad/testsuite_verify.txt` (every CONFIRMED above ran real
code; the two REFUTED lens claims are recorded in Corrections).
Scratch experiment code (gut plugins, line tracers, fragility probes)
under the session scratchpad; none of it touched the repo.
