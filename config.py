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
                angle_threshold_strong=12.0,  # Снижены пороги для захвата слабых трендов
                angle_threshold_weak=5.0,
                divergence_threshold=0.05  # Снижен порог расхождения MA/EMA
            )

        # Средние таймфреймы
        elif timeframe in ['30m', '1h']:
            return cls(
                ma_period=11,
                ema_period=31,
                trend_lookback=14,
                angle_threshold_strong=10.0,
                angle_threshold_weak=5.0,
                divergence_threshold=0.08
            )

        # Трендовый таймфрейм (основной рабочий)
        elif timeframe in ['4h']:
            return cls(
                ma_period=21,
                ema_period=49,
                trend_lookback=20,
                angle_threshold_strong=8.0,
                angle_threshold_weak=3.0,
                divergence_threshold=0.15
            )

        # Глобальные стратегические таймфреймы
        elif timeframe in ['1d', '1w']:
            return cls(
                ma_period=31,
                ema_period=100,
                trend_lookback=30,
                angle_threshold_strong=5.0,
                angle_threshold_weak=2.0,
                divergence_threshold=0.2
            )
        else:
            return cls()


@dataclass
class AnalysisConfig:
    """
    Конфигурация режимов анализа и централизованного риск-менеджмента.
    """
    symbol: str = 'BTC/USDT'
    exchange: str = 'binance'
    limit: int = 300

    mtf_timeframes: tuple = ('5m', '15m', '1h')

    save_csv: bool = True
    verbose: bool = True

    # --- ИНТЕГРАЦИЯ ДИНАМИЧЕСКОГО РИСК-МЕНЕДЖМЕНТА ---
    atr_multiplier: float = 2.0  # Множитель волатильности для динамического Stop Loss
    risk_reward_ratio: float = 2.0  # Математическое соотношение Risk/Reward (1:2) для Take Profit