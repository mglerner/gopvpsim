# Phase 4 plan — global naming rewrite (B1 + B3 + G4 + G5)

**Read before approving execution.** This is the high-risk phase I
committed to sketching before touching. Phases 1-3a are landed; 3b is
patched but awaiting a re-dive that's pre-staged for when you're back.

## What lands together

Four an HSH Discord member items, coordinated into one rename pass:

- **B1** — anchor-name capitalization in tier-card bullets (left side
  reads `lickilicky bulk`, right reads `Lickilicky`)
- **B3** — Oinkologne (Female) named, Oinkologne (Male) bare. You picked
  option (b) — global symmetric rename.
- **G4** — Shadow Pokemon naming. You picked global rename to "Shadow X"
  (not "X (Shadow)") everywhere. Same convention applies to Galarian /
  Alolan / Hisuian / Paldean.
- **G5** — dive top-banner missing "shadow" for shadow focal species —
  falls out for free once G4 is global.

These four can't ship independently without producing internal
inconsistencies (e.g., a tier-card bullet that says "Shadow Forretress"
on the left but `Forretress (Shadow)` in the opponent list, etc.). So
they ride one commit.

## Target output

| Input (gamemaster `speciesName`)          | Output (display)                                        |
| ----------------------------------------- | ------------------------------------------------------- |
| `Forretress`                              | `Forretress`                                            |
| `Forretress (Shadow)`                     | `Shadow Forretress`                                     |
| `Corsola (Galarian)`                      | `Galarian Corsola`                                      |
| `Ninetales (Alolan)`                      | `Alolan Ninetales`                                      |
| `Weezing (Galarian) (Shadow)`             | `Shadow Galarian Weezing`                               |
| `Oinkologne` (when Female sibling exists) | `Oinkologne (Male)`                                     |
| `Oinkologne (Female)`                     | `Oinkologne (Female)`                                   |
| `Aegislash (Shield)`                      | `Aegislash (Shield)` (form, not regional — leave alone) |
| `Aegislash (Blade)`                       | `Aegislash (Blade)`                                     |
| `Mimikyu (Busted)`                        | `Mimikyu (Busted)`                                      |

## The helper

Single function `pretty_species(name)` in (proposed) `src/gopvpsim/display.py`:

```python
_REGIONAL_TAGS = ('Shadow', 'Galarian', 'Alolan', 'Hisuian', 'Paldean')
_FORM_TAGS = frozenset(['Shield', 'Blade', 'Busted', 'Disguised',
                       'Full Belly', 'Hangry', 'Super', 'Large', 'Small',
                       'Average', 'Female'])

def pretty_species(name: str, *, female_sibling_bases: set[str]) -> str:
    """Reformat a gamemaster speciesName for display.

    Shadow / regional parentheticals move to a prefix; bare-male names
    gain '(Male)' when the species has a Female sibling form in the
    gamemaster. Non-regional form parentheticals (Shield/Blade, Busted,
    etc.) are left alone — they're in-battle form changes, not regional
    or shadow flavors.
    """
    prefixes: list[str] = []
    base = name
    # Iteratively strip ' (Shadow)' / ' (Galarian)' / etc.
    while True:
        matched = False
        for tag in _REGIONAL_TAGS:
            suffix = f' ({tag})'
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                prefixes.append(tag)
                matched = True
                break
        if not matched:
            break

    if prefixes:
        # Shadow goes outermost; regionals follow.
        ordered = sorted(prefixes, key=lambda p: 0 if p == 'Shadow' else 1)
        result = ' '.join(ordered) + ' ' + base
    else:
        result = base

    # Gender disambiguation for bare male forms.
    bare_no_paren = base  # already stripped of regional/shadow
    if (bare_no_paren in female_sibling_bases
            and '(Female)' not in base
            and not any(form in base for form in _FORM_TAGS)):
        result = result + ' (Male)'

    return result
```

