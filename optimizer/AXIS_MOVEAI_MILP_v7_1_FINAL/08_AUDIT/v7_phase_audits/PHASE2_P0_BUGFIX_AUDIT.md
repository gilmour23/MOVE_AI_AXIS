# Phase 2 감사 — P0 코드 버그

**대상 지시:** v7 수정 지시서 Phase 2 (2-1 / 2-2 / 2-3)
**판정:** 완료. `07_VALIDATION/PHASE2_TESTS.csv` **29/29 PASS**

---

## 1. 변경한 파일

| 파일 | 내용 |
|---|---|
| `02_CODE/axis_milp_v7.py` | 정책 파서 전면 교체, forced equality 제거, Z7 tie-break, solver 감사, uuid 키 변경, MAX_INVENTORY/BLOCK_OUTBOUND 구현 |
| `01_DOCS/INVENTORY_POLICY_SCHEMA.md` | **신규** — 정책 JSON 정본 |
| `02_CODE/test_phase2_v7.py` | **신규** — 회귀 테스트 |
| `07_VALIDATION/PHASE2_TESTS.csv` | 테스트 결과 |

---

## 2-1. Proposal 결정성

### 수정 전 문제
동일 코드·입력으로 재실행 시 Proposal 집합이 달라졌습니다 (배포본 31건 / 재실행 30건, uuid 10건 소멸).
목적함수 값은 동일한 **대체최적해** 였고, `proposal_uuid` 가 `need_allocation` 문자열을 키로 써서
박스 배분이 조금만 달라져도 전부 새 uuid 가 되었습니다.

### 수정 내용

**(a) Z7 deterministic tie-break stage 추가**

```python
# Z1~Z6 은 이미 e6 로 전부 고정되어 있으므로 이 stage 는 어떤 KPI 도 바꾸지 않는다.
# 대체최적해 중 하나를 정규 해로 고정하는 역할만 한다.
order = sorted(assignments,
               key=lambda a:(a.carrier, a.need_id, a.destination, a.origin, a.train_id, a.size))
c7[a.var] = rank            # 모델 내용에만 의존, dict/solver 순회 순서와 무관
```

가중치가 dict 순회 순서가 아니라 **모델 내용의 canonical sort key** 에만 의존하므로
머신·HiGHS 버전이 달라져도 같은 해를 고릅니다.

**(b) proposal_uuid 키 재설계**

```
v6.1: AXIS|round|carrier|origin|dest|size|train|need_allocation
v7  : AXIS|round|carrier|origin|dest|size|train
```

선사가 협의하는 서비스 정체성은 (선사, 출발지, 도착지, 규격, 열차, 라운드) 이며
내부 need 분배는 협의 대상이 아닙니다.

### 검증 — 동일 명령 5회 반복

| 항목 | 결과 |
|---|---|
| Proposal grouping + uuid (정렬 후 해시) | 5회 **완전 동일** |
| unserved_teu | {86.0} |
| train_count | {2} |
| train_km | {798.7} |
| wagon_km | {26357.1} |
| rail_charge_krw | {9596508.85} |
| served_teu | {94} |
| selected_train_count | {2} |
| 선택된 열차 집합 | 1가지 |

---

## 2-2. Quantity Modification 버그

### 수정 전 문제

```python
for nid,q in target_allocs: forced_service_by_need[nid] += q     # 해당 proposal 만 집계
...
if forced is not None: rows.add(coeff, lb=forced, ub=forced)     # NEED 총합에 등식
```

하나의 need 가 여러 proposal 에 분할되어 있으면, 한 proposal 의 수량을 줄일 때
**손대지 않은 proposal 의 물량까지 삭제**되었습니다.

### 수정 내용

`forced_service_by_need` 를 **완전히 제거**했습니다. 감축은 이미 `declined_by_need`(상한)로,
확정은 `accepted_by_need`(하한)로 정확히 표현되므로 need 단위 등식은 필요하지도 옳지도 않습니다.

```python
if run_mode=="FINAL":
    rows.add(coeff, lb=0, ub=accepted)
else:
    if accepted>0: rows.add(coeff, lb=accepted)
    if declined>0: rows.add(coeff, ub=max(total_q-declined,0))
```

### 검증 — 리뷰 문서 NEED0039 반례 (지시서 요구)

v7 데이터셋에는 분할 need 가 우연히 없으므로, **반례가 실재하는 v6.1 데이터셋에 v7 코드를 적용**해
회귀 테스트로 고정했습니다 (`08_AUDIT/v6_1_reference/`).

NEED0039(3박스) = PROP0013(BUGANG발 2) + PROP0016(UIWANG발 1).
PROP0013 을 3 → 2 로 감축했을 때:

