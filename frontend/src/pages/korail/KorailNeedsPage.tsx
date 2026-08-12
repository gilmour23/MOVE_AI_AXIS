import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailNeeds } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { formatNumber } from '@/lib/format';
import type { KorailNeedRow } from '@/types/domain';
import { statusTone } from './statusTone';
import styles from './Korail.module.css';

/** 미배정 건을 먼저 보이게 하는 정렬 순서. */
const STATUS_ORDER = ['미배정', '부분 배정', '배정 완료'];

function statusRank(status: string): number {
  const index = STATUS_ORDER.indexOf(status);
  return index === -1 ? STATUS_ORDER.length : index;
}

const ALL = 'ALL';

interface Filters {
  carrier: string;
  hub: string;
  size: string;
  date: string;
  status: string;
}

/** 중복 없는 옵션 목록을 만든다. */
function distinct<T>(rows: KorailNeedRow[], pick: (row: KorailNeedRow) => T): T[] {
  return Array.from(new Set(rows.map(pick)));
}

/** 철도 서비스 수요·배정 현황.
 *  SERVICE_NEED_RESULT 는 일반 예약 DB 가 아니라 선사별 철도 서비스 필요량 +
 *  배정 여부이므로 화면명을 그에 맞춰 표기한다.
 *
 *  필터·정렬은 모두 client-side 다. 이미 row 에 있는 값만 쓰므로
 *  새로운 backend selector 나 JSON 파일을 만들지 않는다. */
