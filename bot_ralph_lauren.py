"""
╔══════════════════════════════════════════════════════════════════╗
║          RALPH LAUREN VINTED SNIPER BOT v2.0                   ║
║   Targets: Polo shirts, Rugby tops, Striped vintage,           ║
║            USA branded, Chief Keef city polos                  ║
║   Max Price: £16  |  New listings only  |  Men's only          ║
║   Sizes: Age 14+ only  |  Max size: L  |  No women's           ║
║   Blocked: Accessories, hats, button-ups                       ║
║                                                                 ║
║   NEW: TensorFlow MobileNetV2 visual confidence scoring         ║
║        Visual score added to every Discord embed               ║
╚══════════════════════════════════════════════════════════════════╝

INSTALL DEPENDENCIES:
  pip install requests colorama tensorflow pillow numpy

VERDICT TIERS:
  🔵 BLUE  — Best snipe. Highly desirable, underpriced, must-buy.
  🟢 GREEN — Strong buy. Good style, fair price, solid resale.
  🟡 SOLID — Decent flip. Standard good RL, worth buying.
  🟠 TIGHT — Marginal. Low resale ceiling or weak signals
  ❌ SKIP  — Not worth it. Plain/common, no collector demand.

CATEGORY SYSTEM:
  A — Country & City Series     → BLUE default under £20
  B — Team Racing / RL Racing   → BLUE default under £20
  B2— Big Pony Numbered         → GREEN–BLUE
  C — Diagonal Sash / Colourblock → GREEN
  D — Standard Big Pony Plain   → SOLID
  E — Standard Ralph Lauren Polo → SOLID–TIGHT

  CRITICAL: Never SKIP a confirmed Ralph Lauren polo on signal score alone.
"""

import os
import io
import requests
import time
import numpy as np
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# ── TensorFlow lazy import (graceful fallback if not installed) ──
try:
    import tensorflow as tf
    from tensorflow.keras.applications import MobileNetV2
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
    from tensorflow.keras.preprocessing import image as tf_image
    from PIL import Image

    _model = None

    def _get_model():
        global _model
        if _model is None:
            print(f"{Fore.CYAN}[TF] Loading MobileNetV2 model (first run only)...")
            _model = MobileNetV2(weights="imagenet")
            print(f"{Fore.GREEN}[TF] Model loaded.")
        return _model

    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print(f"{Fore.YELLOW}[WARNING] TensorFlow or Pillow not installed. Visual scoring disabled.")
    print(f"{Fore.YELLOW}          Run: pip install tensorflow pillow numpy")


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1511400876684873829/_mF8_LJxZrP4urAjNxVNAheMDQHsH35V_uUKp9v8iM0v3E5aNPJ0ASOYbFOw0cwhRlae"
)
POLL_INTERVAL   = 12
MAX_PRICE_GBP   = 16.00
DOMAIN          = "www.vinted.co.uk"

# ─────────────────────────────────────────────
#  SEARCH QUERIES
# ─────────────────────────────────────────────
SEARCHES = [
    ("🎽 STRIPED POLO",    "ralph lauren striped polo vintage",    "HIGH"),
    ("🏉 RUGBY TOP",       "ralph lauren rugby top",               "HIGH"),
    ("🇺🇸 USA BRANDED",   "ralph lauren USA polo",                "HIGH"),
    ("🎤 CITY POLO",       "ralph lauren polo shirt oversized",    "HIGH"),
    ("👔 GENERAL POLO",    "ralph lauren polo shirt",              "MED"),
    ("🧥 RL GENERAL",      "ralph lauren",                        "MED"),
]

