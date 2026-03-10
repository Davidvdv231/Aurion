from __future__ import annotations

from typing import Any, Literal

AssetType = Literal["stock", "crypto"]
TickerRow = dict[str, Any]

STOCK_TICKER_CATALOG: list[TickerRow] = [
    {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "region": "US", "popularity": 1000, "asset_type": "stock"},
    {"symbol": "MSFT", "name": "Microsoft", "exchange": "NASDAQ", "region": "US", "popularity": 995, "asset_type": "stock"},
    {"symbol": "NVDA", "name": "NVIDIA", "exchange": "NASDAQ", "region": "US", "popularity": 990, "asset_type": "stock"},
    {"symbol": "AMZN", "name": "Amazon", "exchange": "NASDAQ", "region": "US", "popularity": 980, "asset_type": "stock"},
    {"symbol": "GOOGL", "name": "Alphabet Class A", "exchange": "NASDAQ", "region": "US", "popularity": 970, "asset_type": "stock"},
    {"symbol": "META", "name": "Meta Platforms", "exchange": "NASDAQ", "region": "US", "popularity": 965, "asset_type": "stock"},
    {"symbol": "TSLA", "name": "Tesla", "exchange": "NASDAQ", "region": "US", "popularity": 960, "asset_type": "stock"},
    {"symbol": "AVGO", "name": "Broadcom", "exchange": "NASDAQ", "region": "US", "popularity": 950, "asset_type": "stock"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "exchange": "NASDAQ", "region": "US", "popularity": 945, "asset_type": "stock"},
    {"symbol": "NFLX", "name": "Netflix", "exchange": "NASDAQ", "region": "US", "popularity": 930, "asset_type": "stock"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "exchange": "NYSEARCA", "region": "US", "popularity": 920, "asset_type": "stock"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "exchange": "NASDAQ", "region": "US", "popularity": 910, "asset_type": "stock"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway Class B", "exchange": "NYSE", "region": "US", "popularity": 900, "asset_type": "stock"},
    {"symbol": "JPM", "name": "JPMorgan Chase", "exchange": "NYSE", "region": "US", "popularity": 890, "asset_type": "stock"},
    {"symbol": "V", "name": "Visa", "exchange": "NYSE", "region": "US", "popularity": 885, "asset_type": "stock"},
    {"symbol": "MA", "name": "Mastercard", "exchange": "NYSE", "region": "US", "popularity": 880, "asset_type": "stock"},
    {"symbol": "ASML", "name": "ASML Holding", "exchange": "NASDAQ", "region": "NL", "popularity": 875, "asset_type": "stock"},
    {"symbol": "XOM", "name": "Exxon Mobil", "exchange": "NYSE", "region": "US", "popularity": 870, "asset_type": "stock"},
    {"symbol": "WMT", "name": "Walmart", "exchange": "NYSE", "region": "US", "popularity": 865, "asset_type": "stock"},
    {"symbol": "COST", "name": "Costco", "exchange": "NASDAQ", "region": "US", "popularity": 860, "asset_type": "stock"},
    {"symbol": "ASML.AS", "name": "ASML Holding", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 858, "asset_type": "stock"},
    {"symbol": "UNH", "name": "UnitedHealth", "exchange": "NYSE", "region": "US", "popularity": 855, "asset_type": "stock"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "exchange": "NYSE", "region": "US", "popularity": 850, "asset_type": "stock"},
    {"symbol": "INGA.AS", "name": "ING Groep", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 845, "asset_type": "stock"},
    {"symbol": "KO", "name": "Coca-Cola", "exchange": "NYSE", "region": "US", "popularity": 842, "asset_type": "stock"},
    {"symbol": "KBC.BR", "name": "KBC Group", "exchange": "Euronext Brussels", "region": "BE", "popularity": 840, "asset_type": "stock"},
    {"symbol": "HEIA.AS", "name": "Heineken", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 835, "asset_type": "stock"},
    {"symbol": "UCB.BR", "name": "UCB", "exchange": "Euronext Brussels", "region": "BE", "popularity": 830, "asset_type": "stock"},
    {"symbol": "ABI.BR", "name": "AB InBev", "exchange": "Euronext Brussels", "region": "BE", "popularity": 825, "asset_type": "stock"},
    {"symbol": "ADYEN.AS", "name": "Adyen", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 820, "asset_type": "stock"},
    {"symbol": "INTC", "name": "Intel", "exchange": "NASDAQ", "region": "US", "popularity": 815, "asset_type": "stock"},
    {"symbol": "PLTR", "name": "Palantir", "exchange": "NASDAQ", "region": "US", "popularity": 810, "asset_type": "stock"},
    {"symbol": "UBER", "name": "Uber Technologies", "exchange": "NYSE", "region": "US", "popularity": 805, "asset_type": "stock"},
    {"symbol": "SAP.DE", "name": "SAP", "exchange": "XETRA", "region": "DE", "popularity": 800, "asset_type": "stock"},
    {"symbol": "AIR.PA", "name": "Airbus", "exchange": "Euronext Paris", "region": "FR", "popularity": 795, "asset_type": "stock"},
    {"symbol": "SHELL.AS", "name": "Shell plc", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 790, "asset_type": "stock"},
    {"symbol": "PRX.AS", "name": "Prosus", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 785, "asset_type": "stock"},
    {"symbol": "SOFI", "name": "SoFi Technologies", "exchange": "NASDAQ", "region": "US", "popularity": 780, "asset_type": "stock"},
    {"symbol": "K", "name": "Kellanova", "exchange": "NYSE", "region": "US", "popularity": 730, "asset_type": "stock"},
    {"symbol": "KHC", "name": "Kraft Heinz", "exchange": "NASDAQ", "region": "US", "popularity": 700, "asset_type": "stock"},
    {"symbol": "KVUE", "name": "Kenvue", "exchange": "NYSE", "region": "US", "popularity": 690, "asset_type": "stock"},
    {"symbol": "KMI", "name": "Kinder Morgan", "exchange": "NYSE", "region": "US", "popularity": 685, "asset_type": "stock"},
    {"symbol": "KB", "name": "KB Financial Group ADR", "exchange": "NYSE", "region": "KR", "popularity": 665, "asset_type": "stock"},
    {"symbol": "KBH", "name": "KB Home", "exchange": "NYSE", "region": "US", "popularity": 650, "asset_type": "stock"},
    {"symbol": "KBWB", "name": "Invesco KBW Bank ETF", "exchange": "NASDAQ", "region": "US", "popularity": 615, "asset_type": "stock"},
]

CRYPTO_TICKER_CATALOG: list[TickerRow] = [
    {"symbol": "BTC-USD", "name": "Bitcoin", "exchange": "Crypto", "region": "GLOBAL", "popularity": 1000, "asset_type": "crypto"},
    {"symbol": "ETH-USD", "name": "Ethereum", "exchange": "Crypto", "region": "GLOBAL", "popularity": 980, "asset_type": "crypto"},
    {"symbol": "XRP-USD", "name": "XRP", "exchange": "Crypto", "region": "GLOBAL", "popularity": 940, "asset_type": "crypto"},
    {"symbol": "BNB-USD", "name": "BNB", "exchange": "Crypto", "region": "GLOBAL", "popularity": 930, "asset_type": "crypto"},
    {"symbol": "SOL-USD", "name": "Solana", "exchange": "Crypto", "region": "GLOBAL", "popularity": 920, "asset_type": "crypto"},
    {"symbol": "ADA-USD", "name": "Cardano", "exchange": "Crypto", "region": "GLOBAL", "popularity": 900, "asset_type": "crypto"},
    {"symbol": "DOGE-USD", "name": "Dogecoin", "exchange": "Crypto", "region": "GLOBAL", "popularity": 890, "asset_type": "crypto"},
    {"symbol": "TRX-USD", "name": "TRON", "exchange": "Crypto", "region": "GLOBAL", "popularity": 870, "asset_type": "crypto"},
    {"symbol": "AVAX-USD", "name": "Avalanche", "exchange": "Crypto", "region": "GLOBAL", "popularity": 860, "asset_type": "crypto"},
    {"symbol": "LINK-USD", "name": "Chainlink", "exchange": "Crypto", "region": "GLOBAL", "popularity": 850, "asset_type": "crypto"},
    {"symbol": "DOT-USD", "name": "Polkadot", "exchange": "Crypto", "region": "GLOBAL", "popularity": 840, "asset_type": "crypto"},
    {"symbol": "LTC-USD", "name": "Litecoin", "exchange": "Crypto", "region": "GLOBAL", "popularity": 830, "asset_type": "crypto"},
    {"symbol": "BCH-USD", "name": "Bitcoin Cash", "exchange": "Crypto", "region": "GLOBAL", "popularity": 820, "asset_type": "crypto"},
    {"symbol": "SHIB-USD", "name": "Shiba Inu", "exchange": "Crypto", "region": "GLOBAL", "popularity": 810, "asset_type": "crypto"},
    {"symbol": "XLM-USD", "name": "Stellar", "exchange": "Crypto", "region": "GLOBAL", "popularity": 800, "asset_type": "crypto"},
    {"symbol": "NEAR-USD", "name": "NEAR Protocol", "exchange": "Crypto", "region": "GLOBAL", "popularity": 790, "asset_type": "crypto"},
    {"symbol": "ATOM-USD", "name": "Cosmos", "exchange": "Crypto", "region": "GLOBAL", "popularity": 780, "asset_type": "crypto"},
    {"symbol": "UNI-USD", "name": "Uniswap", "exchange": "Crypto", "region": "GLOBAL", "popularity": 770, "asset_type": "crypto"},
    {"symbol": "APT-USD", "name": "Aptos", "exchange": "Crypto", "region": "GLOBAL", "popularity": 760, "asset_type": "crypto"},
    {"symbol": "FIL-USD", "name": "Filecoin", "exchange": "Crypto", "region": "GLOBAL", "popularity": 750, "asset_type": "crypto"},
]

TICKER_CATALOG: list[TickerRow] = [*STOCK_TICKER_CATALOG, *CRYPTO_TICKER_CATALOG]

STOCK_EXACT_ALIASES: dict[str, str] = {
    "HEIAA": "HEIA.AS",
    "INGA": "INGA.AS",
    "KBC": "KBC.BR",
    "ABI": "ABI.BR",
}

CRYPTO_EXACT_ALIASES: dict[str, str] = {
    "BTC": "BTC-USD",
    "XBT": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
}

EXACT_ALIASES: dict[str, str] = {**STOCK_EXACT_ALIASES, **CRYPTO_EXACT_ALIASES}


def _normalize(text: str) -> str:
    return "".join(ch for ch in text.upper().strip() if ch.isalnum() or ch in ".-")


def _clean_for_match(text: str) -> str:
    return text.replace(".", "").replace("-", "")


def _to_payload(row: TickerRow, score: int | None = None) -> TickerRow:
    payload: TickerRow = {
        "symbol": row["symbol"],
        "name": row["name"],
        "exchange": row["exchange"],
        "region": row["region"],
        "popularity": row["popularity"],
        "asset_type": row["asset_type"],
    }
    if score is not None:
        payload["score"] = score
    return payload


def _catalog_for(asset_type: AssetType) -> list[TickerRow]:
    return STOCK_TICKER_CATALOG if asset_type == "stock" else CRYPTO_TICKER_CATALOG


def _aliases_for(asset_type: AssetType) -> dict[str, str]:
    return STOCK_EXACT_ALIASES if asset_type == "stock" else CRYPTO_EXACT_ALIASES


def get_ticker_metadata(symbol: str, asset_type: AssetType = "stock") -> TickerRow | None:
    normalized = _normalize(symbol)
    if not normalized:
        return None

    alias = _aliases_for(asset_type).get(normalized, normalized)
    for row in _catalog_for(asset_type):
        if row["symbol"].upper() == alias:
            return _to_payload(row)
    return None


def search_tickers(query: str, limit: int = 20, asset_type: AssetType = "stock") -> list[TickerRow]:
    normalized = _normalize(query)
    catalog = _catalog_for(asset_type)

    if not normalized:
        return top_catalog_tickers(limit=limit, asset_type=asset_type)

    normalized = _aliases_for(asset_type).get(normalized, normalized)
    clean_query = _clean_for_match(normalized)
    ranked: list[tuple[int, TickerRow]] = []

    for row in catalog:
        symbol = row["symbol"].upper()
        clean_symbol = _clean_for_match(symbol)
        name = row["name"].upper()

        score = row["popularity"]

        if symbol.startswith(normalized):
            score += 1000
        elif clean_symbol.startswith(clean_query):
            score += 950
        elif normalized in symbol:
            score += 700
        elif clean_query in clean_symbol:
            score += 650
        elif normalized in name:
            score += 350
        else:
            continue

        score -= max(0, len(symbol) - len(normalized)) * 3
        ranked.append((score, row))

    ranked.sort(key=lambda item: (-item[0], -item[1]["popularity"], item[1]["symbol"]))
    return [_to_payload(row, score) for score, row in ranked[:limit]]


def top_catalog_tickers(limit: int = 10, asset_type: AssetType = "stock") -> list[TickerRow]:
    catalog = _catalog_for(asset_type)
    ranked = sorted(catalog, key=lambda item: (-item["popularity"], item["symbol"]))
    return [_to_payload(row) for row in ranked[:limit]]
