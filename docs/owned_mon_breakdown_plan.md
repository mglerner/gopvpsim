# Owned-mon breakdown: "which of my mons should I build?"

Point the ML-IV-guide breakdown at the Pokemon you actually own (a PokeGenie
export): for each owned copy of a species, show what it gives up versus the
best-possible spread, so you can decide which to power up. Wanted on both the
**website** and the **gobattlekit iOS app**.

This plan is backed by a parallel investigation of the three codebases
(2026-06-21). Bottom line: **feasible on all three surfaces with no new battle
engine** — a precompute-once / read-everywhere design.

## The two-layer core (shared spec)

Every surface reproduces the same computation, split into two layers:

1. **Analytic layer** — closed-form, port everywhere, must be bit-identical:
   - stat formula (`pokemon.py:94-101`), damage formula (`moves.py:227-242`).
   - attack breakpoints lost (`dx < d15`), defense bulkpoints lost (`dx > d15`),
     CMP lost (kept at 15 uses `>=`, lost uses strict `<`) —
     `iv_envelope_analysis.py:157-207`. Watch the asymmetric comparisons.
2. **Simulation layer** — expensive; **precompute once, read everywhere**.
   "Matchups dropped" = `hundo_won - won` set difference, where a win is
   `pvpoke_score(focal) > pvpoke_score(opp)` (`iv_envelope_analysis.py:125-144`).
   Needs the full engine + `pvpoke_dp` charge policy. **Do not port it to JS or
   onto the device.**

**Three invariants** (a port that breaks any of these silently diverges):
1. win is strict `>` (ties lose);
2. opponent IVs are always 15/15/15;
3. shadow multipliers ×1.2 atk / ×0.8333 def apply to effective stats, never to
   CP or HP.

Validate any port by round-tripping a known `userdata/dives/<slug>_iv_envelope.json`.

## How it meshes with what already exists (coherence)

This is an **enhancement of existing features on both apps, not a new silo** —
and both apps already take a PokeGenie CSV as input, so it plugs into existing
ingestion.

**Website** — the deep dive's **"Check my collection" paste-box** already:
parses your PokeGenie CSV client-side, recomputes at-cap stats, threshold-matches
your mons to the dive's tiers, overlays them on the scatter, AND already computes
"give up vs the best IV" as `_computePerShieldScoreDelta`
(`deep_dive_engine.js:2276-2283`, surfaced in the Top-IVs table). The deep-dive
HTML also embeds the **full 4096-IV × scenario × opponent score grid**
(`SCORES_GZ`, `deep_dive.py:3644-3713`), and the paste-box already resolves a
pasted IV to its grid index (`canonicalIvIdx`). So the breakdown is a
**column-add to the collection table** via the proven `extras` mechanism
(`renderMatchesList` ~L1047-1075, exactly how the Slayer-IVs section adds its
Top-Mirror CMP % / Matchups-Kept columns). No re-simulation, no new Python
export, no change to the parity-locked `user_collection.js` matcher.

**gobattlekit (iOS)** — the **IV-check screen** (`screens/user_iv_checker.py`)
already ingests your PokeGenie CSV (iOS share-sheet → Inbox poll) and checks
owned mons against **pre-baked** per-species thresholds (`default_thresholds.toml`)
using a parity-pinned pure-Python stat/IV engine (`data/iv_checker.py`). The
breakdown is a **richer version of the same question** — not just "does it clear
the tier floors" but "what does it give up." It is a new Toga screen modeled on
`user_iv_checker.py`, fed by breakdown data **baked offline** through the
existing `tools/threshold_export/` pipeline (the app has no battle sim and must
not get one — that would break the lean iOS build).

**Fidelity/coverage gradient** (worth knowing): Python re-sim (any species/league,
slow) ⊇ website (full grid, but limited to the dive's opponent pool + swept
modes + on-grid IVs) ⊇ iOS (baked subset of species/IVs). A true "scan my whole
collection across species" wants breadth — served per-dived-species on the web,
per-baked-species on iOS, or by the Python CLI iterating meta species.

## Per-surface plan

| Surface                                   | Status                      | Approach                                                                                                                                                                                                                                                   |
| ----------------------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Python** (`scripts/owned_breakdown.py`) | **DONE (reference/oracle)** | Re-sims each owned spread vs the league pool; reads a real PokeGenie CSV via `user_collection` + evolution walk; ranks owned copies and lists drops vs rank-1. League-aware via `at_best_level`.                                                           |
| **Website JS**                            | scoped, not built           | Column-add to the paste-box collection table. On-grid: read `SCORES[key][iv*nS*nO+si*nO+oi]`, threshold ≥500, diff vs rank-1/pvpoke ref IV for per-matchup drops; reuse `_computePerShieldScoreDelta` for the aggregate. Touch `deep_dive_engine.js` only. |
| **iOS (gobattlekit)**                     | scoped, not built           | New Toga screen modeled on `user_iv_checker.py`; bake per-IV breakdown data into the bundle via `tools/threshold_export/`; analytic layer recomputed on-device, simulation layer consumed pre-baked. Add `tests/test_parity_vectors.py` vectors.           |

