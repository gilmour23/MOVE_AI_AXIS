# PATCH CHANGELOG — v7.1 FINAL → v7.1 PATCHED

**대상:** `AXIS_MOVEAI_MILP_v7_1_FINAL` → `AXIS_MOVEAI_MILP_v7_1_PATCHED`
**성격:** MILP 핵심 구조는 그대로. **"실제 데이터로 교체 가능하다"는 주장을 코드로 성립시키는 작업.**

Joint Multi-Carrier MILP / one-shot 실행 / read-only chatbot 구조는 변경하지 않았다.
Negotiation·Accept·Modify·Commitment 는 다시 넣지 않았다.

---

## 0. 팀 피드백(제미나이 분석) 검토

| 지적 | 판정 | 조치 |
|---|---|---|
| `RAIL_UNSERVED.csv` = 물량 포기 오류/페널티 | **사실 아님.** `u[r]` 결정변수(철도 미배정량)이며 설계된 출력이다 | 다만 `reason` 이 과도하게 단정적이던 것은 수정 (§9) |
| `CHATBOT_NEGOTIATION_SCHEMA_v6_1.md` 기준 파싱 오류 | **사실 아님.** v7.1 에서 legacy 로 이동했고 협상 계층 자체가 없다 | 현 정본은 `INVENTORY_POLICY_SCHEMA.md` |
| `UNPRESERVABLE_EXACT_PLAN.csv` 확정 배차 유지 실패 | **사실 아님.** `future_extensions/negotiation_legacy/` 의 v7 잔재이며 main flow 에 없다 | — |
| 정책 충돌 시 솔버 다운 | **부분 사실.** 다운되지 않고 `MODEL_INFEASIBLE` 을 반환하지만 **사전 감지가 없었다** | 정책 충돌 pre-check 추가 (§10) |
| 데이터 집계 무결성 모니터링 | 사실 | 유지 |
| 상하역/정차 시간 비현실성 | **사실이며 실제 결함이 있었다** | 통과역 정차 딜레이 제거 (§1) |

---

## 1. 통과역 정차 딜레이 제거 (사용자 지적)

### 문제

후보 시간표가 경로상의 **모든 중간역에 3시간 정차**를 부여했다.
상하차가 전혀 없는 역에서도 3시간이 붙었다.

```
CAND0054  의왕>부강>약목>부산신항
  의왕 06시 출발 → 부강 08시 도착 → 11시 출발 (3h 정차)
                 → 약목 13시 도착 → 16시 출발 (3h 정차)
                 → 부산신항 18시 도착
  총 12시간 중 6시간이 정차 대기
```

의왕→부산신항 직통 수요조차 12시간이 걸리는 것으로 계산되어
조기도착 창(72h)을 불필요하게 소모하고 후보 열차를 줄였다.

### 수정 — 정차패턴(Stop Pattern) 변형

같은 물리경로에 대해 **중간역 정차조합 전체**를 후보로 생성한다.

| stop_type | 중간역 소요 | 상하차 |
|---|---|---|
| `WORK_STOP` | 3h | 가능 |
| `PASS_THROUGH` | **0h** | **불가** |

출발역·도착역은 항상 `WORK_STOP`.

MILP 제약

```
x[r,o,p] 는 o 와 dest(r) 이 모두 train p 의 WORK_STOP 일 때만 생성된다.
```

### 효과 (의왕>부강>약목>부산신항, 06:00 출발)

| stop_pattern | 작업역 | 총 소요 | 정차대기 | 도착 |
|---|---|---|---|---|
| `SPPS` | 의왕, 부산신항 | **6h** | **0h** | 12:00 |
| `SSPS` | 의왕, 부강, 부산신항 | 9h | 3h | 15:00 |
| `SPSS` | 의왕, 약목, 부산신항 | 9h | 3h | 15:00 |
| `SSSS` | 전역 (v7.1 의 유일 후보) | 12h | 6h | 18:00 |

급행(직통)과 완행(전역정차)이 후보로 공존하며 MILP 가 선택한다.

후보 수 572 → **1,084**.

### 신규 컬럼

