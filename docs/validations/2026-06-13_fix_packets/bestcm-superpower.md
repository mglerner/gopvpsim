# Fix packet: bestcm-superpower

Date drafted: 2026-06-12 (overnight, READ-ONLY session — patch NOT applied)
Fix ID: `bestcm-superpower`
Patch: `userdata/fix_packets_2026-06-13/bestcm-superpower.patch`
(verified `git apply --check` clean against HEAD a73d855)

## What this fixes

Oracle-grid family `bestcm_estimate`: **38 cells, max |d| 205, expected
+38 fixed / 0 broken** (grid_summary.md line 33: "PROBE: faithful
selectBestChargedMove fixes all, breaks 0").

`_estimate_best_cm` (battle.py:127) feeds exactly one consumer: the
defender-bestCM shield gate in `pvpoke_simulate_shield`
(battle.py:214-215, our port of Battle.js:1105-1124, shipped
2026-04-15 commit 359e693). The old implementation picked the strict
max-actual-DPE charged move, which returns SUPER_POWER for Malamar
against most opponents. PvPoke's real `bestChargedMove` is computed by
`selectBestChargedMove` on the priority-shuffled `activeChargedMoves`
and carries a literal SUPER_POWER carve-out, so PvPoke's Malamar
bestCM is FOUL_PLAY vs most of the GL pool — PvPoke never enters the
Battle.js:1105 branch and always-shields, while we entered it and
(via wouldShield) declined shields.

## PvPoke reference (clone `~/coding/MGLPoGo/pvpoke`, SHA 9b7407782)

`src/js/pokemon/Pokemon.js`, selectBestChargedMove, lines 791-804:

```js
791    self.bestChargedMove = self.activeChargedMoves[0];
792    self.bestChargedMove.dpe = self.bestChargedMove.damage / self.bestChargedMove.energy;
793
794    for(var i = 0; i < self.activeChargedMoves.length; i++){
795        var move = self.activeChargedMoves[i];
796        move.dpe = move.damage / move.energy;
797
798        // Use moves that have higher DPE
799        if(((move.dpe - self.bestChargedMove.dpe > .03)&&(move.moveId != "SUPER_POWER"))||(move.dpe - self.bestChargedMove.dpe > .3)){
800            if((! self.bestChargedMove.selfBuffing)||((self.bestChargedMove.selfBuffing)&&(move.dpe - self.bestChargedMove.dpe > .3))){
801                self.bestChargedMove = self.activeChargedMoves[i];
802            }
803
804        }
```

Line 799 is the carve-out: a higher-DPE candidate displaces the
incumbent at a .03 DPE edge **unless it is SUPER_POWER, which needs an
edge > .3**.

The incumbent seed (line 791) is `activeChargedMoves[0]` AFTER the
priority shuffle. The shuffle clause that matters for Malamar
(Pokemon.js:767-771, the selfAttackDebuffing demotion):

```js
767    if((self.activeChargedMoves[1].energy - self.activeChargedMoves[0].energy <= 10)&&(self.activeChargedMoves[0].selfAttackDebuffing)&&(! self.activeChargedMoves[1].selfDebuffing)){
768        var move = self.activeChargedMoves[0];
769        self.activeChargedMoves.splice(0, 1);
770        self.activeChargedMoves.push(move);
771    }
```

## The patch

One hunk, battle.py lines 127-146. `_estimate_best_cm` now delegates
to `owner._ensure_dp_cache(opponent)` and returns
`(dp['order'][best_idx], dp['cms'][best_idx])`.

Rationale: the codebase ALREADY contains a faithful, verbatim port of
selectBestChargedMove — `best_idx` inside `_ensure_dp_cache`
(battle.py:2053-2079), including the SUPER_POWER carve-out at
2062-2063, the selfBuffing incumbent guard, the buffApplyChance
tiebreak, and both Obstruct clauses — and it runs on the energy-sorted
+ `_priority_shuffle`d (battle.py:787-868, port of Pokemon.js:711-787)
move list, so the incumbent seed is correct too. Duplicating the loop
in `_estimate_best_cm` would create a second copy to drift; delegating
makes the shield gate use the *same* bestCM the DP policy already
uses. `d_best_idx` (the first tuple element) is unpacked but unused at
the call site, so the signature is unchanged.

Semantics preserved: per-(opponent, stat-stages) recompute, which is
our documented intentional divergence from PvPoke's compute-once
caching (PvPoke bug #2, CLAUDE.md).

## Static trace for Malamar (why this matches the grid)

Malamar default GL moveset (rankings-1500): PSYWAVE +
[SUPER_POWER, FOUL_PLAY]; defaultIVs cp1500 = L23.5 4/15/15.
Both charged moves cost 40 energy; SUPER_POWER is selfAttackDebuffing
([-1,-1] self, chance 1), FOUL_PLAY has no buffs.

- Energy sort (stable) keeps [SUPER_POWER, FOUL_PLAY].
- Shuffle clause Pokemon.js:767-771 (our battle.py:852-856) fires:
  gap 0 <= 10, slot0 selfAttackDebuffing, slot1 not selfDebuffing →
  swap → slot 0 = FOUL_PLAY. (Matches grid_summary: "PvPoke's slot 0
  is shuffled FOUL PLAY".)
- Loop: incumbent FOUL_PLAY (dark, STAB). SUPER_POWER (fighting, no
  STAB) candidate: vs neutral-on-both targets (quagsire, seaking,
  feraligatr, kingdra, ninetales±) the DPE edge is ~85/78 of FP's DPE,
  i.e. ~0.1 absolute — above .03, below .3 → carve-out blocks →
  bestCM = FOUL_PLAY → not selfDefenseDebuffing → gate at battle.py:215
  not entered → always-shield, matching PvPoke.
- Vs fighting-weak targets (Lickilicky: normal, SE 1.6) the edge
  clears .3 → bestCM = SUPER_POWER in BOTH engines → gate entered as
  before → those cells already agreed and stay agreeing.

## Test plan

### Existing coverage (expected: no changes)

- `tests/test_battle.py` full suite (99/102 currently; xfails
  unrelated). None of the 102 PvPoke ground-truth fixtures involve
  Malamar or any other mon whose strict-max-DPE pick differs from the
  faithful selectBestChargedMove pick, so all scores/logs should be
  byte-identical. The Obstagoon-vs-Azumarill fixtures
  (`test_obstagoon_obstruct_vs_azumarill`) exercise the shuffle +
  Obstruct clauses through `pvpoke_dp` and pin the shield policy; they
  must stay green.
- `TestBuffTargetBoth::test_shield_policy_routes_both_move_through_would_shield`
  calls `pvpoke_simulate_shield` directly with synthetic make_bp mons;
  the new code path builds the defender's dp cache (synthetic moves
  carry all keys `_ensure_dp_cache` reads; misses fall to `.get`
  defaults). Expected still False (defender's FAKE_CHARGED is not
  selfDefenseDebuffing; branch unentered either way).

### New tests to add

1. **Unit test (no oracle needed, derivable statically):** build GL
   Malamar (PSYWAVE / SUPER_POWER+FOUL_PLAY, L23.5 4/15/15) via
   `_make_battle_pokemon` and assert
   `_estimate_best_cm(malamar, quagsire)[1]['moveId'] == 'FOUL_PLAY'`
   (carve-out holds: edge in (.03, .3]) and
   `_estimate_best_cm(malamar, lickilicky)[1]['moveId'] == 'SUPER_POWER'`
   (edge > .3 clears the carve-out). Opponents at defaultIVs cp1500:
   quagsire L28.5 4/15/10, lickilicky L23 4/15/8.
2. **Integration fixtures (scores already known from the grid's pv
   column; chargedLogs to be generated tomorrow via
   `scripts/pvpoke_trace.js` — never hand-typed):** pin the two
   biggest flipped cells, all builds = default moveset + defaultIVs
   cp1500 as in `scratch_oracle_grid/run_grid.py`:
   - Seaking (L26 4/13/14) vs Malamar, shields [1,2]:
     expect score 241 / 758 (ours currently 410/589).
   - Malamar vs Shadow Ninetales (L24.5 4/15/14), shields [2,1]:
     expect score 820 / 179 (ours currently 622/377).
   Also worth pinning one previously-agreeing carve-out-cleared cell
   as a regression guard, e.g. a lickilicky-vs-malamar cell (both
   engines pick SUPER_POWER there; must NOT change).

### Expected post-fix values for all 38 cells

From `userdata/oracle_grid_2026-06-12/grid_classified.json`
(`mechanism == "bestcm_estimate"`): the `pv` score/winner/log of each
cell is the post-fix expectation. The 9 score-severity cells:

| pair (p1 vs p2)             | shields | ours now | expected (pv) |
| --------------------------- | ------- | -------- | ------------- |
| quagsire vs malamar         | [2,1]   | 521/478  | 531/468       |
| seaking vs malamar          | [1,2]   | 410/589  | 241/758       |
| feraligatr vs malamar       | [2,1]   | 652/348  | 640/360       |
| ninetales_shadow vs malamar | [1,2]   | 377/622  | 179/820       |
| malamar vs quagsire         | [1,2]   | 478/521  | 468/531       |
| malamar vs seaking          | [2,1]   | 589/410  | 758/241       |
| malamar vs feraligatr       | [1,2]   | 348/652  | 360/640       |
| malamar vs ninetales_shadow | [2,1]   | 622/377  | 820/179       |
| malamar vs kingdra          | [1,2]   | 360/639  | 334/665       |

(+ kingdra vs malamar [2,1] 639/360 → 665/334; the other 28 cells are
log_shield / log_moves severity — same score, log should converge to
the pv log.)

## Blast radius

- **Grid:** 38 cells fixed, 0 expected broken (probe-verified family).
  All 38 are Malamar-as-shield-holding-defender cells; Malamar is the
  19-mon pool's only Superpower carrier.
- **Mechanism scope beyond the pool:** any matchup where the
  defender's strict-max-DPE charged move differs from the faithful
  selectBestChargedMove pick AND one of the two is
  selfDefenseDebuffing changes shield gating. Candidates: Superpower /
  V-create / Close Combat / Shadow Force-class carriers with a
  close-DPE second move (carve-out, selfAttackDebuffing demotion,
  selfBuffing guard), plus rare new ENTRIES into the branch where the
  .03 leniency or shuffle seed makes a selfDefenseDebuffing move best
  where strict-max didn't.
- **Dives:** Malamar is in the standard ~61-opponent GL pool, so every
  GL dive's vs-Malamar shield rows can move; `thresholds/malamar.toml`
  (untracked, in flight) is the most exposed subject. Non-Malamar
  matchups in the current pool are expected unchanged, but the engine
  is shared — treat all dives as stale.
- **Caches:** battle.py is in the sweep-cache engine hash. Applying
  this patch rotates the hash and invalidates ALL sweep/slayer caches
  → full re-dive cost. Do NOT apply while the overnight batch runs.
- **Side effect (benign, note for review):** `_ensure_dp_cache` runs
  `_priority_shuffle`, whose Zap-Cannon/Registeel clause
  (battle.py:833-843) writes buff keys into the owner's move dicts.
  The shield policy can now trigger that build for defenders even
  under non-DP charged policies. PvPoke does the same mutation at
  init; move dicts are per-BattlePokemon private copies (ownership
  invariant), so no cross-contamination.

## Verification commands (tomorrow, after the batch lands)

```
cd ~/coding/MGLPoGo/pogo-simulator
git apply --check userdata/fix_packets_2026-06-13/bestcm-superpower.patch
git apply userdata/fix_packets_2026-06-13/bestcm-superpower.patch
python -m pytest tests/test_battle.py -q
python scratch_oracle_grid/run_grid.py --top 20 --out /tmp/results_bestcm_fix.jsonl
python - <<'EOF'
import json
base = [json.loads(l) for l in open('userdata/oracle_grid_2026-06-12/grid_classified.json').read().splitlines() if False] or json.load(open('userdata/oracle_grid_2026-06-12/grid_classified.json'))
fixed = {(r['p1'], r['p2'], tuple(r['shields'])): r for r in map(json.loads, open('/tmp/results_bestcm_fix.jsonl'))}
bc = [c for c in base if c['mechanism'] == 'bestcm_estimate']
ok = bad = 0
for c in bc:
    r = fixed[(c['p1'], c['p2'], tuple(c['shields']))]
    good = r['sim']['score'] == c['pv']['score'] and r['sim']['winner'] == c['pv']['winner']
    ok += good; bad += not good
    if not good: print('STILL DIVERGENT:', c['p1'], c['p2'], c['shields'], r['sim']['score'], 'want', c['pv']['score'])
print(f'bestcm cells fixed: {ok}/38, still divergent: {bad}')
EOF
```

(Adjust the harvest snippet to run_grid's actual record schema if it
differs; the contract is: all 38 bestcm_estimate cells must now match
the stored pv values, and no cell outside the family may regress —
diff the full new results.jsonl against
userdata/oracle_grid_2026-06-12 results for a zero-new-divergence
check.)

Then generate the two new integration fixtures' chargedLogs with
`node scripts/pvpoke_trace.js --pvpoke-root ~/coding/MGLPoGo/pvpoke ...`
and add the tests from the plan above.

## Open questions

- `_cheapest_cm` (battle.py:149) is the OTHER approximation in the
  same gate (proxy for attacker's `activeChargedMoves[0]`). For
  equal-energy movesets (Malamar!) min-by-energy returns input-order
  slot 0, not the shuffled slot 0. Not part of this packet's 38-cell
  family, but the same delegate-to-dp-cache treatment
  (`dp['cms'][0]`) would kill it too — flagged, not patched (grid
  evidence ties it to the separate tinkaton/malamar "unknown" cluster
  3, bandaid-chain ordering).
- The grid's probe scripts (`probe_bestcm_family.py`,
  `probe2_grid_result.json`) referenced by grid_summary.md were not
  preserved in userdata/, so "+38/0" rests on the summary's claim plus
  the static trace above; the verification run tomorrow is the real
  gate.

## Adversarial review

Reviewed 2026-06-12 (overnight, read-only). Verdict: **READY** (minor
notes below, none blocking).

### Independently verified

1. **PvPoke reference read directly** (clone 9b7407782):
   Pokemon.js:791-822 — incumbent seed `activeChargedMoves[0]` after
   shuffle, line 799 SUPER_POWER carve-out, line 800 selfBuffing
   guard, line 807 buffApplyChance tiebreak, lines 813-821 both
   Obstruct clauses; Pokemon.js:767-771 selfAttackDebuffing demotion.
   Packet quotes are accurate. Our `_ensure_dp_cache` `best_idx` loop
   (battle.py:2058-2079) matches clause-for-clause, and
   `_priority_shuffle` (battle.py:787-868) ports all six shuffle
   clauses (splice+push == swap for the ≤2-move PvP case).
   Battle.js:1105 confirmed to gate on
   `defender.bestChargedMove.selfDefenseDebuffing` — the symbol this
   fix makes faithful.
2. **Single consumer confirmed**: `_estimate_best_cm` is called
   exactly once in the repo (battle.py:214, the shield gate); no
   scripts/tests import it. `d_best_idx` is indeed unused at the call
   site. Return contract preserved: `dp['order'][slot]` is the
   original `charged_moves` index and `dp['cms'][slot]` is the same
   dict object (sorted list holds references), so the
   identity-keyed `charged_move_damage` lookup at battle.py:234 still
   works. Empty-charged-moves guard retained, so the dp cache's
   empty-cms fallback branch is unreachable from this path.
3. **`git apply --check` passes** — note HEAD has advanced to
   f4a3b3e (4 commits past the packet's a73d855: matchup-web +
   tournament data; none touch battle.py). Re-verified clean at
   f4a3b3e.
4. **Grid evidence re-derived from grid_classified.json**: exactly 38
   `bestcm_estimate` cells, 38/38 involve Malamar, severity split
   24 log_shield / 10 score / 4 log_moves, and all 10 score-severity
   cells match the packet's table byte-for-byte.
5. **Static Malamar trace re-derived from the cached gamemaster**:
   SUPER_POWER 85 power / 40 energy / fighting / buffs [-1,-1] self
   chance 1 (selfAttackDebuffing AND selfDefenseDebuffing);
   FOUL_PLAY 65 power / 40 energy / dark (STAB 1.2 → 78-equivalent,
   matching the packet's "85/78"). Equal energy → demotion clause
   fires → FOUL_PLAY incumbent; ~9% DPE edge lands in (.03, .3] →
   carve-out blocks vs neutral targets; fighting 1.6x vs Lickilicky
   clears .3. Trace holds.
6. **Synthetic-test safety**: make_fast/make_charged dicts carry
   every hard-keyed field `_ensure_dmg_cache`/`_ensure_dp_cache`
   read ('power', 'type', 'energy'); everything else is `.get` with
   defaults. `TestBuffTargetBoth::test_shield_policy_routes_both_move_
   through_would_shield` builds the defender's dp cache without
   error and still returns False (FAKE_CHARGED not
   selfDefenseDebuffing). Single-charged-move defenders skip the
   shuffle (len>1 guard) → identical to old behavior.
7. **Cache implications**: battle.py is in
   `sweep_cache._ENGINE_FILES`, so the engine hash auto-rotates on
   apply; no manual CACHE_VERSION bump needed. Packet's
   "do NOT apply while the batch runs" warning is correct.
8. **Cross-packet stacking**: applies cleanly with
   incoming-gate.patch in BOTH orders (verified on a /tmp copy;
   stacked file parses). Hunks don't overlap (this patch ends at the
   `_cheapest_cm` context line ~151; incoming-gate starts at 163).
   Cell families are disjoint (0 shared cells) — but note all 12
   incoming_gate cells are tinkaton↔malamar pairs, so both fixes
   move Malamar shield behavior. Each probe ran solo; the
   fix-day runbook should run the full-grid zero-new-divergence diff
   once with BOTH battle.py patches applied, not just per-patch.
   (Checked: Malamar's bestCM vs Tinkaton is SUPER_POWER under both
   old and new selection — fighting 1.6x vs steel clears .3 — so this
   fix shouldn't perturb the incoming-gate family. The combined grid
   run is still the gate.)
9. **Zap-Cannon mutation side effect**: correctly characterized as
   benign — PvPoke mutates the same keys at init
   (Pokemon.js:734-744), and BattlePokemon's OWNERSHIP INVARIANT
   docstring guarantees private move dicts.

### Minor issues (fix during apply, none block READY)

- **DEVELOPER_NOTES staleness**: the 2026-04-15 resolved-divergence
  entry (DEVELOPER_NOTES.md:574-588) describes `_estimate_best_cm`
  as "best-actual-DPE ... pragmatic approximation". After this patch
  that text is half-stale (the bestCM half; `_cheapest_cm` half
  still true). Add a 2026-06-13 resolved entry and annotate the old
  one. Not in the packet's deliverables — add it.
- **Docstring nit**: new docstring cites "Pokemon.js:790-822"; the
  selection block starts at 791 (and the old docstring said 791).
  Cosmetic.
- **Third bestChargedMove proxy not flagged**: besides
  `_cheapest_cm`, battle.py:1618 (bandaid[910] defer-self-debuff)
  approximates `opponent.bestChargedMove` (ActionLogic.js:929-930)
  with max-actual-DAMAGE — a different proxy again. Out of this
  family's scope (DP-policy side, not shield gate), but it belongs
  on the same future-divergence list as `_cheapest_cm`.
- **Drafted-at-SHA drift**: packet header says verified at a73d855;
  HEAD is now f4a3b3e. Harmless (battle.py untouched since), but
  tomorrow's runner should re-run `git apply --check` first, per the
  packet's own step 1.

Verdict: **READY**.
