# Fix-packet runbook — 2026-06-13

Ordered implementation plan for tomorrow's sessions, assembled
2026-06-12 night while the overnight dive batch ran. Five packets live
in this directory; each has a patch file and a notes file with an
appended "Adversarial review" section. Read the notes file before
applying its patch.

**HEAD drift warning.** Packets were drafted against `a73d855` and
re-verified against `f4a3b3e`; sessions kept committing overnight.
**Re-run `git apply --check <patch>` immediately before every apply.**
If a check fails, the packet notes name the conflicting region;
regenerate rather than force.

**Companion documents:**

- `userdata/redive_prompt_2026-06-13.md` — Michael's paste-prompt; this
  runbook implements its steps with the packet-review verdicts folded in.
- `userdata/signal_loss_verified_findings_2026-06-12.md` — renderer
  defect list (D1-D6) and the safe ordering this runbook follows.
- `userdata/oracle_grid_2026-06-12/` — grid evidence
  (incoming_gate_writeup.md, grid_summary.md, grid_classified.json).
  Note: grid_summary's "14 draw cells" is stale; grid_classified.json's
  20 is correct (per shadow-cmp review).

## Packet status board

| #   | Packet            | Patch                                                     | Verdict        | Gate before commit                                                                        |
| --- | ----------------- | --------------------------------------------------------- | -------------- | ----------------------------------------------------------------------------------------- |
| 1   | incoming-gate     | `incoming-gate.patch`                                     | READY          | Confirm new unit test fails pre-patch (was derived statically, no pytest allowed tonight) |
| 2   | bestcm-superpower | `bestcm-superpower.patch`                                 | READY          | Apply after #1; re-check context; full-grid zero-new-divergence diff with BOTH applied    |
| 3   | shadow-cmp        | `shadow-cmp.patch`                                        | **NEEDS-WORK** | Two blocking defects (below) must be fixed before this can be committed                   |
| 4   | renderer-D1-D4    | `renderer-D1-D4.patch`                                    | **NEEDS-WORK** | D3 has a missed twin code site in deep_dive.py (below); fix alongside the patch           |
| 5   | renderer-D2-D5    | `renderer-D2-D5.patch` + rebased rendering-only companion | READY          | Must use the 3-command apply order AFTER renderer-D1-D4                                   |

## Global preconditions

- Overnight batch must be FINISHED before anything here runs (engine
  edits while workers run = corrupted caches; battle.py is in
  `sweep_cache._ENGINE_FILES`, so the engine hash auto-rotates on
  apply — no manual CACHE_VERSION bump needed for any engine packet).
- One commit per packet. Before each commit: `git diff --cached --stat`
  (parallel sessions may have staged files). Push stays nod-gated.
- Bare `python` only, never `python3`. Serial dives only,
  `--reserve-cpus 1`, emit the `watch -c -n 5 scripts/chain_status.py`
  command at every dive kick.
- Engine verify gate, run after EACH of packets 1-3:
  1. Full pytest, no `-m` filter: `python -m pytest tests/ -q`
  2. Perf benchmark: `python scripts/profile_slayer.py --n-focal 60
     --n-opp 20` — warm floor **>= 2,850 sims/s** (baseline 3,160;
     >10% drop = stop and investigate before proceeding).
  3. `python scripts/audit_oracle_harness.py` — exit 0.
  4. Grid re-run / probe (per-packet specifics below). Full-grid
     expectation once all three engine packets are in: **>= 3,300 exact
     of 3,420 and all 30 winner flips resolved**; anything that moved
     the WRONG way is a stop-and-investigate.

---

## Phase 1 — Engine fixes

### 1. incoming-gate (READY)

Drop the extra `self_def_debuffing` routing from
`use_heuristic_incoming` in battle.py's pvpoke_simulate_shield
(Battle.js:1077-1128 routes only `move.buffs && move.selfBuffing`; the
sole selfDefenseDebuffing test at 1105 is on
`defender.bestChargedMove`). Notes: `incoming-gate.md`.

