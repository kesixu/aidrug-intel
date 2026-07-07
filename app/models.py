"""Schema v2 数据模型。旧表 intel_entries 不在此定义、原样保留（seeds.py 负责导入）。"""
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.log import now_iso


class Base(DeclarativeBase):
    pass


class KV(Base):
    __tablename__ = "kv_meta"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Source(Base):
    """情报源运行时状态；定义的权威来源是 config/sources.yml（启动时同步进来）。"""
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    tier: Mapped[int] = mapped_column(Integer, default=3)
    kind: Mapped[str] = mapped_column(String, default="html")  # rss | html | manual
    url: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # 选择器/门控/正文抓取等
    etag: Mapped[str] = mapped_column(String, default="")
    last_modified: Mapped[str] = mapped_column(String, default="")
    last_fetch_at: Mapped[str] = mapped_column(String, default="")
    last_success_at: Mapped[str] = mapped_column(String, default="")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    health: Mapped[str] = mapped_column(String, default="unknown")  # ok|degraded|down|unknown|disabled
    note: Mapped[str] = mapped_column(Text, default="")


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String, unique=True, index=True)  # sha1(规范化URL)
    source_id: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[str] = mapped_column(String, default="", index=True)  # YYYY-MM-DD
    fetched_at: Mapped[str] = mapped_column(String, default=now_iso)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="new", index=True)  # new|analyzed|filtered|failed
    simhash: Mapped[str] = mapped_column(String, default="0")
    cluster_of: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 同事件重复指向首发条目


class Analysis(Base):
    __tablename__ = "analyses"
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String, default="其他", index=True)
    event_type: Mapped[str] = mapped_column(String, default="")
    importance: Mapped[int] = mapped_column(Integer, default=0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    tier: Mapped[str] = mapped_column(String, default="gray", index=True)  # red|orange|blue|gray
    lens_scores: Mapped[list] = mapped_column(JSON, default=list)  # [{lens_id,score,reason}]
    action_hint: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[str | None] = mapped_column(String, nullable=True)  # 申报/征求意见截止日
    signal: Mapped[str] = mapped_column(String, default="中")  # 强|中|弱
    policy_family: Mapped[str] = mapped_column(String, default="", index=True)
    policy_stage: Mapped[str] = mapped_column(String, default="")
    entities: Mapped[list] = mapped_column(JSON, default=list)  # [{name,kind}]
    model: Mapped[str] = mapped_column(String, default="")
    analyzed_at: Mapped[str] = mapped_column(String, default=now_iso)


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String, default="other")  # company|agency|park|program|person|other
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    watch: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String, default=now_iso)


class ItemEntity(Base):
    __tablename__ = "item_entities"
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)


class Lens(Base):
    """决策维度：个性化评分的核心。weight 由用户调，description 是给 LLM 的判据。"""
    __tablename__ = "lenses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=0.2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Profile(Base):
    __tablename__ = "profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 恒为 1
    narrative: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)  # 媒体源门控 + 检索加权
    updated_at: Mapped[str] = mapped_column(String, default=now_iso)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String)  # useful|irrelevant|star|unstar|follow_up|read|open_url
    created_at: Mapped[str] = mapped_column(String, default=now_iso, index=True)


class Brief(Base):
    __tablename__ = "briefs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String, unique=True, index=True)  # 北京时间 YYYY-MM-DD
    content_md: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # {item_ids, stats}
    created_at: Mapped[str] = mapped_column(String, default=now_iso)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, default="新对话")
    created_at: Mapped[str] = mapped_column(String, default=now_iso)
    updated_at: Mapped[str] = mapped_column(String, default=now_iso, index=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String)  # user|assistant
    content: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)  # [{n,item_id,title,url}]
    created_at: Mapped[str] = mapped_column(String, default=now_iso)


class EvolutionRun(Base):
    __tablename__ = "evolution_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ran_at: Mapped[str] = mapped_column(String, default=now_iso)
    report_md: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="ok")  # ok|failed


class Suggestion(Base):
    """进化建议：用户一键采纳制，绝不静默改画像。"""
    __tablename__ = "suggestions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("evolution_runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String)  # keyword_add|keyword_remove|weight|entity_watch|narrative
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="pending", index=True)  # pending|accepted|rejected
    created_at: Mapped[str] = mapped_column(String, default=now_iso)
    decided_at: Mapped[str] = mapped_column(String, default="")


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String, default=now_iso, index=True)
    model: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)  # analyze|brief|chat|evolve
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_est: Mapped[float] = mapped_column(Float, default=0.0)  # 元，估算


class FetchLog(Base):
    __tablename__ = "fetch_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[str] = mapped_column(String, default=now_iso, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    http_status: Mapped[int] = mapped_column(Integer, default=0)
    found: Mapped[int] = mapped_column(Integer, default=0)
    new: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    ms: Mapped[int] = mapped_column(Integer, default=0)
