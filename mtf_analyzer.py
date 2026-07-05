"""
Оптимизированный модуль мультитаймфреймового анализа с взвешенным консенсусом
и защитой от рассинхронизации трендов.
"""
import pandas as pd
from typing import Dict, List, Optional
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

    Оптимизация загрузки:
    - При первом запуске загружает limit свечей для каждого ТФ
    - В последующих циклах догружает только новые закрытые свечи
    - Хранит кеш DataFrame'ов в self._cached_data
    """
    # Математические веса таймфреймов (младшие не могут перевесить старшую структуру)
    TF_WEIGHTS = {
        '1m': 0.05, '5m': 0.20, '15m': 0.20,
        '30m': 0.20, '1h': 0.35, '4h': 0.60,
        '1d': 0.85, '1w': 1.00
    }

    def __init__(self,
                 timeframes: List[str] = None,
                 exchange_name: str = 'bybit',
                 symbol: str = 'BTC/USDT'):
        """
        Инициализация MTF анализатора.
        """
        self.timeframes = timeframes or ['1h', '4h', '1d']
        self.symbol = symbol
        self.loader = ExchangeDataLoader(exchange_name, symbol=symbol)
        self.indicators = {
            tf: AdvancedTrendSignalIndicator(Config.for_timeframe(tf))
            for tf in self.timeframes
        }
        # Кеш для хранения загруженных данных между циклами
        self._cached_data: Dict[str, Optional[pd.DataFrame]] = {}

    def load_and_analyze(self, limit: int = 500) -> Dict:
        """
        Загружает данные и проводит скоринговый MTF анализ.
        При повторных вызовах догружает только новые свечи.

        Args:
            limit: максимальное количество свечей для хранения

        Returns:
            Словарь с результатами анализа
        """
        logger.info(f"\n{'=' * 30}")
        logger.info(f" 📊 MTF АНАЛИЗ (КОНСЕНСУС): {self.symbol}")
        logger.info(f"{'=' * 30}")

        # Инкрементальная загрузка — догружаем только новые свечи
        data = self.loader.load_multiple_timeframes_incremental(
            self.symbol,
            timeframes=self.timeframes,
            cached_data=self._cached_data,
            limit=limit
        )

        if not data:
            logger.info(" ❌ Не удалось загрузить данные с биржи")
            return None

        # Сохраняем в кеш для следующего цикла
        self._cached_data = data

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
                'weight': weight,
                'atr': last.get('ATR', 0),
                'adx': last.get('ADX', 0)
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
        Возвращает также ATR и ADX для расчета динамических SL/TP.
        """
        if not summary:
            return {
                'direction': 'NEUTRAL',
                'confidence': 'LOW',
                'strength': 0,
                'trigger_trade': False,
                'atr': 0,
                'adx': 0,
                'close': 0
            }

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

        # --- РАСЧЕТ ATR И ADX ДЛЯ ДИНАМИЧЕСКИХ SL/TP ---
        # Берем данные со старшего (самого весомого) таймфрейма
        # Если нет прямых данных ATR/ADX в summary - рассчитываем средневзвешенные

        # Проверяем, есть ли ATR и ADX в summary (добавлены из индикатора)
        has_atr_adx = all('atr' in item and 'adx' in item for item in summary)

        if has_atr_adx:
            # Средневзвешенные ATR и ADX по всем таймфреймам
            weighted_atr = sum(item['atr'] * item['weight'] for item in summary) / total_weight
            weighted_adx = sum(item['adx'] * item['weight'] for item in summary) / total_weight

            # Также берем значения со старшего таймфрейма (приоритет)
            senior_atr = senior_tf.get('atr', weighted_atr)
            senior_adx = senior_tf.get('adx', weighted_adx)

            # Используем значения со старшего таймфрейма для более консервативного расчета
            final_atr = senior_atr  # Старший ТФ важнее для расчета дистанции стопа
            final_adx = senior_adx  # Старший ТФ показывает глобальный тренд
        else:
            # Если данных нет - используем последнюю цену закрытия для приблизительного ATR
            # (запасной вариант, если индикатор не отдает ATR/ADX)
            last_close = senior_tf.get('close', 0)
            final_atr = last_close * 0.01  # Примерно 1% от цены как ATR
            final_adx = 25.0  # Умеренное значение ADX по умолчанию
            logger.warning("⚠️ ATR/ADX не найдены в данных, использую запасные значения")

        # Получаем цену закрытия со старшего таймфрейма
        final_close = senior_tf.get('close', 0)

        return {
            'direction': direction,
            'confidence': confidence,
            'strength': round(final_strength, 1),
            'agreement': round(agreement_pct, 1),
            'trigger_trade': trigger_trade,
            'total_timeframes': len(summary),
            # Данные для динамических SL/TP
            'atr': round(final_atr, 2),
            'adx': round(final_adx, 1),
            'close': round(final_close, 2)
        }

    def print_analysis(self, analysis: Dict):
        """
        Красивый и информативный вывод скоринга в консоль.
        """
        if not analysis:
            return

        final = analysis['final_signal']
        details = analysis['mtf_details']

        logger.info(f"\n{'ТФ':>33} | {'Цена':>7} | {'Сигнал':} | {'Сила':} | {'Тренд':>5} | {'Вес':}")
        logger.info("-" * 30)
        for item in details:
            logger.info(
                f"{item['timeframe']:} | ${item['close']:.2f} | {item['signal']:} | {item['strength']:.1f} | {item['trend']:} | {item['weight']:.2f}")

        logger.info(f"\n{'=' * 30}")
        logger.debug(f" 🎯 МАТЕМАТИЧЕСКИЙ СИНТЕЗ СИСТЕМЫ")
        logger.debug(f"{'=' * 30}")

        emoji = '🟢' if final['direction'] == 'BULLISH' else ('🔴' if final['direction'] == 'BEARISH' else '⚪')
        logger.debug(f"Направление: {emoji} {final['direction']}")
        logger.debug(f"Уверенность (Согласие): {final['confidence']} ({final['agreement']}%)")
        logger.debug(f"Взвешенная Сила:  {final['strength']} / 100")
        logger.debug(f"\n 💡 ПРИКАЗ ДЛЯ ИСПОЛНИТЕЛЬНОГО МОДУЛЯ:")
        if final['trigger_trade']:
            logger.warning(f" 🔥 [ВХОД РАЗРЕШЕН] Открывать позицию {final['direction']} с полным АТР риск-профилем.")
        else:
            logger.info("🛑[ТОРГ БЛОК] Нет консенсуса или флэт. Ожидание.")