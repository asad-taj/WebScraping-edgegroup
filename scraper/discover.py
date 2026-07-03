"""URL discovery: sitemap.xml first, listing pages as the fallback/top-up.

Returns per-section URL lists:
    products  -> /solutions/<slug>
    news      -> /news/<slug>
    entities  -> pages linked from /entities (top-level slugs)
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from . import config, parse
from .fetch import BrowserFetcher, http_get

log = logging.getLogger(__name__)


def urls_from_sitemaps(session) -> list[str]:
    found: list[str] = []
    queue = [config.BASE_URL + path for path in config.SITEMAP_CANDIDATES]
    seen: set[str] = set()
    while queue:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)
        resp = http_get(session, sitemap_url)
        if resp is None:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", resp.text)
        for loc in locs:
            if loc.endswith(".xml"):
                queue.append(loc)
            else:
                found.append(loc)
    return found


def classify(url: str) -> str | None:
    path = urlparse(url).path
    if not path or path == "/":
        return None
    for section, prefixes in config.SECTION_PATH_PREFIXES.items():
        if any(path.startswith(p) for p in prefixes):
            return section
    return None


def discover(fetcher: BrowserFetcher, session, sections: set[str]) -> dict[str, list[str]]:
    discovered: dict[str, set[str]] = {"products": set(), "news": set(), "entities": set()}

    for url in urls_from_sitemaps(session):
        section = classify(url)
        if section in discovered:
            discovered[section].add(url.split("?")[0])
    log.info(
        "sitemap discovery: %s",
        {k: len(v) for k, v in discovered.items()},
    )

    if "products" in sections:
        for seed in config.SECTION_SEEDS["products"]:
            result = fetcher.fetch(config.BASE_URL + seed, expand_listings=True)
            if result.ok:
                for link in parse.extract_links(parse.soup_of(result.html), result.final_url):
                    if classify(link) == "products":
                        discovered["products"].add(link)

    if "news" in sections:
        for seed in config.SECTION_SEEDS["news"]:
            result = fetcher.fetch(config.BASE_URL + seed, expand_listings=True)
            if result.ok:
                for link in parse.extract_links(parse.soup_of(result.html), result.final_url):
                    if classify(link) == "news":
                        discovered["news"].add(link)

    if "entities" in sections:
        # Entity pages are top-level slugs; trust only links found on /entities.
        for seed in config.SECTION_SEEDS["entities"]:
            result = fetcher.fetch(config.BASE_URL + seed, expand_listings=True)
            if not result.ok:
                continue
            soup = parse.soup_of(result.html)
            for link in parse.extract_links(soup, result.final_url):
                path = urlparse(link).path.rstrip("/")
                if (
                    re.fullmatch(r"/[a-z0-9-]+", path)
                    and classify(link) is None
                    and path not in ("/entities", "/about", "/media", "/inthenews",
                                     "/solutions", "/careers", "/contact", "/search",
                                     "/privacy-policy", "/terms", "/sitemap")
                    and path not in config.CLUSTER_PATHS
                ):
                    discovered["entities"].add(link)

    return {k: sorted(v) for k, v in discovered.items()}
