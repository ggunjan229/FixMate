"""FixMate Helper API endpoint."""
from fastapi import APIRouter, HTTPException

from fixmate.schemas import AssistantInput
from fixmate.services.assistant_context import get_assistant_context
from fixmate.services.llm_assistant import AssistantServiceError, answer_question

router = APIRouter()


@router.post("/api/assistant")
async def assistant(payload: AssistantInput):
    """Answer a question with an LLM, grounded in current platform facts."""
    try:
        context = get_assistant_context()
        answer = await answer_question(
            question=payload.question,
            language=payload.language,
            platform_context=context,
        )
    except AssistantServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"answer": answer, "action": "ask", "mode": "ai_service"}
