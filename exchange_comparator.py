import streamlit as st
import pandas as pd
import ccxt
from faker import Faker
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

# --- Configuration ---
# Define the required columns to ensure consistency across providers.
REQUIRED_COLUMNS = [
    '交易所名称', '交易对', '现货价格', '买一价(Bid)', '卖一价(Ask)', '24h交易量',
    '充值网络', '充值费用', '提现网络', '提现费用', '提现速度', 'API支持'
]

# --- Provider Pattern: Abstract Base Class ---

class BaseProvider(ABC):
    """
    Abstract base class for data providers. Enforces the implementation
    of the get_data method to ensure a consistent interface.
    """
    @abstractmethod
    def get_data(self, **kwargs) -> pd.DataFrame:
        """
        Abstract method to fetch and return data as a Pandas DataFrame.
        The returned DataFrame must contain the REQUIRED_COLUMNS.
        """
        pass

# --- Mock Data Provider ---

class MockProvider(BaseProvider):
    """
    Generates realistic-looking mock data for demonstration purposes.
    This allows for UI development and testing without making live API calls.
    """
    def __init__(self):
        self.fake = Faker()

    def get_data(self, **kwargs) -> pd.DataFrame:
        """
        Generates and returns a DataFrame with mock exchange data.

        Returns:
            pd.DataFrame: A DataFrame containing mock data for several exchanges
                          and trading pairs, conforming to REQUIRED_COLUMNS.
        """
        mock_data = []
        exchanges = ['MockBinance', 'MockCoinbase', 'MockKraken', 'MockHuobi', 'MockOKX']
        symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/BTC']
        networks = ['ERC20', 'TRC20', 'BEP20', 'Solana', 'Bitcoin']

        for exchange in exchanges:
            for symbol in symbols:
                base_price = random.uniform(20, 65000)
                bid = base_price * random.uniform(0.998, 0.999)
                ask = base_price * random.uniform(1.001, 1.002)

                mock_data.append({
                    '交易所名称': exchange,
                    '交易对': symbol,
                    '现货价格': f"{base_price:.2f}",
                    '买一价(Bid)': f"{bid:.2f}",
                    '卖一价(Ask)': f"{ask:.2f}",
                    '24h交易量': f"{random.uniform(1000, 50000):.4f}",
                    '充值网络': random.choice(networks),
                    '充值费用': f"{random.uniform(0.0, 0.5):.4f}%",
                    '提现网络': random.choice(networks),
                    '提现费用': f"{random.uniform(0.5, 2.0):.2f} USD",
                    '提现速度': f"{random.randint(2, 30)} 分钟",
                    'API支持': random.choice(['是', '否'])
                })

        df = pd.DataFrame(mock_data)
        # Ensure all required columns are present and in the correct order
        return df[REQUIRED_COLUMNS]

# --- Real Data Provider (CCXT) ---

class CCXTProvider(BaseProvider):
    """
    Fetches live data from cryptocurrency exchanges using the CCXT library.
    Handles multiple exchanges and symbols, and includes graceful error handling.
    """
    def get_data(self, exchanges: List[str], symbols: List[str]) -> pd.DataFrame:
        """
        Fetches live ticker and fee data for selected exchanges and symbols.

        Args:
            exchanges (List[str]): A list of exchange IDs (e.g., 'binance').
            symbols (List[str]): A list of trading symbols (e.g., 'BTC/USDT').

        Returns:
            pd.DataFrame: A DataFrame containing the aggregated data from all
                          selected sources, conforming to REQUIRED_COLUMNS.
        """
        all_data = []
        for exchange_id in exchanges:
            try:
                exchange_class = getattr(ccxt, exchange_id)
                exchange = exchange_class()
            except AttributeError:
                st.error(f"错误：交易所 '{exchange_id}' 不受 CCXT 支持或ID错误。")
                continue
            except ccxt.ExchangeNotAvailable as e:
                st.error(f"错误：交易所 '{exchange_id}' 暂时不可用。({e})")
                continue

            # Fetch ticker data
            try:
                tickers = exchange.fetch_tickers(symbols) if exchange.has['fetchTickers'] else self._fetch_tickers_loop(exchange, symbols)
            except ccxt.NetworkError as e:
                st.error(f"网络错误：无法从 '{exchange_id}' 获取行情数据。请检查您的网络连接。 ({e})")
                continue
            except Exception as e:
                st.error(f"获取 '{exchange_id}' 行情数据时发生未知错误: {e}")
                continue

            # Attempt to fetch currency data (graceful degradation)
            currency_info = self._fetch_currency_details(exchange)

            for symbol, ticker in tickers.items():
                base_currency = symbol.split('/')[0]
                fee_details = currency_info.get(base_currency, self._get_default_fee_info())

                data_row = {
                    '交易所名称': exchange.name,
                    '交易对': symbol,
                    '现货价格': ticker.get('last') or 'N/A',
                    '买一价(Bid)': ticker.get('bid') or 'N/A',
                    '卖一价(Ask)': ticker.get('ask') or 'N/A',
                    '24h交易量': ticker.get('baseVolume') or 'N/A',
                    '充值网络': fee_details['deposit_network'],
                    '充值费用': fee_details['deposit_fee'],
                    '提现网络': fee_details['withdraw_network'],
                    '提现费用': fee_details['withdraw_fee'],
                    '提现速度': '信息待获取', # This info is not commonly available via API
                    'API支持': '是' if exchange.has['CORS'] else '可能需要代理'
                }
                all_data.append(data_row)

        if not all_data:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)

        df = pd.DataFrame(all_data)
        # Ensure all required columns are present and in the correct order
        return df[REQUIRED_COLUMNS]

    def _fetch_tickers_loop(self, exchange, symbols: List[str]) -> Dict[str, Any]:
        """Fallback to fetch tickers one by one if fetchTickers is not available."""
        tickers = {}
        for symbol in symbols:
            try:
                tickers[symbol] = exchange.fetch_ticker(symbol)
            except Exception:
                # Ignore symbols that can't be fetched on this exchange
                pass
        return tickers

    def _fetch_currency_details(self, exchange) -> Dict[str, Dict]:
        """
        Attempts to fetch currency network and fee information.
        Returns a dictionary with structured fee info, gracefully degrading if call fails.
        """
        currency_info = {}
        if not exchange.has['fetchCurrencies']:
            return {}

        try:
            # Some exchanges might require authentication for this
            currencies = exchange.fetch_currencies()
            for code, currency in currencies.items():
                # Extract deposit/withdraw info if available
                # This logic is complex as 'networks' structure varies widely
                networks = currency.get('networks', {})
                deposit_fee = "N/A"
                withdraw_fee = "N/A"
                deposit_network = "N/A"
                withdraw_network = "N/A"

                # A simplified approach to find any network info
                if networks:
                    network_names = list(networks.keys())
                    deposit_network = ", ".join(network_names)
                    withdraw_network = ", ".join(network_names)

                    # Try to find a representative fee
                    for net_info in networks.values():
                        if net_info.get('deposit', {}).get('fee') is not None:
                            deposit_fee = str(net_info['deposit']['fee'])
                        if net_info.get('withdraw', {}).get('fee') is not None:
                            withdraw_fee = str(net_info['withdraw']['fee'])
                        # Break after finding first piece of info for simplicity
                        if deposit_fee != "N/A" and withdraw_fee != "N/A":
                            break

                currency_info[code] = {
                    'deposit_network': deposit_network,
                    'deposit_fee': deposit_fee,
                    'withdraw_network': withdraw_network,
                    'withdraw_fee': withdraw_fee
                }
        except ccxt.AuthenticationError:
            st.warning(f"提示: '{exchange.name}' 需要API密钥才能获取详细的充提费用信息。")
        except Exception as e:
            st.warning(f"提示: 无法从 '{exchange.name}' 获取充提费用信息。({type(e).__name__})")

        return currency_info

    def _get_default_fee_info(self) -> Dict[str, str]:
        """Returns a default structure for when currency info is unavailable."""
        return {
            'deposit_network': '信息待获取',
            'deposit_fee': '信息待获取',
            'withdraw_network': '信息待获取',
            'withdraw_fee': '信息待获取',
        }


