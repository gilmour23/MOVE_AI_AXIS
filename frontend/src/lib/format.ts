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

/** '2026-08-10 06:00' 또는 ISO 문자열을 안전하게 파싱한다 (모든 시각은 KST 기준). */
function parse(value: string): Date | null {
  const normalized = value.includes('T') ? value : value.replace(' ', 'T');
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

export function weekdayOf(value: string): string {
  const date = parse(value);
  return date ? WEEKDAYS[date.getDay()] : '';
}

/** '08.10' */
export function formatMonthDay(value: string): string {
  const date = parse(value);
  if (!date) return value;
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${mm}.${dd}`;
}

/** '08.10 (월)' */
export function formatDateShort(value: string): string {
  const date = parse(value);
  if (!date) return value;
  return `${formatMonthDay(value)} (${WEEKDAYS[date.getDay()]})`;
}

/** '06:00' */
export function formatTime(value: string | null): string {
  if (!value) return '-';
  const date = parse(value);
  if (!date) return value;
  const hh = String(date.getHours()).padStart(2, '0');
  const mi = String(date.getMinutes()).padStart(2, '0');
  return `${hh}:${mi}`;
}

/** '08.10 (월) 06:00' */
export function formatDateTime(value: string | null): string {
  if (!value) return '-';
  return `${formatDateShort(value)} ${formatTime(value)}`;
}

/** '08.10 06:00' — 작업시각처럼 자정을 넘길 수 있는 값은 항상 날짜를 함께 보여준다.
 *  시간만 보여주면 21:00 → 00:00 을 같은 날로 오해할 수 있다. */
export function formatDateTimeCompact(value: string | null): string {
  if (!value) return '-';
  const date = parse(value);
  if (!date) return value;
  return `${formatMonthDay(value)} ${formatTime(value)}`;
}

/** 규격 표시 라벨 */
export function sizeLabel(size: string): string {
  return size === '20FT' ? '20FT' : '40FT';
}

export function sizeTabLabel(size: string): string {
  return size === '20FT' ? '20피트' : '40피트';
}