# ─────────────────────────────────────────────
#  BLOCKED KEYWORDS
# ─────────────────────────────────────────────
BLOCKED_SIZE_KEYWORDS = [
    "baby", "infant", "toddler", "newborn",
    "0-3", "3-6", "6-9", "6-12", "12-18", "18-24", "9-12",
    "0m", "3m", "6m", "9m", "12m", "18m",
    "5t", "4t", "3t", "2t", "1t",
    "age 1", "age 2", "age 3", "age 4", "age 5",
    "age 6", "age 7", "age 8", "age 9", "age 10",
    "age 11", "age 12", "age 13",
    "1 year", "2 year", "3 year", "4 year", "5 year",
    "6 year", "7 year", "8 year", "9 year", "10 year",
    "11 year", "12 year", "13 year",
    "1-2", "2-3", "3-4", "4-5", "5-6", "6-7", "7-8",
    "8-9", "9-10", "10-11", "11-12", "12-13", "13-14",
    "kids", "children", "child", "junior",
]

BLOCKED_SIZE_LARGE = [
    " xl", "/xl", "-xl", "_xl",
    "xxl", "xxxl", "xxxxl",
    "2xl", "3xl", "4xl", "5xl",
    "1x", "2x", "3x", "4x", "5x",
    "extra large", "extra-large",
    "plus size", "plus-size",
]

BLOCKED_WOMENS_KEYWORDS = [
    "women's", "womens", "womenswear",
    "ladies", "ladieswear",
    "for her", "for women",
]

BLOCKED_ACCESSORY_KEYWORDS = [
    "hat", "cap", "caps", "beanie", "snapback", "fitted cap",
    "baseball cap", "trucker cap", "bucket hat", "flat cap",
    "dad hat", "visor", "beret", "fedora",
    "scarf", "scarves", "snood", "bandana", "neckerchief",
    "bag", "tote", "backpack", "handbag", "wallet", "purse",
    "clutch", "satchel", "holdall", "duffel", "fanny pack",
    "belt", "keyring", "keychain", "lanyard", "pin badge",
    "shoes", "trainers", "boots", "sneakers", "loafers",
    "sandals", "slippers", "socks",
    "watch", "bracelet", "necklace", "ring", "earrings",
    "cufflinks", "tie clip",
    "sunglasses", "glasses", "umbrella", "gloves",
]

BUTTON_UP_KEYWORDS = [
    "button up", "button-up", "button down", "button-down",
    "dress shirt", "oxford shirt", "popover shirt",
    "flannel shirt", "western shirt", "chambray",
]

REQUIRED_BRAND_KEYWORDS = [
    "ralph lauren", "polo ralph", "rl polo", "polo rl",
]

# ─────────────────────────────────────────────
#  CATEGORY DETECTION
#  These map to the tier system. Checked in priority order.
# ─────────────────────────────────────────────

# Category A: Country/City Series
COUNTRY_CITY_KEYWORDS = [
    "uae", "great britain", "madrid", "amsterdam", "italia",
    "united states", "france", "japan", "china", "australia",
    "germany", "brazil", "new york", "chicago", "london",
    "paris", "dubai", "barcelona", "milan", "rome", "sydney",
    "berlin", "moscow", "atlanta", "boston", "shanghai",
    "tokyo", "toronto", "mexico", "portugal", "sweden",
    "polo cup", "polo challenge",
]

# Category B: Racing Series
RACING_KEYWORDS = [
    "team racing", "rl racing", "ralph lauren racing", "racing polo",
    "racing badge", "racing crest",
]

# Category B2: Big Pony Numbered
BIG_PONY_NUMBERED_KEYWORDS = [
    "big pony", "#1", "#2", "#3", "#4",
    "number 1", "number 2", "number 3", "number 4",
    "no.1", "no.2", "no.3", "no.4",
]

# Category C: Diagonal Sash / Colourblock
SASH_COLOURBLOCK_KEYWORDS = [
    "sash", "diagonal", "colour block", "color block",
    "colourblock", "colorblock", "multi colour", "multi-colour",
    "multicolour", "panel", "colour-block",
]

# Category D: Plain Big Pony (no number, no sash)
PLAIN_BIG_PONY_KEYWORDS = [
    "big pony",
]

# Fit signals (minor boost)
FIT_KEYWORDS = ["slim fit", "custom fit"]

