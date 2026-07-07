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