# 生产级数字货币交易所对比分析工具

这是一个高性能、可扩展、功能丰富的生产级数字货币分析工具。它集成了多个数据源（中心化交易所、去中心化交易所、跨链桥），提供实时行情、市场深度、套利机会发现和历史数据分析等高级功能。

## 核心功能

- **多数据源集成**:
  - **CEX**: 通过 `ccxt.pro` 的 WebSocket 实时获取多个主流交易所（如 Binance, Coinbase）的行情和订单簿数据。
  - **DEX**: 通过 `web3.py` 连接以太坊节点，实时计算 Uniswap V3 流动性池的价格。
  - **跨链桥**: 通过 `httpx` 调用 Thorchain 的 API 获取跨链交易的实时报价。
- **实时数据流**: 全面采用异步I/O (`asyncio`) 和 WebSocket，告别传统轮询，实现毫秒级数据更新。
- **高级分析引擎**:
  - **市场深度分析**: 动态、交互式地展示所选交易对的市场深度图，清晰揭示买卖盘的累积深度。
  - **跨平台套利**: 内置套利引擎，能实时分析多个平台间的价差，并精确计算扣除交易和提现手续费后的净利润率。
- **数据持久化**:
  - 使用 `asyncpg` 与 `PostgreSQL/TimescaleDB` 高效集成，将实时行情数据持久化存储。
  - 专为时间序列数据优化的表结构，并利用 TimescaleDB 的连续聚合功能自动生成分钟级K线数据，极大提升历史查询性能。
- **现代化Web界面**:
  - 基于 `Streamlit` 构建，界面清晰、交互友好。
  - 使用标签页（Tabs）将不同功能模块（实时行情、市场深度、套利机会、历史分析）清晰地分隔开。
  - 支持UI自动刷新，提供实时的数据看板体验。
- **容器化部署**:
  - 提供 `Dockerfile` 和 `docker-compose.yml`，支持一键启动整个应用（包括数据库），实现环境一致性和部署便利性。

## 技术架构与原理

本项目采用模块化的架构，将不同的业务关注点分离到独立的模块中，保证了代码的高内聚、低耦合，易于维护和扩展。

### 文件结构

```
.
├── app.py                  # Streamlit 应用主入口
├── config.py               # 配置加载模块
├── db.py                   # 数据库管理器 (DatabaseManager)
├── engine.py               # 套利引擎 (ArbitrageEngine)
├── fees.yml                # 外部化的手续费配置文件
├── providers/              # 数据提供者模块
│   ├── base.py             # Provider 抽象基类
│   ├── cex.py              # CEX 数据提供者 (ccxt.pro)
│   ├── dex.py              # DEX 数据提供者 (web3.py)
│   └── bridge.py           # 跨链桥数据提供者 (httpx)
├── ui/                     # UI 组件模块
│   ├── components.py       # 侧边栏等可复用组件
│   └── tabs.py             # 各个功能标签页的实现
├── tests/                  # 测试套件目录
│   └── test_engine.py      # 对套利引擎的单元测试
├── Dockerfile              # 用于构建应用镜像
├── docker-compose.yml      # 用于编排应用和数据库服务
├── requirements.txt        # Python 依赖列表
└── .env.example            # 环境变量模板文件
```

### 工作原理

1.  **启动**: `docker-compose up` 命令会同时启动 `app` 和 `db` 两个服务。
2.  **UI渲染**: 用户访问 `http://localhost:8501`，`app.py` 开始执行。它会加载配置，初始化数据库连接池和所有数据提供者。
3.  **数据获取**:
    - 当用户在 "实时行情" 或 "套利机会" 标签页时，`app.py` 会调用所有 `Provider` 的异步方法。
    - `asyncio.gather` 会并发地向所有交易所和API发送数据请求。
    - `CEXProvider` 通过持久化的 WebSocket 连接接收实时推送。
    - `DEXProvider` 和 `BridgeProvider` 通过异步HTTP请求获取数据。
4.  **数据处理与分析**:
    - 获取到的数据被送入 `ArbitrageEngine` 进行分析，计算潜在的套利机会。
    - 实时数据被展示在UI上，并可选择存入 TimescaleDB。
5.  **用户交互**: 用户在侧边栏的所有操作都会更新 `st.session_state`，应用会响应式地更新数据和视图。如果开启了自动刷新，应用会定时自动重新获取和展示数据。

## 本地运行指南

本项目被设计为通过 Docker 运行，这是最简单、最可靠的方式。

### 环境准备

-   [Docker](https://www.docker.com/products/docker-desktop/)
-   [Docker Compose](https://docs.docker.com/compose/install/) (通常随 Docker Desktop 一起安装)

### 操作步骤

1.  **克隆项目**
    ```bash
    git clone <your-repo-url>
    cd <project-directory>
    ```

2.  **创建并配置环境变量文件**
    -   将 `.env.example` 文件复制一份，并重命名为 `.env`。
        ```bash
        cp .env.example .env
        ```
    -   打开 `.env` 文件，至少需要配置以下项：
        -   `RPC_URL_ETHEREUM`: 您的以太坊主网 RPC URL，用于 `DEXProvider`。您可以从 [Infura](https://infura.io/) 或 [Alchemy](https://www.alchemy.com/) 等服务获取。
        -   `BINANCE_API_KEY`, `BINANCE_API_SECRET` 等 (可选): 如果您需要使用交易所的认证接口，可以填入您的 API 密钥。

3.  **启动应用**
    -   在项目根目录下，运行以下命令来构建并启动所有服务：
        ```bash
        docker-compose up --build
        ```
    -   第一次启动时，`--build` 参数会根据 `Dockerfile` 构建应用镜像，这可能需要几分钟时间。后续启动不再需要此参数，除非您修改了 `Dockerfile` 或 `requirements.txt`。

4.  **访问应用**
    -   打开您的浏览器，访问 `http://localhost:8501`。
    -   您应该能看到应用的界面。数据库服务也在后台运行。

## 如何运行测试

测试套件用于验证核心业务逻辑（如套利计算）的正确性。

-   您可以在 `docker-compose.yml` 运行的情况下，打开一个新的终端，并执行以下命令来进入 `app` 容器并运行测试：
    ```bash
    docker-compose exec app sh -c "PYTHONPATH=. pytest"
    ```

## 配置文件说明

### `.env` 文件

此文件用于存储所有敏感信息和环境特定的配置。

-   `POSTGRES_*`: 这些变量用于初始化 `db` 服务中的数据库。
-   `DB_DSN`: 应用连接到数据库所使用的数据源名称。**请注意**，在 Docker 环境中，主机名是 `db`，而不是 `localhost`。
-   `RPC_URL_*`: 各个区块链的 RPC 节点 URL。
-   `*_API_KEY`, `*_API_SECRET`: CEX 交易所的 API 密钥。

### `fees.yml` 文件

此文件用于集中管理套利引擎所需的手续费配置，方便随时调整而无需修改代码。

-   `default`: 为未在文件中明确列出的任何交易所提供默认的 `taker` (吃单)费率和 `withdrawal_fees` (提现费率)。
-   **交易所特定配置**: 您可以为每个交易所（使用小写名称）单独定义其手续费结构。
-   `withdrawal_fees`: 定义了按特定资产（如 `BTC`, `ETH`）收取的提现费用。这比固定的美元费用更精确。
