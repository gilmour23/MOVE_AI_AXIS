import { GitCompareArrows } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/common/Card';
import { EmptyState } from '@/components/common/States';

/** 운송비교 상세는 다른 팀원이 담당한다.
 *  실제 비용/시간/탄소 비교 숫자를 임의로 만들지 않는다 (핸드오프 §1.1, §15.3). */
export function ComparisonPlaceholderPage() {
  return (
    <PageContainer
      title="운송비교"
      description="철도와 트럭 운송의 비용·시간·탄소 비교 화면입니다."
    >
      <Card>
        <EmptyState
          icon={<GitCompareArrows size={18} />}
          title="운송비교 화면은 준비 중입니다."
          description={
            '이 화면은 별도로 개발 중이며, 연결되면 철도·트럭의 비용, 소요시간, 탄소 배출량 비교가 표시됩니다.\n비교 수치는 확정된 산출 기준이 연결된 뒤에만 표시합니다.'
          }
        />
      </Card>
    </PageContainer>
  );
}
