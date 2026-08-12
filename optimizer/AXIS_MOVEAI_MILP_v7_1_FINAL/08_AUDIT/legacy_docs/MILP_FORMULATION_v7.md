# AXIS MILP v7 — 수리모형

**Carrier Proposal → Chatbot Negotiation → Final KORAIL Operation**

> 이 문서가 코드의 정본 수식이다.
> 프로젝트 통합계획 v3 §47~§52 는 `I_cikt` 를 MILP 결정변수로 두는 재고보존식 모형을 기술하지만,
> 실제 구현은 **재고·정책 → Service Need 사전생성 → Rail Assignment MILP** 구조다.
> 계획서 대신 이 문서를 기준으로 한다 (v7 수정 지시서 §1).

---

## 1. 서비스 정의

1. 모든 선사의 `현재재고 × 향후수요 × 향후 외생공급` 을 동시에 분석한다.
2. KORAIL AXIS MILP 가 각 선사에 공컨 철도운송 **잠정 Proposal** 을 제시한다.
3. 선사는 챗봇으로 수락·수정·대안요청·거절을 한다.
4. AXIS 가 **전체 선사를 다시 공동최적화**한다.
5. FINAL mode 에서는 확정된 Carrier Commitment 만 모아 KORAIL 최종 운영계획을 산출한다.

공컨 소유권은 선사별로 독립 유지된다. 공유되는 것은 KORAIL 열차 capacity 이다.

---

## 2. 왜 재고를 결정변수로 두지 않는가

플랫폼의 역할은 **재고정책을 대신 정하는 것이 아니라 운송을 최적화하는 것**이다 (계획서 §24).

따라서 재고 흐름은 선사가 제출한 데이터와 선사가 직접 설정한 정책만으로 결정되고,
MILP 는 그 결과로 도출된 **Service Need 를 어떻게 철도로 실어나를지**만 푼다.

```text
Carrier Inventory / Policy
        ↓   (결정변수 아님. 선사 데이터 + 선사 정책으로 확정)
Service Need
        ↓   (여기서부터 MILP)
KORAIL Rail Assignment + Train Design
```

이 구조의 이점과 한계는 §11 에 명시한다.

---

## 3. 집합

| 기호 | 의미 |
|---|---|
| `c ∈ C` | 선사 (Virtual Carrier) |
| `i, j ∈ N` | 6개 거점 |
| `k ∈ K` | 20FT, 40FT |
| `t ∈ T` | 시간 (168) |
| `r ∈ R` | 선사별 Service Need |
| `p ∈ P` | Candidate Train Trip |
| `m ∈ M_p` | 편성 옵션 |
| `e ∈ E_p` | Train p 의 physical rail segment |

---

## 4. Service Need 생성

철도 재배치가 없을 때의 물리 재고 흐름에서 stockout 이 발생하거나,
선사가 직접 설정한 재고정책이 있을 때만 Need 를 만든다.
**플랫폼이 임의 안전재고를 만들지 않는다.** 기본 `Inventory LB = 0`.

각 `(c, i, k)` 에 대해 시간순으로

```
physical_available = physical_stock + S[c,i,k,t]
physical_unmet     = max(D[c,i,k,t] − physical_available, 0)
physical_stock     = max(physical_available − D[c,i,k,t], 0)

target_available   = target_stock + S[c,i,k,t]
gap                = max(D[c,i,k,t] + LB[c,i,k,t] − target_available, 0)
if gap > 0 :  Need r = (c, i, k, quantity=gap, due=t)
target_stock       = max(target_available, D + LB) − D
```

`target_stock` 은 앞서 생성된 Need 가 충족된다고 가정하므로 Need 가 중복 생성되지 않는다.

---

## 5. Source Release Capacity

KORAIL 이 다른 거점의 공컨을 과도하게 빼내어 해당 선사의 자체 수요를 훼손하면 안 된다.

