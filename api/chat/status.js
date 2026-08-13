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
  const keys = (process.env.GEMINI_API_KEYS || process.env.GEMINI_API_KEY || '')
    .split(',')
    .map((key) => key.trim())
    .filter(Boolean);

  response.status(200).json({
    configured: keys.length > 0,
    readOnly: true,
    allowedSources: ALLOWED_CONTEXT_SOURCES,
    // 진단용. 키 값은 절대 내보내지 않고 존재 여부와 개수만 알린다.
    // 설정했는데 configured 가 false 면, 환경변수 이름이 다르거나
    // 재배포를 안 해서 옛 빌드가 서빙되는 것이다.
    diagnostics: {
      apiVersion: 'week-scoped-2026-08',
      hasKeyPool: Boolean(process.env.GEMINI_API_KEYS),
      hasSingleKey: Boolean(process.env.GEMINI_API_KEY),
      keyCount: keys.length,
      model: process.env.GEMINI_MODEL || 'gemini-3.6-flash',
    },
  });
}
