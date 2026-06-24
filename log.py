"""
Модуль логирования.
Логирует в консоль, файл и отправляет WARNING в ntfy.
"""

import sys
from pathlib import Path
from loguru import logger
from python_ntfy import NtfyClient, MessagePriority

# ── Ntfy ────────────────────────────────────────────────
NTFY_TOPIC = "ma_cross_24n14"
ntfy_client = NtfyClient(topic=NTFY_TOPIC)


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

    priority = MessagePriority.HIGH if "STRONG" in text_upper else MessagePriority.DEFAULT

    try:
        ntfy_client.send(message=text, title=title, priority=priority)
    except Exception:  # noqa
        pass


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
