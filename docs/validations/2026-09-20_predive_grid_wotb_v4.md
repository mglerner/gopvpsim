# Pre-dive assessment -- gopvpsim website re-dive

Tree: `/Users/mglerner/coding/gopvpsim` @ `cfbbb98` (main, wotb-v4 merged)
Run: 2026-09-20, 09:30-10:10 EDT. Machine: 18 physical / 18 logical cores, 1.1 TiB free.
Scope: assessment only. No bake launched, no publish, no push. One probe dive into a
scratch `--html` path (cache ON, by design). `tests/fixtures/poke_genie_export.csv`
never staged.

## VERDICT: NO-GO

Two blockers, one of them found only by the probe dive:

1. **B1 -- the "Which one to build?" section does not render on a large fraction of
   dives.** `KeyError: 'def_cut'` at `scripts/deep_dive_which_build.py:719`, swallowed by
   the broad `except Exception` in `deep_dive._which_build_sections`, degraded to one
   log WARNING. Measured on a 13-blob Great League sample: 7 of 13 pages would ship
   with **no section at all** (4 `KeyError`, 3 `GuardError`). The 78-commit merge's
   flagship feature. Root cause isolated, one-line fix verified numerically (below).
2. **B2 -- the re-dive is fully COLD as it stands, and need not be.** Only **468 of
   236,236** current-engine cache columns carry the current gamemaster stamp. The
   gamemaster moved on 2026-09-19 (`9de08819ae0f` -> `6d6e9a7bc32d`), and the delta is
   **entirely non-sim**: 3 species changed only `searchPriority`, 1 unreleased mega got a
   move, 1 move added. A `migrate_cache.py --from-gamemaster` dry-run blesses
   **229,308 columns (97.3%)**. Launching without it burns an estimated **12-20 extra
   hours**.

Plus two decision gates from TODO.md that are Michael's, not mine (see L6).

---

## The grid

Layers: **E/C** engine+cache | **ORC** orchestration (chain, keeper, concurrency) |
**REN** per-dive render (deep_dive.py) | **INP** registry/pools/inputs |
**SITE** site assembly + publish.

### Lens 1 -- is the number right?

| Layer | Trigger                                                     | Result                                                                                                                                                                                                                                                                                                                                                                                                                                         | Verdict |
| ----- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| E/C   | `pytest tests -q` (full, incl. slow)                        | 5 failed, 2797 passed, 10 skipped, 13 xfailed in 1042s. All 5 reds are documented-expected: 4x `test_pogodives_article_showcases` (pins the re-rendered artifact against the stale published one; TODO.md:1765) + `test_verify_overnight_pool_containment::test_real_dives_contain_their_declared_pools` (shipped artifacts baked against the OLD pool; TODO.md:1971 says the bake clears it)                                                  | OK      |
| E/C   | `pytest tests -q -m "not slow"` after my guard commits      | 1 failed (the same pool-containment red), 2685 passed, 409s. No new failures                                                                                                                                                                                                                                                                                                                                                                   | OK      |
| E/C   | `sweep_cache.engine_hash()`                                 | `36037e51a2ee` -- unchanged since the 2026-09-15 migrations, as the brief claimed. Verified against the cache's own stamps, not the sentence                                                                                                                                                                                                                                                                                                   | OK      |
| ORC   | `scripts/verify_dev_counts.py --quiet`                      | rc=0 pre-edit (no drift waiting to kill the chain at hour ~40). My 12 new tests bumped it; sentinel re-stamped to 2836 in commit `4a4f6d0`                                                                                                                                                                                                                                                                                                     | OK      |
| REN   | probe dive; reference moveset actually rendered?            | `--reference MUD_SLAP,BODY_SLAM,TRAILBLAZE` was promoted to the landing by the near-tie rule (avg 487.5 vs Take Down 489.0) and `index.html` is the Mud Slap page. Rule 2 honoured                                                                                                                                                                                                                                                             | OK      |
| INP   | `verify_opponent_pools.py`                                  | rc=0, "All 8 opponent pools match live rankings"                                                                                                                                                                                                                                                                                                                                                                                               | OK      |
| INP   | every non-`auto` `reference` pin vs `get_default_moveset()` | 11 pins; 5 now merely restate PvPoke's default (redundant, not wrong); 6 differ. `oinkologne-female-great-league` pins `MUD_SLAP` where PvPoke's default is `TAKE_DOWN` -- **this is the exact lens-5 "Oinkologne stale-TACKLE" shape recurring**, but here it is deliberate (committed `a4430b3`, 2026-09-17, alongside the `--charged` pin) and the probe proves the Mud Slap page renders. Cradily's pin differs only in charged-move ORDER | WATCH   |
| SITE  | `prune_unlisted_dives.py --site userdata/website`           | rc=0, "no unlisted dive directories". The 3 departed GL dives are already gone locally                                                                                                                                                                                                                                                                                                                                                         | OK      |

