"""
Модуль управления рисками и исполнения ордеров с динамическим ATR/ADX позиционированием.
Содержит класс:
- DynamicRiskManager: расчет и исполнение ордеров с адаптивными множителями
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
import ccxt
from log import logger
import config as cfg
import time


class DynamicRiskManager:
    """
    Менеджер риска с динамическим расчетом стоп-лосса и тейк-профита
    на основе ATR и ADX.

    Логика множителей:
    - Слабый тренд (ADX < 25): SL = ATR * 1.5, TP = ATR * 1.5
    - Умеренный тренд (ADX 25-35): SL = ATR * 1.5, TP = ATR * 2.0
    - Сильный тренд (ADX > 35): SL = ATR * 1.5, TP = ATR * 3.0
    - Высокая волатильность (ATR > 400): SL = ATR * 2.0 (защита от шпилек)
    """

    # Базовые множители
    BASE_SL_MULTIPLIER = 1.5
    BASE_TP_MULTIPLIER = 1.5

    # Пороги ADX
    ADX_MODERATE = 25  # Начало умеренного тренда
    ADX_STRONG = 35    # Начало сильного тренда

    # Множители для TP при различных состояниях ADX
    TP_MULTIPLIERS = {
        'weak': 1.5,      # ADX < 25
        'moderate': 2.0,  # ADX 25-35
        'strong': 3.0     # ADX > 35
    }

    # Порог высокой волатильности для увеличения SL
    HIGH_VOLATILITY_ATR = 400.0  # USD
    HIGH_VOL_SL_MULTIPLIER = 2.0

    def __init__(self, exchange: ccxt.Exchange, symbol: str):
        """
        Инициализация менеджера риска.

        Args:
            exchange: экземпляр биржи CCXT
            symbol: торговая пара (например 'BTC/USDT:USDT')
        """
        self.exchange = exchange
        self.symbol = symbol
        self.market = exchange.market(symbol)

        # Параметры позиции
        self.position_size = None
        self.entry_price = None
        self.side = None  # 'long' или 'short'

    def calculate_sl_tp(
        self,
        entry_price: float,
        atr: float,
        adx: float,
        side: str,
        atr_multiplier: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Расчет стоп-лосса и тейк-профита с динамическими множителями.

        Args:
            entry_price: цена входа
            atr: значение ATR
            adx: значение ADX
            side: направление ('long' или 'short')
            atr_multiplier: переопределение множителя для стопа (если None - рассчитывается)
            risk_reward_ratio: переопределение RR (если None - рассчитывается)

        Returns:
            Tuple[float, float]: (stop_loss_price, take_profit_price)
        """
        if atr <= 0:
            logger.error(f"❌ ATR = {atr}, невозможно рассчитать SL/TP")
            return entry_price, entry_price

        # --- Расчет множителя стоп-лосса ---
        sl_multiplier = self.BASE_SL_MULTIPLIER

        # Если ATR очень высокий - увеличиваем стоп для защиты от шумов
        if atr >= self.HIGH_VOLATILITY_ATR:
            sl_multiplier = self.HIGH_VOL_SL_MULTIPLIER
            logger.debug(f"🔴 Высокая волатильность (ATR={atr:.2f}): SL множитель увеличен до {sl_multiplier}")

        # Если передан кастомный множитель - используем его (приоритет)
        if atr_multiplier is not None:
            sl_multiplier = atr_multiplier

        # --- Расчет множителя тейк-профита ---
        if adx < self.ADX_MODERATE:
            tp_multiplier = self.TP_MULTIPLIERS['weak']
            trend_state = 'слабый'
        elif adx < self.ADX_STRONG:
            tp_multiplier = self.TP_MULTIPLIERS['moderate']
            trend_state = 'умеренный'
        else:
            tp_multiplier = self.TP_MULTIPLIERS['strong']
            trend_state = 'сильный'

        # Если передан кастомный RR - используем его для расчета TP
        if risk_reward_ratio is not None:
            tp_multiplier = sl_multiplier * risk_reward_ratio
            logger.debug(f"📐 Использую кастомный RR={risk_reward_ratio}: TP множитель={tp_multiplier:.2f}")

        # --- Расчет дистанций ---
        sl_distance = atr * sl_multiplier
        tp_distance = atr * tp_multiplier

        # --- Расчет цен ---
        if side == 'long':
            stop_loss_price = entry_price - sl_distance
            take_profit_price = entry_price + tp_distance
        else:  # short
            stop_loss_price = entry_price + sl_distance
            take_profit_price = entry_price - tp_distance

        # Логирование
        logger.info(f"\n{'=' * 30}")
        logger.info(f"📊 ДИНАМИЧЕСКИЙ РАСЧЕТ SL/TP")
        logger.info(f"ATR: ${atr:.2f} | ADX: {adx:.1f} ({trend_state})")
        logger.info(f"SL множитель: {sl_multiplier}x (дист. ${sl_distance:.2f})")
        logger.info(f"TP множитель: {tp_multiplier}x (дист. ${tp_distance:.2f})")
        logger.info(f"RR: 1:{tp_multiplier / sl_multiplier:.2f}")
        logger.info(f"{'=' * 30}")

        return stop_loss_price, take_profit_price

    def calculate_position_size(
        self,
        account_balance: float,
        risk_percent: float = 2.0,
        stop_loss_percent: Optional[float] = None
    ) -> float:
        """
        Расчет размера позиции на основе риска.

        Args:
            account_balance: баланс счета в USD
            risk_percent: процент риска на сделку (по умолчанию 2%)
            stop_loss_percent: процент стоп-лосса для расчета размера

        Returns:
            float: размер позиции в контрактах/монетах
        """
        max_risk_amount = account_balance * (risk_percent / 100)

        if stop_loss_percent and stop_loss_percent > 0:
            position_size = max_risk_amount / (stop_loss_percent / 100)
        else:
            position_size = max_risk_amount

        # Для фьючерсов конвертируем в контракты
        if self.market.get('linear', False) or self.market.get('inverse', False):
            # Для линейных контрактов размер = сумма / цена
            position_size = position_size  # В USDT для USDT-M фьючерсов

        logger.debug(f"💰 Размер позиции: {position_size:.4f} (риск {risk_percent}% = ${max_risk_amount:.2f})")
        return position_size

    def place_limit_order(
        self,
        side: str,
        amount: float,
        price: float,
        stop_loss_price: float,
        take_profit_price: float,
        reduce_only: bool = False,
        time_in_force: str = 'GTC'
    ) -> Dict:
        """
        Размещение лимитного ордера с прикрепленными SL/TP.

        Args:
            side: 'buy' или 'sell'
            amount: количество в контрактах
            price: цена лимитного ордера
            stop_loss_price: цена стоп-лосса
            take_profit_price: цена тейк-профита
            reduce_only: только уменьшение позиции (для SL/TP)
            time_in_force: время жизни ордера

        Returns:
            Dict: информация об ордере
        """
        try:
            # Округляем цены и количество до допустимых значений
            amount = self._adjust_amount(amount)
            price = self._adjust_price(price)
            stop_loss_price = self._adjust_price(stop_loss_price)
            take_profit_price = self._adjust_price(take_profit_price)

            # Параметры ордера
            order_params = {
                'timeInForce': time_in_force,
                'reduceOnly': reduce_only,
            }

            # Размещаем лимитный ордер
            logger.info(f"📝 Размещение лимитного ордера: {side} {amount} @ ${price:.2f}")
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side=side,
                amount=amount,
                price=price,
                params=order_params
            )

            logger.info(f"✅ Ордер размещен: ID {order['id']}")

            # Размещаем стоп-лосс и тейк-профит как отдельные ордера
            time.sleep(0.5)  # Небольшая задержка между ордерами

            if self.market.get('linear', False):
                # Для Bybit фьючерсов используем параметры TP/SL
                self._place_bybit_tp_sl(
                    order_id=order['id'],
                    position_idx=0,  # Обе стороны
                    stop_loss=stop_loss_price,
                    take_profit=take_profit_price,
                    amount=amount
                )
            else:
                # Для других бирж размещаем отдельные ордера
                self._place_oco_orders(
                    main_order_id=order['id'],
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    stop_loss=stop_loss_price,
                    take_profit=take_profit_price
                )

            return {
                'order': order,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при размещении ордера: {e}")
            return {}

    def _place_bybit_tp_sl(
        self,
        order_id: str,
        position_idx: int,
        stop_loss: float,
        take_profit: float,
        amount: float
    ):
        """
        Размещение TP/SL для Bybit фьючерсов.
        """
        try:
            # Устанавливаем TP/SL через позицию
            tp_sl_params = {
                'symbol': self.symbol,
                'orderId': order_id,
                'positionIdx': position_idx,
                'stopLoss': str(stop_loss),
                'takeProfit': str(take_profit),
                'tpTriggerBy': 'LastPrice',
                'slTriggerBy': 'LastPrice'
            }

            self.exchange.private_post_v5_position_set_trading_stop(tp_sl_params)
            logger.info(f"🛑 SL установлен: ${stop_loss:.2f}")
            logger.info(f"🎯 TP установлен: ${take_profit:.2f}")

        except Exception as e:
            logger.error(f"❌ Ошибка установки TP/SL на Bybit: {e}")

    def _place_oco_orders(
        self,
        main_order_id: str,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float
    ):
        """
        Размещение OCO ордеров (Stop Loss + Limit) для обычных бирж.
        """
        try:
            # Stop Loss ордер
            sl_order = self.exchange.create_order(
                symbol=self.symbol,
                type='stop',
                side=side,
                amount=amount,
                price=stop_loss,
                params={
                    'stopPrice': stop_loss,
                    'reduceOnly': True
                }
            )
            logger.info(f"🛑 Stop Loss ордер: ID {sl_order['id']}")

            # Take Profit ордер (лимитный)
            tp_order = self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side=side,
                amount=amount,
                price=take_profit,
                params={
                    'reduceOnly': True
                }
            )
            logger.info(f"🎯 Take Profit ордер: ID {tp_order['id']}")

        except Exception as e:
            logger.error(f"❌ Ошибка размещения OCO: {e}")

    def _adjust_amount(self, amount: float) -> float:
        """
        Округление количества до допустимого шага.
        """
        amount_step = self.market.get('precision', {}).get('amount', 0.001)
        precision = int(abs(np.log10(amount_step)))
        return float(Decimal(str(amount)).quantize(Decimal(f"0.{'0'*precision}"), rounding=ROUND_DOWN))

    def _adjust_price(self, price: float) -> float:
        """
        Округление цены до допустимого шага.
        """
        price_step = self.market.get('precision', {}).get('price', 0.01)
        precision = int(abs(np.log10(price_step)))
        return round(price, precision)

    def get_dynamic_multipliers(self, atr: float, adx: float) -> Dict:
        """
        Получение динамических множителей для визуализации/логирования.

        Args:
            atr: значение ATR
            adx: значение ADX

        Returns:
            Dict: множители и состояния
        """
        sl_mult = self.BASE_SL_MULTIPLIER
        if atr >= self.HIGH_VOLATILITY_ATR:
            sl_mult = self.HIGH_VOL_SL_MULTIPLIER

        if adx < self.ADX_MODERATE:
            tp_mult = self.TP_MULTIPLIERS['weak']
            trend = 'слабый'
        elif adx < self.ADX_STRONG:
            tp_mult = self.TP_MULTIPLIERS['moderate']
            trend = 'умеренный'
        else:
            tp_mult = self.TP_MULTIPLIERS['strong']
            trend = 'сильный'

        return {
            'trend_state': trend,
            'sl_multiplier': sl_mult,
            'tp_multiplier': tp_mult,
            'rr_ratio': round(tp_mult / sl_mult, 2),
            'sl_distance': round(atr * sl_mult, 2),
            'tp_distance': round(atr * tp_mult, 2)
        }
