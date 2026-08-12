# AXIS MILP v7.1 — 수리모형

**Joint Multi-Carrier Optimization (one-shot)**

> 이 문서가 코드의 정본 수식이다.
> 프로젝트 통합계획 v3 §47~§52 는 `I_cikt` 를 MILP 결정변수로 두는 재고보존식 모형을 기술하지만,
> 실제 구현은 **Carrier Input → Service Need → Joint Rail Assignment MILP** 구조다.
> 계획서 대신 이 문서를 기준으로 한다.

---

## 1. 서비스 정의

AXIS 는 각 선사가 제출한 자체 공컨 데이터와 KORAIL 이 제공하는 운행 가능한 철도 서비스 후보를
통합하여, 복수 선사의 공컨 재배치 수요를 **하나의 MILP 에서 동시에** 최적화한다.

```text
Carrier Input Data (선사별 독립 제출)
        ↓
Service Need Generation
        ↓
KORAIL Feasible Candidate Trains
        ↓
Joint Multi-Carrier MILP
        ↓
Single Optimal Solution
        ↓
Carrier Recommendation  +  KORAIL Integrated Operation Plan
```

v7.1 에는 `PROPOSAL → NEGOTIATION → FINAL` 상태기계가 없다.
선사 수락·수정·거절·commitment 기반 재최적화는 상용화 단계의 운영 프로세스이며
이번 연구 범위가 아니다 (참고 구현: `future_extensions/negotiation_legacy/`).

---

## 2. 왜 재고를 결정변수로 두지 않는가

플랫폼의 역할은 재고정책을 대신 정하는 것이 아니라 **운송을 최적화하는 것**이다.
재고 흐름은 선사가 제출한 데이터와 선사가 사전에 설정한 정책만으로 결정되고,
MILP 는 그 결과로 도출된 Service Need 를 어떻게 철도로 실어나를지만 푼다.

Service Need 는 KORAIL 이 임의로 만드는 선사 재고정책이 **아니다.**
선사 데이터로부터 철도 재배치 후보를 도출하기 위한 **model input layer** 이다.

---

## 3. 집합

| 기호 | 의미 |
|---|---|
| `c ∈ C` | 선사 (같은 planning cycle 에 데이터를 제출한 전체) |
| `i, j ∈ N` | 6개 거점 |
| `k ∈ K` | 20FT, 40FT |
| `t ∈ T` | 시간 (168) |
| `r ∈ R` | 선사별 Service Need |
| `p ∈ P` | KORAIL Candidate Train Trip |
| `m ∈ M_p` | 편성 옵션 |
| `e ∈ E_p` | Train p 의 physical rail segment |

---

## 4. Service Need 생성

철도 재배치가 없을 때의 물리 재고 흐름에서 stockout 이 발생하거나,
선사가 **사전에** 제출한 재고정책이 있을 때만 Need 를 만든다.
플랫폼이 임의 안전재고를 만들지 않는다. 기본 `Inventory LB = 0`.

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

## 5. Source Release Capacity — carrier ownership

A 선사 재고는 A 선사 Need 에만 사용 가능하다.
또한 다른 거점의 공컨을 과도하게 빼내어 해당 선사의 자체 수요를 훼손하면 안 된다.

```
SourceRelease[c,o,k,t] = max( physical_stock[c,o,k,t] − LB[c,o,k,t], 0 )

∀ t :   Σ_{r,p : load_slot(p,o) ≤ t}  x[r,o,p]   ≤   SourceRelease[c,o,k,t]
```

누적 판정 기준은 열차 *출발* 이 아니라 **상차 개시(`load_slot`)** 다.
공컨은 상차를 시작하는 시점에 이미 그 거점에 있어야 하기 때문이다.

---

## 6. 결정변수

| 변수 | 정의역 | 의미 |
|---|---|---|
| `x[r,o,p]` | ℤ₊ | Need r 의 공컨 중 source o 에서 train p 로 운송하는 box 수 |
| `u[r]` | ℤ₊ | 철도로 배정되지 않은 box 수 |
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

기한 판정 기준은 열차 도착이 아니라 **하화 완료 = 실제 사용 가능 시각**이다.

```
available(p, dest(r)) = arrival(p, dest(r)) + destination_unloading_h
earliest[r] ≤ available(p, dest(r)) ≤ due[r]
earliest[r] = max(0, due[r] − max_earliness)
```

