#!/usr/bin/env python3
"""
Retro Price Watch - scraper (all 4 stores)
============================================
Pulls product catalogs from four retro game stores and writes the data file
the dashboard reads.

  Store         Platform      Method
  --------      ----------    ------
  RetroFam      Shopify       JSON API (products.json)
  Retro vGames  WooCommerce   WC Store API / HTML fallback
  LukieGames    Shift4Shop    Playwright (headless browser)
  DKOldies      BigCommerce   Playwright (headless browser)

LukieGames and DKOldies have bot protection so they need a real browser.
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

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

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
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


# ================================================================ RETROFAM (Shopify)
RETROFAM_COLLECTIONS = {
    "nintendo-nes":"Nintendo NES","super-nintendo-snes":"Super Nintendo",
    "nintendo-64":"Nintendo 64","nintendo-gamecube":"Nintendo Gamecube",
    "nintendo-wii":"Nintendo Wii","wii-u":"Wii U",
    "nintendo-gameboy":"Game Boy","gameboy-color":"Game Boy Color",
    "gameboy-advance":"Game Boy Advance","nintendo-ds":"Nintendo DS",
    "nintendo-3ds":"Nintendo 3DS","nintendo-switch":"Nintendo Switch",
    "playstation-1":"PlayStation 1","playstation-2":"PlayStation 2",
    "playstation-3":"PlayStation 3","playstation-4":"PlayStation 4",
    "playstation-5":"PlayStation 5","playstation-portable":"PlayStation Portable",
    "playstation-vita":"PlayStation Vita","original-xbox":"Original Xbox",
    "xbox-360":"Xbox 360","xbox-one":"Xbox One",
    "master-system":"Sega Master System","sega-genesis":"Sega Genesis",
    "game-gear":"Sega Game Gear","sega-saturn":"Sega Saturn",
    "sega-dreamcast":"Sega Dreamcast","atari-2600":"Atari 2600",
    "colecovision":"ColecoVision","neo-geo":"Neo Geo",
    "turbo-grafx-16":"Turbo Grafx 16",
}

def variant_min_price(product):
    available, all_p = [], []
    for v in product.get("variants", []):
        try: p = float(v.get("price"))
        except (TypeError, ValueError): continue
        all_p.append(p)
        if v.get("available"): available.append(p)
    pool = available or all_p
    return min(pool) if pool else None

def scrape_retrofam(fetch=None, sleep=1.0):
    print("  [retrofam] scraping Shopify collections...")
    if fetch is None: fetch = fetch_json
    seen = {}
    for handle, platform in RETROFAM_COLLECTIONS.items():
        page = 1
        while True:
            url = "https://retrofam.com/collections/%s/products.json?limit=250&page=%d" % (handle, page)
            try: data = fetch(url)
            except Exception as e:
                print("    ! skipped %s p%d (%s)" % (handle, page, e)); break
            products = data.get("products", [])
            if not products: break
            for prod in products:
                pid = "retrofam-%s" % prod.get("id")
                if pid in seen: continue
                price = variant_min_price(prod)
                if price is None: continue
                seen[pid] = {"id":pid,"name":(prod.get("title") or "").strip(),
                    "store":"retrofam","platform":platform,"price":round(price,2),
                    "url":"https://retrofam.com/products/%s" % prod.get("handle")}
            page += 1
            if sleep: time.sleep(sleep)
    print("    got %d products" % len(seen))
    return list(seen.values())


# ================================================================ RETRO VGAMES (WooCommerce)
BASE_RV = "https://retrovgames.com"
RETROVGAMES_CATEGORIES = {
    "nintendo-nes":"Nintendo NES","super-nintendo":"Super Nintendo",
    "nintendo-64":"Nintendo 64","gamecube":"Nintendo Gamecube",
    "nintendo-wii":"Nintendo Wii","nintendo-wii-u":"Nintendo Wii U",
    "nintendo-switch":"Nintendo Switch","gameboy":"Game Boy",
    "gameboy-color":"Game Boy Color","gameboy-advance":"Game Boy Advance",
    "nintendo-ds":"Nintendo DS","nintendo-3ds":"Nintendo 3DS",
    "playstation-portable":"PlayStation Portable","playstation-vita":"PlayStation Vita",
    "playstation-1":"PlayStation 1","playstation-2":"PlayStation 2",
    "playstation-3":"PlayStation 3","playstation-4":"PlayStation 4",
    "playstation-5":"PlayStation 5","original-xbox":"Original Xbox",
    "xbox-360":"Xbox 360","xbox-one":"Xbox One",
    "master-system":"Sega Master System","game-gear":"Sega Game Gear",
    "sega-genesis":"Sega Genesis","sega-saturn":"Sega Saturn",
    "sega-dreamcast":"Sega Dreamcast","atari-2600":"Atari 2600",
    "colecovision":"ColecoVision","turbo-grafx-16":"Turbo Grafx 16",
}
_RV_SLUG_TO_PLATFORM = dict(RETROVGAMES_CATEGORIES)

def _rv_platform_from_categories(cats):
    for c in cats:
        if c.get("slug","") in _RV_SLUG_TO_PLATFORM:
            return _RV_SLUG_TO_PLATFORM[c["slug"]]
    return cats[0]["name"] if cats else "Other"

def _rv_try_store_api(sleep=1.0):
    api = BASE_RV + "/wp-json/wc/store/v1/products"
    seen = {}; page = 1
    while True:
        url = "%s?per_page=100&page=%d" % (api, page)
        try: data = fetch_json(url)
        except Exception as e:
            if page == 1: print("    Store API unavailable: %s" % e); return None
            break
        if not isinstance(data, list) or not data: break
        for prod in data:
            pid = "retrovgames-%s" % prod.get("id")
            if pid in seen: continue
            prices = prod.get("prices", {})
            minor = int(prices.get("currency_minor_unit", 2))
            try: price = int(prices.get("price","0")) / (10**minor)
            except: continue
            if price <= 0: continue
            cats = prod.get("categories", [])
            seen[pid] = {"id":pid,"name":(prod.get("name") or "").strip(),
                "store":"retrovgames","platform":_rv_platform_from_categories(cats),
                "price":round(price,2),"url":prod.get("permalink","")}
        if len(data) < 100: break
        page += 1
        if sleep: time.sleep(sleep)
    return list(seen.values()) if seen else None

def _rv_parse_price(price_el):
    ins = price_el.find("ins")
    target = ins if ins else price_el
    amount = target.find(class_="woocommerce-Price-amount")
    if not amount: return None
    cleaned = re.sub(r"[^\d.]", "", amount.get_text(strip=True))
    try: return float(cleaned)
    except ValueError: return None

def _rv_scrape_html(sleep=1.0):
    if BeautifulSoup is None: return []
    all_items = {}
    for slug, platform in RETROVGAMES_CATEGORIES.items():
        page = 1
        while True:
            url = "%s/%s/%s" % (BASE_RV, slug, "" if page==1 else "page/%d/" % page)
            try: html = fetch_html(url)
            except: break
            soup = BeautifulSoup(html, "html.parser")
            products = soup.select("li.product, li.type-product")
            if not products: break
            for li in products:
                link = li.find("a", href=True)
                if not link: continue
                name_el = li.find("h2") or li.find(class_="woocommerce-loop-product__title")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name: continue
                btn = li.find(attrs={"data-product_id": True})
                pid = "retrovgames-%s" % btn["data-product_id"] if btn else "retrovgames-slug-%s" % link["href"].rstrip("/").rsplit("/",1)[-1]
                if pid in all_items: continue
                price_el = li.find(class_="price")
                if not price_el: continue
                price = _rv_parse_price(price_el)
                if not price or price <= 0: continue
                all_items[pid] = {"id":pid,"name":name,"store":"retrovgames",
                    "platform":platform,"price":round(price,2),"url":link["href"]}
            if not soup.select_one("a.next.page-numbers, a.next"): break
            page += 1
            if sleep: time.sleep(sleep)
    return list(all_items.values())

def scrape_retrovgames(sleep=1.0):
    print("  [retrovgames] trying WC Store API...")
    records = _rv_try_store_api(sleep=sleep)
    if records is not None:
        print("    Store API: got %d products" % len(records)); return records
    print("  [retrovgames] falling back to HTML...")
    records = _rv_scrape_html(sleep=sleep)
    print("    HTML scrape: got %d products" % len(records)); return records


# ================================================================ PLAYWRIGHT HELPERS
# Used by LukieGames & DKOldies (bot-protected sites).

# JavaScript executed inside the browser to extract products from the page.
# Tries multiple CSS selector patterns common across e-commerce platforms.
EXTRACT_JS = """
() => {
  const results = [];
  const seen = new Set();
  // Try many common product card selectors
  const selectors = [
    'li.product', '.card', '.product-item', '.v-product',
    '[class*="productCard"]', '[class*="ProductCard"]',
    'article.product', '[data-product-id]', '.grid-item--product',
    '.productGrid .product', '.category-product'
  ];
  let cards = [];
  for (const sel of selectors) {
    const found = document.querySelectorAll(sel);
    if (found.length > 2) { cards = found; break; }
  }
  if (cards.length === 0) return results;
  cards.forEach(card => {
    // Find the product link
    const links = card.querySelectorAll('a[href]');
    let link = null;
    for (const a of links) {
      if (a.href && !a.href.includes('cart') && !a.href.includes('wishlist')
          && !a.href.endsWith('#') && a.href.includes('/')) {
        link = a; break;
      }
    }
    if (!link) return;
    // Find product name
    const nameEl = card.querySelector(
      'h2, h3, h4, [class*="title"], [class*="Title"], [class*="name"], [class*="Name"]'
    );
    if (!nameEl) return;
    const name = nameEl.textContent.trim();
    if (!name || name.length < 3) return;
    // Find price - get ALL dollar amounts, take the last one (usually sale/current price)
    const priceEls = card.querySelectorAll(
      '[class*="price"], [class*="Price"], [class*="money"], [class*="Money"]'
    );
    let price = 0;
    for (const pe of priceEls) {
      const matches = pe.textContent.match(/\\$[\\d,]+\\.?\\d*/g);
      if (matches && matches.length > 0) {
        const p = parseFloat(matches[matches.length - 1].replace(/[\\$,]/g, ''));
        if (p > 0) { price = p; break; }
      }
    }
    if (price <= 0) return;
    // Get a stable product ID if available
    const prodId = card.getAttribute('data-product-id')
                || card.querySelector('[data-product-id]')?.getAttribute('data-product-id')
                || card.getAttribute('data-entity-id')
                || '';
    const key = prodId || link.href;
    if (seen.has(key)) return;
    seen.add(key);
    results.push({ name, price, url: link.href, prodId });
  });
  return results;
}
"""

def _pw_scrape_categories(store_id, base_url, categories, sleep=2.0, max_pages=50):
    """Scrape category pages using Playwright. Returns list of records."""
    if not HAS_PLAYWRIGHT:
        print("    Playwright not installed, skipping %s" % store_id)
        return []
    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        for slug, platform in categories.items():
            pg = 1
            while pg <= max_pages:
                if "?" in slug:
                    url = "%s/%s%s" % (base_url, slug, "&page=%d" % pg if pg > 1 else "")
                else:
                    url = "%s/%s/" % (base_url, slug)
                    if pg > 1:
                        url += "?page=%d" % pg
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if resp and resp.status >= 400:
                        if pg == 1:
                            print("    ! %s returned %d, skipping" % (slug, resp.status))
                        break
                except Exception as e:
                    print("    ! %s page %d error: %s" % (slug, pg, e))
                    break
                # Wait for products to render
                time.sleep(2)
                try:
                    page.wait_for_selector('[class*="product"], [class*="Product"], .card, .grid-item', timeout=8000)
                except:
                    if pg == 1:
                        print("    ! %s: no product elements found" % slug)
                    break
                # Extract products
                try:
                    products = page.evaluate(EXTRACT_JS)
                except Exception as e:
                    print("    ! %s extract error: %s" % (slug, e))
                    break
                if not products:
                    break
                new_on_page = 0
                for prod in products:
                    pid_key = prod.get("prodId") or prod["url"].rstrip("/").rsplit("/",1)[-1]
                    pid = "%s-%s" % (store_id, pid_key)
                    if pid in seen:
                        continue
                    seen[pid] = {
                        "id": pid,
                        "name": prod["name"],
                        "store": store_id,
                        "platform": platform,
                        "price": round(prod["price"], 2),
                        "url": prod["url"],
                    }
                    new_on_page += 1
                if new_on_page == 0:
                    break  # No new products = we've exhausted this category
                pg += 1
                if sleep:
                    time.sleep(sleep)
            # Brief log per category
            cat_count = sum(1 for r in seen.values() if r["platform"] == platform)
            if cat_count:
                print("    %s: %d products" % (platform, cat_count))
        browser.close()
    return list(seen.values())


# ================================================================ LUKIEGAMES (Shift4Shop)
# LukieGames uses Shift4Shop. Category URL structure from site navigation.
LUKIEGAMES_CATEGORIES = {
    # slug -> platform label (URLs are lukiegames.com/<slug>)
    "buy-used-nes-nintendo-games-online": "Nintendo NES",
    "buy-used-super-nintendo-snes-games-online": "Super Nintendo",
    "buy-used-nintendo-64-n64": "Nintendo 64",
    "buy-used-gamecube-games-online": "Nintendo Gamecube",
    "buy-used-wii-games": "Nintendo Wii",
    "buy-used-wii-u-games-online": "Wii U",
    "buy-used-nintendo-switch-games-online": "Nintendo Switch",
    "buy-used-gameboy-games-online": "Game Boy",
    "buy-used-gameboy-color-games-online": "Game Boy Color",
    "buy-used-gameboy-advance-games-online": "Game Boy Advance",
    "buy-used-nintendo-ds-games-online": "Nintendo DS",
    "buy-used-nintendo-3ds-games-online": "Nintendo 3DS",
    "buy-used-playstation-ps1-games-online": "PlayStation 1",
    "buy-used-playstation-2-ps2-games-online": "PlayStation 2",
    "buy-used-playstation-3-ps3-games-online": "PlayStation 3",
    "buy-used-playstation-4-ps4-games-online": "PlayStation 4",
    "buy-used-psp-games-online": "PlayStation Portable",
    "buy-used-ps-vita-games-online": "PlayStation Vita",
    "buy-used-original-xbox-games-online": "Original Xbox",
    "buy-used-xbox-360-games-online": "Xbox 360",
    "buy-used-xbox-one-games-online": "Xbox One",
    "buy-used-sega-genesis-games-online": "Sega Genesis",
    "buy-used-sega-dreamcast-games-online": "Sega Dreamcast",
    "buy-used-sega-saturn-games-online": "Sega Saturn",
    "buy-used-sega-game-gear-games-online": "Sega Game Gear",
    "buy-used-sega-master-system-games-online": "Sega Master System",
    "buy-used-atari-2600-games-online": "Atari 2600",
    "buy-used-atari-7800-games-online": "Atari 7800",
}

def scrape_lukiegames(sleep=2.0):
    print("  [lukiegames] scraping with Playwright...")
    # LukieGames Shift4Shop pagination: .html then _c_X-2.html, _c_X-3.html etc.
    # Since the URL pattern is complex, we paginate by finding "Next" links.
    if not HAS_PLAYWRIGHT:
        print("    Playwright not installed, skipping"); return []
    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        for slug, platform in LUKIEGAMES_CATEGORIES.items():
            url = "https://www.lukiegames.com/%s.html" % slug
            pg = 0
            while url and pg < 50:
                pg += 1
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if resp and resp.status >= 400:
                        if pg == 1: print("    ! %s returned %d" % (slug, resp.status))
                        break
                except Exception as e:
                    print("    ! %s error: %s" % (slug, e)); break
                time.sleep(2)
                try:
                    products = page.evaluate(EXTRACT_JS)
                except:
                    break
                if not products: break
                new_count = 0
                for prod in products:
                    pid_key = prod.get("prodId") or prod["url"].rstrip("/").split("/")[-1].replace(".html","")
                    pid = "lukiegames-%s" % pid_key
                    if pid in seen: continue
                    seen[pid] = {"id":pid,"name":prod["name"],"store":"lukiegames",
                        "platform":platform,"price":round(prod["price"],2),"url":prod["url"]}
                    new_count += 1
                if new_count == 0: break
                # Find next page link
                next_url = page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a[class*="next"], a[rel="next"], .pagination a');
                        for (const a of links) {
                            if (a.textContent.includes('Next') || a.textContent.includes('»') || a.textContent.includes('>'))
                                return a.href;
                        }
                        return null;
                    }
                """)
                url = next_url
                if sleep: time.sleep(sleep)
            cat_count = sum(1 for r in seen.values() if r["platform"] == platform)
            if cat_count:
                print("    %s: %d products" % (platform, cat_count))
        browser.close()
    print("    total: %d products" % len(seen))
    return list(seen.values())


