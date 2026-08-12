import { Navigate, Route, Routes } from 'react-router-dom';
import { LandingPage } from '@/pages/LandingPage';
import { OverviewPage } from '@/pages/OverviewPage';
import { InventoryPage } from '@/pages/InventoryPage';
import { OptimizationPage } from '@/pages/OptimizationPage';
import { TransportPage } from '@/pages/TransportPage';
import { TrackingPage } from '@/pages/TrackingPage';
import { KorailOverviewPage } from '@/pages/korail/KorailOverviewPage';
import { KorailCargoPage } from '@/pages/korail/KorailCargoPage';
import { KorailTrainsPage } from '@/pages/korail/KorailTrainsPage';
import { KorailOperationsPage } from '@/pages/korail/KorailOperationsPage';

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />

      {/* Carrier Portal */}
      <Route path="/carrier" element={<OverviewPage />} />
      <Route path="/carrier/inventory" element={<InventoryPage />} />
      <Route path="/carrier/plan" element={<OptimizationPage />} />
      <Route path="/carrier/transport" element={<TransportPage />} />
      <Route path="/carrier/tracking" element={<TrackingPage />} />

      {/* KORAIL Control Tower — 종합계획 → 운송물량 → 열차운행 → 거점작업 */}
      <Route path="/korail" element={<KorailOverviewPage />} />
      <Route path="/korail/cargo" element={<KorailCargoPage />} />
      <Route path="/korail/trains" element={<KorailTrainsPage />} />
      <Route path="/korail/operations" element={<KorailOperationsPage />} />

      {/* 이전 경로 호환 */}
      <Route path="/korail/needs" element={<Navigate to="/korail/cargo" replace />} />
      <Route path="/korail/inventory" element={<Navigate to="/korail" replace />} />
      <Route path="/korail/insights" element={<Navigate to="/korail" replace />} />
      <Route path="/inventory" element={<Navigate to="/carrier/inventory" replace />} />
      <Route path="/optimization" element={<Navigate to="/carrier/plan" replace />} />
      <Route path="/comparison" element={<Navigate to="/carrier/transport" replace />} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
