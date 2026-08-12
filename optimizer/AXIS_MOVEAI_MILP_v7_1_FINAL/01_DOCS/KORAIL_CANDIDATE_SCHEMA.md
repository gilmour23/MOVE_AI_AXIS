# AXIS v7.1 — KORAIL Candidate Schema

MILP 는 **임의의 열차 시각을 만들지 않는다.**
KORAIL 이 제공하는 운행가능 후보 중에서 선택할 뿐이다.

```text
--candidates <DIR>   외부 KORAIL feasible path 사용
(생략)               PROTOTYPE_SYNTHETIC 후보 생성/재사용
```

> **외부 `--candidates` 가 주어지면 AXIS 는 그 파일을 절대 덮어쓰지 않는다.**
> 잘못된 후보는 자동보정이나 synthetic 재생성으로 숨기지 않고 검증 오류로 반환한다.
> 자동검증 `ext::external_candidate_not_overwritten`, `ext::synthetic_generator_not_called` 로 고정되어 있다.

실행 중 생성물(`SERVICE_NEED.csv` 등)은 후보 디렉터리가 아니라
`<root>/_RUN_MODEL_INPUTS/` 에 기록되어 외부 디렉터리를 오염시키지 않는다.

---

## 1. 파일 4종

### `TRAIN_CANDIDATE.csv`

| 컬럼 | 필수 | 설명 |
|---|---|---|
| `train_id` | O | 고유 |
| `service_family` | O | `GYEONGBU` / `SOUTHWEST` / `TRUNK` |
| `origin_terminal` | O | `path` 의 첫 hub 와 일치 |
| `destination_terminal` | O | `path` 의 마지막 hub 와 일치 |
| `path` | O | AXIS 서비스 거점 순서. 전체 물리 통과역 목록이 아님. `UIWANG\|BUGANG\|DONGSAN\|GWANGYANG` 형식 |
| `origin_departure_time` | O | 실제 출발시각 |
| `destination_arrival_time` | O | 실제 도착시각 |
| `service_distance_km` | O | > 0. **Σ segment_distance_km 와 일치해야 함 (허용오차 0.05km)** |
| `work_stops` | 외부 KORAIL 필수 | 상하차 가능역을 `\|` 로 나열. prototype에만 미기재 시 전 정차역으로 하위호환 |
| `stop_pattern` | 선택 | `S`(WORK_STOP)/`P`(PASS_THROUGH) 문자열 (예: `SPPS`) |
| `candidate_source` | O | `PROTOTYPE_SYNTHETIC` / `KORAIL_FEASIBLE_PATH` |
| `timetable_basis` | 선택 | 출처 메모 |

### `TRAIN_STOP_TIME.csv`

| 컬럼 | 필수 | 설명 |
|---|---|---|
| `train_id`, `stop_sequence`, `hub_code` | O | `stop_sequence` 는 1..n 연속, hub 순서는 `path` 와 동일 |
| `load_start_slot` | O | 상차 개시 (재고 필요 시각) |
| `arrival_slot` | O | 도착 |
| `departure_slot` | O | 출발 |
| `available_slot` | O | 하화 완료 = 사용 가능 (**기한 판정 기준**) |
| `stop_type` | 선택 | `WORK_STOP` / `PASS_THROUGH`. 통과역에서는 싣거나 내릴 수 없다 |
| `actual_*_time` | 외부 KORAIL 필수 | 분 단위 원본 시각 (normalization 시 보존) |
| `slot_mapping_rule` | 선택 | 변환 규칙 기록 |

시간 정합성

```
load_start_slot ≤ departure_slot
arrival_slot    ≤ departure_slot      (중간역)
available_slot  ≥ arrival_slot
arrival_slot    ≥ 직전역 departure_slot
모든 slot 이 계획기간 0..167 안
```

### `TRAIN_SEGMENT.csv`

| 컬럼 | 필수 | 설명 |
|---|---|---|
| `train_id`, `segment_sequence` | O | 1..n 연속 |
| `from_hub`, `to_hub` | O | **`path` 의 연속 hub 쌍과 정확히 일치** |
| `segment_distance_km` | O | > 0. **이 값이 물리거리 정본이다** |

### `TRAIN_FORMATION_OPTION.csv`

| 컬럼 | 필수 | 설명 |
|---|---|---|
| `train_id`, `formation_id` | O | `(train_id, formation_id)` 중복 금지 |
| `wagon_count` | O | > 0. **이 값이 정본** |
| `capacity_teu` | O | > 0. **이 값이 정본** |
| `basis` | 선택 | 출처 메모 |

train 당 최소 1개 formation 이 있어야 한다.

> **ID 가 아니라 값이 정본이다.**
> `formation_id` 가 `F33` 이든 `KF44` 든 상관없이
> MILP 는 CSV 의 `wagon_count` / `capacity_teu` 를 사용한다.
> (v7.1 이전에는 global `FORMATION` dict 을 참조해 외부 값이 무시되었다.)

---

### 정차패턴

