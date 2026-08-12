import type { BadgeTone } from '@/components/common/StatusBadge';

/** KORAIL Control Tower 공용 상태 색상 규칙.
 *
 *  색은 의미 기반으로만 쓴다.
 *    success  정상 · 부족 해소 · 배정 완료
 *    warning  부분 배정
 *    danger   미배정 · 부족 잔존
 *
 *  적재율처럼 좋고 나쁨을 단정할 수 없는 값에는 색 의미를 부여하지 않는다.
 *  화면마다 tone 을 따로 정하지 않고 이 함수 하나만 사용한다. */

const SUCCESS = new Set(['정상', '부족 해소', '해소', '배정 완료']);
const WARNING = new Set(['부분 배정']);

export function statusTone(status: string): BadgeTone {
  if (SUCCESS.has(status)) return 'normal';
  if (WARNING.has(status)) return 'warning';
  return 'shortage';
}
