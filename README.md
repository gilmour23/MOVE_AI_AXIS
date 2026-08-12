# MOVE-AI 선사(Carrier) UI

선사 담당자용 **공컨테이너 의사결정지원 UI**입니다.
AXIS MOVE-AI MILP v7.1 결과 파일을 읽어 현재 선사의 재고·부족·철도 재배치 제안을 보여줍니다.

이 UI는 **read-only Decision Support System**입니다.
최적화 결과 수정, 재배치 수량 변경, 재최적화, 수락/거절, tracking, notification 기능은 없습니다.

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
| Overview / 재고 / 공컨 최적화 화면 | 완료 |
| 배포 파이프라인 (Docker · Render) | 구성 완료, 미배포 |

### 본선 당일 (2026-08-13) 구현

| 영역 | 본선 전 상태 |
|---|---|
| **Gemini 기반 MOVE-AI Copilot** | UI shell·provider 추상화만 존재, **AI 연동 없음** |
| 철도·트럭 운송 비교 | placeholder 화면만 존재 |
| KORAIL Control Tower 관점 | 미착수 |
| 서비스 배포 | 미배포 |

> 본선 당일 커밋 이력에서 위 항목의 구현 과정을 확인할 수 있습니다.

---

## 빠른 시작

최초 1회:

```bash
setup.bat
```

실행:

```bash
run_dev.bat
```

- 백엔드 <http://127.0.0.1:8000> (FastAPI, API 문서는 `/docs`)
- 프론트 <http://localhost:5173>

수동 실행:

```bash
cd backend && python -m uvicorn app:app --port 8000 --reload
```

```bash
cd frontend && npm run dev
```

---

## 구조

```text
moveai-carrier-ui/
├─ optimizer/AXIS_MOVEAI_MILP_v7_1_FINAL/   # MILP 패키지 (모든 숫자의 정본)
│  └─ 05_RESULTS/AXIS_INTEGRATED/           # UI가 읽는 결과 디렉터리
├─ backend/                                  # FastAPI — 선사 격리 + 집계
│  ├─ app.py                                 # 엔드포인트
│  ├─ moveai/
│  │  ├─ config.py                           # 경로·환경변수
│  │  ├─ domain.py                           # hub 정의, 요일 헬퍼, mode 컬럼 매핑
│  │  ├─ result_store.py                     # CSV 로더 (UTF-8/CP949 자동 판별) + 캐시
│  │  ├─ selectors/                          # overview / inventory / optimization 집계
│  │  └─ chat/                               # 챗봇 provider 추상화 + 프록시
│  └─ tests/test_sanity.py                   # CARRIER_A sanity check
└─ frontend/                                 # React + TypeScript + Vite (CSS Modules)
   └─ src/
      ├─ components/{layout,common,map,inventory,optimization,chatbot}/
      ├─ pages/                              # Overview / 재고 / 공컨 최적화 / 운송비교
      ├─ api/                                # 자기 백엔드(/api)만 호출
      ├─ config/hubMeta.ts                   # hub 좌표 (schematic)
      └─ styles/tokens.css                   # 디자인 토큰
```

---

## 선사 격리 (최우선 보안 요구사항)

브라우저에는 **현재 선사의 집계 결과만** 전달됩니다.

- 백엔드가 `carrier_id` 로 먼저 필터링한 뒤 집계합니다.
- 타 선사의 demand / supply / inventory / recommendation / allocation 은 응답에 포함되지 않습니다.
- 열차 경로 상세의 상·하차 물량은 자사 recommendation만 집계한 값입니다.
  `STOP_WORK_PLAN.load_teu` / `unload_teu`(열차 전체 물량)는 사용하지 않습니다.
- 공동운송 집계값(`participating_carrier_count`, `train_load_factor`)만 노출합니다.

`DEV_MODE=true`일 때만 헤더에 개발용 carrier selector가 보입니다.
**실제 선사 배포에서는 `DEV_MODE=false`로 설정하세요.** (이 값이 true면 `/api/meta`가
선사 ID 목록을 반환합니다. 데이터는 포함되지 않지만 실사용 화면에서는 노출하지 않습니다.)

---

## 단위 규칙

| 개념 | 필드 | 표시 |
| --- | --- | --- |
| 컨테이너 개수 | `quantity_boxes` | `9개` |
| TEU | `quantity_teu` | 집계 영역에서만 |

