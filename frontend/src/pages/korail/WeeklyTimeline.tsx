import { formatMonthDay, formatTime, parseWallClock, wallClockMs } from '@/lib/format';
import type { KorailTrain } from '@/types/domain';
import { trainOdLabel, viaHubLabel } from './trainInfo';
import styles from './Korail.module.css';

const DAY_MS = 24 * 60 * 60 * 1000;

/** 계획주기 축의 하루 단위 눈금. 모든 좌표는 KST wall-clock 을
 *  같은 기준으로 숫자화한 값이라 브라우저 timezone 과 무관하다. */
function dayAxis(horizonStart: string, horizonEnd: string) {
  const start = parseWallClock(horizonStart);
  const end = parseWallClock(horizonEnd);
  if (!start || !end) return null;

  const startMs = Date.UTC(start.year, start.month - 1, start.day);
  // 마지막 날의 끝(다음날 자정)까지를 축으로 잡는다.
  const endMs = Date.UTC(end.year, end.month - 1, end.day) + DAY_MS;
  const span = endMs - startMs;
  if (span <= 0) return null;

  const dayCount = Math.round(span / DAY_MS);
  const days = Array.from({ length: dayCount }, (_, i) => {
    const d = new Date(startMs + i * DAY_MS);
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(
      d.getUTCDate(),
    ).padStart(2, '0')}`;
  });

  return { startMs, span, dayCount, days };
}

/** 주간 운행 스케줄.
 *
 *  계획주기 위에 각 열차의 출발~도착 구간만 그린다.
 *  중간 정차 marker 는 넣지 않는다 — per-stop 시각을 쓰지 않고
 *  균등 간격으로 배치하면 실제와 다른 정보를 만들어내기 때문이다.
 *  실시간 운행 상태가 아니라 계획값이다. */
export function WeeklyTimeline({
  trains,
  horizonStart,
  horizonEnd,
  showCargo = false,
  onSelect,
}: {
  trains: KorailTrain[];
  horizonStart: string;
  horizonEnd: string;
  /** 종합계획처럼 화차·물량·경유까지 함께 읽어야 할 때 켠다. */
  showCargo?: boolean;
  onSelect?: (trainId: string) => void;
}) {
  const axis = dayAxis(horizonStart, horizonEnd);
  if (!axis) return null;

  const { startMs, span, dayCount, days } = axis;
  const pct = (ms: number) => ((ms - startMs) / span) * 100;

  return (
    <div className={styles.timelineWrap}>
      <div className={styles.timelineHead}>
        <span className={styles.timelineName} />
        <div
          className={styles.timelineDays}
          style={{ gridTemplateColumns: `repeat(${dayCount}, minmax(0, 1fr))` }}
        >
          {days.map((day) => (
            <span key={day} className={styles.timelineDay}>
              {formatMonthDay(day)}
            </span>
          ))}
        </div>
      </div>

      {trains.map((train) => {
        const from = wallClockMs(train.departureTime);
        const to = wallClockMs(train.arrivalTime);
        if (from === null || to === null) return null;

        const left = Math.max(0, Math.min(100, pct(from)));
        const right = Math.max(0, Math.min(100, pct(to)));
        // 아주 짧은 운행도 보이도록 최소 폭을 준다.
        const width = Math.max(1.2, right - left);
        const via = viaHubLabel(train);

        return (
          <div
            key={train.trainId}
            className={[styles.scheduleRow, onSelect ? styles.rowClickable : '']
              .filter(Boolean)
              .join(' ')}
            onClick={onSelect ? () => onSelect(train.trainId) : undefined}
          >
            <div className={styles.scheduleInfo}>
              <span className={styles.scheduleId}>{train.trainId}</span>
              <span className={styles.scheduleOd}>{trainOdLabel(train)}</span>
              <span className={styles.scheduleMeta}>
                {formatMonthDay(train.departureTime)} {formatTime(train.departureTime)} →{' '}
                {formatMonthDay(train.arrivalTime)} {formatTime(train.arrivalTime)}
                {showCargo && (
                  <>
                    {' · '}
                    {train.wagons}량 · {train.totalBoxes}개 / {train.assignedTeu} TEU
                    {via && ` · 경유: ${via}`}
                  </>
                )}
              </span>
            </div>
            <span className={styles.timelineTrack}>
              <span
                className={styles.timelineBar}
                style={{ left: `${left}%`, width: `${width}%` }}
              />
            </span>
          </div>
        );
      })}
    </div>
  );
}
