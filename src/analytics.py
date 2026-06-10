"""
analytics.py — Business analytics queries against warehouse.db.

All queries run via sqlite3 SQL (not pandas). Results written to
output/analytics.json. SQL is the right tool for set-based aggregations
on a relational schema.
"""
import sqlite3
import json
import pandas as pd
from pathlib import Path

OUTPUT_PATH = Path("output/analytics.json")


def top_5_stores_by_net_revenue(conn: sqlite3.Connection) -> list[dict]:
    """Q1: Top 5 stores by net revenue in the most recent 30-day window."""
    raise NotImplementedError("TODO Phase 4")


def mom_revenue_by_category(conn: sqlite3.Connection) -> list[dict]:
    """Q2: Month-over-month revenue change (%) by product category."""
    raise NotImplementedError("TODO Phase 4")


def return_rate_by_store(conn: sqlite3.Connection) -> list[dict]:
    """Q3: Return rate by store; flag stores > 10%."""
    raise NotImplementedError("TODO Phase 4")


def avg_transaction_value_by_region(conn: sqlite3.Connection) -> list[dict]:
    """Q4: Average transaction value by region (exclude returns)."""
    raise NotImplementedError("TODO Phase 4")


def top_10_customers_by_lifetime_spend(conn: sqlite3.Connection) -> list[dict]:
    """Q5: Top 10 non-guest customers by lifetime spend + tx count + AOV."""
    raise NotImplementedError("TODO Phase 4")


def run_all(conn: sqlite3.Connection) -> None:
    results = {
        "top_5_stores_net_revenue":       top_5_stores_by_net_revenue(conn),
        "mom_revenue_by_category":         mom_revenue_by_category(conn),
        "return_rate_by_store":            return_rate_by_store(conn),
        "avg_txn_value_by_region":         avg_transaction_value_by_region(conn),
        "top_10_customers_lifetime_spend": top_10_customers_by_lifetime_spend(conn),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Analytics written to {OUTPUT_PATH}")
