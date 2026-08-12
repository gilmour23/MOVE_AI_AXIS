import { NavLink } from 'react-router-dom';
import type { NavItem } from '@/app/roles';
import styles from './TopNav.module.css';

export function TopNav({ items }: { items: NavItem[] }) {
  return (
    <nav className={styles.nav} aria-label="주요 메뉴">
      {items.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            [styles.item, isActive ? styles.active : ''].filter(Boolean).join(' ')
          }
        >
          <Icon size={15} strokeWidth={2} />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
