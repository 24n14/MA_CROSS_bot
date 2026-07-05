"""
Точка входа. Бот с MTF анализом и автоматической торговлей.
"""
import time
import traceback
from log import logger
from config import AnalysisConfig
from run import create_mtf_analyzer, run_mtf_analysis  # print_mtf_result


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

    logger.info("=" * 50)
    logger.info(f"🚀 Бот запущен (MTF режим + торговля): {SYMBOL}")
    logger.info(f"📊 Таймфреймы: {MTF_TIMEFRAMES}")
    logger.info(f"🕐 Интервал опроса: {SLEEP_SECONDS}с")
    logger.info(f"💰 Риск на сделку: {RISK_PERCENT}%")
    logger.info("=" * 50)

    # Создаём анализатор
    mtf_analyzer = create_mtf_analyzer(cfg)

    # Получаем экземпляр биржи из анализатора
    exchange = mtf_analyzer.loader.exchange

    logger.info("✅ Анализатор создан. Первичная загрузка данных...")

    # Для отслеживания последнего сигнала (чтобы не дублировать входы)
    last_direction = 'NEUTRAL'

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

                # Торговая логика
                if TRADING_ENABLED and final['trigger_trade']:
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

                        if result:
                            last_direction = current_direction
                            logger.info(f"✅ Сделка исполнена: {current_direction}")
                        else:
                            logger.error("❌ Ошибка исполнения сделки")
                    else:
                        logger.info(f"⏭️ Сигнал {current_direction} уже был обработан")
                else:
                    # Сбрасываем направление при отсутствии сигнала
                    if last_direction != 'NEUTRAL':
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
                    from risk_manager import DynamicRiskManager
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
