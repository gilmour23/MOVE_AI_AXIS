import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailOperations } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatDateTimeCompact, formatNumber } from '@/lib/format';
import type { KorailStationHub, KorailStationOperation } from '@/types/domain';
import styles from './Korail.module.css';

/** 거점 작업 계획 — STOP_WORK_PLAN 기준.
 *  새로운 작업량을 임의로 생성하지 않고 결과 파일 값만 집계한다.
 *
 *  시간 필드는 각각 독립된 계획시각이다. STOP_WORK_PLAN 에는
 *  loadStartTime < arrivalTime 인 stop 이 존재하므로
 *  "도착 후 작업 시작" 같은 인과관계를 UI 에서 새로 정의하지 않는다.
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
    return new Set(hub.operations.map((op) => op.stopType).filter(Boolean)).size > 1;
  }, [hub]);

  const selected = useMemo(
    () => hub?.operations.find((op) => opKey(op) === selectedOp) ?? null,
    [hub, selectedOp],
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
          <Card
            title="거점별 계획 취급량"
            subtitle="상차 + 하차 TEU 기준 · 막대를 클릭하면 해당 거점 일정이 열립니다"
          >
            <HandlingChart
              hubs={data.hubs}
              selectedHub={hubCode}
              onSelect={(code) => {
                setHubCode(code);
                setSelectedOp(null);
              }}
            />
          </Card>

          {hub && (
            <>
              <div className={styles.kpiStrip}>
                <Kpi label="작업 횟수" value={`${hub.operationCount}회`} />
                <Kpi
                  label="총 상차"
                  value={`${formatNumber(hub.totalLoadBoxes)}개`}
                  sub={`${formatNumber(hub.totalLoadTeu)} TEU`}
                />
                <Kpi
                  label="총 하차"
                  value={`${formatNumber(hub.totalUnloadBoxes)}개`}
                  sub={`${formatNumber(hub.totalUnloadTeu)} TEU`}
                />
                <Kpi
                  label="총 취급량"
                  value={`${formatNumber(hub.totalLoadBoxes + hub.totalUnloadBoxes)}개`}
                  sub={`${formatNumber(hub.totalHandlingTeu)} TEU`}
                />
              </div>

              <Card
                title={`${hub.hubName} 작업 일정`}
                subtitle="각 시각은 독립된 계획시각입니다 · 행을 클릭하면 상세가 열립니다"
              >
                {hub.operations.length === 0 ? (
                  <EmptyState
                    title="이 거점에는 예정된 작업이 없습니다."
                    description="선정된 열차의 정차 계획에 포함되지 않았습니다."
                  />
                ) : (
                  <>
                    <div className={styles.scroll}>
                      <table className={styles.table}>
                        <thead>
                          <tr>
                            <th>열차</th>
                            {showStopType && <th>구분</th>}
                            <th>작업 개시</th>
                            <th>열차 도착</th>
                            <th>열차 출발</th>
                            <th className={styles.right}>상차</th>
                            <th className={styles.right}>하차</th>
                            <th>사용 가능</th>
                          </tr>
                        </thead>
                        <tbody>
                          {hub.operations.map((op) => (
                            <tr
                              key={opKey(op)}
                              className={[
                                styles.rowClickable,
                                opKey(op) === selectedOp ? styles.rowActive : '',
                              ]
                                .filter(Boolean)
                                .join(' ')}
                              onClick={() =>
                                setSelectedOp(opKey(op) === selectedOp ? null : opKey(op))
                              }
                            >
                              <td className={styles.mono}>{op.trainId}</td>
                              {showStopType && (
                                <td className={styles.muted}>{op.stopType ?? '-'}</td>
                              )}
                              <td>{formatDateTimeCompact(op.loadStartTime)}</td>
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
                              <td>{formatDateTimeCompact(op.availableTime)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {selected && <OperationDetail op={selected} />}
                  </>
                )}
              </Card>
            </>
          )}
        </>
      )}
    </PageContainer>
  );
}

function opKey(op: KorailStationOperation): string {
  return `${op.trainId}-${op.sequence}`;
}

/** 거점별 계획 취급량 비교.
 *  실제 CY 작업 capacity 데이터가 없으므로 과부하·처리한계로 판단하지 않는다. */
function HandlingChart({
  hubs,
  selectedHub,
  onSelect,
}: {
  hubs: KorailStationHub[];
  selectedHub: string | null;
  onSelect: (hubCode: string) => void;
}) {
  const max = Math.max(1, ...hubs.map((h) => h.totalHandlingTeu));

  return (
    <div className={styles.handlingChart}>
      {hubs.map((hub) => (
        <button
          key={hub.hubCode}
          type="button"
          aria-pressed={hub.hubCode === selectedHub}
          className={[
            styles.handlingRow,
            hub.hubCode === selectedHub ? styles.handlingRowActive : '',
          ]
            .filter(Boolean)
            .join(' ')}
          onClick={() => onSelect(hub.hubCode)}
        >
          <span className={styles.handlingName}>{hub.shortName}</span>
          <span className={styles.handlingTrack}>
            <span
              className={styles.handlingFill}
              style={{ width: `${(hub.totalHandlingTeu / max) * 100}%` }}
            />
          </span>
          <span className={styles.handlingValue}>
            {formatNumber(hub.totalHandlingTeu)} TEU
          </span>
        </button>
      ))}
    </div>
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

/** 선택한 train-stop 상세. 모든 row 에 반복하지 않고 하나만 표시한다. */
function OperationDetail({ op }: { op: KorailStationOperation }) {
  return (
    <div className={styles.opDetail}>
      <div className={styles.opDetailHead}>
        <span className={styles.mono}>{op.trainId}</span>
        <span className={styles.muted}>{op.hubName} 작업 상세</span>
      </div>
      <div className={styles.opDetailGrid}>
        <DetailItem label="작업 개시" value={formatDateTimeCompact(op.loadStartTime)} />
        <DetailItem label="열차 도착" value={formatDateTimeCompact(op.arrivalTime)} />
        <DetailItem label="열차 출발" value={formatDateTimeCompact(op.departureTime)} />
        <DetailItem label="사용 가능" value={formatDateTimeCompact(op.availableTime)} />
      </div>
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

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={styles.kpi}>
      <span className={styles.kpiLabel}>{label}</span>
      <span className={styles.kpiValue}>{value}</span>
      {sub && <span className={styles.kpiSub}>{sub}</span>}
    </div>
  );
}
