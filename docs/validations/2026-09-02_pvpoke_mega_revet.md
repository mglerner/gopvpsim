# PvPoke re-vet: the Mega Evolution update (7b96d91fb..56bc6a8b1)

Record for `docs/rebalance_checklist.md` **section B**, run 2026-09-02. This
is the document `tests/fixtures/pvpoke_engine_digests.json` points at; the pin
moved `78c64048a -> 56bc6a8b1` in the same commit as this file.

## 1. The commits, classified

Ten commits, of which four touch the battle engine.

| commit      | sim-relevant?      | what                                                                                                                                                                                      |
| ----------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `574aeb0da` | **YES**            | Mega Bonus damage multiplier; `hasThirdChargedMove()` flipped from `return false` to `hasTag("mega")`; ActionLogic + Pokemon.js generalized from `activeChargedMoves[1]` to `for i` loops |
| `feba66f47` | **YES**            | `supermega` tag (0 -> 13 species); ONE new ActionLogic block (shields-down anti-self-debuff)                                                                                              |
| `e86688bd1` | data               | 11 `extraChargedMoves` attachments; mega rankings; `calculateConsistency` (ranking-only, never on a battle path)                                                                          |
| `56bc6a8b1` | **YES**, ours only | `Ranker.js:524` `o.league = battle.getCP()` -> `==`. Not a battle change, but it corrupted shipped rankings we consume -- see section 5                                                   |
| `bd8c5d889` | UI                 | Mega Level selector                                                                                                                                                                       |
| `7d89192f7` | data               | Kalos starter megas released; Counter ETM on Mewtwo                                                                                                                                       |
| others      | UI / text          | version bumps, spacing, RSS                                                                                                                                                               |

`moves.json` is **byte-unchanged** across the range: 0 moves added, changed or
removed. The 13 `*_PLUS` move stat lines pre-date our baseline (they landed
2026-08-06 in `33fbe92d3`). So this is **not** a rebalance, and the MOVE-DATA
tripwire correctly did not fire.

## 2. Oracle audit

`scripts/audit_oracle_harness.py`, 243 cells:

```
before (our engine unchanged, PvPoke updated):  208 exact + 35 divergences
after  (this work):                             222 exact + 21 divergences, exit 0
```

The +14 comes from two independent causes, and the attribution was **measured,
not inferred** -- by building shadow copies of PvPoke's `src/js` with one block
reverted at a time and re-running the audit against each:

| PvPoke root        | OK  | known div | vanished | new mismatch |
| ------------------ | --- | --------- | -------- | ------------ |
| HEAD (baseline)    | 208 | 27        | 8        | 0            |
| `(a)` reverted     | 208 | 27        | 8        | 0            |
| `(e)` reverted     | 208 | 27        | 8        | 0            |
| `(f)` reverted     | 208 | **35**    | **0**    | 0            |
| all three reverted | 208 | **35**    | **0**    | 0            |

The all-reverted row reproduces the pre-update DEVELOPER_NOTES baseline
exactly, which is the positive control: the harness isolates the right thing,
and the gamemaster delta (17 pokemon entries, 0 moves) touches none of the 27
audited matchups.

