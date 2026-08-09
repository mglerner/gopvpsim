# would_shield / always-shield inconsistency: diagnosis and disposition -- 2026-08-09

> **Verdict: the TODO's "our own bug" framing is FALSIFIED; no behavior
> change should ship.** The predict-vs-policy mismatch is real but shared
> with PvPoke (faithful-port structure), the traced +201 comes from
> PvPoke's own stale damage cache, and the TODO's suggested fix makes
> oracle agreement WORSE (total error 201 -> 730 on the traced pair).
> What remains is comment-scoped and rides the next engine-hash bump
> window. Produced by the 2026-08-09 overnight scout (read-only; all
> measurements via monkeypatched globals in the scratchpad, no repo file
> modified). Oracle: scripts/pvpoke_trace.js + ~/coding/pvpoke @
> 3ca651c7c (note: NOT the sweep's pinned 00f0afe7f; the 9-cell grid
> reproduced our HEAD scores in 8/9 cells, cross-validating the
> gamemaster subset, but re-confirm the pin before citing new numbers).

## The finding as recorded (TODO, from the 2026-07-03 NB-1 sweep carve-out)

The don't-bait override consumes `would_shield=False` while the active
shield policy always shields (Florges vs Seismitoad UL 2-1 inflated
+201). Recorded as "[medium, NEW from the sweep, our own bug]" with the
suggested fix "make the bait override consult the ACTIVE shield policy."

## Mechanism (real, and correctly described)

- Site: `battle.py:1666-1672`, the post-DP don't-bait override inside
  `pvpoke_dp`. Gate: `dpe_ratio > 1.5 and not would_shield(...)` ->
  `first_idx = 1` (throw the nuke instead of the bait).
- Predictor: `would_shield` (`battle.py:550-643`, port of
  `ActionLogic.wouldShield`).
- Active policy: `pvpoke_simulate_shield` (`battle.py:223`,
  `use_shield = True` unconditionally per Battle.js:1084) with only two
  would_shield sub-routes (selfBuffing incoming-move filter at :238-244,
  defender selfDefenseDebuffing branch at :250-300).
- For this pair, BOTH of Seismitoad's charged moves fail the sub-filters
  (Earth Power: selfBuffing False; Icy Wind: buffs[1] == 0), so the
  policy always-shields while `would_shield(Florges, EARTH_POWER)`
  returns False. The override throws Earth Power into a shield at T12
  and again at T24.

## Why "our own bug" is falsified

1. **PvPoke makes the same wasted throw.** Oracle chargedLog for 2-1
   opens `Seismitoad: Earth Power (shielded)` -- its override also fired
   against its own `wouldShield=False`. Same in 1-0, 1-1, 1-2, 2-0, 2-2.
   The predict-vs-policy mismatch is shared structure, exactly as argued
   at `battle.py:1651-1665`.
2. **The +201 is PvPoke's stale cache, not our mismatch.** Ours at HEAD
   matches the oracle in 8/9 shield cells for this pair; only 2-1
   differs (866 vs 665). The divergence is the SECOND override at T24:
   every internally consistent damage ratio for EP/IW is > 1.5 at every
   stat-stage combo in {0,-1,-2}^2 (1.5943-1.6435), so ANY honest ratio
   fires the override. PvPoke skips it only because its `move.damage`
   cache is mixed-stale at T24 (EP refreshed on use = 50, IW init-stale
   = 35 -> ratio 1.2857 < 1.5). Oracle decisionLog confirms. Only
   emulating the stale cache reproduces PvPoke, and the NB-1 sweep
   already rejected emulating that bug.
3. **Corollary:** the in-code attribution at `battle.py:1659-1665`
   (blaming "the fresh-dpeRatio carve-out") is too narrow -- the frozen
   stage-(0,0) ratio (1.5943) also crosses 1.5. Same for the caveat in
   `tests/test_nb1_selection_freeze.py:134-142` (test_group_c10, pins
   866).

## Fix A (the TODO's suggestion) measured, and rejected

Consulting the active policy at :1670 effectively DELETES the override
(the policy always-shields nearly everything the override was written
for). Result on the 9 traced cells: repairs 2-1 only to 651 (oracle
665), and breaks three currently-exact cells (1-1 -242, 1-2 -222, 2-2
-252). Total absolute oracle error 201 -> 730. Blast radius on a GL
top-24 grid (276 pairs x 9 cells): 135/2484 cells change (5.4%), median
|delta| 84, max 401, including shipped focals/opponents (Forretress,
Azumarill, Tinkaton, Mimikyu). Migration predicate feasibility: the
sound conservative predicate ("no charged-move pair with dpe ratio > 1.5
at any stage combo, both sides") blesses only 27.2% -- a near-cold
re-dive to make agreement worse. Three sibling would_shield consumers
(`battle.py:1340` opposite polarity, `:1791` bandaid[910], `:1827`
bandaid[929]) share the structure and interact; patching all four gives
yet other scores and contradicts the documented bandaid[929] divergence.

## Disposition

- **No behavior change.** The mismatch is documented shared-structure
  divergence; the cell's error is PvPoke's bug.
- **Comment-only corrections, deferred to the next engine-hash bump
  window** (battle.py is engine-hashed; even comments bump the hash --
  though comment-only is the one case where a fully-blessing
  `--from-engine` migration is trivially provable):
  1. `battle.py:1659-1665`: reattribute -- any internally consistent
     ratio fires here (ours 1.6071 fresh / 1.5943 frozen vs PvPoke
     1.2857 mixed-stale); the divergence is entirely PvPoke's stale
     EP.damage.
  2. `tests/test_nb1_selection_freeze.py:134-142` docstring: same
     reattribution (not hash-gated, but meaningless without #1 -- keep
     them together).
  3. `src/gopvpsim/formchange.py:127-148` docstring (round-2 FC-2, same
     window): drop the "same fixed point / exact" claim -- PvPoke's cpms
     reaches level 55, so it computes real 52/54/55 Shield reverts for
     35 best-level IV combos (incl. UL 15/15/15) and NaN only past 55;
     our 51.0 clamp stays the defensible choice (levels above 51 don't
     exist in-game). The DEVELOPER_NOTES half was already corrected
     2026-07-16.
- **If a behavior change is ever wanted anyway** (making the four
  predict-vs-policy sites consistent as a matter of principle): gate it
  on a full oracle sweep, not a single-matchup check; batch with another
  cold-forcing change (it cannot be usefully migrated); and re-derive
  the pinned scores in test_nb1_selection_freeze (866) and Group C
  (567).
