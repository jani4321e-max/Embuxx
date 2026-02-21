# Crunchyroll Checker Telegram Bot

A Telegram bot that checks Crunchyroll accounts from combo files.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your bot token

Get a bot token from [@BotFather](https://t.me/BotFather) on Telegram, then set it as an environment variable:

```bash
export BOT_TOKEN="your-bot-token-here"
```

### 3. (Optional) Restrict to specific users

Set a comma-separated list of Telegram user IDs:

```bash
export AUTHORIZED_USERS="123456789,987654321"
```

Leave unset to allow all users.

### 4. Run the bot

```bash
python bot.py
```

## Docker

```bash
docker build -t crunchyroll-bot .
docker run -d --name crunchyroll-bot -e BOT_TOKEN="your-token" crunchyroll-bot
```

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Initialize the bot |
| `/help` | Show help and commands |
| `/check` | Begin checking accounts |
| `/noproxy` | Check without proxies |
| `/withproxy` | Check with proxies |
| `/status` | View current check progress |
| `/results` | View results and download hit files |
| `/clear` | Clear your results |
| `/stats` | Bot-wide statistics |

## Usage Flow

1. Send `/check` to the bot
2. Optionally choose `/noproxy` or `/withproxy`
3. If using proxies, upload a proxy file first (one proxy per line)
4. Upload a combo file with `email:password` format (one per line)
5. Use `/status` to monitor progress
6. Use `/results` to view and download hits
