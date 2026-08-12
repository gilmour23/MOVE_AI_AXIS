# V7.1 구현 감사

**대상:** `AXIS_MOVEAI_MILP_v7_1_FINAL`
**성격:** 모델 범위 정리. 최적화 로직 자체는 v7 에서 변경하지 않았다.

---

## 1. 현재 서비스 구조

```text
각 선사 자체 데이터 제출 (Inventory / Demand / Supply)
        ↓
복수 선사 데이터 동시 입력  +  KORAIL 운행가능 열차 후보
        ↓
Joint Multi-Carrier MILP  (one-shot)
        ↓
Carrier Recommendation  +  KORAIL Integrated Train Operation Plan
        ↓
Read-only Chatbot Explanation
```

---

## 2. 제거한 기능

| 범주 | 항목 |
|---|---|
| 실행 상태기계 | `PROPOSAL` → `NEGOTIATION` → `FINAL`, `--run-mode`, `--proposal-reference`, `--actions` |
| 협상 action | `ACCEPT_SERVICE`, `ACCEPT_EXACT_PLAN`, `DECLINE_RAIL_SERVICE`, `MODIFY_SERVICE`, `REJECT_OPTION`, `CHANGE_QUANTITY`, `CHANGE_LATEST_ARRIVAL`, `SET_EARLIEST_ARRIVAL`, `SET_MAX_EARLINESS`, `BLOCK_ORIGIN`, `ALLOW_ORIGIN` |
| 협상 상태 | `proposal_version`, `negotiation_round`, `parent_proposal_id`, commitment, counterproposal, stale proposal 검증, accepted/declined 상태 |
| 코드 | `load_negotiation()`, `_proposal_allocations()`, `_action_constraints()`, `create_accept_all_actions()`, `diagnose_commitment_conflict()`, 챗봇 `additional_needs` |
| 산출물 | `NEGOTIATION_MIXED`, `FINAL_MIXED`, `FINAL_ACCEPT_ALL`, `CHATBOT_MIXED_NEGOTIATION.json`, `CHATBOT_ACCEPT_ALL_SERVICE.json`, `commitment_confirmation_rate` |

전부 `future_extensions/negotiation_legacy/` 로 이동했고 **main flow·문서·검증·데모에서 사용하지 않는다.**

자동검증 항목으로 고정했다.

```
E::no_negotiation_in_core         코어에 협상 식별자 없음
E::run_is_one_shot                run() 에 run_mode / actions_path 없음
removed::load_negotiation / create_accept_all_actions / diagnose_commitment_conflict
build_milp_has_no_proposal_reference
```

---

## 3. 유지한 기능 (지시서 §17 롤백 금지)

### 데이터 (전부 자동검증 18항목)
demand/supply structural asymmetry · aggregate demand/supply/initial inventory 총량보존 ·
6개 거점 고유 prior · calibration metadata · 시간 연속성 AR(1) · 이월 배분기

### 모델
carrier-specific service need · carrier ownership · source release capacity ·
integer container assignment · candidate train selection · formation selection ·
segment capacity · minimum consolidation scenario · route/time/due-time compatibility ·
intermediate pickup/drop-off · physical/tariff 거리 분리 · handling-time modeling ·
물리적 중복열차 conflict · optional path slot / wagon / locomotive capacity

### Solver
deterministic tie-break (Z7) · stage별 status/gap/objective/runtime 감사 ·
Z1·Z2 `mip_rel_gap=0` · time-limit 을 optimal 로 취급하지 않음

### 비교·민감도
No Repositioning · Carrier Separate · AXIS Integrated ·
earliness / load factor / handling time 민감도

**검증:** `AXIS_INTEGRATED` 결과가 v7 의 `C_AXIS_INTEGRATED` 와 **정확히 일치**한다.
(138 TEU / 3편 / 편당 4.0 선사 / LF 0.5381 / TEU-km 33,802.4 / 수입 12,242,089원)
구조 정리가 최적화 결과를 바꾸지 않았음을 확인했다.

---

## 4. 용어 변경

| v7 | v7.1 | 이유 |
|---|---|---|
| Carrier Proposal | **Carrier Recommendation** | "제안 후 수락 대기" 협상 함의 제거 |
| `CARRIER_PROPOSALS.csv` | `CARRIER_RECOMMENDATIONS.csv` | |
| `proposal_id` | `recommendation_id` | |
| `quantity` / `teu` | `quantity_boxes` / `quantity_teu` | 단위 모호성 제거 |
| `origin` / `destination` | `origin_hub` / `destination_hub` | |

한국어 UI: **AXIS 권장 공컨 철도운송안 / AXIS 권장 공컨 재배치 계획**

---

## 5. 신규 산출물

### 5-1. 동일 solution 의 두 관점 일치 (지시서 §23 완료조건)

```json
"carrier_recommendation_teu": 138,
"korail_allocation_teu": 138,
"rail_served_teu": 138,
"carrier_korail_view_consistent": true
```

매 실행마다 계산·기록되며 회귀 테스트와 검증 양쪽에서 확인한다.

### 5-2. `CARRIER_ALLOCATION.csv`

KORAIL 관점의 열차별 선사 배분.
`train_id, carrier_id, origin, destination, container_size, boxes, teu`

### 5-3. `RECOMMENDATION_EXPLANATION_CONTEXT.csv`

챗봇 read-only 설명 근거. **계산된 값만** 들어간다.

```text
recommendation_id, carrier_id, destination_hub, container_size,
destination_expected_shortage_teu, origin_hub,
origin_available_release_boxes / _teu,
recommended_boxes / _teu, train_id, train_load_factor,
participating_carrier_count, due_time, arrival_time, available_time,
earliness_hours, physical_distance_km, tariff_distance_km,
estimated_rail_charge_krw
```

