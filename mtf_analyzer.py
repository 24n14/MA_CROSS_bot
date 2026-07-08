"""
Оптимизированный модуль мультитаймфреймового анализа со взвешенным консенсусом.
"""
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from config import Config, AnalysisConfig, TF_WEIGHTS
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from log import logger


class MultiTimeframeAnalyzer:
    """
    Мультитаймфреймовый анализатор со строгой фильтрацией по старшему тренду.
    """

    def __init__(self, timeframes: List[str] = None, exchange_name: str = 'bybit', symbol: str = 'BTC/USDT:USDT'):
        # Исправляем возможные опечатки в конфигурации (например, '15' -> '15m')
        raw_tfs = timeframes or ['5m', '15m', '30m']
        self.timeframes = [tf if 'm' in tf.lower() or 'h' in tf.lower() or 'd' in tf.lower() else f"{tf}m" for tf in
                           raw_tfs]

        self.symbol = symbol
        self.loader = ExchangeDataLoader(exchange_name, symbol=symbol)
        self.TF_WEIGHTS = TF_WEIGHTS

        self.indicators = {
            tf: AdvancedTrendSignalIndicator(Config.for_timeframe(tf)) for tf in self.timeframes
        }
        self._cached_data: Dict[str, Optional[pd.DataFrame]] = {}

    def load_and_analyze(self, limit: int = 500) -> Dict:
        logger.info(f"\n{'=' * 30}\n🔍 MTF АНАЛИЗ (КОНСЕНСУС): {self.symbol}\n{'=' * 30}")

        data = self.loader.load_multiple_timeframes_incremental(
            self.symbol, timeframes=self.timeframes, cached_data=self._cached_data, limit=limit
        )
        if not data:
            logger.error("❌ Не удалось загрузить исторические свечи с биржи")
            return {}

        self._cached_data = data
        results = {}
        mtf_summary = []

        for tf in self.timeframes:
            if tf not in data or data[tf].empty:
                logger.warning(f"⚠️ Нет данных для обработки таймфрейма {tf}")
                continue

            indicator = self.indicators[tf]
            result = indicator.generate_signal(data[tf])
            results[tf] = result

            last = result.iloc[-1]
            weight = self.TF_WEIGHTS.get(tf, 0.3)

            mtf_summary.append({
                'timeframe': tf, 'signal': last['Signal'], 'strength': last['Signal_Strength'],
                'trend': last['Trend_State'], 'angle': last['MA_Angle_Final'],
                'divergence': last['Divergence'], 'close': last['close'], 'weight': weight,
                'atr': last.get('ATR', 0), 'adx': last.get('ADX', 0)
            })

        final_signal = self._calculate_final_signal(mtf_summary)
        return {
            'symbol': self.symbol, 'timeframes': self.timeframes, 'timestamp': datetime.now(),
            'mtf_details': mtf_summary, 'final_signal': final_signal, 'results': results
        }

    def _calculate_final_signal(self, summary: List[Dict]) -> Dict:
        ac = AnalysisConfig()
        if not summary:
            return {
                'direction': 'NEUTRAL', 'confidence': 'LOW', 'strength': 0,
                'trigger_trade': False, 'atr': 0, 'adx': 0, 'close': 0
            }

        total_weight = sum(item['weight'] for item in summary)
        bullish_score = 0.0
        bearish_score = 0.0
        flat_score = 0.0
        weighted_strength_sum = 0.0

        for item in summary:
            sig = str(item['signal']).upper()
            w = item['weight']
            weighted_strength_sum += item['strength'] * w

            if 'STRONG BULLISH' in sig or 'BULLISH' in sig:
                bullish_score += w
            elif 'STRONG BEARISH' in sig or 'BEARISH' in sig:
                bearish_score += w
            else:
                flat_score += w

        final_strength = weighted_strength_sum / total_weight if total_weight > 0 else 0.0

        if bullish_score > bearish_score and bullish_score > flat_score:
            direction = 'BULLISH'
            agreement_pct = (bullish_score / total_weight) * 100
        elif bearish_score > bullish_score and bearish_score > flat_score:
            direction = 'BEARISH'
            agreement_pct = (bearish_score / total_weight) * 100
        else:
            direction = 'NEUTRAL'
            agreement_pct = (flat_score / total_weight) * 100

        # --- ИСПРАВЛЕННЫЙ КОМПАРАТОР СТАРШЕГО ТАЙМФРЕЙМА ---
        def tf_to_minutes(tf_str: str) -> int:
            tf_str = tf_str.lower().strip()
            if 'm' in tf_str: return int(tf_str.replace('m', ''))
            if 'h' in tf_str: return int(tf_str.replace('h', '')) * 60
            if 'd' in tf_str: return int(tf_str.replace('d', '')) * 1440
            try:
                return int(tf_str)
            except ValueError:
                return 0

        # Поиск самого старшего ТФ строго по длине свечи, а не по искусственному весу
        senior_tf = max(summary, key=lambda x: tf_to_minutes(x['timeframe']))
        senior_sig = str(senior_tf['signal']).upper()

        # --- СТРОГАЯ ЗАЩИТА ОТ РАССИНХРОНИЗАЦИИ С ТРЕНДОМ ---
        if direction == 'BULLISH' and ('BEARISH' in senior_sig or 'SIDEWAYS' in senior_sig):
            logger.info(
                f"🚫 Фильтр структуры: Мелкие ТФ смотрят в Лонг, но старший ТФ ({senior_tf['timeframe']}) в состоянии {senior_sig}. Вход заблокирован.")
            direction = 'NEUTRAL'
            agreement_pct = 50.0
        elif direction == 'BEARISH' and ('BULLISH' in senior_sig or 'SIDEWAYS' in senior_sig):
            logger.info(
                f"🚫 Фильтр структуры: Мелкие ТФ смотрят в Шорт, но старший ТФ ({senior_tf['timeframe']}) в состоянии {senior_sig}. Вход заблокирован.")
            direction = 'NEUTRAL'
            agreement_pct = 50.0

        if agreement_pct >= ac.confidence_very_high:
            confidence = 'VERY HIGH'
        elif agreement_pct >= ac.confidence_high:
            confidence = 'HIGH'
        elif agreement_pct >= ac.confidence_moderate:
            confidence = 'MODERATE'
        else:
            confidence = 'LOW'

        trigger_trade = False
        if direction != 'NEUTRAL' and confidence in ['HIGH', 'VERY HIGH']:
            if abs(final_strength) >= ac.min_strength_for_trade:
                trigger_trade = True

        # --- БЕЗОПАСНЫЙ РАСЧЕТ ATR И ADX НА ОСНОВЕ СРЕДНЕВЗВЕШЕННЫХ ДАННЫХ ---
        has_atr_adx = all('atr' in item and 'adx' in item for item in summary)
        if has_atr_adx and total_weight > 0:
            final_atr = sum(item['atr'] * item['weight'] for item in summary) / total_weight
            final_adx = sum(item['adx'] * item['weight'] for item in summary) / total_weight
        else:
            # Резервные параметры от старшего ТФ
            final_atr = senior_tf.get('atr', senior_tf.get('close', 60000) * 0.01)
            final_adx = senior_tf.get('adx', 25.0)

        final_close = senior_tf.get('close', 0)

        return {
            'direction': direction, 'confidence': confidence, 'strength': round(final_strength, 1),
            'agreement': round(agreement_pct, 1), 'trigger_trade': trigger_trade,
            'total_timeframes': len(summary), 'atr': round(final_atr, 2), 'adx': round(final_adx, 1),
            'close': round(final_close, 2)
        }

    def print_analysis(self, analysis: Dict):
        if not analysis: return
        final = analysis['final_signal']
        details = analysis['mtf_details']

        logger.info(f"\n{'ТФ':>10} | {'Цена':>10} | {'Сигнал':>15} | {'Сила':>8} | {'Вес':>6}")
        logger.info("-" * 60)
        for item in details:
            logger.info(
                f"{item['timeframe']:>10} | ${item['close']:>9.2f} | {item['signal']:>15} | {item['strength']:>8.1f} | {item['weight']:>6.2f}")
        logger.info("-" * 60)
