## Pre-ship execution order (2026-04-18, for 2026-05-09 CD)

Current thread: pre-ship polish between S10 ship day (2026-04-18) and
Oinkologne CD (2026-05-09). Canonical ordering, read this first when
resuming. **2026-04-23 refresh:** items 1, 3, 5 have shipped or are
largely shipped since this list was written; item 2 is legitimately
open (Michael wants another pass); items 4, 6 are the main remaining
pre-ship surface.

1. ~~**Cross-form re-dive**~~ — **SHIPPED** via `scripts/overnight_redive.sh`
   (2026-04-19/20 chain, ~8h). Both Oinkologne forms in
   `opponent_pools/gl_top50_plus_cs.txt`, article + standalone
   comparison page regenerated, `cd_prep` auto-injection path
   validated. See CHANGELOG 2026-04-19.
2. **JRE / RyanSwag / ours comparison** (`~/.claude/plans/
   jre-ryanswag-comparison.md`). **Status: re-run requested
   2026-04-23.** First pass shipped `docs/jre_ryanswag_comparison.md`
   (2026-04-18) against the pre-re-dive article; 2026-04-21 refresh
   surfaced G-series follow-ups (see §10.4). Michael wants another
   pass now that the article + dives have iterated further — "we
   always learn more each time."
3. **F1-F5 follow-ups** surfaced by the comparison output. **Mostly
   SHIPPED.** F1 Meta Role `ddf9d19`, F2 key-flips callout `923f985`,
   F4+F-wrap+F-intro `cbc9b28`+`259c493`, F-stats-block `c59a701`+
   `f6ef6a0`, F-fast/charge-moves `8397fa9`, F-hide-methodology
   `f9a1fc4`. Post-ship residual: F-tier-name-cleanup, F-shadow-
   narrative, F5 cross-article footer (gated ≥3-5 articles).
4. **P1-P4 polish** (see "Post-ship (article + dive polish)" section
   below). **P1, P2, P4 shipped; P3 (envelope-position annotations)
   and P5 (Stats at a Glance) remain.** Pull forward opportunistically
   if capacity allows before CD day.
5. ~~**XL-candy-decision tool**~~ — **SHIPPED 2026-04-22** as the
   Mirror CMP semantic reframe arc (11 commits `6dcc571`..`939162e` +
   Slayer IVs tooltip retrofit `c3edb14` 2026-04-23). Three columns
   on Top IVs table (Mirror Slayer CMP %, Top-Mirror CMP %, Matchups
   Kept) + About-these-metrics box + Highlight IVs feature + Slayer
   IVs "of yours" table gets the same columns + column-header
   tooltips. All shipped via direct source change; retrofit patchers
   cover previously-shipped dives.
6. **Link-verification pass** (P4 tool shipped; run it pre-publish)
   and **ship**.

Post-ship, the post-S5 arc resumes at S13-S17 in
`~/.claude/plans/post-s5-oinkologne-arc.md` (matchup-flip
attribution, post-debuff breakpoints, bait policy). S11-S12 (HTML
file-size) already shipped 2026-04-21, earlier than scoped. The
remaining S13-S17 are **not pre-ship items** - do not pull forward.

## Pre-ship: XL-candy-decision tool (Mirror CMP % + Score Δ vs rank-1)

**Motivation:** deciding which IV to pour stardust and XL candy into
for a meta-staple species (Tinkaton UL, Medicham GL, Corviknight GL,
Cresselia UL, Clefable GL, Annihilape GL) requires answering two
questions simultaneously:

1. Does this IV score near the top of the overall battle ranking?
2. Does this IV beat the CMP tie-break against the IVs real opponents
   actually run?

Rank-1-by-stat-product answers (1) trivially but often loses CMP
(confirmed 2026-04-19 on Tinkaton UL dive 4: rank-1 13/15/15 at
atk=140.75 is beaten on atk by rows 3, 5, 8, 9, 10 of the Top IVs
table — atk 141.17 through 142.85 — with battle-score deltas of
only 0.9-1.6 points vs rank-1). No single IV maximizes both. The
XL-candy commitment is large enough that eyeballing the table for
the right trade-off is an honest ~20-minute task per species.

**Two new computed values** (native in the dive HTML, retrofittable
to existing dives via an HTML patcher — no re-dive required; both
are pure arithmetic on data already embedded in the dive's `DATA`
object):

1. **`Mirror CMP %`** — per IV, fraction of the `--mirror-slayer`
   converged cohort that this IV beats at CMP (higher atk than).
   The mirror-slayer cohort is already computed for every
   full-sweep dive in `run_website_dives.py`, and its members'
   IV/atk values are already in the dive HTML. Compute =
   `count(cohort[i].atk < this_iv.atk) / len(cohort)`. Uses the
   Nash-converged cohort (not uniform-random 4096 IVs) so the
   number reflects what opponents realistically build, not what
   theoretically exists.
2. **`Score Δ vs rank-1`** — per IV, `my_score - rank1_score`
   under the currently-selected Shields / Opp-IV / Bait combo.
   Negative values = what you give up for the bulk or atk trade.
   Reacts to the dropdowns, so hovering in 1v1 mode shows the
   1v1-specific delta.

**Surface these in two places** (both cheap):

- **New sortable columns in the Top IVs table:** `Mirror CMP %`
  and `Score Δ`. User sorts by `Mirror CMP %` desc, scans down for
  IVs with `Score Δ` close to 0 (small score sacrifice, high CMP
  coverage). That row answers "which of my catchable IVs is the
  right XL target."
- **Hover tooltip on the scatter plot:** two extra lines per
  hover showing the same values. Combined with the existing
  paste-box-CSV-overlay (your collection circled), you can paste
  your Tinkaton collection, hover each one, and see instantly which
  meets the "good battle rank + wins mirror CMP" criteria.

**Implementation path:**

- **Client-side JS** (not server-side Python patching) — the
  computations depend on the currently-selected Shields / Opp-IV /
  Bait dropdowns, which drive the avg score. Doing it in Python
  would require re-running the patcher every time those change.
  ~30 lines of JS in the dive's existing inline script: compute
  both values at page load and after each dropdown change, inject
  into the Top IVs table rows + hover tooltips.
- **Renderer update** (`scripts/deep_dive_rendering.py`): emit
  the new columns + JS block for every future dive.
- **Retrofit patcher** (`scripts/patch_dive_mirror_cmp.py`,
  new): regex-inject the JS into existing dive HTMLs. Idempotent
  via a comment-fingerprint header. Parallels the existing
  `patch_dive_species_narrative.py` pattern. Run against the 4
  existing dive dirs + anything else with an `index_m*.html`.

**Estimated effort:** 3-4 hours (JS computation + table/tooltip
wiring + renderer change + patcher).

**Generalization note:** this is the "which IV do I XL?" decision
tool. Applies to every meta-staple species whose candy XL cost is
nontrivial — Tinkaton UL, Medicham GL, Corviknight GL, Clefable
GL, Annihilape GL, Cresselia UL, Guzzlord UL, Registeel UL, and
on. Once built, zero per-species config — every full-sweep dive
with `--mirror-slayer` gets it for free.

**Optional stretch:** dedicated Pareto-frontier sub-plot — atk
stat on X-axis, avg score on Y-axis, frontier line highlighted,
CMP-% contours at 50/75/90%, user collection circled. Pretty and
information-dense, but the two-column add alone answers the
question at the cost of less visual polish. Pull in if the
core add leaves time; skip otherwise.

## Personal-collection decision tool follow-ups (2026-04-21)

Gaps surfaced during a session helping Michael pick which Tinkaton UL
to build from his PokeGenie CSV. The XL-candy-decision tool section
above answers the headline question once shipped; these three items
are orthogonal polish that became load-bearing when the session tried
to cross-reference the shipped dive against his collection.

- **Matchup Flip tooltip un-truncation.** The Top IVs table's
  `Gained` / `Lost` tooltips cap at 6 entries each with a `+N more`
  tail. For 15/11/11 vs 13/15/15 UL Tinkaton, the hidden "+5 more"
  losses almost certainly contain `Tinkaton 1v1` and `Tinkaton 2v2` —
  which is exactly what decides whether the slayer is a lead or a
  closer choice. Fix options: expand the tooltip cap, or append a
  click-to-expand `<details>` with the full list below the row. Low
  effort, directly unblocks the personal-collection decision without
  needing the bigger XL-candy tool.

- **Per-shield Score Δ column(s) on the Top IVs table.** The SP # and
  avg-score columns collapse 0v0 / 1v1 / 2v2 into one number. For
  role-specific builds (lead ≈ 2v2-weighted, closer ≈ 0v0-weighted,
  mid ≈ 1v1-weighted) the three splits are separate decisions. Data
  already exists in the dive (the Matchup Delta table has per-shield
  deltas); this is a rendering add, not a simulation change. Pairs
  well with the XL-candy tool's `Score Δ` column — extend that to
  three columns instead of one.

- **`scripts/suggest_builds.py`.** CLI helper: takes `--species`,
  `--league`, `--roles lead,closer`, path to a PokeGenie CSV export,
  and the shipped dive HTML. Parses the Top IVs + Anchors + Matchup
  Flip tables, intersects with the collection, prints a ranked
  shortlist per role with the key tradeoffs (atk/HP/def, anchor
  flips, score Δ, XL/dust cost to finish). Essentially automates the
  manual grep+cross-reference dance. Maybe 2-3 hours; deprioritize if
  the XL-candy tool lands first and the scatter paste-box overlay
  turns out to be enough.

## CD-prep tracking (2026-04-17, fix shipped 2026-04-18)

**SHIPPED.** Per-species `[cd_prep]` TOML block is now read by
`deep_dive.py`: any listed `fast_moves` / `charged_moves` are injected
into `enumerate_movesets`' legal lists with a loud log line per
injected move, so pre-CD dives include the incoming move even when
PvPoke's gamemaster lags. Implementation in the
``enumerate_movesets(..., cd_prep_fast=, cd_prep_charged=)`` signature
plus the auto-discover block that reads the focal species' TOML.

Original problem (kept here until the Oinkologne CD ships and we
delete the cd_prep blocks): pre-CD dives silently dropped the
incoming CD move when the gamemaster cache refresh flipped between
runs. Observed on 2026-04-17 for the Male/Female Oinkologne pair.
Manual workaround was `--fast MUD_SLAP`; the permanent fix removes
the need to remember that flag.

Delete the TOML `cd_prep` section after the CD ships, or after
PvPoke stably lists the move for 2+ gamemaster refreshes.

## Pre-ship: article text-density pass (2026-04-18)

Surfaced during S10 UI polish: our article has noticeably more
explanatory / clarifying prose than JRE's GamePress CD articles or
RyanSwag's GamePress deep dives. Much of it answers first-time-reader
questions but repeats on every visit; a second-time reader or
multi-article reader wants to skim faster.

**First-pass fix — SHIPPED.** The three paragraph targets are all
now click-gated:

- Meta Coverage "Each cell averages 4,096 focal IVs x N opponents"
  methodology paragraph — wrapped by `f9a1fc4` (F-hide-methodology).
