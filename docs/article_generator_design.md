# CD article generator — design

This doc covers the generator's **internals** (pipeline, inputs,
section merging, authorship precedence). For the **human-facing
workflow** — how to go from "we want an article on species X" to a
shipped page — see `docs/article_authoring_workflow.md`.

`scripts/generate_article.py` converts simulation + threshold data into
a Community-Day move-comparison article page. The page is a spec-sheet,
not prose: every claim traces back to a number in the sim or a field in
the TOML. No hand-authored analysis unless the source TOML opts in via
the `authorship` override.

Paired with `scripts/render_article.py`. Both write to
`userdata/website/articles/<slug>/`. The boundary between them is
intentional:

- `render_article.py` — renders a fully-authored `articles/<slug>.toml`
  as-is. Every section is hand-authored. Suits the original
  Claude-prose workflow that got scrapped and suits future cases where
  an expert writes the article from scratch.
- `generate_article.py` — reads the threshold TOML + deep-dive data +
  gamemaster, produces section bodies mechanically, merges with any
  hand-authored overrides from `articles/<slug>.toml`, then writes the
  same output shape as `render_article.py`.

Both scripts converge on the same HTML layout (same CSS, same header,
same "Related" link, same `meta.toml` schema) so the site-index
builder doesn't care which one produced a given article.

## Scope cap (S6)

S6 lands the pipeline shell: generator runs end-to-end on Oinkologne,
produces a page whose section structure matches the final article's
layout, with placeholder bodies clearly labelled `TODO: S7 / S8`.

Section bodies ship in subsequent sessions:

