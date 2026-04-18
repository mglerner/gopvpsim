# Article TOML schema

This document specifies the TOML format for `articles/*.toml` files. These
are hand-authored source-of-truth files for article-type pages (as opposed
to deep dives, which are machine-generated from simulation data).

The renderer is `scripts/render_article.py`. Output lands in
`userdata/website/articles/<slug>/`.

## Scope

This schema is designed for the Oinkologne Community Day move-comparison
article. It is not generalized for hypothetical future article types.

## File layout

One TOML file per article, named `articles/<slug>.toml`. The filename
(without extension) is also the output subdirectory slug.

```toml
# ── Front matter ──────────────────────────────────────────────────────

title       = "Human-readable article title"
species     = "Oinkologne"
cd_date     = "2026-05-09"
author      = "mglerner"
description = "One-paragraph summary for the site index."

# The CD move being evaluated.
cd_move     = "Mud Slap"

# How the CD move compares to existing options.
#   "sidegrade"       — different, not strictly better/worse
#   "upgrade"         — strictly better in most/all formats
#   "downgrade"       — strictly worse (rare for a CD article)
#   "format-dependent" — better in some leagues, worse in others
framing     = "sidegrade"

# Content origin. Surfaces a banner distinguishing human-written analysis
# from auto-generated simulation output. Update this field as the article
# evolves (e.g. start as "auto" with scaffold/placeholder content, move
# to "both" or "expert" once a human has written or edited the prose).
#   "expert" — written by a human analyst
#   "both"   — human-written analysis supported by simulation data
#   "auto"   — auto-generated from simulation data
authorship  = "expert"

# ── Obsolescence ──────────────────────────────────────────────────────

[obsolescence]
status  = "current"          # "current" | "obsolete"
as_of   = "2026-05-09"       # date the status was last set
note    = ""                 # optional; shown in staleness banner

# ── Links ─────────────────────────────────────────────────────────────

[links]
# Slug of the deep-dive subdir under userdata/website/.
# Resolved at render time as ../../<slug>/ (up from articles/<this>/).
deep_dive_slug = "oinkologne-great-league"

# ── Sections ──────────────────────────────────────────────────────────
# Ordered list of content sections. Each section becomes a heading +
# body block in the rendered HTML. The renderer preserves source order.

[[sections]]
heading = "Section heading"
body    = """
Markdown-ish body text. The renderer does minimal formatting:
paragraph breaks on blank lines, **bold**, *italic*, backtick code.
No full Markdown parser -- keep it simple.
"""

# Repeat [[sections]] for each content block.
```

## Field reference

| Field                  | Required | Type   | Notes                                                          |
| ---------------------- | -------- | ------ | -------------------------------------------------------------- |
| `title`                | yes      | string | Displayed as page `<h1>` and in site index.                    |
| `species`              | yes      | string | Species name matching `thresholds/*.toml`.                     |
| `cd_date`              | yes      | string | ISO date of the Community Day.                                 |
| `author`               | yes      | string | Attribution shown in page footer.                              |
| `description`          | yes      | string | Summary for site index `<p>` tag.                              |
| `cd_move`              | yes      | string | The Community Day move name (display form).                    |
| `framing`              | yes      | string | One of: sidegrade, upgrade, downgrade, format-dependent.       |
| `authorship`           | yes      | string | `expert`, `both`, or `auto`. Surfaces a content-origin banner. |
| `obsolescence.status`  | yes      | string | `current` or `obsolete`.                                       |
| `obsolescence.as_of`   | yes      | string | ISO date.                                                      |
| `obsolescence.note`    | no       | string | Free text for the staleness banner.                            |
| `links.deep_dive_slug` | yes      | string | Sibling subdir slug under `userdata/website/`.                 |
| `sections`             | yes      | array  | At least one `[[sections]]` entry.                             |
| `sections.heading`     | yes      | string | Section heading text.                                          |
| `sections.body`        | yes      | string | Section body text.                                             |

## Meta Role section (F1, schema only as of 2026-04-18)

A dedicated "Meta Role / Strengths & Weaknesses" section positioned
after the article's intro (and after the stats-at-a-glance block
if / when F-stats-block ships) and before Move Comparison. Added
per `docs/jre_ryanswag_comparison.md` §3.O — both reference styles
(JRE, RyanSwag) spend significant article space on this framing,
ours currently has none.

**Schema shape (Design 2 + freeform escape hatch, decided 2026-04-18):**

```toml
[meta_role]
authorship = "expert"   # or "both" | "auto" — see authorship modes below

# Preferred default: three structured fields, each rendered as one
# <p> block with NO visible label. The reader sees three flowing
# paragraphs. Field names are authoring ergonomics only.
good_at    = """Paragraph on what this species / CD-move combo is
strong against. Cite specific matchups by name where useful."""
bad_at     = """Paragraph on what it's weak against. May be omitted
if there is no distinctive vulnerability."""
team_role  = """Paragraph on how it fits on a team: opener /
closer / pivot / shield-pressure role / etc."""

# Escape hatch. If `body` is a non-empty string, it overrides the
# three structured fields entirely and is rendered as freeform
# paragraphs (split on blank lines). Use sparingly, only when the
# three-slot structure feels forced for a particular species.
body = ""
```

