#!/usr/bin/env python3
"""
Retro Price Watch - scraper
============================
This is the first slice: it pulls RetroFam's full catalog and writes the data
file that the dashboard reads. The other three stores get added the same way.

How it works (plain English):
  1. RetroFam runs on Shopify, which publishes its catalog as clean JSON at
     /collections/<name>/products.json - no fragile HTML scraping needed.
  2. We walk through each console collection (Nintendo 64, SNES, ...), grab every
     product + its price, and tag it with that console as the "platform".
  3. We compare today's prices against the prices we saved last time so each item
     gets a "prev" value -> that's what makes the green price-drop arrows real.
  4. We write everything into dashboard/retro-data.js in exactly the shape the
     design expects:  { id, name, store, platform, price, prev }

You do NOT need to run this yourself - the daily GitHub job will. The --self-test
flag below runs it on fake data so we can prove the logic works without hitting
the live site.
"""

import json, time, sys, os, datetime, tempfile

try:
    import requests
except ImportError:
    requests = None

# ---------------------------------------------------------------- config
STORE_ID = "retrofam"
BASE = "https://retrofam.com"
HEADERS = {
    # Identify the bot honestly and politely. Replace the email before going live.
    "User-Agent": "RetroPriceWatch/1.0 (personal daily price tracker; contact@example.com)"
}

# Each Shopify collection maps to a human-readable console label.
RETROFAM_COLLECTIONS = {
    "nintendo-nes": "Nintendo NES",
    "super-nintendo-snes": "Super Nintendo",
    "nintendo-64": "Nintendo 64",
    "nintendo-gamecube": "Nintendo Gamecube",
    "nintendo-wii": "Nintendo Wii",
    "wii-u": "Wii U",
    "nintendo-gameboy": "Game Boy",
    "gameboy-color": "Game Boy Color",
    "gameboy-advance": "Game Boy Advance",
    "nintendo-ds": "Nintendo DS",
    "nintendo-3ds": "Nintendo 3DS",
    "nintendo-switch": "Nintendo Switch",
    "playstation-1": "PlayStation 1",
    "playstation-2": "PlayStation 2",
    "playstation-3": "PlayStation 3",
    "playstation-4": "PlayStation 4",
    "playstation-5": "PlayStation 5",
    "playstation-portable": "PlayStation Portable",
    "playstation-vita": "PlayStation Vita",
    "original-xbox": "Original Xbox",
    "xbox-360": "Xbox 360",
    "xbox-one": "Xbox One",
    "master-system": "Sega Master System",
    "sega-genesis": "Sega Genesis",
    "game-gear": "Sega Game Gear",
    "sega-saturn": "Sega Saturn",
    "sega-dreamcast": "Sega Dreamcast",
    "atari-2600": "Atari 2600",
    "colecovision": "ColecoVision",
    "neo-geo": "Neo Geo",
    "turbo-grafx-16": "Turbo Grafx 16",
}

# All four stores are declared so the dashboard renders correctly even while only
# RetroFam is wired up. The others fill in as we add their scrapers.
STORES = [
    {"id": "retrofam",    "name": "RetroFam",     "hue": 38},
    {"id": "retrovgames", "name": "Retro vGames", "hue": 192},
    {"id": "lukiegames",  "name": "LukieGames",   "hue": 330},
    {"id": "dkoldies",    "name": "DKOldies",     "hue": 264},
]

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JS_PATH = os.path.join(HERE, "..", "docs", "retro-data.js")
HISTORY_PATH = os.path.join(HERE, "price-history.json")


# ---------------------------------------------------------------- fetching
def fetch_json(url):
    if requests is None:
        raise RuntimeError("The 'requests' package is needed to fetch live data.")
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def variant_min_price(product):
    """A product can have several variants (loose / complete / etc.).
    We track the lowest *available* price -> the cheapest you can actually buy."""
    available, all_prices = [], []
    for v in product.get("variants", []):
        try:
            p = float(v.get("price"))
        except (TypeError, ValueError):
            continue
        all_prices.append(p)
        if v.get("available"):
            available.append(p)
    pool = available or all_prices
    return min(pool) if pool else None


