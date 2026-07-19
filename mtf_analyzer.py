"""Мультитаймфреймовый анализатор со строгой фильтрацией по старшему тренду."""
from __future__ import annotations

import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from config import TF_WEIGHTS, AnalysisConfig, Config
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator

warnings.filterwarnings("ignore")


class MultiTimeframeAnalyzer:
    """
    Анализ нескольких таймфреймов.
    Веса ТФ, пороги, лимиты свечей, биржа/символ — только из config.
    """

    def __init__(
        self,
        timeframes: Optional[List[str]] = None,
        exchange_name: Optional[str] = None,
        symbol: Optional[str] = None,
        analysis_config: Optional[AnalysisConfig] = None,
    ) -> None:
        self.analysis_config = analysis_config or AnalysisConfig()
        self.timeframes: List[str] = list(
            timeframes or getattr(self.analysis_config, "timeframes", list(TF_WEIGHTS.keys()))
        )
        self.exchange_name = exchange_name or getattr(
            self.analysis_config, "exchange_name", getattr(Config, "EXCHANGE_NAME", "binance")
        )
        self.symbol = symbol or getattr(
            self.analysis_config, "symbol", getattr(Config, "SYMBOL", "BTC/USDT")
        )
        self.tf_weights: Dict[str, float] = dict(TF_WEIGHTS)
        self.loader = ExchangeDataLoader(
            exchange_name=self.exchange_name,
            symbol=self.symbol,
        )
        self._data: Dict[str, pd.DataFrame] = {}
        self._tf_results: Dict[str, Dict[str, Any]] = {}

    def _candles_limit(self, tf: str) -> int:
        cfg = Config.for_timeframe(tf) if hasattr(Config, "for_timeframe") else None
        if cfg is not None and hasattr(cfg, "candles_limit"):
            return int(cfg.candles_limit)
        return int(getattr(self.analysis_config, "candles_limit", 500))

    def _tf_config(self, tf: str) -> Config:
        if hasattr(Config, "for_timeframe"):
            return Config.for_timeframe(tf)
        return Config()

    def load_data(self) -> Dict[str, pd.DataFrame]:
        """Загрузка OHLCV по всем таймфреймам."""
        self._data = {}
        if hasattr(self.loader, "load_multiple_timeframes"):
            raw = self.loader.load_multiple_timeframes(
                self.timeframes,
                limit=getattr(self.analysis_config, "candles_limit", None),
            )
            if isinstance(raw, dict):
                self._data = raw
                return self._data

        for tf in self.timeframes:
            limit = self._candles_limit(tf)
            if hasattr(self.loader, "fetch_ohlcv"):
                df = self.loader.fetch_ohlcv(timeframe=tf, limit=limit)
            else:
                df = self.loader.get_ohlcv(timeframe=tf, limit=limit)
            if df is not None and len(df) > 0:
                self._data[tf] = df
        return self._data

    def _signal_from_df(self, df: pd.DataFrame, tf: str) -> Dict[str, Any]:
        """Прогон AdvancedTrendSignalIndicator и разбор последнего бара."""
        cfg = self._tf_config(tf)
        ind = AdvancedTrendSignalIndicator(config=cfg)
        out = ind.generate_signal(df.copy())

        if out is None or len(out) == 0:
            return {
                "timeframe": tf,
                "signal": 0,
                "direction": "neutral",
                "strength": 0.0,
                "close": float("nan"),
                "error": "empty_indicator_output",
            }

        last = out.iloc[-1]
        # гибкий разбор колонок сигнала
        signal_val = 0
        for col in ("signal", "Signal", "trade_signal", "final_signal"):
            if col in out.columns and pd.notna(last.get(col)):
                try:
                    signal_val = int(last[col])
                except (TypeError, ValueError):
                    signal_val = 0
                break

        if signal_val > 0:
            direction = "long"
        elif signal_val < 0:
            direction = "short"
        else:
            direction = "neutral"

        strength = 0.0
        for col in ("strength", "signal_strength", "confidence", "score"):
            if col in out.columns and pd.notna(last.get(col)):
                try:
                    strength = float(last[col])
                except (TypeError, ValueError):
                    strength = 0.0
                break

        close = float(last["close"]) if "close" in out.columns else float("nan")

        extras: Dict[str, Any] = {}
        for col in ("rsi", "RSI", "adx", "ADX", "ma_trend", "ema_trend", "atr", "ATR"):
            if col in out.columns and pd.notna(last.get(col)):
                extras[col] = last[col]

        return {
            "timeframe": tf,
            "signal": signal_val,
            "direction": direction,
            "strength": strength,
            "close": close,
            "weight": float(self.tf_weights.get(tf, 1.0)),
            **extras,
        }

    def analyze_timeframe(self, tf: str) -> Dict[str, Any]:
        if tf not in self._data:
            self.load_data()
        df = self._data.get(tf)
        if df is None or len(df) == 0:
            return {
                "timeframe": tf,
                "signal": 0,
                "direction": "neutral",
                "strength": 0.0,
                "error": "no_data",
            }
        return self._signal_from_df(df, tf)

    def analyze_all(self) -> Dict[str, Dict[str, Any]]:
        if not self._data:
            self.load_data()
        self._tf_results = {}
        for tf in self.timeframes:
            self._tf_results[tf] = self.analyze_timeframe(tf)
        return self._tf_results

    def _sorted_by_weight(self) -> List[str]:
        return sorted(
            self.timeframes,
            key=lambda t: float(self.tf_weights.get(t, 0.0)),
            reverse=True,
        )

    def _higher_tf_bias(self) -> str:
        """
        Направление старшего ТФ (макс. вес).
        long / short / neutral
        """
        ordered = self._sorted_by_weight()
        if not ordered:
            return "neutral"
        top = ordered[0]
        res = self._tf_results.get(top) or self.analyze_timeframe(top)
        return res.get("direction", "neutral")

    def _min_confidence(self) -> float:
        return float(
            getattr(
                self.analysis_config,
                "min_confidence",
                getattr(self.analysis_config, "confidence_threshold", 0.0),
            )
        )

    def _min_strength(self) -> float:
        return float(
            getattr(
                self.analysis_config,
                "min_signal_strength",
                getattr(self.analysis_config, "min_strength", 0.0),
            )
        )

    def aggregate(self) -> Dict[str, Any]:
        """
        Взвешенный итог + фильтр по старшему тренду.
        Сигналы против старшего ТФ обнуляются / режутся.
        """
        if not self._tf_results:
            self.analyze_all()

        higher = self._higher_tf_bias()
        weighted = 0.0
        total_w = 0.0
        details: List[Dict[str, Any]] = []

        for tf in self.timeframes:
            r = self._tf_results.get(tf, {})
            w = float(self.tf_weights.get(tf, 1.0))
            sig = int(r.get("signal", 0) or 0)
            direction = r.get("direction", "neutral")
            strength = float(r.get("strength", 0.0) or 0.0)

            aligned = True
            if higher == "long" and sig < 0:
                aligned = False
                sig = 0
            elif higher == "short" and sig > 0:
                aligned = False
                sig = 0

            # вклад: знак сигнала * сила * вес
            contrib = float(sig) * max(strength, 1.0) * w if sig != 0 else 0.0
            if sig == 0 and direction in ("long", "short") and aligned:
                contrib = (1.0 if direction == "long" else -1.0) * max(strength, 0.0) * w

            weighted += contrib
            total_w += w
            details.append(
                {
                    **r,
                    "aligned_with_higher": aligned,
                    "contribution": contrib,
                }
            )

        score = weighted / total_w if total_w else 0.0
        min_c = self._min_confidence()
        min_s = self._min_strength()

        if score > min_s:
            final_dir = "long"
            final_sig = 1
        elif score < -min_s:
            final_dir = "short"
            final_sig = -1
        else:
            final_dir = "neutral"
            final_sig = 0

        # строгий фильтр: итог не против старшего ТФ
        if higher == "long" and final_sig < 0:
            final_sig, final_dir = 0, "neutral"
            score = 0.0
        elif higher == "short" and final_sig > 0:
            final_sig, final_dir = 0, "neutral"
            score = 0.0
        elif higher == "neutral":
            # при нейтральном старшем — только если |score| достаточно велик
            if abs(score) < max(min_c, min_s):
                final_sig, final_dir = 0, "neutral"

        confidence = min(abs(score), 1.0) if final_sig != 0 else 0.0
        if confidence < min_c and final_sig != 0:
            final_sig, final_dir, confidence = 0, "neutral", 0.0

        return {
            "symbol": self.symbol,
            "exchange": self.exchange_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "higher_tf_bias": higher,
            "final_signal": final_sig,
            "final_direction": final_dir,
            "score": score,
            "confidence": confidence,
            "timeframes": details,
        }

    def run(self) -> Dict[str, Any]:
        """Полный цикл: загрузка → анализ ТФ → агре gated."""
        self.load_data()
        self.analyze_all()
        return self.aggregate()


