"""챗봇 provider 추상화 (핸드오프 §19).

Copilot 은 최적화 controller 가 아니라 read-only explanation layer 다.
- API key 는 백엔드에만 둔다. 프론트로 내려보내지 않는다.
- 미설정 시 503 CHAT_API_NOT_CONFIGURED. 가짜 AI 답변을 하드코딩하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from moveai import config

# 챗봇이 조회할 수 있는 데이터는 current carrier 기준으로 아래 파일뿐이다 (§19.3).
ALLOWED_CONTEXT_SOURCES = (
    "CARRIER_RECOMMENDATIONS_<CARRIER>.csv",
    "RECOMMENDATION_EXPLANATION_CONTEXT_<CARRIER>.csv",
    "CARRIER_INVENTORY_TIMELINE.csv",
    "INVENTORY_IMPACT_SUMMARY.csv",
    "CARRIER_SERVICE_SUMMARY.csv",
    "SERVICE_NEED_RESULT.csv",
)

READ_ONLY_POLICY = (
    "당신은 MOVE-AI Copilot 입니다. 이미 계산된 최적화 결과를 조회하고 설명하는 "
    "역할만 수행합니다. 수량·조건 변경, 재최적화, 열차 재배정, 안전재고 변경 요청은 "
    "수행하지 않습니다. 제공된 컨텍스트에 없는 숫자를 새로 만들어내지 마십시오. "
    "다른 선사의 데이터는 컨텍스트에 포함되지 않으며 추측해서도 안 됩니다."
)

MUTATION_REFUSAL = (
    "현재 Copilot은 최적화 결과를 조회하고 설명하는 기능만 제공합니다.\n"
    "최적화 수량 또는 조건을 변경하거나 재계산하지 않습니다."
)


class ChatNotConfiguredError(RuntimeError):
    """CHAT_API_URL 이 설정되지 않은 상태."""


@dataclass
class ChatRequest:
    carrier_id: str
    message: str
    conversation_id: str | None = None
    context: dict = field(default_factory=dict)


@dataclass
class ChatResponse:
    reply: str
    conversation_id: str | None = None
    sources: list[str] = field(default_factory=list)


class ChatProvider(Protocol):
    def send_message(self, request: ChatRequest) -> ChatResponse: ...


class NotConfiguredChatProvider:
    """API 미연결 상태. 호출되면 항상 예외를 던진다."""

    configured = False

    def send_message(self, request: ChatRequest) -> ChatResponse:
        raise ChatNotConfiguredError(
            "CHAT_API_URL 이 설정되지 않았습니다."
        )


class HttpChatProvider:
    """외부 챗봇 API 프록시.

    실제 API 스펙이 확정되면 payload/응답 파싱만 이 클래스에서 조정한다.
    """

    configured = True

    def __init__(self, api_url: str, api_key: str):
        self._api_url = api_url
        self._api_key = api_key

    def send_message(self, request: ChatRequest) -> ChatResponse:
        import httpx  # 미설정 환경에서는 import 하지 않는다

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "policy": READ_ONLY_POLICY,
            "carrierId": request.carrier_id,
            "message": request.message,
            "conversationId": request.conversation_id,
            "context": request.context,
        }

        with httpx.Client(timeout=30.0) as client:
            res = client.post(self._api_url, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()

        return ChatResponse(
            reply=data.get("reply") or data.get("message") or "",
            conversation_id=data.get("conversationId") or request.conversation_id,
            sources=data.get("sources") or [],
        )


def get_provider() -> ChatProvider:
    if config.CHAT_API_URL:
        return HttpChatProvider(config.CHAT_API_URL, config.CHAT_API_KEY)
    return NotConfiguredChatProvider()
