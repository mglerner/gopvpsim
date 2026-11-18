# Article archiving: dated snapshots beside a stable slug

Decided 2026-08-31 (Michael). Written ahead of the Twilight Trails move
rebalance (2026-09-08) so the archive path exists before it is needed.

## The problem

After a move rebalance, each article gets a per-article regen / no-regen
decision gated on meta relevance in open + cups (TODO.md "Article regen
triage"). That decision needs somewhere for the old version to go.

Two constraints pull against each other:

- **URL stability.** Inbound links exist in the wild (Reddit, Discord).
  A directory rename changes the URL and breaks them.
- **Recurrence.** The same cup returns in a later season with a
  rebalance in between, so one slug has to hold two vintages -- e.g. an
  Equinox Cup this season and another next season, built on different
  move data.

A single stable slug cannot satisfy both. Neither can date-stamping
every slug.

## The pattern

**Bare slug = current. Dated slug = archived snapshot.**

    articles/clodsire-equinox-cup              always the current version
    articles/clodsire-equinox-cup-2026-08-31   frozen pre-rebalance snapshot

Archiving **copies** the current render to a vintage-stamped slug and
marks the copy. The bare slug is then regenerated in place by the normal
pipeline. Inbound links never break -- they always land on current data
-- and history is preserved. Next season regenerates the bare slug and
files another stamped copy beside the first.

The date lands on the archived copy, not on the thing people link to.

## Stamp the DATA vintage, not the archive date

What distinguishes two Equinox articles is the gamemaster/rankings they
were built on, not when someone filed them; those can be months apart,
and the filing date tells a reader nothing.

`scripts/archive_article.py` therefore **requires** `--vintage` and
never guesses it. Archiving happens *after* the new data has landed, so
the live gamemaster stamp at archive time is the NEW one -- defaulting
to it would label the snapshot with data it was not built on, which is
precisely the never-ship-unflagged-known-wrong failure. The operator
states what the article was built on.

`--stamp` optionally records the sweep_cache v7 narrow gamemaster hash
alongside the date (the 2026-08-31 baseline is `c431557dcc76`; see
DEVELOPER_NOTES "Pre-rebalance data vintage pin").

## Why archive rather than delete

`build_website_index.py` already hard-fails when a rendered page with an
`index.html` is unreachable from the index nav (`load_entries`'
`dropped_pages`, "the F1 silent-incompleteness lens, baked into the
producer"). Archived entries stay in the index -- in their own collapsed
section -- so they never trip that guard. Deleting the directory
outright is still a valid choice; anything in between is not.

## Index rendering

Archived entries are split out before the ML-IV-guide split (the guide
split matches `-ml-iv-guide` as a *substring*, so an archived guide
would otherwise flood the chip row) and render in a collapsed
`<details>` block under Articles, labelled with their vintage.

## It also makes an existing claim true

`cups.html` already tells readers "Dated snapshots kept as an archive"
(`build_website_index.py` `_cup_status_line`), and as of 2026-08-31 no
dated snapshot directory existed anywhere on the site. The recurrence
case above is exactly when a reader would notice.

**Scope note:** this ships for *articles* only. Cup dives are a
different surface -- they carry no `meta.toml` and are discovered by
HTML-title fallback -- so extending the pattern to them means giving
dives a `meta.toml` first. Until that happens the `cups.html` sentence
remains ahead of the implementation for dives. Separately unverified:
the other half of that sentence, "open a dive for its exact rankings
snapshot date" -- the cup dive pages were not confirmed to display one.

## Site lifecycle and removal policy

(Moved verbatim from TODO.md "Site lifecycle policy (Michael, 2026-09-02)"
and "Article regen triage" on 2026-11-18; the removal mechanism's line
cites were re-checked then. The open regen items stay in TODO.md "Article
regen triage".)

Standing shape, seasons repeat:

1. A new season is announced.
2. Things get added to the site progressively through the season
   (cups, event/CD articles, condensed-meta surfaces).
3. **At the start of the next season, ALL of it comes down**, and the
   new season's surfaces get added as needed. Rinse, repeat.

The live site is centered on current live content; nothing is left up
carrying a staleness caveat (see "Article regen triage"). Retired
surfaces are re-renderable from their replay blobs, and articles worth
keeping archive as dated snapshots via
`scripts/archive_article.py` (docs/article_archive_plan.md).

What a season-start bake covers is the step list of
`scripts/overnight_redive.sh` (`grep -n '^step \|\[STEP\]'
scripts/overnight_redive.sh`; the IV-guide step runs outside `step()`):
`run_website_dives.py` (all GL/UL/ML dive entries), the ML IV guides via
`run_iv_guides.py` over `master_top60` (a separate multi-hour job, most of
the article surface), the comparison renders + GL/UL matchup webs (need
sims), then reader's guides, index rebuild and ship gates (render-only).

DECIDED (Michael, 2026-08-31) -- **no staleness markers; the live site
is centered on current live stuff.** A no-regen article is REMOVED from
the site rather than left up with a caveat. This satisfies the
never-ship-unflagged-known-wrong rule by not shipping the wrong page at
all, which is stronger than flagging it.

(Tension, noted 2026-11-18: DEVELOPER_NOTES.md "Article lifecycle"
documents the `[obsolescence]` red-banner mechanism -- a staleness marker
-- without mentioning this decision. Under this policy the banner is not
used on the live site.)

Mechanism if you instead DELETE outright: remove the rendered dir from
`userdata/website/articles/`, then re-run `build_website_index.py`.
The index discovers articles by scanning
`userdata/website/articles/*/meta.toml`
(`build_website_index.py` module docstring, `ARTICLES_DIR` at :49), so the
card disappears on its own, and `publish_website.sh` rsyncs with `--delete`
(:237), so the live page goes with it. No hand-editing of index.html.

If a removed article is worth keeping, it archives in the **git repo**,
not on the site. Wrinkle to solve when it first comes up: `userdata/`
is gitignored (`.gitignore:43`), so archiving a *rendered* page needs a
tracked path -- the cheap alternative is to keep only the source
(`articles/*.toml` is already tracked) and re-render from it if ever
wanted.

### Season-start regen triage (from TODO)

(Copied verbatim from TODO.md "Article regen triage" as of 6c7a960. The
counts are as of 2026-08-31; on 2026-11-18 there are 61 rendered dirs, 60
of them `*-ml-iv-guide`.)

Michael, 2026-08-31: once the full move-update data is live, **every
article gets a per-article regen / no-regen decision** -- we do not
blanket-regenerate. The gate is meta relevance in **open + cups**: an
article about a species that is far out of the meta on both does not
earn a regen, however stale its numbers.

The surface (62 rendered dirs under `userdata/website/articles/`):

- **61 `*-ml-iv-guide`** dirs, driven by `opponent_pools/master_top60.txt`
  (`run_iv_guides.py`). ML is where Lugia's new Earth Power lands, so
  this is not a low-churn surface.
- **`cramorant-pogodives-strategy`** -- couples to the fitted-constant
  re-verification already in `docs/rebalance_checklist.md` section A
  step 3; don't regen it before that passes.
- **`articles/oinkologne-cd-2026-05.toml`** -- still all PLACEHOLDER
  bodies, so nothing is shipped and nothing is wrong today. Worth
  knowing before anyone picks it up: its comparison axis is Mud Slap
  vs Tackle/Take Down, and **Take Down goes 5->14 power with increased
  energy gain**, which can invert the article's thesis. Decide
  regen-vs-drop on the meta test above before spending an authoring
  session on it.
