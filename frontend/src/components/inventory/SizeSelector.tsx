import { sizeTabLabel } from '@/lib/format';
import type { ContainerSize } from '@/types/domain';
import styles from './SelectorRow.module.css';

const SIZES: ContainerSize[] = ['20FT', '40FT'];

interface SizeSelectorProps {
  size: ContainerSize;
  onSelectSize: (size: ContainerSize) => void;
  hint?: string;
}

/** 화면 흐름의 시작점.
 *  여기서 고른 규격이 아래 거점별 매트릭스 → 선택 거점 추이·요약까지 그대로 이어진다.
 *  (PDF 2·4페이지의 `규격별 재고 현황 / 20피트 / 40피트` 행) */
export function SizeSelector({ size, onSelectSize, hint }: SizeSelectorProps) {
  return (
    <div
      className={[styles.row, styles.primary].join(' ')}
      role="group"
      aria-label="컨테이너 규격 선택"
    >
      <span className={styles.label}>규격별 재고 현황</span>
      <div className={styles.chips}>
        {SIZES.map((value) => {
          const active = value === size;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={active}
              className={[styles.chip, active ? styles.active : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => onSelectSize(value)}
            >
              {sizeTabLabel(value)}
            </button>
          );
        })}
      </div>
      {hint && <span className={styles.hint}>{hint}</span>}
    </div>
  );
}
