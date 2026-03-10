from __future__ import annotations

from typing import Any

TickerRow = dict[str, Any]

TICKER_CATALOG: list[TickerRow] = [
    {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "region": "US", "popularity": 1000},
    {"symbol": "MSFT", "name": "Microsoft", "exchange": "NASDAQ", "region": "US", "popularity": 995},
    {"symbol": "NVDA", "name": "NVIDIA", "exchange": "NASDAQ", "region": "US", "popularity": 990},
    {"symbol": "AMZN", "name": "Amazon", "exchange": "NASDAQ", "region": "US", "popularity": 980},
    {"symbol": "GOOGL", "name": "Alphabet Class A", "exchange": "NASDAQ", "region": "US", "popularity": 970},
    {"symbol": "META", "name": "Meta Platforms", "exchange": "NASDAQ", "region": "US", "popularity": 965},
    {"symbol": "TSLA", "name": "Tesla", "exchange": "NASDAQ", "region": "US", "popularity": 960},
    {"symbol": "AVGO", "name": "Broadcom", "exchange": "NASDAQ", "region": "US", "popularity": 950},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "exchange": "NASDAQ", "region": "US", "popularity": 945},
    {"symbol": "NFLX", "name": "Netflix", "exchange": "NASDAQ", "region": "US", "popularity": 930},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "exchange": "NYSEARCA", "region": "US", "popularity": 920},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "exchange": "NASDAQ", "region": "US", "popularity": 910},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway Class B", "exchange": "NYSE", "region": "US", "popularity": 900},
    {"symbol": "JPM", "name": "JPMorgan Chase", "exchange": "NYSE", "region": "US", "popularity": 890},
    {"symbol": "V", "name": "Visa", "exchange": "NYSE", "region": "US", "popularity": 885},
    {"symbol": "MA", "name": "Mastercard", "exchange": "NYSE", "region": "US", "popularity": 880},
    {"symbol": "XOM", "name": "Exxon Mobil", "exchange": "NYSE", "region": "US", "popularity": 870},
    {"symbol": "WMT", "name": "Walmart", "exchange": "NYSE", "region": "US", "popularity": 865},
    {"symbol": "COST", "name": "Costco", "exchange": "NASDAQ", "region": "US", "popularity": 860},
    {"symbol": "UNH", "name": "UnitedHealth", "exchange": "NYSE", "region": "US", "popularity": 855},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "exchange": "NYSE", "region": "US", "popularity": 850},
    {"symbol": "KO", "name": "Coca-Cola", "exchange": "NYSE", "region": "US", "popularity": 845},
    {"symbol": "PEP", "name": "PepsiCo", "exchange": "NASDAQ", "region": "US", "popularity": 840},
    {"symbol": "ORCL", "name": "Oracle", "exchange": "NYSE", "region": "US", "popularity": 835},
    {"symbol": "CRM", "name": "Salesforce", "exchange": "NYSE", "region": "US", "popularity": 830},
    {"symbol": "ADBE", "name": "Adobe", "exchange": "NASDAQ", "region": "US", "popularity": 825},
    {"symbol": "INTC", "name": "Intel", "exchange": "NASDAQ", "region": "US", "popularity": 820},
    {"symbol": "MU", "name": "Micron Technology", "exchange": "NASDAQ", "region": "US", "popularity": 815},
    {"symbol": "PLTR", "name": "Palantir", "exchange": "NASDAQ", "region": "US", "popularity": 810},
    {"symbol": "SMCI", "name": "Super Micro Computer", "exchange": "NASDAQ", "region": "US", "popularity": 805},
    {"symbol": "UBER", "name": "Uber Technologies", "exchange": "NYSE", "region": "US", "popularity": 800},
    {"symbol": "DIS", "name": "The Walt Disney Company", "exchange": "NYSE", "region": "US", "popularity": 795},
    {"symbol": "NKE", "name": "Nike", "exchange": "NYSE", "region": "US", "popularity": 790},
    {"symbol": "PFE", "name": "Pfizer", "exchange": "NYSE", "region": "US", "popularity": 785},
    {"symbol": "PYPL", "name": "PayPal", "exchange": "NASDAQ", "region": "US", "popularity": 780},
    {"symbol": "SNOW", "name": "Snowflake", "exchange": "NYSE", "region": "US", "popularity": 775},
    {"symbol": "BA", "name": "Boeing", "exchange": "NYSE", "region": "US", "popularity": 770},
    {"symbol": "F", "name": "Ford Motor Company", "exchange": "NYSE", "region": "US", "popularity": 765},
    {"symbol": "GM", "name": "General Motors", "exchange": "NYSE", "region": "US", "popularity": 760},
    {"symbol": "BABA", "name": "Alibaba", "exchange": "NYSE", "region": "US", "popularity": 755},
    {"symbol": "TSM", "name": "Taiwan Semiconductor ADR", "exchange": "NYSE", "region": "US", "popularity": 750},
    {"symbol": "SAP", "name": "SAP ADR", "exchange": "NYSE", "region": "US", "popularity": 745},
    {"symbol": "SOFI", "name": "SoFi Technologies", "exchange": "NASDAQ", "region": "US", "popularity": 740},
    {"symbol": "RIVN", "name": "Rivian Automotive", "exchange": "NASDAQ", "region": "US", "popularity": 735},
    {"symbol": "MRNA", "name": "Moderna", "exchange": "NASDAQ", "region": "US", "popularity": 730},
    {"symbol": "COIN", "name": "Coinbase", "exchange": "NASDAQ", "region": "US", "popularity": 725},
    {"symbol": "SHOP", "name": "Shopify", "exchange": "NYSE", "region": "US", "popularity": 720},
    {"symbol": "BAC", "name": "Bank of America", "exchange": "NYSE", "region": "US", "popularity": 715},
    {"symbol": "C", "name": "Citigroup", "exchange": "NYSE", "region": "US", "popularity": 710},
    {"symbol": "GS", "name": "Goldman Sachs", "exchange": "NYSE", "region": "US", "popularity": 705},
    {"symbol": "MS", "name": "Morgan Stanley", "exchange": "NYSE", "region": "US", "popularity": 700},
    {"symbol": "ASML", "name": "ASML Holding", "exchange": "NASDAQ", "region": "NL", "popularity": 880},
    {"symbol": "ASML.AS", "name": "ASML Holding", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 860},
    {"symbol": "INGA.AS", "name": "ING Groep", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 845},
    {"symbol": "HEIA.AS", "name": "Heineken", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 835},
    {"symbol": "ADYEN.AS", "name": "Adyen", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 830},
    {"symbol": "PRX.AS", "name": "Prosus", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 825},
    {"symbol": "SHELL.AS", "name": "Shell plc", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 820},
    {"symbol": "KPN.AS", "name": "KPN", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 795},
    {"symbol": "PHIA.AS", "name": "Philips", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 790},
    {"symbol": "ASRNL.AS", "name": "ASR Nederland", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 785},
    {"symbol": "NN.AS", "name": "NN Group", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 780},
    {"symbol": "RAND.AS", "name": "Randstad", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 775},
    {"symbol": "AKZA.AS", "name": "Akzo Nobel", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 770},
    {"symbol": "UMG.AS", "name": "Universal Music Group", "exchange": "Euronext Amsterdam", "region": "NL", "popularity": 765},
    {"symbol": "KBC.BR", "name": "KBC Group", "exchange": "Euronext Brussels", "region": "BE", "popularity": 840},
    {"symbol": "ABI.BR", "name": "AB InBev", "exchange": "Euronext Brussels", "region": "BE", "popularity": 830},
    {"symbol": "UCB.BR", "name": "UCB", "exchange": "Euronext Brussels", "region": "BE", "popularity": 825},
    {"symbol": "SOLB.BR", "name": "Solvay", "exchange": "Euronext Brussels", "region": "BE", "popularity": 805},
    {"symbol": "GBLB.BR", "name": "Groupe Bruxelles Lambert", "exchange": "Euronext Brussels", "region": "BE", "popularity": 800},
    {"symbol": "COLR.BR", "name": "Colruyt", "exchange": "Euronext Brussels", "region": "BE", "popularity": 790},
    {"symbol": "ELI.BR", "name": "Elia Group", "exchange": "Euronext Brussels", "region": "BE", "popularity": 780},
    {"symbol": "ACKB.BR", "name": "Ackermans & van Haaren", "exchange": "Euronext Brussels", "region": "BE", "popularity": 770},
    {"symbol": "DIE.BR", "name": "D'Ieteren Group", "exchange": "Euronext Brussels", "region": "BE", "popularity": 765},
    {"symbol": "BPOST.BR", "name": "bpost", "exchange": "Euronext Brussels", "region": "BE", "popularity": 740},
    {"symbol": "SAP.DE", "name": "SAP", "exchange": "XETRA", "region": "DE", "popularity": 835},
    {"symbol": "SIE.DE", "name": "Siemens", "exchange": "XETRA", "region": "DE", "popularity": 810},
    {"symbol": "ALV.DE", "name": "Allianz", "exchange": "XETRA", "region": "DE", "popularity": 805},
    {"symbol": "BMW.DE", "name": "BMW", "exchange": "XETRA", "region": "DE", "popularity": 790},
    {"symbol": "MBG.DE", "name": "Mercedes-Benz Group", "exchange": "XETRA", "region": "DE", "popularity": 785},
    {"symbol": "VOW3.DE", "name": "Volkswagen Pref", "exchange": "XETRA", "region": "DE", "popularity": 775},
    {"symbol": "AIR.PA", "name": "Airbus", "exchange": "Euronext Paris", "region": "FR", "popularity": 820},
    {"symbol": "MC.PA", "name": "LVMH", "exchange": "Euronext Paris", "region": "FR", "popularity": 815},
    {"symbol": "RMS.PA", "name": "Hermes", "exchange": "Euronext Paris", "region": "FR", "popularity": 810},
    {"symbol": "OR.PA", "name": "L'Oreal", "exchange": "Euronext Paris", "region": "FR", "popularity": 795},
    {"symbol": "SAN.PA", "name": "Sanofi", "exchange": "Euronext Paris", "region": "FR", "popularity": 790},
    {"symbol": "BNP.PA", "name": "BNP Paribas", "exchange": "Euronext Paris", "region": "FR", "popularity": 780},
    {"symbol": "TTE.PA", "name": "TotalEnergies", "exchange": "Euronext Paris", "region": "FR", "popularity": 775},
    {"symbol": "AI.PA", "name": "Air Liquide", "exchange": "Euronext Paris", "region": "FR", "popularity": 770},
    {"symbol": "SHEL.L", "name": "Shell plc", "exchange": "LSE", "region": "UK", "popularity": 780},
    {"symbol": "AZN.L", "name": "AstraZeneca", "exchange": "LSE", "region": "UK", "popularity": 770},
    {"symbol": "HSBA.L", "name": "HSBC", "exchange": "LSE", "region": "UK", "popularity": 760},
    {"symbol": "BP.L", "name": "BP", "exchange": "LSE", "region": "UK", "popularity": 750},
    {"symbol": "RIO.L", "name": "Rio Tinto", "exchange": "LSE", "region": "UK", "popularity": 740},
    {"symbol": "SHOP.TO", "name": "Shopify", "exchange": "TSX", "region": "CA", "popularity": 760},
    {"symbol": "RY.TO", "name": "Royal Bank of Canada", "exchange": "TSX", "region": "CA", "popularity": 750},
    {"symbol": "TD.TO", "name": "Toronto-Dominion Bank", "exchange": "TSX", "region": "CA", "popularity": 745},
    {"symbol": "ENB.TO", "name": "Enbridge", "exchange": "TSX", "region": "CA", "popularity": 730},
    {"symbol": "BNS.TO", "name": "Scotiabank", "exchange": "TSX", "region": "CA", "popularity": 720},
    {"symbol": "K", "name": "Kellanova", "exchange": "NYSE", "region": "US", "popularity": 730},
    {"symbol": "KO", "name": "Coca-Cola", "exchange": "NYSE", "region": "US", "popularity": 845},
    {"symbol": "KHC", "name": "Kraft Heinz", "exchange": "NASDAQ", "region": "US", "popularity": 700},
    {"symbol": "KVUE", "name": "Kenvue", "exchange": "NYSE", "region": "US", "popularity": 690},
    {"symbol": "KMI", "name": "Kinder Morgan", "exchange": "NYSE", "region": "US", "popularity": 685},
    {"symbol": "KMB", "name": "Kimberly-Clark", "exchange": "NYSE", "region": "US", "popularity": 680},
    {"symbol": "KDP", "name": "Keurig Dr Pepper", "exchange": "NASDAQ", "region": "US", "popularity": 675},
    {"symbol": "KR", "name": "Kroger", "exchange": "NYSE", "region": "US", "popularity": 670},
    {"symbol": "KB", "name": "KB Financial Group ADR", "exchange": "NYSE", "region": "KR", "popularity": 665},
    {"symbol": "KBH", "name": "KB Home", "exchange": "NYSE", "region": "US", "popularity": 650},
    {"symbol": "KBWD", "name": "Invesco KBW High Dividend ETF", "exchange": "NASDAQ", "region": "US", "popularity": 620},
    {"symbol": "KBWB", "name": "Invesco KBW Bank ETF", "exchange": "NASDAQ", "region": "US", "popularity": 615},
    {"symbol": "KBWR", "name": "Invesco KBW Regional Banking ETF", "exchange": "NASDAQ", "region": "US", "popularity": 610},
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "exchange": "NYSEARCA", "region": "US", "popularity": 730},
    {"symbol": "DIA", "name": "SPDR Dow Jones ETF", "exchange": "NYSEARCA", "region": "US", "popularity": 700},
    {"symbol": "XLK", "name": "Technology Select Sector SPDR", "exchange": "NYSEARCA", "region": "US", "popularity": 690},
    {"symbol": "XLF", "name": "Financial Select Sector SPDR", "exchange": "NYSEARCA", "region": "US", "popularity": 685},
    {"symbol": "GLD", "name": "SPDR Gold Shares", "exchange": "NYSEARCA", "region": "US", "popularity": 680},
    {"symbol": "SLV", "name": "iShares Silver Trust", "exchange": "NYSEARCA", "region": "US", "popularity": 675},
    {"symbol": "ARKK", "name": "ARK Innovation ETF", "exchange": "NYSEARCA", "region": "US", "popularity": 670},
    {"symbol": "MSTR", "name": "MicroStrategy", "exchange": "NASDAQ", "region": "US", "popularity": 740},
    {"symbol": "RIOT", "name": "Riot Platforms", "exchange": "NASDAQ", "region": "US", "popularity": 700},
    {"symbol": "MARA", "name": "MARA Holdings", "exchange": "NASDAQ", "region": "US", "popularity": 705},
]
# Remove accidental duplicates while preserving order.
_deduped_catalog: list[TickerRow] = []
_seen_symbols: set[str] = set()
for _row in TICKER_CATALOG:
    _symbol = _row["symbol"].upper()
    if _symbol in _seen_symbols:
        continue
    _seen_symbols.add(_symbol)
    _deduped_catalog.append(_row)
