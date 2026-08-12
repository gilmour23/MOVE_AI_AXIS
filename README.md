# MOVE-AI

여러 선사의 공컨테이너 수요를 함께 모아 **신규 공컨 전용 화물열차를 추가 배차**하는
철도 공동 재배치 플랫폼입니다. 기존 화물열차의 잔여용량에 공컨을 끼워 넣는 서비스가 아닙니다.

하나의 MILP 최적화 결과를 **두 사용자 관점**에서 보여줍니다.

| 관점 | 경로 | 무엇을 보는가 |
|---|---|---|
| **Carrier Portal** | `/carrier` | 자사 공컨 재고·부족과 철도 재배치 제안 |
| **KORAIL Control Tower** | `/korail` | 전 선사 운송물량·열차 운행계획·거점 작업계획 |

컨테이너 소유권은 선사별로 독립이며 재고를 공유하지 않습니다. 열차 Capacity만 공동 이용합니다.

이 서비스는 **read-only Decision Support System**입니다.
최적화 결과 수정, 재배치 수량 변경, 재최적화, 수락/거절, 실시간 추적 기능은 없습니다.

---

## 개발 단계 구분

본선 안내(제출규정 1항)의 사전 준비 / 본선 당일 구분에 따라 현재 상태를 그대로 밝힙니다.

### 본선 이전 (2026-08-12까지)

사전 기획·자료조사·개발환경 구축과 함께, 아래 범위가 본선 전에 작성되었습니다.

| 영역 | 상태 |
|---|---|
| AXIS MOVE-AI MILP v7.1 최적화 엔진 | 별도 연구 산출물 (2026-08-10) |
| 화면 기획 (IA·와이어프레임) | 완료 |
| FastAPI 백엔드 · MILP 결과 어댑터 | 완료 |
| Carrier Overview / 재고 / 공컨 최적화 화면 | 완료 |
| 배포 파이프라인 (Docker · Render) | 구성만, 미배포 |

### 본선 당일 (2026-08-13) 구현

| 영역 | 본선 전 상태 | 현재 |
|---|---|---|
| 철도·트럭 운송 비교 | placeholder 화면만 존재 | 구현 완료 |
| KORAIL Control Tower | 미착수 | 4개 화면 구현 |
| 운송물량 데이터 경로 (`transport_allocations`) | 없음 | selector·export·화면 구현 |
| Carrier 운송 현황 | 없음 | 계획 시각 화면 구현 |
| 서비스 배포 (Vercel 정적 + 서버리스) | 미배포 | 배포 완료 |
| **MOVE-AI Copilot (Gemini)** | UI shell·함수 골격만, AI 연동 없음 | **코드는 연결, API 키 미주입 상태** |

> Copilot은 서버리스 함수(`api/chat.js`)와 grounding(`api/_grounding.js`)까지 구현되어 있으나
> `GEMINI_API_KEY`가 주입되지 않아 `/api/chat/status`가 `configured: false`를 반환합니다.
> 이 상태에서는 화면이 "챗봇 API가 아직 연결되지 않았습니다"를 표시하며,
> **가짜 AI 답변을 하드코딩하지 않습니다.**

본선 당일 커밋 이력에서 위 항목의 구현 과정을 확인할 수 있습니다.

기획 산출물과 화면 프로토타입은 [`docs/`](docs/) 에 있습니다.
프로토타입 HTML 안의 숫자는 화면 구조 설명용 mock 이며 정본이 아닙니다.

각 기능의 소유 파일·입력·출력·의존 모듈·완료 테스트는
[`docs/MODULES.md`](docs/MODULES.md) 에 모듈 단위로 정리해 두었습니다.

---

## 아키텍처 — 왜 정적인가

MILP 결과는 한 계획 주기 동안 **고정**입니다. 사용자가 화면을 볼 때마다
서버가 다시 계산할 이유가 없습니다.

그래서 조회 API 응답을 미리 계산해 정적 JSON으로 내보내고, 화면은 그 파일을
그대로 읽습니다. 상시 구동 서버가 없어 콜드 스타트나 서버 다운이 발생하지 않고,
CDN에서 즉시 로드됩니다.

```text
optimizer/05_RESULTS  ──▶  ResultStore  ──▶  selectors  ──▶  export_static.py
                                                                    │
                                              frontend/public/data/*.json
                                                                    │
                                        client.ts (논리 /api → 정적 /data)
                                                                    │
                                                                React UI
```

서버 코드가 필요한 곳은 **챗봇 하나뿐**입니다. API 키를 브라우저에 노출할 수 없어
서버리스 함수(`api/chat.js`)로 프록시합니다.

`backend/`는 삭제하지 않고 **정적 데이터 생성기 겸 로컬 개발용 API**로 유지합니다.
정적 JSON과 백엔드 응답은 같은 `selectors/` 코드에서 나오므로 값이 항상 일치합니다.

