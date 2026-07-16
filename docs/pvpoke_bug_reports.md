# PvPoke bug reports: filing guide + paste-ready drafts (in filing order)

Drafted 2026-06-11; **re-verified 2026-07-16** against pvpoke master
`10fd1a6e43260e59b625d1cf96bbea496672880d` (engine JS byte-identical to
our vetted `bc532fbda`; gamemaster checked live). Every factual claim
below was re-checked by an adversarial verification workflow (7
verifiers + 7 skeptics + 7 duplicate-hunters, all independent): each
line number was re-derived from the current tree, the behavioral
numbers for the Gyro Ball report were re-run live against PvPoke's own
engine, and PvPoke's issue tracker was searched for duplicates (none
found; the "related issues" cross-references below came out of that
search).

Two changes from the 2026-06-11 draft set:

- **Report 6 (Blade->Shield CPM-table overflow) is RETRACTED** — see
  its section at the bottom. PvPoke's cpms table covers levels 1..55;
  the overflow was ours alone. Do not file.
- **Report 2 is reframed** from "clear bug" to "is this asymmetry
  intended?" — our own NB-1 sweep (2026-07-03) falsified the draft's
  original claim that per-turn recompute is better.

That leaves **6 reports, all being filed 2026-07-16**, presented below
in filing order. (Report numbers are our internal names, kept stable
because DEVELOPER_NOTES references them; the section order is the
order to file.)

---

## How to file (the mechanics)

1. Go to <https://github.com/pvpoke/pvpoke/issues/new> (signed in to
   GitHub). There is no issue template — you get a blank title + body.
2. Copy a **Title** line below into the title field, and everything
   from **Body** to the next `---` into the body (it's GitHub-flavored
   markdown; the Preview tab shows how it renders). Michael's opener
   paragraph is already embedded at the top of every body — each one
   is pure copy-paste.
3. Submit, then move to the next section. That's it — labels and
   assignees are maintainer-side.

Notes:

- The code permalinks in the drafts pin the exact commit
  (`10fd1a6e4...`), so they stay correct even after master moves.
  (To make one yourself: open the file on GitHub, press `y` to pin the
  URL to the current commit, click a line number, copy the URL.)
- If any filing slips past 2026-07: re-check that
  `git log 10fd1a6e4..master -- src/js/` is still quiet before
  pasting; the line numbers are only guaranteed at that commit.
- Optional, after all six are up: edit the bodies to cross-link your
  own new issue numbers (e.g. the Gyro Ball and DPE-overwrite reports
  touch adjacent selection code). Nice-to-have, not required.
- Matt (Empoleon_Dynamite) is a volunteer on ~two-week dev cycles and
  says so in the README — expect latency, don't re-ping.

## Filing plan (all six today) and the AI question

**AI.** Matt has said (Discord DMs) he doesn't want AI-generated code
in his hobby projects — he uses plenty of AI at work; this one's for
him. So: issues, not PRs; no code diffs attached; fixes described in
prose. Michael's opener (below) discloses the AI-assisted provenance
up front. Still worth a skim of each body before pasting so the words
read as yours.

**The opener** — embedded verbatim at the top of every body:

> Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
> Python port/etc). While I was building that, I ran into a handful of
> issues. I found them with a lot of AI assistance, so I'm filing them
> as bug reports but not sending along any AI-generated code. I'm
> happy to provide more detail/etc. I'm filing 6 reports today, but I
> know you batch things up, so I'm including this as a header for each
> of them in case it's useful.

**Order** (same-day; lead with the reports whose value is most obvious
so the first issue Matt opens motivates the rest):