# ================================================================ DKOLDIES (BigCommerce)
DKOLDIES_CATEGORIES = {
    "nintendo":"Nintendo NES","super-nintendo":"Super Nintendo",
    "nintendo-64":"Nintendo 64","gamecube":"Nintendo Gamecube",
    "wii":"Nintendo Wii","wii-u":"Wii U",
    "game-boy":"Game Boy","game-boy-color":"Game Boy Color",
    "game-boy-advance":"Game Boy Advance","ds":"Nintendo DS",
    "3ds":"Nintendo 3DS",
    "playstation-1":"PlayStation 1","playstation-2":"PlayStation 2",
    "playstation-3":"PlayStation 3","psp":"PlayStation Portable",
    "ps-vita":"PlayStation Vita",
    "xbox":"Original Xbox","xbox-360":"Xbox 360",
    "sega-genesis":"Sega Genesis","sega-dreamcast":"Sega Dreamcast",
    "sega-saturn":"Sega Saturn","sega-game-gear":"Sega Game Gear",
    "sega-master-system":"Sega Master System",
    "atari-2600":"Atari 2600","atari-7800":"Atari 7800",
}

def scrape_dkoldies(sleep=2.0):
    print("  [dkoldies] scraping with Playwright...")
    return _pw_scrape_categories("dkoldies", "https://www.dkoldies.com",
                                  DKOLDIES_CATEGORIES, sleep=sleep)


