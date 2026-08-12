# 챗봇 데이터 준비 감사

**목적:** read-only 챗봇이 **숫자를 지어내지 않고** 질문에 답할 수 있는지,
그리고 **타 선사 정보가 새지 않는지** 검증한다 (지시서 §12, §13, §23, §28).

**판정:** `[9] Chatbot read-only data readiness` 전 항목 PASS.

---

## 1. 챗봇의 역할 경계

```
허용   이미 계산된 값을 읽고 설명한다
금지   MILP 변수 수정 / constraint 변경 / 재최적화
       새로운 수량·열차 생성 / Carrier allocation 변경
```

v7.1 에서 협상 계층을 제거했으므로 챗봇이 최적화를 바꿀 **경로 자체가 없다.**
자동검증 `E::no_negotiation_in_core`, `E::run_is_one_shot` 으로 고정되어 있다.

---

## 2. v7.1 FINAL 의 gap 3가지

| gap | 문제 |
|---|---|
| **재고 timeline 부재** | README 가 "약목 예상재고는 어떻게 달라져?" 를 예시 질문으로 제시하는데, 최적화 후 시간별 재고 데이터가 **없었다** |
| **의미가 모호한 컬럼** | `destination_expected_shortage_teu` 가 "그 시점 목적지 부족량"처럼 읽히지만 실제로는 연결된 Need 의 단순 합 |
| **선사별 격리 미흡** | recommendation 은 선사별 분리되어 있으나 explanation context 는 통합 파일 하나뿐 |

---

## 3. 추가한 출력

### `CARRIER_INVENTORY_TIMELINE.csv` (12,096행)

```
carrier_id, timestamp, hub_code, container_size,
demand, external_supply,
rail_inbound_boxes, rail_outbound_boxes,
baseline_inventory, post_rail_inventory,
baseline_unmet_demand, post_rail_unmet_demand
```

replay 순서는 `01_DOCS/TIME_SLOT_CONVENTION.md` §2 와 **동일**하다.

```
1) external supply  2) rail inbound  3) demand  4) rail outbound
```

이제 "약목 예상재고는 어떻게 달라져?" 에
`baseline_inventory` vs `post_rail_inventory` 로 정확히 답할 수 있다.

검증

| 항목 | 결과 |
|---|---|
| `chat::inventory_timeline_generated` | PASS — 12,096행 |
| `chat::post_rail_inventory_nonnegative` | PASS — 최소값 ≥ 0 |

### `INVENTORY_IMPACT_SUMMARY.csv` (72행)

```
carrier_id, hub_code, container_size,
baseline_stockout_boxes, post_rail_stockout_boxes, stockout_reduction_boxes,
minimum_baseline_inventory, minimum_post_rail_inventory,
rail_inbound_boxes, rail_outbound_boxes
```

검증: `chat::stockout_not_increased` PASS — 철도 재배치가 재고부족을 늘리지 않음.

### `CARRIER_SERVICE_SUMMARY.csv` (6행)

```
carrier_id, service_need_teu, rail_served_teu, rail_unserved_teu,
rail_coverage, recommendation_count, assigned_train_count,
estimated_tariff_based_rail_charge_krw
```

Joint MILP 는 전체 TEU 를 최적화하므로 capacity 가 부족하면 선사별 coverage 가 달라질 수 있다.
이것은 잘못이 아니지만 **확인 가능해야** 하므로 출력한다.

`SUMMARY.json` 에 fairness 감사도 기록한다.

```json
"carrier_coverage_fairness": {
  "max_carrier_coverage": ..., "min_carrier_coverage": ..., "coverage_stdev": ...
}
```

> **fairness objective 는 Core 에 추가하지 않았다.**
> 원하는 결과를 만들기 위해 목적함수를 임의로 바꾸지 않는다는 원칙에 따른 것이다.
> 편중이 심하면 그때 secondary objective 를 별도 sensitivity 로 검토한다.

---

## 4. Explanation Context 의미 정정

### 삭제한 컬럼

```
destination_expected_shortage_teu     (모호. 중복·과장 가능)
service_due_time  (단일값)             (여러 due 가 묶이면 오해)
```

검증: `chat::ambiguous_shortage_column_removed`, `chat::single_due_column_removed` PASS.

### 추가한 컬럼

**연결된 Need 를 정확히 표현**

```
linked_service_need_teu     이 추천에 연결된 Service Need 합계
linked_need_count           연결된 Need 건수
linked_need_due_min / _max  due 범위
```

실제 post-rail 재고부족은 `CARRIER_INVENTORY_TIMELINE.csv` 에서 별도 조회한다.

**source release 를 3단계로 분리**

```
source_release_capacity_cumulative_boxes            그 시점까지 누적 방출가능량
assigned_outbound_cumulative_boxes_through_load     그 시점까지 이미 배정된 반출량
source_release_remaining_after_assignment_boxes     차감 후 잔여
```

이전에는 누적 capacity 하나만 있어서
"이 추천 직전에 남아 있던 양"으로 잘못 설명될 수 있었다.

**Recommendation due 범위**

```
need_count, service_due_time_earliest, service_due_time_latest
```

검증: `chat::context_has::*` 5항목, `chat::recommendation_due_range_present` PASS.

---

## 5. `RAIL_UNSERVED.reason` 정직화

v7.1 은 모든 미배정에 `NO_FEASIBLE_TRAIN_MEETING_CONSOLIDATION_LEVEL` 을 넣었다.
실제 원인은 time window / source release / segment capacity / conflict /
operational resource / competition 중 무엇이든 될 수 있으므로 **과도한 단정**이었다.

