# Changelog

Completed/shipped work, reverse chronological. **Not** part of the
session-startup read (see `CLAUDE.md`). Purely historical reference
for "when did we ship X" and "what was the root cause of that old
bug." Active pending work lives in `TODO.md`; still-relevant
invariants and PvPoke bugs live in `DEVELOPER_NOTES.md`.

## 2026-04-18 — S10: Oinkologne CD article + Male-vs-Female comparator

**Ship session for the post-S5 Oinkologne arc.** Wires the Female dive
data into the CD article, adds a Male-vs-Female form-comparison
section, extends the site index, verifies bidirectional links, and
deletes the archived Lechonk CD prep plan.

**What shipped:**

1. `scripts/compare_loadouts.py` — MVP pairwise loadout comparator.
   Loadout-list-keyed data model (`loadouts: list[LoadoutSpec]`,
   pairwise deltas via `itertools.combinations`) so N=3 / N=4 are a
   renderer extension rather than a rewrite. MVP ships N=2 only.
   Output: `userdata/website/comparisons/<slug>/index.html` plus an
   importable `build_comparison_fragment()` that `generate_article.py`
   inlines.
2. `comparisons/oinkologne-male-vs-female.toml` — comparator spec for
   the Oinkologne CD arc.
3. `generate_article.py` — new canonical `form-comparison` section
   between Matchup Delta and IV Recommendations, gated on a
   `[form_comparison]` block in the article TOML. Absent the block the
   section drops out cleanly.
4. Site-index updated with both Oinkologne dives, the article, and
   the comparison page. (Site index at `userdata/website/index.html`
   is gitignored, so the edit is local-only by design.)

**Reconciliation vs `~/.claude/plans/archive/lechonk-cd-prep.md`:**

The archived Lechonk plan scoped six sessions targeting a JRE-style
prose article by 2026-04-22. The actual ship happened through the
post-S5 Oinkologne arc (S1-S10), with three documented scope shifts:

- **JRE-style prose → Python-generated spec sheet.** Rationale: JRE
  writes for money; shipping Claude prose mimicking his voice is not
  acceptable. Tracked in TODO.md "CD article generator" (2026-04-16).
- **One dive → Male + Female dives.** Oinkologne forms have
  meaningfully different base stats (186/153/242 vs 169/162/251);
  both receive Mud Slap on the same CD, so both need threshold data.
  Tracked in memory `project_female_oinkologne.md`.
- **No comparator → compare_loadouts.py MVP.** Added this session to
  make the Male-vs-Female section a reusable tool rather than inline
  article code. Tracked in memory `project_ab_comparator_timing.md`
  and TODO.md "Moveset / variant comparison tool".

Aegislash form-change dive (floating beat in the old plan) remains
pending under TODO.md "SwagTips narrative follow-ups".

Archived plan deleted post-reconciliation.

## 2026-04-15 — Forretress/Azumarill DP plan-selection (atk-stage fix)

**Context:** our Azu vs Forr (Sand+Rock) score matrix diverged from
PvPoke by up to +118 rating points, despite our DP tracking
`has_debuf`/`debuf_count` for dedup tie-breaks. Investigated with the
new headless Node harness (`scripts/pvpoke_trace.js`) which emits a
`termLog` of every DP terminal pushed.

**Root cause.** PvPoke's `BattleState` carries a `buffs` field (the
attacker's atk-stage delta) that accumulates as the DP stacks moves
with chance-1 self-atk buffs *or* chance-1 opp-def debuffs. See
`ActionLogic.js:519-535` — line 531 `attackMult -= move.buffs[1]`
effectively promotes an opp-def debuff to a self-atk buff inside
the DP. When a child state is popped, line 471 calls
`poke.applyStatBuffs([buffs, 0])` and recomputes
`moveDamage`/`fastSimulatedDamage` against the buffed atk. Our
`_DPState` held `cm_dmgs[]` and `fast_damage` fixed at root-state
values for the *entire* DP rollout, so stacked-ST plans never
accelerated and never terminated in our reachable-state space — our
DP accepted `[RT]+farm` at turn 13 instead of PvPoke's
`[SAND_TOMB, SAND_TOMB]` at stateTurn 10.

