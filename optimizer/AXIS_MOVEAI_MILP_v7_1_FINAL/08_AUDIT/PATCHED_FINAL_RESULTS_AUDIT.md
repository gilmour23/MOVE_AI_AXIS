# AXIS MOVE-AI MILP v7.1 patched final results audit

Date: 2026-08-10

## Canonical 72-hour result

| KPI | Value |
|---|---:|
| Service Need TEU | 180 |
| Rail Served TEU | 138 |
| Rail Unserved TEU | 42 |
| Rail Coverage | 0.7667 |
| Selected Train Count | 3 |
| Train-km | 942.4 |
| Wagon-km | 31,099.2 |
| TEU-km | 33,802.4 |
| Average distance-weighted LF | 0.5381 |
| Average carriers per train | 4.0 |
| 20FT boxes | 104 |
| 40FT boxes | 17 |
| Total container boxes | 121 |
| Estimated tariff-based rail charge | KRW 12,242,088.67 |

## Baseline comparison

| Scenario | Served TEU | Unserved TEU | Trains | Train-km | Wagon-km | TEU-km |
|---|---:|---:|---:|---:|---:|---:|
| A No Repositioning | 0 | 180 | 0 | 0.0 | 0.0 | 0.0 |
| B Carrier Separate | 34 | 146 | 1 | 143.7 | 4,742.1 | 4,885.8 |
| C AXIS Integrated | 138 | 42 | 3 | 942.4 | 31,099.2 | 33,802.4 |

## Selected train operation summary

| Train | Route | Actual departure | Actual arrival | Formation | Assigned TEU | LF | Carriers | 20FT | 40FT |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| CAND0156 | UIWANG > BUGANG > YAKMOK > BUSAN | 2026-08-10 06:00 | 2026-08-10 18:00 | F33 | 46 | 0.5019 | 5 | 38 | 4 |
| CAND0292 | BUSAN > YAKMOK | 2026-08-12 00:00 | 2026-08-12 03:00 | F33 | 34 | 0.5152 | 1 | 16 | 9 |
| CAND0702 | UIWANG > BUGANG > DONGSAN > GWANGYANG | 2026-08-11 12:00 | 2026-08-12 00:00 | F33 | 58 | 0.5973 | 6 | 50 | 4 |

## Interpretation limits

- Carrier data is synthetic carrier-level data, not actual carrier submissions.
- Candidate trains are `PROTOTYPE_SYNTHETIC`, not actual KORAIL operating times.
- LF 0.5 and 72-hour earliness are scenario assumptions, not KORAIL standards.
- The rail charge is a tariff-based estimate, not profit, settlement, or revenue.
- Train-km and wagon-km cover selected one-way service movements; return wagon
  movement is not included.
- Exhaustive sensitivity and role-tilt results were not finalized in the fast path.

