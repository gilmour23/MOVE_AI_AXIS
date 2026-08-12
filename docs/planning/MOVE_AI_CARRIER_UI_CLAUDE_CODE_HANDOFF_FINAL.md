# MOVE-AI 선사(Carrier) UI — Claude Code 구현 최종 핸드오프

> **목적:** 이 문서 하나와 함께 제공되는 `선사UI기획(2).pdf`, 디자인 참고 이미지, `AXIS_MOVEAI_MILP_v7_1_FINAL(3).zip`만 보고 Claude Code가 선사용 웹 인터페이스를 구현할 수 있도록 한다.
>
> **중요:** PDF 안에 들어간 숫자는 레이아웃 설명용 예시다. **실제 화면에 표시되는 모든 숫자는 반드시 MILP 산출물/입력 데이터에서 읽어 계산해야 한다.** 하드코딩 금지.

---

# 0. Claude Code에게 가장 먼저 전달할 핵심 지시

이 프로젝트는 **선사(Carrier) 담당자용 공컨테이너 의사결정지원 UI**다.

사용자가 이 화면에서 하는 일은 다음과 같다.

1. 이번 주 자기 선사의 6개 거점별 공컨 재고 위험을 확인한다.
2. 20FT / 40FT별로 월~일 예상 재고를 자세히 확인한다.
3. MOVE-AI MILP가 계산한 철도 기반 공컨 재배치 제안을 확인한다.
4. 재배치 전/후 자기 선사의 재고 효과를 확인한다.
5. 우측 하단 챗봇을 통해 **이미 계산된 결과에 대한 설명만** 질의한다.

이 UI는 다음을 **하지 않는다.**

- 수요/공급 데이터 업로드 UI를 만들지 않는다. 데이터는 이미 확보된 상태라고 가정한다.
- 최적화 결과 수정 기능을 만들지 않는다.
- 재배치 수량 변경 기능을 만들지 않는다.
- 안전재고 수정 기능을 만들지 않는다.
- 재최적화 버튼을 만들지 않는다.
- 결과 수락/거절/협상 기능을 만들지 않는다.
- Tracking, Notification, 예약/배차 확정 기능을 만들지 않는다.
- 타 선사의 raw demand / supply / inventory / allocation을 절대 노출하지 않는다.

**선사 UI는 read-only Decision Support System이다.**

---

# 1. 세 가지 자료의 우선순위

구현 시 자료의 역할을 혼동하지 말 것.

## 1.1 `선사UI기획(2).pdf` — 정보 구조(IA)와 화면 구성의 정본

PDF가 정의하는 화면의 정보 구조를 우선한다.

현재 핵심 메뉴 구조:

```text
Overview
재고
공컨 최적화
운송비교
```

단, **운송비교 페이지의 상세 구현은 다른 팀원이 담당한다.**
현재 구현 범위에서는:

- 메뉴 항목은 유지
- Overview의 `철도·트럭 운송 비교` 카드 자리는 유지
- `/comparison` route/component의 빈 shell 또는 placeholder까지만 준비
- 실제 비용/시간/탄소 비교 로직과 화면은 구현하지 않음

PDF 3~4페이지는 **별도 페이지가 아니라 하나의 긴 `공컨 최적화` 스크롤 페이지**다.

---

## 1.2 디자인 참고 이미지 — 시각 언어의 참고 자료

참고 이미지의 **레이아웃을 복사하는 것이 아니다.** 다음 시각적 성격만 가져온다.

- 밝고 차분한 enterprise dashboard
- soft gray background
- white / very light gray surface cards
- 14~20px 정도의 rounded card
- 얇은 border + 아주 약한 shadow
- 여백이 충분한 카드 배치
- 상단 navigation은 작고 정돈된 pill/tab 형태
- 정보 밀도가 높아도 시각적으로 답답하지 않게 구성
- 표/그래프/카드의 hierarchy가 명확해야 함
- 보라색/청록색 accent는 제한적으로 사용

**하지 말 것:**

- 참고 이미지의 `Moveon.` 로고/브랜드를 그대로 복사하지 말 것
- 대형 트럭 hero image를 만들지 말 것
- 과도한 glassmorphism, glow, neon, AI스러운 gradient를 사용하지 말 것
- 모든 요소를 알약(pill) 형태로 만들지 말 것
- marketing landing page처럼 만들지 말 것

이 서비스는 물류 실무자용 B2B dashboard다.

---

## 1.3 `AXIS_MOVEAI_MILP_v7_1_FINAL(3).zip` — 모든 숫자의 정본

UI의 숫자, 운송 계획, 재고 전/후, 시간은 MILP 결과물을 정본으로 한다.

특히 다음 원칙을 지킨다.

> **PDF 숫자보다 CSV/JSON 결과가 우선이다.**

예를 들어 PDF에 `40FT 42개`, `재배치 후 부족 0`이라고 적혀 있어도 실제 현재 결과가 다르면 실제 결과를 표시한다.

---

# 2. 현재 MILP 패키지의 실제 의미

`00_START_HERE.md` 기준 핵심 개념:

- 여러 선사가 같은 planning cycle의 재고/수요/공급을 제출한다.
- 선사별 공컨 ownership은 유지된다.
- 여러 선사의 공컨을 같은 신규 철도 서비스 capacity에 공동 적재할 수 있다.
- 모든 선사의 Service Need를 **하나의 Joint Multi-Carrier MILP**에서 동시에 최적화한다.
- 선사 화면에는 자기 회사 권고안만 제공한다.
- KORAIL 화면과 선사 화면은 동일 MILP solution의 다른 관점이다.
- 챗봇은 최적화 controller가 아니라 read-only explanation layer다.

현재 기본 결과의 중요한 메타:

```text
scenario = AXIS_INTEGRATED
planning horizon = 168시간 = 1주
MILP slot = 1시간
carrier data source = SYNTHETIC_CARRIER_LEVEL_DATA
candidate timetable source = PROTOTYPE_SYNTHETIC
```

따라서 데모 UI에는 필요 시 아주 작게 다음과 같은 badge를 노출할 수 있다.

```text
Synthetic demo data
Prototype timetable
```

실제 데이터로 교체되면 `SUMMARY.json` 값에 따라 자동으로 사라지도록 한다.

---

# 3. 가장 중요한 단위 규칙 — TEU와 컨테이너 수량을 섞지 말 것

선사 UI에서 **개별 공컨 재고/수요/공급/재배치량은 컨테이너 개수(box count)**로 표시한다.

## 화면 표기

```text
20FT 8개
40FT 9개
예상 부족 12개
재배치 물량 16개
```

## 데이터 필드

- 개수: `quantity_boxes`
- TEU: `quantity_teu`

40FT 1개는 내부적으로 2TEU다.

예:

