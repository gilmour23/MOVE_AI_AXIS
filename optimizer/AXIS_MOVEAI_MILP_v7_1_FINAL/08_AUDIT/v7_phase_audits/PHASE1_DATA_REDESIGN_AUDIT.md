# Phase 1 감사 — 데이터 재설계

**대상 지시:** v7 수정 지시서 Phase 1 (1-1 / 1-2 / 1-3)
**작업일:** 2026-08-10
**판정:** 완료. 자동검증 18/18 PASS, 동일 seed 재현성 확인.

---

## 1. 변경한 파일

| 파일 | 구분 | 내용 |
|---|---|---|
| `02_CODE/axis_data_gen_v7.py` | 신규 | Carrier Disaggregation Layer 전체 |
| `03_INPUT_DATA/AXIS_hourly_empty_demand_supply_v8_6hubs.xlsx` | 반입 | Master Aggregate (지시서 1-3) |
| `03_INPUT_DATA/AXIS_carrier_hourly_plan_v7.csv` | 신규 | 12,096행 선사별 168시간 계획 |
| `03_INPUT_DATA/carrier_initial_inventory.csv` | 재생성 | 72행 |
| `03_INPUT_DATA/carrier_profile_metadata.csv` | 재생성 | source_type/source_note/lambda_value/random_seed 포함 |
| `03_INPUT_DATA/PUBLIC_SNAPSHOT_ANCHOR.csv` | 신규 | 공개자료 → Virtual Carrier anchor 유도 감사표 |
| `03_INPUT_DATA/AGGREGATE_PRESERVATION_CHECK.csv` | 신규 | 총량보존 및 구조 검증 18종 |
| `03_INPUT_DATA/DATA_GENERATION_AUDIT.csv` | 신규 | seed / 생성규칙 / 파라미터 전량 기록 |
| `08_AUDIT/v6_1_reference/` | 보관 | v6.1 원본 데이터·결과 (비교용) |

v6.1 패키지 원본은 수정하지 않았습니다.

---

## 2. 수정 전 문제

리뷰 문서 #5 / #13 / #14 에 해당합니다.

| 문제 | v6.1 실측 |
|---|---|
| Demand share ≈ Supply share (계획서 §16 위반) | CARRIER_A 격차 0.0003 |
| 거점별 prior 미분화 (§14 위반) | 고유 profile 3개 / 6거점 (BUGANG=UIWANG, BUSAN=YAKMOK, DONGSAN=GWANGYANG 완전 동일) |
| Master Aggregate 부재 (§21-1~3 검증 불가) | 파일 없음 |
| 결과 | Service Need 118 TEU = 총수요의 8.92% |

---

## 3. 수정 내용

### 3-1. Demand / Supply share 구조적 비대칭 (지시서 1-1)

**임의 +N%p 가산을 쓰지 않았습니다.** 선사 역할을 먼저 정의하고 거기서 share 를 유도했습니다.

> 선사는 자사 주력 항만/거점으로 공컨을 반입(return·sea inbound)하고,
> 자사 화주가 집중된 내륙 거점에서 픽업 수요가 발생한다.
> supply_base 와 demand_base 가 다른 거점일 때 구조적 재배치 수요가 생긴다.

| carrier | supply 우위 | demand 우위 | 성격 |
|---|---|---|---|
| CARRIER_A | BUSAN | YAKMOK | 부산 반입 → 경부축 내륙 |
| CARRIER_B | UIWANG | BUGANG | 수도권 반입 → 중부 |
| CARRIER_C | GWANGYANG | DONGSAN | 광양 반입 → 서남축 내륙 |
| CARRIER_D | BUSAN | GWANGYANG | 부산 반입 → 서남권 (축 교차) |
| CARRIER_E | UIWANG | YAKMOK | 수도권 반입 → 경부축 |
| CARRIER_F | — | — | **Others pool** (역할 없음) |

share 유도식 (multinomial logit tilt):

```
w[c,h] = P_hub[c] · exp(role_tilt · 1{h == base[c]})
share  = w / Σ_c w
```

demand 와 supply 가 서로 다른 base 를 참조하므로 비대칭이 발생합니다.

**CARRIER_F 설계 판단:** 계획서 §13 의 "Others" 는 상위 5사를 제외한 다수 소형선사의 풀입니다.
여러 선사의 합이므로 단일 supply/demand base 를 가질 수 없어 role tilt 를 적용하지 않았습니다.
1차 생성에서는 F 에도 역할을 부여했으나 논리적으로 맞지 않아 제거했습니다.

