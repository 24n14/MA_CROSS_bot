import numpy as np
from typing import Dict, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
import ccxt
from log import logger
import config as cfg


class DynamicRiskManager:
    """
    Менеджер риска с динамическим расчетом стоп-лосса и тейк-профита на основе ATR и ADX.
    Отвечает ТОЛЬКО за расчеты, создание ордеров находится в open_pos.py
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
        """
        Расчет стоп-лосса и тейк-профита на основе ATR и ADX.
        """
        if atr <= 0:
            logger.error(f"ATR = {atr}, невозможно рассчитать SL/TP")
            return entry_price, entry_price

        rc = self.risk_cfg

        # Определяем множители SL и TP
        if atr_multiplier is not None:
            sl_multiplier = atr_multiplier
        else:
            sl_multiplier = rc.base_sl_multiplier

        # Определяем множитель TP на основе ADX
        if adx < rc.adx_moderate_threshold:
            tp_multiplier = rc.tp_multiplier_weak
            trend_state = 'слабый'
        elif adx < rc.adx_strong_threshold:
            tp_multiplier = rc.tp_multiplier_moderate
            trend_state = 'умеренный'
        else:
            tp_multiplier = rc.tp_multiplier_strong
            trend_state = 'сильный'

        # Переопределяем TP множитель если указан кастомный RR
        if risk_reward_ratio is not None:
            tp_multiplier = sl_multiplier * risk_reward_ratio
            logger.debug(f"Кастомный RR={risk_reward_ratio}: TP множитель={tp_multiplier:.2f}")

        sl_distance = atr * sl_multiplier
        tp_distance = atr * tp_multiplier

        if side == 'long':
            stop_loss_price = entry_price - sl_distance
            take_profit_price = entry_price + tp_distance
        else:  # short
            stop_loss_price = entry_price + sl_distance
            take_profit_price = entry_price - tp_distance

        logger.info(f"\n{'=' * 30}\n ДИНАМИЧЕСКИЙ РАСЧЕТ SL/TP")
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
        """
        Расчет размера позиции на основе риска.
        """
        if account_balance <= 0:
            logger.error("Баланс аккаунта должен быть больше 0")
            return 0.0

        max_risk_amount = account_balance * (risk_percent / 100)

        if stop_loss_percent and stop_loss_percent > 0:
            position_size = max_risk_amount / (stop_loss_percent / 100)
        else:
            position_size = max_risk_amount

        # Конвертация в базовую валюту для фьючерсов
        if self.market.get('linear', False) and entry_price and entry_price > 0:
            position_size = position_size / entry_price
            logger.debug(f"Конвертация USDT -> базовая валюта: {position_size:.6f} (по цене ${entry_price:.2f})")

        # Округление размера позиции
        position_size = self._adjust_amount(position_size)

        logger.debug(f"Размер позиции: {position_size:.6f} (риск {risk_percent}% = ${max_risk_amount:.2f})")
        return position_size

    def _adjust_amount(self, amount: float) -> float:
        """
        Округление размера позиции согласно шагу биржи.
        """
        if amount <= 0:
            return 0.0

        amount_step = self.market.get('precision', {}).get('amount', 0.001)
        precision = int(abs(np.log10(amount_step)))
        return float(Decimal(str(amount)).quantize(Decimal(f"0.{'0' * precision}"), rounding=ROUND_DOWN))

    def _adjust_price(self, price: float) -> float:
        """
        Округление цены согласно шагу биржи.
        """
        if price <= 0:
            return 0.0

        price_step = self.market.get('precision', {}).get('price', 0.01)
        precision = int(abs(np.log10(price_step)))
        return round(price, precision)

    def get_dynamic_multipliers(self, atr: float, adx: float) -> Dict:
        """
        Получение динамических множителей на основе ATR и ADX.
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