# ─────────────────────────────────────────────
#  SIGNAL SCORING (v2)
# ─────────────────────────────────────────────
STEAL_SIGNALS = {
    # Country/city — +5
    "uae": 5, "great britain": 5, "madrid": 5, "amsterdam": 5,
    "italia": 5, "united states": 5, "france": 5, "japan": 5,
    "china": 5, "australia": 5, "germany": 5, "brazil": 5,
    "new york": 5, "chicago": 5, "london": 5, "paris": 5,
    "dubai": 5, "barcelona": 5, "milan": 5, "rome": 5,
    "sydney": 5, "berlin": 5, "moscow": 5, "atlanta": 5,
    "boston": 5, "shanghai": 5, "tokyo": 5,
    "polo cup": 5, "polo challenge": 5,
    # Racing — +5
    "team racing": 5, "rl racing": 5, "ralph lauren racing": 5,
    # Big Pony — +3
    "big pony": 3,
    # Sash/colourblock — +3
    "sash": 3, "diagonal": 3, "colour block": 3, "color block": 3,
    "colourblock": 3, "colorblock": 3,
    # Numbered — +2
    "#1": 2, "#2": 2, "#3": 2, "#4": 2,
    "number 1": 2, "number 2": 2, "number 3": 2, "number 4": 2,
    # Mesh — +2
    "mesh": 2,
    # Fit — +1
    "slim fit": 1, "custom fit": 1,
    # Supporting signals — kept from v1
    "crest": 2, "badge": 2, "embroidered": 2, "embroidery": 2,
    "striped": 2, "stripe": 2,
    "multicolour": 2, "multi colour": 2, "multi-colour": 2,
    "panel": 2, "flag": 2,
    "double rl": 2, "rrl": 2,
    "rugby": 1, "vintage": 1, "usa": 1,
    "cable knit": 1, "made in usa": 1, "oversized": 1,
    "limited": 1, "rare": 1,
}

# ─────────────────────────────────────────────
#  RESELL TABLE
# ─────────────────────────────────────────────
RESELL_TABLE = {
    "cat_a_b":      (55, 90),   # Country/City or Racing
    "cat_b2":       (40, 75),   # Big Pony Numbered
    "cat_c":        (35, 60),   # Sash / Colourblock
    "cat_d":        (25, 45),   # Plain Big Pony
    "cat_e":        (18, 32),   # Standard RL
    "rugby":        (40, 75),
    "double rl":    (50, 90),
    "rrl":          (50, 90),
    "cable":        (30, 55),
    "button_up":    (12, 22),
    "default":      (18, 32),
}

POSTAGE_COST  = 3.50
EBAY_FEE_RATE = 0.1269

# ─────────────────────────────────────────────
#  TF VISUAL SCORING
#  MobileNetV2 classifies the listing image.
#  We look for ImageNet classes related to clothing quality/style
#  and map them to a 0–100 confidence score.
# ─────────────────────────────────────────────

# ImageNet class groups we consider "clothing-relevant" (MobileNetV2 labels)
CLOTHING_POSITIVE_CLASSES = {
    # Polo/jersey adjacent
    "jersey",         # sports jersey
    "sweatshirt",
    "pullover",
    "cardigan",
    "suit",
    "military_uniform",
    "abaya",           # fabric/clothing signal
    # Quality/texture signals
    "wool",
    "velvet",
    # Pattern signals
    "stripe",
    "Band_Aid",        # colour contrast (sometimes fires on sash patterns)
    "handkerchief",    # colourful fabric
}

CLOTHING_NEGATIVE_CLASSES = {
    "brassiere", "bikini", "swimwear", "miniskirt",
    "jean", "jeans", "denim",          # not polo territory
    "sandal", "shoe", "boot",          # accessories
    "cap", "hat",
}


