import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
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
import { formatRoute } from '@/config/hubMeta';
import type { KorailHub } from '@/types/domain';
import { statusTone } from './statusTone';
import styles from './Korail.module.css';

/** 재배치 결과 기준 거점 우선순위.
 *  0 부족 잔존 · 1 부족 해소 · 2 정상 — 상태 문자열이 아니라 수치에서 판정한다. */
function shortageRank(hub: KorailHub): number {
  if (hub.postRailStockout > 0) return 0;
  if (hub.baselineStockout > 0) return 1;
  return 2;
}

/** KORAIL 종합 대시보드.
 *  "얼마나 배정됐고 무엇이 미배정인가 / 어떤 열차가 몇 편 선정됐나 /
 *   용량을 얼마나 쓰고 있나 / 재배치 후에도 어디가 부족한가" 에 답한다. */
export function KorailOverviewPage() {
  const { meta } = useMeta();
  const [trainId, setTrainId] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailOverview(signal), []);

  /** 부족 잔존 거점 수 — 새 API 를 만들지 않고 hubs 에서 계산한다. */
  const residualShortageHubCount = useMemo(
    () => (data ? data.hubs.filter((hub) => hub.postRailStockout > 0).length : 0),
    [data],
  );

  /** 부족 잔존 거점이 먼저 보이도록 정렬한다. 원본 배열은 mutate 하지 않는다. */
  const sortedHubs = useMemo(() => {
    if (!data) return [];
    return [...data.hubs].sort(
      (a, b) =>
        shortageRank(a) - shortageRank(b) ||
        b.postRailStockout - a.postRailStockout ||
        b.baselineStockout - a.baselineStockout,
    );
  }, [data]);

  return (
    <PageContainer
      title="종합 대시보드"
      description="공컨테이너 전용 열차 운영 현황과 거점 수급을 한 화면에서 확인합니다."
      action={
        meta?.isPrototypeTimetable ? (
          <StatusBadge
            tone="neutral"
            small
            title="KORAIL 확정 운행시각이 아니라 프로토타입 운행후보 기준 시각입니다."
          >
            프로토타입 운행계획
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
            <Kpi
              label="철도 배정량"
              value={`${formatNumber(data.railServedTeu)} TEU`}
              sub={`커버리지 ${formatPercent(data.railCoverage)}`}
            />
            <Kpi
              label="미배정량"
              value={`${formatNumber(data.railUnservedTeu)} TEU`}
              sub={`총 수송 필요량 ${formatNumber(data.serviceNeedTeu)} TEU`}
              to="/korail/needs?status=미배정"
            />
            <Kpi label="선정 열차" value={`${data.selectedTrainCount}편`} to="/korail/trains" />
            <Kpi label="평균 적재율" value={formatPercent(data.avgLoadFactor)} />
            <Kpi
              label="부족 잔존 거점"
              value={`${residualShortageHubCount}곳`}
              sub={`전체 ${data.hubs.length}개 거점`}
              to="/korail/inventory"
            />
          </div>

          <div className={styles.grid2}>
            <Card title="6거점 철도 운영 네트워크" subtitle="운영 관계를 단순화한 노선도입니다">
              <KorailNetwork
                hubs={data.hubs}
                trains={data.trains}
                selectedTrainId={trainId}
                onSelectTrain={setTrainId}
              />
            </Card>

            <Card title="거점 수급 현황" subtitle="재배치 후에도 부족이 남은 거점을 먼저 표시합니다">
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
                    {sortedHubs.map((hub) => (
                      <tr key={hub.hubCode}>
                        <td>
                          <Link
                            className={styles.carrierLink}
                            to={`/korail/inventory?hub=${hub.hubCode}`}
                          >
                            {hub.hubName}
                          </Link>
                        </td>
                        <td className={styles.right}>{hub.baselineStockout}</td>
                        <td className={styles.right}>{hub.postRailStockout}</td>
                        <td className={styles.right}>{hub.stockoutReduction}</td>
                        <td>
                          <StatusBadge tone={statusTone(hub.status)} small>
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

          <Card
            title="선정 열차"
            subtitle="행을 클릭하면 상세 운행계획이 열립니다"
            action={
              <span className={styles.cardMeta}>
                총 공컨 {formatNumber(data.totalBoxes)}개 · 참여 선사{' '}
                {data.participatingCarrierCount}개
              </span>
            }
          >
            <div className={styles.scroll}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>열차</th>
                    <th>노선</th>
                    <th>출발</th>
                    <th className={styles.right}>배정 / 용량</th>
                    <th className={styles.right}>적재율</th>
                    <th className={styles.right}>참여 선사</th>
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
                      <td className={styles.muted}>{formatRoute(train.route)}</td>
                      <td>{formatTime(train.departureTime)}</td>
                      <td className={styles.right}>
                        {train.assignedTeu} / {train.capacityTeu} TEU
                      </td>
                      <td className={styles.right}>{formatPercent(train.loadFactor)}</td>
                      <td className={styles.right}>{train.participatingCarrierCount}개</td>
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

function Kpi({
  label,
  value,
  sub,
  to,
}: {
  label: string;
  value: string;
  sub?: string;
  /** 지정하면 해당 상세 화면으로 이동하는 KPI 가 된다. */
  to?: string;
}) {
  const body = (
    <>
      <span className={styles.kpiLabel}>{label}</span>
      <span className={styles.kpiValue}>{value}</span>
      {sub && <span className={styles.kpiSub}>{sub}</span>}
    </>
  );

  if (to) {
    return (
      <Link className={[styles.kpi, styles.kpiLink].join(' ')} to={to}>
        {body}
      </Link>
    );
  }

  return <div className={styles.kpi}>{body}</div>;
}