Pre-apply checklist (from the review's open items):

1. **Confirm the new unit test FAILS on unpatched HEAD** before
   applying — its pre-patch FAIL was derived statically. If the
   would_shield arithmetic differs from the hand-trace, adjust attacker
   atk / defender hp. Static values to reproduce: dmg 32, post_hp 168,
   cycle 74.
2. **Fixture levels:** check whether `at_best_level` reproduces
   gamemaster defaultIVs levels for the new Tinkaton/Malamar fixture
   (Tinkaton L25, Malamar L23.5); pin `max_level=25.0/23.5` if not.
3. **Sequencing:** apply this packet FIRST, then re-run `git apply
   --check` on bestcm-superpower (both touch the shield-policy region
   of battle.py; both orders were sandbox-verified clean, but HEAD has
   moved).
4. **Probe ground truth:** `/tmp/oracle_grid_expansion/` may have been
   wiped; copies of `probe_incoming_gate.py` + `probe_grid_result.json`
   are preserved in this directory. Post-patch the probe's BASELINE arm
   should report **3098/3420 exact, +12 fixed / 0 broken** vs 3086. If
   the stored ground truth is unavailable, the heavier fallback is the
   full `scratch_oracle_grid/run_grid.py` re-sim.

Prose corrections to carry into the packet's test plan (none require
patch regeneration):

- The Mienfoo test claim is wrong: `simulate()` defaults to
  `pvpoke_simulate_shield`, not `always_shield`, and HJK IS a carrier;
  that test stays green only via the False→True-toward-PvPoke
  directional argument.
- Test name typo: `test_mg_vs_florges_*` is actually
  `test_moltres_galarian_vs_florges_shield_gate`.
