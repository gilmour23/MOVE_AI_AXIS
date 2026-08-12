/** 챗봇 provider 추상화 (핸드오프 §19.2).
 *  프론트는 자기 백엔드 /api/chat 만 호출한다. API key 는 프론트에 두지 않는다. */

import { apiGet, apiPost } from './client';
import type { ChatReply, ChatStatus } from '@/types/domain';

export interface ChatSendInput {
  carrierId: string;
  message: string;
  conversationId?: string | null;
  /** 어느 화면에서 물었는지 — 서버리스 함수가 컨텍스트를 고를 때 쓴다. */
  role?: 'carrier' | 'korail';
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
        role: input.role ?? 'carrier',
      },
      signal,
    );
  },
};

export const SUGGESTED_QUESTIONS: Record<'carrier' | 'korail', string[]> = {
  carrier: [
    '왜 약목으로 공컨을 보내나요?',
    'REC0002는 어떤 열차에 배정됐나요?',
    '우리 40FT 재고는 재배치 후 어떻게 바뀌나요?',
    '철도가 트럭보다 얼마나 저렴한가요?',
  ],
  korail: [
    'CAND0292에는 어떤 선사 물량이 실려 있나요?',
    '적재율이 가장 낮은 구간은 어디인가요?',
    '재배치로 부족이 가장 많이 줄어든 거점은?',
    '철도로 해결되지 않은 수요는 얼마나 되나요?',
  ],
};
