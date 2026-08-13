import { useState } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { SizeTag } from '@/components/optimization/SizeTag';
import { fetchCarrierSchedule } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useCarrierId, useMeta } from '@/app/MetaContext';
import { formatBoxes, formatDateShort, formatNumber, formatTime } from '@/lib/format';
import type { ScheduleStop, ScheduleTrain } from '@/types/domain';
import styles from './TrackingPage.module.css';

/** 운송 일정 — 자사 공컨이 어떤 계획열차에 배정되었고 언제 상차·출발·도착·사용 가능한지.
 *
 *  실시간 추적 화면이 아니다. 결과에 없는 진행 상태(운송중·완료·지연)를 만들지 않고,
 *  현재 시각과 비교해 상태를 유도하지도 않는다. 전부 계획 시각이다.
 *
 *  route 는 호환을 위해 `/carrier/tracking` 을 유지한다. */
export function TrackingPage() {
  const carrierId = useCarrierId();
  const { weekId } = useMeta();
  const [openTrain, setOpenTrain] = useState<string | null>(null);

  const { data, loading, error, reload } = useAsync(
    (signal) =>
      carrierId && weekId
        ? fetchCarrierSchedule(carrierId, weekId, signal)
        : Promise.resolve(null),
    [carrierId, weekId],
  );

  return (
    <PageContainer
      title="운송 일정"
      description="자사 공컨이 배정된 계획열차와 상차 준비·출발·도착·사용 가능 예정 시각입니다."
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={4} height={24} />
        </Card>
      )}

      {data && data.trains.length === 0 && (
        <Card>
          <EmptyState
            title="이번 계획주차에 배정된 운송이 없습니다."
            description="자사 공컨이 배정된 계획열차가 없습니다."
          />
        </Card>
      )}

      {data?.trains.map((train) => (
        <TrainCard
          key={train.trainId}
          train={train}
          open={openTrain === train.trainId}
          onToggle={() =>
            setOpenTrain((current) => (current === train.trainId ? null : train.trainId))
          }
        />
      ))}

      {data && data.trains.length > 0 && (
        <p className={styles.note}>
          모든 시각은 최적화 결과의 <strong>계획 시각</strong>입니다. 실시간 위치·운행
          실적은 연동되어 있지 않으므로 진행 상태를 생성하지 않습니다.
        </p>
      )}
    </PageContainer>
  );
}

function TrainCard({
  train,
  open,
  onToggle,
}: {
  train: ScheduleTrain;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <Card
      title={`계획열차 ID · ${train.trainId}`}
      subtitle={train.route ?? undefined}
      action={
        <button type="button" className={styles.toggle} onClick={onToggle}>
          {open ? '정차 계획 접기' : '정차 계획 보기'}
        </button>
      }
    >
      <div className={styles.summary}>
        <Fact label="계획 출발" value={stamp(train.departureTime)} />
        <Fact label="최종 도착" value={stamp(train.arrivalTime)} />
        <Fact
          label="편성"
          value={`${train.formation ?? '—'} · ${formatNumber(train.wagons)}량`}
          sub={`용량 ${formatNumber(train.capacityTeu)} TEU`}
        />
        <Fact
          label="자사 물량"
          value={formatBoxes(train.ownBoxes)}
          sub={`${formatNumber(train.ownTeu)} TEU`}
        />
        <Fact
          label="공동 운송"
          value={`${formatNumber(train.participatingCarrierCount)}개 선사`}
          sub={`열차 전체 ${formatNumber(train.assignedTeu)} TEU`}
        />
      </div>

      <div className={styles.lanes}>
        {train.ownAllocations.map((lane, index) => (
          <span key={index} className={styles.lane}>
            {lane.originName} → {lane.destinationName}
            <SizeTag size={lane.size} />
            {formatBoxes(lane.boxes)}
          </span>
        ))}
      </div>

      {open && <StopTimeline stops={train.stops} />}
    </Card>
  );
}

/** 열차의 전체 정차 계획. 자사 작업이 있는 정차역을 강조한다.
 *
 *  자사 작업이 없는 역도 숨기지 않는다 — 그 열차가 어디를 거쳐 가는지가
 *  운송 일정의 일부이기 때문이다. 다만 그 역의 상하차량은 열차 전체 값이 아니라
 *  자사 값(0)으로 표시한다. */
function StopTimeline({ stops }: { stops: ScheduleStop[] }) {
  return (
    <ol className={styles.timeline}>
      {stops.map((stop) => {
        const load = stop.ownLoadBoxes['20FT'] + stop.ownLoadBoxes['40FT'];
        const unload = stop.ownUnloadBoxes['20FT'] + stop.ownUnloadBoxes['40FT'];
        const isOrigin = stop.sequence === 1;
        const isFinal = stop.sequence === stops.length;

        return (
          <li
            key={stop.sequence}
            className={[styles.stop, stop.hasOwnWork ? styles.stopOwn : '']
              .filter(Boolean)
              .join(' ')}
          >
            <div className={styles.stopHead}>
              <span className={styles.stopName}>{stop.hubName}</span>
              {stop.hasOwnWork && <span className={styles.ownTag}>자사 작업</span>}
            </div>

            <dl className={styles.times}>
              {isOrigin && <Time label="상차 준비" value={stop.loadStartTime} />}
              {!isOrigin && <Time label="도착" value={stop.arrivalTime} />}
              {!isFinal && <Time label="출발" value={stop.departureTime} />}
              {/* 사용 가능은 자사 하차가 있을 때만 의미가 있다. */}
              {unload > 0 && <Time label="사용 가능 예정" value={stop.availableTime} />}
            </dl>

            {(load > 0 || unload > 0) && (
              <p className={styles.work}>
                {load > 0 && <>상차 {formatBoxes(load)}</>}
                {load > 0 && unload > 0 && ' · '}
                {unload > 0 && <>하차 {formatBoxes(unload)}</>}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Time({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className={styles.time}>
      <dt>{label}</dt>
      <dd>{stamp(value)}</dd>
    </div>
  );
}

function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={styles.fact}>
      <span className={styles.factLabel}>{label}</span>
      <span className={styles.factValue}>{value}</span>
      {sub && <span className={styles.factSub}>{sub}</span>}
    </div>
  );
}

function stamp(value: string | null): string {
  if (!value) return '—';
  return `${formatDateShort(value)} ${formatTime(value)}`;
}
