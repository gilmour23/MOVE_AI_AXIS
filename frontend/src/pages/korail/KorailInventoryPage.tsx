import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
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
import { statusTone } from './statusTone';
import styles from './Korail.module.css';

const SIZES: ContainerSize[] = ['20FT', '40FT'];

const SIZE_OPTIONS = SIZES.map((v) => ({ value: v, label: sizeTabLabel(v) }));

function isContainerSize(value: string | null): value is ContainerSize {
  return value === '20FT' || value === '40FT';
}

/** 거점 재고 모니터링.
 *  hub total 은 운영 현황 집계이며 선사 간 소유권을 섞지 않는다.
 *  거점을 클릭하면 선사별 breakdown 을 보여준다.
 *
 *  ?hub=BUSAN&size=40FT 로 진입하면 해당 거점·규격이 선택된 상태로 열린다
 *  (수요·배정 / 대시보드에서의 drill-down 진입점). */
export function KorailInventoryPage() {
  const [params] = useSearchParams();
  const requestedHub = params.get('hub');
  const requestedSize = params.get('size');

  const [size, setSize] = useState<ContainerSize>(
    isContainerSize(requestedSize) ? requestedSize : '20FT',
  );
  const [hubCode, setHubCode] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailInventory(signal), []);

  // query 로 지정된 거점이 실제로 존재할 때만 선택한다.
  useEffect(() => {
    if (!requestedHub || !data) return;
    if (data.hubs.some((h) => h.hubCode === requestedHub)) setHubCode(requestedHub);
  }, [requestedHub, data]);

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
                {/* 재배치 전 → 철도 유입·반출 → 재배치 후 → 부족 순으로 읽히게 한다.
                    수요·외부 공급은 보조 정보로 뒤에 둔다. */}
                <tr>
                  <th>거점</th>
                  <th className={styles.right}>재배치 전 재고</th>
                  <th className={styles.right}>철도 유입</th>
                  <th className={styles.right}>철도 반출</th>
                  <th className={styles.right}>재배치 후 재고</th>
                  <th className={styles.right}>부족 (전→후)</th>
                  <th className={[styles.right, styles.secondaryCol].join(' ')}>수요</th>
                  <th className={[styles.right, styles.secondaryCol].join(' ')}>외부 공급</th>
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
                      <td className={styles.right}>{formatNumber(s.baselineInventory)}</td>
                      <td className={styles.right}>{formatNumber(s.railInbound)}</td>
                      <td className={styles.right}>{formatNumber(s.railOutbound)}</td>
                      <td className={styles.right}>{formatNumber(s.postRailInventory)}</td>
                      <td className={styles.right}>
                        {s.baselineStockout} → {s.postRailStockout}
                      </td>
                      <td className={[styles.right, styles.secondaryCol].join(' ')}>
                        {formatNumber(s.demand)}
                      </td>
                      <td className={[styles.right, styles.secondaryCol].join(' ')}>
                        {formatNumber(s.externalSupply)}
                      </td>
                      <td>
                        <StatusBadge tone={statusTone(row.status)} small>
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
            재고는 선사별 소유 물량입니다. 다른 선사의 컨테이너로 부족을 대체하지 않으며,
            공컨 전용 열차의 수송 용량만 공동으로 이용합니다.
          </div>
        </div>
      </aside>
    </>
  );
}
