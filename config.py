"""
Модуль конфигурации индикатора.

Содержит классы:
- Config: параметры технического индикатора
- AnalysisConfig: настройка режимов работы
"""

from dataclasses import dataclass


@dataclass
class Config:
    """
    Конфигурация технического индикатора.

    Attributes:
        ma_period: период простой скользящей средней
        ema_period: период экспоненциальной скользящей средней
        trend_lookback: количество свечей для анализа тренда
        angle_threshold_strong: угол для сильного тренда (градусы)
        angle_threshold_weak: угол для слабого тренда (градусы)
        divergence_threshold: порог расхождения MA/EMA (%)
        use_linear_regression: использовать линейную регрессию
        smooth_angle: сглаживать угол
    """
    ma_period: int = 5
    ema_period: int = 20
    trend_lookback: int = 50
    angle_threshold_strong: float = 30.0
    angle_threshold_weak: float = 10.0
    divergence_threshold: float = 0.1
    use_linear_regression: bool = True
    smooth_angle: bool = True

    @classmethod
    def for_timeframe(cls, timeframe: str) -> 'Config':
        """
        Создать конфигурацию под конкретный таймфрейм.

        Args:
            timeframe: таймфрейм ('1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w')

        Returns:
            Config с оптимальными параметрами
        """
        if timeframe in ['1m', '5m', '15m']:
            return cls(
                ma_period=10, ema_period=10, trend_lookback=5,
                angle_threshold_strong=45.0, angle_threshold_weak=20.0,
                divergence_threshold=0.1
            )
        elif timeframe in ['30m', '1h']:
            return cls(
                ma_period=20, ema_period=20, trend_lookback=10,
                angle_threshold_strong=30.0, angle_threshold_weak=15.0,
                divergence_threshold=0.15
            )
        elif timeframe in ['4h']:
            return cls(
                ma_period=50, ema_period=50, trend_lookback=20,
                angle_threshold_strong=15.0, angle_threshold_weak=5.0,
                divergence_threshold=0.3
            )
        elif timeframe in ['1d', '1w']:
            return cls(
                ma_period=200, ema_period=50, trend_lookback=30,
                angle_threshold_strong=10.0, angle_threshold_weak=3.0,
                divergence_threshold=0.5
            )
        else:
            return cls()


@dataclass
class AnalysisConfig:
    """
    Конфигурация режимов анализа.

    Attributes:
        enable_mtf: включить мультитаймфреймовый анализ
        enable_single: включить анализ одного таймфрейма
        enable_compare: включить сравнение MTF и Single
        symbol: торговая пара
        exchange: биржа для загрузки данных
        limit: количество загружаемых свечей
        mtf_timeframes: таймфреймы для MTF анализа
        single_timeframe: таймфрейм для одиночного режима
        save_csv: сохранять результаты в CSV
        verbose: подробный вывод в консоль
    """
    enable_mtf: bool = True
    enable_single: bool = False
    enable_compare: bool = False

    symbol: str = 'BTC/USDT'
    exchange: str = 'binance'
    limit: int = 500

    mtf_timeframes: tuple = ('1h', '4h', '1d')
    single_timeframe: str = '4h'

    save_csv: bool = True
    verbose: bool = True
