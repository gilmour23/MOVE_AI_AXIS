import { hubShortName } from '@/config/hubMeta';
import type { HubWeeklyInventory } from '@/types/domain';
import styles from './SelectorRow.module.css';

interface HubSelectorProps {
  hubs: HubWeeklyInventory[];
  selectedHub: string | null;
  onSelectHub: (hubCode: string) => void;
  hint?: string;
}

/** 매트릭스 row 클릭과 같은 state 를 공유한다 (핸드오프 §16.3).
 *  상단 규격 선택 → 이 거점 선택 → 아래 추이/요약 순으로 이어진다. */
export function HubSelector({
  hubs,
  selectedHub,
  onSelectHub,
  hint,
}: HubSelectorProps) {
  return (
    <div className={styles.row} role="group" aria-label="거점 선택">
      <span className={styles.label}>거점별 재고 상세</span>
      <div className={styles.chips}>
        {hubs.map((hub) => {
          const active = hub.hubCode === selectedHub;
          return (
            <button
              key={hub.hubCode}
              type="button"
              aria-pressed={active}
              className={[styles.chip, active ? styles.active : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => onSelectHub(hub.hubCode)}
            >
              {hub.weeklyUnmetDemand > 0 && <span className={styles.dot} />}
              {hubShortName(hub.hubCode)}
            </button>
          );
        })}
      </div>
      {hint && <span className={styles.hint}>{hint}</span>}
    </div>
  );
}