**Fix.** `_DPState` now carries an `atk_stage` field; `pvpoke_dp`
precomputes a per-stage damage table (9 rows, stage ∈ [-4..+4]) and
each child state indexes its own row for charged- and fast-move
damage. `cm_buff_delta[n]` = +1 for chance-1 self-atk-buff or
chance-1 opp-def-debuff and bumps `new_atk_stage` on throw (clamped
to [-4, +4]). `_dp_insert_ready` phase-1 dedup now requires equal
`atk_stage` so stacked-buff plans aren't merged away. `_dp_jit.py`
mirrors the change — kernel takes `cm_buff_delta`, `cm_dmgs_stage`
(9 x n_cms), `fast_dmg_stage` (9,), `root_atk_stage`, and the queue
arrays gain a parallel `q_atk_stg` slot.

**Scoreboard.** Azu/Forretress (Sand+Rock) now matches PvPoke 9/9
exact across all shield scenarios. 157 pytest + 27/27
`verify_pvpoke_harness.py` still green. Commit `141eee1`.

**Gotcha.** Raw gamemaster `buffApplyChance` is a *string*, not a
number. The initial `!= 1` comparison was silently false for every
move; the production check is
`float(m.get('buffApplyChance', 0) or 0) != 1.0`.

## 2026-04-14 — Form Change

Data-driven via gamemaster `formChange` field. Three form-change
families implemented:
* **Morpeko** — toggles Aura Wheel between Electric and Dark.
* **Aegislash** — Shield ↔ Blade swap (stats, moveset, level
  adjust).
* **Mimikyu** — disguise effect absorbs first unshielded hit; on
  break, applies -1 def stage.

Form changes DO affect opponent shielding (Aegislash Shield form
suppresses shields when damage < half HP) and baiting (Mimikyu
opponents break disguise ASAP with the cheapest charged move).

Oracle tests: Morpeko 6/9, Aegislash 1/9, Mimikyu 6/9 match PvPoke
exactly. Remaining mismatches were initially attributed to a "DP
cycle-timing" gap; that lead was subsequently closed 2026-04-15
(Azu vs Aegislash 0v0 now throws IB twice, matching PvPoke; all
9 0v0 form-change fixtures land on harness score). Plan file:
`quizzical-hatching-kahan.md`.

**Open follow-ups** (tracked in `TODO.md`): Mimikyu deep dive with
form-change narrative; Goodra / Aegislash test-drive dives for the
new SwagTips narrative renderer.

## 2026-04-14 — PvPoke divergence RESOLVED: selfBuffing flag scope

Our `selfBuffing` flag in `moves.py` now matches PvPoke's
`GameMaster.js:873` definition: guaranteed positive self-buffs AND
guaranteed opponent debuffs (`buffTarget="opponent"`,
`buffApplyChance==1`). Previously only covered self-targeting buffs;
workarounds in shield policy and bait-wait were removed. All 8
`selfBuffing` usage sites now use the broadened flag consistently.

## 2026-04-14 — PvPoke divergence RESOLVED: activeChargedMoves priority-shuffle

PvPoke's `resetMoves` (`Pokemon.js:711-787`) reorders
`activeChargedMoves` after the energy sort based on buff/debuff
properties. The priority-shuffle uses buff-adjusted DPE
(`initializeMove`, `Pokemon.js:849-864`) for one clause. Our code
now replicates all shuffle clauses in `pvpoke_dp`.

**Historical note (corrected):** Divergence 2 was originally
documented as "bait-wait DPE ratio uses `actual_dpe`, not
buff-adjusted DPE." This was incorrect. PvPoke's
`selectBestChargedMove` (`Pokemon.js:791-796`) *overwrites* `.dpe`
to raw `damage/energy` on all `activeChargedMoves` after the
priority-shuffle, so the bait-wait 1.5 ratio check
(`ActionLogic.js:843`) also uses raw `damage/energy`, same as our
`actual_dpe`. The buff-adjusted DPE only affects the
priority-shuffle ordering (lines 711-787), not the ratio check
itself. This paragraph is load-bearing — if you ever revisit
Divergence 2, it will explain why the "obvious" fix wasn't needed.

## 2026-04-09/10 — Stat-target reframing (SwagTips round 1)

Threshold Tier cards, matchup-flipping boundaries, HP co-conditions,
auto-derive from clean dives, scatter plot visual overhaul, HTML size
reduction. 26 commits. Key design decisions:

### Two kinds of threshold
- **Damage-tier boundaries** (from `_aggregate_flips_by_anchor`): the
  def/atk at which `floor(damage_formula)` steps by 1. Invariant to
  battle conditions (energy leads, bait policies). Come from Level 3
  anchor discovery.
