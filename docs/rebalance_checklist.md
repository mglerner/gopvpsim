# Move-rebalance / PvPoke-update response checklist

Pointed at by the two tripwires in `tests/test_rebalance_tripwire.py`.
Context: a big move rebalance is expected ~2 weeks post-Worlds
(Michael, 2026-08-25 -- the usual pattern), and PvPoke periodically
updates its battle AI (the Cramorant update was exactly this). These
steps make either event a procedure instead of a scramble.

## A. When the MOVE-DATA tripwire fires (existing move changed/removed)

1. **Cache migration (gamemaster leg):** keep the OLD gamemaster blob
   (`git -C ../pvpoke show <old>:src/data/gamemaster.json`, or the
   copy in `userdata/gamemaster_vintages/`), then
   `migrate_cache.py --from-gamemaster <old stamp>
   --old-gamemaster-file <old blob> --apply`. The affected set is
   COMPUTED from the delta -- most columns bless.
2. **Re-verify the PoGoDives strat's fitted constants** (they were
   tuned on pre-rebalance move data -- re-confirm, never assume):
   `cramorant_policy_lab.py --pogodives-verify` across the round-7
   file set (~10 min; both leagues, Dive+Surf, withhold, IV spreads).
   If the plateau moved: re-tune per the campaign discipline
   (docs/cramorant_policy_plan.md) before any re-publish.
3. **Spot-check round-6 discriminators** (if any shipped): they are
   mechanism-derived and re-derive at battle time by design, but their
   holdout evidence was pre-rebalance -- one lab pass to confirm.
4. **Refresh oracle fixtures if their cells moved** (a data change
   shifts both sims identically, so usually nothing moves; the audit
   says for sure): `audit_oracle_harness.py`.
5. **Re-pin the tripwire fixture** to the new vintage
   (`tests/fixtures/strat_vintage_moves.json` -- regenerate with the
   snippet in the test's docstring) in the SAME commit as the
   re-verification results, so the guard re-arms at the new baseline.

## B. When the PVPOKE-ENGINE tripwire fires (battle JS changed)

1. `git -C ../pvpoke log <last-vetted>..master -- src/js/` -- read the
   commits; classify sim-relevant vs UI (the Cramorant port review's
   three-bucket pattern: species-specific / global-behavior / UI-only).
2. **Run the full oracle audit** (`audit_oracle_harness.py`): zero
   drift = the change didn't touch our vetted surface; any MISMATCH =
   re-vet per DEVELOPER_NOTES "PvPoke re-vetting log" conventions.
3. **Check for AI/strategy changes specifically** (ActionLogic.js /
   the decision layers): if PvPoke tuned or added strategy rules,
   decide port-vs-diverge per CLAUDE.md "When our sim diverges from
   PvPoke" -- and check whether it affects the PoGoDives comparison
   (our strat is defined RELATIVE to pvpoke_dp).
4. **Re-pin** `tests/fixtures/pvpoke_engine_digests.json` at the newly
   vetted commit, same commit as the re-vet record.

Tone reminder for anything public that comes out of either event:
warm toward PvPoke (memory: feedback-pvpoke-tone).
