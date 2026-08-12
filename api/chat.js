/**
 * MOVE-AI Copilot — Gemini 프록시 (Vercel Serverless Function).
 *
 * 화면과 데이터는 정적으로 서빙되지만, API 키를 브라우저에 노출할 수 없으므로
 * 생성형 AI 호출만 이 함수를 거친다.
 *
 * 원칙
 *  - READ ONLY. 재최적화·수량 변경·열차 변경·스케줄 변경을 수행하지 않는다.
 *  - 컨텍스트에 있는 숫자만 사용한다. 없는 값은 만들어내지 않는다.
 *  - 선사 화면 질문에는 해당 선사 데이터만 컨텍스트로 넣는다.
 *  - GEMINI_API_KEY 는 Vercel 환경변수에서만 읽는다.
 */

import { buildContext } from './_grounding.js';

const MODEL = process.env.GEMINI_MODEL || 'gemini-2.0-flash';

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
  '늘려',
  '줄여',
];

const MUTATION_REFUSAL =
  '현재 Copilot은 최적화 결과를 조회하고 설명하는 기능만 제공합니다.\n' +
  '최적화 수량 또는 조건을 변경하거나 재계산하지 않습니다.';

const SYSTEM_INSTRUCTION = `당신은 MOVE-AI Copilot입니다.
MOVE-AI는 여러 선사의 공컨테이너 수요를 함께 최적화해 신규 공컨 전용 화물열차를
추가 배차하는 플랫폼입니다. 기존 화물열차의 잔여용량을 활용하는 서비스가 아닙니다.
컨테이너 소유권은 선사별로 독립이며 재고를 공유하지 않습니다. 열차 Capacity만 공동 이용합니다.

역할: 이미 계산이 끝난 MILP 최적화 결과를 조회하고 설명합니다.

반드시 지킬 것
- 답변의 모든 수치는 제공된 컨텍스트(JSON)에 있는 값만 사용합니다.
- 컨텍스트에 없는 숫자는 추정하거나 계산해서 만들어내지 마십시오.
  모르면 "제공된 결과에 해당 값이 없습니다"라고 답하십시오.
- 재최적화, 수량 변경, 열차 변경, 스케줄 변경은 수행하지 않습니다.
- 선사 관점(role=carrier) 질문에는 해당 선사 데이터만 사용합니다.
  다른 선사의 배정 상세를 추측하거나 언급하지 마십시오.
- 수량 단위는 컨테이너 개수(boxes)와 TEU를 구분합니다. 40FT 1개는 2TEU입니다.
- 재고는 0 아래로 내려가지 않으며 충족하지 못한 수요는 별도 부족(unmet/stockout)으로 표시됩니다.
- 운행시각이 프로토타입 운행후보 기준이면 "KORAIL 실제 운행시각"이라고 말하지 마십시오.

형식: 한국어로 3~6문장. 핵심 수치를 근거로 간결하게 설명합니다.`;

function send(response, status, body) {
  response.status(status).json(body);
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    return send(response, 405, { detail: { code: 'METHOD_NOT_ALLOWED' } });
  }

  const body = request.body ?? {};
  const message = String(body.message ?? '').trim();
  const carrierId = String(body.carrierId || 'CARRIER_A');
  const role = body.role === 'korail' ? 'korail' : 'carrier';

  if (!message) {
    return send(response, 400, { detail: { code: 'EMPTY_MESSAGE' } });
  }

  // 변경 요청은 모델을 거치지 않고 정책 문구로 응답한다.
  if (MUTATION_KEYWORDS.some((keyword) => message.includes(keyword))) {
    return send(response, 200, {
      reply: MUTATION_REFUSAL,
      conversationId: body.conversationId ?? null,
      sources: [],
      readOnly: true,
    });
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return send(response, 503, {
      detail: {
        code: 'CHAT_API_NOT_CONFIGURED',
        message: '챗봇 API가 아직 연결되지 않았습니다.',
      },
    });
  }

  const proto = request.headers['x-forwarded-proto'] || 'https';
  const host = request.headers['x-forwarded-host'] || request.headers.host;
  const baseUrl = `${proto}://${host}`;

  let context;
  try {
    context = await buildContext(baseUrl, carrierId, message, role);
  } catch (error) {
    return send(response, 502, {
      detail: { code: 'CONTEXT_BUILD_FAILED', message: String(error) },
    });
  }

  try {
    const geminiResponse = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-goog-api-key': apiKey,
        },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
          contents: [
            {
              role: 'user',
              parts: [
                {
                  text:
                    `아래는 현재 최적화 결과입니다. 이 JSON에 있는 값만 사용하세요.\n\n` +
                    `<context>\n${JSON.stringify(context)}\n</context>\n\n` +
                    `질문: ${message}`,
                },
              ],
            },
          ],
          generationConfig: { temperature: 0.2, maxOutputTokens: 800 },
        }),
      },
    );

    if (!geminiResponse.ok) {
      const detail = await geminiResponse.text();
      return send(response, 502, {
        detail: {
          code: 'CHAT_API_ERROR',
          message: `Gemini 응답 오류 (${geminiResponse.status})`,
          detail: detail.slice(0, 500),
        },
      });
    }

    const payload = await geminiResponse.json();
    const reply =
      payload?.candidates?.[0]?.content?.parts?.map((p) => p.text).join('') ?? '';

    if (!reply.trim()) {
      return send(response, 502, {
        detail: { code: 'CHAT_EMPTY_REPLY', message: '응답을 생성하지 못했습니다.' },
      });
    }

    return send(response, 200, {
      reply,
      conversationId: body.conversationId ?? null,
      sources: context.sources,
      readOnly: true,
    });
  } catch (error) {
    return send(response, 502, {
      detail: { code: 'CHAT_API_ERROR', message: String(error) },
    });
  }
}
