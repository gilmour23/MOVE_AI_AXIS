import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { WeeklyTimeline } from './WeeklyTimeline';
import { fetchKorailOperations, fetchKorailTrains } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatDateTimeCompact, formatNumber } from '@/lib/format';
import type { KorailStationHub, KorailStationOperation } from '@/types/domain';
import styles from './Korail.module.css';

/** 거점의 첫 계획시각.
 *
 *  상·하차가 있는 stop 은 작업 준비/개시시각을 먼저 보여주고,
 *  상·하차가 0인 정차는 loadStartTime 때문에 실제 작업처럼 오해되지 않도록
 *  도착시각을 쓴다. 없는 시각을 만들어내지 않는다. */
function planTime(op: KorailStationOperation): string | null {
  const hasHandling = op.loadBoxesTotal + op.unloadBoxesTotal > 0;
  if (hasHandling && op.loadStartTime) return op.loadStartTime;
  return op.arrivalTime ?? op.departureTime;
}

function firstPlanTime(hub: KorailStationHub): string | null {
  const times = hub.operations.map(planTime).filter((t): t is string => Boolean(t));
  if (times.length === 0) return null;
  return times.reduce((min, t) => (t < min ? t : min));
}

/** 공컨 전용열차 종합계획.
 *  이번 계획에서 어떤 열차가 언제 어디를 운행하고,
 *  각 거점에 어떤 열차 작업이 예정되어 있는지만 보여준다. */
export function KorailOverviewPage() {
  const { weekMeta, weekId } = useMeta();
  const navigate = useNavigate();
  const trains = useAsync((signal) => fetchKorailTrains(weekId, signal), [weekId]);
  const operations = useAsync((signal) => fetchKorailOperations(weekId, signal), [weekId]);

  const summary = useMemo(() => {
    const rows = trains.data?.trains ?? [];
    return {
      count: rows.length,
      boxes: rows.reduce((sum, t) => sum + t.totalBoxes, 0),
      teu: rows.reduce((sum, t) => sum + t.assignedTeu, 0),
      wagons: rows.reduce((sum, t) => sum + t.wagons, 0),
    };
  }, [trains.data]);

  /** canonical 6 거점을 항상 유지한다.
   *  이번 주 작업이 없는 거점을 목록에서 빼면 거점 자체가 없어진 것처럼 보인다.
   *  (W02 는 경부축만 운행해 동산·신광양항에 작업이 없다 — 정상 상태다) */
  const hubs = operations.data?.hubs ?? [];

  const error = trains.error ?? operations.error;
  const loading = trains.loading || operations.loading;
  const openTrain = (trainId: string) =>
    navigate(`/korail/trains?week=${weekId}&train=${trainId}`);

  return (
    <PageContainer title="공컨 전용열차 종합계획">
      {error && (
        <ErrorState
          error={error}
          onRetry={() => {
            trains.reload();
            operations.reload();
          }}
        />
      )}
      {loading && (
        <Card>
          <LoadingSkeleton rows={5} height={26} />
        </Card>
      )}

      {trains.data && (
        <p className={styles.planSummary}>
          운행 <strong>{summary.count}</strong>편 · 공컨{' '}
          <strong>{formatNumber(summary.boxes)}</strong>개 /{' '}
          <strong>{formatNumber(summary.teu)}</strong> TEU · 총{' '}
          <strong>{formatNumber(summary.wagons)}</strong>량 편성
        </p>
      )}

      {trains.data && weekMeta?.horizonStart && weekMeta?.horizonEnd && (
        <Card title="주간 운행 스케줄">
          <WeeklyTimeline
            trains={trains.data.trains}
            horizonStart={weekMeta.horizonStart}
            horizonEnd={weekMeta.horizonEnd}
            showCargo
            onSelect={openTrain}
          />
        </Card>
      )}

      {operations.data && (
        <Card title="거점별 열차 일정">
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>거점</th>
                  <th>예정 열차</th>
                  <th>첫 계획</th>
                  <th className={styles.right}>상차</th>
                  <th className={styles.right}>하차</th>
                </tr>
              </thead>
              <tbody>
                {hubs.map((hub) => {
                  const trainIds = [...new Set(hub.operations.map((op) => op.trainId))];
                  const idle = hub.operations.length === 0;

                  if (idle) {
                    return (
                      <tr key={hub.hubCode} className={styles.rowIdle}>
                        <td>{hub.hubName}</td>
                        <td colSpan={4} className={styles.idleNote}>
                          이번 계획주차에 예정된 작업이 없습니다
                        </td>
                      </tr>
                    );
                  }

                  return (
                    <tr
                      key={hub.hubCode}
                      className={styles.rowClickable}
                      onClick={() =>
                        navigate(`/korail/operations?week=${weekId}&hub=${hub.hubCode}`)
                      }
                    >
                      <td>{hub.hubName}</td>
                      <td className={styles.mono}>{trainIds.join(' · ')}</td>
                      <td>{formatDateTimeCompact(firstPlanTime(hub))}</td>
                      <td className={styles.right}>
                        {hub.totalLoadBoxes > 0 ? `${hub.totalLoadBoxes}개` : '-'}
                      </td>
                      <td className={styles.right}>
                        {hub.totalUnloadBoxes > 0 ? `${hub.totalUnloadBoxes}개` : '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </PageContainer>
  );
}
