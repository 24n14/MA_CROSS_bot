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

            logger.info(f"Загрузка данных {symbol} ({timeframe}) с {self.exchange.name}...")
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, limit=limit, since=since_ts
            )

            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            logger.info(f"Загружено {len(df)} свечей")
            logger.info(f"Период: с {df.index[0]} по {df.index[-1]}")

            return df

        except Exception as e:
            logger.info(f"Ошибка при загрузке данных: {e}")
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
    