```text
40FT quantity_boxes = 9
quantity_teu = 18
```

**절대 `40FT 9TEU`라고 표시하지 말 것.**

현재 우리가 만드는 선사 재고/최적화 UI에서는 기본적으로 `개`를 사용한다.
TEU는 향후 운송비교/열차 capacity 등의 집계 영역에서만 필요할 때 사용한다.

---

# 4. 시간 표현 규칙

## 4.1 재고 화면

원본은 1시간 단위지만 사용자가 정한 UI 기준은 **요일 단위**다.

따라서 재고 페이지에서는:

- 월 / 화 / 수 / 목 / 금 / 토 / 일
- 일별 예상 재고
- 주간 예상 수요/공급

수준으로 보여준다.

시간별 demand chart는 만들지 않는다.

## 4.2 철도 재배치 계획

철도 후보/최적화 결과에는 시간 단위 데이터가 있으므로 **정확한 출발/도착시간을 보여준다.**

예:

```text
08.10 (월) 06:00 출발
08.10 (월) 13:00 도착
08.10 (월) 16:00 사용 가능
```

MILP에서 시간의 의미가 다르다.

- `departure_time`: 열차 출발
- `arrival_time`: 물리 도착
- `available_time`: 하화가 끝나 선사가 실제 사용 가능한 시각

선사 입장에서는 `available_time`이 중요하다.

PDF 레이아웃을 크게 변경하고 싶지 않다면 `도착시간` 컬럼은 그대로 두고:

- row expand
- tooltip
- 상세 패널

중 하나에서 `사용 가능: HH:mm`을 반드시 노출한다.

모든 시각은 KST 기준이다.

---

# 5. 프로젝트 scope

## 구현해야 함

- 공통 App Shell / Header / Navigation
- Overview 페이지
- 재고 페이지
- 공컨 최적화 페이지(긴 scroll page)
- 운송비교 route shell/placeholder
- 우측 하단 챗봇 floating button + drawer shell
- MILP 결과 파일을 읽는 backend/data adapter
- 자사 데이터 필터링
- loading / empty / error state

## 구현하지 않음

- 운송비교 상세 logic
- 데이터 입력/업로드
- MILP controller UI
- 재최적화
- negotiation
- 수락/거절
- tracking
- notification
- 다른 선사 raw data 조회

---

# 6. 추천 기술 스택

기존 프론트 프로젝트가 없다면 다음으로 시작한다.

## Frontend

```text
React
TypeScript
Vite
Recharts
Lucide React
CSS Modules 또는 Tailwind CSS
```

Tailwind를 쓰더라도 default template 느낌이 나지 않게 디자인 token을 직접 정의한다.

## Backend

```text
FastAPI
pandas
pydantic
uvicorn
```

이유:

- MILP 자체가 Python 기반
- CSV/JSON parsing이 쉽다
- frontend에 전체 multi-carrier CSV를 직접 넘기지 않고 backend에서 carrier isolation 가능

## 절대 하지 말 것

프론트 브라우저에서 `CARRIER_INVENTORY_TIMELINE.csv` 전체를 직접 읽은 뒤 carrier filter를 하지 않는다.

그렇게 하면 브라우저에 다른 선사의 데이터까지 전달된다.

---

# 7. 권장 repository 구조

기존 프로젝트가 있다면 구조를 강제로 바꾸지 말고 아래 개념만 반영한다.

```text
project-root/
│
├─ optimizer/
│  └─ AXIS_MOVEAI_MILP_v7_1_FINAL/
│     ├─ 00_START_HERE.md
│     ├─ 01_DOCS/
│     ├─ 02_CODE/
│     ├─ 03_INPUT_DATA/
│     ├─ 04_MODEL_INPUTS/
│     └─ 05_RESULTS/
│        └─ AXIS_INTEGRATED/
│
├─ backend/
│  ├─ app.py
│  ├─ config.py
│  ├─ models.py
│  ├─ result_store.py
│  ├─ selectors/
│  │  ├─ overview.py
│  │  ├─ inventory.py
│  │  └─ optimization.py
│  └─ chat/
│     ├─ router.py
│     └─ provider.py        # 추후 API 연결
│
└─ frontend/
   ├─ src/
   │  ├─ app/
   │  │  ├─ App.tsx
   │  │  └─ router.tsx
   │  ├─ components/
   │  │  ├─ layout/
   │  │  │  ├─ AppShell.tsx
   │  │  │  ├─ TopNav.tsx
   │  │  │  └─ PageContainer.tsx
   │  │  ├─ common/
   │  │  │  ├─ Card.tsx
   │  │  │  ├─ StatusBadge.tsx
   │  │  │  ├─ SegmentedControl.tsx
   │  │  │  ├─ DataTable.tsx
   │  │  │  ├─ LoadingSkeleton.tsx
   │  │  │  └─ EmptyState.tsx
   │  │  ├─ map/
   │  │  │  └─ RailHubMap.tsx
   │  │  ├─ inventory/
   │  │  │  ├─ WeeklyInventoryMatrix.tsx
   │  │  │  ├─ HubSelector.tsx
   │  │  │  ├─ WeeklyInventoryLine.tsx
   │  │  │  └─ WeeklyInventorySummary.tsx
   │  │  ├─ optimization/
   │  │  │  ├─ ServiceNeedTable.tsx
   │  │  │  ├─ RecommendationTable.tsx
   │  │  │  ├─ RecommendationRouteDetail.tsx
   │  │  │  └─ InventoryImpactTable.tsx
   │  │  └─ chatbot/
   │  │     ├─ ChatFloatingButton.tsx
   │  │     └─ ChatDrawer.tsx
   │  ├─ pages/
   │  │  ├─ OverviewPage.tsx
   │  │  ├─ InventoryPage.tsx
   │  │  ├─ OptimizationPage.tsx
   │  │  └─ ComparisonPlaceholderPage.tsx
   │  ├─ api/
   │  │  ├─ client.ts
   │  │  ├─ carrier.ts
   │  │  └─ chat.ts
   │  ├─ types/
   │  │  └─ domain.ts
   │  ├─ config/
   │  │  └─ hubMeta.ts
   │  └─ styles/
   │     ├─ tokens.css
   │     └─ globals.css
   └─ ...
```

---

# 8. ZIP 경로 주의 — cross-platform

