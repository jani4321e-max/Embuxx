# Crunchyroll Checker Bot

A Telegram bot for checking Crunchyroll accounts.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set your bot token (either via environment variable or edit `bot.py`):
```bash
export BOT_TOKEN="your-telegram-bot-token"
```

3. Run the bot:
```bash
python3 bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Help and command list |
| `/check` | Start checking accounts |
| `/noproxy` | Check without proxies |
| `/withproxy` | Check with proxies |
| `/status` | View current check status |
| `/results` | View results |
| `/clear` | Clear your results |
| `/stats` | Bot statistics |

## Usage

1. Send `/check` to the bot
2. Optionally choose `/withproxy` or `/noproxy`
3. Send a combo file (`email:password` format, one per line)
4. Monitor with `/status`, view results with `/results`
