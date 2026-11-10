"""给每个视图拍桌面 1280×800 与手机 390×844 的视口截图。

    python3 scripts/shoot_views.py --base http://127.0.0.1:8010 --out /tmp/shots --label before
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWS = ["today", "feed", "chat", "insight", "atlas", "companies", "me"]
WAIT = {
    "today": ".today-head, .brief-card, .empty, .page-head",
    "feed": ".intel-card, .empty, .error-box",
    "chat": ".suggest-card, .chat-input textarea, .msg",
    "insight": ".entity-card, .lineage-card, .empty, .error-box",
    "atlas": ".at-hero-title",
    "companies": ".co-hero-title, .co-detail-title",
    "me": "textarea.narrative, .error-box, .section-title",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8010")
    p.add_argument("--out", required=True)
    p.add_argument("--label", required=True)
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    viewports = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 844}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        for name, vp in viewports.items():
            page = browser.new_page(viewport=vp, device_scale_factor=1, color_scheme="light")
            for view in VIEWS:
                page.goto(f"{args.base}/#/{view}", wait_until="domcontentloaded")
                page.wait_for_selector(WAIT[view], timeout=8000)
                page.wait_for_timeout(400)
                dest = out / f"{args.label}-{name}-{view}.png"
                page.screenshot(path=str(dest))
                print(dest)
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
