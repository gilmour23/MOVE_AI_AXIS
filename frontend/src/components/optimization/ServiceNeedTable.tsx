import { Column, DataTable } from '@/components/common/DataTable';
import { EmptyState } from '@/components/common/States';
import { SizeTag, sharedStyles as styles } from './SizeTag';
import { formatBoxes, formatNumber } from '@/lib/format';
import type { ServiceNeedRow } from '@/types/domain';

interface ServiceNeedTableProps {
  rows: ServiceNeedRow[];
  highlightHub?: string | null;
}

/** 재배치 필요 현황 (핸드오프 §17.1).
 *  Service Need 가 전부 철도로 해결된 것은 아니므로 배정/미배정을 함께 보여준다.
 *  '모두 해결됨' 같은 문구를 하드코딩하지 않는다. */
export function ServiceNeedTable({ rows, highlightHub }: ServiceNeedTableProps) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="이번 주 재배치 필요가 발생하지 않았습니다."
        description="현재 계획 기준으로 자사 공컨 부족에 따른 Service Need가 생성되지 않았습니다."
      />
    );
  }

  // 남는 폭이 거점 컬럼에만 몰리지 않도록 비율로 배분한다 (PDF 표도 컬럼 폭이 고른 편).
  const columns: Column<ServiceNeedRow>[] = [
    {
      key: 'hub',
      header: '거점',
      width: '26%',
      render: (row) => <span style={{ fontWeight: 500 }}>{row.hubName}</span>,
    },
    {
      key: 'size',
      header: '규격',
      width: '13%',
      render: (row) => <SizeTag size={row.size} />,
    },
    {
      key: 'weekday',
      header: '요일',
      width: '23%',
      render: (row) => (
        <span className={styles.timeCell}>
          {row.weekday}요일
          <span className={styles.subtext}>{row.date}</span>
        </span>
      ),
    },
    {
      key: 'required',
      header: '필요량',
      width: '38%',
      render: (row) => (
        <>
          <span className={styles.qty}>{formatBoxes(row.requiredBoxes)}</span>
          <div className={styles.subtext}>
            철도 배정 {formatNumber(row.railServedBoxes)}개 ·{' '}
            {row.railUnservedBoxes > 0 ? (
              <span className={styles.shortageText}>
                미배정 {formatNumber(row.railUnservedBoxes)}개
              </span>
            ) : (
              <>미배정 0개</>
            )}
          </div>
        </>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(row) => `${row.hubCode}-${row.size}-${row.date}`}
      rowClassName={(row) =>
        highlightHub && row.hubCode === highlightHub ? 'is-highlight-hub' : undefined
      }
      minWidth={620}
      maxWidth={920}
    />
  );
}
