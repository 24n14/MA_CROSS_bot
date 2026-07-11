import time
import traceback
from log import logger
from config import AnalysisConfig
from run import create_mtf_analyzer, run_mtf_analysis
from DynamicRiskManager import DynamicRiskManager
from PositionMonitor import PositionMonitor

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

    # Логирование только один раз
    logger.info("=" * 50)
    logger.info(f"Бот запущен (MTF режим + торговля): {SYMBOL}")
    logger.info(f"Таймфреймы: {MTF_TIMEFRAMES}")
    logger.info(f"Интервал опроса: {SLEEP_SECONDS}c")
    logger.info(f"Риск на сделку: {RISK_PERCENT}%")
    logger.info(f"Breakeven: {BREAKEVEN_ATR_MULT}x ATR")
    logger.info(f"Трейлинг SL: {TRAIL_SL_MULT}x ATR")
    logger.info(f"Трейлинг TP: {TRAIL_TP_MULT}x ATR")
    logger.info("=" * 50)

    # Создание анализатора
    mtf_analyzer = create_mtf_analyzer(cfg)
    exchange = mtf_analyzer.loader.exchange
    logger.info("Анализатор создан. Первичная загрузка данных...")

    last_direction = 'NEUTRAL'
    position_monitor = None
    error_count = 0
    max_errors = 5

    try:
        while True:
            try:
                logger.info(f"\n{'=' * 60}\nЗапуск MTF анализа {SYMBOL}...\n{'=' * 60}")

                # Запуск анализа
                analysis_data = run_mtf_analysis(cfg, mtf_analyzer=mtf_analyzer)

                if not analysis_data or not analysis_data.get('analysis'):
                    logger.error("MTF анализ не вернул данных")
                    error_count += 1
                    if error_count >= max_errors:
                        logger.critical(f"Превышено количество ошибок ({max_errors}). Перезапуск...")
                        error_count = 0
                        # Пересоздаем анализатор
                        mtf_analyzer = create_mtf_analyzer(cfg)
                        exchange = mtf_analyzer.loader.exchange
                    time.sleep(SLEEP_SECONDS)
                    continue

                error_count = 0  # Сброс счетчика ошибок

                analysis = analysis_data['analysis']
                mtf = analysis_data['analyzer']
                mtf.print_analysis(analysis)

                final = analysis['final_signal']

                # Проверка наличия необходимых данных
                if not final:
                    logger.error("Нет финального сигнала")
                    time.sleep(SLEEP_SECONDS)
                    continue

                current_price = final.get('close', 0)
                if current_price <= 0:
                    logger.error(f"Некорректная цена: {current_price}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # --- СИСТЕМА МОНИТОРИНГА ОТКРЫТОЙ ПОЗИЦИИ (FAIL-SAFE) ---
                if position_monitor is not None:
                    new_atr = final.get('atr', None)

                    logger.info(f"Мониторинг позиции...")
                    logger.info(f"Цена входа: ${position_monitor.entry_price:.2f}")
                    logger.info(f"Текущий SL: ${position_monitor.current_sl:.2f} | TP: ${position_monitor.current_tp:.2f}")

                    try:
                        # Обновление трейлингов и отправка на биржу
                        updates = position_monitor.update(current_price, new_atr)

                        # Если метод вернул ошибку выполнения API запроса
                        if updates and updates.get('error') is True:
                            raise RuntimeError("Биржа отклонила или не приняла параметры защитных SL/TP")

                        if updates and updates.get('exchange_updated'):
                            logger.info(f"Обновления на бирже отправлены: {updates}")

                    except Exception as exchange_critical_error:
                        logger.critical(f"АВАРИЙНЫЙ СБОЙ: Не удалось обновить стопы! Причина: {exchange_critical_error}")
                        logger.critical("ЗАПУСК ПРОТОКОЛА ЭКСТРЕННОЙ РЫНОЧНОЙ ЛИКВИДАЦИИ ДЕПОЗИТА...")

                        try:
                            trade_side = 'sell' if position_monitor.side == 'long' else 'buy'
                            # Срочно выходим по маркету
                            emergency_order = exchange.create_order(
                                symbol=SYMBOL,
                                type='market',
                                side=trade_side,
                                amount=position_monitor.position_size,
                                params={'reduceOnly': True}
                            )
                            logger.critical(f"Позиция принудительно закрыта по рынку! ID ордера: {emergency_order['id']}. Депозит защищен.")

                        except Exception as close_catastrophe:
                            logger.critical(f"КАТАСТРОФА: РОБОТ НЕ СМОГ ЗАКРЫТЬ ПОЗИЦИЮ ДАЖЕ ПО РЫНКУ: {close_catastrophe}")

                        # Сбрасываем монитор в любом случае
                        position_monitor = None
                        last_direction = 'NEUTRAL'
                        time.sleep(SLEEP_SECONDS)
                        continue

                    # Проверка, открыта ли еще позиция
                    if not position_monitor.is_position_open():
                        logger.info("Позиция закрыта по ордеру. Мониторинг завершен.")
                        position_monitor = None
                        last_direction = 'NEUTRAL'
                    else:
                        logger.info(f"Позиция удерживается, SL=${position_monitor.current_sl:.2f}")

                # --- ТОРГОВАЯ ЛОГИКА (ВХОД В НОВЫЕ СДЕЛКИ) ---
                if TRADING_ENABLED and position_monitor is None:
                    trigger_trade = final.get('trigger_trade', False)
                    current_direction = final.get('direction', 'NEUTRAL')

                    if trigger_trade and current_direction != 'NEUTRAL':
                        if current_direction != last_direction:
                            logger.warning(f"ОБНАРУЖЕН СИГНАЛ НА ВХОД: {current_direction}")

                            # Подготовка данных для сигнала
                            signal_data = {
                                'direction': current_direction,
                                'strength': final.get('strength', 0),
                                'atr': final.get('atr', 0),
                                'adx': final.get('adx', 0),
                                'close': current_price,
                                'trigger_trade': True,
                                'symbol': SYMBOL
                            }

                            # Исполнение сигнала
                            result = mtf_analyzer.loader.execute_trade_signal(
                                signal_data=signal_data,
                                risk_percent=RISK_PERCENT
                            )

                            if result and result.get('order'):
                                last_direction = current_direction
                                logger.info(f"СДЕЛКА ИСПОЛНЕНА УСПЕШНО: {current_direction}")

                                side = 'long' if current_direction == 'BULLISH' else 'short'
                                entry_price = current_price
                                atr = final.get('atr', 0)

                                # Получаем SL и TP из результата
                                sl = result.get('stop_loss', 0)
                                tp = result.get('take_profit', 0)

                                # Вытягиваем фактический объем
                                executed_amount = float(result['order'].get('amount', 0))

                                # Проверка всех необходимых параметров
                                if (entry_price > 0 and atr > 0 and sl > 0 and
                                    tp > 0 and executed_amount > 0):

                                    # Исправлено: добавлена запятая между параметрами
                                    position_monitor = PositionMonitor(
                                        exchange=exchange,
                                        symbol=SYMBOL,
                                        side=side,
                                        entry_price=entry_price,
                                        position_size=executed_amount,  # Добавлен обязательный параметр
                                        atr=atr,
                                        initial_sl=sl,
                                        initial_tp=tp,
                                        breakeven_activation_atr=BREAKEVEN_ATR_MULT,
                                        trail_sl_multiplier=TRAIL_SL_MULT,  # Исправлено: было TRAIL_TP_MULT
                                        trail_tp_multiplier=TRAIL_TP_MULT
                                    )
                                    logger.info(f"Мониторинг позиции {side} успешно запущен.")
                                else:
                                    logger.error(f"Ошибка инициализации PositionMonitor: "
                                                f"entry={entry_price}, atr={atr}, sl={sl}, tp={tp}, amount={executed_amount}")
                            else:
                                logger.error("Биржа отклонила ордер на вход.")
                        else:
                            logger.info(f"Сигнал {current_direction} уже был обработан.")
                    else:
                        if last_direction != 'NEUTRAL':
                            logger.info(f"Сигнал {last_direction} завершен.")
                            last_direction = 'NEUTRAL'
                else:
                    if not TRADING_ENABLED:
                        logger.info("Торговля отключена в настройках")
                    elif position_monitor is not None:
                        logger.debug("Позиция уже открыта, ожидаем закрытия")

                # Ожидание до следующего цикла
                logger.info(f"Ожидание {SLEEP_SECONDS // 60} мин до следующего цикла...")
                time.sleep(SLEEP_SECONDS)

            except Exception as loop_error:
                logger.error(f"Ошибка в цикле: {loop_error}")
                traceback.print_exc()
                error_count += 1

                if error_count >= max_errors:
                    logger.critical(f"Критическое количество ошибок ({max_errors}). Перезапуск цикла...")
                    error_count = 0
                    # Пересоздаем анализатор
                    try:
                        mtf_analyzer = create_mtf_analyzer(cfg)
                        exchange = mtf_analyzer.loader.exchange
                    except Exception as e:
                        logger.error(f"Не удалось пересоздать анализатор: {e}")

                time.sleep(SLEEP_SECONDS)

    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
    except Exception as e:
        logger.error(f"Критическая ошибка главного цикла: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()