| 검사 | 결과 |
|---|---|
| shared_need_exists | PASS — `NEED0039 -> [('PROP0013',2), ('PROP0016',1)]` |
| need_total_is_3 | PASS |
| reduction_is_exactly_one_box | PASS — `declined={'NEED0040': 1}` |
| shared_need_not_declined | PASS — NEED0039 declined=0 |
| no_upper_bound_below_need_total | PASS — NEED0039 을 3 미만으로 제한하는 제약행 없음 |
| no_need_level_forced_equality_row | PASS — 등식행 없음 |
| forced_equality_code_removed | PASS |

v6.1 동작: `NEED0039` 상한이 2 로 고정 → PROP0016 의 1박스 소멸 → rail served 109 → 107 (−2).
v7 동작: `NEED0040` 만 1박스 감축 → **정확히 −1**.

---

## 2-3. Policy JSON Schema 통일

### 수정 전 문제
계획서 §69(`rule_type`, `hub`)와 코드(`type`, `hub_code`)가 달랐고,
**인식 못 하는 정책을 경고 없이 skip** 했습니다. 계획서대로 만든 JSON 이 아무 효과 없이 통과했습니다.

### 수정 내용

`01_DOCS/INVENTORY_POLICY_SCHEMA.md` 를 **정본**으로 새로 정의하고 파서를 전면 교체했습니다.
조용한 skip 은 코드에서 사라졌습니다 — 모든 이상은 `PolicyValidationError` 로 발생합니다.

**구현한 rule_type**

| rule_type | 계획서 | 모델 처리 |
|---|---|---|
| `MIN_INVENTORY_AT_TIME` | Type B | 해당 시점 재고 하한 → Service Need 생성 |
| `MIN_INVENTORY_RANGE` | Type A | 기간 재고 하한 |
| `MAX_INVENTORY` | Type C | `baseline_stock + Σ(도착 x, arr≤t) ≤ value` |
| `BLOCK_OUTBOUND` | Type E | `Σ(출발 x, origin=h, 기간내) ≤ value` |

**명시적 미구현**

| rule_type | 처리 |
|---|---|
| `TARGET_INVENTORY` (Type D, soft) | `RULE_TYPE_NOT_IMPLEMENTED` 오류. 문서에 미구현 명시 |

**오류 코드 12종** — `SCHEMA_TYPE_ERROR` `MISSING_FIELD` `UNKNOWN_RULE_TYPE`
`RULE_TYPE_NOT_IMPLEMENTED` `UNKNOWN_FIELD` `UNKNOWN_CARRIER` `UNKNOWN_HUB`
`UNKNOWN_CONTAINER_SIZE` `BAD_VALUE` `BAD_TIME_FORMAT` `TIME_OUTSIDE_HORIZON`
`BAD_TIME_RANGE` `SOFT_CONSTRAINT_NOT_SUPPORTED`

### 검증

| 검사 | 결과 |
|---|---|
| v6.1 legacy key(`type`) | PASS — `MISSING_FIELD` (legacy key 발견 사실 안내 포함) |
| 계획서 §69 형식(`rule_type: MIN_INVENTORY`) | PASS — `UNKNOWN_RULE_TYPE` |
| `TARGET_INVENTORY` | PASS — `RULE_TYPE_NOT_IMPLEMENTED` |
| 없는 hub / carrier | PASS |
| 계획기간 밖 시각 | PASS — `TIME_OUTSIDE_HORIZON` (horizon 안내 포함) |
| `hard_constraint: false` | PASS — `SOFT_CONSTRAINT_NOT_SUPPORTED` |
| 음수 value | PASS — `BAD_VALUE` |
| 정상 MIN_INVENTORY_RANGE | PASS — needs 147 → 149 (실제 반영) |
| ACTIVE_POLICY 기록 | PASS |
| MAX_INVENTORY 파싱 | PASS — 168 슬롯 |
| BLOCK_OUTBOUND 파싱 | PASS |

출력물 `ACTIVE_POLICY.json`, `INVENTORY_POLICY_AUDIT.csv`, `SUMMARY.json:active_policy_count` 추가.

---

## 3. 작업 중 발견해 함께 처리한 문제

### 3-1. Z5 stage 가 시간제한에 걸림 — 새 solver 가드가 검출

Phase 6 의 solver 건전성 검사를 먼저 넣은 덕분에 드러났습니다.
v7 데이터(needs 147, vars 9,731)에서 조기도착 무제한일 때 `Z5_earliness_teu_hours` 가
90초·600초 모두 최적성을 증명하지 못했습니다.

