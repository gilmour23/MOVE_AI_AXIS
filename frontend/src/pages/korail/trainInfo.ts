import { hubShortName } from '@/config/hubMeta';
import type { KorailTrain } from '@/types/domain';

/** 중간 경유(정차) 거점 코드.
 *
 *  `workStops` 는 열차가 지나는 계획 stop 목록일 뿐,
 *  그 거점에서 반드시 상·하차가 발생한다는 뜻이 아니다.
 *  (실제 데이터에서도 CAND0156 의 BUGANG 은 상차 0 / 하차 0 이다)
 *  따라서 이 값은 `경유거점`·`정차거점` 으로만 표기하고
 *  `작업거점` 이라고 부르지 않는다. 실제 작업 발생 여부는
 *  station operations 의 Box 값으로만 판정한다. */
export function viaHubCodes(train: KorailTrain): string[] {
  return train.workStops.filter(
    (code) =>
      code && code !== train.originTerminal && code !== train.destinationTerminal,
  );
}

/** '부강 · 약목' — 중간 경유가 없으면 null. */
export function viaHubLabel(train: KorailTrain): string | null {
  const codes = viaHubCodes(train);
  if (codes.length === 0) return null;
  return codes.map(hubShortName).join(' · ');
}

/** 열차 OD 표기 — terminal 코드가 없으면 route 문자열의 양 끝을 쓴다. */
export function trainOdLabel(train: KorailTrain): string {
  const from = train.originTerminal ?? train.workStops[0] ?? '';
  const to =
    train.destinationTerminal ?? train.workStops[train.workStops.length - 1] ?? '';
  return `${hubShortName(from)} → ${hubShortName(to)}`;
}
