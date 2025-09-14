import streamlit as st
import asyncio
import nest_asyncio
import time

from config import load_config
from db import DatabaseManager
from engine import ArbitrageEngine
from providers.cex import CEXProvider
from providers.dex import DEXProvider
from providers.bridge import BridgeProvider
from ui.tabs import show_realtime_tab, show_depth_tab, show_arbitrage_tab, show_history_tab
from ui.components import sidebar_controls

# Apply nest_asyncio to allow running asyncio event loops within Streamlit's loop
# This is crucial for integrating async libraries with Streamlit
nest_asyncio.apply()

st.set_page_config(
    page_title="数字货币交易所对比工具 (生产级)",
    layout="wide",
    page_icon="🚀",
    initial_sidebar_state="expanded"
)

# --- App Title ---
st.markdown("<h1>🚀 数字货币交易所对比工具 (生产级)</h1>", unsafe_allow_html=True)

# --- Initialization & Caching ---

@st.cache_data
def get_config():
    """Load configuration from file and cache it."""
    return load_config()

@st.cache_resource
def get_db_manager(dsn):
    """Create and cache the database manager and its connection pool."""
    if not dsn:
        st.warning("Database DSN not configured. Historical analysis will be disabled.")
        return None
    try:
        db_manager = DatabaseManager(dsn)
        asyncio.run(db_manager.connect())
        asyncio.run(db_manager.init_db())
        return db_manager
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

@st.cache_resource
def get_providers(_config):
    """Create and cache a list of all data providers."""
    providers = []
    # CEX Providers
    for ex_id in st.session_state.selected_exchanges:
        providers.append(CEXProvider(name=ex_id, config=_config))
    # DEX Providers
    if _config.get('rpc_urls', {}).get('ethereum'):
        providers.append(DEXProvider(name="Uniswap V3", rpc_url=_config['rpc_urls']['ethereum']))
    # Bridge Providers
    providers.append(BridgeProvider(name="Thorchain"))

    return providers

def init_session_state():
    """Initializes the session state with default values."""
    if 'selected_exchanges' not in st.session_state:
        st.session_state.selected_exchanges = ['binance', 'kraken']
    if 'selected_symbols' not in st.session_state:
        st.session_state.selected_symbols = ['BTC/USDT', 'ETH/USDT']
    if 'bridge_symbol' not in st.session_state:
        st.session_state.bridge_symbol = 'BTC.BTC/ETH.ETH'
    if 'dex_symbol' not in st.session_state:
        st.session_state.dex_symbol = 'WETH/USDC'

# --- Main App Logic ---
def main():
    # Load config and initialize state
    config = get_config()
    init_session_state()

    # Initialize managers
    db_manager = get_db_manager(config.get("db_dsn"))

    # Sidebar for user controls
    sidebar_controls()

    # Get providers based on current selection in session state
    providers = get_providers(config)

    # Initialize arbitrage engine
    arbitrage_engine = ArbitrageEngine(providers, config.get('arbitrage', {}))

    # Main content area with tabs
    tab_names = ["实时行情", "市场深度", "套利机会", "历史分析"]
    tab1, tab2, tab3, tab4 = st.tabs(tab_names)

    with tab1:
        show_realtime_tab(providers, db_manager)

    with tab2:
        # Pass only CEX providers to the depth tab
        cex_providers = [p for p in providers if isinstance(p, CEXProvider)]
        show_depth_tab(cex_providers)

    with tab3:
        show_arbitrage_tab(arbitrage_engine)

    with tab4:
        show_history_tab(db_manager)


if __name__ == "__main__":
    main()

    # --- Auto-refresh loop ---
    if st.session_state.get('auto_refresh_enabled', False):
        interval = st.session_state.get('auto_refresh_interval', 10)
        time.sleep(interval)
        st.rerun()
