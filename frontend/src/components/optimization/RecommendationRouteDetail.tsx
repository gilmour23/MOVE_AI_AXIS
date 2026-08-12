import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { StatusBadge } from '@/components/common/StatusBadge';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchRecommendationDetail } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import {
  formatDateShort,
  formatKrw,
  formatNumber,
  formatPercent,
  formatTime,
} from '@/lib/format';
import type { CarrierRecommendation, RecommendationStop } from '@/types/domain';
import styles from './RecommendationRouteDetail.module.css';

interface RecommendationRouteDetailProps {
  carrierId: string;
  recommendation: CarrierRecommendation;
}

/** 자사 관점 운송 경로 상세 (핸드오프 §17.3).
 *  정차역별 상/하차량은 자사 recommendation 만 집계한 값이며,
 *  STOP_WORK_PLAN 의 열차 전체 load_teu/unload_teu 는 사용하지 않는다. */
export function RecommendationRouteDetail({
  carrierId,
  recommendation,
}: RecommendationRouteDetailProps) {
  const { data, loading, error, reload } = useAsync(
    (signal) =>
      fetchRecommendationDetail(carrierId, recommendation.recommendationId, signal),
    [carrierId, recommendation.recommendationId],
  );

  if (loading) {
    return (
      <div className={styles.wrap}>
        <LoadingSkeleton rows={3} height={26} />
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.wrap}>
        <ErrorState error={error} onRetry={reload} />
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <span className={styles.trainId}>{data.trainId}</span>
        {data.route && <span className={styles.routeText}>{data.route}</span>}
        {data.candidateSource === 'PROTOTYPE_SYNTHETIC' && (
          <StatusBadge
            tone="neutral"
            small
            title="candidate_timetable_source = PROTOTYPE_SYNTHETIC"
          >
            프로토타입 운행후보 기준
          </StatusBadge>
        )}
      </div>

      <div className={styles.stops}>
        {data.stops.map((stop, index) => (
          <StopItem
            key={`${stop.sequence}-${stop.hubCode}`}
            stop={stop}
            isFirst={index === 0}
            isLast={index === data.stops.length - 1}
          />
        ))}
      </div>

      <div className={styles.metaGrid}>
        <MetaItem
          label="사용 가능 시각"
          value={`${formatDateShort(recommendation.availableTime)} ${formatTime(
            recommendation.availableTime,
          )}`}
        />
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>열차 ID</span>
          <Link className={styles.trainLink} to={`/korail/trains?train=${data.trainId}`}>
            {data.trainId} <ArrowRight size={12} />
          </Link>
        </div>
        <MetaItem
          label="공동 운송"
          value={`${formatNumber(data.participatingCarrierCount)}개 선사`}
        />
        <MetaItem label="적재율" value={formatPercent(data.trainLoadFactor)} />
        <MetaItem
          label="운송 거리"
          value={`${formatNumber(Math.round(data.physicalDistanceKm))}km`}
        />
        <MetaItem
          label="예상 철도 운임"
          value={formatKrw(data.estimatedRailChargeKrw)}
        />
      </div>

      <p className={styles.privacyNote}>
        표시된 상·하차 물량은 자사 물량만 집계한 값입니다. 공동 운송 열차의 전체 물량과
        다른 선사의 상·하차 정보는 제공되지 않습니다.
      </p>
    </div>
  );
}

function StopItem({
  stop,
  isFirst,
  isLast,
}: {
  stop: RecommendationStop;
  isFirst: boolean;
  isLast: boolean;
}) {
  const load20 = stop.ownLoadBoxes['20FT'];
  const load40 = stop.ownLoadBoxes['40FT'];
  const unload20 = stop.ownUnloadBoxes['20FT'];
  const unload40 = stop.ownUnloadBoxes['40FT'];

  return (
    <div className={styles.stop}>
      <div className={styles.stopHeader}>
        <span
          className={[styles.marker, stop.hasOwnWork ? styles.markerActive : '']
            .filter(Boolean)
            .join(' ')}
        />
        {!isLast && <span className={styles.connector} />}
      </div>
      <div className={styles.stopName}>{stop.hubName}</div>
      <div className={styles.stopTime}>{stopTimeLabel(stop, isFirst)}</div>

      {stop.hasOwnWork ? (
        <div className={styles.work}>
          {load20 > 0 && <span className={styles.load}>+ 20FT {load20}개</span>}
          {load40 > 0 && <span className={styles.load}>+ 40FT {load40}개</span>}
          {unload20 > 0 && <span className={styles.unload}>− 20FT {unload20}개</span>}
          {unload40 > 0 && <span className={styles.unload}>− 40FT {unload40}개</span>}
          {stop.availableTime && (
            <span className={styles.available}>
              사용 가능 {formatTime(stop.availableTime)}
            </span>
          )}
        </div>
      ) : (
        <div className={styles.noWork}>자사 상·하차 없음</div>
      )}
    </div>
  );
}

/** 출발역은 '출발', 종착역은 '도착', 중간 정차역은 도착·출발을 함께 표시한다. */
function stopTimeLabel(stop: RecommendationStop, isFirst: boolean): string {
  if (isFirst) {
    return `${formatTime(stop.departureTime ?? stop.arrivalTime)} 출발`;
  }
  if (!stop.arrivalTime) return '-';
  const arrival = `${formatTime(stop.arrivalTime)} 도착`;
  if (stop.departureTime && stop.departureTime !== stop.arrivalTime) {
    return `${arrival} · ${formatTime(stop.departureTime)} 출발`;
  }
  return arrival;
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaItem}>
      <span className={styles.metaLabel}>{label}</span>
      <span className={styles.metaValue}>{value}</span>
    </div>
  );
}
