import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatBoxes, formatNumber } from '@/lib/format';
import type { HubInventoryComparison } from '@/types/domain';
import styles from './InventoryComparison.module.css';

/** 재배치 전/후 비교.
 *
 *  재고선 2개와 이벤트(수요·외부공급·철도 유입/반출)를 **분리해서** 그린다.
 *  재고는 시점의 잔량이고 이벤트는 그 날의 유량이라 단위가 다르다.
 *  한 축에 겹치면 크기 비교가 되는 것처럼 보인다.
 *
 *  부족은 최저재고가 0 인지로 판정하지 않는다. 재고는 0 에서 clip 되므로
 *  0 이어도 충족된 날이 있다. 반드시 미충족 수요(unmet) 값을 쓴다. */
export function InventoryComparison({ data }: { data: HubInventoryComparison }) {
  const { baseline, postRail, days } = data;
  const hasShortage = baseline.weeklyUnmetDemand > 0 || postRail.weeklyUnmetDemand > 0;

  return (
    <div className={styles.wrap}>
      <div className={styles.stats}>
        <Stat
          label="주간 최저 예상재고"
          value={`${formatBoxes(baseline.minimumDisplayedInventory)} → ${formatBoxes(
            postRail.minimumDisplayedInventory,
          )}`}
          sub="재배치 전 → 후"
        />
        <Stat
          label="재배치 전 부족"
          value={formatBoxes(baseline.weeklyUnmetDemand)}
          sub="충족하지 못한 수요"
        />
        <Stat
          label="재배치 후 부족"
          value={formatBoxes(postRail.weeklyUnmetDemand)}
          sub={
            postRail.weeklyUnmetDemand > 0 ? '잔존 부족' : '이 거점은 해소'
          }
        />
        <Stat
          label="부족 감소"
          value={formatBoxes(data.shortageReductionBoxes)}
          sub={`철도 유입 ${formatNumber(postRail.railInboundBoxes)}개 · 반출 ${formatNumber(
            postRail.railOutboundBoxes,
          )}개`}
        />
      </div>

      <section className={styles.block}>
        <h4 className={styles.blockTitle}>예상 재고 추이</h4>
        <p className={styles.blockNote}>
          각 요일 마지막 시각의 예상 재고(개). 재고는 0 아래로 내려가지 않습니다.
        </p>
        <div className={styles.chart}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={days} margin={{ top: 12, right: 16, bottom: 4, left: -12 }}>
              <CartesianGrid
                stroke="var(--border)"
                strokeDasharray="3 3"
                vertical={false}
              />
              <XAxis
                dataKey="weekday"
                tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
                axisLine={{ stroke: 'var(--border-strong)' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border-strong)',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value: number, name: string) => [`${value}개`, name]}
              />
              <Legend
                wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                iconType="plainline"
              />
              <Line
                name="재배치 미반영"
                type="monotone"
                dataKey="baselineInventory"
                stroke="var(--text-faint)"
                strokeWidth={1.8}
                strokeDasharray="4 3"
                dot={{ r: 2.5 }}
              />
              <Line
                name="재배치 반영"
                type="monotone"
                dataKey="postRailInventory"
                stroke="var(--brand)"
                strokeWidth={2.2}
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className={styles.block}>
        <h4 className={styles.blockTitle}>일별 증감</h4>
        <p className={styles.blockNote}>
          재고와 단위가 달라 축을 분리했습니다. 수요·외부공급은 계획 입력이고,
          철도 유입·반출은 재배치안이 만든 이동입니다.
        </p>
        <div className={styles.strip}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={days} margin={{ top: 8, right: 16, bottom: 4, left: -12 }}>
              <CartesianGrid
                stroke="var(--border)"
                strokeDasharray="3 3"
                vertical={false}
              />
              <XAxis
                dataKey="weekday"
                tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
                axisLine={{ stroke: 'var(--border-strong)' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border-strong)',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value: number, name: string) => [`${value}개`, name]}
              />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
              <Bar name="수요" dataKey="demand" fill="var(--text-faint)" />
              <Bar name="외부 공급" dataKey="externalSupply" fill="var(--border-strong)" />
              <Bar name="철도 유입" dataKey="railInbound" fill="var(--brand)" />
              <Bar name="철도 반출" dataKey="railOutbound" fill="var(--accent)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {hasShortage && (
        <section className={styles.block}>
          <h4 className={styles.blockTitle}>부족 상세</h4>
          <p className={styles.blockNote}>
            철도 유입은 부족이 발생한 날이 아니라 그 이전에 도착하므로 위
            일별 증감에서 확인합니다.
          </p>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">일자</th>
                  <th scope="col">재배치 전 부족</th>
                  <th scope="col">재배치 후 부족</th>
                </tr>
              </thead>
              <tbody>
                {days
                  .filter((day) => day.baselineUnmet > 0 || day.postRailUnmet > 0)
                  .map((day) => (
                    <tr key={day.date}>
                      <td>
                        {day.weekday}
                        <span className={styles.sub}>{day.date}</span>
                      </td>
                      <td>{formatBoxes(day.baselineUnmet)}</td>
                      <td
                        className={day.postRailUnmet > 0 ? styles.remain : styles.cleared}
                      >
                        {day.postRailUnmet > 0
                          ? formatBoxes(day.postRailUnmet)
                          : '해소'}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={styles.statValue}>{value}</span>
      {sub && <span className={styles.statSub}>{sub}</span>}
    </div>
  );
}
