# Article authoring workflow

Companion to `docs/article_generator_design.md` and
`docs/article_schema.md`. Those cover the generator internals and the
TOML schema; this doc covers the human-facing workflow — how to go
from "we want a page about species X" to a shipped article.

Written 2026-04-18 after the Oinkologne F1 session. Revisit as the
pipeline evolves.

---

## Step 0: Which shape?

Two article shapes are in play. Pick before starting.

### Shape A: CD-move article (Oinkologne model)

**When:** a Community Day adds / rebalances a move and the question is
"does the new move change the species' PvP role."

**What it compares:** the CD move's moveset against the pre-CD default.
Every mechanical section (Move Comparison, Meta Coverage, Matchup
Delta, IV Recommendations, Verdict) is framed as a delta.

**Pipeline status:** fully supported by `scripts/generate_article.py`.
Worked end-to-end on Oinkologne 2026-04-18.

### Shape B: New-species / meta-entry article (Aegislash model)

**When:** no CD move trigger, but the species' meta relevance has
shifted — e.g., a form-change mechanic finally matters, a new move
already landed in a prior season and is now bearing fruit, a species
graduated into the top meta via rebalances. The question is "this
species is now relevant, what does it do."

**What it compares:** the species against the meta, absolute. No
move-vs-move delta columns.

**Pipeline status:** NOT YET fully supported by
`scripts/generate_article.py` (CLI requires a `cd_move` positional).
Current path: use `scripts/render_article.py` with a hand-authored
TOML, or drop Move Comparison / Matchup Delta sections and ship a
slimmer article via `[[sections]]` overrides. Extending the generator
with a `--no-cd-move` mode is a separate future task.

---

## Shape A workflow (CD article)

Step-by-step, what ran on Oinkologne:

1. **Deep dive** — run `scripts/deep_dive.py` for the focal species
   (one invocation per form for dual-form species; see TODO.md
   "Pre-ship: cross-form opponent coverage" for the form-sibling
   opponent-pool rule). Output lands in `userdata/website/<slug>/`.

2. **Form comparison (if applicable)** — for dual-form species, run
   `scripts/compare_loadouts.py <comparison-spec.toml>` to produce
   the per-form win-rate delta fragment.

3. **Mechanical article** — run `scripts/generate_article.py <species>
   <league> "<CD move>"`. Reads the article TOML
   (`articles/<slug>.toml`) for front-matter + form-comparison spec
   + `[meta_role]`, reads the dive HTML for the embedded sim data,
   reads the gamemaster for move stats. Produces
   `userdata/website/articles/<slug>/index.html`.

4. **Author `[meta_role]`** — open a Claude session. Brief:

   > Extract sim data from
   > `userdata/website/articles/<slug>/index.html`: top flips by
   > |delta| from the Matchup Delta table, aggregate win rates from
   > Meta Coverage, notable form asymmetries. Draft `good_at` /
   > `bad_at` / `team_role` for `articles/<slug>.toml`'s `[meta_role]`
   > block, authorship=expert. Target RyanSwag voice
   > (`docs/reference_deep_dives/ryanswag/`), NOT JRE. Follow the
   > calibration warning in `docs/article_schema.md` "Voice target":
   > lead with sim-supported claims (deltas, win rates); do NOT
   > invent game-flow archetypes ("mid-game pivot" etc.); do NOT
   > overstate meta viability if aggregate win rate is below 50%.

   Claude drafts; human reviews for tone (community framing check —
   is the species actually meta, or anti-meta / niche?) and for
   confabulated archetype language.

5. **Regenerate + visual check** — re-run `generate_article.py`,
   `open <path>/index.html` in the default browser, read the Meta
   Role section end to end.

6. **Commit + push** per commit-frequency memory.

---

## Shape B workflow (new-species article, partial support)

Until `generate_article.py` gains a `--no-cd-move` mode, use one of:

### Option B1: `render_article.py` with hand-authored TOML (available today)

- Populate `articles/<slug>.toml` with front-matter + explicit
  `[[sections]]` blocks for each section you want (Introduction,
  Typing & Bulk, Moveset Discussion, Performance in Great League,
  etc. — pick what fits the species; no required order).
