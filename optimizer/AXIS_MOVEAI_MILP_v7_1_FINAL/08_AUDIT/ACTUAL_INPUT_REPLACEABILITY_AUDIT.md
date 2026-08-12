# 실제 입력 교체 가능성 감사

**목적:** "실제 선사 제출 데이터 / 실제 KORAIL feasible path 로 교체 가능하다"는 주장을
**문서가 아니라 실행되는 test fixture 로 증명**한다 (지시서 §28).

**판정:** 6개 항목 전부 자동검증으로 고정됨.

---

## 1. 왜 이 감사가 필요했나

v7.1 FINAL 까지는 "교체 가능"이 **문서상 주장**이었다.
코드를 실제로 뜯어보니 세 가지가 성립하지 않았다.

| 문제 | 결과 |
|---|---|
| `_candidate_inputs_match()` 가 `min(departure) == horizon_start` 를 요구 | 정상 외부 후보도 mismatch 판정 → **synthetic 으로 덮어쓸 수 있었음** |
| `TRAIN_SEGMENT.segment_distance_km` 를 읽지 않음 | 외부 path 의 실제 거리가 MILP·KPI 에 **반영되지 않음** |
| `TRAIN_FORMATION_OPTION` 의 `wagon_count`/`capacity_teu` 를 읽지 않음 | 외부 편성이 **무시되고 global F33/F40/F50 사용** |

추가로 실행 중 `SERVICE_NEED.csv` 등이 **외부 후보 디렉터리에 기록**되어
사용자 파일을 오염시키고 있었다.

---

## 2. 테스트 fixture

```
03_INPUT_DATA/TEST_KORAIL_CANDIDATES_RAW/   분 단위 원본 (KORAIL 제공 형태)
03_INPUT_DATA/TEST_KORAIL_CANDIDATES/       normalization 결과 (AXIS 표준 4파일)
```

**의도적으로 prototype 과 다르게** 만들었다. 값이 반영되지 않으면 테스트가 실패한다.

| 항목 | prototype | fixture |
|---|---|---|
| train_id | `CAND####` | `KTEST001`, `KTEST002` |
| 첫 출발 | 정각 계열 | **06:35** (분 단위, 정각 아님) |
| candidate_source | `PROTOTYPE_SYNTHETIC` | `KORAIL_FEASIBLE_PATH` |
| 부산신항→약목 | 143.7 km | **150.5 km** |
| 의왕→부강 | 111.8 km | **120.4 km** |
| 부강→동산 | 130.2 km | **140.9 km** |
| 동산→신광양항 | 148.6 km | **155.1 km** |
| 편성 | `F33` 66TEU / 33량 | **`KF44` 88TEU / 44량** |

생성:

```bash
python 02_CODE/make_test_korail_candidates.py \
  --out 03_INPUT_DATA/TEST_KORAIL_CANDIDATES \
  --raw 03_INPUT_DATA/TEST_KORAIL_CANDIDATES_RAW \
  --horizon-start "2026-08-10 00:00"
```

분 단위 시각은 `02_CODE/normalize_korail_candidates_v7_1.py` 가 보수적으로 slot 변환하고
원본을 `actual_*` 컬럼에 보존한다.

```
actual_load_start 03:35 → load_start_slot 3   (floor)
actual_departure  06:35 → departure_slot  7   (ceil)
actual_arrival    09:40 → arrival_slot   10   (ceil)
actual_available  12:40 → available_slot 13   (ceil)
```

---

## 3. 지시서 §10 요구 8항목 검증 결과

`02_CODE/test_v7_1.py` `[6] External KORAIL candidate replaceability`

| # | 요구 | 검증 항목 | 결과 |
|---|---|---|---|
| 1 | `--candidates TEST_KORAIL_CANDIDATES` 실행 | `ext::fixture_present` | PASS |
| 2 | 실행 전후 candidate files SHA256 동일 | `ext::external_candidate_not_overwritten`<br>`ext::external_candidate_hash_unchanged` | **PASS** |
| 3 | synthetic generator 미호출 | `ext::synthetic_generator_not_called` | **PASS** |
| 4 | `candidate_source=KORAIL_FEASIBLE_PATH` 유지 | `ext::candidate_source_preserved` | PASS |
| 5 | KORAIL output 에 KTEST 사용 | `ext::external_train_id_used` → `['KTEST002']` | PASS |
| 6 | physical KPI 가 fixture 거리 사용 | `ext::external_segment_distance_used` → `[120.4, 140.9, 155.1]`<br>`ext::external_train_km_matches_fixture` → `416.4` | **PASS** |
| 7 | formation capacity 가 fixture 값 | `ext::external_formation_capacity_used` → `capacity 88 / wagons 44` | **PASS** |
| 8 | SUMMARY source 가 `KORAIL_FEASIBLE_PATH` | `ext::candidate_source_preserved` | PASS |

실제 실행 로그

```
1. 외부 후보 파일 미변경(파일목록+해시): True
   files: ['TRAIN_CANDIDATE.csv','TRAIN_FORMATION_OPTION.csv','TRAIN_SEGMENT.csv','TRAIN_STOP_TIME.csv']
2. candidate_timetable_source: KORAIL_FEASIBLE_PATH
3. 사용열차/편성/용량/화차:
   [{'train_id':'KTEST002','formation':'KF44','capacity_teu':88,'wagons':44,'train_km':416.4}]
4. segment physical_distance_km: 120.4 / 140.9 / 155.1
```

