from app.ingest.parsers import parse_govcn, parse_html_list, parse_rss

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>t</title>
<item><title>AI\xe5\x88\xb6\xe8\x8d\xaf\xe8\x9e\x8d\xe8\xb5\x84\xe6\x96\xb0\xe9\x97\xbb</title>
<link>https://m.example.com/a?utm_source=rss</link>
<pubDate>Mon, 06 Jul 2026 08:00:00 GMT</pubDate>
<description><![CDATA[<p>\xe6\x91\x98\xe8\xa6\x81</p>]]></description></item>
</channel></rss>"""

HTML = """
<html><body>
<ul class="list">
  <li><a href="./202607/t20260703_1.html">北京市关于开展某某申报工作的通知很长标题</a><span>2026-07-03</span></li>
  <li><a href="/nav/about.html">关于我们导航链接不该被收</a></li>
  <li><a href="./202607/t20260702_2.html">另一条政策发布公告标题也很长</a><span>2026-07-02</span></li>
</ul>
<div class="footer"><a href="https://other.com/x">外部很长的链接标题不应收录</a><span>2026-01-01</span></div>
</body></html>""".encode("utf-8")

GOVCN = ("""{"searchVO": {"listVO": [
  {"title": "国务院关于<em>人工智能</em>的通知", "url": "https://www.gov.cn/z/c1.htm",
   "pubtimeStr": "2026.07.03", "summary": "摘要<b>x</b>"}]}}""").encode("utf-8")


def test_parse_rss():
    items = parse_rss(RSS, "https://example.com", {})
    assert len(items) == 1
    assert items[0].title == "AI制药融资新闻"
    assert items[0].published == "2026-07-06"


def test_parse_html_list_generic_date_filter():
    items = parse_html_list(HTML, "https://kw.beijing.gov.cn/zwgk/zcwj/", {})
    urls = [i.url for i in items]
    assert len(items) == 2  # 导航无日期、外部域名都被过滤
    assert urls[0].startswith("https://kw.beijing.gov.cn/zwgk/zcwj/202607/")
    assert items[0].published == "2026-07-03"


def test_parse_html_list_selector_and_pattern():
    items = parse_html_list(HTML, "https://kw.beijing.gov.cn/zwgk/zcwj/",
                            {"item_selector": "ul.list li a", "href_pattern": r"t\d{8}_\d+\.html"})
    assert len(items) == 2


def test_parse_govcn():
    items = parse_govcn(GOVCN, "https://sousuo.www.gov.cn", {})
    assert items[0].title == "国务院关于人工智能的通知"
    assert items[0].published == "2026-07-03"
