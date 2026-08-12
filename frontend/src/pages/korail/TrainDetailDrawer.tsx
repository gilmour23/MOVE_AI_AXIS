import { Link } from 'react-router-dom';
import { ArrowRight, X } from 'lucide-react';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { StatusBadge } from '@/components/common/StatusBadge';
import { fetchKorailTrainDetail } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatDateShort, formatNumber, formatPercent, formatTime } from '@/lib/format';
import type { KorailStop } from '@/types/domain';
import styles from './Korail.module.css';

/** 열차 상세 = Train Summary + Stop Timeline + Segment Load + Carrier Allocation.
 *  KORAIL 운영자 화면이므로 전 선사 배정을 노출한다. */
export function TrainDetailDrawer({
  trainId,
  onClose,
}: {
  trainId: string;
  onClose: () => void;
}) {
  const { meta } = useMeta();
  const { data, loading, error, reload } = useAsync(
    (signal) => fetchKorailTrainDetail(trainId, signal),
    [trainId],
  );

  return (
    <>
      <div className={styles.overlay} onClick={onClose} role="presentation" />
      <aside className={styles.drawer} role="dialog" aria-label={`${trainId} 상세`}>
        <header className={styles.drawerHeader}>
          <div>
            <div className={styles.drawerTitle}>{trainId}</div>
            <div className={styles.drawerSub}>{data?.route ?? '열차 상세 운행계획'}</div>
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
                <span className={styles.sectionTitle}>운행 요약</span>
                <div className={styles.card}>
                  <div className={styles.summaryGrid}>
                    <Item label="편성" value={`${data.formation ?? '-'} · ${data.wagons}량`} />
                    <Item label="Capacity" value={`${data.capacityTeu} TEU`} />
                    <Item label="배정" value={`${data.assignedTeu} TEU`} />
                    <Item label="적재율" value={formatPercent(data.loadFactor)} />
                    <Item label="참여 선사" value={`${data.participatingCarrierCount}개`} />
                    <Item label="운행거리" value={`${formatNumber(Math.round(data.trainKm))} km`} />
                    <Item
                      label="출발"
                      value={`${formatDateShort(data.departureTime)} ${formatTime(data.departureTime)}`}
                    />
                    <Item
                      label="도착"
                      value={`${formatDateShort(data.arrivalTime)} ${formatTime(data.arrivalTime)}`}
                    />
                    <Item
                      label="컨테이너"
                      value={`20FT ${data.boxes20ft} · 40FT ${data.boxes40ft}`}
                    />
                  </div>
                  {meta?.isPrototypeTimetable && (
                    <div style={{ marginTop: 10 }}>
                      <StatusBadge tone="neutral" small title={`candidate_source = ${data.candidateSource}`}>
                        프로토타입 운행후보 기준
                      </StatusBadge>
                    </div>
                  )}
                </div>
              </section>

              <section className={styles.section}>
                <span className={styles.sectionTitle}>정차역 작업 타임라인</span>
                <div className={styles.card}>
                  <div className={styles.timeline}>
                    {data.stops.map((stop, index) => (
                      <StopRow
                        key={`${stop.sequence}-${stop.hubCode}`}
                        stop={stop}
                        isLast={index === data.stops.length - 1}
                      />
                    ))}
                  </div>
                </div>
              </section>

              <section className={styles.section}>
                <span className={styles.sectionTitle}>구간별 적재</span>
                <div className={styles.scroll}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>구간</th>
                        <th className={styles.right}>적재/Capacity</th>
                        <th className={styles.right}>적재율</th>
                        <th className={styles.right}>거리</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.segments.map((seg) => (
                        <tr key={seg.sequence}>
                          <td>
                            {seg.fromHubName} → {seg.toHubName}
                          </td>
                          <td className={styles.right}>
                            {seg.loadedTeu} / {seg.capacityTeu} TEU
                            <div className={styles.loadBar}>
                              <span
                                className={[
                                  styles.loadFill,
                                  seg.loadFactor >= 0.8 ? styles.loadFillHigh : '',
                                ]
                                  .filter(Boolean)
                                  .join(' ')}
                                style={{ width: `${Math.min(100, seg.loadFactor * 100)}%` }}
                              />
                            </div>
                          </td>
                          <td className={styles.right}>{formatPercent(seg.loadFactor)}</td>
                          <td className={styles.right}>{seg.physicalDistanceKm.toFixed(1)} km</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className={styles.section}>
                <span className={styles.sectionTitle}>선사별 배정</span>
                <div className={styles.scroll}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>선사</th>
                        <th>구간</th>
                        <th>규격</th>
                        <th className={styles.right}>박스</th>
                        <th className={styles.right}>TEU</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.allocation.map((row, index) => (
                        <tr key={`${row.carrierId}-${row.originHub}-${row.destinationHub}-${row.size}-${index}`}>
                          <td>
                            {row.carrierId === meta?.currentCarrierId ? (
                              <Link className={styles.carrierLink} to="/carrier/plan">
                                {row.carrierLabel} <ArrowRight size={12} />
                              </Link>
                            ) : (
                              row.carrierLabel
                            )}
                          </td>
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
                <div className={styles.note}>
                  선사별 소계 ·{' '}
                  {data.carrierBreakdown
                    .map((c) => `${c.carrierLabel} ${c.teu} TEU`)
                    .join(' / ')}
                  <br />
                  합계 {data.carrierBreakdown.reduce((sum, c) => sum + c.teu, 0)} TEU (배정{' '}
                  {data.assignedTeu} TEU)
                </div>
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

function StopRow({ stop, isLast }: { stop: KorailStop; isLast: boolean }) {
  const hasWork = stop.loadTeu > 0 || stop.unloadTeu > 0;
  return (
    <div className={styles.stop}>
      <div className={styles.stopMarkerCol}>
        <span className={[styles.stopDot, hasWork ? styles.stopDotWork : ''].filter(Boolean).join(' ')} />
        {!isLast && <span className={styles.stopConnector} />}
      </div>
      <div className={styles.stopBody}>
        <div className={styles.stopName}>{stop.hubName}</div>
        <div className={styles.stopTimes}>
          {stop.loadStartTime && `상차 시작 ${formatTime(stop.loadStartTime)} · `}
          도착 {formatTime(stop.arrivalTime)} · 출발 {formatTime(stop.departureTime)}
          {stop.availableTime && ` · 사용 가능 ${formatTime(stop.availableTime)}`}
        </div>
        {hasWork && (
          <div className={styles.stopWork}>
            {stop.loadTeu > 0 && (
              <span className={[styles.workChip, styles.workLoad].join(' ')}>
                상차 {stop.loadTeu} TEU
              </span>
            )}
            {stop.unloadTeu > 0 && (
              <span className={[styles.workChip, styles.workUnload].join(' ')}>
                하차 {stop.unloadTeu} TEU
              </span>
            )}
          </div>
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
