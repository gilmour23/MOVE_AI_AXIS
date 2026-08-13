import { useEffect, useRef, useState } from 'react';
import { Bot, Send, X } from 'lucide-react';
import { backendChatProvider, SUGGESTED_QUESTIONS } from '@/api/chat';
import type { ChatHistoryTurn } from '@/api/chat';
import { useMeta } from '@/app/MetaContext';
import { ApiError } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import styles from './Chat.module.css';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
}

interface ChatDrawerProps {
  carrierId: string;
  role: 'carrier' | 'korail';
  onClose: () => void;
}

const NOT_CONFIGURED_TEXT =
  '챗봇 API가 아직 연결되지 않았습니다.\nAPI 연결 후 현재 최적화 결과를 기반으로 질의할 수 있습니다.';

/** Copilot 은 read-only 설명 interface 다 (핸드오프 §19).
 *  API 가 없을 때 가짜 AI 답변을 하드코딩하지 않는다. */
export function ChatDrawer({ carrierId, role, onClose }: ChatDrawerProps) {
  const { weekId } = useMeta();
  const status = useAsync((signal) => backendChatProvider.getStatus(signal), []);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const conversationId = useRef<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  const configured = status.data?.configured ?? false;
  const disabled = !configured || sending;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [messages]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;

    setMessages((current) => [
      ...current,
      { id: `u-${Date.now()}`, role: 'user', text: trimmed },
    ]);
    setInput('');
    setSending(true);

    try {
      // 오류 턴은 이력에서 뺀다. 모델이 자기 오류 문구를 문맥으로 삼지 않도록.
      const history: ChatHistoryTurn[] = messages
        .filter((m) => m.role !== 'error')
        .map((m) => ({
          role: m.role === 'assistant' ? ('model' as const) : ('user' as const),
          text: m.text,
        }));

      const reply = await backendChatProvider.sendMessage({
        carrierId,
        role,
        message: trimmed,
        conversationId: conversationId.current,
        weekId,
        history,
      });
      conversationId.current = reply.conversationId ?? conversationId.current;
      setMessages((current) => [
        ...current,
        { id: `a-${Date.now()}`, role: 'assistant', text: reply.reply },
      ]);
    } catch (error) {
      const message =
        error instanceof ApiError && error.code === 'CHAT_API_NOT_CONFIGURED'
          ? NOT_CONFIGURED_TEXT
          : (error as Error).message;
      setMessages((current) => [
        ...current,
        { id: `e-${Date.now()}`, role: 'error', text: message },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <aside className={styles.drawer} role="dialog" aria-label="MOVE-AI Copilot">
      <header className={styles.header}>
        <span className={styles.headerIcon}>
          <Bot size={18} />
        </span>
        <div className={styles.headerText}>
          <div className={styles.headerTitle}>MOVE-AI Copilot</div>
          <div className={styles.headerSub}>조회·설명 전용</div>
        </div>
        <button type="button" className={styles.close} onClick={onClose} aria-label="닫기">
          <X size={17} />
        </button>
      </header>

      <div className={styles.body} ref={bodyRef}>
        {messages.length === 0 && (
          <>
            <p className={styles.intro}>
              이미 계산된 최적화 결과를 조회하고 설명해 드립니다. 수량 변경·재최적화는
              수행하지 않습니다.
            </p>
            {!status.loading && !configured && (
              <div className={styles.notice}>{NOT_CONFIGURED_TEXT}</div>
            )}
            <div className={styles.suggestions}>
              <span className={styles.suggestionLabel}>추천 질문</span>
              {SUGGESTED_QUESTIONS[role].map((question) => (
                <button
                  key={question}
                  type="button"
                  className={styles.suggestion}
                  onClick={() => void send(question)}
                  disabled={disabled}
                >
                  {question}
                </button>
              ))}
            </div>
          </>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={[
              styles.message,
              message.role === 'user' ? styles.userMessage : '',
              message.role === 'assistant' ? styles.botMessage : '',
              message.role === 'error' ? styles.errorMessage : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            {message.text}
          </div>
        ))}
      </div>

      <div className={styles.footer}>
        <form
          className={styles.inputRow}
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
        >
          <textarea
            className={styles.input}
            rows={1}
            value={input}
            disabled={disabled}
            placeholder={
              configured ? '최적화 결과에 대해 질문해보세요' : 'API 연결 후 사용할 수 있습니다'
            }
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void send(input);
              }
            }}
            aria-label="질문 입력"
          />
          <button
            type="submit"
            className={styles.send}
            disabled={disabled || !input.trim()}
            aria-label="보내기"
          >
            <Send size={16} />
          </button>
        </form>
        <p className={styles.policyNote}>
          조회·설명 전용 · 최적화 결과를 변경하거나 재계산하지 않습니다
        </p>
      </div>
    </aside>
  );
}
