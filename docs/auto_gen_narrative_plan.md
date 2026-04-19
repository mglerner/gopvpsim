# Auto-generated narrative plan

**Date:** 2026-04-19. **Status:** design; ready to execute tomorrow
morning (2026-04-20) once tonight's overnight chain completes.

## Problem

Every TOML under `articles/` and `thresholds/` carrying a Species
narrative block currently has `authored_by = "ai"` on the intro,
meta_role, and verdict sections. The text is Claude-drafted prose
not yet human-reviewed. Shipping the Oinkologne CD article with that
prose in it violates our own policy — the `feedback_expert_narrative_not_autogen`
memory says narrative should be expert-authored or auto-generated,
not LLM-drafted. Ship-blocker for the 2026-05-09 CD.

## Scope

Five TOMLs have affected blocks, with identical structure:

- `articles/oinkologne-cd-2026-05.toml`
- `thresholds/oinkologne.toml`
- `thresholds/oinkologne_female.toml`
- `thresholds/aegislash_blade.toml`
- `thresholds/aegislash_shield.toml`

Each has three narrative tables: `[intro|Species.intro]`,
`[meta_role|Species.meta_role]`, `[verdict|Species.verdict]`, for a
total of **30 prose fragments** across 5 TOMLs × 6 fields (`intro.body`,
`meta_role.{good_at,bad_at,team_role}`, `verdict.{editorial,outlook}`).

## Classification

| Field                 | Classification          | Rationale                                                                                   |
| --------------------- | ----------------------- | ------------------------------------------------------------------------------------------- |
| `intro.body`          | **A (partial auto)**    | Mix of facts (stats, win-rate delta, CD date) and editorial adjectives. Template the facts. |
| `meta_role.good_at`   | **A (auto)**            | Top-N positive-delta matchup list grouped by opponent type. Directly templateable.          |
| `meta_role.bad_at`    | **A (auto)**            | Mirror of good_at; same template.                                                           |
| `meta_role.team_role` | **B (delete for ship)** | Requires teambuilding knowledge outside the sim (synergies, role-fit).                      |
| `verdict.editorial`   | **B (delete for ship)** | Editorial catch-priority / XL / ETM judgment.                                               |
| `verdict.outlook`     | **B (delete for ship)** | Pure meta speculation ("rises and falls with Flyer pressure").                              |

**Split:** 15 A-fields to auto-generate, 15 B-fields to delete.

## Template specs (A-bucket)

### `intro.body`

Input: species display name + base stats, CD move (from cd_prep), old
move (from reference), aggregate win rate w/ CD, aggregate win rate
w/ old, top-3 positive-delta opponents, top-3 negative-delta opponents.

Output:

```
{Species} ({atk}/{def}/{hp}). {cd_move} adds {type} coverage.
GL aggregate win rate: {wr}% ({old_move} baseline: {old_wr}%, {delta_sign}{delta}pp).
Biggest wins: {opp_pos_1} +{X}pp, {opp_pos_2} +{Y}pp, {opp_pos_3} +{Z}pp.
Biggest losses: {opp_neg_1} {-X}pp, {opp_neg_2} {-Y}pp, {opp_neg_3} {-Z}pp.
```

Example for Male Oinkologne:

> Male Oinkologne (186/153/242). Mud Slap adds Ground coverage. GL
> aggregate win rate: 43.0% (Tackle baseline: 33.3%, +9.7pp). Biggest
> wins: Empoleon +77pp, Steelix +65pp, Galarian Stunfisk +63pp. Biggest
> losses: Altaria -25pp, Galarian Moltres -33pp.

Length: ~50% of Claude's draft, carries the same key facts, no editorial
adjectives to hallucinate.

**Opponent "type" field for the CD move:** reuse the gamemaster move-
type lookup (`gopvpsim.moves.MOVE_TYPE[cd_move_id]`).

