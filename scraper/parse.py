"""Heuristic HTML parsing shared by all sections.

The site is Drupal-based and its markup can change, so extraction leans on
stable signals — meta tags, JSON-LD, definition lists, two-column tables,
"spec"-classed blocks — rather than exact CSS selectors, and always keeps
the page's readable text so a parser miss never loses the content entirely.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from . import config


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def absolute(base_url: str, href: str) -> str:
    return urljoin(base_url, href.strip())


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def slug_of(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or "home"


# --- page-level metadata -------------------------------------------------

def extract_meta(soup: BeautifulSoup) -> dict:
    meta: dict = {}
    if soup.title:
        meta["page_title"] = clean_text(soup.title.get_text())
    for prop, key in (
        ("og:title", "title"),
        ("og:description", "description"),
        ("og:image", "image"),
        ("og:type", "type"),
    ):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            meta[key] = clean_text(tag["content"])
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        meta.setdefault("description", clean_text(desc["content"]))
    return meta


def extract_jsonld(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                blocks.extend(item.get("@graph", [item]))
    return [b for b in blocks if isinstance(b, dict)]


def main_content(soup: BeautifulSoup):
    """Best-effort location of the page's main content region."""
    for selector in ("main", "article", "[role=main]", "#main-content", ".main-content"):
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def extract_heading(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    return clean_text(h1.get_text()) if h1 else ""


def extract_body_text(soup: BeautifulSoup, limit: int = 20000) -> str:
    node = main_content(soup)
    for tag in node.find_all(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    text = clean_text(node.get_text(" "))
    return text[:limit]


# --- specifications ------------------------------------------------------

_SPEC_LINE = re.compile(r"^([A-Za-z][\w\s/()&.-]{1,60}?)\s*[:–]\s+(.{1,200})$")


def extract_specifications(soup: BeautifulSoup) -> dict[str, str]:
    """Collect key/value specifications from tables, dl lists, spec blocks
    and "Label: value" list items, in that order of confidence."""
    specs: dict[str, str] = {}
    node = main_content(soup)

    for table in node.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) == 2:
                key, val = clean_text(cells[0].get_text()), clean_text(cells[1].get_text())
                if key and val:
                    specs.setdefault(key, val)

    for dl in node.find_all("dl"):
        terms = dl.find_all("dt")
        values = dl.find_all("dd")
        for dt, dd in zip(terms, values):
            key, val = clean_text(dt.get_text()), clean_text(dd.get_text())
            if key and val:
                specs.setdefault(key, val)

    for block in node.select(
        "[class*=spec] li, [class*=Spec] li, [class*=specification] div, "
        "[class*=feature] li, [class*=detail] li"
    ):
        line = clean_text(block.get_text(" "))
        match = _SPEC_LINE.match(line)
        if match:
            specs.setdefault(clean_text(match.group(1)), clean_text(match.group(2)))

    for li in node.find_all("li"):
        line = clean_text(li.get_text(" "))
        match = _SPEC_LINE.match(line)
        if match and len(specs) < 80:
            specs.setdefault(clean_text(match.group(1)), clean_text(match.group(2)))

    return specs


# --- images ---------------------------------------------------------------

def extract_images(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """Content images (absolute URLs), skipping obvious chrome/logos."""
    seen: set[str] = set()
    images: list[dict] = []

    def add(url: str, alt: str = "", source: str = "content"):
        url = absolute(page_url, url)
        low = url.lower()
        if not low.startswith("http"):
            return
        if any(frag in low for frag in config.IMAGE_URL_BLOCKLIST):
            return
        if not re.search(r"\.(jpe?g|png|webp|gif|avif)(\?|$)", low):
            return
        if url in seen:
            return
        seen.add(url)
        images.append({"url": url, "alt": clean_text(alt), "source": source})

    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        add(og["content"], source="og:image")

    node = main_content(soup)
    for img in node.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        srcset = img.get("srcset") or img.get("data-srcset") or ""
        if srcset:  # take the last (largest) candidate
            src = srcset.split(",")[-1].strip().split(" ")[0] or src
        if src:
            add(src, img.get("alt", ""))

    for tag in node.find_all(style=re.compile(r"background(-image)?\s*:")):
        match = re.search(r"url\(['\"]?([^'\")]+)", tag.get("style", ""))
        if match:
            add(match.group(1), source="background")

    return images


# --- links ----------------------------------------------------------------

def extract_links(soup: BeautifulSoup, page_url: str, same_host_only: bool = True) -> list[str]:
    host = urlparse(config.BASE_URL).netloc
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        url = absolute(page_url, a["href"]).split("#")[0]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        if same_host_only and parsed.netloc != host:
            continue
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links
