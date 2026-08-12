import { useNavigate } from 'react-router-dom';
import { Ship, TowerControl } from 'lucide-react';
import { ROLES, type RoleId } from '@/app/roles';
import styles from './RoleSwitch.module.css';

const ICONS = { carrier: Ship, korail: TowerControl } as const;

/** 두 화면이 별도 사이트가 아니라 같은 플랫폼의 두 관점임을 드러내는 전환 컨트롤. */
export function RoleSwitch({ current }: { current: RoleId }) {
  const navigate = useNavigate();

  return (
    <div className={styles.switch} role="group" aria-label="역할 전환">
      {(Object.keys(ROLES) as RoleId[]).map((id) => {
        const role = ROLES[id];
        const Icon = ICONS[id];
        const active = id === current;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={active}
            className={[styles.option, active ? styles.active : ''].filter(Boolean).join(' ')}
            onClick={() => navigate(role.home)}
            title={role.description}
          >
            <Icon size={14} />
            <span className={styles.label}>{role.label}</span>
            <span className={styles.labelShort}>{role.shortLabel}</span>
          </button>
        );
      })}
    </div>
  );
}
