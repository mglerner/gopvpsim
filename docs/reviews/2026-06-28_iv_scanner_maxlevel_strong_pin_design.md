# IV-scanner `maxLevel` single-source: strong-pin design + league-aware plan

Build-ready spec for a later attended session. READ-ONLY review: no
production code changed, no test committed. Source TODO: `TODO.md`
"Tests to add" -> "Guard for the IV-scanner `maxLevel` single-source".

VERIFIED facts (confirmed by reading the code this session) and ASSUMED
/ design proposals are separated below.

## TL;DR

- The strong pin should assert `data_obj['collection']['maxLevel']` from
  a rendered dive: `== 50.0` for a Great dive, `== 51.0` for a Master
  dive. That is the value the browser reads as `DATA.collection.maxLevel`.
- **A Poke Genie CSV is NOT required for this assertion.** The collection
  scanner support-data (including `maxLevel`) is built at render time and
  is independent of any user CSV (the CSV is pasted in-browser at
  runtime). The TODO's "render a tiny GL dive *with a collection* / Poke
  Genie CSV fixture" overstates the fixture need for *this* pin. A CSV +
  node would only be needed for an end-to-end behavior test (owned mons
  render at the right level), which is a strictly larger, separate test.
- The cleanest strong pin is enabled by a tiny **production refactor**
  (extract the collection-data dict builder into a pure helper), which
  turns a heavy full-render test into a fast unit test. Recommended.
- The shared-library league-unaware `51.0` defaults are a real latent
  trap, but the cross-repo coupling is **parallel duplication, not a live
  import** (verified) — which changes the coordination story from the
  TODO/CLAUDE.md framing.

## VERIFIED: current line numbers and the data path

The TODO/task SHAs and line numbers have drifted. Corrected:

| Reference in TODO/task         | Stale value       | VERIFIED current value                                 |
| ------------------------------ | ----------------- | ------------------------------------------------------ |
| Fix commit (IV-scanner)        | `725c184`         | `9f55e38` "dry: single-source the IV-scanner maxLevel" |
| owned_breakdown commit         | `786d437`         | `8fa4517` "dry: league-aware level ceiling"            |
| `_collection_data['maxLevel']` | deep_dive.py:4602 | **deep_dive.py:4667**                                  |

Data path (all VERIFIED this session):

- `scripts/deep_dive.py:4667` bakes
  `'maxLevel': LEAGUE_MAX_LEVEL.get(league, 51.0)` into the
  `_collection_data` dict.
- The dict is attached at `deep_dive.py:4688`:
  `data_obj['collection'] = _collection_data`.
- The whole `_collection_data` block is built **only** inside
  `if _collection_species_key in _pkidx:` (deep_dive.py:4595) — i.e.
  whenever the focal species exists in the pokemon index. It does **not**
  depend on a runtime CSV. So every rendered dive of an indexed species
  carries `data_obj['collection']['maxLevel']`.
- `scripts/deep_dive.py:5608` emits it to the page:
  `html += f'<script>var DATA = {json.dumps(data_obj)};\n'`. Therefore
  `DATA.collection.maxLevel === data_obj['collection']['maxLevel']`
  byte-for-byte; asserting the Python dict is equivalent to asserting the
  emitted JS and is strictly stronger than any rendered-table scrape.
- `src/gopvpsim/pokemon.py:66-71`:
  `LEAGUE_MAX_LEVEL = {little: 51.0, great: 50.0, ultra: 50.0, master: 51.0}`.
- In-page consumer: `scripts/deep_dive_engine.js:661`
  `var maxLevel = coll.maxLevel;` (and :664 best-buddy override uses
  `DATA.bestBuddy.altCap || coll.maxLevel`). The live path always feeds
  this value into `ivsToStatsAtCap` / `matchMons`, so the JS `: 51.0`
  defaults are never hit on the live path (they are latent).

### Why a table-only assertion is too weak (VERIFIED)

A scrape of the rendered owned-mons table would (a) require running node +
a CSV through the JS matcher, and (b) still pass if line 4667 regressed to
`51.0` *and* the CPM happened to land the displayed mon on the same level
under both caps (CP cap binds before L50). The TODO's "wouldn't catch line
4602 drifting" is correct: only an assertion on the emitted
`collection.maxLevel` scalar pins the single-source directly.

