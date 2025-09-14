import asyncio
from typing import List, Dict, Any
import itertools

class ArbitrageEngine:
    """
    Analyzes real-time data from multiple providers to find arbitrage opportunities.
    """
    def __init__(self, providers: List, config: Dict):
        """
        Initializes the engine with data providers and configuration.

        Args:
            providers: A list of instantiated provider objects.
            config: A dictionary containing 'fees' and 'threshold' settings.
        """
        self.providers = providers
        # Example fee structure: {'binance': {'taker': 0.001, 'withdrawal_usd': 5}}
        self.fees_config = config.get('fees', {})
        self.profit_threshold = config.get('threshold', 0.001) # Default 0.1%

    async def find_opportunities(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Compares prices across all providers for given symbols and
        identifies potential arbitrage opportunities after fees.

        Args:
            symbols: A list of symbols to check for arbitrage, e.g., ['BTC/USDT', 'ETH/USDT'].

        Returns:
            A list of dictionaries, where each dictionary represents a
            profitable arbitrage opportunity.
        """
        all_opportunities = []
        for symbol in symbols:
            # Fetch tickers from all providers concurrently
            tasks = [provider.get_ticker(symbol) for provider in self.providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out errors and create a list of valid tickers
            valid_tickers = []
            for i, res in enumerate(results):
                if isinstance(res, dict) and 'error' not in res and res.get('ask') and res.get('bid'):
                    # Add provider name to the ticker info
                    res['provider_name'] = self.providers[i].name
                    valid_tickers.append(res)
                # else:
                #     print(f"Skipping invalid ticker from {self.providers[i].name}: {res}")

            if len(valid_tickers) < 2:
                continue # Need at least two providers to find an opportunity

            # Find the best buy (lowest ask) and sell (highest bid) prices
            # We check all possible pairs of exchanges
            for buy_ticker, sell_ticker in itertools.permutations(valid_tickers, 2):

                buy_provider_name = buy_ticker['provider_name']
                sell_provider_name = sell_ticker['provider_name']

                buy_price = float(buy_ticker['ask']) # Price to buy at
                sell_price = float(sell_ticker['bid']) # Price to sell at

                if buy_price >= sell_price:
                    continue # No potential for profit

                # --- Fee Calculation ---
                # Get fee info for the two providers, with defaults
                buy_fees = self.fees_config.get(buy_provider_name.lower(), {'taker': 0.002, 'withdrawal_usd': 10.0})
                sell_fees = self.fees_config.get(sell_provider_name.lower(), {'taker': 0.002, 'withdrawal_usd': 10.0})

                # 1. Cost of buying 1 unit of the base asset
                # (e.g., 1 BTC in BTC/USDT)
                initial_cost_usd = buy_price
                buy_fee_usd = initial_cost_usd * buy_fees['taker']
                total_cost_usd = initial_cost_usd + buy_fee_usd

                # 2. Revenue from selling 1 unit of the base asset
                revenue_usd = sell_price
                sell_fee_usd = revenue_usd * sell_fees['taker']
                net_revenue_usd = revenue_usd - sell_fee_usd

                # 3. Withdrawal fee (assuming we move the asset from buy exchange to sell exchange)
                # This is tricky as withdrawal fees are per-asset, not per-USD.
                # For this model, we'll use a generic USD withdrawal fee as an estimate.
                # A more advanced model would look up fees per asset (e.g., BTC withdrawal fee).
                withdrawal_fee_usd = buy_fees.get('withdrawal_usd', 10.0)

                # 4. Calculate Net Profit
                net_profit_usd = net_revenue_usd - total_cost_usd - withdrawal_fee_usd

                if net_profit_usd <= 0:
                    continue

                profit_percentage = (net_profit_usd / total_cost_usd) * 100

                if profit_percentage > self.profit_threshold:
                    opportunity = {
                        'symbol': symbol,
                        'buy_at': buy_provider_name,
                        'sell_at': sell_provider_name,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'potential_profit_usd': round(net_profit_usd, 2),
                        'profit_percentage': round(profit_percentage, 4),
                        'calculation': {
                            'initial_cost': round(initial_cost_usd, 2),
                            'buy_fee': round(buy_fee_usd, 2),
                            'sell_fee': round(sell_fee_usd, 2),
                            'withdrawal_fee': round(withdrawal_fee_usd, 2),
                            'net_revenue': round(net_revenue_usd, 2),
                        }
                    }
                    all_opportunities.append(opportunity)

        return all_opportunities
