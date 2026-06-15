# Fix packet: renderer-D1-D4 (drafted 2026-06-12, apply 2026-06-13)

Combined renderer packet for findings D1, D3, D4 from
`userdata/signal_loss_verified_findings_2026-06-12.md`.
Patch: `renderer-D1-D4.patch` (same directory).

**REGENERATED 2026-06-12 (late)** per the adversarial review's
NEEDS-WORK verdict (review + regeneration notes at bottom). Verified
`git apply --check` clean against HEAD `56fd106` — i.e. AFTER tonight's
incoming-gate (`847dd99`) and bestcm-superpower (`56fd106`) landings;
both touch only `src/gopvpsim/battle.py`, no file overlap with this
packet. **Repo files were NOT modified** — the diff was generated from
/tmp copies. Do not apply while the overnight dive batch is running.

Cache safety: `sweep_cache._ENGINE_FILES` hashes only
`gopvpsim/{battle,_dp_jit,moves,formchange,pokemon}.py`. Neither
`scripts/deep_dive.py` nor `scripts/deep_dive_rendering.py` feeds the
engine hash, so applying this patch invalidates NO sweep/slayer caches.
The standing CACHE_VERSION rule (sweep v2 / slayer v3 bumps for
`scripts/` changes) covers worker/orchestration plumbing that alters
*computed* results; renderer-only changes like this packet do not need
a bump. All verification is replay-based re-render (no sims).

---

## D1 — duplicate "Tinkaton Mirror Atk" tier name

File: `scripts/deep_dive.py`, `_rename_plotly_tiers` (docstring + body,
lines 1721-1793 at `56fd106`; call sites 2381 and 3606 — the second is
the idempotent TOML-path re-run).

