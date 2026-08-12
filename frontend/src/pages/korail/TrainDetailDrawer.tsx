import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailTrainDetail } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatDateTime, formatDateTimeCompact } from '@/lib/format';
import { hubShortName } from '@/config/hubMeta';
import type { KorailStop } from '@/types/domain';
import styles from './Korail.module.css';

/** 열차 상세 = 운행정보 → 정차·작업계획 → 선사별 운송물량.
 *
 *  KORAIL 운영자 화면이므로 전 선사 배정을 노출하되,
 *  선사명에서 Carrier Portal 로 넘어가는 링크는 만들지 않는다. */
export function TrainDetailDrawer({
  trainId,
  onClose,
}: {
  trainId: string;
  onClose: () => void;
}) {
  const { data, loading, error, reload } = useAsync(
    (signal) => fetchKorailTrainDetail(trainId, signal),
    [trainId],
  );

  const od = data
    ? `${hubShortName(data.originTerminal ?? '')} → ${hubShortName(data.destinationTerminal ?? '')}`
    : '';

  return (
    <>
      <div className={styles.overlay} onClick={onClose} role="presentation" />
      <aside className={styles.drawer} role="dialog" aria-label={`${trainId} 상세`}>
        <header className={styles.drawerHeader}>
          <div>
            <div className={styles.drawerTitle}>{trainId}</div>
            <div className={styles.drawerSub}>{od}</div>
          </div>
          <button type="button" className={styles.drawerClose} onClick={onClose} aria-label="닫기">
            <X size={17} />
          </button>
        </header>

        <div className={styles.drawerBody}>
          {loading && <LoadingSkeleton rows={6} height={26} />}
          {error && <ErrorState error={error} onRetry={reload} />}

          {data && (
            <>
              <section className={styles.section}>
                <span className={styles.sectionTitle}>운행정보</span>
                <div className={styles.card}>
                  <div className={styles.summaryGrid}>
                    <Item label="출발" value={formatDateTime(data.departureTime)} />
                    <Item label="도착" value={formatDateTime(data.arrivalTime)} />
                    <Item label="편성" value={`${data.wagons}량`} />
                    <Item
                      label="운송"
                      value={`${data.totalBoxes}개 / ${data.assignedTeu} TEU`}
                    />
                  </div>
                </div>
              </section>

              <section className={styles.section}>
                <span className={styles.sectionTitle}>정차·작업계획</span>
                <div className={styles.card}>
                  <div className={styles.timeline}>
                    {data.stops.map((stop, index) => (
                      <StopRow
                        key={`${stop.sequence}-${stop.hubCode}`}
                        stop={stop}
                        index={index}
                        isLast={index === data.stops.length - 1}
                      />
                    ))}
                  </div>
                </div>
              </section>

              <section className={styles.section}>
                <span className={styles.sectionTitle}>선사별 운송물량</span>
                <div className={styles.scroll}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>선사</th>
                        <th>운송구간</th>
                        <th>규격</th>
                        <th className={styles.right}>Box</th>
                        <th className={styles.right}>TEU</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.allocation.map((row, index) => (
                        <tr key={`${row.carrierId}-${row.originHub}-${row.destinationHub}-${row.size}-${index}`}>
                          {/* KORAIL 화면에서는 선사명을 일반 텍스트로만 표시한다. */}
                          <td>{row.carrierLabel}</td>
                          <td className={styles.muted}>
                            {row.originName} → {row.destinationName}
                          </td>
                          <td>{row.size}</td>
                          <td className={styles.right}>{row.boxes}</td>
                          <td className={styles.right}>{row.teu}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

/** 정차역 한 곳의 계획시각과 작업량.
 *
 *  각 시각은 독립된 계획값이다. 데이터에는 loadStartTime < arrivalTime 인
 *  stop 이 존재하므로 "도착 → 작업 → 출발" 같은 인과 서술을 하지 않는다.
 *
 *  상·하차가 0인 정차도 그대로 남기되, 작업 개시·사용 가능 시각을
 *  실제 컨테이너 작업처럼 오해시키지 않도록 조건부로만 보여준다. */
function StopRow({ stop, index, isLast }: { stop: KorailStop; index: number; isLast: boolean }) {
  const hasHandling = stop.loadBoxesTotal + stop.unloadBoxesTotal > 0;
  const hasUnload = stop.unloadBoxesTotal > 0;

  return (
    <div className={styles.stop}>
      <div className={styles.stopMarkerCol}>
        <span
          className={[styles.stopDot, hasHandling ? styles.stopDotWork : '']
            .filter(Boolean)
            .join(' ')}
        />
        {!isLast && <span className={styles.stopConnector} />}
      </div>
      <div className={styles.stopBody}>
        <div className={styles.stopName}>
          <span className={styles.stopIndex}>{index + 1}</span>
          {/* 이 거점의 전체 작업 일정으로 이동 */}
          <Link className={styles.stopLink} to={`/korail/operations?hub=${stop.hubCode}`}>
            {stop.hubName}
          </Link>
        </div>
        <div className={styles.stopTimes}>
          <span>작업 개시 {hasHandling ? formatDateTimeCompact(stop.loadStartTime) : '-'}</span>
          <span>열차 도착 {formatDateTimeCompact(stop.arrivalTime)}</span>
          <span>열차 출발 {formatDateTimeCompact(stop.departureTime)}</span>
          <span>사용 가능 {hasUnload ? formatDateTimeCompact(stop.availableTime) : '-'}</span>
        </div>
        {hasHandling ? (
          <div className={styles.stopWork}>
            {stop.loadBoxesTotal > 0 && (
              <span className={[styles.workChip, styles.workLoad].join(' ')}>
                <strong>상차 {stop.loadBoxesTotal}개</strong>
                <span>
                  20FT {stop.loadBoxes20ft} · 40FT {stop.loadBoxes40ft} · {stop.loadTeu} TEU
                </span>
              </span>
            )}
            {stop.unloadBoxesTotal > 0 && (
              <span className={[styles.workChip, styles.workUnload].join(' ')}>
                <strong>하차 {stop.unloadBoxesTotal}개</strong>
                <span>
                  20FT {stop.unloadBoxes20ft} · 40FT {stop.unloadBoxes40ft} ·{' '}
                  {stop.unloadTeu} TEU
                </span>
              </span>
            )}
          </div>
        ) : (
          <div className={styles.stopNoWork}>상하차 없음</div>
        )}
      </div>
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.summaryItem}>
      <span className={styles.summaryLabel}>{label}</span>
      <span className={styles.summaryValue}>{value}</span>
    </div>
  );
}
