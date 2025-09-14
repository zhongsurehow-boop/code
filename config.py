import streamlit as st
import os
from dotenv import load_dotenv
import yaml

# Load environment variables from a .env file if it exists
load_dotenv()

def load_yaml_config(filepath: str) -> dict:
    """Loads a YAML file and returns its content."""
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        st.error(f"Configuration file not found: {filepath}")
        return {}
    except Exception as e:
        st.error(f"Error loading YAML configuration from {filepath}: {e}")
        return {}

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
    # Load fee structure from the external YAML file
    fee_config = load_yaml_config('fees.yml')

    config['arbitrage'] = {
        'threshold': st.session_state.get('arbitrage_threshold', 0.2), # Get from session state
        'fees': fee_config
    }

    return config
