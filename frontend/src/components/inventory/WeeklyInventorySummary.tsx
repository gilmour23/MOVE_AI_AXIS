import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMeta } from '@/app/MetaContext';
import { ArrowRight } from 'lucide-react';
import { formatNumber, formatSigned } from '@/lib/format';
import type { WeeklyInventorySummaryData } from '@/types/domain';
import styles from './WeeklyInventorySummary.module.css';

interface WeeklyInventorySummaryProps {
  summary: WeeklyInventorySummaryData;
  /** 부족이 있을 때 최적화 페이지로 이동하는 링크를 보여줄지 (§18) */
  showOptimizationLink?: boolean;
}

/** 재고 페이지와 최적화 페이지 하단이 같은 컴포넌트를 쓴다 (§17.5).
 *  계산은 모두 backend selector 에서 끝난 값을 그대로 표시한다. */
export function WeeklyInventorySummary({
  summary,
  showOptimizationLink = false,
}: WeeklyInventorySummaryProps) {
  const { weekId } = useMeta();
  const isPostRail = summary.mode === 'postRail';
  const hasShortage = summary.weeklyUnmetDemand > 0;
  const change = summary.weeklyInventoryChange;

  return (
    <div>
      <div className={styles.list}>
        <SummaryRow label="주간 예상 수요" value={summary.weeklyDemand} />
        <SummaryRow
          label="주간 예상 공급"
          value={summary.weeklyExternalSupply}
          subtext="외부 공급 기준 (철도 유입 제외)"
        />
        <SummaryRow
          label="주간 재고 증감"
          valueNode={
            <span
              className={[
                styles.value,
                change > 0 ? styles.positive : '',
                change < 0 ? styles.negative : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {formatSigned(change)}
              <span className={styles.unit}>개</span>
            </span>
          }
          subtext={
            isPostRail
              ? `철도 유입 ${formatNumber(summary.railInboundBoxes)}개 · 반출 ${formatNumber(
                  summary.railOutboundBoxes,
                )}개`
              : `기초 재고 ${formatNumber(summary.initialInventory)}개 → 주말 ${formatNumber(
                  summary.weekEndInventory,
                )}개`
          }
        />
        <SummaryRow
          label="주간 최저 예상재고"
          value={summary.minimumDisplayedInventory}
        />
      </div>

      <div
        className={[styles.highlight, hasShortage ? styles.highlightShortage : '']
          .filter(Boolean)
          .join(' ')}
      >
        <div className={styles.highlightLabel}>부족 예상</div>
        <div className={styles.highlightValue}>
          {hasShortage ? (
            <>
              {formatNumber(summary.weeklyUnmetDemand)}
              <span className={styles.unit}>개</span>
            </>
          ) : (
            '없음'
          )}
        </div>
        {hasShortage && (
          <div className={styles.shortageDays}>
            부족 발생 요일 {summary.shortageDays.join('·')}
          </div>
        )}
      </div>

      {hasShortage && showOptimizationLink && (
        <Link
          className={styles.link}
          to={`/carrier/plan?week=${weekId}&hub=${summary.hubCode}&size=${summary.size}`}
        >
          MOVE-AI 재배치안 보기 <ArrowRight size={14} />
        </Link>
      )}
    </div>
  );
}

function SummaryRow({
  label,
  value,
  valueNode,
  subtext,
}: {
  label: string;
  value?: number;
  valueNode?: ReactNode;
  subtext?: string;
}) {
  return (
    <div className={styles.row}>
      <span className={styles.label}>{label}</span>
      <span className={styles.valueWrap}>
        {valueNode ?? (
          <span className={styles.value}>
            {formatNumber(value ?? 0)}
            <span className={styles.unit}>개</span>
          </span>
        )}
        {subtext && <div className={styles.subtext}>{subtext}</div>}
      </span>
    </div>
  );
}