현재 zip member 이름에 Windows `\` separator가 들어 있다.

Linux/macOS에서 Python `zipfile.extractall()`을 사용하면 `01_DOCS\...`가 실제 directory가 아니라 **backslash가 포함된 파일명**으로 풀릴 수 있다.

따라서 Claude Code가 Linux/WSL에서 작업한다면 extraction helper를 만들 것.

개념:

```python
normalized = member.filename.replace("\\", "/")
```

이후 정상 디렉터리 구조로 저장한다.

Windows 환경이라면 동봉 `run_*.bat` 사용 가능.

---

# 9. 데이터 파일 — UI가 실제로 읽어야 할 파일

기본 결과 디렉터리:

```text
05_RESULTS/AXIS_INTEGRATED/
```

## 9.1 `SUMMARY.json`

용도:

- scenario metadata
- synthetic/prototype badge
- 전체 모델 결과 meta

중요 필드:

```text
scenario
candidate_timetable_source
carrier_data_source
selected_train_count
recommendation_count
all_stages_proven_optimal
carrier_korail_view_consistent
```

---

## 9.2 `CARRIER_INVENTORY_TIMELINE.csv`

가장 중요한 재고 화면 source.

컬럼:

```text
carrier_id
timestamp
hub_code
container_size
demand
external_supply
rail_inbound_boxes
rail_outbound_boxes
baseline_inventory
post_rail_inventory
baseline_unmet_demand
post_rail_unmet_demand
```

의미:

- `baseline_*` = MOVE-AI 철도 재배치 적용 전
- `post_rail_*` = MOVE-AI 철도 재배치 적용 후

**중요:** 모델 재고는 stockout 발생 시 음수로 내려가지 않고 0에서 clip된다.
부족량은 별도 `*_unmet_demand`로 저장한다.

따라서 UI에서 `재고 -24` 같은 숫자를 실제 결과인 것처럼 만들지 않는다.

정확한 표현:

```text
예상 재고 0개
예상 부족 24개
```

또는 셀:

```text
0
부족 24
```

---

## 9.3 `INVENTORY_IMPACT_SUMMARY.csv`

컬럼:

```text
carrier_id
hub_code
container_size
baseline_stockout_boxes
post_rail_stockout_boxes
stockout_reduction_boxes
minimum_baseline_inventory
minimum_post_rail_inventory
rail_inbound_boxes
rail_outbound_boxes
```

용도:

- 거점별 재배치 영향
- 부족 감소량
- 철도 유입/반출량

---

## 9.4 `CARRIER_RECOMMENDATIONS_<CARRIER>.csv`

예: `CARRIER_RECOMMENDATIONS_CARRIER_A.csv`

선사 화면의 **공식 자사 재배치 추천 source**.

중요 컬럼:

```text
recommendation_id
carrier_id
container_size
quantity_boxes
quantity_teu
origin_hub
origin_name
destination_hub
destination_name
train_id
departure_time
arrival_time
available_time
need_count
service_due_time_earliest
service_due_time_latest
physical_distance_km
tariff_distance_km
estimated_rail_charge_krw
participating_carrier_count
train_load_factor
```

선사 UI에서 수량은 `quantity_boxes` 사용.

---

## 9.5 `SERVICE_NEED_RESULT.csv`

용도:

- `재배치 필요 현황`
- 어떤 거점/규격/시점에 공컨 need가 생겼는지
- 철도로 얼마나 cover됐는지

중요 컬럼:

```text
need_id
carrier_id
destination
destination_name
container_size
quantity
teu
due_time
need_reason
rail_served_boxes
rail_unserved_boxes
```

페이지 3 첫 테이블은 **현재 carrier만 필터링하고 day/hub/size로 group**한다.

---

## 9.6 `KORAIL_TRAIN_PLAN.csv`

용도:

- recommendation row를 클릭했을 때 해당 train route 표시
- train path/공통 운행 시간 정보

중요 컬럼:

```text
train_id
route
service_family
origin_terminal
destination_terminal
actual_origin_departure
actual_final_arrival
candidate_source
work_stops
```

**주의:** 선사 UI에서는 이 파일의 train-level aggregate capacity를 핵심으로 보여줄 필요가 없다.
선사는 자기 공컨 이동이 중심이다.

---

## 9.7 `STOP_WORK_PLAN.csv`

용도:

- train route detail의 정차역/시각

사용할 필드:

```text
train_id
stop_sequence
hub
hub_name
actual_arrival_time
actual_departure_time
actual_available_time
```

**절대 선사 화면에 `load_teu`, `unload_teu`를 그대로 보여주지 말 것.**
이 값은 여러 선사 물량의 train total일 수 있다.

자사 상/하차량은 `CARRIER_RECOMMENDATIONS_<CARRIER>.csv`를 해당 train_id로 묶어서 계산한다.

---

## 9.8 `RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv`

챗봇의 근거 데이터.

다른 carrier context 파일을 절대 섞지 않는다.

---

## 9.9 `carrier_initial_inventory.csv`

용도:

- 계획기간 시작 시 실제 초기 공컨 개수
- 주간 재고 증감 계산 기준

컬럼:

```text
carrier_id
hub_code
hub_name
container_size
initial_inventory
```

---

# 10. 선사 격리(privacy) — 최우선 보안 요구사항

개발 데모에서는 `CARRIER_A`를 기본 carrier로 쓸 수 있다.

```text
DEMO_CARRIER_ID=CARRIER_A
```

하지만 구조는 로그인 carrier를 받을 수 있도록 만든다.

## backend 원칙

```text
/api/carrier/CARRIER_A/...
```

요청이 오면 backend에서 먼저 carrier filter 후 aggregate한다.

프론트에 다음 데이터를 보내지 말 것.

- 다른 carrier의 demand
- 다른 carrier의 supply
- 다른 carrier의 inventory
- 다른 carrier의 recommendation
- 전체 `CARRIER_ALLOCATION.csv`

공동운송 관련 다음 집계값은 허용:

```text
participating_carrier_count
train_load_factor
```

개발 편의를 위한 carrier selector가 필요하다면 **dev mode에서만** 보여준다.
실제 선사 사용자 화면에서는 carrier dropdown을 노출하지 않는다.

---

# 11. Backend API 제안

## `GET /api/meta`

응답 예:

```json
{
  "scenario": "AXIS_INTEGRATED",
  "horizonStart": "2026-08-10T00:00:00",
  "horizonEnd": "2026-08-16T23:00:00",
  "carrierDataSource": "SYNTHETIC_CARRIER_LEVEL_DATA",
  "candidateTimetableSource": "PROTOTYPE_SYNTHETIC"
}
```

---

## `GET /api/carrier/{carrierId}/overview`

응답 구조 예:

```json
{
  "carrierId": "CARRIER_A",
  "hubs": [
    {
      "hubCode": "YAKMOK",
      "hubName": "약목역 CY",
      "sizes": {
        "20FT": {
          "weekEndInventory": 2,
          "weeklyShortage": 25
        },
        "40FT": {
          "weekEndInventory": 0,
          "weeklyShortage": 15
        }
      },
      "hasShortage": true
    }
  ],
  "recommendationPreview": []
}
```

---

## `GET /api/carrier/{carrierId}/inventory?mode=baseline&size=20FT`

`mode`:

```text
baseline  = 재배치 전
postRail  = 재배치 후
```

응답 예:

```json
{
  "size": "20FT",
  "days": ["월", "화", "수", "목", "금", "토", "일"],
  "hubs": [
    {
      "hubCode": "YAKMOK",
      "hubName": "약목역 CY",
      "daily": [
        {"date":"2026-08-10","closingInventory":0,"unmetDemand":2},
        {"date":"2026-08-11","closingInventory":0,"unmetDemand":5}
      ]
    }
  ]
}
```

---

## `GET /api/carrier/{carrierId}/inventory/{hubCode}/{size}/summary?mode=baseline`

예:

```json
{
  "weeklyDemand": 64,
  "weeklyExternalSupply": 29,
  "initialInventory": 37,
  "weekEndInventory": 2,
  "weeklyInventoryChange": -35,
  "minimumDisplayedInventory": 0,
  "weeklyUnmetDemand": 25,
  "shortageDays": ["월", "화", "수", "목", "금", "토", "일"]
}
```

---

## `GET /api/carrier/{carrierId}/optimization`

응답 구조:

```json
{
  "needs": [],
  "recommendations": [],
  "impacts": [],
  "postRailInventory": {}
}
```

---

## `GET /api/carrier/{carrierId}/optimization/recommendations/{recommendationId}`

추천 상세 + train route.

---

# 12. 요일별 재고 계산 규칙 — 반드시 동일하게 구현

UI는 시간별 데이터를 그대로 보여주지 않는다.

## 12.1 하루 예상재고

하루의 마지막 timestamp(일반적으로 23:00 slot)의 inventory를 **그날의 closing inventory**로 사용한다.

baseline page:

```text
baseline_inventory
```

post optimization section:

```text
post_rail_inventory
```

Pseudo:

```python
daily_closing = (
    timeline
    .sort_values("timestamp")
    .groupby(["carrier_id", "hub_code", "container_size", "date"])
    .tail(1)
)
```

## 12.2 하루 부족량

해당 날짜의 hourly unmet를 합산한다.

```text
baseline day shortage = Σ baseline_unmet_demand
post day shortage     = Σ post_rail_unmet_demand
```

따라서 matrix cell은 예를 들어:

```text
0
부족 5개
```

처럼 표현할 수 있다.

## 12.3 주간 예상 수요

```text
Σ demand
```

단위: 개

## 12.4 주간 예상 공급

```text
Σ external_supply
```

단위: 개

`postRail` 화면에서도 이 값은 **외부 공급**이다.
철도 유입량과 섞지 않는다.

## 12.5 주간 재고 증감

```text
weekEndInventory - initial_inventory
```

## 12.6 주간 최저 예상재고

사용자가 요일 단위 화면을 원했으므로 **화면에 표시된 7개 daily closing 값의 minimum**으로 한다.

즉 UI summary는 시간별 `minimum_baseline_inventory`가 아니라 visible daily values와 일치시킨다.

## 12.7 부족 예상

```text
weeklyUnmetDemand = Σ unmet_demand
```

0이면:

```text
부족 예상 없음
```

0보다 크면:

```text
예상 부족 25개
```

필요하면 아래 작은 텍스트:

```text
부족 발생 요일: 월·화·수...
```

---

# 13. Hub 정의

6개 hub는 고정한다.

```ts
const HUBS = [
  { code: 'UIWANG',    name: '의왕ICD(오봉역)' },
  { code: 'BUGANG',    name: '부강화물역 CY' },
  { code: 'YAKMOK',    name: '약목역 CY' },
  { code: 'DONGSAN',   name: '동산역 CY' },
  { code: 'BUSAN',     name: '부산신항' },
  { code: 'GWANGYANG', name: '신광양항' },
]
```

노선 schematic:

```text
경부축:
UIWANG → BUGANG → YAKMOK → BUSAN

