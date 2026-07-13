import time
from pybit.unified_trading import HTTP
from log import logger
import config as cfg


# === Инициализация Pybit ===
if cfg.DEMO_TRADING:
    session_bybit = HTTP(
        demo=True,
        api_key=cfg.API_KEY,
        api_secret=cfg.SECRET_KEY
    )
    logger.info("🧪 ДЕМО-РЕЖИМ АКТИВИРОВАН (Pybit)")
else:
    session_bybit = HTTP(
        api_key=cfg.API_KEY,
        api_secret=cfg.SECRET_KEY
    )
    logger.info("🚀 РЕАЛЬНАЯ ТОРГОВЛЯ (Pybit)")


def execute_trade(exchange, symbol, side, amount, entry_price, stop_loss_price, take_profit_price):
    """
    Открытие позиции с TP/SL через Pybit V5 API.
    
    Args:
        exchange: CCXT exchange instance (для проверки статуса)
        symbol: Торговая пара (BTC/USDT:USDT)
        side: 'long' или 'short'
        amount: Размер позиции
        entry_price: Цена входа (текущая рыночная)
        stop_loss_price: Цена стоп-лосса
        take_profit_price: Цена тейк-профита
    
    Returns:
        dict: Информация об открытой позиции или пустой dict при ошибке
    """
    logger.info("🚀 Запуск модуля открытия позиции")

    try:
        # === 1. Конвертируем символ из CCXT формата в Bybit формат ===
        # BTC/USDT:USDT -> BTCUSDT
        bybit_symbol = symbol.replace('/', '').split(':')[0]
        logger.debug(f"Bybit symbol: {bybit_symbol}")

        # === 2. Определяем направление для Bybit ===
        side_bybit = 'Buy' if side == 'long' else 'Sell'

        # === 3. Округляем цены и размер ===
        stop_loss_price = round(stop_loss_price, 2)
        take_profit_price = round(take_profit_price, 2)
        amount = round(amount, 6)

        logger.info(f"📊 Расчетные цены:")
        logger.info(f"   Вход: {entry_price:.2f}")
        logger.info(f"   SL: {stop_loss_price:.2f} | TP: {take_profit_price:.2f}")
        logger.info(f"   Размер: {amount}")

        # === 4. Открытие позиции через Pybit (V5 API) ===
        order = session_bybit.place_order(
            category="linear",
            symbol=bybit_symbol,
            side=side_bybit,
            orderType="Market",
            qty=str(amount),
            stopLoss=str(stop_loss_price),
            takeProfit=str(take_profit_price),
            tpslMode="Partial",
            tpOrderType="Market",
            slOrderType="Market"
        )

        if order.get("retCode") != 0:
            error_msg = order.get('retMsg', 'Unknown error')
            logger.error(f"❌ Ошибка при размещении ордера: {error_msg}")
            return {}

        order_id = order.get('result', {}).get('orderId', 'unknown')
        logger.info(f"✅ Позиция открыта! ID: {order_id}")
        logger.info(f"📈 {side_bybit} {amount} {bybit_symbol} @ {entry_price:.2f}")

        # === 5. Ждем немного, чтобы позиция успела открыться ===
        time.sleep(1)

        # === 6. Проверяем успешность открытия позиции ===
        try:
            positions = exchange.fetch_positions([symbol])
            for pos in positions:
                if pos['symbol'] == symbol:
                    size = float(pos.get('contracts', 0) or pos.get('size', 0))
                    if size > 0:
                        logger.info(f"✅ Позиция подтверждена: {size} контрактов {side}")
                        # Возвращаем объект похожий на CCXT order для совместимости
                        return {
                            'id': order_id,
                            'symbol': symbol,
                            'type': 'market',
                            'side': side,
                            'amount': amount,
                            'entry_price': entry_price,
                            'stop_loss': stop_loss_price,
                            'take_profit': take_profit_price,
                            'info': order
                        }
        except Exception as check_error:
            logger.warning(f"⚠️ Не удалось проверить позицию: {check_error}")
            # Но ордер был размещен успешно, возвращаем информацию
            return {
                'id': order_id,
                'symbol': symbol,
                'type': 'market',
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'info': order
            }

        logger.warning(f"⚠️ Позиция не найдена после размещения ордера (но ордер был размещен)")
        return {}

    except Exception as e:
        logger.error(f"💥 Ошибка при открытии позиции: {e}", exc_info=True)
        return {}