- DRAGON_ASCENT is NOT a carrier in our sim (moves.py:185 replicates
  GameMaster.js:859's exclusion) — blast-radius list overstates by one
  move.
- Watch the Lapras [1,2] strict xfail (`_MG_NEARKO_PLAN_FLIP`): it's
  the one xfail where a shielded defender faces an incoming carrier.
  Almost certainly unchanged (BB trips the hp/1.4 clause), but the full
  pytest run will surface an XPASS loudly — if it XPASSes, inspect the
  fight per the CLAUDE.md divergence policy before celebrating.

Verification: per `incoming-gate.md` "Verification commands" + the
global engine gate. Generate the Tinkaton/Malamar 9-cell fixture from
`node scripts/pvpoke_trace.js`. Add the DEVELOPER_NOTES draft entry
from the packet.

### 2. bestcm-superpower (READY)

Port PvPoke `selectBestChargedMove`'s literal SUPER_POWER carve-out
(Pokemon.js:791-822: needs DPE edge > .3) into `_estimate_best_cm` by
delegating to the existing `_ensure_dp_cache` best_idx port. Single
consumer at battle.py:214. Fixes all 38 `bestcm_estimate` grid cells
(all Malamar). Notes: `bestcm-superpower.md`.

Apply AFTER incoming-gate; re-run `git apply --check` first. Stacking
was verified clean in both orders, so any conflict means new overnight
commits — regenerate, don't force.

Fold into the same commit (minor issues from the review):

- Update DEVELOPER_NOTES.md:574-588 — the "best-actual-DPE / pragmatic
  approximation" text goes stale with this fix.
- Docstring cites Pokemon.js 790-822; actual is 791.
- Add battle.py:1618 (bandaid[910]; ActionLogic.js:929-930 uses
  `opponent.bestChargedMove`) to the future-divergence list alongside
  `_cheapest_cm`.

Deliberately NOT in this packet:

- `_cheapest_cm` (battle.py:149) — the gate's other approximation;
  returns input-order slot 0 for equal-energy movesets (e.g. Malamar)
  instead of the shuffled slot 0. Same delegate-to-dp-cache treatment
  (`dp['cms'][0]`) would fix it, but grid evidence ties it to the
  separate tinkaton/malamar bandaid-chain "unknown" cluster. Flagged,
  not patched.
- The 12-cell tinkaton↔malamar incoming_gate family (packet #1's
  scope) and the 6 residual tinkaton/malamar "unknown" cells, which
  remain after both fixes.

Verification: per `bestcm-superpower.md` — all 38 bestcm cells must
match stored pv values; the probe scripts grid_summary cites
(probe_bestcm_family.py, probe2_grid_result.json) were NOT preserved,
so **the run_grid.py re-run is the real gate** here. Because the
incoming-gate cell family is all tinkaton-malamar pairs too, run the
full-grid zero-new-divergence diff once with BOTH battle.py patches
applied rather than per-patch.

### 3. shadow-cmp — **NEEDS-WORK** (do not commit as-is)

Core change (verified correct): shadow ×1.2 must not enter
CMP-flavored atk comparisons — plumb a shadow-free `cmp_atk` through
all 10 enumerated battle.py CMP sites, plus charged-only atk priority
bump and stable action sort for PvPoke draw parity (Empoleon cmp_atk
exactly equal at 125.1899635; Quagsire/Feraligatr 133.51→111.25 vs
123.88 flip; 20 ordered draw cells in grid_classified.json). The
mutual-KO draw path needs no porting (Battle.js:471 cancel is
usePriority-gated). Notes: `shadow-cmp.md`.

**BLOCKING defect 1 — missed call site.**
`scripts/deep_dive_signature.py:243` still computes the dedup CMP-sign
column from FOLDED atk. The on-by-default signature dedup will merge
focal profiles whose shadow-free CMP signs differ whenever one side is
shadow and the opponent's atk sits in the ×1.2 straddle band — wrong
scores fan out and persist into the sweep cache under the NEW engine
hash, partially defeating the fix on its target surface
(Forretress-shadow fires on every GL pool; 12 shadow TOMLs pending).
Required: plumb `cmp_atk` through `build_focal_side` / `_form_dict` /
`build_opp_side`, and add a shadow case to
`tests/test_signature_dedup.py`.

**BLOCKING defect 2 — false "zero test changes" claim.**
`tests/test_signature_dedup.py::_opp_entry` builds opp_cache dicts
without `cmp_atk` and drives the real `_sweep_worker`; the patched
strict `opp['cmp_atk']` read will KeyError both grouped-profile tests.
Give that fixture the same one-line update the packet gave
`test_dive_worker_form_change.py`.

Minor (fix in the same commit): stale comments at `_dp_jit.py:426-427`
and battle.py `fast_landings`.

Open items to carry:

- **Draw handling downstream:** `BattleResult.winner=None` becomes
  reachable in real dive sims (base-vs-shadow mirrors). pvpoke_score
  consumers are safe (500/500 symmetric), but audit every aggregation
  that buckets wins via `winner==0` — mirror synth, Matchups-Kept
  fractional expected-wins, slayer win counting — and treat a draw as
  0.5 expected wins BEFORE re-diving shadow species.
- Post-patch grid re-run must RE-CLASSIFY the shadow_cmp residue
  (expect 204 → ~0, but secondary mechanisms — bandaid[910] family,
  activeChargedMoves slot-order cosmetics — may keep some cells
  inexact). Don't assume.
- quagsire_shadow-vs-feraligatr 1v0/2v0 fixture cells sit in the known
  feraligatr ±1 score-rounding family (pv pairs sum to 999): decide
  pin-at-pv vs xfail-comment if they miss by exactly 1.
- Equal-CMP is a live-game coin flip; we and PvPoke resolve it
  deterministically in actor order. Worth a docs/concepts.md note if
  draw semantics get a user-facing writeup.

Verification: per `shadow-cmp.md` §7 (full suite, 153-cell audit
unchanged, empoleon mirror spot-check vs pvpoke_trace.js, grid re-run
into a NEW out file — run_grid.py skips existing cells, don't reuse
results.jsonl — and the perf gate).

---

## Phase 2 — Renderer fixes

Land these BEFORE Phase 3's re-dives launch so re-dives pick them up
free. None of these rotate the engine hash (`_ENGINE_FILES` excludes
scripts/), so no cache invalidation. After landing, replay-re-render
the KEEP species (`scripts/replay_analysis.py`) for renderer parity.

### 2.0 D6 — stale TODO.md paragraph (do first; zero code risk)

No packet; this is the edit, drafted per the verified-findings doc
(D6, verdict: confirmed). In `TODO.md` (the "Observed instance —
Oinkologne GL (2026-04-19)" paragraph, ~lines 558-573 at drafting
time), append this status annotation to the end of that paragraph
(annotate, don't delete — hide-don't-remove policy):

> **Status 2026-06-12: no longer reproduces; do not use as the audit's
> litmus test.** Current post-S7 builds (CACHE_VERSION slayer→3)
> refute the top-right clustering: the 100 slayer-tagged IVs now
> occupy SP ranks 2519-4093 with ZERO overlap in the top-2500 (first
> overlap at top-3000), and rank-1 atk 116.54 sits well below the
> slayer atk floor of 123.26 — the bulk-for-attack trade IS visible
> (female build matches: 29 slayers, ranks 3034-4035). The
> `index_m0_*.html` files referenced above no longer exist in the
> current per-moveset page layout. When the systemic audit picks a
> litmus case, use a currently-reproducing saturated example instead —
> e.g. the jumpluff-great-league 100%-flat slayer tables documented in
> `userdata/signal_loss_verified_findings_2026-06-12.md` (D2).

### 2.1 renderer-D1-D4 — **NEEDS-WORK** (apply with the fixes below)

D1 tier-rename uniqueness guard, D3 gap-count floor, D4 vacuous
Anchors-column gate. Core logic verified sound; `git apply --check`
passes at f4a3b3e despite the stale a73d855 header. Notes:
`renderer-D1-D4.md`.

**MUST FIX alongside the patch:** `scripts/deep_dive.py` ~2776-2786
inlines a twin of the D3 gap rule (g > 3*median, quartile gate,
sig[:5]) building `data_obj['clusterGaps']` for the JS scatter gap
lines. The packet's symbol-grep missed it. Without it, post-patch the
text says "0 significant gaps" while the plot still draws up to 5
lines from the degenerate threshold on every page. Apply
`max(3*med, MIN_SIG_GAP)` there too.

Also:

- One-liner: deep_dive_rendering ~3125-3130 Experimental-methods prose
  still describes the pure 3x-median rule.
- D1 verification gap: the exact-name match can re-route the HP sync
  (stamina write + `_recompute_tier_assignments`) to a different tier;
  extend the catch-all scan from tier-NAMES-only to a full tier-field
  + ivTiers diff.
- Cosmetic: update the packet header to current HEAD and drifted line
  refs.
- Coordination: renderer-D2-D5 edits the same row-emission block the
  D4 hunk rewrites — already pre-resolved via the rebased companion
  patch (see 2.2); apply D1-D4 FIRST.

Open / Michael decisions:

- **D3 threshold knob:** MIN_SIG_GAP=1.0 absolute floor (0.1% of the
  0-1000 score scale) was chosen over the findings doc's p99
  alternative (p99 structurally admits the top ~1% of 4095 gaps, so
  sig never empties and the "Smooth gradient" fallback stays
  unreachable). Needs one post-batch empirical pass (decode a few
  SCORES_GZ blobs, see how the 73-521 pre-fix counts land); one-line
  tune.
- D1 mechanism caveat: built HTML suggests the "Gyarados Slayer"
  flavor was dropped by signature dedup upstream (synth tier
  original_name=None); if a Gyarados flavor survives a rebuild, the
  exact-name layer still routes it — the tinkaton re-render check
  covers either way.
- D4 cosmetic residue left per scope: the "Expand all tags" button
  still renders above the aegislash CMP-First table with zero tag
  cells (dead control); one-line follow-up if wanted.
- New-test expected HTML values assume `render_mirror_slayer_html`
  accepts the synthetic-kwargs path without an AnalysisContext
  (verified by signature read, not execution); pad synthetic rows
  rather than weaken assertions if the table loop needs more keys.

Verification: per `renderer-D1-D4.md` — replay re-renders of
tinkaton-UL (D1: 6 unique tier names, exactly one "Tinkaton Mirror
Atk") and aegislash-shield (D4: zero `<b>0/0</b>`, zero
`>Anchors</th>`); D3 gap-count line varies. Re-render only the 4
tinkaton-ultra-league pages for D1.

### 2.2 renderer-D2-D5 (READY)

D2 option (a) per Michael's recorded decision in the redive prompt
(narrative-polish gate already passed): drop the Top-Mirror CMP column
from Slayer Builds tables + saturated-flatness note + within-archetype
atk percentile. D5: ghost-tier hover/badge multi-tier listing +
identical-membership annotation in engine.js. Notes:
`renderer-D2-D5.md`. Verified: standalone, the 3-command order, and
the full five-patch stack all apply cleanly; py_compile + node --check
pass; all four synthetic tests pass in every state.

**Apply order (mandatory, conflicts with D1-D4 otherwise):**

    git apply userdata/fix_packets_2026-06-13/renderer-D1-D4.patch        # (done in 2.1)
    git apply --exclude=scripts/deep_dive_rendering.py userdata/fix_packets_2026-06-13/renderer-D2-D5.patch
    git apply userdata/fix_packets_2026-06-13/renderer-D2-D5.rebased-after-D1-D4.rendering-only.patch

(The rebased rendering-only patch is content-identical to the
standalone D2 hunks — diff-of-diffs clean. If D1-D4 were ever skipped,
plain renderer-D2-D5.patch alone applies on clean HEAD.)

Apply-time nits from the review: fix the stale a73d855 references in
the packet header; the note line prints 2dp-flat constants at 0dp;
`grep -c` exits 1 on count 0, so do NOT `&&`-chain the expect-0
verification greps.

Open / Michael decisions:

- Atk %ile denominator under `--iv-floor`/`--species-iv-floor` uses
  the dive's swept (post-floor) space, not literal 4096 — matches
  every other per-page surface; confirm.
- `docs/concepts.md` (~line 76 prose + ~283 example table) still shows
  the old slayer-table Top-Mirror column — deliberate omission; small
  follow-up doc edit after applying.
- AF sort key still ranks by top_mirror_cmp first (constant in
  practice, so attack decides) — behavior-preserving; atk-first is a
  separate decision.
- Mirror Wins flatness defined at display precision (frac_wins 1dp) on
  purpose; <0.05 expected-wins differences count as flat.
- Top IVs summary table's own Top-Mirror CMP % column (genuinely
  varying) and overlayFill primary-tier coloring intentionally
  unchanged — flag if either should fold in.