1. Report 3 — Gyro Ball over Shadow Ball (winner flip, repro'd live)
2. Report 7 — Morpeko one-way form change (published numbers wrong)
3. Report 1 — dead dominance pruning (easy to confirm by reading)
4. Report 5 — inert needsBoost system (easy to confirm by reading)
5. Report 4 — buff-adjusted DPE overwritten (subtler code-flow issue)
6. Report 2 — bestChargedMove asymmetry (a question, reads best last)

---

## 1st to file — Report 3 — Aegislash selects Gyro Ball over Shadow Ball (same cost, strictly less damage)

**Title:** Aegislash throws Gyro Ball over Shadow Ball vs Azumarill
(identical energy, strictly lower damage) — flips the published winner

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 6 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

**Repro (simulate mode, Great League; reproduced against master
10fd1a6e4 on 2026-07-16):**

- The matchup: Aegislash (Shield form), IVs 4/14/15, running Psycho
  Cut with Shadow Ball + Gyro Ball, against Azumarill, IVs 4/15/13,
  running Bubble with Ice Beam + Play Rough.
- Shields: Azumarill has 2, Aegislash has 1. (The 2v2 case behaves
  the same way.)
- Both of Aegislash's charged moves cost 50 energy, and both hit
  Azumarill's Water/Fairy typing neutrally with STAB. The only
  difference is that Shadow Ball simply hits harder: 49 vs 39 in
  Shield form, 101 vs 81 in Blade form.
- What the sim does: Aegislash throws three Gyro Balls and never
  throws Shadow Ball. Azumarill shields the first two, the third
  lands, and Aegislash loses 376-623.
- Now take Gyro Ball off the moveset, so Shadow Ball is the only
  charged move: Aegislash wins the same matchup, 510-489.

So having the strictly-worse move *available* flips the published
winner — "more moves can't hurt" doesn't hold here. (The same thing
happens in Ultra League with the same IVs: 442-557 with Gyro Ball,
566-433 without.)

**Root-cause candidate:** `Pokemon.js` ~746-752 blanket-flags ALL of
`aegislash_shield`'s charged moves as `selfDebuffing` (buffs [0,0]).
Because BOTH moves carry the flag, ActionLogic's same-energy /
higher-DPE swap corrections (~905-925) never fire, and the decision
routes through the self-debuff stacking branch — the decision log
shows "doesn't use Gyro Ball because it wants to minimize time
debuffed and it can stack the move 2 times". With shields up, every
charged move does 1 damage, so the DP plans tie and move ordering
picks Gyro Ball, with no guard left to prefer the strictly-stronger
Shadow Ball.

**Impact:** published Aegislash matchup numbers are measurably below
what its own moveset supports, including outright winner flips.

Possibly related existing issues: #47 (adding a third move worsens
rankings — maintainer-acknowledged umbrella) and #149 (same-energy
charged-move order affects results).

---

## 2nd to file — Report 7 — Morpeko form change is one-way instead of a toggle

**Title:** Morpeko sticks in Hangry form after the first charged move
(gamemaster says type "toggle"; in-game it toggles every charged move)

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 6 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

