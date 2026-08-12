import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/common/States';
import { SizeTag } from '@/components/optimization/SizeTag';
import { fetchOptimization } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useCarrierId } from '@/app/MetaContext';
import { formatBoxes, formatDateShort, formatTime } from '@/lib/format';
import styles from './korail/Korail.module.css';

/** 운송 현황 — 계획된 각 재배치안의 출발·도착·사용 가능 시각을 한 줄로 본다.
 *
 *  실시간 위치 추적이 아니라 최적화 결과의 계획 시각을 보여주는 화면이다.
 *  실제 운행 실적 데이터가 없으므로 상태를 임의로 만들지 않는다. */
export function TrackingPage() {
  const carrierId = useCarrierId();
  const { data, loading, error, reload } = useAsync(
    (signal) => (carrierId ? fetchOptimization(carrierId, signal) : Promise.resolve(null)),
    [carrierId],
  );

  return (
    <PageContainer
      title="운송 현황"
      description="계획된 재배치안의 열차별 출발·도착·사용 가능 시각입니다."
    >
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && (
        <Card>
          <LoadingSkeleton rows={4} height={24} />
        </Card>
      )}

      {data && data.recommendations.length === 0 && (
        <Card>
          <EmptyState title="추적할 재배치안이 없습니다." />
        </Card>
      )}

      {data && data.recommendations.length > 0 && (
        <Card title="자사 재배치안 운송 계획" subtitle="출발시간 순">
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>추천</th>
                  <th>열차</th>
                  <th>구간</th>
                  <th>규격·물량</th>
                  <th>출발</th>
                  <th>도착</th>
                  <th>사용 가능</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {data.recommendations.map((rec) => (
                  <tr key={rec.recommendationId}>
                    <td className={styles.mono}>{rec.recommendationId}</td>
                    <td>
                      <Link
                        className={styles.carrierLink}
                        to={`/korail/trains?train=${rec.trainId}`}
                      >
                        {rec.trainId} <ArrowRight size={12} />
                      </Link>
                    </td>
                    <td className={styles.muted}>
                      {rec.originName} → {rec.destinationName}
                    </td>
                    <td>
                      <SizeTag size={rec.size} /> {formatBoxes(rec.quantityBoxes)}
                    </td>
                    <td>
                      {formatTime(rec.departureTime)}
                      <div className={styles.kpiSub}>{formatDateShort(rec.departureTime)}</div>
                    </td>
                    <td>
                      {formatTime(rec.arrivalTime)}
                      <div className={styles.kpiSub}>{formatDateShort(rec.arrivalTime)}</div>
                    </td>
                    <td>
                      {formatTime(rec.availableTime)}
                      <div className={styles.kpiSub}>{formatDateShort(rec.availableTime)}</div>
                    </td>
                    <td>
                      <StatusBadge tone="info" small>
                        계획 확정
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={styles.note} style={{ marginTop: 12 }}>
            이 화면은 최적화 결과의 <strong>계획 시각</strong>을 보여줍니다.
            실시간 위치·운행 실적 데이터는 현재 연동되어 있지 않으므로 진행 상태를
            임의로 생성하지 않습니다.
          </div>
        </Card>
      )}
    </PageContainer>
  );
}
