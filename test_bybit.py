
from pybit.unified_trading import HTTP

session = HTTP(
    demo=True,
    api_key="sJ5vXOJGu95ZdMzprr",
    api_secret="ioBVwqfWIUGpseu2jicINE2zDzHrciZfjybB"
)

# Сначала просто проверим баланс (GET запрос)
try:
    balance = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    print("=== БАЛАНС ===")
    print(balance)
except Exception as e:
    print(f"Ошибка баланса: {e}")

# Потом попробуем ордер (POST запрос) с очень малым qty
try:
    result = session.place_order(
        category="linear",
        symbol="BTCUSDT",
        side="Sell",
        orderType="Market",
        qty="0.001"
    )
    print("\n=== ОРДЕР ===")
    print(result)
except Exception as e:
    print(f"\nОшибка ордера: {e}")