남서/호남축:
UIWANG → BUGANG → DONGSAN → GWANGYANG
```

실제 lat/lon은 MILP 패키지에 정본으로 제공되지 않는다.

따라서 초기 UI에서는 외부 지도 API에 의존하지 말고 **schematic SVG network**로 구현하는 것을 권장한다.

추후 실제 좌표가 제공되면 `hubMeta.ts`의 좌표만 교체할 수 있게 만든다.

---

# 14. 공통 App Shell / 디자인 시스템

## 14.1 화면 기준

primary demo target:

```text
1440px desktop
```

- app max width: 1440~1520px
- page outer padding: 24~32px
- card gap: 16~20px
- section gap: 28~36px

## 14.2 디자인 token 제안

참고 이미지의 느낌을 가져오되 프로젝트용으로 조정한다.

```css
--bg-app:        #eef1f4;
--bg-shell:      #f7f8f8;
--surface:       #ffffff;
--surface-soft:  #f5f7f8;
--border:        #e2e6e9;
--text:          #12161b;
--text-muted:    #737b84;
--brand:         #1f6f8b;
--brand-dark:    #154b61;
--accent:        #8a62d8;
--success:       #5aa56a;
--warning:       #d39b43;
--danger:        #c75b5b;
```

## 14.3 Card

```text
border-radius: 16~18px
border: 1px solid var(--border)
box-shadow: 매우 약하게
background: white
```

## 14.4 Typography

```text
system-ui / Pretendard / Noto Sans KR fallback
```

- page title: 24~28px / semibold
- section title: 18~20px / semibold
- table header: 13~14px / semibold
- body: 14px
- metric: 22~28px / semibold

## 14.5 Navigation

상단 중앙 또는 좌측 정렬된 compact navigation.

```text
[Overview] [재고] [공컨 최적화] [운송비교]
```

선택 메뉴:

- white/brand-soft pill
- icon + text

추천 icons:

```text
Overview       LayoutDashboard
재고           Boxes
공컨 최적화    Route / GitBranch
운송비교       GitCompareArrows
```

## 14.6 상태 표현

정의되지 않은 safety threshold를 임의로 만들지 않는다.

현재 data로 확실히 말할 수 있는 상태:

```text
정상      weekly unmet demand = 0
부족 예상 weekly unmet demand > 0
```

`주의`, `위험`, `안전재고` threshold를 임의로 만들지 말 것.

---

# 15. Page 1 — Overview 상세 구현

PDF 1페이지 structure가 정본이다.

Desktop grid:

```text
┌───────────────────────────────┬────────────────────────────┐
│                               │ 거점별 공컨 재고 현황       │
│ 지도 / 철도 network           │                            │
│                               ├────────────────────────────┤
│                               │ 철도·트럭 운송 비교         │
└───────────────────────────────┴────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│ 이번 주 MOVE-AI 재배치 권고                                │
└────────────────────────────────────────────────────────────┘
```

## 15.1 왼쪽 — `RailHubMap`

비율 약 55~60%.

표시:

- 6 hub node
- 두 corridor line
- 각 node 이름
- shortage가 있으면 red indicator

### node 클릭

compact popover:

```text
약목역 CY
20FT  예상 부족 25개
40FT  예상 부족 15개

