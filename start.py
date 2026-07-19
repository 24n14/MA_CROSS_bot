"""
Главный модуль торгового бота
Реализует MTF анализ, риск-менеджмент и управление позициями
"""
import time
import traceback
from log import logger
from config import AnalysisConfig
from run import create_mtf_analyzer, run_mtf_analysis
from DynamicRiskManager import DynamicRiskManager  # ✅ Восстановлен импорт
from PositionMonitor import PositionMonitor
from open_pos import emergency_close_position, pybit_session, execute_trade


def _extract_tf_value(timeframes, key: str, default=0):
    """Извлечение значения из старшего (первого) ТФ."""
    if timeframes and len(timeframes) > 0:
        return timeframes[0].get(key, default)
    return default


def main():
    """Главный цикл торгового бота"""

    # === ЗАГРУЗКА КОНФИГУРАЦИИ ===
    cfg = AnalysisConfig()
    SYMBOL = cfg.symbol
    MTF_TIMEFRAMES = list(cfg.mtf_timeframes)
    SLEEP_SECONDS = cfg.sleep_seconds
    RISK_PERCENT = cfg.risk_percent
    TRADING_ENABLED = cfg.trading_enabled

    BREAKEVEN_ATR_MULT = cfg.breakeven_atr_mult
    TRAIL_SL_MULT = cfg.trail_sl_mult
    TRAIL_TP_MULT = cfg.trail_tp_mult

    # === ЛОГИРОВАНИЕ СТАРТА ===
    logger.info("=" * 60)
    logger.info(f"🚀 БОТ ЗАПУЩЕН (MTF режим + торговля)")
    logger.info(f"📊 Символ: {SYMBOL}")
    logger.info(f"⏰ Таймфреймы: {MTF_TIMEFRAMES}")
    logger.info(f"🔄 Интервал опроса: {SLEEP_SECONDS // 60} мин")
    logger.info(f"💰 Риск на сделку: {RISK_PERCENT}%")
    logger.info(f"🔒 Breakeven: {BREAKEVEN_ATR_MULT}x ATR")
    logger.info(f"📈 Трейлинг SL: {TRAIL_SL_MULT}x ATR")
    logger.info(f"📈 Трейлинг TP: {TRAIL_TP_MULT}x ATR")
    logger.info("=" * 60)

    # === ИНИЦИАЛИЗАЦИЯ АНАЛИЗАТОРА ===
    try:
        mtf_analyzer = create_mtf_analyzer(cfg)
        exchange = mtf_analyzer.loader.exchange
        logger.info("✅ Анализатор создан успешно")
        logger.info("🔄 Первичная загрузка данных...")
    except Exception as e:
        logger.error(f"💥 Ошибка создания анализатора: {e}", exc_info=True)
        return

    # === ИНИЦИАЛИЗАЦИЯ РИСК-МЕНЕДЖЕРА ===
    try:
        risk_manager = DynamicRiskManager(exchange, SYMBOL)
        logger.info("✅ Риск-менеджер создан успешно")
    except Exception as e:
        logger.error(f"💥 Ошибка создания риск-менеджера: {e}", exc_info=True)
        return

    # === ПЕРЕМЕННЫЕ СОСТОЯНИЯ ===
    last_direction = 'NEUTRAL'
    position_monitor = None
    error_count = 0
    max_errors = 5
    last_price = 0
    last_atr = 0

    # === ГЛАВНЫЙ ЦИКЛ ===
    try:
        while True:
            try:
                logger.info(f"\n{'=' * 60}")
                logger.info(f"🔄 ЗАПУСК MTF АНАЛИЗА {SYMBOL}...")
                logger.info(f"{'=' * 60}")

                # === 1. ВЫПОЛНЕНИЕ MTF АНАЛИЗА ===
                analysis_data = run_mtf_analysis(cfg, mtf_analyzer=mtf_analyzer)

                if not analysis_data or not analysis_data.get('analysis'):
                    logger.error("❌ MTF анализ не вернул данных")
                    error_count += 1
                    if error_count >= max_errors:
                        logger.critical(f"⚠️ Превышено количество ошибок ({max_errors}). Перезапуск анализатора...")
                        error_count = 0
                        try:
                            mtf_analyzer = create_mtf_analyzer(cfg)
                            exchange = mtf_analyzer.loader.exchange
                            risk_manager = DynamicRiskManager(exchange, SYMBOL)
                            logger.info("✅ Анализатор и риск-менеджер пересозданы")
                        except Exception as e:
                            logger.error(f"❌ Не удалось пересоздать: {e}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                error_count = 0  # Сброс счетчика ошибок

                # === 2. ПАРСИНГ РЕЗУЛЬТАТОВ АНАЛИЗА ===
                analysis = analysis_data['analysis']

                # Новая структура из mtf_analyzer.aggregate():
                # {
                #   "symbol", "exchange", "timestamp",
                #   "higher_tf_bias": "long"/"short"/"neutral",
                #   "final_signal": -1/0/1,
                #   "final_direction": "long"/"short"/"neutral",
                #   "score": float,
                #   "confidence": float,
                #   "timeframes": [{...}, ...]
                # }
                timeframes = analysis.get('timeframes', [])
                final_signal = analysis.get('final_signal', 0)
                final_direction = analysis.get('final_direction', 'neutral')
                score = analysis.get('score', 0.0)
                confidence = analysis.get('confidence', 0.0)
                higher_tf_bias = analysis.get('higher_tf_bias', 'neutral')

                # Извлекаем close, atr, adx из старшего ТФ
                current_price = _extract_tf_value(timeframes, 'close', 0)
                current_atr = _extract_tf_value(timeframes, 'atr', 0)
                current_adx = _extract_tf_value(timeframes, 'adx', 0)

                # Маппинг направления
                if final_direction == 'long':
                    current_direction = 'BULLISH'
                elif final_direction == 'short':
                    current_direction = 'BEARISH'
                else:
                    current_direction = 'NEUTRAL'

                trigger_trade = (
                    final_signal != 0
                    and abs(score) >= cfg.min_signal_strength / 100.0
                    and confidence >= 0.3
                )
                strength = abs(score) * 100.0

                # Сохраняем для использования в мониторинге
                last_price = current_price
                last_atr = current_atr

                if current_price <= 0:
                    logger.error(f"❌ Некорректная цена: {current_price}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                logger.info(f"📊 Текущая цена: ${current_price:.2f}")
                logger.info(f"📊 ATR: ${current_atr:.2f}")
                logger.info(f"📊 ADX: {current_adx:.1f}")
                logger.info(f"📊 Направление: {current_direction}")
                logger.info(f"📊 Сила сигнала: {strength:.1f}")
                logger.info(f"📊 Сигнал на вход: {trigger_trade}")
                logger.info(f"📊 Старший ТФ: {higher_tf_bias}")
                logger.info(f"📊 Уверенность: {confidence:.2f}")

                # === 3. МОНИТОРИНГ ОТКРЫТОЙ ПОЗИЦИИ ===
                if position_monitor is not None:
                    logger.info("=" * 60)
                    logger.info("🔍 МОНИТОРИНГ ОТКРЫТОЙ ПОЗИЦИИ")
                    logger.info(f"📈 Сторона: {position_monitor.side}")
                    logger.info(f"💵 Цена входа: ${position_monitor.entry_price:.2f}")
                    logger.info(f"🔒 Текущий SL: ${position_monitor.current_sl:.2f}")
                    logger.info(f"🎯 Текущий TP: ${position_monitor.current_tp:.2f}")
                    logger.info(f"📦 Размер: {position_monitor.position_size}")
                    logger.info("=" * 60)

                    try:
                        # Обновление трейлингов и отправка на биржу
                        updates = position_monitor.update(current_price, current_atr)

                        # Проверка ошибки выполнения API запроса
                        if updates and updates.get('error') is True:
                            logger.critical("🚨 ОШИБКА: Биржа отклонила или не приняла параметры защитных SL/TP")
                            raise RuntimeError("Биржа отклонила параметры SL/TP")

                        if updates and updates.get('exchange_updated'):
                            logger.info(f"✅ Обновления на бирже отправлены: {updates}")

                        # Проверка, открыта ли еще позиция
                        if not position_monitor.is_position_open():
                            logger.info("✅ Позиция закрыта по ордеру. Мониторинг завершен.")
                            position_monitor = None
                            last_direction = 'NEUTRAL'
                            logger.info("🔄 Состояние сброшено, ожидание новых сигналов")
                        else:
                            logger.info(f"📊 Позиция удерживается, SL=${position_monitor.current_sl:.2f}")

                    except Exception as exchange_critical_error:
                        # === ЭКСТРЕННОЕ ЗАКРЫТИЕ ПОЗИЦИИ ===
                        logger.critical("=" * 60)
                        logger.critical("🚨 АВАРИЙНЫЙ СБОЙ ОБНОВЛЕНИЯ СТОПОВ")
                        logger.critical(f"❌ Причина: {exchange_critical_error}")
                        logger.critical("🚨 ЗАПУСК ПРОТОКОЛА ЭКСТРЕННОЙ ЛИКВИДАЦИИ...")
                        logger.critical("=" * 60)

                        try:
                            # Используем новую функцию экстренного закрытия из open_pos.py
                            success = emergency_close_position(
                                symbol=SYMBOL,
                                side=position_monitor.side,
                                qty=position_monitor.position_size
                            )

                            if success:
                                logger.critical("✅ ПОЗИЦИЯ ЭКСТРЕННО ЗАКРЫТА! Депозит защищен.")
                            else:
                                logger.critical("❌ ОШИБКА ЭКСТРЕННОГО ЗАКРЫТИЯ! Попытка через CCXT...")

                                # Fallback: попытка закрыть через CCXT
                                try:
                                    trade_side = 'sell' if position_monitor.side == 'long' else 'buy'
                                    exchange.create_market_order(
                                        symbol=SYMBOL,
                                        side=trade_side,
                                        amount=position_monitor.position_size
                                    )
                                    logger.critical("✅ ПОЗИЦИЯ ЗАКРЫТА ЧЕРЕЗ CCXT!")
                                except Exception as ccxt_error:
                                    logger.critical(f"💥 КАТАСТРОФА: НЕ УДАЛОСЬ ЗАКРЫТЬ ПОЗИЦИЮ: {ccxt_error}")

                        except Exception as close_catastrophe:
                            logger.critical(f"💥 КАТАСТРОФА: ОШИБКА ПРИ ЭКСТРЕННОМ ЗАКРЫТИИ: {close_catastrophe}")
                            logger.critical("⚠️ РЕКОМЕНДУЕТСЯ РУЧНОЕ ВМЕШАТЕЛЬСТВО!")

                        # Сбрасываем монитор в любом случае
                        position_monitor = None
                        last_direction = 'NEUTRAL'

                        logger.info("🔄 Состояние сброшено, ожидание новых сигналов")
                        time.sleep(SLEEP_SECONDS)
                        continue

                # === 4. ТОРГОВАЯ ЛОГИКА (ВХОД В НОВЫЕ СДЕЛКИ) ===
                if TRADING_ENABLED and position_monitor is None:
                    logger.info("=" * 60)
                    logger.info("🔍 ПРОВЕРКА СИГНАЛОВ НА ВХОД")
                    logger.info(f"📊 Направление: {current_direction}")
                    logger.info(f"📊 Триггер: {trigger_trade}")
                    logger.info(f"📊 Предыдущее направление: {last_direction}")
                    logger.info("=" * 60)

                    if trigger_trade and current_direction != 'NEUTRAL':
                        if current_direction != last_direction:
                            logger.warning(f"🔥 ОБНАРУЖЕН СИГНАЛ НА ВХОД: {current_direction}")

                            # === РАСЧЕТ SL, TP И РАЗМЕРА ПОЗИЦИИ ЧЕРЕЗ RISK MANAGER ===
                            try:
                                # 1. Получаем баланс для расчета позиции
                                balance_data = exchange.fetch_balance()
                                currency = 'USDC' if 'USDC' in SYMBOL else 'USDT'
                                account_balance = balance_data[currency]['free']

                                logger.info(f"💰 Баланс {currency}: ${account_balance:.2f}")

                                # 2. Рассчитываем SL и TP на основе ATR и ADX
                                side = 'long' if current_direction == 'BULLISH' else 'short'

                                # Получаем динамические множители
                                multipliers = risk_manager.get_dynamic_multipliers(current_atr, current_adx)
                                logger.info(f"📊 Динамические множители:")
                                logger.info(f"   Тренд: {multipliers['trend_state']}")
                                logger.info(f"   SL множитель: {multipliers['sl_multiplier']}x")
                                logger.info(f"   TP множитель: {multipliers['tp_multiplier']}x")
                                logger.info(f"   RR: 1:{multipliers['rr_ratio']}")

                                # Рассчитываем SL и TP
                                stop_loss_price, take_profit_price = risk_manager.calculate_sl_tp(
                                    entry_price=current_price,
                                    atr=current_atr,
                                    adx=current_adx,
                                    side=side
                                )

                                # 3. Рассчитываем размер позиции
                                # Получаем процент стоп-лосса от цены
                                if side == 'long':
                                    stop_loss_percent = ((current_price - stop_loss_price) / current_price) * 100
                                else:
                                    stop_loss_percent = ((stop_loss_price - current_price) / current_price) * 100

                                position_size = risk_manager.calculate_position_size(
                                    account_balance=account_balance,
                                    risk_percent=RISK_PERCENT,
                                    stop_loss_percent=stop_loss_percent,
                                    entry_price=current_price
                                )

                                if position_size <= 0:
                                    logger.error("❌ Расчетный размер позиции <= 0")
                                    time.sleep(SLEEP_SECONDS)
                                    continue

                                logger.info(f"📊 Расчетные параметры:")
                                logger.info(
                                    f"   SL: ${stop_loss_price:.2f} (дист. ${abs(current_price - stop_loss_price):.2f})")
                                logger.info(
                                    f"   TP: ${take_profit_price:.2f} (дист. ${abs(current_price - take_profit_price):.2f})")
                                logger.info(f"   Размер: {position_size:.6f}")

                                # 4. Исполнение сигнала через open_pos.py
                                result = execute_trade(
                                    exchange=exchange,
                                    symbol=SYMBOL,
                                    side=side,
                                    amount=position_size,
                                    entry_price=current_price,
                                    stop_loss_price=stop_loss_price,
                                    take_profit_price=take_profit_price
                                )

                                if result and result.get('id'):
                                    last_direction = current_direction
                                    logger.info(f"✅ СДЕЛКА ИСПОЛНЕНА УСПЕШНО: {current_direction}")

                                    # Инициализация PositionMonitor
                                    if (current_price > 0 and current_atr > 0 and
                                            stop_loss_price > 0 and take_profit_price > 0 and
                                            position_size > 0):

                                        logger.info("📊 Инициализация PositionMonitor...")
                                        logger.info(f"   Вход: ${current_price:.2f}")
                                        logger.info(f"   SL: ${stop_loss_price:.2f}")
                                        logger.info(f"   TP: ${take_profit_price:.2f}")
                                        logger.info(f"   Размер: {position_size}")

                                        position_monitor = PositionMonitor(
                                            exchange=exchange,
                                            symbol=SYMBOL,
                                            side=side,
                                            entry_price=current_price,
                                            position_size=position_size,
                                            atr=current_atr,
                                            initial_sl=stop_loss_price,
                                            initial_tp=take_profit_price,
                                            breakeven_activation_atr=BREAKEVEN_ATR_MULT,
                                            trail_sl_multiplier=TRAIL_SL_MULT,
                                            trail_tp_multiplier=TRAIL_TP_MULT
                                        )
                                        logger.info(f"✅ Мониторинг позиции {side} успешно запущен.")
                                    else:
                                        logger.error(f"❌ Ошибка инициализации PositionMonitor:")
                                        logger.error(f"   entry={current_price}, atr={current_atr}")
                                        logger.error(
                                            f"   sl={stop_loss_price}, tp={take_profit_price}, amount={position_size}")
                                else:
                                    logger.error("❌ Биржа отклонила ордер на вход.")
                                    logger.error("⚠️ Проверьте логи API для выяснения причины.")

                            except Exception as trade_error:
                                logger.error(f"💥 Ошибка исполнения сигнала: {trade_error}")
                                traceback.print_exc()
                        else:
                            logger.info(f"ℹ️ Сигнал {current_direction} уже был обработан.")
                    else:
                        if last_direction != 'NEUTRAL':
                            logger.info(f"ℹ️ Сигнал {last_direction} завершен.")
                            last_direction = 'NEUTRAL'
                        else:
                            logger.info("ℹ️ Сигналов на вход нет.")
                else:
                    if not TRADING_ENABLED:
                        logger.info("ℹ️ Торговля отключена в настройках")
                    elif position_monitor is not None:
                        logger.debug("ℹ️ Позиция уже открыта, ожидаем закрытия")

                # === 5. ОЖИДАНИЕ ДО СЛЕДУЮЩЕГО ЦИКЛА ===
                logger.info(f"\n⏳ Ожидание {SLEEP_SECONDS // 60} минут до следующего цикла...")
                logger.info("=" * 60)
                time.sleep(SLEEP_SECONDS)

            except KeyboardInterrupt:
                logger.info("🛑 Получен сигнал остановки (Ctrl+C)")
                break

            except Exception as loop_error:
                logger.error(f"❌ Ошибка в цикле: {loop_error}")
                traceback.print_exc()
                error_count += 1

                if error_count >= max_errors:
                    logger.critical(f"⚠️ Критическое количество ошибок ({max_errors}). Перезапус�� цикла...")
                    error_count = 0
                    try:
                        logger.info("🔄 Пересоздание анализатора и риск-менеджера...")
                        mtf_analyzer = create_mtf_analyzer(cfg)
                        exchange = mtf_analyzer.loader.exchange
                        risk_manager = DynamicRiskManager(exchange, SYMBOL)
                        logger.info("✅ Анализатор и риск-менеджер пересозданы успешно")
                    except Exception as e:
                        logger.error(f"❌ Не удалось пересоздать: {e}")
                        logger.critical("⚠️ РЕКОМЕНДУЕТСЯ ПЕРЕЗАПУСК БОТА!")

                time.sleep(SLEEP_SECONDS)

    except KeyboardInterrupt:
        logger.info("\n🛑 Бот остановлен пользователем.")
        logger.info("📊 Итоговое состояние:")
        if position_monitor:
            logger.info(f"   Позиция: {position_monitor.side} {position_monitor.position_size}")
            logger.info(f"   Вход: ${position_monitor.entry_price:.2f}")
            logger.info(f"   Текущий SL: ${position_monitor.current_sl:.2f}")
            logger.info(f"   Текущий TP: ${position_monitor.current_tp:.2f}")
        else:
            logger.info("   Позиций нет")
        logger.info("👋 До свидания!")

    except Exception as e:
        logger.error(f"💥 Критическая ошибка главного цикла: {e}")
        traceback.print_exc()
        logger.critical("⚠️ БОТ АВАРИЙНО ОСТАНОВЛЕН! ТРЕБУЕТСЯ ВНИМАНИЕ!")

    # === ФИНАЛЬНАЯ ОЧИСТКА ===
    logger.info("🧹 Завершение работы бота...")
    try:
        if position_monitor and position_monitor.is_position_open():
            logger.warning("⚠️ Обнаружена открытая позиция при завершении!")
            logger.info("🔄 Попытка закрыть позицию...")
            emergency_close_position(
                symbol=SYMBOL,
                side=position_monitor.side,
                qty=position_monitor.position_size
            )
    except Exception as cleanup_error:
        logger.error(f"❌ Ошибка при очистке: {cleanup_error}")

    logger.info("✅ Бот завершил работу.")


if __name__ == "__main__":
    main()