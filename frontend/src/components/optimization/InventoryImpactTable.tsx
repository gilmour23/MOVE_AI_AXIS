import { Column, DataTable } from '@/components/common/DataTable';
import { EmptyState } from '@/components/common/States';
import { StatusBadge } from '@/components/common/StatusBadge';
import { SizeTag, sharedStyles as styles } from './SizeTag';
import { formatNumber } from '@/lib/format';
import type { InventoryImpact } from '@/types/domain';

interface InventoryImpactTableProps {
  rows: InventoryImpact[];
  highlightHub?: string | null;
}

/** 거점별 재배치 영향 (핸드오프 §17.4).
 *  전/후 최저재고는 재고 화면과 동일한 daily closing 기준 값이며,
 *  '후 = 전 + 이동량' 같은 단순 산술로 만들지 않는다. */
export function InventoryImpactTable({ rows, highlightHub }: InventoryImpactTableProps) {
  if (rows.length === 0) {
    return <EmptyState title="표시할 재배치 영향 데이터가 없습니다." />;
  }

  // 남는 폭이 거점 컬럼에만 몰리지 않도록 비율로 배분한다.
  const columns: Column<InventoryImpact>[] = [
    {
      key: 'hub',
      header: '거점',
      width: '21%',
      render: (row) => <span style={{ fontWeight: 500 }}>{row.hubName}</span>,
    },
    {
      key: 'size',
      header: '규격',
      width: '10%',
      render: (row) => <SizeTag size={row.size} />,
    },
    {
      key: 'role',
      header: '역할',
      width: '13%',
      render: (row) => <RoleBadge role={row.role} />,
    },
    {
      key: 'before',
      header: '재배치 전 최저재고',
      width: '18%',
      render: (row) => (
        <>
          <span className={styles.qty}>{formatNumber(row.baselineMinDisplayedInventory)}</span>
          {row.baselineStockoutBoxes > 0 && (
            <div className={styles.subtext}>
              <span className={styles.shortageText}>
                부족 {formatNumber(row.baselineStockoutBoxes)}개
              </span>
            </div>
          )}
        </>
      ),
    },
    {
      key: 'movement',
      header: '이동량',
      width: '16%',
      render: (row) => <MovementCell row={row} />,
    },
    {
      key: 'after',
      header: '재배치 후 최저재고',
      width: '22%',
      render: (row) => (
        <>
          <span className={styles.qty}>{formatNumber(row.postRailMinDisplayedInventory)}</span>
          {row.postRailStockoutBoxes > 0 ? (
            <div className={styles.subtext}>
              <span className={styles.shortageText}>
                부족 {formatNumber(row.postRailStockoutBoxes)}개
              </span>
              {row.stockoutReductionBoxes > 0 && (
                <> · 감소 {formatNumber(row.stockoutReductionBoxes)}개</>
              )}
            </div>
          ) : (
            row.stockoutReductionBoxes > 0 && (
              <div className={styles.subtext}>
                부족 {formatNumber(row.stockoutReductionBoxes)}개 해소
              </div>
            )
          )}
        </>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(row) => `${row.hubCode}-${row.size}`}
      rowClassName={(row) =>
        highlightHub && row.hubCode === highlightHub ? 'is-highlight-hub' : undefined
      }
      minWidth={820}
      maxWidth={1080}
    />
  );
}

function RoleBadge({ role }: { role: InventoryImpact['role'] }) {
  if (role === '영향 없음') {
    return (
      <span className={styles.muted} style={{ fontSize: 12.5 }}>
        영향 없음
      </span>
    );
  }
  const tone = role === '출발' ? 'accent' : role === '도착' ? 'info' : 'warning';
  return (
    <StatusBadge tone={tone} small>
      {role}
    </StatusBadge>
  );
}

function MovementCell({ row }: { row: InventoryImpact }) {
  if (row.inboundBoxes === 0 && row.outboundBoxes === 0) {
    return <span className={styles.muted}>-</span>;
  }

  return (
    <span className={styles.qty}>
      {row.inboundBoxes > 0 && (
        <span style={{ color: 'var(--brand)' }}>+{formatNumber(row.inboundBoxes)}</span>
      )}
      {row.inboundBoxes > 0 && row.outboundBoxes > 0 && (
        <span className={styles.muted}> / </span>
      )}
      {row.outboundBoxes > 0 && (
        <span style={{ color: 'var(--accent)' }}>−{formatNumber(row.outboundBoxes)}</span>
      )}
      <span className={styles.muted} style={{ fontWeight: 400 }}>
        개
      </span>
    </span>
  );
}
