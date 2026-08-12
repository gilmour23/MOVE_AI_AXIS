# MOVE-AI 모듈 계약서

이 문서는 MOVE-AI를 **26개 기능 모듈**로 나누고, 각 모듈의 소유 파일 · 입력 · 출력 ·
의존 모듈 · 완료 테스트를 고정한다. 모듈을 따로 작업한 뒤 다시 붙일 수 있게 하는 것이 목적이다.

파일을 조각내기 위한 문서가 아니라 **책임 경계를 명시하기 위한 문서**다.
아래 계약을 지키는 한 Carrier UI · KORAIL UI · Copilot을 서로 독립적으로 수정할 수 있다.

---

## 계층

```text
1. Optimization / canonical results     optimizer/
2. Result adapter & selectors           backend/
3. Static materialization               scripts/ → frontend/public/data
4. Dual-role React UI                   frontend/src
5. Grounded Copilot                     api/
```

## 의존 방향

```text
M00 Environment
 ├─ M01 Research Asset
 │    └─ M02 ResultStore
 │         ├─ M03 Carrier Selectors ─┐
 │         └─ M04 KORAIL Selectors ──┴─ M05 Static Export
 │                                          └─ public/data
 └─ M06 Domain Contract
      └─ M07 Data Access
           ├─ M08 App Shell
           └─ M09 Shared UI
                ├─ M10~M14 Carrier Pages
                └─ M15~M19 KORAIL Pages
                     └─ M20 Chat UI → M21 Grounding → M22 Gemini API
                          └─ M23 Deployment → M24 Validation → M25 Cleanup
```

**역방향 참조 금지.** 특히 shared 층(`components/common`, `components/layout`, `lib`,
`hooks`, `config`, `types`)은 `pages/`를 참조하지 않는다. 예외는 `app/router.tsx`
하나이며, 이는 라우팅 정의라는 역할상 정상이다.

---

# 기반

## M00 — Environment / Bootstrap

| | |
|---|---|
| **소유** | `.gitignore` · `.vercelignore` · `frontend/{package.json,package-lock.json,tsconfig.json,vite.config.ts,index.html}` · `frontend/src/main.tsx` · `frontend/src/vite-env.d.ts` · `frontend/public/favicon.svg` · `backend/requirements.txt` · `backend/.env.example` · `backend/pytest.ini` · `setup.bat` · `run_dev.bat` · `vercel.json` · `.claude/launch.json` |
| **입력** | 없음 |
| **출력** | 빌드 가능한 개발환경 |
| **의존** | 없음 |
| **완료 테스트** | `npm ci` · `npm run typecheck` · `npm run build` 모두 성공 |

스택: React 18.3.1 · React Router 6.28 · Recharts 2.13 · lucide-react 0.468 ·
TypeScript 5.6.3 · Vite 5.4.

## M01 — Optimization Research Asset Boundary

| | |
|---|---|
| **소유** | `optimizer/AXIS_MOVEAI_MILP_v7_1_FINAL/**` |
| **입력** | 수요·초기재고·운행후보 |
| **출력** | `05_RESULTS/AXIS_INTEGRATED/*` |
| **의존** | 없음 |
| **완료 테스트** | `05_RESULTS/AXIS_INTEGRATED`에 필수 결과 파일 존재 |

**웹 서비스는 이 Python 코드를 import하지 않는다.** 결과 디렉터리만 읽는다.
따라서 서비스와 최적화 패키지는 한 덩어리가 아니다.

분해 작업에서 **MILP 로직과 결과를 변경하지 않는다.**

---

# 데이터 백본

## M02 — Canonical Result Store

| | |
|---|---|
| **소유** | `backend/moveai/config.py` · `domain.py` · `result_store.py` |
| **입력** | `optimizer/.../05_RESULTS/AXIS_INTEGRATED` · `data/TRUCK_COMPARISON_BY_RECOMMENDATION.csv` |
| **출력** | `store.*` accessor (아래) |
| **의존** | M01 |
| **완료 테스트** | `store.health().ok == true` · CP949 파일 로드 · `reload()` 후 재로딩 · Carrier accessor에 타 선사 없음 |

```text
summary · inventory_timeline · inventory_impact · service_need · train_plan
stop_work_plan · carrier_service_summary · train_operation_summary
carrier_allocation · segment_load · all_recommendations · truck_comparison
initial_inventory
recommendations(carrierId) · explanation_context(carrierId)
carrier_timeline(carrierId) · known_carriers()
```

