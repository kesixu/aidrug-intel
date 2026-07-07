"""对话 API：会话管理 + SSE 流式回答。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.llm import chatsvc
from app.llm.client import LlmError, chat_stream
from app.models import ChatMessage, ChatSession

router = APIRouter(tags=["chat"])


@router.get("/chat/sessions")
def list_sessions(db: Session = Depends(get_db)):
    rows = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).limit(30).all()
    return {"sessions": [{"id": s.id, "title": s.title, "updated_at": s.updated_at} for s in rows],
            "suggested": chatsvc.SUGGESTED_QUESTIONS}


@router.get("/chat/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(ChatSession, session_id)
    if s is None:
        raise HTTPException(404, "会话不存在")
    msgs = (db.query(ChatMessage).filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id).all())
    return {"id": s.id, "title": s.title,
            "messages": [{"role": m.role, "content": m.content,
                          "citations": m.citations or [], "created_at": m.created_at}
                         for m in msgs]}


@router.delete("/chat/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(ChatSession, session_id)
    if s is None:
        raise HTTPException(404, "会话不存在")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(s)
    db.commit()
    return {"ok": True}


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_sse(body: ChatIn):
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "message 不能为空")
    if len(message) > 4000:
        raise HTTPException(400, "message 过长")
    turn = chatsvc.prepare_turn(body.session_id, message)

    async def gen():
        yield _sse("meta", {"session_id": turn["session_id"], "citations": turn["citations"]})
        parts: list[str] = []
        try:
            async for delta in chat_stream(turn["messages"], model=settings.deepseek_model_pro,
                                           purpose="chat"):
                parts.append(delta)
                yield _sse("delta", {"text": delta})
        except LlmError as e:
            yield _sse("error", {"message": f"模型服务暂时不可用：{e}"})
            return
        answer = "".join(parts)
        chatsvc.save_answer(turn["session_id"], answer, turn["citations"])
        yield _sse("done", {"session_id": turn["session_id"]})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # 穿透 nginx 反代缓冲，免改 nginx 配置
        "Connection": "keep-alive",
    })
