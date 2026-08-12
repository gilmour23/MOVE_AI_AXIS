# Phase 9 감사 — 패키지 재현성

**대상 지시:** v7 수정 지시서 Phase 9
**판정:** 완료. 빈 폴더 재현 검증 통과, 전체 자동검증 **74/74 PASS**.

---

## 1. 수정 전 문제

리뷰 문서 #16, #17.

| 문서/코드가 전제한 경로 | 실제 폴더 |
|---|---|
| `code/` | `02_CODE/` |
| `input_data/` | `03_INPUT_DATA/` |
| `results/` | `05_RESULTS/` |
| `results/MODEL_INPUTS/` | `04_MODEL_INPUTS/` |
| `results/CHATBOT_*.json` | `06_CHATBOT_EXAMPLES/*.json` |

`RUN_COMMANDS.md` 의 모든 명령과 `verify_v6_1.py` 가 여기에 해당해
**패키지를 풀어서는 아무것도 실행되지 않았습니다.**
또 `verify` 가 요구하는 시나리오 폴더 7개 중 4개가 부재해
`102/102 PASS` 를 재현할 수 없었습니다.

---

## 2. 수정 내용

### 2-1. 경로 통일

`01_DOCS/RUN_COMMANDS.md` 와 `02_CODE/verify_v7.py` 를 **실제 폴더 구조 기준**으로 재작성했습니다.
패키지 루트에서 그대로 실행됩니다.

### 2-2. 실행 스크립트

```
run_data_generation.bat     Aggregate Master -> Virtual Carrier 분해
run_proposal.bat            KORAIL 제안 생성
run_demo_negotiation.bat    챗봇 협의 후 전체 재최적화
run_final.bat               확정 Commitment 만으로 최종 운영계획
run_baselines.bat           A/B/C 베이스라인 비교
run_sensitivity.bat         조기도착 / 적재율 / 하역시간 민감도
run_verification.bat        전체 자동검증
```

### 2-3. 검증 재현성

`verify_v7.py` 는 하드코딩 회귀값(`118`, `109`, `2편` 등)을 **쓰지 않습니다.**
대신 구조·불변식을 검사합니다.

- 총량보존, 거점 prior 상이성, 구조적 비대칭, 시간 연속성, 구조적 배제 없음
- 정수성, 기한/최조도착 준수, 구간 capacity, 최소적재율, 편성 선택
- carrier ownership 보존, source release capacity
- 거리 검증, 파라미터 출처 기록
- Phase 2 회귀(결정성 / NEED0039 / 정책 스키마)
- 베이스라인 A/B/C 존재 및 동일조건
- 민감도 3종 커버리지
- solver 전 stage status 0, 핵심 stage gap 0, tie-break stage 존재
- 운영제약 `NOT_APPLIED_NO_DATA` 명시, conflict 제약 적용
- 챗봇 구조화 오류, 정책 스키마 문서
- 패키지 구조·실행 스크립트 존재

데이터가 바뀌어도 검증이 깨지지 않고, **의미 있는 회귀만 잡습니다.**

### 2-4. 챗봇 예시 자동 생성

`02_CODE/make_negotiation_example.py` 가 현재 PROPOSAL 산출물에서 협의 예시를 만듭니다.
v6.1 은 `proposal_uuid` 가 하드코딩되어 PROPOSAL 재생성 시 전부 stale 이 되었습니다.

---

## 3. 빈 폴더 재현 검증

패키지를 새 폴더에 풀고 `05_RESULTS` / `07_VALIDATION` / `04_MODEL_INPUTS` 를 삭제한 뒤 실행:

| 단계 | 결과 |
|---|---|
| 데이터 생성 | **18/18 PASS** |
| 생성 데이터 해시 | 배포본과 **바이트 단위 완전 일치** (`270d0429ca5c8238…`) |
| PROPOSAL (48h) | served 90 TEU / 2편 / `all_stages_proven_optimal=true` |
| 잘못된 정책 JSON | 구조화 오류 JSON 출력, exit code 2 |

---

## 4. 최종 자동검증

```
VERIFICATION v7: 74/74 PASS
```

`07_VALIDATION/VERIFICATION_CHECKS_v7.csv`

Phase 2 회귀 테스트는 별도로 `07_VALIDATION/PHASE2_TESTS.csv` **29/29 PASS**.

---

## 5. 최종 패키지 구조

