"""Central configuration for the EDGE Group scraper."""

BASE_URL = "https://edgegroup.ae"

# Listing pages used to discover detail pages, in addition to the sitemap.
SECTION_SEEDS = {
    "products": ["/solutions"],
    "entities": ["/entities"],
    "news": ["/media", "/inthenews"],
    "partnerships": ["/partnerships", "/partners"],
    "group": ["/about", "/"],
}

# URL path prefixes that classify a discovered URL into a section.
SECTION_PATH_PREFIXES = {
    "products": ("/solutions/",),
    "news": ("/news/", "/inthenews/", "/media/"),
}

# Cluster landing pages (also scraped as part of group/entity context).
CLUSTER_PATHS = [
    "/platforms-systems",
    "/missiles-weapons",
    "/space-cyber-technologies",
    "/edge-commercial",
    "/technology-industrialisation",
    "/homeland-security",
]

SITEMAP_CANDIDATES = ["/sitemap.xml", "/sitemap_index.xml"]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Politeness settings.
REQUEST_DELAY_SECONDS = 1.5
PAGE_TIMEOUT_MS = 45_000
MAX_RETRIES = 3

# Data store layout (relative to repo root unless overridden on the CLI).
DATA_DIR = "data"
DB_FILENAME = "edgegroup.db"
JSON_DIR = "json"
IMAGES_DIR = "images"

# News headlines matching these keywords are also recorded as partnerships.
PARTNERSHIP_KEYWORDS = (
    "partnership",
    "partner",
    "joint venture",
    "mou",
    "memorandum of understanding",
    "collaborat",
    "agreement",
    "teaming",
    "alliance",
)

# Image URLs containing these fragments are treated as page chrome, not content.
IMAGE_URL_BLOCKLIST = (
    "logo",
    "icon",
    "favicon",
    "sprite",
    "placeholder",
    "flag",
)
