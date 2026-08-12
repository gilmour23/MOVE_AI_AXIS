import { useState } from 'react';
import { X } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { SegmentedControl } from '@/components/common/SegmentedControl';
import { fetchKorailInventory } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatNumber, sizeTabLabel } from '@/lib/format';
import type { ContainerSize, KorailHub } from '@/types/domain';
import styles from './Korail.module.css';

const SIZE_OPTIONS = (['20FT', '40FT'] as ContainerSize[]).map((v) => ({
  value: v,
  label: sizeTabLabel(v),
}));

/** 거점 재고 모니터링.
 *  hub total 은 운영 현황 집계이며 선사 간 소유권을 섞지 않는다.
 *  거점을 클릭하면 선사별 breakdown 을 보여준다. */
export function KorailInventoryPage() {
  const [size, setSize] = useState<ContainerSize>('20FT');
  const [hubCode, setHubCode] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailInventory(signal), []);

  const hub = data?.hubs.find((h) => h.hubCode === hubCode) ?? null;

  return (
    <PageContainer
      title="거점 재고 모니터링"
      description="전 선사 합산 운영 현황입니다. 거점을 클릭하면 선사별 내역을 볼 수 있습니다."
      action={
        <SegmentedControl
          options={SIZE_OPTIONS}
          value={size}
          onChange={setSize}
          ariaLabel="컨테이너 규격 선택"
        />
      }
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={6} height={24} />
        </Card>
      )}

      {data && (
        <Card
          title={`${sizeTabLabel(size)} 거점별 수급 현황`}
          subtitle={`주말(${data.weekEndDate}) 기준 · 전 선사 합산`}
        >
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>거점</th>
                  <th className={styles.right}>수요</th>
                  <th className={styles.right}>외부 공급</th>
                  <th className={styles.right}>철도 유입</th>
                  <th className={styles.right}>철도 반출</th>
                  <th className={styles.right}>재배치 전 재고</th>
                  <th className={styles.right}>재배치 후 재고</th>
                  <th className={styles.right}>부족 (전→후)</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {data.hubs.map((row) => {
                  const s = row.sizes[size];
                  return (
                    <tr
                      key={row.hubCode}
                      className={[
                        styles.rowClickable,
                        row.hubCode === hubCode ? styles.rowActive : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      onClick={() => setHubCode(row.hubCode)}
                    >
                      <td>{row.hubName}</td>
                      <td className={styles.right}>{formatNumber(s.demand)}</td>
                      <td className={styles.right}>{formatNumber(s.externalSupply)}</td>
                      <td className={styles.right}>{formatNumber(s.railInbound)}</td>
                      <td className={styles.right}>{formatNumber(s.railOutbound)}</td>
                      <td className={styles.right}>{formatNumber(s.baselineInventory)}</td>
                      <td className={styles.right}>{formatNumber(s.postRailInventory)}</td>
                      <td className={styles.right}>
                        {s.baselineStockout} → {s.postRailStockout}
                      </td>
                      <td>
                        <StatusBadge
                          tone={
                            row.status === '정상'
                              ? 'normal'
                              : row.status === '부족 해소'
                                ? 'info'
                                : 'shortage'
                          }
                          small
                        >
                          {row.status}
                        </StatusBadge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className={styles.note} style={{ marginTop: 12 }}>
            합산은 화면상 운영 현황 집계이며 선사 간 컨테이너 소유권을 변경하지 않습니다.
            상태는 데이터에서 직접 계산 가능한 부족(stockout) 발생 여부만으로 판정하며,
            임의 안전재고 기준을 적용하지 않습니다.
          </div>
        </Card>
      )}

      {hub && <HubDrawer hub={hub} size={size} onClose={() => setHubCode(null)} />}
    </PageContainer>
  );
}

function HubDrawer({
  hub,
  size,
  onClose,
}: {
  hub: KorailHub;
  size: ContainerSize;
  onClose: () => void;
}) {
  return (
    <>
      <div className={styles.overlay} onClick={onClose} role="presentation" />
      <aside className={styles.drawer} role="dialog" aria-label={`${hub.hubName} 선사별 재고`}>
        <header className={styles.drawerHeader}>
          <div>
            <div className={styles.drawerTitle}>{hub.hubName}</div>
            <div className={styles.drawerSub}>{sizeTabLabel(size)} 선사별 재고 내역</div>
          </div>
          <button type="button" className={styles.drawerClose} onClick={onClose} aria-label="닫기">
            <X size={17} />
          </button>
        </header>

        <div className={styles.drawerBody}>
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>선사</th>
                  <th className={styles.right}>재배치 전</th>
                  <th className={styles.right}>재배치 후</th>
                  <th className={styles.right}>철도 유입</th>
                  <th className={styles.right}>철도 반출</th>
                  <th className={styles.right}>부족</th>
                </tr>
              </thead>
              <tbody>
                {hub.byCarrier.map((row) => {
                  const s = row.sizes[size];
                  return (
                    <tr key={row.carrierId}>
                      <td>{row.carrierLabel}</td>
                      <td className={styles.right}>{s.baselineInventory}</td>
                      <td className={styles.right}>{s.postRailInventory}</td>
                      <td className={styles.right}>{s.railInbound}</td>
                      <td className={styles.right}>{s.railOutbound}</td>
                      <td className={styles.right}>
                        {s.baselineStockout} → {s.postRailStockout}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className={styles.note}>
            선사별 재고는 각 선사가 소유한 물량입니다. 특정 선사의 부족을 다른 선사의
            컨테이너로 해소하지 않으며, 열차 Capacity 만 공동 이용합니다.
          </div>
        </div>
      </aside>
    </>
  );
}
