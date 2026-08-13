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

export type CorridorTone = 'trunk' | 'gyeongbu' | 'honam';

/** 노선 schematic.
 *
 *  두 축을 각각 의왕부터 그리면 의왕→부강 구간이 겹쳐서, 서로 다른 두 노선이
 *  나란히 가는 것처럼 보인다. 실제로는 **한 구간을 공유**하고 부강에서 갈라진다.
 *  그래서 공통구간을 따로 두고 부강을 분기점으로 그린다. */
export const CORRIDORS: {
  id: string;
  label: string;
  tone: CorridorTone;
  path: string[];
}[] = [
  {
    id: 'TRUNK',
    label: '공통구간',
    tone: 'trunk',
    path: ['UIWANG', 'BUGANG'],
  },
  {
    id: 'GYEONGBU',
    label: '경부축',
    tone: 'gyeongbu',
    path: ['BUGANG', 'YAKMOK', 'BUSAN'],
  },
  {
    id: 'HONAM',
    label: '호남축',
    tone: 'honam',
    path: ['BUGANG', 'DONGSAN', 'GWANGYANG'],
  },
];

/** 부강은 두 축이 갈라지는 분기점이다. 노선도에서 다르게 그린다. */
export const JUNCTION_HUB = 'BUGANG';

export function hubShortName(code: string): string {
  return HUB_BY_CODE[code]?.shortName ?? code;
}

export function hubFullName(code: string): string {
  return HUB_BY_CODE[code]?.name ?? code;
}
