"""
Точка входа. Мониторинг рынка 15m + MTF при сигнале.
"""
import time
import traceback
from log import logger
from config import Config, AnalysisConfig
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from run import run_mtf_analysis, print_mtf_result


def timeframe_to_seconds(tf: str) -> int:
    """Конвертировать таймфрейм в секунды для интервала опроса."""
    multipliers = {
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    value = int(tf[:-1])
    unit = tf[-1]
    return value * multipliers.get(unit, 60)


def is_entry_signal(signal: str, strength: float = 0, raw_direction: str = 'neutral') -> bool:
    """
    Проверка, является ли сигнал входом в рынок.

    Args:
        signal: отфильтрованный сигнал (Neutral, Bullish и т.д.)
        strength: сила сигнала (-100..100)
        raw_direction: сырое направление тренда ('up', 'down', 'neutral')

    Returns:
        True если нужно запустить MTF анализ
    """
    signal_upper = str(signal).upper()

    # 1. Если сигнал уже содержит ключевые слова
    if any(kw in signal_upper for kw in ['STRONG', 'REVERSAL']):
        logger.debug(f"✅ Сигнал '{signal}' — содержит ключевое слово")
        return True

    # 2. Если сигнал 'Bullish' или 'Bearish' (без STRONG, но все равно значимый)
    if signal in ['Bullish', 'Bearish'] and abs(strength) >= 30:
        logger.debug(f"✅ Сигнал '{signal}' — moderate с силой {strength}")
        return True

    # 3. НОВОЕ: Если сырая сила >= 50 и есть четкое направление
    if abs(strength) >= 50 and raw_direction in ['up', 'down']:
        logger.debug(f"✅ Сигнал '{signal}' — сила {strength} > 50, направление {raw_direction}")
        return True

    logger.debug(f"❌ Сигнал '{signal}' (сила={strength}, направление={raw_direction}) — пропущен")
    return False


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
    # НАСТРОЙКИ (из config.py)
    # ==========================================
    cfg = AnalysisConfig()

    SYMBOL = cfg.symbol
    EXCHANGE = cfg.exchange
    MONITOR_TIMEFRAME = cfg.monitor_timeframe
    MTF_TIMEFRAMES = list(cfg.mtf_timeframes)
    LIMIT = cfg.limit
    SLEEP_SECONDS = timeframe_to_seconds(MONITOR_TIMEFRAME)

    logger.info("=" * 50)
    logger.warning(f"🚀 Бот запущен: {SYMBOL}")
    logger.warning(f"📊 Мониторинг: {MONITOR_TIMEFRAME} | MTF: {MTF_TIMEFRAMES}")
    logger.info(f"🕐 Интервал: {SLEEP_SECONDS}с ({SLEEP_SECONDS // 60} мин)")
    logger.info("=" * 50)

    loader = ExchangeDataLoader(EXCHANGE)
    monitor_config = Config.for_timeframe(MONITOR_TIMEFRAME)
    monitor_indicator = AdvancedTrendSignalIndicator(monitor_config)

    last_signal = None

    try:
        while True:
            # ─── Анализ таймфрейма мониторинга ───
            df = loader.fetch_ohlcv(SYMBOL, MONITOR_TIMEFRAME, LIMIT)

            if df is None:
                logger.info("Нет данных, ждем следующий цикл")
                time.sleep(SLEEP_SECONDS)
                continue

            result = monitor_indicator.generate_signal(df)
            current_signal = result['Signal'].iloc[-1]
            current_close = result['close'].iloc[-1]
            current_strength = result['Signal_Strength'].iloc[-1]
            current_trend_state = result['Trend_State'].iloc[-1]
            current_raw_direction = result['Raw_Direction'].iloc[-1]  # НОВОЕ
            current_raw_signal = result['Raw_Signal'].iloc[-1]  # НОВОЕ
            current_ma = result['MA'].iloc[-1] if 'MA' in result.columns else 0
            current_ema = result['EMA'].iloc[-1] if 'EMA' in result.columns else 0
            current_adx = result['ADX'].iloc[-1] if 'ADX' in result.columns else 0
            current_atr = result['ATR'].iloc[-1] if 'ATR' in result.columns else 0
            current_ma_angle = result['MA_Angle_Final'].iloc[-1] if 'MA_Angle_Final' in result.columns else 0

            # Эмодзи для сигнала
            signal_emoji = '🟢' if 'BULLISH' in str(current_signal).upper() else '🔴' if 'BEARISH' in str(
                current_signal).upper() else '⚪'

            # Эмодзи для тренда
            trend_emoji = '📈' if 'up' in str(current_trend_state).lower() else '📉' if 'down' in str(
                current_trend_state).lower() else '➡️'
            # Форматированный вывод
            logger.info(f"{'─' * 60}")
            logger.warning(f"{signal_emoji} {MONITOR_TIMEFRAME} | {current_signal:<20} | ${current_close:<.2f}")
            logger.warning(f"{trend_emoji} Тренд: {current_trend_state:<20} | Сила сигнала: {current_strength:>+.1f}")
            logger.warning(f"📐 Угол MA: {current_ma_angle:>+.1f}° | ADX: {current_adx:<.1f} | ATR: ${current_atr:<.2f}")
            logger.warning(f"📊 MA: ${current_ma:<.2f} | EMA: ${current_ema:<.2f}")
            logger.info(f"{'─' * 60}")

            logger.info(
                f"{MONITOR_TIMEFRAME}: ${current_close:.2f} | {current_signal} | ожидание {SLEEP_SECONDS // 60} мин")
            signal_changed = (last_signal is None) or (last_signal != current_signal)

            # ─── Сигнал входа → MTF ───
            if signal_changed and is_entry_signal(
                    signal=current_signal,
                    strength=current_strength,
                    raw_direction=current_raw_direction
            ):
                logger.info(f"⚡ Сигнал: {current_signal} (сила={current_strength}, "
                            f"направление={current_raw_direction}) → запуск MTF")
                analysis_data = run_mtf_analysis(cfg)

                if analysis_data and analysis_data['analysis']:
                    analysis = analysis_data['analysis']
                    mtf = analysis_data['analyzer']
                    mtf.print_analysis(analysis)
                    message = format_mtf_message(analysis, SYMBOL)
                    print_mtf_result(analysis_data, cfg)
                    logger.warning(message)  # Отправится в ntfy
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
