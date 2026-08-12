/**
 * MOVE-AI Copilot 프록시 (Vercel Serverless Function).
 *
 * 정적으로 배포되는 화면과 달리, 챗봇만 서버 코드가 필요하다.
 * API 키를 브라우저에 노출하지 않기 위해서다.
 *
 * ── 현재 상태 ────────────────────────────────────────────────
 * 아직 생성형 AI 연동이 구현되지 않았다. 지금은 FastAPI 백엔드와 동일하게
 * 503 CHAT_API_NOT_CONFIGURED 를 반환하고, 프론트는 "API 미연결" 안내를 띄운다.
 * 가짜 AI 응답을 하드코딩하지 않는다 (핸드오프 §19.2).
 *
 * Gemini 연동은 본선 당일(2026-08-13)에 이 파일에 구현한다.
 * 키는 Vercel 환경변수 GEMINI_API_KEY 로 주입한다.
 * ─────────────────────────────────────────────────────────────
 *
 * Copilot 은 read-only 설명 계층이다. 수량 변경·재최적화·열차 재배정 요청은
 * 수행하지 않는다 (핸드오프 §19.3).
 */

const MUTATION_KEYWORDS = [
  '바꿔',
  '변경',
  '수정',
  '다시 계산',
  '재계산',
  '재최적화',
  '다시 최적화',
  '취소',
  '거절',
  '수락',
  '예약',
  '배차',
];

const MUTATION_REFUSAL =
  '현재 Copilot은 최적화 결과를 조회하고 설명하는 기능만 제공합니다.\n' +
  '최적화 수량 또는 조건을 변경하거나 재계산하지 않습니다.';

export default function handler(request, response) {
  if (request.method !== 'POST') {
    response.status(405).json({ detail: { code: 'METHOD_NOT_ALLOWED' } });
    return;
  }

  const message = String(request.body?.message ?? '');

  // 변경 요청은 AI 를 거치지 않고 정책 문구로 응답한다.
  if (MUTATION_KEYWORDS.some((keyword) => message.includes(keyword))) {
    response.status(200).json({
      reply: MUTATION_REFUSAL,
      conversationId: request.body?.conversationId ?? null,
      sources: [],
      readOnly: true,
    });
    return;
  }

  if (!process.env.GEMINI_API_KEY) {
    response.status(503).json({
      detail: {
        code: 'CHAT_API_NOT_CONFIGURED',
        message: '챗봇 API가 아직 연결되지 않았습니다.',
      },
    });
    return;
  }

  // TODO(2026-08-13): Gemini 호출 구현.
  //   - 정적 데이터(/data/carrier/<id>/*.json)를 근거 컨텍스트로 구성
  //   - 현재 선사 데이터만 사용, 컨텍스트에 없는 숫자는 만들어내지 않도록 지시
  response.status(503).json({
    detail: {
      code: 'CHAT_API_NOT_CONFIGURED',
      message: '챗봇 API가 아직 연결되지 않았습니다.',
    },
  });
}
