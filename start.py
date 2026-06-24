"""
Точка входа. Мониторинг рынка 15m + MTF при сигнале.
"""

import time
import traceback
from log import logger
from config import Config
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from mtf_analyzer import MultiTimeframeAnalyzer


def is_entry_signal(signal: str) -> bool:
    """Проверка, является ли сигнал входом в рынок"""
    signal_upper = str(signal).upper()
    return any(kw in signal_upper for kw in ['STRONG', 'REVERSAL'])


def format_mtf_message(analysis: dict, symbol: str) -> str:
    """Форматирование MTF результата для лога"""
    if not analysis:
        return "❌ Ошибка MTF анализа"

    final = analysis['final_signal']
    details = analysis['mtf_details']

    lines = []
    emoji = '🟢' if final['direction'] == 'BULLISH' else '🔴' if final['direction'] == 'BEARISH' else '⚪'
    lines.append(f"{emoji} {symbol} — {final['direction']}")
    lines.append(
        f"Уверенность: {final['confidence']} | Сила: {final['strength']:.1f} | Согласие ТФ: {final['agreement']}%")
    lines.append("─" * 30)

    for item in details:
        tf = item['timeframe']
        signal = item['signal']
        lines.append(f"  {tf}: {signal} | ${item['close']:.2f}")

    return "\n".join(lines)


def main():
    # ==========================================
    # НАСТРОЙКИ
    # ==========================================
    SYMBOL = 'BTC/USDT'
    EXCHANGE = 'binance'
    MONITOR_TIMEFRAME = '15m'
    MTF_TIMEFRAMES = ['15m', '1h', '4h']
    LIMIT = 300
    SLEEP_SECONDS = 900  # 15 минут

    logger.info("=" * 50)
    logger.info(f"🚀 Бот запущен: {SYMBOL} | Мониторинг {MONITOR_TIMEFRAME} | MTF {MTF_TIMEFRAMES}")
    logger.info("=" * 50)

    loader = ExchangeDataLoader(EXCHANGE)
    monitor_config = Config.for_timeframe(MONITOR_TIMEFRAME)
    monitor_indicator = AdvancedTrendSignalIndicator(monitor_config)

    last_signal = None

    try:
        while True:
            # ─── Анализ 15m ───
            df = loader.fetch_ohlcv(SYMBOL, MONITOR_TIMEFRAME, LIMIT)

            if df is None:
                logger.warning("Нет данных, ждем следующий цикл")
                time.sleep(SLEEP_SECONDS)
                continue

            result = monitor_indicator.generate_signal(df)
            current_signal = result['Signal'].iloc[-1]
            current_close = result['close'].iloc[-1]

            logger.info(f"15m: ${current_close:.2f} | {current_signal} | ожидание {SLEEP_SECONDS // 60} мин")

            signal_changed = (last_signal is None) or (last_signal != current_signal)

            # ─── Сигнал входа → MTF ───
            if signal_changed and is_entry_signal(current_signal):
                logger.info(f"⚡ Сигнал: {current_signal} → запуск MTF")

                mtf = MultiTimeframeAnalyzer(
                    timeframes=MTF_TIMEFRAMES,
                    exchange_name=EXCHANGE,
                    symbol=SYMBOL
                )
                analysis = mtf.load_and_analyze(limit=LIMIT)

                if analysis:
                    mtf.print_analysis(analysis)
                    message = format_mtf_message(analysis, SYMBOL)
                    # Вот здесь — logger.warning сам отправит в ntfy!
                    logger.warning(message)
                else:
                    logger.error("MTF анализ не удался")

            if signal_changed:
                last_signal = current_signal

            time.sleep(SLEEP_SECONDS)

    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
