"""Scrape orchestrator.

Usage:
    python -m scraper.run                          # everything
    python -m scraper.run --sections products,news --limit 10 --no-images
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import config, parsers
from .discover import discover
from .fetch import BrowserFetcher, make_http_session
from .images import download_images
from .store import DataStore

log = logging.getLogger("scraper")

ALL_SECTIONS = ["products", "entities", "news", "partnerships", "group"]


def scrape(sections: list[str], data_dir: Path, limit: int | None,
           with_images: bool, headless: bool) -> int:
    store = DataStore(data_dir)
    session = make_http_session()
    images_root = data_dir / config.IMAGES_DIR
    run_id = store.start_run(sections)
    errors: list[str] = []
    scraped = 0

    def handle_images(record: dict, section: str) -> None:
        if with_images and record.get("images"):
            record["images"] = download_images(
                session, record["images"], images_root, section, record["slug"]
            )

    try:
        with BrowserFetcher(headless=headless) as fetcher:
            wanted = set(sections)
            urls = discover(fetcher, session, wanted)

            def fetch_each(section_urls: list[str]):
                for url in section_urls[: limit or len(section_urls)]:
                    result = fetcher.fetch(url)
                    if not result.ok:
                        errors.append(f"{url} -> HTTP {result.status}")
                        continue
                    time.sleep(config.REQUEST_DELAY_SECONDS)
                    yield url, result.html

            if "products" in wanted:
                log.info("products: %d urls", len(urls["products"]))
                for url, html in fetch_each(urls["products"]):
                    record = parsers.parse_product(html, url)
                    handle_images(record, "products")
                    store.upsert("products", record)
                    scraped += 1

            if "entities" in wanted:
                log.info("entities: %d urls", len(urls["entities"]))
                for url, html in fetch_each(urls["entities"]):
                    record = parsers.parse_entity(html, url)
                    handle_images(record, "entities")
                    store.upsert("entities", record)
                    scraped += 1

            if "news" in wanted or "partnerships" in wanted:
                log.info("news: %d urls", len(urls["news"]))
                for url, html in fetch_each(urls["news"]):
                    record = parsers.parse_news(html, url)
                    handle_images(record, "news")
                    store.upsert("news", record)
                    if record["is_partnership"]:
                        store.upsert(
                            "partnerships",
                            parsers.partnership_from_news(record),
                            key="source_url",
                        )
                    scraped += 1

            if "partnerships" in wanted:
                for seed in config.SECTION_SEEDS["partnerships"]:
                    result = fetcher.fetch(config.BASE_URL + seed)
                    if result.ok:
                        record = parsers.parse_generic(result.html, result.final_url,
                                                       "partnerships")
                        store.upsert("pages", record)
                        scraped += 1

            if "group" in wanted:
                group_paths = config.SECTION_SEEDS["group"] + config.CLUSTER_PATHS
                for seed in group_paths:
                    result = fetcher.fetch(config.BASE_URL + seed)
                    if not result.ok:
                        errors.append(f"{seed} -> HTTP {result.status}")
                        continue
                    section = "cluster" if seed in config.CLUSTER_PATHS else "group"
                    record = parsers.parse_generic(result.html, result.final_url, section)
                    handle_images(record, "group")
                    store.upsert("pages", record)
                    scraped += 1

        store.export_json()
        status = "ok" if not errors else "ok_with_errors"
        store.finish_run(run_id, status, scraped, errors)
        log.info("done: %d pages, %d errors, counts=%s", scraped, len(errors), store.counts())
        return 0 if scraped > 0 else 1
    except Exception as exc:
        log.exception("run failed")
        errors.append(repr(exc))
        store.finish_run(run_id, "failed", scraped, errors)
        return 1
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape edgegroup.ae")
    parser.add_argument("--sections", default=",".join(ALL_SECTIONS),
                        help=f"comma-separated subset of: {','.join(ALL_SECTIONS)}")
    parser.add_argument("--data-dir", default=config.DATA_DIR)
    parser.add_argument("--limit", type=int, default=None,
                        help="max detail pages per section (for testing)")
    parser.add_argument("--no-images", action="store_true",
                        help="skip downloading image files")
    parser.add_argument("--headed", action="store_true",
                        help="run the browser with a visible window")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sections = [s.strip() for s in args.sections.split(",") if s.strip()]
    unknown = set(sections) - set(ALL_SECTIONS)
    if unknown:
        parser.error(f"unknown sections: {', '.join(sorted(unknown))}")

    return scrape(
        sections=sections,
        data_dir=Path(args.data_dir),
        limit=args.limit,
        with_images=not args.no_images,
        headless=not args.headed,
    )


if __name__ == "__main__":
    sys.exit(main())
