/**
 * Copilot grounding — 질문에 필요한 canonical JSON 만 골라 컨텍스트를 만든다.
 *
 * 저장소 전체를 모델에 던지지 않는다. 정적 데이터는 배포된 사이트에서
 * 그대로 fetch 하므로 화면에 보이는 값과 컨텍스트가 항상 같다.
 *
 * 모든 결과 조회는 주차 스코프를 갖는다. W01/W02 는 독립된 7일 결과이고
 * 같은 CAND ID 가 양쪽에 존재하므로, 주차 없이 읽으면 챗봇이 화면과
 * 다른 주차의 숫자로 답하게 된다.
 */

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

/** 요청된 weekId 가 실제 존재하는 주차인지 확인하고, 아니면 기본 주차로 떨어진다. */
export function resolveWeekId(meta, requested) {
  const weeks = meta?.weeks ?? [];
  if (requested && weeks.some((w) => w.weekId === requested)) return requested;
  return meta?.defaultWeekId ?? weeks[0]?.weekId ?? null;
}

/**
 * 질문 유형에 맞는 컨텍스트만 구성한다.
 *
 * @param {string} baseUrl  배포 origin (https://...)
 * @param {string} carrierId 현재 선사
 * @param {string} message  사용자 질문
 * @param {'carrier'|'korail'} role 화면 역할
 * @param {string|null} weekId 계획주차 (W01_2025-07-01). 없으면 기본 주차.
 */
export async function buildContext(
  baseUrl,
  carrierId,
  message,
  role = 'carrier',
  weekId = null,
) {
  const text = String(message ?? '');
  const { recommendationIds, trainIds } = extractKeys(text);

  const globalMeta = await loadJson(baseUrl, 'meta.json').catch(() => null);
  const week = resolveWeekId(globalMeta, weekId);
  const context = { carrierId, role, weekId: week, sources: [] };

  const add = async (label, path, target) => {
    const data = await loadJson(baseUrl, path);
    if (data) {
      context[target] = data;
      context.sources.push(label);
    }
  };

  if (week) {
    const weekMeta = await loadJson(baseUrl, `shared/weeks/${week}/meta.json`).catch(
      () => null,
    );
    if (weekMeta) {
      context.meta = {
        weekId: weekMeta.weekId,
        label: weekMeta.label,
        horizonStart: weekMeta.horizonStart,
        horizonEnd: weekMeta.horizonEnd,
        isSyntheticCarrierData: weekMeta.isSyntheticCarrierData,
        isPrototypeTimetable: weekMeta.isPrototypeTimetable,
      };
    }
  }

  if (role === 'korail') {
    const base = `korail/weeks/${week}`;
    await add(`${base}/overview`, `${base}/overview.json`, 'korailOverview');
    if (mentions(text, ['재고', '부족', '거점', 'stockout'])) {
      await add(`${base}/inventory`, `${base}/inventory.json`, 'korailInventory');
    }
    if (mentions(text, ['수요', '배정', 'need'])) {
      await add(`${base}/service_needs`, `${base}/service_needs.json`, 'korailNeeds');
    }
    if (mentions(text, ['분석', '권고', '영향'])) {
      await add(`${base}/insights`, `${base}/insights.json`, 'korailInsights');
    }
    for (const trainId of trainIds) {
      await add(
        `${base}/train_details/${trainId}`,
        `${base}/train_details/${trainId}.json`,
        'trainDetail',
      );
    }
    return context;
  }

  // Carrier 관점 — 현재 선사·현재 주차 데이터만 사용한다.
  const base = `carrier/${carrierId}/weeks/${week}`;

  if (mentions(text, ['재고', '부족', '수급', 'stockout'])) {
    await add(`${base}/overview`, `${base}/overview.json`, 'carrierOverview');
  }

  if (
    recommendationIds.length > 0 ||
    trainIds.length > 0 ||
    mentions(text, ['추천', '재배치', '왜', '배정', '열차', '제안'])
  ) {
    await add(`${base}/optimization`, `${base}/optimization.json`, 'carrierOptimization');
  }

  if (mentions(text, ['일정', '스케줄', '출발', '도착', '언제', '상차', '하차'])) {
    await add(`${base}/schedule`, `${base}/schedule.json`, 'carrierSchedule');
  }

  if (mentions(text, ['트럭', '비교', '운임', '비용', '탄소', 'co2', 'CO2', '절감', '리드타임'])) {
    await add(
      `${base}/transport_comparison`,
      `${base}/transport_comparison.json`,
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
    await add(`${base}/overview`, `${base}/overview.json`, 'carrierOverview');
  }

  return context;
}
