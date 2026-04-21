# S11 — HTML dive file-size audit

Post-S5 Oinkologne arc, plan §S11 (plan.md:1202-1241). Fast-tracked to
2026-04-21 per the fast-track trigger (plan.md:1590-1596) after Michael
flagged the Oinkologne GL dive files as actively annoying.

Audit only. S12 implementation is gated on sign-off below.

## Files measured

| Dive                                                     | Size     | Lines   |
| -------------------------------------------------------- | -------- | ------- |
| Oinkologne GL, m1 (`mud_slap_trailblaze`)                | 46.06 MB | 188,833 |
| Tinkaton GL, m1 (`fairy_wind_gigaton_hammer_heavy_slam`) | 10.66 MB | 12,509  |

Both files were re-dived 2026-04-21 (same renderer, same features:
auto-gen narrative, atk-weight badges, DATA.pasteTiers paste-box).

Oinkologne is 4× Tinkaton's size despite running through the same
renderer on the same day. The audit identifies where the gap is and
which reductions are feasible without regressing today's feature work.

## Byte budget — Oinkologne m1 (the problem file)

Hand-measured by `<script>` / `<style>` tag spans + regex attribute
extraction. See `/tmp/s11_audit.py` for the raw measurement script.

| Section                               | Bytes          | MB        | % file     |
| ------------------------------------- | -------------- | --------- | ---------- |
| `title="..."` tooltip attrs           | 20,651,082     | 19.69     | 44.8%      |
| ├─ on `dd-anchor-tag` spans           | ~19,960,000    | 19.04     | 43.3%      |
| ├─ on other badge/cell classes        | ~691,000       | 0.66      | 1.5%       |
| `const DATA` + SCORES_GZ + handler JS | 7,480,614      | 7.13      | 15.5%      |
| ├─ 4 SCORES_GZ base64 blobs           | ~3,680,000     | 3.51      | 7.6%       |
| ├─ rest of DATA block (state + glue)  | ~3,800,000     | 3.62      | 7.9%       |
| Plotly.js (inlined, minified)         | 4,558,713      | 4.35      | 9.5%       |
| `class="..."` attrs                   | 4,315,431      | 4.12      | 8.9%       |
| Residual HTML structure (tags, text)  | ~8,570,000     | 8.17      | 17.7%      |
| Main UI JS (`_scoresReady` handler)   | 94,287         | 0.09      | 0.2%       |
| JS port of `user_collection`          | 16,346         | 0.02      | 0.03%      |
| Inline `<style>` blocks (3)           | 17,019         | 0.02      | 0.04%      |
| Small helper scripts (ddNotable etc.) | 4,785          | 0.00      | 0.01%      |
| Head/meta/boilerplate                 | ~200,000       | 0.19      | 0.4%       |
| **Total**                             | **46,057,369** | **43.92** | **100.0%** |

Note on double-counting: `class="..."` attrs and `title="..."` attrs
are both *inside* the HTML markup zone. The "residual" row is the
remainder after carving both.

### What's inside each bucket

**Tooltips (44.8% of file).** 87,522 `title="..."` attributes; only
**1,651 unique values**. 84,638 of them sit on `<span
class="dd-anchor-tag" title="..."`> elements — the anchor-clears
tooltips. Sample:

```
title="steelix · clears 2 sub-anchors
auto_steelix_brkp_any
body_slam→18, trailblaze→28"
```

Top individual tooltip appears 906× at 85 B each. The same tooltip is
repeated once per IV cell that lands in that anchor's clear-list, so
duplication scales with (opponents × IV cells per opponent).

**SCORES_GZ blobs (7.6% of file).** The DATA block contains **4** ~900 KB
base64-gzip score blobs (not 1). Keys look like `"0_pvpoke": "H4sI..."`
— presumably one per (shield × bait) scenario bundle. These are
already gzipped at the source level; no further compression inside
the source file will shrink them.

**Plotly.js (9.5% of file).** 4.35 MB of inlined, minified Plotly
v2.35.2. Identical byte-for-byte across all 6 moveset sibling files
in the species directory. Already CDN-capable: see
`scripts/deep_dive.py:1175-1189` (`_plotly_script_tag(standalone)`).