`female_sibling_bases` is precomputed once per process from the
gamemaster: scan for any speciesName containing `(Female)`, strip the
suffix, add the bare base to the set.

## Edit sites

Display-only surfaces. Lookups against `gamemaster.speciesName` stay
unchanged — `pretty_species` is applied at the leaf where the user
reads the string.

**Python (server-side rendering):**

1. `scripts/deep_dive_rendering.py`
   - `_opp_b()`, `_opp_strong()` → wrap name in `pretty_species` before
     emitting. ~2 LOC each.
   - `_opp_color()` keeps the gamemaster name (color hash unchanged
     across rename so the same Pokemon stays the same color).
   - Tier-card bullet `anchor_label` — covered by B1's `derive_display_name`
     rewrite (next bullet).

2. `src/gopvpsim/anchors.py`
   - `derive_display_name()` head-recasing logic — re-uses the same
     name-formatting convention (Shadow X, etc.) by mapping the slug
     (`forretress_shadow`) → pretty_species output. ~10 LOC.

3. `scripts/deep_dive.py`
   - Dive `<title>` and H1 banner — apply `pretty_species` when
     constructing.
   - Scatter trace name (the focal species banner on the legend) —
     same.
   - Emit `data_obj['opponentsDisplay']` as a parallel list to
     `data_obj['opponents']`: the same opponents, prettified. JS uses
     it for display only. Adds one new key, no JS-side helper needed.

4. `scripts/generate_article.py` (CD article generator)
   - Form labels (Female / Male columns in Stats at a Glance,
     Matchup Delta, Female vs Male section) — prettify.
   - Opponent column cells in matchup tables — prettify.
   - PvPoke multi-battle link's display string — prettify.

5. `scripts/compare_loadouts.py` (comparison page generator)
   - Loadout labels in headers — prettify.

6. `scripts/build_website_index.py`
   - `_slug_to_pretty_title()` already does some of this; refactor to
     use the same `pretty_species` helper for consistency.

7. `scripts/auto_gen_narrative.py` (narrative templates)
   - Every interpolation of `opponent` or `species` in template
     strings → prettify.

8. `scripts/write_aegislash_narrative.py`
   - Focal species mentions ("Aegislash", "Aegislash (Shield)",
     "Aegislash (Blade)") — none of these need rewriting since neither
     species has a regional/shadow variant and Shield/Blade are
     non-regional form tags. No-op for this script.

**JavaScript (client-side):**

9. `scripts/deep_dive_engine.js`
   - Hover card builder: use `DATA.opponentsDisplay[idx]` instead of
     `DATA.opponents[idx]` for display text. ~2 LOC per surface.
   - Dropdowns (Shields / Opponent IVs / Bait) — these don't show
     opponent names, no change.
   - Tier-card "of yours" rendering uses the precomputed bullet HTML
     which is already prettified server-side; no JS change.
   - Paste-box matching uses `DATA.opponents` (gamemaster name) for
     lookup, unchanged.

10. `scripts/deep_dive_user_collection.js`
    - Same pattern: lookups against gamemaster name, display via
      `opponentsDisplay`.

**Site / sources:**

