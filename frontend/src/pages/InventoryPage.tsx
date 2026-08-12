import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { InventorySection } from '@/components/inventory/InventorySection';
import { useCarrierId } from '@/app/MetaContext';
import type { ContainerSize } from '@/types/domain';

/** MOVE-AI 적용 전 baseline inventory 를 보여준다 (핸드오프 §16).
 *  선택 상태는 URL query 에 반영한다: /inventory?size=20FT&hub=UIWANG */
export function InventoryPage() {
  const carrierId = useCarrierId();
  const [params, setParams] = useSearchParams();

  const size = (params.get('size') as ContainerSize | null) ?? '20FT';
  const hub = params.get('hub');

  const setSize = useCallback(
    (next: ContainerSize) => {
      const updated = new URLSearchParams(params);
      updated.set('size', next);
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  const setHub = useCallback(
    (next: string) => {
      const updated = new URLSearchParams(params);
      updated.set('hub', next);
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  return (
    <PageContainer
      title="규격별 주간 예상 재고"
      description="현재 계획의 수요·외부 공급 기준 (MOVE-AI 재배치 적용 전)"
    >
      {carrierId && (
        <InventorySection
          carrierId={carrierId}
          mode="baseline"
          size={size}
          onSelectSize={setSize}
          selectedHub={hub}
          onSelectHub={setHub}
          matrixSubtitle="재배치 전 · 각 요일 마지막 시각의 예상 재고(개)"
          showOptimizationLink
        />
      )}
    </PageContainer>
  );
}
