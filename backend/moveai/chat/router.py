"""챗봇 프록시 엔드포인트.

프론트엔드는 오직 이 엔드포인트만 호출한다. 외부 API key 는 백엔드에만 존재한다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from moveai import config
from moveai.chat import provider as chat_provider
from moveai.result_store import store
from moveai.selectors import optimization as opt

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 변경/재계산 요청 판별용 키워드. 매칭되면 외부 API 를 호출하지 않고 정책 문구로 응답한다.
_MUTATION_KEYWORDS = (
    "바꿔",
    "변경",
    "수정",
    "다시 계산",
    "재계산",
    "재최적화",
    "다시 최적화",
    "취소",
    "거절",
    "수락",
    "예약",
    "배차",
)


class ChatMessageRequest(BaseModel):
    carrierId: str | None = None
    message: str = Field(min_length=1)
    conversationId: str | None = None


class ChatMessageResponse(BaseModel):
    reply: str
    conversationId: str | None = None
    sources: list[str] = []
    readOnly: bool = True


def _build_context(carrier_id: str) -> dict:
    """current carrier 로 한정된 근거 데이터만 구성한다."""
    explanation = store.explanation_context(carrier_id)
    return {
        "recommendations": opt.recommendations(store, carrier_id),
        "impacts": opt.inventory_impacts(store, carrier_id),
        "serviceSummary": opt.carrier_service_summary(store, carrier_id),
        "explanation": explanation.to_dict(orient="records")
        if not explanation.empty
        else [],
    }


@router.get("/status")
def chat_status() -> dict:
    provider = chat_provider.get_provider()
    return {
        "configured": getattr(provider, "configured", False),
        "readOnly": True,
        "allowedSources": list(chat_provider.ALLOWED_CONTEXT_SOURCES),
    }


@router.post("", response_model=ChatMessageResponse)
def send_message(body: ChatMessageRequest) -> ChatMessageResponse:
    carrier_id = body.carrierId or config.DEMO_CARRIER_ID

    if any(keyword in body.message for keyword in _MUTATION_KEYWORDS):
        return ChatMessageResponse(
            reply=chat_provider.MUTATION_REFUSAL,
            conversationId=body.conversationId,
        )

    provider = chat_provider.get_provider()
    try:
        result = provider.send_message(
            chat_provider.ChatRequest(
                carrier_id=carrier_id,
                message=body.message,
                conversation_id=body.conversationId,
                context=_build_context(carrier_id),
            )
        )
    except chat_provider.ChatNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CHAT_API_NOT_CONFIGURED",
                "message": "챗봇 API가 아직 연결되지 않았습니다.",
            },
        )
    except Exception as exc:  # 외부 API 오류
        raise HTTPException(
            status_code=502,
            detail={"code": "CHAT_API_ERROR", "message": str(exc)},
        )

    return ChatMessageResponse(
        reply=result.reply,
        conversationId=result.conversation_id,
        sources=result.sources,
    )
