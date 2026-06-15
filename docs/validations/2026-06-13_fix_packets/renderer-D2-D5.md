# Fix packet: renderer-D2-D5 (drafted 2026-06-12, apply 2026-06-13 post-batch)

Patch file: `userdata/fix_packets_2026-06-13/renderer-D2-D5.patch`
(verified `git apply --check` clean against HEAD `56fd106` — i.e. after
tonight's incoming-gate `847dd99` and bestcm-superpower `56fd106`
landings, which touch only `src/gopvpsim/battle.py`; the original
"a73d855" header was stale per the adversarial review. Repo files
untouched — patch was built from /tmp copies; rebase re-verification
ran in detached scratch worktrees under /tmp).

Evidence: `userdata/signal_loss_verified_findings_2026-06-12.md` D2 + D5 +
P3, and the DECISION block at its end (Michael 2026-06-12: D2 = option (a)).

## What the patch does

### D2 — Slayer Builds tables (option (a))

1. **Per-row "Top-Mirror CMP %" column removed** from both archetype
   tables (`render_mirror_slayer_html`, scripts/deep_dive_rendering.py).
   It was structurally 100% on all 910 visible rows / full membership of
   all 91 tables in all 20 dives (top-50-by-avg-score cohort is
   bulk-weighted; archetype membership is atk-gated).
2. **One saturated-note line per table**, mirroring the saturated-anchor
   note pattern (deep_dive_rendering.py:2654-2675): "Mirror metrics:
   every build in this table CMPs 100% of the top-50 mirror cohort; ...".
   Defensive branch: if the metric ever varies, the note reports the
   min-to-max range instead (column stays retired either way).
3. **Nash CMP % + Mirror Wins flatness audit (P3) fixed dynamically**:
   each column now renders only when it actually varies across the
   table's FULL membership (`cat_ivs`, not just the 100 emitted rows).
   A constant folds into the same note line ("Nash CMP % is 100% for
   every build; Mirror Wins is 15.0/27 for every build"). Flatness
   definition is display-precision on purpose: Nash rounded to 2dp,
   Mirror Wins keyed on (frac_wins rounded to 1dp, n_pairs).
4. **Replacement discriminating column: "Atk %ile"** — exact computation
   (scripts/deep_dive_slayer.py `build_slayer_archetypes`):

       atk_pctile(i) = 100 * |{ j in swept IV space :
                                round(atk_j, 2) <= round(atk_i, 2) }|
                            / |swept IV space|

   implemented as `_cmp_pct(r['atk'], sorted(round(r['atk'],2) for r in
   results))` — bit-identical tie semantics to the existing CMP%
   columns (both sides rounded to 2dp, `bisect_right` so ties count as
   beaten, focal included in its own denominator). The denominator is
   the dive's swept `results` list (= 4096 IV combos on a no-floor dive;
   post-floor space when `--iv-floor`/`--species-iv-floor` is set, i.e.
   the same space every other table/scatter on the page describes).
   Varies within any atk-gated archetype by construction (members differ
   in raw atk). Rendered as `{v:.2f}%` (steps of 100/4096 ~ 0.0244 stay
   visible near the top). `top_mirror_cmp` is STILL computed on every
   row — it remains the Anchors-First sort key and feeds the note line;
   only the rendered column is gone.
5. AF card description tweaked: "Ranked by Top-Mirror CMP % (reported
   once in the table note rather than per row), then attack."

### D5 — ghost-tier surfaces

1. **Hover "Tier:" line** (deep_dive_engine.js:357-358) now lists ALL
   memberships from `DATA.ivAllTiers` (comma-joined), mirroring
   Python-side `tier_badge_html` (deep_dive_rendering.py:566-581).
   Fallback to primary `ivTiers` for older dives without `ivAllTiers`.
2. **Summary-table tier badge** (deep_dive_engine.js:~2439/2498) emits
   one badge per `ivAllTiers` membership, same fallback.
3. **Identical-membership annotation at tier-derivation time**: new
   `_annotate_identical_tier_membership(data_obj)` in scripts/deep_dive.py
   (next to `_recompute_tier_assignments`), called from
   `generate_analysis_sections` immediately AFTER `_rename_plotly_tiers`
   so the referenced name is the final display name. Sets
   `tiers[ti]['identicalTo'] = <earliest tier with the same frozenset
   membership>`; idempotent (stale keys cleared each call);
   empty-membership tiers never flagged. Consumed in
   deep_dive_engine.js trace build (~line 1645): legend name becomes
   "X (same IVs as Y)" so fully-coincident-marker occlusion is
   explained. `identicalTo` rides into the page via the normal
   `DATA = json.dumps(data_obj)` at deep_dive.py:3657, which runs after
   `generate_analysis_sections`; `tierNames` (deep_dive.py:3760) and
   `DATA.tiers` index-align because both come from the final
   `data_obj['tiers']`.

