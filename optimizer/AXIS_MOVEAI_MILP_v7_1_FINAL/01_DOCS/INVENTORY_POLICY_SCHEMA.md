# AXIS Inventory Policy Schema v7.1 — 정본

이 문서가 **선사 재고정책 JSON 의 유일한 정본**이다.

> **v7.1 주의:** 재고정책은 계획 실행 **전에** 선사가 제출하는 입력조건이다.
> Proposal 이후의 사후 협상(negotiation) 기능이 아니다.
> `Carrier Planning Input → Service Need → Joint Optimization` 단계에서 사용된다.
프로젝트 통합계획 v3 §26~§30, §69 와 코드 `02_CODE/axis_milp_v7_1.py` 는 이 문서를 따른다.

> **v6.1 문제:** 계획서 §69 형식(`rule_type`, `hub`)과 코드 형식(`type`, `hub_code`)이 달랐고,
> 코드가 인식하지 못하는 정책을 **경고 없이 건너뛰었다.**
> 계획서대로 만든 JSON 을 넣어도 결과가 전혀 바뀌지 않는데 에러도 나지 않았다.
>
> **v7 원칙:** 알 수 없는 `rule_type`, 알 수 없는 key, 필수 field 누락은 **전부 hard error** 다.
> 조용한 skip 은 존재하지 않는다.

---

## 1. 파일 형식

```json
{
  "inventory_policies": [ { ...rule... }, { ...rule... } ]
}
```

CLI:

```bash
python 02_CODE/axis_milp_v7_1.py ... --policies 06_POLICY_EXAMPLES/POLICY_MIN_INVENTORY_RANGE.json
```

---

## 2. 공통 field

| field | 타입 | 필수 | 설명 |
|---|---|---|---|
| `rule_id` | string | 선택 | 미지정 시 `POL-001` 형태로 자동부여 |
| `carrier_id` | string | **필수** | 입력 데이터에 존재하는 선사여야 함 |
| `rule_type` | string | **필수** | §3 참조 |
| `hub_code` | string | **필수** | `UIWANG` `BUGANG` `YAKMOK` `BUSAN` `DONGSAN` `GWANGYANG` |
| `container_size` | string | **필수** | `20FT` 또는 `40FT` |
| `value` | integer | **필수** | 0 이상의 정수 (박스 수) |
| `hard_constraint` | bool | 선택 | v7 은 `true` 만 지원. `false` 는 hard error |
| `note` | string | 선택 | 자유 메모. 최적화에 영향 없음 |

시각 형식은 전부 `"YYYY-MM-DD HH:MM"` 이며 **계획기간(168시간) 안**이어야 한다.

> `hub` / `type` / `time` 은 **v6.1 legacy key 이며 v7 에서 오류**다.
> `rule_type` 이 없고 `type` 이 있으면 오류 메시지가 그 사실을 알려준다.

---

## 3. 지원하는 rule_type

### 3-1. `MIN_INVENTORY_AT_TIME` — 특정 시점 최소 확보량 (계획서 Policy Type B)

> "금요일 18시까지 부산신항에 20FT 50개 확보해줘"

| 추가 field | 필수 | 설명 |
|---|---|---|
| `target_time` | **필수** | 해당 시각 |

```json
{
  "rule_id": "POL-001",
  "carrier_id": "CARRIER_A",
  "rule_type": "MIN_INVENTORY_AT_TIME",
  "hub_code": "BUSAN",
  "container_size": "20FT",
  "target_time": "2026-08-14 18:00",
  "value": 50,
  "hard_constraint": true
}
```

모델 처리: 해당 시점의 재고 하한을 올려 Service Need 를 추가 생성한다.

---

### 3-2. `MIN_INVENTORY_RANGE` — 기간 최소 재고 (계획서 Policy Type A)

> "이번 주 약목 40FT는 최소 10개를 유지해줘"

| 추가 field | 필수 | 기본값 |
|---|---|---|
| `start_time` | 선택 | 계획기간 시작 |
| `end_time` | 선택 | 계획기간 종료 |

```json
{
  "rule_id": "POL-002",
  "carrier_id": "CARRIER_A",
  "rule_type": "MIN_INVENTORY_RANGE",
  "hub_code": "YAKMOK",
  "container_size": "40FT",
  "start_time": "2026-08-13 00:00",
  "end_time": "2026-08-16 23:00",
  "value": 10,
  "hard_constraint": true
}
```

---

### 3-3. `MAX_INVENTORY` — 최대 재고 / 장치능력 (계획서 Policy Type C)

> "동산 20FT는 80개 이상 쌓이지 않게 해줘"

| 추가 field | 필수 | 기본값 |
|---|---|---|
| `start_time` | 선택 | 계획기간 시작 |
| `end_time` | 선택 | 계획기간 종료 |

```json
{
  "rule_id": "POL-003",
  "carrier_id": "CARRIER_C",
  "rule_type": "MAX_INVENTORY",
  "hub_code": "DONGSAN",
  "container_size": "20FT",
  "value": 80,
  "hard_constraint": true
}
```

**모델 처리 (중요):** v7 MILP 는 재고를 결정변수로 갖지 않는다.
따라서 다음 형태로 부과한다.

```
baseline_stock[c,h,k,t] + Σ(도착 x with dest=h, arr_slot ≤ t)  ≤  value
```

