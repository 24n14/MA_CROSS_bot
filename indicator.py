"""
Оптимизированный модуль технического индикатора с защитой от флэта
и ATR-нормализацией.

Класс:
  - AdvancedTrendSignalIndicator
"""
from __future__ import annotations

import warnings
from typing import Dict, Optional

import numpy as np
import pandas as pd
import pandas_ta as ta

from config import Config

warnings.filterwarnings("ignore")


class AdvancedTrendSignalIndicator:
    """
    Тренд по N-свечам, ATR-нормализация углов, ADX-фильтр флэта.
    Пороги — из Config (adx_flat_threshold, angle_threshold_*, ma/ema period и т.д.).
    """

    _TREND_STATE_MAP = {
        ("up", "weak"): "UP",
        ("up", "moderate"): "UP",
        ("up", "strong"): "UP",
        ("down", "weak"): "DOWN",
        ("down", "moderate"): "DOWN",
        ("down", "strong"): "DOWN",
        ("neutral", "none"): "NO_TREND",
    }

    def __init__(self, config: Optional[Config] = None):
        self.config = config if config is not None else Config()
        self.lookback = getattr(self.config, "angle_lookback", 5)
        self.divergence_threshold = getattr(self.config, "divergence_threshold", 0.2)
        self.angle_scale = getattr(self.config, "angle_scale", 50.0)

    def calculate_angle(self, series: pd.Series, atr: pd.Series) -> pd.Series:
        """Угол наклона MA/EMA с ATR-нормализацией."""
        angles = pd.Series(index=series.index, dtype=float)
        lookback = int(self.lookback)

        for i in range(len(series)):
            if pd.isna(series.iloc[i]) or pd.isna(atr.iloc[i]):
                angles.iloc[i] = 0.0
                continue

            current_lookback = min(i, lookback)
            if current_lookback < 2:
                angles.iloc[i] = 0.0
                continue

            price_change = float(series.iloc[i] - series.iloc[i - current_lookback])
            atr_period = float(atr.iloc[i]) * current_lookback

            if atr_period > 0:
                normalized = (price_change / atr_period) * float(self.angle_scale)
                normalized = float(np.clip(normalized, -10.0, 10.0))
                angles.iloc[i] = float(np.degrees(np.arctan(normalized)))
            else:
                angles.iloc[i] = 0.0

        return angles

    def calculate_divergence(self, ma: pd.Series, ema: pd.Series) -> pd.Series:
        """
        Расхождение MA vs EMA в % — СО ЗНАКОМ.
        > 0: MA выше EMA (бычий контекст)
        < 0: MA ниже EMA (медвежий)
        Раньше .abs() убивал медвежьи ветки.
        """
        with np.errstate(divide="ignore", invalid="ignore"):
            div = (ma - ema) / ema.replace(0, np.nan) * 100.0
        return div.fillna(0.0)

    def determine_trend_strength(
        self,
        ma_angle: float,
        ema_angle: float,
        divergence: float,
        current_adx: float,
        price_change: float = 0.0,
    ) -> Dict:
        trend_info = {
            "direction": "neutral",
            "strength": "none",
            "confidence": 0.3,
            "divergence_detected": False,
            "divergence_strength": 0.0,
            "adx": current_adx,
        }

        adx_threshold = float(getattr(self.config, "adx_flat_threshold", 25.0))
        weak_threshold = float(getattr(self.config, "angle_threshold_weak", 3.0))
        moderate_threshold = float(
            getattr(self.config, "angle_threshold_moderate", 8.0)
        )
        strong_threshold = float(
            getattr(self.config, "angle_threshold_strong", 15.0)
        )
        div_th = float(self.divergence_threshold)

        # --- флэт по ADX ---
        if current_adx < adx_threshold:
            if abs(divergence) > div_th:
                trend_info["divergence_detected"] = True
                trend_info["divergence_strength"] = float(divergence)
                if divergence > div_th:
                    trend_info["direction"] = "up"
                    trend_info["strength"] = "weak"
                    trend_info["confidence"] = 0.5
                elif divergence < -div_th:
                    trend_info["direction"] = "down"
                    trend_info["strength"] = "weak"
                    trend_info["confidence"] = 0.5
            return trend_info

        abs_ma = abs(ma_angle)
        abs_ema = abs(ema_angle)
        max_abs_angle = max(abs_ma, abs_ema)

        if max_abs_angle < weak_threshold:
            if abs(divergence) > div_th:
                trend_info["divergence_detected"] = True
                trend_info["divergence_strength"] = float(divergence)
                if divergence > div_th:
                    trend_info["direction"] = "up"
                    trend_info["strength"] = "weak"
                    trend_info["confidence"] = 0.4
                elif divergence < -div_th:
                    trend_info["direction"] = "down"
                    trend_info["strength"] = "weak"
                    trend_info["confidence"] = 0.4
            return trend_info

        dominant_angle = ma_angle if abs_ma >= abs_ema else ema_angle
        if dominant_angle > weak_threshold:
            trend_info["direction"] = "up"
        elif dominant_angle < -weak_threshold:
            trend_info["direction"] = "down"
        else:
            return trend_info

        avg_angle_abs = (abs_ma + abs_ema) / 2.0
        if avg_angle_abs >= strong_threshold:
            trend_info["strength"] = "strong"
            trend_info["confidence"] = 0.9
        elif avg_angle_abs >= moderate_threshold:
            trend_info["strength"] = "moderate"
            trend_info["confidence"] = 0.7
        else:
            trend_info["strength"] = "weak"
            trend_info["confidence"] = 0.5

        if current_adx >= 50:
            trend_info["strength"] = "strong"
            trend_info["confidence"] = min(trend_info["confidence"] + 0.1, 1.0)
        elif current_adx >= 35 and trend_info["strength"] == "weak":
            trend_info["strength"] = "moderate"
            trend_info["confidence"] = min(trend_info["confidence"] + 0.1, 1.0)

        if abs(divergence) > div_th:
            trend_info["divergence_detected"] = True
            trend_info["divergence_strength"] = float(divergence)

            if trend_info["direction"] == "up" and divergence > 0:
                if trend_info["strength"] == "weak":
                    trend_info["strength"] = "moderate"
                elif trend_info["strength"] == "moderate":
                    trend_info["strength"] = "strong"
                trend_info["confidence"] = min(trend_info["confidence"] + 0.1, 1.0)
            elif trend_info["direction"] == "down" and divergence < 0:
                if trend_info["strength"] == "weak":
                    trend_info["strength"] = "moderate"
                elif trend_info["strength"] == "moderate":
                    trend_info["strength"] = "strong"
                trend_info["confidence"] = min(trend_info["confidence"] + 0.1, 1.0)

            # дивергенция против тренда — снижение уверенности
            if trend_info["direction"] == "up" and divergence < -div_th:
                trend_info["confidence"] = max(trend_info["confidence"] - 0.2, 0.1)
            elif trend_info["direction"] == "down" and divergence > div_th:
                trend_info["confidence"] = max(trend_info["confidence"] - 0.2, 0.1)

        return trend_info

    def generate_signal(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        required = ["high", "low", "close"]
        if not all(c in df.columns for c in required):
            raise ValueError(f"Нужны колонки: {required}")

        if "open" not in df.columns:
            df["open"] = df["close"]

        df["ATR"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["ATR"] = df["ATR"].fillna(df["close"].rolling(14).std())

        adx_data = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx_data is not None and "ADX_14" in adx_data.columns:
            df["ADX"] = adx_data["ADX_14"]
        else:
            df["ADX"] = 30.0
        df["ADX"] = df["ADX"].fillna(30.0)

        ma_period = int(getattr(self.config, "ma_period", 20))
        ema_period = int(getattr(self.config, "ema_period", 10))
        df["MA"] = df["close"].rolling(window=ma_period).mean()
        df["EMA"] = df["close"].ewm(span=ema_period, adjust=False).mean()
        df["MA"] = df["MA"].fillna(df["close"])
        df["EMA"] = df["EMA"].fillna(df["close"])

        df["MA_Angle"] = self.calculate_angle(df["MA"], df["ATR"])
        df["EMA_Angle"] = self.calculate_angle(df["EMA"], df["ATR"])
        df["Divergence"] = self.calculate_divergence(df["MA"], df["EMA"])

        if getattr(self.config, "smooth_angle", True):
            df["MA_Angle"] = df["MA_Angle"].rolling(3).mean().fillna(0.0)
            df["EMA_Angle"] = df["EMA_Angle"].rolling(3).mean().fillna(0.0)

        signals = []
        signal_strengths = []
        trend_states = []
        raw_directions = []
        trend_confidences = []

        for i in range(len(df)):
            current_ma = df["MA"].iloc[i]
            current_ema = df["EMA"].iloc[i]
            current_adx = df["ADX"].iloc[i]

            if pd.isna(current_ma) or pd.isna(current_ema) or pd.isna(current_adx):
                signals.append("Нет данных")
                signal_strengths.append(0.0)
                trend_states.append("NO_TREND")
                raw_directions.append("neutral")
                trend_confidences.append(0.3)
                continue

            current_close = float(df["close"].iloc[i])
            current_open = float(df["open"].iloc[i])
            is_bullish = current_close > current_open
            is_bearish = current_close < current_open
            price_change = (
                current_close - float(df["close"].iloc[i - 1]) if i > 0 else 0.0
            )

            trend_info = self.determine_trend_strength(
                ma_angle=float(df["MA_Angle"].iloc[i]),
                ema_angle=float(df["EMA_Angle"].iloc[i]),
                divergence=float(df["Divergence"].iloc[i]),
                current_adx=float(current_adx),
                price_change=price_change,
            )
            raw_directions.append(trend_info["direction"])

            signal = self._get_enhanced_signal(
                current_close,
                current_open,
                float(current_ma),
                float(current_ema),
                is_bullish,
                is_bearish,
                trend_info,
            )
            strength = self._calculate_signal_strength(
                trend_info, is_bullish, is_bearish, float(current_adx)
            )

            signals.append(signal)
            signal_strengths.append(strength)
            trend_confidences.append(float(trend_info.get("confidence", 0.3)))
            trend_states.append(
                self._TREND_STATE_MAP.get(
                    (trend_info["direction"], trend_info["strength"]),
                    "NO_TREND",
                )
            )

        df["Signal"] = signals
        df["Signal_Strength"] = signal_strengths
        df["Trend_State"] = trend_states
        df["MA_Angle_Final"] = df["MA_Angle"]
        df["Raw_Direction"] = raw_directions
        df["Trend_Confidence"] = trend_confidences

        for col in (
            "ATR",
            "ADX",
            "MA",
            "EMA",
            "MA_Angle",
            "EMA_Angle",
            "Divergence",
            "Signal_Strength",
            "Trend_Confidence",
        ):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

        return df

    def _get_enhanced_signal(
        self,
        c: float,
        o: float,
        ma: float,
        ema: float,
        is_bullish: bool,
        is_bearish: bool,
        trend_info: Dict,
    ) -> str:
        div_th = float(self.divergence_threshold)

        if trend_info["direction"] == "neutral":
            if trend_info.get("divergence_detected", False):
                div_s = float(trend_info.get("divergence_strength", 0.0))
                if div_s > div_th:
                    return "BULLISH (DIVERGENCE)" if is_bullish else "NEUTRAL"
                if div_s < -div_th:
                    return "BEARISH (DIVERGENCE)" if is_bearish else "NEUTRAL"
            return "SIDEWAYS"

        price_above_ma = c > ma
        price_below_ma = c < ma
        ma_above_ema = ma > ema
        ma_below_ema = ma < ema

        if trend_info["direction"] == "up":
            if price_above_ma and ma_above_ema:
                if is_bullish and trend_info["strength"] in ("strong", "moderate"):
                    return "STRONG BULLISH"
                if trend_info["strength"] in ("weak", "moderate", "strong"):
                    return "BULLISH"
                return "NEUTRAL"
            if (
                trend_info.get("divergence_detected", False)
                and float(trend_info.get("divergence_strength", 0.0)) > 0
            ):
                return "BULLISH (DIVERGENCE)" if is_bullish else "NEUTRAL"
            if c > ema and is_bullish:
                return "BULLISH (WEAK)"
            return "NEUTRAL"

        if trend_info["direction"] == "down":
            if price_below_ma and ma_below_ema:
                if is_bearish and trend_info["strength"] in ("strong", "moderate"):
                    return "STRONG BEARISH"
                if trend_info["strength"] in ("weak", "moderate", "strong"):
                    return "BEARISH"
                return "NEUTRAL"
            if (
                trend_info.get("divergence_detected", False)
                and float(trend_info.get("divergence_strength", 0.0)) < 0
            ):
                return "BEARISH (DIVERGENCE)" if is_bearish else "NEUTRAL"
            if c < ema and is_bearish:
                return "BEARISH (WEAK)"
            return "NEUTRAL"

        return "NEUTRAL"

    def _calculate_signal_strength(
        self,
        trend_info: Dict,
        is_bullish: bool,
        is_bearish: bool,
        current_adx: float,
    ) -> float:
        div_th = float(self.divergence_threshold)

        if trend_info["direction"] == "neutral":
            if trend_info.get("divergence_detected", False):
                div_s = float(trend_info.get("divergence_strength", 0.0))
                if abs(div_s) > div_th:
                    return float(np.clip(div_s * 20.0, -100.0, 100.0))
            return 0.0

        adx_strength = min(float(current_adx) / 50.0, 1.2)
        direction_multiplier = 1.0 if trend_info["direction"] == "up" else -1.0
        base = 50.0 * adx_strength

        if trend_info["strength"] == "strong":
            base *= 1.5
        elif trend_info["strength"] == "moderate":
            base *= 1.2
        elif trend_info["strength"] == "weak":
            base *= 0.8

        base = min(base, 80.0)

        if trend_info.get("divergence_detected", False):
            div_s = float(trend_info.get("divergence_strength", 0.0))
            if abs(div_s) > div_th:
                boost = min(abs(div_s) * 15.0, 25.0)
                aligned = (
                    trend_info["direction"] == "up" and div_s > 0
                ) or (
                    trend_info["direction"] == "down" and div_s < 0
                )
                base = base + boost if aligned else base - boost * 0.5

        if trend_info["direction"] == "up" and is_bearish:
            base *= 0.6
        elif trend_info["direction"] == "down" and is_bullish:
            base *= 0.6

        return float(np.clip(base * direction_multiplier, -100.0, 100.0))
