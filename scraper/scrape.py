#!/usr/bin/env python3
"""
Retro Price Watch - scraper
============================
Pulls product catalogs from retro game stores and writes the data file that
the dashboard reads. Each store has its own scraper function; run() combines
them all.

Currently active:
  - RetroFam    (Shopify  -> /collections/<name>/products.json)
  - Retro vGames (WooCommerce -> WC Store API, HTML fallback)

You do NOT need to run this yourself - the daily GitHub job will.
"""

import json, time, sys, os, datetime, tempfile, re

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ================================================================ SHARED
HEADERS = {
    "User-Agent": "RetroPriceWatch/1.0 (personal daily price tracker; contact@example.com)"
}
STORES = [
    {"id": "retrofam",    "name": "RetroFam",     "hue": 38},
    {"id": "retrovgames", "name": "Retro vGames", "hue": 192},
    {"id": "lukiegames",  "name": "LukieGames",   "hue": 330},
    {"id": "dkoldies",    "name": "DKOldies",     "hue": 264},
]
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JS_PATH = os.path.join(HERE, "..", "docs", "retro-data.js")
HISTORY_PATH = os.path.join(HERE, "price-history.json")

def fetch_json(url):
    if requests is None:
        raise RuntimeError("'requests' package is needed.")
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_html(url):
    if requests is None:
        raise RuntimeError("'requests' package is needed.")
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

# ================================================================ RETROFAM (Shopify)
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

def variant_min_price(product):
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
    print("  [retrofam] scraping Shopify collections...")
    seen = {}
    for handle, platform in RETROFAM_COLLECTIONS.items():
        page = 1
        while True:
            url = "https://retrofam.com/collections/%s/products.json?limit=250&page=%d" % (handle, page)
            try:
                data = fetch(url)
            except Exception as e:
                print("    ! skipped %s p%d (%s)" % (handle, page, e))
                break
            products = data.get("products", [])
            if not products:
                break
            for prod in products:
                pid = "retrofam-%s" % prod.get("id")
                if pid in seen:
                    continue
                price = variant_min_price(prod)
                if price is None:
                    continue
                seen[pid] = {
                    "id": pid,
                    "name": (prod.get("title") or "").strip(),
                    "store": "retrofam",
                    "platform": platform,
                    "price": round(price, 2),
                    "url": "https://retrofam.com/products/%s" % prod.get("handle"),
                }
            page += 1
            if sleep:
                time.sleep(sleep)
    print("    got %d products" % len(seen))
    return list(seen.values())


# ================================================================ RETRO VGAMES (WooCommerce)
BASE_RV = "https://retrovgames.com"

# Category slugs -> human platform labels (from site nav).
RETROVGAMES_CATEGORIES = {
    "nintendo-nes": "Nintendo NES",
    "super-nintendo": "Super Nintendo",
    "nintendo-64": "Nintendo 64",
    "gamecube": "Nintendo Gamecube",
    "nintendo-wii": "Nintendo Wii",
    "nintendo-wii-u": "Nintendo Wii U",
    "nintendo-switch": "Nintendo Switch",
    "gameboy": "Game Boy",
    "gameboy-color": "Game Boy Color",
    "gameboy-advance": "Game Boy Advance",
    "nintendo-ds": "Nintendo DS",
    "nintendo-3ds": "Nintendo 3DS",
    "playstation-portable": "PlayStation Portable",
    "playstation-vita": "PlayStation Vita",
    "playstation-1": "PlayStation 1",
    "playstation-2": "PlayStation 2",
    "playstation-3": "PlayStation 3",
    "playstation-4": "PlayStation 4",
    "playstation-5": "PlayStation 5",
    "original-xbox": "Original Xbox",
    "xbox-360": "Xbox 360",
    "xbox-one": "Xbox One",
    "master-system": "Sega Master System",
    "game-gear": "Sega Game Gear",
    "sega-genesis": "Sega Genesis",
    "sega-saturn": "Sega Saturn",
    "sega-dreamcast": "Sega Dreamcast",
    "atari-2600": "Atari 2600",
    "colecovision": "ColecoVision",
    "turbo-grafx-16": "Turbo Grafx 16",
}

# Reverse map: WC category slug -> platform label (for Store API results).
_RV_SLUG_TO_PLATFORM = dict(RETROVGAMES_CATEGORIES)

def _rv_platform_from_categories(cats):
    """Given WC Store API categories list, return the best platform label."""
    for c in cats:
        slug = c.get("slug", "")
        if slug in _RV_SLUG_TO_PLATFORM:
            return _RV_SLUG_TO_PLATFORM[slug]
    # Fallback: use first category name
    return cats[0]["name"] if cats else "Other"

