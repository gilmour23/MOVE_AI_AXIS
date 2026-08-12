import type { ReactNode } from 'react';
import { Container } from 'lucide-react';
import { TopNav } from './TopNav';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useMeta } from '@/app/MetaContext';
import styles from './AppShell.module.css';

export function AppShell({ children }: { children: ReactNode }) {
  const { meta, carrierId, setCarrierId } = useMeta();

  const carrierLabel = carrierId ? carrierId.replace('CARRIER_', '선사 ') : '—';
  const initial = carrierId ? carrierId.replace('CARRIER_', '') : '?';

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.brand}>
            <span className={styles.brandMark}>
              <Container size={17} strokeWidth={2.2} />
            </span>
            <span className={styles.brandText}>
              <span className={styles.brandName}>MOVE-AI</span>
              <span className={styles.brandSub}>선사 공컨 운송 인터페이스</span>
            </span>
          </div>

          <div className={styles.navSlot}>
            <TopNav />
          </div>

          <div className={styles.headerRight}>
            {/* 실제 데이터로 교체되면 SUMMARY.json 값에 따라 자동으로 사라진다 (§2) */}
            <div className={styles.metaBadges}>
              {meta?.isSyntheticCarrierData && (
                <StatusBadge tone="neutral" small title="carrier_data_source = SYNTHETIC_CARRIER_LEVEL_DATA">
                  Synthetic demo data
                </StatusBadge>
              )}
              {meta?.isPrototypeTimetable && (
                <StatusBadge tone="neutral" small title="candidate_timetable_source = PROTOTYPE_SYNTHETIC">
                  Prototype timetable
                </StatusBadge>
              )}
            </div>

            {meta?.devMode && meta.availableCarriers.length > 1 && (
              <select
                className={styles.devSelect}
                value={carrierId}
                onChange={(event) => setCarrierId(event.target.value)}
                aria-label="개발용 선사 선택"
                title="dev mode 전용 — 실제 선사 화면에는 노출되지 않습니다"
              >
                {meta.availableCarriers.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            )}

            <div className={styles.carrier}>
              <span className={styles.carrierAvatar}>{initial}</span>
              <span className={styles.carrierText}>
                <span className={styles.carrierName}>{carrierLabel}</span>
                <span className={styles.carrierRole}>공컨 운영 담당</span>
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className={styles.main}>{children}</main>
    </div>
  );
}
