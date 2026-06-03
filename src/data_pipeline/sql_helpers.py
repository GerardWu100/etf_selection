"""
sql_helpers.py
----------------
Small ClickHouse SQL formatting helpers reused by export and adapter queries.
"""

from __future__ import annotations

import pandas as pd


def quote_symbol_for_sql(symbol: str) -> str:
    """
    Return a SQL-safe single-quoted symbol literal for ClickHouse ``IN`` lists.

    ETF tickers rarely contain apostrophes, but escaping keeps the helper correct
    for any symbol string passed in from screened universes.
    """
    escaped = symbol.replace("'", "''")
    return f"'{escaped}'"


def build_symbols_in_list(symbols: list[str]) -> str:
    """Join quoted symbols into a comma-separated SQL ``IN`` list."""
    return ", ".join(quote_symbol_for_sql(symbol) for symbol in symbols)


def exclusive_end_date(inclusive_end: str) -> str:
    """
    Convert an inclusive calendar end date to an exclusive timestamp bound.

    Minute-bar tables store ``ts`` as timestamps, so an inclusive end date needs
    a +1 day exclusive upper bound to keep all bars on the final calendar day.
    """
    return (pd.Timestamp(inclusive_end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
