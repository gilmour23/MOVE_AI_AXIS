import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ArrowRight, Leaf, Train, Truck, X } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  LoadingSkeleton,
} from '@/components/common/States';
import { SizeTag } from '@/components/optimization/SizeTag';
import { fetchTransportComparison } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useCarrierId, useMeta } from '@/app/MetaContext';
import { formatDateShort, formatNumber, formatTime, formatKrw } from '@/lib/format';
import type {
  TransportComparison,
  TransportPriority,
  TransportRow,
  TransportTotals,
} from '@/types/domain';
import styles from './TransportPage.module.css';

const PRIORITIES: { value: TransportPriority; label: string }[] = [
  { value: 'cost', label: '비용 우선' },
  { value: 'time', label: '시간 우선' },
  { value: 'carbon', label: '탄소 우선' },
];

const won = (v: number) => `₩${formatNumber(Math.round(v))}`;
const wonM = (v: number) => `₩${(v / 1_000_000).toFixed(2)}M`;
const pct = (v: number | null) => (v === null ? '-' : `${(v * 100).toFixed(1)}%`);
const hrs = (v: number | null) => (v === null ? '-' : `${v.toFixed(1)} h`);
const co2 = (v: number | null) =>
  v === null ? '-' : v >= 1000 ? `${(v / 1000).toFixed(2)} tCO₂e` : `${formatNumber(Math.round(v))} kgCO₂e`;

/** Rail vs Truck 운송 비교.
 *  Transport_index.html 의 정보구조·인터랙션을 유지하되 모든 수치는
 *  transport_comparison.json(= canonical MILP + 트럭 비교 입력)에서 읽는다. */