def create_mtf_analyzer(
    timeframes: Optional[List[str]] = None,
    exchange_name: Optional[str] = None,
    symbol: Optional[str] = None,
    analysis_config: Optional[AnalysisConfig] = None,
) -> MultiTimeframeAnalyzer:
    """Фабрика без передачи несуществующего cfg= в конструктор."""
    return MultiTimeframeAnalyzer(
        timeframes=timeframes,
        exchange_name=exchange_name,
        symbol=symbol,
        analysis_config=analysis_config,
    )


def run_mtf_analysis(
    timeframes: Optional[List[str]] = None,
    exchange_name: Optional[str] = None,
    symbol: Optional[str] = None,
    analysis_config: Optional[AnalysisConfig] = None,
) -> Dict[str, Any]:
    analyzer = create_mtf_analyzer(
        timeframes=timeframes,
        exchange_name=exchange_name,
        symbol=symbol,
        analysis_config=analysis_config,
    )
    return analyzer.run()


def print_mtf_result(result: Dict[str, Any]) -> None:
    """Аккуратный вывод результата в консоль."""
    print("=" * 60)
    print(f"Symbol:   {result.get('symbol')}")
    print(f"Exchange: {result.get('exchange')}")
    print(f"Time:     {result.get('timestamp')}")
    print(f"Higher:   {result.get('higher_tf_bias')}")
    print(
        f"Final:    {result.get('final_direction')} "
        f"(signal={result.get('final_signal')}, "
        f"score={result.get('score'):.4f}, "
        f"conf={result.get('confidence'):.4f})"
    )
    print("-" * 60)
    for row in result.get("timeframes") or []:
        tf = row.get("timeframe")
        print(
            f"  [{tf}] dir={row.get('direction')} "
            f"sig={row.get('signal')} "
            f"str={row.get('strength')} "
            f"w={row.get('weight')} "
            f"aligned={row.get('aligned_with_higher')} "
            f"close={row.get('close')}"
        )
        ma = row.get("ma_trend") or row.get("ema_trend")
        adx = row.get("adx") or row.get("ADX")
        rsi = row.get("rsi") or row.get("RSI")
        if ma is not None or adx is not None or rsi is not None:
            print(f"         ma={ma} adx={adx} rsi={rsi}")
    print("=" * 60)


if __name__ == "__main__":
    res = run_mtf_analysis()
    print_mtf_result(res)