### Lens 2 -- does it survive / does it act? (resource, concurrency, timeouts, disk)

| Layer | Trigger                                                                                                                                          | Result                                                                                                                                                                                                                                                          | Verdict                  |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| ORC   | `grep -rn 'Pool(\|ThreadPoolExecutor\|cpu_count\|--jobs\|--reserve' scripts/ scripts/deep_dive_lib/` + reconcile against `sysctl hw.physicalcpu` | 18 physical cores. Chain step 1: dives SERIAL at `--reserve-cpus 0` (all cores, one dive at a time). Chain step 7b: `run_iv_guides.py --jobs 1` -> preflight prints `1 x 18 = 18 planned vs 18 cores`, passes. No launcher whose (jobs x workers) exceeds cores | OK                       |
| ORC   | `grep -rn -i 'chrome\|chromium\|puppeteer\|playwright' ` over every chain script                                                                 | Zero. Nothing in the chain launches a browser; the absent headless-Chrome watchdog is irrelevant to the bake                                                                                                                                                    | OK                       |
| ORC   | read `overnight_redive.sh` for sleep/TTL protection                                                                                              | `caffeinate -is -w $$` (idle/timer sleep only). Lid-close clamshell sleep is still unprotected -- **pre-launch trigger: leave the lid open.** The 2026-08-06 bake lost 18h to exactly this                                                                      | WATCH                    |
| E/C   | `du -sh ~/.cache/gopvpsim/{sweep,slayer}` and `df -h`                                                                                            | sweep 115 GB, slayer 2.4 GB, 1.1 TiB free. `put_column` overwrites in place, so a cold re-dive replaces rather than doubles. 153,376 columns sit at the dead engine `515a0a95171b` and are reclaimable                                                          | OK                       |
| SITE  | `du -sh userdata/{website,replay}`                                                                                                               | website 15 GB, replay blobs 9.5 GB (280 blobs). Probe page 25.7 MB, split files 26.0/24.4 MB -- squarely in the 20-28 MB band. 136 dives x ~4 files x ~25 MB ~= 13-14 GB, in place of the existing 15 GB                                                        | OK                       |
| REN   | headless Chrome load of a page that DOES have the section                                                                                        | 22 MB page; one CONSOLE line, an informational `Canvas2D willReadFrequently` perf hint. **Zero JS errors.** Chrome did not self-exit inside 110s on a 22 MB page (DOM dumped fine); a human tab will feel slow but works                                        | OK (page weight = WATCH) |
| REN   | dup DOM ids in the RENDERED DOM (scripts + templates stripped, per the 2026-09-10 checklist drift note)                                          | 306 ids, 306 distinct, **0 duplicated**. The known `af-<hash>` x3 shape lives in the inert `<template>` copies, as documented                                                                                                                                   | OK                       |

### Lens 3 -- change-propagation (did every consumer of a changed thing change?)

| Layer | Trigger                                                                                                         | Result                                                                                                                                                                                                                                                                                                                                                                                                   | Verdict                      |
| ----- | --------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| INP   | set-diff `a85d62e~1` vs HEAD on `gl_top50_plus_cs.txt`                                                          | Exactly as briefed: +Charjabug (Shadow), +Diggersby, +Forretress (Shadow), +Oinkologne (Female); -Dragonair (Shadow), -Kingdra (Shadow), -Moltres (Galarian). 74 -> 75 entries, registry 136 dives                                                                                                                                                                                                       | OK                           |
| INP   | `grep -rn` the 3 removed names + their slugs across scripts/articles/thresholds/comparisons/guides/tests/worlds | **No hard-fail anywhere.** Hits are provenance comments, frozen oracle fixtures, and Worlds reject-reasons. Anchors on departed opponents in ~10 `thresholds/*.toml` degrade to an appended off-pool column + a WARN (`deep_dive.py:4550`), never a crash                                                                                                                                                | OK                           |
| INP   | every `opponent_pools/` reader                                                                                  | All 20+ readers take the pool as a parameter or a league->path dict. `run_iv_guides.py` reads `master_top60.txt` (untouched by this delta)                                                                                                                                                                                                                                                               | OK                           |
| INP   | hard-coded dive slugs vs the live 136                                                                           | **Found 3 orphan `DIVE_OVERRIDES` keys** -- `dewgong-great-league`, `mimikyu-busted-{great,ultra}-league`. Their editorial content was silently dropped and nothing reported it. All three were dead leftovers (verified: `build_command()` over all 136 dives is byte-identical with and without them), so no page was mis-baked -- but the hole is real                                                | **FIXED** (commit `f29c72e`) |
| INP   | downstream consumer: gobattlekit                                                                                | `/Users/mglerner/coding/gobattlekit/tools/threshold_export/run_overnight_batch.sh:33-34,42-43` hard-codes `Kingdra` and `Dragonair` in `BASE_DIVES`/`SHADOW_DIVES`; all three of `Kingdra (Shadow)`, `Dragonair (Shadow)`, `Dragonair` are now off-meta, and the four new GL focals are absent. `export_only_from_blobs.sh:53-54` reuses the same arrays. Read-only, downstream, does not block the bake | FIX (after the bake)         |
| SITE  | retired comparisons vs the registry                                                                             | `forretress-shadow-volt-switch-great-league` is BACK in the registry, which is the only reason `comparisons/forretress-fast-move-shadow.toml` was retired (`comparisons/RETIRED.md:11`). It is eligible to be reinstated once that dive bakes; `RETIRED.md:11` is now false prose. `jumpluff-regular-vs-shadow` and `oinkologne-male-vs-female` must STAY retired (the MALE Oinkologne did not return)   | WATCH                        |
| E/C   | `migrate_cache.py --list-stamps`                                                                                | 236,236 columns at the current engine; **only 468 at the current gamemaster**. See B2                                                                                                                                                                                                                                                                                                                    | **FIX (blocker)**            |

