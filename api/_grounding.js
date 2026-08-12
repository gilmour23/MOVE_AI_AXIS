/**
 * Copilot grounding — 질문에 필요한 canonical JSON 만 골라 컨텍스트를 만든다.
 *
 * 저장소 전체를 모델에 던지지 않는다. 정적 데이터는 배포된 사이트에서
 * 그대로 fetch 하므로 화면에 보이는 값과 컨텍스트가 항상 같다.
 */

const CARRIER_SOURCES = {
  optimization: 'optimization.json',
  overview: 'overview.json',
  transport: 'transport_comparison.json',
};

async function loadJson(baseUrl, path) {
  const response = await fetch(`${baseUrl}/data/${path}`);
  if (!response.ok) return null;
  return response.json();
}

/** 질문에서 canonical identifier 를 뽑는다. */
export function extractKeys(message) {
  const text = String(message ?? '');
  return {
    recommendationIds: [...new Set(text.match(/REC\d{4}/g) ?? [])],
    trainIds: [...new Set(text.match(/CAND\d{4}/g) ?? [])],
  };
}

function mentions(message, words) {
  return words.some((w) => message.includes(w));
}

/**
 * 질문 유형에 맞는 컨텍스트만 구성한다.
 *
 * @param {string} baseUrl  배포 origin (https://...)
 * @param {string} carrierId 현재 선사
 * @param {string} message  사용자 질문
 * @param {'carrier'|'korail'} role 화면 역할
 */
export async function buildContext(baseUrl, carrierId, message, role = 'carrier') {
  const text = String(message ?? '');
  const { recommendationIds, trainIds } = extractKeys(text);
  const context = { carrierId, role, sources: [] };

  const add = async (label, path, target) => {
    const data = await loadJson(baseUrl, path);
    if (data) {
      context[target] = data;
      context.sources.push(label);
    }
  };

  const meta = await loadJson(baseUrl, 'meta.json').catch(() => null);
  if (meta) {
    context.meta = {
      scenario: meta.scenario,
      horizonStart: meta.horizonStart,
      horizonEnd: meta.horizonEnd,
      isSyntheticCarrierData: meta.isSyntheticCarrierData,
      isPrototypeTimetable: meta.isPrototypeTimetable,
    };
  }

  if (role === 'korail') {
    await add('korail/overview', 'korail/overview.json', 'korailOverview');
    if (mentions(text, ['재고', '부족', '거점', 'stockout'])) {
      await add('korail/inventory', 'korail/inventory.json', 'korailInventory');
    }
    if (mentions(text, ['수요', '배정', 'need'])) {
      await add('korail/service_needs', 'korail/service_needs.json', 'korailNeeds');
    }
    if (mentions(text, ['분석', '권고', '영향'])) {
      await add('korail/insights', 'korail/insights.json', 'korailInsights');
    }
    for (const trainId of trainIds) {
      await add(
        `korail/train_details/${trainId}`,
        `korail/train_details/${trainId}.json`,
        'trainDetail',
      );
    }
    return context;
  }

  // Carrier 관점 — 현재 선사 데이터만 사용한다.
  const base = `carrier/${carrierId}`;

  if (mentions(text, ['재고', '부족', '수급', 'stockout'])) {
    await add(`${base}/overview`, `${base}/${CARRIER_SOURCES.overview}`, 'carrierOverview');
  }

  if (
    recommendationIds.length > 0 ||
    trainIds.length > 0 ||
    mentions(text, ['추천', '재배치', '왜', '배정', '열차', '제안'])
  ) {
    await add(
      `${base}/optimization`,
      `${base}/${CARRIER_SOURCES.optimization}`,
      'carrierOptimization',
    );
  }

  if (mentions(text, ['트럭', '비교', '운임', '비용', '탄소', 'co2', '리드타임'])) {
    await add(
      `${base}/transport_comparison`,
      `${base}/${CARRIER_SOURCES.transport}`,
      'transportComparison',
    );
  }

  for (const recId of recommendationIds) {
    await add(
      `${base}/recommendations/${recId}`,
      `${base}/optimization/recommendations/${recId}.json`,
      'recommendationDetail',
    );
  }

  // 아무 것도 못 골랐으면 최소한 자사 요약은 준다.
  if (context.sources.length === 0) {
    await add(`${base}/overview`, `${base}/${CARRIER_SOURCES.overview}`, 'carrierOverview');
  }

  return context;
}
