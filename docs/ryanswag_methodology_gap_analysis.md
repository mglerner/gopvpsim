# RyanSwag methodology gap analysis (S0a)

**Written:** 2026-04-16, post-S0. Source: [`docs/ryanswag_how_to_deep_dive.txt`](ryanswag_how_to_deep_dive.txt) — transcript of RyanSwag's "How to do your own PVP IV analysis" video, featuring his Wigglytuff walk-through.

**Purpose:** map each technique in the transcript to our current method, flag numeric claims for Michael to confirm against the source video, and prioritise the implementation work. Analysis only — no code changes this session.

**Reading order:** skim the gap table, scan the numeric-verification list, then read the prioritised implementation list at the bottom.

---

## 1. Gap table

Techniques are ordered roughly as they appear in the transcript. `✅` = we do this (often more thoroughly); `≈` = we do something equivalent but differently; `❌` = we don't do this.

| #   | RyanSwag technique                                                                                                                                                                  | Transcript ~line       | Our method                                                                                                                                                  | Evidence                                                                                                                                                                                                                                              |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T1  | Custom opponent group via PvPoke matrix (Championship Series set, add mons as needed)                                                                                               | 31–42                  | ✅                                                                                                                                                           | `scripts/deep_dive.py` `--group` flag; `--opponents N`; TOML anchors inject extra opponents                                                                                                                                                           |
| T2  | Hand-picks 5+ focal IV variants (rank-1, HP-weight, max-def, slight-atk, heavy-atk)                                                                                                 | 43–68                  | ✅ more thoroughly — we sweep all 4096 IVs                                                                                                                   | `scripts/deep_dive.py` `iv_sweep`; `gopvpsim.pokemon.all_ivs`                                                                                                                                                                                         |
| T3  | Focal variant selection to stress-test spread axes                                                                                                                                  | 43–68                  | ✅ as T2                                                                                                                                                     | same                                                                                                                                                                                                                                                  |
| T4  | Fast-move-class framing ("charm / waterfall / razor-leaf typically favor stat product"; notes Shadow Victreebel as exception)                                                       | 70–94                  | ❌                                                                                                                                                           | `scripts/deep_dive_narrative.py` — no matches for `charm`, `razor_leaf`, `fm_class`, `fast_move_class`                                                                                                                                                |
| T5  | "What's the minimum bulk for functional play?" framing (most players don't have rank-1)                                                                                             | 95–105                 | ≈ Our tier names (Premium Bulk / Balanced / etc.) imply this but no explicit synthesis line                                                                 | `scripts/deep_dive_narrative.py:774-943` render_narrative_zone — tier-by-tier, no minimum-viable callout                                                                                                                                              |
| T6  | Attack breakpoints via PvPoke matrix "Break Points" button                                                                                                                          | 126–134                | ✅ richer — Level 1/2/3 damage_breakpoint anchors in TOML                                                                                                    | `docs/threshold_schema.md:174-262`; `thresholds/annihilape.toml:492-510`                                                                                                                                                                              |
| T7  | **Matchup-flip attribution: IV threshold vs PvPoke DP strategy-flip** (Venusaur FP-vs-LT against rank-1 vs variant Wigglytuff)                                                      | 165–207                | ❌ — we detect flips but don't distinguish cause                                                                                                             | `scripts/deep_dive_analysis.py:133-212` `narrate_flip` — compares per-hit damage only; no dpPlan/move-sequence comparison across variants                                                                                                             |
| T8  | **Post-debuff breakpoints** (Lantern spark 7→5 after Icy Wind for one Wigglytuff vs 7→6 for rank-1)                                                                                 | 208–254                | ❌ at the threshold layer. Mechanics are simulated correctly in `gopvpsim/battle.py`, but not surfaced as a threshold primitive                              | `scripts/deep_dive_analysis.py:154-184` — breakpoint scan uses raw `pvp_damage` with focal's base stats only; grep for `post_debuff`, `def_stage`, `atk_stage`, `icy_wind`, `after_debuff` in `scripts/` → 0 matches                                  |
| T9  | **Attack-weighted opponent variants as a default** (prepares for 7/15/14 Metacham at 106.9 atk alongside rank-1; "axen-adjacent" high-atk Metacham; 10/15/14 Lickitung at 98.2 atk) | 307–377                | ❌ systematically. Schema supports `opponent_ivs` / `opponent_spread` but no TOML actually uses them; every anchor currently runs against PvPoke rank-1 only | `thresholds/oinkologne.toml`, `thresholds/tinkaton.toml`, `thresholds/annihilape.toml` — zero occurrences of `opponent_ivs` or `opponent_spread`; `scripts/deep_dive.py:628-641` `resolve_opp_ivs` picks one opponent-IV mode globally per run        |
| T10 | **Rank-1 self-check in the narrative conclusion** ("rank-1's 224 HP — if you have rank-1, expand target pool to 229")                                                               | 398–430                | ❌                                                                                                                                                           | `scripts/deep_dive_narrative.py` — grep for `rank_1`, `rank1`, `is_rank1` → 0 matches; `scripts/deep_dive.py:2148-2159` computes rank-1 IV index but only uses it as a reference opponent, never validates rank-1 against the species' own thresholds |
| T11 | Spreadsheet tracking of threshold + scenario + IV-used (e.g. "Mantine 0-0 no-bait, 115.44 atk; Lantern 2-1, 225 HP with 74.8 def")                                                  | 152–163, 281–287       | ✅ our threshold-aware HTML *is* this spreadsheet (anchor tables + Notable IVs cards + per-scenario flip bullets)                                            | `scripts/deep_dive_rendering.py` flip narration; anchor-flip aggregator                                                                                                                                                                               |
| T12 | Simulate all 9 shield scenarios                                                                                                                                                     | 69, 164, 255, 291, 380 | ✅ — we sim the full 0/1/2 × 0/1/2 grid                                                                                                                      | `scripts/battle.py` all-9; `scripts/deep_dive.py` scenario sweep                                                                                                                                                                                      |
| T13 | Synthesised minimum-stat conclusion ("probably want 75.1+ def, 225 HP baseline; expand to 224 HP if rank-1-adjacent")                                                               | 394–430                | ≈ Our spreads/tiers encode this implicitly per moveset, but no single "here's the one-line verdict" synthesis paragraph                                     | `scripts/deep_dive_narrative.py:820-869` multi-flavor intro paragraph — narrates flavors, not a "buy-this-or-better" bottom line                                                                                                                      |
| T14 | CMP wins considered via stat-product ordering (implicit in "probably CMP-based mirror matchup")                                                                                     | 383–387                | ✅ richer — `kind="cmp"` anchors against spread lists                                                                                                        | `docs/threshold_schema.md:150-174`                                                                                                                                                                                                                    |
| T15 | Expand IVs matching a derived target spread (225 HP + 75.1 def → 11 IVs in the PvPoke UI expand)                                                                                    | 406–418                | ✅ Notable IVs cards enumerate IVs meeting stat cutoffs                                                                                                      | `scripts/deep_dive.py` notable-IVs section                                                                                                                                                                                                            |
| T16 | Also run vs PvPoke default IVs (not just rank-1) to cover "random IV Pokemon" encounters                                                                                            | 430–434                | ✅ `--opp-ivs` supports `pvpoke`, `rank1`, `both`; default is `pvpoke`                                                                                       | `scripts/deep_dive.py:3195`, `:640`                                                                                                                                                                                                                   |
| T17 | Spot-check specific *known* IV variants beyond rank-1 (Lickitung, Metacham hand-picked atk-weights)                                                                                 | 307–377                | ❌ — same infrastructure gap as T9; each opponent-variant spot-check would need hand-authoring today                                                         | same as T9                                                                                                                                                                                                                                            |
| T18 | Shield-scenario + bait-mode threshold bullets ("2-2 no bait, 2-1 farm, 0-0 Ice Punch only")                                                                                         | 281–287                | ≈ scenario-axis shipped; bait axis is a tracked TODO                                                                                                        | `TODO.md` "Baiting policy as a deep-dive sim axis"; `TODO.md` "Bait-axis matchup categories"                                                                                                                                                          |

**Summary:** 6 of the 18 techniques are real gaps (T4, T7, T8, T9, T10, T17). T17 collapses into T9 (same infrastructure). T13 is a narrative style question rather than a method gap. Everything else is either covered or covered more thoroughly than the transcript's manual approach.

---

## 2. Numeric-claim verification list

**Policy:** the transcript is voice-to-text, and numeric strings like "051 12" or "75.0843 point5" have visible artifacts. Per `project_swagtips_narrative_sessions.md` and the arc's bail-policy note, transcript numbers are provisional until Michael confirms them from the source video.

**Status 2026-04-16:** Michael watched the focal-IV and opponent-IV segments of the video and confirmed all IV spreads (both originally-flagged and three additional hand-picks the transcript didn't name explicitly). Stat-threshold and debuff-mechanic numbers remain unconfirmed — flag each at point-of-use in S14/S15 and re-ask.

Format below: original transcript line preserved for audit, `**Video-confirmed (2026-04-16):**` line underneath with the correct value. `?` = still unconfirmed.

### Focal Wigglytuff IV spreads shown — ✅ confirmed

- transcript ~line 47–48: rank-1 Wigglytuff via "hitting maximize" is written as `"051 12"`.
  **Video-confirmed (2026-04-16):** `0/15/12`. (The transcript garble "051 12" was "0 15 12" mis-spaced; rank-1 Wigglytuff via PvPoke's maximize button is L51 BB at `0/15/12`, not L50 NBB at `0/15/15`.)
- transcript ~line 51: HP-weighted Wigglytuff shown as `"0915"`.
  **Video-confirmed (2026-04-16):** `0/9/15`.
- transcript ~line 56–57: "maximum defense by hitting you know defense and maximize" — no IV spelled out in transcript.
  **Video-confirmed (2026-04-16):** `0/15/2`.
- transcript ~line 58–65: "slight attack weight... just a little baby attack weight" — no IV spelled out.
  **Video-confirmed (2026-04-16):** `6/14/15`.
- transcript ~line 66–67: "wigly tff with a pretty huge attack weight" — no IV spelled out.
  **Video-confirmed (2026-04-16):** `14/14/15`.
- transcript ~line 400: "11 15.44% five" when discussing expanded-pool atk — voice artifact; unclear whether this is an IV spread or an attack-stat number.
  **Status:** `?` — not in the IV-focal segment Michael watched; re-confirm when S5a touches rank-1 self-check text.

### Focal Wigglytuff stat thresholds — **still unconfirmed**

- transcript ~line 149: "115.2 for attack stat" to gain the Mantine attack BP — `?`
- transcript ~line 262: "losing by just 2 HP so 224 HP could be a good baseline" vs Lantern 2-1 — `?`
- transcript ~line 269: "this Wigglytuff has 74.8 defense" with Thunderbolt dealing 78 — `?`
- transcript ~line 271: "if we had 75.4[s] then we might need one less HP, 223 could fit the bill" — `?`
- transcript ~line 279: "unless you're popping 75 plus defense, 225 HP could be more consistent" — `?`
- transcript ~line 306: "74.2 defense" — Wigglytuff def needed vs rank-1 Lickitung 0-1 — `?`
- transcript ~line 336: "75.0843 point5" — def vs atk-weighted Lickitung variants. Voice-to-text garble; likely two numbers. `?`
- transcript ~line 352: "73.41" — def needed vs rank-1 Metacham counter BP — `?`
- transcript ~line 372: "74.1 three" — def needed vs RyanSwag's preferred Metacham — `?`
- transcript ~line 398–419: final conclusions "75.1 def, 225 HP preferred; 224 HP OK if rank-1-adjacent; up to 229 HP in expanded pool" — `?`

These feed S14/S15 (post-debuff breakpoints) and the S5a rank-1 self-check. Confirm before driving design.

### Opponent IV spreads (**directly feeds S4a/S4b**) — ✅ confirmed

- transcript ~line 140: rank-1 Mantine written as `"0514"`.
  **Video-confirmed (2026-04-16):** `0/15/14` (transcript garble for "0 15 14"; not `0/5/14`).
- transcript ~line 332–333: "10 1514 lickong ... 98.2 attack stat".
  **Video-confirmed (2026-04-16):** `10/15/14` Lickitung — swag uses this instead of rank-1 `8/14/15` when preparing for atk-weighted Lickitung.
- transcript ~line 334: atk-weighted Lickitung "10413 right so 98.5 attack".
  **Video-confirmed (2026-04-16):** `10/14/13` (second atk-weighted Lickitung variant he considers).
- transcript ~line 360–361: RyanSwag's "Best of Both Worlds" Metacham "71514 with the 106.9 attack stat".
  **Video-confirmed (2026-04-16):** `7/15/14` at 106.9 atk (self-consistency check: `gopvpsim.pokemon.Pokemon.at_best_level('Medicham', 7, 15, 14)` → atk=106.9184). **This is the S4a end-to-end validation spread.**
- transcript ~line 370–374: "axe'n Metacham and axen-adjacent Metacham which have a high attack stat" — no numeric spread given.
  **Status:** `?` — not named in video per Michael's watch. If S4b wants axe'n variants, pull from RyanSwag's Metacham Slayer dive (not this transcript).
- transcript ~line 378: rank-1 Metacham variant written as `"16 15 14"` — IV max is 15, so this was voice garble.
  **Video-confirmed (2026-04-16):** `5/15/15` (rank-1 NBB Medicham; the transcript's "16 15 14" was "5 15 15" mis-transcribed). Self-consistency: `Medicham 5/15/15 GL` → atk=105.88, hp=142, matches typical rank-1 baseline.

### Debuff-mechanic numbers (**directly feeds S14**) — **still unconfirmed**

- transcript ~line 221–223: Lantern spark damage `7 → 5` on higher-def Wigglytuff post-IW — `?`
- transcript ~line 226: Lantern spark damage `7 → 6` on rank-1 Wigglytuff post-IW — `?`

Confirm before S14 design uses them as a canonical oracle.

### Canonical consolidated list (for downstream use)

Ready-to-paste for TOML authoring. League is Great unless noted.

**Wigglytuff focal hand-picks** (Wiggly rank-1 is computed, not authored):
- Rank-1: `0/15/12` (L51 BB via PvPoke maximize)
- HP-weighted: `0/9/15`
- Max-def: `0/15/2`
- Slight atk-weight: `6/14/15`
- Larger atk-weight: `14/14/15`

**Opponent variants RyanSwag uses against Wigglytuff:**
- Mantine rank-1: `0/15/14`
- Lickitung atk-weighted (primary): `10/15/14` (~98.2 atk)
- Lickitung atk-weighted (secondary): `10/14/13` (~98.5 atk)
- Medicham rank-1: `5/15/15` (~105.88 atk, NBB)
- Medicham atk-weighted: `7/15/14` (~106.92 atk) — **S4a validation spread**

If any of the still-unconfirmed stat/damage numbers above differ from the video when later checked, the Tier A items in §3 may need re-shaping.

---

## 3. Prioritised implementation list

Gaps are already sequenced in `~/.claude/plans/post-s5-oinkologne-arc.md` as S4a, S5a-additions, S13, S14, S15. This section confirms that sequencing is still right post-analysis and adds no new sessions.

### Tier A — already planned, confirmed as scoped

| Plan session     | Gap addressed                          | Matters because                                                                                                                                                                                                                                                                                   | Confirmed scope                                                                                                      | Session estimate           |
| ---------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| S4a              | T9 (attack-weighted opponent variants) | Without it, Oinkologne's threshold data assumes every Lickitung is rank-1, every Metacham is rank-1 — which RyanSwag says is false for competitive play; the actual atk-weighted variants may hit different focal defense bulkpoints. Also blocks T17 (same infrastructure).                      | `Minimum ship` in the plan is correct: convention + loader + one species (Metacham) end-to-end. Defer broad rollout. | 1 session                  |
| S5a-add (item 3) | T10 (rank-1 self-check)                | Avoids users concluding "none of my Wigglytuffs meet these thresholds" when rank-1 itself would fail — per the transcript, RyanSwag specifically notes that rank-1 Wigglytuff has 224 HP but derived preferred is 225+. Cheap one-line addition in the narrative renderer.                        | As scoped in plan. Lives in same subsystem as S5a bug fixes.                                                         | +0.3 session on top of S5a |
| S5a-add (item 4) | T4 (fast-mover-favors-bulk framing)    | Narrative context line for charmer-class species. Cheap default-on; TOML override for exceptions. Oinkologne is Mud Slap (not a charmer), so this is dormant on the arc's ship target, but will matter for future charmer dives.                                                                  | As scoped in plan. Small `fast_move_class.py` lookup.                                                                | +0.3 session on top of S5a |
| S13              | T7 (matchup-flip attribution)          | Currently we cannot distinguish "flipped because focal crossed a real BP" from "flipped because PvPoke's DP picked a different move sequence." Every gains-list in a shipped dive may contain false positives. Affects envelope-position metric (S4) and namesake-guarantee repairs (S5a item 1). | `Minimum ship` (one representative case) is correct; mop-up of previously-shipped dives can slip.                    | 1–2 sessions               |
| S14              | T8 design (post-debuff breakpoints)    | **Biggest genuine methodology gap.** Post-debuff stat thresholds are a dimension we simulate correctly but never surface as a named primitive. Four decisions to make (schema / sim-surface / narrative / display).                                                                               | `Minimum ship` (schema + sim-surface) is correct; narrative + display can slip into S15 start.                       | 1 session                  |
| S15              | T8 implementation                      | Implements S14 design. Validates on one species (RyanSwag's Wigglytuff + Lantern example is a natural oracle; Lantern is in GL meta).                                                                                                                                                             | `Minimum ship` (computable and surfaced somewhere on one species) is correct.                                        | 1–2 sessions               |

**Total new RyanSwag-driven work:** ~4.5–6.5 sessions, all already sequenced in the plan. No reshape required.

### Tier B — not promoting to new sessions

- **T13 (minimum-bulk synthesis line)**: our tier system already encodes this; the gap is stylistic, not informational. If during S5a authorship it feels natural to add a one-line "preferred-minimum" verdict under the rank-1 self-check, ship it there. If not, drop.
- **T11 (spreadsheet output)**: our HTML is already a richer spreadsheet. No action.

### Sequencing notes (anything that changes the plan)

- **S13 before S14 is still right.** Attribution (S13) reduces false flips that would otherwise contaminate post-debuff validation (S14/S15).
- **S4a before S5a is still right.** S4a produces the atk-weighted opponent data that the rank-1 self-check (S5a item 3) might want to compare against; even if it doesn't, it doesn't invert the dependency.
- **Nothing in this analysis reshapes S0–S3, S5, S6–S12, or the Aegislash floater.** The RyanSwag-driven gaps live in their already-sequenced lanes.

### What this analysis did NOT do

- **No numeric design work** that depends on unconfirmed transcript numbers. Everything in §2 is provisional until Michael confirms.
- **No code or test changes.** Per plan: analysis only.
- **No prioritisation of RyanSwag gaps against non-RyanSwag work.** The plan's dependency graph already sequences them; this doc confirms the scoping, not the relative urgency.

---

## 4. Handoff

- S4a session prompt should reference `§1 T9` and the confirmed `§2 "Canonical consolidated list"`. Metacham `7/15/14 @ 106.9 atk` is the validation spread.
- S4b session prompt should reference the confirmed Lickitung `10/15/14` and `10/14/13` variants for the broader authoring pass. Axe'n-Metacham variants are still unconfirmed and should come from RyanSwag's Metacham Slayer dive rather than this transcript.
- S5a session prompt should reference `§1 T10 + T4` for the rank-1 self-check and fast-mover-framing additions. Wigglytuff rank-1 `0/15/12` is confirmed if an example is needed.
- S13 session prompt should reference `§1 T7` and cite the transcript's Venusaur FP-vs-LT example at ~lines 165–207 as the canonical test case.
- S14 / S15 session prompts should reference `§1 T8` and the Lantern spark 7→5 / 7→6 example at `§2 "Debuff-mechanic numbers"`; **those damage numbers are still unconfirmed** and must be checked against the video before implementation.
