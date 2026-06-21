"""
Модуль мультитаймфреймового анализа.

Содержит класс:
- MultiTimeframeAnalyzer: агрегация сигналов с разных таймфреймов
"""

# import pandas as pd
from typing import Dict, List
from datetime import datetime

from config import Config
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator


class MultiTimeframeAnalyzer:
    """
    Мультитаймфреймовый анализатор.

    Анализирует сигналы на разных таймфреймах и агрегирует их
    с учетом весов для получения финального сигнала.

    Старшие таймфреймы имеют больший вес при агрегации.

    Examples:
        >>> mtf = MultiTimeframeAnalyzer(
        ...     timeframes=['1h', '4h', '1d'],
        ...     exchange_name='binance',
        ...     symbol='BTC/USDT'
        ... )
        >>> analysis = mtf.load_and_analyze(limit=500)
        >>> mtf.print_analysis(analysis)
    """

    # Веса таймфреймов для агрегации сигналов
    TF_WEIGHTS = {
        '1m': 0.1, '5m': 0.15, '15m': 0.2,
        '30m': 0.25, '1h': 0.35, '4h': 0.5,
        '1d': 0.7, '1w': 0.9
    }

    def __init__(self,
                 timeframes: List[str] = None,
                 exchange_name: str = 'binance',
                 symbol: str = 'BTC/USDT'):
        """
        Инициализация MTF анализатора.

        Args:
            timeframes: список таймфреймов (по умолчанию ['1h', '4h', '1d'])
            exchange_name: название биржи
            symbol: торговая пара
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
        Загружает данные и проводит MTF анализ.

        Процесс:
        1. Загружает данные для всех таймфреймов
        2. Для каждого ТФ создает индикатор с оптимальной конфигурацией
        3. Генерирует сигналы
        4. Агрегирует результаты

        Args:
            limit: количество свечей для каждого таймфрейма

        Returns:
            Словарь с результатами анализа
        """
        print(f"\n{'=' * 60}")
        print(f"📊 МУЛЬТИТАЙМФРЕЙМОВЫЙ АНАЛИЗ: {self.symbol}")
        print(f"{'=' * 60}")

        data = self.loader.load_multiple_timeframes(
            self.symbol,
            timeframes=self.timeframes,
            limit=limit
        )

        if not data:
            print("❌ Не удалось загрузить данные")
            return None

        results = {}
        mtf_summary = []

        for tf in self.timeframes:
            if tf not in data:
                print(f"⚠️ Нет данных для {tf}")
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
        Расчет финального сигнала на основе всех таймфреймов.

        Агрегация:
        - Взвешенная сила = Σ(сила × вес) / Σ(весов)
        - Согласованность = большинство / всего
        - Противоречие старшему ТФ → понижение уверенности

        Args:
            summary: список с сигналами по таймфреймам

        Returns:
            Словарь с финальным сигналом
        """
        if not summary:
            return {'direction': 'N/A', 'confidence': 'N/A', 'strength': 0}

        total_weight = sum(item['weight'] for item in summary)
        weighted_strength = sum(
            item['strength'] * item['weight'] for item in summary
        ) / total_weight if total_weight > 0 else 0

        bullish_count = sum(1 for s in summary if 'BULLISH' in str(s['signal']).upper())
        bearish_count = sum(1 for s in summary if 'BEARISH' in str(s['signal']).upper())
        total = len(summary)

        if bullish_count > bearish_count:
            direction = 'BULLISH'
            agreement = bullish_count / total
        elif bearish_count > bullish_count:
            direction = 'BEARISH'
            agreement = bearish_count / total
        else:
            direction = 'NEUTRAL'
            agreement = 0.5

        if agreement >= 0.8:
            confidence = 'VERY HIGH'
        elif agreement >= 0.67:
            confidence = 'HIGH'
        elif agreement >= 0.5:
            confidence = 'MODERATE'
        else:
            confidence = 'LOW'

        if len(summary) >= 2:
            senior_tf = max(summary, key=lambda x: self.TF_WEIGHTS.get(x['timeframe'], 0))
            junior_tf = min(summary, key=lambda x: self.TF_WEIGHTS.get(x['timeframe'], 0))

            if 'BULLISH' in str(senior_tf['signal']) and 'BEARISH' in str(junior_tf['signal']):
                if confidence == 'VERY HIGH':
                    confidence = 'HIGH'
                elif confidence == 'HIGH':
                    confidence = 'MODERATE'
            elif 'BEARISH' in str(senior_tf['signal']) and 'BULLISH' in str(junior_tf['signal']):
                if confidence == 'VERY HIGH':
                    confidence = 'HIGH'
                elif confidence == 'HIGH':
                    confidence = 'MODERATE'

        return {
            'direction': direction,
            'confidence': confidence,
            'strength': round(weighted_strength, 1),
            'agreement': round(agreement * 100, 1),
            'buy_signals': bullish_count,
            'sell_signals': bearish_count,
            'total_timeframes': total
        }

    def print_analysis(self, analysis: Dict):
        """
        Вывод результатов MTF анализа в консоль.

        Args:
            analysis: результат load_and_analyze()
        """
        if not analysis:
            return

        final = analysis['final_signal']
        details = analysis['mtf_details']

        print(f"\n{'=' * 60}")
        print(f"📊 MTF АНАЛИЗ: {self.symbol}")
        print(f"🕐 {analysis['timestamp'].strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 60}")

        print(f"\n{'ТФ':<6} {'Цена':>10} {'Сигнал':<30} {'Сила':>6} {'Тренд':<18} {'Угол':>8}")
        print("-" * 85)

        for item in details:
            tf = item['timeframe']
            price = f"${item['close']:.2f}"
            signal = item['signal'][:28]
            strength = f"{item['strength']:.1f}"
            trend = item['trend'][:16]
            angle = f"{item['angle']:.2f}°"

            print(f"{tf:<6} {price:>10} {signal:<30} {strength:>6} {trend:<18} {angle:>8}")

        print(f"\n{'=' * 60}")
        print(f"🎯 ИТОГОВЫЙ СИГНАЛ")
        print(f"{'=' * 60}")

        if final['direction'] == 'BULLISH':
            emoji = '🟢'
        elif final['direction'] == 'BEARISH':
            emoji = '🔴'
        else:
            emoji = '⚪'

        print(f"Направление:  {emoji} {final['direction']}")
        print(f"Уверенность:  {final['confidence']}")
        print(f"Сила сигнала: {final['strength']:.1f}")
        print(f"Согласие ТФ:  {final['agreement']}%")
        print(f"Buy/Sell:     {final['buy_signals']}/{final['sell_signals']}")

        print(f"\n💡 РЕКОМЕНДАЦИЯ:")
        if final['confidence'] in ['VERY HIGH', 'HIGH'] and final['direction'] != 'NEUTRAL':
            if final['direction'] == 'BULLISH':
                print("   ✅ Можно рассматривать LONG позиции")
            else:
                print("   ✅ Можно рассматривать SHORT позиции")
        elif final['confidence'] == 'MODERATE':
            print("   ⚠️ Ждать подтверждения, открывать осторожно")
        else:
            print("   ❌ Лучше воздержаться от торговли")
