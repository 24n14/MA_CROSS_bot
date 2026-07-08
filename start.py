import time
import traceback
from log import logger
from config import AnalysisConfig
from run import create_mtf_analyzer, run_mtf_analysis
from risk_manager import DynamicRiskManager, PositionMonitor


def main():
    cfg = AnalysisConfig()
    SYMBOL = cfg.symbol
    MTF_TIMEFRAMES = list(cfg.mtf_timeframes)
    SLEEP_SECONDS = cfg.sleep_seconds

    RISK_PERCENT = cfg.risk_percent
    TRADING_ENABLED = cfg.trading_enabled

    BREAKEVEN_ATR_MULT = cfg.breakeven_atr_mult
    TRAIL_SL_MULT = cfg.trail_sl_mult
    TRAIL_TP_MULT = cfg.trail_tp_mult

    logger.info("=" * 50)
    logger.info(f"🤖 Бот запущен (MTF режим + торговля): {SYMBOL}")
    logger.info(f"📊 Таймфреймы: {MTF_TIMEFRAMES}")
    logger.info(f"⏱️ Интервал опроса: {SLEEP_SECONDS}c")
    logger.info(f"💰 Риск на сделку: {RISK_PERCENT}%")
    logger.info(f"🛡️ Breakeven: {BREAKEVEN_ATR_MULT}x ATR")
    logger.info(f"📈 Трейлинг SL: {TRAIL_SL_MULT}x ATR")
    logger.info("=" * 50)

    mtf_analyzer = create_mtf_analyzer(cfg)
    exchange = mtf_analyzer.loader.exchange
    logger.info("✅ Анализатор создан. Первичная загрузка данных...")

    last_direction = 'NEUTRAL'
    position_monitor = None

    try:
        while True:
            logger.info(f"\n{'=' * 60}\n🔄 Запуск MTF анализа {SYMBOL}...\n{'=' * 60}")

            analysis_data = run_mtf_analysis(cfg, mtf_analyzer=mtf_analyzer)
            if not analysis_data or not analysis_data.get('analysis'):
                logger.error("❌ MTF анализ не вернул данных")
                time.sleep(SLEEP_SECONDS)
                continue

            analysis = analysis_data['analysis']
            mtf = analysis_data['analyzer']
            mtf.print_analysis(analysis)

            final = analysis['final_signal']

            # --- СИСТЕМА МОНИТОРИНГА ОТКРЫТОЙ ПОЗИЦИИ (FAIL-SAFE) ---
            if position_monitor is not None:
                current_price = final.get('close', 0)
                new_atr = final.get('atr', None)

                if current_price > 0:
                    logger.info(f"\n{'-' * 40}\n🔍 Мониторинг активной позиции...")
                    logger.info(f"Цена: ${current_price:.2f} | Вход: ${position_monitor.entry_price:.2f}")
                    logger.info(
                        f"Текущий SL: ${position_monitor.current_sl:.2f} | TP: ${position_monitor.current_tp:.2f}")

                    try:
                        # Обновление трейлингов и отправка на биржу
                        updates = position_monitor.update(current_price, new_atr)

                        # Если метод вернул ошибку выполнения API запроса, бросаем исключение
                        if updates and updates.get('error') is True:
                            raise RuntimeError("Биржа отклонила или не приняла параметры защитных SL/TP")

                    except Exception as exchange_critical_error:
                        logger.critical(
                            f"🚨 АВАРИЙНЫЙ СБОЙ: Не удалось обновить стопы! Причина: {exchange_critical_error}")
                        logger.critical("🚨 ЗАПУСК ПРОТОКОЛА ЭКСТРЕННОЙ РЫНОЧНОЙ ЛИКВИДАЦИИ ДЕПОЗИТА...")

                        try:
                            trade_side = 'sell' if position_monitor.side == 'long' else 'buy'
                            # Срочно выходим по маркету
                            emergency_order = exchange.create_order(
                                symbol=SYMBOL, type='market', side=trade_side,
                                amount=position_monitor.position_size, params={'reduceOnly': True}
                            )
                            logger.critical(
                                f"✅ Позиция принудительно закрыта по рынку! ID ордера: {emergency_order['id']}. Депозит защищен.")
                        except Exception as close_catastrophe:
                            logger.critical(
                                f"💀 КАТАСТРОФА: РОБОТ НЕ СМОГ ЗАКРЫТЬ ПОЗИЦИЮ ДАЖЕ ПО РЫНКУ: {close_catastrophe}")

                        # Сбрасываем монитор в любом случае, блокируя дальнейшие итерации трейлинга
                        position_monitor = None
                        last_direction = 'NEUTRAL'
                        time.sleep(SLEEP_SECONDS)
                        continue

                    if updates and updates.get('exchange_updated'):
                        logger.info(f"📈 Обновления на бирже отправлены: {updates}")

                    if not position_monitor.is_position_open():
                        logger.info("🔴 Позиция закрыта по ордеру. Мониторинг завершен.")
                        position_monitor = None
                        last_direction = 'NEUTRAL'
                    else:
                        logger.info(f"🟢 Позиция удерживается, SL=${position_monitor.current_sl:.2f}")
                else:
                    logger.warning("⚠️ Нет валидных данных о цене для мониторинга")

            # --- ТОРГОВАЯ ЛОГИКА (ВХОД В НОВЫЕ СДЕЛКИ) ---
            if TRADING_ENABLED and final.get('trigger_trade') and position_monitor is None:
                current_direction = final['direction']

                if current_direction != last_direction:
                    logger.warning(f"⚡ ОБНАРУЖЕН СИГНАЛ НА ВХОД: {current_direction}")

                    result = mtf_analyzer.loader.execute_trade_signal(
                        signal_data={
                            'direction': current_direction, 'strength': final['strength'],
                            'atr': final.get('atr', 0), 'adx': final.get('adx', 0),
                            'close': final.get('close', 0), 'trigger_trade': True, 'symbol': SYMBOL
                        },
                        risk_percent=RISK_PERCENT
                    )

                    if result and result.get('order'):
                        last_direction = current_direction
                        logger.info(f"✅ Сделка исполнена успешно: {current_direction}")

                        side = 'long' if current_direction == 'BULLISH' else 'short'
                        entry_price = final.get('close', 0)
                        atr = final.get('atr', 0)
                        sl = result.get('stop_loss', 0)
                        tp = result.get('take_profit', 0)

                        # Вытягиваем фактический объем, который открыла биржа
                        executed_amount = float(result['order'].get('amount', 0))

                        if entry_price > 0 and atr > 0 and sl > 0 and tp > 0 and executed_amount > 0:
                            position_monitor = PositionMonitor(
                                exchange=exchange, symbol=SYMBOL, side=side, entry_price=entry_price,
                                initial_sl=sl, initial_tp=tp, atr=atr, position_size=executed_amount,
                                # Передаем лот в монитор
                                breakeven_activation_atr=BREAKEVEN_ATR_MULT,
                                trail_sl_multiplier=TRAIL_SL_MULT, trail_tp_multiplier=TRAIL_TP_MULT
                            )
                            logger.info(f"🎯 Мониторинг позиции {side} успешно запущен.")
                        else:
                            logger.error("❌ Ошибка инициализации PositionMonitor: нулевые параметры ордера.")
                    else:
                        logger.error("❌ Биржа отклонила ордер на вход.")
                else:
                    logger.info(f"ℹ️ Сигнал {current_direction} уже был обработан.")
            elif position_monitor is None:
                if last_direction != 'NEUTRAL':
                    logger.info(f"⏹️ Сигнал {last_direction} завершен.")
                last_direction = 'NEUTRAL'

            logger.info(f"⏳ Ожидание {SLEEP_SECONDS // 60} мин до следующего цикла...")
            time.sleep(SLEEP_SECONDS)

    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем руками.")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка главного цикла: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()