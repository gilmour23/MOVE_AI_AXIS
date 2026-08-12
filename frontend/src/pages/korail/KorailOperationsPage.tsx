import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailOperations } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatDateTimeCompact } from '@/lib/format';
import type { KorailStationHub, KorailStationOperation } from '@/types/domain';
import styles from './Korail.module.css';

function opKey(op: KorailStationOperation): string {
  return `${op.trainId}-${op.sequence}`;
}

function trainCount(hub: KorailStationHub): number {
  return new Set(hub.operations.map((op) => op.trainId)).size;
}

/** 거점별 열차 작업계획 — STOP_WORK_PLAN 기준.
 *
 *  각 시각은 독립된 계획값이다. 상·하차가 0인 정차도 KORAIL 에게는
 *  의미가 있으므로 남기되, 작업 개시·사용 가능 시각은 실제 작업이
 *  있는 경우에만 표시한다.
 *
 *  ?hub=BUSAN 으로 진입하면 해당 거점이 선택된 상태로 열린다. */
export function KorailOperationsPage() {
  const [params] = useSearchParams();
  const requestedHub = params.get('hub');
  const [hubCode, setHubCode] = useState<string | null>(null);
  const [selectedOp, setSelectedOp] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync(
    (signal) => fetchKorailOperations(signal),
    [],
  );

  useEffect(() => {
    if (!data?.hubs.length) return;
    const fromQuery = requestedHub
      ? data.hubs.find((h) => h.hubCode === requestedHub)
      : undefined;
    if (fromQuery) {
      setHubCode(fromQuery.hubCode);
      setSelectedOp(null);
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

  // 첫 작업을 기본 선택해 우측 상세가 비어 보이지 않게 한다.
  useEffect(() => {
    if (hub && hub.operations.length > 0 && !selectedOp) {
      setSelectedOp(opKey(hub.operations[0]));
    }
  }, [hub, selectedOp]);

  const selected = useMemo(
    () => hub?.operations.find((op) => opKey(op) === selectedOp) ?? null,
    [hub, selectedOp],
  );

  return (
    <PageContainer title="거점별 열차 작업계획">
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={5} height={24} />
        </Card>
      )}

      {data && (
        <>
          <div className={styles.hubBar}>
            {data.hubs.map((h) => (
              <button
                key={h.hubCode}
                type="button"
                aria-pressed={h.hubCode === hubCode}
                className={[styles.hubChip, h.hubCode === hubCode ? styles.hubChipActive : '']
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => {
                  setHubCode(h.hubCode);
                  setSelectedOp(null);
                }}
              >
                <span className={styles.hubChipName}>{h.shortName}</span>
                <span className={styles.hubChipCount}>{trainCount(h)}편</span>
              </button>
            ))}
          </div>

          {hub && (
            <div className={styles.opsLayout}>
              <Card title={`${hub.hubName} 작업 일정`}>
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
                          <th>작업 개시</th>
                          <th>열차 도착</th>
                          <th>열차 출발</th>
                          <th className={styles.right}>상차</th>
                          <th className={styles.right}>하차</th>
                          <th>사용 가능</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hub.operations.map((op) => {
                          const hasHandling = op.loadBoxesTotal + op.unloadBoxesTotal > 0;
                          return (
                            <tr
                              key={opKey(op)}
                              className={[
                                styles.rowClickable,
                                opKey(op) === selectedOp ? styles.rowActive : '',
                              ]
                                .filter(Boolean)
                                .join(' ')}
                              onClick={() => setSelectedOp(opKey(op))}
                            >
                              <td className={styles.mono}>{op.trainId}</td>
                              <td>
                                {hasHandling ? formatDateTimeCompact(op.loadStartTime) : '-'}
                              </td>
                              <td>{formatDateTimeCompact(op.arrivalTime)}</td>
                              <td>{formatDateTimeCompact(op.departureTime)}</td>
                              <td className={styles.right}>
                                <BoxCell
                                  boxes={op.loadBoxesTotal}
                                  teu={op.loadTeu}
                                  b20={op.loadBoxes20ft}
                                  b40={op.loadBoxes40ft}
                                />
                              </td>
                              <td className={styles.right}>
                                <BoxCell
                                  boxes={op.unloadBoxesTotal}
                                  teu={op.unloadTeu}
                                  b20={op.unloadBoxes20ft}
                                  b40={op.unloadBoxes40ft}
                                />
                              </td>
                              <td>
                                {op.unloadBoxesTotal > 0
                                  ? formatDateTimeCompact(op.availableTime)
                                  : '-'}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card title="선택 작업 상세">
                {selected ? (
                  <OperationDetail op={selected} hubName={hub.hubName} />
                ) : (
                  <EmptyState title="작업을 선택하세요." />
                )}
              </Card>
            </div>
          )}
        </>
      )}
    </PageContainer>
  );
}

/** 표 안에서는 총량을 앞세우고 규격별 내역을 보조로 둔다. */
function BoxCell({
  boxes,
  teu,
  b20,
  b40,
}: {
  boxes: number;
  teu: number;
  b20: number;
  b40: number;
}) {
  if (boxes === 0) return <span className={styles.muted}>-</span>;
  return (
    <>
      {boxes}개
      <div className={styles.kpiSub}>
        20FT {b20} · 40FT {b40} · {teu} TEU
      </div>
    </>
  );
}

function OperationDetail({ op, hubName }: { op: KorailStationOperation; hubName: string }) {
  const hasHandling = op.loadBoxesTotal + op.unloadBoxesTotal > 0;

  return (
    <div className={styles.opDetail}>
      <div className={styles.opDetailHead}>
        <span className={styles.mono}>{op.trainId}</span>
        <span className={styles.muted}>{hubName}</span>
      </div>

      <div className={styles.opDetailGrid}>
        <DetailItem
          label="작업 개시"
          value={hasHandling ? formatDateTimeCompact(op.loadStartTime) : '-'}
        />
        <DetailItem label="열차 도착" value={formatDateTimeCompact(op.arrivalTime)} />
        <DetailItem label="열차 출발" value={formatDateTimeCompact(op.departureTime)} />
        <DetailItem
          label="사용 가능"
          value={op.unloadBoxesTotal > 0 ? formatDateTimeCompact(op.availableTime) : '-'}
        />
      </div>

      {hasHandling ? (
        <div className={styles.opDetailWork}>
          <WorkBlock
            label="상차"
            b20={op.loadBoxes20ft}
            b40={op.loadBoxes40ft}
            total={op.loadBoxesTotal}
            teu={op.loadTeu}
          />
          <WorkBlock
            label="하차"
            b20={op.unloadBoxes20ft}
            b40={op.unloadBoxes40ft}
            total={op.unloadBoxesTotal}
            teu={op.unloadTeu}
          />
        </div>
      ) : (
        <div className={styles.stopNoWork}>상하차 없음 · 정차 계획만 있습니다</div>
      )}
    </div>
  );
}

function WorkBlock({
  label,
  b20,
  b40,
  total,
  teu,
}: {
  label: string;
  b20: number;
  b40: number;
  total: number;
  teu: number;
}) {
  return (
    <div className={styles.workBlock}>
      <span className={styles.summaryLabel}>{label}</span>
      <span className={styles.summaryValue}>
        20FT {b20}개 · 40FT {b40}개
      </span>
      <span className={styles.kpiSub}>
        총 {total}개 / {teu} TEU
      </span>
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.summaryItem}>
      <span className={styles.summaryLabel}>{label}</span>
      <span className={styles.summaryValue}>{value}</span>
    </div>
  );
}
