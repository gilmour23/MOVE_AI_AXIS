import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Container } from 'lucide-react';
import { TopNav } from './TopNav';
import { RoleSwitch } from './RoleSwitch';
import { WeekSelector } from './WeekSelector';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useMeta } from '@/app/MetaContext';
import { ROLES, roleFromPath } from '@/app/roles';
import styles from './AppShell.module.css';

/** 합성 데이터·프로토타입 시각 배지를 하나로 합친다.
 *
 *  데모 데이터라는 사실은 숨기지 않되, 사용자에게는 내부 필드명 대신
 *  읽을 수 있는 표현만 보여준다. 실제 데이터로 교체되면 자동으로 사라진다. */
function buildDataSourceBadge(weekMeta: ReturnType<typeof useMeta>['weekMeta']) {
  if (!weekMeta) return null;
  const meta = weekMeta;
  const parts: string[] = [];
  const details: string[] = [];
  if (meta.isSyntheticCarrierData) {
    parts.push('합성 데이터');
    details.push('선사별 수요·재고는 실제 선사 데이터가 아닌 합성 데이터입니다.');
  }
  if (meta.isPrototypeTimetable) {
    parts.push('프로토타입 운행계획');
    details.push('운행시각은 KORAIL 확정 시각이 아니라 프로토타입 운행후보입니다.');
  }
  if (parts.length === 0) return null;
  // 헤더 폭이 한정되어 라벨은 짧게 두고 상세는 tooltip 으로 보여준다.
  return { label: `DEMO · ${parts[0]}`, title: details.join('\n') };
}

export function AppShell({ children }: { children: ReactNode }) {
  const { weekMeta, carrierId } = useMeta();
  const location = useLocation();
  const roleId = roleFromPath(location.pathname);
  const role = roleId ? ROLES[roleId] : null;

  const carrierLabel = carrierId ? carrierId.replace('CARRIER_', '선사 ') : '—';
  const initial = carrierId ? carrierId.replace('CARRIER_', '') : '?';
  const isKorail = roleId === 'korail';
  // KORAIL header 는 navigation 과 역할 전환에 폭을 우선 배분한다.
  // 계획주기·데이터 출처 배지는 Carrier Portal 에서만 유지한다.
  const dataSourceBadge = isKorail ? null : buildDataSourceBadge(weekMeta);

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

          <div className={styles.navSlot}>
            {role && <TopNav items={role.nav} wide={isKorail} />}
          </div>

          <div className={styles.headerRight}>
            {/* 데이터 출처 배지. 헤더 폭이 한정되어 두 개를 하나로 합치고,
                상세는 tooltip 으로 보여준다. 실제 데이터로 교체되면 사라진다. */}
            <div className={styles.metaBadges}>
              {dataSourceBadge && (
                <StatusBadge tone="neutral" small title={dataSourceBadge.title}>
                  {dataSourceBadge.label}
                </StatusBadge>
              )}
            </div>

            {role && <WeekSelector />}

            {roleId && <RoleSwitch current={roleId} />}

            <div className={styles.carrier}>
              <span className={styles.carrierAvatar}>{isKorail ? 'KR' : initial}</span>
              <span className={styles.carrierText}>
                <span className={styles.carrierName}>
                  {isKorail ? 'KORAIL' : carrierLabel}
                </span>
                <span className={styles.carrierRole}>
                  {isKorail ? '철도물류 운영' : '공컨 운영 담당'}
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
