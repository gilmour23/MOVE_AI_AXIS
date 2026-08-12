# V7 → V7.1 CHANGELOG

**작업 성격:** 기능 추가가 아니라 **AXIS 모델 범위를 정확히 정리하는 구조 작업**
**대상:** `AXIS_MOVEAI_MILP_v7_FINAL` → `AXIS_MOVEAI_MILP_v7_1_FINAL`

---

## 1. 현재 서비스 구조 (확정)

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
                                 (운행가능 시간대·경로·열차후보·편성조건·선로자원)
                                               ↓
                                     Joint Multi-Carrier MILP
                                               ↓
                     ┌─────────────────────────┴─────────────────────────┐
                     ↓                                                   ↓
         Carrier Recommendation                            KORAIL Operation Plan
         선사별 권장 공컨 이동계획                          통합 신규 열차 운행계획
                                               ↓
                              Read-only Chatbot Explanation
```

두 산출물은 서로 다른 최적화 결과가 아니라 **동일 solution 의 두 관점**이며,
`SUMMARY.json:carrier_korail_view_consistent` 로 물량 합계 일치를 매 실행마다 검증한다.

---

## 2. 제거한 기능

### 2-1. 실행 상태기계

| v7 | v7.1 |
|---|---|
| `PROPOSAL` → `NEGOTIATION` → `FINAL` 3단계 | **one-shot** 단일 실행 |
| `--run-mode` | 제거 |
| `--proposal-reference`, `--actions` | 제거 |

### 2-2. 협상 action

전부 제거했다.

```text
ACCEPT_SERVICE          ACCEPT_EXACT_PLAN       DECLINE_RAIL_SERVICE
MODIFY_SERVICE          REJECT_OPTION
CHANGE_QUANTITY         CHANGE_LATEST_ARRIVAL   SET_EARLIEST_ARRIVAL
SET_MAX_EARLINESS       BLOCK_ORIGIN            ALLOW_ORIGIN
```

### 2-3. 협상 상태 개념

```text
proposal_version        negotiation_round       parent_proposal_id
commitment              counterproposal         stale proposal 검증
accepted / declined     carrier commitment state
korail_confirmed_committed_teu / commitment_confirmation_rate
```

### 2-4. 제거된 코드·출력

| 항목 | 조치 |
|---|---|
| `load_negotiation()`, `_proposal_allocations()`, `_action_constraints()` | 삭제 |
| `create_accept_all_actions()`, `diagnose_commitment_conflict()` | 삭제 |
| `make_negotiation_example.py` | legacy 이동 |
| `CHATBOT_MIXED_NEGOTIATION.json`, `CHATBOT_ACCEPT_ALL_SERVICE.json` | legacy 이동 |
| `05_RESULTS/NEGOTIATION_MIXED`, `FINAL_MIXED`, `FINAL_ACCEPT_ALL` | legacy 이동 |
| `CHATBOT_NEGOTIATION_SCHEMA_v6_1.md` | legacy 이동 |
| 챗봇 `additional_needs` (수량조정으로 Need 추가) | 삭제 |

참고용 v7 구현 전체는 `future_extensions/negotiation_legacy/` 에 보관했다.
**main execution flow / README / verification / demo / output 에서는 사용하지 않는다.**

---

## 3. 용어 변경

| v7 | v7.1 |
|---|---|
| Carrier Proposal | **Carrier Recommendation** |
| `CARRIER_PROPOSALS.csv` | `CARRIER_RECOMMENDATIONS.csv` |
| `CARRIER_PROPOSAL_DETAIL.csv` | `CARRIER_RECOMMENDATION_DETAIL.csv` |
| `proposal_id` | `recommendation_id` |
| `quantity` / `teu` | `quantity_boxes` / `quantity_teu` |
| `origin` / `destination` | `origin_hub` / `destination_hub` |

한국어 UI 표기: **AXIS 권장 공컨 철도운송안 / AXIS 권장 공컨 재배치 계획**

"Proposal" 은 선사의 수락을 기다리는 견적처럼 읽히므로 사용하지 않는다.

---

## 4. 유지한 기능 (v7 개선사항 롤백 금지 항목)

전부 그대로 유지되며 회귀 테스트로 고정되어 있다.

### 데이터
- demand / supply share structural asymmetry (역할 기반 tilt)
- aggregate demand / supply / initial inventory 총량보존
- 6개 거점 고유 prior (λ 차별화)
- calibration metadata (`source_type` / `source_note` / `lambda_value` / `random_seed`)
- 시간 연속성 AR(1), 이월 배분기(소형선사 구조적 배제 방지)

### 모델
- carrier-specific service need
- carrier ownership 엄격 분리
- source release capacity (상차 개시 시각 기준)
- integer container assignment
- candidate train selection / formation selection
- segment capacity, minimum consolidation scenario
- route / time / due-time compatibility
- intermediate pickup / drop-off
- physical / tariff 거리 분리 + runtime 검증
- handling time 분리 (상차 3h / 중간 3h / 하화 3h)
- 물리적 중복열차 conflict 제약 (departure slot / shared trunk)
- optional path slot / wagon / locomotive capacity

### Solver
- deterministic tie-break stage (Z7)
- stage별 status / gap / objective / runtime 감사
- Z1·Z2 `mip_rel_gap = 0` proven optimum 요구
- time-limit 종료를 최적해로 취급하지 않음

### 비교·민감도
- No Repositioning / Carrier Separate / AXIS Integrated
- earliness / load factor / handling time 민감도

---

## 5. 새로 추가한 것

| 항목 | 내용 |
|---|---|
| `CARRIER_ALLOCATION.csv` | KORAIL 관점 열차별 선사 배분 |
| `RECOMMENDATION_EXPLANATION_CONTEXT.csv` | 챗봇 read-only 설명 근거 (계산된 값만) |
| `CARRIER_RECOMMENDATIONS_<CARRIER>.csv` | 선사별 격리 파일 (타 선사 정보 없음) |
| `candidate_source` 컬럼 | `PROTOTYPE_SYNTHETIC` / `KORAIL_FEASIBLE_PATH` |
| `--candidates` 옵션 | KORAIL feasible path 디렉터리 교체 지점 |
| `carrier_korail_view_consistent` | 두 관점 물량 일치 자동 검증 |
| `ORIGIN_RELEASE_RESTRICTION` | 정책 rule_type 정본 명칭 (`BLOCK_OUTBOUND` 는 호환 별칭) |
| `run_all.bat` | 전체 파이프라인 일괄 실행 |

---

## 6. 실행 결함 수정 (지시서 18)

### 18.1 실행 default 통일

```text
max_earliness   = 72 h
min_load_factor = 0.5
time_limit      = 900 s
```

CLI 기본값 · 모든 `.bat` · `RUN_COMMANDS.md` · `00_START_HERE.md` 를 통일했다.
**KORAIL 공식 운영기준이 아니라 scenario assumption** 임을 각 파일에 명시했다.

### 18.2 run_baselines.bat 제어문자

v7 의 `run_baselines.bat` 에 BEL(`0x07`) 이 들어가 경로가 깨져 있었다.

```
python 02_CODE^Gxis_baselines_v7.py       (BEL, 실행 불가)
python 02_CODE\axis_baselines_v7_1.py     (v7.1 수정)
```

원인은 v7 작업 중 `sed` 치환에서 `\a` 가 escape 로 해석된 것이다.
모든 `.bat` 를 재생성하고 **제어문자 전수검사**를 검증 항목(`E::bat_files_have_no_control_chars`)으로 넣었다.

### 18.3 테스트 자립 실행

`test_v7_1.py` 는 저장된 과거 결과에 의존하지 않는다.

- reference parameter 를 `configure_params()` 로 **명시적으로 초기화**
- 후보 시간표·Service Need 를 임시 폴더에 새로 생성
- 모든 검사가 그 실행 결과만 사용

v7 의 `test_phase2_v7.py` 는 `05_RESULTS/PROPOSAL` 이 미리 있어야 했다.

### 18.4 검증이 실제 코드를 실행

`verify_v7_1.py` 는 CSV 의 PASS 문자열만 읽지 않는다.

| 단계 | 내용 |
|---|---|
| A | 데이터 생성기를 **다시 실행**하고 배포본과 바이트 단위 비교 |
| B | Joint MILP 를 **다시 실행**하고 불변식을 직접 계산·검사 |
| C | 회귀 테스트 스위트를 **다시 실행** |
| D | 배포 산출물의 내부 일관성 (합계 일치, default 값, 파일 존재) |
| E | 패키지 구조·협상 계층 제거·`.bat` 제어문자 |

---

## 7. 변경 이유

| 무엇을 | 왜 |
|---|---|
| 협상 계층 제거 | 연구 질문은 *"복수 선사 공동화가 KORAIL 신규 철도서비스 구성 가능성과 운영효율을 어떻게 바꾸는가"* 다. 선사 수락행동·가격협상·예약 프로세스는 상용화 단계 운영 프로세스이며 이번 연구 범위가 아니다 |
| Proposal → Recommendation | "제안 후 수락 대기" 라는 협상 함의를 제거하고, 공동 최적화 결과의 선사 관점 표현임을 명확히 하기 위해 |
| one-shot 실행 | 실제 서비스에서 AXIS 는 같은 planning cycle 에 제출된 데이터를 한 번에 공동 최적화한다. 3단계 상태기계는 이 구조를 왜곡한다 |
| 챗봇 read-only 고정 | LLM 이 MILP 변수·제약을 바꾸거나 숫자를 생성하면 최적화 결과의 근거가 무너진다 |
| `candidate_source` 도입 | 현재 결과가 KORAIL 실제 운행가능시간이 아님을 데이터 레벨에서 표시하고, 실제 path 로 교체할 지점을 명시하기 위해 |

---

## 8. 향후 실데이터 교체 지점

| 현재 | 교체 대상 | 교체 방법 |
|---|---|---|
| `AXIS_carrier_hourly_plan_v7_1.csv` (Synthetic Carrier-Level Data) | 선사 제출 CSV | 동일 schema. `--hourly` 로 교체 |
| `carrier_initial_inventory.csv` | 선사 제출 재고 | `--initial` 로 교체 |
| `TRAIN_CANDIDATE.csv` (`candidate_source=PROTOTYPE_SYNTHETIC`) | KORAIL feasible path (`KORAIL_FEASIBLE_PATH`) | `--candidates <dir>` 로 교체 |
| 미제공 | KORAIL path slot / 화차 / 기관차 가용량 | `--operations <json>` 로 활성화 |

**MILP core 는 이 파일들이 바뀌어도 동일하게 작동한다.** 코드 수정이 필요 없다.
