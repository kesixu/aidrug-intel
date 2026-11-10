"""API 集成测试（LLM 全部 mock，不出网）。"""
from app.db import fts_upsert
from app.log import now_iso
from app.models import Analysis, Item, Source


def _mk_item(db, i, title, score=80.0, tier="red", category="政策发布", deadline=None):
    it = Item(uid=f"uid-{i}", source_id="most_tztg", url=f"https://x.cn/{i}",
              title=title, published_at=f"2026-07-{i:02d}", fetched_at=now_iso(),
              excerpt="节选", content=f"{title} 的正文内容，人工智能生物医药。", status="analyzed")
    db.add(it)
    db.flush()
    db.add(Analysis(item_id=it.id, summary=f"{title}摘要", category=category,
                    importance=60, final_score=score, tier=tier,
                    lens_scores=[{"lens_id": "az_career", "score": 70, "reason": "r"}],
                    deadline=deadline, entities=[{"name": "阿斯利康", "kind": "company"}]))
    fts_upsert(db, it.id, it.title, f"{title}摘要", it.content)
    return it.id


def test_feed_pagination_and_filters(client, db):
    ids = [_mk_item(db, i, f"政策标题第{i}号关于人工智能") for i in range(1, 6)]
    _mk_item(db, 9, "低分条目", score=10, tier="gray")
    db.commit()
    r = client.get("/api/v1/feed?limit=3").json()
    assert len(r["items"]) == 3 and r["next_cursor"]
    r2 = client.get(f"/api/v1/feed?limit=3&cursor={r['next_cursor']}").json()
    assert all(x["id"] not in [y["id"] for y in r["items"]] for x in r2["items"])
    red = client.get("/api/v1/feed?tier=red").json()["items"]
    assert red and all(x["analysis"]["tier"] == "red" for x in red)
    assert ids


def test_feed_bad_cursor_400(client):
    assert client.get("/api/v1/feed?cursor=bogus").status_code == 400


def test_search_chinese(client, db):
    _mk_item(db, 20, "量子计算赋能药物发现平台落地亦庄")
    db.commit()
    items = client.get("/api/v1/search?q=量子计算 亦庄").json()["items"]
    assert any("量子计算" in x["title"] for x in items)


def test_feedback_toggle_and_starred_collection(client, db):
    iid = _mk_item(db, 21, "收藏切换测试条目标题")
    db.commit()
    assert client.post(f"/api/v1/items/{iid}/feedback", json={"action": "star"}).json()["state"]["starred"]
    got = client.get("/api/v1/feed?collection=starred").json()["items"]
    assert iid in [x["id"] for x in got]
    assert not client.post(f"/api/v1/items/{iid}/feedback", json={"action": "unstar"}).json()["state"]["starred"]
    assert client.post(f"/api/v1/items/{iid}/feedback", json={"action": "nope"}).status_code == 400


def test_item_detail_related_by_entity(client, db):
    a = _mk_item(db, 22, "阿斯利康北京研发中心扩建一期")
    b = _mk_item(db, 23, "阿斯利康与园区签署合作备忘录")
    db.commit()
    from app.llm.analyst import _link_entities
    _link_entities(db, a, [{"name": "阿斯利康", "kind": "company"}])
    _link_entities(db, b, [{"name": "阿斯利康", "kind": "company"}])
    db.commit()
    d = client.get(f"/api/v1/items/{a}").json()
    assert b in [r["id"] for r in d["related"]]


def test_profile_and_lenses_roundtrip(client):
    p = client.get("/api/v1/profile").json()
    assert p["lenses"] and p["narrative"]
    assert client.put("/api/v1/profile", json={"keywords": ["AI制药", " 亦庄 "]}).json()["ok"]
    assert "亦庄" in client.get("/api/v1/profile").json()["keywords"]
    assert client.put("/api/v1/profile", json={"narrative": "  "}).status_code == 400
    lens_id = p["lenses"][0]["id"]
    assert client.put("/api/v1/lenses", json=[{"id": lens_id, "weight": 0.4, "enabled": True}]).json()["ok"]
    assert client.put("/api/v1/lenses", json=[{"id": "ghost", "weight": 0.4, "enabled": True}]).status_code == 404


def test_deadline_collection(client, db):
    iid = _mk_item(db, 24, "某申报窗口通知截止很快", deadline="2099-01-01")
    db.commit()
    got = client.get("/api/v1/feed?collection=deadline").json()["items"]
    assert iid in [x["id"] for x in got]


def test_status_and_sources(client):
    s = client.get("/api/v1/system/status").json()
    assert s["items"]["total"] >= 1 and "llm" in s
    src = client.get("/api/v1/system/sources").json()["sources"]
    assert any(x["id"] == "most_tztg" for x in src)


def test_analyze_item_with_mocked_llm(client, db, monkeypatch):
    it = Item(uid="uid-llm", source_id="most_tztg", url="https://x.cn/llm",
              title="北京市AI制药专项申报通知", published_at="2026-07-06",
              fetched_at=now_iso(), excerpt="e", content="正文", status="new")
    db.add(it)
    db.commit()
    canned = {"summary": "两句话摘要。细节。", "category": "资金申报", "event_type": "资金申报",
              "importance": 70,
              "lens_scores": [{"lens_id": "talent_funding", "score": 85, "reason": "申报窗口"}],
              "entities": [{"name": "北京市科委", "kind": "agency"}],
              "action_hint": "7月20日前提交", "deadline": "2026-07-20", "signal": "强",
              "policy_family": "北京AI制药专项", "policy_stage": "申报窗口"}
    monkeypatch.setattr("app.llm.analyst.chat_json", lambda *a, **k: canned)
    from app.llm.analyst import analyze_item
    assert analyze_item(it.id)
    d = client.get(f"/api/v1/items/{it.id}").json()
    assert d["analysis"]["category"] == "资金申报"
    assert d["analysis"]["deadline"] == "2026-07-20"
    assert d["analysis"]["tier"] in ("red", "orange", "blue", "gray")
    assert d["status"] == "analyzed"
