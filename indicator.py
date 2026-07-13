"""
Оптимизированный модуль технического индикатора с защитой от флэта и ATR-нормализацией.

Содержит класс:
- AdvancedTrendSignalIndicator: основной индикатор тренда
"""

import pandas as pd
import numpy as np
import pandas_ta as ta  # Исправлено: правильный импорт
from scipy import stats
from typing import Dict, Optional, Tuple
import warnings
from config import Config

warnings.filterwarnings('ignore')


class AdvancedTrendSignalIndicator:
    """
    Индикатор с анализом тренда по N-свечам, динамическим ATR-фильтром волатильности
    и защитой от ложных сигналов во флэте (через ADX).

    Порог ADX для блокировки флэта берётся из Config.adx_flat_threshold.
    """

    # Маппинг Trend_State в короткие значения
    _TREND_STATE_MAP = {
        ('up', 'weak'): 'UP',
        ('up', 'moderate'): 'UP',
        ('up', 'strong'): 'UP',
        ('down', 'weak'): 'DOWN',
        ('down', 'moderate'): 'DOWN',
        ('down', 'strong'): 'DOWN',
        ('neutral', 'none'): 'NO_TREND',
    }

    def __init__(self, config: Config = Config()):
        """
        Инициализация индикатора.

        Args:
            config: объект конфигурации
        """
        self.config = config
        self.lookback = getattr(config, 'angle_lookback', 5)
        self.divergence_threshold = getattr(config, 'divergence_threshold', 0.2)
        self.angle_scale = getattr(config, 'angle_scale', 50.0)

    def calculate_angle(self, series: pd.Series, atr: pd.Series) -> pd.Series:
        """
        Расчет угла наклона скользящей средней с ATR-нормализацией.

        🔥 ИСПРАВЛЕНО:
        - Добавлен множитель масштабирования (angle_scale)
        - Динамический lookback для первых свечей
        - Обработка нулевых значений ATR

        Args:
            series: ряд данных (MA или EMA)
            atr: ряд ATR для нормализации

        Returns:
            pd.Series: углы наклона в градусах
        """
        angles = pd.Series(index=series.index, dtype=float)
        lookback = self.lookback

        for i in range(len(series)):
            # Проверка на NaN
            if pd.isna(series.iloc[i]) or pd.isna(atr.iloc[i]):
                angles.iloc[i] = 0.0
                continue

            # Динамический lookback для первых свечей
            current_lookback = min(i, lookback)
            if current_lookback < 2:
                angles.iloc[i] = 0.0
                continue

            # Расчет изменения цены за lookback периодов
            price_change = series.iloc[i] - series.iloc[i - current_lookback]

            # ATR за период
            atr_period = atr.iloc[i] * current_lookback

            if atr_period > 0:
                # 🔥 КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Нормализация с масштабированием
                # price_change / atr_period показывает, насколько изменилась цена
                # относительно ATR. Умножаем на angle_scale для получения
                # осмысленных углов (обычно 30-50)
                normalized_change = (price_change / atr_period) * self.angle_scale

                # Ограничиваем, чтобы избежать экстремальных углов
                normalized_change = np.clip(normalized_change, -10, 10)

                angle = np.degrees(np.arctan(normalized_change))
                angles.iloc[i] = angle
            else:
                angles.iloc[i] = 0.0

        return angles

    def calculate_divergence(self, ma: pd.Series, ema: pd.Series) -> pd.Series:
        """
        Расчет расхождения между МА и ЕМА в процентах.

        Args:
            ma: ряд скользящей средней
            ema: ряд экспоненциальной скользящей средней

        Returns:
            pd.Series: расхождение в процентах
        """
        # Используем abs() для получения абсолютного расхождения
        divergence = ((ma - ema) / ema * 100).abs()
        return divergence.fillna(0)

    def determine_trend_strength(
            self,
            ma_angle: float,
            ema_angle: float,
            divergence: float,
            current_adx: float,
            price_change: float = 0.0
    ) -> Dict:
        """
        Определение направления и силы тренда с учетом ADX-фильтра флэта
        и фильтра расхождения МА/ЕМА.

        🔥 ИСПРАВЛЕНО:
        - Исправлена опечатка adv_flat_threshold -> adx_flat_threshold
        - Добавлено использование дивергенции
        - Улучшено определение силы тренда

        Args:
            ma_angle: угол наклона MA
            ema_angle: угол наклона EMA
            divergence: расхождение MA/EMA
            current_adx: текущее значение ADX
            price_change: изменение цены за период

        Returns:
            Dict: информация о тренде
        """
        trend_info = {
            'direction': 'neutral',
            'strength': 'none',
            'confidence': 0.3,
            'divergence_detected': False,
            'divergence_strength': 0.0,
            'adx': current_adx
        }

        # --- ЗАЩИТА ОТ ФЛЭТА ---
        # 🔥 ИСПРАВЛЕНО: adx_flat_threshold (было adv_flat_threshold)
        adx_threshold = getattr(self.config, 'adx_flat_threshold', 25.0)

        # Даже во флэте проверяем дивергенцию
        if current_adx < adx_threshold:
            # Дивергенция может указывать на скорый разворот даже во флэте
            if abs(divergence) > self.divergence_threshold:
                trend_info['divergence_detected'] = True
                trend_info['divergence_strength'] = divergence

                # Слабая дивергенция может дать ранний сигнал
                if divergence > self.divergence_threshold:
                    trend_info['direction'] = 'up'
                    trend_info['strength'] = 'weak'
                    trend_info['confidence'] = 0.5
                elif divergence < -self.divergence_threshold:
                    trend_info['direction'] = 'down'
                    trend_info['strength'] = 'weak'
                    trend_info['confidence'] = 0.5
            return trend_info

        # Определяем доминирующий угол (максимальный по модулю)
        abs_ma = abs(ma_angle)
        abs_ema = abs(ema_angle)
        max_abs_angle = max(abs_ma, abs_ema)

        # Получаем пороги из конфига
        weak_threshold = getattr(self.config, 'angle_threshold_weak', 3.0)

        # Если ни один угол не превышает слабый порог – тренда нет
        if max_abs_angle < weak_threshold:
            # Но проверяем дивергенцию
            if abs(divergence) > self.divergence_threshold:
                trend_info['divergence_detected'] = True
                trend_info['divergence_strength'] = divergence
                if divergence > self.divergence_threshold:
                    trend_info['direction'] = 'up'
                    trend_info['strength'] = 'weak'
                    trend_info['confidence'] = 0.4
                elif divergence < -self.divergence_threshold:
                    trend_info['direction'] = 'down'
                    trend_info['strength'] = 'weak'
                    trend_info['confidence'] = 0.4
            return trend_info

        # Определяем направление по углу с большим абсолютным значением
        if abs_ma >= abs_ema:
            dominant_angle = ma_angle
        else:
            dominant_angle = ema_angle

        if dominant_angle > weak_threshold:
            trend_info['direction'] = 'up'
        elif dominant_angle < -weak_threshold:
            trend_info['direction'] = 'down'
        else:
            return trend_info

        # --- ОПРЕДЕЛЕНИЕ СИЛЫ ТРЕНДА ---
        avg_angle_abs = (abs_ma + abs_ema) / 2
        moderate_threshold = getattr(self.config, 'angle_threshold_moderate', 8.0)
        strong_threshold = getattr(self.config, 'angle_threshold_strong', 15.0)

        # Сила на основе углов
        if avg_angle_abs >= strong_threshold:
            trend_info['strength'] = 'strong'
            trend_info['confidence'] = 0.9
        elif avg_angle_abs >= moderate_threshold:
            trend_info['strength'] = 'moderate'
            trend_info['confidence'] = 0.7
        else:
            trend_info['strength'] = 'weak'
            trend_info['confidence'] = 0.5

        # Корректировка силы на основе ADX
        if current_adx >= 50:
            trend_info['strength'] = 'strong'
            trend_info['confidence'] = min(trend_info['confidence'] + 0.1, 1.0)
        elif current_adx >= 35:
            if trend_info['strength'] == 'weak':
                trend_info['strength'] = 'moderate'
                trend_info['confidence'] += 0.1

        # --- ИСПОЛЬЗОВАНИЕ ДИВЕРГЕНЦИИ ---
        if abs(divergence) > self.divergence_threshold:
            trend_info['divergence_detected'] = True
            trend_info['divergence_strength'] = divergence

            # Дивергенция усиливает сигнал
            if trend_info['direction'] == 'up' and divergence > 0:
                # Бычья дивергенция: усиливаем бычий сигнал
                if trend_info['strength'] == 'weak':
                    trend_info['strength'] = 'moderate'
                    trend_info['confidence'] += 0.1
                elif trend_info['strength'] == 'moderate':
                    trend_info['strength'] = 'strong'
                    trend_info['confidence'] += 0.1
            elif trend_info['direction'] == 'down' and divergence < 0:
                # Медвежья дивергенция: усиливаем медвежий сигнал
                if trend_info['strength'] == 'weak':
                    trend_info['strength'] = 'moderate'
                    trend_info['confidence'] += 0.1
                elif trend_info['strength'] == 'moderate':
                    trend_info['strength'] = 'strong'
                    trend_info['confidence'] += 0.1

            # Предупреждение о возможном развороте
            if trend_info['direction'] == 'up' and divergence < -self.divergence_threshold:
                trend_info['divergence_detected'] = True
                trend_info['divergence_strength'] = divergence
                # Медвежья дивергенция при бычьем тренде - предупреждение
                trend_info['confidence'] = max(trend_info['confidence'] - 0.2, 0.1)
            elif trend_info['direction'] == 'down' and divergence > self.divergence_threshold:
                trend_info['divergence_detected'] = True
                trend_info['divergence_strength'] = divergence
                # Бычья дивергенция при медвежьем тренде - предупреждение
                trend_info['confidence'] = max(trend_info['confidence'] - 0.2, 0.1)

        return trend_info

    def generate_signal(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Генерация сигналов с комплексной фильтрацией волатильности и флэта.

        🔥 ИСПРАВЛЕНО:
        - Исправлен расчет углов
        - Добавлено использование дивергенции
        - Смягчены условия для сигналов
        - Signal_Strength привязан к ADX

        Args:
            df: DataFrame с колонками open, high, low, close

        Returns:
            pd.DataFrame: DataFrame с добавленными сигналами
        """
        df = df.copy()

        # Проверяем наличие необходимых колонок
        required_cols = ['high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Отсутствуют необходимые колонки: {required_cols}")

        # Если open отсутствует, создаем из close
        if 'open' not in df.columns:
            df['open'] = df['close']

        # --- РАСЧЕТ ИНДИКАТОРОВ ---
        # ATR
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ATR'] = df['ATR'].fillna(df['close'].rolling(14).std())

        # ADX
        adx_data = ta.adx(df['high'], df['low'], df['close'], length=14)
        if adx_data is not None and 'ADX_14' in adx_data.columns:
            df['ADX'] = adx_data['ADX_14']
        else:
            # Резервный расчет ADX
            df['ADX'] = 30.0
        df['ADX'] = df['ADX'].fillna(30.0)

        # Скользящие средние
        ma_period = getattr(self.config, 'ma_period', 20)
        ema_period = getattr(self.config, 'ema_period', 10)

        df['MA'] = df['close'].rolling(window=ma_period).mean()
        df['EMA'] = df['close'].ewm(span=ema_period, adjust=False).mean()

        # Заполняем первые NaN значения
        df['MA'] = df['MA'].fillna(df['close'])
        df['EMA'] = df['EMA'].fillna(df['close'])

        # --- РАСЧЕТ УГЛОВ (ИСПРАВЛЕНО) ---
        df['MA_Angle'] = self.calculate_angle(df['MA'], df['ATR'])
        df['EMA_Angle'] = self.calculate_angle(df['EMA'], df['ATR'])

        # --- РАСЧЕТ РАСХОЖДЕНИЯ ---
        df['Divergence'] = self.calculate_divergence(ma=df['MA'], ema=df['EMA'])

        # Сглаживание углов для исключения резкого шума
        smooth_angle = getattr(self.config, 'smooth_angle', True)
        if smooth_angle:
            df['MA_Angle'] = df['MA_Angle'].rolling(window=3).mean().fillna(0)
            df['EMA_Angle'] = df['EMA_Angle'].rolling(window=3).mean().fillna(0)

        # --- ГЕНЕРАЦИЯ СИГНАЛОВ ---
        signals = []
        signal_strengths = []
        trend_states = []
        raw_directions = []
        trend_confidences = []

        for i in range(len(df)):
            current_ma = df['MA'].iloc[i]
            current_ema = df['EMA'].iloc[i]
            current_adx = df['ADX'].iloc[i]

            if pd.isna(current_ma) or pd.isna(current_ema) or pd.isna(current_adx):
                signals.append('Нет данных')
                signal_strengths.append(0)
                trend_states.append('NO_TREND')
                raw_directions.append('neutral')
                trend_confidences.append(0.3)
                continue

            current_close = df['close'].iloc[i]
            current_open = df['open'].iloc[i]
            is_bullish = current_close > current_open
            is_bearish = current_close < current_open

            # Изменение цены для определения силы тренда
            price_change = 0
            if i > 0:
                price_change = current_close - df['close'].iloc[i - 1]

            # Расчет силы тренда с учетом ADX и дивергенции
            trend_info = self.determine_trend_strength(
                ma_angle=df['MA_Angle'].iloc[i],
                ema_angle=df['EMA_Angle'].iloc[i],
                divergence=df['Divergence'].iloc[i],
                current_adx=current_adx,
                price_change=price_change
            )

            raw_direction = trend_info['direction']
            raw_directions.append(raw_direction)

            # Генерация отфильтрованного сигнала
            signal = self._get_enhanced_signal(
                current_close, current_open, current_ma, current_ema,
                is_bullish, is_bearish, trend_info
            )

            # Расчет математической силы сигнала
            signal_strength = self._calculate_signal_strength(
                trend_info, is_bullish, is_bearish, current_adx
            )

            signals.append(signal)
            signal_strengths.append(signal_strength)
            trend_confidences.append(trend_info.get('confidence', 0.3))

            # Короткое значение Trend_State
            trend_states.append(
                self._TREND_STATE_MAP.get(
                    (trend_info['direction'], trend_info['strength']),
                    'NO_TREND'
                )
            )

        # --- ЗАПИСЬ РЕЗУЛЬТАТОВ ---
        df['Signal'] = signals
        df['Signal_Strength'] = signal_strengths
        df['Trend_State'] = trend_states
        df['MA_Angle_Final'] = df['MA_Angle']
        df['Raw_Direction'] = raw_directions
        df['Trend_Confidence'] = trend_confidences

        # Округление числовых колонок
        numeric_cols = ['ATR', 'ADX', 'MA', 'EMA', 'MA_Angle', 'EMA_Angle',
                        'Divergence', 'Signal_Strength']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].round(2)

        if 'Trend_Confidence' in df.columns:
            df['Trend_Confidence'] = df['Trend_Confidence'].round(2)

        return df

    def _get_enhanced_signal(
            self,
            c: float,
            o: float,
            ma: float,
            ema: float,
            is_bullish: bool,
            is_bearish: bool,
            trend_info: Dict
    ) -> str:
        """
        Безопасный генератор торговых команд.

        🔥 ИСПРАВЛЕНО:
        - Смягчены условия для сигналов
        - Добавлена дивергенция для раннего входа
        - Учтена сила тренда

        Args:
            c: цена закрытия
            o: цена открытия
            ma: скользящая средняя
            ema: экспоненциальная скользящая средняя
            is_bullish: бычья свеча
            is_bearish: медвежья свеча
            trend_info: информация о тренде

        Returns:
            str: торговый сигнал
        """
        # Если тренд нейтральный, проверяем дивергенцию
        if trend_info['direction'] == 'neutral':
            # 🔥 ФИКС: Дивергенция дает ранний сигнал
            if trend_info.get('divergence_detected', False):
                div_strength = trend_info.get('divergence_strength', 0)
                if div_strength > self.divergence_threshold:
                    # Бычья дивергенция
                    if is_bullish:
                        return 'BULLISH (DIVERGENCE)'
                    else:
                        return 'NEUTRAL'
                elif div_strength < -self.divergence_threshold:
                    # Медвежья дивергенция
                    if is_bearish:
                        return 'BEARISH (DIVERGENCE)'
                    else:
                        return 'NEUTRAL'
            return 'SIDEWAYS'

        # 🔥 ФИКС: Смягченные условия
        # Достаточно, чтобы цена была выше/ниже MA
        price_above_ma = c > ma
        price_below_ma = c < ma

        # Проверка EMA для подтверждения
        ma_above_ema = ma > ema
        ma_below_ema = ma < ema

        # --- ВОСХОДЯЩИЙ ТРЕНД ---
        if trend_info['direction'] == 'up':
            # Основной сигнал
            if price_above_ma and ma_above_ema:
                if is_bullish and trend_info['strength'] in ['strong', 'moderate']:
                    return 'STRONG BULLISH'
                elif trend_info['strength'] in ['weak', 'moderate']:
                    return 'BULLISH'
                return 'NEUTRAL'

            # 🔥 ФИКС: Сигнал даже если цена чуть ниже MA, но есть дивергенция
            elif trend_info.get('divergence_detected', False) and trend_info.get('divergence_strength', 0) > 0:
                if is_bullish:
                    return 'BULLISH (DIVERGENCE)'
                return 'NEUTRAL'

            # 🔥 ФИКС: Слабый сигнал, если цена выше EMA
            elif c > ema and is_bullish:
                return 'BULLISH (WEAK)'

            return 'NEUTRAL'

        # --- НИСХОДЯЩИЙ ТРЕНД ---
        if trend_info['direction'] == 'down':
            # Основной сигнал
            if price_below_ma and ma_below_ema:
                if is_bearish and trend_info['strength'] in ['strong', 'moderate']:
                    return 'STRONG BEARISH'
                elif trend_info['strength'] in ['weak', 'moderate']:
                    return 'BEARISH'
                return 'NEUTRAL'

            # 🔥 ФИКС: Сигнал даже если цена чуть выше MA, но есть дивергенция
            elif trend_info.get('divergence_detected', False) and trend_info.get('divergence_strength', 0) < 0:
                if is_bearish:
                    return 'BEARISH (DIVERGENCE)'
                return 'NEUTRAL'

            # 🔥 ФИКС: Слабый сигнал, если цена ниже EMA
            elif c < ema and is_bearish:
                return 'BEARISH (WEAK)'

            return 'NEUTRAL'

        return 'NEUTRAL'

    def _calculate_signal_strength(
            self,
            trend_info: Dict,
            is_bullish: bool,
            is_bearish: bool,
            current_adx: float
    ) -> float:
        """
        Расчет взвешенной математической силы сигнала.

        🔥 ИСПРАВЛЕНО:
        - Привязано к ADX
        - Дивергенция усиливает сигнал
        - Учтена сила тренда

        Args:
            trend_info: информация о тренде
            is_bullish: бычья свеча
            is_bearish: медвежья свеча
            current_adx: текущее значение ADX

        Returns:
            float: сила сигнала от -100 до 100
        """
        if trend_info['direction'] == 'neutral':
            # Дивергенция дает слабый сигнал даже в нейтрали
            if trend_info.get('divergence_detected', False):
                div_strength = trend_info.get('divergence_strength', 0)
                if abs(div_strength) > self.divergence_threshold:
                    return div_strength * 20  # Слабый сигнал
            return 0.0

        # 🔥 ФИКС: Базовая сила зависит от ADX
        # ADX 25-50: слабый тренд, 50-75: средний, 75+: сильный
        adx_strength = min(current_adx / 50.0, 1.2)  # 0.5-1.2

        # Направление
        direction_multiplier = 1.0 if trend_info['direction'] == 'up' else -1.0

        # Базовая сила от ADX (0-60)
        base_strength = 50.0 * adx_strength

        # Корректировка на силу тренда
        if trend_info['strength'] == 'strong':
            base_strength *= 1.5
        elif trend_info['strength'] == 'moderate':
            base_strength *= 1.2
        elif trend_info['strength'] == 'weak':
            base_strength *= 0.8

        # Ограничиваем
        base_strength = min(base_strength, 80.0)

        # 🔥 ФИКС: Дивергенция усиливает сигнал
        if trend_info.get('divergence_detected', False):
            div_strength = trend_info.get('divergence_strength', 0)
            if abs(div_strength) > self.divergence_threshold:
                divergence_boost = abs(div_strength) * 15
                divergence_boost = min(divergence_boost, 25.0)  # Максимум +25

                # Проверяем согласованность
                if (trend_info['direction'] == 'up' and div_strength > 0) or \
                        (trend_info['direction'] == 'down' and div_strength < 0):
                    # Дивергенция согласована с трендом - усиление
                    base_strength += divergence_boost
                else:
                    # Дивергенция против тренда - ослабление (предупреждение)
                    base_strength -= divergence_boost * 0.5

        # Штраф за свечу против тренда
        if trend_info['direction'] == 'up' and is_bearish:
            base_strength *= 0.6
        elif trend_info['direction'] == 'down' and is_bullish:
            base_strength *= 0.6

        # Применяем направление
        final_strength = base_strength * direction_multiplier

        # Ограничиваем диапазон [-100, 100]
        return max(min(final_strength, 100.0), -100.0)
