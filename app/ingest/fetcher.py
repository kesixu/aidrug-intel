"""HTTP 抓取：真实 UA、超时、重试、条件请求（ETag/Last-Modified）。"""
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class FetchResult:
    status: int = 0
    content: bytes = b""
    etag: str = ""
    last_modified: str = ""
    ms: int = 0
    error: str = ""
    not_modified: bool = False

    @property
    def ok(self) -> bool:
        return self.status == 200 or self.not_modified


def fetch(url: str, etag: str = "", last_modified: str = "",
          verify: bool = True, retries: int = 2) -> FetchResult:
    headers = dict(HEADERS)
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    start = time.monotonic()
    last_err = ""
    last_status: int | None = None
    for attempt in range(retries + 1):
        try:
            r = httpx.get(url, headers=headers, timeout=settings.fetch_timeout,
                          follow_redirects=True, verify=verify)
            ms = int((time.monotonic() - start) * 1000)
            if r.status_code == 304:
                return FetchResult(status=304, not_modified=True, etag=etag,
                                   last_modified=last_modified, ms=ms)
            last_status = r.status_code
            if r.status_code >= 500 and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return FetchResult(
                status=r.status_code, content=r.content,
                etag=r.headers.get("etag", ""), last_modified=r.headers.get("last-modified", ""),
                ms=ms,
            )
        except httpx.HTTPError as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    # 重试耗尽且未拿到任何响应：必须返回结构化失败。
    # 原缺陷：此处引用的 ms/status 只在 try 内赋值；当最后一轮走的是
    # 5xx 分支（continue 后循环自然结束）时 ms 从未被赋值，
    # 触发 UnboundLocalError，把一次普通 503 升级成未捕获异常。
    return FetchResult(
        status=last_status if last_status is not None else 0,
        error=last_err or f"HTTP {last_status}",
        ms=int((time.monotonic() - start) * 1000),
    )
