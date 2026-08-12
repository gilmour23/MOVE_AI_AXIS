import { useEffect, useMemo, useState } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailOperations } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatDateShort, formatTime } from '@/lib/format';
import styles from './Korail.module.css';

/** 거점 작업 계획 — STOP_WORK_PLAN 기준.
 *  새로운 작업량을 임의로 생성하지 않고 결과 파일 값만 집계한다. */
export function KorailOperationsPage() {
  const [hubCode, setHubCode] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync(
    (signal) => fetchKorailOperations(signal),
    [],
  );

  useEffect(() => {
    if (!hubCode && data?.hubs.length) {
      const withWork = data.hubs.find((h) => h.operationCount > 0) ?? data.hubs[0];
      setHubCode(withWork.hubCode);
    }
  }, [hubCode, data]);

  const hub = useMemo(
    () => data?.hubs.find((h) => h.hubCode === hubCode) ?? null,
    [data, hubCode],
  );

  return (
    <PageContainer
      title="거점 작업 계획"
      description="선정 열차의 역별 상·하차 작업 일정입니다."
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={5} height={24} />
        </Card>
      )}

      {data && (
        <>
          <Card>
            <div className={styles.filterRow}>
              {data.hubs.map((h) => (
                <button
                  key={h.hubCode}
                  type="button"
                  aria-pressed={h.hubCode === hubCode}
                  className={[styles.filterChip, h.hubCode === hubCode ? styles.filterActive : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setHubCode(h.hubCode)}
                >
                  {h.shortName}
                  {h.operationCount > 0 ? ` · ${h.operationCount}` : ''}
                </button>
              ))}
            </div>
          </Card>

          {hub && (
            <>
              <div className={styles.kpiStrip}>
                <Kpi label="작업 횟수" value={`${hub.operationCount}회`} />
                <Kpi label="총 상차" value={`${hub.totalLoadTeu} TEU`} />
                <Kpi label="총 하차" value={`${hub.totalUnloadTeu} TEU`} />
                <Kpi
                  label="총 취급량"
                  value={`${hub.totalLoadTeu + hub.totalUnloadTeu} TEU`}
                />
              </div>

              <Card title={`${hub.hubName} 작업 일정`} subtitle="열차별 도착·상차·출발·사용 가능 시각">
                {hub.operations.length === 0 ? (
                  <EmptyState
                    title="이 거점에는 예정된 작업이 없습니다."
                    description="선정된 열차의 정차 계획에 포함되지 않았습니다."
                  />
                ) : (
                  <div className={styles.scroll}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>열차</th>
                          <th>구분</th>
                          <th>상차 시작</th>
                          <th>도착</th>
                          <th>출발</th>
                          <th>사용 가능</th>
                          <th className={styles.right}>상차</th>
                          <th className={styles.right}>하차</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hub.operations.map((op, index) => (
                          <tr key={`${op.trainId}-${op.sequence}-${index}`}>
                            <td className={styles.mono}>{op.trainId}</td>
                            <td className={styles.muted}>{op.stopType ?? '-'}</td>
                            <td>{formatTime(op.loadStartTime)}</td>
                            <td>
                              {formatTime(op.arrivalTime)}
                              <div className={styles.kpiSub}>
                                {formatDateShort(op.arrivalTime ?? '')}
                              </div>
                            </td>
                            <td>{formatTime(op.departureTime)}</td>
                            <td>{formatTime(op.availableTime)}</td>
                            <td className={styles.right}>{op.loadTeu}</td>
                            <td className={styles.right}>{op.unloadTeu}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </>
          )}
        </>
      )}
    </PageContainer>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.kpi}>
      <span className={styles.kpiLabel}>{label}</span>
      <span className={styles.kpiValue}>{value}</span>
    </div>
  );
}
