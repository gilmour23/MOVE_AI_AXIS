/**
 * 챗봇 연결 상태 조회.
 * 프론트는 이 값으로 입력창 활성화 여부와 안내 문구를 결정한다.
 */

const ALLOWED_CONTEXT_SOURCES = [
  'CARRIER_RECOMMENDATIONS_<CARRIER>.csv',
  'RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv',
  'CARRIER_INVENTORY_TIMELINE.csv',
  'INVENTORY_IMPACT_SUMMARY.csv',
  'CARRIER_SERVICE_SUMMARY.csv',
  'SERVICE_NEED_RESULT.csv',
];

export default function handler(_request, response) {
  // 키 풀(GEMINI_API_KEYS, 쉼표 구분) 또는 단일 키(GEMINI_API_KEY) 중 하나라도 있으면 연결된 것.
  const configured = Boolean(
    (process.env.GEMINI_API_KEYS || process.env.GEMINI_API_KEY || '')
      .split(',')
      .map((key) => key.trim())
      .filter(Boolean).length,
  );

  response.status(200).json({
    configured,
    readOnly: true,
    allowedSources: ALLOWED_CONTEXT_SOURCES,
  });
}