```
SourceRelease[c,o,k,t] = max( physical_stock[c,o,k,t] − LB[c,o,k,t], 0 )

∀ t :   Σ_{r,p : load_slot(p,o) ≤ t}  x[r,o,p]   ≤   SourceRelease[c,o,k,t]
```

**v7:** 누적 판정 기준을 열차 *출발* 이 아니라 **상차 개시(`load_slot`)** 로 바꿨다.
공컨은 상차를 시작하는 시점에 이미 그 거점에 있어야 하기 때문이다.

Carrier A 재고는 Carrier A 의 Need 에만 사용 가능하다.

---

## 6. 결정변수

| 변수 | 정의역 | 의미 |
|---|---|---|
| `x[r,o,p]` | ℤ₊ | Need r 의 공컨 중 source o 에서 train p 로 운송하는 box 수 |
| `u[r]` | ℤ₊ | 해당 Need 중 rail 로 배정되지 않은 box 수 |
| `y[p]` | {0,1} | Candidate Train p 운행 여부 |
| `z[p,m]` | {0,1} | Train p 의 편성 m 선택 여부 |

---

## 7. 제약

### 7.1 Need Conservation

```
Σ_{o,p} x[r,o,p] + u[r] = q[r]
```

Service Need 에 없는 공컨을 적재율을 채우려고 이동시킬 수 없다.

### 7.2 Time Window

**v7:** 기한 판정 기준이 열차 도착이 아니라 **하화 완료 = 실제 사용 가능 시각** 이다.

```
available(p, dest(r)) = arrival(p, dest(r)) + destination_unloading_h

earliest[r] ≤ available(p, dest(r)) ≤ latest[r]
```

`latest[r]` 는 협의로 바뀔 수 있고, `earliest[r]` 는
`earliest_arrival` 또는 `max_earliness_hours` 로부터 유도된다.
**v7 은 서비스 전역 기본 `max_earliness` 를 둘 수 있다** (§10).

### 7.3 Blocked Origin

선사가 특정 source 를 금지하면 해당 origin 의 x 변수 자체를 생성하지 않는다.

### 7.4 Formation

```
Σ_m z[p,m] = y[p]
```

### 7.5 Segment Load & Capacity

```
L[p,e] = Σ_{r,o} TEU[r] · δ[r,o,p,e] · x[r,o,p]
L[p,e] ≤ Σ_m Capacity[m] · z[p,m]          ∀ e ∈ E_p
```

여러 선사의 공컨이 동일 구간에서 하나의 열차 capacity 를 공동사용한다.

### 7.6 Minimum Consolidation Level — Scenario

```
Σ_e physical_distance[e] · L[p,e]  ≥  α · Capacity[p] · Σ_e physical_distance[e]
```

> α 는 **KORAIL 공식 손익분기 적재율이 아니다.** 운영 시나리오 값이며
> 0.5 / 0.6 / 0.7 민감도를 반드시 함께 제시한다.

### 7.7 물리적 중복열차 제한 (v7 신규)

항상 활성. KORAIL 데이터 유무와 무관한 물리적 사실이다.

```
Σ_{p : origin(p)=i, dep_slot(p)=t}  y[p]  ≤  1          (동일 거점·시각 출발)
Σ_{p : e ∈ E_p, e ∈ TRUNK, dep_slot(p,e)=t}  y[p]  ≤  1  (공유 trunk 동시 점유)
```

`TRUNK` = 의왕–부강. 두 corridor 가 물리적으로 공유하는 구간이다.

### 7.8 선사 재고정책 (선택)

`01_DOCS/INVENTORY_POLICY_SCHEMA.md` 가 정본이다.

| rule_type | 제약 |
|---|---|
| `MIN_INVENTORY_AT_TIME` / `MIN_INVENTORY_RANGE` | `LB` 상향 → §4 에서 Need 생성 |
| `MAX_INVENTORY` | `baseline_stock[c,i,k,t] + Σ_{arr ≤ t} x ≤ UB` |
| `BLOCK_OUTBOUND` | `Σ_{origin=i, 기간내} x ≤ cap` |

