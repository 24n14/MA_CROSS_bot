"""
Мультитаймфреймовый анализатор со строгой фильтрацией по старшему тренду.
"""

import pandas as pd
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import warnings

from log import logger
from config import AnalysisConfig, Config
from exchange import ExchangeDataLoader
from indicator import AdvancedTrendSignalIndicator

warnings.filterwarnings('ignore')


class MultiTimeframeAnalyzer:
    """
    Мультитаймфреймовый анализатор со строгой фильтрацией по старшему тренду.

    🔥 ИСПРАВЛЕНО:
    - Добавлена обработка ошибок
    - Исправлен парсинг таймфреймов
    - Смягчена фильтрация старшего ТФ
    - Добавлена нормализация весов
    - Исправлен trigger_trade
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

        # 🔥 ФИКС: Нормализация весов
        raw_weights = tf_weights or self.DEFAULT_TF_WEIGHTS
        self.TF_WEIGHTS = self._normalize_weights(raw_weights)

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
            List[str]: нормализованные таймфреймы
        """
        normalized = []
        for tf in raw_tfs:
            tf_lower = tf.lower().strip()
            # Если уже есть буква - оставляем как есть
            if any(x in tf_lower for x in ['m', 'h', 'd']):
                normalized.append(tf_lower)
            else:
                # Иначе добавляем 'm' (минуты)
                try:
                    int(tf_lower)
                    normalized.append(f"{tf_lower}m")
                except ValueError:
                    # Если не число - оставляем как есть
                    normalized.append(tf)
        return normalized

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        🔥 ФИКС: Нормализация весов, чтобы сумма была равна 1.0.

        Args:
            weights: словарь весов

        Returns:
            Dict[str, float]: нормализованные веса
        """
        total = sum(weights.values())
        if total == 0:
            return weights
        return {tf: w / total for tf, w in weights.items()}

    def _tf_to_minutes(self, tf_str: str) -> int:
        """
        🔥 ФИКС: Преобразование таймфрейма в минуты.

        Args:
            tf_str: строка таймфрейма

        Returns:
            int: количество минут
        """
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

    def load_and_analyze(self, limit: int = 500) -> Dict:
        """
        Загрузка данных и мультитаймфреймовый анализ.

        🔥 ИСПРАВЛЕНО:
        - Добавлена обработка ошибок
        - Исправлен метод загрузки данных
        - Добавлена валидация данных

        Args:
            limit: количество свечей для загрузки

        Returns:
            Dict: результаты анализа
        """
        logger.info(f"\n{'=' * 30}\nMTF АНАЛИЗ (КОНСЕНСУС): {self.symbol}\n{'=' * 30}")

        # 🔥 ФИКС: Загрузка данных с обработкой ошибок
        data = {}
        for tf in self.timeframes:
            try:
                # Пробуем разные методы загрузки
                tf_data = None

                # Метод 1: load_multiple_timeframes (если существует)
                if hasattr(self.loader, 'load_multiple_timeframes'):
                    # Загружаем все сразу
                    all_data = self.loader.load_multiple_timeframes(
                        self.symbol,
                        timeframes=self.timeframes,
                        limit=limit
                    )
                    if all_data and tf in all_data:
                        tf_data = all_data[tf]
                else:
                    # Метод 2: Загружаем отдельно
                    if hasattr(self.loader, 'load_ohlcv'):
                        tf_data = self.loader.load_ohlcv(
                            symbol=self.symbol,
                            timeframe=tf,
                            limit=limit
                        )
                    elif hasattr(self.loader, 'get_klines'):
                        tf_data = self.loader.get_klines(
                            symbol=self.symbol,
                            interval=tf,
                            limit=limit
                        )
                    else:
                        logger.error(f"Не найден метод загрузки данных для {tf}")
                        continue

                # Проверяем данные
                if tf_data is not None and not tf_data.empty:
                    data[tf] = tf_data
                    logger.info(f"✅ Загружено {len(tf_data)} свечей для {tf}")
                else:
                    logger.warning(f"⚠️ Нет данных для {tf}")

            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {tf}: {e}")
                continue

        # Проверяем, что данные загружены
        if not data:
            logger.error("❌ Не удалось загрузить исторические свечи с биржи")
            return {}

        self._cached_data = data
        results = {}
        mtf_summary = []

        # Анализ каждого таймфрейма
        for tf in self.timeframes:
            if tf not in data or data[tf].empty:
                logger.warning(f"⚠️ Нет данных для обработки таймфрейма {tf}")
                continue

            # 🔥 ФИКС: try-except для generate_signal
            try:
                indicator = self.indicators[tf]
                result = indicator.generate_signal(data[tf])

                if result is None or len(result) == 0:
                    logger.warning(f"⚠️ Нет результата для таймфрейма {tf}")
                    continue

            except Exception as e:
                logger.error(f"❌ Ошибка анализа {tf}: {e}")
                continue

            results[tf] = result

            # 🔥 ФИКС: Исправлено iloc (было iloс)
            last = result.iloc[-1]
            weight = self.TF_WEIGHTS.get(tf, 0.3)

            mtf_summary.append({
                'timeframe': tf,
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

        if not mtf_summary:
            logger.error("❌ Нет данных для формирования сводки")
            return {}

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

        🔥 ИСПРАВЛЕНО:
        - Исправлен парсинг таймфреймов
        - Смягчена фильтрация старшего ТФ
        - Добавлена проверка на None
        - Сделан trigger_trade менее строгим
        - Исправлена проверка ATR/ADX

        Args:
            summary: список результатов по таймфреймам

        Returns:
            Dict: финальный сигнал
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

        # Расчет взвешенных баллов
        total_weight = sum(item.get('weight', 0) for item in summary)
        if total_weight <= 0:
            total_weight = 1.0

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

        # 🔥 ФИКС: Поиск самого старшего ТФ с проверкой
        senior_tf = None
        if summary:
            try:
                senior_tf = max(
                    summary,
                    key=lambda x: self._tf_to_minutes(x.get('timeframe', '1m'))
                )
            except (ValueError, TypeError):
                senior_tf = summary[0] if summary else None

        # 🔥 ФИКС: Строгая защита от расссинхронизации с трендом
        # Блокируем только при явном противоречии, SIDEWAYS не блокирует
        if senior_tf:
            senior_sig = str(senior_tf.get('signal', 'NEUTRAL')).upper()
            senior_tf_name = senior_tf.get('timeframe', 'unknown')

            if direction == 'BULLISH' and 'BEARISH' in senior_sig:
                logger.info(
                    f"🔒 Фильтр структуры: Мелкие ТФ в Лонг, "
                    f"но старший ТФ ({senior_tf_name}) в Шорт. Вход заблокирован."
                )
                direction = 'NEUTRAL'
                agreement_pct = 50.0
            elif direction == 'BEARISH' and 'BULLISH' in senior_sig:
                logger.info(
                    f"🔒 Фильтр структуры: Мелкие ТФ в Шорт, "
                    f"но старший ТФ ({senior_tf_name}) в Лонг. Вход заблокирован."
                )
                direction = 'NEUTRAL'
                agreement_pct = 50.0
            # 🔥 ФИКС: SIDEWAYS не блокирует, а просто снижает уверенность
            elif direction != 'NEUTRAL' and 'SIDEWAYS' in senior_sig:
                logger.info(
                    f"ℹ️ Старший ТФ ({senior_tf_name}) в боковике - "
                    f"снижение уверенности, но вход не блокируется"
                )
                # Снижаем согласие, но не блокируем
                agreement_pct = agreement_pct * 0.8

        # Определение уверенности
        confidence_thresholds = {
            'very_high': getattr(ac, 'confidence_very_high', 80),
            'high': getattr(ac, 'confidence_high', 65),
            'moderate': getattr(ac, 'confidence_moderate', 50),
        }

        if agreement_pct >= confidence_thresholds['very_high']:
            confidence = 'VERY HIGH'
        elif agreement_pct >= confidence_thresholds['high']:
            confidence = 'HIGH'
        elif agreement_pct >= confidence_thresholds['moderate']:
            confidence = 'MODERATE'
        else:
            confidence = 'LOW'

        # 🔥 ФИКС: Разрешение на торговлю (смягченное)
        trigger_trade = False
        min_strength = getattr(ac, 'min_strength_for_trade', 30.0)

        if direction != 'NEUTRAL':
            if confidence in ['HIGH', 'VERY HIGH']:
                if abs(final_strength) >= min_strength:
                    trigger_trade = True
            elif confidence == 'MODERATE':
                # MODERATE требует более сильного сигнала
                if abs(final_strength) >= min_strength * 1.5:
                    trigger_trade = True
                    logger.info(f"📈 MODERATE уверенность, но сильный сигнал - разрешена торговля")

        # 🔥 ФИКС: Расчет ATR и ADX с проверкой валидности
        has_atr_adx = all(
            'atr' in item and 'adx' in item
            and item.get('atr', 0) > 0
            and item.get('adx', 0) > 0
            for item in summary
        )

        if has_atr_adx and total_weight > 0:
            final_atr = sum(
                item.get('atr', 0) * item.get('weight', 0.3)
                for item in summary
            ) / total_weight
            final_adx = sum(
                item.get('adx', 0) * item.get('weight', 0.3)
                for item in summary
            ) / total_weight
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

        🔥 ИСПРАВЛЕНО:
        - Исправлена синтаксическая ошибка в f-строке
        - Улучшено форматирование

        Args:
            analysis: результаты анализа
        """
        if not analysis:
            logger.warning("⚠️ Нет данных для печати")
            return

        final = analysis.get('final_signal', {})
        details = analysis.get('mtf_details', [])

        if not details:
            logger.warning("⚠️ Нет деталей по таймфреймам")
            return

        logger.info(f"\n{'ТФ':>10} | {'Цена':>10} | {'Сигнал':>18} | {'Сила':>8} | {'Вес':>6}")
        logger.info("-" * 65)

        for item in details:
            signal = item.get('signal', 'NEUTRAL')
            # Обрезаем длинные сигналы
            if len(signal) > 18:
                signal = signal[:15] + '...'

            logger.info(
                f"{item.get('timeframe', 'N/A'):>10} | "
                f"{item.get('close', 0):>10.2f} | "
                f"{signal:>18} | "
                f"{item.get('strength', 0):>8.1f} | "
                f"{item.get('weight', 0):>6.2f}"
            )

        logger.info("-" * 65)

        if final:
            direction = final.get('direction', 'NEUTRAL')
            confidence = final.get('confidence', 'LOW')
            strength = final.get('strength', 0)
            agreement = final.get('agreement', 0)
            trigger = final.get('trigger_trade', False)

            # Цветовая индикация
            if direction == 'BULLISH':
                dir_symbol = '🟢'
            elif direction == 'BEARISH':
                dir_symbol = '🔴'
            else:
                dir_symbol = '⚪'

            logger.info(f"{dir_symbol} ФИНАЛЬНЫЙ СИГНАЛ: {direction}")
            logger.info(f"📊 Уверенность: {confidence}")
            logger.info(f"💪 Сила: {strength:.1f}")
            logger.info(f"🤝 Согласие: {agreement:.1f}%")

            # 🔥 ФИКС: Исправленная f-строка
            trade_status = '✅ ДА' if trigger else '❌ НЕТ'
            logger.info(f"🚀 Торговать: {trade_status}")

            logger.info(f"📈 ATR: ${final.get('atr', 0):.2f}")
            logger.info(f"📊 ADX: {final.get('adx', 0):.1f}")
            logger.info("-" * 65)

    def get_trade_signal(self, analysis: Dict) -> Optional[Dict]:
        """
        Получение торгового сигнала для бота.

        Args:
            analysis: результаты анализа

        Returns:
            Optional[Dict]: торговый сигнал или None
        """
        if not analysis:
            return None

        final = analysis.get('final_signal', {})
        if not final:
            return None

        if not final.get('trigger_trade', False):
            return None

        return {
            'symbol': self.symbol,
            'direction': final.get('direction', 'NEUTRAL'),
            'confidence': final.get('confidence', 'LOW'),
            'strength': final.get('strength', 0),
            'atr': final.get('atr', 0),
            'adx': final.get('adx', 0),
            'close': final.get('close', 0),
            'timestamp': datetime.now(),
            'timeframes': analysis.get('timeframes', [])
        }


