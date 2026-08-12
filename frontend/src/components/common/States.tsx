import type { ReactNode } from 'react';
import { AlertTriangle, Inbox, TriangleAlert } from 'lucide-react';
import styles from './States.module.css';

export function Skeleton({
  width = '100%',
  height = 14,
  radius,
}: {
  width?: number | string;
  height?: number | string;
  radius?: number;
}) {
  return (
    <div
      className={styles.skeleton}
      style={{ width, height, borderRadius: radius }}
      aria-hidden
    />
  );
}

export function LoadingSkeleton({
  rows = 4,
  height = 14,
}: {
  rows?: number;
  height?: number;
}) {
  return (
    <div className={styles.skeletonStack} role="status" aria-label="불러오는 중">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton
          key={index}
          height={height}
          width={index === rows - 1 ? '62%' : '100%'}
        />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 5, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className={styles.skeletonStack} role="status" aria-label="불러오는 중">
      <Skeleton height={34} />
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} style={{ display: 'flex', gap: 10 }}>
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <Skeleton key={columnIndex} height={22} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 220 }: { height?: number }) {
  return <Skeleton height={height} radius={12} />;
}

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
}

export function EmptyState({ title, description, icon }: EmptyStateProps) {
  return (
    <div className={styles.state}>
      <div className={styles.icon}>{icon ?? <Inbox size={18} />}</div>
      <div className={styles.title}>{title}</div>
      {description && <p className={styles.description}>{description}</p>}
    </div>
  );
}

interface ErrorStateProps {
  error: Error;
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const isMissingResults =
    'code' in error && (error as { code?: string }).code === 'RESULT_FILES_MISSING';

  return (
    <div className={styles.state}>
      <div className={[styles.icon, styles.iconError].join(' ')}>
        <AlertTriangle size={18} />
      </div>
      <div className={styles.title}>
        {isMissingResults
          ? '최적화 결과 파일을 불러오지 못했습니다.'
          : '데이터를 불러오지 못했습니다.'}
      </div>
      <p className={styles.description}>
        {isMissingResults ? '결과 디렉터리 설정을 확인해주세요.' : error.message}
      </p>
      {onRetry && (
        <button type="button" className={styles.retry} onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}

export function InlineNotice({
  title,
  children,
  danger = false,
}: {
  title: string;
  children?: ReactNode;
  danger?: boolean;
}) {
  return (
    <div
      className={[styles.inlineNotice, danger ? styles.inlineNoticeDanger : '']
        .filter(Boolean)
        .join(' ')}
      role="status"
    >
      <TriangleAlert size={16} style={{ flexShrink: 0, marginTop: 1 }} />
      <div>
        <div className={styles.noticeTitle}>{title}</div>
        {children}
      </div>
    </div>
  );
}