- Matchup Delta legend "What the columns mean" — SHIPPED `a6db157`
  (removed the default-open `open` attribute so it now collapses
  like the sibling legends).
- Opp-IV / Bait toggle caption — SHIPPED `a6db157` (collapsed the
  visible caption sentence into the adjacent "What these dropdowns
  change" `<details>` block; dropdowns themselves stay visible).

The existing `<details>` on the &Delta; column was already default-
closed pre-pass.

**Broader pass (after the JRE / RyanSwag comparison, pre-ship):**
once the density gap is quantified, do a structural edit pass. The
question isn't "wrap this paragraph in `<details>`" but "which three
of these six paragraphs can go entirely?" - that requires the
benchmark to answer. Comparison tracked under "Pre-ship: JRE /
RyanSwag / ours comparison" below.

## Pre-ship: JRE / RyanSwag / ours comparison (2026-04-18) — EXECUTED (against pre-re-dive article)

Plan: `~/.claude/plans/jre-ryanswag-comparison.md`.
**Output:** `docs/jre_ryanswag_comparison.md` (written 2026-04-18).
**Reference archive:** `docs/reference_deep_dives/jre/` — five JRE
articles archived locally (Tinkaton, Ninetales, Rillaboom,
Empoleon, Toucannon) so future comparison sessions can skip the
re-fetch. RyanSwag archive at `docs/reference_deep_dives/ryanswag/`
(pre-existing).

**Note on re-dive ordering:** The comparison was run *before* the
cross-form re-dive (opposite to the original sequencing plan)
because the JRE/RyanSwag structural findings don't depend on dive
data — section layout, prose-vs-data ratio, and meta-role framing
are all article-level. Numbers quoted in §3.Q of the output doc
(43.1% win rate, specific IV counts) will shift slightly after the
re-dive regenerates the article; the F1-F5 follow-up list below is
unaffected.

### Follow-ups to execute (from comparison §4)

Listed priority-ordered for the pre-ship window (2026-04-18 to
2026-05-09). Hide-vs-remove discipline: default action for "content
we have they don't" is hide-behind-`<details>`, not delete.
Removal candidates (R1-R3 in comparison §5) require per-item
Michael approval; **do not auto-execute**.

**2026-04-19 status audit:** Most of the pre-ship F-list is already
shipped. See each item's **SHIPPED** annotation for the commit. Also:
2026-04-19 decision to move to **Shape 2** (narrative at top of the
dive, not in the article) — see "Shape 2 migration" block at the
bottom of this section. The shipped F-list entries below remain
useful for article-side polish but the primary narrative home is
shifting to the dive via a new renderer path.

- **F1 + F-typing + F-stats-block** — SHIPPED. F1 Meta Role `ddf9d19`,
  F-stats-block `c59a701` + `f6ef6a0`. F-typing is woven into F1's
  Meta Role `good_at` paragraph for Oinkologne (not a separate
  block); could split later if another species needs a distinct
  typing discussion.

- **F2** — SHIPPED `923f985` (key-flips callout above Matchup Delta,
  3/3 knob).

- **F4 + F-wrap + F-intro** — SHIPPED. F4 + F-wrap `cbc9b28` (verdict
  editorial + outlook fields, both expert mode). F-intro `259c493`
  (BLUF intro override with hooked matchup).

- **F-fast-moves + F-charge-moves** — SHIPPED `8397fa9` (full move-
  pool tables between Move Comparison and Meta Coverage).

- **F-hide-methodology** — SHIPPED `f9a1fc4` (four `<details>` wraps:
  Meta Coverage caption split, compare-lead, IV Recommendations
  intro, Matchup Delta pool annotation).

- **P2 article -> dive per-opponent deep links** — SHIPPED `081cd2a`
  (see P2 section below).

### Shape 2 migration — narrative moves from article to dive (2026-04-19)

Decision 2026-04-19: primary narrative home for a species is the
**dive** (RyanSwag-style), not the CD article. Articles continue to
exist when they do something the dive can't — disambiguating multiple
forms (Oinkologne M/F, Aegislash Blade/Shield), shadow variants, or
alt-moveset meta forks (Forretress Volt Switch vs Bug Bite). For
Oinkologne the CD article stays because M/F comparison is its
justification; the existing `[intro] / [meta_role] / [verdict]`
prose will migrate (or be duplicated) into per-form threshold-TOML
expert-zone fields that a new dive renderer surfaces at the top of
each dive.

**Session 1 SHIPPED 2026-04-19 as commit `41bbe6f`** — renderer
plumbing + per-block `author` attribution schema. Pure code, zero
content migration. Design decisions resolved in that session:

- Render position: **above the interactive dashboard** (after the
  Related Article link, before the controls bar).
- TOML schema: **new top-level `[Species.intro] / [Species.meta_role]
  / [Species.verdict]` blocks** in `thresholds/<species>.toml` —
  field-for-field mirrors of `articles/*.toml`'s same-named blocks
  so prose migrates by copy-paste.
- Renderer location: **`deep_dive_rendering.render_species_narrative()`**
  alongside the existing gold-zone code, not the Flavor Guide module.
- Migration scope: **split** — species-scoped prose moves to per-form
  threshold TOMLs; CD-event-scoped framing (move comparison, form
  comparison, verdict-on-the-CD-move) stays article-side.
- Author attribution: **new optional `author = "..."` field** on each
  narrative block, rendered verbatim as a muted italic line. Reader-
  visible distinction between AI-drafted and human-written prose.
  See `docs/article_schema.md` "Per-block author attribution" and
  `docs/threshold_schema.md` "Species narrative" for full schema.

**Pre-ship blocker reminder:** the existing Oinkologne article ships
today with unlabeled Claude-drafted `[intro]` / `[meta_role]` /
`[verdict]` blocks. Session 2 below unblocks ship — Session 1's
renderer alone does not (it just made the `author` field possible).

**Session 2 — SHIPPED `bf05538`.** Per-form Oinkologne M/F narrative
authored in the threshold TOMLs; article `[intro]` / `[meta_role]` /
`[verdict]` slimmed to CD-event scope; every Claude-drafted block
carries `author = "Drafted by Claude (Opus 4.7), not yet
human-reviewed"`. Tonight's overnight re-dive bakes the narrative
into the regenerated Oinkologne dive HTMLs.

**Session 3 (Aegislash) — SHIPPED `bb021fa`.** Blade and Shield
narrative authored in the threshold TOMLs (Shield = canonical
realistic play pattern; Blade = always-Blade diagnostic
hypothetical). Out-of-band Aegislash GL dives against the Orlando
top-32 pool landed the same day (Blade `14:37`, Shield `15:41`);
HTMLs were force-patched with the narrative injection. Aegislash UL
pair runs in tonight's overnight chain and picks up the narrative
natively.

- **[Post-ship] F-tier-name-cleanup** — simplify IV-rec tier card
  names (current: `Steelix (Shadow) Slayer -   (Wigglytuff Slayer
  -   (Wigglytuff Atk))`) to RyanSwag's name/signature convention
  per `docs/reference_deep_dives/ryanswag/STYLE_ANALYSIS.md`.
  Bundles with S5a rename work in post-S5 arc.
- **[Post-ship] F-shadow-narrative** — Shadow-variant comparison
  prose block for species that have shadow forms (not applicable
  to Oinkologne ship).
- **[Post-ship, gated ≥3-5 shipped articles] F5** —
  multi-article-reader cross-linking footer. Not worth building
  until cross-reference surface is large enough.

### Removal candidates (MICHAEL APPROVAL REQUIRED)

Comparison doc §5 (R1-R3) lists three items proposed for deletion
rather than hiding. Each has per-item justification + JRE/RyanSwag
precedent for absence. Nothing ships without explicit sign-off.

- **R1 — SHIPPED `934a8a1`.** "(N dropped, missing from at least one
  dive)" parenthetical removed from `scripts/compare_loadouts.py`
  along with the unused skipped-opponents loop.
- **R2 — SHIPPED `934a8a1`.** "Cards are colored by form (♂ blue /
  ♀ pink)..." self-reference removed from the IV Recommendations
  tier intro in `scripts/generate_article.py`.
- **R3:** Meta Coverage "Shield asymmetry dominates the extremes"
  explanatory paragraph — start with hide (F-hide-methodology
  above), escalate to removal only if hide reads as bloat at
  review time. **Status: still hidden, not removed.** Re-evaluate
  post-ship.

### Aegislash test case — SHIPPED

F1 shipped on Oinkologne first. Aegislash Blade + Shield narrative
shipped 2026-04-19 (commit `bb021fa`) as Shape 2 Session 3, serving
as the second test case for the Meta Role section type. Out-of-band
GL dives landed same day; UL pair came through the overnight chain.
See `project_shape2_session1_shipped.md` for the canonical record.

### 2026-04-21 refresh follow-ups (comparison doc §10)

Refresh pass 2026-04-21 against shipped F1-F5 state surfaced five
new gaps the original 2026-04-18 cut did not anticipate. Full
writeup in `docs/jre_ryanswag_comparison.md` §10.4; short form:

- ~~**G4 — `authored-auto` label for auto-gen narrative blocks**~~
  **SHIPPED 2026-04-21 as commit `284c95b`.** Fourth enum value
  `auto` added alongside `human` / `ai` / `mixed`; `_auto_fill` sets
  `authored_by="auto"` when filling; both `authored_by_class`
  (article) and `_authored_by_class` (dive) map it to the
  `authored-auto` class (blue sidebar). Verified on the shipped
  Oinkologne article (4 blocks tagged `authored-auto` correctly).

- ~~**G5 — Aegislash narrative is orphan ship content**~~
  **NOT NEEDED.** Audit 2026-04-23: the shipped Aegislash narrative
  is `authored-auto` (deterministic rollup from dive data via
  `auto_gen_narrative.py` standalone mode), not LLM-drafted prose.
  Every re-render regenerates it from `data_obj` — no orphan risk.
  The empty `thresholds/aegislash_shield.toml` bodies are correct
  and expected: the TOML comment on line 23-27 explicitly documents
  that auto-gen fills them at render time and they stay empty until
  a human writes species-specific prose.

- **[Pre-ship, Michael-decides] G3 — Oinkologne verdict editorial
  + outlook prose not populated.** `cbc9b28` shipped the F4 schema
  + renderer hook; article ships with just the mechanical one-liner
  because verdict editorial is expert-only (no auto-gen template,
  per `feedback_expert_narrative_not_autogen`). Either 15-30 min
  of Michael-authored prose pre-ship OR accept the mechanical line
  as the ship form. Both defensible.

