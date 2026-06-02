"""
╔══════════════════════════════════════════════════════════════╗
║          RALPH LAUREN VINTED SNIPER BOT v1.1                ║
║   Targets: Polo shirts, Rugby tops, Striped vintage,        ║
║            USA branded, Chief Keef style polos              ║
║   Max Price: £16  |  New listings only  |  Men's only       ║
║   Sizes: Age 14+ only  |  Max size: L  |  No women's        ║
╚══════════════════════════════════════════════════════════════╝

HOW TO USE:
  1. pip install requests colorama
  2. Set your Discord webhook URL in DISCORD_WEBHOOK below
  3. Run: python bot_ralph_lauren.py

PROFIT LOGIC (realistic UK resale margins):
  - Striped vintage polo (bought £8-16)  → resell eBay/Depop £35-60  → profit £19-44
  - Rugby top (bought £10-16)            → resell eBay/Depop £40-75  → profit £24-59
  - USA branded RL (bought £8-16)        → resell eBay/Depop £30-55  → profit £14-39
  - Standard polo (bought £5-16)         → resell Vinted/Depop £22-35 → profit £6-19
  After fees (~13% platform + postage ~£3.50): subtract ~£5-8 from above.
"""

import os
import requests
import time
import json
import hashlib
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# ─────────────────────────────────────────────
#  CONFIG — edit these before running
# ─────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1511400876684873829/_mF8_LJxZrP4urAjNxVNAheMDQHsH35V_uUKp9v8iM0v3E5aNPJ0ASOYbFOw0cwhRlae")
POLL_INTERVAL   = 12          # seconds between scans (don't go below 8)
MAX_PRICE_GBP   = 16.00
DOMAIN          = "www.vinted.co.uk"

# ─────────────────────────────────────────────
#  SEARCH QUERIES  (brand_ids=88 = Ralph Lauren on vinted.co.uk)
#  Each entry: (label, search_text, priority_score_hint)
# ─────────────────────────────────────────────
SEARCHES = [
    # (label,               search_text,                           priority)
    ("🎽 STRIPED POLO",    "ralph lauren striped polo vintage",    "HIGH"),
    ("🏉 RUGBY TOP",       "ralph lauren rugby top",               "HIGH"),
    ("🇺🇸 USA BRANDED",   "ralph lauren USA polo",                "HIGH"),
    ("🎤 CHIEF KEEF POLO", "ralph lauren polo shirt oversized",    "HIGH"),
    ("👔 GENERAL POLO",    "ralph lauren polo shirt",              "MED"),
    ("🧥 RL GENERAL",      "ralph lauren",                        "MED"),
]

# ─────────────────────────────────────────────
#  BLOCKED SIZES & DEMOGRAPHICS
# ─────────────────────────────────────────────

# Infant / children size keywords — blocks everything under age 14
BLOCKED_SIZE_KEYWORDS = [
    # Babies / toddlers
    "baby", "infant", "toddler", "newborn",
    "0-3", "3-6", "6-9", "6-12", "12-18", "18-24", "9-12",
    "0m", "3m", "6m", "9m", "12m", "18m",
    "5t", "4t", "3t", "2t", "1t",
    # Ages explicitly under 14
    "age 1", "age 2", "age 3", "age 4", "age 5",
    "age 6", "age 7", "age 8", "age 9", "age 10",
    "age 11", "age 12", "age 13",
    "1 year", "2 year", "3 year", "4 year", "5 year",
    "6 year", "7 year", "8 year", "9 year", "10 year",
    "11 year", "12 year", "13 year",
    "1-2", "2-3", "3-4", "4-5", "5-6", "6-7", "7-8",
    "8-9", "9-10", "10-11", "11-12", "12-13", "13-14",
    # General kids keywords
    "kids", "children", "child", "junior",
]

# Sizes XL and above — all blocked
BLOCKED_SIZE_LARGE = [
    " xl", "/xl", "-xl", "_xl",   # XL with boundary so "xml" isn't caught
    "xxl", "xxxl", "xxxxl",
    "2xl", "3xl", "4xl", "5xl",
    "1x", "2x", "3x", "4x", "5x",
    "extra large", "extra-large",
    "plus size", "plus-size",
]

# Women's department / listing keywords — all blocked
BLOCKED_WOMENS_KEYWORDS = [
    "women's", "womens", "womenswear",
    "ladies", "ladieswear",
    "for her", "for women",
]

# Title keywords that must appear (brand check)
REQUIRED_BRAND_KEYWORDS = [
    "ralph lauren", "polo ralph", "rl polo", "polo rl",
]

# High-value target keywords — bumps profit score
HIGH_VALUE_KEYWORDS = [
    "striped", "stripe", "rugby", "usa", "vintage", "1990", "1980", "1992",
    "1995", "big pony", "cable knit", "made in usa", "country",
    "chief keef", "oversized", "double rl", "rrl", "pwing",
]