**Article-side intro only:** adds form-comparison framing ("which form
to prioritize"). Dive-side intro stays species-only. Achieved by the
renderer branching on whether the TOML has a `form_comparison` block.

### `meta_role.good_at` / `meta_role.bad_at`

Input: per-opponent matchup-delta (CD move - old move), sorted by delta.
Bucket by opponent primary type.

Output:

```
Wins {Species} picks up by adding {cd_move}:
- vs {type1}: {opp1a} (+{X}pp), {opp1b} (+{Y}pp), {opp1c} (+{Z}pp)
- vs {type2}: {opp2a} (+{X}pp), {opp2b} (+{Y}pp)

Breakpoint-dependent wins at {Species}'s {atk_stat} Attack:
{opp} (+{X}pp, atk breakpoint {Y}), ...
```

`bad_at` is the mirror with negative deltas.

Example for Male Oinkologne good_at (rendered):

> Wins Male Oinkologne picks up by adding Mud Slap:
> - vs Steel-type: Empoleon (+77pp), Steelix (+65pp), Galarian Stunfisk (+63pp)
> - vs Ghost-type: Dusclops (+65pp), Sableye (+55pp), Galarian Corsola (+50pp)

**"Breakpoint-dependent wins"** block is only emitted when (a) an
Atk-IV threshold moves the matchup outcome AND (b) the species' stat
spread puts it on the right side of that threshold. Heuristic: filter
per-opponent win cells by "flip depends on atk_iv >= N" relationship.
Implementation-TBD; skip the block on first cut if it's hard to detect
robustly — the type-grouped list is the core content.

## Bonus A-item: promote narrative flavors to paste-box tiers

**Problem observed 2026-04-19** on the Tinkaton GL dive: the narrative
zone names four flavors ("General Good," "Fortified Azumarill," "Lapras
Slayer," "Fortified Blastoise") with specific cutoffs (e.g. Fortified
Azumarill = def ≥ 143.52, HP ≥ 138). But the "Check my collection"
paste-box only matches user IVs against `DATA.tiers`, which for this
dive contains just `GH Great` and `GH Good` — the flavors are
narrative-prose only, invisible to the membership-check code. A user
who wants to know "do any of my Tinkatons qualify as Fortified
Azumarill?" has to eyeball def/HP values against the prose cutoffs
manually.

**Fix:** the narrative-flavor derivation module already computes each
flavor's stat cutoffs (`atk_cut`, `def_cut`, `hp_cut` in the
`FlavorSpec` dict). Emit each flavor as an additional entry in
`DATA.tiers` with its name + cutoffs, so the paste-box's `byTier`
grouping picks them up automatically. No paste-box code changes
needed; the existing `rec.matched[]` logic cross-checks against every
tier.

**Sequencing with the base auto-gen work:** this is the same module
(`deep_dive_narrative.py` or wherever flavor derivation lives today),
just a second output hook. Do it in the same morning session as the
primary auto-gen work; one commit.

**Deduplication concern:** flavors are derived from underlying
threshold tiers, so "General Good" (flavor) and "GH Good" (tier) may
have identical cutoffs. Paste-box would show the user's mon under both
names — noisy. Resolution: when a flavor maps 1:1 to an existing tier,
suppress the flavor entry OR label the flavor as a tier-alias so the
paste-box renders them merged. Implementation detail; decide during
the morning session once we see the actual overlap pattern.

## Bonus A-item: atk-weight labels on Notable IVs

**Not replacing existing prose** — adds new rendered content.

Classify each Notable IV spread (attack, defense, stamina) relative
to rank-1 (stat-product-max) and emit a label:

| Label               | Heuristic                                                               |
| ------------------- | ----------------------------------------------------------------------- |
| "rank-1"            | Matches the stat-product-max spread exactly                             |
| "no atk weight"     | Same atk as rank-1, bulk close to rank-1                                |
| "slight atk weight" | atk slightly above rank-1 atk, bulk slightly below rank-1 bulk          |
| "heavy atk weight"  | atk much above rank-1 atk, bulk much below rank-1 bulk                  |
| "CMP spread"        | Atk tuned specifically to pass a named CMP anchor in the threshold TOML |
| "bulk-max"          | Stat product within X% of rank-1 but higher HP or Def                   |

Scoring function (first cut, tune during implementation):

```python
def classify_atk_weight(iv, rank1):
    atk_delta = iv.atk - rank1.atk
    bulk_delta = (iv.def_ + iv.sta) - (rank1.def_ + rank1.sta)
    if atk_delta == 0 and bulk_delta == 0:
        return "rank-1"
    if atk_delta == 0 and bulk_delta >= -2:
        return "no atk weight"
    if atk_delta <= 3 and bulk_delta >= -8:
        return "slight atk weight"
    if atk_delta > 3 and bulk_delta < -8:
        return "heavy atk weight"
    # ... CMP / bulk-max / fallthrough
```

