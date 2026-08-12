import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { DotProps } from 'recharts';
import { formatBoxes } from '@/lib/format';
import type { DailyInventoryPoint } from '@/types/domain';
import styles from './WeeklyInventoryLine.module.css';

interface WeeklyInventoryLineProps {
  daily: DailyInventoryPoint[];
}

/** 선택 거점 + 규격의 월~일 7개 point 만 그린다. 시간별 chart 는 만들지 않는다 (§16.4). */
export function WeeklyInventoryLine({ daily }: WeeklyInventoryLineProps) {
  const hasShortage = daily.some((point) => point.unmetDemand > 0);

  return (
    <>
      <div className={styles.wrap}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={daily} margin={{ top: 12, right: 16, bottom: 4, left: -12 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="weekday"
              tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
            />
            <YAxis
              allowDecimals={false}
              width={44}
              domain={[0, 'auto']}
              tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<InventoryTooltip />} cursor={{ stroke: 'var(--border-strong)' }} />
            <Line
              type="monotone"
              dataKey="closingInventory"
              stroke="var(--brand)"
              strokeWidth={2}
              dot={<ShortageDot />}
              activeDot={{ r: 5, fill: 'var(--brand)', stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className={styles.legend}>
        <span className={styles.legendItem}>
          <span className={styles.legendLine} />예상 재고(개)
        </span>
        {hasShortage && (
          <span className={styles.legendItem}>
            <span className={styles.legendDot} />부족 발생일
          </span>
        )}
      </div>
    </>
  );
}

interface TooltipPayloadEntry {
  payload: DailyInventoryPoint;
}

function InventoryTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipTitle}>
        {point.weekday}요일 · {formatBoxes(point.closingInventory)}
      </div>
      <div style={{ color: 'var(--text-muted)' }}>{point.date}</div>
      {point.unmetDemand > 0 && (
        <div className={styles.tooltipShortage}>
          예상 부족 {formatBoxes(point.unmetDemand)}
        </div>
      )}
    </div>
  );
}

function ShortageDot(props: DotProps & { payload?: DailyInventoryPoint }) {
  const { cx, cy, payload } = props;
  if (cx === undefined || cy === undefined) return null;
  const shortage = (payload?.unmetDemand ?? 0) > 0;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={shortage ? 4.5 : 3}
      fill={shortage ? 'var(--danger)' : 'var(--surface)'}
      stroke={shortage ? 'var(--danger)' : 'var(--brand)'}
      strokeWidth={2}
    />
  );
}
