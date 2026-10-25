# Changelog

Completed/shipped work, reverse chronological.

## 2026-10-24 (night) -- Minior GL dives rendered locally (both forms); GL pools regenerated; NOT published

Michael, going to bed: "I want to have gotten to the point of having a
minior dive. that definitely means redoing the pool." Commits 383518b,
472235a, eea3705, 580a808 and this one. Nothing was published.

**Pools (383518b).** `opponent_pools/gl_top50_plus_cs.txt` regenerated
against today's rankings (pvpoke 38f70320d, fetched 2026-10-24 12:03):
adds Dragonair (Shadow) and Kingdra (Shadow), drops Diggersby and
Feraligatr (Shadow). `gl_top30_plus_cs_top100.txt`: adds Annihilape,
Azumarill, Electrode (Hisuian), Hydreigon (Shadow); drops Araquanid
(Shadow), Empoleon, Empoleon (Shadow), Feraligatr. The hand-built
`ul_top60.txt` / `master_top60.txt` still read DRIFT (Michael's curation
call; not inputs to a GL dive). `verify_overnight.py` DEFAULT_MARKERS
follow the regeneration (472235a): Dragonair (Shadow) and Kingdra (Shadow)
in, Diggersby out.

**Pre-dive gate** (docs/predive_checklist.md grid, four Opus reviewers, all
GO): orchestration (launcher fixed: no keeper, PYTHONUNBUFFERED, caffeinate,
pinned data cache; sweep cache ON is safe because no Minior column existed);
input freshness (gamemaster, rankings and the default moveset ROLLOUT /
ACROBATICS, POWER_GEM all match the registry); engine (2,106 Minior cells vs
PvPoke: 31 mismatches, 30 already catalogued, one new = the Mimikyu
break-disguise ordering, now TODO "Minior -- open items", 580a808); trace
(Medicham = PvPoke's seat-order route, docs/pvpoke_divergences.md item 1;
Ariados closed by the class-A port, eea3705). Fast tier: 3,119 passed, 2
failed, both known (`test_ml_guide_progress` cannot spawn `ps` under the
sandbox; `test_real_dives_contain_their_declared_pools` fails on the old
shipped pages until the next full bake brings the two re-entrants in). Smoke
renders on a 4-opponent pool passed.

**Dives.** `run_website_dives.py minior --allow-stale-pools` via
`userdata/logs/launch_minior_dives_2026-10-24.sh`: launched 21:58:35,
minior-core-great-league done in 17.4 min, minior-core-only-great-league in
9.2 min, exit 0 at 22:25:10. 79 opponents each (75 pool + 3 active variants
+ mirror). Artifacts `userdata/website/minior-core-great-league/` and
`.../minior-core-only-great-league/` (index + 4 split pages + vintage.toml;
engine 3d125a0e165f / gamemaster 03e7b77024e9); blobs
`userdata/replay/20261024_221424_Minior_Core_great.replay.pkl.gz` and
`20261024_222408_Minior_Core_only_great.replay.pkl.gz`.

**Verification.** Per page, 48 random tensor cells (any moveset, pvpoke /
rank1 IVs, bait / nobait, any scenario) re-simmed live: 48/48 integer-exact
on both pages (the Core-only draw included two mirror cells). Per page, 10
random pvpoke-IV bait cells vs headless PvPoke: 10/10 exact on both
(Core-only via `--p1-no-form-change`). `verify_overnight.py --since
"2026-10-24 21:58"`: check 2 (2 dirs fully fresh, one vintage) and check 3
(every declared pool entry present, 79 opponents) green; check 1 reads the
Sep 27 chain status and check 5 (60 stale ML guides) are not this run's;
check 4's pytest shows the same two known failures. Render review (Opus,
L5): structure matches Azumarill one for one, every handler and anchor
resolves, visible numbers match the embedded grids, mirror 1v1 at the
default IVs = 500. Findings carried to TODO as pre-publish items: the
closed-form breakpoint / bulkpoint labels are Core-form stats on both sides
(`anchors.py` has no form-change handling; about 15% of spread pairs swap
attack order between forms; grid cells unaffected); the "(Core only)"
pointer is plain text; the Core-only mirror has no PvPoke link; tier-card
anchor lines read "Minior Core (Move)".

**Two render-only follow-ups, re-rendered from the blobs
(`rerender_dive_cards.py`), no sim change.** (1) The Core page's dive card
had the typing-coloured fallback: pokemondb has no `go/normal/minior-core`
sprite (404), so the home sprite was placed at
`~/Documents/gopvpsim_cache/sprites/minior-core.png`; after the re-render
the Core pages differ from the first render ONLY in the card sprite (and
vintage.toml's rendered_at), the Core-only pages only in rendered_at. (2)
The callout's "the shell phase is a small stat adjustment, not the fight's
hinge" read as a claim about the shell phase (which swings scores by
hundreds) rather than about the level-rule uncertainty; reworded to the
recorded claim (<= ~2 Meteor levels, a few percent of the shell's attack
and defense; the Core phase is untouched). The selftests above were re-run
after the sprite re-render; the callout re-render changes prose only.

## 2026-10-24 -- PoGoDives strat re-checked against pvpoke_dp at 38f70320d (checklist B.3)

- **What:** the strat leg of the 2026-10-24 re-vet, deferred when Minior
  was ported. Record: `docs/validations/2026-10-24_cramorant_strat_recheck.md`.
- **Strat:** unchanged. Lab grid today vs the pre-port engine (`87e73e3`):
  0 of 2,430 PoGoDives-tier cells moved, 2 plain-tier cells moved onto
  PvPoke (UL Cramorant vs Dusknoir 1v2, 470 -> 487); net vs plain +76 on
  both engines; the 720-cell strict bar passes from the shipped tensors;
  800 random tensor cells re-simmed exact. No Minior overlay exists;
  2,304 Minior-on-either-side cells have PoGoDives tier == plain tier.
- **Found:** the shipped UL Cramorant page is not today's engine -- the
  port's TTL-order fix moved plain-tier cells against Dusknoir, Shadow
  Dusknoir and Seaking: at full resolution 11,793 of 552,960 plain-tier
  cells (those three opponents, 5 UL pages x 9 scenarios, PvPoke-IV / bait)
  differ, in 14 of 45 slices, never at 1v1 / 2v0 / 2v1 / 2v2; the Surf-only
  page is clean, as were the GL probes. PvPoke-confirmed in three cells,
  one a shown win that is a loss. The bar cannot flip (subset shifts <=
  0.16 mean against +11 margins), but the page is wrong where it moved. Cramorant UL re-dive owed before
  any Cramorant publish; `cramorant_certify.py --check-record` would pass
  the stale page (sha-only) -- TODO Cramorant block.
- **Predicate correction:** Dusknoir's frozen order equals its ascending
  order yet moved, so the fix-2 migration clause must read "frozen
  post-shuffle order != LISTED slot order", not "!= ascending" (TODO
  "Minior -- open items").

## 2026-10-24 -- DEVELOPER_NOTES trimmed to its read-whole cap; the long-form history is archived here

DEVELOPER_NOTES.md had grown to 2,034 lines / 118k chars against its own
stated cap (~52k chars, so that a session-startup read gets the WHOLE file).
It was rewritten to live invariants + open divergences only. The blocks below
are the REMOVED sections and the long-form originals of the most heavily
condensed ones, VERBATIM from the file at `0829b5a` (headings demoted one
level, nothing else changed), grouped under the section they came from. It is
NOT the complete pre-trim text: sections condensed in place (Engine constant
sourcing, bugs #1/#2, bandaid[929], Battle timeout, the move-selection
freeze, Threshold model, DP queue / TTL / CMP / selfBuffing, Form change
gotchas 1-4 and 7, and parts of Turn model and Sweep cache) have no block
here; for those, `git show 0829b5a:DEVELOPER_NOTES.md` is the record. Where
a block was condensed rather than removed, the condensed version in
DEVELOPER_NOTES is the current statement and this is the evidence behind it.
Dates inside the blocks are the original dates. Code-line references inside
the blocks are as of the dates they were written and have not been
re-derived; the 2026-10-24 fact-check found three of the inherited claims
(the spec-5 next-turn charged model, the `intended_pruning` flag, the JS
`little` row) already contradicted by the code, so read the archive as
history, not as a second source of truth.

### Archived: PvPoke re-vetting log: the 2026-06-06 entries

**2026-06-06 — re-vetted against pvpoke `bc532fbda`** (range
`8ed523811..bc532fbda`). Battle engine (`Battle.js` / `ActionLogic.js` /
`DamageCalculator.js`) byte-identical to the 2026-04-16 vetting — every
divergence cited in this doc + CLAUDE.md still resolves to the correct line.
Move data was rebalanced (real June-2026 game patch in `moves.json`); that's
data not logic, shifts both sims identically, so it is **not a divergence**
(our `data.py` already runs on it). Only fixture fallout:
`test_shadow_swampert_vs_registeel` (Earthquake + Flash Cannon) refreshed on
4/9 cells, re-vetted 9/9 exact vs `pvpoke_trace.js`.

**2026-06-06 — full oracle harness audit** (`scripts/audit_oracle_harness.py`,
12 matchups x 9 shields = 108 cells): **98 exact** (score+winner+chargedLog),
**6** the documented Aegislash bug-#3 cells (incl. the 1v2/2v2 510/w0 vs
376/w1 flip), **4** the Morpeko form-toggle cells (score+winner match; only the
form label differs — our two-way toggle is correct, PvPoke's one-way is bug #8
below; Michael verified in-game that Morpeko enters every battle in Full Belly
and toggles after each charged move). Pinned by a chargedLog assertion on the
Morpeko test + known-divergence marks in the audit script.

### Archived: Current status: the oracle-audit cell-count progression (2026-08..10)

**2026-10-24: 297 cells -> 387, 20 divergences + 0.** Ten Minior matchups
(both seats, the mirror, the Ancient Power and Take Down movesets, Cramorant
and Mimikyu interplay, and two for the synthetic 'Minior (Core only)'
variant via the harness's new `--pN-no-form-change`) -- all 90 cells exact.
The 297 prior cells were unchanged after the four fidelity fixes (full
audit, 0 new, 0 vanished).

**2026-09-28: 279 cells -> 297, 11 divergences + 9.** Two Aegislash-S vs
Moltres-G rows were added to pin "PvPoke bugs found" #10: the default
[SHADOW_BALL, GYRO_BALL] input (all nine cells the documented first-throw
quirk) and its [GYRO_BALL, SHADOW_BALL] positive control (all nine exact).
The 279 prior cells were unchanged (full audit, 0 new, 0 vanished).

**2026-09-27: 243 cells -> 279, 8 divergences + 3.** The six Aegislash x
Azumarill cells that stayed open after the 09-09 new-mechanics re-baseline
(`aegislash_vs_azumarill` (1,1)/(2,1), `aegislash_blade_vs_azumarill`
(1,0)/(2,0), `azumarill_vs_aegislash_shield` (1,1)/(1,2)) were our bug:
Shield-form charged moves were priced at the Shield atk (CHANGELOG
2026-09-27, "Form change gotchas" item 6). All 243 pre-existing cells now
match except the 8 Morpeko bug-#8 cells. Four non-Azumarill Aegislash
opponent rows were added (36 cells): 33 exact, 3 Cradily cells the
deliberate stage deviation.

**2026-09-02: 208+35 -> 226+17**, in three steps, none of them a rebalance.
The whole Aegislash divergence cluster is now closed -- all 18 cells across
`aegislash_vs_azumarill` and `azumarill_vs_aegislash_shield` are exact on
score, winner AND chargedLog, and both matchups carry an empty xfail set:

- **+6 (ours).** We were missing clause 4 of the activeChargedMoves shuffle
  (`Pokemon.js:790`, the `aegislash_shield` forEach that marks every charged
  move self-debuffing so Shield farms energy). Adding it made all six
  divergent `tinkaton_vs_aegislash_shield` cells EXACT on score, winner AND
  chargedLog, and turned `azumarill_vs_aegislash_shield` (2,1)/(2,2) from a
  winner flip into a score+winner match with a chargedLog-only residual.
  These had been annotated as "PvPoke bug #3" for months; they were our bug.
- **+8 (theirs).** PvPoke fixed the move-SELECTION half of bug #3 itself in
  `574aeb0da`: `ActionLogic.js:954` flipped the shields-up
  prefer-non-debuffing predicate from `!acm[i].selfBuffing` to
  `!acm[i].selfDebuffing`, which stops its Aegislash Shield (whose moves
  clause 4 marks self-debuffing) picking Gyro Ball over Shadow Ball. That is
  what we filed as pvpoke/pvpoke#378. We did not change to earn these; PvPoke
  came to us. Attribution was measured, not inferred: reverting that one
  predicate in a shadow copy of PvPoke's JS restores all 8 cells, while
  reverting blocks (a) and (e) changes nothing.
- **+4 (adopting theirs).** Turning our own `_AL_PREFER_NON_DEBUFFING` and
  `_AL_SHIELDS_DOWN_ANTI_DEBUFF` knobs ON (decision + corpus A/B in
  `docs/validations/2026-09-02_pvpoke_mega_revet.md`) closed the last four:
  `aegislash_vs_azumarill` (1,2)/(2,2) -- annotated for months as "the deeper
  near-KO plan-choice half of bug #3", which they turn out not to be -- and
  `azumarill_vs_aegislash_shield` (2,1)/(2,2)'s chargedLog-only residual. The
  same flip moved `test_bug3_farm_stack`'s Pinsir vs Cresselia (2,2) from 681
  to PvPoke's 707, taking that matchup from 8/9 to 9/9. Block (a) stays OFF.

The prior history: the 2026-08-24 Cramorant port added 4 matchups / 36 cells,
all exact, and re-verified the prior 207 unchanged at pvpoke 78c64048a;
172+35 re-audited 2026-08-06 at BOTH origin/main and the entry-13 engine
batch -- identical counts, so the batch moved nothing; the old 170+37 had
been stale since the hunt2 merge.

### Archived: Current status: previously failing matchups

#### Previously failing matchups — all fixed

Mienfoo vs Medicham (9/9) resolved by the `would_shield` buff-reset
ordering and CMP cancellation fixes. Full root-cause writeup in
`CHANGELOG.md` under `2026-04-04 to 2026-04-06`.

### Archived: Turn model: history 2026-06-23..09-10

History, 2026-06-23..09-10 (pure history; the dated detail is in
CHANGELOG "2026-09-02..03" and "2026-09-09..10"): `'new'` was first coded
from the published spec alone and pinned only by spec-derived unit tests
(`tests/test_new_turn_mechanics.py`); `'legacy'` stayed the default, the
CLIs printed an EXPERIMENTAL caveat, and the sweep cache was
force-disabled under `new` (the turn model was not yet in its key).
PvPoke's implementation appeared on branch `origin/new-mechanics`
(2026-08-23..26; five commits `041d8c722`, `71ab81008`, `442a4afe8`,
`a2685efe6`, `a1b3ebd95`, +29/-91 in `src/js/battle/Battle.js`; merged
into `origin/twilight-trails` before master), was A/B'd against ours on
2026-09-02, and our charged-move resolution was re-ported on 2026-09-03 from live-game
ground truth before PvPoke merged to master.

### Archived: Turn model: the slayer threading correction (2026-09-20)

**Threaded, and the default now tracks the engine (corrected
2026-09-20).** The paragraph here used to say `deep_dive_slayer.py` was
"not threaded" and simmed on the legacy clock. That went stale at
`37344e6`, which threaded `mechanics` through
`iterative_slayer_discovery` -> the pool `initargs` -> `_slayer_state`
-> every `simulate(...)` call, and `deep_dive.py` has passed
`mechanics=args.mechanics` at BOTH `--mirror-slayer` sites (the main
round and the best-buddy L51 re-convergence) ever since. So no shipped
mirror section ever ran on the wrong clock.

What WAS wrong until 2026-09-20: the three fallback defaults in that
module still read `'legacy'` while `battle.simulate`'s default went
`'new'` on 2026-09-09 (`7e6a82b`), so a caller that named no mechanics
got a legacy mirror beside new-clock sims. They now read
`deep_dive_slayer.SLAYER_DEFAULT_MECHANICS`, pinned to the engine's own
default by `tests/test_dive_worker_form_change.py::
test_the_slayer_default_mechanics_tracks_the_engine`. The module has no
CLI of its own (no `main()`, no argparse), so there is no flag to add;
`deep_dive.py --mechanics` is the only entry point.

### Archived: Turn model: slayer engine stamp CLOSED 2026-09-22 (full writeup)

**Slayer engine stamp: CLOSED 2026-09-22.** Until then `slayer_cache`'s
engine stamp was `sweep_cache.engine_hash()` verbatim, which hashes the
five `gopvpsim/` engine files plus `scripts/deep_dive_signature.py` and
**not** `scripts/deep_dive_slayer.py` -- so a change to the slayer
worker's own sim logic was invisible to the slayer cache. That is a
*wrong-answer* hazard rather than a stale-cache one: a stale stamp is a
safe miss, but an UNCHANGED stamp over changed behaviour is a silent
stale serve. It is also why this module carried three manual
`CACHE_VERSION` bumps under the standing "bump for any worker-code
change" rule (v2, v3, v6) -- the rule existed because the stamp could
not see the worker.

The stamp is now `slayer_cache.slayer_engine_hash()` =
`md5(sweep_engine_hash + deep_dive_slayer.py bytes)[:12]`. Composed
rather than folded into `sweep_cache._ENGINE_FILES` on purpose: **the
sweep stamp must not move** (~153,000 sweep columns carry it, and the
sweep never reads the slayer worker). Pinned by
`tests/test_slayer_engine_stamp.py`, which edits the real worker file
and asserts the slayer stamp moves while the sweep stamp does not.

One-time cost, paid 2026-09-22: the slayer stamp went
`9ac12a2754a1` (it was literally the sweep hash) ->
**`abcd962da95a`**, so **every slayer column is invalidated once** --
2.6 GB, 249 sidecar/pkl pairs on this machine, of which 150 were on the
then-current stamp. They are a SAFE MISS (re-simmed, never served
stale) and re-sim at the next bake's mirror-slayer rounds. Not
migratable: the whole point is that the pre-fix stamp cannot prove
whether the worker changed.

`migrate_cache.py --slayer` was updated with it -- both
`migrate_slayer_engine` and `migrate_slayer_gamemaster` now bless and
compare against the slayer stamp (blessing with the sweep stamp would
make every "warm" column a guaranteed miss), and `--list-stamps` prints
a separate SLAYER section with its own current hash so the operator
reads the right `--from-engine`.

### Archived: Performance baseline: the full measurement table

| Date       | Code                                  | sims/s    | Note                                               |
| ---------- | ------------------------------------- | --------- | -------------------------------------------------- |
| 2026-04-07 | `a57c39f` (recorded then)             | 3,055     | Pre-June gamemaster; not directly comparable       |
| 2026-06-10 | `a57c39f` (re-run, current data)      | 2,255     | Controlled baseline for the regression measurement |
| 2026-06-10 | `d419306` (pre-fix HEAD)              | 1,121     | The 2.0x regression, root-caused to `141eee1`      |
| 2026-06-10 | `154536a` (DP setup cache + log gate) | 2,278     | Post-regression-fix baseline                       |
| 2026-06-10 | `d4d8ed2` (arc S5: TTL JIT, stage-row | 3,160     | Previous baseline (warm JIT cache; first run       |
|            | reachability, DP-cache precompute)    |           | after an engine edit pays ~1-2s compile)           |
| 2026-09-25 | `6f99b08` (engine `5a813036625c`)     | **5,800** | **Current baseline** (CHANGELOG 2026-09-25;        |
|            |                                       |           | 5,846 at the parent engine `d78c67fd06a7`). New    |
|            |                                       |           | turn system, post-2026-09-09 gamemaster: NOT       |
|            |                                       |           | comparable with the rows above                     |

### Archived: Pre-rebalance data vintage pin (Twilight Trails baseline, 2026-08-31)

### Pre-rebalance data vintage pin (Twilight Trails baseline, 2026-08-31)

Recorded so the pre-rebalance numbers stay reproducible after PvPoke's
gamemaster moves. The GBL: Twilight Trails move rebalance lands
2026-09-08; PvPoke has merged its season branch into master on
season-start day, 0 days lag, for six consecutive seasons, and
`data.py` refetches on a 24 h TTL -- so the live cache will roll to
post-rebalance data within a day of the merge.

    pvpoke commit      7b96d91fb   (origin/master, clean tree, verified 2026-08-31)
    gamemaster source  46bd08a77:src/data/gamemaster.json
    gamemaster stamp   c431557dcc76   (sweep_cache v7 narrow hash; verified equal
                                       to the live cache's gamemaster_hash() ON
                                       2026-08-31. The LIVE cache moves with
                                       PvPoke master -- it was already
                                       219c5741f21a by 09-02 -- so re-derive
                                       from the commit, never assume the cache
                                       still holds this vintage.)
    cached columns     153,376 at gamemaster 1398b001cf86 / engine 515a0a95171b
                       (i.e. the cache was ALREADY gamemaster-stale before the
                       rebalance -- a migration was pending independent of it)

Recovery (the `--old-gamemaster-file` input for
`migrate_cache.py --from-gamemaster`):

    git -C ../pvpoke show 46bd08a77:src/data/gamemaster.json > /tmp/gm_prerebalance.json
    git -C ../pvpoke show 7b96d91fb:src/data/rankings/all/overall/rankings-1500.json   # -> great.json
    git -C ../pvpoke show 7b96d91fb:src/data/rankings/all/overall/rankings-2500.json   # -> ultra.json
    git -C ../pvpoke show 7b96d91fb:src/data/rankings/all/overall/rankings-10000.json  # -> master.json

**Never compare these by raw file md5.** `_fetch_json` re-serializes with
`json.dumps` before writing (`src/gopvpsim/data.py:183`), so the cache
file's bytes never equal the git blob's even when the content is
identical. Compare after `json.load`, or via
`sweep_cache.gamemaster_hash()`. (This trips people: the raw md5s here
are `bdafb91f...` for the cache vs `e99c66e3...` for the blob, which
looks like a mismatch and is not one.)

No file copies are kept: all four live cache blobs were verified
content-identical to committed pvpoke objects, so git IS the archive.

### Archived: Sweep cache: the v7 gamemaster-stamp narrowing and the 2026-06-29 cold-state story

- **Gamemaster hash is ALSO a per-column STAMP** (v7, 2026-06-29), and was
  NARROWED to the only sim-relevant subset `md5(pokemon + moves)` — CPM,
  type chart, STAB/BONUS, and shadow mults are all hardcoded in the engine,
  not read from the gamemaster (`sweep_cache.gamemaster_subset`). Two wins:
  (a) non-sim churn (timestamp / cups / formats / rankingScenarios /
  pokemonTags / ...) no longer invalidates the cache at all; (b) a real
  balance patch that touches only a few species/moves no longer orphans the
  whole cache — `migrate_cache.py --from-gamemaster <stamp>
  --old-gamemaster-file <blob>` COMPUTES the affected set from the actual
  pokemon/moves delta and blesses the rest. The delta predicate resolves
  each column's species to the FULL set of gamemaster entries the battle
  reads: base entry (shadow stats come from the base x hardcoded mult, so
  `_shadow` is stripped), transitively-expanded form-change alt forms
  (Aegislash/Mimikyu/Morpeko), and the move entries both sides use; an
  unresolvable species is conservatively re-simmed. The 2026-06-29 cold
  state was purely an over-broad-hash artifact: the bake gamemaster
  (`687e17`, pvpoke `63dfdaafb`) -> current (`75ad14`, `00f0afe7f`) delta
  was *only* the addition of `skarmory_mega` (moves byte-identical, 0
  species changed/removed, 0 columns reference it), so all 48,460 columns
  were semantically warm and were re-keyed + blessed via
  `scripts/migrate_v6_to_v7.py` (a COPY-not-move, idempotent, atomic-publish
  one-shot) then `migrate_cache.py --from-gamemaster`. Note `slayer_cache.py`
  shares `gamemaster_hash()`, so the narrowing cold-invalidated the slayer
  cache once (sound — same engine subset; re-bakes on demand; opaque keys
  can't be warm-migrated).

### Archived: Sweep cache: engine-hash bumps table (2026-09-15..20, all migrated)

**Engine-hash bumps, most recent first** (the `--from-engine` value a
migration needs is the OLD hash of its row):

| date       | old            | new            | change                                | predicate                          |
| ---------- | -------------- | -------------- | ------------------------------------- | ---------------------------------- |
| 2026-09-20 | `36037e51a2ee` | `9ac12a2754a1` | cmp_atk carries the pre-shadow attack | `no_shadow_either_side_20260920`   |
| 2026-09-15 | `1436a17ffbb2` | `36037e51a2ee` | Cramorant pogodives sheet v6          | `pogodives_sheet_v6_20260912`      |
| 2026-09-15 | `e4d380ec3e5e` | `1436a17ffbb2` | Aegislash reuse leak                  | `form_change_either_side_20260912` |

The 2026-09-20 bump is a lone localized fix, as the one-fix-per-bump rule
requires: the whole hashed delta is `raw_atk` (a new `Pokemon` property, a
new `FormData` field + its three builders and `apply_form_change`, and the
`BattlePokemon` field + `__post_init__` fallback + `cmp_atk`). Nothing else
reads `raw_atk`, so the only score that can move is one CMP decided, and a
battle with no shadow on either side has `raw_atk == atk` bit for bit.

### Archived: PvPoke bugs found: the 2026-07-16 filing record

numbering reflects discovery order; section 4 was retracted 2026-04-15
and is excluded from the count). **FILED UPSTREAM 2026-07-16** as pvpoke/pvpoke issues: #378 (our §3
Gyro Ball), #379 (§8 Morpeko), #380 (§1 dead pruning), #381 (the
initializeMove DPE-overwrite), #382 (§2 bestChargedMove staleness,
filed as an intent question). The §7 needsBoost report was reframed to
a retired-or-returning question and HELD BACK (draft still in
`docs/pvpoke_bug_reports.md`); the Blade→Shield CPM-table overflow
draft was RETRACTED 2026-07-16 — PvPoke's cpms table reaches level 55,
the overflow was ours alone. All drafts were re-verified 2026-07-16
against pvpoke master `10fd1a6e4` by an adversarial verify/refute/dedup
workflow before filing.

### Archived: PvPoke bug #3 (Aegislash Gyro Ball) -- original full entry

#### 3. Aegislash selects Gyro Ball over Shadow Ball

**FIXED UPSTREAM** in pvpoke `574aeb0da` (`ActionLogic.js:954`,
`!selfBuffing` -> `!selfDebuffing`; see "Current status", 2026-09-02):
PvPoke master throws 0 Gyro Balls in 76 Aegislash charged throws across
the 36 pre-09-27 Aegislash oracle cells (three Azumarill matchups + UL
Tinkaton; re-counted 2026-09-27). Kept for the record (and the bug
count). The Shield-form damages quoted below (49 / 39) were OUR
under-estimate, not the damage a Shield-form throw deals -- it resolves in
Blade form ("Form change gotchas" item 6).

The residual Gyro-Ball-vs-Shadow-Ball first-throw differences found
2026-09-28 are NOT #3: they are its inverse (ours picks Gyro Ball, PvPoke
Shadow Ball), from a different mechanism -- see #10 ("F3").

**File**: `ActionLogic.js` (near-KO DP or bestChargedMove selection)

PvPoke selects Gyro Ball (Steel, 80 power, 50 energy) over Shadow
Ball (Ghost, 100 power, 50 energy) for Aegislash vs Azumarill in
multi-shield scenarios. Both moves cost identical energy, have the
same type effectiveness (1.0x) and STAB (1.2x) against Water/Fairy.
SB does strictly more damage (49 vs 39 in Shield form, 101 vs 81 in
Blade form). Confirmed: Aegislash with SB-only scores 429 vs 376
with SB+GB in the 1v2 scenario, meaning GB availability actively
hurts Aegislash's score. Root cause unclear - may be in the near-KO
DP's plan selection or a bandaid condition.

### Archived: PvPoke bug #7 (needsBoost dead code) -- original full entry

#### 7. needsBoost / non-guaranteed-buff plan selection is dead code

**File**: `ActionLogic.js:515-539, 793-810, 868` (decideAction DP)

