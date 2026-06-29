# bandaid[910] cleanup: migratable-fix feasibility (READ-ONLY investigation)

Date: 2026-06-28
Scope: TODO.md "#6 bandaid[910]" / DEVELOPER_NOTES line 514-515.
Status: investigation only. **No engine file was edited.** All A/Bs ran
against an in-memory recompiled copy of `pvpoke_dp` (patched via
`inspect.getsource` + `exec`), never the repo's `battle.py`.
Current engine hash at investigation time: `acdb94e0df72`.

The keep-vs-fix decision is **Michael's** per CLAUDE.md "When our sim
diverges from PvPoke." This note supplies the evidence; it does not make
the call.

---

## TL;DR

- **What it is (VERIFIED):** a 2-line port infidelity at
  `battle.py:1732-1733`. The [910] defer gate picks the defender's
  **max-damage** charged move where PvPoke (ActionLogic.js:929-930) uses
  the defender's **bestChargedMove**. Faithful fix = use
  `_estimate_best_cm(defender, attacker)`.
- **Not strictly cosmetic (VERIFIED, corrects the TODO wording):** the
  gate is reachable with **default** movesets and the fix changes at
  least one real fight outcome. Across 720 score cells (default + forced
  grids) **1 cell changed** (Pangoro vs Lickitung, 0-0: 907 -> 715),
  with a real turn/HP-remaining difference (13 -> 14 turns, focal HP
  106 -> 56) and **zero winner flips**. "16/16 oracle match" is
  consistent with *no winner flips*, but the change is **not**
  score-identical.
- **Migratable, but the triage's predicate name is WRONG (VERIFIED):**
  the sound warm-serve predicate is **"neither side has a self-debuff
  charged move,"** NOT the triage's focal-only
  `focal_has_self_debuff_cm` complement. An **opponent**-side
  self-debuff holder changes a non-self-debuff focal's column (proven:
  Lickitung focal vs Pangoro 92 -> 284). Focal-only would silently serve
  stale scores.
- **Feasible as a lone-fix bump** with a both-sided predicate computed
  from existing sidecar fields (no schema change). Rough warm-serve
  ~77% of columns (GL); ~23% re-sim.

---

## 1. What the bandaid does vs what the fix does (VERIFIED)

`battle.py:1727-1741`, the [910] "defer self-debuffing until after
survivable charged moves" gate:

```python
if (cm_self_debuf[first_idx]
        and attacker.shields == 0
        and attacker.energy < 100
        and defender.charged_moves):
    opp_best = max(defender.charged_moves,                       # <-- THE BANDAID
                   key=lambda m: defender.charged_move_damage(m, attacker))
    if (defender.energy >= opp_best['energy']
            and not would_shield(defender, attacker, opp_best)
            and not cm_self_buff[0]):
        return None   # defer: wait for opponent to fire opp_best
```

PvPoke ActionLogic.js:929-930 (the port source):

```javascript
if(finalState.moves[0].selfDebuffing && poke.shields == 0 && poke.energy < 100 && opponent.bestChargedMove){
    if((opponent.energy >= opponent.bestChargedMove.energy)&&(! ActionLogic.wouldShield(... opponent.bestChargedMove).value)&&(! poke.activeChargedMoves[0].selfBuffing)){
```

So PvPoke gates on `opponent.bestChargedMove`; we gate on the defender's
**max-damage** move. `bestChargedMove` is highest-DPE with the
SUPER_POWER carve-out (`_estimate_best_cm`, battle.py:148-169), which can
differ from max-damage in both **energy** (changing the
`energy >= move.energy` test) and **would_shield** (changing the shield
test). The two-line fix:

```python
    _ob_idx, opp_best = _estimate_best_cm(defender, attacker)
```

(`defender.charged_moves` is already non-empty at this point, so
`_estimate_best_cm` returns non-None.)

`_estimate_best_cm` already exists and is already used by the shield
policy; the fix only changes the [910] *call site*. **The engine delta
is exactly these two lines** -- nothing else in `pvpoke_dp` or the
engine changes.

This looks like an **accidental port infidelity, not a documented
intentional divergence**: there is no inline comment defending
max-damage here (contrast the explicit INTENTIONAL-DIVERGENCE comments at
[929] and bandaid[866]).

## 2. Which columns a fix changes, and the migration predicate

### Reachability (VERIFIED -- corrects an earlier harness error)

> Methodology caveat (VERIFIED the hard way): an early version of this
> harness built move dicts from **raw gamemaster JSON**, which lacks the
> computed `selfDebuffing` flag (set by `moves.py:199`). That made
> `cm_self_debuf` all-zero and produced a *false* "gate never reached /
> 0 differences" reading. The corrected harness loads moves via
> `gopvpsim.moves.get_moves()` (the engine path). **Do not trust any
> self-debuff measurement built from raw gamemaster move dicts.**

