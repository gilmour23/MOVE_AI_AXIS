# AXIS MOVE-AI MILP v7.1

**Joint Multi-Carrier Optimization + Read-only AI Explanation**

---

## 프로젝트 설명

> AXIS는 각 선사가 제출한 거점별·시간별·규격별 공컨 재고·수요·공급 계획과 KORAIL의 운행 가능한
> 철도 서비스 후보를 통합하여, 복수 선사의 공컨 재배치 수요를 하나의 MILP에서 공동 최적화하는 시스템이다.
>
> 최적화 결과는 동일 solution을 기반으로 선사에게는 회사별 권장 공컨 철도운송계획을,
> KORAIL에는 복수 선사의 물량이 통합된 열차 운영계획을 제공한다.
>
> 현재 프로젝트에서는 실제 선사 운영데이터와 실제 신규 열차 path 데이터를 확보할 수 없어
> synthetic carrier data와 prototype timetable을 사용하며, 향후 실제 선사 제출 데이터와
> KORAIL 운행가능 path input으로 교체 가능한 구조로 설계한다.
>
> 챗봇은 MILP를 수정하거나 재최적화하는 기능이 아니라, 산출된 운송계획의 근거·시각·수량·운임·
> 재고효과 등을 설명하는 read-only Q&A interface로 사용한다.

---

## 운영 흐름

```text
Carrier A ── A사 Inventory / Demand / Supply ──┐
Carrier B ── B사 Inventory / Demand / Supply ──┤
Carrier C ── C사 Inventory / Demand / Supply ──┤
Carrier D ── D사 Inventory / Demand / Supply ──┤
Carrier E ── E사 Inventory / Demand / Supply ──┤
Carrier F ── F사 Inventory / Demand / Supply ──┘
                                               ↓
                                      AXIS Planning Cycle
                                               +
                                 KORAIL Operational Inputs
                                 - 운행 가능한 시간대 / 경로 / 열차 후보
                                 - 편성 가능조건
                                 - (선택) 선로·화차·기관차 자원 제약
                                               ↓
                                     Joint Multi-Carrier MILP
                                               ↓
                     ┌─────────────────────────┴─────────────────────────┐
                     ↓                                                   ↓
         Carrier Recommendation                            KORAIL Operation Plan
         AXIS 권장 공컨 재배치 계획                        통합 신규 열차 운행계획
                                               ↓
                              Read-only Chatbot Explanation
```

두 산출물은 서로 다른 최적화 결과가 아니라 **동일 MILP solution 의 두 관점**이다.
매 실행마다 `SUMMARY.json:carrier_korail_view_consistent` 로 물량 합계 일치를 검증한다.

---

## 핵심 원칙

- **선사별 공컨 ownership 엄격 유지.** A사 재고는 A사 수요에만 사용된다.
- 선사 간 공유되는 것은 재고가 아니라 **KORAIL 철도 capacity** 이다.
  여러 선사의 공컨을 같은 열차에 공동 적재할 수 있다.
- **선사별 개별 최적화 후 합산이 아니다.** 같은 planning cycle 에 제출된 모든 Service Need 를
  하나의 MILP 에서 동시에 고려한다. 이 multi-carrier consolidation 이 AXIS 의 핵심 기능이다.
- MILP 는 임의의 열차 시각을 만들지 않는다. **KORAIL 이 제공하는 운행가능 후보 중에서** 선택한다.

---

## 실행

```bash
pip install numpy scipy pandas openpyxl
```

```text
run_all.bat                 전체 파이프라인 일괄 실행
  ├─ run_data_generation.bat   1. Aggregate Master -> Synthetic Carrier-Level Data
  ├─ run_axis_integrated.bat   2. Joint Multi-Carrier MILP (one-shot)
  ├─ run_baselines.bat         3. A/B/C 연구용 베이스라인
  ├─ run_sensitivity.bat       4. 조기도착 / 적재율 / 하역시간 민감도
  ├─ run_tests.bat             5. 자립 회귀 테스트
  └─ run_verification.bat      6. 전체 검증 (코드 재실행 포함)

run_policy_example.bat      선사 사전 재고정책 입력 예시
```

Windows 가 아니면 `01_DOCS/RUN_COMMANDS.md` 의 명령을 그대로 사용한다.

### 정본 실행 파라미터

```text
min_load_factor = 0.5      Minimum Consolidation Level Scenario
max_earliness   = 72 h     조기도착 상한
time_limit      = 900 s    lexicographic stage 당
```

> **이 값들은 KORAIL 공식 운영기준이 아니라 scenario assumption 이다.**
> 근거와 민감도는 `05_RESULTS/SENSITIVITY/` 와 `08_AUDIT/` 참조.

---

## 폴더

| 폴더 | 내용 |
|---|---|
| `01_DOCS` | 수리모형(v7.1), 재고정책 스키마, 실행명령, 운영제약 스키마 |
| `02_CODE` | 데이터 생성 / 파라미터 / Joint MILP / 베이스라인 / 민감도 / 테스트 / 검증 |
| `03_INPUT_DATA` | Master Aggregate, 선사 제출 데이터(현재 synthetic), 공개자료, OD 파라미터 |
| `05_RESULTS` | `AXIS_INTEGRATED` / `BASELINES` / `SENSITIVITY` / `VALIDATION` |
| `06_POLICY_EXAMPLES` | 선사 사전 재고정책 JSON 예시 |
| `08_AUDIT` | v7→v7.1 변경내역, 구현감사, 재현성감사, v7 단계별 감사 |
| `future_extensions/negotiation_legacy` | 제거한 협상 계층 참고 구현 (**데모·검증에 사용하지 않음**) |

