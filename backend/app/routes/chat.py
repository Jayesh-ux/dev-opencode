from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.orchestrator import Orchestrator, LoopState
from app.tools import list_tools

router = APIRouter(prefix="/api/chat", tags=["chat"])
orchestrator = Orchestrator()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    state: str
    snapshot_path: str | None = None
    error: str | None = None
    token_usage_pct: float = 0.0
    tool_results: list[dict] | None = None
    rotation: bool = False
    tasks: dict | None = None


class StatusResponse(BaseModel):
    state: str
    total_tokens: int
    token_usage_pct: float
    history_length: int
    available_tools: list[str] | None = None
    last_tool_results: list[dict] | None = None
    memory: dict | None = None
    tasks: dict | None = None
    error: str | None = None


class ToolExecuteRequest(BaseModel):
    tool: str
    args: dict = {}


class ToolExecuteResponse(BaseModel):
    success: bool
    output: str
    error: str | None = None


@router.post("")
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    if orchestrator.state == LoopState.PAUSED:
        return ChatResponse(
            response="",
            state=orchestrator.state.value,
            error="Session is paused due to previous error. Resume when ready.",
            token_usage_pct=0,
        )
    if not req.message.strip():
        return ChatResponse(
            response="",
            state=orchestrator.state.value,
            error="Empty message",
            token_usage_pct=0,
        )

    try:
        result = await orchestrator.process_message(req.message)
        return ChatResponse(
            response=result.text,
            state=result.state.value,
            snapshot_path=result.snapshot_path,
            error=result.error,
            token_usage_pct=round(result.token_pct * 100, 1),
            tool_results=result.tool_results,
            rotation=result.rotation,
            tasks=result.tasks,
        )
    except Exception as e:
        return ChatResponse(
            response="",
            state=LoopState.PAUSED.value,
            error=f"Chat processing error: {str(e)}",
            token_usage_pct=0,
        )


@router.get("/status")
async def status_endpoint() -> StatusResponse:
    try:
        s = orchestrator.get_status()
        return StatusResponse(**s)
    except Exception as e:
        return StatusResponse(
            state="PAUSED",
            total_tokens=0,
            token_usage_pct=0.0,
            history_length=0,
            error=f"Status error: {str(e)}",
        )


@router.post("/resume")
async def resume_endpoint() -> ChatResponse:
    if orchestrator.state == LoopState.PAUSED:
        orchestrator.state = LoopState.LISTEN
        return ChatResponse(
            response="Session resumed.",
            state=orchestrator.state.value,
        )
    return ChatResponse(
        response="Session is not paused.",
        state=orchestrator.state.value,
    )


@router.post("/tools")
async def tools_execute(req: ToolExecuteRequest) -> ToolExecuteResponse:
    if req.tool not in {t["name"] for t in list_tools()}:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {req.tool}")
    result = await orchestrator.execute_tool(req.tool, **req.args)
    return ToolExecuteResponse(
        success=result.success,
        output=result.output,
        error=result.error,
    )


@router.get("/tools")
async def tools_list():
    return {"tools": list_tools()}