## Strong-pin design

Three implementation options, ranked. All assert the same target:
`collection.maxLevel == LEAGUE_MAX_LEVEL[league]`.

### Option 1 (RECOMMENDED): tiny production refactor + fast unit test

Extract the `_collection_data` dict construction (deep_dive.py:4656-4687)
into a module-level pure helper, e.g.:

```python
def build_collection_data(species, league, shadow, tier_info, best_buddy,
                          pkidx, ...):
    ...
    return _collection_data   # or None if species not in pkidx
```

Then `generate_interactive_html` calls it, and a unit test imports
`deep_dive` (the existing `importlib.util.spec_from_file_location`
pattern used by `tests/test_best_buddy_toggle.py:_spec`) and asserts:

```python
def test_collection_maxlevel_is_league_capped():
    for league, expected in [('great', 50.0), ('ultra', 50.0),
                             ('master', 51.0), ('little', 51.0)]:
        cd = deep_dive.build_collection_data(
            species='Azumarill', league=league, shadow=False,
            tier_info=[], best_buddy=None, pkidx=get_pokemon_index())
        assert cd['maxLevel'] == expected
```

Cost: ~milliseconds (one `compute_rank_lookup` over 4096 IVs per league,
already fast). No full render, no CSV, no node.

- PRO: fast, deterministic, directly pins line 4667; covers all four
  leagues so it also pins league-awareness (catches a re-hardcode to a
  constant *and* a wrong-league lookup).
- CON: requires a small production change (the extraction). This is the
  "one localized DRY/testability refactor" kind of change; it must be a
  separate, reviewed commit — out of scope for this READ-ONLY design.
- NOTE: the extraction is a behavior-preserving move of an existing block.
  Keep `tier_info` as a parameter (it is read at 4647-4652 only to build
  `thresholds`/`tierNames`; an empty list yields empty tiers, which is
  fine for the maxLevel assertion).

### Option 2: full-render integration test (no production change)

Render a real dive to a temp HTML, regex out `var DATA = ({...});`,
`json.loads`, assert `data['collection']['maxLevel']`.

```python
def test_rendered_dive_collection_maxlevel(tmp_path):
    out = tmp_path / 'dive.html'
    # run the actual deep_dive entrypoint for a 1-opponent, 1-moveset GL dive
    subprocess.run([...,'scripts/deep_dive.py','Azumarill','--league','great',
                    '--opponents','Medicham', '--out', str(out)], check=True)
    html = out.read_text()
    m = re.search(r'var DATA = (\{.*?\});\n', html, re.S)
    data = json.loads(m.group(1))
    assert data['collection']['maxLevel'] == 50.0
```

- PRO: exercises the true emit path (line 5608), no production change.
- CON: this is the "Heavy" path the TODO flagged. A real dive runs the
  sim (numba JIT warmup + DP across opponents/shields); even a minimal
  1v1 GL dive is seconds-to-minutes and pulls in the sweep cache, file
  I/O, plotly, narrative. Flaky/slow for a unit suite. The `var DATA`
  regex must be non-greedy and tolerant of the trailing newline; confirm
  there is exactly one `var DATA =` in the page (VERIFIED: single emit at
  5608).
- NOTE: calling `generate_interactive_html` directly with synthetic
  minimal `moveset_data` is NOT a reliable shortcut — the function does
  substantial downstream work (scatter traces, narrative, notable-IVs)
  that assumes well-formed `moveset_data`/`meta`; feeding stubs risks
  unrelated breakage. If you go the no-refactor route, drive the real
  entrypoint (subprocess), don't hand-build `moveset_data`.

### Option 3: end-to-end JS behavior test (largest; optional, separate)

Extend the existing equivalence harness `scripts/verify_js_parser.py` (or
a node-driven test) to feed a CSV through `matchMons` with
`maxLevel = DATA.collection.maxLevel` derived from the league, and assert
an owned mon's emitted level. This is the only variant that needs a Poke
Genie CSV and node. It is a superset of the pin and tests a different
thing (the JS matcher honoring the cap), so treat it as a *separate*
future item, not the strong pin.