# ─────────────────────────────────────────────
#  PROFIT ESTIMATOR
# ─────────────────────────────────────────────
RESELL_TABLE = {
    "rugby":    (40, 75),
    "striped":  (35, 60),
    "stripe":   (35, 60),
    "usa":      (30, 55),
    "vintage":  (28, 50),
    "double rl":(50, 90),
    "rrl":      (50, 90),
    "big pony": (25, 45),
    "cable":    (30, 55),
    "oversized":(22, 40),
    "default":  (18, 32),
}
VINTED_FEE_RATE = 0.05    # seller fee ~5%
POSTAGE_COST    = 3.50
EBAY_FEE_RATE   = 0.1269  # eBay ~12.69% final value fee


def get_price(item):
    price_data = item.get("price", 0)

    if isinstance(price_data, (int, float)):
        return float(price_data)

    if isinstance(price_data, str):
        try:
            return float(price_data)
        except ValueError:
            return 0.0

    if isinstance(price_data, dict):
        for key in ("amount", "value", "numeric"):
            if key in price_data:
                try:
                    return float(price_data[key])
                except (TypeError, ValueError):
                    pass

    return 0.0


def estimate_profit(title: str, buy_price: float) -> dict:
    title_lower = title.lower()
    low, high = RESELL_TABLE["default"]
    for kw, (l, h) in RESELL_TABLE.items():
        if kw != "default" and kw in title_lower:
            if h > high:
                low, high = l, h
    # net after eBay fees + postage
    net_low  = round(low  * (1 - EBAY_FEE_RATE) - POSTAGE_COST - buy_price, 2)
    net_high = round(high * (1 - EBAY_FEE_RATE) - POSTAGE_COST - buy_price, 2)
    roi_low  = round((net_low / buy_price) * 100) if buy_price > 0 else 0
    roi_high = round((net_high / buy_price) * 100) if buy_price > 0 else 0
    rating = "🔥 FIRE" if net_low >= 20 else "✅ SOLID" if net_low >= 10 else "⚠️ TIGHT" if net_low >= 4 else "❌ SKIP"
    return {
        "resell_low": low, "resell_high": high,
        "profit_low": net_low, "profit_high": net_high,
        "roi_low": roi_low, "roi_high": roi_high,
        "rating": rating,
    }


# ─────────────────────────────────────────────
#  VINTED API FETCH
# ─────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": f"https://{DOMAIN}/",
    "Origin":  f"https://{DOMAIN}",
}

session = requests.Session()
session.headers.update(HEADERS)
seen_ids: set = set()


def fetch_listings(search_text: str, max_price: float) -> list:
    url = (
        f"https://{DOMAIN}/api/v2/catalog/items"
        f"?search_text={requests.utils.quote(search_text)}"
        f"&price_to={max_price}"
        f"&currency=GBP"
        f"&order=newest_first"
        f"&per_page=30"
        f"&page=1"
    )
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("items", [])
        elif r.status_code == 401:
            print(f"{Fore.YELLOW}[AUTH] 401 received, re-fetching session cookies...")
            _refresh_session()
    except Exception as e:
        print(f"{Fore.RED}[ERROR] fetch_listings: {e}")
    return []


def _refresh_session():
    """Visit homepage to grab fresh cookies (access_token_web etc.)"""
    try:
        session.get(f"https://{DOMAIN}/", timeout=10)
    except Exception:
        pass


# ─────────────────────────────────────────────
#  FILTERS
# ─────────────────────────────────────────────
def is_infant_or_underage(item: dict) -> bool:
    """Block anything sized for under-14s."""
    title = (item.get("title") or "").lower()
    desc  = (item.get("description") or "").lower()
    size  = (item.get("size_title") or "").lower()
    text  = title + " " + desc + " " + size
    return any(kw in text for kw in BLOCKED_SIZE_KEYWORDS)


def is_oversized(item: dict) -> bool:
    """Block XL and above."""
    size  = (item.get("size_title") or "").lower()
    title = (item.get("title") or "").lower()
    text  = " " + size + " " + title + " "   # padded so word-boundary checks work
    return any(kw in text for kw in BLOCKED_SIZE_LARGE)


def is_womens(item: dict) -> bool:
    """Block women's / ladies listings."""
    title      = (item.get("title") or "").lower()
    desc       = (item.get("description") or "").lower()
    dept       = (item.get("department") or "").lower()          # API field e.g. "Women"
    dept_name  = (item.get("department_name") or "").lower()
    unisex     = (item.get("unisex") or False)
    text       = title + " " + desc + " " + dept + " " + dept_name

    # If Vinted marks it explicitly as women's department, reject
    if "women" in dept or "female" in dept:
        return True

    # Keyword scan across title + description
    return any(kw in text for kw in BLOCKED_WOMENS_KEYWORDS)


