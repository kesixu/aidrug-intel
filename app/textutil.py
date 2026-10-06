"""文本工具：URL 规范化、jieba 分词、simhash 软去重、HTML 正文抽取、北京时间。"""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import jieba
from bs4 import BeautifulSoup

BEIJING = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def beijing_day_start_utc_iso() -> str:
    """北京当日 00:00 对应的 UTC ISO 字符串（"今日"统计的正确日界）。"""
    bj = datetime.now(timezone.utc) + timedelta(hours=8)
    start_bj = datetime(bj.year, bj.month, bj.day, tzinfo=timezone.utc)
    return (start_bj - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")


def beijing_month_start_utc_iso() -> str:
    """北京当月 1 日 00:00 对应的 UTC ISO 字符串。"""
    bj = datetime.now(timezone.utc) + timedelta(hours=8)
    start_bj = datetime(bj.year, bj.month, 1, tzinfo=timezone.utc)
    return (start_bj - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")


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


_TITLE_STOP = {
    "的", "了", "与", "及", "和", "对", "在", "为", "各", "有关", "关于", "根据",
    "通知", "公告", "公示", "通告", "批复", "意见", "办法", "印发", "转发", "发布",
    "开展", "组织", "做好", "启动", "举办", "召开", "工作",
}
_WORDCHAR_RE = re.compile(r"[\w一-鿿]")


def title_tokens(text: str) -> frozenset:
    """标题实义词集合（剔除公文模板词与标点），供 Jaccard 软去重。
    公文标题大量共享「关于/开展/通知」等模板词，不剔除会把不同事件误判为重复。"""
    out = set()
    for t in jieba.cut(clean_text(text)):
        t = t.strip().lower()
        if t and t not in _TITLE_STOP and _WORDCHAR_RE.search(t):
            out.add(t)
    return frozenset(out)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


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
    """从字符串中提取 YYYY-MM-DD；支持分隔符与紧凑形式（如 gov 站 URL 的 t20260703_）。"""
    if not s:
        return ""
    m = re.search(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", s)
    if not m:
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", s)
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
    return ""
