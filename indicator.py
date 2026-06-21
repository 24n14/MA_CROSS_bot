"""
Модуль технического индикатора.

Содержит класс:
- AdvancedTrendSignalIndicator: основной индикатор тренда
"""

import pandas as pd
import numpy as np
from scipy import stats
from typing import Dict
import warnings

from config import Config

warnings.filterwarnings('ignore')


class AdvancedTrendSignalIndicator:
    """
    Индикатор с анализом тренда по N-свечам и углом расхождения MA/EMA.

    Анализирует:
    - Угол наклона скользящих средних
    - Расхождение между MA и EMA
    - Положение цены относительно скользящих
    - Тип свечи (бычья/медвежья)

    Examples:
        >>> config = Config.for_timeframe('4h')
        >>> indicator = AdvancedTrendSignalIndicator(config)
        >>> result = indicator.generate_signal(df)
    """

    def __init__(self, config: Config = Config()):
        """
        Инициализация индикатора.

        Args:
            config: конфигурация параметров
        """
        self.config = config

    def calculate_angle(self, series: pd.Series) -> pd.Series:
        """
        Расчет угла наклона скользящей средней в градусах.

        Использует линейную регрессию для определения наклона
        за последние trend_lookback свечей.

        Формула: angle = arctan(slope / price * 100)

        Args:
            series: ряд значений скользящей средней

        Returns:
            Series с углами в градусах
        """
        angles = pd.Series(index=series.index, dtype=float)

        for i in range(self.config.trend_lookback, len(series)):
            if self.config.use_linear_regression:
                y = series.iloc[i - self.config.trend_lookback:i + 1].values
                x = np.arange(len(y))

                if len(y) > 1 and not np.isnan(y).any():
                    slope, _, r_value, _, _ = stats.linregress(x, y)
                    angle = np.degrees(np.arctan(slope / series.iloc[i] * 100))
                else:
                    angle = 0.0
            else:
                if i >= self.config.trend_lookback:
                    price_change = series.iloc[i] - series.iloc[i - self.config.trend_lookback]
                    price_avg = series.iloc[i]
                    angle = np.degrees(np.arctan(price_change / (price_avg * self.config.trend_lookback)))
                else:
                    angle = 0.0

            angles.iloc[i] = angle

        return angles

    #@staticmethod
    def calculate_divergence(self, ma: pd.Series, ema: pd.Series) -> pd.Series:
        """
        Расчет расхождения между MA и EMA в процентах.

        Формула: divergence = |(MA - EMA) / EMA * 100|

        Args:
            ma: ряд значений MA
            ema: ряд значений EMA

        Returns:
            Series с расхождением в процентах
        """
        divergence = ((ma - ema) / ema * 100).abs()
        return divergence

    def determine_trend_strength(self,
                                 ma_angle: float,
                                 ema_angle: float,
                                 divergence: float,
                                 ma_value: float,
                                 ema_value: float) -> Dict:
        """
        Определение силы тренда на основе углов и расхождения.

        Логика:
        1. Если оба угла > порога → восходящий тренд
        2. Если оба угла < -порога → нисходящий тренд
        3. Иначе смотрим на расхождение и положение MA/EMA

        Args:
            ma_angle: угол наклона MA
            ema_angle: угол наклона EMA
            divergence: расхождение MA/EMA (%)
            price_vs_ma: отклонение цены от MA (%)
            ma_value: значение MA
            ema_value: значение EMA

        Returns:
            Словарь с направлением, силой и уверенностью
        """
        trend_info = {
            'direction': 'neutral',
            'strength': 'none',
            'confidence': 0.0
        }

        # Определяем направление тренда
        if ma_angle > self.config.angle_threshold_weak and ema_angle > 0:
            trend_info['direction'] = 'up'
        elif ma_angle < -self.config.angle_threshold_weak and ema_angle < 0:
            trend_info['direction'] = 'down'
        else:
            if divergence > self.config.divergence_threshold:
                if ma_value is not None and ema_value is not None:
                    if ma_value > ema_value:
                        trend_info['direction'] = 'up'
                    else:
                        trend_info['direction'] = 'down'
                else:
                    if ma_angle > 0:
                        trend_info['direction'] = 'up'
                    elif ma_angle < 0:
                        trend_info['direction'] = 'down'

        # Определяем силу тренда
        avg_angle_abs = (abs(ma_angle) + abs(ema_angle)) / 2

        if avg_angle_abs >= self.config.angle_threshold_strong and divergence > self.config.divergence_threshold:
            trend_info['strength'] = 'strong'
            trend_info['confidence'] = 0.9
        elif avg_angle_abs >= self.config.angle_threshold_weak and divergence > self.config.divergence_threshold / 2:
            trend_info['strength'] = 'moderate'
            trend_info['confidence'] = 0.7
        elif avg_angle_abs >= self.config.angle_threshold_weak:
            trend_info['strength'] = 'weak'
            trend_info['confidence'] = 0.5
        else:
            trend_info['strength'] = 'none'
            trend_info['confidence'] = 0.3

        return trend_info

    def generate_signal(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Генерация сигналов с учетом тренда и углов.

        Добавляет к DataFrame колонки:
        - MA, EMA: скользящие средние
        - MA_Angle, EMA_Angle: углы наклона
        - Divergence: расхождение
        - Signal: текстовый сигнал
        - Signal_Strength: сила сигнала (-100 до +100)
        - Trend_State: состояние тренда
        - Trend_Confidence: уверенность в тренде

        Args:
            df: DataFrame с колонками open, high, low, close

        Returns:
            DataFrame с добавленными сигналами
        """
        df = df.copy()

        # Расчет скользящих средних
        df['MA'] = df['close'].rolling(window=self.config.ma_period).mean()
        df['EMA'] = df['close'].ewm(span=self.config.ema_period, adjust=False).mean()

        # Расчет углов
        df['MA_Angle'] = self.calculate_angle(df['MA'])
        df['EMA_Angle'] = self.calculate_angle(df['EMA'])

        # Расчет расхождения
        df['Divergence'] = self.calculate_divergence(ma=df['MA'], ema=df['EMA'])

        # Сглаживание углов если нужно
        if self.config.smooth_angle:
            df['MA_Angle'] = df['MA_Angle'].rolling(window=3).mean()
            df['EMA_Angle'] = df['EMA_Angle'].rolling(window=3).mean()

        signals = []
        signal_strengths = []
        trend_descriptions = []
        angle_info = []

        for i in range(len(df)):
            current_close = df['close'].iloc[i]
            current_open = df['open'].iloc[i]
            current_ma = df['MA'].iloc[i]
            current_ema = df['EMA'].iloc[i]

            if pd.isna(current_ma) or pd.isna(current_ema):
                signals.append('⚪ Нет данных')
                signal_strengths.append(0)
                trend_descriptions.append('')
                angle_info.append(0.0)
                continue

            is_bullish = current_close > current_open
            is_bearish = current_close < current_open

            if i >= self.config.trend_lookback:

                trend_info = self.determine_trend_strength(
                    ma_angle=df['MA_Angle'].iloc[i],
                    ema_angle=df['EMA_Angle'].iloc[i],
                    divergence=df['Divergence'].iloc[i],
                    ma_value=current_ma,
                    ema_value=current_ema
                )
            else:
                trend_info = {'direction': 'neutral', 'strength': 'none', 'confidence': 0.3}

            signal = self._get_enhanced_signal(
                current_close, current_open, current_ma, current_ema,
                is_bullish, is_bearish,
                trend_info, df['Divergence'].iloc[i],
                df['MA_Angle'].iloc[i], df['EMA_Angle'].iloc[i]
            )

            signals.append(signal)

            signal_strength = self._calculate_signal_strength(
                trend_info, df['Divergence'].iloc[i],
                is_bullish, is_bearish
            )
            signal_strengths.append(signal_strength)

            trend_desc = f"{trend_info['direction']}_{trend_info['strength']}"
            trend_descriptions.append(trend_desc)
            angle_info.append(df['MA_Angle'].iloc[i])

        df['Signal'] = signals
        df['Signal_Strength'] = signal_strengths
        df['Trend_State'] = trend_descriptions
        df['MA_Angle_Final'] = angle_info
        df['Trend_Confidence'] = df['Trend_State'].apply(
            lambda x: 0.9 if 'strong' in str(x) else (0.7 if 'moderate' in str(x) else 0.3)
        )

        return df

    def _get_enhanced_signal(self,
                             c: float, o: float,
                             ma: float, ema: float,
                             is_bullish: bool, is_bearish: bool,
                             trend_info: dict,
                             divergence: float,
                             ma_angle: float, ema_angle: float) -> str:
        """
        Получение улучшенного сигнала с учетом всех факторов.

        Логика основана на:
        - Положении цены относительно MA/EMA
        - Типе свечи (бычья/медвежья)
        - Направлении и силе тренда
        - Комбинированном весе (тренд + расхождение)

        Args:
            c: цена закрытия
            o: цена открытия
            ma: значение MA
            ema: значение EMA
            is_bullish: бычья свеча
            is_bearish: медвежья свеча
            trend_info: информация о тренде
            divergence: расхождение MA/EMA
            ma_angle: угол MA
            ema_angle: угол EMA

        Returns:
            Текстовый сигнал
        """
        above_all = c > ma and o > ma
        below_all = c < ma and o < ma
        between_up = c > ma and o < ma
        between_down = c < ma and o > ma

        trend_weight = trend_info['confidence']
        divergence_factor = min(divergence * 10, 1.0)
        combined_weight = (trend_weight + divergence_factor) / 2

        if trend_info['direction'] == 'up':
            if above_all and is_bullish:
                if trend_info['strength'] in ['strong', 'moderate']:
                    signal = '🟢🟢 STRONG BULLISH'
                else:
                    signal = '🟢 Bullish'
            elif between_up and is_bullish:
                signal = '🟡 Weak Bullish (Hold)'
            elif between_down and is_bearish:
                if combined_weight > 0.7:
                    signal = '🔴🔴 STRONG BEARISH REVERSAL'
                else:
                    signal = '🔴 Bearish Warning'
            elif below_all and is_bearish:
                signal = '⚪ Counter-Trend Bearish'
            else:
                signal = '⚪ Neutral'

        elif trend_info['direction'] == 'down':
            if below_all and is_bearish:
                if trend_info['strength'] in ['strong', 'moderate']:
                    signal = '🔴🔴 STRONG BEARISH'
                else:
                    signal = '🔴 Bearish'
            elif between_down and is_bearish:
                signal = '🟠 Weak Bearish (Hold)'
            elif between_up and is_bullish:
                if combined_weight > 0.7:
                    signal = '🟢🟢 STRONG BULLISH REVERSAL'
                else:
                    signal = '🟢 Bullish Warning'
            elif above_all and is_bullish:
                signal = '⚪ Counter-Trend Bullish'
            else:
                signal = '⚪ Neutral'
        else:
            if above_all and is_bullish:
                signal = '🟡 Range High'
            elif below_all and is_bearish:
                signal = '🟡 Range Low'
            else:
                signal = '⚪ Sideways'

        return signal

    def _calculate_signal_strength(self,
                                   trend_info: dict,
                                   divergence: float,
                                   is_bullish: bool,
                                   is_bearish: bool) -> float:
        """
        Расчет числовой силы сигнала от -100 до +100.

        Базовая сила зависит от направления тренда и типа свечи.
        Модификаторы: сила тренда (x1.2-x1.5) и расхождение (±divergence*5).

        Args:
            trend_info: информация о тренде
            divergence: расхождение MA/EMA
            is_bullish: бычья свеча
            is_bearish: медвежья свеча

        Returns:
            Числовая сила сигнала (-100 до +100)
        """
        base_strength = 0

        if trend_info['direction'] == 'up':
            if is_bullish:
                base_strength = 50
            elif is_bearish:
                base_strength = -30

            if trend_info['strength'] == 'strong':
                base_strength *= 1.5
            elif trend_info['strength'] == 'moderate':
                base_strength *= 1.2

        elif trend_info['direction'] == 'down':
            if is_bearish:
                base_strength = -50
            elif is_bullish:
                base_strength = 30

            if trend_info['strength'] == 'strong':
                base_strength *= 1.5
            elif trend_info['strength'] == 'moderate':
                base_strength *= 1.2

        divergence_impact = divergence * 5 * (1 if base_strength > 0 else -1)
        base_strength += divergence_impact

        return max(min(base_strength, 100), -100)