규칙: 인코딩은 `utf-8-sig` → `cp949` fallback. 프로세스 수명 동안 캐시.
필수 파일 누락은 빈 상태가 아니라 `RESULT_FILES_MISSING`.
**selector·UI 로직을 이 모듈에 넣지 않는다.**

## M03 — Carrier Selectors

| | |
|---|---|
| **소유** | `backend/moveai/selectors/{overview,inventory,optimization,transport}.py` |
| **입력** | `ResultStore` + `carrier_id` |
| **출력** | `OverviewData` · `WeeklyInventory{Matrix,Summary}Data` · `OptimizationData` · `TransportComparison` |
| **의존** | M02 |
| **완료 테스트** | recommendation ID·rail charge·train ID·OD·boxes·TEU가 canonical과 동일 · truck 누락은 recommendation을 지우지 않고 `missingTruckComparison`으로 반환 |

집계 기준: 하루 예상재고 = 그날 마지막 timestamp · 하루 부족 = 그날 `*_unmet_demand` 합 ·
주간 최저 = 7개 daily closing 최솟값.

**철도 값은 canonical MILP가 정본이고 truck CSV는 비교값만 join한다.**

## M04 — KORAIL Selectors

| | |
|---|---|
| **소유** | `backend/moveai/selectors/korail.py` |
| **입력** | `ResultStore` (전 선사) |
| **출력** | UI 필수 4종 + legacy 4종 (아래) |
| **의존** | M02 |
| **완료 테스트** | allocation origin.sequence < destination.sequence · 열차별 allocation 합 = `assignedTeu` · 상하차 0인 stop 유지 |

```text
UI 필수      trains · train_detail · station_operations · transport_allocations
legacy 4종   overview · service_needs · hub_inventory · operational_insights
```

legacy 4종은 KORAIL 4페이지가 쓰지 않지만 **M21 grounding이 실제로 읽는다.**
`overview`는 추가로 `pages/LandingPage.tsx`가 진입 화면 요약에 쓴다. 삭제 금지 (M21 참조).

`transport_allocations`: `CARRIER_ALLOCATION` 1행 = 운송 1건. 시각은 반드시
`STOP_WORK_PLAN`을 `(trainId, hubCode)`로 join해서 만든다.
**열차 전체 출발/최종 도착을 대입하지 않는다** — 한 열차에 여러 OD가 섞여 있다.

규격별 박스는 `CARRIER_ALLOCATION`에서 직접 집계한다. **TEU에서 역산하지 않는다.**

## M05 — Static Export & Consistency Verification

| | |
|---|---|
| **소유** | `scripts/export_static.py` |
| **입력** | M03 · M04 selector 출력 |
| **출력** | `frontend/public/data/**/*.json` (47개) |
| **의존** | M03 · M04 |
| **완료 테스트** | 8종 검증 전부 통과 후에만 종료 (실패 시 `SystemExit`) |

```text
1 TEU 4중 정합성        5 rail 값 = canonical recommendation
2 rec train ⊆ 선정열차   6 stop 규격별 box → TEU
3 열차별 allocation 합   7 allocation OD stop 시각
4 transport join         8 carrier 파일에 타 선사 없음
```

`export_static.py`와 `client.ts`는 **한 세트**다. 한쪽만 바꾸면 404가 난다.

## 모듈 밖 — 로컬 개발 전용 백엔드 표면

아래 파일은 어느 모듈에도 속하지 않는다. **배포 경로가 아니기 때문이다.**
`.vercelignore`가 `backend/`를 통째로 제외하므로 배포된 사이트는 이 코드를 실행하지 않는다.

| 파일 | 역할 |
|---|---|
| `backend/app.py` | M02 store + M03 selector를 로컬 FastAPI로 노출 (`run_dev.bat`) |
| `backend/moveai/chat/{provider,router}.py` | 로컬 개발용 챗봇 provider 추상화. 배포 정본은 M22 `api/chat.js` |
| `backend/moveai/{,chat/,selectors/}__init__.py` | 빈 패키지 마커 |

`backend/app.py`는 selector 계산을 다시 하지 않고 M03 함수를 그대로 호출한다.
따라서 로컬 API 응답과 정적 JSON은 **같은 코드에서 나온다.**

---

# 프론트엔드 기반

## M06 — Frontend Domain Contract

| | |
|---|---|
| **소유** | `frontend/src/types/domain.ts` |
| **입력** | selector JSON 스키마 |
| **출력** | TypeScript 인터페이스 |
| **의존** | M03 · M04 |
| **완료 테스트** | JSON 키와 TS 키가 정확히 일치 (Seam 1) |

