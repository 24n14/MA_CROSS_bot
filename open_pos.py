"""
Модуль для открытия позиций через Bybit V5 API
Использует собственный экземпляр Pybit HTTP клиента с логированием
"""
import time

from typing import Dict, Any, Optional
from pybit.unified_trading import HTTP
from log import logger
import config as cfg
# from api_logger import APILogger  # Используем исправленный логгер


# === Инициализация собственного экземпляра Pybit ===
def create_pybit_session() -> HTTP:
    """
    Создает и возвращает экземпляр Pybit HTTP клиента с логированием

    Returns:
        HTTP: Настроенный клиент Pybit
    """
    # Создаем базовый клиент
    if cfg.DEMO_TRADING:
        client = HTTP(
            demo=True,
            api_key=cfg.API_KEY,
            api_secret=cfg.SECRET_KEY,
            recv_window=5000
        )
        logger.info("🧪 ДЕМО-РЕЖИМ АКТИВИРОВАН (Pybit)")
    else:
        client = HTTP(
            api_key=cfg.API_KEY,
            api_secret=cfg.SECRET_KEY,
            recv_window=5000
        )
        logger.info("🚀 РЕАЛЬНАЯ ТОРГОВЛЯ (Pybit)")

    # Обертываем клиент для логирования
    #logger.info("🔍 Добавление логирования API запросов...")
    #api_logger = APILogger(log_full_response=True, log_params=True)
    #wrapped_client = api_logger.wrap_client(client)
    #logger.info("✅ Логирование API запросов включено")

    #return wrapped_client
    return client

# Создаем глобальный экземпляр для использования во всех функциях
pybit_session = create_pybit_session()


def check_balance(currency: str = 'USDT') -> Optional[float]:
    """
    Проверяет баланс через Pybit API

    Args:
        currency: Валюта для проверки (USDT, USDC)

    Returns:
        float: Свободный баланс или None при ошибке
    """
    try:
        logger.info(f"💰 Проверка баланса {currency} через Pybit API...")

        response = pybit_session.get_wallet_balance(
            accountType="UNIFIED",
            coin=currency
        )

        if response.get("retCode") != 0:
            logger.error(f"❌ Ошибка получения баланса: {response.get('retMsg')}")
            return None

        # Парсим баланс
        result = response.get("result", {})
        list_data = result.get("list", [])

        if not list_data:
            logger.warning(f"⚠️ Нет данных о балансе для {currency}")
            return 0.0

        # Ищем нужную валюту
        for coin_data in list_data:
            coins = coin_data.get("coin", [])
            for coin in coins:
                if coin.get("coin") == currency:
                    free_balance = float(coin.get("walletBalance", 0))
                    logger.info(f"💰 Свободный баланс {currency}: {free_balance:.2f}")
                    return free_balance

        logger.warning(f"⚠️ Валюта {currency} не найдена в балансе")
        return 0.0

    except Exception as e:
        logger.error(f"💥 Ошибка проверки баланса: {e}", exc_info=True)
        return None


