# PvPoke bug reports: filing guide + paste-ready drafts (in filing order)

Drafted 2026-06-11; **re-verified 2026-07-16** against pvpoke master
`10fd1a6e43260e59b625d1cf96bbea496672880d` (engine JS byte-identical to
our vetted `bc532fbda`; gamemaster checked live). Every factual claim
below was re-checked by an adversarial verification workflow (7
verifiers + 7 skeptics + 7 duplicate-hunters, all independent): each
line number was re-derived from the current tree, the Gyro Ball and
Morpeko behaviors were re-run live against PvPoke's own engine, and
PvPoke's issue tracker was searched for duplicates (none found; the
"related issues" cross-references below came out of that search).

Changes from the 2026-06-11 draft set:

- **Report 6 (Blade->Shield CPM-table overflow) is RETRACTED** - see
  its section at the bottom. PvPoke's cpms table covers levels 1..55;
  the overflow was ours alone. Do not file.
- **Report 2 is reframed** from "clear bug" to "is this asymmetry
  intended?" - our own NB-1 sweep (2026-07-03) falsified the draft's
  original claim that per-turn recompute is better.
- **Report 3 carries no battle-rating numbers** (2026-07-16). The
  Gyro Ball behavior and the remove-it-and-improve effect reproduce
  on pvpoke.com, but the exact ratings for the Shadow-Ball-only
  variant did NOT: the site showed 429 where headless runs of the
  same engine + data + inputs show 510 (both vintages). Unresolved;
  the knife-edge cells ("3 turns of difference can flip this
  scenario") are where site and harness disagree, so the report
  describes behavior, not scores.
- **Report 5 is reframed as a question** (2026-07-16): the caps-lock
  disable comment at ActionLogic.js:538 is clearly deliberate, so the
  report now asks whether the system is retired or coming back, and
  carries the two faults that would keep it inert even if re-enabled.
  Michael is probably holding it out of the initial batch.

That leaves **5 reports being filed 2026-07-16**, presented below in
filing order, plus the held-back Report 5 question at the end. (Report
numbers are our internal names, kept stable because DEVELOPER_NOTES
references them; the section order is the order to file.)

---

## How to file (the mechanics)

1. Go to <https://github.com/pvpoke/pvpoke/issues/new> (signed in to
   GitHub). There is no issue template - you get a blank title + body.
2. Copy a **Title** line below into the title field, and everything
   from **Body** to the next `---` into the body (it's GitHub-flavored
   markdown; the Preview tab shows how it renders). Michael's opener
   paragraph is already embedded at the top of every body - each one
   is pure copy-paste.
3. Submit, then move to the next section. That's it - labels and
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
  says so in the README - expect latency, don't re-ping.

## Filing plan (five today, one held back) and the AI question

**AI.** Matt has said (Discord DMs) he doesn't want AI-generated code
in his hobby projects - he uses plenty of AI at work; this one's for
him. So: issues, not PRs; no code diffs attached; fixes described in
prose. Michael's opener (below) discloses the AI-assisted provenance
up front. Still worth a skim of each body before pasting so the words
read as yours.

**The opener** - embedded verbatim at the top of every body:

> Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
> Python port/etc). While I was building that, I ran into a handful of
> issues. I found them with a lot of AI assistance, so I'm filing them
> as bug reports but not sending along any AI-generated code. I'm
> happy to provide more detail/etc. I'm filing 5 reports today, but I
> know you batch things up, so I'm including this as a header for each
> of them in case it's useful.

**Order** (same-day; lead with the reports whose value is most obvious
so the first issue Matt opens motivates the rest):

1. Report 3 - Gyro Ball over Shadow Ball (behavior reproduced on pvpoke.com)
2. Report 7 - Morpeko one-way form change (behavior reproduced on pvpoke.com)
3. Report 1 - dead dominance pruning (easy to confirm by reading)
4. Report 4 - buff-adjusted DPE overwritten (subtler code-flow issue)
5. Report 2 - bestChargedMove asymmetry (a question, reads best last)
6. Report 5 - retired-or-returning question (probably NOT filing today)

---

## 1st to file - Report 3 - Aegislash selects Gyro Ball over Shadow Ball (same cost, strictly less damage)

