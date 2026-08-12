# AXIS v7.1 — Time Slot Convention

MILP 의 계획 해상도는 **1시간 정수 slot** 이다.
실제 KORAIL feasible path 는 분 단위 시각을 가질 수 있으므로,
시각의 의미와 변환 규칙을 여기서 정본으로 고정한다.

---

## 1. `timestamp` 의 의미

계획기간은 `horizon_start` 부터 1시간 간격 168개 slot 이다.

```
slot t  ==  [horizon_start + t시간, horizon_start + (t+1)시간)
```

즉 slot 은 **그 1시간 구간 전체**를 의미한다.
선사가 제출하는 시간별 수요·공급은 해당 구간에서 발생하는 총량이다.

---

## 2. Hourly Event Order (공식 순서)

한 slot `t` 안에서 재고는 다음 순서로 변한다. **이 순서가 정본이다.**

```
1. external supply     S[c,i,k,t]   가 가용해진다
2. rail inbound        해당 slot 에 available 이 된 철도 도착분이 가용해진다
3. demand consumption  D[c,i,k,t]   가 차감된다
4. rail outbound       남은 재고에서만 반출(상차)이 가능하다
```

따라서

- **같은 slot 에 도착한 공컨은 그 slot 의 수요를 충족할 수 있다.**
  단 "도착"은 하화가 끝난 `available_slot` 기준이다.
- **반출은 자체 수요를 훼손하지 않는 잔여재고에서만 가능하다.**
  이것이 Source Release Capacity 의 정의다.

```
SourceRelease[c,o,k,t] = max( physical_stock[c,o,k,t] − LB[c,o,k,t], 0 )
```

`physical_stock` 은 철도 재배치가 전혀 없을 때의 그 slot 종료 시점 재고다.

`CARRIER_INVENTORY_TIMELINE.csv` 의 replay 도 정확히 이 순서를 따른다.

---

## 3. 열차 시각 4종

| 이름 | 의미 | 모델에서의 역할 |
|---|---|---|
| `load_start_slot` | 출발역 상차 **개시** | 이 시점에 공컨이 그 거점에 있어야 한다 (source release 판정 기준) |
| `departure_slot` | 열차 출발 | 구간 점유 시작 |
| `arrival_slot` | 열차 도착 | 물리 도착 |
| `available_slot` | 하화 완료 = 화주가 실제로 사용 가능 | **기한(due) 충족 판정 기준** |

prototype 생성기 기본값

```
load_start_slot = departure_slot − ⌈origin_loading_h⌉               (3h)
departure_slot(중간 WORK_STOP)  = arrival_slot + ⌈intermediate_handling_h⌉  (3h)
departure_slot(중간 PASS_THROUGH) = arrival_slot                     (0h, 무정차 통과)
available_slot  = arrival_slot + ⌈destination_unloading_h⌉           (3h)
```

**v7.1-patch:** 이전에는 모든 중간역에 3시간이 붙었다.
상하차가 없는 통과역에는 정차시간을 부여하지 않는다.

---

## 4. 실제 분 단위 시각 → model slot 변환 (보수적)

`02_CODE/normalize_korail_candidates_v7_1.py` 가 수행한다.
원본 시각은 `actual_*` 컬럼으로 **항상 보존**한다.

| 대상 | 규칙 | 이유 |
|---|---|---|
| `load_start` | **floor** | 상차 개시를 앞당겨 재고를 더 일찍 요구 → 보수적 |
| `departure` | **ceil** | 출발을 늦춤 |
| `arrival` | **ceil** | 도착을 늦춤 |
| `available` | **ceil** | 사용가능을 늦춤 → 기한 판정 보수적 |

**원칙: 서비스 가능성을 과대평가하는 방향으로는 반올림하지 않는다.**

예시 (fixture `KTEST001`)

```
actual_load_start 03:35 → load_start_slot 3   (floor)
actual_departure  06:35 → departure_slot  7   (ceil)
actual_arrival    09:40 → arrival_slot   10   (ceil)
actual_available  12:40 → available_slot 13   (ceil)
```

변환 규칙은 `TRAIN_STOP_TIME.csv` 의 `slot_mapping_rule` 컬럼에도 기록된다.

---

## 5. 계획기간 밖 후보 처리

`load_start_slot < 0` 이거나 `available_slot >= horizon_hours` 인 후보는
normalization 단계에서 **제외**하고 `dropped_outside_horizon` 으로 보고한다.
조용히 잘라내지 않는다.

---

## 6. 시간대 (timezone)

모든 시각은 **KST 로컬시각, timezone-naive** 로 다룬다.
선사 제출 데이터와 KORAIL 후보가 동일 기준이어야 한다.
UTC 등 다른 기준을 쓰려면 입력 단계에서 변환한 뒤 제출한다.

---

## 7. 알려진 한계

1. MILP 해상도가 1시간이므로 30분 단위 headway 는 표현하지 못한다.
2. 보수적 반올림 때문에 실제 timetable 보다 서비스 가능량이 **과소평가**될 수 있다.
   이는 의도된 방향이다.
3. slot 내 이벤트 순서는 §2 로 고정되어 있으며, 실제 터미널의 세부 작업순서와
   완전히 일치한다고 주장하지 않는다.
