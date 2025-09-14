import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import asyncio
from datetime import datetime, timedelta

from providers.cex import CEXProvider
from ui.components import display_error

# --- Tab 1: Real-time Ticker Data ---

def show_realtime_tab(providers, db_manager):
    """Displays the real-time ticker data and saves it to the DB."""
    st.header("📊 Real-time Ticker Data")

    symbols_to_fetch = st.session_state.get('selected_symbols', [])
    if not symbols_to_fetch:
        st.warning("Please select at least one symbol in the sidebar.")
        return

    all_tickers = []

    # Use a placeholder to show loading status
    placeholder = st.empty()
    placeholder.info("Fetching real-time data from all providers...")

    async def fetch_all_tickers():
        tasks = []
        for provider in providers:
            # Determine which symbols the provider should fetch
            # This is a simple check; a more robust app might map providers to symbols
            if isinstance(provider, CEXProvider):
                tasks.extend([provider.get_ticker(s) for s in symbols_to_fetch])
            elif provider.name == "Uniswap V3":
                tasks.extend([provider.get_ticker(s) for s in symbols_to_fetch if s in ['WETH/USDC', 'WBTC/WETH']])
            elif provider.name == "Thorchain":
                tasks.append(provider.get_ticker(st.session_state.bridge_symbol))

        return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(fetch_all_tickers())

    for res in results:
        if isinstance(res, dict) and 'error' not in res:
            res['provider_name'] = res.get('provider', 'N/A')
            all_tickers.append(res)

    if not all_tickers:
        placeholder.error("Could not fetch any ticker data. Check provider connections.")
        return

    df = pd.DataFrame(all_tickers)
    df = df[['provider_name', 'symbol', 'last', 'bid', 'ask', 'timestamp']]
    df = df.rename(columns={'provider_name': 'Provider', 'symbol': 'Symbol', 'last': 'Price', 'bid': 'Bid', 'ask': 'Ask'})
    df['Price'] = df['Price'].map('{:,.4f}'.format)

    placeholder.dataframe(df, use_container_width=True, hide_index=True)

    # Save data to DB if enabled
    if db_manager and st.toggle("Save data to DB", value=True):
        # Re-fetch full data for DB schema
        db_records = [t for t in all_tickers if 'error' not in t]
        if db_records:
            asyncio.run(db_manager.save_ticker_data(db_records))
            st.success(f"Saved {len(db_records)} records to the database.")

# --- Tab 2: Market Depth ---

def _create_depth_chart(order_book: dict) -> go.Figure:
    bids = pd.DataFrame(order_book.get('bids', []), columns=['price', 'volume']).astype(float)
    asks = pd.DataFrame(order_book.get('asks', []), columns=['price', 'volume']).astype(float)
    bids = bids.sort_values('price', ascending=False)
    asks = asks.sort_values('price', ascending=True)
    bids['cumulative'] = bids['volume'].cumsum()
    asks['cumulative'] = asks['volume'].cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bids['price'], y=bids['cumulative'], name='Bids', fill='tozeroy', line_color='green'))
    fig.add_trace(go.Scatter(x=asks['price'], y=asks['cumulative'], name='Asks', fill='tozeroy', line_color='red'))
    fig.update_layout(title_text=f"Market Depth for {order_book.get('symbol', '')}", xaxis_title="Price", yaxis_title="Cumulative Volume")
    return fig

def show_depth_tab(cex_providers):
    st.header("🌊 Market Depth Analysis")
    if not cex_providers:
        st.warning("Please select at least one CEX exchange in the sidebar.")
        return

    col1, col2 = st.columns(2)
    selected_exchange_name = col1.selectbox("Select Exchange", options=[p.name for p in cex_providers])
    symbol = col2.text_input("Enter Symbol", "BTC/USDT", key="depth_symbol")

    if st.button("Fetch Market Depth"):
        provider = next((p for p in cex_providers if p.name == selected_exchange_name), None)
        if not provider:
            st.error("Selected provider not found.")
            return

        with st.spinner(f"Fetching order book for {symbol} from {provider.name}..."):
            try:
                order_book = asyncio.run(provider.get_order_book(symbol, limit=50))
                if 'error' in order_book:
                    display_error(f"Could not fetch order book: {order_book['error']}")
                else:
                    st.plotly_chart(_create_depth_chart(order_book), use_container_width=True)
            except Exception as e:
                display_error(f"An error occurred: {e}")

# --- Tab 3: Arbitrage Opportunities ---

def show_arbitrage_tab(arbitrage_engine):
    st.header("⚡ Arbitrage Opportunities")
    st.info("This tab analyzes price differences across all selected providers to find profitable arbitrage opportunities, accounting for estimated fees.")

    if st.button("Find Arbitrage Opportunities"):
        with st.spinner("Analyzing all pairs and symbols..."):
            try:
                # Update engine with latest threshold from UI
                arbitrage_engine.profit_threshold = st.session_state.get('arbitrage_threshold', 0.2)

                opportunities = asyncio.run(arbitrage_engine.find_opportunities(st.session_state.selected_symbols))

                if not opportunities:
                    st.success("No profitable arbitrage opportunities found with the current settings.")
                else:
                    st.success(f"Found {len(opportunities)} arbitrage opportunities!")
                    for op in opportunities:
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Buy At", f"{op['buy_at']} @ ${op['buy_price']:,.2f}")
                        col2.metric("Sell At", f"{op['sell_at']} @ ${op['sell_price']:,.2f}")
                        col3.metric("Net Profit", f"${op['potential_profit_usd']:.2f} ({op['profit_percentage']:.2f}%)")
                        with st.expander("Show Calculation Details"):
                            st.json(op['calculation'])
            except Exception as e:
                display_error(f"An error occurred during arbitrage analysis: {e}")

# --- Tab 4: Historical Analysis ---

def show_history_tab(db_manager):
    st.header("📜 Historical Data Analysis")
    if not db_manager:
        st.warning("Database connection is not available. This feature is disabled.")
        return

    st.info("Query and visualize historical ticker data stored in the database.")

    col1, col2, col3 = st.columns(3)
    symbol = col1.text_input("Symbol", "BTC/USDT", key="history_symbol_input")
    start_date = col2.date_input("Start Date", datetime.now() - timedelta(days=1))
    end_date = col3.date_input("End Date", datetime.now())

    if st.button("Query Historical Data"):
        if not symbol:
            st.warning("Please enter a symbol.")
            return

        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        with st.spinner(f"Querying data for {symbol} from {start_date} to {end_date}..."):
            try:
                df = asyncio.run(db_manager.query_historical_data(symbol, start_datetime, end_datetime))
                if df.empty:
                    st.success("No historical data found for the selected criteria.")
                else:
                    st.dataframe(df, use_container_width=True)
                    # Create a simple price chart
                    fig = go.Figure()
                    for provider in df['provider_name'].unique():
                        provider_df = df[df['provider_name'] == provider]
                        fig.add_trace(go.Scatter(x=provider_df['timestamp'], y=provider_df['price'], mode='lines', name=provider))
                    fig.update_layout(title=f"Price History for {symbol}", xaxis_title="Timestamp", yaxis_title="Price (USD)")
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                display_error(f"An error occurred while querying the database: {e}")