- **Matchup-flipping boundaries** (from `_find_matchup_boundaries`):
  the def (+HP) at which the overall battle outcome flips win→loss.
  Usually higher than the damage tier because multiple damage reductions
  must accumulate. Depend on battle conditions — will shift when we add
  energy-lead sims. Both are shown: damage tiers in anchor-flip bullets,
  matchup boundaries in their own section + tier cards.

### Auto-derive path (no TOML needed)
`_auto_derive_tiers` consumes both anchor-flip records (atk-side) and
matchup boundaries (def-side). Tiers ranked by selectivity (fewest
qualifying IVs first); General excluded from scatter plot coloring.
Tinkaton clean dive produces tiers at ~143 def (≈acidicArisen GH Great),
~140 def (≈GH Good), ~138 def (intermediate). Validated against 4/6
acidicArisen findings.

### Open threads for next sessions
- **Atk-side matchup-flipping boundaries**: `_find_matchup_boundaries`
  currently only sweeps def. Should also sweep atk for species where
  atk breakpoints flip matchups (e.g. Annihilape Lickitung BP at 127).
  Same algorithm, different partition stat.
- **Energy-lead matchup boundaries**: damage tiers don't change with
  energy leads, but matchup boundaries do. Once we add energy-lead sim
  options (`--energy-lead 1` etc.), re-sweep matchup boundaries under
  those conditions. The two-layer display (damage tier + matchup flip)
  is designed for this.
- **Shadow / atk-weighted opponent IVs**: acidicArisen's Shadow Drapion
  (140.21 def) uses "attack-weighted" opponent IVs, not rank-1 or
  PvPoke default. Our system doesn't simulate arbitrary opponent IV
  spreads. Possible fix: `--opp-ivs custom:119.80` in the TOML or CLI.
- **HP co-condition on atk-side**: currently only def anchors try HP
  co-conditions. Atk-side anchors theoretically could too (HP affects
  whether a fast-move damage increase translates to a KO), but no
  known case warrants it yet.
- **CMP anchor schema shorthand**: acidicArisen's CMP thresholds
  (105.58 Corviknight, 105.79 Lickilicky, etc.) can't be expressed as
  CMP anchors without an IV-list spread. Need a `opponent_species`
  shorthand that resolves the opponent's rank-1 atk automatically.
  Listed in "Schema simplification" TODO.
- **HTML size**: down from 25 MB to 10 MB (base64 uint16 scores +
  Notable IVs member cap). Remaining 9 MB is packed scores. Further:
  delta-encode, drop non-displayed moveset scores, or serve gzipped.
- **deep_dive.py refactor**: now ~6000 lines. The extraction targets
  in the Refactoring TODO are still valid; this session added
  `_find_matchup_boundaries`, `_auto_derive_tiers` (matchup boundary
  path), `_probe_tier_cutoff_flips`, `_render_matchup_boundary_bullets`
  as new extraction candidates for `deep_dive_lib/boundaries.py`.

## 2026-04-09 — Structured IV categories (round 1)

Unified `IVCategory` framework abstracting over slayer categories,
threshold tiers, and their intersections. New "Notable IVs" HTML
section surfaces composite (slayer ∩ tier) cards and matchup
(opponent, scenario) cards with auto-generated tradeoff prose.
Annihilape `13/0/11` lands as the canonical example: "The sole Atk
Slayer that also clears the Top 5% threshold (hp≥139). Trades mirror
dominance (45/132 wins, vs 132/132 for the top Atk Slayer survivors)
for the Top 5% cutoff." Section is gated behind a "show only notable"
header checkbox (≤ 5% of cohort or ≤ 5 members, default on). Round 1
ships zero TOML changes — composite + matchup categories are
auto-derived from existing infrastructure. Bait dimension on
`matchup_conditions` is reserved (`None`) until the bait-axis sweep
TODO lands. Commits: `f3aa4ad` (dataclass + builder), `8ff4469`
(matchup branch), `79e2e87` (renderer), `b344356` (wire-in). Cross-ref:
"Hand-named composite categories via TOML" and "Bait-axis matchup
categories" in Deep-dive narrative for round 2 followups.

## 2026-04-08 / 2026-04-09 — Bulkpoint anchor system