def _rv_try_store_api(sleep=1.0):
    """Try the WooCommerce Store API. Returns list of records or None if unavailable."""
    api = BASE_RV + "/wp-json/wc/store/v1/products"
    seen = {}
    page = 1
    per_page = 100
    while True:
        url = "%s?per_page=%d&page=%d" % (api, per_page, page)
        try:
            data = fetch_json(url)
        except Exception as e:
            if page == 1:
                print("    Store API unavailable: %s" % e)
                return None   # signal: try HTML fallback
            print("    Store API stopped at page %d: %s" % (page, e))
            break
        if not isinstance(data, list) or len(data) == 0:
            break
        for prod in data:
            pid = "retrovgames-%s" % prod.get("id")
            if pid in seen:
                continue
            prices = prod.get("prices", {})
            minor = int(prices.get("currency_minor_unit", 2))
            try:
                price = int(prices.get("price", "0")) / (10 ** minor)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            cats = prod.get("categories", [])
            seen[pid] = {
                "id": pid,
                "name": (prod.get("name") or "").strip(),
                "store": "retrovgames",
                "platform": _rv_platform_from_categories(cats),
                "price": round(price, 2),
                "url": prod.get("permalink", ""),
            }
        if len(data) < per_page:
            break
        page += 1
        if sleep:
            time.sleep(sleep)
    return list(seen.values()) if seen else None

def _rv_parse_price(price_el):
    """Extract the effective price from a WooCommerce .price element.
    Handles regular and sale prices (<ins> for sale)."""
    # If there's an <ins> tag, the product is on sale — take that price
    ins = price_el.find("ins")
    target = ins if ins else price_el
    # Find the amount text
    amount = target.find(class_="woocommerce-Price-amount")
    if not amount:
        return None
    txt = amount.get_text(strip=True)
    # Strip currency symbols and commas, parse float
    cleaned = re.sub(r"[^\d.]", "", txt)
    try:
        return float(cleaned)
    except ValueError:
        return None

def _rv_scrape_category(slug, platform, sleep=1.0):
    """Scrape one WooCommerce category's product listing pages."""
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is needed for HTML scraping fallback.")
    items = {}
    page = 1
    while True:
        if page == 1:
            url = "%s/%s/" % (BASE_RV, slug)
        else:
            url = "%s/%s/page/%d/" % (BASE_RV, slug, page)
        try:
            html = fetch_html(url)
        except Exception as e:
            if page == 1:
                print("    ! category %s failed: %s" % (slug, e))
            break
        soup = BeautifulSoup(html, "html.parser")
        products = soup.select("li.product, li.type-product")
        if not products:
            break
        for li in products:
            # Product link + name
            link = li.find("a", href=True)
            if not link:
                continue
            href = link.get("href", "")
            name_el = li.find("h2") or li.find(class_="woocommerce-loop-product__title")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            # Stable ID from data-product_id or URL slug
            cart_btn = li.find(attrs={"data-product_id": True})
            if cart_btn:
                pid = "retrovgames-%s" % cart_btn["data-product_id"]
            else:
                # Derive from URL slug
                slug_id = href.rstrip("/").rsplit("/", 1)[-1]
                pid = "retrovgames-slug-%s" % slug_id
            if pid in items:
                continue
            # Price
            price_el = li.find(class_="price")
            if not price_el:
                continue
            price = _rv_parse_price(price_el)
            if price is None or price <= 0:
                continue
            items[pid] = {
                "id": pid,
                "name": name,
                "store": "retrovgames",
                "platform": platform,
                "price": round(price, 2),
                "url": href,
            }
        # Check for a next page link
        next_link = soup.select_one("a.next.page-numbers, a.next")
        if not next_link:
            break
        page += 1
        if sleep:
            time.sleep(sleep)
    return items

def _rv_scrape_html(sleep=1.0):
    """Fallback: scrape WooCommerce category pages via HTML."""
    all_items = {}
    for slug, platform in RETROVGAMES_CATEGORIES.items():
        cat_items = _rv_scrape_category(slug, platform, sleep=sleep)
        # Only add items not seen yet (a product might appear in multiple categories)
        for pid, rec in cat_items.items():
            if pid not in all_items:
                all_items[pid] = rec
        print("    %s: %d products" % (slug, len(cat_items)))
    return list(all_items.values())

