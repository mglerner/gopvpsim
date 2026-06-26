# Fix packet: incoming-gate (drop extra selfDefenseDebuffing routing in pvpoke_simulate_shield)

Drafted 2026-06-12 (read-only session; overnight dive batch running — NO repo
files were modified, NO sims were run). Evidence:
`userdata/oracle_grid_2026-06-12/incoming_gate_writeup.md` (decisive trace +
probe), `grid_summary.md`, `grid_classified.json`.

## The fix

`src/gopvpsim/battle.py` `pvpoke_simulate_shield`:

- battle.py:200 `use_heuristic_incoming = sb_subroute or self_def_debuffing`
  → `use_heuristic_incoming = sb_subroute`
- battle.py:187 drop the now-unused `self_def_debuffing` binding
- battle.py:204-206 trace tag loses the `selfDefDebuff` arm
- battle.py:166-170 docstring corrected — it claimed Battle.js overrides for
  "move.selfDefensiveDebuffing", which the reference does not contain
  (Battle.js:1090 routes only `move.buffs && move.selfBuffing`; the only
  selfDefenseDebuffing test, line 1105, is on the DEFENDER's own
  bestChargedMove). Port error introduced with the policy itself in
  `ead46c1` (2026-04-15).

Patch: `userdata/fix_packets_2026-06-13/incoming-gate.patch`
(verified `git apply --check` clean against HEAD `a73d855`).

Apply with, from the repo root:

    git apply userdata/fix_packets_2026-06-13/incoming-gate.patch

Note: the line-270 trace guard still references `use_heuristic_incoming`;
it is kept and unchanged.

## Test plan

### Existing coverage (expected: zero fixture changes)

All PvPoke-ground-truth fixtures move TOWARD the reference or are untouched:
the fix replaces a wouldShield consult with PvPoke's always-shield default,
so any currently-passing PvPoke-truth cell where a carrier nuke was shielded
stays shielded, and cells where it landed unshielded had no shields left.

- `tests/test_battle.py::test_mg_vs_florges_*` (~line 1800, Brave Bird
  incoming, uses `pvpoke_simulate_shield`) — must stay green.
- `tests/test_battle.py::test_mienfoo_vs_medicham_high_jump_kick` (line 835)
  — uses always_shield default policy, unaffected by construction.
- `TestBuffTargetBoth::test_shield_policy_routes_both_move_through_would_shield`
  (line 639) — selfBuffing subroute retained, unaffected.
- `test_reset_for_battle_reuse_matches_fresh[annihilape-mirror]` (Close
  Combat) — self-consistency test, policy-agnostic.
- `scripts/audit_oracle_harness.py` (153-cell audit) — exit 0; the
  MG-vs-Florges and Mienfoo blocks are the carrier-bearing matchups; no
  divergence cell should vanish or appear.

### New unit test (add to tests/test_battle.py near TestBuffTargetBoth)

Fails on unpatched HEAD (gate routes to wouldShield, which returns False:
post_hp 168 > cycle_damage 74, cm threat 32 < 200/1.4, selfAtkDebuff
override 32/200 < 0.55), passes after the patch. Values derived statically
from would_shield; confirm the pre-patch FAIL before applying.

    def test_incoming_self_def_debuff_nuke_is_always_shielded():
        # Battle.js:1090 routes ONLY `move.buffs && move.selfBuffing`
        # through wouldShield; a self-def-debuffing nuke (Superpower /
        # Brave Bird class) is not selfBuffing (GameMaster.js:873), so
        # PvPoke always-shields it. Pins the 2026-06-13 incoming-gate
        # port-error fix.
        move = make_charged(power=50, energy=40)
        move.update({'moveId': 'FAKE_SUPERPOWER',
                     'buffs': [-1, -1], 'buffTarget': 'self',
                     'buffApplyChance': '1', 'selfDebuffing': True,
                     'selfAttackDebuffing': True,
                     'selfDefenseDebuffing': True})
        # Move must be the attacker's own dict (charged_move_damage
        # resolves by identity); weak attacker + bulky defender keep
        # every wouldShield clause False.
        attacker = make_bp(atk=80.0, charged=[move])
        defender = make_bp(hp=200, shields=2)
        assert pvpoke_simulate_shield(attacker, defender, move) is True

