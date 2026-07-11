"""
Оптимизированный модуль мультитаймфреймового анализа со взвешенным консенсусом.
"""

import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
from log import logger
from config import AnalysisConfig, Config
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator


class MultiTimeframeAnalyzer:
    """
    Мультитаймфреймовый анализатор со строгой фильтрацией по старшему тренду.
    """

    # Веса для таймфреймов (по умолчанию)
    DEFAULT_TF_WEIGHTS = {
        '5m': 0.2,
        '15m': 0.3,
        '30m': 0.5,
        '1h': 0.6,
        '4h': 0.8,
        '1d': 1.0
    }

    def __init__(
        self,
        timeframes: List[str] = None,
        exchange_name: str = 'bybit',
        symbol: str = 'BTC/USDT:USDT',
        tf_weights: Dict[str, float] = None
    ):
        """
        Инициализация мультитаймфреймового анализатора.

        Args:
            timeframes: список таймфреймов
            exchange_name: название биржи
            symbol: торговая пара
            tf_weights: веса таймфреймов
        """
        # Исправляем возможные опечатки в конфигурации
        raw_tfs = timeframes or ['5m', '15m', '30m']
        self.timeframes = self._normalize_timeframes(raw_tfs)
        self.symbol = symbol
        self.loader = ExchangeDataLoader(exchange_name, symbol=symbol)

        # Установка весов
        self.TF_WEIGHTS = tf_weights or self.DEFAULT_TF_WEIGHTS

        # Создание индикаторов для каждого таймфрейма
        self.indicators = {
            tf: AdvancedTrendSignalIndicator(Config())
            for tf in self.timeframes
        }

        self._cached_data: Dict[str, Optional[pd.DataFrame]] = {}

    def _normalize_timeframes(self, raw_tfs: List[str]) -> List[str]:
        """
        Нормализация таймфреймов.

        Args:
            raw_tfs: сырые таймфреймы

        Returns:
            Нормализованные таймфреймы
        """
        normalized = []
        for tf in raw_tfs:
            tf_lower = tf.lower().strip()
            # Если уже есть буква - оставляем как есть
            if 'm' in tf_lower or 'h' in tf_lower or 'd' in tf_lower:
                normalized.append(tf_lower)
            else:
                # Иначе добавляем 'm' (минуты)
                try:
                    # Пробуем преобразовать в число
                    int(tf_lower)
                    normalized.append(f"{tf_lower}m")
                except ValueError:
                    # Если не число - оставляем как есть
                    normalized.append(tf)
        return normalized

    def load_and_analyze(self, limit: int = 500) -> Dict:
        """
        Загрузка данных и мультитаймфреймовый анализ.

        Args:
            limit: количество свечей для загрузки

        Returns:
            Словарь с результатами анализа
        """
        logger.info(f"\n{'=' * 30}\nMTF АНАЛИЗ (КОНСЕНСУС): {self.symbol}\n{'=' * 30}")

        # Загрузка данных
        data = self.loader.load_multiple_timeframes_incremental(
            self.symbol,
            timeframes=tuple(self.timeframes),  # Преобразуем в tuple
            cached_data=self._cached_data,
            limit=limit
        )

        if not data:
            logger.error("Не удалось загрузить исторические свечи с биржи")
            return {}

        self._cached_data = data

        results = {}
        mtf_summary = []

        # Анализ каждого таймфрейма
        for tf in self.timeframes:
            if tf not in data or data[tf].empty:
                logger.warning(f"Нет данных для обработки таймфрейма {tf}")
                continue

            indicator = self.indicators[tf]
            result = indicator.generate_signal(data[tf])

            if result is None or len(result) == 0:
                logger.warning(f"Нет результата для таймфрейма {tf}")
                continue

            results[tf] = result

            # Исправлено: iloc вместо iloс
            last = result.iloc[-1]
            weight = self.TF_WEIGHTS.get(tf, 0.3)

            mtf_summary.append({
                'timeframe': tf,  # Исправлено: было '1timeframe'
                'signal': last.get('Signal', 'NEUTRAL'),
                'strength': last.get('Signal_Strength', 0),
                'trend': last.get('Trend_State', 'SIDEWAYS'),
                'angle': last.get('MA_Angle_Final', 0),
                'divergence': last.get('Divergence', 'NONE'),
                'close': last.get('close', last.get('Close', 0)),
                'weight': weight,
                'atr': last.get('ATR', 0),
                'adx': last.get('ADX', 0)
            })

        # Расчет финального сигнала
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
        Расчет финального сигнала на основе взвешенного консенсуса.

        Args:
            summary: список результатов по таймфреймам

        Returns:
            Словарь с финальным сигналом
        """
        ac = AnalysisConfig()

        if not summary:
            return {
                'direction': 'NEUTRAL',
                'confidence': 'LOW',
                'strength': 0,
                'agreement': 0,
                'trigger_trade': False,
                'total_timeframes': 0,
                'atr': 0,
                'adx': 0,
                'close': 0
            }

        total_weight = sum(item.get('weight', 0) for item in summary)
        if total_weight <= 0:
            total_weight = 1.0  # Защита от деления на ноль

        bullish_score = 0.0
        bearish_score = 0.0
        flat_score = 0.0
        weighted_strength_sum = 0.0

        for item in summary:
            sig = str(item.get('signal', 'NEUTRAL')).upper()
            w = item.get('weight', 0.3)
            strength = item.get('strength', 0)

            weighted_strength_sum += strength * w

            if 'STRONG BULLISH' in sig or 'BULLISH' in sig:
                bullish_score += w
            elif 'STRONG BEARISH' in sig or 'BEARISH' in sig:
                bearish_score += w
            else:
                flat_score += w

        final_strength = weighted_strength_sum / total_weight if total_weight > 0 else 0.0

        # Определение направления
        if bullish_score > bearish_score and bullish_score > flat_score:
            direction = 'BULLISH'
            agreement_pct = (bullish_score / total_weight) * 100
        elif bearish_score > bullish_score and bearish_score > flat_score:
            direction = 'BEARISH'
            agreement_pct = (bearish_score / total_weight) * 100
        else:
            direction = 'NEUTRAL'
            agreement_pct = (flat_score / total_weight) * 100

        # --- КОМПАРАТОР СТАРШЕГО ТАЙМФРЕЙМА ---
        def tf_to_minutes(tf_str: str) -> int:
            """Преобразование таймфрейма в минуты."""
            tf_str = tf_str.lower().strip()
            if 'm' in tf_str:
                try:
                    return int(tf_str.replace('m', ''))
                except ValueError:
                    return 0
            if 'h' in tf_str:
                try:
                    return int(tf_str.replace('h', '')) * 60
                except ValueError:
                    return 0
            if 'd' in tf_str:
                try:
                    return int(tf_str.replace('d', '')) * 1440
                except ValueError:
                    return 0
            try:
                return int(tf_str)
            except ValueError:
                return 0

        # Поиск самого старшего ТФ
        try:
            senior_tf = max(summary, key=lambda x: tf_to_minutes(x.get('timeframe', '1m')))
        except ValueError:
            # Если не удалось найти старший ТФ, берем первый
            senior_tf = summary[0] if summary else None

        # --- СТРОГАЯ ЗАЩИТА ОТ РАССИНХРОНИЗАЦИИ С ТРЕНДОМ ---
        if senior_tf:
            senior_sig = str(senior_tf.get('signal', 'NEUTRAL')).upper()
            senior_tf_name = senior_tf.get('timeframe', 'unknown')

            if direction == 'BULLISH' and ('BEARISH' in senior_sig or 'SIDEWAYS' in senior_sig):
                logger.info(
                    f"Фильтр структуры: Мелкие ТФ смотрят в Лонг, но старший ТФ "
                    f"({senior_tf_name}) в состоянии {senior_sig}. Вход заблокирован."
                )
                direction = 'NEUTRAL'
                agreement_pct = 50.0

            elif direction == 'BEARISH' and ('BULLISH' in senior_sig or 'SIDEWAYS' in senior_sig):
                logger.info(
                    f"Фильтр структуры: Мелкие ТФ смотрят в Шорт, но старший ТФ "
                    f"({senior_tf_name}) в состоянии {senior_sig}. Вход заблокирован."
                )
                direction = 'NEUTRAL'
                agreement_pct = 50.0

        # Определение уверенности
        if agreement_pct >= ac.confidence_very_high:
            confidence = 'VERY HIGH'
        elif agreement_pct >= ac.confidence_high:
            confidence = 'HIGH'
        elif agreement_pct >= ac.confidence_moderate:
            confidence = 'MODERATE'
        else:
            confidence = 'LOW'

        # Разрешение на торговлю
        trigger_trade = False
        if direction != 'NEUTRAL' and confidence in ['HIGH', 'VERY HIGH']:
            if abs(final_strength) >= ac.min_strength_for_trade:
                trigger_trade = True

        # --- РАСЧЕТ ATR И ADX ---
        has_atr_adx = all('atr' in item and 'adx' in item for item in summary)

        if has_atr_adx and total_weight > 0:
            final_atr = sum(item.get('atr', 0) * item.get('weight', 0.3) for item in summary) / total_weight
            final_adx = sum(item.get('adx', 0) * item.get('weight', 0.3) for item in summary) / total_weight
            final_close = summary[-1].get('close', 0) if summary else 0
        else:
            # Резервные параметры от старшего ТФ
            if senior_tf:
                final_atr = senior_tf.get('atr', senior_tf.get('close', 60000) * 0.01)
                final_adx = senior_tf.get('adx', 25.0)
                final_close = senior_tf.get('close', 0)
            else:
                final_atr = 0
                final_adx = 0
                final_close = 0

        return {
            'direction': direction,
            'confidence': confidence,
            'strength': round(final_strength, 1),
            'agreement': round(agreement_pct, 1),
            'trigger_trade': trigger_trade,
            'total_timeframes': len(summary),
            'atr': round(final_atr, 2),
            'adx': round(final_adx, 1),
            'close': round(final_close, 2)
        }

    def print_analysis(self, analysis: Dict):
        """
        Печать результатов анализа в консоль.

        Args:
            analysis: результаты анализа
        """
        if not analysis:
            logger.warning("Нет данных для печати")
            return

        final = analysis.get('final_signal', {})
        details = analysis.get('mtf_details', [])

        if not details:
            logger.warning("Нет деталей по таймфреймам")
            return

        logger.info(f"\n{'ТФ':>10} | {'Цена':>10} | {'Сигнал':>15} | {'Сила':>8} | {'Вес':>6}")
        logger.info("-" * 60)

        for item in details:
            logger.info(
                f"{item.get('timeframe', 'N/A'):>10} | "
                f"${item.get('close', 0):>9.2f} | "
                f"{item.get('signal', 'NEUTRAL'):>15} | "
                f"{item.get('strength', 0):>8.1f} | "
                f"{item.get('weight', 0):>6.2f}"
            )

        logger.info("-" * 60)

        # Дополнительная информация
        if final:
            logger.info(f"ФИНАЛЬНЫЙ СИГНАЛ: {final.get('direction', 'NEUTRAL')}")
            logger.info(f"Уверенность: {final.get('confidence', 'LOW')}")
            logger.info(f"Сила: {final.get('strength', 0):.1f}")
            logger.info(f"Согласие: {final.get('agreement', 0):.1f}%")
            logger.info(f"Торговать: {'ДА' if final.get('trigger_trade', False) else 'НЕТ'}")
            logger.info(f"ATR: ${final.get('atr', 0):.2f}")
            logger.info(f"ADX: {final.get('adx', 0):.1f}")
            logger.info("-" * 60)


# Вспомогательная функция для создания анализатора
def create_mtf_analyzer(config) -> MultiTimeframeAnalyzer:
    """
    Создание мультитаймфреймового анализатора из конфигурации.

    Args:
        config: объект конфигурации

    Returns:
        Экземпляр MultiTimeframeAnalyzer
    """
    return MultiTimeframeAnalyzer(
        timeframes=list(config.mtf_timeframes),
        exchange_name=config.exchange_name,
        symbol=config.symbol
    )


# Вспомогательная функция для запуска анализа
def run_mtf_analysis(config, mtf_analyzer=None) -> Dict:
    """
    Запуск мультитаймфреймового анализа.

    Args:
        config: объект конфигурации
        mtf_analyzer: существующий анализатор (опционально)

    Returns:
        Результаты анализа
    """
    if mtf_analyzer is None:
        mtf_analyzer = create_mtf_analyzer(config)

    analysis = mtf_analyzer.load_and_analyze(limit=config.analysis_limit)

    if not analysis:
        logger.error("Ошибка при выполнении анализа")
        return {}

    return {
        'analysis': analysis,
        'analyzer': mtf_analyzer
    }