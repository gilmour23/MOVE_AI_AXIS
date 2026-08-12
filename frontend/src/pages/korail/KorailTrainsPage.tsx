import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { TrainDetailDrawer } from './TrainDetailDrawer';
import { WeeklyTimeline } from './WeeklyTimeline';
import { fetchKorailTrains } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatDateShort, formatPercent, formatTime } from '@/lib/format';
import { formatRoute } from '@/config/hubMeta';
import styles from './Korail.module.css';

/** 공컨테이너 운행계획.
 *  ?train=CAND0292 로 진입하면 해당 열차 상세가 바로 열린다
 *  (선사 포털의 Train ID drill-down 진입점). */
export function KorailTrainsPage() {
  const [params, setParams] = useSearchParams();
  const trainId = params.get('train');
  const { meta } = useMeta();

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
      title="공컨테이너 운행계획"
      description="이번 계획주기에 선정된 공컨 전용 화물열차의 운행 및 배정 계획입니다."
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

      {data && data.trains.length > 0 && meta?.horizonStart && meta?.horizonEnd && (
        <Card
          title="주간 계획 타임라인"
          subtitle="계획주기 위의 출발~도착 구간입니다 · 중간 정차는 열차 상세에서 확인합니다"
        >
          <WeeklyTimeline
            trains={data.trains}
            horizonStart={meta.horizonStart}
            horizonEnd={meta.horizonEnd}
          />
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
                  <th>출발</th>
                  <th>도착</th>
                  <th className={styles.right}>편성</th>
                  <th className={styles.right}>배정 / 용량</th>
                  <th className={styles.right}>적재율</th>
                  <th className={styles.right}>참여 선사</th>
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
                    <td className={styles.muted}>{formatRoute(train.route)}</td>
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
                    <td className={styles.right}>
                      {train.assignedTeu} / {train.capacityTeu} TEU
                    </td>
                    <td className={styles.right}>
                      {formatPercent(train.loadFactor)}
                      <div className={styles.loadBar}>
                        <span
                          className={styles.loadFill}
                          style={{ width: `${Math.min(100, train.loadFactor * 100)}%` }}
                        />
                      </div>
                    </td>
                    <td className={styles.right}>{train.participatingCarrierCount}개</td>
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
