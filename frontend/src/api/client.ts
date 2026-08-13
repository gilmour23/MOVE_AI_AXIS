/** 데이터 접근 계층.
 *
 *  MILP 결과는 계획 주기 동안 고정이므로, 조회 API 응답을 미리 계산해
 *  정적 JSON(`public/data/`)으로 내보낸 뒤 그대로 읽는다.
 *  (생성: `python scripts/export_static.py`)
 *
 *  덕분에 상시 구동 서버 없이 CDN에서 즉시 로드된다.
 *  챗봇만 API 키를 숨겨야 하므로 실제 엔드포인트(/api/chat)를 호출한다.
 *
 *  타 선사 격리는 내보내기 시점에 이미 끝나 있다 — 정적 파일에는
 *  현재 선사의 집계 결과만 들어 있다 (핸드오프 §10, export_static.py 검증).
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

interface ErrorDetail {
  code?: string;
  message?: string;
}

/** 논리적 API 경로를 정적 JSON 파일 경로로 변환한다.
 *  변환 대상이 아니면 null 을 돌려주고, 호출은 실제 엔드포인트로 나간다. */
function toStaticPath(path: string): string | null {
  // 챗봇은 API 키를 숨겨야 하므로 서버리스 함수로 그대로 보낸다.
  if (path.startsWith('/api/chat')) return null;
  if (!path.startsWith('/api/')) return null;

  const [rawPath, rawQuery] = path.split('?');
  const params = new URLSearchParams(rawQuery ?? '');
  const segments = rawPath.replace(/^\/api\//, '').split('/');

  // 주차 무관 전역 메타 (week 목록·hub·현재 선사)
  if (segments[0] === 'meta') return '/data/meta.json';

  // 주차별 메타 — /api/weeks/{weekId}/meta
  if (segments[0] === 'weeks' && segments[1] && segments[2] === 'meta') {
    return `/data/shared/weeks/${segments[1]}/meta.json`;
  }

  // week 은 모든 결과 조회의 필수 스코프다.
  // 같은 CAND0158 이 두 주차에 모두 있으므로, week 없는 경로를 허용하면
  // 조용히 다른 주차의 열차를 보여주게 된다. 그래서 없으면 매핑하지 않는다.
  const week = params.get('week');

  // KORAIL Control Tower
  if (segments[0] === 'korail') {
    if (!week) return null;
    const base = `/data/korail/weeks/${week}`;
    const view = segments[1];
    if (view === 'trains') {
      // /korail/trains 또는 /korail/trains/{trainId}
      return segments[2]
        ? `${base}/train_details/${segments[2]}.json`
        : `${base}/trains.json`;
    }
    const fileByView: Record<string, string> = {
      cargo: 'transport_allocations.json',
      operations: 'station_operations.json',
      overview: 'overview.json',
      needs: 'service_needs.json',
      inventory: 'inventory.json',
      insights: 'insights.json',
    };
    const file = view ? fileByView[view] : undefined;
    return file ? `${base}/${file}` : null;
  }

  if (segments[0] !== 'carrier' || !segments[1] || !week) return null;

  const base = `/data/carrier/${segments[1]}/weeks/${week}`;
  const rest = segments.slice(2);
  const mode = params.get('mode') ?? 'baseline';
  const size = params.get('size') ?? '20FT';

  if (rest[0] === 'overview') return `${base}/overview.json`;
  if (rest[0] === 'transport') return `${base}/transport_comparison.json`;

  if (rest[0] === 'inventory') {
    // /inventory?size=&mode=
    if (rest.length === 1) return `${base}/inventory/${size}_${mode}.json`;
    // /inventory/{hub}/{size}/summary?mode=
    if (rest.length === 4 && rest[3] === 'summary') {
      return `${base}/inventory/${rest[1]}_${rest[2]}_${mode}_summary.json`;
    }
    // /inventory/{hub}/{size}/comparison — 재배치 전/후를 한 번에 받는다.
    if (rest.length === 4 && rest[3] === 'comparison') {
      return `${base}/inventory/${rest[1]}_${rest[2]}_comparison.json`;
    }
  }

  if (rest[0] === 'optimization') {
    if (rest.length === 1) return `${base}/optimization.json`;
    // /optimization/recommendations/{id}
    if (rest.length === 3 && rest[1] === 'recommendations') {
      return `${base}/optimization/recommendations/${rest[2]}.json`;
    }
  }

  return null;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const staticPath = toStaticPath(path);
  if (staticPath) {
    return request<T>(staticPath, { method: 'GET', signal }, true);
  }
  return request<T>(path, { method: 'GET', signal });
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
}

async function request<T>(
  path: string,
  init: RequestInit,
  isStatic = false,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error;
    throw new ApiError(
      '데이터를 불러오지 못했습니다. 네트워크 연결을 확인해주세요.',
      0,
      'NETWORK_ERROR',
    );
  }

  if (!response.ok) {
    // 정적 데이터 파일이 없다는 것은 내보내기가 누락됐다는 뜻이다.
    if (isStatic && response.status === 404) {
      throw new ApiError(
        '최적화 결과 파일을 불러오지 못했습니다.',
        404,
        'RESULT_FILES_MISSING',
      );
    }

    let code: string | null = null;
    let message = `요청에 실패했습니다 (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: ErrorDetail | string };
      if (typeof payload.detail === 'string') {
        message = payload.detail;
      } else if (payload.detail) {
        code = payload.detail.code ?? null;
        message = payload.detail.message ?? message;
      }
    } catch {
      // 본문이 JSON 이 아니면 기본 메시지를 사용한다.
    }
    throw new ApiError(message, response.status, code);
  }

  if (isStatic) {
    // 정적 호스팅은 없는 경로에 index.html 을 돌려줄 수 있다.
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('json')) {
      throw new ApiError(
        '최적화 결과 파일을 불러오지 못했습니다.',
        response.status,
        'RESULT_FILES_MISSING',
      );
    }
  }

  return (await response.json()) as T;
}
