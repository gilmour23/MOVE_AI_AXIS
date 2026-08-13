import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { SegmentedControl } from '@/components/common/SegmentedControl';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { InventorySection } from '@/components/inventory/InventorySection';
import { InventoryComparison } from '@/components/inventory/InventoryComparison';
import { SizeSelector } from '@/components/inventory/SizeSelector';
import { fetchInventoryComparison } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useCarrierId, useMeta } from '@/app/MetaContext';
import type { ContainerSize } from '@/types/domain';
import styles from './InventoryPage.module.css';

type View = 'baseline' | 'postRail' | 'compare';

const VIEWS: { value: View; label: string }[] = [
  { value: 'baseline', label: '재배치 전' },
  { value: 'postRail', label: '재배치 후' },
  { value: 'compare', label: '비교' },
];

/** 어느 거점/규격이 계획기간 중 언제 부족해지고 철도 재배치 전후가 어떻게 달라지는가.
 *
 *  선택 상태는 URL query 에 반영한다:
 *  /carrier/inventory?week=...&hub=YAKMOK&size=20FT&view=compare */
export function InventoryPage() {
  const carrierId = useCarrierId();
  const { weekId, meta } = useMeta();
  const [params, setParams] = useSearchParams();

  const size = (params.get('size') as ContainerSize | null) ?? '20FT';
  const hub = params.get('hub');
  const view = (params.get('view') as View | null) ?? 'baseline';

  const patch = useCallback(
    (key: string, value: string) => {
      const updated = new URLSearchParams(params);
      updated.set(key, value);
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  const setSize = useCallback((next: ContainerSize) => patch('size', next), [patch]);
  const setHub = useCallback((next: string) => patch('hub', next), [patch]);
  const setView = useCallback((next: View) => patch('view', next), [patch]);

  // 비교 보기는 거점을 골라야 의미가 있다. 아직 안 골랐으면 요청하지 않는다.
  const comparisonHub = view === 'compare' ? (hub ?? 'YAKMOK') : null;
  const comparison = useAsync(
    (signal) =>
      carrierId && weekId && comparisonHub
        ? fetchInventoryComparison(carrierId, weekId, comparisonHub, size, signal)
        : Promise.resolve(null),
    [carrierId, weekId, comparisonHub, size],
  );

  return (
    <PageContainer
      title="재고"
      description="계획기간 중 어느 거점·규격이 언제 부족해지고, 철도 재배치 전후가 어떻게 달라지는지 확인합니다."
      action={
        <SegmentedControl
          options={VIEWS}
          value={view}
          onChange={(next) => setView(next as View)}
          ariaLabel="재고 보기 선택"
        />
      }
    >
      {view === 'compare' ? (
        <>
          <Card>
            <div className={styles.selectors}>
              <SizeSelector size={size} onSelectSize={setSize} />
              {/* 비교 보기는 canonical 6 거점을 그대로 유지한다.
                  이번 주 작업이 없는 거점도 빼지 않는다. */}
              <SegmentedControl
                options={(meta?.hubs ?? []).map((h) => ({
                  value: h.code,
                  label: h.shortName,
                }))}
                value={comparisonHub ?? ''}
                onChange={setHub}
                ariaLabel="거점 선택"
              />
            </div>
          </Card>

          {comparison.error && (
            <ErrorState error={comparison.error} onRetry={comparison.reload} />
          )}

          <Card>
            {comparison.loading && <LoadingSkeleton rows={6} height={24} />}
            {comparison.data && <InventoryComparison data={comparison.data} />}
          </Card>
        </>
      ) : (
        carrierId && (
          <InventorySection
            carrierId={carrierId}
            mode={view}
            size={size}
            onSelectSize={setSize}
            selectedHub={hub}
            onSelectHub={setHub}
            matrixSubtitle={
              view === 'baseline'
                ? '재배치 전 · 각 요일 마지막 시각의 예상 재고(개)'
                : '재배치 후 · 각 요일 마지막 시각의 예상 재고(개)'
            }
            showOptimizationLink={view === 'baseline'}
          />
        )
      )}
    </PageContainer>
  );
}