Explicitly NOT touched (out of this packet's spec): `overlayFill`
coloring (engine.js:1742) stays primary-tier; the Top IVs summary
table's own "Top-Mirror CMP %" column (`_computeTopMirrorCmpPct`) is a
different, genuinely-varying surface and is unchanged.

## Files in the diff

| File                           | Change                                                              |
| ------------------------------ | ------------------------------------------------------------------- |
| scripts/deep_dive_slayer.py    | `atk_pctile` row key (+docstring)                                   |
| scripts/deep_dive_rendering.py | column removal, flatness gate, note line, Atk %ile column, AF desc  |
| scripts/deep_dive.py           | `_annotate_identical_tier_membership` + call site after tier rename |
| scripts/deep_dive_engine.js    | hover multi-tier, badge multi-tier, legend identicalTo annotation   |
| tests/test_slayer_smoke.py     | atk_pctile assertions + 2 new tests (see below)                     |

## Test plan

Pre-verified tonight WITHOUT touching the repo or running pytest:
`python -m py_compile` on all patched .py files, `node --check` on the
patched engine.js, and a /tmp driver re-running the new tests' logic
against the patched copies — all passed (atk_pctile = 100.0 and
66.6667 on the synthetic 3-IV space; flat table drops Nash/MW columns
and emits the note; varying table restores them; D5 annotation sets /
clears / idempotent).

Existing tests that cover the touched code (run tomorrow, post-batch):

- `tests/test_slayer_smoke.py::test_build_slayer_archetypes_smoke` —
  extended in the patch with static expectations: `cf[0]['atk_pctile']
  == 100.0`, `cf[1]['atk_pctile'] == approx(200/3)` (atks 110/105/95 ->
  3/3 and 2/3 of the space), same pair re-asserted on the AF rows.
- `tests/test_slayer_smoke.py::test_build_slayer_archetypes_auto_anchor_selectivity`
  — unchanged; rows gain a key, assertions unaffected.
- `tests/test_slayer_smoke.py::test_slayer_iteration_smoke` — unchanged
  (runs ~10-15 s of sims; post-batch only).
- `tests/test_battle.py` — untouched surface (no src/gopvpsim changes),
  run as the usual regression gate.

New tests added by the patch:

- `test_render_mirror_slayer_flatness_gate` — renders
  `render_mirror_slayer_html` on a synthetic 2-row CMP-First table.
  Flat case asserts: no `Top-Mirror CMP&nbsp;%` anywhere, `Atk&nbsp;%ile`
  header present, cells `100.00%`/`99.98%`, note contains "every build
  in this table CMPs 100% of the top-50 mirror cohort", "Nash CMP&nbsp;%
  is 100% for every build", "Mirror Wins is 15.0/27 for every build",
  and no `>Nash CMP&nbsp;%</th>` / `>Mirror Wins</th>` headers. Varying
  case (nash 100 vs 50, frac 15.0 vs 12.5) asserts both headers return.
- `test_identical_tier_membership_annotation` — Alpha/Beta identical
  membership -> `Beta['identicalTo'] == 'Alpha Atk'`; distinct Gamma's
  stale key cleared; second call idempotent.

No fixture refreshes needed: no PvPoke-ground-truth fixtures touch these
surfaces.

## Blast radius

- **Sim/caches: zero.** Only `scripts/` + `tests/` are touched; scripts
  are outside the sweep/slayer engine hash (slayer_cache.py:24 comment)
  and CACHE_VERSION is untouched. `build_slayer_archetypes` and both
  renderers run per dive-render from cached sweep data — no resim.
- **D2: all 20 dives, all 91 Slayer Builds tables** (index + alt-moveset
  pages). Every table loses the Top-Mirror column, gains Atk %ile and
  the note line; Nash CMP % / Mirror Wins columns disappear wherever
  flat (confirmed flat at least in the jumpluff AF table; the gate
  decides per table at render time).
- **D5 hover/badge: every dive page** (engine.js is embedded per page),
  but visible change only on IVs with >1 tier membership. Legend
  annotation fires only on exact-duplicate memberships — confirmed
  candidates: oinkologne-great-league m3 (t2+t3 both 56-member),
  possibly ninetales-great-league and tinkaton-ultra-league (D1
  duplicates). Jumpluff t2 (primary=0, all=15) may be a strict subset
  of an earlier tier rather than identical — hover/badge fix covers it
  regardless.
- HTML refresh requires re-render; per the retrofit-via-redive policy
  do ONE consolidated re-render together with the D1/D3/D4 packets
  (ordering per the findings doc: D6, D1, D3, D4, then D2, then D5).

## Verification commands (tomorrow, after the overnight batch finishes)

    cd ~/coding/MGLPoGo/pogo-simulator
    git apply --check userdata/fix_packets_2026-06-13/renderer-D2-D5.patch
    git apply userdata/fix_packets_2026-06-13/renderer-D2-D5.patch
    node --check scripts/deep_dive_engine.js
    python -m pytest tests/test_slayer_smoke.py -q
    python -m pytest tests/test_battle.py -q

Pilot re-dive (small first, per policy; jumpluff GL shows both D2 and
D5 symptoms — reuse the fully-resolved command embedded in the existing
page's "equivalent command" block, add `--reserve-cpus 1`, offer the
`watch -c -n 5 scripts/chain_status.py ...` line). Then on the rendered
page:

    P=userdata/website/jumpluff-great-league/index.html
    grep -c 'Top-Mirror CMP&nbsp;%</th>' $P                 # expect 0
    grep -c 'Atk&nbsp;%ile</th>' $P                         # expect >= 2 (AF + CF)
    grep -c 'CMPs 100% of the top-50 mirror cohort' $P      # expect >= 1
    grep -c '>Nash CMP&nbsp;%</th>' $P                      # 0 where flat (AF confirmed flat)
    grep -o 'Mirror Wins is [0-9.]*/[0-9]* for every build' $P | head
    grep -c '"identicalTo"' userdata/website/oinkologne-great-league/index_m3*.html  # expect >= 1 if t2/t3 truly identical

Browser spot-check (`open $P`, default browser): hover a point inside
an overlapping tier — "Tier:" line lists every membership; Top IVs
summary table shows stacked badges; scatter legend shows
"(same IVs as ...)" where the annotation fired. Then the consolidated
batch re-render + commit per the plan-file session-end policy.

## Open questions / follow-ups

1. **Atk %ile denominator under IV floors**: uses the dive's swept
   space (post `--iv-floor`/`--species-iv-floor`), not a literal 4096.
   Chosen because it matches every other per-page surface; flag to
   Michael if he wants the literal full space instead.
2. **docs/concepts.md** lines ~76 and ~283 still describe/illustrate
   the old Top-Mirror column in slayer tables — deliberate omission
   from the code patch; needs a small doc edit after the patch lands.
3. **D1 interaction**: if the tinkaton-UL rename collision is NOT fixed
   first, two same-named tiers with identical membership would render a
   legend like "Tinkaton Mirror Atk (same IVs as Tinkaton Mirror Atk)".
   The agreed implementation order (D1 before D2/D5) avoids this; keep
   that order.
4. **AF sort key** still ranks by top_mirror_cmp first (constant, so
   attack decides in practice). Left unchanged to keep this packet
   behavior-preserving on ordering; simplifying to atk-first is a
   separate decision.
5. **engine.js "About these metrics" blurb** (summary table) describes
   Top-Mirror CMP % for the Top IVs table, which keeps its column —
   no change needed, but worth a read-through during review since the
   slayer-table column is now note-only.

## IMPORTANT: merge coordination with renderer-D1-D4.patch

The sibling packet `renderer-D1-D4.patch` (its D4 hunks) rewrites the
SAME header/row region of `render_mirror_slayer_html` that this packet
touches. The two patches conflict on `scripts/deep_dive_rendering.py`
only — verified tonight in a scratch tree:

- D1-D4 applied first, then this packet WITHOUT the rendering file
  (`git apply --exclude=scripts/deep_dive_rendering.py
  renderer-D2-D5.patch`): applies cleanly.
- The pre-resolved rendering diff is provided as
  `renderer-D2-D5.rebased-after-D1-D4.rendering-only.patch` — verified
  to apply cleanly ON TOP of D1-D4 (and to fail on clean HEAD, as it
  should). The merged file py_compiles, and a combined smoke render
  confirmed the D2 flatness gate and D4 anchors-column suppression
  coexist (a no-anchor flat table emits neither the Anchors column nor
  the Top-Mirror/Nash/Mirror Wins columns, with the note line present).

So tomorrow, apply in this order (matches the findings-doc ordering):

    git apply userdata/fix_packets_2026-06-13/renderer-D1-D4.patch
    git apply --exclude=scripts/deep_dive_rendering.py userdata/fix_packets_2026-06-13/renderer-D2-D5.patch
    git apply userdata/fix_packets_2026-06-13/renderer-D2-D5.rebased-after-D1-D4.rendering-only.patch

If D1-D4 is NOT applied for some reason, use the plain
`renderer-D2-D5.patch` alone (re-verified clean against HEAD `56fd106`).

## Adversarial review (2026-06-12, independent agent)

**Verdict: READY** (with the corrections/notes below; none blocking).

Verified independently, repo untouched (all apply/compile/test work done
in a /tmp scratch tree built from `git archive HEAD`):

1. **Baseline drift — packet metadata is stale, patch is fine.** The
   packet header says "verified against HEAD a73d855", but HEAD is now
   `f4a3b3e` (6 commits landed today: energy-lead axis c5d2aa3, matchup
   web, etc., touching deep_dive.py / deep_dive_rendering.py /
   deep_dive_engine.js). The patch's blob indices (engine.js
   `ac28b3a`, rendering `9306ccf`) match f4a3b3e, so it was actually
   built on the NEWER tree; `git apply --check` passes on current HEAD
   (re-confirmed). The energy-axis changes are in `parse_mode`/
   `compose_mode`/boundary-bullet regions, nowhere near the patched
   hunks — no semantic interaction found. Correct the header line; and
   note more sessions are committing tonight, so re-run `git apply
   --check` first thing tomorrow (the verification commands already do).
