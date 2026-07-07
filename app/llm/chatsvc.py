"""对话服务：FTS 检索增强 + 引用编号 + 流式回答。"""
import uuid

from sqlalchemy.orm import Session

from app.db import SessionLocal, fts_search, session_scope
from app.log import log_event, now_iso
from app.models import Analysis, ChatMessage, ChatSession, Item, Profile, Source
from app.textutil import beijing_today

RETRIEVE_K = 8
HISTORY_MAX = 8

SUGGESTED_QUESTIONS = [
    "过去两周亦庄/经开区有什么值得注意的政策？",
    "最近有哪些临近截止的申报机会？",
    "AI 制药领域这个月有什么大事？",
    "有哪些和 AI 合规、算法备案相关的新动向？",
    "阿斯利康最近在中国有什么动作？",
]


def retrieve(db: Session, query: str, k: int = RETRIEVE_K) -> list[tuple[Item, Analysis | None, float]]:
    """FTS 召回 + 轻量重排：BM25 为主，红/橙级与新条目小幅加权。"""
    hits = fts_search(db, query, limit=48)
    if not hits:
        return []
    ids = [i for i, _ in hits]
    bm = dict(hits)  # bm25 越小越相关（负值）
    rows = (db.query(Item, Analysis).outerjoin(Analysis, Analysis.item_id == Item.id)
            .filter(Item.id.in_(ids), Item.cluster_of.is_(None)).all())
    today = beijing_today()

    def rank(pair):
        it, an = pair
        score = bm.get(it.id, 0.0)  # 负值，越小越好
        if an and an.tier in ("red", "orange"):
            score -= 1.0
        if it.published_at and (today[:7] == (it.published_at or "")[:7]):
            score -= 0.5  # 当月小幅加权
        return score

    ranked = sorted(rows, key=rank)[:k]
    return [(it, an, bm.get(it.id, 0.0)) for it, an in ranked]


def build_context(db: Session, question: str) -> tuple[str, list[dict]]:
    got = retrieve(db, question)
    citations, blocks = [], []
    for n, (it, an, _) in enumerate(got, start=1):
        citations.append({"n": n, "item_id": it.id, "title": it.title, "url": it.url})
        summary = an.summary if an else (it.excerpt or "")[:200]
        blocks.append(f"【资料{n}】(id={it.id}) {it.published_at}《{it.title}》\n{summary}\n"
                      f"正文节选：{(it.content or '')[:600]}")
    return "\n\n".join(blocks), citations


def system_prompt(db: Session, context_block: str) -> str:
    profile = db.get(Profile, 1)
    return f"""你是「见微」，用户的私人情报分析师，专注中国大陆 AI for Science / 生物医药领域。今天是 {beijing_today()}（北京时间）。

# 用户画像
{profile.narrative if profile else ""}

# 回答规则
- 优先基于下方检索到的情报库资料回答；引用资料时在句末标 [n]（n 为资料编号），可多个。
- 资料不足以回答时明确说"情报库中暂无相关记录"，可以再给出你的一般性判断，但要说明这不是来自情报库。
- 中文回答，简洁直接，先给结论。涉及日期/金额/截止时间必须精确转述，不得改写。

# 检索到的资料
{context_block if context_block else "（本次未检索到相关资料）"}"""


def ensure_session(db: Session, session_id: str | None, first_message: str) -> ChatSession:
    if session_id:
        s = db.get(ChatSession, session_id)
        if s is not None:
            return s
    s = ChatSession(id=uuid.uuid4().hex[:16], title=first_message.strip()[:24] or "新对话")
    db.add(s)
    db.flush()
    return s


def prepare_turn(session_id: str | None, message: str) -> dict:
    """同步准备：建会话、存用户消息、检索、拼 prompt。返回流式所需的一切。"""
    with session_scope() as db:
        s = ensure_session(db, session_id, message)
        db.add(ChatMessage(session_id=s.id, role="user", content=message))
        s.updated_at = now_iso()
        history = (db.query(ChatMessage).filter(ChatMessage.session_id == s.id)
                   .order_by(ChatMessage.id.desc()).limit(HISTORY_MAX + 1).all())
        history = list(reversed(history[1:]))  # 去掉刚插入的这条，按时间正序
        context_block, citations = build_context(db, message)
        messages = [{"role": "system", "content": system_prompt(db, context_block)}]
        for m in history:
            messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": message})
        return {"session_id": s.id, "messages": messages, "citations": citations}


def save_answer(session_id: str, content: str, citations: list[dict]) -> None:
    with session_scope() as db:
        used = {int(n) for n in _cited_ns(content)}
        kept = [c for c in citations if c["n"] in used] or citations
        db.add(ChatMessage(session_id=session_id, role="assistant",
                           content=content, citations=kept))
        s = db.get(ChatSession, session_id)
        if s:
            s.updated_at = now_iso()
    log_event("chat.answered", session=session_id, chars=len(content), citations=len(citations))


def _cited_ns(text: str) -> list[str]:
    import re
    return re.findall(r"\[(\d{1,2})\]", text)
