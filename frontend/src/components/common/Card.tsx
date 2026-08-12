import type { ReactNode } from 'react';
import styles from './Card.module.css';

interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  soft?: boolean;
  flush?: boolean;
  className?: string;
  id?: string;
}

export function Card({
  title,
  subtitle,
  action,
  children,
  soft = false,
  flush = false,
  className,
  id,
}: CardProps) {
  const hasHeader = Boolean(title || subtitle || action);
  const classes = [styles.card, soft ? styles.soft : '', className ?? '']
    .filter(Boolean)
    .join(' ');

  const bodyClasses = [
    styles.body,
    hasHeader ? styles.bodyWithHeader : '',
    flush ? styles.flush : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section className={classes} id={id}>
      {hasHeader && (
        <header className={styles.header}>
          <div className={styles.headerText}>
            {title && <h2 className={styles.title}>{title}</h2>}
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {action && <div className={styles.action}>{action}</div>}
        </header>
      )}
      <div className={bodyClasses}>{children}</div>
    </section>
  );
}