def assess_image_with_tf(image_url: str) -> dict:
    """
    Download the listing image, run MobileNetV2, and return a visual confidence dict.
    Always returns a result even on failure (score = -1 means unavailable).
    """
    if not TF_AVAILABLE:
        return {"score": -1, "label": "TF unavailable", "top_classes": []}

    try:
        resp = requests.get(image_url, timeout=8)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img = img.resize((224, 224))

        x = tf_image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)

        model = _get_model()
        preds = model.predict(x, verbose=0)
        decoded = decode_predictions(preds, top=5)[0]
        # decoded = list of (imagenet_id, class_name, confidence)

        top_classes = [(cls, round(float(conf) * 100, 1)) for _, cls, conf in decoded]

        # Score: sum positive class confidences, subtract negatives
        score = 0.0
        for _, cls, conf in decoded:
            if cls in CLOTHING_POSITIVE_CLASSES:
                score += conf * 100
            elif cls in CLOTHING_NEGATIVE_CLASSES:
                score -= conf * 50

        # Also check if top-1 class is clothing-related at all
        top1_class = decoded[0][1]
        top1_conf  = decoded[0][2]

        # Presence of fabric/pattern class in top-3 = boost
        top3_classes = {cls for _, cls, _ in decoded[:3]}
        if top3_classes & CLOTHING_POSITIVE_CLASSES:
            score += 15

        # Clamp to 0–100
        score = max(0.0, min(100.0, score))
        score = round(score, 1)

        # Human-readable label
        if score >= 60:
            label = "🟢 Visually strong"
        elif score >= 35:
            label = "🟡 Visually moderate"
        elif score >= 10:
            label = "🟠 Visually weak"
        else:
            label = "❓ Uncertain (no clothing class detected)"

        return {
            "score": score,
            "label": label,
            "top_classes": top_classes[:3],
        }

    except Exception as e:
        return {"score": -1, "label": f"Error: {e}", "top_classes": []}


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def get_price(item: dict) -> float:
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


def text_of(item: dict) -> str:
    return " ".join([
        item.get("title", ""),
        item.get("description", ""),
    ]).lower()


def score_signals(title: str) -> tuple:
    title_lower = title.lower()
    matched = []
    total = 0
    for signal, pts in STEAL_SIGNALS.items():
        if signal in title_lower:
            matched.append(f"{signal}(+{pts})")
            total += pts
    return total, matched


def detect_category(text: str) -> str:
    """
    Returns 'A', 'B', 'B2', 'C', 'D', 'E' based on keyword presence.
    Priority order: A > B > B2 > C > D > E
    """
    if any(kw in text for kw in COUNTRY_CITY_KEYWORDS):
        return "A"
    if any(kw in text for kw in RACING_KEYWORDS):
        return "B"
    if any(kw in text for kw in BIG_PONY_NUMBERED_KEYWORDS):
        return "B2"
    if any(kw in text for kw in SASH_COLOURBLOCK_KEYWORDS):
        return "C"
    if any(kw in text for kw in PLAIN_BIG_PONY_KEYWORDS):
        return "D"
    return "E"


def is_button_up(title: str) -> bool:
    return any(kw in title.lower() for kw in BUTTON_UP_KEYWORDS)


CATEGORY_LABELS = {
    "A":  "🌍 Country/City Series",
    "B":  "🏎️ RL Racing Series",
    "B2": "🐴 Big Pony Numbered",
    "C":  "🔷 Diagonal Sash/Colourblock",
    "D":  "🐴 Plain Big Pony",
    "E":  "👕 Standard RL Polo",
}

