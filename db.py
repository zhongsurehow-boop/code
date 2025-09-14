import asyncpg
import asyncio
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd

class DatabaseManager:
    """
    Manages the connection to a PostgreSQL/TimescaleDB database
    and handles all data storage and retrieval operations asynchronously.
    """
    def __init__(self, dsn: str):
        if not dsn:
            raise ValueError("Database DSN (Data Source Name) is required.")
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        """Creates and checks the connection pool to the database."""
        try:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)
            async with self.pool.acquire() as conn:
                # Test connection
                await conn.execute("SELECT 1")
            print("Database connection pool created successfully.")
        except Exception as e:
            print(f"Error: Could not connect to the database. {e}")
            self.pool = None
            raise

    async def close(self):
        """Closes the database connection pool."""
        if self.pool:
            await self.pool.close()
            print("Database connection pool closed.")

    async def init_db(self):
        """
        Initializes the database by creating the necessary tables and hypertables.
        This method is idempotent.
        """
        if not self.pool:
            raise ConnectionError("Database pool is not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Step 1: Create the main table for ticker data
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticker_data (
                    timestamp TIMESTAMPTZ NOT NULL,
                    provider_name VARCHAR(50) NOT NULL,
                    symbol VARCHAR(30) NOT NULL,
                    price DOUBLE PRECISION,
                    bid DOUBLE PRECISION,
                    ask DOUBLE PRECISION,
                    volume DOUBLE PRECISION
                );
                """)

                # Step 2: Check for TimescaleDB extension and create hypertable
                extension_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')"
                )
                if extension_exists:
                    print("TimescaleDB extension found. Creating hypertable...")
                    # This command makes the table a TimescaleDB hypertable
                    await conn.execute(
                        "SELECT create_hypertable('ticker_data', 'timestamp', if_not_exists => TRUE);"
                    )
                    # Also create the continuous aggregate view
                    await self._create_continuous_aggregates(conn)
                else:
                    print("Warning: TimescaleDB extension not found. Using standard PostgreSQL table.")
                    # Optional: Create a standard index for performance on regular PostgreSQL
                    await conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ticker_data_timestamp ON ticker_data (timestamp DESC);"
                    )
        print("Database initialization complete.")

    async def _create_continuous_aggregates(self, conn: asyncpg.Connection):
        """Creates continuous aggregates for OHLCV data."""
        print("Creating/updating continuous aggregate for 1-minute OHLCV data...")
        await conn.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1min
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 minute', timestamp) AS bucket,
                symbol,
                provider_name,
                FIRST(price, timestamp) AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                LAST(price, timestamp) AS close,
                SUM(volume) AS volume
            FROM
                ticker_data
            GROUP BY
                bucket, symbol, provider_name
            WITH NO DATA;
        """)

        # Add a policy to automatically refresh the view
        await conn.execute("""
            SELECT add_continuous_aggregate_policy(
                'ohlcv_1min',
                start_offset => INTERVAL '30 minutes',
                end_offset => INTERVAL '1 minute',
                schedule_interval => INTERVAL '1 minute'
            );
        """)


    async def save_ticker_data(self, data: List[Dict[str, Any]]):
        """
        Saves a batch of ticker data records to the database using the
        highly efficient `copy_records_to_table`.

        Args:
            data: A list of dictionaries, where each dict represents a ticker record.
                  Each dict must contain the keys: 'timestamp', 'provider_name',
                  'symbol', 'price', 'bid', 'ask', 'volume'.
        """
        if not self.pool:
            raise ConnectionError("Database pool is not initialized.")
        if not data:
            return

        records_to_insert = []
        for row in data:
            # Ensure all required fields are present, providing defaults for optional ones
            records_to_insert.append((
                row.get('timestamp', datetime.utcnow()),
                row.get('provider_name'),
                row.get('symbol'),
                row.get('price'),
                row.get('bid'),
                row.get('ask'),
                row.get('volume')
            ))

        async with self.pool.acquire() as conn:
            try:
                await conn.copy_records_to_table(
                    'ticker_data',
                    records=records_to_insert,
                    columns=[
                        'timestamp', 'provider_name', 'symbol',
                        'price', 'bid', 'ask', 'volume'
                    ]
                )
                print(f"Successfully saved {len(records_to_insert)} records to the database.")
            except Exception as e:
                print(f"Error saving data to database: {e}")

    async def query_ohlcv_data(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> pd.DataFrame:
        """Queries the 1-minute OHLCV continuous aggregate view."""
        if not self.pool:
            raise ConnectionError("Database pool is not initialized.")

        query = """
        SELECT * FROM ohlcv_1min
        WHERE symbol = $1 AND bucket BETWEEN $2 AND $3
        ORDER BY bucket ASC;
        """
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query, symbol, start_time, end_time)

        if not records:
            return pd.DataFrame()

        return pd.DataFrame(records, columns=records[0].keys())

    async def query_historical_data(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> pd.DataFrame:
        """
        Queries historical data for a given symbol and time range.

        Returns:
            A pandas DataFrame containing the queried data.
        """
        if not self.pool:
            raise ConnectionError("Database pool is not initialized.")

        query = """
        SELECT * FROM ticker_data
        WHERE symbol = $1 AND timestamp BETWEEN $2 AND $3
        ORDER BY timestamp ASC;
        """
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query, symbol, start_time, end_time)

        if not records:
            return pd.DataFrame()

        return pd.DataFrame(records, columns=records[0].keys())
