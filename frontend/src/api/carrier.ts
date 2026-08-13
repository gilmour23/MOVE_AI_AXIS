import { apiGet } from './client';
import type {
  ContainerSize,
  GlobalMeta,
  HubInventoryComparison,
  InventoryMode,
  KorailInsights,
  KorailNeedRow,
  KorailOverview,
  KorailStationHub,
  KorailTrain,
  KorailTrainDetail,
  KorailTransportAllocation,
  OptimizationData,
  OverviewData,
  RecommendationDetail,
  TransportComparison,
  WeekMeta,
  WeeklyInventoryMatrixData,
  WeeklyInventorySummaryData,
} from '@/types/domain';
import type { KorailHub } from '@/types/domain';

/** 모든 결과 조회는 주차 스코프를 갖는다.
 *
 *  W01/W02 는 독립된 7일 결과이고 같은 CAND ID 가 양쪽에 존재한다.
 *  weekId 없이 조회하면 조용히 다른 주차의 열차를 보게 되므로,
 *  fetch 함수는 전부 weekId 를 필수 인자로 받는다. */
function withWeek(path: string, weekId: string, extra?: string): string {
  const query = extra ? `${extra}&week=${weekId}` : `week=${weekId}`;
  return `${path}?${query}`;
}

/** 주차 무관 전역 메타 — week 목록, hub, 현재 선사. */
export function fetchMeta(signal?: AbortSignal): Promise<GlobalMeta> {
  return apiGet<GlobalMeta>('/api/meta', signal);
}

/** 선택 주차의 horizon 과 provenance. */
export function fetchWeekMeta(
  weekId: string,
  signal?: AbortSignal,
): Promise<WeekMeta> {
  return apiGet<WeekMeta>(`/api/weeks/${weekId}/meta`, signal);
}

export function fetchOverview(
  carrierId: string,
  weekId: string,
  signal?: AbortSignal,
): Promise<OverviewData> {
  return apiGet<OverviewData>(
    withWeek(`/api/carrier/${carrierId}/overview`, weekId),
    signal,
  );
}

export function fetchInventoryMatrix(
  carrierId: string,
  weekId: string,
  size: ContainerSize,
  mode: InventoryMode,
  signal?: AbortSignal,
): Promise<WeeklyInventoryMatrixData> {
  return apiGet<WeeklyInventoryMatrixData>(
    withWeek(`/api/carrier/${carrierId}/inventory`, weekId, `size=${size}&mode=${mode}`),
    signal,
  );
}

export function fetchInventorySummary(
  carrierId: string,
  weekId: string,
  hubCode: string,
  size: ContainerSize,
  mode: InventoryMode,
  signal?: AbortSignal,
): Promise<WeeklyInventorySummaryData> {
  return apiGet<WeeklyInventorySummaryData>(
    withWeek(
      `/api/carrier/${carrierId}/inventory/${hubCode}/${size}/summary`,
      weekId,
      `mode=${mode}`,
    ),
    signal,
  );
}

/** 재배치 전/후 비교. 두 mode 를 각각 받지 않고 한 번에 받아 같은 축에 그린다. */
export function fetchInventoryComparison(
  carrierId: string,
  weekId: string,
  hubCode: string,
  size: ContainerSize,
  signal?: AbortSignal,
): Promise<HubInventoryComparison> {
  return apiGet<HubInventoryComparison>(
    withWeek(`/api/carrier/${carrierId}/inventory/${hubCode}/${size}/comparison`, weekId),
    signal,
  );
}

export function fetchOptimization(
  carrierId: string,
  weekId: string,
  signal?: AbortSignal,
): Promise<OptimizationData> {
  return apiGet<OptimizationData>(
    withWeek(`/api/carrier/${carrierId}/optimization`, weekId),
    signal,
  );
}

export function fetchRecommendationDetail(
  carrierId: string,
  weekId: string,
  recommendationId: string,
  signal?: AbortSignal,
): Promise<RecommendationDetail> {
  return apiGet<RecommendationDetail>(
    withWeek(
      `/api/carrier/${carrierId}/optimization/recommendations/${recommendationId}`,
      weekId,
    ),
    signal,
  );
}

export function fetchTransportComparison(
  carrierId: string,
  weekId: string,
  signal?: AbortSignal,
): Promise<TransportComparison> {
  return apiGet<TransportComparison>(
    withWeek(`/api/carrier/${carrierId}/transport`, weekId),
    signal,
  );
}

/* ── KORAIL Control Tower ─────────────────────────────────────── */

export function fetchKorailOverview(
  weekId: string,
  signal?: AbortSignal,
): Promise<KorailOverview> {
  return apiGet<KorailOverview>(withWeek('/api/korail/overview', weekId), signal);
}

export function fetchKorailTrains(
  weekId: string,
  signal?: AbortSignal,
): Promise<{ trains: KorailTrain[] }> {
  return apiGet<{ trains: KorailTrain[] }>(
    withWeek('/api/korail/trains', weekId),
    signal,
  );
}

/** 열차 상세는 반드시 week + trainId 로 찾는다. trainId 만으로 전역 lookup 하지 않는다. */
export function fetchKorailTrainDetail(
  weekId: string,
  trainId: string,
  signal?: AbortSignal,
): Promise<KorailTrainDetail> {
  return apiGet<KorailTrainDetail>(
    withWeek(`/api/korail/trains/${trainId}`, weekId),
    signal,
  );
}

export function fetchKorailNeeds(
  weekId: string,
  signal?: AbortSignal,
): Promise<{
  rows: KorailNeedRow[];
  totals: KorailOverview['needTotals'];
}> {
  return apiGet(withWeek('/api/korail/needs', weekId), signal);
}

export function fetchKorailInventory(
  weekId: string,
  signal?: AbortSignal,
): Promise<{
  dates: string[];
  weekEndDate: string;
  hubs: KorailHub[];
}> {
  return apiGet(withWeek('/api/korail/inventory', weekId), signal);
}

export function fetchKorailOperations(
  weekId: string,
  signal?: AbortSignal,
): Promise<{
  hubs: KorailStationHub[];
}> {
  return apiGet(withWeek('/api/korail/operations', weekId), signal);
}

export function fetchKorailInsights(
  weekId: string,
  signal?: AbortSignal,
): Promise<KorailInsights> {
  return apiGet<KorailInsights>(withWeek('/api/korail/insights', weekId), signal);
}

/** 선정 열차에 실제 배정된 공컨 운송물량 (CARRIER_ALLOCATION 기준).
 *  시각은 각 건의 origin/destination stop 에서 join 된 값이다. */
export function fetchKorailCargo(
  weekId: string,
  signal?: AbortSignal,
): Promise<{
  rows: KorailTransportAllocation[];
}> {
  return apiGet(withWeek('/api/korail/cargo', weekId), signal);
}