### Authorship modes

- `expert`: the three fields (or `body`) are human-authored. No
  auto-generation. Missing fields are rendered as nothing (not an
  error).
- `both`: per-field fallback. If any of `good_at` / `bad_at` /
  `team_role` is empty AND `body` is empty, the renderer emits an
  auto-generated skeleton for that specific field, tagged inline
  so the reader can see which bits are expert vs auto. Human can
  override any single field without disturbing the rest.
- `auto`: all three fields are generated from simulation data,
  labeled as auto-generated in the rendered output. Used for
  scaffolding / preview.

### Auto-skeleton data sources (for `both` and `auto` modes)

- `good_at` ← wins-by-type synthesis from the Matchup Delta table
  (count wins per opponent type + surface the CD-move-driven flips).
- `bad_at` ← losses-by-type synthesis from the same table.
- `team_role` ← threshold-tier cluster analysis + envelope position
  (e.g., "bulk-first role" vs "attack-weighted closer").

### Voice target for `auto` / `both` synthesis

Auto-synthesised prose should target **RyanSwag's voice**, not JRE's.
Conversational, lightly hedged ("may be the flavor of choice"),
direct reader address where it fits, matchup-level specificity over
high-level generalities. See `docs/reference_deep_dives/ryanswag/`
for the archive and `docs/jre_ryanswag_comparison.md` §7 for the
full voice framing.

Rationale: RyanSwag is retired from PvP content production, so our
auto-synthesis filling that register fills a vacuum rather than
competing with an active writer. JRE is actively writing; mimicking
his voice would substitute for live work (separately, his wordy
tangential style is a poor fit for our density goals — see the
JRE-specific out-of-scope in the comparison doc).

**Calibration warning — do not overstate meta viability.** When
synthesising prose, lead with the mechanical claim the sim actually
supports (aggregate win rate, delta magnitude, flip count) before
reaching for archetype language like "opener," "closer," or "pivot".
Game-flow archetypes aren't derivable from the sim's per-matchup
flip data; committing to one anyway is confabulation. If a species'
aggregate win rate is below 50%, framing it as a meta staple is
overstatement — the honest framing is "anti-meta counter-pick"
(recurring lesson from the Oinkologne F1 authoring session,
2026-04-18).

### Rendering

Output is a `<section id="meta-role">` with `<h2>Meta Role</h2>` and
three `<p class="meta-role-para">` blocks (or N paragraphs if `body`
is set). No visible field labels — the prose itself carries the
structure.

### Field reference (Meta Role)

| Field                  | Required | Type   | Notes                                                              |
| ---------------------- | -------- | ------ | ------------------------------------------------------------------ |
| `meta_role.authorship` | yes¹     | string | `expert` / `both` / `auto`. ¹Required if `[meta_role]` present.    |
| `meta_role.good_at`    | no       | string | One paragraph. Omit or leave empty to skip / auto-fill.            |
| `meta_role.bad_at`     | no       | string | One paragraph. Omit or leave empty to skip / auto-fill.            |
| `meta_role.team_role`  | no       | string | One paragraph. Omit or leave empty to skip / auto-fill.            |
| `meta_role.body`       | no       | string | Escape hatch. If non-empty, overrides the three structured fields. |

Omitting the entire `[meta_role]` block skips the section.

## Intro augment (F-intro, schema shipped 2026-04-18)

The Introduction section has a default template that fires from
front-matter fields (species + CD move + CD date + framing + reader-
guidance sentence). It's proof-of-life prose, not authored. The
**augment** is an optional expert-authored override that replaces
the template entirely. Added per
`docs/jre_ryanswag_comparison.md` §3.A / §4 F-intro — JRE and
RyanSwag both open with 1-3 sentence hooks that include an upfront
verdict and a species-specific angle; the default template can't
do that.

**Schema shape (simpler than Meta Role / Verdict — one field):**

```toml
[intro]
# The intro prose. 2-3 sentences, species-specific, ideally with
# an upfront verdict and a hook to a specific matchup or angle.
# Renders as one or more <p> blocks (split on blank lines per
# format_body). If empty / missing, the default template fires.
body = """..."""
```

No `authorship` field — the intro is either template (no block /
empty body) or expert (body populated). Auto-synthesis beyond the
existing template isn't on the roadmap; a human-written intro is
the whole point of the augment.

Voice target: same as Meta Role / Verdict — RyanSwag-adjacent, NOT
JRE. Keep it tight; the intro shouldn't repeat what Meta Role and
Verdict will say.

