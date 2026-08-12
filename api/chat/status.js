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
  response.status(200).json({
    configured: Boolean(process.env.GEMINI_API_KEY),
    readOnly: true,
    allowedSources: ALLOWED_CONTEXT_SOURCES,
  });
}
