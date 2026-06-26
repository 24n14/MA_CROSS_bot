"""
Модуль функций запуска и вывода результатов.

Содержит функции:
- run_single_analysis: запуск одиночного анализа
- run_mtf_analysis: запуск MTF анализа
- print_single_result: вывод одиночного результата
- print_comparison: сравнение MTF и Single
"""
import os
from typing import Dict
from log import logger
from config import AnalysisConfig
from mtf_analyzer import MultiTimeframeAnalyzer
from exchange import ExchangeDataLoader

# Папка для сохранения CSV
CSV_DIR = 'csv_history'


def _ensure_csv_dir():
    """Создать папку csv_history если её нет"""
    os.makedirs(CSV_DIR, exist_ok=True)


def run_mtf_analysis(analysis_config: AnalysisConfig) -> Dict:
    """
    Запуск мультитаймфреймового анализа.

    Args:
        analysis_config: конфигурация режимов

    Returns:
        Словарь с анализатором и результатами
    """
    mtf = MultiTimeframeAnalyzer(
        timeframes=list(analysis_config.mtf_timeframes),
        exchange_name=analysis_config.exchange,
        symbol=analysis_config.symbol
    )

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
    logger.info(f"{'Таймфрейм':<15} {'Сигнал':<20} {'Цена':<15}")
    logger.info(f"{'─' * 50}")

    for item in details:
        tf = item['timeframe']
        signal = item['signal']
        close = item['close']
        logger.info(f"{tf:<15} {signal:<20} ${close:<10.2f}")
