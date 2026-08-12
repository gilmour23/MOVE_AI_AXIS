import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailInsights } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatNumber, formatPercent } from '@/lib/format';
import styles from './Korail.module.css';

/** 수급 분석 및 권고.
 *
 *  여기 수치는 MILP 결과에서 직접 계산한 값이므로 '운영 분석'으로 표기한다.
 *  생성형 AI 가 만든 설명은 Copilot(우측 하단)에서만 AI 로 표기한다. */
export function KorailInsightsPage() {
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailInsights(signal), []);

  return (
    <PageContainer
      title="수급 분석 및 권고"
      description="최적화 결과에서 계산한 거점 수급 영향과 구간 적재 분석입니다."
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={5} height={24} />
        </Card>
      )}

      {data && (
        <>
          <div className={styles.kpiStrip}>
            <Kpi label="재배치 전 총 부족" value={`${formatNumber(data.totals.baselineStockout)}개`} />
            <Kpi label="재배치 후 총 부족" value={`${formatNumber(data.totals.postRailStockout)}개`} />
            <Kpi label="부족 감소" value={`${formatNumber(data.totals.reduction)}개`} />
          </div>

          <Card
            title="거점·규격별 수급 영향"
            subtitle="철도 재배치로 해소된 부족과 잔존 부족"
          >
            {data.stockoutImpacts.length === 0 ? (
              <EmptyState title="부족이 발생한 거점이 없습니다." />
            ) : (
              <div className={styles.scroll}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>거점</th>
                      <th>규격</th>
                      <th className={styles.right}>재배치 전 부족</th>
                      <th className={styles.right}>철도 유입</th>
                      <th className={styles.right}>재배치 후 부족</th>
                      <th className={styles.right}>감소</th>
                      <th>결과</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.stockoutImpacts.map((item) => (
                      <tr key={`${item.hubCode}-${item.size}`}>
                        <td>{item.hubName}</td>
                        <td>{item.size}</td>
                        <td className={styles.right}>{item.baselineStockout}</td>
                        <td className={styles.right}>{item.railInbound}</td>
                        <td className={styles.right}>{item.postRailStockout}</td>
                        <td className={styles.right}>{item.reduction}</td>
                        <td>
                          <StatusBadge tone={item.resolved ? 'normal' : 'shortage'} small>
                            {item.resolved ? '해소' : '부족 잔존'}
                          </StatusBadge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className={styles.note} style={{ marginTop: 12 }}>
              위 수치는 최적화 결과(INVENTORY_IMPACT_SUMMARY)에서 직접 계산한 값입니다.
              생성형 AI가 만든 설명이 아니므로 <strong>운영 분석</strong>으로 표기합니다.
            </div>
          </Card>

          <div className={styles.grid2}>
            <Card title="적재율이 낮은 구간" subtitle="추가 수요 유치 여지가 있는 구간">
              <SegmentTable rows={data.lowestLoadSegments} />
            </Card>
            <Card title="적재율이 높은 구간" subtitle="증차 검토가 필요할 수 있는 구간">
              <SegmentTable rows={data.highestLoadSegments} />
            </Card>
          </div>
        </>
      )}
    </PageContainer>
  );
}

function SegmentTable({
  rows,
}: {
  rows: {
    trainId: string;
    fromHubName: string;
    toHubName: string;
    loadedTeu: number;
    capacityTeu: number;
    loadFactor: number;
  }[];
}) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>열차</th>
            <th>구간</th>
            <th className={styles.right}>적재</th>
            <th className={styles.right}>적재율</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((seg, index) => (
            <tr key={`${seg.trainId}-${index}`}>
              <td className={styles.mono}>{seg.trainId}</td>
              <td className={styles.muted}>
                {seg.fromHubName} → {seg.toHubName}
              </td>
              <td className={styles.right}>
                {seg.loadedTeu} / {seg.capacityTeu} TEU
              </td>
              <td className={styles.right}>{formatPercent(seg.loadFactor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.kpi}>
      <span className={styles.kpiLabel}>{label}</span>
      <span className={styles.kpiValue}>{value}</span>
    </div>
  );
}
