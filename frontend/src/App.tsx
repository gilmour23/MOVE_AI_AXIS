import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

type Health = {
  ok: boolean;
  service: string;
  runtime: string;
  gemini: boolean;
};

/**
 * 배포 파이프라인이 실제로 살아있는지 확인하는 화면.
 *
 * 세 가지를 동시에 증명한다.
 *  1. 정적 빌드가 서빙된다 (이 페이지가 보인다)
 *  2. api/ 서버리스 함수가 붙었다 (health 카드가 ok 를 받는다)
 *  3. SPA rewrite 가 걸렸다 (/status 새로고침이 404 가 아니다)
 *
 * 실제 기능을 붙이기 시작하면 이 화면은 지운다.
 */
function StatusPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: Health) => {
        if (!cancelled) setHealth(data);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <div className="card">
        <h2>배포 파이프라인</h2>
        <div className="row">
          <span className="label">정적 빌드 (frontend/dist)</span>
          <span className="pill" data-state="ok">
            서빙됨
          </span>
        </div>
        <div className="row">
          <span className="label">SPA rewrite</span>
          <span className="pill" data-state="ok">
            /status 직접 진입 가능
          </span>
        </div>
        <div className="row">
          <span className="label">서버리스 함수 (/api/health)</span>
          {health ? (
            <span className="pill" data-state="ok">
              {health.runtime}
            </span>
          ) : error ? (
            <span className="pill" data-state="warn">
              미연결 · {error}
            </span>
          ) : (
            <span className="pill" data-state="idle">
              확인 중
            </span>
          )}
        </div>
        <div className="row">
          <span className="label">GEMINI_API_KEY</span>
          {health ? (
            <span className="pill" data-state={health.gemini ? "ok" : "warn"}>
              {health.gemini ? "설정됨" : "미설정"}
            </span>
          ) : (
            <span className="pill" data-state="idle">
              —
            </span>
          )}
        </div>
      </div>

      {error ? (
        <p className="lede">
          로컬 <code>npm run dev</code> 만 띄운 상태라면 <code>/api/*</code> 가 없는 게
          정상이다. 함수까지 같이 돌리려면 루트에서 <code>vercel dev</code> 를 쓴다.
        </p>
      ) : null}
    </>
  );
}

function HomePage() {
  return (
    <div className="card">
      <h2>다음 작업</h2>
      <div className="row">
        <span className="label">frontend/src</span>
        <span className="value">화면 구현</span>
      </div>
      <div className="row">
        <span className="label">api/</span>
        <span className="value">서버리스 함수 (API key 는 여기서만)</span>
      </div>
      <div className="row">
        <span className="label">.vercelignore</span>
        <span className="value">배포 제외 대상 관리</span>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="shell">
      <p className="eyebrow">MOVE-AI</p>
      <h1>AXIS</h1>
      <p className="lede">공컨테이너 재배치 의사결정 플랫폼.</p>

      <nav>
        <NavLink to="/" end>
          Home
        </NavLink>
        <NavLink to="/status">Status</NavLink>
      </nav>

      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/status" element={<StatusPage />} />
      </Routes>
    </div>
  );
}