### 챗봇 경로가 두 개인 이유

| 경로 | 용도 |
|---|---|
| `api/chat.js` + `api/_grounding.js` | **배포 정본.** Vercel 서버리스에서 Gemini 호출 |
| `backend/moveai/chat/*` | 로컬 FastAPI 개발용 provider 추상화 |

배포 환경에서 실제로 동작하는 것은 전자입니다. 후자는 로컬에서 백엔드를 띄웠을 때만 쓰입니다.

---

## 빠른 시작

최초 1회:

```bash
setup.bat
```

MILP 결과를 정적 JSON으로 내보내기 (결과가 갱신됐을 때만 다시 실행):

```bash
python scripts/export_static.py
```

화면 실행 — 정적 JSON을 읽으므로 백엔드 없이도 동작합니다:

```bash
cd frontend && npm run dev
```

백엔드까지 함께 띄우려면 (챗봇 개발·API 확인용):

```bash
run_dev.bat
```

---

## 화면 구성

### Carrier Portal

| 경로 | 화면 |
|---|---|
| `/carrier` | Overview — 네트워크 지도, 거점별 재고, 운송비교 요약, 재배치 권고 preview |
| `/carrier/inventory` | 재고 — 20FT/40FT × 거점별 주간 재고 추이 |
| `/carrier/plan` | 공컨 최적화 — 재배치 필요 현황 / 제안 / 거점 영향 / 재배치 후 재고 |
| `/carrier/transport` | 운송비교 — 철도 vs 트럭 비용·시간·탄소 |
| `/carrier/tracking` | 운송 현황 — 계획된 출발·도착·사용 가능 시각 |

### KORAIL Control Tower

전체 → 화물 → 열차 → 거점 순서로 읽습니다.

| 경로 | 화면 |
|---|---|
| `/korail` | 종합계획 — 계획 요약, 주간 운행 스케줄, 거점별 열차 일정 |
| `/korail/cargo` | 운송물량 — 선사×OD×규격×열차 배정 물량 |
| `/korail/trains` | 열차운행 — 주간 운행 시간표, 편성·물량·경유 거점 |
| `/korail/operations` | 거점작업 — 거점별 상·하차 작업계획 |

`?train=CAND0292`, `?hub=BUSAN` 같은 query deep-link를 지원합니다.

---

## 구조

```text
MOVEAI_AXIS2/
├─ optimizer/AXIS_MOVEAI_MILP_v7_1_FINAL/   # MILP 패키지 (모든 숫자의 정본)
│  └─ 05_RESULTS/AXIS_INTEGRATED/           # 서비스가 읽는 결과 디렉터리
├─ backend/                                  # 결과 해석 + selector + 검증
│  ├─ moveai/
│  │  ├─ result_store.py                     # CSV 로더 (UTF-8/CP949 자동 판별) + 캐시
│  │  ├─ selectors/                          # overview·inventory·optimization·transport·korail
│  │  └─ chat/                               # 로컬 개발용 챗봇 provider
│  └─ tests/test_sanity.py                   # 어댑터 sanity check
├─ scripts/export_static.py                  # selector → 정적 JSON + 정합성 검증
├─ frontend/                                 # React + TypeScript + Vite (CSS Modules)
│  ├─ public/data/                           # 생성된 정적 JSON (커밋 대상)
│  └─ src/{api,app,components,config,hooks,lib,pages,styles,types}/
├─ api/                                      # Vercel 서버리스 (챗봇 전용)
│  ├─ chat.js · _grounding.js · chat/status.js
├─ data/TRUCK_COMPARISON_BY_RECOMMENDATION.csv
└─ docs/{planning,prototypes}/
```

---

## 선사 격리 (최우선 보안 요구사항)

Carrier Portal 정적 파일에는 **현재 선사의 집계 결과만** 들어갑니다.

- 내보내기 시점에 `carrier_id`로 먼저 필터링한 뒤 집계합니다.
- 타 선사의 demand / supply / inventory / recommendation / allocation 은 포함되지 않습니다.
- `export_static.py`가 carrier 파일 전체를 스캔해 타 선사 식별자가 없는지 자동 검증합니다.

**KORAIL Control Tower만** 전 선사 배정을 볼 수 있습니다. 운영자 관점이므로 정상입니다.
단, KORAIL 화면에서 선사명을 눌러 Carrier Portal로 이동하는 링크는 두지 않습니다.

---

## 단위·집계 규칙

| 개념 | 필드 | 표시 |
|---|---|---|
| 컨테이너 개수 | `quantity_boxes` | `9개` |
| TEU | `quantity_teu` | 집계 영역에서만 |

40FT 1개 = 2TEU입니다. **`40FT 9TEU` 같은 표기는 사용하지 않습니다.**

규격별 박스 수는 `CARRIER_ALLOCATION`에서 직접 집계합니다.
**TEU에서 역산하지 않습니다.**

