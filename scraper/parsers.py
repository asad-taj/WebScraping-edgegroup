"""Section-specific record builders (products, entities, news, partnerships,
group details). Each takes rendered HTML and returns a plain dict ready for
the data store."""

from __future__ import annotations

import re

from . import config, parse


def _base_record(html: str, url: str) -> tuple[dict, "parse.BeautifulSoup"]:
    soup = parse.soup_of(html)
    meta = parse.extract_meta(soup)
    record = {
        "url": url,
        "slug": parse.slug_of(url),
        "name": parse.extract_heading(soup) or meta.get("title") or meta.get("page_title", ""),
        "description": meta.get("description", ""),
        "meta": meta,
        "jsonld": parse.extract_jsonld(soup),
        "body_text": parse.extract_body_text(soup),
        "images": parse.extract_images(soup, url),
    }
    return record, soup


def parse_product(html: str, url: str) -> dict:
    record, soup = _base_record(html, url)
    record["specifications"] = parse.extract_specifications(soup)

    # Enrich from JSON-LD Product blocks when present.
    for block in record["jsonld"]:
        if block.get("@type") in ("Product", "Vehicle"):
            record["name"] = record["name"] or parse.clean_text(str(block.get("name", "")))
            record["description"] = record["description"] or parse.clean_text(
                str(block.get("description", ""))
            )
            brand = block.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            if brand:
                record["entity"] = parse.clean_text(str(brand))

    # Breadcrumbs usually carry the category / owning entity.
    crumbs = [
        parse.clean_text(a.get_text())
        for a in soup.select("[class*=breadcrumb] a, nav[aria-label*=readcrumb] a")
    ]
    crumbs = [c for c in crumbs if c and c.lower() not in ("home", "edge")]
    if crumbs:
        record.setdefault("category", crumbs[0])
        if len(crumbs) > 1:
            record.setdefault("entity", crumbs[-1])
    record.setdefault("category", "")
    record.setdefault("entity", "")
    return record


def parse_entity(html: str, url: str) -> dict:
    record, soup = _base_record(html, url)

    website = ""
    for a in soup.find_all("a", href=True):
        text = parse.clean_text(a.get_text()).lower()
        href = a["href"]
        if ("visit" in text or "website" in text) and href.startswith("http") \
                and "edgegroup.ae" not in href:
            website = href
            break
    record["website"] = website

    # Product links on the entity page (relative /solutions/... links).
    record["product_urls"] = [
        u for u in parse.extract_links(soup, url)
        if any(u.startswith(config.BASE_URL + p) for p in config.SECTION_PATH_PREFIXES["products"])
    ]
    record.setdefault("cluster", "")
    return record


_DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+(\d{4})\b", re.I),
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
)

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
)}


def _find_date(soup, jsonld: list[dict], body_text: str) -> str:
    for block in jsonld:
        for key in ("datePublished", "dateCreated", "dateModified"):
            if block.get(key):
                return str(block[key])[:10]
    time_tag = soup.find("time")
    if time_tag:
        if time_tag.get("datetime"):
            return str(time_tag["datetime"])[:10]
        body_text = parse.clean_text(time_tag.get_text()) + " " + body_text
    sample = body_text[:600]
    for pattern in _DATE_PATTERNS:
        match = pattern.search(sample)
        if not match:
            continue
        groups = match.groups()
        if pattern is _DATE_PATTERNS[2]:
            return match.group(0)
        if groups[0].isdigit():  # "12 March 2026"
            day, month, year = groups
        else:  # "March 12, 2026"
            month, day, year = groups
        return f"{year}-{_MONTHS[month[:3].lower()]:02d}-{int(day):02d}"
    return ""


def parse_news(html: str, url: str) -> dict:
    record, soup = _base_record(html, url)
    record["title"] = record.pop("name")
    record["published_date"] = _find_date(soup, record["jsonld"], record["body_text"])
    haystack = (record["title"] + " " + record["body_text"][:1500]).lower()
    record["is_partnership"] = any(k in haystack for k in config.PARTNERSHIP_KEYWORDS)
    return record


def partnership_from_news(news: dict) -> dict:
    """Derive a partnership record from a partnership-flagged news article."""
    return {
        "title": news["title"],
        "description": news["description"] or news["body_text"][:500],
        "date": news["published_date"],
        "source_url": news["url"],
        "source": "news",
    }


def parse_generic(html: str, url: str, section: str) -> dict:
    """Group/about/cluster/partnership pages: keep everything readable."""
    record, _ = _base_record(html, url)
    record["section"] = section
    return record
