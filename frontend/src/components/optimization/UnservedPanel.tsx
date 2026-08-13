import { Column, DataTable } from '@/components/common/DataTable';
import { EmptyState } from '@/components/common/States';
import { SizeTag, sharedStyles as styles } from './SizeTag';
import { formatBoxes, formatNumber } from '@/lib/format';
import type { UnservedNeed } from '@/types/domain';

/** 철도로 배정되지 못한 자사 수요.
 *
 *  `reasonIsProvenCause` 가 false 면 모델이 붙인 **진단 분류**일 뿐 확정 원인이 아니다.
 *  화면에서 "이래서 못 실었다"로 단정하지 않는다. 현재 결과는 전부 false 다.
 *
 *  커버리지가 76% 근처이므로 미배정이 남는 것은 정상이고, 이것을 숨기거나
 *  경고색으로 과장하지 않는다. */
export function UnservedPanel({ rows }: { rows: UnservedNeed[] }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="이번 주 미배정 수요가 없습니다."
        description="자사 Service Need가 모두 철도 재배치안에 배정되었습니다."
      />
    );
  }

  const columns: Column<UnservedNeed>[] = [
    {
      key: 'need',
      header: '수요 ID',
      width: '14%',
      render: (row) => <span className={styles.timeCell}>{row.needId}</span>,
    },
    {
      key: 'destination',
      header: '도착거점',
      width: '20%',
      render: (row) => <span style={{ fontWeight: 500 }}>{row.destinationName}</span>,
    },
    {
      key: 'size',
      header: '규격',
      width: '11%',
      render: (row) => <SizeTag size={row.size} />,
    },
    {
      key: 'qty',
      header: '미배정',
      width: '17%',
      render: (row) => (
        <>
          <span className={styles.qty}>{formatBoxes(row.unservedBoxes)}</span>
          <div className={styles.subtext}>{formatNumber(row.unservedTeu)} TEU</div>
        </>
      ),
    },
    {
      key: 'due',
      header: '필요시각',
      width: '18%',
      render: (row) => <span className={styles.timeCell}>{row.dueTime ?? '—'}</span>,
    },
    {
      key: 'reason',
      header: '모델 진단 분류',
      width: '20%',
      render: (row) => (
        <>
          <span className={styles.subtext}>{row.reason}</span>
          {!row.reasonIsProvenCause && (
            <div className={styles.subtext}>확정 원인 아님</div>
          )}
        </>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(row) => row.needId}
      minWidth={720}
    />
  );
}