```
TRAIN_CANDIDATE.csv   work_stops, stop_pattern, work_stop_count
TRAIN_STOP_TIME.csv   stop_type (WORK_STOP | PASS_THROUGH)
KORAIL_TRAIN_PLAN.csv work_stops, work_stop_count, transit_hours, dwell_hours
STOP_WORK_PLAN.csv    stop_type
```

`work_stops` 미기재 시 전 정차역을 작업역으로 간주한다 (하위호환).

---

## 2. 외부 KORAIL Candidate 를 절대 덮어쓰지 않음 (지시서 §2)

### 문제

```python
input_dir = candidates_dir or root/"MODEL_INPUTS"
if not _candidate_inputs_match(...):
    generate_candidate_inputs(...)      # 외부 파일을 synthetic 으로 덮어쓸 수 있었다
```

`_candidate_inputs_match()` 가 `min(departure) == horizon_start` 를 요구했는데,
prototype 생성기는 상차 3시간 때문에 그 시각 후보를 만들 수 없어
**정상 후보도 mismatch 로 판정**되었다.

### 수정

```python
if candidates_dir is not None:
    input_dir = Path(candidates_dir)
    validate_candidate_inputs(input_dir, timestamps)   # 실패 시 구조화 오류
    # generate_candidate_inputs() 를 절대 호출하지 않는다
else:
    ...prototype 생성/재사용...
```

`_candidate_inputs_match()` 는 "모든 후보 시각이 계획주간 안인가" 만 검사한다.
첫 열차가 06:00 이어도 정상이다.

### 추가로 발견해 고친 실제 버그

`generate_service_needs()` 가 `SERVICE_NEED.csv`, `BASELINE_AND_SOURCE_CAPACITY.csv` 를
**후보 디렉터리에** 기록하고 있었다. 외부 KORAIL 폴더를 오염시킨다.
실행 생성물을 `<root>/_RUN_MODEL_INPUTS/` 로 분리했다 (지시서 §24.3).

---

## 3. 외부 Candidate 의 실제 거리를 실제로 사용 (지시서 §3)

`TRAIN_SEGMENT.segment_distance_km` 를 읽지 않고 module global `SEGMENT_DISTANCE` 를 쓰고 있었다.

### 수정

`Train.segment_km` 에 CSV 값을 저장하고 `Train.seg_km()` / `path_km()` 으로 접근한다.
아래가 전부 train-specific 거리를 쓴다.

```
Z3 Train-km            Z4 Wagon-km            Minimum Consolidation 거리가중
TEU-km                 SEGMENT_LOAD.physical_distance_km
Recommendation.physical_distance_km          KORAIL_TRAIN_PLAN.train_km
```

운임은 계속 OD tariff distance 를 쓴다 (physical / tariff 분리 유지).

검증: `service_distance_km ≈ Σ segment_distance_km` (허용오차 0.05km).
불일치 시 조용히 한쪽을 고르지 않고 `CANDIDATE_INPUT_INVALID`.

---

## 4. 외부 Formation 을 실제 MILP 파라미터로 사용 (지시서 §4)

`TRAIN_FORMATION_OPTION.csv` 에서 `formation_id` 만 읽고
`wagon_count` / `capacity_teu` 는 global `FORMATION` dict 을 참조하고 있었다.

### 수정

`Train.formation_spec` 에 CSV 값을 저장하고 `Train.wagons()` / `capacity()` 로 접근한다.
**ID 가 아니라 값이 정본이다.** `KF44` 같은 새 ID 도 그대로 동작한다.

적용처: segment capacity, minimum consolidation, wagon availability, wagon-km, 출력.

검증: `wagon_count > 0`, `capacity_teu > 0`, train 당 ≥1개, `(train_id, formation_id)` 중복 금지.

---

## 5. 실제 KORAIL 시각을 위한 Time Adapter (지시서 §5, §6)

MILP 해상도(1시간)는 바꾸지 않고 별도 계층을 만들었다.

```
02_CODE/normalize_korail_candidates_v7_1.py
```

분 단위 실제 시각(06:35 등)을 보수적으로 slot 으로 변환하고
**원본은 `actual_*` 컬럼으로 항상 보존**한다.

```
load_start  → floor   상차 개시를 앞당김 → 재고를 더 일찍 요구 (보수적)
departure   → ceil
arrival     → ceil
available   → ceil    사용가능을 늦춤 → 기한 판정 보수적
```

