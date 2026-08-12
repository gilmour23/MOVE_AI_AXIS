import type { ReactNode } from 'react';
import styles from './PageContainer.module.css';

interface PageContainerProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}

export function PageContainer({
  title,
  description,
  action,
  children,
}: PageContainerProps) {
  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{title}</h1>
          {description && <p className={styles.description}>{description}</p>}
        </div>
        {action && <div className={styles.headAction}>{action}</div>}
      </div>
      {children}
    </div>
  );
}