Renders as a small badge on each Notable IV card, next to the IVs line.
Matches RyanSwag's vocabulary (T2 in the 2026-04-16 gap analysis doc).

## Renderer architecture

New module `scripts/auto_gen_narrative.py`:

- `render_intro(article_or_species_data, sim_results) -> str`
- `render_good_at(species_data, sim_results) -> str`
- `render_bad_at(species_data, sim_results) -> str`
- `classify_atk_weight(iv, rank1) -> str`

Called from:
- `scripts/deep_dive_rendering.py::render_species_narrative()` — replaces
  the TOML-block reads with generator calls for intro / good_at / bad_at.
  team_role / editorial / outlook sub-blocks are skipped entirely when
  the B-fields are absent (existing "skip empty" behavior handles this).
- `scripts/generate_article.py::render_intro_section()` / `_render_meta_role_section()`
  — same swap on the article side.
- `scripts/deep_dive_rendering.py::render_notable_ivs_card()` — new
  atk-weight badge.

**TOML state after migration:**
- Delete 15 B-fields across 5 TOMLs.
- Delete the 15 A-field contents (template now takes over); keep the
  section header for auto-prose anchor.
- Delete all `author` / `authored_by` attribution lines — no prose to
  attribute once templates take over.
- Net: the narrative sections in each TOML shrink to empty shells or
  get removed entirely. Renderer generates all visible content.

## Two-mode enforcement

### Hard: pre-commit hook

File: `.githooks/pre-commit` (or wire into existing `.claude/settings.json`
hooks if you prefer tool-level over git-level).

```bash
#!/usr/bin/env bash
# Reject authored_by = "ai" in ship-tracked TOMLs.
AI_FILES=$(git diff --cached --name-only | \
    grep -E '^(articles|thresholds)/.*\.toml$' | \
    xargs grep -l '^authored_by = "ai"' 2>/dev/null)
if [[ -n "$AI_FILES" ]]; then
    echo "ERROR: AI-drafted prose in ship-tracked TOMLs:"
    echo "$AI_FILES"
    echo
    echo "Policy: articles/ and thresholds/ must not carry"
    echo "  authored_by = \"ai\""
    echo "Either auto-generate via scripts/auto_gen_narrative.py"
    echo "and remove the block, or human-author and set"
    echo "  authored_by = \"human\" or \"mixed\"."
    exit 1
fi
```

Wire via `git config core.hooksPath .githooks` once (project-local, not
shared unless committed). Alternatively, land a PostToolUse hook in
`.claude/settings.json` that catches Edit/Write on the affected paths.

### Soft: CLAUDE.md directive + memory

Add a paragraph to CLAUDE.md under a new "Ship-mode narrative policy"
heading:

> When drafting prose for blocks under `articles/` or `thresholds/`
> Species narrative sections (`intro.body`, `meta_role.*`, `verdict.*`),
> default to **suggesting an auto-gen template** (classify sim data,
> fill template blanks via `scripts/auto_gen_narrative.py`) rather than
> writing prose directly. If the block can't be auto-gen'd honestly
> (editorial judgment, teambuilding synergies beyond what the sim
> knows), say so and recommend leaving it for the human. Claude-drafted
> prose with `authored_by = "ai"` is a pre-commit failure for these
> files.

Plus extend the existing `feedback_expert_narrative_not_autogen` memory:
sharpen the distinction between "template-from-data" (OK, Path A) and
"LLM-draft" (not OK, Path B).

### Mental-mode distinction (two-mode design)

- **Ship-mode** (articles/ and thresholds/ narrative TOMLs, rendered
  dive/article HTML): No Claude prose. Auto-gen from sim data, or leave
  empty, or human-author. Hard-enforced via pre-commit hook.
- **Exploration-mode** (session chat, one-off `/tmp/` analysis, docs/
  design work, planning files): Claude prose is fine. No enforcement.

Key boundary: **anything git-committed under `articles/`, `thresholds/`,
or rendered HTML that ships to the site is ship-mode.** Everything else
is exploration-mode. The pre-commit hook enforces the path-based
boundary; the CLAUDE.md directive enforces the mental boundary.

