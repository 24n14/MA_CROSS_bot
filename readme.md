# 🚀 MA-CROSS-BOT

**Многофункциональный индикатор технического анализа** с мультитаймфреймовым анализом тренда на основе углов наклона скользящих средних (MA/EMA) и ATR-нормализацией.

---

## 📋 Содержание

- [Возможности](#возможности)
- [Установка](#установка)
- [Структура проекта](#структура-проекта)
- [Быстрый старт](#быстрый-старт)
- [Архитектура](#архитектура)
- [Классы и функции](#классы-и-функции)
  - [Config](#config)
  - [AnalysisConfig](#analysisconfig)
  - [ExchangeDataLoader](#exchangedataloader)
  - [AdvancedTrendSignalIndicator](#advancedtrendsignalindicator)
  - [MultiTimeframeAnalyzer](#multitimeframeanalyzer)
- [Сигналы](#сигналы)
- [Примеры использования](#примеры-использования)
- [Сохранение результатов](#сохранение-результатов)

---

## ✨ Возможности

- ✅ Анализ тренда по углу наклона MA/EMA с ATR-нормализацией
- ✅ Мультитаймфреймовый анализ (MTF) с взвешенным консенсусом
- ✅ Автоматический подбор параметров под таймфрейм (`Config.for_timeframe()`)
- ✅ Защита от флэта через ADX-фильтр (ADX < 25 → торговля заблокирована)
- ✅ Фильтр расхождения MA/EMA (`divergence_threshold`) — отсекает ложные сигналы при "слипании" средних
- ✅ Числовая оценка силы сигнала (от -100 до +100)
- ✅ Загрузка реальных данных с 100+ бирж через CCXT
- ✅ Сохранение результатов в CSV
- ✅ Непрерывный мониторинг рынка в реальном времени

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
│   ├── BTC_USDT_4h_signals.csv
│   ├── MTF_BTC_USDT_1h_signals.csv
│   └── ...
├── config.py              # Конфигурации (Config, AnalysisConfig)
├── exchange.py            # Загрузчик данных с бирж (CCXT)
├── indicator.py           # Основной индикатор (AdvancedTrendSignalIndicator)
├── mtf_analyzer.py        # MTF анализатор (MultiTimeframeAnalyzer)
├── run.py                 # Функции запуска и вывода
├── start.py               # Точка входа — непрерывный мониторинг
├── log.py                 # Настройка логирования
├── requirements.txt       # Зависимости
└── readme.md              # Этот файл
```

---

## 🚀 Быстрый старт

```bash
# Запуск бота с настройками по умолчанию (BTC/USDT, Binance)
python start.py
```

Бот запустит непрерывный мониторинг рынка:
1. Анализирует таймфрейм мониторинга (по умолчанию `5m`)
2. При обнаружении входящего сигнала запускает MTF-анализ
3. Выводит результаты в консоль и сохраняет в CSV

---

## 🏗 Архитектура

```
Config                          # Параметры индикатора (MA, EMA, углы)
└── for_timeframe()             # Автоподбор под таймфрейм

AnalysisConfig                  # Настройка режимов работы

ExchangeDataLoader              # Загрузка данных с бирж
├── fetch_ohlcv()               # Один таймфрейм
└── load_multiple_timeframes()  # Несколько таймфреймов

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
```

---

## 📚 Классы и функции

### Config

**Назначение:** Параметры технического индикатора.

```python
from config import Config

# Значения по умолчанию
config = Config()

# Автоподбор под таймфрейм
config = Config.for_timeframe('4h')
```

#### Параметры

| Параметр                 | Тип     | По умолч. | Описание                                                    |
|--------------------------|---------|-----------|-------------------------------------------------------------|
| `ma_period`              | `int`   | `20`      | Период простой скользящей средней (MA)                      |
| `ema_period`             | `int`   | `50`      | Период экспоненциальной скользящей средней (EMA)            |
| `trend_lookback`         | `int`   | `20`      | Количество свечей для расчёта угла наклона                  |
| `angle_threshold_strong` | `float` | `30.0`    | Порог угла для **сильного** тренда (градусы)                |
| `angle_threshold_weak`   | `float` | `10.0`    | Порог угла для **слабого** тренда (градусы)                 |
| `divergence_threshold`   | `float` | `0.1`     | Минимальное расхождение MA/EMA (%) для подтверждения тренда |
| `use_linear_regression`  | `bool`  | `True`    | Использовать линейную регрессию для расчёта угла            |
| `smooth_angle`           | `bool`  | `True`    | Сглаживать угол (скользящее среднее по 3 периодам)          |

#### Config.for_timeframe(timeframe: str) -> Config

Автоматически подбирает оптимальные параметры под таймфрейм.

| Таймфрейм         | `ma_period` | `ema_period` | `trend_lookback` | `angle_strong` | `angle_weak` | `divergence` |
|-------------------|-------------|--------------|------------------|----------------|--------------|--------------|
| `1m`, `5m`, `15m` | 9           | 21           | 14               | 25.0°          | 12.0°        | 0.10         |
| `30m`, `1h`       | 20          | 50           | 14               | 20.0°          | 10.0°        | 0.15         |
| `4h`              | 50          | 100          | 20               | 15.0°          | 5.0°         | 0.25         |
| `1d`, `1w`        | 50          | 200          | 30               | 10.0°          | 3.0°         | 0.35         |
| *другие*          | 20          | 50           | 20               | 30.0°          | 10.0°        | 0.10         |

> **Логика подбора:** младшие таймфреймы (скальпинг) — короткие периоды и высокие пороги углов для фильтрации шума. Старшие таймфреймы (стратегические) — длинные периоды и низкие пороги для улавливания глобального тренда.

---

### AnalysisConfig

**Назначение:** Централизованная конфигурация режимов анализа и риск-менеджмента.

```python
from config import AnalysisConfig

# Значения по умолчанию
cfg = AnalysisConfig()

# Кастомная настройка
cfg = AnalysisConfig(
    symbol='ETH/USDT',
    exchange='bybit',
    mtf_timeframes=('4h', '1d', '1w'),
    save_csv=True
)
```

#### Параметры

| Параметр            | Тип     | По умолч.            | Описание                                            |
|---------------------|---------|----------------------|-----------------------------------------------------|
| `symbol`            | `str`   | `'BTC/USDT'`         | Торговая пара                                       |
| `exchange`          | `str`   | `'binance'`          | Биржа для загрузки данных                           |
| `limit`             | `int`   | `500`                | Количество загружаемых свечей                       |
| `mtf_timeframes`    | `tuple` | `('1h', '4h', '1d')` | Таймфреймы для MTF анализа                          |
| `monitor_timeframe` | `str`   | `'5m'`               | Таймфрейм мониторинга (start.py)                    |
| `save_csv`          | `bool`  | `True`               | Сохранять результаты в CSV                          |
| `verbose`           | `bool`  | `True`               | Подробный вывод в консоль                           |
| `atr_multiplier`    | `float` | `2.0`                | Множитель волатильности для динамического Stop Loss |
| `risk_reward_ratio` | `float` | `2.0`                | Соотношение Risk/Reward для Take Profit             |

---

### ExchangeDataLoader

**Назначение:** Загрузка рыночных данных с бирж через библиотеку CCXT.

```python
from exchange import ExchangeDataLoader

loader = ExchangeDataLoader('binance')
```

Поддерживает **100+ бирж**: Binance, Bybit, Kraken, KuCoin, OKX, Huobi и др.

#### Методы

##### `fetch_ohlcv(symbol, timeframe, limit, since) -> pd.DataFrame`

Загружает свечные данные с биржи.

| Параметр    | Тип   | Описание                                                                     |
|-------------|-------|------------------------------------------------------------------------------|
| `symbol`    | `str` | Торговая пара (`'BTC/USDT'`, `'ETH/USDT'`)                                   |
| `timeframe` | `str` | Таймфрейм (`'1m'`, `'5m'`, `'15m'`, `'30m'`, `'1h'`, `'4h'`, `'1d'`, `'1w'`) |
| `limit`     | `int` | Количество свечей (макс. зависит от биржи)                                   |
| `since`     | `str` | Начальная дата (`'2024-01-01'`) или `None`                                   |

**Возвращает:** `DataFrame` с колонками: `open`, `high`, `low`, `close`, `volume`.

```python
# Последние 500 свечей
df = loader.fetch_ohlcv('BTC/USDT', '4h', 500)

# Свечи с определённой даты
df = loader.fetch_ohlcv('ETH/USDT', '1h', 1000, since='2024-01-01')
```

##### `load_multiple_timeframes(symbol, timeframes, limit) -> Dict[str, pd.DataFrame]`

Загружает данные для нескольких таймфреймов одновременно.

```python
data = loader.load_multiple_timeframes(
    'BTC/USDT',
    timeframes=('15m', '1h', '4h', '1d'),
    limit=500
)

df_1h = data['1h']
df_4h = data['4h']
```

---

### AdvancedTrendSignalIndicator

**Назначение:** Основной индикатор для анализа тренда и генерации сигналов.

```python
from indicator import AdvancedTrendSignalIndicator
from config import Config

config = Config.for_timeframe('4h')
indicator = AdvancedTrendSignalIndicator(config)
result = indicator.generate_signal(df)
```

#### Методы

##### `calculate_angle(series: pd.Series, atr: pd.Series) -> pd.Series`

Рассчитывает угол наклона скользящей средней в градусах с **ATR-нормализацией**.

**Алгоритм:**
1. Берёт последние `trend_lookback` значений
2. Строит линейную регрессию (или простой расчёт, если `use_linear_regression=False`)
3. Нормализует наклон по ATR: `angle = arctan(slope / current_atr)`

**Интерпретация:**
- `> 0°` — линия растёт (восходящий тренд)
- `< 0°` — линия падает (нисходящий тренд)
- `≈ 0°` — линия горизонтальна (флэт)

##### `calculate_divergence(ma: pd.Series, ema: pd.Series) -> pd.Series`

Рассчитывает расхождение между MA и EMA в процентах.

```
divergence = |(MA - EMA) / EMA * 100|
```

**Интерпретация:**
- Большое расхождение → сильный тренд
- Маленькое расхождение → слабый тренд или флэт
- Расхождение → 0 → готовится пересечение (смена тренда)

##### `determine_trend_strength(ma_angle, ema_angle, divergence, current_adx) -> Dict`

Определяет направление и силу тренда с учётом ADX и расхождения MA/EMA.

**Логика определения направления:**
1. Если ADX < 25 → **neutral** (флэт, торговля заблокирована)
2. Если оба угла > `angle_threshold_weak` → **up**
3. Если оба угла < `-angle_threshold_weak` → **down**
4. Иначе → **neutral**

**Логика определения силы:**
1. Если `divergence < divergence_threshold` → **weak** (MA и EMA почти совпадают — тренд не подтверждён)
2. Средний угол > `angle_threshold_strong` **И** ADX > 35 → **strong**
3. Средний угол > `angle_threshold_weak` **И** ADX ≥ 25 → **moderate**
4. Иначе → **weak**

**Возвращает:**
```python
{
    'direction': 'up' | 'down' | 'neutral',
    'strength': 'strong' | 'moderate' | 'weak' | 'none',
    'confidence': 0.0 до 1.0
}
```

##### `generate_signal(df: pd.DataFrame) -> pd.DataFrame`

Главный метод генерации сигналов. Добавляет к DataFrame расчётные колонки.

| Колонка | Описание |
|---|---|
| `MA` | Простая скользящая средняя |
| `EMA` | Экспоненциальная скользящая средняя |
| `ATR` | Средний истинный диапазон (волатильность) |
| `ADX` | Индекс направленного движения (сила тренда) |
| `MA_Angle` | Угол наклона MA в градусах |
| `EMA_Angle` | Угол наклона EMA в градусах |
| `Divergence` | Расхождение MA/EMA в % |
| `Signal` | Текстовый торговый сигнал |
| `Signal_Strength` | Числовая сила сигнала (-100 до +100) |
| `Trend_State` | Состояние тренда (например `up_moderate`) |
| `Trend_Confidence` | Уверенность в тренде (0.0 – 1.0) |

```python
indicator = AdvancedTrendSignalIndicator(config)
result = indicator.generate_signal(df)

# Последний сигнал
print(result['Signal'].iloc[-1])
print(f"Сила: {result['Signal_Strength'].iloc[-1]}")
```

##### `_get_enhanced_signal(c, o, ma, ema, is_bullish, is_bearish, trend_info) -> str`

Внутренний метод. Генерирует текстовый сигнал на основе всех факторов.

**Логика:**
- Если `direction = 'neutral'` → `Sideways` (флэт)
- Если `direction = 'up'` и цена/открытие выше MA и EMA:
  - `strong`/`moderate` → `STRONG BULLISH`
  - `weak` → `Bullish`
  - иначе → `Neutral`
- Если `direction = 'down'` и цена/открытие ниже MA и EMA:
  - `strong`/`moderate` → `STRONG BEARISH`
  - `weak` → `Bearish`
  - иначе → `Neutral`

> Полностью исключает торговлю против тренда и "пилу".

##### `_calculate_signal_strength(trend_info, is_bullish, is_bearish) -> float`

Рассчитывает числовую силу сигнала от **-100 до +100**.

| Условие | Базовая сила |
|---|---|
| Восходящий тренд | +50 |
| Нисходящий тренд | -50 |

**Модификаторы:**
- Сильный тренд: ×1.5
- Умеренный тренд: ×1.2
- Свеча против тренда: ×0.5

---

### MultiTimeframeAnalyzer

**Назначение:** Мультитаймфреймовый анализ для фильтрации ложных сигналов.

```python
from mtf_analyzer import MultiTimeframeAnalyzer

mtf = MultiTimeframeAnalyzer(
    timeframes=['1h', '4h', '1d'],
    exchange_name='binance',
    symbol='BTC/USDT'
)
```

#### Методы

##### `load_and_analyze(limit: int = 500) -> Dict`

Загружает данные для всех таймфреймов и проводит полный анализ.

**Процесс:**
1. Загружает данные через `ExchangeDataLoader.load_multiple_timeframes()`
2. Для каждого ТФ создаёт индикатор с авто-конфигурацией (`Config.for_timeframe()`)
3. Генерирует сигналы для каждого ТФ
4. Агрегирует результаты через взвешенный консенсус

**Возвращает:**
```python
{
    'symbol': 'BTC/USDT',
    'timeframes': ['1h', '4h', '1d'],
    'timestamp': datetime,
    'mtf_details': [...],   # Детали по каждому ТФ
    'final_signal': {...},  # Агрегированный сигнал
    'results': {...}        # Полные DataFrame для каждого ТФ
}
```

##### `_calculate_final_signal(summary: List[Dict]) -> Dict`

Агрегирует сигналы с разных таймфреймов через **взвешенный консенсус**.

**Веса таймфреймов** (старшие имеют больший вес):

| Таймфрейм | Вес |
|---|---|
| `1m` | 0.05 |
| `5m` | 0.10 |
| `15m` | 0.15 |
| `30m` | 0.20 |
| `1h` | 0.35 |
| `4h` | 0.60 |
| `1d` | 0.85 |
| `1w` | 1.00 |

**Формула взвешенной силы:**
```
final_strength = Σ(signal_strength × tf_weight) / Σ(tf_weight)
```

**Защита от рассинхронизации:** если итоговый вектор младших ТФ идёт против старшего тренда — направление принудительно сбрасывается в `NEUTRAL`.

**Логика уверенности:**

| Согласованность ТФ | Уверенность |
|---|---|
| ≥ 75% | VERY HIGH |
| ≥ 60% | HIGH |
| ≥ 45% | MODERATE |
| < 45% | LOW |

**Возвращает:**
```python
{
    'direction': 'BULLISH' | 'BEARISH' | 'NEUTRAL',
    'confidence': 'VERY HIGH' | 'HIGH' | 'MODERATE' | 'LOW',
    'strength': float,        # Взвешенная сила
    'agreement': float,       # % согласованности
    'trigger_trade': bool,    # Разрешение на вход
    'total_timeframes': int   # Всего ТФ
}
```

##### `print_analysis(analysis: Dict)`

Выводит форматированную таблицу с результатами MTF анализа.

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
Максимально                                                    Максимально
медвежий                                                        бычий
```

| Диапазон | Значение |
|---|---|
| +75 до +100 | Очень сильный бычий сигнал |
| +50 до +75 | Сильный бычий |
| +25 до +50 | Умеренный бычий |
| 0 до +25 | Слабый бычий |
| 0 до -25 | Слабый медвежий |
| -25 до -50 | Умеренный медвежий |
| -50 до -75 | Сильный медвежий |
| -75 до -100 | Очень сильный медвежий сигнал |

---

## 💡 Примеры использования

### Пример 1: Запуск непрерывного мониторинга

```bash
python start.py
```

Бот будет анализировать рынок каждые 5 минут (или другой `monitor_timeframe`). При обнаружении входящего сигнала запускает MTF-анализ для подтверждения.

### Пример 2: Быстрая смена торговой пары

```python
from config import AnalysisConfig

# Bitcoin
cfg = AnalysisConfig(symbol='BTC/USDT')

# Ethereum
cfg = AnalysisConfig(symbol='ETH/USDT')

# Solana
cfg = AnalysisConfig(symbol='SOL/USDT')
```

### Пример 3: Быстрая смена биржи

```python
# Binance
cfg = AnalysisConfig(exchange='binance')

# Bybit
cfg = AnalysisConfig(exchange='bybit')

# Kraken
cfg = AnalysisConfig(exchange='kraken')
```

### Пример 4: Ручная настройка параметров индикатора

```python
from config import Config

# Агрессивная стратегия (быстрые сигналы)
config = Config(
    ma_period=10,
    ema_period=21,
    trend_lookback=10,
    angle_threshold_weak=15.0,
    angle_threshold_strong=40.0
)

# Консервативная стратегия (медленные, но надёжные сигналы)
config = Config(
    ma_period=100,
    ema_period=200,
    trend_lookback=50,
    angle_threshold_weak=3.0,
    angle_threshold_strong=10.0
)
```

### Пример 5: MTF анализ в коде

```python
from config import AnalysisConfig
from run import run_mtf_analysis

cfg = AnalysisConfig(symbol='BTC/USDT')
result = run_mtf_analysis(cfg)

if result and result['analysis']:
    final = result['analysis']['final_signal']
    print(f"Направление: {final['direction']}")
    print(f"Уверенность: {final['confidence']}")
    print(f"Сила: {final['strength']}")
```

---

## 💾 Сохранение результатов

### Имена файлов

| Режим | Формат имени |
|---|---|
| Одиночный | `{SYMBOL}_{TIMEFRAME}_signals.csv` |
| MTF | `MTF_{SYMBOL}_{TIMEFRAME}_signals.csv` |

### Структура CSV

| Колонка | Тип | Описание |
|---|---|---|
| `timestamp` | datetime | Дата и время свечи |
| `open` | float | Цена открытия |
| `high` | float | Максимальная цена |
| `low` | float | Минимальная цена |
| `close` | float | Цена закрытия |
| `volume` | float | Объём торгов |
| `MA` | float | Скользящая средняя |
| `EMA` | float | Экспоненциальная средняя |
| `ATR` | float | Средний истинный диапазон |
| `ADX` | float | Индекс направленного движения |
| `MA_Angle` | float | Угол наклона MA |
| `EMA_Angle` | float | Угол наклона EMA |
| `Divergence` | float | Расхождение MA/EMA (%) |
| `Signal` | str | Текстовый сигнал |
| `Signal_Strength` | float | Сила сигнала (-100 до +100) |
| `Trend_State` | str | Состояние тренда |
| `Trend_Confidence` | float | Уверенность в тренде |

### Отключение сохранения

```python
cfg = AnalysisConfig(save_csv=False)
```

---

## ❓ Часто задаваемые вопросы

**В: Почему MTF показывает `neutral_none`, а угол MA положительный?**

**О:** Это означает, что ADX < 25 — на рынке флэт. Система заблокировала торговлю, даже если углы выглядят привлекательно. Это защита от ложных сигналов.

**В: Какой таймфрейм лучше использовать?**

**О:** Зависит от стиля торговли:
- **Скальпинг:** `5m`, `15m`
- **Внутридневная:** `1h`
- **Свинг-трейдинг:** `4h`
- **Долгосрочная:** `1d`

Рекомендуется MTF с комбинацией `1h + 4h + 1d`.

**В: Почему много `Sideways` сигналов?**

**О:** Это нормально для флэта. Индикатор специально не генерирует ложные сигналы в боковике. Попробуйте уменьшить `angle_threshold_weak` для более частых сигналов.

**В: Как интерпретировать `Signal_Strength`?**

**О:** Это агрегированная оценка:
- `|strength| > 75` — очень сильный сигнал
- `|strength| > 50` — сильный сигнал
- `|strength| > 25` — умеренный сигнал
- `|strength| < 25` — слабый сигнал (лучше пропустить)

---

## 🔧 Импорты

```python
from config import Config, AnalysisConfig
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from mtf_analyzer import MultiTimeframeAnalyzer
from run import run_mtf_analysis, print_mtf_result
```

---

## 📄 Лицензия

Проект создан для образовательных и исследовательских целей. Используйте на свой страх и риск. Торговля криптовалютами сопряжена с высоким риском.