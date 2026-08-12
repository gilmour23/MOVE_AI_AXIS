import { useMemo, useState } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailNeeds } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatNumber } from '@/lib/format';
import styles from './Korail.module.css';

const STATUS_TONE: Record<string, 'normal' | 'warning' | 'shortage'> = {
  '배정 완료': 'normal',
  '부분 배정': 'warning',
  미배정: 'shortage',
};

/** 철도 서비스 수요·배정 현황.
 *  SERVICE_NEED_RESULT 는 일반 예약 DB 가 아니라 선사별 철도 서비스 필요량 +
 *  배정 여부이므로 화면명을 그에 맞춰 표기한다. */
export function KorailNeedsPage() {
  const [filter, setFilter] = useState<string>('ALL');
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailNeeds(signal), []);

  const carriers = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.rows.map((r) => r.carrierId))).sort();
  }, [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    return filter === 'ALL' ? data.rows : data.rows.filter((r) => r.carrierId === filter);
  }, [data, filter]);

  return (
    <PageContainer
      title="수송 수요·배정 현황"
      description="선사별 철도 서비스 필요량과 배정 결과입니다."
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={6} height={24} />
        </Card>
      )}

      {data && (
        <>
          <div className={styles.kpiStrip}>
            <Kpi label="총 필요량" value={`${formatNumber(data.totals.requiredBoxes)}개`} sub={`${data.totals.requiredTeu} TEU`} />
            <Kpi label="철도 배정" value={`${formatNumber(data.totals.railServedBoxes)}개`} />
            <Kpi label="미배정" value={`${formatNumber(data.totals.railUnservedBoxes)}개`} />
            <Kpi label="Need 건수" value={`${formatNumber(data.totals.needCount)}건`} />
          </div>

          <Card
            title="수요·배정 상세"
            subtitle="거점·규격·요일 단위 집계"
            action={
              <div className={styles.filterRow}>
                <button
                  type="button"
                  className={[styles.filterChip, filter === 'ALL' ? styles.filterActive : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setFilter('ALL')}
                >
                  전체
                </button>
                {carriers.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={[styles.filterChip, filter === c ? styles.filterActive : '']
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => setFilter(c)}
                  >
                    {c.replace('CARRIER_', 'Carrier ')}
                  </button>
                ))}
              </div>
            }
          >
            <div className={styles.scroll}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>선사</th>
                    <th>도착 거점</th>
                    <th>규격</th>
                    <th>요일</th>
                    <th className={styles.right}>필요</th>
                    <th className={styles.right}>배정</th>
                    <th className={styles.right}>미배정</th>
                    <th>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={`${row.carrierId}-${row.hubCode}-${row.size}-${row.date}-${index}`}>
                      <td>{row.carrierLabel}</td>
                      <td>{row.hubName}</td>
                      <td>{row.size}</td>
                      <td>
                        {row.weekday}요일
                        <div className={styles.kpiSub}>{row.date}</div>
                      </td>
                      <td className={styles.right}>{row.requiredBoxes}</td>
                      <td className={styles.right}>{row.railServedBoxes}</td>
                      <td className={styles.right}>{row.railUnservedBoxes}</td>
                      <td>
                        <StatusBadge tone={STATUS_TONE[row.status] ?? 'neutral'} small>
                          {row.status}
                        </StatusBadge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </PageContainer>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={styles.kpi}>
      <span className={styles.kpiLabel}>{label}</span>
      <span className={styles.kpiValue}>{value}</span>
      {sub && <span className={styles.kpiSub}>{sub}</span>}
    </div>
  );
}