def scrape_retrofam(fetch=fetch_json, sleep=1.0):
    """Walk every collection, return one record per product (deduped)."""
    seen = {}
    for handle, platform in RETROFAM_COLLECTIONS.items():
        page = 1
        while True:
            url = "%s/collections/%s/products.json?limit=250&page=%d" % (BASE, handle, page)
            try:
                data = fetch(url)
            except Exception as e:
                print("  ! skipped %s p%d (%s)" % (handle, page, e))
                break
            products = data.get("products", [])
            if not products:
                break
            for prod in products:
                pid = "%s-%s" % (STORE_ID, prod.get("id"))
                if pid in seen:          # already captured in another collection
                    continue
                price = variant_min_price(prod)
                if price is None:
                    continue
                seen[pid] = {
                    "id": pid,
                    "name": (prod.get("title") or "").strip(),
                    "store": STORE_ID,
                    "platform": platform,
                    "price": round(price, 2),
                    "url": "%s/products/%s" % (BASE, prod.get("handle")),
                }
            page += 1
            if sleep:
                time.sleep(sleep)   # be polite to the store
    return list(seen.values())


# ---------------------------------------------------------------- price history
def load_history(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(records, path):
    hist = {r["id"]: r["price"] for r in records}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=0)


def apply_prev(records, history):
    """Attach yesterday's price as `prev` (None if the item is brand new)."""
    for r in records:
        r["prev"] = history.get(r["id"])
    return records


# ---------------------------------------------------------------- output
def write_data_js(records, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="minutes")
    body = (
        "// AUTO-GENERATED by scrape.py - do not edit by hand.\n"
        "// Last sync: %s\n"
        "window.RETRO_STORES = %s;\n"
        "window.RETRO_DATA = %s;\n"
        "window.RETRO_LAST_SYNC = %s;\n"
    ) % (
        stamp,
        json.dumps(STORES, indent=2),
        json.dumps(records, ensure_ascii=False, indent=2),
        json.dumps(stamp),
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def run(fetch=fetch_json, data_path=DATA_JS_PATH, history_path=HISTORY_PATH, sleep=1.0):
    history = load_history(history_path)
    records = scrape_retrofam(fetch=fetch, sleep=sleep)
    records = apply_prev(records, history)
    records.sort(key=lambda r: (r["platform"], r["name"].lower()))
    write_data_js(records, data_path)
    save_history(records, history_path)
    drops = sum(1 for r in records if r["prev"] and r["price"] < r["prev"])
    new = sum(1 for r in records if r["prev"] is None)
    print("Wrote %d products | %d price drops | %d new | data -> %s"
          % (len(records), drops, new, data_path))
    return records


# ---------------------------------------------------------------- self-test
def self_test():
    """Prove the transform + price-diff logic on fake data (no network)."""
    print("=== SELF-TEST: simulating two daily runs on fake RetroFam data ===\n")

    catalog = {
        "nintendo-64": [
            {"id": 101, "title": "Super Mario 64", "handle": "super-mario-64",
             "variants": [{"price": "49.99", "available": True}]},
            {"id": 102, "title": "GoldenEye 007", "handle": "goldeneye-007",
             "variants": [{"price": "34.99", "available": True}]},
        ],
        "super-nintendo-snes": [
            {"id": 201, "title": "Chrono Trigger", "handle": "chrono-trigger",
             "variants": [{"price": "139.99", "available": False},
                          {"price": "129.99", "available": True}]},
        ],
    }

    def fake_fetch(url):
        # url looks like .../collections/<handle>/products.json?...&page=N
        handle = url.split("/collections/")[1].split("/")[0]
        page = int(url.split("page=")[1])
        return {"products": catalog.get(handle, []) if page == 1 else []}

    tmp = tempfile.mkdtemp()
    data_path = os.path.join(tmp, "retro-data.js")
    hist_path = os.path.join(tmp, "price-history.json")

    print("-- Day 1 (no history yet) --")
    run(fetch=fake_fetch, data_path=data_path, history_path=hist_path, sleep=0)

    # Day 2: Mario drops, GoldenEye rises, Chrono unchanged.
    catalog["nintendo-64"][0]["variants"][0]["price"] = "39.99"
    catalog["nintendo-64"][1]["variants"][0]["price"] = "37.99"
    print("\n-- Day 2 (prices changed) --")
    recs = run(fetch=fake_fetch, data_path=data_path, history_path=hist_path, sleep=0)

    print("\n-- Resulting records (what the dashboard receives) --")
    for r in sorted(recs, key=lambda x: x["name"]):
        chg = "NEW" if r["prev"] is None else ("%+.2f" % (r["price"] - r["prev"]))
        print("  %-18s $%-7.2f prev=%-8s change=%s"
              % (r["name"], r["price"], r["prev"], chg))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        run()
