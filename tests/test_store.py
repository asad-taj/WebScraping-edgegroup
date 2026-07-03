import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scraper.store import DataStore  # noqa: E402


def make_product(**overrides):
    record = {
        "url": "https://edgegroup.ae/solutions/skyknight",
        "slug": "skyknight",
        "name": "SkyKnight",
        "category": "Missiles & Weapons",
        "entity": "HALCON",
        "description": "Compact SAM.",
        "specifications": {"Range": "10 km"},
        "images": [{"url": "https://edgegroup.ae/x.jpg", "alt": "", "source": "content"}],
        "body_text": "SkyKnight ...",
        "meta": {"title": "SkyKnight"},
    }
    record.update(overrides)
    return record


def test_upsert_insert_update_and_change_tracking(tmp_path):
    store = DataStore(tmp_path)
    store.upsert("products", make_product())
    row = store.conn.execute("SELECT * FROM products").fetchone()
    first_seen = row["first_seen"]
    assert json.loads(row["specifications"]) == {"Range": "10 km"}

    # identical record: no rewrite
    store.upsert("products", make_product())
    row2 = store.conn.execute("SELECT * FROM products").fetchone()
    assert row2["last_updated"] == row["last_updated"]

    # changed record: updated, first_seen preserved
    store.upsert("products", make_product(specifications={"Range": "12 km"}))
    row3 = store.conn.execute("SELECT * FROM products").fetchone()
    assert json.loads(row3["specifications"]) == {"Range": "12 km"}
    assert row3["first_seen"] == first_seen
    assert store.counts()["products"] == 1
    store.close()


def test_export_json(tmp_path):
    store = DataStore(tmp_path)
    store.upsert("products", make_product())
    store.upsert(
        "partnerships",
        {"source_url": "https://edgegroup.ae/news/mou", "title": "MoU",
         "description": "d", "date": "2026-01-01", "source": "news"},
        key="source_url",
    )
    store.export_json()
    products = json.loads((tmp_path / "json" / "products.json").read_text())
    assert products[0]["name"] == "SkyKnight"
    assert products[0]["specifications"] == {"Range": "10 km"}
    partnerships = json.loads((tmp_path / "json" / "partnerships.json").read_text())
    assert partnerships[0]["title"] == "MoU"
    store.close()


def test_run_lifecycle(tmp_path):
    store = DataStore(tmp_path)
    run_id = store.start_run(["products"])
    store.finish_run(run_id, "ok", 5, [])
    row = store.conn.execute("SELECT * FROM scrape_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "ok"
    assert row["pages_scraped"] == 5
    store.close()
