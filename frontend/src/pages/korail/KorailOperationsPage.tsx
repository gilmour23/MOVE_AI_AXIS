import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailOperations } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatDateShort, formatTime } from '@/lib/format';
import styles from './Korail.module.css';

/** 거점 작업 계획 — STOP_WORK_PLAN 기준.
 *  새로운 작업량을 임의로 생성하지 않고 결과 파일 값만 집계한다.
 *
 *  ?hub=BUSAN 으로 진입하면 해당 거점이 선택된 상태로 열린다
 *  (Train Detail 정차역에서의 drill-down 진입점). */
export function KorailOperationsPage() {
  const [params] = useSearchParams();
  const requestedHub = params.get('hub');
  const [hubCode, setHubCode] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync(
    (signal) => fetchKorailOperations(signal),
    [],
  );

  useEffect(() => {
    if (!data?.hubs.length) return;
    // query 로 지정된 거점이 실제로 존재할 때만 반영한다.
    const fromQuery = requestedHub
      ? data.hubs.find((h) => h.hubCode === requestedHub)
      : undefined;
    if (fromQuery) {
      setHubCode(fromQuery.hubCode);
      return;
    }
    if (!hubCode) {
      const withWork = data.hubs.find((h) => h.operationCount > 0) ?? data.hubs[0];
      setHubCode(withWork.hubCode);
    }
  }, [data, requestedHub, hubCode]);

  const hub = useMemo(
    () => data?.hubs.find((h) => h.hubCode === hubCode) ?? null,
    [data, hubCode],
  );

  /** 현재 데이터의 stopType 이 한 종류뿐이면 `구분` 컬럼은 정보 가치가 없다.
   *  타입/데이터는 그대로 두고 표시 여부만 조건부로 처리한다. */
  const showStopType = useMemo(() => {
    if (!hub) return false;
    const kinds = new Set(hub.operations.map((op) => op.stopType).filter(Boolean));
    return kinds.size > 1;
  }, [hub]);

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

              <Card
                title={`${hub.hubName} 작업 일정`}
                subtitle="열차 도착부터 사용 가능 시각까지의 흐름입니다"
              >
                {hub.operations.length === 0 ? (
                  <EmptyState
                    title="이 거점에는 예정된 작업이 없습니다."
                    description="선정된 열차의 정차 계획에 포함되지 않았습니다."
                  />
                ) : (
                  <div className={styles.scroll}>
                    <table className={styles.table}>
                      <thead>
                        {/* 시간 흐름 순서: 도착 → 상차 시작 → 출발 → 사용 가능 */}
                        <tr>
                          <th>열차</th>
                          {showStopType && <th>구분</th>}
                          <th>도착</th>
                          <th>상차 시작</th>
                          <th>출발</th>
                          <th className={styles.right}>상차</th>
                          <th className={styles.right}>하차</th>
                          <th>사용 가능</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hub.operations.map((op, index) => (
                          <tr key={`${op.trainId}-${op.sequence}-${index}`}>
                            <td className={styles.mono}>{op.trainId}</td>
                            {showStopType && (
                              <td className={styles.muted}>{op.stopType ?? '-'}</td>
                            )}
                            <td>
                              {formatTime(op.arrivalTime)}
                              <div className={styles.kpiSub}>
                                {formatDateShort(op.arrivalTime ?? '')}
                              </div>
                            </td>
                            <td>{formatTime(op.loadStartTime)}</td>
                            <td>{formatTime(op.departureTime)}</td>
                            <td className={styles.right}>{op.loadTeu}</td>
                            <td className={styles.right}>{op.unloadTeu}</td>
                            <td>{formatTime(op.availableTime)}</td>
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
