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

## Not yet established

Claim 2 is the cleanest discriminator between the two models -- our deferral
would apply the debuff a turn later than PvPoke's priority ordering -- and a
first attempt to exhibit it in our engine did NOT isolate it: Zekrom
(Wild Charge, self-def-debuff `[0,-2]`) vs Dialga in ML scored 364/635 under
BOTH `legacy` and `new`, differing only in turn count (19 vs 20). That means
the matchup never reached the situation, not that the models agree. A real
discriminator needs the self-debuffing charged move and an opposing fast move
landing on the SAME turn, with the defender's HP near the boundary where the
extra debuffed damage changes the outcome. Worth building as a fixture before
the re-port, so the re-port has a test that fails for the right reason.

Claims 3 and 4 concern SWAPS and are unreachable in our 1v1 core (`simulate()`
takes exactly two BattlePokemon and has no incoming-Pokemon path). They matter
only for the out-of-scope team-sim work -- but note claim 6: the meta
consequences Caleb draws are partly driven by the swap rules, so a
spreads-level reading of "spammy is stronger" should not be attributed purely
to the charged-priority change.
