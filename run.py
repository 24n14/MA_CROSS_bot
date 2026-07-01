"""
Модуль функций запуска и вывода результатов.

Содержит функции:
- run_single_analysis: запуск одиночного анализа
- run_mtf_analysis: запуск MTF анализа
- print_single_result: вывод одиночного результата
- print_comparison: сравнение MTF и Single
"""
import os
from typing import Dict, Optional
from log import logger
from config import AnalysisConfig
from mtf_analyzer import MultiTimeframeAnalyzer


# Папка для сохранения CSV
CSV_DIR = 'csv_history'


def _ensure_csv_dir():
    """Создать папку csv_history если её нет"""
    os.makedirs(CSV_DIR, exist_ok=True)


def create_mtf_analyzer(analysis_config: AnalysisConfig) -> MultiTimeframeAnalyzer:
    """
    Создание MTF анализатора (один раз при старте).

    Args:
        analysis_config: конфигурация режимов

    Returns:
        Экземпляр MultiTimeframeAnalyzer
    """
    return MultiTimeframeAnalyzer(
        timeframes=list(analysis_config.mtf_timeframes),
        exchange_name=analysis_config.exchange,
        symbol=analysis_config.symbol
    )


def run_mtf_analysis(analysis_config: AnalysisConfig,
                     mtf_analyzer: Optional[MultiTimeframeAnalyzer] = None) -> Dict:
    """
    Запуск мультитаймфреймового анализа.
    При повторных вызовах с тем же анализатором догружает только новые свечи.

    Args:
        analysis_config: конфигурация режимов
        mtf_analyzer: существующий анализатор (если None — создаётся новый)

    Returns:
        Словарь с анализатором и результатами
    """
    if mtf_analyzer is None:
        mtf = create_mtf_analyzer(analysis_config)
    else:
        mtf = mtf_analyzer

    analysis = mtf.load_and_analyze(limit=analysis_config.limit)

    if analysis and analysis_config.save_csv:
        _ensure_csv_dir()
        safe_symbol = analysis_config.symbol.replace('/', '_')
        for tf, result in analysis['results'].items():
            filename = f"MTF_{safe_symbol}_{tf}_signals.csv"
            output_file = os.path.join(CSV_DIR, filename)
            result.to_csv(output_file)
            logger.info(f"💾 Сохранено: {output_file}")

    return {
        'analyzer': mtf,
        'analysis': analysis
    }


def print_mtf_result(mtf_data: Dict, analysis_config: AnalysisConfig):
    """
    Вывод результатов MTF анализа.

    Args:
        mtf_data: результат run_mtf_analysis()
        analysis_config: конфигурация режимов
    """
    if not mtf_data or not analysis_config.verbose:
        return

    analysis = mtf_data['analysis']
    final = analysis['final_signal']
    details = analysis['mtf_details']

    logger.info(f"\n{'=' * 60}")
    logger.info(f"📊 МТФ АНАЛИЗ: {analysis_config.symbol}")
    logger.info(f"{'=' * 60}")

    emoji = '🟢' if final['direction'] == 'BULLISH' else '🔴' if final['direction'] == 'BEARISH' else '⚪'
    logger.info(f"{emoji} Направление: {final['direction']}")
    logger.info(f"💪 Сила: {final['strength']:.1f}")
    logger.info(f"🎯 Уверенность: {final['confidence']}")
    logger.info(f"📊 Согласие ТФ: {final['agreement']}%")

    logger.info(f"\n{'─' * 50}")
    logger.info(f"{'Таймфрейм':} {'Сигнал':} {'Цена':}")
    logger.info(f"{'─' * 50}")

    for item in details:
        tf = item['timeframe']
        signal = item['signal']
        close = item['close']
        logger.info(f"{tf:} {signal:} ${close:.2f}")

        # Подробные данные по индикаторам для каждого таймфрейма
        result_df = analysis['results'][tf]
        last = result_df.iloc[-1]

        ma_angle = last.get('MA_Angle_Final', 0.0)
        adx = last.get('ADX', 0.0)
        atr = last.get('ATR', 0.0)
        ma = last.get('MA', close)
        ema = last.get('EMA', close)

        logger.info(f"  📐 Угол MA: {ma_angle:+.1f}° | ADX: {adx:.1f} | ATR: ${atr:.2f}")
        logger.info(f"  📊 MA: ${ma:.2f} | EMA: ${ema:.2f}")