PvPoke's code looks like it accumulates a `stateList` of KO-bearing
terminal DP states tagged with `.chance` (product of `buffApplyChance`
values along the path), then picks the highest-chance plan when
`opponent.turnsToKO != -1 && poke.turnsToKO > opponent.turnsToKO`
(logged as "changes its plan because it needs the BOOST to win or
debuff"). Line 868 gates a downstream plan-reorder on the same flag.

Two independent faults render the whole system inert in simulate mode:

1. **Line 539: `changeTTKChance = 0;`** (unconditional, with comment
   "DISABLE THE NON-GUARANTEED BUFF EVALUATION SYSTEM"). This fires
   at the top of every move-evaluation iteration, after lines 519-536
   would have set `changeTTKChance` to the move's `buffApplyChance`.
   Every chance-<1 DPQueue push (lines 613, 631, 661, 680, 710, 728,
   756, 774) is gated on `if (changeTTKChance != 0)` → always false.
   So `stateList` only ever accumulates chance-1 plans.
2. **`needsBoost` is declared `false` on line 793 and is never
   assigned `true` anywhere in the file** (grep confirms). The
   "else if (... poke.turnsToKO > opponent.turnsToKO)" branch picks
   `bestPlan` but doesn't flip the flag. So the `if (!needsBoost)`
   gate at line 868 always fires — the plan-reorder branch is never
   actually gated.

**Empirical confirmation 2026-04-15**: ran `scripts/pvpoke_trace.js`
across all 9 shield scenarios for the four GL species carrying
`0 < buffApplyChance < 1` moves in their default movesets (Tinkaton+
Bulldoze, Corviknight+AirCutter, Clefable+Moonblast, Drapion+Crunch)
vs common opponents. The "needs the BOOST" decision log message never
fired — 0 hits across 36 sims. Matches the static analysis.

**Our stance**: we intentionally do NOT port stateList accumulation
or the needsBoost trigger. Doing so would *diverge* from PvPoke's
actual observable behavior in the direction of a feature PvPoke has
explicitly disabled. Our first-KO-terminal pick matches PvPoke's
effective single-plan behavior.

If PvPoke ever removes line 539 or fixes the `needsBoost = true`
assignment, revisit — the enumeration of affected meta species above
still applies.

### Archived: PvPoke bug #8 (Morpeko one-way) -- original full entry

#### 8. Morpeko form change is one-way instead of a true toggle

**File**: `Battle.js:1536-1537` (post-attack `charged_move` form trigger)
and `src/data/gamemaster/pokemon.json` (`morpeko_hangry` has
`formChange: null`).

Morpeko's gamemaster `formChange` is `type: "toggle", trigger:
"charged_move", moveId: "ANY"`, and the real game toggles Full Belly
<-> Hangry after **every** charged move (Aura Wheel swaps
Electric/Dark accordingly). Michael verified in-game 2026-06-06: Morpeko
enters every battle in Full Belly (battle start AND switch-in), fires a
charged move in its current form, then changes form.

PvPoke implements this one-way. The line 1536 trigger is gated on
`attacker.activeFormId != attacker.formChange.alternativeFormId`. The
first charged move changes Full Belly -> Hangry (guard passes); but once
in Hangry, `activeFormId == alternativeFormId` ("morpeko_hangry") so the
guard fails, AND the `morpeko_hangry` entry carries no `formChange` of
its own — so PvPoke never toggles back. Morpeko sticks in Hangry for the
rest of the battle (it does correctly reset to Full Belly on switch via
`resetOnSwitch: true`). The guard was evidently written for genuinely
one-way changers (Aegislash/Mimikyu) and wrongly catches Morpeko's
toggle, contradicting the gamemaster's own `type: "toggle"`.

**Our code**: `formchange.py:240-241` makes the Hangry form inherit the
`charged_move` trigger so it toggles back, matching the real game. So
our chargedLog disagrees with PvPoke's on any battle where Morpeko
throws a second-or-later charged move: we correctly fire the
post-second-toggle move from Full Belly (Aura Wheel Electric), PvPoke
fires it from a stuck Hangry (Aura Wheel Dark).

**Impact**: in `morpeko_vs_azumarill_form_change` the divergence is
score-neutral (every label-differing throw is form-independent Psychic
Fangs or a shielded Aura Wheel), so the score-only oracle never caught
it — the 2026-06-06 harness audit did. It IS score-relevant in any
matchup where Morpeko throws an unshielded Aura Wheel as its 2nd+ charged
move and Electric-vs-Dark effectiveness differs against the opponent
(e.g. Aura Wheel Electric is super-effective on Water, Dark is not).
There PvPoke's published Morpeko numbers are wrong; ours are right.

**Our stance**: keep our two-way toggle. PvPoke isn't demonstrably
better here — it's wrong about the mechanic — and our deviation matches
the verified game behavior. Pinned by a chargedLog regression assertion
on `test_morpeko_vs_azumarill_form_change` and marked as a known
divergence in `scripts/audit_oracle_harness.py`.

### Archived: PvPoke bug #9 (stale IV-rank chip) -- original full entry

#### 9. Stale IV-rank chip on battle permalink loads (UI-only)

**File**: `Interface.js:1858-1875` (URL-param branch) vs
`PokeSelect.js:418` (updateIVRank) and `PokeSelect.js:1320-1335`
(manual IV input handler). Found 2026-08-10.

When a battle permalink URL carries custom IVs, Interface.js calls
`pokeSelectors[i].setPokemon(arr[0])` — which renders the green
"Rank #N / 4096" chip via `updateIVRank()` while the Pokemon still has
its **default** IV spread — and then applies the URL's IVs/level with
`pokemon.setIV(...)` / `setLevel(...)` directly, filling the input
fields but never calling `updateIVRank()` again. The stats panel
updates; the rank chip keeps the default spread's rank. Typing an IV
by hand DOES refresh (the input handler calls `updateIVRank`), which
is why the bug only bites on permalink loads.

**Worked example (GL Mimikyu 0/8/14, level 26)**: the chip shows
"Rank #42 / 4096" — the rank of PvPoke's default GL Mimikyu spread
5/13/15 (L25, CP 1500) — while the true overall rank of 0/8/14 is
**#80/4096**. Verified by running PvPoke's own `Pokemon.js`
`getIVRank("overall")` under node (pvpoke_trace.js-style shims):
80/4096 for 0/8/14, 42/4096 for the default spread, under both forms
and every level cap. Our deep-dive card's SP #80 for that spread is
correct; PvPoke's own engine agrees with us.

**Impact**: display-only — no effect on sims, scores, or rankings.
Not filed upstream yet.

**Related non-bug (stat display convention)**: PvPoke floors displayed
atk/def to 1 decimal (`PokeSelect.js:75`), our cards round
(`deep_dive_engine.js:3838`). Cosmetic only (120.5 vs 120.6).

### Archived: PvPoke bug #10 (Shield-start first throw) -- original full entry with proofs

#### 10. Shield-start Aegislash's first throw follows the input order (quirk, not ported)

**Files**: `Pokemon.js:757-763` (shuffle clause 1), `:790-796` (clause 4;
`resetMoves` at `:711` re-pushes the same move objects and never clears
it), `resetMoves` callers incl. `Pokemon.js:420` (initialize), `:1288`
(addNewMove), `:1939` (reset), `Battle.js:113` (setNewPokemon); ours
`battle.py:1502-1506` (clause 1), `:1546-1559` (clause 4 stamp),
`:2969/2976` (`reset_for_battle` -> `_restore_shuffle_stamp`). Found
2026-09-28 (the "F3" follow-up of the 2026-09-27 Aegislash diagnosis).

**Mechanism.** PvPoke's `resetMoves()` priority shuffle has a clause 1
(same energy: move the buffing or higher-damage move to slot 0), gated on
`!selfDebuffing`, and a clause 4 that, in `aegislash_shield` form, stamps
every charged move `selfDebuffing = true` IN PLACE on the move objects.
That stamp is never undone, and `resetMoves()` runs several times before
a fight starts (initialize, move selection, setNewPokemon). So by the time
the opponent-aware reset runs, both of Shield-form Aegislash's moves are
already self-debuffing, clause 1 is dead, and slot 0 is simply the order
the user typed the moves in. Ours snapshots the stamp and
`reset_for_battle` restores the pristine move dicts (needed: without it a
reused Blade inherited the stamp, the 2026-09-12 leak), so at the
battle's first Shield shuffle clause 1 is live and, with default
[SHADOW_BALL, GYRO_BALL], puts the move that does more damage vs the
current opponent in slot 0 -- Gyro Ball against Fairy/Rock/Ice types, or
wherever Ghost is resisted (Dark: Moltres-G, Guzzlord).

**Consequences** (1080-cell GL sample, Aegislash 4/14/15 both start
forms vs 15/15/15 top-60 opponents, both seats): 52 cells differ only in
chargedLog (Gyro Ball vs Shadow Ball into a shield, 1 damage either way);
5 differ in score -- Moltres-G (0,0)/(0,1)/(1,1)/(2,1) and Guzzlord
(0,0) -- and in all 5 ours is about +100 for Aegislash (Aegislash-S vs
Moltres-G (0,0): ours 408/591, PvPoke 308/691; PvPoke's last-gasp throw
is the resisted Shadow Ball).

**Proofs.**

- *Forward:* PvPoke run with `--p1-charged GYRO_BALL,SHADOW_BALL`
  reproduces ours exactly on Florges (0,1), Moltres-G (0,0) and Guzzlord
  (0,0). The audit's `aegislash_shield_gb_first_vs_moltres_galarian_form_change`
  row keeps this as a standing positive control (all nine cells exact).
- *Reverse:* emulating the persisted stamp in ours (stamp the moves
  before the first Shield-form shuffle) makes all 52 log-only cells
  exact and moves exactly those 5 score cells to PvPoke's values, with
  no cell lost; 9 already-mismatched cells (Thievul (2,x), Cradily
  Shield-start) change chargedLog only and stay mismatched. The 279-cell
  oracle audit is unchanged under the emulation.

**Caveat, stated honestly.** Ours is order-invariant only at the first
Shield-form throw. After that the stamp persists within the battle in
BOTH engines (clause 1 is dead for later shuffles on either side), so the
input order still matters in the Blade phase: a Gyro-Ball-first input
changes 196/1080 sample cells versus Shadow-Ball-first in ours.

**Verdict: not ported.** PvPoke's slot 0 here is an artifact of how many
times `resetMoves()` ran, i.e. of the user's typing order, and where it
changes the score it throws the resisted move and loses about 100 points.
It passes none of the three "When our sim diverges" tests. Pinned in
`tests/test_form_change_oracle.py`
(`test_aegislash_shield_vs_moltres_g_first_throw_divergence`, PvPoke's
308/691 in the message, plus the GB-first positive control) and as nine
xfail cells on `aegislash_shield_vs_moltres_galarian_form_change` in
`scripts/audit_oracle_harness.py`.

### Archived: PvPoke bug #11 (Minior Meteor level typo) -- original full entry

#### 11. Minior's Meteor level: the simulator steps whole levels, the site shows half levels (ported with a switch)

**File**: `Pokemon.js:2590-2612` (`getFormStats`, Minior branch; pvpoke
`38f70320d`). Found 2026-10-22, confirmed at runtime 2026-10-24.

The Meteor level walk `while (newCP > battleCP)` steps `0.5` only when
`this.activeFormId == "minior_core"` or `this.decrementer == "minior_meteor"`
(sic -- `decrementer` is a never-assigned field, so the second clause is
dead; evidently a typo for a form-id check), else `1`. `changeForm` sets
`activeFormId` to the NEW form before calling `getFormStats`, so the
battle-start Core -> Meteor change sees `minior_meteor` and steps WHOLE
levels; the site UI (PokeSelect) calls `getFormStats` while Core is still
active and steps half levels. Result: pvpoke.com's displayed Meteor CP/level
and the simulator's Meteor stats disagree for about a third of GL spreads
(10/6/10: UI 43.5, sim 43.0; 12/14/12: 40.5 vs 40.0). We port the BATTLE
path (what the scores come from) behind `formchange.MINIOR_HALF_LEVEL_STEP`
(False = sim path, True = UI path); pinned by
`tests/test_minior.py::test_meteor_level_from_stored_core_gl` on both
settings. Neither path matches every in-game reading (memory
`project_minior_pvpoke_model`: go-iv's empirical rule fits 11/11; PvPoke's
formula 3/9 GL); Michael's call was to trust PvPoke's model over go-iv and
revisit when the community settles. Impact: <= ~2 Meteor levels, a 1-4%
atk/def scale on the shell phase. Draft: `docs/pvpoke_bug_reports.md` Report 11.

### Archived: PvPoke bug #4 (Mimikyu SS timing) -- retracted

#### 4. Mimikyu SS timing — RETRACTED 2026-04-15

Phantom bug: the divergence was a missing timeline log line in our
disguise-bust branch (fixed then), not a behavior difference. Full
writeup in git history (pre-2026-08-24 DEVELOPER_NOTES) and the
2026-04-15 "Localization meta-finding" entry.

### Archived: Resolved engine divergences (historical index, as of 2026-10-24)

### Resolved engine divergences (historical index)

Once-open divergences, now all RESOLVED and test-pinned. Compact index only —
full root-cause writeups live in CHANGELOG, the linked reviews, and the commit
messages.

- **shadow x1.2 wrongly folded into CMP attack — RESOLVED 2026-06-13.** CMP
  (who throws first on a simultaneous charged turn) compares the *unboosted*
  attack; shadow x1.2 boosts damage, not priority. Added `cmp_atk` (`atk/1.2`
  for shadow); switched battle.py's CMP sites off `.atk`. Cleared the 204-cell
  `shadow_cmp` family (all 30 GL top-20 winner flips). Pinned by
  `test_shadow_quagsire_vs_feraligatr_cmp`, `test_cmp_atk_strips_shadow_bonus`.
  - **Missed 10th site, the fire_now double-fire gate — RESOLVED 2026-06-27**
    (`582f7d7`): same `.atk`->`cmp_atk` fix. Shadow-XOR only; oracle-repro
    Shadow Quagsire vs Gastrodon 2v1 (625/375 -> 459/540). Pinned by
    `test_fire_now_cmp_shadow`. Impact 35/20,178 cells, 6 flips (window-
    defenders Talonflame/Milotic/Guzzlord/Gourgeist/Dusclops). Pre-fix dives
    carried it in shadow-XOR cells -> corrected by the 2026-06-28 cold re-dive.

- **Engine bug-hunt #2–#7 (2026-06-27) — all RESOLVED.** Report:
  `docs/reviews/2026-06-27_engine_bug_hunt.md`; shipped record in CHANGELOG
  "2026-06-28".
  - **#2** float32-truncated damage constants (`f1538ff`) + shadow-def
    `float32(5/6)` (`805cdc3`) — boundary-scattered, forced the cold re-dive.
  - **#3** farm-down stacks self-debuffing moves (`50e8cd2`,
    `test_bug3_farm_stack`); 0/2160 default-meta cells changed. Follow-up
    (~117 both-self-debuff divergences) CLOSED 2026-07-03: KEEP, every flip
    ours-favorable. Pins: `test_both_self_debuff_divergence.py`; writeup +
    post-`ffb582b` re-measure addendum:
    `docs/reviews/2026-06-28_both_self_debuff_divergence_cluster.md`.
  - **#4** slayer-cache key includes `focal_max_level` (`slayer_cache` v4).
  - **#5** bandaid[929] no-bait swap kept ungated as an INTENTIONAL divergence
    (see below); `test_bandaid929_nobait_divergence`.
  - **#7** `_cm_debuf_delta` dead str-vs-int branch -> `float(...)==1.0`
    (matches PvPoke loose-equality); 0/10458 dive cells. `test_cm_debuf_delta`.
  - **#6 bandaid[910] — RESOLVED 2026-06-29** (`ffb582b`). The [910] defer-gate
    picked the defender's max-damage charged move where PvPoke
    (`ActionLogic.js:929`) uses `bestChargedMove`; an accidental port infidelity,
    not a defended divergence. **Winner-stable but NOT score-stable** (the old
    "cosmetic / 16/16 oracle" wording was misleading): A/B Pangoro vs Lickitung
    GL 0-0 907 -> 715 (real turns/HP diff, 0 GL winner flips; flips 1 UL winner,
    Moltres-G vs Dondozo 478 -> 538). 2-line `_estimate_best_cm` fix. Warm-
    migrated via the both-sided self-debuff-CM predicate (`migrate_cache.py`
    `self_debuff_either_side`, 39,600/48,464 columns blessed); production re-dive
    launched 2026-06-29. **NB:** this resolves only the opponent-best-move PICK
    inside the [910] gate. (This entry used to add that a separate [910]/[918]
    self-debuff *timing* deviation remained intentional; re-checked
    2026-09-28 against pvpoke master `78b1e66db` ActionLogic.js, both gates
    match PvPoke's, and the `_optimize_move_timing` self-debuff exclusion
    that CLAUDE.md cited for it was removed 2026-06-11 (entry below). The
    one live divergence in this family is bandaid[929], "Known divergences"
    below.)
    Evidence: `docs/reviews/2026-06-28_bandaid910_migratable_fix_feasibility.md`,
    CHANGELOG.

- **Incoming selfDefenseDebuffing shield gate — RESOLVED 2026-06-13.** Removed
  an extra routing condition the reference lacks (a self-def-debuffing nuke is
  not selfBuffing, so PvPoke always-shields it). Tinkaton vs Malamar GL [1,0]
  702/297 -> 861/138. Writeup:
  `docs/validations/2026-06-12_oracle_grid/incoming_gate_writeup.md`.

- **Bait-wait hold — RESOLVED 2026-06-11.** Ported, but had an extra
  `not cm_self_debuf[1]` gate the reference lacks; removed. Snorlax vs Obstagoon
  9/9 exact.

- **Snorlax/Obstagoon OMT KO-override — RESOLVED 2026-06-11.** Our "exclude
  self-debuffing moves from the can-KO override" deviation was falsified
  (Snorlax ate one extra Counter per battle); removed, matches
  ActionLogic.js:317-329.

- **OMT `turns_planned` divisor — RESOLVED 2026-07-03.** We divided
  `poke.energy` by the cheapest *affordable* charged move (returning early
  when none was affordable); PvPoke (ActionLogic.js:305) divides by
  `activeChargedMoves[0].energy` (the frozen slot-0 move) regardless of
  affordability. At a low-energy deathbed state ours inflated `turns_planned`
  and fired several fast moves early (sweep doc Group D; PvPoke strictly
  better). Now uses the frozen slot-0 energy; pinned by Group D.

(Lesson across the last four: "score-neutral" claims about decision-timing
deviations need a trace, not reasoning — each was an extra condition the
reference lacks, with a plausible comment, producing real margin errors.)

### Archived: Known divergences: Minior open sweep cells, as written 2026-10-24

#### Minior (2026-10-24): UL level clamp, animation clock, 41 open sweep cells

Deliberate or open gaps after the as-is port (`tests/test_minior.py` is
PvPoke-exact on its 90 cells; none of these is in the oracle audit):

- **UL Meteor level 52 vs PvPoke's 55 (deliberate).** Meteor cannot reach
  2500 CP, so PvPoke's walk never steps down from its table end (55) and
  ours stops at `max(CPM)` = 52 (`formchange._MINIOR_PVPOKE_LEVEL_CAP`
  clamps the start; GL is unaffected because every GL answer is <= 52).
  UL Minior is unverified in-game and outside every pool. Pinned by
  `test_meteor_level_ul_clamps_to_our_cpm_table`.
- **`animationTime` (5000 ms) on the hp flip is not added to a clock.**
  PvPoke adds it to its wall-clock `time`, which only feeds the timeline
  display and the 240 s time-out (see "Battle timeout" below); turns and
  cooldowns are untouched, so no score effect unless a fight nears the limit.
- **4 of 702 sweep cells differ** after the class-A port below
  (`userdata/logs/minior_midflight_sweep_6.log`, scratch sweep vs
  `pvpoke_trace.js`; 41 before the port, `_5.log`; the 10-matchup oracle
  set is a subset and is 90/90). The log still lists 14: the ten Lickitung
  cells are the level-cap artifact explained below, PvPoke-exact when both
  sides cap at 50. Morpeko 2-2 both seats = the documented one-way-toggle
  divergence (bug #8); Medicham
  vs Minior 1-2 (ours 351 / PvPoke 373) and 2-2 (734 / 391): both engines
  reach the same DP plan [Ice Punch x3] at Medicham e=95 vs an 80-HP
  1-shield Meteor, then PvPoke's post-DP bandaid region (ActionLogic.js
  ~838-990) swaps slot 0 to Dynamic Punch and ours does not (frozen Core dpe
  1.775 vs 1.778 is the suspected gate -- NOT traced to a line). Michael's
  call 2026-10-24: ship the port, improve later (TODO "Minior -- open
  items"). (Ariados vs Minior 2-0 and the Sableye/Steelix/Lanturn/
  Cresselia/Charjabug cells closed with the class-A port.)

### Archived: Class A port (Minior form-animation cooldown reset) -- original full entry

#### Minior's form animation resets both cooldowns like a charged move (class A, PORTED 2026-10-24)

`Battle.js:548`: at the end of a round, `if(roundChargedMoveUsed ||
roundFormAnimation) poke.cooldown = 500` for BOTH Pokemon. The charged-move
arm is old (blame: 2019) and our turn model already reproduced it; the
`|| roundFormAnimation` arm is new in `4d2908fac` and `roundFormAnimation`
is set in exactly one place (`Battle.js:1668`, the `hp`-trigger change), so
it fires only on Minior's Meteor -> Core flip. PvPoke treats the 5000 ms
animation as a battle pause like a charged move. What that means in
PvPoke's state machine: cooldown only gates `getTurnAction` (`:732`), while
a queued fast resolves when `(turns - action.turn) * 500 >= fastMove.cooldown
- 500` (`:405-410`) -- so after the reset BOTH Pokemon may act again next
turn and a fast already in flight still lands on its own schedule. A Pokemon
can therefore decide with its own fast in the air, and a 4-turn mover (Volt
Switch) can have two fasts in flight. Ported in `simulate()`: `_queued_fasts`
is a list; the Phase B gate is PvPoke's plain `cooldown == 0` (a landing
fast still shows cooldown 1 at decision time, so normal flow is unchanged);
the new-mechanics landing no longer zeroes the attacker's cooldown (always
1 there anyway, and it would wipe a newly queued action); the TTL initial
state and the two DP adjustments test `defender.cooldown` as PvPoke does
instead of "has a fast in flight" (identical in normal flow); optimizeMove
Timing counts the attacker's own queued fasts (`ActionLogic.js:301-313`);
and after a fast-triggered flip both cooldowns are set to 1 (a flip off a
charged hit takes the existing charged arm). A flip off a charged hit was
already covered. Result: the 702-cell Minior sweep went from 41 open cells
to 4, the 387-cell audit was unchanged, and every mover landed on PvPoke's
value. Pinned: `tests/test_minior.py` fix 5 (four revert-fails cells, the
timeline mechanism, and the Lickitung level-cap lesson below).

Two lessons from the sweep that attributed those cells: (1) the scratch
tool read PvPoke's decisionLog "uses X" as the queue turn, but it is logged
at RESOLUTION, so its MIDFLIGHT/landed tags were unreliable -- the port's
evidence is the 27 cells that moved onto PvPoke, not the tags; (2) the ten
Lickitung cells that survived the port were a harness artifact: Lickitung
7/15/15's GL best level is 50.5 (best buddy) under our default cap and 50
under PvPoke's autoLevel, and that one level moves Acrobatics across a
floor boundary (99 vs 98). Pin `level=` in audit specs when a species'
best level exceeds 50 (the harness's `P(level=...)` exists for this).

### Archived: Near-KO DP plan choice (RESOLVED 2026-09-25) -- original full entry incl. the 2026-04-15 analysis

#### Near-KO DP plan choice: nuke-with-self-debuff vs serial-Fly (RESOLVED 2026-09-25)

**Resolved 2026-09-25: we now match PvPoke.** The `_cached_damage` memo
that our port of bandaid[866] reads is refreshed at PvPoke's four refresh
points (battle start in `simulate`, `_optimize_move_timing` for both
sides' moves with no energy gate, `would_shield`, and the form-changer's
moves in `apply_form_change`), so the bandaid fires exactly where PvPoke's
bandaid[885] does. Why the 2026-04-15 keep-our-plan decision below was
reversed: its rationale ("ours retains 23-30pp more HP in 6 of 7 cases")
was measured under the legacy turn system; the 2026-09-09 re-derivation
under the new turn system inverted it (PvPoke's Fly chain scored 72-129
points higher for Moltres-G in every divergent cell, and Lapras [1,2] was
still a winner flip against us). Michael's call 2026-09-25: "do what's
consistent with the new turn system." Verification: the 243-cell oracle
audit -- the six Moltres-G cells VANISHED as divergences (score and
chargedLog now exact), nothing else moved; `tests/test_battle.py`
`test_moltres_g_nearKO_plan_divergence_pinned` pins PvPoke's values and
fails on the old engine. One deviation stays: bandaid[866] only swaps when the target cms[0] is
non-debuffing, so the both-self-debuff cluster (docs/reviews/
2026-06-28_both_self_debuff_divergence_cluster.md, KEEP) is unchanged;
PvPoke swaps into another self-debuffing move there. Engine hash bump
d78c67fd06a7 -> 5a813036625c; cache migration predicate
`cached_damage_refresh_20260925` (self-debuff-either-side, see
scripts/migrate_cache.py). The text below is the original analysis, kept
as history.

**Mechanism (localized 2026-04-15 followup session):** The divergence
is NOT a difference in the near-KO DP's plan output — both sims' DPs
return `[BRAVE_BIRD]` as `finalState`. The divergence is in a
**post-DP bandaid**: PvPoke's ActionLogic.js line 885-887 (our port:
battle.py:1541-1558, bandaid[866]) swaps `finalState.moves[0]` from
the self-debuffing nuke to `activeChargedMoves[0]` (Fly) whenever:

    opp.shields == 0
    AND finalState.moves[0].selfDebuffing
    AND finalState.moves[0].energy > 50
    AND poke.hp / poke.stats.hp > 0.5
    AND finalState.moves[0].damage / opp.hp < 0.8

PvPoke's `move.damage` is essentially NEVER undefined: `initializeMove`
(Pokemon.js:830-839) sets it at battle init, `wouldShield` refreshes it
(ActionLogic.js:1121), and the OMT side effect (line 320, per-move when
`opponent.shields == 0`) keeps it freshest. So PvPoke's bandaid[885]
always evaluates its `damage/opp.hp < 0.8` ratio (possibly stale). Our port
caches damage at battle.py:652 but subgates the assignment on
`attacker.energy >= cm['energy']` — so in the Moltres-G cluster
(energy < BB's 55 at the T20 DP-entry state) our `_cached_damage`
stays `None`, bandaid[866] skips its ratio test entirely, the DP plan
is left alone, and bandaid[918] stacks BB until energy reaches 100 →
single-BB nuke instead of Fly-chain. The divergence surface is
therefore broader than the MG cluster: our bandaid[866] skips wherever
`_cached_damage` is None, while PvPoke's always fires. The empirical
cluster measurements and the keep-our-behavior decision below stand
(measured from actual traces).

**Why we don't fix it:** faithfully mirroring PvPoke's OMT side
effect (so bandaid[866] fires when PvPoke's bandaid[885] would) swaps
BB → Fly in **all** MG cluster cases, not just Lapras. The bandaid's
`damage/opp.hp < 0.8` test doesn't discriminate: all cluster cases hit
0.6-0.7 and fire — Lapras [1,2] (PvPoke's Fly plan wins, ours loses by 1
HP) but Jellicent/Corviknight (PvPoke's Fly plan worse by ~38-47 HP).

So the fix is all-or-nothing against a 6:1 weighting; matching PvPoke
inverts the ratio rather than improving it. Per CLAUDE.md "When our
sim diverges from PvPoke": PvPoke isn't demonstrably better overall,
and our deviation has a defensible reason (better HP retention in 6
of 7 cases). Keep the `_cached_damage` subgate as the intentional
deviation that implements this choice.

**Outcome comparison** — full magnitude across the cluster (UL top-8
harness, MG max HP=161, all cases MG wins in both sims):

| matchup           | ours MG HP | PvPoke MG HP | gap         |
| ----------------- | ---------- | ------------ | ----------- |
| Jellicent   [0,0] | 92  ( 57%) | ~45 ( 28%)   | +47 / +29pp |
| Jellicent   [0,1] | 137 ( 85%) | ~89 ( 55%)   | +48 / +30pp |
| Jellicent   [0,2] | 137 ( 85%) | ~89 ( 55%)   | +48 / +30pp |
| Corviknight [0,0] | 45  ( 28%) | ~7 (  4%)    | +38 / +24pp |
| Corviknight [0,1] | 71  ( 44%) | ~33 ( 20%)   | +38 / +24pp |
| Corviknight [0,2] | 97  ( 60%) | ~59 ( 37%)   | +38 / +23pp |

Consistently +23-30 percentage points (~38-48 raw HP); MG also KOs
6-12 turns earlier in our sim. The magnitude is what makes our
divergence defensible — if the gap were a few HP we'd match PvPoke; at
25-30pp the post-KO carry-over is material for next-mon analysis.

**Caveat — Lapras [1,2] winner flip**: 1 of 7 cluster cases is a real
edge case where our plan is worse. Same root cause (MG picks BB, PvPoke
picks Fly-Fly-Fly), but Lapras is bulky enough (234 HP) that our BB's
atk debuff bites AND PvPoke's 3 Fly throws add up:
- Ours: Lapras barely wins 502/497 (MG 0 HP, Lapras 1 HP, 1-HP margin)
- PvPoke: MG wins 608/391 (MG ~34 HP, Lapras 0)

Here PvPoke's slower plan **is demonstrably better** — it correctly
predicts MG wins a close fight that our BB-nuke loses by 1 HP. Pinned
as its own xfail in `tests/test_battle.py` under `_MG_NEARKO_PLAN_FLIP`.

**Decision**: keep our DP behavior, net. Rationale is 6:1 weight of
clear-win cases (ours retains 23-30pp more HP) against 1 close-fight
flip. Per CLAUDE.md "When our sim diverges from PvPoke" policy: PvPoke
is better for close/bulky matchups, ours is better for clear-win HP
retention. Neither plan is universally right.

**Impact** (UL harness top-8): 7 cases show |Δ|>20 (jellicent×3 at
d1=-146, corviknight×3 at d1=-118, lapras×1 at d1=+111 with winner
flip). All MG-involving, all defender=MG or bulky-water-attacker.
GL unaffected (no top-8 GL species has this matchup shape).

**Revisit** if: (a) wider harness sampling adds more bulky opponents
that produce close-fight flips (shifts the 6:1 ratio); (b) we add a
shield-state / multi-mon model where next-mon HP carry-over isn't the
only scoring dimension; (c) a probabilistic/random DP mode would
prefer PvPoke's lower-variance multi-throw plan; (d) we find a
discriminator that separates Lapras-style bulky-comeback matchups
from Jellicent/Corv-style clear-wins (bandaid[885]'s existing
`damage/opp.hp < 0.8` test doesn't — all 6 cluster cases land in the
0.6-0.7 band alongside Lapras at 0.70).

**Closed lead (2026-04-15 followup):** "Port a non-debuf swap into
the near-KO DP branch" was the original session hypothesis. The
localization found the mechanism is PvPoke's post-DP bandaid[885],
not a near-KO plan-selection difference — so porting a near-KO swap
would diverge from PvPoke, not match it. Issue retired.

### Archived: Resolved 2026-04 divergences (historical index)

#### Resolved 2026-04 divergences (historical index)

The 2026-04-04/15 correctness arc closed a batch of once-open divergences —
the `would_shield` buff-reset + CMP cancellation (Mienfoo/Medicham), the
simultaneous-KO 500/500 tie-break semantics, the `needsBoost`/`stateList`
dead-code decision (not ported; see "PvPoke bugs found §7"), the selfBuffing
flag scope, the activeChargedMoves priority-shuffle, the Forretress/Azu
stage-aware DP, the Mimikyu disguise-bust log line, the many-cycle non-debuff
swap, the OMT fast-also-KOs gate, the farm-down boost-move override, and the
defender-bestCM selfDefenseDebuffing shield gate (Moltres-G cluster; its one
live invariant — the SUPER_POWER DPE-edge >0.3 carve-out — is self-documented
in `src/gopvpsim/battle.py` `_estimate_best_cm`). All resolved and suite-pinned.
Full root-cause prose lives in CHANGELOG for the items it covers (Mienfoo/
Medicham, selfBuffing, priority-shuffle, Forretress/Azu DP); the rest live only
in git history (pre-2026-06-28 DEVELOPER_NOTES) and their linked commits — do
NOT assume a named item has a dedicated CHANGELOG section.

### Archived: Key implementation details: DP stack-two twins -- original full entry

#### DP "stack two self-debuffing moves" expansion -- both twins (2026-10-24)

PvPoke's DP has TWO blocks that expand a state by stacking two copies of a
self-debuffing charged move (selfDebuffing, `buffs[0] < 0`, `2 * energy <=
100`) and throwing both: a READY twin (ActionLogic.js:668-717, inserted
AFTER same-turn states with `<=`, skipped when `fm_stack == 0`, and it can
produce negative turn counts when energy > 2E -- kept verbatim) and a
NOT-READY twin (:764-808, inserted BEFORE same-turn states with `<`).
Eligibility reads `buffs` directly, so the Aegislash `[0,0]` selfDebuffing
stamp (bug #10) does not qualify. Both twins were missing until Minior's
hold-to-100 AI made Malamar reach 2x Super Power energy routinely. Porting
only the ready twin regressed 36 cells (Malamar vs Dunsparce 2-1 640/359 vs
PvPoke 784/215); with both, a 14,022-cell GL A/B scan moved 496 cells, every
one onto PvPoke's value (`userdata/logs/stack_two_verify_2026-10-24b.log`).
GL default movesets that qualify: Super Power and Psycho Boost (28 species).
Plumbing: `cm_stack_ok` in `_ensure_dp_init_cache` -> int8 array into
`_near_ko_dp_jit`; Python fallback `_dp_insert_farm_down` (ready) and
`_dp_insert_not_ready`. Pinned: `tests/test_minior.py` fix 3.

### Archived: Form change gotchas item 5 (Cramorant) -- original full entry

**5. Cramorant is the first MULTI-form / variable-target changer
(ported 2026-08-24 from pvpoke 78c64048a).** `FormChangeConfig.forms` is
now N-length (3 for Cramorant: base/Gulping/Gorging, order pinned) and
`BattlePokemon._form_idx` replaced the old `_form_is_alt` bool (a compat
property remains). The gamemaster's `alternativeFormId: "variable"` +
plural `moveIDs: [DIVE, SURF]` resolve at the battle.py charged_move
trigger site: prey = Gulping iff hp/max_hp is STRICTLY > 0.5 post-attack.
Gulp Missile is NEVER in `charged_moves` (a 0-energy charged move would
break ~30 affordability/DPE sites) -- it lives in the per-instance
`_extra_charged` registry and is inserted into the (now index-driven)
`_resolve_charged` action list when a prey-holder takes an unshielded,
non-instant charged hit. Damage is flat `floor(0.15*target_max_hp)+1`
computed inline (`damageMethod: percentMaxHP`). Tags drive three guards:
`instant` (unshieldable, no Mimikyu-disguise interaction, no
counter-missile), `ignoresFaint` (fires from the grave; lethal missile +
lethal trigger = 500/500 draw). `use_priority` is forced True in the
Cramorant mirror (PvPoke Battle.js:253-259). AI adds: Dive/Surf-ASAP
pre-farm-down rule, prey-holder energy stacking (piggybacks bandaid
[918]'s gate), and four wouldShield tail rules -- two of which replicate
PvPoke's shipped `move.moveID` TYPOS as-is for oracle parity (SURF
branches dead; a lethal Dive is never shielded -- likely inverted intent
upstream, candidate bug report; harmless for the Peck/Dive+Fly default).
Oracle: 4 matchups x 9 cells exact (audit; incl. Mimikyu disguise
interplay + a simultaneous-KO draw) + 81 fixture cells
(tests/test_cramorant.py). The wouldShield tail also ports upstream's
new Aegislash-shield-form rule (attacker-model side only; audit-clean).
A 52-agent adversarial review (2026-08-24) confirmed 19 findings, all
fixed same-day with failing-first tests (highlights: migrate_cache's
'variable' dead-end + a generator-consumption bug made the
missile/prey-form cache invalidation silently dead; the missile now
fires at a corpse for log parity; would_shield tail rules, [918]
widening, and the signature movable-axes widening are all unit-pinned).
Engine migration predicate: `cramorant_port_20260824` (Cramorant or
Aegislash either side). The three-tier policy campaign (PvPoke default /
never-bait / the "PoGoDives strat" overlay) is planned in
docs/cramorant_policy_plan.md.

### Archived: Form change gotchas item 6 (Shield-form Aegislash charged estimate) -- original full entry

**6. Shield-form Aegislash prices its CHARGED moves at the Blade atk
(FIXED 2026-09-27).** Every Shield-form charged throw changes form
(`activate_charged`) BEFORE damage resolves, so it always lands with Blade
stats. PvPoke's estimate knows this (`DamageCalculator.js:43-50`
substitutes `getFormStats("aegislash_blade").atk` for charged moves when
the attacker is `aegislash_shield`); ours used the Shield atk (82.85 vs
172.93 for 4/14/15 in GL: Shadow Ball estimated 44 vs Azumarill, dealt
91). Every consumer -- the farm gate, the DP plan, bandaid[918], TTL, the
opponent's would_shield -- then passed up KOs PvPoke takes: the six
Aegislash x Azumarill cells open since 09-09. The fix moves 153 of 1080
sampled GL cells, 149 of them onto PvPoke's value. Fixed in `BattlePokemon._charged_atk_base`, the ONE source for
the charged rows of all three damage builders (a gate-only fix fixes 0/6;
the fix must live in the caches). Keyed on the current form's trigger, so
Blade form and every other species take `self.atk` unchanged; fast moves
always use the current form's atk. Pinned by
`test_aegislash_shield_charged_estimate_uses_blade_atk` (tests/test_battle.py).

DELIBERATE DEVIATION -- the atk STAGE. We multiply the Blade atk by the
CURRENT atk-stage multiplier; PvPoke uses the raw, stage-blind Blade atk,
although its own throw (changeForm keeps statBuffs) does apply the stage.
So after an opponent's atk debuff (Rock Tomb, Icy Wind, Chilling Water,
Lunge, Breaking Swipe, ...) PvPoke over-estimates (Shadow Ball 91 at -1
where 73 is dealt) and ours equals what our resolver deals. This is NOT
invisible: in the 1080-cell sample (Shield + Blade 4/14/15 vs the top-60
GL at 15/15/15, 9 scenarios) it decides 15 cells per seat, 4 of them
winner flips (3 in Aegislash's favour under ours, 1 under PvPoke's), net
+209 rating to Aegislash under ours; and it is the whole of the
`cradily_vs_aegislash_blade` oracle xfails (1,1)/(1,2)/(2,2) (a
stage-blind variant reproduces PvPoke on all three; pinned at our value by
`test_cradily_vs_aegislash_blade_estimate_stage_divergence` in
tests/test_form_change_oracle.py, and by the stage -1 leg of the estimate
pin). Kept because PvPoke's choice is internally inconsistent (estimate !=
its own dealt damage) and not demonstrably better on outcomes; revisit if
that changes. Listed as docs/pvpoke_divergences.md item 7.

### Archived: Active alt-moveset opponent variants -- original full section

### Active alt-moveset opponent variants

`opponent_pools/active_variants.toml` lists project-wide alt-moveset
opponent variants that auto-merge onto every loaded opponent pool.
The file is read by `scripts/deep_dive.py` (`_apply_active_variants`)
unless the dive is invoked with `--no-active-variants`.

Use case: a meta-relevant species has a competitive split between
two fast moves (e.g. Forretress with Volt Switch vs Bug Bite) and we
want every focal dive's matchup matrix to see *both* fast-move forms
of that opponent without editing each pool file.

Schema per `[[variants]]` entry:

```toml
species = "Forretress"   # PvPoke speciesName, base form (no shadow suffix)
shadow  = true           # optional, default false
fast    = "BUG_BITE"     # optional fast-move ID override
charged = ["A", "B"]     # optional charged-move ID list override
note    = "..."          # free-form; ignored by the loader
```

At least one of `fast` / `charged` is required. Display name is
auto-generated:

* `Forretress | fast=BUG_BITE` → `Forretress (Bug Bite)`
* `Forretress (Shadow) | fast=BUG_BITE` → `Forretress (Shadow) (Bug Bite)`

The loader skips a variant whose `(species, shadow)` isn't already
in the loaded pool, so a single TOML can ship across leagues — a
GL-only Forretress entry quietly skips on UL pools. A display-name
collision with the inline pipe-syntax (e.g.
`Forretress | fast=BUG_BITE` directly in a pool file) is also a
no-op; inline wins.

Toggling:

* Comment out a single `[[variants]]` block to disable that variant
  while keeping the entry in source.
* Pass `--no-active-variants` to skip the auto-merge for one dive
  (clean-baseline reproductions).
* Empty / delete the file to disable globally.

The same per-line override format is also accepted directly in pool
files — `_parse_opponent_pool_line` handles `| fast=ID` and
`| charged=A,B` syntax. Use inline overrides when the variant is
genuinely pool-specific; use `active_variants.toml` when it should
apply across pools. Memory file
`project_active_alt_movesets.md` tracks which variants are currently
active and the pre-dive confirmation habit.

### Archived: Deep dive output file layout -- original full section

### Deep dive output file layout

Deep dive HTML files (and the logs that come with them) generated by
`scripts/deep_dive.py` are user-specific scratch — never committed to
the repo. There are two valid locations depending on whether you might
want to revisit the file later:

* **`userdata/dives/`** — for deep dives you want to keep around:
  baseline runs, runs you'll compare against later, anything you might
  want to look at again after a reboot. The whole `userdata/` directory
  is in `.gitignore`, so the files persist on disk but never enter the
  git history. Create the directory if it doesn't exist
  (`mkdir -p userdata/dives`).

* **`/tmp/`** — for truly throwaway in-session iterations: smoke tests
  while you're tweaking renderer code, "let me see what this looks like
  with a different flag", etc. macOS clears `/tmp/` on reboot, so don't
  put anything there you'd be sad to lose. Within a session, `/tmp/`
  is fine and the convention I (and Claude) have been using for quick
  verification cycles.

When in doubt, prefer `userdata/dives/` — the cost of an extra
directory entry is nothing compared to the cost of accidentally losing
a 7-minute deep dive run to a reboot.

The convention applies to all output files from `scripts/deep_dive.py`:
the HTML itself, the `.log` redirect file if you used one, and any
ancillary data (cached cohort dumps, etc.). If you're scripting batch
runs that produce many dives, point `--html` at a path under
`userdata/dives/` rather than the repo root.

Reference deep dives that *should* live in the repo (e.g., the
validation HTMLs under `docs/validations/`) are a separate category —
those are checked in deliberately as point-in-time evidence and don't
follow this convention.

### Archived: Log file layout -- original full section

### Log file layout

`scripts/deep_dive.py` and `scripts/deep_dive_slayer.py` route all
progress, warnings, and final-output tables through a structured logger
(`scripts/deep_dive_logging.py`). Rationale and the per-call-site
classification live in `docs/structured_logger_design.md`; this section
is the steady-state reference.

**Per-run log file.** Every dive opens
`userdata/logs/YYYY-MM/YYYYMMDD_HHMMSS_<species>_<league>[_shadow].log`
and writes every INFO/WARNING/RESULT record (plus DEBUG when
`--verbose` is passed). The monthly subdir is created on demand. File
records carry a full `[YYYY-MM-DD HH:MM:SS.mmm] LEVEL   deep_dive: ...`
prefix so `grep -E '\] WARNING' userdata/logs/2026-04/*.log` is a
reasonable forensic starting point. As with `userdata/dives/`, the whole
`userdata/logs/` tree is gitignored — logs persist across reboots but
never enter the repo.

**Latest-run symlink.** Right after the file is opened, the logger
atomically refreshes `userdata/logs/latest.log` to point at the current
run. Canonical monitoring command:

```
tail -f userdata/logs/latest.log
```

The symlink is swapped via `rename(2)`, so a long-running `tail -f` from
another terminal never lands on a broken link mid-update — the previous
run's file stays open on the old inode until you stop tailing it.

**CLI flags** (on `scripts/deep_dive.py`):

- `--verbose` — promotes aggregator DEBUG records to the log file.
  Stdout is unchanged.
- `--quiet` — suppresses INFO on stdout; WARNINGs and the Top-20 /
  banner RESULT records still appear. The log file is unaffected.
- `--log-file PATH` — overrides the auto-generated log path. Use
  `/dev/null` to disable the file handler entirely.
- `--log-dir DIR` — relocates the logs root. Useful for batch runs
  that want their own dated directory. Ignored when `--log-file` is
  given.

**Worker processes.** Spawn-mode pool workers (default on macOS) do not
inherit the parent logger's handlers. Each pool's initializer calls
`deep_dive_logging.worker_log_setup(log_path, verbose=...)` — a bare
`print()` from a worker bypasses the log file *and* stdout buffering
kicks in. If you add a new multiprocessing surface, thread `log_path`
and `verbose` through `initargs` alongside the existing state. See
CLAUDE.md "Debugging conventions" for the commit-time rules around
ad-hoc debug prints.

**Periodic cleanup** via `scripts/clean_logs.py` (dry-run default):

```
## Preview what would go away
python scripts/clean_logs.py --older-than 30d

## Actually delete
python scripts/clean_logs.py --older-than 30d --execute

## Archive (move to userdata/logs/archive/YYYY-MM/) instead of deleting
python scripts/clean_logs.py --older-than 60d --archive --execute

## Keep only the 50 most recent runs across all months
python scripts/clean_logs.py --keep-last 50 --execute
```

No auto-purge inside `deep_dive.py` — deletions happen only when you
run the cleanup script with `--execute`. The archive subtree is
gitignored the same way the live tree is.

### Archived: All-in-one vs split-moveset HTML: the 2026-06-10 history note

**History note (2026-06-10):** the paragraph above was false from
2026-04-12 to 2026-06-10. A cross-file analysis cache (`fa34f39`)
assumed split files shared identical analysis and served **moveset 0's
analysis sections in every split file** (surfaced as the "wrong
moveset in the Deep Dive Results subheader" symptom on the Sylveon
NAIC dive — the label was the visible tip; the whole section was
moveset-0's). The cache is removed; a tripwire assertion in
`generate_interactive_html` now verifies each split file's results
subheader names that file's moveset. Split dives published before the
fix carry moveset-0 analysis on their non-landing pages and need a
re-render to correct.

### Archived: Dive-card spreads: the poles are retired (2026-09-17) -- original full section

### Dive-card spreads: the poles are retired (2026-09-17)

Four surfaces used to name "the spreads this page is about", and they did
not agree:

| Surface                                   | Chose its spreads by                          |
| ----------------------------------------- | --------------------------------------------- |
| the dive card                             | the "Which one to build?" builds (2026-09-16) |
| the scatter overlay "Spec Card Spreads"   | three stat-extreme POLES                      |
| "Threats where your build choice matters" | the same three poles, plus their style names  |
| "Top Picks"                               | composite score, headlined with a pole style  |

The poles were a balanced lead (battle-score #1), an attack pole (max
effective attack) and a bulk pole (max effective defense), labelled by a
style classifier ("Attack Weight", "High Defense", "High HP", "Matchup
Hunter", "Generalist", "Balanced", "Bait Robust", "Max Bulk"). On Shadow
Sableye GL the overlay marked 9/6/13, 0/15/13 and 15/15/0 while the card
showed 8/7/5, 2/11/13, 9/6/13 and 7/2/14 -- a live disagreement on one page,
and the threat chips named two different spreads "Max Bulk".

All of it is gone. `deep_dive_which_build.card_specs` is now the ONLY
spread-selection rule on the page:

- `data_obj['recIvs']` (the scatter overlay) = the card's spreads.
- `data_obj['recNames']` (the threat chips) = the card titles' short forms
  (`short` on each spec: "Build 1", "Build 2", "Highest avg battle score",
  "Most matchups won"). This replaces `recStyles`, which is deleted.
- The threat rows' hint reads "-> won by Build 1 or Build 2" (it used to be
  "-> build <style>", which with the new names would have read "build Build
  1").
- RETIRED 2026-09-17 (round 8 item 2): "Top Picks" kept its own selection
  (top three by composite score) headlined "7/2/12 -- in Build 1" /
  "-- in no build", from `deep_dive_which_build.card_build_membership`
  (every member of every build, threaded through
  `generate_analysis_sections(card_build_membership=)` as `build_of`). The
  block, the membership map and the hand-off are all deleted; one Notable
  spreads list in the section is the page's only ranking of single spreads.
- The best-buddy (L51) pass reuses the league-cap spreads, as the card does,
  and the threat rows quote the card's own `PINNED_NOTE`.

**Fallback when a page has no builds** (a moveset with no decision cells, an
old blob, or a dive with no replay blob): the card, the overlay and the chips
all fall back to the composite-score top picks -- `rec_candidates`, filtered
by the same `efficient_frontier` strict-dominance guard the extra card
spreads always carried, capped at `REC_MAX_SPREADS`, and labelled "Top pick
##N". Never a pole. `REC_STRONG_POOL_N`, `REC_NOTABLE_MAX_CLEAR_FRAC` and
`REC_DISTINCTNESS_MIN_SYMDIFF` tuned the retired selection and are deleted
with it.

`tests/test_card_pole_tiebreak.py` now pins the RETIREMENT (its old content,
the 810f53c attack tie-break tripwires, is quoted in the module docstring):
a pole that came back would silently re-open the 2026-06-24 UL Mimikyu
dominated-spread bug, whose tie-break lives nowhere now.

#### SP1, and the standouts' two matchup lists

- The section defines "stat-product rank-1 (SP1)" once per surface -- the
  builds lead and the collapsed summary line -- and writes SP1 everywhere
  else (paragraphs, table column header, compare prefill). The glossary
  tooltip matches either spelling, so the first one a reader meets carries
  the definition. The panel legend entry is "Stat-product rank-1 (SP1)".
- Each standout now prints the two matchup LISTS behind its counts, not just
  the counts: the cells it wins that its nearest build does not guarantee
  (each with the share of that build's members that win the same cell,
  ascending; cells above `MEMBER_SHARE_TAIL` = 25% go to a counted tail), and
  the cells that build guarantees to every member and this spread loses.
  `deep_dive_builds.standout_block` computes them as `beyond_cells` /
  `lost_cells`.
- The fixed note under the block prints the page's OWN two thresholds -- the
  brief's line and the primary build's attack rung -- and only when every
  outside standout actually sits between them. Round 6 makes the window
  COUNTED rather than "a few spreads wide", and prints the bulk cuts the
  count was taken at (the standouts' own def and HP, TRUNCATED to the two
  places the page prints -- a rounded 96.3469 prints 96.35, and the count
  taken at 96.35 excludes the very spread the sentence is about). It also
  drops the cryptic "sits at the top of this grid on the axis that named it"
  for Michael's "if you already have one, build it", and says a build is a
  region whose members "all win a common core of matchups" -- they do not
  all win the SAME matchups, which is what the note claimed.
- Each standout paragraph now also carries the measured version of the
  note's claim: `n_profile_peers` (`standout_block`) counts the OTHER
  spreads on the grid that win every decision matchup this one wins -- 0 for
  Shadow Sableye's 7/2/14, 2 for 9/6/13. "No region reproduces this profile"
  is a statement about regions; this is the stronger one about spreads.
- The "Its rarest wins" sentence is printed only for a standout INSIDE a
  build. Outside, the two lists above already name every cell with its grid
  rate, and it repeated three of them.

#### One name per standout, one spelling for SP1

The two standouts carried three names each (section head / card title /
chip), and the shortest dropped the word that says the score is an AVERAGE.
There is now one canonical short name per standout -- "Most matchups won"
and "Highest avg battle score" -- and every surface LEADS with it: the
section head adds its qualifier after it ("Most matchups won (all nine
shield scenarios)"), the card title adds "(outside the builds)", and the
chips, the scatter overlay names and the stealable bullets use the short
form alone. `CARD_SHORT` and `STANDOUT_KIND` are the two dicts.

SP1 spellings, all deliberate:

- The at-a-glance strip's third row is labelled `SP1` (it is the first place
  the section names the spread, and the section's term marker attaches the
  glossary definition to the first occurrence, wherever it falls).
- The section's prose writes SP1 everywhere, including the brief's own
  headline sentences, which the renderer passes through
  `deep_dive_which_build.sp1_prose` ("The stat-product rank-1 spread,
  0/15/15, misses it by 6.35 attack" -> "SP1, 0/15/15, ...").
- The glossary's definition-list heading is "stat-product rank-1 (SP1)"
  (`glossary.DISPLAY`), so a reader scanning the terms for SP1 finds it.
- The CARD writes "SP #817" for a stat-product RANK and "SP1" for rank 1,
  and its foot defines both -- the card ships standalone with `--card-out`
  and has no section to read a key from.
- The "Rank-1 check" evidence field keeps its audit name (it prints as
  field 5 in the reader's order). It is a guard report, not reader prose.

#### The nested wide build

`deep_dive_builds.wide_build` surfaces at most one region of the same
lattice that

1. holds EVERY member of the primary,
2. is at least `WIDE_MIN_FACTOR` (2x) its size, and
3. carries a rule at the fidelity the table prints
   (`region_rule` = `pick_descriptions(describe(...))['d95']`),

ranked among those on

1. how many of the preset's OUTSIDE standouts (the ones with `in_build is
   None`) the region holds, 2 > 1 > 0; then
2. preset-weighted guaranteed cells; then
3. size, ties to the larger region.

The constructed bulk box is excluded, and it is computed for the PRIMARY
only. The rule is fitted lazily, best candidate first, so `describe()` runs
on one or two regions per preset rather than on all of them.

The FILTER clauses 1 and 3 are the 2026-09-17 round-6 correction. The
original rule was "holds >= 90% of the primary's members" with no rule
requirement, and ranked on cells alone; on Shadow Sableye GL arm 0 that
picked D,F,G -- 157 spreads, 51 guaranteed cells, holding 59 of Build 1's
61, and fitted by no two- or three-stat rule. A row headed "Build 1 wide"
that drops two of Build 1's own spreads is not wide around Build 1, and one
printed as "a list of 157 spreads that no rule fits" is not a target anybody
can aim at. Both reviews of the round-5 render landed on the same fix: make
containment and describability FILTERS, then rank inside them.

The standout clause of the RANKING key is round 6b (2026-09-17), and it is
the region's stated purpose finally entering its selection: Michael's reason
for surfacing the region at all is "the standouts as ordinary members of
Build 1 wide". Round 6 kept ranking inside the filters on cells alone, and
on Shadow Sableye GL arm 0 that picked E,F (292 spreads, 49 cells) over
three describable supersets that hold both standouts -- so the page's own
paragraph had to end "it holds neither standout below, so it is not a route
to them", on the one row that exists to be a route to them. Where a preset
has no outside standout the key is exactly the round-6 one (plain Sableye
and Melmetal are unchanged under all three presets).

It is deliberately NOT in `bl['builds']`: it lives at `bl['wide']`, so the
objectives line, the card set, the standouts' nearest-build search and the
UpSet columns all go on seeing two or three builds. The surfaces that opt in
are the table (one row directly under Build 1, carrying its payload index),
the paragraphs (one directly under Build 1's), the collapsed summary (a
clause, not a build slot), the standouts' membership, and the panel -- where
it travels LAST in the payload's `builds` array with `col: null`, so
`_wbBuildOf` lets every real build claim its members first, and draws in a
tinted Build 1 colour underneath Build 1.

**On Shadow Sableye GL arm 0 the rule picks D,H** -- 644 spreads, 43
guaranteed cells, `roughly Atk >= 148.70 and Def + 1.7*HP >= 301.928`, and
it holds BOTH outside standouts (7/2/14 and 9/6/13). Both of them sit below
Build 1's 150.24 attack rung, so only a region dropping that rung reaches
them; D,H is the best-guaranteeing one that does and its rule fits. Every
superset of Build 1 here that holds a standout, plus the round-6 pick, in
the order the round-6b key ranks them:

| combo | spreads | cells | standouts held |
| ----- | ------- | ----- | -------------- |
| D,H   | 644     | 43    | both           |
| D     | 838     | 39    | both           |
| H     | 1656    | 34    | both           |
| D,E,H | 369     | 48    | 9/6/13 only    |
| D,E   | 533     | 43    | 9/6/13 only    |
| E,H   | 738     | 42    | 9/6/13 only    |
| E     | 935     | 38    | 9/6/13 only    |
| E,F   | 292     | 49    | neither        |

(Rows below the winner are ranked but never described: the rule is fitted
lazily, so on this page `describe()` ran on D,H alone and the
describability of the rest is untested.) E,F was the round-6 pick (cells
alone) and D,H is the round-6b one. The
"holds neither standout below, so it is not a route to them" branch stays in
the renderer for pages where it is still true; on this page the paragraph now
ends "It holds both standouts below." and the collapsed line gains "and holds
both standouts".

What the wide surfaces print, after round 6:

- The paragraph opens on what the region is FOR ("the looser target around
  Build 1, for a reader who cannot hit Build 1 exactly"), then its RULE --
  with the set difference as a gloss, not instead of the rule. Round 5
  printed "Build 1 without 1v0 Azumarill staircase" for a region that was
  simply `Atk >= 150.24`: an internal lattice-set alias the page defines
  nowhere, in place of a one-stat rule.
- Every count it prints is a RETENTION on the preset's own scale: "keeps 49
  of Build 1's 55 guaranteed matchups" (narrow presets carry both scales, as
  the builds do). The wide region contains all of Build 1, so every cell it
  guarantees is one of Build 1's; round 5 printed a bare all-scenario count
  after a clause that said "guarantees 43", which read as 33 MORE.
- It names the guarantees it gives up out there (rarest first, three plus a
  count).
- When every spread it holds is already in a build its plot trace has no
  points of its own. The paragraph says so, and the JS emits the empty trace
  anyway with a legend entry that says it ("all N already in a build"),
  instead of letting Plotly drop a named region off the legend silently. A
  non-empty wide trace's legend reads "N of SIZE not already in a build",
  because the trace carries only the spreads no build claims while the table
  row gives the region's full size. Round 6's live example of `_own` = 0 was
  Shadow Sableye under the Even preset (E,H, 249 spreads); round 6b's
  standout clause moved that preset to E (838 spreads, `_own` = 589) and no
  preset of the three preview pages now has `_own` = 0, so the branch is
  covered by a unit test on a faked block rather than by a rendered page.
- The table row prints `--` for its most-winning member: the plot draws it
  no triangle and "Compare these spreads" does not offer it, both because it
  is not a build to build, so a cell naming one pointed at a spread the
  reader could find on neither interactive surface.
- RETIRED 2026-09-17 (round 8 item 2): `card_build_membership` included the
  wide region LAST, under the name "Build 1 wide only", so a Top Pick that
  no build held but the wide region did was labelled instead of reading "in
  no build" on a page whose builds table named the same spread; Top Picks
  also carried one sentence saying the two rankings answered different
  questions. The Notable spreads list says where every entry sits (build /
  wide / family / none) in the entry itself, so there is no second map.
- The wide region's combo is excluded from the UpSet panel's extra candidate
  columns: it took no column of its own (`col: null`) but could come back as
  an anonymous unselected column for the region the table above names.

#### Section-plot legend geometry (two Plotly facts, both measured)

The section scatter owns a full-width row with its legend UNDER the plot
(round 8 item 4), so the panel's height has to hold a legend whose height
nobody can predict from the trace count. Two Plotly 2.35.2 behaviours decide
how `_wbFitLegend` is written; both were measured in headless Chrome on
2026-09-17 and neither is documented:

- **A horizontal legend's DRAWN height is capped at half the graph height**
  and the overflow becomes a scroll box. So `rect.bg`'s height reports the
  CAP, not what the keys need (303px inside a 608px graph whose keys wanted
  342), and a layout sized from the rect converges on the cap. The uncapped
  content height is `gd._fullLayout.legend._height`, and it does NOT move
  when the panel grows (342 at graph heights 608, 900 and 1000). Measure
  that.
- **`Plotly.react` does not re-read the graph div's height.** Setting
  `style.height` from 685 to 900 left `_fullLayout.height` at 608 through a
  react AND a tick. A `window` resize event picks it up (that is what
  `responsive: true` listens to), `Plotly.Plots.resize` picks it up but is
  debounced ~100ms, and `Plotly.relayout(gd, {autosize: true})` picks it up
  SYNCHRONOUSLY while leaving responsive width alone. Use the relayout;
  setting `layout.height` outright would work too but turns autosize off for
  BOTH dimensions and kills responsive width.

Sizing the legend's room from `ceil(nTraces / 3) * 18px` instead cost the
round-7b render six clipped legend keys at a 900px viewport -- clipped by the
plot svg's own `overflow: hidden`, so `elementFromPoint` missed them and
legend-hover isolation was dead for both standouts, both most-winning members
and SP1 -- while Plotly's automargin squeezed the plot area from 324px to
186px. The invariant to hold is the PLOT AREA (322-324px at every width and
both views); the panel's height is what moves.

### Archived: Article lifecycle -- original full section

### Article lifecycle

Articles live in `articles/*.toml` (source TOML, checked in) and render
to `userdata/website/articles/<slug>/` via `scripts/render_article.py`.
Full schema: `docs/article_schema.md`.

#### Marking an article obsolete

When a CD move turns out to be strictly better/worse than the sidegrade
framing claimed, or the meta shifts enough that the analysis no longer
applies:

1. Edit the article TOML (e.g. `articles/oinkologne-cd-2026-05.toml`).
2. Change `[obsolescence]` fields:
   ```toml
   [obsolescence]
   status = "obsolete"
   as_of  = "2026-06-15"       # date you're marking it obsolete
   note   = "Mud Slap is strictly better in GL; sidegrade framing no longer applies."
   ```
3. Re-render: `python scripts/render_article.py articles/oinkologne-cd-2026-05.toml`
4. Republish: `scripts/publish_website.sh --push`

The renderer shows a red banner at the top of the page with the note
text and date. No other files need to change.

#### Changing authorship level

The `authorship` field tracks content origin. Update it as the article
evolves:

- `auto` — scaffold / auto-generated placeholder content
- `both` — human has edited the prose, but it's backed by sim data
- `expert` — fully human-written analysis

Edit the field in the article TOML and re-render. The banner color
changes automatically (blue -> green -> gold).

## 2026-10-24 (later) -- class A ported: Minior's form animation resets both cooldowns

- **What:** `Battle.js:548`'s `|| roundFormAnimation` arm (new in pvpoke
  4d2908fac; set only by the hp-trigger change, so Minior-only). After a
  Core flip off a fast hit both Pokemon may act again next turn while a fast
  already in flight still lands on schedule. `simulate()`: `_queued_fasts`
  list, Phase B gate = `cooldown == 0`, no cooldown wipe on a new-mechanics
  landing, TTL/DP read `defender.cooldown` (as PvPoke), optimizeMoveTiming
  counts own queued fasts, both cooldowns -> 1 after a fast-triggered flip.
- **Evidence:** 702-cell Minior sweep 41 -> 4 open (Medicham 1-2/2-2,
  Morpeko 2-2 x2); 387-cell audit unchanged; Charjabug 1-1 210 -> 626 (w
  flip), Cresselia 0-1 103 -> 293, Lanturn 1-1 306 -> 327, Steelix 2-2 87
  -> 95, all onto PvPoke. The ten Lickitung "divergences" were a harness
  artifact (our best-buddy L50.5 vs PvPoke's autoLevel 50; one Acrobatics
  floor boundary). Pins: `tests/test_minior.py` fix 5.
- **Correction to the morning's docs:** class A had been written up as a
  global engine change; the charged-move arm is from 2019 and was always
  matched. Michael: not filing anything upstream (PvPoke unresponsive).

## 2026-10-24 -- Minior ported as-is from PvPoke 38f70320d; four port-fidelity fixes; engine digest re-pinned

- **What:** Minior (released 2026-10-19) is the first `battle_start` +
  `hp` form changer. The stored Core (218/131) enters `simulate()` as
  Meteor (116/194) at PvPoke's formula level (whole-level walk, its
  simulator path; `formchange.MINIOR_HALF_LEVEL_STEP` flips to the site's
  half-level path), drops one way to Core under 50% HP off any landing, HP
  locked to Core's; both sides hold charged energy while a shell is up
  (`DP[minior_hold]`), and `would_shield` spares the shell against a hit it
  can take twice. Unknown gamemaster triggers now raise
  (`formchange._check_trigger`) instead of simming the stored form.
  Synthetic variant 'Minior (Core only)' (`data.SPECIES_VARIANTS`,
  `pokemon._all_entries`): the same Core spreads with no Meteor phase (a
  Minior re-entering battle already flipped); `species_id` and the
  rankings lookups map it to `minior_core`. Michael's decisions: trust
  PvPoke over go-iv's empirical rule, port as-is with the switch, GL dives
  in both forms (registry slugs `minior-core-great-league`,
  `minior-core-only-great-league`, Rollout pinned), Core spreads only.
- **Four fidelity fixes the port exposed** (each PvPoke-exact after;
  revert-fails cells in `tests/test_minior.py`'s docstring): (1) new-mechanics
  fast landings resolve in queue order (queued turn, seat) and a landing
  that flips the defender's form re-prices in-flight fasts
  (azumarill_vs_minior 1-1 646 -> 641); (2) turnsToLive walks the
  defender's frozen post-shuffle move order (Minior vs Drapion 1-1 461 ->
  680, Carbink vs Malamar 2-2 399 -> 406); (3) the DP "stack two
  self-debuffing moves" expansion, BOTH twins (ActionLogic.js:668-717,
  :764-808) -- 496 of 14,022 scanned GL cells moved, all 496 onto PvPoke
  (Minior vs Malamar 0-0 612 -> 599; Malamar vs Dunsparce 2-1 640 -> 784
  with the not-ready twin); (4) battle-start freeze order per seat,
  freeze-then-change as in `Battle.start` (Ariados vs Minior 2-1 265 ->
  625). Fixes 2-3 move non-Minior cells: every published GL column with a
  Super Power / Psycho Boost user or a shuffle-promoted defender move is
  stale under the new engine hash (TODO "Minior -- open items", cache).
- **Verification:** oracle audit 387 cells (ten Minior matchups added,
  90/90 exact), the 20 non-Minior divergences the identical set to the
  pre-port run; 702-cell Minior sweep 41 open cells, catalogued in
  DEVELOPER_NOTES "Known divergences" (Minior; the class-A cooldown-reset
  quirk is Michael's pending port-vs-document decision, Report 10 drafted).
  `tests/fixtures/pvpoke_engine_digests.json` re-pinned at `38f70320d`
  (upstream delta: Minior + the e87448291 sandbox fix, which supersedes our
  bug-report draft 9; `test_pvpoke_sandbox.py` re-pinned to the fixed page).
- **Tooling:** `scripts/pvpoke_trace.js` `--p1/--p2-no-form-change` +
  formLog/finalForms; audit harness `no_form_change` plumbing and
  ' (Core only)' label fold; `deep_dive_slayer.py` looks the focal up via
  `get_pokemon_entry` (variants are not in `gm['pokemon']`); deep-dive
  form-change callouts for both Minior names.
- **Not done:** no dives run (opponent pools have drifted, `run_website_dives.py
  minior --dry-run` fails; regeneration is Michael's call), no publish, no
  cache migration, UL unverified.

## 2026-09-28 -- Mirror population block: wording decided, render gate opened

- **What:** TODO "NEXT BAKE: mirror population" item (g). Michael picked
  the V4 lead sentence plus the V2 table from the 2026-09-28 mockups
  (`~/coding/reports/gopvpsim-mirror-paragraph-mockups-2026-09-28.html`),
  and `deep_dive_which_build.RENDER_MIRROR_POPULATION` is now True. The
  block under the builds table, where the blob carries a population: a
  lead sentence chosen by a mechanical trigger (column moveset differs from
  the arm's -> name it, "every build ... loses the 1v1 to all N" only when
  true of every build's typical member, else the counts; same moveset and
  no build beats more than 2 while one out-prioritises half -> "Priority
  does not win the {species} mirror, bulk does"; same moveset and a build
  beats half -> "{Build} beats k of the top-N"; else no lead), then a table
  (per build: spreads, the typical member's W / T / L and CMP wins against
  the rank list and against the page's picks), a caption naming the column
  moveset, and the CMP-cut sentence.
- **Facts:** `population_facts` rows carry `tie` (score == 500; `is_win` is
  strict) and `loss` beside `beat`, off ONE typical member per build (the
  lower middle by (wins, ties), so w + t + l = N); each group carries its
  `moveset`, the facts the `arm_label`. `beat` and `cmp` are unchanged.
- **Old pages:** blobs without a population render byte-identical
  (replay-render harness, five default blobs, vs a main@3beb843 baseline).
- **Pins:** `tests/test_mirror_population.py` (recount of ties and losses
  from the stored scores; each lead trigger word for word; the table
  cells; the gate test inverted to "population present -> new block,
  absent -> cohort paragraph byte-identical").

## 2026-09-28 -- PoGoDives sheet v8: rule R, the Surf-gulp 0v1 gate reads HP (0a1df03)

- **Why:** sheet v7's `surf_gate_dpe` 2.25 (entry 2026-09-27) fixed the GL
  Peck / Fly + Surf 0v1 Araquanid bar failure but also sent Jumpluff and
  Kingdra (same Fly/Surf DPE band, ~2.65-2.75) back to plain: about -165
  rating per cell on fights Cramorant loses anyway. A read-only probe
  (2026-09-28) found a principled discriminator; Michael approved it the
  same day.
- **Rule R:** row (0,1) gains `surf_early_when_behind: True`. With a SURF
  gulp (and CMP won, as the row's 'cmp' gate already requires),
  `_cram_dive_gate_dpe` keeps the 3.0 gate while Cramorant's HP fraction
  is below the opponent's; level or ahead, v7's 2.25 applies. Behind on HP,
  the loaded missile is insurance that fires on the opponent's lethal move
  (Jumpluff, Kingdra); ahead, a resisted Surf only spends the tempo the
  lethal Fly needed (Araquanid: the Fly KO beats Mirror Coat on CMP). Reads
  only both sides' hp/max_hp, which are dedup-signature components. Every
  other row is byte-identical; a DIVE gulp never reads either field. A
  strategy-sheet change, not a PvPoke divergence (docs/pvpoke_divergences.md
  untouched).
- **Probe evidence (not knife-edged):** the DPE band [2.25, 3.0) is reached
  by exactly three opponents on the GL Fly + Surf page and by none on any
  other page (Dive gulp, or ratio 1.0 from PvPoke's `moveID` typo). Any lead
  cutoff in [-0.25, +0.10] is byte-identical (Araquanid's lowest lead +0.13
  vs Jumpluff/Kingdra's highest -0.27). Ten other candidates were screened
  (Mirror Coat name check, two-hit KO, HP <= 50%, race count, CMP margin,
  type steps, ...): the ones that work are knife-edged or name-based; the
  rest fail on Kingdra or do not separate.
- **Stride-1 recert, GL Peck / Fly + Surf 0v1, all 8 slices** (319,488
  cells each; bait/nobait and cap 50/51 give identical numbers):
  pvpoke net +11 / mean +10.491 (v7) -> +11 / +14.470; rank1 +0 / +13.298
  -> +0 / +17.487. Only Jumpluff (4,096 pvpoke / 4,050 rank1 cells, smallest
  gain +163 / +162) and Kingdra (3,456 / 3,968, smallest +166 / +167) move;
  no moved cell gets worse, 0 win flips; worst opponent unchanged
  (Jellicent, 0 net, -0.93 / -0.69 mean). Plain-PvPoke tier integer-exact
  against the tensors throughout.
- **Controls:** every other page's 0v1 slice at stride 1 with
  `--check-tensor` (9 pages x 8 slices, 20,545,536 cells) and the Fly + Surf
  page's other 8 scenarios at stride 13 (64 slices, 1,577,472 cells) are
  integer-exact against the shipped tensors.
- **Certification:** `cramorant_certify.py --league both --selftest 5` on a
  scratch copy of the pages with the Fly + Surf page's 0v1 tensors patched
  to the recert (62,280 cells): 720 cells, 0 bar failures, 0 exemption
  violations, selftest 50/50 integer-exact (record kept in scratch only;
  the real record is written after the re-dive).
- **Tests:** `tests/test_cramorant.py` v8 block -- Jumpluff/Kingdra 0v1
  cells recover (pvpoke 199 -> 366 / 194 -> 364, rank1 194 -> 359 /
  191 -> 358; failing-first against 20d9f018970b), Araquanid pinned at
  plain 670 / 707 (an unconditional 3.0 gives 474 / 528), a UL Dive + Fly
  vs Lapras control (274, 424), and a gate unit probe.
- **Cache:** merged right after the farm-down port, so engine
  9f1947ee5614 -> 4b42f9d83690 (slayer 587f61940e6f -> 3a2ed21a79ce);
  predicate `cram_0v1_rule_r_20260928` (same affected set as
  `cram_0v1_surf_gate_20260927`), applied with `--from-engine
  9f1947ee5614` (see the migration line below).
- **Article:** the cheat sheet's 0-0/0-1 row gained the Surf-gulp rule text
  (v7 + v8), pending Michael's review; not re-rendered.
- **Still open:** apply the migration, Cramorant GL re-dive, certification
  record, article re-render, publish on Michael's go.

## 2026-09-28 -- DP farm-down insertion order ported to PvPoke's (engine bump)

- **What:** TODO "DP farm-down insertion order" (F2b of the 2026-09-27
  Aegislash diagnosis; Michael's call: port). PvPoke's DP inserts the
  farm-down state inside its per-move loop, ahead of each charged move's
  expansion; we inserted it once after all expansions. Now inserted once,
  before the expansions, in both `_dp_jit.py` (numba kernel) and the
  pure-Python loop in `battle.py` `pvpoke_dp` (once is equivalent to
  PvPoke's per-move copies: they are identical, any farm-down pop ends the
  search, and the ready-move dedup can never remove the farm-down state).
  The orders differ only on a same-turn tie with a ready move
  (`fm_to_ko * fast_turns == 1`: a 1-turn fast move whose single hit KOs),
  where PvPoke keeps farming. Ours had scored the thrower higher in the
  1v1 by denying the dying side its last fast move, but that was port
  order, not a defended deviation.
- **Effect:** 1080-cell Aegislash sample, both seats: 7 cells per seat
  move, all to PvPoke-exact on score and log (970 -> 977 exact), 0
  regressions: Blade vs Corviknight (1,1) 434 -> 444 and (1,2) 104 -> 114,
  Blade vs Kingdra (2,2) 173 -> 191, 4 Dunsparce log-only cells. Closes F4
  (Shield Air Slash vs Registeel (2,1): the trailing shielded Flash Cannon
  is gone, as on PvPoke). The 297-cell oracle audit is byte-identical to
  main's (277 exact, 20 documented, 0 new, 0 vanished); no existing test
  pin moved.
- **Pins:** `tests/test_farmdown_order_port.py`, four cells verified on
  PvPoke master 78b1e66db via `scripts/pvpoke_trace.js`, each failing on
  b82ca59 (pre-port values recorded in the test).
- **Hashes:** engine 20d9f018970b -> 9f1947ee5614; slayer 5dfdafc264f6 ->
  587f61940e6f.
- **Cache:** predicate `farmdown_order_20260928` (affected iff either
  side's fast move, or its form-change swap, is 1-turn; proof in its
  docstring). Dry run: sweep 155,610 blessed / 124,408 deleted; slayer 112
  blessed / 39 deleted. Not applied.

## 2026-09-28 -- Mirror population as opponent columns (bake ON, paragraph render-gated OFF; gate opened later that day, entry above)

- **What:** TODO.md "NEXT BAKE: mirror population" (Michael, 2026-09-22),
  built. After the main sweeps and before the blob is dumped, each dive
  computes the page's own builds (`deep_dive_builds.compute_builds`, the
  section's mode, league cap) and sweeps every moveset against the MIRROR
  POPULATION: PvPoke's top-20 IV rank list for the focal (plus the other
  shadow form's top 20 when the pool carries it) and each named build's
  most-winning member under every live preset plus SP1 (stat-product rank
  1), deduplicated, at explicit IVs and best level under the cap, with the
  pool's moveset for that form, both bait modes. Stored as
  `state['mirror_population']` (schema v1, int16 scores per arm,
  4096 x 9 x M); `--no-mirror-population` skips it.
- **Page:** "The mirror" paragraph under the builds table reads the
  population where the blob has one: per build, the share of the rank list
  its median member beats in the 1v1 (with the weakest member where it
  differs) and out-prioritises on CMP (charge-move priority, strict
  pre-shadow attack, the engine's rule), the rank list's a_50 / a_75 CMP
  cuts, and the same counts against the page's own picks, labelled
  separately. Blobs without the key keep the cohort paragraph, byte-
  identical. The page-picks sentence is dropped when the bake's tagged
  members are not the builds the render selects.
- **Guards:** every swept arm must carry SP1 and the rank list's #1
  (`PopulationGuardError` at bake time); the per-build numbers are pinned
  against an independent recount from the stored scores
  (`tests/test_mirror_population.py`); the vintage stamp gains the
  population's bake-time engine and gamemaster hashes (only when present).
- **Cost:** Melmetal GL, 5 movesets: 31 members, 224 column-sweeps, 39-47 s
  per dive on a loaded machine. Default ON.
- **Render gate:** `deep_dive_which_build.RENDER_MIRROR_POPULATION = False`.
  The as-built "Build 1 beats 0%" counts are true but hide that the bulk
  build TIES most of the rank list (bulk wins the Melmetal mirror) and that
  every population column carries the pool's moveset, so off-meta arms read
  a moveset loss as an IV one; the cohort paragraph renders until Michael
  settles the wording (TODO "NEXT BAKE: mirror population" (g)).

## 2026-09-28 -- Aegislash first-throw quirk documented as PvPoke #10 (docs + pins, no engine change)

- Shield-start Aegislash's first Shield-form throw: PvPoke's persisted
  clause-4 stamp kills shuffle clause 1, so its slot 0 is the input order;
  ours picks the higher-damage move (52 log-only + 5 score cells in the
  1080-cell sample, ours ~+100 for Aegislash in all 5). Not ported
  (DEVELOPER_NOTES "PvPoke bugs found" #10). Pinned by two Aegislash-S vs
  Moltres-G audit rows (9 xfail cells + a 9/9-exact GB-first control;
  audit now 297 cells, 20 documented, 0 new) and two tests in
  `tests/test_form_change_oracle.py`. The F2b farm-down insertion-order
  port gap is a TODO decision item.

## 2026-09-28 -- In-hash dead-code removal, fully-blessing bump (1a05c60)

- **What:** the in_hash=true items from the 2026-09-25 cruft scout that
  re-verified as zero-caller: battle.py unused imports
  `type_effectiveness`/`stab`, `pvpoke_shield`, unused locals `best_idx`
  (pvpoke_dp) and `n` (_ensure_dp_cache), the always-False
  `_resolve_charged(allow_dead_attacker)` parameter; the unused
  `fast_damage` parameter of the numba near-KO kernel (`_dp_jit.py`);
  `pokemon._LEVEL_CAP_EXCLUSIONS`; plus the orphaned "deferred charged"
  comments.
- **Kept (have readers):** `use_first_available` (test_battle,
  test_cramorant, test_new_turn_mechanics), `BattlePokemon._form_is_alt`
  (test_mimikyu_starts_busted); the `compute_default_ivs` chain and the
  legacy-mechanics branch were out of scope (product decisions).
- **Neutrality proof:** battle tier green; `audit_oracle_harness.py
  --mechanics new` byte-identical to main (279 cells, 268 exact, 11
  documented, 0 new, 0 vanished); 60 stratified cached sweep columns
  (GL/UL, shadow/non-shadow both sides, pvpoke/pogodives, bait/nobait)
  re-simmed at every stored IV row: 60/60 score and energy planes exactly
  equal (2,211,840 cells); profile_slayer A/B within noise.
- **Cache:** engine 45cf73a2d23d -> 20d9f018970b, slayer 0c54e07bc21b ->
  5dfdafc264f6. Migrate warm with `migrate_cache.py --from-engine
  45cf73a2d23d --predicate inhash_deadcode_20260928` (and `--slayer
  --from-engine 0c54e07bc21b`); dry-run: 280,018 columns and 151 slayer
  entries blessed, 0 deleted.

## 2026-09-27 -- Shield-form Aegislash prices charged moves at the Blade atk (03993a4)

- **Symptom:** six Aegislash x Azumarill oracle cells open since the 09-09
  new-mechanics re-baseline, same winner, 50-142 rating points apart:
  `aegislash_vs_azumarill` (1,1) 564 and (2,1) 550 vs PvPoke 618;
  `aegislash_blade_vs_azumarill` (1,0) 570/429 vs 712/287 and (2,0)
  580/419 vs 655/344; `azumarill_vs_aegislash_shield` (1,1) 435/564 and
  (1,2) 449/550 vs 381/618. Framed for weeks as an open turn-system
  question ("farming in Shield is the species' gimmick", mechanics_notice);
  it was an engine bug on our side.
- **Root cause:** every Shield-form charged throw changes form
  (`activate_charged`) before damage resolves, so it lands with Blade stats,
  and PvPoke's estimate knows it (`DamageCalculator.js:43-50`). Our
  `_ensure_dmg_cache`, `_ensure_dp_init_cache` and the buff-delta stage
  rows priced charged moves with the Shield atk: Shadow Ball / Gyro Ball
  estimated at 44 / 39 vs Azumarill, dealt 91 / 81. The farm gate, the DP
  plan and bandaid[918] all read the estimate, so our Aegislash farmed past
  a guaranteed KO, bled 15-30 HP more and twice burned a shield for
  nothing. A gate-only fix moves 0/6 cells (gate + bandaid[918] gives 6/6
  scores but 0/6 logs -- score coincidence); the fix has to live in the
  caches. It became six cells on 09-09 because PvPoke's SHADOW_BALL 100 ->
  90 (2ab0fc395) moved Azumarill's HP into the window between the two
  estimates; b0c4fb0 was right that the nerf does not change move
  selection, but it was the trigger.
- **Fix:** `BattlePokemon._charged_atk_base`, one helper for all three
  sites: when the current form's trigger is `activate_charged` (only
  aegislash_shield) charged moves use the target form's atk; fast moves and
  every other form/species are unchanged. Estimate pin: [44, 39] ->
  [91, 81], and equal to the dealt damage at atk stage -1 ([73, 65]). All
  six cells now match PvPoke on score, winner and chargedLog; failing-first
  verified against main's battle.py (7 failures).
- **Stage decision (deliberate divergence):** we apply the current atk stage
  to the Blade atk; PvPoke uses the raw, stage-blind Blade atk although its
  own throw applies the stage. The diagnosis expected this to be
  oracle-invisible; it is not. Against atk debuffers it decides 15/1080
  sampled cells (4 winner flips, 3 in Aegislash's favour under ours, net
  +209 rating to Aegislash) and three `cradily_vs_aegislash_blade` oracle
  cells, now pinned at our value (DEVELOPER_NOTES "Form change gotchas" 6,
  docs/pvpoke_divergences.md item 7).
- **Measured:** full oracle audit 243 cells, 8 documented Morpeko
  divergences, 0 new, 0 vanished (was 14 diverging). Four new non-Azumarill
  Aegislash opponent rows (69b9212: Electrode-H, Mimikyu, Clodsire, Cradily;
  pre-fix 8/36 diverged incl. 4 winner flips): 33/36 exact + the 3 Cradily
  stage cells; 279 cells total. 1080-cell sample (Shield + Blade 4/14/15 vs
  top-60 GL at 15/15/15, 9 scenarios, both seats): matches PvPoke on
  score+winner 887 -> 1035 (1050 with PvPoke's stage-blind variant); 153
  cells move, 149 onto PvPoke; 8 winner flips, all to PvPoke; 1 cell that
  matched before no longer does (Shield vs Cradily 2-2, the stage choice).
- **Cache:** engine 32a20be48379 -> 45cf73a2d23d (slayer 9b90c8d8b434 ->
  0c54e07bc21b; includes 654061d, a comment-only rewording of the stale
  "EXPERIMENTAL / UNVALIDATED" mechanics='new' header). Predicate
  `aegislash_blade_atk_20260927` (89cb264): affected iff either side's
  species starts with Aegislash (Blade starts revert to Shield; the other
  side's would_shield / TTL read the Aegislash's estimates); slayer mirrors
  iff the scenario species does. Both Aegislash GL dives and every GL dive's
  Aegislash opponent rows were baked with the bug.
- **Cleanup:** `scripts/mechanics_notice.py` deleted with its call sites and
  the tests that pinned its wording (24971d9); the stale blade xfails
  {(1,1),(1,2)} cleared (69b9212).
- **Brief caveat stamp retired:** `scripts/deep_dive_brief.py`
  `CAVEAT_SPECIES` is now `()` (branch `swing/retire-aegislash-caveat`), so
  Aegislash cells no longer print "(engine divergence vs PvPoke)" and
  re-enter the floor, the rungs and the cost totals from the next bake (the
  brief is recomputed from the blob whenever `deep_dive.py` renders a page;
  published pages keep the stamp until then). The G-caveat machinery
  stays for the next documented divergence; its tests now pin it on a
  monkeypatched species. Furret GL arm 4 pre-fix: 3 cells excluded, 4
  divergence mentions; post-fix 0 / 0 with an Aegislash rung printed.

## 2026-09-27/28 -- Great League re-dive for the Aegislash fix (GL only, 3.5 h)

- 76 GL dives in 209 min under `run_website_dives.py great` + `caffeinate -is`,
  data cache pinned (same 76: 494 min on 09-26, ~20 h on 09-20). Only the
  two Aegislash columns per dive were cold after the
  `aegislash_blade_atk_20260927` migration, so each dive was its render.
  Ultra pages not re-dived (no Aegislash in that pool; Cramorant UL already
  at sheet v7). Tail steps by hand; Cramorant certification 720 / 0 / 5-of-5
  exact; record check OK; ship gates green (2883 passed). Aegislash pages
  carry no divergence stamp. Awaiting Michael's publish go.
- Chain note: without `PYTHONUNBUFFERED=1` the dive runner's banners are
  block-buffered; read per-dive logs for progress.

## 2026-09-27 -- PoGoDives sheet v7: Surf-normalized 0v1 dive gate (dfebbd8)

- **Finding:** the post-bake Cramorant certification (owed since 09-20, run
  after the 09-26/27 bake) showed 8 bar failures, all one cell: GL page
  PECK / FLY, SURF, start 0v1, vs plain Araquanid -- PoGoDives tier -1,971
  net wins / -155.7 mean vs plain; 3,214 of 4,096 spreads worse, none
  better. Not a regression: that page did not exist before the 09-20 bake
  (a85d62e regenerated the GL opponent pool on 09-17, the top-20 screening
  set changed, and Fly+Surf edged out Hydro Pump+Surf by 1.2 points), so it
  had never been certified.
- **Mechanism:** row (0,1) 'cmp' raises the Dive/Surf-ASAP DPE threshold
  from 1.5 to 3.0 when Cramorant wins CMP. 3.0 was fitted to Fly vs DIVE
  (neutral ratio 1.42: one type step ~2.28 admitted, two ~3.64 excluded).
  With SURF the neutral ratio is 1.07, so two steps (~2.65-2.75: Araquanid,
  Jumpluff, Kingdra) were admitted untested; vs Araquanid the tier throws a
  resisted Surf into a kept shield and eats two Mirror Coats.
- **Fix:** row (0,1) gains `surf_gate_dpe: 2.25` (3.0 x 1.07/1.42), read
  by `_cram_dive_gate_dpe` only when the gulp move is SURF; Dive pages are
  byte-identical by construction. Stride-1 recert of all 8 changed slices:
  pvpoke +11 net / +10.49 mean, rank1 +0 / +13.30 (bar PASS); 24 control
  slices (GL/UL Dive+Fly, UL Hydro Pump+Surf, stride 13, --check-tensor)
  reproduce the shipped tensors exactly. Accepted cost: Jumpluff and Kingdra
  fall back to plain at 0v1 (about -165 rating on fights Cramorant loses
  anyway, 0 flips; page mean +12.5 -> +10.5). Tests in
  `tests/test_pogodives_v6.py` (plain 720 / shipped 551 / fixed 720, a Dive
  control, a field-scope probe); failing-first verified.
- **Cache:** engine 5a813036625c -> 32a20be48379 (slayer d3ce425c2ce4 ->
  9b90c8d8b434); predicate `cram_0v1_surf_gate_20260927` -- affected iff a
  pogodives column whose focal is Cramorant with SURF plus a non-Dive,
  non-Surf charged move; slayer fully blesses.
- **Guard:** `cramorant_certify.py --out` now records every certified
  page's sha256; `--check-record REC.json` exits 1 if any rendered Cramorant
  page is missing from, or differs from, the record, or the record is not
  clean -- so a page that enters through the moveset screen can no longer
  ship uncertified. Wired into publish_website.sh's gate section.

## 2026-09-27 -- Sweep-side rank-1 IV memo (ea32bd9), no CACHE_VERSION bump

- `deep_dive_lib.opponents.resolve_opp_ivs` is memoized per process
  (species, league, shadow, base opp-IV mode; cleared by
  `gopvpsim.invalidate_caches()`); the render-side memo from R1 (dc34ab0)
  is removed as redundant. Michael reversed the 09-25 Q2 ruling on 09-26:
  no CACHE_VERSION bump, because the function is parent-side and
  `tests/test_resolve_opp_ivs_memo.py` proves output identity over all 104
  pool species x both modes x both shadow states plus column-key identity.
- Measured (Miltank UL smoke dive): rank-1 sweep setup 3.9-4.1 s -> 0.13 s
  for every sweep after the first in a dive; ~2-2.4 h per bake off the
  single-core column. Replay renders byte-identical to the 09-27 baseline.

## 2026-09-26/27 -- Bake on the sped-up render layer: 2.0x awake, 2.8x single-core

- **Chain** `overnight_20260926_102139.log`, launched 09-26 10:21 after the
  pre-dive checklist (smoke dive, pools fresh, gamemaster stamp matching
  every cached column, engine 5a813036625c), SUCCESS 09-27 16:37. Every
  morning-check gate green; the new sleep check red by design (12.1 h of
  battery sleep, resolution recorded in docs/chain_resolutions.toml).
- **Measured, like-for-like over the same 136 dives, sleep subtracted:**
  35.9 h -> 17.9 h awake (2.01x). Single-core (the layer R1-R4 targeted)
  19.0 h -> 6.9 h (2.76x); pool sims 16.9 h -> 11.0 h (1.53x, cache hit
  61% -> 72%). Great League 2.44x, Ultra League 1.64x (its pool only 1.16x:
  the 42,594 self-debuff columns unlinked by the 09-25 migration re-simmed
  here and are warm now). Ship-gate step 885 s -> 317 s (concurrent roster);
  ML tail 204 s.
- **Cramorant certification (owed since 09-20, run now):** 8 bar failures,
  all one cell -- GL PECK / FLY, SURF 0v1 vs Araquanid, PoGoDives tier
  -1,971 net wins / -156 mean vs plain across all 8 slices. Byte-identical in
  the 09-20 tensors, so it predates this bake and the 09-25 engine change;
  Michael's call (strat sheet / exemption / page).
- **Process:** "charger connected" added to the pre-dive triggers
  (caffeinate cannot hold off sleep on battery).

## 2026-08-31..09-25 -- Worlds 2026 post-event: publish path unblocked; code dormant until 2027

Closed out of TODO's post-Worlds checklist 2026-09-27.

- **08-31 (Michael):** the Worlds surfaces retire with the Twilight Trails
  site update. `verify_worlds.py` left the ship-gate roster (5985777) -- it
  failed from main on all six gamemaster stamps and, the roster being
  shared, blocked every publish path; the publish-time Worlds re-render
  became opt-in (`WORLDS_RERENDER=1`). The pinned `gopvpsim-worlds` worktree
  was removed after its one delta (`scripts/worlds_meta.py`) was verified
  byte-identical to main. The `.cards_rerender_pending` sentinel set that
  day (L51 dead-tooltip fix 061d93c; the cup banner's false "dated archive"
  claim) cleared with the September full re-renders.
- **09-10:** the three Worlds artifact tests marked dormant, not broken
  (066e528). **09-20:** the deferred cmp_atk 1-ULP shadow-tie fix landed on
  its own hash bump (ebf5944; pin now
  `test_cmp_shadow_roundtrip_artifact_no_longer_reaches_cmp`). **09-22:**
  nothing is hardcoded to legacy mechanics, Worlds included (4b6342b).
- **Aegislash rebake question: moot.** Cramorant was not Worlds-legal
  (eligible 09-01), the surface retired, and Aegislash was fixed and rebaked
  site-wide (CHANGELOG 2026-09-12/15).
- **09-25 (Michael, perf-doc Q4):** do NOT execute the retire/delete pass;
  the Worlds code stays dormant until 2027. The pages are off the live
  site (absent from `userdata/website/`, which publish rsyncs with
  `--delete`); the exact publish that removed them is not recorded. Open
  residue stays in TODO.

## 2026-09-25 -- Moltres-G near-KO plan: match PvPoke (engine bump d78c67fd06a7 -> 5a813036625c)

- **What changed:** the `_cached_damage` memo that our port of PvPoke's
  post-DP bandaid[866] ("shields down, prefer the non-debuffing move")
  reads is now refreshed at every point PvPoke refreshes `move.damage`:
  battle start (`simulate`, mirroring Pokemon.reset -> resetMoves ->
  initializeMove), `_optimize_move_timing` for BOTH sides' moves with no
  energy gate (ActionLogic.js:320/336), `would_shield` (:1159), and the
  form-changer's moves in `apply_form_change`. Until now the OMT
  assignment sat inside the affordability gate, so an unaffordable
  self-debuffing nuke kept no memo and the bandaid silently skipped --
  the Moltres-G "single Brave Bird instead of a Fly chain" divergence
  documented 2026-04-15 as intentional.
- **Why now:** the keep-our-plan rationale (ours retained 23-30pp more
  Moltres-G HP in 6 of 7 cells) was measured under the legacy turn
  system; the 2026-09-09 re-derivation under the new turn system
  reversed it in every cell (PvPoke's plan +72..+129 for MG, Lapras
  [1,2] still a winner flip against us). Surfaced by the 2026-09-25
  test-cruft pass; Michael: "do what's consistent with the new turn
  system".
- **Verification:** 243-cell oracle audit vs PvPoke master: the six
  Moltres-G cells VANISHED as divergences (score + chargedLog exact),
  nothing else moved (8 Morpeko documented, 6 Aegislash open, as
  before). `tests/test_battle.py::test_moltres_g_nearKO_plan_divergence_pinned`
  pins PvPoke's values and fails on the old engine (531/670/670,
  580/689, 482). Benchmark `profile_slayer.py --n-focal 60 --n-opp 20`:
  5,846 -> 5,800 sims/s (noise).
- **Kept deviation (both-self-debuff movesets):** with the memo live,
  PvPoke's bandaid also fires on movesets whose charged moves are ALL
  self-debuffing (Lurantis Leaf Storm + Superpower, Blaziken Brave Bird +
  Overheat, Braviary ML Close Combat + Brave Bird), swapping the DP's nuke
  for a worse-typed self-debuffing move and losing fights we win -- the
  cluster the 2026-06-28 review decided to KEEP (re-upheld 2026-09-09
  under the new turn system). The fast tier caught it (three pins in
  `tests/test_both_self_debuff_divergence.py` moved to PvPoke's values).
  Our bandaid[866] now requires the swap TARGET cms[0] to be
  non-debuffing -- the rule's stated intent -- so those pins hold at ours
  (613 / 646 / 695) and the Moltres-G cells still match (Fly is
  non-debuffing). One clause, reversible; flagged for Michael.
- **Cache:** engine hash bump; predicate `cached_damage_refresh_20260925`
  (self-debuff-either-side: bandaid[866] can only fire when the acting
  side's DP-chosen first move is self-debuffing, so a column is provably
  unchanged iff neither side owns one; same Zap-Cannon-mutation caveat
  as `self_debuff_either_side`, measured harmless 2026-07-03).

## 2026-09-23..25 -- Signature dedup made exact (a4ca14e); migrations applied

- **Found 2026-09-23** by the statfx lab, which re-sims plain PvPoke for every
  cell it touches: on 25 of 165 class pages (engine 9ac12a2754a1, the bake
  stamp) 1-92 cells per page (~0.01-0.1%) did not reproduce, e.g. Florges GL
  vs Shadow Annihilape (an exact-CMP-tie spread's score rows swapped) and
  Zygarde (Complete) UL vs Mimikyu (1044 1v1/2v1 = 325/337 vs 400/414).
- **Root cause (a617f98):** `deep_dive_signature.py` dedup was not exact.
  Dedup ON reproduced the tensors, OFF (per-profile truth) did not: 396 /
  774 / 6 cells on Florges, Zygarde, Blastoise UL vs Forretress. Two gaps:
  (1) the CMP column divided shadow attack by 1.2 -- the lossy round trip
  ebf5944 had removed from the engine -- so exact CMP ties vs a shadow side
  were signed win/loss; (2) `movable_axes` missed the attack axis that
  `pvpoke_dp`'s `_cm_buff_delta` moves for a chance-1 opponent-DEFENSE
  debuff (Sand Tomb, Bulldoze), so `atk*1.25/def` vs `atk/(def*0.8)` floored
  differently at rare boundaries.
- **Fix (a4ca14e):** `cmp_atk = (base atk + atk IV) * CPM` like the engine's
  `raw_atk`; def-debuff charged moves make the owner's atk axis movable.
  Failing-first tests on the three pairs; two pins that encoded gap 2
  corrected with pre-fix values recorded. Dedup ON == OFF on all three
  pages; `verify_signature_dedup.py` default corpus EXACT MATCH.
- **Cache:** the signature module is in the sweep engine hash, so the hash
  moved 9ac12a2754a1 -> d78c67fd06a7 (every column a safe miss). Predicates
  (b6e369a): `signature_regroup_20260923` (old grouping rebuilt from a frozen
  pre-fix module, matched 1,504/1,504 sampled columns) and
  `signature_fix_slayer_20260923`; the unsafe `legacy_guard_20260922` was
  removed unrun. Applied by hand 2026-09-25: sweep 239,091 blessed / 43,077
  unlinked, slayer 150 / 0 (docs/perf/2026-09-25_bake_attribution_and_cruft_scout.md
  "Results"). The corrected tensors reached the site with the 2026-09-26/27
  bake and the 2026-09-27 publish.

## 2026-09-22 -- Three TODO items closed: Sableye GL bands, ml_tail ETA, --mechanics comment

- **Shadow Sableye GL "the bands are wild"** (reminder 2438093, 09-11):
  answered from the published page, no re-sim (034646c). The 0v1 band is
  the CMP (charge move priority) line against a PvPoke-default Annihilape
  4/13/13 at 148.10 attack, 2220 of 4096 spreads, 100% rule accuracy,
  named both in "Which one to build?" and in the Matchup clusters table.
  The plain page cuts at 123.42 (123.419 x 1.2 = 148.104), so both forms
  flip the same 2220 spreads and both pages say so. Scope: this settles
  "does the analysis capture the 0v1 bands", not what Michael meant by
  "wild" (unelaborated; reopen with the specific reading). The
  band-crosser glossary gap stays open in TODO.
- **ml_tail ETA:** self-calibration from `run_iv_guides.py`'s own
  `Done in` line landed 3c299aa (09-12,
  `overnight_eta.measured_ml_tail_min()`), but the fallback constant
  stayed 420 min, so a machine with no ML history still printed a phantom
  ~7 h. 399ae72 set it to 10.0 (3.9 min measured for 60 guides on 09-12,
  ~2.5x headroom), put `ML_TAIL_MEASUREMENT` beside it, and pinned the
  fallback within [1x, 5x] of it in `tests/test_eta_and_timing_report.py`
  (fails on 420).
- **`--mechanics` comment:** the help string was fixed 79ecb48 (09-12;
  "DEFAULT IS new ... 237 of 243"), but the `warn_mechanics` call-site
  comment still called legacy the default. Fixed 2ecac26 with
  `test_no_comment_names_the_wrong_turn_model_as_the_default` (tokenize
  scan that joins contiguous comment lines into blocks -- the stale claim
  straddled a line break -- plus a positive control on the pre-fix text).
  `battle.py`'s "UNVALIDATED" comment is engine-hashed and waits for a
  bump (TODO).

## 2026-09-12..22 -- Build brief -> "Which one to build?" v4, published

Closed out of TODO's "BUILD BRIEF (2026-09-12)" section 2026-09-27.

- **Build brief:** standalone compute core + renderer + tests (b6e6263, v2);
  v3 floors on Def and HP with bulkpoint mechanisms (d65c509; acceptance
  cases Altaria Def >= 148.29 vs 2v2 Clodsire, Furret Def >= 102.06 vs 1v1
  Lapras). Michael 2026-09-12: split placement (D11; superseded by v4's
  one-section, answer-first layout, 94c201e), retire the flavor badge +
  catch phrase (D10, still open in TODO), Cramorant first (done, entries
  2026-09-12/15). Named "Which one to build?" 2026-09-13; merged
  with the all-scenario matchup clusters 09-15 (9b5e86d).
- **Analyses:** spread sets (2026-09-15; 108 dives / 448 arms / 7944 named
  sets; two-/three-stat structure in 88% of arms but only 1.8% of decision
  cells after the materiality bar; the explicit list stays the primitive)
  and the builds lattice (2026-09-16; 993 builds; best region beats best
  single set by a median 6 guaranteed cells; 79% of arms name a fork).
  Reports in `~/coding/reports/` (spread-sets 09-15, builds-lattice 09-16).
- **v4:** the section shows 2-3 BUILDS (primary / fork / rank-1 region)
  with a three-preset Build-criteria knob (a06a74f, d9fbb09; review rounds
  2-10 through 65e78cc), merged cfbbb98 (09-20), live since the 2026-09-22
  publish of the 2026-09-20 bake. Rankings-vintage drift found on the way (9adc094: tests
  freeze `tests/fixtures/pvpoke_rankings_20260908.json`); the chain pins
  the data cache for the whole bake (88bec7b). The Cramorant hand-off rules
  (local clone, no engine edits during a bake) were followed and the clones
  deleted 09-22.

## 2026-09-15 -- Cramorant close-out: merges + cache migrations (re-dive deferred)

Michael: "Do the first four, don't do the redive." Merged in one pass:
0afbf6b (Aegislash fix), 1374a70 (predicates), 8a8afcd (v6), 9b5e86d
(scenario clusters + "Which one to build?"); engine e4d380ec3e5e ->
1436a17ffbb2 -> 36037e51a2ee, fast tier green after each engine merge.
After a hardlink snapshot (`sweep_pre_aegislash_20260915`, slayer
likewise): `form_change_either_side_20260912` (235,768 blessed / 25,320
re-sim; only Blade columns actually moved), gamemaster 51dfa745457a and
66b3cba2840d -> 9de08819ae0f (0 further deletions), then
`pogodives_sheet_v6_20260912` (all blessed). f783255 fixed
`--from-gamemaster` ignoring `--slayer`; 129 slayer entries migrated.
**Gamemaster-vintage swap recipe:** the 09-12 rebake was launched with
`run_website_dives.py` directly (no TTL keeper), so the live gamemaster
refreshed mid-stream; engine and gamemaster migrations deadlock (each skips
columns whose other stamp is not current). Resolved by writing each old
gamemaster blob (from `../pvpoke` history) into
`~/Documents/gopvpsim_cache/gamemaster.json`, running the engine migration
per vintage, restoring the live file, then running the gamemaster
migrations. The re-dive was deferred behind Michael's cluster review; the
2026-09-20 full chain followed.

## 2026-09-12 -- Aegislash (Blade) reuse leak found + fixed; Cramorant sheet v6

**Engine bug (found 09-12, fixed 2e8d36b):** Aegislash (Blade) columns
were contaminated across battles on a reused BattlePokemon pair (sweep,
slayer, robustness and joint-IV workers reuse one pair across the 9
scenarios). Priority-shuffle clause 4 (`aegislash_shield`, 9fe11e2) stamped
the shared charged-move dicts in place and `reset_for_battle` never undid
it; and a fight ending in Blade skipped the form swap on reset, so
`_dp_init_cache` / `_dp_cache` were never invalidated. Found because
`cramorant_mini_sweep.py` (fresh pair per cell) disagreed with the tensor
on one cell (500 vs 490). Blast radius: 8803/36864 cells (24%) of the
Cramorant-vs-Blade column; every column of the Blade focal dives; 75 of 140
dive dirs carried a Blade column. Fix = snapshot + restore of the stamp and
unconditional DP-cache invalidation for form-changers; failing-first test =
the `aegislash-blade-azumarill` param of
`test_reset_for_battle_reuse_matches_fresh`. Merged 09-15 (entry above).

**Sheet v6** (8a639e2; record `docs/validations/2026-09-12_cramorant_deep_vet.md`):
(1,0) terminal-KO guard, (2,2) last-shield chip guard; stride-1
re-certification of the changed rows 90/90 PASS on 09-15 (net 937,116 ->
931,522, -0.6%; the four failing GL cells fixed; fbbc213). Render side, no
hash impact: computed + page-verified article showcases (6f79ab9, 258e11b),
instruments (9dd51f5, c926558), lab loader fix (dcf33a1), docs (491f819,
0397089).

## 2026-09-10..12 -- Cramorant: rebalance re-verify, deep re-verification, stale-article audit

Closed out of TODO 2026-09-27 (every thread below finished with the sheet v7
re-dive, re-certification and article re-render, entry 2026-09-27).

- **Rebalance re-verify (09-10):** sheet v5 FAILED the bar under the new
  move data (d492963): UL 2v1 -1.325 mean (all Jellicent), UL 0v1 -2 win
  cells (Dondozo). The LEAD constant is inert (460a63e: lead 30-45 vs static
  differ in 12 of 2,394 cells). Fix option A: (2,1) re-exempted (f116674);
  the UL 0v1 -2 is pre-existing, byte-identical under legacy and new
  mechanics and against the June pool (8c5c219) -- a standing dive-early
  cost, kept as the one accepted exception (the 09-12 full-resolution read
  then found the -2 was a single-spread artefact of the PvPoke-default IV
  run). Writeup:
  `docs/validations/2026-09-10_cramorant_strat_reverify.md`.
- **Deep re-verification (09-12):** instruments `cramorant_certify.py`
  (strict bar over the full 720-cell grid from the dive tensors;
  `--selftest N`) and `cramorant_mini_sweep.py` (`--check-tensor`,
  coprime `--stride`) plus a changed-row recert driver (9dd51f5, c926558).
  First full-grid read 716/720; the 4 failures (GL Peck/Hydro Pump+Surf 2v2
  nobait, Corviknight-driven) led to sheet v6 (entry below; stride-1 15/15
  priority slices fbbc213, 90/90 changed rows 09-15).
- **Live article stale (09-12 audit):** the four hardcoded 08-27 sandbox
  links replayed differently after PvPoke's post-charge cooldown (Twilight
  Trails merge acb3ce461), Jellicent's 2-1 premise died with Shadow Ball
  100->90, Blastoise's default moved Rollout -> Bite, and every number on the
  page was a legacy-clock value. Fixes: showcases computed and page-verified
  at render time (6f79ab9); `verify_url` emulates pvpoke.com's double run of
  a sandbox link (`hasActed` survives `Pokemon.reset()`, PvPoke Report 9
  drafted, 491f819) and the encoder shifts by DISTINCT prior resolved turns,
  not charged-action count (17/17 same-turn-pair cells had been mis-encoded;
  258e11b); the policy lab's GL pool loads again (dcf33a1). The article was
  re-rendered from rebaked new-clock pages 2026-09-27; its fixed prose pass
  stays open in TODO.

## 2026-09-11..12 -- Moveset rules merged; dives-only rebake

Michael 09-11: the old movesets, meta and mechanics are dead; "bake" means
"bake with a legit set of moves". Rules in `scripts/dive_registry.py`
("MOVESET RULES"; e7342f2, built in a separate clone during the 09-10
bake, merged b80f93e 09-12): every dive renders `DEFAULT_TOP_MOVESETS` (5)
screened movesets (the 42 per-slug overrides are gone; Sableye had 1 and
Shadow Sableye 4, sharing none); PvPoke's default moveset is always a page
(`--reference auto`); shadow/plain pairs render the UNION of both forms'
screened sets (`pair_partner` / `--union-with-form`). Pinned by
`tests/test_dive_registry_movesets.py`. The 2026-09-10 bake was held
unpublished as the warm-cache baseline and a dives-only rebake with the
cache on launched 09-12 18:02; it did not publish as-is (the Aegislash
leak, 2026-09-12 entry, went first) and the 2026-09-20 chain superseded it. The
fast-tier red `test_entry_points_route_through_the_roster` (tripped by
`publish_website.sh --partial`, 986cc01) was fixed by 0af9da4 (`--exclude`
routes `--partial` through the roster). The dead
`forretress-shadow-volt-switch-great-league` registry entries came alive
when a85d62e (09-17) brought Forretress (Shadow) into the GL pool (29913bd).

## 2026-09-09..10 -- Turn system: PvPoke master merge, default flip everywhere, re-baseline

- **09-09:** PvPoke shipped mechanics + moves + rankings to master
  (5ca1b89): master `src/js` byte-identical to twilight-trails, tripwire
  fired on Battle.js only; 29 moves / 105 pokemon changed. The gamemaster
  cache migration was moot (never baked under new). Re-measure vs master
  (1211b0a; raw `docs/validations/2026-09-09_oracle_new_vs_master_raw.txt`):
  223 exact + 14 documented + 6 new, all one Aegislash x Azumarill
  form-change cluster (open in TODO); SHADOW_BALL hypothesis killed
  (b0c4fb0). Default flipped to new everywhere, `simulate()` and the audit
  harness included (7e6a82b): seven scripts had silently inherited legacy.
- **Re-baseline:** the pull left 102 fast-tier failures in 19 files (pinned
  scores, loud rather than rotting); oracle pins re-derived against PvPoke
  in tranches f9923e0, fa7d801, 935c38b, d7e9e26, c01aa6a, 5e19bc5,
  540ce46, 67da3d2. Pools rebuilt against post-rebalance rankings with the
  ItsAxn augmentation (f92bec1 + follow-ons). Threshold TOMLs re-vetted as
  inputs: 58 derived stat-cutoff spreads archived, 15 IV-list spreads kept
  (d363b1d); of the cd_prep blocks, Oinkologne's retired 3f28221 (08-27),
  Thievul's rides the Worlds checklist, Baxcalibur's is a deliberate
  hypothetical. Tripwire re-vetted per checklist section B and re-pinned
  (4407c01; 229 exact + 8 documented + the 6 Aegislash cells). The cold
  bake under new followed (2026-09-10/12).
- **09-10 also:** sandbox-link encoder turn-clock fix (e6827a0; PvPoke's
  post-charge cooldown, auto-fired Gulp Missile excluded; refined 258e11b
  to one cooldown per round); Worlds artifact tests marked dormant
  (066e528); the "dead" pogodives constants were found deliberately kept
  (synthetic-row tests in `test_pogodives.py`) and their removal reverted.
- **Follow-on:** slayer follows the engine's mechanics (36b10da, 09-20);
  `simulate()` refuses legacy unless `GOPVPSIM_ALLOW_LEGACY_MECHANICS=1`
  (2615c6e, 09-22); nothing hardcoded to legacy (4b6342b, 09-22).

## 2026-09-02..03 -- Turn system: new-mechanics A/B, product-CLI default flip, re-port

- **09-02:** the legacy turn system left the live game. Our
  `mechanics='new'` disagreed with PvPoke's unmerged branch on 104 of 243
  oracle cells (5f16035; `docs/validations/2026-09-02_new_mechanics_oracle_ab.md`),
  45 of them from PvPoke's own "for now" revert 442a4afe8 (39dab5d). Both
  disk caches keyed on `mechanics` (32400af); both models print a CLI
  caveat (e5ec153, `scripts/mechanics_notice.py`); product CLIs default to
  new (2228cff; Michael: "It is literally impossible to play an actual game
  with the old turn system now"). Decision: wait for the merge, do not
  chase `origin/twilight-trails`.
- **09-03:** a Caleb Peng breakdown of the live game
  (`docs/validations/2026-09-03_new_turn_system_ground_truth.md`) gave
  swaps > charged > fast within a turn; the re-port resolves charged moves
  the same turn ahead of fast landings: 104 -> 1 mismatch, legacy control
  still 0 (f1ff911).

## 2026-09-02 -- PvPoke mega drift re-vetted; stale opponent pools now hard-fail a bake

Michael pulled `../pvpoke` (master 7b96d91fb -> 56bc6a8b1) and the
PVPOKE-ENGINE tripwire fired as designed (Pokemon.js, DamageCalculator.js,
ActionLogic.js drifted from 78c64048a), blocking `verify_tests` and so every
ship gate. Upstream: 574aeb0da third charged attacks + Mega Bonus damage
multiplier, bd8c5d889 Mega Level select, feba66f47 Super Mega tag with
default Mega Level 4, e86688bd1 mega rankings. Our engine never had an
`n_cms > 2` guard (every occurrence is `n_cms > 1`), which is why a 3-move
build used to run silently wrong; the downstream third-charged-move
plumbing landed the same day (1b2290c). Re-vetted per `docs/rebalance_checklist.md` section B
and re-pinned 420d829 (`docs/validations/2026-09-02_pvpoke_mega_revet.md`):
not a rebalance (moves.json byte-unchanged), oracle 208+35 -> 222+21; the
pre-rebalance baseline pin (46bd08a77 / c431557dcc76) unaffected. Re-pinned
again 4407c01 (09-10, entry above); green on the 09-20 pre-dive grid.

Same day, the opponent-pool gap: `build_opponent_pool.py` appeared in zero
of `overnight_redive.sh` / `run_website_dives.py` / `publish_website.sh` /
`phase2_preship.sh`, and `gl_top50_plus_cs.txt` was still stamped
2026-06-10. Pools are the INPUT to every dive and a new member is a new,
un-migrate-able column, so a season-start bake against stale pools was
silently wrong everywhere. Recorded c70ad94, fixed e8ac919:
`run_website_dives.py` runs `verify_opponent_pools` as a preflight and
hard-fails on DRIFT / MISSING / ERROR (`--allow-stale-pools` overrides). The
season lifecycle policy recorded with it stays in TODO.

## 2026-08-27 -- L51 dead-tooltip fix + build_collection_data() strong pin

Closing the "[render, unchecked] L51 tooltip registry" follow-up
found the suspected bug class absent (the registry is text-keyed and
dumped after the L51 render -- now pinned by a completeness test) but
a REAL adjacent bug present: the tooltip hydration pass cannot see
into inert <template> content, and setBestBuddyLevel swapped
templates in without re-running it, so EVERY tooltip on the
best-buddy L51 half of every shipped dive page was dead (760 on the
Cramorant dive). Fixed 061d93c (window.ddPopulateTooltips re-run
after the swap; render-only, no engine-hash impact); shipped pages
need a re-render at the next publish. Same day (7c7d5ab): the
2026-06-28 Option-1 maxLevel strong pin landed --
build_collection_data() extracted with 4-league / call-time /
key-order pins, byte-identical replay-render verified, and the two
remaining literal 51.0 ceilings in deep_dive.py routed through the
single source.

## 2026-08-27 -- Article-slug durable home (thresholds/cramorant.toml)

The Cramorant dive->article link no longer depends on a
replay-injection wrapper (83cc3c0): `[Cramorant.article] slug` lives
in a structural-minimum thresholds/cramorant.toml; deep_dive.py
resolves it on the --no-thresholds path AND as a render-time fallback
when a replay blob carries an empty slug, so both a plain CLI rebake
and a blob re-render emit the link (gated, as before, on the built
article dir existing). The registry entries deliberately keep
no_thresholds -- dropping it would auto-merge _shared.toml
spreads/anchors and change the dive content. Verified with real
scratch replay renders of the newest Cramorant GL blob and the
Thievul precedent; 8 tests in tests/test_article_slug_wiring.py.

## 2026-08-27 -- Unicode-dash ship gate now reads inlined app JS

Closes the TODO "Ship-gate gap" (725734d) opened by the 2026-08-17 thievul
pre-publish review. `verify_no_unicode_dashes.py` parsed page HTML and
skipped `<script>` wholesale, so any page that RENDERS its prose from
an inlined bundle -- the joint-IV robustness pages are ~100% that --
got a clean bill regardless of content. The gate was passing on pages
it could not see.

`js_string_literals()` (scripts/verify_no_unicode_dashes.py) is the
inverse of `tests/test_win_boundary.strip_js`: strip_js blanks literals
to leave code, this keeps literals and drops code. It handles
single/double-quoted strings with escapes, template literals (text
parts, with `${...}` scanned recursively), `//` and `/* */` comments,
and regex-vs-division disambiguation, and it tracks the innermost
enclosing callee so a carve-out can key on it. Every literal is decoded
through the render-equivalent dash spellings (`—`, `&mdash;`,
`&#8212;`, `&#x2014;` and the en-dash forms) before the same em/en-dash
policy is applied -- the HTML-text side gets that free from
`convert_charrefs=True`, script bodies do not.

Scope line: string/template literals IN, code + comments + regex
sources OUT. Two named carve-outs, both with a negative AND a positive
half in the tests so neither can silently widen:

- Vendored third-party bundles (`VENDOR_SCRIPT_MARKERS`): the inlined
  Plotly 2.35.2 bundle carries genuine dashes in its i18n table and a
  GLSL shader comment (3 distinct literals across 232 shipped pages).
  Matched on the bundle banner, not on "big minified script", so an
  unrecognized bundle still FIRES.
- `console.*` arguments: developer-console output, never rendered.
  One such string in the tree today
  (`scripts/deep_dive_engine.js:984`, on 210 shipped pages); the
  identical sentence assigned to `innerHTML` still fires.

Verified clean across the full 1,035-file `userdata/website/` ship
surface; the script pass costs ~30s on top of the gate's ~117s
(117s -> 148s). Nine new tests in `tests/test_ship_gate_detectors.py`
including an extractor self-test; 8 of the 9 proven to FAIL against
the pre-change gate (the ninth is a pure negative control, which must
pass both ways). No interface change: `run_ship_gates.py` and
`publish_website.sh` call it exactly as before.

## 2026-08-27 -- Sweep cache fully warm: sheet-v5 engine bless

Migration record (the runs themselves were never logged; state
verified via `migrate_cache.py --list-stamps` + sidecar scans):

- The Cramorant-port legs (TODO item queued 2026-08-24) had ALREADY
  run by 2026-08-26: zero columns remained at gamemaster 8f1d6cca5c0f
  or engine 5839391a7596, and the `cramorant_port_20260824`
  predicate's deletion footprint is present (the 6 Aegislash_*_great_*
  focal dirs hold only meta.json — next Aegislash dive is a cold
  bake). Sidecar mtimes show bless-not-resim (npz 2026-08-06..08, json
  rewritten 2026-08-26 02:15 by the sheet-v4 bless).
