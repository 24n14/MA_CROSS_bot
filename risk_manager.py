"""
Модуль управления рисками и исполнения ордеров с динамическим ATR/ADX позиционированием.
Содержит классы:
- DynamicRiskManager: расчет и исполнение ордеров с адаптивными множителями
- PositionMonitor: мониторинг и динамическое обновление SL/TP открытой позиции
"""
#  import pandas as pd
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

    Все множители и пороги берутся из config.RiskConfig.
    """

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

        # Загружаем конфигурацию риск-менеджмента
        self.risk_cfg = cfg.RiskConfig()

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

        rc = self.risk_cfg

        # --- Расчет множителя стоп-лосса ---
        sl_multiplier = rc.base_sl_multiplier

        # Если ATR очень высокий - увеличиваем стоп для защиты от шумов
        if atr >= rc.high_volatility_atr:
            sl_multiplier = rc.high_vol_sl_multiplier
            logger.debug(f"🔴 Высокая волатильность (ATR={atr:.2f}): SL множитель увеличен до {sl_multiplier}")

        # Если передан кастомный множитель - используем его (приоритет)
        if atr_multiplier is not None:
            sl_multiplier = atr_multiplier

        # --- Расчет множителя тейк-профита ---
        if adx < rc.adx_moderate_threshold:
            tp_multiplier = rc.tp_multiplier_weak
            trend_state = 'слабый'
        elif adx < rc.adx_strong_threshold:
            tp_multiplier = rc.tp_multiplier_moderate
            trend_state = 'умеренный'
        else:
            tp_multiplier = rc.tp_multiplier_strong
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
        stop_loss_percent: Optional[float] = None,
        entry_price: Optional[float] = None
    ) -> float:
        """
        Расчет размера позиции на основе риска.

        Args:
            account_balance: баланс счета в USD
            risk_percent: процент риска на сделку (по умолчанию 2%)
            stop_loss_percent: процент стоп-лосса для расчета размера
            entry_price: цена входа (нужна для конвертации USDT → базовая валюта)

        Returns:
            float: размер позиции в контрактах/монетах
        """
        max_risk_amount = account_balance * (risk_percent / 100)

        if stop_loss_percent and stop_loss_percent > 0:
            position_size = max_risk_amount / (stop_loss_percent / 100)
        else:
            position_size = max_risk_amount

        # Для линейных фьючерсов (USDT-M) конвертируем USDT в базовую валюту
        if self.market.get('linear', False) and entry_price and entry_price > 0:
            position_size = position_size / entry_price
            logger.debug(f"🔄 Конвертация USDT → базовая валюта: {position_size:.6f} (по цене ${entry_price:.2f})")

        logger.debug(f"💰 Размер позиции: {position_size:.6f} (риск {risk_percent}% = ${max_risk_amount:.2f})")
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

            # Для линейных фьючерсов (Bybit) передаём TP/SL прямо в ордер
            if self.market.get('linear', False):
                order_params['stopLossPrice'] = stop_loss_price
                order_params['takeProfitPrice'] = take_profit_price
                logger.info(f"🛑 SL в ордере: ${stop_loss_price:.2f}")
                logger.info(f"🎯 TP в ордере: ${take_profit_price:.2f}")

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

            # Для нелинейных рынков размещаем OCO ордера отдельно
            if not self.market.get('linear', False):
                time.sleep(0.5)
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
            'trend_state': trend,
            'sl_multiplier': sl_mult,
            'tp_multiplier': tp_mult,
            'rr_ratio': round(tp_mult / sl_mult, 2),
            'sl_distance': round(atr * sl_mult, 2),
            'tp_distance': round(atr * tp_mult, 2)
        }


class PositionMonitor:
    """
    Мониторинг и динамическое обновление SL/TP открытой позиции.

    Возможности:
    - Перевод в безубыток (breakeven) при движении цены в прибыль
    - Трейлинг стоп-лосс вслед за ценой после безубытка
    - Динамическое обновление TP на основе новых значений ATR
    - Обновление SL/TP на бирже только при значимых изменениях

    Все пороги берутся из config.RiskConfig.
    """

    def __init__(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        side: str,
        entry_price: float,
        initial_sl: float,
        initial_tp: float,
        atr: float,
        breakeven_activation_atr: Optional[float] = None,
        trail_sl_multiplier: Optional[float] = None,
        trail_tp_multiplier: Optional[float] = None,
        min_update_distance_atr: Optional[float] = None,
        min_atr_change_pct: Optional[float] = None
    ):
        """
        Инициализация монитора позиции.

        Args:
            exchange: экземпляр биржи CCXT
            symbol: торговая пара
            side: направление ('long' или 'short')
            entry_price: цена входа
            initial_sl: начальный стоп-лосс
            initial_tp: начальный тейк-профит
            atr: значение ATR на момент входа
            breakeven_activation_atr: множитель ATR для активации безубытка
            trail_sl_multiplier: множитель ATR для трейлинга стопа
            trail_tp_multiplier: множитель ATR для трейлинга TP (None = не трейлить)
            min_update_distance_atr: минимальное смещение SL/TP (в долях ATR) для отправки на биржу
            min_atr_change_pct: минимальное изменение ATR в % для отправки на биржу
        """
        # Загружаем конфигурацию риск-менеджмента
        rc = cfg.RiskConfig()

        self.exchange = exchange
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.current_sl = initial_sl
        self.current_tp = initial_tp
        self.atr = atr

        # Используем переданные значения или значения по умолчанию из RiskConfig
        self.breakeven_activation_atr = breakeven_activation_atr if breakeven_activation_atr is not None else rc.breakeven_activation_atr
        self.trail_sl_multiplier = trail_sl_multiplier if trail_sl_multiplier is not None else rc.trail_sl_multiplier
        self.trail_tp_multiplier = trail_tp_multiplier if trail_tp_multiplier is not None else rc.trail_tp_multiplier
        self.min_update_distance_atr = min_update_distance_atr if min_update_distance_atr is not None else rc.min_update_distance_atr
        self.min_atr_change_pct = min_atr_change_pct if min_atr_change_pct is not None else rc.min_atr_change_pct

        # Флаги состояния
        self.breakeven_activated = False
        self.best_price = entry_price  # лучшая цена в направлении прибыли

        # Порог для активации безубытка
        self.breakeven_threshold = atr * self.breakeven_activation_atr

        # Последние значения, отправленные на биржу (чтобы не слать лишних запросов)
        self._last_exchange_sl = initial_sl
        self._last_exchange_tp = initial_tp
        self._last_exchange_atr = atr

        logger.info(f"\n{'=' * 30}")
        logger.info(f"📊 PositionMonitor создан")
        logger.info(f"   {side.upper()} @ ${entry_price:.2f}")
        logger.info(f"   SL=${initial_sl:.2f} | TP=${initial_tp:.2f} | ATR=${atr:.2f}")
        logger.info(f"   Breakeven: {self.breakeven_activation_atr}x ATR = ${self.breakeven_threshold:.2f}")
        logger.info(f"   Трейлинг SL: {self.trail_sl_multiplier}x ATR")
        if self.trail_tp_multiplier:
            logger.info(f"   Трейлинг TP: {self.trail_tp_multiplier}x ATR")
        logger.info(f"   Мин. сдвиг для обновления: {self.min_update_distance_atr}x ATR")
        logger.info(f"   Мин. изм. ATR: {self.min_atr_change_pct}%")
        logger.info(f"{'=' * 30}")

    def _should_update_exchange(self, new_sl: float, new_tp: float) -> bool:
        """
        Проверить, достаточно ли значительны изменения, чтобы отправить их на биржу.

        Args:
            new_sl: новый стоп-лосс
            new_tp: новый тейк-профит

        Returns:
            bool: True если нужно обновить на бирже
        """
        # Всегда обновляем при первом переводе в безубыток
        if self.breakeven_activated and self._last_exchange_sl == self.current_sl:
            return True

        # Проверяем изменение SL
        sl_change = abs(new_sl - self._last_exchange_sl)
        sl_significant = sl_change >= self.atr * self.min_update_distance_atr

        # Проверяем изменение TP
        tp_change = abs(new_tp - self._last_exchange_tp)
        tp_significant = tp_change >= self.atr * self.min_update_distance_atr

        return sl_significant or tp_significant

    def _should_update_atr(self, new_atr: float) -> bool:
        """Проверить, достаточно ли изменился ATR для пересчёта."""
        if self._last_exchange_atr <= 0:
            return True
        change_pct = abs(new_atr - self._last_exchange_atr) / self._last_exchange_atr * 100
        return change_pct >= self.min_atr_change_pct

    def update(self, current_price: float, new_atr: Optional[float] = None) -> Dict:
        """
        Обновить SL/TP на основе текущей рыночной цены.
        Отправляет изменения на биржу ТОЛЬКО при значимых сдвигах.

        Args:
            current_price: текущая рыночная цена
            new_atr: новое значение ATR (если изменилось)

        Returns:
            Dict: словарь с информацией о произведённых обновлениях
        """
        # Обновляем ATR если он значимо изменился
        atr_changed = False
        if new_atr is not None and new_atr > 0 and self._should_update_atr(new_atr):
            old_atr = self.atr
            self.atr = new_atr
            self.breakeven_threshold = self.atr * self.breakeven_activation_atr
            atr_changed = True
            logger.info(f"📊 ATR обновлён: ${old_atr:.2f} → ${new_atr:.2f}")

        # Расчёт текущей прибыли и обновление best_price
        if self.side == 'long':
            profit = current_price - self.entry_price
            is_profitable = profit > 0
            if current_price > self.best_price:
                self.best_price = current_price
        else:  # short
            profit = self.entry_price - current_price
            is_profitable = profit > 0
            if current_price < self.best_price:
                self.best_price = current_price

        updates = {}
        need_exchange_update = False

        # --- 1. Перевод в безубыток ---
        if not self.breakeven_activated and is_profitable and profit >= self.breakeven_threshold:
            self.current_sl = self.entry_price
            self.breakeven_activated = True
            need_exchange_update = True
            updates['breakeven'] = {
                'activated': True,
                'sl': self.entry_price
            }
            logger.info(f"🔒 BREAKEVEN АКТИВИРОВАН! SL → ${self.entry_price:.2f}")

        # --- 2. Трейлинг стоп-лосс (после безубытка) ---
        if self.breakeven_activated:
            new_sl = self._calculate_trailing_sl()
            if abs(new_sl - self.current_sl) > 0.01:
                old_sl = self.current_sl
                self.current_sl = new_sl
                updates['trailing_sl'] = {
                    'from': round(old_sl, 2),
                    'to': round(new_sl, 2)
                }
                logger.info(f"🔺 Трейлинг SL: ${old_sl:.2f} → ${new_sl:.2f}")

        # --- 3. Трейлинг тейк-профита (опционально) ---
        if self.trail_tp_multiplier is not None and self.breakeven_activated:
            new_tp = self._calculate_trailing_tp()
            if abs(new_tp - self.current_tp) > 0.01:
                old_tp = self.current_tp
                self.current_tp = new_tp
                updates['trailing_tp'] = {
                    'from': round(old_tp, 2),
                    'to': round(new_tp, 2)
                }
                logger.info(f"🎯 Трейлинг TP: ${old_tp:.2f} → ${new_tp:.2f}")

        # --- 4. Обновляем на бирже ТОЛЬКО если изменения значительны ---
        if updates or atr_changed:
            # Проверяем, достаточно ли значителен сдвиг для отправки на биржу
            if need_exchange_update or self._should_update_exchange(self.current_sl, self.current_tp):
                self._update_on_exchange(self.current_sl, self.current_tp)
                self._last_exchange_sl = self.current_sl
                self._last_exchange_tp = self.current_tp
                self._last_exchange_atr = self.atr
                updates['exchange_updated'] = True
            else:
                logger.debug(f"⏸️ Изменения незначительны — пропускаем обновление на бирже")
                updates['exchange_updated'] = False

        return updates

    def _calculate_trailing_sl(self) -> float:
        """Рассчитать трейлинг стоп-лосс на основе best_price."""
        trail_distance = self.atr * self.trail_sl_multiplier

        if self.side == 'long':
            # SL не может быть ниже entry (breakeven уже активирован)
            new_sl = self.best_price - trail_distance
            # SL может только подтягиваться вверх, не ниже текущего
            return max(new_sl, self.current_sl, self.entry_price)
        else:
            new_sl = self.best_price + trail_distance
            return min(new_sl, self.current_sl, self.entry_price)

    def _calculate_trailing_tp(self) -> float:
        """Рассчитать трейлинг тейк-профит."""
        trail_distance = self.atr * self.trail_tp_multiplier

        if self.side == 'long':
            new_tp = self.best_price + trail_distance
            return max(new_tp, self.current_tp)
        else:
            new_tp = self.best_price - trail_distance
            return min(new_tp, self.current_tp)

    def _update_on_exchange(self, sl_price: float, tp_price: float):
        """
        Обновить SL/TP на бирже через CCXT.

        Использует create_order с amount=0, что позволяет Bybit
        обновить TP/SL существующей позиции без изменения её размера.
        """
        try:
            # Для long позиции TP/SL — это sell ордера, для short — buy
            side = 'sell' if self.side == 'long' else 'buy'

            self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=0,
                params={
                    'stopLossPrice': sl_price,
                    'takeProfitPrice': tp_price,
                    'positionIdx': 0,
                    'reduceOnly': True,
                }
            )
            logger.info(f"✅ SL/TP обновлены на бирже: SL=${sl_price:.2f}, TP=${tp_price:.2f}")

        except AttributeError:
            # Fallback: прямой API вызов Bybit
            try:
                params = {
                    'symbol': self.symbol,
                    'stopLoss': str(sl_price),
                    'takeProfit': str(tp_price),
                    'tpTriggerBy': 'LastPrice',
                    'slTriggerBy': 'LastPrice',
                    'positionIdx': 0,
                }
                self.exchange.privatePostV5PositionSetTradingStop(params)
                logger.info(f"✅ SL/TP обновлены на бирже (direct): SL=${sl_price:.2f}, TP=${tp_price:.2f}")
            except Exception as e2:
                logger.error(f"❌ Ошибка обновления TP/SL (direct): {e2}")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления TP/SL на бирже: {e}")

    def is_position_open(self) -> bool:
        """
        Проверить, открыта ли ещё позиция на бирже.

        Returns:
            bool: True если позиция открыта
        """
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for pos in positions:
                if pos['symbol'] == self.symbol:
                    size = float(pos.get('contracts', 0) or pos.get('size', 0))
                    if size > 0:
                        return True
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки позиции: {e}")
            return False

    def get_status(self) -> Dict:
        """
        Получить текущий статус монитора.

        Returns:
            Dict: статус позиции
        """
        return {
            'side': self.side,
            'entry_price': self.entry_price,
            'current_sl': self.current_sl,
            'current_tp': self.current_tp,
            'atr': self.atr,
            'best_price': self.best_price,
            'breakeven_activated': self.breakeven_activated,
            'breakeven_threshold': self.breakeven_threshold,
        }