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

import json, time, sys, os, datetime, tempfile, re, inspect

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
SCRAPER_VERSION = "v8-dkoldies-api"

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
EXTRACT_JS = r"""
() => {
  const results = [];
  const seen = new Set();
  // Try many common product card selectors
  const selectors = [
    'ul.productGrid > li', '.productGrid li.product', 'article.card',
    'li.product', 'div.product', '.product-item', '.v-product',
    '[class*="productCard"]', '[class*="ProductCard"]',
    'article.product', '[data-product-id]', '[data-entity-id]',
    '.grid-item--product', '.productGrid .product', '.category-product'
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
      const matches = pe.textContent.match(/\$[\d,]+\.?\d*/g);
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

# LukieGames uses the SearchSpring widget: products are <article class="ss__result">
LUKIE_EXTRACT_JS = r"""
() => {
  const out = [];
  document.querySelectorAll('article.ss__result, .ss__result--item').forEach(card => {
    const nameA = card.querySelector('.ss__result__name a') || card.querySelector('.ss__result__name');
    const linkA = card.querySelector('.ss__result__name a') || card.querySelector('a.ss__result__image__link') || card.querySelector('a[href]');
    if (!nameA || !linkA) return;
    const name = (nameA.textContent || '').trim();
    const url = linkA.href;
    if (!name || !url) return;
    // Prefer the actual selling price (on sale), else the MSRP
    const sale = card.querySelector('.ss__result__price');
    const msrp = card.querySelector('.ss__result__msrp');
    const txt = ((sale ? sale.textContent : '') + ' ' + (msrp ? msrp.textContent : ''));
    const m = txt.match(/\$[\d,]+\.?\d*/);
    if (!m) return;
    const price = parseFloat(m[0].replace(/[$,]/g, ''));
    if (!(price > 0)) return;
    out.push({ name, price, url, prodId: '' });
  });
  return out;
}
"""

def _wait_scroll_extract(page, settle=1.0):
    """Wait for product cards to render, scroll to trigger lazy loads, then extract.
    Returns a list of product dicts (possibly empty)."""
    import time as _t
    # Give product elements a chance to appear (non-fatal if they don't)
    try:
        page.wait_for_selector(
            'ul.productGrid, li.product, article.card, [data-product-id], [class*="product"]',
            timeout=8000)
    except Exception:
        pass
    # Scroll down to trigger any lazy-loaded images/cards, then back up
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _t.sleep(settle)
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    _t.sleep(settle)
    try:
        return page.evaluate(EXTRACT_JS)
    except Exception:
        return []

def _dump_debug(page, store_id):
    """Save the current page HTML + report selector match counts, so we can
    diagnose extraction without guessing. Files land next to run-scraper.bat."""
    root = os.path.dirname(HERE)
    try:
        html = page.content()
    except Exception:
        html = ""
    try:
        with open(os.path.join(root, "debug-%s.html" % store_id), "w", encoding="utf-8") as f:
            f.write(html)
        print("    [debug] saved page HTML -> debug-%s.html (%d chars)" % (store_id, len(html)))
    except Exception as e:
        print("    [debug] could not save HTML: %s" % e)
    try:
        sels = ['ul.productGrid > li','li.product','div.product','article.card',
                '.product-item','.v-product','[data-product-id]','[data-entity-id]',
                '.card','[class*="product"]','[class*="Product"]']
        counts = page.evaluate("(s)=>s.map(x=>x+'='+document.querySelectorAll(x).length)", sels)
        print("    [debug] selector counts: " + " | ".join(counts))
    except Exception as e:
        print("    [debug] selector count failed: %s" % e)


# ================================================================ LUKIEGAMES (Shift4Shop)
# We no longer hardcode category URLs. Instead we read the site's own nav menu
# and match each console to the real link it points to. LG_WANTED maps a platform
# label to the nav text(s) we accept for it (most specific first).
LG_WANTED = [
    ("Nintendo NES",        ["NES Games", "Nintendo NES"]),
    ("Super Nintendo",      ["SNES Games", "Super Nintendo"]),
    ("Nintendo 64",         ["N64 Games", "Nintendo 64"]),
    ("Nintendo Gamecube",   ["Gamecube Games", "Gamecube"]),
    ("Nintendo Wii",        ["Wii Games", "Nintendo Wii"]),
    ("Wii U",               ["Wii U"]),
    ("Game Boy Advance",    ["Gameboy Advance Games", "Gameboy Advance"]),
    ("Game Boy Color",      ["Gameboy Color Games", "Gameboy Color"]),
    ("Game Boy",            ["Gameboy"]),
    ("Nintendo DS",         ["DS Games", "Nintendo DS"]),
    ("Nintendo 3DS",        ["3DS Games", "Nintendo 3DS"]),
    ("PlayStation 1",       ["PS1 Games", "Playstation 1"]),
    ("PlayStation 2",       ["PS2 Games", "Playstation 2"]),
    ("PlayStation 3",       ["PS3 Games", "Playstation 3"]),
    ("PlayStation 4",       ["Playstation 4"]),
    ("PlayStation Portable",["PSP Games", "Sony PSP"]),
    ("PlayStation Vita",    ["Playstation Vita", "Sony Vita"]),
    ("Original Xbox",       ["Xbox Games", "Original Xbox"]),
    ("Xbox 360",            ["Xbox 360 Games", "Xbox 360"]),
    ("Xbox One",            ["Xbox One"]),
    ("Sega Genesis",        ["Genesis Games", "Sega Genesis"]),
    ("Sega Saturn",         ["Sega Saturn"]),
    ("Sega Dreamcast",      ["Sega Dreamcast"]),
    ("Sega Game Gear",      ["Sega Game Gear"]),
    ("Sega Master System",  ["Sega Master System"]),
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

def _make_stealth_context(browser, ua=None):
    """Create a browser context that looks like a real user."""
    import random
    ua = ua or random.choice(USER_AGENTS)
    context = browser.new_context(
        user_agent=ua,
        viewport={"width": random.choice([1280,1366,1440,1920]),
                  "height": random.choice([768,800,900,1080])},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
        window.chrome = {runtime: {}};
    """)
    return context