Def-side mirror of `damage_breakpoint` anchors. Three precision levels
(L1 explicit, L2 reference-anchored via `above_def`, L3 discover-and-tag),
parser, resolver, auto-fallback, tests, docs, Annihilape TOML entries.
Bulk Slayer category gained dual membership (structural HP+def OR
clears at least one named bulkpoint). `ResolvedAnchor` generalized to
`target_stat` with `threshold_value` so the same passes() machinery
handles both atk and def side. Commits: `13665dc` (main feature +
brkp/blkp rename + tag UX + CLI args embed — should have been split,
see commit message), `8f9369d` (clarify ×N count in hover tooltip),
`7ed5765` + `967bb09` (Compact/Expand toggle for tag cells).

**Headline finding** from running the new system on Annihilape
explicit: the historical Lurgan Ape `def ≥ 102.9` floor is *not*
recoverable as a single (move, tier) bulkpoint. The next bulkpoint
above 102.9 is `shadow_ball ≤149` at def 103.34, but 0/66 of today's
converged cohort can reach it (max cohort def ~101.30). The 102.9
floor predates Rage Fist, so the threat-move set has shifted; today's
optimization trades def for atk and lands well below the historical
baseline. Don't promote anything to Level 1 from this enumeration —
follow up via Discord with mercuryish to recover historical context
(see "Send mercuryish a Discord message" in Analysis goals).

## 2026-04-08 — bp → brkp short-name rename

Renamed all anchor name slugs from `_bp_` to `_brkp_` so the
breakpoint short form is unambiguous against the new bulkpoint
`_blkp_` short form. The Python kind discriminator stays
`damage_breakpoint` (full word); only the slug-style short forms
changed. Touched anchors.py, build_auto_anchors, annihilape.toml
anchor table keys, tests, and docs. Part of commit `13665dc`.

## 2026-04-08 — Ultra-short anchor abbreviations + Compact tags toggle

