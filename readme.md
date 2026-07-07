# 🚀 MA-CROSS-BOT

**Многофункциональный индикатор технического анализа** с мультитаймфреймовым анализом тренда на основе углов наклона скользящих средних (MA/EMA) и ATR-нормализацией.

Ключевые особенности решения:
- Динамический SL/TP на основе ATR и ADX
- Перевод в безубыток и трейлинг стоп-лосс
- MTF анализ с взвешенным консенсусом
- Полная конфигурация через `config.py`

---

## 📋 Содержание

- [Возможности](#возможности)
- [Установка](#установка)
- [Структура проекта](#структура-проекта)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
  - [Config — параметры индикатора](#config--параметры-индикатора)
  - [AnalysisConfig — режимы анализа и торговли](#analysisconfig--режимы-анализа-и-торговли)
  - [RiskConfig — риск-менеджмент](#riskconfig--риск-менеджмент)
  - [TF_WEIGHTS — веса ��аймфреймов](#tf_weights--веса-таймфреймов)
- [Архитектура](#архитектура)
- [Классы и функции](#классы-и-функции)
- [Сигналы](#сигналы)
- [Примеры использования](#примеры-использования)

---

## ✨ Возможности

- ✅ Анализ тренда по углу наклона MA/EMA с ATR-нормализацией
- ✅ Мультитаймфреймовый анализ (MTF) с взвешенным консенсусом
- ✅ Автоматический подбор параметров под таймфрейм (`Config.for_timeframe()`)
- ✅ Защита от флэта через ADX-фильтр (порог настраивается)
- ✅ Фильтр расхождения MA/EMA — отсекает ложные сигналы
- ✅ Числовая оценка силы сигнала (от -100 до +100)
- ✅ Динамический SL/TP на основе ATR и ADX
- ✅ Перевод в безубыток (breakeven) при движении цены
- ✅ Трейлинг стоп-лосс вслед за ценой
- ✅ Умное обновление SL/TP на бирже (только при значимых изменениях)
- ✅ Загрузка реальных данных с 100+ бирж через CCXT
- ✅ Сохранение результатов в CSV
- ✅ Непрерывный MTF анализ рынка в реальном времени

---

## 📦 Установка

```bash
pip install ccxt pandas numpy scipy pandas-ta
```

---

## 📁 Структура проекта

```
ma-cross-bot/
├── logs/                  # Логи работы программы
│   └── bot_history.log
├── csv_history/           # Результаты анализа (CSV)
├── config.py              # Конфигурации (Config, AnalysisConfig, RiskConfig)
├── exchange.py            # Загрузчик данных с бирж (CCXT)
├── indicator.py           # Основной индикатор (AdvancedTrendSignalIndicator)
├── mtf_analyzer.py        # MTF анализатор (MultiTimeframeAnalyzer)
├── risk_manager.py        # Риск-менеджмент (DynamicRiskManager, PositionMonitor)
├── run.py                 # Функции запуска и вывода
├── start.py               # Точка входа — непрерывный MTF анализ + торговля
├── log.py                 # Настройка логирования
├── requirements.txt       # Зависимости
└── readme.md              # Этот файл
```

---

## 🚀 Быстрый старт

```bash
# Запуск бота с настройками по умолчанию (BTC/USDT, Bybit)
python start.py
```

Бот запускает **непрерывный MTF анализ + торговлю** в бесконечном цикле:
1. Загружает данные по всем настроенным таймфреймам
2. Проводит взвешенный консенсус — агрегирует сигналы со всех ТФ
3. При наличии сигнала открывает сделку с динамическим SL/TP
4. Мониторит позицию: переводит в безубыток, подтягивает стоп
5. Повторяет анализ каждые N секунд (настраивается)

---

## ⚙️ Конфигурация

Все настраиваемые параметры бота находятся в **`config.py`**. Ниже — полное описание каждого класса и параметра.

---

### Config — параметры индикатора

**Назначение:** Параметры технического индикатора (MA, EMA, углы, фильтры).

```python
from config import Config

# Значения по умолчанию
config = Config()

# Автоподбор под таймфрейм
config = Config.for_timeframe('4h')
```

#### Параметры

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `ma_period` | `int` | `20` | Период простой скользящей средней (MA) |
| `ema_period` | `int` | `50` | Период экспоненциальной скользящей средней (EMA) |
| `trend_lookback` | `int` | `20` | Количество свечей для расчёта угла наклона |
| `angle_threshold_strong` | `float` | `30.0` | Порог угла для **сильного** тренда (градусы) |
| `angle_threshold_weak` | `float` | `10.0` | Порог угла для **слабого** тренда (градусы) |
| `divergence_threshold` | `float` | `0.1` | Мин. расхождение MA/EMA (%) для подтверждения тренда |
| `adx_flat_threshold` | `float` | `20.0` | **ADX ниже этого порога = флэт, торговля заблокирована** |
| `use_linear_regression` | `bool` | `True` | Использовать линейную регрессию для расчёта угла |
| `smooth_angle` | `bool` | `True` | Сглаживать угол (скользящее среднее по 3 периодам) |

> 💡 **`adx_flat_threshold`** — ключевой параметр защиты от флэта. Чем выше значение, тем реже бот будет входить в рынок. Для BTC рекомендуется 20-25.

---

### AnalysisConfig — режимы анализа и торговли

**Назначение:** Централизованная конфигурация режимов анализа, торговли и мониторинга позиции.

```python
from config import AnalysisConfig

# Значения по умолчанию
cfg = AnalysisConfig()

# Кастомная настройка
cfg = AnalysisConfig(
    symbol='ETH/USDT',
    exchange='bybit',
    risk_percent=5.0,           # Риск 5% на сделку
    sleep_seconds=60,           # Анализ каждую минуту
    breakeven_atr_mult=2.0,     # Безубыток при 2x ATR
    trail_sl_mult=2.0           # Трейлинг стоп 2x ATR
)
```

#### Параметры

##### Биржа и символ

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `symbol` | `str` | `'BTC/USDT:USDT'` | Торговая пара |
| `exchange` | `str` | `'bybit'` | Биржа (bybit, binance и т.д.) |
| `limit` | `int` | `300` | Количество загружаемых свечей |

##### Таймфреймы и вывод

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `mtf_timeframes` | `tuple` | `('5m', '5m', '15m')` | Таймфреймы для MTF анализа |
| `save_csv` | `bool` | `True` | Сохранять результаты в CSV |
| `verbose` | `bool` | `True` | Подробный вывод в консоль |

##### Параметры цикла

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `sleep_seconds` | `int` | `300` | **Интервал между циклами анализа (сек)** — 5 мин |
| `trading_enabled` | `bool` | `True` | **Включить/выключить торговлю** |

##### Параметры риска

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `risk_percent` | `float` | `2.0` | **Риск на сделку в % от депозита** |
| `min_signal_strength` | `float` | `30.0` | **Минимальная сила сигнала для входа (0-100)** |

##### Параметры мониторинга позиции

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `breakeven_atr_mult` | `float` | `1.5` | **Активация безубытка при N × ATR прибыли** |
| `trail_sl_mult` | `float` | `1.5` | **Трейлинг стопа на N × ATR от best_price** |
| `trail_tp_mult` | `Optional[float]` | `None` | **Трейлинг TP (None = отключён)** |

##### Параметры MTF анализа

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `min_strength_for_trade` | `float` | `40.0` | **Мин. взвешенная сила для разрешения входа** |
| `confidence_very_high` | `float` | `75.0` | >= этого % согласия ТФ → VERY HIGH |
| `confidence_high` | `float` | `60.0` | >= этого % согласия ТФ → HIGH |
| `confidence_moderate` | `float` | `45.0` | >= этого % согласия ТФ → MODERATE |

---

### RiskConfig — риск-менеджмент

**Назначение:** Конфигурация расчёта SL/TP и мониторинга позиции.

```python
from config import RiskConfig

rc = RiskConfig()
# Все параметры имеют значения по умолчанию
```

#### Параметры

##### Базовые множители SL/TP

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `base_sl_multiplier` | `float` | `1.5` | **Базовый множитель стоп-лосса (SL = ATR × multiplier)** |
| `base_tp_multiplier` | `float` | `1.5` | Базовый множитель тейк-профита |

##### Пороги ADX для множителей TP

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `adx_moderate_threshold` | `float` | `25.0` | ADX >= этого → умеренный тренд |
| `adx_strong_threshold` | `float` | `35.0` | ADX >= этого → сильный тренд |
| `tp_multiplier_weak` | `float` | `1.5` | **TP при слабом тренде (ADX < 25)** |
| `tp_multiplier_moderate` | `float` | `2.0` | **TP при умеренном тренде (ADX 25-35)** |
| `tp_multiplier_strong` | `float` | `3.0` | **TP при сильном тренде (ADX > 35)** |

##### Защита от высокой волатильности

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `high_volatility_atr` | `float` | `400.0` | **Порог ATR ($) — при превышении SL увеличивается** |
| `high_vol_sl_multiplier` | `float` | `2.0` | Множитель SL при ATR >= high_volatility_atr |

##### Параметры мониторинга позиции (PositionMonitor)

| Параметр | Тип | По умолч. | Описание |
|---|---|---|---|
| `breakeven_activation_atr` | `float` | `1.5` | Множитель ATR для активации безубытка |
| `trail_sl_multiplier` | `float` | `1.5` | Множитель ATR для трейлинга стопа |
| `trail_tp_multiplier` | `Optional[float]` | `None` | Множитель ATR для трейлинга TP (None = откл) |
| `min_update_distance_atr` | `float` | `0.5` | **Мин. сдвиг SL/TP (в долях ATR) для отправки на биржу** |
| `min_atr_change_pct` | `float` | `15.0` | **Мин. изменение ATR в % для пересчёта** |

> 💡 **`min_update_distance_atr`** — защита от лишних запросов к бирже. При 0.5x ATR стоп сдвинется на бирже только если изменение ≥ половины текущего ATR.

---

### TF_WEIGHTS — веса таймфреймов

**Назначение:** Веса таймфреймов для взвешенного консенсуса в MTF анализе. Старшие ТФ имеют больший вес, чтобы младшие не перевешивали.

```python
from config import TF_WEIGHTS

# Значения по умолчанию
TF_WEIGHTS = {
    '1m': 0.05, '5m': 0.20, '15m': 0.20,
    '30m': 0.20, '1h': 0.35, '4h': 0.60,
    '1d': 0.85, '1w': 1.00
}
```

| Таймфрейм | Вес | Описание |
|---|---|---|
| `1m` | 0.05 | Минимальное влияние (шумы) |
| `5m` | 0.20 | |
| `15m` | 0.20 | |
| `30m` | 0.20 | |
| `1h` | 0.35 | Среднее влияние |
| `4h` | 0.60 | Высокое влияние |
| `1d` | 0.85 | Очень высокое влияние |
| `1w` | 1.00 | Максимальное влияние |

---

## 🏗 Архитектура

```
Config                          # Параметры индикатора (MA, EMA, углы, ADX порог)
└── for_timeframe()             # Автоподбор под таймфрейм

AnalysisConfig                  # Настройка режимов работы, торговли, мониторинга

RiskConfig                      # Параметры риск-менеджмента (SL/TP, трейлинг)

ExchangeDataLoader              # Загрузка данных с бирж
├── fetch_ohlcv()               # Один таймфрейм
├── load_multiple_timeframes()  # Несколько таймфреймов
└── execute_trade_signal()      # Исполнение торгового сигнала

AdvancedTrendSignalIndicator    # Основной индикатор
├── calculate_angle()           # Угол наклона (с ATR-нормализацией)
├── calculate_divergence()      # Расхождение MA/EMA (%)
├── determine_trend_strength()  # Определение тренда (ADX + углы + divergence)
├── generate_signal()           # Генерация сигналов
├── _get_enhanced_signal()      # Логика торговых сигналов
└── _calculate_signal_strength() # Числовая сила сигнала

MultiTimeframeAnalyzer          # MTF анализатор
├── load_and_analyze()          # Загрузка и анализ всех ТФ
├── _calculate_final_signal()   # Взвешенная агрегация сигналов
└── print_analysis()            # Вывод результатов

DynamicRiskManager              # Расчёт SL/TP и исполнение ордеров
├── calculate_sl_tp()           # Динамический расчёт SL/TP
├── calculate_position_size()   # Расчёт размера позиции
└── place_limit_order()         # Размещение ордера с SL/TP

PositionMonitor                 # Мониторинг открытой позиции
├── update()                    # Обновление SL/TP по рынку
├── _calculate_trailing_sl()    # Трейлинг стоп-лосс
├── _calculate_trailing_tp()    # Трейлинг тейк-профит
├── _update_on_exchange()       # Отправка на биржу
└── is_position_open()          # Проверка статуса позиции
```

---

## 📚 Классы и функции

### ExchangeDataLoader

**Назначение:** Загрузка рыночных данных с бирж через библиотеку CCXT.

```python
from exchange import ExchangeDataLoader

loader = ExchangeDataLoader('bybit')
```

Поддерживает **100+ бирж**: Binance, Bybit, Kraken, KuCoin, OKX, Huobi и др.

#### Методы

##### `fetch_ohlcv(symbol, timeframe, limit, since) -> pd.DataFrame`

Загружает свечные данные с биржи.

| Параметр | Тип | Описание |
|---|---|---|
| `symbol` | `str` | Торговая пара (`'BTC/USDT'`, `'ETH/USDT'`) |
| `timeframe` | `str` | Таймфрейм (`'1m'`, `'5m'`, `'15m'`, `'30m'`, `'1h'`, `'4h'`, `'1d'`, `'1w'`) |
| `limit` | `int` | Количество свечей (макс. зависит от биржи) |
| `since` | `str` | Начальная дата (`'2024-01-01'`) или `None` |

**Возвращает:** `DataFrame` с колонками: `open`, `high`, `low`, `close`, `volume`.

##### `execute_trade_signal(signal_data, risk_percent) -> Optional[Dict]`

Исполняет торговый сигнал: рассчитывает SL/TP, размер позиции и размещает ордер.

| Параметр | Тип | Описание |
|---|---|---|
| `signal_data` | `Dict` | Данные сигнала (direction, strength, atr, adx, close) |
| `risk_percent` | `float` | Процент риска на сделку |

---

### DynamicRiskManager

**Назначение:** Расчёт динамических SL/TP на основе ATR и ADX, размещение ордеров.

```python
from risk_manager import DynamicRiskManager

risk_mgr = DynamicRiskManager(exchange, 'BTC/USDT:USDT')
sl, tp = risk_mgr.calculate_sl_tp(entry_price=64000, atr=136, adx=42, side='long')
```

Все множители и пороги берутся из **`RiskConfig`**.

---

### PositionMonitor

**Назначение:** Мониторинг открытой позиции с автоматическим переводом в безубыток и трейлингом.

```python
from risk_manager import PositionMonitor

monitor = PositionMonitor(
    exchange=exchange,
    symbol='BTC/USDT:USDT',
    side='long',
    entry_price=64000,
    initial_sl=63800,
    initial_tp=64500,
    atr=136
)

# В каждом цикле:
updates = monitor.update(current_price=64500, new_atr=140)
```

**Логика работы:**
1. Цена прошла ≥ 1.5× ATR в прибыль → SL переводится на цену входа (безубыток)
2. После безубытка SL подтягивается вслед за ценой (трейлинг)
3. На биржу изменения отправляются только если сдвиг ≥ 0.5× ATR
4. ATR пересчитывается только при изменении > 15%

---

## 📊 Сигналы

### Все типы сигналов

| Сигнал | Эмодзи | Значение | Действие |
|---|---|---|---|
| `STRONG BULLISH` | 🟢🟢 | Сильный восходящий тренд | Открывать/удерживать LONG |
| `Bullish` | 🟢 | Умеренный восходящий тренд | Можно рассматривать LONG |
| `STRONG BEARISH` | 🔴🔴 | Сильный нисходящий тренд | Открывать/удерживать SHORT |
| `Bearish` | 🔴 | Умеренный нисходящий тренд | Можно рассматривать SHORT |
| `Sideways` | ⚪ | Боковое движение / флэт | Не торговать |
| `Neutral` | ⚪ | Нейтральный сигнал | Ждать более чёткого сигнала |

### Шкала силы сигнала

```
-100 ═══ -75 ═══ -50 ═══ -25 ═══ 0 ═══ +25 ═══ +50 ═══ +75 ═══ +100
  🔴🔴      🔴       🔴       🟠      ⚪      🟡       🟢       🟢       🟢🟢
```

---

## 💡 Примеры использования

### Пример 1: Настройка агрессивной стратегии

```python
from config import AnalysisConfig

cfg = AnalysisConfig(
    risk_percent=5.0,           # Риск 5% на сделку
    breakeven_atr_mult=1.0,     # Безубыток при 1x ATR (быстрее)
    trail_sl_mult=1.0,          # Трейлинг стоп 1x ATR (плотнее)
    min_signal_strength=20.0,   # Пропускать даже слабые сигналы
    min_strength_for_trade=30.0 # Нижний порог для входа
)
```

### Пример 2: Настройка консервативной стратегии

```python
from config import AnalysisConfig

cfg = AnalysisConfig(
    risk_percent=1.0,           # Риск 1% на сделку
    breakeven_atr_mult=2.5,     # Безубыток при 2.5x ATR
    trail_sl_mult=2.0,          # Широкий трейлинг
    min_signal_strength=50.0,   # Только сильные сигналы
    min_strength_for_trade=60.0 # Высокий порог входа
)
```

### Пример 3: Настройка SL/TP под свою стратегию

```python
from config import RiskConfig

# Агрессивный TP, широкий SL
rc = RiskConfig(
    base_sl_multiplier=2.0,     # Широкий стоп
    tp_multiplier_weak=2.0,     # TP при слабом тренде
    tp_multiplier_moderate=3.0, # TP при умеренном тренде
    tp_multiplier_strong=4.0,   # TP при сильном тренде
    high_volatility_atr=500.0   # Выше порог волатильности
)
```

### Пример 4: Изменение весов таймфреймов

```python
from config import TF_WEIGHTS

# Дать больше веса младшим ТФ
custom_weights = TF_WEIGHTS.copy()
custom_weights['5m'] = 0.35
custom_weights['15m'] = 0.35
custom_weights['1h'] = 0.30
```

---

## 🔧 Импорты

```python
from config import Config, AnalysisConfig, RiskConfig, TF_WEIGHTS
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from mtf_analyzer import MultiTimeframeAnalyzer
from risk_manager import DynamicRiskManager, PositionMonitor
from run import run_mtf_analysis, print_mtf_result
```

---

## 📄 Лицензия

Проект создан для образовательных и исследовательских целей. Используйте на свой страх и риск. Торговля криптовалютами сопряжена с высоким риском.