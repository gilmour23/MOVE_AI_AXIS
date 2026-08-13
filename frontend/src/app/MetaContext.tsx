import { createContext, useContext, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchMeta, fetchWeekMeta } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import type { GlobalMeta, WeekMeta, WeekSummary } from '@/types/domain';

/** 전역 계획 컨텍스트.
 *
 *  두 포털이 같은 planning context(주차)를 공유한다. 역할별 세부 선택은 공유하지 않는다.
 *  weekId 는 URL `?week=` 와 동기화되어 딥링크가 항상 같은 주차를 연다. */
interface MetaContextValue {
  meta: GlobalMeta | null;
  weekMeta: WeekMeta | null;
  weeks: WeekSummary[];
  loading: boolean;
  error: Error | null;
  reload: () => void;
  /** canonical weekId (W01_2025-07-01). 준비 전에는 빈 문자열. */
  weekId: string;
  setWeekId: (weekId: string) => void;
  /** 현재 로그인 선사. 실제 서비스에서는 인증에서 주입된다. */
  carrierId: string;
}

const MetaContext = createContext<MetaContextValue | null>(null);

export function MetaProvider({ children }: { children: ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    data: meta,
    loading: metaLoading,
    error: metaError,
    reload,
  } = useAsync((signal) => fetchMeta(signal), []);

  const weeks = useMemo(() => meta?.weeks ?? [], [meta]);
  const requested = searchParams.get('week');

  // URL 의 week 이 실제 존재할 때만 쓴다.
  // 없는 주차를 그대로 신뢰하면 빈 화면 대신 엉뚱한 주차가 열린다.
  const weekId = useMemo(() => {
    if (!weeks.length) return '';
    const valid = weeks.some((w) => w.weekId === requested);
    return valid && requested ? requested : (meta?.defaultWeekId ?? weeks[0].weekId);
  }, [weeks, requested, meta]);

  const {
    data: weekMeta,
    loading: weekLoading,
    error: weekError,
  } = useAsync(
    (signal) => (weekId ? fetchWeekMeta(weekId, signal) : Promise.resolve(null)),
    [weekId],
  );

  const value = useMemo<MetaContextValue>(() => {
    /** 주차를 바꾸면 그 주차에 존재하지 않는 선택(train/recommendation/date)은 버린다.
     *  남겨두면 화면이 빈 상세를 열거나 이전 주차 값을 계속 보여준다. */
    const setWeekId = (next: string) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          params.set('week', next);
          for (const key of ['train', 'recommendation', 'date', 'hub']) {
            params.delete(key);
          }
          return params;
        },
        { replace: false },
      );
    };

    return {
      meta,
      weekMeta,
      weeks,
      loading: metaLoading || weekLoading,
      error: metaError ?? weekError,
      reload,
      weekId,
      setWeekId,
      carrierId: meta?.currentCarrierId ?? '',
    };
  }, [
    meta,
    weekMeta,
    weeks,
    metaLoading,
    weekLoading,
    metaError,
    weekError,
    reload,
    weekId,
    setSearchParams,
  ]);

  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>;
}

export function useMeta(): MetaContextValue {
  const context = useContext(MetaContext);
  if (!context) {
    throw new Error('useMeta 는 MetaProvider 안에서만 사용할 수 있습니다.');
  }
  return context;
}

/** carrierId 가 준비되기 전에는 데이터 요청을 하지 않는다. */
export function useCarrierId(): string {
  return useMeta().carrierId;
}

/** weekId 가 빈 문자열이면 아직 manifest 로딩 전이다. 요청을 보내지 않는다. */
export function useWeekId(): string {
  return useMeta().weekId;
}
