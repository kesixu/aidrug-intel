from app.llm.analyst import _normalize, compute_final, source_authority, tier_for
from app.models import Lens


def _lenses():
    return [Lens(id="a", name="A", weight=0.3, enabled=True, position=0),
            Lens(id="b", name="B", weight=0.1, enabled=True, position=1)]


def test_compute_final_weighted():
    lenses = {l.id: l for l in _lenses()}
    scores = [{"lens_id": "a", "score": 80}, {"lens_id": "b", "score": 40}]
    # personal = (80*0.3+40*0.1)/0.4 = 70; final = 0.55*70+0.25*50+0.20*88 = 68.6
    assert compute_final(scores, lenses, importance=50, authority=88) == 68.6


def test_compute_final_ignores_disabled_and_unknown():
    ls = _lenses()
    ls[1].enabled = False
    lenses = {l.id: l for l in ls}
    scores = [{"lens_id": "a", "score": 80}, {"lens_id": "b", "score": 0},
              {"lens_id": "ghost", "score": 100}]
    assert compute_final(scores, lenses, 0, 0) == round(0.55 * 80, 1)


def test_tier_thresholds():
    assert tier_for(75) == "red"
    assert tier_for(60) == "orange"
    assert tier_for(45) == "blue"
    assert tier_for(44.9) == "gray"


def test_authority_map():
    assert source_authority(1) > source_authority(2) > source_authority(3) > source_authority(9)


def test_normalize_clamps_and_fills():
    lenses = _lenses()
    raw = {"summary": "s" * 999, "category": "不存在的类", "importance": 250,
           "lens_scores": [{"lens_id": "a", "score": 999, "reason": "r"},
                           {"lens_id": "ghost", "score": 10}],
           "signal": "超强", "deadline": "not-a-date", "entities": []}
    out = _normalize(raw, lenses)
    assert out["category"] == "其他"
    assert out["importance"] == 100
    assert len(out["summary"]) == 600
    got = {s["lens_id"]: s["score"] for s in out["lens_scores"]}
    assert got == {"a": 100, "b": 0}  # 越界钳制 + 缺失补零 + 未知丢弃
    assert out["signal"] == "中"
    assert out["deadline"] is None