`TARGET_INVENTORY`(soft) 는 v7 미구현이며 요청 시 구조화 오류를 반환한다.

### 7.9 KORAIL 운영제약 (선택, 데이터 있을 때만)

```
Σ_{p ∈ slot} y[p] ≤ PathCap[slot]
Σ_{p active at t} y[p] ≤ AvailableLocomotives[t]
Σ_m Wagons[m] · z[p,m] ≤ AvailableWagons[t]
```

실제 값이 없으면 `NOT_APPLIED_NO_DATA` 로 명시 기록한다.

### 7.10 협의 상태 제약

```
PROPOSAL / NEGOTIATION :   Σ x[r,·,·] ≥ accepted[r]
                           Σ x[r,·,·] ≤ q[r] − declined[r]
FINAL                  :   Σ x[r,·,·] ≤ accepted[r]
```

**v7:** need 단위 등식(`lb = ub = forced`)을 제거했다.
하나의 need 가 여러 proposal 에 분할되어 있을 때 한 proposal 의 수량을 줄이면
손대지 않은 proposal 의 물량까지 삭제되던 버그의 원인이었다.
감축은 `declined`(상한), 확정은 `accepted`(하한) 으로 이미 정확히 표현된다.

---

## 8. 거리 — 두 종류 (v7)

| 이름 | 용도 | 정의 |
|---|---|---|
| `physical_distance_km` | Train-km / Wagon-km / TEU-km / 구간 적재율 | 열차 실제 주행거리. **정차역 인입선 포함** |
| `tariff_distance_km` | 운임 계산 전용 | 코레일 영업거리. 통과역 인입선 미포함 |

두 값은 의왕 출발 OD 8건에서 정확히 5.8 km 차이가 난다.

```
의왕→부강 111.8 = 의왕인입 + 경부선(의왕~부강) + 부강인입
부강→약목 152.6 = 부강인입 + 경부선(부강~약목)
의왕→약목 258.6 = 의왕인입 + 경부선(의왕~약목)
⇒ 111.8 + 152.6 − 258.6 = 5.8 = 2 × 부강인입선(2.9km)
```

부강 CY 에 **정차**하는 열차는 인입선을 진입·진출 2회 주행하지만,
**통과** OD 의 영업거리에는 인입선이 포함되지 않는다.
오류가 아니라 서로 다른 물리량이며, runtime 에 자동 검증한다
(`DISTANCE_VALIDATION.csv`, `DISTANCE_PHYSICAL_VS_TARIFF.csv`).

> 알려진 한계: 약목·동산 인입선은 원자료 재구성에서 0 으로 처리되어 있어
> 거점 간 완전한 일관성은 없다.

---

## 9. 상하차 시간 (v7)

세 가지를 분리하며 전부 CLI 로 조정 가능하다.

| 파라미터 | 기본값 | 출처 |
|---|---|---|
| `origin_loading_h` | 3.0 | 코레일 화물운송약관 컨테이너 적재제한시간 |
| `intermediate_handling_h` | 3.0 | 하화제한시간 |
| `destination_unloading_h` | 3.0 | 하화제한시간 |

```
load_slot[origin]  = dep_slot[origin] − ⌈origin_loading_h⌉
dep_slot[b]        = arr_slot[b] + ⌈intermediate_handling_h⌉      (중간역)
avail_slot[hub]    = arr_slot[hub] + ⌈destination_unloading_h⌉
```

v6.1 은 출발역 dwell 이 구조적으로 0 이어서 0시간에 49 TEU 를 상차하는 계획을 산출했다.

---

## 10. Lexicographic Objective

| 순위 | 목적 | gap |
|---|---|---|
| Z1 | 선사 Rail Unserved TEU 최소화 | **0 (proven optimum 요구)** |
| Z2 | 신규열차 수 최소화 | **0 (proven optimum 요구)** |
| Z3 | Train-km 최소화 | 기본 |
| Z4 | Wagon-km 최소화 | 기본 |
| Z5 | 조기도착(TEU-hour) 최소화 | 기본 |
| Z6 | 선사 예상 철도운임 최소화 | 기본 |
| **Z7** | **deterministic tie-break** | 기본 |