[재고 상세 보기]
```

부족량 source:

```text
CARRIER_INVENTORY_TIMELINE baseline_unmet_demand weekly sum
```

또는 `INVENTORY_IMPACT_SUMMARY.baseline_stockout_boxes`.

`재고 상세 보기` 클릭 시:

```text
/inventory?hub=YAKMOK&size=20FT
```

## 15.2 오른쪽 상단 — `전체 거점별 공컨 재고 현황`

추천 visual:

- 6 hub compact horizontal bar/list
- 각 hub에 20FT / 40FT 주말 예상재고
- shortage badge

예:

```text
의왕ICD     20FT 14   40FT 4
부산신항    20FT 82   40FT 73
약목        20FT 2    40FT 0   [부족 예상]
```

데이터:

- 마지막 일자 `baseline_inventory` closing
- weekly baseline unmet로 shortage badge

**Overview도 optimization 적용 전 baseline 기준으로 보여주어야 Page 2와 일관된다.**

## 15.3 오른쪽 하단 — `철도·트럭 운송 비교`

이 영역은 다른 팀원 담당.

현재 구현:

- card shell
- 제목
- placeholder/empty component
- `상세 비교 →` route link

실제 비교 숫자를 임의로 만들지 않는다.

## 15.4 하단 full width — `이번 주 MOVE-AI 재배치 권고`

자사 recommendation preview.

source:

```text
CARRIER_RECOMMENDATIONS_<CARRIER>.csv
```

sort:

```text
departure_time ASC
```

3~5개 정도를 compact row로 보여준다.

row 내용:

```text
의왕ICD → 약목역 CY
20FT · 7개
08.10 06:00 출발 → 13:00 도착
사용 가능 16:00
```

row click:

```text
/optimization#REC0004
```

PDF에 있는 “들리는 역” 정보는 Overview에 모두 펼치지 말고 route summary/tooltip 수준으로 처리한다.

---

# 16. Page 2 — 재고

이 화면은 **MOVE-AI 적용 전 baseline inventory**를 보여준다.

페이지 설명 예:

```text
규격별 주간 예상 재고
현재 계획의 수요·외부 공급 기준
```

## 16.1 상단 size tabs

```text
[20피트] [40피트]
```

내부 값:

```text
20FT
40FT
```

default: 20FT

선택 상태는 URL query에 반영하는 것을 권장:

```text
/inventory?size=20FT&hub=UIWANG
```

## 16.2 Weekly Inventory Matrix

PDF의 큰 표.

```text
거점 | 월 | 화 | 수 | 목 | 금 | 토 | 일
```

6 rows 고정.

cell main value:

```text
daily closing baseline_inventory
```

해당 day에 unmet가 있으면:

```text
0
부족 3
```

또는 red dot + tooltip.

숫자 자체를 음수로 만들지 않는다.

### cell style

- normal: white/soft gray
- daily unmet > 0: light red background + red label
- selected hub row: subtle brand highlight

## 16.3 HubSelector

표 아래 PDF처럼 6개 button/tab:

```text
[의왕ICD] [부강] [약목] [동산] [부산신항] [신광양항]
```

위 matrix row click과 같은 state를 공유한다.

## 16.4 하단 왼쪽 — Weekly Inventory Line

선택한 hub + size의 7개 daily closing baseline inventory를 line chart로 보여준다.

- x = 월~일
- y = 컨테이너 개수
- 한 개 line만
- chart fill/gradient는 아주 약하게 또는 사용하지 않음
- tooltip: `수요일 · 2개`
- unmet day에는 point를 red marker로 표시 가능

**시간별 chart 금지.**

## 16.5 하단 오른쪽 — Weekly Summary

PDF의 요약 box.

표시 항목:

```text
주간 예상 수요        N개
주간 예상 공급        N개
주간 재고 증감        +N개 / -N개
주간 최저 예상재고    N개
부족 예상             없음 / N개
```

계산은 §12 규칙 사용.

부족이 있으면:

```text
예상 부족 25개
부족 발생 요일 월·화·수...
```

summary box는 card 내부에서 숫자 hierarchy를 크게 잡는다.

---

# 17. Page 3 — 공컨 최적화

PDF 3~4페이지는 **한 화면**이다.

페이지는 길게 scroll된다.

큰 흐름:

```text
재배치 필요 현황
↓
철도 기반 공컨 재배치 제안
↓
거점별 재배치 영향
↓
재배치 이후 예상 재고 현황
↓
선택 거점 상세(재고 페이지와 동일 패턴)
```

---

## 17.1 Section A — `재배치 필요 현황`

source:

```text
SERVICE_NEED_RESULT.csv
```

filter:

```text
carrier_id == loggedInCarrier
```

group:

```text
destination_name
container_size
due_date
```

aggregation:

```text
필요량 = Σ quantity   # boxes
```

PDF 표 구조:

```text
거점 | 규격 | 요일 | 필요량
```

요일은 `due_time`의 날짜를 KST 기준 한글 요일로 변환.

필요량 단위는 `개`.

**주의:** Service Need가 있다고 해서 전부 rail로 해결된 것은 아니다.
현재 integrated result도 residual unserved가 존재할 수 있다.

따라서 필요하면 row tooltip 또는 작은 subtext로:

```text
철도 배정 N개 / 미배정 M개
```

를 `rail_served_boxes`, `rail_unserved_boxes`로 제공한다.

`모두 해결됨`을 하드코딩하지 않는다.

---

## 17.2 Section B — `철도 기반 공컨 재배치 제안`

source:

```text
CARRIER_RECOMMENDATIONS_<CARRIER>.csv
```

PDF 표 structure 유지:

```text
출발 | 도착 | 규격 | 물량 | 출발시간 | 도착시간
```

실제 data mapping:

```text
출발       origin_name
도착       destination_name
규격       container_size
물량       quantity_boxes + '개'
출발시간   departure_time
도착시간   arrival_time
```

row 내부/tooltip/detail에서 추가:

```text
사용 가능   available_time
열차 ID     train_id
공동 운송   participating_carrier_count개 선사
적재율      train_load_factor
```

공동 선사 수와 적재율은 집계 정보이므로 표시 가능하지만 핵심 table에는 필수가 아니다.

### 중요

`candidate_timetable_source == PROTOTYPE_SYNTHETIC`이면

```text
프로토타입 운행후보 기준
```

badge/tooltip을 표시하고 “KORAIL 실제 운행시각”이라고 쓰지 않는다.

---

## 17.3 Recommendation row expand — 선사 관점 운송 경로 상세

PDF 1페이지의 “운송 시간, 들리는 역, 해당 역에서 어떤 규격의 컨을 내리는지” 요구를 여기서 구체적으로 구현한다.

row click 시 accordion/expand panel.

### route source

```text
KORAIL_TRAIN_PLAN.csv -> same train_id -> route
STOP_WORK_PLAN.csv -> same train_id -> stop sequence/time
```

### 매우 중요한 privacy rule

`STOP_WORK_PLAN.load_teu/unload_teu`는 train 전체 물량이므로 **선사 UI에 사용하지 않는다.**

자사 load/unload는 현재 carrier recommendation들을 같은 train_id로 aggregate한다.

Pseudo:

```text
for each stop:
  myLoad20 = sum(quantity_boxes where origin_hub == stop && size == 20FT)
  myLoad40 = sum(quantity_boxes where origin_hub == stop && size == 40FT)
  myUnload20 = sum(quantity_boxes where destination_hub == stop && size == 20FT)
  myUnload40 = sum(quantity_boxes where destination_hub == stop && size == 40FT)
