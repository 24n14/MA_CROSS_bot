"""
Модуль загрузки данных с бирж и торговли.

Содержит класс:
- ExchangeDataLoader: загрузчик OHLCV данных
"""

import pandas as pd
import ccxt
import time
import requests
from typing import Dict, Optional  # Tuple
from datetime import datetime
from log import logger
import config
from DynamicRiskManager import DynamicRiskManager
from open_pos import execute_trade


class ExchangeDataLoader:
    def __init__(self, exchange_name: str = 'bybit', symbol: str = None):
        """
        Инициализация загрузчика данных.

        Args:
            exchange_name: название биржи (bybit, binance и т.д.)
            symbol: торговая пара по умолчанию (опционально)
        """
        self.symbol = symbol  # Сохраняем символ для использования в методах

        # ============= ПРОКСИ =============
        proxies = None
        if config.USE_PROXY:
            proxy_url = f"http://{config.PROXY_USER}:{config.PROXY_PASS}@{config.PROXY_HOST}:{config.PROXY_PORT}"
            proxies = {'http': proxy_url, 'https': proxy_url}

            try:
                test_ip = requests.get('https://api.ipify.org', proxies=proxies, timeout=10).text
                logger.info(f"✅ Внешний IP через прокси: {test_ip}")
            except Exception as e:
                logger.error(f"❌ Не удалось проверить IP через прокси: {e}")
        else:
            logger.info("⏭️ Прокси отключён")

        # ============= БИРЖА =============
        self.exchange = getattr(ccxt, exchange_name)({
            'apiKey': config.API_KEY,
            'secret': config.SECRET_KEY,
            'proxies': proxies,  # Если None — без прокси
            'enableRateLimit': True,
            'options': {
                'enableDemoTrading': config.DEMO_TRADING,
                'defaultType': 'linear',
                'adjustForTimeDifference': True,
                'recvWindow': 10000
            }
        })

        if config.DEMO_TRADING:
            self.exchange.urls['api'] = self.exchange.urls['demotrading']
            result = self.exchange.privateGetV5UserQueryApi()
            uid = result['result']['userID']
            logger.info(f"🧪 ДЕМО-РЕЖИМ АКТИВИРОВАН UID {uid}")
        else:
            result = self.exchange.privateGetV5UserQueryApi()
            uid = result['result']['userID']
            logger.info(f"⚠️ РЕАЛЬНАЯ ТОРГОВЛЯ! UID {uid}")

        balance = self.exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        logger.info(f"✅ АВТОРИЗАЦИЯ УСПЕШНА! 💰 Баланс: {usdt_balance} USDT")


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

    def execute_trade_signal(
            self,
            signal_data: Dict,
            risk_percent: float = 2.0
    ) -> Optional[Dict]:
        """
        Исполнение торгового сигнала с динамическим SL/TP через Pybit V5 API.

        Args:
            signal_data: данные сигнала (должны содержать direction, strength,
                        atr, adx, close и др.)
            risk_percent: процент риска на сделку

        Returns:
            Dict с информацией об ордере или None
        """
        if not signal_data:
            return None

        direction = signal_data.get('direction', 'NEUTRAL')
        if direction == 'NEUTRAL':
            logger.info("⏭️ Нейтральный сигнал - пропускаем")
            return None

        # Проверка силы сигнала (порог из config.AnalysisConfig)
        min_strength = config.AnalysisConfig().min_signal_strength
        strength = signal_data.get('strength', 0)
        if strength < min_strength:
            logger.info(f"⏭️ Слабый сигнал (сила={strength} < {min_strength}) - пропускаем")
            return None

        # Получаем данные для расчета
        atr = signal_data.get('atr', 0)
        adx = signal_data.get('adx', 0)
        close_price = signal_data.get('close', 0)
        trigger_trade = signal_data.get('trigger_trade', False)

        if not trigger_trade:
            logger.info("⏭️ Сигнал не разрешает торговлю - пропускаем")
            return None

        if atr <= 0 or adx <= 0:
            logger.error(f"❌ Некорректные ATR({atr}) или ADX({adx})")
            return None

        # Определяем символ для торговли
        # Используем переданный в signal_data, иначе self.symbol, иначе стандартный
        trade_symbol = signal_data.get('symbol', self.symbol)
        if not trade_symbol:
            logger.error("❌ Не указан символ для торговли")
            return None

        # Создаем менеджер риска
        risk_manager = DynamicRiskManager(self.exchange, trade_symbol)

        # Рассчитываем SL/TP
        side_direction = 'long' if direction == 'BULLISH' else 'short'
        sl_price, tp_price = risk_manager.calculate_sl_tp(
            entry_price=close_price,
            atr=atr,
            adx=adx,
            side=side_direction
        )

        # Рассчитываем размер позиции
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса: {e}")
            usdt_balance = 0

        if usdt_balance <= 0:
            logger.error(f"❌ Недостаточно средств на балансе: ${usdt_balance}")
            return None

        # SL в процентах для расчета размера
        sl_percent = abs(close_price - sl_price) / close_price * 100
        position_size = risk_manager.calculate_position_size(
            account_balance=usdt_balance,
            risk_percent=risk_percent,
            stop_loss_percent=sl_percent,
            entry_price=close_price
        )

        # Логирование параметров
        logger.info(f"\n{'=' * 30}")
        logger.info(f"🔥 ИСПОЛНЕНИЕ СИГНАЛА: {direction}")
        logger.info(f"💰 Баланс: ${usdt_balance:.2f}")
        logger.info(f"💰 Риск: {risk_percent}% = ${usdt_balance * risk_percent / 100:.2f}")
        logger.info(f"📊 Цена входа: ${close_price:.2f}")
        logger.info(f"📊 Размер: {position_size:.4f}")
        logger.info(f"📊 SL: ${sl_price:.2f} | TP: ${tp_price:.2f}")
        logger.info(f"{'=' * 30}")

        # Исполняем ордер через Pybit V5 API (open_pos.py)
        order_result = execute_trade(
            exchange=self.exchange,
            symbol=trade_symbol,
            side=side_direction,
            amount=position_size,
            entry_price=close_price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price
        )

        if not order_result:
            return None

        # Возвращаем результат в формате, совместимом со start.py
        return {
            'order': order_result,
            'stop_loss': sl_price,
            'take_profit': tp_price
        }