- **S7** — move comparison table, verdict
- **S8** — matchup-delta table, PvPoke-link helper, IV recommendations
  (+ envelope-position annotations if S4's hook is ready)

S6 does **not** parse dive HTML, does **not** ship real content, does
**not** alter `render_article.py`.

## Invocation

```
python scripts/generate_article.py <species> <league> <cd_move>
```

- `<species>` — display form (`Oinkologne`), matches
  `thresholds/<species>.toml` top-level key.
- `<league>` — `great` / `ultra` / `master`.
- `<cd_move>` — display form of the CD move (`"Mud Slap"`). Passed
  through to the rendered header and used as the article's topic.

Resolves the output slug from `thresholds/<species>.toml`
`[<Species>.article] slug`. Oinkologne: `oinkologne-cd-2026-05`.
Errors loudly if the slug field isn't set.

Optional flags:

- `--article-toml PATH` — override the default
  `articles/<slug>.toml` lookup. Useful for dry-run against a throwaway
  authorship-override file in /tmp.
- `--dive-dir PATH` — override the default
  `userdata/website/<league-aware-dive-slug>/` lookup. The default
  resolution is "the `deep_dive_slug` field inside the matching
  `articles/<slug>.toml`," because the deep-dive slug already exists
  for bidirectional linking (see `docs/article_schema.md` "Bidirectional
  link contract").

## Inputs

The generator reads four things:

1. **Threshold TOML** (`thresholds/<species>.toml`) — named anchors,
   tier list, article slug, provenance. Feeds the IV recommendations
   section directly via the existing threshold-tier renderer.
2. **Deep-dive data** — the `DATA = { … }` JSON blob embedded in the
   dive's `index.html`. Fields consumed later:
   - `movesets` — per-moveset labels + avg score by scenario
   - `opponents` — name list; aligned with scenario score matrices
   - `scores` / `ivAllTiers` / `ivAtk` / `ivDef` / `ivHp` — for
     matchup-delta attribution
   - `movesetIndex` for each `index_m*.html` sibling file
   Parsed via a small helper (`_load_dive_data(dive_dir)`) that
   extracts the JSON between `var DATA = ` and the following `;`. In
   S6 the helper is stubbed; S7/S8 fill it in.
3. **Gamemaster** (`gopvpsim.data.load_gamemaster`) — fast/charged move
   stats. Feeds the move comparison table in S7.
4. **Article TOML override** (`articles/<slug>.toml`) — optional
   hand-authored prose. Precedence rule below.

## Output

Same shape as `render_article.py`:

```
userdata/website/articles/<slug>/
├── index.html    — the article page
└── meta.toml     — title / description / authorship / landing
```

HTML format: same scaffold as `render_article.py` (same CSS, same
`<title>`, same header layout, same "Related" bidirectional-link
block). Sharing the CSS is the point — both generators should produce
indistinguishable page chrome; only the body sections differ in how
they came to be.

## Section list

Ordered. Each section has a stable heading the override path keys on.

1. **Introduction** — species + CD move + date + framing in a one-
   paragraph lede. Template-rendered from front-matter fields. No new
   prose.
2. **Move comparison** — fast moves side-by-side (power, energy,
   turns, DPT, EPT, type, STAB). Two-column when the CD is a single
   move swap (Tackle vs Mud Slap); generalises cleanly if there are
   three fast-move options. S7.
3. **Meta coverage** — table: one row per surviving moveset, columns
   for avg score across scenarios, win count vs rank-1 opponents in
   each of (0-0, 1-1, 2-2). Numbers, not prose. Source: dive data's
   per-moveset scenario averages. S8 (or late S7 if cheap).
4. **Matchup delta** — per-opponent score difference between the CD-
   move moveset and the old-default moveset, with flip highlighting
   (win→loss, loss→win). S8.
5. **IV recommendations** — rendered from `thresholds/<species>.toml`
   via the existing threshold-tier renderer
   (`deep_dive_rendering.render_threshold_tier_cards`). Near-free once
   the import seam is set up in S6. S8 wires the actual call and any
   envelope-position annotations.
6. **Verdict** — one line, template-selected from the avg-score delta
   sign and magnitude across movesets. Cutoffs from TODO.md: `Δ > 10%`
   → "clear upgrade", `|Δ| < 5%` → "sidegrade", mid band →
   "upgrade in X scenarios, sidegrade in Y." S7.

Section IDs in HTML (for stable anchors): `intro`, `move-comparison`,
`meta-coverage`, `matchup-delta`, `iv-recommendations`, `verdict`.

In S6 every section body renders a labelled `TODO` placeholder block:

```html
<div class="todo-placeholder">TODO (S7): move comparison table</div>
```

The `.todo-placeholder` CSS class gives the placeholder a visible but
unobtrusive treatment (dashed border, muted background) so a reviewer
can spot at a glance which sections are real vs. stubbed.

## Authorship precedence

Per TODO.md "Python article generator — optional augmentation path."
The `authorship` field on `articles/<slug>.toml` selects how the
override TOML interacts with generator output:

| `authorship` | Behaviour                                                                                                                                                                                            |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `auto`       | Generator output used for every section. Any `[[sections]]` bodies in the TOML are ignored. Default for S6.                                                                                          |
| `expert`     | The override TOML is authoritative. Generator defers entirely to `render_article.py`; `generate_article.py` exits with a note that the article is expert-authored and points to `render_article.py`. |
| `both`       | Per-section merge: if an override section (matched on `heading`) has a non-empty, non-placeholder body, it wins; otherwise the generator renders its mechanical default.                             |

"Non-placeholder" = the body doesn't start with the string
`PLACEHOLDER`. Tuple (current Oinkologne TOML uses `PLACEHOLDER — …`
scaffolding; under `both` those sections still fall back to generator
output because the placeholder sentinel gates the override.)

Section matching is by exact `heading` string. Case-sensitive.
Trailing whitespace stripped. If an override TOML has a section
heading that doesn't appear in the canonical list above, a warning is
logged and the override section is ignored. (We don't let a typo in
the override silently suppress a generator section.)

**Oinkologne's current TOML is `authorship = "auto"`** so the
generator's output is what ships — no override merge needed for S6.
The `both` path stays tested via `tests/test_generate_article.py`
(eventually) against a throwaway fixture TOML.

## Related work touched by this design

- **Histogram section** (arc S3, shipped) — the dive already emits a
  per-moveset battle-rating histogram. Meta-coverage can link to it;
  no new infra needed.
- **Envelope-position metric** (arc S4) — if S4's annotation hook
  surfaces in `render_threshold_tier_cards`, IV recommendations gets
  per-category envelope-position annotations for free in S8. If not,
  S8 skips them and logs a follow-up.
- **Female Oinkologne** (arc S9) — Male and Female have different
  base stats and both get Mud Slap on the same CD. The generator
  stays per-species — a Female article gets its own threshold TOML
  and its own `articles/*.toml`. S9 decides whether to cross-link
  the two articles.
- **Non-interactive `generate_html`** (TODO.md "HTML output paths") —
  unaffected; generator reads interactive-dive HTML for its data.

## Follow-ups explicitly punted out of S6

- Parsing the `DATA` JSON out of the dive HTML (S7/S8).
- Gamemaster-driven move-stat lookup (S7).
- PvPoke multi-battle URL formatting (S8).
- Envelope-position annotation wiring (S8, gated on S4 hook).
- Tests. `tests/test_generate_article.py` gets added once section
  bodies do real work — S6's output is trivially checkable by eye.
- Site-index integration. `build_website_index.py` already picks up
  anything in `userdata/website/articles/`; no change needed.

## Related Article link (S0 verification)

Checked 2026-04-17 during S6 kickoff:
`articles/oinkologne-cd-2026-05.toml` uses hyphens,
`thresholds/oinkologne.toml` `[Oinkologne.article] slug` uses hyphens,
and the dive at `userdata/website/oinkologne-great-league/index.html`
links to `../articles/oinkologne-cd-2026-05/`. The slug-convention fix
from commit `5d7ced3` (S0) is in place; the "Related Article" link
resolves. No further action on the preflight reconciliation item.

The `obsolescence` metadata field is present in both the article TOML
and the renderer (`render_article.py:render_obsolescence_banner`). No
follow-up needed from the reconciliation checklist.