`max_earliness` 는 서비스 설계 scenario parameter 다 (정본 72h).
`Z2`(열차 수 최소화)가 `Z5`(조기도착)보다 우선하므로, 상한이 없으면 조기도착이 억제되지 않는다.

### 7.3 Formation

```
Σ_m z[p,m] = y[p]
```

### 7.4 Segment Load & Capacity

```
L[p,e] = Σ_{r,o} TEU[r] · δ[r,o,p,e] · x[r,o,p]
L[p,e] ≤ Σ_m Capacity[m] · z[p,m]          ∀ e ∈ E_p
```

**여러 선사의 공컨이 동일 구간에서 하나의 열차 capacity 를 공동사용한다.**
이것이 AXIS 의 multi-carrier consolidation 이다.

### 7.5 Minimum Consolidation Level — Scenario

```
Σ_e physical_distance[e] · L[p,e]  ≥  α · Capacity[p] · Σ_e physical_distance[e]
```

> α 는 **KORAIL 공식 손익분기 적재율이 아니다.** 0.5 / 0.6 / 0.7 민감도를 함께 제시한다.

### 7.6 물리적 중복열차 제한

항상 활성. KORAIL 데이터 유무와 무관한 물리적 사실이다.

```
Σ_{p : origin(p)=i, dep_slot(p)=t}  y[p]  ≤  1                (동일 거점·시각 출발)
Σ_{p : e ∈ E_p, e ∈ TRUNK, dep_slot(p,e)=t}  y[p]  ≤  1        (공유 trunk 동시 점유)
```

`TRUNK` = 의왕–부강. 두 corridor 가 물리적으로 공유하는 구간이다.

### 7.7 선사 사전 재고정책 (선택)

`01_DOCS/INVENTORY_POLICY_SCHEMA.md` 가 정본이다.
**사후 negotiation 기능이 아니라 계획 실행 전 입력조건이다.**

| rule_type | 제약 |
|---|---|
| `MIN_INVENTORY_AT_TIME` / `MIN_INVENTORY_RANGE` | `LB` 상향 → §4 에서 Need 생성 |
| `MAX_INVENTORY` | `baseline_stock[c,i,k,t] + Σ_{arr ≤ t} x ≤ UB` |
| `ORIGIN_RELEASE_RESTRICTION` | `Σ_{origin=i, 기간내} x ≤ cap` |

`TARGET_INVENTORY`(soft) 는 미구현이며 요청 시 구조화 오류를 반환한다.

### 7.8 KORAIL Operational Inputs (선택, 데이터 있을 때만)

```
Σ_{p ∈ slot} y[p] ≤ PathCap[slot]
Σ_{p active at t} y[p] ≤ AvailableLocomotives[t]
Σ_m Wagons[m] · z[p,m] ≤ AvailableWagons[t]
```

실제 값이 없으면 `NOT_APPLIED_NO_DATA` 로 명시 기록한다.

---

## 8. 거리 — 두 종류

| 이름 | 용도 | 정의 |
|---|---|---|
| `physical_distance_km` | Train-km / Wagon-km / TEU-km / 구간 적재율 / 최소 consolidation | 열차 실제 주행거리. **정차역 인입선 포함** |
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
오류가 아니라 서로 다른 물리량이며 runtime 에 자동 검증한다.

---

## 8-A. 정차패턴 (Stop Pattern) — v7.1-patch

같은 물리경로라도 **어느 중간역에서 실제로 상하차를 하는지**에 따라 소요시간이 다르다.

| stop_type | 의미 | 중간역 소요시간 | 상하차 |
|---|---|---|---|
| `WORK_STOP` | 작업역 | `intermediate_handling_h` (3h) | 가능 |
| `PASS_THROUGH` | 통과역 | **0h** | 불가 |

출발역과 도착역은 항상 `WORK_STOP` 이다.

후보 생성기는 각 경로에 대해 중간역 정차조합 전체를 후보로 만든다.
MILP 는 이 중에서 선택하므로 **급행(직통)과 완행(전역정차)이 함께 경쟁**한다.

예: 의왕 > 부강 > 약목 > 부산신항, 06:00 출발

| stop_pattern | 작업역 | 총 소요 | 정차대기 | 도착 |
|---|---|---|---|---|
| `SPPS` | 의왕, 부산신항 | **6h** | 0h | 12:00 |
| `SSPS` | 의왕, 부강, 부산신항 | 9h | 3h | 15:00 |
| `SPSS` | 의왕, 약목, 부산신항 | 9h | 3h | 15:00 |
| `SSSS` | 전역 | 12h | 6h | 18:00 |

