import { formatMonthDay, formatTime } from '@/lib/format';
import { formatRoute } from '@/config/hubMeta';
import type { KorailTrain } from '@/types/domain';
import styles from './Korail.module.css';

/** 'YYYY-MM-DD' 또는 'YYYY-MM-DDTHH:mm:ss' 의 날짜 부분을 로컬 자정으로 파싱한다.
 *  new Date('2026-08-10') 은 UTC 로 해석되어 하루가 밀릴 수 있으므로 직접 만든다. */
function localMidnight(value: string): Date | null {
  const [datePart] = value.split(/[T ]/);
  const [y, m, d] = datePart.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function parseTimestamp(value: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value.includes('T') ? value : value.replace(' ', 'T'));
  return Number.isNaN(date.getTime()) ? null : date;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** 주간 계획 타임라인.
 *
 *  계획주기 위에 각 열차의 출발~도착 구간만 표시한다.
 *  중간 정차 marker 는 넣지 않는다 — 균등 간격으로 임의 배치하면
 *  실제 정차 시각과 다른 정보를 만들어내기 때문이다.
 *  실시간 운행 상태가 아니라 계획값이다. */
export function WeeklyTimeline({
  trains,
  horizonStart,
  horizonEnd,
}: {
  trains: KorailTrain[];
  horizonStart: string;
  horizonEnd: string;
}) {
  const start = localMidnight(horizonStart);
  const endDay = localMidnight(horizonEnd);
  if (!start || !endDay) return null;

  // 마지막 날의 끝(다음날 자정)까지를 축으로 잡는다.
  const end = new Date(endDay.getTime() + DAY_MS);
  const span = end.getTime() - start.getTime();
  if (span <= 0) return null;

  const dayCount = Math.round(span / DAY_MS);
  const days = Array.from({ length: dayCount }, (_, i) => new Date(start.getTime() + i * DAY_MS));

  const pct = (date: Date) => ((date.getTime() - start.getTime()) / span) * 100;

  return (
    <div className={styles.timelineWrap}>
      <div className={styles.timelineHead}>
        <span className={styles.timelineName} />
        <div
          className={styles.timelineDays}
          style={{ gridTemplateColumns: `repeat(${dayCount}, minmax(0, 1fr))` }}
        >
          {days.map((day) => (
            <span key={day.toISOString()} className={styles.timelineDay}>
              {formatMonthDay(
                `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(
                  day.getDate(),
                ).padStart(2, '0')}`,
              )}
            </span>
          ))}
        </div>
      </div>

      {trains.map((train) => {
        const from = parseTimestamp(train.departureTime);
        const to = parseTimestamp(train.arrivalTime);
        if (!from || !to) return null;

        const left = Math.max(0, Math.min(100, pct(from)));
        const right = Math.max(0, Math.min(100, pct(to)));
        // 아주 짧은 운행도 보이도록 최소 폭을 준다.
        const width = Math.max(1.2, right - left);

        return (
          <div key={train.trainId} className={styles.timelineRow}>
            <span className={[styles.timelineName, styles.mono].join(' ')}>{train.trainId}</span>
            <span
              className={styles.timelineTrack}
              style={{
                backgroundSize: `${100 / dayCount}% 100%`,
              }}
            >
              <span
                className={styles.timelineBar}
                style={{ left: `${left}%`, width: `${width}%` }}
                title={`${formatRoute(train.route)} · ${formatTime(train.departureTime)} → ${formatTime(train.arrivalTime)}`}
              >
                <span className={styles.timelineBarText}>{formatRoute(train.route)}</span>
              </span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