export function KorailNeedsPage() {
  const [params] = useSearchParams();
  const { data, loading, error, reload } = useAsync((signal) => fetchKorailNeeds(signal), []);

  // 대시보드 '미배정량' KPI 에서 ?status=미배정 으로 진입할 수 있다.
  const [filters, setFilters] = useState<Filters>({
    carrier: ALL,
    hub: ALL,
    size: ALL,
    date: ALL,
    status: params.get('status') ?? ALL,
  });

  const setFilter = (key: keyof Filters, value: string) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  const resetFilters = () =>
    setFilters({ carrier: ALL, hub: ALL, size: ALL, date: ALL, status: ALL });

  const options = useMemo(() => {
    const rows = data?.rows ?? [];
    return {
      carriers: distinct(rows, (r) => r.carrierId).sort(),
      hubs: distinct(rows, (r) => r.hubCode).sort(),
      sizes: distinct(rows, (r) => r.size).sort(),
      dates: distinct(rows, (r) => r.date).sort(),
      statuses: distinct(rows, (r) => r.status).sort(
        (a, b) => statusRank(a) - statusRank(b),
      ),
    };
  }, [data]);

  /** 거점 코드 → 표시명. 필터 select 에 코드가 아니라 이름을 보여준다. */
  const hubNameByCode = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of data?.rows ?? []) map.set(row.hubCode, row.hubName);
    return map;
  }, [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    const filtered = data.rows.filter(
      (row) =>
        (filters.carrier === ALL || row.carrierId === filters.carrier) &&
        (filters.hub === ALL || row.hubCode === filters.hub) &&
        (filters.size === ALL || row.size === filters.size) &&
        (filters.date === ALL || row.date === filters.date) &&
        (filters.status === ALL || row.status === filters.status),
    );

    // 원본 data.rows 는 mutate 하지 않는다 (filter 가 이미 새 배열을 만든다).
    return filtered.sort(
      (a, b) =>
        statusRank(a.status) - statusRank(b.status) ||
        a.date.localeCompare(b.date) ||
        b.railUnservedBoxes - a.railUnservedBoxes,
    );
  }, [data, filters]);

  const isFiltered = Object.values(filters).some((value) => value !== ALL);

  /** 미배정이 어디에 집중되는지 — 거점 × 규격으로 합산한다.
   *  기존 rows 만 사용하며 새 API 를 만들지 않는다. */
  const unservedHotspots = useMemo(() => {
    if (!data) return [];
    const totals = new Map<string, { hubCode: string; hubName: string; size: string; boxes: number }>();
    for (const row of data.rows) {
      if (row.railUnservedBoxes <= 0) continue;
      const key = `${row.hubCode}-${row.size}`;
      const entry = totals.get(key) ?? {
        hubCode: row.hubCode,
        hubName: row.hubName,
        size: row.size,
        boxes: 0,
      };
      entry.boxes += row.railUnservedBoxes;
      totals.set(key, entry);
    }
    return [...totals.values()].sort((a, b) => b.boxes - a.boxes).slice(0, 5);
  }, [data]);

  return (
    <PageContainer
      title="수송 수요·배정 현황"
      description="선사별 철도 서비스 필요량과 배정 결과입니다."
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={6} height={24} />
        </Card>
      )}

      {data && (
        <>
          <div className={styles.kpiStrip}>
            <Kpi
              label="총 수송 필요량"
              value={`${formatNumber(data.totals.requiredBoxes)}개`}
              sub={`${formatNumber(data.totals.requiredTeu)} TEU`}
            />
            <Kpi label="철도 배정량" value={`${formatNumber(data.totals.railServedBoxes)}개`} />
            <Kpi label="미배정량" value={`${formatNumber(data.totals.railUnservedBoxes)}개`} />
            <Kpi label="수송 필요 건수" value={`${formatNumber(data.totals.needCount)}건`} />
          </div>

          {/* 미배정 집중 현황 — 클릭하면 해당 거점·규격의 미배정 건만 남긴다. */}
          <div className={styles.hotspotStrip}>
            <span className={styles.hotspotLabel}>미배정 집중</span>
            {unservedHotspots.length === 0 ? (
              <span className={styles.hotspotEmpty}>미배정 물량 없음</span>
            ) : (
              unservedHotspots.map((spot) => (
                <button
                  key={`${spot.hubCode}-${spot.size}`}
                  type="button"
                  className={styles.hotspot}
                  onClick={() =>
                    setFilters({
                      carrier: ALL,
                      date: ALL,
                      hub: spot.hubCode,
                      size: spot.size,
                      status: '미배정',
                    })
                  }
                >
                  <span className={styles.hotspotName}>
                    {spot.hubName} · {spot.size}
                  </span>
                  <span className={styles.hotspotValue}>미배정 {spot.boxes}개</span>
                </button>
              ))
            )}
          </div>

          <Card
            title="수요·배정 상세"
            subtitle="거점·규격·요일 단위 집계 · 미배정 건이 먼저 표시됩니다"
            action={
              <span className={styles.cardMeta}>
                {formatNumber(data.rows.length)}건 중 {formatNumber(rows.length)}건 표시
              </span>
            }
          >
            <div className={styles.filterBar}>
              <FilterField
                label="선사"
                value={filters.carrier}
                onChange={(v) => setFilter('carrier', v)}
                options={options.carriers.map((id) => ({
                  value: id,
                  label: id.replace('CARRIER_', 'Carrier '),
                }))}
              />
              <FilterField
                label="거점"
                value={filters.hub}
                onChange={(v) => setFilter('hub', v)}
                options={options.hubs.map((code) => ({
                  value: code,
                  label: hubNameByCode.get(code) ?? code,
                }))}
              />
              <FilterField
                label="규격"
                value={filters.size}
                onChange={(v) => setFilter('size', v)}
                options={options.sizes.map((size) => ({ value: size, label: size }))}
              />
              <FilterField
                label="날짜"
                value={filters.date}
                onChange={(v) => setFilter('date', v)}
                options={options.dates.map((date) => ({ value: date, label: date }))}
              />
              <FilterField
                label="배정 상태"
                value={filters.status}
                onChange={(v) => setFilter('status', v)}
                options={options.statuses.map((status) => ({ value: status, label: status }))}
              />
              {isFiltered && (
                <button type="button" className={styles.filterReset} onClick={resetFilters}>
                  필터 초기화
                </button>
              )}
            </div>

            {rows.length === 0 ? (
              <EmptyState
                title="조건에 맞는 수송 필요 건이 없습니다."
                description="필터를 조정하거나 초기화해 보십시오."
              />
            ) : (
              <div className={styles.scroll}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>선사</th>
                      <th>도착 거점</th>
                      <th>규격</th>
                      <th>요일</th>
                      <th className={styles.right}>필요</th>
                      <th className={styles.right}>배정</th>
                      <th className={styles.right}>미배정</th>
                      <th>상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={`${row.carrierId}-${row.hubCode}-${row.size}-${row.date}-${index}`}>
                        <td>{row.carrierLabel}</td>
                        <td>
                          {/* 해당 거점·규격의 재고 화면으로 이동 */}
                          <Link
                            className={styles.carrierLink}
                            to={`/korail/inventory?hub=${row.hubCode}&size=${row.size}`}
                          >
                            {row.hubName}
                          </Link>
                        </td>
                        <td>{row.size}</td>
                        <td>
                          {row.weekday}요일
                          <div className={styles.kpiSub}>{row.date}</div>
                        </td>
                        <td className={styles.right}>{row.requiredBoxes}</td>
                        <td className={styles.right}>{row.railServedBoxes}</td>
                        <td className={styles.right}>{row.railUnservedBoxes}</td>
                        <td>
                          <StatusBadge tone={statusTone(row.status)} small>
                            {row.status}
                          </StatusBadge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </PageContainer>
  );
}

function FilterField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className={styles.filterField}>
      <span className={styles.filterLabel}>{label}</span>
      <select
        className={styles.filterSelect}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value={ALL}>전체</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
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