### Lens 4 -- input freshness

| Layer | Trigger                                                                    | Result                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Verdict                                         |
| ----- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| INP   | mtimes of `~/Documents/gopvpsim_cache/*.json` vs `data.CACHE_TTL` (86400s) | `gamemaster.json` **18.41h**, `great.json` 18.41h, `ultra.json` 17.18h, `rankings_mega_1500.json` 17.57h. `master.json` 66.9h and four cup/group files 193.9h (already past TTL; nothing in the GL/UL bake reads them)                                                                                                                                                                                                                                 | WATCH                                           |
| ORC   | read the TTL keeper in `overnight_redive.sh`                               | **The keeper lives in `overnight_redive.sh`, NOT in `run_website_dives.py`** -- confirmed. `touch_data_cache` at launch, then an AGE-based subshell polling every 300s and touching once the OLDEST file passes 21600s (6h), liveness-tied to `$$` with an EXIT trap. It covers the whole run and survives system sleep (it re-reads real age, not a timer). Chain step 1 is inside that window                                                        | OK                                              |
| ORC   | is a mid-bake rankings/gamemaster refresh possible?                        | **Only if the chain is NOT used.** A bare `run_website_dives.py` launch has no keeper: gamemaster is 18.41h old right now, so it would refetch ~5.6h in -- which is precisely the 2026-09-12 incident. Opponent ranks are a live read per page (`deep_dive_brief.build_opp_meta_ranks` -> `data.get_rankings_for`), so a mid-bake roll changes VERDICTS between pages with zero sim change                                                             | WATCH (launch discipline)                       |
| ORC   | what would CATCH a mid-bake roll?                                          | **Nothing.** `verify_overnight.py` has no gamemaster/rankings vintage check (only an mtime mixed-vintage check on split files within one dir). No hash is stamped into the page, the `meta.toml`, or the replay blob (`load_replay_state` keys contain no hash/stamp/version field). The only protection is the keeper                                                                                                                                 | FIX (recommended guard, not built -- see below) |
| INP   | jq/py diff of the pinned old gamemaster vs live                            | Old blob recovered from the local pvpoke clone at `78b1e66db` (2026-09-15), verified to hash to `9de08819ae0f`. Delta: `pokemon` 1742 -> 1742, **4 changed** (`melmetal`, `sableye_shadow`, `starmie_shadow`: **only `searchPriority`**; `staraptor_mega`: `released` false->true plus `extraChargedMoves`), `moves` 351 -> 352 (**+`BRAVE_BIRD_PLUS`, zero changed**). No species added or removed. Saved at `<scratch>/gamemaster_9de08819ae0f.json` | OK (and see B2)                                 |
| E/C   | the local pvpoke clone                                                     | `~/coding/pvpoke` HEAD is `78b1e66db` (2026-09-15) and hashes to the OLD stamp -- i.e. **the clone is behind the live cached data**. `userdata/_preserved/gamemaster_vintages/` does NOT hold a `9de08819ae0f` blob; I extracted it from git history into scratch. Copy it into `_preserved/` before the bake                                                                                                                                          | FIX (cheap)                                     |

### Lens 5 -- affordance (does every control do something?)