- The final leg ran today: `migrate_cache.py --from-engine
  03aff90d1e71 --predicate pogodives_sheet_v5_20260826 --apply` —
  144,336 blessed / 0 re-sim / 9,040 already-current. Soundness: the
  entire v4->v5 engine delta is one commit (`56a68b3`, battle.py
  only, gated on `policy == 'pogodives'`), and every stale column was
  pvpoke-default tier (no `policy` key).
- End state: all 153,376 columns stamp engine bff4191c3cfe +
  gamemaster 1398b001cf86 (both current). Slayer cache remains
  effectively cold (96/99 entries at two-generations-stale stamps;
  no migration path for its opaque keys — re-bakes on demand).

## 2026-08-27 -- KO-edge "divergence": not an engine bug (investigation record)

The fast-move-on-the-killing-blow divergence logged from sandbox-link
validation (UL Cramorant/Lapras 1-1: ours 668 vs sandbox 662) was
adversarially investigated and is NOT an engine divergence. Our
step-3-before-step-4 ordering IS PvPoke's priority scheme (due fast
+20 > charged 10-15 > floating fast -20; Battle.js:388-408/834-843);
given the same action set the engines agree cell-for-cell (1,089
verified cells, GL+UL top-16 x 9 shields). The gap is a sandbox-link
ENCODER artifact: `timeline_to_actions` (scripts/pvpoke_sandbox.py)
only emits charged moves that RESOLVE, so a decided-then-CANCELLED
charged move (CMP loser KO'd, etc.) leaves no action and PvPoke's
sandbox substitutes a phantom due fast on the KO turn; scripting the
cancelled move (or a `wait`) reproduces our score exactly (7/7
mismatch cells). The 4 shipped showcase links verified clean
(cancel_gap 0, byte-exact). Bonus find: all three Node harnesses
(pvpoke_url_run.js / pvpoke_sandbox_driver.js / pvpoke_trace.js) used
the Ranker.js rating formula `floor((health+damage)*500)` where the
battle page uses `floor(500*damage + 500*health)` (Pokemon.js:2124) --
sum-then-scale lands 1 low on exact fractions, the only 2 non-encoder
mismatches in the sample. Both tool-layer fixes SHIPPED same day
(3a041cb): cancelled charged decisions are now logged + encoded (the
reference cell round-trips 662 exact), the three Node harnesses use
the battle-page formula, and the log-only engine bump (bff4191c3cfe
-> 515a0a95171b) was fully blessed via the
cancelled_charged_log_20260827 predicate (153,376/153,376 warm).

## 2026-08-27 -- Cramorant dives + strategy article + Worlds refresh PUBLISHED

Full site push to pogodives.com (Michael's explicit go): both
Cramorant dives (sheet v5 tensors, blobs 20260826_124234/140322), the
strategy article (final authorship "both" after Michael's review; 4
verify_url-gated sandbox showcases, 8fc7ec4/96acaba), the site-wide
all-scenarios 3x3 checkbox grid, and the frozen Worlds surfaces. Ship
gates all green (verify_worlds run from the pinned worktree; live
gamemaster restored + hash-verified 1398b001cf86 after). Same
morning (~04:30): Greninja + Annihilape entered the Worlds matrix (35
entries, 555 pair pages, 0 deferred; 31a7361), executed from the
vintage-pinned worktree gopvpsim-worlds at 6a7e534 -- the Worlds
surface stays FROZEN at the pre-Cramorant engine until after Aug 30.
Core-breaker scan + HSH Greninja verification findings:
~/coding/reports/gopvpsim-worlds-2026-refresh-2026-08-27.html.
Worlds Discord post SKIPPED by Michael's decision (draft header-marked;
the Corvi/Quag scatter lead moved to a possible Reddit post, TODO).

## 2026-08-24..26 -- Cramorant arc: Gulp Missile port, policy campaign, pogodives sheet

Engine port of the first multi-form/variable-target changer (pvpoke
78c64048a) landed 2026-08-24: 81 oracle-exact fixture cells + 36-cell
audit extension, 52-agent adversarial review, all 19 confirmed
findings fixed same-day (mechanics record: DEVELOPER_NOTES "Form
change gotchas" item 5; migration predicate cramorant_port_20260824).
Policy campaign (standing resource authorization): round 1 overnight
lab (80 variants x 4 opponent models x 4 IV spreads; synthesis
docs/validations/cramorant_policy_lab_2026_08_24.md), lead40 adaptive
tank frozen 08-25, pogodives_dp/pogodives_shield overlay landed
08-25 (byte-identical pvpoke_dp fallback for every non-Cram
situation, test-pinned), render side same day (b67b8d4 policy tier
through sweep/cache + 744c4a5 --policy axis & Strategy dropdown).
Round 6 closed 08-25: nothing ships, lead40 stands. Michael's
strict bar 08-26 (every start scenario >= 0 on BOTH mean rating delta
and net flips vs plain PvPoke) superseded uniform lead40:
_POGODIVES_SHEET landed (8fc5764), v3 certified 360/360 cells at full
4096-IV resolution (90d8811), v5 shipped (56a68b3) after the 0v0
oracle capture + 1v0 loaded-tank skeptic round; full record incl. the
blob-vintage rule: docs/validations/cramorant_strict_bar_2026_08_26.md.
GL + UL dives baked --policy both --bait both; published 08-27
(entry above). Sweep-cache migrations for the arc all ran (recorded
in the 2026-08-27 cache entry above).

## 2026-08-18..20 -- Worlds: Thievul fork + IV-robustness deep pages

Thievul entered the published Worlds matrix post-publish (08-18) as a
two-entry moveset fork (NS+IW / IW+PR) with Icy Wind INJECTED under
the pinned gamemaster (lag proven via upstream eliteMoves, CLAUDE.md
cd_prep rule; per-entry injected_move_ids honored by
worlds_bake.preflight_moveset_legality, disclosed on every Worlds
page; two worlds_code bumps blessed forward with written proofs,
verified additive). Tier-1 grew to 2,112 keys / amber 455.
2026-08-19: worlds_shortlist.py shipped (455 amber pairs by combined
usage); the joint_iv_* kit replaced thievul_licki_* (8feec47,
319c8a2). Overnight into 08-20, three site pushes: 11 deep pages +
grid-amber squares; the 73-clean-pair audit (1.36B sims, FINAL amber
505/528, 50 squares recolored -- the hub FN block now reports 11/73,
retiring the 4/21 original-sample figure); three MIRROR pages
(lickilicky/wigglytuff/corviknight; mirrors had been an accidental
combinations() exclusion; heavily IV-decided, e.g. Licki mirror best
build rank-3182 15/3/3) + a latent renderYourDenial crash fix.
Round-2 mirrors built 08-24 (thievul x3 incl. the cross-arm,
quagsire-shadow, altaria); the 11 deferred review minors shipped
28f2a4d, [meta.oracle] pins on all 18 eligible pairs 7360eb2; mirror
seat-asymmetry finding baked into the kit (8ebb642). The kit's
untested-guard debt was closed 2026-08-27 (37ccc01 + 93b6d91).
Operational lesson: run long bakes DETACHED (os.fork/os.setsid
double-fork; two harness-managed bakes were killed mid-run, per-grid
manifest keying lost nothing).

## 2026-08-15/16 -- Thievul CD: dive published + Licki robustness pages

Dive live at pogodives.com/thievul-great-league/ (4 pages; landing SP
/ Icy Wind + Play Rough, the 62W-25L 1-1 build; pre-CD reference
NS+PR as m3; plan + verified numbers docs/thievul_cd_plan.md). The CD
article was DROPPED by Michael's decision; the thresholds/thievul.toml
article slug stays pre-registered but inert (renderer emits the link
only when the article dir exists). CD-day addendum (08-16): the
Thievul-vs-Licki IV-robustness analysis shipped -- full 4096x4096
joint IV grids vs Lickilicky (4 moveset/bait grids) + Lickitung,
published as thievul-lickilicky-robustness.html +
thievul-lickitung-robustness.html with an index card (pipeline
contract docs/thievul_licki_analysis.md). CD-day poke_genie fixture
committed 1b5ce69 (Michael's ok, 2026-08-19).

## 2026-08-14 -- Worlds 2026 PUBLISHED (pogodives.com)

Full amber coverage shipped: 401/401 IV-decided pairs baked
(`c80889d`; three resumable legs across a suspend + a monitor-standby
power loss, zero partial pairs, ~5.1B sims total for the completion
run) and all surfaces rendered + live (hub, 31 cheat sheets, 401 pair
pages, CMP board, IV explorer). Gamemaster pinned at the pre-Worlds
vintage 8f1d6cca5c0f for every leg and render (upstream delta since:
three mega forms, sim-irrelevant; old blob restored from pvpoke
`f60a41199` on each cache TTL expiry).

Same-day pre-publish polish (`157bf71`, each with a fails-without-it
test): cheat-sheet 3x3 grids link to pair pages (802 links, all
resolve); trivial 512/512 deny cells annotated "(moot: rank-1 never
reaches)" with an atk-citing hover tip (17 cells; strictly-between
counts stay bare); robustness curves got a cursor-following IV
readout (8-hex-per-rank WPACK, JS-injected hint so no-JS shows no
dead affordance). Adversarially verified: WPACK decodes == fresh
iv_rank, data-bins bit-match npz re-derivation. Also `6a45bba`:
meta current_rank refreshed to PvPoke's live rankings (Mimikyu 1 ->
5) and the ==1 moving-external test pin relaxed.

