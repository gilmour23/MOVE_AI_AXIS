import { EmptyState } from '@/components/common/States';
import { formatNumber } from '@/lib/format';
import { hubFullName } from '@/config/hubMeta';
import type { RecommendationExplanation as Explanation } from '@/types/domain';
import styles from './RecommendationExplanation.module.css';

/** `왜 이 추천인가`.
 *
 *  결과 파일(RECOMMENDATION_EXPLANATION_CONTEXT)에 있는 사실만 옮긴다.
 *  solver 의 인과증명이 아니므로 "이래서 이렇게 배정했다"로 단정하지 않고,
 *  연결된 수요와 출발거점의 가용량이라는 **관찰값**만 나열한다. */
export function RecommendationExplanationPanel({
  rows,
}: {
  rows: Explanation[];
}) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="추천 근거 데이터가 없습니다."
        description="이번 계획주차 결과에 설명 컨텍스트 파일이 포함되지 않았습니다."
      />
    );
  }

  return (
    <div className={styles.list}>
      {rows.map((row) => (
        <article key={row.recommendationId} className={styles.item}>
          <header className={styles.head}>
            <span className={styles.recId}>{row.recommendationId}</span>
            <span className={styles.route}>
              {hubFullName(row.originHub)} → {hubFullName(row.destinationHub)} ·{' '}
              {row.size}
            </span>
          </header>

          <dl className={styles.facts}>
            <div className={styles.fact}>
              <dt>연결된 수요</dt>
              <dd>
                {formatNumber(row.linkedNeedCount)}건 ·{' '}
                {formatNumber(row.linkedServiceNeedTeu)} TEU
              </dd>
            </div>
            <div className={styles.fact}>
              <dt>수요 납기</dt>
              <dd>
                {row.linkedNeedDueMin ?? '—'} ~ {row.linkedNeedDueMax ?? '—'}
              </dd>
            </div>
            <div className={styles.fact}>
              <dt>출발거점 가용</dt>
              <dd>
                {formatNumber(row.sourceReleaseCapacityBoxes)}개 중{' '}
                {formatNumber(row.assignedOutboundBoxes)}개 배정 · 잔여{' '}
                {formatNumber(row.sourceReleaseRemainingBoxes)}개
              </dd>
            </div>
            <div className={styles.fact}>
              <dt>배정량</dt>
              <dd>
                {formatNumber(row.recommendedBoxes)}개 ·{' '}
                {formatNumber(row.recommendedTeu)} TEU
              </dd>
            </div>
            <div className={styles.fact}>
              <dt>납기 여유</dt>
              <dd>{formatNumber(Math.round(row.earlinessHours))}시간</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}