```
AXIS_MOVEAI_MILP_v7_FINAL/
├── 00_START_HERE.md
├── run_*.bat                      (7개)
├── 01_DOCS/
│   ├── MILP_FORMULATION_v7.md          수리모형 (코드 정본)
│   ├── INVENTORY_POLICY_SCHEMA.md      재고정책 JSON 정본
│   ├── RUN_COMMANDS.md                 실행 명령 (실제 경로)
│   ├── CHATBOT_NEGOTIATION_SCHEMA_v6_1.md
│   └── OPERATIONS_SCHEMA_v6_1.md / OPERATIONS_TEMPLATE_v6_1.json
├── 02_CODE/
│   ├── axis_data_gen_v7.py             Carrier 분해
│   ├── axis_params_v7.py               철도 파라미터 + 거리 검증
│   ├── axis_milp_v7.py                 MILP 본체
│   ├── axis_baselines_v7.py            A/B/C 베이스라인
│   ├── axis_sensitivity_v7.py          민감도
│   ├── make_negotiation_example.py     챗봇 예시 생성
│   ├── test_phase2_v7.py               회귀 테스트
│   └── verify_v7.py                    전체 검증
├── 03_INPUT_DATA/
│   ├── AXIS_hourly_empty_demand_supply_v8_6hubs.xlsx   Master Aggregate
│   ├── AXIS_carrier_hourly_plan_v7.csv                 12,096행
│   ├── carrier_initial_inventory.csv / carrier_profile_metadata.csv
│   ├── AGGREGATE_PRESERVATION_CHECK.csv / DATA_GENERATION_AUDIT.csv
│   ├── PUBLIC_SNAPSHOT_ANCHOR.csv / public_snapshot_2026-08-09.csv
│   └── AXIS_rail_OD_parameters_v1.xlsx
├── 04_MODEL_INPUTS/                    후보 시간표·편성 (생성물 사본)
├── 05_RESULTS/
│   ├── PROPOSAL / NEGOTIATION_MIXED / FINAL_MIXED / FINAL_ACCEPT_ALL
│   ├── C_AXIS_INTEGRATED / B_SEPARATE_CARRIER_A
│   ├── BASELINE_COMPARISON.csv/.json, BASELINE_NO_REPOSITIONING.csv,
│   │   BASELINE_CARRIER_SEPARATE.csv, AXIS_INTEGRATED_RESULT.csv
│   └── EARLINESS / LOAD_FACTOR / HANDLING_TIME _SENSITIVITY.csv
├── 06_CHATBOT_EXAMPLES/                협의 action + 재고정책 JSON
├── 07_VALIDATION/
│   ├── VERIFICATION_CHECKS_v7.csv      74/74
│   └── PHASE2_TESTS.csv                29/29
└── 08_AUDIT/
    ├── PHASE1_DATA_REDESIGN_AUDIT.md
    ├── PHASE2_P0_BUGFIX_AUDIT.md
    ├── PHASE3_BASELINE_AUDIT.md
    ├── PHASE4_TIME_REALISM_AUDIT.md
    ├── PHASE5_RAIL_PARAMETER_AUDIT.md
    ├── PHASE6_8_SOLVER_OPS_CHATBOT_AUDIT.md
    ├── PHASE9_PACKAGE_AUDIT.md
    └── v6_1_reference/                 v6.1 원본 데이터·결과 (회귀 테스트용)
```

`AXIS_MOVEAI_MILP_v7_FINAL.zip` (2.0 MB)

---

## 6. 버전 분리

지시서 §8 대로 기존 파일을 덮어쓰지 않았습니다.

```
AXIS_MOVEAI_HACKATHON_MILP_v6_1_PACKAGE/   원본 그대로 보존
AXIS_MOVEAI_MILP_v7_WORK/                  작업본
AXIS_MOVEAI_MILP_v7_FINAL/                 최종본
AXIS_MOVEAI_MILP_v7_FINAL.zip
```

v6.1 의 데이터·PROPOSAL 결과는 `08_AUDIT/v6_1_reference/` 에 보관되어
NEED0039 회귀 테스트가 계속 동작합니다.

---

## 7. 남아있는 한계

1. **전체 파이프라인 재실행에는 시간이 걸립니다** (조기도착 72h 기준 1~2시간).
   `--max-earliness 48` 이면 훨씬 빠릅니다(PROPOSAL 약 40초). `RUN_COMMANDS.md` 실행시간 표 참고.
2. **빈 폴더 재현 검증은 데이터 생성 + PROPOSAL(48h) + 정책 오류까지** 수행했습니다.
   전체 시나리오 재실행은 시간 관계로 배포본 결과를 그대로 포함했습니다.
3. `04_MODEL_INPUTS/` 는 `05_RESULTS/MODEL_INPUTS/` 의 사본입니다.
   코드는 `--root` 하위에 생성하므로 실행 시 `05_RESULTS/MODEL_INPUTS/` 가 정본입니다.
4. Windows `.bat` 만 제공합니다. 다른 OS 는 `RUN_COMMANDS.md` 의 명령을 직접 사용합니다.