Post-publish spot-check (Michael's read of the Altaria-Jellicent
curves): 1-1 and 2-2 win matrices verified cell-identical in the npz
(both bait modes), and the win boundary confirmed as the Dragon
Breath 2 -> 3 damage tier vs each Jellicent build's def (cutoffs
105.75-108.58 across the cohort; win fraction exactly monotone in
focal atk).

## 2026-08-11 -- Worlds session 5: IV explorer, CMP board, verify_worlds gate

IV explorer (`worlds-explorer.html`): the browser receives BAKED
tier-0 cutoff ladders (worlds_explorer_data.py, 1.1MB blob) and never
computes damage -- the JS surface is stat math (delegated to the
parity-tested POGOCollection) plus threshold comparisons, closing the
retyped-damage-constant drift class by construction (scan-pinned).
Parity: stats bit-exact vs gopvpsim.pokemon; 5,700+ ladder read-outs
equal worlds_tier0.staged_damage at the same effective stats; every
shipped cutoff verified min/max-true at adjacent floats. Under-range /
over-cap builds get explicit banners, never clamped read-outs.

CMP board (`worlds-cmp.html`): priority order + contested pairs with
exact flip thresholds (tier0.cmp_threshold), PROP-1 tie semantics, and
the mandatory cmp_atk 1-ULP shadow-tie footnote.