export function TransportPage() {
  const carrierId = useCarrierId();
  const { weekId } = useMeta();
  const [params, setParams] = useSearchParams();
  const [priority, setPriority] = useState<TransportPriority>('cost');
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const { data, loading, error, reload } = useAsync(
    (signal) =>
      carrierId ? fetchTransportComparison(carrierId, weekId, signal) : Promise.resolve(null),
    [carrierId],
  );

  // 선택 상태는 URL 에 남겨 Plan 화면에서 넘어온 rec 를 그대로 연다.
  const selectedId = params.get('rec') ?? 'ALL';
  const setSelectedId = useCallback(
    (next: string) => {
      const updated = new URLSearchParams(params);
      if (next === 'ALL') updated.delete('rec');
      else updated.set('rec', next);
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 2400);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const rows = useMemo(() => data?.rows ?? [], [data]);
  const sortedRows = useMemo(() => {
    const copy = [...rows];
    if (priority === 'cost') copy.sort((a, b) => (b.costSavingKrw ?? 0) - (a.costSavingKrw ?? 0));
    if (priority === 'time') copy.sort((a, b) => (a.railHours ?? 0) - (b.railHours ?? 0));
    if (priority === 'carbon') copy.sort((a, b) => (b.carbonSavingKg ?? 0) - (a.carbonSavingKg ?? 0));
    return copy;
  }, [rows, priority]);

  const isOverall = selectedId === 'ALL';
  const selectedRow = rows.find((r) => r.recommendationId === selectedId) ?? null;
  const drawerRow = rows.find((r) => r.recommendationId === drawerId) ?? null;

  return (
    <PageContainer
      title="운송수단 비교"
      description={
        data && !data.truckAvailable
          ? 'MOVE-AI 철도 재배치안의 추정 운임과 계획 시각입니다. 트럭 비교는 연결되지 않았습니다.'
          : 'MOVE-AI 철도 재배치안과 트럭 운송을 같은 기준으로 비교합니다.'
      }
      action={
        !data || data.truckAvailable ? (
        <div className={styles.priorityRow}>
          {PRIORITIES.map((p) => (
            <button
              key={p.value}
              type="button"
              aria-pressed={priority === p.value}
              className={[styles.priorityChip, priority === p.value ? styles.priorityActive : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => setPriority(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>
        ) : undefined
      }
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={6} height={26} />
        </Card>
      )}

      {data && data.rows.length === 0 && (
        <Card>
          <EmptyState
            title="비교할 철도 재배치안이 없습니다."
            description="현재 계획 기준으로 자사 추천이 생성되지 않았습니다."
          />
        </Card>
      )}

      {data && data.rows.length > 0 && !data.truckAvailable && (
        <>
          <InlineNotice title="트럭 비교 데이터가 연결되지 않았습니다.">
            {data.truckUnavailableReason ??
              '트럭 비교 데이터가 연결되지 않았습니다.'}{' '}
            현재는 MOVE-AI 철도 재배치안의 추정 운임과 계획 시각을 확인할 수 있습니다.
            트럭 측 값을 임의로 만들지 않습니다.
          </InlineNotice>

          <Card
            title="철도 재배치안"
            subtitle={`${data.rows.length}건 · 추정 철도운임과 계획 시각`}
          >
            <div className={styles.railOnlyScroll}>
              <table className={styles.railOnlyTable}>
                <thead>
                  <tr>
                    <th>추천 ID</th>
                    <th>구간</th>
                    <th>규격</th>
                    <th>물량</th>
                    <th>계획 출발</th>
                    <th>사용 가능</th>
                    <th>철도거리</th>
                    <th>추정 철도운임</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.recommendationId}>
                      <td>{row.recommendationId}</td>
                      <td>
                        {row.originName} → {row.destinationName}
                      </td>
                      <td>{row.size}</td>
                      <td>
                        {row.boxes}개 · {row.teu} TEU
                      </td>
                      <td>{row.departureTime}</td>
                      <td>{row.availableTime}</td>
                      <td>{row.railDistanceKm} km</td>
                      <td>{formatKrw(row.railChargeKrw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <BasisNote data={data} />
        </>
      )}

      {data && data.rows.length > 0 && data.truckAvailable && (
        <>
          <Card>
            <div className={styles.controls}>
              <select
                className={styles.select}
                value={selectedId}
                onChange={(event) => setSelectedId(event.target.value)}
                aria-label="비교할 추천 선택"
              >
                <option value="ALL">
                  전체 · 철도 추천 {data.rows.length}건
                </option>
                {rows.map((row) => (
                  <option key={row.recommendationId} value={row.recommendationId}>
                    {row.recommendationId} · {row.originName} → {row.destinationName} ·{' '}
                    {row.size}
                  </option>
                ))}
              </select>
              <StatusBadge tone={isOverall ? 'accent' : 'info'} small>
                {isOverall ? 'All recommendations' : 'Rail Recommended'}
              </StatusBadge>
            </div>
          </Card>

          <div className={styles.grid}>
            <OverviewCard row={selectedRow} totals={data.totals} />
            <ComparisonCard row={selectedRow} totals={data.totals} priority={priority} />
          </div>

          <Card
            title="철도 재배치 추천 비교"
            subtitle={`${PRIORITIES.find((p) => p.value === priority)?.label} 기준 정렬 · 행을 클릭하면 상세가 열립니다`}
          >
            <RecommendationTable
              rows={sortedRows}
              selectedId={selectedId}
              chosenId={chosenId}
              onSelect={setSelectedId}
              onOpenDetail={setDrawerId}
            />
          </Card>

          <BasisNote data={data} />
        </>
      )}

      {drawerRow && (
        <>
          <div className={styles.overlay} onClick={() => setDrawerId(null)} role="presentation" />
          <DetailDrawer
            row={drawerRow}
            chosen={chosenId === drawerRow.recommendationId}
            onClose={() => setDrawerId(null)}
            onChoose={() => {
              setChosenId(drawerRow.recommendationId);
              setToast(`${drawerRow.recommendationId} 를 검토안으로 선택했습니다.`);
            }}
          />
        </>
      )}

      {toast && <div className={styles.toast}>{toast}</div>}
    </PageContainer>
  );
}

/* ── 운송 개요 ─────────────────────────────── */

function OverviewCard({
  row,
  totals,
}: {
  row: TransportRow | null;
  totals: TransportTotals | null;
}) {
  if (!row) {
    if (!totals) return null;
    return (
      <Card
        title="전체 추천 운송 개요"
        subtitle="자사 철도 추천을 하나의 비교 화면으로 집계합니다."
      >
        <div className={styles.overviewGrid}>
          <Field label="20FT 컨테이너" value={`${totals.boxes20ft}개`} />
          <Field label="40FT 컨테이너" value={`${totals.boxes40ft}개`} />
          <Field label="총 운송 화물" value={`${totals.teu} TEU`} sub={`총 ${totals.boxes}개`} />
          <Field label="배정 열차" value={`${totals.trainIds.length}편`} sub={totals.trainIds.join(' · ')} />
        </div>
      </Card>
    );
  }

  return (
    <Card title="선택 REC 운송 개요" subtitle="출발지·도착지와 운송 화물 정보를 먼저 확인합니다.">
      <div className={styles.overviewGrid}>
        <Field label="출발지" value={row.originName} />
        <Field label="도착지" value={row.destinationName} />
        <Field
          label="운송 화물"
          value={`${row.size} × ${row.boxes}개`}
          sub={`${row.teu} TEU`}
        />
        <Field
          label="도로 기준 거리"
          value={row.roadDistanceKm !== null ? `${row.roadDistanceKm.toFixed(0)} km` : '-'}
          sub={`철도 ${row.railDistanceKm.toFixed(0)} km`}
        />
        <Field
          label="사용 가능"
          value={formatTime(row.availableTime)}
          sub={formatDateShort(row.availableTime)}
        />
        <div className={styles.field}>
          <span className={styles.fieldLabel}>배정 열차</span>
          <Link className={styles.trainLink} to={`/korail/trains?train=${row.trainId}`}>
            {row.trainId} <ArrowRight size={13} />
          </Link>
          <span className={styles.fieldSub}>
            공동 운송 {row.participatingCarrierCount}개 선사
          </span>
        </div>
      </div>
    </Card>
  );
}

function Field({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={styles.field}>
      <span className={styles.fieldLabel}>{label}</span>
      <span className={styles.fieldValue}>{value}</span>
      {sub && <span className={styles.fieldSub}>{sub}</span>}
    </div>
  );
}

/* ── Rail / Truck 비교 ─────────────────────────────── */

function ComparisonCard({
  row,
  totals,
  priority,
}: {
  row: TransportRow | null;
  totals: TransportTotals | null;
  priority: TransportPriority;
}) {
  const overall = !row;
  const railCost = row ? row.railChargeKrw : totals?.railChargeKrw ?? 0;
  const truckCost = row ? row.truckCostKrw ?? 0 : totals?.truckCostKrw ?? 0;
  const railHours = row ? row.railHours : totals?.avgRailHours ?? null;
  const truckHours = row ? row.truckHours : totals?.avgTruckHours ?? null;
  const railCo2 = row ? row.railCo2Kg ?? 0 : totals?.railCo2Kg ?? 0;
  const truckCo2 = row ? row.truckCo2Kg ?? 0 : totals?.truckCo2Kg ?? 0;
  const costSaving = row ? row.costSavingKrw ?? 0 : totals?.costSavingKrw ?? 0;
  const costRate = row ? row.costSavingRate : totals?.costSavingRate ?? null;
  const timeGap = row ? row.timeGapHours : totals?.timeGapHours ?? null;
  const carbonSaving = row ? row.carbonSavingKg ?? 0 : totals?.carbonSavingKg ?? 0;
  const carbonRate = row ? row.carbonSavingRate : totals?.carbonSavingRate ?? null;

  const chartData = [
    {
      name: '운임',
      rail: railCost / 1_000_000,
      truck: truckCost / 1_000_000,
      unit: 'M원',
      key: 'cost' as TransportPriority,
    },
    {
      name: '리드타임',
      rail: railHours ?? 0,
      truck: truckHours ?? 0,
      unit: 'h',
      key: 'time' as TransportPriority,
    },
    {
      name: '탄소배출',
      rail: railCo2 / 1000,
      truck: truckCo2 / 1000,
      unit: 't',
      key: 'carbon' as TransportPriority,
    },
  ];

  return (
    <Card
      title={overall ? '전체 운송수단 비교' : '선택 REC 운송수단 요약'}
      subtitle={
        overall
          ? '운임·탄소배출은 합계, 리드타임은 건당 평균입니다.'
          : '운임·리드타임·탄소배출을 같은 조건에서 비교합니다.'
      }
    >
      <div className={styles.modeHeader}>
        <span />
        <span className={styles.modeHeaderCell}>
          <Train size={13} /> 철도 (MOVE-AI)
        </span>
        <span className={styles.modeHeaderCell}>
          <Truck size={13} /> 트럭
        </span>
        <span className={styles.modeHeaderCell} style={{ justifyContent: 'flex-end' }}>
          차이
        </span>
      </div>

      <CompareRow
        title={overall ? '총 운임' : '운임'}
        subtitle="Estimated total cost"
        railValue={wonM(railCost)}
        railMeta={row ? row.trainId : totals?.trainIds.join(' · ')}
        truckValue={wonM(truckCost)}
        truckMeta={row?.truckVehicles ? `${row.truckVehicles}대` : undefined}
        deltaValue={wonM(costSaving)}
        deltaRate={`${pct(costRate)} 절감`}
        good
      />
      <CompareRow
        title={overall ? '건당 평균 리드타임' : '리드타임'}
        subtitle="End-to-end lead time"
        railValue={hrs(railHours)}
        railMeta={row?.railAvailableTime ? `사용 가능 ${formatTime(row.railAvailableTime)}` : undefined}
        truckValue={hrs(truckHours)}
        deltaValue={timeGap !== null ? `${timeGap > 0 ? '+' : ''}${timeGap.toFixed(1)} h` : '-'}
        deltaRate="철도 − 트럭"
        good={(timeGap ?? 0) >= 0}
      />
      <CompareRow
        title={overall ? '총 탄소배출량' : '탄소배출량'}
        subtitle="Estimated CO₂e"
        railValue={co2(railCo2)}
        truckValue={co2(truckCo2)}
        deltaValue={co2(carbonSaving)}
        deltaRate={`${pct(carbonRate)} 저감`}
        good
      />

      <div className={styles.chartWrap}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 12, right: 8, bottom: 4, left: -16 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={false}
              width={44}
            />
            <Tooltip
              cursor={{ fill: 'var(--surface-sunken)' }}
              formatter={(value: number, name: string, item) => [
                `${value.toFixed(2)} ${(item.payload as { unit: string }).unit}`,
                name === 'rail' ? '철도' : '트럭',
              ]}
              contentStyle={{
                borderRadius: 8,
                border: '1px solid var(--border)',
                fontSize: 12,
              }}
            />
            <Bar dataKey="rail" name="rail" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {chartData.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={entry.key === priority ? 'var(--brand)' : '#9dc3d2'}
                />
              ))}
            </Bar>
            <Bar dataKey="truck" name="truck" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {chartData.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={entry.key === priority ? 'var(--accent)' : '#cfc2ec'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function CompareRow({
  title,
  subtitle,
  railValue,
  railMeta,
  truckValue,
  truckMeta,
  deltaValue,
  deltaRate,
  good,
}: {
  title: string;
  subtitle: string;
  railValue: string;
  railMeta?: string;
  truckValue: string;
  truckMeta?: string;
  deltaValue: string;
  deltaRate: string;
  good?: boolean;
}) {
  return (
    <div className={styles.compareRow}>
      <div className={styles.compareLabel}>
        <span className={styles.compareTitle}>{title}</span>
        <span className={styles.compareSub}>{subtitle}</span>
      </div>
      <div className={[styles.modeCell, styles.modeCellRail].join(' ')}>
        <span className={styles.modeValue}>{railValue}</span>
        {railMeta && <span className={styles.modeMeta}>{railMeta}</span>}
      </div>
      <div className={styles.modeCell}>
        <span className={styles.modeValue}>{truckValue}</span>
        {truckMeta && <span className={styles.modeMeta}>{truckMeta}</span>}
      </div>
      <div className={styles.delta}>
        <div
          className={[styles.deltaValue, good ? styles.deltaGood : styles.deltaWarn].join(' ')}
        >
          {deltaValue}
        </div>
        <div className={styles.deltaRate}>{deltaRate}</div>
      </div>
    </div>
  );
}

/* ── 추천 목록 ─────────────────────────────── */

function RecommendationTable({
  rows,
  selectedId,
  chosenId,
  onSelect,
  onOpenDetail,
}: {
  rows: TransportRow[];
  selectedId: string;
  chosenId: string | null;
  onSelect: (id: string) => void;
  onOpenDetail: (id: string) => void;
}) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>추천</th>
            <th>구간</th>
            <th>규격·물량</th>
            <th>철도 운임</th>
            <th>트럭 운임</th>
            <th>절감</th>
            <th>탄소 저감</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.recommendationId}
              className={[
                styles.row,
                row.recommendationId === selectedId ? styles.rowActive : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => onSelect(row.recommendationId)}
            >
              <td>
                <span className={styles.recId}>{row.recommendationId}</span>
                {chosenId === row.recommendationId && (
                  <>
                    {' '}
                    <StatusBadge tone="normal" small>
                      선택
                    </StatusBadge>
                  </>
                )}
              </td>
              <td>
                {row.originName} → {row.destinationName}
              </td>
              <td>
                <SizeTag size={row.size} /> {row.boxes}개
              </td>
              <td>{won(row.railChargeKrw)}</td>
              <td>{row.truckCostKrw !== null ? won(row.truckCostKrw) : '-'}</td>
              <td className={styles.saving}>
                {row.costSavingKrw !== null ? wonM(row.costSavingKrw) : '-'}
                <div className={styles.deltaRate}>{pct(row.costSavingRate)}</div>
              </td>
              <td className={styles.saving}>{co2(row.carbonSavingKg)}</td>
              <td>
                <button
                  type="button"
                  className={styles.detailButton}
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenDetail(row.recommendationId);
                  }}
                >
                  상세
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── 상세 Drawer ─────────────────────────────── */

function DetailDrawer({
  row,
  chosen,
  onClose,
  onChoose,
}: {
  row: TransportRow;
  chosen: boolean;
  onClose: () => void;
  onChoose: () => void;
}) {
  return (
    <aside className={styles.drawer} role="dialog" aria-label={`${row.recommendationId} 상세`}>
      <header className={styles.drawerHeader}>
        <div>
          <div className={styles.drawerTitle}>{row.recommendationId} 운송 비교 상세</div>
          <div className={styles.drawerSub}>
            {row.originName} → {row.destinationName} · {row.size} {row.boxes}개
          </div>
        </div>
        <button type="button" className={styles.drawerClose} onClick={onClose} aria-label="닫기">
          <X size={17} />
        </button>
      </header>

      <div className={styles.drawerBody}>
        <section>
          <div className={styles.metricList}>
            <Metric label="배정 열차" value={row.trainId} />
            <Metric label="출발" value={`${formatDateShort(row.departureTime)} ${formatTime(row.departureTime)}`} />
            <Metric label="도착" value={`${formatDateShort(row.arrivalTime)} ${formatTime(row.arrivalTime)}`} />
            <Metric label="사용 가능" value={`${formatDateShort(row.availableTime)} ${formatTime(row.availableTime)}`} />
            <Metric label="공동 운송" value={`${row.participatingCarrierCount}개 선사`} />
            <Metric label="열차 적재율" value={pct(row.trainLoadFactor)} />
          </div>
        </section>

        <section>
          <div className={styles.metricList}>
            <Metric label="철도 운임" value={won(row.railChargeKrw)} />
            <Metric label="트럭 운임" value={row.truckCostKrw !== null ? won(row.truckCostKrw) : '-'} />
            <Metric
              label="비용 절감"
              value={row.costSavingKrw !== null ? `${won(row.costSavingKrw)} (${pct(row.costSavingRate)})` : '-'}
            />
            <Metric label="철도 리드타임" value={hrs(row.railHours)} />
            <Metric label="트럭 리드타임" value={hrs(row.truckHours)} />
            <Metric label="철도 CO₂e" value={co2(row.railCo2Kg)} />
            <Metric label="트럭 CO₂e" value={co2(row.truckCo2Kg)} />
            <Metric
              label="탄소 저감"
              value={row.carbonSavingKg !== null ? `${co2(row.carbonSavingKg)} (${pct(row.carbonSavingRate)})` : '-'}
            />
            <Metric label="철도 거리" value={`${row.railDistanceKm.toFixed(1)} km`} />
            <Metric
              label="도로 거리"
              value={row.roadDistanceKm !== null ? `${row.roadDistanceKm.toFixed(1)} km` : '-'}
            />
          </div>
        </section>

        <div className={styles.noteBox}>
          <Leaf size={12} style={{ verticalAlign: -1 }} /> 철도 리드타임은 출발역 상차 시작(
          {formatTime(row.railLoadStartTime)}) → 도착역 사용 가능(
          {formatTime(row.railAvailableTime)}) 기준이며, 트럭도 상·하차를 포함한 end-to-end
          기준으로 비교합니다. 철도 거리와 도로 거리는 서로 다른 경로 기준입니다.
        </div>

        <button
          type="button"
          className={[styles.selectButton, chosen ? styles.selectButtonChosen : '']
            .filter(Boolean)
            .join(' ')}
          onClick={onChoose}
        >
          {chosen ? '검토안으로 선택됨' : 'Rail안 검토 대상으로 선택'}
        </button>
        <div className={styles.noteBox}>
          이 선택은 화면 내 검토 표시입니다. 최적화 결과나 열차 배정을 변경하지 않습니다.
        </div>
      </div>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metricRow}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue}>{value}</span>
    </div>
  );
}

function BasisNote({ data }: { data: TransportComparison }) {
  return (
    <Card>
      <div className={styles.noteBox}>
        <strong>비교 기준</strong>
        <br />
        철도 운임·수량·시각·열차는 MOVE-AI MILP 결과({data.basis.railCostSource})에서 읽습니다.
        철도 리드타임은 {data.basis.rail} 기준입니다.
        <br />
        트럭 비용·소요시간·CO₂ 및 도로거리는 {data.basis.truckSource} 의 비교 산출자료이며,
        철도 측 값과 충돌하면 MILP 결과가 우선합니다.
        {data.missingTruckComparison.length > 0 && (
          <>
            <br />
            트럭 비교값이 없는 추천: {data.missingTruckComparison.join(', ')}
          </>
        )}
      </div>
    </Card>
  );
}
