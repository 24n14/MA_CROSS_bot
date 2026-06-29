"""
Точка входа. Бот работает в режиме мультитаймфрейма (MTF) с постоянным циклом анализа.
"""
import time
import traceback
from log import logger
from config import AnalysisConfig
from run import run_mtf_analysis, print_mtf_result


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

    try:
        while True:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"🔄 Запуск MTF анализа {SYMBOL}...")
            logger.info(f"{'=' * 60}")

            analysis_data = run_mtf_analysis(cfg)

            if analysis_data and analysis_data['analysis']:
                analysis = analysis_data['analysis']
                mtf = analysis_data['analyzer']
                mtf.print_analysis(analysis)
                print_mtf_result(analysis_data, cfg)

                # Логируем финальный сигнал для ntfy
                final = analysis['final_signal']
                emoji = '🟢' if final['direction'] == 'BULLISH' else '🔴' if final['direction'] == 'BEARISH' else '⚪'
                logger.warning(
                    f"{emoji} {SYMBOL} — {final['direction']} | "
                    f"Уверенность: {final['confidence']} | "
                    f"Сила: {final['strength']:.1f} | "
                    f"Согласие ТФ: {final['agreement']}%"
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