Two adversarial rounds drove real fixes: (1) the board's ranges now
cover the UNION cohort (top-512 SP + attack band) after the hundo
blind spot -- a 15/15/15 Wigglytuff (SP rank 2137) beats Sableye
(Shadow)'s rank-1 on CMP while every top-512 Wigglytuff loses; 124
pairs the top-512 ranges called "settled" were IV-decided; (2) all
displayed cutoffs/thresholds round UP so reaching the printed number
always suffices (plain 2dp had rendered unreached cutoffs as "+0.00"
on 22.6% of builds and read exact CMP ties as wins at display
precision); (3) a shadow threshold 1.2x re-scaling bug was caught by
the new threshold-consistency test before ever rendering; (4)
sub-0.01 gaps print as "<0.01" with the not-closeable-by-powering-up
caveat.

`verify_worlds.py` wired as SHIP_GATES entry 5: Tier-1 stamp+coverage,
Tier-2 soundness + deferred-list agreement, all rendered surfaces
incl. pair-page set equality, hub FN freshness, cmp/explorer
byte-freshness vs current meta, and the *_great.toml collision glob.
Full roster green (1878 fast-tier tests, links, dashes, sentinels,
worlds). Publish held for Michael's explicit go.

## 2026-08-11 -- Worlds session 4: Tier-2 grids, pair detail pages, measured FN-rate

Overnight Tier-2 bake (after an eventful evening -- see the session-4
commits: lid-sleep ate the first budget; head-of-line blocking idled
13/16 workers and was fixed with out-of-order harvest + producer-stamp
narrowing to `worlds_tier2_worker.py`; a clean-sample direction bug
contaminated the FN inputs and was fixed + retagged): 87 complete
pairs / 348 grids / ~2.1B sims at 64k sims/s on the fixed driver --
the top-66 usage-ranked amber pairs plus 21 genuinely-clean FN
samples; 335 amber pairs deferred by budget (hub lists them;
`worlds_tier2.py` re-runs extend idempotently).

66 per-pair detail pages shipped with per-scenario full-grid counts,
SVG robustness curves (bin-centered, bait/top-512 provenance
adversarially confirmed), and boundary-confirmed reach-or-deny strips
(now incl. deny counts vs the focal rank-1 anchor). Two adversarial
verify rounds: round 1 confirmed every printed number reproduces from
the grids (1,442 assertions incl. all 62,976 curve points; 496 reach
rows re-bisected against the engine; Tier-1 vs Tier-2 cross-bake 0
mismatches) and round 2's structural catches all landed as fixes:
scenario selection now comes from the GRIDS (the Tier-1 probe screen
had silently dropped 84 mixed scenario slots, worst 35.2% minority --
Aegislash vs Kingdra 2-2 now renders 290-sweep/101-shutout), reach
headers no longer say "beats" (damage-plan language only), the FN
block reports spread-impact instead of the misread-prone cell-minority
share, cheat sheets no longer claim "deferred" for never-worklisted
pairs, and matrix pair-links are bidirectional. Measured FN-rate: 4 of
21 clean pairs show IV-dependence in the full block; the pages'
scenario selection no longer depends on the screen at all.

## 2026-08-10 -- Worlds session 3, block 2: Tier-1 bake + matrix + cheat sheets + hub

Full Tier-1 bake straight after the migration so the manifest pins the
final pre-Worlds vintage: 1,860/1,860 planes (7.06M sims, 115s, 61k
sims/s pooled), stamps engine `5839391a7596` / gamemaster `8f1d6cca5c0f`
/ worlds_code `653d776f9028`; mid-bake engine-digest check clean. New
renderer stack, both deliberately OUTSIDE the plane-producer hash:
`scripts/worlds_render_data.py` (plane -> per-scenario fractions/wins/
margins; STRICT green/amber/red, no epsilon; coverage + stamp refusal
paths) and `scripts/build_worlds_pages.py` (root-level `worlds.html`
hub with meta table + rejects/banned table + 31x31 robustness matrix,
plus 31 `worlds-<species_id>.html` cheat sheets; `_page_shell` gained
viewport meta + `extra_css`; index card + publish_website.sh wiring).

Adversarially verified (2 workflows, 8 Opus lenses total): orientation
proven end-to-end (84 independent re-sims match planes exactly incl.
form-change/shadow cells; complementary-direction scores; every one of
the 16,740 strip tooltips + 930 matrix tooltips/margin bands
regenerated from raw npz with 0 mismatches; won == score>500 across
all planes, no uint16 wrap). The review's page-layer honesty findings
were all fixed and re-pinned in tests: margin bands now span BOTH bait
modes (bait-only band hid a -279 no-bait loss behind "+13..+279"),
tooltips print exact "beats N of n" counts (rounding had collapsed 127
IV-decided cells to a settled-looking 0%/100%), W/L/? letters make
outcomes color-independent (the three fills are isoluminant in
grayscale), the focal-only no-bait semantics + tie-counts-as-loss +
excluded-Internationals + team-level/per-variant conventions are
disclosed, badge_rule divergence renders (Altaria (Shadow) PLAYED/rule
MODEL), movesets display in SIMMED slot order (4 equal-energy cases),
and the "usage predates the rebalance" claim was softened to the
verifiable "corpus ends at the rebalance boundary" (pvpoke merged
Forever Forward 2026-06-02, before Turin -- plan doc carries the
correction note; in-game date TBD session 4).

## 2026-08-10 -- behavior-neutral engine-hash batch + two-leg warm cache migration

