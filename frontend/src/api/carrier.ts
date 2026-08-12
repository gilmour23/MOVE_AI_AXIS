import { apiGet } from './client';
import type {
  ContainerSize,
  InventoryMode,
  Meta,
  OptimizationData,
  OverviewData,
  RecommendationDetail,
  WeeklyInventoryMatrixData,
  WeeklyInventorySummaryData,
} from '@/types/domain';

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