- Add `[meta_role]` block same as Shape A.
- Run `python scripts/render_article.py articles/<slug>.toml`.
- Publish as usual.
- Cost: every mechanical section is hand-authored. Per-opponent
  matchup data has to be manually transcribed from the dive; no
  auto-generated Move Comparison table.

### Option B2: Generator enhancement (future)

Extend `generate_article.py` to accept `--no-cd-move` (or equivalent
sentinel). The generator would:

- Skip `Move Comparison`, `Matchup Delta` (both CD-relative sections).
- Reframe `Meta Coverage` as absolute win-rate grid (no "each form's
  CD-move win rate" copy; just "aggregate win rate").
- Reframe `Verdict` as "species relevance" rather than "upgrade /
  sidegrade" framing.
- Keep `Form Comparison` and `IV Recommendations` unchanged.
- Keep `Meta Role` unchanged (Michael's call 2026-04-18: same schema
  works for species-vs-meta absolute framing, not just move-vs-move).

Tracked as a future TODO; not scoped for the Oinkologne CD ship
window.

---

## `[meta_role]` authoring discipline

Applies to both shapes. Distilled from the Oinkologne session.

### Before drafting

Pull the raw material first, don't write from vibes. The essentials:

- **Top flips by |delta|** from the Matchup Delta table (if Shape A)
  or the matchup win-rate table (if Shape B). Group by opponent type
  for the "good at" story. This is what `good_at` and `bad_at`
  build from.
- **Aggregate win rate** from Meta Coverage. This is the honesty
  anchor — it calibrates whether the species is meta (>50%
  aggregate) or anti-meta counter-pick (<50%).
- **Form asymmetries** (dual-form species) — which form wins on
  aggregate, which form unlocks unique flips. This drives the
  team-role paragraph's form-choice advice.
- **Threshold tier summary** from the dive — which tiers are the
  "recommended" vs "slayer" variants. This informs team role
  (bulk-first vs attack-weighted build advice).

A one-off Python script to extract the Matchup Delta rows from the
built HTML is the fastest path; see the Oinkologne session's
extraction for a pattern.

### Drafting

- **Lead paragraphs with sim-derived claims.** Deltas, win rates,
  specific flip opponents. If a sentence can't be tied to a number
  or a named flip, it's editorial — flag it or cut.
- **Avoid invented game-flow archetypes** unless the sim supports
  them. "Mid-game pivot," "opener," "closer," "shield-pressure
  role" are not in the sim's per-matchup data. Committing to one
  anyway is confabulation (the Oinkologne miss). The
  tier-cluster + envelope-position data supports build advice
  ("bulk-first" / "attack-weighted") — those are OK.
- **Calibrate meta viability honestly.** Aggregate win rate is the
  check. Below 50% = anti-meta counter-pick, not meta staple. The
  upgrade story ("Mud Slap is a clean upgrade over Tackle") is
  separate from the meta-viability story ("but still sub-50%
  aggregate").
- **Voice target: RyanSwag.** See `docs/article_schema.md` "Voice
  target for auto / both synthesis". Conversational, hedging, direct
  reader address.

### Reviewing

After drafting, human review against community framing. Two specific
checks:

1. **Is the tone consistent with how the community talks about this
   species?** If analysts are calling it "anti-meta" and the draft
   calls it "meta pivot," recalibrate.
2. **Does every claim survive "where did this come from"?** If the
   answer is "I pattern-matched from JRE/RyanSwag genre language,"
   cut or anchor it.

### Regenerating

Edit `articles/<slug>.toml`'s `[meta_role]` block, re-run the
generator (Shape A) or the renderer (Shape B), `open` in the
browser, read the section end to end.

---

## Related docs

- `docs/article_schema.md` — TOML schema, including `[meta_role]`
  spec, authorship modes, voice target, calibration warning.
- `docs/article_generator_design.md` — generator pipeline internals,
  authorship-precedence for section-level expert overrides.
- `feedback_hide_not_remove` memory — hide-behind-`<details>` rather
  than delete when pruning our own content. Applies during the
  review-and-regenerate loop.
