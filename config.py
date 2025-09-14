import streamlit as st
import os
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

def load_config() -> dict:
    """
    Loads configuration from Streamlit secrets and environment variables.
    Streamlit secrets take precedence.
    """
    config = {}

    # --- Database Configuration ---
    config['db_dsn'] = st.secrets.get("database", {}).get("dsn") or os.getenv("DB_DSN")

    # --- RPC URLs for DEX Providers ---
    config['rpc_urls'] = st.secrets.get("rpc_urls", {}) or {
        "ethereum": os.getenv("RPC_URL_ETHEREUM"),
        "polygon": os.getenv("RPC_URL_POLYGON"),
    }

    # --- API Keys for CEX Providers (for authenticated endpoints) ---
    config['api_keys'] = st.secrets.get("api_keys", {}) or {
        "binance": {
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_API_SECRET"),
        },
        "coinbase": {
            "apiKey": os.getenv("COINBASE_API_KEY"),
            "secret": os.getenv("COINBASE_API_SECRET"),
        }
    }

    # --- Arbitrage Engine Settings ---
    # In a real app, this could be a more complex structure, maybe loaded from a separate YAML/JSON.
    config['arbitrage'] = {
        'threshold': st.session_state.get('arbitrage_threshold', 0.2), # Get from session state
        'fees': {
            # Default fees, can be overridden by exchange-specific fees
            'default': {'taker': 0.002, 'withdrawal_usd': 15.0},
            # Exchange-specific fees (lowercase)
            'binance': {'taker': 0.001, 'withdrawal_usd': 5.0},
            'kraken': {'taker': 0.0025, 'withdrawal_usd': 10.0},
            'coinbase': {'taker': 0.005, 'withdrawal_usd': 2.0},
            'kucoin': {'taker': 0.001, 'withdrawal_usd': 8.0},
            'okx': {'taker': 0.001, 'withdrawal_usd': 6.0},
            'uniswap v3': {'taker': 0.003, 'withdrawal_usd': 20.0}, # Approximating gas as withdrawal
            'thorchain': {'taker': 0.003, 'withdrawal_usd': 0.0}, # Fees are complex and already in quote
        }
    }

    return config