**도메인 타입은 이 파일에만 둔다.** 컴포넌트 props·유틸리티 타입
(`Column<T>`, `SegmentOption<T>`, `BadgeTone`, `AsyncState<T>`, `WallClock`,
`HubSchematic`, `RoleDefinition`, `ChatProvider`)은 각 소유 파일에 둔다 —
백엔드 스키마가 아니기 때문이다.

## M07 — Frontend Data Access Layer

| | |
|---|---|
| **소유** | `frontend/src/api/{client,carrier,chat}.ts` |
| **입력** | 논리 경로 `/api/...` |
| **출력** | 정적 `/data/...json` (챗봇만 실제 endpoint) |
| **의존** | M06 |
| **완료 테스트** | 모든 조회가 올바른 `/data` 경로로 전환 · `/api/chat`은 전환되지 않음 |

```text
/api/meta                  → /data/meta.json
/api/korail/trains         → /data/korail/trains.json
/api/korail/trains/{id}    → /data/korail/train_details/{id}.json
/api/korail/cargo          → /data/korail/transport_allocations.json
/api/korail/operations     → /data/korail/station_operations.json
/api/carrier/{id}/...      → /data/carrier/{id}/...
/api/chat                  → 전환 없음 (서버리스)
```

에러: network fail → `NETWORK_ERROR` · 404 또는 non-JSON → `RESULT_FILES_MISSING`.

**UI 코드에서 JSON 파일 경로를 직접 쓰지 않는다.**

## M08 — App Shell / Router / Role / Meta

| | |
|---|---|
| **소유** | `app/App.tsx` · `app/MetaContext.tsx` · `app/roles.ts` · `app/router.tsx` · `pages/LandingPage.{tsx,module.css}` · `components/layout/{AppShell,RoleSwitch,TopNav,PageContainer}.{tsx,module.css}` |
| **입력** | `meta.json` · `korail/overview.json`(진입 화면 요약) · 현재 pathname |
| **출력** | 역할 선택 진입 화면 · 역할별 navigation · 전역 meta |
| **의존** | M07 |
| **완료 테스트** | `/`→역할 선택 · `/carrier/*`→Carrier nav · `/korail/*`→KORAIL nav · RoleSwitch 이동 · 모든 deep link 직접 접속 |

**`roles.ts`만 `.ts`이고 나머지 셋은 `.tsx`다.** JSX를 담지 않는 순수 정의 파일이기 때문이다.

`router.tsx`와 `roles.ts`의 path는 항상 일치해야 한다 (Seam 4).
`TopNav`는 `wide` variant로 KORAIL만 여백을 키운다 — Carrier에 영향 주지 않는다.

`LandingPage`는 역할 선택 진입 화면이라 Carrier·KORAIL 어느 쪽에도 속하지 않는다.
`AppShell` 안에서 그려지지만 `/`에서는 `roleFromPath`가 `null`이므로
`TopNav`·`RoleSwitch`가 렌더되지 않는다 (`AppShell.tsx:35-36,62,76`).

## M09 — Shared UI Primitives & Design System

| | |
|---|---|
| **소유** | `styles/{tokens,globals}.css` · `components/common/*` · `hooks/useAsync.ts` · `lib/format.ts` · `config/hubMeta.ts` |
| **입력** | 없음 (순수 표현·유틸) |
| **출력** | `Card` · `DataTable` · `SegmentedControl` · `States` · `StatusBadge` · 포맷터 · hub 이름 |
| **의존** | 없음 |
| **완료 테스트** | 페이지가 loading/error/empty를 자체 구현하지 않음 · 시각 포맷이 timezone 무관 |

`lib/format.ts`는 모든 timestamp를 **KST wall-clock**으로 다룬다.
문자열 component를 직접 읽으므로 브라우저 timezone이 값을 바꾸지 않는다.

---

# Carrier Portal

공통 계약: 각 페이지는 API 결과를 **표시**하고 도메인 계산을 다시 하지 않는다.
KORAIL 디렉터리의 CSS·helper를 참조하지 않는다.

## M10 — Carrier Overview

| | |
|---|---|
| **소유** | `pages/OverviewPage.{tsx,module.css}` · `components/map/RailHubMap.{tsx,module.css}` |
| **입력** | `fetchOverview` · `fetchTransportComparison` · meta |
| **출력** | 최적성 경고 · 네트워크 지도 · 거점 재고 · 운송비교 요약 · 권고 preview |
| **의존** | M07 · M09 |
| **완료 테스트** | 숫자를 재계산하지 않고 API 결과 그대로 표시 · 지도↔재고 선택 연동 · preview → `/carrier/plan#REC` |