With the corrected loader, the [910] gate **is reachable with default
movesets.** Probe over default-moveset GL grids (instrumented
original-behavior run):

| metric                                                | count |
| ----------------------------------------------------- | ----- |
| [910] block entered                                   | 12033 |
| ...with self-debuff `first_idx` (opp_best computed)   | 2890  |
| ...gate actually evaluated (`opp_best` line ran)      | 1410  |
| ...where defender max-dmg != bestChargedMove          | 414   |
| ...where the DEFER (`return None`) decision **flips** | 37    |

self-debuff-first reached by: Lurantis, Malamar, Buzzwole, Pangoro,
Moltres (Galarian), Talonflame, Blaziken, Virizion (forced).

### The predicate (VERIFIED both-sided; triage name corrected)

The gate's first condition is `cm_self_debuf[first_idx]` -- it only does
anything when the **acting** Pokemon's selected first move is
self-debuffing, which requires that Pokemon to **own a self-debuffing
charged move.** In a sweep column **both** focal and opponent act, so:

> **Sound warm-serve predicate:** a column is provably unchanged iff
> **neither the focal nor the opponent owns a self-debuffing charged
> move** (over its column-resolved moveset).
> **Re-sim set = the complement** (focal OR opponent owns a self-debuff CM).

**The triage's `focal_has_self_debuff_cm` complement is UNSOUND.**
Opponent-side [910] firing changes a non-self-debuff focal's column:
focal Lickitung (no self-debuff CM) vs opponent Pangoro (Close Combat),
0-0: **92 -> 284** under the fix. A focal-only predicate would warm-serve
that column and serve the stale 92.

### Computability over sidecar fields (VERIFIED -- no schema change)

`selfDebuffing` is a deterministic function of `moveId` + gamemaster, and
the gamemaster is pinned by the focal-key hash (a blessed column is
same-gamemaster). Both movesets are already stored:

- focal `fast` + `charged` move IDs: `focal_key_fields` (dir-level key,
  `sweep_cache.py:130`).
- opponent `fast` + `charged` move IDs: `column_key_fields` (the
  `.json` sidecar `col`, `sweep_cache.py:168`).

So the predicate is a one-boolean function over stored fields:
`any(selfDebuffing(m) for m in focal.charged) or any(selfDebuffing(m)
for m in col.charged)` -> re-sim; else warm-serve. No sidecar schema
change.

### Proof outline

