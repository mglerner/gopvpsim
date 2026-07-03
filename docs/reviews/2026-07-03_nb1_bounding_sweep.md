# NB-1 bounding sweep -- footprint, FIX recommendation, predicate sketch

Decision material for Michael (follows up round-2 finding NB-1,
docs/reviews/2026-07-02_engine_bug_hunt_round2.md). Produced 2026-07-03 by a
14-agent bounding-sweep workflow in the hunt2 worktree: 140-matchup grid
(1260 cells) ours-vs-PvPoke-oracle, pinned gamemaster md5 363e44f3 / pvpoke
00f0afe7f, 8 mechanism-trace clusters covering 53 of the 76 diff cells.

Headline numbers: 76/1260 cells differ (6.0%), 7 winner flips; effectively
all 36 GL diffs touch the shipped surface in one orientation, including a
shipped winner flip (Forretress (Shadow) vs Cradily GL 1-0: ours 413 LOSS vs
oracle 588 WIN, -175). NOTE this corrects the round-2 report's "no shipped
winner flips were observed" claim -- that held for the hunt's own sampled
cells; this sweep's wider grid found one.

Two NEW items surfaced beyond the NB-1 class (tracked in TODO):
- OMT `turns_planned` divisor port infidelity (battle.py:749-750 vs
  ActionLogic.js:306) -- unintentional, PvPoke strictly better in all traced
  cells; fix forces a cold re-dive, so batch with the next cold-forcing
  change.
- Our own would_shield/always-shield internal inconsistency (Florges vs
  Seismitoad UL 2-1 inflates our score by +201) -- independent of PvPoke
  fidelity.

The full synthesis follows verbatim.

---

# NB-1 bounding sweep — synthesis for fix-vs-document decision

Sources: sweep grid (140 matchups / 1260 cells, pinned gamemaster md5 `363e44f3f9d9a56cf9dc7d9e3abd735e`, pvpoke clone @ `00f0afe7f`, bait-on both sides), 8 mechanism-trace clusters covering 53 of the 76 diff cells, round-2 report NB-1/F1/F2/FC-1/PROP-1 sections, and code reads of `_priority_shuffle` (battle.py:866-951) and `_ensure_dp_cache` (battle.py:2086-2260) in the hunt2 worktree.

---

## 1. FOOTPRINT

**Base rates:** 76/1260 cells differ (6.0%); 7/1260 winner flips (0.56%).

### By shipped surface

Shipped = GL matchup whose focal has a `thresholds/*.toml` and whose opponent is in `gl_top50_plus_cs.txt` (UL columns are unshipped: the gobattlekit bundler is Great-league-only, and the grid itself marked UL Forretress `shipped:false`).

| Surface                              | Diff cells | Flips | Notes                                                                                                                                                                                                                                           |
| ------------------------------------ | ---------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shipped-oriented (GL, focal shipped) | 24         | 2     | OinkF vs Forretress (2), ForreS vs Cradily (9, incl. flip), Forretress mirror (2), OinkF vs Florges (1, flip), ForreS mirror (2), Florges mirror (1), Sableye(S) vs Diggersby (3), OinkF vs ForreS (3), Dragonair(S) vs Forretress (1, 0-point) |
| GL, mirror-orientation shipped       | 12         | 0     | Greedent vs Forretress (6), Wigglytuff vs Florges (2), Cradily vs Florges (4) — focal side unshipped, but the swapped-role column (Forretress/Florges dives vs these pool opponents) IS shipped and carries the same misplay                    |
| Unshipped (all UL)                   | 40         | 5     | 3 of the 5 UL flips are the Forretress UL mirror ties (500/500 in oracle) — PROP-1 tie-artifact entangled, cosmetic in-game                                                                                                                     |

So effectively **all 36 GL diffs touch the shipped surface in one orientation**, plus 2 shipped winner flips.

### By league

GL: 36 diffs / 2 flips. UL: 40 diffs / 5 flips.

### By who-plays-better (cluster-verified, not score-sign)

