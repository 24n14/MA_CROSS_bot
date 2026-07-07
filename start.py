"""
Точка входа. Бот с MTF анализом и автоматической торговлей.
"""
import time
import traceback
from log import logger
from config import AnalysisConfig
from run import create_mtf_analyzer, run_mtf_analysis
from risk_manager import DynamicRiskManager, PositionMonitor


def main():
    # ==========================================
    # НАСТРОЙКИ (из config.py)
    # ==========================================
    cfg = AnalysisConfig()

    SYMBOL = cfg.symbol
    MTF_TIMEFRAMES = list(cfg.mtf_timeframes)
    SLEEP_SECONDS = 300  # 5 минут между циклами

    # Параметры торговли
    RISK_PERCENT = 2.0  # Риск на сделку в %
    TRADING_ENABLED = True  # Включить/выключить торговлю

    # Параметры мониторинга позиции
    BREAKEVEN_ATR_MULT = 1.5   # Активация безубытка при 1.5x ATR прибыли
    TRAIL_SL_MULT = 1.5        # Трейлинг стопа на 1.5x ATR от best_price
    TRAIL_TP_MULT = None       # Трейлинг TP отключён (None)

    logger.info("=" * 50)
    logger.info(f"🚀 Бот запущен (MTF режим + торговля): {SYMBOL}")
    logger.info(f"📊 Таймфреймы: {MTF_TIMEFRAMES}")
    logger.info(f"🕐 Интервал опроса: {SLEEP_SECONDS}с")
    logger.info(f"💰 Риск на сделку: {RISK_PERCENT}%")
    logger.info(f"🔒 Breakeven: {BREAKEVEN_ATR_MULT}x ATR")
    logger.info(f"🔺 Трейлинг SL: {TRAIL_SL_MULT}x ATR")
    logger.info("=" * 50)

    # Создаём анализатор
    mtf_analyzer = create_mtf_analyzer(cfg)

    # Получаем экземпляр биржи из анализатора
    exchange = mtf_analyzer.loader.exchange

    logger.info("✅ Анализатор создан. Первичная загрузка данных...")

    # Для отслеживания последнего сигнала (чтобы не дублировать входы)
    last_direction = 'NEUTRAL'

    # Монитор открытой позиции (None — позиции нет)
    position_monitor = None

    try:
        while True:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"🔄 Запуск MTF анализа {SYMBOL}...")
            logger.info(f"{'=' * 60}")

            # Анализ
            analysis_data = run_mtf_analysis(cfg, mtf_analyzer=mtf_analyzer)

            if analysis_data and analysis_data['analysis']:
                analysis = analysis_data['analysis']
                mtf = analysis_data['analyzer']
                mtf.print_analysis(analysis)

                # Финальный сигнал
                final = analysis['final_signal']

                # --- МОНИТОРИНГ ОТКРЫТОЙ ПОЗИЦИИ ---
                if position_monitor is not None:
                    current_price = final.get('close', 0)
                    new_atr = final.get('atr', None)

                    if current_price > 0:
                        logger.info(f"\n{'─' * 40}")
                        logger.info(f"📡 Мониторинг позиции...")
                        logger.info(f"   Цена: ${current_price:.2f}")
                        logger.info(f"   Вход: ${position_monitor.entry_price:.2f}")
                        logger.info(f"   SL:   ${position_monitor.current_sl:.2f}")
                        logger.info(f"   TP:   ${position_monitor.current_tp:.2f}")
                        logger.info(f"   BE:   {'✅' if position_monitor.breakeven_activated else '❌'}")

                        # Обновляем SL/TP
                        updates = position_monitor.update(current_price, new_atr)

                        if updates:
                            logger.info(f"📊 Обновления позиции: {updates}")

                        # Проверяем, открыта ли ещё позиция
                        if not position_monitor.is_position_open():
                            logger.info("🔴 Позиция закрыта. Мониторинг остановлен.")
                            position_monitor = None
                            last_direction = 'NEUTRAL'
                        else:
                            logger.info(f"📡 Позиция активна, SL=${position_monitor.current_sl:.2f}")
                    else:
                        logger.warning("⚠️ Нет данных о текущей цене для мониторинга")

                # --- ТОРГОВАЯ ЛОГИКА (только если нет открытой позиции) ---
                if TRADING_ENABLED and final['trigger_trade'] and position_monitor is None:
                    current_direction = final['direction']

                    # Проверяем, не повторяем ли мы тот же сигнал
                    if current_direction != last_direction:
                        logger.warning(f"🔥 НОВЫЙ СИГНАЛ: {current_direction}")

                        # Исполняем сделку
                        result = mtf_analyzer.loader.execute_trade_signal(
                            signal_data={
                                'direction': current_direction,
                                'strength': final['strength'],
                                'atr': final.get('atr', 0),
                                'adx': final.get('adx', 0),
                                'close': final.get('close', 0),
                                'trigger_trade': True,
                                'symbol': SYMBOL
                            },
                            risk_percent=RISK_PERCENT
                        )

                        if result and result.get('order'):
                            last_direction = current_direction
                            logger.info(f"✅ Сделка исполнена: {current_direction}")

                            # Создаём монитор позиции
                            side = 'long' if current_direction == 'BULLISH' else 'short'
                            entry_price = final.get('close', 0)
                            atr = final.get('atr', 0)
                            sl = result.get('stop_loss', 0)
                            tp = result.get('take_profit', 0)

                            if entry_price > 0 and atr > 0 and sl > 0 and tp > 0:
                                position_monitor = PositionMonitor(
                                    exchange=exchange,
                                    symbol=SYMBOL,
                                    side=side,
                                    entry_price=entry_price,
                                    initial_sl=sl,
                                    initial_tp=tp,
                                    atr=atr,
                                    breakeven_activation_atr=BREAKEVEN_ATR_MULT,
                                    trail_sl_multiplier=TRAIL_SL_MULT,
                                    trail_tp_multiplier=TRAIL_TP_MULT
                                )
                                logger.info(f"📊 PositionMonitor запущен для {side} @ ${entry_price:.2f}")
                        else:
                            logger.error("❌ Ошибка исполнения сделки")
                    else:
                        logger.info(f"⏭️ Сигнал {current_direction} уже был обработан")
                else:
                    # Сбрасываем направление при отсутствии сигнала (если нет позиции)
                    if last_direction != 'NEUTRAL' and position_monitor is None:
                        logger.info(f"🔄 Сигнал {last_direction} завершен")
                        last_direction = 'NEUTRAL'

                # Вывод информации
                emoji = '🟢' if final['direction'] == 'BULLISH' else '🔴' if final['direction'] == 'BEARISH' else '⚪'
                logger.info(
                    f"{emoji} {SYMBOL} — {final['direction']} | "
                    f"Уверенность: {final['confidence']} | "
                    f"Сила: {final['strength']:.1f} | "
                    f"Согласие: {final['agreement']}%"
                )

                # Если есть данные для TP/SL - выводим
                if 'atr' in final and 'adx' in final:
                    risk_mgr = DynamicRiskManager(exchange, SYMBOL)
                    multipliers = risk_mgr.get_dynamic_multipliers(
                        atr=final['atr'],
                        adx=final['adx']
                    )
                    logger.info(
                        f"📊 Параметры риска: ATR=${final['atr']:.2f} | "
                        f"ADX={final['adx']:.1f} | "
                        f"SL множ.: {multipliers['sl_multiplier']}x | "
                        f"TP множ.: {multipliers['tp_multiplier']}x | "
                        f"RR: 1:{multipliers['rr_ratio']}"
                    )

            else:
                logger.error("❌ MTF анализ не удался")

            logger.info(f"⏳ Ожидание {SLEEP_SECONDS // 60} мин до следующего цикла...")
            time.sleep(SLEEP_SECONDS)

    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()