# JS: collect every link's href + visible text from the current page
DISCOVER_JS = """
() => {
  const out = [];
  document.querySelectorAll('a[href]').forEach(a => {
    const t = (a.textContent || '').replace(/\\s+/g,' ').trim();
    if (a.href && t && t.length < 40) out.push({href: a.href, text: t});
  });
  return out;
}
"""

# JS: find the "next page" link, if any
NEXT_JS = """
() => {
  const cand = [
    ...document.querySelectorAll('a[rel="next"]'),
    ...document.querySelectorAll('a.next, a.next-page, .pagination a, .pager a, .pages a')
  ];
  for (const a of cand) {
    const t = (a.textContent||'').trim().toLowerCase();
    if (a.rel === 'next' || t === 'next' || t === '>' || t === 'next page' || t.includes('next'))
      return a.href;
  }
  return null;
}
"""

def _norm(s):
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum())

def _discover_categories(page, wanted):
    """Read the site's nav links and map each wanted platform to its real URL.
    Returns an ordered dict {url: platform_label}."""
    try:
        links = page.evaluate(DISCOVER_JS)
    except Exception:
        links = []
    by_text = {}
    for l in links:
        key = _norm(l["text"])
        if key and key not in by_text:
            by_text[key] = l["href"]
    found = {}
    for label, variants in wanted:
        for v in variants:
            href = by_text.get(_norm(v))
            if href and href not in found:
                found[href] = label
                break
    return found

