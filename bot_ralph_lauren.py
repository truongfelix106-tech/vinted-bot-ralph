"""
╔══════════════════════════════════════════════════════════════════════╗
║          RALPH LAUREN VINTED SNIPER BOT v2.0  — AI EDITION         ║
║                                                                      ║
║   New in v2.0:                                                       ║
║   • Claude AI scores every candidate deal (0-100)                   ║
║   • AI writes its own resale estimate + reasoning per item          ║
║   • Hybrid filter: fast keyword pre-filter → AI deep score          ║
║   • Self-tuning: after 20 scored items, AI rewrites its own         ║
║     resale brackets and saves them to ai_calibration.json           ║
║   • Discord embed shows Claude's reasoning blurb                    ║
║   • SKIP verdicts never hit Discord (saves noise)                   ║
║                                                                      ║
║   HOW TO USE:                                                        ║
║   1. pip install requests colorama                                   ║
║   2. Set DISCORD_WEBHOOK_URL  (env var or hardcode below)           ║
║   3. Run: python bot_ralph_lauren_ai.py                             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os, json, time, requests
from datetime import datetime, timezone
from colorama import Fore, Style, init

init(autoreset=True)

# ══════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "PASTE_YOUR_WEBHOOK_HERE"           # ← paste your webhook here
)
POLL_INTERVAL   = 12          # seconds between Vinted scans
MAX_PRICE_GBP   = 16.00
DOMAIN          = "www.vinted.co.uk"
CALIBRATION_FILE = "ai_calibration.json"
SCORE_LOG_FILE   = "scored_items.json"
AI_RETUNE_EVERY  = 20         # retune resale brackets every N scored items
MIN_AI_SCORE     = 40         # items below this score are silently skipped

# ══════════════════════════════════════════════════════════════════════
#  SEARCH QUERIES
# ══════════════════════════════════════════════════════════════════════
SEARCHES = [
    ("🎽 STRIPED POLO",    "ralph lauren striped polo vintage",   "HIGH"),
    ("🏉 RUGBY TOP",       "ralph lauren rugby top",              "HIGH"),
    ("🇺🇸 USA BRANDED",   "ralph lauren USA polo",               "HIGH"),
    ("🎤 CHIEF KEEF POLO", "ralph lauren polo shirt oversized",   "HIGH"),
    ("👔 GENERAL POLO",    "ralph lauren polo shirt",             "MED"),
    ("🧥 RL GENERAL",      "ralph lauren",                        "MED"),
]

# ══════════════════════════════════════════════════════════════════════
#  FAST PRE-FILTER LISTS  (keyword gate before AI call — saves tokens)
# ══════════════════════════════════════════════════════════════════════
BLOCKED_SIZE_KEYWORDS = [
    "baby","infant","toddler","newborn",
    "0-3","3-6","6-9","6-12","12-18","18-24","9-12",
    "0m","3m","6m","9m","12m","18m",
    "5t","4t","3t","2t","1t",
    "age 1","age 2","age 3","age 4","age 5",
    "age 6","age 7","age 8","age 9","age 10",
    "age 11","age 12","age 13",
    "1-2","2-3","3-4","4-5","5-6","6-7","7-8",
    "8-9","9-10","10-11","11-12","12-13","13-14",
    "kids","children","child","junior",
]
BLOCKED_SIZE_LARGE = [
    " xl","/xl","-xl","_xl","xxl","xxxl","2xl","3xl","4xl","5xl",
    "1x","2x","3x","4x","extra large","plus size",
]
BLOCKED_WOMENS = [
    "women's","womens","womenswear","ladies","ladieswear","for her","for women",
]
BLOCKED_ACCESSORIES = [
    "hat","cap","caps","beanie","snapback","bucket hat","scarf","scarves",
    "bag","tote","backpack","wallet","purse","belt","shoes","trainers",
    "boots","sneakers","socks","watch","bracelet","necklace","sunglasses",
]
REQUIRED_BRAND = ["ralph lauren","polo ralph","rl polo","polo rl"]

# ══════════════════════════════════════════════════════════════════════
#  RESALE BRACKETS  (AI will overwrite these after self-tuning)
# ══════════════════════════════════════════════════════════════════════
DEFAULT_BRACKETS = {
    "city_polo":    {"low": 50, "high": 90,  "label": "City / Chief Keef Polo"},
    "rugby":        {"low": 40, "high": 75,  "label": "Rugby Top"},
    "double_rl":    {"low": 50, "high": 90,  "label": "Double RL / RRL"},
    "striped":      {"low": 30, "high": 60,  "label": "Striped Vintage Polo"},
    "usa":          {"low": 30, "high": 55,  "label": "USA Branded RL"},
    "big_pony":     {"low": 35, "high": 65,  "label": "Big Pony Polo"},
    "button_up":    {"low": 12, "high": 22,  "label": "Button-Up Shirt"},
    "default":      {"low": 18, "high": 35,  "label": "Polo / Knitwear"},
}

POSTAGE     = 3.50
EBAY_FEE    = 0.1269


def load_brackets() -> dict:
    """Load AI-tuned brackets from disk if available, else use defaults."""
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE) as f:
                data = json.load(f)
                print(f"{Fore.CYAN}[CALIBRATION] Loaded AI-tuned resale brackets from {CALIBRATION_FILE}")
                return data
        except Exception:
            pass
    return DEFAULT_BRACKETS.copy()


def save_brackets(brackets: dict):
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(brackets, f, indent=2)
    print(f"{Fore.CYAN}[CALIBRATION] Saved updated brackets → {CALIBRATION_FILE}")


# Load brackets at startup
resale_brackets = load_brackets()


# ══════════════════════════════════════════════════════════════════════
#  SCORE LOG  (feeds the self-tuner)
# ══════════════════════════════════════════════════════════════════════
def load_score_log() -> list:
    if os.path.exists(SCORE_LOG_FILE):
        try:
            with open(SCORE_LOG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def append_score_log(entry: dict):
    log = load_score_log()
    log.append(entry)
    with open(SCORE_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


# ══════════════════════════════════════════════════════════════════════
#  ANTHROPIC API  — deal scorer
# ══════════════════════════════════════════════════════════════════════
ANTHROPIC_HEADERS = {"Content-Type": "application/json"}
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"


def ai_score_item(title: str, price: float, size: str, condition: str,
                  description: str, brackets: dict) -> dict | None:
    """
    Send one listing to Claude for deep scoring.
    Returns a parsed dict or None on failure.
    """
    bracket_summary = "\n".join(
        f"  {k}: £{v['low']}–£{v['high']} ({v['label']})"
        for k, v in brackets.items()
    )

    prompt = f"""You are an expert vintage Ralph Lauren reseller operating on UK eBay and Depop in 2024-2025.
