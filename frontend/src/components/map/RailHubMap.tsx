import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, X } from 'lucide-react';
import { CORRIDORS, HUB_BY_CODE, HUB_SCHEMATIC, JUNCTION_HUB } from '@/config/hubMeta';
import { useMeta } from '@/app/MetaContext';
import { formatBoxes } from '@/lib/format';
import type { ContainerSize, OverviewHub } from '@/types/domain';
import styles from './RailHubMap.module.css';

const SIZES: ContainerSize[] = ['20FT', '40FT'];

interface RailHubMapProps {
  hubs: OverviewHub[];
  selectedHub?: string | null;
  onSelectHub?: (hubCode: string) => void;
}

const TONE_CLASS: Record<string, string> = {
  trunk: styles.corridorTrunk,
  gyeongbu: styles.corridorGyeongbu,
  honam: styles.corridorHonam,
};

/** 6 거점과 운행축을 schematic 노선도로 그린다.
 *
 *  **지리 지도가 아니다.** 결과 파일에 거점 lat/lon 이 없고, 지도를 눈대중으로
 *  그리면 거점이 실제와 다른 곳에 찍힌다. 그래서 지리를 주장하지 않는
 *  노선도로 그리고 화면에도 그렇게 밝힌다. 실제 좌표가 확보되면
 *  hubMeta.ts 의 x/y 만 교체하면 된다.
 *
 *  의왕→부강은 두 축이 함께 쓰는 공통구간이고 부강이 분기점이다. */
export function RailHubMap({ hubs, selectedHub, onSelectHub }: RailHubMapProps) {
  const [openHub, setOpenHub] = useState<string | null>(null);
  const { weekId } = useMeta();

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
                className={[styles.corridorLine, TONE_CLASS[corridor.tone]].join(' ')}
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
                {hub.code === JUNCTION_HUB && (
                  <circle cx={hub.x} cy={hub.y} r={3.4} className={styles.junctionRing} />
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

        <span className={styles.schematicNote}>
          노선도 · 지리적 위치를 나타내지 않습니다
        </span>

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
                  to={`/carrier/inventory?week=${weekId}&hub=${active.hubCode}&size=${size}`}
                >
                  {size} 재고 상세 보기 <ArrowRight size={13} />
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={styles.legend}>
        {CORRIDORS.map((corridor) => (
          <span key={corridor.id} className={styles.legendItem}>
            <span
              className={styles.legendSwatch}
              style={{ background: `var(--corridor-${corridor.tone})` }}
            />
            {corridor.label}
          </span>
        ))}
        <span className={styles.legendItem}>
          <span className={styles.legendDot} />
          이번 주 부족 예상 거점
        </span>
      </div>
    </div>
  );
}
