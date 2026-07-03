# EDGE Group Website Scraper

Scrapes the public website of [EDGE Group PJSC](https://edgegroup.ae) and
stores the results in a local data store. Covered sections:

| Section          | Source pages                              | Stored in            |
|------------------|-------------------------------------------|----------------------|
| **Products**     | `/solutions` listing + `/solutions/<slug>` | `products` table — name, category, owning entity, description, specifications (key/value JSON), images |
| **Entities**     | `/entities` + each entity page (`/halcon`, `/caracal`, …) | `entities` table — name, description, external website, linked products, images |
| **News**         | `/media`, `/inthenews` + `/news/<slug>`    | `news` table — title, published date, body text, images |
| **Partnerships** | Dedicated pages if present, plus news articles flagged by partnership keywords (MoU, joint venture, agreement, …) | `partnerships` table |
| **Group details**| `/about`, homepage, cluster pages (`/platforms-systems`, …) | `pages` table |

## Data store

Everything lives under `data/`:

```
data/
  edgegroup.db      # SQLite — canonical store (products, entities, news,
                    #   partnerships, pages, scrape_runs)
  json/             # per-table JSON exports, regenerated each run
  images/           # downloaded content images, images/<section>/<slug>/<hash>.<ext>
```

Records are upserted by URL with `first_seen` / `last_updated` timestamps and
a content hash, so monthly runs only rewrite rows whose content actually
changed. Each run is logged in the `scrape_runs` table.

## Running locally

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium

python -m scraper.run                                   # full scrape
python -m scraper.run --sections products --limit 5     # quick test
python -m scraper.run --no-images                       # skip image downloads
```

If a Chromium is already installed somewhere (e.g. a sandbox with
pre-provisioned browsers), skip `playwright install` and point the scraper at
it: `CHROMIUM_EXECUTABLE=/path/to/chrome python -m scraper.run ...`

The site is served behind Cloudflare and rejects plain HTTP clients, so pages
are fetched with a real Chromium browser via Playwright (plain `requests` is
used only for sitemaps and image files). The scraper waits
~1.5&nbsp;s between page loads to stay polite.

## Scheduled & on-demand updates

`.github/workflows/scrape.yml` runs the scraper:

- **Monthly** — cron `0 4 1 * *` (04:00 UTC on the 1st of each month)
- **User-triggered** — the *Run workflow* button (`workflow_dispatch`) in the
  Actions tab, with inputs for sections, per-section page limit, and whether
  to download images

After each run the workflow commits any changed files under `data/` back to
the branch it ran on and also uploads the database + JSON exports as a build
artifact (kept 90 days).

> Note: scheduled workflows only fire on the repository's default branch, so
> merge this branch (or set it as default) to activate the monthly cron.
> Manual `workflow_dispatch` runs can target any branch containing the
> workflow.

## Architecture

```
scraper/
  config.py     # URLs, section seeds, politeness settings
  fetch.py      # Playwright browser fetcher (+ requests session for assets)
  discover.py   # URL discovery: sitemap.xml + listing-page crawl
  parse.py      # generic extraction: meta, JSON-LD, specs, images, links
  parsers.py    # section-specific record builders
  images.py     # content-image downloader
  store.py      # SQLite schema, upserts, JSON export
  run.py        # CLI orchestrator (python -m scraper.run)
tests/          # parser + store unit tests (run with pytest)
```

Parsers are heuristic by design: the site is Drupal-based and its markup can
change, so extraction relies on stable signals (meta/OpenGraph tags, JSON-LD,
spec tables, definition lists, breadcrumbs) and always preserves the page's
readable body text, ensuring a selector miss never loses content entirely.
