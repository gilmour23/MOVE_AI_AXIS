import { Link } from 'react-router-dom';
import { ArrowRight, Ship, TowerControl } from 'lucide-react';
import { fetchKorailOverview } from '@/api/carrier';
import { useAsync } from '@/hooks/useAsync';
import { useMeta } from '@/app/MetaContext';
import { ROLES } from '@/app/roles';
import { formatNumber, formatPercent } from '@/lib/format';
import styles from './LandingPage.module.css';

const ICONS = { carrier: Ship, korail: TowerControl } as const;

/** 역할 선택 진입 화면. B2B 플랫폼 entry 수준으로 간결하게 유지한다. */
export function LandingPage() {
  const { meta } = useMeta();
  const { data } = useAsync((signal) => fetchKorailOverview(signal), []);

  return (
    <div className={styles.wrap}>
      <span className={styles.eyebrow}>MOVE-AI</span>
      <h1 className={styles.title}>공컨테이너 철도 공동 재배치 플랫폼</h1>
      <p className={styles.subtitle}>
        여러 선사의 공컨테이너 수요를 함께 최적화해 신규 공컨 전용 화물열차를 배차합니다.
        컨테이너 소유권은 선사별로 유지되며, 열차 Capacity 만 공동 이용합니다.
      </p>

      <div className={styles.cards}>
        {(['carrier', 'korail'] as const).map((id) => {
          const role = ROLES[id];
          const Icon = ICONS[id];
          return (
            <Link key={id} to={role.home} className={styles.card}>
              <span className={styles.cardIcon}>
                <Icon size={19} />
              </span>
              <span className={styles.cardTitle}>{role.label}</span>
              <span className={styles.cardDesc}>{role.description}</span>
              <span className={styles.cardMenu}>
                {role.nav.map((n) => n.label).join(' · ')}
              </span>
              <span className={styles.cardLink}>
                들어가기 <ArrowRight size={14} />
              </span>
            </Link>
          );
        })}
      </div>

      {data && (
        <div className={styles.factStrip}>
          <Fact label="Service Need" value={`${formatNumber(data.serviceNeedTeu)} TEU`} />
          <Fact label="철도 배정" value={`${formatNumber(data.railServedTeu)} TEU`} />
          <Fact label="커버리지" value={formatPercent(data.railCoverage)} />
          <Fact label="선정 열차" value={`${data.selectedTrainCount}편`} />
          <Fact label="참여 선사" value={`${data.participatingCarrierCount}개`} />
        </div>
      )}

      <p className={styles.note}>
        화면에 표시되는 모든 최적화 수치는 AXIS MOVE-AI MILP v7.1 결과
        ({meta?.scenario ?? 'AXIS_INTEGRATED'})에서 계산됩니다.
        {meta?.isSyntheticCarrierData && ' 현재 데이터는 합성 데모 데이터입니다.'}
        {meta?.isPrototypeTimetable && ' 운행시각은 프로토타입 운행후보 기준입니다.'}
      </p>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.fact}>
      <span className={styles.factLabel}>{label}</span>
      <span className={styles.factValue}>{value}</span>
    </div>
  );
}