11. TOML threshold files don't store opponent display names; they
    use gamemaster names internally and produce display strings via
    the renderers. No edits to thresholds/*.toml needed.

12. Article TOMLs (e.g. `articles/oinkologne-cd-2026-05.toml`) — same.

13. opponent_pools/*.txt — these are gamemaster name lists used for
    pool resolution. No change.

## Risks and how I'll de-risk

**Risk 1: missing a display site.** A handful of "Forretress (Shadow)"
strings sneak through and the site reads inconsistently.

Mitigation: after the edit pass, grep the rendered site for the old
format: `grep -rE '\([A-Z][a-z]+\) ?(Shadow|Galarian|...)' userdata/website/`.
Any hit is a missed display site.

**Risk 2: breaking a lookup.** A renderer compares a prettified name
to a gamemaster name and the comparison silently fails.

Mitigation: keep `pretty_species` as a display-only function. NEVER
store its output in `data_obj['opponents']`, `attacker.species`, etc.
Always at the LAST mile, at HTML emit time.

**Risk 3: paste-box bug regression.** The Female Oinkologne paste-box
bug you flagged earlier is probably caused by a name-format mismatch
between PokeGenie CSV ("Oinkologne ♀"?) and our dive's species filter.
If the PokeGenie name uses `(Female)` already and our pretty_species
output also retains `(Female)`, no regression. If PokeGenie uses `♀`
or `(F)` etc., separate bug — won't be fixed by Phase 4, won't be made
worse either.

Mitigation: after Phase 4 lands, test the Female Oinkologne paste-box
with your CSV (Phase 5a task). Either confirm fixed-by-rename or
diagnose as a separate issue.

**Risk 4: search-and-replace catastrophe.** Doing this as a regex
sweep risks rewriting strings inside comments, docstrings, or test
fixtures that shouldn't change.

Mitigation: NOT going to use sed/regex. Every edit goes through Edit
tool, scoped to the specific call site. Per CLAUDE.md "Surgical Changes."

**Risk 5: Test fixtures break.** Tests that assert on tier-card HTML
or anchor labels would see the new format.

Mitigation: run the full test suite after the Python-side rename.
Update fixtures that legitimately need to follow the new format; for
any test asserting on `Forretress (Shadow)` literal, decide
case-by-case.

## Execution order

1. Add `src/gopvpsim/display.py` with `pretty_species()` + helper
   for precomputing `female_sibling_bases`. Unit tests for the
   helper.
2. Edit `derive_display_name` in `anchors.py` to use the new
   convention. Run tests/test_anchors.py + tests for any caller.
3. Edit `_opp_b`/`_opp_strong` and immediately adjacent display
   call sites in `deep_dive_rendering.py`. Run dive renderer on
   ONE species locally (Oinkologne GL is fast, ~5 min) to eyeball.
4. Edit the CD article + comparison page + site index renderers.
   Run `python scripts/generate_article.py articles/oinkologne-cd-2026-05.toml`
   to eyeball.
5. JS-side: emit `opponentsDisplay`, wire hover card.
6. Eyeball one rendered dive in browser; look for missed sites.
7. Full test suite. Fix any fixture breakage.
8. Full site re-dive + re-render (this is the part that takes
   real wall-clock time).
9. Grep-check the rendered site for any surviving old-format
   strings.
10. Commit.

Wall-clock estimate: 1-2 hours of code work + however long a full
re-publish takes on your machine. Most of the rendered-site
regeneration cost is the re-dive of every species — IF we re-dive,
which we'd want to do at least for Oinkologne GL and Aegislash
(Blade) GL (which is already pending the S1 patch). A "re-render
HTML only" path that re-reads the cached score arrays would be
faster than a full re-dive; need to check whether that's a
supported flow in `scripts/publish_website.sh` before committing
to a timeline.

## What I want before I touch any of this

Two questions:

1. **Is the `(Male)` suffix correct stylistically, or do you want
   `Male X` to mirror the regional/shadow prefix convention?** I.e.
   `Oinkologne (Male)` vs `Male Oinkologne`. I led with the
   parenthetical because that's what PvPoke already uses for the
   `(Female)` form, but you may prefer symmetry with the regional
   tags.

2. **OK to ship the rename without re-diving every species?** A
   "render-only" republish that re-reads cached score arrays would
   be much faster than full re-dives. Some sites' dive HTML may be
   stale-but-correct on the gamemaster-name front; we'd just refresh
   the display. If you'd rather do a full re-dive sweep for safety,
   say so — that's a longer wall-clock but cleaner end state.

If you sign off on the plan (with answers to those two), I execute
end-to-end.
