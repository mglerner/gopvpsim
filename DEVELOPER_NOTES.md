# Developer Notes

## PvPoke re-vetting log

**2026-06-06 — re-vetted against pvpoke `bc532fbda`** (Michael's
2026-06-05 `git pull`; range `8ed523811..bc532fbda` covers the
04-26 / 06-02 / 06-05 pulls). Findings:

- **Battle engine unchanged.** `Battle.js`, `ActionLogic.js`, and
  `DamageCalculator.js` are byte-identical to the 2026-04-16 vetting.
  The only `src/js` changes were non-sim: a `dex` multi-range filter
  in `GameMaster.js` (before line 873, so the `selfBuffing` citation
  is unaffected), a whitespace + `&& self.fastMove` null-guard in
  `Pokemon.js` `replaceMove`, a `startStatBuffs` comparison fix in
  `TeamRanker.js`, and pure-UI files. **Every divergence cited in
  this doc and CLAUDE.md still resolves to the correct line and is
  still valid.**
- **Move data rebalanced** (real June-2026 game patch PvPoke tracked,
  in `src/data/gamemaster/moves.json`): Charm 13->12, Dragon Ascent
  150/70->110/45, Drill Run 80/45->70/40, Earthquake 110->120, Earth
  Power ->50e, Energy Ball 90/55->80/45, Flash Cannon ->65e, Hurricane
  ->60e, Silver Wind 60->75, Wrap 60->70, Gust energyGain 12->14,
  Plasma Fists added. `buffApplyChance` untouched (buff flags
  unaffected). This is data, not logic — it shifts both sims
  identically, so it is **not a divergence**. Our sim already runs on
  it (`data.py` fetches gamemaster from GitHub master, 24h cache).
- **Fixture fallout:** `test_shadow_swampert_vs_registeel` (uses
  Earthquake + Flash Cannon) went stale on 4 of 9 cells. Re-vetted all
  9 via `scripts/pvpoke_trace.js`; our engine matches current PvPoke
  exactly on score, winner, and chargedLog. Fixtures refreshed
  (0v0 541->720, 0v1 507->686, 1v2 436->232; 0v2 score held at 216 but
  log changed). No other battle test affected.