# ─────────────────────────────────────────────
#  VERDICT ENGINE (v2)
# ─────────────────────────────────────────────
def estimate_profit(item: dict) -> dict:
    title    = item.get("title", "")
    full_txt = text_of(item)
    price    = get_price(item)

    signal_score, matched_signals = score_signals(title)
    category  = detect_category(full_txt)
    btn_up    = is_button_up(title)

    # ── Pick resell bracket ──
    if btn_up:
        resell_key = "button_up"
    elif category in ("A", "B"):
        resell_key = "cat_a_b"
    elif category == "B2":
        resell_key = "cat_b2"
    elif category == "C":
        resell_key = "cat_c"
    elif category == "D":
        resell_key = "cat_d"
    elif "rugby" in full_txt:
        resell_key = "rugby"
    elif "double rl" in full_txt or "rrl" in full_txt:
        resell_key = "double rl" if "double rl" in full_txt else "rrl"
    elif "cable" in full_txt:
        resell_key = "cable"
    else:
        resell_key = "cat_e"

    low, high = RESELL_TABLE[resell_key]
    net_low  = round(low  * (1 - EBAY_FEE_RATE) - POSTAGE_COST - price, 2)
    net_high = round(high * (1 - EBAY_FEE_RATE) - POSTAGE_COST - price, 2)
    roi_low  = round((net_low  / price) * 100) if price > 0 else 0
    roi_high = round((net_high / price) * 100) if price > 0 else 0

    # ── NEW VERDICT LOGIC — priority order ──
    if btn_up:
        rating = "🟠 TIGHT"

    # Category A or B
    elif category in ("A", "B"):
        if price <= 20:
            rating = "🔵 BLUE"
        elif price <= 30:
            rating = "🟢 GREEN"
        else:
            rating = "🟡 SOLID"

    # Category B2 — Big Pony Numbered
    elif category == "B2":
        if price <= 12:
            rating = "🔵 BLUE"
        else:
            rating = "🟢 GREEN"

    # Category C — Sash / Colourblock
    elif category == "C":
        if price <= 15:
            rating = "🔵 BLUE"
        elif price <= 25:
            rating = "🟢 GREEN"
        else:
            rating = "🟡 SOLID"

    # Category D — Plain Big Pony
    elif category == "D":
        if price <= 12:
            rating = "🟢 GREEN"
        else:
            rating = "🟡 SOLID"

    # Category E — Standard RL (NEVER auto-SKIP if brand confirmed)
    elif category == "E":
        if price <= 10:
            rating = "🟡 SOLID"
        elif price <= MAX_PRICE_GBP:
            rating = "🟠 TIGHT"
        else:
            rating = "❌ SKIP"

    else:
        rating = "🟠 TIGHT"

    # ── Special tag ──
    special_tag = ""
    cat_label = CATEGORY_LABELS.get(category, "")
    if category in ("A", "B") and price <= 20:
        special_tag = f"🏆 PREMIUM SNIPE — {cat_label}"
    elif category == "B2":
        special_tag = f"🐴 BIG PONY NUMBERED — {cat_label}"
    elif category == "C":
        special_tag = f"🔷 SASH/COLOURBLOCK — {cat_label}"
    elif matched_signals:
        top = ", ".join(s.split("(")[0] for s in matched_signals[:2])
        special_tag = f"✨ Signals: {top}"

    return {
        "resell_low":      low,
        "resell_high":     high,
        "profit_low":      net_low,
        "profit_high":     net_high,
        "roi_low":         roi_low,
        "roi_high":        roi_high,
        "rating":          rating,
        "special_tag":     special_tag,
        "signal_score":    signal_score,
        "matched_signals": matched_signals,
        "category":        category,
        "cat_label":       cat_label,
    }


# ─────────────────────────────────────────────
#  VINTED API
# ─────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer":         f"https://{DOMAIN}/",
    "Origin":          f"https://{DOMAIN}",
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
            return r.json().get("items", [])
        elif r.status_code == 401:
            print(f"{Fore.YELLOW}[AUTH] 401 received — re-fetching session cookies...")
            _refresh_session()
    except Exception as e:
        print(f"{Fore.RED}[ERROR] fetch_listings: {e}")
    return []


def _refresh_session():
    try:
        session.get(f"https://{DOMAIN}/", timeout=10)
    except Exception:
        pass