### Field reference (Intro augment)

| Field        | Required | Type   | Notes                                         |
| ------------ | -------- | ------ | --------------------------------------------- |
| `intro.body` | no       | string | If non-empty, overrides the default template. |

Omitting the entire `[intro]` block (or leaving `body` empty) falls
back to the default template.

## Verdict augment (F4, schema shipped 2026-04-18)

The Verdict section always renders a mechanical line (upgrade /
sidegrade / downgrade classification + win-rate delta + per-scenario
exceptions) from sim data. The **augment** is an optional
expert-authored editorial block appended underneath it, answering
"should you invest?" in the style of JRE's IN SUMMATION or
RyanSwag's wrap-up paragraph. Added per
`docs/jre_ryanswag_comparison.md` §3.R / §4 F4.

**Schema shape (parallel to Meta Role):**

```toml
[verdict]
authorship = "expert"   # or "both" | "auto"

# The "should you invest?" paragraph. Calibrated to CD
# catch-priority, Elite TM cost, meta window. Rendered as a single
# <p> appended after the mechanical verdict line.
editorial = """One paragraph."""

# Optional meta-outlook closer (2-4 sentences). Rendered as a
# second <p> after `editorial`. Omit or leave empty to skip.
outlook = """Optional short paragraph on meta pulse / follow-up
expectations."""
```

### Authorship modes (Verdict augment)

Same shape as Meta Role. `expert` is wired today; `both` / `auto`
log a warning and fall through to expert, pending the next F1
session that adds auto-synthesis.

### Auto-skeleton data sources (for `both` / `auto`, future)

- `editorial` ← combination of the mechanical verdict (upgrade /
  sidegrade) + [meta_role]'s team_role framing + CD-logistics
  front-matter (cd_date, framing).
- `outlook` ← threshold-tier envelope position + meta-volatility
  proxies (once wired).

Voice target matches Meta Role: RyanSwag-adjacent, NOT JRE. See
the voice-target subsection under Meta Role above; it applies
to Verdict augment identically.

### Rendering

The mechanical `<p class="verdict-line">` renders first, then the
augment paragraphs follow. No new section wrapper — everything
lives inside the existing Verdict `<section>`.

### Field reference (Verdict augment)

| Field                | Required | Type   | Notes                                                         |
| -------------------- | -------- | ------ | ------------------------------------------------------------- |
| `verdict.authorship` | yes¹     | string | `expert` / `both` / `auto`. ¹Required if `[verdict]` present. |
| `verdict.editorial`  | no       | string | "Should you invest?" paragraph. Omit to skip.                 |
| `verdict.outlook`    | no       | string | Short meta-outlook closer. Omit to skip.                      |

Omitting the entire `[verdict]` block leaves only the mechanical
line (pre-F4 behaviour).

## Obsolescence semantics

- `current` -- the article's framing (sidegrade/upgrade/etc.) still holds.
  No banner is shown.
- `obsolete` -- post-CD data shows the framing was wrong or the meta has
  shifted enough that the analysis no longer applies. The renderer shows
  a prominent banner at the top of the page with the `note` text and
  `as_of` date.

Transition is manual: the author edits the TOML file. There is no
auto-detection.

## Bidirectional link contract

This contract is frozen as of Session 3 (2026-04-16). Sessions 4 and 5
consume it independently; do not change it without a touchup pass on both
outputs.

### Article side

`links.deep_dive_slug` holds the subdir name of the deep dive under
`userdata/website/`. The article renderer resolves it as a relative link:
`../../{deep_dive_slug}/` (up from `articles/<this-slug>/`).

### Deep-dive side

`thresholds/<species>.toml` gains an `[article]` table:

```toml
[Oinkologne.article]
slug = "oinkologne-cd-2026-05"    # subdir under userdata/website/articles/
```

The deep-dive renderer resolves it as: `../articles/{slug}/`. Both sides
produce relative links that work in local `file://` preview and on
mglerner.com.

### Rendered output

Each side emits a "Related" link block near the top of its HTML, with
labels that make the content origin clear:

- Article: "Simulation Deep Dive: [Oinkologne - Great League IV Deep Dive](../../oinkologne-great-league/)"
- Deep dive: "Expert Analysis: [title](../articles/oinkologne-cd-2026-05/)"

Link text is read from the counterpart's `meta.toml` title at render
time, with a hardcoded fallback if the counterpart hasn't been built yet.

The `authorship` field controls a banner at the top of the article:

- `expert` (gold) -- "This article is written by a human analyst."
- `both` (green) -- "Human-written analysis supported by simulation data."
- `auto` (blue) -- "This article is auto-generated from simulation data."

Update this field in the TOML as the article evolves (e.g. start as
`auto` during scaffold, move to `both` or `expert` once a human has
written or edited the prose).