| Layer | Trigger                                                     | Result                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Verdict                      |
| ----- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| REN   | probe page: is the section there at all?                    | **NO.** `grep -c 'class="wb-root"'` = 0, `id="dd-which-build"` = 0. The clusters fall back to a sibling `<section id="dd-matchup-clusters">`. Confirmed on a control page (Swampert UL) that DOES render it: `wb-root` = 1 and the clusters are NESTED inside it (14 `<details>` opens vs 13 closes between the two anchors). So the fallback is honest -- but B1 is the headline                                                                                                                                                                                                                                                                                            | **FIX (blocker)**            |
| REN   | control inventory inside the section (control page)         | 47 `<button>`, 6 `<select>`, 18 `<summary>`, 6 `<label>`, 4 `<a href>`. Classes: `wb-criteria`(1), `wb-val`(36), `wb-btn`(8), `wb-tab`(3), `wb-scen`(3), `wb-allscen-y`(1), `wb-allscen-color`(1). **Every one of those classes is referenced in the page's embedded JS** -- no dead affordance shapes found                                                                                                                                                                                                                                                                                                                                                                 | OK (structural)              |
| REN   | best-buddy toggle swaps the section?                        | **NO.** On a BB-active page, `wb-root` inside `<template>` = **0**, while `dd-bb-card-tmpl`, `dd-bb-clusters-tmpl` and `dd-bb-prose-tmpl` all exist. So flipping Best Buddy swaps the dive card, the matchup clusters and the prose -- but the surrounding which-build section (answer strip, table, tabbed figure, notable list, four expanders) stays at L50. Because `MATCHUP_CLUSTERS_SLOT` sits INSIDE the section (`deep_dive_which_build.py:4097`), the post-toggle page shows **L51 clusters under an L50 headline**. `deep_dive_which_build.py:1524` says the section "is re-parented wholesale into an inert `<template>` by the best-buddy L51 pass" -- it is not | **FIX / decision**           |
| SITE  | `publish_website.sh` failure message for an incomplete site | Offered `--partial (safe, pulls live content down first)`. It does neither -- the pull-down was in an early draft of `986cc01` and was dropped; under `--partial`, `rsync --delete` still removes every page the bake has not reached. A false safety affordance at the exact moment a human decides whether to mirror over the live site                                                                                                                                                                                                                                                                                                                                    | **FIXED** (commit `2041637`) |
| ORC   | dive omission visible anywhere?                             | Before my change: a dive that omitted the section exited 0, the page rendered, the chain printed SUCCESS, and `verify_overnight.py` was silent                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | **FIXED** (commit `4a4f6d0`) |

---

## A. The probe dive

Command: `run_website_dives.build_command(oinkologne-female-great-league, DIVES)` **verbatim**,
`--html` redirected to scratch, plus `--card-out <scratch>` and `--verbose` (both additive;
`--card-out` is not in `build_command`, and the brief asks for it to be exercised).
Sweep cache ON.

```
.venv/bin/python scripts/deep_dive.py "Oinkologne (Female)" --league great \
  --opponents-file opponent_pools/gl_top50_plus_cs.txt --top-movesets 5 \
  --opp-ivs both --bait both --reference MUD_SLAP,BODY_SLAM,TRAILBLAZE \
  --html <scratch>/probe/out/index.html --interactive --standalone --mirror-slayer \
  --mirror-slayer-metric all --mirror-slayer-rounds 4 --mirror-slayer-pool 30 \
  --mirror-slayer-show 20 --split-movesets --reserve-cpus 1 \
  --charged BODY_SLAM,TRAILBLAZE
```

Numbers:

|                    |                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------ |
| wall time          | **13m 41s** (09:30:55 -> 09:44:36)                                                         |
| opponents          | 75 pool + 2 moveset variants + 3 active alt-variants = **79 columns**                      |
| movesets rendered  | **3** (charged pinned, so only 3 fast moves exist -- a CHEAP dive; typical dives render 5) |
| sweep cache        | **1 / 79 columns hit, on all 8 sweeps** -- effectively fully cold                          |
| sim phase          | ~7.2 min (~2.4 min per moveset)                                                            |
| render phase       | ~6.5 min (~2.2 min per moveset-file)                                                       |
| page sizes         | index 25.7 MB, `index_m1_take_down_*` 26.0 MB, `index_m2_tackle_*` 24.4 MB                 |
| `--card-out`       | written, 62,826 bytes, "Dive card written to ..."                                          |
| `--split-movesets` | 3 files emitted, names match the movesets                                                  |
| headless Chrome    | zero JS errors (one Canvas2D perf hint); 0 duplicate ids in the rendered DOM               |

Checklist from the brief, against the probe page:

- "Which one to build?" section present, with answer strip / table / tabbed figure /
  notable list / four expanders -- **ABSENT.** `WARNING:   Which one to build?: omitted
  (KeyError: 'def_cut')`.
- Matchup clusters inside it, no sibling section -- **inverted**: because the section is
  omitted, `deep_dive.py:2315`'s `if not which_build_html:` fallback fires and the
  clusters render as a sibling. That fallback is correct behaviour; it is just proof the
  section is gone.
- `--card-out`, split files, dive card carries the builds, console-free load -- **OK.**
- Render time per moveset for the section vs its ~60s budget -- **not measurable**: the
  section never rendered. On the control page (Swampert UL) the whole `prepare()` +
  render for 5 arms completed inside the replay run without a per-arm budget line in
  the log; I could not isolate a per-moveset section time.
