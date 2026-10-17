"""Find your Telegram chat_id: write any message to your bot, then run
python -m vfs_monitor.telegram_setup
"""

import sys

import requests

from .config import load_config


def main() -> None:
    cfg = load_config()
    if not cfg.telegram_token:
        sys.exit("Сначала впишите TELEGRAM_BOT_TOKEN в .env")
    resp = requests.get(f"https://api.telegram.org/bot{cfg.telegram_token}/getUpdates", timeout=30)
    resp.raise_for_status()
    chats = {}
    for update in resp.json().get("result", []):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("username") or chat.get("first_name", "")
    if not chats:
        sys.exit("Сообщений нет. Напишите боту /start в Telegram и запустите снова.")
    for chat_id, name in chats.items():
        print(f"TELEGRAM_CHAT_ID={chat_id}   ({name})")


if __name__ == "__main__":
    main()