> v7.1-patch 이전에는 `SSSS` 만 존재해, 상하차가 전혀 없는 역에서도 3시간이 붙었다.
> 의왕→부산신항 직통이 12시간으로 계산되어 조기도착 창을 불필요하게 소모했다.

MILP 제약

```
x[r,o,p] 는 o 와 dest(r) 이 모두 train p 의 WORK_STOP 일 때만 생성된다.
```

`KORAIL_TRAIN_PLAN.csv` 에 `work_stops`, `work_stop_count`,
`transit_hours`, `dwell_hours` 가 기록되고,
`STOP_WORK_PLAN.csv` 의 각 행에 `stop_type` 이 표시된다.

---

## 9. 상하차 시간

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
- Z7 은 Z1~Z6 이 전부 고정된 뒤에만 작동하므로 어떤 KPI 도 바꾸지 않는다.
  대체최적해 중 하나를 정규 해로 고정해 재현성을 보장한다.
  가중치는 `(carrier, need_id, destination, origin, train_id, size)` canonical sort 순위이며
  dict/solver 순회 순서에 의존하지 않는다.
- 모든 stage 의 status / gap / objective / runtime 이 `SOLVER_AUDIT.csv` 에 기록된다.
  **최적성을 증명하지 못한 stage 가 있으면 결과를 산출하지 않고 중단**한다.

---

## 11. 출력 — 동일 solution 의 두 관점

### 선사 관점

| 파일 | 내용 |
|---|---|
| `CARRIER_RECOMMENDATIONS.csv` | 선사/OD/규격/열차 단위 권장 이동계획 |
| `CARRIER_RECOMMENDATION_DETAIL.csv` | Need 단위 상세 |
| `CARRIER_RECOMMENDATIONS_<CARRIER>.csv` | 선사별 격리 파일 |
| `RECOMMENDATION_EXPLANATION_CONTEXT.csv` | 챗봇 read-only 설명 근거 |

선사 인터페이스에서는 자기 회사 데이터와 자기 Recommendation 만 노출한다.
타 선사의 inventory / demand / supply / individual allocation 은 표시하지 않는다.
공동운송 여부는 `participating_carrier_count`, `train_load_factor` 집계정보로만 제공한다.

### KORAIL 관점

| 파일 | 내용 |
|---|---|
| `KORAIL_TRAIN_PLAN.csv` | 열차·경로·편성·적재율·참여선사수·train-km·wagon-km |
| `CARRIER_ALLOCATION.csv` | 열차별 선사 배분 |
| `STOP_WORK_PLAN.csv` | 거점별 상하차 |
| `SEGMENT_LOAD.csv` | 구간별 적재 TEU / 적재율 |

### 일치 검증

```
SUMMARY.json:
  carrier_recommendation_teu == korail_allocation_teu == rail_served_teu
  carrier_korail_view_consistent = true
```

---

## 12. 이 구조의 한계 (명시)

1. **환적 불가.** 도착한 공컨을 다른 거점으로 재발송하는 2단 이동을 모델링하지 않는다.
2. **도착 공컨이 source capacity 에 가산되지 않는다.** 보수적 방향이다.
3. **편도 계획모형이다.** 화차 회송은 포함되지 않는다.
4. **실제 수익성은 주장하지 않는다.** 내부 운영원가 데이터가 없다.
5. Candidate timetable 은 `PROTOTYPE_SYNTHETIC` 이며 KORAIL 실제 train path 가 아니다.
6. 선사 협상·수락행동·가격협상은 모델 범위 밖이다.

---

## 13. 연구용 베이스라인

실제 서비스 프로세스가 아니라 **AXIS 통합효과 검증용**이다.

| 시나리오 | 내용 |
|---|---|
| A. No Repositioning | 철도 재배치 없음 |
| B. Carrier Separate | 각 선사가 독립적으로 철도서비스 구성 (열차 공유 없음) |
| C. AXIS Integrated | 전체 선사 물량을 하나의 KORAIL capacity 에 공동 배정 |

동일한 service need / candidate timetable / formation / minimum load factor /
handling time / 운영 가정에서 비교한다.

비교 KPI: Rail Served TEU, Train Count, Train-km, Wagon-km, TEU-km,
Distance-weighted Load Factor, Average Carriers per Train.

B 는 `--carrier` 로 선사를 하나씩 제한해 MILP 를 따로 푼 뒤 합산한다.
**B 가 특정 결과가 나오도록 모델을 조정하지 않는다.**
