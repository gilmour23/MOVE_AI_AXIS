# V7.1 재현성 감사

**판정:** 전체 검증 **76/76 PASS**, 자립 회귀 테스트 **56/56 PASS** (pre-patch record)

---

## 1. 지시서 18.4 대응 — 검증이 실제 코드를 실행한다

v7 의 `verify_v7.py` 는 저장된 CSV 의 `PASS` 문자열을 읽는 항목이 많았다.
`verify_v7_1.py` 는 **5단계**로 나누고 A·B·C 를 실제 실행으로 대체했다.

| 단계 | 내용 | 결과 |
|---|---|---|
| **A** | 데이터 생성기를 **다시 실행**하고 배포본과 바이트 단위 비교 | 11/11 |
| **B** | Joint MILP 를 **다시 실행**하고 불변식을 직접 계산·검사 | 24/24 |
| **C** | 회귀 테스트 스위트를 **다시 실행** | 1/1 |
| **D** | 배포 산출물의 내부 일관성 | 23/23 |
| **E** | 패키지 구조 · 협상 계층 제거 · `.bat` 제어문자 | 17/17 |

```
VERIFICATION v7.1: 76/76 PASS
```

---

## 2. A — 데이터 생성 재현

생성기를 임시 폴더에 다시 실행한 결과.

| 검사 | 결과 |
|---|---|
| 생성기 재실행 | PASS — `aggregate/structure checks: 18/18 ALL PASS` |
| aggregate demand 보존 | mismatch **0 / 2,016행** |
| aggregate supply total 보존 | mismatch **0 / 2,016행** |
| aggregate initial inventory 보존 | PASS |
| 6개 거점 고유 prior | **6/6** |
| demand/supply 구조적 비대칭 | min_max_gap 0.1349, mean 0.1918 |
| 시간 연속성 | 인접 block 최대 변동 0.0903 (ρ=0.75, σ=0.10) |
| 소형선사 구조적 배제 | **0건** |
| 실현 share 의 설계 share 추종 | 최대편차 0.0921 |
| **배포본과 바이트 단위 동일** | `37178fb48bc905867810f826…` **일치** |

v7 개선사항(§17 롤백 금지 항목)이 전부 유지되고 있음을 **재실행으로** 확인했다.

---

## 3. B — Joint MILP 재현 및 불변식

MILP 를 다시 풀어 산출물에서 직접 계산해 검사했다 (`--quick`: 48h).

| 항목 | 결과 |
|---|---|
| 전 stage 최적성 증명 | PASS |
| solver 전 stage status = 0 | PASS |
| Z1·Z2 `mip_rel_gap = 0` | PASS |
| deterministic tie-break stage 존재 | PASS |
| **multi-carrier consolidation 발생** | PASS (편당 5~6 선사) |
| 구간 capacity 준수 | PASS |
| minimum consolidation level 준수 | PASS |
| formation 선택 | PASS |
| 정수 배정 | PASS |
| 기한(하화 완료 기준) 준수 | PASS |
| 조기도착 상한 준수 | PASS |
| 동일 거점·시각 중복열차 없음 | PASS |
| **carrier ownership 보존** | 위반 0건 |
| **source release capacity 준수** | 위반 0건 |
| **선사 관점 == KORAIL 관점** | PASS |
| explanation context 생성 | PASS |
| `candidate_source` 기록 | `PROTOTYPE_SYNTHETIC` |
| synthetic/prototype 플래그 | PASS |
| 편도 모형 플래그 | `return_wagon_movement_included = false` |
| 거리 검증 (physical vs tariff) | 9/9 PASS |
| 파라미터 출처 기록 | XLSX 로드 확인 |
| 운영제약 `NOT_APPLIED_NO_DATA` 기록 | PASS |
| conflict 제약 적용 기록 | PASS |

---

## 4. C — 회귀 테스트 재실행 (지시서 18.3)

`test_v7_1.py` 는 **저장된 과거 결과에 의존하지 않는다.**

- `configure_params()` 로 reference parameter 를 명시적으로 초기화
- 후보 시간표·Service Need·최적화 결과를 임시 폴더에 새로 생성
- 종료 시 임시 폴더 삭제

```
REGRESSION v7.1: 56/56 PASS
```

| 그룹 | 항목 수 | 내용 |
|---|---|---|
| [1] 파라미터 초기화 | 4 | xlsx 로드, 거리 검증, physical vs tariff 설명 |
| [2] 재고정책 스키마 | 19 | 8개 오류 케이스 × (코드·구조화) + 정상 적용 3건 |
| [3] 공동최적화 불변식 | 18 | consolidation, capacity, ownership, source release, 두 관점 일치, 선사별 파일 격리 |
| [4] 협상 계층 제거 | 7 | 코어 식별자 부재, 함수 삭제, `run()` one-shot |
| [5] 결정성 | 8 | 5회 반복 recommendation/열차/목적값 완전 동일 |

### 결정성 실측

