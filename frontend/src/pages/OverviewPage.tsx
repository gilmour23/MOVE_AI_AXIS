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
import { fetchOverview } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatBoxes, formatDateShort, formatTime } from '@/lib/format';
import type { CarrierRecommendation, ContainerSize, OverviewHub } from '@/types/domain';
import styles from './OverviewPage.module.css';

const SIZES: ContainerSize[] = ['20FT', '40FT'];

export function OverviewPage() {
  const { meta, carrierId } = useMeta();
  const navigate = useNavigate();
  const [selectedHub, setSelectedHub] = useState<string | null>(null);

  const { data, loading, error, reload } = useAsync(
    (signal) => (carrierId ? fetchOverview(carrierId, signal) : Promise.resolve(null)),
    [carrierId],
  );

  return (
    <PageContainer
      title="Overview"
      description="이번 주 자사 공컨 재고 위험과 MOVE-AI 재배치 권고를 한눈에 확인합니다."
    >
      {meta && !meta.allStagesProvenOptimal && (
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

          {/* 이 영역은 다른 팀원 담당. 비교 숫자를 임의로 만들지 않는다 (§15.3) */}
          <Card title="철도·트럭 운송 비교">
            <div className={styles.comparisonPlaceholder}>
              <StatusBadge tone="neutral" small>
                준비 중
              </StatusBadge>
              <p className={styles.comparisonText}>
                철도와 트럭의 비용·시간·탄소 비교는 별도 화면에서 제공될 예정입니다.
              </p>
              <Link className={styles.comparisonLink} to="/comparison">
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
                    navigate(`/optimization#${rec.recommendationId}`)
                  }
                />
              ))}
            </div>
            <div className={styles.previewFooter}>
              <span className={styles.previewCount}>
                전체 {data.recommendationTotalCount}건 중{' '}
                {data.recommendationPreview.length}건 표시
              </span>
              <Link className={styles.previewAll} to="/optimization">
                공컨 최적화에서 전체 보기 <ArrowRight size={14} />
              </Link>
            </div>
          </>
        )}
      </Card>
    </PageContainer>
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
