# MOVE-AI AXIS

공컨테이너 재배치 의사결정 플랫폼.

## 구조

```
MOVE_AI_AXIS/
├─ frontend/        React 19 + TypeScript + Vite (정적 빌드)
│  ├─ src/
│  └─ dist/         빌드 산출물 — Vercel 이 서빙하는 대상
├─ api/             Vercel 서버리스 함수 (ESM). API key 는 여기서만 읽는다
│  └─ health.js
├─ vercel.json      빌드·라우팅 설정
└─ .vercelignore    배포 제외 대상
```

## 실행

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

http://localhost:5175

`/api/*` 함수까지 같이 돌리려면 저장소 루트에서 `vercel dev` 를 쓴다.
`npm run dev` 만 띄우면 `/api/health` 는 502/404 가 나는 게 정상이다.

## 배포 (Vercel)

GitHub 연동으로 배포한다. `main` 에 push 하면 프로덕션, PR 마다 프리뷰 URL 이 생긴다.

`vercel.json` 이 프레임워크 자동감지를 덮어쓰므로 Vercel 대시보드에서
Framework Preset / Build Command / Output Directory 를 건드리지 않는다.

```json
{
  "installCommand": "cd frontend && npm ci",
  "buildCommand": "cd frontend && npm run build",
  "outputDirectory": "frontend/dist",
  "rewrites": [{ "source": "/((?!api/|data/|assets/).*)", "destination": "/index.html" }]
}
```

### 환경변수

Vercel 프로젝트 Settings → Environment Variables 에 넣는다. `.env` 는 커밋하지 않는다.
항목은 `.env.example` 참고.

| 이름 | 용도 |
|---|---|
| `GEMINI_API_KEY` | Copilot 함수용. 미설정 시 `/api/health` 가 `gemini: false` 반환 |
| `GEMINI_MODEL` | 기본 `gemini-2.0-flash` |

### 배포 확인

| 확인 대상 | 방법 |
|---|---|
| 정적 빌드 | 루트 페이지가 뜬다 |
| SPA rewrite | `/status` 로 **직접 진입**(새로고침)해도 404 가 아니다 |
| 서버리스 함수 | `/api/health` 가 `{"ok":true,...}` 를 반환한다 |

`/status` 화면이 위 셋을 한 번에 보여준다. 실제 기능을 붙이기 시작하면 지운다.

## 배포에서 겪었던 함정

이전 AXIS 배포에서 실제로 막혔던 것들이라 그대로 옮겨왔다.

- **`.vercelignore` 패턴 앞에 `/` 를 붙인다.** `.gitignore` 문법이라 `data/` 라고 쓰면
  모든 깊이의 `data` 폴더가 걸려 `frontend/public/data/` 까지 배포에서 사라진다.
  반드시 `/data/` 로 저장소 루트에만 적용한다.
- **Python backend 를 저장소에 두면 `.vercelignore` 로 반드시 제외한다.**
  안 그러면 Vercel 이 FastAPI 웹서비스로 감지해 멀티 서비스 프로젝트로 잡고 배포를 막는다.
- **`installCommand` 가 `npm ci` 이므로 `frontend/package-lock.json` 은 반드시 커밋한다.**
  lock 파일이 없으면 설치 단계에서 바로 실패한다.
- **rewrite 의 negative lookahead 에서 `api/` 를 빼먹지 않는다.**
  빼면 `/api/*` 요청까지 `index.html` 로 삼켜져 함수가 영영 안 불린다.

## 원칙

- API key 는 `frontend/` 에 두지 않는다. 서버리스 함수에서만 읽는다.
- 값이 없으면 `산정 준비중` 으로 표시하고 0 이나 임의값을 만들지 않는다.
