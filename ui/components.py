import streamlit as st

def sidebar_controls():
    """
    Defines the controls in the sidebar and updates session_state.
    The main app will react to changes in st.session_state.
    """
    st.sidebar.header("⚙️ Configuration")

    # --- Exchange Selection ---
    st.sidebar.multiselect(
        "Select CEX Exchanges",
        options=['binance', 'coinbase', 'kraken', 'kucoin', 'okx', 'bybit', 'gate', 'mexc', 'bitget', 'bitfinex', 'htx'],
        default=['binance', 'kraken'],
        key='selected_exchanges', # This key links the widget to session_state
        help="Select Centralized Exchanges for ticker and arbitrage analysis."
    )

    # --- Symbol Selection ---
    st.sidebar.multiselect(
        "Select CEX/DEX Symbols",
        options=['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ETH/BTC', 'WETH/USDC', 'WBTC/WETH'],
        default=['BTC/USDT', 'ETH/USDT'],
        key='selected_symbols',
        help="Select symbols to track across exchanges."
    )

    # --- Bridge Symbol Selection ---
    st.sidebar.text_input(
        "Bridge Swap Pair",
        value='BTC.BTC/ETH.ETH',
        key='bridge_symbol',
        help="Enter a cross-chain pair for Thorchain, e.g., 'BTC.BTC/ETH.ETH'."
    )

    # --- Arbitrage Settings ---
    st.sidebar.subheader("Arbitrage Settings")
    st.sidebar.number_input(
        "Profit Threshold (%)",
        min_value=0.01,
        max_value=10.0,
        value=0.2,
        step=0.01,
        key='arbitrage_threshold',
        help="Set the minimum profit percentage to trigger an alert."
    )

    # --- Refresh Control ---
    st.sidebar.subheader("Display Control")
    if st.sidebar.button("🔄 Force Refresh All Data"):
        # Clearing cached resources will force them to rerun
        st.cache_resource.clear()
        st.rerun()

    st.sidebar.toggle("Auto-Refresh", key='auto_refresh_enabled', value=False)
    st.sidebar.number_input(
        "Refresh Interval (s)",
        min_value=5,
        max_value=120,
        value=10,
        step=5,
        key='auto_refresh_interval',
        disabled=not st.session_state.get('auto_refresh_enabled', False)
    )

def display_error(message: str):
    """A standardized way to display errors."""
    st.error(message, icon="🚨")

def display_warning(message: str):
    """A standardized way to display warnings."""
    st.warning(message, icon="⚠️")