## Morning execution plan (2026-04-20)

Depends on the overnight 2026-04-19 chain having completed.

**No re-dives needed.** All template inputs (scores, matchup deltas,
notable IVs, anchor flips, threshold tiers) are already embedded in
the dive HTMLs — `SCORES_B64` blob carries the per-(IV, scenario,
opponent) scores; tier / anchor / boundary data is also embedded.
Workflow is **HTML patching, not simulation regeneration**:

- **Dive side:** extend `scripts/patch_dive_species_narrative.py` to
  (a) decode `SCORES_B64`, (b) run the template, (c) inject generated
  prose in place of reading from TOML. Same patcher pattern we
  already use to inject narrative into dive HTMLs. Seconds per dive.
- **Article side:** `python scripts/generate_article.py Oinkologne
  great "Mud Slap"` re-reads the dive HTMLs and rebuilds the article
  in ~5 seconds. No re-dive.
- **Atk-weight badges:** new patcher (or extend
  `patch_dive_tier_anchors.py`) that finds each `.dd-rec-card`'s IV
  spread, classifies, injects a badge. HTML surgery only.

This path also applies to the **dives-1-3 retroactive patch** (morning
task for the index.html landing-page fix) — same HTML-only surgery;
no re-dives there either.

**Order of operations:**

1. **Delete 15 B-fields** across 5 TOMLs. Trivial: remove the
   `team_role`, `editorial`, `outlook` keys and their content. One
   commit.
2. **Write `scripts/auto_gen_narrative.py`** with the three render
   functions + atk-weight classifier. Uses cached dive data from
   `userdata/` (same data the dive HTML renderer uses). ~2-3 hours.
3. **Wire auto-gen into `deep_dive_rendering.py` +
   `generate_article.py`** — replace TOML-block reads with generator
   calls. Remove the `authored_by = "ai"` TOML-block content for the
   15 A-fields. ~1 hour.
4. **Atk-weight badges on Notable IVs cards.** Same module, new
   classify_atk_weight function, new render_atk_weight_badge call in
   the Notable IVs card renderer. ~1-2 hours.
4b. **Promote flavors to paste-box tiers.** Emit each narrative flavor
   as a DATA.tiers entry with its cutoffs so the "Check my collection"
   paste-box can report flavor membership. Resolve the dedup question
   (flavor = tier alias vs suppress) based on actual overlap seen.
   ~30 min.
5. **Install pre-commit hook** + **update CLAUDE.md** with the
   ship-mode directive. ~30 min.
6. **Regenerate Oinkologne article + dives** from the fresh
   overnight-chain data to verify auto-gen output reads cleanly.
   Compare against Claude's drafts — auto-gen should preserve the
   key facts, drop the editorial adjectives, and feel more scannable.

**Total:** ~6-8 hours. Realistic for one focused morning.

## Out of scope tonight / in-session

- Actually writing `scripts/auto_gen_narrative.py` — defers to post-chain
  when the real dive data is available to validate templates against.
- Editing any TOML under `articles/` or `thresholds/` — production paths
  read by dives 5-10 of the running chain; risk of subprocess confusion.
- Installing the pre-commit hook — wait for the B-field delete to land
  so the first commit after install isn't a rejection.

## Open questions

- **CMP-spread detection for the atk-weight classifier.** Requires
  reading the species' CMP anchors from the threshold TOML and
  matching IVs whose atk hits one of those tie-breakers exactly. Spec
  later during implementation; fall back to the atk-delta heuristic
  if detection is hard.
- **Should the renderer emit a "human-authored version pending" badge
  on B-fields that are currently deleted?** Or silently omit? Default:
  silently omit. The B-fields are genuinely not required; badge-less
  feels cleaner than "we know this is missing" self-commentary.
- **Do we want the renderer output itself to be TOML-cacheable?** I.e.
  auto-gen once, cache the prose into a TOML block with
  `authored_by = "auto"` or similar. Pro: human reviewer can edit the
  auto-gen'd prose to polish it and promote to `authored_by = "human"`.
  Con: defeats the "always re-derive from live data" cleanness.
  Default: stateless renderer; no cache. Revisit if we actually want
  polish-editing workflow.