def is_ralph_lauren(item: dict) -> bool:
    title = (item.get("title") or "").lower()
    brand = (item.get("brand_title") or "").lower()
    return (
        any(kw in brand for kw in REQUIRED_BRAND_KEYWORDS) or
        any(kw in title for kw in REQUIRED_BRAND_KEYWORDS)
    )


def score_item(item: dict) -> int:
    title = (item.get("title") or "").lower()
    score = 0
    for kw in HIGH_VALUE_KEYWORDS:
        if kw in title:
            score += 1
    return score


# ─────────────────────────────────────────────
#  DISCORD NOTIFICATION
# ─────────────────────────────────────────────
def send_discord(item: dict, label: str, profit: dict):
    price = get_price(item)
    title = item.get("title", "Unknown")
    url   = item.get("url") or f"https://{DOMAIN}/items/{item.get('id')}"
    photo = ""
    if item.get("photos"):
        photo = item["photos"][0].get("url") or item["photos"][0].get("full_size_url", "")

    color_map = {"🔥 FIRE": 0xFF4500, "✅ SOLID": 0x00C851, "⚠️ TIGHT": 0xFFBB33, "❌ SKIP": 0xCC0000}
    embed_color = color_map.get(profit["rating"], 0x888888)

    embed = {
        "title": f"{label}  |  £{price:.2f}",
        "description": f"**{title}**\n[🔗 View on Vinted]({url})",
        "color": embed_color,
        "fields": [
            {"name": "💰 Buy Price",     "value": f"£{price:.2f}",                                          "inline": True},
            {"name": "📦 Resell Range",  "value": f"£{profit['resell_low']}–£{profit['resell_high']} (eBay/Depop)", "inline": True},
            {"name": "📈 Net Profit",    "value": f"£{profit['profit_low']}–£{profit['profit_high']}",       "inline": True},
            {"name": "🎯 ROI",           "value": f"{profit['roi_low']}%–{profit['roi_high']}%",             "inline": True},
            {"name": "⚡ Verdict",       "value": profit["rating"],                                         "inline": True},
            {"name": "🏷️ Brand Check",   "value": "✅ Ralph Lauren confirmed",                              "inline": True},
        ],
        "thumbnail": {"url": photo} if photo else {},
        "footer": {"text": f"Ralph Lauren Bot v1.1 • {datetime.now().strftime('%H:%M:%S')}"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    payload = {
        "username":   "RL Sniper 🎽",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [embed],
    }

    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        if r.status_code not in (200, 204):
            print(f"{Fore.YELLOW}[DISCORD] Non-200: {r.status_code}")
    except Exception as e:
        print(f"{Fore.RED}[DISCORD ERROR] {e}")


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
def run():
    print(f"\n{Fore.CYAN}{'═'*60}")
    print(f"{Fore.CYAN}  🎽  RALPH LAUREN VINTED SNIPER v1.1 — STARTED")
    print(f"{Fore.CYAN}  Max Price: £{MAX_PRICE_GBP}  |  Interval: {POLL_INTERVAL}s")
    print(f"{Fore.CYAN}  Filters: Men's only | Age 14+ | Max size L")
    print(f"{Fore.CYAN}{'═'*60}\n")

    _refresh_session()
    cycle = 0

    while True:
        cycle += 1
        found_this_cycle = 0
        print(f"{Fore.WHITE}[{datetime.now().strftime('%H:%M:%S')}] Cycle #{cycle} scanning {len(SEARCHES)} queries...")

        for label, search_text, priority in SEARCHES:
            items = fetch_listings(search_text, MAX_PRICE_GBP)

            for item in items:
                item_id = str(item.get("id", ""))
                if not item_id or item_id in seen_ids:
                    continue

                seen_ids.add(item_id)

                # ── FILTERS ──
                if is_infant_or_underage(item):
                    continue
                if is_oversized(item):
                    continue
                if is_womens(item):
                    continue
                if not is_ralph_lauren(item):
                    continue

                price = get_price(item)
                if price <= 0 or price > MAX_PRICE_GBP:
                    continue

                # ── SCORE & PROFIT ──
                score  = score_item(item)
                profit = estimate_profit(item.get("title", ""), price)

                found_this_cycle += 1
                verdict_color = Fore.RED if "FIRE" in profit["rating"] else Fore.GREEN if "SOLID" in profit["rating"] else Fore.YELLOW
                print(
                    f"  {verdict_color}{profit['rating']}  {label}  "
                    f"£{price:.2f}  →  profit £{profit['profit_low']}-£{profit['profit_high']}  "
                    f"|  {item.get('title','')[:50]}"
                )

                if DISCORD_WEBHOOK_URL:
                    send_discord(item, label, profit)

            time.sleep(1.5)  # be polite between queries

        if found_this_cycle == 0:
            print(f"  {Fore.WHITE}No new items this cycle.")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