**2026-06-06 — full oracle harness audit.** Ran the new
`scripts/audit_oracle_harness.py`, which drives **every** hand-typed
PvPoke-oracle matchup in `tests/test_battle.py` (12 matchups × 9 shield
combos = 108 cells) through both our sim and `scripts/pvpoke_trace.js`
and compares score / winner / chargedLog directly. (We compare sim-vs-
harness rather than re-typing PvPoke's score matrices, since the passing
test suite already proves sim == fixture; this avoids re-introducing the
typo class we're auditing for.) Results:

- **98 of 108 cells: exact match** (score + winner + chargedLog) against
  current PvPoke. Confirms no hand-entry typo ever crept into the
  Medicham/Azu, Azu/Forr (full + RT), Beedrill/Med, Corv/Med,
  Mienfoo/Med, Corv/Azu, Shadow Swampert/Registeel, Corviknight-mirror,
  Aegislash, and Mimikyu fixtures.
- **6 cells: documented Aegislash bug #3 divergence, all still present**
  (the `_AEGI_XFAIL_GB_*` cells: 0v1, 0v2, 1v1, 1v2, 2v1, 2v2). Includes
  the 1v2/2v2 score+winner flip (ours 510/w0 vs PvPoke 376/w1) — intact.
- **4 cells: NEW PvPoke bug found — Morpeko form-toggle**
  (`morpeko_vs_azumarill_form_change` 1v1, 1v2, 2v1, 2v2). Score and
  winner match PvPoke exactly; the chargedLog form prefix on a Morpeko
  throw differs (we tag "Morpeko (Full Belly)" where PvPoke tags
  "Morpeko (Hangry)"). Root-caused and resolved 2026-06-06: **our
  two-way toggle is correct; PvPoke's is a bug** (now documented as
  PvPoke bug #8 below). Michael verified in-game 2026-06-06 that Morpeko
  enters every battle in Full Belly (start AND switch-in) and toggles
  Full Belly <-> Hangry after each charged move. The divergence is
  score-neutral across this oracle (every label-differing throw is
  form-independent Psychic Fangs or a shielded Aura Wheel), which is why
  the score-only Morpeko test never caught it. Now pinned by a chargedLog
  regression assertion on the Morpeko test (asserts OUR correct log) and
  marked as a known-divergence cell in `scripts/audit_oracle_harness.py`.
  Keeping our behavior per the CLAUDE.md divergence policy.

## Current status (updated 2026-06-12)

<!-- sync:test_count -->955<!-- /sync --> tests collected. The original PvPoke battle-correctness
core was 102 + 9 shadow + 9 Corviknight mirror = 120; the remainder are
unit and integration tests added since. The oracle audit
(`scripts/audit_oracle_harness.py`, GL + UL) verifies the simulator
against PvPoke's live engine for <!-- sync:pvpoke_matchups_verified -->22<!-- /sync --> matchups
(<!-- sync:pvpoke_cells_verified -->198<!-- /sync --> cells: 161 exact on score+winner+chargedLog, 37 cells =
documented divergences, each traced to a mechanism: the near-KO
plan-choice cluster, PvPoke bug #3 Gyro-Ball-over-Shadow-Ball — both
sides of it, and bug #8 Hangry stickiness; per-cell reasons live on
the MATCHUPS entries in the audit script). Historical
note: the 3 original 2026-04-06 failures were all Mienfoo vs Medicham
(`bestChargedMove` selection, resolved then).

### Verified correct
- **Type effectiveness**: All <!-- sync:type_chart_cells_verified -->324<!-- /sync --> matchups match PvPoke exactly
- **Damage formula**: Verified against manual calculation
- **Buff/debuff mechanics**: Guaranteed buff (Beedrill 9/9), chance buff
  (Corviknight 9/9), self-debuff meter threshold
- **DP queue insertion**: Three PvPoke strategies ported (farm-down <=,
  ready <=+dedup, not-ready <)
- **selfBuffing/selfDebuffing flags**: Match PvPoke's chance thresholds
  (==1 for selfBuffing, >=0.5 for selfDebuffing)
- **Shield policy**: pvpoke_simulate_shield uses precomputed flags
- **Shadow Pokemon**: ×1.2 atk / ×(5/6) def multipliers match PvPoke's
  SHADOW_ATK=1.2, SHADOW_DEF=0.83333331. Shadow Swampert vs Registeel 9/9.
- **Both-side buffs**: Corviknight mirror (Air Cutter only) 9/9. Both mons'
  buffApplyMeter fires independently; unbuffed Air Cutter does 18, buffed does 23.

### Previously failing matchups — all fixed

Mienfoo vs Medicham (9/9) resolved by the `would_shield` buff-reset
ordering and CMP cancellation fixes. Full root-cause writeup in
`CHANGELOG.md` under `2026-04-04 to 2026-04-06`.

## Performance baseline (regression gate)

**Rule: after any change to `battle.py`, `_dp_jit.py`, or `moves.py`,
re-run the benchmark below and compare against the current baseline.
A drop of more than ~10% means stop and investigate before
committing.** This rule exists because the 2026-04-15 correctness arc
silently halved engine throughput (the stage-aware DP fix `141eee1`
rebuilt per-atk-stage damage tables on every `pvpoke_dp` call) and
nobody noticed for eight weeks — the 2026-04-07 "26k sims/s" figure
kept being quoted while real dives ran at half that.

Canonical benchmark (single-process, ~10s, Annihilape mirror):

```
python scripts/profile_slayer.py --n-focal 60 --n-opp 20
```

| Date       | Code                                  | sims/s    | Note                                               |
| ---------- | ------------------------------------- | --------- | -------------------------------------------------- |
| 2026-04-07 | `a57c39f` (recorded then)             | 3,055     | Pre-June gamemaster; not directly comparable       |
| 2026-06-10 | `a57c39f` (re-run, current data)      | 2,255     | Controlled baseline for the regression measurement |
| 2026-06-10 | `d419306` (pre-fix HEAD)              | 1,121     | The 2.0x regression, root-caused to `141eee1`      |
| 2026-06-10 | `154536a` (DP setup cache + log gate) | 2,278     | Post-regression-fix baseline                       |
| 2026-06-10 | `d4d8ed2` (arc S5: TTL JIT, stage-row | **3,160** | **Current baseline** (warm JIT cache; first run    |
|            | reachability, DP-cache precompute)    |           | after an engine edit pays ~1-2s compile)           |

Gamemaster data changes shift battle lengths and therefore sims/s
(that's the 3,055 → 2,255 gap on identical code), so when the
rankings/gamemaster cache refreshes, expect drift — re-baseline by
re-running on a commit with a known-good number rather than comparing
across data vintages. cProfile runs (`--profile`) are ~2-5x slower
than wall-time runs; only compare like with like.

**Caveat when benchmarking dives (not the canonical benchmark above):**
since arc S4, `deep_dive.py` serves IV sweeps from the per-opponent-
column disk cache by default, so a repeated dive command reports 0
sims. Pass `--no-sweep-cache` for timing runs.

## Sweep disk cache + replay-from-saved-state (arc S4)

Two iteration-speed layers shipped 2026-06-10; full design rationale
in CHANGELOG ("Sweep disk cache + replay-from-saved-state").

**Sweep cache** (`scripts/sweep_cache.py`): `iv_sweep` persists each
opponent's score column to `~/.cache/gopvpsim/sweep/` and skips
cache-hit opponents entirely. Keys include the moveset, scenarios,
bait mode, an engine-source hash (battle.py, _dp_jit.py, moves.py,
formchange.py, pokemon.py — any edit invalidates automatically), and
a gamemaster content hash; opponent-side keys carry resolved IVs +
moveset, so rankings drift produces clean misses rather than stale
hits. Columns are raw float64 in canonical iv_meta order — hits are
bit-identical to fresh sims (pinned by tests/test_sweep_cache.py).
Operational notes:

- `--no-sweep-cache` forces fresh sims (timing runs, debugging).
- Hit log line per sweep: `sweep cache: N/M opponent columns hit`
  (nothing printed on an all-miss sweep).
- Stale key-dirs accumulate as engine/gamemaster evolve; the cache
  has no auto-purge. `rm -r ~/.cache/gopvpsim/sweep` is always safe.
- Library callers (tests, verify scripts) default to OFF; only the
  CLI turns it on.

**Replay** (`scripts/replay_analysis.py`): every interactive dive
dumps its render-input state to `userdata/replay/*.replay.pkl.gz`
right after sims complete (skip with `--no-replay-dump`). To iterate
on renderer/analysis-section code without re-simming:

```
python scripts/replay_analysis.py userdata/replay/<blob> [--html OUT]
```

This re-runs `deep_dive.render_dive_html` — the same code path the
live dive uses, split-moveset mode included — and produces HTML
byte-identical to the original dive's. Prefer this over the old
inline-HTML-editing workaround when the change is in Python renderer
code (inline edits remain fine for pure JS/CSS tweaks in built
files). Blobs are ~1MB for smokes, ~10MB for website-scale dives,
and accumulate in userdata/replay/ (gitignored, never published);
delete old ones freely.

## PvPoke bugs found

<!-- sync:pvpoke_bugs_documented -->5<!-- /sync --> bugs documented below (sections 1, 2, 3, 7, 8 —
numbering reflects discovery order; section 4 was retracted 2026-04-15
and is excluded from the count). **Paste-ready GitHub-issue drafts for
filing upstream live in `docs/pvpoke_bug_reports.md`** (7 reports:
these five plus the initializeMove DPE-overwrite and the
Blade→Shield CPM-table overflow, both 2026-06-11; filing is
Michael's action, no urgency).

### 1. BattleState .hp/.oppHealth naming inconsistency

**File**: `ActionLogic.js:1187` (class definition) vs lines 479, 600, 697

PvPoke's `BattleState` stores `.oppHealth` and `.oppShields`, but the
dominance checks reference `.hp` and `.shields` (undefined in JS →
always false → dead code). The dedup check at line 545 correctly uses
`.oppHealth`.

We added an `intended_pruning` flag to `pvpoke_dp` that toggles between
PvPoke's actual behavior (dead-code pruning, `False`) and the apparently
intended behavior (functional pruning, `True`).

### 2. bestChargedMove not recomputed on opponent form change

**File**: `Pokemon.js:791-822` (selectBestChargedMove) and
`Pokemon.js:2344` (changeForm calls resetMoves on self only)

PvPoke computes `bestChargedMove` at init time using actual damage
against the opponent's current stats, then caches it on the Pokemon
object. When the **opponent** changes form (e.g., Aegislash
Shield->Blade, dramatically changing defense), the attacker's
`bestChargedMove` is NOT recomputed. Only the form-changing Pokemon's
own `resetMoves()` is called.

Concrete example: Azu's IB (15 dmg, 55 energy, DPE 0.273) vs PR
(18 dmg, 60 energy, DPE 0.300) against Aegislash Shield form. DPE
diff is 0.027 < 0.03 threshold, so PvPoke picks IB (cheaper, locked
at init). Against Blade form (low def), DPE diff grows to 0.062 >
0.03, and PR becomes clearly better - but PvPoke still uses IB. Our
code recomputes per turn, which we believe is more correct.

### 3. Aegislash selects Gyro Ball over Shadow Ball

**File**: `ActionLogic.js` (near-KO DP or bestChargedMove selection)

PvPoke selects Gyro Ball (Steel, 80 power, 50 energy) over Shadow
Ball (Ghost, 100 power, 50 energy) for Aegislash vs Azumarill in
multi-shield scenarios. Both moves cost identical energy, have the
same type effectiveness (1.0x) and STAB (1.2x) against Water/Fairy.
SB does strictly more damage (49 vs 39 in Shield form, 101 vs 81 in
Blade form). Confirmed: Aegislash with SB-only scores 429 vs 376
with SB+GB in the 1v2 scenario, meaning GB availability actively
hurts Aegislash's score. Root cause unclear - may be in the near-KO
DP's plan selection or a bandaid condition.

### 7. needsBoost / non-guaranteed-buff plan selection is dead code

**File**: `ActionLogic.js:515-539, 793-810, 868` (decideAction DP)

PvPoke's code looks like it accumulates a `stateList` of KO-bearing
terminal DP states tagged with `.chance` (product of `buffApplyChance`
values along the path), then picks the highest-chance plan when
`opponent.turnsToKO != -1 && poke.turnsToKO > opponent.turnsToKO`
(logged as "changes its plan because it needs the BOOST to win or
debuff"). Line 868 gates a downstream plan-reorder on the same flag.

Two independent faults render the whole system inert in simulate mode:

1. **Line 539: `changeTTKChance = 0;`** (unconditional, with comment
   "DISABLE THE NON-GUARANTEED BUFF EVALUATION SYSTEM"). This fires
   at the top of every move-evaluation iteration, after lines 519-536
   would have set `changeTTKChance` to the move's `buffApplyChance`.
   Every chance-<1 DPQueue push (lines 613, 631, 661, 680, 710, 728,
   756, 774) is gated on `if (changeTTKChance != 0)` → always false.
   So `stateList` only ever accumulates chance-1 plans.
2. **`needsBoost` is declared `false` on line 793 and is never
   assigned `true` anywhere in the file** (grep confirms). The
   "else if (... poke.turnsToKO > opponent.turnsToKO)" branch picks
   `bestPlan` but doesn't flip the flag. So the `if (!needsBoost)`
   gate at line 868 always fires — the plan-reorder branch is never
   actually gated.

**Empirical confirmation 2026-04-15**: ran `scripts/pvpoke_trace.js`
across all 9 shield scenarios for the four GL species carrying
`0 < buffApplyChance < 1` moves in their default movesets (Tinkaton+
Bulldoze, Corviknight+AirCutter, Clefable+Moonblast, Drapion+Crunch)
vs common opponents. The "needs the BOOST" decision log message never
fired — 0 hits across 36 sims. Matches the static analysis.

**Our stance**: we intentionally do NOT port stateList accumulation
or the needsBoost trigger. Doing so would *diverge* from PvPoke's
actual observable behavior in the direction of a feature PvPoke has
explicitly disabled. Our first-KO-terminal pick matches PvPoke's
effective single-plan behavior.

If PvPoke ever removes line 539 or fixes the `needsBoost = true`
assignment, revisit — the enumeration of affected meta species above
still applies.

### 8. Morpeko form change is one-way instead of a true toggle

**File**: `Battle.js:1536-1537` (post-attack `charged_move` form trigger)
and `src/data/gamemaster/pokemon.json` (`morpeko_hangry` has
`formChange: null`).

Morpeko's gamemaster `formChange` is `type: "toggle", trigger:
"charged_move", moveId: "ANY"`, and the real game toggles Full Belly
<-> Hangry after **every** charged move (Aura Wheel swaps
Electric/Dark accordingly). Michael verified in-game 2026-06-06: Morpeko
enters every battle in Full Belly (battle start AND switch-in), fires a
charged move in its current form, then changes form.

PvPoke implements this one-way. The line 1536 trigger is gated on
`attacker.activeFormId != attacker.formChange.alternativeFormId`. The
first charged move changes Full Belly -> Hangry (guard passes); but once
in Hangry, `activeFormId == alternativeFormId` ("morpeko_hangry") so the
guard fails, AND the `morpeko_hangry` entry carries no `formChange` of
its own — so PvPoke never toggles back. Morpeko sticks in Hangry for the
rest of the battle (it does correctly reset to Full Belly on switch via
`resetOnSwitch: true`). The guard was evidently written for genuinely
one-way changers (Aegislash/Mimikyu) and wrongly catches Morpeko's
toggle, contradicting the gamemaster's own `type: "toggle"`.

**Our code**: `formchange.py:240-241` makes the Hangry form inherit the
`charged_move` trigger so it toggles back, matching the real game. So
our chargedLog disagrees with PvPoke's on any battle where Morpeko
throws a second-or-later charged move: we correctly fire the
post-second-toggle move from Full Belly (Aura Wheel Electric), PvPoke
fires it from a stuck Hangry (Aura Wheel Dark).

**Impact**: in `morpeko_vs_azumarill_form_change` the divergence is
score-neutral (every label-differing throw is form-independent Psychic
Fangs or a shielded Aura Wheel), so the score-only oracle never caught
it — the 2026-06-06 harness audit did. It IS score-relevant in any
matchup where Morpeko throws an unshielded Aura Wheel as its 2nd+ charged
move and Electric-vs-Dark effectiveness differs against the opponent
(e.g. Aura Wheel Electric is super-effective on Water, Dark is not).
There PvPoke's published Morpeko numbers are wrong; ours are right.

**Our stance**: keep our two-way toggle. PvPoke isn't demonstrably
better here — it's wrong about the mechanic — and our deviation matches
the verified game behavior. Pinned by a chargedLog regression assertion
on `test_morpeko_vs_azumarill_form_change` and marked as a known
divergence in `scripts/audit_oracle_harness.py`.

### 4. Mimikyu SS timing — RETRACTED 2026-04-15

This was a phantom bug. We thought our Mimi threw Shadow Sneak one
turn earlier than PvPoke (363 vs 350), but harness localization
revealed the divergence was in our timeline OUTPUT, not behavior.
Our `simulate()` disguise-bust branch logged only "disguise busted"
without emitting the standard `X uses Y → Z dmg` line for the
throw that triggered it. So `_extract_battle_log` saw N-1 entries
where PvPoke's harness saw N — making it look like PvPoke threw an
"extra" opening Ice Beam. Once the missing log line was added, our
chargedLog matches PvPoke's exactly across all 9 Mimi vs Azu shield
combos. Mimi's actual SS timing was correct all along; the
"363 vs 350" score difference came from earlier raw_dpe issues
(also fixed 2026-04-15), not from SS timing. See the 2026-04-15
"Localization meta-finding" entry below for the broader lesson.

## Open divergences

### RESOLVED 2026-06-13 — shadow ×1.2 wrongly folded into CMP attack

CMP (charged-move priority — who throws first on a simultaneous charged
turn, plus the CMP turn-bonus/penalty in the shield + DP heuristics) was
decided on `BattlePokemon.atk`, which folds the shadow ×1.2 attack bonus.
The shadow bonus boosts *damage* but NOT priority: the live game compares
the unboosted attack stat (Michael, domain expert, 2026-06-13), and
PvPoke compares its shadow-free `stats.atk` in every CMP-flavored check.
Fix: `BattlePokemon` gained a `shadow` flag and a `cmp_atk` property
(`atk / 1.2` for shadow, else `atk`); all 9 CMP comparison/ordering sites
in battle.py switched from `.atk` to `.cmp_atk` (250, 381, 406, 468, 686,
1047, the `use_priority` test, and both the fast-landing and charged
priority sorts). `shadow` is threaded through `from_pokemon` (→ CLI,
matchup web, tests) and the deep_dive / slayer dive workers; harness_grid
is non-shadow by design (filters `_shadow`) and needs none.

This resolves the 204-cell `shadow_cmp` family from the 2026-06-12 GL
top-20 grid (every one of the grid's 30 winner flips). Spot-checked 10/10
distinct shadow pairs exact vs `pvpoke_trace.js` post-fix, including
base-vs-shadow mirrors that correctly resolve to 500/500 mutual-KO draws
(`use_priority` becomes False once the bonus is stripped and equal-IV
mirrors tie on `cmp_atk` — the simultaneous-charged draw path the live
game produces, engaged for free by this fix, not a separate port).
Pinned by `test_shadow_quagsire_vs_feraligatr_cmp` (9 PvPoke-verified
cells incl. the [0,0] winner flip: pre-fix Quagsire wrongly won 555/444,
now Feraligatr 464/536) and `test_cmp_atk_strips_shadow_bonus` (unit).
Caches auto-invalidate (engine_hash covers battle.py/pokemon.py for both
sweep and slayer caches). Benchmark 3,224 sims/s (baseline 3,160).

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
docs/validations/2026-06-12_oracle_grid/incoming_gate_writeup.md.

### RESOLVED 2026-06-11 (same evening) — bait-wait hold: one extra
condition, not an unported branch

The decideLog trace first read this as PvPoke's bait-WAIT hold
(~ActionLogic.js:839-853) being unported. Reading our port against
the reference showed the truth: the hold WAS ported, but with an
extra `not cm_self_debuf[1]` gate the reference does not have — so
it never fired when the pricier active move was
Superpower/Brave-Bird-class (precisely the observed cells). Removed
the extra condition; our TTL fire_now path already supplies PvPoke's
death-pressure escape from the hold. Results:

- Snorlax vs Obstagoon GL: 9/9 cells exact (was 8/9).
- MG vs Florges UL [1,2]: chargedLog now byte-identical to PvPoke
  (fixture updated to ground truth; audit pin removed).
- The three jellicent (2,x) LOG-ONLY cells pinned earlier the same
  day also vanished — same mechanism family. Audit documented
  divergences: 21 → 17, all now the single genuine near-KO
  plan-choice cluster.

Second falsified "intentional deviation" in one day (after the OMT
KO-override). Both carried plausible comments; both were extra
conditions the reference lacks; both produced real margin errors.
Lesson reinforced: deviations need traces and probes, not reasoning.

### RESOLVED 2026-06-11 — Snorlax/Obstagoon margin cluster (OMT
self-debuffing KO-override deviation falsified)

The cluster (ours −26..−29 at 0v0/1v0/2v0/2v1, logs identical) was
localized via decideLog tracing to OUR intentional deviation in the
OMT "can KO with a charged move" override: we excluded self-debuffing
moves, reasoned to be score-neutral ("the debuff fires after the KO").
False: while OMT keeps delaying the lethal self-debuffing throw, the
opponent's fast moves keep landing — Snorlax ate exactly one extra
Counter per battle waiting to throw a Superpower whose debuff could
not matter. Removed the exclusion (battle.py `_optimize_move_timing`,
now matches ActionLogic.js:317-329 exactly); 8/9 Snorlax cells now
match PvPoke exactly, all other gates unchanged (suite, 153-cell
audit, benchmark). Lesson for the divergence policy: "score-neutral"
claims about decision-timing deviations need a trace, not reasoning —
the deviation cost real HP in every shields-down endgame where the
closer is self-debuffing (Superpower/HJK/Draco users vs walls).

## Known divergences from PvPoke implementation

Places where our code intentionally does NOT match PvPoke's
implementation. Each is a potential source of score mismatches if we
hit an edge case. Fix these before assuming a score difference is a
PvPoke bug.

### Battle timeout: flat 500-turn guard vs PvPoke's 240s display clock
(documented 2026-06-11, review finding E14)

PvPoke ends battles when `time > 240000` ms (Battle.js:653), where
`time` mixes 500 ms turns with 10,000 ms charged-move "minigame"
adjustments (Battle.js:523-530: a charged round REPLACES the turn's
500 ms with minigame time, and a shielded round discounts one). Its
effective turn cap therefore shrinks with every charged throw. Ours is
a flat `MAX_TURNS = 500` guard. Intentionally NOT matching: both are
infinite-loop guards, and neither is reachable in practice — the
bulkiest realistic GL wall fight (Carbink mirror, 2v2, traced
2026-06-11) ends at 85 turns with 8 charged throws (~118 s on PvPoke's
clock). Porting the minigame bookkeeping would complicate the hot loop
for zero observable effect. Revisit only if a real matchup is ever
found that times out in either sim.

**Team-sim caveat (Michael, 2026-06-11):** the 240 s is the real
game's MATCH timer for a full 3v3 — PvPoke's per-1v1 cap inherits it,
and the minigame-time bookkeeping exists because charged-move
animations consume the shared match clock. In a 1v1 sim no single
pairing approaches it; in a future team sim the three pairings SPLIT
one 240 s budget, so timing out becomes a real outcome (games are won
on the clock) and this bookkeeping becomes load-bearing, not a guard.
If/when the TODO "Team/multi-mon simulation" item lands, port
PvPoke's clock semantics (500 ms turns; charged rounds REPLACE the
turn's 500 ms with 10,000 ms minigame time; shielded rounds discount
one minigame) as match-level state.

### Near-KO DP plan choice: nuke-with-self-debuff vs serial-Fly (intentional)

**Mechanism (localized 2026-04-15 followup session):** The divergence
is NOT a difference in the near-KO DP's plan output — both sims' DPs
return `[BRAVE_BIRD]` as `finalState`. The divergence is in a
**post-DP bandaid**: PvPoke's ActionLogic.js line 885-887 (our port:
battle.py:1541-1558, bandaid[866]) swaps `finalState.moves[0]` from
the self-debuffing nuke to `activeChargedMoves[0]` (Fly) whenever:

    opp.shields == 0
    AND finalState.moves[0].selfDebuffing
    AND finalState.moves[0].energy > 50
    AND poke.hp / poke.stats.hp > 0.5
    AND finalState.moves[0].damage / opp.hp < 0.8

*(Mechanism paragraph corrected 2026-06-11, review finding E11.)*
PvPoke's `move.damage` is essentially NEVER undefined: `initializeMove`
(Pokemon.js:830-839) sets it for every move at battle init (both the
with-opponent and without-opponent branches assign), `wouldShield`
refreshes it on every evaluation (ActionLogic.js:1121), and the OMT
side effect (line 320, fires per-move whenever `opponent.shields == 0`)
keeps it freshest. So PvPoke's bandaid[885] always evaluates its
`damage/opp.hp < 0.8` ratio — possibly with a stale value. Our port
caches damage at battle.py:652 but subgates the assignment on
`attacker.energy >= cm['energy']` — so in the Moltres-G cluster
(energy < BB's 55 at the T20 DP-entry state) our `_cached_damage`
stays `None`, bandaid[866] skips its ratio test entirely, the DP plan
is left alone, and bandaid[918] stacks BB until energy reaches 100 →
single-BB nuke instead of Fly-chain. NOTE the divergence surface is
therefore broader than the MG cluster: our bandaid[866] skips wherever
`_cached_damage` is None, while PvPoke's always fires — the empirical
cluster measurements and the keep-our-behavior decision below stand
(they were measured from actual traces), but an earlier version of
this paragraph wrongly claimed the field is "undefined in JS" unless
OMT fired.

**Why we don't fix it:** faithfully mirroring PvPoke's OMT side
effect (so bandaid[866] fires when PvPoke's bandaid[885] would) swaps
BB → Fly in **all** MG cluster cases, not just Lapras. The bandaid's
`damage/opp.hp < 0.8` test doesn't discriminate:

- Lapras [1,2]:   BB 99 / hp 142 = 0.70 → fires (PvPoke's Fly plan wins; ours loses by 1 HP)
- Jellicent [0,0]: BB 99 / hp ~160 = 0.62 → fires (PvPoke's Fly plan worse by ~47 HP)
- Corviknight cluster: similar 0.6-0.7 ratios → fires (PvPoke's Fly plan worse by ~38 HP)

So the fix is all-or-nothing against a 6:1 weighting; matching PvPoke
inverts the ratio rather than improving it. Per CLAUDE.md "When our
sim diverges from PvPoke": PvPoke isn't demonstrably better overall,
and our deviation has a defensible reason (better HP retention in 6
of 7 cases). Keep the `_cached_damage` subgate as the intentional
deviation that implements this choice.

**Outcome comparison** — full magnitude across the cluster (UL top-8
harness, MG max HP=161, all cases MG wins in both sims):

| matchup           | ours MG HP | PvPoke MG HP | gap         |
| ----------------- | ---------- | ------------ | ----------- |
| Jellicent   [0,0] | 92  ( 57%) | ~45 ( 28%)   | +47 / +29pp |
| Jellicent   [0,1] | 137 ( 85%) | ~89 ( 55%)   | +48 / +30pp |
| Jellicent   [0,2] | 137 ( 85%) | ~89 ( 55%)   | +48 / +30pp |
| Corviknight [0,0] | 45  ( 28%) | ~7 (  4%)    | +38 / +24pp |
| Corviknight [0,1] | 71  ( 44%) | ~33 ( 20%)   | +38 / +24pp |
| Corviknight [0,2] | 97  ( 60%) | ~59 ( 37%)   | +38 / +23pp |

Consistently +23-30 percentage points (~38-48 raw HP). MG also KOs
6-12 turns earlier in our sim. The magnitude is what makes our
divergence defensible — if the gap were a few HP, PvPoke's plan
would be at-or-better than ours and we'd match. At 25-30pp the
post-KO carry-over difference is material for next-mon analysis.

**Caveat — Lapras [1,2] winner flip**: 1 of 7 cluster cases is a real
edge case where our plan is worse. Same root cause (MG picks BB, PvPoke
picks Fly-Fly-Fly), but Lapras is bulky enough (234 HP) that our BB's
atk debuff bites AND PvPoke's 3 Fly throws add up:
- Ours: Lapras barely wins 502/497 (MG 0 HP, Lapras 1 HP, 1-HP margin)
- PvPoke: MG wins 608/391 (MG ~34 HP, Lapras 0)

Here PvPoke's slower plan **is demonstrably better** — it correctly
predicts MG wins a close fight that our BB-nuke loses by 1 HP. Pinned
as its own xfail in `tests/test_battle.py` under `_MG_NEARKO_PLAN_FLIP`.

**Decision**: keep our DP behavior, net. Rationale is 6:1 weight of
clear-win cases (ours retains 23-30pp more HP) against 1 close-fight
flip. Per CLAUDE.md "When our sim diverges from PvPoke" policy: PvPoke
is better for close/bulky matchups, ours is better for clear-win HP
retention. Neither plan is universally right.

**Impact** (UL harness top-8): 7 cases show |Δ|>20 (jellicent×3 at
d1=-146, corviknight×3 at d1=-118, lapras×1 at d1=+111 with winner
flip). All MG-involving, all defender=MG or bulky-water-attacker.
GL unaffected (no top-8 GL species has this matchup shape).

**Revisit** if: (a) wider harness sampling adds more bulky opponents
that produce close-fight flips (shifts the 6:1 ratio); (b) we add a
shield-state / multi-mon model where next-mon HP carry-over isn't the
only scoring dimension; (c) a probabilistic/random DP mode would
prefer PvPoke's lower-variance multi-throw plan; (d) we find a
discriminator that separates Lapras-style bulky-comeback matchups
from Jellicent/Corv-style clear-wins (bandaid[885]'s existing
`damage/opp.hp < 0.8` test doesn't — all 6 cluster cases land in the
0.6-0.7 band alongside Lapras at 0.70).

**Closed lead (2026-04-15 followup):** "Port a non-debuf swap into
the near-KO DP branch" was the original session hypothesis. The
localization found the mechanism is PvPoke's post-DP bandaid[885],
not a near-KO plan-selection difference — so porting a near-KO swap
would diverge from PvPoke, not match it. Issue retired.

### Tie-break semantics on simultaneous-KO (score=500/500) — resolved 2026-04-15

Previously two harness cases showed up as "winner flips" on 500/500
double-KO ties:
- GL `wigglytuff vs azumarill [2,2]`
- UL `corviknight vs moltres_galarian [2,2]`

Root cause was in the harness scripts, not the sim: `pvpoke_trace.js`
collapsed PvPoke's native tie output (`winner.pokemon = false`) to
`winner=1` as a shortcut, while our sim correctly returned `None`.
`harness_grid.py` then mapped `None → -1` for JSON output, producing
a spurious flip.

Fix: `pvpoke_trace.js` now emits `winner: null` on genuine ties
(matching PvPoke's native semantics); `harness_grid.py` preserves
`None` end-to-end. Sim behavior unchanged. GL flips 1 → 0, UL flips
2 → 1 (the remaining UL flip is the real Lapras [1,2] divergence).

### Closed 2026-04-15: needsBoost — not implementing (PvPoke system is dead code)

Originally flagged as an open port. Full root-cause writeup is in
"PvPoke bugs found" §7 above. Short version: PvPoke's code looks
like it picks alternative plans from a `stateList` accumulated over
chance-<1 buff states, but (a) line 539 unconditionally zeros
`changeTTKChance` so no chance-<1 states ever reach `stateList`, and
(b) the `needsBoost` flag is never assigned `true`. Empirically
verified 0 "needs the BOOST" log hits across 36 sims covering every
GL-meta species whose default moveset includes a `buffApplyChance<1`
charged move (Tinkaton, Corviknight, Clefable, Drapion).

**Our single-plan behavior already matches PvPoke's observable
behavior.** Porting stateList+needsBoost would diverge from the
reference in the direction of a feature PvPoke has explicitly
disabled — exactly the anti-pattern the CLAUDE.md "When our sim
diverges from PvPoke" policy warns against.

Revisit only if PvPoke removes line 539 or fixes the
`needsBoost = true` assignment upstream.

### Resolved divergences (full writeups in CHANGELOG.md)

* **2026-04-15 — Defender-bestCM-selfDefenseDebuffing shield gate
  (UL Moltres-G score-margin cluster).** Ported PvPoke Battle.js:1105-
  1124. Our `pvpoke_simulate_shield` was always-shielding standard
  charged moves; PvPoke instead routes the shield decision through
  `wouldShield` whenever the **defender's own** `bestChargedMove` is
  `selfDefenseDebuffing` — defender saves shields for the post-debuff
  fragility window. Two sub-branches by attacker shields: if attacker
  has shields, override directly; if attacker has 0 shields, override
  only when defender's next charged-cycle would KO the attacker
  (cycleDamage and CMP-aware turn-comparison gates). Helper
  `_estimate_best_cm` *(updated 2026-06-13)* now delegates to the
  pvpoke_dp setup cache's `best_idx` — the energy-sorted,
  priority-shuffled selectBestChargedMove with the literal
  SUPER_POWER carve-out (Pokemon.js:799: Superpower needs a DPE edge
  > .3 to displace, others .03). The original best-actual-DPE
  approximation wrongly returned Superpower for Malamar-likes and
  entered this branch when PvPoke (best = Foul Play) always-shields
  instead — the 38-cell `bestcm_estimate` family in the 2026-06-12
  oracle grid. `_cheapest_cm` still proxies
  attacker.activeChargedMoves[0].
  Probe: MG vs Florges [2,0] previously d1=+230, now d1=0 (same
  chargedLog as before, but MG correctly skips shielding the second
  Disarming Voice → 9% HP remaining instead of 55%, matching PvPoke).
  UL grid: max |Δ| 230→146, |Δ|>20 18→7, winner flips 2→2 (no new
  flips introduced). GL grid: max |Δ|=0 across 405 pairs unchanged
  (no top-8 GL species default moveset has a selfDefenseDebuffing
  charged move). Tests 156p/6xf, oracle 27/27 unchanged.
  Localization landmark: trace_shields output revealed the gap
  immediately — `wouldShield(...) → False` followed one turn later
  by `shield(...): True (always shield)`. The helper text
  ("[defBestCM=BRAVE_BIRD selfDefDebuff, attShields=0, no cycleKO]")
  added to trace makes the new gate auditable from log inspection.

* **2026-04-14 — selfBuffing flag scope.** Now matches PvPoke's
  `GameMaster.js:873` definition (positive self-buffs *and*
  guaranteed opponent debuffs).
* **2026-04-14 — activeChargedMoves priority-shuffle.** All
  `resetMoves` shuffle clauses replicated in `pvpoke_dp`. **Keep in
  mind** when revisiting bait-wait: PvPoke's
  `selectBestChargedMove` overwrites `.dpe` to raw `damage/energy`
  *after* the priority-shuffle, so the 1.5 ratio check
  (`ActionLogic.js:843`) uses raw DPE, same as our `actual_dpe`.
  Buff-adjusted DPE only affects the shuffle ordering, not the
  ratio check.
* **2026-04-15 — Forretress/Azumarill DP plan-selection.** Near-KO
  DP now tracks attacker `atk_stage` and recomputes charged/fast
  damage at every reachable stage so stacked chance-1 opp-def
  debuffs accelerate plans the way PvPoke does. Azu/Forr
  (Sand+Rock) now matches PvPoke 9/9 exact. Gotcha preserved for
  future readers: raw gamemaster `buffApplyChance` is a string;
  compare via `float(...) != 1.0`.
* **2026-04-15 — Mimikyu disguise-bust missing log line (meta-lesson).**
  Pinned via the new chargedLog test assertions: when Azu's "break
  Mimi's disguise" charged throw lands on a still-disguised Mimikyu,
  the `simulate()` loop's disguise-bust branch (battle.py:2066-2075)
  emits `Mimikyu (Busted) disguise busted (1 dmg)` but skipped the
  standard `Azumarill uses Ice Beam → 1 dmg` line. So
  `_extract_battle_log` lost one entry, and PvPoke's chargedLog
  appeared to have one extra Azu IB at the front. Fix: emit the
  "uses" line in the disguise branch too. All 6 Mimikyu xfails (4
  AZU_OPENING_IB + 2 SS_DELAY) flipped to clean passes; PvPoke "bug
  #4" was retracted (see above). **Meta-lesson:** the audit in
  docs/validations/2026-04-15_harness_code_review.md correctly
  identified the disguise-handling DP path as implemented, but
  audited DP/policy features rather than the throw-dispatch logger.
  Log emission is downstream of the DP and isn't covered by oracle
  score tests, so divergences there were silent until chargedLog
  assertions were added. Future feature audits should include a
  pass over the timeline/log emission paths, not just the
  decision-making code.
* **2026-04-15 — Many-cycle non-debuff swap (Moltres-G cluster winner flip).**
  Ported PvPoke's ActionLogic.js lines 371-393: when bestChargedMove is
  selfDebuffing AND a cheaper non-debuffing alt exists with DPE ratio
  < 2x, drop the farm-down threshold from 2.0x to 1.1x cycles AND swap
  the first-throw to the non-debuffing alt. Without this, our near-KO DP
  picked the debuffing nuke (BrB) and bandaid [918] stacked, letting
  Lapras KO first. Concrete case: Lapras vs Moltres-G [0,1] at MG energy
  49 (Fly affordable, BrB not). PvPoke's MG throws Fly (61 free damage,
  no atk debuff, Lapras has 0 shields); our MG waited for BrB and died.
  Fix: compute min_cycle_thr=1.1 when the debuffing-best-with-cheaper-
  non-debuf-alt condition holds, and swap selected_idx to the non-debuf
  alt in the farm-down path. UL harness-grid max |Δ| 352→230, winner
  flips 4→2 (the Lapras[0,1] flip and one other resolved). Remaining
  MG-cluster deltas are score-margin only (same chargedLog order),
  investigated separately — see "Open divergences" below. GL grid
  unchanged (max |Δ|=0 across 405 pairs). Tests 156p/6xf, oracle 27/27.
  Localization landmark: instrumenting PvPoke ActionLogic.js with
  `console.error` at the many-cycle entry revealed that PvPoke's
  bestChargedMove computation uses raw `damage/energy` (post-STAB,
  post-effectiveness), not `power/energy` — an easy misread when
  eyeballing DPE.
* **2026-04-15 — OMT fast-also-KOs gate dropped.** The OMT KO-override
  had a `defender.hp > _fast_dmg` gate: if the fast move would ALSO KO,
  prefer fast over charged (rationale: "score identical, saves energy /
  animation / post-KO state"). Harness localized Forr vs Azu 1-0 (Δ=-15)
  to T37: Forr has e=64 (ST affordable) and Azu hp=17; fast_dmg=18>=17
  so the gate fires and Forr delays for fast. But Forr just fired VS at
  T36 (floating), so its next fast doesn't land until T40 — three extra
  turns of Azu damage on Forr. The "score identical" claim held only
  when the fast could fire immediately; under mid-cooldown timing it
  fails. Dropped the gate, keeping the self-debuffing clause. GL grid
  max |Δ| 15→0 across all 405 pairs. UL unchanged (Moltres-G is a
  different root cause). Test suite: 156 pass (one prior xfail converted
  to pass — Azu's final Ice Beam in Forr/Azu (2,0) chargedLog now
  matches PvPoke). Investigation landmark: decideLog entry/return
  tracing in scripts/pvpoke_trace.js (decideAction-level) was the tool
  that localized the divergence — earlier score/dpPlan-level traces
  missed it because the divergence was in OMT, upstream of the DP.
* **2026-04-15 — Farm-down boost-move override + raw_dpe fix.**
  Two linked DP gaps surfaced when localizing GL Empoleon vs
  Forretress 2-2 (Δ=-204). (1) When the near-KO DP returns a
  farm-down plan (no charged moves in the winning path), our code
  returned `None` and the Pokemon never threw. PvPoke
  (ActionLogic.js:813-823) instead force-pushes `getBoostMove()`
  — the LAST charged move in user order with chance≥0.5 buff
  and not selfDebuffing — so the debuff value lands on the
  opponent even when the KO is guaranteed by fast moves alone.
  Ported in `pvpoke_dp`: farm-down plans now substitute the
  boost move as `first_idx` and fall through the existing
  bandaid chain. (2) `raw_dpe` was `power/energy`, but PvPoke's
  `move.dpe` is `move.damage/move.energy` (type-effectiveness-
  aware, set by `selectBestChargedMove` at Pokemon.js:792 and
  overwriting the buff-adjusted DPE from `initializeMove`). Fixed
  to use cached actual damage. Together these close the
  Forretress cluster: GL grid max |Δ| 204→15, |Δ|>20 count
  16→0, |Δ|>50 count 6→0. UL grid unchanged (Moltres-G cluster
  has a different root cause). Side effect: 12 log-order test
  fixtures updated (scores/winners already matched PvPoke; only
  throw order was stale); 3 Mimikyu xfails now xpass. Oracle
  27/27 still green.

### 3. bestChargedMove computed per-turn, not cached at init (intentional)

**PvPoke**: `bestChargedMove` is computed once at init (and on self
form change via `resetMoves`). Not updated when the opponent changes
form or when stat stages change.

**Our code**: `best_idx` is recomputed every call to `pvpoke_dp` using
current damage values. We believe this is more correct: it responds to
stat stage changes mid-battle and to opponent form changes (e.g.,
Aegislash Shield->Blade dramatically changes defender's def, shifting
DPE thresholds). PvPoke's stale cache produces suboptimal move choices
when opponent stats change, as documented in PvPoke bug #2 above.

**Impact**: +134 delta on Aegislash 1v2/2v2 — our Azu correctly
switches to Play Rough (higher DPE against Blade form) while PvPoke
keeps using Ice Beam (cached against Shield form's def).

**Decision**: keep our per-turn recomputation. The only known
mismatches are in Aegislash scenarios where PvPoke's cached selection
is demonstrably worse.

## Threshold model: damage tiers vs matchup boundaries

The deep dive reports two kinds of stat threshold (2026-04-09/10):

**Damage-tier boundaries** (`_aggregate_flips_by_anchor`): the exact
def (or atk) at which `floor(0.5 * 1.3 * Power * Atk/Def * Eff * STAB) + 1`
steps by 1. These are pure-formula boundaries, invariant to battle
conditions (energy leads, bait policy, turn count). Discovered by
Level 3 anchor enumeration.

**Matchup-flipping boundaries** (`_find_matchup_boundaries`): the
minimum def (+HP) at which the overall battle outcome changes from loss
to win. Usually higher than the damage tier because multiple per-hit
reductions must accumulate across a full fight to change the turn count.
Found by sweeping def thresholds against sim results.

Both are shown in the HTML output: damage tiers in the "Anchor-Driven
Matchup Flips" section, matchup boundaries in "Matchup-Flipping
Boundaries" and in tier cards. The distinction matters for future
energy-lead work: damage tiers won't change, matchup boundaries will.

## Key implementation details

### DP queue insertion (pvpoke_dp)

PvPoke uses three different insertion strategies in the DP queue:
1. **Farm-down** (`<=`): insert after same-turn states
2. **Ready-move** (`<=` + dedup): dedup at exact turn, then insert after
3. **Not-ready-move** (`<`): insert before same-turn, giving charged-move
   KO paths priority over farm-down

The `<` for not-ready states is critical — it produced 2 exact PvPoke
matches and several closer scores for Azu vs Forretress.

### selfBuffing / selfDebuffing thresholds

PvPoke gates these flags on `buffApplyChance`:
- `selfBuffing`: chance == 1 only (guaranteed buffs)
- `selfDebuffing`: chance >= 0.5 (excludes low-chance like HJK at 10%)
- `DRAGON_ASCENT` is explicitly excluded from selfDebuffing

These flags control the shield policy: guaranteed self-buff moves use
the `wouldShield` heuristic, while chance-buff moves are always shielded.

### Form change gotchas

Two non-obvious behaviors discovered during form change implementation
(2026-04-14) that are easy to get wrong:

**1. HP does not scale on form change.** When Aegislash switches between
Shield form (97 atk, 272 def) and Blade form (272 atk, 97 def), the HP
and max_hp stay fixed at the starting form's values. PvPoke's
`Pokemon.js changeForm()` has the HP update explicitly commented out:
`//this.stats.hp = newStats.hp;` (line ~2365). This means Aegislash
keeps Shield form's HP even after transforming to Blade. It would be
natural to assume HP scales proportionally with the new form's stats,
but it doesn't.

**2. Aegislash Blade form uses whole levels only.** When Shield form
(level 46 in GL) transforms to Blade form, the game rounds DOWN to the
nearest whole level (not half level). In Pokemon Go you power up in
0.5-level increments, so a Blade form could theoretically be level 22.5
(1476 CP, under the 1500 cap), but the game puts it at level 22 (1443
CP) instead -- losing a half level of stats. PvPoke's `getFormStats()`
(Pokemon.js line ~2455 as of pvpoke bc532fbda) implements this via
`newLevel--` (decrementing by 1, not 0.5). This was discovered by cascade1185
(https://x.com/cascade1185/status/2037456058265075782) and explained by
Caleb Peng (https://www.youtube.com/watch?v=OdHxOD6FZcg&t=167s). When
choosing which Aegislash to power up, players need to check that the
Blade form level lands on a favorable whole number.

**3. The Blade->Shield reverse level formula overflows the CPM table.**
PvPoke's `getFormStats()` aegislash_shield branch starts the Shield
level at `blade_level / 0.5 + 2` (GL) as a deliberate overshoot, then
walks down whole levels until CP fits. A low-IV Blade *focal* caps at
level 25 in GL (whole-level rule above), putting the raw start at 52 —
past the end of the CPM table (max 51.0). PvPoke survives because it
computes form stats lazily at form-change time and JS just yields
`undefined` (`cpms[index]` out of range — a latent PvPoke bug); our
dive plumbing builds per-IV `FormChangeConfig`s eagerly at sweep setup,
so the first post-S1 Aegislash (Blade) GL dive crashed with
`KeyError: 52.0` (2026-06-11). Fix: `_aegislash_shield_level` clamps
its start to `max(CPM)` — exact, since levels above 51 don't exist and
the walk-down from 51 reaches the same fixed point. Pinned by
`tests/test_pokemon.py::TestAegislashShieldLevelOverflow` (exhaustive
4096-IV × GL/UL build sweep). Blade really does revert to Shield
in-battle (gamemaster trigger `activate_shield`), so the reverse
mapping is load-bearing, not hypothetical-only.

## Active alt-moveset opponent variants

`opponent_pools/active_variants.toml` lists project-wide alt-moveset
opponent variants that auto-merge onto every loaded opponent pool.
The file is read by `scripts/deep_dive.py` (`_apply_active_variants`)
unless the dive is invoked with `--no-active-variants`.

Use case: a meta-relevant species has a competitive split between
two fast moves (e.g. Forretress with Volt Switch vs Bug Bite) and we
want every focal dive's matchup matrix to see *both* fast-move forms
of that opponent without editing each pool file.

Schema per `[[variants]]` entry:

```toml
species = "Forretress"   # PvPoke speciesName, base form (no shadow suffix)
shadow  = true           # optional, default false
fast    = "BUG_BITE"     # optional fast-move ID override
charged = ["A", "B"]     # optional charged-move ID list override
note    = "..."          # free-form; ignored by the loader
```

At least one of `fast` / `charged` is required. Display name is
auto-generated:

* `Forretress | fast=BUG_BITE` → `Forretress (Bug Bite)`
* `Forretress (Shadow) | fast=BUG_BITE` → `Forretress (Shadow) (Bug Bite)`

The loader skips a variant whose `(species, shadow)` isn't already
in the loaded pool, so a single TOML can ship across leagues — a
GL-only Forretress entry quietly skips on UL pools. A display-name
collision with the inline pipe-syntax (e.g.
`Forretress | fast=BUG_BITE` directly in a pool file) is also a
no-op; inline wins.

Toggling:

* Comment out a single `[[variants]]` block to disable that variant
  while keeping the entry in source.
* Pass `--no-active-variants` to skip the auto-merge for one dive
  (clean-baseline reproductions).
* Empty / delete the file to disable globally.

The same per-line override format is also accepted directly in pool
files — `_parse_opponent_pool_line` handles `| fast=ID` and
`| charged=A,B` syntax. Use inline overrides when the variant is
genuinely pool-specific; use `active_variants.toml` when it should
apply across pools. Memory file
`project_active_alt_movesets.md` tracks which variants are currently
active and the pre-dive confirmation habit.

## Deep dive output file layout

Deep dive HTML files (and the logs that come with them) generated by
`scripts/deep_dive.py` are user-specific scratch — never committed to
the repo. There are two valid locations depending on whether you might
want to revisit the file later:

* **`userdata/dives/`** — for deep dives you want to keep around:
  baseline runs, runs you'll compare against later, anything you might
  want to look at again after a reboot. The whole `userdata/` directory
  is in `.gitignore`, so the files persist on disk but never enter the
  git history. Create the directory if it doesn't exist
  (`mkdir -p userdata/dives`).

* **`/tmp/`** — for truly throwaway in-session iterations: smoke tests
  while you're tweaking renderer code, "let me see what this looks like
  with a different flag", etc. macOS clears `/tmp/` on reboot, so don't
  put anything there you'd be sad to lose. Within a session, `/tmp/`
  is fine and the convention I (and Claude) have been using for quick
  verification cycles.

When in doubt, prefer `userdata/dives/` — the cost of an extra
directory entry is nothing compared to the cost of accidentally losing
a 7-minute deep dive run to a reboot.

The convention applies to all output files from `scripts/deep_dive.py`:
the HTML itself, the `.log` redirect file if you used one, and any
ancillary data (cached cohort dumps, etc.). If you're scripting batch
runs that produce many dives, point `--html` at a path under
`userdata/dives/` rather than the repo root.

Reference deep dives that *should* live in the repo (e.g., the
validation HTMLs under `docs/validations/`) are a separate category —
those are checked in deliberately as point-in-time evidence and don't
follow this convention.

## Log file layout

`scripts/deep_dive.py` and `scripts/deep_dive_slayer.py` route all
progress, warnings, and final-output tables through a structured logger
(`scripts/deep_dive_logging.py`). Rationale and the per-call-site
classification live in `docs/structured_logger_design.md`; this section
is the steady-state reference.

**Per-run log file.** Every dive opens
`userdata/logs/YYYY-MM/YYYYMMDD_HHMMSS_<species>_<league>[_shadow].log`
and writes every INFO/WARNING/RESULT record (plus DEBUG when
`--verbose` is passed). The monthly subdir is created on demand. File
records carry a full `[YYYY-MM-DD HH:MM:SS.mmm] LEVEL   deep_dive: ...`
prefix so `grep -E '\] WARNING' userdata/logs/2026-04/*.log` is a
reasonable forensic starting point. As with `userdata/dives/`, the whole
`userdata/logs/` tree is gitignored — logs persist across reboots but
never enter the repo.

**Latest-run symlink.** Right after the file is opened, the logger
atomically refreshes `userdata/logs/latest.log` to point at the current
run. Canonical monitoring command:

```
tail -f userdata/logs/latest.log
```

The symlink is swapped via `rename(2)`, so a long-running `tail -f` from
another terminal never lands on a broken link mid-update — the previous
run's file stays open on the old inode until you stop tailing it.

**CLI flags** (on `scripts/deep_dive.py`):

- `--verbose` — promotes aggregator DEBUG records to the log file.
  Stdout is unchanged.
- `--quiet` — suppresses INFO on stdout; WARNINGs and the Top-20 /
  banner RESULT records still appear. The log file is unaffected.
- `--log-file PATH` — overrides the auto-generated log path. Use
  `/dev/null` to disable the file handler entirely.
- `--log-dir DIR` — relocates the logs root. Useful for batch runs
  that want their own dated directory. Ignored when `--log-file` is
  given.

**Worker processes.** Spawn-mode pool workers (default on macOS) do not
inherit the parent logger's handlers. Each pool's initializer calls
`deep_dive_logging.worker_log_setup(log_path, verbose=...)` — a bare
`print()` from a worker bypasses the log file *and* stdout buffering
kicks in. If you add a new multiprocessing surface, thread `log_path`
and `verbose` through `initargs` alongside the existing state. See
CLAUDE.md "Debugging conventions" for the commit-time rules around
ad-hoc debug prints.

**Periodic cleanup** via `scripts/clean_logs.py` (dry-run default):

```
# Preview what would go away
python scripts/clean_logs.py --older-than 30d

# Actually delete
python scripts/clean_logs.py --older-than 30d --execute

# Archive (move to userdata/logs/archive/YYYY-MM/) instead of deleting
python scripts/clean_logs.py --older-than 60d --archive --execute

# Keep only the 50 most recent runs across all months
python scripts/clean_logs.py --keep-last 50 --execute
```

No auto-purge inside `deep_dive.py` — deletions happen only when you
run the cleanup script with `--execute`. The archive subtree is
gitignored the same way the live tree is.

## All-in-one vs split-moveset HTML

The all-in-one interactive HTML (`--interactive` without `--split-movesets`)
generates the Deep Dive Results section (tier cards, anchor-flip bullets,
matchup boundaries, notable IVs) once for the top-ranked moveset only.
When the moveset dropdown changes, the Plotly scatter updates (score
data is embedded for all movesets) and the IV Flavor Guide narrative
zone swaps (per-moveset narratives are pre-rendered in hidden divs),
but the rest of the analysis stays fixed on the top moveset.

In `--split-movesets` mode each HTML file gets its own full call to
`generate_analysis_sections` with that file's moveset, so every section
reflects the correct moveset. This is the intended experience for the
website — all-in-one is primarily for quick interactive score-distribution
comparison during development.

**History note (2026-06-10):** the paragraph above was false from
2026-04-12 to 2026-06-10. A cross-file analysis cache (`fa34f39`)
assumed split files shared identical analysis and served **moveset 0's
analysis sections in every split file** (surfaced as the "wrong
moveset in the Deep Dive Results subheader" symptom on the Sylveon
NAIC dive — the label was the visible tip; the whole section was
moveset-0's). The cache is removed; a tripwire assertion in
`generate_interactive_html` now verifies each split file's results
subheader names that file's moveset. Split dives published before the
fix carry moveset-0 analysis on their non-landing pages and need a
re-render to correct.

## Article lifecycle

Articles live in `articles/*.toml` (source TOML, checked in) and render
to `userdata/website/articles/<slug>/` via `scripts/render_article.py`.
Full schema: `docs/article_schema.md`.

### Marking an article obsolete

When a CD move turns out to be strictly better/worse than the sidegrade
framing claimed, or the meta shifts enough that the analysis no longer
applies:

1. Edit the article TOML (e.g. `articles/oinkologne-cd-2026-05.toml`).
2. Change `[obsolescence]` fields:
   ```toml
   [obsolescence]
   status = "obsolete"
   as_of  = "2026-06-15"       # date you're marking it obsolete
   note   = "Mud Slap is strictly better in GL; sidegrade framing no longer applies."
   ```
3. Re-render: `python scripts/render_article.py articles/oinkologne-cd-2026-05.toml`
4. Republish: `scripts/publish_website.sh --push`

The renderer shows a red banner at the top of the page with the note
text and date. No other files need to change.

### Changing authorship level

The `authorship` field tracks content origin. Update it as the article
evolves:

- `auto` — scaffold / auto-generated placeholder content
- `both` — human has edited the prose, but it's backed by sim data
- `expert` — fully human-written analysis

Edit the field in the article TOML and re-render. The banner color
changes automatically (blue -> green -> gold).
