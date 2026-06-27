# Engine correctness bug-hunt — 2026-06-27

Adversarial multi-agent bug-hunt of the battle engine vs the PvPoke oracle
(7 subsystem finders -> per-finding double verification: one "is this
documented?" skeptic + one "reproduce/refute empirically" skeptic ->
triage). 6 confirmed, 12 dismissed.

## Status / what's been actioned

- **Bug #1 (HIGH, `cmp_atk` double-fire gate): FIXED** on branch
  `overnight/2026-06-26`. Independently reproduced (Shadow Quagsire vs
  Gastrodon, all 9 shields vs `pvpoke_trace.js`: 2v1 winner-flipped
  625/375/Quagsire -> 459/540/Gastrodon, now matches the oracle exactly),
  fixed, pinned by a new regression test. See commit.
- **Bugs #2-#6: LEFT FOR YOUR REVIEW (not auto-fixed).** Each needs a
  judgment call or a broad re-vet that shouldn't happen unattended:
  #2 shifts many fixtures (float32 damage constants), #3 and #5 need
  GL/UL grid winner-flip checks, #4 is a cache-version bump, #5 is an
  explicit gate-or-document decision. My recommendation per bug below.
- **Blast-radius note:** the overnight ML bake started on the PRE-#1-fix
  engine, so any Master-league SHADOW guide it produced may carry the
  bug-#1 behavior in the narrow CMP window. Nothing is published. If you
  take the #1 fix, re-bake the shadow ML guides before trusting them.

---

## Confirmed bugs (by severity)

### 1. [HIGH — FIXED] `fire_now` double-fire CMP gate uses shadow-boosted `.atk` instead of `.cmp_atk`
- **Where:** `src/gopvpsim/battle.py:1177-1178` feeding the gate at `:1188` (`a_atk > d_atk`).
- **Repro:** Shadow Quagsire vs Gastrodon 2-shield-ish: our sim said Quagsire wins; PvPoke oracle says Gastrodon wins. The shadow x1.2 was folding into a charged-move-PRIORITY comparison (it boosts damage, not priority).
- **Evidence:** PvPoke `ActionLogic.js:181` compares shadow-free `poke.stats.atk`. The 2026-06-13 shadow-CMP migration switched 9 CMP sites to `.cmp_atk`; this was the missed 10th. Any defender whose `stats.atk` sits between a shadow attacker's `cmp_atk` and boosted `atk` (a common GL window) flips this branch.
- **Fix (applied):** `a_atk = attacker.cmp_atk` / `d_atk = defender.cmp_atk`. Pinned by `tests/test_fire_now_cmp_shadow.py` (9-cell oracle snapshot).

### 2. [MEDIUM] Damage formula uses exact `1.3 / 1.2 / 1.6` constants instead of the game's float32-truncated values
- **Where:** `src/gopvpsim/moves.py:19-20` (`STAB_MULTIPLIER`, `BONUS`), `:242` (`damage()`), super-effective `1.6` cells (e.g. `:39`).
- **Repro:** Tinkaton Play Rough vs Gourgeist (Small) 0/0 15/15/15 -> our Play Rough = 51 (score 422); `pvpoke_trace.js` = 52 (score 427). The raw product lands exactly on the floor boundary; exact doubles -> 50.999 -> 51, float32 constants -> 51.0000002 -> 52.
- **Evidence:** PvPoke `DamageCalculator.js` uses `BONUS=1.2999999523162841796875`, `STAB=1.2000000476837158203125`, `SUPER_EFFECTIVE=1.60000002384185791015625` = `struct float32(1.3/1.2/1.6)` — the game computes damage in single precision, so PvPoke and the real game agree and our exact doubles are wrong. ~0.009% of damage calcs flip by 1 (253/2.76M across GL top-120, 19 at neutral stages) — but they land precisely on the breakpoint/bulkpoint boundaries that are the project's core deliverable.
- **Recommendation:** Worth fixing, but it WILL shift fixtures and must be re-vetted broadly. Set the three constants to PvPoke's float32-truncated doubles; derive double-super-effective from `f32(1.6)*f32(1.6)` (not exact 2.56); leave the exactly-representable `0.625`/`0.390625` resist cells. Add a boundary regression test (Tinkaton Play Rough vs Gourgeist (Small) = 52, score 427). **Do not auto-apply — re-run the full oracle audit + suite and reconcile fixture drift.**

### 3. [MEDIUM] Farm-down path never stacks self-debuffing moves (throws them at first affordability)
- **Where:** `src/gopvpsim/battle.py:1283-1311` (farm-down early-return), fire-at-affordable check around `:1298-1306`. Reference: `ActionLogic.js:396-405`.
- **Repro:** `scripts/battle.py --policy pvpoke_dp --trace-dp Pinsir FURY_CUTTER CLOSE_COMBAT,SUPER_POWER Cresselia 0-0` -> Pinsir fires CLOSE_COMBAT at T15, score 631; PvPoke holds both self-debuffs and stacks Superpower-then-Close-Combat near T25-26, score 656. Same winner, 25-pt gap from ~10 extra turns at -2 def.
- **Evidence:** PvPoke's farm branch has a self-debuff stacking gate (`energyToReach`, RETURN until reached) that our farm early-return omits; it also bypasses the near-KO `bandaid[918]` which has the stacking. Same class as the documented 2026-06-11 Snorlax OMT finding, at an undocumented site.
- **Recommendation:** Fix using the farm-branch formula (fast-move `energyGain`, not bandaid[918]'s cm form). **Verify GL/UL grids for winner flips before committing** (the report's own caveat). Pin with a Pinsir-vs-Cresselia oracle test.