**However**, while here, fix the harness's own league-blindness (VERIFIED
defect): `verify_js_parser.py:152` (`build_rank_lookup(..., max_level=51.0)`)
and `:302` (`payload['maxLevel'] = 51.0`) hardcode `51.0` with
`league='great'`. Because GL's canonical cap is 50.0, this harness can
**never** catch a league-awareness regression. Fix: derive
`max_level = LEAGUE_MAX_LEVEL.get(league, 51.0)` in both spots. (Small,
no cross-repo coordination — it's a gopvpsim-only test harness.)

### Recommendation

Ship **Option 1** as the strong pin (after the extraction refactor lands
as its own reviewed commit). Fold the **verify_js_parser 51.0 -> league**
fix in alongside (Option 3's harness hardening, without the full
node/CSV behavior assertion). Defer the full end-to-end JS behavior test.

## Fixture inventory (VERIFIED)

- A real Poke Genie export already exists at
  `tests/fixtures/poke_genie_export.csv` (~512 KB, maintainer's
  collection). Per MEMORY "PokeGenie collection public is OK" it is fine
  to keep. **The strong pin (Option 1/2) needs NONE of it.** If a future
  end-to-end test (Option 3) wants a *minimal* CSV, carve a handful of
  rows (one focal species + one pre-evo) from this file rather than
  hand-authoring the Poke Genie header — the header/column contract is
  exercised by `parse_csv_text` and is easy to get subtly wrong.
- Module-load pattern for importing `deep_dive` in a test is established:
  see `tests/test_best_buddy_toggle.py` (lines ~24-34) — reuse it
  verbatim so the shared `sys.modules['deep_dive']` object is consistent
  with `test_sweep_cache.py` / `test_energy_lead.py` (multiprocessing
  pickling depends on the single shared module object).

## League-aware single-source plan (shared library)

Scope (VERIFIED current line numbers in `src/gopvpsim/user_collection.py`):

- `:209` `ivs_to_stats_at_cap(..., max_level: float = 51.0, ...)`
- `:263` `compute_rank_lookup(..., max_level: float = 51.0, ...)`
- also `:298` `match_mons(..., max_level: float = 51.0, ...)`
- also `:417` `check_thresholds(..., max_level: float = 51.0, ...)`

NOT currently wrong on any shipped path: every deep_dive bake site
overrides `max_level` with `LEAGUE_MAX_LEVEL.get(league, 51.0)` (verified
at deep_dive.py:4615, 4635, 4667). The defaults are a league-unaware trap
a *future* caller could hit.

The JS twins (`scripts/deep_dive_user_collection.js`): `:275`
(`ivsToStatsAtCap`) and `:344` (`matchMons`) both do
`(opts.maxLevel != null) ? opts.maxLevel : 51.0`. Live in-page path passes
`coll.maxLevel` (engine.js:661), so these are latent. `matchMons` is
exported (js :467) but has no in-page call site that relies on the default
(engine.js mirrors the logic inline). Single-source these to the same
league-derived ceiling **only if/when matchMons is wired up directly** —
low priority.

### Option A (preferred): default `None` + derive from league

Mirror the `owned_breakdown.py` fix (`8fa4517`): change the signature
default to `None` and, inside each function that already receives
`league`, derive `_ceiling = LEAGUE_MAX_LEVEL.get(league, 51.0)` and set
`max_level = _ceiling if max_level is None else max_level`.

- Applies cleanly to `compute_rank_lookup` (`:263`, has `league`),
  `match_mons` (`:298`, has `league`), `check_thresholds` (`:417`, has
  `league`).
- `ivs_to_stats_at_cap` (`:209`) has **no `league` parameter** (it takes
  raw base stats + `max_cp`). It cannot derive a league ceiling on its
  own. For this one, either (a) leave the `51.0` default and rely on the
  always-passed override (status quo, lowest churn), or (b) require an
  explicit `max_level` (Option B) for this function only. Recommend (a):
  it is a leaf helper whose every caller already passes `max_level`;
  changing its default to `None` would push a "derive ceiling" decision
  into a function that lacks the league context to make it.

### Option B: require an explicit cap (no default)

Make `max_level` a required keyword (drop the `= 51.0`). Forces every
caller to be explicit; a missing arg becomes a `TypeError` at call time
rather than a silent wrong-league computation.

- PRO: no silent default can ever be league-wrong.
- CON: hard API break for any external caller; noisier. Given the verified
  coupling (below), the blast radius is gopvpsim-internal, so this is
  viable — but Option A is gentler and matches the precedent already set
  by `owned_breakdown.py`.

### Cross-repo coordination steps

**VERIFIED coupling reality (differs from TODO/CLAUDE.md framing):**

- gobattlekit does **not** import `gopvpsim.user_collection`. Grep over
  `gobattlekit/src` and `gobattlekit/tools` shows the only `gopvpsim`
  imports are in `tools/threshold_export/export_thresholds.py`
  (`breakpoints`, `data`, `moves`, `pokemon.iv_rank`, `thresholds`) —
  NOT `user_collection`.
- gobattlekit's runtime IV checker is a **vendored port**:
  `gobattlekit/src/gobattlekit/data/iv_checker.py` ("Ported from the
  PoGoIVChecker notebook"), with its own `check_thresholds`,
  `compute_rank_lookup`, `stats_at_cap`. It mentions
  `gopvpsim.user_collection.ivs_to_stats_at_cap` only in a docstring
  (`iv_checker.py:147`) as the algorithm it mirrors.
- That port **also hardcodes `max_level=51`** at its own call sites
  (`iv_checker.py:574, 694, 832, 1025`, `user_iv_checker.py:234`, and
  defaults at `iv_checker.py:141, 468`). So gobattlekit has the *same
  latent league-blindness*, independently.

Consequence: changing gopvpsim's `user_collection` signature **cannot
break gobattlekit at import time** (no import edge). The coupling is
"keep two parallel ports behaviorally in sync," not a live contract. The
TODO/CLAUDE.md "consumed by gobattlekit (shared user_collection)" wording
is imprecise and should be read as "duplicated-by," confirmed this
session.

Coordination steps for the attended session:

1. Re-confirm the no-import-edge with a fresh grep (the port could be
   re-wired to import gopvpsim later):
   `grep -rn "from gopvpsim.user_collection\|import gopvpsim" gobattlekit/src gobattlekit/tools`.
   If still no `user_collection` import: the gopvpsim change is internally
   safe and needs no gobattlekit code change to avoid breakage.
2. Apply Option A in `gopvpsim/user_collection.py` (`compute_rank_lookup`,
   `match_mons`, `check_thresholds`; leave `ivs_to_stats_at_cap`'s default
   as-is per A(a)). Run `python -m pytest` + `scripts/verify_js_parser.py`
   (after its 51.0->league fix) to confirm parity.
3. Separately (gobattlekit repo, its own commit/PR): make
   gobattlekit's `data/iv_checker.py` league-aware by the same Option-A
   shape, and replace the hardcoded `max_level=51` at the screen call
   sites with a league-derived ceiling. This is a gobattlekit-internal
   change; coordinate so the two ports don't silently diverge in behavior.
   It does NOT block the gopvpsim change.
4. Do NOT touch `gopvpsim.user_collection`'s default *and* assume
   gobattlekit picks it up — there is no shared code path; each repo must
   fix its own copy. Note the duplication in both repos' notes so the next
   editor knows to mirror.

## Out of scope for this design (do NOT do unattended)

- The production extraction refactor (Option 1) and the `user_collection`
  default change (Option A/B) are code changes; this doc is the spec only.
- The JS `:275`/`:344` single-sourcing — latent, defer until `matchMons`
  is wired up directly.
- The full end-to-end node/CSV behavior test (Option 3 assertion).

## ASSUMED / unverified

- That `generate_interactive_html` will tolerate `tier_info=[]` in the
  extracted helper for the maxLevel assertion. VERIFIED that the maxLevel
  line itself (4667) is independent of `tier_info`; the empty-tiers
  assumption is for the surrounding `thresholds`/`tierNames` fields, which
  the assertion does not read. Confirm no early `assert tier_info` exists
  in the extracted block (none seen at 4656-4687).
- Exact subprocess invocation flags for Option 2 (e.g. `--out`, opponent
  selection) were not run; the flag set above is illustrative. Confirm
  against `scripts/deep_dive.py` argparse before writing that variant.
- gobattlekit's port behavior parity with gopvpsim was not exercised this
  session beyond reading signatures; step 3 above should diff the two
  `compute_rank_lookup` implementations before mirroring.
