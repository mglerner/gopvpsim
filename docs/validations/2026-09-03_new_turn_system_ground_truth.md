# In-game ground truth for the new turn system (Caleb Peng, 2026-09)

**This is the first description of the LIVE game's turn system we have had.**
Until now both our `mechanics='new'` and PvPoke's new-mechanics branch were
readings of a published spec, neither validated against play -- which is why
`2026-09-02_new_mechanics_oracle_ab.md` ends with "at least one of us is wrong
in ways neither has caught."

Source: <https://youtu.be/p6hGHYMShb0> -- Caleb Peng, breaking down every
difference between the legacy and new PvP systems, with side-by-side in-game
footage of the same matchup under each. Auto-captions pulled 2026-09-03;
working copy of the transcript is in the session scratchpad, not committed
(third-party content). Timestamps below cite the video.

Caveat on standing: this is one creator's account, not a Niantic spec. It is
strong evidence -- a top-level player, demonstrating each claim with paired
footage rather than asserting it -- but it is not a primary source, and where
it and a future Niantic statement disagree, the statement wins.

## The claims

1. **Charged attacks take priority over fast-attack damage.** If a fast attack
   would KO you on the turn you throw a charged move, you now get the charged
   move off anyway. If it KOs the opponent you avoid the fast damage entirely;
   if it does not, you faint immediately after. [01:02, 01:32]

2. **A charged move's buffs/debuffs apply BEFORE the incoming fast-attack
   damage registers.** Demonstrated with a self-defense-debuffing move: throw
   it, the debuff lands, and the incoming fast attack is then computed against
   the lowered defense -- the health bar visibly re-adjusts downward after the
   throw. Under the legacy system the fast damage applied first. [02:03-03:35]

3. **Swaps take priority over fast-attack damage**, so damage transfer now
   works at a one-turn difference. [03:35-04:06]

4. **Zero-turn swaps for BOTH players** after a charged attack, not only for
   the player who threw it. [04:06-05:36]

5. **Stated order of operations: swaps > charged attacks (including their
   buffs/debuffs) > fast attacks.** [06:07]

6. Meta consequence: spammy Pokemon that throw more charged attacks are
   stronger; long-turn-duration fast moves are weaker, because their damage no
   longer registers ahead of an incoming charged attack. [07:08-07:40]

## What this settles for us

**It is a priority ORDERING within a turn, not a one-turn deferral.** Claim 5
is an ordering of actions inside a turn; nowhere is a charged move described
as resolving on the following turn.

That is decisive for the open question in the A/B writeup:

| model                                | charged resolution                                                                    | matches claim 5? |
| ------------------------------------ | ------------------------------------------------------------------------------------- | ---------------- |
| ours, `mechanics='new'`              | deferred to the TOP of the next turn (`_pending_charged`)                             | no               |
| PvPoke, current new-mechanics branch | same turn, priority-ordered (`requiredTimeToPass = 0` + 1000 ms post-charge cooldown) | yes              |
| PvPoke, `041d8c722` only             | deferred by 500 ms to the next turn                                                   | no               |

So PvPoke's REVERT in `442a4afe8` -- the commit its author marked "for now",
and the single commit accounting for 45 of our 104 mismatches -- moved it
TOWARD the live game, and our model is the one implementing the rule the game
does not use. The provisional-looking change was the correct one.

This removes the reason to keep waiting on our side of the question. It does
not remove the reason to wait for the MERGE (we still want a stable reference
to port against, and the move rebalance is still guessed), but it changes the
expected outcome of the re-port from "adopt a coin-flip" to "adopt the model
the game demonstrably uses".

## FIXED, same day: our model now matches

`mechanics='new'` was corrected to resolve charged moves at step 2.5 -- the
same turn, ahead of the fast landings -- instead of deferring them to the top
of the next turn. The change is a REORDERING, and it deleted machinery rather
than adding any: `_pending_charged`, the `allow_dead_attacker` deferred
resolve, and the "withhold the faint break" guard all existed only to make the
deferral behave, and the ordering gives both observable behaviours for free.

Result against PvPoke's new-mechanics branch, same harness and roots as the
attribution run:

| our `new` vs PvPoke new-mechanics | mismatches |
| --------------------------------- | ---------- |
| before                            | **104**    |
| after                             | **1**      |

Legacy control unchanged at 0/243, so port fidelity is intact.

That is the validation the A/B writeup asked for: Caleb's description, PvPoke's
reverted-to model and our corrected model all agree. The commit its author
marked "for now" was right.

### The discriminator, built

The earlier failed attempt (Zekrom Wild Charge vs Dialga, 364/635 under BOTH
models) failed because the matchup never reached the situation. The working
version tunes it so the ordering decides an OUTCOME rather than a total: the
defender's fast deals **63** un-debuffed and **94** after -2 defence, so an
attacker on exactly 94 HP dies to the debuffed hit and survives the un-debuffed
one with 31 left. Pinned as
`test_new_charged_debuff_applies_before_incoming_fast_damage`, and verified
fail-first -- reverting the ordering fails it and the charged-survives test.

### Known residual (1 cell)

`aegislash_blade_vs_azumarill_form_change [1v0]`: same winner, score 584/415
ours vs 712/287 PvPoke, chargedLog differs. A form-change interaction with the
new ordering, not chased. It is 1 of 243 and does not flip a winner; worth a
look before any bake that leans on Blade-form numbers.

Claims 3 and 4 concern SWAPS and are unreachable in our 1v1 core (`simulate()`
takes exactly two BattlePokemon and has no incoming-Pokemon path). They matter
only for the out-of-scope team-sim work -- but note claim 6: the meta
consequences Caleb draws are partly driven by the swap rules, so a
spreads-level reading of "spammy is stronger" should not be attributed purely
to the charged-priority change.
