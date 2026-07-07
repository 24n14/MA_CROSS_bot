# SL в процентах для расчета размера
        sl_percent = abs(close_price - sl_price) / close_price * 100
        position_size = risk_manager.calculate_position_size(
            account_balance=usdt_balance,
            risk_percent=risk_percent,
            stop_loss_percent=sl_percent,
            entry_price=close_price
        )