여기서 `baseline_stock` 은 철도 재배치가 없을 때의 물리 재고다.
즉 **"철도로 들여올 수 있는 총량"의 상한**으로 작동하며,
목적지 장치장 점유를 제한하는 용도로 정확하다.

---

### 3-4. `ORIGIN_RELEASE_RESTRICTION` — 거점 반출 제한 (계획서 Policy Type E)

> v7 의 `BLOCK_OUTBOUND` 는 호환 별칭으로 계속 허용된다.

> "이번 주 부산신항에서 40FT는 100개 이상 빼지 마"

| 추가 field | 필수 | 기본값 |
|---|---|---|
| `start_time` | 선택 | 계획기간 시작 |
| `end_time` | 선택 | 계획기간 종료 |

```json
{
  "rule_id": "POL-004",
  "carrier_id": "CARRIER_A",
  "rule_type": "ORIGIN_RELEASE_RESTRICTION",
  "hub_code": "BUSAN",
  "container_size": "40FT",
  "value": 100,
  "hard_constraint": true
}
```

모델 처리:

```
Σ(출발 x with origin=h, carrier=c, size=k, start ≤ dep_slot ≤ end)  ≤  value
```

`value: 0` 이면 해당 거점에서의 반출을 완전 차단한다.

---

## 4. 지원하지 않는 rule_type

| rule_type | 상태 | 사유 |
|---|---|---|
| `TARGET_INVENTORY` | **미구현** | 계획서 Policy Type D(soft target). v7 MVP 범위 밖 |

`TARGET_INVENTORY` 를 넣으면 다음 오류가 난다.

```json
{
  "status": "INVALID_POLICY",
  "reason_code": "RULE_TYPE_NOT_IMPLEMENTED",
  "message": "rule_type 'TARGET_INVENTORY' is defined in the schema but not implemented in v7",
  "detail": { "implemented": ["MAX_INVENTORY","MIN_INVENTORY_AT_TIME","MIN_INVENTORY_RANGE","ORIGIN_RELEASE_RESTRICTION"] }
}
```

**자연어 대응 지침:** "25개 정도로 맞춰줘" 같은 soft 표현은 챗봇이 사용자에게
`MIN_INVENTORY_AT_TIME`(최소 보장) 인지 `MAX_INVENTORY`(상한) 인지 되물어 확정한 뒤 전달한다.
LLM 이 임의로 soft target 을 hard 제약으로 바꿔 넣으면 안 된다.

---

## 5. 오류 코드

전부 `PolicyValidationError` 로 발생하며 `as_dict()` 로 구조화된다.

| reason_code | 발생 조건 |
|---|---|
| `SCHEMA_TYPE_ERROR` | `inventory_policies` 가 list 가 아니거나 원소가 object 가 아님 |
| `MISSING_FIELD` | `rule_type` 등 필수 field 누락 (legacy key 발견 시 안내 포함) |
| `UNKNOWN_RULE_TYPE` | 정의되지 않은 `rule_type` |
| `RULE_TYPE_NOT_IMPLEMENTED` | 스키마에는 있으나 v7 미구현 (`TARGET_INVENTORY`) |
| `UNKNOWN_FIELD` | 해당 `rule_type` 에 허용되지 않는 key |
| `UNKNOWN_CARRIER` / `UNKNOWN_HUB` / `UNKNOWN_CONTAINER_SIZE` | 입력 데이터에 없는 값 |
| `BAD_VALUE` | `value` 가 정수가 아니거나 음수 |
| `BAD_TIME_FORMAT` | 시각 형식 오류 |
| `TIME_OUTSIDE_HORIZON` | 계획기간 밖 시각 |
| `BAD_TIME_RANGE` | `start_time > end_time` |
| `SOFT_CONSTRAINT_NOT_SUPPORTED` | `hard_constraint: false` |

응답 예:

```json
{
  "status": "INVALID_POLICY",
  "reason_code": "TIME_OUTSIDE_HORIZON",
  "message": "'target_time' is outside the planning horizon",
  "rule": { "...": "..." },
  "detail": { "got": "2026-09-01 18:00",
              "horizon": ["2026-08-10 00:00", "2026-08-16 23:00"] }
}
```

챗봇은 이 구조를 그대로 받아 선사에게 설명한다.
**LLM 이 숫자를 지어내거나 대체 정책을 임의로 만들면 안 된다** (계획서 §45).

---

## 6. 출력물

| 파일 | 내용 |
|---|---|
| `ACTIVE_POLICY.json` | 정규화되어 실제 적용된 정책 목록 (계획서 §56 `ACTIVE_POLICY`) |
| `INVENTORY_POLICY_AUDIT.csv` | 각 정책이 실제로 제약 몇 개를 만들었는지 |
| `SUMMARY.json` → `active_policy_count` | 적용된 정책 수 |

정책을 넣었는데 `active_policy_count` 가 0 이면 **JSON 이 조용히 무시된 것이 아니라
파일이 전달되지 않은 것**이다 (v7 에서 무시는 불가능하다).

---

## 7. 챗봇 연동 (계획서 §35~§39)

```text
선사 자연어
  → LLM 이 위 스키마의 JSON 생성
  → UI 에 해석 결과 표시, 사용자 "적용" 확인 (계획서 §46)
  → Backend 가 이 스키마로 검증
  → 실패 시 reason_code 로 되물음
  → 성공 시 MILP 재실행
```

LLM 은 **JSON 생성까지만** 한다. 열차·출발거점·편성은 MILP 가 결정한다.
