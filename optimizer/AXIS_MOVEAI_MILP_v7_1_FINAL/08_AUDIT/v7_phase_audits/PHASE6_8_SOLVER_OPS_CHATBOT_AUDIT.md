# Phase 6–8 감사 — Solver 건전성 / 운영제약 / 챗봇 UX

**대상 지시:** v7 수정 지시서 Phase 6, Phase 7, Phase 8
**판정:** 완료.

---

## Phase 6 — Solver 건전성

### 수정 전 문제

리뷰 문서 #15. `solve_lex()` 는 `res.x is None` 만 검사했습니다.
`mip_rel_gap = 0.001` 로 종료했거나 **time limit 으로 잘린 해도 최적해로 취급**하고,
그 값을 이후 stage 에 등식으로 고정했습니다.

### 수정 내용

```python
def solve(c, extra, name, gap=None):
    ...
    audit.append({"stage": name, "status": res.status, "success": res.success,
                  "message": res.message, "objective": ...,
                  "mip_gap_requested": ..., "mip_gap_achieved": ...,
                  "mip_dual_bound": ..., "runtime_sec": ..., "rows": ..., "cols": ...})
    if res.status != 0 or res.x is None:
        raise RuntimeError(f"stage '{name}' not proven optimal (status={res.status}) ...")
```

| 항목 | 처리 |
|---|---|
| stage별 status / gap / objective / runtime | `SOLVER_AUDIT.csv` 에 전량 기록 |
| Z1(unserved TEU), Z2(train count) | `mip_rel_gap = 0` — proven optimum 요구 |
| time limit 종료 | **최적해로 취급하지 않고 중단**. Phase 8 구조화 오류로 반환 |
| Z7 tie-break | 결정성 확보용 stage 추가 (Phase 2 참조) |

### 실효성 확인

이 가드가 실제로 문제를 잡았습니다. v7 데이터(needs 147, vars 9,731)에서
조기도착 무제한일 때 `Z5_earliness_teu_hours` 가 90초·600초 모두 최적성을 증명하지 못했습니다.

```
RuntimeError: stage 'Z5_earliness_teu_hours' not proven optimal (status=1): Time limit reached.
```

**v6.1 이었다면 이 해를 그대로 최적해로 보고했을 상황입니다.**
또한 시간제한 해는 실행 시점에 따라 달라지므로 재현성(Phase 2)도 함께 깨집니다.

대응으로 조기도착 상한(`--max-earliness`)을 도입해 모델 규모를 줄였고,
이후 Phase 5 의 하역시간 3시간 반영과 Phase 7 의 conflict 제약이 더해지면서
**무제한 조합도 355.9초에 최적성을 증명**하게 되었습니다.

---

## Phase 7 — 운영제약

### 7-1. 데이터 없음 명시 기록

```python
for kind in ("path_slot_capacity", "resource_capacity"):
    if not operations_obj.get(kind):
        operational_audit.append({
            "type": kind.upper(), "status": "NOT_APPLIED_NO_DATA",
            "rule": "KORAIL 실제 운영자원 데이터가 제공되지 않아 비활성. "
                    "구조는 구현되어 있으며 값만 넣으면 즉시 적용된다."})
```

적용된 제약에도 `status: "APPLIED"` 를 붙여 `OPERATIONAL_CONSTRAINT_AUDIT.csv` 에서
무엇이 실제로 걸렸고 무엇이 데이터 부재로 비활성인지 한눈에 구분됩니다.

### 7-2. COMMON segment 문제

리뷰 문서 #19. `service_family()` 가 의왕–부강 단독 구간을 `COMMON` 으로 분류했고,
`path_slot_capacity` 의 `service_family` 필터는 `GYEONGBU` / `SOUTHWEST` 만 매칭하므로
**56편이 선로용량 제약을 완전히 우회**했습니다. 의왕–부강은 경부선 본선으로 실제로는 가장 혼잡한 구간입니다.

수정:

```python
def service_family(path):
    ...
    return "TRUNK"        # COMMON -> TRUNK 로 명시

def family_matches(train_family, rule_family):
    """공유 trunk 서비스는 slot 규칙상 두 corridor 모두에 속한다."""
    if not rule_family: return True
    if train_family == "TRUNK":
        return rule_family in ("GYEONGBU", "SOUTHWEST", "TRUNK")
    return train_family == rule_family
```

이제 `service_family: "GYEONGBU"` 슬롯 규칙이 의왕–부강 trunk 열차도 함께 제한합니다.

### 7-3. 물리적 중복열차 conflict 제약 (신규, 항상 활성)

리뷰 문서 #20. v6.1 은 `UIWANG→BUGANG`, `UIWANG→YAKMOK`, `UIWANG→BUSAN` 을
같은 날 00:00 에 동시에 개설하는 것을 막지 않았습니다.

