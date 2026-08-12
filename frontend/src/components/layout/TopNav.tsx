import { NavLink } from 'react-router-dom';
import { Boxes, GitCompareArrows, LayoutDashboard, Route } from 'lucide-react';
import styles from './TopNav.module.css';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/inventory', label: '재고', icon: Boxes, end: false },
  { to: '/optimization', label: '공컨 최적화', icon: Route, end: false },
  { to: '/comparison', label: '운송비교', icon: GitCompareArrows, end: false },
];

export function TopNav() {
  return (
    <nav className={styles.nav} aria-label="주요 메뉴">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
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