## M11 — Carrier Inventory

| | |
|---|---|
| **소유** | `pages/InventoryPage.tsx` · `components/inventory/*` |
| **입력** | carrierId · size · mode=baseline · hub |
| **출력** | 거점×요일 재고 매트릭스 · 추이 · 주간 요약 |
| **의존** | M07 · M09 |
| **완료 테스트** | baseline만 표시 · 20FT/40FT 전환 · hub 선택 · matrix와 summary 기준 동일 |

`InventorySection`은 `mode` prop으로 M12에서도 재사용된다.

## M12 — Carrier Optimization

| | |
|---|---|
| **소유** | `pages/OptimizationPage.{tsx,module.css}` · `components/optimization/*` |
| **입력** | `fetchOptimization` · postRail inventory |
| **출력** | A 재배치 필요 / B 제안 / C 거점 영향 / D 재배치 후 재고 |
| **의존** | M07 · M09 · M11(`InventorySection`) |
| **완료 테스트** | KPI 4종 · recommendation 확장 · deep-link `#REC0004` 진입 시 해당 항목 확장·스크롤 |

## M13 — Carrier Rail vs Truck

| | |
|---|---|
| **소유** | `pages/TransportPage.{tsx,module.css}` · `backend/moveai/selectors/transport.py` · `data/TRUCK_COMPARISON_BY_RECOMMENDATION.csv` · `data/README.md` |
| **입력** | `TransportComparison` |
| **출력** | 비용·시간·탄소 우선순위 비교 · 그래프 · 상세 |
| **의존** | M03 · M07 · M09 |
| **완료 테스트** | rail = canonical MILP · truck = comparison 입력 · `trainId` → `/korail/trains?train=` |

`chosenId`는 브라우저 UI 상태일 뿐 optimizer 결과를 바꾸지 않는다.

## M14 — Carrier Tracking

| | |
|---|---|
| **소유** | `pages/TrackingPage.{tsx,module.css}` |
| **입력** | `fetchOptimization(carrierId).recommendations` |
| **출력** | 계획 출발·도착·사용 가능 시각 표 |
| **의존** | M07 · M09 |
| **완료 테스트** | **자체 CSS module만 import** (KORAIL CSS 참조 금지) · 실시간 상태를 만들지 않음 |

**실시간 추적이 아니다.** 상태는 `계획 확정` 하나뿐이고 위치·지연·운행실적을 만들지 않는다.

---

# KORAIL Control Tower

최종 IA는 **4페이지**다: 종합계획 → 운송물량 → 열차운행 → 거점작업.
과거 6페이지 구조를 되살리지 않는다. legacy route는 redirect로만 남긴다.

## M15 — KORAIL Overview (종합계획)

| | |
|---|---|
| **소유** | `pages/korail/KorailOverviewPage.tsx` · `WeeklyTimeline.tsx` · `Korail.module.css` |
| **입력** | `fetchKorailTrains` · `fetchKorailOperations` · `meta.horizon{Start,End}` |
| **출력** | 계획 요약 1줄 · 주간 운행 스케줄 · 거점별 열차 일정 |
| **의존** | M07 · M09 · M17(WeeklyTimeline 공유) |
| **완료 테스트** | `korail/overview.json`을 읽지 않음 · train→`?train=` · hub→`?hub=` |

**첫 계획시각**: 상하차가 있으면 `loadStartTime`, 상하차 0인 정차는 arrival/departure를
써서 작업처럼 오해시키지 않는다.

## M16 — KORAIL Cargo (운송물량)

| | |
|---|---|
| **소유** | `pages/korail/KorailCargoPage.tsx` |
| **입력** | `fetchKorailCargo()` → `transport_allocations.json` |
| **출력** | 선사×OD×규격×열차 배정 물량 표 |
| **의존** | M04 · M07 · M09 |
| **완료 테스트** | 6종 필터(날짜·선사·출발·도착·규격·열차) 조합 후 row 수 정확 · 날짜는 wall-clock 기준 |

## M17 — KORAIL Trains (열차운행)

