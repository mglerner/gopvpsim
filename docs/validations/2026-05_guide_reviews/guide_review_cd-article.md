# Mercuryish review — Reading a CD Article

Source: `guides/cd-article/body.md`. Per G6, also flip authorship `ai` →
`both` once edits applied.

---

## Item 1 [CD-1]: missing authorship category

**Mercuryish:** "The named authorship categories are missing one of the
listed categories in the 'Under the Hood' section."

**Current** (`body.md:34-45`):

```text
- **Gold banner ("written by a human analyst")**: the narrative
  sections were written by an expert. Opinions in the Meta Role,
  Verdict, and IV Recommendations prose are load-bearing and reflect
  editorial judgment.
- **Green banner ("human-written analysis supported by simulation
  data")**: hybrid - human-written prose with generated tables and
  grids woven in.
- **Blue banner ("auto-generated from simulation data")**: the prose
  was produced by our templated narrative generator. The shapes and
  numbers are mechanical; any editorial framing ("switch GL pick,"
  "clear upgrade") comes from a small vocabulary of auto-gen patterns,
  not from a human taking a stance.
```

The **Under the Hood guide** lists **four** tiers: gold, green, blue,
**orange (`ai`)**. CD Article guide is missing orange.

**Proposed:** add an orange-banner bullet between blue and the closing
paragraph:

```text
- **Orange banner ("LLM-drafted, not yet human-reviewed")**: the prose
  was drafted by an LLM and is awaiting human review. Distinct from
  blue because LLMs make register choices a template can't, so the
  orange border flags the section for extra scrutiny. CD articles
  rarely ship with this banner; it's mostly used in the Reader's
  Guides while they're being polished.
```

Insert after `body.md:45` (before the "The reference Oinkologne article
is currently auto-generated..." paragraph at line 47).

---

## Item 2 [CD-2]: explain the obsolescence trigger

**Mercuryish:** "What makes an article outdated enough for the
obsolescence banner to be applied to an article?"

**Current** (`body.md:54-62`):

```text
## The obsolescence banner

When an article ages past the event it was written for, or when a
simulator change reshuffles its conclusions, we add a **red "This
article is outdated" banner** at the top and a dated note explaining
what changed. The article stays live - its numbers at time of writing
are sometimes still useful for historical comparison - but the banner
is an explicit "don't treat this as current advice."

No banner visible means the article is current.
```

**Proposed:**

```text
## The obsolescence banner

The banner is editorial: when one of us decides an article's framing
no longer applies, we flip an `[obsolescence]` field in the article
TOML and the banner appears on the next publish. Triggers we've used
or expect to use:

- **The CD move turned out to be strictly better or worse** than the
  article's "sidegrade" / "upgrade" framing claimed. (Article was
  written before launch; live data showed something different.)
- **The opponent meta has shifted** enough that the article's per-
  matchup deltas read against an opponent pool nobody plays anymore
  (e.g. a new species drops the old #1 out of the top 50).
- **A simulator fix changed the underlying numbers** (a damage formula
  bugfix, a new shield-policy gate) and the article's headline
  conclusion no longer matches what the dives now say.

A red **"This article is outdated"** banner appears at the top with a
dated note explaining what changed. The article stays live - its
numbers at time of writing are sometimes still useful for historical
comparison - but the banner is an explicit "don't treat this as
current advice."

No banner visible means the article is current.
```

---

## Item 3 [CD-3 / G2]: "IV" → "IV spread" pass

| Line    | Current                                                                                                            | Proposed                                                                                      |
| ------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| 7       | "you've decided the species is worth a dust commit and you want to pick a specific IV"                             | "you've decided the species is worth a dust commit and you want to pick a specific IV spread" |
| 76      | "showing each form's rank-1-IV stats"                                                                              | "showing each form's rank-1 IV-spread stats"                                                  |
| 78-79   | "alongside the form's rank-1 IV triple"                                                                            | unchanged (already explicitly "IV triple")                                                    |
| 161-162 | "switches every opponent's IV spread between PvPoke's current default and the opponent's highest-stat-product IVs" | "...and the opponent's highest-stat-product IV spreads"                                       |
| 209-216 | "The member count out of {{dive:iv_space_size}} IVs."                                                              | "...out of {{dive:iv_space_size}} IV spreads."                                                |

**Notes:** small set; the CD article guide is mostly about article
sections, not IV-level prose.

---

## Item 4 [CD-4 / G3]: "PvPoke" usage check

Consistent. No edit.

---

## Item 5 [CD-5]: pick up the "(Female)" / "(Male)" asymmetry

**Cross-reference INDEX item B3 and G4.** Once those decisions are made,
the CD article guide may need a sentence noting the convention. Defer
until B3 / G4 are decided.

---

## Summary of cd-article changes

If you accept CD-1, CD-2, CD-3:

- 1 paragraph addition (CD-1, +6-8 lines)
- 1 paragraph rewrite (CD-2, +4 lines)
- ~5 wording tweaks for IV/IV-spread (CD-3)
- CD-5 deferred pending INDEX B3 / G4 decisions

After Edit pass: rebuild guides + flip authorship to `both`.
