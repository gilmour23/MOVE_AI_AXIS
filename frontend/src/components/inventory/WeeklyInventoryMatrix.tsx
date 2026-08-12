import { formatNumber } from '@/lib/format';
import type { WeeklyInventoryMatrixData } from '@/types/domain';
import styles from './WeeklyInventoryMatrix.module.css';

interface WeeklyInventoryMatrixProps {
  data: WeeklyInventoryMatrixData;
  selectedHub: string | null;
  onSelectHub: (hubCode: string) => void;
}

/** 거점 × 요일 재고 매트릭스.
 *  cell 값은 daily closing inventory 이며, 부족은 음수가 아니라 별도 라벨로 표시한다 (§9.2, §16.2).
 *  baseline / postRail 모두 이 컴포넌트를 재사용한다 (§17.5). */
export function WeeklyInventoryMatrix({
  data,
  selectedHub,
  onSelectHub,
}: WeeklyInventoryMatrixProps) {
  const modeLabel = data.mode === 'baseline' ? '재배치 전' : '재배치 후';

  return (
    <>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.hubHead} scope="col">
                거점
              </th>
              {data.days.map((day) => (
                <th key={day.date} scope="col" title={day.date}>
                  {day.weekday}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className={styles.tbody}>
            {data.hubs.map((hub) => {
              const selected = hub.hubCode === selectedHub;
              return (
                <tr
                  key={hub.hubCode}
                  className={[
                    styles.rowClickable,
                    selected ? styles.selectedRow : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => onSelectHub(hub.hubCode)}
                >
                  <th scope="row" className={styles.hubCell}>
                    <button
                      type="button"
                      className={styles.hubButton}
                      aria-pressed={selected}
                    >
                      <span className={styles.hubName}>{hub.hubName}</span>
                    </button>
                  </th>
                  {hub.daily.map((day) => {
                    const hasShortage = day.unmetDemand > 0;
                    return (
                      <td
                        key={day.date}
                        className={[
                          styles.cell,
                          hasShortage ? styles.cellShortage : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        title={`${hub.hubName} · ${day.weekday}요일 (${day.date}) · ${modeLabel}`}
                      >
                        <div
                          className={[
                            styles.value,
                            day.closingInventory === 0 ? styles.valueZero : '',
                          ]
                            .filter(Boolean)
                            .join(' ')}
                        >
                          {formatNumber(day.closingInventory)}
                        </div>
                        {hasShortage && (
                          <div className={styles.shortage}>
                            부족 {formatNumber(day.unmetDemand)}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className={styles.footnote}>
        각 칸은 해당 요일 마지막 시각의 예상 재고(개)입니다. 재고는 0 아래로 내려가지
        않으며, 충족하지 못한 수요는 <strong>부족</strong>으로 따로 표시합니다.
      </p>
    </>
  );
}
