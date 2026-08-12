/** 프론트엔드는 자기 백엔드(/api)만 호출한다.
 *  타 선사 필터링/집계는 모두 백엔드에서 끝난다 (핸드오프 §6, §10). */

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

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
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

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error;
    throw new ApiError(
      '서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해주세요.',
      0,
      'NETWORK_ERROR',
    );
  }

  if (!response.ok) {
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

  return (await response.json()) as T;
}