Worlds session 3, block 1 (Michael's decided sequencing). One engine-hash
bump `1415857072fa -> 5839391a7596`* carrying: (a) the would_shield
attribution rewording per `docs/reviews/2026-08-09_would_shield_diagnosis.md`
(battle.py + the test_group_c10 docstring; the review doc's own disposition
bullet had the staleness BACKWARDS -- EP.damage is the fresh-on-use value
(50), IW.damage the init-stale one (35), (50/50)/(35/45)=1.2857 -- caught by
the session's adversarial verify pass and corrected in all three places);
(b) `parse_types` relocated verbatim `data.py -> moves.py`, closing
test-suite-review F5 (damage-affecting but unhashed) -- 21 call sites
repointed, `data.py` keeps a lazy PEP-562 alias because gobattlekit's
`export_thresholds.py` imports it from `gopvpsim.data` by name
(`test_gobattlekit_api_pin`); alias removal is a post-Worlds TODO. FC-2's
formchange.py half turned out to have already landed in `281a40a` (the
2026-08-09 diagnosis doc listed it stale). Neutrality proven, not assumed:
token-stream diff (battle.py comment-only), AST-identical parse_types body,
1,539-battle differential vs a HEAD tree bit-identical (JIT active) + an
independent 819-cell probe, full suite green (1856+1 passed, 13 xfail).

Cache migration was TWO-legged because both sidecar stamps were stale
(engine: this bump; gamemaster: pvpoke `ea8f7691c -> f60a41199`, the
purely-additive Mega Starmie patch, `d0506c8999e9 -> 8f1d6cca5c0f`) and each
migrate mode requires the OTHER axis current -- a single-leg run provably
blesses 0 columns (dry-run: 146,968 skipped). Sequence: `--from-gamemaster`
FIRST from a pre-batch `git archive` tree (computed delta: 1 species added,
0 changed/removed -> bless-all), then commit, then `--from-engine
1415857072fa --predicate neutral_batch_20260810` (fully-blessing; proof in
its docstring + `test_neutral_batch_20260810_predicate`). The 96 slayer-cache
entries have no gamemaster-migration path (opaque keys) and cold re-bake on
demand, matching the 2026-06-29 precedent.

*The engine hash also covers `scripts/deep_dive_signature.py` as a sixth
input -- the "five files" shorthand in older notes undercounts it.

## 2026-08-10 -- S8a tie semantics decided: exact 500 is a tie, not a win

Resolution of lane A's 2026-08-09 escalation (Michael's call): KEEP the
strict `>` that the S8a vectorization (`8a7fdc7`, 2026-04-17) silently
introduced in `aggregate_flips_by_anchor` -- it matches
`battle.is_win`, PvPoke (exact 500 = tie), the sibling probe/losses
paths, and everything shipped since April. The frozen test oracle
(transcribed from the pre-S8a `>=` code) is now corrected to `>`, the
parity fixture plants exact-500 cells (losses vs OPP_0), and a new
`test_tie_score_is_not_a_win` pins the boundary directly with a
501-control. Discrimination proven by mutation: regressing production
to `>=` fails 2 tests; restored, all pass. Retroactive record: the
April S8a commit was presented as behavior-neutral vectorization but
also fixed this tie-handling bug -- production `>=` counted exact ties
as wins, contradicting the canonical convention. No production change
today; test-only.

## 2026-08-09 (evening) -- test-suite review phases 2-4: the suite now discriminates

5 adversarially-verified lanes (20 agents; every replanted/converted
test proven to FAIL against broken code before landing):

- **Phase 2 dead weight** (`e6dcc2e`, `d27f481`): the three vacuous
  S8a oracle-parity files replanted (scores now couple to the swept
  stat; all 14 tests fail under a type-correct stub, previously 13
  passed) with non-emptiness asserts on every comparison; the 33.9s
  permanently-xfailed gamemaster sweep replaced by a 1.7s seeded
  banded sample + a slow-marked full sweep that actually asserts (last
  permanent xfail gone; 14 -> 13 xfails, all strict); 72-cell
  turn-mechanics grid shrunk to its 3 distinct signatures; duplicate
  conftest TTL fixtures merged; 4 tracked-file skips -> hard asserts;
  `render`/`local_artifacts` markers added. Fast tier 44s -> 36s.
- **Phase 3 pin conversions** (`aa74af1`, `8a78c4e`): the silent-rot
  absence pins re-planted as tolerant structural scans WITH positive
  controls (respelled antipatterns now caught -- proven per pin);
  import-text pins -> object identity; bake pins -> rendered-DATA
  assertions; the print() pin -> an AST scan; KEEP-list items
  untouched.
- **Phase 4 blind spots** (`64b3e29`): six new files, 50 tests --
  JIT-vs-pure-Python equivalence (+ overflow-sentinel fallback, with a
  counting-shim anti-vacuity guard), ship-gate detector
  positive/negative controls, worker-logging spawn delivery,
  `_ENGINE_FILES` closure guard (data.py allowlisted with a pointer to
  the queued parse_types relocation; sweep_cache's overclaiming
  comment fixed), gobattlekit 9-name signature pin (+ `__all__` on
  thresholds.py), attribution surfaces on the rendered dive.
- **Policy adopted**: the testing-policy block is now in CLAUDE.md's
  Testing section. Suite 1783: full ~79s / fast tier 36s / gates
  green. Lane A escalated one real find for decision: the S8a
  vectorization silently changed aggregate's tie handling (`>=` ->
  `>`) -- TODO carries the decision bullet.

## 2026-08-09 (day) -- both-reference card lines, publish, test-suite review + Phase 1

**Card flip lines (Michael feature request):** the recommendation
card's per-spread gains/loses prose -- computed vs pvpokeRefIvIdx but
mislabeled "vs stat-product #1" since b595071, caught live on the
Umbreon GL Bait Robust card -- now renders BOTH labeled lines ("vs
stat-product #1 (a/d/s)" from a new flips_sp pass, "vs PvPoke default
(a/d/s)"), collapsing when the references coincide, with "this spread
IS the ..." for the reference spreads themselves. Adversarial review
caught 4 findings pre-commit, incl. a must-fix false-"no flips" on
IV-floor dives and the latent shadow= omission in the pvpoke-default
lookup. 6 new tests.

**Published to pogodives.com:** the overnight-lane visible changes (SP
Rank PvPoke convention, "Avg score behind best" relabel, methodology
wording, #opp- landings) + the card feature, after Michael's review of
the staged Umbreon page. Live spot-checks green. The re-render's only
FAIL was the dev-count gate racing the card commit's own tests --
resolved via verify_dev_counts --update, the tool built the night
before for exactly this.

**Test-suite review** (docs/reviews/2026-08-09_test_suite_review.md +
HTML on the reports pogo subpage): inventory + 5 lenses + adversarial
verify pass, every load-bearing claim executed. Verdict: right shape
(A-grade boundary contracts, 13/14 strict xfails), three structural
problems -- no mechanical trigger, ~90 dead/vacuous tests (13 proven
stub-survivors, the 34s permanent xfail = 45% of wall time), and
negative source pins that miss re-spelled antipatterns. Bonus verified
find: data.py:parse_types is damage-affecting but outside every cache
hash (low probability / high blast radius; relocation queued for the
next bump window). Phases 2-4 + the CLAUDE.md testing-policy block
await sign-off.

**Phase 1 (mechanize) SHIPPED same day:** new verify_tests.py ship
gate (pytest -m 'not slow', ~44s, first in the roster; loud
node-presence check closing the 19-silently-skipped-JS-tests hole) on
every publish path; core.hooksPath actually activated in this clone +
added to the fresh-machine setup steps. Suite 1784; full roster green.

## 2026-08-09 (overnight) -- scouted-backlog churn: 7 lanes, 5 fixes, 2 tools, 1 refuted engine change

Fable-orchestrated overnight run (Michael AFK): a 9-agent read-only
scout re-derived every candidate TODO finding at HEAD, then 7
file-disjoint lanes (28 agents, 2 adversarial verifiers each) landed:

- **fix(breakpoints) `fa1bd1d`:** Aegislash (Blade)'s whole-level rule
  was honored at only 1 of 4 level sites in iv_breakpoints/
  iv_bulkpoints (2053/4096 rows sat at half levels while the same
  output's rank column used whole levels). CLI + tests only; no dive
  HTML, TOML, or export is affected. Surfaced a separate pre-existing
  51.0-vs-league max-level default divergence -> TODO.
- **fix(dive SP Rank) `8c1f98e` (js-parity-3):** DATA.spRanks was baked
  from the 0.1-rounded display array with enumeration-order ties while
  the same column's off-grid path used iv_rank (unrounded SP, IV-sum
  tiebreak, PvPoke convention); Medicham GL disagreed on 1354/4096
  spreads and the rank-1 marker itself flipped (5/15/14 vs the famous
  5/15/15). New `sp_rank_array` helper routes the L50 grid, the L51
  best-buddy twin, and the CLI sweep variant through one convention;
  8-test pin file. RE-RENDER ONLY (no engine hash, no cache impact);
  25-81% of SP Rank cells change per page.
- **verify_overnight pool containment `48d37c7`:** step [3/5] now
  asserts name-set containment of each dive's own opponents_file
  against its rendered DATA.opponents -- the first completeness guard
  for UL/ML/cup dives (GL had only a 3-marker check; a deranked
  opponent silently dropping from every UL dive previously passed
  GREEN). The old "needs a count-marker design decision" framing
  dissolved: counts can't work (mirror/anchor/variant entries APPEND),
  containment can. Same commit: run_website_dives' narrative patch no
  longer skips silently when the dive dir is absent (F3 tail; F3
  proper had already shipped in `278bc44` -- the TODO was stale).
- **verify_dev_counts --update `5b6aec9`:** opt-in flag rewrites the
  DERIVABLE sentinels (test_count, type_chart_cells_verified) in
  DEVELOPER_NOTES.md in place -- ends the six-racing-sentinel-bumps
  serialization pain from the 2026-08-08 churn. Adversarial review
  caught a real pre-commit defect: a lost `<!-- /sync -->` marker made
  the DOTALL rewrite swallow prose up to the NEXT sentinel; fixed +
  tested before landing.
- **fix(compare methodology) `95fcf74` (G16, narrowed):** the
  comparison-page "About these numbers" block said win rate counts sims
  "scoring at least 500" -- the code counts strictly > 500 and an exact
  500 is a tie. Corrected wording (user-visible on 4 published pages at
  next publish), sweep dims now derived instead of hardcoded, block
  links the How This Works guide.
- **"Gives up vs #1" disambiguation `c911eff` (js-parity-5 follow-on):**
  the dive column, owned_breakdown.py, and the compare-card each
  measure something different; docstrings now say so (the false "must
  reproduce" claim was already deleted in `639ef1e`) and the
  compare-card row is relabeled "Avg score behind best" so one label no
  longer covers two units. Bundle-export staleness caveat added
  (shipped dives predate `8c1f98e`, so their rank1RefIvIdx is
  pre-convention).
- **fix(#opp- landing) `b43bd2d`:** `#opp-<slug>` deep links now land
  on the opponent's matchup detail in the Threats section instead of a
  collapsed anchor-flip bullet (first-mention-wins registry claimed at
  compute time, and the bullets computed first); the best-buddy L51
  template also gets its own opponent-id set instead of inheriting an
  exhausted registry (its `#opp-` hrefs all dangled after the L51
  swap).

**Refuted, no code shipped:** the TODO's would_shield/always-shield
"our own bug" medium. The scout's oracle-traced diagnosis
(`docs/reviews/2026-08-09_would_shield_diagnosis.md`): the mismatch is
shared PvPoke structure, the traced +201 is PvPoke's own stale damage
cache, and the suggested fix worsens total oracle error 201 -> 730
while blessing only 27% of a migration. Comment-only reattributions
ride the next engine-hash bump window.

Suite 1719 -> 1762 passed (+43); full suite + ship gates green; engine
hash untouched (verified per lane against sweep_cache._ENGINE_FILES).
Docs groomed same night: stale TODO sections (deep_dive split DONE with
landed-home map, F3, UL-guard, dev-count, #opp-, BP-3/would_shield) and
the last surviving "bundle matches the website column" falsehood in
docs/owned_mon_breakdown_plan.md. Rendered-page changes staged by an
overnight re-render; PUBLISH HELD for Michael's sign-off (TODO "Pending
publish").

## 2026-08-08 (evening) -- re-render + publish: the DRY render ledger reaches the live site

The render-only chain (`rerender_20260808b.sh`, replay blobs ->
HTML, no sims) drained the 15 pending render-side commits from the
DRY arc into shipped HTML: 97/97 dive pages OK (0 failures, ~15 min/
blob x 8 workers), 61/61 ML guides from saved JSONs, comparisons /
matchup web / reader guides / index rebuilt, ship gates green (402
files, 0 broken internal refs across 392,555 hrefs, no unicode
dashes, dev counts). Ledger spot-checks verified on the rebuilt pages
AND on the live site after `publish_website.sh --push`: plotly theme
shim chrome (`themeColor()` + `--cat-anchors` fallback), the 0v0
Flavor Guide vocabulary, WIN_RATING in DATA, and zero live-DOM
duplicate ids (context-aware scan; a naive grep re-reports the
dd6b7a3 scan artifacts). First chain launch was caught re-rendering
the 97 superseded July blobs alongside the v8 set (double render, ~1h
waste) and restarted at `--since-hours 60`; July-blob retirement is
TODO'd (bulk mv is permission-gated).

Watch-script pair shipped alongside: new `scripts/rerender_status.py`
(colored status box for render chains; its first live render exposed
both the July-blob double-render above and, later, its own padded
OK/FAIL regex bug -- fixed) and `scripts/chain_status.py` upgrades
(dynamic full-run step checklist from [STEP]/[DONE]/[FAIL] lines,
COMPLETE/FAILED liveness instead of a red DEAD after success,
fabricated post-completion ETA suppressed, phantom `retrofit` preset
removed, `sys.executable` for the overnight_eta subprocess, and the
Path('')-is-truthy validation hole closed).

## 2026-08-08 -- AFK deferral churn: the review's recorded ledger cleared (28 commits)

41-agent workflow while Michael was AFK: a scout re-verified all 26
harvested deferral-ledger items at HEAD (4 already done -- nothing
re-implemented), then four file-disjoint lanes + a final plotly step
cleared the rest with 2 adversarial verifiers per step (7 must-fix
findings caught and fixed in-flight). Landed: remaining L11 scans in
deep_dive/deep_dive_lib; DOM-id de-dupe (af-/dd- dupes from the predive
gate); one moveset-label + one scenario-label rule everywhere on the py
side (Flavor Guide moves to the 0v0 vocabulary -- deliberate visible
change); .cmp-* stylesheet hoisted across both renderers; iv_envelope
_move_abbr retired; shared EVEN_SHIELDS home; WR-ramp constants emitted
from the module; verify_overnight cup glob derives from
data.cup_slug_suffix; invalidate_caches gained a registration seam for
the scripts-side move-display cache; emitted-JS WIN_RATING scan
coverage; JS league-caps little:500 + maxCp fallback pinned; WIN_RATING
baked into DATA with ~15 JS boundary sites routed through one helper +
a staleness guard on patch_dive_gives_up_column; theme.py _THEME_KEY;
and the two iv-tech NO-BAIT ORACLES -- both reference claims REPRODUCE
(Tinkaton 0-1 vs Shadow Altaria via the def=143.04 Flamethrower
bulkpoint, surviving on exactly 1 HP; Spidops 1s vs Altaria), with the
old "more forgiving threshold" question resolved (bait-on wins are
real; the reference claim is specifically no-bait). Auto-anchor gating
tests were found already covered (test_anchors, 585a136) -- TODO was
stale.

Suite 1620 -> 1719 passed / 14 xfailed. Engine-hash inputs verified
byte-identical (incl. deep_dive_signature.py beyond the brief). Gate
caught one real red: the test_count sentinel raced across lanes (six
bump commits; recorded as a TODO tooling item). PENDING RE-RENDER
ledger: 15 render-changing commits await the next re-render+publish,
GATED on Michael's visual sign-off of the plotly theme shim (8da55c4:
theme-aware chart chrome, previews rendered for both themes; known
limitation disclosed in 048bb3e -- two overlay hues alias a tier hue).

## 2026-08-06/08 -- entries 12+13 shipped; v8 cold bake complete (18h sleep stall, recovered)

**Entries 12+13** (commits `d95e9d0..6cfe512`, 30-agent workflow + independent
re-verify): the engine DRY batch landed as ONE hash bump
(`9ac2f4ed -> 1415857072`) -- league descriptor (little-league KeyErrors
fixed), cached `from_pokemon` accessor hop (10.27s -> 0.003s per 2000
constructions), shadow-stats primitive -- with behavior neutrality proven
twice (bytecode-identity harness at implementation; oracle-harness A/B at
gate: 172 exact + 35 documented on BOTH sides). The deep_dive.py split
extracted five `deep_dive_lib` modules with import shims and Pool-round-trip
worker proof; D9 SweepConfig / D10 shared `build_battle_pair`
(CACHE_VERSION sweep v8 + slayer v6, deliberate whole-cache cold) / D14
one-meets-rule (the adversarial re-verify found and fixed a THIRD
hand-copied chain in the L51 path -- the last rounded-stats classifier).
Gate fallout fixed: oracle baseline was publicly 2 cells stale since hunt2
(A/B-proven; sentinels corrected), verify_dev_counts joined the ship-gate
roster (it was called by nothing and a month stale), three pvpoke-root
defaults pointed at the pre-Smith path. Suite 1290 -> 1620 tests across
the 3-day arc.

**The v8 cold bake** (`overnight_20260806_211020.log`): launched Aug 6
21:10 after a Fable predive gate that caught two would-be killers
pre-launch (a step-9 sentinel drift that would have failed the chain at
hour ~20, and the data-cache TTL expiring mid-bake -> vintage pinned at
launch). SUCCESS Aug 8 13:01; verify_overnight ALL GREEN (97/97 dives,
61/61 ML guides, three-gate roster clean). Wall-clock ~40h, of which
**18h was a machine-sleep stall** (Aug 7 16:48 -> Aug 8 10:54, lid-close;
sim pace when awake beat July: 9.4 vs 12.5 min/dive mean on one fewer
core). The stall pushed the run past the pinned TTL: a worker refetched
the gamemaster at Aug 7 21:11, making the bake mixed-vintage (121,292
columns on Jul-30 `e97cb2f0`, 25,676 on Aug-7 `d0506c89`). **Recovered
and proven consistent**: the vintage delta was purely additive (13 moves
added, nothing changed/removed) -> `migrate_cache --from-gamemaster`
blessed all 121,292 columns to current with 0 affected; rankings-level
check found 0 default-moveset flips across the GL + UL pools and all
post-stall focals. Hardening shipped: caffeinate in the chain script
(idle/timer sleep), lid-open + TTL-vs-wall-clock pre-launch triggers on
the predive checklist, keep-a-vintage-copy recovery note. ML-guide phase
was 245s -- the guides are 64-IV sweeps, so the cold-ML fear was
unfounded. gc of the 42G v7 leftovers is now UNBLOCKED (bake verified).
Published to pogodives.com 2026-08-08 (gates green; live spot checks
200 incl. post-stall dives and ML guides). v7 cache reclaimed same day:
~44 GB sweep legacy dirs + 1 GB pre-bake slayer files; cache now 43G at
a single current vintage.

## 2026-08-05 -- DRY review executed end-to-end; site re-rendered + published

Two-day arc, one day: the Fable-orchestrated DRY/single-sourcing review
(13 agents, `docs/reviews/2026-08-05_dry_review.md`, 56 distinct defects
ranked into 15 entries) was run in the morning, and by evening entries
1-11 + 14 + the two entry-12 "safe-any-time" cherries were implemented,
adversarially verified, re-rendered, and published. Only entries 12
(deep_dive.py split, CACHE_VERSION cold) and 13 (engine DRY batch) remain,
both scheduled against the next bake window, plus entry 15's fold-ins.

**Entries 1-3** (commits `d81c4ad..1db4f65`, hand-implemented): five live
wrong-output fixes (case-insensitive opponent-color hash; unrounded tier
classification via `classify_tier_indices`; one `_atkBeats` mirror-CMP rule;
`rank1_spread` -> `iv_rank` wrapper; honest surface docstring), the
gender+min-level-aware evolution walk (`gender_allows` /
`eligible_final_forms` in user_collection; on the fixture the Oinkologne
(Female) GL breakdown now skips 34 wrong-gender + 6 over-leveled rows), and
five ops/gate items (shared ship-surface enumeration gating cups.html/
support.html; single SHIP_GATES roster -- two chains had silently skipped the
dash gate; filename-stamp chain-log rule; ML-slug single-sourcing;
read-modify-write cache-sidecar primitives).

**Entries 4-11 + 14 + cherries** (commits `caeded9..7e66ba2`, 30-agent
lane-partitioned workflow, 2 adversarial verifiers per entry, 3 must-fix
findings caught and fixed in-flight): WIN_RATING JS tripwire + league-cap
pins; the five Py<->JS wire strings baked from Python (score key, mode
grammar, scenario label, moveset label, tier slug); July cup plumbing
consolidated (public data accessors, one cup registry, W8 slug-parser
merge); gamemaster-backed move display names (~39 labels corrected/page)
with the id-derived `move_abbr` energy tags; pvpoke link-builder
consolidation + Python<->JS URL parity test; league-derived level ceilings
in user_collection (None-means-derive; gobattlekit PORTS the module -- its
copy noted in the docstring); per-target JS gender mirror + Oinkologne
harness coverage; `gopvpsim.invalidate_caches()`; matchup-clusters cleanup.
Suite 1322 -> **1514 passed / 14 xfailed** (+192 tests in the day);
engine-hash files verified untouched in every commit, so the sweep cache
survived the whole arc warm.

**Verification-report discipline** (reports repo,
`gopvpsim-dry-fixes-verification-2026-08-05.html` + the rendered review):
every agent-verified claim was re-verified by hand; THREE claims fell and
are corrected visibly -- the Annihilape 0/9/14 "shipped page" example
(refuted: atk gates block it, no such page), the "9 of top-80" rank-1 count
(measured 7), and the first re-audit's own "48/94 dives, 2328 flipped
spreads" tier estimate (superseded by a direct DATA.ivTiers diff of all 97
pages, old live vs new: ZERO tier changes -- the sweep had classified
against `blob['thresholds']`, which the anchor-derived page tier system
does not use). Lesson recorded: model-level sweeps against blob structures
are not page-level evidence; diff the rendered artifact.

**Re-render + publish**: render-only chain
(`userdata/logs/2026-08/rerender_20260805.{sh,log}`) -- 97 dives from
replay blobs, 61 ML guides from JSONs, 4 comparisons, matchup web, guides,
index, ship gates -- then `publish_website.sh --push` (396 files by
checksum). Live-site spot checks green: Altaria one hue (96 spans),
zero "Super Power", `_atkBeats` shipped. No re-sim anywhere. **Not** part of the
session-startup read (see `CLAUDE.md`). Purely historical reference
for "when did we ship X" and "what was the root cause of that old
bug." Active pending work lives in `TODO.md`; still-relevant
invariants and PvPoke bugs live in `DEVELOPER_NOTES.md`.

## 2026-08-04 -- 2026-07-06/07 bake closed out (was left red on a fixed failure)

The 2026-07-06/07 cold re-dive (chain `overnight_20260706_204813.log`, the
first bake of the post-hunt2 engine merged in `2a63b65`) finished its work but
was never formally closed: `overnight_status.txt` still read `[FAIL]`, no
CHANGELOG entry existed, and TODO's re-dive runbook still named 2026-06-28 as
the last bake. Reconstructed and verified today.

**The bake itself was always sound.** The single failing step was the final
`verify_article_links.py --ship`, which reported 1580 dangling hrefs, every one
of the form `../guides/...`. Root cause: the run was on a fresh laptop, where
`userdata/website/guides/` did not exist yet -- the Reader's Guides are a build
product and `userdata/` is gitignored, while every dive page hardcodes ~5 links
into that tree. No dive output was wrong; the link target was absent. This was
diagnosed and fixed the same evening in **`73747e6`**, which added chain step
**7c** (`build_guides.py`, after the dives so `{{dive:...}}` tokens resolve,
before index + link-verify) so the chain is self-sufficient on a fresh machine.
The guides were then built by hand at 22:28 -- but the gate was never re-run,
which is the only reason the failure outlived its fix.

Post-hoc verification (2026-08-04): `verify_article_links.py --ship` clean (400
files, 392,534 hrefs, no broken internal refs); `verify_no_unicode_dashes.py
--ship` clean; `verify_overnight.py` checks [2/5]-[5/5] green independently
(97/97 dive dirs fully fresh, opponent counts 21..89, 61/61 ML guides fresh).
The bake had been published; the live site was confirmed serving the guide
URLs (HTTP 200).

**`publish_website.sh --dry-run` is not a drift detector** (found while
closing this out). It regenerates the guides and `index.html` at the top of
*every* invocation, dry runs included -- so the run that measures the delta
first rewrites the files it is about to compare. `rsync -a` keys on size+mtime,
not content, so those rewrites always re-send. A dry run therefore reports a
standing ~18-path "delta" that can never reach zero: `index.html` /
`cups.html` / `support.html` were verified byte-identical to the live copies
(md5), and the guide pages differed only in an embedded `Last regenerated
<date>` stamp that the rebuild itself had just bumped. Nothing had drifted;
the push done today was a no-op re-send. To actually check drift, compare
content (md5 against the live URLs, or `rsync --checksum`), not a dry run.
Side effect of the same design: the public `Last regenerated` date on the
guides tracks when someone last ran publish, not when the methodology
changed.

Two tooling fixes fell out of the reconstruction:

- **`overnight_redive.sh` `LOG_DIR` hardcoded `userdata/logs/2026-04`**, so
  every chain since April filed its log under an April directory (the July bake
  included). That also mis-sorts `verify_overnight.newest_chain_log()`, which
  globs `*/overnight_*.log` and sorts by path -- a July log filed under
  `2026-04/` ranks below a May log filed correctly. Now derived from the clock.
- **`verify_overnight.py` had no way to record a resolved failure.** Check
  [1/5] reads the historical status line and greps the chain log, so a fixed
  failure stays red forever; doctoring either file to force green would falsify
  the gate, and a permanently-red gate is how a real failure later gets waved
  off. New `docs/chain_resolutions.toml` records the resolution instead: pinned
  to ONE chain log plus a step label, carrying `fix_commit` + `verified`, and
  **printed** as `RSLV` rather than silently suppressed. It expires on its own
  (the next chain writes a new log filename that no entry names), and an entry
  naming the current log that matches no `[FAIL]` line is reported as a *stale
  resolution* and fails the gate -- so a typo'd label can't ship as a live
  suppression rule. Tests in `tests/test_verify_overnight_resolutions.py` pin
  the expiry and evidence-required properties; gate now ALL GREEN, rc=0.

## 2026-07-16 -- 5 PvPoke bug reports filed upstream (TODO item closed)

Michael filed the long-pending PvPoke bug reports (drafted 2026-06-11,
`docs/pvpoke_bug_reports.md`): pvpoke/pvpoke issues **#378** (Aegislash
Gyro Ball over Shadow Ball; selfDebuffing blanket-flag root-cause
candidate), **#379** (Morpeko one-way form change; Chansey 2v2 repro),
**#380** (BattleState dead dominance pruning + opponentShields
constructor typo), **#381** (initializeMove buff-adjusted DPE
overwritten in resetMoves), **#382** (opponent bestChargedMove pinned
to init-time form stats -- filed as an intent question). Every draft was
re-verified same day against pvpoke master `10fd1a6e4` by an
adversarial verify/refute/dedup workflow (21 agents), then rewritten in
Michael's voice per his style pass (no em dashes, no directive prose,
Impact only where non-obvious, battle-rating numbers dropped where the
site couldn't reproduce them). Two drafts did NOT go: the CPM-table
overflow was RETRACTED (PvPoke's cpms covers L1..55; the KeyError 52.0
was our table, DEVELOPER_NOTES divergence item 3 corrected), and the
needsBoost dead-code report was reframed to a retired-or-returning
question and held back. Open loose end: pvpoke.com's single-battle UI
showed 429 where headless engine runs show 510 for the SB-only
knife-edge cells (same code, data, inputs; both vintages) -- recorded in
the drafts doc header, unexplained. Key commits: `9943862` (re-verify +
filing guide), `8eb0360` (same-day order + opener), `19aef45` (MGL
style pass + number drop), `51a638c` (Report 5 reframe/hold).

## 2026-07-08 -- matchup-fingerprint clusters shipped site-wide (render-only)

The dive "experimental analysis" block (banding stats + 1-D score-gap
clusters) is retired, replaced by a **Matchup clusters** section as the
first block of every dive's Dive Analysis collapsible. Methodology from the
2026-07-04..06 cluster re-evaluation (reports repo,
`gopvpsim-cluster-methodology-2026-07-05.html`): per even-shield scenario,
IVs are fingerprinted by which sharp-marginal matchups they win (win-rate
2%-98% opponents), clustered bottom-up (Hamming/average linkage, silhouette
K under a parsimony floor), and explained via three stat-plane panels
(atk/def, atk/hp, def/hp), a gains/trades-away cluster summary, per-cluster
win-rate grids, in-sample depth-3 stat rules, and a matchup-flip-threshold
table with named/UNNAMED authored-anchor flags. Zero re-sim: two full
95-blob replay re-renders (131.8 + 129.2 min, 95/95 OK each).

Key commits: `477b8fb` pure-numpy pipeline (`scripts/
deep_dive_matchup_clusters.py` -- deliberately no sklearn/scipy; unique-
pattern weighted linkage + exact full-population silhouette for byte-stable
re-renders; cross-checked against the sklearn reference, incl. a reference
bug found: its single-stat flip accuracies are inflated on tied stat
values); `58bbd8f` section wiring + retirement of all five old surfaces
(alpha-chk block, clusterGaps DATA, cluster-chk checkbox, engine.js
overlay, orphaned renderers); `bcb47f3` 24 adversarial-review fixes (31
agents; e.g. degenerate constant flip rules no longer render as candidate
anchors); `cec8070` pass 2: owned-mon gold-star overlay in the panels
(collection paste + best-buddy aware), legend-name word-wrap (closes the
TODO legend-overflow item), and a "Matchup cluster" main-scatter color mode
(featured-moveset/default-IVs only, honest fallback note otherwise);
`8df0ba1` pass-2 review fixes (headline: a skeptic agent CDP-hover-tested
the panels live and caught svg-on-gl star hovers resolving to the wrong
spread -- now scattergl + y-nudge per the c0e782d precedent).

Also shipped: a 43-finding staleness audit + fixes across all 7 Reader's
Guides (most rot predated this work: the 2026-06-25 Male->Female reference
repoint broke both worked examples), a new **Matchup Clusters** guide
(`guides/matchup-clusters/`, promoted to authorship=both), two screenshot
retakes, and a new `pvpoke_cells_exact` sync sentinel so the how-this-works
guide's 170-exact/37-divergence claim can't drift. JS entry points for the
new section: `_mcRenderRoot` / `mcSelectScenario` / `mcRefreshAll` in
`deep_dive_engine.js`.

Known non-blockers at publish: `overnight_status.txt` still ends with the
2026-07-07 17:01 chain FAIL (guides dir did not exist when that chain
verified links -- ordering fixed in `73747e6`; the live tree passes the
same gate), and verify_overnight's ML-guide freshness check flags the
render-only batch window by design (ML guide articles were not touched).

## 2026-07-03 -- bug-hunt round-2 fixes + hunt2 merge + Equinox Cup pilot
*(entry added retroactively 2026-08-08 when the completed narratives were
groomed out of TODO.md; verbatim writeups in docs/TODO_archive.md)*

Round-2 non-engine fixes landed on main: **F1** (`57137e4`,
migrate_cache used-set unions form-change swapped-in moves, adversarially
verified complete), **F2 doc** (predicate-caveat recorded), **BP-1**
(`2931d1d`, power-0 breakpoints return [] instead of ZeroDivisionError --
was silently dropping every Aegislash-Shield GL anchor), **BP-2**
(`cc70593`, CLI forwards shadow multipliers into damage math),
**JIT-COV-1** (`22c0a0b`). The **hunt2 engine batch merged** (`2a63b65`:
NB-1 selection freeze, FC-1 Aegislash revert energy, OMT turns_planned
divisor, would_shield-as-documented; battle.py byte-identical to the
audit-passed engine), plus post-merge **JIT-COV-2** (`02627fe`) and
**PROP-1** (`fe2c443`); the OMT-forced cold re-dive was the 2026-07-06/07
bake (closed out 2026-08-04). The anchors.py engine-hash question was
ruled BENIGN. Same day: **top-N Phase 1** (`b8b561e`/`f5741a3`,
client-side opponent filter) and the **Equinox Cup pilot Phase 2**
(gopvpsim `aa8dac8..3c153fb`, gobattlekit `0c1bd5c`: cup rankings
loader, recipe + committed pool, --cup labeling overlay, flat
<species>-equinox-cup slugs + cups index, threshold-export collision
guard; five pilot dives; audit report in the reports repo). Also the
limited-availability enumeration research confirmed all seven floor-10
assignments with no additions (Michael ratified; shadow-legendary gap
closed same week).

## 2026-06-28 — cold re-dive complete (engine bug-hunt + cache-rework batch shipped)

The pre-launch engine batch plus a full cold re-dive landed. The bake ran
2026-06-28 01:55–11:49 (`overnight chain SUCCESS`, 153 files / 239k hrefs,
no broken internal refs) on an engine carrying every fix below; no post-bake
commit touches an engine file (battle/moves/pokemon/_dp_jit/formchange) — later
commits are render/JS/docs/orchestration/comment-only — so the published site
is on the trusted engine. Root-cause writeups for the engine fixes live in
DEVELOPER_NOTES ("Resolved engine divergences" / "engine bug-hunt #2–#7"); this entry
is the dated "what shipped" record.

**Engine fixes** (all in main before the bake, each test-pinned):

- **bug #1** fire_now double-fire CMP gate -> `cmp_atk` (`582f7d7`) — the
  missed 10th shadow-CMP site. Shadow-XOR only; measured 35/20,178 cells,
  6 winner flips, max margin 273.
