"""
Модуль глобальной конфигурации индикаторов и параметров риск-менеджмента.
Содержит классы:
- Config: параметры технического индикатора
- AnalysisConfig: настройка режимов работы и управление рисками
"""
from dataclasses import dataclass


@dataclass
class Config:
    """
    Конфигурация технического индикатора.
    """
    ma_period: int = 20
    ema_period: int = 50
    trend_lookback: int = 20
    angle_threshold_strong: float = 30.0
    angle_threshold_weak: float = 10.0
    divergence_threshold: float = 0.1
    use_linear_regression: bool = True
    smooth_angle: bool = True

    @classmethod
    def for_timeframe(cls, timeframe: str) -> 'Config':
        """
        Создать конфигурацию под конкретный таймфрейм с исправленными математическими периодами.
        """
        # Младшие таймфреймы (скальпинг/интрадей шумы)
        if timeframe in ['1m', '5m', '15m']:
            return cls(
                ma_period=9,  # Короткая быстрая скользящая
                ema_period=21,  # Экспоненциальная средняя для фильтрации шума
                trend_lookback=14,  # Увеличен lookback для защиты от резких шпилек
                angle_threshold_strong=25.0,  # Оптимизированные углы под ATR-регрессию
                angle_threshold_weak=12.0,
                divergence_threshold=0.1
            )

        # Средние таймфреймы
        elif timeframe in ['30m', '1h']:
            return cls(
                ma_period=20,
                ema_period=50,
                trend_lookback=14,
                angle_threshold_strong=20.0,
                angle_threshold_weak=10.0,
                divergence_threshold=0.15
            )

        # Трендовый таймфрейм (основной рабочий)
        elif timeframe in ['4h']:
            return cls(
                ma_period=50,
                ema_period=100,
                trend_lookback=20,
                angle_threshold_strong=15.0,
                angle_threshold_weak=5.0,
                divergence_threshold=0.25
            )

        # Глобальные стратегические таймфреймы
        elif timeframe in ['1d', '1w']:
            return cls(
                ma_period=50,
                ema_period=200,
                trend_lookback=30,
                angle_threshold_strong=10.0,
                angle_threshold_weak=3.0,
                divergence_threshold=0.35
            )
        else:
            return cls()


@dataclass
class AnalysisConfig:
    """
    Конфигурация режимов анализа и централизованного риск-менеджмента.
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

    # --- ИНТЕГРАЦИЯ ДИНАМИЧЕСКОГО РИСК-МЕНЕДЖМЕНТА ---
    atr_multiplier: float = 2.0  # Множитель волатильности для динамического Stop Loss
    risk_reward_ratio: float = 2.0  # Математическое соотношение Risk/Reward (1:2) для Take Profit