2. **Apply-order matrix re-verified in scratch tree.** (a) standalone
   D2-D5 on HEAD: clean; (b) the exact 3-command order (D1-D4 →
   D2-D5 `--exclude=scripts/deep_dive_rendering.py` → rebased
   rendering-only): clean; (c) full five-patch stack (incoming-gate,
   bestcm-superpower, shadow-cmp, D1-D4, D2-D5 3-command form): all
   apply cleanly. Every state py_compiles (deep_dive, rendering,
   slayer, battle, pokemon, formchange) and `node --check` passes.
3. **Rebased rendering patch is content-identical to the standalone
   D2 hunks.** diff-of-diffs (base→standalone vs D1-D4→merged) shows
   identical added/removed content lines, only positional offsets.
   Not a divergent re-edit.
4. **New tests pass on standalone, merged, AND five-patch states** —
   ran `test_build_slayer_archetypes_smoke`,
   `test_render_mirror_slayer_flatness_gate`,
   `test_identical_tier_membership_annotation`,
   `test_build_slayer_archetypes_auto_anchor_selectivity` via a bare-
   python driver (no pytest runner, no sims, no rankings load). All
   green in all three states.
5. **Consumer sweep, Python side.** `build_slayer_archetypes` callers:
   deep_dive.py:5149 (passes the full sweep `results`, so the Atk %ile
   denominator claim — post-floor swept space — is correct) and the
   debug-log table at deep_dive.py:5181, which still reads
   `top_mirror_cmp` (still computed — fine, though it logs CMP%, not
   the new column; debug-only, acceptable). `render_mirror_slayer_html`
   has exactly one production caller (rendering.py:3455). No
   article/comparison script consumes `top_mirror_cmp` rows.
