import { useState } from 'react';
import { Bot } from 'lucide-react';
import { ChatDrawer } from './ChatDrawer';
import { useCarrierId } from '@/app/MetaContext';
import styles from './Chat.module.css';

/** 모든 페이지 우측 하단에 고정된다 (핸드오프 §19.1). */
export function ChatFloatingButton() {
  const [open, setOpen] = useState(false);
  const carrierId = useCarrierId();

  if (open) {
    return <ChatDrawer carrierId={carrierId} onClose={() => setOpen(false)} />;
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
