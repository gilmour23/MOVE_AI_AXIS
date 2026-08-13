import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Bot } from 'lucide-react';
import { ChatDrawer } from './ChatDrawer';
import { useCarrierId } from '@/app/MetaContext';
import { roleFromPath } from '@/app/roles';
import styles from './Chat.module.css';

/** 선사 화면 우측 하단에 고정되는 Copilot 진입점.
 *
 *  KORAIL 화면에는 두지 않는다 — 핸드오프 §06: Carrier 요구만 있으므로
 *  챗봇을 KORAIL 에 억지로 복제하지 않는다. 랜딩(/)에도 선사 컨텍스트가
 *  없으므로 보여주지 않는다. */
export function ChatFloatingButton() {
  const [open, setOpen] = useState(false);
  const carrierId = useCarrierId();
  const location = useLocation();
  const role = roleFromPath(location.pathname);

  if (role !== 'carrier') return null;

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
