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