TICKER_CATALOG = _deduped_catalog
EXACT_ALIASES: dict[str, str] = {
    "HEIAA": "HEIA.AS",
    "INGA": "INGA.AS",
    "KBC": "KBC.BR",
    "ABI": "ABI.BR",
}

_BY_SYMBOL: dict[str, TickerRow] = {row["symbol"].upper(): row for row in TICKER_CATALOG}


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
    }
    if score is not None:
        payload["score"] = score
    return payload


def get_ticker_metadata(symbol: str) -> TickerRow | None:
    normalized = _normalize(symbol)
    if not normalized:
        return None

    alias = EXACT_ALIASES.get(normalized, normalized)
    row = _BY_SYMBOL.get(alias)
    return _to_payload(row) if row else None


def search_tickers(query: str, limit: int = 20) -> list[TickerRow]:
    normalized = _normalize(query)

    if not normalized:
        return top_catalog_tickers(limit)

    clean_query = _clean_for_match(normalized)
    ranked: list[tuple[int, TickerRow]] = []

    for row in TICKER_CATALOG:
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


def top_catalog_tickers(limit: int = 10) -> list[TickerRow]:
    ranked = sorted(TICKER_CATALOG, key=lambda item: (-item["popularity"], item["symbol"]))
    return [_to_payload(row) for row in ranked[:limit]]