- Best-buddy toggle swaps the section -- **NO** (see lens 5).

### B1 root cause, prevalence, and the verified fix

`scripts/deep_dive_brief.py:3477-3481` attaches the back-compat `def_cut` / `hp_cut`
aliases **only** when the alternative rectangle's axes are `{def, hp}`, and the comment
says so deliberately: "A (HP, attack) or (Def, attack) rectangle has no Def-and-HP
reading, so it does not get keys that would invite one."

`scripts/deep_dive_which_build.py:719` reads them unconditionally:

```python
flags = (dfn >= alt['def_cut']) & (hp >= alt['hp_cut'])
```

Any dive whose alternative rectangle is attack-paired therefore raises `KeyError`, which
`deep_dive._which_build_sections`'s bare `except Exception` turns into one log line.
`def_cut` / `hp_cut` are read **nowhere else** in `deep_dive_which_build.py` or
`deep_dive_engine.js` -- I grepped; line 719 is the only consumer.

Verified fix (monkeypatched, measured, **not committed** -- it is the merged feature's
own turf):

```python
a0, a1 = alt['axes']
flags = (planes[a0] >= alt['cut_a']) & (planes[a1] >= alt['cut_b'])
```

On the Oinkologne blob: `axes=['hp','atk'] cut_a=158.0 cut_b=114.6218310882` ->
mask covers **302**, brief prints **302**, MATCH. It reduces to the current expression
when `axes == ('def','hp')`, and the existing `got != alt['n']` cross-check right below
it is the guard that catches a wrong generalisation.

Prevalence, measured by running `which_build.prepare()` over existing replay blobs:

| sample                                | blobs | section renders | omitted                                               |
| ------------------------------------- | ----- | --------------- | ----------------------------------------------------- |
| Ultra League (2026-09-13/14)          | 17    | 14              | 3 (`KeyError`)                                        |
| Great League (2026-09-13 + the probe) | 13    | 6               | **7** -- 4 `KeyError`, 3 `deep_dive_brief.GuardError` |

The three GuardErrors all read `cell=Aegislash ... recomputed=named with no
engine-divergence marker`, i.e. they are downstream of the Aegislash (Blade) reuse-leak
contamination that this very re-dive is meant to clear (TODO.md:193-223) -- those
plausibly self-heal on fresh sims. The `KeyError` will not: it is a code bug, and on this
sample it costs **4 of 13 GL pages and 3 of 17 UL pages** outright.

---

## B2. Warm-vs-cold: the migration nobody has run

```
$ .venv/bin/python scripts/migrate_cache.py --list-stamps
current engine hash:     36037e51a2ee
current gamemaster hash: 6d6e9a7bc32d
engine stamps:      236236  36037e51a2ee  <- current
                    153376  515a0a95171b
gamemaster stamps:  235768  9de08819ae0f
                    153376  1398b001cf86
                       468  6d6e9a7bc32d  <- current
```

The brief's "gamemaster 9de08819ae0f" is **stale** -- PvPoke pushed on 2026-09-19 and the
TTL refetch at 15:08 moved us to `6d6e9a7bc32d`. Every one of the 235,768 good columns is
now a safe miss. That is what made the probe read 1/79.

Dry-run of the fix (read-only, no `--apply`):

```
$ migrate_cache.py --from-gamemaster 9de08819ae0f --old-gamemaster-file <blob>
  delta: 4 species changed/removed, 0 moves changed/removed, 0 added species, 1 added move
  changed/removed species: ['melmetal', 'sableye_shadow', 'staraptor_mega', 'starmie_shadow']
  blessed (unaffected, served warm): 229308
  deleted (affected, will re-sim):     6460
  skipped (other engine vintage):    153376
  skipped (other gamemaster vintage):   702
$ migrate_cache.py --slayer --from-gamemaster ...   ->  blessed 127, deleted 2
```

What actually changed in those 4 entries: `melmetal`, `sableye_shadow` and
`starmie_shadow` changed **`searchPriority` only** (a PvPoke UI field the battle engine
never reads); `staraptor_mega` flipped `released` and gained `BRAVE_BIRD_PLUS` (an
unreleased mega, in no GL/UL pool). `migrate_cache` is entry-granular, so it conservatively
re-sims their columns anyway -- 6,460 of them, which is fine.

**Recommended pre-launch sequence:**

```bash
cp <scratch>/gamemaster_9de08819ae0f.json \
   userdata/_preserved/gamemaster_vintages/gamemaster_9de08819ae0f_2026-09-15.json
.venv/bin/python scripts/migrate_cache.py --from-gamemaster 9de08819ae0f \
   --old-gamemaster-file userdata/_preserved/gamemaster_vintages/gamemaster_9de08819ae0f_2026-09-15.json --apply
.venv/bin/python scripts/migrate_cache.py --slayer --from-gamemaster 9de08819ae0f \
   --old-gamemaster-file <same> --apply
```