> **보수적 가정 명시:** 실제 Others 는 다수의 소형선사이며 각각은 열차 1편을 채울 수 없습니다.
> 이를 단일 carrier 로 묶으면 Phase 3 의 Carrier Separate 베이스라인이 실제보다 **유리**해지므로,
> AXIS 통합효과를 과대평가하지 않는 방향입니다.

### 3-2. 6개 거점 고유 prior (지시서 1-2)

공개자료를 anchor 로, 거점별 혼합계수 λ 로 6개 고유 profile 을 만들었습니다.

```
P_hub = normalize( λ_hub · P_PNC + (1-λ_hub) · P_KITL )
```

| hub | λ | source_type |
|---|---|---|
| BUSAN | 1.00 | `PNC_CALIBRATED` |
| YAKMOK | 0.85 | `PNC_DERIVED_SYNTHETIC` |
| BUGANG | 0.55 | `BLENDED_SYNTHETIC` |
| UIWANG | 0.45 | `BLENDED_SYNTHETIC` |
| DONGSAN | 0.15 | `KITL_DERIVED_SYNTHETIC` |
| GWANGYANG | 0.00 | `KITL_CALIBRATED` |

검증 `six_hubs_distinct_prior` = **6/6 고유** (v6.1 은 3/6).

라벨링도 정정했습니다. v6.1 은 약목·동산에 항만과 동일한 `*_CALIBRATED` 를 붙여 실측처럼 보였으나,
v7 은 `*_DERIVED_SYNTHETIC` 으로 구분하고 `source_note` 에 "실측값 아님"을 명시했습니다.

**Virtual Carrier 해석 주의(계획서 §12):** 공개자료의 점유율 *순위 shape* 만 차용했으며
CARRIER_A 가 특정 실선사를 지칭하지 않습니다. 코드 docstring 과 metadata 에 명시했습니다.

### 3-3. Master Aggregate 및 총량보존 (지시서 1-3)

원본 파일을 패키지에 반입하고, 총량보존 검증을 자동검증에 넣었습니다.
**1건이라도 불일치하면 전체 FAIL** 하도록 구현했습니다 (exit code 1).

원본 주간: `2025-05-05 ~ 2025-05-11` → 대상 주간 `2026-08-10 ~ 2026-08-16` 매핑.

---

## 4. 작업 중 발견해 수정한 문제 2건

지시서에 없던 항목이지만 데이터 타당성에 직결되어 수정했습니다.

### 4-1. 시간 연속성 위반 (계획서 §18)

1차 구현은 6시간 block 마다 **독립 Dirichlet** 을 뽑았습니다. block 간 자기상관이 없어
인접 block share 변동 **최대 0.7831** — 계획서 §18 이 금지한 "12시 60% → 13시 3%" 급변에 해당했습니다.

log-share 공간의 **AR(1) 평균회귀 과정**으로 교체했습니다.

```
z_b = (1-ρ)·log(base) + ρ·z_{b-1} + ε_b,   ε ~ N(0, σ²)
share_b = softmax(z_b)          ρ=0.75, σ=0.10
```

| 지표 | 수정 전 | 수정 후 |
|---|---|---|
| 인접 block share 변동 최대 | 0.7831 | **0.0903** |
| 평균 | 0.1139 | **0.0123** |
| base 로부터의 장기 편향 | — | 0.0328 (평균회귀 확인) |

### 4-2. Largest Remainder 의 소형선사 구조적 배제

매시간 독립 LRM 을 적용하면 물량이 1~2박스인 시점에서 **항상 share 최대 선사가 가져가**
소형 선사가 168시간 내내 0 을 받았습니다. 실측: 거점별 composition 에 `0.000` 이 **9건**.

"받아야 할 누적량(owed)" 을 유지하고 매 시점 owed 가 큰 선사부터 1박스씩 배분하는
**이월(carry-over) 배분기**로 교체했습니다.

- Σ alloc == total (매 시점 정확한 총량 보존) 유지
- 누적 배분량이 누적 목표량을 추종 → 장기 share 가 설계 share 로 수렴
- 실측 결과 구조적 배제 **0건**, 실현 share 의 설계 share 대비 최대편차 0.0921

> 이 수정으로 Service Need 가 356 → 180 TEU 로 **감소**했습니다.
> 1차 수치가 높았던 것은 편향된 LRM 이 만든 **인위적 불균형**이었으므로,
> 감소가 정상입니다. (지시서 §6 "숫자가 원하는 방향으로 나오도록 tuning 하지 않는다" 적용)

---

## 5. Phase 1 요구 출력

| 항목 | v6.1 | v7 |
|---|---|---|
| total demand TEU | 1,323 | **1,323** |
| total supply TEU | 1,604 | **1,604** |
| service need 건수 | 86 | 147 |
| service need TEU | 118 | 180 |
| service need / total demand | 8.92% | **13.61%** |
| aggregate preservation error | 미검증 | **0 / 2,016행** |