You know every era, colourway and collectable sub-line of Ralph Lauren.

A Vinted listing has passed a basic keyword filter. Score it for resell potential.

LISTING DETAILS
───────────────
Title:       {title}
Buy price:   £{price:.2f}
Size:        {size}
Condition:   {condition}
Description: {description[:300] if description else 'N/A'}

CURRENT RESALE BRACKETS (used for context, you may override)
────────────────────────────────────────────────────────────
{bracket_summary}

YOUR TASK
─────────
Return ONLY valid JSON with exactly these fields — no markdown, no explanation outside the JSON:

{{
  "score": <integer 0-100>,
  "verdict": "<FIRE|SOLID|TIGHT|SKIP>",
  "category": "<city_polo|rugby|double_rl|striped|usa|big_pony|button_up|default>",
  "est_resale_low": <integer GBP>,
  "est_resale_high": <integer GBP>,
  "net_profit_low": <integer GBP after 12.7% eBay fee and £3.50 postage>,
  "net_profit_high": <integer GBP after 12.7% eBay fee and £3.50 postage>,
  "roi_pct": <integer percent based on net_profit_low / buy_price>,
  "reasoning": "<1-2 punchy sentences explaining WHY this is or isn't a snipe. Be specific about the era, colourway, or detail that drives value. Be harsh if it's weak.>",
  "confidence": "<high|medium|low>",
  "skip_reason": "<null or brief reason if verdict is SKIP>"
}}

SCORING GUIDE
─────────────
90-100: Grail — city polo, polo cup, rare RRL, diagonal sash, pristine rugby for <£5
70-89:  Fire   — big pony, usa, striped vintage, rugby <£10, identifiable collectable
50-69:  Solid  — clean polo with resell upside, good condition basics
30-49:  Tight  — possible flip but tight margin, button-ups, logo-less pieces
0-29:   Skip   — bad condition, no brand confirmation, common item, no margin