(The blob is recoverable at pvpoke `78b1e66db`; I verified its `pokemon+moves` hash is
exactly `9de08819ae0f`. Preserve it -- `_preserved/gamemaster_vintages/` currently has
`1398b001cf86`, `66b3cba2840d`, `8f1d6cca5c0f` and **not** this one.)

**Honest caveat.** A blessed column is only served if the FOCAL key also matches (species,
league, shadow, fast/charged pins, level, IVs, policy). The registry emits byte-identical
commands to the 2026-09-12 rebake for every unchanged dive, so overlap should be high --
but any moveset-screen flip mints a new focal key and goes cold regardless of the
blessing. Treat the warm estimate as a range, not a promise.

**Note also (do not act on it now):** `gamemaster_subset()` hashes whole `pokemon`
entries, so a pure `searchPriority` churn invalidates the entire sweep cache -- which is
exactly what happened. Narrowing the subset further to sim-read fields would prevent the
recurrence, but changing `gamemaster_subset` changes `gamemaster_hash` for everything and
forces a cold bake, so it is a *post-bake* item, never a pre-bake one.

---

## Full-chain time estimate

Anchor: the 2026-09-12..14 rebake (`userdata/logs/2026-09/rebake_movesets_20260912.log`),
135 dives, `Done in` lines summing to **2,121.3 min = 35.4 h**, mean 15.7 min, max 71.2 min.

Probe decomposition (cold, 3 movesets): ~2.4 min sim + ~2.2 min render **per moveset**.
Most dives render 5, so ~12 min sim + ~11 min render = ~23 min/dive cold at the top end.

| scenario                                      | dive step                                                                                                                                                       | + ML guides (best-effort) | + guides/index/gates                      | total        |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- | ----------------------------------------- | ------------ |
| **COLD** (launch as-is)                       | 136 x 15.7-23 min = **36-52 h**                                                                                                                                 | ~7 h cold                 | ~40 min (incl. `verify_tests` now ~9 min) | **~44-60 h** |
| **WARM** (gamemaster migration applied first) | render-bound floor ~8-11 min/dive plus the 4 fully-cold new GL focals, the +4 new opponent columns x 76 GL dives, and the 6,460 re-simmed columns = **20-28 h** | ~7 h                      | ~40 min                                   | **~28-36 h** |

Either way the bake spans **more than one 24h TTL window**, so the keeper in
`overnight_redive.sh` is load-bearing and the lid must stay open. `DIVE_RESERVE_CPUS`
defaults to 0 (all 18 cores) for an unattended run.

---

## Guards added (committed to main, explicit paths, each failing-first)

| commit    | what                                                                                                                                                                                                                                                                                                                                                                                            | pre-fix value pinned in the test                                                                                                |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `4a4f6d0` | `verify_overnight.scan_which_build_omissions()` -- the morning gate now goes red on every `Which one to build?: omitted` / `: skipped` line in the teed chain log, the way it already does for narrative-patch WARNs. Includes a scanner self-test against the literal `deep_dive.py` emits, so a reworded log line cannot silently disarm it. Also re-stamps the `test_count` sentinel to 2836 | function did not exist; a bake that omitted the section on every page passed GREEN                                              |
| `f29c72e` | `dive_registry.check_override_keys()` -- `run_website_dives.main()` now hard-fails in seconds on a `DIVE_OVERRIDES` key that names no dive, alongside `check_cup_slugs`. Removed the 3 dead keys (`dewgong-great-league`, `mimikyu-busted-{great,ultra}-league`)                                                                                                                                | 3 orphan keys live and unreported; proven inert (`build_command()` over 136 dives byte-identical before/after)                  |
| `2041637` | `publish_website.sh` -- `ACTUAL_DIVES` now counts registry dive pages instead of every depth-2 `index.html` (it was counting `guides/`, `matchups/`, `matchups-ultra/` as dives: 135 reported vs 132 real, hiding 4 unbaked dives); and the `--partial` bypass line no longer claims it "pulls live content down first"                                                                         | gate read 135/136 while 132 dive pages existed; bypass message advertised a pull-down that was removed before `986cc01` shipped |

Post-commit fast tier: **1 failed, 2685 passed, 409s** -- the one red is the expected
pool-containment test the bake clears. No new failures.

**Guard NOT built (needs a design call):** nothing stamps the gamemaster/rankings vintage
into a dive page, its `meta.toml`, or its replay blob, so a mid-bake roll is undetectable
after the fact. The cheap version is to record `sweep_cache.gamemaster_hash()` +
`engine_hash()` into each dive's `meta.toml` at render, and have `verify_overnight.py`
assert one distinct value across the fresh dirs. I did not build it because it touches
`deep_dive.py`'s render tail and the schema `build_website_index.py` reads -- your call.

