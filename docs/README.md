# 기획·프로토타입 자료

본선 이전(2026-08-12까지)에 작성된 **기획 산출물과 화면 프로토타입**입니다.
실행 코드가 아니며, 실제 서비스는 `frontend/` · `backend/` · `api/` 에 있습니다.

> **중요 — 이 폴더의 숫자는 정본이 아닙니다.**
> 프로토타입 HTML 안의 열차 ID·선사명·수량은 화면 구조를 설명하기 위한 mock 이며
> 실제 최적화 결과와 다릅니다. 서비스에 표시되는 모든 수치는
> `optimizer/AXIS_MOVEAI_MILP_v7_1_FINAL/05_RESULTS/AXIS_INTEGRATED/` 에서 계산됩니다.

---

## `planning/` — 기획 산출물

| 파일 | 내용 |
|---|---|
| `carrier_ui_plan.pdf` | 선사 화면 정보구조(IA) 기획. 4페이지 |
| `korail_presentation_v3.pdf` | KORAIL Control Tower 기능·정보구조 기획 |
| `MOVE_AI_CARRIER_UI_CLAUDE_CODE_HANDOFF_FINAL.md` | 선사 UI 구현 핸드오프 문서. 단위 규칙, 요일별 집계 규칙, 선사 격리 원칙 정의 |

---

## `prototypes/` — 화면 프로토타입 (정적 HTML)

구현 전에 레이아웃과 인터랙션을 확정하기 위해 만든 단독 HTML 입니다.
각각 아래 React 화면으로 포팅되었습니다.

| 프로토타입 | → 실제 구현 |
|---|---|
| `carrier/Transport_index.html` | `frontend/src/pages/TransportPage.tsx` |
| `korail/index.html` | `frontend/src/pages/korail/*` (6개 화면) |

### 포팅하며 달라진 점

**데이터 출처가 바뀌었습니다.** 프로토타입은 JS 배열에 숫자를 직접 적어두었지만,
실제 구현은 MILP 결과에서 생성한 정적 JSON 만 읽습니다.

- `carrier/Transport_index.html` — 철도 측 값(운임·수량·OD·열차·시각)은 canonical MILP 로 교체.
  트럭 측 값만 `data/TRUCK_COMPARISON_BY_RECOMMENDATION.csv` 로 분리
- `korail/index.html` — mock 열차(`CAND0054`, `CAND0164`, `CAND0344`)와
  예시 선사명(`HMM`, `MSC`, `CMA CGM`)을 **전부 제거**하고 실제 선정 열차
  (`CAND0156`, `CAND0292`, `CAND0702`)와 `CARRIER_A~F` 로 재생성

문자열만 치환한 것이 아니라 노선·시각·선사 배정·적재량을 데이터 모델 단위로 다시 만들었습니다.

---

## 이미지 자료 출처

| 파일 | 출처 |
|---|---|
| `prototypes/korail/korail_logo.png` | 한국철도공사(KORAIL) 로고. 주최 기업 식별 목적의 프로토타입 표시용 |
| `prototypes/korail/freight_train.jpg` | 화물열차 이미지. 프로토타입 시각 자료 |

두 이미지는 프로토타입 HTML 이 참조하는 자산이며 실제 서비스 화면에서는 사용하지 않습니다.
