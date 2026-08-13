import { Fragment } from 'react';
import { ChevronRight } from 'lucide-react';
import { EmptyState } from '@/components/common/States';
import { SizeTag } from './SizeTag';
import { RecommendationRouteDetail } from './RecommendationRouteDetail';
import { formatKrw, formatBoxes, formatDateShort, formatTime } from '@/lib/format';
import type { CarrierRecommendation } from '@/types/domain';
import styles from './RecommendationTable.module.css';

interface RecommendationTableProps {
  carrierId: string;
  rows: CarrierRecommendation[];
  expandedId: string | null;
  onToggle: (recommendationId: string) => void;
  highlightId?: string | null;
}

/** 철도 기반 공컨 재배치 제안 (핸드오프 §17.2).
 *  PDF 표 구조(출발/도착/규격/물량/출발시간/도착시간)를 유지하고,
 *  available_time 은 도착시간 셀 아래와 상세 패널에서 노출한다 (§4.2). */
export function RecommendationTable({
  carrierId,
  rows,
  expandedId,
  onToggle,
  highlightId,
}: RecommendationTableProps) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="이번 주 철도 재배치 권고가 없습니다."
        description={
          '현재 계획 기준으로 추천 가능한 철도 재배치안이 생성되지 않았습니다.'
        }
      />
    );
  }

  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        {/* 남는 폭이 출발/도착 컬럼에만 몰리지 않도록 비율로 배분한다. */}
        <colgroup>
          <col style={{ width: 44 }} />
          <col style={{ width: '16%' }} />
          <col style={{ width: '16%' }} />
          <col style={{ width: '8%' }} />
          <col style={{ width: '9%' }} />
          <col style={{ width: '17%' }} />
          <col style={{ width: '20%' }} />
          <col style={{ width: '14%' }} />
        </colgroup>
        <thead>
          <tr>
            <th className={styles.expandCell} scope="col">
              <span className="sr-only">상세</span>
            </th>
            <th scope="col">출발</th>
            <th scope="col">도착</th>
            <th scope="col">규격</th>
            <th scope="col">물량</th>
            <th scope="col">출발시간</th>
            <th scope="col">도착시간</th>
            <th scope="col">추정 철도운임</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const open = expandedId === row.recommendationId;
            return (
              <Fragment key={row.recommendationId}>
                <tr
                  id={row.recommendationId}
                  className={[
                    styles.row,
                    open ? styles.rowOpen : '',
                    highlightId === row.recommendationId ? styles.rowHighlight : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => onToggle(row.recommendationId)}
                >
                  <td className={styles.expandCell}>
                    <span
                      className={[styles.chevron, open ? styles.chevronOpen : '']
                        .filter(Boolean)
                        .join(' ')}
                      aria-hidden
                    >
                      <ChevronRight size={16} />
                    </span>
                  </td>
                  <td className={styles.hubName}>{row.originName}</td>
                  <td className={styles.hubName}>{row.destinationName}</td>
                  <td>
                    <SizeTag size={row.size} />
                  </td>
                  <td>
                    <strong>{formatBoxes(row.quantityBoxes)}</strong>
                  </td>
                  <td className={styles.timeCell}>
                    <span className={styles.timeDay}>
                      {formatDateShort(row.departureTime)}
                    </span>
                    {formatTime(row.departureTime)}
                  </td>
                  <td className={styles.timeCell}>
                    <span className={styles.timeDay}>
                      {formatDateShort(row.arrivalTime)}
                    </span>
                    {formatTime(row.arrivalTime)}
                    <div className={styles.availableHint}>
                      사용 가능 {formatTime(row.availableTime)}
                    </div>
                  </td>
                  {/* 추정 철도운임. 매출/수익/이익이 아니다. */}
                  <td className={styles.timeCell}>{formatKrw(row.estimatedRailChargeKrw)}</td>
                </tr>
                {open && (
                  <tr className={styles.detailRow}>
                    <td colSpan={8}>
                      <RecommendationRouteDetail
                        carrierId={carrierId}
                        recommendation={row}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