---

## Delete risk (cell D) -- `rsync -n --delete` against the live site

I ran the rsync dry-run **directly** rather than through `publish_website.sh`, because the
script's dry-run path still regenerates `userdata/website/index.html` and the reader guides
(writes I was told not to make):

```
rsync -rvzhn --delete --delete-excluded --exclude=meta.toml \
      userdata/website/ mglerner.com:/home/mglerner/pogodives.com/
```

rc=0. Live site total 15.7 GB. It would delete **28 paths**:

- the 3 departed dive dirs and their contents -- `shadow-kingdra-great-league/`,
  `shadow-dragonair-great-league/` (+4 split files), `galarian-moltres-great-league/`
  (+4 split files). Correct: those dives left the registry.
- **13 stale split-moveset orphans** whose moveset no longer exists locally --
  `alolan-ninetales-ultra-league/index_m5_powder_snow_weather_ball_ice_chilling_water.html`,
  `corviknight-great-league/index_m1_sand_attack_air_cutter_iron_head.html`,
  `empoleon-great-league/index_m1_metal_sound_hydro_cannon_drill_peck.html`,
  `empoleon-ultra-league/index_m5_...`, `galarian-corsola-great-league/index_m1_astonish_night_shade_power_gem.html`,
  `galarian-moltres-ultra-league/index_m1_sucker_punch_fly_brave_bird.html`,
  `mimikyu-great-league/index_m1_shadow_claw_shadow_sneak_play_rough.html`,
  `shadow-alolan-ninetales-ultra-league/index_m5_...`, `shadow-empoleon-great-league/index_m1_...`,
  `shadow-giratina-altered-ultra-league/index_m5_...`, `shadow-hippowdon-great-league/index_m5_...`,
  `shadow-sableye-great-league/index_m2_...` and `index_m3_...`,
  `thievul-great-league/index_m5_sucker_punch_play_rough.html`.
  All correct: server-side leftovers from older moveset screens.
- **Nothing a current dive needs.** No registry slug is on the delete list.

Gate behaviour in dry-run, each checked individually:

| gate                                     | state now                                                                                                                                                                                                                                                                |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| completeness                             | expected 136, actual **132** dive pages (floor 122) -> PASSES. Missing: `diggersby-`, `shadow-charjabug-`, `forretress-shadow-volt-switch-`, `oinkologne-female-great-league`. (Before my fix it read 135 because `guides/`+`matchups/`+`matchups-ultra/` were counted.) |
| prune (`prune_unlisted_dives.py --site`) | rc=0, clean -- fires correctly, nothing to prune locally                                                                                                                                                                                                                 |
| cards-rerender sentinel                  | `userdata/.cards_rerender_pending` absent -> passes                                                                                                                                                                                                                      |
| link gate                                | 3 errors, all in `userdata/website/index.html` (hrefs to the 3 pruned dives). Chain step 8's `build_website_index.py` clears them                                                                                                                                        |
| dash gate                                | PASS, 765 files                                                                                                                                                                                                                                                          |
| `verify_dev_counts`                      | PASS                                                                                                                                                                                                                                                                     |

`--partial` semantics, now documented in the script itself: it relaxes the completeness
gate and skips the guide rebuild + `verify_tests.py`; it does **not** pull live content
down, and `rsync --delete` still removes every page the bake has not reached. Use it only
when you accept that.

---

## L6 -- backlog / process (the gates that are Michael's)

From TODO.md and DEVELOPER_NOTES.md:

1. **TODO.md:74-77** -- "NEXT: the warm re-dive ... **Blocked on Michael's cluster review**
   (two-axis rungs / cluster-mined co-gates, plan Phase D)." Unresolved on this tree.
2. **TODO.md:841-842** -- "Gate before the rebake: **Michael reviews the preview renders**
   (Sableye pair + Melmetal) and says go." No preview artifacts found under `userdata/`.
3. **Batch-the-bake economics (lens 7) -- ask before launching.** Parked ENGINE fixes whose
   only real cost is their own re-dive:
   - `cmp_atk` 1-ULP shadow-tie (carry pre-shadow atk on `BattlePokemon`) -- SMALL,
     **winner-affecting** at exact-CMP-tie cells. TODO.md:514-518.
   - Gate-column refactor + 3 dead constants -- SMALL-MED, certified **behaviour-neutral**.
     TODO.md:166-173.
   - `deep_dive_slayer.py` has no `--mechanics` flag, so it silently sims the LEGACY
     ruleset while every product CLI defaults to `new` -- SMALL-MED, affects mirror/slayer
     output. DEVELOPER_NOTES.md:197-200. **This one runs inside every dive
     (`--mirror-slayer`), so it is arguably in scope for this bake, not a nice-to-have.**
   - Aegislash x Azumarill new-mechanics cluster (6 of 243 oracle cells, widest gap on the
     grid) -- LARGE, root cause not found. TODO.md:1937-1959.
   If B2's migration is used, the CLAUDE.md "one localized fix per hash bump" rule applies:
   any engine edit bumps `engine_hash` and forfeits all 229,308 blessings. **Decide the
   engine co-fixes BEFORE running the migration, or you will run it twice.**
