import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { fetchKorailCargo } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { formatDateTimeCompact, formatNumber, parseWallClock } from '@/lib/format';
import type { KorailTransportAllocation } from '@/types/domain';
import styles from './Korail.module.css';

const ALL = 'ALL';

interface Filters {
  date: string;
  carrier: string;
  origin: string;
  destination: string;
  size: string;
  train: string;
}

const EMPTY: Filters = {
  date: ALL,
  carrier: ALL,
  origin: ALL,
  destination: ALL,
  size: ALL,
  train: ALL,
};

/** 출발 wall-clock 의 달력 날짜. 브라우저 timezone 변환을 거치지 않는다. */
function departureDate(row: KorailTransportAllocation): string {
  const w = parseWallClock(row.originDepartureTime);
  if (!w) return '';
  return `${w.year}-${String(w.month).padStart(2, '0')}-${String(w.day).padStart(2, '0')}`;
}

/** 공컨 운송물량.
 *  어느 선사의 어떤 규격 공컨을 어디에서 어디까지 몇 개 옮기며
 *  어떤 열차가 담당하는지를 배정 결과 기준으로 보여준다. */
export function KorailCargoPage() {
  const navigate = useNavigate();
  const { weekId } = useMeta();
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const { data, loading, error, reload } = useAsync(
    (signal) => fetchKorailCargo(weekId, signal),
    [weekId],
  );

  const setFilter = (key: keyof Filters, value: string) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  const options = useMemo(() => {
    const rows = data?.rows ?? [];
    const uniq = <T,>(pick: (r: KorailTransportAllocation) => T) =>
      Array.from(new Set(rows.map(pick)));
    const hubNames = new Map<string, string>();
    for (const row of rows) {
      hubNames.set(row.originHub, row.originName);
      hubNames.set(row.destinationHub, row.destinationName);
    }
    return {
      dates: uniq(departureDate).filter(Boolean).sort(),
      carriers: uniq((r) => r.carrierId).sort(),
      origins: uniq((r) => r.originHub).sort(),
      destinations: uniq((r) => r.destinationHub).sort(),
      sizes: uniq((r) => r.size).sort(),
      trains: uniq((r) => r.trainId).sort(),
      hubNames,
      carrierLabels: new Map(rows.map((r) => [r.carrierId, r.carrierLabel])),
    };
  }, [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.rows.filter(
      (row) =>
        (filters.date === ALL || departureDate(row) === filters.date) &&
        (filters.carrier === ALL || row.carrierId === filters.carrier) &&
        (filters.origin === ALL || row.originHub === filters.origin) &&
        (filters.destination === ALL || row.destinationHub === filters.destination) &&
        (filters.size === ALL || row.size === filters.size) &&
        (filters.train === ALL || row.trainId === filters.train),
    );
  }, [data, filters]);

  const isFiltered = Object.values(filters).some((v) => v !== ALL);

  return (
    <PageContainer title="공컨 운송물량">
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={6} height={24} />
        </Card>
      )}

      {data && (
        <Card
          title="운송물량 상세"
          action={
            <span className={styles.cardMeta}>
              {formatNumber(data.rows.length)}건 중 {formatNumber(rows.length)}건
            </span>
          }
        >
          <div className={styles.filterBar}>
            <FilterField
              label="날짜"
              value={filters.date}
              onChange={(v) => setFilter('date', v)}
              options={options.dates.map((d) => ({ value: d, label: d }))}
            />
            <FilterField
              label="선사"
              value={filters.carrier}
              onChange={(v) => setFilter('carrier', v)}
              options={options.carriers.map((id) => ({
                value: id,
                label: options.carrierLabels.get(id) ?? id,
              }))}
            />
            <FilterField
              label="출발"
              value={filters.origin}
              onChange={(v) => setFilter('origin', v)}
              options={options.origins.map((c) => ({
                value: c,
                label: options.hubNames.get(c) ?? c,
              }))}
            />
            <FilterField
              label="도착"
              value={filters.destination}
              onChange={(v) => setFilter('destination', v)}
              options={options.destinations.map((c) => ({
                value: c,
                label: options.hubNames.get(c) ?? c,
              }))}
            />
            <FilterField
              label="규격"
              value={filters.size}
              onChange={(v) => setFilter('size', v)}
              options={options.sizes.map((s) => ({ value: s, label: s }))}
            />
            <FilterField
              label="열차"
              value={filters.train}
              onChange={(v) => setFilter('train', v)}
              options={options.trains.map((t) => ({ value: t, label: t }))}
            />
            {isFiltered && (
              <button
                type="button"
                className={styles.filterReset}
                onClick={() => setFilters(EMPTY)}
              >
                초기화
              </button>
            )}
          </div>

          {rows.length === 0 ? (
            <EmptyState title="조건에 맞는 운송물량이 없습니다." />
          ) : (
            <div className={styles.scroll}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>선사</th>
                    <th>운송구간</th>
                    <th>규격</th>
                    <th className={styles.right}>물량</th>
                    <th>배정 열차</th>
                    <th>출발</th>
                    <th>도착</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr
                      key={`${row.trainId}-${row.carrierId}-${row.originHub}-${row.destinationHub}-${row.size}-${index}`}
                      className={styles.rowClickable}
                      onClick={() => navigate(`/korail/trains?train=${row.trainId}`)}
                    >
                      <td>{row.carrierLabel}</td>
                      <td>
                        {row.originName} → {row.destinationName}
                      </td>
                      <td>{row.size}</td>
                      <td className={styles.right}>
                        {row.boxes}개
                        <div className={styles.kpiSub}>{row.teu} TEU</div>
                      </td>
                      <td className={styles.mono}>{row.trainId}</td>
                      <td>{formatDateTimeCompact(row.originDepartureTime)}</td>
                      <td
                        title={
                          row.destinationAvailableTime
                            ? `사용 가능 ${formatDateTimeCompact(row.destinationAvailableTime)}`
                            : undefined
                        }
                      >
                        {formatDateTimeCompact(row.destinationArrivalTime)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
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
