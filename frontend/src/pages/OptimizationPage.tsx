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
import { InventorySection } from '@/components/inventory/InventorySection';
import { fetchOptimization } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatNumber, formatPercent } from '@/lib/format';
import { hubFullName } from '@/config/hubMeta';
import type { ContainerSize } from '@/types/domain';
import styles from './OptimizationPage.module.css';

/** PDF 3~4페이지는 하나의 긴 scroll 페이지다 (핸드오프 §17). */
export function OptimizationPage() {
  const { meta, carrierId } = useMeta();
  const [params, setParams] = useSearchParams();
  const location = useLocation();

  const hubFilter = params.get('hub');
  const size = (params.get('size') as ContainerSize | null) ?? '20FT';
  const postRailHub = params.get('posthub') ?? hubFilter;

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);

  const { data, loading, error, reload } = useAsync(
    (signal) =>
      carrierId ? fetchOptimization(carrierId, signal) : Promise.resolve(null),
    [carrierId],
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

  return (
    <PageContainer
      title="공컨 최적화"
      description="MOVE-AI MILP가 계산한 자사 철도 기반 공컨 재배치 제안과 그 영향입니다."
      action={
        meta?.isPrototypeTimetable ? (
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
      {meta && !meta.allStagesProvenOptimal && (
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