| | |
|---|---|
| **소유** | `pages/korail/KorailTrainsPage.tsx` · `WeeklyTimeline.tsx` · `trainInfo.ts` |
| **입력** | `fetchKorailTrains()` · meta horizon |
| **출력** | 주간 운행 시간표 · 편성·물량·경유 거점 표 |
| **의존** | M07 · M09 |
| **완료 테스트** | 자정 넘는 열차의 날짜·시간 모두 표시 · `?train=` deep link |

`workStops`는 **정차 계획**이며 상하차 발생을 뜻하지 않는다.
`trainInfo.ts`가 origin/destination을 제외한 중간 경유만 뽑는다.
UI 표기는 `경유거점`·`정차거점`이며 `작업거점`이라 부르지 않는다.

## M18 — KORAIL Train Detail

| | |
|---|---|
| **소유** | `pages/korail/TrainDetailDrawer.tsx` |
| **입력** | `fetchKorailTrainDetail(trainId)` |
| **출력** | 운행정보 → 정차·작업계획 → 선사별 운송물량 |
| **의존** | M04 · M07 · M09 |
| **완료 테스트** | 상하차 0인 stop은 `작업 개시`·`사용 가능`을 `-`로 · 하차 있을 때만 `사용 가능` 표시 · Carrier Portal 링크 없음 |

데이터에 `loadStartTime < arrivalTime`인 stop이 존재하므로 UI가
**`도착 → 작업 → 출발` 같은 인과 순서를 만들지 않는다.** 각 시각은 독립 계획값이다.

## M19 — KORAIL Operations (거점작업)

| | |
|---|---|
| **소유** | `pages/korail/KorailOperationsPage.tsx` |
| **입력** | `fetchKorailOperations()` → `station_operations.json` |
| **출력** | 거점 selector → 작업 일정 표 → 선택 작업 상세 |
| **의존** | M04 · M07 · M09 |
| **완료 테스트** | `?hub=` query 진입 · 상하차 0인 정차는 `상하차 없음`으로 구분 · capacity/혼잡 판정 없음 |

---

# AI

## M20 — Chat UI

| | |
|---|---|
| **소유** | `components/chatbot/{ChatDrawer,ChatFloatingButton}.tsx` · `Chat.module.css` · `api/chat.ts` |
| **입력** | message · carrierId · role · conversationId |
| **출력** | `/api/chat` POST → reply · sources |
| **의존** | M07 · M08(role) |
| **완료 테스트** | Carrier 화면 role=carrier · KORAIL 화면 role=korail · API 미설정 시 crash 없음 · 번들에 API key 없음 |

## M21 — Grounding

| | |
|---|---|
| **소유** | `api/_grounding.js` |
| **입력** | 배포된 `/data/**` · 질문 텍스트 · role · carrierId |
| **출력** | 질문에 필요한 JSON만 담은 context + sources |
| **의존** | M05 |
| **완료 테스트** | Carrier role이 `carrier/${carrierId}` 밖을 읽지 않음 · `REC\d{4}`·`CAND\d{4}` 인식 |

**KORAIL grounding은 legacy JSON 4종에 여전히 의존한다.**

```text
korail/overview.json       항상            _grounding.js:66
korail/inventory.json      재고·부족·거점   _grounding.js:68
korail/service_needs.json  수요·배정        _grounding.js:71
korail/insights.json       분석·권고·영향   _grounding.js:74
```

이 4개를 "KORAIL 4페이지가 안 쓴다"는 이유로 삭제하면 **챗봇 grounding이 약해진다.**
삭제하려면 grounding을 4페이지 데이터 구조로 먼저 재설계해야 한다.

`korail/overview.json`은 여기에 더해 **`pages/LandingPage.tsx`(M08)도 읽는다.**
UI 미사용 파일이 아니다.

## M22 — Gemini Serverless API

| | |
|---|---|
| **소유** | `api/chat.js` · `api/chat/status.js` |
| **입력** | POST body · `GEMINI_API_KEY` (환경변수) |
| **출력** | reply · sources · `readOnly: true` |
| **의존** | M21 |
| **완료 테스트** | 변경 요청 키워드는 모델 호출 없이 거절 · 키 미설정 시 503 · 키가 저장소·번들에 없음 |

read-only 거절 키워드: 바꿔·변경·수정·재계산·재최적화·취소·거절·수락·예약·배차·늘려·줄여.

system instruction이 보장할 것: context의 숫자만 사용 · 없는 숫자 추정 금지 ·
carrier 격리 · boxes/TEU 구분 · prototype timetable을 실제 운행시각이라 하지 않음 · read-only.

---

# 배포·검증

## M23 — Deployment

