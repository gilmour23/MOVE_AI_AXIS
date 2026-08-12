# AXIS v7.1 — Chatbot Read-only Data Guide

챗봇은 **최적화 controller 가 아니다.**
이미 산출된 MILP solution 을 읽고 설명하는 **Read-only Explanation / Q&A Layer** 다.

---

## 1. 절대 하면 안 되는 것

```text
MILP 변수 수정          constraint 변경          재최적화
새로운 수량 생성        새로운 train 생성        Carrier allocation 변경
```

**LLM 이 숫자를 임의로 생성하면 안 된다.**
모든 답변은 아래 CSV 에 이미 계산되어 있는 값만 근거로 한다.

---

## 2. 선사 포털에서 조회 가능한 데이터

`CARRIER_A` 로 로그인한 사용자의 챗봇은 다음만 볼 수 있다.

| 파일 | 내용 |
|---|---|
| `CARRIER_RECOMMENDATIONS_CARRIER_A.csv` | 자사 권장 운송계획 |
| `RECOMMENDATION_EXPLANATION_CONTEXT_CARRIER_A.csv` | 자사 추천의 근거 데이터 |
| `CARRIER_INVENTORY_TIMELINE.csv` (자사 행만) | 시간별 재고 변화 |
| `INVENTORY_IMPACT_SUMMARY.csv` (자사 행만) | 재고 개선 효과 |
| `CARRIER_SERVICE_SUMMARY.csv` (자사 행만) | 자사 커버리지 |
| `SERVICE_NEED_RESULT.csv` (자사 행만) | 자사 Service Need 충족 결과 |

**공동운송 사실은 집계정보로만 제공한다.**

```text
participating_carrier_count   해당 열차에 몇 개 선사가 함께 실었는지
train_load_factor             해당 열차의 거리가중 적재율
```

---

## 3. 조회하면 안 되는 것

```text
다른 carrier 의 raw demand / supply / inventory
다른 carrier 의 individual allocation
CARRIER_ALLOCATION.csv 전체 (KORAIL 전용)
```

자동검증 `chat::carrier_context_isolation` 이
선사별 파일에 타 선사 `carrier_id` 가 섞이면 FAIL 시킨다.

---

## 4. 예상 질문 → 근거 데이터 매핑

| 질문 | 근거 파일 | 컬럼 |
|---|---|---|
| 왜 약목으로 공컨을 보내? | `RECOMMENDATION_EXPLANATION_CONTEXT_<C>.csv` | `destination_hub`, `linked_service_need_teu`, `linked_need_count` |
| 왜 부산신항에서 출발해? | 〃 | `origin_hub`, `source_release_capacity_cumulative_boxes` |
| 왜 8개야? | 〃 | `recommended_boxes`, `source_release_remaining_after_assignment_boxes` |
| 언제 출발/도착해? | `CARRIER_RECOMMENDATIONS_<C>.csv` | `departure_time`, `arrival_time`, `available_time` |
| 기한은 언제까지야? | 〃 | `service_due_time_earliest`, `service_due_time_latest`, `need_count` |
| 어떤 열차에 실려? | 〃 | `train_id` |
| 열차 적재율은? | 〃 | `train_load_factor` |
| 몇 개 선사가 공동 운송해? | 〃 | `participating_carrier_count` |
| 운임은 얼마야? | 〃 | `estimated_rail_charge_krw`, `tariff_distance_km` |
| **약목 예상재고는 어떻게 달라져?** | `CARRIER_INVENTORY_TIMELINE.csv` | `baseline_inventory` vs `post_rail_inventory` |
| 재고부족이 줄어? | `INVENTORY_IMPACT_SUMMARY.csv` | `baseline_stockout_boxes`, `post_rail_stockout_boxes`, `stockout_reduction_boxes` |
| 우리 물량 다 실렸어? | `CARRIER_SERVICE_SUMMARY.csv` | `rail_coverage`, `rail_unserved_teu` |
| 왜 이건 안 실렸어? | `RAIL_UNSERVED.csv` | `reason`, `reason_is_proven_cause` |

