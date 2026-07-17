"""
Модуль глобальной конфигурации индикаторов и параметров риск-менеджмента.
Содержит классы:
- Config: параметры технического индикатора
- AnalysisConfig: настройка режимов работы и управление рисками
- RiskConfig: конфигурация риск-менеджмента
"""
import os
from dataclasses import dataclass  # ,field
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# ПРОКСИ И КЛЮЧИ БИРЖИ (из .env)
# =============================================================================
USE_PROXY = False  # False - отключено, True - включено
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")

API_KEY = os.getenv("API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
DEMO_TRADING = True


# =============================================================================
# ВЕСА ТАЙМФРЕЙМОВ ДЛЯ MTF КОНСЕНСУСА
# Старшие ТФ имеют больший вес, чтобы младшие не перевешивали.
# =============================================================================
TF_WEIGHTS: Dict[str, float] = {
    '1m': 0.05, '5m': 0.20, '15m': 0.20,
    '30m': 0.20, '1h': 0.35, '4h': 0.60,
    '1d': 0.85, '1w': 1.00
}

MIN_AMOUNT: float = 0.001  # Минимальный объём для BTC/USDT на Bybit
min_amount = MIN_AMOUNT

@dataclass
class Config:
    """
    Конфигурация технического индикатора.

    Параметры для расчёта скользящих средних, углов наклона,
    фильтрации флэта и расхождения MA/EMA.
    """
    # --- ПЕРИОДЫ СКОЛЬЗЯЩИХ СРЕДНИХ ---
    ma_period: int = 20          # Период простой скользящей средней (MA)
    ema_period: int = 50         # Период экспоненциальной скользящей средней (EMA)
    trend_lookback: int = 20     # Количество свечей для расчёта угла наклона

    # --- ПОРОГИ УГЛОВ ---
    angle_threshold_strong: float = 30.0  # Угол (град) для сильного тренда
    angle_threshold_weak: float = 10.0    # Угол (град) для слабого тренда

    # --- ФИЛЬТРЫ ---
    divergence_threshold: float = 0.1     # Мин. расхождение MA/EMA (%) для подтверждения тренда
    adx_flat_threshold: float = 20.0      # ADX ниже этого порога = флэт (торговля заблокирована)

    # --- НАСТРОЙКИ РАСЧЁТА ---
    use_linear_regression: bool = True    # Использовать линейную регрессию для угла
    smooth_angle: bool = True             # Сглаживать угол (скользящее среднее по 3 периодам)

    @classmethod
    def for_timeframe(cls, timeframe: str) -> 'Config':
        """
        Создать конфигурацию под конкретный таймфрейм с исправленными математическими периодами.
        """
        # Младшие таймфреймы (скальпинг/интрадей шумы)
        if timeframe in ['1m', '5m', '15m']:
            return cls(
                ma_period=9,
                ema_period=21,
                trend_lookback=14,
                angle_threshold_strong=12.0,
                angle_threshold_weak=5.0,
                divergence_threshold=0.05
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
    Конфигурация режимов анализа и торговли.

    Содержит все настраиваемые параметры для работы бота:
    - подключение к бирже
    - таймфреймы для MTF анализа
    - параметры цикла и торговли
    - пороги сигналов и уверенности
    """
    # --- БИРЖА И СИМВОЛ ---
    symbol: str = "BTC/USDT:USDT"     # Торговая пара
    exchange: str = 'bybit'           # Биржа (bybit, binance и т.д.)
    limit: int = 300                  # Количество загружаемых свечей

    # --- ТАЙМФРЕЙМЫ ---
    mtf_timeframes: tuple = ('5m', '15m', '30m')  # Таймфреймы для MTF анализа

    # --- ВЫВОД ---
    save_csv: bool = True             # Сохранять результаты в CSV
    verbose: bool = True              # Подробный вывод в консоль

    # =========================================================================
    # ПАРАМЕТРЫ ЦИКЛА
    # =========================================================================
    sleep_seconds: int = 300          # Интервал между циклами анализа (сек) — 5 мин
    trading_enabled: bool = True      # Включить/выключить торговлю

    # =========================================================================
    # ПАРАМЕТРЫ РИСКА
    # =========================================================================
    risk_percent: float = 2.0         # Риск на сделку в % от депозита
    min_signal_strength: float = 30.0  # Минимальная сила сигнала для входа (0-100)

    # =========================================================================
    # ПАРАМЕТРЫ МОНИТОРИНГА ПОЗИЦИИ (PositionMonitor)
    # =========================================================================
    breakeven_atr_mult: float = 1.5   # Активация безубытка при N x ATR прибыли
    trail_sl_mult: float = 1.5        # Трейлинг стопа на N x ATR от best_price
    trail_tp_mult: Optional[float] = None  # Трейлинг TP (None = отключён)

    # =========================================================================
    # ПАРАМЕТРЫ MTF АНАЛИЗА
    # =========================================================================
    min_strength_for_trade: float = 40.0  # Мин. взвешенная сила для разрешения входа

    # --- ПОРОГИ УВЕРЕННОСТИ (% согласия ТФ) ---
    confidence_very_high: float = 75.0  # >= этого % -> VERY HIGH
    confidence_high: float = 60.0       # >= этого % -> HIGH
    confidence_moderate: float = 45.0   # >= этого % -> MODERATE


@dataclass
class RiskConfig:
    """
    Конфигурация риск-менеджмента.

    Все параметры для DynamicRiskManager (расчёт SL/TP)
    и PositionMonitor (мониторинг и обновление позиции).
    """
    # =========================================================================
    # БАЗОВЫЕ МНОЖИТЕЛИ SL/TP
    # =========================================================================
    base_sl_multiplier: float = 3   # Базовый множитель стоп-лосса (SL = ATR × multiplier)
    base_tp_multiplier: float = 3   # Базовый множитель тейк-профита

    # =========================================================================
    # ПОРОГИ ADX ДЛЯ МНОЖИТЕЛЕЙ TP
    # =========================================================================
    adx_moderate_threshold: float = 25.0  # ADX >= этого -> умеренный тренд
    adx_strong_threshold: float = 35.0    # ADX >= этого -> сильный тренд
    tp_multiplier_weak: float = 1.5       # TP при слабом тренде (ADX < 25)
    tp_multiplier_moderate: float = 2.0   # TP при умеренном тренде (ADX 25-35)
    tp_multiplier_strong: float = 3.0     # TP при сильном тренде (ADX > 35)

    # =========================================================================
    # ЗАЩИТА ОТ ВЫСОКОЙ ВОЛАТИЛЬНОСТИ
    # =========================================================================
    high_volatility_atr: float = 400.0    # Порог ATR ($) — при превышении SL увеличивается
    high_vol_sl_multiplier: float = 2.0   # Множитель SL при ATR >= high_volatility_atr

    # =========================================================================
    # ПАРАМЕТРЫ МОНИТОРИНГА ПОЗИЦИИ (PositionMonitor)
    # =========================================================================
    breakeven_activation_atr: float = 1.5  # Множитель ATR для активации безубытка
    trail_sl_multiplier: float = 1.5       # Множитель ATR для трейлинга стопа
    trail_tp_multiplier: Optional[float] = None  # Множитель ATR для трейлинга TP (None = откл)
    min_update_distance_atr: float = 0.5   # Мин. сдвиг SL/TP (в долях ATR) для отправки на биржу
    min_atr_change_pct: float = 15.0       # Мин. изменение ATR в % для пересчёта
    MIN_AMOUNT: float = 0.001  # Минимальный объём для BTC/USDT на Bybit
    min_amount = MIN_AMOUNT
    