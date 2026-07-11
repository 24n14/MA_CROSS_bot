import numpy as np
from typing import Dict, Optional
from log import logger
import config as cfg


class PositionMonitor:
    """
    Мониторинг и динамическое обновление SL/TP открытой позиции на бирже.
    """

    def __init__(
        self,
        exchange,
        symbol: str,
        side: str,
        entry_price: float,
        position_size: float,
        atr: float,
        initial_sl: float,
        initial_tp: float,
        breakeven_activation_atr: Optional[float] = None,
        trail_sl_multiplier: Optional[float] = None,
        trail_tp_multiplier: Optional[float] = None,
        min_update_distance_atr: Optional[float] = None,
        min_atr_change_pct: Optional[float] = None
    ):
        self.exchange = exchange
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.position_size = position_size
        self.atr = atr
        self.current_sl = initial_sl
        self.current_tp = initial_tp

        rc = cfg.RiskConfig()
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

        logger.info(f"\n{'=' * 30}\nPositionMonitor создан")
        logger.info(f"{side.upper()} @ ${entry_price:.2f} | Lot: {position_size}")
        logger.info(f"SL=${initial_sl:.2f} | TP=${initial_tp:.2f} | ATR=${atr:.2f}")
        logger.info(f"{'=' * 30}")

    def _should_update_exchange(self, new_sl: float, new_tp: float) -> bool:
        """
        Проверка необходимости обновления SL/TP на бирже.
        """
        if self.breakeven_activated and self._last_exchange_sl == self.entry_price:
            return True

        sl_significant = abs(new_sl - self._last_exchange_sl) >= self.atr * self.min_update_distance_atr
        tp_significant = abs(new_tp - self._last_exchange_tp) >= self.atr * self.min_update_distance_atr
        return sl_significant or tp_significant

    def _should_update_atr(self, new_atr: float) -> bool:
        """
        Проверка необходимости обновления ATR.
        """
        if self._last_exchange_atr <= 0:
            return True
        return (abs(new_atr - self._last_exchange_atr) / self._last_exchange_atr * 100) >= self.min_atr_change_pct

    def update(self, current_price: float, new_atr: Optional[float] = None) -> Dict:
        """
        Обновление позиции на основе текущей цены и ATR.
        """
        updates = {'exchange_updated': False, 'error': False}
        atr_changed = False

        # Обновление ATR
        if new_atr is not None and new_atr > 0 and self._should_update_atr(new_atr):
            old_atr = self.atr
            self.atr = new_atr
            self.breakeven_threshold = self.atr * self.breakeven_activation_atr
            atr_changed = True
            logger.info(f"ATR ОБНОВЛЕН: ${old_atr:.2f} -> ${new_atr:.2f}")

        # Обновление лучшей цены
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

        # 1. Активация безубытка
        if not self.breakeven_activated and is_profitable and profit >= self.breakeven_threshold:
            self.current_sl = self.entry_price
            self.breakeven_activated = True
            updates['breakeven'] = {'activated': True, 'sl': self.entry_price}
            logger.info(f"BREAKEVEN АКТИВИРОВАН! SL -> ${self.entry_price:.2f}")

        # 2. Трейлинг стоп-лосса
        if self.breakeven_activated:
            new_sl = self._calculate_trailing_sl()
            if abs(new_sl - self.current_sl) > 0.01:
                old_sl = self.current_sl
                self.current_sl = new_sl
                updates['trailing_sl'] = {'from': round(old_sl, 2), 'to': round(new_sl, 2)}
                logger.info(f"Трейлинг SL: ${old_sl:.2f} -> ${new_sl:.2f}")

        # 3. Трейлинг тейк-профита
        if self.trail_tp_multiplier is not None and self.breakeven_activated:
            new_tp = self._calculate_trailing_tp()
            if abs(new_tp - self.current_tp) > 0.01:
                old_tp = self.current_tp
                self.current_tp = new_tp
                updates['trailing_tp'] = {'from': round(old_tp, 2), 'to': round(new_tp, 2)}
                logger.info(f"Трейлинг TP: ${old_tp:.2f} -> ${new_tp:.2f}")

        # 4. Отправка изменений на биржу
        if (updates.get('breakeven') or updates.get('trailing_sl') or
            updates.get('trailing_tp') or atr_changed):
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
                logger.debug("Изменения незначительны – обновление пропущено.")

        return updates

    def _calculate_trailing_sl(self) -> float:
        """
        Расчет трейлингового стоп-лосса.
        """
        trail_distance = self.atr * self.trail_sl_multiplier

        if self.side == 'long':
            new_sl = self.best_price - trail_distance
            return max(new_sl, self.current_sl, self.entry_price)
        else:  # short
            new_sl = self.best_price + trail_distance
            return min(new_sl, self.current_sl, self.entry_price)

    def _calculate_trailing_tp(self) -> float:
        """
        Расчет трейлингового тейк-профита.
        """
        trail_distance = self.atr * self.trail_tp_multiplier

        if self.side == 'long':
            new_tp = self.best_price + trail_distance
            return max(new_tp, self.current_tp)
        else:  # short
            new_tp = self.best_price - trail_distance
            return min(new_tp, self.current_tp)

    def _update_on_exchange(self, sl_price: float, tp_price: float) -> bool:
        """
        Обновить SL/TP на бирже через CCXT.
        Возвращает True в случае успеха.
        """
        # Округление перед отправкой
        price_step = self.exchange.market(self.symbol).get('precision', {}).get('price', 0.01)
        precision = int(abs(np.log10(price_step)))
        sl_price = round(sl_price, precision)
        tp_price = round(tp_price, precision)

        side = 'sell' if self.side == 'long' else 'buy'

        try:
            # Метод 1: Обновление через стандартный ордер
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
            logger.info(f"SL/TP обновлены: SL=${sl_price:.2f}, TP=${tp_price:.2f}")
            return True

        except Exception as e:
            logger.warning(f"Стандартный метод изменения SL/TP не сработал: {e}. Применяем Fallback...")

            # Метод 2: Прямой вызов V5 API
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
                logger.info(f"SL/TP успешно обновлены через V5 API: SL=${sl_price:.2f}, TP=${tp_price:.2f}")
                return True

            except Exception as e2:
                logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось установить стопы: {e2}")
                return False

    def is_position_open(self) -> bool:
        """
        Проверка наличия открытой позиции.
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
            logger.error(f"Ошибка проверки открытой позиции: {e}")
            return False

    def get_status(self) -> Dict:
        """
        Получение текущего статуса позиции.
        """
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