# ================================================================ SHARED PIPELINE
def load_history(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
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
    ) % (stamp, json.dumps(STORES, indent=2),
         json.dumps(records, ensure_ascii=False, indent=2), json.dumps(stamp))
    with open(path, "w", encoding="utf-8") as f: f.write(body)

def run(data_path=DATA_JS_PATH, history_path=HISTORY_PATH, sleep=1.0, scrapers=None):
    if scrapers is None:
        scrapers = [scrape_retrofam, scrape_retrovgames, scrape_lukiegames, scrape_dkoldies]
    history = load_history(history_path)
    all_records = []
    for scraper in scrapers:
        try:
            records = scraper(sleep=sleep)
            all_records.extend(records)
            print("  -> %d from %s" % (len(records), scraper.__name__))
        except Exception as e:
            print("  !! %s FAILED: %s" % (scraper.__name__, e))
            import traceback; traceback.print_exc()
    all_records = apply_prev(all_records, history)
    all_records.sort(key=lambda r: (r["store"], r["platform"], r["name"].lower()))
    write_data_js(all_records, data_path)
    save_history(all_records, history_path)
    drops = sum(1 for r in all_records if r["prev"] and r["price"] < r["prev"])
    new = sum(1 for r in all_records if r["prev"] is None)
    print("\nTotal: %d products | %d drops | %d new | data -> %s"
          % (len(all_records), drops, new, data_path))
    return all_records


