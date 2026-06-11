# deep_dive.py perf summary (10 dive log(s))

Source: `userdata/logs/2026-04`
Filter: `--since 20260419_170000`

## Per-dive summary

| Start ts            | Species             | League | Sh  | Bucket        | Total elapsed | Total sims | Aggregate sims/s |
| ------------------- | ------------------- | ------ | --- | ------------- | ------------- | ---------- | ---------------- |
| 2026-04-19 17:30:28 | Oinkologne          | great  |     | gl_full       | 62m00s        | 33,874,425 | 9,106            |
| 2026-04-19 18:32:30 | Oinkologne (Female) | great  |     | gl_full       | 62m44s        | 33,297,225 | 8,846            |
| 2026-04-19 19:35:17 | Tinkaton            | great  |     | gl_full       | 69m34s        | 35,810,450 | 8,579            |
| 2026-04-19 20:44:53 | Tinkaton            | ultra  |     | ul_full       | 79m35s        | 43,550,260 | 9,120            |
| 2026-04-19 22:04:30 | Aegislash (Blade)   | ultra  |     | ul_pinned     | 26m20s        | 15,910,058 | 10,069           |
| 2026-04-19 22:30:52 | Aegislash (Shield)  | ultra  |     | ul_full       | 72m44s        | 44,129,280 | 10,112           |
| 2026-04-19 23:43:37 | Forretress          | great  |     | forretress_cs | 23m46s        | 9,010,974  | 6,319            |
| 2026-04-20 00:07:24 | Forretress          | great  |     | forretress_cs | 47m07s        | 9,010,974  | 3,187            |
| 2026-04-20 00:54:33 | Forretress          | great  | ✓   | forretress_cs | 21m24s        | 9,010,974  | 7,017            |
| 2026-04-20 01:15:58 | Forretress          | great  | ✓   | forretress_cs | 25m19s        | 9,010,974  | 5,932            |

## Fallback baseline recommendations

Averages of per-dive total elapsed, by bucket. Plug these into `scripts/overnight_eta.py::FALLBACKS` as the new defaults (replacing the ad-hoc 40/35/6 guess).

| Bucket        | N   | Mean minutes | Median minutes | Min minutes | Max minutes |
| ------------- | --- | ------------ | -------------- | ----------- | ----------- |
| forretress_cs | 4   | 29.4         | 25.3           | 21.4        | 47.1        |
| gl_full       | 3   | 64.8         | 62.7           | 62.0        | 69.6        |
| ul_full       | 2   | 76.2         | 79.6           | 72.7        | 79.6        |
| ul_pinned     | 1   | 26.3         | 26.3           | 26.3        | 26.3        |

## Per-phase breakdown (slowest-first per dive)

