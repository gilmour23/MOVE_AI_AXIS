# AXIS v7.1 실행 명령

모든 경로는 **이 패키지의 실제 폴더 구조** 기준이며, 패키지 루트에서 실행한다.
Windows 는 동봉된 `run_*.bat` 을 그대로 사용해도 된다.

```bash
pip install numpy scipy pandas openpyxl
```

## 정본 실행 파라미터

```text
min_load_factor = 0.5      Minimum Consolidation Level Scenario
max_earliness   = 72 h
time_limit      = 900 s    lexicographic stage 당
```

> **KORAIL 공식 운영기준이 아니라 scenario assumption 이다.**

---

## 1. 데이터 생성 — Aggregate Master → Synthetic Carrier-Level Data

```bash
python 02_CODE/axis_data_gen_v7_1.py \
  --master 03_INPUT_DATA/AXIS_hourly_empty_demand_supply_v8_6hubs.xlsx \
  --snapshot 03_INPUT_DATA/public_snapshot_2026-08-09.csv \
  --outdir 03_INPUT_DATA
```

총량보존 검증이 1건이라도 실패하면 exit code 1 로 중단된다.

옵션: `--seed 20260810` `--role-tilt 1.10` `--rho 0.75` `--sigma 0.10`

> 실제 서비스에서는 이 단계가 사라지고 **선사가 직접 제출한 CSV** 를 그대로 사용한다.

---

## 2. Joint Multi-Carrier MILP (one-shot)

```bash
python 02_CODE/axis_milp_v7_1.py \
  --hourly 03_INPUT_DATA/AXIS_carrier_hourly_plan_v7_1.csv \
  --initial 03_INPUT_DATA/carrier_initial_inventory.csv \
  --params 03_INPUT_DATA/AXIS_rail_OD_parameters_v1.xlsx \
  --candidates 04_MODEL_INPUTS \
  --root 05_RESULTS --scenario AXIS_INTEGRATED \
  --min-load-factor 0.5 --max-earliness 72 --time-limit 900 \
  --strict-lexicographic
```

산출: `05_RESULTS/AXIS_INTEGRATED/`

- 선사 관점 `CARRIER_RECOMMENDATIONS.csv`, `CARRIER_RECOMMENDATION_DETAIL.csv`,
  `CARRIER_RECOMMENDATIONS_<CARRIER>.csv`, `RECOMMENDATION_EXPLANATION_CONTEXT.csv`
- KORAIL 관점 `KORAIL_TRAIN_PLAN.csv`, `CARRIER_ALLOCATION.csv`,
  `STOP_WORK_PLAN.csv`, `SEGMENT_LOAD.csv`
- 감사 `SOLVER_AUDIT.csv`, `OPERATIONAL_CONSTRAINT_AUDIT.csv`,
  `RAIL_PARAMETER_PROVENANCE.csv`, `DISTANCE_VALIDATION.csv`

---

## 3. 연구용 베이스라인 (A / B / C)

```bash
python 02_CODE/axis_baselines_v7_1.py \
  --hourly 03_INPUT_DATA/AXIS_carrier_hourly_plan_v7_1.csv \
  --initial 03_INPUT_DATA/carrier_initial_inventory.csv \
  --params 03_INPUT_DATA/AXIS_rail_OD_parameters_v1.xlsx \
  --root 05_RESULTS/BASELINES \
  --candidates 04_MODEL_INPUTS \
  --min-load-factor 0.5 --max-earliness 72 --time-limit 900
```

`--candidates` 로 AXIS_INTEGRATED 와 **동일한 후보 시간표**를 공유해 동일조건 비교를 보장한다.

---

## 4. 민감도

```bash
python 02_CODE/axis_sensitivity_v7_1.py \
  --hourly 03_INPUT_DATA/AXIS_carrier_hourly_plan_v7_1.csv \
  --initial 03_INPUT_DATA/carrier_initial_inventory.csv \
  --params 03_INPUT_DATA/AXIS_rail_OD_parameters_v1.xlsx \
  --root 05_RESULTS/SENSITIVITY \
  --base-earliness 72 --base-lf 0.5 --base-handling 3 --time-limit 900
```

`--which earliness|loadfactor|handling` 로 개별 실행 가능.

---

## 5. 선사 사전 재고정책 입력

```bash
python 02_CODE/axis_milp_v7_1.py \
  ... \
  --policies 06_POLICY_EXAMPLES/POLICY_MIN_INVENTORY_RANGE.json \
  --scenario AXIS_INTEGRATED_WITH_POLICY
```

스키마는 `01_DOCS/INVENTORY_POLICY_SCHEMA.md`.
잘못된 정책은 조용히 무시되지 않고 구조화된 오류(exit code 2)를 낸다.

---

## 6. 상하차시간 조정

```bash
  --origin-loading-h 3 --intermediate-handling-h 3 --destination-unloading-h 3
```

기본값은 코레일 화물운송약관의 적재·하화 제한시간 3시간이다.

---

## 7. KORAIL 실제 운영자원 제약 (데이터가 있을 때만)

```bash
  --operations 01_DOCS/OPERATIONS_TEMPLATE_v7_1.json
```

값이 없으면 넣지 않는다. 비활성 상태는 `OPERATIONAL_CONSTRAINT_AUDIT.csv` 에
`NOT_APPLIED_NO_DATA` 로 명시 기록된다.

---

## 8. KORAIL 실제 운행가능 path 로 교체

```bash
  --candidates <KORAIL_FEASIBLE_PATH_DIR>
```

해당 디렉터리에 `TRAIN_CANDIDATE.csv`, `TRAIN_STOP_TIME.csv`,
`TRAIN_SEGMENT.csv`, `TRAIN_FORMATION_OPTION.csv` 를 두고
`TRAIN_CANDIDATE.csv` 의 `candidate_source` 를 `KORAIL_FEASIBLE_PATH` 로 표기한다.

**MILP core 는 수정하지 않는다.**

---

## 9. 테스트 · 검증

```bash
python 02_CODE/test_v7_1.py       # 자립 회귀 테스트 (과거 결과 의존 없음)
python 02_CODE/verify_v7_1.py .   # 전체 검증 (데이터 생성·MILP·테스트 재실행 포함)
python 02_CODE/verify_v7_1.py . --quick   # MILP 재실행을 48h 로 단축
```

결과는 `05_RESULTS/VALIDATION/` 에 저장된다.

---

## 실행 시간 참고 (Intel 데스크톱 기준)

| 명령 | 대략 |
|---|---|
| 데이터 생성 | 20초 |
| Joint MILP (72h) | 6~13분 |
| 베이스라인 A/B/C | 15~25분 |
| 민감도 11종 | 30~45분 |
| 회귀 테스트 | 4~6분 |
| 전체 검증 | 15~25분 (`--quick` 시 8~12분) |

`--max-earliness 48` 이면 훨씬 빠르다 (Joint MILP 약 40초).
모든 lexicographic stage 가 최적성을 증명해야 결과가 나오므로,
`--time-limit` 을 줄이면 결과 대신 `SOLVER_LIMIT_REACHED` 구조화 오류가 반환된다.
