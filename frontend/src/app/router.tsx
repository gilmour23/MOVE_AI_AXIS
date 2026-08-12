import { Navigate, Route, Routes } from 'react-router-dom';
import { LandingPage } from '@/pages/LandingPage';
import { OverviewPage } from '@/pages/OverviewPage';
import { InventoryPage } from '@/pages/InventoryPage';
import { OptimizationPage } from '@/pages/OptimizationPage';
import { TransportPage } from '@/pages/TransportPage';
import { TrackingPage } from '@/pages/TrackingPage';
import { KorailOverviewPage } from '@/pages/korail/KorailOverviewPage';
import { KorailNeedsPage } from '@/pages/korail/KorailNeedsPage';
import { KorailTrainsPage } from '@/pages/korail/KorailTrainsPage';
import { KorailInventoryPage } from '@/pages/korail/KorailInventoryPage';
import { KorailInsightsPage } from '@/pages/korail/KorailInsightsPage';
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

      {/* KORAIL Control Tower */}
      <Route path="/korail" element={<KorailOverviewPage />} />
      <Route path="/korail/needs" element={<KorailNeedsPage />} />
      <Route path="/korail/trains" element={<KorailTrainsPage />} />
      <Route path="/korail/inventory" element={<KorailInventoryPage />} />
      <Route path="/korail/insights" element={<KorailInsightsPage />} />
      <Route path="/korail/operations" element={<KorailOperationsPage />} />

      {/* 이전 경로 호환 */}
      <Route path="/inventory" element={<Navigate to="/carrier/inventory" replace />} />
      <Route path="/optimization" element={<Navigate to="/carrier/plan" replace />} />
      <Route path="/comparison" element={<Navigate to="/carrier/transport" replace />} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