`train_km 416.4 = 120.4 + 140.9 + 155.1` — **prototype 의 390.6 이 아니다.**

---

## 4. 외부 후보 보호 메커니즘

```python
if candidates_dir is not None:
    input_dir = Path(candidates_dir)
    validate_candidate_inputs(input_dir, timestamps)   # 실패 시 구조화 오류
    # generate_candidate_inputs() 를 절대 호출하지 않는다
else:
    input_dir = root / "MODEL_INPUTS"
    if not _candidate_inputs_match(...):
        generate_candidate_inputs(...)
```

- 외부 후보가 잘못되면 **자동 보정하거나 synthetic 으로 대체하지 않고** `CANDIDATE_INPUT_INVALID` 를 반환한다.
- 실행 생성물은 `<root>/_RUN_MODEL_INPUTS/` 에 기록해 외부 디렉터리를 오염시키지 않는다.

---

## 5. Candidate cross-file validation

`validate_candidate_inputs()` — `[8] KORAIL candidate cross-file validation`

| 검사 | 테스트 결과 |
|---|---|
| 정상 fixture 통과 | PASS — `train_count=2, sources=['KORAIL_FEASIBLE_PATH']` |
| 파일 누락 | PASS — `CANDIDATE_FILE_MISSING` |
| `service_distance_km ≠ Σ segment_distance_km` | PASS — `KTEST001: 160.5 != 150.5 (tolerance 0.05km)` |
| `capacity_teu = 0` | PASS — `KTEST001/KF44: capacity_teu must be > 0` |
| `available_slot < arrival_slot` | PASS — `KTEST001/BUSAN: available_slot < arrival_slot` |

추가 검사: train_id 유일성 / path 정합 / stop 순서·단조성 / slot 범위 /
segment pair 가 path 연속쌍과 일치 / formation 중복 / **4파일 train_id 집합 일치** /
work_stops 부분집합 및 출발·도착 포함.

---

## 6. 선사 제출 데이터 교체

`validate_carrier_inputs()` — `[7] Carrier input validation`

| 검사 | 결과 |
|---|---|
| 정상 파일 통과 | PASS — 12,096행 / 6선사 / 6거점 / 2규격 / 168시간 |
| 중복 행 | PASS — `duplicate (carrier,timestamp,hub,size)` |
| 시간 누락 | PASS — `incomplete grid: 12092 rows, expected 12096` |
| 음수 수요 | PASS — `demand=-3 must be nonnegative` |
| 알 수 없는 hub | PASS — `unknown hub_code 'SEOUL'` |
| 소수 수요 | PASS — `demand=1.5 must be an integer` |
| 초기재고 누락 | PASS |
| carrier 집합 불일치 | PASS |

구조화 오류를 반환하므로 챗봇/포털이 그대로 사용자에게 설명할 수 있다.

실제 서비스 입력 구조는 `01_DOCS/CARRIER_INPUT_SCHEMA.md` 에 정의했고,
선사 1곳 기준 템플릿을 제공한다.

```
03_INPUT_DATA/templates/CARRIER_SUBMISSION_TEMPLATE.csv          (2,016행)
03_INPUT_DATA/templates/CARRIER_INITIAL_INVENTORY_TEMPLATE.csv   (12행)
```

---

## 7. 교체 절차 요약

### 선사 데이터

```bash
# 1) 각 선사가 자기 파일만 제출 → AXIS backend 가 검증·정규화
# 2) 정규화된 내부 테이블로 실행
python 02_CODE/axis_milp_v7_1.py \
  --hourly <정규화된 carrier_hourly_plan.csv> \
  --initial <정규화된 carrier_initial_inventory.csv> ...
```

데이터 생성 단계(`run_data_generation.bat`)는 실제 서비스에서 **사라진다.**

### KORAIL 후보

```bash
# 1) 실제 timetable 을 AXIS 표준으로 변환 (분 단위 → slot, 원본 보존)
python 02_CODE/normalize_korail_candidates_v7_1.py \
  --raw <KORAIL 원본> --out 03_INPUT_DATA/KORAIL_CANDIDATES \
  --horizon-start "2026-08-10 00:00" --horizon-hours 168

# 2) 그대로 사용 (덮어쓰지 않음)
python 02_CODE/axis_milp_v7_1.py ... --candidates 03_INPUT_DATA/KORAIL_CANDIDATES
```

**MILP core 코드는 수정하지 않는다.**

---

## 8. 남아있는 한계

1. **MILP 해상도는 1시간이다.** 분 단위 path 는 보수적으로 slot 변환되며
   30분 단위 headway 는 표현하지 못한다.
2. 보수적 반올림 때문에 실제 timetable 보다 서비스 가능량이 **과소평가**될 수 있다.
   의도된 방향이다.
3. fixture 는 2개 열차의 소규모 예시다. 실제 KORAIL path 수백 건에서의
   solver 성능은 별도 확인이 필요하다.
4. `work_stops` 미기재 시 전 정차역을 작업역으로 간주한다(하위호환).
   실제 무정차 통과역이 있으면 반드시 `work_stops` 를 명시해야 한다.
5. 선사 입력 검증은 **형식·정합성**만 본다.
   제출된 수요·공급 예측 자체의 타당성은 검증하지 않는다.
