import type { ReactNode } from 'react';
import styles from './DataTable.module.css';

export interface Column<T> {
  key: string;
  header: ReactNode;
  align?: 'left' | 'right' | 'center';
  width?: number | string;
  render: (row: T, index: number) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  onRowClick?: (row: T, index: number) => void;
  rowClassName?: (row: T, index: number) => string | undefined;
  minWidth?: number;
  /** 컬럼 수가 적은 표가 넓은 화면에서 과도하게 늘어나 여백이 생기는 것을 막는다. */
  maxWidth?: number;
  caption?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  rowClassName,
  minWidth,
  maxWidth,
  caption,
}: DataTableProps<T>) {
  return (
    <div className={styles.scroll}>
      <table
        className={styles.table}
        style={{
          ...(minWidth ? { minWidth } : {}),
          ...(maxWidth ? { maxWidth } : {}),
        }}
      >
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={alignClass(column.align)}
                style={column.width ? { width: column.width } : undefined}
                scope="col"
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={rowKey(row, index)}
              className={[
                onRowClick ? styles.clickable : '',
                rowClassName?.(row, index) ?? '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={onRowClick ? () => onRowClick(row, index) : undefined}
            >
              {columns.map((column) => (
                <td key={column.key} className={alignClass(column.align)}>
                  {column.render(row, index)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function alignClass(align: Column<unknown>['align']): string | undefined {
  if (align === 'right') return styles.alignRight;
  if (align === 'center') return styles.alignCenter;
  return undefined;
}

export const tableStyles = styles;
