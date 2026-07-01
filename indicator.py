"""
Оптимизированный модуль технического индикатора с защитой от флэта и ATR-нормализацией.
Содержит класс:
- AdvancedTrendSignalIndicator: основной индикатор тренда
"""
import pandas as pd
import numpy as np
import pandas_ta as ta  # Добавлено для точного расчета ATR и ADX
from scipy import stats
from typing import Dict
import warnings
from config import Config

warnings.filterwarnings('ignore')


class AdvancedTrendSignalIndicator:
    """
    Индикатор с анализом тренда по N-свечам, динамическим ATR-фильтром волатильности
    и защитой от ложных сигналов во флэте (через ADX).
    """

    def __init__(self, config: Config = Config()):
        """
        Инициализация индикатора.
        """
        self.config = config

    def calculate_angle(self, series: pd.Series, atr: pd.Series) -> pd.Series:
        """
        Расчет угла наклона скользящей средней, нормализованный по волатильности (ATR).
        Использует линейную регрессию за период trend_lookback.
        """
        angles = pd.Series(0.0, index=series.index, dtype=float)
        lookback = self.config.trend_lookback

        for i in range(lookback, len(series)):
            current_atr = atr.iloc[i]
            if pd.isna(current_atr) or current_atr <= 0:
                current_atr = series.iloc[i] * 0.001  # Резервная нормализация, если ATR пуст

            if self.config.use_linear_regression:
                y = series.iloc[i - lookback:i + 1].values
                x = np.arange(len(y))
                if len(y) > 1 and not np.isnan(y).any():
                    slope, _, _, _, _ = stats.linregress(x, y)
                    # Нормализуем наклон к ATR: сколько "нормальных" движений делает MA за шаг
                    angle = np.degrees(np.arctan(slope / current_atr))
                else:
                    angle = 0.0
            else:
                price_change = series.iloc[i] - series.iloc[i - lookback]
                angle = np.degrees(np.arctan(price_change / (current_atr * lookback)))

            angles.iloc[i] = angle
        return angles

    def calculate_divergence(self, ma: pd.Series, ema: pd.Series) -> pd.Series:
        """
        Расчет расхождения между MA и EMA в процентах.
        """
        return ((ma - ema) / ema * 100).abs()

    def determine_trend_strength(self, ma_angle: float, ema_angle: float, divergence: float,
                                 current_adx: float) -> Dict:
        """
        Определение направления и силы тренда с учетом ADX-фильтра флэта
        и фильтра расхождения MA/EMA (divergence_threshold).

        Исправления:
        - ADX порог снижен с 25 до 20 (ADX 20-25 — developing trend, не флэт)
        - Направление определяется по максимальному углу (MA или EMA), а не по обоим сразу
        """
        trend_info = {
            'direction': 'neutral',
            'strength': 'none',
            'confidence': 0.3
        }

        # --- ЗАЩИТА ОТ ФЛЭТА ---
        # ADX ниже 20 — рынок во флэте, блокируем сигналы
        if current_adx < 20.0:
            return trend_info

        # Определяем доминирующий угол (максимальный по модулю)
        abs_ma = abs(ma_angle)
        abs_ema = abs(ema_angle)
        max_abs_angle = max(abs_ma, abs_ema)

        # Если ни один угол не превышает слабый порог — тренда нет
        if max_abs_angle < self.config.angle_threshold_weak:
            return trend_info

        # Определяем направление по углу с большим абсолютным значением
        if abs_ma >= abs_ema:
            dominant_angle = ma_angle
        else:
            dominant_angle = ema_angle

        if dominant_angle > self.config.angle_threshold_weak:
            trend_info['direction'] = 'up'
        elif dominant_angle < -self.config.angle_threshold_weak:
            trend_info['direction'] = 'down'
        else:
            return trend_info  # Спорные сигналы сбрасываем в нейтраль

        # Определение силы тренда (на основе углов, ADX и расхождения)
        avg_angle_abs = (abs_ma + abs_ema) / 2

        # --- ФИЛЬТР ПО РАСХОЖДЕНИЮ MA/EMA ---
        # Если расхождение меньше порога — MA и EMA почти совпадают,
        # тренд не подтверждён, снижаем силу до weak
        if divergence < self.config.divergence_threshold:
            trend_info['strength'] = 'weak'
            trend_info['confidence'] = 0.4
            return trend_info

        if avg_angle_abs >= self.config.angle_threshold_strong and current_adx > 35.0:
            trend_info['strength'] = 'strong'
            trend_info['confidence'] = 0.9
        elif avg_angle_abs >= self.config.angle_threshold_weak and current_adx >= 20.0:
            trend_info['strength'] = 'moderate'
            trend_info['confidence'] = 0.7
        else:
            trend_info['strength'] = 'weak'
            trend_info['confidence'] = 0.5

        return trend_info


    def generate_signal(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Генерация сигналов с комплексной фильтрацией волатильности и флэта.
        """
        df = df.copy()

        # Инъекция математики волатильности и силы тренда
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        adx_data = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['ADX'] = adx_data['ADX_14'] if adx_data is not None else 30.0  # резерв

        # Расчет скользящих средних
        df['MA'] = df['close'].rolling(window=self.config.ma_period).mean()
        df['EMA'] = df['close'].ewm(span=self.config.ema_period, adjust=False).mean()

        # Расчет углов (теперь передаем ATR для динамической нормализации)
        df['MA_Angle'] = self.calculate_angle(df['MA'], df['ATR'])
        df['EMA_Angle'] = self.calculate_angle(df['EMA'], df['ATR'])

        # Расчет расхождения
        df['Divergence'] = self.calculate_divergence(ma=df['MA'], ema=df['EMA'])

        # Сглаживание углов для исключения резкого шума
        if self.config.smooth_angle:
            df['MA_Angle'] = df['MA_Angle'].rolling(window=3).mean()
            df['EMA_Angle'] = df['EMA_Angle'].rolling(window=3).mean()

        signals = []
        signal_strengths = []
        trend_states = []
        raw_directions = []  # НОВОЕ: реальное направление без фильтрации
        raw_strengths = []  # НОВОЕ: реальная сила без фильтрации

        for i in range(len(df)):
            current_ma = df['MA'].iloc[i]
            current_ema = df['EMA'].iloc[i]
            current_adx = df['ADX'].iloc[i]

            if pd.isna(current_ma) or pd.isna(current_ema) or pd.isna(current_adx):
                signals.append('Нет данных')
                signal_strengths.append(0)
                trend_states.append('neutral_none')
                raw_directions.append('neutral')  # НОВОЕ
                raw_strengths.append(0)  # НОВОЕ
                continue

            current_close = df['close'].iloc[i]
            current_open = df['open'].iloc[i]
            is_bullish = current_close > current_open
            is_bearish = current_close < current_open

            # Расчет силы тренда с учетом ADX
            trend_info = self.determine_trend_strength(
                ma_angle=df['MA_Angle'].iloc[i],
                ema_angle=df['EMA_Angle'].iloc[i],
                divergence=df['Divergence'].iloc[i],
                current_adx=current_adx
            )

            # === НОВОЕ: Сохраняем "сырые" значения ДО фильтрации ===
            raw_direction = trend_info['direction']  # 'up', 'down' или 'neutral'
            raw_strength = self._calculate_signal_strength(trend_info, is_bullish, is_bearish)

            raw_directions.append(raw_direction)
            raw_strengths.append(raw_strength)

            # Генерация отфильтрованного сигнала (как было)
            signal = self._get_enhanced_signal(
                current_close, current_open, current_ma, current_ema,
                is_bullish, is_bearish, trend_info
            )

            # Расчет математической силы сигнала
            signal_strength = self._calculate_signal_strength(trend_info, is_bullish, is_bearish)

            signals.append(signal)
            signal_strengths.append(signal_strength)
            trend_states.append(f"{trend_info['direction']}_{trend_info['strength']}")

        df['Signal'] = signals
        df['Signal_Strength'] = signal_strengths
        df['Trend_State'] = trend_states
        df['MA_Angle_Final'] = df['MA_Angle']

        # === НОВОЕ: Добавляем сырые колонки ===
        df['Raw_Direction'] = raw_directions
        df['Raw_Signal'] = raw_strengths

        df['Trend_Confidence'] = df['Trend_State'].apply(
            lambda x: 0.9 if 'strong' in str(x) else (0.7 if 'moderate' in str(x) else 0.3)
        )
        return df

    def _get_enhanced_signal(self, c: float, o: float, ma: float, ema: float,
                             is_bullish: bool, is_bearish: bool, trend_info: dict) -> str:
        """
        Безопасный генератор торговых команд. Полностью исключает торговлю против тренда и "пилу".
        """
        if trend_info['direction'] == 'neutral':
            return 'Sideways'  # Если ADX < 20 или тренд не сформирован — робот жестко сидит на заборе

        above_all = c > ma and o > ma
        below_all = c < ma and o < ma

        # Фильтрация для восходящего тренда
        if trend_info['direction'] == 'up':
            if above_all and is_bullish:
                if trend_info['strength'] in ['strong', 'moderate']:
                    return 'STRONG BULLISH'
                return 'Bullish'
            return 'Neutral'  # Вместо Counter-Trend Bearish — переводим робота в режим ожидания

        # Фильтрация для нисходящего тренда
        if trend_info['direction'] == 'down':
            if below_all and is_bearish:
                if trend_info['strength'] in ['strong', 'moderate']:
                    return 'STRONG BEARISH'
                return 'Bearish'
            return 'Neutral'  # Перевод в нейтраль, запрещаем ловить развороты импульса лонгами

        return 'Neutral'

    def _calculate_signal_strength(self, trend_info: dict, is_bullish: bool, is_bearish: bool) -> float:
        """
        Расчет взвешенной математической силы сигнала.
        """
        if trend_info['direction'] == 'neutral':
            return 0.0

        base = 50.0 if trend_info['direction'] == 'up' else -50.0

        if trend_info['strength'] == 'strong':
            base *= 1.5
        elif trend_info['strength'] == 'moderate':
            base *= 1.2

        # Штраф к силе, если свеча идет против направления глобального тренда
        if trend_info['direction'] == 'up' and is_bearish:
            base *= 0.5
        elif trend_info['direction'] == 'down' and is_bullish:
            base *= 0.5

        return max(min(base, 100.0), -100.0)