import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import {
  ErrorState,
  InlineNotice,
  LoadingSkeleton,
  TableSkeleton,
} from '@/components/common/States';
import { ServiceNeedTable } from '@/components/optimization/ServiceNeedTable';
import { RecommendationTable } from '@/components/optimization/RecommendationTable';
import { InventoryImpactTable } from '@/components/optimization/InventoryImpactTable';
import { UnservedPanel } from '@/components/optimization/UnservedPanel';
import { RecommendationExplanationPanel } from '@/components/optimization/RecommendationExplanation';
import { InventorySection } from '@/components/inventory/InventorySection';
import { fetchOptimization } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatKrw, formatNumber, formatPercent } from '@/lib/format';
import { hubFullName } from '@/config/hubMeta';
import type { ContainerSize } from '@/types/domain';
import styles from './OptimizationPage.module.css';

/** PDF 3~4페이지는 하나의 긴 scroll 페이지다 (핸드오프 §17). */
export function OptimizationPage() {
  const { weekMeta, carrierId, weekId } = useMeta();
  const [params, setParams] = useSearchParams();
  const location = useLocation();

  const hubFilter = params.get('hub');
  const size = (params.get('size') as ContainerSize | null) ?? '20FT';
  const postRailHub = params.get('posthub') ?? hubFilter;

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);

  const { data, loading, error, reload } = useAsync(
    (signal) =>
      carrierId ? fetchOptimization(carrierId, weekId, signal) : Promise.resolve(null),
    [carrierId, weekId],
  );

  // Overview 의 preview row 클릭 → /optimization#REC0004 로 진입 시 해당 행을 펼치고 강조한다.
  useEffect(() => {
    const target = location.hash.replace('#', '');
    if (!target || !data) return;
    setExpandedId(target);
    setHighlightId(target);
    const element = document.getElementById(target);
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const timer = window.setTimeout(() => setHighlightId(null), 2800);
    return () => window.clearTimeout(timer);
  }, [location.hash, data]);

  const setSize = useCallback(
    (next: ContainerSize) => {
      const updated = new URLSearchParams(params);
      updated.set('size', next);
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  const setPostRailHub = useCallback(
    (next: string) => {
      const updated = new URLSearchParams(params);
      updated.set('posthub', next);
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  const clearHubFilter = useCallback(() => {
    const updated = new URLSearchParams(params);
    updated.delete('hub');
    setParams(updated, { replace: true });
  }, [params, setParams]);

  const summary = data?.serviceSummary ?? null;
  // 운임 합계는 추천 행에서 더한다. 별도 총계 필드를 만들지 않는다.
  const railChargeTotal = (data?.recommendations ?? []).reduce(
    (total, rec) => total + rec.estimatedRailChargeKrw,
    0,
  );

  return (
    <PageContainer
      title="재배치안"
      description="MOVE-AI가 자사 공컨을 어디서 어디로 몇 개, 어떤 계획열차에 배정했는지 보여줍니다."
      action={
        weekMeta?.isPrototypeTimetable ? (
          <StatusBadge
            tone="neutral"
            small
            title="candidate_timetable_source = PROTOTYPE_SYNTHETIC"
          >
            프로토타입 운행후보 기준
          </StatusBadge>
        ) : undefined
      }
    >
      {weekMeta && !weekMeta.allStagesProvenOptimal && (
        <InlineNotice title="최적화 결과가 최적해로 증명되지 않았습니다." danger>
          SUMMARY.json 의 all_stages_proven_optimal 값이 true 가 아닙니다.
        </InlineNotice>
      )}

      {error && <ErrorState error={error} onRetry={reload} />}

      {summary && (
        <div className={styles.summaryStrip}>
          <SummaryItem
            label="자사 Service Need"
            value={`${formatNumber(summary.serviceNeedTeu)}TEU`}
            sub="철도 재배치가 필요한 총량"
          />
          <SummaryItem
            label="철도 배정"
            value={`${formatNumber(summary.railServedTeu)}TEU`}
            sub={`커버리지 ${formatPercent(summary.railCoverage)}`}
          />
          <SummaryItem
            label="미배정"
            value={`${formatNumber(summary.railUnservedTeu)}TEU`}
            sub="철도로 해결되지 않은 잔여량"
          />
          <SummaryItem
            label="재배치 제안"
            value={`${formatNumber(summary.recommendationCount)}건`}
            sub={`열차 ${formatNumber(summary.assignedTrainCount)}편`}
          />
          <SummaryItem
            label="추정 철도운임"
            value={formatKrw(railChargeTotal)}
            sub="MILP 추정치 · 매출이 아님"
          />
        </div>
      )}

      {/* Section A */}
      <Section
        index="A"
        title="재배치 필요 현황"
        description="자사 Service Need를 거점·규격·요일로 집계했습니다."
        action={
          hubFilter && (
            <span className={styles.filterNote}>
              {hubFullName(hubFilter)} 강조 중
              <button type="button" className={styles.clearFilter} onClick={clearHubFilter}>
                해제
              </button>
            </span>
          )
        }
      >
        <Card>
          {loading && <TableSkeleton rows={5} columns={4} />}
          {data && <ServiceNeedTable rows={data.needs} highlightHub={hubFilter} />}
        </Card>
      </Section>

      {/* Section B */}
      <Section
        index="B"
        title="철도 기반 공컨 재배치 제안"
        description="행을 클릭하면 열차 경로와 자사 상·하차 물량을 볼 수 있습니다."
      >
        <Card>
          {loading && <TableSkeleton rows={5} columns={6} />}
          {data && carrierId && (
            <RecommendationTable
              carrierId={carrierId}
              rows={data.recommendations}
              expandedId={expandedId}
              highlightId={highlightId}
              onToggle={(id) => setExpandedId((current) => (current === id ? null : id))}
            />
          )}
        </Card>
      </Section>

      {/* Section C */}
      <Section
        index="C"
        title="거점별 재배치 영향"
        description="최저재고는 재고 화면과 동일한 요일별 마감 재고 기준입니다."
      >
        <Card>
          {loading && <TableSkeleton rows={6} columns={6} />}
          {data && <InventoryImpactTable rows={data.impacts} highlightHub={hubFilter} />}
        </Card>
      </Section>

      {/* Section D */}
      <Section
        index="D"
        title="재배치 이후 예상 재고 현황"
        description="재배치를 반영한 뒤의 요일별 예상 재고입니다. 잔여 부족이 있으면 그대로 표시됩니다."
      >
        {loading && (
          <Card>
            <LoadingSkeleton rows={6} height={24} />
          </Card>
        )}
        {carrierId && data && (
          <InventorySection
            carrierId={carrierId}
            mode="postRail"
            size={size}
            onSelectSize={setSize}
            selectedHub={postRailHub}
            onSelectHub={setPostRailHub}
            matrixSubtitle="재배치 후 · 각 요일 마지막 시각의 예상 재고(개)"
          />
        )}
      </Section>

      {/* Section E */}
      <Section
        index="E"
        title="왜 이 추천인가"
        description="결과 파일에 기록된 연결 수요와 출발거점 가용량입니다. 최적화 인과증명이 아닙니다."
      >
        {loading && (
          <Card>
            <LoadingSkeleton rows={3} height={24} />
          </Card>
        )}
        {data && <RecommendationExplanationPanel rows={data.explanations} />}
      </Section>

      {/* Section F */}
      <Section
        index="F"
        title="미배정 수요"
        description="철도로 배정되지 못한 자사 수요입니다. 사유는 모델 진단 분류이며 확정 원인이 아닙니다."
      >
        <Card>
          {loading && <TableSkeleton rows={4} columns={6} />}
          {data && <UnservedPanel rows={data.unserved} />}
        </Card>
      </Section>
    </PageContainer>
  );
}

function Section({
  index,
  title,
  description,
  action,
  children,
}: {
  index: string;
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <div>
          <div className={styles.sectionTitleWrap}>
            <span className={styles.sectionIndex}>{index}</span>
            <h2 className={styles.sectionTitle}>{title}</h2>
          </div>
          {description && <p className={styles.sectionDesc}>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function SummaryItem({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className={styles.summaryItem}>
      <span className={styles.summaryLabel}>{label}</span>
      <span className={styles.summaryValue}>{value}</span>
      {sub && <span className={styles.summarySub}>{sub}</span>}
    </div>
  );
}