| | |
|---|---|
| **소유** | `vercel.json` · `.vercelignore` |
| **입력** | `frontend/` · `api/` · `frontend/public/data` |
| **출력** | 정적 CDN + 서버리스 함수 |
| **의존** | M05 · M22 |
| **완료 테스트** | SPA deep link 새로고침 정상 · `/data` 서빙 · `backend/optimizer/scripts` 배포 제외 |

## M24 — Integration Tests / Final Validation

| | |
|---|---|
| **소유** | `backend/tests/test_sanity.py` + 실행 절차 |
| **입력** | 전체 파이프라인 |
| **출력** | PASS/FAIL 판정 |
| **의존** | 전부 |
| **완료 테스트** | 아래 3개 명령 + route·cross-link·invariant 확인 |

```bash
cd backend  && python -m pytest -q
cd ..       && python scripts/export_static.py
cd frontend && npm run typecheck && npm run build
```

## M25 — Legacy & Cleanup

| | |
|---|---|
| **소유** | `README.md` · `docs/MODULES.md` · `docs/README.md` · `docs/planning/**` · `docs/prototypes/**` |
| **입력** | 실제 구현 상태 · git 이력 |
| **출력** | 구현과 일치하는 문서 |
| **의존** | 전부 |
| **완료 테스트** | README가 현재 화면·데이터·배포와 일치 · 개발 시점 서술이 git 이력으로 입증 가능 · 참조 검색 없이 파일을 지우지 않음 |

`docs/planning`·`docs/prototypes`는 실행 코드가 아니다. 그 안의 숫자는 mock이며 정본이 아니다.

**개발 시점을 쓸 때는 `git log`로 확인한 사실만 쓴다.** 특정 시점 이후 구현이라고
적으려면 그 시점 이후의 커밋이 실제로 존재해야 한다.

---

# Seam — 다시 붙일 때 가장 자주 깨지는 지점

| # | Seam | 확인 방법 |
|---|---|---|
| 1 | Python JSON key ↔ TS key | 생성된 JSON 키와 `domain.ts` 필드 비교 |
| 2 | `RESULT_DIR` ↔ optimizer 결과 | `store.health().ok` |
| 3 | export 경로 ↔ `client.ts` 매핑 | 두 파일을 한 세트로 수정 |
| 4 | `router.tsx` ↔ `roles.ts` | path 문자열 일치 |
| 5 | `meta.horizon*` ↔ `WeeklyTimeline` | 타임라인 축이 그려지는지 |
| 6 | `/korail/trains?train=` | Transport · Tracking · RouteDetail · Cargo · KorailOverview 5곳 공유 |
| 7 | `/korail/operations?hub=` | KorailOverview · TrainDetailDrawer 2곳 공유 |
| 8 | `/carrier/plan#REC` | OverviewPage → OptimizationPage |
| 9 | grounding legacy 의존 | `_grounding.js`가 읽는 4개 JSON 유지 |
| 10 | Tracking CSS | `TrackingPage.tsx`가 자체 CSS만 import |

---

# 불변조건

모듈을 분리했다 다시 붙여도 아래는 깨지면 안 된다.

```text
boxes 와 TEU 는 다른 단위다.  20FT 1개 = 1TEU · 40FT 1개 = 2TEU
  올바름  40FT 9개 / 18 TEU        잘못됨  40FT 9 TEU

Σ Recommendation TEU = Σ Allocation TEU = Σ Train Assigned TEU = Rail Served TEU
Σ allocation.teu by trainId = train.assignedTeu

loadTEU   = loadBoxes20ft   + 2 × loadBoxes40ft
unloadTEU = unloadBoxes20ft + 2 × unloadBoxes40ft
  → CARRIER_ALLOCATION 에서 직접 집계. TEU 역산 금지.

Carrier Portal 정적 파일에는 현재 선사 데이터만 존재한다.
KORAIL 만 전 선사 배정을 본다.

운송 건의 시각은 그 건의 origin/destination stop 에서 온다.
  열차 전체 출발·최종 도착을 대입하지 않는다.

tracking 은 실시간이 아니다. 없는 상태를 만들지 않는다.
```

# 만들지 않는 것

```text
UI 에서 임의 수치 재계산 · TEU 에서 박스 역산
Carrier 화면에서 전 선사 allocation 사용
prototype timetable 을 KORAIL 실제 운행시각으로 표현
실시간 위치·지연·운행실적 · CY capacity·혼잡 판정
재최적화 버튼 · 수락/거절 workflow
```