40FT 1개 = 2TEU입니다. **`40FT 9TEU` 같은 표기는 사용하지 않습니다.**

재고는 0에서 clip되며 음수가 되지 않습니다. 충족하지 못한 수요는 `부족`으로 따로 표시합니다.

```text
예상 재고 0개
예상 부족 24개
```

---

## 요일 단위 집계 규칙

- **하루 예상재고** = 그날 마지막 timestamp의 `baseline_inventory` / `post_rail_inventory`
- **하루 부족량** = 그날 시간별 `*_unmet_demand` 합
- **주간 수요/공급** = `demand` / `external_supply` 합 (철도 유입과 섞지 않음)
- **주간 재고 증감** = 주말 재고 − `initial_inventory`
- **주간 최저 예상재고** = 화면에 보이는 7개 daily closing의 최솟값
- **거점별 재배치 영향의 전/후 최저재고**도 같은 daily 기준을 사용합니다.
  `재배치 후 = 재배치 전 + 이동량` 같은 산술은 하지 않고 `post_rail_inventory` 결과를 그대로 씁니다.

---

## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/health` | 결과 파일 존재 확인 |
| GET | `/api/meta` | 시나리오 메타, 배지, hub 목록 |
| GET | `/api/carrier/{id}/overview` | 거점별 주말 재고·부족, 추천 프리뷰 |
| GET | `/api/carrier/{id}/inventory?size=&mode=` | 거점×요일 재고 매트릭스 |
| GET | `/api/carrier/{id}/inventory/{hub}/{size}/summary?mode=` | 주간 요약 |
| GET | `/api/carrier/{id}/optimization` | need / recommendation / impact |
| GET | `/api/carrier/{id}/optimization/recommendations/{recId}` | 열차 경로 상세 |
| GET | `/api/chat/status` | 챗봇 연결 여부 |
| POST | `/api/chat` | 챗봇 프록시 |
| POST | `/api/admin/reload` | 결과 재로딩 (사용자 화면 미노출) |

`mode`: `baseline`(재배치 전) / `postRail`(재배치 후)

---

## 챗봇

현재는 provider 추상화와 UI shell만 있습니다.

- `CHAT_API_URL` 미설정 → `/api/chat` 이 `503 CHAT_API_NOT_CONFIGURED` 반환
- 프론트는 "챗봇 API가 아직 연결되지 않았습니다" 안내를 표시합니다.
- **가짜 AI 답변을 하드코딩하지 않습니다.**
- 수량 변경·재계산 요청은 외부 API를 호출하지 않고 read-only 정책 문구로 응답합니다.
- API key는 백엔드 환경변수에만 둡니다. 자세한 설정은 `backend/.env.example` 참고.

---

## 테스트

```bash
cd backend && python -m pytest -q
```

번들된 `AXIS_INTEGRATED` 결과에 대한 sanity check 15개가 있습니다
(추천 5건 / 43박스 / 55TEU, baseline·postRail stockout, 열차 경로 자사 물량, 선사 격리).
여기 있는 값은 UI에 하드코딩하지 않고 어댑터 검증용으로만 씁니다.

---

## MILP 결과 갱신

```text
MILP 실행 → 05_RESULTS/AXIS_INTEGRATED 갱신 → 백엔드 재시작(또는 POST /api/admin/reload)
```

사용자에게 `재최적화` 버튼은 제공하지 않습니다.

---

## 현재 데이터 상태

번들된 결과는 합성 데이터입니다. 헤더에 다음 배지가 표시됩니다.

```text
Synthetic demo data      carrier_data_source = SYNTHETIC_CARRIER_LEVEL_DATA
Prototype timetable      candidate_timetable_source = PROTOTYPE_SYNTHETIC
```

실제 데이터로 교체되면 `SUMMARY.json` 값에 따라 자동으로 사라집니다.
운행시각은 프로토타입 운행후보이며 "KORAIL 실제 운행시각"이 아닙니다.

`all_stages_proven_optimal`이 true가 아니면 화면 상단에 경고가 표시됩니다.

---

## 미구현 (의도적)

- 운송비교 상세 (다른 팀원 담당 — `/comparison`은 placeholder)
- 데이터 입력/업로드, MILP controller UI, 재최적화
- 수락/거절/협상, tracking, notification
- 타 선사 데이터 조회