Root cause (refined during drafting, beyond the findings doc): each
flavor carries `tier_name` = the name of the tier it was derived from,
but the matcher ignored it and took the FIRST unclaimed tier within 0.1
of the stat cutoff in `plot_tiers` order. In tinkaton-ultra-league the
mirror flavor (cut 141.6328) hit the earlier "Gyarados Atk" tier
(141.6765, delta 0.044) and renamed it "Tinkaton Mirror Atk"; the synth
mirror tier (listed last, already carrying that name from
`_synthesize_mirror_tier`) was never claimed, leaving two tiers with
identical name + color (#bc8cff). No "Gyarados Slayer" flavor rescued
the tier (current pages show the synth tier with `original_name: None`,
i.e. never renamed — consistent with the Gyarados flavor being dropped
by signature dedup upstream).

Fix, two independent layers:

1. **Exact-name match first:** claim the unclaimed tier whose `name`
   (or `original_name`, for the idempotent TOML-path re-run) equals
   `flavor['tier_name']`; fall back to the existing 0.1 stat-tolerance
   scan only when no exact match exists. Also fixes latent ambiguity in
   m1 where "Walrein Atk" and "Walrein (Shadow) Atk" tiers share the
   identical attack cutoff 142.0753.
2. **Uniqueness guard:** before committing, skip the flavor entirely
   (no claim, no rename, no HP sync) if `new_name` is already carried
   by a *different* tier. HP-sync skip is deliberate: in the guard-hit
   case the stat-matched tier is the wrong tier, so syncing HP into it
   would be a second bug.

Statically verified TWICE. First on synthetic tiers (extracted the
patched function via `ast`, ran standalone): mirror-flavor-first,
reversed-order, guard-only (no tier_name match), and idempotent-re-run
cases all yield unique names with the synth tier keeping "Tinkaton
Mirror Atk". Second (regeneration pass) **against the real
tinkaton-ultra-league `DATA.tiers` extracted from the built
index.html** — the exact duplicate state documented in the findings
doc (6 tiers, 5 unique names, dup at attack 141.6765/141.6328, both
#bc8cff):

- Real flavor set, real tier order → exact-name layer routes the
  mirror flavor to the synth tier; Gyarados tier reverts to
  "Gyarados Atk"; 6 unique names.
- Guard-only (tier_name stripped so the exact layer can't fire): the
  0.1 stat scan latches onto the Gyarados tier exactly as in the bug,
  and the guard skips the rename — no duplicate.
- Idempotent double-run and reversed flavor order: same 6 unique names.
- Replay-on-stale-state caveat: re-running the function on a tiers
  list that ALREADY carries the old duplicate (as the 4 broken built
  pages do today) does not heal it in place — the exact layer claims
  the wrongly-renamed tier by name. This is irrelevant to the
  pipeline (tiers are rebuilt by auto-derive + synth before every
  rename) and is exactly why the fix path is a focused re-render,
  per the retrofit policy, not HTML surgery.

Expected post-fix values (statically derived from current built HTML):
tinkaton-ultra-league `DATA.tiers` on index/m1/m3/m4 keeps 6 tiers with
6 UNIQUE names; exactly one "Tinkaton Mirror Atk" (the synth tier,
attack 141.6328119239645); the attack-141.67649882051282 tier reverts
to its auto-derived name "Gyarados Atk" (no flavor claims it).
`DATA.pasteTiers` dedups for free (it unions plot tiers + flavors by
name). m2 (already 6 unique names) must be byte-stable modulo
timestamps.

## D3 — "5 significant gap(s)" constant

Files: `scripts/deep_dive_rendering.py` — `detect_clusters` (def at
line 2256 at `56fd106`), its single text-render call site in
`render_analysis_alpha_html` (line 2942) — AND `scripts/deep_dive.py`
— the inlined `clusterGaps` twin (lines 2776-2790 at `56fd106`), which
the original packet missed (review item 1).

Two stacked causes, FOUR changes (was two; regeneration added 3-4):

1. **Degenerate threshold:** with 4096 near-continuous averaged scores
   the median consecutive gap is ~0, so `> 3 * med` admitted 73-521
   gaps per scenario. New module constant `MIN_SIG_GAP = 1.0` (avg-score
   points on the 0-1000 battle-score scale); threshold becomes
   `max(3 * med, MIN_SIG_GAP)`. Chose the absolute floor over p99
   because p99 structurally admits ~the top 1% of 4095 gaps, so `sig`
   could never be empty and the "Smooth gradient" fallback would stay
   unreachable.
2. **Capped count:** `detect_clusters` now returns
   `(clusters, sig[:5], len(sig))`; the renderer prints the uncapped
   `n_sig_total` with a ` (top K used for clustering)` suffix only when
   truncation actually happened. Intro paragraph mentions the floor;
   fallback line becomes "Smooth gradient (no significant gaps)."
   (the old text named the now-incomplete 3x-median rule).
3. **clusterGaps twin (NEW, review item 1):** `deep_dive.py` 2776-2790
   inlines the same gap rule (`g > 3 * median_gap`, quartile gate,
   `sig[:5]`) to build `data_obj['clusterGaps']` — the horizontal gap
   lines the JS draws on the scatter plot. Without the twin fix, a
   smooth-gradient scenario would say "0 significant gaps" in the text
   while the plot still drew up to 5 lines from the degenerate
   threshold, on every dive page. Now
   `gap_thresh = max(3 * median_gap, rendering.MIN_SIG_GAP)` — the
   constant is imported via the existing module-level
   `import deep_dive_rendering as rendering` (deep_dive.py:81), no new
   import needed. Pre-existing cosmetic divergence NOT touched: the
   twin keeps its first-5-in-rank-order cap while `detect_clusters`
   takes top-5-by-gap-size, and its quartile gate is off-by-one
   stricter; both are unchanged from the old code and only matter when
   >5 significant gaps survive the floor.
4. **Stale methods prose (NEW, review item 2):** the "Cluster
   detection (gap analysis)" entry in the hidden Experimental-methods
   `<dl>` (`render_analysis_methods_html`, ~line 3160) still described
   the pure 3x-median rule; it now mentions the absolute floor. The
   block is an f-string, so `{MIN_SIG_GAP:g}` interpolates the live
   constant — no drift if the knob is retuned.

Statically verified on the extracted patched function: smooth uniform
4096-score distribution → `n_sig == 0`, 1 cluster, fallback path taken;
synthetic distribution with 2 real breaks (18- and 7-point gaps at
ranks 200/500, top-quartile) → `n_sig == 2`, 3 clusters, boundaries at
200 and 500. Regeneration pass additionally verified **text/plot
agreement**: the patched twin logic (run verbatim on the same two
distributions) emits 0 gap lines on the smooth case and exactly 2
lines (Y = 880.0, 870.0, the scores just below each break) on the
2-break case, matching `detect_clusters`' `n_sig`.

Only text call site is rendering line 2942 (verified by grep; no test
or script imports `detect_clusters`); only plot producer is the
deep_dive.py twin.

## D4 — vacuous "0/0 -" Anchors column

File: `scripts/deep_dive_rendering.py`, `render_mirror_slayer_html`
(def at 2425 at `56fd106`) per-category table loop (~lines 2690-2780
post-patch).

`show_anchors_col = any(r.get('n_counted_parents', 0) > 0 for r in
emitted)` gates both the `<th>Anchors</th>` header and the per-row
`<td class="dd-anchor-tags-cell">` cell (built as `anchors_td`, empty
string when suppressed). Gating on row data rather than the category
name automatically applies only to CMP-First in practice: Anchors-First
is already hidden entirely via `if not cat_ivs: continue` when no
counted anchors exist. `_anchor_tags_cell` is now only called when the
column renders.

Known cosmetic residue (NOT fixed, out of scope): the "Expand all tags"
button still renders above the table even when no tag cells exist
(dead control on aegislash-shield). One-line follow-up if Michael
wants it.

---

## Test plan

Existing coverage: **none.** Grep confirms no test references
`_rename_plotly_tiers`, `detect_clusters`, `render_mirror_slayer_html`,
or the "significant gap" string. `tests/test_slayer_signal_loss.py`
covers the adjacent `_parent_clear_stats`/`_anchor_tags_cell` helpers
and is unaffected (helpers unchanged; only their call site is gated).
`tests/test_signature_dedup.py` is adjacent to the D1 root cause but
tests the dedup itself, not the rename.

New tests — add `tests/test_renderer_d1_d3_d4.py` using the
import-by-path pattern from `test_slayer_signal_loss.py` (and
`importlib.util.spec_from_file_location` for `deep_dive.py`, stubbing
`_recompute_tier_assignments` is unnecessary since tests avoid the
HP-sync path):

D1 (call `_rename_plotly_tiers` directly; tiers listed Gyarados-first,
synth-mirror-last, cutoffs from the real tinkaton case):

| case                                                                                      | expected                                                          |
| ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| mirror flavor (tier_name + name "Tinkaton Mirror Atk", cut 141.6328) then Gyarados flavor | names == ['Gyarados Slayer', 'Tinkaton Mirror Atk']               |
| same flavors, reversed order                                                              | same two unique names                                             |
| single flavor, tier_name absent from tiers, rename would dup the synth name (guard-only)  | names == ['SomeAutoName', 'Tinkaton Mirror Atk'] (rename skipped) |
| idempotent re-run: Gyarados tier pre-renamed with original_name set                       | names unchanged == ['Gyarados Slayer', 'Tinkaton Mirror Atk']     |

D3 (call `detect_clusters` directly; `data` dict needs only
ivAtk/ivDef/ivHp lists):

| case                                                                     | expected                                        |
| ------------------------------------------------------------------------ | ----------------------------------------------- |
| 4096 sorted uniform scores in [500, 550] (seeded)                        | `n_sig == 0`, `top5 == []`, 1 cluster           |
| 200 @ 900-step-0.01, 300 @ 880-..., 3596 @ 870-... (gaps 18.01 and 7.01) | `n_sig == 2`, boundaries {200, 500}, 3 clusters |
| 3-tuple unpack contract                                                  | `clusters, top5, n_sig = detect_clusters(...)`  |

D3-twin (the clusterGaps builder is inlined in the orchestrator, so no
direct unit test; covered by (a) the replay-output consistency check
below and (b) a `MIN_SIG_GAP` import-contract assertion in the new test
file: `rendering.MIN_SIG_GAP` exists, is `>= 1.0`, and appears in the
clusterGaps block of `deep_dive.py`'s source — a cheap tripwire against
the two copies drifting again).

D4 (call `render_mirror_slayer_html(slayer_iter_result=..., data_obj=...)`
with a synthetic result: `final` non-empty, `resolved_anchors=[]`,
`categories={'CMP-First Slayer': rows}`, rows carrying
iv/atk/def_/hp/avg_score and `n_counted_parents=0`):

| case                                                           | expected                                                     |
| -------------------------------------------------------------- | ------------------------------------------------------------ |
| all rows n_counted_parents == 0                                | `'>Anchors</th>' not in html` and `'<b>0/0</b>' not in html` |
| control: one row with n_counted_parents=1, n_parents_cleared=1 | Anchors `<th>` present, `<b>1/1</b>` present                 |

Fixture refresh: none — no stored fixture encodes tier names, gap
counts, the clusterGaps array, or the anchors column (checked tests/ by
grep).

---

## Blast radius

- **Caches/sims:** zero. Engine hash untouched; renderer-only (see
  standing CACHE_VERSION rule note in the header — no bump needed).
- **D1:** rename logic runs on every dive, but output changes only
  where a flavor stat-matched a foreign tier or a rename would dup.
  Confirmed-affected: tinkaton-ultra-league (index, m1, m3, m4; NOT
  m2). Possible silent re-routing on pages with identical-cutoff tier
  pairs (tinkaton-UL m1's Walrein pair resolves to the same names by
  order, so expected no-op). The exact-name layer can also re-route
  the HP sync (`stamina` write + `_recompute_tier_assignments`) to a
  different tier than the old stat scan picked, so affected pages can
  change in tier `stamina`/`ivTiers`, not just names — the catch-all
  scan below diffs (name, attack, defense, stamina) tuples for exactly
  this reason (review item 3).
- **D3:** all 20 dives, 9 scenario blocks per page — the 423
  "5 significant gap(s)" lines change, and because `sig` shrinks, the
  Cluster Analysis boundaries/cluster tables in the same section can
  regroup. NEW with the twin fix: `DATA.clusterGaps` shrinks on every
  page wherever `3 * median_gap < 1.0`, so scatter plots lose their
  noise-threshold horizontal lines (plot now agrees with the text).
  The hidden Experimental-methods prose changes on every page.
  Nothing else consumes `detect_clusters` or `clusterGaps`.
- **D4:** aegislash-shield-great-league only (sole dive with zero
  counted parents); future anchor-less dives inherit the gate. All
  other dives' slayer tables must be byte-identical for this hunk.
- **Out of scope, untouched:** D2 (CMP% saturation — gated on
  Michael), D5 (engine.js hover), the dead "Expand all tags" button
  residue noted above.
- **Packet sequencing:** `renderer-D2-D5.rebased-after-D1-D4.
  rendering-only.patch` now exists and was re-verified (regeneration
  pass) to apply cleanly ON TOP of this regenerated patch — apply
  D1-D4 first, always.

## Verification commands (tomorrow, after the batch finishes)

```
cd ~/coding/MGLPoGo/pogo-simulator
git apply --check userdata/fix_packets_2026-06-13/renderer-D1-D4.patch
git apply userdata/fix_packets_2026-06-13/renderer-D1-D4.patch
python -m pytest tests/test_renderer_d1_d3_d4.py tests/test_slayer_signal_loss.py -q   # after writing the new tests
```

Replay re-renders (no sims; render_dive_html -> generate_interactive_html
-> generate_analysis_sections re-runs the patched rename):

```
python scripts/replay_analysis.py userdata/replay/20260611_210652_Tinkaton_ultra.replay.pkl.gz --html /tmp/tink_ul_d1.html
python scripts/replay_analysis.py userdata/replay/20260611_212341_Aegislash_Shield_great.replay.pkl.gz --html /tmp/aegis_d4.html
```

Checks on the outputs:

```
# D1: 6 unique tier names, exactly one Tinkaton Mirror Atk
python -c "import re,json; h=open('/tmp/tink_ul_d1.html',encoding='utf-8').read(); t=json.loads(re.search(r'\"tiers\":\s*(\[.*?\])\s*,\s*\"',h,re.S).group(1)); names=[x['name'] for x in t]; print(names); assert len(set(names))==len(names)==6 and names.count('Tinkaton Mirror Atk')==1"
# D3: gap-count line varies / floor active
grep -o '[0-9]\+ significant gap(s)[^<]*' /tmp/tink_ul_d1.html | sort | uniq -c
grep -c 'Smooth gradient' /tmp/tink_ul_d1.html   # may be 0; just confirm no crash + counts differ from constant 5
# D3-twin: text and plot agree — every scenario block reporting 0 significant
# gaps must have an empty clusterGaps list, and no scenario may carry more
# gap lines than its reported significant-gap count
python - <<'EOF'
import re, json
h = open('/tmp/tink_ul_d1.html', encoding='utf-8').read()
cg = json.loads(re.search(r'"clusterGaps":\s*(\{.*?\})\s*,\s*"', h, re.S).group(1))
counts = [int(x) for x in re.findall(r'(\d+) significant gap\(s\)', h)]
lines_per_scn = [len(s) for v in cg.values() for s in v]
print('text gap counts:', sorted(set(counts)), '| plot line counts:', sorted(set(lines_per_scn)))
assert not (0 in counts and all(lines_per_scn)), 'text says smooth but every plot scenario draws lines'
assert max(lines_per_scn, default=0) <= 5
print('clusterGaps consistency OK')
EOF
# D4: no vacuous anchors column on aegislash-shield
grep -c '<b>0/0</b>' /tmp/aegis_d4.html          # expect 0
grep -c '>Anchors</th>' /tmp/aegis_d4.html       # expect 0
grep -c 'CMP-First Slayer' /tmp/aegis_d4.html    # expect >0 (table still renders)
```

Then re-dive/re-render the affected pages canonically (retrofit policy:
focused re-dive, not HTML surgery) and run the catch-all scan across
all 20 dives — extended (review item 3) to diff full
(name, attack, defense, stamina) tuples and ivTiers assignments, not
just names, so a wrong-tier HP-sync regression can't slip through
name-clean. Capture the BEFORE state with the same script prior to
applying/re-rendering, then diff the two outputs:

```
python - <<'EOF'
import re, json, pathlib
for d in sorted(pathlib.Path('userdata/website').iterdir()):
    for f in sorted(d.glob('index*.html')):
        h = f.read_text(encoding='utf-8')
        m = re.search(r'"tiers":\s*(\[.*?\])\s*,\s*"', h, re.S)
        if not m: continue
        tiers = json.loads(m.group(1))
        names = [t['name'] for t in tiers]
        if len(set(names)) != len(names):
            print('DUP', f, names)
        for t in tiers:
            print('TIER', f, json.dumps([t.get('name'), t.get('attack'), t.get('defense'), t.get('stamina')]))
        mt = re.search(r'"ivTiers":\s*(\[[^\]]*\])', h)
        if mt:
            import hashlib
            print('IVTIERS', f, hashlib.sha1(mt.group(1).encode()).hexdigest())
print('tier scan done')
EOF
```

Expected diff: DUP lines disappear; TIER tuples change ONLY on
tinkaton-ultra-league index/m1/m3/m4 (the 141.6765 tier's name, plus
possibly its stamina if the HP sync re-routes); IVTIERS hashes change
on at most those same four pages. Any other page changing = stop and
investigate before pushing.

Open question for Michael (also in the structured output): is the
MIN_SIG_GAP=1.0 floor the right knob, or would he prefer a p99 cut
(which keeps the line varying but makes "Smooth gradient" unreachable)?
The constant is a one-line tune either way. The floor now drives both
the text counts and the scatter-plot gap lines, so retuning it is
still a single-constant change.

---

## Adversarial review

Reviewed 2026-06-12 against HEAD `f4a3b3e` (NOT the `a73d855` the packet
was drafted on — 7 commits landed in between, including energy-lead-axis
changes to BOTH patched files). `git apply --check` re-verified clean at
`f4a3b3e`; the patched regions do not overlap the energy-axis hunks.
Independently re-verified: `detect_clusters` has exactly one call site
(rendering line 2942); `render_mirror_slayer_html` one call site (3455);
`_rename_plotly_tiers` two call sites (deep_dive.py 2381, 3606 — the
second is the idempotent re-run the patch handles via `original_name`);
`flavor['tier_name']` is real and survives `refine_flavor_names` (it
mutates `name` only, deep_dive_narrative.py 207/246/559); the mirror
passthrough/dedup exemptions are consistent with the exact-match layer;
`sweep_cache._ENGINE_FILES` is still `battle/_dp_jit/moves/formchange/
pokemon` at v3, so the no-cache-invalidation claim holds; no test or
fixture encodes the changed strings; both replay pickles exist; the D4
table has no colspan rows to break; incoming-gate and bestcm-superpower
patches touch only `src/gopvpsim/battle.py` (no file overlap).

**Verdict: NEEDS-WORK** — the core logic of all three fixes is sound,
but the D3 fix is incomplete:

1. **Missed twin implementation (must fix).** `scripts/deep_dive.py`
   ~2776-2786 inlines the SAME gap rule (`g > 3 * median_gap`, quartile
   gate, `sig[:5]`) to build `data_obj['clusterGaps']` — the horizontal
   gap lines the JS draws on the scatter plot. The packet's consumer
   grep searched for the `detect_clusters` symbol and missed this
   copy. Post-patch, a smooth-gradient scenario would render "0
   significant gaps" in the text while the plot still draws up to 5
   gap lines from the degenerate threshold, on every dive page. Add
   `thresh = max(3 * median_gap, MIN_SIG_GAP)` here too (import the
   constant from `deep_dive_rendering`), and add a clusterGaps check
   to the test plan / verification greps.
2. **Missed stale prose (one-liner).** `deep_dive_rendering.py`
   ~3125-3130, the "Cluster detection (gap analysis)" entry in the
   hidden Experimental-methods `<dl>`, still describes the pure
   3x-median rule. The patch updated the parallel intro at ~2931 but
   not this block; same class of text-drift D3 exists to fix.
3. **Verification gap (extend, don't re-cut).** D1's exact-name match
   can re-route the HP sync (`stamina` write + `_recompute_tier_
   assignments`) to a different tier than the old stat-scan picked,
   so affected pages can change in tier `stamina`/`ivTiers`, not just
   names. The catch-all cross-dive scan diffs NAMES only. Extend it to
   diff (name, attack, defense, stamina) tuples and flag ivTiers
   reassignment, so a wrong-tier HP-sync regression can't slip
   through name-clean.
4. **Stale packet metadata (cosmetic).** Update the header's verified
   HEAD to `f4a3b3e`; the ~line references in the D3/D4 sections moved
   slightly (e.g. render call site is now 2942/2961).
5. **Queued-fix coordination (note, no change).** A future
   renderer-D2-D5 packet would edit the same row-emission block
   (rendering ~2684/2709/2735) that the D4 hunk rewrites; it must be
   drafted against the D1-D4-applied tree or it will fail to apply.
   shadow-cmp / renderer-D2-D5 packets do not exist yet, so nothing
   to diff today. Also worth one sentence in the packet: the
   sweep_cache "standing rule" (v2/v3 bumps for scripts/ changes)
   covers worker/orchestration plumbing; renderer-only changes do not
   need a CACHE_VERSION bump — currently the packet argues only from
   `_ENGINE_FILES`.

Items 1-2 require regenerating the patch; 3-4 are .md edits; 5 is
process. Everything else checked out.

## Regeneration 2026-06-12 (same night, against HEAD `56fd106`)

All five review items addressed; patch regenerated from /tmp copies
(repo files untouched), `git apply --check` clean at `56fd106`.

1. **Twin fixed.** clusterGaps block (deep_dive.py 2776-2790 at
   `56fd106`) now uses `gap_thresh = max(3 * median_gap,
   rendering.MIN_SIG_GAP)` via the existing module import (line 81).
   Statically verified text/plot agreement on the smooth and 2-break
   synthetic distributions (0 and 2 gap lines, matching `n_sig`).
   clusterGaps consistency check added to verification commands;
   import-contract tripwire added to the test plan.
2. **Prose fixed.** Methods `<dl>` entry now states the absolute
   floor, interpolating `{MIN_SIG_GAP:g}` in the existing f-string.
3. **Catch-all extended.** Cross-dive scan now emits
   (name, attack, defense, stamina) tuples + ivTiers hash for
   before/after diffing; expected-diff statement added.
4. **Metadata refreshed.** Header HEAD `56fd106`; line refs updated
   throughout (rename fn 1721-1793, detect_clusters 2256, text call
   site 2942, twin 2776-2790, mirror-slayer def 2425).
5. **Coordination noted.** Standing CACHE_VERSION rule sentence added
   to the header. The rebased D2-D5 patch (which exists now, contrary
   to the review's snapshot) re-verified to apply cleanly on top of
   this regenerated patch in a /tmp sequential-apply check.

Additional regeneration verification: D1 re-verified against the REAL
tinkaton-ultra-league `DATA.tiers` extracted from the built page (the
findings-doc evidence), including a guard-only run that reproduces the
exact 0.044-delta Gyarados mis-match and confirms the guard blocks it;
see the D1 section. Both /tmp patched files compile
(`py_compile` clean).