**class attrs (8.9% of file).** 183,613 class attributes, 75 unique.
Top: `class="dd-anchor-tag"` × 84,638 (1.78 MB), then
`class="dd-anchor-tag-count"` × 77,270 (1.77 MB). Gzip compresses
these well (the 20.4% overall gzip ratio reflects this), so
uncompressed savings are bigger than wire savings.

**Residual HTML (17.7% of file).** 168,650 `<span>` tags, 24,915
`<td>`, 4,949 `<tr>`, 1,601 `<div>`, 157 `<details>`/`<summary>`
pairs. Span-heavy because of the 87K tooltip badges.

## Byte budget — Tinkaton m1 (the compact file, for comparison)

| Section                         | Bytes          | MB        | % file |
| ------------------------------- | -------------- | --------- | ------ |
| `const DATA` + SCORES_GZ        | 4,735,465      | 4.52      | 42.4%  |
| Plotly.js (inlined)             | 4,558,713      | 4.35      | 39.9%  |
| HTML markup + attrs + text      | 1,753,360      | 1.67      | 15.7%  |
| ├─ `title="..."` (5,754 titles) | 445,322        | 0.42      | 4.0%   |
| Main UI JS + helpers            | 115,650        | 0.11      | 1.0%   |
| **Total**                       | **11,178,508** | **10.66** | 100.0% |

Very different bottleneck shape: Tinkaton is dominated by Plotly +
SCORES_GZ (82% of the file); tooltips are only 4%. Tinkaton's 5,754
titles are mostly on atk-weight badges (2,143 slight-weight + 969
tilt + 877 heavy + ...), and they already dedup to 243 uniques, so
the absolute savings from tooltip-dedup on Tinkaton are only ~330 KB.

Moral: different species hit different walls. An approach that makes
Oinkologne 40% smaller may barely move the needle on Tinkaton, and
vice versa. A good S12 scope should hit both.

## Compressibility (wire size)

| File          | Uncompressed | gzip -6 | gzip -9 | Ratio |
| ------------- | ------------ | ------- | ------- | ----- |
| Oinkologne m1 | 46.06 MB     | 8.96 MB | 8.85 MB | 19.5% |
| Tinkaton m1   | 10.66 MB     | 4.26 MB | —       | 39.9% |

Oinkologne's 20% ratio reflects the title/class dup: gzip's sliding
window captures most of the repetition on the wire. But the full 46 MB
still has to be parsed by the browser — gzip doesn't help parse time.
The user-perceived pain (slow open, laggy interactivity) is
uncompressed-size cost, not wire cost. So reducing uncompressed size
is the real prize here.

## Reduction approaches, ranked

Ranked by **(bytes saved on Oinkologne + bytes saved on Tinkaton) ÷
implementation effort**. Effort estimated in renderer-LOC and risk of
touching today's feature work.

### Rank 1 — Shared tooltip-lookup table (dedup `title=` values)

**What:** Emit a single JS object `DATA.tooltips = {"a":"...", "b":"..."}`
containing the 1,651 unique tooltip strings. Replace per-element
`title="<long text>"` with `data-t="<short id>"`. On page load, a
single JS pass walks `[data-t]` elements and sets their `title`
attribute (or a `mouseenter` handler creates a custom tooltip div).

**Projected savings:**

| File          | Current tooltip bytes | After dedup | Δ         | % of file  |
| ------------- | --------------------- | ----------- | --------- | ---------- |
| Oinkologne m1 | 20.65 MB              | ~1.80 MB    | -18.85 MB | **-40.9%** |
| Tinkaton m1   | 0.42 MB               | ~0.08 MB    | -0.34 MB  | -3.2%      |

Single-handed hits the plan's -40% target on Oinkologne.

**Effort:** ~150-250 LOC in `scripts/deep_dive.py` renderer +
~30 LOC of runtime JS glue. No sim-logic changes. Non-breaking:
existing dives still work at full fidelity; the swap is purely a
representation change.