- **+8, theirs.** Block `(f)` alone -- `ActionLogic.js:954`, predicate flipped
  from `!acm[i].selfBuffing` to `!acm[i].selfDebuffing`. Mechanism confirmed by
  move label via `pvpoke_trace.js`: Aegislash's first throw changes from Gyro
  Ball to Shadow Ball, score identical (`[374,625]` both ways, because the
  throw is shielded -- which is exactly why the score-only oracle never caught
  bug #3 and the chargedLog assertion did). This is the move-selection half of
  what we filed as pvpoke/pvpoke#378. **We did not change to earn these.**
- **+6, ours.** Our `_priority_shuffle` was missing clause 4 of the
  activeChargedMoves shuffle (`Pokemon.js:790`, the `aegislash_shield`
  forEach). Seven clauses were ported; there are eight. Adding it made all six
  divergent `tinkaton_vs_aegislash_shield` cells exact on score, winner AND
  chargedLog, and turned `azumarill_vs_aegislash_shield` (2,1)/(2,2) from a
  winner flip into a score+winner match. These had been annotated "PvPoke bug
  #3" for months; they were our bug.

## 3. AI / strategy changes (checklist step 3)

The rewrite is **not** a pure loop generalization. Per-block verdict, from a
line-by-line read of the diff plus executed 2-move and 3-move traces:

| block | site (HEAD)            | at n=2                                                                                    |
| ----- | ---------------------- | ----------------------------------------------------------------------------------------- |
| (a)   | ActionLogic.js:405-415 | **CHANGES** -- bait/debuff precedence flips, and `wouldShield(acm[0])` is newly evaluated |
| (b)   | :858-874               | identical                                                                                 |
| (c)   | :878-892               | identical                                                                                 |
| (d)   | :928-937               | identical                                                                                 |
| (e)   | :940-947               | **NEW BLOCK**, fires at n=2, no energy/HP/damage gate                                     |
| (f)   | :949-961               | **CHANGES** -- different predicate, not a generalization                                  |
| (g)   | Pokemon.js:752-833     | identical at n=2; **rotates** at n>=3                                                     |
| (h)   | Pokemon.js:2286-2330   | identical; ranking-only, not a sim path                                                   |

**Adopted:** the n>=3 generalizations of (b)(c)(d), the (f) INDEX half, and
the (g) rotate. All are provably no-ops at n=2, which the bit-identical oracle
grid confirms at each step.

**DECIDED 2026-09-02 (Michael): (e) and (f) ON, (a) OFF.** The n=2 semantic
changes in (a), (e) and (f)'s predicate. All three are implemented behind module knobs
(`_AL_FARM_BAIT_MERGE`, `_AL_SHIELDS_DOWN_ANTI_DEBUFF`,
`_AL_PREFER_NON_DEBUFFING`), defaulting to our pre-update behaviour, so the
decision is a one-line change and could be MEASURED rather than argued.

**A/B on our own engine**, top-60 focal x top-20 opponents x 9 shield cells
per league, PvPoke default movesets, 30,285 cells total:

| block | Great       | Ultra       | Master                          |
| ----- | ----------- | ----------- | ------------------------------- |
| (a)   | 0/9,918     | 0/9,747     | 0/10,620                        |
| (e)   | 0/9,918     | 0/9,747     | **76/10,620 (0.72%)**, 2 winner flips, worst delta 208 |
| (f)   | 0/9,918     | 0/9,747     | 0/10,620                        |

Block (e)'s Master cells concentrate on Xerneas (10), Togekiss (6), Zygarde
Complete (5), Florges (5), Sylveon (5), Zacian Crowned Sword (4) -- i.e.
species pairing a self-debuffing cheapest move with a non-debuffing
alternative, which is exactly its trigger shape.

### Outcome of the decision

Turning (e) and (f) on took the oracle grid from **222+21 to 226+17**, closing
the last four Aegislash cells:

  aegislash_vs_azumarill          (1,2) (2,2)   annotated for months as "the
                                                deeper near-KO plan-choice
                                                half of bug #3" -- they were
                                                not that
  azumarill_vs_aegislash_shield   (2,1) (2,2)   the chargedLog-only residual
                                                clause 4 had left behind

Both matchups now carry an EMPTY xfail set: all 18 cells exact on score,
winner AND chargedLog. The whole Aegislash divergence cluster is closed.

One test fixture moved outside the grid, and it also improved:
`test_bug3_farm_stack`'s Pinsir vs Cresselia (2,2), 681 -> 707. Pinsir carries
TWO self-debuffing moves (Close Combat + Superpower), so the OLD
`!acm[i].selfBuffing` test fired the shields-up swap and the new
`!acm[i].selfDebuffing` correctly does not. Re-captured against PvPoke: that
matchup went from 8/9 to **9/9 exact**, and 707 is PvPoke's own number.

So the corpus A/B *understated* the case for adopting: it measured 0/9,918 GL
and 0/9,747 UL for both knobs because its corpus used meta default movesets at
top-60 x top-20, which does not reach Aegislash Shield or Pinsir. Every cell
that actually moved, moved toward PvPoke.

Earlier, broader measurements from the n>=3 spec work (different corpus, incl.
randomized and non-default movesets) found (a) 0/135,000, (e) 60/1080 with a
610 max delta concentrated on Gigalith, and (f) 9/80,000 on Staraptor /
Galarian Zapdos / Shadow Hariyama. The two corpora agree on the ordering --
(a) is inert, (f) nearly so, (e) is the one with real reach -- and disagree on
which species surface it, which is a corpus-composition artifact (this one uses
meta default movesets only). Summary of both:

| block | our 243-cell grid | broader corpus                                                                         |
| ----- | ----------------- | -------------------------------------------------------------------------------------- |
| (a)   | zero              | 0 decisions changed in 135,000 n=2 samples                                             |
| (e)   | zero              | 60/1080 sims differ, max delta 610, concentrated on Gigalith / Gigalith-shadow         |
| (f)   | fixes 8 cells     | 9/80,000 randomized n=2 decisions change (Staraptor, Galarian Zapdos, Shadow Hariyama) |

Our own block-(f) counterpart (`battle.py`, bandaid[895]) still carries
upstream's OLD predicate. Note the asymmetry: PvPoke moved to US on the grid,
so we already agree there without changing anything; flipping our predicate
would only bite where `cms[1]` is self-buffing (new swaps, old does not) or
self-debuffing (old swaps, new does not), and the grid contains no such case.

**PoGoDives tier impact (checklist step 3, second half):** our strat is defined
relative to `pvpoke_dp`, and `pvpoke_dp`'s n=2 behaviour is unchanged by
everything adopted here -- the grid is bit-identical across the shuffle
rewrite, the slot-read fixes and the bandaid generalizations. Clause 4 DOES
move `pvpoke_dp` for Aegislash Shield specifically (toward PvPoke), so any
PoGoDives comparison involving Aegislash Shield predates that fix.

## 4. What we changed, and how each was verified

| change                                  | verification                                                                                              |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `MEGA_BONUS` + gate                     | 204/204 damage values vs PvPoke across 5 mega moves, including the `damageIfNotMegaMove` negative control |
| damage-formula DRY (`damage_constant`)  | grid bit-identical; operand order measured (0/400,000 realistic, 21,412/5,733,000 ulp-boundary)           |
| shuffle rotate + loop                   | 111/111 real PvPoke orderings; swap port fails 54/111                                                     |
| shuffle clause 4                        | oracle 208+35 -> 222+21                                                                                   |
| `_priority_cm` (was `_cheapest_cm`)     | fail-first test; old proxy wrong on 70/600 n=2 cases                                                      |
| `min_cycle_thr` -> `fastestChargedMove` | fail-first via a synthetic ordering (no real one discriminates)                                           |
| bandaid chain -> N moves                | 90 mega battle cells exact on score+winner+chargedLog                                                     |

## 5. A rankings-data hazard the tripwire cannot see

`Ranker.js:524` read `overrides.find(o => o.league = battle.getCP() && ...)` --
an assignment, always truthy, so `find` matched the FIRST element and mutated
it. Fixed to `==` in `56bc6a8b1`, but `rankings/all/` was **not** regenerated
in this range, so the shipped files still carry the corruption:

- `rankings-2500.json`: of the species whose UL and GL overrides genuinely
  differ, **65 report the GL-1500 moveset** and 0 report their own.
- `rankings-10000.json`: 34 own, 2 GL (`machamp`, `gyarados_shadow`), 3
  neither -- so ML is mostly but **not** cleanly unaffected.

We are currently consistent with pvpoke.com (the site reads the same file), so
nothing is wrong *relative to the oracle* today. The hazard is forward-looking:
when PvPoke regenerates with the fix, ~65 UL default movesets change under us
with **no gamemaster-hash bump** (the v7 hash is `md5(pokemon + moves)`), so
`migrate_cache.py --from-gamemaster` will not catch it and a warm cache would
serve columns simmed against the old defaults.

**Recommended guard (not yet built):** a dive preflight that hard-fails when a
resolved default moveset differs from the one its cached column was simmed
with. The sidecar already stores the moveset, so this is cheap, and it is
exactly the "input-freshness" cell of the pre-dive lens grid.

## 6. Still open

- Phase 4: adopt or reject the (a)/(e)/(f) n=2 semantic changes. Measurements
  in section 3; this is a judgment call, not a fact question.
- Mega roster construction for dives: the cup is titled "All Pokemon" and its
  1500 rankings carry 1198 entries of which ~55 are megas, so an opponent pool
  built from it rewrites non-mega movesets. Drift vs the open meta: 0 species
  through GL top-200, 11 through UL top-100, 13 through ML top-100.
- The five species excluded at 1500 only (`mewtwo_mega_x`, `mewtwo_mega_y`,
  `kyogre_primal`, `groudon_primal`, `rayquaza_mega`) must be applied by
  whoever builds that roster; pinned in `tests/test_mega_cup_registry.py`.
- **Not confirmed by Niantic:** the GBL Mega CP reduction for the GL/UL
  editions is published in wording only -- no formula, no granularity, no stat
  basis. PvPoke models the mega formats as ordinary CP-capped cups. Any GL/UL
  mega spread we publish rests on that unpublished rule and must say so.
