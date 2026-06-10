"""
loader.py — Star schema creation and population.

Creates output/warehouse.db with: dim_date, dim_store, dim_product,
dim_customer, fact_sales. Writes excluded rows to output/exclusions.json.
"""
import sqlite3
import json
import pandas as pd
from pathlib import Path

DB_PATH = Path("output/warehouse.db")
EXCLUSIONS_PATH = Path("output/exclusions.json")


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all dimension and fact tables (DROP IF EXISTS → CREATE)."""
    raise NotImplementedError("TODO Phase 3")


def load_dims(conn: sqlite3.Connection,
              stores: pd.DataFrame,
              products: pd.DataFrame,
              transactions: pd.DataFrame) -> dict:
    """
    Populate dim_date, dim_store, dim_product, dim_customer.
    Returns a dict of {natural_key: surrogate_key} lookup maps for fact loading.
    """
    raise NotImplementedError("TODO Phase 3")


def load_facts(conn: sqlite3.Connection,
               transactions: pd.DataFrame,
               key_maps: dict) -> None:
    """Populate fact_sales from clean transactions using surrogate key maps."""
    raise NotImplementedError("TODO Phase 3")


def write_exclusions(exclusions: list[dict]) -> None:
    """Write excluded rows with reason to output/exclusions.json."""
    EXCLUSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXCLUSIONS_PATH, "w") as f:
        json.dump(exclusions, f, indent=2, default=str)
