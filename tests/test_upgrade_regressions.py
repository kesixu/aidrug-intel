"""见微升级 · 回归测试

针对 2026-10-06 代码审计发现的缺陷，锁死以下行为：
  1. _is_due 必须是分钟粒度（此前被写成日粒度，导致源实际日抓一次）
  2. fetcher 在重试耗尽且无底层异常时不得抛 UnboundLocalError
  3. 晨报必须区分「无新条目」与「有候选但全低分」两种空态
  4. 对话历史必须是时间正序且不含本轮问题（此前上下文错位一格）
  5. "今日"统计必须用北京日界
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.ingest.pipeline import _is_due
from app.textutil import beijing_today


def _iso(minutes_ago: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestIsDue:
    """BUG A 回归：调度到期判定必须是分钟粒度。

    现场证据：源 last_fetch_at 精确到秒（2026-10-06T04:16:56Z），
    原实现只看日期部分，导致 schedule_minutes=120 的源一个 UTC 日只抓一次。
    """

    def test_recent_fetch_is_not_due(self):
        assert _is_due(_iso(1), 120) is False

    def test_past_half_period_is_not_due(self):
        assert _is_due(_iso(59), 120) is False

    def test_beyond_period_is_due(self):
        assert _is_due(_iso(121), 120) is True

    def test_same_day_multi_cycle_now_detected(self):
        """核心回归：同一天内必须能多次到期。"""
        assert _is_due(_iso(180), 120) is True

    def test_empty_last_fetch_is_due(self):
        assert _is_due("", 240) is True

    def test_unparseable_last_fetch_is_due(self):
        assert _is_due("not-a-timestamp", 240) is True

    def test_zero_schedule_always_due(self):
        assert _is_due(_iso(0), 0) is True

    def test_accepts_millisecond_and_naive_forms(self):
        """兼容其它写入路径可能产生的 ISO 变体。"""
        assert _is_due(_iso(200).replace("Z", ".000Z"), 120) is True
        assert _is_due(_iso(10).rstrip("Z"), 120) is False


class TestFetcherNoUnboundLocal:
    """BUG B 回归：重试耗尽且无底层异常时不得崩溃。"""

    def test_retry_exhausted_without_exception_returns_result(self, monkeypatch):
        from app.ingest import fetcher

        class FakeResp:
            status_code = 503
            content = b""
            headers: dict = {}

        calls = {"n": 0}

        def fake_get(url, **kwargs):
            calls["n"] += 1
            return FakeResp()

        monkeypatch.setattr(fetcher.httpx, "get", fake_get)
        monkeypatch.setattr(fetcher.time, "sleep", lambda _s: None)

        r = fetcher.fetch("https://example.invalid/x", retries=2)

        assert r.status == 503
        assert r.ok is False
        assert calls["n"] == 3
        assert isinstance(r.ms, int)


class TestFetchLogColumns:
    """FetchLog 必须能记录本轮新增数（供前端源健康展示）。"""

    def test_fetchlog_records_new_count(self):
        from app.models import FetchLog

        cols = set(FetchLog.__table__.columns.keys())
        assert {"source_id", "ok", "http_status", "found", "new", "ms"} <= cols


class TestBriefEmptyStates:
    """BUG C 回归：晨报两种空态必须可区分。"""

    def test_fallback_mentions_date(self):
        from app.llm.briefing import _fallback_md

        assert "2026-10-06" in _fallback_md("2026-10-06", 0)

    def test_low_signal_state_is_distinct(self):
        from app.llm.briefing import _low_signal_md

        md = _low_signal_md("2026-10-06", 12, 3)
        assert "12" in md and "3" in md
        assert "候选池" in md

    def test_two_empty_states_differ(self):
        from app.llm.briefing import _fallback_md, _low_signal_md

        assert _fallback_md("2026-10-06", 0) != _low_signal_md("2026-10-06", 0, 1)


class TestBeijingDayBoundary:
    """BUG D 回归：'今日'统计用北京日界，而非 UTC 日界。"""

    def test_beijing_today_format(self):
        s = beijing_today()
        assert len(s) == 10 and s[4] == "-" and s[7] == "-"

    def test_beijing_day_start_utc_maps_back_to_midnight(self):
        from app.textutil import beijing_day_start_utc_iso

        dt = datetime.strptime(beijing_day_start_utc_iso(), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc) + timedelta(hours=8)
        bj_now = datetime.now(timezone.utc) + timedelta(hours=8)
        assert dt.date() == bj_now.date()
        assert dt.hour == 0 and dt.minute == 0

    def test_beijing_month_start_maps_back_to_first(self):
        from app.textutil import beijing_month_start_utc_iso

        dt = datetime.strptime(beijing_month_start_utc_iso(), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc) + timedelta(hours=8)
        bj_now = datetime.now(timezone.utc) + timedelta(hours=8)
        assert dt.day == 1 and dt.hour == 0
        assert (dt.year, dt.month) == (bj_now.year, bj_now.month)


class TestChatHistoryOrder:
    """BUG E 回归：历史必须是时间正序、不含本轮问题、从最近端截取。"""

    # 模拟 DB 按 id DESC 取回：第 0 条是刚插入的本轮问题
    ROWS = [
        {"role": "user", "content": "Q3"},       # 本轮刚插入
        {"role": "assistant", "content": "A2"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q1"},
    ]

    def test_drops_current_question_and_orders_chronologically(self):
        from app.llm.chatsvc import _recent_history_asc

        out = _recent_history_asc(self.ROWS, drop_first=True, keep=8)
        assert [m["content"] for m in out] == ["Q1", "A1", "Q2", "A2"]
        assert "Q3" not in [m["content"] for m in out]

    def test_drop_first_disabled_keeps_current_and_reverses(self):
        from app.llm.chatsvc import _recent_history_asc

        out = _recent_history_asc(self.ROWS, drop_first=False, keep=0)
        assert [m["content"] for m in out] == ["Q1", "A1", "Q2", "A2", "Q3"]

    def test_keep_trims_from_oldest_side(self):
        """截断必须丢最旧的，保留最近的。"""
        from app.llm.chatsvc import _recent_history_asc

        out = _recent_history_asc(self.ROWS, drop_first=True, keep=2)
        assert [m["content"] for m in out] == ["Q2", "A2"]

    def test_empty_input_is_safe(self):
        from app.llm.chatsvc import _recent_history_asc

        assert _recent_history_asc([], drop_first=True, keep=8) == []

    def test_single_current_message_yields_empty_history(self):
        from app.llm.chatsvc import _recent_history_asc

        rows = [{"role": "user", "content": "only"}]
        assert _recent_history_asc(rows, drop_first=True, keep=8) == []


class TestPromptAssemblyContract:
    """终态契约：历史 + 本轮问题拼接后，最后一条恰是本轮问题一次，角色交替正确。"""

    def test_last_message_is_current_question_once(self):
        from app.llm.chatsvc import _recent_history_asc

        rows = [
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q1"},
        ]
        hist = _recent_history_asc(rows, drop_first=True, keep=8)
        final = hist + [{"role": "user", "content": "Q2"}]
        assert final[-1]["content"] == "Q2"
        assert sum(1 for m in final if m["content"] == "Q2") == 1
        assert [m["role"] for m in final] == ["user", "assistant", "user"]