```
RuntimeError: stage 'Z5_earliness_teu_hours' not proven optimal (status=1): Time limit reached.
```

**v6.1 이었다면 이 해를 최적해로 간주하고 이후 stage 에 그대로 고정했을 상황입니다.**
동시에 이는 결정성(2-1)도 깨뜨립니다 — 시간제한 해는 실행 시점에 따라 달라지기 때문입니다.

대응으로 `--max-earliness` 를 도입했습니다 (Phase 4 항목이지만 여기서 필요).
조기도착 상한을 두면 후보 assignment 가 줄어 모델이 작아지고 전 stage 가 최적성을 증명합니다.

| max_earliness | assignments | vars | 후보열차 | solve | 전 stage 최적증명 |
|---|---|---|---|---|---|
| 48h | 1,314 | 1,514 | 15 | 50.6s | ✅ |
| 72h | 5,319 | 5,759 | 81 | 498.6s | ✅ |
| 무제한 | 9,183 | 9,731 | 110 | >600s/stage | ❌ |

Phase 2 검증은 48h 기준으로 수행했습니다. **최종 default 는 Phase 4 에서 확정**합니다.

### 3-2. 최소 consolidation 수준과 조기도착의 구조적 trade-off

민감도 준비 중 발견했습니다. 최소적재율 0.5 에서:

| max_earliness | assignments (minLF=0) | assignments (minLF=0.5) |
|---|---|---|
| 0h | 169 | **0** |
| 12h | 2,349 | **0** |
| 24h | 4,472 | **0** |
| 48h | 8,440 | 1,314 |
| 72h | 11,601 | 5,319 |
| 무제한 | 16,040 | 9,183 |

**24시간 이하에서는 최소적재율 50% 를 만족하는 열차가 하나도 존재하지 않습니다.**
시간창 자체는 feasible 하지만(minLF=0 에서 assignment 존재), 일주일에 흩어진 수요를
24시간 창 안에서 모아 66 TEU 열차의 절반을 채울 수 없기 때문입니다.

이는 데이터나 코드 결함이 아니라 **실제 구조적 trade-off** 이며 Phase 4 에서 정식 보고합니다.

### 3-3. 함께 처리한 리뷰 항목

| 리뷰 # | 내용 | 처리 |
|---|---|---|
| #15 | lexicographic + MIP gap 건전성 | stage별 status/gap/objective/runtime 을 `SOLVER_AUDIT.csv` 에 기록. Z1·Z2 는 `mip_rel_gap=0`. 최적성 미증명 stage 는 예외 발생 |
| #18 | TRAIN_CANDIDATE 재생성 조건 | `_candidate_inputs_match()` 로 시작시각·horizon 일치를 검사. 불일치 시 재생성 |
| 지시서 §4 | 화차 회송 | `SUMMARY.json:return_wagon_movement_included=false` 기록 |
| 리뷰 #60 | TEU-km KPI 부재 | `SUMMARY.json:teu_km`, `avg_carriers_per_train`, `avg_distance_weighted_load_factor` 추가 |

---

## 4. 현재 PROPOSAL 결과 (max_earliness=48, minLF=0.5)

| 항목 | 값 |
|---|---|
| requested_teu | 180 |
| served_teu | 94 |
| unserved_teu | 86 |
| selected_train_count | 2 |
| proposal_count | 25 |
| teu_km | 26,417 |
| avg_carriers_per_train | 5.5 |
| avg_distance_weighted_load_factor | 0.5011 |
| earliness_teu_hours | 1,914 |
| all_stages_proven_optimal | **true** |
| expected_korail_revenue_krw | 9,596,509 |

v6.1 의 `118 / 109 / 2편 / 92.37%` 는 폐기했습니다 (지시서 §6).

---

## 5. 남아있는 한계

1. **조기도착 무제한 설정은 현재 규모에서 최적성을 증명하지 못합니다.** Phase 4 에서
   default 를 확정하고, 무제한은 "solver 한계로 미증명"임을 명시해 보고합니다.
2. `TARGET_INVENTORY`(soft target) 미구현입니다. 계획서 §29·§37 의 챗봇 시나리오 중
   soft target 부분은 현재 지원되지 않으며 문서에 명시했습니다.
3. `MAX_INVENTORY` 는 재고 결정변수가 없는 구조상 "철도 반입 총량 상한"으로 구현됩니다.
   목적지 장치장 제한 용도로는 정확하지만, 자체 공급으로 초과하는 경우는 제어하지 않습니다.
4. 결정성은 **동일 환경 5회** 로 검증했습니다. 다른 scipy/HiGHS 버전 간 동일성은
   Z7 tie-break 로 구조적으로 보장하되 실측하지는 않았습니다.