- **bug #2** float32-truncated damage constants (`f1538ff`) + shadow-def
  `float32(5/6)` (`805cdc3`). Boundary-scattered -> this is what forced the
  cold bake; every other fix rode it for free.
- **bug #3** farm-down must stack self-debuffing moves (`50e8cd2`); pinned
  by `test_bug3_farm_stack`.
- **bug #4** slayer-cache key includes `focal_max_level` (cache-rework,
  `slayer_cache` v4).
- **bug #5** bandaid[929] no-bait swap documented as an INTENTIONAL
  divergence (`cdcef73`).
- **bug #7** `_cm_debuf_delta` dead str-vs-int branch (`30fd819`).
- two port-fidelity micro-fixes: bandaid[910] index + `buffApplyChance`
  float coercion (`68ad233`).
- a focal that STARTS in an alt form now gets native form stat buffs
  (`b52250e`).

**Cache-rework bundle** (merged `fbbc3ad`; design
`docs/design/2026-06-27_cache_rework_design.md`): energy plane
(`sweep_cache` v6, `--compare-energy` serves warm); per-column engine STAMP
+ `migrate_cache.py` predicate invalidation; ML/dive merge onto the shared
`iv_sweep` (`WonSetCache` retired — this also moots the old "WonSetCache
stores scores" and "ML guide re-bake perf" follow-ups); `gc_cache.py` N-1
vintage GC. The "warm bug-#1 re-dive" follow-up was MOOTED: #2's float32 fix
forced the bake cold, so #1 rode the cold bake rather than a warm migration.

**Session-6 dive-output fixes** (rode the bake): best-buddy toggle on every
GL/UL page, no-op where provable (`7a72394`); shadow opponents get their own
PvPoke-default IVs (`5b474a3`, flips UL Mimikyu vs Shadow Raikou 2-2 from
470 loss to 707 win); IV-scanner `maxLevel` single-sourced (`9f55e38`);
`owned_breakdown.py` same-class fix (`786d437`).

**Open verification gate** (carried to TODO as P1): rendered-output sanity
checks of the session-6 fixes — Registeel no-op toggle + "(no change)" hint,
Carbink active L51 sweep, UL Mimikyu vs Shadow Raikou flip.

## 2026-06-12 (evening) — S7 cleanup pass (arc COMPLETE)

The perf+correctness arc's gated cleanup session (Michael's
2026-06-11 greenlight; register = deep-review §I + TODO "Deferred
cleanup" + S6 leftovers). Three commits (`41ecbb8`, `ae679d0`,
`559967f`), ~1,100 net lines deleted across 35 files. Deletions only
— the deep_dive.py split refactor is its own future session.

- **20 dead scripts deleted**: analyze/augment_deep_dive
  (SCORES_GZ-incompatible fossils superseded by replay blobs),
  audit_chargedlog_fixtures (superseded by audit_oracle_harness),
  clean_ryanswag_dump, measure_html_size, retrofit_3_dives.sh
  (+ chain_status 'retrofit' preset), and the entire retrofit
  patch_dive_* set except chain-live patch_dive_species_narrative.
  Kept per the register's UNCLEAR call: check_sableye_energy_lead,
  summarize_perf, scripts/moves.py.
- **Static `generate_html` deleted** (~390 lines + the only
  rendering.hover_text consumer): the non-interactive path had been
  crashing on a NameError since ~S1 with nobody noticing. `--html`
  now implies `--interactive`. Legacy-JSON `load_thresholds` (zero
  callers since the TOML registry) went with it.
- **E12 `intended_pruning` removed** from the DP insertion helpers,
  `pvpoke_dp`, and the JIT kernel (signatures in lockstep). Zero
  consumers, and the mode was drifted — it compared only
  hp/energy/shields where PvPoke's (dead) check also compares buffs,
  so enabling it would have pruned wrongly. Default behavior
  unchanged (oracle harness 161 exact + 37 documented; benchmark
  3,293 sims/s vs 3,160 baseline).
- **L8 `breakpoints.cmp_threshold`** + orphaned `_floor2`;
  **`evolution_lines.get_final_form`** (tests converted to
  get_final_forms; sentinel 914→912); **D11 set** (re-export
  aliases, screen_n double-assign, write-only focal_in_opponents,
  unused slayer-worker base-stat params, unused opponent_name
  param); **R14 `_group_sort_key`**.
- **CACHE_VERSION bumps** (sweep 1→2, slayer 2→3): worker code in
  scripts/ is outside the engine source hash; standing rule after
  the 2026-06-10 near-miss. Engine-file edits also rotate the sweep
  cache's source hash — post-S7 dives run cold (budgeted by the
  gobattlekit pipeline's overnight batch).
- **legacy/historical/backcompat grep audit**: nothing further
  actionable; remaining hits are protected gobattlekit seams
  (as_legacy_dict, user_collection schema — its threshold pipeline
  actively consumes them), live CLI surface, or documentation. §I
  consolidations (L6/L11/L15/D9/D14/R11/W8/W10/T8) deferred to the
  split session / natural feature sessions — see TODO.
- S6 leftover: empty `shadow-sableye-power-gem-great-league/` orphan
  dir removed.

## 2026-06-12 (afternoon) — cross-repo parity fixes + plotly cache + site re-render

Same-day follow-ups after the S6 publish, from gobattlekit's
2026-06-11/12 deep review (its sections F/J flagged three items for
this repo; each was verified against current code before changing):

- **CP4 — level-aware CP-cap matching** (`3928b31`): `match_mons`
  ignored the mon's actual level, so an over-leveled mon (e.g. a
  level-30 Tinkaton) was reported as a GL qualifier with stats it
  can never have (power-ups are one-way). `best_level` /
  `ivs_to_stats_at_cap` gained `min_level`; the JS port mirrors it;
  verify_js_parser passes on the 2,296-mon personal fixture. Two
  test fixtures carried fictional level-26.5 Tinkaton rows — made
  legal (25.5).
- **CP13 — shared-final evolution merge** (`3928b31`): the
  family-wide visited set kept only the first root's chain to a
  shared final, so Burmy (Sandy)/(Trash) never mapped to Mothim.
  Ported gobattlekit's fix (their `2256a80`): visited LEAF
  evolutions still terminate each path; same-final lines merge
  members. CP9/CP12 (dep extras split, injectable data layer,
  shared parity corpus) recorded in TODO "Shared user_collection
  module".
- **Plotly.js version-keyed local cache** (`62eb4de`): every
  `--standalone` render re-downloaded the pinned 4.35MB
  plotly-2.35.2.min.js; now cached at `~/.cache/gopvpsim/` (atomic
  write, cache key = pinned filename so it can never go stale).
  Warm-cache replays touch no network.
- **Site re-rendered + republished** (Michael): all 20 dives via
  replay_analysis.py (~2 min/dive — blob unpickle + split-file
  renders dominate; the 5.8s S5e figure is smoke-dive-render-only)
  to pick up the CP4 JS-port fix in the paste-box, then
  publish_website.sh --push. Live site verified byte-identical to
  local.

## 2026-06-12 — S6 closeout: archive diff, spot-checks, site published (arc S6 DONE)

Judgment half of the S6 landing, after the morning repair below:

- **Dewgong RyanSwag-archive diff** (`002fd1d`,
  `docs/validations/2026-06-12_dewgong_gl_vs_ryanswag_redive.md`) —
  the only re-dived species with a local archive (published Stunfisk
  is the regular form, not Galarian). Delta vs the 2026-04-25
  side-by-side: Umbreon's pool return revives the article's atk
  axis with updated numbers (101.08/104.84 vs 2022's 101.79-102.81);
  the mirror-synth tier (Dewgong Mirror Bulk, 140.61 Def + 152 HP,
  7/9 vs rank-1 SP) lands inside the article's 138.28-141 range and
  closes the 04-25 TOML-anchor recommendation; Greedent def
  reproduces (137.56/138.91 vs 137.53-139.25); the June Drill Run
  rebalance put the article's moveset back on our landing page.
  Conformance C1-C8 pass. No sim/renderer action items.
- **Spot-checks of the 2026-06-11 ship-alongs** on the fresh full
  dives: mechanical checks (71-mon pool rows incl.
  Sylveon/Primeape/Umbreon, Aegislash Shield+Blade opponent rows
  everywhere, scanner-export buttons, Slayer Builds hoist callout +
  rarity badges, mirror-synth flavor tier) verified from the HTML;
  interactive checks (clipboard export, sort-vs-collapse, legend
  rewire, moveset-switch fallback) verified by Michael in-browser.
- **Site published** via `scripts/publish_website.sh --push`
  (Michael, 2026-06-12) after a clean dry-run through both ship
  gates. Live site verified (new index + fresh Dewgong page).
  Publish notes drafted around the three stacked score-shift
  reasons: 66→71 pool refresh, arc S1-S5, 2026-06-11 engine fixes.

Arc status: S1-S6 done; only S7 (cleanup, greenlit 2026-06-11)
remains.

## 2026-06-12 — S6 chain landing repairs + overnight verification tooling

The 2026-06-11 S6 re-dive chain completed all 20 dives in 3h45m but
died at the first post-dive step: `generate_article.py`'s freshness
gate (correctly) refused to run because the rebalance changed moveset
enumerations, leaving 52 old-pool `index_m*.html` split files as stale
orphans beside the fresh dives. Manual repair: orphans quarantined to
/tmp, post-dive steps (article, 5 comparisons, Aegislash draft, site
index, gates) run by hand. Three latent bugs surfaced and fixed:

- **compare_loadouts matcher order-sensitivity + broken deep links**
  (`d9fa744`): loadout→dive-HTML matching now treats charged moves as
  a set (rankings reorder them on rebalances; sim is order-blind), and
  flip-badge `#opp-<slug>` deep links are gated on the anchor actually
  existing in the dive HTML (dives only emit ids for opponents with a
  matchup-flip boundary; 21 broken links on the Forretress 4-way).
- **Em-dashes in ship surfaces** (`32f243f`): 5 guide body.md sources
  + the Aegislash narrative template; newly flagged because the
  2026-06-11 gates went tree-enumerated.
- **Stale split-orphan prevention** (this entry's commit):
  `deep_dive.py` now deletes `{stem}_m*.html` siblings it didn't just
  write (`_remove_stale_split_siblings`, both split and single-file
  paths), so the chain-killer class can't recur. 3 unit tests.

**Form-change oracle depth (pre-publish gap fill).** Each form-change
species previously had exactly one oracle opponent (Azumarill), and
two live-on-every-dive surfaces had no 9-cell coverage at all:
Blade-as-focal (the Blade→Shield reversion-on-shielding path) and
opponent-side Aegislash. Added 4 matchups × 9 cells to the audit
harness (Blade vs Azumarill, Azumarill vs Shield, Mimikyu vs Medicham
— 9/9 PvPoke-exact, Morpeko vs Galarian Stunfisk where the Aura Wheel
type flip changes effectiveness class) + offline fixtures in
`tests/test_form_change_oracle.py`. Every divergent cell traced to a
known mechanism before pinning: PvPoke bug #3 (its Aegislash throws
Gyro Ball over strictly-better Shadow Ball — including two winner
flips where PvPoke's Aegislash loses fights ours wins), bug #8
(Hangry stickiness), and one near-KO plan-choice cell where PvPoke's
hold-for-double-Shadow-Ball plan is genuinely better (cluster closed
as not-fixing). Reversion mechanics verified PvPoke-identical
(Pokemon.js changeForm swaps stats AND the fast move both ways).
A fifth matchup covers UL Aegislash (Tinkaton vs Shield at PvPoke's
default level 50 — pinning levels on both engines exposed that
best-buddy level 51 yields a level-39 Blade instead of 38, a
different Pokémon, which masqueraded as 9 false divergences until
the harness gained per-side `level` pins; the 8 real xfails are
bug #3 + Tinkaton-side plan timing, winner agreeing in all 9).
Audit baseline 153→198 cells (161 exact + 37 documented). The
tracing also surfaced a REAL bug: `scripts/battle.py`'s
`make_battle_pokemon` never attached form change (same class as the
arc-S1 dive-worker bug) — every form-change CLI sim ran formless;
fixed by routing through `from_pokemon`. Harness gained `--only
SUBSTR` for triage.

New tooling: `scripts/verify_overnight.py` — one-shot morning check
aggregating chain status, dive-dir freshness (mixed-vintage/orphan
detection), opponent-pool sanity markers (Sylveon/Primeape/Umbreon
prove the post-rebalance pool loaded), and both ship gates. Documented
as the morning check in `overnight_redive.sh` + the arc plan's S6
landing checklist. Suite 847p+14xf (sentinel 858→861).

## 2026-06-11 — Fable 5 deep codebase review + 39-commit fix day

A six-agent read-only review of the whole codebase
(`docs/reviews/2026-06-11_fable5_deep_codebase_review.md`, `7b30cbe`)
followed by fixing every finding actionable outside a dedicated
session. The in-flight S6 chain was killed mid-morning because two
confirmed bugs tainted its output; the re-dive relaunches on this
state. Personal narrative: `docs/validations/2026-06-11_deep_review_and_fixes.html`.
Suite ended 841p+14xf; oracle audit re-baselined at 153 cells = 136
exact + 17 documented (all 17 = the one intentional near-KO plan
cluster); benchmark 3,327 sims/s vs the 3,160 gate.

**Publish-blockers (the chain-kill trio):**

- **D1 `ab26a1c`** — interactive scenario expansion moved BEFORE
  Phase 2: the mirror-slayer iteration / archetypes / threshold
  auto-discovery had been running on 1v1 only while pages display
  all 9; at nS=1 the S2 graded metric degenerated and the pool cap
  blew ~40x.
- **L1 `92dd629`** — anchor resolution never applied shadow
  multipliers (opponent side via the ' (Shadow)' suffix, focal side
  via build_auto_anchors): BP anchors vs shadows ~20% too strict
  (published Sylveon card anchor resolved 145.7 vs the true 121.44),
  bulkpoints too lenient.
- **E1 `d371951`** — buffTarget='both' applied the generic buffs
  array to both sides: each Obstruct RAISED the opponent's defense.
  Pinned by a 9-cell Obstagoon/Azumarill harness fixture.

**Engine-fidelity round (oracle-driven, every step gated):** E2
buff-meter ported as PvPoke's exact float accumulator (`434fece` —
real first-proc bug for Crunch/Night Slash); E3 wouldShield
selfAttackDebuffing override (`ae44c43`); E4 signed DP stage deltas
(`b20fd0f`); E5 lethal slot-1 bait gate (`6fac7f9`); E6 disguise
break via pre-shuffle cheapest only (`bc533c7`); E7 TTL energy cap
dropped (`e53483d`); E8 held-reference cache keys (`034434b`); E9
near-KO JIT overflow sentinel + Python fallback (`4f40250`); E14
timeout divergence documented-not-matched (`87d77c1`, Carbink-mirror
probe; 240s = the real 3v3 MATCH timer — port as match state if team
sim ever lands).

**Two falsified "intentional deviations"** (both extra conditions
the reference lacks, both with plausible comments — deviations need
traces, not reasoning): the OMT KO-override's self-debuffing
exclusion (`632f637`; Snorlax/Obstagoon margin cluster, one wasted
Counter per shields-down endgame with a Superpower/HJK/Draco closer)
and the bait-wait hold's self-debuffing gate (`4d315ba`; Snorlax
9/9 exact, MG/Florges log byte-identical, three jellicent log-only
audit pins vanished).

**Dive pipeline / caches:** D6+R4 form-matched shadow mirrors +
sibling-form synth bail (`bb5cbcf`); D2/D3+D12 slayer-cache keys
(iv_floor, buff fields, engine+gamemaster hashes) + atomic cache
writes (`b1fc6da`); D5 canonical-tuple reference dedup, D7
silent-failure logging, L5 data.py corrupt-cache/atomic, W2/W7
chain_status year+digit fixes, D13 shebang (`03b5397`); D4 replay
blobs carry the variant registry (`8ef1bd9`); L3 speciesIds resolved
via the gamemaster map — Farfetch'd/Mr. Mime/Ho-Oh no longer
silently skipped (`3156373`).

**Render honesty (replay-diff verified):** R5 tier-card HP-rider
coverage, R2 flavor losses gated on real cohort win rate, R13 stat-
note heuristics (`0856ab8`); R9 banding crash guard, L10 league-key
case, W5 article sibling-alignment guard (`b9db11d`); W1 format_md
indent/escaped-pipe/code-span fixes (`a749d93`); W8 index
longest-prefix species slugs (`045d46f`); W9 publish gate enumerates
the whole site tree — instantly caught 75 baked em-dashes (renderer
strings fixed) + 31 stale anchors that clear on rebuild (`598f5ee`);
JS trio W3/W4/W6 (`e302759`).

**Features landed same day:** Notable-IVs "Copy for IV scanner"
buttons emitting gobattlekit user-threshold JSON (`b97113f`); slayer
signal-loss 4+3 hybrid — saturated-parent callout + rarity-coded
badges, Oinkologne-verified, ~360KB/dive lighter (`2629fde`);
monitor watch-hints at dive/chain startup (`77fd880`).

**Test infrastructure:** conftest pins the data-cache TTL (pytest
can no longer refresh it mid-chain); strict divergence xfails;
JIT↔Python parity test; MG-vs-Florges passing shield-gate fixture;
Mimikyu/Morpeko reuse rows; UL matchups added to the oracle audit
(`66c3ee9`, `73239fb`, `0cfb925`, `043cc03`). Suite 772 → 855
collected.

**Docs:** 7 paste-ready PvPoke bug-report drafts
(`docs/pvpoke_bug_reports.md`, curated: Mimikyu-timing retracted,
bestChargedMove premise debunked, CPM-overflow added); Annihilape
validation 102.9-floor closed as unrecoverable; E11 bandaid[866]
mechanism corrected.

## 2026-06-10 — Engine round 3: +37.5% single-core (perf+correctness arc S5)

Four commits (`4c38c6a..d4d8ed2`), each gated on full suite + oracle
harness + the canonical benchmark; net 2,295 → **3,160 sims/s**
(new regression-gate baseline in DEVELOPER_NOTES), dive-level
interactive sweeps ~+33% (Tinkaton GL smoke, 21-24k sims/s).
Engine behavior bit-identical against live PvPoke throughout —
S5 changed where values are computed, never what they are.

- **S5a `4c38c6a`** — `_calc_turns_to_live` JIT'd
  (`_dp_jit._calc_ttl_jit`) with defender-side int64 buffers rebuilt
  alongside the damage cache (no per-call asarray — the 2026-04-07
  round-3 false-start fix). Only +1.8%: numba dispatch eats most of
  the tiny-kernel win; kept for exactness + scaling headroom.
- **S5b `40b0168`** — DP stage tables compute only REACHABLE rows:
  root row reused from the damage cache; all rows alias root when no
  charged move has a chance-1 atk-stage delta; one-sided fill
  otherwise. The 9-row rebuild was ~97% of all damage computations.
  +8.2% on the (near-worst-case, Rage-Fist-carrying) benchmark.
- **S5c `840bbd8`** — bestChargedMove selection + farm-down constants
  (bestCycleDamage, min_cycle_thr, debuf swap) precomputed in
  `_ensure_dp_cache` (key-stable inputs only); bait-wait + bandaid
  chain array-ified (~20 dict/closure sites → cm_dpe/cm_self_debuf/
  cm_self_buff/cm_energy/cm_dmgs_root). raw_dpe == actual_dpe ==
  cm_dpe identity collapsed the two closures. +20%, the session's
  big win. Bandaid[866]'s `_cached_damage` OMT-side-effect subgate
  untouched (intentional divergence, DEVELOPER_NOTES).
- **S5d `d4d8ed2`** — explicit JIT signatures, eager compile at
  import (disk-cached), +2-3%, warm import 0.74s.

Full writeup: `docs/perf/2026-06-10_s5_engine_speedups.md`. Arc
scorecard updated (no-buff sweep now ≈11.4x vs the morning-of-
2026-06-10 state). S6 re-dive runs cold-cache (engine hash changed —
expected).

## 2026-06-10 — Sweep disk cache + replay-from-saved-state (perf+correctness arc S4)

Two iteration-speed features, both exact-by-construction:

**Per-opponent-column sweep disk cache** (`scripts/sweep_cache.py`,
`iv_sweep(use_sweep_cache=...)`, on by default in the CLI,
`--no-sweep-cache` to disable). A sweep decomposes into independent
per-opponent score columns, so the cache keys each column by
(focal species/league/shadow/moveset/iv_floor/scenarios/bait mode +
engine-source hash + gamemaster content hash) × (opponent species/
shadow/resolved IVs/level/moveset). Columns store raw float64 per-IV
scores (canonical iv_meta order) under `~/.cache/gopvpsim/sweep/`, so
hits are bit-identical to fresh sims. An unchanged dive command re-runs
all-hits (smoke: 16/16 columns, 0 sims, 113s → 53s wall — remainder is
slayer iteration + render); a pool edit sims only the new/changed
columns. Engine edits auto-invalidate via the source hash (battle.py,
_dp_jit.py, moves.py, formchange.py, pokemon.py) — no manual version
bump to forget. Old key-dirs accumulate; clear with
`rm -r ~/.cache/gopvpsim/sweep` when disk matters. avg_score now sums
per_opp in canonical (si, oi) order so float accumulation is identical
regardless of cache-hit pattern.

**Replay-from-saved-state** (`scripts/replay_analysis.py`). The HTML
render tail of `main()` is factored into `render_dive_html(state)`;
the dive dumps the full render-input state (moveset data + scores,
thresholds, slayer result, narrative, registry) to
`userdata/replay/*.replay.pkl.gz` right after sims complete
(`--no-replay-dump` to skip; ~1MB smoke / ~10MB website-scale blob).
`replay_analysis.py BLOB [--html OUT]` re-renders the dive through the
exact same code path in seconds-to-a-minute instead of a full re-sim —
the renderer/analysis iteration loop the inline-HTML-editing workflow
was approximating. Verified: replayed HTML is byte-identical to the
original dive's, single-file and split-moveset modes both.

Byte-identical verification flushed out two pre-existing run-to-run
nondeterminisms, both fixed: `_opp_colored` (deep_dive_narrative.py)
keyed colors off builtin `hash()` (PYTHONHASHSEED-randomized per
process) → md5; SCORES_GZ embedded the gzip mtime header → `mtime=0`.

Also fixed pain point #7 (project_post_ship_cleanup_pain_points):
`_STAT_NP_CACHE`/`_SCORE_NP_CACHE` in deep_dive_analysis.py keyed by
`id()` of host dicts with no liveness guarantee; entries now pin the
host dict (strong ref) and identity-check on read, so id reuse is
impossible and a future dive-A-vs-dive-B path stays correct.

Tests: +6 (tests/test_sweep_cache.py — column roundtrip/shape/key
separation, iv_sweep end-to-end second-run-0-sims + bit-equality +
incremental pool edit vs no-cache ground truth, replay dump/load
roundtrip; sentinel 729→735). Engine files untouched — no bench/oracle
rerun required.

## 2026-06-10 — Damage-signature dedup in IV sweeps (perf+correctness arc S3)

Sweep sims now dedup per-opponent by **damage signature**: the audit
of battle.py/_dp_jit.py established that focal stats enter a battle
only through (1) floor-quantized damage tables both directions (per
stat-stage where a stage axis is movable), (2) the 3-way sign of the
pairwise atk comparison (engine uses `>`, `>=`, `<`, `!=`), and
(3) integer max HP. Profiles matching on all three vs a given
opponent fight bit-identical battles; one representative sims, the
score fans out. New `scripts/deep_dive_signature.py` (vectorized,
bit-exact mirror of `moves.damage`, form-change aware: per-form
tables from `build_form_change_state`'s per-IV alt stats — the S1
hazard note); `iv_sweep` dispatches (representative, opponent) pairs;
`--no-signature-dedup` restores the per-profile path; dedup factor
logged per sweep.

**Verification** (`scripts/verify_signature_dedup.py`, full sweep
both ways, raw-float equality across 774,144 cells per species per
mode, 21 opponents incl. Aegislash (Shield) opp-side, all 9
scenarios): EXACT for Azumarill (4.50x dedup / 4.07x wall-clock),
Tinkaton bait+nobait (2.23x / 2.13-2.16x, identical grouping both
modes — policy independence confirmed), Aegislash (Shield) focal
(1.43x / 1.36x — more than claws back S1's per-IV expansion, exactly
this time). Full writeup: docs/perf/2026-06-10_signature_dedup.md.

Tests: +5 (tests/test_signature_dedup.py — bitwise damage_vec parity,
every-member-vs-representative score equality for Tinkaton and
Aegislash, axis movability; sentinel 724→729);
tests/test_dive_worker_form_change.py updated to the pair-based
worker contract. Engine files untouched (read-only audit) — no
bench/oracle rerun required.

## 2026-06-10 — Mirror-slayer redesign: archetypes + tie-explosion fix (perf+correctness arc S2)

Interactive design session with Michael; his four decisions: replace
the HTML section, fractional-wins + score-tiebreak round metric,
top-mirror cohort as the primary CMP denominator (Nash secondary),
retire the Atk/Bulk/CMP Slayer labels.

**Archetypes are now the first-class output.**
`build_slayer_archetypes` (deep_dive_slayer.py, replaces
`categorize_slayers`) classifies the FULL IV space, sim-free:

- **Anchors-First Slayer** — clear the max achievable number of
  counted anchor parents, then rank by Top-Mirror CMP% / atk.
  Explicit TOML parents always count; auto parents only when
  selective (<50% pass rate) — the slayer-card signal-loss fix.
- **CMP-First Slayer ("lab mon")** — top-N max-atk spreads with a
  clears-vs-sacrifices anchor checklist; no anchor required.

The Nash iteration is demoted to producing the mirror opponent
population: new `all_scores` export (dense per-IV mirror wins vs the
converged pool) feeds the archetype rows and makes the winsMirror
y-axis dense (4096 values vs ~30); the Nash cohort survives only as
the secondary "Nash CMP %" column (JS "Mirror Slayer CMP %"
unchanged). Top-Mirror CMP% computed Python-side with the same
semantics as the JS (2dp rounding, ties-as-beats, top-50 by avg
score, self included).

**Tie explosion fixed.** Round metric is graded — per-opponent credit
= scenarios won / scenarios counted (the Matchups Kept formulation,
`bb6f63e`), avg-score tiebreak; `_cut_pool` honors
`--mirror-slayer-pool` exactly except on exact metric ties. Smoke
measurement (Tinkaton GL, pool 30): Round 1 = 29 opponents × 2,978
profiles ≈ 86k sims vs the old 2,756 × 2,978 × 9 = 8.2M (~95× cut);
slayer phase 20.7s and no longer dominates the dive budget.

**HTML.** "Mirror Slayer Iteration" section replaced by "Slayer
Builds": two compact archetype tables (Anchors/CMP% columns, badge
walls with per-anchor tooltips, 100-row hard cap with an explicit
dropped-count note), iteration diagnostics collapsed, Level-3
sub-anchor distribution kept. Per-row `data-anchors` attributes and
the filter-panel JS/CSS deleted — the Jumpluff 60.7MB-table mechanism
is gone. Scatter star-diamonds, Notable IVs composites, and the
collection table now key off the two archetype names (plumbing was
name-agnostic). docs/concepts.md vocabulary updated.

Gates: 710 passed + 14 xfailed (sentinel 722→724; +3 new tests, −1
retired); engine files untouched so no bench/oracle rerun required.
Smoke HTML: /tmp scale, 2.97MB, tables capped, dense mirrorWinsByIv
confirmed.

Watch item for S6 re-dives: Tinkaton's Anchors-First cohort is broad
(1,349 IVs clear the max-cleared parent count) — ranking makes the
top rows meaningful, but if broad cohorts recur, consider requiring
all counted parents or tightening the selectivity gate.

## 2026-06-10 — Form-change plumbing in dive workers (perf+correctness arc S1)

The deep-dive sweep/slayer workers (and the phase-1 moveset screen)
constructed `BattlePokemon` directly from effective stats, so
`_form_change` was always None — every published Aegislash / Mimikyu /
Morpeko dive simmed those species without form mechanics, on both the
focal and opponent side. The engine itself was always correct (oracle
suite); the dive pipeline never opted in.

Fix: IVs + level are threaded through the sweep profile tuples,
`opp_cache` entries, and slayer opponent tuples; workers call the new
`gopvpsim.formchange.attach_form_change` (also the canonical path
inside `BattlePokemon.from_pokemon` now). Form-change species sweep
per-IV instead of per-stat-profile because alt-form stats depend on
raw IVs + level (Blade whole-level rounding) — measured cost 1.1-1.35x
more sims, confined to those species. Form-swapped move dicts are
copied rather than shared from the global gamemaster tables (a mirror
battle would otherwise cross-contaminate `_cached_damage` between the
two sides). Slayer disk-cache `CACHE_VERSION` bumped 1→2.

Verification: `tests/test_dive_worker_form_change.py` pins worker ==
`from_pokemon` equivalence (focal side, opponent side, slayer mirror)
and the PvPoke-harness-verified 773 cell. Smoke dive (Aegislash
(Shield) UL, 10 opponents): top-IV avg score 237.9 → 390.7, with
def-IV differentiation the no-form-change baseline couldn't see.
Gates: 708 passed + 14 xfailed; benchmark 2,254 sims/s (baseline
2,278, −1.1%); oracle harness 98 exact + 10 documented divergences.

Side finding: non-interactive `generate_html` crashes with a
`NameError` (pre-existing, unrelated) — logged in TODO under the
existing "non-interactive is strictly worse" item.

## 2026-06-07 — HTTPS on the website + Oinkologne NAIC re-dive