Be HARSH. Most items should score 30-60. Only exceptional pieces score 80+."""

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        r = requests.post(
            ANTHROPIC_URL,
            headers=ANTHROPIC_HEADERS,
            json=payload,
            timeout=20
        )
        if r.status_code != 200:
            print(f"{Fore.YELLOW}[AI] API error {r.status_code}: {r.text[:200]}")
            return None

        raw = r.json()["content"][0]["text"].strip()
        # Strip any accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"{Fore.RED}[AI] JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"{Fore.RED}[AI] Request error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
#  SELF-TUNER  — runs every AI_RETUNE_EVERY scored items
# ══════════════════════════════════════════════════════════════════════
def ai_retune_brackets(score_log: list, current_brackets: dict) -> dict:
    """
    Feed scored item history back to Claude.
    Ask it to revise the resale brackets based on real observations.
    Returns updated brackets dict (or current if something fails).
    """
    if len(score_log) < AI_RETUNE_EVERY:
        return current_brackets

    recent = score_log[-AI_RETUNE_EVERY:]
    history_text = "\n".join(
        f"- {e['title'][:60]} | buy £{e['buy_price']} | "
        f"AI said resale £{e.get('est_resale_low','?')}–£{e.get('est_resale_high','?')} | "
        f"category: {e.get('category','?')} | score: {e.get('score','?')}"
        for e in recent
    )

    current_text = json.dumps(current_brackets, indent=2)

    prompt = f"""You are an expert Ralph Lauren reseller who also writes pricing models.

You have been scoring Vinted listings. Here are the last {AI_RETUNE_EVERY} items you scored:

{history_text}

Here are the CURRENT resale brackets your scoring system uses:
{current_text}

Based on the pattern of items you've seen (prices, categories, scores), 
decide if any brackets need adjusting to be more accurate.