**Risks:**
- The runtime `title` attribute no longer exists until JS has run.
  Trade-off: users may briefly see no tooltip on a freshly-loaded
  page. Mitigation: bind titles at DOM-ready (not at first hover) so
  the window is <100 ms.
- Browser extensions / screen readers that read `title` attributes
  may break. Low risk given the anchor-tag tooltips are
  supplementary; the visible text is still in the DOM.
- Non-tooltip callers that rely on `title` attribute for programmatic
  access will need to read `data-t` + lookup. No current consumers
  known.

### Rank 2 — External shared Plotly.js

**What:** Add a `--shared-assets` mode to `scripts/deep_dive.py` that
writes `userdata/website/_shared/plotly-2.35.2.min.js` once and emits
`<script src="../_shared/plotly-2.35.2.min.js">` (relative path) in
each dive. Per-file save: 4.35 MB. Across-directory save: 4.35 MB ×
(moveset siblings + index). Wire-side: the browser caches plotly.js
after the first file opens — subsequent files skip the 4.35 MB download.

**Projected savings:**

| File          | Current plotly | After shared | Δ        | % of file  |
| ------------- | -------------- | ------------ | -------- | ---------- |
| Oinkologne m1 | 4.35 MB        | ~0 MB        | -4.35 MB | -9.5%      |
| Tinkaton m1   | 4.35 MB        | ~0 MB        | -4.35 MB | **-40.8%** |

Hits the -40% target on Tinkaton by itself. Complements Rank 1 on
Oinkologne (combined: -50%).

**Effort:** ~30-60 LOC. The plumbing already exists —
`scripts/deep_dive.py:1175-1189` has `_plotly_script_tag(standalone)`
which can emit CDN vs inlined. Third mode: emit relative path to
shared file. Copy plotly.min.js to `_shared/` at build time.

**Risks:**
- Breaks true single-file portability (moving an index HTML by itself
  loses the plot). Keep `--standalone` as an explicit flag for that
  case; `--shared-assets` is a new flag, default-off in the short term.
- Requires a bootstrap step: the `_shared/` directory must be
  populated. One-line call in `scripts/run_website_dives.py` or a
  post-dive check in `deep_dive.py` handles this.

### Rank 3 — Lazy-load per-scenario SCORES_GZ

**What:** The 4 ~900 KB gzip blobs in the DATA object correspond to
different (shield × bait) scenarios. Ship only the currently-selected
scenario inline; fetch others on-demand via `fetch("scores_<key>.b64.gz")`
when the user changes the scenario dropdown.

**Projected savings:**

| File          | Current SCORES_GZ | After lazy | Δ        | % of file |
| ------------- | ----------------- | ---------- | -------- | --------- |
| Oinkologne m1 | 3.51 MB           | ~0.9 MB    | -2.6 MB  | -5.6%     |
| Tinkaton m1   | ~3.0 MB           | ~0.75 MB   | -2.25 MB | -21.1%    |

**Effort:** ~200 LOC. Need to: split the emission into N sidecar
`.b64.gz` files, change the JS state loader to `await fetch()` on
scenario change, handle offline-file:// gracefully (can still load
relative files in most browsers, but needs UX for the switch).

