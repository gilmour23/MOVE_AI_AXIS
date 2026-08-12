import { CORRIDORS, HUB_BY_CODE, HUB_SCHEMATIC } from '@/config/hubMeta';
import type { KorailHub, KorailTrain } from '@/types/domain';
import styles from './Korail.module.css';

/** 6-Hub 운영 network schematic.
 *  지리 지도가 아니라 KORAIL 운영 관점 schematic 이며,
 *  실제 선정 열차를 해당 corridor 위에 표시한다. */
export function KorailNetwork({
  hubs,
  trains,
  selectedTrainId,
  onSelectTrain,
}: {
  hubs: KorailHub[];
  trains: KorailTrain[];
  selectedTrainId?: string | null;
  onSelectTrain?: (trainId: string) => void;
}) {
  const byCode = new Map(hubs.map((h) => [h.hubCode, h]));

  // 열차를 corridor 에 배치 — work_stops 가 어느 축에 속하는지로 판정
  const trainsByCorridor = CORRIDORS.map((corridor) => ({
    corridor,
    trains: trains.filter((t) =>
      t.workStops.every((stop) => corridor.path.includes(stop)),
    ),
  }));

  return (
    <div>
      <div className={styles.network}>
        <svg className={styles.networkSvg} viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" role="img" aria-label="6거점 철도 운영 네트워크">
          {CORRIDORS.map((corridor) => {
            const points = corridor.path
              .map((code) => HUB_BY_CODE[code])
              .filter(Boolean)
              .map((h) => `${h.x},${h.y}`)
              .join(' ');
            return (
              <polyline
                key={corridor.id}
                points={points}
                className={styles.netLine}
                stroke={corridor.id === 'GYEONGBU' ? 'var(--brand)' : 'var(--accent)'}
              />
            );
          })}

          {HUB_SCHEMATIC.map((hub) => {
            const data = byCode.get(hub.code);
            const alert = (data?.postRailStockout ?? 0) > 0;
            const anchor = hub.labelSide === 'left' ? 'end' : 'start';
            const labelX = hub.labelSide === 'left' ? hub.x - 3.6 : hub.x + 3.6;
            const total20 = data?.sizes['20FT'].postRailInventory ?? 0;
            const total40 = data?.sizes['40FT'].postRailInventory ?? 0;

            return (
              <g key={hub.code}>
                <circle
                  cx={hub.x}
                  cy={hub.y}
                  r={2.2}
                  className={[styles.netNode, alert ? styles.netNodeAlert : ''].filter(Boolean).join(' ')}
                />
                <text x={labelX} y={hub.y - 0.3} textAnchor={anchor} className={styles.netLabel}>
                  {hub.shortName}
                </text>
                <text x={labelX} y={hub.y + 2.9} textAnchor={anchor} className={styles.netSub}>
                  20FT {total20} · 40FT {total40}
                </text>
              </g>
            );
          })}

          {/* 열차 marker — corridor 중간 지점에 표기 */}
          {trainsByCorridor.map(({ corridor, trains: corridorTrains }) =>
            corridorTrains.map((train, index) => {
              const path = corridor.path.map((c) => HUB_BY_CODE[c]).filter(Boolean);
              const mid = path[Math.floor(path.length / 2)];
              if (!mid) return null;
              const selected = train.trainId === selectedTrainId;
              return (
                <g
                  key={train.trainId}
                  onClick={() => onSelectTrain?.(train.trainId)}
                  style={{ cursor: onSelectTrain ? 'pointer' : undefined }}
                >
                  <rect
                    x={mid.x - 7}
                    y={mid.y + 5 + index * 4.4}
                    width={14}
                    height={3.4}
                    rx={1.2}
                    fill={selected ? 'var(--brand-soft)' : 'var(--surface)'}
                    stroke={selected ? 'var(--brand)' : 'var(--border-strong)'}
                    strokeWidth={0.3}
                  />
                  <text
                    x={mid.x}
                    y={mid.y + 7.4 + index * 4.4}
                    textAnchor="middle"
                    className={styles.netTrain}
                  >
                    {train.trainId}
                  </text>
                </g>
              );
            }),
          )}
        </svg>
      </div>
      <div className={styles.legend}>
        <span className={styles.legendItem}>
          <span className={styles.legendSwatch} style={{ background: 'var(--brand)' }} />
          경부축
        </span>
        <span className={styles.legendItem}>
          <span className={styles.legendSwatch} style={{ background: 'var(--accent)' }} />
          서남축
        </span>
        <span className={styles.legendItem}>재고는 재배치 후 주말 기준 · 붉은 노드는 부족 잔존</span>
      </div>
    </div>
  );
}
