# Tournament roster dumps (Dracoviz)

Per-team, per-mon roster dumps from Play! Pokemon GO Championship Series
events, used for meta/usage analysis (opponent pools, moveset audits,
Worlds-prep meta condensation). The original CP->IV reverse-engineering
purpose was tried and abandoned (see docs/TODO_backlog.md "Reverse-engineer
anchor intent from tournament CPs -- TRIED, ABANDONED").

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

| File                          | Event                                          | Source slug           | Data date  | Retrieved  | Teams |
| ----------------------------- | ---------------------------------------------- | --------------------- | ---------- | ---------- | ----- |
| `cs_2026_frankfurt.json`      | Frankfurt Regional Championships 2026          | `2026-frankfurt`      | 2025-09-15 | 2026-08-10 | 105   |
| `cs_2026_monterrey.json`      | Monterrey Regional Championships 2026          | `2026-monterrey`      | 2025-09-15 | 2026-08-10 | 155   |
| `cs_2026_pittsburgh.json`     | Pittsburgh Regional Championships 2026         | `2026-pittsburgh`     | 2025-09-22 | 2026-08-10 | 170   |
| `cs_2026_milwaukee.json`      | Milwaukee Regional Championships 2026          | `2026-milwaukee`      | 2025-10-14 | 2026-06-12 | 116   |
| `cs_2026_belo_horizonte.json` | Belo Horizonte Regional Championships 2026     | `2026-belo-horizonte` | 2025-10-14 | 2026-06-12 | 65    |
| `cs_2026_lille.json`          | Lille Regional Championships 2026              | `2026-lille`          | 2025-10-27 | 2026-08-10 | 156   |
| `cs_2026_brisbane.json`       | Brisbane Regional Championships 2026           | `2026-brisbane`       | 2025-11-01 | 2026-08-10 | 38    |
| `cs_2026_gdansk.json`         | Gdansk Regional Championships 2026             | `2026-gdansk`         | 2025-11-03 | 2026-08-10 | 94    |
| `cs_2026_las_vegas.json`      | Las Vegas Regional Championships 2026          | `2026-las-vegas`      | 2025-11-28 | 2026-08-10 | 193   |
| `cs_2026_laic.json`           | Latin America International Championships 2026 | `2026-laic`           | 2025-11-29 | 2026-08-10 | 266   |
| `cs_2026_stuttgart.json`      | Stuttgart Regional Championships 2026          | `2026-stuttgart`      | 2026-01-06 | 2026-08-10 | 80    |
| `cs_2026_toronto.json`        | Toronto Regional Championships 2026            | `2026-toronto`        | 2026-01-20 | 2026-08-10 | 185   |
| `cs_2026_birmingham.json`     | Birmingham Regional Championships 2026         | `2026-birmingham`     | 2026-02-05 | 2026-08-10 | 141   |
| `cs_2026_merida.json`         | Merida Regional Championships 2026             | `2026-merida`         | 2026-02-06 | 2026-08-10 | 148   |
| `cs_2026_euic.json`           | Europe International Championships 2026        | `2026-euic`           | 2026-02-16 | 2026-06-12 | 407   |
| `cs_2026_santiago.json`       | Santiago Regional Championships 2026           | `2026-santiago`       | 2026-02-16 | 2026-08-10 | 80    |
| `cs_2026_sydney.json`         | Sydney Regional Championships 2026             | `2026-sydney`         | 2026-02-16 | 2026-08-10 | 62    |
| `cs_2026_auckland.json`       | Auckland Special Championships 2026            | `2026-auckland`       | 2026-02-23 | 2026-08-10 | 24    |
| `cs_2026_san_juan.json`       | San Juan Special Championships 2026            | `2026-san-juan`       | 2026-03-09 | 2026-06-12 | 13    |
| `cs_2026_seattle.json`        | Seattle Regional Championships 2026            | `2026-seattle`        | 2026-03-09 | 2026-08-10 | 188   |
| `cs_2026_curitiba.json`       | Curitiba Regional Championships 2026           | `2026-curitiba`       | 2026-03-16 | 2026-06-12 | 82    |
| `cs_2026_houston.json`        | Houston Regional Championships 2026            | `2026-houston`        | 2026-03-24 | 2026-06-12 | 135   |
| `cs_2026_seville.json`        | Seville Special Championships 2026             | `2026-seville`        | 2026-03-30 | 2026-06-12 | 92    |
| `cs_2026_cape_town.json`      | Cape Town Special Championships 2026           | `2026-cape-town`      | 2026-04-01 | 2026-06-12 | 8     |
| `cs_2026_orlando.json`        | Orlando Regional Championships 2026            | `2026-orlando`        | 2026-04-06 | 2026-04-18 | 156   |
| `cs_2026_queretaro.json`      | Querétaro Regional Championships 2026          | `2026-queretaro`      | 2026-04-06 | 2026-06-12 | 224   |
| `cs_2026_prague.json`         | Prague Regional Championships 2026             | `2026-prague`         | 2026-04-28 | 2026-06-12 | 119   |
| `cs_2026_los_angeles.json`    | Los Angeles Regional Championships 2026        | `2026-los-angeles`    | 2026-05-11 | 2026-06-12 | 141   |
| `cs_2026_utrecht.json`        | Utrecht Regional Championships 2026            | `2026-utrecht`        | 2026-05-18 | 2026-06-12 | 120   |
| `cs_2026_campinas.json`       | Campinas Regional Championships 2026           | `2026-campinas`       | 2026-05-18 | 2026-06-12 | 88    |
| `cs_2026_melbourne.json`      | Melbourne Regional Championships 2026          | `2026-melbourne`      | 2026-05-24 | 2026-06-12 | 62    |
| `cs_2026_lima.json`           | Lima Special Championships 2026                | `2026-lima`           | 2026-05-26 | 2026-06-12 | 57    |
| `cs_2026_indianapolis.json`   | Indianapolis Regional Championships 2026       | `2026-indianapolis`   | 2026-06-01 | 2026-06-12 | 182   |
| `cs_2026_turin.json`          | Turin Special Championships 2026               | `2026-turin`          | 2026-06-09 | 2026-06-12 | 138   |
| `cs_2026_buenos_aires.json`   | Buenos Aires Special Championships 2026        | `2026-buenos-aires`   | 2026-06-09 | 2026-08-10 | 36    |
| `cs_2026_naic.json`           | North America International Championships 2026 | `2026-naic`           | 2026-06-15 | 2026-08-10 | 331   |

## Format caveats

- All events are Great League CP-capped (1500), **but the three
  Internationals used LIMITED metas** (type/species-restricted formats
  per their Liquipedia "Pokemon Format" sections): EUIC
  (Dark/Dragon/Bug/Normal+), LAIC (Dragon/Flying/Ghost/Ice/Psychic+,
  no Shadows), NAIC (Fairy/Normal/Psychic/Water+). Regionals and
  Special Championships were open GL. **Exclude EUIC/LAIC/NAIC from
  any open-meta usage analysis** (e.g. Worlds-prep meta condensation);
  their rosters answer a different question.
- CPs are self-reported at team submission; a small number of entries
  are obvious typos or unleveled placeholders (e.g. CP 10/12 mons in
  Campinas/Turin, CP 580 Lapras in Indianapolis). Filter `cp < ~1300`
  before using CPs. Counts of cp<1300 entries: Orlando 8, Prague 6,
  LA 16, Utrecht 0, Campinas 19, Indianapolis 13, Turin 37, Frankfurt
  1, Monterrey 13, Pittsburgh 2, Lille 0, Brisbane 0, Gdansk 0,
  Las Vegas 24, LAIC 106, Stuttgart 0, Toronto 12, Birmingham 0,
  Merida 27, Santiago 5, Sydney 3, Auckland 1, Seattle 17, Buenos
  Aires 0 (but 65 empty-string CPs), NAIC 52. `cp` is stored as a
  string in most files and as int in some of the 2026-08-10 batch;
  Buenos Aires includes empty-string `''` values -- coerce and drop
  non-numeric before any CP math.
- Some teams submitted short rosters (<6 mons): Orlando 1, Prague 1,
  LA 5, Campinas 6, Indianapolis 2, Turin 12, Utrecht 0, and in the
  2026-08-10 batch: LAIC 25, NAIC 12, Toronto 8, Merida 8, plus 0-2
  each elsewhere. Melbourne and Lima each have 2 records with no
  `roster` field at all -- consume rosters via `r.get('roster') or []`,
  never `r['roster']`.
- `cs_2026_buenos_aires.json` is a **late backfill, not a June event**:
  the event ran in September 2025 (early-season Special Championship)
  but its rosters were uploaded 2026-06-09, so its "data date" does not
  follow the "shortly after the event weekend" convention above.
- `fast` move names sometimes carry a trailing `*` (Dracoviz's marker
  for legacy/Elite TM moves), e.g. `"Psywave*"`.
- Regional/form variants are encoded in `name`/`form` Dracoviz-style;
  `scripts/build_opponent_pool.py:_dracoviz_to_pvpoke_name` has the
  mapping to PvPoke species names.
- Turin, Lima, Cape Town, Seville, San Juan are "Special
  Championships" (smaller/online-qualifier-style events); the roster
  schema is identical to regionals.

## Known events not captured here (as of 2026-08-10)

- `2026-worlds` returns an empty array -- Worlds 2026 (Aug 28-30, San
  Francisco) rosters not yet uploaded. NB the endpoint returns `200 []`
  for both "not uploaded yet" and "no such slug", so empty is not
  evidence the slug is wrong. Re-poll as the event approaches.
- Also empty: `2026-pjcs` (Japan Championships) and every regional
  qualifier/playoff slug (`2026-apac-*`, `2026-india-*`, etc.).
- Slug discovery: there is no listing API; the full event list lives in
  the Gatsby page-data blob:
  `curl -s 'https://www.dracoviz.com/page-data/index/page-data.json' |
  grep -oE '202[56]-[a-z0-9-]+' | sort -u`