6. **Consumer sweep, JS side.** All `ivTiers` primary-only surfaces:
   hover (357), legend traces (1645), overlayFill (1742), summary
   badge (2439/2498). Patch covers hover/legend/badge; overlayFill
   exclusion matches the findings-doc D5 fix scope (item 6 lists only
   hover/badge + annotation). `tier_badge_html`
   (rendering.py:566-581) parity claim verified — it does iterate
   `ivAllTiers` with the same fallback shape. `DATA.tiers` IS
   serialized (json.dumps(data_obj) at ~3657, after
   generate_analysis_sections), and `tierNames` comes from
   `final_tier_info = data_obj.get('tiers', ...)` — index alignment
   claim verified.
7. **Annotation ordering verified.** Insertion is after the
   `_rename_plotly_tiers` block in generate_analysis_sections; the
   later safety-net rename at ~3606 is a no-op on names already
   renamed with the same flavors (checked `_rename_plotly_tiers`:
   rename and HP-sync both guard against re-application), so
   `identicalTo` can't reference a pre-rename name on any current
   path. generate_analysis_sections is always computed per call (the
   fa34f39 cross-file cache was removed), so split-moveset files get
   the annotation too.
8. **Cache/engine-hash: confirmed zero impact.** `engine_hash()`
   (sweep_cache.py:55) hashes only src/gopvpsim battle/_dp_jit/moves/
   formchange/pokemon — no scripts/ files. `build_slayer_archetypes`
   is post-iteration classification in the parent process, not worker
   code, so the slayer CACHE_VERSION worker-change standing rule does
   not apply. No bump needed.
