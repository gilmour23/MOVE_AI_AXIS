import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  LoadingSkeleton,
} from '@/components/common/States';
import { RailHubMap } from '@/components/map/RailHubMap';
import { SizeTag } from '@/components/optimization/SizeTag';
import { fetchOverview, fetchTransportComparison } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatBoxes, formatDateShort, formatTime } from '@/lib/format';
import type { CarrierRecommendation, ContainerSize, OverviewHub } from '@/types/domain';
import styles from './OverviewPage.module.css';

const SIZES: ContainerSize[] = ['20FT', '40FT'];

export function OverviewPage() {
  const { weekMeta, carrierId, weekId } = useMeta();
  const navigate = useNavigate();
  const [selectedHub, setSelectedHub] = useState<string | null>(null);

  const { data, loading, error, reload } = useAsync(
    (signal) => (carrierId ? fetchOverview(carrierId, weekId, signal) : Promise.resolve(null)),
    [carrierId],
  );

  const transport = useAsync(
    (signal) =>
      carrierId ? fetchTransportComparison(carrierId, weekId, signal) : Promise.resolve(null),
    [carrierId],
  );

  return (
    <PageContainer
      title="Overview"
      description="이번 주 자사 공컨 재고 위험과 MOVE-AI 재배치 권고를 한눈에 확인합니다."
    >
      {weekMeta && !weekMeta.allStagesProvenOptimal && (
        <InlineNotice title="최적화 결과가 최적해로 증명되지 않았습니다." danger>
          SUMMARY.json 의 all_stages_proven_optimal 값이 true 가 아닙니다. 아래 수치는
          참고용으로만 사용해주세요.
        </InlineNotice>
      )}

      {error && <ErrorState error={error} onRetry={reload} />}

      <div className={styles.topGrid}>
        <Card
          title="거점 및 철도 네트워크"
          subtitle="거점을 클릭하면 규격별 부족 현황을 확인할 수 있습니다."
        >
          {loading && <LoadingSkeleton rows={8} height={26} />}
          {data && (
            <RailHubMap
              hubs={data.hubs}
              selectedHub={selectedHub}
              onSelectHub={setSelectedHub}
            />
          )}
        </Card>

        <div className={styles.rightColumn}>
          <Card
            title="전체 거점별 공컨 재고 현황"
            subtitle="재배치 전 · 주말 예상재고(개)"
          >
            {loading && <LoadingSkeleton rows={6} height={22} />}
            {data && (
              <div className={styles.hubList}>
                {data.hubs.map((hub) => (
                  <HubRow
                    key={hub.hubCode}
                    hub={hub}
                    onClick={() => setSelectedHub(hub.hubCode)}
                  />
                ))}
              </div>
            )}
          </Card>

          <Card title="철도·트럭 운송 비교" subtitle="자사 추천 전체 합계">
            <div className={styles.comparisonPlaceholder}>
              {transport.loading && <LoadingSkeleton rows={3} height={20} />}
              {transport.data?.totals && (
                <>
                  <div className={styles.comparisonStats}>
                    <ComparisonStat
                      label="비용 절감"
                      value={`₩${(transport.data.totals.costSavingKrw / 1_000_000).toFixed(1)}M`}
                      sub={`${((transport.data.totals.costSavingRate ?? 0) * 100).toFixed(1)}% 절감`}
                    />
                    <ComparisonStat
                      label="탄소 저감"
                      value={`${(transport.data.totals.carbonSavingKg / 1000).toFixed(2)} t`}
                      sub={`${((transport.data.totals.carbonSavingRate ?? 0) * 100).toFixed(1)}% 저감`}
                    />
                  </div>
                  <p className={styles.comparisonText}>
                    철도 리드타임은 트럭 대비 건당 평균{' '}
                    {Math.abs(transport.data.totals.timeGapHours).toFixed(1)}시간
                    {transport.data.totals.timeGapHours < 0 ? ' 더 걸립니다' : ' 짧습니다'}.
                  </p>
                </>
              )}
              <Link className={styles.comparisonLink} to="/carrier/transport">
                상세 비교 <ArrowRight size={14} />
              </Link>
            </div>
          </Card>
        </div>
      </div>

      <Card
        title="이번 주 MOVE-AI 재배치 권고"
        subtitle="출발시간 순 · 자사 물량 기준"
      >
        {loading && <LoadingSkeleton rows={3} height={56} />}
        {data && data.recommendationPreview.length === 0 && (
          <EmptyState
            title="이번 주 철도 재배치 권고가 없습니다."
            description="현재 계획 기준으로 추천 가능한 철도 재배치안이 생성되지 않았습니다."
          />
        )}
        {data && data.recommendationPreview.length > 0 && (
          <>
            <div className={styles.previewList}>
              {data.recommendationPreview.map((rec) => (
                <RecommendationPreviewCard
                  key={rec.recommendationId}
                  rec={rec}
                  onClick={() =>
                    navigate(`/carrier/plan#${rec.recommendationId}`)
                  }
                />
              ))}
            </div>
            <div className={styles.previewFooter}>
              <span className={styles.previewCount}>
                전체 {data.recommendationTotalCount}건 중{' '}
                {data.recommendationPreview.length}건 표시
              </span>
              <Link className={styles.previewAll} to="/carrier/plan">
                공컨 최적화에서 전체 보기 <ArrowRight size={14} />
              </Link>
            </div>
          </>
        )}
      </Card>
    </PageContainer>
  );
}

function ComparisonStat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className={styles.comparisonStat}>
      <span className={styles.comparisonStatLabel}>{label}</span>
      <span className={styles.comparisonStatValue}>{value}</span>
      <span className={styles.comparisonStatSub}>{sub}</span>
    </div>
  );
}

function HubRow({ hub, onClick }: { hub: OverviewHub; onClick: () => void }) {
  return (
    <div className={styles.hubRow} onClick={onClick} role="presentation">
      <span className={styles.hubName}>{hub.hubName}</span>
      <span className={styles.hubValues}>
        {SIZES.map((size) => {
          const state = hub.sizes[size];
          return (
            <span key={size} className={styles.sizeValue}>
              <span className={styles.sizeLabel}>{size}</span>
              <span
                className={[
                  styles.sizeNumber,
                  state.weekEndInventory === 0 ? styles.sizeZero : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                {state.weekEndInventory}
              </span>
            </span>
          );
        })}
      </span>
      <span className={styles.badgeSlot}>
        {hub.hasShortage && (
          <StatusBadge tone="shortage" small>
            부족 예상
          </StatusBadge>
        )}
      </span>
    </div>
  );
}

function RecommendationPreviewCard({
  rec,
  onClick,
}: {
  rec: CarrierRecommendation;
  onClick: () => void;
}) {
  return (
    <button type="button" className={styles.previewCard} onClick={onClick}>
      <span className={styles.previewRoute}>
        {rec.originName}
        <ArrowRight size={14} className={styles.previewArrow} />
        {rec.destinationName}
      </span>
      <span className={styles.previewMeta}>
        <SizeTag size={rec.size} />
        <span className={styles.previewQty}>{formatBoxes(rec.quantityBoxes)}</span>
      </span>
      <span className={styles.previewTimes}>
        {formatDateShort(rec.departureTime)} {formatTime(rec.departureTime)} 출발 →{' '}
        {formatTime(rec.arrivalTime)} 도착
        <br />
        <span className={styles.previewAvailable}>
          사용 가능 {formatTime(rec.availableTime)}
        </span>
      </span>
    </button>
  );
}
