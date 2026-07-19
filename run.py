"""Модуль функций запуска и вывода результатов."""
from __future__ import annotations

import os
from typing import Dict, Optional

from config import AnalysisConfig
from log import logger
from mtf_analyzer import MultiTimeframeAnalyzer
from mtf_analyzer import create_mtf_analyzer as _create_mtf_analyzer


CSV_DIR = "csv_history"


def _ensure_csv_dir() -> None:
    os.makedirs(CSV_DIR, exist_ok=True)


def create_mtf_analyzer(analysis_config: AnalysisConfig) -> MultiTimeframeAnalyzer:
    """
    Создание MTF-анализатора.
    Использует фабрику из mtf_analyzer.py, передавая analysis_config.
    """
    return _create_mtf_analyzer(analysis_config=analysis_config)


def run_mtf_analysis(
    analysis_config: AnalysisConfig,
    mtf_analyzer: Optional[MultiTimeframeAnalyzer] = None,
) -> Dict:
    if mtf_analyzer is None:
        mtf = create_mtf_analyzer(analysis_config)
    else:
        mtf = mtf_analyzer

    # Загружаем данные, анализируем все ТФ и агрегируем результат
    mtf.load_data()
    mtf.analyze_all()
    analysis = mtf.aggregate()

    if analysis and getattr(analysis_config, "save_csv", False):
        _ensure_csv_dir()
        safe_symbol = analysis_config.symbol.replace("/", "_")
        # Сохраняем сырые данные индикаторов по каждому ТФ
        for tf, df in mtf._data.items():
            filename = f"MTF_{safe_symbol}_{tf}_signals.csv"
            output_file = os.path.join(CSV_DIR, filename)
            df.to_csv(output_file)
            logger.debug(f"Сохранено: {output_file}")

    return {"analyzer": mtf, "analysis": analysis}


def print_mtf_result(mtf_data: Dict, analysis_config: AnalysisConfig) -> None:
    if not mtf_data or not getattr(analysis_config, "verbose", True):
        return

    analysis = mtf_data.get("analysis") or {}
    if not analysis:
        logger.warning("Нет analysis в mtf_data")
        return

    final = analysis.get("final_signal") or {}
    details = analysis.get("mtf_details") or []
    results = analysis.get("results") or {}

    logger.info(f"\n{'=' * 30}")
    logger.info(f"МТФ АНАЛИЗ: {analysis_config.symbol}")
    logger.info(f"{'=' * 30}")

    direction = final.get("direction", "NEUTRAL")
    if direction == "BULLISH":
        emoji = "[BULL]"
    elif direction == "BEARISH":
        emoji = "[BEAR]"
    else:
        emoji = "[FLAT]"

    logger.info(f"{emoji} Направление: {direction}")
    logger.info(f"Сила: {float(final.get('strength', 0) or 0):.1f}")
    logger.info(f"Уверенность: {final.get('confidence', 'LOW')}")
    logger.info(f"Согласие ТФ: {float(final.get('agreement', 0) or 0)}%")
    logger.info(f"\n{'─' * 40}")
    logger.info(f"{'Таймфрейм':<12} {'Сигнал':<20} {'Цена':>12}")
    logger.info(f"{'─' * 40}")

    for item in details:
        tf = item.get("timeframe", "?")
        signal = str(item.get("signal", "NEUTRAL"))
        close = float(item.get("close", 0) or 0)
        logger.info(f"{tf:<12} {signal:<20} ${close:>10.2f}")

        # детали индикаторов — внутри цикла
        if tf in results:
            result_df = results[tf]
            if result_df is not None and len(result_df) > 0:
                last = result_df.iloc[-1]
                ma_angle = float(last.get("MA_Angle_Final", 0.0) or 0.0)
                adx = float(last.get("ADX", 0.0) or 0.0)
                atr = float(last.get("ATR", 0.0) or 0.0)
                ma = float(last.get("MA", close) or close)
                ema = float(last.get("EMA", close) or close)
                logger.info(
                    f"  Угол MA: {ma_angle:+.1f}° | ADX: {adx:.1f} | ATR: ${atr:.2f}"
                )
                logger.info(f"  MA: ${ma:.2f} | EMA: ${ema:.2f}")

    logger.info(f"{'─' * 40}")
    trade = "ДА" if final.get("trigger_trade") else "НЕТ"
    logger.info(f"Торговать: {trade}")
    logger.info(f"ATR: ${float(final.get('atr', 0) or 0):.2f}")
    logger.info(f"ADX: {float(final.get('adx', 0) or 0):.1f}")