**Title:** Aegislash throws Gyro Ball over Shadow Ball vs Azumarill (identical energy, strictly lower damage)

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 5 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

**To reproduce (simulate mode, Great League; verified against
master 10fd1a6e4 on 2026-07-16):**

- Aegislash (Shield form), IVs 4/14/15, running Psycho Cut with Shadow Ball +
  Gyro Ball, against Azumarill, IVs 4/15/13, running Bubble with Ice Beam + Play
  Rough.
- Shields: 2 on each side. (Azumarill 2 vs Aegislash 1 behaves the
  same way.)
- Both of Aegislash's charged moves cost 50 energy, and both hit Azumarill's
  Water/Fairy typing neutrally with STAB. But Shadow Ball hits harder: 49 vs 39
  in Shield form, 101 vs 81 in Blade form.
- In the sim, Aegislash throws three Gyro Balls and never
  throws Shadow Ball. Azumarill shields the first two, the third
  lands, and Aegislash loses.
- If I make Shadow Ball the only charged move, Aegislash's rating
  clearly improves.

Having the strictly-worse move available actively hurts, and in my
testing it flips some close matchups.

**Root-cause candidate:** `Pokemon.js` ~746-752 blanket-flags ALL of
`aegislash_shield`'s charged moves as `selfDebuffing` (buffs [0,0]).
Because BOTH moves carry the flag, ActionLogic's same-energy /
higher-DPE swap corrections (~905-925) never fire, and the decision
routes through the self-debuff stacking branch - the decision log
shows "doesn't use Gyro Ball because it wants to minimize time
debuffed and it can stack the move 2 times". With shields up, every
charged move does 1 damage, so the DP plans tie and move ordering
picks Gyro Ball, with no guard left to prefer the strictly-stronger
Shadow Ball.

Possibly related existing issues: #47 (adding a third move worsens
rankings) and #149 (same-energy charged-move order affects results).

---

## 2nd to file - Report 7 - Morpeko form change is one-way instead of a toggle

**Title:** Morpeko sticks in Hangry form after the first charged move (gamemaster formChange says type "toggle")

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 5 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

**To reproduce (simulate mode, Great League):** Morpeko (Thunder
Shock / Aura Wheel + Psychic Fangs) vs Chansey (Zen Headbutt /
Dazzling Gleam + Psychic), 2 shields each. Morpeko fires one
Electric-type Aura Wheel, and every Aura Wheel after that is
Dark-type. The gamemaster's `morpeko_full_belly` entry says
`type: "toggle", trigger: "charged_move", moveId: "ANY"`, so those
should alternate.

**Where:**
[`src/js/battle/Battle.js:1536`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/battle/Battle.js#L1536):
the post-attack charged-move form trigger is gated on
`attacker.activeFormId != attacker.formChange.alternativeFormId`, and
`changeForm` (Pokemon.js:2344) only overwrites `this.formChange` when
the target form has its own (`if(form?.formChange)`, 2355) - which
`morpeko_hangry` doesn't (no `formChange` in the gamemaster). So the
first charged move flips Full Belly -> Hangry; after that,
`activeFormId == alternativeFormId` and the guard is false forever,
until a switch resets the form via `resetOnSwitch`. Grep confirms
nothing in `src/js` consumes `formChange.type == "toggle"` at all.

The relevant history: f0eac2fca ("Reworked Morpeko form change",
2024-10-02) implemented the toggle - `changeForm()` computed the
target from `defaultFormId`/`alternativeFormId` when
`type == "toggle"`. df75572b7 ("Fixed Morpeko", 2025-07-25) removed
that branch while cleaning up after the Aegislash form-change rework,
leaving only the first flip.

**Suggested fix:** for `type: "toggle"` form changes, let the trigger
fire from either form and compute the target as the form it's not in,
as the 2024 implementation did.

---

## 3rd to file - Report 1 - BattleState dominance checks reference nonexistent fields (dead code)

**Title:** ActionLogic: BattleState dominance checks read `.hp`/`.shields` which don't exist (always-false, dead pruning)

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 5 reports today, but I know you
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
`new BattleState(...)` constructor - also a nonexistent field (the
real one is `oppShields`), so farm-down states carry undefined
shields. Latent today (those states are terminal, so their shields are
never read), but if the dominance checks are ever renamed to
`.oppShields`, the constructor calls have to change in the same pass
or the renamed comparisons will still see undefined.

**Impact:** the DP queue's dominance pruning is silently inert.
Results are still correct (pruning is an optimization), but the DP
explores states the code clearly intends to discard, and anyone
reading the code may assume the pruning works.

**Suggested fix:** rename the fields in the checks to
`.oppHealth`/`.oppShields` and fix the two constructor calls together.
Note that enabling the pruning changes which plans win ties, so it
changes some battle outputs. (My Python port keeps a flag for both
behaviors; the "intended" variant also needs a buffs term in the
comparison to be safe.)

---

## 4th to file - Report 4 - initializeMove's buff-adjusted DPE is immediately overwritten

**Title:** Buff-adjusted move.dpe computed in initializeMove never reaches the bait/ratio logic (reset at the end of resetMoves)

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 5 reports today, but I know you
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
battle-simulation consumer - those all read the post-reset raw value.
And since `Battle.start()` calls `poke.reset()` -> `resetMoves()` for
every battle, there's no path where a battle sees the adjusted value.

One inconsistency worth noting: moves in the charged-move POOL that
aren't currently selected keep their buff-adjusted dpe (the reset only
touches active moves), and `generateMoveUsage` (1052, 1097) reads
pool-wide dpe - so that code sees adjusted values for unselected moves
and raw values for selected ones.