# --- Streamlit User Interface ---

def main():
    st.set_page_config(page_title="数字货币交易所对比工具", layout="wide")
    st.title("📈 数字货币交易所对比工具")
    st.caption("一个功能完备的原型，用于对比不同交易所的行情和费率信息。")

    # --- Sidebar Controls ---
    st.sidebar.header("🛠️ 控制面板")

    mode = st.sidebar.radio(
        "选择数据模式",
        ('模拟数据模式', '真实数据模式'),
        help="选择使用预置的模拟数据或通过API拉取实时数据。"
    )

    data_provider: BaseProvider
    df_display = pd.DataFrame(columns=REQUIRED_COLUMNS)

    if mode == '模拟数据模式':
        st.sidebar.info("当前为模拟模式。下方将展示预先生成的示例数据。")
        data_provider = MockProvider()
        if st.sidebar.button("🔄 重新生成模拟数据"):
            df_display = data_provider.get_data()
        else:
            # Get data on first load
            df_display = data_provider.get_data()

    else: # 真实数据模式
        st.sidebar.info("当前为真实模式。请选择交易所和交易对后点击按钮获取数据。")

        # --- API Key Inputs (for future use) ---
        with st.sidebar.expander("🔑 API密钥 (可选)"):
            st.text_input("API Key", type="password", help="部分交易所获取费率等信息需要API Key。")
            st.text_input("API Secret", type="password")

        # --- Exchange and Symbol Selection ---
        try:
            available_exchanges = ccxt.exchanges
        except Exception:
            st.error("无法加载可用交易所列表。请检查网络连接。")
            available_exchanges = []

        selected_exchanges = st.sidebar.multiselect(
            "选择交易所",
            options=available_exchanges,
            default=['binance', 'kraken', 'coinbase'],
            help="支持多选。选择您想查询的交易所。"
        )

        # Common symbols for user convenience
        common_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BTC/USD', 'ETH/USD', 'XRP/USDT', 'DOGE/USDT']
        selected_symbols = st.sidebar.multiselect(
            "选择或输入交易对",
            options=common_symbols,
            default=['BTC/USDT', 'ETH/USDT'],
            help="支持多选。您可以从列表中选择，或直接输入后按回车添加（如：ADA/USDT）。"
        )

        if st.sidebar.button("🚀 获取实时数据", type="primary"):
            if not selected_exchanges or not selected_symbols:
                st.warning("请至少选择一个交易所和一个交易对。")
            else:
                data_provider = CCXTProvider()
                with st.spinner('正在从各大交易所拉取数据，请稍候...'):
                    df_display = data_provider.get_data(
                        exchanges=selected_exchanges,
                        symbols=selected_symbols
                    )

    # --- Main Panel Data Display ---
    st.header("📊 对比结果")

    if not df_display.empty:
        st.dataframe(df_display, use_container_width=True)
    else:
        st.info("请在左侧控制面板中选择参数并获取数据。")


if __name__ == "__main__":
    main()