- AF/CF card description copy ("reported once in the table note rather
  than per row") is Claude-drafted; adjust wording pre-re-render if
  desired.

Verification: per `renderer-D2-D5.md` — spot-check jumpluff GL
(120/120 slayer cells 100% and 15.0/27 pre-fix supports the flatness
premise), then one-dive verify before any batch re-render.

---

## Phase 3 — Selective re-dive screen

Run `userdata/redive_prompt_2026-06-13.md` steps 2-6 verbatim once
Phases 1-2 are committed. Summary of its gates:

1. Re-verify: audit_oracle_harness + full 3,420-cell grid re-run
   (>= 3,300 exact, all 30 winner flips resolved; investigate anything
   that moved the wrong way).
2. Three-part screen of the 44 overnight blobs: (a) closed-form
   shadow-CMP straddle screen (pure stat math, no sims — flag pairs
   where exactly one side is shadow and folded-vs-unfolded CMP
   ordering differs over the focal atk range); (b) old-vs-new engine
   worktree diff via a matchup-web-style all-pairs sweep; (c)
   conservative moveset flags (SUPER_POWER defenders + the 10
   incoming-gate-exposed moves, minus DRAGON_ASCENT per packet #1's
   correction) where (b) shows deltas. **Also fold in the shadow-cmp
   packet's draw-handling audit (winner=None → 0.5 expected wins)
   before re-diving any shadow species.**
3. Produce the per-species KEEP/REDIVE table with evidence. **Show
   Michael and WAIT for his OK before launching any dive.**
4. Re-dives: serial, `--reserve-cpus 1`, full website config, watch
   command on each start. Forretress-shadow: handle the Bug Bite
   question per `userdata/tournament_iv_report_2026-06-12.html`.
   Energy-scan SENSITIVE species: ask per-species about
   `--energy-lead on`.
5. Replay-re-render KEEP species for renderer parity; one consolidated
   publish at the end; push nod-gated.
6. Coordinate with the gobattlekit session: engine-vintage table of
   exactly which species were re-dived; don't touch thresholds/*.toml
   without coordinating (43 untracked threshold TOMLs are sitting in
   the working tree from that effort).