- 철도운임은 KORAIL 운영효율보다 앞서지 않는다.
- **Z7 은 Z1~Z6 이 전부 고정된 뒤에만 작동**하므로 어떤 KPI 도 바꾸지 않는다.
  대체최적해 중 하나를 정규 해로 고정해 재현성을 보장한다.
  가중치는 `(carrier, need_id, destination, origin, train_id, size)` canonical sort 의
  순위이며 dict/solver 순회 순서에 의존하지 않는다.
- 모든 stage 의 status / gap / objective / runtime 이 `SOLVER_AUDIT.csv` 에 기록된다.
  **최적성을 증명하지 못한 stage 가 있으면 결과를 산출하지 않고 중단**한다
  (time-limit 해를 최적해로 취급하지 않는다).

`max_earliness` 는 Z5 를 보조하는 **하드 제약**으로도 둘 수 있다.
Z2(열차 수 최소화)가 Z5 보다 우선하므로 제약 없이는 조기도착이 억제되지 않기 때문이다.

---

## 11. 이 구조의 한계 (명시)

1. **환적 불가.** 도착한 공컨을 다른 거점으로 재발송하는 2단 이동을 모델링하지 않는다.
2. **도착 공컨이 source capacity 에 가산되지 않는다.** 보수적 방향이다.
3. **편도 계획모형이다.** 화차 회송은 포함되지 않는다
   (`return_wagon_movement_included = false`). 향후 자원 availability / turnaround 로 확장한다.
4. **실제 수익성은 주장하지 않는다.** 내부 운영원가 데이터가 없다.
   운영 KPI 는 Train Count / Train-km / Wagon-km / TEU-km / Load Factor /
   Tariff 기반 예상수입으로 한정한다.
5. Candidate timetable 은 prototype 이며 KORAIL 실제 train path 가 아니다.

---

## 12. 실행상태

| mode | 내용 |
|---|---|
| `PROPOSAL` | 모든 예상 Service Need 를 대상으로 선사별 잠정 Proposal 생성 |
| `NEGOTIATION` | ACCEPTED 보호 / MODIFIED 재최적화 / REJECT_OPTION 대안탐색 / DECLINED 제외 |
| `FINAL` | **ACCEPTED / MODIFIED_ACCEPTED 물량만** 최종 운영계획 대상 |

협의조건은 **Candidate Assignment 생성 전에** 적용되므로 기한 완화가 실제 탐색공간을 넓힌다.

---

## 13. 출력

### Carrier
`CARRIER_PROPOSALS.csv` `CARRIER_PROPOSAL_DETAIL.csv` `CARRIER_COMMITMENT_STATUS.csv`
`RAIL_UNSERVED.csv` `NONCOMMITTED_FORECAST_NEED.csv` `ACTIVE_POLICY.json`

### KORAIL
`KORAIL_TRAIN_PLAN.csv` `STOP_WORK_PLAN.csv` `SEGMENT_LOAD.csv`
`OPERATIONAL_CONSTRAINT_AUDIT.csv`

### 감사
`SOLVER_AUDIT.csv` `INVENTORY_POLICY_AUDIT.csv`
`RAIL_PARAMETER_PROVENANCE.csv` `DISTANCE_VALIDATION.csv` `DISTANCE_PHYSICAL_VS_TARIFF.csv`

### 비교·민감도
`BASELINE_COMPARISON.csv` `BASELINE_NO_REPOSITIONING.csv` `BASELINE_CARRIER_SEPARATE.csv`
`AXIS_INTEGRATED_RESULT.csv`
`EARLINESS_SENSITIVITY.csv` `LOAD_FACTOR_SENSITIVITY.csv` `HANDLING_TIME_SENSITIVITY.csv`
