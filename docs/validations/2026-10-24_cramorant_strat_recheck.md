# PoGoDives strat re-checked against pvpoke_dp after the Minior port (pvpoke 38f70320d)

Checklist item B.3 of `docs/rebalance_checklist.md`: after a PvPoke engine
re-vet, confirm the PoGoDives strat still stands relative to `pvpoke_dp`.
The 2026-10-24 re-vet (DEVELOPER_NOTES "PvPoke re-vetting log") re-pinned
the digests at `38f70320d` and ported Minior; this is the deferred strat
leg, run the same day on engine hash `3d125a0e165f`. "Our strat" is the
PoGoDives Cramorant sheet v8 (`battle.py` `_POGODIVES_SHEET`), the only
PoGoDives overlay in the engine; `POGODIVES_CASE_SPECIES_PREFIXES` is
`('Cramorant',)`. There is no Minior strat: PvPoke's Minior rules (hold
energy under the shell, spare the shell) live inside `pvpoke_dp` and apply
to both tiers.

## Headline

- **The strat's margins did not move.** Lab grid at today's engine vs the
  pre-port engine (`87e73e3`, worktree): 0 of 2,430 PoGoDives-tier cells
  changed; 2 plain-tier cells changed, both UL Cramorant vs Dusknoir 1v2
  (470 -> 487, bait and nobait), and headless PvPoke reads 487. Net vs
  plain is +76 on both engines.
- **The shipped UL Cramorant page is not today's engine.** The port's
  TTL-order fix moved plain-tier cells against Dusknoir, Shadow Dusknoir
  and Seaking; PvPoke agrees with the new engine in every cell checked.
  The GL page probes were clean. The strict bar still passes from the
  tensors (720 cells, 0 failures), and the deltas on the moved slices
  barely change, but the page shows wrong plain-tier numbers (Shadow
  Dusknoir 0v0: a 509 win on the page is a 394 loss).
- **Minior on either side:** 2,304 GL cells (Minior (Core) and Minior
  (Core only) as focal and as opponent, 30 pool opponents plus two
  Cramorant builds, 9 scenarios x 2 bait modes): PoGoDives tier ==
  plain tier in all of them.

## Instruments and results

1. `cramorant_certify.py --league both --selftest 80` on the shipped pages:
   720 cells, 0 bar failures, 0 exemption violations; 800 random
   (IV, opponent, scenario, mode, bait) cells re-simmed through the
   production path, 800/800 integer-exact on both tiers. Raw: scratch only
   (the record file is written after a re-dive, per the runbook).
2. `cramorant_policy_lab.py --pogodives-verify --league both` at today's
   engine (`userdata/cramorant_lab/reverify_2026-10-24.json`, 2,430 cells
   per variant: GL 75 + UL 60 opponents x 9 x 2 bait, Peck / Dive + Fly,
   PvPoke default IVs):

       variant        W    D     L   net
       pg_lead40   1310  110  1010   +76   (all pg_* identical: lead is inert)
       baseline    1251  101  1078    +0

   Per start scenario (pg_lead40 vs baseline, win-cell delta / mean score
   delta): every GL slice >= 0; UL 0v1 -2 / +8.3 (the documented Dondozo
   single-spread cost, not an exception; `2026-09-12_cramorant_deep_vet.md`);
   UL 2v1 0 / 0.000 (exempt since 2026-09-10; it read -1.325 then). Same
   picture as the 2026-09-10 run.
3. The same lab at the pre-port commit (`git worktree add ... 87e73e3`,
   `PYTHONPATH` on its `src`): identical totals; per-cell diff above.
4. `cramorant_mini_sweep.py --check-tensor --stride 13`, both leagues,
   `index.html`, all nine scenarios, PvPoke-IV opponents, bait
   (`userdata/cramorant_lab/minisweep_check_2026-10-24.log`):

       GL: 9/9 slices integer-exact (both tiers), strat deltas reproduce.
       UL: 5/9 exact. Plain-tier mismatches, of 19,908 cells per slice:
           0v0 36   0v1 86   0v2 122   1v2 104   -- all Dusknoir,
           Dusknoir (Shadow) or Seaking. Strat deltas: unchanged except
           1v2 mean +35.542 -> +35.481 (the Dusknoir 1v2 gain is gone
           because plain now plays the same fight).

