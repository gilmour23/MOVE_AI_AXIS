import { Navigate, Route, Routes } from 'react-router-dom';
import { OverviewPage } from '@/pages/OverviewPage';
import { InventoryPage } from '@/pages/InventoryPage';
import { OptimizationPage } from '@/pages/OptimizationPage';
import { ComparisonPlaceholderPage } from '@/pages/ComparisonPlaceholderPage';

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/inventory" element={<InventoryPage />} />
      <Route path="/optimization" element={<OptimizationPage />} />
      <Route path="/comparison" element={<ComparisonPlaceholderPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