출발역과 도착역은 반드시 `work_stops` 에 포함되어야 한다.
통과역은 물리적으로 경로에 있지만 상하차가 불가능하며 정차시간도 0 이다.
실제 KORAIL path 를 넣을 때 무정차 통과역이 있으면 `work_stops` 에서 제외하면 된다.

---

## 2. 물리거리 vs 운임거리

| 종류 | 출처 | 사용처 |
|---|---|---|
| `physical_distance_km` | **`TRAIN_SEGMENT.segment_distance_km`** | Train-km, Wagon-km, TEU-km, 구간 적재율, 최소 consolidation |
| `tariff_distance_km` | OD 영업거리표 (`AXIS_rail_OD_parameters_v1.xlsx`) | 운임 계산 전용 |

외부 KORAIL path 가 prototype network 와 다른 거리를 갖더라도
**CSV 의 실제 거리가 MILP 와 모든 KPI 에 반영된다.**
자동검증 `ext::external_segment_distance_used`, `ext::external_train_km_matches_fixture` 로 고정.

---

## 3. Cross-file validation (`validate_candidate_inputs`)

```
candidate train set == stop train set == segment train set == formation train set
```

실패 시 구조화 오류

```json
{
  "status": "INVALID_INPUT",
  "reason_code": "CANDIDATE_INPUT_INVALID",
  "message": "KORAIL candidate 파일 검증에서 2건의 문제가 발견되었습니다. 외부 후보는 자동 보정하거나 synthetic 으로 대체하지 않습니다.",
  "errors": [
    "KTEST001: service_distance_km 160.5 != Σ segment_distance_km 150.5 (tolerance 0.05km)",
    "KTEST001/KF44: capacity_teu must be > 0"
  ]
}
```

---

## 4. 실제 KORAIL timetable → candidate 변환

분 단위 실제 시각은 `02_CODE/normalize_korail_candidates_v7_1.py` 로 변환한다.

```bash
python 02_CODE/normalize_korail_candidates_v7_1.py \
  --raw <KORAIL 원본 디렉터리> \
  --out 03_INPUT_DATA/KORAIL_CANDIDATES \
  --horizon-start "2026-08-10 00:00" --horizon-hours 168
```

원본 입력

```text
KORAIL_PATHS.csv          train_id, service_family, path, work_stops, candidate_source,
                          formation_id, wagon_count, capacity_teu
KORAIL_PATH_STOPS.csv     train_id, stop_sequence, hub_code,
                          actual_load_start_time, actual_arrival_time,
                          actual_departure_time, actual_available_time
KORAIL_PATH_SEGMENTS.csv  train_id, segment_sequence, from_hub, to_hub,
                          segment_distance_km
```

변환 규칙(보수적)과 근거는 `01_DOCS/TIME_SLOT_CONVENTION.md` §4.
원본 시각은 `actual_*` 컬럼으로 항상 보존된다.

---

## 5. 교체 예시

```bash
python 02_CODE/axis_milp_v7_1.py \
  --hourly 03_INPUT_DATA/AXIS_carrier_hourly_plan_v7_1.csv \
  --initial 03_INPUT_DATA/carrier_initial_inventory.csv \
  --params 03_INPUT_DATA/AXIS_rail_OD_parameters_v1.xlsx \
  --candidates 03_INPUT_DATA/KORAIL_CANDIDATES \
  --root 05_RESULTS --scenario AXIS_INTEGRATED \
  --min-load-factor 0.5 --max-earliness 72 --time-limit 900 --strict-lexicographic
```

`SUMMARY.json` 의 `candidate_timetable_source` 가 자동으로
`KORAIL_FEASIBLE_PATH` 로 기록된다 (하드코딩하지 않음, 혼합 시 `MIXED`).

**MILP core 는 수정하지 않는다.**

---

## 6. 테스트 fixture

```text
03_INPUT_DATA/TEST_KORAIL_CANDIDATES/       변환 완료된 외부 후보
03_INPUT_DATA/TEST_KORAIL_CANDIDATES_RAW/   분 단위 원본
```

의도적으로 prototype 과 다르게 만들어 두었다.

| 항목 | prototype | fixture |
|---|---|---|
| train_id | `CAND####` | `KTEST001` / `KTEST002` |
| 첫 출발 | 00:00 계열 | **06:35** (정각 아님) |
| candidate_source | `PROTOTYPE_SYNTHETIC` | `KORAIL_FEASIBLE_PATH` |

`SUMMARY.json` records the full pool in `candidate_input_sources`, the sources of
selected trains in `selected_train_sources`, and keeps `candidate_timetable_source`
as the selected-source compatibility label.

User-facing output columns contain the preserved actual minute timetable. Audit
columns prefixed with `model_` contain conservative integer slots/timestamps used
for MILP feasibility. They must never be presented under the same name.
| 부산→약목 거리 | 143.7 | **150.5** |
| 의왕→부강 거리 | 111.8 | **120.4** |
| 편성 | F33 = 66TEU / 33량 | **KF44 = 88TEU / 44량** |

이 fixture 로 §29 완료조건의 "실제 KORAIL path 교체 가능"을 자동검증한다.
