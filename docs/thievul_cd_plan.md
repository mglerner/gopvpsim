# Thievul CD dive - plan of record (written 2026-08-14, for the 08-15 session)

**Deadline: the CD is Sunday 2026-08-16, 2-5pm local.** The dive +
article should publish Saturday so it answers "should I grind this CD
for PvP" before the event.

## Facts (verified 2026-08-14)

- Nickit Community Day, Sun Aug 16 2026: evolve Nickit during the
  event or up to 4h after for Thievul with **Icy Wind** (Ice charged
  attack, not TM-able afterward). Sources: Niantic announcement
  (pokemongo.com/en/news/communityday-august-2026-nickit), GO Hub,
  Dexerto.
- Thievul: Dark type. Legal pool in the gamemaster today -- fast:
  Quick Attack / Snarl / Sucker Punch; charged: Night Slash / Play
  Rough.
- **The gamemaster genuinely lags (CD-prep rule check DONE).** Checked
  2026-08-14 against pvpoke origin/master (`e5ee9b767`): Thievul has
  NO Icy Wind, NO `eliteMoves` entry, and no thievul/icy-wind commit
  in the log. ICY_WIND itself exists in the moves db (Baxcalibur has
  it). So `[cd_prep]` injection of `ICY_WIND` into the charged pool is
  CORRECT here -- this is the opposite of the 2026-06 Baxcalibur trap
  recorded in CLAUDE.md.

## The work (Oinkologne CD recipe)

1. GL deep dive, focal Thievul, `[cd_prep]` TOML table injecting
   `cd_prep_charged = "ICY_WIND"` (plumbing:
   `enumerate_movesets(..., cd_prep_charged=)`, commit `e61c14e`).
   Check whether Thievul even reaches 1500 comfortably / whether a UL
   cap matters (almost certainly GL-only).
2. Moveset comparison for the CD question: Icy Wind vs Play Rough as
   the second charged move (and Snarl vs Sucker Punch fast) --
   `compare_loadouts.py` if it fits N=2.
3. CD article via `generate_article.py`; narrative blocks follow the
   ship-mode policy (auto-gen templates or leave empty for Michael --
   NO Claude prose in `[intro]`/`[meta_role]`/`[Species.*]`).
4. Angle worth a sentence: the CD lands 12 days before Worlds
   (Aug 28-30, open GL), so Icy Wind Thievul is technically obtainable
   for Worlds-format play.

## Operational cautions (both matter, both from the Worlds arc)

- **The data cache currently holds the PINNED pre-Worlds gamemaster**
  (`8f1d6cca5c0f`, the full old blob from pvpoke `f60a41199`). Letting
  it TTL-refresh to current is FINE for this dive (current pvpoke has
  no Icy Wind anyway; cd_prep injects regardless). But do NOT
  re-render any Worlds surface afterward without re-pinning first:
  `git -C ~/coding/pvpoke show f60a41199:src/data/gamemaster.json >
  ~/Documents/gopvpsim_cache/gamemaster.json` (verify
  `sweep_cache.gamemaster_hash()` returns `8f1d6cca5c0f`).
- **Sweep cache**: when the gamemaster stamp moves off the pin,
  warm-migrate instead of cold re-simming:
  `scripts/migrate_cache.py --from-gamemaster 8f1d6cca5c0f
  --old-gamemaster-file <old blob>`. The delta since the pin is
  purely additive (three Kalos mega forms), so the migration blesses
  every column. Keep the old blob retrievable from pvpoke git
  (`f60a41199`).
- cd_prep dives and the sweep cache coexisted fine in the Oinkologne
  arc; nothing new needed there.

## The request (from Michael's screenshots, 2026-08-14)

The dive is a direct user request on the launch post
(r/TheSilphArena): **u/LeansCenter** (9h before the screenshot):
"Thank you for your continued work on this! I use it alllll the time.
Any chance you'll have a GL Thievul deep dive before Comm Day? It
doesn't appear that Thievul is too spectacular in UL so no analysis
needed and besides, a Hundo is optimal anyway."

- **Scope: GL only, confirmed by the requester.** (Sanity-check the
  UL hundo claim in passing if cheap, but UL is not a deliverable.)
- LeansCenter is the SAME user whose top-10/20/50 + limited-cups
  feedback became the shipped top-N/cup filter -- second closed
  feedback loop with one person. When the dive ships, Michael can
  reply on that comment.
- Related thread context worth remembering: LeansCenter also asked
  (8-9d ago) whether the post-Worlds move rebalance will reshuffle
  per-species IV rankings (their example: Tinkaton 0/8/15 -- does a
  move nerf/buff move the top spread?). Michael replied he is looking
  forward to seeing the shifts. That is a natural post-rebalance
  analysis/article for later -- do not scope it into the Thievul
  session, just don't lose it.
- Post metadata for reference: Michael posts as u/SpaceBearAI; the
  post links mglerner.com/pogo-dives + the github repo; 36 upvotes /
  21 comments / 4.9K views despite a 4-day automod removal.
