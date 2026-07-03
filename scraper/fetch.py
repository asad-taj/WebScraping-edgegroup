"""Page fetching.

edgegroup.ae sits behind Cloudflare and serves 403 to plain HTTP clients,
so the primary fetcher drives a real Chromium via Playwright. A requests
session is kept as a fallback for plain assets (sitemaps, images) which are
generally not challenged.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import requests

from . import config

log = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    html: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and bool(self.html)


class BrowserFetcher:
    """Fetches fully rendered pages with Playwright/Chromium."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "BrowserFetcher":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        # CHROMIUM_EXECUTABLE lets environments with a pre-installed browser
        # (a different build than the pip playwright version expects) work
        # without downloading a new one.
        executable = os.environ.get("CHROMIUM_EXECUTABLE")
        self._browser = self._pw.chromium.launch(
            headless=self._headless,
            executable_path=executable or None,
        )
        self._context = self._browser.new_context(
            user_agent=config.USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        self._context.set_default_timeout(config.PAGE_TIMEOUT_MS)
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()

    def fetch(self, url: str, expand_listings: bool = False) -> FetchResult:
        """Fetch a page, retrying on failure.

        With expand_listings=True, repeatedly clicks "load more" style
        buttons and scrolls so paginated listings render all items.
        """
        last_status, last_html, final_url = 0, "", url
        for attempt in range(1, config.MAX_RETRIES + 1):
            page = self._context.new_page()
            try:
                resp = page.goto(url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle")
                if expand_listings:
                    self._expand(page)
                last_status = resp.status if resp else 0
                last_html = page.content()
                final_url = page.url
                if 200 <= last_status < 300:
                    return FetchResult(url, final_url, last_status, last_html)
                log.warning("GET %s -> %s (attempt %d)", url, last_status, attempt)
            except Exception as exc:
                log.warning("GET %s failed (attempt %d): %s", url, attempt, exc)
            finally:
                page.close()
            time.sleep(config.REQUEST_DELAY_SECONDS * attempt)
        return FetchResult(url, final_url, last_status, last_html)

    def _expand(self, page) -> None:
        """Scroll to the bottom and click any load-more buttons, bounded."""
        for _ in range(30):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(700)
            clicked = False
            for pattern in ("load more", "show more", "view more", "see more"):
                button = page.locator(
                    f"button:has-text('{pattern}'), a:has-text('{pattern}')"
                ).first
                try:
                    if button.is_visible():
                        button.click()
                        page.wait_for_load_state("networkidle")
                        clicked = True
                        break
                except Exception:
                    continue
            at_bottom = page.evaluate(
                "() => window.innerHeight + window.scrollY >= document.body.scrollHeight - 10"
            )
            if at_bottom and not clicked:
                break


def make_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": config.BASE_URL + "/",
        }
    )
    return session


def http_get(session: requests.Session, url: str, **kwargs) -> requests.Response | None:
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=30, **kwargs)
            if resp.status_code == 200:
                return resp
            log.warning("GET %s -> %s (attempt %d)", url, resp.status_code, attempt)
        except requests.RequestException as exc:
            log.warning("GET %s failed (attempt %d): %s", url, attempt, exc)
        time.sleep(config.REQUEST_DELAY_SECONDS * attempt)
    return None
