# AXIS MILP v6.1 — Carrier Proposal → Chatbot Negotiation → Final KORAIL Operation

## 1. 서비스 정의

AXIS는 **선사를 고객으로 하는 KORAIL 공컨 철도운송 제안·운영 플랫폼**이다.

1. 모든 선사의 `현재재고 × 향후수요 × 향후외생공급`을 동시에 분석한다.
2. KORAIL AXIS MILP가 각 선사에 공컨 철도운송 **잠정 Proposal**을 제시한다.
3. 선사는 챗봇으로 수락·수정·대안요청·철도서비스 거절을 한다.
4. 챗봇은 자연어를 구조화된 서비스조건으로 변환한다.
5. AXIS가 **전체 선사를 다시 공동최적화**한다.
6. FINAL mode에서는 확정된 Carrier Commitment만 모아 KORAIL의 최종 열차·편성·상하차·구간적재 계획을 산출한다.

> 공컨 소유권은 선사별로 독립 유지한다. 공유되는 것은 KORAIL 열차 capacity이다.

---

## 2. v6.1 핵심 수정

### 2.1 협의조건을 Candidate Train 생성 전에 적용

v6의 핵심 버그는 `CHANGE_LATEST_ARRIVAL`로 기한을 늦춰도 최초 due-time으로 이미 열차후보가 제거되어 탐색공간이 늘지 않는 것이었다.

v6.1 처리 순서:

```text
Chatbot Action
→ Effective quantity / latest arrival / earliest arrival / blocked origin 갱신
→ Candidate Assignment 재생성
→ MILP
```

따라서 **기한 앞당김과 기한 완화가 모두 실제 feasible train set에 반영**된다.

### 2.2 MODIFY_SERVICE

한 메시지에서 여러 조건을 동시에 수정할 수 있다.

```json
{
  "proposal_id": "PROP0010",
  "action": "MODIFY_SERVICE",
  "constraints": {
    "quantity": 12,
    "latest_arrival": "2026-08-14 18:00",
    "earliest_arrival": "2026-08-13 00:00",
    "max_earliness_hours": 48,
    "blocked_origins": ["BUSAN"]
  },
  "commit": false
}
```

LLM은 위 JSON까지만 생성한다. 열차·출발거점·편성은 MILP가 다시 결정한다.

### 2.3 Proposal Versioning

각 Proposal 출력:

- `proposal_uuid`
- `negotiation_round`
- `proposal_version`
- `parent_proposal_id`

챗봇 Action이 `proposal_uuid` 또는 `proposal_version`을 함께 보내면 v6.1이 stale proposal 여부를 검증한다.

### 2.4 Optional KORAIL Operational Constraints

실제 데이터가 있을 때만 활성화한다.

- 추가 Train Path Slot
- 사용 가능한 화차 수
- 사용 가능한 기관차 수

값을 모르면 임의로 생성하지 않고 비활성화한다.

---

# 3. 기본 집합

- `c ∈ C`: 선사
- `i,j ∈ N`: 6개 거점
- `k ∈ K`: 20FT, 40FT
- `t ∈ T`: 시간
- `r ∈ R`: 선사별 Service Need
- `p ∈ P`: Candidate Train Trip
- `m ∈ M_p`: 편성 옵션
- `e ∈ E_p`: Train p의 physical rail segment

---

# 4. Service Need

재배치가 없는 경우 선사별 시간흐름에서 발생하는 stockout 또는 선사가 직접 설정한 재고정책을 기반으로 Service Need를 생성한다.

플랫폼이 임의 안전재고를 만들지 않는다.

기본값:

`Inventory LB = 0`

선사가 챗봇으로 최소재고를 요청할 때만 정책을 추가한다.

Need r:

- carrier
- destination
- container size
- quantity
- due time
- priority

---

# 5. Source Release Capacity

KORAIL이 다른 거점의 공컨을 과도하게 빼내어 해당 선사의 자체 수요를 훼손하면 안 된다.

선사 c, source o, 규격 k에 대해 시점 t까지 누적 rail departure는 해당 시점까지의 방출가능량 이하로 제한한다.

`Cumulative Rail Departure(c,o,k,t) <= Source Release Capacity(c,o,k,t)`

Carrier A 재고는 Carrier A의 Need에만 사용 가능하다.

---

# 6. 핵심 의사결정변수

### x[r,o,p] ∈ Z+

Need r의 공컨 중 source o에서 train p를 통해 운송하는 box 수.

### u[r] ∈ Z+

해당 Need 중 rail로 배정되지 않은 box 수.

### y[p] ∈ {0,1}

