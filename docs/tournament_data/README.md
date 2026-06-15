# Tournament roster dumps (Dracoviz)

Per-team, per-mon roster dumps from Play! Pokemon GO Championship Series
events, used for reverse-engineering anchor intent from tournament CPs
(see TODO.md "Reverse-engineer anchor intent from tournament CPs").

## Source

All files are raw responses from Dracoviz's public tournament API:

    https://www.dracoviz.com/api/tournament/?searchType=tm&tm=<slug>

fetched via `scripts/fetch_dracoviz_tournament.py <slug>`. The endpoint
needs the site-wide `x_authorization` header baked into that script (a
rate-limit token from Dracoviz's public Gatsby bundle, not a user
secret; override with `DRACOVIZ_AUTH` if rotated). Human-readable event
pages live at `https://www.dracoviz.com/<slug>/`.

Each file is a JSON array with one record per submitted team:
`_id`, `name` (player handle), `tournament` (slug), `country`,
`final_rank`, `match_wins/losses`, `game_wins/losses`, `qualified`,
and a `roster` of up to 6 mons with `name`, `form`, `cp`, `fast`,
`charge1`, `charge2`, `best_buddy`, `shadow`, `purified`.

The "data date" below is decoded from the MongoDB `_id` timestamps
(all records in a dump share one creation date, shortly after the
event weekend; Houston is the one exception, with a few stragglers
two days later). All files have byte-identical schemas — no field
differences vs the original Orlando file.

## Files

| File                          | Event                                      | Source slug           | Data date  | Retrieved  | Teams |
| ----------------------------- | ------------------------------------------ | --------------------- | ---------- | ---------- | ----- |
| `cs_2026_milwaukee.json`      | Milwaukee Regional Championships 2026      | `2026-milwaukee`      | 2025-10-14 | 2026-06-12 | 116   |
| `cs_2026_belo_horizonte.json` | Belo Horizonte Regional Championships 2026 | `2026-belo-horizonte` | 2025-10-14 | 2026-06-12 | 65    |
| `cs_2026_euic.json`           | Europe International Championships 2026    | `2026-euic`           | 2026-02-16 | 2026-06-12 | 407   |
| `cs_2026_san_juan.json`       | San Juan Special Championships 2026        | `2026-san-juan`       | 2026-03-09 | 2026-06-12 | 13    |
| `cs_2026_curitiba.json`       | Curitiba Regional Championships 2026       | `2026-curitiba`       | 2026-03-16 | 2026-06-12 | 82    |
| `cs_2026_houston.json`        | Houston Regional Championships 2026        | `2026-houston`        | 2026-03-24 | 2026-06-12 | 135   |
| `cs_2026_seville.json`        | Seville Special Championships 2026         | `2026-seville`        | 2026-03-30 | 2026-06-12 | 92    |
| `cs_2026_cape_town.json`      | Cape Town Special Championships 2026       | `2026-cape-town`      | 2026-04-01 | 2026-06-12 | 8     |
| `cs_2026_orlando.json`        | Orlando Regional Championships 2026        | `2026-orlando`        | 2026-04-06 | 2026-04-18 | 156   |
| `cs_2026_queretaro.json`      | Querétaro Regional Championships 2026      | `2026-queretaro`      | 2026-04-06 | 2026-06-12 | 224   |
| `cs_2026_prague.json`         | Prague Regional Championships 2026         | `2026-prague`         | 2026-04-28 | 2026-06-12 | 119   |
| `cs_2026_los_angeles.json`    | Los Angeles Regional Championships 2026    | `2026-los-angeles`    | 2026-05-11 | 2026-06-12 | 141   |
| `cs_2026_utrecht.json`        | Utrecht Regional Championships 2026        | `2026-utrecht`        | 2026-05-18 | 2026-06-12 | 120   |
| `cs_2026_campinas.json`       | Campinas Regional Championships 2026       | `2026-campinas`       | 2026-05-18 | 2026-06-12 | 88    |
| `cs_2026_melbourne.json`      | Melbourne Regional Championships 2026      | `2026-melbourne`      | 2026-05-24 | 2026-06-12 | 62    |
| `cs_2026_lima.json`           | Lima Special Championships 2026            | `2026-lima`           | 2026-05-26 | 2026-06-12 | 57    |
| `cs_2026_indianapolis.json`   | Indianapolis Regional Championships 2026   | `2026-indianapolis`   | 2026-06-01 | 2026-06-12 | 182   |
| `cs_2026_turin.json`          | Turin Special Championships 2026           | `2026-turin`          | 2026-06-09 | 2026-06-12 | 138   |

## Format caveats

- All events are Great League (CP cap 1500). CPs are self-reported at
  team submission; a small number of entries are obvious typos or
  unleveled placeholders (e.g. CP 10/12 mons in Campinas/Turin,
  CP 580 Lapras in Indianapolis). Filter `cp < ~1300` before
  IV reverse-engineering. Counts of cp<1300 entries: Orlando 8,
  Prague 6, LA 16, Utrecht 0, Campinas 19, Indianapolis 13, Turin 37.
- Some teams submitted short rosters (<6 mons): Orlando 1, Prague 1,
  LA 5, Campinas 6, Indianapolis 2, Turin 12, Utrecht 0. Melbourne
  and Lima each have 2 records with no `roster` field at all.
- `fast` move names sometimes carry a trailing `*` (Dracoviz's marker
  for legacy/Elite TM moves), e.g. `"Psywave*"`.
- Regional/form variants are encoded in `name`/`form` Dracoviz-style;
  `scripts/build_opponent_pool.py:_dracoviz_to_pvpoke_name` has the
  mapping to PvPoke species names.
- Turin, Lima, Cape Town, Seville, San Juan are "Special
  Championships" (smaller/online-qualifier-style events); the roster
  schema is identical to regionals.

## Known events not captured here (as of 2026-06-12)

- `2026-naic` returns an empty array — NAIC rosters not yet uploaded
  (re-checked 2026-06-12).
