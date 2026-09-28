# Divergences from PvPoke

> **Note on authorship.** This document was drafted by Claude (Anthropic's
> Claude Code), so the tone may read as AI-like in places. The technical
> content is verified against tests and PvPoke's reference engine; the
> root-cause writeups it summarizes live in `DEVELOPER_NOTES.md`.

Our scores match PvPoke's almost everywhere (the oracle audit in
`scripts/audit_oracle_harness.py` is exact on score, winner, and charged-move
log for the large majority of its cells). The simulator is a faithful port;
the handful of intentional differences below each have a reason and a pinned
test or documented guard, and the full root-cause writeups live in
`DEVELOPER_NOTES.md`. These all apply to the current (new) turn mechanics,
the default since 2026-09-09.

1. **The one dpe site kept fresh: the don't-bait dpeRatio carve-out.** We now
   FREEZE move selection exactly like PvPoke (ordering, each move's raw dpe,
   best charged move, and the farm-down constants are fixed at battle start and
   re-fixed only on a self form change) -- the old "we recompute every turn and
   it's strictly better" claim was falsified by the 2026-07-03 NB-1 bounding
   sweep and is gone. The single deliberate exception is PvPoke's post-DP
   "don't bait if the opponent won't shield" check: PvPoke forms its dpe ratio
   from `move.damage`, which it refreshes only on use, so one move is current
   and the other init-stale -- an internally inconsistent cache bug. We evaluate
   both moves fresh at the current stage instead. Pinned in
   `tests/test_nb1_selection_freeze.py` Group C.
2. **Morpeko toggles form on every charged move.** The game, and Morpeko's own
   gamemaster entry, toggles Full Belly <-> Hangry after each charged move.
   PvPoke changes it one way and then sticks in Hangry. Ours matches verified
   in-game behavior.
3. **Aegislash's Shadow Ball vs Gyro Ball pick -- RESOLVED upstream
   2026-08-31; we match PvPoke.** Our Aegislash (Shield) threw Shadow Ball
   where PvPoke threw Gyro Ball (same energy, and Shadow Ball does strictly
   more damage against Azumarill). We reported it as pvpoke/pvpoke#378.
   PvPoke's own generalization of its move logic for third charged moves
   (`574aeb0da`) changed the shields-up "prefer the non-debuffing move"
   check from `selfBuffing` to `selfDebuffing`, and PvPoke now throws Shadow
   Ball there too: the affected oracle cells match on score and on the
   charged-move log, and reverting that one check in a copy of PvPoke's JS
   brings the old difference back (DEVELOPER_NOTES "Current status"). The
   six Aegislash x Azumarill form-change cells that still differed under the
   new turn system were resolved on 2026-09-27, on our side: we priced
   Shield-form charged moves at the Shield form's Attack, while PvPoke
   (correctly) uses the Blade form's, which is what the throw lands with.
   They now match PvPoke on score, winner and charged-move log.
4. **Near-KO plan choice: one big self-debuffing move vs a chain of cheaper
   moves -- RESOLVED 2026-09-25, we now match PvPoke.** In a shields-down
   endgame PvPoke swaps a self-debuffing nuke for a chain of cheaper
   non-debuffing throws; our port of that rule only saw the damage number it
   reads when the nuke was already affordable, so we kept the nuke. That was
   kept as a deliberate choice in April 2026 because it retained more HP under
   the old turn system; re-measured under the current turn system PvPoke's
   chain scored better in every measured cell, so the rule now fires where
   PvPoke's does (DEVELOPER_NOTES "Near-KO DP plan choice") -- with one
   exception we keep: when every charged move is self-debuffing, PvPoke
   swaps one debuffing nuke for another worse-typed one and loses; ours
   keeps the nuke (docs/reviews/2026-06-28_both_self_debuff_divergence_cluster.md).
5. **Battle-length guard.** PvPoke ends a fight on a 240-second display clock
   that mixes turn time with charged-move animation time; ours is a flat
   500-turn cap. Both are infinite-loop guards and neither is reachable in a
   real 1v1, so the simpler guard costs nothing observable.
