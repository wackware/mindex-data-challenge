"""
cleaner.py — Data cleaning pipeline.

Functions operate on raw DataFrames loaded from data/raw/*.csv and return
cleaned DataFrames ready for loader.py. Each function corresponds to one or
more rows in the data quality table.
"""
import pandas as pd


def normalize_dates(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Coerce mixed date formats (ISO, MM/DD/YYYY, DD-MM-YYYY) to YYYY-MM-DD."""
    raise NotImplementedError("TODO Phase 2")


def strip_dollar(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Strip leading $ from a string-typed numeric column and cast to float."""
    raise NotImplementedError("TODO Phase 2")


def clean_stores(df: pd.DataFrame) -> pd.DataFrame:
    """Handle: near-duplicate S007, malformed zip S003, NULL regions."""
    raise NotImplementedError("TODO Phase 2")


def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    """Handle: duplicate P012, two prices P005, NULL categories, zero price P027."""
    raise NotImplementedError("TODO Phase 2")


def clean_transactions(df: pd.DataFrame, valid_store_ids: set, valid_product_ids: set) -> pd.DataFrame:
    """
    Handle: mixed dates, $-amounts, silent discounts, orphaned FKs,
    NULL customer_ids, zero-quantity rows, future dates, exact duplicates.
    Returns (clean_df, exclusions_df).
    """
    raise NotImplementedError("TODO Phase 2")
