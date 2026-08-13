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
 *  - API 키는 Vercel 환경변수에서만 읽는다. 클라이언트 번들에 절대 넣지 않는다.
 *    (GEMINI_API_KEYS 에 쉼표로 여러 개를 주면 한도 초과 시 순환한다)
 */

import { buildContext } from './_grounding.js';

// gemini-2.0-flash 는 2026-08 현재 은퇴됐다(404). 팀이 검증한 모델을 기본으로 둔다.
const MODEL = process.env.GEMINI_MODEL || 'gemini-3.6-flash';

/** 무료 키의 분당 한도를 넘겼을 때를 위한 키 풀. 첫 키부터 순서대로 시도한다. */
function apiKeyPool() {
  const pool = (process.env.GEMINI_API_KEYS || process.env.GEMINI_API_KEY || '')
    .split(',')
    .map((key) => key.trim())
    .filter(Boolean);
  return pool;
}

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

const SYSTEM_INSTRUCTION = `당신은 MOVE-AI Copilot, 선사(Shipowner) 전용 AI 어시스턴트입니다.
MOVE-AI는 여러 선사의 공컨테이너 수요를 함께 최적화해 신규 공컨 전용 화물열차를
추가 배차하는 플랫폼입니다. 기존 화물열차의 잔여용량을 활용하는 서비스가 아닙니다.
컨테이너 소유권은 선사별로 독립이며 재고를 공유하지 않습니다. 열차 Capacity만 공동 이용합니다.

역할: 이미 계산이 끝난 MILP 최적화 결과를 조회하고 설명합니다.
완전한 읽기 전용(Read-only) 인터페이스이며, 재최적화를 제안하거나 재고를
예약/할당해 주겠다는 식의 답변을 절대로 하지 않습니다.

반드시 지킬 것
- 답변의 모든 수치는 제공된 컨텍스트(JSON)에 있는 값만 사용합니다.
- 컨텍스트에 없는 숫자는 추정하거나 계산해서 만들어내지 마십시오.
  모르면 "제공된 결과에 해당 값이 없습니다"라고 답하십시오.
- 컨텍스트의 weekId 가 현재 계획주차입니다. 다른 주차의 값과 섞지 마십시오.
- 선사 관점(role=carrier) 질문에는 해당 선사 데이터만 사용합니다.
  다른 선사의 배정 상세를 추측하거나 언급하지 마십시오.
- 수량 단위는 컨테이너 개수(boxes)와 TEU를 구분합니다. 40FT 1개는 2TEU입니다.
- 재고는 0 아래로 내려가지 않으며 충족하지 못한 수요는 별도 부족(unmet/stockout)으로 표시됩니다.
- 운행시각이 프로토타입 운행후보 기준이면 "KORAIL 실제 운행시각"이라고 말하지 마십시오.
- 철도 vs 트럭 절감 질문에는 transportComparison 의 값(costSavingKrw,
  carbonSavingKg 등 이미 계산된 차이)을 그대로 인용해 철도 전환의 장점을 설명합니다.

대화 스타일
- 사람과 대화하듯 부드럽고 간결하게, 핵심만 요약해서 답합니다. 기계적인 전체 나열(TMI)을 하지 않습니다.
  (예: "다음 주 약목역의 가용 재고는 총 46개입니다. 주로 CAND0158 열차 등을 통해 배정된 물량입니다.")
- 재고를 말할 때는 '가용 재고'라는 표현을 사용합니다.
- 한국어 3~6문장. 마크다운 표·목록·굵게 서식 없이 일반 문장으로 답합니다.`;

function send(response, status, body) {
  response.status(status).json(body);
}

/** 프론트가 보낸 대화 이력을 Gemini contents 형식으로 바꾼다. 최근 10건만 쓴다. */
function toContents(history, message) {
  const turns = Array.isArray(history) ? history.slice(-10) : [];
  const contents = [];
  for (const turn of turns) {
    const role = turn?.role === 'model' ? 'model' : 'user';
    const text = String(turn?.text ?? '').trim();
    if (text) contents.push({ role, parts: [{ text }] });
  }
  contents.push({ role: 'user', parts: [{ text: message }] });
  return contents;
}

async function callGemini(apiKey, requestBody) {
  return fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': apiKey,
      },
      body: JSON.stringify(requestBody),
    },
  );
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    return send(response, 405, { detail: { code: 'METHOD_NOT_ALLOWED' } });
  }

  const body = request.body ?? {};
  const message = String(body.message ?? '').trim();
  const carrierId = String(body.carrierId || 'CARRIER_A');
  const role = body.role === 'korail' ? 'korail' : 'carrier';
  const weekId = body.weekId ? String(body.weekId) : null;

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

  const keys = apiKeyPool();
  if (keys.length === 0) {
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
    context = await buildContext(baseUrl, carrierId, message, role, weekId);
  } catch (error) {
    return send(response, 502, {
      detail: { code: 'CONTEXT_BUILD_FAILED', message: String(error) },
    });
  }

  const requestBody = {
    systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
    contents: toContents(body.history, [
      `아래는 현재 최적화 결과입니다. 이 JSON에 있는 값만 사용하세요.`,
      ``,
      `<context>`,
      JSON.stringify(context),
      `</context>`,
      ``,
      `질문: ${message}`,
    ].join('\n')),
    generationConfig: { temperature: 0.2, maxOutputTokens: 800 },
  };

  // 한도 초과(429)나 키 문제(403)면 다음 키로 순환한다.
  let lastFailure = null;
  for (const apiKey of keys) {
    let geminiResponse;
    try {
      geminiResponse = await callGemini(apiKey, requestBody);
    } catch (error) {
      lastFailure = { status: 0, detail: String(error) };
      continue;
    }

    if (geminiResponse.status === 429 || geminiResponse.status === 403) {
      lastFailure = {
        status: geminiResponse.status,
        detail: (await geminiResponse.text()).slice(0, 300),
      };
      continue;
    }

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
  }

  return send(response, 502, {
    detail: {
      code: 'CHAT_API_ERROR',
      message: '사용 가능한 API 키가 없습니다 (한도 초과 또는 키 오류).',
      detail: lastFailure ? `마지막 실패: ${lastFailure.status}` : undefined,
    },
  });
}