사전검사로 **증명 가능한 범위만** 분류하고 나머지는 단정하지 않는다.

| reason | 의미 |
|---|---|
| `NO_TIME_COMPATIBLE_TRAIN` | 기한·조기도착 창 안에 도착하는 후보가 없음 |
| `NO_SOURCE_RELEASE_CAPACITY` | 시간은 맞지만 그 시점 반출 가능한 자사 재고가 없음 |
| `NO_CANDIDATE_AFTER_CONSOLIDATION_PRUNING` | 최소 consolidation 미달로 후보에서 제외 |
| `UNSERVED_AFTER_JOINT_OPTIMIZATION` | 후보는 있었으나 공동최적화 결과 미배정 |

모든 행에 **`reason_is_proven_cause = false`** 를 붙여
"수학적으로 증명된 유일 원인이 아님"을 명시한다.

검증: `chat::unserved_reason_not_false_specific`, `chat::unserved_reason_flagged_unproven` PASS.

---

## 6. 선사별 데이터 격리

### 생성 파일

```
CARRIER_RECOMMENDATIONS_<CARRIER>.csv
RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv
```

`CARRIER_A` 포털의 챗봇은 자사 파일만 조회한다.

### 검증

| 항목 | 결과 |
|---|---|
| `per_carrier_files_generated` | PASS — 6개 |
| `per_carrier_file_isolation` | PASS — 타 선사 `carrier_id` 없음 |
| `chat::per_carrier_context_generated` | PASS — 6개 |
| `chat::carrier_context_isolation` | PASS — 유출 0건 |

### 노출 가능한 공동운송 정보

```
participating_carrier_count   해당 열차에 몇 개 선사가 함께 실었는지
train_load_factor             해당 열차의 거리가중 적재율
```

### 노출 금지

```
타 선사 raw demand / supply / inventory
타 선사 individual allocation
CARRIER_ALLOCATION.csv 전체 (KORAIL 전용)
```

---

## 7. 질문 → 근거 데이터 매핑

`01_DOCS/CHATBOT_READ_ONLY_DATA_GUIDE.md` 에 전체 표가 있다. 요약:

| 질문 | 근거 |
|---|---|
| 왜 약목으로 보내? | `linked_service_need_teu`, `linked_need_count` |
| 왜 부산신항에서 출발해? | `origin_hub`, `source_release_capacity_cumulative_boxes` |
| 왜 8개야? | `recommended_boxes`, `source_release_remaining_after_assignment_boxes` |
| 언제 출발/도착? | `departure_time`, `arrival_time`, `available_time` |
| 기한은? | `service_due_time_earliest/latest`, `need_count` |
| 적재율은? | `train_load_factor` |
| 몇 개 선사가 함께? | `participating_carrier_count` |
| 운임은? | `estimated_rail_charge_krw`, `tariff_distance_km` |
| **약목 예상재고는?** | `CARRIER_INVENTORY_TIMELINE.csv` baseline vs post_rail |
| 재고부족 줄어? | `INVENTORY_IMPACT_SUMMARY.csv` |
| 우리 물량 다 실렸어? | `CARRIER_SERVICE_SUMMARY.csv` |
| 왜 안 실렸어? | `RAIL_UNSERVED.reason` (+ 증명 아님 명시) |

---

## 8. 챗봇이 말하면 안 되는 표현

| 금지 | 이유 |
|---|---|
| "KORAIL 실제 운행시각" | `candidate_timetable_source = PROTOTYPE_SYNTHETIC` 인 경우 |
| "손익분기 적재율" | Minimum Consolidation Level 은 scenario 값 |
| "수익" / "이익" | `revenue_definition = TARIFF_BASED_ESTIMATE_NOT_PROFIT` |
| "이 조건으로 다시 최적화했습니다" | 재최적화 기능 없음 |
| 타 선사 물량 언급 | 집계값 외 금지 |

정책 변경 요청에는 재최적화하지 않고
"계획 제출 단계에서 재고정책으로 입력해야 한다"고 안내한다
(`01_DOCS/INVENTORY_POLICY_SCHEMA.md`).

---

## 9. 정책 입력은 협상이 아니다

```
Carrier Planning Input → Service Need → Joint Optimization
```

서로 모순되는 정책은 MILP 실행 전에 차단된다.

```
MIN_INVENTORY 30 + MAX_INVENTORY 5 → PolicyValidationError(POLICY_CONFLICT)
```

검증: `policy::min_above_max_rejected` PASS.

---

## 10. 남아있는 한계

1. **자연어 → 질의 변환기(intent parser)는 이 패키지 범위 밖이다.**
   본 패키지는 설명에 필요한 read-only 데이터와 의미 정의까지 제공한다.
2. 선사별 격리는 **파일 수준**이다. 실제 포털에서는 API layer 의
   authentication 기반 filter 를 함께 강제해야 한다.
3. `CARRIER_INVENTORY_TIMELINE.csv` 는 전 선사 통합 파일이다.
   포털 제공 시 자사 행만 필터링해야 한다 (검증은 recommendation/context 파일만 강제).
4. `UNSERVED_AFTER_JOINT_OPTIMIZATION` 은 "경쟁에서 밀렸다" 이상으로
   설명하면 안 된다. 정확한 원인은 dual/IIS 분석이 필요하며 구현하지 않았다.
