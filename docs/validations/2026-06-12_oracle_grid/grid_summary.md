# GL top-20 oracle grid — results & mechanism classification (2026-06-12)

Setup: PvPoke GL rankings top-20 entries (shadows kept as separate
entries), default movesets via `get_default_moveset`, gamemaster
`defaultIVs.cp1500` levels/IVs pinned on BOTH engines, all 380 ordered
pairs x 9 shield scenarios = **3420 cells**. Ours:
`simulate(charged_policy=pvpoke_dp)`; reference:
`scripts/pvpoke_trace.js` (clone @ 9b7407782). Comparison contract =
score + winner + normalized chargedLog (same as
`scripts/audit_oracle_harness.py`).

Raw data: `results.jsonl` (one record/cell; produced by the
2026-06-12 scratch run in `scratch_oracle_grid/`, completed before
this session). Per-cell classification: `grid_classified.json`.
Probes: `probe_grid_result.json` (incoming-gate),
`probe2_grid_result.json` (incoming-gate + bestCM).

## Headline counts

| bucket                          | cells | %     |
| ------------------------------- | ----- | ----- |
| exact (score+winner+chargedLog) | 3086  | 90.2% |
| non-exact                       | 334   | 9.8%  |

Severity of the 334: 36 log-only (shield attribution), 120 log-only
(move identity/order), 148 score-differs-same-winner, 30 winner flips.

## Mechanism attribution (first match wins)

| mechanism       | cells | verified how                                                                      |
| --------------- | ----- | --------------------------------------------------------------------------------- |
| incoming_gate   | 12    | PROBE: reference-exact policy fixes all, breaks 0                                 |
| bestcm_estimate | 38    | PROBE: faithful selectBestChargedMove fixes all, breaks 0                         |
| shadow_cmp      | 204   | signature (atk-comparison predicate flips) + reference reading + decideLog traces |
| unknown         | 80    | —                                                                                 |

With both probe patches applied: **3136/3420 exact (91.7%), 0
regressions.** The two probe-verified families are mechanical port
errors with one-line-ish fixes (see incoming_gate_writeup.md).

### incoming_gate (12 cells, max |d| 159)

