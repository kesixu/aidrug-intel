"""无头浏览器冒烟：每个视图、两种视口、主要操作。LLM 只在浏览器里被 mock。"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ["today", "feed", "chat", "insight", "atlas", "companies", "me"]
WAIT = {
    "today": ".today-head",
    "feed": ".intel-card, .empty, .error-box",
    "chat": ".suggest-card, .chat-input textarea",
    "insight": ".entity-card, .empty, .error-box",
    "atlas": ".at-hero-title",
    "companies": ".co-hero-title",
    "me": "textarea.narrative, .error-box",
}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    base_dir = tmp_path_factory.mktemp("ui")
    env = os.environ.copy()
    env["AIDRUG_DB_PATH"] = str(base_dir / "ui.db")
    env["AIDRUG_LOG_DIR"] = str(base_dir / "logs")
    env["AIDRUG_SCHEDULER_ENABLED"] = "false"
    env["DEEPSEEK_API_KEY"] = "sk-test-not-used"
    env["DEEPSEEK_BASE_URL"] = "http://127.0.0.1:9"
    subprocess.check_call([sys.executable, "scripts/seed_fixture.py"], cwd=ROOT, env=env)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("ui server did not start")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _launch(p):
    try:
        return p.chromium.launch(channel="chrome", headless=True)
    except Exception:
        return p.chromium.launch(headless=True)


def _overflow(page):
    return page.evaluate("""() => {
      const vw = document.documentElement.clientWidth;
      const doc = document.documentElement.scrollWidth - vw;
      const view = document.getElementById('view');
      const inner = view.scrollWidth - view.clientWidth;
      return { doc, inner };
    }""")


def _watch(page):
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    return errors


def test_every_view_desktop_and_phone(live):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = _launch(p)
        for name, vp in {"desktop": (1280, 800), "phone": (390, 844)}.items():
            page = browser.new_page(viewport={"width": vp[0], "height": vp[1]}, color_scheme="light")
            errors = _watch(page)
            for view in VIEWS:
                page.goto(live + f"/#/{view}", wait_until="domcontentloaded")
                page.wait_for_selector(WAIT[view], timeout=8000)
                page.wait_for_timeout(200)
                assert not errors, f"{name} {view}: {errors}"
                if name == "phone":
                    gap = _overflow(page)
                    assert gap["doc"] <= 1 and gap["inner"] <= 1, f"overflow on {view}: {gap}"
            page.close()
        browser.close()


def test_main_interactions(live):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 800}, color_scheme="light")
        errors = _watch(page)

        page.goto(live + "/#/feed", wait_until="domcontentloaded")
        page.wait_for_selector(".intel-card")
        page.locator('.filter-bar button[data-value="red"]').click()
        page.wait_for_function("""() => {
          const cards = [...document.querySelectorAll('.intel-card')];
          return cards.length > 0 && cards.every(c => c.classList.contains('tier-red'));
        }""")

        page.locator(".intel-card").first.click()
        page.wait_for_selector(".fb-btn")
        page.locator('.fb-btn[data-act="star"]').click()
        page.wait_for_selector("#toast.show")
        assert "收藏" in page.locator("#toast").inner_text()

        item_id = page.evaluate("""async () => {
          const r = await fetch('/api/v1/feed?tier=red&limit=1');
          const j = await r.json();
          return j.items[0].id;
        }""")

        def fulfill(route):
            body = "\n".join([
                "event: meta",
                "data: " + json.dumps({
                    "session_id": "smoke",
                    "citations": [{"n": 1, "item_id": item_id, "title": "亦庄专项", "url": "https://example.com/1"}],
                }, ensure_ascii=False),
                "",
                "event: delta",
                'data: {"text":"亦庄有新申报 [1]。"}',
                "",
                "event: done",
                'data: {"session_id":"smoke"}',
                "",
            ])
            route.fulfill(status=200, content_type="text/event-stream", body=body)

        page.route("**/api/v1/chat/stream", fulfill)
        page.goto(live + "/#/chat", wait_until="domcontentloaded")
        page.wait_for_selector(".suggest-card")
        page.fill("textarea", "亦庄最近有什么申报？")
        page.locator(".send-btn").click()
        page.wait_for_selector(".cite-ref")
        assert "亦庄有新申报" in page.locator(".msg.assistant").inner_text()
        page.locator(".cite-ref").click()
        page.wait_for_selector(".detail-title")

        page.goto(live + "/#/me", wait_until="domcontentloaded")
        page.wait_for_selector("textarea.narrative")
        page.locator("textarea.narrative").fill(page.locator("textarea.narrative").input_value() + "\n界面检查。")
        page.get_by_role("button", name="保存画像").click()
        page.wait_for_function("""() => document.getElementById('toast').classList.contains('show')
          && document.getElementById('toast').textContent.includes('画像已更新')""")

        page.goto(live + "/#/companies/astrazeneca", wait_until="domcontentloaded")
        page.wait_for_selector(".co-detail-title")
        page.locator('#side-nav [data-nav="companies"]').click()
        page.wait_for_selector(".co-hero-title")

        phone = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
        phone_err = _watch(phone)
        phone.goto(live + "/#/companies/astrazeneca", wait_until="domcontentloaded")
        phone.wait_for_selector(".co-table")
        gap = _overflow(phone)
        assert gap["doc"] <= 1 and gap["inner"] <= 1, gap
        phone.goto(live + "/#/feed", wait_until="domcontentloaded")
        phone.wait_for_selector(".intel-card")
        phone.locator('.filter-bar button[data-value="followed"]').click()
        phone.wait_for_selector(".intel-card, .empty")
        assert not errors, errors
        assert not phone_err, phone_err
        browser.close()
