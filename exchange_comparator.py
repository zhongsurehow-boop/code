import streamlit as st
import pandas as pd
import ccxt
from faker import Faker
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np

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
    st.set_page_config(
        page_title="数字货币交易所对比工具", 
        layout="wide",
        page_icon="📈",
        initial_sidebar_state="expanded"
    )
    
    # 添加自定义CSS样式
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin: 0.5rem 0;
    }
    .stDataFrame {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="main-header"><h1>📈 数字货币交易所对比工具</h1><p>专业的多交易所实时数据对比分析平台</p></div>', unsafe_allow_html=True)

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
    if not df_display.empty:
        # 添加数据统计概览
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("交易所数量", len(df_display['交易所名称'].unique()))
        with col2:
            st.metric("交易对数量", len(df_display['交易对'].unique()))
        with col3:
            avg_price = df_display['现货价格'].apply(lambda x: float(str(x).replace(',', '')) if str(x) != 'N/A' else 0).mean()
            st.metric("平均价格", f"${avg_price:.2f}" if avg_price > 0 else "N/A")
        with col4:
            st.metric("数据更新时间", datetime.now().strftime("%H:%M:%S"))
        
        st.header("📊 数据分析")
        
        # 添加筛选功能
        col1, col2 = st.columns(2)
        with col1:
            selected_exchanges_filter = st.multiselect(
                "筛选交易所",
                options=df_display['交易所名称'].unique(),
                default=df_display['交易所名称'].unique(),
                key="exchange_filter"
            )
        with col2:
            selected_symbols_filter = st.multiselect(
                "筛选交易对",
                options=df_display['交易对'].unique(),
                default=df_display['交易对'].unique(),
                key="symbol_filter"
            )
        
        # 应用筛选
        filtered_df = df_display[
            (df_display['交易所名称'].isin(selected_exchanges_filter)) &
            (df_display['交易对'].isin(selected_symbols_filter))
        ]
        
        # 数据可视化
        if not filtered_df.empty:
            # 价格对比图表
            st.subheader("💰 价格对比分析")
            
            # 准备价格数据
            price_data = []
            for _, row in filtered_df.iterrows():
                try:
                    price = float(str(row['现货价格']).replace(',', '')) if str(row['现货价格']) != 'N/A' else None
                    if price:
                        price_data.append({
                            '交易所': row['交易所名称'],
                            '交易对': row['交易对'],
                            '价格': price
                        })
                except:
                    continue
            
            if price_data:
                price_df = pd.DataFrame(price_data)
                
                # 按交易对分组的价格对比
                for symbol in price_df['交易对'].unique():
                    symbol_data = price_df[price_df['交易对'] == symbol]
                    if len(symbol_data) > 1:
                        fig = px.bar(
                            symbol_data, 
                            x='交易所', 
                            y='价格',
                            title=f'{symbol} 各交易所价格对比',
                            color='价格',
                            color_continuous_scale='viridis'
                        )
                        fig.update_layout(height=400)
                        st.plotly_chart(fig, use_container_width=True)
            
            # 买卖价差分析
            st.subheader("📈 买卖价差分析")
            spread_data = []
            for _, row in filtered_df.iterrows():
                try:
                    bid = float(str(row['买一价(Bid)']).replace(',', '')) if str(row['买一价(Bid)']) != 'N/A' else None
                    ask = float(str(row['卖一价(Ask)']).replace(',', '')) if str(row['卖一价(Ask)']) != 'N/A' else None
                    if bid and ask:
                        spread = ask - bid
                        spread_pct = (spread / bid) * 100
                        spread_data.append({
                            '交易所': row['交易所名称'],
                            '交易对': row['交易对'],
                            '价差': spread,
                            '价差百分比': spread_pct
                        })
                except:
                    continue
            
            if spread_data:
                spread_df = pd.DataFrame(spread_data)
                fig = px.scatter(
                    spread_df,
                    x='交易所',
                    y='价差百分比',
                    color='交易对',
                    size='价差',
                    title='各交易所买卖价差对比',
                    hover_data=['价差']
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
        
        # 详细数据表格
        st.subheader("📋 详细数据")
        
        # 添加排序选项
        sort_column = st.selectbox(
            "选择排序列",
            options=filtered_df.columns,
            index=2  # 默认按现货价格排序
        )
        
        sort_order = st.radio("排序方式", ["升序", "降序"], horizontal=True)
        
        # 应用排序
        try:
            if sort_column in ['现货价格', '买一价(Bid)', '卖一价(Ask)']:
                # 数值列排序
                filtered_df_sorted = filtered_df.copy()
                filtered_df_sorted[sort_column + '_numeric'] = pd.to_numeric(
                    filtered_df_sorted[sort_column].astype(str).str.replace(',', ''), 
                    errors='coerce'
                )
                filtered_df_sorted = filtered_df_sorted.sort_values(
                    sort_column + '_numeric', 
                    ascending=(sort_order == "升序")
                ).drop(columns=[sort_column + '_numeric'])
            else:
                # 文本列排序
                filtered_df_sorted = filtered_df.sort_values(
                    sort_column, 
                    ascending=(sort_order == "升序")
                )
        except:
            filtered_df_sorted = filtered_df
        
        # 显示数据表格
        st.dataframe(
            filtered_df_sorted, 
            use_container_width=True,
            hide_index=True
        )
        
        # 数据导出功能
        st.subheader("💾 数据导出")
        col1, col2 = st.columns(2)
        with col1:
            csv = filtered_df_sorted.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 下载CSV文件",
                data=csv,
                file_name=f"exchange_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        with col2:
            json_data = filtered_df_sorted.to_json(orient='records', force_ascii=False, indent=2)
            st.download_button(
                label="📥 下载JSON文件",
                data=json_data,
                file_name=f"exchange_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
    else:
        st.info("🔍 请在左侧控制面板中选择参数并获取数据开始分析。")
        
        # 添加使用说明
        with st.expander("📖 使用说明"):
            st.markdown("""
            ### 如何使用本工具：
            
            1. **选择数据模式**：
               - 模拟数据模式：快速体验功能，使用预生成的示例数据
               - 真实数据模式：获取实时市场数据（需要网络连接）
            
            2. **配置参数**（真实数据模式）：
               - 选择要对比的交易所
               - 选择要查询的交易对
               - 可选：输入API密钥获取更详细信息
            
            3. **分析数据**：
               - 查看价格对比图表
               - 分析买卖价差
               - 使用筛选和排序功能
               - 导出数据进行进一步分析
            
            ### 功能特点：
            - 🔄 实时数据更新
            - 📊 可视化图表分析
            - 🔍 灵活的筛选排序
            - 💾 数据导出功能
            - 📱 响应式设计
            """)


if __name__ == "__main__":
    main()