**HTTPS.** `mglerner.com/pogo-dives/` now serves over HTTPS via a free,
auto-renewing DreamHost Let's Encrypt cert (per-domain, so it covers
`/pogo-dives/` automatically) plus force-HTTPS. Confirmed in-browser: a
dive page loads over HTTPS with no mixed-content warnings and the Plotly
scatter renders. Mixed-content scan of the built `userdata/website/` tree
came back clean and required no generator change or republish: all 77
files containing `http://` are false positives (~5400 XML namespace
identifiers like `http://www.w3.org/2000/svg`, an ESRI attribution `<a>`
inside Plotly's unused basemap config, and a Plotly WebGL error string).
Grepping for real loads/links (`src="http://"` / `href="http://"`)
returns zero hits; Plotly is inlined at build time, not pulled from a CDN
at runtime. `publish_website.sh` is unaffected (rsync over SSH, not HTTP).

**Oinkologne NAIC re-dive.** Re-dived Oinkologne (Male + Female) GL
against the NAIC-meta cohort once PvPoke's rankings included it, and
published. Full reproducible procedure (cache invalidation, pool build,
re-dive, article refresh) is preserved in memory file
`project_oinkologne_naic_redive.md` for the next NAIC-style cycle.

## 2026-06-06 — Full oracle harness audit + Morpeko form-toggle (PvPoke bug #8)

**Oracle harness audit.** New `scripts/audit_oracle_harness.py` drives
all 12 hand-typed PvPoke-oracle matchups in `tests/test_battle.py` x 9
shield combos (108 cells) through both our sim and
`scripts/pvpoke_trace.js`, comparing score / winner / chargedLog. Result:
98 exact matches (confirming no hand-entry typo ever crept in), 6
documented Aegislash bug #3 divergence cells (intact), and 1 new finding
(Morpeko, below). Re-run anytime: `python scripts/audit_oracle_harness.py`.

**Morpeko form-toggle (PvPoke bug #8).** The audit flagged 4 Morpeko
cells whose chargedLog tagged a throw "Full Belly" where PvPoke said
"Hangry". Root cause: PvPoke implements Morpeko's `type: "toggle"` form
change as one-way (it sticks in Hangry after the first charged move),
whereas the real game toggles Full Belly <-> Hangry after every charged
move (Michael verified in-game: enters every battle in Full Belly at
start AND switch-in). Ours is the correct two-way toggle. Score-neutral
across this oracle, which is why the score-only test never caught it.
Kept per the CLAUDE.md divergence policy; pinned by a chargedLog
regression assertion on `test_morpeko_vs_azumarill_form_change` and a
known-divergence marker in the audit script. Full writeup in
DEVELOPER_NOTES.md §8.

## 2026-05-17 — Dropped UL Aegislash dives (HSH Discord review, S2)

**What:** Removed every UL-Aegislash surface from the site:

- `userdata/website/aegislash-blade-ultra-league/`
- `userdata/website/aegislash-shield-ultra-league/`
- `userdata/website/comparisons/aegislash-blade-vs-shield-ul/`
- `userdata/website/articles/aegislash-form-change-guide-ul/`
- `comparisons/aegislash-blade-vs-shield-ul.toml` (source TOML)
- UL entries in `scripts/run_website_dives.py`,
  `scripts/write_aegislash_narrative.py`'s `LEAGUE_INFO`, and
  `scripts/overnight_redive.sh`'s UL render steps
- UL deep-dive / article comment references in
  `thresholds/aegislash_{shield,blade}.toml`

**Why:** An HSH Discord member flagged UL Aegislash as non-competitive in his
2026-04-26 review, with confirmation from his UL-player contacts.
Per the review: "I asked for second opinions from people who play
UL, and they agree that UL Aegislash is not real." We agreed —
keeping a stale-data UL surface live (where the simulation
produces numbers but the species itself isn't a live PvP option)
risks misleading readers who land on the page without context.

**Reversal cost if UL Aegislash becomes viable later:** small.
The deletion is purely site-state + scripted-config; the sim's
form-change mechanics (`src/gopvpsim/formchange.py`) still handle
Aegislash transformations in both leagues and there are no
correctness tests gated on UL Aegislash. To re-add: restore the
two `run_website_dives.py` entries, the `LEAGUE_INFO['ultra']`
block in `write_aegislash_narrative.py`, the two `overnight_redive.sh`
UL steps, and the `comparisons/aegislash-blade-vs-shield-ul.toml`
file from git history.

## 2026-04-23 — Slayer IVs "of yours" table: column-header tooltips

**Retrofit follow-up on the Mirror CMP reframe (2026-04-22).** The
Top IVs table's three mirror-adjacent columns already carried `title=`
hover text via the `help` field on `_summaryColumns()`. The Slayer IVs
"of yours" table rendered via `renderSection` extras had no equivalent,
so the same two columns (Top-Mirror CMP % and Matchups Kept) were
bare.

**What shipped:**

1. Three module-level `HELP_*` constants in `scripts/deep_dive_engine.js`
   (`HELP_MIRROR_SLAYER_CMP`, `HELP_TOP_MIRROR_CMP`,
   `HELP_MATCHUPS_KEPT`) so the Top IVs and Slayer IVs tables share
   one source of truth. The emitted HTML still inlines the full text
   per `title=` attribute, but the JS source no longer carries three
   copies of each string.
2. `renderSection` extras schema extended with an optional `help` field
   that renders as `<th title="...">`, matching the Top IVs pattern.
3. `scripts/patch_dive_slayer_help.py` — retrofit patcher, idempotent
   via `SLAYER_HELP_v1` fingerprint, partial-match safe. Applied
   in-place to all 41 shipped HTMLs under `userdata/website/*/` so
   the live site picks up the tooltip without re-diving.

Single commit: `c3edb14`.

## 2026-04-22 — Mirror CMP % semantic reframe + Highlight IVs scatter

**Arc trigger:** on Tinkaton UL the original "Mirror CMP %" column
wrapped `DATA.mirrorCohortAtk`, which collapsed to 160 entries all
at atk=142.8509983 (Nash converges on the 15/0/0 L50 atk corner).
Users sorting by CMP saw only the niche slayer-optimal build path,
not a general-purpose mirror target. Reframe splits the old column
into three semantically distinct metrics and adds a scatter
highlight tool for arbitrary IV lookup.

**What shipped (11 commits):**

1. `6dcc571` — Core reframe. Rename `Mirror CMP %` →
   `Mirror Slayer CMP %` (keeps the Nash-cohort semantic but labels
   it explicitly as niche). Add `Top-Mirror CMP %` column (cohort =
   top-50 same-species IVs by active battle score in THIS dive; IV
   counted in its own cohort so denominator stays at 50; returns a
   meaningful 0-100 spread). Add `Matchups Kept` column. Add
   "About these metrics" collapsible `<details>` box above the Top
   IVs table explaining all three metrics + the overfit-slayer
   tradeoff story + when-to-invest heuristic. Ships
   `DATA.mirrorOppIdxs` server-side so mirror-opponent identification
   handles shadow/form pools correctly.
2. `bd226f9` — Extend Slayer IVs "of yours" table with the two new
   columns. Adds `extras.cls` hint to the collection-matches table
   schema; wrap CSS tidy so Slayer type and Also in columns break
   cleanly without blowing column widths.
3. `32a1c9d` — Fix inert Show/Hide and sort buttons on
   collection-matches tables (pre-existing bug; handlers were
   IIFE-scoped and `window.*` registration was missing).
4. `a771c4e` — Scatter highlight-IVs feature. Text input below the
   plot; matching IVs render as red diamonds, other traces dim to
   ~30%. Handles two hover-routing gotchas: Y-nudge opposite to
   Yours overlays, and skip highlighted IVs from user-overlay ring
   traces (hollow circle-open hit detection routed cursors wrong).
5. `6c19e7f` — Collapse multi-mon `Yours (N)` hover block to one
   CP-list line. Was vertical-clipping the tooltip against the plot
   bottom edge for owned IVs with 2+ CSV records and full
   matchup-diff blocks. Single-mon IVs retain full detail.
6. `2b1af06` — Fix MaxListenersExceededWarning on legend handlers.
   Plotly's graphDiv is an EventEmitter that persists across
   `Plotly.react`; `gd.on()` was accumulating listeners every
   `updateView`. One-shot `_legendHandlersAttached` guard.
7. `02d9eba` — Shrink Yours-other / Yours-notable ring markers
   (size 9→6 / 13→9, opacity 0.9→0.7 on "other"). No hover/symbol/
   text changes.
8. `81db37d` — Move Highlight-IVs strip from top control strip to
   below the plot, right-aligned. Tightens the eye path from "I see
   a diamond I want to investigate" to "let me type a different IV."
9. `bb6f63e` — Matchups Kept: fractional expected-wins credit.
   Original "avg score >= 500" rule produced only 5 unique values
   across 4096 Tinkaton UL IVs; majority-of-scenarios still gave
   only 7. Final: per-opponent credit = `(scenarios won / nSel)`,
   summed across non-mirror opponents. Reduces to integer count for
   single-scenario mode; yields 70 unique 0.1-bins across 4096 IVs
   in the default avg-across-9 mode. Spot check confirms the metric
   now ranks 15/11/11 (rank 16) ahead of 15/14/8 (rank 161) —
   previously both tied at 31 with no signal.
10. `939162e` — Polish Matchups Kept About-box prose: drop
    implementation-footnote comparing fractional credit to thresholds;
    replace with a user-facing explanation of the fractional value.
11. `f9d760e` / `f5325e2` — added + reverted: attempted to add a
    `scripts/redive-shipped.sh` helper, but `scripts/overnight_redive.sh`
    + `scripts/run_website_dives.py` already do that work (plus article
    regen, comparison rebuild, link verify). Use the existing chain
    instead.

**Re-dive validation:** full overnight chain 2026-04-22 evening
exercised every shipped dive against the new JS; 12 dives + 2
Aegislash auto-articles + Oink CD article + comparison pages +
link-verify in ~8h.

## 2026-04-21 — S11 + S12: HTML dive file-size reduction (~40%)

**Motivation:** pre-ship, the Oinkologne GL m1 dive was 46 MB
uncompressed; the Oink files became actively annoying to open in a
browser or diff. Originally scoped as post-ship in the post-S5 arc
(S11-S12), fast-tracked when the file size crossed the
annoying-to-use threshold.

**What shipped (4 commits):**

1. `f839e65` — S11: audit + measurement harness. `docs/s11_html_size_audit.md`
   is the byte budget writeup: 87k `title=` attributes on anchor
   badges collapse to 1.6k unique values (18 MB of pure duplication
   on Oinkologne). Six ranked reduction approaches, recommendation
   narrows to R1 (tooltip dedup) + R2 (external shared plotly).
   `scripts/measure_html_size.py` reports uncompressed + gzip-6 +
   title-dedup projection + plotly inline bytes per file for
   before/after diffs.
2. `1fe232a` — S12-R1: dedup `title=` tooltips. Unique tooltip bodies
   get emitted once into `DATA.tooltips`; each inline `title=` becomes
   `data-t="<short-id>"`. A `DOMContentLoaded` pass walks `[data-t]`
   elements and populates `el.title` from the lookup; browsers show
   the native tooltip on hover, no custom positioning. A/B on a
   scale-matched 10-opp/1-moveset Oinkologne dive: 38.12 MB →
   26.07 MB (-31.6% uncompressed, -99.98% of `title=` bytes).
3. `5ad2d4b` — S12-R2: `--shared-plotly DIR` flag. Third mode of
   `_plotly_script_tag()`; plotly.min.js is downloaded to DIR once
   (idempotent) and each dive emits a relative `<script src=...>`
   referencing it instead of inlining the 4.35 MB source. Overrides
   `--standalone` for plotly specifically. A/B on the same dive:
   R1 + R2 = 21.72 MB uncompressed / 6.09 MB gzip (-43.0% / -40.5%
   vs baseline). Hits the S12 target.
4. `e2e0737` — TODO.md housekeeping, closes the HTML file-size entry.

**Full-scale validation:** projection on the real 46 MB Oinkologne m1
dive is ~27.9 MB (-39.4%). Verified by the next overnight re-dive.

**Precedent:** prior HTML size cut (25 MB → 10 MB, 61%) landed
2026-04-10 as commit `cab0a72` (cap member-IV tables at 50 rows).
S11/S12 is the second cut, orthogonal to that one (targets the
title-attribute and plotly-inline tail).

## 2026-04-19 — Shape 2 migration: dive-side species narrative

**Arc trigger:** pre-Oinkologne-ship decision (2026-04-19) that the
primary narrative home for a species is the **dive**
(RyanSwag-style), not the CD article. Articles continue to exist
when they do something the dive can't — disambiguating multiple
forms (Oinkologne M/F, Aegislash Blade/Shield), shadow variants, or
alt-moveset meta forks (Forretress Volt Switch vs Bug Bite). For
Oinkologne the CD article stays because M/F comparison is its
justification, but the `[intro] / [meta_role] / [verdict]` prose
now lives per-form in the threshold TOML and renders at the top of
each dive.

**3-session arc (all shipped 2026-04-19):**

1. `41bbe6f` — Session 1: renderer plumbing + per-block `author`
   attribution schema. Pure code, zero content migration. Design
   decisions:
   - Render position: above the interactive dashboard (after the
     Related Article link, before the controls bar).
   - TOML schema: new top-level `[Species.intro] /
     [Species.meta_role] / [Species.verdict]` blocks in
     `thresholds/<species>.toml` — field-for-field mirrors of
     `articles/*.toml`'s same-named blocks so prose migrates
     by copy-paste.
   - Renderer: `deep_dive_rendering.render_species_narrative()`
     alongside the existing gold-zone code.
   - Author attribution: optional `author = "..."` field per block,
     rendered as a muted italic line; reader-visible distinction
     between AI-drafted and human-written prose.
2. `bf05538` — Session 2: per-form Oinkologne M/F narrative authored
   in `thresholds/oinkologne.toml` and
   `thresholds/oinkologne_female.toml`; article
   `[intro] / [meta_role] / [verdict]` slimmed to CD-event scope.
   Every Claude-drafted block carries
   `author = "Drafted by Claude (Opus 4.7), not yet human-reviewed"`.
   Overnight re-dive bakes the narrative into the regenerated
   Oinkologne dive HTMLs.
3. `bb021fa` — Session 3: Aegislash Blade + Shield narrative authored
   in `thresholds/aegislash_blade.toml` and
   `thresholds/aegislash_shield.toml` (Shield = canonical realistic
   play pattern; Blade = always-Blade diagnostic hypothetical).
   Out-of-band GL dives against the Orlando top-32 pool landed the
   same day (Blade 14:37, Shield 15:41); HTMLs force-patched with
   the narrative injection. Aegislash UL pair runs in the overnight
   chain and picks up the narrative natively. Stress-tests the
   renderer against mid-battle form/moveset swaps.

**Same-day polish:**

- `670f57b` — Per-block `authored_by` colour coding. Gold =
  expert-authored, muted = AI-drafted.
- `464e04a` — Unify all sidebar CSS on one rounded-pseudo-element
  pattern (cleanup that made the new narrative block visually
  consistent with the gold Expert Analysis zone).

**Documentation:** `docs/article_schema.md` "Per-block author
attribution" and `docs/threshold_schema.md` "Species narrative"
carry the full schema.

## 2026-04-18 — S10: Oinkologne CD article + Male-vs-Female comparator

**Ship session for the post-S5 Oinkologne arc.** Wires the Female dive
data into the CD article, adds a Male-vs-Female form-comparison
section, extends the site index, verifies bidirectional links, and
deletes the archived Lechonk CD prep plan.

**What shipped:**

1. `scripts/compare_loadouts.py` — MVP pairwise loadout comparator.
   Loadout-list-keyed data model (`loadouts: list[LoadoutSpec]`,
   pairwise deltas via `itertools.combinations`) so N=3 / N=4 are a
   renderer extension rather than a rewrite. MVP ships N=2 only.
   Output: `userdata/website/comparisons/<slug>/index.html` plus an
   importable `build_comparison_fragment()` that `generate_article.py`
   inlines.
2. `comparisons/oinkologne-male-vs-female.toml` — comparator spec for
   the Oinkologne CD arc.
3. `generate_article.py` — new canonical `form-comparison` section
   between Matchup Delta and IV Recommendations, gated on a
   `[form_comparison]` block in the article TOML. Absent the block the
   section drops out cleanly.
4. Site-index updated with both Oinkologne dives, the article, and
   the comparison page. (Site index at `userdata/website/index.html`
   is gitignored, so the edit is local-only by design.)

**Reconciliation vs `~/.claude/plans/archive/lechonk-cd-prep.md`:**

The archived Lechonk plan scoped six sessions targeting a JRE-style
prose article by 2026-04-22. The actual ship happened through the
post-S5 Oinkologne arc (S1-S10), with three documented scope shifts:

- **JRE-style prose → Python-generated spec sheet.** Rationale: JRE
  writes for money; shipping Claude prose mimicking his voice is not
  acceptable. Tracked in TODO.md "CD article generator" (2026-04-16).
- **One dive → Male + Female dives.** Oinkologne forms have
  meaningfully different base stats (186/153/242 vs 169/162/251);
  both receive Mud Slap on the same CD, so both need threshold data.
  Tracked in memory `project_female_oinkologne.md`.
- **No comparator → compare_loadouts.py MVP.** Added this session to
  make the Male-vs-Female section a reusable tool rather than inline
  article code. Tracked in memory `project_ab_comparator_timing.md`
  and TODO.md "Moveset / variant comparison tool".

Aegislash form-change dive (floating beat in the old plan) remains
pending under TODO.md "SwagTips narrative follow-ups".

Archived plan deleted post-reconciliation.

## 2026-04-15 — Forretress/Azumarill DP plan-selection (atk-stage fix)

**Context:** our Azu vs Forr (Sand+Rock) score matrix diverged from
PvPoke by up to +118 rating points, despite our DP tracking
`has_debuf`/`debuf_count` for dedup tie-breaks. Investigated with the
new headless Node harness (`scripts/pvpoke_trace.js`) which emits a
`termLog` of every DP terminal pushed.

**Root cause.** PvPoke's `BattleState` carries a `buffs` field (the
attacker's atk-stage delta) that accumulates as the DP stacks moves
with chance-1 self-atk buffs *or* chance-1 opp-def debuffs. See
`ActionLogic.js:519-535` — line 531 `attackMult -= move.buffs[1]`
effectively promotes an opp-def debuff to a self-atk buff inside
the DP. When a child state is popped, line 471 calls
`poke.applyStatBuffs([buffs, 0])` and recomputes
`moveDamage`/`fastSimulatedDamage` against the buffed atk. Our
`_DPState` held `cm_dmgs[]` and `fast_damage` fixed at root-state
values for the *entire* DP rollout, so stacked-ST plans never
accelerated and never terminated in our reachable-state space — our
DP accepted `[RT]+farm` at turn 13 instead of PvPoke's
`[SAND_TOMB, SAND_TOMB]` at stateTurn 10.

**Fix.** `_DPState` now carries an `atk_stage` field; `pvpoke_dp`
precomputes a per-stage damage table (9 rows, stage ∈ [-4..+4]) and
each child state indexes its own row for charged- and fast-move
damage. `cm_buff_delta[n]` = +1 for chance-1 self-atk-buff or
chance-1 opp-def-debuff and bumps `new_atk_stage` on throw (clamped
to [-4, +4]). `_dp_insert_ready` phase-1 dedup now requires equal
`atk_stage` so stacked-buff plans aren't merged away. `_dp_jit.py`
mirrors the change — kernel takes `cm_buff_delta`, `cm_dmgs_stage`
(9 x n_cms), `fast_dmg_stage` (9,), `root_atk_stage`, and the queue
arrays gain a parallel `q_atk_stg` slot.

**Scoreboard.** Azu/Forretress (Sand+Rock) now matches PvPoke 9/9
exact across all shield scenarios. 157 pytest + 27/27
`verify_pvpoke_harness.py` still green. Commit `141eee1`.

**Gotcha.** Raw gamemaster `buffApplyChance` is a *string*, not a
number. The initial `!= 1` comparison was silently false for every
move; the production check is
`float(m.get('buffApplyChance', 0) or 0) != 1.0`.

## 2026-04-14 — Form Change

Data-driven via gamemaster `formChange` field. Three form-change
families implemented:
* **Morpeko** — toggles Aura Wheel between Electric and Dark.
* **Aegislash** — Shield ↔ Blade swap (stats, moveset, level
  adjust).
* **Mimikyu** — disguise effect absorbs first unshielded hit; on
  break, applies -1 def stage.

Form changes DO affect opponent shielding (Aegislash Shield form
suppresses shields when damage < half HP) and baiting (Mimikyu
opponents break disguise ASAP with the cheapest charged move).

Oracle tests: Morpeko 6/9, Aegislash 1/9, Mimikyu 6/9 match PvPoke
exactly. Remaining mismatches were initially attributed to a "DP
cycle-timing" gap; that lead was subsequently closed 2026-04-15
(Azu vs Aegislash 0v0 now throws IB twice, matching PvPoke; all
9 0v0 form-change fixtures land on harness score). Plan file:
`quizzical-hatching-kahan.md`.

**Open follow-ups** (tracked in `TODO.md`): Mimikyu deep dive with
form-change narrative; Goodra / Aegislash test-drive dives for the
new SwagTips narrative renderer.

## 2026-04-14 — PvPoke divergence RESOLVED: selfBuffing flag scope

Our `selfBuffing` flag in `moves.py` now matches PvPoke's
`GameMaster.js:873` definition: guaranteed positive self-buffs AND
guaranteed opponent debuffs (`buffTarget="opponent"`,
`buffApplyChance==1`). Previously only covered self-targeting buffs;
workarounds in shield policy and bait-wait were removed. All 8
`selfBuffing` usage sites now use the broadened flag consistently.

## 2026-04-14 — PvPoke divergence RESOLVED: activeChargedMoves priority-shuffle

PvPoke's `resetMoves` (`Pokemon.js:711-787`) reorders
`activeChargedMoves` after the energy sort based on buff/debuff
properties. The priority-shuffle uses buff-adjusted DPE
(`initializeMove`, `Pokemon.js:849-864`) for one clause. Our code
now replicates all shuffle clauses in `pvpoke_dp`.

**Historical note (corrected):** Divergence 2 was originally
documented as "bait-wait DPE ratio uses `actual_dpe`, not
buff-adjusted DPE." This was incorrect. PvPoke's
`selectBestChargedMove` (`Pokemon.js:791-796`) *overwrites* `.dpe`
to raw `damage/energy` on all `activeChargedMoves` after the
priority-shuffle, so the bait-wait 1.5 ratio check
(`ActionLogic.js:843`) also uses raw `damage/energy`, same as our
`actual_dpe`. The buff-adjusted DPE only affects the
priority-shuffle ordering (lines 711-787), not the ratio check
itself. This paragraph is load-bearing — if you ever revisit
Divergence 2, it will explain why the "obvious" fix wasn't needed.

## 2026-04-09/10 — Stat-target reframing (SwagTips round 1)

Threshold Tier cards, matchup-flipping boundaries, HP co-conditions,
auto-derive from clean dives, scatter plot visual overhaul, HTML size
reduction. 26 commits. Key design decisions:

### Two kinds of threshold
- **Damage-tier boundaries** (from `_aggregate_flips_by_anchor`): the
  def/atk at which `floor(damage_formula)` steps by 1. Invariant to
  battle conditions (energy leads, bait policies). Come from Level 3
  anchor discovery.
- **Matchup-flipping boundaries** (from `_find_matchup_boundaries`):
  the def (+HP) at which the overall battle outcome flips win→loss.
  Usually higher than the damage tier because multiple damage reductions
  must accumulate. Depend on battle conditions — will shift when we add
  energy-lead sims. Both are shown: damage tiers in anchor-flip bullets,
  matchup boundaries in their own section + tier cards.

### Auto-derive path (no TOML needed)
`_auto_derive_tiers` consumes both anchor-flip records (atk-side) and
matchup boundaries (def-side). Tiers ranked by selectivity (fewest
qualifying IVs first); General excluded from scatter plot coloring.
Tinkaton clean dive produces tiers at ~143 def (≈an HSH Discord member GH Great),
~140 def (≈GH Good), ~138 def (intermediate). Validated against 4/6
an HSH Discord member findings.

### Open threads for next sessions
- **Atk-side matchup-flipping boundaries**: `_find_matchup_boundaries`
  currently only sweeps def. Should also sweep atk for species where
  atk breakpoints flip matchups (e.g. Annihilape Lickitung BP at 127).
  Same algorithm, different partition stat.
- **Energy-lead matchup boundaries**: damage tiers don't change with
  energy leads, but matchup boundaries do. Once we add energy-lead sim
  options (`--energy-lead 1` etc.), re-sweep matchup boundaries under
  those conditions. The two-layer display (damage tier + matchup flip)
  is designed for this.
- **Shadow / atk-weighted opponent IVs**: an HSH Discord member's Shadow Drapion
  (140.21 def) uses "attack-weighted" opponent IVs, not rank-1 or
  PvPoke default. Our system doesn't simulate arbitrary opponent IV
  spreads. Possible fix: `--opp-ivs custom:119.80` in the TOML or CLI.
- **HP co-condition on atk-side**: currently only def anchors try HP
  co-conditions. Atk-side anchors theoretically could too (HP affects
  whether a fast-move damage increase translates to a KO), but no
  known case warrants it yet.
- **CMP anchor schema shorthand**: an HSH Discord member's CMP thresholds
  (105.58 Corviknight, 105.79 Lickilicky, etc.) can't be expressed as
  CMP anchors without an IV-list spread. Need a `opponent_species`
  shorthand that resolves the opponent's rank-1 atk automatically.
  Listed in "Schema simplification" TODO.
- **HTML size**: down from 25 MB to 10 MB (base64 uint16 scores +
  Notable IVs member cap). Remaining 9 MB is packed scores. Further:
  delta-encode, drop non-displayed moveset scores, or serve gzipped.
- **deep_dive.py refactor**: now ~6000 lines. The extraction targets
  in the Refactoring TODO are still valid; this session added
  `_find_matchup_boundaries`, `_auto_derive_tiers` (matchup boundary
  path), `_probe_tier_cutoff_flips`, `_render_matchup_boundary_bullets`
  as new extraction candidates for `deep_dive_lib/boundaries.py`.

## 2026-04-09 — Structured IV categories (round 1)

Unified `IVCategory` framework abstracting over slayer categories,
threshold tiers, and their intersections. New "Notable IVs" HTML
section surfaces composite (slayer ∩ tier) cards and matchup
(opponent, scenario) cards with auto-generated tradeoff prose.
Annihilape `13/0/11` lands as the canonical example: "The sole Atk
Slayer that also clears the Top 5% threshold (hp≥139). Trades mirror
dominance (45/132 wins, vs 132/132 for the top Atk Slayer survivors)
for the Top 5% cutoff." Section is gated behind a "show only notable"
header checkbox (≤ 5% of cohort or ≤ 5 members, default on). Round 1
ships zero TOML changes — composite + matchup categories are
auto-derived from existing infrastructure. Bait dimension on
`matchup_conditions` is reserved (`None`) until the bait-axis sweep
TODO lands. Commits: `f3aa4ad` (dataclass + builder), `8ff4469`
(matchup branch), `79e2e87` (renderer), `b344356` (wire-in). Cross-ref:
"Hand-named composite categories via TOML" and "Bait-axis matchup
categories" in Deep-dive narrative for round 2 followups.

## 2026-04-08 / 2026-04-09 — Bulkpoint anchor system

Def-side mirror of `damage_breakpoint` anchors. Three precision levels
(L1 explicit, L2 reference-anchored via `above_def`, L3 discover-and-tag),
parser, resolver, auto-fallback, tests, docs, Annihilape TOML entries.
Bulk Slayer category gained dual membership (structural HP+def OR
clears at least one named bulkpoint). `ResolvedAnchor` generalized to
`target_stat` with `threshold_value` so the same passes() machinery
handles both atk and def side. Commits: `13665dc` (main feature +
brkp/blkp rename + tag UX + CLI args embed — should have been split,
see commit message), `8f9369d` (clarify ×N count in hover tooltip),
`7ed5765` + `967bb09` (Compact/Expand toggle for tag cells).

**Headline finding** from running the new system on Annihilape
explicit: the historical Lurgan Ape `def ≥ 102.9` floor is *not*
recoverable as a single (move, tier) bulkpoint. The next bulkpoint
above 102.9 is `shadow_ball ≤149` at def 103.34, but 0/66 of today's
converged cohort can reach it (max cohort def ~101.30). The 102.9
floor predates Rage Fist, so the threat-move set has shifted; today's
optimization trades def for atk and lands well below the historical
baseline. Don't promote anything to Level 1 from this enumeration —
follow up via Discord with an HSH Discord member to recover historical context
(see "Send an HSH Discord member a Discord message" in Analysis goals).

## 2026-04-08 — bp → brkp short-name rename

Renamed all anchor name slugs from `_bp_` to `_brkp_` so the
breakpoint short form is unambiguous against the new bulkpoint
`_blkp_` short form. The Python kind discriminator stays
`damage_breakpoint` (full word); only the slug-style short forms
changed. Touched anchors.py, build_auto_anchors, annihilape.toml
anchor table keys, tests, and docs. Part of commit `13665dc`.

## 2026-04-08 — Ultra-short anchor abbreviations + Compact tags toggle

Tag cells in slayer cards previously truncated badges horizontally
with `text-overflow: ellipsis` at 280px max-width, hiding most of
the badges past the first 2-3. Replaced with: (a) `derive_short_name`
function producing 3-6 char badge labels (cre, lic, mirb, lic↑lur,
c:lur, quasb...) with the long form preserved in the badge hover
tooltip, (b) cell wrapping enabled, max-width bumped to 480px,
(c) Compact/Expand toggle button at the top of the slayer card grid
that caps cells at ~2 lines via an inner `<div>` wrapper (the wrapper
is needed because `<td>` ignores `max-height` in CSS — fixed in
`967bb09` after the first attempt at the toggle didn't actually work).
Part of commit `13665dc` + the three follow-ups.

## 2026-04-08 — CLI args embedded in HTML output for forensics

`format_cli_args(args, parser)` builds the *fully-resolved* equivalent
invocation: every flag emitted with its actual value, including flags
whose value happens to equal the current parser default. Embedded in
HTML two places: a grep-able `<!-- CLI: ... -->` comment near the top
and a collapsed `<details>` footer at the bottom of `<body>`. Also
printed to console at startup as `CLI: ...`. Why fully-resolved
instead of literal user input: defaults can change between runs, so
a string that omits "default" flags becomes ambiguous when read later.
This is the forensic gold standard. Part of commit `13665dc`.

## 2026-04-08 — Slayer anchor system

The TOML threshold schema (`docs/threshold_schema.md`), anchor
resolver (`gopvpsim/anchors.py`), and anchor-tagged
`categorize_slayers` are all in place. Atk Slayer and CMP Slayer use
named anchors instead of vacuous median heuristics. Three precision
levels for damage_breakpoint anchors (L1 explicit, L2
reference-anchored, L3 discover-and-tag). Auto-fallback layer
synthesizes anchors at runtime when the user doesn't provide them
via TOML, gated per kind so explicit user input always wins. Commits
`beace47` (main) and `10a693c` (an HSH Discord member testimony incorporated
into thresholds/annihilape.toml + anchors tests).

## 2026-04-07 — Battle simulator perf optimization (round 1 + round 2 + chunking)

Real-world impact: ~9hr → ~6 min on a full Annihilape mirror slayer
deep dive workload. Stack of optimizations:
* Damage cache + DP hoisting — +51% throughput (commit `3596fb4`)
* Numba JIT on the near-KO DP loop — +40% throughput (commit `a57c39f`)
* Stat profile dedup in `iv_sweep` — ~1.7x faster Phase 2 (commit `6ccb124`)
* Slayer iteration: dedup focal & opponent IVs by effective stats
  (commit `579aef7`)
* Slayer iteration: keep all IVs tied at top win count (commit `eb145a2`)
* Chunk count bumped from `n_workers` to ~100 for finer progress
  reporting (commit `8498ec4`)

Round 3 (numba JIT for the entire inner sim loop) was deprioritized
after round 1+2 made the workload tolerable; fastmath was confirmed
a dead-end during the round 1 work.

## 2026-04-07 — Iterative slayer discovery (Nash-style mirror match)

`scripts/deep_dive.py --mirror-slayer` runs Round 0 (focal IVs vs
PvPoke default opponent) then iterates Round k (focal IVs vs round
k-1's top survivors), stopping on convergence or `--mirror-slayer-rounds`.
Survivors are classified into RyanSwag-style Atk Slayer / Bulk Slayer
/ CMP Slayer categories. Disk cache at
`~/.cache/gopvpsim/slayer/<key>.pkl` keyed on species/league/shadow/
moves/scenarios so re-runs are near-instant. Commits `43b8784` (main),
`75fa8ce` (HTML rendering), `9cabba7` (cache key fix), `3b9d5fb`
(metric/rounds/pool/show CLI flags), `0dfcc98` (validation doc).

## 2026-04-06 — IV deep dive script + interactive HTML

`scripts/deep_dive.py` simulates all 4096 IV spreads of a focal
species against meta opponents across moveset combinations, with
threshold-tier coloring, custom group support, and an interactive
HTML mode (`--interactive`) with moveset/scenario/opp-IV switching
dropdowns. Commits `f0253d5` (script), `a4d18e5` (interactive mode),
`30452c6` (PvPoke default IVs for opponents), `4c7bcf9` (legend
isolation, matchup hover), `6924b1a` (`--standalone` inline Plotly).
Doc reorganization in `0ce1229` (CLAUDE.md, TODO.md, DEVELOPER_NOTES.md).

## 2026-04-04 to 2026-04-06 — Battle simulator correctness (Mienfoo vs Medicham)

Several rounds of bug fixing brought the battle simulator into
agreement with PvPoke's reference output:
* Three turn-model bugs: 1-turn FM timing, faintSource, FM fire order
  (commit `e036670`)
* Buff/debuff implementation (commit `6145aaa`)
* Buff meter, pvpoke_simulate_shield, trace flags (commit `ead46c1`)
* ActionLogic.js post-DP bandaids, sort cms by energy, raw_dpe
  (commit `f4d0eb3`)
* DP queue insertion strategies, intended_pruning flag (commit `44f3215`)
* Shadow Pokemon support (commit `8c5fb65`)
* `wouldShield` buff reset ordering, CMP cancellation (commit `5b07790`)
* All 9 Medicham vs Azumarill scenarios match PvPoke (commit `008d8e7`)

### Mienfoo vs Medicham — FIXED (all 9/9), root cause

Two bugs specifically responsible for the Mienfoo vs Medicham all-9
pass:

1. **wouldShield buff reset ordering** (battle.py `would_shield`):
   The charged-move threat loop ran BEFORE resetting the temporarily-
   applied stat buffs, inflating damage predictions. PvPoke resets
   buffs first (ActionLogic.js:1136-1140), then evaluates charged-move
   threat (lines 1145-1165). Fix: moved the reset before the loop.

2. **CMP (Charge Move Priority) cancellation** (battle.py `simulate`):
   When both Pokemon fire charged moves simultaneously, the lower-ATK
   Pokemon's move should be canceled if it was KO'd by the higher-ATK
   Pokemon's charged move (PvPoke Battle.js:464-467). Our code had an
   exception that always allowed both to fire. Fix: track `charged_ko`
   set and cancel if `use_priority` and attacker was KO'd by a charged
   move.

## 2026-04-01 — pvpoke_dp charged-move policy

Implemented PvPoke's `ActionLogic.js` DP-based charged-move decision
policy in Python (`gopvpsim.battle.pvpoke_dp`). Commit `62b9cfb`.

---

# Resolved (deeper history)

* **Slayer Ape / Lurgan Ape IV analysis** — Resolved 2026-04-08 by
  an HSH Discord member Discord testimony. The community Lurgan Ape spread is a
  *historical floor* (`atk ≥ 127.2`, `def ≥ 102.9`) calibrated to a
  Lickitung breakpoint near atk 127.23, predating the Counter nerf,
  Rage Fist addition, and Low Kick buff. Our slayer iteration's
  convergence to atk 129.44 matches *current* expert advice (push
  higher than the Lurgan baseline for CMP wins and BP security against
  the mirror and Lickitung). The "we disagree with the community"
  framing in earlier analysis was wrong — we converge to current
  expert practice; Lurgan is a frozen historical reference.