def scrape_lukiegames(sleep=2.0, on_progress=None):
    """Scrape LukieGames. Discovers category URLs from the nav, then paginates
    each by following the 'next' link (no guessed URLs).
    Calls on_progress(list_of_records) after each console so progress is saved."""
    import random
    print("  [lukiegames] scraping with stealth Playwright...")
    if not HAS_PLAYWRIGHT:
        print("    Playwright not installed, skipping"); return []
    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = _make_stealth_context(browser)
        page = context.new_page()
        try:
            page.goto("https://www.lukiegames.com/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print("    ! homepage load failed: %s" % e)

        categories = _discover_categories(page, LG_WANTED)
        print("    discovered %d categories from nav" % len(categories))
        for u, pl in list(categories.items())[:5]:
            print("      -> %s  (%s)" % (u, pl))
        if not categories:
            _dump_debug(page, "lukiegames-home")

        dumped = False
        for ci, (base_url, platform) in enumerate(categories.items(), 1):
            print("    [%d/%d] %s ..." % (ci, len(categories), platform))
            pg = 1
            throttled_pages = 0
            while pg <= 60:
                sep = "&" if "?" in base_url else "?"
                url = base_url if pg == 1 else "%s%spage=%d" % (base_url, sep, pg)
                ok, retries = False, 0
                while retries < 2:
                    try:
                        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        if resp and resp.status == 429:
                            retries += 1
                            print("      (throttled, waiting 20s %d/2)" % retries)
                            time.sleep(20); continue
                        if resp and resp.status >= 400:
                            break
                        ok = True; break
                    except Exception as e:
                        print("      ! %s p%d error: %s" % (platform, pg, e)); break
                if not ok:
                    throttled_pages += 1
                    if throttled_pages >= 2:
                        print("      (giving up on %s after repeated blocks)" % platform)
                        break
                    continue

                try:
                    page.wait_for_selector("article.ss__result, .ss__result--item", timeout=12000)
                except Exception:
                    pass
                time.sleep(random.uniform(0.6, 1.2))
                try:
                    products = page.evaluate(LUKIE_EXTRACT_JS)
                except Exception:
                    products = []
                if not dumped:
                    _dump_debug(page, "lukiegames"); dumped = True
                if not products: break
                new_count = 0
                for prod in products:
                    pid_key = prod["url"].rstrip("/").split("/")[-1].replace(".html","")
                    pid = "lukiegames-%s" % pid_key
                    if pid in seen: continue
                    seen[pid] = {"id":pid,"name":prod["name"],"store":"lukiegames",
                        "platform":platform,"price":round(prod["price"],2),"url":prod["url"]}
                    new_count += 1
                if new_count == 0: break
                if pg % 3 == 0:
                    print("      page %d (%d products so far)" % (pg, len(seen)))
                pg += 1
                time.sleep(random.uniform(0.4, 0.9))

            cat_count = sum(1 for r in seen.values() if r["platform"] == platform)
            if cat_count:
                print("    %s: %d products  [running total: %d]" % (platform, cat_count, len(seen)))
            # Save progress after every console so a hang/cancel never loses it
            if on_progress:
                try: on_progress(list(seen.values()))
                except Exception as e: print("      (progress save skipped: %s)" % e)
            time.sleep(random.uniform(0.4, 0.9))
        browser.close()
    print("    total: %d products" % len(seen))
    return list(seen.values())


# ================================================================ DKOLDIES (BigCommerce)
DK_WANTED = [
    ("Nintendo 64",         ["Nintendo 64"]),
    ("Nintendo NES",        ["Nintendo NES"]),
    ("Super Nintendo",      ["Super Nintendo"]),
    ("Nintendo Gamecube",   ["GameCube"]),
    ("Nintendo Wii",        ["Wii"]),
    ("Wii U",               ["Wii U"]),
    ("Nintendo Switch",     ["Nintendo Switch", "Switch"]),
    ("Game Boy Advance",    ["GameBoy Advance"]),
    ("Game Boy Color",      ["GameBoy Color"]),
    ("Game Boy",            ["GameBoy"]),
    ("Nintendo DS",         ["Nintendo DS", "DS"]),
    ("Nintendo 3DS",        ["Nintendo 3DS", "3DS"]),
    ("PlayStation 1",       ["PlayStation 1"]),
    ("PlayStation 2",       ["PlayStation 2"]),
    ("PlayStation 3",       ["PlayStation 3"]),
    ("PlayStation 4",       ["PlayStation 4"]),
    ("PlayStation 5",       ["PlayStation 5"]),
    ("PlayStation Portable",["PlayStation Portable", "PSP"]),
    ("PlayStation Vita",    ["PS Vita"]),
    ("Original Xbox",       ["Original Xbox"]),
    ("Xbox 360",            ["Xbox 360"]),
    ("Xbox One",            ["Xbox One"]),
    ("Sega Genesis",        ["Genesis"]),
    ("Sega Dreamcast",      ["Dreamcast"]),
    ("Sega Saturn",         ["Saturn"]),
    ("Sega Game Gear",      ["Game Gear"]),
    ("Atari",               ["Atari 2600", "Atari"]),
]

# DKOldies loads products from its own SearchSpring API. We call it from inside
# the page (same origin -> no CORS issue), reusing the site's get_cat_hierarchy().
DK_API_JS = r"""
(pageNum) => {
  return (async () => {
    let cat = [];
    try { if (typeof get_cat_hierarchy === 'function') cat = get_cat_hierarchy(); } catch (e) {}
    if (!cat || !cat.length) {
      cat = [...document.querySelectorAll('li.breadcrumb')]
        .map(li => (li.textContent || '').trim())
        .filter(t => t && t.toLowerCase() !== 'home');
    }
    let pageurl = window.location.href.split('?')[0].split('#')[0];
    if (pageNum > 1) pageurl += '?page=' + pageNum;
    const params = new URLSearchParams();
    params.set('pageurl', pageurl);
    (cat || []).forEach(c => params.append('data_cat_hirarchey[]', c));
    params.set('per_page', '48');
    let status = 0, html = '', err = '';
    try {
      const r = await fetch('https://inventory.dkoldies.com/admin/searchspring?' + params.toString(),
                            { headers: { 'Accept': 'application/json' }, credentials: 'omit' });
      status = r.status;
      const j = await r.json();
      html = j.productData || '';
    } catch (e) { err = String(e); }
    return { status, err, html, cat };
  })();
}
"""

# Extract products from the API's returned HTML (injected into a hidden container).
DK_EXTRACT_JS = r"""
(html) => {
  let box = document.getElementById('ss-api-extract');
  if (!box) { box = document.createElement('div'); box.id = 'ss-api-extract';
              box.style.display = 'none'; document.body.appendChild(box); }
  box.innerHTML = html;
  const out = [], seen = new Set();
  box.querySelectorAll('a[href]').forEach(a => {
    const href = a.href;
    if (!/dkoldies\.com\//.test(href)) return;
    if (/-games\/?($|\?)/.test(href)) return;          // skip category links
    let el = a, price = null, hops = 0;
    while (el && hops < 4) {
      const m = (el.textContent || '').match(/\$[\d,]+\.?\d*/);
      if (m) { price = parseFloat(m[0].replace(/[$,]/g, '')); break; }
      el = el.parentElement; hops++;
    }
    if (!price || !(price > 0)) return;
    const name = (a.textContent || '').trim();
    if (!name || name.length < 2) return;
    if (seen.has(href)) return;
    seen.add(href);
    out.push({ name, price, url: href });
  });
  return out;
}
"""

def scrape_dkoldies(sleep=2.0, on_progress=None):
    """Scrape DKOldies. Discovers category URLs from nav, paginates via ?page=N.
    Calls on_progress(list_of_records) after each console so progress is saved."""
    import random
    print("  [dkoldies] scraping with stealth Playwright...")
    if not HAS_PLAYWRIGHT:
        print("    Playwright not installed, skipping"); return []
    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = _make_stealth_context(browser)
        page = context.new_page()
        try:
            page.goto("https://www.dkoldies.com/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print("    ! homepage load failed: %s" % e)

        categories = _discover_categories(page, DK_WANTED)
        print("    discovered %d category hubs from nav" % len(categories))
        if not categories:
            _dump_debug(page, "dkoldies-home")

        # The nav links point at category HUB pages (e.g. /nintendo-64/) which only
        # show subcategory tiles. The real product lists are the "-games" pages
        # (e.g. /n64-games/). From each hub we find its games-listing link.
        GAMES_LINK_JS = """
        () => {
          const bad = /rare-games|sell-your-games|sell-games/;
          const a = [...document.querySelectorAll('a[href]')].find(a =>
            /dkoldies\\.com\\/[a-z0-9-]+-games\\/?$/.test(a.href) && !bad.test(a.href));
          return a ? a.href : null;
        }
        """

        dumped = False
        for ci, (hub_url, platform) in enumerate(categories.items(), 1):
            print("    [%d/%d] %s ..." % (ci, len(categories), platform))
            # Step 1: open the hub, locate its games-listing page
            try:
                page.goto(hub_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(0.6, 1.2))
                games_url = page.evaluate(GAMES_LINK_JS)
            except Exception as e:
                print("      ! %s hub error: %s" % (platform, e)); games_url = None
            if not games_url:
                games_url = hub_url

            # Step 2: load the games page once (gives us breadcrumbs + the site's
            # own get_cat_hierarchy()), then call DKOldies' SearchSpring API
            # directly for each page. Products come back as HTML in result.productData.
            try:
                page.goto(games_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(0.8, 1.4))
            except Exception as e:
                print("      ! %s games page error: %s" % (platform, e)); 
                if on_progress:
                    try: on_progress(list(seen.values()))
                    except Exception: pass
                continue

            pg = 1
            while pg <= 60:
                try:
                    res = page.evaluate(DK_API_JS, pg)
                except Exception as e:
                    print("      ! %s api error p%d: %s" % (platform, pg, e)); break

                html = (res or {}).get("html", "")
                if pg == 1 and not dumped:
                    # Save the raw API product HTML so we can verify the markup
                    try:
                        root = os.path.dirname(HERE)
                        with open(os.path.join(root, "debug-dkoldies-api.html"), "w", encoding="utf-8") as f:
                            f.write("<!-- status=%s cat=%s -->\n%s" % (res.get("status"), res.get("cat"), html))
                        print("      [debug] API status=%s, productData=%d chars -> debug-dkoldies-api.html"
                              % (res.get("status"), len(html)))
                    except Exception as e:
                        print("      [debug] could not save api html: %s" % e)
                    dumped = True

                if not html:
                    break
                # Inject the returned product HTML and extract from it
                try:
                    products = page.evaluate(DK_EXTRACT_JS, html)
                except Exception:
                    products = []
                if not products:
                    break

                new_count = 0
                for prod in products:
                    pid_key = prod["url"].rstrip("/").rsplit("/", 1)[-1]
                    pid = "dkoldies-%s" % pid_key
                    if pid in seen: continue
                    seen[pid] = {"id":pid,"name":prod["name"],"store":"dkoldies",
                        "platform":platform,"price":round(prod["price"],2),"url":prod["url"]}
                    new_count += 1
                if new_count == 0:
                    break
                if pg % 3 == 0:
                    print("      page %d (%d products so far)" % (pg, len(seen)))
                pg += 1
                time.sleep(random.uniform(0.4, 0.9))

            cat_count = sum(1 for r in seen.values() if r["platform"] == platform)
            if cat_count:
                print("    %s: %d products  [running total: %d]" % (platform, cat_count, len(seen)))
            if on_progress:
                try: on_progress(list(seen.values()))
                except Exception as e: print("      (progress save skipped: %s)" % e)
            time.sleep(random.uniform(0.4, 0.9))
        browser.close()
    print("    total: %d products" % len(seen))
    return list(seen.values())

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

def load_existing_records(path):
    """Read the current window.RETRO_DATA out of an existing retro-data.js so we
    can preserve stores we are NOT scraping in this run (merge, don't clobber)."""
    if not os.path.exists(path):
        return []
    try:
        txt = open(path, encoding="utf-8").read()
        m = re.search(r"window\.RETRO_DATA\s*=\s*(\[.*?\]);", txt, re.S)
        if not m:
            return []
        return json.loads(m.group(1))
    except Exception:
        return []

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
    print("=== Retro Price Watch scraper %s ===" % SCRAPER_VERSION)
    if scrapers is None:
        scrapers = [scrape_retrofam, scrape_retrovgames, scrape_lukiegames, scrape_dkoldies]
    history = load_history(history_path)

    def save_snapshot(records):
        """Merge the given records with existing data for OTHER stores, then write
        to disk immediately. Safe to call repeatedly mid-run, so progress from each
        console is persisted and a hang or cancel never loses completed work."""
        recs = apply_prev(list(records), history)
        fresh = set(r["store"] for r in recs)
        kept = [r for r in load_existing_records(data_path) if r["store"] not in fresh]
        merged = kept + recs
        merged.sort(key=lambda r: (r["store"], r["platform"], r["name"].lower()))
        write_data_js(merged, data_path)
        save_history(merged, history_path)
        return merged

    all_records = []
    for scraper in scrapers:
        try:
            params = inspect.signature(scraper).parameters
            if "on_progress" in params:
                records = scraper(sleep=sleep, on_progress=save_snapshot)
            else:
                records = scraper(sleep=sleep)
            all_records.extend(records)
            print("  -> %d from %s" % (len(records), scraper.__name__))
            # Persist after each store so a later store can't lose an earlier one
            save_snapshot(all_records)
        except Exception as e:
            print("  !! %s FAILED: %s" % (scraper.__name__, e))
            import traceback; traceback.print_exc()
            # Still save whatever we have so far
            if all_records:
                save_snapshot(all_records)

    merged = save_snapshot(all_records)
    drops = sum(1 for r in merged if r["prev"] and r["price"] < r["prev"])
    new = sum(1 for r in merged if r["prev"] is None)
    if merged:
        kept_stores = sorted(set(r["store"] for r in merged))
        print("  (final data covers: %s)" % ", ".join(kept_stores))
    print("\nTotal: %d products | %d drops | %d new | data -> %s"
          % (len(merged), drops, new, data_path))
    return merged


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
    if "--self-test" in sys.argv:
        self_test()
    else:
        all_scrapers = {
            "retrofam":    scrape_retrofam,
            "retrovgames": scrape_retrovgames,
            "lukiegames":  scrape_lukiegames,
            "dkoldies":    scrape_dkoldies,
        }
        if "--stores" in sys.argv:
            idx = sys.argv.index("--stores")
            names = sys.argv[idx+1:]
            chosen = [all_scrapers[n] for n in names if n in all_scrapers]
        else:
            chosen = list(all_scrapers.values())
        run(scrapers=chosen)