5. Headless PvPoke (`scripts/pvpoke_trace.js`, master `38f70320d`) on three
   moved UL cells, Peck / Dive + Fly, cap 50, PvPoke-IV opponents:

   | cell                                            | page | live | PvPoke |
   | ----------------------------------------------- | ---- | ---- | ------ |
   | Dusknoir (Shadow) 0v0, Cramorant 0/1/10         | 509  | 394  | 394    |
   | Seaking 1v2, Cramorant 1/1/14                   | 450  | 462  | 462    |
   | Dusknoir 1v2, Cramorant 11/14/15 (and 15/15/15) | 470  | 487  | 487    |

6. Full-resolution count of the moved cells (stride 1, the three
   opponents, every UL page x scenario, PvPoke-IV / bait):
   `userdata/cramorant_lab/minisweep_ul_dusk_seaking_stride1_2026-10-24.log`.
   45 slices (5 pages x 9 scenarios) x 12,288 cells (4,096 IVs x 3
   opponents): **11,793 plain-tier cells differ (2.1%)**, in 14 of the 45
   slices; 31 slices are integer-exact on both tiers. By page: `index.html`
   (Dive + Fly) 0v0 460 / 0v1 1,122 / 0v2 1,582 / 1v2 1,356; `m2` (Dive +
   Surf) 0v0 460 / 0v1 1,122 / 0v2 1,582 / 1v0 87 / 1v2 1,080; `m4` (Dive)
   0v0 80 / 0v1 1,122 / 0v2 1,122 / 1v2 558; `m1` (Hydro Pump + Surf) 1v2
   60; `m3` (Surf) clean. Every 1v1, 2v0, 2v1 and 2v2 slice is exact.
   On this three-opponent subset the strat deltas moved in five slices:
   mean on the 1v2 slices down by 1.3 (index), 3.1 (m2), 3.2 (m4) and 0.6
   (m1, whose subset net also went -36 -> -96), and m2 1v0 up (+20 -> +107
   net). Scaled to the full slices (about 245k cells each), those are
   shifts of at most 0.16 mean against whole-slice minimum margins of
   +11.14 mean / +8,377 net (UL 1v2) and +1.32 / +624 (UL 1v0), so no
   slice can cross the bar; the re-dive will re-certify it properly.

## Mechanism

Timeline diff of Cramorant vs Dusknoir 1v2 (default IVs) pre-port vs now:
identical through turn 34; the old engine threw Fly on turn 35 off 48
energy, the new one takes one more Peck (energy 56) and throws Fly on turn
37. PvPoke's decisionLog shows the same "optimizing move timing" fight.
That is fix 2 of the port (DEVELOPER_NOTES "Key implementation details",
TTL order): `turnsToLive` now walks the defender's frozen post-shuffle
charged order; before the port it walked the LISTED slot order.

| defender | listed                      | frozen (post-shuffle)       | ascending                   |
| -------- | --------------------------- | --------------------------- | --------------------------- |
| Dusknoir | Dynamic Punch, Shadow Punch | Shadow Punch, Dynamic Punch | Shadow Punch, Dynamic Punch |
| Seaking  | Drill Run, Icy Wind         | Icy Wind, Drill Run         | Drill Run, Icy Wind         |
| Lapras   | Surf, Ice Beam              | Surf, Ice Beam              | Surf, Ice Beam              |

Dusknoir's frozen order EQUALS its ascending order and it still moved, so
the migration-predicate clause TODO carried ("defender's post-shuffle order
!= its ascending-energy order") would have blessed these columns wrongly.
The sound clause for fix 2 is "either side's frozen post-shuffle order !=
its listed slot order". TODO "Minior -- open items" now says so; the
predicate as a whole still needs its proof.

## Consequences

- No strat change. Sheet v8 stands; nothing to re-tune.
- Cramorant UL must be re-dived before any Cramorant publish (the GL page
  showed no drift in these probes but rides the same engine bump).
- `cramorant_certify.py --check-record` would pass the stale UL page: it
  compares sha256 only, and the 5-per-page random selftest in the 09-28
  record had an ~8% chance per draw of landing on one of these opponents.
  Opened as a lens-grid input-freshness item in TODO (Cramorant block).

## Limitations

- The lab is one moveset at default IVs; the tensor probes covered
  `index.html` at stride 13 for one opponent-IV mode and one bait mode, and
  the three moved opponents at stride 1 on all five UL pages (item 6).
  Rank-1-IV and nobait slices, and the other opponents on the four
  non-default UL pages, were not re-simmed; the re-dive makes them right
  regardless.
- Pre-port means `87e73e3`; the pre-port lab numbers are not the 09-28
  bake's engine (`4b42f9d83690`) but the last commit before the port, which
  is the delta this check is about.