| 지표 | 5회 결과 |
|---|---|
| Recommendation 그룹 해시 | 1가지 |
| 선택 열차 집합 | 1가지 |
| rail_served_teu | {90} |
| selected_train_count | {2} |
| train_km / wagon_km | {798.7} / {26357.1} |
| teu_km | {26487.7} |
| expected_korail_revenue_krw | {9616860.8} |

---

## 5. D — 배포 산출물 일관성

| 검사 | 결과 |
|---|---|
| `AXIS_INTEGRATED/SUMMARY.json` 존재 | PASS |
| **선사 관점 == KORAIL 관점** | `carrier_korail_view_consistent = true` |
| 정본 default `max_earliness = 72` | PASS |
| 정본 default `min_load_factor = 0.5` | PASS |
| Recommendation TEU == Allocation TEU | PASS |
| 필수 출력 10종 존재 | PASS |
| 베이스라인 A/B/C 존재 | PASS |
| 민감도 3종 (5/3/3행) | PASS |
| LF 민감도 0.5/0.6/0.7 커버 | PASS |

---

## 6. E — 구조 및 협상 계층 제거

| 검사 | 결과 |
|---|---|
| 코어에 협상 식별자 없음 | `[]` (ACCEPT_SERVICE, MODIFY_SERVICE, proposal_version, negotiation_round, accepted_by_need, declined_by_need 등 전무) |
| `run()` one-shot | `run_mode` / `actions_path` 없음 |
| legacy 폴더 분리 | `future_extensions/negotiation_legacy` |
| 패키지 폴더 5종 | PASS |
| 실행 스크립트 7종 + README | PASS |
| **`.bat` 제어문자 없음** | `[]` |

### `.bat` 제어문자 (지시서 18.2)

v7 의 `run_baselines.bat` 에 BEL(`0x07`) 이 들어가 실행이 불가능했다.

```
v7   : python 02_CODE^Gxis_baselines_v7.py        (BEL)
v7.1 : python 02_CODE\axis_baselines_v7_1.py      (정상)
```

원인은 v7 작업 중 `sed` 치환에서 `\a` 가 escape 로 해석된 것이다.
모든 `.bat` 를 재생성하고 **제어문자 전수검사를 검증 항목으로 고정**했다
(`0x00-0x08`, `0x0b`, `0x0c`, `0x0e-0x1f`).

---

## 7. 실행 결과 (정본 default)

`min_load_factor = 0.5`, `max_earliness = 72h`, handling 3h
Service Need **180 TEU / 147건**

### AXIS_INTEGRATED

| 항목 | 값 |
|---|---|
| Rail Served TEU | 138 (커버리지 76.7%) |
| 신규열차 | 3 |
| Recommendation | 24건 |
| 편당 참여선사 | 4.0 |
| distance-weighted LF | 0.5381 |
| TEU-km | 33,802.4 |
| 예상 철도운임 수입 | 12,242,089원 |

### 베이스라인 (동일조건)

| KPI | A. No Repositioning | B. Carrier Separate | C. AXIS Integrated |
|---|---|---|---|
| Rail Served TEU | 0 | 34 | **138** |
| Rail Unserved TEU | 180 | 146 | **42** |
| Train Count | 0 | 1 | 3 |
| Train-km | 0 | 143.7 | 942.4 |
| Wagon-km | 0 | 4,742.1 | 31,099.2 |
| TEU-km | 0 | 4,885.8 | **33,802.4** |
| Distance-weighted LF | — | 0.5152 | 0.5381 |
| **Avg Carriers per Train** | — | **1.0** | **4.0** |
| 예상 운임수입 | 0 | 1,643,560원 | **12,242,089원** |
| Movement 건수 | 0 | 21 | 113 |

B 의 선사별 내역: CARRIER_A 만 34 TEU / 1편 (부산→약목 단일구간).
나머지 5개 선사는 실행가능 assignment 가 **0** 이다.

> B → C 로 서비스 물량 **4.06배**, TEU-km **6.92배**, 수입 **7.45배**.
> 열차는 1 → 3편(3배)인데 TEU-km 가 6.9배인 것은, 통합이 단순히 열차를 더 띄우는 것이 아니라
> **같은 열차에 여러 선사 물량을 실어 장거리 다구간 서비스를 가능하게** 만들기 때문이다.

### 민감도

**조기도착** (LF 0.5)

| max_earliness | status | Served TEU | 열차 | LF | 편당 선사 | 평균 조기 | 최대 조기 |
|---|---|---|---|---|---|---|---|
| 0h | NO_FEASIBLE_ASSIGNMENT | 0 | 0 | — | — | — | — |
| 24h | NO_FEASIBLE_ASSIGNMENT | 0 | 0 | — | — | — | — |
| **48h** | OPTIMAL | 90 | 2 | 0.5025 | 5.5 | 23.0h | 48h |
| **72h (정본)** | OPTIMAL | **138** | 3 | 0.5381 | 4.0 | 33.4h | 72h |
| 무제한 | OPTIMAL | 173 | 3 | 0.6852 | 4.0 | 57.5h | **146h** |

**Minimum Consolidation Level** (조기도착 72h)