Tag cells in slayer cards previously truncated badges horizontally
with `text-overflow: ellipsis` at 280px max-width, hiding most of
the badges past the first 2-3. Replaced with: (a) `derive_short_name`
function producing 3-6 char badge labels (cre, lic, mirb, lic↑lur,
c:lur, quasb...) with the long form preserved in the badge hover
tooltip, (b) cell wrapping enabled, max-width bumped to 480px,
(c) Compact/Expand toggle button at the top of the slayer card grid
that caps cells at ~2 lines via an inner `<div>` wrapper (the wrapper
is needed because `<td>` ignores `max-height` in CSS — fixed in
`967bb09` after the first attempt at the toggle didn't actually work).
Part of commit `13665dc` + the three follow-ups.

## 2026-04-08 — CLI args embedded in HTML output for forensics

`format_cli_args(args, parser)` builds the *fully-resolved* equivalent
invocation: every flag emitted with its actual value, including flags
whose value happens to equal the current parser default. Embedded in
HTML two places: a grep-able `<!-- CLI: ... -->` comment near the top
and a collapsed `<details>` footer at the bottom of `<body>`. Also
printed to console at startup as `CLI: ...`. Why fully-resolved
instead of literal user input: defaults can change between runs, so
a string that omits "default" flags becomes ambiguous when read later.
This is the forensic gold standard. Part of commit `13665dc`.

## 2026-04-08 — Slayer anchor system

The TOML threshold schema (`docs/threshold_schema.md`), anchor
resolver (`gopvpsim/anchors.py`), and anchor-tagged
`categorize_slayers` are all in place. Atk Slayer and CMP Slayer use
named anchors instead of vacuous median heuristics. Three precision
levels for damage_breakpoint anchors (L1 explicit, L2
reference-anchored, L3 discover-and-tag). Auto-fallback layer
synthesizes anchors at runtime when the user doesn't provide them
via TOML, gated per kind so explicit user input always wins. Commits
`beace47` (main) and `10a693c` (mercuryish testimony incorporated
into thresholds/annihilape.toml + anchors tests).

## 2026-04-07 — Battle simulator perf optimization (round 1 + round 2 + chunking)

Real-world impact: ~9hr → ~6 min on a full Annihilape mirror slayer
deep dive workload. Stack of optimizations:
* Damage cache + DP hoisting — +51% throughput (commit `3596fb4`)
* Numba JIT on the near-KO DP loop — +40% throughput (commit `a57c39f`)
* Stat profile dedup in `iv_sweep` — ~1.7x faster Phase 2 (commit `6ccb124`)
* Slayer iteration: dedup focal & opponent IVs by effective stats
  (commit `579aef7`)
* Slayer iteration: keep all IVs tied at top win count (commit `eb145a2`)
* Chunk count bumped from `n_workers` to ~100 for finer progress
  reporting (commit `8498ec4`)

Round 3 (numba JIT for the entire inner sim loop) was deprioritized
after round 1+2 made the workload tolerable; fastmath was confirmed
a dead-end during the round 1 work.

## 2026-04-07 — Iterative slayer discovery (Nash-style mirror match)

`scripts/deep_dive.py --mirror-slayer` runs Round 0 (focal IVs vs
PvPoke default opponent) then iterates Round k (focal IVs vs round
k-1's top survivors), stopping on convergence or `--mirror-slayer-rounds`.
Survivors are classified into RyanSwag-style Atk Slayer / Bulk Slayer
/ CMP Slayer categories. Disk cache at
`~/.cache/gopvpsim/slayer/<key>.pkl` keyed on species/league/shadow/
moves/scenarios so re-runs are near-instant. Commits `43b8784` (main),
`75fa8ce` (HTML rendering), `9cabba7` (cache key fix), `3b9d5fb`
(metric/rounds/pool/show CLI flags), `0dfcc98` (validation doc).

## 2026-04-06 — IV deep dive script + interactive HTML

`scripts/deep_dive.py` simulates all 4096 IV spreads of a focal
species against meta opponents across moveset combinations, with
threshold-tier coloring, custom group support, and an interactive
HTML mode (`--interactive`) with moveset/scenario/opp-IV switching
dropdowns. Commits `f0253d5` (script), `a4d18e5` (interactive mode),
`30452c6` (PvPoke default IVs for opponents), `4c7bcf9` (legend
isolation, matchup hover), `6924b1a` (`--standalone` inline Plotly).
Doc reorganization in `0ce1229` (CLAUDE.md, TODO.md, DEVELOPER_NOTES.md).

## 2026-04-04 to 2026-04-06 — Battle simulator correctness (Mienfoo vs Medicham)

Several rounds of bug fixing brought the battle simulator into
agreement with PvPoke's reference output:
* Three turn-model bugs: 1-turn FM timing, faintSource, FM fire order
  (commit `e036670`)
* Buff/debuff implementation (commit `6145aaa`)
* Buff meter, pvpoke_simulate_shield, trace flags (commit `ead46c1`)
* ActionLogic.js post-DP bandaids, sort cms by energy, raw_dpe
  (commit `f4d0eb3`)
* DP queue insertion strategies, intended_pruning flag (commit `44f3215`)
* Shadow Pokemon support (commit `8c5fb65`)
* `wouldShield` buff reset ordering, CMP cancellation (commit `5b07790`)
* All 9 Medicham vs Azumarill scenarios match PvPoke (commit `008d8e7`)

### Mienfoo vs Medicham — FIXED (all 9/9), root cause

Two bugs specifically responsible for the Mienfoo vs Medicham all-9
pass:

1. **wouldShield buff reset ordering** (battle.py `would_shield`):
   The charged-move threat loop ran BEFORE resetting the temporarily-
   applied stat buffs, inflating damage predictions. PvPoke resets
   buffs first (ActionLogic.js:1136-1140), then evaluates charged-move
   threat (lines 1145-1165). Fix: moved the reset before the loop.

2. **CMP (Charge Move Priority) cancellation** (battle.py `simulate`):
   When both Pokemon fire charged moves simultaneously, the lower-ATK
   Pokemon's move should be canceled if it was KO'd by the higher-ATK
   Pokemon's charged move (PvPoke Battle.js:464-467). Our code had an
   exception that always allowed both to fire. Fix: track `charged_ko`
   set and cancel if `use_priority` and attacker was KO'd by a charged
   move.

## 2026-04-01 — pvpoke_dp charged-move policy

Implemented PvPoke's `ActionLogic.js` DP-based charged-move decision
policy in Python (`gopvpsim.battle.pvpoke_dp`). Commit `62b9cfb`.

---

# Resolved (deeper history)

* **Slayer Ape / Lurgan Ape IV analysis** — Resolved 2026-04-08 by
  mercuryish Discord testimony. The community Lurgan Ape spread is a
  *historical floor* (`atk ≥ 127.2`, `def ≥ 102.9`) calibrated to a
  Lickitung breakpoint near atk 127.23, predating the Counter nerf,
  Rage Fist addition, and Low Kick buff. Our slayer iteration's
  convergence to atk 129.44 matches *current* expert advice (push
  higher than the Lurgan baseline for CMP wins and BP security against
  the mirror and Lickitung). The "we disagree with the community"
  framing in earlier analysis was wrong — we converge to current
  expert practice; Lurgan is a frozen historical reference.
