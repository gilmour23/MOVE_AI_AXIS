# Phase 5 감사 — 철도 파라미터 정합성

**대상 지시:** v7 수정 지시서 Phase 5 (5-1 거리 / 5-2 Reference Parameter / 5-3 Handling Time)
**판정:** 완료. 거리 검증 9/9 PASS, 모든 파라미터가 xlsx 에서 로드됨.

---

## 1. 변경한 파일

| 파일 | 내용 |
|---|---|
| `02_CODE/axis_params_v7.py` | **신규** — 파라미터 로더 + 거리 runtime validation |
| `02_CODE/axis_milp_v7.py` | 하드코딩 상수 제거, `configure_params()` 로 주입, 상하차 분리 |
| `05_RESULTS/*/RAIL_PARAMETER_PROVENANCE.csv` | 파라미터별 출처 기록 |
| `05_RESULTS/*/DISTANCE_VALIDATION.csv` | 거리 검증 결과 |
| `05_RESULTS/*/DISTANCE_PHYSICAL_VS_TARIFF.csv` | OD별 두 거리 대조표 |

---

## 5-1. 거리 — 모순 제거

### 수정 전 문제

리뷰 문서 #7. `SEGMENT_DISTANCE` 합과 `OD_DISTANCE` 가 8개 OD 에서 5.8 km 어긋났고,
train-km/wagon-km 는 전자를, 운임은 후자를 써서 **서로 다른 거리 기준으로 계산**되고 있었습니다.

### 조사 결과 — 오류가 아니라 서로 다른 물리량

```
의왕→부강 111.8 = 의왕인입 + 경부선(의왕~부강) + 부강인입
부강→약목 152.6 = 부강인입 + 경부선(부강~약목)
의왕→약목 258.6 = 의왕인입 + 경부선(의왕~약목)

⇒ 111.8 + 152.6 − 258.6 = 5.8 = 2 × 부강인입선(2.9 km)
```

**부강 CY 에 정차하는 열차는 인입선을 진입·진출 2회 주행**하지만,
**통과 OD 의 영업거리에는 인입선이 포함되지 않습니다.**

실측으로 확인했습니다. 22개 corridor OD 중 delta 가 5.8 km 인 것은
**정확히 부강을 경유하는 OD 8건뿐**이고 나머지는 전부 0 입니다.

### 수정 내용 — 이름부터 분리

| 이름 | 용도 | 정의 |
|---|---|---|
| `physical_distance_km` | Train-km / Wagon-km / TEU-km / 구간 적재율 / 최소 consolidation | 열차 실제 주행거리, 정차역 인입선 포함 |
| `tariff_distance_km` | 운임 계산 전용 | 코레일 영업거리, 통과역 인입선 미포함 |

### runtime validation (9/9 PASS)

| 검사 | 결과 |
|---|---|
| laden_rate_positive | PASS |
| empty_discount_in_range | PASS — 0.74 |
| min_charge_positive | PASS — 100 km |
| avg_speed_reasonable | PASS — 68.38 km/h |
| handling_times_nonnegative | PASS — (3.0, 3.0, 3.0) |
| all_corridor_od_have_tariff_distance | PASS |
| all_corridor_segments_have_physical_distance | PASS |
| **distance_delta_fully_explained** | **PASS — 모든 delta 가 0 또는 5.8km(부강 경유 시)** |
| tariff_distance_symmetric | PASS |

설명되지 않는 차이가 하나라도 생기면 `configure_params()` 가 예외를 던져 실행이 중단됩니다.

### OD별 대조표

| OD | physical | tariff | delta | 부강경유 |
|---|---|---|---|---|
| UIWANG→BUGANG | 111.8 | 111.8 | 0.0 | — |
| UIWANG→YAKMOK | 264.4 | 258.6 | **+5.8** | O |
| UIWANG→BUSAN | 408.1 | 402.3 | **+5.8** | O |
| BUGANG→YAKMOK | 152.6 | 152.6 | 0.0 | — |
| BUGANG→BUSAN | 296.3 | 296.3 | 0.0 | — |
| YAKMOK→BUSAN | 143.7 | 143.7 | 0.0 | — |
| UIWANG→DONGSAN | 242.0 | 236.2 | **+5.8** | O |
| UIWANG→GWANGYANG | 390.6 | 384.8 | **+5.8** | O |
| BUGANG→DONGSAN | 130.2 | 130.2 | 0.0 | — |
| BUGANG→GWANGYANG | 278.8 | 278.8 | 0.0 | — |
| DONGSAN→GWANGYANG | 148.6 | 148.6 | 0.0 | — |

> **알려진 한계:** 약목·동산 인입선은 원자료(철도거리표) 재구성 과정에서 0 으로 처리되어 있어
> 거점 간 완전한 일관성은 없습니다. 부강만 인입선이 반영되어 있습니다.
> 실제 KORAIL 영업거리표를 확보하면 이 layer 만 교체하면 됩니다.

---

## 5-2. Reference Parameter 연결

### 수정 전 문제

리뷰 문서 #8. `AXIS_rail_OD_parameters_v1.xlsx` 에 출처·URL 이 잘 정리되어 있는데
**코드가 단 한 번도 참조하지 않았고**, 하드코딩 값에 출처 주석도 없었습니다.

### 수정 내용

