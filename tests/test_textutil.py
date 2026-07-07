from app.textutil import (canonical_url, jaccard, parse_date_like, segment,
                          title_tokens, uid_for)


def test_canonical_url_strips_tracking():
    a = canonical_url("https://Ex.com/a/?utm_source=x&id=3#frag")
    assert a == "https://ex.com/a?id=3"
    assert uid_for("https://ex.com/a?id=3&utm_medium=y") == uid_for(a)


def test_segment_chinese():
    seg = segment("北京市加快推进人工智能赋能科学研究")
    assert "人工智能" in seg.split()


def test_title_jaccard_dedup():
    a = title_tokens("北京市发布人工智能赋能科学研究实施方案")
    b = title_tokens("北京市发布人工智能赋能科学研究实施方案（全文）")
    c = title_tokens("上海市启动生物医药产业园区租金补贴申报")
    d = title_tokens("关于开展2026年人工智能大模型补贴申报的通知")
    e = title_tokens("关于开展2026年数据领域核心技术攻关补贴申报的通知")
    f = title_tokens("国务院关于印发《美丽中国建设十五五规划》的通知")
    g = title_tokens("国务院印发美丽中国建设十五五规划")
    assert jaccard(a, b) >= 0.7       # 同事件（仅后缀差异）→ 判重
    assert jaccard(f, g) >= 0.7       # 同政策不同表述 → 判重
    assert jaccard(a, c) < 0.7        # 不同事件
    assert jaccard(d, e) < 0.7        # 同模板不同主题的通知不能误判重


def test_parse_date_like_variants():
    assert parse_date_like("发布于 2026年7月3日") == "2026-07-03"
    assert parse_date_like("2026-07-03") == "2026-07-03"
    assert parse_date_like("2026.7.3 更新") == "2026-07-03"
    assert parse_date_like("无日期") == ""
