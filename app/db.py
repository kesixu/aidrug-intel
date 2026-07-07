"""SQLite 引擎（WAL）、会话、schema 迁移与 FTS5 同步。"""
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.log import log_event
from app.models import Base, KV
from app.textutil import segment

settings.db_path.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False, "timeout": 15},
)


@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=15000")
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    """FastAPI 依赖。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SCHEMA_VERSION = 2


def migrate() -> None:
    """启动时幂等迁移：建 v2 表 + FTS5 虚表；旧表 intel_entries 原样保留。"""
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5("
            "title_seg, summary_seg, content_seg, item_id UNINDEXED)"
        ))
    with session_scope() as db:
        row = db.get(KV, "schema_version")
        if row is None:
            db.add(KV(key="schema_version", value=str(SCHEMA_VERSION)))
        else:
            row.value = str(SCHEMA_VERSION)
    log_event("db.migrated", version=SCHEMA_VERSION, path=str(settings.db_path))


def fts_upsert(db: Session, item_id: int, title: str, summary: str, content: str) -> None:
    """FTS 与 items/analyses 在代码层同步（触发器无法调 jieba）。"""
    db.execute(text("DELETE FROM items_fts WHERE item_id = :i"), {"i": item_id})
    db.execute(
        text("INSERT INTO items_fts(title_seg, summary_seg, content_seg, item_id) "
             "VALUES (:t, :s, :c, :i)"),
        {"t": segment(title), "s": segment(summary), "c": segment(content[:6000]), "i": item_id},
    )


def fts_search(db: Session, query: str, limit: int = 50) -> list[tuple[int, float]]:
    """返回 [(item_id, bm25分)]，分越小越相关（bm25 原生为负向）。"""
    q = segment(query)
    if not q.strip():
        return []
    match = " OR ".join(f'"{tok}"' for tok in q.split()[:12])
    rows = db.execute(
        text("SELECT item_id, bm25(items_fts, 3.0, 2.0, 1.0, 0.0) AS r "
             "FROM items_fts WHERE items_fts MATCH :m ORDER BY r LIMIT :l"),
        {"m": match, "l": limit},
    ).fetchall()
    return [(int(r[0]), float(r[1])) for r in rows]
