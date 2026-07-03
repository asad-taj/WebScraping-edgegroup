"""Downloads content images referenced by scraped records into
data/images/<section>/<slug>/, and annotates each image dict with its
local path. Files are named by URL hash so re-runs are idempotent."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config
from .fetch import http_get

log = logging.getLogger(__name__)


def download_images(
    session: requests.Session,
    images: list[dict],
    images_root: Path,
    section: str,
    slug: str,
    max_per_page: int = 12,
) -> list[dict]:
    target_dir = images_root / section / slug
    for image in images[:max_per_page]:
        url = image["url"]
        suffix = Path(urlparse(url).path).suffix.lower() or ".jpg"
        name = hashlib.sha1(url.encode()).hexdigest()[:16] + suffix
        target = target_dir / name
        rel_path = str(target.relative_to(images_root.parent))
        if target.exists():
            image["local_path"] = rel_path
            continue
        resp = http_get(session, url)
        if resp is None:
            log.warning("image download failed: %s", url)
            continue
        ctype = resp.headers.get("Content-Type", "")
        if not ctype.startswith("image/"):
            continue
        if suffix == ".jpg" and ctype != "image/jpeg":
            guessed = mimetypes.guess_extension(ctype.split(";")[0])
            if guessed:
                target = target.with_suffix(guessed)
                rel_path = str(target.relative_to(images_root.parent))
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(resp.content)
        image["local_path"] = rel_path
        time.sleep(config.REQUEST_DELAY_SECONDS / 3)
    return images