LLM 이 새로운 최적화 판단이나 숫자를 만들 필요가 없도록 설계했다.

### 5-4. 선사별 격리 파일

`CARRIER_RECOMMENDATIONS_<CARRIER>.csv` 는 해당 선사 행만 포함한다.
타 선사의 inventory / demand / supply / individual allocation 은 노출하지 않는다.
공동운송 여부는 `participating_carrier_count`, `train_load_factor` 집계정보로만 제공한다.

회귀 테스트 `per_carrier_file_isolation` 이 타 선사 유출을 검사한다.

### 5-5. `candidate_source`

`TRAIN_CANDIDATE.csv` 와 `KORAIL_TRAIN_PLAN.csv` 에 추가했다.

```text
PROTOTYPE_SYNTHETIC     현재 (KORAIL 실제 운행가능시간 아님; pre-patch record)
KORAIL_FEASIBLE_PATH    향후 실제 path 교체 시
```

`SUMMARY.json` 에도 `candidate_timetable_source`, `carrier_data_source` 를 기록한다.

---

## 6. 실행 결함 수정 (지시서 §18)

| 항목 | 수정 |
|---|---|
| 18.1 default 통일 | `max_earliness=72`, `min_load_factor=0.5`, `time_limit=900` 을 CLI 기본값·모든 `.bat`·문서에 통일. **scenario assumption 임을 각 파일에 명시** |
| 18.2 `.bat` 제어문자 | v7 `run_baselines.bat` 의 BEL(`0x07`) 제거. 모든 `.bat` 재생성 + 제어문자 전수검사를 검증 항목화 |
| 18.3 테스트 자립 | `test_v7_1.py` 가 파라미터를 명시 초기화하고 임시 폴더에 모든 입력을 새로 생성. 과거 결과 의존 없음 |
| 18.4 검증이 코드 실행 | `verify_v7_1.py` 가 데이터 생성기·Joint MILP·회귀 스위트를 **실제로 다시 실행** |

---

## 7. 실행 결과 (정본 default)

`min_load_factor=0.5`, `max_earliness=72h`, handling 3h, Service Need **180 TEU / 147건**

### AXIS_INTEGRATED

| 항목 | 값 |
|---|---|
| Rail Served TEU | 138 (커버리지 76.7%) |
| Rail Unserved TEU | 42 |
| 신규열차 | 3 |
| Recommendation 건수 | 24 |
| 편당 참여선사 | 4.0 |
| 평균 distance-weighted LF | 0.5381 |
| TEU-km | 33,802.4 |
| 예상 철도운임 수입 | 12,242,089원 |
| 두 관점 일치 | **true** |
| 전 stage 최적성 증명 | **true** |

---

## 8. Synthetic / Prototype 가정

| 항목 | 현재 | 표기 |
|---|---|---|
| 선사별 데이터 | **Synthetic Carrier-Level Data** | `SUMMARY.json:carrier_data_source` |
| 후보 시간표 | **PROTOTYPE_SYNTHETIC** | `candidate_source` 컬럼 |
| Virtual Carrier | 익명 A~F. 공개자료 점유율 *shape* 만 차용 | 코드 docstring·metadata |
| 공개자료 | PNC / KITL 2026-08-09 단일 snapshot | `source_type` / `source_note` |
| λ, role_tilt | scenario parameter | `DATA_GENERATION_AUDIT.csv` |
| Minimum Consolidation Level | scenario, **손익분기 아님** | 문서 전반 |
| 화차 회송 | 미포함 (편도 계획모형) | `return_wagon_movement_included=false` |
| KORAIL 자원제약 | 데이터 없음 | `NOT_APPLIED_NO_DATA` |

**실제 개별 선사의 전국 공컨 수급 데이터라고 표현하지 않는다.**

---

## 9. 실데이터 교체 지점

| 현재 | 교체 대상 | 방법 |
|---|---|---|
| `AXIS_carrier_hourly_plan_v7_1.csv` | 선사 제출 CSV | `--hourly` (동일 schema) |
| `carrier_initial_inventory.csv` | 선사 제출 재고 | `--initial` |
| `TRAIN_CANDIDATE.csv` (`PROTOTYPE_SYNTHETIC`) | KORAIL feasible path (`KORAIL_FEASIBLE_PATH`) | `--candidates <dir>` |
| 미제공 | path slot / 화차 / 기관차 가용량 | `--operations <json>` |

**MILP core 는 코드 수정 없이 동일하게 작동한다.**
`--candidates` 는 실제 서비스 전환의 핵심 교체 지점이며, 데이터 생성 단계(1번)는 사라진다.

---

## 10. 남아있는 한계

1. **환적 불가.** 도착 공컨을 다른 거점으로 재발송하는 2단 이동을 모델링하지 않는다.
2. **도착 공컨이 source capacity 에 가산되지 않는다.** 보수적 방향이다.
3. **편도 계획모형.** 화차 회송 미포함.
4. **실제 수익성을 주장하지 않는다.** 내부 운영원가 데이터가 없다.
5. 후보 시간표가 prototype 이므로 현재 열차 시각·소요시간은 KORAIL 실제 운행가능시간이 아니다.
6. conflict 제약은 "시간당 1편" 단순화다. 실제 선로용량은 폐색·신호·기존 다이어에 좌우된다.
7. 챗봇 자연어 → 질의 변환기(intent parser)는 이 패키지 범위 밖이다.
   본 패키지는 **설명에 필요한 read-only 데이터까지** 제공한다.
8. 민감도는 단일 주간(2026-08-10~16) 기준이다.
