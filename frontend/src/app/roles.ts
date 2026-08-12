import type { LucideIcon } from 'lucide-react';
import {
  Boxes,
  GitCompareArrows,
  LayoutDashboard,
  MapPinned,
  Radar,
  Route,
  Train,
} from 'lucide-react';

export type RoleId = 'carrier' | 'korail';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

export interface RoleDefinition {
  id: RoleId;
  label: string;
  shortLabel: string;
  description: string;
  home: string;
  nav: NavItem[];
}

/** 하나의 최적화 결과를 두 사용자 관점에서 본다.
 *  라우팅과 상단 네비게이션이 역할별로 갈리되 같은 App Shell 을 공유한다. */
export const ROLES: Record<RoleId, RoleDefinition> = {
  carrier: {
    id: 'carrier',
    label: 'Carrier Portal',
    shortLabel: '선사',
    description: '자사 공컨 재고와 철도 재배치 제안을 확인합니다.',
    home: '/carrier',
    nav: [
      { to: '/carrier', label: 'Overview', icon: LayoutDashboard, end: true },
      { to: '/carrier/inventory', label: '재고', icon: Boxes },
      { to: '/carrier/plan', label: '공컨 최적화', icon: Route },
      { to: '/carrier/transport', label: '운송비교', icon: GitCompareArrows },
      { to: '/carrier/tracking', label: '운송 현황', icon: Radar },
    ],
  },
  korail: {
    id: 'korail',
    label: 'KORAIL Control Tower',
    shortLabel: 'KORAIL',
    description: '공컨 전용열차 운송계획과 거점 작업계획을 관리합니다.',
    home: '/korail',
    // 전체 → 화물 → 열차 → 거점 순서로 읽히게 한다.
    nav: [
      { to: '/korail', label: '종합계획', icon: LayoutDashboard, end: true },
      { to: '/korail/cargo', label: '운송물량', icon: Boxes },
      { to: '/korail/trains', label: '열차운행', icon: Train },
      { to: '/korail/operations', label: '거점작업', icon: MapPinned },
    ],
  },
};

export function roleFromPath(pathname: string): RoleId | null {
  if (pathname.startsWith('/korail')) return 'korail';
  if (pathname.startsWith('/carrier')) return 'carrier';
  return null;
}