### Oinkologne (great)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [4/5] Tackle / Body Slam, Trailblaze (Rank 1,  | 1,647,945 | 3m48s   | 7,216  |
| Interactive sweep [4/5] Tackle / Body Slam, Trailblaze (Rank 1,  | 1,647,945 | 3m46s   | 7,285  |
| Interactive sweep [4/5] Tackle / Body Slam, Trailblaze (PvPoke D | 1,647,945 | 3m36s   | 7,618  |
| Interactive sweep [4/5] Tackle / Body Slam, Trailblaze (PvPoke D | 1,647,945 | 3m33s   | 7,713  |
| Interactive sweep [1/5] Mud Slap / Body Slam, Trailblaze (Rank 1 | 1,647,945 | 2m25s   | 11,309 |

### Oinkologne (Female) (great)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [2/5] Tackle / Body Slam, Trailblaze (Rank 1,  | 1,619,865 | 3m48s   | 7,099  |
| Interactive sweep [2/5] Tackle / Body Slam, Trailblaze (Rank 1,  | 1,619,865 | 3m45s   | 7,193  |
| Interactive sweep [2/5] Tackle / Body Slam, Trailblaze (PvPoke D | 1,619,865 | 3m44s   | 7,230  |
| Interactive sweep [2/5] Tackle / Body Slam, Trailblaze (PvPoke D | 1,619,865 | 3m36s   | 7,476  |
| Interactive sweep [3/5] Mud Slap / Dig, Trailblaze (Rank 1, all  | 1,619,865 | 2m21s   | 11,428 |

### Tinkaton (great)

| Phase                                                           | Sims      | Elapsed | Sims/s |
| --------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [3/5] Fairy Wind / Gigaton Hammer, Play Rough | 1,742,130 | 3m05s   | 9,413  |
| Interactive sweep [3/5] Fairy Wind / Gigaton Hammer, Play Rough | 1,742,130 | 2m57s   | 9,806  |
| Interactive sweep [2/5] Fairy Wind / Gigaton Hammer, Heavy Slam | 1,742,130 | 2m56s   | 9,892  |
| Interactive sweep [5/5] Fairy Wind / Bulldoze, Play Rough (Rank | 1,742,130 | 2m55s   | 9,924  |
| Interactive sweep [5/5] Fairy Wind / Bulldoze, Play Rough (Rank | 1,742,130 | 2m54s   | 9,983  |

### Tinkaton (ultra)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [5/5] Fairy Wind / Flash Cannon, Gigaton Hamme | 1,773,540 | 3m13s   | 9,157  |
| Interactive sweep [5/5] Fairy Wind / Flash Cannon, Gigaton Hamme | 1,773,540 | 3m11s   | 9,256  |
| Interactive sweep [3/5] Fairy Wind / Gigaton Hammer, Play Rough  | 1,773,540 | 3m10s   | 9,325  |
| Interactive sweep [3/5] Fairy Wind / Gigaton Hammer, Play Rough  | 1,773,540 | 3m08s   | 9,410  |
| Interactive sweep [5/5] Fairy Wind / Flash Cannon, Gigaton Hamme | 1,773,540 | 3m07s   | 9,458  |

### Aegislash (Blade) (ultra)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [1/1] Psycho Cut / Flash Cannon, Shadow Ball ( | 1,961,514 | 2m36s   | 12,508 |
| Interactive sweep [1/1] Psycho Cut / Flash Cannon, Shadow Ball ( | 1,961,514 | 2m33s   | 12,805 |
| Interactive sweep [1/1] Psycho Cut / Flash Cannon, Shadow Ball ( | 1,961,514 | 2m32s   | 12,895 |
| Interactive sweep [1/1] Psycho Cut / Flash Cannon, Shadow Ball ( | 1,961,514 | 2m31s   | 12,909 |
| Interactive sweep [1/1] Psycho Cut / Flash Cannon, Shadow Ball ( | 1,961,514 | 2m31s   | 12,945 |

### Aegislash (Shield) (ultra)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [3/5] Aegislash Charge Psycho Cut / Flash Cann | 1,797,120 | 3m10s   | 9,412  |
| Interactive sweep [3/5] Aegislash Charge Psycho Cut / Flash Cann | 1,797,120 | 3m08s   | 9,543  |
| Interactive sweep [1/5] Aegislash Charge Psycho Cut / Gyro Ball, | 1,797,120 | 3m04s   | 9,724  |
| Interactive sweep [3/5] Aegislash Charge Psycho Cut / Flash Cann | 1,797,120 | 3m04s   | 9,753  |
| Interactive sweep [3/5] Aegislash Charge Psycho Cut / Flash Cann | 1,797,120 | 3m03s   | 9,789  |

### Forretress (great)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m26s   | 12,914 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m25s   | 12,934 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m25s   | 12,976 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m25s   | 13,074 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (PvPo | 1,110,942 | 1m22s   | 13,407 |

### Forretress (great)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m35s   | 7,159  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m34s   | 7,212  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m33s   | 7,222  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m33s   | 7,241  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (PvPoke  | 1,110,942 | 2m31s   | 7,326  |

### Forretress (great/Shadow)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m22s   | 13,395 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m22s   | 13,398 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m22s   | 13,486 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m21s   | 13,572 |
| Interactive sweep [1/1] Volt Switch / Rock Tomb, Sand Tomb (Rank | 1,110,942 | 1m18s   | 14,177 |

### Forretress (great/Shadow)

| Phase                                                            | Sims      | Elapsed | Sims/s |
| ---------------------------------------------------------------- | --------- | ------- | ------ |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m25s   | 7,650  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m23s   | 7,736  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m23s   | 7,746  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (Rank 1, | 1,110,942 | 2m22s   | 7,803  |
| Interactive sweep [1/1] Bug Bite / Rock Tomb, Sand Tomb (PvPoke  | 1,110,942 | 2m18s   | 8,013  |
