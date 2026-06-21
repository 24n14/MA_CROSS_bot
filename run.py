"""
Модуль функций запуска и вывода результатов.

Содержит функции:
- run_single_analysis: запуск одиночного анализа
- run_mtf_analysis: запуск MTF анализа
- print_single_result: вывод одиночного результата
- print_comparison: сравнение MTF и Single
"""

# import pandas as pd
from typing import Dict

from config import Config, AnalysisConfig
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from mtf_analyzer import MultiTimeframeAnalyzer


def run_single_analysis(analysis_config: AnalysisConfig) -> Dict:
    """
    Запуск анализа одиночного таймфрейма.

    Args:
        analysis_config: конфигурация режимов

    Returns:
        Словарь с результатами или None
    """
    print(f"\n{'=' * 60}")
    print(f"📊 ОДИНОЧНЫЙ АНАЛИЗ: {analysis_config.symbol} ({analysis_config.single_timeframe})")
    print(f"{'=' * 60}")

    loader = ExchangeDataLoader(analysis_config.exchange)
    config = Config.for_timeframe(analysis_config.single_timeframe)
    indicator = AdvancedTrendSignalIndicator(config)

    df = loader.fetch_ohlcv(
        analysis_config.symbol,
        analysis_config.single_timeframe,
        analysis_config.limit
    )

    if df is None:
        print(f"❌ Не удалось загрузить данные для {analysis_config.symbol}")
        return None

    result = indicator.generate_signal(df)

    if analysis_config.save_csv:
        safe_symbol = analysis_config.symbol.replace('/', '_')
        output_file = f"{safe_symbol}_{analysis_config.single_timeframe}_signals.csv"
        result.to_csv(output_file)
        print(f"💾 Сохранено: {output_file}")

    return {
        'result': result,
        'config': config,
        'dataframe': df
    }


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
        for tf, result in analysis['results'].items():
            output_file = f"MTF_{analysis_config.symbol.replace('/', '_')}_{tf}_signals.csv"
            result.to_csv(output_file)
            print(f"💾 Сохранено: {output_file}")

    return {
        'analyzer': mtf,
        'analysis': analysis
    }


def print_single_result(single_data: Dict, analysis_config: AnalysisConfig):
    """
    Вывод результатов одиночного анализа.

    Args:
        single_data: результат run_single_analysis()
        analysis_config: конфигурация режимов
    """
    if not single_data or not analysis_config.verbose:
        return

    result = single_data['result']
    config = single_data['config']

    last_row = result.iloc[-1]
    print(f"\n📅 Последний сигнал: {result.index[-1]}")
    print(f"💰 Open: ${last_row['open']:.2f}")
    print(f"💰 Close: ${last_row['close']:.2f}")
    print(f"📊 MA({config.ma_period}): ${last_row['MA']:.2f}")
    print(f"📊 EMA({config.ema_period}): ${last_row['EMA']:.2f}")
    print(f"📐 Угол MA: {last_row['MA_Angle_Final']:.2f}°")
    print(f"📐 Расхождение: {last_row['Divergence']:.3f}%")
    print(f"🎯 Сигнал: {last_row['Signal']}")
    print(f"💪 Сила: {last_row['Signal_Strength']:.1f}")
    print(f"📈 Тренд: {last_row['Trend_State']}")


def print_comparison(mtf_data: Dict, single_data: Dict, analysis_config: AnalysisConfig):
    """
    Сравнение результатов MTF и одиночного анализа.

    Args:
        mtf_data: результат run_mtf_analysis()
        single_data: результат run_single_analysis()
        analysis_config: конфигурация режимов
    """
    if not mtf_data or not single_data:
        return

    mtf_final = mtf_data['analysis']['final_signal']
    single_last = single_data['result'].iloc[-1]

    print(f"\n{'=' * 60}")
    print(f"📊 СРАВНЕНИЕ MTF vs SINGLE")
    print(f"{'=' * 60}")

    print(f"\n{'Параметр':<25} {'MTF':<25} {'SINGLE ({})'.format(analysis_config.single_timeframe):<25}")
    print("-" * 75)

    print(f"{'Направление':<25} {mtf_final['direction']:<25} {single_last['Signal']:<25}")
    print(f"{'Сила':<25} {mtf_final['strength']:<25} {single_last['Signal_Strength']:<25}")
    print(f"{'Уверенность/Тренд':<25} {mtf_final['confidence']:<25} {single_last['Trend_State']:<25}")

    mtf_dir = mtf_final['direction']
    single_signal = str(single_last['Signal']).upper()

    if (mtf_dir == 'BULLISH' and 'BULLISH' in single_signal) or \
            (mtf_dir == 'BEARISH' and 'BEARISH' in single_signal):
        print(f"\n✅ Сигналы СОГЛАСОВАНЫ - можно действовать")
    else:
        print(f"\n⚠️ Сигналы РАСХОДЯТСЯ - требуется осторожность")
