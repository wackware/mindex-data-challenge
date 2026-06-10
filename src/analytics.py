"""
analytics.py — Business analytics queries against warehouse.db.

All queries run via sqlite3 SQL (not pandas). Results written to
output/analytics.json. SQL is the right tool for set-based aggregations
on a relational schema.
"""
import sqlite3
import json
from pathlib import Path

OUTPUT_PATH = Path("output/analytics.json")


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def top_5_stores_by_net_revenue(conn: sqlite3.Connection) -> list[dict]:
    """Q1: Top 5 stores by net revenue in the most recent 30-day window."""
    cur = conn.execute("""
        WITH max_date AS (
            SELECT MAX(dd.full_date) AS max_dt
            FROM fact_sales fs
            JOIN dim_date dd ON fs.date_key = dd.date_key
        )
        SELECT ds.store_id,
               ds.store_name,
               ROUND(SUM(fs.total_amount), 2) AS net_revenue
        FROM fact_sales fs
        JOIN dim_date dd ON fs.date_key = dd.date_key
        JOIN dim_store ds ON fs.store_key = ds.store_key
        WHERE dd.full_date >= DATE((SELECT max_dt FROM max_date), '-29 days')
        GROUP BY ds.store_id, ds.store_name
        ORDER BY net_revenue DESC
        LIMIT 5
    """)
    return _rows(cur)


def mom_revenue_by_category(conn: sqlite3.Connection) -> list[dict]:
    """Q2: Month-over-month revenue change (%) by product category."""
    cur = conn.execute("""
        WITH monthly AS (
            SELECT dp.category,
                   dd.year,
                   dd.month,
                   ROUND(SUM(fs.total_amount), 2) AS revenue
            FROM fact_sales fs
            JOIN dim_date dd  ON fs.date_key    = dd.date_key
            JOIN dim_product dp ON fs.product_key = dp.product_key
            GROUP BY dp.category, dd.year, dd.month
        )
        SELECT m.category,
               m.year,
               m.month,
               m.revenue,
               prev.revenue                                              AS prev_month_revenue,
               ROUND(100.0 * (m.revenue - prev.revenue) / prev.revenue, 1) AS mom_change_pct
        FROM monthly m
        LEFT JOIN monthly prev
            ON  m.category = prev.category
            AND (
                    (m.month  > 1 AND prev.year = m.year     AND prev.month = m.month - 1)
                 OR (m.month  = 1 AND prev.year = m.year - 1 AND prev.month = 12)
                )
        ORDER BY m.category, m.year, m.month
    """)
    return _rows(cur)


def return_rate_by_store(conn: sqlite3.Connection) -> list[dict]:
    """Q3: Return rate by store; flag stores > 10%."""
    cur = conn.execute("""
        SELECT ds.store_id,
               ds.store_name,
               ROUND(100.0 * SUM(fs.is_return) / COUNT(*), 1) AS return_rate_pct,
               CASE WHEN 100.0 * SUM(fs.is_return) / COUNT(*) > 10
                    THEN 'FLAGGED' ELSE 'OK'
               END AS flag
        FROM fact_sales fs
        JOIN dim_store ds ON fs.store_key = ds.store_key
        GROUP BY ds.store_id, ds.store_name
        ORDER BY return_rate_pct DESC
    """)
    return _rows(cur)


def avg_transaction_value_by_region(conn: sqlite3.Connection) -> list[dict]:
    """Q4: Average transaction value by region (exclude returns)."""
    cur = conn.execute("""
        SELECT ds.region,
               ROUND(SUM(fs.total_amount) / COUNT(*), 2) AS avg_txn_value,
               COUNT(*) AS transaction_count
        FROM fact_sales fs
        JOIN dim_store ds ON fs.store_key = ds.store_key
        WHERE fs.is_return = 0
        GROUP BY ds.region
        ORDER BY avg_txn_value DESC
    """)
    return _rows(cur)


def top_10_customers_by_lifetime_spend(conn: sqlite3.Connection) -> list[dict]:
    """Q5: Top 10 non-guest customers by lifetime spend + tx count + AOV."""
    cur = conn.execute("""
        SELECT dc.customer_id,
               ROUND(SUM(fs.total_amount), 2)             AS lifetime_spend,
               COUNT(*)                                    AS transaction_count,
               ROUND(SUM(fs.total_amount) / COUNT(*), 2)  AS avg_order_value
        FROM fact_sales fs
        JOIN dim_customer dc ON fs.customer_key = dc.customer_key
        WHERE dc.is_guest = 0
        GROUP BY dc.customer_id
        ORDER BY lifetime_spend DESC
        LIMIT 10
    """)
    return _rows(cur)


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
