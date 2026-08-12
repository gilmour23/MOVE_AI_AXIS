import type { ReactNode } from 'react';
import styles from './StatusBadge.module.css';

export type BadgeTone = 'normal' | 'shortage' | 'neutral' | 'info' | 'accent' | 'warning';

interface StatusBadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  dot?: boolean;
  small?: boolean;
  title?: string;
}

export function StatusBadge({
  tone = 'neutral',
  children,
  dot = false,
  small = false,
  title,
}: StatusBadgeProps) {
  const classes = [styles.badge, styles[tone], small ? styles.small : '']
    .filter(Boolean)
    .join(' ');
  return (
    <span className={classes} title={title}>
      {dot && <span className={styles.dot} />}
      {children}
    </span>
  );
}

/** 부족 상태 표기.
 *  현재 데이터로 확실히 말할 수 있는 상태만 사용한다 —
 *  '주의'/'위험'/'안전재고' 같은 임의 threshold 를 만들지 않는다 (핸드오프 §14.6). */
export function ShortageBadge({ boxes, small }: { boxes: number; small?: boolean }) {
  if (boxes > 0) {
    return (
      <StatusBadge tone="shortage" dot small={small}>
        부족 예상
      </StatusBadge>
    );
  }
  return (
    <StatusBadge tone="normal" dot small={small}>
      정상
    </StatusBadge>
  );
}