### New integration fixture (generate from harness tomorrow)

Tinkaton vs Malamar GL, all 9 shield cells, fixture values from
`scripts/pvpoke_trace.js` (clone @ 9b7407782) — do NOT hand-type:

- Tinkaton FAIRY_WIND / GIGATON_HAMMER + BULLDOZE, 4/15/14, L25
  (gamemaster defaultIVs.cp1500 — verify `at_best_level` lands on 25,
  else pin via `max_level=25.0`)
- Malamar PSYWAVE / SUPER_POWER + FOUL_PLAY, 4/15/15, L23.5 (same check,
  pin `max_level=23.5` if needed)
- Statically known from the writeup: [1,0] (Tinkaton 1 shield, Malamar 0)
  → Tinkaton 861 / Malamar 138, chargedLog
  `['Tinkaton: Gigaton Hammer', 'Malamar: Superpower (shielded)']`.
  Unpatched HEAD gives 702/297 with the Superpower unshielded.
- Probe confirmed ALL tinkaton-vs-malamar and malamar-vs-tinkaton cells go
  exact with this patch alone (the bestcm_estimate family hits other
  species vs Malamar, not these), so the full 9-cell grid is safe to pin
  now. Also add the matchup to `scripts/audit_oracle_harness.py` MATCHUPS
  for transitive coverage.

## Expected blast radius

- **Behavior change scope:** only `pvpoke_simulate_shield` decisions where
  the incoming charged move is selfDefenseDebuffing, is NOT caught by the
  selfBuffing subroute, the defender holds shields, and wouldShield said
  False. Carriers (full gamemaster): BRAVE_BIRD, CLANGING_SCALES,
  CLOSE_COMBAT, DRAGON_ASCENT, HIGH_JUMP_KICK, MIND_BLOWN, SUPER_POWER,
  VOLT_TACKLE, V_CREATE, WILD_CHARGE. Direction: defenders now shield
  these nukes → carrier-side scores drop / defender margins improve.
- **Grid:** GL top-20 grid (3420 cells) 3086 → 3098 exact; the 12 fixed
  cells are tinkaton-vs-malamar [1,0] [1,1] [1,2] [2,0] [2,1] [2,2] and
  malamar-vs-tinkaton [0,1] [0,2] [1,1] [1,2] [2,1] [2,2]; 0 broken; max
  margin move 159 ([1,0]); no winner flips in this pool. HJK / Brave Bird
  users in other leagues/pools can plausibly flip winners (UL Moltres-G
  pools especially).
- **Dives:** editing battle.py rotates the sweep/slayer engine hash —
  ALL cached sweeps invalidate and the next dive recomputes from scratch.
  Apply this patch together with the other queued packets (bestcm-family,
  etc.) so the hash rotates ONCE. Tonight's overnight thresholds/*.toml
  batch becomes stale for any matchup vs a carrier with shields held
  (e.g. every GL dive with Malamar in the pool: malamar.toml itself,
  tinkaton margins vs Malamar by up to 159; UL dives vs Moltres-G).
  Per the retrofit policy, fix via targeted re-dive of affected species,
  not HTML surgery.
- **Tests:** zero expected fixture changes; xfails unchanged (the Brave
  Bird near-KO DP xfail is a DP plan divergence, not a shield decision).

## Verification commands (tomorrow, post-batch)

    cd ~/coding/MGLPoGo/gopvpsim
    python -m pytest tests/test_battle.py -q          # record baseline counts
    # add the new unit test, confirm it FAILS pre-patch
    python -m pytest tests/test_battle.py -q -k incoming_self_def_debuff
    git apply userdata/fix_packets_2026-06-13/incoming-gate.patch
    python -m pytest tests/test_battle.py -q          # baseline counts + 1 new pass
    python scripts/audit_oracle_harness.py            # exit 0
    # grid recheck against stored ground truth (results.jsonl):
    python /tmp/oracle_grid_expansion/probe_incoming_gate.py
    #   (copy preserved at userdata/fix_packets_2026-06-13/probe_incoming_gate.py
    #    with its prior output probe_grid_result.json; post-patch the BASELINE
    #    arm should report 3098/3420 exact, +12 / 0 broken vs 3086 baseline)
    # generate the Tinkaton/Malamar 9-cell fixture from the harness
    node scripts/pvpoke_trace.js ...   # per audit_oracle_harness invocation
    # perf regression gate (battle.py touched; >10% drop = stop):
    python scripts/profile_slayer.py --n-focal 60 --n-opp 20