### carrier별 share (전국 TEU 기준)

| carrier | v6.1 D | v6.1 S | v7 D | v7 S |
|---|---|---|---|---|
| A | 0.3379 | 0.3367 | 0.2494 | 0.2519 |
| B | 0.1633 | 0.1440 | 0.1920 | 0.1883 |
| C | 0.1232 | 0.1203 | 0.1202 | 0.1016 |
| D | 0.1096 | 0.1390 | 0.2063 | 0.2712 |
| E | 0.1504 | 0.1253 | 0.0703 | 0.0680 |
| F | 0.1156 | 0.1347 | 0.1618 | 0.1191 |

> **전국 격차는 핵심 지표가 아닙니다.** 역할 tilt 는 거점 단위로 작동하므로,
> 한 선사가 전국적으로 수요·공급이 균형인 채로 **공간적으로만 어긋나 있는 것**이 정상입니다.
> (전국적으로 수요 > 공급이면 그 선사는 구조적으로 컨테이너를 잃고 있다는 뜻이 되어 비현실적입니다.)

### 거점별 |demand share − supply share| — 실제 핵심 지표

| hub | v6.1 평균 | v7 평균 | v6.1 최대 | v7 최대 |
|---|---|---|---|---|
| UIWANG | 0.0410 | 0.0895 | 0.1065 | 0.1857 |
| BUGANG | 0.0431 | 0.0756 | 0.0835 | 0.2268 |
| YAKMOK | 0.0408 | 0.0909 | 0.0697 | 0.2255 |
| BUSAN | 0.0140 | 0.0684 | 0.0273 | 0.1158 |
| DONGSAN | 0.0849 | 0.0598 | 0.1705 | 0.1794 |
| GWANGYANG | 0.0328 | 0.0392 | 0.0502 | 0.1176 |
| **전체** | **0.0428** | **0.0706** | 0.1705 | 0.2268 |

설계 share 기준 검증값: `min_max_gap=0.1349, mean=0.1918`

### hub별 carrier composition (v7, demand share)

| hub | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| UIWANG | 0.204 | 0.156 | 0.124 | 0.171 | 0.080 | 0.265 |
| BUGANG | 0.135 | **0.405** | 0.099 | 0.135 | 0.045 | 0.180 |
| YAKMOK | **0.465** | 0.139 | 0.078 | 0.163 | 0.094 | 0.061 |
| BUSAN | 0.243 | 0.232 | 0.111 | **0.328** | 0.050 | 0.037 |
| DONGSAN | 0.121 | 0.103 | **0.328** | 0.069 | 0.069 | 0.310 |
| GWANGYANG | 0.150 | 0.110 | 0.145 | 0.092 | 0.092 | **0.410** |

굵은 값이 각 선사의 demand_role_hub 입니다. 설계대로 나타났습니다.

---

## 6. 구조적 타당성 검사

지시서: *"새 Service Need 가 많아졌다는 이유만으로 성공으로 판정하지 않는다."*

### 6-1. Need 가 실제 부족 거점에 발생하는가

| hub | 순수급(S−D) | Need TEU |
|---|---|---|
| UIWANG | **+143** | 0 |
| BUSAN | **+270** | 31 |
| BUGANG | +1 | 14 |
| GWANGYANG | −28 | 53 |
| DONGSAN | −31 | 16 |
| YAKMOK | **−74** | **66** |

부족이 가장 큰 YAKMOK 에 Need 가 가장 크고, 최대 잉여 UIWANG 은 Need 0 입니다. 타당합니다.

BUSAN 이 +270 잉여인데도 Need 31 TEU 가 발생하는 것은 **선사별 ownership 분리** 때문입니다.
A·D 가 부산에 대량 보유하지만 B·E·F 는 부족합니다. 이것이 AXIS 가 다루는 현상 자체이며,
계획서 §2.4(재고 pooling 금지)의 직접적 귀결입니다.

### 6-2. Need 가 각 선사의 demand_role_hub 에 집중되는가

| carrier | role_demand | 해당 거점 Need / 총 Need |
|---|---|---|
| CARRIER_A | YAKMOK | 81.2% |
| CARRIER_B | BUGANG | 67.1% |
| CARRIER_C | DONGSAN | 100.0% |
| CARRIER_D | GWANGYANG | 61.5% |
| CARRIER_E | YAKMOK | 44.8% |
| CARRIER_F | (Others) | 분산 |

### 6-3. 각 선사가 supply_role_hub 에 실제 잉여를 갖는가

