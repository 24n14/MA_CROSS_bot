"""
Точка входа. Бот работает в режиме мультитаймфрейма (MTF) с постоянным циклом анализа.
Оптимизация: анализатор создаётся один раз, данные догружаются инкрементально.
"""
import time
import traceback
from log import logger
from config import AnalysisConfig
from run import create_mtf_analyzer, run_mtf_analysis, print_mtf_result


def main():
    # ==========================================
    # НАСТРОЙКИ (из config.py)
    # ==========================================
    cfg = AnalysisConfig()

    SYMBOL = cfg.symbol
    MTF_TIMEFRAMES = list(cfg.mtf_timeframes)
    SLEEP_SECONDS = 300  # 5 минут между циклами MTF анализа

    logger.info("=" * 50)
    logger.info(f"🚀 Бот запущен (MTF режим): {SYMBOL}")
    logger.info(f"📊 Таймфреймы: {MTF_TIMEFRAMES}")
    logger.info(f"🕐 Интервал опроса: {SLEEP_SECONDS}с ({SLEEP_SECONDS // 60} мин)")
    logger.info("=" * 50)

    # Создаём анализатор ОДИН РАЗ перед циклом
    # При первом вызове load_and_analyze() загрузит 300 свечей для каждого ТФ
    # При последующих — только новые закрытые свечи
    mtf_analyzer = create_mtf_analyzer(cfg)
    logger.info("✅ Анализатор создан. Первичная загрузка данных...")

    try:
        while True:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"🔄 Запуск MTF анализа {SYMBOL}...")
            logger.info(f"{'=' * 60}")

            # Передаём существующий анализатор — он догрузит только новые свечи
            analysis_data = run_mtf_analysis(cfg, mtf_analyzer=mtf_analyzer)

            if analysis_data and analysis_data['analysis']:
                analysis = analysis_data['analysis']
                mtf = analysis_data['analyzer']
                mtf.print_analysis(analysis)
                print_mtf_result(analysis_data, cfg)

                # Финальный сигнал
                final = analysis['final_signal']
                emoji = '🟢' if final['direction'] == 'BULLISH' else '🔴' if final['direction'] == 'BEARISH' else '⚪'
                signal_msg = (
                    f"{emoji} {SYMBOL} — {final['direction']} | "
                    f"Уверенность: {final['confidence']} | "
                    f"Сила: {final['strength']:.1f} | "
                    f"Согласие ТФ: {final['agreement']}%"
                )

                # В ntfy отправляем только если сигнал BULLISH/BEARISH и сила > 0
                if final['direction'] in ('BULLISH', 'BEARISH') and final['strength'] > 0:
                    logger.warning(signal_msg)
                else:
                    logger.info(signal_msg)
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