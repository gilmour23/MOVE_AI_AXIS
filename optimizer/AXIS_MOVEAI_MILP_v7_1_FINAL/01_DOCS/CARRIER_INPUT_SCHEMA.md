# AXIS v7.1 — Carrier Input Schema

**각 선사는 자기 회사 데이터만 제출한다.**
한 선사가 다른 선사의 데이터를 함께 제출하는 구조가 아니다.

```text
Carrier A upload ─┐
Carrier B upload ─┤
Carrier C upload ─┤   각 선사가 자기 파일만 제출
      ...         ┤
Carrier F upload ─┘
                  ↓
        Input Validation / Normalization      (AXIS backend)
                  ↓
   AXIS internal carrier_hourly_plan table    (정규화된 내부 테이블)
                  ↓
             Joint MILP                        (여기서만 통합)
```

내부 통합 테이블 `AXIS_carrier_hourly_plan_v7_1.csv` 는 **AXIS backend 산출물**이며
선사가 이 형태로 제출하는 것이 아니다.

> 현재 패키지의 선사 데이터는 실제 운영데이터가 아니라
> **Synthetic Carrier-Level Data** 다. 실제 서비스에서는 이 layer 가 선사 제출 파일로 교체된다.

---

## 1. Planning Cycle

- 계획주기: **1주(168시간)**
- 모든 선사가 **동일 계획주기**에 제출한다.
- 시각: KST 로컬시각, 1시간 간격 (`01_DOCS/TIME_SLOT_CONVENTION.md`)

---

## 2. 선사 제출 파일 1 — 시간별 수요·공급

`CARRIER_SUBMISSION_TEMPLATE.csv`

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `carrier_id` | string | O | 제출 선사 ID (자기 회사만) |
| `timestamp` | `YYYY-MM-DD HH:MM` | O | 1시간 간격, 계획기간 전체 연속 |
| `hub_code` | string | O | `UIWANG` `BUGANG` `YAKMOK` `BUSAN` `DONGSAN` `GWANGYANG` |
| `container_size` | string | O | `20FT` `40FT` |
| `demand` | int ≥ 0 | O | 그 시간에 발생하는 공컨 픽업 수요(박스) |
| `supply_total` | int ≥ 0 | O | 그 시간에 가용해지는 공컨(반납 + 해상 반입) |
| `supply_return` | int ≥ 0 | 선택 | 참고용 내역 |
| `supply_sea_empty_inbound` | int ≥ 0 | 선택 | 참고용 내역 |

**행 수 = 168 × 6 hub × 2 size = 2,016행 (선사 1곳 기준)**

---

## 3. 선사 제출 파일 2 — 초기재고

`CARRIER_INITIAL_INVENTORY_TEMPLATE.csv`

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `carrier_id` | string | O | |
| `hub_code` | string | O | |
| `container_size` | string | O | |
| `initial_inventory` | int ≥ 0 | O | 계획기간 시작 시점 보유 공컨 |

**행 수 = 6 hub × 2 size = 12행 (선사 1곳 기준)**
`(carrier, hub, size)` 조합당 정확히 1행이어야 한다.

---

## 4. 검증 (`validate_carrier_inputs`)

제출 파일은 MILP 이전에 반드시 통과해야 한다.
실패 시 Python `KeyError` 가 아니라 **구조화된 오류**를 반환한다.

```json
{
  "status": "INVALID_INPUT",
  "reason_code": "CARRIER_INPUT_INVALID",
  "message": "선사 제출 데이터 검증에서 3건의 문제가 발견되었습니다.",
  "detail": { "error_count": 3 },
  "errors": [
    "hourly row 2: demand=-3 must be nonnegative",
    "hourly row 2: unknown hub_code 'SEOUL'",
    "incomplete carrier x hub x size x time grid: 12092 rows, expected 12096"
  ]
}
```

검증 항목

| 항목 | 내용 |
|---|---|
| 필수 컬럼 | 위 표의 필수 컬럼 존재 |
| 중복 | `(carrier_id, timestamp, hub_code, container_size)` 중복 금지 |
| 값 | `demand`, `supply_total`, `initial_inventory` 는 **음수·소수 금지** |
| 거점 | 허용 6개 hub 만 |
| 규격 | `20FT` / `40FT` 만 |
| 시간 연속성 | 1시간 간격으로 끊김 없음 |
| 완전성 | carrier × hub × size × time 조합 전부 존재 |
| 초기재고 | `(carrier, hub, size)` 당 정확히 1행 |
| 일관성 | hourly 의 carrier 집합 == initial 의 carrier 집합 |

CLI 에서 `--no-input-validation` 으로 끌 수 있으나 **권장하지 않는다.**

---

## 5. 데이터 privacy 원칙

- 선사는 **자기 데이터만** 제출한다.
- Joint MILP 는 AXIS backend 내부에서만 전 선사 데이터를 본다.
- 산출물은 선사별로 분리 제공한다.
  - `CARRIER_RECOMMENDATIONS_<CARRIER>.csv`
  - `RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv`
- 타 선사의 raw demand / supply / inventory / individual allocation 은 **노출하지 않는다.**
- 공동운송 사실은 집계정보로만 제공한다.
  - `participating_carrier_count`
  - `train_load_factor`

자동검증 `chat::carrier_context_isolation` 이 타 선사 유출을 검사한다.

---

## 6. 템플릿

```text
03_INPUT_DATA/templates/CARRIER_SUBMISSION_TEMPLATE.csv
03_INPUT_DATA/templates/CARRIER_INITIAL_INVENTORY_TEMPLATE.csv
```

한 선사(`CARRIER_A`) 기준 샘플이 들어 있다.

---

## 7. 내부 정규화 테이블

AXIS backend 는 제출 파일들을 합쳐 다음을 만든다.

```text
03_INPUT_DATA/AXIS_carrier_hourly_plan_v7_1.csv   (전 선사 통합, 12,096행)
03_INPUT_DATA/carrier_initial_inventory.csv        (전 선사 통합, 72행)
```

**MILP core 는 이 두 파일만 읽는다.**
synthetic 이든 실제 제출 데이터든 schema 가 같으면 코드 수정 없이 동작한다.
