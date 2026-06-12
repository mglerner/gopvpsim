# PvPoke bug-report drafts (paste-ready)

Drafted 2026-06-11 for the TODO "File PvPoke bug reports" item. Each
section below is a self-contained GitHub-issue draft against
github.com/pvpoke/pvpoke. Line numbers reference commit `bc532fbda`
(our last vetted clone state; re-check before filing).

**Curation notes (why this is 7 reports, not the TODO's 8):**

- TODO's "Mimikyu delays Shadow Sneak" was RETRACTED 2026-04-15
  (DEVELOPER_NOTES §4): the divergence was in OUR battle-log output,
  not PvPoke's behavior. Do not file.
- TODO's "bestChargedMove using move.damage (undefined at init)" has a
  debunked premise: `initializeMove` (Pokemon.js:830-839) sets
  `move.damage` for every move at battle init, both with and without
  an opponent (re-verified 2026-06-11 during the E11 doc correction;
  also memory `project_bestchargedmove.md`). The real, fileable issue
  in that area is the buff-adjusted-DPE overwrite (report 4 below).
- The Blade→Shield CPM-table overflow (report 6) was found 2026-06-11
  and is new since the TODO list was written.

ASCII hyphens only below (these are public-facing drafts).

---

## Report 1 — BattleState dominance checks reference nonexistent fields (dead code)

**Title:** ActionLogic: BattleState dominance checks read `.hp`/`.shields`
which don't exist (always-false, dead pruning)

**Where:** `src/js/battle/actions/ActionLogic.js` — the `BattleState`
class stores `.oppHealth` and `.oppShields` (line ~1187), but the
dominance checks at lines ~479, ~600, and ~697 compare `.hp` and
`.shields`. Those properties are never set on BattleState instances,
so the comparisons evaluate against `undefined` and the prune branch
never fires. (The dedup check at line ~545 correctly uses
`.oppHealth`, which is how the mismatch is visible.)

**Impact:** the DP queue's dominance pruning is silently inert.
Results are still correct (pruning is an optimization), but the DP
explores states the code clearly intends to discard, and anyone
reading the code will assume the pruning works.

**Suggested fix:** rename the fields in the checks to
`.oppHealth`/`.oppShields` — but note that ENABLING the pruning
changes which plans win ties, so it changes some battle outputs;
treat as a behavior change, not a cleanup. (We maintain a Python port
and keep a flag for both behaviors; the "intended" variant also needs
a buffs term in the comparison to be safe — see report 5's
relationship to state fields.)

---

## Report 2 — bestChargedMove not recomputed when the OPPONENT changes form

**Title:** Stale bestChargedMove after opponent form change (Aegislash):
attacker keeps using the move selected against Shield-form defense

**Where:** `src/js/pokemon/Pokemon.js` — `selectBestChargedMove`
(~line 791) runs at init and caches `bestChargedMove`;
`changeForm` (~line 2344) calls `resetMoves()` on the form-changer
itself only. The opponent's cached selection is never refreshed.

**Repro (simulate mode, Ultra League):** Azumarill
(Bubble / Ice Beam + Play Rough) vs Aegislash (Shield). At init,
against Shield form's 272 defense, Ice Beam (DPE 0.273) and Play
Rough (DPE 0.300) differ by less than the 0.03 threshold, so the
cheaper Ice Beam is selected. After Aegislash transforms to Blade
(97 defense), the DPE gap grows to ~0.062 — Play Rough is now clearly
better — but Azumarill keeps throwing Ice Beam for the rest of the
battle because the selection was cached against the old form.

**Impact:** scores in Aegislash (and Mimikyu-class) matchups are
computed with demonstrably suboptimal move choices for the
non-form-changing side. In our cross-check the 1v2/2v2 cells shift by
~134 rating points when the selection is refreshed per-turn.

**Suggested fix:** on `changeForm`, also invalidate/recompute the
OPPONENT's `bestChargedMove` (or recompute lazily per decision).

---

## Report 3 — Aegislash selects Gyro Ball over Shadow Ball (same cost, strictly less damage)

**Title:** Aegislash prefers Gyro Ball over Shadow Ball vs Azumarill
despite identical energy and strictly lower damage

**Where:** move selection feeding the charged-move decision
(`ActionLogic.js` near-KO DP / bestChargedMove area; exact root cause
unclear from the outside).

**Repro (simulate mode, Ultra League):** Aegislash (Shield)
(Psycho Cut / Shadow Ball + Gyro Ball) vs Azumarill, shields 1v2 or
2v2. Both charged moves cost 50 energy; against Water/Fairy both are
neutral with STAB, and Shadow Ball does strictly more damage (49 vs
39 in Shield form, 101 vs 81 in Blade form). PvPoke throws Gyro Ball.
Removing Gyro Ball from the moveset RAISES Aegislash's 1v2 score from
376 to 429 — having the strictly-worse move available actively hurts.

**Impact:** published Aegislash matchup numbers are measurably below
what its own moveset supports; "more moves can only help" intuition
is violated.

**Winner-flip evidence (found 2026-06-12, Great League):** Azumarill
(Bubble / Ice Beam + Play Rough, 4/15/13) vs Aegislash (Shield)
(4/14/15), shields 2v1 and 2v2: the simulator reports Azumarill
WINNING 623-376 because Aegislash burns both of Azumarill's shields
on Gyro Ball and then lands a third Gyro Ball instead of Shadow
Balls. With Shadow Ball selected (identical 50 energy, strictly more
damage), Aegislash wins the same matchup 510-489. The bug does not
just shave score margins - it flips published matchup outcomes.

---

## Report 4 — initializeMove's buff-adjusted DPE is immediately overwritten

**Title:** Buff-adjusted move.dpe computed in initializeMove never
reaches the bait/ratio logic (overwritten by selectBestChargedMove)

**Where:** `src/js/pokemon/Pokemon.js`. `initializeMove`
(~lines 849-864) computes a buff multiplier that inflates `move.dpe`
for self-attack-buffing and opponent-defense-debuffing moves. But
`selectBestChargedMove` (~lines 791-796), called inside the same
`resetMoves()` flow, immediately resets `move.dpe = move.damage /
move.energy` for every active charged move. The buff-adjusted value
therefore only influences the activeChargedMoves priority shuffle
(lines ~711-787); it never reaches the bait-wait ratio check
(`ActionLogic.js:843`) or any later consumer, although the code reads
as if it should.

**Impact:** baiting decisions treat e.g. Power-Up Punch and a plain
move of equal raw DPE identically, even though the init code clearly
intends the buff move to look more valuable.

**Suggested fix:** either reorder so the buff adjustment is applied
after the reset, or apply the multiplier inside
`selectBestChargedMove` itself.

---

## Report 5 — needsBoost / non-guaranteed-buff plan selection is dead code

**Title:** ActionLogic: the chance-buff plan-selection system
(changeTTKChance / stateList / needsBoost) is fully inert in simulate mode

**Where:** `src/js/battle/actions/ActionLogic.js`, decideAction DP:

1. Line ~539: `changeTTKChance = 0;` runs unconditionally (comment:
   "DISABLE THE NON-GUARANTEED BUFF EVALUATION SYSTEM") AFTER lines
   ~519-536 set it from the move's buffApplyChance. Every chance-<1
   DPQueue push (lines ~613, 631, 661, 680, 710, 728, 756, 774) is
   gated on `changeTTKChance != 0`, which is now always false — so
   `stateList` only ever accumulates chance-1 plans.
2. `needsBoost` is declared `false` (line ~793) and never assigned
   `true` anywhere in the file, so the plan-reorder gate at line ~868
   (`if (!needsBoost)`) is inert.

**Empirical confirmation:** across all 9 shield scenarios for the
four GL meta species whose default moveset carries a
0 < buffApplyChance < 1 charged move (Tinkaton + Bulldoze,
Corviknight + Air Cutter, Clefable + Moonblast, Drapion + Crunch),
the "needs the BOOST" decision-log message fires 0 times in 36 sims.

**Impact:** none on outputs today (the system is disabled), but the
~100 lines of accumulation/reorder machinery read as live logic and
the disabling line is easy to miss. Either the disable is intentional
(then the machinery could be removed) or line 539 is a leftover
debugging kill-switch (then re-enabling changes plan selection for
chance-buff movesets).

---

## Report 6 — Blade-to-Shield reverse level computation can index past the CPM table

**Title:** getFormStats (aegislash_shield branch): level overshoot
can read past the end of the CPM array (undefined CPM)

**Where:** `src/js/pokemon/Pokemon.js`, `getFormStats` (~line 2455).
The aegislash_shield branch starts the Shield-form level at
`blade_level / 0.5 + 2` (Great League) as a deliberate overshoot,
then walks down whole levels until the CP fits.

**Problem:** a low-IV Blade-form focal caps at level 25 in Great
League (whole-level rule), so the raw start is 25 / 0.5 + 2 = 52 —
past the end of the CPM table (max 51). `cpms[index]` then yields
`undefined`, the computed CP is NaN, and the walk-down loop's behavior
depends on NaN comparisons rather than real values. JS happens to
survive this (NaN fails the fits-check so the loop keeps stepping
down), but the first iterations operate on garbage and the code only
works by accident.

**Repro:** any Aegislash (Blade) build whose Blade level lands at 25
in GL (e.g. low-attack IV spreads), then inspect getFormStats'
intermediate values for the shield form.

**Suggested fix:** clamp the starting level to the CPM table maximum
(the walk-down from 51 reaches the same fixed point). Found
2026-06-11 when the same overshoot crashed our (eagerly-validating)
Python port with `KeyError: 52.0`.

---

## Report 7 — Morpeko form change is one-way instead of a toggle

**Title:** Morpeko sticks in Hangry form after the first charged move
(gamemaster says type "toggle"; in-game it toggles every charged move)

**Where:** `src/js/battle/Battle.js` line ~1536: the post-attack
charged-move form trigger is gated on
`attacker.activeFormId != attacker.formChange.alternativeFormId`, and
the `morpeko_hangry` gamemaster entry carries no `formChange` of its
own. The first charged move flips Full Belly -> Hangry; once in
Hangry, the guard fails and no reverse trigger exists, so Morpeko
never toggles back (it only resets on switch via `resetOnSwitch`).

**Ground truth:** the gamemaster's own entry says
`type: "toggle", trigger: "charged_move", moveId: "ANY"`, and in-game
verification (2026-06-06) confirms Morpeko enters every battle in
Full Belly and toggles after EVERY charged move (Aura Wheel swaps
Electric/Dark accordingly).

**Impact:** score-relevant whenever Morpeko throws an unshielded
2nd-or-later Aura Wheel against an opponent where Electric vs Dark
effectiveness differs (e.g. Electric is super-effective on Water,
Dark is not). Published Morpeko numbers are wrong in those matchups.

**Suggested fix:** the line-1536 guard was evidently written for
genuinely one-way changers (Aegislash, Mimikyu); for
`type: "toggle"` form changes, allow the trigger to fire from either
form (or give the alternate-form entry the reverse formChange).