def scrape_retrovgames(sleep=1.0):
    """Scrape Retro vGames. Tries WC Store API first, falls back to HTML."""
    print("  [retrovgames] trying WC Store API...")
    records = _rv_try_store_api(sleep=sleep)
    if records is not None:
        print("    Store API: got %d products" % len(records))
        return records
    print("  [retrovgames] falling back to HTML category scraping...")
    records = _rv_scrape_html(sleep=sleep)
    print("    HTML scrape: got %d products" % len(records))
    return records


# ================================================================ SHARED PIPELINE
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
    for r in records:
        r["prev"] = history.get(r["id"])
    return records

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

def run(data_path=DATA_JS_PATH, history_path=HISTORY_PATH, sleep=1.0,
        scrapers=None):
    """Run all scrapers, combine, apply price history, write output."""
    if scrapers is None:
        scrapers = [scrape_retrofam, scrape_retrovgames]
    history = load_history(history_path)
    all_records = []
    for scraper in scrapers:
        try:
            records = scraper(sleep=sleep)
            all_records.extend(records)
            print("  -> %d from %s" % (len(records), scraper.__name__))
        except Exception as e:
            print("  !! %s FAILED: %s" % (scraper.__name__, e))
    all_records = apply_prev(all_records, history)
    all_records.sort(key=lambda r: (r["store"], r["platform"], r["name"].lower()))
    write_data_js(all_records, data_path)
    save_history(all_records, history_path)
    drops = sum(1 for r in all_records if r["prev"] and r["price"] < r["prev"])
    new = sum(1 for r in all_records if r["prev"] is None)
    total = len(all_records)
    print("\nTotal: %d products | %d drops | %d new | data -> %s"
          % (total, drops, new, data_path))
    return all_records


# ================================================================ SELF-TEST
def self_test():
    """Prove the logic on fake data (no network needed)."""
    print("=== SELF-TEST ===\n")

    # -- Fake RetroFam (Shopify) --
    rf_catalog = {
        "nintendo-64": [
            {"id": 101, "title": "Super Mario 64", "handle": "super-mario-64",
             "variants": [{"price": "49.99", "available": True}]},
        ],
    }
    def fake_rf_fetch(url):
        handle = url.split("/collections/")[1].split("/")[0]
        page = int(url.split("page=")[1])
        return {"products": rf_catalog.get(handle, []) if page == 1 else []}
    def fake_rf(sleep=1.0):
        return scrape_retrofam(fetch=fake_rf_fetch, sleep=0)

    # -- Fake Retro vGames (WC Store API style) --
    rv_api_data = [
        {"id": 501, "name": "Crash Bandicoot", "permalink": "https://retrovgames.com/crash/",
         "prices": {"price": "2399", "currency_minor_unit": 2},
         "categories": [{"id": 10, "name": "PlayStation 1", "slug": "playstation-1"}]},
        {"id": 502, "name": "Halo CE", "permalink": "https://retrovgames.com/halo/",
         "prices": {"price": "1499", "currency_minor_unit": 2},
         "categories": [{"id": 20, "name": "Original Xbox", "slug": "original-xbox"}]},
    ]
    def fake_rv(sleep=1.0):
        # Simulate Store API success
        seen = {}
        for prod in rv_api_data:
            pid = "retrovgames-%s" % prod["id"]
            prices = prod["prices"]
            minor = int(prices.get("currency_minor_unit", 2))
            price = int(prices["price"]) / (10 ** minor)
            cats = prod.get("categories", [])
            seen[pid] = {
                "id": pid,
                "name": prod["name"],
                "store": "retrovgames",
                "platform": _rv_platform_from_categories(cats),
                "price": round(price, 2),
                "url": prod["permalink"],
            }
        print("  [retrovgames-mock] got %d products" % len(seen))
        return list(seen.values())

    tmp = tempfile.mkdtemp()
    dp = os.path.join(tmp, "retro-data.js")
    hp = os.path.join(tmp, "price-history.json")

    print("-- Day 1 --")
    run(data_path=dp, history_path=hp, sleep=0, scrapers=[fake_rf, fake_rv])

    # Day 2: Mario drops, Crash rises
    rf_catalog["nintendo-64"][0]["variants"][0]["price"] = "39.99"
    rv_api_data[0]["prices"]["price"] = "2699"

    print("\n-- Day 2 --")
    recs = run(data_path=dp, history_path=hp, sleep=0, scrapers=[fake_rf, fake_rv])

    print("\n-- Records --")
    for r in sorted(recs, key=lambda x: x["name"]):
        chg = "NEW" if r["prev"] is None else ("%+.2f" % (r["price"] - r["prev"]))
        print("  %-18s %-12s $%-7.2f prev=%-8s chg=%s"
              % (r["name"], r["store"], r["price"], r["prev"], chg))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        run()