# ─────────────────────────────────────────────
#  FILTERS
# ─────────────────────────────────────────────
def is_infant_or_underage(item: dict) -> bool:
    text = " ".join([
        item.get("title", ""),
        item.get("description", ""),
        item.get("size_title", ""),
    ]).lower()
    return any(kw in text for kw in BLOCKED_SIZE_KEYWORDS)


def is_oversized(item: dict) -> bool:
    text = " " + (item.get("size_title") or "").lower() + " " + (item.get("title") or "").lower() + " "
    return any(kw in text for kw in BLOCKED_SIZE_LARGE)


def is_womens(item: dict) -> bool:
    dept      = (item.get("department", "") or "").lower()
    dept_name = (item.get("department_name", "") or "").lower()
    if "women" in dept or "female" in dept or "women" in dept_name:
        return True
    text = " ".join([
        item.get("title", ""),
        item.get("description", ""),
        dept, dept_name,
    ]).lower()
    return any(kw in text for kw in BLOCKED_WOMENS_KEYWORDS)


def is_accessory(item: dict) -> bool:
    text = " ".join([
        item.get("title", ""),
        item.get("description", ""),
        item.get("category_title", ""),
    ]).lower()
    return any(kw in text for kw in BLOCKED_ACCESSORY_KEYWORDS)


def is_ralph_lauren(item: dict) -> bool:
    title = (item.get("title", "") or "").lower()
    brand = (item.get("brand_title", "") or "").lower()
    return (
        any(kw in brand for kw in REQUIRED_BRAND_KEYWORDS) or
        any(kw in title for kw in REQUIRED_BRAND_KEYWORDS)
    )


# ─────────────────────────────────────────────
#  DISCORD
# ─────────────────────────────────────────────
COLOR_MAP = {
    "🔵 BLUE":  0x0055FF,
    "🟢 GREEN": 0x00C851,
    "🟡 SOLID": 0xFFDD00,
    "🟠 TIGHT": 0xFF8800,
    "❌ SKIP":  0xCC0000,
}