---

## 5. 숫자 의미 — 잘못 설명하지 않기 위한 주의

### `linked_service_need_teu`
이 추천에 **연결된 Service Need 의 합계**다.
"그 시점 목적지의 예상 부족량"이 **아니다.**
하나의 Need 가 여러 추천으로 나뉘거나 한 추천이 여러 Need 를 묶을 수 있기 때문이다.
실제 재고부족은 `CARRIER_INVENTORY_TIMELINE.csv` 에서 조회한다.

### source release 3종
```
source_release_capacity_cumulative_boxes            그 시점까지 누적 방출가능량
assigned_outbound_cumulative_boxes_through_load     그 시점까지 이미 배정된 반출량
source_release_remaining_after_assignment_boxes     차감 후 잔여
```
"이 추천 직전에 남아 있던 양"을 설명할 때는 **세 번째 값**을 써야 한다.

### `service_due_time_earliest` / `_latest`
한 추천에 여러 due 가 묶일 수 있다. 단일 기한처럼 설명하면 안 된다.
`need_count` 로 몇 건이 묶였는지 함께 말한다.

### `RAIL_UNSERVED.reason`
`reason_is_proven_cause = false` 다.
사전검사로 확인 가능한 범위만 분류했으며 **수학적으로 증명된 유일 원인이 아니다.**

| reason | 의미 |
|---|---|
| `NO_TIME_COMPATIBLE_TRAIN` | 기한·조기도착 창 안에 도착하는 후보열차가 없음 |
| `NO_SOURCE_RELEASE_CAPACITY` | 시간은 맞지만 그 시점 반출 가능한 자사 재고가 없음 |
| `NO_CANDIDATE_AFTER_CONSOLIDATION_PRUNING` | 최소 consolidation 요건을 못 채워 후보에서 제외 |
| `UNSERVED_AFTER_JOINT_OPTIMIZATION` | 후보는 있었으나 공동최적화 결과 배정되지 않음 |

마지막 항목은 "다른 물량과 경쟁에서 밀렸다" 정도로만 설명하고
특정 원인을 단정하지 않는다.

### `estimated_rail_charge_krw`
**공표 운임표 기반 추정액**이며 KORAIL 실제 정산·할인·운영원가를 반영한 수익이 아니다.
**수익성(profit)을 주장하지 않는다.**

---

## 6. 답변 원칙

1. 위 CSV 에 없는 숫자는 말하지 않는다.
2. 계산이 필요하면 이미 계산된 컬럼을 인용한다. LLM 이 재계산하지 않는다.
3. 다른 선사 정보는 집계값 외에는 언급하지 않는다.
4. 후보 시간표가 `PROTOTYPE_SYNTHETIC` 인 경우
   "KORAIL 실제 운행시각"이라고 말하지 않는다.
   (`SUMMARY.json:candidate_timetable_source` 확인)
5. 최소 consolidation 값을 "손익분기 적재율"이라고 말하지 않는다.
6. 사용자가 조건 변경을 요청하면 **재최적화하지 않고**,
   "조건을 바꾸려면 계획 제출 단계에서 재고정책을 입력해야 한다"고 안내한다
   (`01_DOCS/INVENTORY_POLICY_SCHEMA.md`).

---

## 7. 정책 입력은 협상이 아니다

선사의 재고정책(`MIN_INVENTORY_*`, `MAX_INVENTORY`, `ORIGIN_RELEASE_RESTRICTION`)은
**계획 실행 전 입력조건**이다. 결과를 보고 사후에 조정하는 협상 기능이 아니다.

```text
Carrier Planning Input  →  Service Need  →  Joint Optimization
```

서로 모순되는 정책(예: MIN 30 + MAX 5)은 MILP 실행 전에
`POLICY_CONFLICT` 구조화 오류로 반환된다.