[`src/js/battle/Battle.js:1536`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/battle/Battle.js#L1536):
the post-attack charged-move form trigger is gated on
`attacker.activeFormId != attacker.formChange.alternativeFormId`, and
`changeForm` (Pokemon.js:2344) only overwrites `this.formChange` when
the target form has its own (`if(form?.formChange)`, 2355) — which
`morpeko_hangry` doesn't (no `formChange` in the gamemaster). So the
first charged move flips Full Belly -> Hangry; after that,
`activeFormId == alternativeFormId` and the guard is false forever.
Morpeko never toggles back (it only resets on switch via
`resetOnSwitch`). Grep confirms nothing in `src/js` consumes
`formChange.type == "toggle"` at all.

**Ground truth:** the gamemaster's own `morpeko_full_belly` entry says
`type: "toggle", trigger: "charged_move", moveId: "ANY"`, and in-game
verification (2026-06-06) confirms Morpeko enters every battle in Full
Belly and toggles after EVERY charged move (Aura Wheel swaps
Electric/Dark accordingly).

**History (why this looks like a regression, not a decision):**
f0eac2fca (2024-10-02, "Reworked Morpeko form change") implemented a
working toggle — `changeForm()` computed the target from
`defaultFormId`/`alternativeFormId` when `type == "toggle"`. The
Aegislash form-change rework later broke it, and df75572b7
(2025-07-25, "Fixed Morpeko": "Morpeko's form is now explicitly set
rather than toggled") removed the toggle branch and restored only the
first flip — while the gamemaster still declares the toggle.

**Impact:** score-relevant whenever Morpeko throws an unshielded Aura
Wheel as its 3rd-or-later charged move on an odd slot (i.e. after an
even number of prior charged moves since entry) against an opponent
where Electric vs Dark effectiveness differs — in-game that Aura Wheel
is Electric (toggled back to Full Belly); in PvPoke it stays Dark
(stuck Hangry). Published Morpeko numbers are wrong in those
matchups. (The 2nd consecutive charged move doesn't diverge — both
sims are in Hangry for that one.)

**Suggested fix:** for `type: "toggle"` form changes, let the trigger
fire from either form (compute the target as "the form I'm not in", as
the 2024 implementation did) — the current guard was evidently written
for genuinely one-way changers like Aegislash and Mimikyu.

(Not related to #330, which is a sandbox/timeline input bug that
happens to involve Morpeko.)

---

## 3rd to file — Report 1 — BattleState dominance checks reference nonexistent fields (dead code)

**Title:** ActionLogic: BattleState dominance checks read `.hp`/`.shields`
which don't exist (always-false, dead pruning)

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 6 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

The `BattleState` class in
[`src/js/battle/actions/ActionLogic.js`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/battle/actions/ActionLogic.js#L1205)
(line 1205) stores `.oppHealth` (1208) and `.oppShields` (1210), but
five pruning checks compare `.hp` and `.shields`, which are never set
on any BattleState:

- line 497: `if (DPQueue[i].hp < 0)` (farm-down insertion prune)
- lines 618, 666, 715, 761: four identical dominance checks of the form
  `DPQueue[i].hp <= newOppHealth && ... && DPQueue[i].shields <= newShields`

Since those properties are `undefined`, `undefined < 0` and
`undefined <= x` are always false, so every prune branch is
unreachable. (The dedup check at line 563 correctly uses `.oppHealth`,
which is how the mismatch is visible.) This isn't a refactor artifact:
the same dead checks exist in the pre-refactor `Battle.js`, so the
pruning has never fired.

Related: lines 494 and 507 pass `currState.opponentShields` into the
`new BattleState(...)` constructor — also a nonexistent field (the
real one is `oppShields`), so farm-down states carry undefined
shields. Latent today (those states are terminal, so their shields are
never read), but if the dominance checks are ever renamed to
`.oppShields`, this must be fixed in the same pass or the "fixed"
comparisons will still see undefined.

**Impact:** the DP queue's dominance pruning is silently inert.
Results are still correct (pruning is an optimization), but the DP
explores states the code clearly intends to discard, and anyone
reading the code will assume the pruning works.

**Suggested fix:** rename the fields in the checks to
`.oppHealth`/`.oppShields` and fix the two constructor calls together.
But note that ENABLING the pruning changes which plans win ties, so it
changes some battle outputs — treat as a behavior change, not a
cleanup. (I maintain a Python port and keep a flag for both
behaviors; the "intended" variant also needs a buffs term in the
comparison to be safe.)

Possibly related existing issue: #88 (a wrong charged-move decision in
the same DP area — different bug, since dead pruning can only cost
work, not decisions).

---

## 4th to file — Report 5 — needsBoost / non-guaranteed-buff plan selection is dead code

**Title:** ActionLogic: the chance-buff plan-selection system
(changeTTKChance / stateList / needsBoost) is fully inert

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 6 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

In
[`src/js/battle/actions/ActionLogic.js`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/battle/actions/ActionLogic.js#L539),
decideAction's DP:

1. Line 539: `changeTTKChance = 0;` runs unconditionally (comment at
   538: "DISABLE THE NON-GUARANTEED BUFF EVALUATION SYSTEM") AFTER
   lines 519-536 set it from the move's `buffApplyChance`. Every
   chance-<1 DPQueue push (gates at 613, 631, 661, 679, 710, 728, 756,
   774) requires `changeTTKChance != 0`, which is now always false —
   so every DP state stays at chance 1.
2. That makes the "needs the BOOST" branch statically unreachable, not
   just empirically rare: `stateList` is pushed only at 448 and the
   loop breaks on the first chance-1 KO state (450-451), so it can
   never hold two plans, and the else-if at 796 (log line 804) needs
   at least two. Consistent with that, `needsBoost` is declared
   `false` (793) and never assigned `true` anywhere, so the
   plan-reorder gate at 868 (`if (!needsBoost)`) always passes.
3. Small tell that the branch has never run: line 800 compares
   `stateList[i].chance > bestPlan` — a number against a BattleState
   object (presumably meant to be `bestPlan.chance`). It can't throw
   because it can't execute.

**Empirical cross-check:** across all 9 shield scenarios for the four
GL meta species whose default moveset carries a
0 < buffApplyChance < 1 charged move (Tinkaton + Bulldoze, Corviknight
+ Air Cutter, Clefable + Moonblast, Drapion + Crunch), the "needs the
BOOST" decision-log message fires 0 times in 36 sims.

**Impact:** none on outputs today (the system is disabled), but the
~100 lines of accumulation/reorder machinery read as live logic and
the disabling line is easy to miss. Either the disable is intentional
(then the machinery could be removed, including the line-800 latent
bug) or line 539 is a leftover kill-switch (then re-enabling changes
plan selection for chance-buff movesets). This also affects the
TrainingAI path, which calls decideAction too.

---

## 5th to file — Report 4 — initializeMove's buff-adjusted DPE is immediately overwritten

**Title:** Buff-adjusted move.dpe computed in initializeMove never
reaches the bait/ratio logic (reset at the end of resetMoves)

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 6 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

In
[`src/js/pokemon/Pokemon.js`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/pokemon/Pokemon.js#L849),
`initializeMove` (function at 831-871) computes a buff multiplier
(lines 849-865, using the gamemaster's `buffDivisor`) that inflates
`move.dpe` for self-attack-buffing and opponent-defense-debuffing
moves, e.g. Power-Up Punch. But later in the same `resetMoves()` body,
lines 791-796 reset `move.dpe = move.damage / move.energy` for
`bestChargedMove` and every active charged move.

So the buff-adjusted value influences exactly one thing: the
activeChargedMoves priority shuffle (711-789, which reads it at 735
and 758). It never reaches the bait-wait ratio check
(`src/js/battle/actions/ActionLogic.js:844`) or any other
battle-simulation consumer — those all read the post-reset raw value.
And since `Battle.start()` calls `poke.reset()` -> `resetMoves()` for
every battle, there's no path where a battle sees the adjusted value.

One inconsistency worth noting: moves in the charged-move POOL that
aren't currently selected keep their buff-adjusted dpe (the reset only
touches active moves), and `generateMoveUsage` (1052, 1097) reads
pool-wide dpe — so that code sees adjusted values for unselected moves
and raw values for selected ones.

**Impact:** the DPE comparisons in baiting decisions treat e.g.
Power-Up Punch and a plain move of equal raw DPE identically — buff
awareness only enters via the coarse boolean `selfBuffing` flags,
although the init code reads as if the adjusted DPE should matter.

**Suggested fix:** either apply the buff adjustment after (or inside)
the reset loop at 791-796, or drop the adjustment in initializeMove if
the reset is the intended behavior. One caution: the reset feeds the
bestChargedMove selection thresholds right below it (798-822), so a
fix needs to decide which consumers are meant to see buff-adjusted
DPE.

Possibly related existing issues: #34 (Acid Spray's debuff not valued
in move selection — the user-visible symptom of exactly this) and
#149.

---

## 6th to file — Report 2 — opponent's bestChargedMove stays pinned to init-time form stats

*(Last on purpose: it's a question, not a bug claim — our own
experiments could not show either behavior is better, and it reads
best once the other five have set the context.)*

**Title:** bestChargedMove selection asymmetry on form change: the
form-changer re-selects, the opponent stays pinned to init-time stats
— intended?

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 6 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

Unlike the other five, this one is a question about intent rather than
a bug claim.

`bestChargedMove` is selected in the block at the end of
[`resetMoves()`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/pokemon/Pokemon.js#L791)
(`Pokemon.js`, selection at lines 791-826, the 0.03 DPE threshold at
799). In simulate mode that runs once per Pokemon at battle init
(`Battle.start()` -> `reset()` -> `resetMoves()`). When a form-changer
transforms, `changeForm` (Pokemon.js:2344) calls `self.resetMoves()`
(2397) on the form-changer only — so the changer re-selects against
the opponent's current stats, but the OPPONENT's selection stays
pinned to the pre-change form's stats for the rest of the battle. No
in-battle path refreshes it.

**Concrete case (Ultra League, IVs pinned because the DPE gap depends
on them):** Azumarill 4/15/13 at L50 (Bubble / Ice Beam + Play Rough)
vs Aegislash (Shield). At init, against Shield form's 272 base
defense, Ice Beam (DPE 0.273) vs Play Rough (DPE 0.300) differ by
0.027 < 0.03, so the cheaper Ice Beam is selected. After Aegislash
transforms to Blade (97 base defense) the gap grows to ~0.088 — Play
Rough is now clearly better — but Azumarill keeps throwing Ice Beam
because the selection was cached against the old form. (With PvPoke's
default 15/15/15 Azumarill the same mechanism applies with slightly
different numbers: 0.309/0.333 at init, gap ~0.082 after the change.)

**Why I'm filing this as a question rather than a bug:** scores in
these matchups are sensitive to the choice (~134 rating points in the
1v2/2v2 cells I measured), but when I tried "recompute per decision"
in my port, a bounding sweep showed it was NOT reliably better — the
recompute crosses the init-tuned 0.03/0.3 thresholds mid-fight for
non-strategic reasons, in both directions, including at least one
winner flip against the recompute. I reverted my port to match your
freeze. So: is the asymmetry (changer refreshes, opponent doesn't)
deliberate, or just where the code landed? If deliberate, it might
deserve a comment; if not, be warned that "fixing" it moves a lot of
published Aegislash-matchup scores and the selection thresholds would
probably need retuning.

Possibly related existing issue: #134 (Azumarill locking Ice Beam over
Play Rough vs Bastiodon — no form change involved, so that one is
about the init-time selection thresholds themselves).

---

## Report 6 — RETRACTED 2026-07-16: do not file

The 2026-06-11 draft claimed PvPoke's Blade->Shield reverse-level
overshoot (`blade_level / 0.5 + 2` in GL -> level 52 for a low-IV
Blade) reads past the CPM table. **False:** PvPoke's `cpms` array
(Pokemon.js:24) has 109 entries covering levels 1..55 via
`index = (level - 1) * 2`; level 52 -> `cpms[102]` = 0.8503..., a
defined value. Genuinely overshooting PvPoke's table would need a
Blade level > 26.5, unreachable under 1500 CP. The 2026-06-11
`KeyError: 52.0` was OUR bug — gopvpsim's CPM table stops at 51 — and
our clamp fix (`_aegislash_shield_level`, pinned by
`tests/test_pokemon.py::TestAegislashShieldLevelOverflow`) remains
correct for us. The draft's fallback claim (NaN comparisons in the
walk-down) was also wrong: an out-of-range level would give
`cpms.indexOf(undefined) = -1`, the `cpmIndex >= 0` guard skips the
loop, and `changeForm` would throw a TypeError — no NaN path exists.
DEVELOPER_NOTES "Known divergences" item 3 has been corrected to
match.