battle.py:200 routes incoming selfDefenseDebuffing moves through
wouldShield; Battle.js:1090 routes only `move.buffs && move.selfBuffing`.
All 12 cells are tinkaton<->malamar with Tinkaton holding shields
(Malamar is the pool's only Superpower carrier). Full writeup:
`incoming_gate_writeup.md`.

### bestcm_estimate (38 cells, max |d| 205)

The 2026-04-15 defender-bestCM shield gate (battle.py:214) keys on
`_estimate_best_cm` = max actual DPE, which returns SUPER_POWER for
Malamar. PvPoke's `selectBestChargedMove` (Pokemon.js:790-822) runs on
the shuffled activeChargedMoves and has a literal
`moveId != "SUPER_POWER"` carve-out (dpe edge must exceed .3, not .03)
— Malamar's bestChargedMove is FOUL PLAY there, so PvPoke never enters
the branch and always-shields. Affected: every X-vs-malamar /
malamar-vs-X cell where the defender Malamar held shields and declined
one in our sim (quagsire, quagsire_shadow, ninetales,
ninetales_shadow, seaking, feraligatr, kingdra). Note the .3 edge is
DPE-dependent: vs fighting-weak opponents (e.g. Lickilicky) Superpower
clears the carve-out in PvPoke too and both engines agree.

### shadow_cmp (204 cells; 30 winner flips incl. all 14 PvPoke draws)

Ours folds the shadow x1.2 into `.atk` (pokemon.py:195) and uses
`.atk` for every CMP-flavored comparison (battle.py:2312 use_priority,
2405/2432 action ordering, 677 OMT, 241 shield-cycle, 372/397/459 TTL,
1038 DP). PvPoke uses shadow-free `stats.atk` everywhere
(Battle.js:255/831/1116, ActionLogic.js:10/106/181/307); the shadow
multiplier exists only inside DamageCalculator/getEffectiveStat.
Two observable sub-effects, both confirmed in decideLogs:

1. **Base-vs-shadow same-IV mirror => PvPoke draw.** stats.atk equal
   => usePriority=false => Battle.js:454/471 lets a charged-fainted
   mon's same-turn charged move resolve => mutual KO, 500/500,
   winner=null (decisionLog: both Empoleons fire Hydro Cannon T22).
   We produce a winner. Pairs: empoleon, ninetales, quagsire, altaria
   base<->shadow (all their winner_flip + many score cells).
2. **Cross-species CMP flip.** Wherever x1.2 flips (or un-ties) the
   atk comparison: quagsire_shadow vs feraligatr [0,0] (PvPoke
   decisionLog: Feraligatr Hydro Cannon wins CMP at T11; ours fires
   Quagsire first; winner flips +-92), quagsire_shadow vs seaking
   [0,0] (+-182), ninetales_shadow vs malamar [0,0] (+-214), etc.

Tag is signature-based (cells whose pair's shadow-folded vs
shadow-free atk comparisons disagree), NOT probe-verified —
`use_priority` is computed inside `simulate()` and can't be patched
without editing the frozen engine. Some of these 204 cells may carry
secondary mechanisms. Design question before fixing: live-game CMP is
believed to ignore the shadow bonus (=> PvPoke right); verify, then
decide whether `.atk` should be split into damage-atk vs cmp-atk.

### unknown (80 cells: 50 score-diff, 30 log-only-moves), ranked

Worst-first by max |d| (both directions of a pair listed once):

1. **corsola_galarian <-> forretress [1,1]/[1,2]** (4 cells, |d| 159/117).
   Trace: after the first unshielded Sand Tomb, PvPoke-Forretress's DP
   plan is [Sand Tomb -> Rock Tomb] (decisionLog T26: "wants to use
   Rock Tomb after it uses Sand Tomb"); ours throws ROCK_TOMB first
   (shielded), then the fight unspools differently. Hypothesis:
   near-KO DP plan first-throw divergence (the known near-KO
   plan-choice family signature: same survival outcome, different
   first move under shields), possibly interacting with Sand Tomb's
   opp-def-debuff in plan scoring. Needs dpPlans diff
   (traces/corsola_galarian__forretress__1v1.json is saved).
2. **forretress <-> kingdra [1,1]/[1,2]/[2,2]** (8 cells, |d| 82/25/8).
   Same Forretress plan-shape smell (Sand Tomb vs Rock Tomb ordering).
3. **tinkaton <-> malamar shields-0-on-Tinkaton cells** (6 cells,
   |d| 60/49/18). Residue AFTER the incoming-gate fix: with Malamar's
   shields irrelevant, ours has Malamar throwing Foul Play early
   where PvPoke holds for Tinkaton's Gigaton Hammer first. Hypothesis:
   bandaid[910]/[918] stacking + defer interplay (note bandaid[910]
   index deltas flagged in the writeup) or activeChargedMoves-order
   sensitivity in the post-DP bandaid chain (our cms[] is
   energy-sorted; PvPoke's slot 0 is shuffled FOUL PLAY).
4. **quagsire <-> malamar [1,2] + 4 log-only** (|d| 29). Likely same
   bandaid-chain family as (3) (Malamar slot ordering).
5. **lickilicky <-> seaking 0-shield-side cells** (6 cells, |d| 13/12).
   Consistent small offset, log_ok mostly. Hypothesis: one extra fast
   move of chip before a charged throw — OMT/timing-grain family.
6. **seaking <-> azumarill 0-shield-side cells** (6 cells, |d| 11/10).
   Same shape as (5).
7. **ninetales <-> forretress [2,2]** (2 cells, |d| 8).
8. **forretress <-> malamar** (6 cells, |d| 4) + assorted.
9. **feraligatr-involved +-1/0 cells** (~10 cells, |d| <= 1, some pv
   score pairs sum to 999 vs our 1000). Hypothesis: score rounding
   semantics on fractional raw scores — cosmetic, not worth chasing.
10. **log-only-moves residue** (30 cells, d=0): Malamar 'Foul Play' vs
    'Superpower' identity swaps at equal score — activeChargedMoves
    slot-ordering cosmetics; plus quagsire/empoleon/seaking first-throw
    attribution order.

Note Forretress appears in 3 of the top-8 unknown clusters — a
focused Forretress (Sand Tomb/Rock Tomb plan-choice) localization
session would likely collapse most of the real unknown score mass.

## Files

- `incoming_gate_writeup.md` — primary finding, DEVELOPER_NOTES-ready
- `results.jsonl` — raw 3420-cell comparison records
- `grid_classified.json` — per-cell severity + mechanism
- `classify_output.txt` — human-readable classification dump
- `summarize_full.txt` — pair-grouped diff listing (pre-classification)
- `probe_incoming_gate.py`, `probe_grid_result.json` — probe 1
- `probe_bestcm_family.py`, `probe2_grid_result.json` — probe 1+2
- `classify.py` — classifier
- (scratch from the killed agent remains in repo `scratch_oracle_grid/`;
  untouched, do not commit)
