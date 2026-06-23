Многофункциональный индикатор технического анализа с мультитаймфреймовым анализом тренда на основе 
углов расхождения скользящих средних (MA/EMA).


indicator
├── config.py          # Конфигурации
├── exchange.py        # Загрузчик данных
├── indicator.py       # Основной индикатор
├── mtf_analyzer.py    # MTF анализатор
├── run.py             # Функции запуска и вывода
├── start.py           # Точка входа
└── requirements.txt   # Зависимости

# Только MTF
analysis_config = AnalysisConfig(
    enable_mtf=True,
    enable_single=False,
    enable_compare=False
)

# Только одиночный таймфрейм
analysis_config = AnalysisConfig(
    enable_mtf=False,
    enable_single=True,
    enable_compare=False
)

# MTF + Одиночный + Сравнение
analysis_config = AnalysisConfig(
    enable_mtf=True,
    enable_single=True,
    enable_compare=True
)

# Быстрое переключение таймфреймов
analysis_config = AnalysisConfig(
    enable_mtf=False,
    enable_single=True,
    single_timeframe='1h'  # Меняем на часовой
)

# Advanced Trend Signal Indicator


## 📋 Содержание

- [Возможности](#возможности)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Архитектура](#архитектура)
- [Описание классов и функций](#описание-классов-и-функций)
- [Настройка режимов](#настройка-режимов)
- [Конфигурация](#конфигурация)
- [Сигналы](#сигналы)
- [Примеры использования](#примеры-использования)
- [Сохранение результатов](#сохранение-результатов)

## Возможности

- ✅ Анализ тренда по углу наклона MA/EMA
- ✅ Мультитаймфреймовый анализ (MTF)
- ✅ Автоматический подбор параметров под таймфрейм
- ✅ Числовая оценка силы сигнала (-100 до +100)
- ✅ Загрузка реальных данных с бирж (Binance, Bybit, Kraken и др.)
- ✅ Сохранение результатов в CSV
- ✅ Гибкое включение/выключение режимов анализа

### Требования
pip install ccxt pandas numpy scipy

Архитектура

├── Config                  # Параметры индикатора (MA, EMA, углы)
│   └── for_timeframe()     # Автоподбор под таймфрейм
├── AnalysisConfig          # Настройка режимов работы (True/False)
├── ExchangeDataLoader      # Загрузка данных с бирж
│   ├── fetch_ohlcv()       # Один таймфрейм
│   └── load_multiple_timeframes()  # Несколько таймфреймов
├── AdvancedTrendSignalIndicator   # Основной индикатор
│   ├── calculate_angle()          # Угол наклона
│   ├── calculate_divergence()     # Расхождение MA/EMA
│   ├── determine_trend_strength() # Определение тренда
│   ├── generate_signal()          # Генерация сигналов
│   ├── _get_enhanced_signal()     # Логика сигналов
│   └── _calculate_signal_strength() # Сила сигнала
└── MultiTimeframeAnalyzer   # MTF анализатор
    ├── load_and_analyze()   # Загрузка и анализ
    ├── _calculate_final_signal()  # Агрегация сигналов
    └── print_analysis()     # Вывод результатов

Описание классов и функций
Config

Назначение: Параметры технического индикатора
Параметр	            Тип	   Значение	   Описание
ma_period	            int	    5	    Период простой скользящей средней
ema_period	            int	    20	    Период экспоненциальной скользящей средней
trend_lookback	        int	    50	    Количество свечей для анализа тренда
angle_threshold_strong	float	30.0	Угол для сильного тренда (градусы)
angle_threshold_weak	float	10.0	Угол для слабого тренда (градусы)
divergence_threshold	float	0.1	    Порог расхождения MA/EMA (%)
use_linear_regression	bool	True	Использовать линейную регрессию для расчета угла
smooth_angle	        bool	True	Сглаживать угол (скользящее среднее по 3 периодам)

Config.for_timeframe(timeframe: str) -> Config
Назначение: Автоматически подбирает оптимальные параметры под таймфрейм
Логика подбора:
Таймфрейм	ma_period	ema_period	trend_lookback	angle_strong	angle_weak	divergence
1m/5m/15m	10	          10	           5	       45.0°	      20.0°       0.10%
30m/1h	    20	          20	           10	       30.0°	      15.0°	      0.15%
4h	        50	          50	           20	       15.0°	      5.0°	      0.30%
1d/1w	    200	          50	           30	       10.0°	      3.0°	      0.50%

AnalysisConfig

Назначение: Управление режимами работы индикатора
Параметр	    Тип	  По умолчанию	Описание
enable_mtf	    bool	True	Включить мультитаймфреймовый анализ
enable_single	bool	False	Включить анализ одного таймфрейма
enable_compare	bool	False	Включить сравнение MTF и Single

symbol	          str	'BTC/USDT'	Торговая пара
exchange	      str	'binance'	Биржа для загрузки данных
limit	          int	500	Количество загружаемых свечей
mtf_timeframes	  tuple	('1h', '4h', '1d')	Таймфреймы для MTF анализа
single_timeframe  str	'4h'	Таймфрейм для одиночного режима
save_csv	      bool	True	Сохранять результаты в CSV файлы
verbose	          bool	True	Подробный вывод в консоль

ExchangeDataLoader
Назначение: Загрузка рыночных данных с бирж через библиотеку CCXT
__init__(exchange_name: str = 'binance')
Инициализация подключения к бирже.
Поддерживаемые биржи: binance, bybit, kraken, kucoin, okx, huobi и другие (всего 100+ через CCXT)
Пример:
# Spot рынок Binance
loader = ExchangeDataLoader('binance')
# Futures рынок Bybit
loader = ExchangeDataLoader('bybit')
loader.exchange.options['defaultType'] = 'future'

fetch_ohlcv(symbol, timeframe, limit, since) -> pd.DataFrame

Загружает свечные данные с биржи.

Параметры:

    symbol: str — торговая пара ('BTC/USDT', 'ETH/USDT')

    timeframe: str — таймфрейм ('1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w')

    limit: int — количество свечей (максимум зависит от биржи, обычно 1000-2000)

    since: str — начальная дата в формате 'YYYY-MM-DD' или None

Возвращает: pd.DataFrame с колонками: open, high, low, close, volume

Пример:
loader = ExchangeDataLoader('binance')

# Последние 500 свечей
df = loader.fetch_ohlcv('BTC/USDT', '4h', 500)

# Свечи с определенной даты
df = loader.fetch_ohlcv('ETH/USDT', '1h', 1000, since='2024-01-01')

load_multiple_timeframes(symbol, timeframes, limit) -> Dict[str, pd.DataFrame]

Загружает данные для нескольких таймфреймов одновременно.

Параметры:

    symbol: str — торговая пара

    timeframes: tuple — кортеж таймфреймов

    limit: int — количество свечей для каждого таймфрейма

Возвращает: словарь {timeframe: DataFrame}

Пример:
loader = ExchangeDataLoader('binance')
data = loader.load_multiple_timeframes(
    'BTC/USDT',
    timeframes=('15m', '1h', '4h', '1d'),
    limit=500
)

# Доступ к данным
df_1h = data['1h']
df_4h = data['4h']

AdvancedTrendSignalIndicator

Назначение: Основной индикатор для анализа тренда и генерации сигналов
calculate_angle(series: pd.Series) -> pd.Series

Рассчитывает угол наклона скользящей средней в градусах.

Алгоритм:

    Берет последние trend_lookback значений

    Строит линейную регрессию

    Вычисляет угол: angle = arctan(slope / price * 100)

Интерпретация:

    > 0° — линия растет (восходящий тренд)

    < 0° — линия падает (нисходящий тренд)

    ≈ 0° — линия горизонтальна (флэт)

calculate_divergence(ma: pd.Series, ema: pd.Series) -> pd.Series

Рассчитывает расхождение между MA и EMA в процентах.

Формула: divergence = |(MA - EMA) / EMA * 100|

Интерпретация:

    Большое расхождение → сильный тренд

    Маленькое расхождение → слабый тренд или флэт

    Расхождение → 0 → готовится пересечение (смена тренда)

determine_trend_strength(ma_angle, ema_angle, divergence, price_vs_ma, ma_value, ema_value) -> Dict

Определяет направление и силу тренда.

Логика определения направления:

    Если оба угла > порога → up

    Если оба угла < -порога → down

    Если расхождение > порога:

        MA > EMA → up

        MA < EMA → down

    Иначе → neutral

Логика определения силы:

    Средний угол > strong_threshold И расхождение > divergence_threshold → strong

    Средний угол > weak_threshold И расхождение > divergence_threshold/2 → moderate

    Средний угол > weak_threshold → weak

    Иначе → none

Возвращает:
{
    'direction': 'up' | 'down' | 'neutral',
    'strength': 'strong' | 'moderate' | 'weak' | 'none',
    'confidence': 0.0 до 1.0
}
generate_signal(df: pd.DataFrame) -> pd.DataFrame

Главный метод генерации сигналов. Добавляет к DataFrame расчетные колонки.

Добавляемые колонки:
Колонка	            Описание
MA	                Значение простой скользящей средней
EMA	                Значение экспоненциальной скользящей средней
MA_Angle            Угол наклона MA в градусах
EMA_Angle           Угол наклона EMA в градусах
Divergence          Расхождение MA/EMA в %
Signal	            Текстовый торговый сигнал
Signal_Strength	    Числовая сила сигнала (-100 до +100)
Trend_State	        Состояние тренда (например up_moderate)
Trend_Confidence	Уверенность в тренде (0.0 - 1.0)

Пример:
indicator = AdvancedTrendSignalIndicator(config)
result = indicator.generate_signal(df)

# Последний сигнал
print(result['Signal'].iloc[-1])
print(f"Сила: {result['Signal_Strength'].iloc[-1]}")

_get_enhanced_signal(c, o, ma, ema, is_bullish, is_bearish, trend_info, divergence, ma_angle, ema_angle) -> str

Внутренний метод. Генерирует текстовый сигнал на основе всех факторов.

Логика сигналов:

Восходящий тренд (direction = 'up'):
Условие	                                                    Сигнал
Цена > MA/EMA + бычья свеча + сильный тренд	                🟢🟢 STRONG BULLISH
Цена > MA/EMA + бычья свеча	                                🟢 Bullish
Открытие < MA, закрытие > MA + бычья свеча	                🟡 Weak Bullish (Hold)
Открытие > MA, закрытие < MA + медвежья свеча + высокий вес	🔴🔴 STRONG BEARISH REVERSAL
Открытие > MA, закрытие < MA + медвежья свеча	            🔴 Bearish Warning
Цена < MA/EMA + медвежья свеча	                            ⚪ Counter-Trend Bearish

Нисходящий тренд (direction = 'down'):
Условие	                                                    Сигнал
Цена < MA/EMA + медвежья свеча + сильный тренд	            🔴🔴 STRONG BEARISH
Цена < MA/EMA + медвежья свеча	                            🔴 Bearish
Открытие > MA, закрытие < MA + медвежья свеча	            🟠 Weak Bearish (Hold)
Открытие < MA, закрытие > MA + бычья свеча + высокий вес	🟢🟢 STRONG BULLISH REVERSAL
Открытие < MA, закрытие > MA + бычья свеча	                🟢 Bullish Warning
Цена > MA/EMA + бычья свеча	                                ⚪ Counter-Trend Bullish

Боковой тренд (direction = 'neutral'):
Условие	                                                   Сигнал
Цена > MA/EMA + бычья свеча	                               🟡 Range High
Цена < MA/EMA + медвежья свеча	                           🟡 Range Low
Все остальное	                                           ⚪ Sideways

_calculate_signal_strength(trend_info, divergence, is_bullish, is_bearish) -> float
Рассчитывает числовую силу сигнала от -100 до +100.
Базовая сила:
    Восходящий тренд + бычья свеча = +50
    Восходящий тренд + медвежья свеча = -30
    Нисходящий тренд + медвежья свеча = -50
    Нисходящий тренд + бычья свеча = +30

Модификаторы:
    Сильный тренд: ×1.5
    Умеренный тренд: ×1.2
    Расхождение: ±(divergence × 5)

Шкала интерпретации:
Диапазон	  Значение
+75 до +100	  Очень сильный бычий сигнал
+50 до +75	  Сильный бычий
+25 до +50	  Умеренный бычий
0 до +25	  Слабый бычий
0 до -25	  Слабый медвежий
-25 до -50	  Умеренный медвежий
-50 до -75	  Сильный медвежий
-75 до -100	  Очень сильный медвежий сигнал

MultiTimeframeAnalyzer
Назначение: Мультитаймфреймовый анализ для фильтрации ложных сигналов и повышения точности
__init__(timeframes, exchange_name, symbol)

Инициализация MTF анализатора.
Параметры:
    timeframes: List[str] — список таймфреймов (по умолчанию ['1h', '4h', '1d'])
    exchange_name: str — биржа
    symbol: str — торговая пара

Пример:
mtf = MultiTimeframeAnalyzer(
    timeframes=['15m', '1h', '4h'],
    exchange_name='binance',
    symbol='BTC/USDT'
)
load_and_analyze(limit: int = 500) -> Dict

Загружает данные для всех таймфреймов и проводит полный анализ.

Процесс:

    Загружает данные через ExchangeDataLoader.load_multiple_timeframes()

    Для каждого ТФ создает индикатор с авто-конфигурацией (Config.for_timeframe())

    Генерирует сигналы для каждого ТФ

    Агрегирует результаты

Возвращает:
{
    'symbol': 'BTC/USDT',
    'timeframes': ['1h', '4h', '1d'],
    'timestamp': datetime,
    'mtf_details': [...],  # Детали по каждому ТФ
    'final_signal': {...},  # Агрегированный сигнал
    'results': {...}        # Полные DataFrame для каждого ТФ
}
_calculate_final_signal(summary: List[Dict]) -> Dict

Агрегирует сигналы с разных таймфреймов.

Веса таймфреймов (старшие ТФ имеют больший вес):
Таймфрейм	Вес
1m	        0.10
5m	        0.15
15m	        0.20
30m	        0.25
1h	        0.35
4h	        0.50
1d	        0.70
1w	        0.90

Формула взвешенной силы:
final_strength = Σ(signal_strength × tf_weight) / Σ(tf_weight)

Логика определения уверенности:
Согласованность ТФ	Уверенность
≥ 80%	VERY HIGH
≥ 67%	HIGH
≥ 50%	MODERATE
< 50%	LOW

Дополнительное правило:

    Если младший ТФ противоречит старшему → уверенность понижается на 1 уровень

Возвращает:
{
    'direction': 'BULLISH' | 'BEARISH' | 'NEUTRAL',
    'confidence': 'VERY HIGH' | 'HIGH' | 'MODERATE' | 'LOW',
    'strength': float,          # Взвешенная сила
    'agreement': float,         # % согласованности
    'buy_signals': int,         # Количество бычьих ТФ
    'sell_signals': int,        # Количество медвежьих ТФ
    'total_timeframes': int     # Всего ТФ
}

print_analysis(analysis: Dict)

Выводит форматированную таблицу с результатами MTF анализа.

Пример вывода:
============================================================
📊 MTF АНАЛИЗ: BTC/USDT
🕐 2024-01-15 14:00
============================================================

ТФ     Цена       Сигнал                         Сила   Тренд             Угол
---------------------------------------------------------------------------------
1h     $43250.00  🟢 Bullish                     65.5   up_moderate       12.34°
4h     $43250.00  🟡 Weak Bullish (Hold)          25.3   up_weak            4.56°
1d     $43250.00  🟢🟢 STRONG BULLISH             85.2   up_strong         18.90°

============================================================
🎯 ИТОГОВЫЙ СИГНАЛ
============================================================
Направление:  🟢 BULLISH
Уверенность:  HIGH
Сила сигнала: 58.7
Согласие ТФ:  67%
Buy/Sell:     2/0

💡 РЕКОМЕНДАЦИЯ:
   ✅ Можно рассматривать LONG позиции

Вспомогательные функции
run_single_analysis(analysis_config: AnalysisConfig) -> Dict

Запускает анализ для одного таймфрейма.

Возвращает:
{
    'result': pd.DataFrame,  # DataFrame с сигналами
    'config': Config,        # Конфигурация индикатора
    'dataframe': pd.DataFrame  # Исходные данные
}
run_mtf_analysis(analysis_config: AnalysisConfig) -> Dict

Запускает мультитаймфреймовый анализ.

Возвращает:
{
    'analyzer': MultiTimeframeAnalyzer,
    'analysis': Dict  # Результаты анализа
}

print_single_result(single_data: Dict, analysis_config: AnalysisConfig)

Выводит результаты одиночного анализа в консоль.
print_comparison(mtf_data: Dict, single_data: Dict, analysis_config: AnalysisConfig)

Сравнивает результаты MTF и одиночного анализа. Показывает согласованность или расхождение сигналов.
Настройка режимов

Все режимы включаются/выключаются через булевы флаги в AnalysisConfig:
analysis_config = AnalysisConfig(
    enable_mtf=True,        # True = включить MTF
    enable_single=False,    # False = выключить одиночный
    enable_compare=False    # False = выключить сравнение
)
Возможные комбинации режимов
enable_mtf	enable_single	enable_compare	Результат
True	False	False	Только мультитаймфреймовый анализ
False	True	False	Только анализ одного таймфрейма
True	True	False	MTF анализ + одиночный анализ
True	True	True	MTF + одиночный + сравнение результатов
False	False	True	Ничего не произойдет (нужен хотя бы один режим)
Предустановленные сценарии

Сценарий 1: Быстрая проверка рынка
config = AnalysisConfig(
    enable_mtf=False,
    enable_single=True,
    single_timeframe='1h',
    limit=200,
    verbose=True
)
Сценарий 2: Полный анализ для торговли
config = AnalysisConfig(
    enable_mtf=True,
    enable_single=True,
    enable_compare=True,
    symbol='BTC/USDT',
    mtf_timeframes=('1h', '4h', '1d'),
    save_csv=True
)

Сценарий 3: Мониторинг портфеля
config = AnalysisConfig(
    enable_mtf=True,
    enable_single=False,
    symbol='ETH/USDT',
    mtf_timeframes=('4h', '1d', '1w'),
    limit=300
)
Конфигурация
# Bitcoin
config = AnalysisConfig(symbol='BTC/USDT')

# Ethereum
config = AnalysisConfig(symbol='ETH/USDT')

# Solana
config = AnalysisConfig(symbol='SOL/USDT')

Быстрая смена биржи
# Binance
config = AnalysisConfig(exchange='binance')

# Bybit
config = AnalysisConfig(exchange='bybit')

# Kraken
config = AnalysisConfig(exchange='kraken')

Быстрая смена таймфрейма
# Скальпинг (15 минут)
config = AnalysisConfig(
    enable_single=True,
    single_timeframe='15m'
)

# Дневной график
config = AnalysisConfig(
    enable_single=True,
    single_timeframe='1d'
)
Ручная настройка параметров индикатора
# Агрессивная стратегия (быстрые сигналы)
config = Config(
    ma_period=10,
    ema_period=10,
    trend_lookback=5,
    angle_threshold_weak=15.0,
    angle_threshold_strong=40.0
)

# Консервативная стратегия (медленные, но надежные сигналы)
config = Config(
    ma_period=100,
    ema_period=50,
    trend_lookback=50,
    angle_threshold_weak=3.0,
    angle_threshold_strong=10.0
)

Сигналы
Все типы сигналов
Сигнал	                Эмодзи	Значение	Рекомендуемое действие
STRONG BULLISH	        🟢🟢	Сильный восходящий тренд, цена выше MA/EMA	Открывать/удерживать LONG
Bullish	                🟢	Умеренный восходящий тренд	Можно рассматривать LONG
Weak Bullish (Hold)	    🟡	Слабый бычий сигнал, цена между MA и EMA	Держать позицию, не добавлять
STRONG BULLISH REVERSAL	🟢🟢	Сильный разворот вверх из нисходящего тренда	Закрывать SHORT, искать вход в LONG
Bullish Warning	        🟢	Предупреждение о возможном развороте вверх	Готовиться к смене тренда
Counter-Trend Bullish	⚪	Бычий сигнал против нисходящего тренда	Не входить, ждать подтверждения
STRONG BEARISH	        🔴🔴	Сильный нисходящий тренд, цена ниже MA/EMA	Открывать/удерживать SHORT
Bearish	                🔴	Умеренный нисходящий тренд	Можно рассматривать SHORT
Weak Bearish (Hold)	    🟠	Слабый медвежий сигнал, цена между MA и EMA	Держать позицию, не добавлять
STRONG BEARISH REVERSAL	🔴🔴	Сильный разворот вниз из восходящего тренда	Закрывать LONG, искать вход в SHORT
Bearish Warning	        🔴	Предупреждение о возможном развороте вниз	Готовиться к смене тренда
Counter-Trend Bearish	⚪	Медвежий сигнал против восходящего тренда	Не входить, ждать подтверждения
Range High	            🟡	Цена у верхней границы боковика	Фиксировать прибыль LONG
Range Low	            🟡	Цена у нижней границы боковика	Искать вход в LONG
Sideways	            ⚪	Боковое движение, нет тренда	Не торговать, ждать пробой
Neutral	                ⚪	Нейтральный сигнал	Ждать более четкого сигнала
Шкала силы сигнала
-100 ═════ -75 ═════ -50 ═════ -25 ═════ 0 ═════ +25 ═════ +50 ═════ +75 ═════ +100
  🔴🔴      🔴       🔴       🟠       ⚪      🟡       🟢       🟢       🟢🟢
Максимально                                                          Максимально
медвежий                                                              бычий

Примеры использования
Пример 1: Проверка сигнала перед входом в сделку
# Настройка
config = AnalysisConfig(
    enable_mtf=True,
    enable_single=True,
    enable_compare=True,
    symbol='BTC/USDT',
    mtf_timeframes=('1h', '4h', '1d')
)

# Запуск
mtf_data = run_mtf_analysis(config)
single_data = run_single_analysis(config)

# Проверка
final = mtf_data['analysis']['final_signal']
if final['confidence'] in ['VERY HIGH', 'HIGH'] and final['direction'] != 'NEUTRAL':
    print(f"✅ Сигнал подтвержден: {final['direction']}")
    print(f"Сила: {final['strength']}, Согласие ТФ: {final['agreement']}%")
else:
    print("❌ Сигнал недостаточно сильный, пропускаем")

Пример 2: Сканирование нескольких пар
symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ADA/USDT']

for symbol in symbols:
    config = AnalysisConfig(
        enable_mtf=False,
        enable_single=True,
        symbol=symbol,
        single_timeframe='4h',
        verbose=False
    )
    
    single_data = run_single_analysis(config)
    if single_data:
        last_signal = single_data['result']['Signal'].iloc[-1]
        strength = single_data['result']['Signal_Strength'].iloc[-1]
        print(f"{symbol}: {last_signal} (Сила: {strength:.1f})")
    
    time.sleep(2)  # Задержка между запросами

Пример 3: Фильтрация только сильных сигналов

# Запускаем анализ
config = AnalysisConfig(enable_single=True, single_timeframe='4h')
single_data = run_single_analysis(config)

# Фильтруем STRONG сигналы
result = single_data['result']
strong_signals = result[result['Signal'].str.contains('STRONG', na=False)]

print(f"Найдено {len(strong_signals)} сильных сигналов за период")

# Показываем последние 5
for idx, row in strong_signals.tail(5).iterrows():
    print(f"{idx}: {row['Signal']} | Цена: ${row['close']:.2f} | Сила: {row['Signal_Strength']:.1f}")

Пример 4: Экспорт сигналов для TradingView
config = AnalysisConfig(
    enable_single=True,
    single_timeframe='4h',
    save_csv=True
)

single_data = run_single_analysis(config)
result = single_data['result']

# Создаем колонку с числовым сигналом для TradingView
result['TV_Signal'] = result['Signal'].map({
    '🟢🟢 STRONG BULLISH': 2,
    '🟢 Bullish': 1,
    '🟢🟢 STRONG BULLISH REVERSAL': 1,
    '⚪ Neutral': 0,
    '🔴 Bearish': -1,
    '🔴🔴 STRONG BEARISH': -2,
    '🔴🔴 STRONG BEARISH REVERSAL': -1,
}).fillna(0)

result.to_csv('tradingview_signals.csv')

Сохранение результатов
Имена файлов

Одиночный режим:
{BTC_USDT}_{4h}_signals.csv

MTF режим:
MTF_{BTC_USDT}_{1h}_signals.csv
MTF_{BTC_USDT}_{4h}_signals.csv
MTF_{BTC_USDT}_{1d}_signals.csv

Структура CSV файла
Колонка	Тип	Описание
timestamp	datetime	Дата и время свечи
open	float	Цена открытия
high	float	Максимальная цена
low	float	Минимальная цена
close	float	Цена закрытия
volume	float	Объем торгов
MA	float	Скользящая средняя
EMA	float	Экспоненциальная средняя
MA_Angle	float	Угол наклона MA
EMA_Angle	float	Угол наклона EMA
Divergence	float	Расхождение MA/EMA (%)
Signal	str	Текстовый сигнал
Signal_Strength	float	Сила сигнала (-100 до +100)
Trend_State	str	Состояние тренда
Trend_Confidence	float	Уверенность в тренде
Отключение сохранения
config = AnalysisConfig(
    enable_single=True,
    save_csv=False  # Не сохранять в CSV
)
Быстрые команды
# Запуск с настройками по умолчанию
python start.py

# Справка по классам и функциям
python -c "from indicator import *; help(AdvancedTrendSignalIndicator)"
python -c "from indicator import *; help(MultiTimeframeAnalyzer)"

# Проверка доступных пар на бирже
python -c "
from indicator import ExchangeDataLoader
loader = ExchangeDataLoader('binance')
loader.exchange.load_markets()
btc_pairs = [s for s in loader.exchange.symbols if '/USDT' in s]
print(f'Доступно {len(btc_pairs)} USDT пар')
"
Часто задаваемые вопросы

В: Почему MTF показывает up_none, а угол MA отрицательный?
О: Это означает формально восходящий тренд (MA > EMA), но с разворотными признаками (угол < 0). Система определила тренд по положению MA/EMA, но предупреждает о слабости. Следите за сигналом Counter-Trend Bearish — это подтверждает расхождение.

В: Какой таймфрейм лучше использовать?

О: Зависит от стиля торговли:

    Скальпинг: 5m, 15m

    Внутридневная: 1h

    Свинг-трейдинг: 4h

    Долгосрочная: 1d

Рекомендуется использовать MTF с комбинацией 1h + 4h + 1d.

В: Почему так много Neutral сигналов?

О: Это нормально для флэта. Индикатор специально не генерирует ложные сигналы в боковике. Попробуйте уменьшить angle_threshold_weak для более частых сигналов.

В: Как интерпретировать Signal_Strength?

О: Это агрегированная оценка:

    |strength| > 75 — очень сильный сигнал

    |strength| > 50 — сильный сигнал

    |strength| > 25 — умеренный сигнал

    |strength| < 25 — слабый сигнал (лучше пропустить)

ИМПОРТЫ
from config import Config, AnalysisConfig
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from mtf_analyzer import MultiTimeframeAnalyzer
from run import run_single_analysis, run_mtf_analysis

# Использование
config = AnalysisConfig(enable_single=True, symbol='ETH/USDT')
result = run_single_analysis(config)

MA-CROSS-bot/
├── logs/                  # Логи работы программы
│   └── bot_history.log    # Что происходило, ошибки, отладка
├── csv_history/           # Результаты анализа
│   ├── BTC_USDT_4h_signals.csv
│   ├── MTF_BTC_USDT_1h_signals.csv
│   ├── MTF_BTC_USDT_4h_signals.csv
│   └── MTF_BTC_USDT_1d_signals.csv
├── log.py
├── config.py
├── exchange.py
├── indicator.py
├── mtf_analyzer.py
├── run.py
└── start.py