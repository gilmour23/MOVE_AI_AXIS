import { apiGet } from './client';
import type {
  ContainerSize,
  InventoryMode,
  KorailInsights,
  KorailNeedRow,
  KorailOverview,
  KorailStationHub,
  KorailTrain,
  KorailTrainDetail,
  KorailTransportAllocation,
  Meta,
  OptimizationData,
  OverviewData,
  RecommendationDetail,
  TransportComparison,
  WeeklyInventoryMatrixData,
  WeeklyInventorySummaryData,
} from '@/types/domain';
import type { KorailHub } from '@/types/domain';

export function fetchMeta(signal?: AbortSignal): Promise<Meta> {
  return apiGet<Meta>('/api/meta', signal);
}

export function fetchOverview(
  carrierId: string,
  signal?: AbortSignal,
): Promise<OverviewData> {
  return apiGet<OverviewData>(`/api/carrier/${carrierId}/overview`, signal);
}

export function fetchInventoryMatrix(
  carrierId: string,
  size: ContainerSize,
  mode: InventoryMode,
  signal?: AbortSignal,
): Promise<WeeklyInventoryMatrixData> {
  return apiGet<WeeklyInventoryMatrixData>(
    `/api/carrier/${carrierId}/inventory?size=${size}&mode=${mode}`,
    signal,
  );
}

export function fetchInventorySummary(
  carrierId: string,
  hubCode: string,
  size: ContainerSize,
  mode: InventoryMode,
  signal?: AbortSignal,
): Promise<WeeklyInventorySummaryData> {
  return apiGet<WeeklyInventorySummaryData>(
    `/api/carrier/${carrierId}/inventory/${hubCode}/${size}/summary?mode=${mode}`,
    signal,
  );
}

export function fetchOptimization(
  carrierId: string,
  signal?: AbortSignal,
): Promise<OptimizationData> {
  return apiGet<OptimizationData>(`/api/carrier/${carrierId}/optimization`, signal);
}

export function fetchRecommendationDetail(
  carrierId: string,
  recommendationId: string,
  signal?: AbortSignal,
): Promise<RecommendationDetail> {
  return apiGet<RecommendationDetail>(
    `/api/carrier/${carrierId}/optimization/recommendations/${recommendationId}`,
    signal,
  );
}

export function fetchTransportComparison(
  carrierId: string,
  signal?: AbortSignal,
): Promise<TransportComparison> {
  return apiGet<TransportComparison>(
    `/api/carrier/${carrierId}/transport`,
    signal,
  );
}

/* ── KORAIL Control Tower ─────────────────────────────────────── */

export function fetchKorailOverview(signal?: AbortSignal): Promise<KorailOverview> {
  return apiGet<KorailOverview>('/api/korail/overview', signal);
}

export function fetchKorailTrains(
  signal?: AbortSignal,
): Promise<{ trains: KorailTrain[] }> {
  return apiGet<{ trains: KorailTrain[] }>('/api/korail/trains', signal);
}

export function fetchKorailTrainDetail(
  trainId: string,
  signal?: AbortSignal,
): Promise<KorailTrainDetail> {
  return apiGet<KorailTrainDetail>(`/api/korail/trains/${trainId}`, signal);
}

export function fetchKorailNeeds(signal?: AbortSignal): Promise<{
  rows: KorailNeedRow[];
  totals: KorailOverview['needTotals'];
}> {
  return apiGet('/api/korail/needs', signal);
}

export function fetchKorailInventory(signal?: AbortSignal): Promise<{
  dates: string[];
  weekEndDate: string;
  hubs: KorailHub[];
}> {
  return apiGet('/api/korail/inventory', signal);
}

export function fetchKorailOperations(signal?: AbortSignal): Promise<{
  hubs: KorailStationHub[];
}> {
  return apiGet('/api/korail/operations', signal);
}

export function fetchKorailInsights(signal?: AbortSignal): Promise<KorailInsights> {
  return apiGet<KorailInsights>('/api/korail/insights', signal);
}

/** 선정 열차에 실제 배정된 공컨 운송물량 (CARRIER_ALLOCATION 기준).
 *  시각은 각 건의 origin/destination stop 에서 join 된 값이다. */
export function fetchKorailCargo(signal?: AbortSignal): Promise<{
  rows: KorailTransportAllocation[];
}> {
  return apiGet('/api/korail/cargo', signal);
}
