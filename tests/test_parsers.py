import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scraper import parsers  # noqa: E402
from scraper.discover import classify  # noqa: E402

PRODUCT_HTML = """
<html><head>
<title>SkyKnight | EDGE</title>
<meta property="og:title" content="SkyKnight Air Defence Missile">
<meta property="og:description" content="A compact surface-to-air missile system.">
<meta property="og:image" content="/sites/default/files/skyknight-hero.jpg">
<script type="application/ld+json">
{"@type": "Product", "name": "SkyKnight", "brand": {"name": "HALCON"},
 "description": "Compact SAM."}
</script>
</head><body>
<nav class="breadcrumbs"><a href="/">Home</a><a href="/missiles-weapons">Missiles &amp; Weapons</a><a href="/halcon">HALCON</a></nav>
<main>
  <h1>SkyKnight</h1>
  <div class="product-specs">
    <table>
      <tr><th>Range</th><td>10 km</td></tr>
      <tr><th>Weight</th><td>12 kg</td></tr>
    </table>
    <ul class="specifications">
      <li>Guidance: Ka-band radar seeker</li>
      <li>Length: 1.8 m</li>
    </ul>
  </div>
  <img src="/sites/default/files/skyknight-1.jpg" alt="SkyKnight launcher">
  <img src="/themes/edge/logo.png" alt="EDGE logo">
</main>
</body></html>
"""

NEWS_HTML = """
<html><head>
<title>EDGE signs MoU | EDGE</title>
<meta name="description" content="EDGE Group signs partnership agreement with Acme.">
</head><body>
<main>
  <h1>EDGE and Acme Sign Strategic Partnership</h1>
  <time datetime="2026-02-23T09:00:00Z">23 February 2026</time>
  <p>EDGE Group PJSC announced a memorandum of understanding with Acme Corp.</p>
</main>
</body></html>
"""

ENTITY_HTML = """
<html><head><title>HALCON | EDGE</title>
<meta property="og:description" content="Precision-guided weapons manufacturer.">
</head><body>
<main>
  <h1>HALCON</h1>
  <p>HALCON is a regional leader in precision-guided systems.</p>
  <a href="/solutions/skyknight">SkyKnight</a>
  <a href="/solutions/desert-sting">Desert Sting</a>
  <a href="https://halcon.ae" >Visit website</a>
</main>
</body></html>
"""


def test_parse_product_specs_and_images():
    record = parsers.parse_product(PRODUCT_HTML, "https://edgegroup.ae/solutions/skyknight")
    assert record["slug"] == "skyknight"
    assert record["name"] == "SkyKnight"
    assert record["specifications"]["Range"] == "10 km"
    assert record["specifications"]["Weight"] == "12 kg"
    assert record["specifications"]["Guidance"] == "Ka-band radar seeker"
    assert record["entity"] == "HALCON"
    assert record["category"] == "Missiles & Weapons"
    urls = [img["url"] for img in record["images"]]
    assert "https://edgegroup.ae/sites/default/files/skyknight-hero.jpg" in urls
    assert "https://edgegroup.ae/sites/default/files/skyknight-1.jpg" in urls
    assert all("logo" not in u for u in urls)


def test_parse_news_date_and_partnership_flag():
    record = parsers.parse_news(NEWS_HTML, "https://edgegroup.ae/news/edge-acme-mou")
    assert record["title"] == "EDGE and Acme Sign Strategic Partnership"
    assert record["published_date"] == "2026-02-23"
    assert record["is_partnership"] is True
    partnership = parsers.partnership_from_news(record)
    assert partnership["source_url"] == "https://edgegroup.ae/news/edge-acme-mou"
    assert partnership["date"] == "2026-02-23"


def test_parse_news_date_from_text():
    html = NEWS_HTML.replace('<time datetime="2026-02-23T09:00:00Z">23 February 2026</time>',
                             "<p>Abu Dhabi, 5 March 2026</p>")
    record = parsers.parse_news(html, "https://edgegroup.ae/news/x")
    assert record["published_date"] == "2026-03-05"


def test_parse_entity():
    record = parsers.parse_entity(ENTITY_HTML, "https://edgegroup.ae/halcon")
    assert record["name"] == "HALCON"
    assert record["website"] == "https://halcon.ae"
    assert record["product_urls"] == [
        "https://edgegroup.ae/solutions/skyknight",
        "https://edgegroup.ae/solutions/desert-sting",
    ]


def test_classify():
    assert classify("https://edgegroup.ae/solutions/skyknight") == "products"
    assert classify("https://edgegroup.ae/news/some-story") == "news"
    assert classify("https://edgegroup.ae/halcon") is None
    assert classify("https://edgegroup.ae/") is None