## Build order

1. **Python reference** (DONE) — the oracle the other two are checked against.
2. **Website column-add** — highest value/effort: all data already ships; it is a
   rendering extension following a proven template. Needs visual review.
3. **gobattlekit screen** — bake the data, add the screen, pin parity vectors.

## Top risks

1. **Off-grid / pruned dives (web):** score deltas exist only for on-grid IVs;
   a `--species-iv-floor` dive leaves some owned mons scoreless (show `-`).
   Mitigation: assume/guarantee an unpruned full-4096 dive (the default).
2. **Silent cross-port divergence** on the three invariants. Mitigation:
   round-trip a known JSON + parity vectors before shipping any re-implementation.
3. **gobattlekit parity is hand-maintained** (`iv_checker.py` is a port, not a
   shared import). Mitigation: add parity vectors for every new analytic helper;
   keep the simulation layer as consumed pre-baked data so it cannot drift.

Key files: `scripts/iv_envelope_analysis.py` (canonical core, L125-207),
`scripts/owned_breakdown.py` (Python reference),
`scripts/deep_dive_engine.js` (web extension point ~L1047-1075,
`_computePerShieldScoreDelta` L2276-2283),
`src/gopvpsim/user_collection.py` (`match_mons` to fork, L296-412),
`gobattlekit/src/gobattlekit/data/iv_checker.py` + `screens/user_iv_checker.py`,
artifact schema `userdata/dives/<slug>_iv_envelope.json`.

## Status (2026-06-21)

- **Python reference** (`scripts/owned_breakdown.py`): DONE, end-to-end on a real
  PokeGenie CSV (incl. evolution walk). The oracle.
- **Website column-add** (`scripts/deep_dive_engine.js`): DONE + pushed. A
  "Gives up vs #1" column in the paste-box collection table (per-tier + Slayer
  sections), count + hover list, reusing the scatter hover's proven SCORES diff.
  Re-render a dive to see it (replay is enough); paste a CSV to populate it.
- **gobattlekit screen**: NOT built. Needs the bake below + UI review.

### gobattlekit bake: extract from existing dives, do NOT re-sim top-K

A first exporter that sim'd the **top-K stat-product spreads** was a dead end:
those spreads are exactly the bulk-leaning cluster, so they all "give up nothing"
vs rank-1 — the differentiation lives in the **attack-weighted / lower-SP
spreads**, and an owned collection holds **arbitrary** IVs anyway. So the bake
needs full-grid coverage, and re-simming all 4096 per species would just
duplicate work the dive already did.

**Correct approach:** the deep dive already computes the **full 4096-IV ×
scenario × opponent score grid** (the same `SCORES` the website embeds). The
gobattlekit bake should **extract per-IV dropped-vs-rank-1 lists from an existing
dive's grid** (via the replay blob / the computed sweep), emit a compact
per-(species, league) artifact `{rank1, drops: {"a/d/h": [...]}}`, and bundle it
like `default_thresholds.toml`. The on-device screen (modeled on
`screens/user_iv_checker.py`) parses the owned CSV, resolves each mon through its
evolution line, looks up its IV in the artifact, and renders the breakdown.
**Open product decision before building:** which leagues/species to bundle
(bundle-size vs coverage on a mobile app).

### Extractor built + the size finding (2026-06-21)

`scripts/export_owned_breakdown_bundle.py` extracts the breakdown from a dive's
embedded `SCORES_GZ` (decode base64+gzip uint16, index `iv*nS*nO + si*nO + oi`,
win = score>=500), diffs every IV's even-shield win set against
`DATA.rank1RefIvIdx`, and emits `{rank1, drops:{"a/d/h":[...]}}`. It uses key
`0_pvpoke` (moveset 0, dive's default opponents), so it **matches the website
"Gives up vs #1" column** (same SCORES, same convention — the dive's PvPoke-default
opponents, NOT the CLI's 15/15/15).

**The size finding:** the full per-IV dropped-list JSON is **~25.6 MB for 15
species** — almost every IV gives up at least one marginal (opponent, scenario)
cell vs rank-1, so the "omit drops-nothing" compaction barely helps (only rank-1
+ a couple of exact ties are empty). Too big to bundle on iOS.

**Mobile format (do this before bundling):** store a per-IV **bitmask** over the
even-shield (opponent × scenario) cells dropped vs rank-1 — 82 opp × 3 = 246 bits
= ~31 bytes/IV × 4096 ≈ 127 KB/species (gzips much smaller), plus a one-time
header `{opponents:[...], scenarios:[...]}`. The on-device screen decodes the
mask to render the dropped list. The human-readable JSON the extractor emits now
is fine for the website-equivalent / debugging, but the iOS bundle needs the
bitmask form. **Remaining: the bitmask exporter variant + the Toga screen +
parity vectors.**
