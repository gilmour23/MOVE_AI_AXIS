import { useEffect } from 'react';
import { Card } from '@/components/common/Card';
import {
  ChartSkeleton,
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  TableSkeleton,
} from '@/components/common/States';
import { HubSelector } from './HubSelector';
import { WeeklyInventoryLine } from './WeeklyInventoryLine';
import { WeeklyInventoryMatrix } from './WeeklyInventoryMatrix';
import { WeeklyInventorySummary } from './WeeklyInventorySummary';
import { SizeSelector } from './SizeSelector';
import { fetchInventoryMatrix, fetchInventorySummary } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { sizeTabLabel } from '@/lib/format';
import type { ContainerSize, InventoryMode } from '@/types/domain';
import styles from './InventorySection.module.css';

interface InventorySectionProps {
  carrierId: string;
  mode: InventoryMode;
  size: ContainerSize;
  onSelectSize: (size: ContainerSize) => void;
  selectedHub: string | null;
  onSelectHub: (hubCode: string) => void;
  matrixSubtitle?: string;
  showOptimizationLink?: boolean;
}

/** 재고 페이지(baseline)와 최적화 페이지 Section D(postRail)가 공유하는 블록.
 *  차이는 mode prop 하나뿐이다 (핸드오프 §17.5).
 *  PDF 2·4페이지처럼 `규격별 재고 현황` 라벨과 20/40피트 탭은 매트릭스 바로 위에 둔다. */
export function InventorySection({
  carrierId,
  mode,
  size,
  onSelectSize,
  selectedHub,
  onSelectHub,
  matrixSubtitle,
  showOptimizationLink = false,
}: InventorySectionProps) {
  const matrix = useAsync(
    (signal) => fetchInventoryMatrix(carrierId, size, mode, signal),
    [carrierId, size, mode],
  );

  // 선택된 거점이 없으면 첫 번째 거점을 기본 선택한다.
  const hubs = matrix.data?.hubs ?? [];
  useEffect(() => {
    if (!selectedHub && hubs.length > 0) {
      onSelectHub(hubs[0].hubCode);
    }
  }, [selectedHub, hubs, onSelectHub]);

  const summary = useAsync(
    (signal) =>
      selectedHub
        ? fetchInventorySummary(carrierId, selectedHub, size, mode, signal)
        : Promise.resolve(null),
    [carrierId, selectedHub, size, mode],
  );

  const selectedHubData = hubs.find((hub) => hub.hubCode === selectedHub) ?? null;

  return (
    <div className={styles.stack}>
      {/* 1단계 — 규격 선택. 아래 매트릭스와 거점 상세가 모두 이 값을 따른다. */}
      <Card>
        <SizeSelector
          size={size}
          onSelectSize={onSelectSize}
          hint="규격을 선택하면 아래 거점별 재고와 추이가 모두 바뀝니다."
        />
      </Card>

      {/* 2단계 — 선택 규격의 거점 × 요일 재고 */}
      <Card title={`${sizeTabLabel(size)} 거점별 요일 재고`} subtitle={matrixSubtitle}>
        {matrix.loading && <TableSkeleton rows={6} columns={7} />}
        {matrix.error && <ErrorState error={matrix.error} onRetry={matrix.reload} />}
        {matrix.data && matrix.data.hubs.length === 0 && (
          <EmptyState
            title="표시할 재고 데이터가 없습니다."
            description="현재 계획 기간에 해당 규격의 재고 기록이 없습니다."
          />
        )}
        {matrix.data && matrix.data.hubs.length > 0 && (
          <WeeklyInventoryMatrix
            data={matrix.data}
            selectedHub={selectedHub}
            onSelectHub={onSelectHub}
          />
        )}
      </Card>

      {/* 3단계 — 거점 선택 */}
      {matrix.data && matrix.data.hubs.length > 0 && (
        <Card>
          <HubSelector
            hubs={matrix.data.hubs}
            selectedHub={selectedHub}
            onSelectHub={onSelectHub}
            hint="거점을 선택하면 아래 추이와 요약이 함께 바뀝니다."
          />
        </Card>
      )}

      <div className={styles.detailGrid}>
        <Card
          title={
            selectedHubData
              ? `${selectedHubData.hubName} · ${size} 주간 재고 추이`
              : '주간 재고 추이'
          }
          subtitle="월~일 요일별 예상 재고(개)"
        >
          {summary.loading && <ChartSkeleton />}
          {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
          {summary.data && <WeeklyInventoryLine daily={summary.data.daily} />}
          {!summary.loading && !summary.error && !summary.data && (
            <EmptyState title="거점을 선택해주세요." />
          )}
        </Card>

        <Card title="주간 요약" subtitle={selectedHubData?.hubName ?? undefined}>
          {summary.loading && <LoadingSkeleton rows={5} height={22} />}
          {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
          {summary.data && (
            <WeeklyInventorySummary
              summary={summary.data}
              showOptimizationLink={showOptimizationLink}
            />
          )}
        </Card>
      </div>
    </div>
  );
}