**Impact:** the DPE comparisons in baiting decisions treat e.g.
Power-Up Punch and a plain move of equal raw DPE identically - buff
awareness only enters via the coarse boolean `selfBuffing` flags,
although the init code reads as if the adjusted DPE should matter.

**Suggested fix:** either apply the buff adjustment after (or inside)
the reset loop at 791-796, or drop the adjustment in initializeMove if
the reset is the intended behavior. The reset also feeds the
bestChargedMove selection thresholds right below it (798-822), so the
two consumers are coupled.

Possibly related existing issues: #34 (Acid Spray's debuff not valued
in move selection - the user-visible symptom of exactly this) and
#149.

---

## 5th to file - Report 2 - opponent's bestChargedMove stays pinned to init-time form stats

*(Last of today's batch on purpose: it's a question, not a bug claim -
our own experiments could not show either behavior is better, and it
reads best once the other four have set the context.)*

**Title:** bestChargedMove selection asymmetry on form change: the form-changer re-selects, the opponent stays pinned to init-time stats - intended?

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 5 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

Unlike the other four, this one is a question about intent rather than
a bug claim.

`bestChargedMove` is selected in the block at the end of
[`resetMoves()`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/pokemon/Pokemon.js#L791)
(`Pokemon.js`, selection at lines 791-826, the 0.03 DPE threshold at
799). In simulate mode that runs once per Pokemon at battle init
(`Battle.start()` -> `reset()` -> `resetMoves()`). When a form-changer
transforms, `changeForm` (Pokemon.js:2344) calls `self.resetMoves()`
(2397) on the form-changer only - so the changer re-selects against
the opponent's current stats, but the OPPONENT's selection stays
pinned to the pre-change form's stats for the rest of the battle. No
in-battle path refreshes it.

**Concrete case (Ultra League):**

- Azumarill, IVs 4/15/13 at level 50, running Bubble with Ice Beam +
  Play Rough, against Aegislash (Shield form). (The specific IVs
  matter because the damage-per-energy numbers below depend on
  Azumarill's attack stat.)
- At battle start, Azumarill picks its best charged move against
  Shield form's 272 base defense: Ice Beam gives 0.273 damage per
  energy, Play Rough gives 0.300. The gap (0.027) is under the 0.03
  threshold, so the sim takes the cheaper Ice Beam.
- Then Aegislash transforms to Blade form, whose base defense is only
  97. Against that, the gap grows to about 0.088 - Play Rough is now
  clearly the better move.
- But Azumarill keeps throwing Ice Beam for the rest of the battle,
  because its selection was cached against the old form and nothing
  refreshes it.

(With PvPoke's default 15/15/15 Azumarill the same thing happens with
slightly different numbers: 0.309 vs 0.333 at the start, a gap of
about 0.082 after the transform.)

**Why I'm filing this as a question rather than a bug:** scores in
these matchups are sensitive to the choice (over 100 rating points in
some shield scenarios I measured), but when I tried "recompute per
decision" in my port, a bounding sweep showed it was NOT reliably
better - the recompute crosses the init-tuned 0.03/0.3 thresholds
mid-fight for non-strategic reasons, in both directions, including at
least one winner flip against the recompute. I reverted my port to
match your freeze. So: is the asymmetry (changer refreshes, opponent
doesn't) deliberate, or just where the code landed? If it's not, a
change here would move a lot of published Aegislash matchup scores.

Related existing issue: #134 - the same Azumarill Ice-Beam-over-Play-
Rough lock-in from the same selection block, but vs Bastiodon with no
form change. That one questions the init-time threshold itself; this
one is about the selection never being revisited.

---

## Holding back for now - Report 5 - is the chance-buff plan-selection system retired?

*(Reframed 2026-07-16: the caps-lock disable comment at
ActionLogic.js:538 is clearly deliberate, so this is a question, not a
bug claim. Michael is probably NOT filing it in the initial batch. If
filed on a later day, adjust the opener paragraph - its "5 reports
today" line belongs to the 2026-07-16 batch.)*

**Title:** Question: is the chance-buff plan-selection system
(changeTTKChance / stateList / needsBoost) retired for good?

**Body:**

Hey, this is Michael/TitanTrainers15, the guy who does gopvpsim (the
Python port/etc). While I was building that, I ran into a handful of
issues. I found them with a lot of AI assistance, so I'm filing them
as bug reports but not sending along any AI-generated code. I'm happy
to provide more detail/etc. I'm filing 5 reports today, but I know you
batch things up, so I'm including this as a header for each of them in
case it's useful.

In
[`src/js/battle/actions/ActionLogic.js`](https://github.com/pvpoke/pvpoke/blob/10fd1a6e43260e59b625d1cf96bbea496672880d/src/js/battle/actions/ActionLogic.js#L539),
line 539 sets `changeTTKChance = 0;` unconditionally, right under the
comment "DISABLE THE NON-GUARANTEED BUFF EVALUATION SYSTEM" (538) and
right after lines 519-536 set it from the move's `buffApplyChance`.
That reads like a deliberate off-switch, so this is a question rather
than a bug report: is the system permanently retired, or meant to come
back someday?

The reason I ask: while porting the code I found that the kill line
isn't the only thing keeping the system off. If line 539 were removed,
two more faults would still keep it inert:

1. `needsBoost` is declared `false` (793) and never assigned `true`
   anywhere in the file, so the plan-reorder gate at 868
   (`if (!needsBoost)`) always passes; the branch that picks
   `bestPlan` (796) never sets the flag.
2. Line 800 compares `stateList[i].chance > bestPlan` - a number
   against a BattleState object (presumably meant to be
   `bestPlan.chance`). It can't throw today because it can't execute:
   `stateList` is pushed only at 448 and the loop breaks on the first
   chance-1 KO state (450-451), so it never holds the two plans the
   else-if at 796 needs.

If the system is retired for good, the ~100 lines of accumulation and
reorder machinery now read as live logic with an off-switch that's
easy to miss. If it's coming back, the two items above are the actual
bug report.

---

## Report 6 - RETRACTED 2026-07-16: do not file

The 2026-06-11 draft claimed PvPoke's Blade->Shield reverse-level
overshoot (`blade_level / 0.5 + 2` in GL -> level 52 for a low-IV
Blade) reads past the CPM table. **False:** PvPoke's `cpms` array
(Pokemon.js:24) has 109 entries covering levels 1..55 via
`index = (level - 1) * 2`; level 52 -> `cpms[102]` = 0.8503..., a
defined value. Genuinely overshooting PvPoke's table would need a
Blade level > 26.5, unreachable under 1500 CP. The 2026-06-11
`KeyError: 52.0` was OUR bug - gopvpsim's CPM table stops at 51 - and
our clamp fix (`_aegislash_shield_level`, pinned by
`tests/test_pokemon.py::TestAegislashShieldLevelOverflow`) remains
correct for us. The draft's fallback claim (NaN comparisons in the
walk-down) was also wrong: an out-of-range level would give
`cpms.indexOf(undefined) = -1`, the `cpmIndex >= 0` guard skips the
loop, and `changeForm` would throw a TypeError - no NaN path exists.
DEVELOPER_NOTES "Form change gotchas" item 3 has been corrected to
match.

---

## Drafted 2026-08-24, NOT YET FILED - Report 8 - two `move.moveID` typos in the Cramorant logic (one likely intent-inverted)

Found during our port of the Cramorant update (commit `78c64048a`,
master tip at draft time); every line number below is from that commit.
Verified by dead-branch analysis + A/B measurement in our harness (see
caveat at the end). File AFTER Michael reviews; adjust the "today"
framing if other reports ship in the same batch.

**Title:** Two `move.moveID` (capital D) typos dead-branch the SURF
half of the Cramorant logic; the ActionLogic.js:1239 rule also looks
intent-inverted

**Body draft:**

While porting the Cramorant mechanics (78c64048a - thanks for the
detailed update notes!) we hit two places where `move.moveID` is read
instead of `moveId`. Since `moveID` is always `undefined`, the SURF
comparisons silently degenerate:

1. `ActionLogic.js:368` (the Dive/Surf-ASAP rule):
   `poke.activeChargedMoves.find(move => move.moveId != "DIVE" &&
   move.moveID != "SURF")` - the second clause is always true, so
   `nonGulpMove` is just "first move that isn't DIVE". For a SURF+FLY
   or SURF+HYDRO_PUMP Cramorant, `nonGulpMove` can be SURF itself, so
   the `nonGulpMove.dpe / gulpMove.dpe < 1.5` gate compares Surf
   against itself (ratio 1.0) and the rule fires unconditionally; for
   DIVE+SURF the find returns SURF and the rule's damage/DPE terms use
   the wrong move. (Harmless for the default Peck/Dive+Fly ranking
   build, which is presumably why it wasn't visible.)

2. `ActionLogic.js:1239`:
   `if(attacker.speciesId == "cramorant" && (move.moveId == "DIVE" ||
   move.moveID == "SURF") && move.damage > defender.hp){ useShield =
   false; }` - the SURF clause never matches, so the rule is DIVE-only.
   Separately from the typo: as written this makes defenders NEVER
   shield a *lethal* Cramorant Dive (it is the last statement before
   the return, so it overrides the lethal-hit shielding logic above
   it). Was the intent `useShield = true` (shield the lethal
   Dive/Surf)? As shipped it hands Cramorant free KOs through held
   shields.

Measured effect of fixing the :1239 rule (our PvPoke-port harness,
GL top-50-style + UL top-60 pools, default IVs, all 9 shield cells x
both bait modes): exactly 5 cells change, all Cramorant-worse -
Galarian Moltres GL (1v1 bait) W->L; Talonflame UL (0v2, both baits)
W->L; Talonflame UL (1v1, both baits) W->D. Small but strictly
score-inflating for published Cramorant results wherever it fires.
(Numbers are from our harness over our pools, not pvpoke.com's ranking
pool - the mechanism is the shipped code either way.)

Happy to PR either fix if useful - the minimal patch is `moveID ->
moveId` twice, plus (if the intent read is right) `false -> true` at
:1239.

**Pre-filing checklist:** re-run `git log 78c64048a..master -- src/js/`
for upstream fixes; search the issue tracker for "moveID"/"Cramorant"
duplicates; re-verify both line numbers against master tip.

## Drafted 2026-09-12, FIXED UPSTREAM 2026-09-27 (e87448291) - do not file - Report 9 - `hasActed` survives `Pokemon.reset()`, so a sandbox link's displayed battle is not the battle it encodes

**Status (2026-10-24):** superseded by PvPoke's own fix. Commit
`e87448291` "Sandbox mode fix" (2026-09-27) adds `previousTurnActions =
[]` to `Battle.start()`, with the message "previous turn actions weren't
properly cleared, causing some sandbox mode battles to have a one turn
delay and making subsequent action assignments invalid." The symptom is
the one described below (the one-turn delay on the page's second run) and
our replay test now pins the FIXED page: the UL Cramorant vs Lapras link
displays 662 with the scripted actions at [51, 0]
(`tests/test_pvpoke_sandbox.py::test_cancelled_charged_sandbox_replays_the_same_fight`,
`verify_url(page=True)`). Our diagnosis named `hasActed` as the field
that survives `reset()`; upstream cleared `previousTurnActions` instead,
and we have not re-derived whether `hasActed` still carries over in a way
that matters once that list is cleared. The draft is kept for the record.

**Status (original):** drafted from a browser-verified reproduction (pvpoke.com
1.40.1.6, engine JS byte-identical to master `a93147bf1`; gamemaster
2026-09-10). Not yet filed. Possibly the same root cause as the
unresolved site-vs-harness discrepancy noted under Report 3 on
2026-07-16 (site 429 where headless runs gave 510) - that page also
ran the same battle twice.

**Summary.** `Pokemon.reset()` (Pokemon.js:1924) restores HP, energy,
cooldown, shields, buffs and form, but not `hasActed`. `Battle.start()`
does not clear it either. So a Pokemon that acted on the final turn of
one `simulate()` starts the next `simulate()` on the same objects flagged
as having already acted, `getTurnAction` (Battle.js:724) skips its
turn-1 action, and its whole fast-move cycle runs one turn late for the
rest of the fight. In sandbox mode the scripted actions are matched by
exact turn (Battle.js:745), so every action of that Pokemon on the old
parity is silently dropped.

**Why users see it.** Loading a `/battle/sandbox/...` link simulates
twice: `loadGetData()` calls `runSandboxSim()` synchronously (Interface.js:
2233-2248: setActions + simulate + displayTimeline), and the
`.battle-btn` click triggered just before it (Interface.js:2223) fires
`startBattle()`'s `setTimeout` afterwards, which simulates again with
the same actions still set and re-renders. The page shows run 2.

**Reproduction (browser).** Cramorant (L26 5/15/13, Peck / Dive + Fly)
vs Azumarill (L43 4/15/13, Bubble / Ice Beam + Play Rough), 0-0,
scripted Dive T15, Ice Beam T20, Fly T30:

    /battle/sandbox/1500/cramorant-26-5-15-13-4-4-1-1/azumarill-43-4-15-13-4-4-1-1/00/0-1-2/0-2-3/15.100000-20.110000-30.101000/

One `simulate()` (headless, or the page's first run): Cramorant wins,
rating 690, 48 HP left, all three actions execute. The page displays:
Cramorant wins, rating 547, 12 HP left, "Energy Used 45" - the T15 Dive
never fires (Cramorant's Pecks now resolve on odd turns, so its cooldown
is not 0 on turn 15), no Gulp Missile, Fly does 57 instead of 71. A
second reproduction in the other direction: the UL Cramorant vs Lapras
(L36) 1-1 link in gopvpsim's tests replays 662 (win) once and 446 (loss)
on the page.

**Reproduction (headless).** Load Battle.js, set up the two Pokemon,
`setSandboxMode(true)`, `setActions(...)`, then call `simulate()` twice
and compare `getPokemon()[0].hp`; between the runs
`getPokemon()[0].hasActed` is `true` while everything else `reset()`
touches is back to its start value.

**Suggested fix.** Add `self.hasActed = false;` to `Pokemon.reset()`
(or clear it for both Pokemon in `Battle.start()` next to the
`processed` reset, Battle.js:249). Either makes consecutive
`simulate()` calls idempotent; the per-turn clear at Battle.js:302
already handles the in-battle case.

**Scope.** Anything that simulates twice on the same Pokemon objects
shows this: the sandbox share links above, and any UI flow that re-runs
after a settings change without rebuilding the Pokemon. Single-run
consumers (rankings, matrix) are unaffected.

## Drafted 2026-10-24, MOOT (we ported the rule the same day; not filing) - Report 10 - a form-animation round sets both cooldowns to 500 ms, letting both Pokemon act while a fast is still in flight

**Status (later 2026-10-24):** ported as PvPoke has it (class A, DEVELOPER_NOTES "Key implementation details", "Cooldown gates DECISIONS, not landings"); the in-game question (does the shell-break animation pause the battle like a charged move?) is unanswered but no longer a divergence. Kept for the record; not filing. Note the draft below mis-describes the effect: the reset does not shorten the in-flight fast move (queued fasts resolve on their own turn clock), it lets the Pokemon act again while the fast is still in the air.

**Status (original):** drafted from the 2026-10-24 Minior sweep (gopvpsim vs
`pvpoke_trace.js` at master `38f70320d`, 702 cells, ~35 attributed to
this). Not yet filed. Frame as an intent question, not a bug: the game
does interrupt fast-move animations with a charged move, and whether the
remaining cooldown is forgiven is exactly what we do not know.

**Summary.** `Battle.js:548` (inside the per-Pokemon end-of-turn loop):

    // Reset after a charged move
    if(roundChargedMoveUsed || roundFormAnimation){
        poke.cooldown = 500;
    }

The `roundChargedMoveUsed` arm is old (2019) and our engine already
matches it; the question is the `|| roundFormAnimation` arm added in
`4d2908fac`. `roundFormAnimation` is set only by the `hp`-trigger form
change (Battle.js:1668), i.e. Minior's Meteor -> Core flip, so this is
Minior-specific. On a flip turn every Pokemon's cooldown becomes 500 ms
regardless of what it was: a Pokemon one turn into a 3-turn fast move
(cooldown 1000 left) resolves it on the next turn, for full damage and
energy, one turn early; the side that was mid-fast-move gains a turn.
Not being filed for now (2026-10-24: no response yet to the July batch).

**Where it shows.** Any multi-turn fast move in flight during a charged
round; Minior makes it frequent because its Meteor -> Core change carries
`animationTime: 5000` and often lands mid-Rollout (the `hp` trigger fires
off fast damage). Minior (Core) L24 5/14/15 Rollout / Acrobatics + Power
Gem vs Lickitung 7/15/15 Lick / Body Slam + Power Whip, 1-1: PvPoke 408
for Minior, a model without the reset 403; vs Charjabug 4/14/15 Volt Switch
/ X-Scissor + Discharge, 1-1, the winner changes (PvPoke 626 vs 210). Both
opponents at their GL best level (`userdata/logs/minior_midflight_sweep_5.log`;
reproduce either cell with `scripts/pvpoke_trace.js` before filing).

**Question for upstream.** Is the early completion intended -- i.e. does
the game forgive the remaining cooldown after a charged-move pause -- or
should the reset only apply when `poke.cooldown` was already <= 500 (so
an in-flight fast move keeps its remaining duration)? If the former, a
one-line comment at :548 saying so would spare the next porter the trace.

## Drafted 2026-10-24, NOT YET FILED - Report 11 - Minior `getFormStats` steps whole levels in battle but half levels in the UI (`this.decrementer` typo)

**Status:** drafted; see DEVELOPER_NOTES "PvPoke bugs found" #11 for the
runtime confirmation (2026-10-24, master `38f70320d`).

**Summary.** `Pokemon.js:2590-2612` (Minior branch of `getFormStats`):
the level walk steps 0.5 when `this.activeFormId == "minior_core" ||
this.decrementer == "minior_meteor"`, else 1. `decrementer` is never
assigned anywhere in `src/js`, so the second clause is always false and
reads as a typo for a form-id check. `changeForm` sets `activeFormId` to
the new form BEFORE calling `getFormStats`, so the battle-start Core ->
Meteor change evaluates the clause with `activeFormId == "minior_meteor"`
and steps whole levels, while `PokeSelect` calls `getFormStats` while Core
is still active and steps half levels. The displayed Meteor CP/level on
the site and the Meteor stats the simulator fights with therefore disagree
for roughly a third of Great League spreads: 10/6/10 displays L43.5 and
sims L43.0; 12/14/12 displays L40.5 and sims L40.0 (5/14/15 agrees at
L44.0).

**Suggested fix.** Replace the dead clause with the intended one (or step
0.5 unconditionally, since the walk is "highest level whose CP fits" and a
half-level grid is the game's). Either makes the UI and the simulator
agree; which level rule matches the game is a separate question the
community is still measuring.

**Our handling.** Ported the battle path as-is behind
`formchange.MINIOR_HALF_LEVEL_STEP`, pinned on both settings
(`tests/test_minior.py::test_meteor_level_from_stored_core_gl`).