Return ONLY valid JSON — the full updated brackets object with the same structure.
Do NOT add new keys. Do NOT remove keys. Only adjust the "low" and "high" integer values if warranted.
If the current brackets are already accurate, return them unchanged.
No markdown, no explanation — pure JSON only."""

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 600,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        r = requests.post(
            ANTHROPIC_URL,
            headers=ANTHROPIC_HEADERS,
            json=payload,
            timeout=25
        )
        if r.status_code != 200:
            print(f"{Fore.YELLOW}[RETUNE] API error {r.status_code}")
            return current_brackets

        raw = r.json()["content"][0]["text"].strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        new_brackets = json.loads(raw)

        # Sanity check — must have same keys
        if set(new_brackets.keys()) == set(current_brackets.keys()):
            print(f"{Fore.CYAN}[RETUNE] ✅ Brackets updated by AI after {AI_RETUNE_EVERY} items")
            return new_brackets
        else:
            print(f"{Fore.YELLOW}[RETUNE] Key mismatch — keeping current brackets")
            return current_brackets

    except Exception as e:
        print(f"{Fore.RED}[RETUNE] Failed: {e}")
        return current_brackets


# ══════════════════════════════════════════════════════════════════════
#  VINTED SESSION + FETCH
# ══════════════════════════════════════════════════════════════════════
VINTED_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": f"https://{DOMAIN}/",
    "Origin":  f"https://{DOMAIN}",
}

vinted_session = requests.Session()
vinted_session.headers.update(VINTED_HEADERS)
seen_ids: set = set()


def refresh_session():
    try:
        vinted_session.get(f"https://{DOMAIN}/", timeout=10)
    except Exception:
        pass


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
        r = vinted_session.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("items", [])
        elif r.status_code == 401:
            print(f"{Fore.YELLOW}[AUTH] 401 — refreshing session...")
            refresh_session()
    except Exception as e:
        print(f"{Fore.RED}[VINTED ERROR] {e}")
    return []


# ══════════════════════════════════════════════════════════════════════
#  FAST PRE-FILTERS  (run before AI to save API calls)
# ══════════════════════════════════════════════════════════════════════
def _text(item: dict, *fields) -> str:
    return " ".join((item.get(f) or "") for f in fields).lower()


def passes_prefilter(item: dict) -> tuple[bool, str]:
    """Returns (passes, reason_if_blocked)"""
    text = _text(item, "title", "description", "size_title", "department", "category_title")
    brand = _text(item, "brand_title")

    if any(k in text for k in BLOCKED_SIZE_KEYWORDS):
        return False, "infant/child size"
    if any(k in (" " + _text(item, "size_title", "title") + " ") for k in BLOCKED_SIZE_LARGE):
        return False, "XL or above"
    if any(k in text for k in BLOCKED_WOMENS):
        return False, "women's item"
    if any(k in text for k in BLOCKED_ACCESSORIES):
        return False, "accessory"

    # Must have Ralph Lauren brand confirmation
    combined = text + " " + brand
    if not any(k in combined for k in REQUIRED_BRAND):
        return False, "no RL brand confirmed"

    price = get_price(item)
    if price <= 0 or price > MAX_PRICE_GBP:
        return False, f"price £{price:.2f} out of range"

    return True, ""


def get_price(item: dict) -> float:
    p = item.get("price", 0)
    if isinstance(p, (int, float)):
        return float(p)
    if isinstance(p, str):
        try: return float(p)
        except: return 0.0
    if isinstance(p, dict):
        for k in ("amount", "value", "numeric"):
            if k in p:
                try: return float(p[k])
                except: pass
    return 0.0


# ══════════════════════════════════════════════════════════════════════
#  DISCORD NOTIFICATION
# ══════════════════════════════════════════════════════════════════════
VERDICT_COLORS = {
    "FIRE":  0x0099FF,   # Blue  — premium
    "SOLID": 0x00C851,   # Green
    "TIGHT": 0xFFBB33,   # Amber
    "SKIP":  0xCC0000,   # Red
}
VERDICT_EMOJI = {
    "FIRE":  "🔥",
    "SOLID": "✅",
    "TIGHT": "⚠️",
    "SKIP":  "❌",
}
CONFIDENCE_EMOJI = {"high": "🟢", "medium": "🟡", "low": "🔴"}


def send_discord(item: dict, label: str, ai: dict):
    price  = get_price(item)
    title  = item.get("title", "Unknown")
    url    = item.get("url") or f"https://{DOMAIN}/items/{item.get('id')}"
    photo  = ""
    photos = item.get("photos") or []
    if photos:
        photo = photos[0].get("url") or photos[0].get("full_size_url", "")
    elif item.get("photo"):
        photo = item["photo"].get("url", "")

    verdict    = ai.get("verdict", "TIGHT")
    color      = VERDICT_COLORS.get(verdict, 0x888888)
    v_emoji    = VERDICT_EMOJI.get(verdict, "⚠️")
    conf_emoji = CONFIDENCE_EMOJI.get(ai.get("confidence", "low"), "🔴")
    ai_score   = ai.get("score", 0)
    reasoning  = ai.get("reasoning", "No reasoning provided.")

    # Score bar (visual)
    filled = round(ai_score / 10)
    score_bar = "█" * filled + "░" * (10 - filled)

    embed = {
        "title": f"{v_emoji} {verdict}  |  {label}  |  £{price:.2f}",
        "url": url,
        "color": color,
        "description": (
            f"**{title}**\n"
            f"[🔗 View on Vinted]({url})\n\n"
            f"💬 **AI says:** *{reasoning}*"
        ),
        "fields": [
            {
                "name": "💰 Buy Price",
                "value": f"**£{price:.2f}**",
                "inline": True
            },
            {
                "name": "📈 Est. Resale",
                "value": f"£{ai.get('est_resale_low','?')}–£{ai.get('est_resale_high','?')}",
                "inline": True
            },
            {
                "name": "💵 Net Profit",
                "value": f"£{ai.get('net_profit_low','?')}–£{ai.get('net_profit_high','?')}",
                "inline": True
            },
            {
                "name": "🎯 ROI",
                "value": f"{ai.get('roi_pct','?')}%",
                "inline": True
            },
            {
                "name": f"{conf_emoji} AI Confidence",
                "value": ai.get("confidence", "low").upper(),
                "inline": True
            },
            {
                "name": "📦 Condition",
                "value": item.get("status", "N/A"),
                "inline": True
            },
            {
                "name": f"🧠 AI Score  [{score_bar}]  {ai_score}/100",
                "value": f"Category: `{ai.get('category', 'default')}`",
                "inline": False
            },
        ],
        "thumbnail": {"url": photo} if photo else {},
        "footer": {
            "text": f"RL Sniper v2.0 AI Edition  •  {datetime.now().strftime('%H:%M:%S')}"
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = {
        "username":   "RL Sniper 🎽 AI",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [embed],
    }

    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        if r.status_code not in (200, 204):
            print(f"{Fore.YELLOW}[DISCORD] {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"{Fore.RED}[DISCORD ERROR] {e}")


# ══════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════
def run():
    global resale_brackets

    print(f"\n{Fore.CYAN}{'═'*65}")
    print(f"{Fore.CYAN}  🎽  RALPH LAUREN VINTED SNIPER v2.0  —  AI EDITION  —  STARTED")
    print(f"{Fore.CYAN}  Max Price: £{MAX_PRICE_GBP}  |  Poll: {POLL_INTERVAL}s  |  Min AI score: {MIN_AI_SCORE}")
    print(f"{Fore.CYAN}  Self-tunes every {AI_RETUNE_EVERY} scored items  →  {CALIBRATION_FILE}")
    print(f"{Fore.CYAN}{'═'*65}\n")

    refresh_session()
    score_log  = load_score_log()
    cycle      = 0
    ai_calls   = 0

    while True:
        cycle += 1
        new_this_cycle  = 0
        ai_this_cycle   = 0

        print(
            f"{Fore.WHITE}[{datetime.now().strftime('%H:%M:%S')}] "
            f"Cycle #{cycle} | {len(SEARCHES)} queries | "
            f"{ai_calls} AI calls total | {len(score_log)} in log"
        )

        for label, search_text, priority in SEARCHES:
            items = fetch_listings(search_text, MAX_PRICE_GBP)

            for item in items:
                item_id = str(item.get("id", ""))
                if not item_id or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # ── Stage 1: fast keyword pre-filter ──
                ok, reason = passes_prefilter(item)
                if not ok:
                    continue

                price = get_price(item)

                # ── Stage 2: AI deep score ──
                print(f"  {Fore.CYAN}[AI] Scoring: {item.get('title','')[:55]}  £{price:.2f}")

                ai_result = ai_score_item(
                    title       = item.get("title", ""),
                    price       = price,
                    size        = item.get("size_title", "N/A"),
                    condition   = item.get("status", "N/A"),
                    description = item.get("description", ""),
                    brackets    = resale_brackets,
                )
                ai_calls      += 1
                ai_this_cycle += 1

                if ai_result is None:
                    print(f"  {Fore.YELLOW}[AI] No result — skipping")
                    continue

                score   = ai_result.get("score", 0)
                verdict = ai_result.get("verdict", "SKIP")

                # Log every scored item for self-tuning
                log_entry = {
                    "timestamp":     datetime.now().isoformat(),
                    "item_id":       item_id,
                    "title":         item.get("title", ""),
                    "buy_price":     price,
                    **{k: ai_result.get(k) for k in (
                        "score","verdict","category",
                        "est_resale_low","est_resale_high",
                        "net_profit_low","net_profit_high",
                        "roi_pct","reasoning","confidence"
                    )}
                }
                score_log.append(log_entry)
                append_score_log(log_entry)

                # ── Console output ──
                color = (
                    Fore.BLUE   if verdict == "FIRE"  else
                    Fore.GREEN  if verdict == "SOLID" else
                    Fore.YELLOW if verdict == "TIGHT" else
                    Fore.RED
                )
                emoji = VERDICT_EMOJI.get(verdict, "⚠️")
                print(
                    f"  {color}{emoji} {verdict:5s}  score={score:3d}  "
                    f"£{price:.2f} → "
                    f"£{ai_result.get('net_profit_low','?')}–£{ai_result.get('net_profit_high','?')} profit  |  "
                    f"{item.get('title','')[:40]}"
                )

                # ── Send to Discord (skip low scores and actual SKIPs) ──
                if score >= MIN_AI_SCORE and verdict != "SKIP":
                    send_discord(item, label, ai_result)
                    new_this_cycle += 1
                    time.sleep(0.5)   # brief pause between Discord sends

                # ── Self-tuning check ──
                if len(score_log) % AI_RETUNE_EVERY == 0 and len(score_log) > 0:
                    print(f"\n{Fore.CYAN}[RETUNE] {len(score_log)} items scored — running self-tune...")
                    new_brackets = ai_retune_brackets(score_log, resale_brackets)
                    if new_brackets != resale_brackets:
                        resale_brackets = new_brackets
                        save_brackets(resale_brackets)
                    print(f"{Fore.CYAN}[RETUNE] Done.\n")

            time.sleep(1.5)  # small gap between Vinted queries

        summary = (
            f"  Cycle done — {new_this_cycle} sent to Discord | "
            f"{ai_this_cycle} AI calls this cycle"
        )
        print(Fore.WHITE + summary if new_this_cycle == 0 else Fore.GREEN + summary)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