---

## 먼저 볼 파일

1. `01_DOCS/MILP_FORMULATION_v7_1.md` — 수리모형
2. `05_RESULTS/AXIS_INTEGRATED/CARRIER_RECOMMENDATIONS.csv` — 선사 관점
3. `05_RESULTS/AXIS_INTEGRATED/KORAIL_TRAIN_PLAN.csv` — KORAIL 관점
4. `05_RESULTS/BASELINES/BASELINE_COMPARISON.csv` — AXIS 통합효과
5. `08_AUDIT/V7_TO_V7_1_CHANGELOG.md` — 무엇을 왜 제거했는지
6. `05_RESULTS/VALIDATION/VERIFICATION_CHECKS_v7_1.csv` — 전체 검증

---

## 챗봇의 역할

챗봇은 **최적화 controller 가 아니라 read-only Explanation / Q&A Layer** 이다.

조회 가능한 데이터

```text
Carrier Recommendation / Recommendation Explanation Context
Service Need / Carrier inventory forecast
Train Assignment / KORAIL Train Plan / Segment Load
Estimated Rail Fare
```

답할 수 있는 질문 예

```text
왜 약목으로 공컨을 보내는 거야?      왜 부산신항에서 출발해?
왜 8개야?                            언제 출발하고 언제 도착해?
어떤 열차에 실려?                    열차 적재율은?
몇 개 선사가 공동 운송해?            약목 예상재고는 어떻게 달라져?
```

챗봇이 하면 안 되는 것

```text
MILP 변수 수정 / constraint 변경 / 재최적화
새로운 수량·열차 생성 / Carrier allocation 변경
```

`RECOMMENDATION_EXPLANATION_CONTEXT.csv` 에는 **계산된 값만** 들어 있다.
LLM 이 숫자를 임의로 생성하면 안 된다.

---

## 중요한 가정 — 발표 시 반드시 함께 말할 것

### 데이터

- 현재 선사별 데이터는 **Synthetic Carrier-Level Data** 이며 실제 선사 운영데이터가 아니다.
- 총 수요·공급 총량과 시간패턴은 Aggregate Master Data 를 **정확히 보존**한다 (자동검증).
- `CARRIER_A`~`CARRIER_F` 는 익명 Virtual Carrier 다. 공개자료의 점유율 *shape* 만 차용했으며
  특정 실제 선사나 전국 시장점유율을 의미하지 않는다.
- PNC / KITL 공개자료는 2026-08-09 **단일 시점 snapshot** 이며 정의가 서로 다르다.
  절대값을 합치거나 전국 점유율로 해석하면 안 된다.
- 거점 혼합계수 λ, 역할 tilt 는 scenario parameter 다.

### 모델

- Candidate timetable 은 **PROTOTYPE_SYNTHETIC** 이며 KORAIL 실제 운행가능 train path 가 아니다.
  `TRAIN_CANDIDATE.csv` 의 `candidate_source` 컬럼에 표시된다.
- **Minimum Consolidation Level 은 KORAIL 공식 손익분기 적재율이 아니다.**
  0.5 / 0.6 / 0.7 민감도를 함께 제시한다.
- 33/40/50량 편성은 scenario option 이며 노선별 실제 운행가능성은 검증되지 않았다.
- **내부 운영원가 데이터가 없으므로 실제 수익성은 주장하지 않는다.**
  운영 KPI 는 Train Count / Train-km / Wagon-km / TEU-km / Load Factor /
  Tariff 기반 예상수입으로 한정한다.
- 본 모델은 **편도 계획모형**이다. 화차 회송은 포함되지 않는다
  (`return_wagon_movement_included = false`).
- Path slot / 화차 / 기관차 가용량 제약은 구조가 구현되어 있으며 실제 값이 없으면
  `NOT_APPLIED_NO_DATA` 로 명시 기록된다.

### 재현성

- 동일 code / input / parameter / seed 이면 결과가 **완전히 동일**하다
  (lexicographic 마지막 deterministic tie-break stage).
- 모든 solver stage 의 status·gap·runtime 이 `SOLVER_AUDIT.csv` 에 남는다.
  최적성을 증명하지 못한 stage 가 있으면 결과를 내지 않고 중단한다.

---

## 연구 범위

> 각 선사가 개별적으로 철도운송을 구성하는 경우와 비교했을 때,
> 여러 선사의 공컨 재배치 수요를 공동화하면
> KORAIL 의 신규 공컨 철도서비스 구성 가능성과 운영효율이 어떻게 달라지는가?

**범위 밖** — Carrier negotiation / acceptance behavior / pricing negotiation /
commercial contract / iterative counterproposal / reservation process.

Canonical pipeline also runs `run_role_tilt_sensitivity.bat` and uses
`04_MODEL_INPUTS` with strict lexicographic solving for the 72-hour integrated run.
상용화 단계의 운영 프로세스로 분리한다.