Hourly Event Order 를 포함한 시각 규약을 문서로 고정했다.

```
01_DOCS/TIME_SLOT_CONVENTION.md
```

---

## 6. 선사 제출 데이터 검증 계층 (지시서 §7, §8)

`validate_carrier_inputs()` 추가. Python `KeyError` 대신 **구조화 오류**를 반환한다.

검사: 필수컬럼 / 중복 / 음수·소수 / 허용 hub·size / 시간 연속성 /
carrier×hub×size×time 완전성 / 초기재고 1행 / carrier 집합 일치.

`--no-input-validation` 으로 끌 수 있으나 권장하지 않는다.

실제 서비스 입력 구조를 문서화하고 템플릿을 추가했다.

```
01_DOCS/CARRIER_INPUT_SCHEMA.md
03_INPUT_DATA/templates/CARRIER_SUBMISSION_TEMPLATE.csv
03_INPUT_DATA/templates/CARRIER_INITIAL_INVENTORY_TEMPLATE.csv
```

---

## 7. Candidate 4파일 cross-validation (지시서 §9)

`validate_candidate_inputs()` 추가.

train_id 유일성 / path 정합 / 거리 양수 / stop 순서·시간 단조성 / slot 범위 /
segment pair 가 path 연속쌍과 일치 / 거리합 일치 / formation 유효성 /
**4파일 train_id 집합 일치** / work_stops 부분집합·출발도착 포함.

---

## 8. SUMMARY candidate source 하드코딩 제거 (지시서 §11)

`"PROTOTYPE_SYNTHETIC"` 고정값을 제거하고 실제 선택된 후보에서 유도한다.
단일이면 그 값, 혼합이면 `MIXED`.

---

## 9. 설명 데이터 정확화 (지시서 §12~§16)

| 항목 | 변경 |
|---|---|
| `CARRIER_INVENTORY_TIMELINE.csv` | **신규.** 시간별 baseline vs post-rail 재고, rail in/out, 미충족 |
| `INVENTORY_IMPACT_SUMMARY.csv` | **신규.** 재고부족 감소량, 최저재고 |
| `CARRIER_SERVICE_SUMMARY.csv` | **신규.** 선사별 need/served/coverage/추천수/열차수/운임 |
| `SUMMARY.carrier_coverage_fairness` | **신규.** max/min/stdev (fairness objective 는 추가하지 않음) |
| `destination_expected_shortage_teu` | **삭제.** `linked_service_need_teu` + `linked_need_count` + due 범위로 대체 |
| `origin_available_release_boxes` | **분리.** capacity_cumulative / assigned_through_load / remaining_after_assignment |
| `service_due_time` (단일) | **삭제.** `need_count` + `service_due_time_earliest/latest` |
| `RAIL_UNSERVED.reason` | 사전검사로 증명 가능한 4분류 + `reason_is_proven_cause=false` |
| 선사별 explanation context | **신규.** `RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv` |

`reason` 분류

```
NO_TIME_COMPATIBLE_TRAIN          기한·조기도착 창 안에 도착 후보 없음
NO_SOURCE_RELEASE_CAPACITY        시간은 맞지만 반출 가능 자사 재고 없음
NO_CANDIDATE_AFTER_CONSOLIDATION_PRUNING   최소 consolidation 미달로 후보 제외
UNSERVED_AFTER_JOINT_OPTIMIZATION 후보는 있었으나 공동최적화에서 미배정
```

수학적으로 증명할 수 없는 원인은 억지로 세분화하지 않았다.

---

## 10. 정책 충돌 사전 감지 (팀 피드백)

MILP 실행 전에 논리적 모순을 감지한다.

```
MIN_INVENTORY 30 + MAX_INVENTORY 5 (동일 carrier/hub/size/time)
→ PolicyValidationError(POLICY_CONFLICT)
```

반출 완전차단(`ORIGIN_RELEASE_RESTRICTION value=0`) + 같은 기간 최소재고 요구는
경고로 기록한다(다른 거점에서 공급 가능하므로 hard error 는 아님).

---

## 11. Solver 정확성 (지시서 §18)