```

### UI example

```text
CAND0156

의왕ICD          부강           약목             부산신항
06:00 출발  ───→ 08:00 도착 ───→ 13:00 도착 ───→ 18:00 도착
+ 20FT 7개                      - 20FT 7개
+ 40FT 3개                      - 40FT 3개
                                사용 가능 16:00
```

자사 action이 없는 stop은 station + 시간만 표시.

다른 선사의 적재/하역량은 표시하지 않는다.

---

## 17.4 Section C — `거점별 재배치 영향`

source:

```text
INVENTORY_IMPACT_SUMMARY.csv
```

filter current carrier.

PDF의 단순 구조를 유지하면서 data semantics를 정확히 해야 한다.

추천 column:

```text
거점
규격
역할
재배치 전 최저재고
이동량
재배치 후 최저재고
```

### 역할 계산

```text
rail_outbound_boxes > 0 && rail_inbound_boxes == 0 -> 출발
rail_inbound_boxes > 0 && rail_outbound_boxes == 0 -> 도착
둘 다 > 0                                    -> 출발·도착
둘 다 0                                      -> 영향 없음
```

### 이동량

출발:

```text
-rail_outbound_boxes
```

도착:

```text
+rail_inbound_boxes
```

둘 다 있으면:

```text
+N / -M
```

### 전/후 재고

모델에는 canonical hourly minimum이 있으나 PDF/재고 UI는 daily granularity다.

화면 일관성을 위해 `재배치 전/후 최저재고`는 **daily closing matrix에서 계산한 weekly min**을 우선 사용한다.

그리고 tooltip/detail에 다음 canonical effect를 추가할 수 있다.

```text
재배치 전 총 부족량    baseline_stockout_boxes
재배치 후 총 부족량    post_rail_stockout_boxes
부족 감소              stockout_reduction_boxes
```

### 절대 하지 말 것

```text
재배치 후 = 재배치 전 + 이동량
```

을 단순 산술식으로 계산하지 않는다.

재고는 수요/공급 및 이동 시각을 모두 반영하기 때문에 `post_rail_inventory` 결과를 그대로 사용해야 한다.

---

## 17.5 Section D — `재배치 이후 예상 재고 현황`

PDF 4페이지.

Page 2와 **동일한 UI component를 재사용**한다.

차이는 data field만:

```text
Page 2: baseline_inventory / baseline_unmet_demand
Page 3 after: post_rail_inventory / post_rail_unmet_demand
```

따라서 `WeeklyInventoryMatrix`, `WeeklyInventoryLine`, `WeeklyInventorySummary`에 `mode` prop을 준다.

```tsx
<WeeklyInventoryMatrix mode="baseline" />
<WeeklyInventoryMatrix mode="postRail" />
```

### post summary

```text
주간 예상 수요          Σ demand
주간 예상 공급          Σ external_supply
철도 유입/반출          rail_inbound / rail_outbound (작은 subtext 권장)
주간 최저 예상재고      min daily post closing
부족 예상               Σ post_rail_unmet_demand
```

PDF의 5줄 summary layout은 유지하되, post 화면에서는 `철도 유입/반출` 정보가 의미 있으므로 `재고 증감`의 subtext 또는 tooltip으로 추가한다.

---

# 18. Overview → Inventory → Optimization 연결 UX

서비스가 한 흐름으로 느껴져야 한다.

## Overview map node

```text
약목 부족 예상
→ 재고 상세 보기
→ /inventory?hub=YAKMOK&size=20FT
```

## Inventory shortage cell

해당 hub/size에 unmet가 있으면 optional link:

```text
MOVE-AI 재배치안 보기 →
```

클릭:

```text
/optimization?hub=YAKMOK&size=20FT
```

## Overview recommendation preview

row 클릭:

```text
/optimization#REC0004
```

해당 recommendation row highlight.

---

# 19. 챗봇 — 반드시 우측 하단 floating interface

PDF 우측 하단 robot icon 위치를 유지한다.

## 19.1 UI

기본:

```text
fixed bottom: 24px
right: 24px
56px circle button
```

open 시:

```text
right-side drawer
width 380~430px
height 70~85vh
```

header:

```text
MOVE-AI Copilot
조회·설명 전용
```

추천 질문 예:

```text
왜 약목으로 공컨을 보내나요?
우리 40FT 재고는 어떻게 바뀌나요?
이 공컨은 언제 사용 가능한가요?
어떤 열차에 배정됐나요?
```

---

## 19.2 현재 API가 없을 때

지금은 API를 모른다.

따라서 provider abstraction만 구현한다.

```ts
interface ChatProvider {
  sendMessage(input: {
    carrierId: string;
    message: string;
    conversationId?: string;
  }): Promise<ChatResponse>
}
```

frontend는 자기 backend `/api/chat`만 호출한다.

**API key를 frontend env에 넣지 않는다.**

backend env:

```text
CHAT_API_URL=
CHAT_API_KEY=
```

미설정 시 backend:

```text
503 CHAT_API_NOT_CONFIGURED
```

frontend에서는:

```text
챗봇 API가 아직 연결되지 않았습니다.
API 연결 후 현재 최적화 결과를 기반으로 질의할 수 있습니다.
```

라고 보여준다.

가짜 AI 답변을 하드코딩하지 않는다.

---

## 19.3 API 연결 후 반드시 지켜야 할 read-only 규칙

챗봇은 다음 데이터만 current carrier 기준으로 조회한다.

```text
CARRIER_RECOMMENDATIONS_<CARRIER>.csv
RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv
CARRIER_INVENTORY_TIMELINE.csv (current carrier only)
INVENTORY_IMPACT_SUMMARY.csv (current carrier only)
CARRIER_SERVICE_SUMMARY.csv (current carrier only)
SERVICE_NEED_RESULT.csv (current carrier only)
```

다음 요청은 실행하지 않는다.

```text
수량 바꿔줘
다시 계산해줘
안전재고 바꿔줘
다른 열차로 바꿔줘
```

답변 예:

```text
현재 Copilot은 최적화 결과를 조회하고 설명하는 기능만 제공합니다.
최적화 수량 또는 조건을 변경하거나 재계산하지 않습니다.
```

LLM이 숫자를 새로 만들면 안 된다.

---

# 20. TypeScript domain type 예시

```ts
export type ContainerSize = '20FT' | '40FT';
export type InventoryMode = 'baseline' | 'postRail';

