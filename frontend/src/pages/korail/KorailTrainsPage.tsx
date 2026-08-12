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
import { formatDateShort, formatTime } from '@/lib/format';
import { hubShortName } from '@/config/hubMeta';
import { viaHubLabel } from './trainInfo';
import styles from './Korail.module.css';

/** 공컨 전용열차 운행계획.
 *  ?train=CAND0292 로 진입하면 해당 열차 상세가 바로 열린다.
 *  Train Detail 의 진입점은 이 경로 하나로 통일한다. */
export function KorailTrainsPage() {
  const [params, setParams] = useSearchParams();
  const trainId = params.get('train');
  const { meta } = useMeta();

  const { data, loading, error, reload } = useAsync((signal) => fetchKorailTrains(signal), []);

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
    <PageContainer title="공컨 전용열차 운행계획">
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
        <Card title="주간 운행 시간표">
          <WeeklyTimeline
            trains={data.trains}
            horizonStart={meta.horizonStart}
            horizonEnd={meta.horizonEnd}
            onSelect={setTrainId}
          />
        </Card>
      )}

      {data && data.trains.length > 0 && (
        <Card title="열차 운행계획">
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>열차</th>
                  <th>출발지</th>
                  <th>도착지</th>
                  <th>출발</th>
                  <th>도착</th>
                  <th className={styles.right}>편성</th>
                  <th className={styles.right}>운송 공컨</th>
                  <th>경유 거점</th>
                </tr>
              </thead>
              <tbody>
                {data.trains.map((train) => {
                  const via = viaHubLabel(train);
                  return (
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
                      <td>{hubShortName(train.originTerminal ?? '')}</td>
                      <td>{hubShortName(train.destinationTerminal ?? '')}</td>
                      {/* 자정을 넘기는 운행이 있으므로 날짜를 항상 함께 보여준다. */}
                      <td>
                        {formatDateShort(train.departureTime)}
                        <div className={styles.kpiSub}>{formatTime(train.departureTime)}</div>
                      </td>
                      <td>
                        {formatDateShort(train.arrivalTime)}
                        <div className={styles.kpiSub}>{formatTime(train.arrivalTime)}</div>
                      </td>
                      <td className={styles.right}>{train.wagons}량</td>
                      <td className={styles.right}>
                        {train.totalBoxes}개
                        <div className={styles.kpiSub}>{train.assignedTeu} TEU</div>
                      </td>
                      {/* workStops 는 정차 계획이며 상·하차 발생을 뜻하지 않는다. */}
                      <td className={styles.muted}>{via ?? '-'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {trainId && <TrainDetailDrawer trainId={trainId} onClose={() => setTrainId(null)} />}
    </PageContainer>
  );
}
