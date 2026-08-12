/** Hub 정의와 schematic 좌표 (핸드오프 §13).
 *
 *  MILP 패키지에 정본 lat/lon 이 없으므로 초기 UI 는 외부 지도 API 에 의존하지 않고
 *  schematic SVG network 로 그린다. 실제 좌표가 확보되면 이 파일의 x/y 만 교체한다. */

export interface HubSchematic {
  code: string;
  name: string;
  shortName: string;
  /** SVG viewBox 0 0 100 100 기준 상대 좌표 */
  x: number;
  y: number;
  /** 라벨을 노드 기준 어느 쪽에 놓을지 */
  labelSide: 'left' | 'right';
}

export const HUB_SCHEMATIC: HubSchematic[] = [
  { code: 'UIWANG', name: '의왕ICD(오봉역)', shortName: '의왕ICD', x: 50, y: 12, labelSide: 'right' },
  { code: 'BUGANG', name: '부강화물역 CY', shortName: '부강', x: 50, y: 36, labelSide: 'right' },
  { code: 'YAKMOK', name: '약목역 CY', shortName: '약목', x: 70, y: 58, labelSide: 'left' },
  { code: 'DONGSAN', name: '동산역 CY', shortName: '동산', x: 30, y: 60, labelSide: 'left' },
  { code: 'BUSAN', name: '부산신항', shortName: '부산신항', x: 82, y: 86, labelSide: 'left' },
  { code: 'GWANGYANG', name: '신광양항', shortName: '신광양항', x: 30, y: 88, labelSide: 'left' },
];

export const HUB_BY_CODE: Record<string, HubSchematic> = Object.fromEntries(
  HUB_SCHEMATIC.map((hub) => [hub.code, hub]),
);

/** 노선 schematic (§13) */
export const CORRIDORS: { id: string; label: string; path: string[] }[] = [
  {
    id: 'GYEONGBU',
    label: '경부축',
    path: ['UIWANG', 'BUGANG', 'YAKMOK', 'BUSAN'],
  },
  {
    id: 'SOUTHWEST',
    label: '남서·호남축',
    path: ['UIWANG', 'BUGANG', 'DONGSAN', 'GWANGYANG'],
  },
];

export function hubShortName(code: string): string {
  return HUB_BY_CODE[code]?.shortName ?? code;
}

export function hubFullName(code: string): string {
  return HUB_BY_CODE[code]?.name ?? code;
}
