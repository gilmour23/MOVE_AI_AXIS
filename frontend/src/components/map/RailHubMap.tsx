import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, X } from 'lucide-react';
import { CORRIDORS, HUB_BY_CODE, HUB_SCHEMATIC } from '@/config/hubMeta';
import { formatBoxes } from '@/lib/format';
import type { ContainerSize, OverviewHub } from '@/types/domain';
import styles from './RailHubMap.module.css';

const SIZES: ContainerSize[] = ['20FT', '40FT'];

interface RailHubMapProps {
  hubs: OverviewHub[];
  selectedHub?: string | null;
  onSelectHub?: (hubCode: string) => void;
}

/** 6 hub + 두 corridor 를 schematic SVG 로 그린다.
 *  실제 lat/lon 이 확보되면 hubMeta.ts 좌표만 교체하면 된다 (핸드오프 §13). */
export function RailHubMap({ hubs, selectedHub, onSelectHub }: RailHubMapProps) {
  const [openHub, setOpenHub] = useState<string | null>(null);

  const byCode = new Map(hubs.map((hub) => [hub.hubCode, hub]));
  const active = openHub ? byCode.get(openHub) ?? null : null;
  const activeMeta = openHub ? HUB_BY_CODE[openHub] : null;

  const handleClick = (hubCode: string) => {
    setOpenHub((current) => (current === hubCode ? null : hubCode));
    onSelectHub?.(hubCode);
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.canvas}>
        <svg
          className={styles.svg}
          viewBox="0 0 100 100"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="거점 및 철도 노선 개요"
        >
          {CORRIDORS.map((corridor) => {
            const points = corridor.path
              .map((code) => HUB_BY_CODE[code])
              .filter(Boolean)
              .map((hub) => `${hub.x},${hub.y}`)
              .join(' ');
            return (
              <polyline
                key={corridor.id}
                points={points}
                className={[
                  styles.corridorLine,
                  corridor.id === 'GYEONGBU'
                    ? styles.corridorGyeongbu
                    : styles.corridorSouthwest,
                ].join(' ')}
              />
            );
          })}

          {HUB_SCHEMATIC.map((hub) => {
            const data = byCode.get(hub.code);
            const hasShortage = data?.hasShortage ?? false;
            const isSelected = selectedHub === hub.code || openHub === hub.code;
            const anchor = hub.labelSide === 'left' ? 'end' : 'start';
            const labelX = hub.labelSide === 'left' ? hub.x - 3.4 : hub.x + 3.4;

            return (
              <g
                key={hub.code}
                className={styles.nodeGroup}
                onClick={() => handleClick(hub.code)}
                role="button"
                tabIndex={0}
                aria-label={`${hub.name} 상세 보기`}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    handleClick(hub.code);
                  }
                }}
              >
                {hasShortage && (
                  <circle cx={hub.x} cy={hub.y} r={4.4} className={styles.nodeHalo} />
                )}
                <circle
                  cx={hub.x}
                  cy={hub.y}
                  r={isSelected ? 2.5 : 2}
                  className={[
                    styles.node,
                    hasShortage ? styles.nodeShortage : '',
                    isSelected ? styles.nodeSelected : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                />
                <text
                  x={labelX}
                  y={hub.y - 0.2}
                  textAnchor={anchor}
                  className={styles.nodeLabel}
                >
                  {hub.shortName}
                </text>
                {data && (
                  <text
                    x={labelX}
                    y={hub.y + 3}
                    textAnchor={anchor}
                    className={styles.nodeSub}
                  >
                    20FT {data.sizes['20FT'].weekEndInventory} · 40FT{' '}
                    {data.sizes['40FT'].weekEndInventory}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {active && activeMeta && (
          <div
            className={styles.popover}
            style={{ left: `${activeMeta.x}%`, top: `${activeMeta.y}%` }}
          >
            <button
              type="button"
              className={styles.popoverClose}
              onClick={() => setOpenHub(null)}
              aria-label="닫기"
            >
              <X size={13} />
            </button>
            <div className={styles.popoverTitle}>{active.hubName}</div>
            <div className={styles.popoverMeta}>재배치 전 · 주말 예상재고 기준</div>

            {SIZES.map((size) => {
              const state = active.sizes[size];
              return (
                <div key={size} className={styles.popoverRow}>
                  <span className={styles.popoverSize}>{size}</span>
                  <span className={styles.popoverValue}>
                    {state.weeklyShortage > 0 ? (
                      <span className={styles.popoverShortage}>
                        예상 부족 {formatBoxes(state.weeklyShortage)}
                      </span>
                    ) : (
                      <>예상 재고 {formatBoxes(state.weekEndInventory)}</>
                    )}
                  </span>
                </div>
              );
            })}

            <div className={styles.popoverLinks}>
              {SIZES.map((size) => (
                <Link
                  key={size}
                  className={styles.popoverLink}
                  to={`/carrier/inventory?hub=${active.hubCode}&size=${size}`}
                >
                  {size} 재고 상세 보기 <ArrowRight size={13} />
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={styles.legend}>
        <span className={styles.legendItem}>
          <span
            className={styles.legendSwatch}
            style={{ background: 'var(--brand)' }}
          />
          경부축
        </span>
        <span className={styles.legendItem}>
          <span
            className={styles.legendSwatch}
            style={{ background: 'var(--accent)' }}
          />
          남서·호남축
        </span>
        <span className={styles.legendItem}>
          <span className={styles.legendDot} />
          이번 주 부족 예상 거점
        </span>
      </div>
    </div>
  );
}
