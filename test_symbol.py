"""
Тест передачи symbol в ExchangeDataLoader
"""
from exchange import ExchangeDataLoader

# Тест 1: Явная передача
loader = ExchangeDataLoader('binance')
df = loader.fetch_ohlcv(symbol='BTC/USDT', timeframe='1h', limit=10)
print(f"Тест 1: {'✅' if df is not None else '❌'}")

# Тест 2: Без слеша
df = loader.fetch_ohlcv(symbol='BTCUSDT', timeframe='1h', limit=10)
print(f"Тест 2: {'✅' if df is not None else '❌'}")

# Тест 3: С маленькой буквы
df = loader.fetch_ohlcv(symbol='btc/usdt', timeframe='1h', limit=10)
print(f"Тест 3: {'✅' if df is not None else '❌'}")

# Тест 4: Пустой символ
df = loader.fetch_ohlcv(symbol='', timeframe='1h', limit=10)
print(f"Тест 4: {'✅ (ожидаемо)' if df is None else '❌'}")

# Тест 5: Несуществующая пара
df = loader.fetch_ohlcv(symbol='INVALID/PAIR', timeframe='1h', limit=10)
print(f"Тест 5: {'✅ (ожидаемо)' if df is None else '❌'}")
