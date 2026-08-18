"""Shared helpers used by the Aeronca listing scrapers.

Barnstormers.com sits behind Cloudflare bot protection that treats plain
`requests`/`curl` HTTP clients differently from a real browser, silently
returning near-empty pages. A real headless browser clears this, so
fetching is done through Playwright/Chromium instead of a plain HTTP client.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PAGE_TIMEOUT_MS = 30_000
CHALLENGE_MAX_WAIT_MS = 25_000
CHALLENGE_POLL_MS = 1_000
REQUEST_DELAY_SECONDS = 1.0
CHALLENGE_TITLE_MARKERS = ("just a moment", "attention required", "checking your browser")

_playwright = None
_browser = None
_context = None


def _get_context():
    global _playwright, _browser, _context
    if _context is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        _context = _browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        _context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
    return _context


def close_browser() -> None:
    """Shut down the shared Playwright browser, if one was started."""
    global _playwright, _browser, _context
    if _browser is not None:
        _browser.close()
    if _playwright is not None:
        _playwright.stop()
    _playwright = _browser = _context = None


def fetch(url: str) -> Optional[str]:
    """Load a URL in a real browser and return the rendered HTML, or None on failure."""
    page = _get_context().new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        # If Cloudflare's JS challenge fires, poll until it clears (or give up).
        waited = 0
        while waited < CHALLENGE_MAX_WAIT_MS:
            title = (page.title() or "").lower()
            if not any(marker in title for marker in CHALLENGE_TITLE_MARKERS):
                break
            page.wait_for_timeout(CHALLENGE_POLL_MS)
            waited += CHALLENGE_POLL_MS
        else:
            print(f"  [warn] {url} -> Cloudflare challenge did not clear after {waited}ms")
        # Let any client-side rendering (SPA search results, etc.) finish.
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        return page.content()
    except Exception as exc:  # Playwright raises its own error types
        print(f"  [warn] {url} -> {exc}")
        return None
    finally:
        page.close()
        time.sleep(REQUEST_DELAY_SECONDS)


PRICE_RE = re.compile(r"\$\s?[\d,]{3,12}(?:\.\d{2})?")
STATE_ABBRS = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
LOCATION_RE = re.compile(
    r"\b([A-Z][a-zA-Z.'\-]+(?:\s[A-Z][a-zA-Z.'\-]+)*),\s(" + "|".join(STATE_ABBRS) + r")\b"
)
DATE_LABEL_RE = re.compile(
    r"(?:Date Posted|Date Listed|Posted|Listed)[:\s]+"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)


def extract_price(text: str) -> str:
    m = PRICE_RE.search(text)
    return m.group(0).strip() if m else "Contact for price"


def extract_location(text: str) -> str:
    m = LOCATION_RE.search(text)
    return f"{m.group(1)}, {m.group(2)}" if m else "Unknown"


def extract_date(text: str) -> str:
    m = DATE_LABEL_RE.search(text)
    return m.group(1).strip() if m else ""


def extract_jsonld_objects(soup: BeautifulSoup) -> list[dict]:
    """Pull every schema.org JSON-LD object out of a page, if any are present."""
    objects: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        if isinstance(data, list):
            objects.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            objects.append(data)
    return objects


@dataclass
class Listing:
    title: str
    price: str
    location: str
    date_posted: str
    site: str
    url: str

    def key(self) -> tuple:
        return (self.site, self.url)