export interface DailyInventoryPoint {
  date: string;
  weekday: string;
  closingInventory: number;
  unmetDemand: number;
}

export interface HubWeeklyInventory {
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  daily: DailyInventoryPoint[];
}

export interface WeeklyInventorySummary {
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  weeklyDemand: number;
  weeklyExternalSupply: number;
  initialInventory: number;
  weekEndInventory: number;
  weeklyInventoryChange: number;
  minimumDisplayedInventory: number;
  weeklyUnmetDemand: number;
  shortageDays: string[];
}

export interface CarrierRecommendation {
  recommendationId: string;
  size: ContainerSize;
  quantityBoxes: number;
  originHub: string;
  originName: string;
  destinationHub: string;
  destinationName: string;
  trainId: string;
  departureTime: string;
  arrivalTime: string;
  availableTime: string;
  participatingCarrierCount: number;
  trainLoadFactor: number;
}

export interface InventoryImpact {
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  role: '출발' | '도착' | '출발·도착' | '영향 없음';
  baselineMinDisplayedInventory: number;
  postRailMinDisplayedInventory: number;
  inboundBoxes: number;
  outboundBoxes: number;
  baselineStockoutBoxes: number;
  postRailStockoutBoxes: number;
  stockoutReductionBoxes: number;
}
```

---

# 21. 현재 bundled result를 이용한 sanity check — CARRIER_A

이 값은 **UI에 hardcode하지 않는다.**
backend adapter가 실제 결과를 올바르게 읽는지 확인하는 테스트 fixture로만 사용한다.

## CARRIER_A recommendations

현재 `CARRIER_RECOMMENDATIONS_CARRIER_A.csv`에는 5건이 있다.

```text
부강화물역 CY → 신광양항   20FT 8개
부산신항 → 약목역 CY        20FT 16개
부산신항 → 약목역 CY        40FT 9개
의왕ICD(오봉역) → 약목역 CY 20FT 7개
의왕ICD(오봉역) → 약목역 CY 40FT 3개
```

대표 시간 예:

```text
의왕ICD → 약목
출발 2026-08-10 06:00
도착 2026-08-10 13:00
사용 가능 2026-08-10 16:00
```

## CARRIER_A baseline weekly stockout totals

현재 결과에서:

```text
동산 20FT      1개
신광양항 20FT  11개
약목 20FT      25개
약목 40FT      15개
```

## optimization 후 residual stockout

```text
동산 20FT      1개
신광양항 20FT  3개
약목 20FT      2개
약목 40FT      3개
```

따라서 현재 bundled result 기준으로는 **최적화 후 부족이 완전히 0이 아니다.**

UI에서 `최적화 후 부족 0` 같은 문구를 하드코딩하면 실패다.

## CARRIER_A recommendation quantity consistency

```text
20FT boxes = 8 + 16 + 7 = 31개
40FT boxes = 9 + 3 = 12개
총 boxes = 43개
TEU = 55
```

프론트 수량 표시에서 box/TEU 혼동이 없는지 테스트한다.

---

# 22. 데이터 source 우선순위

같은 개념이 여러 파일에 있어도 다음 우선순위를 사용한다.

## 재고

```text
CARRIER_INVENTORY_TIMELINE.csv
```

## 최적화 추천

```text
CARRIER_RECOMMENDATIONS_<CARRIER>.csv
```

## 재고 effect

```text
INVENTORY_IMPACT_SUMMARY.csv
```

## need

```text
SERVICE_NEED_RESULT.csv
```

## route/stop time

```text
KORAIL_TRAIN_PLAN.csv
STOP_WORK_PLAN.csv
```

## chatbot explanation

```text
RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv
```

PDF의 숫자 또는 별도 mock JSON을 source-of-truth로 만들지 않는다.

---

# 23. 결과 refresh 전략

UI 클릭마다 MILP를 실행하지 않는다.

기본 동작:

```text
MILP 실행 완료
→ 05_RESULTS/AXIS_INTEGRATED 갱신
→ backend result store reload
→ UI 새 데이터 표시
```

개발 단계에서는 backend restart 또는 internal reload function이면 충분하다.

사용자에게 `재최적화` 버튼을 노출하지 않는다.

---

# 24. MILP 실행이 필요할 때 참고 명령

패키지 root에서:

```bash
pip install numpy scipy pandas openpyxl
```

정본 integrated run:

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

Windows에서는:

```text
run_axis_integrated.bat
```

UI 개발 중에는 이미 들어 있는 `05_RESULTS/AXIS_INTEGRATED` 결과를 읽으면 되므로 매번 재실행할 필요 없다.

---

# 25. Empty / Error / Loading 상태

enterprise UI에서 반드시 구현.

## Loading

- card skeleton
- table skeleton rows
- chart area skeleton

## Empty recommendation

```text
이번 주 철도 재배치 권고가 없습니다.
현재 계획 기준으로 추천 가능한 철도 재배치안이 생성되지 않았습니다.
```

`정상`이라고 임의 해석하지 않는다. 추천이 없을 수 있는 원인은 여러 가지다.

## Missing result files

```text
최적화 결과 파일을 불러오지 못했습니다.
결과 디렉터리 설정을 확인해주세요.
```

## Solver/meta warning

`SUMMARY.json.all_stages_proven_optimal != true`라면 정상 결과처럼 보여주지 말고 warning/error state.

---

# 26. Responsive

핵심 demo는 desktop이지만 최소 대응한다.

## >= 1200px

PDF structure 그대로.

## 768~1199px

- Overview 2-column → 1-column
- matrix/table horizontal scroll
- lower chart + summary stack

## < 768px

완전한 모바일 최적화는 우선순위 낮음.

- nav horizontal scroll
- table horizontal scroll
- chatbot drawer width 100vw minus margin

---

# 27. 구현 품질 규칙

- TypeScript `strict: true`
- 숫자 formatting: `Intl.NumberFormat('ko-KR')`
- 날짜/시간 formatting helper 한 곳에서 관리
- Korean weekday helper 한 곳에서 관리
- CSV column name을 component에서 직접 사용하지 말고 adapter에서 domain model로 변환
- 모든 숫자는 data-derived
- UI component에서 business calculation을 중복 구현하지 말고 selector/backend layer에서 계산
- 동일 Inventory component를 baseline/postRail에 재사용
- mock number hardcode 금지
- console error 없음
- 다른 carrier 데이터 network response에 없음

---

# 28. Acceptance Criteria — 완료 판정

## 전체

- [ ] Overview / 재고 / 공컨 최적화 / 운송비교 nav가 존재한다.
- [ ] 운송비교는 placeholder이며 다른 팀원이 연결할 수 있다.
- [ ] chatbot button이 모든 페이지 우측 하단에 고정되어 있다.
- [ ] 숫자는 PDF mock이 아니라 optimizer file에서 읽는다.
- [ ] carrier 단위는 `개`가 기본이다.

## Overview

- [ ] 6개 hub와 rail network가 보인다.
- [ ] hub 클릭 시 해당 carrier의 20/40FT 부족량이 보인다.
- [ ] right top에 거점별 weekly inventory summary가 보인다.
- [ ] bottom에 current carrier recommendation preview가 보인다.

## 재고

- [ ] 20FT/40FT toggle이 있다.
- [ ] 6 hub × 월~일 matrix가 있다.
- [ ] matrix 값은 daily closing `baseline_inventory`다.
- [ ] unmet가 있는 날은 shortage가 별도 표시된다.
- [ ] hub를 선택하면 아래 line chart가 바뀐다.
- [ ] line chart는 월~일 7개 point만 사용한다.
- [ ] weekly demand/supply/change/min/shortage summary가 실제 data와 일치한다.

## 공컨 최적화

- [ ] `재배치 필요 현황`은 current carrier Service Need에서 생성된다.
- [ ] 추천 표는 current carrier recommendation file에서 생성된다.
- [ ] 수량은 quantity_boxes이다.
- [ ] exact departure/arrival time이 보인다.
- [ ] available_time을 detail에서 확인할 수 있다.
- [ ] recommendation row expand 시 train route/stops가 보인다.
- [ ] stop load/unload는 자사 recommendation만 aggregate한다.
- [ ] 타 선사 load/unload 정보가 보이지 않는다.
- [ ] 거점별 재배치 영향이 algorithm output 기반이다.
- [ ] 재배치 후 inventory matrix는 `post_rail_inventory`를 사용한다.
- [ ] residual `post_rail_unmet_demand`가 존재하면 그대로 부족 표시한다.

## 챗봇

- [ ] floating button + drawer UI가 있다.
- [ ] API 미연결 상태를 정상적으로 처리한다.
- [ ] API key는 frontend에 두지 않는다.
- [ ] read-only policy가 코드 구조에 반영되어 있다.

---

# 29. 절대 하면 안 되는 구현 실수

1. **PDF 숫자 hardcode**
2. `quantity_teu`를 컨테이너 개수처럼 표시
3. 40FT 9개를 `9TEU`로 표시
4. baseline inventory를 임의로 음수화
5. stockout을 negative inventory와 혼동
6. `STOP_WORK_PLAN.load_teu`를 자사 물량으로 노출
7. 다른 선사의 allocation을 frontend로 전달
8. optimization 후 부족이 항상 0이라고 가정
9. prototype timetable을 `KORAIL 실제 운행시간`이라고 표기
10. chatbot이 숫자를 추측하거나 재최적화를 수행
11. 시간별 demand chart를 추가하여 데이터 정밀도를 과장
12. 디자인 참고 이미지 때문에 대형 vehicle hero image를 추가
13. PDF 구조를 무시하고 generic AI dashboard로 재구성

---

# 30. Claude Code 작업 순서

아래 순서로 구현한다.

## Phase 1 — optimizer inspection / data adapter

1. zip 정상 extraction
2. `05_RESULTS/AXIS_INTEGRATED` 파일 schema 확인
3. carrier filter helper 작성
4. daily aggregation unit test 작성
5. CARRIER_A sanity check 통과

## Phase 2 — backend

1. FastAPI app
2. meta endpoint
3. overview endpoint
4. baseline inventory endpoint
5. optimization endpoint
6. postRail inventory endpoint
7. current carrier isolation test

## Phase 3 — app shell/design system

1. background/shell
2. top nav
3. card primitive
4. table primitive
5. typography
6. responsive grid
7. chatbot floating button shell

## Phase 4 — Overview

1. schematic hub map
2. hub click popover
3. hub inventory summary
4. comparison placeholder
5. recommendation preview

## Phase 5 — 재고

1. size toggle
2. weekly matrix
3. hub selection
4. line chart
5. weekly summary
6. shortage state

## Phase 6 — 공컨 최적화

1. service need table
2. recommendation table
3. row route expand
4. inventory impact table
5. postRail weekly matrix
6. postRail hub detail

## Phase 7 — chatbot integration shell

1. drawer
2. chat provider abstraction
3. backend proxy endpoint
4. API-not-configured state

## Phase 8 — polish

1. empty/loading/error
2. Korean number/time format
3. real data validation
4. privacy check
5. responsive
6. remove all mock numbers

---

# 31. 최종 제품이 전달해야 하는 사용자 스토리

화면을 발표할 때 사용자가 자연스럽게 다음 흐름을 읽을 수 있어야 한다.

```text
Overview
“이번 주 우리 공컨 상황에서 어느 거점이 부족한가?”

↓

재고
“20FT/40FT별로 월~일 재고가 어떻게 변하고, 어느 거점에 부족이 발생하는가?”

↓

공컨 최적화
“그 부족을 해결하기 위해 MOVE-AI가 내 공컨을 어디서 어디로 몇 개, 언제 보내라고 제안하는가?”

↓

공컨 최적화 하단
“그 재배치를 반영하면 우리 거점들의 재고/부족이 실제로 어떻게 달라지는가?”

↓

Copilot
“이 결과가 왜 이렇게 나왔는지 이미 계산된 데이터를 기반으로 설명해줘.”
```

이 사용자 스토리를 벗어나는 기능은 현재 구현하지 않는다.

---

# 32. Claude Code용 마지막 한 문장 지시

> **PDF의 정보구조를 그대로 존중하고, 참고 이미지의 차분한 B2B dashboard visual language만 차용하되, 모든 실제 수치와 운송시간은 AXIS v7.1 결과 파일에서 current carrier만 필터링하여 계산하라. 선사용 UI이므로 타 선사 정보·최적화 수정·재최적화 기능은 절대 구현하지 말고, 챗봇은 추후 API가 연결될 read-only 설명 interface로만 설계하라.**

