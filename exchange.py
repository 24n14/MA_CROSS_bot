"""
Модуль загрузки данных с бирж.

Содержит класс:
- ExchangeDataLoader: загрузчик OHLCV данных
"""

import pandas as pd
import ccxt
import time
from typing import Dict, Optional
from datetime import datetime
from log import logger


class ExchangeDataLoader:
    """
    Загрузчик данных с бирж через CCXT.

    Поддерживает все биржи доступные в CCXT (Binance, Bybit, Kraken и др.)

    Examples:
        >>> loader = ExchangeDataLoader('binance')
        >>> df = loader.fetch_ohlcv('BTC/USDT', '4h', 500)
    """

    def __init__(self, exchange_name: str = 'binance'):
        """
        Инициализация загрузчика.

        Args:
            exchange_name: название биржи ('binance', 'bybit', 'kraken', и т.д.)
        """
        self.exchange = getattr(ccxt, exchange_name)({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })

    def fetch_ohlcv(self,
                    symbol: str,
                    timeframe: str = '1h',
                    limit: int = 500,
                    since: str = None) -> Optional[pd.DataFrame]:
        """
        Загрузка OHLCV данных с биржи.

        Args:
            symbol: торговая пара ('BTC/USDT', 'ETH/USDT')
            timeframe: таймфрейм ('1m', '5m', '15m', '1h', '4h', '1d')
            limit: количество свечей
            since: начальная дата 'YYYY-MM-DD' или None

        Returns:
            DataFrame с колонками: open, high, low, close, volume
            или None в случае ошибки
        """
        try:
            since_ts = None
            if since:
                since_ts = int(datetime.strptime(since, '%Y-%m-%d').timestamp() * 1000)

            logger.debug(f"Загрузка данных {symbol} ({timeframe}) с {self.exchange.name}...")
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, limit=limit, since=since_ts
            )

            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            logger.debug(f"Загружено {len(df)} свечей")
            logger.debug(f"Период: с {df.index[0]} по {df.index[-1]}")

            return df

        except Exception as e:
            logger.info(f"Ошибка при загрузке данных: {e}")
            return None

    def fetch_new_ohlcv(self,
                        symbol: str,
                        timeframe: str,
                        since_timestamp: pd.Timestamp,
                        limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Загрузка только новых свечей после указанной даты.
        Используется для инкрементального обновления данных.

        Args:
            symbol: торговая пара
            timeframe: таймфрейм
            since_timestamp: загружать свечи НАЧИНАЯ с этой даты (включительно)
            limit: максимум свечей для загрузки

        Returns:
            DataFrame с новыми свечами или None
        """
        try:
            since_ms = int(since_timestamp.timestamp() * 1000)

            ohlcv = self.exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since_ms, limit=limit
            )

            if not ohlcv:
                return None

            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # Исключаем дубликат последней свечи из предыдущей загрузки
            # (биржи часто возвращают последнюю свечу повторно)
            if len(df) > 1:
                df = df.iloc[1:]  # отрезаем первую (уже была в прошлой загрузке)

            if len(df) == 0:
                return None

            logger.debug(f"Загружено {len(df)} новых свечей {symbol} ({timeframe})")
            return df

        except Exception as e:
            logger.info(f"Ошибка при загрузке новых данных: {e}")
            return None

    def load_multiple_timeframes(self,
                                 symbol: str,
                                 timeframes: tuple = ('5m', '15m', '1h'),
                                 limit: int = 500) -> Dict[str, pd.DataFrame]:
        """
        Загрузка данных для нескольких таймфреймов.

        Args:
            symbol: торговая пара
            timeframes: кортеж таймфреймов
            limit: количество свечей для каждого таймфрейма

        Returns:
            Словарь {timeframe: DataFrame}
        """
        data = {}
        for tf in timeframes:
            df = self.fetch_ohlcv(symbol, tf, limit)
            if df is not None:
                data[tf] = df
            time.sleep(1)
        return data

    def load_multiple_timeframes_incremental(self,
                                             symbol: str,
                                             timeframes: tuple,
                                             cached_data: Dict[str, pd.DataFrame],
                                             limit: int = 500) -> Dict[str, pd.DataFrame]:
        """
        Инкрементальная загрузка данных для нескольких таймфреймов.
        Если данные уже есть в кеше — догружает только новые свечи.

        Args:
            symbol: торговая пара
            timeframes: кортеж таймфреймов
            cached_data: словарь с ранее загруженными данными {timeframe: DataFrame}
            limit: максимальное количество свечей для хранения

        Returns:
            Обновлённый словарь {timeframe: DataFrame}
        """
        data = cached_data.copy() if cached_data else {}

        for tf in timeframes:
            if tf in data and data[tf] is not None and len(data[tf]) > 0:
                # Инкрементальная загрузка — только новые свечи
                last_timestamp = data[tf].index[-1]
                new_df = self.fetch_new_ohlcv(symbol, tf, last_timestamp, limit=limit)

                if new_df is not None and len(new_df) > 0:
                    # Добавляем новые свечи и обрезаем до limit
                    combined = pd.concat([data[tf], new_df])
                    # Удаляем возможные дубликаты по индексу
                    combined = combined[~combined.index.duplicated(keep='first')]
                    # Оставляем только последние limit свечей
                    data[tf] = combined.iloc[-limit:]
                    logger.debug(f"📈 {tf}: было {len(data[tf]) - len(new_df)} свечей, "
                                 f"добавлено {len(new_df)}, всего {len(data[tf])}")
                else:
                    logger.info(f"⏸️ {tf}: новых свечей нет")
            else:
                # Первичная загрузка — все 300 свечей
                logger.debug(f"🆕 {tf}: первичная загрузка {limit} свечей")
                df = self.fetch_ohlcv(symbol, tf, limit)
                if df is not None:
                    data[tf] = df

            time.sleep(1)

        return data