`axis_params_v7.load_rail_params()` 가 xlsx 의 `REFERENCE_PARAMS` / `OD_PARAMETER` 시트를 읽습니다.
xlsx 를 읽지 못하면 하드코딩 fallback 을 쓰되 **어느 값이 어디서 왔는지 항상 기록**합니다.

실행 결과 — 전부 XLSX 에서 로드됨:

| parameter | value | unit | evidence | loaded_from |
|---|---|---|---|---|
| laden_rate_20ft | 516.0 | KRW/km/container | Official | XLSX |
| laden_rate_40ft | 800.0 | KRW/km/container | Official | XLSX |
| empty_discount_ratio | 0.74 | ratio | Official | XLSX |
| min_charge_distance | 100.0 | km | Official | XLSX |
| benchmark_avg_speed | 68.379603 | km/h | Formula | XLSX |
| container_loading_limit | 3.0 | h | Official | XLSX |
| container_unloading_limit | 3.0 | h | Official | XLSX |
| teu_per_wagon | 2.0 | TEU/wagon | Official-derived | XLSX |
| base_max_wagons | 40.0 | wagons/train | Official-reference | XLSX |
| literature_min_load_factor | 0.70 | ratio | Literature | XLSX |
| tariff_distance_km | 22 OD | km | Official-reconstructed | XLSX |

각 행에 `source_url` 이 함께 기록되어 `RAIL_PARAMETER_PROVENANCE.csv` 로 출력됩니다.

**작업 중 발견한 버그:** xlsx 의 거점명은 서비스명(`의왕`)이 아니라 철도역명(`오봉`)이었습니다.
초기 매핑 실패로 의왕 관련 OD 6건이 로드되지 않아 `KeyError` 가 발생했고, 매핑을 보강했습니다.

---

## 5-3. Handling Time

### 수정 전 문제

리뷰 문서 #9. `dep_slot[origin] = arr_slot[origin] = origin_slot` 이라
**출발역 dwell 이 구조적으로 0**이었고, 실제로 `0시간에 49 TEU 상차` 계획이 산출되었습니다.
중간역도 `INTERMEDIATE_HANDLING_H = 0.5` 가 `ceil` 에 흡수되어 실질 1시간이었습니다.

팀 자체 자료의 공식값은 **적재 3시간 / 하화 3시간** 입니다.

### 수정 내용 — 세 가지로 분리

```python
load_slot[origin] = dep_slot[origin] − ⌈origin_loading_h⌉      # 상차 개시
dep_slot[b]       = arr_slot[b] + ⌈intermediate_handling_h⌉    # 중간역 작업 후 출발
avail_slot[hub]   = arr_slot[hub] + ⌈destination_unloading_h⌉  # 하화 완료 = 사용 가능
```

모델 판정 기준도 함께 바꿨습니다.

| 판정 | v6.1 | v7 |
|---|---|---|
| Source Release Capacity | 열차 **출발** 시각 | **상차 개시** 시각 |
| 기한(due) 충족 | 열차 **도착** 시각 | **하화 완료** 시각 |

실측 예 (`CAND0054`, 의왕→부강→약목→부산신항):

```
UIWANG    상차개시 03시  출발 06시
BUGANG    도착 08시  출발 11시            (3시간 작업)
YAKMOK    도착 13시  출발 16시
BUSAN     도착 18시  사용가능 21시         (3시간 하화)
```

의왕 상차개시 → 부산 사용가능까지 18시간. v6.1 은 같은 열차를 6시간으로 계산했습니다.

### CLI 민감도

```bash
--origin-loading-h 0 --intermediate-handling-h 0 --destination-unloading-h 0
--origin-loading-h 6 --intermediate-handling-h 6 --destination-unloading-h 6
```

0h / 3h / 6h 결과는 Phase 4 감사 §5 에 있습니다.
후보 조합이 1,376 → 1,167 → 941 로 줄고 서비스 물량이 98 → 90 → 90 TEU 가 됩니다.

---

## 6. 부수 효과

후보 열차 수가 612 → 572 로 줄었습니다.
상차 3시간 + 하화 3시간이 추가되면서 계획기간(168h) 안에 완결되지 못하는 후보가 제외되었기 때문입니다.
이는 정상 동작입니다.

---

## 7. 남아있는 한계

1. **약목·동산 인입선이 원자료에 반영되어 있지 않습니다.** 부강만 반영되어 있어
   거점 간 거리 기준이 완전히 일관되지는 않습니다.
2. **평균속도 68.38 km/h 는 의왕~부산신항 1개 구간에서 유도한 proxy** 입니다.
   구간별 실제 표정속도가 아닙니다. xlsx `MODEL_NOTES` 도 `proxy` 로 표시하고 있습니다.
3. `lead_run_only_h` / `lead_plus3h_h` / `lead_plus6h_h` 컬럼은 아직 사용하지 않습니다.
   현재는 `⌈distance / avg_speed⌉` 로 계산합니다.
4. 상하차 3시간은 **약관상 제한시간**이며 실제 터미널 작업시간 통계가 아닙니다.
   물량 규모에 따른 가변 작업시간은 모델링하지 않았습니다.
5. 거점별 시간당 하역능력(예: 오봉에서 1시간에 처리 가능한 TEU) 제약은 없습니다.
