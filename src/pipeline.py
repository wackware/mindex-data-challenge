"""
pipeline.py — Orchestrates the full data pipeline end-to-end.

Run: python src/pipeline.py

Stages (in order):
  1. Profile raw data  → output/profiling_report.json
  2. Clean raw data    → clean DataFrames in memory
  3. Load warehouse    → output/warehouse.db
  4. Run analytics     → output/analytics.json
"""
import json
import sqlite3
import pandas as pd
from pathlib import Path

from profiler import profile
from cleaner import clean_stores, clean_products, clean_transactions
from loader import create_schema, load_dims, load_facts, write_exclusions, DB_PATH
from analytics import run_all

RAW = Path("data/raw")
PROFILE_OUT = Path("output/profiling_report.json")


def main():
    print("=== Mindex Data Pipeline ===\n")

    # --- Stage 1: Profile ---
    print("[1/4] Profiling raw data...")
    raw = {name: pd.read_csv(RAW / f"{name}.csv") for name in ("stores", "products", "transactions")}
    profiling = {name: profile(df, name) for name, df in raw.items()}
    PROFILE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_OUT, "w") as f:
        json.dump(profiling, f, indent=2, default=str)
    print(f"  Report written to {PROFILE_OUT}")

    # --- Stage 2: Clean ---
    print("[2/4] Cleaning data...")
    stores_clean = clean_stores(raw["stores"])
    products_clean = clean_products(raw["products"])
    valid_store_ids = set(stores_clean["store_id"])
    valid_product_ids = set(products_clean["product_id"])
    transactions_clean, exclusions = clean_transactions(
        raw["transactions"], valid_store_ids, valid_product_ids
    )
    write_exclusions(exclusions)
    print(f"  Clean transactions: {len(transactions_clean)} rows  |  Excluded: {len(exclusions)}")

    # --- Stage 3: Load ---
    print("[3/4] Loading warehouse...")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    key_maps = load_dims(conn, stores_clean, products_clean, transactions_clean)
    load_facts(conn, transactions_clean, key_maps)
    conn.commit()
    conn.close()
    print(f"  Warehouse written to {DB_PATH}")

    # --- Stage 4: Analytics ---
    print("[4/4] Running analytics...")
    conn = sqlite3.connect(DB_PATH)
    run_all(conn)
    conn.close()

    print("\n=== Pipeline complete ===")


if __name__ == "__main__":
    main()