# Вспомогательные функции
def create_mtf_analyzer(config) -> MultiTimeframeAnalyzer:
    """
    Создание мультитаймфреймового анализатора из конфигурации.

    Args:
        config: объект конфигурации

    Returns:
        MultiTimeframeAnalyzer: экземпляр анализатора
    """
    return MultiTimeframeAnalyzer(
        timeframes=list(getattr(config, 'mtf_timeframes', ['5m', '15m', '30m'])),
        exchange_name=getattr(config, 'exchange_name', 'bybit'),
        symbol=getattr(config, 'symbol', 'BTC/USDT:USDT')
    )


def run_mtf_analysis(config, mtf_analyzer=None) -> Dict:
    """
    Запуск мультитаймфреймового анализа.

    Args:
        config: объект конфигурации
        mtf_analyzer: существующий анализатор (опционально)

    Returns:
        Dict: результаты анализа
    """
    if mtf_analyzer is None:
        mtf_analyzer = create_mtf_analyzer(config)

    try:
        analysis = mtf_analyzer.load_and_analyze(
            limit=getattr(config, 'analysis_limit', 500)
        )

        if not analysis:
            logger.error("❌ Ошибка при выполнении анализа")
            return {}

        # Печать результатов
        mtf_analyzer.print_analysis(analysis)

        return {
            'analysis': analysis,
            'analyzer': mtf_analyzer,
            'trade_signal': mtf_analyzer.get_trade_signal(analysis)
        }

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при анализе: {e}")
        import traceback
        traceback.print_exc()
        return {}