| 항목 | 변경 |
|---|---|
| `--strict-lexicographic` | **신규.** 전 stage `mip_rel_gap = 0` |
| Z7 tie-break | **항상 gap 0** (정규해가 유일하게 고정되어야 하므로) |
| `SUMMARY.solver_exactness` | `EXACT_ALL_STAGES` / `APPROXIMATE_WITHIN_GAP_Z3_TO_Z6` |
| 정본 실행 | strict mode 사용 |

---

## 12. 자원 점유시간 보정 (지시서 §19)

화차·기관차 점유구간을 `출발~도착` 에서
**`출발역 상차개시 ~ 도착역 하화완료`** 로 바꿨다.

---

## 13. Conflict 제약 명칭 정확화 (지시서 §20)

`DEPARTURE_SLOT_CONFLICT` / `SHARED_TRUNK_CONFLICT` 를
`DUPLICATE_CANDIDATE_GUARD_*` 로 rename 하고
`scope: PROTOTYPE_DUPLICATE_CANDIDATE_GUARD`,
`"NOT a full track-occupancy / headway model"` 을 명시했다.

**exact-hour rule 을 "실제 선로 충돌 방지"라고 과장하지 않는다.**

---

## 14. Synthetic role_tilt 민감도 (지시서 §17)

```
02_CODE/axis_role_tilt_sensitivity_v7_1.py
05_RESULTS/SENSITIVITY/ROLE_TILT_SENSITIVITY.csv
```

tilt 0.55 / 1.10 / 1.65 로 **데이터를 다시 생성한 뒤 베이스라인까지 재실행**해
AXIS 통합효과가 이 scenario parameter 에 얼마나 의존하는지 측정한다.

---

## 15. 패키지 정리 (지시서 §21, §22, §24)

| 항목 | 변경 |
|---|---|
| legacy policy-example folder | → **`06_POLICY_EXAMPLES`** (실제 내용은 사전 재고정책 예시) |
| legacy 문서 | `01_DOCS` → **`08_AUDIT/legacy_docs/`** (v6.1/v7 문서 6종) |
| MODEL_INPUTS 중복 | 정본 `04_MODEL_INPUTS`, 실행 생성물 `05_RESULTS/_RUN_MODEL_INPUTS` |
| sensitivity Python 기본값 | `base-earliness 72`, `time-limit 900` 으로 정본과 통일 |
| `expected_korail_revenue_krw` | `estimated_tariff_based_rail_revenue_krw` 추가, `revenue_definition: TARFF_BASED_ESTIMATE_NOT_PROFIT` 명시 (기존 컬럼은 alias 유지) |
| `BLOCK_OUTBOUND` | `ORIGIN_RELEASE_RESTRICTION` 정본화 (기존 이름은 별칭) |

---

## 16. 신규 문서

```
01_DOCS/CARRIER_INPUT_SCHEMA.md
01_DOCS/KORAIL_CANDIDATE_SCHEMA.md
01_DOCS/TIME_SLOT_CONVENTION.md
01_DOCS/CHATBOT_READ_ONLY_DATA_GUIDE.md
```

---

## 17. 검증 확장

| 스위트 | v7.1 FINAL | v7.1 PATCHED |
|---|---|---|
| 회귀 테스트 | 56 | **98** |
| 전체 검증 | 76 | 확장 (F 단계 추가) |

신규 테스트 그룹

```
[6] External KORAIL candidate replaceability   외부 후보 미변경·거리·편성·source
[7] Carrier input validation                   중복/누락시간/음수/소수/hub오타/carrier불일치
[8] KORAIL candidate cross-file validation     파일누락/거리합/편성/시간역전
[9] Chatbot read-only data readiness           timeline/impact/context 의미·격리
[10] Policy conflict pre-check                 MIN>MAX 충돌
```

---

## 18. 변경하지 않은 것

```
Joint Multi-Carrier MILP 구조        one-shot 실행
carrier ownership 분리               source release capacity
deterministic tie-break              physical/tariff 거리 분리
Carrier Separate / No Repositioning baseline
earliness / load factor / handling time 민감도
read-only chatbot 방향
```

Negotiation / Accept / Decline / Modify / Commitment / Proposal versioning /
사후 재최적화는 **다시 넣지 않았다.**
