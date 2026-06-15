# Mercuryish doc review — index

Source feedback: Discord, mercuryish.

- Original feedback: 2026-04-26 (5:07 PM, edited)
- Amended bullets: 2026-05-04 (added 2 General-Feedback items + IV Flavor Guide section)
- Authorship plan confirmed: 2026-05-08 (mercuryish: "AI + human works fine
  with me")

Per-guide proposals: `userdata/reviews/guide_review_<slug>.md` (one file per guide).

Files in this directory:

```
guide_review_INDEX.md              — this file. Bug fixes + corrections + open questions.
guide_review_how-this-works.md     — 6 items
guide_review_threshold-tiers.md    — 4 items
guide_review_envelope-position.md  — 3 items
guide_review_cd-article.md         — 5 items
guide_review_deep-dive-scatter.md  — 5 items
guide_review_under-the-hood.md     — 5 items
guide_review_iv-flavor-guide.md    — 7 items (now has specific feedback, not just G2)
```

## How to use this

1. Read each per-guide file. Each item is *Mercuryish quote → current text →
   proposed text → notes*. Mark accept / reject / edit on each item.
2. Read this index for the four bug-report items, the Aegislash whole-level
   finding, the two new naming items (G4/G5), the authorship plan (G6), and
   the open questions that need your call.
3. Tell me which items to apply. I'll patch source, regenerate guides, and
   commit per item or batched, your preference.

---

## Coordination note: B1 ↔ G4 must land together

Both items touch shadow-Pokemon naming. B1 (anchor-name capitalization in
tier bullets) would render the left side as `Quagsire (Shadow) bulk` to
match the right side. **G4 (new) wants `Shadow Quagsire bulk` instead.**

Pick one canonical format before applying either. The choice cascades to
every renderer that displays shadow species names: tier bullets, opponent
strings, hover cards, narrative prose, site-index cards, dive banners,
articles, comparison pages.

**Default recommendation:** **adopt `Shadow X` globally.** Mercuryish's
phrasing reads more naturally and matches in-game convention (the in-game
nickname tag is "Shadow Pokemon," with the modifier first). Doing this
globally — rather than just on the card titles — means we only fight one
convention battle and never have to explain why opponent strings disagree
with card titles.

**Cost:** one rename pass through `_pretty_species`,
`derive_display_name`, `_opp_b`, the opponent-pool loaders, the
article generator's title formatting, the site-index card builder, and
any narrative templates that interpolate species names. Probably 30-60
min of grep + Edit, plus a full site re-render. No re-dive needed —
the changes are all display-layer.

**Question for you:** adopt `Shadow X` globally, or scope to just the
site-index card titles (G4's literal ask)?

---

## Bug-report items (code, not doc)

These came in mixed with the doc feedback but require code patches, not text edits.

### B1. Anchor-name capitalization in tier-card bullets

**Mercuryish:** "the lefthand side is always lowercase, while the righthand
side is always capitalized. The righthand side also formats the names
differently when it comes to shadow Pokemon and form changes."

**Where:** Tier-card anchor bullets read e.g.

> "96.62 Def for **lickilicky bulk** (Hyper Beam) vs **Lickilicky** (0v1, 1v2)"

The left-side `lickilicky bulk` is the anchor's display name; the right-side
`Lickilicky` is the opponent's `speciesName` from the gamemaster.

**Root cause:** `src/gopvpsim/anchors.py:79 derive_display_name()` returns the
parent name lowercase because TOML anchor keys are conventionally lowercased
(`lickilicky_brkp_any`, `quagsire_shadow_blkp_any`, etc.) and the function
just splits on `_brkp_` / `_blkp_` markers without re-casing. Output for
`quagsire_shadow_blkp_any` is `quagsire_shadow bulk` — lowercase head AND
underscore preserved, vs the right-side `Quagsire (Shadow)` which is
properly cased.

**Proposed fix:** post-process the head segment in `derive_display_name`
to (a) split on `_`, (b) title-case each word, (c) reorder shadow / regional
suffixes to a parenthetical or prefix (depending on G4 decision). Worked
examples after fix:

If you pick **`X (Shadow)` parenthetical** (current convention):

| Anchor parent name            | Before                 | After                    |
| ----------------------------- | ---------------------- | ------------------------ |
| `lickilicky_blkp_any`         | `lickilicky bulk`      | `Lickilicky bulk`        |
| `quagsire_shadow_blkp_any`    | `quagsire_shadow bulk` | `Quagsire (Shadow) bulk` |
| `corsola_galarian_brkp_any`   | `corsola_galarian`     | `Corsola (Galarian)`     |
| `lickitung_brkp_above_lurgan` | `lickitung↑lurgan`     | `Lickitung↑lurgan`       |
| `cmp_vs_lurgan`               | `cmp:lurgan`           | `cmp:lurgan`             |

If you pick **`Shadow X` prefix** (G4 request):

| Anchor parent name            | Before                 | After                  |
| ----------------------------- | ---------------------- | ---------------------- |
| `lickilicky_blkp_any`         | `lickilicky bulk`      | `Lickilicky bulk`      |
| `quagsire_shadow_blkp_any`    | `quagsire_shadow bulk` | `Shadow Quagsire bulk` |
| `corsola_galarian_brkp_any`   | `corsola_galarian`     | `Galarian Corsola`     |
| `lickitung_brkp_above_lurgan` | `lickitung↑lurgan`     | `Lickitung↑lurgan`     |
| `cmp_vs_lurgan`               | `cmp:lurgan`           | `cmp:lurgan`           |

**Code site:** `src/gopvpsim/anchors.py:113-134`. Patch is ~15-25 LOC
(more if we re-order regional suffixes too).

**Test impact:** affects any test or fixture that asserts on the lowercase
form. Need to grep for `lickilicky bulk`, `mirror bulk`, etc. in tests/.

**Re-render:** every shipped dive has these bullets. After the fix, run
`scripts/publish_website.sh` (or the dive-only patcher) to refresh HTML.

### B2. Fortified Greedent tier appends "bulk" to every tier name

**Mercuryish:** "the Fortified Greedent adds 'bulk' to the end of every tier.
Why?"

**Root cause (intentional, not a bug):** `derive_display_name` (anchors.py:79)
deliberately appends ` bulk` to bulkpoint anchor display names. Docstring
explicitly says:

> "Bulkpoint badges also get a trailing ` bulk` so the two kinds are doubly
> distinguishable in the Bulk Slayer card (where they can appear together)."

The disambiguation is needed in the **Bulk Slayer** category card where
breakpoints and bulkpoints can both appear; without ` bulk`, you'd see
`lickilicky` for both the breakpoint and the bulkpoint anchor.

**Mercuryish's complaint:** in the **Fortified Greedent** tier card
specifically (a defense-axis tier), every bullet is a bulkpoint by
construction — the suffix is redundant noise.

**Proposed fix (option A, surgical):** suppress the `bulk` suffix when the
bullet is rendered inside a tier card whose only target axis is `def`.
Bulk Slayer card retains the suffix. Code site:
`scripts/deep_dive_rendering.py:1050 anchor_label` line — pass a context
flag that strips `bulk` when in a def-axis-only tier.

**Proposed fix (option B, doc-only):** keep the suffix; add a one-line note
on the tier card header explaining "every bullet here is a bulkpoint
because this tier is defined on def." Cheaper but doesn't address the
redundancy mercuryish flagged.

**Recommendation:** option A (surgical strip). Net win: Fortified Greedent
reads `for Greedent vs Greedent`, `for Lapras vs Lapras`, etc. Bulk Slayer
unchanged.

**Question for you:** does the Fortified Greedent **header** ("Fortified
Greedent") on the tier card itself read clearly as a bulkpoint card? If not,
option B might still be worth doing alongside option A.

### B3. Oinkologne (Female) named, Oinkologne (Male) bare

**Mercuryish:** "Why do you specify Oinkologne (Female) but not Oinkologne
(Male)? The male section does not include the parenthetical I have been
using."

**Root cause:** PvPoke's gamemaster.json names the base/Male form just
`Oinkologne` (no parenthetical) and the female variant `Oinkologne (Female)`.
Our renderers use the gamemaster `speciesName` verbatim, so the asymmetry
propagates to every surface (focal-species banner, opponent list, narrative
prose, comparison tables).

**Concrete impact:** in the Male dive, the focal species reads "Oinkologne"
but the opponent pool lists "Oinkologne (Female)" as one of the 65
opponents; in the Female dive, the focal reads "Oinkologne (Female)" and
the opponent pool lists Male as just "Oinkologne." The article-level
comparison page uses both forms with their gamemaster names.

**Proposed fix options:**
- **(a)** Add `(Male)` qualifier on the Male dive's focal-species banner
  (and any narrative reference to itself) when the species has a
  `(Female)` sibling. Other surfaces keep gamemaster names. Pros: addresses
  mercuryish's specific complaint; localized to the focal-display path.
  Cons: requires sibling-form lookup; may interact with the CD article
  generator's expectations.
- **(b)** Add `(Male)` everywhere — opponent strings, scatter hover,
  narrative prose. Symmetric but invasive; touches many renderers.
- **(c)** Leave as-is; document the convention in the relevant guide so a
  reader who sees "Oinkologne" vs "Oinkologne (Female)" knows the bare form
  is Male.

**Recommendation:** **(b)** symmetric global rename. Same reasoning as the
G4 coordination note above — having both forms tagged consistently means
we don't have to explain why some surfaces disagree. The Female-paste-box
bug (separate followup) might actually be caused by this asymmetry too.

**Question for you:** which?

### B4. Threshold-tier guide claims "5 tiers" but Oinkologne dive shows 6

**Mercuryish:** "you say that the Oinkologne deep dive has five tiers. Does
it not have six?"

**Confirmed:** the rendered guide's worked example reads "Oinkologne (Male)
Great League has **5** threshold-tier cards on its featured moveset." The
actual dive page renders **6** tier cards (`tier-card-general`,
`tier-card-greedent-bulk`, `tier-card-lapras-atk`, `tier-card-swampert-atk`,
`tier-card-talonflame-atk`, `tier-card-tinkaton-atk`).

**Root cause:** `scripts/build_guides.py:274 dive:tier_count` returns
`len(data['tiers'])` — but `data['tiers']` is the 5-element auto-derived
tier list before the General fallback gets stitched in. The renderer
appends a 6th "General" card from a separate path; the JS payload's
`tiers` array stays at 5.

**Proposed fix:** in `_resolve_dive_token`, count the rendered tier-card
ids (or check `data` for a separate `general_tier` field) instead of just
`len(tiers)`. Concretely: parse the dive's `index.html` and count
`id="tier-card-..."` (excluding `tier-card-yours-` placeholders). The
guide builder already opens the file via `_load_dive_data`.

**Alternative:** look up where the General card gets stitched in (search
`deep_dive_analysis.py` near line 814 and `deep_dive_rendering.py` for
where "General" gets the extra render call) and add the General entry
to `data['tiers']` so the count is right at the data layer.

**Recommendation:** alternative. The data-layer fix means every consumer
of `data['tiers']` (CD article generator, paste-box JS, mirror-tier
synth) sees the General entry consistently.

**Question for you:** which?

---

## Substantive corrections

### S1. Aegislash whole-level rounding — sim bug in focal-species path

**Mercuryish:** "Aegislash (Blade) always rounds its level down to the
nearest whole number. ... his Aegislash is 1454cp in Blade form because
it has to round down to level 22."

**Status:** Partially right. Our sim **does** enforce whole-level rounding
for the in-battle Shield→Blade transform (`src/gopvpsim/formchange.py:96
_aegislash_alt_level` with `alt_level -= 1.0` step-down loop, matching
PvPoke's `getFormStats() newLevel--`). But the **focal-species path**
(`Pokemon.at_best_level` and `iv_rank` in `src/gopvpsim/pokemon.py`)
walks the standard half-level grid when Aegislash (Blade) is the dive
subject, so the dive lands on `.5` levels for many IVs.

**Concrete impact:** our shipped Aegislash (Blade) GL dive displays:

| IVs      | Our dive        | mercuryish (real-world)   |
| -------- | --------------- | ------------------------- |
| 1/14/11  | L22.5 / 1487 CP | L22 / 1454 CP             |
| 15/14/15 | L21.0 / 1477 CP | unchanged (already whole) |
| 15/15/14 | L21.0 / 1479 CP | unchanged                 |
| 15/15/15 | L21.0 / 1484 CP | unchanged                 |

UL Aegislash (Blade) hundo: our dive shows L40.5 / 2489 CP; real-world
should be L40 / lower CP.

This is **not just a display issue** — the half-level stats also feed the
sim's atk/def/hp values, so battle outcomes for these IVs are computed
at higher stats than a real Blade-form Aegislash would have.

**Proposed fix:** patch `Pokemon.at_best_level` and `iv_rank` in
`pokemon.py` to round Aegislash (Blade) levels DOWN to whole levels.
~5 LOC. After the fix, re-dive Aegislash (Blade) GL + UL.

```python
# In Pokemon.at_best_level (pokemon.py:211), after best_level returns:
if species_name == 'Aegislash (Blade)' and level % 1.0 != 0:
    level -= 0.5  # whole-level grid for Blade form
```

(Same change in `iv_rank` line ~265. Note: if you adopt `Shadow X`
naming per G4 plus a "Blade Aegislash" rename, update the string match.)

**Re-dive cost:** ~5-10 min per dive based on prior runs. GL + UL = ~20 min.
The form-change comparison page and the form-change guide article would
re-render automatically off the new dive data.

**Form-change guide article addition:** mercuryish also asked us to "update
the form change guide to include this." Currently `userdata/website/articles/
aegislash-form-change-guide-{gl,ul}/index.html` doesn't mention the
whole-level rule. Add a one-paragraph callout explaining:

> Blade form only powers up in whole levels. If your Shield form lands on
> a half level (e.g. L22.5), Blade form rounds DOWN to the nearest whole
> (L22), losing half a level of stats. When choosing which Aegislash to
> power up, check that the resulting Blade level is a whole number.

Source: `scripts/write_aegislash_narrative.py`.

**Question for you:** patch + re-dive? If yes, also drop UL section per S2?

### S2. Aegislash UL is unusable — drop the UL dive?

**Mercuryish:** "I am almost certain that Aegislash is unusable in the
Ultra League ... I asked for second opinions from people who play UL,
and they agree that UL Aegislash is not real. ... arguing over whether
trash or garbage is better."

**Status:** opinionated; UL is not your main league. The mercuryish + UL-
player consensus is the closest thing to expert sign-off we have.

**Options:**
- **Drop:** delete `userdata/website/aegislash-blade-ultra-league/`,
  `userdata/website/aegislash-shield-ultra-league/`,
  `userdata/website/comparisons/aegislash-blade-vs-shield-ul/`,
  `userdata/website/articles/aegislash-form-change-guide-ul/`. Update the
  site index. Update the threshold TOMLs to remove `[Aegislash*.Ultra]`
  blocks.
- **Mark obsolete:** keep the URL live, slap a red obsolescence banner
  ("UL Aegislash is not competitively viable; this dive is preserved
  for reference only") via the same banner mechanism CD articles use.
- **Keep:** ignore the recommendation; UL data is still data.

**Recommendation:** drop. The cost of stale-data risk on a
non-competitive page outweighs reference value. mercuryish + UL contacts
agree it's not real; we have no countervailing data.

**Question for you:** drop, mark obsolete, or keep?

---

## Open questions (need your call)

### Q1. "Sibling forms" definition

**Mercuryish:** "what are 'sibling forms'?"

**Where used:** `guides/how-this-works/body.md:99-100` —

> "Rankings across opponent pools that use different rules than pvpoke.com
> (we sometimes cap CP on opponents or include sibling forms; each dive's
> methodology footer spells out what pool was used)."

**Options:**
- **(a)** Define inline: "sibling forms (e.g. Oinkologne Male and Female,
  Aegislash Shield and Blade)."
- **(b)** Drop the term; rephrase as "or include both forms of multi-form
  species (Oinkologne Male/Female, Aegislash Shield/Blade)."
- **(c)** Define in a glossary block elsewhere and link to it.

**Recommendation:** (b). Cleaner, no jargon.

### Q2. Why do Anchor IV markers change color?

**Mercuryish:** "(Why does it change colors? I understand why the
non-Anchor IVs do, but why these?)"

**Where:** the scatter plot's Anchor IVs band (the "grey triangle band"
that isn't actually grey and shifts color across the rank axis).

**Need to verify:** I haven't traced the anchor-color logic yet. Possibly
the marker color encodes a different variable than the non-anchor points
(e.g., bait scenario, opp-IV mode), or the band-color shift is just the
selected color mode applied to anchors too.

**Question for you:** want me to dig into the color code now, or stub the
guides with "TODO: explain anchor color shift" pending separate
investigation?

### Q3. Client-side add/remove anchors and thresholds

**Mercuryish:** "Is it possible to add thresholds and anchors? ... Is it
possible to remove thresholds and anchors? ... I could see someone
wanting to add and remove thresholds and anchors (client-side, not for
the entire website) for a specific Pokemon in order to focus on what
they consider to be important."

**Status:** not currently supported. The TOML files add anchors at build
time; the rendered HTML has no toggle to add/remove client-side.

**Recommendation:** add a one-line clarification to the under-the-hood
guide ("no client-side add/remove UI today; editing requires a local
clone"). Capture the feature itself as a TODO.

**Question for you:** is client-side add/remove a feature you'd want to
build, or strictly out of scope?

---

## General feedback (cross-cutting)

### G1. LLM authorship banner — appreciated

**Mercuryish (5/8):** "AI + human works fine with me haha, but thank you
for the offer."

**Action:** none directly. Positive signal worth keeping. Tied to G6
(authorship promotion plan).

### G2. "IV" vs "IV spread" terminology audit

**Mercuryish:** "I think 'IV' refers to one specific IV (say, 2 attack),
so I think rewriting every use of 'IV' in reference to an IV spread to
'IV spread' would reduce confusion."

**Action:** per-guide pass. Each per-guide review file has the affected
lines flagged with a `[G2]` tag.

### G3. "PvPoke" vs "pvpoke.com" interchangeable use

**Mercuryish:** "I would stick with using 'PvPoke' or 'pvpoke.com' instead
of using these two terms interchangeably."

**Action:** per-guide pass with `[G3]` tags. The guides are already mostly
consistent — "PvPoke" for the tool, "pvpoke.com" only for the live site
URL. Audit per file found no actual interchangeable use; suggest no edits
unless a specific line trips the audit.

### G4. (NEW 5/4) Shadow Pokemon naming: "Shadow X" not "X (Shadow)"

**Mercuryish:** "In the list of deep dives, I think the title cards with
shadow Pokemon should say 'Shadow (Pokemon name)' instead of '(Pokemon
name) Shadow'"

**Note:** mercuryish wrote `Shadow (Pokemon name)` — i.e. the species
name is the variable; the literal output should be `Shadow Forretress`,
not `Shadow (Forretress)`. Likewise `Galarian Corsola`, `Alolan
Ninetales`, etc.

**Status:** PvPoke gamemaster uses `Forretress (Shadow)`. Our entire site
inherits that convention. Switching to `Shadow X` is a global rename.

**Scope options:**
- **(a)** Just the site-index card titles. Minimum-blast-radius — exactly
  what mercuryish wrote. But every other surface (dive banners, opponent
  strings, narrative, articles) still reads "X (Shadow)" — internal
  inconsistency.
- **(b)** Site-index cards + dive top banner (addresses G5 simultaneously).
- **(c)** Global rename: every surface that displays a species name
  reformats Shadow / Galarian / Alolan / Hisuian / Paldean / Mega forms
  to the modifier-first convention. Coordinated with B1 (anchor-name
  capitalization).

**Recommendation:** **(c)**. Half-applying creates worse problems than
the current convention. The rename is mechanical: one helper function
`_pretty_species(name)` that maps `"Forretress (Shadow)" → "Shadow
Forretress"` and `"Corsola (Galarian)" → "Galarian Corsola"`, called
everywhere a species name is rendered. Probably 30-60 min of grep + Edit
plus a publish-time re-render.

**Coordination:** lands together with B1. The two share an output format
choice; doing them in one commit avoids a half-renamed site.

**Question for you:** (a) / (b) / (c)?

### G5. (NEW 5/4) Dive top-banner should include "shadow" for shadow focal species

**Mercuryish:** "Once a deep dive is selected, the title at the top of the
page should still include the specific details. Example: The Shadow
Forretress deep dive does not say 'shadow' at the top."

**Status:** confirmed if true. Need to inspect the dive's H1 title to see
what it currently renders for a Shadow focal species.

**Likely root cause:** the dive's H1 uses the species's *base* name from
the gamemaster (`speciesName` minus the `(Shadow)` parenthetical), or
strips the suffix somewhere in the title template.

**Proposed fix:** patch the dive's H1 title generator to include the full
display name (with whichever shadow convention G4 settles on). If G4
adopts `Shadow X` globally, this is a one-line consequence of that rename
since the same `_pretty_species` helper produces the H1.

**Question for you:** sequenced after G4. If G4 = (c), G5 falls out for
free.

### G6. (NEW 5/4-5/8) Authorship promotion: ai → both, no attribution

**Plan (per your Discord message 5/7):** "my default is going to be to
change the pages to my 'AI + human' tag but not to acknowledge you
directly, since you've avoided having your name on stuff in the past."

**Mercuryish (5/8):** "AI + human works fine with me."

**Concretely:** flip `authorship = "ai"` → `authorship = "both"` in each
reviewed guide's `guide.toml`. Currently `authorship = "ai"` on the four
unreviewed guides (How This Works, IV Flavor Guide, CD Article, Deep-Dive
Scatter — per memory `project_user_facing_docs`). Envelope Position and
Threshold Tiers are already at `"both"`. Under the Hood is at `"ai"`.

**After this review's edits ship,** mercuryish will have effectively
co-reviewed:

- How This Works (HTW items)
- Threshold Tiers (already `both`)
- Envelope Position (already `both`)
- CD Article (CD items)
- Deep-Dive Scatter (DDS items)
- Under the Hood (UTH items)
- IV Flavor Guide (IFG items)

i.e. all 7 guides. So all 7 can move to `authorship = "both"` once their
respective edits are applied. The banner color flips from orange (ai) to
green (both); no name appears in the banner.

**Action:** after applying each per-guide review file's edits, also flip
that guide's `guide.toml` authorship field. I'll bundle the flips into
each guide-edit commit so a guide is never "edited but still claiming
ai-only authorship."

**Question for you:** sound right? Anything to handle differently from
"flip authorship on commit-of-edits"?
