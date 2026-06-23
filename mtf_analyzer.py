"""
Оптимизированный модуль мультитаймфреймового анализа с взвешенным консенсусом
и защитой от рассинхронизации трендов.
"""
from typing import Dict, List
from datetime import datetime
from config import Config
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator
from log import logger


class MultiTimeframeAnalyzer:
    """
    Мультитаймфреймовый анализатор.
    Математически агрегирует сигналы с учетом весов и жестко блокирует торговлю
    в моменты рассинхронизации старших и младших периодов.
    """
    # Математические веса таймфреймов (младшие не могут перевесить старшую структуру)
    TF_WEIGHTS = {
        '1m': 0.05, '5m': 0.10, '15m': 0.15,
        '30m': 0.20, '1h': 0.35, '4h': 0.60,
        '1d': 0.85, '1w': 1.00
    }

    def __init__(self,
                 timeframes: List[str] = None,
                 exchange_name: str = 'binance',
                 symbol: str = 'BTC/USDT'):
        """
        Инициализация MTF анализатора.
        """
        self.timeframes = timeframes or ['1h', '4h', '1d']
        self.symbol = symbol
        self.loader = ExchangeDataLoader(exchange_name)
        self.indicators = {
            tf: AdvancedTrendSignalIndicator(Config.for_timeframe(tf))
            for tf in self.timeframes
        }

    def load_and_analyze(self, limit: int = 500) -> Dict:
        """
        Загружает данные и проводит скоринговый MTF анализ.
        """
        logger.info(f"\n{'=' * 60}")
        logger.info(f" 📊 МУЛЬТИТАЙМФРЕЙМОВЫЙ АНАЛИЗ (КОНСЕНСУС): {self.symbol}")
        logger.info(f"{'=' * 60}")

        data = self.loader.load_multiple_timeframes(
            self.symbol,
            timeframes=self.timeframes,
            limit=limit
        )
        if not data:
            logger.info(" ❌ Не удалось загрузить данные с биржи")
            return None

        results = {}
        mtf_summary = []

        for tf in self.timeframes:
            if tf not in data:
                logger.info(f" ⚠️ Нет данных для таймфрейма {tf}")
                continue

            indicator = self.indicators[tf]
            result = indicator.generate_signal(data[tf])
            results[tf] = result

            last = result.iloc[-1]
            weight = self.TF_WEIGHTS.get(tf, 0.3)

            mtf_summary.append({
                'timeframe': tf,
                'signal': last['Signal'],
                'strength': last['Signal_Strength'],
                'trend': last['Trend_State'],
                'angle': last['MA_Angle_Final'],
                'divergence': last['Divergence'],
                'close': last['close'],
                'weight': weight
            })

        # Вычисление финального математического консенсуса
        final_signal = self._calculate_final_signal(mtf_summary)

        return {
            'symbol': self.symbol,
            'timeframes': self.timeframes,
            'timestamp': datetime.now(),
            'mtf_details': mtf_summary,
            'final_signal': final_signal,
            'results': results
        }

    def _calculate_final_signal(self, summary: List[Dict]) -> Dict:
        """
        МАТЕМАТИЧЕСКИЙ СКОРИНГ КОНСЕНСУСА.
        Исключает ложные входы по простому арифметическому большинству мелких ТФ.
        """
        if not summary:
            return {'direction': 'NEUTRAL', 'confidence': 'LOW', 'strength': 0, 'trigger_trade': False}

        total_weight = sum(item['weight'] for item in summary)

        # Считаем взвешенные голоса за каждое направление
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

        # Финальная средневзвешенная сила сигнала
        final_strength = weighted_strength_sum / total_weight if total_weight > 0 else 0.0

        # Выделяем доминирующее взвешенное направление
        if bullish_score > bearish_score and bullish_score > flat_score:
            direction = 'BULLISH'
            agreement_pct = (bullish_score / total_weight) * 100
        elif bearish_score > bullish_score and bearish_score > flat_score:
            direction = 'BEARISH'
            agreement_pct = (bearish_score / total_weight) * 100
        else:
            direction = 'NEUTRAL'
            agreement_pct = (flat_score / total_weight) * 100

        # Находим самый старший (тяжелый) таймфрейм в пуле для фильтра структуры
        senior_tf = max(summary, key=lambda x: x['weight'])
        senior_sig = str(senior_tf['signal']).upper()

        # --- ЖЕСТКАЯ ЗАЩИТА ОТ РАССИНХРОНИЗАЦИИ ---
        # Если итоговый вектор мелких ТФ идет против старшего тренда, блокируем вход
        if direction == 'BULLISH' and ('BEARISH' in senior_sig or 'SIDEWAYS' in senior_sig):
            direction = 'NEUTRAL'
            agreement_pct = 50.0
        elif direction == 'BEARISH' and ('BULLISH' in senior_sig or 'SIDEWAYS' in senior_sig):
            direction = 'NEUTRAL'
            agreement_pct = 50.0

        # Градация уверенности на основе % взвешенного согласия
        if agreement_pct >= 75.0:
            confidence = 'VERY HIGH'
        elif agreement_pct >= 60.0:
            confidence = 'HIGH'
        elif agreement_pct >= 45.0:
            confidence = 'MODERATE'
        else:
            confidence = 'LOW'

        # Разрешение на открытие рыночного ордера (Сигнал должен быть четким и сильным)
        trigger_trade = False
        if direction != 'NEUTRAL' and confidence in ['HIGH', 'VERY HIGH']:
            if abs(final_strength) >= 40.0:  # Защита от вялых движений
                trigger_trade = True

        return {
            'direction': direction,
            'confidence': confidence,
            'strength': round(final_strength, 1),
            'agreement': round(agreement_pct, 1),
            'trigger_trade': trigger_trade,
            'total_timeframes': len(summary)
        }

    def print_analysis(self, analysis: Dict):
        """
        Красивый и информативный вывод скоринга в консоль.
        """
        if not analysis:
            return

        final = analysis['final_signal']
        details = analysis['mtf_details']

        logger.info(f"\n{'ТФ':<6} {'Цена':>10} {'Внутренний Сигнал':<25} {'Сила':>6} {'Глобальный Тренд':<18} {'Вес':>5}")
        logger.info("-" * 75)
        for item in details:
            logger.info(
                f"{item['timeframe']:<6} ${item['close']:>9.2f} {item['signal']:<25} {item['strength']:>6.1f} {item['trend']:<18} {item['weight']:>5.2f}")

        logger.info(f"\n{'=' * 60}")
        logger.info(f" 🎯 МАТЕМАТИЧЕСКИЙ СИНТЕЗ СИСТЕМЫ")
        logger.info(f"{'=' * 60}")

        emoji = '🟢' if final['direction'] == 'BULLISH' else ('🔴' if final['direction'] == 'BEARISH' else '⚪')
        logger.info(f"Направление: {emoji} {final['direction']}")
        logger.info(f"Уверенность (Согласие): {final['confidence']} ({final['agreement']}%)")
        logger.info(f"Взвешенная Сила:  {final['strength']} / 100")
        logger.info(f"\n 💡 ПРИКАЗ ДЛЯ ИСПОЛНИТЕЛЬНОГО МОДУЛЯ:")
        if final['trigger_trade']:
            logger.info(f" 🔥 [ВХОД РАЗРЕШЕН] Открывать позицию {final['direction']} с полным АТР риск-профилем.")
        else:
            logger.info(" 🛑 [ТОРГОВЛЯ ЗАБЛОКИРОВАНА] Нет рыночного консенсуса или обнаружен флэт. Ожидание.")
