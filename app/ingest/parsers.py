"""列表解析器：rss / html_list（通用启发式）/ govcn（政策文件库 JSON API）。

通用启发式的依据（2026-07-07 实测）：大陆政府网站的政策列表项几乎都是
「<li>/<tr> 内含标题链接 + 同容器内含日期」，据此过滤导航噪声，无需逐站写选择器。
"""
import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import feedparser
from bs4 import BeautifulSoup

from app.textutil import clean_text, parse_date_like


@dataclass
class RawItem:
    title: str
    url: str
    published: str = ""   # YYYY-MM-DD
    excerpt: str = ""


def parse_rss(content: bytes, base_url: str, cfg: dict) -> list[RawItem]:
    feed = feedparser.parse(content)
    out = []
    for e in feed.entries[: cfg.get("max_items", 60)]:
        title = clean_text(getattr(e, "title", ""))
        link = getattr(e, "link", "")
        if not title or not link:
            continue
        published = ""
        for key in ("published_parsed", "updated_parsed"):
            t = getattr(e, key, None)
            if t:
                published = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
                break
        summary = clean_text(re.sub(r"<[^>]+>", " ", getattr(e, "summary", "") or ""))[:500]
        out.append(RawItem(title=title, url=urljoin(base_url, link), published=published, excerpt=summary))
    return out


def parse_html_list(content: bytes, base_url: str, cfg: dict) -> list[RawItem]:
    soup = BeautifulSoup(content, "lxml")
    anchors = soup.select(cfg["item_selector"]) if cfg.get("item_selector") else soup.find_all("a", href=True)
    href_pattern = re.compile(cfg["href_pattern"]) if cfg.get("href_pattern") else None
    require_date = cfg.get("require_date", True)
    min_title = cfg.get("min_title", 10)
    base_host = urlparse(base_url).netloc
    seen, out = set(), []
    for a in anchors:
        href = a.get("href") or ""
        title = clean_text(a.get_text(" ", strip=True))
        if len(title) < min_title or href.startswith(("javascript:", "#")):
            continue
        url = urljoin(base_url, href)
        if urlparse(url).netloc != base_host and not cfg.get("allow_external"):
            continue
        if href_pattern and not href_pattern.search(url):
            continue
        container = a.find_parent(["li", "tr", "dd"]) or a.parent
        ctx = clean_text(container.get_text(" ", strip=True)) if container else title
        published = (parse_date_like(ctx.replace(title, " "))
                     or parse_date_like(title) or parse_date_like(url))
        if require_date and not published:
            continue
        if url in seen:
            continue
        seen.add(url)
        excerpt = ctx.replace(title, " ").strip(" -—|·")[:300]
        out.append(RawItem(title=title, url=url, published=published, excerpt=excerpt))
        if len(out) >= cfg.get("max_items", 60):
            break
    return out


def parse_govcn(content: bytes, base_url: str, cfg: dict) -> list[RawItem]:
    """国务院政策文件库 search-gov JSON。"""
    data = json.loads(content.decode("utf-8", errors="replace"))
    docs = (data.get("searchVO") or {}).get("listVO") or []
    out = []
    for d in docs[: cfg.get("max_items", 30)]:
        title = clean_text(re.sub(r"<[^>]+>", "", d.get("title") or ""))
        url = d.get("url") or ""
        if not title or not url:
            continue
        published = parse_date_like(d.get("pubtimeStr") or str(d.get("pubtime") or ""))
        out.append(RawItem(title=title, url=url, published=published,
                           excerpt=clean_text(re.sub(r"<[^>]+>", "", d.get("summary") or ""))[:300]))
    return out


PARSERS = {"rss": parse_rss, "html_list": parse_html_list, "govcn": parse_govcn}


def pick_parser(kind: str, cfg: dict):
    name = cfg.get("parser") or ("rss" if kind == "rss" else "html_list")
    return PARSERS[name]
