# OOTP Tournament Rosters

Last refreshed: 2026-10-08 from the active SQLite roster plans.

The **OOTP ID** is the number shown in parentheses beside the tournament name in
OOTP. Older planner records did not capture it, so those entries remain marked
`Not captured`. Newer automation records include the ID in the roster plan name.
Values such as `T-021` are older planner labels, and values such as `1002` or
`1006` are roster date suffixes, not OOTP tournament IDs.

## Quick

### Gold

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Quick Low Gold - UnH/Snap/RS | Gold; value 84 or lower | Not captured | Unsung Heroes, Snapshot, and Rookie Sensation only; DH; 1999 simulation |

### Mixed Tier Slots

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Quick Slots | P 2, D 3, G 4, S 5, B 6 | Not captured | DH; Gold scoring |

## Daily

### Iron

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Daily Dank | Value 49 or lower | 1140208 | No DH; max 13 variants; 1945 simulation; Comiskey Park (1945); Iron scoring |

### Bronze

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Daily Bronze Only | Bronze only | Not captured | DH; 1,689-point cap; max 13 variants; 2019 simulation; Bronze scoring |
| Daily Early Bronze | Bronze or lower | Not captured | No DH; no variants; 1942 simulation; Wrigley Field (1945) |

### Silver

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Daily Silver Only Cap | Silver only | Not captured | DH; 1,888-point cap; max 11 variants; 1998 simulation; Silver scoring |
| Daily Late Silver | Silver or lower | Not captured | Non-LIVE only; DH; 1992 simulation; Oriole Park at Camden Yards (1992); Silver scoring |

### Gold

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Daily Golden Heart | Gold or lower | Not captured | Card years 1930-1989; DH; 1956 simulation; Crosley Field (1958); Gold scoring |
| Daily Low Gold Only | Gold only; values 84 or lower | 1280207 | DH; max 8 variants; Fenway Park (2026); Gold scoring |

### Gold and Lower

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Daily Low Gold Cap | Gold or lower; values 84 or lower | 1910135 | DH; 1,610-point cap; 2007 simulation; Shea Stadium (2008); Gold scoring |

### Bronze-Gold Slots

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Daily Gold Slots | G 12, S 8, B 6; no Diamond or Perfect | 1320206 | DH; max 13 variants; 1968 simulation; Connie Mack Stadium (1968); Gold scoring |

### Diamond

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Daily Diamond Jumble | Diamond or lower | Not captured | AS, HaH, NeL, Snapshot, and Unsung Heroes only; DH; tier slots D 12, G 8, S 3, B 3; no Perfect; Diamond scoring |
| Daily Diamond to 1969 | Diamond or lower | Not captured | Card years through 1969; no DH; 2009 simulation; Coors Field (1996); Diamond scoring |
| Daily Low Diamond Only | Diamond only; values 90-94 | Not captured | DH; Coors Field (2000); Diamond scoring |

## Weekly

### Bronze

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Saturday Bronze Cap | Bronze or lower | Not captured | DH; 1,386-point cap; 2016 simulation; Bronze scoring |

### Silver

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Friday Nightmare Cap | Silver only; values 65 or higher | 1540029 | No DH; 1,805-point cap; max 6 variants; no Limited Edition cards; 1971 simulation; County Stadium (1970); Silver scoring |
| Tuesday Dead Silver Walking | Silver or lower | Not captured | Card years through 1920; no DH; 1919 simulation; Washington Park (1911); Silver scoring |

### Silver-Gold

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Sunday Silver-Gold Cap | Silver through Gold | Not captured | DH; 2,026-point cap; max 13 variants; Atlanta-Fulton County Stadium (1977) |

### Diamond

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Wednesday Ice to See You | Diamond only | 1490029 | DH; Wrigley Field (1977); Diamond scoring |

### Open Tier Cap

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Thursday CWhit's Say My Name Cap | Any tier; value 100 or lower | 1870022 | DH; 1,775-point cap; max 10 variants; automatic scoring environment |

### Mixed Historical Slots

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| Monday Wonky Historical Slots | D 13, S 7, B 6; no Gold or Perfect | Not captured | Card years through 1949; no DH; 2009 simulation; Coors Field (2026) |

## Special Events

### Gold-Perfect

| Tournament | Tier/range | OOTP ID | Key settings |
|---|---|---:|---|
| PTCS Cap - Period 7 | Gold or higher | 1070006 | DH; 2,342-point cap; max 11 variants; 1970 simulation; Dodger Stadium (1971); automatic scoring environment |

## Verification Notes

- The standard PT regular-season plan is intentionally excluded because it is not
  a tournament roster.
- The document now represents 22 unique active tournaments: 2 Quick, 12 Daily,
  7 Weekly, and 1 PTCS special event.
- SQLite currently contains 25 active tournament roster-plan records for those
  22 tournaments. Friday Nightmare Cap appears in three records (`roster_050`,
  `roster_052`, and `roster_053`); this list uses the latest corrected rules from
  `roster_053` and shows the tournament once. Daily Low Gold Cap appears in two
  consecutive records (`roster_049`, ID 1910134, and `roster_055`, ID 1910135);
  this list shows the newer `roster_055` instance.
- Quick Low Gold is active in SQLite but has no roster-report path. Verify that its
  local OOTP roster still exists before relying on it for entry.
- Monday Wonky and Tuesday Dead were completed through the roster automation
  workflow even though Monday Wonky's active plan points to an older report path.
- Tournament rules can change between runs. For older records without an OOTP ID,
  compare the tournament name and key settings before entering. For newer records,
  verify the ID first, then confirm that the displayed restrictions still match.
