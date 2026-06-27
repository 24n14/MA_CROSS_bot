"""
Модуль логирования.
Логирует в консоль, файл и отправляет WARNING в ntfy.
"""

import os
import sys
from pathlib import Path
from loguru import logger
import requests
from python_ntfy import MessagePriority

# ── Ntfy ────────────────────────────────────────────────
NTFY_TOPIC = "ma_cross_24n14"

# ── Прокси ──────────────────────────────────────────────
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")

_proxies = None
if PROXY_HOST and PROXY_PORT:
    proxy_url = (
        f"http://{PROXY_USER}:{PROXY_PASS}@"
        f"{PROXY_HOST}:{PROXY_PORT}"
    )
    _proxies = {'http': proxy_url, 'https': proxy_url}

    # Проверка IP
    try:
        test_ip = requests.get(
            'https://api.ipify.org', proxies=_proxies, timeout=10
        ).text
        logger.info(f"✅ Внешний IP через прокси: {test_ip}")
    except Exception as e:
        logger.error(f"❌ Не удалось проверить IP через прокси: {e}")


def _send_ntfy(message: str, title: str, priority: int) -> None:
    """Отправляет уведомление в ntfy через requests (с прокси если настроен)"""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    payload = {
        "topic": NTFY_TOPIC,
        "message": message,
        "title": title,
        "priority": priority,
    }
    try:
        if _proxies:
            requests.post(url, json=payload, proxies=_proxies, timeout=10)
        else:
            requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


# ── Кастомный handler для ntfy ──────────────────────────
def ntfy_handler(message):
    """Отправляет WARNING сообщения в ntfy"""
    text = message.record["message"].strip()
    text_upper = text.upper()

    if "BULLISH" in text_upper:
        title = f"🟢 {text.split(chr(10))[0][:50]}"
    elif "BEARISH" in text_upper:
        title = f"🔴 {text.split(chr(10))[0][:50]}"
    else:
        title = f"⚠️ {text.split(chr(10))[0][:50]}"

    priority = (
        MessagePriority.HIGH.value
        if "STRONG" in text_upper
        else MessagePriority.DEFAULT.value
    )

    _send_ntfy(message=text, title=title, priority=priority)


logger.remove()

# ── Консоль ───────────────────────────────────────────────
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:MM-DD HH:mm}</green>|{level}|<cyan>{name}</cyan>|<level>{message}</level>",
    level="INFO",
)

# ── Файл с ротацией ───────────────────────────────────────
log_file = Path(__file__).parent / "logs" / "bot_history.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logger.add(
    log_file,
    format="{time:YYYY-MM-DD HH:mm:ss}|{level}|{name}|{message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8"
)

# ── Ntfy handler: только WARNING ─────────────────────────
logger.add(
    ntfy_handler,
    level="WARNING",
    format="{message}",
)