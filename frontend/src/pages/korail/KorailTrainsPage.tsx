import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { TrainDetailDrawer } from './TrainDetailDrawer';
import { fetchKorailTrains } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatDateShort, formatNumber, formatPercent, formatTime } from '@/lib/format';
import styles from './Korail.module.css';

/** 공컨테이너 노선·열차 현황.
 *  ?train=CAND0292 로 진입하면 해당 열차 상세가 바로 열린다
 *  (선사 포털의 Train ID drill-down 진입점). */
export function KorailTrainsPage() {
  const [params, setParams] = useSearchParams();
  const trainId = params.get('train');

  const { data, loading, error, reload } = useAsync(
    (signal) => fetchKorailTrains(signal),
    [],
  );

  const setTrainId = useCallback(
    (next: string | null) => {
      const updated = new URLSearchParams(params);
      if (next) updated.set('train', next);
      else updated.delete('train');
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  return (
    <PageContainer
      title="공컨테이너 노선·열차 현황"
      description="이번 계획주기에 선정된 공컨테이너 전용 화물열차입니다."
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={4} height={26} />
        </Card>
      )}

      {data && data.trains.length === 0 && (
        <Card>
          <EmptyState title="선정된 열차가 없습니다." />
        </Card>
      )}

      {data && data.trains.length > 0 && (
        <Card title={`선정 열차 ${data.trains.length}편`} subtitle="행을 클릭하면 상세가 열립니다">
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>열차</th>
                  <th>노선</th>
                  <th>축</th>
                  <th>출발</th>
                  <th>도착</th>
                  <th className={styles.right}>편성</th>
                  <th className={styles.right}>Capacity</th>
                  <th className={styles.right}>배정</th>
                  <th className={styles.right}>적재율</th>
                  <th className={styles.right}>선사</th>
                  <th className={styles.right}>20FT</th>
                  <th className={styles.right}>40FT</th>
                </tr>
              </thead>
              <tbody>
                {data.trains.map((train) => (
                  <tr
                    key={train.trainId}
                    className={[
                      styles.rowClickable,
                      train.trainId === trainId ? styles.rowActive : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => setTrainId(train.trainId)}
                  >
                    <td className={styles.mono}>{train.trainId}</td>
                    <td className={styles.muted}>{train.route}</td>
                    <td className={styles.muted}>{train.serviceFamily ?? '-'}</td>
                    <td>
                      {formatTime(train.departureTime)}
                      <div className={styles.kpiSub}>{formatDateShort(train.departureTime)}</div>
                    </td>
                    <td>
                      {formatTime(train.arrivalTime)}
                      <div className={styles.kpiSub}>{formatDateShort(train.arrivalTime)}</div>
                    </td>
                    <td className={styles.right}>
                      {train.formation ?? '-'}
                      <div className={styles.kpiSub}>{train.wagons}량</div>
                    </td>
                    <td className={styles.right}>{train.capacityTeu} TEU</td>
                    <td className={styles.right}>{train.assignedTeu} TEU</td>
                    <td className={styles.right}>
                      {formatPercent(train.loadFactor)}
                      <div className={styles.loadBar}>
                        <span
                          className={styles.loadFill}
                          style={{ width: `${Math.min(100, train.loadFactor * 100)}%` }}
                        />
                      </div>
                    </td>
                    <td className={styles.right}>{train.participatingCarrierCount}</td>
                    <td className={styles.right}>{formatNumber(train.boxes20ft)}</td>
                    <td className={styles.right}>{formatNumber(train.boxes40ft)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {trainId && <TrainDetailDrawer trainId={trainId} onClose={() => setTrainId(null)} />}
    </PageContainer>
  );
}
