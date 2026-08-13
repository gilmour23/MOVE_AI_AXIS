import { useMeta } from '@/app/MetaContext';
import styles from './WeekSelector.module.css';

/** 계획주차 선택.
 *
 *  두 포털이 같은 planning context 를 공유하므로 header 한 곳에만 둔다.
 *  W01 과 W02 는 독립된 7일 최적화 결과다. 합쳐서 14일로 보여주지 않는다.
 *
 *  주차 목록은 결과 폴더에서 생성된 manifest 에서 온다. 화면에 주차를 박지 않는다. */
export function WeekSelector() {
  const { weeks, weekId, setWeekId } = useMeta();

  if (weeks.length === 0) {
    return <span className={styles.placeholder}>계획주차 —</span>;
  }

  return (
    <div className={styles.wrap}>
      <span className={styles.label}>계획주차</span>
      <select
        className={styles.select}
        value={weekId}
        onChange={(event) => setWeekId(event.target.value)}
        aria-label="계획주차 선택"
      >
        {weeks.map((week) => (
          <option key={week.weekId} value={week.weekId}>
            {week.label}
          </option>
        ))}
      </select>
    </div>
  );
}