9. **Spot-check of the structural-100% premise.** jumpluff GL page:
   all 120 `dd-gain` slayer cells are `100%` and all 120 Mirror Wins
   cells are `15.0/27` — consistent with the findings doc and with
   the flatness gate dropping Nash/MW there. Also confirmed
   `all_scores` covers every focal IV (deep_dive_slayer.py scores
   `range(n_focal)` each round), so the `n_pairs == 0` exclusion in
   `mw_vals` is a theoretical edge, not a real mis-note risk.
10. **Doc drift check.** Besides the already-flagged
    docs/concepts.md:76/283, the Reader's Guide
    (guides deep-dive-scatter) mentions Top-Mirror CMP % only for the
    Top IVs table, which keeps its column — no guide edit needed.
    The verification grep `'Top-Mirror CMP&nbsp;%</th>'` is safe: the
    engine.js summary-table header uses a plain space, so the only
    `&nbsp;` `</th>` hits are the two retired slayer headers (counted
    2 on the current jumpluff page → 0 post-patch is the right
    expectation).

Minor nits (non-blocking): (a) the note line prints the 2dp-flat
constant with `:.0f`, so a hypothetical flat 99.96% would display as
"100%" — currently unreachable (value is exactly 100.0 everywhere);
(b) `grep -c` exits non-zero on a 0 count, so don't chain the
"expect 0" verification greps with `&&`; (c) fix the stale "HEAD
a73d855" references in this file's header when applying.

## Rebase onto regenerated renderer-D1-D4 (2026-06-12, late — v2)

`renderer-D1-D4.patch` was regenerated per its NEEDS-WORK review
(adds the D3 clusterGaps twin fix in `scripts/deep_dive.py`
~2813-2819 using `rendering.MIN_SIG_GAP`, plus the Experimental-methods
prose floor mention at rendering ~3160). Same filename, so the
3-command apply order above is unchanged verbatim. This packet was
re-verified against that v2 at HEAD `56fd106`:

1. **Companion regenerated against the v2 base.**
   `renderer-D2-D5.rebased-after-D1-D4.rendering-only.patch` was
   rebuilt as the `git diff` of `scripts/deep_dive_rendering.py`
   between (HEAD `56fd106` + D1-D4-v2) and (that + the D2 rendering
   hunks). Hunk content is line-for-line identical to the previous
   companion (diff-of-diffs clean modulo the `index` line, which now
   names the v2-applied base blob `7da7cda`). The v2's extra rendering
   hunks (prose at ~3160) sit past every companion hunk (max ~2840),
   so no positional interaction exists.
2. **3-command chain re-verified** in a fresh detached worktree of
   `56fd106` under /tmp, with `git apply --check` before every apply:
   D1-D4-v2 → D2-D5 `--exclude=scripts/deep_dive_rendering.py` →
   rebased companion. All three check + apply clean. Negative control:
   the companion alone on clean `56fd106` fails (as it must — it
   needs the D4 context).
3. **Compile gates on the final state:** `python -m py_compile` on
   deep_dive.py / deep_dive_rendering.py / deep_dive_slayer.py and
   `node --check` on deep_dive_engine.js — clean. No pytest run
   (overnight batch still running); the post-batch test plan above is
   unchanged.
4. **deep_dive.py interaction checked:** v2's new clusterGaps hunk
   (~2813) is disjoint from this packet's deep_dive.py hunks (~1857
   annotation helper, ~2422 call site) — applies with offsets only.
5. **Open question 2 (docs/concepts.md drift) now has a drafted
   edit:** `renderer-D2-D5.concepts-followup.patch` (same directory),
   built from the patched tree and `git apply --check`-verified on
   clean `56fd106` (docs are untouched by the code patches, so it
   applies independently; land it in the same commit as this packet).
   It updates the Anchors-First bullet (~line 74: Top-Mirror CMP %
   now lives in the mirror-metrics note line), the example sketch
   (~line 283: Atk %ile column + note line), adds a paragraph
   defining the note line and Atk %ile semantics, folds in the D4
   Anchors-column-omission caveat on the CMP-First sentence, and
   tweaks "columns" → "metrics" in the Survivor-cohort paragraph
   (~line 37). `scripts/format_md.py` reports the result unchanged
   (idempotent).