| Cluster                              | Cells | Verdict                 | Mechanism                                                                                                                                                    |
| ------------------------------------ | ----- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Greedent GL (exemplar)               | 6     | PvPoke                  | NB-1 0.3 guard (-84 x 5, -20 x 1)                                                                                                                            |
| ForreS GL vs Cradily + ForreS mirror | 11    | mixed, PvPoke ahead     | NB-1 0.3 guard (9) + bait-wait 1.5 second site (2); oracle better 7, ours 3, incl. the shipped flip                                                          |
| Forretress UL family                 | 12    | mixed, PvPoke ahead     | 0.3 guard both directions + bait-wait 1.5; oracle 7 (~-297), ours 4 genuine + 1 PROP-1 artifact                                                              |
| Oranguru UL                          | 6     | mixed                   | NB-1 0.3 guard; ours better with 2 opp shields (incl. 2-0 flip won), oracle better in 1-0/1-1                                                                |
| Florges UL                           | 8     | mixed, PvPoke ahead 5/8 | NB-1 0.3 guard (7) + don't-bait staleness site (Seismitoad 2-1, +201 = our own opponent-side misplay)                                                        |
| Wigglytuff GL                        | 2     | ours                    | NB-1 0.3 guard, ours-better direction (+56)                                                                                                                  |
| Oinkologne GL                        | 6     | mixed                   | **NOT NB-1**: 4 cells = new OMT turns_planned divisor infidelity (PvPoke better, -24 each); 2 cells = don't-bait staleness (ours better, incl. shipped flip) |
| Forretress GL mirror                 | 2     | ours                    | **NOT NB-1**: bait-wait 1.5 site, +/-4 points, near-cosmetic                                                                                                 |

23 cells (Sableye(S)/Diggersby, Cradily-Florges GL, Ampharos, Steelix(S), Seaking, Cresselia cells, Florges GL mirror, Dragonair(S)) were **not individually traced**; they sit in the same species/moveset families and are presumed in-class, not verified.

### Worst shipped impact

