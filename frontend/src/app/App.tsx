import { BrowserRouter } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { ChatFloatingButton } from '@/components/chatbot/ChatFloatingButton';
import { MetaProvider, useMeta } from './MetaContext';
import { AppRoutes } from './router';
import { ErrorState } from '@/components/common/States';
import { PageContainer } from '@/components/layout/PageContainer';

export function App() {
  return (
    <BrowserRouter>
      <MetaProvider>
        <AppShell>
          <AppContent />
        </AppShell>
        <ChatFloatingButton />
      </MetaProvider>
    </BrowserRouter>
  );
}

function AppContent() {
  const { error, reload, loading } = useMeta();

  // meta 로드 자체가 실패하면 결과 파일/백엔드 문제이므로 페이지 대신 에러 상태를 보여준다.
  if (error) {
    return (
      <PageContainer title="MOVE-AI 선사 인터페이스">
        <ErrorState error={error} onRetry={reload} />
      </PageContainer>
    );
  }

  if (loading) return null;

  return <AppRoutes />;
}
