# 비-MILP 비교 입력 데이터

MOVE-AI MILP는 **철도** 최적화 엔진이므로 트럭 비교값을 산출하지 않습니다.
Rail vs Truck 화면에 필요한 트럭 측 값만 이 폴더에서 입력으로 관리합니다.

## `TRUCK_COMPARISON_BY_RECOMMENDATION.csv`

`recommendation_id`를 join key로 canonical recommendation과 결합됩니다.

| 컬럼 | 의미 | 출처 |
|---|---|---|
| `recommendation_id` | canonical recommendation ID | MILP |
| `road_distance_km` | 도로 기준 거리 | 트럭 비교 산출자료 |
| `truck_vehicles` | 필요 차량 대수 | 트럭 비교 산출자료 |
| `truck_cost_krw` | 트럭 운송비 | 트럭 비교 산출자료 |
| `truck_end_to_end_hours` | 상·하차 포함 트럭 소요시간 | 트럭 비교 산출자료 |
| `truck_co2_kg` | 트럭 CO₂e | 트럭 비교 산출자료 |
| `rail_co2_kg` | 철도 CO₂e | 트럭 비교 산출자료 |

## 원칙

- **철도 측 값(운임·수량·시각·열차)은 이 파일에 두지 않습니다.** 전부 canonical MILP 결과에서
  읽습니다. 충돌 시 MILP가 우선합니다.
- `road_distance_km`는 **도로 거리**이며 MILP의 `physical_distance_km`(철도 거리)와 다릅니다.
  둘을 섞어 쓰지 않습니다.
- 철도 소요시간은 이 파일이 아니라 `STOP_WORK_PLAN.csv`의
  출발역 `actual_load_start_time` → 도착역 `actual_available_time`으로 계산합니다.
  트럭도 상·하차를 포함한 end-to-end 기준이라 비교 기준이 같습니다.