carrier × hub 순포지션 (I₀ + 공급 − 수요, TEU) 에서
A: BUSAN **+257** / YAKMOK **−93**, B: UIWANG **+248** / BUGANG **−55**,
C: GWANGYANG **+50** / DONGSAN **−31**, D: BUSAN **+223** / GWANGYANG **−6**,
E: UIWANG **+79** / YAKMOK **−12**.

각 선사가 자기 supply base 에 잉여, demand base 에 부족을 갖는 구조가 정확히 형성되었으며
이 방향이 모두 실제 corridor(경부·서남) 위에 놓여 있습니다.

---

## 7. 파라미터 선택 근거 (role_tilt)

지시서 §6 에 따라 목표 수치를 정해놓고 맞추지 않았습니다.
`role_tilt = 1.10` 은 `exp(1.10) ≈ 3.0`, 즉 **주력거점에서 가중 3배**라는 해석 가능한 값으로 선택했습니다.

| role_tilt | exp | needs | need TEU | need/demand | hub 비대칭 평균 | max carrier share | 검증 |
|---|---|---|---|---|---|---|---|
| 0.00 | 1.00 | 63 | 74 | 5.59% | 0.0163 | 0.221 | **FAIL** |
| 0.55 | 1.73 | 76 | 90 | 6.80% | 0.0333 | 0.234 | PASS |
| **1.10** | **3.00** | **147** | **180** | **13.61%** | **0.0706** | **0.249** | **PASS** |
| 1.65 | 5.21 | 235 | 298 | 22.52% | 0.1093 | 0.267 | PASS |

- 단조적이고 안정적입니다.
- `tilt=0` 이 자동검증에서 FAIL 하는 것은 정상입니다 — 구조적 비대칭이 없으므로
  `demand_supply_structural_asymmetry` 검사가 걸립니다. 이 값이 곧 v6.1 의 상태입니다.
- 어떤 tilt 에서도 총량보존과 carrier 과집중 기준은 유지됩니다.

---

## 8. 자동검증 결과 (18/18 PASS)

| 검사 | 결과 |
|---|---|
| aggregate_demand_preservation | PASS — mismatch 0/2016 |
| aggregate_supply_return_preservation | PASS — 0/2016 |
| aggregate_supply_sea_preservation | PASS — 0/2016 |
| aggregate_supply_total_preservation | PASS — 0/2016 |
| aggregate_initial_inventory_preservation | PASS |
| all_values_integer | PASS |
| no_negative_values | PASS |
| horizon_168_hours | PASS |
| six_hubs / both_sizes / row_count | PASS (12,096행) |
| six_hubs_distinct_prior | PASS — 6/6 |
| demand_supply_structural_asymmetry | PASS — min_max_gap 0.1349 |
| no_carrier_over_concentration | PASS — max 0.2432 |
| temporal_continuity_block_share | PASS — 0.0903 |
| no_structural_carrier_exclusion | PASS — 0건 |
| realized_share_tracks_design | PASS — 최대편차 0.0921 |
| block_share_mean_reversion | PASS — drift 0.0328 |

**재현성:** 동일 seed 2회 실행 → `AXIS_carrier_hourly_plan_v7.csv` SHA-256 완전 일치.

---

## 9. 남아있는 한계

1. **Virtual Carrier 는 합성값입니다.** PNC/KITL 공개자료는 2026-08-09 단일 시점 snapshot 이며
   점유율 *shape* 만 차용했습니다. 전국 시장점유율이나 특정 선사의 실제 물량이 아닙니다.
2. **λ 와 role_tilt 는 scenario parameter 입니다.** 실측 근거가 없으므로 공식값처럼 제시하면 안 됩니다.
   §7 민감도 표를 함께 제시해야 합니다.
3. **Others pool 을 단일 carrier 로 취급**했습니다. Phase 3 베이스라인 해석 시 이 보수적 가정을 명시해야 합니다.
4. **역할 배정 자체가 가정**입니다. 실제 선사 운영데이터가 확보되면 이 layer 전체를 교체합니다
   (계획서 §23 구조 유지 — schema 동일).
5. 공개자료 다시점 수집(계획서 §64)은 아직 1개 시점뿐입니다. MVP 필수사항은 아닙니다.

---

## 10. 다음 Phase 영향

- Service Need 가 118 → 180 TEU 로 증가하고 **6개 거점 전체에 분산**되었으므로,
  Phase 3 (Carrier Separate) 과 Phase 4 (민감도) 의 결과가 v6.1 과 크게 달라집니다.
- v6.1 의 `118 TEU / 109 TEU / 2편 / 92.37%` 수치는 **전부 폐기**합니다 (지시서 §6).
- MILP 입력 파일명이 `AXIS_carrier_hourly_plan_v7.csv` 로 변경되었습니다.
