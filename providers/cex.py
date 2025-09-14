import asyncio
import random
import time
from typing import List, Dict, Any

# --- Mock CCXT.PRO Implementation ---
# This block is used if the actual ccxt.pro library is not installed,
# allowing for development and testing without a license.
try:
    import ccxt.pro as ccxtpro
    IS_MOCK = False
except ImportError:
    print("Warning: ccxt.pro not found. Using a mock implementation for CEXProvider.")
    IS_MOCK = True

    class MockExchange:
        """Mocks a single ccxt.pro exchange connection."""
        def __init__(self, config: Dict = None):
            self._last_price = 50000 + random.uniform(-100, 100)

        async def watch_ticker(self, symbol: str) -> Dict[str, Any]:
            """Simulates waiting for and receiving a single ticker update."""
            await asyncio.sleep(random.uniform(0.1, 0.5)) # Simulate network latency
            self._last_price *= random.uniform(0.999, 1.001)
            bid = self._last_price * 0.9998
            ask = self._last_price * 1.0002
            return {
                'symbol': symbol,
                'timestamp': int(time.time() * 1000),
                'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                'high': self._last_price * 1.02,
                'low': self._last_price * 0.98,
                'bid': bid,
                'ask': ask,
                'last': self._last_price,
                'baseVolume': random.uniform(1000, 5000),
                'info': {}, # Keep the structure consistent
            }

        async def watch_order_book(self, symbol: str, limit: int = 25) -> Dict[str, List]:
            """Simulates waiting for and receiving a single order book update."""
            await asyncio.sleep(random.uniform(0.1, 0.5))
            price = 50000 + random.uniform(-100, 100)
            bids = sorted([[price - random.uniform(0, 10), random.uniform(0.1, 5)] for _ in range(limit)], key=lambda x: x[0], reverse=True)
            asks = sorted([[price + random.uniform(0, 10), random.uniform(0.1, 5)] for _ in range(limit)], key=lambda x: x[0])
            return {
                'bids': bids,
                'asks': asks,
                'symbol': symbol,
                'timestamp': int(time.time() * 1000),
                'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            }

        async def close(self):
            """Simulates closing the connection."""
            print(f"Mock exchange connection closed.")
            await asyncio.sleep(0.01)

    class MockCCXTPro:
        """Mocks the ccxtpro library by dynamically creating MockExchange instances."""
        def __getattr__(self, name: str):
            # Return a constructor for a MockExchange
            return MockExchange

    ccxtpro = MockCCXTPro()

# --- Real CEX Provider ---
from .base import BaseProvider

class CEXProvider(BaseProvider):
    """
    Connects to Centralized Exchanges (CEX) using ccxt.pro
    to get real-time data via WebSockets.
    """
    def __init__(self, name: str, config: Dict = None):
        super().__init__(name)
        self.exchange_id = name.lower()
        try:
            exchange_class = getattr(ccxtpro, self.exchange_id)
            # Pass API keys if they exist for this exchange
            api_keys = config.get('api_keys', {}).get(self.exchange_id, {})
            self.exchange = exchange_class(api_keys)
        except (AttributeError, TypeError):
            # TypeError can be raised by ccxt.pro if keys are wrong type
            raise ValueError(f"Exchange '{self.exchange_id}' is not supported or config is invalid.")

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches the next ticker data update from the WebSocket stream.
        """
        if IS_MOCK:
            print(f"[{self.name}] MOCK watching ticker for {symbol}...")
        return await self.exchange.watch_ticker(symbol)

    async def get_order_book(self, symbol: str, limit: int = 25) -> Dict[str, List]:
        """
        Fetches the next order book data update from the WebSocket stream.
        """
        if IS_MOCK:
             print(f"[{self.name}] MOCK watching order book for {symbol}...")
        return await self.exchange.watch_order_book(symbol, limit)

    async def close(self):
        """Closes the underlying ccxt.pro exchange connection."""
        print(f"Closing connection for {self.name}...")
        await self.exchange.close()
