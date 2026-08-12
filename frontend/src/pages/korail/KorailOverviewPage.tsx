import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { ErrorState, LoadingSkeleton } from '@/components/common/States';
import { KorailNetwork } from './KorailNetwork';
import { TrainDetailDrawer } from './TrainDetailDrawer';
import { fetchKorailInsights, fetchKorailOverview } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatNumber, formatPercent, formatTime } from '@/lib/format';
import { formatRoute } from '@/config/hubMeta';
import type { ContainerSize, KorailHub } from '@/types/domain';
import { statusTone } from './statusTone';
import styles from './Korail.module.css';

const SIZES: ContainerSize[] = ['20FT', '40FT'];

/** 재배치 결과 기준 거점 우선순위.
 *  0 부족 잔존 · 1 부족 해소 · 2 정상 — 상태 문자열이 아니라 수치에서 판정한다. */
function shortageRank(hub: KorailHub): number {
  if (hub.postRailStockout > 0) return 0;
  if (hub.baselineStockout > 0) return 1;
  return 2;
}

/** 잔존 부족이 가장 큰 규격. 재고 화면이 기본값(20FT)으로 열려
 *  실제 부족이 남은 규격을 놓치지 않도록 deep-link 에 함께 넘긴다.
 *  잔존 부족이 없으면 규격을 강제하지 않는다. */
function residualShortageSize(hub: KorailHub): ContainerSize | null {
  if (hub.postRailStockout <= 0) return null;
  return SIZES.reduce((best, size) => {
    const a = hub.sizes[size];
    const b = hub.sizes[best];
    if (a.postRailStockout > b.postRailStockout) return size;
    if (
      a.postRailStockout === b.postRailStockout &&
      a.baselineStockout > b.baselineStockout
    ) {
      return size;
    }
    return best;
  });
}

function inventoryLink(hub: KorailHub): string {
  const size = residualShortageSize(hub);
  return size
    ? `/korail/inventory?hub=${hub.hubCode}&size=${size}`
    : `/korail/inventory?hub=${hub.hubCode}`;
}

/** KORAIL 종합 대시보드.
 *  "얼마나 배정됐고 무엇이 미배정인가 / 어떤 열차가 몇 편 선정됐나 /
 *   용량을 얼마나 쓰고 있나 / 재배치 후에도 어디가 부족한가" 에 답한다. */
export function KorailOverviewPage() {
  const { meta } = useMeta();
  const [trainId, setTrainId] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailOverview(signal), []);
  // 최대 구간 적재율은 기존 분석 결과를 그대로 읽는다 (새 계산을 만들지 않는다).
  const { data: insights } = useAsync((signal) => fetchKorailInsights(signal), []);

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

  const peakSegment = insights?.highestLoadSegments?.[0] ?? null;

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
          {/* KPI 는 배정 / 운행 / 수급 세 범주로 읽히게 한다.
              범주마다 다른 컬러 카드를 만들지 않고 간격과 label 로만 구분한다. */}
          <div className={styles.kpiGroups}>
            <KpiGroup label="배정">
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
            </KpiGroup>

            <KpiGroup label="운행">
              <Kpi label="선정 열차" value={`${data.selectedTrainCount}편`} to="/korail/trains" />
              <Kpi
                label="평균 적재율"
                value={formatPercent(data.avgLoadFactor)}
                sub={
                  peakSegment ? `최대 구간 ${formatPercent(peakSegment.loadFactor)}` : undefined
                }
              />
            </KpiGroup>

            <KpiGroup label="수급">
              <Kpi
                label="부족 잔존 거점"
                value={`${residualShortageHubCount}곳`}
                sub={`전체 ${data.hubs.length}개 거점`}
                to="/korail/inventory"
              />
            </KpiGroup>
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
                          {/* 잔존 부족이 있는 거점은 그 부족이 남은 규격으로 연결한다. */}
                          <Link className={styles.carrierLink} to={inventoryLink(hub)}>
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

          {/* 용량 여유가 가장 작은 구간. 높은 적재율을 병목·위험으로 단정하지 않는다. */}
          {peakSegment && (
            <div className={styles.peakStrip}>
              <span className={styles.peakLabel}>최대 구간 적재율</span>
              <span className={styles.peakValue}>{formatPercent(peakSegment.loadFactor)}</span>
              <span className={styles.peakDetail}>
                <span className={styles.mono}>{peakSegment.trainId}</span>{' '}
                {peakSegment.fromHubName} → {peakSegment.toHubName}
              </span>
              <span className={styles.peakRemain}>
                잔여 {peakSegment.capacityTeu - peakSegment.loadedTeu} TEU
              </span>
            </div>
          )}

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

function KpiGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.kpiGroup}>
      <span className={styles.kpiGroupLabel}>{label}</span>
      <div className={styles.kpiStrip}>{children}</div>
    </div>
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
