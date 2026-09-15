"""One-time Telegram webhook registration.

MANUAL ONE-TIME STEP — do NOT run automatically at app boot.

When to run:
  After deploying bat-board to Railway with BOTH env vars set in the
  Railway dashboard:
    - TELEGRAM_BOT_TOKEN (from @BotFather)
    - TELEGRAM_WEBHOOK_SECRET (random string you generated)

What it does:
  Tells Telegram's Bot API to POST all incoming bot messages to:
    https://bat-board.up.railway.app/api/telegram/webhook
  ...with the secret token Telegram must include in the
  X-Telegram-Bot-Api-Secret-Token header on every delivery.

Usage (from the repo root, with the two env vars exported locally):
  TELEGRAM_BOT_TOKEN=<from BotFather> \\
  TELEGRAM_WEBHOOK_SECRET=<your generated secret> \\
  backend/.venv/bin/python backend/scripts/set_telegram_webhook.py

  Optional override if the public URL ever changes:
  ... set_telegram_webhook.py --url https://your-domain/api/telegram/webhook

Re-run any time the bot token, webhook secret, or public URL changes.
"""

import argparse
import os
import sys

import httpx

DEFAULT_WEBHOOK_URL = "https://bat-board.up.railway.app/api/telegram/webhook"


def main() -> int:
    parser = argparse.ArgumentParser(description="Register the Telegram webhook (one-time, manual).")
    parser.add_argument("--url", default=DEFAULT_WEBHOOK_URL, help="Public webhook URL Telegram will POST to.")
    args = parser.parse_args()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not bot_token or not webhook_secret:
        print("ERROR: set TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET in your environment first.", file=sys.stderr)
        return 1

    resp = httpx.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json={"url": args.url, "secret_token": webhook_secret},
        timeout=15.0,
    )
    print(f"HTTP {resp.status_code}: {resp.text}")
    try:
        ok = resp.json().get("ok", False)
    except Exception:
        ok = False
    if resp.status_code == 200 and ok:
        print(f"Webhook registered: {args.url}")
        return 0
    print("Webhook registration FAILED — check the bot token and try again.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
