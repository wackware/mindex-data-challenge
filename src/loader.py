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
    conn.executescript("""
        PRAGMA foreign_keys = OFF;
        DROP TABLE IF EXISTS fact_sales;
        DROP TABLE IF EXISTS dim_date;
        DROP TABLE IF EXISTS dim_store;
        DROP TABLE IF EXISTS dim_product;
        DROP TABLE IF EXISTS dim_customer;
        PRAGMA foreign_keys = ON;

        CREATE TABLE dim_date (
            date_key    INTEGER PRIMARY KEY,
            full_date   TEXT NOT NULL,
            year        INTEGER,
            month       INTEGER,
            day         INTEGER,
            quarter     INTEGER,
            day_of_week TEXT,
            month_name  TEXT
        );

        CREATE TABLE dim_store (
            store_key    INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id     TEXT NOT NULL UNIQUE,
            store_name   TEXT,
            city         TEXT,
            state        TEXT,
            zip_code     TEXT,
            zip_valid    INTEGER DEFAULT 1,
            region       TEXT,
            opened_date  TEXT
        );

        CREATE TABLE dim_product (
            product_key   INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id    TEXT NOT NULL UNIQUE,
            product_name  TEXT,
            category      TEXT,
            unit_price    REAL,
            supplier_id   TEXT,
            price_is_zero INTEGER DEFAULT 0
        );

        CREATE TABLE dim_customer (
            customer_key  INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id   TEXT UNIQUE,
            is_guest      INTEGER DEFAULT 0
        );

        CREATE TABLE fact_sales (
            transaction_id        TEXT PRIMARY KEY,
            date_key              INTEGER REFERENCES dim_date(date_key),
            store_key             INTEGER REFERENCES dim_store(store_key),
            product_key           INTEGER REFERENCES dim_product(product_key),
            customer_key          INTEGER REFERENCES dim_customer(customer_key),
            quantity              INTEGER,
            unit_price            REAL,
            total_amount          REAL,
            is_return             INTEGER DEFAULT 0,
            has_price_discrepancy INTEGER DEFAULT 0
        );
    """)


def load_dims(conn: sqlite3.Connection,
              stores: pd.DataFrame,
              products: pd.DataFrame,
              transactions: pd.DataFrame) -> dict:
    """
    Populate dim_date, dim_store, dim_product, dim_customer.
    Returns {"store": {store_id: store_key}, "product": {...}, "customer": {...}}.
    date_key is YYYYMMDD — computed inline in load_facts, no map needed.
    """
    # --- dim_date: one row per calendar day in the transaction window ---
    dates = pd.to_datetime(transactions["transaction_date"], errors="coerce").dropna()
    date_range = pd.date_range(dates.min(), dates.max())
    conn.executemany(
        "INSERT OR IGNORE INTO dim_date VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                int(d.strftime("%Y%m%d")),
                d.strftime("%Y-%m-%d"),
                int(d.year),
                int(d.month),
                int(d.day),
                int((d.month - 1) // 3 + 1),
                d.strftime("%A"),
                d.strftime("%B"),
            )
            for d in date_range
        ],
    )

    # --- dim_store ---
    for _, row in stores.iterrows():
        conn.execute(
            """INSERT INTO dim_store
               (store_id, store_name, city, state, zip_code, zip_valid, region, opened_date)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                row["store_id"],
                row.get("store_name"),
                row.get("city"),
                row.get("state"),
                str(row["zip_code"]),
                int(row.get("zip_valid", 1)),
                row.get("region"),
                row.get("opened_date"),
            ),
        )
    store_map = {r[0]: r[1] for r in conn.execute("SELECT store_id, store_key FROM dim_store")}

    # --- dim_product ---
    for _, row in products.iterrows():
        conn.execute(
            """INSERT INTO dim_product
               (product_id, product_name, category, unit_price, supplier_id, price_is_zero)
               VALUES (?,?,?,?,?,?)""",
            (
                row["product_id"],
                row.get("product_name"),
                row.get("category"),
                float(row["unit_price"]),
                row.get("supplier_id"),
                int(row.get("price_is_zero", 0)),
            ),
        )
    product_map = {r[0]: r[1] for r in conn.execute("SELECT product_id, product_key FROM dim_product")}

    # --- dim_customer: synthetic guest first, then real customers ---
    conn.execute("INSERT INTO dim_customer (customer_id, is_guest) VALUES ('CUST_GUEST', 1)")
    unique_customers = [
        c for c in transactions["customer_id"].dropna().unique() if c != "CUST_GUEST"
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO dim_customer (customer_id, is_guest) VALUES (?,0)",
        [(c,) for c in unique_customers],
    )
    customer_map = {r[0]: r[1] for r in conn.execute("SELECT customer_id, customer_key FROM dim_customer")}

    conn.commit()
    return {"store": store_map, "product": product_map, "customer": customer_map}


def load_facts(conn: sqlite3.Connection,
               transactions: pd.DataFrame,
               key_maps: dict) -> None:
    """Populate fact_sales from clean transactions using surrogate key maps."""
    store_map = key_maps["store"]
    product_map = key_maps["product"]
    customer_map = key_maps["customer"]

    rows = []
    for _, row in transactions.iterrows():
        date_key = int(str(row["transaction_date"]).replace("-", ""))
        store_key = store_map.get(row["store_id"])
        product_key = product_map.get(row["product_id"])
        customer_key = customer_map.get(row["customer_id"])

        if store_key is None or product_key is None or customer_key is None:
            continue  # shouldn't happen after clean_transactions; defensive guard

        rows.append((
            row["transaction_id"],
            date_key,
            store_key,
            product_key,
            customer_key,
            int(row["quantity"]),
            float(row["unit_price"]),
            float(row["total_amount"]),
            int(row["is_return"]),
            int(row["has_price_discrepancy"]),
        ))

    conn.executemany(
        """INSERT INTO fact_sales
           (transaction_id, date_key, store_key, product_key, customer_key,
            quantity, unit_price, total_amount, is_return, has_price_discrepancy)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()


def write_exclusions(exclusions: list[dict]) -> None:
    """Write excluded rows with reason to output/exclusions.json."""
    EXCLUSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXCLUSIONS_PATH, "w") as f:
        json.dump(exclusions, f, indent=2, default=str)