**Risks:**
- `file://` cross-origin restrictions on some browsers (Chrome) will
  block local fetches by default. Firefox (Michael's default) is
  permissive. But this regresses offline single-file openability.
- First-scenario-switch latency (synchronous UX hiccup).
- More files in the per-dive directory.

### Rank 4 — class attribute dedup

**What:** 75 unique class names across 183K uses; emit a shorter
internal map in a `<style>` block (e.g. `.a { same-rules-as dd-anchor-tag }`).
Replace `class="dd-anchor-tag"` with `class="a"`. Saves ~3.5 MB
uncompressed on Oinkologne.

**Why skip:** Gzip already captures most of this (contributes to the
20% wire ratio). Uncompressed savings are real but smaller than
Rank 1-3 and the rewrite is widespread (breaks all pre-existing
CSS references + any user-facing `:inspect` habit). ROI too low.

### Rank 5 — Defer DOM rendering of collapsed `<details>`

**What:** Today's 157 `<details>`/`<summary>` pairs parse their full
contents on page load even when collapsed (browsers still build the
DOM, just don't render it). Swap collapsed content for a
`<script type="application/json">` payload that's lazily injected
into the DOM on `toggle`.

**Why skip:** The anchor-tag spans — the 87K-span DOM pain — are
*not* inside `<details>` blocks; they're inline in the IV-matrix
tables. This helps the sections-where-we-already-have-`<details>`
but not the 32 MB of tooltip-decorated inline rows. Rank 1 addresses
the actual bottleneck. Revisit if Rank 1 ships and there's still pain.

### Rank 6 — CSS-pseudo-element atk-weight tooltips

**What:** The plan called this out as a ~200 KB per-dive win. On
Oinkologne today there are 6 atk-weight mentions (trivial); on
Tinkaton there are 11,256. Replace `title="..."` on atk-weight badges
with `::after { content: ... }` CSS rules keyed by class name.

**Why skip:** Tinkaton's atk-weight tooltips are ~370 KB, all of
which Rank 1 (tooltip dedup) already eliminates. No separate work
needed once Rank 1 ships.

## S12 recommendation

**Ship Rank 1 (tooltip dedup) + Rank 2 (shared Plotly).**

Together they hit the -40% target on both the Oinkologne and
Tinkaton shape of dive. They're orthogonal (different code paths),
low risk relative to feature work, and total ~300 LOC.

| File          | Current  | After R1 | After R1+R2 | Total Δ    |
| ------------- | -------- | -------- | ----------- | ---------- |
| Oinkologne m1 | 46.06 MB | 27.21 MB | 22.86 MB    | **-50.4%** |
| Tinkaton m1   | 10.66 MB | 10.32 MB | 5.97 MB     | **-44.0%** |

The plan limits S12 to 1-2 approaches; this is exactly two.

**Explicitly out of S12 scope (document as post-arc TODOs):**

- Rank 3 lazy SCORES_GZ (regresses file:// portability; revisit
  after we have a hosted site).
- Rank 4 class dedup (ROI too low vs complexity).
- Rank 5 defer-DOM collapsibles (wrong bottleneck).
- Rank 6 atk-weight CSS tooltips (covered by Rank 1).

## Verification plan for S12

Measurement harness (a small `scripts/measure_html_size.py` or inline
in the audit script):

1. Pick the same 2 representative files before/after.
2. Measure: uncompressed size, gzip-6 size, line count, DOM node
   count (headless estimate via `scripts/pvpoke_trace.js` JSDOM or
   equivalent).
3. Measure parse time: Node `--experimental-fetch` + `performance.now()`
   around a `new DOMParser().parseFromString(html, "text/html")` call.
4. Report before/after in the S12 commit message.
5. **Fail-loud gate:** if measured reduction on Oinkologne falls below
   35% (5% cushion below the 40% estimate), flag it and don't ship.

## Feature preservation checklist

Today's 2026-04-21 renderer features must survive S12 unchanged:

- [ ] Auto-gen narrative (`scripts/auto_gen_narrative.py`) still
      renders into the two-zone layout.
- [ ] Atk-weight badges still show on anchor pills (Tinkaton has
      11,256; test that they still tooltip correctly post-Rank-1).
- [ ] `DATA.pasteTiers` paste-box promotion still populates.
- [ ] `.githooks/pre-commit` still rejects `authored_by = "ai"`.
- [ ] `--split-movesets` output layout unchanged (vs-Ref hover
      intentionally disabled per feedback memory).

## Gate: sign-off required before S12

Stop here. Do not start S12 implementation until Michael reviews and
approves. Specifically:

1. Confirm Rank 1 + Rank 2 is the right scope (vs. Rank 1 alone for a
   smaller-blast-radius ship).
2. Confirm the "breaks programmatic `title` attribute reads" risk on
   Rank 1 is acceptable (mitigation: bind at DOM-ready).
3. Confirm `--shared-assets` default-off is acceptable (breaks
   single-file portability only when opted in).

If S11 reveals Rank 1 is thornier than the audit suggests (e.g.
accessibility regressions), the plan explicitly allows punting S12 to
post-ship (plan.md:1594-1596).