def get_instrument_info(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Получает информацию об инструменте

    Args:
        symbol: Торговая пара (BTCUSDT)

    Returns:
        Dict: Информация об инструменте или None при ошибке
    """
    try:
        logger.info(f"📊 Получение информации об инструменте {symbol}...")

        response = pybit_session.get_instruments_info(
            category="linear",
            symbol=symbol
        )

        if response.get("retCode") != 0:
            logger.error(f"❌ Ошибка получения информации: {response.get('retMsg')}")
            return None

        result = response.get("result", {})
        list_data = result.get("list", [])

        if not list_data:
            logger.error(f"❌ Инструмент {symbol} не найден")
            return None

        instrument = list_data[0]
        logger.info(f"✅ Информация получена: {instrument.get('symbol')}")

        return instrument

    except Exception as e:
        logger.error(f"💥 Ошибка получения информации об инструменте: {e}", exc_info=True)
        return None


def place_market_order(symbol: str, side: str, qty: float) -> Optional[Dict[str, Any]]:
    """
    Размещает рыночный ордер

    Args:
        symbol: Торговая пара (BTCUSDT)
        side: Направление (Buy/Sell)
        qty: Количество

    Returns:
        Dict: Информация об ордере или None при ошибке
    """
    try:
        # === ВАЖНО: Получаем информацию об инструменте для корректного qty ===
        instrument = get_instrument_info(symbol)
        if instrument:
            # Лоты (обычно 1 для USDT контрактов)
            lot_size_filter = instrument.get('lotSizeFilter', {})
            qty_step = float(lot_size_filter.get('qtyStep', '0.001'))

            # Округляем до шага лота
            qty = round(qty / qty_step) * qty_step
            qty = round(qty, 6)  # Bybit принимает до 6 знаков
        logger.info(f"📈 Размещение рыночного ордера: {side} {qty} {symbol}")

        response = pybit_session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty)
        )

        if response.get("retCode") != 0:
            logger.error(f"❌ Ошибка размещения ордера: {response.get('retMsg')}")
            return None

        order_data = response.get("result", {})
        order_id = order_data.get("orderId", "unknown")

        logger.info(f"✅ Ордер размещен! ID: {order_id}")
        return order_data

    except Exception as e:
        logger.error(f"💥 Ошибка размещения рыночного ордера: {e}", exc_info=True)
        return None


def set_trading_stop(symbol: str, stop_loss: float, take_profit: float) -> bool:
    """
    Устанавливает TP/SL для позиции

    Args:
        symbol: Торговая пара
        stop_loss: Цена стоп-лосса
        take_profit: Цена тейк-профита

    Returns:
        bool: True если успешно
    """
    try:
        logger.info(f"🔒 Установка TP/SL: SL={stop_loss:.2f}, TP={take_profit:.2f}")

        response = pybit_session.set_trading_stop(
            category="linear",
            symbol=symbol,
            stopLoss=str(stop_loss),
            takeProfit=str(take_profit),
            tpslMode="Full",
            tpOrderType="Market",
            slOrderType="Market"
        )

        if response.get("retCode") != 0:
            logger.error(f"❌ Ошибка установки TP/SL: {response.get('retMsg')}")
            return False

        logger.info(f"✅ TP/SL успешно установлены!")
        return True

    except Exception as e:
        logger.error(f"💥 Ошибка установки TP/SL: {e}", exc_info=True)
        return False


def get_position_info(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о текущей позиции

    Args:
        symbol: Торговая пара

    Returns:
        Dict: Информация о позиции или None
    """
    try:
        response = pybit_session.get_positions(
            category="linear",
            symbol=symbol
        )

        if response.get("retCode") != 0:
            logger.error(f"❌ Ошибка получения позиции: {response.get('retMsg')}")
            return None

        result = response.get("result", {})
        list_data = result.get("list", [])

        if not list_data:
            logger.info("ℹ️ Нет открытых позиций")
            return None

        position = list_data[0]
        size = float(position.get("size", 0))

        if size == 0:
            logger.info("ℹ️ Позиция закрыта (размер 0)")
            return None

        logger.info(f"📊 Позиция найдена: size={size}, side={position.get('side')}")
        return position

    except Exception as e:
        logger.error(f"💥 Ошибка получения позиции: {e}", exc_info=True)
        return None


def execute_trade(exchange, symbol, side, amount, entry_price, stop_loss_price, take_profit_price):
    """
    Открытие позиции с TP/SL через Pybit V5 API.
    Использует собственный экземпляр Pybit для всех операций.

    Args:
        exchange: CCXT exchange instance (используется только для некоторых проверок)
        symbol: Торговая пара (BTC/USDT:USDT)
        side: 'long' или 'short'
        amount: Размер позиции
        entry_price: Цена входа (текущая рыночная)
        stop_loss_price: Цена стоп-лосса
        take_profit_price: Цена тейк-профита

    Returns:
        dict: Информация об открытой позиции или пустой dict при ошибке
    """
    logger.info("🚀 Запуск модуля открытия позиции (Pybit V5)")

    try:
        # === 1. Конвертируем символ из CCXT формата в Bybit формат ===
        bybit_symbol = symbol.replace('/', '').split(':')[0]
        logger.debug(f"Bybit symbol: {bybit_symbol}")

        # === 2. Определяем направление для Bybit ===
        side_bybit = 'Buy' if side == 'long' else 'Sell'

        # === 3. Округляем цены и размер ===
        stop_loss_price = round(stop_loss_price, 2)
        take_profit_price = round(take_profit_price, 2)
        instrument_info = get_instrument_info(bybit_symbol)
        if instrument_info:
            lot_size = instrument_info.get('lotSizeFilter', {})
            qty_step = float(lot_size.get('qtyStep', '0.001'))
            min_qty = float(lot_size.get('minOrderQty', '0.001'))
            max_qty = float(lot_size.get('maxOrderQty', '1000000'))

            # Округляем до шага
            amount = round(amount / qty_step) * qty_step
            amount = max(amount, min_qty)
            amount = min(amount, max_qty)

            logger.debug(f"Скорректированный размер: {amount} (шаг={qty_step}, мин={min_qty})")

        amount = round(amount, 6)

        logger.info(f"📊 Расчетные цены:")
        logger.info(f"   Вход: {entry_price:.2f}")
        logger.info(f"   SL: {stop_loss_price:.2f} | TP: {take_profit_price:.2f}")
        logger.info(f"   Размер: {amount}")

        # === 4. Проверка баланса через Pybit ===
        currency = 'USDC' if 'USDC' in symbol else 'USDT'
        balance = check_balance(currency)

        if balance is None:
            logger.error("❌ Не удалось получить баланс")
            return {}

        if balance < cfg.MIN_AMOUNT:
            logger.warning(f"❌ Недостаточно средств: {balance:.2f} < {cfg.MIN_AMOUNT}")
            return {}

        # === 5. Проверка информации об инструменте ===
        instrument = get_instrument_info(bybit_symbol)
        if not instrument:
            logger.error(f"❌ Инструмент {bybit_symbol} не найден")
            return {}

        # === 6. Проверка минимального размера ===
        try:
            market = exchange.market(symbol)
            min_amount = market['limits']['amount']['min']

            if amount < min_amount:
                logger.error(f"❌ Размер {amount} меньше минимального {min_amount}")
                return {}

            min_cost = entry_price * min_amount
            if amount * entry_price < min_cost:
                logger.error(f"❌ Сумма {amount * entry_price:.2f} < минимум {min_cost}")
                return {}

            logger.info(f"✅ Проверка лимитов пройдена: min_amount={min_amount}")

        except Exception as e:
            logger.warning(f"⚠️ Не удалось проверить лимиты: {e}")

        # === 7. Размещение рыночного ордера ===
        order_data = place_market_order(bybit_symbol, side_bybit, amount)
        if not order_data:
            logger.error("❌ Не удалось разместить рыночный ордер")
            return {}

        order_id = order_data.get("orderId", "unknown")
        logger.info(f"✅ Рыночный ордер размещен! ID: {order_id}")

        # === 8. Ожидание исполнения ордера ===
        logger.info("⏳ Ожидание исполнения ордера (2 секунды)...")
        time.sleep(2)

        # === 9. Установка TP/SL ===
        if not set_trading_stop(bybit_symbol, stop_loss_price, take_profit_price):
            logger.warning("⚠️ TP/SL не установлены, но позиция открыта")

        # === 10. Проверка позиции ===
        position = get_position_info(bybit_symbol)

        if position:
            logger.info(f"✅ Позиция подтверждена!")
            return {
                'id': order_id,
                'symbol': symbol,
                'type': 'market',
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'position_info': position,
                'order_info': order_data
            }
        else:
            logger.warning("⚠️ Позиция не найдена, но ордер был размещен")
            return {
                'id': order_id,
                'symbol': symbol,
                'type': 'market',
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'order_info': order_data
            }

    except Exception as e:
        logger.error(f"💥 Критическая ошибка при открытии позиции: {e}", exc_info=True)
        return {}


# === Функция для экстренного закрытия позиции ===
def emergency_close_position(symbol: str, side: str, qty: float) -> bool:
    """
    Экстренное закрытие позиции по рыночной цене

    Args:
        symbol: Торговая пара
        side: Направление позиции ('long' или 'short')
        qty: Количество для закрытия

    Returns:
        bool: True если успешно
    """
    try:
        bybit_symbol = symbol.replace('/', '').split(':')[0]
        close_side = 'Sell' if side == 'long' else 'Buy'

        logger.critical(f"🚨 ЭКСТРЕННОЕ ЗАКРЫТИЕ: {side} {qty} {bybit_symbol}")

        response = pybit_session.place_order(
            category="linear",
            symbol=bybit_symbol,
            side=close_side,
            orderType="Market",
            qty=str(qty),
            reduceOnly=True
        )

        if response.get("retCode") != 0:
            logger.error(f"❌ Ошибка экстренного закрытия: {response.get('retMsg')}")
            return False

        logger.critical(f"✅ Позиция экстренно закрыта! ID: {response.get('result', {}).get('orderId')}")
        return True

    except Exception as e:
        logger.error(f"💥 Ошибка экстренного закрытия: {e}", exc_info=True)
        return False