### 4. [MEDIUM] Slayer disk-cache key omits the focal cohort level cap (stale cross-level hits in Master mirror-slayer dives)
- **Where:** `scripts/slayer_cache.py:50-90` (`compute_cache_key`); triggered via `deep_dive.py` `--max-level` mutating global `LEAGUE_MAX_LEVEL`.
- **Repro:** Master Dialga mirror-slayer at `--max-level 51` then `--max-level 50`: second run reuses L51 scores for an L50 cohort (the cache key is byte-identical across caps, but the cohort stats/CP differ).
- **Evidence:** Silent-wrong deep-dive output — wrong Top-Mirror IVs / CMP% / membership. The sibling SWEEP cache got this right (`focal_max_level=_eff_focal_cap`, pinned by `test_sweep_cache.py:110`); the slayer cache has the asymmetric gap.
- **Recommendation:** Thread `_eff_focal_cap` into `compute_cache_key`, bump `CACHE_VERSION`, add a level-cap separation test mirroring `test_sweep_cache.py:110`. Clean, low-risk, well-evidenced — but it's a cache-version bump, so I left it for you to schedule.

### 5. [MEDIUM/LOW] `bandaid[929]` stack-switch is missing the `bait_shields` gate the reference requires (no-bait mode divergence)
- **Where:** `src/gopvpsim/battle.py:1705` (`elif defender.shields > 0 and n_cms > 1:`). Reference: `ActionLogic.js:947-952` (`poke.baitShields && ...`).
- **Evidence:** Every sibling bandaid is correctly bait-gated; this `elif` omits `bait_shields` (the inline comment even mis-cites "929-933"; real clause is 947-952). Default `bait_shields=True` fires in both engines so the oracle suite never exercises it — confined to no-bait deep-dive analysis (thresholds/CD articles).
- **Decision point (yours):** either gate it (`elif bait_shields and ...`, fix the comment) to match the reference, OR keep current behavior (not switching off a self-debuff into a shield is arguably better) and document it as an intentional divergence with an xfail. The actual defect is that it is currently NEITHER gated NOR documented. Add a no-bait regression test either way.

---

## Contested (code divergence real, but a 360-sim sweep showed it cosmetic)

### `bandaid[910]` defer-self-debuff evaluates the defender's MAX-DAMAGE move, not its `bestChargedMove`
- **Where:** `src/gopvpsim/battle.py:1682-1686`. Reference: `ActionLogic.js:929-933`.
- **Status:** Code divergence is real (line 1682 uses `max(..., key=charged_move_damage)` where PvPoke uses DPE-selected `bestChargedMove`), but a 360-sim GL-top-120-vs-Malamar sweep found bandaid[910] fires 16 times and ALL 16 match the oracle exactly on score+winner. The candidate's "40 vs 45 energy" claim is factually wrong (Foul Play and Superpower are both 40e).
- **Recommendation:** Low-priority consistency cleanup, NOT a shipping bug. If applied, note the 16 fire-cases stay score-identical. Do not present as a correctness fix.

---

## Dismissed (checked, not actionable)

Documented as known/intentional divergences (DEVELOPER_NOTES / CHANGELOG / TODO):
- New-mode `_fm_since_charge` not reset after a charged move (new_mechanics) — documented.
- New-mode drops per-charge cooldown / `_queued_fast` reset (new_mechanics) — documented.
- `test_new_decisions_identical_to_legacy` feeds hand-built states, not new-mode sim states — documented.
- Simultaneous deferred charged moves apply legacy CMP cancellation under new mode — documented.
- OMT `turnsPlanned` divides energy by cheapest-affordable move, not `activeChargedMoves[0]` — documented.
- `_cheapest_cm` uses min-energy proxy vs PvPoke's priority-shuffled `activeChargedMoves[0]` — documented.

Refuted / cosmetic / not impactful on investigation:
- Mimikyu disguise-break checked before `turnsToLive`/lethal-charged (dp_charged) — reorder real, outcome identical.
- `_cm_debuf_delta` self-buff clause dead code (`'1' == 1` string/int mismatch) — real but cosmetic (sweep showed no score impact).
- Shield cycle/turn math clamps `Math.ceil` with `max(0,...)` PvPoke lacks — analytically equivalent.
- `bandaid[910]` max-DAMAGE vs `bestChargedMove` — same site as Contested above; cosmetic.
- Breakpoint/bulkpoint thresholds inherit the exact-constant damage formula — subsumed by #2.
- Aegislash Shield energy-farm gate uses max-affordable-damage vs `bestChargedMove.damage` (formchange).

---

*Note: `_cm_debuf_delta` `'1' == 1` (dismissed as cosmetic by the sweep) is
a latent string-vs-int comparison bug worth a separate cheap fix even
though it didn't move scores in the tested cases — flagged here so it's
not lost.*