```text
loadTEU   = loadBoxes20ft   + 2 × loadBoxes40ft
unloadTEU = unloadBoxes20ft + 2 × unloadBoxes40ft
```

재고는 0에서 clip되며 음수가 되지 않습니다. 충족하지 못한 수요는 `부족`으로 따로 표시합니다.

- **하루 예상재고** = 그날 마지막 timestamp의 재고
- **하루 부족량** = 그날 시간별 `*_unmet_demand` 합
- **주간 최저** = 화면에 보이는 7개 daily closing의 최솟값

### 시각 처리

모든 timestamp는 **KST wall-clock 계획시각**입니다. 문자열 component를 그대로 읽어
표시하므로 브라우저 timezone과 무관하게 같은 값이 보입니다.

`STOP_WORK_PLAN`에는 `loadStartTime < arrivalTime`인 stop이 존재합니다.
따라서 UI는 "도착 → 작업 → 출발" 같은 **인과 순서를 만들지 않고** 각 시각을 독립 계획값으로 표시합니다.

한 열차에 여러 OD가 섞여 있으므로, 운송 건별 시각은 열차 전체 출발/최종 도착이 아니라
**그 건의 origin/destination stop**에서 가져옵니다.

---

## 정합성 검증

`python scripts/export_static.py` 실행 시 자동으로 검증하며, 실패하면 내보내기를 중단합니다.

```text
[정합성]  Σ Recommendation TEU = Σ Allocation TEU = Σ Train Assigned TEU = Rail Served TEU
          recommendation train_id ⊆ 선정 열차
          열차별 allocation 합 == assigned TEU
[거점작업] 20FT + 2×40FT == STOP_WORK_PLAN TEU
[운송물량] OD stop 시각 join · 열차별 Box/TEU 합 == 열차 요약
[Transport] rail 값 == canonical recommendation
[격리]     carrier/ 파일에 타 선사 식별자 없음
```

```bash
cd backend && python -m pytest -q
```

---

## 현재 데이터

번들된 결과는 **합성 데이터**입니다. 헤더 배지와 화면에서 이 사실을 숨기지 않습니다.

| 항목 | 값 |
|---|---|
| 시나리오 | `AXIS_INTEGRATED` |
| 계획주기 | 2026-08-10 ~ 2026-08-16 |
| 선정 열차 | 3편 (CAND0156 · CAND0702 · CAND0292) |
| 총 편성 | 99량 |
| 총 공컨 | 121개 / 138 TEU |
| 운송물량 | 24건 |
| 정적 JSON | 47개 파일 |

운행시각은 **프로토타입 운행후보**이며 "KORAIL 실제 운행시각"이 아닙니다.
실제 데이터로 교체되면 `SUMMARY.json` 값에 따라 배지가 자동으로 사라집니다.

---

## 배포 (Vercel)

| 설정 | 값 |
|---|---|
| Install | `cd frontend && npm ci` |
| Build | `cd frontend && npm run build` |
| Output | `frontend/dist` |
| 서버리스 함수 | `api/chat.js`, `api/chat/status.js` |

- 정적 파일과 데이터는 CDN에서 서빙됩니다.
- SPA 딥링크는 `vercel.json`의 rewrite가 처리합니다.
- `backend/`, `optimizer/`, `scripts/`는 `.vercelignore`로 배포에서 제외됩니다.
  정적 JSON을 만들 때만 쓰입니다.
- `GEMINI_API_KEY`는 Vercel 환경변수로 주입합니다. **저장소에 커밋하지 않습니다.**

---

## MILP 결과 갱신

```text
MILP 실행 → 05_RESULTS/AXIS_INTEGRATED 갱신
         → python scripts/export_static.py
         → frontend/public/data/*.json 커밋 → 배포 자동 갱신
```

정적 JSON은 저장소에 커밋합니다. 데이터가 고정이라 빌드 환경에 Python이
없어도 되고, 심사자가 저장소에서 화면에 표시되는 값을 그대로 확인할 수 있습니다.

사용자에게 `재최적화` 버튼은 제공하지 않습니다.

---

## 의도적으로 만들지 않은 기능

현재 데이터로 뒷받침할 수 없는 것은 만들지 않습니다.

```text
실시간 열차 위치 · 운행 중/지연 상태 · 실제 운행실적
기관차/승무원 배정 · 선로 확보 · 입환 계획
CY 설비·인력 capacity 및 과부하 판정
수락/거절 workflow · 실제 예약 · 재최적화 버튼
```

`/carrier/tracking`은 **실시간 추적이 아니라 계획 시각 화면**입니다.

적재율에도 경고색을 쓰지 않습니다. 높은 적재율은 효율적인 용량 활용일 수 있어
`높은 적재율 = 위험`으로 자동 해석하지 않습니다.