6. **A self-debuffing move is not thrown into a shield it can't get past
   (no-bait analysis only).** When our attacker's biggest move is self-debuffing
   (Brave Bird, Superpower, Wild Charge) and the opponent would shield it anyway,
   we throw a cheaper non-debuffing move instead -- the shield is spent either
   way, so this only avoids eating the -atk/-def for nothing. PvPoke ties this
   swap to its bait toggle, so with baiting off it throws the self-debuffing nuke
   into the shield, a strictly worse line. This only affects bait-off analysis
   (the oracle runs bait-on and never sees it); ours keeps those matchups honest
   (traced: Malamar vs Furret 1-1, ours 769 vs PvPoke's 237).
7. **Shield-form Aegislash's charged-move estimate keeps its Attack stage.**
   Following PvPoke, Aegislash in Shield form estimates its charged moves
   with the Blade form's Attack (the throw changes form before it lands). We
   also apply Aegislash's current Attack stage to that number; PvPoke uses
   the unstaged Blade Attack, although the throw it then resolves does apply
   the stage. The two agree unless an opponent has lowered Aegislash's Attack
   (Rock Tomb, Icy Wind, ...); then ours estimates exactly the damage the
   throw deals. In a 1080-cell Great League sample this decides 15 cells,
   with winner changes going both ways (3 of 4 favour Aegislash under ours).
   Pinned in `tests/test_form_change_oracle.py`
   (`test_cradily_vs_aegislash_blade_estimate_stage_divergence`) and
   DEVELOPER_NOTES "Form change gotchas" item 6.
8. **Shield-start Aegislash's first charged move doesn't depend on the order
   the moves were entered.** Both engines order same-energy charged moves so
   the one that hits harder goes first, and both then mark all of Shield
   Aegislash's moves as "farm energy, don't throw" -- which also switches that
   ordering rule off. In PvPoke that marking sticks from the setup steps that
   run before the fight, so the rule is already off at the start and
   Aegislash's first throw is simply whichever move was entered first
   (Shadow Ball in the default moveset). We clear it between fights, so our
   first throw is the move that does more damage to this opponent: Gyro Ball
   where Ghost is resisted or Steel hits hard (Moltres-G, Guzzlord, Fairies).
   Usually that is a shielded throw either way and changes nothing (52 of a
   1080-cell sample differ only in the log); in 5 cells it is the last
   unshielded throw and ours scores about 100 points higher for Aegislash.
   Entering the moves as [Gyro Ball, Shadow Ball] in PvPoke reproduces our
   fights exactly. A small, understandable setup-order effect rather than a
   decision anyone made; we keep the damage-first pick. Pinned in
   `tests/test_form_change_oracle.py`
   (`test_aegislash_shield_vs_moltres_g_first_throw_divergence` plus its
   Gyro-Ball-first positive control) and DEVELOPER_NOTES "PvPoke bugs found"
   #10.

We also deliberately do NOT replicate one block of PvPoke's decision code (its
non-guaranteed-buff "needsBoost" plan selection): that code is disabled
upstream and never runs, so copying it would make us diverge from PvPoke's
actual behavior rather than match it.

Turn system: the in-game turn changes (`mechanics='new'`) are the default
everywhere since 2026-09-09 (7e6a82b), the day PvPoke merged its own
implementation to master; every published score since the 2026-09-10/12
bake uses them, and `simulate()` refuses the retired legacy system unless
explicitly opted in (2615c6e). The oracle audit is cross-checked against
PvPoke master under the new system (CHANGELOG 2026-09-09..10).

## Keeping this list current

- **When you add or remove a divergence, update this document and
  `DEVELOPER_NOTES.md` together.** The `CLAUDE.md` policy ("When our sim
  diverges from PvPoke") requires every divergence to carry a test with a
  specific reason and an inline code comment (since 9f1da69, 2026-09-25,
  `tests/test_battle.py`'s divergence cells are real pins at our value with
  PvPoke's value in the message, not xfails); this document is the
  human-readable index of those.
- **Re-vet against PvPoke upstream when the tripwire fires.** PvPoke's battle
  logic lives in `Battle.js`, `actions/ActionLogic.js`, `DamageCalculator.js`
  and `pokemon/Pokemon.js`. `tests/test_rebalance_tripwire.py` pins their
  sha256 in `tests/fixtures/pvpoke_engine_digests.json` (last re-vetted
  2026-09-10) and fails when the `../pvpoke` checkout drifts; the procedure
  is `docs/rebalance_checklist.md` section B -- read the upstream commits,
  re-run the oracle audit (`scripts/audit_oracle_harness.py`), then update
  this list, the re-vetting log in `DEVELOPER_NOTES.md`, and the digest
  fixture.