4. **Cramorant post-bake runbook -- still runs, with caveats:**
   - `cramorant_certify.py --league both --selftest 5` -> exit 1, selftest 50/50
     integer-exact, **4 bar failures** (the exact 4 GL Peck/Hydro Pump+Surf 2v2 cells sheet
     v6 fixes), 0 exemption violations. Expected pre-bake; **expect 0 post-bake**.
   - `cramorant_mini_sweep.py --check-tensor` -> the bare form in the runbook cannot run
     (`--league` and `--scenario` are required, rc=2). Concrete argv recoverable only from
     `tests/test_pogodives_v6.py:36-58`. With it, `--check-tensor` aborts by design until
     the rebake (plain tier byte-exact, pogodives plane is v5-vs-v6). **FIX the runbook
     line at TODO.md:148.**
   - The strategy-article re-render **cannot be rehearsed**:
     `scripts/render_pogodives_strategy_article.py` has no argparse at all and writes
     straight to `userdata/website/articles/cramorant-pogodives-strategy/index.html`.
     ~5-line `--out` addition, render-only, no engine-hash cost. **FIX before the bake.**
5. **`grep -rn "XXX:" scripts src tests`** -> zero hits. Clean.
6. **`verify_tests.py` now takes 549s**, against "~36s" in CLAUDE.md:359 and "~44s" in
   `scripts/verify_tests.py:15`. The merge added ~3,900 lines of
   `tests/test_which_build_section.py`. It is gate 1 of every publish path and chain step 9,
   so that is ~10 min at the launch keyboard and ~10 min at the chain's tail. Re-baseline
   the two documented numbers; consider `@pytest.mark.render` on the new render tests.
7. **`tests/test_pogodives_v6.py`** has a hidden test-ordering dependency (`from test_battle
   import ...` with only `scripts/` on `sys.path`); standalone it is 2/4 red for an import
   reason. The Cramorant runbook tells you to run it standalone. One-line fix
   (`tests/test_deep_dive_builds.py:49` shows the right form).
8. Two TODO.md bullets are now stale (both listed as red, both GREEN here):
   `test_ship_gate_roster::test_entry_points_route_through_the_roster` and
   `test_rebalance_tripwire::test_pvpoke_engine_matches_last_vetted_commit` (9/9).

---

## Blocking items, in the order I would clear them

1. **Fix B1** (`deep_dive_which_build.py:719`). One line, generalisation verified
   numerically (302 == 302) on the failing blob. Then re-run `which_build.prepare()` over
   the GL + UL blob samples and confirm the `KeyError` count goes to zero. Ship it with a
   failing-first test carrying the pre-fix `KeyError`. The 3 `GuardError` blobs are a
   separate question -- they look like Aegislash-contamination fallout that fresh sims
   clear, but **confirm that** rather than assume it.
2. **Decide the engine co-fixes** (L6 item 3), especially `deep_dive_slayer.py --mechanics`,
   which runs inside every dive. Any engine edit must land *before* step 3.
3. **Apply the B2 gamemaster migration** (sweep + slayer, `--apply`), after preserving the
   old blob. Expect ~12-20 h saved. Re-run `--list-stamps` afterwards and confirm ~229k
   columns now carry `6d6e9a7bc32d`.
4. **Add `--out` to `render_pogodives_strategy_article.py`** and fix the
   `tests/test_pogodives_v6.py` `sys.path` line -- both trivial, both named by the post-bake
   runbook.
5. **Resolve the two TODO.md gates** (cluster review; preview-render go) -- yours.
6. **Decide on the best-buddy / which-build swap** (lens 5). If the section is meant to be
   level-aware, it must go into a `dd-bb-*` host/template pair like the card, clusters and
   prose; if it is meant to be level-invariant, the clusters should probably not swap
   inside it, and `deep_dive_which_build.py:1524`'s comment needs correcting.
7. **Launch through the chain**, never a bare `run_website_dives.py`:
   `direnv exec . nohup scripts/overnight_redive.sh &`. Leave the lid open. The
   gamemaster cache is 18.4h old right now, so a keeper-less launch rolls it ~5.6h in.

Not blocking, do after: the gobattlekit `run_overnight_batch.sh` species list;
`comparisons/RETIRED.md:11` and the possible Forretress comparison reinstatement;
the vintage-stamp guard; the `verify_tests.py` runtime re-baseline.
