import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Bot } from 'lucide-react';
import { ChatDrawer } from './ChatDrawer';
import { useCarrierId } from '@/app/MetaContext';
import { roleFromPath } from '@/app/roles';
import styles from './Chat.module.css';

/** 모든 페이지 우측 하단에 고정된다.
 *  현재 화면 역할을 함께 넘겨 Copilot 이 알맞은 컨텍스트만 사용하도록 한다. */
export function ChatFloatingButton() {
  const [open, setOpen] = useState(false);
  const carrierId = useCarrierId();
  const location = useLocation();
  const role = roleFromPath(location.pathname) ?? 'carrier';

  if (open) {
    return (
      <ChatDrawer carrierId={carrierId} role={role} onClose={() => setOpen(false)} />
    );
  }

  return (
    <button
      type="button"
      className={styles.fab}
      onClick={() => setOpen(true)}
      aria-label="MOVE-AI Copilot 열기"
      title="MOVE-AI Copilot"
    >
      <Bot size={23} />
    </button>
  );
}