## DEVELOPER_NOTES draft entry

Insert under `## Open divergences` (above the 2026-06-11 bait-wait entry),
matching the style of the two 2026-06-11 RESOLVED entries:

    ### RESOLVED 2026-06-13 — incoming selfDefenseDebuffing shield gate
    (port error: extra routing condition the reference lacks)

    `pvpoke_simulate_shield` routed the defender's shield decision
    through `wouldShield` whenever the INCOMING charged move was
    `selfDefenseDebuffing` (`use_heuristic_incoming = sb_subroute or
    self_def_debuffing`, introduced with the policy itself in ead46c1,
    2026-04-15). The reference has no such condition: Battle.js:1090
    overrides the always-shield default only for `move.buffs &&
    move.selfBuffing` (sub-filtered to self-atk-buff / opp-def-debuff),
    and its only selfDefenseDebuffing test (line 1105) is on the
    DEFENDER's own bestChargedMove. A self-def-debuffing nuke
    (Superpower, Brave Bird, Close Combat, HJK, Wild Charge, ...) is not
    selfBuffing (GameMaster.js:873), so PvPoke simply always-shields it;
    our gate let wouldShield decline the shield — but "can survive" is
    not "should tank": the defender burned real HP to save a shield it
    never got better value for. The docstring claimed reference parity
    the reference does not contain. Decisive trace: Tinkaton vs Malamar
    GL [1,0] — ours tanked the Superpower (702/297); PvPoke shields
    (861/138); with the condition removed our cell is 861/138 with a
    byte-identical chargedLog. GL top-20 grid (3420 cells): 3086 → 3098
    exact, +12 fixed (all tinkaton<->malamar cells — Malamar is that
    pool's only reachable carrier), 0 broken, max margin move 159, no
    winner flips in-pool (carrier users elsewhere can plausibly flip
    winners). Third instance of the 2026-06-11 pattern (after the OMT
    KO-override and the bait-wait hold): an extra condition the
    reference lacks, carrying a plausible comment, producing real margin
    errors. Full writeup:
    userdata/oracle_grid_2026-06-12/incoming_gate_writeup.md.

## Open questions

- Whether `at_best_level` reproduces the gamemaster defaultIVs levels
  (Tinkaton L25, Malamar L23.5) without an explicit `max_level` pin —
  check before generating the fixture.
- Sequencing with the bestcm-family packet: both touch the same shield
  policy region of battle.py; apply this one first (the bestcm patch
  context may need regenerating after this lands, or produce a combined
  patch tomorrow).

## Adversarial review

Reviewed 2026-06-12 (read-only session). Independent re-verification,
NOT trusting the drafter's quotes:

**Confirmed correct (checked against primary sources):**

- **Reference reading is accurate.** Read Battle.js:1077-1128 directly
  (clone @ 9b7407782). Line 1090 routes only `move.buffs &&
  move.selfBuffing` (sub-filtered 1091-1100 exactly as our
  `sb_subroute` replicates, including the buffTarget-both arm);
  the ONLY `selfDefenseDebuffing` test is line 1105 on
  `defender.bestChargedMove`. GameMaster.js:849-875 confirms a
  self-negative-buff nuke is never `selfBuffing` (line 873 requires
  buffTarget opponent, or positive self/both buffs). The incoming-move
  gate we carry has no counterpart in the reference. Core claim TRUE.
- **`git apply --check` passes at current HEAD f4a3b3e** (HEAD moved
  past the packet's a73d855 — 7 commits, none touching battle.py, so
  the context is intact).
- **No missed call sites.** `self_def_debuffing` has zero uses outside
  the patched lines (187/200/204); the line-270 trace guard reads only
  `use_heuristic_incoming` and stays consistent. All other
  `selfDefenseDebuffing` reads (battle.py:215, defender-bestCM branch)
  are intentionally untouched and match Battle.js:1105-1124.
  `pvpoke_simulate_shield` consumers (simulate() defaults at
  battle.py:2265-66, deep_dive.py, deep_dive_slayer.py, tests) take it
  as an opaque policy callable — no signature change, nothing to
  update.
- **Cache story is right.** sweep_cache.py `_ENGINE_FILES` includes
  battle.py, so the engine hash rotates automatically; slayer_cache.py
  folds in the same `engine_hash()`. No CACHE_VERSION bump required.
- **Probe evidence corroborates.** probe_grid_result.json: total 3420,
  baseline 3086, patched 3098, fixed list = the 12 named
  tinkaton/malamar cells, [1,0] old 702/297 → pv 861/138 with the
  "(shielded)" log, exactly as claimed.
- **New unit test static values verified exactly:** charged dmg
  floor(0.5*1.3*50*0.8*1.2)+1 = 32; post_hp 168; cycle with
  make_fast() defaults (power 5, gain 5) and the temporary -1 def
  stage = (9*4+1)*2 = 74; all four would_shield clauses False
  (32 < 142.9, 32 < 126, 0.16 < 0.55). Pre-patch FAIL / post-patch
  PASS as claimed. The synthetic defender's FAKE_CHARGED is not
  selfDefenseDebuffing, so the line-215 branch can't contaminate the
  assertion.
- **Cross-packet conflicts:** bestcm-superpower.patch (battle.py
  @ _estimate_best_cm, lines 125-149) and this patch apply cleanly in
  BOTH orders (verified in a /tmp sandbox), so the "apply this one
  first / regenerate context" worry in Open questions is unfounded —
  any order works. renderer-D1-D4.patch touches only
  scripts/deep_dive.py + deep_dive_rendering.py — no overlap.
  shadow-cmp and renderer-D2-D5 packets are not yet in the directory,
  so conflicts with those could not be checked (re-check when drafted
  if shadow-cmp touches battle.py).

**Issues found (packet prose, not the diff — the diff itself is
correct):**

1. **Wrong claim about the Mienfoo test.** The packet says
   `test_mienfoo_vs_medicham_high_jump_kick` "uses always_shield
   default policy, unaffected by construction." False: `simulate()`'s
   default shield policy IS `pvpoke_simulate_shield`
   (battle.py:2265-66), and HJK ([0,-4]) is a carrier, so that test
   exercises the changed gate in every Medicham-holds-shields cell.
   It still stays green — but for a different reason: the patch only
   flips decisions False→True toward PvPoke's always-shield, and every
   passing chargedLog fixture already shows HJK "(shielded)" whenever
   Medicham held one (so wouldShield was returning True there). Same
   directional argument protects every PvPoke-truth fixture in the
   suite. Conclusion stands; reasoning in the packet is wrong.
2. **Test name doesn't exist.** `test_mg_vs_florges_*` is actually
   `test_moltres_galarian_vs_florges_shield_gate` (test_battle.py:1828).
   A `-k mg_vs_florges` filter would match nothing.
3. **DRAGON_ASCENT is not a carrier in our sim.** moves.py:183-186
   replicates GameMaster.js:859's explicit DRAGON_ASCENT exclusion
   from selfDebuffing (hence selfDefenseDebuffing False), so the gate
   never routed it pre-patch and the patch changes nothing for it.
   Blast-radius carrier list (and the writeup's) overstates by one
   move. The other nine carriers check out.
4. **Lapras [1,2] strict xfail deserves an explicit post-patch look.**
   `_MG_NEARKO_PLAN_FLIP` (strict=True) is the one xfail where the
   defender (Lapras, 1 shield) faces an incoming carrier (Brave Bird)
   with shields held, so the gate removal CAN touch that fight. Almost
   certainly no change (BB's damage vs Lapras trips wouldShield's
   hp/1.4 clause, so it was already shielded pre-patch), but the
   packet's "xfails unchanged" is asserted, not verified. The full
   pytest run in the verification plan WILL scream on an XPASS
   (strict), so coverage exists — just don't be surprised there;
   if it XPASSes, inspect the chargedLog per the score-coincidence
   policy before celebrating.

**Verdict: READY.** The diff is a faithful one-condition removal that
matches the reference exactly; evidence is reproducible; test plan and
verification commands are sound (full pytest covers the one residual
risk in issue 4). Issues 1-3 are documentation corrections recorded
above — no patch regeneration needed.