# ================================================================ SELF-TEST
def self_test():
    print("=== SELF-TEST (RetroFam + RVG mock, no Playwright) ===\n")
    rf_catalog = {"nintendo-64": [
        {"id":101,"title":"Super Mario 64","handle":"sm64",
         "variants":[{"price":"49.99","available":True}]},
    ]}
    def fake_rf_fetch(url):
        h = url.split("/collections/")[1].split("/")[0]
        pg = int(url.split("page=")[1])
        return {"products": rf_catalog.get(h,[]) if pg==1 else []}
    def fake_rf(sleep=1.0): return scrape_retrofam(fetch=fake_rf_fetch, sleep=0)
    rv_data = [{"id":501,"name":"Crash Bandicoot","permalink":"https://retrovgames.com/crash/",
        "prices":{"price":"2399","currency_minor_unit":2},
        "categories":[{"id":10,"name":"PlayStation 1","slug":"playstation-1"}]}]
    def fake_rv(sleep=1.0):
        out = []
        for prod in rv_data:
            p = int(prod["prices"]["price"]) / 100
            out.append({"id":"retrovgames-%s"%prod["id"],"name":prod["name"],
                "store":"retrovgames","platform":prod["categories"][0]["name"],
                "price":round(p,2),"url":prod["permalink"]})
        return out
    tmp = tempfile.mkdtemp()
    dp, hp = os.path.join(tmp,"retro-data.js"), os.path.join(tmp,"history.json")
    print("-- Day 1 --")
    run(data_path=dp, history_path=hp, sleep=0, scrapers=[fake_rf, fake_rv])
    rf_catalog["nintendo-64"][0]["variants"][0]["price"] = "39.99"
    rv_data[0]["prices"]["price"] = "2699"
    print("\n-- Day 2 --")
    recs = run(data_path=dp, history_path=hp, sleep=0, scrapers=[fake_rf, fake_rv])
    print("\n-- Records --")
    for r in sorted(recs, key=lambda x: x["name"]):
        chg = "NEW" if r["prev"] is None else ("%+.2f" % (r["price"]-r["prev"]))
        print("  %-18s %-12s $%-7.2f prev=%-8s chg=%s" % (r["name"],r["store"],r["price"],r["prev"],chg))

if __name__ == "__main__":
    if "--self-test" in sys.argv: self_test()
    else: run()