| α | status | Served TEU | 열차 | 실제 LF | 편당 선사 |
|---|---|---|---|---|---|
| **0.5 (정본)** | OPTIMAL | 138 | 3 | 0.5381 | 4.0 |
| 0.6 | OPTIMAL | 111 | 2 | 0.6011 | 5.5 |
| 0.7 | OPTIMAL | 66 | 1 | 0.7010 | 5.0 |

**하역시간** (조기도착 72h, LF 0.5)

| handling | status | 후보 assignment | Served TEU | 열차 |
|---|---|---|---|---|
| 0h | OPTIMAL | 5,476 | 138 | 3 |
| **3h (정본)** | OPTIMAL | 4,989 | 138 | 3 |
| 6h | OPTIMAL | 4,459 | 135 | 3 |

---

## 8. 구조 정리가 최적화를 바꾸지 않았음

v7.1 `AXIS_INTEGRATED` 결과가 v7 `C_AXIS_INTEGRATED` 와 **완전히 일치**한다.

```
138 TEU / 3편 / 편당 4.0 선사 / LF 0.5381 / TEU-km 33,802.4 / 수입 12,242,089원
```

협상 계층 제거·용어 변경·출력 재편은 **인터페이스 정리**이며 MILP 로직에 영향이 없다.

---

## 9. 작업 중 발견해 수정한 이식 버그 2건

| 버그 | 증상 | 원인 | 수정 |
|---|---|---|---|
| 베이스라인 C `movement_count = 0` | C 시나리오만 movement 0 | `CARRIER_PROPOSAL_DETAIL.csv` → `CARRIER_RECOMMENDATION_DETAIL.csv` 치환이 C 구간(`out_c`)에 미반영 | 파일명 수정 후 재실행 (113건 정상) |
| 민감도 전체 `ERROR_KeyError` | E_48 이후 전 항목 실패 | `summ["served_teu"]` / `summ["forecast_unserved_teu"]` 키가 v7.1 에서 `rail_served_teu` / `rail_unserved_teu` 로 바뀜 | 키 수정 후 재실행 |

두 버그 모두 **검증이 실제 코드를 실행하기 때문에** 발견되었다.
저장된 CSV 의 PASS 문자열만 읽었다면 드러나지 않았을 유형이다.

---

## 10. Synthetic / Prototype 가정

| 항목 | 표기 위치 |
|---|---|
| Synthetic Carrier-Level Data | `SUMMARY.json:carrier_data_source` |
| PROTOTYPE_SYNTHETIC 시간표 | `TRAIN_CANDIDATE.csv:candidate_source`, `KORAIL_TRAIN_PLAN.csv`, `SUMMARY.json` |
| 익명 Virtual Carrier | 코드 docstring, `carrier_profile_metadata.csv` |
| PNC/KITL 단일 snapshot | `source_type` / `source_note` |
| λ, role_tilt scenario parameter | `DATA_GENERATION_AUDIT.csv` |
| Minimum Consolidation Level (손익분기 아님) | 문서 전반 + `.bat` 주석 |
| 편도 계획모형 | `return_wagon_movement_included = false` |
| KORAIL 자원제약 미적용 | `OPERATIONAL_CONSTRAINT_AUDIT.csv:NOT_APPLIED_NO_DATA` |

---

## 11. 실데이터 교체 지점

| 현재 | 교체 대상 | 방법 | 코드 수정 |
|---|---|---|---|
| `AXIS_carrier_hourly_plan_v7_1.csv` | 선사 제출 CSV | `--hourly` | 불필요 |
| `carrier_initial_inventory.csv` | 선사 제출 재고 | `--initial` | 불필요 |
| `TRAIN_CANDIDATE.csv` (`PROTOTYPE_SYNTHETIC`) | KORAIL feasible path (`KORAIL_FEASIBLE_PATH`) | `--candidates <dir>` | 불필요 |
| 미제공 | path slot / 화차 / 기관차 가용량 | `--operations <json>` | 불필요 |

실제 서비스 전환 시 데이터 생성 단계(`run_data_generation.bat`)는 사라지고
선사 제출 파일이 그 자리에 들어간다. **MILP core 는 동일하게 작동한다.**

---

## 12. 남아있는 한계

1. 전체 파이프라인 재실행에 시간이 걸린다 (72h 기준 1.5~2시간).
   `--max-earliness 48` 이면 크게 단축된다.
2. `verify_v7_1.py` 는 기본적으로 72h 로 MILP 를 재실행하며 `--quick` 으로 48h 단축이 가능하다.
   본 감사는 `--quick` 으로 수행했다. 배포 산출물(D 단계)은 72h 기준으로 검사된다.
3. 결정성은 **동일 환경 5회** 로 검증했다. 다른 scipy/HiGHS 버전 간 동일성은
   Z7 tie-break 로 구조적으로 보장하되 실측하지 않았다.
4. 민감도는 단일 주간(2026-08-10~16) 기준이다.
5. 조기도착 24h 이하에서 서비스가 성립하지 않는 것은 데이터·코드 결함이 아니라
   **조기도착 허용폭과 consolidation 사이의 구조적 trade-off** 다.
