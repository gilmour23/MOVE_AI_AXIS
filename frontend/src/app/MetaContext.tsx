import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { fetchMeta } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import type { Meta } from '@/types/domain';

interface MetaContextValue {
  meta: Meta | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
  /** 현재 로그인 선사. 실제 서비스에서는 인증에서 주입된다. */
  carrierId: string;
  /** dev mode 전용 — 실제 선사 화면에서는 노출하지 않는다 (핸드오프 §10). */
  setCarrierId: (carrierId: string) => void;
}

const MetaContext = createContext<MetaContextValue | null>(null);

export function MetaProvider({ children }: { children: ReactNode }) {
  const { data, loading, error, reload } = useAsync(
    (signal) => fetchMeta(signal),
    [],
  );
  const [override, setOverride] = useState<string | null>(null);

  const setCarrierId = useCallback((carrierId: string) => {
    setOverride(carrierId);
  }, []);

  const value = useMemo<MetaContextValue>(
    () => ({
      meta: data,
      loading,
      error,
      reload,
      carrierId: override ?? data?.currentCarrierId ?? '',
      setCarrierId,
    }),
    [data, loading, error, reload, override, setCarrierId],
  );

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