def send_discord(item: dict, label: str, profit: dict, visual: dict):
    price = get_price(item)
    title = item.get("title", "Unknown")
    url   = item.get("url") or f"https://{DOMAIN}/items/{item.get('id')}"
    photo = ""
    if item.get("photos"):
        photo = item["photos"][0].get("url") or item["photos"][0].get("full_size_url", "")

    embed_color = COLOR_MAP.get(profit["rating"], 0x888888)

    desc_lines = [f"**{title}**", f"[🔗 View on Vinted]({url})"]
    if profit.get("special_tag"):
        desc_lines.insert(0, f"**{profit['special_tag']}**")

    # Visual score display
    vis_score = visual.get("score", -1)
    if vis_score < 0:
        vis_display = "Unavailable"
    else:
        vis_display = f"{vis_score}/100 — {visual.get('label', '')}"
        if visual.get("top_classes"):
            top_cls_str = ", ".join(f"{c}({s}%)" for c, s in visual["top_classes"])
            vis_display += f"\nTop classes: {top_cls_str}"

    # Signals display
    signals_str = (
        f"{profit['signal_score']}pts — "
        + (", ".join(s.split("(")[0] for s in profit["matched_signals"]) or "none detected")
    )

    embed = {
        "title":       f"{profit['rating']}  |  {label}  |  £{price:.2f}",
        "description": "\n".join(desc_lines),
        "color":       embed_color,
        "fields": [
            {"name": "📂 Category",      "value": profit["cat_label"],                                           "inline": True},
            {"name": "💰 Buy Price",     "value": f"£{price:.2f}",                                              "inline": True},
            {"name": "📦 Resell Range",  "value": f"£{profit['resell_low']}–£{profit['resell_high']} (eBay/Depop)", "inline": True},
            {"name": "📈 Net Profit",    "value": f"£{profit['profit_low']}–£{profit['profit_high']}",           "inline": True},
            {"name": "🎯 ROI",           "value": f"{profit['roi_low']}%–{profit['roi_high']}%",                 "inline": True},
            {"name": "⚡ Verdict",       "value": profit["rating"],                                             "inline": True},
            {"name": "🔍 Signal Score",  "value": signals_str,                                                  "inline": False},
            {"name": "🤖 Visual Score",  "value": vis_display,                                                  "inline": False},
        ],
        "thumbnail": {"url": photo} if photo else {},
        "footer":    {"text": f"Ralph Lauren Bot v2.0 • {datetime.now().strftime('%H:%M:%S')}"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    payload = {
        "username":   "RL Sniper 🎽",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds":     [embed],
    }

    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        if r.status_code not in (200, 204):
            print(f"{Fore.YELLOW}[DISCORD] Non-200: {r.status_code}")
    except Exception as e:
        print(f"{Fore.RED}[DISCORD ERROR] {e}")


# ─────────────────────────────────────────────
#  CONSOLE COLOUR HELPER
# ─────────────────────────────────────────────
def verdict_color(rating: str) -> str:
    if "BLUE"  in rating: return Fore.BLUE
    if "GREEN" in rating: return Fore.GREEN
    if "SOLID" in rating: return Fore.YELLOW
    if "TIGHT" in rating: return Fore.YELLOW
    return Fore.RED


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
def run():
    print(f"\n{Fore.CYAN}{'═'*65}")
    print(f"{Fore.CYAN}  🎽  RALPH LAUREN VINTED SNIPER v2.0 — STARTED")
    print(f"{Fore.CYAN}  Max Price: £{MAX_PRICE_GBP}  |  Interval: {POLL_INTERVAL}s")
    print(f"{Fore.CYAN}  Filters: Men's only | Age 14+ | Max size L | No accessories")
    print(f"{Fore.CYAN}  TensorFlow visual scoring: {'✅ ENABLED' if TF_AVAILABLE else '❌ DISABLED (install tensorflow)'}")
    print(f"{Fore.CYAN}  🔵 BLUE = must-buy | 🟢 GREEN = strong | 🟡 SOLID = decent | 🟠 TIGHT = marginal")
    print(f"{Fore.CYAN}{'═'*65}\n")

    _refresh_session()
    cycle = 0

    while True:
        cycle += 1
        found_this_cycle = 0
        print(
            f"{Fore.WHITE}[{datetime.now().strftime('%H:%M:%S')}] "
            f"Cycle #{cycle} — scanning {len(SEARCHES)} queries..."
        )

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
                if is_accessory(item):
                    continue
                if not is_ralph_lauren(item):
                    continue

                price = get_price(item)
                if price <= 0 or price > MAX_PRICE_GBP:
                    continue

                # ── PROFIT & VERDICT ──
                profit = estimate_profit(item)

                # ── TF VISUAL ASSESSMENT ──
                photo_url = ""
                if item.get("photos"):
                    photo_url = (
                        item["photos"][0].get("url") or
                        item["photos"][0].get("full_size_url", "")
                    )
                visual = assess_image_with_tf(photo_url) if photo_url else {
                    "score": -1, "label": "No image", "top_classes": []
                }

                found_this_cycle += 1
                vc = verdict_color(profit["rating"])
                tag = f"  [{profit['special_tag']}]" if profit.get("special_tag") else ""
                vis_str = (
                    f"  | 🤖 {visual['score']}/100"
                    if visual["score"] >= 0
                    else "  | 🤖 N/A"
                )
                print(
                    f"  {vc}{profit['rating']}  {label}  "
                    f"£{price:.2f}  →  profit £{profit['profit_low']}-£{profit['profit_high']}"
                    f"{tag}{vis_str}  |  {item.get('title', '')[:40]}"
                )

                # ── DISCORD — always send, visual score included ──
                if DISCORD_WEBHOOK_URL:
                    send_discord(item, label, profit, visual)

            time.sleep(1.5)

        if found_this_cycle == 0:
            print(f"  {Fore.WHITE}No new items this cycle.")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