Candidate Train p 운행 여부.

### z[p,m] ∈ {0,1}

Train p의 편성 m 선택 여부.

---

# 7. 핵심 제약

## 7.1 Need Conservation

`Σ(o,p) x[r,o,p] + u[r] = q[r]`

따라서 실제 Service Need에 없는 공컨을 적재율 충족 목적으로 이동할 수 없다.

## 7.2 Time Window

각 협의 라운드의 effective 조건으로 Candidate Assignment를 생성한다.

`earliest_arrival[r] <= arrival[p,destination(r)] <= latest_arrival[r]`

## 7.3 Blocked Origin

선사가 특정 source를 금지하면 해당 origin의 x-variable 자체를 생성하지 않는다.

## 7.4 Formation

`Σ_m z[p,m] = y[p]`

## 7.5 Segment Load

`L[p,e] = Σ(r,o) TEU[r] × delta[r,o,p,e] × x[r,o,p]`

## 7.6 Segment Capacity

`L[p,e] <= Σ_m Capacity[m] × z[p,m]`

## 7.7 Minimum Consolidation Level — Scenario

`Σ_e distance[e] × L[p,e] >= alpha × Capacity[p] × Σ_e distance[e]`

현재 alpha=0.50은 **KORAIL 공식 손익분기 적재율이 아니라 해커톤 운영 시나리오**다.

---

# 8. KORAIL Optional Operational Constraints

## 8.1 Train Path Slot

특정 노선/시간창에서 추가 운행가능한 신규 열차 수가 주어지면:

`Σ y[p in slot] <= PathCap[slot]`

## 8.2 Locomotive

시간 t에 운행 중인 신규 공컨열차:

`Σ y[p active at t] <= AvailableLocomotives[t]`

## 8.3 Wagon

`Σ Wagons[m] × z[p,m] <= AvailableWagons[t]`

현재 실제 자원값이 없으면 해당 제약은 비활성화한다.

---

# 9. 실행상태

## PROPOSAL

모든 예상 Service Need를 대상으로 선사별 잠정 Proposal 생성.

## NEGOTIATION

- ACCEPTED: 서비스 commitment 보호
- MODIFIED: 수정조건으로 전체 재최적화
- REJECT_OPTION: 기존 옵션만 제외하고 대안 탐색
- DECLINED: 해당 rail service 제외
- PENDING: 계속 제안 가능

## FINAL

**ACCEPTED / MODIFIED_ACCEPTED 물량만 KORAIL 최종 운영계획 대상**이다.

PENDING / DECLINED 물량은 최종열차에 실리지 않는다.

---

# 10. 챗봇 Action 의미

- `ACCEPT_SERVICE`: 수량·목적지·기한 등 서비스 수준 수락. Train은 KORAIL이 재배정 가능.
- `ACCEPT_EXACT_PLAN`: 현재 source/train까지 고정 수락.
- `REJECT_OPTION`: 이 시간/열차는 거절, 다른 rail option 탐색.
- `DECLINE_RAIL_SERVICE`: 이번 rail service 자체를 거절.
- `MODIFY_SERVICE`: 수량·도착윈도우·source 조건을 한 번에 수정.

---

# 11. Lexicographic Objective

1. 선사 Rail Unserved TEU 최소화
2. 신규열차 수 최소화
3. Train-km 최소화
4. Wagon-km 최소화
5. 너무 이른 도착(TEU-hour) 최소화
6. 위 조건이 모두 같을 때 선사 예상 철도운임 최소화

철도운임은 KORAIL 운영효율보다 앞서지 않는다.

---

# 12. 최종 Output

## Carrier

- `CARRIER_PROPOSALS.csv`
- `CARRIER_PROPOSAL_DETAIL.csv`
- `CARRIER_COMMITMENT_STATUS.csv`
- `RAIL_UNSERVED.csv`

## KORAIL

- `KORAIL_TRAIN_PLAN.csv`
- `STOP_WORK_PLAN.csv`
- `SEGMENT_LOAD.csv`
- `OPERATIONAL_CONSTRAINT_AUDIT.csv`

---

# 13. 해석 원칙

- 109/118 TEU는 현재 synthetic week/timetable/50% consolidation scenario에서 나온 **데모 결과**다.
- 50%는 공식 KORAIL 경제성 기준이 아니다.
- 00/06/12/18 후보는 prototype timetable이다.
- 33/40/50량은 route별 feasibility가 실제 확정된 값이 아니라 scenario option을 포함한다.
- 내부 실제 운영원가가 없으므로 `Revenue - Cost` 경제성 최적화는 아직 하지 않는다.
