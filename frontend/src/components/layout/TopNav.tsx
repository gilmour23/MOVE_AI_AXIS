import { NavLink } from 'react-router-dom';
import type { NavItem } from '@/app/roles';
import styles from './TopNav.module.css';

/** `wide` 는 메뉴 수가 적은 KORAIL 용 — 글자·여백을 키운다.
 *  Carrier Portal 은 메뉴가 많으므로 기본 밀도를 유지한다. */
export function TopNav({ items, wide = false }: { items: NavItem[]; wide?: boolean }) {
  return (
    <nav
      className={[styles.nav, wide ? styles.navWide : ''].filter(Boolean).join(' ')}
      aria-label="주요 메뉴"
    >
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
