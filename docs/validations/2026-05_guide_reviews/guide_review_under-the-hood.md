# HSH Discord review — Under the Hood

Source: `guides/under-the-hood/body.md`. Per G6, also flip authorship
`ai` → `both` once edits applied.

---

## Item 1 [UTH-1]: define `xfail`

**An HSH Discord member:** "What does xfail mean?"

**Current** (`body.md:23-26`):

```text
The sim itself is a pure-Python port of PvPoke's JavaScript
ActionLogic and Battle engine; we verify exact score parity against
PvPoke on a fixed oracle set. When we diverge, we document and xfail
rather than quietly differ.
```

**Proposed:**

```text
The sim itself is a pure-Python port of PvPoke's JavaScript
ActionLogic and Battle engine; we verify exact score parity against
PvPoke on a fixed oracle set. When we diverge, we document the
divergence and pin the case as an **expected-failure** test (`xfail`,
the pytest term for a test we expect to fail until we either fix our
code or confirm PvPoke's number is wrong) rather than quietly
differ.
```

---

## Item 2 [UTH-2]: clarify "users can add their own thresholds"

**An HSH Discord member:** "Is it possible to add thresholds and anchors? I see you
list that it was possible for users to add their own thresholds, but I
do not understand how to do this. Is it possible to add anchors as well?"

**Likely culprit** (`body.md:223-237`):

```text
## Overriding any of this

The tool is designed so expert authoring always wins over automation.

- Adding a TOML anchor replaces whatever the auto-fallback would have
  produced on that axis.
- Adding a `[Species.intro]` / `[meta_role]` / `[verdict]` block in
  `thresholds/<species>.toml` replaces the auto-gen template for that
  species.
- Adding a named spread with `source = "..."` routes the anchor into
  the gold Expert zone so readers can tell it's your judgment call.

If you see something on a shipped dive that you disagree with,
there's a TOML knob for it.
```

Reads as if any reader can do it — but "adding a TOML anchor" requires
a local clone, running the dive locally, and a PR. An HSH Discord member assumed
there was a UI.

**Proposed:**

```text
## Overriding any of this — for project contributors

The tool is designed so expert authoring always wins over automation.
The overrides below all live in `thresholds/<species>.toml` and apply
on the next dive run. **There is no client-side UI for this today** -
adding or removing anchors / thresholds requires editing the TOML in
a local clone and re-running the dive. If you want a per-Pokemon
custom-anchor surface in your browser, that's a future feature; see
the project README for the current contribution flow.

- Adding a TOML anchor replaces whatever the auto-fallback would have
  produced on that axis.
- Adding a `[Species.intro]` / `[meta_role]` / `[verdict]` block in
  `thresholds/<species>.toml` replaces the auto-gen template for that
  species.
- Adding a named spread with `source = "..."` routes the anchor into
  the gold Expert zone so readers can tell it's your judgment call.

If you see something on a shipped dive that you disagree with,
there's a TOML knob for it. The auto-fallback is specifically
designed to stay out of the way when authored content is present.
```

**Question for you (cross-ref INDEX Q3):** if you do want to build a
client-side add/remove UI in the future, this paragraph should change to
point at it. For now, add this clarification and capture the feature as
a TODO.

---

## Item 3 [UTH-3]: removing thresholds and anchors

**An HSH Discord member:** "Is it possible to remove thresholds and anchors?"

Future feature, not a doc edit. Logging in INDEX Q3 with the "add"
version.

**Optional doc addition** (after UTH-2 paragraph):

```text
For removal: the auto-fallback layer is also gated, so a TOML that
hand-authors anchors against (say) Annihilape will not get the
auto-fallback's Annihilape additions on top — only auto-anchors
against opponents the TOML doesn't already cover. If a tier card has
too many bullets, the right move is usually adding a hand-authored
narrower anchor against that opponent rather than removing the
auto one.
```

---

## Item 4 [UTH-4 / G2]: "IV" → "IV spread" pass

| Line    | Current                                                                                                               | Proposed                                                                                                    |
| ------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 11-13   | "we sim each of the 4,096 possible IVs of the focal species (0/0/0, 0/0/1, ..., 15/15/14, 15/15/15)"                  | "we sim each of the 4,096 possible IV spreads of the focal species (0/0/0, 0/0/1, ..., 15/15/14, 15/15/15)" |
| 17      | "One 'score' per focal IV x opponent x scenario x opp-IV x bait cell"                                                 | "One 'score' per focal IV spread × opponent × scenario × opp-IV × bait cell"                                |
| 109-111 | "Every focal IV gets tagged with the set of anchors it passes."                                                       | "Every focal IV spread gets tagged with the set of anchors it passes."                                      |
| 117-118 | "the set usually collapses to 30-150 IVs over 3-4 rounds"                                                             | "the set usually collapses to 30-150 IV spreads over 3-4 rounds"                                            |
| 125-128 | "**Matchup categories** are synthesized per (opponent, scenario, bait mode) where an IV cohort wins that exact cell." | "...where an IV-spread cohort wins that exact cell."                                                        |
| 129-131 | "Categories are ranked on a selectivity metric (how many IVs pass vs the dive baseline)"                              | "...how many IV spreads pass vs the dive baseline"                                                          |
| 174-180 | "in 14 catches you have a 50% shot at seeing a qualifying IV"                                                         | "in 14 catches you have a 50% shot at seeing a qualifying IV spread"                                        |

**Notes:** ~6 places. The Notable IVs section heading is a literal UI
label; keep that as "IVs."

---

## Item 5 [UTH-5 / G3]: "PvPoke" / "pvpoke.com" usage check

Consistent. No edit.

---

## Summary of under-the-hood changes

If you accept UTH-1, UTH-2, UTH-3 (the optional bit), UTH-4:

- 1 inline definition (UTH-1, +1 phrase)
- 1 paragraph clarification (UTH-2, +3 lines)
- 1 optional paragraph addition (UTH-3, ~5 lines)
- ~6 wording tweaks for IV/IV-spread (UTH-4)

After Edit pass: rebuild guides + flip authorship to `both`.
