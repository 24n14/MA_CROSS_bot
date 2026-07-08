"""
Модуль управления рисками и исполнения ордеров с динамическим ATR/ADX позиционированием.
"""
import time
import numpy as np
from typing import Dict, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
import ccxt
from log import logger
import config as cfg


class DynamicRiskManager:
    """
    Менеджер риска с динамическим расчетом стоп-лосса и тейк-профита на основе ATR и ADX.
    """

    def __init__(self, exchange: ccxt.Exchange, symbol: str):
        self.exchange = exchange
        self.symbol = symbol
        # Безопасная загрузка рынков, если они еще не загружены
        if not exchange.markets:
            exchange.load_markets()
        self.market = exchange.market(symbol)
        self.risk_cfg = cfg.RiskConfig()

        self.position_size = None
        self.entry_price = None
        self.side = None

    def calculate_sl_tp(
            self,
            entry_price: float,
            atr: float,
            adx: float,
            side: str,
            atr_multiplier: Optional[float] = None,
            risk_reward_ratio: Optional[float] = None
    ) -> Tuple[float, float]:
        if atr <= 0:
            logger.error(f"❌ ATR = {atr}, невозможно рассчитать SL/TP")
            return entry_price, entry_price

        rc = self.risk_cfg
        sl_multiplier = rc.base_sl_multiplier

        if atr >= rc.high_volatility_atr:
            sl_multiplier = rc.high_vol_sl_multiplier
            logger.debug(f"🔥 Высокая волатильность (ATR={atr:.2f}): SL множитель увеличен до {sl_multiplier}")

        if atr_multiplier is not None:
            sl_multiplier = atr_multiplier

        if adx < rc.adx_moderate_threshold:
            tp_multiplier = rc.tp_multiplier_weak
            trend_state = 'слабый'
        elif adx < rc.adx_strong_threshold:
            tp_multiplier = rc.tp_multiplier_moderate
            trend_state = 'умеренный'
        else:
            tp_multiplier = rc.tp_multiplier_strong
            trend_state = 'сильный'

        if risk_reward_ratio is not None:
            tp_multiplier = sl_multiplier * risk_reward_ratio
            logger.debug(f"📐 Кастомный RR={risk_reward_ratio}: TP множитель={tp_multiplier:.2f}")

        sl_distance = atr * sl_multiplier
        tp_distance = atr * tp_multiplier

        if side == 'long':
            stop_loss_price = entry_price - sl_distance
            take_profit_price = entry_price + tp_distance
        else:
            stop_loss_price = entry_price + sl_distance
            take_profit_price = entry_price - tp_distance

        logger.info(f"\n{'=' * 30}\n📐 ДИНАМИЧЕСКИЙ РАСЧЕТ SL/TP")
        logger.info(f"ATR: ${atr:.2f} | ADX: {adx:.1f} ({trend_state})")
        logger.info(f"SL множитель: {sl_multiplier}x (дист. ${sl_distance:.2f})")
        logger.info(f"TP множитель: {tp_multiplier}x (дист. ${tp_distance:.2f})")
        logger.info(f"RR: 1:{tp_multiplier / sl_multiplier:.2f}\n{'=' * 30}")

        return stop_loss_price, take_profit_price

    def calculate_position_size(
            self,
            account_balance: float,
            risk_percent: float = 2.0,
            stop_loss_percent: Optional[float] = None,
            entry_price: Optional[float] = None
    ) -> float:
        max_risk_amount = account_balance * (risk_percent / 100)
        if stop_loss_percent and stop_loss_percent > 0:
            position_size = max_risk_amount / (stop_loss_percent / 100)
        else:
            position_size = max_risk_amount

        if self.market.get('linear', False) and entry_price and entry_price > 0:
            position_size = position_size / entry_price
            logger.debug(f"💱 Конвертация USDT -> базовая валюта: {position_size:.6f} (по цене ${entry_price:.2f})")

        logger.debug(f"💰 Размер позиции: {position_size:.6f} (риск {risk_percent}% = ${max_risk_amount:.2f})")
        return position_size

    def place_limit_order(
            self, side: str, amount: float, price: float, stop_loss_price: float,
            take_profit_price: float, reduce_only: bool = False, time_in_force: str = 'GTC'
    ) -> Dict:
        try:
            amount = self._adjust_amount(amount)
            price = self._adjust_price(price)
            stop_loss_price = self._adjust_price(stop_loss_price)
            take_profit_price = self._adjust_price(take_profit_price)

            order_params = {'timeInForce': time_in_force, 'reduceOnly': reduce_only}

            if self.market.get('linear', False):
                order_params['stopLossPrice'] = stop_loss_price
                order_params['takeProfitPrice'] = take_profit_price
                logger.info(f"🛑 SL в ордере: ${stop_loss_price:.2f} | TP в ордере: ${take_profit_price:.2f}")

            logger.info(f"🚀 Размещение лимитного ордера: {side} {amount} @ ${price:.2f}")
            order = self.exchange.create_order(
                symbol=self.symbol, type='limit', side=side, amount=amount, price=price, params=order_params
            )
            logger.info(f"✅ Ордер размещен: ID {order['id']}")

            if not self.market.get('linear', False):
                time.sleep(0.5)
                self._place_oco_orders(
                    main_order_id=order['id'], side='sell' if side == 'buy' else 'buy',
                    amount=amount, stop_loss=stop_loss_price, take_profit=take_profit_price
                )
            return {'order': order, 'stop_loss': stop_loss_price, 'take_profit': take_profit_price}
        except Exception as e:
            logger.error(f"❌ Ошибка при размещении ордера: {e}")
            return {}

    def _place_oco_orders(self, main_order_id: str, side: str, amount: float, stop_loss: float, take_profit: float):
        try:
            sl_order = self.exchange.create_order(
                symbol=self.symbol, type='stop', side=side, amount=amount, price=stop_loss,
                params={'stopPrice': stop_loss, 'reduceOnly': True}
            )
            logger.info(f"🛑 Stop Loss ордер размещен: ID {sl_order['id']}")

            tp_order = self.exchange.create_order(
                symbol=self.symbol, type='limit', side=side, amount=amount, price=take_profit,
                params={'reduceOnly': True}
            )
            logger.info(f"🎯 Take Profit ордер размещен: ID {tp_order['id']}")
        except Exception as e:
            logger.error(f"❌ Ошибка размещения OCO ордеров: {e}")

    def _adjust_amount(self, amount: float) -> float:
        amount_step = self.market.get('precision', {}).get('amount', 0.001)
        precision = int(abs(np.log10(amount_step)))
        return float(Decimal(str(amount)).quantize(Decimal(f"0.{'0' * precision}"), rounding=ROUND_DOWN))

    def _adjust_price(self, price: float) -> float:
        price_step = self.market.get('precision', {}).get('price', 0.01)
        precision = int(abs(np.log10(price_step)))
        return round(price, precision)

    def get_dynamic_multipliers(self, atr: float, adx: float) -> Dict:
        rc = self.risk_cfg
        sl_mult = rc.base_sl_multiplier
        if atr >= rc.high_volatility_atr:
            sl_mult = rc.high_vol_sl_multiplier
        if adx < rc.adx_moderate_threshold:
            tp_mult = rc.tp_multiplier_weak
            trend = 'слабый'
        elif adx < rc.adx_strong_threshold:
            tp_mult = rc.tp_multiplier_moderate
            trend = 'умеренный'
        else:
            tp_mult = rc.tp_multiplier_strong
            trend = 'сильный'
        return {
            'trend_state': trend, 'sl_multiplier': sl_mult, 'tp_multiplier': tp_mult,
            'rr_ratio': round(tp_mult / sl_mult, 2), 'sl_distance': round(atr * sl_mult, 2),
            'tp_distance': round(atr * tp_mult, 2)
        }


