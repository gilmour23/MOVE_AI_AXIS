import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Container } from 'lucide-react';
import { TopNav } from './TopNav';
import { RoleSwitch } from './RoleSwitch';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useMeta } from '@/app/MetaContext';
import { ROLES, roleFromPath } from '@/app/roles';
import styles from './AppShell.module.css';

export function AppShell({ children }: { children: ReactNode }) {
  const { meta, carrierId, setCarrierId } = useMeta();
  const location = useLocation();
  const roleId = roleFromPath(location.pathname);
  const role = roleId ? ROLES[roleId] : null;

  const carrierLabel = carrierId ? carrierId.replace('CARRIER_', '선사 ') : '—';
  const initial = carrierId ? carrierId.replace('CARRIER_', '') : '?';
  const isKorail = roleId === 'korail';

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link to="/" className={styles.brand}>
            <span className={styles.brandMark}>
              <Container size={17} strokeWidth={2.2} />
            </span>
            <span className={styles.brandText}>
              <span className={styles.brandName}>MOVE-AI</span>
              <span className={styles.brandSub}>
                {role ? role.label : '공컨테이너 철도 공동 재배치 플랫폼'}
              </span>
            </span>
          </Link>

          <div className={styles.navSlot}>{role && <TopNav items={role.nav} />}</div>

          <div className={styles.headerRight}>
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

            {roleId && <RoleSwitch current={roleId} />}

            {meta?.devMode && meta.availableCarriers.length > 1 && !isKorail && (
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
              <span className={styles.carrierAvatar}>{isKorail ? 'KR' : initial}</span>
              <span className={styles.carrierText}>
                <span className={styles.carrierName}>
                  {isKorail ? 'KORAIL' : carrierLabel}
                </span>
                <span className={styles.carrierRole}>
                  {isKorail ? '본부 관제' : '공컨 운영 담당'}
                </span>
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className={styles.main}>{children}</main>
    </div>
  );
}
