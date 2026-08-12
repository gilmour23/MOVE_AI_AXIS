/** 챗봇 provider 추상화 (핸드오프 §19.2).
 *  프론트는 자기 백엔드 /api/chat 만 호출한다. API key 는 프론트에 두지 않는다. */

import { apiGet, apiPost } from './client';
import type { ChatReply, ChatStatus } from '@/types/domain';

export interface ChatSendInput {
  carrierId: string;
  message: string;
  conversationId?: string | null;
}

export interface ChatProvider {
  getStatus(signal?: AbortSignal): Promise<ChatStatus>;
  sendMessage(input: ChatSendInput, signal?: AbortSignal): Promise<ChatReply>;
}

/** 실제 API 가 연결되면 백엔드 쪽 provider 만 교체하면 된다. */
export const backendChatProvider: ChatProvider = {
  getStatus(signal) {
    return apiGet<ChatStatus>('/api/chat/status', signal);
  },
  sendMessage(input, signal) {
    return apiPost<ChatReply>(
      '/api/chat',
      {
        carrierId: input.carrierId,
        message: input.message,
        conversationId: input.conversationId ?? null,
      },
      signal,
    );
  },
};

export const SUGGESTED_QUESTIONS = [
  '왜 약목으로 공컨을 보내나요?',
  '우리 40FT 재고는 어떻게 바뀌나요?',
  '이 공컨은 언제 사용 가능한가요?',
  '어떤 열차에 배정됐나요?',
];