- **Points + flip:** Forretress (Shadow) vs Cradily GL **1-0: ours 413 (LOSS) vs oracle 588 (WIN), -175** — a shipped dive page (`forretress_shadow.toml` focal, Cradily in pool) shows a loss where the reference plays to a win, attributable to our Sand Tomb misplay. This directly contradicts the round-2 report's "no shipped winner flip observed" (it had only sampled 4 cells of this shape).
- Next-worst shipped points: Sableye (Shadow) vs Diggersby 2-0, -125 (untraced).
- Second shipped flip: OinkF vs Florges GL 2-2 (567 W vs 471 L) — **in our favor and defensible** (PvPoke's own DP preferred our move; its override rests on stale-inconsistent cached damage).
- Largest overall delta: Florges vs Seismitoad UL 2-1, +201 — inflated by our own opponent-side wasted nuke (fresh don't-bait check internally inconsistent with our always-shield policy), i.e. NOT a point in our favor.

---

## 2. RECOMMENDATION: FIX (freeze dpe-derived selection at init stages), with one carve-out kept as documented divergence

Argued through the CLAUDE.md three-question gate:

**Q1 — Does PvPoke produce a demonstrably better outcome?** On balance, yes, for the init-frozen-threshold class. Cluster verdicts: PvPoke strictly better in the exemplar (6/6), ahead in ForreS-GL (7/11), Forretress-UL (7/12), Florges-UL (5/8), and the new OMT cells (4/4); ours better in Wigglytuff (2) and scattered 2-shield cells. Raw sign tally: oracle-higher 44, ours-higher 31, tie 1. Decisively: the class produced a **shipped winner flip against us (-175)** where the misplay is isolated to our side (Cradily's play comparable in both engines). This is not "different chargedLog, same outcome" — scores, HP margins, and a winner differ.

**Q2 — Does our deviation have a defensible reason?** **No — this is the dispositive question.** The documented rationale (three sites: battle.py:1286-1293 INTENTIONAL DIVERGENCE note, DEVELOPER_NOTES divergence #3 / PvPoke bug #2, docs/pvpoke_divergences.md #1) claims recompute-always-better with Aegislash as the only mismatch. The sweep falsifies it in both directions: PvPoke's 0.3 selfBuffing guard and 1.5 bait-gate ratio are thresholds *tuned for init-time stage-(0,0) evaluation*; re-evaluating them per stage makes them cross for non-strategic reasons — Trailblaze (11 dmg/45e) held over Body Slam (17 dmg/35e), and a bait-gate crossing produced purely by integer flooring noise (1.495 vs 1.52). Our residual "wins" (Wigglytuff +56, Oranguru 2-0) come from the same accidental threshold jitter, not a policy we can defend; keeping them is keeping unprincipled noise.

**Q3 — Would matching PvPoke make us worse for the use case?** No. For breakpoint/bulkpoint teambuilding, users cross-check our dives against PvPoke; mixed-direction disagreement (sometimes -175, sometimes +56, unpredictably) is strictly worse than sharing the reference's arbitrary-but-consistent convention. We lose a handful of accidental wins and gain reference-consistency plus the shipped flip fix. No post-KO/energy-carry-over consideration favors the recompute.

**Fix scope (all three init-frozen sites, or the fix is incomplete):**

1. `_priority_shuffle` ordering + promotion clause (battle.py:866-951);
2. `best_idx` 0.3-guard loop and its `best_cycle_dmg`/`min_cycle_thr`/`farm_swap_idx` derivatives (battle.py:2204-2247);
3. the bait-wait selfBuffing exemption 1.5 ratio (battle.py:1584-1599).

Compute these once per battle from stage-(0,0) damages, PvPoke-style; keep the per-stage damage tables for the DP itself fresh (PvPoke's damage is fresh too — only `.dpe`/ordering is init-frozen). The traces prove freezing only `best_idx` would NOT reconcile the mirror cells (bait-wait site) — cover all three.

**Carve-out (keep as documented divergence, do NOT match):** the post-DP "don't bait if the opponent won't shield" dpeRatio site (battle.py:1615-1622 vs ActionLogic.js:857-865). PvPoke evaluates it with *mixed* staleness (one move's `.damage` refreshed on use, the other init-stale) — an internally inconsistent cache artifact, not a policy; its own DP preferred our move in the traced cells. Matching it would be emulating a PvPoke bug. Document + xfail-pin (spec below). Flag separately for follow-up: our fresh evaluation is ALSO internally inconsistent (Florges vs Seismitoad UL 2-1: `would_shield`=False feeds the override while the actual policy always shields — we waste our nuke). That is our bug, independent of PvPoke fidelity.

**Separate new finding, not part of this bump:** the OMT `turns_planned` divisor infidelity (battle.py:749-750 vs ActionLogic.js:306; the four -24 Oinkologne cells, 3 shipped-oriented). Genuine unintentional port bug, PvPoke strictly better in all traced cells, one-line-ish fix — but its touched set is essentially uncharacterizable statically (the divisor differs at any deathbed state where slot-0 is unaffordable or promoted, i.e. potentially any 2-charged column), so it forces a cold re-dive. Batch it with the next cold-forcing change; do not ride it on this bump.

**Doc/hygiene payload of the fix commit:** rewrite the three falsified doc sites; delete/replace the battle.py:1286-1293 INTENTIONAL DIVERGENCE note; the round-2 report's "no shipped winner flip this round" claim gets a correction pointer (ForreS vs Cradily GL 1-0).

---

## 3. MIGRATE_CACHE PREDICATE SKETCH (for the freeze fix)

**Predicate `nb1_selection_freeze` (bless = column provably untouched):**

```
bless(column) iff:
    for every charged move m in EXPANDED(focal_moveset) UNION EXPANDED(opp_moveset):
        m has no 'buffs' entry with any nonzero delta   # any buffApplyChance > 0 counts
    and (belt-and-suspenders) no fast move on either side carries 'buffs'
```

where `EXPANDED(moveset)` = stored moveset IDs from the column sidecar, transitively expanded through the form-change move-swap table (AEGISLASH_CHARGE_* <-> PSYCHO_CUT/AIR_SLASH, AURA_WHEEL_ELECTRIC <-> AURA_WHEEL_DARK) whenever the species (also in the sidecar) is a form-change species.

**Proof shape:** the fix changes only which values feed the shuffle/best_idx/bait-gate computations — frozen stage-(0,0) vs current-stage. At stages (0,0) the two are identical by construction (recompute at stage 0 == init compute; the dp-cache defender key cannot change in a 1v1 sim). Stat stages move ONLY via charged-move buffs — verified for this gamemaster: no fast move carries `buffs` (re-verify mechanically at migration time against the pinned blob, since the predicate is one-shot pinned to `--from-engine` + gamemaster stamp). Therefore: no nonzero-buff charged move on either side => stages are (0,0) all battle => frozen == fresh => battle byte-identical. The predicate covers all three fixed sites at once because all three consume the same stage-dependent damages, and (if the freeze also touches the don't-bait ratio's inputs) that site too.

**Dynamic-flag audit (the F2 failure mode) — every battle-time move-dict mutation in `_priority_shuffle`/`_ensure_dp_cache`, from a full read of both:**

1. **Registeel clause, battle.py:912-922** (the exact site that sank F2's `self_debuff_either_side` proof): mutates `cms[0]['buffs'] = [0,0]`, `buffTarget='self'`, `selfDebuffing=True` onto FOCUS_BLAST when paired with ZAP_CANNON, or `pop`s those keys. **Covered without widening:** the injected buffs are `[0,0]` — zero delta, cannot move a stage — and the else-branch only removes flags. Moreover any FOCUS_BLAST+ZAP_CANNON column is already in the touched set via ZAP_CANNON's own static nonzero debuff. The predicate reads buff *values*, not `selfDebuffing`, so this mutation cannot fool it the way it fooled F2.
2. **List reorders (the five swap clauses, battle.py:899-951):** pure `cms` list permutation, no dict mutation, no stage effect. Ordering differences are exactly what the fix changes — behavior identical at stage (0,0) regardless of when ordering is computed.
3. **`_ensure_dp_cache` (battle.py:2086-2260):** builds fresh lists/arrays; **no move-dict mutation** (verified by read).
4. **Form-change move swaps (F1's hazard):** the battle reads move dicts NOT in the stored moveset. Handled by `EXPANDED()` above. Concretely: Aegislash swaps *fast* moves (no buffs — but the fast-move belt-and-suspenders clause catches any future change) and Morpeko's two Aura Wheels both carry the same +1 atk self-buff (so such columns are touched either way). If implementing `EXPANDED()` feels heavier than it's worth, the sound cheap widening is: **any column whose either species is a form-change species is touched unconditionally** (small set).

**Touched-set size:** substantial — Rock Tomb/Icy Wind/Chilling Water/Ancient Power/Superpower-family moves are everywhere in both pools — but the buff-free remainder (e.g. pure Swift/Body Slam/Hydro Cannon movesets on both sides) is real warm savings vs cold. Computable exactly from sidecars before committing.

**Co-bump analysis (one-localized-fix-per-bump):**

- **FC-1 (Aegislash revert-energy, battle.py:2833/:2771) is a CLEAN co-bump candidate.** Its touched set is statically characterizable from sidecar species: the stale-queued-fast revert path requires a mid-flight *fast-move* form swap, which only Aegislash does (Morpeko swaps charged moves). Union predicate: `bless iff nb1_selection_freeze(column) AND neither species is Aegislash (any form)`. Both proofs stay independent and simple. Recommended pairing if Michael wants FC-1 fixed now (it has 4 known winner flips of its own on the Aegislash surface).
- **The OMT divisor fix must NOT ride this bump:** its delta fires at any low-energy deathbed state regardless of buffs or promotion (our cheapest-affordable divisor + return-False-when-unaffordable vs PvPoke's slot-0-regardless), so no predicate short of "either side has a charged move" covers it — co-bumping it converts the whole bump to a cold re-dive. Batch it with the next unavoidably-cold change instead.
- Nothing else should share the bump.

---

## 4. XFAIL SPEC (re-document path; also the pins for the carved-out don't-bait divergence under the fix path)

All pins: pinned gamemaster md5 `363e44f3f9d9a56cf9dc7d9e3abd735e` (pvpoke @ `00f0afe7f`), 15/15/15 both sides, bait-on (PvPoke default) both sides, hard-coded movesets (never `get_default_moveset` — these must not drift with rankings).

**Group A — NB-1 0.3-guard class (xfail if documenting; these become MUST-PASS oracle fixtures if fixing):**

| #   | Focal (moves, level)                                        | Opponent (moves, level)                                   | League/CP  | Shields | Ours | Oracle | Pins                                                                                            |
| --- | ----------------------------------------------------------- | --------------------------------------------------------- | ---------- | ------- | ---- | ------ | ----------------------------------------------------------------------------------------------- |
| 1   | Greedent, MUD_SHOT + BODY_SLAM,TRAILBLAZE, L22              | Forretress, VOLT_SWITCH + SAND_TOMB,ROCK_TOMB, L23        | great/1500 | 1-1     | 268  | 352    | exemplar; timeline: T24 Rock Tomb SHIELDED -> T27 ours Trailblaze 11 dmg vs oracle Body Slam 17 |
| 2   | Greedent, same                                              | Forretress, same                                          | great/1500 | 1-2     | 188  | 272    | exemplar second cell                                                                            |
| 3   | Forretress (Shadow), VOLT_SWITCH + SAND_TOMB,ROCK_TOMB, L23 | Cradily, BULLET_SEED + ROCK_TOMB,GRASS_KNOT, L23.5        | great/1500 | 1-0     | 413  | 588    | **shipped winner flip**; ours-loss/oracle-win                                                   |
| 4   | Oranguru, CONFUSION + BRUTAL_SWING,TRAILBLAZE, L41.5        | Orthworm, MUD_SLAP + ROCK_TOMB,EARTHQUAKE, L46.5          | ultra/2500 | 1-1     | 300  | 366    | oracle-better direction, UL                                                                     |
| 5   | Oranguru, same                                              | Orthworm, same                                            | ultra/2500 | 2-0     | 556  | 447    | ours-better winner flip — documents mixed direction                                             |
| 6   | Wigglytuff, CHARM + SWIFT,ICY_WIND, L27                     | Florges, FAIRY_WIND + CHILLING_WATER,DISARMING_VOICE, L16 | great/1500 | 1-1     | 632  | 576    | ours-better direction, stage-0 gap 0.3016 crossing to 0.257                                     |

**Group B — bait-wait 1.5 second site (same class, different threshold; any fix must cover or these stay red):**

| #   | Focal                                                       | Opponent                               | League/CP  | Shields | Ours | Oracle | Pins                                                 |
| --- | ----------------------------------------------------------- | -------------------------------------- | ---------- | ------- | ---- | ------ | ---------------------------------------------------- |
| 7   | Forretress (Shadow), VOLT_SWITCH + SAND_TOMB,ROCK_TOMB, L23 | Forretress (Shadow), same moveset, L23 | great/1500 | 1-2     | 240  | 296    | flooring-noise crossing (ratio 1.495 vs frozen 1.52) |
| 8   | Forretress, VOLT_SWITCH + SAND_TOMB,ROCK_TOMB, L47          | Forretress (Shadow), same moveset, L47 | ultra/2500 | 1-2     | 381  | 468    | frozen 1.486 vs live 1.508 crossing                  |

**Group C — don't-bait dpeRatio staleness site (KEEP as intentional divergence under EITHER path — PvPoke's mixed refresh-on-use staleness is a PvPoke bug; xfail reason must say so, per policy "PvPoke X is arbitrary/buggy because Z"):**

| #   | Focal                                                     | Opponent                                                  | League/CP  | Shields | Ours | Oracle | Pins                                                                                                                                                                     |
| --- | --------------------------------------------------------- | --------------------------------------------------------- | ---------- | ------- | ---- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 9   | Oinkologne (Female), MUD_SLAP + BODY_SLAM,TRAILBLAZE, L21 | Florges, FAIRY_WIND + CHILLING_WATER,DISARMING_VOICE, L16 | great/1500 | 2-2     | 567  | 471    | shipped flip in our favor; oracle's override fed by BS.damage=35 stale vs TB.damage=28 fresh (ratio 1.607 vs consistent 1.286)                                           |
| 10  | Florges, FAIRY_WIND + CHILLING_WATER,DISARMING_VOICE, L27 | Seismitoad, MUD_SHOT + EARTH_POWER,ICY_WIND, L38          | ultra/2500 | 2-1     | 866  | 665    | **flag the caveat in the xfail reason:** our score is inflated by our own opponent-side would_shield/always-shield inconsistency (separate open bug), not by better play |

**Group D — OMT divisor infidelity (new finding; xfail only until its own fix lands — reason: unintentional port bug, PvPoke strictly better):**

| #   | Focal                                                     | Opponent                                                    | League/CP  | Shields | Ours | Oracle | Pins                                                                                                                                                                           |
| --- | --------------------------------------------------------- | ----------------------------------------------------------- | ---------- | ------- | ---- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 11  | Oinkologne (Female), MUD_SLAP + BODY_SLAM,TRAILBLAZE, L21 | Forretress (Shadow), VOLT_SWITCH + SAND_TOMB,ROCK_TOMB, L23 | great/1500 | 0-1     | 280  | 304    | deathbed ttl=4, energy=35: PvPoke divides by promoted slot-0 (45e) -> waits, banks a floating Mud Slap (+24); ours divides by cheapest-affordable (35e) -> fires 3 turns early |

Doc sites to update alongside whichever path is chosen: `battle.py:1286-1293` note, DEVELOPER_NOTES divergence #3 / PvPoke bug #2, `docs/pvpoke_divergences.md` #1 (all currently claim recompute-always-better — falsified), plus new entries for the bait-wait 1.5 site, the don't-bait staleness site, and the OMT divisor.

Key scratch artifacts (hunt2 worktree, `/Users/mglerner/coding/hunt2/gopvpsim/nb1_scratch/`): `pin.py` (gamemaster redirect), `oink_*`, `trace_cluster.py`, `forre_mirror_ours.py`, `oran_*`, `florges_*`, `wiggly_*`, `forre_ul_trace.py`, `pvpoke_trace2.js` (oracle bandaid-line probe).
