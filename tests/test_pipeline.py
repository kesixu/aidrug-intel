from app.ingest.pipeline import _gate_pass, _is_due
from app.seeds import import_legacy


def test_gate_pass():
    kws = ["AI制药", "亦庄"]
    assert _gate_pass("大事件：ai制药公司获融资", "", kws)  # 大小写不敏感
    assert _gate_pass("平平无奇", "落地北京亦庄", kws)
    assert not _gate_pass("体育新闻", "足球比赛", kws)


def test_is_due():
    assert _is_due("", 120)
    assert _is_due("2020-01-01T00:00:00Z", 120)
    from app.log import now_iso
    assert not _is_due(now_iso(), 120)


def test_legacy_import_idempotent(db):
    from sqlalchemy import text
    db.execute(text("""CREATE TABLE IF NOT EXISTS intel_entries (
        id TEXT PRIMARY KEY, date_published TEXT, date_captured TEXT,
        source_department TEXT, source_url TEXT, title TEXT, category TEXT,
        region_tier TEXT, original_excerpt TEXT, ai_interpretation TEXT,
        relevance_score_overall INT, relevance_score_az INT,
        relevance_score_trustpathbot INT, relevance_score_talent INT,
        relevance_score_funding INT, relevance_reasoning TEXT, forecast TEXT,
        recommended_action TEXT, follow_up_flag INT, related_entry_ids TEXT,
        user_note TEXT, user_status TEXT, policy_family TEXT, policy_stage TEXT,
        created_at TEXT)"""))
    db.execute(text("""INSERT OR IGNORE INTO intel_entries VALUES (
        'intel_x', '2026-07-01', '2026-07-06', '市科委', 'https://legacy.example/1',
        '旧系统条目标题', '政策发布', '市级', '节选', '解读', 4, 5, 2, 1, 0,
        '推理', '', '行动', 0, '[]', '', '', '', '', '2026-07-06')"""))
    db.commit()
    n1 = import_legacy(db)
    db.commit()
    n2 = import_legacy(db)
    assert n1 == 1 and n2 == 0
    from app.models import Analysis, Item
    it = db.query(Item).filter(Item.uid != None).filter(Item.url == "https://legacy.example/1").one()  # noqa: E711
    a = db.get(Analysis, it.id)
    assert a.tier == "red"  # overall 4 → 80 分
    scores = {s["lens_id"]: s["score"] for s in a.lens_scores}
    assert scores["az_career"] == 100 and scores["talent_funding"] == 20