```
Σ_{p : origin(p)=i, dep_slot(p)=t}  y[p]  ≤  1              # 동일 거점·시각 출발
Σ_{p : e ∈ E_p, e ∈ TRUNK, dep_slot(p,e)=t}  y[p]  ≤  1     # 공유 trunk 동시 점유
```

`TRUNK` = 의왕–부강(양방향). **KORAIL 데이터 유무와 무관한 물리적 사실**이므로
optional 이 아니라 항상 적용하며, `OPERATIONAL_CONSTRAINT_AUDIT.csv` 에
`DEPARTURE_SLOT_CONFLICT` / `SHARED_TRUNK_CONFLICT` 로 기록합니다.

부수 효과로 모델이 조여져 solver 수렴이 빨라졌습니다.

---

## Phase 8 — 챗봇 UX

### 수정 전 문제

리뷰 문서 #21. 불가능한 조건이 들어오면 raw Python traceback 으로 죽었습니다.

```
RuntimeError: Stage1 failed: ...
ValueError: arrival window infeasible for NEED0012: earliest>48
ValueError: stale proposal_uuid for PROP0024
```

### 수정 내용

두 개의 구조화 예외를 도입했습니다.

**`AxisRequestError`** — 최적화 자체가 불가능하거나 solver 한계

```json
{
  "status": "INFEASIBLE",
  "reason_code": "NO_FEASIBLE_RAIL_SERVICE",
  "message": "현재 조건에서는 최소 consolidation 요건을 만족하는 신규 공컨 전용열차를 구성할 수 없습니다.",
  "detail": { "service_need_teu": 180, "service_need_count": 147,
              "max_earliness_hours": 24, "min_load_factor": 0.5 },
  "alternatives": [
    {"action": "LOWER_MIN_CONSOLIDATION_LEVEL", "current": 0.5, "note": "..."},
    {"action": "RELAX_MAX_EARLINESS", "current": 24, "note": "..."},
    {"action": "RELAX_LATEST_ARRIVAL", "note": "..."}
  ]
}
```

| reason_code | 조건 |
|---|---|
| `NO_FEASIBLE_RAIL_SERVICE` | 후보 assignment 가 0 |
| `SOLVER_LIMIT_REACHED` | 제한시간 내 최적성 미증명 |

**`PolicyValidationError`** — 재고정책 스키마 오류 (Phase 2, 오류코드 12종)

CLI `main()` 이 두 예외를 잡아 **JSON 을 stdout 으로 출력하고 exit code 2** 를 반환합니다.
raw traceback 은 나오지 않습니다.

### LLM 역할 경계

`alternatives` 는 **모델이 계산한 조정 가능한 축**만 제시합니다.
LLM 은 이 결과를 선사에게 설명할 뿐, 스스로 숫자나 새 열차안을 만들지 않습니다 (계획서 §45).

---

## 부수 개선 — 챗봇 예시 JSON 자동 생성

v6.1 의 `06_CHATBOT_EXAMPLES/*.json` 은 `proposal_uuid` 가 하드코딩되어 있어
PROPOSAL 을 재생성하면 전부 stale 이 되었습니다 (리뷰 문서 #2 의 실제 피해).

`02_CODE/make_negotiation_example.py` 가 **현재 PROPOSAL 산출물에서 예시를 생성**하므로
항상 유효합니다. 5개 action 유형을 모두 포함합니다.

```
CHATBOT_MIXED_NEGOTIATION.json: 24 actions
  {'ACCEPT_SERVICE': 10, 'ACCEPT_EXACT_PLAN': 4, 'MODIFY_SERVICE': 4,
   'REJECT_OPTION': 3, 'DECLINE_RAIL_SERVICE': 3}
CHATBOT_ACCEPT_ALL_SERVICE.json: 24 ACCEPT_SERVICE
```

---

## 남아있는 한계

1. **`SOLVER_LIMIT_REACHED` 는 근본 해결이 아닙니다.** 수요가 크게 늘면 다시 발생할 수 있으며,
   그때는 조기도착 상한을 조이거나 후보 열차 집합을 줄여야 합니다.
2. **conflict 제약은 "시간당 1편" 이라는 단순화** 입니다. 실제 선로용량은
   폐색구간·신호·기존 여객/화물 열차 다이어에 좌우되며, 그 데이터는 없습니다.
3. `NOT_APPLIED_NO_DATA` 는 구조가 구현되어 있음을 보증할 뿐,
   **실제 KORAIL 자원 제약을 반영했다는 뜻이 아닙니다.** 발표에서 혼동하면 안 됩니다.
4. 챗봇 자연어 → JSON 변환기(intent parser)는 이 패키지 범위 밖입니다.
   본 패키지는 **JSON 스키마와 구조화 응답까지** 제공합니다.
