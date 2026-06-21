"""
Точка входа в программу.

Настройте AnalysisConfig и запустите:
    python start.py
"""

import traceback
from config import AnalysisConfig
from run import (
    run_single_analysis,
    run_mtf_analysis,
    print_single_result,
    print_comparison
)


def main():
    """
    Главная функция запуска анализа.

    Настройте параметры в AnalysisConfig:
    - enable_mtf: True/False для MTF анализа
    - enable_single: True/False для одиночного ТФ
    - enable_compare: True/False для сравнения
    """
    # ==========================================
    # НАСТРОЙКА РЕЖИМОВ (True/False)
    # ==========================================

    analysis_config = AnalysisConfig(
        # Выберите нужные режимы:
        enable_mtf=True,  # Мультитаймфреймовый анализ
        enable_single=True,  # Одиночный таймфрейм
        enable_compare=True,  # Сравнение MTF vs Single

        # Общие настройки
        symbol='BTC/USDT',
        exchange='binance',
        limit=500,

        # Таймфреймы для MTF
        mtf_timeframes=('1h', '4h', '1d'),

        # Таймфрейм для одиночного режима
        single_timeframe='4h',

        # Сохранение и вывод
        save_csv=True,
        verbose=True
    )

    print(f"\n{'🔷' * 30}")
    print(f"ЗАПУСК АНАЛИЗА: {analysis_config.symbol}")
    print(f"{'🔷' * 30}")
    print(f"\nАктивные режимы:")
    print(f"  MTF:     {'✅ ВКЛ' if analysis_config.enable_mtf else '❌ ВЫКЛ'}")
    print(f"  Single:  {'✅ ВКЛ' if analysis_config.enable_single else '❌ ВЫКЛ'}")
    print(f"  Compare: {'✅ ВКЛ' if analysis_config.enable_compare else '❌ ВЫКЛ'}")

    mtf_data = None
    single_data = None

    # ====== MTF АНАЛИЗ ======
    if analysis_config.enable_mtf:
        mtf_data = run_mtf_analysis(analysis_config)
        if mtf_data and analysis_config.verbose:
            mtf_data['analyzer'].print_analysis(mtf_data['analysis'])

    # ====== ОДИНОЧНЫЙ АНАЛИЗ ======
    if analysis_config.enable_single:
        single_data = run_single_analysis(analysis_config)
        if single_data:
            print_single_result(single_data, analysis_config)

    # ====== СРАВНЕНИЕ ======
    if analysis_config.enable_compare and mtf_data and single_data:
        print_comparison(mtf_data, single_data, analysis_config)

    print(f"\n{'=' * 60}")
    print(f"✅ Анализ завершен успешно")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Выполнение прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        traceback.print_exc()
