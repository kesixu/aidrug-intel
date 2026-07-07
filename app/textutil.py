"""文本工具：URL 规范化、jieba 分词、simhash 软去重、HTML 正文抽取、北京时间。"""
import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import jieba
from bs4 import BeautifulSoup

BEIJING = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def beijing_today() -> str:
    return beijing_now().strftime("%Y-%m-%d")

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "spm", "from", "src"}
_WS_RE = re.compile(r"\s+")


def canonical_url(url: str) -> str:
    """去追踪参数与锚点，统一末尾斜杠，用于全局去重。"""
    url = (url or "").strip()
    try:
        p = urlparse(url)
        query = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING_PARAMS])
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", query, ""))
    except ValueError:
        return url


def uid_for(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()


def clean_text(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def segment(text: str) -> str:
    """jieba 分词为空格连接串，供 FTS5 索引与查询两侧共用。"""
    tokens = [t.strip().lower() for t in jieba.cut(clean_text(text)) if t.strip()]
    return " ".join(tokens)


def simhash64(text: str) -> int:
    """基于 jieba 词元的 64 位 simhash，用于标题软去重。"""
    v = [0] * 64
    tokens = [t for t in jieba.cut(clean_text(text).lower()) if t.strip()]
    if not tokens:
        return 0
    for tok in tokens:
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if v[i] > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def extract_main_text(html: str | bytes, max_chars: int = 8000) -> str:
    """通用正文抽取：剔除脚本/导航后取密度最高的文本块，够用且无重依赖。"""
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "form"]):
        tag.decompose()
    candidates = soup.find_all(["article", "div", "section"], limit=400)
    best, best_len = None, 0
    for c in candidates:
        txt = c.get_text(" ", strip=True)
        if len(txt) > best_len:
            best, best_len = c, len(txt)
    text = (best or soup).get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 1]
    return clean_text("\n".join(lines))[:max_chars]


def parse_date_like(s: str) -> str:
    """从字符串中提取 YYYY-MM-DD；失败返回空串。"""
    if not s:
        return ""
    m = re.search(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""