1. The engine delta from `acdb94e0df72` is exactly the 2-line opp_best
   change at the [910] site (lone fix -- soundness guard #1; see below).
2. That site is reached only inside `if cm_self_debuf[first_idx]:`. By
   construction `cm_self_debuf[i]` is true only for self-debuffing
   charged moves; `first_idx` indexes the acting side's own
   `charged_moves`. So if the acting side owns no self-debuff CM the
   block is dead.
3. A column simulates both orientations (focal acts; opponent acts). If
   **neither** side owns a self-debuff CM, the block is dead in both
   orientations for every turn/state -> the per-IV score plane is
   byte-identical -> safe to warm-serve.
4. Therefore the complement (either side owns a self-debuff CM) is the
   only set that can change, and re-simming it is sufficient. QED.

### Save ratio (VERIFIED for GL ranked list; ASSUMED for the dive set)

12% of GL **ranked** species (133 / 1143) carry a self-debuff CM in their
**default** moveset (Talonflame, Malamar, Pangoro, Raikou, Gallade,
Pidgeot, Kommo-o, ...). If the dive's opponent set has a similar ~12%
self-debuff share, warm-serve ~= 0.88 (non-SD focal) x 0.88 (non-SD opp)
~= **~77% of columns warm-served, ~23% re-simmed.** ASSUMED: the actual
per-dive opponent list may differ from the full ranked list; the exact
re-sim fraction should be computed against the real opponent set before
relying on it.

## 3. Impact A/B (VERIFIED -- direct simulate(), not dives)

GL, IVs 15/15/15, both sides `pvpoke_dp`, all 9 shield scenarios, base =
original (max-dmg) vs fixed (bestCM):

- **Group A (default movesets):** 7 self-debuff-capable focals x 8 meta
  opponents x 9 = 504 cells -> **1 differing cell.**
- **Group B (forced both-self-debuff focals: Lurantis LEAF_STORM+
  SUPER_POWER, Blaziken BLAST_BURN+OVERHEAT, Virizion LEAF_BLADE+
  CLOSE_COMBAT) x 8 opponents:** 216 cells -> **0 additional differing.**
- **Total: 1 / 720 cells changed, 0 winner flips.**

The one cell, confirmed reproducible and a **real** fight difference (not
score-coincidence):

| variant        | score0 | winner | turns | focal HP | opp HP |
| -------------- | ------ | ------ | ----- | -------- | ------ |
| ORIG (max-dmg) | 907    | P0     | 13    | 106/130  | 0      |
| FIXED (bestCM) | 715    | P0     | 14    | 56/130   | 0      |

Pangoro (Close Combat / Night Slash) vs Lickitung (Body Slam / Power
Whip): Lickitung's bestChargedMove is **Body Slam** (higher DPE); its
max-damage move is **Power Whip**. The fix makes Pangoro wait on Body
Slam instead of Power Whip, so it defers Close Combat differently and
finishes with **half the HP** -- a quantity that matters for the
post-KO/teambuilding use case even though the 1v1 winner is unchanged.

By construction the FIXED value (715) is the one that matches PvPoke
(faithful port). Whether PvPoke's defer is *better* here is the
keep-vs-fix judgment, not a fact this note settles.

## 4. Recommendation (decision is Michael's)

**It is feasible to do this as a lone, migratable engine-hash bump**, and
the change is well-localized (2 lines) with a provable both-sided
predicate. If you choose to fix:

1. Apply the 2-line change at `battle.py:1732-1733` **as the only engine
   edit in that commit** (soundness guard #1: the predicate must cover
   the *entire* delta since `from-engine acdb94e0df72`; a co-batched
   second engine change would invalidate it).
2. Add the `neither_side_has_self_debuff_cm` predicate (both-sided -- NOT
   the triage's focal-only name) to `scripts/migrate_cache.py`, pinned
   `--from-engine acdb94e0df72`. One-shot; delete/keep as history after.
3. Run the pre-dive checklist (`docs/predive_checklist.md`) -- the
   migration warm-serves the bulk but the re-sim set is non-trivial
   (~23% of columns), so it still ties up the machine.
4. Update the TODO/DEVELOPER_NOTES wording: "measured cosmetic (16/16
   oracle match)" is misleading -- it is **winner-stable but not
   score-stable** (>= 1 real HP/score divergence on default movesets).

**The case for leaving it (also defensible):** zero winner flips and 1
changed cell in 720; the only known effect is post-KO HP-remaining
magnitude in rare self-debuff matchups. If no current analysis depends on
exact post-KO HP against a self-debuff opponent, the cost (a frozen-file
edit + a ~23%-column re-dive across the website chain) may exceed the
benefit. Under CLAUDE.md's three-question test this is **not** a defended
intentional divergence (no rationale comment, accidental max-damage), so
the tie-breaker leans toward "fix to match PvPoke" -- but the magnitude
is small enough that "leave it, documented" is reasonable.

Either way: **flag the wording.** The current TODO/notes present
"cosmetic" as if score-identical; it is not.

---

## VERIFIED vs ASSUMED summary

**VERIFIED (by direct measurement this session):**
- Mechanism: max-damage (battle.py:1732-1733) vs PvPoke bestChargedMove
  (ActionLogic.js:929-930); fix = `_estimate_best_cm`.
- Gate reachable with default movesets; 37 defer-decision flips in the
  probe; 1/720 score cells changed; 0 winner flips.
- The Pangoro-vs-Lickitung cell is a real, reproducible fight difference
  (turns + HP-remaining), not score-coincidence.
- Predicate must be **both-sided**; opponent-side self-debuff changes a
  non-self-debuff focal's column (Lickitung vs Pangoro 92 -> 284).
- selfDebuffing is deterministic from moveId + pinned gamemaster; both
  movesets live in existing sidecar fields -> no schema change.
- 12% of GL ranked species hold a self-debuff default CM.
- Current engine hash `acdb94e0df72`; `battle.py` is in `_ENGINE_FILES`,
  so the fix bumps the hash.

**ASSUMED / not independently checked:**
- The exact per-dive re-sim fraction (used the full GL ranked list as a
  proxy; the real opponent set may differ). Compute it against the
  actual opponent list before relying on ~77%/23%.
- UL/ML behavior (only GL was A/B'd). The gate logic is league-agnostic,
  but the self-debuff population and which cells change will differ.
- Whether PvPoke's defer-on-bestChargedMove is the *better* fight outcome
  (the fix matches PvPoke by construction; "better" is the human
  keep-vs-fix call).
- That 1/720 is the full extent of score change -- it is a finite sample
  (GL, 15/15/15, default + a few forced movesets); a full 4096-IV dive
  could surface more changed cells, though all are bounded to columns
  where some side holds a self-debuff CM and (deeper) where defender
  max-dmg != bestChargedMove (414/1410 of gate evals).
