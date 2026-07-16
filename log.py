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
from dotenv import load_dotenv

load_dotenv()

# ── Ntfy ────────────────────────────────────────────────
NTFY_TOPIC = "github_24n14_ma_cross"

# ── Прокси ──────────────────────────────────────────────
USE_PROXY = False  # False - отключено, True - включено

PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")

_proxies = None
if USE_PROXY and PROXY_HOST and PROXY_PORT:
    proxy_url = (
        f"http://{PROXY_USER}:{PROXY_PASS}@"
        f"{PROXY_HOST}:{PROXY_PORT}"
    )
    _proxies = {'http': proxy_url, 'https': proxy_url}

    try:
        test_ip = requests.get(
            'https://api.ipify.org', proxies=_proxies, timeout=10
        ).text
        print(f"✅ Внешний IP через прокси: {test_ip}")
    except Exception as e:
        print(f"❌ Не удалось проверить IP через прокси: {e}")


def _send_ntfy(message: str, priority: int) -> None:
    """Отправляет уведомление в ntfy через requests"""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"

    # 🔥 Заголовок - короткий (минимальный) или пустой
    # Используем пустой заголовок, чтобы не дублировать сообщение
    headers = {
        "Title": ".",  # <-- Минимальный заголовок (точка), можно оставить пустым
        "Priority": str(priority),
        "Tags": "warning",
        "Content-Type": "text/plain; charset=utf-8"
    }

    try:
        if _proxies:
            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers=headers,
                proxies=_proxies,
                timeout=10
            )
        else:
            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers=headers,
                timeout=10
            )

        if response.status_code != 200:
            logger.error(f"ntfy ошибка: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"ntfy не отправлено: {e}")


def ntfy_handler(message):
    """Обработчик для отправки WARNING сообщений в ntfy"""
    text = message.record["message"].strip()
    text_upper = text.upper()

    # Определяем приоритет
    priority = (
        MessagePriority.HIGH.value
        if "STRONG" in text_upper or "СИЛЬНЫЙ" in text
        else MessagePriority.DEFAULT.value
    )

    # 🔥 Отправляем ТОЛЬКО тело сообщения (без заголовка)
    _send_ntfy(message=text, priority=priority)


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
    rotation="1 MB",
    retention="7 days",
    encoding="utf-8"
)

# ── Ntfy handler: только WARNING ─────────────────────────
logger.add(
    ntfy_handler,
    level="WARNING",
    format="{message}",
)