class PositionMonitor:
    """
    Мониторинг и динамическое обновление SL/TP открытой позиции на бирже.
    """

    def __init__(
            self, exchange: ccxt.Exchange, symbol: str, side: str, entry_price: float,
            initial_sl: float, initial_tp: float, atr: float, position_size: float,
            breakeven_activation_atr: Optional[float] = None,
            trail_sl_multiplier: Optional[float] = None,
            trail_tp_multiplier: Optional[float] = None,
            min_update_distance_atr: Optional[float] = None,
            min_atr_change_pct: Optional[float] = None
    ):
        rc = cfg.RiskConfig()
        self.exchange = exchange
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.current_sl = initial_sl
        self.current_tp = initial_tp
        self.atr = atr
        self.position_size = position_size

        self.breakeven_activation_atr = breakeven_activation_atr or rc.breakeven_activation_atr
        self.trail_sl_multiplier = trail_sl_multiplier or rc.trail_sl_multiplier
        self.trail_tp_multiplier = trail_tp_multiplier or rc.trail_tp_multiplier
        self.min_update_distance_atr = min_update_distance_atr or rc.min_update_distance_atr
        self.min_atr_change_pct = min_atr_change_pct or rc.min_atr_change_pct

        self.breakeven_activated = False
        self.best_price = entry_price
        self.breakeven_threshold = atr * self.breakeven_activation_atr

        self._last_exchange_sl = initial_sl
        self._last_exchange_tp = initial_tp
        self._last_exchange_atr = atr

        logger.info(f"\n{'=' * 30}\n📊 PositionMonitor создан")
        logger.info(f"{side.upper()} @ ${entry_price:.2f} | Лот: {position_size}")
        logger.info(f"SL=${initial_sl:.2f} | TP=${initial_tp:.2f} | ATR=${atr:.2f}")
        logger.info(f"{'=' * 30}")

    def _should_update_exchange(self, new_sl: float, new_tp: float) -> bool:
        if self.breakeven_activated and self._last_exchange_sl == self.entry_price:
            return True
        sl_significant = abs(new_sl - self._last_exchange_sl) >= self.atr * self.min_update_distance_atr
        tp_significant = abs(new_tp - self._last_exchange_tp) >= self.atr * self.min_update_distance_atr
        return sl_significant or tp_significant

    def _should_update_atr(self, new_atr: float) -> bool:
        if self._last_exchange_atr <= 0:
            return True
        return (abs(new_atr - self._last_exchange_atr) / self._last_exchange_atr * 100) >= self.min_atr_change_pct

    def update(self, current_price: float, new_atr: Optional[float] = None) -> Dict:
        updates = {'exchange_updated': False, 'error': False}
        atr_changed = False

        if new_atr is not None and new_atr > 0 and self._should_update_atr(new_atr):
            old_atr = self.atr
            self.atr = new_atr
            self.breakeven_threshold = self.atr * self.breakeven_activation_atr
            atr_changed = True
            logger.info(f"🔄 ATR обновлён: ${old_atr:.2f} -> ${new_atr:.2f}")

        if self.side == 'long':
            profit = current_price - self.entry_price
            is_profitable = profit > 0
            if current_price > self.best_price:
                self.best_price = current_price
        else:
            profit = self.entry_price - current_price
            is_profitable = profit > 0
            if current_price < self.best_price:
                self.best_price = current_price

        # 1. Безубыток
        if not self.breakeven_activated and is_profitable and profit >= self.breakeven_threshold:
            self.current_sl = self.entry_price
            self.breakeven_activated = True
            updates['breakeven'] = {'activated': True, 'sl': self.entry_price}
            logger.info(f"🛡️ BREAKEVEN АКТИВИРОВАН! SL -> ${self.entry_price:.2f}")

        # 2. Трейлинг стопа
        if self.breakeven_activated:
            new_sl = self._calculate_trailing_sl()
            if abs(new_sl - self.current_sl) > 0.01:
                old_sl = self.current_sl
                self.current_sl = new_sl
                updates['trailing_sl'] = {'from': round(old_sl, 2), 'to': round(new_sl, 2)}
                logger.info(f"📈 Трейлинг SL: ${old_sl:.2f} -> ${new_sl:.2f}")

        # 3. Трейлинг тейка
        if self.trail_tp_multiplier is not None and self.breakeven_activated:
            new_tp = self._calculate_trailing_tp()
            if abs(new_tp - self.current_tp) > 0.01:
                old_tp = self.current_tp
                self.current_tp = new_tp
                updates['trailing_tp'] = {'from': round(old_tp, 2), 'to': round(new_tp, 2)}
                logger.info(f"🎯 Трейлинг TP: ${old_tp:.2f} -> ${new_tp:.2f}")

        # 4. Отправка изменений на биржу
        if updates.get('breakeven') or updates.get('trailing_sl') or updates.get('trailing_tp') or atr_changed:
            if self._should_update_exchange(self.current_sl, self.current_tp):
                success = self._update_on_exchange(self.current_sl, self.current_tp)
                if success:
                    self._last_exchange_sl = self.current_sl
                    self._last_exchange_tp = self.current_tp
                    self._last_exchange_atr = self.atr
                    updates['exchange_updated'] = True
                else:
                    updates['exchange_updated'] = False
                    updates['error'] = True
            else:
                logger.debug("ℹ️ Изменения незначительны — обновление пропущено.")

        return updates

    def _calculate_trailing_sl(self) -> float:
        trail_distance = self.atr * self.trail_sl_multiplier
        if self.side == 'long':
            new_sl = self.best_price - trail_distance
            return max(new_sl, self.current_sl, self.entry_price)
        else:
            new_sl = self.best_price + trail_distance
            return min(new_sl, self.current_sl, self.entry_price)

    def _calculate_trailing_tp(self) -> float:
        trail_distance = self.atr * self.trail_tp_multiplier
        if self.side == 'long':
            new_tp = self.best_price + trail_distance
            return max(new_tp, self.current_tp)
        else:
            new_tp = self.best_price - trail_distance
            return min(new_tp, self.current_tp)

    def _update_on_exchange(self, sl_price: float, tp_price: float) -> bool:
        """Обновить SL/TP на бирже через CCXT. Возвращает True в случае успеха."""
        # Округление перед отправкой
        price_step = self.exchange.market(self.symbol).get('precision', {}).get('price', 0.01)
        precision = int(abs(np.log10(price_step)))
        sl_price = round(sl_price, precision)
        tp_price = round(tp_price, precision)

        side = 'sell' if self.side == 'long' else 'buy'

        try:
            # Метод 1: Попытка обновить через стандартный ордер с нулевым объемом (фирменный метод Bybit в CCXT)
            self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=0,
                params={
                    'stopLossPrice': sl_price,
                    'takeProfitPrice': tp_price,
                    'positionIdx': 0,
                    'reduceOnly': True
                }
            )
            logger.info(f"✅ SL/TP обновлены (create_order): SL=${sl_price:.2f}, TP=${tp_price:.2f}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Стандартный метод изменения SL/TP не сработал: {e}. Применяем Fallback...")

            # Метод 2: Исправленный прямой вызов V5 API с обязательным snake_case синтаксисом и category='linear'
            try:
                market_id = self.exchange.market(self.symbol)['id']
                params = {
                    'category': 'linear',
                    'symbol': market_id,
                    'stopLoss': str(sl_price),
                    'takeProfit': str(tp_price),
                    'tpTriggerBy': 'LastPrice',
                    'slTriggerBy': 'LastPrice',
                    'positionIdx': 0
                }
                self.exchange.private_post_v5_position_set_trading_stop(params)
                logger.info(f"✅ SL/TP успешно обновлены через V5 API: SL=${sl_price:.2f}, TP=${tp_price:.2f}")
                return True
            except Exception as e2:
                logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА API BYBIT: Не удалось установить стопы: {e2}")
                return False

    def is_position_open(self) -> bool:
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for pos in positions:
                if pos['symbol'] == self.symbol:
                    size = float(pos.get('contracts', 0) or pos.get('size', 0))
                    if size > 0:
                        return True
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки открытой позиции: {e}")
            return False

    def get_status(self) -> Dict:
        return {
            'side': self.side,
            'entry_price': self.entry_price,
            'current_sl': self.current_sl,
            'current_tp': self.current_tp,
            'atr': self.atr,
            'best_price': self.best_price,
            'breakeven_activated': self.breakeven_activated,
            'breakeven_threshold': self.breakeven_threshold
        }