- **[Post-ship, recommended] G1 + G2 + G7 — richer auto-gen prose
  template.** F1 Meta Role, F2 key-flips callout, and F-fast/charge-
  moves all shipped as deterministic rollups ("vs Steel-type:
  Steelix +77pp..." / "Steelix — Male: 0.0% → 76.6% (+76.6 pp)
  +Flip"). JRE-style prose ("Mud Slap takes Male Oinkologne from
  0% to 76.6% vs Steelix — the signature upgrade") would close
  the register gap. Template change, not Claude-drafted prose, so
  ship-policy-clean. 0.5-1 session. Benefits every future dive.

- **[Post-ship, bundles with G1] Row D — bulk-vs-peers paragraph.**
  Micro-gap from original §3.D; never made it through F1's auto-
  gen template. Fold into the G1 template upgrade.

## Post-ship (article + dive polish, 2026-04-18)

Items queued from the post-S10 UI polish round that are nice-to-
have but not required for the Oinkologne CD ship. Pulled-forward
candidates: after each pre-ship item lands, check whether there's
capacity to pull one of these in without risking the ship window.

### P1. Tier-card anchors for Notable IVs + Mirror Slayer cards — SHIPPED `40d19e9`

Notable IVs cards now emit `id="notable-<slug>"` (name-slug stable
across re-dives) and Mirror Slayer cards emit `id="mirror-<slug>"`.
`scripts/patch_dive_tier_anchors.py` extended with regex-backfill
variants for both card types (verified: 125 notable + 3 mirror
per Oinkologne GL dive file). External pages — CD article IV
Recommendations, cross-species comparisons — can now deep-link
into the per-card anchor. Article-side wiring is still open; see
TODO §"S8 envelope-annotation" / the parked form-change-pool
decision for the design question around which article surface
should consume these anchors.

### P2. Article -> dive per-opponent deep links — SHIPPED 2026-04-18

Each opponent name in the per-form Matchup Delta table is now a
link to the primary form's dive, landing on that opponent's first
`#opp-<slug>` anchor inside the Matchup-Flipping Boundaries
section. Secondary forms get a small trailing symbol link (♂ / ♀)
in the form's column color. Opponents with no flipping boundary in
any form's dive (clean sweeps in either direction) stay as plain
text so clicks never scroll to nowhere.

**Implementation:**
- `scripts/deep_dive_rendering.py`: `opp_slug()` helper;
  `render_matchup_boundary_bullets` + `render_anchor_flip_bullets`
  emit `id="opp-<slug>"` on the first `<li>` per opponent when
  `emit_opponent_ids=True` (wired only at the standalone call
  sites to avoid duplicate ids with the tier-card-nested callers).
- `scripts/patch_dive_opp_anchors.py`: in-place regex backfiller
  parallel to `patch_dive_tier_anchors.py`; idempotent.
- `scripts/generate_article.py`: `_load_one_dive_file` extracts
  `anchored_opps` from each dive file's HTML;
  `_render_matchup_delta_per_form_section` gates link emission on
  whether the slug exists in the best-CD moveset's anchor set.

**Follow-up (out of scope this session):** single-form
`_render_matchup_delta_section` (line 1954) doesn't yet link
opponent cells — applies to non-CD articles that aren't per-form.
Extend when the first such article actually ships.

### P3. Envelope-position annotations in IV Recommendations cards

Previously deferred in the post-S5 arc (see the "S8 envelope-
annotation wiring skipped" note in the old TODO flow). The S4
`envelopePositions` dict is keyed by Notable-IVs category name,
not threshold tier, so the article would need either a
category-card surface or a tier-name to category-name mapping.
Design question before implementation.

### P4. Pre-ship link verification pass — TOOL SHIPPED 2026-04-18

Tool: `scripts/verify_article_links.py`. Usage:

    python scripts/verify_article_links.py --ship
    # or against specific files:
    python scripts/verify_article_links.py path/to/index.html [...]

The `--ship` flag scans the Oinkologne pre-ship surface set
automatically (site index, CD article, both dive landings, all
moveset split files under each, the standalone compare page).
Exit code 0 = no broken internal refs; 1 = errors found.

First run 2026-04-18: 18 files, 252 hrefs (36 internal, 24 anchor,
192 external, 0 other). No broken refs. Article had zero stale
`tackle_*` references — all dive-split links land on Mud Slap
movesets. The `tackle_*` files only cross-reference each other in
the moveset dropdown nav, which is self-consistent.

**Re-run before ship** (after the cross-form re-dive lands, since
any regeneration can introduce new link shapes). The script uses
stdlib `html.parser` so it correctly skips the ~1000 `onclick`
handlers in each dive — those construct PvPoke URLs at runtime
and can't be statically verified. Add a targeted onclick scan if
a regression ever surfaces; not worth building until then.

### P5. Stats at a Glance follow-ups

The CP-capped rank-1 stats section shipped 2026-04-18 (part of
F-stats-block enhancement). Two known limitations in the
`_rank1_cp_capped` helper in `scripts/generate_article.py`:

1. **Best Buddy (level 51) is included in the rank-1 search.** The
   underlying `gopvpsim.pokemon.iv_rank` defaults `max_level=51`
   for every league, so rank-1 computation implicitly picks the
   Best Buddy-option IV spread when that produces a better stat
   product. PvPoke's UI defaults to non-BB (level 50). For low-
   level species (Oinkologne rank-1 lands at level 22-23) this is
   a non-issue. For UL bulk-first species (Cresselia, Registeel,
   Guzzlord, etc.) rank-1 IVs differ between BB and non-BB and
   our displayed numbers may not match a reader's PvPoke-defaults
   view. Fix: add a TOML knob (`stats_at_a_glance.best_buddy =
   true|false`, default false to match PvPoke) and thread through
   to `iv_rank(..., max_level=50 or 51)`.

2. **Shadow focal species aren't supported.** `_rank1_cp_capped`
   hardcodes `shadow=False` in the `iv_rank` call. Any future CD
   article whose focal Pokemon is a Shadow variant (e.g. a
   hypothetical Shadow Oinkologne CD) would display non-Shadow
   rank-1 stats. Fix: detect shadow from the article's species
   name or a TOML flag; pass `shadow=True` to `iv_rank`.

Neither blocks current CD-article generation. Pull into a session
when a species that actually needs either hits the queue.

## Status-box generalization — shipped as chain_status.py (2026-04-21)

`scripts/chain_status.py` replaces `scripts/overnight_status.sh`
with a `--chain {overnight,retrofit}` preset flag + `--status-file`
/ `--pgrep` / `--wrapper-log-glob` escape-hatch overrides. ETA still
delegates to `scripts/overnight_eta.py` for bucket averages and
cross-midnight / overshoot handling. Backward-compat: both presets
render correctly; overnight's display uses the wrapper-log mtime as
an upper bound so a later chain's per-dive logs don't leak in.

Follow-up #2 from the 2026-04-19 plan (paste-this-watch-command
hint in other wrappers) still stands — `run_website_dives.py` and
`deep_dive.py` could print a `watch -n 5 'scripts/chain_status.py
--chain ...'` recipe at startup when the matching status preset
exists. Small.

## Pre-ship: cross-form opponent coverage for Oinkologne (2026-04-18) — SHIPPED

Items 1-3 (add both forms to `opponent_pools/gl_top50_plus_cs.txt`,
re-dive serially, regenerate article + comparison page) shipped via
the 2026-04-19/20 overnight chain. `cd_prep` TOML auto-injection
(commit `e61c14e`) replaced the old `--fast MUD_SLAP` workaround;
re-dive validated that code path.

**Open tail:** item 4 (auto-form-sibling expansion in
`build_opponent_pool.py`) — design done but parked pending review of
rendered Oinkologne article; decide pool-level vs render-level filter
for hypothetical-form rows. See memory
`project_form_change_pool_expansion_parked.md`.

## S9a checkpoint observations (2026-04-17)

- **CLI-comment logger reconstructs `--mirror-slayer` incorrectly.** In
  the log header and the top-of-HTML `<!-- CLI: ... -->` comment,
  `deep_dive_logging.py`'s argv reconstruction emits `--mirror-slayer
  True` even when the actual invocation used only `--mirror-slayer` (a
  `BooleanOptionalAction` flag, which argparse rejects with a literal
  `True` argument — reproducibly verified: pasting the logged CLI back
  into a shell errors with `unrecognized arguments: True`). Effect:
  cosmetic but breaks copy-paste reproducibility of past dives.
  Likely cause: the reconstruction formats bool flags as
  `--flag <value>` instead of `--flag` / `--no-flag`. Low-risk fix in
  the logger.

## Deferred cleanup: backwards-compatibility removal pass

Once we've verified all the oracle/sim tests (including direct human
review by Michael), run a dedicated session to **remove
backwards-compatibility shims, historical artifacts, and
"just-in-case" abstractions** that accumulated during feature work.
The goal is to simplify the code now that we've confirmed the new
behavior is right.

Concrete candidates to audit (grows as we spot them):

- **`gopvpsim.evolution_lines.get_final_form()`** — kept alongside the
  new `get_final_forms()` for callers that "know they're dealing with
  unambiguous chains." Delete once nothing in the codebase calls it.
  Currently used only by tests.
- **`pvpoke_dp(intended_pruning=...)`** — the flag toggles between
  "PvPoke's actual JS behavior (dead-code dominance checks)" and
  "apparently intended behavior." If we're confident one branch is
  right, collapse to that and drop the flag.
- **Anything flagged with "historical" / "legacy" / "backcompat"** in
  code comments — grep for these when the session starts.
- **Gobattlekit threshold schema compatibility** in
  `gopvpsim.user_collection.check_thresholds` — once gobattlekit has
  actually migrated to use the shared module and we've confirmed it
  works, we may want to simplify the dict schema or unify with
  pogo-simulator's TOML anchor schema. But not before gobattlekit's
  migration lands.

Do NOT start this cleanup pass until Michael has explicitly signed
off that the current oracle tests pass human verification. This rule
exists because "simplification" mid-feature-work tends to silently
break invariants that weren't yet nailed down by tests.

## Battle simulator

* **File PvPoke bug reports** — Seven bugs found in PvPoke's JS:
  1. BattleState `.hp`/`.oppHealth` naming inconsistency (dead-code dominance checks)
  2. bestChargedMove using `move.damage` (undefined at init) instead of `move.power`
  3. bestChargedMove not recomputed on opponent form change (stale DPE cache)
  4. Aegislash selects Gyro Ball over Shadow Ball (same cost, strictly less damage)
  5. Mimikyu delays Shadow Sneak by 1 SC (suboptimal timing, costs 13 score points)
  6. initializeMove's buff-adjusted `move.dpe` is overwritten by
     selectBestChargedMove before use. Pokemon.js:849-864 computes a
     buff multiplier that inflates DPE for self-atk-buff and opp-def-
     debuff moves, but Pokemon.js:791-796 (inside the same `resetMoves`
     call) immediately resets `move.dpe = move.damage / move.energy`
     on every activeChargedMove. So the buff-adjusted DPE only affects
     the priority-shuffle ordering (lines 711-787); it never reaches
     the bait-wait ratio check (ActionLogic.js:843) or any later
     consumer, despite looking like it should. Likely intent was for
     the buff adjustment to persist through the ratio check. Discovered
     2026-04-14 while resolving our Divergence 2.
  7. needsBoost / non-guaranteed-buff plan selection is dead code.
     ActionLogic.js:539 unconditionally zeros `changeTTKChance`, so
     `stateList` never accumulates chance-<1 plans; and `needsBoost`
     (line 793) is never assigned `true`, so the line 868 plan-reorder
     gate is inert. Empirically 0 "needs the BOOST" log hits across
     the 4 GL meta species whose default moveset has a chance-<1
     charged move (Tinkaton, Corviknight, Clefable, Drapion).
     Discovered 2026-04-15; writeup in DEVELOPER_NOTES.md §7.

* **Resolve known PvPoke divergences** — ~~Three~~ One remaining intentional
  implementation difference tracked in DEVELOPER_NOTES.md "Known divergences."
  1. ~~selfBuffing flag scope~~ RESOLVED 2026-04-14: broadened to match PvPoke
  2. ~~Bait-wait DPE ratio~~ RESOLVED 2026-04-14: was misdiagnosed; PvPoke
     also uses raw DPE in the 1.5 ratio check (selectBestChargedMove
     overwrites buff-adjusted values). Real gap was the priority-shuffle
     (Pokemon.js:711-787), now ported.
  3. bestChargedMove recomputed per-turn vs PvPoke's init-time cache --
     keeping ours (intentional, more correct; see DEVELOPER_NOTES.md)

* **Audit existing oracle tests against the PvPoke harness** — Now
  that `scripts/pvpoke_trace.js` + `scripts/verify_pvpoke_harness.py`
  exist and 27/27 pass, extend the verify script to cover ALL
  PvPoke-oracle test cases currently in `tests/test_battle.py` (and
  anywhere else we've hand-typed a PvPoke score or move sequence into
  a test/docstring/comment). Typos and user-entry errors may have
  silently crept in over time; the harness is cheap to run and gives
  a definitive check against PvPoke. Scope: enumerate all existing
  fixtures, feed each to the harness, flag any where the harness
  disagrees with the recorded PvPoke numbers. Fix typos; separately
  flag genuine PvPoke divergences for follow-up.

* **Speed test** -- compare our speed vs the PvPoke JS code, look for
  ways we can speed ours up.

* ~~**Forretress/Azu 0-shield score divergence**~~ — **RESOLVED 2026-04-15.**
  Not a DP plan-selection bug after all. Root cause: our OMT
  (`_optimize_move_timing`) had a `defender.hp > _fast_dmg` gate that
  preferred fast-KO over charged-KO "because scores identical." That
  assumption held only for instant-fast; under mid-cooldown timing a
  delayed fast cost 3 turns of Azu damage on Forr (T37 fires charged
  immediately in PvPoke; ours waits for fast that lands at T40). Gate
  removed. GL grid max |Δ| 15→0 across all 405 pairs.
  Investigation landmark: decideLog entry/return tracing added to
  scripts/pvpoke_trace.js (PvPoke's decideAction-level entry/exit log)
  was the tool that localized this — earlier dpPlan-level traces missed
  it because the divergence was upstream of the DP. Full writeup in
  DEVELOPER_NOTES.md "Resolved divergences" 2026-04-15 OMT entry.

* ~~**Near-KO DP non-debuf swap (Lapras [1,2] flip)**~~ — **Closed
  2026-04-15 followup, not fixing.** Original hypothesis ("near-KO
  branch needs a symmetric non-debuf swap") was wrong. The actual
  mechanism is PvPoke's post-DP bandaid[885] (our port: bandaid[866]
  at battle.py:1541), which relies on a `.damage` side effect from
  OMT line 320. Faithfully mirroring PvPoke fires the swap in ALL 6
  MG cluster cases — the `damage/opp.hp < 0.8` test doesn't separate
  Lapras (0.70) from Jellicent (0.62) / Corv (~0.6). Net: matching
  PvPoke inverts the 6:1 ratio (resolves Lapras, regresses 6 cluster
  clear-wins). Per CLAUDE.md divergence policy, ours is defensibly
  better overall. Keeping the `_cached_damage` subgate at
  battle.py:652 as the intentional deviation; xfails stay. Full
  writeup in DEVELOPER_NOTES.md "Near-KO DP plan choice".

## Policies to add

* **PvPoke "Selective" baiting** — PvPoke's UI offers a bait toggle; "Selective"
  uses the same ActionLogic.js DP to decide *whether* baiting is worthwhile given
  current state (turnsToLive, bestChargedMove by DPE, minimumCycleThreshold).

* **Random buff/debuff** — For chance-based buffs (< 1), PvPoke uses a
  deterministic buffApplyMeter that fires every 1/chance activations. We should
  also support running many sims with random rolls, to find win conditions
  (e.g. if first Air Cutter boosts, you win, otherwise you lose). Options:
  deterministic (current), random, always-hit, never-hit, double-boost.

* **EV-based baiting** — our own novel policy: parameterize the bait decision by
  an estimated P(opponent shields). P~0 → fire best-DPE move; P~1 → bait with
  cheapest.

* ~~**Baiting policy as a deep-dive sim axis**~~ — **SHIPPED.** `--bait
  {on,off,both}` sweeps the selected modes; with `--bait both` the HTML
  renders a Bait dropdown (`deep_dive.py:2678-2683`) alongside Shields
  and Opponent-IVs. Scatter, threshold/flip aggregator, anchor-clear
  overlay, and bait-differential matchup cards
  (`deep_dive_rendering.py:2840-2910`) all consume `state.oppIvMode`
  with the `:nobait` suffix so they react to the dropdown. Confirmed
  2026-04-16 while scoping S3 histogram. Remaining open items are
  policy-enumeration (Selective, EV-based) under "Policies to add"
  above — distinct from the axis plumbing. S16/S17 in the post-S5 arc
  still tracks post-ship design polish (named bait modes in bullets),
  but nothing is blocking.

## Features to add

* **Form Change** — ✅ **Done 2026-04-14.** Morpeko (toggle Aura Wheel
  Electric/Dark), Aegislash (Shield<->Blade stat/move/level swap),
  Mimikyu (disguise absorbs first unshielded hit, -1 def stage).
  Data-driven via gamemaster formChange field. Oracle tests: Morpeko
  6/9, Aegislash 1/9, Mimikyu 6/9 match PvPoke exactly; remaining
  mismatches are the GB/SB cascade (PvPoke bug #3) and Mimikyu SS
  timing (PvPoke bug #5), pinned as xfails. Next: Mimikyu deep dive
  with form change narrative.

* ~~**DP cycle-timing move selection**~~ — **CLOSED 2026-04-15,
  not an actual issue.** Original claim: our DP picks PR over IB in
  Azu vs Aegislash 0v0 where IB yields more total damage via an extra
  throw. Verified independently in two sessions (2026-04-15): current
  sim throws Ice Beam twice in Azu vs Aegislash 0v0 and lands on the
  same score PvPoke does (773). The concrete example was resolved
  incidentally by one or more of: the bestChargedMove DPE threshold
  port (fca1b7c), the activeChargedMoves priority-shuffle port
  (68a306d), and the raw-DPE / atk_stage fixes around 2026-04-15. The
  full oracle audit (115/115 matches PvPoke harness) shows no
  remaining cycle-timing symptoms in any form-change or basic 0v0
  fixture. Do NOT re-queue without a new concrete failing case.

## Tests to add

* **No-bait oracle tests from iv-tech deep dives** — `pvpoke_dp` now
  accepts `bait_shields=False`. Sanity tests for the farm-down gate
  landed in `test_battle.py` (see `test_pvpoke_dp_no_bait_*`), but we
  should add real-world oracle cases from the HSH #iv-tech deep dives
  in `docs/*.md`. Candidates (each asserts that `bait_shields=False`
  still wins the cited matchup):

  1. **Tinkaton vs Medicham 1-1** — ✅ **Done 2026-04-12**
     `docs/tinkaton_deep_dive_reference.md:25`. "141.66 defense with
     138 hp lets you … win the 1s *without baiting*." Covered by
     `test_tinkaton_wins_1v1_vs_medicham_no_bait` parametrized over
     both rank #1 (5/15/15 NBB) and default (7/15/14) Medicham and
     both bait modes. Tinkaton 1/14/14 (def=141.66 exactly, hp=143)
     wins all 4 cases at score 520. Note: `bait_shields` has no
     observable effect here (near-KO DP phase bypasses farm-down bait
     branches); the test confirms bait-off doesn't break the matchup.
     **Open followup**: our sim has a more forgiving win threshold
     than the reference — many Tinkaton spreads below def=141.66 also
     win the 1v1 (e.g. 0/10/15 at def=138.96 wins). The reference's
     141.66 threshold may be overly conservative, or our sim is
     missing a nuance. Worth round-tripping at pvpoke.com/battle.

  2. **Tinkaton vs rank #1 Azumarill 1-2** — ✅ **Done 2026-04-12**
     `docs/tinkaton_deep_dive_reference.md:27`. "143.03 defense gives
     a bulkpoint vs rank #1 azu which flips the 1-2s (*no baiting
     required*)." Covered by
     `test_tinkaton_def_143_flips_1v2_vs_rank1_azumarill` which
     asserts the directional def-bulkpoint flip: Tink 1/14/14
     (def=141.66) LOSES 1v2 at score 397; Tink 0/14/9 (def=143.04)
     WINS 1v2 at score 535. Crossing def=143.03 flips the matchup as
     predicted. The "no baiting required" qualifier is verified by
     parametrizing over both bait modes (bait_shields irrelevant in
     this matchup, same scores either way).

  3. **Tinkaton vs rank #1 shadow Altaria 0-1** —
     `docs/tinkaton_deep_dive_reference.md:31`. "143.04 defense with
     141 hp … win the 0-1s *without baiting*." Note: reference also
     flags inconsistency due to shadow IV variance.

  4. **Spidops vs rank #1 Altaria 1s** —
     `docs/spidops_deep_dive_reference.md:35`. "140.67 defense with
     132+ hp flips the 1s vs the rank #1 altaria *without baits* by
     reducing sky attack damage."

  5. **Corviknight vs default-IV Shadow Sableye** — ✅ **Done 2026-04-12**
     `docs/corviknight_deep_dive_reference.md:58`. Both halves of the
     reference claim verified by:
     - `test_corviknight_max_def_wins_1v1_vs_default_shadow_sableye`
       (parametrized over bait modes — 1v1 "flips without baiting")
     - `test_corviknight_2v2_vs_default_shadow_sableye_flips_with_bait`
       (2v2 "flips with bait twice" — directional A/B: bait-on wins
       531, bait-off loses 288). This is the strongest oracle we have
       for the `bait_shields` gate: if farm-down baiting regresses, the
       2v2 test flips and catches it.

  Each test should parametrize over `bait_shields=[True, False]`
  when the reference makes a directional claim (cases 1, 5
  especially). For cases where the reference only asserts the
  no-bait result, test only `bait_shields=False`.

  Priority: low-to-medium. These are integration oracles, not
  correctness-blocking — the simple unit tests in `test_battle.py`
  already prove the gate works. Pick these up in a session where you
  can verify exact movesets/IVs at pvpoke.com/battle.

* **Form Change** — ✅ **Done 2026-04-14.** Oracle tests shipped:
  Morpeko 9/9, Aegislash 5/9 + 4 xfails (PvPoke bug #3 GB/SB cascade),
  Mimikyu 9/9 match PvPoke harness.
  Form changes DO affect opponent shielding (Aegislash Shield form
  suppresses shields if damage < half HP) and baiting (Mimikyu
  opponents break disguise ASAP with cheapest charged move).

* **Auto-anchor fallback gating tests** — `build_auto_anchors()` and
  the per-kind gating logic are currently only verified by smoke runs
  against real Annihilape data. Add explicit unit tests for the
  gating cases (no kinds existing → all three fire; one kind existing
  → other two fire; all three existing → empty registry).
  *Note: bulkpoint gating tests landed in 2026-04-08; this entry now
  covers the broader BP/CMP gating coverage gap.*

## Analysis goals

* **RyanSwag atk-weighted spreads may be outdated** — The
  `thresholds/_shared.toml` atk-weighted variants (Medicham 7/15/14,
  Lickitung 10/15/14 + 10/14/13) are sourced from RyanSwag's 2024
  methodology video and archived GamePress deep dives. Moves and meta
  have shifted since (Counter nerf, Rage Fist, Low Kick buff, new
  species). Periodically re-evaluate:
  1. Is the species itself still meta-relevant? (Lickitung dropped out
     of the GL top-50 in the current pool; Lickilicky is more common.)
  2. Is the *atk-weighted* variant still the one competitive players
     prepare against, or has the community shifted to a different
     high-atk IV?
  3. Does the variant's atk stat still cross meaningful breakpoints
     against current focal species, or did a move rebalance collapse
     the BP distinction?
  Not urgent — the current spreads work as "the 2024 community-cited
  variants RyanSwag uses, verified by the methodology video." But the
  longer the spreads sit without review, the more likely they drift
  from the live meta. Revisit whenever a new atk-weighted variant
  lands in a future deep dive, or annually.

* **RyanSwag-style matchup-flip annotations + wins-based y-axis**
  *(in progress 2026-04-09)* — Extend deep dives to call out *which
  specific matchups flip at which IV thresholds, in which shield
  scenarios* (e.g. "103.54 Def for the mirror BP vs Annihilape: 2-2
  no bait, 2-1 farm, 0-0 Ice Punch only"). The flip infrastructure
  already exists (`_find_flips`, `_narrate_flip`,
  `_generate_threshold_descriptions` in `scripts/deep_dive.py`); the
  gaps are: (a) the aggregator collapses scenarios instead of naming
  them, (b) threshold descriptions are stat-shape heuristics, not
  tied to named anchors (mirror BP, etc.), (c) flips are computed
  against a single reference IV, not multiple baselines.
  **Phase 1 (text)**: Extend the aggregator to emit per-anchor
  bullets that name the scenarios where each anchor's flip occurs;
  tie threshold descriptions to anchor names from the resolver.
  **Phase 2 (graph)**: Add a wins-based y-axis to the interactive
  scatter plot, with three baseline traces — vs rank-1, vs PvPoke
  default, vs mirror-converged cohort. Single shared flip table
  feeds both phases. **Caveat**: move parameters have changed since
  the original RyanSwag dives; we are reproducing the *format and
  reasoning style*, not the exact stats. **Cross-ref**: this work
  may resolve (or substantially shift) the "Slayer-card signal-loss
  audit" item below — both are about surfacing differentiating
  signal where current heuristics produce vacuous output. Re-read
  the audit item before starting Phase 2 renderer changes.

* **Meta-wide slayer reference (ambitious)** — With the slayer anchor
  system AND bulkpoint anchor system shipped, we can systematically run
  `--mirror-slayer` (with anchors) on the top 30 GL meta picks and build
  a meta-wide reference of "the converged slayer cohort + named anchors"
  for every relevant species. Each species gets its own
  `thresholds/<species>.toml` with hand-picked anchors against its key
  opponents (and the auto-fallback layer fills the gaps). The output:
  a per-species HTML deep dive plus a top-level summary table of which
  IVs are slayer-quality across the meta. This is the natural extension
  of the Annihilape work to the rest of the format. Could be paced as
  2-5 species per session to keep momentum without burning out on TOML
  authoring. Goodra, Clodsire, Carbink, Galarian Stunfisk, Tinkaton,
  Medicham, Annihilape (already done) are obvious starting points —
  they're in the existing dive history. Anything in the championship-
  series group is a candidate.

* **Reproduce SwagTips-style IV deep dives** — articles like the old GamePress
  Carbink and Annihilape PvP IV deep dives. Use Pokemon Go Championship Series
  event data (most common mons/movesets) as the modern test pool. Sim all 4096
  IVs of competitive mons against rank 1s, find interesting IV targets, check
  for hidden corebreakers. Consider atk-weighted IVs for CMP tie priority.

* **Reverse-engineer anchor intent from tournament CPs** — dracoviz dumps
  real per-mon CPs (83% non-1500, 48 distinct values in the Orlando 2026
  snapshot at `docs/tournament_data/cs_2026_orlando.json`). For each
  tournament entry, enumerate 4096 IVs × valid levels, filter to matching
  CP, cluster candidates into anchor categories (rank-1 SP, atk-weighted,
  def-floor at threshold X, HP-floor, CMP atk-floor). Top-k categories per
  mon give a best guess at what the player was aiming for, and aggregating
  across the 156-team field lets us ask "do top-8 Forretress converge on
  one anchor or spread across flavors?" and "do our TOML-authored
  thresholds match what elite players actually chase?" Own branch when
  this lands.

* **Compare to reddit IV spectrum post** —
  https://www.reddit.com/r/TheSilphArena/comments/z11xr0/theorycrafting_iv_spectrum_graphs/
  Reproduce the method (move parameters have changed since then).

* **Reproduce iv-tech channel analysis** from HSH's Discord.

* When I look at our interactive plots of Fairy Wind/Bulldoze,Gigaton
  Hammer Tinkaton, against the PvPoke default IVs, the 1v1 sheilds has
  a clear cluster at the top right, and I'd liek to know what's
  distinguishing about it. Especially since none of our pre-programmed
  thresholds show up in it. The 2v2 shows a similar cluster, though
  some of our pre-programmed thresholds do show up there. And the 2v2
  has some clear mostly horizontal banding structure. That would be
  interesting to dig into. The 0v0 has a big chunk in the bottom right
  that does include several of our GH Good mons ... but those have far
  worse battle scores here than lots of other mons. What are they
  missing? It's weird that a lot of that structure (almost all of it,
  actually) washes out when we look at the average battle score across
  all scenarios. Well. Across all even shield scenarios. We should
  check against all scenarios when we fix that bug.

* **Reinvestigate clustering methodology** — Current gap analysis (>3× median
  gap in sorted scores) is a rough heuristic. Consider better approaches:
  density-based methods, stat-space clustering instead of score-space, or
  matchup-aware clustering (group IVs that win/lose the same matchups).
  The Color By dropdown (HP/Def/Atk) already reveals banding structure
  visually; the automated analysis should match what users see.

* **Send acidicArisen a Discord message about the Lurgan 102.9 def floor**
  — Our 2026-04-08 bulkpoint Level 3 enumeration against the Annihilape
  mirror found that the historical Lurgan Ape `def ≥ 102.9` floor is
  *unrecoverable* from current sims: the next bulkpoint above 102.9
  (`shadow_ball ≤149` at def 103.34) is unreachable for today's
  converged cohort (max def ~101.30). The 102.9 floor predates Rage Fist,
  so the threat-move set has shifted. Ask acidicArisen whether the
  historical calibration was against a Counter or Close Combat tier
  transition, or against something more niche (Shadow Ball / Night Slash).
  This is the missing context that would let us promote a specific
  bulkpoint to a Level 1 anchor with full provenance.

## Slayer card UX (post-bulkpoint shipped 2026-04-08)

* **Slayer-card signal-loss audit + design discussion** *(needs design
  before implementing; broader than originally scoped)* — With Level 3
  auto-bulkpoint enumeration shipped, every survivor in the converged
  cohort passes nearly every parent's *lowest* sub-anchor (which is
  trivially cleared). Result: Bulk Slayer membership = 100% of the
  survivor pool, no signal. Same effective problem for Atk Slayer with
  auto-BP enumeration. **We will almost certainly find similar
  signal-loss in other places once we go looking** — e.g. the CMP
  Slayer top-quartile fallback may saturate too on some species, the
  banding-by-color analysis in the interactive HTML may have similar
  issues, and the threshold-tier dropdown may produce vacuous tiers
  on some cohorts. Treat this as a **systemic audit** rather than a
  local Bulk Slayer fix. Possible fixes for the immediate Bulk Slayer
  case, none ideal:
  1. **Minimum interesting threshold gate**: in the resolver, suppress
     sub-anchors whose lowest tier is cleared by 100% of the cohort.
     Pros: simple, applies uniformly. Cons: cohort-dependent (two
     dives with different cohorts get different anchor sets).
  2. **Show only differentiating parents in row badges**: render
     a parent's badge only when this row passes *more* sub-anchors
     than the cohort median for that parent. Pros: highlights what's
     unique. Cons: hides structure that's "everyone passes 6/6", which
     is sometimes information.
  3. **Tier badges by significance**: color-code badges by how rare
     the row's sub-anchor count is in the cohort. Pros: keeps all info,
     adds signal. Cons: more visual complexity.
  4. **Hide parents with 100% pass rate from the filter panel and
     row badges, surface them once in a "everyone passes" callout**.
     Pros: cleanest. Cons: extra renderer state to track.
  Pick one (or a hybrid) before implementing. This is *not* the same
  bug as the cell-level tooltip dump (fixed 2026-04-09 separately).
  When this is worked, sweep the rest of the slayer/threshold/banding
  output for similar "everyone passes the lowest tier" patterns.

  **Observed instance — Oinkologne GL (2026-04-19).** Dive 1 of the
  overnight re-dive; Mud Slap / Body Slam / Trailblaze scatter under
  `userdata/website/oinkologne-great-league/index_m0_*.html`. Slayer
  IVs (yellow markers) cluster in the top-RIGHT of the scatter — i.e.
  rank-1-ish stat product *and* high avg battle score — instead of
  the traditional Lurgan-Ape-style LEFT-cluster where slayers sit at
  worse bulk in exchange for higher attack. Mechanism: Oinkologne
  caps at level ~22-23 at GL CP, so the atk range across IV spreads
  is narrow, *and* Mud Slap's low DPE means the damage step between
  adjacent atk values is small — so the slayer atk breakpoint lands
  below where rank-1-bulk IVs already sit, making the "slayer" tag
  non-discriminating against premium bulk. Concrete real-world
  instance of the signal-loss concern this TODO flags. Worth using
  as the first test case when the audit happens; if the chosen
  remedy doesn't differentiate the Oinkologne scatter, it's not
  solving the problem.

* **"Show clusters" section is always visible** — it sits above the
  interactive scatter plot but should be gated behind the "Show
  experimental analysis (banding, clusters)" checkbox in the Deep Dive
  Analysis section. The checkbox already toggles `#dd-alpha` and
  `#dd-alpha-methods`; the cluster-display block needs to either move
  inside `#dd-alpha` or be hidden by the same JS handler. Discovered
  2026-04-08.

## Slayer iteration cleanup

* **Investigate inconsistent slayer Max Wins column** *(cosmetic, not
  blocking — ranking is correct)* — Yesterday's
  `annihilape_*_old.html` files report Max Wins values in the round
  table that aren't multiples of `n_even` (3) — e.g. round 2 max=41.
  Today's runs with the same code (and same metric=even-strict) produce
  values that ARE multiples of 3 (round 2 max=123 = 41×3). The
  converged pool sizes match exactly (round 1 = 66 in both), so the
  iteration logic is consistent and IV ranking is preserved; only
  the displayed Max Wins column number differs. Either the metric
  semantics changed between runs, or the HTML rendering uses a
  different code path that I haven't found. Check git history of
  `iterative_slayer_discovery` for any silent shifts. Discovered
  2026-04-08, deferred as task #13.

* **Re-run Annihilape mirror slayer with Lurgan as an explicit
  opponent variant** — Hypothesis 2 from the validation doc was that
  the community optimizes against a broader opponent set (PvPoke
  defaults + atk-weighted + Lurgan-style hand-builds). With the new
  TOML format, we can put the Lurgan spread in as a named opponent IV
  cohort and re-run mirror iteration to see whether our convergence
  shifts. If atk 129.44 still wins, hypothesis 1 (outdated community
  spread) is confirmed; if it shifts toward 127, hypothesis 2 is
  confirmed.

* **Update `docs/validations/2026-04-07_annihilape_mirror_slayer_iteration.md`**
  to reflect acidicArisen testimony (Discord, 2026-04-08) and the
  bulkpoint Level 3 enumeration finding (2026-04-09): the community
  Lurgan Ape spread is a *historical anchor* calibrated to a Lickitung
  BP near atk 127.23, predating Counter nerf, Rage Fist addition, and
  Low Kick buff. Current expert advice is to push higher attack than
  the Lurgan baseline, which matches our converged result. Reframe
  the validation doc from "we disagree with community" to "we converge
  to current expert practice; the published Lurgan spread is a frozen
  historical reference." Also note the 102.9 def floor knowledge-
  recovery investigation conclusion (unrecoverable from today's data).

## HTML output paths

* **Non-interactive `generate_html` is now strictly worse than interactive**
  — `generate_analysis_sections` (line 2046, which produces the slayer
  iteration display, breakpoint narration, banding analysis, clusters,
  etc.) is *only* called from `generate_interactive_html` (line 2866),
  not from `generate_html` (line 1242). Without `--interactive`, the HTML
  shows just the top-N table, the plot, and a brief methodology footer —
  none of the slayer analysis. Fix: either deprecate the non-interactive
  path entirely, or refactor so both paths render the analysis sections.
  Discovered 2026-04-08 during anchor-system smoke testing — it's easy
  to mistakenly run a smoke test without `--interactive` and conclude
  nothing rendered.

## CD article generator (2026-04-16; SHIPPED Post-S5 S6-S10)

* ~~**Python article generator**~~ — **SHIPPED** across Post-S5
  Sessions S6-S10 (2026-04-17 to 2026-04-18). Default path is live at
  `scripts/generate_article.py`; the Oinkologne CD article ships from
  `articles/oinkologne-cd-2026-05.toml` to `userdata/website/articles/
  oinkologne-cd-2026-05/index.html`. Move-comparison table, meta-
  coverage summary, matchup-delta, IV recommendations, verdict,
  PvPoke-link helper, per-form rendering, and opponent-IV / bait
  toggle are all implemented. The authorship-gated override layer
  (`expert` / `both` / `auto`) also shipped — F1 Meta Role, F2 key-
  flips callout, F4 Verdict augment, and F-intro are the currently
  authored surfaces.

  **Related work now resolved:**
  - ~~Battle-rating histogram~~ — SHIPPED `af56cb6`.
  - ~~Slug convention fix~~ — resolved; article TOML
    (`articles/oinkologne-cd-2026-05.toml`) and threshold slug
    (`thresholds/oinkologne.toml:13` `slug = "oinkologne-cd-2026-05"`)
    both use hyphens. Dive "Related Article" link renders at
    `scripts/deep_dive.py:2783` — re-verify during ship if a 404 is
    observed in the field.
  - ~~Female Oinkologne dive~~ — SHIPPED 2026-04-18 (S10);
    `userdata/website/oinkologne-female-great-league/` live with 10
    split-moveset HTMLs.

  **Still open on top of the shipped generator:**
  - Envelope-position annotation wiring into IV Recommendations
    cards — see S8 envelope-annotation follow-up below (unchanged).

  **Also shipped on top of the generator:**
  - Shape 2 migration of narrative from article to dive — SHIPPED
    2026-04-19 across three sessions (commits `41bbe6f`, `bf05538`,
    `bb021fa`). Per-species narrative now lives in
    `thresholds/<species>.toml` and renders at the top of each dive
    via `deep_dive_rendering.render_species_narrative()`. Article
    `[intro] / [meta_role] / [verdict]` slimmed to CD-event scope.

  **Watch item for S8 (envelope-position annotation surfacing):** when
  the per-category envelope-position metric (S4) gets surfaced as
  in-card annotations in the IV recommendations section, audit whether
  `render_notable_ivs_section`'s existing UX caps
  (`notable_max_count=5`, `max_members_shown=5`) still feel right with
  an extra shape-tag line per card. Not an action item yet — S4's
  metric doesn't add new category *types*, only a classification, so
  the cap isn't currently under pressure. Flagging so the audit
  doesn't get discovered at render-time in S8.

  **S8 envelope-annotation wiring skipped (2026-04-17), follow-up
  logged:** S4's `envelopePositions` dict is embedded in the dive DATA
  blob keyed by Notable-IVs category name (`Atk Slayer`, `Lapras Atk`,
  etc.). The article's IV Recommendations section currently renders
  `tier` cards (stat-cutoff-based, from `data_obj['tiers']`) not
  category cards, so the annotations don't have a natural slot. Two
  paths for a future session: (a) add a Notable-IVs card block to the
  article IV-recs section and annotate those directly, or (b) build a
  tier-name → category-name mapping and attach the envelope annotation
  to whichever tier exposes the anchor that backs the category. (a) is
  simpler but duplicates dive content; (b) reuses the existing
  presentation but needs a naming bridge. Defer until someone has an
  opinion about which surface to annotate.

## Deep-dive narrative

* **SwagTips narrative 3-session arc — SHIPPED 2026-04-19.** The
  renderer module `scripts/deep_dive_narrative.py` (1016 lines, purple
  "IV Flavor Guide" zone between Expert Analysis gold and Simulation
  Deep Dive blue) is in place. All three sessions per
  `~/.claude/plans/flickering-swinging-micali.md` are done:
  (1) renderer shipped as Shape 2 Session 1 (commit `41bbe6f`),
  (2) ~~Goodra test-drive dive~~ done 2026-04-16, and
  (3) ~~Aegislash form-change dive~~ done 2026-04-19 (commit `bb021fa`,
  Shape 2 Session 3); narrative generation handles mid-battle form/
  moveset swaps. See "Narrative renderer polish gated on Oinkologne"
  below for cosmetic items logged during the Goodra session.

* **Narrative renderer polish gated on Oinkologne** — surfaced during
  the Goodra test-drive (2026-04-16, Lechonk CD prep Session 2). Items
  are cosmetic; holding until Session 4 (Oinkologne deep dive) reveals
  which actually bite on a different species before fixing
  speculatively.
  1. ~~**General-tier 3-stat signature**~~ — **FIXED 2026-04-17 (S5a
     items 6+7).** Resolution was structural, not cosmetic: the name
     and signature are now coupled via `_flavor_name_for_tier(name, atk,
     def_, hp)`, which picks from axis shape per STYLE_ANALYSIS.md
     "Stat Signature Rule". A General tier with ADH signature renames
     to `General Good`; DH stays `Premium Bulk`; A-only becomes
     `Attack Weight`. `_stat_signature` no longer suppresses axes at
     all — it shows the real constraint set, which is correct because
     name family now matches shape. Also fixes item 7 of S5a (any
     2-axis pair supported, e.g. GFisk `Pure Mirror Slayer (Atk/Def)`
     without HP).
  2. **22-IV catch-phrase edge case** — `_catch_phrase` caps at 500
     catches as "very rare". The 22-IV Altaria Slayer on Goodra
     moveset 4 shows `~129-258 for a 50-75% chance`, which is under
     the cap but still a large number; arguably should have a middle
     "rare" tier. Wait for Oinkologne to see what catch counts
     actually land in the 50-300 range before adding a tier.
  3. **Session 2 validation note** — most Goodra narrative thresholds
     that diverge from RyanSwag's June 2024 reference are explained
     by opponent-pool shift (Lickitung/Gligar/Mantine/Pelipper no
     longer in PvPoke GL top-21), not renderer bugs. Session 4 /
     Oinkologne should not re-litigate these; they are expected data
     differences per the existing "format and reasoning style, not
     exact stats" principle.
  4. ~~**Identical-stat flavors not merged**~~ — **FIXED 2026-04-17
     (S5a item 2).** `merge_identical_stat_flavors()` groups flavors
     by `(stat_sig, gains_sig)` exact equality, renames the primary
     to `"{Opp} / Shadow {Opp} Slayer"` (or `Fortified …`), and
     absorbs the others. Live Oinkologne m0 case after the renderer
     fix is Lapras / Shadow Lapras Slayer (the Quagsire case no longer
     renders because commit 759edb8 dropped 0-IV narrative flavors).
     Negative-test `Fortified Lapras (105.19 Def, 153 HP)` has a
     different stat signature and correctly stays standalone.
     Also fixed: S5a item 1 namesake guarantee — Slayer tiers whose
     gains didn't mention their namesake opponent now get a synthetic
     entry prepended from the closest matchup boundary.
  5. **Narrative flavors not reflected in Plotly scatter tiers** —
     surfaced on Oinkologne Tackle moveset (Session 4): the IV Flavor
     Guide derives 4 flavors (Premium Bulk, Quag Slayer, Shadow Quag
     Slayer, G-Corsola Slayer) but the Plotly scatter only shows
     "Top 5%" because the anchor-flip aggregation system found too
     few records to derive named tiers. The two tier systems (anchor-
     flip-derived plot tiers and narrative-derived flavors) are
     independent; when the anchor system falls back to "Top 5%" only,
     the plot loses all the structure the narrative found. Consider
     feeding narrative flavors back as plot tier annotations, at least
     as a fallback when anchor-derived tiers are sparse.

* **Export Notable IVs cards to external scanner tool** — The user has a
  separate tool that scans their existing pokemon collection against
  IV target specs. Each Notable IVs card represents a target the user
  might want to feed to that scanner: composite cards have stat
  cutoffs (`atk≥X, def≥Y, hp≥Z`) and matchup cards have an exhaustive
  IV list. Add per-card "Copy to clipboard" buttons (matchup cards →
  IV triples; composite cards → stat cutoffs). Possible "Copy all
  visible" button at the section header for the typical "filter to
  notable, copy everything" flow. **Format unknown until user
  specifies what their scanner accepts** — could be plain comma-
  separated triples (`0/8/15, 0/11/11, ...`), Pokegenie/CalcyIV search
  strings, JSON, or something specific to the scanner. Ask before
  implementing. Discovered 2026-04-09 while reviewing the first
  Annihilape Notable IVs render — a 16-IV matchup card with no way
  to extract its members surfaced the gap.

* **Hand-named composite categories via TOML** *(round 2 of structured
  IV categories)* — Round 1 shipped 2026-04-09 (commits f3aa4ad, 8ff4469,
  79e2e87, b344356) as the unified `IVCategory` framework with
  literal-intersection naming (`Atk Slayer ∩ Top 5%`). The natural next
  step is a `[Species.Great.categories.<name>]` TOML table that lets
  the user assign a memorable display name + custom description to a
  specific intersection (`bulk_floor_slayer`, `compromise_slayer`,
  etc.) and override the literal name with the playstyle name. Schema
  sketch: `includes_anchors = [...]` + `includes_tier = "..."` +
  `display_priority = N`. Defer until the auto-derived path proves
  useful on Tinkaton + 1-2 more species — single point of data
  doesn't yet justify the schema work.

* ~~**Bait-axis matchup categories**~~ — **SHIPPED.** Confirmed
  2026-04-16 while scoping S3 histogram. Non-bait matchup cards
  populate `bait` from `parse_mode(opp_iv_mode)[1]`
  (`deep_dive.py:415-423`); the bait-differential builder in
  `deep_dive_rendering.py:2840-2910` emits "Beats … with bait only" /
  "… no bait only" cards keyed on `(opponent, scenario, bait)`; and
  `matchup_subtitle()` at `deep_dive_rendering.py:517-538` renders the
  ``· no bait`` / ``· with bait`` suffix. Follow-up UX polish (richer
  narrative phrasing, merging adjacent bait cards) lives in S17 of the
  post-S5 arc, not here.

* **RyanSwag-style autogenerated deep-dive section** *(own arc, scope
  after post-S5 arc ships)* — With the narrative renderer,
  namesake/merge/conformance fixes (S5a), article generator (S6-S10),
  histogram (S3), envelope metric (S4), matchup-flip attribution (S13),
  post-debuff breakpoints (S15), and bait-axis-in-narrative (S17) all
  shipped, revisit whether the deep dive (or a dedicated section of it)
  should autogenerate a prose output that looks like a RyanSwag
  GamePress article — same 5-part structure (intro, moveset discussion,
  PvP IV tables, per-league analysis, wrap-up), same prose style, but
  generated from our simulation data instead of Claude mimicking
  RyanSwag's voice. Not a session in the current post-S5 arc: (a)
  that arc is already 17 sessions + Aegislash, bail-prone; (b) the
  shape depends on what the renderer ends up capable of after S5a/
  S6-S10 settle. This is its own arc when the time comes.
  **Prerequisite check before opening**: confirm S5a items C1/C2/C3/C5
  shipped (name-signature coupling, namesake guarantee, 2-axis support,
  identical-stat merge). Those fixes are the RyanSwag-conformance
  floor; autogen doesn't make sense on a renderer that still produces
  name-signature mismatches. Separate from the JRE/CD article work in
  S6-S10, which has a different audience and format — **don't conflate
  them**; the CD article is mechanical spec-sheet + data tables, this
  is narrative prose structured like RyanSwag's articles.
  Flagged 2026-04-17 by Michael.

## Reproducibility

* **Deep dives have non-reproducible opponent data** — `scripts/deep_dive.py`
  fetches PvPoke rankings (`great`, `ultra`, `master`) from GitHub via a
  24-hour-TTL on-disk cache at `~/Documents/gopvpsim_cache/`. Two dives
  with the same CLI args can produce *substantially* different opponent
  sets if the cache was refreshed between them — not "Annihilape moved
  one spot," but "the entire top 20 changed." Discovered 2026-04-09 while
  trying to byte-equality-verify a JS rename refactor: the post-rename HTML
  vs the pre-rename backup HTML disagreed on the opponent list because
  the cache had been refreshed (likely by a `pytest` invocation that
  triggered `load_rankings`) between the runs that generated each file.
  CLI-args embedding (already shipped, see `format_cli_args`) lets a reader
  reproduce the *command*; this gap means it doesn't fully reproduce the
  *data*. Possible fixes:
    1. Embed a small "data fingerprint" in the HTML at run time: hash +
       mtime + first-N species of the rankings list. Lets a reader spot
       drift without enabling reproduction.
    2. Add a `--rankings-snapshot DATE_OR_HASH` flag that pins to a
       specific cache state for full reproduction. Requires durably
       archiving rankings snapshots, e.g. under
       `userdata/rankings_snapshots/`.
    3. At minimum, log the `great.json` mtime + first-5 species at run
       start so users notice when their dive's opponent set is unusual.
  Option 1 + option 3 together is probably the right starting point —
  cheap, doesn't require any new infra.

## UI / Display

* **Additional scatter plot color modes** — The current color scheme has some dark
  points that are hard to see against the background. Add a dropdown with alternate
  color modes (e.g. color by stat product rank, color by HP, color by attack,
  single bright color for non-threshold IVs). Should be a JS dropdown next to the
  existing moveset/scenario selectors.

* **Pretty-print move and species names in reports** — HTML output, analysis
  sections, and console summaries should use natural casing (e.g. "Gigaton Hammer"
  not "GIGATON_HAMMER", "Galarian Stunfisk" not "STUNFISK_GALARIAN"). The CLI
  argument parsing can stay uppercase/underscore for ease of typing.

* **List all valid options in CLI help** — Flags like `--group` and `--charged`
  should enumerate all valid choices in `--help` output (e.g. list all known
  PvPoke groups, list all legal moves for the species). Currently only a few
  example group names are shown. Get user input before fully
  implementing this, though, because listing all legal moves might
  make the help text too long.

* **Table sorting** We have a lot of tables that would be a bit more
  useful if we made it so that clicking on the headers sorted the
  table by that column (the standard thing where you click it once to
  sort descending, and a little arrow appears to show how you've
  sorted, then you click it again to reverse the sort order, the arrow
  changes direction, you click on another column to sort by that
  column and the arrow from the first column goes away, etc).

* ~~**Threshold Tiers intro: document multi-axis anchor filtering**~~ —
  **Done 2026-04-16** (Lechonk CD prep Session 1). Intro rewritten as
  short lead + nested `<ul>` covering subset, crossed-cutoff, and
  slayer-axis IV-count cases. Rendering gained (a) an "Anchors we get
  for free" collapsed `<details>` per tier, surfacing anchors on axes
  the tier doesn't cut off but every IV still clears, and (b) a
  parent-tier diff callout in the header (e.g. `(−73 vs Balanced,
  def-sacrificing / hp-low spreads excluded)`) when a tier's IVs are
  a strict subset of a looser tier's. Verified against Annihilape m0
  (`High Bulk` tier: 5 primary def-bulk bullets, 1 free atk-mirror
  anchor, −73 vs Balanced callout).

## Diagnostics / observability

* ~~**Switch deep_dive.py from print statements to a structured
  logger**~~ — **SHIPPED Post-S5 S2a-S2d** (2026-04-15/16). Helper
  module at `scripts/deep_dive_logging.py` (commit `e300862`);
  `deep_dive.py` + `deep_dive_slayer.py` ported (`1261d33`); log-
  cleanup utility at `scripts/clean_logs.py` (`ca089bb`); docs
  reference in `CLAUDE.md` "Debugging conventions" and
  `DEVELOPER_NOTES.md` "Log file layout" (`6510c69`). Per-run log
  files land under `userdata/logs/YYYY-MM/`, canonical live-monitor
  command is `tail -f userdata/logs/latest.log`, workers route
  through `worker_log_setup` instead of bare prints.

## Performance

**Architecture note (2026-04-07)**: The BeeWare/iOS-pure-Python constraint
has been DROPPED. Mobile is no longer a meaningful use case for the deep
dive scripts. We can now use numba, Cython, C extensions, etc. — though
the core `gopvpsim/` library should still avoid making mobile impossible
in case we want to revisit it. The optimization work below targets the
desktop deep-dive workflow.

**Round 1 + Round 2 + chunking optimizations are SHIPPED** (see Shipped
section). Real-world impact: 9hr → 6 min on the actual deep-dive workload.
Round 3 (numba JIT for the inner sim loop) was deprioritized because
fastmath was confirmed a dead-end and the workload is no longer the
bottleneck.

* ~~**Deep-dive analysis+narrative phase is 20+ min single-threaded**~~
  *(pulled into current plan as S8a on 2026-04-17)* — profile numbers
  and candidate targets live in `~/.claude/plans/post-s5-oinkologne-arc.md`
  §S8a. Pulled forward because S9+S10 full dives both benefit from the
  speedup; scope is contained (two vectorisation targets). Not post-ship
  anymore.

* ~~**HTML file size**~~ — *S11+S12 shipped 2026-04-21 (commits
  f839e65 S11 audit, 1fe232a R1 tooltip dedup, 5ad2d4b R2
  --shared-plotly).* A/B on a small Oinkologne dive:
  baseline 38.12 MB, R1+R2 21.72 MB (**-43.0%** file size,
  **-40.5%** gzipped). Byte budget + ranked approach list in
  `docs/s11_html_size_audit.md`. Deferred follow-ups (not currently
  painful enough to pursue): lazy per-scenario SCORES_GZ blobs
  (Rank 3 — regresses `file://` portability), class= dedup
  (Rank 4 — gzip already captures most), defer-DOM collapsibles
  (Rank 5 — wrong bottleneck). Reopen only if the post-R1+R2 file
  size becomes painful again.

* **Better slayer iteration progress reporting** — The current progress
  prints fire only when a `pool.imap_unordered` chunk completes. With
  10 chunks each taking ~85 minutes, the first progress line doesn't
  appear for 85 minutes. *Partly addressed in 2026-04-07 by chunking
  to ~100 chunks (commit 8498ec4), but consider further refinement
  if individual chunks become slow again.*

* **Incremental slayer cache flush** — The slayer iteration cache
  (`SlayerCache` in `scripts/slayer_cache.py`) currently does one read
  at startup and one save at the end. If a long run crashes mid-iteration
  (e.g. 28 minutes into a 30-minute run), all the work done in that run
  is lost. Add periodic flush to disk after each slayer round so a crash
  loses at most one round's worth of sims. Tiny code change, big peace
  of mind.

* **Form-change path speedup (Aegislash Shield, Mimikyu, Morpeko)**
  — *Discovered 2026-04-19 during the out-of-band Aegislash GL dive
  against Orlando top-32.* Mirror-slayer Round 1 on Aegislash (Shield)
  projected ~25-30 min per moveset (~10× the Blade-side baseline) at
  ~700 sims/s vs the 7,000 sims/s Phase 2 baseline. Correctness is fine
  (validated by `tests/test_aegislash_vs_azumarill_form_change`); the
  9.5M-sim scale just magnifies the form-change per-sim overhead.

  **Suspected dominant costs** (unprofiled):

  1. `apply_form_change(bp, opponent)` does a full state swap: base
     stats (atk/def/hp), active moveset, `bestChargedMove` reselection,
     per-move cached damage tables invalidated. Fires every time
     Aegislash (Shield) lands its first charged move, which is nearly
     every sim in a mirror-slayer scale run.
  2. Per-turn `attacker.current_form_trigger` / `defender.current_form_trigger`
     property evaluation on every charged-move event, even for species
     with no form change (no-ops but not free). Cheap individually;
     compounded across 9.5M sims it adds up.
  3. Damage-and-timing caches that key on (attacker form, opponent) get
     stale on form change and rebuild from scratch the next call. If
     caching is per-form, the form swap is a mandatory invalidation.

  **Why Shield hits this harder than Blade:** Shield-focal transforms
  on every charged move (every battle). Blade-focal transforms only
  when Aegislash *shields* an opponent's charged move — conditional
  on shield count and policy — so the code path runs much less often.

  **Perf session plan** (~2 hours):

  * `cProfile` or `py-spy` on `scripts/deep_dive.py 'Aegislash (Shield)'`
    with `--opponents 3 --mirror-slayer-rounds 1`, compare to same
    command on Aegislash (Blade). Flame graph diff highlights the
    form-change-only hot path.
  * Likely interventions: (a) precompute both forms' damage tables
    up front and swap by pointer, (b) lazy-invalidate damage caches
    per-opponent rather than per-form, (c) inline the form-trigger
    checks into a single type-dispatch so non-form-change species
    pay zero per-turn cost.
  * Success criterion: Shield mirror-slayer within 2× Blade's rate
    (rather than today's 10×).

  Deferred because correctness is fine and Aegislash isn't on the
  pre-ship critical path. Pull forward if Aegislash becomes a frequent
  dive target post-CD.

## Schema simplification

* **TOML simplification triggers** *(collect friction, don't act yet)* —
  Worry surfaced 2026-04-09: the legacy JSON threshold files were three
  keys; the current TOML schema is ~530 lines of docs and Annihilape's
  hand-authored file is ~180 lines. Sample size of one species (plus a
  one-line tinkaton stub) is too small to design a simplification
  against — Annihilape is also the *worst* canary because its
  Lurgan/acidicArisen historical provenance pressure makes it
  documentation-heavy in ways most species won't be.
  **Action**: when authoring the *next* species TOML (Tinkaton CD prep,
  Goodra, etc.), aim for the smallest file possible — lean on the
  auto-fallback hard, skip provenance you don't need. If you reach for
  a schema feature and it feels heavy, write a one-liner here noting
  *which* feature and *why*. Three friction observations in a row is
  the action threshold; until then, collect.
  **Two candidates already named** without acting:
  1. The Level 1/2/3 anchor distinction is a doc artifact, not a
     schema artifact — the resolver just looks at which optional
     fields are populated. Could be re-presented as "fill in whichever
     fields you know" instead of three named precision tiers. Doc
     rewrite, not code rewrite — cheap whenever it stops feeling
     helpful to teach the levels separately.
  2. The mandatory spread/anchor split is overhead for one-off CMP
     anchors. Most species would benefit from inlining `ivs = [...]`
     or `above_atk = X` directly on the anchor instead of needing a
     separate `[spreads.x]` table. Don't *remove* the split — it earns
     its keep when multiple anchors share a spread (cf. Annihilape's
     `lurgan_ape` referenced by both `cmp_vs_lurgan` and
     `lickitung_brkp_above_lurgan`) — just make it optional.
  **Meta-rule**: distinguish complexity that *enables provenance*
  (description fields, source fields, the multiple breakpoint
  precision levels) from complexity that's *structural overhead*
  (deep nesting, mandatory spread/anchor split for one-offs).
  Simplifications target the second category; don't accidentally cut
  the first.

## Refactoring

* **Split `scripts/deep_dive.py`** *(deferred from 2026-04-09; not
  blocking, but file is now ~6100 lines as of 2026-04-10)* — After the structured IV
  categories shipped, the file is approaching the size where edits
  start fighting the line-cap. Concrete extraction targets, in rough
  order of independence:
  1. **`scripts/deep_dive_lib/categories.py`** — `IVCategory` dataclass,
     `build_iv_categories()`, `_stat_cutoffs_from_anchors()`,
     `_format_stat_cutoffs()`, `_composite_tradeoff_prose()`,
     `_matchup_subtitle()`. Pure-Python, already isolated, already has
     unit tests in `tests/test_iv_categories.py`. Easiest move.
  2. **`scripts/deep_dive_lib/anchor_flips.py`** — `_aggregate_flips_by_anchor()`,
     `_render_anchor_flip_bullets()`. Pure-Python, already isolated,
     already has tests in `tests/test_flip_aggregator.py`.
  3. **`scripts/deep_dive_lib/slayer.py`** — `iterative_slayer_discovery()`,
     `categorize_slayers()`, `_slayer_iter_worker()`, related helpers.
     The multiprocessing entry points complicate this — workers are
     resolved by qualified name, so the move requires careful import
     plumbing.
  4. **`scripts/deep_dive_lib/render.py`** — `generate_analysis_sections()`,
     the per-section helpers (`_render_notable_ivs_section`,
     `_iv_label`, `_tier_badge_html`, `_threshold_desc`,
     `_hover_text`, etc.), the CSS string. This is the actual monster
     (~1500 lines and growing). Needs a small "renderer context"
     dataclass first to avoid passing a 15-arg tuple around.
  5. **`scripts/deep_dive_lib/sweep.py`** — `iv_sweep()`, the worker
     init/run pair, `screen_movesets()`, `compute_iv_metadata()`,
     `group_ivs_by_stat_profile()`. Numba-touching code; same
     multiprocessing import-plumbing concern as slayer.
  Remaining in `scripts/deep_dive.py` after all five steps: argument
  parsing, the top-level orchestration in `main()`, and the legacy
  non-interactive `generate_html()` (already on the chopping block —
  see "Non-interactive `generate_html` is now strictly worse" above).
  Test split: each module gets its own `tests/test_<module>.py`; the
  existing tests already prove the importlib pattern works for
  modules that can't import from `gopvpsim` directly.
  **Recommendation**: do this in a dedicated session, not interleaved
  with feature work — refactor diffs and feature diffs shouldn't ride
  the same commit. Mechanical (file moves + import fixes) so it
  shouldn't take long once started; the risk is multiprocessing
  worker resolution and CSS-string fragment positioning.

## Moveset / variant comparison tool

* **Generalise the article generator into a loadout comparator**
  *(follow-up from the Oinkologne CD article arc)* — most of the
  infrastructure built for `scripts/generate_article.py` is really a
  "compare loadout A vs loadout B" pipeline with a CD framing bolted
  on. Concrete user questions this should answer:
  - "I'm playing in a Championship Series event and want to know if
    I should run Forretress with Volt Switch or Bug Bite." (Two fast
    moves on the same species.)
  - "I want to see the difference between Shadow Forretress and
    normal Forretress." (Same moveset, different base form /
    stat-multiplier pair.)
  - "Which Forretress do I want on my team — Volt Switch Shadow, Volt
    Switch normal, Bug Bite Shadow, or Bug Bite normal?" (2 fast-move
    options × 2 form options = 4 loadouts.)
  - CD catches that weren't tied to a new move announcement — just
    "is the shadow worth chasing for this slot."

  **MVP (N=2) SHIPPED 2026-04-18 (S10)** at
  `scripts/compare_loadouts.py`; commits `ebba13f` (MVP),
  `8530f19` (wired into CD article), `21d3393` (source-dive
  listing), `69bdf64` (spec `order` field), `53d7050` (Oinkologne
  spec puts Female first). Output lands at
  `userdata/website/comparisons/<slug>/index.html`; the Oinkologne
  M-vs-F comparison is live at `.../oinkologne-male-vs-female/`.

  **Design constraint:** stay loadout-list-keyed, not A/B-keyed. Use
  `loadouts: list[LoadoutSpec]` in the data model even at N=2; use
  pairwise-delta iteration (`itertools.combinations`) rather than
  `a - b` shortcuts. Upgrade to N=4 is then a renderer extension, not
  a data-model rewrite.

  **N=4 ceiling:** 4 covers the canonical (moveset × form) cross
  (Forretress case above). More than 4 makes the matchup-delta table
  unreadable and the verdict ambiguous. Don't design past this.

  **Remaining post-S10 work:** N=3 and N=4 renderer support, verdict
  templating for N-way ranking (MVP keeps verdict simple, just for
  Male-vs-Female).

  Reuse of the S8 work: matchup-delta table, per-opponent win-rate
  diff, +Flip/No-flip/-Flip pills, PvPoke single-battle drill-through
  links, move-stat side-by-side table. What changes vs CD article: no
  "old default" vs "new CD move" framing; instead a generic loadout
  comparison with the user picking all sides. Flagged 2026-04-17 by
  Michael after seeing the Oinkologne article render.

## User-facing documentation (post-arc)

* **Explainer docs for expert-but-non-programmer readers** *(queue
  after the post-S5 Oinkologne arc ships)* — audience is roughly
  RyanSwag's level of PvP game understanding, but with no programming
  background or interest. Separate audience from everything in
  `docs/` today (which assumes the reader is reading source).
  **The full topic list is a conversation Michael wants to have at the
  start of the task, not a fixed scope** — the five topics below are a
  starting draft captured during S8 (2026-04-17) so the idea doesn't
  get lost, and Michael explicitly asked that they not be removed, but
  a first-pass planning session should (a) add topics we haven't
  thought of yet, (b) reorder by what's causing the most reader
  confusion at the time the task starts, (c) decide screenshot
  authoring cadence, and (d) decide whether each topic gets its own
  page or whether related topics merge into a single guide. Starting
  draft, in current priority order:
  1. **Envelope-position metric** (S4) — what "elevated-band-crosser"
     means for a category, why it matters when you're deciding which
     IV to chase, what the `mean_delta` / `spread` / `shape` tuple
     says about the category in plain language. Needs **annotated
     screenshots** of the Notable IVs section with the envelope
     annotation visible, plus a contrasting screenshot of a category
     with a very different shape.
  2. **Threshold Tiers** — tier vs category vs anchor, what the stat
     cutoff bullets mean, why overlapping tiers are intentional. The
     current in-page intro (rewritten 2026-04-16, Session 1) is good
     enough for an expert scanning the page but lacks the worked
     example a non-programmer needs. Screenshots of a tier card with
     each part labeled.
  3. **IV Flavor Guide** — what the purple "IV Flavor Guide" zone
     does, how to read a flavor, what a "namesake" is, why two flavors
     with the same stat signature merge. Owe this to acidicArisen per
     `project_acidic_arisen_writeup_commitment.md`.
  4. **CD article page** — how to read the matchup-delta table,
     what the PvPoke multi-battle link does when you click it, what
     "flip" means here. Short; mostly a figure tour.
  5. **Deep-dive scatter plot** — color modes, hover cards, the
     Shields / Opponent-IVs / Bait dropdowns, what "anchor-clear
     overlay" shows.
  Shape: `docs/guides/*.md` (new subdir) or a landing page at
  `userdata/website/guides/`. Decide placement when the first guide
  lands. Screenshots authored manually; keep them under
  `docs/guides/screenshots/` (or `userdata/website/guides/images/`)
  and compress before committing — the existing policy against
  embedding large binaries still applies.
  Not urgent until a second user starts engaging with the tool; until
  then the primary reader is Michael, who can read source.

## Low priority

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support.

---

Historical/shipped work lives in `CHANGELOG.md`.
