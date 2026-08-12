import { useState } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { KorailNetwork } from './KorailNetwork';
import { TrainDetailDrawer } from './TrainDetailDrawer';
import { fetchKorailOverview } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatNumber, formatPercent, formatTime } from '@/lib/format';
import styles from './Korail.module.css';

/** KORAIL 종합 대시보드.
 *  "어디가 부족한가 / 어떤 열차가 선정됐나 / 얼마나 적재됐나 /
 *   어떤 선사가 공동 이용하나 / 어느 거점 작업이 많은가" 에 답한다. */
export function KorailOverviewPage() {
  const { meta } = useMeta();
  const [trainId, setTrainId] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailOverview(signal), []);

  return (
    <PageContainer
      title="종합 대시보드"
      description="공컨테이너 전용 열차 운영 현황과 거점 수급을 한 화면에서 확인합니다."
      action={
        meta?.isPrototypeTimetable ? (
          <StatusBadge tone="neutral" small>
            프로토타입 운행후보 기준
          </StatusBadge>
        ) : undefined
      }
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={5} height={26} />
        </Card>
      )}

      {data && (
        <>
          <div className={styles.kpiStrip}>
            <Kpi label="Rail Served" value={`${formatNumber(data.railServedTeu)} TEU`} sub={`커버리지 ${formatPercent(data.railCoverage)}`} />
            <Kpi label="Rail Unserved" value={`${formatNumber(data.railUnservedTeu)} TEU`} sub={`Service Need ${data.serviceNeedTeu} TEU`} />
            <Kpi label="선정 열차" value={`${data.selectedTrainCount}편`} sub={`평균 적재율 ${formatPercent(data.avgLoadFactor)}`} />
            <Kpi label="총 공컨 박스" value={`${formatNumber(data.totalBoxes)}개`} sub={`20FT ${data.boxes20ft} · 40FT ${data.boxes40ft}`} />
            <Kpi label="참여 선사" value={`${data.participatingCarrierCount}개`} sub={`열차당 평균 ${data.avgCarriersPerTrain.toFixed(1)}개`} />
          </div>

          <div className={styles.grid2}>
            <Card title="6거점 철도 운영 네트워크" subtitle="선정 열차와 거점 수급 상태">
              <KorailNetwork
                hubs={data.hubs}
                trains={data.trains}
                selectedTrainId={trainId}
                onSelectTrain={setTrainId}
              />
            </Card>

            <Card title="부족 위험 거점" subtitle="재배치 전후 부족 박스 비교">
              <div className={styles.scroll}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>거점</th>
                      <th className={styles.right}>재배치 전 부족</th>
                      <th className={styles.right}>재배치 후 부족</th>
                      <th className={styles.right}>감소</th>
                      <th>상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.hubs.map((hub) => (
                      <tr key={hub.hubCode}>
                        <td>{hub.hubName}</td>
                        <td className={styles.right}>{hub.baselineStockout}</td>
                        <td className={styles.right}>{hub.postRailStockout}</td>
                        <td className={styles.right}>{hub.stockoutReduction}</td>
                        <td>
                          <StatusBadge
                            tone={
                              hub.status === '정상'
                                ? 'normal'
                                : hub.status === '부족 해소'
                                  ? 'info'
                                  : 'shortage'
                            }
                            small
                          >
                            {hub.status}
                          </StatusBadge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <Card title="선정 열차" subtitle="행을 클릭하면 상세 운행계획이 열립니다">
            <div className={styles.scroll}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>열차</th>
                    <th>노선</th>
                    <th>출발</th>
                    <th className={styles.right}>배정/Capacity</th>
                    <th className={styles.right}>적재율</th>
                    <th className={styles.right}>선사</th>
                    <th className={styles.right}>컨테이너</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trains.map((train) => (
                    <tr
                      key={train.trainId}
                      className={[
                        styles.rowClickable,
                        train.trainId === trainId ? styles.rowActive : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      onClick={() => setTrainId(train.trainId)}
                    >
                      <td className={styles.mono}>{train.trainId}</td>
                      <td className={styles.muted}>{train.route}</td>
                      <td>{formatTime(train.departureTime)}</td>
                      <td className={styles.right}>
                        {train.assignedTeu} / {train.capacityTeu} TEU
                      </td>
                      <td className={styles.right}>{formatPercent(train.loadFactor)}</td>
                      <td className={styles.right}>{train.participatingCarrierCount}</td>
                      <td className={styles.right}>
                        {train.totalBoxes}개
                        <div className={styles.kpiSub}>
                          20FT {train.boxes20ft} · 40FT {train.boxes40ft}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {trainId && <TrainDetailDrawer trainId={trainId} onClose={() => setTrainId(null)} />}
    </PageContainer>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={styles.kpi}>
      <span className={styles.kpiLabel}>{label}</span>
      <span className={styles.kpiValue}>{value}</span>
      {sub && <span className={styles.kpiSub}>{sub}</span>}
    </div>
  );
}
