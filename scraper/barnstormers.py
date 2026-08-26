"""Scraper for Aviat aircraft listings on barnstormers.com.

Barnstormers' "Aviat Aircraft" category page is loosely curated and mixes in
competing backcountry/aerobatic aircraft (CubCrafters, Cessna 175, American
Champion Decathlons) with no distinguishing HTML markup - same DOM structure
as the genuine listings. So results are filtered by title against a small
allowlist of Aviat product names before being published.

On top of that brand allowlist, only whole-aircraft-for-sale listings are
kept: each ad's title must state a model year and match a recognized Husky/
Pitts/Christen Eagle model, and titles that look like parts/accessories/
services/raffles are dropped. Surviving titles are rewritten to a canonical
"YEAR MAKE MODEL" form - Aviat for Huskys, Pitts for the Pitts Special,
Christen for the Christen Eagle, since those are how each is actually
branded - so every listing follows the same format.
"""
from __future__ import annotations

import re
from urllib.parse import quote, unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from .common import (
    Listing,
    extract_date,
    extract_location,
    extract_price,
    fetch,
    format_aircraft_title,
)

SITE_NAME = "Barnstormers.com"
BASE = "https://www.barnstormers.com"

# Category pages known to carry Aviat listings on Barnstormers (Husky, Pitts, Eagle, etc.).
CATEGORY_URLS = [
    f"{BASE}/category-24045-Aviat-Aircraft.html",
]

# Only ads whose title matches one of these (case/hyphen/space-insensitive)
# are kept - the category page itself isn't reliably Aviat-only.
TARGET_MODEL_PHRASES = [
    "aviat",
    "husky",
    "pitts",
    "christen eagle",
]

MAX_PAGES = 10
LISTING_LINK_RE = re.compile(r"^/classified-(\d+)-(.+)\.html$")
GENERIC_SITE_TITLE_SNIPPET = "barnstormers.com find aircraft"


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[-_]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _matches_target_models(title: str) -> bool:
    normalized = _normalize(title)
    return any(phrase in normalized for phrase in TARGET_MODEL_PHRASES)


def _extract_model(title: str) -> tuple[str, str] | None:
    normalized = _normalize(title)
    if "husky" in normalized:
        if re.search(r"a[\s-]?1[\s-]?c\b", normalized):
            return "Aviat", "Husky A-1C"
        if re.search(r"a[\s-]?1[\s-]?b\b", normalized):
            return "Aviat", "Husky A-1B"
        if re.search(r"a[\s-]?1\b", normalized):
            return "Aviat", "Husky A-1"
        return "Aviat", "Husky"
    if "pitts" in normalized:
        if re.search(r"s[\s-]?2b\b", normalized):
            return "Pitts", "S-2B"
        if re.search(r"s[\s-]?2s\b", normalized):
            return "Pitts", "S-2S"
        if re.search(r"s[\s-]?2c\b", normalized):
            return "Pitts", "S-2C"
        return "Pitts", "Special"
    if "christen eagle" in normalized:
        return "Christen", "Eagle"
    return None


def _title_from_url(url: str) -> str:
    """Listing pages share a generic <title>/<h1>, but the URL slug is the ad's own title."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    match = LISTING_LINK_RE.match("/" + slug)
    if not match:
        return unquote(slug)
    return unquote(match.group(2)).replace("-", " ").strip()


def _find_listing_links(html: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0]
        if LISTING_LINK_RE.match(href):
            links.add(urljoin(BASE, href))
    return links


def _page_url(category_url: str, page: int) -> str:
    """Build a category page's URL directly.

    Barnstormers' category pager renders as page-number buttons with no
    "Next" text or rel="next" attribute for a link-following heuristic to
    find (confirmed on the companion Van's RV, Stearman, Waco, Pitts,
    Taylorcraft, Swift, and Beech repos, where that approach silently
    stopped after page 1) - so each page's URL is built from the known
    ?seocategory=<url-encoded-path>&page=<n> pattern instead.
    """
    if page <= 1:
        return category_url
    path = urlparse(category_url).path
    return f"{category_url}?seocategory={quote(path, safe='')}&page={page}"


def _debug_dump_hrefs(html: str, limit: int = 25) -> None:
    soup = BeautifulSoup(html, "lxml")
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]
    interesting = [
        h for h in hrefs
        if "classified" in h.lower() or "aviat" in h.lower() or "husky" in h.lower() or "pitts" in h.lower()
    ]
    sample = interesting[:limit] or hrefs[:limit]
    print(f"  [debug] {len(hrefs)} total <a href> on page; sample: {sample}")


def _parse_detail_page(url: str, html: str) -> Listing | None:
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    if title:
        title = re.sub(r"\s*[\|\-]\s*Barnstormers.*$", "", title, flags=re.IGNORECASE).strip()
    if not title or GENERIC_SITE_TITLE_SNIPPET in title.lower():
        title = _title_from_url(url)
    if not title:
        return None

    text = soup.get_text(" ", strip=True)

    formatted_title = format_aircraft_title(title, text, _extract_model)
    if not formatted_title:
        return None
    title = formatted_title

    price = extract_price(text)
    location = extract_location(text)
    date_posted = extract_date(text)

    return Listing(
        title=title,
        price=price,
        location=location,
        date_posted=date_posted,
        site=SITE_NAME,
        url=url,
    )


def scrape() -> list[Listing]:
    print(f"[{SITE_NAME}] starting scrape")
    all_links: set[str] = set()

    for category_url in CATEGORY_URLS:
        seen_this_category: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            url = _page_url(category_url, page)
            html = fetch(url)
            if not html:
                break
            links = _find_listing_links(html)
            new_links = links - seen_this_category
            print(f"  [{category_url}] page {page}: {len(links)} links ({len(new_links)} new)")
            if page == 1 and not links:
                _debug_dump_hrefs(html)
            seen_this_category |= links
            if not new_links:
                break
        all_links |= seen_this_category

    print(f"[{SITE_NAME}] {len(all_links)} total listing URLs found")

    candidate_links = {url for url in all_links if _matches_target_models(_title_from_url(url))}
    print(f"[{SITE_NAME}] {len(candidate_links)} match Aviat product names")

    listings: list[Listing] = []
    for url in sorted(candidate_links):
        html = fetch(url)
        if not html:
            continue
        listing = _parse_detail_page(url, html)
        if listing and _matches_target_models(listing.title):
            listings.append(listing)

    print(f"[{SITE_NAME}] parsed {len(listings)} listings")
    return listings
