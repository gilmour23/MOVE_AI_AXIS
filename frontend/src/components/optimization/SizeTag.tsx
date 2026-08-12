import type { ContainerSize } from '@/types/domain';
import styles from './Shared.module.css';

export function SizeTag({ size }: { size: ContainerSize }) {
  return (
    <span
      className={[styles.sizeTag, size === '40FT' ? styles.size40 : '']
        .filter(Boolean)
        .join(' ')}
    >
      {size}
    </span>
  );
}

export const sharedStyles = styles;
