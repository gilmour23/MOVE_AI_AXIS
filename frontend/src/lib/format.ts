/** 숫자·날짜·요일 포맷 헬퍼는 이 파일에서만 관리한다 (핸드오프 §27). */

const numberFormatter = new Intl.NumberFormat('ko-KR');

export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

/** 컨테이너 수량은 항상 '개'. TEU 와 섞지 않는다 (§3). */
export function formatBoxes(value: number): string {
  return `${numberFormatter.format(value)}개`;
}

export function formatTeu(value: number): string {
  return `${numberFormatter.format(value)}TEU`;
}

export function formatSigned(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${numberFormatter.format(value)}`;
}

export function formatSignedBoxes(value: number): string {
  return `${formatSigned(value)}개`;
}

export function formatPercent(ratio: number, digits = 1): string {
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function formatKrw(value: number): string {
  return `${numberFormatter.format(Math.round(value))}원`;
}

/** MOVE-AI 의 모든 timestamp 는 **KST wall-clock 계획시각**이다.
 *
 *  `new Date('2026-08-10T06:00')` 처럼 timezone 없는 문자열을 파싱하면
 *  브라우저 지역시간으로 해석되어 UTC·미주 환경에서 날짜와 시각이 밀린다.
 *  따라서 문자열의 숫자 component 를 그대로 읽어 표시한다. */
export interface WallClock {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

const TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

export function parseWallClock(value: string | null): WallClock | null {
  if (!value) return null;
  const matched = TIMESTAMP.exec(value.trim());
  if (!matched) return null;
  return {
    year: Number(matched[1]),
    month: Number(matched[2]),
    day: Number(matched[3]),
    hour: Number(matched[4] ?? 0),
    minute: Number(matched[5] ?? 0),
  };
}

/** 같은 wall-clock 끼리의 상대 시간 계산용 숫자 좌표.
 *  timezone 변환 목적이 아니라 차이를 정확히 유지하기 위해 UTC 를 쓴다. */
export function wallClockMs(value: string | null): number | null {
  const w = parseWallClock(value);
  if (!w) return null;
  return Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute);
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

const pad = (n: number) => String(n).padStart(2, '0');

export function weekdayOf(value: string): string {
  const w = parseWallClock(value);
  if (!w) return '';
  return WEEKDAYS[new Date(Date.UTC(w.year, w.month - 1, w.day)).getUTCDay()];
}

/** '08.10' */
export function formatMonthDay(value: string): string {
  const w = parseWallClock(value);
  if (!w) return value;
  return `${pad(w.month)}.${pad(w.day)}`;
}

/** '08.10 (월)' */
export function formatDateShort(value: string): string {
  const w = parseWallClock(value);
  if (!w) return value;
  return `${pad(w.month)}.${pad(w.day)} (${weekdayOf(value)})`;
}

/** '06:00' */
export function formatTime(value: string | null): string {
  if (!value) return '-';
  const w = parseWallClock(value);
  if (!w) return value;
  return `${pad(w.hour)}:${pad(w.minute)}`;
}

/** '08.10 (월) 06:00' */
export function formatDateTime(value: string | null): string {
  if (!value) return '-';
  const w = parseWallClock(value);
  if (!w) return value;
  return `${formatDateShort(value)} ${formatTime(value)}`;
}

/** '08.10 06:00' — 작업시각처럼 자정을 넘길 수 있는 값은 항상 날짜를 함께 보여준다.
 *  시간만 보여주면 21:00 → 00:00 을 같은 날로 오해할 수 있다. */
export function formatDateTimeCompact(value: string | null): string {
  if (!value) return '-';
  const w = parseWallClock(value);
  if (!w) return value;
  return `${pad(w.month)}.${pad(w.day)} ${pad(w.hour)}:${pad(w.minute)}`;
}

/** 규격 표시 라벨 */
export function sizeLabel(size: string): string {
  return size === '20FT' ? '20FT' : '40FT';
}

export function sizeTabLabel(size: string): string {
  return size === '20FT' ? '20피트' : '40피트';
}
